"""The void left behind after SINGULARITY: the stage is replaced by deep space with floating rocks.

  void_sky   (2 frames, 320x180, normal)  deep violet space, nebulae, faded multiverse galaxies
  void_rocks (8 frames, 80x64,   normal)  floating rock islands (drawn by the game at many positions
                                          and scales, bobbing, with parallax)
  void_floor (1 frame, 256x48,   normal)  fractured floating-stone ground, tiles horizontally; the
                                          fighters stand on its top edge (origin y = 8)
  void_dust  (8 frames, 8x8,     normal)  drifting pebbles
Rocks and floor are pixel art shaded like the rooster (rig.Canvas), with violet glowing fissures.
"""
import math, os, sys
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rig
from rig import Canvas, _m

STONE = _m((70, 56, 104), (118, 100, 162), (40, 30, 66), (110, 200, 255), (18, 12, 32))
STONE2 = _m((56, 44, 88), (96, 82, 140), (30, 22, 52), (90, 170, 240), (14, 10, 26))
FISSURE = (190, 100, 255, 255)
FISSURE_HOT = (240, 200, 255, 255)
CRYSTAL = _m((150, 90, 240), (230, 190, 255), (90, 40, 170), (200, 240, 255), (40, 12, 80))


def rock(seed, w=80, h=64):
    rng = np.random.default_rng(seed)
    c = Canvas(w, h, w // 2, h // 2)
    top_y = -6 + rng.uniform(-2, 2)
    n = 11
    xs = np.linspace(-30, 30, n) * rng.uniform(0.75, 1.0)
    top = [(x, top_y + rng.uniform(-3.5, 1.5)) for x in xs]
    # tapered rocky underside, like a hanging root of stone
    depth = rng.uniform(18, 28)
    tipx = rng.uniform(-6, 6)
    under = []
    for i, x in enumerate(xs[::-1]):
        t = abs(x) / 30
        y = top_y + 4 + (1 - t ** 1.6) * depth + rng.uniform(-2.5, 2.5)
        under.append((x * (0.95 - 0.2 * (1 - t)), y))
    under.insert(n // 2, (tipx, top_y + depth + 8))
    poly = top + under
    m = c.poly(poly)
    c.paint(m, STONE, bump=2.6)
    # strata bands
    for k in range(3):
        y0 = top_y + 6 + k * 6
        band = c.taper([(-30, y0 + rng.uniform(-1, 1)), (30, y0 + rng.uniform(-1, 1))], 0.45, 0.45) & m
        c.img[band] = STONE['shadow']
    # glowing fissures
    for k in range(2):
        x0 = rng.uniform(-14, 14)
        pts = [(x0, top_y + 2)]
        for s in range(4):
            pts.append((pts[-1][0] + rng.uniform(-4, 4), pts[-1][1] + rng.uniform(3, 6)))
        f = c.taper(pts, 0.55, 0.3) & m
        c.img[f] = FISSURE
        c.img[c.taper(pts[:2], 0.35, 0.3) & m] = FISSURE_HOT
    # crystals on top
    for k in range(rng.integers(1, 4)):
        x = rng.uniform(-20, 20); hgt = rng.uniform(4, 9)
        cm = c.poly([(x - 2.2, top_y + 1), (x + rng.uniform(-1, 1), top_y - hgt), (x + 2.2, top_y + 1)])
        c.paint(cm, CRYSTAL, shade=1, hl=1, rim=1)
    c.outline()
    img = c.img.copy()
    # faint violet glow under the fissures (baked, partial alpha)
    gl = ndi.gaussian_filter(((img[..., 0] > 180) & (img[..., 2] > 240)).astype(np.float32), 2.0)
    empty = img[..., 3] == 0
    a = np.clip(gl * 1.2, 0, 1) * 0.55
    img[empty, 0], img[empty, 1], img[empty, 2] = 160, 80, 250
    img[empty, 3] = (a[empty] * 255).astype(np.uint8)
    return Image.fromarray(img, 'RGBA')


def rock_images():
    return [rock(100 + i) for i in range(8)]


def floor():
    W, H = 256, 48
    rng = np.random.default_rng(42)
    c = Canvas(W, H, 0, 8)
    # periodic surface so the strip tiles seamlessly
    xs = np.linspace(0, W, 33)
    surf = [(x, -0.5 + 1.2 * math.sin(2 * math.pi * x / W * 3) + 0.8 * math.sin(2 * math.pi * x / W * 7 + 1)) for x in xs]
    under = []
    for i, x in enumerate(xs[::-1]):
        y = 14 + 10 * (0.5 + 0.5 * math.sin(2 * math.pi * x / W * 5 + 0.7)) + 8 * (0.5 + 0.5 * math.sin(2 * math.pi * x / W * 11))
        under.append((x, y))
    m = c.poly(surf + under)
    c.paint(m, STONE, bump=2.2)
    # top surface highlight + cracks
    top = m & ~rig.shift(m, 0, 2)
    c.img[top] = STONE['light']
    for k in range(9):
        x0 = (k + 0.5) * W / 9 + rng.uniform(-8, 8)
        pts = [(x0, 0.5)]
        for s in range(4):
            pts.append((pts[-1][0] + rng.uniform(-5, 5), pts[-1][1] + rng.uniform(2.5, 5)))
        f = c.taper(pts, 0.5, 0.3) & m
        c.img[f] = FISSURE
    c.outline()
    img = c.img.copy()
    # underside fades away into the void
    fade = np.clip(1 - (np.arange(H) - 26) / 22, 0, 1)
    img[..., 3] = (img[..., 3].astype(np.float32) * fade[:, None]).astype(np.uint8)
    return Image.fromarray(img, 'RGBA')


def sky(k):
    import cutscene
    gal = [(70, 40, 26, (60, 200, 220), 0.4), (250, 30, 22, (240, 190, 80), -0.6), (160, 70, 30, (230, 80, 220), 0.9)]
    a = cutscene.space_bg(13 + k, dim=0.78, galaxies=gal)
    return Image.fromarray(a.astype(np.uint8)).convert('RGBA')


def dust(k):
    im = Image.new('RGBA', (8, 8), (0, 0, 0, 0))
    a = np.array(im)
    pts = [(3, 3), (4, 3), (3, 4), (4, 4), (2, 3) if k % 2 else (5, 4)]
    for x, y in pts:
        a[y, x] = (90, 72, 130, 255)
    a[3, 3] = (170, 140, 230, 255)
    return Image.fromarray(a, 'RGBA')


def strip(frames):
    w, h = frames[0].size
    s = Image.new('RGBA', (w * len(frames), h), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        s.paste(f, (i * w, 0))
    return s


def build(out):
    os.makedirs(out, exist_ok=True)
    strip([sky(0), sky(1)]).save(os.path.join(out, 'scyther_void_sky.png'))
    rocks = rock_images()
    strip(rocks).save(os.path.join(out, 'scyther_void_rocks.png'))
    floor().save(os.path.join(out, 'scyther_void_floor.png'))
    strip([dust(k) for k in range(8)]).save(os.path.join(out, 'scyther_void_dust.png'))
    return rocks


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else '/tmp'
    rocks = build(out)
    # preview: a mock arena after the ultimate
    bg = np.array(sky(0).convert('RGB')).astype(np.float32)
    def put(im, x, y, sc=1.0):
        im = im.resize((int(im.width * sc), int(im.height * sc)), Image.NEAREST)
        arr = np.array(im).astype(np.float32); h, w = arr.shape[:2]
        x0, y0 = max(0, x), max(0, y); x1, y1 = min(320, x + w), min(180, y + h)
        if x1 <= x0 or y1 <= y0: return
        sub = arr[y0 - y:y1 - y, x0 - x:x1 - x]; al = sub[..., 3:4] / 255
        bg[y0:y1, x0:x1] = bg[y0:y1, x0:x1] * (1 - al) + sub[..., :3] * al
    for i, (x, y, sc) in enumerate(((30, 40, 0.6), (110, 20, 0.45), (210, 30, 0.7), (280, 70, 0.5), (60, 95, 0.8), (250, 105, 0.9))):
        put(rocks[i], x, y, sc)
    fl = floor()
    for x in (-60, 196):
        put(fl, x, 132)
    Image.fromarray(bg.astype(np.uint8)).resize((960, 540), Image.NEAREST).save(os.path.join(out, 'void_preview.png'))
    print('void ok')
