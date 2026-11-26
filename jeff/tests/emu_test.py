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
CHARACTER_OBJS = {685, 686, 687, 523, 420}
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
def st_blend():
    a = args_rv(1, X(4))
    if state.get('blend') != a[0][1]: calls.append(('blend_switch',))
    state['blend'] = a[0][1]; rv_write(X(0), None)
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
    calls.append(('draw', spr, round(S(0), 2), state['blend'], round(S(3), 2), round(S(6), 3)))
def st_draw_self():
    i = by_ptr.get(X(0))
    calls.append(('draw_self', int(i.get('sprite_index')) if i and isinstance(i.get('sprite_index'), (int, float)) else None))
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
    'YYGML_draw_set_alpha': lambda: None, 'YYGML_draw_set_colour': lambda: calls.append(('colour', W(0))),
    'YYGML_draw_rectangle': lambda: calls.append(('rect', round(S(0)), round(S(1)), round(S(2)), round(S(3)))),
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
check(n == 0xe7f, f'count 0xe65 -> {n:#x} (8 Jeff + 9 Scyther + 9 Grey)')
check(tbl == BASE + J['g_funcs'] if 'g_funcs' in J else tbl != state['func_table'], 'table pointer moved to Jeff table')
exp = ['Create_0', 'Step_0', 'Draw_0', 'Draw_64', 'Destroy_0', 'Alarm_0', 'Alarm_2', 'Alarm_3']
for k, e in enumerate(exp):
    nm, fn, gs = struct.unpack('<QQQ', rd(tbl + 24 * (0xe65 + k), 24))
    check(cstr(nm) == 'gml_Object_o_jeff_' + e and fn == BASE + J['gml_Object_o_jeff_' + e], f'entry {0xe65 + k:#x} = {cstr(nm)}')
sexp = ['Create_0', 'Step_0', 'Draw_0', 'Draw_64', 'Draw_72', 'Destroy_0', 'Alarm_0', 'Alarm_2', 'Alarm_3']
for k, e in enumerate(sexp):
    nm, fn, gs = struct.unpack('<QQQ', rd(tbl + 24 * (0xe6d + k), 24))
    check(cstr(nm) == 'gml_Object_o_scyther_' + e and fn == BASE + J['gml_Object_o_scyther_' + e], f'entry {0xe6d + k:#x} = {cstr(nm)}')
gexp = ['Create_0', 'Step_0', 'Draw_0', 'Draw_64', 'Destroy_0', 'Alarm_0', 'Alarm_2', 'Alarm_3', 'Draw_72']
for k, e in enumerate(gexp):
    nm, fn, gs = struct.unpack('<QQQ', rd(tbl + 24 * (0xe76 + k), 24))
    check(cstr(nm) == 'gml_Object_o_grey_' + e and fn == BASE + J['gml_Object_o_grey_' + e], f'entry {0xe76 + k:#x} = {cstr(nm)}')
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
check(len(sprites) == 127 and len(sounds) == 9, f'loaded {len(sprites)} sprites / {len(sounds)} sounds')
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
check([glob.arr.get(('charord', i)) for i in range(1, 7)] == [1005, 1006, 1007, 12, 5, 9], f"charord = {[glob.arr.get(('charord', i)) for i in range(1, 7)]}")
check(glob.get('chars_num') == 6, 'chars_num 3 -> 6')
check(all(glob.arr.get(('char', c)) == 1 for c in (1005, 1006, 1007)), 'global.char[1005..1007] = 1 (owned)')
call('jeff_charsel_ext', menu.ptr)
check(glob.get('chars_num') == 6, 'second rebuild does not add them twice')

print('[3b] online character select (global.game_gm == 2): Jeff, Scyther and Grey stay out')
glob.set('game_gm', 2.0)
glob.slots['game_plrchar'] = alloc(16); uc.mem_write(glob.slots['game_plrchar'], struct.pack('<QII', 0x9abc, 0, ARRAY))
glob.arr[('game_plrchar', 1)] = 685; glob.arr[('game_plrchar', 2)] = 523
for i, v in enumerate([12, 5, 9], 1): glob.arr[('charord', i)] = v
glob.arr.pop(('charord', 4), None); glob.arr.pop(('charord', 5), None); glob.arr.pop(('charord', 6), None); glob.set('chars_num', 3)
call('jeff_charsel_ext', menu.ptr)
check([glob.arr.get(('charord', i)) for i in range(1, 5)] == [12, 5, 9, None] and glob.get('chars_num') == 3,
      f"online list unchanged: {[glob.arr.get(('charord', i)) for i in range(1, 5)]}")
check(glob.arr.get(('game_plrchar', 1)) == -1, 'leftover offline Jeff pick cleared (game_plrchar[1] = -1)')
check(glob.arr.get(('game_plrchar', 2)) == 523, 'other picks untouched')
check(not any(k[0] == 'game_plrchar' and k[1] > 2 for k in glob.arr), 'only slots 1-2 touched')
glob.arr[('game_plrchar', 2)] = 686
call('jeff_charsel_ext', menu.ptr)
check(glob.arr.get(('game_plrchar', 2)) == -1, 'leftover Scyther pick cleared too')
glob.arr[('game_plrchar', 2)] = 687
call('jeff_charsel_ext', menu.ptr)
check(glob.arr.get(('game_plrchar', 2)) == -1, 'leftover Grey pick cleared too')
glob.arr[('game_plrchar', 2)] = 523
glob.set('game_gm', 1.0)
call('jeff_charsel_ext', menu.ptr)
check([glob.arr.get(('charord', i)) for i in (1, 2, 3)] == [1005, 1006, 1007] and glob.get('chars_num') == 6,
      'back offline (game_gm 1): all three listed again')

print('[3c] cheats: local fights only (global.game_gm == 2 turns them all off)')
CHEAT_WORD = BASE + 0x3060000
def cheat_word(): return struct.unpack('<I', uc.mem_read(CHEAT_WORD, 4))[0]
def call_at(va, *args):
    for i, a in enumerate(args): uc.reg_write(UC_ARM64_REG_X0 + i, a)
    uc.reg_write(UC_ARM64_REG_SP, STACK + STACK_SZ - 0x100); uc.reg_write(UC_ARM64_REG_LR, RET_MAGIC)
    uc.reg_write(UC_ARM64_REG_X18, 0)
    uc.emu_start(BASE + va, RET_MAGIC, count=5_000_000)
def branch_at(va):
    w = struct.unpack('<I', uc.mem_read(BASE + va, 4))[0]
    imm = w & 0x3ffffff
    if imm & 0x2000000: imm -= 0x4000000
    return (w & 0x7c000000) == 0x14000000, bool(w >> 31), va + imm * 4
