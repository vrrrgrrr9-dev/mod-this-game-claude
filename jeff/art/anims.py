"""All of Jeff's body animations (pixel-art sprite strips) built from rig.py poses.

Run:  python anims.py <outdir>   -> writes jeff_<name>.png strips + preview sheet
Frame canvas is 96x72 with the origin (feet) at (48, 71) so punches have room; the
character itself is ~56px tall, the same scale as the game's 64x64 fighters.
"""
import os, sys, math
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rig
from rig import PIVOT

W, H, OX, OY = 96, 72, 48, 71
TRAIL = (235, 240, 255, 255)
TRAIL2 = (170, 190, 255, 255)

def F(x, y, r=46, b=36, *sh):
    return ('fist', x, y, r, b) + tuple(sh)

def S(dx=0, dy=0, a=0):
    return ('stub', dx, dy, a)

def pts_to_px(c, pts):
    return [rig.apply(c.world, p) for p in pts]

def speed_lines(y_list, x0, x1, color=TRAIL):
    def fx(c):
        im = Image.fromarray(c.img); d = ImageDraw.Draw(im)
        for y in y_list:
            a = rig.apply(c.world, (x0, y)); b = rig.apply(c.world, (x1, y))
            d.line([a, b], fill=color, width=1)
        c.img = np.array(im)
    return fx

def arc_trail(cx, cy, r, a0, a1, color=TRAIL, color2=TRAIL2, n=14):
    def fx(c):
        im = Image.fromarray(c.img); d = ImageDraw.Draw(im)
        for k, (rr, col) in enumerate(((r, color), (r - 28, color2))):
            P = [rig.apply(c.world, (cx + rr * math.cos(math.radians(a0 + (a1 - a0) * t / n)),
                                     cy + rr * math.sin(math.radians(a0 + (a1 - a0) * t / n)))) for t in range(n + 1)]
            d.line(P, fill=col, width=1)
        c.img = np.array(im)
    return fx

def impact_star(x, y, size=5, color=(255, 255, 255, 255)):
    def fx(c):
        im = Image.fromarray(c.img); d = ImageDraw.Draw(im)
        px, py = rig.apply(c.world, (x, y))
        for a in range(0, 360, 45):
            L = size if a % 90 == 0 else size * 0.6
            d.line([(px, py), (px + L * math.cos(math.radians(a)), py + L * math.sin(math.radians(a)))], fill=color, width=1)
        c.img = np.array(im)
    return fx

def both(*fs):
    def fx(c):
        for f in fs:
            f(c)
    return fx

STANCE = dict(footF=(24, 0, 0), footB=(-16, 0, 0))
ANIMS = {}

# --- locomotion -------------------------------------------------------------------------
ANIMS['stand'] = [dict(),
                  dict(sy=0.985, head=(0, 6, 1), tail=(0, 0, -3), armB=S(0, 4, 3), armF=S(0, 4, -3)),
                  dict(sy=0.97, head=(0, 14, 2), tail=(0, 0, -6), armB=S(0, 8, 5), armF=S(0, 8, -5)),
                  dict(sy=0.985, head=(0, 6, 1), tail=(0, 0, -3), armB=S(0, 4, 3), armF=S(0, 4, -3))]
walk = []
for i in range(6):
    t = i / 6 * 2 * math.pi
    walk.append(dict(dy=-abs(math.sin(t)) * 16, rot=2,
                     footF=(math.cos(t) * 40, -max(0, math.sin(t)) * 26, math.sin(t) * 10),
                     footB=(-math.cos(t) * 40, -max(0, -math.sin(t)) * 26, -math.sin(t) * 10),
                     armF=S(0, 0, -math.cos(t) * 22), armB=S(0, 0, math.cos(t) * 22),
                     tail=(0, 0, math.sin(t) * 6), head=(0, 0, math.sin(t * 2) * 2)))
