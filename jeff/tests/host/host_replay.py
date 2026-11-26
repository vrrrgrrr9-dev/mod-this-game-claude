"""tests/replay.py's rasteriser on the host build of grey.c: renders Grey's real draw calls to PNGs.
usage: host_replay.py <grey host .so> <assets dir> <out dir> <scenario> [frames]
scenarios: moonfall (frames: comma list or every-N, default 8), axe (sub attack 1), moves"""
import math, os, sys
import numpy as np
from PIL import Image
so, ASSETS, OUT, SCEN = sys.argv[1:5]
ARG = sys.argv[5] if len(sys.argv) > 5 else ''
sys.argv = [sys.argv[0], so, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shim.json')]
from hostemu import *
os.makedirs(OUT, exist_ok=True)

Z = 2
VX, VY, VW, VH = 100.0, 50.0, 600.0, 300.0
cache = {}
canvas = None
probe = None                          # fast-forward: record sprite ids instead of rasterising
rs = dict(col=0xFFFFFF, alpha=1.0)

def frame_img(sid, img):
    fn, n, ox, oy = sprites[sid]
    if fn not in cache: cache[fn] = Image.open(os.path.join(ASSETS, fn)).convert('RGBA')
    st = cache[fn]; w = st.width // n; k = int(math.floor(img)) % n
    return st.crop((k * w, 0, (k + 1) * w, st.height)), ox, oy
def tint(im, col, alpha):
    a = np.asarray(im).astype(np.float32)
    a[..., 0] *= (col & 255) / 255; a[..., 1] *= ((col >> 8) & 255) / 255; a[..., 2] *= ((col >> 16) & 255) / 255; a[..., 3] *= alpha
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGBA')
def put_sprite(sid, img, x, y, xs, ys, rot, col, alpha):
    if sid not in sprites or abs(xs) < 1e-3 or abs(ys) < 1e-3 or alpha <= 0.002: return
    im, ox, oy = frame_img(sid, img); im = tint(im, col, alpha); W, H = im.size
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    def fwd(px, py):
        u, v = (px - ox) * xs, (py - oy) * ys
        return ((x - VX) + u * c + v * s) * Z, ((y - VY) - u * s + v * c) * Z
    a11, a12, a21, a22 = xs * c * Z, ys * s * Z, -xs * s * Z, ys * c * Z
    det = a11 * a22 - a12 * a21
    if abs(det) < 1e-9: return
    i11, i12, i21, i22 = a22 / det, -a12 / det, -a21 / det, a11 / det
    tx, ty = (x - VX) * Z, (y - VY) * Z
    c0, c1 = -(i11 * tx + i12 * ty) + ox, -(i21 * tx + i22 * ty) + oy
    pts = [fwd(px, py) for px, py in ((0, 0), (W, 0), (0, H), (W, H))]
    X0 = max(0, int(min(p[0] for p in pts)) - 1); X1 = min(canvas.shape[1], int(max(p[0] for p in pts)) + 2)
    Y0 = max(0, int(min(p[1] for p in pts)) - 1); Y1 = min(canvas.shape[0], int(max(p[1] for p in pts)) + 2)
    if X1 <= X0 or Y1 <= Y0: return
    coeffs = (i11, i12, c0 + i11 * X0 + i12 * Y0, i21, i22, c1 + i21 * X0 + i22 * Y0)
    a = np.asarray(im.transform((X1 - X0, Y1 - Y0), Image.AFFINE, coeffs, resample=Image.BILINEAR)).astype(np.float32) / 255
    sub = canvas[Y0:Y1, X0:X1]
    if state['blend'] == 1: sub[..., :3] = np.clip(sub[..., :3] + a[..., :3] * a[..., 3:4], 0, 1)
    else: al = a[..., 3:4]; sub[..., :3] = sub[..., :3] * (1 - al) + a[..., :3] * al

def h_draw_ext(s, spr, img, x, y, xs, ys, rot, col, alpha):
    if probe is not None: probe.add(spr); return
    put_sprite(spr, img, x, y, xs, ys, rot, col, alpha)
def h_blend(r, s, o, n, a): state['blend'] = int(args(1, a)[0][1]); rv_write(r, None)
def h_stretched(r, s, o, n, a):
    sid, img, x, y, w, h, col, al = [v for _, v in args(8, a)]
    if probe is not None: probe.add(int(sid))
    elif int(sid) in sprites:
        im, ox, oy = frame_img(int(sid), img)
        put_sprite(int(sid), img, x + ox * w / im.width, y + oy * h / im.height, w / im.width, h / im.height, 0, int(col), al)
    rv_write(r, None)
def h_part(r, s, o, n, a):
    sid, img, l, t, w, h, x, y, xs, ys, col, al = [v for _, v in args(12, a)]
    sid = int(sid)
    if probe is not None: probe.add(sid)
    elif sid in sprites and w >= 1:
        im, ox, oy = frame_img(sid, img)
        cache['_part'] = im.crop((int(l), int(t), int(l + w), int(t + h))); sprites[-99] = ('_part', 1, 0, 0)
        put_sprite(-99, 0, x, y, xs, ys, 0, int(col), al)
    rv_write(r, None)
def h_rect(x1, y1, x2, y2, outline):
    if probe is not None: return
    col, al = rs['col'], rs['alpha']
    X1, X2 = int(max(0, (min(x1, x2) - VX) * Z)), int(min(canvas.shape[1], (max(x1, x2) - VX) * Z))
    Y1, Y2 = int(max(0, (min(y1, y2) - VY) * Z)), int(min(canvas.shape[0], (max(y1, y2) - VY) * Z))
    if X2 > X1 and Y2 > Y1:
        c = np.array([(col & 255) / 255, ((col >> 8) & 255) / 255, ((col >> 16) & 255) / 255], np.float32)
        sub = canvas[Y1:Y2, X1:X2]
        if state.get('blend') == 1: sub[...] = np.clip(sub + c * al, 0, 1)
        else: sub[...] = sub * (1 - al) + c * al
def h_legacy(s, o, ret, argc, fid, argv):
    name = VAR_ID.get(fid, '?')
    if 'gui_width' in name: rv_write(ret, 1200.0); return ret
    if 'gui_height' in name: rv_write(ret, 600.0); return ret
    return e_legacy(s, o, ret, argc, fid, argv)
IMPL.update(YYGML_draw_sprite_ext=h_draw_ext, F_GPUSetBlendMode=h_blend, F_DrawSpriteStretchedExt=h_stretched,
            F_DrawSpritePartExt=h_part, YYGML_draw_rectangle=h_rect, YYGML_CallLegacyFunction=h_legacy,
            YYGML_draw_set_alpha=lambda a: rs.__setitem__('alpha', a),
            YYGML_draw_set_colour=lambda c: rs.__setitem__('col', c))

# ---- scene ----
menu = new_inst(5); call('grey_load_assets', menu.ptr)
gc = new_inst(431)
for k, v in (('plr_team', 1), ('plr_dmg', 47), ('plr_energy', 100), ('plr_maxenergy', 100)): gc.set(k, v)
for k in ('key_defend', 'keyp_special', 'key_down', 'is_hurt', 'is_fallen', 'is_dead', 'is_onair', 'is_charging', 'is_running', 'plr_controller'): gc.set(k, 0)
gr = new_inst(687); gr.set('x', 260); gr.set('y', 300); gr.set('image_xscale', 1); gr.set('image_alpha', 1)
call('gml_Object_o_grey_Create_0', gr.ptr, gr.ptr); gr.set('parent', gc.id); gr.set('leavecombo_penaltytime', 8)
call('gml_Object_o_grey_Alarm_0', gr.ptr, gr.ptr)
ectrl = new_inst(431); ectrl.set('plr_team', 2); ectrl.set('plr_hp', 1900); ectrl.set('is_dead', 0)
foe = new_inst(523); foe.set('x', 345); foe.set('y', 300); foe.set('parent', ectrl.id)
yy_ = (np.arange(int(VH * Z)) / (VH * Z))[:, None]
SKYC = np.array([0.36, 0.58, 0.92]) * (1 - yy_) + np.array([0.70, 0.84, 0.97]) * yy_

def mframe(gui=True):
    global canvas, VX, VY, Z
    canvas = np.zeros((int(VH * Z), int(VW * Z), 3), np.float32); canvas[...] = SKYC[:, None, :]
    gy = int((300 - VY) * Z); canvas[gy:, :] = (0.33, 0.27, 0.2); canvas[gy:gy + 6, :] = (0.25, 0.5, 0.2)
    state['blend'] = 0
    call('gml_Object_o_grey_Draw_72', gr.ptr, gr.ptr)
    fx_, fy_ = (foe.get('x') - VX) * Z, (foe.get('y') - VY) * Z
    canvas[max(0, int(fy_ - 60 * Z)):max(0, int(fy_)), max(0, int(fx_ - 9 * Z)):max(0, int(fx_ + 9 * Z))] = (0.55, 0.55, 0.6)
    state['blend'] = 0
    call('gml_Object_o_grey_Draw_0', gr.ptr, gr.ptr)
    if gui:
        sv = (VX, VY, Z); VX, VY, Z = 0.0, 0.0, 1
        state['blend'] = 0
        call('gml_Object_o_grey_Draw_64', gr.ptr, gr.ptr)
        VX, VY, Z = sv
    return Image.fromarray((np.clip(canvas, 0, 1) * 255).astype(np.uint8))
def mtick(press=False, physics=True):
    a2 = gr.arr.get(('alarm', 2), -1)
    if a2 is not None and a2 > 0:
        a2 -= 1; gr.arr[('alarm', 2)] = a2
        if a2 == 0:
            gr.arr[('alarm', 2)] = -1
            if press: gr.set('combo_nextcombo', 1)
            call('gml_Object_o_grey_Alarm_2', gr.ptr, gr.ptr)
    call('gml_Object_o_grey_Step_0', gr.ptr, gr.ptr)
    if physics:
        x = gr.get('x') + (gr.get('hspeed') or 0); y = gr.get('y') + (gr.get('vspeed') or 0); vs = gr.get('vspeed') or 0
        if y < 300: vs += 0.45; gc.set('is_onair', 1)
        else: y = 300; vs = 0; gc.set('is_onair', 0)
        gr.set('x', x); gr.set('y', y); gr.set('vspeed', vs)

frames, names = [], []
if SCEN == 'moonfall':
    for _ in range(44): mtick()
    gc.set('key_defend', 1); gc.set('keyp_special', 1); mtick(physics=False)
    gc.set('key_defend', 0); gc.set('keyp_special', 0)
    want = {int(v) for v in ARG.split(',')} if ',' in ARG else None
    every = int(ARG) if ARG and want is None else 8
    for f in range(1, 501):
        mtick(physics=False)
        if (want and f in want) or (not want and f % every == 0):
            frames.append(mframe()); names.append(f)
elif SCEN in ('axe', 'axeL'):                     # sub attack 1 = skill 1 = combo_next 100
    if SCEN == 'axe': gr.set('x', 300); foe.set('x', 352)
    else: gr.set('x', 420); foe.set('x', 368); gr.set('image_xscale', -1)
    for _ in range(50): mtick()
    gr.set('combo_next', 100); gr.set('hspeed', 0)
    call('gml_Object_o_grey_Alarm_3', gr.ptr, gr.ptr)
    every = int(ARG or 1)
    for f in range(1, 61):
        mtick()
        n0 = len(calls)
        if f % every == 0: frames.append(mframe(gui=False)); names.append(f)
for n, im in zip(names, frames):
    im.save(os.path.join(OUT, f'{SCEN}_{n:03d}.png'))
print(SCEN, 'frames', names)
if errors: print('ERRORS', errors[:5])
