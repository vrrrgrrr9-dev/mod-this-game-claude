"""Host-side stand-in for tests/emu_test.py (Grey only): runs grey.c compiled for x86-64 against the same
mocked engine (ported stub for stub from emu_test.py), so Grey's logic and draw calls can be checked
where Unicorn isn't available. It does not test the ARM build itself: compile_check.sh covers that it
builds, this covers what the code does."""
import ctypes as C, json, os, struct, sys

LIB, SHIM_JSON = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), 'shim.json')
lib = C.CDLL(LIB)
meta = json.load(open(SHIM_JSON))
VAR_ID = {v: k for k, v in meta['vars'].items()}            # id -> name

class RV(C.Structure):
    _fields_ = [('u', C.c_uint64), ('flags', C.c_uint32), ('kind', C.c_uint32)]
REAL, STRING, ARRAY, UNDEF, OBJECT, BOOL, INT32, INT64 = 0, 1, 2, 5, 6, 13, 7, 10
keep = []                                                    # keep ctypes objects alive
strings = {}

def f2u(d): return struct.unpack('<Q', struct.pack('<d', float(d)))[0]
def u2f(u): return struct.unpack('<d', struct.pack('<Q', u))[0]
def rv_at(addr): return RV.from_address(addr)
def rv_read(addr):
    r = rv_at(addr); k = r.kind & 0xffffff
    if k in (REAL, BOOL): return ('num', u2f(r.u))
    if k == INT32: return ('num', float(struct.unpack('<i', struct.pack('<I', r.u & 0xffffffff))[0]))
    if k == INT64: return ('num', float(struct.unpack('<q', struct.pack('<Q', r.u))[0]))
    if k == STRING: return ('str', strings.get(r.u, '?'))
    if k == OBJECT: return ('inst', r.u)
    if k == ARRAY: return ('array', r.u)
    if k == UNDEF: return ('undef', None)
    return ('kind%d' % k, r.u)
def rv_write(addr, val):
    r = rv_at(addr); r.flags = 0
    if isinstance(val, tuple) and val[0] == 'str':
        b = C.create_string_buffer(val[1].encode()); keep.append(b); a = C.addressof(b); strings[a] = val[1]
        r.u, r.kind = a, STRING; return
    if isinstance(val, tuple) and val[0] == 'array': r.u, r.kind = val[1], ARRAY; return
    if val is None: r.u, r.kind = 0, UNDEF; return
    r.u, r.kind = f2u(val), REAL

class Inst:
    def __init__(self, obj, iid):
        self.obj, self.id = obj, iid
        self.buf = (C.c_uint64 * 8)(); self.buf[0] = C.addressof(VTABLE); self.ptr = C.addressof(self.buf)
        self.slots, self.arr = {}, {}
    def slot(self, var):
        if var not in self.slots:
            s = RV(); s.kind = UNDEF; keep.append(s); self.slots[var] = C.addressof(s)
        return self.slots[var]
    def get(self, var, idx=None):
        if idx is not None and idx != -0x80000000: return self.arr.get((var, idx), 0.0)
        return rv_read(self.slot(var))[1]
    def set(self, var, val, idx=None):
        if idx is not None and idx != -0x80000000: self.arr[(var, idx)] = val; return
        rv_write(self.slot(var), val)

insts, by_ptr, next_id = {}, {}, [100001]
CHARACTER_OBJS = {685, 686, 687, 523, 420}
VREF = C.CFUNCTYPE(C.c_void_p, C.c_void_p, C.c_int)
def _vref(p, vid):
    inst = by_ptr.get(p); return inst.slot(VAR_ID.get(vid, str(vid)))
_vref_c = VREF(_vref)
VTABLE = (C.c_void_p * 8)(*([C.cast(_vref_c, C.c_void_p)] * 8))
def new_inst(obj):
    i = Inst(obj, next_id[0]); next_id[0] += 1; insts[i.id] = i; by_ptr[i.ptr] = i
    i.set('object_index', obj); i.set('x', 0); i.set('y', 0); i.set('depth', 0); i.set('image_xscale', 1)
    return i