check(branch_at(0x3055e50) == (True, False, J['jeff_cheats_set']), 'nativeSetCheats -> jeff_cheats_set')
check(branch_at(0xaeb6a4) == (True, False, J['jeff_process_hook']), 'RunnerJNILib_Process entry -> jeff_process_hook')
check(branch_at(0x303d640) == (True, True, J['jeff_cheat_button_pause']), "pause menu's Cheats button -> jeff_cheat_button_pause")
check(cheat_word() == 0x1f, 'the Coco default (0x1f) is in place at start')
glob.set('game_gm', 1.0)
call('jeff_frame')
check(cheat_word() == 0x1f, 'offline: the default stays on')
call_at(0x3055e50, 0, 0, 0xfc1)               # the dialog: mana, HP/one-tap, immunity, dash (+ junk bits)
check(cheat_word() == 0x1c1, f'offline: switches apply at once ({cheat_word():#x})')
glob.set('game_gm', 2.0)                       # online: one frame through the real Process entry
regs = {UC_ARM64_REG_X0 + i: 0x1111 * (i + 1) for i in range(8)}
for r, v in regs.items(): uc.reg_write(r, v)
for i in range(8): uc.reg_write(UC_ARM64_REG_Q0 + i, 0x4000000000000000 + i)
uc.reg_write(UC_ARM64_REG_Q10, 0x3ff8000000000000)
sp0 = STACK + STACK_SZ - 0x100
uc.reg_write(UC_ARM64_REG_SP, sp0); uc.reg_write(UC_ARM64_REG_LR, RET_MAGIC); uc.reg_write(UC_ARM64_REG_X18, 0)
uc.emu_start(BASE + 0xaeb6a4, BASE + 0xaeb6a8, count=5_000_000)
check(uc.reg_read(UC_ARM64_REG_PC) == BASE + 0xaeb6a8, 'the hook carries on into Process')
check(all(uc.reg_read(r) == v for r, v in regs.items()) and uc.reg_read(UC_ARM64_REG_LR) == RET_MAGIC
      and all(uc.reg_read(UC_ARM64_REG_Q0 + i) & 0xffffffffffffffff == 0x4000000000000000 + i for i in range(8)),
      "Process's arguments and return address untouched")
check(uc.reg_read(UC_ARM64_REG_SP) == sp0 - 0x80 and struct.unpack('<Q', uc.mem_read(sp0 - 0x80, 8))[0] == 0x3ff8000000000000,
      "Process's first instruction (str d10, [sp, #-0x80]!) done by the hook")
check(cheat_word() == 0, 'online: every cheat off')
call_at(0x3055e50, 0, 0, 0x1ff)
check(cheat_word() == 0, 'online: switching them on in the dialog changes nothing')
calls.clear()
HOOKS[BASE + 0x303c3d0] = lambda: calls.append(('coco_button', X(0), round(S(0), 1), X(3)))
uc.reg_write(UC_ARM64_REG_Q0, struct.unpack('<I', struct.pack('<f', 42.0))[0])
call('jeff_cheat_button_pause', 0xbeef, 0, 0, 3)
check(not any(c[0] == 'coco_button' for c in calls), 'online: the pause menu has no Cheats button')
glob.set('game_gm', 1.0)
call('jeff_frame')
check(cheat_word() == 0x1ff, 'back offline: the switches made online apply')
calls.clear(); uc.reg_write(UC_ARM64_REG_Q0, struct.unpack('<I', struct.pack('<f', 42.0))[0])
call('jeff_cheat_button_pause', 0xbeef, 0, 0, 3)
check(('coco_button', 0xbeef, 42.0, 3) in calls, 'offline: the Cheats button is drawn, its arguments passed through')
glob.set('game_gm', 2.0); call('jeff_frame'); glob.set('game_gm', 1.0)   # leave it as the game would find it
call('jeff_frame')

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

print('[8] special: Bone Breaker (shield + one skill tap; a full bar waits a moment for a double tap)')
enemy.set('x', 520); jeff.set('x', 400); ectrl.set('plr_hp', 1900)
calls.clear()
ctrl.set('key_defend', 1); ctrl.set('keyp_special', 1); ctrl.set('plr_energy', 100)
call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
check(ctrl.get('keyp_special') == 0, 'skill press held back (no normal skill)')
check(ctrl.get('plr_energy') == 100, 'nothing spent while it waits for a second tap')
for _ in range(17): call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
check(ctrl.get('plr_energy') == 0, 'one tap with the shield held: full energy bar spent once the window closed')
calls.clear(); call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
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

def jstep(n=1, draw=False, gui=False, acc=None):
    for _ in range(n):
        if acc is not None: calls.clear()
        call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
        if draw: call('gml_Object_o_jeff_Draw_0', jeff.ptr, jeff.ptr)
        if gui: call('gml_Object_o_jeff_Draw_64', jeff.ptr, jeff.ptr)
        if acc is not None:
            acc |= jdrawn()
            acc |= {('part', sprites[c[1]][0]) for c in calls if c[0] == 'part' and c[1] in sprites}
            acc |= {('self', sprites[c[1]][0]) for c in calls if c[0] == 'draw_self' and c[1] in sprites}
            if any(c[0] == 'BAD_SPRITE_DRAW' for c in calls): acc.add('BAD_SPRITE_DRAW')
def jdrawn(): return {sprites[c[1]][0] for c in calls if c[0] == 'draw' and c[1] in sprites}
def tap(key, down=2, up=3, **kw):
    ctrl.set(key, 1); jstep(down, **kw); ctrl.set(key, 0); jstep(up, **kw)
enemy.set('sprite_index', spr_id['jeff_hurt.png']); enemy.set('image_index', 0)   # (any loaded sprite: the cinematics draw it)

print('[8b] double-tap shield: blue -> red (the black form, sun sword and sun shield)')
ctrl.set('keyp_special', 0); ctrl.set('key_defend', 0); ctrl.set('key_down', 0); jstep(2)
seen = set()
tap('key_defend', draw=True, acc=seen); tap('key_defend', draw=True, acc=seen)
jstep(40, draw=True, acc=seen)
check(sprites.get(jeff.get('spr_stand'), ('',))[0] == 'jeff_rstand.png' and sprites.get(jeff.get('spr_defend'), ('',))[0] == 'jeff_rdefend.png',
      'red stance: spr_stand / spr_defend = rstand / rdefend')
check(('part', 'jeff_d_power.png') in seen, 'the black form rises from his feet (drawn row by row over the old one)')
check(sprites.get(ctrl.get('spr_face'), ('',))[0] == 'jeff_face_d.png', 'HUD portrait: the black form')
want = {'jeff_js_sword.png', 'jeff_js_shield.png', 'jeff_jd_glow.png', 'jeff_js_swirl.png', 'jeff_js_fist.png'}
check(want <= seen, f'sun sword, sun shield, glowing eyes, swirl and the band of fire drawn (missing: {sorted(want - seen)})')
calls.clear(); jeff.set('sprite_index', spr_id['jeff_rstand.png']); jeff.set('image_index', 0)
call('gml_Object_o_jeff_Draw_0', jeff.ptr, jeff.ptr)
ds = [sprites.get(c[1], ('?',))[0] for c in calls if c[0] == 'draw_self']
check(ds == ['jeff_d_rstand.png'], f'the body is drawn with its black copy: {ds}')
check(jeff.get('sprite_index') == spr_id['jeff_rstand.png'], 'sprite_index restored after drawing (game logic sees the normal sprite)')
jeff.set('sprite_index', spr_id['jeff_hurt.png']); calls.clear(); call('gml_Object_o_jeff_Draw_0', jeff.ptr, jeff.ptr)
check([sprites.get(c[1], ('?',))[0] for c in calls if c[0] == 'draw_self'] == ['jeff_d_hurt.png'], 'every animation has its black copy (hurt)')
check('BAD_SPRITE_DRAW' not in seen, 'no invalid sprite draws')

