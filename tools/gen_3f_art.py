#!/usr/bin/env python3
"""gen_3f_art.py — Stage 3F task A1: the LEAN 3F monster frames (DRAFTS).

Deterministic pixel art (no AI raster) for the user's review on the Design
canvas. Rulings: docs/design/game.md §9.1 roster, §9.7 R1-R6 (Orc 3 frames,
HURT = hit flash, one shared humanoid DEAD, only Goblin/Skeleton climb, NO
Archer SHOOT art), §11.1, docs/design/pool_spike.md (sizes, stand-ins).

Frames (all face right; the engine mirrors):
  SPIDER       WALK 1 (MOT, rest) 32x16, WALK 2 32x16, BITE 40x16
  ORC          WALK 1 (MOT, rest) 24x48, WALK 2 24x48, ATTACK 32x48
  NECROMANCER  WALK 1 (MOT, rest) 24x48, WALK 2 24x48, CAST 32x48
               (Vampire and Archmage are drawn with these frames)
  MUMMY        WALK 1 (MOT, rest) 24x48, WALK 2 24x48, ATTACK 32x48
  OGRE         WALK 1 (MOT, rest) 32x48, WALK 2 32x48, SLAM 40x48
  DEATH KNIGHT WALK 1 (MOT, rest) 24x48, WALK 2 24x48, CLEAVE 40x48, BLOCK 32x48
  DEAD         HUMANOID 40x16 (shared by every new humanoid kind)
  NECRO BOLT   FLY 1 16x8, FLY 2 16x8, HIT 16x16 (Death Bolt = same frames)
Walk cycles are 2 entries (MOVECYC2: WALK 1 = MOT, WALK 2 = WK0;
docs/conventions.md 'Walk cycles').

Tiles (game.md §9.7 R2): lectern 2x2 = common ids 15 TL / 16 TR / 17 BL /
18 BR (pixels verbatim from the approved concept decor_r4.grid 'lectern',
attrs $43 top / $06 bottom) and T_GRATE_SHUT = 13 (the B12 'gate_closed'
source glyph, b12_gate.tiles, attr $07).

Outputs (this tool owns sprites/index_3f.asm (INCLUDEd by index.asm); it does NOT touch index.asm, src/frames.asm,
SRC6_KINDS or any layout file: T13 wires the frames in):
  assets/gfx/sprites/grid/<name>.grid      3-state grids (svg_sprites format)
  assets/gfx/sprites/<name>.asm            gfx_convert --layout native output
  assets/gfx/sprites/grid/tiles_3f.grid    lectern + closed grate (tile mode), and
  assets/gfx/sprites/tiles_3f.asm          written by svg_sprites.import_tiles from the
                                           fragment's '3F TILES' section (TILE_ATTR attrs)
  assets/gfx/source/3f_frames.svg.html     canvas-convention fragment for review
  --png-dir DIR                            PNG previews (review only)

Validation (exit != 0 on failure): the fragment re-parses with the canvas
importer to the same bitmaps; canvas + fragment run through the REAL
importer (svg_sprites.import_sheet -> gfx_convert -> DEFB decode: clash +
data/mask round-trip) in a temp dir; the committed asm is decoded again and
compared; per-group ZX0 blocks (zx0_sources.partition, dzx0 round-trip) vs
the pool_spike stand-in packed size + 10 %.

Usage: python3 tools/gen_3f_art.py [--png-dir DIR] [--check]
"""

from __future__ import annotations

import argparse
import html
import os
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gfx_convert as GC  # noqa: E402
import svg_sprites as S  # noqa: E402
import zx0_sources as ZS  # noqa: E402

REPO = S.REPO
SPR = os.path.join(REPO, "assets/gfx/sprites")
GRID_DIR = os.path.join(SPR, "grid")
FRAGMENT = os.path.join(REPO, "assets/gfx/source/3f_frames.svg.html")
TILE_ASM = os.path.join(SPR, "tiles_3f.asm")      # written by svg_sprites.import_tiles
CONCEPT = os.path.join(REPO, "assets/gfx/concept/grid")
GEN_DATE = "2026-10-28"
SCALE = 4


def art(text: str, w: int) -> np.ndarray:
    """Rows of '#' (ink) / '.' (paper); an optional 'NN|' row prefix is ignored.
    Rows may be short (right-padded with paper) but never wider than w."""
    rows = []
    for r in text.strip("\n").splitlines():
        r = r.strip()
        r = r.split("|", 1)[1] if "|" in r else r
        if len(r) > w:
            raise ValueError(f"row {len(rows)} wider than {w}: {r!r}")
        rows.append([c == "#" for c in r.ljust(w, ".")])
    return np.array(rows, bool)


def stack(*parts: np.ndarray) -> np.ndarray:
    return np.vstack(parts)


def blank(w: int, h: int) -> np.ndarray:
    return np.zeros((h, w), bool)


# ===========================================================================
# drawing primitives (bool arrays, True = ink)
# ===========================================================================


def line_pts(x0, y0, x1, y1):
    """Bresenham points from (x0, y0) to (x1, y1) inclusive."""
    pts = []
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        pts.append((x0, y0))
        if (x0, y0) == (x1, y1):
            return pts
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def poly(shape, pts, w=1) -> np.ndarray:
    """Polyline mask with a w x w square brush (top-left at the point)."""
    m = np.zeros(shape, bool)
    for (a, b), (c, d) in zip(pts, pts[1:]):
        for x, y in line_pts(a, b, c, d):
            m[max(y, 0):y + w, max(x, 0):x + w] = True
    return m


def ellipse(shape, cx, cy, rx, ry) -> np.ndarray:
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    return ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0


def dilate4(m: np.ndarray) -> np.ndarray:
    p = np.pad(m, 1)
    return m | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]


def put(b: np.ndarray, m: np.ndarray, sep: bool = False) -> None:
    """Ink m into b; sep: first cut a 1-px paper ring round it (part in front)."""
    if sep:
        b[dilate4(m) & ~m] = False
    b |= m


# ===========================================================================
# SPIDER (32x16 body; ink $05). Abdomen left, head right, 4 legs a side seen as
# one set: hip -> knee (above the body) -> ankle (row 11) -> foot (floor row 15).
# Legs sit BEHIND the body (no paper ring). Walk frames differ only below the
# ankles (rows 12-15), so the pair packs like the Rat's run pair.
# ===========================================================================

