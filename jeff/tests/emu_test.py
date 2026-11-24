"""Run Jeff's native code (from the patched libyoyo.so) under Unicorn with a mocked engine.

usage: python emu_test.py <patched libyoyo.so> <jeff.elf> <engine.ld>

Every engine function Jeff calls is replaced by a Python stub that keeps a tiny model of
instances / variables / sprites. The tests drive Jeff through: function-table registration,
the character-menu hook, the select-list hook, Create, combos (jab-cross-hook-uppercut for both
attack buttons), skill 1, skill 2 and the Bone Breaker special, and check the results.
This can't prove the game will accept everything (that needs a phone), but it catches crashes,
wrong arguments and logic slips in the native code.
"""
import re, struct, subprocess, sys
from unicorn import Uc, UcError, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_INVALID
from unicorn.arm64_const import *

SO, ELF, LD = sys.argv[1:4]
BASE = 0x10000000                       # load bias (non-zero so NULL derefs fault)
HEAP = 0x80000000; HEAP_SZ = 0x4000000
STACK = 0x90000000; STACK_SZ = 0x200000
STUBS = 0xA0000000                      # fake vtable targets
RET_MAGIC = 0xB0000000

so = open(SO, 'rb').read()
uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
# enable FP/SIMD
uc.reg_write(UC_ARM64_REG_CPACR_EL1, 0x300000)

# ---- map PT_LOAD segments -------------------------------------------------------------------
phoff, = struct.unpack_from('<Q', so, 0x20); phnum, = struct.unpack_from('<H', so, 0x38)
for i in range(phnum):
    t, fl, off, va, pa, fsz, msz, al = struct.unpack_from('<IIQQQQQQ', so, phoff + 56 * i)
    if t != 1:
        continue
    start = (BASE + va) & ~0xfff; end = (BASE + va + msz + 0xfff) & ~0xfff
    try:
        uc.mem_map(start, end - start)
    except UcError:
        # overlapping page with previous segment: map the remainder
        for p in range(start, end, 0x1000):
            try: uc.mem_map(p, 0x1000)
            except UcError: pass
    uc.mem_write(BASE + va, so[off:off + fsz])
uc.mem_map(HEAP, HEAP_SZ); uc.mem_map(STACK, STACK_SZ); uc.mem_map(STUBS, 0x10000); uc.mem_map(RET_MAGIC, 0x1000)

# ---- symbols ------------------------------------------------------------------------------
ENG = {}
for l in open(LD):
    m = re.match(r'(\w+) = (0x[0-9a-f]+);', l)
    if m: ENG[m.group(1)] = int(m.group(2), 16)
ENG.update(mod_initllvm_hook=0x3000000, mod_get_char_hook=0x3044a70, mod_charsel_ext=0x3043880)
J = {p[2]: int(p[0], 16) for p in (l.split() for l in subprocess.run(['nm', ELF], capture_output=True, text=True).stdout.splitlines()) if len(p) == 3}

heap_ptr = HEAP
def alloc(n):
    global heap_ptr
    a = heap_ptr; heap_ptr += (n + 15) & ~15
    uc.mem_write(a, b'\0' * n); return a
def rd(a, n): return bytes(uc.mem_read(a, n))
def u64(a): return struct.unpack('<Q', rd(a, 8))[0]
def cstr(a):
    b = b''
    while True:
        c = rd(a, 1)
        if c == b'\0': return b.decode()
        b += c; a += 1

# ---- variable ids -------------------------------------------------------------------------
VAR_ID = {}
for name, addr in ENG.items():
    if name.startswith('g_VAR_') or name.startswith('g_FUNC_'):
        vid = 100000 + len(VAR_ID)
        VAR_ID[vid] = name[6:] if name.startswith('g_VAR_') else name
        uc.mem_write(BASE + addr + 8, struct.pack('<i', vid))
NAME_ID = {v: k for k, v in VAR_ID.items()}

