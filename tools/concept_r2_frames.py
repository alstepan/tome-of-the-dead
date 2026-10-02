#!/usr/bin/env python3
"""concept_r2_frames.py — deterministic authoring of the CONCEPT round-2 sprite frames.

Writes assets/gfx/concept/grid/r2_frames.grid (2-state block format, read by
tools/concept_screen.py, which derives the 3-state F8 masks). Same method as
tools/gen_missing_frames.py: hand-typed rows + explicit, reviewable edits (row
pastes, leans, flips, rotations) on existing canvas frames. No AI raster.

  new monsters  zombie, mummy, orc (hand-typed torso + 2 leg sets),
                skeleton archer (skeleton frames + bow), necromancer (wizard
                frames + cowl + skull staff), giant spider (polyline legs)
  hero          wizard_staffswing (from wizard_cast2: fist + staff + swoosh)
  projectile    axe_spin1..4 (one hand-typed frame, rotated 90 deg steps)

Every frame faces RIGHT (the engine mirrors at load, F8). Header token ax:N =
anchor (draw_x = body_x - ax), multiple of 4, prototype.md §5.3.

Usage: python3 tools/concept_r2_frames.py     (then tools/concept_screen.py)
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gfx_convert  # noqa: E402
from gen_missing_frames import (T, blank, paste, over, lean, fit, trim,  # noqa: E402
                                line, poly)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPR = os.path.join(REPO, "assets/gfx/sprites/grid")
OUT = os.path.join(REPO, "assets/gfx/concept/grid/r2_frames.grid")

FRAMES: list[tuple[str, np.ndarray, str, int, str]] = []   # name, bm, ink spec, ax, note


def src(name: str) -> np.ndarray:
    fg, _so, _w, _h = gfx_convert.parse_grid_text_mask(
        open(os.path.join(SPR, name + ".grid")).read(), None, None)
    return fg.copy()


def add(name: str, bm: np.ndarray, ink: str, ax: int = 0, note: str = "") -> None:
    h, w = bm.shape
    assert w % 8 == 0 and h % 8 == 0 and w <= 40, (name, w, h)
    assert ax % 4 == 0 and 0 <= ax <= 8, (name, ax)
    FRAMES.append((name, bm, ink, ax, note))


def R(w: int, rows: list) -> np.ndarray:
    """Rows from inclusive x spans: [[(x0, x1), ...], ...] (no hand-counting)."""
    b = blank(w, len(rows))
    for y, spans in enumerate(rows):
        for x0, x1 in spans:
            b[y, x0:x1 + 1] = True
    return b


def stack(*parts: np.ndarray) -> np.ndarray:
    return np.vstack(parts)


def dead_from(bm: np.ndarray, w: int = 32, h: int = 16, drop_every: int = 3,
              row_keep: int = 2) -> np.ndarray:
    """Lying corpse: turn the standing frame onto its back (head left -> right
    for a fall backwards = rot90 clockwise), then thin it to fit w x h by
    dropping every `drop_every`-th column and keeping 1 of `row_keep` rows."""
    r = trim(np.rot90(trim(bm), -1))            # k=-1: head (top) -> right side
    r = r[:, [c for c in range(r.shape[1]) if c % drop_every != drop_every - 1]]
    if r.shape[0] % row_keep:
        r = np.vstack([r, np.zeros((row_keep - r.shape[0] % row_keep, r.shape[1]), bool)])
    r = r.reshape(-1, row_keep, r.shape[1]).any(1)   # OR row pairs: squash flat
    r = trim(r)
    out = blank(w, h)
    paste(out, r[-h:, :w], (w - min(w, r.shape[1])) // 2, h - min(h, r.shape[0]))
    return out


# ---------------------------------------------------------------------------
# Shared legs (rows 30..47 of a 24x48 tall monster)
# ---------------------------------------------------------------------------

LEGS_STRIDE = T("""
......##########........
......##########........
......####..####........
.....####...####........
.....###.....####.......
....####.....####.......
....###.......###.......
....###.......####......
...####........###......
...###.........###......
...###.........####.....
..####..........###.....
..###...........###.....
..###...........####....
..###............###....
.####............####...
#####............######.
####.............######.
""")

LEGS_PASS = T("""
.......#########........
.......#########........
.......###..####........
.......###..####........
.......###..###.........
......####..###.........
......###...###.........
......###..####.........
......###..###..........
......###..###..........
......###..###..........
......###..###..........
......###..###..........
......###..###..........
......###..###..........
.....####.####..........
...######.######........
...######.######........
""")


def bandage(bm: np.ndarray, y0: int, y1: int, step: int = 4, phase: int = 0) -> None:
    """Mummy wraps: diagonal paper lines (/), one every `step` px, rows y0..y1-1."""
    for y in range(y0, y1):
        for x in range(bm.shape[1]):
            if (x + y + phase) % step == 0 and bm[y, x]:
                # keep the silhouette edge: only carve interior pixels
                if 0 < x < bm.shape[1] - 1 and bm[y, x - 1] and bm[y, x + 1]:
                    bm[y, x] = False


# ---------------------------------------------------------------------------
# Zombie (24x48, dim green): hunched, both arms reaching forward, ragged shirt
# ---------------------------------------------------------------------------

ZOMBIE_TOP = T("""
........................
........................
.........#####..........
........########........
.......##########.......
.......###########......
.......#######..##......
.......#######..##......
.......###########......
........###.#.#.##......
........#########.......
.........#.#.#.#........
.........#######........
..........#####.........
........#########.......
.......###########......
......##############.#.#
......##################
......#####.............
......###.##############
......####.#############
......#####.......#.#.#.
......##.###............
......#..###............
......#######...........
......#######...........
......########..........
.....#########..........
.....##.##.##...........
.....#..#..#............
""")


def zombie() -> dict:
    w1 = stack(ZOMBIE_TOP, LEGS_STRIDE)
    w2 = stack(ZOMBIE_TOP, LEGS_PASS)
    w2 = lean(w2, 0, 30, 1)                              # shamble: torso sways
    # attack: lunge, arms clawing 8 px further (32 wide, ax 0)
    a = fit(lean(stack(ZOMBIE_TOP, LEGS_STRIDE), 0, 30, 3), 32, 48)
    over(a, """
