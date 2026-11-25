"""Jeff's red power - the sun - and his two cinematics, all pixel art (same fire as flame.py,
other palettes).

  red power   js_sword (sun blade, grip at the origin, pointing right; the game rotates it to his
              arm), js_shield (sun disk with a turning corona), js_fist / js_trail / js_burst /
              js_arc / js_aura (sun fire), js_wave (Solar Flare crescent), js_swirl (the blue ->
              red power switch), js_glow
  cinematics  rbh_core / rbh_disk_b / rbh_disk_f (the red black hole), hp_orb_b / hp_orb_r /
              hp_orb_p (blue, red and the merged Hollow Purple), hp_nuke (the purple nuclear
              blast), cin_ring (shockwave, tinted by the game), cin_bg (red / purple skies)
"""
import math, os, sys
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flame
from flame import Flame, pixelate, _strip, _BAYER


def pal(name, fn):
    def f(k, n):
        flame.use_palette(name)
        return fn(k, n)
    return f


def sword(k, n=6):
    """a blade of sun fire: grip at (6, 10), pointing right, length ~52 px."""
    W, H = 64, 20
    flame.use_palette('sun')
    f = Flame(W, H, k, n, seed=101, speed=2.0, flow='back')
    X, Y = f.warp(1.0, 0.6)
    t = np.clip((X - 12) / 50, 0, 1)
    half = 4.6 * (1 - t) ** 0.7 + 0.6
    blade = (X >= 12) & (X <= 62)
    env = np.clip(1 - np.abs(Y - 10) / half, 0, 1) * blade
    f.add(env ** 0.6 * 1.25, 1.2)
    im = np.array(f.finish(dark=0.5))
    # crossguard and hilt: solid metal-gold pixels
    def put(x0, x1, y0, y1, col):
        im[y0:y1, x0:x1, :3] = col; im[y0:y1, x0:x1, 3] = 255
    put(9, 12, 3, 17, (150, 40, 10)); put(10, 11, 4, 16, (255, 200, 60))
    put(2, 9, 8, 12, (90, 20, 8)); put(3, 9, 9, 11, (200, 90, 20)); put(1, 3, 7, 13, (255, 220, 90))
    return Image.fromarray(im, 'RGBA')


def shield(k, n=8):
    """a round sun: white-hot core, gold body, red rim, a corona of flares turning round it."""
    W = 40; c = 19.5
    yy, xx = np.mgrid[0:W, 0:W]
    d = np.sqrt((xx - c) ** 2 + (yy - c) ** 2)
    ang = np.arctan2(yy - c, xx - c)
    flame.use_palette('sun')
    P = flame.PAL
    lvl = np.where(d < 11, 4 - d / 11 * 2.6, 0) + _BAYER[yy % 2, xx % 2] * 0.9
    rays = (np.abs(((ang + k * 2 * math.pi / n / 3) * 12 / (2 * math.pi)) % 1 - 0.5) < 0.22 - (d - 11) / 40) & (d >= 11) & (d < 18 - (k % 2))
    out = np.zeros((W, W, 4), np.uint8)
    body = d < 11
    out[body, :3] = P[np.clip(np.round(lvl), 1, 4).astype(int)][body]
    out[body, 3] = 255
    rim = (d >= 10) & (d < 11.4)
    out[rim, :3] = P[1]; out[rim, 3] = 255
    out[rays, :3] = P[3]; out[rays, 3] = 255
    tips = rays & (d >= 15)
    out[tips, :3] = P[2]
    glint = (np.abs(xx - c + 4) < 1.5) & (np.abs(yy - c + 4) < 1.5)
    out[glint, :3] = (255, 255, 240)
    edge = ndi.binary_dilation(out[..., 3] > 0) & (out[..., 3] == 0)
    out[edge, :3] = P[0]; out[edge, 3] = 255
    return Image.fromarray(out, 'RGBA')


def wave(k, n=8):
    """Solar Flare: a tall crescent of sun fire flying right (origin at its centre)."""
    W, H = 48, 72; cx, cy = 14, 36
    f = Flame(W, H, k, n, seed=111, speed=1.8, flow='back')
    X, Y = f.warp(2, 2)
    r = np.sqrt((X - cx) ** 2 + ((Y - cy) * 0.75) ** 2)
    front = np.clip((X - cx) / 26, 0, 1)
    env = np.clip(1 - np.abs(r - 24) / (3 + 5 * front), 0, 1) * (X > cx - 2)
    f.add(env ** 0.7 * 1.3, 1.2)
    return f.finish()


