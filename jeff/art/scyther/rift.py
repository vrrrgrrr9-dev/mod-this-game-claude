"""Reality tears - every Scyther cut slices a hole in reality.

A tear is a jagged lens (vesica) cut into space.  It is drawn as two sprites:
  * <name>_void  (normal blend)  the hole itself: deep space seen through the cut - near-black
                  violet void, nebula clouds, stars, (big tears: a distant galaxy) - it occludes the
                  stage behind it, so it really reads as a hole;
  * <name>_edge  (additive)      the torn rim glowing violet-white, cracks running out into reality,
                  shards flaking off and drifting away.
16 frames: 0-3 the cut splits open, 4-11 it shimmers, 12-15 it seals with a flash.
The game rotates them to the slash angle (origin = centre).
"""
import math
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

NF = 16


def _smooth_noise(n, seed, scale=6.0):
    rng = np.random.default_rng(seed)
    v = rng.uniform(-1, 1, int(n / scale) + 4)
    xs = np.linspace(0, len(v) - 3, n)
    i = xs.astype(int); t = xs - i
    t = t * t * (3 - 2 * t)
    return v[i] * (1 - t) + v[i + 1] * t


def _open(k):
    if k < 4:
        return [0.12, 0.45, 0.8, 1.0][k]
    if k < 12:
        return 1.0 + 0.04 * math.sin(k * 1.7)
    return [0.72, 0.42, 0.16, 0.0][k - 12]


