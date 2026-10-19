#!/usr/bin/env python3
"""dec1_preview.py — review fragment + validation for the DEC1 dead-skeleton BONES strip.

Source: assets/gfx/concept/grid/bones.tiles (block "bones" 32x8, cells $47 x4). Writes:
  assets/gfx/tiles/dec1_bones.svg.html  canvas-style artboard of the strip ('DEC1 bones'),
                                        the 4 cells with their common ids, and the strip on
                                        a black standing row over a T_PLAT row in each of the
                                        8 ATTR_FLOOR values (tiles_convert.SCHEME), x4 and x1
  <png_dir>/dec1_bones.png              all 8 scenes stacked (x4), if --png
Validation (exit 1 on failure): every cell attr $47; the 4 cells split to 8x8 tiles and packed
through tools/gfx_convert.py --mode tile (clash: one ink+paper per tile), decoded back from the
emitted DEFB == the grid (round-trip); spine continuity across the 3 cell edges.
Usage: python3 tools/dec1_preview.py [--png DIR]
Review artefact only: no engine data is written (staff wires ids 13,15,16,31 after approval).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b10_preview as bp  # noqa: E402  (scene_svg / scene_png / artboard / figure / PLAT)
import tiles_convert as tc  # noqa: E402

SRC, NAME = "bones.tiles", "bones"
OUT = os.path.join(tc.REPO, "assets/gfx/tiles/dec1_bones.svg.html")
IDS = [13, 15, 16, 31]                 # screen order left->right (NOT contiguous: BONES_IDS)
AIR = (bytes(8), 0x00)
PLAT_G = bp.PLAT[0]                    # T_PLAT glyph; attr = per-level ATTR_FLOOR
W = 6                                  # scene width: air, 4 bones cells, air


def cells():
    return tc.cells_of(SRC, NAME)[0]


def scene(floor_attr: int):
    return [[AIR] * W, [AIR] + cells() + [AIR], [(PLAT_G, floor_attr)] * W]


def validate() -> list[str]:
    errs = list(tc.errors)
    cs = cells()
    errs += [f"cell {i} attr ${a:02X} != $47" for i, (_, a) in enumerate(cs) if a != 0x47]
    rows = tc.blocks(SRC)[NAME]["rows"]
    for e in (7, 15, 23):              # glyph must touch across each cell edge (one pile)
        if not any(rows[y][e] == "#" and rows[y2][e + 1] == "#"
                   for y in range(8) for y2 in range(max(0, y - 1), min(8, y + 2))):
            errs.append(f"no ink touching across cols {e}|{e + 1}")
    with tempfile.TemporaryDirectory() as td:
        grid = os.path.join(td, "bones8.grid")
        with open(grid, "w") as f:
            for i, tid in enumerate(IDS):
                f.write(f"=== bones_{i}_id{tid} ink:white paper:black bright\n")
                f.write("\n".join(r[i * 8:i * 8 + 8] for r in rows) + "\n\n")
        asm = os.path.join(td, "bones8.asm")
        r = subprocess.run([sys.executable, os.path.join(tc.REPO, "tools/gfx_convert.py"),
                            "--mode", "tile", "--in", grid, "--name", "bones", "--out", asm,
                            "--date", "review"], capture_output=True, text=True)
        if r.returncode:
            errs.append("gfx_convert: " + r.stderr.strip())
        else:
            print(r.stdout.strip())
            for i, tid in enumerate(IDS):
                got = tc.asm_bytes(asm, f"bones_bones_{i}_id{tid}")
                if got[:8] != cs[i][0]:
                    errs.append(f"round-trip mismatch tile {i} (id {tid})")
    return errs


GLYPH_NOTE = ("DRAFT DEC1: dead skeleton lying on the floor line, skull left, ribs, pelvis, "
              "femur. 4 cells, all $47; common ids 13,15,16,31 left->right.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--png")
    a = ap.parse_args()
    errs = validate()
    if errs:
        print("\n".join("ERROR: " + e for e in errs), file=sys.stderr)
        sys.exit(1)
    print("round-trip: OK (4 tiles), attrs: $47 x4, edges 7|8 15|16 23|24 touch")
    css = ("font-family:'Press Start 2P',monospace;background:#12121c;color:#e6e4f0;"
           "padding:24px;display:flex;flex-direction:column;gap:28px;")
    h = [f'<div style="{css}">',
         '<h2 style="margin:0;font-size:14px;">DEC1 BONES (DRAFT FOR REVIEW)</h2>',
         '<div style="display:flex;gap:28px;flex-wrap:wrap;align-items:flex-start;">',
         bp.artboard(SRC, NAME, "#FFFFFF", GLYPH_NOTE)]
    for i, (g, at) in enumerate(cells()):
        h.append(bp.figure(bp.scene_svg([[(g, at)]], scale=8), f"id {IDS[i]} · ${at:02X}"))
    h += ['</div>']
    for scale in (4, 1):
        h += [f'<h2 style="margin:0;font-size:12px;">x{scale} · standing row (black) over a '
              f'T_PLAT row in each ATTR_FLOOR</h2>',
              '<div style="display:flex;gap:20px;flex-wrap:wrap;">']
        h += [bp.figure(bp.scene_svg(scene(fa), scale=scale), f"D{d} ${fa:02X}")
              for d, (fa, _) in enumerate(tc.SCHEME, 1)]
        h += ['</div>']
    h += ['</div>', '']
    with open(OUT, "w") as f:
        f.write("\n".join(h))
    print("wrote", OUT)
    if a.png:
        os.makedirs(a.png, exist_ok=True)
        allrows = []
        for fa, _ in tc.SCHEME:
            allrows += scene(fa)
        bp.scene_png(allrows, os.path.join(a.png, "dec1_bones.png"), scale=4)
        print("png ->", os.path.join(a.png, "dec1_bones.png"))


if __name__ == "__main__":
    main()
