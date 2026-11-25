"""Jeff the anteater - pixel-art rig built from the original drawing (jeff_reference.jpg).

The drawing is segmented into its fill regions (head, eyes, body, tail, arms, feet) plus the
black bandana / mouth line.  Every animation frame is produced by moving those exact shapes
(rotate/translate/scale about joint pivots) and re-rendering them as crisp pixel art with
1px black outlines, matching the look of the game's 64x64 fighters (Erbito Black Rose).
"""
import math, os
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
FILL = (244, 244, 246, 255)      # body colour from the drawing (#f4f4f6)
SHADE = (214, 216, 224, 255)     # far-side limbs (tiny depth cue)
WHITE = (255, 255, 255, 255)
BLACK = (16, 16, 20, 255)

# the red-power form: the same drawing gone black, with glowing white eyes ringed in yellow and a
# white tag with two black buttons on the chest (the user's "dark Jeff" drawing)
DARK = dict(head=(33, 33, 36, 255), limb=(23, 23, 26, 255), shade=(15, 15, 18, 255), torso=(11, 11, 13, 255),
            line=(0, 0, 0, 255), eye=(255, 255, 255, 255), glow=(238, 244, 26, 255), glow2=(96, 100, 16, 255),
            trail=(255, 186, 70, 255), trail2=(236, 92, 26, 255))
CHEST = (526, 975)        # centre of the chest tag (drawing coordinates)

# --- segmentation -----------------------------------------------------------------------
_ref = np.array(Image.open(os.path.join(HERE, 'jeff_reference.jpg')).convert('L')).astype(np.int16)
_black = _ref < 110
_lab, _n = ndi.label(~_black)

def _find(cx, cy):
    return _lab[cy, cx]

# label ids picked by a point inside each region of the drawing
_ids = dict(head=_find(600, 450), eyeL=_find(436, 700), eyeR=_find(672, 680), body=_find(520, 990),
            tail=_find(250, 930), armB=_find(330, 970), armF=_find(690, 960), footB=_find(450, 1135),
            footF=_find(620, 1118))
assert len(set(_ids.values())) == len(_ids), _ids

def _mask(name):
    m = ndi.binary_fill_holes(_lab == _ids[name])
    # regions are separated by ~13px lines; grow each region to the middle of its outline so
    # neighbouring parts touch, exactly like the drawing's silhouette.
    return ndi.binary_dilation(m, iterations=6)

PARTS = {k: _mask(k) for k in _ids}
# bandana = thick black area under the head (erode away thin outlines, grow back)
_thick = ndi.binary_erosion(_black, iterations=9)
_thick = ndi.binary_dilation(_thick, iterations=9) & _black
_yy, _xx = np.mgrid[0:_ref.shape[0], 0:_ref.shape[1]]
PARTS['bandana'] = _thick & (_yy > 820) & (_yy < 1000) & (_xx > 360) & (_xx < 700)
# the eye shapes include their white fill; the head is drawn underneath
PIVOT = dict(  # joint pivots in drawing coordinates
    root=(530, 1172),      # between the feet, on the ground
    neck=(520, 852),
    tail=(395, 1040),
    armB=(372, 915),       # back (viewer-left) shoulder
    armF=(654, 915),       # front (viewer-right) shoulder
    footB=(452, 1100),
    footF=(622, 1088),
    hip=(520, 1080),
)
MOUTH = [(578, 829), (600, 836), (622, 842), (645, 846)]
KNOT = [((372, 846), (334, 845)), ((372, 852), (336, 866))]

def _bbox(m):
    ys, xs = np.nonzero(m)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1

_CROPS = {}
for k, m in PARTS.items():
    x0, y0, x1, y1 = _bbox(m)
    _CROPS[k] = (x0, y0, Image.fromarray((m[y0:y1, x0:x1] * 255).astype(np.uint8)))

