"""Render Scyther's real draw calls (from the native code running under the emulator) to images.

usage: replay.py <libyoyo.so> <jeff.elf> <engine.ld> <assets dir> <out dir> <scenario>
Runs the setup half of tests/emu_test.py, then drives Scyther frame by frame and rasterises every
draw call (sprites with scale/flip/rotation/colour/alpha, additive blending, stretched/part/quad
sprites, coloured triangle strips) into a 2x view-space image per frame.
"""
import sys, os, math
import numpy as np
from PIL import Image

SO, ELF, LD, ASSETS, OUT, SCEN = sys.argv[1:7]
sys.argv = [sys.argv[0], SO, ELF, LD]
src = open('/home/user/mod-this-game-claude/jeff/tests/emu_test.py').read()
exec(compile(src[:src.index('# ============================== tests')], 'emu_setup', 'exec'), globals())
os.makedirs(OUT, exist_ok=True)

Z = 2                                   # render scale
VX, VY, VW, VH = 100.0, 50.0, 600.0, 300.0
cache = {}
def frame_img(sid, img):
    fn, n, ox, oy = sprites[sid]
    if fn not in cache:
        cache[fn] = Image.open(os.path.join(ASSETS, fn)).convert('RGBA')
    st = cache[fn]
    w = st.width // n
    k = int(math.floor(img)) % n
    return st.crop((k * w, 0, (k + 1) * w, st.height)), ox, oy

canvas = None
def composite(layer, add):
    global canvas
    a = np.asarray(layer).astype(np.float32) / 255
    if add:
        canvas[..., :3] = np.clip(canvas[..., :3] + a[..., :3] * a[..., 3:4], 0, 1)
    else:
        al = a[..., 3:4]
        canvas[..., :3] = canvas[..., :3] * (1 - al) + a[..., :3] * al

def tint(im, col, alpha):
    a = np.asarray(im).astype(np.float32)
    r, g, b = col & 255, (col >> 8) & 255, (col >> 16) & 255
    a[..., 0] *= r / 255; a[..., 1] *= g / 255; a[..., 2] *= b / 255; a[..., 3] *= alpha
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGBA')

def put_sprite(sid, img, x, y, xs, ys, rot, col, alpha):
    if sid not in sprites or abs(xs) < 1e-3 or abs(ys) < 1e-3: return
    im, ox, oy = frame_img(sid, img)
    im = tint(im, col, alpha)
    W, H = im.size
    # affine: screen = T(x,y) * R(rot) * S(xs,ys) * T(-ox,-oy); GM rotation is counter-clockwise
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    def fwd(px, py):
        u, v = (px - ox) * xs, (py - oy) * ys
        return ((x - VX) + u * c + v * s) * Z, ((y - VY) - u * s + v * c) * Z
    # inverse mapping for PIL (output -> input)
    a11, a12 = xs * c * Z, ys * s * Z
    a21, a22 = -xs * s * Z, ys * c * Z
    det = a11 * a22 - a12 * a21
    if abs(det) < 1e-9: return
    i11, i12, i21, i22 = a22 / det, -a12 / det, -a21 / det, a11 / det
    tx, ty = (x - VX) * Z, (y - VY) * Z
    c0, c1 = -(i11 * tx + i12 * ty) + ox, -(i21 * tx + i22 * ty) + oy
    # only the sprite's own box on the canvas (much faster than a full-canvas layer)
    pts = [fwd(px, py) for px, py in ((0, 0), (W, 0), (0, H), (W, H))]
    X0 = max(0, int(min(p[0] for p in pts)) - 1); X1 = min(canvas.shape[1], int(max(p[0] for p in pts)) + 2)
    Y0 = max(0, int(min(p[1] for p in pts)) - 1); Y1 = min(canvas.shape[0], int(max(p[1] for p in pts)) + 2)
    if X1 <= X0 or Y1 <= Y0: return
    coeffs = (i11, i12, c0 + i11 * X0 + i12 * Y0, i21, i22, c1 + i21 * X0 + i22 * Y0)
    layer = im.transform((X1 - X0, Y1 - Y0), Image.AFFINE, coeffs, resample=Image.BILINEAR)
    a = np.asarray(layer).astype(np.float32) / 255
    sub = canvas[Y0:Y1, X0:X1]
    if state['blend'] == 1:
        sub[..., :3] = np.clip(sub[..., :3] + a[..., :3] * a[..., 3:4], 0, 1)
    else:
        al = a[..., 3:4]
        sub[..., :3] = sub[..., :3] * (1 - al) + a[..., :3] * al

