"""Black Holing Scyther - every body animation, keyframed for the fight choreography.

Body frames do NOT contain the scythe: each frame records where the wing-hand grips (grip),
the scythe's angle there (wang, degrees clockwise from the haft pointing forward), whether it is
drawn behind the body (wl=1), hidden (wh=1, it was thrown) or mirrored (wf=1, spin frames facing
back).  The game draws weapon.py's sprite at that grip and can spin/tween it between frames.

  python anims.py <outdir>  ->  scyther_<anim>.png strips, frames.json (metadata), preview sheet
"""
import os, sys, json, math
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rig, weapon

W, H, OX, OY = rig.W, rig.H, rig.OX, rig.OY

def P(**kw):
    return kw


def planted(point, dx=0.0, dy=0.0):
    """grip for a weapon planted at a fixed frame point while the body moves by (dx, dy)."""
    return (point[0] - dx, point[1] - dy)


A = {}

# --------------------------------------------------------------------------------- locomotion
A['stand'] = []
for i in range(6):
    t = 2 * math.pi * i / 6
    A['stand'].append(P(crouch=0.7 + 0.7 * math.sin(t), neck=1.5 * math.sin(t), flow=1.5 + math.sin(t),
                        tail=2 * math.sin(t), grip=(15, -33 + 0.6 * math.sin(t)), wang=-62 + 2 * math.sin(t)))
A['walk'] = []
for i in range(8):
    t = 2 * math.pi * i / 8
    A['walk'].append(P(lean=4, crouch=1 - abs(math.sin(t)) * 1.5,
                       footF=(4 + 7 * math.cos(t), -max(0.0, math.sin(t)) * 4.5),
                       footB=(-7 - 7 * math.cos(t), -max(0.0, -math.sin(t)) * 4.5),
                       neck=2 * math.sin(2 * t), tail=3 * math.sin(t), flow=2 + math.sin(t),
                       grip=(15, -33 + math.sin(2 * t) * 0.8), wang=-60 + 4 * math.sin(t)))
A['run'] = []
for i in range(8):
    t = 2 * math.pi * i / 8
    A['run'].append(P(lean=20, crouch=2 - abs(math.sin(t)) * 2.5, neck=6, head=(1, 1, 4),
                      footF=(6 + 11 * math.cos(t), -max(0.0, math.sin(t)) * 8),
                      footB=(-6 - 11 * math.cos(t), -max(0.0, -math.sin(t)) * 8),
                      toeF=-20 * max(0.0, math.sin(t)), toeB=-20 * max(0.0, -math.sin(t)),
                      tail=-8 + 3 * math.sin(t), flow=7, beak=4,
                      grip=(9, -31), wang=166 + 3 * math.sin(t), wl=1))
A['jump'] = [P(lean=-6, footF=(8, -12), footB=(-4, -9), toeF=40, toeB=30, fwing='raise', grip=(12, -44), wang=-80, flow=3, beak=8),
             P(lean=-8, footF=(8, -14), footB=(-5, -11), toeF=46, toeB=36, fwing='raise', grip=(11, -46), wang=-86, flow=4, beak=8)]
A['fall'] = [P(lean=6, footF=(7, -3), footB=(-6, -2), toeF=20, fwing='raise', grip=(14, -44), wang=-36, flow=-2, tail=-6),
             P(lean=8, footF=(8, -2), footB=(-6, -1), toeF=24, fwing='raise', grip=(15, -45), wang=-30, flow=-3, tail=-8)]
A['crouch'] = [P(crouch=7, lean=10, footF=(8, 0), footB=(-10, 0), grip=(16, -27), wang=-40, flow=2)]
A['defend'] = [P(crouch=6, lean=-4, neck=4, footF=(9, 0), footB=(-11, 0), grip=(18, -36), wang=-88, flow=1),
               P(crouch=7, lean=-6, neck=5, footF=(9, 0), footB=(-11, 0), grip=(17, -35), wang=-86, flow=1)]
A['charge'] = [P(crouch=2, fwing='raise', grip=(6, -54), wang=2, beak=20, eye='glow', flow=4, tail=-4),
               P(crouch=3, fwing='raise', grip=(6, -55), wang=-2, beak=26, eye='glow', flow=6, tail=-6)]
A['hurt'] = [P(lean=-14, neck=-10, head=(-1, 0, -10), eye='shut', beak=12, grip=(10, -30), wang=-24, flow=-2, tail=8),
             P(lean=-18, neck=-14, head=(-2, 0, -14), eye='shut', beak=16, grip=(8, -29), wang=-14, flow=-4, tail=12)]