# --- geometry helpers -------------------------------------------------------------------
def rot(deg, about=(0, 0)):
    a = math.radians(deg); c, s = math.cos(a), math.sin(a); px, py = about
    return np.array([[c, -s, px - c * px + s * py], [s, c, py - s * px - c * py], [0, 0, 1.0]])

def trans(dx, dy):
    return np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1.0]])

def scl(sx, sy, about=(0, 0)):
    px, py = about
    return np.array([[sx, 0, px - sx * px], [0, sy, py - sy * py], [0, 0, 1.0]])

def apply(M, pt):
    v = M @ np.array([pt[0], pt[1], 1.0]); return (v[0], v[1])

class Canvas:
    """Supersampled pixel-art compositor: parts are rasterised as binary masks at 1x and
    outlined with 1px of black (outline drawn outside the shape, 4-connected)."""
    SS = 6

    def __init__(self, w, h, ox, oy, scale, line=BLACK):
        self.w, self.h, self.ox, self.oy, self.s = w, h, ox, oy, scale
        self.outline = line
        self.img = np.zeros((h, w, 4), np.uint8)
        self.world = None   # world (drawing) -> pixel matrix, set by begin()

    def begin(self, root_shift=(0, 0), root_rot=0.0):
        r = PIVOT['root']
        # drawing coords -> target pixels; the root pivot maps to (ox, oy)
        M = trans(self.ox, self.oy) @ scl(self.s, self.s) @ trans(-r[0], -r[1])
        M = M @ trans(root_shift[0], root_shift[1]) @ rot(root_rot, r)
        self.world = M

    def mask_from_crop(self, name, M):
        x0, y0, im = _CROPS[name]
        F = self.world @ M @ trans(x0, y0)          # crop pixel -> target pixel
        S = scl(self.SS, self.SS) @ F               # -> supersampled target
        inv = np.linalg.inv(S)
        big = im.transform((self.w * self.SS, self.h * self.SS), Image.AFFINE,
                           data=tuple(inv[:2].ravel()), resample=Image.NEAREST)
        small = np.array(big.resize((self.w, self.h), Image.BOX))
        return small >= 128

    def mask_from_poly(self, pts_world, M=np.eye(3), width=None, closed=True):
        S = scl(self.SS, self.SS) @ self.world @ M
        P = [apply(S, p) for p in pts_world]
        big = Image.new('L', (self.w * self.SS, self.h * self.SS), 0)
        d = ImageDraw.Draw(big)
        if width:
            d.line(P, fill=255, width=max(1, int(width * self.SS * self.s)), joint='curve')
            for p in (P[0], P[-1]):
                r = width * self.SS * self.s / 2
                d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=255)
        else:
            d.polygon(P, fill=255)
        small = np.array(big.resize((self.w, self.h), Image.BOX))
        return small >= 128

    def mask_capsule(self, a, b, r_a, r_b, M=np.eye(3)):
        """tapered capsule in drawing units (for stretched punching arms)."""
        S = scl(self.SS, self.SS) @ self.world @ M
        A, B = apply(S, a), apply(S, b)
        k = self.SS * self.s
        big = Image.new('L', (self.w * self.SS, self.h * self.SS), 0)
        d = ImageDraw.Draw(big)
        n = 24
        for i in range(n + 1):
            t = i / n
            x = A[0] + (B[0] - A[0]) * t; y = A[1] + (B[1] - A[1]) * t
            r = (r_a + (r_b - r_a) * t) * k
            d.ellipse((x - r, y - r, x + r, y + r), fill=255)
        small = np.array(big.resize((self.w, self.h), Image.BOX))
        return small >= 128

    def put(self, m, color=FILL, outline=True):
        if not m.any():
            return
        if outline:
            o = ndi.binary_dilation(m, structure=ndi.generate_binary_structure(2, 1)) & ~m
            self.img[o] = self.outline
        self.img[m] = color

    def line(self, pts_world, M=np.eye(3), color=BLACK):
        P = [apply(self.world @ M, p) for p in pts_world]
        im = Image.fromarray(self.img)
        ImageDraw.Draw(im).line(P, fill=color, width=1)
        self.img = np.array(im)

    def pixel_line(self, a, b, color=BLACK):
        im = Image.fromarray(self.img)
        ImageDraw.Draw(im).line([a, b], fill=color, width=1)
        self.img = np.array(im)

    def image(self):
        return Image.fromarray(self.img, 'RGBA')