def swirl(k, n=12):
    """the power switch: his blue fire spins up, turns red and bursts (frames 0-5 blue, 6-11 sun)."""
    flame.use_palette('blue' if k < 6 else 'sun')
    W, H = 96, 112; bx, by = 48, 104
    f = Flame(W, H, k, n, seed=121, speed=1.6)
    X, Y = f.warp(4, 3)
    grow = min(1.0, (k + 1) / 6) if k < 6 else 1.0 + (k - 6) * 0.12
    u = np.clip((by - Y) / (90 * min(grow, 1.3)), 0, 1)
    spiral = 0.5 + 0.5 * np.sin((X - bx) * 0.25 + (by - Y) * 0.12 - k * 1.2)
    env = np.clip(1 - np.abs(X - bx) / (34 * grow - 12 * u), 0, 1) * (Y < by + 2) * (1 - u) ** 0.5 * (0.6 + 0.4 * spiral)
    if k >= 9:
        env *= 1 - (k - 9) / 4
    f.add(env, 1.3)
    return f.finish()


def glow_sun():
    W = 64; c = 31.5
    yy, xx = np.mgrid[0:W, 0:W]
    d = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / 31
    lvl = np.clip(1 - d, 0, 1) ** 1.5 * 3 + _BAYER[yy % 2, xx % 2] * 0.8
    out = np.zeros((W, W, 4), np.float32); out[..., :3] = (255, 140, 50); out[..., 3] = np.clip(np.floor(lvl), 0, 3) * 70
    return Image.fromarray(out.astype(np.uint8), 'RGBA')


def rbh_core(k, n=8):
    """the red black hole: a black disc, a white-hot ring, a dithered red halo."""
    W = 96; c = 47.5
    yy, xx = np.mgrid[0:W, 0:W]
    d = np.sqrt((xx - c) ** 2 + (yy - c) ** 2)
    flame.use_palette('sun'); P = flame.PAL
    R0 = 20 + (k % 2) * 0.5
    out = np.zeros((W, W, 4), np.uint8)
    halo = (d >= R0 + 1.5) & (d < R0 + 9) & (((xx + yy + k) % 2 == 0) | (d < R0 + 4))
    out[halo, :3] = P[1]; out[halo, 3] = 255
    ring = (d >= R0) & (d < R0 + 1.8)
    out[ring, :3] = P[4]; out[ring, 3] = 255
    ring2 = (d >= R0 + 1.8) & (d < R0 + 3)
    out[ring2, :3] = P[3]; out[ring2, 3] = 255
    out[d < R0, :3] = (2, 0, 0); out[d < R0, 3] = 255
    return Image.fromarray(out, 'RGBA')


def orb(name, seed):
    def f(k, n=8):
        flame.use_palette(name)
        W = 48 if name != 'purple' else 64; c = W / 2
        fl = Flame(W, W, k, n, seed=seed, speed=1.4)
        X, Y = fl.warp(2.5, 2.5)
        r = np.sqrt((X - c) ** 2 + (Y - c) ** 2) / (W * 0.36)
        env = np.clip(1 - r, 0, 1) ** 0.6
        if name == 'purple':                      # Hollow Purple: a void core inside a bright shell
            env = np.clip(1 - np.abs(r - 0.62) / 0.4, 0, 1) + np.clip(1 - r, 0, 1) * 0.35
        fl.add(env * 1.3, 1.2)
        im = np.array(fl.finish(dark=1.2 if name == 'purple' else 0.8))
        if name == 'purple':
            yy, xx = np.mgrid[0:W, 0:W]
            core = np.sqrt((xx - c + 0.5) ** 2 + (yy - c + 0.5) ** 2) < W * 0.13
            im[core, :3] = (12, 0, 20); im[core, 3] = 255
        return Image.fromarray(im, 'RGBA')
    return f


def nuke(k, n=12):
    """the purple nuclear blast, ground at y = 130: fireball -> mushroom cloud -> dissipating."""
    flame.use_palette('purple')
    W, H = 160, 144; cx, gy = 80, 130
    f = Flame(W, H, k, n, seed=141, speed=1.0)
    X, Y = f.warp(5, 4)
    t = k / (n - 1)
    if k < 3:                                         # the fireball swells off the ground
        R = 14 + 26 * (k + 1) / 3
        env = np.clip(1 - np.sqrt((X - cx) ** 2 + (Y - (gy - R * 0.8)) ** 2) / R, 0, 1) ** 0.5 * 1.3
    else:                                             # stem + cap rising, skirt along the ground
        rise = min(1.0, (k - 2) / 5)
        top = gy - 50 - 50 * rise
        capR = 26 + 16 * rise
        cap = np.clip(1 - np.sqrt(((X - cx) / (capR * 1.35)) ** 2 + ((Y - top) / capR) ** 2), 0, 1)
        stem = np.clip(1 - np.abs(X - cx) / (9 + 4 * rise + (gy - Y) * 0.04), 0, 1) * (Y > top) * (Y < gy)
        skirt = np.clip(1 - np.abs(Y - gy + 6) / 8, 0, 1) * np.clip(1 - np.abs(X - cx) / (30 + 40 * rise), 0, 1)
        fade = 1.0 if k < 8 else 1 - (k - 7) / 5
        env = np.clip(cap * 1.2 + stem + skirt * 0.8, 0, 1.3) * fade
    f.add(env, 1.3)
    return f.finish(dark=1.0 + t)


