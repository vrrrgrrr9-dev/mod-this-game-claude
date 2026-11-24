"""Animated preview of Jeff's kit (GIF), using the built assets and the same timings as src/jeff.c.

usage: python showcase.py <assets dir> <erbito sprites dir> <out.gif>
(the opponent dummy uses Erbito Black Rose sprites extracted from game.droid)
"""
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw

A, ERB, OUT = sys.argv[1:4]
W, H, Z = 384, 216, 2
GROUND = 176


def strip(name, frames, fw=None):
    im = Image.open(os.path.join(A, f'jeff_{name}.png')).convert('RGBA')
    fw = fw or im.width // frames
    return [im.crop((i * fw, 0, i * fw + fw, im.height)) for i in range(frames)]


S = {n: strip(n, f) for n, f in [('stand', 4), ('walk', 6), ('jab', 3), ('cross', 3), ('hook', 4), ('uppercut', 4),
                                    ('cast1', 4), ('cast2', 4), ('defend', 2), ('grab', 2), ('win', 2)]}
FX = {n: strip(n, f) for n, f in [('s1_circle', 16), ('s1_swarm', 12), ('s1_burst', 16), ('s2_orb', 8), ('s2_beam', 8),
                                     ('s2_tip', 8), ('s2_nova', 16), ('sp_impact', 10), ('sp_dash', 6), ('s1_spark', 8)]}
CUT = strip('cut_a', 12) + strip('cut_b', 12) + strip('cut_c', 12)
ORIG = {'s1_circle': (48, 16), 's1_swarm': (56, 40), 's1_burst': (64, 92), 's2_orb': (20, 20), 's2_beam': (0, 16),
        's2_tip': (24, 24), 's2_nova': (64, 64), 'sp_impact': (48, 48), 'sp_dash': (48, 40), 's1_spark': (8, 8)}
erb = {k: Image.open(os.path.join(ERB, f's_plr_erbitobkr_{k}.png')).convert('RGBA') for k in ('stand', 'hurt', 'fallen', 'defend')}


def background():
    a = np.zeros((H, W, 4), np.uint8)
    for y in range(H):
        k = y / H
        a[y, :, :3] = (int(40 + 60 * k), int(50 + 70 * k), int(90 + 80 * k))
    a[..., 3] = 255
    a[GROUND:, :, :3] = (58, 46, 40); a[GROUND:GROUND + 3, :, :3] = (110, 90, 70)
    im = Image.fromarray(a); d = ImageDraw.Draw(im)
    for x in range(0, W, 48):
        d.rectangle((x + 6, GROUND - 60, x + 30, GROUND), fill=(46, 58, 92, 255))
    return im


BG = background()


def put(img, spr, x, y, ox, oy, flip=False, add=False, alpha=1.0, sx=1.0):
    if flip:
        spr = spr.transpose(Image.FLIP_LEFT_RIGHT); ox = spr.width - ox
    if sx != 1.0:
        spr = spr.resize((max(1, int(spr.width * sx)), spr.height), Image.NEAREST); ox = int(ox * sx)
    px, py = int(round(x - ox)), int(round(y - oy))
    if add:
        a = np.array(img).astype(np.float32); s = np.array(spr).astype(np.float32)
        x0, y0 = max(0, px), max(0, py); x1, y1 = min(W, px + spr.width), min(H, py + spr.height)
        if x1 <= x0 or y1 <= y0: return img
        sub = s[y0 - py:y1 - py, x0 - px:x1 - px]
        a[y0:y1, x0:x1, :3] += sub[..., :3] * (sub[..., 3:4] / 255.0) * alpha
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    if alpha < 1:
        spr = spr.copy(); arr = np.array(spr); arr[..., 3] = (arr[..., 3] * alpha).astype(np.uint8); spr = Image.fromarray(arr)
    img.alpha_composite(spr, (px, py)) if 0 <= px and 0 <= py and px + spr.width <= W and py + spr.height <= H else img.paste(spr, (px, py), spr)
    return img


