#!/usr/bin/env python3
"""b10_preview.py — review fragment + PNGs for the B10 open-door jambs and the lair grate.

Source: assets/gfx/concept/grid/b10_door_grate.tiles (+ door.tiles, live tiles via
tiles_convert). Writes:
  assets/gfx/tiles/b10_door_grate.svg.html  one canvas-style SVG per glyph (x8) + composed
                                            closed/open door and closed/open grate scenes
  <png_dir>/*.png                           the same scenes as PNG (x4)

Usage: python3 tools/b10_preview.py [--png DIR]
Review artefact only: no engine data is written (ids are the designer's call).
"""
from __future__ import annotations

import argparse
import html
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import svg_sprites  # noqa: E402
import tiles_convert as tc  # noqa: E402

SRC = "b10_door_grate.tiles"
OUT = os.path.join(tc.REPO, "assets/gfx/tiles/b10_door_grate.svg.html")

# ZX palette as hex (bright = 0xFF channels, normal = 0xD7)
def zx_hex(c: int, bright: bool) -> str:
    return "#%02X%02X%02X" % tc.rgb(c, bright)


def glyph(src: str, name: str):
    return tc.tile8(src, name)


def live(label: str, attr: int):
    return tc.live_tile(label), attr


PLAT = (bytes([0xFF, 0x10, 0x10, 0x10, 0xFF, 0x01, 0x01, 0x01]), 0x0F)   # T_PLAT, D1 floor
BRICK = (bytes([0xFF, 0x88, 0x88, 0x88, 0xFF, 0x22, 0x22, 0x22]), 0x01)  # T_BRICK lintel
AIR = (bytes(8), 0x00)


def door_scene(state: str):
    """Rows 9s-1 .. 9s+8 of one door column (storey-0 floor .. storey-1 floor), 4 cols."""
    arch_l, arch_r = glyph("door.tiles", "door_arch_l"), glyph("door.tiles", "door_arch_r")
    if state == "closed":
        l, r = glyph("door.tiles", "door_l"), glyph("door.tiles", "door_r")
    elif state == "openA":
        l, r = glyph(SRC, "door_jamb_l"), glyph(SRC, "door_jamb_r")
    elif state == "openB":
        l, r = glyph(SRC, "door_jamb_lp"), glyph(SRC, "door_jamb_r")
    else:  # today: planks -> AIR
        l = r = AIR
    rows = [[PLAT] * 4, [AIR, BRICK, BRICK, AIR], [AIR, arch_l, arch_r, AIR]]
    rows += [[AIR, l, r, AIR] for _ in range(6)]
    rows.append([PLAT] * 4)
    return rows


def grate_scene(state: str):
    g = glyph(SRC, "grate")
    hole = [live(f"tiles_bg_ladder_{s}", 0x02) for s in "lmr"]
    mid = [g] * 3 if state == "closed" else hole
    return [[AIR] * 7, [AIR] * 7, [PLAT, PLAT] + mid + [PLAT, PLAT]]


def scene_png(rows, path: str, scale: int = 4) -> None:
    img = Image.new("RGB", (len(rows[0]) * 8 * scale, len(rows) * 8 * scale))
    for cy, row in enumerate(rows):
        for cx, (gl, at) in enumerate(row):
            tc.draw_cell(img, cx * 8 * scale, cy * 8 * scale, gl, at, scale)
    img.save(path)


def scene_svg(rows, scale: int = 6) -> str:
    """Composed multi-attr preview (review only, NOT a canvas artboard)."""
    w, h = len(rows[0]) * 8, len(rows) * 8
    parts = []
    for cy, row in enumerate(rows):
        for cx, (gl, at) in enumerate(row):
            ink, paper, br = at & 7, (at >> 3) & 7, bool(at & 0x40)
            parts.append(f'<rect x="{cx*8}" y="{cy*8}" width="8" height="8" '
                         f'fill="{zx_hex(paper, br)}"/>')
            d = "".join(f"M{cx*8+x} {cy*8+y}h1v1h-1z" for y in range(8) for x in range(8)
                        if gl[y] & (0x80 >> x))
            if d:
                parts.append(f'<path d="{d}" fill="{zx_hex(ink, br)}"/>')
    return (f'<svg width="{w*scale}" height="{h*scale}" viewBox="0 0 {w} {h}" '
            f'shape-rendering="crispEdges" style="display:block">{"".join(parts)}</svg>')


def bm(src: str, name: str) -> np.ndarray:
    rows = tc.blocks(src)[name]["rows"]
    return np.array([[c == "#" for c in r] for r in rows], dtype=bool)


