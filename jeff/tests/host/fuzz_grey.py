"""Randomized Grey fights on the host build (stand-in for the lost scratchpad fuzz.py).
usage: fuzz_grey.py <grey host .so> <frames> <seed>
Random presses of every input (attacks, skills, the special with a full bar, jumps, guard, getting hit /
knocked down / K.O.), opponent moving about; fails on bad sprite draws, NaN/huge draw coordinates, stub
errors, or a sanitizer trap (the process dies)."""
import os, random, sys
so, N, seed = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
sys.argv = [sys.argv[0], so, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shim.json')]
from hostemu import *
rng = random.Random(seed)
menu = new_inst(5); call('grey_load_assets', menu.ptr)
gc = new_inst(431)
for k, v in (('plr_team', 1), ('plr_dmg', 47), ('plr_energy', 100), ('plr_maxenergy', 100)): gc.set(k, v)
for k in ('key_defend', 'keyp_special', 'key_down', 'is_hurt', 'is_fallen', 'is_dead', 'is_onair', 'is_charging', 'is_running', 'plr_controller', 'keyp_action1'): gc.set(k, 0)
gr = new_inst(687); gr.set('x', 400); gr.set('y', 300); gr.set('image_xscale', 1); gr.set('image_alpha', 1)
call('gml_Object_o_grey_Create_0', gr.ptr, gr.ptr); gr.set('parent', gc.id)
call('gml_Object_o_grey_Alarm_0', gr.ptr, gr.ptr)
ec = new_inst(431); ec.set('plr_team', 2); ec.set('plr_hp', 1900); ec.set('is_dead', 0)
foe = new_inst(523); foe.set('x', 460); foe.set('y', 300); foe.set('parent', ec.id)
bad, specials, skills, dtap = [], 0, 0, 0
for f in range(N):
    r = rng.random()
    if gc.get('plr_energy') < 100 and rng.random() < 0.01: gc.set('plr_energy', 100)
    if r < 0.03: gr.set('combo_next', rng.choice((1, 50, 10, 60, 11, 61, 100, 110))); call('gml_Object_o_grey_Alarm_3', gr.ptr, gr.ptr); skills += 1
    elif r < 0.035: gc.set('key_defend', 1); gc.set('keyp_special', 1); specials += 1
    elif r < 0.04: dtap = 4                                     # double-tap shield: toggle the bow stance
    elif r < 0.05: gr.set('vspeed', -7); gr.set('y', 299); gc.set('is_onair', 1)
    elif r < 0.06: gc.set('is_hurt', 1)
    elif r < 0.065: gc.set('is_fallen', 1)
    elif r < 0.0655: gc.set('is_dead', 1)
    elif r < 0.07: gc.set('is_running', 1); gr.set('hspeed', rng.choice((-8, 8)))
    elif r < 0.12:
        for k in ('is_hurt', 'is_fallen', 'is_running', 'key_defend', 'keyp_special', 'is_dead'): gc.set(k, 0)
        gr.set('hspeed', 0)
    if dtap > 0: gc.set('key_defend', 1 if dtap in (4, 2) else 0); dtap -= 1
    if rng.random() < 0.02: foe.set('x', gr.get('x') + rng.uniform(-200, 200))
    if rng.random() < 0.003: ec.set('is_dead', 1 - (ec.get('is_dead') or 0))
    a2 = gr.arr.get(('alarm', 2), -1)
    if a2 is not None and a2 > 0:
        a2 -= 1; gr.arr[('alarm', 2)] = a2
        if a2 == 0:
            gr.arr[('alarm', 2)] = -1
            if rng.random() < 0.7: gr.set('combo_nextcombo', 1)
            call('gml_Object_o_grey_Alarm_2', gr.ptr, gr.ptr)
    calls.clear()
    call('gml_Object_o_grey_Step_0', gr.ptr, gr.ptr)
    gc.set('keyp_special', 0)
    x = gr.get('x') + (gr.get('hspeed') or 0); y = gr.get('y') + (gr.get('vspeed') or 0); vs = gr.get('vspeed') or 0
    if y < 300: vs += 0.45; gc.set('is_onair', 1)
    else: y = 300; vs = 0; gc.set('is_onair', 0)
    x = min(1400, max(-200, x)); gr.set('x', x); gr.set('y', y); gr.set('vspeed', vs)
    state['blend'] = 0
    call('gml_Object_o_grey_Draw_72', gr.ptr, gr.ptr); call('gml_Object_o_grey_Draw_0', gr.ptr, gr.ptr)
    call('gml_Object_o_grey_Draw_64', gr.ptr, gr.ptr)
    for c in calls:
        if c[0] in ('BAD_SPRITE_DRAW', 'BAD_FLOAT', 'UNSTUBBED') or c[0].startswith('PRIMITIVE'): bad.append((f, c))
    if len(bad) > 20: break
print(f'seed {seed}: {f + 1} frames, {skills} moves, {specials} special presses, {len(bad)} problems', bad[:5])
sys.exit(1 if bad else 0)
