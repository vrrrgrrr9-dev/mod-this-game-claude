"""Grey's pose library (see skel.py for the conventions)."""
from skel import pose, joints, STANCE, L_THIGH, L_SHIN
import math


def grounded(p, ground=0.0):
    """moves the hip up/down so the lower foot rests on the ground."""
    q = dict(p); q['hy'] = 0.0
    j = joints(q)
    low = max(j['fb'][1], j['ff'][1])
    q['hy'] = ground - low
    return q


G = lambda **kw: grounded(pose(**kw))

STAND = G(tf=52, sf=96, tb=122, sb=100)
STAND2 = G(sp=-84, hd=-88, uf=58, lf=-36, ub=44, lb=-58, tf=54, sf=97, tb=120, sb=99)  # breathing
JAB = G(sp=-76, hd=-84, uf=-3, lf=-3, ub=46, lb=-62, tf=58, sf=98, tb=112, sb=100)
JAB_BACK = G(sp=-80, hd=-86, uf=40, lf=-60, ub=44, lb=-62, tf=64, sf=99, tb=108, sb=97)
CROSS = G(sp=-70, hd=-80, ub=-6, lb=-6, back_over=1, uf=80, lf=-95, tf=52, sf=96, tb=120, sb=104)
HOOK_WIND = G(sp=-88, hd=-90, uf=150, lf=-140, ub=50, lb=-60, tf=70, sf=100, tb=104, sb=95)
SLASH_WIND = G(sp=-95, hd=-95, uf=-130, lf=-150, ub=60, lb=-40, tf=72, sf=100, tb=104, sb=94, w=-160)
SLASH_END = G(sp=-72, hd=-80, uf=30, lf=40, ub=70, lb=-30, tf=55, sf=98, tb=118, sb=103, w=40)
CROUCH = G(sp=-70, hd=-80, uf=40, lf=-50, ub=50, lb=-60, tf=10, sf=120, tb=150, sb=75)
CROUCH_PALM = G(sp=-55, hd=-70, uf=80, lf=85, ub=60, lb=-40, tf=5, sf=118, tb=150, sb=72)
UPPER = G(sp=-98, hd=-96, uf=-58, lf=-78, ub=60, lb=-20, tf=80, sf=90, tb=95, sb=88)
KICK_CHAMBER = G(sp=-95, hd=-90, uf=70, lf=-30, ub=120, lb=60, tf=-10, sf=110, tb=96, sb=92)
KICK_OUT = G(sp=-118, hd=-104, uf=150, lf=170, ub=40, lb=10, tf=-18, sf=-14, tb=94, sb=91)
SWEEP = G(sp=-40, hd=-60, uf=100, lf=100, ub=70, lb=90, tf=5, sf=0, tb=150, sb=85)
RUN1 = dict(pose(sp=-64, hd=-72, uf=150, lf=200, ub=10, lb=-50, tf=25, sf=75, tb=150, sb=125), hy=-21)
RUN2 = dict(pose(sp=-64, hd=-72, uf=10, lf=-50, ub=150, lb=200, tf=150, sf=125, tb=25, sb=75), hy=-21)
TUCK = pose(hy=-30, sp=-80, hd=-84, uf=40, lf=-40, ub=50, lb=-50, tf=-20, sf=110, tb=-10, sb=100)
FALL = pose(hy=-30, sp=-92, hd=-92, uf=-120, lf=-150, ub=-60, lb=-30, tf=70, sf=110, tb=110, sb=80)
HURT = G(sp=-110, hd=-130, uf=160, lf=130, ub=200, lb=180, tf=80, sf=95, tb=110, sb=100)
FALLEN = pose(hy=-3, sp=180, hd=180, uf=150, lf=170, ub=200, lb=190, tf=5, sf=-10, tb=-5, sb=8)
DEFEND = G(sp=-78, hd=-84, uf=15, lf=-95, ub=35, lb=-75, back_over=1, tf=50, sf=100, tb=124, sb=100)
CHARGE = G(sp=-90, hd=-92, uf=120, lf=150, ub=60, lb=30, tf=60, sf=105, tb=120, sb=100)
SPEAR_THRUST = G(sp=-66, hd=-76, uf=-4, lf=-4, ub=-10, lb=-4, back_over=1, tf=48, sf=96, tb=124, sb=104, w=0)
POSE_COOL = G(sp=-88, hd=-78, uf=-8, lf=-14, ub=110, lb=60, tf=76, sf=96, tb=104, sb=92)

WALK1 = G(sp=-82, hd=-86, uf=50, lf=-40, ub=46, lb=-56, tf=62, sf=88, tb=118, sb=106)
WALK2 = G(sp=-84, hd=-88, uf=58, lf=-36, ub=40, lb=-60, tf=118, sf=106, tb=62, sb=88)
AIRDASH = dict(pose(sp=-30, hd=-40, uf=170, lf=180, ub=160, lb=190, tf=170, sf=160, tb=190, sb=170), hy=-30)

ALL = dict(WALK1=WALK1, WALK2=WALK2, AIRDASH=AIRDASH, STAND=STAND, STAND2=STAND2, JAB=JAB, CROSS=CROSS, HOOK_WIND=HOOK_WIND, SLASH_WIND=SLASH_WIND,
           SLASH_END=SLASH_END, CROUCH=CROUCH, CROUCH_PALM=CROUCH_PALM, UPPER=UPPER, KICK_CHAMBER=KICK_CHAMBER,
           KICK_OUT=KICK_OUT, SWEEP=SWEEP, RUN1=RUN1, RUN2=RUN2, TUCK=TUCK, FALL=FALL, HURT=HURT, FALLEN=FALLEN,
           DEFEND=DEFEND, CHARGE=CHARGE, SPEAR_THRUST=SPEAR_THRUST, POSE_COOL=POSE_COOL)
