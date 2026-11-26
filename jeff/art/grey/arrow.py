"""INFERNO ARROW - Grey's bow ultimate: the art (all generated, registered into fx.SPRITES).

* bow        - his glitch bow (the stance weapon): dark limbs, cyan edge, magenta glitch pixels, a taut string.
                Drawn along +x from the grip at (28, 12); the limbs' tips sit on the archer's side (-y).
* firebow    - the giant bow of fire for the close-up (sun-palette pixel flame, flickering), grip at (104, 224),
                its tips curving back toward the archer (left), at (24, 14) and (24, 434).
* firetrail  - the arrow in flight: a long tapered streak of fire, hot head on the right (origin at the head).
* speedring  - an anime speed ring: a broken white ellipse the arrow punches through.
* ia_sky     - the sunset sky over the dusty plain: slate cloud bands lit orange from below, a hidden sun.
* ia_hills   - rocky ridges, tileable left-right (they scroll under the flying arrow).
* ia_top     - the plain seen from straight above: dry earth, cracks, rocks.
* ia_crater  - the impact from above: white-hot core, molten cracks, a dust shock ring, debris streaks.
* ia_cloud   - the mushroom cloud, flat cel-shaded puffs, 8 stages of growth (origin at its base).
* ia_splash  - the white-out's black ink silhouette: a spike of earth and flame thrown up, on the ground line.
"""
import math, random
import numpy as np
from PIL import Image, ImageDraw
import flame
from flame import Flame
from moonfall import fbm

CYAN, MAGENTA, WHITE = (60, 230, 255), (255, 60, 210), (255, 255, 255)
INK = (24, 16, 14)


def _rgba(w, h): return np.zeros((h, w, 4), np.uint8)
def _put(a, x, y, col, al=255):
    if 0 <= x < a.shape[1] and 0 <= y < a.shape[0]: a[y, x, :3] = col; a[y, x, 3] = al


# --------------------------------------------------------------------------------------------
# the stance bow and the giant fire bow
# --------------------------------------------------------------------------------------------
def bow(k, n=4, W=56, H=16, gx=28, gy=12):
    a = _rgba(W, H)
    rng = random.Random(70 + k)
    ys = []
    for x in range(W):
        t = abs(x + 0.5 - gx) / (W / 2)
        y = gy - 9.0 * t ** 1.7
        ys.append(y)
        th = 2.2 - 1.2 * t
        for yy in range(int(y - th), int(y + 1) + 1):
            if yy < y - th + 0.5: _put(a, x, yy, CYAN)                     # the back of the limb: a cyan edge
            else: _put(a, x, yy, (44, 46, 56) if yy <= y else (26, 26, 32))
    for y in range(int(ys[0]) - 1, int(ys[0]) + 1): _put(a, 0, y, WHITE)
    for y in range(int(ys[-1]) - 1, int(ys[-1]) + 1): _put(a, W - 1, y, WHITE)
    for x in range(1, W - 1):                                              # the string, tip to tip
        _put(a, x, int(round(min(ys[0], ys[-1]))), (205, 215, 230), 210)
    for y in range(gy - 3, gy + 3):                                       # the grip: cyan wrap
        for x in range(gx - 2, gx + 2): _put(a, x, y, (30, 140, 160) if (x + y) % 2 else CYAN)
    for _ in range(4):                                                    # glitch pixels on the limbs
        x = rng.randint(2, W - 3); y = int(ys[x]) - rng.randint(0, 1)
        _put(a, x, y, MAGENTA)
    return Image.fromarray(a, 'RGBA')


def firebow(k, n=6, W=128, H=448, gx=104, gy=224, tx=24):
    flame.use_palette('sun')
    f = Flame(W, H, k, n, seed=81, speed=1.3, flow='up')
    X, Y = f.warp(3.0, 4.0)
    half = (H - 28) / 2
    u = np.clip(np.abs(Y - gy) / half, 0, 1.08)
    cx = gx - (gx - tx) * u ** 1.8                                       # the limb's centre line
    th = 15.0 - 7.0 * u                                                  # thick at the grip, thinner at the tips
    env = np.clip(1 - np.abs(X - cx) / th, 0, 1) * (u <= 1.0)
    lick = (f.n2 - 0.5) * 18                                             # flame tongues streaming off the limb
    tongues = np.clip(1 - np.abs(X - cx + 4 + lick) / (th * 1.5), 0, 1) * (0.5 + 0.5 * f.n3) * (u <= 1.02)
    grip = np.clip(1 - np.hypot(X - gx, (Y - gy) * 0.6) / 28, 0, 1)
    tips = sum(np.clip(1 - np.hypot(X - tx, Y - ty) / 12, 0, 1) for ty in (gy - half, gy + half))
    f.add(env ** 0.6 * (1.2 - 0.25 * u), 1.4)
    f.add(tongues, 1.15)
    f.add(grip ** 0.8, 1.4)
    f.add(tips, 1.1)
    im = f.finish(dark=0.35)
    flame.use_palette('blue')
    return im