def tri_fill(p0, p1, p2, add):
    """triangle with per-vertex colour+alpha: p = (x, y, r, g, b, a) in screen px (2x)"""
    xs_ = [p0[0], p1[0], p2[0]]; ys_ = [p0[1], p1[1], p2[1]]
    x0, x1 = max(0, int(min(xs_))), min(canvas.shape[1] - 1, int(max(xs_)) + 1)
    y0, y1 = max(0, int(min(ys_))), min(canvas.shape[0] - 1, int(max(ys_)) + 1)
    if x1 < x0 or y1 < y0: return
    yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1].astype(np.float32) + 0.5
    (ax, ay), (bx, by), (cx, cy) = (p0[0], p0[1]), (p1[0], p1[1]), (p2[0], p2[1])
    d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    if abs(d) < 1e-6: return
    w0 = ((by - cy) * (xx - cx) + (cx - bx) * (yy - cy)) / d
    w1 = ((cy - ay) * (xx - cx) + (ax - cx) * (yy - cy)) / d
    w2 = 1 - w0 - w1
    m = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
    if not m.any(): return
    col = np.stack([w0 * p0[k] + w1 * p1[k] + w2 * p2[k] for k in range(2, 6)], -1)
    sub = canvas[y0:y1 + 1, x0:x1 + 1]
    al = (col[..., 3:4] * m[..., None])
    if add: sub[..., :3] = np.clip(sub[..., :3] + col[..., :3] * al, 0, 1)
    else: sub[..., :3] = sub[..., :3] * (1 - al) + col[..., :3] * al

prim_v = []
probe = None                       # a set: record the sprite ids drawn instead of rasterising (fast-forward)
def h_draw_ext():
    if probe is not None: probe.add(sW(1)); return
    put_sprite(sW(1), S(0), S(1), S(2), S(3), S(4), S(5), W(2), S(6))
def h_blend():
    a = args_rv(1, X(4)); state['blend'] = int(a[0][1]); rv_write(X(0), None)
def h_stretched():
    a = [v for _, v in args_rv(8, X(4))]
    sid, img, x, y, w, h, col, al = a
    if sid in sprites:
        im, ox, oy = frame_img(int(sid), img)
        put_sprite(int(sid), img, x + ox * w / im.width, y + oy * h / im.height, w / im.width, h / im.height, 0, int(col), al)
    rv_write(X(0), None)
def h_part():
    a = [v for _, v in args_rv(12, X(4))]
    sid, img, l, t, w, h, x, y, xs, ys, col, al = a
    sid = int(sid)
    if sid in sprites and w >= 1:
        im, ox, oy = frame_img(sid, img)
        part = im.crop((int(l), int(t), int(l + w), int(t + h)))
        fn = '_part'; sprites[-99] = (fn, 1, 0, 0); cache[fn] = part
        put_sprite(-99, 0, x, y, xs, ys, 0, int(col), al)
    rv_write(X(0), None)
def h_pos():
    a = [v for _, v in args_rv(11, X(4))]
    sid, img = int(a[0]), a[1]
    q = [((a[2 + 2 * k] - VX) * Z, (a[3 + 2 * k] - VY) * Z) for k in range(4)]
    if sid in sprites:
        im, ox, oy = frame_img(sid, img)
        W_, H_ = im.size
        src = [(0, 0), (W_, 0), (W_, H_), (0, H_)]
        for tri in ((0, 1, 2), (0, 2, 3)):     # affine per triangle, like the GPU
            (u0, v0), (u1, v1), (u2, v2) = [src[i] for i in tri]
            (x0, y0), (x1, y1), (x2, y2) = [q[i] for i in tri]
            M = np.array([[x0, y0, 1], [x1, y1, 1], [x2, y2, 1]], np.float64)
            try:
                cu = np.linalg.solve(M, [u0, u1, u2]); cv = np.linalg.solve(M, [v0, v1, v2])
            except np.linalg.LinAlgError:
                continue
            layer = im.transform(canvas.shape[1::-1], Image.AFFINE, (cu[0], cu[1], cu[2], cv[0], cv[1], cv[2]), resample=Image.BILINEAR)
            mask = Image.new('L', layer.size, 0)
            from PIL import ImageDraw
            ImageDraw.Draw(mask).polygon([q[i] for i in tri], fill=255)
            la = np.asarray(layer).copy(); la[..., 3] = (la[..., 3].astype(np.float32) * np.asarray(mask) / 255 * a[10]).astype(np.uint8)
            composite(Image.fromarray(la, 'RGBA'), state['blend'] == 1)
    rv_write(X(0), None)
def h_pbegin(): prim_v.clear(); rv_write(X(0), None)
def h_vtx():
    a = [v for _, v in args_rv(4, X(4))]
    col = int(a[2])
    prim_v.append(((a[0] - VX) * Z, (a[1] - VY) * Z, (col & 255) / 255, ((col >> 8) & 255) / 255, ((col >> 16) & 255) / 255, a[3]))
    rv_write(X(0), None)
def h_pend():
    if probe is not None: prim_v.clear(); rv_write(X(0), None); return
    for i in range(len(prim_v) - 2):
        tri_fill(prim_v[i], prim_v[i + 1], prim_v[i + 2], state['blend'] == 1)
    prim_v.clear(); rv_write(X(0), None)
def h_draw_self():
    i = by_ptr.get(X(0))
    if i is not None:
        put_sprite(int(i.get('sprite_index')), i.get('image_index') or 0, i.get('x'), i.get('y'), i.get('image_xscale') or 1, 1, 0, 0xFFFFFF, 1)