SP_HIPS = ((22, 7), (20, 6), (18, 6), (16, 7))
SP_KNEES = ((26, 2), (23, 1), (16, 1), (11, 1))
SP_ANKLES = ((29, 11), (25, 11), (13, 11), (6, 11))


def spider_body(front_up: bool = False) -> np.ndarray:
    sh = (16, 32)
    b = np.zeros(sh, bool)
    cy = 7 if front_up else 8
    put(b, ellipse(sh, 7.5, 7.0, 7.2, 4.6))                    # abdomen
    put(b, ellipse(sh, 19.0, cy, 4.3, 2.8))                    # cephalothorax
    put(b, ellipse(sh, 24.0, cy + 0.5, 2.2, 2.0))              # head
    b[4, 6:9] = False                                           # abdomen chevron
    b[5, 4:6] = False
    b[5, 9:11] = False
    b[7, 7] = False
    b[9, 4:11] = False                                          # abdomen band
    b[cy - 1, 24] = False                                       # eye
    b[cy + 1, 14:16] = False                                    # waist
    return b


def spider_frame(legs, front_up=False, fangs=((25, 11), (26, 12))) -> np.ndarray:
    b = np.zeros((16, 32), bool)
    for pts in legs:
        put(b, poly(b.shape, pts))
    b |= spider_body(front_up)
    for x, y in fangs:
        b[y, x] = True
    return b


def sp_legs(feet):
    return [[h, k, a, f] for h, k, a, f in zip(SP_HIPS, SP_KNEES, SP_ANKLES, feet)]


def spider_walk1():
    return spider_frame(sp_legs(((31, 15), (26, 15), (12, 15), (4, 15))))


def spider_walk2():
    return spider_frame(sp_legs(((30, 15), (24, 15), (14, 15), (7, 15))))


def spider_bite() -> np.ndarray:
    """Rears up: the two front legs lifted forward, fangs bared under the head."""
    legs = sp_legs(((31, 15), (26, 15), (12, 15), (4, 15)))
    legs[0] = [(22, 6), (25, 1), (31, 3)]
    legs[1] = [(20, 6), (23, 0), (29, 0)]
    return spider_frame(legs, front_up=True,
                        fangs=((25, 10), (26, 11), (26, 12), (24, 11), (24, 12)))


# ===========================================================================
# ORC (24x48; ink $04): hunched brute, jutting jaw + tusk, pointed ear, belt,
# cleaver hanging from the front fist. ART2 (2026-10-29, user): the 1-px strip
# hanging between the legs under the belt (rows 30-32, x 13) removed.
# ===========================================================================

ORC_TOP = """
00|........................
01|........................
02|........................
03|........................
04|........................
05|..........#######.......
06|.........#########......
07|........###########.....
08|.......#.####...###.....
09|........#####.#.###.....
10|.........##########.#...
11|.........#####.######...
12|.........####.#.#.#.#...
13|..........#########.....
14|...........#######......
15|........###########.....
16|......##############....
17|.....####.########.###..
18|....#####.########.####.
19|....####.##########.###.
20|....####.##########.###.
21|....####.##########.###.
22|....###..##########.###.
23|....###..#########..###.
24|....###..#########..###.
25|....###..#########..###.
26|...####..#########.####.
27|...####..#.#.#.#.#.####.
28|...####..#########.####.
29|....##...####.####.###..
30|.........###...###..#...
31|.........###...###.####.
32|.........###...###.#####
33|.........###...###.#####
34|.........###...###.###.#
"""
ORC_LEGS1 = """
35|........####...####.####
36|........####...####.###.
37|........###.....###.##..
38|........###.....###.....
39|........###.....###.....
40|........###.....###.....
41|.......####.....####....
42|.......###.......###....
43|.......###.......###....
44|.......###.......###....
45|.......####......####...
46|......######.....######.
47|......######.....######.
"""
ORC_LEGS2 = """
35|........####...####.####
36|.......####.....###.###.
37|.......###......####.#..
38|......####.......###....
39|......###........###....
40|.....####.........###...
41|.....###..........###...
42|....####..........###...
43|....###...........###...
44|...####...........####..
45|...###............#####.
46|..#####...........######
47|..#####...........######
"""


def orc_walk(legs) -> np.ndarray:
    return stack(art(ORC_TOP, 24), art(legs, 24))


ORC_ATTACK_HIGH = """
00|................#..#.##########.
01|.............#.......#.########.
02|...........#.........##########.
03|.....................#........#.
04|.....................##########.
05|......................###.......
06|......................###.......
07|......................####......
08|.....................#####......
09|....................#####.......
10|...................#####........
11|..................#####.........
12|..................####..........
13|..................###...........
14|..................###...........
15|..................###...........
16|..................###...........
17|..................###...........
18|..................##............
"""


def orc_attack() -> np.ndarray:
    """ART2 O3 (user-approved 2026-10-29), same 32x48 box: the cleaver (carried
    low at the hip in the walk) raised over the head and chopping down — blade
    above the fist, a swing arc of ticks behind the skull."""
    b = np.hstack([orc_walk(ORC_LEGS1), blank(8, 48)])
    b[15:29, 18:] = False                                         # old front arm
    b[29:38, 19:] = False                                         # cleaver at the hip
    arm = np.zeros_like(b)
    arm[0:19] = art(ORC_ATTACK_HIGH, 32)
    put(b, arm, sep=True)
    return b


# ===========================================================================
# NECROMANCER (24x48; ink $03): hood, glowing eyes, skull staff, long robe.
# ===========================================================================