# --- posing ------------------------------------------------------------------------------
DEFAULT = dict(dx=0, dy=0, rot=0, sy=1.0,
               head=(0, 0, 0), tail=(0, 0, 0), footB=(0, 0, 0), footF=(0, 0, 0),
               armB=('stub', 0, 0, 0), armF=('stub', 0, 0, 0),
               eyes='open', front_arm_over=False, back_arm_over=False, blush=False, kickF=None, kickB=None)

def _dark_eye(c, m, mode):
    """the dark form's eye: white, its top cut off by a slanted line (rising toward the snout),
    ringed by a bright yellow glow and a dim one (kept inside the silhouette)."""
    ys, xs = np.nonzero(m)
    if not len(xs):
        return
    inside = c.img[..., 3] > 0
    four = ndi.generate_binary_structure(2, 1)
    if mode in ('open', 'angry'):
        # a wide oval with a flat, slanted top and a round bottom (supersampled, then thresholded)
        k = c.s / 0.0625
        cx, cy = xs.mean() + 0.5, ys.mean() + 0.9 * k
        rx, ry = 4.6 * k, 4.7 * k
        top, slope = (2.3 * k, 0.16) if mode == 'open' else (1.6 * k, 0.22)
        n = 8
        yy, xx = np.mgrid[0:c.h * n, 0:c.w * n]
        fx_, fy_ = (xx + 0.5) / n, (yy + 0.5) / n
        big = (((fx_ - cx) / rx) ** 2 + ((fy_ - cy) / ry) ** 2 <= 1) & (fy_ >= cy - top - slope * (fx_ - cx))
        e = big.reshape(c.h, n, c.w, n).mean(axis=(1, 3)) >= 0.5
    else:                                   # squint / knocked out: a glowing slit or cross
        e = np.zeros_like(m)
        cx, cy = int(round(xs.mean())), int(round(ys.mean()))
        if mode == 'x':
            for k in range(-2, 3):
                for px, py in ((cx + k, cy + k), (cx + k, cy - k)):
                    if 0 <= px < c.w and 0 <= py < c.h: e[py, px] = True
        else:
            for k in range(-3, 4):
                py = cy - (1 if k > 1 else 0)
                if 0 <= cx + k < c.w and 0 <= py < c.h: e[py, cx + k] = True
    r1 = ndi.binary_dilation(e, structure=four) & ~e & inside
    r2 = ndi.binary_dilation(e, iterations=2) & ~e & ~r1 & inside
    c.img[r2] = DARK['glow2']
    c.img[r1] = DARK['glow']
    c.img[e] = DARK['eye']


def _chest_tag(c, M):
    """3x5 white tag with two black buttons, outlined in black."""
    px, py = apply(c.world @ M, CHEST)
    x0, y0 = int(round(px)) - 1, int(round(py)) - 2
    for y in range(y0 - 1, y0 + 6):
        for x in range(x0 - 1, x0 + 4):
            if not (0 <= x < c.w and 0 <= y < c.h):
                continue
            edge = y in (y0 - 1, y0 + 5) or x in (x0 - 1, x0 + 3)
            dot = x == x0 + 1 and y in (y0 + 1, y0 + 3)
            c.img[y, x] = DARK['line'] if edge or dot else DARK['eye']


