"""Grey's choreography: every attack as an eased keyframe timeline plus timed events.

A timeline is played by the game for Grey himself and for each of his glitch clones (a clone is
the same stickman running a clone script at its own spot).  Positions are game px from the feet,
x forward (the facing direction), y down; rel='enemy' measures from the nearest opponent instead.
Keyframe 'mx' is root motion: how far forward the fighter has travelled since the move started.
"""
import json, math
from skel import pose, ANGLES, EASE
import poses as P

WEAPONS = {'none': 0, 'sword': 1, 'spear': 2, 'giant': 3}
COLORS = {'grey': 0, 'glitch': 1, 'ice': 2, 'fire': 3, 'volt': 4}
EVT = ['hit', 'clone', 'proj', 'spike', 'fx', 'snd', 'shake', 'tele', 'vel', 'glitch']
PROJ = {'fire': 0, 'shard': 1, 'spear': 2, 'spear_down': 3}
FX = {'glitch': 0, 'spark': 1, 'shock': 2, 'fireburst': 3, 'shatter': 4, 'arc': 5, 'ring': 6, 'bolt': 7,
      'pillar': 8, 'error': 9, 'spawn': 10}
SOUNDS = {  # game sounds (in memory) + our own (streamed, see grey.c)
    'woosh1': 465, 'woosh2': 466, 'woosh3': 467, 'strong1': 162, 'strong2': 163, 'magic': 203,
    'cast': 206, 'explode': 100, 'dark': 82, 'thunder': 177, 'impact': 464, 'charge': 266,
    'glitch': -1, 'clone': -2, 'ice': -3, 'crash': -4}


class TL:
    def __init__(self, name, dur, chain=-1):
        self.name, self.dur, self.chain = name, dur, chain
        self.keys, self.evts = [], []

    def k(self, t, p, e='inout', **kw):
        q = dict(p); q.update(kw)
        q.setdefault('wk', 'none'); q.setdefault('gh', 0); q.setdefault('back_over', 0); q.setdefault('mx', 0.0)
        self.keys.append((t, q, e))
        return self

    def ev(self, t, kind, **kw):
        self.evts.append(dict(t=t, kind=kind, **kw))
        return self

    def hit(self, t, dx, dy, size=32, xs=1.0, ys=1.0, dmg=1.0, hf=3.0, vf=-3.0, stun=14, knock=0, spr=1,
            col='grey', rel='self', snd=1):
        return self.ev(t, 'hit', dx=dx, dy=dy, size=size, xs=xs, ys=ys, dmg=dmg, hf=hf, vf=vf, stun=stun,
                       knock=knock, spr=spr, col=col, rel=rel, snd=snd)

    def clone(self, t, script, dx, dy=0, rel='self', face=1, tint='glitch'):
        return self.ev(t, 'clone', script=script, dx=dx, dy=dy, rel=rel, face=face, tint=tint)

    def proj(self, t, kind, dx, dy, vx, vy, dmg=0.4, rel='self'):
        return self.ev(t, 'proj', pk=kind, dx=dx, dy=dy, vx=vx, vy=vy, dmg=dmg, rel=rel)

    def spike(self, t, dx, rel='self', size=1.0, vf=-6.0, dmg=0.35):
        return self.ev(t, 'spike', dx=dx, rel=rel, size=size, vf=vf, dmg=dmg)

    def fx(self, t, kind, dx=0, dy=-30, sc=1.0, rel='self'):
        return self.ev(t, 'fx', fk=kind, dx=dx, dy=dy, sc=sc, rel=rel)

    def snd(self, t, name, pitch=1.0):
        return self.ev(t, 'snd', name=name, pitch=pitch)


def S(**kw): return P.grounded(pose(**kw))
def air(p, hy): return dict(p, hy=hy)


MOVES, CLONES = {}, {}
def move(tl): MOVES[tl.name] = tl; return tl
def clone_script(tl): CLONES[tl.name] = tl; return tl

ST = P.STAND
# ---------------------------------------------------------------------------------------------
# attack A: the glitch blade chain
# ---------------------------------------------------------------------------------------------
a1 = move(TL('A1', 18, chain=2))                           # glitch jab -> cross
a1.k(0, ST).k(3, P.JAB, 'expo', mx=6, gh=1).k(6, P.JAB_BACK, 'out', mx=7).k(9, P.CROSS, 'expo', mx=12, gh=1)
a1.k(18, ST, 'inout', mx=12)
a1.hit(3, 24, -36, 16, 1.2, 1.0, 0.8, 2, -2, 12).snd(2, 'woosh1', 1.2).fx(3, 'spark', 30, -36, 0.6)
a1.hit(9, 26, -36, 24, 1.2, 1.0, 1.0, 3, -2, 13).snd(8, 'woosh2', 1.1).fx(9, 'spark', 32, -36, 0.8)