A['hurtup'] = [P(rot=-28, lean=-10, footF=(6, -8), footB=(-4, -6), toeF=30, eye='shut', beak=18, grip=(10, -34), wang=24, tail=14)]
A['hurtdown'] = [P(rot=-62, dy=-4, footF=(6, -6), footB=(-5, -4), eye='shut', beak=10, grip=(10, -34), wang=50, tail=20)]
A['fallen'] = [P(rot=-92, dx=-6, dy=26, footF=(5, -4), footB=(-5, -3), toeF=30, toeB=30, eye='x', beak=8,
                 grip=(10, -30), wang=8, tail=24, flow=-3)]
A['win'] = [P(fwing='raise', grip=(9, -52), wang=-98, beak=30, eye='glow', flow=4, neck=-6, head=(0, -1, -10)),
            P(fwing='raise', grip=(9, -53), wang=-100, beak=10, eye='angry', flow=5, neck=-4, head=(0, -1, -6))]

# --------------------------------------------------------------------------------- combo A
# A1 Rift Cleave - rising diagonal cut that splits a tear open along its path
A['a1'] = [P(crouch=5, lean=6, footF=(10, 0), footB=(-10, 0), grip=(13, -26), wang=48, beak=6, flow=2),
           P(crouch=2, lean=16, footF=(12, 0), footB=(-8, 0), grip=(19, -34), wang=-30, beak=24, eye='glow', flow=5),
           P(lean=14, footF=(12, 0), footB=(-8, 0), grip=(18, -42), wang=-105, beak=18, eye='glow', flow=6),
           P(lean=10, footF=(11, 0), footB=(-9, 0), grip=(16, -44), wang=-125, beak=8, flow=5),
           P(lean=6, grip=(15, -36), wang=-80, flow=3)]
# A2 Twin Crescent - steps in while twirling the double scythe (the game spins it 720 deg)
A['a2'] = [P(lean=8, footF=(9, 0), footB=(-9, 0), grip=(18, -35), wang=-60, beak=8),
           P(lean=12, footF=(14, -3), footB=(-6, 0), grip=(20, -35), wang=0, beak=22, eye='glow', flow=4),
           P(lean=12, footF=(12, 0), footB=(-3, -2), grip=(20, -35), wang=90, beak=22, eye='glow', flow=5),
           P(lean=6, footF=(10, 0), footB=(-8, 0), grip=(18, -32), wang=25, beak=6, flow=3)]
# A3 Orbit Reap - full body spin, the blades sweep in front AND behind (three hits)
A['a3'] = [P(crouch=4, lean=-4, grip=(11, -34), wang=170, wl=1, beak=6),
           P(lean=14, footF=(10, 0), footB=(-8, 0), grip=(20, -34), wang=8, beak=22, eye='glow', flow=6),
           P(lean=6, squash=0.55, grip=(10, -34), wang=60, flow=6),
           P(lean=10, mirror=True, grip=(19, -34), wang=8, wf=1, beak=22, flow=6),
           P(lean=6, mirror=True, squash=0.55, grip=(10, -34), wang=60, wf=1, flow=6),
           P(lean=16, footF=(11, 0), footB=(-8, 0), grip=(21, -33), wang=-10, beak=24, eye='glow', flow=7),
           P(lean=18, footF=(14, 0), footB=(-6, 0), grip=(21, -31), wang=30, beak=26, flow=7),
           P(lean=8, grip=(16, -33), wang=-50, flow=3)]
# A4 Event Horizon Cleave - leap, forward flip, both blades slam down: a giant tear with a galaxy inside
A['a4'] = [P(crouch=9, lean=14, footF=(8, 0), footB=(-11, 0), grip=(12, -24), wang=140, wl=1, eye='glow', beak=10, flow=3),
           P(lean=-8, footF=(8, -12), footB=(-5, -9), toeF=40, toeB=30, fwing='raise', grip=(8, -52), wang=-160, wl=1, beak=26, eye='glow', flow=4),
           P(rot=60, footF=(7, -11), footB=(-4, -9), toeF=40, grip=(12, -46), wang=-100, beak=20, flow=6),
           P(rot=175, footF=(7, -11), footB=(-4, -9), toeF=40, grip=(12, -46), wang=-60, beak=20, flow=6),
           P(rot=300, footF=(7, -11), footB=(-4, -9), toeF=40, grip=(12, -46), wang=-30, beak=24, flow=6),
           P(crouch=6, lean=24, neck=8, grip=(22, -26), wang=85, beak=30, eye='glow', flow=8, footF=(10, 0), footB=(-11, 0)),
           P(crouch=10, lean=20, neck=8, grip=(21, -20), wang=92, beak=20, eye='glow', flow=8, footF=(11, 0), footB=(-12, 0)),
           P(lean=6, grip=(16, -32), wang=-60, flow=3)]

