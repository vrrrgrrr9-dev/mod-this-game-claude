"""Scyther's skill / ultimate effects - smooth glowing VFX in the style of the game's own effects.

All sprites are rendered at 3x and box-filtered (soft, anti-aliased).  Additive sprites store the
light colour in RGB and its intensity in alpha (the game draws them with bm_add); normal sprites
(the black-hole core) are ordinary RGBA.

  Event Horizon (skill 1)  bh_core (normal), bh_diskb / bh_diskf (accretion disk behind / in front
                           of the core), bh_pull (gravity spiral), bh_debris, bh_burst (collapse)
  Void Lance (skill 2)     vl_iris, vl_beam, vl_tip, vl_nova  (the aperture itself is a rift sprite)
  misc                     aura, dash, hitfx, spark, impact
"""
import math, os, sys
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

S3 = 3
VIO = np.array((180, 100, 255), np.float32)
VIO_D = np.array((100, 36, 200), np.float32)
WHITE = np.array((255, 246, 255), np.float32)
MAG = np.array((240, 90, 220), np.float32)
CYAN = np.array((150, 236, 255), np.float32)
HOT = np.array((255, 190, 120), np.float32)


class FX:
    """float light buffer at 3x; finish() -> additive RGBA PIL image at 1x."""
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.L = np.zeros((h * S3, w * S3, 3), np.float32)
        yy, xx = np.mgrid[0:h * S3, 0:w * S3].astype(np.float32)
        self.X, self.Y = (xx + 0.5) / S3, (yy + 0.5) / S3

    def blob(self, x, y, r, col, k=1.0, soft=1.0):
        d = np.sqrt((self.X - x) ** 2 + (self.Y - y) ** 2)
        v = np.clip(1 - d / max(r, 1e-3), 0, 1) ** (1.0 + soft) * k
        self.L += v[..., None] * col

    def gauss(self, x, y, s, col, k=1.0):
        # only touch the window where the Gaussian is visible (4 sigma)
        r = 4 * s
        x0, x1 = int(max(0, (x - r) * S3)), int(min(self.w * S3, (x + r) * S3 + 1))
        y0, y1 = int(max(0, (y - r) * S3)), int(min(self.h * S3, (y + r) * S3 + 1))
        if x1 <= x0 or y1 <= y0:
            return
        X, Y = self.X[y0:y1, x0:x1], self.Y[y0:y1, x0:x1]
        d2 = (X - x) ** 2 + (Y - y) ** 2
        self.L[y0:y1, x0:x1] += (np.exp(-d2 / (2 * s * s)) * k)[..., None] * col

    def ring(self, x, y, r, w, col, k=1.0, sy=1.0, a0=None, a1=None):
        dx, dy = self.X - x, (self.Y - y) / sy
        d = np.sqrt(dx * dx + dy * dy)
        v = np.exp(-((d - r) / max(w, 0.3)) ** 2) * k
        if a0 is not None:
            th = np.degrees(np.arctan2(dy, dx)) % 360
            m = ((th - a0) % 360) <= ((a1 - a0) % 360)
            v = v * m
        self.L += v[..., None] * col

    def line(self, pts, w, col, k=1.0, taper=False):
        for i in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[i], pts[i + 1]
            n = max(2, int(math.hypot(x1 - x0, y1 - y0) * 2))
            for t in np.linspace(0, 1, n, endpoint=False):
                ww = w * ((1 - (i + t) / len(pts)) if taper else 1)
                self.gauss(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, max(0.35, ww), col, k / n * 6)

    def finish(self, gamma=1.0):
        L = self.L.reshape(self.h, S3, self.w, S3, 3).mean(axis=(1, 3))
        a = np.clip(L.max(axis=2) / 255.0, 0, 1) ** gamma
        rgb = np.where(a[..., None] > 1e-4, L / np.maximum(L.max(axis=2, keepdims=True), 1e-4) * 255, 0)
        out = np.concatenate([np.clip(rgb, 0, 255), (a * 255)[..., None]], axis=2)
        return Image.fromarray(out.astype(np.uint8), 'RGBA')