def render(pose, w=64, h=64, ox=32, oy=63, scale=0.0625, fx=None, style='white'):
    """pose keys (drawing units, 16 units = 1px at default scale):
    dx,dy,rot  whole-character offset / rotation about the feet
    sy         body squash (crouch) about the feet - head/arms/tail ride along, not squashed
    head/tail/footB/footF = (dx, dy, angle) about their pivots
    armB/armF  = ('stub', dx, dy, angle) or ('fist', x, y, fist_r, base_r[, dx, dy]) capsule to a fist
    eyes       'open' | 'squint' | 'x' | 'angry'
    *_over     draw that arm in front of body/head (punches, guard)
    fx         callback(canvas, world_matrix) to draw effect pixels on top
    """
    p = dict(DEFAULT); p.update(pose)
    dark = style == 'dark'
    LINE = DARK['line'] if dark else BLACK
    LIMB = DARK['limb'] if dark else FILL
    c = Canvas(w, h, ox, oy, scale, LINE)
    c.begin((p['dx'], p['dy']), p['rot'])
    root = PIVOT['root']
    body = scl(1.0, p['sy'], root)
    def carried(pivot):
        q = apply(body, PIVOT[pivot]); return trans(q[0] - PIVOT[pivot][0], q[1] - PIVOT[pivot][1])
    def part_m(name, spec, ride=True):
        dx, dy, a = spec
        base = carried(name) if ride else np.eye(3)
        return base @ trans(dx, dy) @ rot(a, PIVOT[name])

    def arm(name, spec):
        kind = spec[0]
        if kind == 'stub':
            _, dx, dy, a = spec
            return c.mask_from_crop(name, part_m(name, (dx, dy, a)))
        _, tx, ty, fr, br = spec[:5]
        sdx, sdy = (spec[5], spec[6]) if len(spec) > 6 else (0, 0)
        sh = apply(carried(name) @ trans(sdx, sdy), PIVOT[name])
        return c.mask_capsule(sh, (tx, ty), br, fr)

    shade_back = DARK['shade'] if dark else SHADE
    c.put(c.mask_from_crop('tail', part_m('tail', p['tail'])), LIMB)
    def foot(name, spec, kick, color):
        if kick:                                     # a kick: a leg from the hip out to the foot
            fx_, fy_, fa = kick
            hip = apply(carried('hip'), PIVOT['hip'])
            hip = (hip[0] + (40 if name == 'footF' else -30), hip[1] - 20)
            c.put(c.mask_capsule(hip, (fx_, fy_), 40, 32), color)
            x0, y0, im = _CROPS[name]
            cx, cy = x0 + im.width / 2, y0 + im.height / 2
            c.put(c.mask_from_crop(name, trans(fx_ - cx, fy_ - cy) @ rot(fa, (cx, cy))), color)
        else:
            c.put(c.mask_from_crop(name, part_m(name, spec, ride=False)), color)

    foot('footB', p['footB'], p['kickB'], shade_back)
    if not p['back_arm_over']:
        c.put(arm('armB', p['armB']), shade_back)
    if not p['front_arm_over']:
        c.put(arm('armF', p['armF']), LIMB)
    c.put(c.mask_from_crop('body', body), DARK['torso'] if dark else FILL)
    foot('footF', p['footF'], p['kickF'], LIMB)
    hx, hy, ha = p['head']
    headM = carried('neck') @ trans(hx, hy) @ rot(ha, PIVOT['neck'])
    c.put(c.mask_from_crop('head', headM), DARK['head'] if dark else FILL)
    eye = p['eyes']
    for e in ('eyeL', 'eyeR'):
        m = c.mask_from_crop(e, headM)
        if dark:
            _dark_eye(c, m, eye)
            continue
        if eye == 'open':
            c.put(m, WHITE)
            continue
        ys, xs = np.nonzero(m)
        if not len(xs):
            continue
        cx, cy = int(round(xs.mean())), int(round(ys.mean()))
        if eye == 'x':
            c.pixel_line((cx - 2, cy - 2), (cx + 2, cy + 2)); c.pixel_line((cx - 2, cy + 2), (cx + 2, cy - 2))
        elif eye == 'angry':      # open eye with a heavy brow line cutting the top
            c.put(m, WHITE)
            c.pixel_line((xs.min() - 1, ys.min() - 1), (xs.max() + 1, ys.min() + 2))
            c.pixel_line((xs.min() - 1, ys.min()), (xs.max() + 1, ys.min() + 3))
        else:
            c.pixel_line((cx - 3, cy), (cx + 3, cy - 1))
    c.line(MOUTH, headM, LINE)
    neckM = carried('neck') @ trans(hx * 0.35, hy * 0.6)
    c.put(c.mask_from_crop('bandana', neckM @ np.linalg.inv(carried('neck')) @ body), LINE, outline=False)
    for a, b in KNOT:
        c.line([a, b], neckM, LINE)
    if dark:
        _chest_tag(c, body)
    if p['back_arm_over']:
        c.put(arm('armB', p['armB']), LIMB)
    if p['front_arm_over']:
        c.put(arm('armF', p['armF']), LIMB)
    if fx:
        fx(c)
        if dark:                                       # motion lines burn orange in the red form
            for src, dst in (((235, 240, 255), DARK['trail']), ((170, 190, 255), DARK['trail2'])):
                k = (c.img[..., 0] == src[0]) & (c.img[..., 1] == src[1]) & (c.img[..., 2] == src[2])
                c.img[k] = dst
    return c.image()