a2 = move(TL('A2', 26, chain=3))                           # clone cut
SW_W = S(sp=-96, hd=-94, uf=-120, lf=-160, ub=60, lb=-40, tf=60, sf=98, tb=114, sb=98)
SW_E = S(sp=-70, hd=-80, uf=20, lf=35, ub=80, lb=-30, tf=48, sf=96, tb=124, sb=104)
a2.k(0, ST).k(4, SW_W, 'out', wk='sword', w=-150).k(9, SW_E, 'expo', wk='sword', w=30, mx=10, gh=1)
a2.k(16, SW_E, 'lin', wk='sword', w=36, mx=11).k(26, ST, 'inout', wk='none', mx=11)
a2.fx(3, 'glitch', 14, -40, 0.6).snd(3, 'glitch', 1.2)
a2.ev(7, 'fx', fk='arc', dx=18, dy=-36, sc=1.0, rel='self').snd(7, 'woosh3', 1.1)
a2.hit(9, 26, -34, 32, 1.4, 1.2, 1.0, 3, -2, 14, col='glitch')
a2.clone(6, 'CL_SLASH_BACK', 34, 0, rel='enemy', face=-1).snd(6, 'clone', 1.0)

a3 = move(TL('A3', 30, chain=4))                           # frost rise
a3.k(0, ST).k(5, P.CROUCH_PALM, 'out', mx=4).k(9, P.CROUCH_PALM, 'lin', mx=4)
a3.k(14, air(P.UPPER, -32), 'expo', mx=12, gh=1).k(20, air(P.UPPER, -30), 'out', mx=13).k(30, ST, 'inout', mx=13)
a3.snd(5, 'ice', 1.0).fx(6, 'shock', 16, -2, 0.6)
for i, dx in enumerate((22, 36, 50)):
    a3.spike(6 + 3 * i, dx, size=0.7 + 0.15 * i, vf=-5.0 - i)
a3.hit(14, 22, -44, 24, 1.2, 1.6, 1.2, 2, -9, 18, col='ice').snd(13, 'strong1', 1.1).fx(14, 'spark', 26, -48, 0.9)

a4 = move(TL('A4', 36, chain=5))                           # fireball backflip
TUCKF = dict(P.TUCK, uf=-10, lf=-20)
a4.k(0, ST).k(4, P.CROUCH, 'out').k(8, air(TUCKF, -40), 'out', rot=-90, mx=-6)
a4.k(14, air(TUCKF, -54), 'lin', rot=-200, mx=-12).k(20, air(TUCKF, -48), 'lin', rot=-300, mx=-16)
a4.k(26, air(P.TUCK, -30), 'in', rot=-360, mx=-18).k(29, P.CROUCH, 'out', rot=-360, mx=-18).k(36, ST, 'inout', rot=-360, mx=-18)
a4.snd(5, 'woosh2', 0.9)
a4.proj(11, 'fire', 10, -62, 5.5, 2.2, 0.45).snd(11, 'woosh3', 1.3).fx(11, 'fireburst', 10, -62, 0.35)
a4.proj(17, 'fire', 6, -58, 6.0, 1.6, 0.45).snd(17, 'woosh3', 1.2).fx(17, 'fireburst', 6, -58, 0.35)

a5 = move(TL('A5', 50))                                    # fatal glitch: three clones and him, spears in
a5.k(0, ST).k(3, ST, 'lin').k(7, P.SPEAR_THRUST, 'snap', wk='spear', w=0)
a5.k(11, dict(P.SPEAR_THRUST, uf=-140, lf=-150, ub=-150, lb=-160, w=180), 'out', wk='spear')
a5.k(15, P.SPEAR_THRUST, 'expo', wk='spear', w=0, mx=8, gh=1).k(30, P.SPEAR_THRUST, 'lin', wk='spear', w=0, mx=9)
a5.k(38, P.POSE_COOL, 'inout', wk='none', mx=9).k(50, ST, 'inout', mx=9)
a5.ev(2, 'glitch', n=6).snd(2, 'glitch', 0.9).ev(4, 'tele', mode='behind').fx(4, 'glitch', 0, -30, 1.2)
a5.clone(6, 'CL_SPEAR', -30, 0, rel='enemy', face=1).clone(7, 'CL_SPEAR_AIR', -16, -44, rel='enemy', face=1)
a5.clone(8, 'CL_SPEAR', 30, 0, rel='enemy', face=-1).snd(6, 'clone', 0.9)
a5.hit(15, 24, -34, 32, 1.4, 1.2, 0.8, 2, -2, 22, col='glitch')
a5.hit(19, 24, -34, 64, 1.6, 1.6, 1.6, 6, -8, 28, knock=1, spr=3, col='glitch', snd=2)
a5.fx(19, 'shatter', 24, -34, 1.2).fx(19, 'ring', 24, -1, 1.2).ev(19, 'shake', n=3).snd(19, 'strong2', 0.9).snd(19, 'glitch', 0.7)

# ---------------------------------------------------------------------------------------------
# attack B: kicks with clones, ice and fire
# ---------------------------------------------------------------------------------------------
b1 = move(TL('B1', 20, chain=51))                          # roundhouse
b1.k(0, ST).k(4, P.KICK_CHAMBER, 'out', mx=3).k(8, P.KICK_OUT, 'expo', mx=8, gh=1).k(12, P.KICK_OUT, 'lin', mx=8)
b1.k(20, ST, 'inout', mx=8)
b1.hit(8, 26, -36, 32, 1.3, 1.0, 1.0, 4, -3, 14).snd(7, 'woosh2', 1.0).fx(8, 'arc', 18, -38, 0.9)

