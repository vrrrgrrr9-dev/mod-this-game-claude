"""Run the mod's native code (from the patched libyoyo.so) under Unicorn with a mocked engine.

usage: python emu_test.py <patched libyoyo.so> <jeff.elf> <engine.ld>

Every engine function the code calls is replaced by a Python stub that keeps a tiny model of
instances / variables / sprites / layers. The tests drive: function-table registration, the
character-menu hook, the select-list hook (offline + online), then Jeff (Create, both combos, both
skills, Bone Breaker) and Black Holing Scyther (Create, both combo chains tick by tick with real
alarm timing, crouch/air attacks, Event Horizon, Void Lance, SINGULARITY + the void stage).
This can't prove the game will accept everything (that needs a phone), but it catches crashes,
wrong arguments and logic slips in the native code.
"""
import re, struct, subprocess, sys
from unicorn import Uc, UcError, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_INVALID
from unicorn.arm64_const import *

SO, ELF, LD = sys.argv[1:4]
import os
GEN_DIR = os.path.dirname(os.path.abspath(ELF))
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
CHARACTER_OBJS = {685, 686, 523, 420}
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
    calls.append(('draw', spr, round(S(0), 2), state['blend'], round(S(3), 2)))
def st_draw_self(): calls.append(('draw_self',))
def slot_owner(addr):
    for inst in list(insts.values()) + [glob]:
        for var, a in inst.slots.items():
            if a == addr: return inst, var
    return None, None
arrays = {}                                     # (inst id, var) -> array length
LAYERS = {1: [101], 2: [201, 202], 3: [301], 4: [401]}     # layer -> element ids
ELTYPE = {1: 1, 2: 2, 3: 5, 4: 4}                          # element id // 100 -> type (2 = instance)
def st_legacy():
    fid = VAR_ID.get(sW(4), '?')
    if 'gui_width' in fid: rv_write(X(2), 1280.0)
    elif 'gui_height' in fid: rv_write(X(2), 720.0)
    elif 'array_length' in fid:
        inst, var = slot_owner(u64(X(5)))
        rv_write(X(2), float(arrays.get((inst.id, var), 0)) if inst else 0.0)
    else: rv_write(X(2), None)
    ret_x(X(2))
def st_layer_all():
    inst, var = slot_owner(X(0))
    for i, l in enumerate(sorted(LAYERS)): inst.arr[(var, i)] = l
    arrays[(inst.id, var)] = len(LAYERS); rv_write(X(0), ('array', 0x7777))
def st_layer_elems():
    a = args_rv(1, X(4)); els = LAYERS.get(int(a[0][1]), [])
    inst, var = slot_owner(X(0))
    for i, e in enumerate(els): inst.arr[(var, i)] = e
    arrays[(inst.id, var)] = len(els); rv_write(X(0), ('array', 0x8888))