# ---- RValues & instance model -------------------------------------------------------------
REAL, STRING, ARRAY, UNDEF, OBJECT, BOOL = 0, 1, 2, 5, 6, 13
strings = {}                      # addr -> python str
def rv_read(a):
    v, fl, k = struct.unpack('<QII', rd(a, 16)); k &= 0xffffff
    if k in (REAL, BOOL): return ('num', struct.unpack('<d', struct.pack('<Q', v))[0])
    if k == STRING: return ('str', strings.get(v, '?'))
    if k == OBJECT: return ('inst', v)
    if k == ARRAY: return ('array', v)
    if k == UNDEF: return ('undef', None)
    return ('kind%d' % k, v)
def rv_write(a, val):
    if isinstance(val, tuple) and val[0] == 'str':
        s = alloc(len(val[1]) + 1); uc.mem_write(s, val[1].encode() + b'\0'); strings[s] = val[1]
        uc.mem_write(a, struct.pack('<QII', s, 0, STRING)); return
    if isinstance(val, tuple) and val[0] == 'array':
        uc.mem_write(a, struct.pack('<QII', val[1], 0, ARRAY)); return
    if val is None:
        uc.mem_write(a, struct.pack('<QII', 0, 0, UNDEF)); return
    uc.mem_write(a, struct.pack('<dII', float(val), 0, REAL))

class Inst:
    def __init__(self, obj, iid):
        self.obj, self.id = obj, iid
        self.ptr = alloc(64)
        uc.mem_write(self.ptr, struct.pack('<Q', VTABLE))
        self.slots = {}           # var name -> slot addr (for vtable refs)
        self.arr = {}             # (var, idx) -> value
    def slot(self, var):
        if var not in self.slots:
            a = alloc(16); rv_write(a, None); self.slots[var] = a
        return self.slots[var]
    def get(self, var, idx=None):
        if idx is not None and idx != -0x80000000:
            return self.arr.get((var, idx), 0.0)
        t, v = rv_read(self.slot(var))
        return v
    def set(self, var, val, idx=None):
        if idx is not None and idx != -0x80000000:
            self.arr[(var, idx)] = val; return
        rv_write(self.slot(var), val)

insts = {}; by_ptr = {}
next_id = [100001]
CHARACTER_OBJS = {685, 523, 420}
def new_inst(obj):
    i = Inst(obj, next_id[0]); next_id[0] += 1
    insts[i.id] = i; by_ptr[i.ptr] = i
    i.set('object_index', obj); i.set('x', 0); i.set('y', 0); i.set('depth', 0); i.set('image_xscale', 1)
    return i

# vtable: [2] read ref, [3] write ref -> stubs
VTABLE = alloc(8 * 8)
for k, addr in enumerate(range(8)):
    uc.mem_write(VTABLE + 8 * k, struct.pack('<Q', STUBS + 0x100 * k))
glob = None

def resolve(rv_addr):
    t, v = rv_read(rv_addr)
    if t == 'inst': return by_ptr.get(v)
    if t == 'num':
        if v >= 100000: return insts.get(int(v))
        lst = [i for i in insts.values() if i.obj == int(v)]
        return lst[0] if lst else None
    return None

# ---- stubs --------------------------------------------------------------------------------
calls = []
def X(n): return uc.reg_read(UC_ARM64_REG_X0 + n) if n < 29 else None
def W(n): return X(n) & 0xffffffff
def sW(n): v = W(n); return v - (1 << 32) if v & 0x80000000 else v
def S(n): return struct.unpack('<f', struct.pack('<I', uc.reg_read(UC_ARM64_REG_Q0 + n) & 0xffffffff))[0]
def D(n): return struct.unpack('<d', struct.pack('<Q', uc.reg_read(UC_ARM64_REG_Q0 + n) & 0xffffffffffffffff))[0]
def ret_x(v): uc.reg_write(UC_ARM64_REG_X0, v & 0xffffffffffffffff)
def ret_d(v): uc.reg_write(UC_ARM64_REG_Q0, struct.unpack('<Q', struct.pack('<d', v))[0])
def args_rv(argc, ptr):
    return [rv_read(ptr + 16 * i) for i in range(argc)]