b2 = move(TL('B2', 26, chain=52))                          # low sweep while a clone flies over with a kick
b2.k(0, ST).k(4, P.CROUCH, 'out').k(9, P.SWEEP, 'expo', mx=6, gh=1).k(16, P.SWEEP, 'lin', mx=6).k(26, ST, 'inout', mx=6)
b2.hit(9, 22, -6, 32, 1.4, 0.6, 0.9, 2, -2, 16, knock=1)
b2.clone(4, 'CL_FLYKICK', 0, 0, rel='self', face=1).snd(4, 'clone', 1.1).snd(8, 'woosh1', 0.9)

b3 = move(TL('B3', 34, chain=53))                          # ice lance, shattered by a spinning heel
STOMP_UP = S(sp=-92, hd=-90, uf=60, lf=-20, ub=100, lb=60, tf=-30, sf=80, tb=96, sb=92)
STOMP = S(sp=-80, hd=-84, uf=50, lf=-30, ub=80, lb=40, tf=60, sf=92, tb=110, sb=96)
SPIN_HEEL = dict(P.KICK_OUT, hy=-38)
b3.k(0, ST).k(4, STOMP_UP, 'out').k(7, STOMP, 'expo').k(12, P.CROUCH, 'inout', mx=4)
b3.k(16, air(P.TUCK, -36), 'out', rot=180, mx=10).k(20, SPIN_HEEL, 'expo', rot=360, mx=14, gh=1)
b3.k(25, SPIN_HEEL, 'lin', rot=360, mx=15).k(34, ST, 'inout', rot=360, mx=15)
b3.spike(7, 0, rel='enemy', size=1.6, vf=-5.5, dmg=0.5).snd(7, 'ice', 0.9).fx(7, 'shock', 10, -2, 0.7).ev(7, 'shake', n=2)
b3.hit(20, 26, -38, 32, 1.4, 1.2, 0.9, 4, -4, 16, col='ice').snd(19, 'woosh3', 1.1)
b3.fx(21, 'shatter', 0, -30, 1.0, rel='enemy').snd(21, 'ice', 1.3)                   # the heel shatters the lance
b3.hit(21, 0, -30, 32, 1.4, 1.4, 0.5, 3, -3, 14, col='ice', rel='enemy')
for i, (vx, vy) in enumerate(((7.5, -1.5), (6.8, 0.4), (6.0, -3.2), (7.2, 1.8), (5.5, -0.8))):
    b3.proj(21, 'shard', 4, -26 - 4 * i, vx, vy, 0.15, rel='enemy')

b4 = move(TL('B4', 44))                                    # meteor axe: jump, flip, burning heel
AXE_UP = dict(P.KICK_OUT, sp=-110, tf=-75, sf=-80, uf=160, lf=200, ub=20, lb=-20)
AXE_DOWN = S(sp=-70, hd=-80, tf=60, sf=95, tb=124, sb=104, uf=150, lf=190, ub=30, lb=10)
b4.k(0, ST).k(5, P.CROUCH, 'out').k(12, air(P.TUCK, -64), 'out', rot=180, mx=18).k(18, air(P.TUCK, -74), 'lin', rot=330, mx=28)
b4.k(22, air(AXE_UP, -66), 'out', rot=360, mx=34).k(27, dict(AXE_DOWN, rot=360), 'in', mx=40, gh=1)
b4.k(34, dict(AXE_DOWN, rot=360), 'lin', mx=40).k(44, dict(ST, rot=360), 'inout', mx=40)
b4.snd(5, 'woosh2', 0.8).fx(23, 'fireburst', 26, -70, 0.5).snd(23, 'woosh3', 0.8)
b4.hit(27, 22, -12, 64, 1.5, 1.2, 1.7, 5, -8, 26, knock=1, spr=3, col='fire', snd=2)
b4.fx(27, 'fireburst', 22, -14, 1.2).fx(27, 'ring', 22, -1, 1.3).ev(27, 'shake', n=3).snd(27, 'explode', 1.1)

# ---------------------------------------------------------------------------------------------
# crouch / air / run
# ---------------------------------------------------------------------------------------------
ca = move(TL('CA', 20))                                    # glitch blade sweep (trips)
CA_W = S(sp=-60, hd=-74, uf=150, lf=170, ub=60, lb=-40, tf=10, sf=120, tb=150, sb=74)
CA_E = S(sp=-50, hd=-66, uf=20, lf=10, ub=80, lb=-20, tf=5, sf=118, tb=152, sb=72)
ca.k(0, P.CROUCH).k(4, CA_W, 'out', wk='sword', w=170).k(8, CA_E, 'expo', wk='sword', w=8, mx=4, gh=1).k(20, P.CROUCH, 'inout', wk='none', mx=4)
ca.hit(8, 26, -8, 32, 1.5, 0.6, 0.9, 2, -2, 14, knock=1, col='glitch').snd(7, 'woosh1', 1.0).fx(3, 'glitch', 10, -20, 0.5)

cb = move(TL('CB', 24))                                    # frost slide
SLIDE = dict(pose(sp=-30, hd=-50, uf=200, lf=200, ub=150, lb=170, tf=2, sf=0, tb=40, sb=150), hy=-8)
cb.k(0, P.CROUCH).k(3, SLIDE, 'out', mx=8).k(12, SLIDE, 'lin', mx=56, gh=1).k(16, SLIDE, 'out', mx=60).k(24, P.CROUCH, 'inout', mx=60)
cb.hit(6, 20, -6, 32, 1.4, 0.6, 0.9, 3, -2, 14, knock=1, col='ice').snd(3, 'ice', 1.2)
for t in (4, 7, 10):
    cb.fx(t, 'shatter', -4, -4, 0.35)

