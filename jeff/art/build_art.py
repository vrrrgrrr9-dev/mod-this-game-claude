"""Render every Jeff asset listed in manifest.py into one folder and validate it.

usage: python build_art.py <outdir>
"""
import os, shutil, sys
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import manifest, anims, flame, sun, vfx, cutscene, face, sfx


def main(out):
    os.makedirs(out, exist_ok=True)
    anims.build(out)                             # body animations + preview + jeff_frames.json
    face.card().save(os.path.join(out, 'jeff_face.png'))
    face.card(True).save(os.path.join(out, 'jeff_face_d.png'))  # HUD card in the red power
    flame.build(out)                             # dark blue flame effects
    sun.build(out)                               # red sun power + the two cinematics
    for name in ('sp_impact', 'sp_dash'):
        vfx.ALL[name]().save(os.path.join(out, f'jeff_{name}.png'))
    cutscene.render_all(out)
    sfx.write_ogg(sfx.snap(0.32, 1.0, 6), os.path.join(out, 'jeff_crack1.ogg'))
    sfx.write_ogg(sfx.snap(0.36, 1.25, 9), os.path.join(out, 'jeff_crack2.ogg'))
    sfx.write_ogg(sfx.snap(0.45, 0.8, 14), os.path.join(out, 'jeff_crack3.ogg'))
    sfx.write_ogg(sfx.ko(), os.path.join(out, 'jeff_ko.ogg'))
    sfx.write_ogg(sfx.flame(), os.path.join(out, 'jeff_flame.ogg'))
    sfx.write_ogg(sfx.meteor(), os.path.join(out, 'jeff_meteor.ogg'))
    sfx.write_ogg(sfx.hole(), os.path.join(out, 'jeff_hole.ogg'))
    sfx.write_ogg(sfx.power(), os.path.join(out, 'jeff_power.ogg'))
    sfx.write_ogg(sfx.nuke(), os.path.join(out, 'jeff_nuke.ogg'))
    SPRITES = manifest.sprites(out)

    # validate against the manifest the C code is generated from
    errors = []
    for name, frames, ox, oy, half in SPRITES:
        p = os.path.join(out, f'jeff_{name}.png')
        if not os.path.exists(p):
            errors.append(f'missing {p}'); continue
        im = Image.open(p)
        if im.width % frames:
            errors.append(f'{name}: width {im.width} not divisible by {frames} frames')
        if im.width > 4096 or im.height > 4096:
            errors.append(f'{name}: {im.size} exceeds 4096 px')
    for name in manifest.SOUNDS:
        if not os.path.exists(os.path.join(out, f'jeff_{name}.ogg')):
            errors.append(f'missing sound {name}')
    keep = {f'jeff_{n}.png' for n, *_ in SPRITES} | {f'jeff_{n}.ogg' for n in manifest.SOUNDS} | {'jeff_frames.json'}
    for f in os.listdir(out):
        if f not in keep:
            os.remove(os.path.join(out, f))
    if errors:
        sys.exit('\n'.join(errors))
    print(f'art ok: {len(SPRITES)} sprites, {len(manifest.SOUNDS)} sounds -> {out}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'out')