print('[8c] red combos: sun sword (A) and sun shield (B)')
for start, label, want in ((1, 'A', ['jeff_rs1.png', 'jeff_rs2.png', 'jeff_rs3.png', 'jeff_rs4.png', 'jeff_rs5.png']),
                           (50, 'B', ['jeff_rb1.png', 'jeff_rb2.png', 'jeff_rb3.png', 'jeff_rb4.png'])):
    calls.clear(); jeff.set('combo_next', start)
    call('gml_Object_o_jeff_Alarm_3', jeff.ptr, jeff.ptr)
    seq = []
    for _ in range(len(want)):
        cn = [c for c in calls if c[0] == 'scr_combo_normal']
        seq.append(sprites[int(cn[-1][2][0][1])][0] if cn else sprites.get(int(jeff.get('sprite_index')), ('',))[0])
        calls.clear(); jeff.set('combo_nextcombo', 1)
        call('gml_Object_o_jeff_Alarm_2', jeff.ptr, jeff.ptr)
    check(seq == want, f'attack {label}: {seq}')
    check(ctrl.get('is_attacking') == 0 and jeff.get('combo_next') == -1, f'attack {label}: the finisher ends the combo')
calls.clear(); jeff.set('sprite_index', spr_id['jeff_rs1.png']); jeff.set('image_index', 1)
call('gml_Object_o_jeff_Draw_0', jeff.ptr, jeff.ptr)
check({'jeff_js_trail.png', 'jeff_js_glow.png'} <= jdrawn(), 'the blade blazes on the slashing frame')
jeff.set('sprite_index', spr_id['jeff_rstand.png']); jeff.set('image_index', 0)

print('[8d] red skills: Solar Flare (skill 1), Corona (skill 2)')
seen = set(); jeff.set('x', 400); jeff.set('image_xscale', 1); enemy.set('x', 520)
calls.clear(); jeff.set('combo_next', 100); call('gml_Object_o_jeff_Alarm_3', jeff.ptr, jeff.ptr)
hb = []
for _ in range(90):
    calls.clear(); jstep(1, draw=True)
    hb += [c for c in calls if c[0] == 'instance_create' and c[1] == 224]; seen |= jdrawn()
check(len(hb) >= 4 and min(c[2] for c in hb) > 420, f'Solar Flare: the crescent travels forward, {len(hb)} hits')
check({'jeff_js_wave.png', 'jeff_js_aura.png'} <= seen, 'crescent of sun fire + sun aura drawn')
seen = set(); calls.clear(); jeff.set('combo_next', 110); call('gml_Object_o_jeff_Alarm_3', jeff.ptr, jeff.ptr)
hb = []
for _ in range(60):
    calls.clear(); jstep(1, draw=True)
    hb += [c for c in calls if c[0] == 'instance_create' and c[1] == 224]; seen |= jdrawn()
check(len(hb) >= 2 and min(c[2] for c in hb) < 400 < max(c[2] for c in hb), f'Corona: blasts both sides ({len(hb)} hitboxes)')
check({'jeff_js_burst.png', 'jeff_cin_ring.png'} <= seen, 'the flare and its shock rings drawn')

print('[8e] double-tap skill (full bar): RED BLACK HOLE cinematic, K.O.')
ectrl.set('plr_hp', 1900); ctrl.set('plr_energy', 100); enemy.set('x', 520); jstep(20)
ctrl.set('keyp_special', 1); jstep(1); jstep(3); ctrl.set('keyp_special', 1); jstep(1); ctrl.set('keyp_special', 0)
check(ctrl.get('plr_energy') == 0, 'bar spent on the second tap')
check(ctrl.get('can_gethurt') == 0, 'untouchable during the cinematic')
check(ectrl.get('plr_hp') == 1900, 'no K.O. yet')
seen = set(); hp_at = None
for t in range(CIN_RED := 170):
    jstep(1, draw=True, gui=True, acc=seen)
    if t == 120: hp_at = ectrl.get('plr_hp')
check({'jeff_cin_bg.png', 'jeff_rbh_core.png', 'jeff_rbh_disk_b.png', 'jeff_rbh_disk_f.png', 'jeff_d_meteor.png', 'jeff_d_pose.png',
       'jeff_js_burst.png', 'jeff_cin_ring.png', 'jeff_jf_rock.png', 'jeff_hurt.png'} <= seen,
      'cinematic: red sky, black hole (core + disk), the black form, the opponent pulled in, the burst')
check(hp_at == 1900 and ectrl.get('plr_hp') == 0, f'the K.O. lands as the fight comes back (HP {hp_at} -> {ectrl.get("plr_hp")})')
check(ctrl.get('can_gethurt') == 1, 'Jeff vulnerable again')
check('BAD_SPRITE_DRAW' not in seen, 'no invalid sprite draws')
calls.clear(); jstep(1)
check(any(c[0] == 'scr_plr_step' for c in calls), 'framework step resumes afterwards')

print('[8f] double-tap shield + double-tap skill together: HOLLOW PURPLE cinematic, K.O.')
ectrl.set('plr_hp', 1900); ctrl.set('plr_energy', 100); enemy.set('x', 520); jstep(20)
ctrl.set('key_defend', 1); ctrl.set('keyp_special', 1); jstep(1); ctrl.set('keyp_special', 0); jstep(1)
ctrl.set('key_defend', 0); jstep(3)
ctrl.set('key_defend', 1); ctrl.set('keyp_special', 1); jstep(1); ctrl.set('keyp_special', 0); jstep(1); ctrl.set('key_defend', 0)
check(ctrl.get('plr_energy') == 0, 'bar spent')
seen = set()
for t in range(200): jstep(1, draw=True, gui=True, acc=seen)
check({'jeff_cin_bg.png', 'jeff_hp_orb_b.png', 'jeff_hp_orb_r.png', 'jeff_hp_orb_p.png', 'jeff_hp_nuke.png', 'jeff_d_purple.png', 'jeff_d_pose.png'} <= seen,
      'cinematic: blue + red orbs, merged into purple, flicked, the nuclear blast, the pose')
check(ectrl.get('plr_hp') == 0 and ctrl.get('can_gethurt') == 1, 'K.O., Jeff vulnerable again')
check(sprites.get(jeff.get('spr_stand'), ('',))[0] == 'jeff_rstand.png', 'the shield double tap did not also switch his power')
check('BAD_SPRITE_DRAW' not in seen, 'no invalid sprite draws')

print('[8g] one skill tap with a full bar reaches the game after the window; double-tap shield back to blue')
ctrl.set('plr_energy', 100); jstep(20)
ctrl.set('keyp_special', 1); ctrl.set('key_down', 1); jstep(1); ctrl.set('keyp_special', 0); ctrl.set('key_down', 0)
jstep(16)
check(ctrl.get('keyp_special') == 0, 'held back for the tap window')
jstep(1)
check(ctrl.get('keyp_special') == 1 and ctrl.get('key_down') == 1, 'then handed to the game with down still held (skill 2)')
check(ctrl.get('plr_energy') == 100, 'no finisher')
ctrl.set('keyp_special', 0); ctrl.set('key_down', 0)
seen = set()
tap('key_defend', draw=True, acc=seen); tap('key_defend', draw=True, acc=seen); jstep(40, draw=True, acc=seen)
check(sprites.get(jeff.get('spr_stand'), ('',))[0] == 'jeff_stand.png', 'back to blue: spr_stand = stand')
check(sprites.get(ctrl.get('spr_face'), ('',))[0] == 'jeff_face.png', 'HUD portrait back to white Jeff')
check(('part', 'jeff_power.png') in seen and 'jeff_jf_aura.png' in seen, 'the white form rises back, blue fire returns')
calls.clear(); jeff.set('sprite_index', spr_id['jeff_stand.png']); call('gml_Object_o_jeff_Draw_0', jeff.ptr, jeff.ptr)
check([sprites.get(c[1], ('?',))[0] for c in calls if c[0] == 'draw_self'] == ['jeff_stand.png'] and 'jeff_js_sword.png' not in jdrawn(),
      'white body again, no sword')

