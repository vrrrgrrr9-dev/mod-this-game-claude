"""3D swing arcs - the slash effects that make Scyther's attacks read as 3D.

Built the same way as the game's own sword/scythe effects (Azrael's *_ef sprites, the reaper's
circular sweep): the blade tip travels along a CIRCLE IN 3D SPACE; that circle lies in a tilted
plane and is projected to the screen, giving a perspective ellipse/crescent.  Along the sweep the
band is thicker where the path comes toward the camera and thinner where it recedes, brightest at
the leading edge (the blade) and fading to nothing at the tail.  Everything is smooth and
anti-aliased with a soft glow (rendered 4x then box-filtered), like the game's effect sprites.

Each arc is split by depth into a BACK sprite (the part of the swing behind the fighter, drawn
before his body) and a FRONT sprite (drawn over him), so a swing wraps around the rooster.

  python arcs.py <outdir>  ->  arc_<name>_b.png / arc_<name>_f.png strips (+ preview)
"""
import math, os, sys
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

SSA = 4                                   # supersampling
NFR = 6

CORE = np.array((248, 236, 255), np.float32)
BODY = np.array((196, 120, 255), np.float32)
DEEP = np.array((110, 40, 210), np.float32)
STARC = np.array((170, 240, 255), np.float32)

# name: (frame w, h, origin x, y, radius, tilt, roll, a0, a1, width, turns/headspin, back layer?)
ARCS = {
    'rise':   dict(w=136, h=120, ox=56, oy=70, r=44, tilt=52, roll=-38, a0=40, a1=235, wid=16),
    'twirl':  dict(w=112, h=96, ox=56, oy=48, r=30, tilt=64, roll=0, a0=0, a1=330, wid=6, spin=True),
    'orbit':  dict(w=176, h=96, ox=88, oy=52, r=62, tilt=78, roll=-4, a0=0, a1=340, wid=13, spin=True),
    'cleave': dict(w=128, h=136, ox=40, oy=96, r=52, tilt=18, roll=0, a0=-150, a1=40, wid=19),
    'stitcha': dict(w=96, h=80, ox=36, oy=44, r=30, tilt=40, roll=30, a0=-110, a1=10, wid=6),
    'stitchb': dict(w=96, h=80, ox=36, oy=44, r=30, tilt=40, roll=-30, a0=110, a1=-10, wid=6),
    'sweep':  dict(w=160, h=72, ox=64, oy=48, r=56, tilt=76, roll=0, a0=-170, a1=30, wid=14),
    'xcut':   dict(w=128, h=128, ox=64, oy=64, r=110, cyp=-110, tilt=8, roll=0, a0=62, a1=118, wid=12, xcut=True),
    'spin':   dict(w=96, h=80, ox=48, oy=40, r=28, tilt=70, roll=-10, a0=0, a1=340, wid=6, spin=True),
}


def _path(cfg, a0, a1, n):
    """points along the 3D circle -> (x, y, z) screen coords relative to the origin."""
    tl, rl = math.radians(cfg['tilt']), math.radians(cfg['roll'])
    out = []
    cxp, cyp = cfg.get('cxp', 0.0), cfg.get('cyp', 0.0)
    for a in np.linspace(math.radians(a0), math.radians(a1), n):
        x, y = cxp + cfg['r'] * math.cos(a), cyp + cfg['r'] * math.sin(a)
        y3, z3 = y * math.cos(tl), y * math.sin(tl)          # tilt the plane away
        xr = x * math.cos(rl) - y3 * math.sin(rl)
        yr = x * math.sin(rl) + y3 * math.cos(rl)
        out.append((xr, yr, z3))
    return out


def _centre(cfg):
    """screen position of the circle centre (for arcs whose circle is offset in-plane)."""
    tl, rl = math.radians(cfg['tilt']), math.radians(cfg['roll'])
    x, y = cfg.get('cxp', 0.0), cfg.get('cyp', 0.0)
    y3 = y * math.cos(tl)
    return (x * math.cos(rl) - y3 * math.sin(rl), x * math.sin(rl) + y3 * math.cos(rl))


def _stamp(buf, x, y, rad, val):
    """add a soft disc (anti-aliased) of radius rad (supersampled px) with peak val."""
    h, w = buf.shape
    x0, x1 = int(max(0, x - rad - 2)), int(min(w, x + rad + 3))
    y0, y1 = int(max(0, y - rad - 2)), int(min(h, y + rad + 3))
    if x1 <= x0 or y1 <= y0:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1]
    d = np.sqrt((xx - x) ** 2 + (yy - y) ** 2)
    v = np.clip((rad - d) / 1.5 + 0.5, 0, 1) * val
    np.maximum(buf[y0:y1, x0:x1], v, out=buf[y0:y1, x0:x1])