# --------------------------------------------------------------------------------- combo B
# B1 Crescent Throw - hurls the spinning scythe like a buzzsaw boomerang, catches it
A['b1'] = [P(crouch=3, lean=-10, grip=(6, -38), wang=150, wl=1, beak=10),
           P(lean=18, footF=(11, 0), footB=(-8, 0), grip=(22, -36), wang=0, wh=1, beak=26, eye='glow', flow=5),
           P(lean=10, grip=(18, -36), wang=0, wh=1, beak=12, eye='glow', flow=3),
           P(lean=6, grip=(17, -38), wang=0, wh=1, beak=4, eye='angry', flow=2),
           P(lean=2, grip=(19, -40), wang=-40, beak=6, flow=2),
           P(lean=4, grip=(15, -34), wang=-62, flow=1)]
# B2 Spur Vault - plants the scythe, vaults on it, double spur kick, rips it up through a tear
PL = (24, -22)
A['b2'] = [P(crouch=4, lean=14, grip=PL, wang=80, beak=12, flow=3),
           P(dy=-14, lean=-12, footF=(12, -8), footB=(2, -10), toeF=-20, grip=planted(PL, 0, -14), wang=80, beak=16, flow=4),
           P(dy=-18, rot=-22, footF=(22, -16), footB=(0, -8), toeF=-50, grip=planted(PL, 0, -18), wang=80, beak=28, eye='glow', flow=6),
           P(dy=-16, rot=-16, footF=(8, -9), footB=(18, -18), toeB=-50, grip=planted(PL, 0, -16), wang=80, beak=28, eye='glow', flow=6),
           P(dy=-3, lean=16, grip=(20, -40), wang=-70, beak=20, eye='glow', flow=5),
           P(lean=6, grip=(16, -34), wang=-62, flow=2)]
# B3 Dimensional Stitch - a flurry of fast alternating cuts stitching a zigzag of small tears
A['b3'] = [P(lean=14, footF=(10, 0), footB=(-9, 0), grip=(20, -36), wang=-40, beak=20, eye='glow', flow=5),
           P(lean=16, footF=(10, 0), footB=(-9, 0), grip=(21, -32), wang=40, beak=26, eye='glow', flow=6),
           P(lean=12, footF=(10, 0), footB=(-9, 0), grip=(20, -38), wang=-50, beak=20, eye='glow', flow=5),
           P(lean=16, footF=(10, 0), footB=(-9, 0), grip=(21, -31), wang=50, beak=26, eye='glow', flow=6),
           P(lean=12, footF=(10, 0), footB=(-9, 0), grip=(20, -37), wang=-45, beak=20, eye='glow', flow=5),
           P(lean=8, grip=(16, -34), wang=-62, flow=2)]
# B4 Singular Rend - cuts a portal, steps into it, reappears behind the opponent and cleaves
A['b4'] = [P(lean=10, grip=(20, -42), wang=-95, beak=14, eye='glow', flow=3),
           P(lean=4, grip=(20, -28), wang=85, beak=20, eye='glow', flow=4),
           P(lean=20, footF=(14, 0), footB=(-4, -3), grip=(18, -34), wang=-30, beak=8, flow=4),
           P(lean=16, footF=(12, 0), footB=(-6, 0), grip=(17, -34), wang=-30, beak=8, flow=4),
           P(crouch=4, lean=-6, grip=(10, -36), wang=170, wl=1, eye='glow', beak=10, flow=3),
           P(lean=22, footF=(12, 0), footB=(-8, 0), grip=(22, -33), wang=10, beak=30, eye='glow', flow=8),
           P(lean=8, grip=(16, -34), wang=-50, flow=3)]