def _space(w, h, seed, galaxy=False):
    """deep-space texture (RGB float 0..255)."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.zeros((h, w, 3), np.float32)
    img[...] = (8, 4, 20)
    # nebula clouds: blurred noise in magenta and blue
    for col, s, amp in (((120, 30, 160), 5.0, 1.0), ((40, 60, 170), 3.5, 0.8), ((200, 60, 190), 2.2, 0.5)):
        n = ndi.gaussian_filter(rng.uniform(0, 1, (h, w)).astype(np.float32), s)
        n = (n - n.min()) / (np.ptp(n) + 1e-6)
        n = np.clip((n - 0.45) * 2.2, 0, 1) * amp
        img += n[..., None] * np.array(col, np.float32)
    if galaxy:
        cx, cy = w * 0.55, h * 0.5
        dx, dy = (xx - cx) / (w * 0.22), (yy - cy) / (h * 0.30)
        r = np.sqrt(dx * dx + dy * dy) + 1e-6
        th = np.arctan2(dy, dx)
        arms = np.cos(2 * th - 4.0 * np.log(r + 0.08)) * 0.5 + 0.5
        g = np.exp(-r * 1.6) * (0.35 + 0.65 * arms ** 3)
        core = np.exp(-r * r * 9)
        img += g[..., None] * np.array((150, 110, 255)) + core[..., None] * np.array((255, 235, 255))
    # stars
    m = rng.uniform(0, 1, (h, w)) < 0.035
    tint = rng.uniform(0, 1, (h, w))
    img[m & (tint < 0.6)] = (240, 236, 255)
    img[m & (tint >= 0.6)] = (150, 230, 255)
    for _ in range(max(2, w * h // 900)):
        x, y = rng.integers(2, w - 2), rng.integers(2, h - 2)
        img[y, x] = (255, 255, 255)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            img[y + dy, x + dx] = (190, 170, 255)
    return np.clip(img, 0, 255)


def make(W, H, L, hw, seed, galaxy=False, cracks=7):
    """-> (void_frames, edge_frames) lists of RGBA PIL images, origin at the centre."""
    cx, cy = W / 2, H / 2
    xs = np.arange(W) - cx + 0.5
    voids, edges = [], []
    space_cache = [_space(W, H, seed + 100 + i, galaxy) for i in range(3)]
    rng = np.random.default_rng(seed)
    crack_seeds = [(rng.uniform(-0.42, 0.42), rng.choice([-1, 1]), rng.uniform(0.5, 1.0), rng.integers(0, 1 << 30))
                   for _ in range(cracks)]
    shard_seeds = [(rng.uniform(-0.45, 0.45), rng.choice([-1, 1]), rng.uniform(0.6, 1.4), rng.uniform(-0.6, 0.6))
                   for _ in range(10)]
    base_noise = _smooth_noise(W, seed, 5.0)
    for k in range(NF):
        f = _open(k)
        jit = _smooth_noise(W, seed * 31 + k, 3.0) * 0.6
        u = np.clip(2 * xs / L, -1.2, 1.2)
        prof = np.clip(1 - u * u, 0, 1) ** 0.65
        w_top = hw * f * prof * (1 + 0.28 * base_noise + 0.12 * jit)
        w_bot = hw * f * prof * (1 - 0.22 * base_noise + 0.12 * jit[::-1])
        yy = np.arange(H)[:, None] - cy + 0.5
        inside = (yy > -w_top[None, :]) & (yy < w_bot[None, :]) & (np.abs(u) < 1)[None, :]
        # ---- void (normal blend) ----
        v = np.zeros((H, W, 4), np.uint8)
        sp = space_cache[(k // 3) % 3]
        if inside.any():
            # darker toward the centre line, more violet near the torn edges
            depth = np.clip(np.minimum(yy + w_top[None, :], w_bot[None, :] - yy) / (hw * 0.6 + 1e-6), 0, 1)
            colr = sp * (0.55 + 0.45 * depth[..., None]) + (1 - depth[..., None]) * np.array((70, 20, 110))
            v[inside, :3] = np.clip(colr[inside], 0, 255).astype(np.uint8)
            v[inside, 3] = 255
        voids.append(Image.fromarray(v, 'RGBA'))
        # ---- edge glow, cracks, shards (additive) ----
        e = np.zeros((H, W), np.float32)
        ecol = np.zeros((H, W, 3), np.float32)
        if f > 0.01:
            rim = inside ^ ndi.binary_erosion(inside, iterations=1)
            outer = ndi.binary_dilation(inside, iterations=2) & ~inside
            glow = ndi.gaussian_filter((rim | outer).astype(np.float32), 1.4)
            e += glow * 1.4
            ecol += (glow * 1.4)[..., None] * np.array((170, 80, 255))
            ecol[rim] = (255, 225, 255)
            e[rim] = 1.0
            ecol[outer & ~rim] = np.maximum(ecol[outer & ~rim], (200, 120, 255))
        else:
            pass
        if k < 1 or k >= 14:        # the cut line itself / the final seal flash
            line_w = 1 if k < 14 else 1
            mid = (np.abs(np.arange(H)[:, None] - cy + 0.5) <= line_w) & (np.abs(u) < (0.95 if k < 1 else 0.7 * (16 - k) / 2))[None, :]
            ecol[mid] = (255, 240, 255)
            fl = ndi.gaussian_filter(mid.astype(np.float32), 2.0) * 2.5
            ecol += fl[..., None] * np.array((190, 120, 255))
        # cracks running out into reality (grow while opening, fade while closing)
        grow = min(1.0, (k + 1) / 5.0) if k < 12 else max(0.0, (16 - k) / 4.0)
        im = Image.new('L', (W, H), 0)
        from PIL import ImageDraw
        d = ImageDraw.Draw(im)
        for (px, side, Lc, s) in crack_seeds:
            r2 = np.random.default_rng(s)
            x0 = cx + px * L
            prof0 = max(0.0, 1 - (2 * px) ** 2) ** 0.65
            y0 = cy + side * hw * f * prof0
            ang = math.pi / 2 * side + r2.uniform(-0.7, 0.7)
            length = Lc * (H * 0.45) * grow
            pts = [(x0, y0)]
            x, y = x0, y0
            for seg in range(3):
                step = length / 3
                ang += r2.uniform(-0.6, 0.6)
                x += math.cos(ang) * step; y += math.sin(ang) * step
                pts.append((x, y))
            if length > 0.5:
                d.line(pts, fill=255, width=1)
                if Lc > 0.8:                         # a branch
                    bx, by = pts[1]
                    ba = ang + r2.choice([-1, 1]) * 0.9
                    d.line([(bx, by), (bx + math.cos(ba) * length * 0.4, by + math.sin(ba) * length * 0.4)], fill=170, width=1)
        cr = np.array(im, np.float32) / 255.0
        ecol += cr[..., None] * np.array((170, 100, 255)) * (0.6 + 0.4 * f)
        # shards flaking off the torn edges and drifting outward
        if 3 <= k < 15:
            for (px, side, sp_, drift) in shard_seeds:
                t = (k - 3) / 11.0
                x = cx + px * L + drift * t * 10
                prof0 = max(0.0, 1 - (2 * px) ** 2) ** 0.65
                y = cy + side * (hw * prof0 + 2 + t * 14 * sp_)
                xi, yi = int(round(x)), int(round(y))
                if 1 <= xi < W - 1 and 1 <= yi < H - 1:
                    a = 1 - t
                    ecol[yi, xi] = np.maximum(ecol[yi, xi], np.array((240, 210, 255)) * a)
                    ecol[yi, xi + (1 if side > 0 else -1)] = np.maximum(ecol[yi, xi + (1 if side > 0 else -1)], np.array((160, 90, 255)) * a)
        ecol = np.clip(ecol, 0, 255)
        alpha = np.clip(ecol.max(axis=2), 0, 255)
        out = np.zeros((H, W, 4), np.uint8)
        out[..., :3] = ecol.astype(np.uint8)
        out[..., 3] = alpha.astype(np.uint8)
        edges.append(Image.fromarray(out, 'RGBA'))
    return voids, edges


def strip(frames):
    w, h = frames[0].size
    s = Image.new('RGBA', (w * len(frames), h), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        s.paste(f, (i * w, 0))
    return s


def all_rifts():
    """name -> (void strip, edge strip, origin)"""
    out = {}
    v, e = make(192, 96, 160, 18.0, seed=7, cracks=9)        # 2x density (drawn at half scale)
    out['rift'] = (v, e, (96, 48))
    v, e = make(176, 96, 156, 26.0, seed=11, galaxy=True, cracks=12)
    out['riftbig'] = (v, e, (88, 48))
    return out


if __name__ == '__main__':
    import sys, os
    outdir = sys.argv[1] if len(sys.argv) > 1 else '/tmp'
    r = all_rifts()
    # preview: composite void (normal) + edge (additive) on a stage-like background
    for name, (v, e, o) in r.items():
        w, h = v[0].size
        Z = 4 if name == 'rift' else 2
        sheet = Image.new('RGB', (w * Z * 4, h * Z * 4), (0, 0, 0))
        for k in range(16):
            bg = np.zeros((h, w, 3), np.float32)
            bg[...] = (70, 56, 96)                     # a mid-tone stage colour so the hole is visible
            bg[h // 2:, :] = (96, 74, 70)
            vv = np.array(v[k]).astype(np.float32); ee = np.array(e[k]).astype(np.float32)
            a = vv[..., 3:4] / 255
            bg = bg * (1 - a) + vv[..., :3] * a
            bg = np.clip(bg + ee[..., :3] * (ee[..., 3:4] / 255), 0, 255)
            im = Image.fromarray(bg.astype(np.uint8)).resize((w * Z, h * Z), Image.NEAREST)
            sheet.paste(im, ((k % 4) * w * Z, (k // 4) * h * Z))
        sheet.save(os.path.join(outdir, f'{name}_preview.png'))
    print('ok')
