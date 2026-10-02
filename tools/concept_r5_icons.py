#!/usr/bin/env python3
"""concept_r5_icons.py — deterministic 24x16 (3x2 cell) bar icons, CONCEPT round 5.

Writes assets/gfx/concept/grid/icons24x16.grid (block format, read by concept_r4.py).
Each icon is built from explicit geometry (polygons, Bresenham lines, ellipses, arcs) and
small hand-typed overlays; no raster input. The 24x16 shape (user decision, round 5) frees a
full panel row for the selected action's name/cost/range text.

Usage: python3 tools/concept_r5_icons.py
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_missing_frames import blank, line, poly, over  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "assets/gfx/concept/grid/icons24x16.grid")
W, H = 24, 16


def ell(cx, cy, rx, ry):
    yy, xx = np.mgrid[0:H, 0:W]
    return ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0


def thick(b, x0, y0, x1, y1, t=2, ink=True, vertical=False):
    for k in range(t):
        if vertical:
            line(b, x0, y0 + k, x1, y1 + k, ink)
        else:
            line(b, x0 + k, y0, x1 + k, y1, ink)


def arc(b, cx, cy, rx, ry, t0, t1, n=120, ink=True):
    for t in np.linspace(t0, t1, n):
        x, y = int(round(cx + rx * np.cos(t))), int(round(cy + ry * np.sin(t)))
        if 0 <= x < W and 0 <= y < H:
            b[y, x] = ink


def staff():
    b = blank(W, H)
    thick(b, 1, 14, 15, 5, 2, vertical=True)            # shaft, lying diagonal
    arc(b, 18.5, 5, 4.3, 4.3, -2.6, 2.2)                  # crook ring
    arc(b, 18.5, 5, 3.4, 3.4, -2.6, 2.2)
    b[ell(18.5, 5, 1.6, 1.6)] = True                       # gem
    for x, y in ((23, 11), (21, 13), (10, 3), (13, 1)):
        b[y, x] = True
    return b


def spark():
    b = blank(W, H)
    poly(b, [(12, 0), (13, 6), (23, 8), (13, 9), (12, 15), (11, 9), (1, 8), (11, 6)])
    b[ell(12, 7.5, 1.4, 1.4)] = False
    b[7:9, 12] = True
    for x, y in ((3, 2), (20, 2), (4, 13), (19, 13), (2, 3)):
        b[y, x] = True
    return b


def firebolt():
    b = blank(W, H)
    b[ell(17, 7.5, 6, 6)] = True                           # head
    b[ell(17.5, 7.5, 3.3, 3.3) & ~ell(17.5, 7.5, 1.8, 1.8)] = False
    for y0, x1, y1 in ((5, 2, 2), (7, 0, 7), (9, 1, 11), (11, 4, 14), (4, 6, 1)):
        thick(b, 12, y0, x1, y1, 2, vertical=True)         # ragged tail
    for x, y in ((1, 4), (3, 9), (7, 15), (0, 14)):
        b[y, x] = True
    return b


def frost():
    b = blank(W, H)
    for k in range(6):                                     # 6-arm flake, squashed to 16 rows
        th = k * np.pi / 3
        ex, ey = 12 + 11 * np.cos(th), 7.5 + 7.4 * np.sin(th)
        line(b, 12, 7, int(round(ex)), int(round(ey)))
        for d in (5, 8):
            px, py = 12 + d * np.cos(th), 7.5 + d * 0.68 * np.sin(th)
            for s in (-1, 1):
                line(b, int(round(px)), int(round(py)),
                     int(round(px + 2.6 * np.cos(th + s * 1.0))),
                     int(round(py + 2.0 * np.sin(th + s * 1.0))))
    b[ell(12, 7.5, 2.2, 1.8)] = True
    return b


def drain():
    b = blank(W, H)
    poly(b, [(9, 15), (2, 8), (2, 4), (5, 1), (9, 3), (13, 1), (16, 4), (16, 8)])   # heart
    for t in np.linspace(0, 2.5 * np.pi, 80):              # wisp spiralling out of it
        r = 1.2 + t * 0.9
        x, y = int(round(9 + r * np.cos(t))), int(round(7 + r * 0.75 * np.sin(t)))
        if 0 <= x < W and 0 <= y < H:
            b[y, x] = not b[y, x]
    for x in range(16, 24):                                # stream leaving to the right
        y = int(round(7 + 2.5 * np.sin(x * 0.9)))
        b[y, x] = x % 3 != 2
    return b


def lightning():
    b = blank(W, H)
    poly(b, [(16, 0), (6, 8), (11, 8), (3, 15), (19, 6), (13, 6), (21, 0)])
    line(b, 15, 2, 9, 7, False)                            # inner glint
    for x, y in ((2, 2), (22, 12), (23, 14), (1, 5)):
        b[y, x] = True
    return b


def apple():
    b = blank(W, H)
    b[ell(9, 9.5, 6.5, 6)] = True
    b[ell(14.5, 9.5, 6.5, 6)] = True
    b[3:5, 11:13] = False
    thick(b, 11, 4, 13, 0, 2)
    poly(b, [(14, 3), (17, 0), (21, 0), (19, 3), (16, 4)])
    b[ell(7, 8, 1.2, 2)] = False
    return b


def potion():
    b = blank(W, H)
    b[ell(12, 10.5, 7.5, 5.5)] = True
    b[1:6, 10:14] = True
    b[0, 9:15] = True
    b[ell(12, 10.5, 5.8, 3.8) & (np.mgrid[0:H, 0:W][0] < 9)] = False   # air above liquid
    b[3:5, 11] = False
    b[ell(8.5, 10, 1, 1.6)] = False                        # glint
    return b


def scroll():
    b = blank(W, H)
    b[2:14, 3:21] = True
    b[0:4, 1:23] = True
    b[12:16, 1:23] = True
    b[1, 2:22] = False
    b[14, 2:22] = False
    for y in (5, 7, 9, 11):
        b[y, 6:18 - (y % 4)] = False
    return b


def bag():
    b = blank(W, H)
    b[ell(12, 10.5, 9.5, 5.5)] = True
    poly(b, [(8, 5), (16, 5), (14, 3), (10, 3)])
    poly(b, [(6, 0), (10, 3), (14, 3), (18, 0), (15, 2), (12, 0), (9, 2)])
    b[4, 8:16] = False
    b[3, 9:15] = True
    coin = ell(12, 10.5, 3, 2.6) & ~ell(12, 10.5, 1.8, 1.4)
    b[coin] = False
    return b


def sword():
    b = blank(W, H)
    b[6:10, 8:21] = True                                   # blade, 4 px, horizontal
    b[7:9, 21] = True
    b[6, 20] = b[9, 20] = False
    b[7, 22] = b[8, 22] = True
    b[7, 10:19] = False                                    # fuller (negative)
    b[2:14, 6:8] = True                                    # crossguard
    b[2, 6] = b[13, 7] = False
    b[7:9, 1:6] = True                                     # grip
    b[5:11, 0:2] = True                                    # pommel
    b[7:9, 3] = False
    return b


def power():
    b = blank(W, H)
    b[0:2, 11:13] = True                                   # pommel
    b[2:4, 6:18] = True                                    # crossguard
    b[4:12, 10:14] = True                                  # blade, 4 px, driven down
    b[12, 11:13] = True
    b[5:11, 11] = False                                    # fuller
    b[13:16, 0:24] = True                                  # ground slab
    b[13, 9:15] = False                                    # crater
    b[14, 10:14] = False
    line(b, 12, 15, 9, 13, False)                          # cracks
    line(b, 12, 15, 16, 13, False)
    for rx, ry, dot in ((6, 5, False), (10, 9, True)):     # shock rings, both sides
        for t in np.linspace(np.pi, 2 * np.pi, 60):
            x, y = int(round(12 + rx * np.cos(t))), int(round(12 + ry * np.sin(t)))
            if 0 <= x < W and 0 <= y < 13 and not (9 <= x <= 14) and (not dot or (x + y) % 2):
                b[y, x] = True
    for x, y in ((2, 2), (21, 1), (4, 6), (19, 6)):        # debris
        b[y, x] = True
    return b


def whirl():
    b = blank(W, H)
    for t in np.linspace(0, 4.3 * np.pi, 600):
        r = 0.75 * t
        x, y = int(round(12 + r * np.cos(t))), int(round(7.5 + r * 0.62 * np.sin(t)))
        if 0 <= x < W and 0 <= y < H:
            b[y, x] = True
            if t > 6 and x + 1 < W:
                b[y, x + 1] = True
    b[ell(12, 7.5, 1.8, 1.5)] = True
    return b


def daggers():
    b = blank(W, H)
    for k in range(2):
        line(b, 2 + k, 14, 17 + k, 2)                      # dagger 1
        line(b, 21 - k, 14, 6 - k, 2)                      # dagger 2
    over(b, "#...#\n.#.#.\n.....\n.#.#.\n#...#", 3, 9)
    over(b, "#...#\n.#.#.\n.....\n.#.#.\n#...#", 16, 9)
    b[13:16, 0:3] = True
    b[13:16, 21:24] = True
    return b


def bow():
    b = blank(W, H)
    arc(b, 10, 7.5, 8, 7.6, np.pi / 2, 3 * np.pi / 2, 200)  # limb bulging back (left)
    arc(b, 10, 7.5, 7, 7.0, np.pi / 2 + 0.2, 3 * np.pi / 2 - 0.2, 200)
    line(b, 10, 0, 10, 15)                                 # string
    b[7:9, 4:22] = True                                    # arrow
    over(b, "#...\n###.\n####\n###.\n#...", 20, 5)       # head
    b[5:11, 20] = False
    over(b, "#\n#\n#\n#\n#\n#", 21, 5)
    over(b, "#.#\n.#.\n...\n.#.\n#.#", 3, 5)              # fletching
    return b


ICONS = [("staff", staff, "yellow", True), ("spark", spark, "magenta", True),
         ("firebolt", firebolt, "red", True), ("frost", frost, "cyan", True),
         ("drain", drain, "magenta", True), ("lightning", lightning, "white", True),
         ("apple", apple, "red", True), ("potion", potion, "red", True),
         ("scroll", scroll, "white", True), ("bag", bag, "yellow", False),
         ("sword", sword, "white", True), ("power", power, "red", True),
         ("whirl", whirl, "white", True), ("daggers", daggers, "white", True),
         ("bow", bow, "yellow", False)]


def main():
    out = ["# WazHack/ZX CONCEPT round-5 bar icons 24x16 (3x2 cells) — GENERATED by",
           "# tools/concept_r5_icons.py (edit that). Unmasked opaque panel glyphs: 48 B + 1 attr.", ""]
    for n, fn, ink, br in ICONS:
        b = fn()
        assert b.shape == (H, W), n
        out.append(f"=== {n}2416 24x16 ink:{ink} paper:black{' bright' if br else ''}")
        out += ["".join("#" if v else "." for v in r) for r in b]
        out.append("")
    open(OUT, "w").write("\n".join(out))
    print(f"wrote {OUT}: {len(ICONS)} icons")


if __name__ == "__main__":
    main()