def st_eltype(): a = args_rv(1, X(4)); rv_write(X(0), float(ELTYPE.get(int(a[0][1]) // 100, 0)))
def st_layer_vis(): a = args_rv(2, X(4)); calls.append(('layer_visible', int(a[0][1]), a[1][1])); rv_write(X(0), None)
def st_cam(v): return lambda: rv_write(X(0), v)
def st_stretched(): a = args_rv(8, X(4)); calls.append(('stretched', int(a[0][1]))); rv_write(X(0), None)
LAYER_DEPTH = {1: 900000.0, 2: 0.0, 3: 500.0, 4: -200.0}     # layer 4 is in front of the fighters
def st_layer_depth(): a = args_rv(1, X(4)); rv_write(X(0), LAYER_DEPTH.get(int(a[0][1]), 0.0))
def st_part(): a = args_rv(12, X(4)); calls.append(('part', int(a[0][1]))); rv_write(X(0), None)
def st_spritepos():
    a = args_rv(11, X(4)); calls.append(('spritepos', int(a[0][1]), [v for _, v in a[2:10]])); rv_write(X(0), None)
prim = {'open': False, 'n': 0, 'strips': 0, 'verts': 0}
def st_prim_begin():
    if prim['open']: calls.append(('PRIM_NESTED',))
    prim['open'] = True; prim['n'] = 0; calls.append(('prim_begin',)); rv_write(X(0), None)
def st_vertex():
    if not prim['open']: calls.append(('VERTEX_OUTSIDE',))
    a = args_rv(4, X(4))
    if not (0.0 <= a[3][1] <= 1.0): calls.append(('BAD_ALPHA', a[3][1]))
    prim['n'] += 1; prim['verts'] += 1; rv_write(X(0), None)
def st_prim_end():
    if not prim['open']: calls.append(('PRIM_END_UNOPENED',))
    prim['open'] = False; prim['strips'] += 1; calls.append(('prim_end', prim['n'])); rv_write(X(0), None)
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
    'F_ViewGetCamera': st_cam(3.0), 'F_CameraGetViewX': st_cam(100.0), 'F_CameraGetViewY': st_cam(50.0),
    'F_CameraGetViewWidth': st_cam(600.0), 'F_CameraGetViewHeight': st_cam(300.0),
    'F_LayerGetAll': st_layer_all, 'F_LayerGetAllElements': st_layer_elems, 'F_LayerGetElementType': st_eltype,
    'F_LayerSetVisible': st_layer_vis, 'F_PlaceMeeting': st_cam(0.0), 'F_CollisionPoint': st_cam(0.0),
    'F_DrawSpriteStretchedExt': st_stretched,
    'F_AudioIsPlaying': st_cam(0.0),
    'F_LayerGetDepth': st_layer_depth, 'F_DrawSpritePartExt': st_part, 'F_DrawSpritePos': st_spritepos,
    'F_DrawPrimitiveBegin': st_prim_begin, 'F_DrawVertexColor': st_vertex, 'F_DrawPrimitiveEnd': st_prim_end,
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
check(n == 0xe76, f'count 0xe65 -> {n:#x} (8 Jeff + 9 Scyther)')
check(tbl == BASE + J['g_funcs'] if 'g_funcs' in J else tbl != state['func_table'], 'table pointer moved to Jeff table')
exp = ['Create_0', 'Step_0', 'Draw_0', 'Draw_64', 'Destroy_0', 'Alarm_0', 'Alarm_2', 'Alarm_3']
for k, e in enumerate(exp):
    nm, fn, gs = struct.unpack('<QQQ', rd(tbl + 24 * (0xe65 + k), 24))
    check(cstr(nm) == 'gml_Object_o_jeff_' + e and fn == BASE + J['gml_Object_o_jeff_' + e], f'entry {0xe65 + k:#x} = {cstr(nm)}')
sexp = ['Create_0', 'Step_0', 'Draw_0', 'Draw_64', 'Draw_72', 'Destroy_0', 'Alarm_0', 'Alarm_2', 'Alarm_3']
for k, e in enumerate(sexp):
    nm, fn, gs = struct.unpack('<QQQ', rd(tbl + 24 * (0xe6d + k), 24))
    check(cstr(nm) == 'gml_Object_o_scyther_' + e and fn == BASE + J['gml_Object_o_scyther_' + e], f'entry {0xe6d + k:#x} = {cstr(nm)}')
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
check(len(sprites) == 49 and len(sounds) == 7, f'loaded {len(sprites)} sprites / {len(sounds)} sounds')
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
check([glob.arr.get(('charord', i)) for i in range(1, 6)] == [1005, 1006, 12, 5, 9], f"charord = {[glob.arr.get(('charord', i)) for i in range(1, 6)]}")
check(glob.get('chars_num') == 5, 'chars_num 3 -> 5')
check(glob.arr.get(('char', 1005)) == 1 and glob.arr.get(('char', 1006)) == 1, 'global.char[1005] = global.char[1006] = 1 (owned)')
call('jeff_charsel_ext', menu.ptr)
check(glob.get('chars_num') == 5, 'second rebuild does not add them twice')

print('[3b] online character select (global.game_gm == 2): Jeff and Scyther stay out')
glob.set('game_gm', 2.0)
glob.slots['game_plrchar'] = alloc(16); uc.mem_write(glob.slots['game_plrchar'], struct.pack('<QII', 0x9abc, 0, ARRAY))
glob.arr[('game_plrchar', 1)] = 685; glob.arr[('game_plrchar', 2)] = 523
for i, v in enumerate([12, 5, 9], 1): glob.arr[('charord', i)] = v
glob.arr.pop(('charord', 4), None); glob.arr.pop(('charord', 5), None); glob.set('chars_num', 3)
call('jeff_charsel_ext', menu.ptr)
check([glob.arr.get(('charord', i)) for i in range(1, 5)] == [12, 5, 9, None] and glob.get('chars_num') == 3,
      f"online list unchanged: {[glob.arr.get(('charord', i)) for i in range(1, 5)]}")
check(glob.arr.get(('game_plrchar', 1)) == -1, 'leftover offline Jeff pick cleared (game_plrchar[1] = -1)')
check(glob.arr.get(('game_plrchar', 2)) == 523, 'other picks untouched')
check(not any(k[0] == 'game_plrchar' and k[1] > 2 for k in glob.arr), 'only slots 1-2 touched')
glob.arr[('game_plrchar', 2)] = 686
call('jeff_charsel_ext', menu.ptr)
check(glob.arr.get(('game_plrchar', 2)) == -1, 'leftover Scyther pick cleared too')
glob.arr[('game_plrchar', 2)] = 523
glob.set('game_gm', 1.0)
call('jeff_charsel_ext', menu.ptr)
check(glob.arr.get(('charord', 1)) == 1005 and glob.arr.get(('charord', 2)) == 1006 and glob.get('chars_num') == 5,
      'back offline (game_gm 1): both listed again')

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

print('[5] combos: dark flame punches (A) and blue flame kicks (B)')
for start, label, want in ((1, 'A', ['jeff_jab.png', 'jeff_cross.png', 'jeff_hook.png', 'jeff_flurry.png', 'jeff_uppercut.png']),
                           (50, 'B', ['jeff_kick1.png', 'jeff_kick2.png', 'jeff_kick3.png', 'jeff_kick4.png'])):
    calls.clear(); jeff.set('combo_next', start)
    call('gml_Object_o_jeff_Alarm_3', jeff.ptr, jeff.ptr)
    check(ctrl.get('is_attacking') == 1, f'attack {label}: is_attacking set when the combo starts')
    seq = []
    for _ in range(len(want)):
        cn = [c for c in calls if c[0] == 'scr_combo_normal']
        seq.append(sprites[int(cn[-1][2][0][1])][0] if cn else sprites.get(int(jeff.get('sprite_index')), ('',))[0])
        hits = len([c for c in calls if c[0] == 'instance_create' and c[1] == 224])
        if seq[-1] == 'jeff_flurry.png':                   # the flurry runs on Jeff's own step
            for _ in range(26): call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
            check(len([c for c in calls if c[0] == 'instance_create' and c[1] == 224]) - hits >= 5, 'flame flurry: 5 quick hits')
        calls.clear()
        jeff.set('combo_nextcombo', 1)
        call('gml_Object_o_jeff_Alarm_2', jeff.ptr, jeff.ptr)
    check(seq == want, f'attack {label}: {seq}')
    check(ctrl.get('is_attacking') == 0 and jeff.get('combo_next') == -1, f'attack {label}: the finisher ends the combo, is_attacking cleared')

print('[5b] the burning fist / foot')
spr_id = {v[0]: k for k, v in sprites.items()}
calls.clear()
jeff.set('sprite_index', spr_id['jeff_kick2.png']); jeff.set('image_index', 1); jeff.set('image_speed', 0)
call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
jeff.set('sprite_index', spr_id['jeff_kick2.png']); jeff.set('image_index', 1)
call('gml_Object_o_jeff_Draw_0', jeff.ptr, jeff.ptr)
drawn = {sprites[c[1]][0] for c in calls if c[0] == 'draw' and c[1] in sprites}
check({'jeff_jf_fist.png', 'jeff_jf_trail.png', 'jeff_jf_burst.png'} <= drawn, f'dark flame round the kicking foot + a flare as it lands')
plays = [c for c in calls if c[0] == 'play']
calls.clear()
for _ in range(3):
    call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
    jeff.set('sprite_index', spr_id['jeff_kick2.png']); jeff.set('image_index', 1)
check(sum(1 for c in calls if c[0] == 'play') == 0, 'the flare fires once per burning frame, not every step')
jeff.set('sprite_index', spr_id['jeff_stand.png']); jeff.set('image_index', 0)

ectrl = new_inst(431); ectrl.set('plr_team', 2); ectrl.set('plr_hp', 1900); ectrl.set('is_dead', 0)
enemy = new_inst(523); enemy.set('x', 520); enemy.set('y', 300); enemy.set('parent', ectrl.id)

print('[6] skill 1: Meteor Shower')
calls.clear(); jeff.set('combo_next', 100); jeff.set('x', 400)
call('gml_Object_o_jeff_Alarm_3', jeff.ptr, jeff.ptr)
for t in range(130):
    call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
    call('gml_Object_o_jeff_Draw_0', jeff.ptr, jeff.ptr)
hb = [c for c in calls if c[0] == 'instance_create' and c[1] == 224]
check(len(hb) >= 9, f'meteor impacts: {len(hb)} hitboxes')
check(hb and all(abs(c[3] - 286) < 2 for c in hb) and min(c[2] for c in hb) > 430, 'meteors land on the ground in front of him')
drawn = {sprites[c[1]][0] for c in calls if c[0] == 'draw' and c[1] in sprites}
check({'jeff_jf_portal.png', 'jeff_jf_meteor.png', 'jeff_jf_crater.png', 'jeff_jf_aura.png'} <= drawn, 'black holes in the sky, flaming meteors, craters, aura drawn')
check(not any(c[0] == 'BAD_SPRITE_DRAW' for c in calls), 'no invalid sprite draws')

print('[7] skill 2: Abyss Palm (black hole)')
calls.clear(); jeff.set('combo_next', 110); jeff.set('x', 400); enemy.set('x', 540)
call('gml_Object_o_jeff_Alarm_3', jeff.ptr, jeff.ptr)
for t in range(100):
    call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
    call('gml_Object_o_jeff_Draw_0', jeff.ptr, jeff.ptr)
hb = [c for c in calls if c[0] == 'instance_create' and c[1] == 224]
check(len(hb) >= 6, f'black hole hitboxes: {len(hb)}')
check(enemy.get('x') < 540 - 5, f'opponent dragged toward the hole (x 540 -> {enemy.get("x"):.0f})')
drawn = {sprites[c[1]][0] for c in calls if c[0] == 'draw' and c[1] in sprites}
check({'jeff_jf_bh.png', 'jeff_jf_bhring_b.png', 'jeff_jf_bhring_f.png', 'jeff_jf_burst.png', 'jeff_jf_rock.png'} <= drawn, 'black hole core, flame disk (back/front), rocks, detonation drawn')

print('[8] special: Bone Breaker')
enemy.set('x', 520); jeff.set('x', 400); ectrl.set('plr_hp', 1900)
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

print('[9b] Jeff homes in on the opponent; as the CPU he uses the Bone Breaker')
ctrl.set('key_defend', 0); ctrl.set('keyp_special', 0); ctrl.set('plr_energy', 40)
jeff.set('x', 400); jeff.set('image_xscale', 1); jeff.set('hspeed', 0); enemy.set('x', 500); ectrl.set('plr_hp', 1500)
calls.clear(); jeff.set('combo_next', 1)
call('gml_Object_o_jeff_Alarm_3', jeff.ptr, jeff.ptr)
call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
check(jeff.get('hspeed') > 5, f'jab lunges toward the opponent 100 px away (hspeed {jeff.get("hspeed"):.1f})')
for _ in range(6): call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
jeff.set('combo_next', -1); call('gml_Object_o_jeff_Alarm_2', jeff.ptr, jeff.ptr)
ctrl.set('plr_controller', 2); ctrl.set('keyp_special', 1); ctrl.set('plr_energy', 100)
calls.clear(); call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
check(ctrl.get('plr_energy') == 0, 'CPU Jeff fired the Bone Breaker without holding shield')
for t in range(14 + 156 + 40):
    call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
check(ectrl.get('plr_hp') == 0 and ctrl.get('can_gethurt') == 1, 'it lands on the player')
ctrl.set('plr_controller', 0); ctrl.set('keyp_special', 0)

print('[10] destroy')
calls.clear(); call('gml_Object_o_jeff_Destroy_0', jeff.ptr, jeff.ptr)
check(('parent_destroy',) in calls, 'parent destroy called')

# ============================== Black Holing Scyther ==========================================
def spr_name(c): return sprites[c[1]][0] if c[0] == 'draw' and c[1] in sprites else None
def drawn_names(): return {spr_name(c) for c in calls if spr_name(c)}

print('[11] Scyther: scr_menu_get_char(1006)')
calls.clear(); rv_write(argrv, 1006.0)
nspr = len(sprites)
call('jeff_get_char', menu.ptr, menu.ptr, ret, 1, argv)
check(menu.get('char_name') == 'Black Holing Scyther' and menu.get('char_obj') == 686, 'name / object 686')
check(sprites.get(menu.get('char_face'), ('',))[0] == 'scyther_face.png', 'portrait card = scyther_face.png')
nsc = len(sprites) - nspr
check(nsc >= 70 and sum(1 for v in sounds.values() if str(v).startswith('scyther_')) == 8, f'loaded {nsc} Scyther sprites, 8 sounds')
check(any(c[0] == 'object_set_sprite' and c[1] == 686 for c in calls), 'object_set_sprite(o_scyther, preview)')

print('[12] Scyther: create + alarm0')
sc_ctrl = new_inst(431); sc_ctrl.set('plr_team', 1); sc_ctrl.set('plr_dmg', 48); sc_ctrl.set('plr_energy', 100); sc_ctrl.set('plr_maxenergy', 100)
for k in ('key_defend', 'keyp_special', 'is_hurt', 'is_fallen', 'is_dead', 'is_onair', 'is_charging'): sc_ctrl.set(k, 0)
scy = new_inst(686); scy.set('x', 400); scy.set('y', 300); scy.set('image_xscale', 1); scy.set('image_alpha', 1)
calls.clear()
call('gml_Object_o_scyther_Create_0', scy.ptr, scy.ptr)
check(('parent_create',) in calls, 'event_inherited (parent create) called')
check(scy.get('stats_hp') == 2250 and scy.get('char_name') == 'Black Holing Scyther', 'stats/name set')
check(sprites.get(scy.get('spr_defend'), ('',))[0] == 'scyther_defend.png', 'spr_defend = scythe guard')
scy.set('parent', sc_ctrl.id)
call('gml_Object_o_scyther_Alarm_0', scy.ptr, scy.ptr)
check(sprites.get(sc_ctrl.get('spr_face'), ('',))[0] == 'scyther_face.png', 'controller spr_face = scyther_face')

def tick(press_next=True, draw=True):
    """one frame: alarms (alarm[2] counts down and fires), Step, Draw, Draw Begin, Draw GUI."""
    a2 = scy.arr.get(('alarm', 2), -1)
    if a2 is not None and a2 > 0:
        a2 -= 1; scy.arr[('alarm', 2)] = a2
        if a2 == 0:
            scy.arr[('alarm', 2)] = -1
            if press_next: scy.set('combo_nextcombo', 1)
            call('gml_Object_o_scyther_Alarm_2', scy.ptr, scy.ptr)
    call('gml_Object_o_scyther_Step_0', scy.ptr, scy.ptr)
    if draw:
        call('gml_Object_o_scyther_Draw_72', scy.ptr, scy.ptr)
        call('gml_Object_o_scyther_Draw_0', scy.ptr, scy.ptr)
        call('gml_Object_o_scyther_Draw_64', scy.ptr, scy.ptr)

sc_ectrl = new_inst(431); sc_ectrl.set('plr_team', 2); sc_ectrl.set('plr_hp', 1900); sc_ectrl.set('is_dead', 0)
foe = new_inst(523); foe.set('x', 470); foe.set('y', 300); foe.set('parent', sc_ectrl.id)

COMBO_A = ['scyther_a1.png', 'scyther_a2.png', 'scyther_thrust.png', 'scyther_a3.png', 'scyther_a4.png']
COMBO_B = ['scyther_b1.png', 'scyther_b2.png', 'scyther_phase.png', 'scyther_b3.png', 'scyther_b4.png']
def prim_ok():
    bad = [c for c in calls if c[0] in ('PRIM_NESTED', 'VERTEX_OUTSIDE', 'PRIM_END_UNOPENED', 'BAD_ALPHA')]
    return not bad and not prim['open'], bad[:3]
def run_chain(start, frames, press=True, track=None):
    calls.clear(); scy.set('combo_next', start); scy.set('hspeed', 0)
    call('gml_Object_o_scyther_Alarm_3', scy.ptr, scy.ptr)
    shown = []
    for _ in range(frames):
        tick(press_next=press)
        nm = sprites.get(int(scy.get('sprite_index')), ('',))[0]
        if not shown or shown[-1] != nm: shown.append(nm)
        if track: track()
        if sc_ctrl.get('is_attacking') == 0: break
    return shown

print('[13] Scyther combo A: Rift Cleave -> Twin Crescent -> Comet Thrust -> Orbit Reap -> Event Horizon Cleave')
scy.set('x', 400); scy.set('image_xscale', 1); foe.set('x', 470)
calls.clear(); scy.set('combo_next', 1); scy.set('hspeed', 0)
call('gml_Object_o_scyther_Alarm_3', scy.ptr, scy.ptr)
tick()
check(scy.get('hspeed') > 5, f'homes in on the opponent 70 px away (hspeed {scy.get("hspeed"):.1f})')
prim['verts'] = 0
shown = ['scyther_a1.png']
for _ in range(200):
    tick()
    nm = sprites.get(int(scy.get('sprite_index')), ('',))[0]
    if shown[-1] != nm: shown.append(nm)
    if sc_ctrl.get('is_attacking') == 0: break
check([s_ for s_ in shown if s_ in COMBO_A] == COMBO_A, f'steps shown: {shown}')
hits = [c for c in calls if c[0] == 'instance_create' and c[1] == 224]
check(len(hits) >= 10, f'hitboxes: {len(hits)} (1 + 2 + 2 + 3 + 2)')
behind = [c for c in hits if c[2] < scy.get('x') - 10]
check(len(behind) >= 1, 'Orbit Reap also hits behind him')
d = drawn_names()
check({'scyther_rift_v.png', 'scyther_rift_e.png', 'scyther_riftbig_v.png'} <= d, 'every cut tears reality (small + giant tears drawn)')
check({'scyther_arc_rise_b.png', 'scyther_arc_rise_f.png', 'scyther_arc_orbit_b.png', 'scyther_arc_cleave_f.png'} <= d, '3D arcs drawn (back + front layers)')
check({'scyther_orbb.png', 'scyther_orbf.png'} <= d and ({'scyther_wpn0.png', 'scyther_wpn1.png'} & d), 'scythe drawn in hand and twirling in its 3D orbit')
check({'scyther_hitfx.png', 'scyther_bh_debris.png', 'scyther_dash.png'} <= d, 'cut flashes, debris with depth, dash lines drawn')
strips = sum(1 for c in calls if c[0] == 'prim_end')
ok, bad = prim_ok()
check(strips >= 40 and prim['verts'] >= 400 and ok, f'3D blade trails + rings: {strips} strips, {prim["verts"]} vertices, balanced {bad}')
check(sc_ctrl.get('is_attacking') == 0 and scy.get('combo_next') == -1, 'finisher ends the combo, is_attacking cleared')
check(not any(c[0] == 'BAD_SPRITE_DRAW' for c in calls), 'no invalid sprite draws')

print('[14] Scyther combo B: Crescent Throw -> Spur Vault -> Phase Step -> Dimensional Stitch -> Singular Rend')
scy.set('x', 400); scy.set('image_xscale', 1); foe.set('x', 470)
sides = set()
def side():
    if scy.get('sprite_index') == next(k for k, v in sprites.items() if v[0] == 'scyther_phase.png'):
        sides.add('right' if scy.get('x') > foe.get('x') else 'left')
shown = run_chain(50, 360, track=side)
check([s_ for s_ in shown if s_ in COMBO_B] == COMBO_B, f'steps shown: {shown}')
d = drawn_names()
check('scyther_disc.png' in d, 'thrown scythe drawn as a spinning disc')
check(sides == {'left', 'right'}, f'Phase Step blinks through him to both sides: {sorted(sides)}')
hits = [c for c in calls if c[0] == 'instance_create' and c[1] == 224]
check(len(hits) >= 14, f'hitboxes: {len(hits)}')
check(sc_ctrl.get('is_attacking') == 0, 'combo B ends cleanly')
ok, bad = prim_ok()
check(ok, f'primitives balanced {bad}')

print('[15] Scyther run attack, crouch and air attacks')
sc_ctrl.set('is_running', 1); scy.set('x', 400); scy.set('image_xscale', 1)
calls.clear(); scy.set('combo_next', 1); scy.set('hspeed', 0)
call('gml_Object_o_scyther_Alarm_3', scy.ptr, scy.ptr)
sc_ctrl.set('is_running', 0)
seen = set(); fast = 0
for _ in range(30):
    tick(press_next=False); seen.add(sprites.get(int(scy.get('sprite_index')), ('',))[0]); fast = max(fast, scy.get('hspeed'))
check('scyther_dashatk.png' in seen and fast >= 10, f'Meteor Dash out of a run (top speed {fast:.0f})')
for k in range(40): tick(press_next=False)
for start, anim in ((10, 'scyther_crouchatk.png'), (60, 'scyther_crouchb.png')):
    calls.clear(); scy.set('combo_next', start); scy.set('image_xscale', 1); scy.set('hspeed', 0)
    call('gml_Object_o_scyther_Alarm_3', scy.ptr, scy.ptr)
    seen = set()
    for _ in range(40):
        tick(press_next=False); seen.add(sprites.get(int(scy.get('sprite_index')), ('',))[0])
    check(anim in seen and any(c[0] == 'instance_create' and c[1] == 224 for c in calls), f'{anim[8:-4]}: shown and hits')
# air A, pressed again -> Sky Splitter dive; air B -> Gravity Drop; landing makes a crater
for start, anims_, press in ((11, ('scyther_airatk.png', 'scyther_airatk2.png'), True), (61, ('scyther_airb.png',), False)):
    calls.clear(); scy.set('combo_next', start); scy.set('image_xscale', 1); sc_ctrl.set('is_onair', 1)
    call('gml_Object_o_scyther_Alarm_3', scy.ptr, scy.ptr)
    seen = set(); landed_at = None
    for f in range(90):
        tick(press_next=press); seen.add(sprites.get(int(scy.get('sprite_index')), ('',))[0])
        if 'scyther_airatk2.png' in seen or start == 61:
            if landed_at is None and scy.get('vspeed') >= 9: landed_at = f + 6
        if landed_at is not None and f >= landed_at: sc_ctrl.set('is_onair', 0)
        if sc_ctrl.get('is_attacking') == 0 and f > 10: break
    crater = sum(1 for c in calls if c[0] == 'instance_create' and c[1] == 224)
    rings = sum(1 for c in calls if c[0] == 'prim_end')
    check(set(anims_) <= seen and crater >= 2 and rings >= 4, f'{"/".join(a_[8:-4] for a_ in anims_)}: shown, dive + crater hits {crater}, rings')
    check(sc_ctrl.get('is_attacking') == 0, f'{start}: ends after landing')
    sc_ctrl.set('is_onair', 0)

print('[16] Scyther skill 1: Event Horizon')
calls.clear(); scy.set('combo_next', 100); scy.set('x', 400); scy.set('image_xscale', 1); foe.set('x', 540)
call('gml_Object_o_scyther_Alarm_3', scy.ptr, scy.ptr)
for _ in range(120):
    tick(press_next=False)
d = drawn_names()
check({'scyther_bh_core.png', 'scyther_bh_diskb.png', 'scyther_bh_diskf.png', 'scyther_bh_pull.png', 'scyther_bh_burst.png'} <= d, 'black hole: core, disk (back/front), pull, collapse drawn')
check(foe.get('x') < 540 - 5, f'opponent dragged toward the hole (x 540 -> {foe.get("x"):.0f})')
hits = [c for c in calls if c[0] == 'instance_create' and c[1] == 224]
check(len(hits) >= 9, f'black hole hitboxes: {len(hits)}')

print('[17] Scyther skill 2: Void Lance')
calls.clear(); scy.set('combo_next', 110)
call('gml_Object_o_scyther_Alarm_3', scy.ptr, scy.ptr)
for _ in range(100):
    tick(press_next=False)
d = drawn_names()
check({'scyther_vl_iris.png', 'scyther_vl_beam.png', 'scyther_vl_tip.png', 'scyther_vl_nova.png', 'scyther_riftbig_v.png'} <= d, 'aperture tear, iris, beam, tip, nova drawn')

print('[18] Scyther special: SINGULARITY (no K.O.) + the void stage')
DECOR = {}
for l in open(GEN_DIR + '/stage_decor.h'):
    m_ = re.match(r'\s+(\d+),\s+/\* (\w+) \*/', l)
    if m_: DECOR[m_.group(2)] = int(m_.group(1))
bk = new_inst(DECOR['o_map_bk']); bk.set('depth', 900000); bk.set('visible', 1)
tree = new_inst(DECOR['o_tile_tree_1']); tree.set('depth', 300); tree.set('visible', 1)
grass_front = new_inst(DECOR['o_tile_grass_1']); grass_front.set('depth', -50); grass_front.set('visible', 1)
floor_ = new_inst(425); floor_.set('bbox_left', 0); floor_.set('bbox_right', 1499); floor_.set('bbox_top', 300); floor_.set('bbox_bottom', 620)
ledge = new_inst(425); ledge.set('bbox_left', 520); ledge.set('bbox_right', 583); ledge.set('bbox_top', 230); ledge.set('bbox_bottom', 261)
calls.clear(); foe.set('x', 520); scy.set('x', 400); sc_ectrl.set('plr_hp', 1900)
first_new = next_id[0]                         # instances created from here on belong to the special
sc_ctrl.set('key_defend', 1); sc_ctrl.set('keyp_special', 1); sc_ctrl.set('plr_energy', 100)
tick()
check(sc_ctrl.get('plr_energy') == 0 and sc_ctrl.get('keyp_special') == 0, 'full bar spent, skill press consumed')
sc_ctrl.set('key_defend', 0)
cut = hero = 0
for _ in range(40 + 180 + 45):
    tick(press_next=False)
    cut += sum(1 for c in calls if spr_name(c) and spr_name(c).startswith('scyther_cut_'))
    hero += sum(1 for c in calls if spr_name(c) == 'scyther_sp.png' and c[4] > 1.5)   # big = the cutscene hero
    calls_keep = [c for c in calls if c[0] in ('instance_create', 'layer_visible', 'stretched')]
    calls.clear(); calls.extend(calls_keep)
check(cut >= 170, f'cutscene drawn on the GUI layer: {cut} frames')
check(hero >= 30, f'act 3: the rooster drawn live at 2x detail over the panels ({hero} frames)')
check(sc_ectrl.get('plr_hp') == 1900, f'no instant K.O. (HP still {sc_ectrl.get("plr_hp")})')
big = [i for i in insts.values() if i.obj == 224 and i.id >= first_new and (i.get('stats_dmg') or 0) >= 500]
check(len(big) == 1 and big[0].get('can_defend') == 0, f'one huge unblockable hit ({big[0].get("stats_dmg") if big else 0:.0f} dmg)')
hidden = sorted(c[1] for c in calls if c[0] == 'layer_visible' and not c[2])
check(hidden == [1, 3], f'background/tile/asset layers behind the fighters hidden, instance layer + front layer kept: {hidden}')
check(bk.get('visible') == 0 and tree.get('visible') == 0, 'stage backdrop (o_map_bk) and scenery behind the fighters hidden')
check(grass_front.get('visible') == 1, 'scenery in front of the fighters left alone')
calls.clear(); tick()
d = drawn_names()
check(any(c[0] == 'stretched' for c in calls) and {'scyther_void_rocks.png'} <= d, 'void sky and floating rocks drawn')
tops = [c for c in calls if c[0] == 'spritepos' and sprites[c[1]][0] == 'scyther_void_top.png']
fronts = [c for c in calls if c[0] == 'part' and sprites[c[1]][0] == 'scyther_void_floor.png']
far_y = sorted({round(c[2][1]) for c in tops})
check(len(tops) >= 8 and len(fronts) >= 3 and far_y == [216, 286], f'perspective stone slabs on both solids: {len(tops)} top quads, {len(fronts)} front strips, far edges at y {far_y}')
q = [c[2] for c in tops if round(c[2][1]) == 286]
near_w = max(c[4] for c in q) - min(c[6] for c in q); far_w = max(c[2] for c in q) - min(c[0] for c in q)
check(far_w < near_w, f'top face narrows toward the far edge (near {near_w:.0f} px, far {far_w:.0f} px)')
check(sc_ctrl.get('can_gethurt') == 1 and any(c[0] == 'scr_plr_step' for c in calls), 'Scyther back to normal afterwards')

print('[19] Scyther special without a full bar does nothing')
sc_ctrl.set('key_defend', 1); sc_ctrl.set('keyp_special', 1); sc_ctrl.set('plr_energy', 40)
calls.clear(); tick()
check(sc_ctrl.get('plr_energy') == 40, 'no energy spent')
sc_ctrl.set('key_defend', 0); sc_ctrl.set('keyp_special', 0)

print('[20] Scyther as the CPU: uses SINGULARITY when its bar is full')
sc_ctrl.set('plr_controller', 2); sc_ctrl.set('keyp_special', 1); sc_ctrl.set('plr_energy', 60)
calls.clear(); tick()
check(sc_ctrl.get('plr_energy') == 60, 'not with 60 energy (normal skill instead)')
scy.set('x', 400); foe.set('x', 470); sc_ctrl.set('keyp_special', 1); sc_ctrl.set('plr_energy', 100)
calls.clear(); tick()
check(sc_ctrl.get('plr_energy') == 0 and sprites.get(int(scy.get('sprite_index')), ('',))[0] == 'scyther_sp.png', 'CPU fired the special without holding shield')
for _ in range(40 + 180 + 45):
    tick(press_next=False); calls.clear()
check(sc_ctrl.get('can_gethurt') == 1, 'and finished it')
sc_ctrl.set('plr_controller', 0); sc_ctrl.set('keyp_special', 0)

print('[21] Scyther destroy')
calls.clear(); call('gml_Object_o_scyther_Destroy_0', scy.ptr, scy.ptr)
check(('parent_destroy',) in calls, 'parent destroy called')

print('\nRESULT:', 'ALL PASSED' if not fails else f'{len(fails)} FAILED')
sys.exit(1 if fails else 0)
