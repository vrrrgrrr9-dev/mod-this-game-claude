"""Black Holing Scyther - a fierce cosmic gamecock, drawn as pixel art from a 2D skeletal rig.

Anatomy follows a real fighting rooster: long scaled shanks that bend backward at the hock, big
spurs, feathered drumsticks, a muscular chest, long pointed hackle feathers flowing from the head
over the shoulders, saddle feathers, tall arching sickle tail feathers, a heavy brow over a glowing
eye, a hooked beak (can open for a battle cry), wattles and a tall jagged comb.  Plumage is cosmic
violet with starlight speckles; every part is cel-shaded automatically (key light from the front-top,
a cyan rim light from behind) and the silhouette gets a dark 1px outline.

The scythe is NOT drawn here: weapon.py renders it at 32 angles and the game draws it at the grip
point returned by render() (so it can spin, be thrown and twirl).  Frame: 128x120, feet at (64,106).
"""
import math
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

SS = 8                                   # supersampling for mask rasterisation
W, H = 128, 120
OX, OY = 64, 106
CROSS = ndi.generate_binary_structure(2, 1)

# ------------------------------------------------------------------------------------------
# materials: base / light (key) / shadow / rim (cosmic back-light) / line (internal outline)
# ------------------------------------------------------------------------------------------
def _m(base, light, shadow, rim, line):
    return dict(base=base + (255,), light=light + (255,), shadow=shadow + (255,), rim=rim + (255,), line=line + (255,))

PLUM   = _m((66, 42, 120), (112, 78, 186), (38, 22, 74), (110, 150, 240), (20, 10, 42))       # body plumage
PLUM_F = _m((40, 24, 78), (64, 42, 118), (24, 12, 50), (70, 104, 190), (14, 6, 32))         # far side
HACK   = _m((170, 88, 214), (232, 164, 250), (118, 52, 166), (196, 200, 255), (58, 18, 92))  # hackles: bright lilac
HACK2  = _m((196, 108, 230), (246, 196, 255), (138, 64, 184), (214, 214, 255), (66, 22, 104))
SADL   = _m((152, 74, 204), (220, 148, 246), (100, 42, 150), (180, 190, 255), (52, 16, 86))
COVT   = _m((72, 54, 150), (120, 100, 214), (40, 26, 92), (120, 160, 245), (20, 12, 54))      # wing coverts
PRIM   = _m((30, 26, 70), (66, 82, 170), (16, 12, 40), (90, 140, 230), (10, 6, 28))        # primaries
TAIL   = _m((24, 18, 54), (60, 52, 140), (12, 8, 32), (80, 120, 220), (8, 4, 22))
TAIL2  = _m((38, 24, 82), (90, 62, 176), (20, 12, 50), (100, 140, 230), (12, 6, 30))
COMB   = _m((198, 32, 96), (248, 92, 164), (130, 14, 62), (255, 176, 240), (72, 6, 38))
SKIN   = _m((168, 28, 86), (214, 70, 134), (112, 12, 56), (240, 140, 220), (62, 6, 34))
BEAK   = _m((180, 168, 214), (230, 222, 250), (118, 104, 160), (240, 236, 255), (44, 32, 74))
LEG    = _m((88, 78, 136), (140, 128, 196), (50, 42, 88), (130, 180, 250), (22, 18, 42))
LEG_F  = _m((56, 50, 94), (90, 82, 140), (32, 26, 58), (90, 150, 210), (16, 12, 32))
SPUR   = _m((214, 204, 244), (252, 248, 255), (150, 136, 196), (210, 150, 255), (48, 36, 80))
OUTLINE = (12, 6, 24, 255)
STAR = (240, 232, 255, 255)
TALON = (24, 18, 44, 255)
SHEEN = (70, 170, 236, 255)
SHEEN2 = (226, 120, 246, 255)
EYE_SOCK = (34, 8, 44, 255)
EYE_IRIS = (140, 240, 255, 255)
EYE_HOT = (240, 255, 255, 255)
EYE_PUP = (12, 4, 24, 255)
BROW = (40, 10, 34, 255)
SCAR = (236, 186, 226, 255)

# ------------------------------------------------------------------------------------------
# affine helpers (y down, positive angle = clockwise on screen)
# ------------------------------------------------------------------------------------------
def T(dx, dy):
    return np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1.0]])

def R(deg, about=(0, 0)):
    a = math.radians(deg); c, s = math.cos(a), math.sin(a); px, py = about
    return np.array([[c, -s, px - c * px + s * py], [s, c, py - s * px - c * py], [0, 0, 1.0]])

