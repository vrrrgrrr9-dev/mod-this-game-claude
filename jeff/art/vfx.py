"""Procedural pixel-art effects for Jeff's skills (drawn in-game with additive blending).

Every effect is rendered as a float "light" field at 3x, downsampled, then mapped through a
small palette ramp so it keeps a crisp pixel look next to the game's sprites. Alpha carries the
intensity (the game draws these with bm_add).
"""
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw

SS = 3
RNG = np.random.default_rng(1005)

RAMPS = {
    'amber':  [(70, 25, 5), (170, 70, 15), (255, 150, 35), (255, 215, 100), (255, 250, 215)],
    'violet': [(45, 15, 100), (110, 45, 210), (175, 110, 255), (230, 190, 255), (255, 245, 255)],
    'cyan':   [(15, 45, 110), (30, 120, 220), (80, 205, 255), (180, 245, 255), (255, 255, 255)],
    'red':    [(80, 5, 10), (190, 20, 25), (255, 70, 50), (255, 170, 140), (255, 250, 240)],
    'white':  [(70, 70, 90), (140, 140, 170), (200, 200, 230), (235, 235, 255), (255, 255, 255)],
}


class Light:
    """float intensity canvas at SS x resolution"""
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.f = np.zeros((h * SS, w * SS), np.float32)
        self.yy, self.xx = np.mgrid[0:h * SS, 0:w * SS].astype(np.float32) / SS

    def glow(self, x, y, r, a=1.0, sharp=2.0):
        d = np.sqrt((self.xx - x) ** 2 + (self.yy - y) ** 2) / max(r, 1e-3)
        self.f += a * np.clip(1 - d, 0, 1) ** sharp

    def disc(self, x, y, r, a=1.0):
        d = np.sqrt((self.xx - x) ** 2 + (self.yy - y) ** 2)
        self.f += a * (d <= r)

    def lines(self, pts, a=1.0, width=1.0, closed=False):
        im = Image.new('F', (self.w * SS, self.h * SS), 0)
        dr = ImageDraw.Draw(im)
        P = [(p[0] * SS, p[1] * SS) for p in pts]
        if closed:
            P = P + [P[0]]
        dr.line(P, fill=a, width=max(1, int(round(width * SS))))
        self.f += np.array(im, np.float32)

    def poly(self, pts, a=1.0):
        im = Image.new('F', (self.w * SS, self.h * SS), 0)
        ImageDraw.Draw(im).polygon([(p[0] * SS, p[1] * SS) for p in pts], fill=a)
        self.f += np.array(im, np.float32)

    def ellipse_ring(self, cx, cy, rx, ry, a=1.0, width=1.0, n=96, rot=0.0, dash=None):
        pts = []
        for i in range(n + 1):
            t = 2 * math.pi * i / n + rot
            pts.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
        if dash:
            for i in range(0, n, dash * 2):
                self.lines(pts[i:i + dash + 1], a, width)
        else:
            self.lines(pts, a, width)

    def result(self, ramp, gain=1.0, levels=5):
        small = self.f.reshape(self.h, SS, self.w, SS).max(axis=(1, 3)) * 0.6 + \
            self.f.reshape(self.h, SS, self.w, SS).mean(axis=(1, 3)) * 0.4
        v = np.clip(small * gain, 0, 1)
        q = np.floor(v * levels + 0.25).astype(int)
        q = np.clip(q, 0, levels)
        cols = np.array([(0, 0, 0)] + list(RAMPS[ramp]), np.uint8)[:levels + 1]
        rgb = cols[q]
        alpha = np.clip(q / levels * 1.15, 0, 1)
        out = np.zeros((self.h, self.w, 4), np.uint8)
        out[..., :3] = rgb
        out[..., 3] = (alpha * 255).astype(np.uint8)
        return Image.fromarray(out, 'RGBA')


