"""The Void Reaper - Scyther's double-bladed obsidian scythe, rendered as a 3D object in pixel art.

Modelled after the user's reference: a long, slightly wavy obsidian haft; at each end a spiked
crown with a glowing gem; from each crown a long blade that runs straight out sideways and then
hooks back toward the centre (cutting edge on the inside of the curve, thorns along the outer spine).
The two blades sit on opposite sides (S-shape).  Black obsidian, violet veins glowing through it.

The weapon is planar; render(angle, tilt) spins it by `angle` inside its plane and tilts that plane
by `tilt` degrees about the screen's horizontal axis (tilt 0 = flat facing the camera; ~65 = the
spin plane seen in perspective, an orbit around the holder like the game's own reaper).  Parts are
depth-sorted and can be split into a BACK layer (z < 0, drawn behind the body) and a FRONT layer.
held=True adds the wing-feather fingers wrapped around the grip.
"""
import math, os, sys
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rig
from rig import Canvas, lerp, _m

WS = 200                       # sprite size at 2x (drawn at half scale in game); origin at the centre
KSCALE = 0.9                   # overall weapon scale vs the rooster
HALF = 30.0                    # half haft length (local units)
OBS = _m((30, 20, 44), (82, 62, 120), (10, 6, 18), (132, 90, 220), (4, 2, 10))
OBS2 = _m((44, 30, 64), (100, 78, 146), (16, 10, 28), (150, 100, 236), (6, 3, 14))
VEIN = (186, 86, 255, 255)
VEIN_HOT = (240, 196, 255, 255)
EDGE = (226, 150, 255, 255)
SUBV = (120, 50, 200, 255)
RUNE = (206, 130, 255, 255)
GEM = (236, 150, 255, 255)
GEM_HOT = (255, 236, 255, 255)
HALO = (150, 60, 250)


def cubic(a, b, c, d, n=24):
    out = []
    for t in np.linspace(0, 1, n):
        u = 1 - t
        out.append((u ** 3 * a[0] + 3 * u * u * t * b[0] + 3 * u * t * t * c[0] + t ** 3 * d[0],
                    u ** 3 * a[1] + 3 * u * u * t * b[1] + 3 * u * t * t * c[1] + t ** 3 * d[1]))
    return out


