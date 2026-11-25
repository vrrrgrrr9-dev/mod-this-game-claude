"""Jeff's portrait card (48x77, HUD + character select) and select-screen preview.

Draws a golden card in the same layout/palette as the game's portrait cards (e.g. Erbito Black
Rose's face sprite: gold border, 42x60 portrait window, gold name plate) and paints Jeff into it.
"""
import os, sys, math
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rig

HERE = os.path.dirname(os.path.abspath(__file__))
X0, Y0, X1, Y1 = 3, 3, 45, 63          # portrait window (exclusive end)


def portrait(dark=False):
    """blue power: the white Jeff on violet; red power: the black form on a sun-red backdrop."""
    w, h = X1 - X0, Y1 - Y0
    bg = np.zeros((h, w, 4), np.uint8)
    for y in range(h):
        k = y / h
        bg[y, :, :3] = (int(120 - 80 * k), int(34 - 24 * k), int(14 - 8 * k)) if dark else \
                       (int(70 - 45 * k), int(30 - 18 * k), int(110 - 70 * k))
    bg[..., 3] = 255
    im = Image.fromarray(bg)
    d = ImageDraw.Draw(im)
    rings = ((26, (220, 100, 30, 255)), (19, (160, 50, 20, 255))) if dark else ((26, (110, 60, 190, 255)), (19, (80, 40, 150, 255)))
    for r, col in rings:                                                    # faint rune rings
        d.ellipse((w / 2 - r, 30 - r, w / 2 + r, 30 + r), outline=col)
    for i in range(8):
        a = i * math.pi / 4
        d.point((w / 2 + 26 * math.cos(a), 30 + 26 * math.sin(a)), fill=(255, 210, 90, 255) if dark else (200, 150, 255, 255))
    sc = 0.068
    D = rig.DARK
    c = rig.Canvas(w, h, int(round(w / 2 - (620 - rig.PIVOT['root'][0]) * sc)),
                   int(round(3 + (rig.PIVOT['root'][1] - 300) * sc)), sc, D['line'] if dark else rig.BLACK)
    c.begin()
    M = np.eye(3)
    c.put(c.mask_from_crop('tail', M), D['limb'] if dark else rig.FILL)
    c.put(c.mask_from_crop('body', M), D['torso'] if dark else rig.FILL)
    c.put(c.mask_from_crop('bandana', M), D['line'] if dark else rig.BLACK, outline=False)
    c.put(c.mask_from_crop('head', M), D['head'] if dark else rig.FILL)
    for e in ('eyeL', 'eyeR'):
        if dark: rig._dark_eye(c, c.mask_from_crop(e, M), 'open')
        else: c.put(c.mask_from_crop(e, M), rig.WHITE)
    c.line(rig.MOUTH, M, D['line'] if dark else rig.BLACK)
    if dark: rig._chest_tag(c, M)
    im.alpha_composite(c.image())
    return im


GOLD_HI, GOLD, GOLD_LO, INK = (242, 223, 77, 255), (219, 161, 2, 255), (163, 81, 0, 255), (0, 0, 0, 255)


def frame():
    W, H = 48, 77
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, W - 1, H - 1), 4, fill=INK)            # outer ink
    d.rounded_rectangle((1, 1, W - 2, H - 2), 3, fill=GOLD_HI)        # bright rim
    d.rounded_rectangle((2, 2, W - 3, H - 3), 2, fill=GOLD_LO)        # dark rim
    d.rectangle((X0, Y0, X1 - 1, Y1 - 1), fill=INK)                   # window
    # name plate
    d.rectangle((3, 64, W - 4, 73), fill=GOLD)
    d.line((4, 64, W - 5, 64), fill=GOLD_LO)
    d.line((4, 66, W - 5, 66), fill=GOLD_HI)
    d.line((3, 74, W - 4, 74), fill=GOLD_LO)
    d.line((2, 75, W - 3, 75), fill=GOLD_HI)
    return im


def card(dark=False):
    out = frame()
    out.paste(portrait(dark), (X0, Y0))
    return out


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'out'
    os.makedirs(out, exist_ok=True)
    card().save(os.path.join(out, 'jeff_face.png'))
    card(True).save(os.path.join(out, 'jeff_face_d.png'))
    print('face ok')
