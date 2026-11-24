"""Generate src/scyther_assets.h from the art build's JSON (build_art.py writes both files).

  python manifest.py <assets dir> <out header>

Contents: SC_* sprite enum (enum order = load order), SCS_* sound enum, the sprite table (file,
frames, origin, half-scale flag: 2x-density sprites are drawn at 0.5 by the game), and the
per-frame weapon table for body animations (grip offset from the feet in 2x pixels, scythe angle,
flags: 1 = scythe behind the body, 2 = scythe not in hand (thrown), 4 = mirrored).
"""
import json, os, sys


def header(assets):
    sj = json.load(open(os.path.join(assets, 'scyther_sprites.json')))
    fj = json.load(open(os.path.join(assets, 'scyther_frames.json')))
    sprites, sounds = sj['sprites'], sj['sounds']
    names = [s[0] for s in sprites]
    o = ['/* generated from art/scyther (build_art.py + manifest.py) - do not edit */', '#pragma once',
         '#include <stdint.h>', '']
    o.append('enum {')
    for n in names:
        o.append(f'    SC_{n.upper()},')
    o.append('    SC_COUNT\n};')
    o.append('enum {')
    for n in sounds:
        o.append(f'    SCS_{n.upper()},')
    o.append('    SCS_COUNT\n};')
    o.append('typedef struct { char file[32]; uint8_t frames; uint8_t half; int16_t ox, oy; } ScySpriteDef;')
    o.append('static const ScySpriteDef k_scy_sprites[SC_COUNT] = {')
    for n, fr, ox, oy, half in sprites:
        fname = f'scyther_{n}.png'
        assert len(fname) < 32, fname
        o.append(f'    {{"{fname}", {fr}, {half}, {ox}, {oy}}},')
    o.append('};')
    o.append('static const char k_scy_sounds[SCS_COUNT][24] = {')
    for n in sounds:
        o.append(f'    "scyther_{n}.ogg",')
    o.append('};')
    # per-frame weapon metadata for the body animations
    o.append('typedef struct { int16_t gx, gy, ang; uint8_t fl, pad; } ScyFrame;')
    first, rows = [], []
    for n in names:
        if n in fj['anims']:
            first.append(len(rows))
            for m in fj['anims'][n]['meta']:
                fl = (1 if m.get('wl') else 0) | (2 if m.get('wh') else 0) | (4 if m.get('wf') else 0)
                rows.append((m['gx'], m['gy'], m['wang'], fl))
        else:
            first.append(-1)
    o.append('static const int16_t k_scy_meta_first[SC_COUNT] = {' + ', '.join(map(str, first)) + '};')
    o.append(f'static const ScyFrame k_scy_meta[{len(rows)}] = {{')
    for gx, gy, ang, fl in rows:
        o.append(f'    {{{gx}, {gy}, {ang}, {fl}, 0}},')
    o.append('};')
    o.append(f'#define SCY_CUT_W 320\n#define SCY_CUT_H 180\n#define SCY_RENDER_K {fj["k"]}')
    return '\n'.join(o) + '\n'


if __name__ == '__main__':
    open(sys.argv[2], 'w').write(header(sys.argv[1]))
    print('header ok')
