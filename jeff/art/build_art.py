"""Render every Jeff asset listed in manifest.py into one folder and validate it.

usage: python build_art.py <outdir>
"""
import os, shutil, sys
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import manifest, anims, vfx, cutscene, face, sfx


def main(out):
    os.makedirs(out, exist_ok=True)
    # body animations (96x72 frames)
    for name in anims.ANIMS:
        anims.strip(anims.render_anim(name)).save(os.path.join(out, f'jeff_{name}.png'))
    shutil.copyfile(os.path.join(out, 'jeff_stand.png'), os.path.join(out, 'jeff_preview.png'))
    face.card().save(os.path.join(out, 'jeff_face.png'))
    for name, fn in vfx.ALL.items():
        fn().save(os.path.join(out, f'jeff_{name}.png'))
    cutscene.render_all(out)
    sfx.write_ogg(sfx.snap(0.32, 1.0, 6), os.path.join(out, 'jeff_crack1.ogg'))
    sfx.write_ogg(sfx.snap(0.36, 1.25, 9), os.path.join(out, 'jeff_crack2.ogg'))
    sfx.write_ogg(sfx.snap(0.45, 0.8, 14), os.path.join(out, 'jeff_crack3.ogg'))
    sfx.write_ogg(sfx.swarm(), os.path.join(out, 'jeff_swarm.ogg'))
    sfx.write_ogg(sfx.beam(), os.path.join(out, 'jeff_beam.ogg'))
    sfx.write_ogg(sfx.ko(), os.path.join(out, 'jeff_ko.ogg'))

    # validate against the manifest the C code is generated from
    errors = []
    for name, frames, ox, oy in manifest.SPRITES:
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
    keep = {f'jeff_{n}.png' for n, *_ in manifest.SPRITES} | {f'jeff_{n}.ogg' for n in manifest.SOUNDS}
    for f in os.listdir(out):
        if f not in keep:
            os.remove(os.path.join(out, f))
    if errors:
        sys.exit('\n'.join(errors))
    print(f'art ok: {len(manifest.SPRITES)} sprites, {len(manifest.SOUNDS)} sounds -> {out}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'out')