def h_combo_normal():
    i = by_ptr.get(X(0)); argc = sW(3); a = args_pp(argc, X(4))
    if i is not None:
        i.set('sprite_index', a[0][1]); i.set('image_index', 0); i.set('image_speed', 0.3)
        i.arr[('alarm', 2)] = int(a[11][1])
    rv_write(X(2), None); ret_x(X(2))
def h_set_alpha(): state['alpha'] = S(0)
def h_set_col(): state['col'] = W(0)
def h_rect():
    x1, y1, x2, y2 = S(0), S(1), S(2), S(3)
    col, al = state.get('col', 0), state.get('alpha', 1.0)
    X1, X2 = int(max(0, (min(x1, x2) - VX) * Z)), int(min(canvas.shape[1], (max(x1, x2) - VX) * Z))
    Y1, Y2 = int(max(0, (min(y1, y2) - VY) * Z)), int(min(canvas.shape[0], (max(y1, y2) - VY) * Z))
    if X2 > X1 and Y2 > Y1:
        c = np.array([(col & 255) / 255, ((col >> 8) & 255) / 255, ((col >> 16) & 255) / 255], np.float32)
        sub = canvas[Y1:Y2, X1:X2]
        if state.get('blend') == 1: sub[...] = np.clip(sub + c * al, 0, 1)
        else: sub[...] = sub * (1 - al) + c * al
def h_legacy():
    fid = VAR_ID.get(sW(4), '?')
    if 'gui_width' in fid: rv_write(X(2), 1200.0); ret_x(X(2))
    elif 'gui_height' in fid: rv_write(X(2), 600.0); ret_x(X(2))
    else: st_legacy()
HOOKS[BASE + ENG['YYGML_draw_set_alpha']] = h_set_alpha
HOOKS[BASE + ENG['YYGML_draw_set_colour']] = h_set_col
HOOKS[BASE + ENG['YYGML_draw_rectangle']] = h_rect
HOOKS[BASE + ENG['YYGML_CallLegacyFunction']] = h_legacy
for name, f in (('YYGML_draw_self', h_draw_self), ('gml_Script_scr_combo_normal', h_combo_normal), ('YYGML_draw_sprite_ext', h_draw_ext), ('F_GPUSetBlendMode', h_blend), ('F_DrawSpriteStretchedExt', h_stretched),
                ('F_DrawSpritePartExt', h_part), ('F_DrawSpritePos', h_pos), ('F_DrawPrimitiveBegin', h_pbegin),
                ('F_DrawVertexColor', h_vtx), ('F_DrawPrimitiveEnd', h_pend)):
    HOOKS[BASE + ENG[name]] = f

# ---- scene ------------------------------------------------------------------------------------
ctrl = new_inst(431); ctrl.set('plr_team', 1); ctrl.set('plr_dmg', 48); ctrl.set('plr_energy', 100); ctrl.set('plr_maxenergy', 100)
for k in ('key_defend', 'keyp_special', 'is_hurt', 'is_fallen', 'is_dead', 'is_onair', 'is_charging', 'is_running', 'plr_controller'): ctrl.set(k, 0)
scy = new_inst(686); scy.set('x', 330); scy.set('y', 300); scy.set('image_xscale', 1); scy.set('image_alpha', 1)
call('gml_Object_o_scyther_Create_0', scy.ptr, scy.ptr)
scy.set('parent', ctrl.id)
ectrl = new_inst(431); ectrl.set('plr_team', 2); ectrl.set('plr_hp', 1900); ectrl.set('is_dead', 0)
foe = new_inst(523); foe.set('x', 420); foe.set('y', 300); foe.set('parent', ectrl.id)
floor_ = new_inst(425); floor_.set('bbox_left', 0); floor_.set('bbox_right', 1499); floor_.set('bbox_top', 300); floor_.set('bbox_bottom', 620)
ledge = new_inst(425); ledge.set('bbox_left', 560); ledge.set('bbox_right', 655); ledge.set('bbox_top', 236); ledge.set('bbox_bottom', 267)
BG = (0.11, 0.16, 0.42)                     # the training stage's blue

def render_frame(void=False):
    global canvas
    canvas = np.zeros((int(VH * Z), int(VW * Z), 3), np.float32); canvas[...] = BG
    if not void:                                                # a grid like the training stage
        canvas[::48, :] = (0.25, 0.4, 0.8); canvas[:, ::48] = (0.25, 0.4, 0.8)
    state['blend'] = 0
    call('gml_Object_o_scyther_Draw_72', scy.ptr, scy.ptr)
    # the opponent: a grey stand-in at his position
    fx, fy = (foe.get('x') - VX) * Z, (foe.get('y') - VY) * Z
    canvas[int(fy - 60 * Z):int(fy), int(fx - 9 * Z):int(fx + 9 * Z)] = (0.55, 0.55, 0.6)
    state['blend'] = 0
    call('gml_Object_o_scyther_Draw_0', scy.ptr, scy.ptr)
    return Image.fromarray((np.clip(canvas, 0, 1) * 255).astype(np.uint8))