##########
#########.#.#
######....###
""".replace(" ", ""), 22, 16)
    over(a, """
###########
##########.#
#####......#.#
""", 22, 19)
    hurt = lean(w1, 2, 30, -3)
    dead = dead_from(stack(ZOMBIE_TOP, LEGS_PASS), 32, 24, 3, 1)
    return {"zombie_walk1": w1, "zombie_walk2": w2, "zombie_claw": a,
            "zombie_hurt": hurt, "zombie_dead": dead}


# ---------------------------------------------------------------------------
# Mummy (24x48, dim yellow = linen): one arm forward, trailing wrap, bandages
# ---------------------------------------------------------------------------

MUMMY_TOP = T("""
........................
........................
.........#####..........
........#######.........
.......#########........
.......##########.......
.......#######..#.......
.......#######..#.......
.......##########.......
.......##########.......
........########........
.........#######........
..........#####.........
.......##########.......
......############......
......############......
.....#################..
.....##################.
.....####.#########.#.#.
....#.####..............
...#..#####.............
..#...######............
.#....######............
......#######...........
......#######...........
......#######...........
......#######...........
......#######...........
......########..........
......########..........
""")


def mummy() -> dict:
    def body(legs):
        b = stack(MUMMY_TOP, legs)
        bandage(b, 2, 46, 4, 0)
        over(b, "oo\noo", 13, 6)                          # eye socket stays open
        over(b, "##", 13, 7)
        return b
    w1, w2 = body(LEGS_STRIDE), body(LEGS_PASS)
    w2 = lean(w2, 0, 30, -1)
    a = fit(body(LEGS_STRIDE), 32, 48)                    # strangle: both arms out
    over(a, """
#########
##.######.#
#########.##
""", 18, 16)
    over(a, """
#########
.###.####.#
""", 17, 20)
    hurt = lean(w1, 2, 30, -3)
    # dead: a crumbled heap of wraps (24x16), hand-typed
    dead = T("""