aa = move(TL('AA', 22, chain=12))                          # aerial glitch spin (-> clone uplink -> data crash)
AIR_W = air(dict(P.TUCK, uf=-60, lf=-30), -36)
aa.k(0, air(P.FALL, -34)).k(3, AIR_W, 'out', wk='sword', w=-90).k(9, AIR_W, 'lin', wk='sword', rot=200, w=-90, gh=1)
aa.k(15, AIR_W, 'lin', wk='sword', rot=360, w=-90).k(22, air(P.FALL, -34), 'inout', wk='none', rot=360)
aa.hit(6, 16, -30, 32, 1.4, 1.4, 0.6, 2, 2, 12, col='glitch').hit(12, 16, -30, 32, 1.4, 1.4, 0.6, 3, 3, 12, col='glitch')
aa.snd(5, 'woosh1', 1.2).snd(11, 'woosh2', 1.2).fx(2, 'glitch', 10, -36, 0.5)
aa.ev(1, 'vel', hs=1.5, vs=-3.5)                           # a little lift, so the chain fits in a jump

aa2 = move(TL('AA2', 24, chain=13))                        # clone uplink: a rising knee, a clone launches him
KNEE = air(dict(P.KICK_CHAMBER, sp=-100, hd=-96, tf=-60, sf=60, tb=120, sb=100, uf=-40, lf=-80, ub=130, lb=80), -40)
aa2.k(0, air(P.FALL, -34)).k(4, air(P.TUCK, -36), 'out').k(8, KNEE, 'expo', gh=1).k(16, KNEE, 'lin').k(24, air(P.FALL, -34), 'inout')
aa2.ev(2, 'vel', hs=1.0, vs=-5.5).snd(6, 'woosh2', 1.3).ev(3, 'glitch', n=4)
aa2.hit(8, 14, -44, 24, 1.2, 1.3, 0.7, 2, -6, 14, col='glitch').fx(8, 'spark', 16, -46, 0.7)
aa2.clone(3, 'CL_UPLINK', -12, 0, rel='enemy', face=1).snd(3, 'clone', 1.2)

aa3 = move(TL('AA3', 40))                                  # data crash: a front flip, then down with the spear
CRASH_W = air(dict(P.TUCK, uf=-150, lf=-170, ub=-150, lb=-170), -40)
CRASH = air(dict(P.SPEAR_THRUST, sp=-40, hd=-50, uf=40, lf=45, ub=30, lb=40, back_over=1, tf=150, sf=170, tb=190, sb=200, w=60), -36)
aa3.k(0, air(P.FALL, -34)).k(4, CRASH_W, 'out', rot=180, wk='spear', w=-90).k(9, CRASH_W, 'lin', rot=360, wk='spear', w=-90)
aa3.k(12, CRASH, 'expo', rot=360, wk='spear', w=60, gh=1).k(34, CRASH, 'lin', rot=360, wk='spear', w=60, gh=1)
aa3.k(40, air(P.FALL, -34), 'inout', rot=360)
aa3.ev(1, 'vel', hs=0.5, vs=-3.0).ev(2, 'glitch', n=6).snd(2, 'glitch', 1.0)
aa3.ev(11, 'vel', hs=4.5, vs=10.0).snd(11, 'woosh3', 0.8).fx(11, 'spawn', 0, -30, 0.8)
aa3.hit(14, 22, -12, 32, 1.4, 1.4, 0.6, 3, 4, 16, col='glitch').hit(20, 22, -12, 32, 1.4, 1.4, 0.6, 3, 4, 16, col='glitch')

ab = move(TL('AB', 28))                                    # phantom dive kick with an echo
DIVE = air(dict(P.KICK_OUT, sp=-60, tf=40, sf=45, tb=150, sb=100, uf=-150, lf=-170, ub=200, lb=210), -32)
ab.k(0, air(P.TUCK, -34)).k(4, DIVE, 'out', gh=1).k(20, DIVE, 'lin', gh=1).k(28, air(P.FALL, -32), 'inout')
ab.ev(4, 'vel', hs=5.0, vs=7.0).snd(4, 'woosh3', 1.0)
ab.hit(8, 16, -14, 32, 1.3, 1.2, 1.0, 4, 4, 14, col='volt').hit(14, 16, -14, 32, 1.3, 1.2, 0.8, 4, 3, 14, col='volt')
ab.clone(7, 'CL_DIVE', -22, -26, rel='self', face=1).fx(8, 'bolt', 16, -14, 0.7)

rd = move(TL('RD', 28))                                    # glitch dash: through him, echoes cut behind
DASH = dict(pose(sp=-40, hd=-56, uf=170, lf=190, ub=160, lb=180, tf=60, sf=140, tb=160, sb=120, w=180), hy=-18)
rd.k(0, ST).k(2, DASH, 'out', wk='sword', w=180).k(10, DASH, 'lin', wk='sword', mx=88, gh=1, w=180)
rd.k(14, SW_E, 'expo', wk='sword', w=30, mx=92).k(28, ST, 'inout', wk='none', mx=92)
rd.ev(1, 'glitch', n=10).snd(2, 'glitch', 1.3).hit(6, 0, -32, 32, 1.4, 1.2, 0.8, 1, -2, 16, col='glitch')
for i, dx in enumerate((24, 48, 72)):
    rd.clone(4 + 2 * i, 'CL_GHOST_SLASH', dx, 0, rel='self', face=1 if i % 2 else -1)