def tick(press=True):
    a2 = scy.arr.get(('alarm', 2), -1)
    if a2 is not None and a2 > 0:
        a2 -= 1; scy.arr[('alarm', 2)] = a2
        if a2 == 0:
            scy.arr[('alarm', 2)] = -1
            if press: scy.set('combo_nextcombo', 1)
            call('gml_Object_o_scyther_Alarm_2', scy.ptr, scy.ptr)
    call('gml_Object_o_scyther_Step_0', scy.ptr, scy.ptr)
    # crude physics: hspeed / vspeed move him, the floor stops him
    x = scy.get('x') + (scy.get('hspeed') or 0); y = scy.get('y') + (scy.get('vspeed') or 0)
    vs = scy.get('vspeed') or 0
    if y < 300: vs += 0.45; ctrl.set('is_onair', 1)
    else: y = 300; vs = 0; ctrl.set('is_onair', 0)
    scy.set('x', x); scy.set('y', y); scy.set('vspeed', vs)

frames = []
def run(start, n, press=True, every=1, void=False, setup=None):
    scy.set('combo_next', start); scy.set('hspeed', 0)
    if setup: setup()
    call('gml_Object_o_scyther_Alarm_3', scy.ptr, scy.ptr)
    for f in range(n):
        tick(press)
        if f % every == 0: frames.append(render_frame(void))
        if ctrl.get('is_attacking') == 0 and f > 4: break

if SCEN == 'jeff':
    jc = new_inst(431)
    for k, v in (('plr_team', 1), ('plr_dmg', 46), ('plr_energy', 100), ('plr_maxenergy', 100)): jc.set(k, v)
    for k in ('key_defend', 'keyp_special', 'is_hurt', 'is_fallen', 'is_dead', 'is_onair', 'is_charging', 'is_running', 'plr_controller'): jc.set(k, 0)
    jf = new_inst(685); jf.set('x', 330); jf.set('y', 300); jf.set('image_xscale', 1); jf.set('image_alpha', 1)
    call('gml_Object_o_jeff_Create_0', jf.ptr, jf.ptr); jf.set('parent', jc.id)
    scy.set('x', -500)                          # Scyther out of shot
    def jframe():
        global canvas
        canvas = np.zeros((int(VH * Z), int(VW * Z), 3), np.float32); canvas[...] = BG
        canvas[::48, :] = (0.25, 0.4, 0.8); canvas[:, ::48] = (0.25, 0.4, 0.8)
        fx_, fy_ = (foe.get('x') - VX) * Z, (foe.get('y') - VY) * Z
        canvas[int(fy_ - 60 * Z):int(fy_), int(fx_ - 9 * Z):int(fx_ + 9 * Z)] = (0.55, 0.55, 0.6)
        state['blend'] = 0
        call('gml_Object_o_jeff_Draw_0', jf.ptr, jf.ptr)
        return Image.fromarray((np.clip(canvas, 0, 1) * 255).astype(np.uint8))
    def jtick(press=True):
        a2 = jf.arr.get(('alarm', 2), -1)
        if a2 is not None and a2 > 0:
            a2 -= 1; jf.arr[('alarm', 2)] = a2
            if a2 == 0:
                jf.arr[('alarm', 2)] = -1
                if press: jf.set('combo_nextcombo', 1)
                call('gml_Object_o_jeff_Alarm_2', jf.ptr, jf.ptr)
        call('gml_Object_o_jeff_Step_0', jf.ptr, jf.ptr)
        n = sprites.get(int(jf.get('sprite_index')), ('', 1))[1]
        if (jf.get('image_speed') or 0) > 0: jf.set('image_index', ((jf.get('image_index') or 0) + jf.get('image_speed')) % n)
        x = jf.get('x') + (jf.get('hspeed') or 0); y = jf.get('y') + (jf.get('vspeed') or 0); vs = jf.get('vspeed') or 0
        if y < 300: vs += 0.45; jc.set('is_onair', 1)
        else: y = 300; vs = 0; jc.set('is_onair', 0)
        jf.set('x', min(max(x, 120), 680)); jf.set('y', y); jf.set('vspeed', vs); jf.set('hspeed', 0)
    def jrun(start, n, press=True, setup=None):
        jf.set('combo_next', start)
        if setup: setup()
        call('gml_Object_o_jeff_Alarm_3', jf.ptr, jf.ptr)
        for f in range(n):
            jtick(press); frames.append(jframe())
            if jc.get('is_attacking') == 0 and f > 4: break
        for f in range(8): jtick(False); frames.append(jframe())
    foe.set('x', 395)
    jrun(1, 160); jf.set('x', 330); jrun(50, 120); jf.set('x', 330); jrun(60, 30, press=False)
    def jump(): jf.set('y', 240); jf.set('vspeed', -2); jc.set('is_onair', 1)
    jf.set('x', 330); jrun(61, 30, press=False, setup=jump)
    jf.set('x', 250); foe.set('x', 420); jrun(100, 140, press=False)
    jf.set('x', 300); foe.set('x', 460); jrun(110, 100, press=False)