........................
........................
........................
........................
........................
.........#.......#......
........#.#.....#.......
.......#..##...##.......
......#.##.##.#.##......
.....##.#.####.#.##.....
....#.##.#.##.#.#.##....
...#.#.##.#..#.#.#.##...
..##.#.#.##.##.#.#.#.#..
.#.##.#.#.##.#.##.#.##..
#.#.#.##.#.#.#.#.##.#.#.
########################
""")
    return {"mummy_walk1": w1, "mummy_walk2": w2, "mummy_grab": a, "mummy_hurt": hurt,
            "mummy_dead": dead}


# ---------------------------------------------------------------------------
# Orc (24x48, bright green): horned helm, tusks, broad, cleaver on the shoulder
# ---------------------------------------------------------------------------

ORC_HEAD = T("""
...#..........#.........
...##........##.........
....##.#####.##.........
.....##########.........
.....##########.........
.....##########.........
.....#.#.#.#.##.........
....############........
....#########.##........
....#############.......
....##############......
.....########.#.#.......
.....#########.##.......
......#########.........
""")
_belt = [(x, x) for x in range(7, 16, 2)]
ORC_TOP = np.vstack([ORC_HEAD, R(24, [
    [(4, 16)], [(2, 18)],
    [(1, 5), (7, 15), (17, 20)], [(1, 5), (7, 15), (17, 20)], [(1, 5), (7, 15), (17, 20)],
    [(1, 4), (7, 15), (18, 20)], [(1, 4), (7, 15), (18, 20)],
    [(1, 4)] + _belt + [(18, 21)],
    [(1, 5), (7, 15), (17, 21)], [(2, 4), (7, 15), (18, 20)],
    [(7, 16)], [(6, 17)], [(6, 10), (12, 17)], [(6, 9), (13, 17)], [(6, 9), (13, 17)],
    [(6, 10), (13, 18)]])])

CLEAVER = T("""
.####
#####
#####
#####
####.
.##..
...#.
...#.
...#.
...#.
...#.
...#.
...#.
...#.
...#.
...#.
""")


def orc() -> dict:
    def body(legs):
        b = stack(ORC_TOP, legs)
        paste(b, CLEAVER, 19, 5)                           # haft x 22 into the front fist
        return b
    w1, w2 = body(LEGS_STRIDE), body(LEGS_PASS)
    w2 = lean(w2, 0, 30, 1)
    # chop: cleaver swung down in front (32 wide, ax 0)
    a = fit(stack(ORC_TOP, LEGS_STRIDE), 40, 48)          # forward overhang 16 px (max)
    a[16:24, 16:24] = False                               # front arm swings out
    for k in range(3):
        line(a, 16, 15 + k, 23, 18 + k)
    over(a, "####\n####\n####\n.##.", 23, 17)              # fist
    line(a, 27, 19, 34, 19)                               # haft forward
    over(a, """
