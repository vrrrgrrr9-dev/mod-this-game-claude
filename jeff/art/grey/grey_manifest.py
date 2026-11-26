"""Grey's runtime assets (sprite_add / audio_create_stream) -> gen/grey_assets.h, plus the moves."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fx

SOUNDS = ['glitch', 'clone', 'ice', 'crash']


def sprites():
    out = [(n, k, ox, oy) for n, (fn, k, ox, oy) in fx.SPRITES.items()]
    out += [('m_' + n, k, 0, 0) for n, k in fx.MARKERS]
    out.append(('face', 1, 0, 0))
    return out


def header():
    sp = sprites()
    o = ['/* generated from art/grey/grey_manifest.py - do not edit */', '#pragma once', '#include <stdint.h>', '']
    o.append('enum {'); o += [f'    GR_{n.upper()},' for n, *_ in sp]; o.append('    GR_COUNT\n};')
    o.append('enum {'); o += [f'    GS_{n.upper()},' for n in SOUNDS]; o.append('    GS_COUNT\n};')
    o.append('typedef struct { char file[28]; uint8_t frames; int16_t ox, oy; } GreySpriteDef;')
    o.append('static const GreySpriteDef k_grey_sprites[GR_COUNT] = {')
    for n, k, ox, oy in sp:
        assert len(f'grey_{n}.png') < 28, n
        o.append(f'    {{"grey_{n}.png", {k}, {ox}, {oy}}},')
    o.append('};')
    o.append('static const char k_grey_sounds[GS_COUNT][24] = {')
    o += [f'    "grey_{n}.ogg",' for n in SOUNDS]
    o.append('};')
    import moonfall                              # the ragged melt front, for the shock ring
    o.append(moonfall.front_table_c())
    return '\n'.join(o) + '\n'


if __name__ == '__main__':
    gen = sys.argv[2]
    open(os.path.join(gen, 'grey_assets.h'), 'w').write(header())
    import moves
    open(os.path.join(gen, 'grey_moves.h'), 'w').write(moves.export_c())