elif SCEN == 'jeff4':
    jc = new_inst(431)
    for k, v in (('plr_team', 1), ('plr_dmg', 46), ('plr_energy', 100), ('plr_maxenergy', 100)): jc.set(k, v)
    for k in ('key_defend', 'keyp_special', 'key_down', 'is_hurt', 'is_fallen', 'is_dead', 'is_onair', 'is_charging', 'is_running', 'plr_controller'): jc.set(k, 0)
    jf = new_inst(685); jf.set('x', 300); jf.set('y', 300); jf.set('image_xscale', 1); jf.set('image_alpha', 1)
    call('gml_Object_o_jeff_Create_0', jf.ptr, jf.ptr); jf.set('parent', jc.id)
    call('gml_Object_o_jeff_Alarm_0', jf.ptr, jf.ptr)
    scy.set('x', -500)
    sid = {v[0]: k for k, v in sprites.items()}
    foe.set('sprite_index', sid['scyther_stand.png']); foe.set('image_index', 0)
    def jframe(gui=False):
        global canvas, VX, VY, Z
        canvas = np.zeros((int(VH * Z), int(VW * Z), 3), np.float32); canvas[...] = BG
        canvas[::48, :] = (0.25, 0.4, 0.8); canvas[:, ::48] = (0.25, 0.4, 0.8)
        fx_, fy_ = (foe.get('x') - VX) * Z, (foe.get('y') - VY) * Z
        canvas[int(fy_ - 60 * Z):int(fy_), int(fx_ - 9 * Z):int(fx_ + 9 * Z)] = (0.55, 0.55, 0.6)
        state['blend'] = 0
        call('gml_Object_o_jeff_Draw_0', jf.ptr, jf.ptr)
        if gui:
            sv = (VX, VY, Z); VX, VY, Z = 0.0, 0.0, 1
            state['blend'] = 0
            call('gml_Object_o_jeff_Draw_64', jf.ptr, jf.ptr)
            VX, VY, Z = sv
        return Image.fromarray((np.clip(canvas, 0, 1) * 255).astype(np.uint8))
    def jtick(press=True):
        a2 = jf.arr.get(('alarm', 2), -1)
        if a2 is not None and a2 > 0:
            a2 -= 1; jf.arr[('alarm', 2)] = a2
            if a2 == 0:
                jf.arr[('alarm', 2)] = -1
                if press: jf.set('combo_nextcombo', 1)
                call('gml_Object_o_jeff_Alarm_2', jf.ptr, jf.ptr)
        call('gml_Object_o_jeff_Step_0', jf.ptr, jf.ptr)
        n = sprites.get(int(jf.get('sprite_index')), ('', 1))[1]
        if (jf.get('image_speed') or 0) > 0: jf.set('image_index', ((jf.get('image_index') or 0) + jf.get('image_speed')) % n)
        x = jf.get('x') + (jf.get('hspeed') or 0); y = jf.get('y') + (jf.get('vspeed') or 0); vs = jf.get('vspeed') or 0
        if y < 300: vs += 0.45; jc.set('is_onair', 1)
        else: y = 300; vs = 0; jc.set('is_onair', 0)
        jf.set('x', min(max(x, 120), 680)); jf.set('y', y); jf.set('vspeed', vs); jf.set('hspeed', 0)
    def idle(n, gui=False):
        for _ in range(n):
            jtick(False)
            if not jc.get('is_attacking'):
                jf.set('sprite_index', jf.get('spr_stand') if not jc.get('key_defend') else jf.get('spr_defend'))
            frames.append(jframe(gui))
    def jrun(start, n, press=True):
        jf.set('combo_next', start)
        call('gml_Object_o_jeff_Alarm_3', jf.ptr, jf.ptr)
        for f in range(n):
            jtick(press); frames.append(jframe())
            if jc.get('is_attacking') == 0 and f > 4: break
        idle(8)
    foe.set('x', 390)
    idle(14)
    for k in (1, 1, 0, 0, 0, 1, 1, 0):                 # double-tap shield: the transformation
        jc.set('key_defend', k); jtick(False); frames.append(jframe())
    jc.set('key_defend', 0)
    for _ in range(36): jtick(False); frames.append(jframe())
    idle(16)
    jf.set('image_xscale', 1); jrun(1, 160); jf.set('x', 300); jrun(50, 120)
    jf.set('x', 240); foe.set('x', 430); jrun(100, 70, press=False)
    jf.set('x', 300); foe.set('x', 390); jrun(110, 60, press=False)
    jf.set('x', 300); foe.set('x', 420); jc.set('plr_energy', 100); idle(6)
    for k in (1, 0, 0, 0, 1):                        # double-tap skill: RED BLACK HOLE
        jc.set('keyp_special', k); jtick(False); frames.append(jframe(True))
    jc.set('keyp_special', 0); idle(172, gui=True)
    ectrl.set('plr_hp', 1900); jf.set('x', 300); foe.set('x', 420); jc.set('plr_energy', 100); idle(10)
    for d, k in ((1, 1), (1, 0), (0, 0), (0, 0), (0, 0), (1, 1), (1, 0), (0, 0)):   # both double-tapped: HOLLOW PURPLE
        jc.set('key_defend', d); jc.set('keyp_special', k); jtick(False); frames.append(jframe(True))
    jc.set('key_defend', 0); jc.set('keyp_special', 0); idle(200, gui=True)