def args_pp(argc, ptr):
    return [rv_read(u64(ptr + 8 * i)) for i in range(argc)]

sprites = {}; next_spr = [3000]; sounds = {}; next_snd = [900]
state = dict(blend=0, func_table=None)

def st_vref(_k):
    def f():
        inst = by_ptr.get(X(0)) or (glob if X(0) == glob.ptr else None)
        var = VAR_ID.get(sW(1), str(sW(1)))
        ret_x(inst.slot(var))
    return f
def st_getvalue():
    inst = resolve(X(0)); var = VAR_ID[sW(1)]; idx = sW(2)
    if inst is None:
        rv_write(X(3), None); calls.append(('get_missing', var)); return
    v = inst.get(var, idx)
    if isinstance(v, str): rv_write(X(3), ('str', v))
    else: rv_write(X(3), v)
def st_setvalue(direct=False):
    def f():
        inst = by_ptr.get(X(0)) if direct else resolve(X(0))
        var = VAR_ID[sW(1)]; idx = sW(2); t, v = rv_read(X(3))
        if inst is None:
            calls.append(('set_missing', var)); return
        inst.set(var, v if t != 'str' else ('str', v), idx)
    return f
def st_getdirect():
    inst = by_ptr.get(X(0)); var = VAR_ID[sW(1)]; rv_write(X(3), inst.get(var, sW(2)))
def st_bool(): t, v = rv_read(X(0)); ret_x(1 if (t == 'num' and v > 0.5) else 0)
def st_real(): t, v = rv_read(X(0)); ret_d(v if t == 'num' else 0.0)
def st_int32():
    t, v = rv_read(X(0))
    ret_x(int(v) & 0xffffffff if t == 'num' else (by_ptr[v].id if t == 'inst' else 0))
def st_free(): pass
def st_create_string():
    s = cstr(X(1)); rv_write(X(0), ('str', s))
def st_find(): i = insts.get(sW(0)); ret_x(i.ptr if i else 0)
def st_sprite_add():
    a = args_rv(W(3), X(4)); sid = next_spr[0]; next_spr[0] += 1
    sprites[sid] = (a[0][1], int(a[1][1]), int(a[4][1]), int(a[5][1])); rv_write(X(0), sid)
def st_stream():
    a = args_rv(1, X(4)); sid = next_snd[0]; next_snd[0] += 1; sounds[sid] = a[0][1]; rv_write(X(0), sid)
def st_play(): a = args_rv(W(3), X(4)); calls.append(('play', a[0][1])); rv_write(X(0), 77)
def st_noop_ret(): rv_write(X(0), None) if X(0) else None
def st_blend(): a = args_rv(1, X(4)); state['blend'] = a[0][1]; rv_write(X(0), None)
def st_objspr(): a = args_rv(2, X(4)); calls.append(('object_set_sprite', a[0][1], a[1][1])); rv_write(X(0), None)
def st_icreate():
    a = args_rv(4, X(4)); i = new_inst(int(a[3][1])); i.set('x', a[0][1]); i.set('y', a[1][1])
    calls.append(('instance_create', int(a[3][1]), a[0][1], a[1][1])); rv_write(X(0), i.id)
def st_inum():
    a = args_rv(1, X(4)); obj = int(a[0][1])
    n = len([i for i in insts.values() if (i.obj == obj or (obj == 420 and i.obj in CHARACTER_OBJS))])
    rv_write(X(0), n)
def st_ifind():
    a = args_rv(2, X(4)); obj, k = int(a[0][1]), int(a[1][1])
    lst = [i for i in insts.values() if (i.obj == obj or (obj == 420 and i.obj in CHARACTER_OBJS))]
    rv_write(X(0), lst[k].id if k < len(lst) else -4)
