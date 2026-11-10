#!/usr/bin/env python3
"""HOW TO PLAY (INSTR1) render mockups -> assets/gfx/instr/instr_p{1,2}.png (+ @3).

Source spec: docs/design/instructions_screen.txt + the PAGES table in tools/instr_pack.py
(shared with the build, INSTR-BUILD). Text = real FONT6 (assets/gfx/fonts/font6x8.bin,
6x8 at x=6k,y=8r); icons/tiles decoded from the real asm tables. Attribute-legal: every
8x8 cell has one INK+PAPER (+BRIGHT); --check also verifies no ink pixel is invisible
(ink==paper), <=2 colours per cell in the rendered image, and rows <= 42 chars.
Usage: tools/gen_instr_mock.py [--check]
"""
import os, re, sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import instr_pack  # noqa: E402  (the shared page spec)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G = os.path.join(ROOT, "assets", "gfx")
OUT = os.path.join(G, "instr")
W, H = 256, 192


def rd(p):
    return open(os.path.join(G, p)).read()


def font6():
    raw = open(os.path.join(G, "fonts", "font6x8.bin"), "rb").read()
    return {chr(32 + i): np.array([[(raw[i * 8 + r] >> (7 - b)) & 1 for b in range(6)]
                                   for r in range(8)], bool) for i in range(96)}


def hexes(txt):
    return [int(x, 16) for x in re.findall(r"\$([0-9A-Fa-f]{2})", re.sub(r";[^\n]*", "", txt))]


def bytes_after(txt, label, n):
    """First n DEFB bytes after `label:`."""
    return hexes(txt.split(label + ":", 1)[1])[:n]


I16 = rd("icons/icons16.asm")
I16_BYTES = hexes(I16.split("\nicons16:", 1)[1])
PI = rd("panel/panel_icons.asm")
TC = rd("tiles/tiles_common.asm")


I16_NAMES = re.findall(r"^;\s*\d+ (\w+)\s", I16.split("\nicons16:", 1)[1], re.M)  # physical order


def icon16(name):
    """16x16 bool by name (physical order = file order; Mana/Cure share p_heal's shape)."""
    idx = I16_NAMES.index(name)
    d = I16_BYTES[idx * 32:idx * 32 + 32]
    bm = np.zeros((16, 16), bool)
    for q, (oy, ox) in enumerate([(0, 0), (0, 8), (8, 0), (8, 8)]):
        for y in range(8):
            for x in range(8):
                bm[oy + y, ox + x] = d[q * 8 + y] >> (7 - x) & 1
    return bm


def bar24(name):
    d = bytes_after(PI, name, 54)
    bm = np.array([[d[y * 3 + x // 8] >> (7 - x % 8) & 1 for x in range(24)] for y in range(16)], bool)
    return bm, d[48:54]


def tile(i):
    d = bytes_after(TC, "tiles_common_glyphs", 32 * 8)[i * 8:i * 8 + 8]
    a = bytes_after(TC, "tiles_common_attrs", 32)[i]
    return np.array([[v >> (7 - x) & 1 for x in range(8)] for v in d], bool), a


FONT = font6()


class Scr:
    def __init__(s):
        s.bm = np.zeros((H, W), bool)
        s.at = np.zeros((24, 32), np.uint8)
        s.warn = []

    def fill(s, rows, c0, c1, a):
        for r in rows:
            s.at[r, c0:c1 + 1] = a

    def text(s, rows):
        for r, ln in enumerate(rows):
            if len(ln) > 42:
                s.warn.append("row %d: %d chars > 42" % (r, len(ln)))
            for k, ch in enumerate(ln):
                s.bm[r * 8:r * 8 + 8, k * 6:k * 6 + 6] |= FONT[ch]

    def blit(s, bm, r, c, attrs):
        h, w = bm.shape
        s.bm[r * 8:r * 8 + h, c * 8:c * 8 + w] = bm
        for i, a in enumerate(attrs):
            s.at[r + i // (w // 8), c + i % (w // 8)] = a


def page(n):
    """Page n from the shared spec (tools/instr_pack.py PAGES: fills, icons; text rows)."""
    s = Scr()
    rows = instr_pack.rows(n)
    for r, c0, c1, a in instr_pack.PAGES[n]["fills"]:
        s.fill([r], c0, c1, a)
    s.text(rows)
    for ic in instr_pack.PAGES[n]["icons"]:
        kind, arg, r, c = ic[:4]
        if kind == "bar":
            bm, at = bar24(arg)
            s.blit(bm, r, c, at)
        elif kind == "tile":
            bm, a = tile(arg)
            s.blit(bm, r, c, [a])
        elif kind == "label":
            d = bytes_after(PI, arg, 9)
            s.blit(np.array([[v >> (7 - x) & 1 for x in range(8)] for v in d[:8]], bool), r, c, [d[8]])
        else:
            s.blit(icon16(arg), r, c, [ic[4]] * 4)
    return s


def page1():
    return page(1)


def rgb(idx, br):
    lv = 0xFF if br else 0xD7
    return ((idx >> 1 & 1) * lv, (idx >> 2 & 1) * lv, (idx & 1) * lv)


def render(s):
    img = np.zeros((H, W, 3), np.uint8)
    for r in range(24):
        for c in range(32):
            a = int(s.at[r, c]); br = a >> 6 & 1
            blk = s.bm[r * 8:r * 8 + 8, c * 8:c * 8 + 8]
            img[r * 8:r * 8 + 8, c * 8:c * 8 + 8] = np.where(
                blk[..., None], rgb(a & 7, br), rgb(a >> 3 & 7, br))
    return img


def check(s, name):
    bad = list(s.warn)
    img = render(s)
    for r in range(24):
        for c in range(32):
            a = int(s.at[r, c])
            blk = s.bm[r * 8:r * 8 + 8, c * 8:c * 8 + 8]
            cell = img[r * 8:r * 8 + 8, c * 8:c * 8 + 8].reshape(-1, 3)
            if len({tuple(p) for p in cell}) > 2:
                bad.append("clash r%d c%d" % (r, c))
            if blk.any() and (a & 7) == (a >> 3 & 7):
                bad.append("invisible ink r%d c%d attr $%02X" % (r, c, a))
    for b in bad:
        print(name, "FAIL", b)
    print(name, "ok" if not bad else "%d problems" % len(bad))
    return not bad


def main():
    ok = True
    for n, s in (("instr_p1", page(1)), ("instr_p2", page(2))):
        ok &= check(s, n)
        if "--check" in sys.argv:
            continue
        im = Image.fromarray(render(s))
        im.save(os.path.join(OUT, n + ".png"))
        im.resize((W * 3, H * 3), Image.NEAREST).save(os.path.join(OUT, n + "@3.png"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
