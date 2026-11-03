#!/usr/bin/env python3
"""look1_flames.py — LOOK-1 concept: flames without the colour flash (review only).

User brief 2026-11-02: drop the flame attr cycle (dt_attr_tab DT_HOT/DT_RED/DT_DIM);
flame cells keep ONE fixed attr, liveliness comes from the 2 glyph frames only.
Drop-in: same footprints as bigdecor.grid (tall torch / big brazier 2x4, slim 1x3),
bodies (cell rows below the flame) copied byte-for-byte from bigdecor.grid.

Writes  assets/gfx/concept/look1/look1_flames.grid  (bigdecor.grid block format)
        assets/gfx/concept/look1/look1_sheet.png    (4x, black, wall tiles around)
        assets/gfx/concept/look1/look1_anim.gif     (A/B alternation, recommended set)
Prints per-object tile cost: distinct (glyph, attr) cells over the shown frames.

Shapes:  TEAR  teardrop with a hollow ring + inner core (refs 14.50.17 / 14.49.39 tip twist)
         RAG   ragged split tongues with gaps (ref 14.48.37)
Colours: Y = $46 bright yellow, R = $42 bright red, RY = red tip cells over yellow
         body cells (2-cell stack; one attr per cell, so no red-with-core inside a cell).
Frame B differs from A only in the top cell row (same swap cells as today).
"""

from __future__ import annotations

import os
import re
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import concept_screen as cs  # noqa: E402

OUT = os.path.join(cs.OUT, "look1")
SRC = os.path.join(cs.GRID, "bigdecor.grid")
Y, R, D = 0x46, 0x42, 0x06
SCALE = 4

# --- flame art (rows 0..15; brazier rows 0..14, its row 15 = rim from the body) ---------
TEAR_TORCH_LO = """\
....##.##.##....
...##.####.##...
...##.####.##...
...##.####.##...
...###.##.###...
....###..###....
.....######.....
......####......"""
TEAR_TORCH_A = """\
......#.........
......##........
.......##.......
......###.......
......####......
.....#####..#...
.....######.#...
....###..###...."""
TEAR_TORCH_B = """\
.........#......
........##......
.......##.......
.......###......
......####......
...#..#####.....
...#.######.....
....###..###...."""
RAG_TORCH_LO = """\
...##.###.###...
....#.##.####...
...##.###.##....
...###.###.#....
....###.####....
....##.####.....
.....######.....
......####......"""
RAG_TORCH_A = """\
.......#........
........#.......
.......#....#...
...#...##...#...
...#..##.#.#....
....#.##.#.#....
....#.###.##....
...##..##.##...."""
RAG_TORCH_B = """\
........#.......
.......#........
...#...#........
...#..##...#....
....#.#.##.#....
....#.#.##..#...
....##.###..#...
...##..##.##...."""
# LOWER-FLAME experiment (user 2026-11-02): the lower flame cell row (rows 8..15 of the 2x4 objects) swaps
# too. B shifts the ragged gaps one column (anti-phase to the top tongues); the stem rows (torch 14..15,
# brazier 13..14 + the body rim in row 15) stay identical, so only the upper flame rows differ.
RAG_TORCH_LO_B = """\
...###.###.##...
....##.##.###...
...###.#.###....
...##.###.##....
....##.#####....
....###.###.....
.....######.....
......####......"""
RAG_BRAZ_LO_B = """\
.##.###.##.###..
..###.##.###.##.
.###.##.##.###..
.##.###.###.##..
..###.#####.##..
..############..
...##########..."""

TEAR_BRAZ_LO = """\
.##.##.##.##.##.
.##.#.####.#.##.
.##.#.####.#.##.
.##.##.##.##.##.
.###.##..##.###.
..############..
...##########..."""
TEAR_BRAZ_A = """\
......#.........
......##........
.......##.......
.#.....###......
.#....####......
.##..######..#..
.##..######..##.
.##.###..###.##."""
TEAR_BRAZ_B = """\
.........#......
........##......
.......##.......
......###.....#.
......####....#.
..#..######..##.
.##..######..##.
.##.###..###.##."""
RAG_BRAZ_LO = """\
.##.##.##.###.#.
..##.###.##.###.
.##.##.###.##.#.
.###.##.##.###..
..##.######.##..
..############..
...##########..."""
RAG_BRAZ_A = """\
....#......#....
.....#.....#....
....#.....#..#..
.#..##.#..##.#..
.#.#.#.#.#.#..#.
..##.#..##.#.##.
.##.##.##.##.##.
.#.##.###.##.#.."""
RAG_BRAZ_B = """\
.....#......#...
....#......#....
.#...#....#.....
.#..##..#.##..#.
..#.#.#.#.#.#.#.
..##.#.##..#.##.
.##.##.##.##.##.
.#.##.###.##.#.."""

