"""Single source of truth for Jeff's runtime assets (loaded with sprite_add / audio_create_stream).

Each sprite is a horizontal strip PNG in the APK's assets/ folder. Order matters: the C code
uses the generated enum (src/jeff_assets.h) as an index into the loaded-sprite table.
"""

# name, frames, origin x, origin y   (file = jeff_<name>.png)
SPRITES = [
    # --- body (96x72 frames, feet at 48,71) ---
    ('stand', 4, 48, 71), ('walk', 6, 48, 71), ('run', 6, 48, 71), ('jump', 2, 48, 71),
    ('fall', 2, 48, 71), ('crouch', 1, 48, 71), ('defend', 2, 48, 71), ('charge', 2, 48, 71),
    ('hurt', 2, 48, 71), ('hurtup', 1, 48, 71), ('hurtdown', 1, 48, 71), ('fallen', 1, 48, 71),
    ('jab', 3, 48, 71), ('cross', 3, 48, 71), ('hook', 4, 48, 71), ('uppercut', 4, 48, 71),
    ('airpunch', 2, 48, 71), ('crouchpunch', 2, 48, 71), ('cast1', 4, 48, 71), ('cast2', 4, 48, 71),
    ('grab', 2, 48, 71), ('win', 2, 48, 71),
    # --- portrait / select ---
    ('face', 1, 0, 0), ('preview', 4, 48, 71),
    # --- skill 1: runic ant swarm ---
    ('s1_circle', 16, 48, 16), ('s1_swarm', 12, 56, 40), ('s1_burst', 16, 64, 92), ('s1_spark', 8, 8, 8),
    # --- skill 2: starlight lance ---
    ('s2_orb', 8, 20, 20), ('s2_beam', 8, 0, 16), ('s2_tip', 8, 24, 24), ('s2_nova', 16, 64, 64),
    # --- special: bone breaker ---
    ('sp_impact', 10, 48, 48), ('sp_dash', 6, 48, 40), ('aura', 8, 40, 78),
    ('cut_a', 12, 0, 0), ('cut_b', 12, 0, 0), ('cut_c', 12, 0, 0),
]

# custom sounds (file = jeff_<name>.ogg); the rest of Jeff's audio reuses the game's own sounds
SOUNDS = ['crack1', 'crack2', 'crack3', 'swarm', 'beam', 'ko']

CUT_W, CUT_H = 320, 180     # cutscene panel size (scaled up to the GUI layer in game)


def header():
    """C header with the asset enums and a pointer-free table (no relocations needed)."""
    out = ['/* generated from art/manifest.py - do not edit */', '#pragma once', '#include <stdint.h>', '']
    out.append('enum {')
    for n, *_ in SPRITES:
        out.append(f'    A_{n.upper()},')
    out.append('    A_COUNT\n};')
    out.append('enum {')
    for n in SOUNDS:
        out.append(f'    S_{n.upper()},')
    out.append('    S_COUNT\n};')
    out.append('typedef struct { char file[28]; uint8_t frames; uint8_t pad; int16_t ox, oy; } JeffSpriteDef;')
    out.append('static const JeffSpriteDef k_sprites[A_COUNT] = {')
    for n, f, ox, oy in SPRITES:
        out.append(f'    {{"jeff_{n}.png", {f}, 0, {ox}, {oy}}},')
    out.append('};')
    out.append('static const char k_sounds[S_COUNT][24] = {')
    for n in SOUNDS:
        out.append(f'    "jeff_{n}.ogg",')
    out.append('};')
    out.append(f'#define CUT_W {CUT_W}\n#define CUT_H {CUT_H}')
    return '\n'.join(out) + '\n'


if __name__ == '__main__':
    import sys
    open(sys.argv[1], 'w').write(header())