def st_iexists():
    a = args_rv(1, X(4)); t, v = a[0]
    ok = (t == 'num' and int(v) in insts) or (t == 'inst' and v in by_ptr)
    rv_write(X(0), 1 if ok else 0)
def st_draw_ext():
    spr = sW(1)
    if spr not in sprites: calls.append(('BAD_SPRITE_DRAW', spr))
    calls.append(('draw', spr, round(S(0), 2), state['blend']))
def st_draw_self(): calls.append(('draw_self',))
def st_legacy():
    fid = VAR_ID.get(sW(4), '?')
    if 'gui_width' in fid: rv_write(X(2), 1280.0)
    elif 'gui_height' in fid: rv_write(X(2), 720.0)
    else: rv_write(X(2), None)
    ret_x(X(2))
def st_script(name):
    def f():
        argc = sW(3); a = args_pp(argc, X(4)) if argc > 0 else []
        calls.append((name, argc, a)); rv_write(X(2), None); ret_x(X(2))
    return f
def st_event(name):
    def f(): calls.append((name,))
    return f
def st_mod_init():
    vars_ = X(0)
    tbl = alloc(24 * 0xe65)
    for i in range(0xe65):
        uc.mem_write(tbl + 24 * i, struct.pack('<QQQ', 0x1000 + i, 0x2000 + i, 0))
    uc.mem_write(vars_ + 0x14, struct.pack('<i', 0xe65)); uc.mem_write(vars_ + 0x28, struct.pack('<Q', tbl))
    state['func_table'] = tbl
def st_mod_get_char():
    calls.append(('mod_get_char', sW(3))); ret_x(X(2))

STUB = {
    'BOOL_RValue': st_bool, 'REAL_RValue_Ex': st_real, 'INT32_RValue': st_int32, 'FREE_RValue__Pre': st_free,
    'YYCreateString': st_create_string, 'YYGML_Variable_GetValue': st_getvalue,
    'YYGML_Variable_SetValue': st_setvalue(False), 'Variable_SetValue_Direct': st_setvalue(True),
    'Variable_GetValue_Direct': st_getdirect, 'YYGML_FindInstance': st_find,
    'YYGML_CallLegacyFunction': st_legacy, 'YYGML_draw_sprite_ext': st_draw_ext, 'YYGML_draw_self': st_draw_self,
    'YYGML_draw_set_alpha': lambda: None, 'YYGML_draw_set_colour': lambda: None, 'YYGML_draw_rectangle': lambda: None,
    'F_SpriteAdd': st_sprite_add, 'F_SpriteExists': st_noop_ret, 'F_AudioCreateStream': st_stream,
    'F_AudioPlaySound': st_play, 'F_AudioStopSound': st_noop_ret, 'F_AudioSoundPitch': st_noop_ret,
    'F_GPUSetBlendMode': st_blend, 'F_InstanceCreateDepth': st_icreate, 'F_InstanceNumber': st_inum,
    'F_InstanceFind': st_ifind, 'F_InstanceExists': st_iexists, 'F_ObjectSetSprite': st_objspr,
    'F_DrawCircle': st_noop_ret, 'F_DrawLineWidth': st_noop_ret,
    'gml_Script_scr_plr_step': st_script('scr_plr_step'), 'gml_Script_scr_combo_normal': st_script('scr_combo_normal'),
    'gml_Script_scr_char_charge_effect': st_script('scr_char_charge_effect'),
    'gml_Object_o_parent_character_Create_0': st_event('parent_create'),
    'gml_Object_o_parent_character_Destroy_0': st_event('parent_destroy'),
    'mod_initllvm_hook': st_mod_init, 'mod_get_char_hook': st_mod_get_char, 'mod_charsel_ext': st_event('mod_charsel_ext'),
}
HOOKS = {BASE + ENG[k]: f for k, f in STUB.items()}
for k in range(8):
    HOOKS[STUBS + 0x100 * k] = st_vref(k)

