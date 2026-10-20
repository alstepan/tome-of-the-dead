#!/usr/bin/env python3
"""ammo_preview.py — review fragment + PNGs for the D3-7 T6 dropped-ammo floor glyphs.

Source: assets/gfx/concept/grid/ammo.tiles (HISTORICAL: the old dagger/arrow stand-ins on ids 17/18; since 3E the merged AMMO glyph is id 17 from items3e.tiles and id 18 is PAGES).
Writes:
  assets/gfx/tiles/ammo.svg.html  one canvas-style SVG artboard per glyph (x8) + composed
                                  strips (air row over the floor row) on a D1 and a D5 floor,
                                  incl. the $06 arrow ink option
  <png_dir>/*.png                 the same strips (x4)
Usage: python3 tools/ammo_preview.py [--png DIR]
Review artefact only: the engine data comes from tiles_convert.py.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b10_preview as bp  # noqa: E402  (scene_svg / scene_png / artboard / figure)
import tiles_convert as tc  # noqa: E402

SRC = "ammo.tiles"
OUT = os.path.join(tc.REPO, "assets/gfx/tiles/ammo.svg.html")
AIR = (bytes(8), 0x00)
DEPTHS = {1: 0x0F, 5: 0x30}  # ATTR_FLOOR (tiles_convert.SCHEME)
W = 7                        # cells: air, daggers, air, arrows, air, arrows($06), air

GLYPHS = [
    ("daggers", "#FFFFFF", "Common id 17 T_DAGGERS, $47: two crossed leaning daggers over one "
                           "lying flat. Non-solid, flags 0."),
    ("arrows", "#D7D7D7", "Common id 18 T_ARROWS, $07 (game.md §6.3): two arrows, heads right, "
                          "lower one 1 px back. Non-solid, flags 0. Option: $06 yellow."),
]


def strip(depth: int):
    plat = (tc.live_tile("tiles_bg_platform"), DEPTHS[depth])
    d, a = tc.tile8(SRC, "daggers"), tc.tile8(SRC, "arrows")
    top = [AIR, d, AIR, a, AIR, (a[0], 0x06), AIR]
    return [[AIR] * W, top, [plat] * W]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--png")
    a = ap.parse_args()
    css = ("font-family:'Press Start 2P',monospace;background:#12121c;color:#e6e4f0;"
           "padding:24px;display:flex;flex-direction:column;gap:28px;")
    h = [f'<div style="{css}">',
         '<h2 style="margin:0;font-size:14px;">D3-7 AMMO FLOOR STACKS (DRAFT FOR REVIEW)</h2>',
         '<div style="display:flex;gap:28px;flex-wrap:wrap;align-items:flex-start;">']
    h += [bp.artboard(SRC, n, ink, note) for n, ink, note in GLYPHS]
    h += ['</div>',
          '<div style="display:flex;gap:28px;flex-wrap:wrap;">']
    h += [bp.figure(bp.scene_svg(strip(d), scale=6),
                    f"D{d}: daggers $47 · arrows $07 · arrows $06 (option)") for d in DEPTHS]
    h += ['</div>', '</div>', '']
    with open(OUT, "w") as f:
        f.write("\n".join(h))
    print("wrote", OUT)
    if a.png:
        os.makedirs(a.png, exist_ok=True)
        allrows = []
        for d in DEPTHS:
            bp.scene_png(strip(d), os.path.join(a.png, f"ammo_d{d}.png"))
            allrows += strip(d)
        bp.scene_png(allrows, os.path.join(a.png, "ammo_all.png"), scale=6)
        print("pngs ->", a.png)


if __name__ == "__main__":
    main()