ANIMS['walk'] = walk
run = []
for i in range(6):
    t = i / 6 * 2 * math.pi
    run.append(dict(dy=-abs(math.sin(t)) * 30 - 8, rot=10, dx=8,
                    footF=(math.cos(t) * 70 + 10, -max(0, math.sin(t)) * 44, math.sin(t) * 20),
                    footB=(-math.cos(t) * 70 - 10, -max(0, -math.sin(t)) * 44, -math.sin(t) * 20),
                    armF=S(0, 0, -math.cos(t) * 45 - 10), armB=S(0, 0, math.cos(t) * 45 + 10),
                    tail=(0, 0, -14 + math.sin(t) * 8), head=(8, 0, 4)))
ANIMS['run'] = run
ANIMS['jump'] = [dict(dy=-10, footF=(16, -50, 25), footB=(-10, -40, -20), armF=S(0, -10, -70), armB=S(0, -10, 70), tail=(0, 0, 12), head=(0, -6, -4)),
                 dict(dy=-14, footF=(18, -58, 30), footB=(-12, -48, -24), armF=S(0, -14, -85), armB=S(0, -14, 85), tail=(0, 0, 16), head=(0, -8, -6))]
ANIMS['fall'] = [dict(footF=(10, -6, 10), footB=(-8, -2, -8), armF=S(0, -20, -120), armB=S(0, -20, 120), tail=(0, 0, 20), head=(0, 0, 3)),
                 dict(footF=(12, -2, 14), footB=(-10, 0, -12), armF=S(0, -24, -135), armB=S(0, -24, 135), tail=(0, 0, 24), head=(0, 0, 5))]
ANIMS['crouch'] = [dict(sy=0.78, footF=(30, 0, 0), footB=(-24, 0, 0), armF=S(0, 0, -20), armB=S(0, 0, 20), tail=(0, 0, -10))]
# crouching guard: both hands up in front of the face (user spec)
guard = dict(sy=0.8, footF=(34, 0, 0), footB=(-26, 0, 0), tail=(0, 0, -12), head=(-14, 10, 8), eyes='angry',
             armF=F(800, 735, 54, 34, 40, 0), armB=F(745, 770, 54, 34, 230, 10), front_arm_over=True, back_arm_over=True)
ANIMS['defend'] = [guard, dict(guard, dx=-8, armF=F(796, 740, 54, 34, 40, 0), armB=F(741, 775, 54, 34, 230, 10))]
ANIMS['charge'] = [dict(sy=0.92, footF=(40, 0, 0), footB=(-34, 0, 0), armF=F(700, 1010, 44, 34), armB=F(372, 1010, 44, 34), head=(0, 10, 8), eyes='angry', tail=(0, 0, 10)),
                   dict(sy=0.9, dy=-4, footF=(42, 0, 0), footB=(-36, 0, 0), armF=F(706, 1016, 44, 34), armB=F(366, 1016, 44, 34), head=(0, 12, 8), eyes='angry', tail=(0, 0, 14))]
ANIMS['hurt'] = [dict(rot=-8, dx=-10, head=(-10, 0, -16), eyes='squint', armF=S(0, 0, -50), armB=S(0, 0, 40), tail=(0, 0, 14), footF=(10, 0, 8)),
                 dict(rot=-12, dx=-14, head=(-14, 0, -22), eyes='squint', armF=S(0, -6, -70), armB=S(0, -6, 55), tail=(0, 0, 20), footF=(12, -4, 12))]
ANIMS['hurtup'] = [dict(rot=-28, dy=-20, head=(0, 0, -20), eyes='x', armF=S(0, 0, -110), armB=S(0, 0, 100), footF=(10, -20, 30), footB=(-10, -10, -20), tail=(0, 0, 30))]
ANIMS['hurtdown'] = [dict(rot=-62, dy=-130, dx=300, head=(0, 0, -15), eyes='x', armF=S(0, 0, -100), armB=S(0, 0, 80), footF=(10, -10, 20), tail=(0, 0, 30))]
ANIMS['fallen'] = [dict(rot=-90, dx=430, dy=-330, head=(0, 0, -6), eyes='x', armF=S(0, 0, -30), armB=S(0, 0, 20), tail=(0, 0, 60), footF=(0, 0, 20))]

