#!/usr/bin/env python3
"""HOW TO PLAY (INSTR1) render mockups -> assets/gfx/instr/instr_p{1,2}.png (+ @3).

Source spec: docs/design/instructions_screen.txt. Text = real FONT6 (assets/gfx/fonts/font6x8.bin,
6x8 at x=6k,y=8r); icons/tiles decoded from the real asm tables. Attribute-legal: every
8x8 cell has one INK+PAPER (+BRIGHT); --check also verifies no ink pixel is invisible
(ink==paper), <=2 colours per cell in the rendered image, and rows <= 42 chars.
Usage: tools/gen_instr_mock.py [--check]
"""
import os, re, sys
import numpy as np
from PIL import Image

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


def parse(page):
    rows, on = [], False
    for ln in open(os.path.join(ROOT, "docs/design/instructions_screen.txt")).read().split("\n"):
        if ln.startswith("==="):
            on = ln.startswith("=== PAGE %d ROWS" % page)
            continue
        if on:
            rows.append(ln)
    assert len(rows) == 24, (page, len(rows))
    return rows


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


def page1():
    s = Scr()
    rows = parse(1)
    s.fill([0], 0, 31, 0x46)
    s.fill([2, 3, 4, 5], 0, 31, 0x47)
    s.fill([7], 0, 31, 0x06)
    for r in (8, 9, 10, 11, 12, 13, 15):
        s.fill([r], 0, 8, 0x45); s.fill([r], 9, 23, 0x47); s.fill([r], 24, 31, 0x46)
    s.fill([14], 9, 31, 0x47)
    s.fill([16], 3, 23, 0x47); s.fill([16], 24, 31, 0x46)
    s.fill([17], 3, 31, 0x07)
    s.fill([18], 3, 31, 0x47); s.fill([19], 3, 31, 0x07)
    s.fill([21, 22], 0, 31, 0x05)
    s.fill([23], 0, 31, 0x46)
    s.text(rows)
    bm, at = bar24("icon_bag"); s.blit(bm, 16, 0, at)
    bm, at = bar24("icon_sword"); s.blit(bm, 18, 0, at)
    for (r, c, i) in ((4, 30, 15), (4, 31, 16), (5, 30, 17), (5, 31, 18)):
        bm, a = tile(i); s.blit(bm, r, c, [a])
    return s


def page2():
    s = Scr()
    rows = parse(2)
    s.fill([0, 12, 23], 0, 31, 0x46)
    s.fill([2], 0, 31, 0x06)
    for r in (3, 5, 7, 9):
        s.fill([r], 2, 31, 0x47)
    for r in (4, 6, 8, 10):
        s.fill([r], 2, 31, 0x07)
    for r, a in ((13, 0x47), (15, 0x45), (17, 0x47), (19, 0x45), (21, 0x47)):
        s.fill([r], 0, 31, a)
    s.text(rows)
    for r in range(3, 11):  # left-column text must end before the right icon (cell 16 = x128)
        for k, ch in enumerate(rows[r][:24]):
            if ch != ' ' and (k + 1) * 6 > 128:
                s.warn.append("row %d: left text char %d overlaps right icon" % (r, k))
    for (r, c, i, a) in ((3, 0, 'p_heal', 0x42), (3, 16, 'f_meat', 0x42), (5, 0, 's_teleport', 0x45),
                         (5, 16, 'book', 0x43), (7, 0, 'ammo_dagger', 0x47), (7, 16, 'w_long', 0x07)):
        s.blit(icon16(i), r, c, [a] * 4)
    d = bytes_after(PI, "label_key", 9)
    s.blit(np.array([[v >> (7 - x) & 1 for x in range(8)] for v in d[:8]], bool), 9, 1, [d[8]])
    bm, a = tile(13)
    s.blit(np.tile(bm, (2, 2)), 9, 16, [a] * 4)
    return s


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
    for n, s in (("instr_p1", page1()), ("instr_p2", page2())):
        ok &= check(s, n)
        if "--check" in sys.argv:
            continue
        im = Image.fromarray(render(s))
        im.save(os.path.join(OUT, n + ".png"))
        im.resize((W * 3, H * 3), Image.NEAREST).save(os.path.join(OUT, n + "@3.png"))
    sys.exit(0 if ok else 1)


main()
