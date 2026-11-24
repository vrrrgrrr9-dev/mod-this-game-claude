"""Render every Scyther asset into one directory and write the sprite manifest.

  python build_art.py <outdir>

Writes scyther_*.png strips, scyther_*.ogg sounds, scyther_frames.json (body animation metadata)
and scyther_sprites.json (name, frames, origin, half-scale flag for every sprite, in enum order) -
manifest.py turns the two JSON files into the C header.
"""
import json, os, sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rig, weapon, rift, arcs, vfx, void, cutscene, face, sfx, anims


def save_strip(frames, path, crop=True):
    """frames -> horizontal strip (optionally cropped to the union bbox); returns (fw, fh, x0, y0)."""
    w, h = frames[0].size
    x0, y0, x1, y1 = 0, 0, w, h
    if crop:
        box = None
        for f in frames:
            bb = f.getbbox()
            if bb:
                box = bb if box is None else (min(box[0], bb[0]), min(box[1], bb[1]), max(box[2], bb[2]), max(box[3], bb[3]))
        if box:
            x0, y0 = max(0, box[0] - 1), max(0, box[1] - 1)
            x1, y1 = min(w, box[2] + 1), min(h, box[3] + 1)
    fw, fh = x1 - x0, y1 - y0
    s = Image.new('RGBA', (fw * len(frames), fh), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        s.paste(f.crop((x0, y0, x1, y1)), (i * fw, 0))
    assert s.width <= 4096, f'{path}: strip {s.width}px wider than a mobile texture'
    s.save(path)
    return fw, fh, x0, y0


def main(out):
    os.makedirs(out, exist_ok=True)
    P = lambda n: os.path.join(out, f'scyther_{n}.png')
    sprites = []                                   # (name, frames, ox, oy, half)

    # body animations (2x, cropped per animation) + select-screen preview + portrait card
    anims.build(out)
    fj = json.load(open(os.path.join(out, 'scyther_frames.json')))
    for name in fj['order']:
        a = fj['anims'][name]
        sprites.append((name, len(a['meta']), a['ox'], a['oy'], 1))
    pv = fj['preview']
    sprites.append(('preview', 4, pv['ox'], pv['oy'], 0))
    face.card().save(P('face'))
    sprites.append(('face', 1, 0, 0, 0))

    # the scythe (2x): flat held angles split in two strips, twirl back/front, thrown disc
    C = weapon.WS // 2
    sets = [('wpn0', [weapon.render(i * 11.25, held=True) for i in range(16)]),
            ('wpn1', [weapon.render(i * 11.25, held=True) for i in range(16, 32)]),
            ('orbb', [weapon.render(i * 18.0, held=True, tilt=64, layer='back') for i in range(20)]),
            ('orbf', [weapon.render(i * 18.0, held=True, tilt=64, layer='front') for i in range(20)]),
            ('disc', [weapon.render(i * 18.0, held=False, tilt=74) for i in range(20)])]
    for name, frames in sets:
        fw, fh, x0, y0 = save_strip(frames, P(name), crop=True)
        sprites.append((name, len(frames), C - x0, C - y0, 1))

    # reality tears: small one at 2x, the big one at 1x
    R = rift.all_rifts()
    for name, half in (('rift', 1), ('riftbig', 0)):
        v, e, (ox, oy) = R[name]
        save_strip(v, P(name + '_v'), crop=False); save_strip(e, P(name + '_e'), crop=False)
        sprites.append((name + '_v', len(v), ox, oy, half))
        sprites.append((name + '_e', len(e), ox, oy, half))

    # 3D swing arcs (back + front layers)
    for name, cfg in arcs.ARCS.items():
        b, f = arcs.strips(name)
        b.save(P(f'arc_{name}_b')); f.save(P(f'arc_{name}_f'))
        sprites.append((f'arc_{name}_b', arcs.NFR, cfg['ox'], cfg['oy'], 0))
        sprites.append((f'arc_{name}_f', arcs.NFR, cfg['ox'], cfg['oy'], 0))

    # skill / ultimate effects
    vfx.build(out)
    for name, (fn, n, ox, oy, add) in vfx.FX_LIST.items():
        sprites.append((name, n, ox, oy, 0))

    # the void left behind by SINGULARITY, and the cutscene
    rocks = void.build(out)
    sprites += [('void_sky', 2, 0, 0, 0), ('void_rocks', 8, 40, 32, 0), ('void_floor', 1, 0, 0, 0),
                ('void_top', 5, 0, 0, 0), ('void_dust', 8, 4, 4, 0)]
    # the rooster is not baked into act 3: the game draws him live from his 2x sprites (crisp at any
    # screen size) at manifest.HERO_* on top of the panels
    cutscene.render_all(out, rocks, None)
    sprites += [('cut_a', 12, 0, 0, 0), ('cut_b', 12, 0, 0, 0), ('cut_c', 12, 0, 0, 0)]

    for name, fn in sfx.SOUNDS.items():
        sfx.write_ogg(fn(), os.path.join(out, f'scyther_{name}.ogg'))

    # validate: every sprite file exists and its width is a whole number of frames
    for name, n, ox, oy, half in sprites:
        im = Image.open(P(name))
        assert im.width % n == 0, f'{name}: width {im.width} not divisible by {n} frames'
    json.dump({'sprites': sprites, 'sounds': list(sfx.SOUNDS)}, open(os.path.join(out, 'scyther_sprites.json'), 'w'))
    # previews and intermediates are not game assets
    for junk in ('preview_sheet.png', 'vfx_preview.png', 'void_preview.png', 'cutscene_preview.png'):
        if os.path.exists(os.path.join(out, junk)):
            os.remove(os.path.join(out, junk))
    print(f'scyther art ok: {len(sprites)} sprites, {len(sfx.SOUNDS)} sounds -> {out}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'out')