elif SCEN in ('grey', 'grey2'):
    gc = new_inst(431)
    for k, v in (('plr_team', 1), ('plr_dmg', 47), ('plr_energy', 100), ('plr_maxenergy', 100)): gc.set(k, v)
    for k in ('key_defend', 'keyp_special', 'key_down', 'is_hurt', 'is_fallen', 'is_dead', 'is_onair', 'is_charging', 'is_running', 'plr_controller'): gc.set(k, 0)
    gr = new_inst(687); gr.set('x', 280); gr.set('y', 300); gr.set('image_xscale', 1); gr.set('image_alpha', 1)
    call('gml_Object_o_grey_Create_0', gr.ptr, gr.ptr); gr.set('parent', gc.id); gr.set('leavecombo_penaltytime', 8)
    call('gml_Object_o_grey_Alarm_0', gr.ptr, gr.ptr)
    scy.set('x', -500)
    def gframe(gui=False):
        global canvas, VX, VY, Z
        canvas = np.zeros((int(VH * Z), int(VW * Z), 3), np.float32); canvas[...] = BG
        canvas[::48, :] = (0.25, 0.4, 0.8); canvas[:, ::48] = (0.25, 0.4, 0.8)
        fx_, fy_ = (foe.get('x') - VX) * Z, (foe.get('y') - VY) * Z
        canvas[int(fy_ - 60 * Z):int(fy_), int(fx_ - 9 * Z):int(fx_ + 9 * Z)] = (0.55, 0.55, 0.6)
        state['blend'] = 0
        call('gml_Object_o_grey_Draw_0', gr.ptr, gr.ptr)
        if gui:
            sv = (VX, VY, Z); VX, VY, Z = 0.0, 0.0, 1
            state['blend'] = 0
            call('gml_Object_o_grey_Draw_64', gr.ptr, gr.ptr)
            VX, VY, Z = sv
        return Image.fromarray((np.clip(canvas, 0, 1) * 255).astype(np.uint8))
    def gtick(press=True, phys=True):
        a2 = gr.arr.get(('alarm', 2), -1)
        if a2 is not None and a2 > 0:
            a2 -= 1; gr.arr[('alarm', 2)] = a2
            if a2 == 0:
                gr.arr[('alarm', 2)] = -1
                if press: gr.set('combo_nextcombo', 1)
                call('gml_Object_o_grey_Alarm_2', gr.ptr, gr.ptr)
        call('gml_Object_o_grey_Step_0', gr.ptr, gr.ptr)
        if phys:
            x = gr.get('x') + (gr.get('hspeed') or 0); y = gr.get('y') + (gr.get('vspeed') or 0); vs = gr.get('vspeed') or 0
            if y < 300: vs += 0.45; gc.set('is_onair', 1)
            else: y = 300; vs = 0; gc.set('is_onair', 0)
            gr.set('x', min(max(x, 120), 680)); gr.set('y', y); gr.set('vspeed', vs)
    def gidle(n, gui=False, setup=None):
        for _ in range(n):
            if setup: setup()
            gtick(False); frames.append(gframe(gui))
    def grun(start, n=400, press=True, setup=None, gui=False):
        gr.set('combo_next', start)
        if setup: setup()
        call('gml_Object_o_grey_Alarm_3', gr.ptr, gr.ptr)
        for f in range(n):
            gtick(press); frames.append(gframe(gui))
            if gc.get('is_attacking') == 0 and f > 4: break
        gidle(14)
    foe.set('x', 345)
    gidle(30 if SCEN == 'grey' else 6)
    def walk(): gr.set('hspeed', 2.4); gr.set('sprite_index', gr.get('spr_walk'))
    if SCEN == 'grey': gidle(26, setup=walk)
    gr.set('hspeed', 0); gr.set('sprite_index', gr.get('spr_stand')); gidle(10)
    gr.set('x', 280); foe.set('x', 345); gr.set('image_xscale', 1)
    grun(1)
    gr.set('x', 280); foe.set('x', 345); gr.set('image_xscale', 1); gidle(6)
    if SCEN == 'grey2': gr.set('x', 260); foe.set('x', 330)
    for _ in ([0] if SCEN == 'grey' else []):
     grun(50)
     gr.set('x', 220); foe.set('x', 330); gr.set('image_xscale', 1)
     def run_(): gc.set('is_running', 1); gr.set('hspeed', 8.0)
     gidle(10, setup=run_)
     grun(1, press=False, setup=lambda: gc.set('is_running', 1)); gc.set('is_running', 0)
     gr.set('x', 260); gr.set('image_xscale', 1)
     gr.set('vspeed', -7.2); gr.set('y', 299); gc.set('is_onair', 1)
     for _ in range(36): gtick(False); frames.append(gframe())
     gidle(8)
     gr.set('x', 240); foe.set('x', 330); gr.set('image_xscale', 1)
     grun(100, press=False); gidle(30)
     gr.set('x', 240); foe.set('x', 330)
     grun(110, press=False); gidle(24)
    gr.set('x', 260); foe.set('x', 330); gr.set('image_xscale', 1); gc.set('plr_energy', 100)
    gc.set('key_defend', 1); gc.set('keyp_special', 1); gtick(False); frames.append(gframe(True))
    gc.set('key_defend', 0); gc.set('keyp_special', 0)
    for _ in range(186): gtick(False); frames.append(gframe(True))
    gidle(20)