NECRO_TOP = """
00|........................
01|..................###...
02|.................#####..
03|.................#.#.#..
04|..........###....#####..
05|.........######...#.#...
06|........########...#....
07|.......##########..#....
08|.......####.....#..#....
09|.......###.......#.#....
10|.......###..#.#..#.#....
11|.......####......#.#....
12|........####....##.#....
13|........#########..#....
14|.......###########.#....
15|......####.########.....
16|.....####.#####...###...
17|.....####.####.######...
18|.....###.#####.######...
19|.....###.#####..##.#....
20|.....###.######....#....
21|.....###.######.##.#....
22|......##.#######.#.#....
23|......#..#######.#.#....
24|.........#######.#.#....
25|.........#.#.#.#...#....
26|.........#######.#.#....
27|.........#######.#.#....
28|........########.#.#....
29|........#########..#....
30|........#########..#....
31|........##########.#....
32|.......###########.#....
33|.......###.#######.#....
34|.......###.########.....
35|......####.########.....
36|......###.#########.....
37|......###.##########....
38|.....####.##########....
39|.....###.###########....
"""
NECRO_HEM1 = """
40|.....###.###########....
41|....####.############...
42|....###.#############...
43|....###.#############...
44|...####.##############..
45|...#.#.#.#.#.#.#.#.#.#..
46|...........#####........
47|..........######........
"""
NECRO_HEM2 = """
40|.....###.###########....
41|....####.############...
42|....###.#############...
43|...####.#############...
44|...###.##############...
45|..#.#.#.#.#.#.#.#.#.#...
46|..####...........####...
47|..####...........#####..
"""


def necro_walk(hem) -> np.ndarray:
    return stack(art(NECRO_TOP, 24), art(hem, 24))


def necro_cast() -> np.ndarray:
    """Front arm thrust out, clawed hand under a dark spark; staff kept upright."""
    b = np.hstack([necro_walk(NECRO_HEM1), blank(8, 48)])
    b[14:25, 15:] = False
    b[14:25] |= art("""
14|.......................#..#..#
15|.....................#..#.#.#.
16|..............#######.#.###.#.
17|..............###########.##..
18|..............#######..####.#.
19|..............##.........#.#.#
20|...................#..........
21|...................#..........
22|...................#..........
23|...................#..........
24|...................#..........
""", 32)
    return b


# ===========================================================================
# MUMMY (24x48; ink $06): bandage bands, arms reaching forward, shuffle.
# ===========================================================================

MUMMY_TOP = """
00|........................
01|........................
02|........................
03|........................
04|..........######........
05|.........########.......
06|........##########......
07|........###....####.....
08|........##########......
09|........#######.#.#.....
10|........##########......
11|.........###....##......
12|.........########.......
13|..........######........
14|........##########......
15|.......##############...
16|.......####.##########..
17|.......###########..#...
18|.......#####.###########
19|.......################.
20|.......###########.#.#..
21|.......######..###......
22|........##########......
23|........###....###......
24|........##########......
25|........#####...##......
26|........##########......
27|........###....###......
28|........##########......
29|........#####..###......
30|........##########......
31|........###..#####......
32|........##########......
"""
MUMMY_LEGS1 = """
33|........####..####......
34|........##.#..##.#......
35|........####..####......
36|........#..#..###.......
37|........####..####......
38|........###...#.##......
39|........####..####......
40|........#.##..##.#......
41|........####..####......
42|........##.#..#..#......
43|........####..####......
44|.......#####..#####.....
45|.......####...######....
46|.......#####..######....
47|......######..######....
"""
MUMMY_LEGS2 = """
33|........####..####......
34|........##.#..##.#......
35|.......####...####......
36|.......#..#...###.......
37|......####.....####.....
38|......###......#.##.....
39|......####.....####.....
40|.....#.##.......##.#....
41|.....####.......####....
42|.....##.#.......#..#....
43|....####........####....
44|....####........#####...
45|...####.........######..
46|...#####........######..
47|..######........######..
"""


def mummy_walk(legs) -> np.ndarray:
    b = stack(art(MUMMY_TOP, 24), art(legs, 24))
    # trailing bandage from the back shoulder
    b[16:30, 5:7] |= art("""
#.
##
.#
.#
#.
#.
.#
..
.#
#.
#.
..
..
..
""", 2)
    return b


def mummy_attack() -> np.ndarray:
    """Lunging grab: both arms thrust out 8 px further than in the walk."""
    b = np.hstack([mummy_walk(MUMMY_LEGS1), blank(8, 48)])
    b[15:22, 15:] = False
    b[15:22] |= art("""
15|.......#####################....
16|.......####.#################...
17|.......###########.........#....
18|.......#####.###################
19|.......########################.
20|.......###########.........#.#..
21|.......######..###..............
""", 32)
    return b


# ===========================================================================
# OGRE WARLORD (32x48 body; ink $44): small bald head with an underbite, huge
# shoulders and gut, arms hanging, a knotted club dragged in the front fist.
# Parts are layered back to front; a part in front gets a 1-px paper ring.
# ===========================================================================


def ogre_body(sh, legs, front_arm=True) -> np.ndarray:
    b = np.zeros(sh, bool)
    (bx0, bx1), (fx0, fx1) = legs                  # foot x (back, front) at the hip / floor
    put(b, poly(sh, [(bx0, 31), (bx1, 44)], w=5))  # back leg
    put(b, poly(sh, [(fx0, 31), (fx1, 44)], w=5))  # front leg
    put(b, poly(sh, [(bx1 - 1, 45), (bx1 + 5, 45)], w=3))   # feet (toes right)
    put(b, poly(sh, [(fx1 - 1, 45), (fx1 + 6, 45)], w=3))
    put(b, poly(sh, [(7, 15), (4, 26)], w=4))      # back arm (behind the gut)
    put(b, ellipse(sh, 5.5, 28.5, 2.6, 2.6))       # back fist
    put(b, ellipse(sh, 16.0, 23.5, 9.6, 9.2), sep=True)   # gut
    put(b, ellipse(sh, 15.0, 16.0, 10.4, 4.8))     # shoulders / chest
    b[29, 8:25] = False                            # belt edges
    b[31, 8:25] = False
    b[30, 9:24:2] = False                          # belt studs
    b[32:35, 14:19] = True                         # loincloth flap
    b[24, 18] = False                              # navel
    b[19, 10:15] = False                           # chest fold
    put(b, ellipse(sh, 17.0, 8.0, 4.4, 5.0), sep=True)    # head
    b[13, 15:20] = True                            # thick neck
    b[7, 18:21] = False                            # brow shadow / eye
    b[8, 19] = False
    put(b, poly(sh, [(17, 11), (22, 11)], w=2))    # underbite jaw
    b[10, 19:22] = False                           # mouth line
    b[9, 22] = True                                # tusk
    b[10, 22] = True
    b[5, 16] = False                               # skull dent
    if front_arm:
        put(b, poly(sh, [(21, 14), (24, 26)], w=4), sep=True)   # front arm
    return b


OGRE_LEGS1 = ((11, 10), (19, 20))
OGRE_LEGS2 = ((11, 7), (19, 23))