def strip(frames):
    w, h = frames[0].size
    s = Image.new('RGBA', (w * len(frames), h), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        s.paste(f, (i * w, 0))
    return s


# ------------------------------------------------------------------------- Event Horizon
def bh_core(k):
    """the black hole itself (normal blend): shadow sphere + gravitational dimming + photon ring."""
    W = H = 72; c = 36
    yy, xx = np.mgrid[0:H * S3, 0:W * S3].astype(np.float32) / S3
    d = np.sqrt((xx - c) ** 2 + (yy - c) ** 2)
    R0 = 14.0
    a = np.clip((R0 + 0.6 - d) / 1.2, 0, 1)                     # the event horizon (solid black)
    halo = np.clip(1 - (d - R0) / 11, 0, 1) ** 2 * 0.55          # light bent away around it
    alpha = np.maximum(a, halo)
    rgb = np.zeros(d.shape + (3,), np.float32)
    rgb[...] = (4, 2, 10)
    ring = np.exp(-((d - (R0 + 0.9)) / 0.7) ** 2) * (0.85 + 0.15 * math.sin(k * 1.3))
    rgb = rgb * (1 - ring[..., None]) + np.array((246, 222, 255)) * ring[..., None]
    alpha = np.maximum(alpha, ring)
    rgba = np.concatenate([rgb, alpha[..., None] * 255], axis=2)
    small = rgba.reshape(H, S3, W, S3, 4).mean(axis=(1, 3))
    return Image.fromarray(np.clip(small, 0, 255).astype(np.uint8), 'RGBA')


def bh_disk(k, front):
    """accretion disk seen at a steep angle; front=True -> the near (lower) half, else the far half
    plus the lensed image of the far disk bent over the top of the hole."""
    W, H = 160, 80; cx, cy = 80, 40
    f = FX(W, H)
    ry_k = 0.27
    dx, dy = f.X - cx, (f.Y - cy) / ry_k
    r = np.sqrt(dx * dx + dy * dy); th = np.arctan2(dy, dx)
    rin, rout = 20.0, 70.0
    band = np.clip((r - rin) / 3, 0, 1) * np.clip((rout - r) / 18, 0, 1)
    u = np.clip((r - rin) / (rout - rin), 0, 1)
    swirl = 0.55 + 0.45 * np.sin(5 * th - 9 * np.log(r + 1) + k * 0.8)
    swirl2 = 0.6 + 0.4 * np.sin(11 * th - 15 * np.log(r + 1) - k * 1.1)
    dopp = 1 + 0.55 * np.cos(th)                                  # approaching side brighter
    inten = band * swirl * swirl2 * dopp * (1.25 - u)
    col = (WHITE * np.clip(1 - u * 3, 0, 1)[..., None] + HOT * np.clip(1 - np.abs(u - 0.3) * 4, 0, 1)[..., None]
           + MAG * np.clip(1 - np.abs(u - 0.55) * 3, 0, 1)[..., None] + VIO_D * np.clip((u - 0.6) * 3, 0, 1)[..., None])
    half = (f.Y >= cy) if front else (f.Y < cy)
    f.L += (inten * half)[..., None] * col * 1.25
    if front:
        # lensed far side: a bright arc hugging the top of the shadow
        f.ring(cx, cy, 17.5, 1.3, WHITE, 1.1, sy=1.0, a0=190, a1=350)
        f.ring(cx, cy, 19.5, 2.2, MAG, 0.6, sy=1.0, a0=200, a1=340)
    return f.finish(0.9)


def bh_pull(k):
    W = H = 168; c = 84
    f = FX(W, H)
    for arm in range(9):
        pts = []
        for r in np.linspace(78, 18, 22):
            th = arm * 2 * math.pi / 9 + 1.9 * math.log(78 / r) + k * 0.35
            pts.append((c + r * math.cos(th), c + r * math.sin(th) * 0.55))
        f.line(pts, 0.7, VIO, 0.45)
    return f.finish()


def bh_debris(k):
    W = H = 20
    im = np.zeros((H, W, 4), np.uint8)
    rng = np.random.default_rng(3)
    poly = [(10 + 4.5 * math.cos(a + k * 0.6) * rng.uniform(0.7, 1.1), 10 + 3.6 * math.sin(a + k * 0.6) * rng.uniform(0.7, 1.1))
            for a in np.linspace(0, 2 * math.pi, 7, endpoint=False)]
    from PIL import ImageDraw
    pi = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(pi)
    d.polygon(poly, fill=(46, 30, 70, 255), outline=(170, 110, 255, 255))
    d.point([(int(poly[0][0]), int(poly[0][1]))], fill=(230, 200, 255, 255))
    return pi


def bh_burst(k):
    W = H = 192; c = 96
    f = FX(W, H)
    if k < 4:                                  # implosion: everything drawn into a point
        r = 46 * (1 - k / 4) + 3
        f.ring(c, c, r, 2.5, VIO, 1.0); f.gauss(c, c, 3 + k, WHITE, 0.6 + k * 0.3)
        for i in range(14):
            a = i * 2 * math.pi / 14 + k
            f.line([(c + (r + 30) * math.cos(a), c + (r + 30) * math.sin(a)), (c + r * math.cos(a), c + r * math.sin(a))], 0.6, VIO, 0.6)
    elif k == 4:                               # flash
        f.gauss(c, c, 18, WHITE, 2.2); f.gauss(c, c, 40, VIO, 1.2)
    else:                                      # shockwave
        t = (k - 5) / 10
        r = 14 + 78 * t
        f.ring(c, c, r, 5 * (1 - t) + 1, WHITE, 1.4 * (1 - t))
        f.ring(c, c, r * 0.8, 9 * (1 - t) + 2, VIO, 1.1 * (1 - t))
        f.ring(c, c, r * 1.05, 3, MAG, 0.7 * (1 - t), sy=0.35)
        f.gauss(c, c, 22 * (1 - t) + 4, VIO_D, 1.0 * (1 - t))
        rng = np.random.default_rng(9)
        for i in range(18):
            a = rng.uniform(0, 2 * math.pi); s = rng.uniform(0.6, 1.1)
            rr = r * s + 10
            f.line([(c + rr * math.cos(a), c + rr * math.sin(a)), (c + (rr + 14 * (1 - t)) * math.cos(a), c + (rr + 14 * (1 - t)) * math.sin(a))], 0.6, CYAN, 0.9 * (1 - t))
    return f.finish()


# ------------------------------------------------------------------------- Void Lance
def vl_iris(k):
    W = H = 56; c = 28
    f = FX(W, H)
    for i, (r, w) in enumerate(((6, 1.5), (11, 1.1), (16, 0.9), (21, 0.7))):
        f.ring(c, c, r + 1.5 * math.sin(k * 0.9 + i), w, VIO if i % 2 else MAG, 0.9 - i * 0.15)
    for i in range(12):
        a = i * math.pi / 6 + k * 0.25
        f.line([(c + 17 * math.cos(a), c + 17 * math.sin(a)), (c + 23 * math.cos(a), c + 23 * math.sin(a))], 0.5, CYAN, 0.8)
    f.gauss(c, c, 3.5 + (k % 4) * 0.5, WHITE, 1.4)
    return f.finish()


def vl_beam(k):
    W, H = 32, 40; c = 20
    f = FX(W, H)
    f.L += (np.exp(-((f.Y - c) / 2.0) ** 2) * 1.4)[..., None] * WHITE
    f.L += (np.exp(-((f.Y - c) / 6.5) ** 2) * 0.9)[..., None] * VIO
    for ph in (0, math.pi):
        ys = c + 7.5 * np.sin(2 * math.pi * f.X / 32 + ph + k * 0.785)
        f.L += (np.exp(-((f.Y - ys) / 0.9) ** 2) * 0.85)[..., None] * MAG
    return f.finish()


def vl_tip(k):
    W = H = 64; c = 32
    f = FX(W, H)
    f.gauss(c, c, 5, WHITE, 1.8); f.gauss(c, c, 13, VIO, 1.0)
    for i in range(8):
        a = i * math.pi / 4 + k * 0.2
        L = (26 if i % 2 == 0 else 15) * (0.8 + 0.2 * math.sin(k + i))
        f.line([(c, c), (c + L * math.cos(a), c + L * math.sin(a))], 0.6, WHITE if i % 2 == 0 else CYAN, 1.2, taper=True)
    return f.finish()


def vl_nova(k):
    W = H = 160; c = 80
    f = FX(W, H)
    t = k / 15
    r = 8 + 60 * t ** 0.7
    f.gauss(c, c, r * 0.6, VIO, 1.3 * (1 - t))
    f.gauss(c, c, r * 0.25, WHITE, 1.6 * (1 - t) ** 2)
    f.ring(c, c, r, 4 * (1 - t) + 1, WHITE, 1.2 * (1 - t))
    f.ring(c, c, r * 1.15, 2, MAG, 0.8 * (1 - t), sy=0.4)
    if 2 <= k <= 6:                            # a black singularity pops in the centre
        f.L -= (np.exp(-((f.X - c) ** 2 + (f.Y - c) ** 2) / (2 * 5 ** 2)) * 400)[..., None]
        f.L = np.clip(f.L, 0, None)
    return f.finish()


# ------------------------------------------------------------------------- misc
def aura(k):
    W, H = 96, 112; bx, by = 48, 104
    f = FX(W, H)
    rng = np.random.default_rng(k * 13 + 1)
    for i in range(11):
        x = bx + rng.uniform(-22, 22)
        hgt = rng.uniform(40, 82)
        sway = rng.uniform(-6, 6)
        pts = [(x + sway * math.sin(j / 6 * math.pi + k), by - hgt * j / 6) for j in range(7)]
        f.line(pts, 2.6, VIO if i % 3 else MAG, 0.55, taper=True)
    for i in range(6):
        a = k * 0.8 + i * 1.05
        f.gauss(bx + 26 * math.cos(a), by - 40 + 12 * math.sin(a * 1.3), 1.1, CYAN, 1.2)
    return f.finish()


def dash(k):
    W, H = 112, 64
    f = FX(W, H)
    rng = np.random.default_rng(5)
    for i in range(10):
        y = rng.uniform(8, 56); x0 = rng.uniform(0, 30); L = rng.uniform(40, 90) * (1 - k / 7)
        f.line([(x0 + k * 8, y), (x0 + k * 8 + L, y)], 0.7, VIO if i % 2 else WHITE, 0.7 * (1 - k / 6))
    return f.finish()


def hitfx(k):
    W = H = 64; c = 32
    f = FX(W, H)
    t = k / 7
    L = 24 * (0.6 + 0.6 * t)
    for a in (math.pi / 4, -math.pi / 4):
        f.line([(c - L * math.cos(a), c - L * math.sin(a)), (c + L * math.cos(a), c + L * math.sin(a))], 1.0 * (1 - t) + 0.3, WHITE, 1.6 * (1 - t))
    f.gauss(c, c, 6 + 6 * t, VIO, 1.2 * (1 - t))
    f.ring(c, c, 6 + 18 * t, 1.2, MAG, 0.8 * (1 - t))
    return f.finish()


def spark(k):
    W = H = 16; c = 8
    f = FX(W, H)
    s = math.sin(k / 8 * math.pi)
    for a in (0, math.pi / 2):
        L = 6 * s
        f.line([(c - L * math.cos(a), c - L * math.sin(a)), (c + L * math.cos(a), c + L * math.sin(a))], 0.4, WHITE, 1.2)
    f.gauss(c, c, 1.2, CYAN, 1.0 * s)
    return f.finish()


def impact(k):
    W = H = 112; c = 56
    f = FX(W, H)
    t = k / 9
    for i in range(12):
        a = i * math.pi / 6 + 0.2
        L = (46 if i % 2 == 0 else 26) * (0.5 + t)
        f.line([(c, c), (c + L * math.cos(a), c + L * math.sin(a))], 1.0 * (1 - t) + 0.3, WHITE if i % 2 == 0 else VIO, 1.6 * (1 - t), taper=True)
    f.gauss(c, c, 10 + 10 * t, VIO, 1.4 * (1 - t))
    f.ring(c, c, 12 + 40 * t, 2.5, MAG, 1.0 * (1 - t))
    return f.finish()


def smear(k):
    """a soft white bar for stretched trail / ring segments (tinted, additive)."""
    W, H = 32, 8
    f = FX(W, H)
    for x in range(2, W - 2):
        f.gauss(x + 0.5, H / 2, 1.5, WHITE, 0.5)
    return f.finish()


# name: (fn, frames, origin x, origin y, additive)
FX_LIST = {
    'bh_core': (bh_core, 8, 36, 36, False),
    'bh_diskb': (lambda k: bh_disk(k, False), 16, 80, 40, True),
    'bh_diskf': (lambda k: bh_disk(k, True), 16, 80, 40, True),
    'bh_pull': (bh_pull, 8, 84, 84, True),
    'bh_debris': (bh_debris, 8, 10, 10, False),
    'bh_burst': (bh_burst, 16, 96, 96, True),
    'vl_iris': (vl_iris, 8, 28, 28, True),
    'vl_beam': (vl_beam, 8, 0, 20, True),
    'vl_tip': (vl_tip, 8, 32, 32, True),
    'vl_nova': (vl_nova, 16, 80, 80, True),
    'aura': (aura, 8, 48, 104, True),
    'dash': (dash, 6, 56, 32, True),
    'hitfx': (hitfx, 8, 32, 32, True),
    'spark': (spark, 8, 8, 8, True),
    'smear': (smear, 1, 16, 4, True),
    'impact': (impact, 10, 56, 56, True),
}


def build(out):
    os.makedirs(out, exist_ok=True)
    res = {}
    for name, (fn, n, ox, oy, add) in FX_LIST.items():
        fr = [fn(k) for k in range(n)]
        strip(fr).save(os.path.join(out, f'scyther_{name}.png'))
        res[name] = fr
    return res


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else '/tmp'
    res = build(out)
    # preview on a dark backdrop (additive composite)
    rows = []
    for name, fr in res.items():
        w, h = fr[0].size
        n = min(8, len(fr))
        row = np.zeros((h, w * n, 3), np.float32); row[...] = (26, 20, 44)
        for i in range(n):
            a = np.array(fr[i * len(fr) // n]).astype(np.float32)
            if FX_LIST[name][4]:
                row[:, i * w:(i + 1) * w] = np.clip(row[:, i * w:(i + 1) * w] + a[..., :3] * a[..., 3:4] / 255, 0, 255)
            else:
                al = a[..., 3:4] / 255
                row[:, i * w:(i + 1) * w] = row[:, i * w:(i + 1) * w] * (1 - al) + a[..., :3] * al
        rows.append(row)
    Wd = max(r.shape[1] for r in rows); Hd = sum(r.shape[0] + 4 for r in rows)
    sheet = np.zeros((Hd, Wd, 3), np.uint8); y = 0
    for r in rows:
        sheet[y:y + r.shape[0], :r.shape[1]] = r.astype(np.uint8); y += r.shape[0] + 4
    Image.fromarray(sheet).save(os.path.join(out, 'vfx_preview.png'))
    print('vfx ok')