print('[9] special without energy does nothing')
ctrl.set('key_defend', 1); ctrl.set('keyp_special', 1); ctrl.set('plr_energy', 40); ectrl.set('plr_hp', 1500)
call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
check(ctrl.get('plr_energy') == 40 and ectrl.get('plr_hp') == 1500, 'no energy spent, enemy untouched')

print('[9b] Jeff homes in on the opponent; as the CPU he uses one of his three finishers')
ctrl.set('key_defend', 0); ctrl.set('keyp_special', 0); ctrl.set('plr_energy', 40)
jeff.set('x', 400); jeff.set('image_xscale', 1); jeff.set('hspeed', 0); enemy.set('x', 480); ectrl.set('plr_hp', 1500)
calls.clear(); jeff.set('combo_next', 1)
call('gml_Object_o_jeff_Alarm_3', jeff.ptr, jeff.ptr)
call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
check(5 < jeff.get('hspeed') < 8, f'jab steps in toward the opponent 80 px away, no long dash (hspeed {jeff.get("hspeed"):.1f})')
for _ in range(6): call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
jeff.set('combo_next', -1); call('gml_Object_o_jeff_Alarm_2', jeff.ptr, jeff.ptr)
jeff.set('x', 400); jeff.set('hspeed', 0); enemy.set('x', 560)
calls.clear(); jeff.set('combo_next', 1)
call('gml_Object_o_jeff_Alarm_3', jeff.ptr, jeff.ptr)
call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
check(abs(jeff.get('hspeed')) < 0.5, f'opponent 160 px away: no lunge at all (hspeed {jeff.get("hspeed"):.1f})')
for _ in range(6): call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
jeff.set('combo_next', -1); call('gml_Object_o_jeff_Alarm_2', jeff.ptr, jeff.ptr)
enemy.set('x', 480)
picked = set()
for trial in range(6):
    ectrl.set('plr_hp', 1500)
    ctrl.set('plr_controller', 2); ctrl.set('keyp_special', 1); ctrl.set('plr_energy', 100)
    calls.clear(); call('gml_Object_o_jeff_Step_0', jeff.ptr, jeff.ptr)
    ctrl.set('keyp_special', 0)
    if ctrl.get('plr_energy') != 0:
        check(False, 'CPU Jeff fired a finisher without holding shield'); break
    gui = set()
    for t in range(14 + 156 + 40): jstep(1, gui=True, acc=gui)
    picked.add('purple' if 'jeff_hp_nuke.png' in gui else 'red hole' if 'jeff_rbh_core.png' in gui else 'bone breaker' if 'jeff_cut_a.png' in gui else '?')
    if not (ectrl.get('plr_hp') == 0 and ctrl.get('can_gethurt') == 1):
        check(False, f'CPU finisher {picked} lands on the player'); break
check(len(picked) >= 2 and '?' not in picked, f'the CPU mixes its finishers: {sorted(picked)}')
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
check(len(hits) >= 9, f'hitboxes: {len(hits)} (1 + 2 + 2 + 3 + 1: the cleave hits once, on the slam)')
behind = [c for c in hits if c[2] < scy.get('x') - 10]
check(len(behind) >= 1, 'Orbit Reap also hits behind him')
d = drawn_names()
check({'scyther_rift_v.png', 'scyther_rift_e.png', 'scyther_riftbig_v.png'} <= d, 'every cut tears reality (small + giant tears drawn)')
check({'scyther_arc_rise_b.png', 'scyther_arc_rise_f.png', 'scyther_arc_orbit_b.png', 'scyther_arc_cleave_f.png'} <= d, '3D arcs drawn (back + front layers)')
check({'scyther_orbb.png', 'scyther_orbf.png'} <= d and ({'scyther_wpn0.png', 'scyther_wpn1.png'} & d), 'scythe drawn in hand and twirling in its 3D orbit')
check({'scyther_hitfx.png', 'scyther_bh_debris.png', 'scyther_dash.png'} <= d, 'cut flashes, debris with depth, dash lines drawn')
smear = sum(1 for c in calls if c[0] == 'draw' and c[1] in sprites and sprites[c[1]][0] == 'scyther_smear.png')
noprim = not any(c[0] in ('prim_end', 'prim_begin') for c in calls)
check(smear >= 40 and noprim, f'3D blade trails + rings drawn as sprite quads: {smear} smear segments, no draw_primitive ({noprim})')
check(sc_ctrl.get('is_attacking') == 0 and scy.get('combo_next') == -1, 'finisher ends the combo, is_attacking cleared')
check(not any(c[0] == 'BAD_SPRITE_DRAW' for c in calls), 'no invalid sprite draws')

print('[13b] Event Horizon Cleave: one knockdown on the slam, nothing fires as the tear closes')
scy.set('x', 400); scy.set('image_xscale', 1); scy.set('y', 300); scy.set('vspeed', 0); foe.set('x', 470)
for _ in range(30): tick(press_next=False)
calls.clear(); scy.set('combo_next', 5); scy.set('hspeed', 0)
call('gml_Object_o_scyther_Alarm_3', scy.ptr, scy.ptr)
events = []
for t in range(1, 60):
    n0 = len(calls)
    tick(press_next=False)
    for c in calls[n0:]:
        if c[0] == 'instance_create' and c[1] == 224: events.append((t, 'hit'))
        if c[0] == 'play': events.append((t, 'sound'))
    if sc_ctrl.get('is_attacking') == 0: break
hit_t = [t for t, k in events if k == 'hit']
check(len(hit_t) == 1 and 18 <= hit_t[0] <= 24, f'one hit, on the slam (frames {hit_t})')
check(not [t for t, k in events if t > 30], f'nothing fires after the slam settles (events {[e for e in events if e[0] > 30]})')

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
    rings = sum(1 for c in calls if c[0] == 'draw' and c[1] in sprites and sprites[c[1]][0] == 'scyther_smear.png')
    check(set(anims_) <= seen and crater >= 2 and rings >= 4, f'{"/".join(a_[8:-4] for a_ in anims_)}: shown, dive + crater hits {crater}, ring segments {rings}')
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

# ============================== Grey ==========================================================
print('[22] Grey: scr_menu_get_char(1007)')
calls.clear(); rv_write(argrv, 1007.0)
nspr = len(sprites)
call('jeff_get_char', menu.ptr, menu.ptr, ret, 1, argv)
check(menu.get('char_name') == 'Grey' and menu.get('char_obj') == 687, 'name / object 687')
check(sprites.get(menu.get('char_face'), ('',))[0] == 'grey_face.png', 'portrait card = grey_face.png')
ngr = len(sprites) - nspr
check(ngr == 60 and sum(1 for v in sounds.values() if str(v).startswith('grey_')) == 4, f'loaded {ngr} Grey sprites, 4 sounds')
check(any(c[0] == 'object_set_sprite' and c[1] == 687 for c in calls), 'object_set_sprite(o_grey, preview)')