SHAPES = {   # obj: {shape: (top_A, top_B, lower flame rows)}
    "torch_tall": {"tear": (TEAR_TORCH_A, TEAR_TORCH_B, TEAR_TORCH_LO),
                   "rag": (RAG_TORCH_A, RAG_TORCH_B, RAG_TORCH_LO)},
    "brazier_big": {"tear": (TEAR_BRAZ_A, TEAR_BRAZ_B, TEAR_BRAZ_LO),
                    "rag": (RAG_BRAZ_A, RAG_BRAZ_B, RAG_BRAZ_LO)},
}
COLOURS = {"y": ((Y, Y), (Y, Y)), "r": ((R, R), (R, R)), "ry": ((R, R), (Y, Y))}


def rows_of(s: str) -> list[str]:
    r = s.splitlines()
    assert all(len(x) == 16 and set(x) <= set("#.") for x in r), s
    return r


def cells_str(cells: np.ndarray) -> str:
    return ";".join(",".join(f"{int(a):02X}" for a in row) for row in cells)


def block_text(name: str, bm_rows: list[str], cells: np.ndarray) -> str:
    w, h = len(bm_rows[0]), len(bm_rows)
    return f"=== {name} {w}x{h} cells:{cells_str(cells)}\n" + "\n".join(bm_rows) + "\n"


def build_grid(src: dict) -> str:
    out = [open(__file__).read().split('"""')[1].strip().replace("\n", "\n# ").join(["# ", "\n"]),
           "# Format = assets/gfx/concept/grid/bigdecor.grid (one attr per 8x8 cell, paper black).\n"
           "# Generated by tools/look1_flames.py - edit the flame constants there.\n"]
    for obj in ("torch_slim",):
        for col, a in (("y", Y), ("r", R)):
            for k, f in (("a", "f1"), ("b", "f2")):
                b = src[f"{obj}_{f}"]
                rows = ["".join("#" if v else "." for v in r) for r in b["bm"]]
                cells = b["cells"].copy()
                cells[0, 0] = a
                out.append(block_text(f"{obj}_{col}_{k}", rows, cells))
    for obj, shapes in SHAPES.items():
        body = src[f"{obj}_f1"]
        brows = ["".join("#" if v else "." for v in r) for r in body["bm"]]
        for shape, (ta, tb, lo) in shapes.items():
            lo_r = rows_of(lo)
            for col, (top, mid) in COLOURS.items():
                for k, top_rows in (("a", ta), ("b", tb)):
                    flame = rows_of(top_rows) + lo_r
                    rows = flame + brows[len(flame):]
                    cells = body["cells"].copy()
                    cells[0, :] = top
                    cells[1, :] = mid
                    out.append(block_text(f"{obj}_{shape}_{col}_{k}", rows, cells))
    lo_b = {"torch_tall": RAG_TORCH_LO_B, "brazier_big": RAG_BRAZ_LO_B}
    for obj, shapes in SHAPES.items():           # LOWER-FLAME: top B + lower B (frame 2 of the lower variant)
        body = src[f"{obj}_f1"]
        brows = ["".join("#" if v else "." for v in r) for r in body["bm"]]
        flame = rows_of(shapes["rag"][1]) + rows_of(lo_b[obj])
        cells = body["cells"].copy()
        cells[0, :] = COLOURS["r"][0]
        cells[1, :] = COLOURS["r"][1]
        out.append(block_text(f"{obj}_rag_r_c", flame + brows[len(flame):], cells))
    return "\n".join(out)


def ids(blocks) -> int:
    return len({(g, a) for b in blocks for _, _, g, a in cs.cell_glyphs(b)})


def swaps(a, b) -> set:
    return {(cx, cy) for (cx, cy, g, _), (_, _, g2, _) in zip(cs.cell_glyphs(a), cs.cell_glyphs(b))
            if g != g2}


