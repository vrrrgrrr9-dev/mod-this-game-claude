"""Black Holing Scyther - a fierce cosmic gamecock, drawn as pixel art from a 2D skeletal rig.

Anatomy follows a real fighting rooster: long scaled shanks that bend backward at the hock, big
spurs, feathered drumsticks, a muscular chest, long pointed hackle feathers flowing from the head
over the shoulders, saddle feathers, tall arching sickle tail feathers, a heavy brow over a glowing
eye, a hooked beak (can open for a battle cry), wattles and a tall jagged comb.  Plumage is cosmic
violet with starlight speckles; every part is cel-shaded automatically (key light from the front-top,
a cyan rim light from behind) and the silhouette gets a dark 1px outline.

The scythe is NOT drawn here: weapon.py renders it at 32 angles and the game draws it at the grip
point returned by render() (so it can spin, be thrown and twirl).

Rendered at 2x pixel density (K = 2): the game's camera view is 600x300 but it renders to a
1200x600 surface, so the game draws Scyther at half scale and every one of these pixels reaches the
screen - twice the detail of the 1x fighters.  World coordinates stay in 1x units.
Frame: 256x240, feet at (128,212).
"""
import math
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

SS = 6                                   # supersampling for mask rasterisation
K = 2                                    # render scale (pixels per world unit)
W, H = 128 * K, 120 * K
OX, OY = 64 * K, 106 * K
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
    def __init__(self, w=W, h=H, ox=OX, oy=OY, k=K):
        self.w, self.h, self.ox, self.oy, self.k = w, h, ox, oy, k
        self.img = np.zeros((h, w, 4), np.uint8)
        self.sil = np.zeros((h, w), bool)
        self.big = Image.new('L', (w * SS, h * SS), 0)
        self.d = ImageDraw.Draw(self.big)

    def _p(self, p):
        return ((self.ox + p[0] * self.k) * SS, (self.oy + p[1] * self.k) * SS)

    def px(self, p):
        """world -> integer pixel coords."""
        return int(round(self.ox + p[0] * self.k)), int(round(self.oy + p[1] * self.k))

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
            seg = math.hypot(b[0] - a[0], b[1] - a[1]) * self.k
            steps = max(2, int(seg * SS / 3))
            for j in range(steps):
                t = j / steps; u = (k + t) / n
                x, y = self._p((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
                r = max(0.25, r0 + (r1 - r0) * u) * SS * self.k
                self.d.ellipse((x - r, y - r, x + r, y + r), fill=255)
        x, y = self._p(pts[-1]); r = max(0.25, r1) * SS * self.k
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
        cast = (shift(m, -1, 1) | shift(m, -self.k, self.k)) & ~m & painted
        if cast.any():
            self.img[cast, :3] = (self.img[cast, :3].astype(np.float32) * 0.8).astype(np.uint8)
        ramp = mat.get('ramp')
        if ramp is None:
            b, l, s = (np.array(mat[k][:3], np.float32) for k in ('base', 'light', 'shadow'))
            ramp = [np.clip(s * 0.72, 0, 255), s, b, l, np.clip(l * 1.12 + 22, 0, 255)]
            mat['ramp'] = ramp
        dt = ndi.distance_transform_edt(np.pad(m, 1))[1:-1, 1:-1]
        if dt.max() < 1.6 * self.k:                   # thin part (feather, spike): crisp bands
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
        R = max(1.6, min(6.5 * self.k, float(dt.max())))
        hgt = np.sqrt(np.clip(dt / R, 0, 1))
        hgt = ndi.gaussian_filter(hgt, 0.7 * self.k) * m
        gy, gx = np.gradient(hgt)
        nx, ny = -gx * bump * self.k, -gy * bump * self.k
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
    # feathered drumstick with a fringe of pointed feathers over the hock
    c.paint(c.taper([hipw, lerp(hipw, hock, 0.45), hock], 3.7, 1.5), mat_p, shade=2, hl=1, rim=0)
    for t, off in ((0.62, -1.4), (0.74, 0.2), (0.86, 1.4)):
        q = lerp(hipw, hock, t)
        tip = (q[0] + off - 1.2, q[1] + 3.4)
        strand(c, q, lerp(q, tip, 0.5), tip, 0.9, 0.2, mat_p, rachis=False)
    # scaled shank: transverse scutes down the front, a light edge
    shank = c.taper([hock, fw], 1.2, 1.0)
    c.paint(shank, mat_l, shade=1, hl=1, rim=0)
    dxs, dys = fw[0] - hock[0], fw[1] - hock[1]
    L = math.hypot(dxs, dys) or 1
    nx, ny = dys / L, -dxs / L                 # front normal
    for i, t in enumerate(np.linspace(0.12, 0.9, 8)):
        q = lerp(hock, fw, t)
        a = (q[0] + nx * 0.05, q[1] + ny * 0.05)
        b = (q[0] + nx * 1.1 + (dxs / L) * 0.35, q[1] + ny * 1.1 + (dys / L) * 0.35)
        c.img[c.taper([a, b], 0.18, 0.18) & shank] = mat_l['shadow'] if i % 2 == 0 else mat_l['line']
    # spur: on the back of the shank, pointing back/down, glowing tip
    sp0 = lerp(fw, hock, 0.30)
    ang = math.atan2(fw[1] - hock[1], fw[0] - hock[0]) + math.radians(95)
    sp1 = (sp0[0] + 4.2 * math.cos(ang), sp0[1] + 4.2 * math.sin(ang))
    sm = c.taper([sp0, lerp(sp0, sp1, 0.6), sp1], 1.0, 0.16)
    c.paint(sm, SPUR, shade=1, hl=1, rim=0)
    c.img[c.taper([lerp(sp0, sp1, 0.62), sp1], 0.45, 0.15) & sm] = SPUR['rim']
    # toes with scale rings, dark curved talons with a glint
    tr = math.radians(toe)
    for L2, a in ((5.6, 0.0), (4.6, -12.0), (2.8, 180.0)):
        aa = tr + math.radians(a)
        tip = (fw[0] + L2 * math.cos(aa), fw[1] + L2 * math.sin(aa) - 0.2)
        tm = c.taper([fw, tip], 1.05, 0.55)
        c.paint(tm, mat_l, shade=0, hl=1, rim=0)
        for tt in (0.4, 0.72):
            q = lerp(fw, tip, tt)
            c.img[c.taper([(q[0], q[1] - 0.6), (q[0] + 0.2, q[1] + 0.6)], 0.16, 0.16) & tm] = mat_l['shadow']
        tal = (tip[0] + 1.5 * math.cos(aa + 0.6), tip[1] + 1.5 * math.sin(aa + 0.6))
        c.flat(c.taper([tip, lerp(tip, tal, 0.5), tal], 0.55, 0.15), TALON)
        x, y = c.px(lerp(tip, tal, 0.35))
        if 0 <= x < c.w and 0 <= y < c.h:
            c.img[y, x] = (120, 100, 170, 255)
    return hock


def strand(c, a, ctrl, b, r0, r1, mat, sheen=None, rim=0, hl=0, rachis=True, tip=True):
    """one feather: tapered stroke along a curve, quill line down its centre, lighter tip."""
    pts = bez(a, ctrl, b, 16)
    m = c.taper(pts, r0, r1)
    c.paint(m, mat, shade=1, hl=hl, rim=rim)
    if sheen is not None:
        s = c.taper(pts[2:-3], max(0.3, r0 * 0.38), 0.2) & m
        c.img[s] = sheen
    if rachis and r0 >= 1.3:
        c.img[c.taper(pts[1:-4], 0.2, 0.14) & m] = mat['line'] if r0 >= 2.2 else mat['shadow']
    if tip and r0 >= 1.0:
        c.img[c.taper(pts[-4:], max(0.25, r1 + 0.15), 0.12) & m] = mat['light']
    return m


def draw_tail(c, Tm, p):
    f = p['flow']
    specs = [  # (base, ctrl, tip, r0, mat, sheen)
        ((-13.6, -34.2), (-23.0, -42.0), (-30.0 - f * 0.4, -27.5 + f * 0.3), 2.2, TAIL2, None),
        ((-13.8, -34.6), (-25.0, -50.0), (-35.5 - f * 0.6, -33.0 + f * 0.5), 2.6, TAIL2, SHEEN),
        ((-13.2, -35.8), (-21.5, -59.0), (-35.0 - f * 0.8, -42.5 + f * 0.6), 2.9, TAIL, SHEEN),
        ((-12.6, -36.8), (-17.0, -63.5), (-31.0 - f, -50.0 + f * 0.8), 3.1, TAIL, SHEEN2),
        ((-12.2, -37.4), (-15.5, -55.0), (-24.0 - f * 0.7, -52.0 + f * 0.6), 2.4, TAIL2, None),
        ((-12.4, -37.6), (-17.0, -49.0), (-25.5, -45.0 + f * 0.3), 2.8, TAIL2, None),
        ((-13.4, -36.0), (-20.0, -44.0), (-28.0, -37.5 + f * 0.3), 2.6, TAIL2, None),
    ]
    for a, ctl, b, r0, mat, sh in specs:
        strand(c, ap(Tm, a), ap(Tm, ctl), ap(Tm, b), r0, 0.4, mat, sheen=sh, rim=0, hl=1)
        if sh is not None:                    # magenta starlight tip on the long sickles
            tipm = c.taper([lerp(ap(Tm, ctl), ap(Tm, b), 0.82), ap(Tm, b)], 0.65, 0.3)
            c.img[tipm & (c.img[..., 3] > 0)] = (214, 120, 240, 255)
    # short coverts over the base of the tail
    for i in range(5):
        t = i / 4
        b0 = ap(Tm, lerp((-11.5, -38.2), (-14.6, -33.6), t))
        tp = ap(Tm, (lerp((-19.0, -43.0), (-21.0, -33.0), t)[0] - f * 0.3, lerp((-19.0, -43.0), (-21.0, -33.0), t)[1]))
        strand(c, b0, (lerp(b0, tp, 0.5)[0], lerp(b0, tp, 0.5)[1] - 1.2), tp, 1.7, 0.3, SADL if i % 2 else HACK, hl=1)


def scallops(c, M, region, rows, mat, x0=-12.0, x1=9.0, y0=-38.0, dy=3.4, dx=3.2, r=1.3, col='shadow'):
    """rows of feather edges (small U arcs) inside `region` (mask), in part-local coords via M."""
    for rr in range(rows):
        y = y0 + rr * dy
        x = x0 + (rr % 2) * dx * 0.5
        while x <= x1:
            arc = apl(M, [(x - r, y - 0.25), (x - r * 0.45, y + r * 0.6), (x + r * 0.45, y + r * 0.6), (x + r, y - 0.25)])
            m = c.taper(arc, 0.22, 0.22) & region
            c.img[m] = mat[col]
            x += dx


def draw_wing_fold(c, U, p, ang):
    Wf = U @ R(ang, SH)
    sec = c.poly(apl(Wf, SECOND))
    c.paint(sec, PRIM, shade=1, hl=1, rim=1)
    for i in range(6):                       # secondary feather separations
        t = i / 5
        a = lerp((0.2, -29.8), (-12.0, -29.8), t)
        b = (a[0] - 1.2, a[1] + 3.6)
        c.img[c.taper(apl(Wf, [a, b]), 0.18, 0.16) & sec] = PRIM['line']
    for i in range(7):
        t = i / 6
        b = lerp((-7.5, -31.2), (-11.5, -29.4), t)
        tip = lerp((-17.0, -30.4), (-20.2, -26.6), t)
        tip = (tip[0] - p['flow'] * 0.4, tip[1])
        strand(c, ap(Wf, b), ap(Wf, lerp(b, tip, 0.5)), ap(Wf, tip), 1.4, 0.3, PRIM, hl=1)
    cov = c.poly(apl(Wf, COVERTS))
    c.paint(cov, COVT, shade=1, hl=1, rim=1)
    scallops(c, Wf, cov, 3, COVT, x0=-9.0, x1=3.0, y0=-36.4, dy=2.2, dx=2.6, r=1.1)


def draw_wing_grip(c, U, G, p):
    sh = ap(U, SH)
    g = ap(G, p['grip'])
    dx, dy = g[0] - sh[0], g[1] - sh[1]
    d = math.hypot(dx, dy); reach = 15.5
    if d > reach:
        g = (sh[0] + dx / d * reach, sh[1] + dy / d * reach)
    el = ik2(sh, g, 7.5, 8.5, bend=1)          # elbow drops below the line
    fx, fy = g[0] - el[0], g[1] - el[1]
    L = math.hypot(fx, fy) or 1
    nx, ny = -fy / L, fx / L
    if ny < 0:
        nx, ny = -nx, -ny                       # normal pointing down
    fringe = [el, g, (g[0] + nx * 2.5, g[1] + ny * 2.5)]
    tips = []
    for t in (0.85, 0.65, 0.45, 0.25, 0.05):
        q = lerp(el, g, t)
        tp = (q[0] + nx * 5.4 - fx / L * 1.6, q[1] + ny * 5.4 - fy / L * 1.6)
        fringe.append(tp); tips.append((q, tp))
        fringe.append((q[0] + nx * 3.2, q[1] + ny * 3.2))
    fringe.append((el[0] + nx * 3.0, el[1] + ny * 3.0))
    fm = c.poly(fringe)
    c.paint(fm, PRIM, shade=1, hl=1, rim=1)
    for q, tp in tips:                          # feather separations + quills
        c.img[c.taper([q, lerp(q, tp, 0.85)], 0.17, 0.15) & fm] = PRIM['line']
    up = c.taper([sh, lerp(sh, el, 0.5), el], 4.2, 3.0)
    c.paint(up, COVT, shade=1, hl=1, rim=1)
    M = T(sh[0], sh[1]) @ R(math.degrees(math.atan2(el[1] - sh[1], el[0] - sh[0])))
    scallops(c, M, up, 2, COVT, x0=0.5, x1=7.0, y0=-1.0, dy=1.9, dx=2.2, r=0.9)
    c.paint(c.taper([el, g], 2.8, 1.9), COVT, shade=1, hl=1, rim=1)
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
    for i in range(9):
        a = math.radians(-162 + i * 12)
        L2 = 15.5 - abs(i - 3) * 1.1
        tip = (wr[0] + L2 * math.cos(a), wr[1] + L2 * math.sin(a))
        strand(c, wr, lerp(wr, tip, 0.45), tip, 2.2, 0.45, matp, hl=1)
    for i in range(6):
        q = lerp(el, wr, i / 5)
        tip = (q[0] - 5.5 - i, q[1] + 8.5 - i * 1.4)
        strand(c, q, lerp(q, tip, 0.5), tip, 2.1, 0.5, matp, hl=1)
    c.paint(c.taper([sh, el, wr], 3.8, 2.4), matc, shade=1, hl=1, rim=1)


def draw_eye(c, Hm, e):
    """the eye at 2x: dark socket, cyan iris with a darker ring, slit pupil, glint, heavy brow."""
    kk = HEAD_K
    E = ap(Hm, EYE)
    if e == 'x':
        for a, b in (((-1.3, -1.3), (1.3, 1.3)), ((-1.3, 1.3), (1.3, -1.3))):
            c.flat(c.taper([(E[0] + a[0], E[1] + a[1]), (E[0] + b[0], E[1] + b[1])], 0.35, 0.35), EYE_PUP, sil=False)
        return
    if e == 'shut':
        c.flat(c.taper([(E[0] - 1.8, E[1] - 0.4), (E[0], E[1] + 0.3), (E[0] + 1.8, E[1] - 0.1)], 0.3, 0.3), EYE_PUP, sil=False)
        c.flat(c.poly([(x, y - 0.6) for x, y in apl(Hm, BROW_P)]), BROW, sil=False)
        return
    wide = e in ('wide',)
    c.flat(c.ell(E, 1.85 * kk * 0.78, 1.45 * kk * 0.78), EYE_SOCK, sil=False)
    ir = (1.38 if wide else 1.22) * kk * 0.78
    iris = c.ell((E[0] + 0.15, E[1] + 0.05), ir, ir * 0.88)
    c.flat(iris, EYE_IRIS, sil=False)
    ring = iris & ~c.ell((E[0] + 0.15, E[1] + 0.05), ir * 0.72, ir * 0.62)
    c.img[ring] = (70, 170, 220, 255)
    c.flat(c.ell((E[0] + 0.45, E[1] + 0.05), 0.32 * kk, 0.78 * kk * 0.8), EYE_PUP, sil=False)
    gx, gy = c.px((E[0] - 0.35, E[1] - 0.45))
    if 0 <= gx < c.w and 0 <= gy < c.h:
        c.img[gy, gx] = EYE_HOT
    if e == 'glow':
        gl = c.taper([(E[0] - 1.0, E[1]), (E[0] - 4.5, E[1] - 0.8), (E[0] - 8.0, E[1] - 1.8)], 0.42, 0.12)
        c.img[gl] = (170, 250, 255, 255)
    if not wide:
        c.flat(c.poly(apl(Hm, BROW_P)), BROW, sil=False)
        # brow ridge highlight line
        a, b = ap(Hm, (HC[0] - 1.0, HC[1] - 3.2)), ap(Hm, (HC[0] + 4.0, HC[1] - 3.4))
        c.img[c.taper([a, b], 0.16, 0.16)] = (110, 40, 90, 255)
    else:
        c.flat(c.poly([(x, y - 0.9) for x, y in apl(Hm, BROW_P)]), BROW, sil=False)


def draw_head(c, Hm, p):
    e = p['eye']
    cm = c.poly(apl(Hm, COMB_P))
    c.paint(cm, COMB, shade=1, hl=1, rim=0)
    c.img[c.poly(apl(Hm, COMB_SHADE)) & cm] = COMB['shadow']
    # comb texture: small bumps catching the light, darker base
    for q in ((3.6, -7.2), (1.6, -9.6), (-0.6, -9.2), (-2.8, -8.6), (-4.6, -7.4), (0.6, -6.4), (-1.8, -6.0), (2.6, -5.6)):
        bm = c.ell(ap(Hm, (HC[0] + q[0], HC[1] + q[1])), 0.38, 0.38) & cm
        c.img[bm] = COMB['light']
    base = c.taper(apl(Hm, [(HC[0] + 4.4, HC[1] - 4.3), (HC[0] - 6.4, HC[1] - 5.3)]), 0.45, 0.45) & cm
    c.img[base] = COMB['shadow']
    sk = c.poly(apl(Hm, SKULL))
    c.paint(sk, HACK, shade=1, hl=1, rim=1)
    for i in range(4):                       # small nape feathers behind the comb
        b0 = ap(Hm, (HC[0] - 1.0 - i * 0.9, HC[1] - 3.6 + i * 0.7))
        tp = ap(Hm, (HC[0] - 4.6 - i * 0.8, HC[1] - 2.4 + i * 1.1))
        strand(c, b0, lerp(b0, tp, 0.5), tp, 0.7, 0.2, HACK2 if i % 2 else HACK, rachis=False)
    c.paint(c.poly(apl(Hm, FACE)), SKIN, shade=1, hl=0, rim=0)
    wb = c.poly(apl(Hm, WATTLE_B))
    c.paint(wb, SKIN, shade=1, hl=0, rim=0)
    # beak (lower mandible opens about its hinge)
    piv = ap(Hm, BEAK_PIV)
    Mb = R(p['beak'], piv)
    Mu = R(-p['beak'] * 0.35, piv)
    lm = c.poly(apl(Mb, apl(Hm, BEAK_L)))
    c.paint(lm, BEAK, shade=1, hl=0, rim=0)
    if p['beak'] > 6:                        # open mouth: dark gape + tongue
        gp = [piv, ap(Mu, ap(Hm, (HC[0] + 8.0, HC[1] + 0.4))), ap(Mb, ap(Hm, (HC[0] + 7.4, HC[1] + 1.0)))]
        c.flat(c.poly(gp), (54, 8, 36, 255))
        tg = c.taper([piv, lerp(piv, ap(Mb, ap(Hm, (HC[0] + 6.4, HC[1] + 0.9))), 0.8)], 0.45, 0.3) & c.poly(gp)
        c.img[tg] = (190, 70, 130, 255)
    um = c.poly(apl(Mu, apl(Hm, BEAK_U)))
    c.paint(um, BEAK, shade=1, hl=1, rim=0)
    tipm = c.ell(ap(Mu, ap(Hm, (HC[0] + 9.2, HC[1] + 1.4))), 1.1, 1.1) & um
    c.img[tipm] = BEAK['line']
    nos = c.ell(ap(Mu, ap(Hm, (HC[0] + 5.6, HC[1] - 1.5))), 0.42, 0.28) & um
    c.img[nos] = BEAK['line']
    ml = c.taper(apl(Mu, apl(Hm, [(HC[0] + 4.4, HC[1] + 0.3), (HC[0] + 7.6, HC[1] + 0.6)])), 0.15, 0.15) & um
    c.img[ml] = BEAK['shadow']
    hk = c.ell(ap(Mu, ap(Hm, (HC[0] + 8.6, HC[1] - 0.6))), 0.35, 0.35) & um
    c.img[hk] = (255, 255, 255, 255)
    wf = c.poly(apl(Hm, WATTLE_F))
    c.paint(wf, SKIN, shade=1, hl=1, rim=0)
    for a, b in (((3.6, 2.8), (4.6, 4.2)), ((3.2, 4.6), (4.4, 5.8))):     # wattle wrinkles
        c.img[c.taper(apl(Hm, [(HC[0] + a[0], HC[1] + a[1]), (HC[0] + b[0], HC[1] + b[1])]), 0.15, 0.15) & wf] = SKIN['shadow']
    # old battle scar across the cheek (under the eye so the eye stays clean)
    a, b = apl(Hm, SCAR_P)
    sc = c.taper([a, b], 0.26, 0.22)
    c.img[sc & (c.img[..., 3] > 0)] = SCAR
    draw_eye(c, Hm, p['eye'])


def draw_hackles(c, U, Hm, p, front):
    f = p['flow']
    if not front:
        for i in range(18):
            t = i / 17
            jit = ((i * 7) % 5 - 2) * 0.35
            base = ap(Hm, lerp((9.6, -54.6), (5.4, -44.6), t))
            tp0 = lerp((3.6, -37.6), (-6.0, -36.4), t)
            tip = ap(U, (tp0[0] - f * 0.8 + jit, tp0[1] + abs(jit) * 0.6))
            mid = lerp(base, tip, 0.5)
            ctrl = (mid[0] - 3.4 - f * 0.5 + jit * 0.5, mid[1] - 0.8)
            strand(c, base, ctrl, tip, 1.55, 0.25, HACK if i % 2 else HACK2, rim=1)
    else:
        for i in range(8):
            t = i / 7
            base = ap(Hm, lerp((13.4, -47.4), (10.0, -44.4), t))
            tip = ap(U, lerp((10.8, -36.6), (7.0, -34.0), t))
            mid = lerp(base, tip, 0.5)
            strand(c, base, (mid[0] + 1.5, mid[1]), tip, 1.4, 0.3, HACK2 if i % 2 else HACK)


def draw_saddle(c, U, p):
    f = p['flow']
    for i in range(12):
        t = i / 11
        base = ap(U, lerp((-0.8, -40.3), (-9.8, -38.2), t))
        tp0 = lerp((-10.8, -31.2), (-17.0, -28.8), t)
        tip = ap(U, (tp0[0] - f * 0.6, tp0[1] + ((i * 3) % 4) * 0.25))
        mid = lerp(base, tip, 0.5)
        strand(c, base, (mid[0] - 1.0, mid[1] - 1.6), tip, 1.5, 0.3, SADL if i % 2 else HACK, rim=1)


def draw_stars(c, U, Tm):
    pts = STARS + [(-9, -27), (-2, -31), (-12, -36), (5, -33), (-15, -31), (-31, -45), (-21, -57), (-27, -36)]
    for i, s in enumerate(pts):
        q = ap(Tm if s[0] < -16 else U, s)
        x, y = c.px(q)
        if 1 <= x < c.w - 1 and 1 <= y < c.h - 1 and c.img[y, x, 3] > 0:
            v = c.img[y, x, :3].astype(int)
            if v.sum() < 330:                         # only on dark plumage
                c.img[y, x] = STAR
                if i % 3 == 0:                        # a few twinkle crosses
                    for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        if c.img[y + ddy, x + ddx, 3] > 0 and c.img[y + ddy, x + ddx, :3].astype(int).sum() < 330:
                            c.img[y + ddy, x + ddx] = (170, 160, 240, 255)


def draw_body(c, U, p):
    bm = c.poly(apl(U, BODY))
    c.paint(bm, PLUM, shade=2, hl=1, rim=1)
    br = c.poly(apl(U, BREAST))
    c.img[br & (c.img[..., 3] > 0) & ~shift(br, 2 * c.k, -2 * c.k)] = PLUM['light']
    scallops(c, U, bm, 5, PLUM, x0=-12.5, x1=9.5, y0=-37.6, dy=3.2, dx=3.0, r=1.25)
    return bm


def render(pose):
    """-> (RGBA image W x H at 2x, grip point in frame px (x, y) or None)."""
    p, G, U, Hn, Hm, Tm = build(pose)
    c = Canvas()
    if p['fwing'] == 'raise':
        draw_wing_raise(c, U, p, far=True)
    draw_tail(c, Tm, p)
    draw_leg(c, U, G, p['footB'], p['toeB'], True, p)
    draw_body(c, U, p)
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
        grip = (OX + g[0] * K, OY + g[1] * K)
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
    im.resize((W * 3, H * 3), Image.NEAREST).save(sys.argv[1] if len(sys.argv) > 1 else '/tmp/scy_rest.png')
    print('ok', im.size, 'grip', g)