def on_code(u, addr, size, _):
    f = HOOKS.get(addr)
    if f is None:
        if addr == RET_MAGIC: u.emu_stop()
        return
    f()
    u.reg_write(UC_ARM64_REG_PC, u.reg_read(UC_ARM64_REG_LR))
uc.hook_add(UC_HOOK_CODE, on_code, begin=BASE, end=BASE + 0x4000000)
uc.hook_add(UC_HOOK_CODE, on_code, begin=STUBS, end=STUBS + 0x10000)
uc.hook_add(UC_HOOK_CODE, on_code, begin=RET_MAGIC, end=RET_MAGIC + 4)
def on_bad(u, access, addr, size, value, _):
    print(f'!! invalid memory access at {addr:#x} pc={u.reg_read(UC_ARM64_REG_PC) - BASE:#x}')
    return False
uc.hook_add(UC_HOOK_MEM_INVALID, on_bad)

# g_pGlobal -> fake global object
glob = Inst(-5, -5); by_ptr[glob.ptr] = glob
uc.mem_write(BASE + ENG['g_pGlobal'], struct.pack('<Q', glob.ptr))

def call(fn, *args, fargs=()):
    for i, a in enumerate(args):
        uc.reg_write(UC_ARM64_REG_X0 + i, a)
    uc.reg_write(UC_ARM64_REG_SP, STACK + STACK_SZ - 0x100)
    uc.reg_write(UC_ARM64_REG_LR, RET_MAGIC)
    uc.reg_write(UC_ARM64_REG_X18, 0)
    uc.emu_start(BASE + J[fn], RET_MAGIC, count=5_000_000)
    return X(0)

fails = []
def check(cond, msg):
    print(('  ok   ' if cond else '  FAIL ') + msg)
    if not cond: fails.append(msg)

# ============================== tests =========================================================
print('[1] function table registration')
vars_ = alloc(0x40); uc.mem_write(vars_ + 0x14, struct.pack('<i', 0xe41))
call('jeff_initllvm', vars_)
n, = struct.unpack('<i', rd(vars_ + 0x14, 4)); tbl = u64(vars_ + 0x28)
check(n == 0xe6d, f'count 0xe65 -> {n:#x}')
check(tbl == BASE + J['g_funcs'] if 'g_funcs' in J else tbl != state['func_table'], 'table pointer moved to Jeff table')
exp = ['Create_0', 'Step_0', 'Draw_0', 'Draw_64', 'Destroy_0', 'Alarm_0', 'Alarm_2', 'Alarm_3']
for k, e in enumerate(exp):
    nm, fn, gs = struct.unpack('<QQQ', rd(tbl + 24 * (0xe65 + k), 24))
    check(cstr(nm) == 'gml_Object_o_jeff_' + e and fn == BASE + J['gml_Object_o_jeff_' + e], f'entry {0xe65 + k:#x} = {cstr(nm)}')
nm, fn, gs = struct.unpack('<QQQ', rd(tbl + 24 * 0xe64, 24))
check(nm == 0x1000 + 0xe64 and fn == 0x2000 + 0xe64, 'mod entries copied')

print('[2] scr_menu_get_char hook')
menu = new_inst(300)
argrv = alloc(16); rv_write(argrv, 1005.0); argv = alloc(8); uc.mem_write(argv, struct.pack('<Q', argrv))
ret = alloc(16)
call('jeff_get_char', menu.ptr, menu.ptr, ret, 1, argv)
check(menu.get('char_name') == 'Jeff', 'char_name = Jeff')
check(menu.get('char_obj') == 685, 'char_obj = 685 (o_jeff)')
check(menu.get('char_face') in sprites and sprites[menu.get('char_face')][0] == 'jeff_face.png', 'char_face = jeff_face.png sprite')
check(len(sprites) == 38 and len(sounds) == 6, f'loaded {len(sprites)} sprites / {len(sounds)} sounds')
check(any(c[0] == 'object_set_sprite' and c[1] == 685 for c in calls), 'object_set_sprite(o_jeff, preview)')
calls.clear()
rv_write(argrv, 7.0)
call('jeff_get_char', menu.ptr, menu.ptr, ret, 1, argv)
check(calls and calls[0] == ('mod_get_char', 1), 'other ids fall through to the mod hook')