# ---------------------------------------------------------------------------------------------
# skills
# ---------------------------------------------------------------------------------------------
s1 = move(TL('S1', 74))                                    # clone legion
CAST = S(sp=-96, hd=-98, uf=-60, lf=-90, ub=200, lb=160, tf=60, sf=100, tb=118, sb=98)
s1.k(0, ST).k(6, CAST, 'out').k(60, CAST, 'lin').k(74, ST, 'inout')
s1.ev(6, 'glitch', n=12).fx(6, 'error', 0, -70, 1.0).snd(6, 'clone', 0.8).snd(6, 'cast', 0.9)
s1.clone(9, 'CL_ICE', -40, 0, rel='enemy', face=1)
s1.clone(12, 'CL_FIRE', -70, 0, rel='enemy', face=1)
s1.clone(15, 'CL_SPEAR_SKY', 6, -86, rel='enemy', face=-1)
s1.clone(18, 'CL_VOLT', 60, 0, rel='enemy', face=-1)

s2 = move(TL('S2', 72))                                    # element overload: ice prison, fire pillar, spear rain
SLAM = S(sp=-48, hd=-62, uf=80, lf=88, ub=90, lb=95, back_over=1, tf=10, sf=120, tb=150, sb=74)
s2.k(0, ST).k(6, P.CHARGE, 'out').k(10, SLAM, 'expo').k(22, SLAM, 'lin').k(30, CAST, 'inout').k(62, CAST, 'lin').k(72, ST, 'inout')
s2.snd(10, 'ice', 0.8).ev(10, 'shake', n=2).fx(10, 'shock', 18, -2, 0.8)
for i, dx in enumerate((-30, 30, -18, 18, -6, 6)):
    s2.spike(12 + i, dx, rel='enemy', size=0.9 + 0.1 * (i // 2), vf=-1.5, dmg=0.2)
s2.ev(32, 'fx', fk='pillar', dx=0, dy=0, sc=1.0, rel='enemy').snd(32, 'explode', 0.9).snd(33, 'dark', 1.1)
for k in range(4):
    s2.hit(34 + 4 * k, 0, -30, 64, 1.0, 1.8, 0.3, 0, -3, 10, col='fire', rel='enemy')
for i, dx in enumerate((-18, 12, -6, 20, 0)):
    s2.proj(46 + 3 * i, 'spear_down', dx, -150, 0, 9.0, 0.3 if i < 4 else 0.6, rel='enemy')
s2.snd(46, 'glitch', 1.1)

# ---------------------------------------------------------------------------------------------
# clone scripts
# ---------------------------------------------------------------------------------------------
c = clone_script(TL('CL_SLASH_BACK', 22))
c.k(0, SW_W, wk='sword', w=-150).k(5, SW_W, 'lin', wk='sword', w=-150).k(9, SW_E, 'expo', wk='sword', w=30, mx=6).k(22, SW_E, 'lin', wk='sword', w=34, mx=7)
c.hit(9, 24, -34, 32, 1.4, 1.2, 0.9, 3, -3, 14, col='glitch').fx(8, 'arc', 16, -36, 0.9).snd(8, 'woosh2', 1.2)

c = clone_script(TL('CL_SPEAR', 26))
c.k(0, P.SPEAR_THRUST, wk='spear', w=0).k(6, dict(P.SPEAR_THRUST, uf=-140, lf=-150, ub=-150, lb=-160, w=180), 'out', wk='spear')
c.k(10, P.SPEAR_THRUST, 'expo', wk='spear', w=0, mx=8).k(26, P.SPEAR_THRUST, 'lin', wk='spear', w=0, mx=8)
c.hit(10, 22, -34, 24, 1.2, 1.2, 0.5, 1, -1, 18, col='glitch').fx(10, 'spark', 26, -34, 0.7)

c = clone_script(TL('CL_SPEAR_AIR', 26))
SPA = air(dict(P.SPEAR_THRUST, sp=-50, w=40, uf=36, lf=40, ub=30, lb=40, tf=150, sf=120, tb=200, sb=150), -36)
c.k(0, SPA, wk='spear').k(10, dict(SPA, hy=-30), 'expo', wk='spear', mx=8).k(26, dict(SPA, hy=-30), 'lin', wk='spear', mx=8)
c.hit(10, 20, -14, 24, 1.2, 1.2, 0.5, 1, 1, 18, col='glitch')

c = clone_script(TL('CL_FLYKICK', 24))
FLY = air(dict(P.KICK_OUT, sp=-80, tf=-5, sf=-5, tb=150, sb=130), -40)
c.k(0, air(P.TUCK, -30), gh=1).k(5, FLY, 'out', mx=40, gh=1).k(12, FLY, 'lin', mx=70, gh=1).k(24, air(P.FALL, -36), 'out', mx=82)
c.hit(8, 26, -46, 32, 1.4, 1.2, 1.0, 4, -5, 16, col='glitch').fx(8, 'spark', 30, -46, 0.8)

c = clone_script(TL('CL_DIVE', 20))
c.k(0, DIVE, gh=1).k(10, dict(DIVE, hy=-6), 'in', mx=30, gh=1).k(20, dict(DIVE, hy=-6), 'lin', mx=34)
c.hit(8, 18, -16, 32, 1.3, 1.2, 0.6, 4, 3, 12, col='volt').fx(9, 'bolt', 18, -14, 0.6)

c = clone_script(TL('CL_GHOST_SLASH', 18))
c.k(0, SW_W, wk='sword', w=-150).k(6, SW_W, 'lin', wk='sword', w=-150).k(10, SW_E, 'expo', wk='sword', w=30).k(18, SW_E, 'lin', wk='sword', w=30)
c.hit(10, 18, -34, 32, 1.2, 1.2, 0.4, 2, -2, 10, col='glitch').fx(9, 'arc', 12, -36, 0.7).snd(9, 'woosh1', 1.4)

c = clone_script(TL('CL_UPLINK', 24))                      # (air chain) a clone under him uppercuts him up
c.k(0, P.CROUCH, gh=1).k(5, P.CROUCH, 'lin').k(9, air(P.UPPER, -40), 'expo', gh=1).k(16, air(P.UPPER, -46), 'out').k(24, air(P.FALL, -40), 'inout')
c.hit(9, 14, -40, 32, 1.3, 1.6, 0.6, 1, -9, 18, col='volt').fx(9, 'bolt', 14, -40, 0.7).snd(8, 'woosh1', 1.3)

c = clone_script(TL('CL_WIN', 44))                         # (victory) back to back with him, pointing the other way
c.k(0, P.POSE_COOL).k(44, P.POSE_COOL, 'lin')

c = clone_script(TL('CL_ICE', 30))
c.k(0, STOMP_UP).k(8, STOMP_UP, 'lin').k(11, STOMP, 'expo').k(30, STOMP, 'lin')
c.spike(11, 40, size=1.3, vf=-6.5, dmg=0.45).fx(11, 'shock', 12, -2, 0.6).snd(11, 'ice', 1.0)

c = clone_script(TL('CL_FIRE', 34))
THROW_W = S(sp=-96, hd=-92, uf=-150, lf=-170, ub=40, lb=-40, tf=60, sf=98, tb=114, sb=98)
THROW = S(sp=-70, hd=-80, uf=-5, lf=-5, ub=70, lb=-20, tf=48, sf=96, tb=124, sb=104)
c.k(0, THROW_W).k(10, THROW_W, 'lin').k(13, THROW, 'expo').k(18, THROW_W, 'inout').k(21, THROW, 'expo').k(34, THROW, 'lin')
c.proj(13, 'fire', 22, -36, 6.5, 0, 0.4).proj(21, 'fire', 22, -36, 6.5, -0.4, 0.4).snd(13, 'woosh3', 1.2).snd(21, 'woosh3', 1.1)

c = clone_script(TL('CL_SPEAR_SKY', 36))
SKY = air(dict(P.SPEAR_THRUST, uf=-120, lf=-120, ub=-110, lb=-110, w=90, tf=80, sf=100, tb=110, sb=90), -10)
c.k(0, SKY, wk='spear', w=-90).k(14, SKY, 'lin', wk='spear', w=-90).k(18, dict(SKY, uf=60, lf=70, w=90), 'expo', wk='none').k(36, dict(SKY, uf=60, lf=70), 'lin')
c.proj(18, 'spear_down', 0, 0, 0, 10.0, 0.5).snd(17, 'woosh3', 0.9)

c = clone_script(TL('CL_VOLT', 34))
VOLT = dict(pose(sp=-40, hd=-56, uf=170, lf=190, ub=160, lb=180, tf=-5, sf=-5, tb=150, sb=120), hy=-30)
c.k(0, P.CROUCH).k(16, P.CROUCH, 'lin').k(20, VOLT, 'expo', mx=40, gh=1).k(26, VOLT, 'lin', mx=56, gh=1).k(34, air(P.FALL, -30), 'out', mx=60)
c.fx(14, 'bolt', 0, -60, 1.0).snd(16, 'thunder', 1.2)
c.hit(22, 0, -30, 64, 1.4, 1.2, 1.2, 6, -7, 24, knock=1, spr=3, col='volt', snd=2).fx(22, 'bolt', 6, -30, 1.0)


# ---------------------------------------------------------------------------------------------
# SYSTEM CRASH (special): clones dash through him from every side, then the giant blade
# ---------------------------------------------------------------------------------------------
c = clone_script(TL('CL_SC_STRIKE', 22))
c.k(0, P.CROUCH, wk='sword', w=170).k(5, P.CROUCH, 'lin', wk='sword', w=170).k(9, DASH, 'expo', wk='sword', w=180, mx=70, gh=1)
c.k(12, SW_E, 'out', wk='sword', w=30, mx=80).k(22, SW_E, 'lin', wk='sword', w=30, mx=82)
c.hit(8, 0, -32, 32, 1.2, 1.2, 0.35, 0, -1, 30, col='glitch').fx(8, 'arc', 0, -34, 1.0).snd(7, 'woosh1', 1.3)

fin = move(TL('SP_FINALE', 64))
GIANT_UP = air(dict(P.UPPER, uf=-95, lf=-95, ub=-85, lb=-85, back_over=1, w=-90), -96)
GIANT_DOWN = S(sp=-50, hd=-66, uf=60, lf=70, ub=50, lb=60, back_over=1, tf=10, sf=120, tb=150, sb=74, w=80)
fin.k(0, air(P.TUCK, -40), wk='giant', w=-90).k(10, GIANT_UP, 'out', wk='giant', w=-90).k(24, GIANT_UP, 'lin', wk='giant', w=-95)
fin.k(30, GIANT_DOWN, 'in', wk='giant', w=80, gh=1).k(44, GIANT_DOWN, 'lin', wk='giant', w=82).k(56, P.POSE_COOL, 'inout', wk='none').k(64, P.POSE_COOL, 'lin')
fin.snd(10, 'charge', 0.8).ev(12, 'glitch', n=20).snd(29, 'woosh3', 0.7)


# ---------------------------------------------------------------------------------------------
# not attacks: the victory and an idle flourish (played by grey.c as pose overrides, no hitboxes)
# ---------------------------------------------------------------------------------------------
win = move(TL('WIN', 100))                                 # a twirl of the glitch sword, a clone, the blade shatters
HOLD_UP = S(sp=-92, hd=-80, uf=-40, lf=-70, ub=110, lb=60, tf=60, sf=98, tb=114, sb=98)
TWIRL = S(sp=-90, hd=-84, uf=-6, lf=-10, ub=110, lb=60, tf=60, sf=98, tb=114, sb=98)
REST = S(sp=-86, hd=-80, uf=70, lf=40, ub=110, lb=60, tf=62, sf=98, tb=112, sb=98)
win.k(0, ST).k(8, HOLD_UP, 'out').k(12, TWIRL, 'out', wk='sword', w=-90)
spin = [30, 150, 270, 390, 510, 630, 750, 840, 910, 960]   # fast, then slowing (each step < 180 degrees)
for i, w in enumerate(spin):
    win.k(15 + 3 * i, TWIRL, 'lin', wk='sword', w=w)
win.k(50, REST, 'expo', wk='sword', w=1060).k(62, REST, 'lin', wk='sword', w=1062)
win.k(70, P.POSE_COOL, 'out', wk='sword', w=-14).k(72, P.POSE_COOL, 'lin', wk='none').k(100, P.POSE_COOL, 'lin')
win.fx(10, 'glitch', 12, -52, 0.5).snd(10, 'glitch', 1.3)
for t, pt in ((15, 1.1), (24, 1.2), (33, 1.3)):
    win.snd(t, 'woosh1', pt)
win.clone(56, 'CL_WIN', -14, 0, rel='self', face=-1).snd(56, 'clone', 1.1)
win.fx(71, 'shatter', 24, -44, 0.6).snd(71, 'glitch', 0.8)

idle = move(TL('IDLE', 52))                                # now and then at rest: the blade appears, spins, is dismissed
idle.k(0, ST).k(8, HOLD_UP, 'out').k(11, TWIRL, 'out', wk='sword', w=-90)
for i, w in enumerate((30, 150, 270, 390, 510, 600, 660)):
    idle.k(14 + 3 * i, TWIRL, 'lin', wk='sword', w=w)
idle.k(38, REST, 'expo', wk='sword', w=720).k(42, REST, 'lin', wk='none').k(52, ST, 'inout')
idle.fx(9, 'glitch', 12, -52, 0.4).snd(9, 'glitch', 1.5).fx(41, 'shatter', 14, -24, 0.45)


# ---------------------------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------------------------
def export_c():
    order = list(MOVES) + list(CLONES)
    kf, ev, tl = [], [], []
    for name in order:
        t = MOVES.get(name) or CLONES[name]
        k0, e0 = len(kf), len(ev)
        for (tt, p, e) in sorted(t.keys, key=lambda k: k[0]):
            flags = (1 if p.get('back_over') else 0) | (2 if p.get('gh') else 0) | (WEAPONS[p.get('wk', 'none')] << 2)
            kf.append([tt, EASE[e], flags, round(p['hx'] * 4), round(p['hy'] * 4), round(p.get('rot', 0)), round(p.get('mx', 0) * 4)]
                      + [round(p[a]) for a in ANGLES])
        for e in sorted(t.evts, key=lambda e: e['t']):
            kind = e['kind']; q = [0] * 10; fl = 0
            if kind == 'hit':
                q = [round(e['dx'] * 4), round(e['dy'] * 4), e['size'], round(e['xs'] * 100), round(e['ys'] * 100),
                     round(e['dmg'] * 100), round(e['hf'] * 10), round(e['vf'] * 10), e['stun'], COLORS[e['col']]]
                fl = (1 if e['knock'] else 0) | (2 if e['rel'] == 'enemy' else 0) | (e['spr'] << 2) | (e['snd'] << 5)
            elif kind == 'clone':
                q = [round(e['dx'] * 4), round(e['dy'] * 4), order.index(e['script']), e['face'], COLORS.get(e['tint'], 1)]
                fl = 2 if e['rel'] == 'enemy' else 0
            elif kind == 'proj':
                q = [round(e['dx'] * 4), round(e['dy'] * 4), PROJ[e['pk']], round(e['vx'] * 10), round(e['vy'] * 10), round(e['dmg'] * 100)]
                fl = 2 if e['rel'] == 'enemy' else 0
            elif kind == 'spike':
                q = [round(e['dx'] * 4), 0, round(e['size'] * 100), round(e['vf'] * 10), round(e['dmg'] * 100)]
                fl = 2 if e['rel'] == 'enemy' else 0
            elif kind == 'fx':
                q = [round(e['dx'] * 4), round(e['dy'] * 4), FX[e['fk']], round(e['sc'] * 100)]
                fl = 2 if e['rel'] == 'enemy' else 0
            elif kind == 'snd':
                q = [SOUNDS[e['name']], round(e['pitch'] * 100)]
            elif kind == 'shake':
                q = [e['n']]
            elif kind == 'tele':
                q = [{'behind': 0, 'front': 1}[e['mode']]]
            elif kind == 'vel':
                q = [round(e['hs'] * 10), round(e['vs'] * 10)]
            elif kind == 'glitch':
                q = [e['n']]
            ev.append([e['t'], EVT.index(kind), fl] + q)
        tl.append((name, k0, len(kf) - k0, e0, len(ev) - e0, t.dur, t.chain))
    out = ['/* generated by art/grey/moves.py - do not edit */', '#pragma once', '#include <stdint.h>', '']
    out.append('enum {'); out += [f'    GT_{n},' for n in order]; out.append('    GT_COUNT\n};')
    out.append(f'#define GT_FIRST_CLONE GT_{list(CLONES)[0]}')
    out.append('enum { ' + ', '.join(f'GE_{k.upper()}' for k in EVT) + ' };')
    out.append('enum { ' + ', '.join(f'GP_{k.upper()}' for k in PROJ) + ' };')
    out.append('enum { ' + ', '.join(f'GF_{k.upper()}' for k in FX) + ' };')
    out.append('enum { ' + ', '.join(f'GC_{k.upper()}' for k in COLORS) + ' };')
    out.append('enum { ' + ', '.join(f'GW_{k.upper()}' for k in WEAPONS) + ' };')
    out.append('enum { ' + ', '.join(f'GA_{a.upper()}' for a in ANGLES) + ', GA_N };')
    out.append('typedef struct { int16_t t; uint8_t ease, flags; int16_t hx, hy, rot, mx; int16_t a[%d]; } GKey;'
               '   /* hx, hy, mx in 1/4 px; angles in degrees; flags: 1 back arm over, 2 ghosts, weapon << 2 */' % len(ANGLES))
    out.append('typedef struct { int16_t t; uint8_t type, flags; int16_t p[10]; } GEvt;')
    out.append('typedef struct { int16_t key0, nkey, evt0, nevt, dur, chain; } GTimeline;')
    out.append(f'static const GKey k_gkeys[{len(kf)}] = {{')
    for r in kf:
        out.append('    {%d, %d, %d, %d, %d, %d, %d, {%s}},' % (r[0], r[1], r[2], r[3], r[4], r[5], r[6], ', '.join(map(str, r[7:]))))
    out.append('};')
    out.append(f'static const GEvt k_gevts[{max(1, len(ev))}] = {{')
    for r in ev:
        out.append('    {%d, %d, %d, {%s}},' % (r[0], r[1], r[2], ', '.join(map(str, r[3:]))))
    out.append('};')
    out.append('enum { ' + ', '.join(f'GPZ_{n}' for n in P.ALL) + ', GPZ_COUNT };')
    out.append('static const GKey k_gposes[GPZ_COUNT] = {')
    for n, p in P.ALL.items():
        q = dict(p); q.setdefault('mx', 0.0)
        flags = 1 if q.get('back_over') else 0
        out.append('    {0, 0, %d, %d, %d, %d, %d, {%s}},   /* %s */' % (flags, round(q['hx'] * 4), round(q['hy'] * 4), round(q.get('rot', 0)), 0,
                                                              ', '.join(str(round(q[a])) for a in ANGLES), n))
    out.append('};')
    out.append('static const GTimeline k_gtl[GT_COUNT] = {')
    for name, k0, nk, e0, ne, dur, chain in tl:
        out.append(f'    {{{k0}, {nk}, {e0}, {ne}, {dur}, {chain}}},   /* {name} */')
    out.append('};')
    from skel import L_SPINE, L_NECK, HEAD_R, L_UARM, L_FARM, L_THIGH, L_SHIN, SHOULDER_DROP, W_LIMB, W_TORSO, W_OUT
    for n, v in dict(L_SPINE=L_SPINE, L_NECK=L_NECK, HEAD_R=HEAD_R, L_UARM=L_UARM, L_FARM=L_FARM, L_THIGH=L_THIGH,
                     L_SHIN=L_SHIN, SHOULDER_DROP=SHOULDER_DROP, W_LIMB=W_LIMB, W_TORSO=W_TORSO, W_OUT=W_OUT).items():
        out.append(f'#define G_{n} {v:.2f}f')
    return '\n'.join(out) + '\n'


if __name__ == '__main__':
    import sys
    open(sys.argv[1], 'w').write(export_c())
    print('moves', len(MOVES), 'clone scripts', len(CLONES))