print('[23] Grey: create + alarm0')
for other in (foe, enemy):
    other.set('x', -3000)                                    # earlier opponents out of the way
gr_ctrl = new_inst(431); gr_ctrl.set('plr_team', 1); gr_ctrl.set('plr_dmg', 47); gr_ctrl.set('plr_energy', 100); gr_ctrl.set('plr_maxenergy', 100)
for k in ('key_defend', 'keyp_special', 'is_hurt', 'is_fallen', 'is_dead', 'is_onair', 'is_charging', 'is_running', 'plr_controller'): gr_ctrl.set(k, 0)
grey = new_inst(687); grey.set('x', 400); grey.set('y', 300); grey.set('image_xscale', 1); grey.set('image_alpha', 1)
calls.clear()
call('gml_Object_o_grey_Create_0', grey.ptr, grey.ptr)
check(('parent_create',) in calls, 'event_inherited (parent create) called')
check(grey.get('stats_hp') == 2200 and grey.get('char_name') == 'Grey', 'stats/name set')
check(sprites.get(grey.get('spr_stand'), ('',))[0] == 'grey_m_stand.png' and sprites.get(grey.get('spr_run'), ('',))[0] == 'grey_m_run.png',
      'framework sprites are the invisible state markers')
grey.set('parent', gr_ctrl.id)
call('gml_Object_o_grey_Alarm_0', grey.ptr, grey.ptr)
check(sprites.get(gr_ctrl.get('spr_face'), ('',))[0] == 'grey_face.png', 'controller spr_face = grey_face')
g_ectrl = new_inst(431); g_ectrl.set('plr_team', 2); g_ectrl.set('plr_hp', 1900); g_ectrl.set('is_dead', 0)
gfoe = new_inst(523); gfoe.set('x', 460); gfoe.set('y', 300); gfoe.set('parent', g_ectrl.id)

def gtick(press_next=True, draw=True, gui=False, physics=True):
    a2 = grey.arr.get(('alarm', 2), -1)
    if a2 is not None and a2 > 0:
        a2 -= 1; grey.arr[('alarm', 2)] = a2
        if a2 == 0:
            grey.arr[('alarm', 2)] = -1
            if press_next: grey.set('combo_nextcombo', 1)
            call('gml_Object_o_grey_Alarm_2', grey.ptr, grey.ptr)
    call('gml_Object_o_grey_Step_0', grey.ptr, grey.ptr)
    if physics:
        x = grey.get('x') + (grey.get('hspeed') or 0); y = grey.get('y') + (grey.get('vspeed') or 0); vs = grey.get('vspeed') or 0
        if y < 300: vs += 0.45; gr_ctrl.set('is_onair', 1)
        else: y = 300; vs = 0; gr_ctrl.set('is_onair', 0)
        grey.set('x', x); grey.set('y', y); grey.set('vspeed', vs)
    if draw: call('gml_Object_o_grey_Draw_0', grey.ptr, grey.ptr)
    if gui: call('gml_Object_o_grey_Draw_64', grey.ptr, grey.ptr)

g_strips = []                                            # vertex counts of the primitive strips drawn
GBAD = ('BAD_SPRITE_DRAW', 'PRIM_NESTED', 'VERTEX_OUTSIDE', 'PRIM_END_UNOPENED', 'BAD_ALPHA')
def grun(start, frames=400, press=True, setup=None):
    seen, hits, xs = set(), [], []
    calls.clear(); grey.set('combo_next', start); grey.set('hspeed', 0); g_strips.clear()
    if setup: setup()
    call('gml_Object_o_grey_Alarm_3', grey.ptr, grey.ptr)
    for _ in range(frames):
        n0 = len(calls)
        gtick(press_next=press)
        new = calls[n0:]
        seen |= {sprites[c[1]][0] for c in new if c[0] == 'draw' and c[1] in sprites}
        hits += [c for c in new if c[0] == 'instance_create' and c[1] == 224]
        g_strips.extend(c[1] for c in new if c[0] == 'prim_end')
        if any(c[0] in GBAD for c in new): seen.add('BAD_SPRITE_DRAW')
        xs.append((grey.get('x'), grey.get('image_xscale')))
        if gr_ctrl.get('is_attacking') == 0: break
        calls.clear()
    for _ in range(12): gtick(press_next=False)          # clones / projectiles finish
    return seen, hits, xs

def head_alpha():                                        # Grey's head fill: the disc at G_HEAD_R / 16, normal blend
    a = [c[5] for c in calls if c[0] == 'draw' and c[1] in sprites and sprites[c[1]][0] == 'grey_shape.png'
         and c[2] == 1 and c[3] == 0 and abs(c[4] - 0.38) < 0.006]
    return max(a) if a else None

print('[23b] Grey materialises at the start of the match')
calls.clear(); gtick(press_next=False); a0 = head_alpha()
for _ in range(44): calls.clear(); gtick(press_next=False)
a1 = head_alpha()
check(a0 is not None and a0 < 0.2 and a1 is not None and a1 > 0.99, f'fades in out of pixels: head alpha {a0} -> {a1}')

print('[24] Grey combo A: jab-cross, clone cut, frost rise, fireball flip, fatal glitch')
grey.set('x', 400); grey.set('image_xscale', 1); gfoe.set('x', 455)
seen, hits, xs = grun(1)
check(len(hits) >= 14, f'hitboxes: {len(hits)}')
check({'grey_shape.png', 'grey_sword.png', 'grey_spear.png', 'grey_spike.png', 'grey_fire.png', 'grey_spawn.png',
       'grey_shatter.png', 'grey_arc.png'} <= seen, f'stickman, glitch sword, spear, ice spikes, fireballs, clones, shatter, swing drawn (missing {sorted({"grey_shape.png", "grey_sword.png", "grey_spear.png", "grey_spike.png", "grey_fire.png", "grey_spawn.png", "grey_shatter.png", "grey_arc.png"} - seen)})')
check(any(x > 455 and xsc < 0 for x, xsc in xs), 'Fatal Glitch: teleported behind him and turned round')
check('BAD_SPRITE_DRAW' not in seen, 'no invalid sprite draws, primitives well formed')
check(gr_ctrl.get('is_attacking') == 0 and grey.get('combo_next') == -1, 'the finisher ends the combo')
check({'grey_star.png', 'grey_smoke.png'} <= seen, f'impact stars and fireball smoke drawn (missing {sorted({"grey_star.png", "grey_smoke.png"} - seen)})')
check(len(g_strips) == 0 and 'grey_shape.png' in seen,
      f'ribbon trails / lightning drawn as sprite quads, no draw_primitive ({len(g_strips)} strips)')

print('[25] Grey combo B: roundhouse, twin clone kick, ice lance shatter, meteor axe')
grey.set('x', 400); grey.set('image_xscale', 1); gfoe.set('x', 455)
seen, hits, xs = grun(50)
check(len(hits) >= 8, f'hitboxes: {len(hits)} (the ice shards only hit what they touch)')
check({'grey_spike.png', 'grey_shard.png', 'grey_fireburst.png', 'grey_ring.png', 'grey_spawn.png'} <= seen,
      f'ice lance, shards, fire burst, shock ring, clone drawn (missing {sorted({"grey_spike.png", "grey_shard.png", "grey_fireburst.png", "grey_ring.png", "grey_spawn.png"} - seen)})')