def firetrail(k, n=6, W=256, H=48):
    flame.use_palette('sun')
    f = Flame(W, H, k, n, seed=91, speed=2.4, flow='back')
    X, Y = f.warp(3.0, 1.6)
    t = np.clip(X / (W - 16), 0, 1)
    env = np.clip(1 - np.abs(Y - H / 2) / (1.5 + 13 * t ** 1.4), 0, 1) * np.clip(t * 1.4, 0, 1) * (X < W - 16)
    head = np.clip(1 - np.hypot((X - (W - 16)) * 1.25, Y - H / 2) / 15, 0, 1)    # a rounded, white-hot head
    f.add(env ** 0.8 * (0.45 + 0.75 * t), 1.3)
    f.add(head, 1.6)
    im = f.finish(dark=0.5)
    flame.use_palette('blue')
    return im


def speedring(k, n=4, W=40, H=112):
    im = Image.new('RGBA', (W * 4, H * 4), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    rng = random.Random(500 + k)
    cx, cy, rx, ry = W * 2, H * 2, W * 2 - 10, H * 2 - 10
    a = 0.0
    while a < 360:
        span = rng.uniform(40, 110); gap = rng.uniform(10, 40)
        wdt = rng.choice((6, 8, 10))
        d.arc((cx - rx, cy - ry, cx + rx, cy + ry), a, a + span, fill=(255, 255, 255, 255), width=wdt)
        a += span + gap
    return im.resize((W, H), Image.LANCZOS)


# --------------------------------------------------------------------------------------------
# backdrops (flat anime cel shading: a few tones, hard edges)
# --------------------------------------------------------------------------------------------
def _cel(v, stops, cols):
    """quantise a 0..1 field to hard colour bands."""
    out = np.zeros(v.shape + (3,), np.float32); out[...] = cols[0]
    for s, c in zip(stops, cols[1:]): out[v >= s] = c
    return out


def ia_sky(k=0, n=1, W=320, H=180):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    v = yy / H
    top, mid, low = np.array([62, 74, 92]), np.array([142, 104, 78]), np.array([238, 176, 104])
    col = np.where(v[..., None] < 0.55, top + (mid - top) * (v / 0.55)[..., None],
                   mid + (low - mid) * ((v - 0.55) / 0.45)[..., None])
    sun = np.exp(-(((xx - W * 0.22) / (W * 0.16)) ** 2 + ((yy - H * 0.62) / (H * 0.2)) ** 2))   # the sun behind the dust
    col = col + sun[..., None] * np.array([110, 80, 30])
    nz = fbm(xx / 90.0, yy / 22.0, np.full_like(xx, 3.1), 5)                        # stretched cloud bands
    band = nz + 0.35 * np.sin(yy / H * 7.0) - 0.25 * v
    cloud = band > 0.0
    lit = (fbm(xx / 90.0, (yy + 4) / 22.0, np.full_like(xx, 3.1), 5) + 0.35 * np.sin((yy + 4) / H * 7.0) - 0.25 * (v + 4 / H)) <= 0.0
    ccol = _cel(nz, [0.25], [np.array([66, 74, 90]), np.array([104, 110, 124])])
    ccol = np.where((cloud & lit)[..., None], np.array([226, 170, 120]), ccol)      # undersides lit orange
    col = np.where(cloud[..., None], ccol, col)
    dust = fbm(xx / 40.0, yy / 30.0, np.full_like(xx, 8.0), 4) + (v - 0.8) * 2.2     # dust billowing at the bottom
    dcol = _cel(dust, [0.45, 0.62], [np.array([120, 92, 70]), np.array([150, 116, 88]), np.array([186, 150, 112])])
    col = np.where((dust > 0.3)[..., None], dcol, col)
    a = np.dstack([np.clip(col, 0, 255), np.full((H, W), 255)]).astype(np.uint8)
    return Image.fromarray(a, 'RGBA')


def ia_hills(k=0, n=1, W=320, H=72):
    a = np.zeros((H, W, 4), np.uint8)
    xs = np.arange(W) / W * 2 * math.pi
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    ang = xx / W * 2 * math.pi                                                     # wrap the noise round a cylinder: tiles
    FACET = fbm(np.cos(ang) * 3.2, yy / 9.0, np.sin(ang) * 3.2, 3)
    FACET = (FACET - FACET.min()) / (FACET.max() - FACET.min())
    for layer, (base, amp, cols) in enumerate(((24, 14, ((126, 96, 74), (96, 72, 56), (166, 128, 96))),
                                               (44, 10, ((104, 78, 60), (74, 54, 42), (148, 112, 84))))):
        h = base + amp * (0.6 * np.sin(xs * 3 + layer) + 0.3 * np.sin(xs * 7 + 1.7 * layer) + 0.2 * np.sin(xs * 13 + 2))
        h += 3 * np.sign(np.sin(xs * 23 + layer))                                  # jagged rock steps
        for x in range(W):
            top = int(H - h[x] - 24 + layer * 10)
            for y in range(max(0, top), H):
                c = cols[0]
                if y < top + 2: c = cols[2]                                         # lit ridge line
                elif FACET[y, x] > 0.6: c = cols[1]                                 # shadowed rock facets
                elif FACET[y, x] < 0.22: c = cols[2]                                # lit facets
                a[y, x, :3] = c; a[y, x, 3] = 255
    return Image.fromarray(a, 'RGBA')


def ia_top(k=0, n=1, W=320, H=180):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    nz = fbm(xx / 50.0, yy / 50.0, np.full_like(xx, 1.7), 5)
    col = _cel(nz, [0.42, 0.6], [np.array([128, 96, 72]), np.array([152, 116, 86]), np.array([176, 138, 104])])
    cr = fbm(xx / 16.0, yy / 16.0, np.full_like(xx, 5.3), 3, ridged=True)
    col = np.where((cr > 0.78)[..., None], np.array([88, 64, 48]), col)            # dry cracks
    img = Image.fromarray(np.dstack([col, np.full((H, W), 255)]).astype(np.uint8), 'RGBA')
    d = ImageDraw.Draw(img); rng = random.Random(9)
    for _ in range(46):                                                         # rocks: shadow, body, lit top-left
        x, y, r = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(1.5, 5)
        d.ellipse((x - r + 1.5, y - r * 0.8 + 1.5, x + r + 1.5, y + r * 0.8 + 1.5), fill=(70, 50, 38, 255))
        d.ellipse((x - r, y - r * 0.8, x + r, y + r * 0.8), fill=(150, 118, 92, 255))
        d.ellipse((x - r * 0.7, y - r * 0.7, x + r * 0.1, y), fill=(196, 160, 122, 255))
    return img


def ia_crater(k, n=8, S=192):
    t = k / (n - 1)
    c = S / 2
    im = Image.new('RGBA', (S * 2, S * 2), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    Z = 2
    rng = random.Random(120)
    R = (16 + 74 * t ** 0.6)
    def blob(r, jag, col):
        pts = []
        for i in range(72):
            ang = 2 * math.pi * i / 72
            rr = r * (1 + jag * (math.sin(ang * 7 + 1.3) * 0.5 + math.sin(ang * 13 + 0.4) * 0.3 + rng.uniform(-0.4, 0.4)))
            pts.append(((c + math.cos(ang) * rr) * Z, (c + math.sin(ang) * rr) * Z))
        d.polygon(pts, fill=col)
    ring_w = 6 + 10 * t
    blob(R + ring_w + 2, 0.07, (92, 68, 52, 255))                               # the dust shock ring, ragged
    blob(R + ring_w, 0.06, (222, 200, 168, 255))
    blob(R, 0.05, (176, 146, 116, 255))
    for i in range(54):                                                         # debris streaks thrown out radially
        ang = rng.uniform(0, 2 * math.pi); r0 = R * rng.uniform(0.95, 1.1); r1 = R * rng.uniform(1.25, 1.6)
        w = rng.choice((2, 3, 4)) * Z
        d.line(((c + math.cos(ang) * r0) * Z, (c + math.sin(ang) * r0) * Z, (c + math.cos(ang) * r1) * Z,
                (c + math.sin(ang) * r1) * Z), fill=(70, 50, 38, int(255 * (1 - 0.6 * t))), width=w)
    rin = R * 0.72                                                              # the crater: dark, molten cracks
    blob(rin, 0.06, (58, 36, 30, 255))
    hot = 1 - t
    for i in range(14):
        ang = rng.uniform(0, 2 * math.pi); pts = [(c * Z, c * Z)]
        r = 0
        while r < rin * 0.95:
            r += rng.uniform(4, 9); ang += rng.uniform(-0.4, 0.4)
            pts.append(((c + math.cos(ang) * r) * Z, (c + math.sin(ang) * r) * Z))
        d.line(pts, fill=(255, int(120 + 110 * hot), int(40 * hot), int(255 * (0.35 + 0.65 * hot))), width=2 * Z)
    core = rin * (0.45 * hot + 0.12)
    d.ellipse(((c - core) * Z, (c - core) * Z, (c + core) * Z, (c + core) * Z), fill=(255, 236, 170, int(255 * (0.4 + 0.6 * hot))))
    return im.resize((S, S), Image.LANCZOS)


def _puff(d, x, y, r, base, shade, light, ink):
    d.ellipse((x - r - 2, y - r - 2, x + r + 2, y + r + 2), fill=ink)
    d.ellipse((x - r, y - r, x + r, y + r), fill=shade)
    d.ellipse((x - r, y - r, x + r * 0.55, y + r * 0.55), fill=base)
    d.ellipse((x - r * 0.75, y - r * 0.8, x - r * 0.05, y - r * 0.1), fill=light)


def ia_cloud(k, n=8, W=192, H=224):
    t = (k + 1) / n
    Z = 2
    im = Image.new('RGBA', (W * Z, H * Z), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    base, shade, light, ink = (164, 124, 98, 255), (124, 90, 72, 255), (202, 166, 136, 255), (88, 62, 50, 255)
    rng = random.Random(77)
    cx, gy = W / 2, H - 4
    capy = gy - (52 + 118 * t ** 0.8); capr = 22 + 50 * t ** 0.9; stw = 10 + 14 * t
    for i in range(10):                                                         # the skirt of dust at the base
        x = cx + rng.uniform(-1, 1) * (30 + 50 * t); r = rng.uniform(10, 18) * (0.6 + 0.6 * t)
        _puff(d, x * Z, (gy - r * 0.5) * Z, r * Z, base, shade, light, ink)
    steps = 9
    for i in range(steps):                                                      # the stem, bottom to top
        y = gy - (gy - capy) * i / steps
        r = stw * (1.0 + 0.6 * (1 - i / steps) ** 2) + rng.uniform(-2, 2)
        _puff(d, (cx + rng.uniform(-3, 3)) * Z, y * Z, r * Z, base, shade, light, ink)
    for ring, (rf, cnt) in enumerate(((1.0, 12), (0.62, 8), (0.25, 4))):          # the cap: rings of puffs
        for i in range(cnt):
            ang = 2 * math.pi * i / cnt + ring * 0.4
            x = cx + math.cos(ang) * capr * rf; y = capy + math.sin(ang) * capr * rf * 0.62
            r = capr * (0.36 - 0.06 * ring) + rng.uniform(-2, 2)
            _puff(d, x * Z, y * Z, r * Z, base, shade, light, ink)
    for i in range(5):                                                          # darker rounded clumps in the cap
        x = cx + rng.uniform(-0.6, 0.6) * capr; y = capy + rng.uniform(-0.4, 0.3) * capr
        r = capr * 0.16
        d.ellipse(((x - r) * Z, (y - r) * Z, (x + r) * Z, (y + r) * Z), outline=ink, width=2 * Z)
    return im.resize((W, H), Image.LANCZOS)


def ia_splash(k=0, n=1, W=224, H=128):
    im = Image.new('RGBA', (W * 2, H * 2), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    Z = 2; gy = H - 8
    rng = random.Random(33)
    pts = [(10, gy)]                                                            # a jagged spike of earth and flame
    for x, y in ((60, gy - 6), (84, gy - 22), (96, gy - 40), (104, gy - 70), (110, gy - 110), (114, gy - 66),
                 (124, gy - 44), (138, gy - 24), (166, gy - 6), (214, gy)):
        pts.append((x + rng.uniform(-3, 3), y))
    d.polygon([(x * Z, y * Z) for x, y in pts], fill=INK + (255,))
    for i in range(16):                                                         # splatter flung out
        ang = rng.uniform(math.pi * 1.05, math.pi * 1.95); r = rng.uniform(40, 100)
        x, y = 112 + math.cos(ang) * r, gy + math.sin(ang) * r * 0.8
        s = rng.uniform(2, 6)
        d.polygon([((x - s) * Z, y * Z), (x * Z, (y - s * 2.2) * Z), ((x + s) * Z, y * Z), (x * Z, (y + s) * Z)], fill=INK + (255,))
    d.rectangle((0, (gy) * Z, W * Z, (gy + 3) * Z), fill=INK + (255,))
    return im.resize((W, H), Image.LANCZOS)


SPRITES = {
    'bow': (bow, 4, 28, 12), 'firebow': (firebow, 6, 104, 224), 'firetrail': (firetrail, 6, 240, 24),
    'speedring': (speedring, 4, 20, 56), 'ia_sky': (ia_sky, 1, 0, 0), 'ia_hills': (ia_hills, 1, 0, 0),
    'ia_top': (ia_top, 1, 0, 0), 'ia_crater': (ia_crater, 8, 96, 96), 'ia_cloud': (ia_cloud, 8, 96, 220),
    'ia_splash': (ia_splash, 1, 112, 120),
}