elif SCEN == 'grey3':                       # the new bits: air chain, dash, charge, idle flourish, victory
    gc = new_inst(431)
    for k, v in (('plr_team', 1), ('plr_dmg', 47), ('plr_energy', 100), ('plr_maxenergy', 100)): gc.set(k, v)
    for k in ('key_defend', 'keyp_special', 'key_down', 'is_hurt', 'is_fallen', 'is_dead', 'is_onair', 'is_charging', 'is_running', 'plr_controller'): gc.set(k, 0)
    gr = new_inst(687); gr.set('x', 280); gr.set('y', 300); gr.set('image_xscale', 1); gr.set('image_alpha', 1)
    call('gml_Object_o_grey_Create_0', gr.ptr, gr.ptr); gr.set('parent', gc.id); gr.set('leavecombo_penaltytime', 8)
    call('gml_Object_o_grey_Alarm_0', gr.ptr, gr.ptr)
    scy.set('x', -500); ectrl.set('is_dead', 0)
    def gframe(gui=False):
        global canvas
        canvas = np.zeros((int(VH * Z), int(VW * Z), 3), np.float32); canvas[...] = BG
        canvas[::48, :] = (0.25, 0.4, 0.8); canvas[:, ::48] = (0.25, 0.4, 0.8)
        fx_, fy_ = (foe.get('x') - VX) * Z, (foe.get('y') - VY) * Z
        if ectrl.get('is_dead'): canvas[int(fy_ - 10 * Z):int(fy_), int(fx_ - 30 * Z):int(fx_ + 30 * Z)] = (0.55, 0.55, 0.6)
        else: canvas[int(fy_ - 60 * Z):int(fy_), int(fx_ - 9 * Z):int(fx_ + 9 * Z)] = (0.55, 0.55, 0.6)
        state['blend'] = 0
        call('gml_Object_o_grey_Draw_0', gr.ptr, gr.ptr)
        return Image.fromarray((np.clip(canvas, 0, 1) * 255).astype(np.uint8))
    def gtick(press=True):
        a2 = gr.arr.get(('alarm', 2), -1)
        if a2 is not None and a2 > 0:
            a2 -= 1; gr.arr[('alarm', 2)] = a2
            if a2 == 0:
                gr.arr[('alarm', 2)] = -1
                if press: gr.set('combo_nextcombo', 1)
                call('gml_Object_o_grey_Alarm_2', gr.ptr, gr.ptr)
        call('gml_Object_o_grey_Step_0', gr.ptr, gr.ptr)
        x = gr.get('x') + (gr.get('hspeed') or 0); y = gr.get('y') + (gr.get('vspeed') or 0); vs = gr.get('vspeed') or 0
        if y < 300: vs += 0.45; gc.set('is_onair', 1)
        else: y = 300; vs = 0; gc.set('is_onair', 0)
        gr.set('x', min(max(x, 120), 680)); gr.set('y', y); gr.set('vspeed', vs)
    def skip_until(sprite_name, limit):
        global probe
        want = [k for k, v in sprites.items() if v[0] == sprite_name]
        for _ in range(limit):
            gtick(False)
            probe = set(); call('gml_Object_o_grey_Draw_0', gr.ptr, gr.ptr); got = probe; probe = None
            if any(w in got for w in want): return True
        return False
    foe.set('x', 360)
    for _ in range(20): gtick(False); frames.append(gframe())
    gr.set('x', 250); gr.set('y', 170); gr.set('vspeed', -2); gc.set('is_onair', 1)    # the air chain
    gr.set('combo_next', 11); call('gml_Object_o_grey_Alarm_3', gr.ptr, gr.ptr)
    for f in range(200):
        gtick(True); frames.append(gframe())
        if gc.get('is_attacking') == 0 and f > 4: break
    for _ in range(16): gtick(False); frames.append(gframe())
    gr.set('x', 200); gr.set('y', 220); gr.set('vspeed', -1); gc.set('is_onair', 1)    # an air dash
    for k in range(14):
        gr.set('hspeed', 9.4 if k < 10 else 3.0); gtick(False); frames.append(gframe())
    for _ in range(30): gr.set('hspeed', 0); gtick(False); frames.append(gframe())
    for _ in range(4): gtick(False)
    gc.set('is_running', 1)                                                             # breaking into a run
    for _ in range(18): gr.set('hspeed', 8.0); gtick(False); frames.append(gframe())
    gc.set('is_running', 0); gr.set('hspeed', 0)
    for _ in range(10): gtick(False); frames.append(gframe())
    gc.set('is_fallen', 1)                                                              # knocked down, then up
    for _ in range(26): gtick(False); frames.append(gframe())
    gc.set('is_fallen', 0)
    for _ in range(20): gtick(False); frames.append(gframe())
    gr.set('x', 280)
    gc.set('is_charging', 1)                                                            # charging
    for _ in range(50): gtick(False); frames.append(gframe())
    gc.set('is_charging', 0)
    for _ in range(10): gtick(False); frames.append(gframe())
    if skip_until('grey_sword.png', 460):                                               # the idle flourish
        for _ in range(48): gtick(False); frames.append(gframe())
    for _ in range(10): gtick(False); frames.append(gframe())
    ectrl.set('is_dead', 1)                                                              # victory
    for _ in range(150): gtick(False); frames.append(gframe())