def strip(frames):
    w, h = frames[0].size
    s = Image.new('RGBA', (w * len(frames), h), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        s.paste(f, (i * w, 0))
    return s


def over(a, b):
    """composite two RGBA effect frames (b on top)"""
    o = a.copy(); o.alpha_composite(b); return o


def glyph(L, cx, cy, s, kind, a=1.0):
    """tiny rune glyphs"""
    if kind == 0:
        L.lines([(cx - s, cy - s), (cx + s, cy + s)], a); L.lines([(cx - s, cy + s), (cx + s, cy - s)], a)
    elif kind == 1:
        L.lines([(cx, cy - s), (cx, cy + s)], a); L.lines([(cx - s, cy), (cx + s, cy - s)], a)
    elif kind == 2:
        L.lines([(cx - s, cy + s), (cx, cy - s), (cx + s, cy + s)], a)
    else:
        L.ellipse_ring(cx, cy, s, s * 0.7, a, n=10)


# --- skill 1 -----------------------------------------------------------------------------
def s1_circle():
    W, H, N = 96, 32, 16
    frames = []
    for f in range(N):
        t = f / N
        L = Light(W, H)
        cx, cy = 48, 16
        pulse = 0.75 + 0.25 * math.sin(t * 2 * math.pi * 2)
        L.ellipse_ring(cx, cy, 44, 13, 0.9 * pulse, 1.0)
        L.ellipse_ring(cx, cy, 36, 10.5, 0.7 * pulse, 1.0, dash=4, rot=t * 2 * math.pi)
        L.ellipse_ring(cx, cy, 22, 6.5, 0.8, 1.0)
        # rotating hexagram
        for k in range(2):
            pts = []
            for i in range(3):
                ang = -t * 2 * math.pi + k * math.pi / 3 + i * 2 * math.pi / 3
                pts.append((cx + 22 * math.cos(ang), cy + 6.5 * math.sin(ang)))
            L.lines(pts, 0.6, closed=True)
        for i in range(8):                                 # runes riding the ring
            ang = t * 2 * math.pi + i * math.pi / 4
            glyph(L, cx + 40 * math.cos(ang), cy + 11.8 * math.sin(ang), 1.6, i % 4, 0.9)
        L.glow(cx, cy, 30, 0.35 * pulse, 1.5)
        frames.append(over(L.result('violet', 1.0), Light(W, H).result('amber')))
    return strip(frames)


def ant(L, x, y, d, phase, a=1.0, s=1.0):
    """a glowing magic ant facing d (+1 right)"""
    L.disc(x, y, 1.1 * s, a)                      # abdomen
    L.disc(x + d * 1.9 * s, y - 0.3, 0.8 * s, a)  # thorax
    L.disc(x + d * 3.2 * s, y - 0.6, 0.9 * s, a)  # head
    L.lines([(x + d * 3.6 * s, y - 1.2), (x + d * 4.8 * s, y - 2.6)], a * 0.8)   # antenna
    for k in range(3):                             # legs scuttling
        lx = x + d * (0.8 + k * 1.1) * s
        sw = math.sin(phase + k * 2.1) * 1.2
        L.lines([(lx, y), (lx + sw, y + 1.8 * s)], a * 0.7)


def s1_swarm():
    W, H, N = 112, 56, 12
    ox, oy = 56, 40
    frames = []
    ants = [(RNG.uniform(0, 2 * math.pi), RNG.uniform(6, 26), RNG.uniform(3, 15), RNG.uniform(0.7, 1.3)) for _ in range(34)]
    for f in range(N):
        t = f / N
        L = Light(W, H); G = Light(W, H)
        G.glow(ox + 6, oy - 10, 34, 0.45, 1.6)
        G.glow(ox + 22, oy - 10, 14, 0.7, 2.0)
        for k, (a0, rx, ry, sp) in enumerate(ants):
            ang = a0 + t * 2 * math.pi * sp
            x = ox + 4 + rx * math.cos(ang) * 1.6
            y = oy - 12 + ry * math.sin(ang) * 0.9
            ant(L, x, y, 1, t * 12 + k, 1.0 if math.sin(ang) > -0.3 else 0.6)
        for k in range(6):                              # front runners
            x = ox + 24 + ((t * 40 + k * 9) % 22)
            ant(L, x, oy - 4 - (k % 3) * 6, 1, t * 16 + k, 1.0, 1.1)
        for k in range(12):                             # embers trailing
            x = ox - 40 + ((k * 7 + t * 60) % 44)
            y = oy - 6 - 20 * ((k * 37 % 11) / 11) + 4 * math.sin(t * 6 + k)
            L.disc(x, y, 0.6, 0.7)
        img = over(G.result('violet', 0.9), L.result('amber', 1.1))
        frames.append(img)
    return strip(frames)


def s1_burst():
    W, H, N = 128, 128, 16
    cx, cy = 64, 92
    frames = []
    shards = [(RNG.uniform(0, 2 * math.pi), RNG.uniform(0.6, 1.2)) for _ in range(26)]
    for f in range(N):
        t = f / (N - 1)
        L = Light(W, H); V = Light(W, H)
        if f < 4:
            L.glow(cx, cy - 20, 18 + f * 10, 1.4 - f * 0.15, 1.4)
        r = 8 + t * 54
        fade = max(0.0, 1 - t * 1.05)
        V.ellipse_ring(cx, cy - 20, r, r, 0.9 * fade, 1.5)
        V.ellipse_ring(cx, cy - 20, r * 0.72, r * 0.72, 0.7 * fade, 1.0, dash=3, rot=t * 3)
        for i in range(10):
            ang = i * math.pi / 5 + t * 1.5
            glyph(V, cx + r * 0.86 * math.cos(ang), cy - 20 + r * 0.86 * math.sin(ang), 2.2, i % 4, fade)
        L.ellipse_ring(cx, cy, r * 1.1, r * 0.25, 0.8 * fade, 1.5)   # ground shock
        for ang, sp in shards:
            d = (6 + 60 * t * sp)
            x = cx + d * math.cos(ang); y = cy - 20 + d * math.sin(ang) * 0.8 + 30 * t * t
            ant(L, x, y, 1 if math.cos(ang) > 0 else -1, f + ang * 5, fade * 1.1)
        L.glow(cx, cy - 20, 40 * (1 - t) + 6, 0.5 * fade, 1.2)
        frames.append(over(V.result('violet', 1.0), L.result('amber', 1.1)))
    return strip(frames)


def spark(ramp='white'):
    W, H, N = 16, 16, 8
    frames = []
    for f in range(N):
        L = Light(W, H)
        k = math.sin(f / N * math.pi)
        s = 1 + 6 * k
        L.lines([(8 - s, 8), (8 + s, 8)], 1.0); L.lines([(8, 8 - s), (8, 8 + s)], 1.0)
        L.lines([(8 - s * 0.5, 8 - s * 0.5), (8 + s * 0.5, 8 + s * 0.5)], 0.6)
        L.lines([(8 - s * 0.5, 8 + s * 0.5), (8 + s * 0.5, 8 - s * 0.5)], 0.6)
        L.glow(8, 8, 2 + 3 * k, 1.0)
        frames.append(L.result(ramp, 1.0))
    return strip(frames)


# --- skill 2 -----------------------------------------------------------------------------
def s2_orb():
    W, H, N = 40, 40, 8
    frames = []
    for f in range(N):
        t = f / N
        L = Light(W, H); V = Light(W, H)
        V.glow(20, 20, 19, 0.7, 1.3)
        L.glow(20, 20, 9 + 1.5 * math.sin(t * 2 * math.pi), 1.3, 1.6)
        for i in range(8):
            ang = t * 2 * math.pi * 0.5 + i * math.pi / 4
            ln = 15 if i % 2 == 0 else 10
            L.lines([(20 + 4 * math.cos(ang), 20 + 4 * math.sin(ang)), (20 + ln * math.cos(ang), 20 + ln * math.sin(ang))], 0.8)
        frames.append(over(V.result('violet', 0.9), L.result('cyan', 1.1)))
    return strip(frames)


def s2_beam():
    W, H, N = 32, 32, 8
    frames = []
    for f in range(N):
        t = f / N
        L = Light(W, H); V = Light(W, H)
        yy = L.yy - 16
        width = 6.5 + 1.0 * math.sin(t * 2 * math.pi * 2)
        V.f += np.clip(1 - np.abs(yy) / (width * 1.9), 0, 1) ** 1.3 * 0.9
        L.f += np.clip(1 - np.abs(yy) / width, 0, 1) ** 0.8 * 1.0
        L.f += np.clip(1 - np.abs(yy) / (width * 0.35), 0, 1) * 1.2
        for k in range(2):     # helix strands
            ph = t * 2 * math.pi + k * math.pi
            pts = [(x, 16 + (width + 1.5) * math.sin(x / 32 * 2 * math.pi + ph)) for x in np.linspace(0, 32, 40)]
            V.lines(pts, 0.9, 1.0)
        frames.append(over(V.result('violet', 1.0), L.result('cyan', 1.05)))
    return strip(frames)


def s2_tip():
    W, H, N = 48, 48, 8
    frames = []
    for f in range(N):
        t = f / N
        L = Light(W, H); V = Light(W, H)
        L.glow(24, 24, 13 + 2 * math.sin(t * 6.28), 1.6, 1.4)
        V.glow(24, 24, 23, 0.8, 1.2)
        for i in range(6):
            ang = t * 1.2 + i * math.pi / 3
            L.lines([(24, 24), (24 + 22 * math.cos(ang), 24 + 22 * math.sin(ang) * 0.6)], 0.7)
        L.lines([(4, 24), (44, 24)], 1.0, 1.5); L.lines([(24, 10), (24, 38)], 0.9)
        frames.append(over(V.result('violet', 1.0), L.result('cyan', 1.0)))
    return strip(frames)


def s2_nova():
    W, H, N = 128, 128, 16
    c = 64
    frames = []
    stars = [(RNG.uniform(0, 2 * math.pi), RNG.uniform(0.3, 1.0)) for _ in range(22)]
    for f in range(N):
        t = f / (N - 1)
        L = Light(W, H); V = Light(W, H)
        fade = max(0.0, 1 - t)
        if f < 3:
            L.glow(c, c, 24 + 14 * f, 1.8, 1.3)
        rad = 6 + 56 * math.sqrt(t)
        for i in range(8):                      # 8-pointed star rays
            ang = i * math.pi / 4 + t * 0.6
            ln = rad * (1.25 if i % 2 == 0 else 0.8)
            w = 3.5 * fade + 0.5
            p1 = (c + ln * math.cos(ang), c + ln * math.sin(ang))
            pa = (c + w * math.cos(ang + math.pi / 2), c + w * math.sin(ang + math.pi / 2))
            pb = (c + w * math.cos(ang - math.pi / 2), c + w * math.sin(ang - math.pi / 2))
            L.poly([pa, p1, pb], 0.9 * fade)
        V.ellipse_ring(c, c, rad, rad, 0.9 * fade, 2.0)
        V.ellipse_ring(c, c, rad * 0.6, rad * 0.6, 0.6 * fade, 1.0, dash=3, rot=-t * 3)
        pts = []
        for ang, sp in stars:                   # constellation sparks
            d = rad * (0.4 + sp)
            x, y = c + d * math.cos(ang), c + d * math.sin(ang)
            pts.append((x, y))
            L.disc(x, y, 1.2, fade)
        V.lines(pts[:8], 0.35 * fade)
        L.glow(c, c, rad * 0.5 + 4, 1.2 * fade, 1.5)
        frames.append(over(V.result('violet', 1.0), L.result('cyan', 1.05)))
    return strip(frames)


# --- special / misc ----------------------------------------------------------------------
def sp_impact():
    W, H, N = 96, 96, 10
    c = 48
    frames = []
    cracks = [[(RNG.uniform(0, 2 * math.pi))] for _ in range(9)]
    for f in range(N):
        t = f / (N - 1)
        L = Light(W, H); R = Light(W, H)
        fade = max(0.0, 1 - t)
        L.glow(c, c, 10 + 34 * t, 1.6 * fade, 1.3)
        R.ellipse_ring(c, c, 8 + 40 * t, 8 + 40 * t, fade, 2.0)
        for (ang,) in cracks:                   # jagged red crack lightning
            pts = [(c, c)]; d = 0; a = ang
            while d < 10 + 38 * min(1, t * 2):
                d += 5; a += RNG.uniform(-0.5, 0.5)
                pts.append((c + d * math.cos(a), c + d * math.sin(a)))
            R.lines(pts, fade, 1.0)
        frames.append(over(R.result('red', 1.1), L.result('white', 1.0)))
    return strip(frames)


def sp_dash():
    W, H, N = 96, 80, 6
    frames = []
    for f in range(N):
        L = Light(W, H)
        for k in range(9):
            y = 18 + k * 6 + (k % 2) * 2
            x1 = 40 - (k * 13 + f * 9) % 30
            L.lines([(x1 - 34, y), (x1, y)], 0.8 - 0.05 * k)
        L.glow(46, 52, 16, 0.4)
        frames.append(L.result('white', 1.0))
    return strip(frames)


def aura():
    W, H, N = 80, 96, 8
    frames = []
    for f in range(N):
        t = f / N
        V = Light(W, H); L = Light(W, H)
        cx, base = 40, 78
        for k in range(11):                     # flame tongues rising around the body
            ph = k * 1.7 + t * 2 * math.pi
            x0 = cx + (k - 5) * 5.2
            h = 52 + 14 * math.sin(ph) + (6 if k in (4, 5, 6) else 0)
            pts = [(x0 - 4, base), (x0 + 3 * math.sin(ph), base - h * 0.55), (x0 + 5 * math.sin(ph + 1), base - h), (x0 + 4, base)]
            V.poly(pts, 0.5)
            L.lines([pts[1], pts[2]], 0.6)
        V.glow(cx, base - 30, 34, 0.4, 1.2)
        for k in range(7):                      # rising motes
            x = cx + 30 * math.sin(k * 2.3) ; y = base - ((k * 13 + t * 70) % 80)
            L.disc(x, y, 0.9, 1.0)
        frames.append(over(V.result('violet', 0.9), L.result('white', 1.0)))
    return strip(frames)


ALL = dict(s1_circle=s1_circle, s1_swarm=s1_swarm, s1_burst=s1_burst, s1_spark=lambda: spark('white'),
           s2_orb=s2_orb, s2_beam=s2_beam, s2_tip=s2_tip, s2_nova=s2_nova,
           sp_impact=sp_impact, sp_dash=sp_dash, aura=aura)

if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'out'
    os.makedirs(out, exist_ok=True)
    for n, fn in ALL.items():
        im = fn()
        im.save(os.path.join(out, f'jeff_{n}.png'))
        print(n, im.size)
