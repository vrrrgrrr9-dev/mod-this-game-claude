"""Render every Grey asset into one folder.  usage: python build_art.py <outdir>"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fx, grey_sfx, grey_manifest as manifest
from PIL import Image


def main(out):
    os.makedirs(out, exist_ok=True)
    fx.build(out)
    fx.face().save(os.path.join(out, 'grey_face.png'))
    grey_sfx.build(out)
    errors = []
    for n, k, ox, oy in manifest.sprites():
        p = os.path.join(out, f'grey_{n}.png')
        if not os.path.exists(p): errors.append('missing ' + p); continue
        im = Image.open(p)
        if im.width % k: errors.append(f'{n}: width {im.width} not divisible by {k}')
        if im.width > 4096 or im.height > 4096: errors.append(f'{n}: too big {im.size}')
    for n in manifest.SOUNDS:
        if not os.path.exists(os.path.join(out, f'grey_{n}.ogg')): errors.append('missing sound ' + n)
    if errors: sys.exit('\n'.join(errors))
    print(f'grey art ok: {len(manifest.sprites())} sprites, {len(manifest.SOUNDS)} sounds -> {out}')


if __name__ == '__main__':
    main(sys.argv[1])