# --- sheet ------------------------------------------------------------------------------
def framed(b: dict, attr_override: dict | None = None) -> np.ndarray:
    """Object with one wall-tile column each side and wall rows above/below ($01 blue)."""
    wall = WALL
    wc, hc = b["w"] // 8 + 2, b["h"] // 8 + 2
    bm = np.zeros((hc * 8, wc * 8), bool)
    at = np.full((hc, wc), cs.A_WALL, np.uint8)
    for r in range(hc):
        for c in range(wc):
            if r in (0, hc - 1) or c in (0, wc - 1):
                bm[r * 8:r * 8 + 8, c * 8:c * 8 + 8] = wall
    cells = b["cells"].copy()
    for (cx, cy), a in (attr_override or {}).items():
        cells[cy, cx] = a
    bm[8:8 + b["h"], 8:8 + b["w"]] = b["bm"]
    at[1:1 + b["h"] // 8, 1:1 + b["w"] // 8] = cells
    return cs.render_rgb(bm, at)


class Canvas:
    def __init__(self, font, w):
        self.font, self.w, self.items, self.y = font, w, [], 4

    def text(self, x, y, s, col=(200, 200, 210)):
        for i, ch in enumerate(s):
            g = self.font[ch]
            img = np.zeros((8, 8, 3), np.uint8)
            img[g] = col
            self.items.append((x + i * 8, y, img))

    def row(self, groups: list[tuple[str, list[np.ndarray]]], title: str | None = None):
        if title:
            self.text(4, self.y, title, (255, 255, 120))
            self.y += 12
        x, h = 4, 0
        for cap, imgs in groups:
            gx = x
            for im in imgs:
                self.items.append((gx, self.y, im))
                gx += im.shape[1] + 2
            self.text(x, self.y + max(i.shape[0] for i in imgs) + 2, cap)
            x = max(gx, x + len(cap) * 8) + 12
            h = max(h, max(i.shape[0] for i in imgs) + 12)
        self.y += h + 6

    def render(self):
        img = np.zeros((self.y + 4, self.w, 3), np.uint8)
        for x, y, im in self.items:
            img[y:y + im.shape[0], x:x + im.shape[1]] = im
        return img


# LOOK-1 import (user-approved 2026-11-02: RAG shapes, colour R $42): the approved blocks are
# copied into bigdecor.grid as <obj>_look1_f1 / _f2 (the in-room objects, tools/tiles_convert.py
# OBJ_SPEC); the old <obj>_fN blocks stay for the menu torches (tools/menu_art.py) and the concept sheet.
APPROVED = {"torch_slim": "torch_slim_r", "torch_tall": "torch_tall_rag_r", "brazier_big": "brazier_big_rag_r"}
MERGE_MARK = "# --- LOOK-1 import (generated by tools/look1_flames.py --merge; do not edit) ---"


def merge_bigdecor() -> None:
    txt = open(os.path.join(OUT, "look1_flames.grid")).read()
    blk = {m.group(1): m.group(0) for m in re.finditer(
        r"^=== (\S+) .*?(?=^=== |\Z)", txt, re.S | re.M)}
    base = open(SRC).read().split(MERGE_MARK)[0].rstrip("\n") + "\n\n" + MERGE_MARK + "\n\n"
    for obj, pre in APPROVED.items():
        for k, f in (("a", "f1"), ("b", "f2")):
            b = blk[f"{pre}_{k}"]
            base += b.replace(f"=== {pre}_{k} ", f"=== {obj}_look1_{f} ", 1).rstrip("\n") + "\n\n"
    for obj, pre in APPROVED.items():           # LOWER-FLAME: frame 2 with the lower row B (f1 is shared)
        if obj != "torch_slim":
            b = blk[f"{pre[:-2]}_r_c"]
            base += b.replace(f"=== {pre[:-2]}_r_c ", f"=== {obj}_look2_f2 ", 1).rstrip("\n") + "\n\n"
    open(SRC, "w").write(base.rstrip("\n") + "\n")


def main() -> int:
    global WALL
    os.makedirs(OUT, exist_ok=True)
    art = cs.Art()
    WALL = art.tiles["wall"]
    src = cs.parse_blocks(SRC)
    gpath = os.path.join(OUT, "look1_flames.grid")
    open(gpath, "w").write(build_grid(src))
    L = cs.parse_blocks(gpath)
    for b in L.values():   # clash-legal by construction: paper black on every cell
        assert all((int(a) & 0x38) == 0 for a in b["cells"].flat), b["name"]

    report = []
    cv = Canvas(art.font, 4 + 6 * 34 + 5 * 14 + 40)
    # BEFORE: today's 2 shown frames x the 3 cycle attrs (cycled cells = BIG_ANIM cells)
    cv.text(4, cv.y, "BEFORE: F1/F2 X ATTR CYCLE $46 $42 $06", (255, 120, 120))
    cv.y += 12
    for obj in ("torch_slim", "torch_tall", "brazier_big"):
        cyc = cs.BIG_ANIM[obj]["cycle"]
        groups = []
        for a, nm in ((Y, "$46"), (R, "$42"), (D, "$06")):
            groups.append((nm, [framed(src[f"{obj}_{f}"], {c: a for c in cyc}) for f in ("f1", "f2")]))
        cv.row(groups, obj.upper())
        report.append(f"{obj}: today {ids([src[obj + '_f1'], src[obj + '_f2']])} ids "
                      f"(swap {sorted(swaps(src[obj + '_f1'], src[obj + '_f2']))}, "
                      f"+attr cycle on {sorted(cyc)})")
    cv.y += 6
    cv.text(4, cv.y, "AFTER: FIXED ATTR, FRAMES A/B", (120, 255, 120))
    cv.y += 12
    cv.row([(f"SLIM {c.upper()}", [framed(L[f"torch_slim_{c}_{k}"]) for k in "ab"]) for c in ("y", "r")],
           "TORCH_SLIM (GLYPHS UNCHANGED)")
    for c in ("y", "r"):
        fa, fb = L[f"torch_slim_{c}_a"], L[f"torch_slim_{c}_b"]
        report.append(f"torch_slim {c}: {ids([fa, fb])} ids, swap {sorted(swaps(fa, fb))}")
    for obj in SHAPES:
        for shape in SHAPES[obj]:
            groups = []
            for col in COLOURS:
                fa, fb = L[f"{obj}_{shape}_{col}_a"], L[f"{obj}_{shape}_{col}_b"]
                assert swaps(fa, fb) <= {(0, 0), (1, 0)}
                groups.append((f"{shape.upper()} {col.upper()}", [framed(fa), framed(fb)]))
                today = {(g, a) for f in (src[obj + "_f1"], src[obj + "_f2"])
                         for _, _, g, a in cs.cell_glyphs(f)}
                new = {(g, a) for f in (fa, fb) for _, _, g, a in cs.cell_glyphs(f)} - today
                report.append(f"{obj} {shape} {col}: {ids([fa, fb])} ids, {len(new)} new (glyph,attr) "
                              f"vs today, swap {sorted(swaps(fa, fb))}")
            cv.row(groups, f"{obj.upper()} {shape.upper()}")
    img = cv.render()
    Image.fromarray(np.kron(img, np.ones((SCALE, SCALE, 1), np.uint8))).save(
        os.path.join(OUT, "look1_sheet.png"))

    # Animation at the game's decor rate: one step per 4th 25 Hz tick = 160 ms.
    # TODAY = attr steps every step (dt_attr_tab order), glyph swap every 16th tick
    # (= every 4th step). AFTER = fixed attr, glyph A/B every step (needs the flame swap on
    # the 4-tick step instead of DT_GLYPH_HOLD 16 - engine note, not done here).
    cyc_tab = [Y, R, D, Y, R, D, Y, R]
    rows = [("TODAY", None), ("TEAR Y", ("y", "tear", "y")), ("TEAR R", ("r", "tear", "r")),
            ("TEAR RY", ("r", "tear", "ry")), ("RAG Y", ("y", "rag", "y")),
            ("RAG R", ("r", "rag", "r")), ("RAG RY", ("r", "rag", "ry"))]
    frames = []
    for step in range(8):
        cvf = Canvas(art.font, 4 + 3 * 34 + 2 * 2 + 16)
        for label, spec in rows:
            ims = []
            for obj in ("torch_slim", "torch_tall", "brazier_big"):
                if spec is None:
                    f = src[f"{obj}_f{(step // 4) % 2 + 1}"]
                    ims.append(framed(f, {c: cyc_tab[step] for c in cs.BIG_ANIM[obj]["cycle"]}))
                else:
                    k = "ab"[step % 2]
                    n = (f"torch_slim_{spec[0]}_{k}" if obj == "torch_slim"
                         else f"{obj}_{spec[1]}_{spec[2]}_{k}")
                    ims.append(framed(L[n]))
            cvf.row([(label, ims)])
        frames.append(Image.fromarray(np.kron(cvf.render(), np.ones((SCALE, SCALE, 1), np.uint8))))
    frames[0].save(os.path.join(OUT, "look1_anim.gif"), save_all=True, append_images=frames[1:],
                   duration=160, loop=0)
    print("\n".join(report))
    if "--merge" in sys.argv:
        merge_bigdecor()
    return 0


WALL = None
if __name__ == "__main__":
    sys.exit(main())
