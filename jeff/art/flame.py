"""Jeff's dark blue flame - blue fire with darkness flowing inside it.

Not a flat dark-blue: the flame body is electric blue with bright cyan-white edges, and dark
(near-black indigo) tongues flow up through its core like smoke inside the fire.  Rendered from
animated turbulence (noise periodic in time, so every effect loops), 3x supersampled, normal
blend (the dark parts must be able to darken what is behind them); the game adds a soft additive
glow (jf_glow) for the bloom.

  jf_fist    flame wrapped round a fist / foot, streaming back      jf_trail  punch streak
  jf_burst   impact explosion                                        jf_arc    kick swing crescent
  jf_meteor  flaming meteor (the game rotates it along its fall)     jf_crater meteor impact pillar
  jf_portal  black hole in the sky the meteors fall out of           jf_bh / jf_bhring_b / _f  black hole
  jf_aura    flame aura round Jeff                                   jf_rock   debris chips, jf_glow bloom
"""
import math, os, sys
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

S = 3
EDGE = np.array((205, 244, 255), np.float32)
CYAN = np.array((96, 200, 255), np.float32)
BLUE = np.array((40, 104, 246), np.float32)
DEEP = np.array((22, 40, 150), np.float32)
DARK = np.array((10, 6, 30), np.float32)


PAL = np.array([DARK, DEEP, BLUE, CYAN, EDGE], np.float32)
_LUM = PAL @ np.array((0.3, 0.55, 0.15), np.float32)
_BAYER = (np.array([[0, 2], [3, 1]], np.float32) / 4.0) - 0.375


def pixelate(rgb, al, outline=True, cut=0.42):
    """1x float colour + coverage -> pixel art: hard alpha, 5-colour palette with 2x2 ordered
    dithering between neighbouring tones, and a 1 px dark rim (the darkness is part of the flame)."""
    h, w = al.shape
    yy, xx = np.mgrid[0:h, 0:w]
    lum = rgb @ np.array((0.3, 0.55, 0.15), np.float32)
    t = np.interp(lum, _LUM, np.arange(len(PAL), dtype=np.float32)) + _BAYER[yy % 2, xx % 2] * 0.9
    idx = np.clip(np.round(t), 0, len(PAL) - 1).astype(int)
    out = np.zeros((h, w, 4), np.uint8)
    solid = al > cut
    out[..., :3] = PAL[idx]
    out[..., 3] = np.where(solid, 255, 0)
    if outline:
        rim = ndi.binary_dilation(solid) & ~solid
        out[rim, :3] = DARK; out[rim, 3] = 255
    return Image.fromarray(out, 'RGBA')


def _noise(h, w, sy, sx, seed):
    """smooth noise, periodic in both axes (wrap), stretched (sy, sx), values 0..1."""
    rng = np.random.default_rng(seed)
    n = ndi.gaussian_filter(rng.random((h, w)).astype(np.float32), (sy, sx), mode='wrap')
    n -= n.min(); n /= max(n.max(), 1e-6)
    return n


def _smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


