"""Grey's pixel-art effects: glitch, clones, glitch blades, ice, fire (from ../flame.py), lightning,
shock rings, error text, the HUD card and the select-screen preview."""
import math, os, sys, random
import numpy as np
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import flame
from flame import _strip
import skel, poses

CYAN, MAGENTA, WHITE, BLACK = (60, 230, 255), (255, 60, 210), (255, 255, 255), (8, 8, 12)
ICE = [(16, 40, 80), (40, 110, 180), (110, 200, 245), (200, 245, 255), (255, 255, 255)]


def rgba(w, h): return np.zeros((h, w, 4), np.uint8)


def put(a, x, y, col, al=255):
    if 0 <= x < a.shape[1] and 0 <= y < a.shape[0]:
        a[y, x, :3] = col; a[y, x, 3] = al


def shape(k, n=2):
    """frame 0: a white square, frame 1: a white disc (the stickman is drawn from these, tinted)."""
    a = rgba(32, 32)
    if k == 0:
        a[...] = 255
    else:
        yy, xx = np.mgrid[0:32, 0:32]
        m = (xx + 0.5 - 16) ** 2 + (yy + 0.5 - 16) ** 2 <= 16 ** 2
        a[m] = 255
    return Image.fromarray(a, 'RGBA')


def glitch(k, n=8):
    """a burst of glitch blocks: white / cyan / magenta / black rectangles, scattering and thinning."""
    rng = random.Random(900 + k * 13)
    a = rgba(48, 48)
    life = 1 - k / n
    for _ in range(int(26 * life) + 4):
        w, h = rng.randint(2, 12), rng.randint(1, 4)
        r = (k + 2) * 2.4 * rng.random()
        ang = rng.random() * 6.283
        cx, cy = 24 + math.cos(ang) * r, 24 + math.sin(ang) * r * 0.8
        col = rng.choice((WHITE, CYAN, MAGENTA, BLACK, CYAN, WHITE))
        x0, y0 = int(cx - w / 2), int(cy - h / 2)
        a[max(0, y0):max(0, min(48, y0 + h)), max(0, x0):max(0, min(48, x0 + w)), :3] = col
        a[max(0, y0):max(0, min(48, y0 + h)), max(0, x0):max(0, min(48, x0 + w)), 3] = 255
    return Image.fromarray(a, 'RGBA')


def spark(k, n=6):
    """a hit spark: white star with chromatic fringes."""
    a = rgba(32, 32); d_ = 1 - k / n
    L = int(4 + 11 * (1 - (1 - k / n) ** 3))
    for ang in range(0, 360, 45):
        ln = L if ang % 90 == 0 else int(L * 0.6)
        for i in range(ln):
            x = 16 + round(math.cos(math.radians(ang)) * i); y = 16 + round(math.sin(math.radians(ang)) * i)
            if i > ln * d_: continue
            put(a, x - 1, y, CYAN); put(a, x + 1, y, MAGENTA); put(a, x, y, WHITE)
    return Image.fromarray(a, 'RGBA')


def arc(k, n=6):
    """a sword swing: a crescent from up-back to down-front, white core, cyan / magenta edges."""
    a = rgba(64, 64)
    span = 200 * min(1, (k + 1) / 3)
    fade = 1 - max(0, k - 2) / (n - 2)
    for i in range(160):
        t = i / 159
        ang = math.radians(-120 + span * t)
        thick = (1 - abs(t - 0.6) / 0.6) * 5 * fade
        if thick < 0.5: continue
        for r in np.arange(26 - thick, 26 + thick, 0.5):
            x, y = int(32 + math.cos(ang) * r), int(32 + math.sin(ang) * r)
            inner = abs(r - 26) < thick * 0.45
            put(a, x, y, WHITE if inner else (CYAN if r < 26 else MAGENTA))
    return Image.fromarray(a, 'RGBA')


def ring(k, n=8):
    """a flat shock ring (white, tinted in game), expanding."""
    W, H = 96, 32
    a = rgba(W, H)
    R = 10 + 36 * (1 - (1 - (k + 1) / n) ** 2)
    th = 3.0 * (1 - k / n) + 1
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx + 0.5 - 48) / R) ** 2 + ((yy + 0.5 - 16) / (R * 0.28)) ** 2)
    m = np.abs(d - 1) < th / R
    a[m] = (255, 255, 255, 255)
    return Image.fromarray(a, 'RGBA')


def ice_px(v):
    i = int(np.clip(v, 0, 4)); return ICE[i]


