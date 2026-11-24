"""Bone Breaker cutscene: 36 pixel-art panels (320x180), three strips of 12 frames.

Timeline (frame numbers; the game shows them across 156 ticks, see SP_CUT in src/jeff.c):
  0-8   Jeff close-up, eyes ignite red, "BONE BREAKER" slams in
  9     X-ray: fist breaks the arm          ("CRACK!")   <- crack1 sound
  14    ribs shatter                         ("SNAP!")    <- crack2
  19    spine snaps                          ("CRUNCH!")  <- crack3
  24    skull cracks                         ("CRACK!!")  <- crack1+3
  29    the whole skeleton bursts            ("K.O.")     <- ko boom
  30-35 fragments fly, fade to white
"""
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rig

W, H = 320, 180
RNG = np.random.default_rng(55)

# ---------------- pixel font ---------------------------------------------------------------
FONT = {
 'B': ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
 'O': [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
 'N': ["#...#", "##..#", "#.#.#", "#.#.#", "#..##", "#...#", "#...#"],
 'E': ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
 'R': ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
 'A': [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
 'K': ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
 'C': [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
 'S': [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
 'P': ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
 'U': ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
 'H': ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
 '!': ["..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."],
 '.': [".....", ".....", ".....", ".....", ".....", ".....", "..#.."],
 ' ': [".....", ".....", ".....", ".....", ".....", ".....", "....."],
}


def text(img, s, x, y, scale, color, outline=(0, 0, 0), shadow=True, center=True):
    gw = 6 * scale
    tw = len(s) * gw - scale
    if center:
        x -= tw // 2
    m = np.zeros((7 * scale + 4, tw + 4), bool)
    for i, ch in enumerate(s):
        g = FONT.get(ch, FONT[' '])
        for r, row in enumerate(g):
            for c, v in enumerate(row):
                if v == '#':
                    m[2 + r * scale:2 + (r + 1) * scale, 2 + i * gw + c * scale:2 + i * gw + (c + 1) * scale] = True
    from scipy import ndimage as ndi
    o = ndi.binary_dilation(m, iterations=2)
    a = np.array(img)
    def stamp(mask, col, dx, dy):
        ys, xs = np.nonzero(mask)
        ys = ys + y - 2 + dy; xs = xs + x - 2 + dx
        ok = (ys >= 0) & (ys < H) & (xs >= 0) & (xs < W)
        a[ys[ok], xs[ok], :3] = col; a[ys[ok], xs[ok], 3] = 255
    if shadow:
        stamp(o, (0, 0, 0), 3, 3)
    stamp(o, outline, 0, 0)
    # vertical gradient on the letters
    ys, xs = np.nonzero(m)
    for yy, xx in zip(ys, xs):
        py, px = yy + y - 2, xx + x - 2
        if 0 <= py < H and 0 <= px < W:
            k = yy / (7 * scale + 2)
            col = tuple(int(c * (1.15 - 0.35 * k)) if c * (1.15 - 0.35 * k) < 255 else 255 for c in color)
            a[py, px, :3] = col; a[py, px, 3] = 255
    return Image.fromarray(a)


# ---------------- helpers ------------------------------------------------------------------
def bg_red(f):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt((xx - 200) ** 2 + (yy - 90) ** 2) / 220
    r = np.clip(150 - d * 150 + 20 * math.sin(f), 10, 255)
    img = np.zeros((H, W, 4), np.uint8)
    img[..., 0] = r; img[..., 1] = r * 0.12; img[..., 2] = r * 0.18; img[..., 3] = 255
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    for k in range(46):                               # converging speed lines
        a = k * 2 * math.pi / 46 + f * 0.05
        r1 = 70 + (k * 37 % 50)
        d.line([(200 + math.cos(a) * r1, 90 + math.sin(a) * r1), (200 + math.cos(a) * 400, 90 + math.sin(a) * 400)],
               fill=(255, 190, 190, 255) if k % 3 else (90, 0, 10, 255), width=1)
    return im


def bg_xray(f, flash=0.0):
    img = np.zeros((H, W, 4), np.uint8)
    yy, xx = np.mgrid[0:H, 0:W]
    base = 14 + 10 * np.exp(-((xx - 200) ** 2 + (yy - 95) ** 2) / 9000.0)
    img[..., 0] = base * 0.5; img[..., 1] = base * 1.3; img[..., 2] = base * 3.2; img[..., 3] = 255
    img[yy % 2 == 0] = (img[yy % 2 == 0] * 0.8).astype(np.uint8)          # scanlines
    grid = ((xx % 20) == 0) | ((yy % 20) == 0)
    img[grid, 1] = np.minimum(255, img[grid, 1] + 18); img[grid, 2] = np.minimum(255, img[grid, 2] + 30)
    if flash:
        img[..., :3] = np.clip(img[..., :3] + flash * 255, 0, 255)
    return Image.fromarray(img)


def jeff_face(pose_eyes='angry', glow=0.0):
    """big close-up of Jeff's head: pixel art at 0.1 scale, upscaled 3x (192x180)"""
    w, h, sc = 64, 60, 0.1
    # drawing point (620, 300) (middle of the head, ear tips) -> canvas (32, 2)
    c = rig.Canvas(w, h, int(round(32 - (620 - rig.PIVOT['root'][0]) * sc)),
                   int(round(2 + (rig.PIVOT['root'][1] - 300) * sc)), sc)
    c.begin()
    M = np.eye(3)
    c.put(c.mask_from_crop('body', M))
    c.put(c.mask_from_crop('bandana', M), rig.BLACK, outline=False)
    c.put(c.mask_from_crop('head', M))
    eye_c = []
    for e in ('eyeL', 'eyeR'):
        m = c.mask_from_crop(e, M)
        c.put(m, rig.WHITE)
        ys, xs = np.nonzero(m)
        eye_c.append((xs.mean(), ys.mean()))
        if pose_eyes == 'angry':
            im = Image.fromarray(c.img); d = ImageDraw.Draw(im)
            d.line([(xs.min() - 1, ys.min() - 1), (xs.max() + 1, ys.min() + 2)], fill=rig.BLACK, width=1)
            d.line([(xs.min() - 1, ys.min()), (xs.max() + 1, ys.min() + 3)], fill=rig.BLACK, width=1)
            c.img = np.array(im)
    c.line(rig.MOUTH, M)
    a = c.img.copy()
    if glow > 0:                                  # eyes burn red
        yy, xx = np.mgrid[0:h, 0:w]
        for (cx, cy) in eye_c:
            d = np.sqrt((xx - cx) ** 2 + (yy - cy - 0.5) ** 2)
            core = (d < 1.2 + 1.3 * glow) & (a[..., 3] > 0)
            ring = (d < 2.4 + 1.6 * glow) & ~core & (a[..., 0] > 200) & (a[..., 1] > 200)
            a[ring] = (255, 150, 150, 255)
            a[core] = (255, 30, 40, 255)
    img = Image.fromarray(a, 'RGBA')
    return img.resize((w * 3, h * 3), Image.NEAREST)


# ---------------- skeleton -----------------------------------------------------------------
CX = 212
BONES = {   # name: (x1, y1, x2, y2, radius)
    'humL': (CX - 22, 64, CX - 32, 92, 3.2), 'radL': (CX - 32, 92, CX - 28, 116, 2.6),
    'humR': (CX + 22, 64, CX + 32, 92, 3.2), 'radR': (CX + 32, 92, CX + 28, 116, 2.6),
    'femL': (CX - 8, 122, CX - 12, 150, 3.6), 'tibL': (CX - 12, 150, CX - 13, 176, 3.0),
    'femR': (CX + 8, 122, CX + 12, 150, 3.6), 'tibR': (CX + 12, 150, CX + 13, 176, 3.0),
    'clavL': (CX, 62, CX - 22, 64, 2.2), 'clavR': (CX, 62, CX + 22, 64, 2.2),
}
VERTS = [(CX, 62 + i * 5.6) for i in range(10)]
RIBS = [(68 + i * 6, 20 - i * 1.2) for i in range(5)]


def draw_capsule(d, a, b, r, fill, outline):
    for (col, rr) in ((outline, r + 1.3), (fill, r)):
        n = 10
        for i in range(n + 1):
            t = i / n
            x = a[0] + (b[0] - a[0]) * t; y = a[1] + (b[1] - a[1]) * t
            d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=col)


def crack_line(d, a, b, col=(255, 40, 40, 255), w=1, jag=3, seed=0):
    rng = np.random.default_rng(seed)
    pts = [a]
    n = 6
    for i in range(1, n):
        t = i / n
        x = a[0] + (b[0] - a[0]) * t + rng.uniform(-jag, jag)
        y = a[1] + (b[1] - a[1]) * t + rng.uniform(-jag, jag)
        pts.append((x, y))
    pts.append(b)
    d.line(pts, fill=col, width=w)


def skeleton(img, broken, f, burst=None):
    """broken: set of 'arm','ribs','spine','skull'; burst: frames since total shatter"""
    d = ImageDraw.Draw(img)
    BONE, OUT = (235, 245, 255, 255), (90, 170, 255, 255)
    # body silhouette glow
    sil = Image.new('L', (W, H), 0); sd = ImageDraw.Draw(sil)
    sd.ellipse((CX - 17, 26, CX + 17, 62), fill=70)
    sd.rounded_rectangle((CX - 26, 60, CX + 26, 126), 12, fill=55)
    for k in ('humL', 'radL', 'humR', 'radR', 'femL', 'tibL', 'femR', 'tibR'):
        x1, y1, x2, y2, r = BONES[k]
        sd.line([(x1, y1), (x2, y2)], fill=55, width=int(r * 4))
    if burst is None:
        g = np.array(sil, np.float32)[..., None] / 255
        a = np.array(img).astype(np.float32)
        a[..., :3] = a[..., :3] + g * np.array([40, 140, 255])
        img.paste(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)))
        d = ImageDraw.Draw(img)

    def off(name, base):
        if burst is None:
            return base, 0
        rng = np.random.default_rng(abs(hash(name)) % 2 ** 32)
        vx, vy = rng.uniform(-6, 6), rng.uniform(-6, 2)
        t = burst
        return (base[0] + vx * t, base[1] + vy * t + 0.35 * t * t), rng.uniform(-0.4, 0.4) * t

    def bone(name, a, b, r):
        (ax, ay), rot = off(name, a)
        bx, by = ax + (b[0] - a[0]), ay + (b[1] - a[1])
        if rot:
            mx, my = (ax + bx) / 2, (ay + by) / 2
            c, s = math.cos(rot), math.sin(rot)
            ax, ay = mx + (ax - mx) * c - (ay - my) * s, my + (ax - mx) * s + (ay - my) * c
            bx, by = mx + (bx - mx) * c - (by - my) * s, my + (bx - mx) * s + (by - my) * c
        draw_capsule(d, (ax, ay), (bx, by), r, BONE, OUT)
        return (ax, ay), (bx, by)

    for k, (x1, y1, x2, y2, r) in BONES.items():
        if k == 'humL' and 'arm' in broken and burst is None:       # snapped upper arm
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            drift = min(4, (f - 9) * 0.8)
            bone(k + 'a', (x1, y1), (mx - 1, my - 2), r)
            bone(k + 'b', (mx + 2 + drift * 0.3, my + 3 + drift), (x2 + drift * 0.3, y2 + drift), r)
            crack_line(d, (mx - 6, my - 4), (mx + 6, my + 4), seed=1)
            continue
        bone(k, (x1, y1), (x2, y2), r)
    for i, (vx, vy) in enumerate(VERTS):                             # spine
        dy = 0
        if 'spine' in broken and burst is None and i >= 5:
            dy = min(5, (f - 19) * 1.2) + 2
        (px, py), _ = off('v%d' % i, (vx, vy + dy))
        d.rounded_rectangle((px - 4, py - 2, px + 4, py + 2), 1, fill=BONE, outline=OUT)
    if 'spine' in broken and burst is None:
        crack_line(d, (CX - 9, 89), (CX + 9, 91), seed=3, w=2)
    for i, (ry, span) in enumerate(RIBS):                            # ribs
        for side in (-1, 1):
            pts = [(CX + side * (3 + span * t), ry + 10 * t * t - 4 * t) for t in np.linspace(0, 1, 8)]
            if burst is not None:
                (dx, dy), _ = off('rib%d%d' % (i, side), (0, 0))
                pts = [(x + dx, y + dy) for x, y in pts]
            if 'ribs' in broken and burst is None and side == -1 and i in (1, 2, 3):
                d.line(pts[:4], fill=OUT, width=4); d.line(pts[:4], fill=BONE, width=2)
                q = [(x - 3, y + 3) for x, y in pts[5:]]
                d.line(q, fill=OUT, width=4); d.line(q, fill=BONE, width=2)
                crack_line(d, pts[4], (pts[4][0] - 3, pts[4][1] + 5), seed=10 + i)
                continue
            d.line(pts, fill=OUT, width=4); d.line(pts, fill=BONE, width=2)
    # pelvis
    (px, py), _ = off('pelvis', (CX, 122))
    d.polygon([(px - 14, py - 6), (px + 14, py - 6), (px + 9, py + 6), (px, py + 2), (px - 9, py + 6)], fill=BONE, outline=OUT)
    # skull
    (sx, sy), rot = off('skull', (CX, 44))
    d.ellipse((sx - 15, sy - 17, sx + 15, sy + 13), fill=BONE, outline=OUT)
    d.rounded_rectangle((sx - 10, sy + 6, sx + 8, sy + 18), 3, fill=BONE, outline=OUT)       # jaw
    d.ellipse((sx - 12, sy - 6, sx - 3, sy + 4), fill=(20, 30, 70, 255))                     # eye sockets (facing Jeff)
    d.ellipse((sx + 1, sy - 6, sx + 9, sy + 4), fill=(20, 30, 70, 255))
    d.polygon([(sx - 3, sy + 5), (sx, sy + 1), (sx + 1, sy + 6)], fill=(20, 30, 70, 255))
    for k in range(5):
        d.line([(sx - 8 + k * 4, sy + 12), (sx - 8 + k * 4, sy + 17)], fill=OUT)
    if 'skull' in broken and burst is None:
        crack_line(d, (sx - 4, sy - 17), (sx + 2, sy + 2), seed=21, w=2, jag=4)
        crack_line(d, (sx + 1, sy - 8), (sx + 12, sy - 2), seed=22, w=1, jag=3)
        crack_line(d, (sx - 2, sy - 10), (sx - 13, sy - 4), seed=23, w=1, jag=3)
    return img


def fist(img, x, y, power=0.0):
    """Jeff's punching paw coming in from the left edge (white, outlined, violet magic glow)"""
    d = ImageDraw.Draw(img)
    if power > 0:
        for r, col in ((24, (90, 40, 160, 255)), (18, (150, 90, 230, 255))):
            d.ellipse((x - r, y - r, x + r, y + r), outline=col, width=2)
    d.rounded_rectangle((-10, y - 9, x - 6, y + 9), 8, fill=(16, 16, 20, 255))
    d.rounded_rectangle((-10, y - 7, x - 6, y + 7), 7, fill=(244, 244, 246, 255))
    d.ellipse((x - 16, y - 15, x + 14, y + 15), fill=(16, 16, 20, 255))
    d.ellipse((x - 14, y - 13, x + 12, y + 13), fill=(244, 244, 246, 255))
    for k in range(3):                                           # knuckle lines
        d.line([(x + 4, y - 8 + k * 6), (x + 10, y - 8 + k * 6)], fill=(170, 170, 190, 255))
    for k in range(6):                                           # speed lines
        yy = y - 18 + k * 7
        d.line([(x - 70 - k * 9, yy), (x - 26, yy)], fill=(255, 255, 255, 255) if k % 2 else (180, 160, 255, 255))
    return img


def impact(img, x, y, size, col=(255, 255, 255, 255)):
    d = ImageDraw.Draw(img)
    for k in range(12):
        a = k * math.pi / 6
        L = size * (1.0 if k % 2 == 0 else 0.55)
        d.line([(x, y), (x + math.cos(a) * L, y + math.sin(a) * L)], fill=col, width=2 if k % 2 == 0 else 1)
    d.ellipse((x - size * 0.25, y - size * 0.25, x + size * 0.25, y + size * 0.25), fill=col)
    return img


def shards(img, x, y, t, n=10, seed=0, col=(235, 245, 255, 255)):
    rng = np.random.default_rng(seed)
    d = ImageDraw.Draw(img)
    for _ in range(n):
        a = rng.uniform(-math.pi * 0.8, math.pi * 0.8); sp = rng.uniform(2, 6)
        px = x + math.cos(a) * sp * t; py = y + math.sin(a) * sp * t + 0.4 * t * t
        s = rng.uniform(1.5, 3)
        d.polygon([(px, py - s), (px + s, py + s), (px - s, py + s * 0.6)], fill=col)
    return img


# ---------------- frames -------------------------------------------------------------------
HITS = {9: ('arm', (CX - 27, 78), 'CRACK!'), 14: ('ribs', (CX - 14, 80), 'SNAP!'),
        19: ('spine', (CX - 8, 92), 'CRUNCH!'), 24: ('skull', (CX - 10, 40), 'CRACK!!')}


def frame(f):
    if f <= 8:                                                     # --- intro close-up
        im = bg_red(f)
        slide = max(0, 3 - f) * 64
        glow = 0 if f < 3 else min(1.0, (f - 2) / 3)
        face = jeff_face('angry', glow)
        im.alpha_composite(face, (160 + slide, 0))
        if f >= 3:
            sc = 7 if f == 3 else 6
            im = text(im, 'BONE', 84, 36 if f > 3 else 30, sc, (255, 255, 255), (60, 0, 0))
        if f >= 5:
            sc = 4
            im = text(im, 'BREAKER', 84, 102 if f > 5 else 98, sc, (255, 70, 60), (40, 0, 0))
        if f == 8:
            a = np.array(im); a[..., :3] = 255 - a[..., :3] // 2; im = Image.fromarray(a)
        return im
    # --- X-ray beats
    broken = set()
    for hf, (part, _, _) in HITS.items():
        if f >= hf:
            broken.add(part)
    if f >= 29:
        im = bg_xray(f, flash=0.6 if f == 29 else max(0, (f - 31) * 0.18))
        skeleton(im, broken, f, burst=(f - 29) * 1.6 + 0.5)
        if f >= 29:
            im = text(im, 'K.O.', 160, 60 - min(10, (f - 29) * 4), 9 if f == 29 else 8, (255, 230, 60), (90, 10, 0))
        if f >= 33:
            a = np.array(im).astype(np.float32)
            k = (f - 32) / 4
            a[..., :3] = a[..., :3] * (1 - k) + 255 * k
            im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
        return im
    im = bg_xray(f)
    skeleton(im, broken, f)
    # fist choreography: strike on hit frames, retract between
    last = max([hf for hf in HITS if hf <= f], default=None)
    nxt = min([hf for hf in HITS if hf > f], default=None)
    if last is not None and f == last:
        part, (hx, hy), word = HITS[last]
        fist(im, hx - 8, hy, power=1)
        impact(im, hx, hy, 22)
        impact(im, hx, hy, 12, (255, 60, 50, 255))
        im = text(im, word, 92, 18, 4, (255, 90, 60), (50, 0, 0))
    elif last is not None and f - last <= 2:
        part, (hx, hy), word = HITS[last]
        fist(im, hx - 20 - (f - last) * 14, hy)
        shards(im, hx, hy, (f - last) * 2.5, seed=last)
        im = text(im, word, 92, 18 - (f - last), 4, (255, 120, 90), (50, 0, 0))
    elif nxt is not None:
        part, (hx, hy), _ = HITS[nxt]
        wind = 1 - (nxt - f) / 4
        fist(im, 20 + 40 * max(0, wind), hy, power=0.5)
    return im


def render_all(outdir):
    os.makedirs(outdir, exist_ok=True)
    frames = [frame(f).convert('RGBA') for f in range(36)]
    for k, name in enumerate(('cut_a', 'cut_b', 'cut_c')):
        s = Image.new('RGBA', (W * 12, H))
        for i in range(12):
            s.paste(frames[k * 12 + i], (i * W, 0))
        s.save(os.path.join(outdir, f'jeff_{name}.png'))
    return frames


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'out'
    fr = render_all(out)
    sheet = Image.new('RGBA', (W * 6, H * 6))
    for i, f in enumerate(fr):
        sheet.paste(f, ((i % 6) * W, (i // 6) * H))
    sheet.save(os.path.join(out, 'cutscene_sheet.png'))
    print('ok')