# --- jab, cross, hook, uppercut (used by combo 1 AND combo 2) ---------------------------
lean = dict(STANCE, rot=4, head=(10, 0, 3), eyes='angry')
ANIMS['jab'] = [dict(lean, armF=F(700, 900, 44, 34), front_arm_over=True),
                dict(lean, rot=7, dx=10, head=(18, 0, 4), armF=F(930, 872, 50, 34), front_arm_over=True,
                     fx=both(speed_lines((850, 900), 640, 780), impact_star(990, 872, 4))),
                dict(lean, rot=5, armF=F(800, 885, 46, 34), front_arm_over=True)]
ANIMS['cross'] = [dict(lean, rot=2, dx=-6, armB=F(470, 880, 44, 34), armF=F(720, 820, 44, 34), front_arm_over=True),
                  dict(lean, rot=10, dx=26, head=(22, 4, 6), footB=(10, -4, -18),
                       armB=F(960, 862, 52, 36, 200, -10), armF=F(700, 950, 42, 32), back_arm_over=True,
                       fx=both(speed_lines((830, 880, 910), 560, 760), impact_star(1024, 862, 5))),
                  dict(lean, rot=6, dx=12, armB=F(820, 880, 46, 34, 200, 0), back_arm_over=True)]
ANIMS['hook'] = [dict(lean, rot=-2, dx=-8, armF=F(600, 820, 46, 34), front_arm_over=False, armB=F(690, 900, 42, 32), back_arm_over=True),
                 dict(lean, rot=6, dx=6, head=(14, 0, 5), armF=F(800, 730, 48, 34), front_arm_over=True,
                      fx=arc_trail(760, 880, 150, -150, -70)),
                 dict(lean, rot=10, dx=20, head=(22, 0, 7), armF=F(930, 820, 52, 36), front_arm_over=True,
                      fx=both(arc_trail(800, 900, 150, -110, -20), impact_star(990, 820, 5))),
                 dict(lean, rot=4, dx=8, armF=F(770, 880, 46, 34), front_arm_over=True)]
ANIMS['uppercut'] = [dict(lean, sy=0.86, dx=-4, rot=0, armB=F(600, 1040, 46, 34, 120, 0), back_arm_over=True, footF=(30, 0, 0), footB=(-24, 0, 0)),
                     dict(lean, sy=1.03, dy=-20, rot=6, head=(10, -6, -4), armB=F(800, 800, 50, 36, 200, 0), back_arm_over=True,
                          footB=(-10, -10, -20), fx=arc_trail(700, 900, 150, 80, -20)),
                     dict(lean, sy=1.06, dy=-70, rot=-4, head=(4, -10, -12), armB=F(790, 520, 54, 36, 220, -20), back_arm_over=True,
                          footF=(26, -20, 20), footB=(-16, -26, -20), tail=(0, 0, 18),
                          fx=both(arc_trail(640, 800, 190, 40, -70), impact_star(790, 470, 6))),
                     dict(lean, dy=-30, armB=F(700, 760, 46, 34, 200, 0), back_arm_over=True, footF=(20, -8, 10), footB=(-14, -10, -10))]
ANIMS['airpunch'] = [dict(dy=-10, rot=12, footF=(20, -40, 30), footB=(-14, -46, -10), head=(12, 0, 8), eyes='angry',
                          armF=F(880, 1000, 50, 34), front_arm_over=True, armB=S(0, 0, 60), tail=(0, 0, 20),
                          fx=speed_lines((960, 1000), 640, 800)),
                     dict(dy=-10, rot=8, footF=(20, -36, 24), footB=(-14, -40, -10), head=(8, 0, 6), eyes='angry',
                          armF=F(800, 960, 46, 34), front_arm_over=True, armB=S(0, 0, 50), tail=(0, 0, 16))]
ANIMS['crouchpunch'] = [dict(sy=0.8, footF=(34, 0, 0), footB=(-24, 0, 0), eyes='angry', armF=F(720, 1000, 44, 34), front_arm_over=True),
                        dict(sy=0.8, footF=(40, 0, 0), footB=(-24, 0, 0), eyes='angry', dx=10, rot=4,
                             armF=F(940, 1010, 50, 34), front_arm_over=True, fx=both(speed_lines((1000, 1030), 640, 800), impact_star(1000, 1010, 4)))]