o.......
o#######
o#######
o#######
o#######
o######.
o#####..
""", 28, 20)                                              # blade hangs: end of the chop
    over(a, "#..#..#", 26, 12)                             # swing marks
    over(a, ".#..#..#", 30, 14)
    hurt = lean(w1, 0, 30, -3)
    dead = dead_from(body(LEGS_PASS), 32, 24, 3, 1)
    return {"orc_walk1": w1, "orc_walk2": w2, "orc_chop": a, "orc_hurt": hurt,
            "orc_dead": dead}


# ---------------------------------------------------------------------------
# Skeleton archer (white bright): the skeleton's own frames + a bow.
# hurt / dead REUSE skeleton_hurt / skeleton_collapsed (0 new ids).
# ---------------------------------------------------------------------------

BOW_V = T("""
##...
.#...
.##..
..#..
..##.
..##.
...##
...##
...##
...##
...##
...##
..##.
..##.
..#..
.##..
.#...
##...
""")


def skeleton_archer() -> dict:
    out = {}
    for k in (1, 2):
        b = src(f"skeleton_walk{k}")
        paste(b, BOW_V, 15, 12)                         # bow carried low in the front hand
        line(b, 15, 12, 15, 29)                          # string
        out[f"skelarch_walk{k}"] = b
    # draw: arm straight forward, bow vertical at x 24..28, string to the jaw
    base = src("skeleton_walk2")
    d = fit(base, 32, 48)
    over(d, "oooooooooooooooooo", 10, 17)                # (no other arms on these rows)
    line(d, 11, 18, 25, 18)                              # front arm
    line(d, 11, 19, 24, 19)
    paste(d, BOW_V, 24, 9)
    line(d, 24, 9, 13, 18)                               # string pulled to the cheek
    line(d, 24, 26, 13, 19)
    line(d, 13, 18, 31, 18)                              # nocked arrow (shaft)
    over(d, "#\n##\n#", 31, 17)
    s = fit(base, 32, 48)                                # shoot: string snaps back
    over(s, "oooooooooooooooooo", 10, 17)
    line(s, 11, 18, 25, 18)
    line(s, 11, 19, 24, 19)
    paste(s, BOW_V, 24, 9)
    line(s, 24, 9, 24, 26)
    over(s, "#.#\n.#.\n#.#", 28, 6)                      # twang marks
    out["skelarch_draw"] = d
    out["skelarch_shoot"] = s
    return out


# ---------------------------------------------------------------------------
# Necromancer (magenta): wizard frames re-hatted with a cowl, skull-topped staff
# ---------------------------------------------------------------------------

COWL = R(24, [
    [(6, 9)], [(5, 10)], [(4, 11)], [(4, 12)], [(4, 13)], [(4, 14)],
    [(4, 9), (15, 15)], [(4, 8), (15, 15)], [(4, 8), (11, 11), (13, 13), (15, 15)],
    [(4, 8), (15, 15)], [(4, 9), (14, 15)], [(4, 10), (13, 16)], [(4, 17)], [(5, 16)]])

SKULL = T("""
.#####.
#######
#.##.##
#..#..#
#######
.#.#.#.
.#####.
""")


def _cowl(b: np.ndarray, dx: int = 0) -> np.ndarray:
    b = b.copy()
    b[0:14, max(0, 2 + dx):18 + dx] = False                # drop the pointed hat
    paste(b, COWL, dx, 0)
    return b


def necromancer() -> dict:
    out = {}
    for k in (1, 2):
        b = _cowl(src(f"wizard_walk{k}"))
        b[0:12, 18:24] = False                            # staff crook -> skull
        paste(b, SKULL, 17, 1)
        line(b, 20, 8, 20, 12)
        out[f"necro_walk{k}"] = b
    c = src("wizard_cast2")
    c = _cowl(c)
    over(c, "#..#..#\n.#.#.#.\n..###..", 25, 15)          # dark sparks over the palm
    out["necro_cast"] = c
    h = src("wizard_hurt")                                 # 32 wide, ax 8: hat at x 8+
    h[0:14, 0:23] = False
    paste(h, COWL, 4, 0)
    out["necro_hurt"] = h
    d = src("wizard_dead")                                 # 40x16, ax 8: hat at the right end
    d[:, 31:] = False
    hood = trim(np.rot90(COWL, -1))
    paste(d, hood, 28, 16 - hood.shape[0])
    out["necro_dead"] = d
    return out


# ---------------------------------------------------------------------------
# Giant spider (32x24, red): body ellipses + 8 polyline legs
# ---------------------------------------------------------------------------

def _spider(legs, rear: int = 0) -> np.ndarray:
    b = blank(32, 24)
    poly(b, [(1, 12 - rear), (4, 8 - rear), (10, 7 - rear), (15, 9 - rear), (17, 13 - rear),
             (14, 17 - rear), (8, 18 - rear), (3, 16 - rear)])          # abdomen
    poly(b, [(17, 11 - rear), (22, 10 - rear), (25, 12 - rear), (24, 16 - rear),
             (19, 17 - rear)])                                          # head+thorax
    over(b, "o.o\n.o.\no.o", 7, 11 - rear)                              # hourglass mark
    over(b, "o.o", 21, 12 - rear)                                       # eyes
    over(b, "#.\n.#\n#.", 25, 15 - rear)                                # fangs
    b[:, 17] &= ~(np.arange(b.shape[0]) == 14 - rear)                   # waist notch
    for pts in legs:
        (hx, hy), (kx, ky), (fx, fy) = pts
        line(b, hx, hy, kx, ky)
        line(b, hx + 1, hy, kx + 1, ky)                   # thick femur
        line(b, kx, ky, fx, fy)
    return b


def spider() -> dict:
    # each leg: hip -> knee (high) -> foot (ground row 23)
    walk1 = [[(21, 11), (26, 1), (31, 23)], [(19, 11), (22, 0), (25, 23)],
             [(15, 9), (11, 0), (9, 23)], [(12, 9), (5, 1), (1, 23)]]
    walk2 = [[(21, 11), (25, 0), (28, 23)], [(19, 11), (23, 1), (22, 23)],
             [(15, 9), (10, 1), (13, 23)], [(12, 9), (6, 0), (4, 23)]]
    w1, w2 = _spider(walk1), _spider(walk2)
    # attack: rear up, front pair raised forward
    att = [[(21, 8), (25, 0), (31, 6)], [(19, 8), (27, 2), (30, 12)],
           [(15, 6), (11, 0), (9, 23)], [(12, 6), (5, 1), (1, 23)]]
    a = _spider(att, rear=3)
    hurt = np.roll(w2, (1, -2), (0, 1))
    hurt[:1] = False
    hurt[:, -2:] = False                                  # drop the wrapped columns
    dead = blank(32, 16)                                  # on its back, legs curled up
    flipped = np.flipud(_spider([[(20, 12), (23, 15), (21, 18)], [(19, 12), (20, 16), (17, 18)],
                                 [(17, 12), (14, 15), (15, 18)], [(16, 12), (11, 15), (9, 18)]]))
    paste(dead, trim(flipped), 2, 16 - trim(flipped).shape[0])
    return {"spider_walk1": w1, "spider_walk2": w2, "spider_bite": a, "spider_hurt": hurt,
            "spider_dead": dead}


# ---------------------------------------------------------------------------
# Wizard staff swing (hero, 40x48, ax 0) — consistent with wizard_cast2
# ---------------------------------------------------------------------------

def wizard_staffswing() -> np.ndarray:
    b = fit(src("wizard_cast2"), 40, 48)
    b[16:28, 24:32] = False                               # open palm -> fist
    over(b, """