ARM_TIP = dict(armF=(736, 994), armB=(288, 1006))     # hand end of the drawing's arm shapes
EYE_C = dict(eyeL=(436, 712), eyeR=(672, 692))        # eye centres (a bit low: the dark eyes are cut on top)


def points(pose, ox, oy, scale=0.0625):
    """pixel positions (relative to the feet) of both hands and the kicking foot, and each arm's
    screen angle (degrees, atan2 with y down) from shoulder to hand."""
    p = dict(DEFAULT); p.update(pose)
    r = PIVOT['root']
    M = trans(ox, oy) @ scl(scale, scale) @ trans(-r[0], -r[1]) @ trans(p['dx'], p['dy']) @ rot(p['rot'], r)
    body = scl(1.0, p['sy'], r)

    def carried(pivot):
        q = apply(body, PIVOT[pivot]); return trans(q[0] - PIVOT[pivot][0], q[1] - PIVOT[pivot][1])

    def px(pt):
        x, y = apply(M, pt); return (x - ox, y - oy)
    out = {}
    for k in ('armF', 'armB'):
        spec = p[k]
        if spec[0] == 'fist':
            sdx, sdy = (spec[5], spec[6]) if len(spec) > 6 else (0, 0)
            sh = apply(carried(k) @ trans(sdx, sdy), PIVOT[k]); hand = (spec[1], spec[2])
        else:
            _, dx, dy, a = spec
            Mk = carried(k) @ trans(dx, dy) @ rot(a, PIVOT[k])
            sh = apply(Mk, PIVOT[k]); hand = apply(Mk, ARM_TIP[k])
        hx, hy = px(hand); sx, sy = px(sh)
        out[k] = (hx, hy)
        out[k + '_a'] = math.degrees(math.atan2(hy - sy, hx - sx))
    for k in ('kickF', 'kickB'):
        if p[k]:
            out[k] = px((p[k][0], p[k][1]))
    hx, hy, ha = p['head']
    headM = carried('neck') @ trans(hx, hy) @ rot(ha, PIVOT['neck'])
    out['eyeL'] = px(apply(headM, EYE_C['eyeL']))
    out['eyeR'] = px(apply(headM, EYE_C['eyeR']))
    out['eyes_open'] = p['eyes'] in ('open', 'angry')
    return out


if __name__ == '__main__':
    im = render({})
    im.resize((im.width * 8, im.height * 8), Image.NEAREST).save('/tmp/jeff_idle_x8.png')
    print('ok', im.size)