def ogre_walk(legs) -> np.ndarray:
    sh = (48, 32)
    b = ogre_body(sh, legs)
    put(b, poly(sh, [(25, 30), (28, 38)], w=2), sep=True)        # club haft
    put(b, ellipse(sh, 28.5, 41.5, 3.0, 4.0), sep=True)          # club head
    b[40, 28] = False                                            # knots
    b[43, 29] = False
    put(b, ellipse(sh, 25.5, 28.5, 2.6, 2.6), sep=True)          # front fist
    return b


def ogre_slam() -> np.ndarray:
    """ART2 O1 (user-approved 2026-10-29), same 40x48 box: the club comes DOWN on
    the victim's head — arm thrown up-forward, club head at head height, an arc
    of swing ticks above the skull, chips off the impact. No floor strike."""
    sh = (48, 40)
    b = ogre_body(sh, OGRE_LEGS1, front_arm=False)
    for x, y in ((14, 0), (17, 0), (20, 0), (23, 1), (26, 1), (29, 2), (31, 3),
                 (33, 4), (12, 1), (24, 0), (28, 0), (32, 1)):
        b[y, x] = True                                            # swing arc above the head
    put(b, poly(sh, [(21, 14), (28, 10)], w=4), sep=True)         # arm thrown up-forward
    put(b, ellipse(sh, 30.5, 11.0, 2.6, 2.6), sep=True)           # fist
    put(b, poly(sh, [(32, 9), (34, 6)], w=2), sep=True)           # haft
    put(b, ellipse(sh, 36.0, 5.5, 3.6, 4.6), sep=True)            # club head (coming down)
    b[4, 36] = False                                              # knots
    b[7, 35] = False
    for x, y in ((39, 13), (38, 15), (36, 14)):
        b[y, x] = True                                            # chips off the impact
    return b


# ===========================================================================
# DEATH KNIGHT (24x48 body; ink $47): the Warrior's evil twin — great helm with
# two horns and a 3-point crown, visor slit, cape behind, plate with a studded
# belt and tassets, greaves; a two-handed greatsword (fullered blade) carried
# upright in front, crossguard at the shoulder.
# ===========================================================================

DK_TOP = """
00|....#.................#.
01|....#........#....#..###
02|....##....#..#..#.#..#.#
03|.....##..##########..#.#
04|......############...#.#
05|.......###########...#.#
06|.......###########...#.#
07|.......###########...#.#
08|.......######....#...#.#
09|.......###########...#.#
10|.......#######.#.#...#.#
11|.......###########...#.#
12|........#########....#.#
13|.....###..#####......#.#
14|....####.######.####.#.#
15|...#####.#####.#####.#.#
16|...#####.#####.#####.#.#
17|...#####.######.##.#####
18|..######.#######.######.
19|..######.#######.######.
20|..######.########.#####.
21|..######.########.....#.
22|..######.#########......
23|..######.#########......
24|..######.#.#.#.#.#......
25|..######.#########......
26|.#######.####.####......
27|.#######.####.####......
28|.#######.###...###......
29|########.###...###......
30|#.#.#.#..###...###......
"""
DK_LEGS1 = """
31|.........####..####.....
32|.........###....###.....
33|.........###....###.....
34|.........###....###.....
35|........####....####....
36|........#..#....#..#....
37|........####....####....
38|........###.....###.....
39|........###.....###.....
40|........###.....###.....
41|........###.....###.....
42|........###.....###.....
43|........###.....###.....
44|........###.....###.....
45|........#####...#####...
46|.......######..######...
47|.......######..######...
"""
DK_LEGS2 = """
31|.........####..####.....
32|........####....###.....
33|........###.....####....
34|.......####......###....
35|.......###.......####...
36|......#..#.......#..#...
37|......####.......####...
38|......###.........###...
39|.....####.........###...
40|.....###..........###...
41|.....###...........###..
42|....####...........###..
43|....###............###..
44|....###............####.
45|...#####...........#####
46|..######...........#####
47|..######...........#####
"""


def dk_walk(legs) -> np.ndarray:
    return stack(art(DK_TOP, 24), art(legs, 24))


def dk_unarmed(dx: int, w: int) -> np.ndarray:
    """WALK 1 body placed at x = dx in a w-px frame, sword, arm and hands removed."""
    body = dk_walk(DK_LEGS1)
    body[0:24, 20:] = False                        # blade, guard, grip, pommel
    body[17:22, 16:20] = False                     # forearm + hands
    body[1:4, 18:20] = art("""
#.
#.
##
""", 2)                                            # front horn tip (was next to the blade)
    b = np.zeros((48, w), bool)
    b[:, dx:dx + 24] = body
    return b


def greatsword(sh, hilt, tip, guard=3) -> np.ndarray:
    """Blade 2 px (brush) from the hilt to the tip + a crossguard across it."""
    m = poly(sh, [hilt, tip], w=2)
    (hx, hy), (tx, ty) = hilt, tip
    vx, vy = tx - hx, ty - hy
    n = float(max(abs(vx), abs(vy)))
    px, py = -vy / n, vx / n
    a = (round(hx - px * guard), round(hy - py * guard))
    c = (round(hx + px * guard), round(hy + py * guard))
    return m | poly(sh, [a, c], w=2)


def dk_cleave() -> np.ndarray:
    """The two-handed chop landed (ax 4): arms thrust forward-down, blade
    reaching the floor line ahead, sparks where it strikes."""
    sh = (48, 40)
    b = dk_unarmed(4, 40)
    put(b, greatsword(sh, (27, 24), (37, 42)), sep=True)
    put(b, poly(sh, [(20, 18), (25, 22)], w=3), sep=True)   # arms
    for x, y in ((39, 41), (36, 46), (39, 46), (35, 44)):
        b[y, x] = True                                       # sparks where it bites the floor
    return b


def dk_block() -> np.ndarray:
    """Parry (ax 4): blade slanted up-forward across the front, hilt at the chest."""
    sh = (48, 32)
    b = dk_unarmed(4, 32)
    put(b, greatsword(sh, (25, 18), (31, 1)), sep=True)
    put(b, poly(sh, [(20, 18), (23, 19)], w=3), sep=True)   # forearm to the grip
    b[19:23, 23:26] = True                                   # gauntlets on the grip
    return b