def spike(k, n=10):
    """an ice spike bursting out of the ground: grows (0-3), holds (4-6), cracks and falls apart (7-9)."""
    W, H = 32, 48
    a = rgba(W, H)
    grow = min(1.0, (k + 1) / 4)
    h = int(44 * (grow if k < 7 else 1.0))
    shatter = max(0, k - 6) / 3
    rng = random.Random(77)
    for y in range(h):
        frac = y / max(1, h)                     # 0 at the tip
        half = 1 + 7 * frac
        yy = H - h + y
        for x in range(int(16 - half), int(16 + half) + 1):
            side = (x - 16) / max(1, half)
            v = 2.6 - 1.6 * side + (0.8 if abs(side) < 0.25 else 0) - frac * 0.6
            if shatter and rng.random() < shatter * 0.8: continue
            put(a, x + (int(side * 6 * shatter) if shatter else 0), yy + int(shatter * 6 * rng.random()), ice_px(v))
    # outline
    al = a[..., 3] > 0
    from scipy import ndimage as ndi
    o = ndi.binary_dilation(al) & ~al
    a[o] = (10, 30, 60, 255)
    if k in (4, 5):                                # glint
        put(a, 14, H - h + 8, WHITE); put(a, 15, H - h + 7, WHITE)
    return Image.fromarray(a, 'RGBA')


def shard(k, n=4):
    a = rgba(12, 12)
    ang = k * math.pi / 4
    for i in range(-5, 6):
        x, y = 6 + round(math.cos(ang) * i), 6 + round(math.sin(ang) * i * 0.6)
        put(a, x, y, ICE[3] if abs(i) < 3 else ICE[2])
        if abs(i) < 2: put(a, x, y - 1, WHITE)
    return Image.fromarray(a, 'RGBA')


def shatter(k, n=10):
    """shards and glitch pixels flying out."""
    a = rgba(64, 64)
    rng = random.Random(55)
    for i in range(40):
        ang = rng.random() * 6.283; sp = 1.5 + rng.random() * 3.0
        r = sp * (k + 1) * 1.6
        x, y = 32 + math.cos(ang) * r, 32 + math.sin(ang) * r + 0.25 * (k + 1) ** 2 * 0.5
        if rng.random() < k / n * 0.9: continue
        col = rng.choice((ICE[3], ICE[2], WHITE, CYAN, MAGENTA))
        s = 2 if i % 3 else 1
        for dx in range(s):
            for dy in range(s): put(a, int(x) + dx, int(y) + dy, col)
    return Image.fromarray(a, 'RGBA')


def blade(k, n=4, L=48, grip=4, w=3):
    """a glitch blade pointing right: black core, cyan / magenta RGB-split edges, flickering slices."""
    H = 12
    a = rgba(L, H)
    rng = random.Random(300 + k)
    for x in range(grip + 2, L):
        t = (x - grip) / (L - grip)
        half = w * (1 - t ** 3) + 0.6
        off = (rng.randint(-1, 1) if rng.random() < 0.18 else 0)
        for y in range(int(6 - half - 1), int(6 + half + 2)):
            yy = y + off
            if abs(y - 6) <= half - 0.5: put(a, x, yy, (24, 24, 30) if abs(y - 6) > 0.5 else WHITE)
            elif y < 6: put(a, x, yy, CYAN)
            else: put(a, x, yy, MAGENTA)
    for x in range(0, grip + 2):                     # hilt
        put(a, x, 6, (40, 40, 46)); put(a, x, 5, (70, 70, 80))
    for y in range(2, 10): put(a, grip + 1, y, (200, 200, 210))
    return Image.fromarray(a, 'RGBA')


def spear(k, n=4):
    a = np.array(blade(k, n, L=80, grip=30, w=2.2))
    a[5:7, 0:30, :3] = (46, 46, 52); a[5:7, 0:30, 3] = 255
    return Image.fromarray(a, 'RGBA')


