"""Scyther's portrait card (48x77, HUD + character select) in the game's gold card layout:
gold border, 42x60 portrait window (cosmic backdrop, a blade of the scythe behind him, his fierce
head straight from the 2x render), gold name plate."""
import os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rig, weapon, cutscene

X0, Y0, X1, Y1 = 3, 3, 45, 63
GOLD_HI, GOLD, GOLD_LO, INK = (242, 223, 77, 255), (219, 161, 2, 255), (163, 81, 0, 255), (0, 0, 0, 255)


def frame():
    W, H = 48, 77
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, W - 1, H - 1), 4, fill=INK)
    d.rounded_rectangle((1, 1, W - 2, H - 2), 3, fill=GOLD_HI)
    d.rounded_rectangle((2, 2, W - 3, H - 3), 2, fill=GOLD_LO)
    d.rectangle((X0, Y0, X1 - 1, Y1 - 1), fill=INK)
    d.rectangle((3, 64, W - 4, 73), fill=GOLD)
    d.line((4, 64, W - 5, 64), fill=GOLD_LO)
    d.line((4, 66, W - 5, 66), fill=GOLD_HI)
    d.line((3, 74, W - 4, 74), fill=GOLD_LO)
    d.line((2, 75, W - 3, 75), fill=GOLD_HI)
    return im


def portrait():
    w, h = X1 - X0, Y1 - Y0
    bg = cutscene.space_bg(21, dim=0.9)
    bg = Image.fromarray(bg.astype(np.uint8)).convert('RGBA').crop((100, 40, 100 + w, 40 + h))
    blade = weapon.render(-118, held=False)
    blade = blade.resize((blade.width // 2, blade.height // 2), Image.LANCZOS)
    bg.alpha_composite(blade.crop((20, 6, 20 + w, 6 + h)))
    pose = dict(eye='glow', beak=0, neck=-4, head=(0, 0, -6), wing='fold', flow=2)
    im, _ = rig.render(pose)
    p, G, U, Hn, Hm, Tm = rig.build(pose)
    hx, hy = rig.ap(Hm, rig.HC)
    cx, cy = rig.OX + hx * rig.K, rig.OY + hy * rig.K
    x0, y0 = int(cx - 22), int(cy - 24)                 # 2x head crop fills the 42x60 window
    bg.alpha_composite(im.crop((x0, y0, x0 + w, y0 + h)))
    return bg


def card():
    out = frame()
    out.paste(portrait(), (X0, Y0))
    return out


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else '/tmp'
    c = card()
    c.save(os.path.join(out, 'scyther_face.png'))
    c.resize((c.width * 6, c.height * 6), Image.NEAREST).save(os.path.join(out, 'face_x6.png'))
    print('face ok')