print('[3] character select list')
glob.slots['charord'] = alloc(16); uc.mem_write(glob.slots['charord'], struct.pack('<QII', 0x1234, 0, ARRAY))
glob.set('chars_num', 3)
glob.slots['char'] = alloc(16); uc.mem_write(glob.slots['char'], struct.pack('<QII', 0x5678, 0, ARRAY))
for i, v in enumerate([12, 5, 9], 1): glob.arr[('charord', i)] = v
call('jeff_charsel_ext', menu.ptr)
check([glob.arr.get(('charord', i)) for i in range(1, 5)] == [1005, 12, 5, 9], f"charord = {[glob.arr.get(('charord', i)) for i in range(1, 5)]}")
check(glob.get('chars_num') == 4, 'chars_num 3 -> 4')
check(glob.arr.get(('char', 1005)) == 1, 'global.char[1005] = 1 (owned)')
call('jeff_charsel_ext', menu.ptr)
check(glob.get('chars_num') == 4, 'second rebuild does not add Jeff twice')

print('[4] create + alarm0')
ctrl = new_inst(431); ctrl.set('plr_team', 1); ctrl.set('plr_dmg', 46); ctrl.set('plr_energy', 100); ctrl.set('plr_maxenergy', 100)
for k in ('key_defend', 'keyp_special', 'is_hurt', 'is_fallen', 'is_dead', 'is_onair', 'is_charging'): ctrl.set(k, 0)
jeff = new_inst(685); jeff.set('x', 400); jeff.set('y', 300)
call('gml_Object_o_jeff_Create_0', jeff.ptr, jeff.ptr)
check(('parent_create',) in calls, 'event_inherited (parent create) called')
check(jeff.get('stats_hp') == 2300 and jeff.get('char_name') == 'Jeff', 'stats/name set')
check(sprites.get(jeff.get('spr_defend'), ('',))[0] == 'jeff_defend.png', 'spr_defend = crouch-block sprite')
check(jeff.get('spr_mask_stand') == 1684, 'collision mask = erbito mask')
jeff.set('parent', ctrl.id)
call('gml_Object_o_jeff_Alarm_0', jeff.ptr, jeff.ptr)
check(sprites.get(ctrl.get('spr_face'), ('',))[0] == 'jeff_face.png', 'controller spr_face = jeff_face')

print('[5] combos: jab, cross, hook, uppercut (attack A and B)')
for start, label in ((1, 'A'), (50, 'B')):
    calls.clear(); jeff.set('combo_next', start)
    call('gml_Object_o_jeff_Alarm_3', jeff.ptr, jeff.ptr)
    check(ctrl.get('is_attacking') == 1, f'attack {label}: is_attacking set when the combo starts')
    seq = []
    for _ in range(4):
        cn = [c for c in calls if c[0] == 'scr_combo_normal']
        if cn: seq.append(sprites[int(cn[-1][2][0][1])][0])
        calls.clear()
        jeff.set('combo_nextcombo', 1)
        call('gml_Object_o_jeff_Alarm_2', jeff.ptr, jeff.ptr)
    check(seq == ['jeff_jab.png', 'jeff_cross.png', 'jeff_hook.png', 'jeff_uppercut.png'], f'attack {label}: {seq}')
    check(ctrl.get('is_attacking') == 0 and jeff.get('combo_next') == -1, f'attack {label}: uppercut ends the combo, is_attacking cleared')

print('[6] skill 1 (ant swarm)')
calls.clear(); jeff.set('combo_next', 100)
call('gml_Object_o_jeff_Alarm_3', jeff.ptr, jeff.ptr)
for t in range(110):
    call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
    call('gml_Object_o_jeff_Draw_0', jeff.ptr, jeff.ptr)