def resolve(a):
    t, v = rv_read(a)
    if t == 'inst': return by_ptr.get(v)
    if t == 'num':
        if v >= 100000: return insts.get(int(v))
        lst = [i for i in insts.values() if i.obj == int(v)]
        return lst[0] if lst else None
    return None

calls, sprites, sounds = [], {}, {}
next_spr, next_snd = [3000], [900]
state = dict(blend=0)
def args(n, p): return [rv_read(p + 16 * i) for i in range(n)]
def args_pp(n, p): return [rv_read(C.c_uint64.from_address(p + 8 * i).value) for i in range(n)]

# ---- builtins: (ret, self, other, argc, args) ----
def b_sprite_add(r, s, o, n, a):
    a = args(n, a); sid = next_spr[0]; next_spr[0] += 1
    sprites[sid] = (a[0][1], int(a[1][1]), int(a[4][1]), int(a[5][1])); rv_write(r, sid)
def b_stream(r, s, o, n, a): a = args(1, a); sid = next_snd[0]; next_snd[0] += 1; sounds[sid] = a[0][1]; rv_write(r, sid)
def b_play(r, s, o, n, a): a = args(n, a); calls.append(('play', a[0][1])); rv_write(r, 77)
def b_none(r, s, o, n, a):
    if r: rv_write(r, None)
def b_val(v): return lambda r, s, o, n, a: rv_write(r, v)
def b_blend(r, s, o, n, a):
    a = args(1, a)
    if state.get('blend') != a[0][1]: calls.append(('blend_switch',))
    state['blend'] = a[0][1]; rv_write(r, None)
def b_objspr(r, s, o, n, a): a = args(2, a); calls.append(('object_set_sprite', a[0][1], a[1][1])); rv_write(r, None)
def b_icreate(r, s, o, n, a):
    a = args(4, a); i = new_inst(int(a[3][1])); i.set('x', a[0][1]); i.set('y', a[1][1])
    calls.append(('instance_create', int(a[3][1]), a[0][1], a[1][1])); rv_write(r, i.id)
def _match(obj): return [i for i in insts.values() if (i.obj == obj or (obj == 420 and i.obj in CHARACTER_OBJS))]
def b_inum(r, s, o, n, a): a = args(1, a); rv_write(r, len(_match(int(a[0][1]))))
def b_ifind(r, s, o, n, a):
    a = args(2, a); lst = _match(int(a[0][1])); k = int(a[1][1]); rv_write(r, lst[k].id if k < len(lst) else -4)
def b_iexists(r, s, o, n, a):
    t, v = args(1, a)[0]; rv_write(r, 1 if (t == 'num' and int(v) in insts) or (t == 'inst' and v in by_ptr) else 0)
def slot_owner(addr):
    for inst in list(insts.values()) + [glob]:
        for var, sa in inst.slots.items():
            if sa == addr: return inst, var
    return None, None
arrays = {}
LAYERS = {1: [101], 2: [201, 202], 3: [301], 4: [401]}
ELTYPE = {1: 1, 2: 2, 3: 5, 4: 4}
LAYER_DEPTH = {1: 900000.0, 2: 0.0, 3: 500.0, 4: -200.0}
def b_layer_all(r, s, o, n, a):
    inst, var = slot_owner(r)
    for i, l in enumerate(sorted(LAYERS)): inst.arr[(var, i)] = l
    arrays[(inst.id, var)] = len(LAYERS); rv_write(r, ('array', 0x7777))
def b_layer_elems(r, s, o, n, a):
    els = LAYERS.get(int(args(1, a)[0][1]), []); inst, var = slot_owner(r)
    for i, e in enumerate(els): inst.arr[(var, i)] = e
    arrays[(inst.id, var)] = len(els); rv_write(r, ('array', 0x8888))