def ring(k, n=8):
    """a pixel shockwave ellipse in greys (the game tints it), expanding and thinning out."""
    W, H = 160, 56; c, cy = 79.5, 27.5
    yy, xx = np.mgrid[0:H, 0:W]
    t = (k + 1) / n
    R = 12 + 66 * t
    d = np.sqrt((xx - c) ** 2 + ((yy - cy) * 2.8) ** 2)
    band = np.abs(d - R) < 2.6 * (1 - t) + 1
    keep = band & ((xx + yy) % 2 == 0) if k >= n - 2 else band
    out = np.zeros((H, W, 4), np.uint8)
    out[keep] = (235, 235, 235, 255)
    inner = keep & (np.abs(d - R) < 1)
    out[inner] = (255, 255, 255, 255)
    return Image.fromarray(out, 'RGBA')


def sky(k, n=2):
    """cinematic backdrops: 0 = red (the black hole), 1 = purple (Hollow Purple); dithered bands + stars."""
    W, H = 320, 180
    top, bot = ((4, 0, 0), (120, 14, 6)) if k == 0 else ((6, 0, 12), (90, 24, 140))
    yy, xx = np.mgrid[0:H, 0:W]
    t = np.clip(yy / (H - 1) + _BAYER[yy % 2, xx % 2] * 0.12, 0, 1)
    steps = np.floor(t * 6) / 6
    rgb = np.array(top)[None, None] * (1 - steps[..., None]) + np.array(bot)[None, None] * steps[..., None]
    rng = np.random.default_rng(7 + k)
    for _ in range(90):
        x, y = rng.integers(0, W), rng.integers(0, int(H * 0.7))
        rgb[y, x] = (255, 230, 220) if k == 0 else (240, 220, 255)
    out = np.concatenate([rgb, np.full((H, W, 1), 255)], axis=2)
    return Image.fromarray(out.astype(np.uint8), 'RGBA')


# name: (frame function, frames, origin x, origin y)
def eye_glow():
    """soft white glow (pixel-stepped rings), tinted yellow by the game round the dark form's eyes."""
    im = Image.new('RGBA', (24, 24), (0, 0, 0, 0)); px = im.load()
    for y in range(24):
        for x in range(24):
            d = math.hypot(x + 0.5 - 12, y + 0.5 - 12) / 12
            if d < 1:
                a = int(255 * (1 - d) ** 1.6 / 32) * 32
                if a > 0: px[x, y] = (255, 255, 255, min(255, a))
    return im


SPRITES = {
    'js_sword': (sword, 6, 6, 10), 'js_shield': (shield, 8, 20, 20),
    'js_fist': (pal('sun', flame.fist), 8, 34, 30), 'js_trail': (pal('sun', flame.trail), 6, 92, 16),
    'js_burst': (pal('sun', flame.burst), 10, 56, 56), 'js_arc': (pal('sun', flame.arc), 6, 52, 70),
    'js_aura': (pal('sun', flame.aura), 8, 48, 104), 'js_wave': (pal('sun', wave), 8, 14, 36),
    'js_swirl': (swirl, 12, 48, 104), 'js_glow': (lambda k, n=1: glow_sun(), 1, 32, 32),
    'rbh_core': (rbh_core, 8, 48, 48),
    'rbh_disk_b': (pal('sun', lambda k, n=8: flame.bh_ring(k, n, False)), 8, 88, 48),
    'rbh_disk_f': (pal('sun', lambda k, n=8: flame.bh_ring(k, n, True)), 8, 88, 48),
    'hp_orb_b': (orb('blue', 151), 8, 24, 24), 'hp_orb_r': (orb('sun', 152), 8, 24, 24), 'hp_orb_p': (orb('purple', 153), 8, 32, 32),
    'hp_nuke': (nuke, 12, 80, 130), 'cin_ring': (ring, 8, 80, 28), 'cin_bg': (sky, 2, 0, 0),
    'jd_glow': (lambda k, n=1: eye_glow(), 1, 12, 12),
}


def build(out):
    os.makedirs(out, exist_ok=True)
    res = {}
    for name, (fn, n, ox, oy) in SPRITES.items():
        fr = [fn(k, n) for k in range(n)]
        _strip(fr).save(os.path.join(out, f'jeff_{name}.png'))
        res[name] = fr
    flame.use_palette('blue')
    return res


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else '/tmp'
    res = build(out)
    rows = []
    for name, fr in res.items():
        if name == 'cin_bg':
            continue
        w, h = fr[0].size
        row = Image.new('RGBA', (w * len(fr), h), (50, 60, 110, 255))
        for i, im in enumerate(fr):
            row.alpha_composite(im, (i * w, 0))
        rows.append(row)
    Wd = min(1600, max(r.width for r in rows)); Hd = sum(r.height + 4 for r in rows)
    sheet = Image.new('RGBA', (Wd, Hd), (20, 20, 30, 255)); y = 0
    for r in rows:
        sheet.alpha_composite(r.crop((0, 0, min(Wd, r.width), r.height)), (0, y)); y += r.height + 4
    sheet.save(os.path.join(out, 'sun_preview.png'))
    print('sun ok')