# --------------------------------------------------------------------------------- crouch / air
A['crouchatk'] = [P(crouch=8, lean=18, footF=(9, 0), footB=(-11, 0), grip=(12, -18), wang=170, wl=1, beak=8),
                  P(crouch=9, lean=22, footF=(10, 0), footB=(-11, 0), grip=(23, -16), wang=10, beak=18, eye='glow', flow=5),
                  P(crouch=7, lean=14, footF=(9, 0), footB=(-10, 0), grip=(20, -18), wang=-20, flow=3)]
A['airatk'] = [P(rot=10, footF=(10, -10), footB=(-2, -9), toeF=30, grip=(20, -36), wang=0, fwing='raise', beak=20, eye='glow', flow=5),
               P(rot=14, footF=(10, -10), footB=(-2, -9), toeF=30, grip=(20, -36), wang=90, fwing='raise', beak=24, eye='glow', flow=6),
               P(rot=6, footF=(9, -8), footB=(-3, -8), toeF=24, grip=(18, -34), wang=-40, flow=3)]

# --------------------------------------------------------------------------------- new moves
# Comet Thrust (combo A 3rd) - coils, then lunges like a comet, haft thrust forward through a ring burst
A['thrust'] = [P(crouch=7, lean=-6, footF=(10, 0), footB=(-12, 0), grip=(5, -30), wang=176, wl=1, beak=8, eye='glow', flow=2, tail=4),
               P(crouch=4, lean=28, neck=6, footF=(17, 0), footB=(-15, -2), toeB=-24, grip=(25, -32), wang=-2,
                 beak=30, eye='glow', flow=9, tail=-8),
               P(crouch=3, lean=24, neck=5, footF=(17, 0), footB=(-14, 0), grip=(26, -31), wang=6, beak=22, eye='glow', flow=8, tail=-6),
               P(lean=8, footF=(9, 0), footB=(-9, 0), grip=(16, -34), wang=-50, flow=3)]
# Phase Step (combo B 3rd) - blinks through the opponent three times, cutting from each side
A['phase'] = [P(crouch=8, lean=18, footF=(9, 0), footB=(-11, 0), grip=(12, -22), wang=160, wl=1, eye='glow', beak=6, flow=3),
              P(lean=14, footF=(12, 0), footB=(-8, 0), grip=(20, -42), wang=-120, beak=26, eye='glow', flow=6),
              P(crouch=5, lean=20, footF=(12, 0), footB=(-10, 0), grip=(22, -22), wang=62, beak=24, eye='glow', flow=7),
              P(lean=24, crouch=2, footF=(13, 0), footB=(-9, -2), grip=(22, -46), wang=-80, beak=30, eye='glow', flow=8,
                fwing='raise')]
# Rising Moon (down + attack B) - springs out of the crouch with a vertical crescent that launches
A['crouchb'] = [P(crouch=10, lean=16, footF=(9, 0), footB=(-11, 0), grip=(8, -14), wang=200, wl=1, eye='glow', beak=8, flow=3),
                P(lean=-6, footF=(10, -4), footB=(-6, 0), toeF=20, grip=(22, -46), wang=-100, beak=30, eye='glow', flow=7,
                  fwing='raise'),
                P(dy=-8, rot=-10, footF=(8, -10), footB=(-4, -8), toeF=30, toeB=24, grip=(15, -58), wang=-80, beak=26,
                  eye='glow', flow=7, fwing='raise'),
                P(lean=4, grip=(16, -36), wang=-60, flow=2)]
# Gravity Drop (air attack B) - flips the scythe under him and plunges straight down, blades first
A['airb'] = [P(rot=-8, footF=(8, -12), footB=(-4, -10), toeF=30, grip=(10, -16), wang=90, eye='glow', beak=12, flow=3,
               fwing='raise'),
             P(footF=(6, -7), footB=(-5, -7), toeF=60, toeB=60, grip=(12, -12), wang=90, beak=26, eye='glow', flow=-5,
               tail=-12, fwing='raise'),
             P(crouch=10, lean=20, neck=6, footF=(11, 0), footB=(-12, 0), grip=(18, -8), wang=95, beak=30, eye='glow', flow=8)]
# Meteor Dash (run + attack) - a low dash straight through the opponent, scythe dragged behind then swung
A['dashatk'] = [P(lean=32, crouch=6, neck=7, footF=(15, 0), footB=(-17, -2), toeB=-30, grip=(-3, -28), wang=170, wl=1,
                  beak=10, eye='glow', flow=9, tail=-10),
                P(lean=30, crouch=4, neck=6, footF=(17, 0), footB=(-15, -3), toeB=-24, grip=(24, -30), wang=20, beak=30,
                  eye='glow', flow=10, tail=-10),
                P(lean=20, footF=(14, 0), footB=(-12, 0), grip=(22, -40), wang=-70, beak=20, eye='glow', flow=8),
                P(crouch=6, lean=-8, footF=(16, 0), footB=(-8, 0), grip=(14, -34), wang=-60, beak=6, flow=2, tail=6)]