elif SCEN == 'combos':
    run(1, 170); scy.set('x', 330); scy.set('image_xscale', 1); foe.set('x', 420)
    run(50, 260)
elif SCEN == 'moves':
    def running(): ctrl.set('is_running', 1)
    run(1, 30, press=False, setup=running); ctrl.set('is_running', 0)
    for _ in range(20): tick(False)
    scy.set('x', 330); scy.set('image_xscale', 1); run(60, 30, press=False)
    for _ in range(30): tick(False)
    def jump(): scy.set('y', 230); scy.set('vspeed', -2); ctrl.set('is_onair', 1)
    scy.set('x', 330); run(11, 70, press=True, setup=jump)
    for _ in range(20): tick(False)
    scy.set('x', 330); run(61, 70, press=False, setup=jump)
elif SCEN.startswith('moonfall'):          # Grey's MOONFALL: the ground, the climb, space, the impact, the lava world
    gc = new_inst(431)
    for k, v in (('plr_team', 1), ('plr_dmg', 47), ('plr_energy', 100), ('plr_maxenergy', 100)): gc.set(k, v)
    for k in ('key_defend', 'keyp_special', 'key_down', 'is_hurt', 'is_fallen', 'is_dead', 'is_onair', 'is_charging', 'is_running', 'plr_controller'): gc.set(k, 0)
    gr = new_inst(687); gr.set('x', 260); gr.set('y', 300); gr.set('image_xscale', 1); gr.set('image_alpha', 1)
    call('gml_Object_o_grey_Create_0', gr.ptr, gr.ptr); gr.set('parent', gc.id); gr.set('leavecombo_penaltytime', 8)
    call('gml_Object_o_grey_Alarm_0', gr.ptr, gr.ptr)
    scy.set('x', -500); foe.set('x', 345)
    yy_ = (np.arange(int(VH * Z)) / (VH * Z))[:, None]
    SKYC = np.array([0.36, 0.58, 0.92]) * (1 - yy_) + np.array([0.70, 0.84, 0.97]) * yy_     # a daytime stage
    def mframe():
        global canvas, VX, VY, Z
        canvas = np.zeros((int(VH * Z), int(VW * Z), 3), np.float32); canvas[...] = SKYC[:, None, :]
        gy = int((300 - VY) * Z); canvas[gy:, :] = (0.33, 0.27, 0.2); canvas[gy:gy + 6, :] = (0.25, 0.5, 0.2)
        state['blend'] = 0
        call('gml_Object_o_grey_Draw_72', gr.ptr, gr.ptr)
        fx_, fy_ = (foe.get('x') - VX) * Z, (foe.get('y') - VY) * Z
        canvas[int(fy_ - 60 * Z):int(fy_), int(fx_ - 9 * Z):int(fx_ + 9 * Z)] = (0.55, 0.55, 0.6)
        state['blend'] = 0
        call('gml_Object_o_grey_Draw_0', gr.ptr, gr.ptr)
        sv = (VX, VY, Z); VX, VY, Z = 0.0, 0.0, 1
        state['blend'] = 0
        call('gml_Object_o_grey_Draw_64', gr.ptr, gr.ptr)
        VX, VY, Z = sv
        return Image.fromarray((np.clip(canvas, 0, 1) * 255).astype(np.uint8))
    def mtick():
        a2 = gr.arr.get(('alarm', 2), -1)
        if a2 is not None and a2 > 0:
            a2 -= 1; gr.arr[('alarm', 2)] = a2
            if a2 == 0:
                gr.arr[('alarm', 2)] = -1
                call('gml_Object_o_grey_Alarm_2', gr.ptr, gr.ptr)
        call('gml_Object_o_grey_Step_0', gr.ptr, gr.ptr)
    for _ in range(44): mtick()
    gc.set('key_defend', 1); gc.set('keyp_special', 1); mtick()
    gc.set('key_defend', 0); gc.set('keyp_special', 0)
    every = int(SCEN[8:] or 8)
    names = []
    for f in range(1, 520):
        mtick()
        if f % every == 0 or f in (30, 44, 50, 70, 96, 104, 120, 244, 250, 262, 280):
            frames.append(mframe()); names.append(f)
    print('special frames', names)
elif SCEN == 'void':
    ctrl.set('key_defend', 1); ctrl.set('keyp_special', 1); ctrl.set('plr_energy', 100)
    tick(); ctrl.set('key_defend', 0)
    for f in range(40 + 180 + 45):
        tick(False)
        if f < 38 and f % 3 == 0: frames.append(render_frame())
    for f in range(40):
        tick(False)
        if f % 4 == 0: frames.append(render_frame(True))
    scy.set('x', 330); scy.set('image_xscale', 1); foe.set('x', 420)
    run(1, 120, every=2, void=True)
for i, im in enumerate(frames):
    im.save(os.path.join(OUT, f'f{i:03d}.png'))
print('frames', len(frames))