def artboard(src: str, name: str, ink_hex: str, note: str) -> str:
    b = bm(src, name)
    h, w = b.shape
    return ('<div style="display:flex;flex-direction:column;gap:8px;align-items:flex-start;">\n'
            '<div style="padding:8px;background:#000000;border:2px solid #26263a;">'
            f'{svg_sprites.bitmap_to_svg(b, ink_hex, scale=8)}</div>\n'
            f'<div style="font-size:11px;letter-spacing:1px;color:#a9a7b8;">'
            f'{html.escape(name.upper())} · {w}×{h}</div>\n'
            f'<div style="font-size:10px;color:#77758a;max-width:200px;">{html.escape(note)}</div>\n'
            '</div>')


def figure(svg: str, cap: str) -> str:
    return (f'<figure style="margin:0;display:flex;flex-direction:column;gap:6px;">{svg}'
            f'<figcaption style="font-size:11px;color:#a9a7b8;">{html.escape(cap)}</figcaption>'
            '</figure>')


YEL = "#D7D700"           # $06 dim yellow, canvas INK_MAP value
WHT = "#D7D7D7"           # $07 dim white: not in INK_MAP (tiles are not imported)

GLYPHS = [
    ("door_jamb_l", YEL, "Open door, left side, rows 9s+2..9s+7. Proposal A: double stroke + "
                         "open leaf edge-on + hinge strap. Non-solid, $06."),
    ("door_jamb_lp", YEL, "Proposal B (staff): plain double stroke. Same id as A; pick one."),
    ("door_jamb_r", YEL, "Open door, right side. Non-solid, $06."),
    ("grate", WHT, "T_GRATE id 26, over the down-exit hole in row 17, x3. $07, solid while "
                   "closed."),
]

SCENES_DOOR = [("closed", "closed (today)"), ("air", "open today: planks -> AIR (B10 bug)"),
               ("openA", "open, proposal A (leaf)"), ("openB", "open, proposal B (plain)")]
SCENES_GRATE = [("closed", "lair exit, grate closed"), ("open", "boss dead: hole (T_HOLE_L/M/R)")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--png", help="write PNG previews into this dir")
    a = ap.parse_args()
    css = ("font-family:'Press Start 2P',monospace;background:#12121c;color:#e6e4f0;"
           "padding:24px;display:flex;flex-direction:column;gap:28px;")
    h = [f'<div style="{css}">',
         '<h2 style="margin:0;font-size:14px;">B10 OPEN DOOR + LAIR GRATE (DRAFT)</h2>',
         '<div style="display:flex;gap:28px;flex-wrap:wrap;align-items:flex-start;">']
    h += [artboard(SRC, n, ink, note) for n, ink, note in GLYPHS]
    h += ['</div>', '<h2 style="margin:0;font-size:12px;">DOOR IN CONTEXT · rows 9s-1..9s+8</h2>',
          '<div style="display:flex;gap:28px;flex-wrap:wrap;">']
    h += [figure(scene_svg(door_scene(s)), cap) for s, cap in SCENES_DOOR]
    h += ['</div>', '<h2 style="margin:0;font-size:12px;">GRATE IN CONTEXT · rows 15..17</h2>',
          '<div style="display:flex;gap:28px;flex-wrap:wrap;">']
    h += [figure(scene_svg(grate_scene(s)), cap) for s, cap in SCENES_GRATE]
    h += ['</div>', '</div>', '']
    with open(OUT, "w") as f:
        f.write("\n".join(h))
    print("wrote", OUT)
    if a.png:
        os.makedirs(a.png, exist_ok=True)
        for s, _ in SCENES_DOOR:
            scene_png(door_scene(s), os.path.join(a.png, f"door_{s}.png"))
        for s, _ in SCENES_GRATE:
            scene_png(grate_scene(s), os.path.join(a.png, f"grate_{s}.png"))
        # one strip with everything side by side for a quick look
        rows = []
        door = [door_scene(s) for s, _ in SCENES_DOOR]
        for y in range(10):
            r = []
            for d in door:
                r += d[y] + [AIR]
            rows.append(r)
        g = [AIR] * 2 + grate_scene("closed")[2] + [AIR] + grate_scene("open")[2] + [AIR] * 3
        rows += [[AIR] * len(rows[0]), g[:len(rows[0])]]
        scene_png(rows, os.path.join(a.png, "b10_all.png"))
        print("pngs ->", a.png)


if __name__ == "__main__":
    main()