def bolt(k, n=6):
    """a lightning bolt, top to bottom (centre origin), white core with violet-cyan glow."""
    W, H = 32, 96
    a = rgba(W, H)
    rng = random.Random(40 + k // 2)
    x = 16.0
    pts = []
    for y in range(0, H, 6):
        pts.append((x, y)); x = float(np.clip(x + rng.uniform(-6, 6), 4, W - 5))
    pts.append((x, H - 1))
    im = Image.fromarray(a, 'RGBA'); d = ImageDraw.Draw(im)
    fade = 1 - k / n
    d.line(pts, fill=(120, 90, 255, int(200 * fade)), width=5)
    d.line(pts, fill=CYAN + (int(255 * fade),), width=3)
    d.line(pts, fill=WHITE + (255,), width=1)
    return im


def text_img(txt, k, n, W, H, scale=2):
    """pixel text with an RGB split and slices shifted by the glitch."""
    small = Image.new('L', (W // scale, H // scale), 0)
    d = ImageDraw.Draw(small)
    tw = d.textlength(txt)
    d.text(((W // scale - tw) / 2, (H // scale - 11) / 2), txt, fill=255)
    m = np.array(small.resize((W, H), Image.NEAREST)) > 128
    a = rgba(W, H)
    rng = random.Random(k * 7)
    for dx, col in ((-2, CYAN), (2, MAGENTA), (0, WHITE)):
        mm = np.roll(m, dx + (rng.randint(-1, 1) if k % 2 else 0), axis=1)
        a[mm, :3] = col; a[mm, 3] = 255
    for _ in range(3):                                 # sliced rows
        y0 = rng.randint(0, H - 4); hh = rng.randint(1, 3); sh = rng.randint(-5, 5)
        a[y0:y0 + hh] = np.roll(a[y0:y0 + hh], sh, axis=1)
    return Image.fromarray(a, 'RGBA')


def error_txt(k, n=4): return text_img('ERROR', k, n, 96, 24)
def fatal_txt(k, n=4): return text_img('FATAL ERROR', k, n, 160, 32)


def hexwall(k, n=4):
    """the glitch barrier when he guards: a hex outline with scanlines."""
    W, H = 40, 60
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    pts = [(20, 2), (36, 12), (36, 46), (20, 57), (4, 46), (4, 12)]
    off = (k % 2)
    d.polygon(pts, fill=(60, 200, 255, 70))
    d.line(pts + [pts[0]], fill=(150, 240, 255, 255), width=1)
    for y in range(4 + off, H - 4, 3): d.line([(8, y), (32, y)], fill=(120, 220, 255, 90))
    return im


def spawn(k, n=8):
    """a clone being written in: a vertical scan beam with glitch rows."""
    W, H = 32, 80
    a = rgba(W, H)
    rng = random.Random(k)
    w = int(14 * (1 - abs(k - 3) / 5)) + 1
    a[:, 16 - w // 2:16 + (w + 1) // 2, :] = (120, 240, 255, 110)
    a[:, 15:17, :] = (255, 255, 255, 220)
    for _ in range(10):
        y = rng.randint(0, H - 2); x0 = rng.randint(2, 20); ww = rng.randint(3, 12)
        a[y, x0:x0 + ww, :3] = rng.choice((CYAN, MAGENTA, WHITE)); a[y, x0:x0 + ww, 3] = 255
    return Image.fromarray(a, 'RGBA')


def pillar(k, n=8):
    """a column of fire bursting up out of the ground (origin: bottom centre)."""
    W, H = 40, 112
    flame.use_palette('sun')
    f = flame.Flame(W, H, k, n, seed=505, speed=2.6, flow='up')
    X, Y = f.warp(1.0, 0.8)
    t = np.clip(Y / H, 0, 1)
    half = 5 + 12 * t ** 0.6
    rise = np.clip((Y - (H * (1 - min(1, (k + 1) / 3)))) / 12, 0, 1)
    env = np.clip(1 - np.abs(X - W / 2) / half, 0, 1) * rise * (1 - max(0, k - 5) / 4)
    f.add(env ** 0.7 * 1.35, 1.15)
    return f.finish(dark=0.4)


def sun_pal(fn):
    def f(k, n):
        flame.use_palette('sun')
        return fn(k, n)
    return f


def preview(k, n=4):
    """select-screen preview (his breathing idle, 1x, feet at 48,74)."""
    u = (1 - math.cos(k / n * 2 * math.pi)) / 2
    p = skel.lerp_pose(poses.STAND, poses.STAND2, u)
    im, _ = skel.render(p, (96, 80), (48, 74), 1)
    return im


def marker(k, n=1):
    return Image.new('RGBA', (1, 1), (0, 0, 0, 0))


GOLD_HI, GOLD, GOLD_LO, INK = (242, 223, 77, 255), (219, 161, 2, 255), (163, 81, 0, 255), (0, 0, 0, 255)


def face():
    """HUD / select portrait: the game's gold card, Grey on a glitching grey-blue screen."""
    W, H = 48, 77
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, W - 1, H - 1), 4, fill=INK)
    d.rounded_rectangle((1, 1, W - 2, H - 2), 3, fill=GOLD_HI)
    d.rounded_rectangle((2, 2, W - 3, H - 3), 2, fill=GOLD_LO)
    d.rectangle((3, 3, 44, 62), fill=INK)
    d.rectangle((3, 64, W - 4, 73), fill=GOLD)
    d.line((4, 64, W - 5, 64), fill=GOLD_LO); d.line((4, 66, W - 5, 66), fill=GOLD_HI)
    d.line((3, 74, W - 4, 74), fill=GOLD_LO); d.line((2, 75, W - 3, 75), fill=GOLD_HI)
    win = np.zeros((60, 42, 4), np.uint8)
    for y in range(60):
        k = y / 60
        win[y, :, :3] = (int(30 + 40 * k), int(34 + 44 * k), int(46 + 60 * k))
    win[..., 3] = 255
    rng = random.Random(3)
    for y in range(0, 60, 3): win[y, :, :3] = (win[y, :, :3] * 0.8).astype(np.uint8)
    for _ in range(6):
        y = rng.randint(0, 58); x0 = rng.randint(0, 30)
        win[y, x0:x0 + rng.randint(4, 12), :3] = rng.choice((CYAN, MAGENTA))
    wim = Image.fromarray(win, 'RGBA')
    p = dict(poses.POSE_COOL)
    big, _ = skel.render(p, (42, 60), (18, 58), 1)            # the whole stickman, as he stands
    for dx, col in ((-1, CYAN), (1, MAGENTA)):
        ch = np.array(big); m = ch[..., 3] > 0
        ghost = np.zeros_like(ch); ghost[m, :3] = col; ghost[m, 3] = 120
        wim.alpha_composite(Image.fromarray(np.roll(ghost, dx, axis=1), 'RGBA'))
    wim.alpha_composite(big)
    im.paste(wim, (3, 3))
    return im


SPRITES = {   # name: (generator, frames, ox, oy)
    'shape': (shape, 2, 16, 16), 'glitch': (glitch, 8, 24, 24), 'spark': (spark, 6, 16, 16),
    'arc': (arc, 6, 32, 32), 'ring': (ring, 8, 48, 16),
    'fire': (sun_pal(flame.fist), 8, 34, 30), 'fireburst': (sun_pal(flame.burst), 10, 56, 56),
    'pillar': (pillar, 8, 20, 112),
    'spike': (spike, 10, 16, 48), 'shard': (shard, 4, 6, 6), 'shatter': (shatter, 10, 32, 32),
    'sword': (blade, 4, 4, 6), 'spear': (spear, 4, 30, 6), 'bolt': (bolt, 6, 16, 48),
    'error': (error_txt, 4, 48, 12), 'fatal': (fatal_txt, 4, 80, 16), 'hex': (hexwall, 4, 20, 58),
    'spawn': (spawn, 8, 16, 80), 'preview': (preview, 4, 48, 74),
}
MARKERS = [('stand', 4), ('walk', 6), ('run', 6), ('jump', 2), ('fall', 2), ('crouch', 1), ('defend', 1),
           ('charge', 2), ('hurt', 2), ('hurtup', 1), ('hurtdown', 1), ('fallen', 1), ('attack', 1)]


def build(out):
    os.makedirs(out, exist_ok=True)
    res = {}
    for name, (fn, n, ox, oy) in SPRITES.items():
        fr = [fn(k, n) for k in range(n)]
        _strip(fr).save(os.path.join(out, f'grey_{name}.png'))
        res[name] = fr
    for name, n in MARKERS:
        Image.new('RGBA', (n, 1), (0, 0, 0, 0)).save(os.path.join(out, f'grey_m_{name}.png'))
    face().save(os.path.join(out, 'grey_face.png'))
    flame.use_palette('blue')
    return res


if __name__ == '__main__':
    out = sys.argv[1]
    res = build(out)
    rows = []
    for name, fr in res.items():
        w, h = fr[0].size
        row = Image.new('RGBA', (w * len(fr), h), (60, 70, 100, 255))
        for i, im in enumerate(fr): row.alpha_composite(im, (i * w, 0))
        rows.append(row.resize((row.width * 2, row.height * 2), Image.NEAREST))
    Wd = min(2000, max(r.width for r in rows)); Hd = sum(r.height + 4 for r in rows)
    sheet = Image.new('RGBA', (Wd, Hd), (20, 20, 30, 255)); y = 0
    for r in rows:
        sheet.alpha_composite(r.crop((0, 0, min(Wd, r.width), r.height)), (0, y)); y += r.height + 4
    sheet.save(os.path.join(out, '_fx_preview.png'))
    f = face().resize((48 * 4, 77 * 4), Image.NEAREST); f.save(os.path.join(out, '_face_preview.png'))
    print('fx ok')