def _normals(pts):
    ns = []
    for i in range(len(pts)):
        a = pts[max(0, i - 1)]; b = pts[min(len(pts) - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]; L = math.hypot(dx, dy) or 1
        ns.append((-dy / L, dx / L))
    return ns


def blade_geo(s):
    root = (s * (HALF - 1.0), 0.0)
    spine = cubic(root, (s * (HALF + 6.0), -s * 12.0), (s * (HALF + 5.0), -s * 30.0), (s * (HALF - 13.0), -s * 37.0), 30)
    ns = _normals(spine)
    outer, inner = [], []
    n = len(spine)
    for i, (p, nn) in enumerate(zip(spine, ns)):
        t = i / (n - 1)
        w = 5.0 * (1 - t) ** 0.9 + 0.25
        o = 1 if nn[0] * s > 0 else -1
        outer.append((p[0] + nn[0] * w * o, p[1] + nn[1] * w * o))
        inner.append((p[0] - nn[0] * w * o * 0.9, p[1] - nn[1] * w * o * 0.9))
    thorns = []
    for t, L in ((0.1, 4.4), (0.22, 3.8), (0.34, 3.2), (0.46, 2.7), (0.58, 2.1), (0.7, 1.5)):
        i = int(t * (n - 1))
        p = outer[i]; nn = ns[i]; o = 1 if nn[0] * s > 0 else -1
        d = (nn[0] * o, nn[1] * o)
        back = (spine[max(0, i - 2)][0] - spine[i][0], spine[max(0, i - 2)][1] - spine[i][1])
        bl = math.hypot(*back) or 1
        tip = (p[0] + d[0] * L + back[0] / bl * L * 0.55, p[1] + d[1] * L + back[1] / bl * L * 0.55)
        thorns.append([outer[max(0, i - 2)], tip, outer[min(n - 1, i + 2)]])
    return outer + inner[::-1], spine, inner, thorns


def haft_y(x):
    return 1.5 * math.sin(math.pi * x / HALF)


def parts():
    """the weapon as a list of (group, kind, data) in local 2D coords (group = depth sorting unit)."""
    P = []
    for s, g in ((1, 'R'), (-1, 'L')):
        poly, spine, inner, thorns = blade_geo(s)
        P.append(('blade' + g, 'thorns', thorns))
        P.append(('blade' + g, 'blade', (poly, spine, inner)))
        x0 = s * HALF
        P.append(('crown' + g, 'polys', [[(x0 - s * 1.5, 1.0), (x0 + s * 3.0, 6.5), (x0 + s * 0.5, 0.6)],
                                          [(x0 - s * 4.0, 1.2), (x0 - s * 3.0, 6.0), (x0 - s * 1.6, 1.4)],
                                          [(x0 - s * 5.5, -1.0), (x0 - s * 8.5, -4.5), (x0 - s * 4.0, -1.6)]]))
        P.append(('crown' + g, 'spear', [(x0 - s * 1.0, -1.6), (x0 + s * 8.5, 0.6), (x0 - s * 1.0, 1.9)]))
        P.append(('crown' + g, 'knot', (x0 - s * 3.6, 0.0)))
        xs = np.linspace(0, s * HALF, 20)
        P.append(('haft' + g, 'haft', [(x, haft_y(x)) for x in xs]))
        xc = s * 14.0
        P.append(('haft' + g, 'collar', (xc, haft_y(xc))))
    P.append(('grip', 'grip', None))
    return P


def _dimmed(mat, k):
    if k >= 0.99:
        return mat
    return {kk: tuple(int(c_ * k) for c_ in v[:3]) + (255,) for kk, v in mat.items() if kk != 'ramp'}


def render(angle, held=True, tilt=0.0, layer='all', glow=True):
    """-> RGBA PIL image (WS x WS, origin at the centre).
    layer: 'all' | 'front' (parts with depth >= 0) | 'back' (depth < 0)."""
    c = Canvas(WS, WS, WS // 2, WS // 2)
    a, t = math.radians(angle), math.radians(tilt)
    ca, sa, ct, st = math.cos(a), math.sin(a), math.cos(t), math.sin(t)
    K = KSCALE

    def X(p):                                  # local (x, y) -> screen (x, y)
        x, y = p[0] * ca - p[1] * sa, p[0] * sa + p[1] * ca
        return (x * K, y * ct * K)

    def Z(p):                                  # depth toward the viewer
        return (p[0] * sa + p[1] * ca) * st

    def XL(pts):
        return [X(p) for p in pts]

    dim = 0.7 + 0.3 * abs(ct)                  # a tilted plane catches less key light
    obs, obs2 = _dimmed(OBS, dim), _dimmed(OBS2, dim)
    groups = {}
    for g, kind, data in parts():
        groups.setdefault(g, []).append((kind, data))

    def gdepth(g):
        pts = []
        for kind, data in groups[g]:
            if kind == 'blade':
                pts += data[1]
            elif kind in ('haft', 'spear'):
                pts += data
            elif kind in ('knot', 'collar'):
                pts.append(data)
        return float(np.mean([Z(p) for p in pts])) if pts else 0.0

    blades = np.zeros((WS, WS), bool)
    for g in sorted(groups, key=gdepth):
        dz = gdepth(g)
        if layer == 'front' and dz < -0.01:
            continue
        if layer == 'back' and dz >= -0.01:
            continue
        for kind, data in groups[g]:
            if kind == 'thorns':
                tm = np.zeros((WS, WS), bool)
                for th in data:
                    tm |= c.poly(XL(th))
                c.paint(tm, obs2, shade=1, hl=1, rim=0)
                blades |= tm
            elif kind == 'blade':
                poly, spine, inner = data
                bm = c.poly(XL(poly))
                c.paint(bm, obs, glossy=True, bump=2.0)
                blades |= bm
                c.img[c.taper(XL(spine[2:-4]), 0.55, 0.25) & bm] = VEIN
                sub = [lerp(spine[i], inner[i], 0.55) for i in range(4, len(spine) - 6)]
                c.img[c.taper(XL(sub), 0.4, 0.2) & bm] = SUBV
                c.img[c.taper(XL(inner[1:-1]), 0.7, 0.3) & bm] = EDGE
                c.img[c.taper(XL(inner[6:-8]), 0.35, 0.2) & bm] = VEIN_HOT
                # rune engravings between the spine vein and the outer edge
                for i in range(5, len(spine) - 8, 3):
                    a_ = lerp(spine[i], poly[i], 0.35); b_ = lerp(spine[i], poly[i], 0.7)
                    c.img[c.taper(XL([a_, b_]), 0.16, 0.16) & bm] = RUNE if (i // 3) % 2 else SUBV
            elif kind == 'polys':
                for pp in data:
                    c.paint(c.poly(XL(pp)), obs2, shade=1, hl=1, rim=0)
            elif kind == 'spear':
                sm = c.poly(XL(data))
                c.paint(sm, obs, shade=1, hl=1, rim=1)
                c.img[c.taper(XL([data[0], data[1]]), 0.3, 0.2) & sm] = EDGE
            elif kind == 'knot':
                kx, ky = data
                km = c.poly(XL([(kx - 2.6, 0), (kx, -3.4), (kx + 2.6, 0), (kx, 3.4)]))
                c.paint(km, obs2, shade=1, hl=1, rim=1)
                gm = c.ell(X(data), 1.3 * K, max(0.45, 1.3 * K * abs(ct))) & km
                c.img[gm] = GEM
                c.img[gm & ~rig.shift(gm, 1, 1)] = (170, 80, 230, 255)        # facet shade
                c.img[c.ell(X((kx - 0.4, -0.4)), 0.45, 0.45) & gm] = GEM_HOT
            elif kind == 'haft':
                hm = c.taper(XL(data), 1.7 * K, 1.7 * K)
                c.paint(hm, obs2, shade=1, hl=1, rim=1)
                for k in range(1, len(data) - 1, 2):      # spiral wrap
                    x_, y_ = data[k]
                    c.img[c.taper(XL([(x_ - 0.7, y_ + 1.3), (x_ + 0.7, y_ - 1.3)]), 0.14, 0.14) & hm] = obs2['light']
                for k in range(0, len(data) - 3, 4):
                    seg = c.taper(XL([(data[k][0], data[k][1] + 0.3), (data[k + 2][0], data[k + 2][1] - 0.3)]), 0.3, 0.3) & hm
                    c.img[seg] = VEIN
            elif kind == 'collar':
                xc, yc = data
                col = c.poly(XL([(xc - 2.0, yc), (xc, yc - 3.0), (xc + 2.0, yc), (xc, yc + 3.0)]))
                c.paint(col, obs2, shade=1, hl=1, rim=0)
                c.img[c.ell(X(data), 0.8, 0.8) & col] = GEM
            elif kind == 'grip':
                wrap = c.taper(XL([(x, haft_y(x)) for x in np.linspace(-5.5, 5.5, 8)]), 1.9 * K, 1.9 * K)
                c.paint(wrap, rig.COVT, shade=1, hl=1, rim=0)
                for x in (-4.0, -1.5, 1.0, 3.5):
                    y = haft_y(x)
                    band = c.taper(XL([(x - 0.8, y + 1.9), (x + 0.8, y - 1.9)]), 0.35, 0.35) & wrap
                    c.img[band] = rig.COVT['shadow']
                if held:
                    knob = c.ell(X((-1.0, 2.6)), 2.6 * K, 2.2 * K)
                    c.paint(knob, rig.COVT, shade=1, hl=1, rim=1)
                    for p0, p1 in (((-3.6, 3.4), (0.4, -2.8)), ((-1.4, 3.8), (2.6, -2.4)), ((0.8, 3.9), (4.4, -1.6))):
                        c.paint(c.taper(XL([p0, lerp(p0, p1, 0.5), p1]), 1.05 * K, 0.4 * K), rig.PRIM, shade=1, hl=1, rim=0)
    c.outline()
    img = c.img
    if glow and blades.any():
        gl = ndi.gaussian_filter(blades.astype(np.float32), 2.2)
        al = np.clip(gl * 1.35, 0, 1) * 0.6
        empty = img[..., 3] == 0
        halo = np.zeros_like(img)
        halo[..., 0], halo[..., 1], halo[..., 2] = HALO
        halo[..., 3] = (al * 255).astype(np.uint8)
        img = np.where(empty[..., None], halo, img)
    return Image.fromarray(img.astype(np.uint8), 'RGBA')


def strip(n=32, held=True, tilt=0.0, layer='all'):
    s = Image.new('RGBA', (WS * n, WS), (0, 0, 0, 0))
    for i in range(n):
        s.paste(render(i * 360.0 / n, held=held, tilt=tilt, layer=layer), (i * WS, 0))
    return s


SETS = {   # name: (frames, held, tilt, layer)
    'wpn': (32, True, 0.0, 'all'),            # held, flat (normal holds / swings)
    'wpnfree': (32, False, 0.0, 'all'),       # loose
    'orbb': (24, True, 64.0, 'back'),         # held twirl, far half (drawn behind the body)
    'orbf': (24, True, 64.0, 'front'),        # held twirl, near half
    'disc': (24, False, 74.0, 'all'),         # thrown buzzsaw (spinning almost flat)
}


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else '/tmp'
    row = [render(a, tilt=tl, layer=ly) for a, tl, ly in
           ((-35, 0, 'all'), (0, 64, 'all'), (60, 64, 'all'), (120, 64, 'all'), (0, 64, 'back'), (0, 64, 'front'), (30, 74, 'all'))]
    sheet = Image.new('RGBA', (WS * 4 * len(row), WS * 4), (18, 12, 36, 255))
    for i, im in enumerate(row):
        bg = Image.new('RGBA', im.size, (18, 12, 36, 255)); bg.alpha_composite(im)
        sheet.paste(bg.resize((WS * 4, WS * 4), Image.NEAREST), (i * WS * 4, 0))
    sheet.save(os.path.join(out, 'weapon3d.png'))
    print('ok')