def b_eltype(r, s, o, n, a): rv_write(r, float(ELTYPE.get(int(args(1, a)[0][1]) // 100, 0)))
def b_layer_vis(r, s, o, n, a): a = args(2, a); calls.append(('layer_visible', int(a[0][1]), a[1][1])); rv_write(r, None)
def b_layer_depth(r, s, o, n, a): rv_write(r, LAYER_DEPTH.get(int(args(1, a)[0][1]), 0.0))
def b_stretched(r, s, o, n, a):
    a = args(8, a); spr = int(a[0][1])
    if spr not in sprites: calls.append(('BAD_SPRITE_DRAW', spr))
    calls.append(('stretched', spr)); rv_write(r, None)
def b_part(r, s, o, n, a):
    a = args(12, a); spr = int(a[0][1])
    if spr not in sprites: calls.append(('BAD_SPRITE_DRAW', spr))
    calls.append(('part', spr)); rv_write(r, None)
def b_spritepos(r, s, o, n, a): a = args(11, a); calls.append(('spritepos', int(a[0][1]))); rv_write(r, None)
def b_prim(name): return lambda r, s, o, n, a: (calls.append(('PRIMITIVE_' + name,)), rv_write(r, None))

BUILTIN = {
    'F_SpriteAdd': b_sprite_add, 'F_SpriteExists': b_none, 'F_AudioCreateStream': b_stream, 'F_AudioPlaySound': b_play,
    'F_AudioStopSound': b_none, 'F_AudioIsPlaying': b_val(0.0), 'F_AudioSoundPitch': b_none, 'F_GPUSetBlendMode': b_blend,
    'F_InstanceCreateDepth': b_icreate, 'F_InstanceNumber': b_inum, 'F_InstanceFind': b_ifind, 'F_InstanceExists': b_iexists,
    'F_ObjectSetSprite': b_objspr, 'F_DrawCircle': b_none, 'F_DrawLineWidth': b_none,
    'F_ViewGetCamera': b_val(3.0), 'F_CameraGetViewX': b_val(100.0), 'F_CameraGetViewY': b_val(50.0),
    'F_CameraGetViewWidth': b_val(600.0), 'F_CameraGetViewHeight': b_val(300.0),
    'F_LayerGetAll': b_layer_all, 'F_LayerGetAllElements': b_layer_elems, 'F_LayerGetElementType': b_eltype,
    'F_LayerSetVisible': b_layer_vis, 'F_PlaceMeeting': b_val(0.0), 'F_CollisionPoint': b_val(0.0),
    'F_DrawSpriteStretchedExt': b_stretched, 'F_LayerGetDepth': b_layer_depth, 'F_DrawSpritePartExt': b_part,
    'F_DrawSpritePos': b_spritepos, 'F_DrawPrimitiveBegin': b_prim('begin'), 'F_DrawVertexColor': b_prim('vertex'),
    'F_DrawPrimitiveEnd': b_prim('end'),
}
# ---- the rest ----
def e_bool(p): t, v = rv_read(p); return t == 'num' and v > 0.5
def e_real(p): t, v = rv_read(p); return v if t == 'num' else 0.0
def e_int32(p):
    t, v = rv_read(p)
    return int(v) if t == 'num' else (by_ptr[v].id if t == 'inst' else 0)
def e_getvalue(inst_rv, var, idx, out, a, b):
    inst = resolve(inst_rv); name = VAR_ID[var]
    if inst is None: rv_write(out, None); calls.append(('get_missing', name)); return
    v = inst.get(name, idx); rv_write(out, ('str', v) if isinstance(v, str) else v)
def e_setvalue(inst_rv, var, idx, val):
    inst = resolve(inst_rv); name = VAR_ID[var]; t, v = rv_read(val)
    if inst is None: calls.append(('set_missing', name)); return
    inst.set(name, v if t != 'str' else ('str', v), idx)
def e_setdirect(ip, var, idx, val):
    inst = by_ptr.get(ip); t, v = rv_read(val); inst.set(VAR_ID[var], v if t != 'str' else ('str', v), idx)
def e_getdirect(ip, var, idx, out, a, b): rv_write(out, by_ptr[ip].get(VAR_ID[var], idx))
def e_create_string(p, s): rv_write(p, ('str', C.string_at(s).decode()))
def e_find(iid): i = insts.get(iid); return i.ptr if i else None
def e_legacy(s, o, ret, argc, fid, argv):
    name = VAR_ID.get(fid, '?')
    if 'gui_width' in name: rv_write(ret, 1280.0)
    elif 'gui_height' in name: rv_write(ret, 720.0)
    elif 'array_length' in name:
        inst, var = slot_owner(C.c_uint64.from_address(argv).value)
        rv_write(ret, float(arrays.get((inst.id, var), 0)) if inst else 0.0)
    else: rv_write(ret, None)
    return ret
def e_draw_ext(s, spr, img, x, y, xs, ys, rot, col, alpha):
    if spr not in sprites: calls.append(('BAD_SPRITE_DRAW', spr))
    for v in (img, x, y, xs, ys, rot, alpha):
        if v != v or abs(v) > 1e7: calls.append(('BAD_FLOAT', spr, v))
    calls.append(('draw', spr, round(img, 2), state['blend'], round(xs, 2), round(alpha, 3), x, y))
def e_draw_self(s): calls.append(('draw_self',))
def e_script(name):
    def f(s, o, ret, argc, argv):
        calls.append((name, argc, args_pp(argc, argv) if argc > 0 else [])); rv_write(ret, None); return ret
    return f
def e_event(name): return lambda s, o: calls.append((name,))
OTHER = {
    'BOOL_RValue': e_bool, 'REAL_RValue_Ex': e_real, 'INT32_RValue': e_int32, 'FREE_RValue__Pre': lambda p: None,
    'YYCreateString': e_create_string, 'YYGML_Variable_GetValue': e_getvalue, 'YYGML_Variable_SetValue': e_setvalue,
    'Variable_SetValue_Direct': e_setdirect, 'Variable_GetValue_Direct': e_getdirect, 'YYGML_FindInstance': e_find,
    'YYGML_CallLegacyFunction': e_legacy, 'YYGML_draw_sprite_ext': e_draw_ext, 'YYGML_draw_self': e_draw_self,
    'YYGML_draw_set_alpha': lambda a: None, 'YYGML_draw_set_colour': lambda c: calls.append(('colour', c)),
    'YYGML_draw_rectangle': lambda a, b, c, d, e: calls.append(('rect', a, b, c, d)),
    'gml_Script_scr_plr_step': e_script('scr_plr_step'), 'gml_Script_scr_combo_normal': e_script('scr_combo_normal'),
    'gml_Script_scr_char_charge_effect': e_script('scr_char_charge_effect'),
    'gml_Object_o_parent_character_Create_0': e_event('parent_create'),
    'gml_Object_o_parent_character_Destroy_0': e_event('parent_destroy'),
}
CT = {'p': C.c_void_p, 'b': C.c_bool, 'd': C.c_double, 'i': C.c_int, 'f': C.c_float, 'v': None}
errors = []
def wrap(name, fn):
    def g(*a):
        try: return fn(*a)
        except Exception as e:
            errors.append(f'{name}: {e!r}'); return None
    return g
IMPL = {}                                                    # name -> stub; a renderer may replace entries
for f in meta['funcs']:
    fn = BUILTIN.get(f['name']) or OTHER.get(f['name'])
    if fn is None: fn = (lambda nm: lambda *a: calls.append(('UNSTUBBED', nm)))(f['name'])
    IMPL[f['name']] = fn
    disp = (lambda nm: lambda *a: IMPL[nm](*a))(f['name'])
    cb = C.CFUNCTYPE(CT[f['ret']], *[CT[t] for t in f['args']])(wrap(f['name'], disp)); keep.append(cb)
    C.c_void_p.in_dll(lib, 'P_' + f['name']).value = C.cast(cb, C.c_void_p).value

glob = Inst(-5, -5); by_ptr[glob.ptr] = glob
C.c_void_p.in_dll(lib, 'g_pGlobal').value = glob.ptr

def call(fn, *a):
    f = getattr(lib, fn); f.restype = None; f.argtypes = [C.c_void_p] * len(a); f(*a)
    if errors: raise RuntimeError(errors[:5])

fails = []
def check(cond, msg):
    print(('  ok   ' if cond else '  FAIL ') + msg)
    if not cond: fails.append(msg)