frames = []
def emit(img, label):
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 12), fill=(0, 0, 0, 255)); d.text((4, 1), label, fill=(255, 230, 90, 255))
    frames.append(img.resize((W * Z, H * Z), Image.NEAREST).convert('P', palette=Image.ADAPTIVE, colors=128))


EX = 250                       # enemy x
def enemy(img, state='stand', dx=0):
    return put(img, erb[state], EX + dx, GROUND, 32, 64 if state != 'fallen' else 59, flip=True)


t_global = 0
# 1. idle + walk in
jx = 120
for t in range(50):
    im = BG.copy(); im = enemy(im); im = put(im, S['stand'][int(t * 0.15) % 4], jx, GROUND, 48, 71)
    if t % 2 == 0: emit(im, 'Jeff - idle')
for t in range(70):
    jx += 1.0
    im = BG.copy(); im = enemy(im); im = put(im, S['walk'][int(t * 0.2) % 6], jx, GROUND, 48, 71)
    if t % 2 == 0: emit(im, 'walk')
# 2. combo: jab, cross, hook, uppercut
for name, dur, nf, hitf in (('jab', 12, 3, 1), ('cross', 13, 3, 1), ('hook', 15, 4, 2), ('uppercut', 24, 4, 2)):
    for t in range(dur):
        f = min(nf - 1, int(t * 0.3))
        im = BG.copy()
        hurt = f >= hitf
        im = enemy(im, 'hurt' if hurt else 'stand', 4 if hurt else 0)
        im = put(im, S[name][f], jx, GROUND, 48, 71)
        if f == hitf and t < dur * 0.7:
            im = put(im, FX['sp_impact'][min(9, t)], EX - 8, GROUND - 30, 48, 48, add=True, alpha=0.8)
        if t % 2 == 0: emit(im, f'combo 1 / combo 2:  {name.upper()}')