# ===========================================================================
# DEAD (shared humanoid, 40x16, ax 8 like knight_dead; ink = the kind's)
# ===========================================================================

def dead_humanoid() -> np.ndarray:
    return art("""
00|........................................
01|........................................
02|........................................
03|........................................
04|........................................
05|........................................
06|................................#####...
07|...............................#######..
08|...........#.####..............##.#.##..
09|..........######.##........#############
10|.........########.##.###########..####..
11|.......##########.##############.#####..
12|.....###########.###############.####...
13|...##############.##############.###....
14|..#####.####.#########.#######.#.##.....
15|.######################################.
""", 40)


# ===========================================================================
# NECRO BOLT (FX, cell-aligned; ink $43 like the Death Bolt)
# ===========================================================================

NBOLT_FLY1 = """
.......#........
..#...###.......
.....#####.#....
#.#.###.###.##..
.#.#########.##.
.....#####......
..#...###.#.....
.......#........
"""
NBOLT_FLY2 = """
........#.......
#......###......
...#..#####.....
.#.#.###.####.#.
#.#.#########.#.
....#..###.#....
.#.....###......
........#.......
"""
NBOLT_HIT = """
................
.......#........
...#...#...#....
....#..#..#.....
.....#.#.#......
..#...###...#...
...#.#####.#....
.####.#.#.####..
...#.#####.#....
..#...###...#...
.....#.#.#......
....#..#..#.....
...#...#...#....
.......#........
................
................
"""

# ===========================================================================
# Frame list (fragment order): (heading, caption, builder, ink hex)
# ===========================================================================

INK_SPIDER = "#00D7D7"    # $05 (tiers: Black Widow $02)
INK_ORC = "#00D700"       # $04 (tiers: Berserker $02, Bouncer $03)
INK_NECRO = "#D700D7"     # $03 (tier: Bone Caller $06); Vampire / Archmage ink per kind row
INK_MUMMY = "#D7D700"     # $06
INK_OGRE = "#00FF00"      # $44
INK_DK = "#FFFFFF"        # $47 (the Warrior's evil twin)
INK_DEAD = "#D7D7D7"      # $07 preview only: drawn in the dead kind's ink
TILE_INK = {0x43: "#FF00FF", 0x06: "#D7D700", 0x07: "#D7D7D7"}
INK_BOLT = "#FF00FF"      # $43 (game.md §11.1: Death Bolt $43; Dark Bolt same frames)

FRAMES = [
    ("SPIDER", "WALK 1", spider_walk1, INK_SPIDER),
    ("SPIDER", "WALK 2", spider_walk2, INK_SPIDER),
    ("SPIDER", "BITE", spider_bite, INK_SPIDER),
    ("ORC", "WALK 1", lambda: orc_walk(ORC_LEGS1), INK_ORC),
    ("ORC", "WALK 2", lambda: orc_walk(ORC_LEGS2), INK_ORC),
    ("ORC", "ATTACK", orc_attack, INK_ORC),
    ("NECROMANCER", "WALK 1", lambda: necro_walk(NECRO_HEM1), INK_NECRO),
    ("NECROMANCER", "WALK 2", lambda: necro_walk(NECRO_HEM2), INK_NECRO),
    ("NECROMANCER", "CAST", necro_cast, INK_NECRO),
    ("MUMMY", "WALK 1", lambda: mummy_walk(MUMMY_LEGS1), INK_MUMMY),
    ("MUMMY", "WALK 2", lambda: mummy_walk(MUMMY_LEGS2), INK_MUMMY),
    ("MUMMY", "ATTACK", mummy_attack, INK_MUMMY),
    ("OGRE", "WALK 1", lambda: ogre_walk(OGRE_LEGS1), INK_OGRE),
    ("OGRE", "WALK 2", lambda: ogre_walk(OGRE_LEGS2), INK_OGRE),
    ("OGRE", "SLAM", ogre_slam, INK_OGRE),
    ("DEATH KNIGHT", "WALK 1", lambda: dk_walk(DK_LEGS1), INK_DK),
    ("DEATH KNIGHT", "WALK 2", lambda: dk_walk(DK_LEGS2), INK_DK),
    ("DEATH KNIGHT", "CLEAVE", dk_cleave, INK_DK),
    ("DEATH KNIGHT", "BLOCK", dk_block, INK_DK),
    ("DEAD", "HUMANOID", dead_humanoid, INK_DEAD),
    ("NECRO BOLT", "FLY 1", lambda: art(NBOLT_FLY1, 16), INK_BOLT),
    ("NECRO BOLT", "FLY 2", lambda: art(NBOLT_FLY2, 16), INK_BOLT),
    ("NECRO BOLT", "HIT", lambda: art(NBOLT_HIT, 16), INK_BOLT),
]
# heading -> (pool_spike group, stand-in packed B from docs/design/pool_spike.md)
GROUPS = {"SPIDER": ("SPIDER", 185), "ORC": ("ORC", 338), "NECROMANCER": ("NECRO", 470),
          "MUMMY": ("MUMMY", 560), "OGRE": ("OGRE", 464), "DEATH KNIGHT": ("DK", 770),
          "DEAD": ("DEAD_H", 98), "NECRO BOLT": ("NBOLT", 101)}
NOTE_TEXT = {
    "SPIDER": "Body 32x16, ink $05 (proposal; Black Widow tier $02). WALK 1 = rest (MOT), "
              "WALK 2 (WK0), BITE 40x16 ax 0 (lunges onto the front legs, fangs out).",
    "ORC": "Body 24x48, ink $04 (proposal; tiers $02/$03). §9.7 R3: 3 frames. WALK 1 = rest, "
           "WALK 2, ATTACK 32x48 (ART2: cleaver raised overhead, chopping down). Walker, no climb.",
    "NECROMANCER": "Body 24x48, ink $03 (proposal; Bone Caller $06). Vampire and Archmage are "
                   "drawn with these frames in their own inks. CAST 32x48: arm out under a dark spark.",
    "MUMMY": "Body 24x48, ink $06. Bandage bands = paper lines. ATTACK 32x48: arms thrust "
             "out for the grab.",
    "OGRE": "Ogre Warlord (unique), body 32x48, ink $44 (proposal). SLAM 40x48 (ART2): club "
            "brought down at head height (reach 2). RAISE / HURT dropped (lean set).",
    "DEATH KNIGHT": "Unique, body 24x48, ink $47. Horned crowned helm, greatsword carried "
                    "upright. CLEAVE 40x48 (ax 4): the chop down to the floor. BLOCK 32x48 "
                    "(ax 4): blade crosswise, parry (kept: §9.7 R5 item 7 is last resort).",
    "DEAD": "One shared lying-body frame for every new humanoid kind (40x16, ax 8 like "
            "knight_dead). Drawn in the dead kind's ink; the preview ink is neutral.",
    "NECRO BOLT": "Dark Bolt / Death Bolt FX: FLY 1/2 16x8 -> HIT 16x16, ink $43.",
}
# frames the engine draws mid-tween (WALK 1 = MOT rest frame, WALK 2 = WK0)
MOT = {"WALK 1"}