check('BAD_SPRITE_DRAW' not in seen, 'no invalid sprite draws')

print('[26] Grey crouch, air and run attacks')
for start, label, setup in ((10, 'Glitch Sweep Blade', None), (60, 'Frost Slide', None),
                            (11, 'Aerial Glitch Spin', lambda: (grey.set('y', 230), grey.set('vspeed', -3), gr_ctrl.set('is_onair', 1))),
                            (61, 'Phantom Dive', lambda: (grey.set('y', 230), grey.set('vspeed', -3), gr_ctrl.set('is_onair', 1))),
                            (1, 'Glitch Dash (running)', lambda: gr_ctrl.set('is_running', 1))):
    grey.set('x', 380); grey.set('image_xscale', 1); gfoe.set('x', 450)
    seen, hits, xs = grun(start, press=False, setup=setup)
    gr_ctrl.set('is_running', 0)
    check(len(hits) >= 1 and 'BAD_SPRITE_DRAW' not in seen, f'{label}: {len(hits)} hits')
    for _ in range(30): gtick(press_next=False)

print('[26b] Grey: impacts and hit-stop only on blows that land')
def sweep(foe_x):
    grey.set('x', 380); grey.set('image_xscale', 1); gfoe.set('x', foe_x)
    seen, hits, xs = grun(10, press=False)
    for _ in range(30): gtick(press_next=False)
    return len(xs), seen, len(hits)
n_hit, seen_hit, h1 = sweep(450)
n_miss, seen_miss, h2 = sweep(1400)
check(h1 == h2 >= 1, f'same hitboxes either way ({h1} / {h2})')
check('grey_star.png' in seen_hit and 'grey_star.png' not in seen_miss, 'impact star when it lands, none on a whiff')
check(n_hit > n_miss, f'hit-stop only when it lands: {n_hit} frames vs {n_miss} on a whiff')
gfoe.set('x', 450)

print('[26c] Grey air chain: glitch spin -> clone uplink -> data crash, landing with a quake')
grey.set('x', 380); grey.set('image_xscale', 1); gfoe.set('x', 430)
def high_jump(): grey.set('y', 170); grey.set('vspeed', -2); gr_ctrl.set('is_onair', 1)
seen, hits, xs = grun(11, frames=240, setup=high_jump)
check(len(hits) >= 6, f'all three air moves, the uplink clone and the landing hit: {len(hits)} hitboxes')
check({'grey_bolt.png', 'grey_spear.png', 'grey_ring.png', 'grey_shatter.png'} <= seen,
      f'uplink lightning, the spear dive, the landing rings and shatter drawn (missing {sorted({"grey_bolt.png", "grey_spear.png", "grey_ring.png", "grey_shatter.png"} - seen)})')
check('BAD_SPRITE_DRAW' not in seen and gr_ctrl.get('is_attacking') == 0, 'clean, and the attack is over after landing')
for _ in range(30): gtick(press_next=False)
grey.set('x', 380); gfoe.set('x', 430)
def low_jump(): grey.set('y', 292); grey.set('vspeed', 0); gr_ctrl.set('is_onair', 1)
seen, hits, xs = grun(11, frames=120, setup=low_jump)
check('grey_bolt.png' not in seen and gr_ctrl.get('is_attacking') == 0, 'landed before the spin ended: no chain on the ground')
for _ in range(30): gtick(press_next=False)

print('[27] Grey skills: Glitch Axe (launcher), Element Overload')
grey.set('x', 380); grey.set('image_xscale', 1); gfoe.set('x', 430)
first_new = next_id[0]
seen, hits, xs = grun(100, press=False)
for _ in range(30): gtick(press_next=False); seen |= {sprites[c[1]][0] for c in calls if c[0] == 'draw' and c[1] in sprites}; hits += [c for c in calls if c[0] == 'instance_create' and c[1] == 224]; calls.clear()
axe_hb = [i for i in insts.values() if i.obj == 224 and i.id >= first_new]
check(len(hits) == 1 and len(axe_hb) == 1, f'Glitch Axe: one hit ({len(hits)})')
check(axe_hb and axe_hb[0].get('vforce') <= -10 and axe_hb[0].get('can_knock') == 1,
      f'it launches him high and knocks him down (vforce {axe_hb[0].get("vforce") if axe_hb else None})')
check({'grey_axe.png', 'grey_spawn.png', 'grey_arc.png', 'grey_ring.png'} <= seen,
      f'the axe, its materialising, the swing arc and the ring drawn (missing {sorted({"grey_axe.png", "grey_spawn.png", "grey_arc.png", "grey_ring.png"} - seen)})')
check('BAD_SPRITE_DRAW' not in seen and gr_ctrl.get('is_attacking') == 0, 'clean, and the move is over')
grey.set('x', 380); gfoe.set('x', 470)
seen, hits, xs = grun(110, press=False)
for _ in range(40): gtick(press_next=False); seen |= {sprites[c[1]][0] for c in calls if c[0] == 'draw' and c[1] in sprites}; hits += [c for c in calls if c[0] == 'instance_create' and c[1] == 224]; calls.clear()
check(len(hits) >= 12, f'Element Overload: {len(hits)} hits')
check({'grey_spike.png', 'grey_pillar.png', 'grey_spear.png'} <= seen, 'ice prison, fire pillar, spear rain drawn')
check(all(abs(c[2] - 470) < 60 for c in hits), 'all of it lands on the opponent')

print('[28] Grey special: MOONFALL + the lava world')
g_bk = new_inst(DECOR['o_map_bk']); g_bk.set('depth', 900000); g_bk.set('visible', 1)
g_tree = new_inst(DECOR['o_tile_tree_1']); g_tree.set('depth', 300); g_tree.set('visible', 1)
grey.set('x', 400); grey.set('image_xscale', 1); gfoe.set('x', 470); g_ectrl.set('plr_hp', 1900)
for _ in range(20): gtick(press_next=False)
calls.clear()
gr_ctrl.set('key_defend', 1); gr_ctrl.set('keyp_special', 1); gr_ctrl.set('plr_energy', 100)
gtick(gui=True)
gr_ctrl.set('key_defend', 0); gr_ctrl.set('keyp_special', 0)
check(gr_ctrl.get('plr_energy') == 0 and gr_ctrl.get('can_gethurt') == 0, 'bar spent, untouchable')
check(grey.get('depth') == -15000, 'drawn over the HUD')
seen, hits, bad, maxd, maxb, held, hit_t = set(), [], False, 0, 0, True, -1
by_phase = {}
for t in range(1, 521):                                    # MOONFALL is 500 frames
    calls.clear()
    call('gml_Object_o_grey_Draw_72', grey.ptr, grey.ptr)
    gtick(gui=True)
    names = {sprites[c[1]][0] for c in calls if c[0] in ('draw', 'stretched', 'part') and c[1] in sprites}
    seen |= names
    for ph, (a_, b_) in (('ground', (40, 90)), ('space', (120, 236)), ('impact', (242, 370)), ('lava', (420, 500))):
        if a_ <= t < b_: by_phase.setdefault(ph, set()).update(names)
    new_hits = [c for c in calls if c[0] == 'instance_create' and c[1] == 224]
    if new_hits and hit_t < 0: hit_t = t
    hits += new_hits
    bad |= any(c[0] in GBAD for c in calls)
    maxd = max(maxd, sum(1 for c in calls if c[0] in ('draw', 'stretched', 'part', 'prim_end')))
    maxb = max(maxb, sum(1 for c in calls if c[0] == 'blend_switch'))
    if t < 410 and abs(gfoe.get('x') - 470) > 1: held = False
    calls_keep = [c for c in calls if c[0] == 'layer_visible']
    calls.clear(); calls.extend(calls_keep)