.###.
#####
#####
#####
.###.
""", 23, 18)
    # staff: from behind the fist (butt) down-forward to the head (2 px thick)
    line(b, 21, 16, 37, 36)
    line(b, 22, 16, 38, 36)
    over(b, """
.###.
##.##
#...#
#....
.#...
""", 33, 35)                                              # hooked head (crook)
    # swoosh: dotted arc of the swing's path, above and ahead of the staff
    for t in np.linspace(-1.45, 0.55, 22):
        x = int(round(23 + 16 * np.cos(t)))
        y = int(round(20 + 19 * np.sin(t)))
        if 0 <= x < 40 and 0 <= y < 48:
            b[y, x] = True
    for t in np.linspace(-1.3, 0.35, 12):
        x = int(round(23 + 12 * np.cos(t)))
        y = int(round(20 + 15 * np.sin(t)))
        b[y, x] = True
    return b


# ---------------------------------------------------------------------------
# Thrown axe: one hand-typed frame, rotated in 90-degree steps (4-frame spin)
# ---------------------------------------------------------------------------

AXE = T("""
................
........###.....
.......#####....
......#######...
.......#######..
........#######.
.......##.######
......##...#####
.....##.....####
....##.......##.
...##...........
..##............
.##.............
##..............
................
................
""")


def axe_spin() -> dict:
    return {f"axe_spin{i + 1}": np.rot90(AXE, -i).copy() for i in range(4)}


# ---------------------------------------------------------------------------

INK = {
    "zombie": "ink:green paper:black", "mummy": "ink:yellow paper:black",
    "orc": "ink:green paper:black bright", "skelarch": "ink:white paper:black bright",
    "necro": "ink:magenta paper:black bright", "spider": "ink:red paper:black bright",
    "wizard": "ink:cyan paper:black bright", "axe": "ink:white paper:black bright",
}
AX = {"necro_hurt": 8, "necro_dead": 8}


def build() -> None:
    for group in (zombie(), mummy(), orc(), skeleton_archer(), necromancer(), spider(),
                  {"wizard_staffswing": wizard_staffswing()}, axe_spin()):
        for name, bm in group.items():
            add(name, bm.astype(bool), INK[name.split("_")[0]], AX.get(name, 0))


def write() -> None:
    lines = ["# WazHack/ZX CONCEPT round-2 sprite frames — GENERATED by tools/concept_r2_frames.py",
             "# (edit that script). 2-state block format: '=== name WxH ink:<c> paper:black",
             "# [bright] ax:N' + H rows ('#' ink, '.' paper). tools/concept_screen.py derives the",
             "# 3-state F8 masks into grid/sprites/. All frames face right. DRAFT for review.", ""]
    for name, bm, ink, ax, _note in FRAMES:
        h, w = bm.shape
        lines.append(f"=== {name} {w}x{h} {ink} ax:{ax}")
        lines += ["".join("#" if v else "." for v in row) for row in bm]
        lines.append("")
    open(OUT, "w").write("\n".join(lines))


if __name__ == "__main__":
    build()
    write()
    print(f"wrote {OUT}: {len(FRAMES)} frames")