# Sky Splitter (air attack A, pressed again) - a diving diagonal cleave into the ground
A['airatk2'] = [P(rot=-20, footF=(8, -12), footB=(-4, -10), toeF=30, fwing='raise', grip=(4, -50), wang=-150, wl=1, beak=16,
                  eye='glow', flow=4),
                P(rot=30, footF=(10, -6), footB=(-6, -8), toeF=40, grip=(22, -24), wang=50, beak=30, eye='glow', flow=8),
                P(crouch=10, lean=22, neck=6, footF=(11, 0), footB=(-12, 0), grip=(20, -10), wang=80, beak=30, eye='glow', flow=8)]

# --------------------------------------------------------------------------------- skills
A['cast1'] = [P(crouch=2, fwing='raise', grip=(6, -54), wang=0, beak=10, eye='glow', flow=3),
              P(crouch=2, fwing='raise', grip=(8, -56), wang=90, beak=18, eye='glow', flow=4),
              P(crouch=2, fwing='raise', grip=(8, -56), wang=180, beak=18, eye='glow', flow=4),
              P(lean=14, footF=(10, 0), footB=(-9, 0), grip=(22, -40), wang=-10, beak=28, eye='glow', flow=5),
              P(lean=10, footF=(10, 0), footB=(-9, 0), grip=(21, -38), wang=-15, beak=12, eye='glow', flow=4)]
A['cast2'] = [P(lean=6, grip=(18, -46), wang=-90, beak=8, eye='glow', flow=2),
              P(lean=4, grip=(18, -26), wang=90, beak=16, eye='glow', flow=3),
              P(lean=12, footF=(10, 0), footB=(-9, 0), grip=(20, -36), wang=-2, eye='glow', beak=22, flow=4),
              P(lean=6, dx=-2, footF=(10, 0), footB=(-9, 0), grip=(18, -36), wang=-2, beak=26, eye='glow', flow=7),
              P(lean=4, grip=(16, -34), wang=-50, flow=2)]

# --------------------------------------------------------------------------------- the ultimate
A['sp'] = [P(crouch=3, fwing='raise', grip=(8, -54), wang=0, beak=24, eye='glow', flow=4),
           P(crouch=3, fwing='raise', grip=(8, -55), wang=90, beak=30, eye='glow', flow=6),
           P(lean=18, footF=(11, 0), footB=(-8, 0), grip=(22, -40), wang=-135, beak=30, eye='glow', flow=7),
           P(lean=18, footF=(11, 0), footB=(-8, 0), grip=(22, -30), wang=135, beak=30, eye='glow', flow=7),
           P(lean=10, grip=(22, -38), wang=-4, eye='glow', beak=10, flow=4),
           P(lean=0, grip=(10, -40), wang=-95, eye='angry', beak=0, flow=1)]

ANIM_ORDER = ['stand', 'walk', 'run', 'jump', 'fall', 'crouch', 'defend', 'charge', 'hurt', 'hurtup',
              'hurtdown', 'fallen', 'win', 'a1', 'a2', 'a3', 'a4', 'b1', 'b2', 'b3', 'b4', 'crouchatk',
              'airatk', 'thrust', 'phase', 'crouchb', 'airb', 'dashatk', 'airatk2', 'cast1', 'cast2', 'sp']
META_KEYS = ('wang', 'wl', 'wh', 'wf')


def render_frame(pose):
    """-> (2x body image, meta). meta: gx, gy = grip relative to the feet in 2x pixels; wang; flags."""
    pose = dict(pose)
    meta = {k: pose.pop(k, 0) for k in META_KEYS}
    im, g = rig.render(pose)
    if g is None:
        g = (OX + 14 * rig.K, OY - 40 * rig.K)
    meta['gx'] = int(round(g[0] - OX))
    meta['gy'] = int(round(g[1] - OY))
    meta['wang'] = int(round(meta['wang'])) % 360
    return im, meta