# --- magic casting poses (effects are separate sprites drawn by the game code) -----------
ANIMS['cast1'] = [dict(STANCE, sy=0.94, armF=F(600, 990, 44, 34), armB=F(450, 990, 44, 34), head=(0, 8, 6), eyes='angry'),
                  dict(STANCE, armF=F(700, 760, 46, 34), armB=F(660, 780, 46, 34), front_arm_over=True, back_arm_over=True, head=(0, 0, -6), eyes='angry'),
                  dict(STANCE, rot=6, dx=10, armF=F(900, 860, 50, 36), armB=F(880, 900, 50, 36), front_arm_over=True, back_arm_over=True, head=(12, 0, 4), eyes='angry'),
                  dict(STANCE, rot=8, dx=14, armF=F(910, 856, 52, 36), armB=F(890, 904, 52, 36), front_arm_over=True, back_arm_over=True, head=(14, 0, 4), eyes='angry')]
ANIMS['cast2'] = [dict(STANCE, rot=-6, head=(-10, 0, -24), armF=S(0, 0, 40), armB=S(0, 0, -30), eyes='angry', tail=(0, 0, 12)),
                  dict(STANCE, rot=-10, head=(-16, -6, -34), armF=S(0, -6, 60), armB=S(0, -6, -45), eyes='angry', tail=(0, 0, 18)),
                  dict(STANCE, rot=8, dx=16, head=(20, 0, 8), armF=S(0, 0, -30), armB=S(0, 0, 40), eyes='angry', tail=(0, 0, -10)),
                  dict(STANCE, rot=10, dx=20, head=(24, 0, 10), armF=S(0, 0, -36), armB=S(0, 0, 44), eyes='angry', tail=(0, 0, -14))]
# special: dash + grab
ANIMS['grab'] = [dict(rot=14, dx=20, dy=-6, footF=(60, -20, 20), footB=(-60, -10, -20), armF=F(900, 880, 48, 34), armB=F(870, 940, 48, 34),
                      front_arm_over=True, back_arm_over=True, head=(16, 0, 8), eyes='angry', tail=(0, 0, -20),
                      fx=speed_lines((860, 940, 1020), 120, 320)),
                 dict(STANCE, rot=4, dx=24, armF=F(860, 860, 50, 36), armB=F(850, 930, 50, 36), front_arm_over=True, back_arm_over=True,
                      head=(16, 0, 4), eyes='angry')]
ANIMS['win'] = [dict(armF=F(905, 700, 48, 34), front_arm_over=True, head=(0, 0, -8), tail=(0, 0, 10)),
                dict(dy=-12, armF=F(915, 650, 48, 34), front_arm_over=True, head=(0, -4, -10), tail=(0, 0, 14))]

def render_anim(name):
    frames = []
    for pose in ANIMS[name]:
        pose = dict(pose); fx = pose.pop('fx', None)
        frames.append(rig.render(pose, W, H, OX, OY, fx=fx))
    return frames

def strip(frames):
    s = Image.new('RGBA', (W * len(frames), H), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        s.paste(f, (i * W, 0))
    return s

if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'out'
    os.makedirs(out, exist_ok=True)
    allf = {}
    for n in ANIMS:
        fr = render_anim(n); allf[n] = fr
        strip(fr).save(os.path.join(out, f'jeff_{n}.png'))
    # preview sheet x3 on a dark backdrop with a ground line
    Z = 3; rows = []
    sheet = Image.new('RGBA', (W * Z * 6 + 20, (H * Z + 26) * len(allf)), (52, 60, 80, 255))
    d = ImageDraw.Draw(sheet)
    y = 4
    for n, fr in allf.items():
        d.text((6, y), n, fill=(255, 230, 80, 255))
        for i, f in enumerate(fr[:6]):
            x = 10 + i * W * Z
            d.line([(x, y + 14 + OY * Z), (x + W * Z - 8, y + 14 + OY * Z)], fill=(90, 100, 120, 255))
            sheet.alpha_composite(f.resize((W * Z, H * Z), Image.NEAREST), (x, y + 14))
        y += H * Z + 26
    sheet.save(os.path.join(out, 'preview_sheet.png'))
    print('rendered', len(allf), 'animations')
