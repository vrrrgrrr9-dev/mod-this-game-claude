"""Grey the stickman - skeleton, poses, easing and a preview renderer.

Grey is not drawn from sprite strips: the game draws his lines every frame from this skeleton
(src/grey.c), so every move is smooth at 60 fps.  This module is the single source of truth for the
skeleton and the interpolation; moves.py authors the choreography with it and exports C tables.

Coordinates: game pixels, y down, facing right.  Angles in degrees: 0 = pointing right (forward),
-90 = up, 90 = down.  All limb angles are absolute (not relative to the parent bone).
"""
import math
from PIL import Image, ImageDraw

# bone lengths (game px)
L_SPINE, L_NECK, HEAD_R = 15.0, 8.0, 6.0
L_UARM, L_FARM, L_THIGH, L_SHIN = 10.0, 10.0, 12.0, 12.5
SHOULDER_DROP = 2.0                        # shoulders sit a little below the neck
W_LIMB, W_TORSO, W_OUT = 3.0, 3.4, 1.0     # line widths (core) and outline

C_FILL = (70, 70, 78)                      # dark gray
C_BACK = (52, 52, 60)                      # far limbs, a shade darker
C_LINE = (10, 10, 14)

ANGLES = ('sp', 'hd', 'ub', 'lb', 'uf', 'lf', 'tb', 'sb', 'tf', 'sf', 'w')
STANCE = dict(hx=0.0, hy=-22.5, rot=0.0, mx=0.0,
              sp=-82, hd=-86,
              ub=40, lb=-55,        # back arm: guard near the chin
              uf=55, lf=-40,        # front arm: guard forward
              tb=105, sb=95,        # back leg
              tf=70, sf=100,        # front leg
              w=-60)                # weapon angle (when one is out)


def pose(base=None, **kw):
    p = dict(STANCE if base is None else base)
    p.update(kw)
    return p


def wrap180(a):
    a = (a + 180.0) % 360.0 - 180.0
    return a


EASE = {'lin': 0, 'in': 1, 'out': 2, 'inout': 3, 'back': 4, 'snap': 5, 'expo': 6}


def ease(kind, u):
    u = min(1.0, max(0.0, u))
    if kind == 'lin': return u
    if kind == 'in': return u * u
    if kind == 'out': return 1 - (1 - u) * (1 - u)
    if kind == 'inout': return u * u * (3 - 2 * u)
    if kind == 'back':                       # overshoot then settle
        c = 1.70158
        v = u - 1
        return 1 + (c + 1) * v * v * v + c * v * v
    if kind == 'snap': return 1.0 if u >= 1 else 0.0
    if kind == 'expo': return 1 - 2 ** (-10 * u) if u < 1 else 1.0
    return u


def lerp_pose(a, b, u):
    """angles take the short way round, except rot (full flips) and positions."""
    out = {}
    for k in a:
        if k in ('wk', 'gh', 'back_over') or k not in b:   # flags hold until the next key
            out[k] = a[k]
        elif k in ANGLES:
            out[k] = a[k] + wrap180(b[k] - a[k]) * u
        else:
            out[k] = a[k] + (b[k] - a[k]) * u
    return out


def sample(keys, t):
    """keys: [(t, pose, ease_into_this_key)] sorted by t."""
    if t <= keys[0][0]: return dict(keys[0][1])
    for (t0, p0, _), (t1, p1, e1) in zip(keys, keys[1:]):
        if t <= t1:
            u = (t - t0) / max(1e-6, t1 - t0)
            return lerp_pose(p0, p1, ease(e1, u))
    return dict(keys[-1][1])


def joints(p, x=0.0, y=0.0, f=1.0):
    """world positions of every joint. f = facing (+1 right, -1 left)."""
    r = p.get('rot', 0.0)
    def d(a):
        a = math.radians(a + r)
        return math.cos(a) * f, math.sin(a)
    hip = (x + p['hx'] * f + p.get('mx', 0) * f * 0, y + p['hy'])
    def add(o, a, l):
        dx, dy = d(a); return (o[0] + dx * l, o[1] + dy * l)
    neck = add(hip, p['sp'], L_SPINE)
    sh = add(hip, p['sp'], L_SPINE - SHOULDER_DROP)
    head = add(neck, p['hd'], L_NECK)
    eb = add(sh, p['ub'], L_UARM); hb = add(eb, p['lb'], L_FARM)
    ef = add(sh, p['uf'], L_UARM); hf = add(ef, p['lf'], L_FARM)
    kb = add(hip, p['tb'], L_THIGH); fb = add(kb, p['sb'], L_SHIN)
    kf = add(hip, p['tf'], L_THIGH); ff = add(kf, p['sf'], L_SHIN)
    return dict(hip=hip, neck=neck, sh=sh, head=head, eb=eb, hb=hb, ef=ef, hf=hf, kb=kb, fb=fb, kf=kf, ff=ff)


def lowest(p):
    j = joints(p)
    return max(j['fb'][1], j['ff'][1], j['hb'][1], j['hf'][1], j['head'][1] + HEAD_R)


def render(p, size=(96, 80), origin=(48, 74), scale=4, f=1.0, color=C_FILL, back=C_BACK, line=C_LINE,
           alpha=255, img=None):
    """preview render (supersampled lines with round caps, outlined, back limbs behind)."""
    W, H = size
    S = scale
    own = img is None
    if own:
        img = Image.new('RGBA', (W * S, H * S), (0, 0, 0, 0))
    j = joints(p, origin[0], origin[1], f)
    d = ImageDraw.Draw(img)
    def P(pt): return (pt[0] * S, pt[1] * S)
    def seg(a, b, w, col):
        d.line([P(a), P(b)], fill=col, width=max(1, int(round(w * S))))
        for q in (a, b):
            r = w * S / 2
            d.ellipse((P(q)[0] - r, P(q)[1] - r, P(q)[0] + r, P(q)[1] + r), fill=col)
    back_bones = [('sh', 'eb'), ('eb', 'hb'), ('hip', 'kb'), ('kb', 'fb')]
    front_bones = [('hip', 'kf'), ('kf', 'ff'), ('hip', 'neck'), ('sh', 'ef'), ('ef', 'hf')]
    if p.get('back_over'):
        back_bones, front_bones = [('hip', 'kb'), ('kb', 'fb')], [('hip', 'kf'), ('kf', 'ff'), ('hip', 'neck'), ('sh', 'ef'), ('ef', 'hf'), ('sh', 'eb'), ('eb', 'hb')]
    for layer, col in ((back_bones, back), (front_bones, color)):
        for a, b in layer:
            w = W_TORSO if (a, b) == ('hip', 'neck') else W_LIMB
            seg(j[a], j[b], w + 2 * W_OUT, line + (alpha,))
        if layer is front_bones:
            hx, hy = P(j['head']); r = (HEAD_R + W_OUT) * S
            d.ellipse((hx - r, hy - r, hx + r, hy + r), fill=line + (alpha,))
        for a, b in layer:
            w = W_TORSO if (a, b) == ('hip', 'neck') else W_LIMB
            seg(j[a], j[b], w, col + (alpha,))
        if layer is front_bones:
            hx, hy = P(j['head']); r = HEAD_R * S
            d.ellipse((hx - r, hy - r, hx + r, hy + r), fill=col + (alpha,))
    return img, j


if __name__ == '__main__':
    im, _ = render(STANCE)
    bg = Image.new('RGBA', im.size, (150, 170, 210, 255)); bg.alpha_composite(im)
    bg.save('/tmp/grey_stance.png'); print('ok')
