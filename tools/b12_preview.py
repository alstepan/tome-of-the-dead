#!/usr/bin/env python3
"""b12_preview.py — review fragment + PNGs for the B12 level-exit gate (raised portcullis).

Source: assets/gfx/concept/grid/b12_gate.tiles (+ panel_r4.tiles ornament, decor.tiles candles,
live hole tiles via tiles_convert). Writes:
  assets/gfx/tiles/b12_gate.svg.html  one canvas-style SVG per glyph (x8) + composed row 14..17
                                      strips: ordinary down hole vs lair exit (open, open+glow,
                                      open+candles, closed 3F) on a D1 and a D5 floor row
  <png_dir>/*.png                     the same strips (x4)
Usage: python3 tools/b12_preview.py [--png DIR]
Review artefact only: no engine data is written (user approves first).
"""
from __future__ import annotations

import argparse
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b10_preview as bp  # noqa: E402  (scene_svg / scene_png / artboard / figure)
import tiles_convert as tc  # noqa: E402

SRC = "b12_gate.tiles"
OUT = os.path.join(tc.REPO, "assets/gfx/tiles/b12_gate.svg.html")
AIR = (bytes(8), 0x00)
W = 14                       # strip width in cells: cap, chain, hole @3..5, chain, exit @9..11, cap
HOLE_C, EXIT_C = 3, 9
DEPTHS = {1: 0x0F, 5: 0x30}  # ATTR_FLOOR (tiles_convert.SCHEME)


def orn_row(floor_attr: int):
    """Row 17 ornament: cap_l, link/bar alternating, cap_r (wing/skull block is cols 14-17)."""
    g = lambda n: (tc.tile8("panel_r4.tiles", n)[0], floor_attr)  # noqa: E731
    row = [g("orn_cap_l")] + [g("orn_link" if c % 2 else "orn_bar") for c in range(1, W - 1)]
    return row + [g("orn_cap_r")]


def strip(depth: int, state: str):
    fa = DEPTHS[depth]
    r17 = orn_row(fa)
    hole = [(tc.live_tile(f"tiles_bg_ladder_{s}"), 0x02) for s in "lmr"]
    r17[HOLE_C:HOLE_C + 3] = hole                     # ordinary room-to-room down hole
    gate = tc.tile8(SRC, {"closed": "gate_closed", "openb": "gate_raised_b"}.get(state, "gate_raised"))
    r17[EXIT_C:EXIT_C + 3] = [gate] * 3
    r16 = [AIR] * W
    if state == "glowb":
        r17[EXIT_C:EXIT_C + 3] = [tc.tile8(SRC, "gate_raised_b")] * 3
    if state in ("glow", "glowb"):
        r16[EXIT_C + 1] = tc.tile8(SRC, "gate_glow")
    elif state == "candles":
        r16[EXIT_C + 1] = tc.tile8("decor.tiles", "candles")
    return [[AIR] * W, [AIR] * W, r16, r17]


STATES = [("glowb", "APPROVED: variant B + glow"), ("openb", "variant B, no glow"),
          ("open", "rejected spec bar"), ("glow", "open + gate_glow (new id)"),
          ("candles", "open + T_CANDLES reuse (0 ids)"), ("closed", "closed, 3F (gate_closed)")]
GLYPHS = [
    ("gate_raised", "#FFFF00", "Rejected (spec bar): raised portcullis x3 over the exit hole, "
                               "$46, non-solid; rows 5-7 clear."),
    ("gate_raised_b", "#FFFF00", "APPROVED: T_GRATE id 26 (tiles_common), $46, x3 over the "
                                 "exit hole; never reads as floor on light floors."),
    ("gate_closed", "#D7D7D7", "3F closed gate, $07, solid; source only, no id yet."),
    ("gate_glow", "#FFFF00", "APPROVED marker, row 16 above the hole centre, $46; per-level id TS<d>_GLOW (58/59; D6 55)."),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--png")
    a = ap.parse_args()
    css = ("font-family:'Press Start 2P',monospace;background:#12121c;color:#e6e4f0;"
           "padding:24px;display:flex;flex-direction:column;gap:28px;")
    h = [f'<div style="{css}">',
         '<h2 style="margin:0;font-size:14px;">B12 LEVEL-EXIT GATE (USER: VARIANT B + GLOW)</h2>',
         '<div style="display:flex;gap:28px;flex-wrap:wrap;align-items:flex-start;">']
    h += [bp.artboard(SRC, n, ink, note) for n, ink, note in GLYPHS]
    h += ['</div>']
    for d in DEPTHS:
        h += [f'<h2 style="margin:0;font-size:12px;">D{d} · rows 14..17 · ordinary down hole '
              f'(cols 3-5) vs lair exit (cols 9-11)</h2>',
              '<div style="display:flex;gap:28px;flex-wrap:wrap;">']
        h += [bp.figure(bp.scene_svg(strip(d, s), scale=4), f"D{d}: {cap}") for s, cap in STATES]
        h += ['</div>']
    h += ['</div>', '']
    with open(OUT, "w") as f:
        f.write("\n".join(h))
    print("wrote", OUT)
    if a.png:
        os.makedirs(a.png, exist_ok=True)
        allrows = []
        for d in DEPTHS:
            for s, _ in STATES:
                rows = strip(d, s)
                bp.scene_png(rows, os.path.join(a.png, f"d{d}_{s}.png"))
                allrows += rows + [[AIR] * W]
        bp.scene_png(allrows, os.path.join(a.png, "b12_all.png"), scale=3)
        print("pngs ->", a.png)


if __name__ == "__main__":
    main()