check(len(hits) == 1 and 410 <= hit_t <= 416, f'one blow, when it lands back on the ground: {len(hits)} hits at frame {hit_t}')
check({'grey_moon_big.png'} <= by_phase.get('ground', set()), 'the Moon appears in the sky over the battlefield')
check({'grey_earth.png', 'grey_moon_big.png', 'grey_stars.png'} <= by_phase.get('space', set()), f'space: Earth, Moon, stars ({sorted(by_phase.get("space", set()))})')
check({'grey_earth_top.png'} <= seen, 'the horizon crop as the camera clears the atmosphere')
check({'grey_earth_melt.png', 'grey_plume.png', 'grey_glow.png', 'grey_rocks.png'} <= by_phase.get('impact', set()),
      f'impact: melt front, plume, glow, Moon debris ({sorted(by_phase.get("impact", set()))})')
check({'grey_lava_sky.png', 'grey_lava_far.png', 'grey_lava_mid.png', 'grey_lava_crust.png'} <= by_phase.get('lava', set()),
      f'the lava world drawn afterwards ({sorted(by_phase.get("lava", set()))})')
check(not bad, 'no invalid draws or primitives during the special')
check(maxd < 1400, f'draw calls per frame stay bounded (max {maxd})')
check(maxb <= 24, f'blend-mode switches per frame stay few, so draws batch (max {maxb})')
check(held, 'the opponent is held in place until the blow')
check(g_bk.get('visible') == 0 and g_tree.get('visible') == 0, 'the stage backdrop and the scenery behind the fighters hidden')
check(gr_ctrl.get('can_gethurt') == 1 and grey.get('depth') != -15000, 'vulnerable again, depth restored')
calls.clear(); gtick()
check(any(c[0] == 'scr_plr_step' for c in calls), 'framework step resumes afterwards')
calls.clear(); call('gml_Object_o_grey_Draw_72', grey.ptr, grey.ptr)
check({'grey_lava_sky.png', 'grey_lava_crust.png'} <= {sprites[c[1]][0] for c in calls if c[0] in ('draw', 'stretched', 'part') and c[1] in sprites},
      'the lava world stays for the rest of the match')

print('[28b] Grey: a second MOONFALL in the same match starts clean, and lasts 500 frames')
grey.set('x', 400); grey.set('image_xscale', 1); gfoe.set('x', 470); g_ectrl.set('plr_hp', 1900)
for _ in range(10): gtick(press_next=False)
gr_ctrl.set('key_defend', 1); gr_ctrl.set('keyp_special', 1); gr_ctrl.set('plr_energy', 100)
calls.clear(); gtick(gui=True)
gr_ctrl.set('key_defend', 0); gr_ctrl.set('keyp_special', 0)
early_rocks, end_t = 0, -1
for t in range(1, 521):
    calls.clear(); gtick(gui=True)
    if 120 <= t < 150:                                   # space, before the Moon sheds anything this time
        early_rocks += sum(1 for c in calls if c[0] == 'draw' and c[1] in sprites and sprites[c[1]][0] == 'grey_rocks.png')
    if end_t < 0 and gr_ctrl.get('can_gethurt') == 1: end_t = t
check(early_rocks == 0, f'no frozen debris left over from the first MOONFALL ({early_rocks} rock draws)')
check(499 <= end_t <= 501, f'the special lasts 500 frames at 60 fps (over at frame {end_t})')
calls.clear()

print('[28c] Grey bow stance (double-tap shield) + INFERNO ARROW (shield + skill in the stance)')
def drawn_now(): return {sprites[c[1]][0] for c in calls if c[0] in ('draw', 'stretched', 'part') and c[1] in sprites}
grey.set('x', 400); grey.set('image_xscale', 1); gfoe.set('x', 470); g_ectrl.set('plr_hp', 1900)
for _ in range(30): gtick(press_next=False)
def shield_tap(): gr_ctrl.set('key_defend', 1); gtick(press_next=False); gr_ctrl.set('key_defend', 0); gtick(press_next=False)
shield_tap()
for _ in range(30): gtick(press_next=False)
calls.clear(); gtick(press_next=False)
check('grey_bow.png' not in drawn_now(), 'one shield press: no bow')
shield_tap(); shield_tap()
for _ in range(12): gtick(press_next=False)
calls.clear(); gtick(press_next=False)
check('grey_bow.png' in drawn_now(), 'double-tap shield: the bow in his hand')
calls.clear()
gr_ctrl.set('key_defend', 1); gr_ctrl.set('keyp_special', 1); gr_ctrl.set('plr_energy', 100)
gtick(gui=True)
gr_ctrl.set('key_defend', 0); gr_ctrl.set('keyp_special', 0)
check(gr_ctrl.get('plr_energy') == 0 and gr_ctrl.get('can_gethurt') == 0, 'bar spent, untouchable')
first_new = next_id[0]
seen, ph, hits, hit_t, bad, maxd, maxb, end_t = set(), {}, [], -1, False, 0, 0, -1
PH = (('closeup', (40, 120)), ('flight', (136, 176)), ('flash', (178, 186)), ('top', (188, 236)), ('spike', (238, 248)),
      ('cloud', (250, 316)), ('after', (320, 378)))
for t in range(1, 401):
    calls.clear()
    call('gml_Object_o_grey_Draw_72', grey.ptr, grey.ptr)
    gtick(gui=True)
    names = drawn_now(); seen |= names
    for k_, (a_, b_) in PH:
        if a_ <= t < b_: ph.setdefault(k_, set()).update(names)
    nh = [c for c in calls if c[0] == 'instance_create' and c[1] == 224]
    if nh and hit_t < 0: hit_t = t
    hits += nh
    bad |= any(c[0] in GBAD for c in calls)
    maxd = max(maxd, sum(1 for c in calls if c[0] in ('draw', 'stretched', 'part', 'prim_end')))
    maxb = max(maxb, sum(1 for c in calls if c[0] == 'blend_switch'))
    if end_t < 0 and gr_ctrl.get('can_gethurt') == 1: end_t = t
hb = [i for i in insts.values() if i.obj == 224 and i.id >= first_new]
check(len(hits) == 1 and 316 <= hit_t <= 320, f'one blow, back on the ground: {len(hits)} hits at frame {hit_t}')
check(hb and hb[0].get('can_defend') == 0 and hb[0].get('can_knock') == 1 and hb[0].get('vforce') <= -10,
      'unblockable, launches and knocks down')
