"""SINGULARITY - Scyther's ultimate, as 36 cutscene panels (320x180, drawn full-screen on the GUI).

Act 1 (cut_a, 0-11)  the X cut on the opponent tears open into a black hole: accretion disk ignites,
                     starlight bends around it, the opponent is stretched into it, it swallows the screen
Act 2 (cut_b, 12-23) reality cracks like glass, shatters into tumbling shards and reveals the
                     multiverse - galaxies of every colour blooming behind it
Act 3 (cut_c, 24-35) the galaxies fade into a violet void of floating rocks; Scyther stands on one,
                     scythe at rest; title "SINGULARITY"
"""
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

W, H = 320, 180
CX, CY = 196, 92                 # where the opponent stands / the hole opens

FONT = {
 'S': [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
 'I': ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"],
 'N': ["#...#", "##..#", "#.#.#", "#.#.#", "#..##", "#...#", "#...#"],
 'G': [".####", "#....", "#....", "#.###", "#...#", "#...#", ".###."],
 'U': ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
 'L': ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
 'A': [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
 'R': ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
 'T': ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
 'Y': ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
 'K': ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
 'O': [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
 '.': [".....", ".....", ".....", ".....", ".....", ".....", "..#.."],
 ' ': [".....", ".....", ".....", ".....", ".....", ".....", "....."],
}


def text(a, s, x, y, scale, top=(255, 220, 255), bot=(150, 70, 255), glitch=0, seed=0):
    """pixel-font text with outline, drop shadow and a vertical gradient; optional glitch slicing."""
    gw = 6 * scale
    tw = len(s) * gw - scale
    x -= tw // 2
    m = np.zeros((7 * scale + 4, tw + 4), bool)
    for i, ch in enumerate(s):
        for r, row in enumerate(FONT.get(ch, FONT[' '])):
            for c, v in enumerate(row):
                if v == '#':
                    m[2 + r * scale:2 + (r + 1) * scale, 2 + i * gw + c * scale:2 + i * gw + (c + 1) * scale] = True
    o = ndi.binary_dilation(m, iterations=2)
    rng = np.random.default_rng(seed)
    def stamp(mask, col, dx, dy, grad=False):
        ys, xs = np.nonzero(mask)
        offs = np.zeros(len(ys), int)
        if glitch:
            band = ys // max(1, scale * 2)
            shifts = rng.integers(-glitch, glitch + 1, band.max() + 1)
            offs = shifts[band]
        py, px = ys + y - 2 + dy, xs + x - 2 + dx + offs
        ok = (py >= 0) & (py < H) & (px >= 0) & (px < W)
        if grad:
            k = (ys[ok] / (7 * scale + 2))[:, None]
            a[py[ok], px[ok]] = np.array(top) * (1 - k) + np.array(bot) * k
        else:
            a[py[ok], px[ok]] = col
    stamp(o, (0, 0, 0), 3, 3)
    stamp(o, (40, 8, 70), 0, 0)
    stamp(m, None, 0, 0, grad=True)


def space_bg(seed=1, dim=1.0, galaxies=()):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    a = np.zeros((H, W, 3), np.float32)
    a[...] = (8, 4, 20)
    for col, s, amp in (((110, 30, 150), 9.0, 1.0), ((30, 50, 150), 6.0, 0.8), ((180, 50, 170), 4.0, 0.45)):
        n = ndi.gaussian_filter(rng.uniform(0, 1, (H, W)).astype(np.float32), s)
        n = (n - n.min()) / (np.ptp(n) + 1e-6)
        a += (np.clip((n - 0.45) * 2.4, 0, 1) * amp)[..., None] * np.array(col)
    for (gx, gy, size, col, rot) in galaxies:
        dx, dy = (xx - gx) / size, (yy - gy) / (size * 0.55)
        c_, s_ = math.cos(rot), math.sin(rot)
        dx, dy = dx * c_ - dy * s_, dx * s_ + dy * c_
        r = np.sqrt(dx * dx + dy * dy) + 1e-6
        th = np.arctan2(dy, dx)
        arms = np.cos(2 * th - 4.5 * np.log(r + 0.05)) * 0.5 + 0.5
        g = np.exp(-r * 2.2) * (0.3 + 0.7 * arms ** 3) * 1.4
        core = np.exp(-r * r * 30) * 1.6
        a += g[..., None] * np.array(col) + core[..., None] * np.array((255, 245, 255))
    stars = rng.uniform(0, 1, (H, W)) < 0.012
    a[stars] = np.maximum(a[stars], (230, 226, 255))
    for _ in range(26):
        x, y = rng.integers(2, W - 2), rng.integers(2, H - 2)
        a[y, x] = (255, 255, 255)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a[y + dy, x + dx] = np.maximum(a[y + dy, x + dx], (170, 160, 255))
    return np.clip(a * dim, 0, 255)


def silhouette(a, x, y, scale=1.0, stretch=0.0, alpha=1.0, dir_=(-1, 0)):
    """generic fighter silhouette (the victim), optionally stretched toward the hole."""
    im = Image.new('L', (W * 2, H * 2), 0); d = ImageDraw.Draw(im)
    S = 2 * scale
    def P(px, py):
        # stretch along dir_ proportional to distance from the feet
        k = 1 + stretch * (1 - (py + 40) / 40)
        return (2 * x + (px * S) * (1 + stretch * 0.2) + dir_[0] * stretch * 30 * (1 - (py + 40) / 40) * S,
                2 * y + py * S * (1 + stretch * 0.3))
    d.ellipse([P(-5, -40), P(5, -30)], fill=255)
    d.polygon([P(-7, -30), P(7, -30), P(6, -14), P(-6, -14)], fill=255)
    d.polygon([P(-7, -29), P(-13, -20), P(-11, -18), P(-6, -24)], fill=255)
    d.polygon([P(7, -29), P(13, -20), P(11, -18), P(6, -24)], fill=255)
    d.polygon([P(-6, -14), P(-1, -14), P(-3, 0), P(-8, 0)], fill=255)
    d.polygon([P(1, -14), P(6, -14), P(8, 0), P(3, 0)], fill=255)
    m = np.array(im.resize((W, H), Image.BOX)).astype(np.float32) / 255 * alpha
    rim = np.clip(m - ndi.shift(m, (1, 1), order=0), 0, 1)
    a[:] = a * (1 - m[..., None]) + np.array((10, 6, 18)) * m[..., None]
    a[:] = np.clip(a + rim[..., None] * np.array((170, 110, 255)), 0, 255)


def black_hole(a, cx, cy, r, disk=1.0, k=0):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    dx, dy = xx - cx, yy - cy
    d = np.sqrt(dx * dx + dy * dy)
    # lensing: pull the background toward the ring (approximate by sampling inward)
    if r > 2:
        lens = np.clip(1 - (d - r) / (r * 2.2), 0, 1) ** 2
        scale = 1 + lens * 0.9
        sx = np.clip(cx + dx * scale, 0, W - 1).astype(int); sy = np.clip(cy + dy * scale, 0, H - 1).astype(int)
        a[:] = a[sy, sx]
    # accretion disk (tilted ring)
    if disk > 0:
        ry = 0.28
        de = np.sqrt(dx * dx + (dy / ry) ** 2)
        th = np.arctan2(dy / ry, dx)
        band = np.clip(1 - np.abs(de - r * 2.1) / (r * 0.9), 0, 1)
        swirl = 0.55 + 0.45 * np.sin(5 * th - 8 * np.log(de + 1) + k * 0.9)
        dopp = 1 + 0.5 * np.cos(th)
        heat = band * swirl * dopp * disk
        col = np.array((255, 180, 140)) * 0.5 + np.array((230, 100, 230)) * 0.5
        a[:] = np.clip(a + heat[..., None] * col * 1.4, 0, 255)
    # shadow + photon ring
    sh = np.clip((r + 0.6 - d) / 1.2, 0, 1)
    a[:] = a * (1 - sh[..., None]) + np.array((2, 1, 6)) * sh[..., None]
    ring = np.exp(-((d - r - 0.8) / max(0.7, r * 0.03)) ** 2)
    a[:] = np.clip(a + ring[..., None] * np.array((250, 230, 255)), 0, 255)
    if disk > 0:     # lensed far side arcing over the top
        arc = np.exp(-((d - r * 1.12) / max(0.8, r * 0.05)) ** 2) * (dy < 0) * disk
        a[:] = np.clip(a + arc[..., None] * np.array((255, 160, 230)), 0, 255)


def cracks(seed, n, length, grow=1.0):
    rng = np.random.default_rng(seed)
    im = Image.new('L', (W, H), 0); d = ImageDraw.Draw(im)
    for i in range(n):
        a0 = rng.uniform(0, 2 * math.pi)
        x, y = W / 2 + rng.uniform(-14, 14), H / 2 + rng.uniform(-10, 10)
        pts = [(x, y)]
        L = length * rng.uniform(0.6, 1.2) * grow
        steps = 7
        for s in range(steps):
            a0 += rng.uniform(-0.5, 0.5)
            x += math.cos(a0) * L / steps; y += math.sin(a0) * L / steps
            pts.append((x, y))
            if rng.uniform() < 0.35:
                b = a0 + rng.choice([-1, 1]) * rng.uniform(0.6, 1.2)
                d.line([(x, y), (x + math.cos(b) * L * 0.25, y + math.sin(b) * L * 0.25)], fill=170, width=1)
        d.line(pts, fill=255, width=1)
    return np.array(im).astype(np.float32) / 255


GAL = [(70, 50, 34, (60, 200, 220), 0.4), (250, 40, 28, (240, 190, 80), -0.6), (150, 130, 40, (230, 80, 220), 0.9),
       (285, 140, 24, (90, 120, 255), 0.2), (40, 140, 22, (240, 120, 160), -1.1)]


def shards_frame(t, base_img, behind, seed=4):
    """Voronoi shards of base_img flying outward over `behind` (t: 0..1)."""
    rng = np.random.default_rng(seed)
    n = 34
    pts = np.stack([rng.uniform(0, W, n), rng.uniform(0, H, n)], axis=1)
    yy, xx = np.mgrid[0:H, 0:W]
    d = (xx[..., None] - pts[None, None, :, 0]) ** 2 + (yy[..., None] - pts[None, None, :, 1]) ** 2
    cell = d.argmin(axis=2)
    out = behind.copy()
    for i in range(n):
        m = cell == i
        if not m.any():
            continue
        cy_, cx_ = np.argwhere(m).mean(axis=0)
        vx, vy = (cx_ - W / 2), (cy_ - H / 2)
        L = math.hypot(vx, vy) or 1
        sp = 140 * t ** 1.3 + rng.uniform(0, 30) * t
        ox, oy = vx / L * sp, vy / L * sp
        sc = max(0.05, 1 - t * rng.uniform(0.6, 1.0))
        ys, xs = np.nonzero(m)
        nx = (cx_ + (xs - cx_) * sc + ox).astype(int); ny = (cy_ + (ys - cy_) * sc + oy).astype(int)
        ok = (nx >= 0) & (nx < W) & (ny >= 0) & (ny < H)
        col = base_img[ys[ok], xs[ok]]
        # lit shard edges
        out[ny[ok], nx[ok]] = col
        edge = m & ~ndi.binary_erosion(m)
        ey, ex = np.nonzero(edge)
        enx = (cx_ + (ex - cx_) * sc + ox).astype(int); eny = (cy_ + (ey - cy_) * sc + oy).astype(int)
        ok2 = (enx >= 0) & (enx < W) & (eny >= 0) & (eny < H)
        out[eny[ok2], enx[ok2]] = (220, 190, 255)
    return out


def frame(f, rooster=None):
    if f < 12:                                                 # ---- Act 1: the swallowing
        a = space_bg(3, dim=0.6)
        a[150:, :] = a[150:, :] * 0.4 + np.array((30, 20, 40)) * 0.6
        k = f
        if f == 0:
            silhouette(a, CX, 150)
            im = Image.fromarray(a.astype(np.uint8)); d = ImageDraw.Draw(im)
            d.line([(CX - 16, 98), (CX + 16, 130)], fill=(250, 220, 255), width=2)
            d.line([(CX + 16, 98), (CX - 16, 130)], fill=(250, 220, 255), width=2)
            return np.array(im).astype(np.float32)
        r = [0, 5, 9, 13, 18, 24, 31, 40, 60, 95, 150, 240][f]
        stretch = min(1.6, max(0.0, (f - 2) * 0.32))
        if f < 8:
            silhouette(a, CX + 8 * stretch, 150 - 22 * stretch, stretch=stretch, alpha=max(0.0, 1 - (f - 4) * 0.22) if f > 4 else 1.0)
        black_hole(a, CX, 116 - min(24, f * 3), r, disk=1.0 if f < 10 else 0.6, k=k)
        if f == 11:
            a *= 0.15
        return a
    if f < 24:                                                 # ---- Act 2: the multiverse shatters
        g = f - 12
        black = np.zeros((H, W, 3), np.float32); black[...] = (2, 1, 6)
        if g == 0:
            c = cracks(21, 1, 40)
            return np.clip(black + c[..., None] * np.array((255, 240, 255)), 0, 255)
        if g < 4:
            c = cracks(21, 3 + g * 3, 60 + g * 40, 1.0)
            glow = ndi.gaussian_filter(c, 2.0) * 3
            return np.clip(black + c[..., None] * np.array((255, 240, 255)) + glow[..., None] * np.array((160, 80, 255)), 0, 255)
        multi = space_bg(9, dim=1.0, galaxies=GAL)
        c = cracks(21, 12, 220, 1.0)
        cracked = np.clip(black + c[..., None] * np.array((255, 240, 255)), 0, 255)
        if g == 4:                                                      # the flash: light blazes through
            glow = ndi.gaussian_filter(c, 3.0) * 6
            fl = np.zeros((H, W, 3), np.float32); fl[...] = (150, 90, 230)
            return np.clip(fl + glow[..., None] * np.array((255, 220, 255)) + c[..., None] * 255, 0, 255)
        t = (g - 4) / 7
        bloom = 0.6 + 0.4 * t
        multi = space_bg(9, dim=bloom, galaxies=GAL)
        return shards_frame(min(1.0, t * 1.3), cracked, multi)
    g = f - 24                                                 # ---- Act 3: the floating-rock void
    fade = min(1.0, g / 4)
    multi = space_bg(9, dim=1.0 - 0.6 * fade, galaxies=GAL)
    void = space_bg(13, dim=0.85)
    a = multi * (1 - fade) + void * fade
    if rooster is not None:
        rocks, hero = rooster
        for i, (rx, ry, rk, sc) in enumerate(((40, 120, 0, 1.0), (120, 60, 1, 0.6), (270, 70, 2, 0.8), (230, 150, 3, 1.3), (300, 130, 4, 0.7))):
            bob = math.sin(g * 0.5 + i) * 2
            im = rocks[rk]
            im = im.resize((int(im.width * sc), int(im.height * sc)), Image.NEAREST)
            put(a, im, int(rx - im.width / 2), int(ry - im.height / 2 + bob), fade)
        if g >= 4:
            al = min(1.0, (g - 4) / 3)
            put(a, hero, int(118 - hero.width / 2), int(176 - hero.height + 8), al)
    if g >= 8:
        im = a.astype(np.uint8)
        text(im, 'SINGULARITY', 160, 18, 3, glitch=max(0, 6 - (g - 8) * 2), seed=g)
        a = im.astype(np.float32)
    return a


def put(a, im, x, y, alpha=1.0):
    arr = np.array(im).astype(np.float32); h, w = arr.shape[:2]
    x0, y0 = max(0, x), max(0, y); x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    sub = arr[y0 - y:y1 - y, x0 - x:x1 - x]; al = sub[..., 3:4] / 255 * alpha
    a[y0:y1, x0:x1] = a[y0:y1, x0:x1] * (1 - al) + sub[..., :3] * al


def render_all(out, rocks, hero):
    frames = [Image.fromarray(np.clip(frame(f, (rocks, hero)), 0, 255).astype(np.uint8)).convert('RGBA') for f in range(36)]
    for i, nm in enumerate(('cut_a', 'cut_b', 'cut_c')):
        s = Image.new('RGBA', (W * 12, H), (0, 0, 0, 255))
        for k in range(12):
            s.paste(frames[i * 12 + k], (k * W, 0))
        s.save(os.path.join(out, f'scyther_{nm}.png'))
    return frames


if __name__ == '__main__':
    import void, anims
    out = sys.argv[1] if len(sys.argv) > 1 else '/tmp'
    rocks = void.rock_images()
    hero = anims.hero_1x(anims.A['sp'][5])
    hero = hero.resize((int(hero.width * 1.6), int(hero.height * 1.6)), Image.NEAREST)
    fr = render_all(out, rocks, hero)
    sheet = Image.new('RGB', (W * 6, H * 6), (0, 0, 0))
    for i in range(36):
        sheet.paste(fr[i].convert('RGB'), ((i % 6) * W, (i // 6) * H))
    sheet.save(os.path.join(out, 'cutscene_preview.png'))
    print('cutscene ok')