class Flame:
    """flame on a W x H canvas, frame k of n (loops).  flow = 'up' (rising fire) or 'back' (fire
    streaming sideways, e.g. off a punching fist).  add() builds a heat envelope; turbulence then
    tears it into tongues; the hottest part burns white-cyan, the body blue, the tips deep blue -
    and darkness streams through the body (never the hot core)."""
    def __init__(self, w, h, k, n, seed=1, speed=1.0, flow='up'):
        self.w, self.h, self.flow = w, h, flow
        yy, xx = np.mgrid[0:h * S, 0:w * S].astype(np.float32)
        self.X, self.Y = (xx + 0.5) / S, (yy + 0.5) / S
        ph = k / n
        if flow == 'up':
            P = h * S * 2
            fields = [(_noise(P, w * S, 5.5 * S, 1.6 * S, seed), 1.0), (_noise(P, w * S, 9 * S, 3 * S, seed + 1), 0.5),
                      (_noise(P, w * S, 7 * S, 1.4 * S, seed + 2), 0.7)]
            out = []
            for f, sp in fields:
                off = int(ph * P * speed * sp) % P
                out.append(np.roll(f, off, axis=0)[:h * S])          # content moves up the screen
        else:
            P = w * S * 2
            fields = [(_noise(h * S, P, 1.6 * S, 5.5 * S, seed), 1.0), (_noise(h * S, P, 3 * S, 9 * S, seed + 1), 0.5),
                      (_noise(h * S, P, 1.4 * S, 7 * S, seed + 2), 0.7)]
            out = []
            for f, sp in fields:
                off = int(ph * P * speed * sp) % P
                out.append(np.roll(f, -off, axis=1)[:, :w * S])      # content streams to the left
        self.n1, self.n2, self.n3 = out
        self.T = np.zeros_like(self.X)

    def warp(self, ax=4.0, ay=2.0):
        """coordinates jittered by the turbulence (flickering envelope edges)."""
        return self.X + (self.n2 - 0.5) * 2 * ax, self.Y + (self.n1 - 0.5) * 2 * ay

    def add(self, env, k=1.0):
        self.T = np.maximum(self.T, np.clip(env * k, 0, 1.3))

    def finish(self, dark=1.0, glow=0.0):
        T = self.T
        d = T * (0.5 + 0.8 * self.n1) - 0.16                   # turbulence tears the edges into tongues
        a = _smooth(0.0, 0.22, d)
        heat = np.clip(T * (0.62 + 0.4 * self.n2), 0, 1.2)
        col = (BLUE * 0.35 + DEEP * 0.65)[None, None] * np.ones_like(T)[..., None]
        for lo, hi, c in ((0.25, 0.5, BLUE), (0.5, 0.75, CYAN), (0.78, 1.0, EDGE)):
            w = _smooth(lo, hi, heat)[..., None]
            col = col * (1 - w) + c * w
        # darkness streaming through the body: streaky noise, kept out of the hottest core
        dk = _smooth(0.44, 0.6, self.n3) * _smooth(0.1, 0.3, d) * (1 - _smooth(0.72, 0.92, heat)) * dark
        col = col * (1 - dk[..., None] * 0.92) + DARK * dk[..., None] * 0.92
        a = np.maximum(a, dk * 0.9 * _smooth(0.05, 0.2, d))
        if glow > 0:
            gl = ndi.gaussian_filter(a, 2.5 * S) * glow
            col = np.where((a < 0.02)[..., None], CYAN, col); a = np.maximum(a, gl * 0.6)
        rgba = np.concatenate([col * a[..., None], a[..., None]], axis=2)
        small = rgba.reshape(self.h, S, self.w, S, 4).mean(axis=(1, 3))
        al = small[..., 3]
        rgb = np.where(al[..., None] > 1e-4, small[..., :3] / np.maximum(al[..., None], 1e-4), 0)
        return pixelate(rgb, al)