def has(ph_, need): return set(need) <= ph.get(ph_, set())
check(has('closeup', ['grey_ia_sky.png', 'grey_firebow.png', 'grey_fire.png', 'grey_shape.png']), f'close-up: the sky, the bow of fire, the arrow, Grey ({sorted(ph.get("closeup", []))})')
check(has('flight', ['grey_firetrail.png', 'grey_speedring.png', 'grey_ia_hills.png']), f'flight: the fire streak, speed rings, the plain ({sorted(ph.get("flight", []))})')
check(has('top', ['grey_ia_top.png', 'grey_ia_crater.png', 'grey_rocks.png']), f'from above: the ground, the crater, rocks ({sorted(ph.get("top", []))})')
check(has('spike', ['grey_ia_splash.png']), 'the white-out spike')
check(has('cloud', ['grey_ia_cloud.png', 'grey_rocks.png', 'grey_ring.png']), f'the mushroom cloud, rocks, the ground ring ({sorted(ph.get("cloud", []))})')
check(has('after', ['grey_ia_cloud.png', 'grey_bow.png']), 'afterwards: the cloud behind, the bow still in his hand')
check('grey_earth.png' not in seen, 'not MOONFALL')
check(not bad, 'no invalid draws or primitives')
check(maxd < 1400 and maxb <= 24, f'draws / blend switches per frame bounded (max {maxd} / {maxb})')
check(379 <= end_t <= 381, f'the cinematic lasts 380 frames (over at frame {end_t})')
calls.clear()
shield_tap(); shield_tap()
for _ in range(12): gtick(press_next=False)
calls.clear(); gtick(press_next=False)
check('grey_bow.png' not in drawn_now(), 'double-tap shield again: the bow is put away')
gr_ctrl.set('key_defend', 1); gr_ctrl.set('keyp_special', 1); gr_ctrl.set('plr_energy', 100)
gtick(gui=True); gr_ctrl.set('key_defend', 0); gr_ctrl.set('keyp_special', 0)
seen = set()
for t in range(1, 521):
    calls.clear(); gtick(gui=True); seen |= drawn_now()
check('grey_earth.png' in seen and 'grey_firebow.png' not in seen, 'out of the stance: MOONFALL again')
calls.clear()

print('[29] Grey as the CPU: MOONFALL with a full bar')
gr_ctrl.set('plr_controller', 2); gr_ctrl.set('keyp_special', 1); gr_ctrl.set('plr_energy', 100)
grey.set('x', 400); gfoe.set('x', 470)
calls.clear(); gtick()
gr_ctrl.set('keyp_special', 0)
check(gr_ctrl.get('plr_energy') == 0, 'CPU fired it without holding shield')
for _ in range(520): gtick(); calls.clear()
check(gr_ctrl.get('can_gethurt') == 1, 'and finished it')
gr_ctrl.set('plr_controller', 0)

print('[30] Grey moves about: idle, walk, run, jump (front flip), guard, hurt, knocked down')
states = []
def draws_now():
    return sum(1 for c in calls if c[0] == 'draw' and c[1] in sprites and sprites[c[1]][0] == 'grey_shape.png')
for label, setup in (('idle', lambda: None), ('walk', lambda: (grey.set('hspeed', 3.0), grey.set('sprite_index', grey.get('spr_walk')))),
                     ('run', lambda: (grey.set('hspeed', 8.0), gr_ctrl.set('is_running', 1))),
                     ('jump', lambda: (grey.set('y', 299), grey.set('vspeed', -7), gr_ctrl.set('is_onair', 1))),
                     ('guard', lambda: gr_ctrl.set('key_defend', 1)), ('hurt', lambda: gr_ctrl.set('is_hurt', 1)),
                     ('fallen', lambda: gr_ctrl.set('is_fallen', 1))):
    setup()
    calls.clear(); gtick(physics=label == 'jump')
    n = draws_now()
    states.append((label, n))
    for _ in range(8): calls.clear(); gtick(physics=label == 'jump')
    for k in ('is_running', 'key_defend', 'is_hurt', 'is_fallen'): gr_ctrl.set(k, 0)
    grey.set('hspeed', 0); grey.set('sprite_index', grey.get('spr_stand')); grey.set('y', 300); grey.set('vspeed', 0); gr_ctrl.set('is_onair', 0)
check(all(n >= 40 for _, n in states), f'the stickman is drawn bone by bone in every state: {states}')
calls.clear(); gr_ctrl.set('key_defend', 1); gtick(); gtick()
check('grey_hex.png' in {sprites[c[1]][0] for c in calls if c[0] == 'draw' and c[1] in sprites}, 'guard shows the glitch barrier')
gr_ctrl.set('key_defend', 0)

print('[30b] Grey glitches when hit, crashes when knocked down, is deleted when K.O.')
def drawn_names_g(): return {sprites[c[1]][0] for c in calls if c[0] == 'draw' and c[1] in sprites}
calls.clear(); gr_ctrl.set('is_hurt', 1); gtick(); gtick()
check('grey_glitch.png' in drawn_names_g(), 'hit: a glitch burst')
gr_ctrl.set('is_hurt', 0); gr_ctrl.set('is_fallen', 1)
calls.clear(); gtick(); gtick()
check({'grey_glitch.png', 'grey_ring.png', 'grey_smoke.png'} <= drawn_names_g(), 'knocked down: glitch, a ring, dust')
g_ectrl.set('is_dead', 0); gr_ctrl.set('is_dead', 1)
for _ in range(100): calls.clear(); gtick()
ad = head_alpha()
check(ad is not None and 0.3 < ad < 0.4, f'K.O.: dissolves down to a faint ghost (head alpha {ad})')
gr_ctrl.set('is_dead', 0); gr_ctrl.set('is_fallen', 0)
for _ in range(3): calls.clear(); gtick()
check(head_alpha() is not None and head_alpha() > 0.99, 'back to normal when the round restarts')

print('[30c] Grey at rest: now and then the glitch sword appears, spins and is dismissed')
grey.set('x', 400); grey.set('y', 300); grey.set('vspeed', 0); grey.set('hspeed', 0); gr_ctrl.set('is_onair', 0)
seen, hb = set(), 0
for _ in range(430):
    calls.clear(); gtick(press_next=False)
    seen |= drawn_names_g(); hb += sum(1 for c in calls if c[0] == 'instance_create' and c[1] == 224)
check({'grey_sword.png', 'grey_shatter.png'} <= seen and hb == 0, f'idle flourish drawn, no hitboxes ({hb})')

print('[30d] Grey wins: once every opponent is down he twirls the blade, a clone joins him, the blade shatters')
ctrls = [i for i in insts.values() if i.obj == 431 and i is not gr_ctrl and i.get('plr_team') not in (None, 1)]
saved = [(i, i.get('is_dead')) for i in ctrls]
for i in ctrls: i.set('is_dead', 1)
seen, hb = set(), 0
for _ in range(170):
    calls.clear(); gtick(press_next=False)
    seen |= drawn_names_g(); hb += sum(1 for c in calls if c[0] == 'instance_create' and c[1] == 224)
check({'grey_sword.png', 'grey_spawn.png', 'grey_shatter.png'} <= seen and hb == 0,
      f'victory: blade, clone, shatter; no hitboxes (missing {sorted({"grey_sword.png", "grey_spawn.png", "grey_shatter.png"} - seen)})')
for i, v in saved: i.set('is_dead', v)
for _ in range(10): calls.clear(); gtick(press_next=False)
check('grey_sword.png' not in drawn_names_g(), 'a new round (opponent back up): the victory ends')

print('[31] Grey destroy')
calls.clear(); call('gml_Object_o_grey_Destroy_0', grey.ptr, grey.ptr)
check(('parent_destroy',) in calls, 'parent destroy called')

print('\nRESULT:', 'ALL PASSED' if not fails else f'{len(fails)} FAILED')
sys.exit(1 if fails else 0)
