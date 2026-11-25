"""Single source of truth for Jeff's runtime assets (loaded with sprite_add / audio_create_stream).

Each sprite is a horizontal strip PNG in the APK's assets/ folder. Order matters: the C code
uses the generated enum (gen/jeff_assets.h) as an index into the loaded-sprite table.  Body
animations come with a per-frame table of where his fists / kicking foot are and which of them
burn (the game draws the dark flame there).
"""
import json, os

FLAME = [('jf_fist', 8, 34, 30), ('jf_trail', 6, 92, 16), ('jf_burst', 10, 56, 56), ('jf_arc', 6, 52, 70),
         ('jf_meteor', 8, 56, 20), ('jf_crater', 12, 64, 100), ('jf_portal', 8, 56, 28), ('jf_bh', 8, 32, 32),
         ('jf_bhring_b', 8, 88, 48), ('jf_bhring_f', 8, 88, 48), ('jf_aura', 8, 48, 104), ('jf_rock', 8, 8, 8),
         ('jf_glow', 1, 32, 32)]
SUN = [('js_sword', 6, 6, 10), ('js_shield', 8, 20, 20), ('js_fist', 8, 34, 30), ('js_trail', 6, 92, 16), ('js_burst', 10, 56, 56),
       ('js_arc', 6, 52, 70), ('js_aura', 8, 48, 104), ('js_wave', 8, 14, 36), ('js_swirl', 12, 48, 104), ('js_glow', 1, 32, 32),
       ('rbh_core', 8, 48, 48), ('rbh_disk_b', 8, 88, 48), ('rbh_disk_f', 8, 88, 48), ('hp_orb_b', 8, 24, 24), ('hp_orb_r', 8, 24, 24),
       ('hp_orb_p', 8, 32, 32), ('hp_nuke', 12, 80, 130), ('cin_ring', 8, 80, 28), ('cin_bg', 2, 0, 0), ('jd_glow', 1, 12, 12)]
SPECIAL = [('sp_impact', 10, 48, 48), ('sp_dash', 6, 48, 40), ('cut_a', 12, 0, 0), ('cut_b', 12, 0, 0), ('cut_c', 12, 0, 0)]

# custom sounds (file = jeff_<name>.ogg); the rest of Jeff's audio reuses the game's own sounds
SOUNDS = ['crack1', 'crack2', 'crack3', 'ko', 'flame', 'meteor', 'hole', 'power', 'nuke']

CUT_W, CUT_H = 320, 180     # cutscene panel size (scaled up to the GUI layer in game)


def sprites(assets):
    """[(name, frames, ox, oy, half)] in enum order."""
    fj = json.load(open(os.path.join(assets, 'jeff_frames.json')))
    out = [(n, a['n'], a['ox'], a['oy'], 0) for n, a in ((n, fj['anims'][n]) for n in fj['order'])]
    pv = fj['preview']
    out.append(('preview', pv['n'], pv['ox'], pv['oy'], 0))
    out.append(('face', 1, 0, 0, 0))
    out.append(('face_d', 1, 0, 0, 0))
    out += [(n, f, ox, oy, 0) for n, f, ox, oy in FLAME + SUN + SPECIAL]
    # the red-power form: a black copy of every body animation, same order (A_DARK0 + body index)
    out += [('d_' + n, fj['anims'][n]['n'], fj['anims'][n]['ox'], fj['anims'][n]['oy'], 0) for n in fj['order']]
    return out


def header(assets):
    """C header with the asset enums, a pointer-free table (no relocations) and the frame table."""
    fj = json.load(open(os.path.join(assets, 'jeff_frames.json')))
    sp = sprites(assets)
    out = ['/* generated from art/manifest.py - do not edit */', '#pragma once', '#include <stdint.h>', '']
    out.append('enum {')
    for n, *_ in sp:
        out.append(f'    A_{n.upper()},')
    out.append('    A_COUNT\n};')
    out.append('enum {')
    for n in SOUNDS:
        out.append(f'    S_{n.upper()},')
    out.append('    S_COUNT\n};')
    out.append('typedef struct { char file[28]; uint8_t frames; uint8_t half; int16_t ox, oy; } JeffSpriteDef;')
    out.append('static const JeffSpriteDef k_sprites[A_COUNT] = {')
    for n, f, ox, oy, half in sp:
        assert len(f'jeff_{n}.png') < 28, n
        out.append(f'    {{"jeff_{n}.png", {f}, {half}, {ox}, {oy}}},')
    out.append('};')
    out.append('static const char k_sounds[S_COUNT][24] = {')
    for n in SOUNDS:
        out.append(f'    "jeff_{n}.ogg",')
    out.append('};')
    # per frame: front fist, back fist, kicking foot (1x px from the feet, facing right), hot bits
    out.append(f'#define JEFF_BODY_N {len(fj["order"])}      /* body animations are A_0 .. JEFF_BODY_N-1 */')
    out.append(f'#define A_DARK0 A_D_{fj["order"][0].upper()}       /* their black (red-power) copies, same order */')
    out.append('typedef struct { int8_t fx, fy, bx, by, kx, ky; uint8_t hot, flags; int16_t fa, ba; int8_t elx, ely, erx, ery; } JeffFrame;'
               '   /* hot: 1 F, 2 B, 4 K; flags: 1 eyes open, 2 front arm over, 4 back arm over; fa: sun sword angle, ba: back arm angle (degrees, y down); eye centres */')
    first, rows = [], []
    for n, *_ in sp:
        if n in fj['anims']:
            first.append(len(rows))
            for m in fj['anims'][n]['meta']:
                hot = (1 if 'F' in m['hot'] else 0) | (2 if 'B' in m['hot'] else 0) | (4 if 'K' in m['hot'] else 0)
                clamp = lambda v: max(-127, min(127, int(v)))
                rows.append((clamp(m['fx']), clamp(m['fy']), clamp(m['bx']), clamp(m['by']), clamp(m['kx']), clamp(m['ky']), hot,
                             int(m.get('flags', 0)), int(m.get('fa', 0)), int(m.get('ba', 0)),
                             clamp(m.get('elx', 0)), clamp(m.get('ely', 0)), clamp(m.get('erx', 0)), clamp(m.get('ery', 0))))
        else:
            first.append(-1)
    out.append('static const int16_t k_jeff_meta_first[A_COUNT] = {' + ', '.join(map(str, first)) + '};')
    out.append(f'static const JeffFrame k_jeff_meta[{len(rows)}] = {{')
    for r in rows:
        out.append('    {%d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d},' % r)
    out.append('};')
    out.append(f'#define CUT_W {CUT_W}\n#define CUT_H {CUT_H}')
    return '\n'.join(out) + '\n'


if __name__ == '__main__':
    import sys
    open(sys.argv[2], 'w').write(header(sys.argv[1]))