def _strip(frames):
    w, h = frames[0].size
    s = Image.new('RGBA', (w * len(frames), h), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        s.paste(f, (i * w, 0))
    return s


def fist(k, n=8):
    """flame round a fist at (34, 30), streaming back (to the left) and up."""
    f = Flame(56, 56, k, n, seed=11, speed=1.4, flow='back')
    X, Y = f.warp(3.0, 2.0)
    dx, dy = X - 34, Y - 30
    back = np.clip(-dx / 30, 0, 1)
    env = np.clip(1 - np.sqrt((dx / (12 + 20 * back)) ** 2 + ((dy + 6 * back * back) / (11 - 4 * back)) ** 2), 0, 1)
    f.add(env ** 0.8 * (1.15 - 0.45 * back), 1.25)
    return f.finish(dark=1.0)


def trail(k, n=6):
    """punch streak: a tapered horizontal flame from the fist (right end) back to the left."""
    f = Flame(96, 32, k, n, seed=21, speed=2.0, flow='back')
    X, Y = f.warp(2.0, 1.5)
    t = np.clip(X / 90, 0, 1)
    fade = 1 - k / n
    env = np.clip(1 - np.abs(Y - 16) / (2 + 9 * t), 0, 1) * np.clip(t * 1.2, 0, 1) * (0.4 + 0.6 * fade)
    f.add(env ** 0.8 * (0.5 + 0.6 * t), 1.3)
    return f.finish()


def burst(k, n=10):
    W = 112; c = 56
    f = Flame(W, W, k, n, seed=31, speed=1.0)
    X, Y = f.warp(5, 5)
    r = np.sqrt((X - c) ** 2 + (Y - c) ** 2)
    t = k / (n - 1)
    R = 10 + 38 * t ** 0.7
    core = np.clip(1 - r / (R * 0.9), 0, 1) * (1 - t) ** 1.2
    ring = np.clip(1 - np.abs(r - R) / (6 + 6 * t), 0, 1) * (1 - t * 0.85)
    ang = np.arctan2(Y - c, X - c)
    tongues = np.clip(1 - np.abs(r - R * 1.1) / (8 + 10 * t), 0, 1) * (0.5 + 0.5 * np.sin(ang * 9 + k)) * (1 - t)
    f.add(np.clip(core + ring + tongues, 0, 1), 1.5)
    return f.finish(dark=1.2)


def arc(k, n=6):
    """kick swing: a crescent of dark flame (head at the end of the sweep)."""
    W, H = 128, 112; cx, cy = 52, 70
    f = Flame(W, H, k, n, seed=41, speed=1.6)
    X, Y = f.warp(3, 3)
    r = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    ang = np.degrees(np.arctan2(Y - cy, X - cx))
    a0, a1 = -150, 40
    span = (0.55, 1, 1, 1, 1, 1)[k]
    a1k = a0 + (a1 - a0) * span
    u = np.clip((ang - a0) / max(a1k - a0, 1), 0, 1)
    inside = (ang >= a0) & (ang <= a1k)
    tail = (0, 0, 0.2, 0.45, 0.65, 0.85)[k]
    wid = 4 + 10 * u
    env = np.clip(1 - np.abs(r - 44) / wid, 0, 1) * inside * np.clip((u - tail) / 0.2, 0, 1)
    f.add(env ** 0.7, 1.5)
    return f.finish()


def meteor(k, n=8):
    """meteor heading right: rock at (56, 20), flame tail streaming left."""
    W, H = 72, 40
    f = Flame(W, H, k, n, seed=51, speed=2.2, flow='back')
    X, Y = f.warp(2, 2)
    dx, dy = X - 56, Y - 20
    back = np.clip(-dx / 52, 0, 1)
    env = np.clip(1 - np.sqrt((dx / (9 + 44 * back)) ** 2 + (dy / (8 + 3 * back)) ** 2), 0, 1)
    f.add(env ** 0.7 * (1.2 - 0.6 * back), 1.3)
    im = f.finish(dark=1.1)
    # the rock itself: a dark faceted stone with a molten blue crack
    a = np.array(im).astype(np.float32)
    yy, xx = np.mgrid[0:H, 0:W]
    rr = np.sqrt((xx - 57) ** 2 + ((yy - 20) * 1.1) ** 2)
    rock = rr < 7.5 + 1.2 * np.sin(np.arctan2(yy - 20, xx - 57) * 5 + 1)
    shade = np.clip(0.4 + ((57 - xx) * 0.5 + (20 - yy) * 0.6) / 10, 0.2, 1)
    a[rock, :3] = np.stack([22 + 40 * shade, 20 + 36 * shade, 40 + 60 * shade], -1)[rock]
    a[rock, 3] = 255
    crack = rock & (np.abs((xx - 57) * 0.6 - (yy - 20)) < 0.8)
    a[crack, :3] = (130, 220, 255)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGBA')


def crater(k, n=12):
    """impact: a flame pillar bursts up and spreads along the ground (origin bottom centre)."""
    W, H = 128, 112; cx, gy = 64, 100
    f = Flame(W, H, k, n, seed=61, speed=1.2)
    X, Y = f.warp(4, 3)
    t = k / (n - 1)
    hgt = 70 * math.sin(min(1, t * 1.6) * math.pi / 2) * (1 - t * 0.6)
    pillar = np.clip(1 - np.abs(X - cx) / (10 + 14 * t + (gy - Y) * 0.12), 0, 1) * (Y > gy - hgt) * (Y < gy + 4)
    spread = np.clip(1 - np.abs(Y - gy + 4) / 7, 0, 1) * np.clip(1 - np.abs(X - cx) / (20 + 44 * t), 0, 1)
    f.add(np.clip(pillar * (1 - t) ** 0.8 + spread * (1 - t), 0, 1), 1.4)
    return f.finish(dark=1.1)


def portal(k, n=8):
    """the black hole in the sky: a dark disk seen at an angle, ringed by swirling blue flame."""
    W, H = 112, 56; cx, cy = 56, 28
    f = Flame(W, H, k, n, seed=71, speed=1.0)
    X, Y = f.warp(2, 1.5)
    dx, dy = (X - cx) / 50, (Y - cy) / 22
    r = np.sqrt(dx * dx + dy * dy)
    ang = np.arctan2(dy, dx)
    swirl = 0.5 + 0.5 * np.sin(ang * 6 - r * 9 + k * 2 * math.pi / n)
    ring = np.clip(1 - np.abs(r - 0.78) / 0.24, 0, 1) * (0.55 + 0.45 * swirl)
    f.add(ring, 1.5)
    im = np.array(f.finish(dark=0.8)).astype(np.float32)
    yy, xx = np.mgrid[0:H, 0:W]
    rr = np.sqrt(((xx - cx + 0.5) / 34) ** 2 + ((yy - cy + 0.5) / 13) ** 2)
    hole = rr < 1
    im[hole, :3] = (2, 2, 8); im[hole, 3] = 255
    edge = (rr >= 1) & (rr < 1.09)
    im[edge, :3] = EDGE; im[edge, 3] = 255
    return Image.fromarray(np.clip(im, 0, 255).astype(np.uint8), 'RGBA')


def bh_core(k, n=8):
    W = 64; c = 31.5
    yy, xx = np.mgrid[0:W, 0:W]
    d = np.sqrt((xx - c) ** 2 + (yy - c) ** 2)
    R0 = 12 + (k % 2) * 0.4
    out = np.zeros((W, W, 4), np.uint8)
    halo = (d >= R0 + 1) & (d < R0 + 5) & (((xx + yy + k) % 2 == 0) | (d < R0 + 2.5))
    out[halo] = (*DEEP.astype(int), 255)
    ring = (d >= R0) & (d < R0 + 1.2)
    out[ring] = (*EDGE.astype(int), 255)
    out[d < R0] = (2, 2, 8, 255)
    glint = (np.abs(d - (R0 + 0.6)) < 0.8) & (np.arctan2(yy - c, xx - c) > -2.6 + 0.4 * k) & (np.arctan2(yy - c, xx - c) < -1.8 + 0.4 * k)
    out[glint] = (*CYAN.astype(int), 255)
    return Image.fromarray(out, 'RGBA')


def bh_ring(k, n=8, front=True):
    """accretion disk of dark blue flame, seen steeply; front = the near (lower) half."""
    W, H = 176, 96; cx, cy = 88, 48
    f = Flame(W, H, k, n, seed=81, speed=1.0)
    X, Y = f.warp(3, 2)
    dx, dy = (X - cx), (Y - cy) / 0.32
    r = np.sqrt(dx * dx + dy * dy)
    ang = np.arctan2(dy, dx)
    swirl = 0.5 + 0.5 * np.sin(ang * 4 - np.log(r + 1) * 7 + k * 2 * math.pi / n)
    band = np.clip((r - 18) / 6, 0, 1) * np.clip((78 - r) / 22, 0, 1) * (0.5 + 0.5 * swirl)
    half = (Y >= cy) if front else (Y < cy)
    f.add(band * half, 1.0)
    return f.finish(dark=1.2)


def aura(k, n=8):
    W, H = 96, 112; bx, by = 48, 104
    f = Flame(W, H, k, n, seed=91, speed=1.3)
    X, Y = f.warp(4, 3)
    u = np.clip((by - Y) / 90, 0, 1)
    env = np.clip(1 - np.abs(X - bx) / (30 - 14 * u), 0, 1) * (Y < by + 2) * (1 - u) ** 0.6
    shell = env * np.clip(np.abs(X - bx) / (22 - 10 * u), 0, 1)            # hollow: flames round him
    f.add(shell, 1.3)
    return f.finish(dark=0.9)


def rock(k):
    im = Image.new('RGBA', (16, 16), (0, 0, 0, 0))
    a = np.array(im)
    rng = np.random.default_rng(k + 5)
    pts = [(8 + 4.5 * math.cos(t) * rng.uniform(0.7, 1.1), 8 + 3.5 * math.sin(t) * rng.uniform(0.7, 1.1))
           for t in np.linspace(0, 2 * math.pi, 7, endpoint=False) + k * 0.7]
    from PIL import ImageDraw
    d = ImageDraw.Draw(im); d.polygon(pts, fill=(34, 34, 56, 255), outline=(110, 190, 255, 255))
    return im


def glow():
    """additive bloom in pixel steps (dithered rings, no smooth gradient)."""
    W = 64; c = 31.5
    yy, xx = np.mgrid[0:W, 0:W]
    d = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / 31
    lvl = np.clip(1 - d, 0, 1) ** 1.5 * 3 + _BAYER[yy % 2, xx % 2] * 0.8
    a = np.clip(np.floor(lvl), 0, 3) * 70
    out = np.zeros((W, W, 4), np.float32); out[..., :3] = (90, 180, 255); out[..., 3] = a
    return Image.fromarray(out.astype(np.uint8), 'RGBA')


# name: (frames function, frame count, origin x, origin y)
SPRITES = {
    'jf_fist': (fist, 8, 34, 30), 'jf_trail': (trail, 6, 92, 16), 'jf_burst': (burst, 10, 56, 56),
    'jf_arc': (arc, 6, 52, 70), 'jf_meteor': (meteor, 8, 56, 20), 'jf_crater': (crater, 12, 64, 100),
    'jf_portal': (portal, 8, 56, 28), 'jf_bh': (bh_core, 8, 32, 32),
    'jf_bhring_b': (lambda k, n=8: bh_ring(k, n, False), 8, 88, 48), 'jf_bhring_f': (lambda k, n=8: bh_ring(k, n, True), 8, 88, 48),
    'jf_aura': (aura, 8, 48, 104), 'jf_rock': (lambda k, n=8: rock(k), 8, 8, 8), 'jf_glow': (lambda k, n=1: glow(), 1, 32, 32),
}


def build(out):
    os.makedirs(out, exist_ok=True)
    res = {}
    for name, (fn, n, ox, oy) in SPRITES.items():
        fr = [fn(k, n) if name not in ('jf_rock', 'jf_glow') else fn(k) for k in range(n)]
        _strip(fr).save(os.path.join(out, f'jeff_{name}.png'))
        res[name] = fr
    return res


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else '/tmp'
    res = build(out)
    rows = []
    for name, fr in res.items():
        w, h = fr[0].size
        row = Image.new('RGBA', (w * len(fr), h), (60, 70, 120, 255))
        for i, im in enumerate(fr):
            row.alpha_composite(im, (i * w, 0))
        rows.append(row)
    Wd = max(r.width for r in rows); Hd = sum(r.height + 4 for r in rows)
    sheet = Image.new('RGBA', (Wd, Hd), (30, 30, 40, 255)); y = 0
    for r in rows:
        sheet.alpha_composite(r, (0, y)); y += r.height + 4
    sheet.save(os.path.join(out, 'flame_preview.png'))
    print('flame ok')