# ===========================================================================
# Tiles (§9.7 R2)
# ===========================================================================


def concept_tile_block(fname: str, name: str) -> list[str]:
    rows, on = [], False
    for line in open(os.path.join(CONCEPT, fname)):
        line = line.rstrip("\n")
        if line.startswith("==="):
            if on:
                break
            on = line.split()[1] == name
            continue
        if on and line and set(line) <= {".", "#"} and not line.startswith("# "):
            rows.append(line)                  # a pixel row ('#...' rows are pixels too)
    if not rows:
        raise SystemExit(f"{fname}: no block {name!r}")
    return rows


def tiles() -> list[tuple[str, int, list[str], str]]:
    """-> [(name, attr, 8 rows, note)]: lectern TL/TR/BL/BR then grate_shut."""
    lect = concept_tile_block("decor_r4.grid", "lectern")
    assert len(lect) == 16 and all(len(r) == 16 for r in lect), "lectern must be 16x16"
    out = []
    for i, (nm, a) in enumerate((("lectern_tl", 0x43), ("lectern_tr", 0x43),
                                 ("lectern_bl", 0x06), ("lectern_br", 0x06))):
        r0, c0 = (i // 2) * 8, (i % 2) * 8
        out.append((nm, a, [r[c0:c0 + 8] for r in lect[r0:r0 + 8]],
                    f"common id {15 + i}: decor_r4.grid 'lectern' cell r{i // 2}c{i % 2}"))
    g = concept_tile_block("b12_gate.tiles", "gate_closed")
    assert len(g) == 8 and all(len(r) == 8 for r in g)
    out.append(("grate_shut", 0x07, g, "common id 13 T_GRATE_SHUT: b12_gate.tiles 'gate_closed'"))
    return out


# ===========================================================================
# outputs
# ===========================================================================

BADGE = ('<p style="margin: 0; font-family: \'Press Start 2P\', monospace; font-size: 8px; '
         'color: #ffd84a;">NEW</p>')
ROW = '<div style="display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-end;">'
NOTE = '<p style="font-size: 11px; color: #a9a7b8; margin: 8px 0;">{}</p>'


def svg(bm, ink):
    h, w = bm.shape
    return (f'<svg width="{w * SCALE}" height="{h * SCALE}" viewBox="0 0 {w} {h}" '
            f'shape-rendering="crispEdges" style="display: block;">'
            f'<rect width="{w}" height="{h}" fill="#000000"></rect>'
            f'<path d="{S.grid_path(w, h)}" stroke="{S.GRID_STROKE}" stroke-width="0.12" '
            f'fill="none"></path>'
            f'<path d="{S.bitmap_to_path(bm)}" fill="{ink}"></path></svg>')


def box(bm, ink):
    return ('<div style="padding: 8px; background: #000000; border: 2px solid #26263a;">'
            f'{svg(bm, ink)}</div>')


def artboard(bm, ink, caption):
    h, w = bm.shape
    cap = html.escape(f"{caption} · {w}×{h}")
    return ('<div style="display: flex; flex-direction: column; gap: 6px; align-items: flex-start;">\n'
            f'{box(bm, ink)}\n'
            f'<div style="font-size: 11px; letter-spacing: 1px; color: #a9a7b8;">{cap}</div>\n'
            f'{BADGE}\n</div>')


def tile_board(bm, ink, label):
    return ('<div style="display: flex; flex-direction: column; gap: 6px; align-items: flex-start;">\n'
            f'{box(bm, ink)}\n'
            '<div style="font-family: \'Press Start 2P\', monospace; font-size: 10px; '
            f'color: #e8e6f0;">{label}</div>\n</div>')


def heading(name):
    return ('<div style="font-family: \'Press Start 2P\', monospace; font-size: 13px; '
            f'color: #e8e6f0; margin: 24px 0 12px;">{name}</div>')


def grid_text(b) -> str:
    bm, solid = b["bm"], b["solid"]
    h, w = bm.shape
    lines = ["# WazHack/ZX gfx text grid — DRAFT generated by tools/gen_3f_art.py "
             "(edit that); 3F-A1, not on the canvas yet.",
             f"# name: {b['name']}", f"# size: {w}x{h}", f"# character: {b['hd']}",
             f"# caption: {b['cap']}", f"# ink: {b['ink']}", f"# anchor: {b['ax']} {b['ay']}",
             "# legend: '#' ink, '+' opaque paper (mask 0, data 0), '.' transparent", "#"]
    lines += ["".join("#" if bm[y, x] else "+" if solid[y, x] else "." for x in range(w))
              for y in range(h)]
    return "\n".join(lines) + "\n"


def render(bm, solid, ink, scale=SCALE, paper=(52, 52, 84)):
    h, w = bm.shape
    rgb = tuple(int(ink[i:i + 2], 16) for i in (1, 3, 5))
    a = np.zeros((h, w, 3), np.uint8)
    a[:] = paper
    a[solid] = (0, 0, 0)
    a[bm] = rgb
    return Image.fromarray(a).resize((w * scale, h * scale), Image.NEAREST)


def hstrip(ims, gap=12, bg=(24, 24, 36)):
    W = sum(i.width for i in ims) + gap * (len(ims) - 1)
    H = max(i.height for i in ims)
    st = Image.new("RGB", (W, H), bg)
    x = 0
    for im in ims:
        st.paste(im, (x, H - im.height))
        x += im.width + gap
    return st


def vstack_im(ims, gap=12, bg=(24, 24, 36)):
    W = max(i.width for i in ims)
    H = sum(i.height for i in ims) + gap * (len(ims) - 1)
    st = Image.new("RGB", (W, H), bg)
    y = 0
    for im in ims:
        st.paste(im, (0, y))
        y += im.height + gap
    return st


def gfx_native(b, rel_grid, out_asm):
    colour, bright = S.INK_MAP[b["ink"]]
    h, w = b["bm"].shape
    notes = ["DRAFT (not yet on the canvas): assets/gfx/source/3f_frames.svg.html",
             "generated by tools/gen_3f_art.py (3F-A1)",
             f"artboard: {b['hd']} / {b['cap']} ({w}x{h}), ink {b['ink']}",
             f"grid: {rel_grid}",
             f"anchor: {b['anchor_note']}; ax_L={b['axl']}",
             "class: " + ("MOTION" if b["cap"] in MOT and b["hd"] not in S.FX_PREFIXES
                          and b["hd"] != "NECRO BOLT" else "STATIONARY"),
             "NOT in sprites/index.asm yet (T13 wires it: FRM row, SRC6 block)"]
    argv = ["--mode", "sprite", "--layout", "native", "--in", rel_grid,
            "--name", b["name"], "--out", out_asm,
            "--ink", GC.COL_NAME[colour], "--paper", "black", "--band-paper", "black",
            "--anchor-x", str(b["ax"]), "--anchor-y", str(b["ay"]), "--src-path",
            "--date", GEN_DATE]
    for n in notes:
        argv += ["--note", n]
    if bright:
        argv.append("--bright")
    S._quiet(S.run_gfx, argv)


def raw_bytes(asm_path):
    rows, attr = S.decode_asm(asm_path)
    return bytes(x for r in rows for x in r), rows, attr


def check_rows(b, rows):
    """DEFB rows decode back to the bitmap (data) and the derived mask."""
    h, w = b["bm"].shape
    assert len(rows) == h, b["name"]
    for y, r in enumerate(rows):
        assert len(r) == w // 4, b["name"]
        for c in range(w // 8):
            m, d = r[2 * c], r[2 * c + 1]
            for i in range(8):
                x = c * 8 + i
                bit = 0x80 >> i
                if bool(d & bit) != bool(b["bm"][y, x]):
                    raise SystemExit(f"{b['name']}: data mismatch at ({x},{y})")
                if (not (m & bit)) != bool(b["solid"][y, x]):
                    raise SystemExit(f"{b['name']}: mask mismatch at ({x},{y})")


ART23_FRAMES = ("orc_raise", "ogre_raise", "vamp_bite", "small_corpse", "necro_walk3",
                "mummy_walk3", "mummy_walk4", "climb_h1", "climb_h2", "dk_walk3")
# ANIM-IMPORT (necro_walk4, ART3) and ANIM-IMPORT2 (the 40-px-only names: no 48-px file, the .asm
# lives in assets/gfx/sprites40/, resolved by tools/zx0_pack.py sprite_asm through index40.asm)
ANIM_FRAMES = ("necro_walk4",)
ANIM40_FRAMES = ("orc_walk3", "orc_hurt", "vamp_walk1", "vamp_walk2", "vamp_walk3", "vamp_hurt")


def write_index_3f() -> None:
    """assets/gfx/sprites/index_3f.asm: the INCLUDEs of this tool's frames (sources only: the
    packer reads them; no <char>_frames / _meta tables, unread by the engine). index.asm
    INCLUDEs it (svg_sprites.write_index always emits that line), so a canvas re-import
    cannot wipe the 3F frames."""
    L = ["; 3F-A1 lean frames: GENERATED by tools/gen_3f_art.py (owns this file); INCLUDEd by",
         "; index.asm (svg_sprites.write_index always emits that line). Sources only: the packer",
         "; (tools/zx0_pack.py index_names) reads these includes; no tables."]
    for hd, cap, _fn, _ink in FRAMES:
        L.append(f'        INCLUDE "{S.CHAR_PREFIX[hd]}_{S.slug(cap)}.asm"')
    L.append("; ART2 / ART3 final frames (tools/gen_art2_final.py / gen_art3_final.py own the .asm files;")
    L.append("; wired by 3F-T13bc: src/frames.asm FRM rows)")
    for n in ART23_FRAMES + ANIM_FRAMES:
        L.append(f'        INCLUDE "{n}.asm"')
    L.append("; ANIM-IMPORT2: new 40-px-only frames (no 48-px file; tools/zx0_pack.py sprite_asm resolves")
    L.append("; them in assets/gfx/sprites40/, listed in its index40.asm)")
    for n in ANIM40_FRAMES:
        L.append(f'        INCLUDE "{n}.asm"')
    with open(os.path.join(SPR, "index_3f.asm"), "w") as f:
        f.write("\n".join(L) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--png-dir")
    ap.add_argument("--check", action="store_true",
                    help="build + validate + sizes only; write nothing under assets/")
    args = ap.parse_args()
    built = []
    for hd, cap, fn, ink in FRAMES:
        bm = fn()
        name = f"{S.CHAR_PREFIX[hd]}_{S.slug(cap)}"
        h, w = bm.shape
        assert w % 8 == 0 and h % 8 == 0, (name, w, h)
        built.append(dict(hd=hd, cap=cap, name=name, bm=bm, ink=ink,
                          solid=S.make_mask(bm, S.OUTLINE, name)))
    if args.png_dir:
        d = args.png_dir
        os.makedirs(d, exist_ok=True)
        rowsim = []
        for hd in dict.fromkeys(b["hd"] for b in built):
            rowsim.append(hstrip([render(b["bm"], b["solid"], b["ink"]) for b in built
                                  if b["hd"] == hd]))
            hstrip([render(b["bm"], b["solid"], b["ink"], scale=7) for b in built
                    if b["hd"] == hd]).save(os.path.join(d, S.CHAR_PREFIX[hd] + ".png"))
        vstack_im(rowsim).save(os.path.join(d, "3f_sheet.png"))
        print(f"preview -> {os.path.join(d, '3f_sheet.png')}")
    # ---- fragment
    out = ["<!-- WazHack/ZX 3F-A1 DRAFT artboards (lean 3F monster frames). Generated by "
           "tools/gen_3f_art.py; paste as one artboard for review. All face right (the "
           "engine mirrors). Inks are proposals (game.md §9.6 ink rules). -->",
           "<h2>3F DRAFT</h2>"]
    for hd in dict.fromkeys(b["hd"] for b in built):
        out.append(heading(hd))
        out.append(NOTE.format(html.escape(NOTE_TEXT[hd])))
        out.append(ROW)
        out += [artboard(b["bm"], b["ink"], b["cap"]) for b in built if b["hd"] == hd]
        out.append("</div>")
    ts = tiles()
    out.append("<h2>3F TILES</h2>")
    out.append(NOTE.format("game.md §9.7 R2: lectern 2x2 = common ids 15/16/17/18 (top $43, "
                           "base $06; pixels = the approved decor_r4 lectern), T_GRATE_SHUT = "
                           "id 13 ($07, B12 gate_closed: its bars line up with the raised "
                           "gate's teeth)."))
    out.append(ROW)
    out += [tile_board(art("\n".join(rows), 8), TILE_INK[a], nm.upper().replace("_", " "))
            for nm, a, rows, _n in ts]
    out.append("</div>")
    frag = "\n".join(out) + "\n"
    # ---- re-parse check: the sprite part of the fragment reads back to the same bitmaps
    with tempfile.TemporaryDirectory() as tmp:
        sprite_frag = frag.split("<h2>3F TILES</h2>")[0]
        fpath = os.path.join(tmp, "frag.html")
        with open(fpath, "w") as f:
            f.write(frag)
        fr, _ = S.parse_sheet(fpath)
        tframes = [f for f in fr if f.kind == "tile"]
        assert [t.caption for t in tframes] == [nm.upper().replace("_", " ") for nm, *_ in ts]
        for t, (nm, a, rows, _n) in zip(tframes, ts):
            assert np.array_equal(t.bitmap, art("\n".join(rows), 8)), nm
            assert S.INK_MAP[t.ink_hex][0] == a & 7, nm
            t.extra["draft"] = os.path.relpath(FRAGMENT, REPO)
        sprites = [f for f in fr if f.kind == "sprite"]
        assert len(sprites) == len(built), (len(sprites), len(built))
        for f, b in zip(sprites, built):
            assert (f.character, f.caption) == (b["hd"], b["cap"]) and \
                np.array_equal(f.bitmap, b["bm"]), b["name"]
        # ---- the real importer: canvas + fragment -> anchors, grids, gfx_convert, decode
        sheet = os.path.join(tmp, "sheet.html")
        with open(sheet, "w") as f:
            f.write(open(S.SHEET).read() + "\n" + sprite_frag)
        frames = S.import_sheet(sheet, os.path.join(tmp, "out"), GEN_DATE)
        by = {f.name: f for f in frames}
        for b in built:
            f = by[b["name"]]
            assert np.array_equal(f.solid, b["solid"]), b["name"]
            b["ax"], b["ay"] = f.anchor
            b["axl"] = f.extra["ax_l"]
            b["anchor_note"] = ("declared (svg_sprites ANCHOR_X"
                                + (", ANCHOR_Y" if b["name"] in S.ANCHOR_Y else "") + ")"
                                if f.extra.get("declared")
                                else f"reference {f.extra['ref']} head-band IoU "
                                     f"{f.extra['iou']:.2f}")
            b["raw"], rows, _ = raw_bytes(os.path.join(tmp, "out", b["name"] + ".asm"))
            check_rows(b, rows)
        print(f"importer: canvas + fragment imported, clash + round-trip OK "
              f"({len(frames)} frames incl. {len(built)} new)")
        # ---- sizes per group (zx0_sources block DP + dzx0 round-trip)
        zdir = os.path.join(tmp, "z")
        os.makedirs(zdir)
        over_budget = []
        print(f"{'frame':22s} {'WxH':>6s} {'raw':>4s} ax ay axL")
        for b in built:
            h, w = b["bm"].shape
            print(f"{b['name']:22s} {w:>2d}x{h:<3d} {len(b['raw']):>4d} {b['ax']:>2d} "
                  f"{b['ay']:>3d} {b['axl']:>3d}")
        tot = 0
        for hd, (g, standin) in GROUPS.items():
            fl = [(b["name"], b["raw"]) for b in built if b["hd"] == hd]
            parts = ZS.partition(fl, zdir)
            gz = graw = 0
            for i, (s0, k) in enumerate(parts):
                raw = b"".join(d for _, d in fl[s0:s0 + k])
                z = ZS.pack(raw, zdir)
                ZS.roundtrip(z, raw, zdir, f"{g}{i}")
                gz += len(z)
                graw += len(raw)
            cap = standin * 11 // 10
            tot += gz
            flag = "OK" if gz <= cap else "OVER"
            if gz > cap:
                over_budget.append(g)
            print(f"group {g:7s} {len(fl)} frames raw {graw:5d} -> zx0 {gz:4d} "
                  f"({len(parts)} block{'s' * (len(parts) > 1)}) | stand-in {standin}, "
                  f"cap +10% {cap}: {flag}")
        print(f"lean 3F total zx0 {tot} (pool_spike stand-ins 3,179 incl. ARCHER_SHOOT 193)")
    if args.check:
        return 1 if over_budget else 0
    # ---- write outputs
    with open(FRAGMENT, "w") as f:
        f.write(frag)
    cwd = os.getcwd()
    os.chdir(REPO)
    try:
        for b in built:
            gpath = os.path.join(GRID_DIR, b["name"] + ".grid")
            with open(gpath, "w") as f:
                f.write(grid_text(b))
            asm = os.path.join(SPR, b["name"] + ".asm")
            gfx_native(b, os.path.relpath(gpath, REPO), os.path.relpath(asm, REPO))
            raw, rows, attr = raw_bytes(asm)
            check_rows(b, rows)
            assert raw == b["raw"], b["name"]
            colour, bright = S.INK_MAP[b["ink"]]
            assert attr == colour | (0x40 if bright else 0), (b["name"], attr)
        S.import_tiles(tframes, SPR, GEN_DATE)       # -> grid/tiles_3f.grid + tiles_3f.asm
        write_index_3f()
    finally:
        os.chdir(cwd)
    print(f"wrote {len(built)} grids + asm -> assets/gfx/sprites/, "
          f"{os.path.relpath(TILE_ASM, REPO)}, {os.path.relpath(FRAGMENT, REPO)}")
    return 1 if over_budget else 0


if __name__ == "__main__":
    raise SystemExit(main())