def composite(body, meta):
    """2x body frame + weapon at its grip (previews, select-screen sprite, cutscene)."""
    out = Image.new('RGBA', body.size, (0, 0, 0, 0))
    w = weapon.render(meta['wang'], held=True)
    if meta.get('wf'):
        w = w.transpose(Image.FLIP_LEFT_RIGHT)
    wx = int(OX + meta['gx'] - weapon.WS / 2); wy = int(OY + meta['gy'] - weapon.WS / 2)
    lay = Image.new('RGBA', body.size, (0, 0, 0, 0)); lay.paste(w, (wx, wy), w)
    if meta.get('wh'):
        out.alpha_composite(body)
    elif meta.get('wl'):
        out.alpha_composite(lay); out.alpha_composite(body)
    else:
        out.alpha_composite(body); out.alpha_composite(lay)
    return out


def to_1x(im):
    """2x -> 1x (premultiplied box filter, then crisp alpha) for 1x uses (select screen, cutscene)."""
    a = np.array(im).astype(np.float32)
    pm = a.copy(); pm[..., :3] *= a[..., 3:4] / 255
    h, w = a.shape[0] // 2, a.shape[1] // 2
    s = pm[:h * 2, :w * 2].reshape(h, 2, w, 2, 4).mean(axis=(1, 3))
    al = s[..., 3:4]
    rgb = np.where(al > 1, s[..., :3] / np.maximum(al / 255, 1e-3), 0)
    alpha = np.where(al[..., 0] >= 96, 255, 0)
    out = np.concatenate([np.clip(rgb, 0, 255), alpha[..., None]], axis=2)
    return Image.fromarray(out.astype(np.uint8), 'RGBA')


def hero_1x(pose):
    im, m = render_frame(pose)
    return to_1x(composite(im, m))


def strip(frames, w=None, h=None):
    w = w or frames[0].width; h = h or frames[0].height
    s = Image.new('RGBA', (w * len(frames), h), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        s.paste(f, (i * w, 0))
    return s


def build(out):
    """write every body strip (cropped per animation), the select-screen preview and
    scyther_frames.json (frame sizes, origins, per-frame weapon metadata)."""
    os.makedirs(out, exist_ok=True)
    info, comp_all = {}, {}
    for name in ANIM_ORDER:
        frames, metas = [], []
        for pose in A[name]:
            im, m = render_frame(pose)
            frames.append(im); metas.append(m)
        # union bounding box of the animation (+ margin), so 2x strips stay small
        box = None
        for f in frames:
            bb = f.getbbox()
            if bb:
                box = bb if box is None else (min(box[0], bb[0]), min(box[1], bb[1]), max(box[2], bb[2]), max(box[3], bb[3]))
        x0, y0, x1, y1 = box
        x0, y0 = max(0, x0 - 2), max(0, y0 - 2); x1, y1 = min(W, x1 + 2), min(H, y1 + 2)
        crops = [f.crop((x0, y0, x1, y1)) for f in frames]
        strip(crops).save(os.path.join(out, f'scyther_{name}.png'))
        info[name] = dict(w=x1 - x0, h=y1 - y0, ox=OX - x0, oy=OY - y0, meta=metas)
        comp_all[name] = [composite(f, m) for f, m in zip(frames, metas)]
    prev = [to_1x(composite(*render_frame(p))) for p in A['stand'][:4]]
    strip(prev).save(os.path.join(out, 'scyther_preview.png'))
    json.dump({'order': ANIM_ORDER, 'k': rig.K, 'anims': info, 'preview': dict(w=W // 2, h=H // 2, ox=OX // 2, oy=OY // 2)},
              open(os.path.join(out, 'scyther_frames.json'), 'w'))
    return comp_all


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'out'
    comp = build(out)
    Z = 1
    cols = max(len(v) for v in comp.values())
    sheet = Image.new('RGBA', (W * Z * cols + 20, (H * Z + 18) * len(comp)), (16, 11, 34, 255))
    d = ImageDraw.Draw(sheet)
    y = 2
    for n, fr in comp.items():
        d.text((4, y), n, fill=(210, 150, 255, 255))
        for i, f in enumerate(fr):
            x = 10 + i * W * Z
            d.line([(x, y + 14 + OY * Z), (x + W * Z - 6, y + 14 + OY * Z)], fill=(70, 50, 110, 255))
            sheet.alpha_composite(f, (x, y + 14))
        y += H * Z + 18
    sheet.save(os.path.join(out, 'preview_sheet.png'))
    print('rendered', len(comp), 'animations,', sum(len(v) for v in comp.values()), 'frames')
