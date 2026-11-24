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
SPECIAL = [('sp_impact', 10, 48, 48), ('sp_dash', 6, 48, 40), ('cut_a', 12, 0, 0), ('cut_b', 12, 0, 0), ('cut_c', 12, 0, 0)]

# custom sounds (file = jeff_<name>.ogg); the rest of Jeff's audio reuses the game's own sounds
SOUNDS = ['crack1', 'crack2', 'crack3', 'ko', 'flame', 'meteor', 'hole']

CUT_W, CUT_H = 320, 180     # cutscene panel size (scaled up to the GUI layer in game)


def sprites(assets):
    """[(name, frames, ox, oy, half)] in enum order."""
    fj = json.load(open(os.path.join(assets, 'jeff_frames.json')))
    out = [(n, a['n'], a['ox'], a['oy'], 0) for n, a in ((n, fj['anims'][n]) for n in fj['order'])]
    pv = fj['preview']
    out.append(('preview', pv['n'], pv['ox'], pv['oy'], 0))
    out.append(('face', 1, 0, 0, 0))
    out += [(n, f, ox, oy, 0) for n, f, ox, oy in FLAME + SPECIAL]
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
    out.append('typedef struct { int8_t fx, fy, bx, by, kx, ky; uint8_t hot, pad; } JeffFrame;   /* hot: 1 F, 2 B, 4 K */')
    first, rows = [], []
    for n, *_ in sp:
        if n in fj['anims']:
            first.append(len(rows))
            for m in fj['anims'][n]['meta']:
                hot = (1 if 'F' in m['hot'] else 0) | (2 if 'B' in m['hot'] else 0) | (4 if 'K' in m['hot'] else 0)
                clamp = lambda v: max(-127, min(127, int(v)))
                rows.append((clamp(m['fx']), clamp(m['fy']), clamp(m['bx']), clamp(m['by']), clamp(m['kx']), clamp(m['ky']), hot))
        else:
            first.append(-1)
    out.append('static const int16_t k_jeff_meta_first[A_COUNT] = {' + ', '.join(map(str, first)) + '};')
    out.append(f'static const JeffFrame k_jeff_meta[{len(rows)}] = {{')
    for r in rows:
        out.append('    {%d, %d, %d, %d, %d, %d, %d, 0},' % r)
    out.append('};')
    out.append(f'#define CUT_W {CUT_W}\n#define CUT_H {CUT_H}')
    return '\n'.join(out) + '\n'


if __name__ == '__main__':
    import sys
    open(sys.argv[2], 'w').write(header(sys.argv[1]))