hb = [c for c in calls if c[0] == 'instance_create' and c[1] == 224]
check(len(hb) >= 12, f'swarm hitboxes created: {len(hb)}')
check(hb and hb[-1][2] > 400 + 150, f'swarm travelled to x={hb[-1][2]:.0f}' if hb else 'no hitbox')
drawn = {sprites[c[1]][0] for c in calls if c[0] == 'draw' and c[1] in sprites}
check({'jeff_s1_circle.png', 'jeff_s1_swarm.png', 'jeff_s1_burst.png'} <= drawn, 'circle/swarm/burst drawn')
check(not any(c[0] == 'BAD_SPRITE_DRAW' for c in calls), 'no invalid sprite draws')

print('[7] skill 2 (starlight lance)')
calls.clear(); jeff.set('combo_next', 110)
call('gml_Object_o_jeff_Alarm_3', jeff.ptr, jeff.ptr)
for t in range(100):
    call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
    call('gml_Object_o_jeff_Draw_0', jeff.ptr, jeff.ptr)
hb = [c for c in calls if c[0] == 'instance_create' and c[1] == 224]
check(len(hb) >= 8, f'beam hitboxes: {len(hb)}')
drawn = {sprites[c[1]][0] for c in calls if c[0] == 'draw' and c[1] in sprites}
check({'jeff_s2_orb.png', 'jeff_s2_beam.png', 'jeff_s2_tip.png', 'jeff_s2_nova.png'} <= drawn, 'orb/beam/tip/nova drawn')

print('[8] special: Bone Breaker')
ectrl = new_inst(431); ectrl.set('plr_team', 2); ectrl.set('plr_hp', 1900); ectrl.set('is_dead', 0)
enemy = new_inst(523); enemy.set('x', 520); enemy.set('y', 300); enemy.set('parent', ectrl.id)
calls.clear()
ctrl.set('key_defend', 1); ctrl.set('keyp_special', 1); ctrl.set('plr_energy', 100)
call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
check(ctrl.get('keyp_special') == 0, 'skill press consumed (no normal skill)')
check(ctrl.get('plr_energy') == 0, 'full energy bar spent')
check(not any(c[0] == 'scr_plr_step' for c in calls), 'framework step paused during special')
ctrl.set('key_defend', 0)
gui_draws = 0
for t in range(14 + 156 + 40):
    calls.clear()
    call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
    call('gml_Object_o_jeff_Draw_64', jeff.ptr, jeff.ptr)
    gui_draws += sum(1 for c in calls if c[0] == 'draw' and c[1] in sprites and sprites[c[1]][0].startswith('jeff_cut_'))
    if t == 5:
        check(abs(jeff.get('x') - 400) > 1, f'Jeff dashes toward the enemy (x={jeff.get("x"):.0f})')
check(gui_draws >= 150, f'cutscene panels drawn on GUI layer: {gui_draws} frames')
check(ectrl.get('plr_hp') == 0, f'enemy HP -> {ectrl.get("plr_hp")}')
check(ctrl.get('can_gethurt') == 1, 'Jeff vulnerable again after the special')
ctrl.set('keyp_special', 0)
calls.clear(); call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
check(any(c[0] == 'scr_plr_step' for c in calls), 'framework step resumes afterwards')

print('[9] special without energy does nothing')
ctrl.set('key_defend', 1); ctrl.set('keyp_special', 1); ctrl.set('plr_energy', 40); ectrl.set('plr_hp', 1500)
call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
check(ctrl.get('plr_energy') == 40 and ectrl.get('plr_hp') == 1500, 'no energy spent, enemy untouched')

print('[10] destroy')
calls.clear(); call('gml_Object_o_jeff_Destroy_0', jeff.ptr, jeff.ptr)
check(('parent_destroy',) in calls, 'parent destroy called')

print('\nRESULT:', 'ALL PASSED' if not fails else f'{len(fails)} FAILED')
sys.exit(1 if fails else 0)