# 3. skill 1
sw = None; burst = None
for t in range(140):
    im = BG.copy(); im = enemy(im, 'hurt' if (sw and abs(sw[0] - EX) < 30) or burst else 'stand')
    if t < 42:
        im = put(im, FX['s1_circle'][(t // 2) % 16], jx, GROUND - 1, 48, 16, add=True, alpha=min(1, t / 8))
        f = 0 if t < 8 else 1 if t < 16 else 2 if t < 24 else 3
        im = put(im, S['cast1'][f], jx, GROUND, 48, 71)
    else:
        im = put(im, S['stand'][int(t * 0.15) % 4], jx, GROUND, 48, 71)
    if t == 16: sw = [jx + 22, GROUND - 6, 0]
    if sw:
        sw[2] += 1; sw[0] += 2.6 + (sw[2] * 0.12 if sw[2] < 24 else 2.9)
        for i in range(3, 0, -1):
            im = put(im, FX['s1_swarm'][(sw[2] // 2 + i) % 12], sw[0] - 10 * i, sw[1], 56, 40, add=True, alpha=0.45 / i)
        im = put(im, FX['s1_swarm'][(sw[2] // 2) % 12], sw[0], sw[1], 56, 40, add=True)
        if sw[2] >= 70 or sw[0] > EX + 10:
            burst = [sw[0], sw[1], 0]; sw = None
    if burst:
        burst[2] += 1
        im = put(im, FX['s1_burst'][min(15, burst[2] // 2)], burst[0], burst[1], 64, 92, add=True)
        if burst[2] > 32: burst = None
    if t % 2 == 0: emit(im, 'SKILL 1  Formic Arcana - runic ant swarm')
# 4. skill 2
beam = None; nova = None
for t in range(100):
    im = BG.copy(); im = enemy(im, 'hurt' if beam or nova else 'stand')
    f = 0 if t < 10 else 1 if t < 26 else 2 if t < 32 else 3
    im = put(im, S['cast2'][f] if t < 82 else S['stand'][0], jx, GROUND, 48, 71)
    sxp, syp = jx + 27, GROUND - 34
    if t < 30:
        k = min(1, t / 26)
        im = put(im, FX['s2_orb'][(t // 2) % 8].resize((int(40 * (0.4 + 0.9 * k)) or 1,) * 2, Image.NEAREST), sxp, syp,
                 int(20 * (0.4 + 0.9 * k)), int(20 * (0.4 + 0.9 * k)), add=True)
    if t == 26: beam = [0, 0.0]
    if beam:
        beam[0] += 1; beam[1] += (330 - beam[1]) * 0.35
        fade = 1.0 if beam[0] <= 44 else 1 - (beam[0] - 44) / 12
        L = int(beam[1])
        seg = FX['s2_beam'][(beam[0] // 2) % 8].resize((max(1, L), 32), Image.NEAREST)
        im = put(im, seg, sxp, syp, 0, 16, add=True, alpha=fade)
        im = put(im, FX['s2_tip'][(beam[0] // 2) % 8], sxp + L, syp, 24, 24, add=True, alpha=fade)
        if beam[0] == 44: nova = [sxp + min(L, EX - sxp + 10), syp, 0]
        if beam[0] >= 56: beam = None
    if nova:
        nova[2] += 1
        im = put(im, FX['s2_nova'][min(15, int(nova[2] / 2.25))], nova[0], nova[1], 64, 64, add=True)
        if nova[2] > 36: nova = None
    if t % 2 == 0: emit(im, 'SKILL 2 (down+skill)  Starlight Lance')
# 5. defend
for t in range(40):
    im = BG.copy(); im = enemy(im)
    im = put(im, S['defend'][(t // 4) % 2], jx, GROUND, 48, 71)
    if t % 2 == 0: emit(im, 'DEFEND - crouch + two-hand block')
# 6. special
x0 = jx
for t in range(14):
    im = BG.copy(); im = enemy(im)
    x = x0 + (EX - 26 - x0) * (t / 14)
    im = put(im, FX['sp_dash'][(t // 2) % 6], x, GROUND, 48, 40, add=True)
    im = put(im, S['grab'][0], x, GROUND, 48, 71)
    if t % 2 == 0: emit(im, 'SPECIAL (shield + skill)  Bone Breaker')
for c in range(1, 157):
    f = min(35, c * 36 // 156)
    im = Image.new('RGBA', (W, H), (0, 0, 0, 255))
    panel = CUT[f].resize((W, int(W * 180 / 320)), Image.NEAREST)
    im.paste(panel, (0, (H - panel.height) // 2))
    if (40 <= c < 44) or (62 <= c < 66) or (84 <= c < 88) or (106 <= c < 111):
        im = Image.blend(im, Image.new('RGBA', (W, H), (255, 240, 240, 255)), 0.5)
    if c % 3 == 0: emit(im, 'SPECIAL  Bone Breaker - cutscene')
for t in range(40):
    im = BG.copy(); im = enemy(im, 'fallen' if t > 6 else 'hurt', 40 + min(30, t * 3))
    im = put(im, S['win'][(t // 8) % 2] if t > 12 else S['uppercut'][2], EX - 26, GROUND, 48, 71)
    if t < 30: im = put(im, FX['sp_impact'][min(9, t // 3)], EX + 8, GROUND - 28, 48, 48, add=True)
    d = ImageDraw.Draw(im); d.text((EX - 20, 40), 'K.O.  (HP -> 0)', fill=(255, 220, 60, 255))
    if t % 2 == 0: emit(im, 'opponent HP set to 0')

frames[0].save(OUT, save_all=True, append_images=frames[1:], duration=33, loop=0, optimize=True)
print('frames', len(frames), '->', OUT, os.path.getsize(OUT) // 1024, 'KB')