def Sc(sx, sy, about=(0, 0)):
    px, py = about
    return np.array([[sx, 0, px - sx * px], [0, sy, py - sy * py], [0, 0, 1.0]])

def ap(M, p):
    v = M @ np.array([p[0], p[1], 1.0]); return (float(v[0]), float(v[1]))

def apl(M, pts):
    return [ap(M, p) for p in pts]

def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

def bez(a, c, b, n=18):
    return [((1 - t) ** 2 * a[0] + 2 * (1 - t) * t * c[0] + t * t * b[0],
             (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * c[1] + t * t * b[1]) for t in np.linspace(0, 1, n)]

def shift(m, dx, dy):
    """out[y, x] = m[y - dy, x - dx] (zero filled)."""
    out = np.zeros_like(m)
    h, w = m.shape
    ys0, ys1 = max(0, dy), min(h, h + dy); xs0, xs1 = max(0, dx), min(w, w + dx)
    out[ys0:ys1, xs0:xs1] = m[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
    return out

def ik2(A, C, la, lb, bend=1):
    """2-bone IK: joint between A and C with bone lengths la, lb; bend=+1 puts the joint on the
    clockwise side of A->C (for a downward leg facing right = behind = the bird's hock)."""
    dx, dy = C[0] - A[0], C[1] - A[1]
    d = math.hypot(dx, dy)
    d = max(abs(la - lb) + 1e-3, min(la + lb - 1e-3, d))
    ux, uy = (dx / (math.hypot(dx, dy) or 1), dy / (math.hypot(dx, dy) or 1))
    ca = (la * la + d * d - lb * lb) / (2 * la * d)
    a = math.acos(max(-1.0, min(1.0, ca))) * bend
    c, s = math.cos(a), math.sin(a)
    return (A[0] + la * (ux * c - uy * s), A[1] + la * (ux * s + uy * c))


class Canvas:
    def __init__(self, w=W, h=H, ox=OX, oy=OY):
        self.w, self.h, self.ox, self.oy = w, h, ox, oy
        self.img = np.zeros((h, w, 4), np.uint8)
        self.sil = np.zeros((h, w), bool)
        self.big = Image.new('L', (w * SS, h * SS), 0)
        self.d = ImageDraw.Draw(self.big)

    def _p(self, p):
        return ((self.ox + p[0]) * SS, (self.oy + p[1]) * SS)

    def _clear(self):
        self.d.rectangle((0, 0, self.w * SS, self.h * SS), fill=0)

    def _bake(self, thr=120):
        return np.array(self.big.resize((self.w, self.h), Image.BOX)) >= thr

    # ---- shape masks (world px coords) ----
    def poly(self, pts):
        self._clear(); self.d.polygon([self._p(p) for p in pts], fill=255); return self._bake()

    def ell(self, c, rx, ry, rot=0, n=40):
        r = math.radians(rot); pts = []
        for i in range(n):
            a = 2 * math.pi * i / n; x, y = rx * math.cos(a), ry * math.sin(a)
            pts.append((c[0] + x * math.cos(r) - y * math.sin(r), c[1] + x * math.sin(r) + y * math.cos(r)))
        return self.poly(pts)

    def taper(self, pts, r0, r1, thr=120):
        self._clear()
        n = len(pts) - 1
        for k in range(n):
            a, b = pts[k], pts[k + 1]
            seg = math.hypot(b[0] - a[0], b[1] - a[1])
            steps = max(2, int(seg * SS / 3))
            for j in range(steps):
                t = j / steps; u = (k + t) / n
                x, y = self._p((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
                r = max(0.25, r0 + (r1 - r0) * u) * SS
                self.d.ellipse((x - r, y - r, x + r, y + r), fill=255)
        x, y = self._p(pts[-1]); r = max(0.25, r1) * SS
        self.d.ellipse((x - r, y - r, x + r, y + r), fill=255)
        return self._bake(thr)

    # ---- painting ----
    def paint(self, m, mat, shade=2, hl=1, rim=1, line=True, sil=True, glossy=False, bump=2.4):
        """fill a part with volumetric (normal-mapped) shading so the pixels read as 3D:
        the part's silhouette is inflated into a rounded surface (distance transform), lit by a key
        light from the upper front, a cosmic back rim light, optional specular; the result is
        quantised to the material's 5-tone ramp (keeps crisp pixel clusters).  The part also casts a
        soft contact shadow onto whatever it overlaps (depth separation), and gets an internal
        outline where it sits on top of something."""
        if not m.any():
            return
        painted = self.img[..., 3] > 0
        if line:
            ring = ndi.binary_dilation(m, CROSS) & ~m & painted
            self.img[ring] = mat['line']
        # contact shadow cast down-left onto parts below
        cast = shift(m, -1, 1) & ~m & painted
        if cast.any():
            self.img[cast, :3] = (self.img[cast, :3].astype(np.float32) * 0.8).astype(np.uint8)
        ramp = mat.get('ramp')
        if ramp is None:
            b, l, s = (np.array(mat[k][:3], np.float32) for k in ('base', 'light', 'shadow'))
            ramp = [np.clip(s * 0.72, 0, 255), s, b, l, np.clip(l * 1.12 + 22, 0, 255)]
            mat['ramp'] = ramp
        dt = ndi.distance_transform_edt(np.pad(m, 1))[1:-1, 1:-1]
        if dt.max() < 2.3:                            # thin part (feather, spike): crisp bands
            self.img[m] = mat['base']
            if shade:
                self.img[m & ~shift(m, 1, -1)] = mat['shadow']
            if hl:
                self.img[m & ~shift(m, -1, 1)] = mat['light']
            if rim:
                self.img[m & ~shift(m, 1, 1) & ~shift(m, 0, 1)] = mat['rim']
            if sil:
                self.sil |= m
            return
        R = max(1.6, min(6.5, float(dt.max())))
        hgt = np.sqrt(np.clip(dt / R, 0, 1))
        hgt = ndi.gaussian_filter(hgt, 0.7) * m
        gy, gx = np.gradient(hgt)
        nx, ny = -gx * bump, -gy * bump
        nz = 1.0 / np.sqrt(1 + nx * nx + ny * ny)
        nx, ny = nx * nz, ny * nz
        L = (0.55, -0.62, 0.56)                       # key light: upper front-right, toward viewer
        diff = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
        tone = 0.3 + diff * 1.0
        idx = np.digitize(tone, (0.46, 0.66, 0.9, 1.08))
        out = np.zeros(m.shape + (3,), np.float32)
        for k in range(5):
            out[idx == k] = ramp[k]
        if rim:
            rl = np.clip((nx * -0.86 + ny * -0.5), 0, 1) * (1 - nz)   # grazing back/top-left edges
            rmask = (rl > 0.32) & m
            out[rmask] = np.array(mat['rim'][:3], np.float32) * 0.85 + out[rmask] * 0.15
        if glossy:
            # Blinn-Phong highlight (half vector between light and viewer)
            hx, hy, hz = L[0], L[1], L[2] + 1
            hn = math.sqrt(hx * hx + hy * hy + hz * hz)
            sp = np.clip((nx * hx + ny * hy + nz * hz) / hn, 0, 1) ** 18
            out[(sp > 0.55) & m] = (255, 250, 255)
        self.img[m, :3] = out[m].astype(np.uint8)
        self.img[m, 3] = 255
        if sil:
            self.sil |= m

    def flat(self, m, color, sil=True):
        self.img[m] = color
        if sil:
            self.sil |= m

    def outline(self):
        o = ndi.binary_dilation(self.sil, CROSS) & ~self.sil
        self.img[o] = OUTLINE

    def image(self):
        return Image.fromarray(self.img, 'RGBA')


# ------------------------------------------------------------------------------------------
# rest-pose skeleton (world px; feet origin (0,0); facing +x; y down)
# ------------------------------------------------------------------------------------------
HIP = (-2.0, -24.0)            # drumstick top
LT, LS = 10.0, 15.5            # drumstick (tibiotarsus) and shank lengths
NB = (5.0, -37.5)              # neck base
HC = (12.5, -51.5)             # head centre
HEAD_K = 1.32                  # head drawn larger than life for readability
SH = (3.0, -37.0)              # wing shoulder
RUMP = (-14.0, -34.5)
BODYC = (-2.0, -32.0)          # body-rotation (flip) centre

BODY = [(9.5, -34.5), (10.8, -31.0), (10.2, -27.5), (7.6, -24.2), (3.6, -22.2), (-1.5, -21.6),
        (-6.5, -22.6), (-11.0, -25.2), (-14.4, -28.6), (-15.8, -32.4), (-14.8, -36.2), (-11.4, -38.8),
        (-6.0, -40.2), (0.0, -40.6), (4.6, -39.6), (8.0, -37.4)]
BREAST = [(10.4, -31.5), (10.0, -27.6), (7.2, -24.4), (3.4, -22.8), (2.0, -26.0), (5.0, -30.0), (8.0, -33.4)]

def _h(pts):      # head-relative -> absolute (rest)
    return [(HC[0] + x, HC[1] + y) for x, y in pts]

SKULL = _h([(-3.6, -1.4), (-2.6, -3.9), (0.0, -4.9), (3.0, -4.4), (4.6, -2.6), (4.6, 0.4), (2.8, 2.4), (-0.4, 2.6), (-3.0, 1.2)])
FACE = _h([(-0.8, -2.9), (3.4, -3.3), (4.7, -0.6), (3.6, 2.0), (0.6, 2.2), (-1.0, 0.6)])
EYE = _h([(1.8, -1.5)])[0]
BROW_P = _h([(-1.0, -2.9), (0.2, -4.0), (4.2, -3.1), (4.4, -2.1), (2.0, -2.3)])
BEAK_U = _h([(4.0, -2.6), (6.4, -2.4), (8.8, -1.2), (9.8, 0.4), (9.2, 2.1), (8.5, 1.1), (6.6, 0.2), (4.2, 0.2)])
BEAK_L = _h([(4.2, 0.4), (7.4, 0.7), (8.4, 1.0), (7.0, 2.0), (4.4, 1.5)])
BEAK_PIV = _h([(4.3, 0.3)])[0]
WATTLE_F = _h([(2.8, 1.4), (5.2, 1.4), (5.8, 3.8), (5.2, 6.4), (3.8, 7.2), (2.6, 6.0), (2.2, 3.4)])
WATTLE_B = _h([(1.0, 1.8), (2.6, 2.0), (2.8, 4.6), (1.8, 5.8), (0.8, 4.4)])
EARLOBE = _h([(-1.6, 0.2)])[0]
COMB_P = _h([(4.8, -3.8), (6.6, -8.4), (3.9, -6.9), (4.9, -11.9), (1.9, -8.1), (1.4, -13.4), (-0.9, -8.3),
             (-2.4, -12.8), (-3.9, -7.6), (-6.2, -11.0), (-5.6, -6.6), (-8.8, -8.2), (-6.8, -5.0),
             (-3.8, -4.3), (0.0, -4.9)])
COMB_SHADE = _h([(-3.9, -7.6), (-6.2, -11.0), (-5.6, -6.6), (-8.8, -8.2), (-6.8, -5.0), (-3.8, -4.3), (-1.0, -4.8)])
SCAR_P = _h([(0.4, -5.2), (3.2, 0.8)])

COVERTS = [(4.2, -37.6), (0.5, -38.6), (-5.5, -37.6), (-9.5, -34.6), (-10.4, -31.2), (-5.0, -29.4), (0.8, -30.2), (4.0, -33.4)]
SECOND = [(0.8, -30.2), (-5.0, -29.4), (-10.4, -31.2), (-13.6, -29.4), (-12.2, -26.4), (-5.0, -25.4), (0.6, -27.4)]

STARS = [(-8, -35), (-4, -27), (-11, -30), (1, -34), (-6, -31), (3, -29), (-13, -33), (-1, -38),
         (-20, -48), (-26, -44), (-29, -38), (-18, -53), (-23, -51)]

DEFAULT = dict(
    dx=0.0, dy=0.0,            # whole-character offset
    rot=0.0,                   # whole-body rotation about BODYC (flips)
    lean=0.0,                  # upper-body lean about the hip (+ = forward)
    crouch=0.0,                # hip drop (px)
    hip=(0.0, 0.0),            # hip shift
    footF=(4.0, 0.0), footB=(-7.0, 0.0),
    toeF=0.0, toeB=0.0,        # foot rotation (deg)
    neck=0.0,                  # neck rotation about its base (+ = forward/down)
    head=(0.0, 0.0, 0.0),      # head offset + tilt
    beak=0.0,                  # beak open (deg)
    tail=0.0,                  # tail rotation about the rump (+ = down)
    flow=0.0,                  # feather flow (+ = streaming back)
    wing='grip',               # near wing: 'fold' | 'grip' | 'raise'
    grip=(15.0, -33.0),        # hand position (world) for wing='grip'
    fwing='hide',              # far wing: 'hide' | 'raise'
    eye='angry',               # 'angry' | 'wide' | 'shut' | 'x' | 'glow'
    squash=1.0,                # horizontal squash about BODYC (spin frames)
    mirror=False,              # draw mirrored (spin frames facing back)
)


def build(pose):
    """Pose -> transforms and key points."""
    p = dict(DEFAULT); p.update(pose)
    G = T(p['dx'], p['dy']) @ Sc(p['squash'], 1.0, BODYC) @ R(p['rot'], BODYC)
    L = T(p['hip'][0], p['hip'][1] + p['crouch']) @ R(p['lean'], HIP)
    U = G @ L
    Hn = U @ R(p['neck'], NB)
    hx, hy, ht = p['head']
    Hm = Hn @ T(hx, hy) @ R(ht, HC) @ Sc(HEAD_K, HEAD_K, HC)
    Tm = U @ R(p['tail'], RUMP)
    return p, G, U, Hn, Hm, Tm


def draw_leg(c, U, G, foot, toe, far, p):
    mat_p = PLUM_F if far else PLUM
    mat_l = LEG_F if far else LEG
    hipw = ap(U, (HIP[0] + (-2.5 if far else 0.5), HIP[1] + 1.0))
    fw = ap(G, foot)
    hock = ik2(hipw, fw, LT, LS, bend=1)
    # feathered drumstick + fringe
    c.paint(c.taper([hipw, lerp(hipw, hock, 0.45), hock], 3.7, 1.5), mat_p, shade=2, hl=1, rim=0)
    # scaled shank (thin, with small scale marks on the front edge)
    shank = c.taper([hock, fw], 1.2, 1.0)
    c.paint(shank, mat_l, shade=1, hl=1, rim=0)
    dxs, dys = fw[0] - hock[0], fw[1] - hock[1]
    L = math.hypot(dxs, dys) or 1
    nx, ny = dys / L, -dxs / L                 # front normal
    for t in (0.3, 0.52, 0.74):
        q = lerp(hock, fw, t)
        mk = c.ell((q[0] + nx * 0.9, q[1] + ny * 0.9), 0.5, 0.5) & shank
        c.img[mk] = mat_l['shadow']
    # spur: on the back of the shank, pointing back/down
    sp0 = lerp(fw, hock, 0.30)
    ang = math.atan2(fw[1] - hock[1], fw[0] - hock[0]) + math.radians(95)
    sp1 = (sp0[0] + 4.0 * math.cos(ang), sp0[1] + 4.0 * math.sin(ang))
    sm = c.taper([sp0, lerp(sp0, sp1, 0.6), sp1], 0.95, 0.18)
    c.paint(sm, SPUR, shade=0, hl=1, rim=1)
    tipm = c.taper([lerp(sp0, sp1, 0.7), sp1], 0.4, 0.15) & sm
    c.img[tipm] = SPUR['rim']
    # toes: two forward toes, the hind toe, dark talons
    tr = math.radians(toe)
    for L, a in ((5.6, 0.0), (4.6, -12.0), (2.8, 180.0)):
        aa = tr + math.radians(a)
        tip = (fw[0] + L * math.cos(aa), fw[1] + L * math.sin(aa) - 0.2)
        tm = c.taper([fw, tip], 1.05, 0.55)
        c.paint(tm, mat_l, shade=0, hl=1, rim=0)
        tal = (tip[0] + 1.4 * math.cos(aa + 0.6), tip[1] + 1.4 * math.sin(aa + 0.6))
        c.flat(c.taper([tip, tal], 0.5, 0.2), TALON)
    return hock


def strand(c, a, ctrl, b, r0, r1, mat, sheen=None, rim=0, hl=0):
    pts = bez(a, ctrl, b, 14)
    m = c.taper(pts, r0, r1)
    c.paint(m, mat, shade=1, hl=hl, rim=rim)
    if sheen is not None:
        s = c.taper(pts[2:-3], max(0.3, r0 * 0.38), 0.2) & m
        c.img[s] = sheen
    return m


def draw_tail(c, Tm, p):
    f = p['flow']
    specs = [  # (base, ctrl, tip, r0, mat, sheen)
        ((-13.8, -34.6), (-25.0, -50.0), (-35.5 - f * 0.6, -33.0 + f * 0.5), 2.6, TAIL2, SHEEN),
        ((-13.2, -35.8), (-21.5, -59.0), (-35.0 - f * 0.8, -42.5 + f * 0.6), 2.9, TAIL, SHEEN),
        ((-12.6, -36.8), (-17.0, -63.5), (-31.0 - f, -50.0 + f * 0.8), 3.1, TAIL, SHEEN2),
        ((-12.4, -37.6), (-17.0, -49.0), (-25.5, -45.0 + f * 0.3), 2.8, TAIL2, None),
        ((-13.4, -36.0), (-20.0, -44.0), (-28.0, -37.5 + f * 0.3), 2.6, TAIL2, None),
    ]
    for a, ctl, b, r0, mat, sh in specs:
        strand(c, ap(Tm, a), ap(Tm, ctl), ap(Tm, b), r0, 0.4, mat, sheen=sh, rim=0, hl=1)
        # magenta starlight tip on the long sickles
        if sh is not None:
            tipm = c.taper([lerp(ap(Tm, ctl), ap(Tm, b), 0.82), ap(Tm, b)], 0.6, 0.3)
            c.img[tipm & (c.img[..., 3] > 0)] = (214, 120, 240, 255)


def draw_wing_fold(c, U, p, ang):
    Wf = U @ R(ang, SH)
    c.paint(c.poly(apl(Wf, SECOND)), PRIM, shade=1, hl=1, rim=1)
    for i in range(5):
        t = i / 4
        b = lerp((-8.0, -31.0), (-11.0, -29.6), t)
        tip = lerp((-17.5, -29.8), (-19.6, -27.0), t)
        tip = (tip[0] - p['flow'] * 0.4, tip[1])
        strand(c, ap(Wf, b), ap(Wf, lerp(b, tip, 0.5)), ap(Wf, tip), 1.3, 0.3, PRIM)
    c.paint(c.poly(apl(Wf, COVERTS)), COVT, shade=1, hl=1, rim=1)
    # covert feather scallops
    for q in ((-1.0, -33.6), (-5.0, -33.0), (-8.0, -32.2), (1.6, -35.6)):
        m = c.ell(ap(Wf, q), 2.0, 1.2, rot=-10) & c.poly(apl(Wf, COVERTS))
        c.img[m & ~shift(m, 0, -1)] = COVT['shadow']


def draw_wing_grip(c, U, G, p):
    sh = ap(U, SH)
    g = ap(G, p['grip'])
    # clamp reach
    dx, dy = g[0] - sh[0], g[1] - sh[1]
    d = math.hypot(dx, dy); reach = 15.5
    if d > reach:
        g = (sh[0] + dx / d * reach, sh[1] + dy / d * reach)
    el = ik2(sh, g, 7.5, 8.5, bend=1)          # elbow drops below the line
    # forearm secondaries hanging below the arm (feathered fringe)
    fx, fy = g[0] - el[0], g[1] - el[1]
    L = math.hypot(fx, fy) or 1
    nx, ny = -fy / L, fx / L                      # normal (one side)
    if ny < 0:
        nx, ny = -nx, -ny                         # make it point down
    fringe = [el, g, (g[0] + nx * 2.5, g[1] + ny * 2.5)]
    for t in (0.85, 0.65, 0.45, 0.25, 0.05):
        q = lerp(el, g, t)
        fringe.append((q[0] + nx * 5.2 - fx / L * 1.6, q[1] + ny * 5.2 - fy / L * 1.6))
        fringe.append((q[0] + nx * 3.2, q[1] + ny * 3.2))
    fringe.append((el[0] + nx * 3.0, el[1] + ny * 3.0))
    c.paint(c.poly(fringe), PRIM, shade=1, hl=1, rim=1)
    # upper wing (coverts) shoulder -> elbow, forearm -> wrist
    c.paint(c.taper([sh, lerp(sh, el, 0.5), el], 4.2, 3.0), COVT, shade=1, hl=1, rim=1)
    c.paint(c.taper([el, g], 2.8, 1.9), COVT, shade=1, hl=1, rim=1)
    # primaries fan behind the grip (the weapon sprite wraps feather-fingers over the haft)
    for k, (a, L2) in enumerate(((-30, 5.5), (0, 6.5), (28, 5.0))):
        ang = math.atan2(fy, fx) + math.radians(a)
        tip = (g[0] + L2 * math.cos(ang) * 0.6 + nx * 2.0, g[1] + L2 * math.sin(ang) * 0.6 + ny * 2.0)
        strand(c, g, lerp(g, tip, 0.5), tip, 1.2, 0.3, PRIM)
    return g


def draw_wing_raise(c, U, p, far=False):
    """wing thrown up and back, long primaries fanned (battle display / big swings)."""
    sh = ap(U, (SH[0] - (3 if far else 0), SH[1] - (1 if far else 0)))
    el = (sh[0] - 4, sh[1] - 8)
    wr = (sh[0] - 11, sh[1] - 14)
    matc = PLUM_F if far else COVT
    matp = PLUM_F if far else PRIM
    for i in range(7):                     # long primaries fanning up/back
        a = math.radians(-158 + i * 15)
        L2 = 15.5 - abs(i - 2) * 1.3
        tip = (wr[0] + L2 * math.cos(a), wr[1] + L2 * math.sin(a))
        strand(c, wr, lerp(wr, tip, 0.45), tip, 2.3, 0.45, matp, hl=1)
    for i in range(5):                     # secondaries hanging from the forearm
        q = lerp(el, wr, i / 4)
        tip = (q[0] - 5.5 - i, q[1] + 8.5 - i * 1.5)
        strand(c, q, lerp(q, tip, 0.5), tip, 2.2, 0.5, matp, hl=1)
    c.paint(c.taper([sh, el, wr], 3.8, 2.4), matc, shade=1, hl=1, rim=1)


EYE_STAMPS = {
    # (dx, dy) -> colour key; eye centre at (0, 0); facing right (beak side = +x)
    'angry': {(-2, -2): 'B', (-1, -2): 'B', (-1, -1): 'B', (0, -1): 'B', (1, -1): 'B', (1, 0): 'B', (2, 0): 'B',
              (-2, 0): 'S', (-1, 0): 'I', (0, 0): 'I', (-2, 1): 'S', (-1, 1): 'I', (0, 1): 'W', (1, 1): 'I',
              (2, 1): 'S', (-1, 2): 'S', (0, 2): 'S', (1, 2): 'S'},
    'wide':  {(-2, -2): 'B', (-1, -2): 'B', (0, -2): 'B', (1, -2): 'B',
              (-2, -1): 'S', (-1, -1): 'I', (0, -1): 'I', (1, -1): 'S', (-2, 0): 'S', (-1, 0): 'I', (0, 0): 'W',
              (1, 0): 'I', (2, 0): 'S', (-1, 1): 'S', (0, 1): 'I', (1, 1): 'S'},
    'shut':  {(-2, 0): 'B', (-1, 0): 'B', (0, 0): 'B', (1, 1): 'B', (2, 1): 'B', (-1, -1): 'B'},
    'x':     {(-1, -1): 'P', (1, -1): 'P', (0, 0): 'P', (-1, 1): 'P', (1, 1): 'P', (2, -2): 'P', (-2, 2): 'P'},
}
EYE_STAMPS['glow'] = dict(EYE_STAMPS['angry'])
EYE_STAMPS['glow'].update({(-3, 0): 'G', (-4, 0): 'G', (-5, -1): 'G', (-6, -1): 'g', (-3, 1): 'g'})
EYE_COL = dict(B=(30, 6, 30, 255), S=EYE_SOCK, I=EYE_IRIS, W=EYE_HOT, P=EYE_PUP, G=(170, 250, 255, 255), g=(110, 200, 255, 255))


def draw_head(c, Hm, p):
    e = p['eye']
    cm = c.poly(apl(Hm, COMB_P))
    c.paint(cm, COMB, shade=1, hl=1, rim=0)
    c.img[c.poly(apl(Hm, COMB_SHADE)) & cm] = COMB['shadow']
    c.paint(c.poly(apl(Hm, SKULL)), HACK, shade=1, hl=1, rim=1)
    c.paint(c.poly(apl(Hm, FACE)), SKIN, shade=1, hl=0, rim=0)
    c.paint(c.poly(apl(Hm, WATTLE_B)), SKIN, shade=1, hl=0, rim=0)
    # beak (lower mandible opens about its hinge)
    piv = ap(Hm, BEAK_PIV)
    Mb = R(p['beak'], piv)
    Mu = R(-p['beak'] * 0.35, piv)
    c.paint(c.poly(apl(Mb, apl(Hm, BEAK_L))), BEAK, shade=1, hl=0, rim=0)
    if p['beak'] > 6:                       # open mouth: dark gape + tongue
        gp = [piv, ap(Mu, ap(Hm, (HC[0] + 8.0, HC[1] + 0.4))), ap(Mb, ap(Hm, (HC[0] + 7.4, HC[1] + 1.0)))]
        c.flat(c.poly(gp), (54, 8, 36, 255))
    um = c.poly(apl(Mu, apl(Hm, BEAK_U)))
    c.paint(um, BEAK, shade=1, hl=1, rim=0)
    tip = c.ell(ap(Mu, ap(Hm, (HC[0] + 9.2, HC[1] + 1.4))), 1.1, 1.1) & um
    c.img[tip] = BEAK['line']
    c.paint(c.poly(apl(Hm, WATTLE_F)), SKIN, shade=1, hl=1, rim=0)
    # battle scar across the cheek (drawn before the eye so the eye stays clean)
    a, b = apl(Hm, SCAR_P)
    sc = c.taper([a, b], 0.35, 0.3)
    c.img[sc & (c.img[..., 3] > 0)] = SCAR
    # eye: hand-placed pixels (readable at 1x)
    ex, ey = ap(Hm, EYE)
    cx, cy = int(round(OX + ex)), int(round(OY + ey))
    for (dx, dy), k in EYE_STAMPS.get(e, EYE_STAMPS['angry']).items():
        x, y = cx + dx, cy + dy
        if 0 <= x < c.w and 0 <= y < c.h:
            c.img[y, x] = EYE_COL[k]


def draw_hackles(c, U, Hm, p, front):
    f = p['flow']
    if not front:
        for i in range(10):
            t = i / 9
            base = ap(Hm, lerp((9.4, -54.2), (5.6, -45.0), t))
            tip = ap(U, (lerp((3.4, -37.8), (-5.5, -36.6), t)[0] - f * 0.8, lerp((3.4, -37.8), (-5.5, -36.6), t)[1]))
            mid = lerp(base, tip, 0.5)
            ctrl = (mid[0] - 3.6 - f * 0.5, mid[1] - 0.8)
            strand(c, base, ctrl, tip, 1.9, 0.3, HACK if i % 2 else HACK2, rim=1)
    else:
        for i in range(5):
            t = i / 4
            base = ap(Hm, lerp((13.2, -47.2), (10.2, -44.6), t))
            tip = ap(U, lerp((10.6, -36.8), (7.4, -34.4), t))
            mid = lerp(base, tip, 0.5)
            strand(c, base, (mid[0] + 1.6, mid[1]), tip, 1.7, 0.35, HACK2 if i % 2 else HACK)


def draw_saddle(c, U, p):
    f = p['flow']
    for i in range(7):
        t = i / 6
        base = ap(U, lerp((-1.0, -40.2), (-9.5, -38.4), t))
        tip = ap(U, (lerp((-11.0, -31.4), (-16.6, -29.0), t)[0] - f * 0.6, lerp((-11.0, -31.4), (-16.6, -29.0), t)[1]))
        mid = lerp(base, tip, 0.5)
        strand(c, base, (mid[0] - 1.0, mid[1] - 1.6), tip, 1.8, 0.35, SADL if i % 2 else HACK, rim=1)


def draw_stars(c, U, Tm):
    for i, s in enumerate(STARS):
        q = ap(Tm if s[0] < -16 else U, s)
        x, y = int(round(OX + q[0])), int(round(OY + q[1]))
        if 0 <= x < W and 0 <= y < H and c.img[y, x, 3] > 0:
            v = c.img[y, x, :3].astype(int)
            if v.sum() < 330:                         # only on dark plumage
                c.img[y, x] = STAR


def render(pose):
    """-> (RGBA image W x H, grip point in frame px (x, y) or None)."""
    p, G, U, Hn, Hm, Tm = build(pose)
    c = Canvas()
    if p['fwing'] == 'raise':
        draw_wing_raise(c, U, p, far=True)
    draw_tail(c, Tm, p)
    draw_leg(c, U, G, p['footB'], p['toeB'], True, p)
    c.paint(c.poly(apl(U, BODY)), PLUM, shade=2, hl=1, rim=1)
    c.img[c.poly(apl(U, BREAST)) & (c.img[..., 3] > 0) & ~shift(c.poly(apl(U, BREAST)), 2, -2)] = PLUM['light']
    draw_saddle(c, U, p)
    draw_leg(c, U, G, p['footF'], p['toeF'], False, p)
    if p['wing'] == 'fold':
        draw_wing_fold(c, U, p, 0.0)
    elif p['wing'] == 'raise':
        draw_wing_raise(c, U, p)
    c.paint(c.taper([ap(U, NB), ap(Hm, HC)], 4.6, 3.6), HACK, shade=1, hl=1, rim=1)
    draw_hackles(c, U, Hm, p, front=False)
    draw_head(c, Hm, p)
    draw_hackles(c, U, Hm, p, front=True)
    draw_stars(c, U, Tm)
    grip = None
    if p['wing'] == 'grip':
        g = draw_wing_grip(c, U, G, p)
        grip = (OX + g[0], OY + g[1])
    c.outline()
    im = c.image()
    if p['mirror']:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
        if grip:
            grip = (W - grip[0], grip[1])
    return im, grip


if __name__ == '__main__':
    import sys
    im, g = render({})
    im.resize((W * 6, H * 6), Image.NEAREST).save(sys.argv[1] if len(sys.argv) > 1 else '/tmp/scy_rest.png')
    print('ok', im.size, 'grip', g)