def render_arc(cfg, k, seed=1):
    """frame k -> (back RGBA, front RGBA) PIL images."""
    W, H, ox, oy = cfg['w'], cfg['h'], cfg['ox'], cfg['oy']
    S = SSA
    inten = [np.zeros((H * S, W * S), np.float32) for _ in range(2)]   # back, front
    core = [np.zeros((H * S, W * S), np.float32) for _ in range(2)]
    rng = np.random.default_rng(seed + k * 7)
    span_fr = (0.55, 1.0, 1.0, 1.0, 1.0, 1.0)[k]                  # frame 0: swing still travelling
    fade = (1.0, 1.0, 0.85, 0.62, 0.38, 0.16)[k]
    tail_cut = (0.0, 0.0, 0.18, 0.4, 0.62, 0.8)[k]                # the tail erodes away
    arcs = []
    if cfg.get('xcut'):
        for rl, a0, a1 in ((45, 62, 118), (-45, 118, 62)):
            c2 = dict(cfg, roll=rl)
            arcs.append((c2, a0, a0 + (a1 - a0) * span_fr))
    elif cfg.get('spin'):
        head = cfg['a0'] + k * 72                                  # the head travels around
        arcs.append((cfg, head - 300, head))
    else:
        arcs.append((cfg, cfg['a0'], cfg['a0'] + (cfg['a1'] - cfg['a0']) * span_fr))
    for c2, a0, a1 in arcs:
        n = 140
        pts = _path(c2, a0, a1, n)
        for i, (x, y, z) in enumerate(pts):
            t = i / (n - 1)
            if t < tail_cut:
                continue
            tt = (t - tail_cut) / max(1e-3, 1 - tail_cut)
            near = 1 + 0.5 * (z / c2['r'])                         # perspective: nearer = thicker
            wid = c2['wid'] * (0.22 + 0.78 * tt ** 0.8) * near * (0.6 + 0.4 * fade)
            val = (0.25 + 0.75 * tt ** 1.3) * fade
            layer = 1 if z >= -0.5 else 0
            # the band sits INSIDE the tip path: bright sharp outer edge, softer inner body
            cx, cy = (ox + x) * S, (oy + y) * S
            ccx, ccy = _centre(c2)
            r0 = math.hypot(x - ccx, y - ccy) or 1
            ux, uy = (x - ccx) / r0, (y - ccy) / r0
            for j, (off, vv, cv) in enumerate(((0.0, 1.0, 1.0), (0.3, 0.8, 0.3), (0.6, 0.55, 0.0))):
                px, py = cx - ux * off * wid * S, cy - uy * off * wid * S
                _stamp(inten[layer], px, py, wid * S * (0.55 - 0.15 * j), val * vv)
                if cv > 0:
                    _stamp(core[layer], cx - ux * 0.08 * wid * S, cy - uy * 0.08 * wid * S, max(1.2, wid * S * 0.18), val * cv)
    outs = []
    for L in range(2):
        I = inten[L]; C = core[L]
        # soft glow halo around the band
        glow = ndi.gaussian_filter(I, 3.2 * S) * 1.4
        I2 = np.clip(np.maximum(I, glow * 0.7), 0, 1)
        col = DEEP[None, None] * (1 - I2[..., None]) + BODY[None, None] * I2[..., None]
        col = col * (1 - C[..., None]) + CORE[None, None] * C[..., None]
        alpha = np.clip(I2 * 1.15 + C * 0.4, 0, 1)
        rgba = np.concatenate([col, alpha[..., None] * 255], axis=2)
        # box-filter down to 1x (premultiplied)
        pm = rgba.copy(); pm[..., :3] *= alpha[..., None]
        small = pm.reshape(H, S, W, S, 4).mean(axis=(1, 3))
        a = small[..., 3:4] / 255
        rgb = np.where(a > 1e-4, small[..., :3] / np.maximum(a, 1e-4), 0)
        out = np.concatenate([np.clip(rgb, 0, 255), np.clip(small[..., 3:4], 0, 255)], axis=2)
        # sparkles shed by the blade, drifting outward in later frames
        if k >= 1 and L == 1:
            for _ in range(10):
                i = rng.integers(len(pts) // 3, len(pts))
                x, y, z = pts[i]
                drift = (k - 1) * 3.0
                r0 = math.hypot(x, y) or 1
                sx, sy = int(ox + x + x / r0 * drift + rng.uniform(-2, 2)), int(oy + y + y / r0 * drift + rng.uniform(-2, 2))
                if 0 <= sx < W and 0 <= sy < H:
                    out[sy, sx, :3] = STARC; out[sy, sx, 3] = 255 * fade
        outs.append(Image.fromarray(out.astype(np.uint8), 'RGBA'))
    return outs[0], outs[1]


def strips(name):
    cfg = ARCS[name]
    back, front = [], []
    for k in range(NFR):
        b, f = render_arc(cfg, k, seed=hash(name) & 0xffff)
        back.append(b); front.append(f)
    def st(fr):
        s = Image.new('RGBA', (cfg['w'] * len(fr), cfg['h']), (0, 0, 0, 0))
        for i, im in enumerate(fr):
            s.paste(im, (i * cfg['w'], 0))
        return s
    return st(back), st(front)


def has_back(name):
    cfg = ARCS[name]
    return math.sin(math.radians(cfg['tilt'])) > 0.5


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else '/tmp'
    os.makedirs(out, exist_ok=True)
    rows = []
    for name in ARCS:
        b, f = strips(name)
        b.save(os.path.join(out, f'arc_{name}_b.png')); f.save(os.path.join(out, f'arc_{name}_f.png'))
        rows.append((name, b, f))
    # preview: back + front over a mid-tone backdrop
    Wd = max(f.width for _, _, f in rows); Hd = sum(f.height + 6 for _, _, f in rows)
    sheet = Image.new('RGBA', (Wd, Hd), (40, 32, 64, 255))
    y = 0
    for name, b, f in rows:
        sheet.alpha_composite(b, (0, y)); sheet.alpha_composite(f, (0, y))
        y += f.height + 6
    sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST).save(os.path.join(out, 'arcs_preview.png'))
    print('arcs ok')
