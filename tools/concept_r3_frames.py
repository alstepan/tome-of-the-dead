#!/usr/bin/env python3
"""concept_r3_frames.py — deterministic authoring of the CONCEPT round-3 sprite frames.

Writes assets/gfx/concept/grid/r3_frames.grid (2-state block format; tools/concept_screen.py
derives the 3-state F8 masks). Same method as gen_missing_frames.py / concept_r2_frames.py:
existing canvas frames + explicit edits (row deletes, region clears, pastes, lines) and
hand-typed rows. No AI raster.

  hero      knight_jump1/2, knight_power, knight_whirl, knight_throw, knight_bow,
            wizard_jump1/2   (docs/design/game.md §11.1)
  boss      archmage_idle 24x48, archmage_cast 40x48
  spells    drain_fly1/2 16x8, drain_hit 16x16 (Drain Life)
  hand pass zombie_dead, orc_dead, necro_dead (hand-typed 32x16),
            spider_walk1/2, spider_bite, spider_hurt, spider_dead (hand-typed, lighter)
            -> these REPLACE the round-2 frames of the same name (concept_screen.py
               loads r3 after r2).

Usage: python3 tools/concept_r3_frames.py
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from concept_r2_frames import R, src, fit, line, over, paste, blank, T, trim  # noqa: E402
from gen_missing_frames import del_rows, poly  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "assets/gfx/concept/grid/r3_frames.grid")
FRAMES: list = []


def add(name, bm, ink, ax=0):
    h, w = bm.shape
    assert w % 8 == 0 and h % 8 == 0 and w <= 40, (name, w, h)
    assert ax % 4 == 0 and 0 <= ax <= 8, (name, ax)
    FRAMES.append((name, bm.astype(bool), ink, ax))


def arc(b, cx, cy, rx, ry, t0, t1, n, every=1):
    """Dotted elliptical motion arc (swing path), every n-th point kept."""
    for i, t in enumerate(np.linspace(t0, t1, n)):
        if i % every:
            continue
        x, y = int(round(cx + rx * np.cos(t))), int(round(cy + ry * np.sin(t)))
        if 0 <= y < b.shape[0] and 0 <= x < b.shape[1]:
            b[y, x] = True


def crouch(bm, rows_to_drop):
    """Bend the knees: delete leg rows, keep the frame 48 high (pad at the top)."""
    c = del_rows(bm, rows_to_drop)
    return fit(c, bm.shape[1], bm.shape[0])


# ---------------------------------------------------------------------------
# Warrior (knight)
# ---------------------------------------------------------------------------

def knight_no_sword(name="knight_idle1"):
    b = src(name)
    b[0:26, 19:24] = False                                 # sword + guard (right of body)
    return b


def knight() -> dict:
    out = {}
    idle = src("knight_idle1")
    # JUMP1: crouch (take-off / landing), 6 leg rows dropped
    j1 = crouch(idle, [33, 35, 37, 39, 41, 42])
    over(j1, "##..\n.##.", 13, 47 - 1)                       # toe pushes forward
    out["knight_jump1"] = j1
    # JUMP2: airborne tuck — upper body unchanged, legs folded (rows 31..47 redrawn)
    j2 = idle.copy()
    j2[31:48] = False
    paste(j2, R(24, [
        [(8, 14)], [(7, 16)], [(7, 18)], [(8, 19)],
        [(5, 8), (14, 19)], [(4, 7), (15, 18)], [(4, 6), (15, 17)], [(3, 6), (14, 16)],
        [(3, 5), (13, 16)], [(2, 6), (13, 18)], [(2, 7)], [(1, 4)]]), 0, 31)
    out["knight_jump2"] = j2
    # POWER STRIKE 40x48 (ax 4): the slash body, a heavy blade driven down-forward
    p = src("knight_slash")
    p[0:21, 27:40] = False                                 # sword, guard and arc
    over(p, "####\n####\n####\n.##.", 26, 12)                # fist
    over(p, "#\n#\n#\n#\n#\n#\n#", 30, 9)                     # crossguard
    for k in range(3):
        line(p, 30 + k, 14, 37 + k, 40)                     # blade, 3 px
    over(p, "#.#\n.#.\n#.#", 37, 42)                         # ground spark
    over(p, "#...#\n.....\n..#..", 33, 43)
    arc(p, 27, 14, 12, 14, -1.6, 0.9, 30, 2)                 # swing path, dotted
    arc(p, 27, 14, 8, 10, -1.5, 0.6, 16, 2)
    out["knight_power"] = p
    # WHIRLWIND 40x48 (ax 8): body centred, sword horizontal, spinning ring of the blade
    w = fit(knight_no_sword(), 40, 48, 8)
    line(w, 27, 20, 39, 20)
    line(w, 27, 21, 38, 21)
    over(w, "#\n#\n#\n#", 26, 18)                            # guard
    over(w, "###\n###", 23, 19)                              # hand
    arc(w, 19, 22, 19, 6, 0.25, np.pi - 0.1, 26, 2)          # front half (below)
    arc(w, 19, 22, 19, 6, np.pi + 0.15, 2 * np.pi - 0.3, 22, 3)   # back half, sparser
    over(w, "#.#.#\n.....\n#.#.#", 0, 19)                    # back blur
    out["knight_whirl"] = w
    # THROW 32x48 (ax 0): arm snapped forward-up, hand open at release
    t = fit(knight_no_sword(), 32, 48)
    for k in range(3):
        line(t, 17, 15 + k, 26, 8 + k)
    over(t, ".#.#\n####\n###.\n.#..", 26, 5)                 # open hand
    over(t, "#..\n.#.\n..#", 29, 10)                          # release flick
    out["knight_throw"] = t
    # BOW 32x48 (ax 0): bow arm straight, string at the chin, arrow nocked
    bw = fit(knight_no_sword(), 32, 48)
    line(bw, 17, 17, 25, 17)
    line(bw, 17, 18, 25, 18)
    from concept_r2_frames import BOW_V
    paste(bw, BOW_V, 25, 8)
    line(bw, 25, 8, 19, 17)                                  # string
    line(bw, 25, 25, 19, 18)
    line(bw, 19, 17, 31, 17)                                 # arrow
    over(bw, "#\n##\n#", 30, 16)
    out["knight_bow"] = bw
    return out


# ---------------------------------------------------------------------------
# Mage (wizard)
# ---------------------------------------------------------------------------

def wizard() -> dict:
    idle = src("wizard_idle")
    j1 = crouch(idle, [31, 33, 35, 37, 39])                  # robe folds as the knees bend
    j2 = idle.copy()
    j2[41:48] = False                                        # feet lifted, hem flares
    paste(j2, R(24, [[(2, 18)], [(1, 6), (8, 12), (14, 19)], [(0, 3), (17, 20)]]), 0, 41)
    return {"wizard_jump1": j1, "wizard_jump2": j2}


# ---------------------------------------------------------------------------
# Necromancer Archmage (final boss): crowned cowl, skull face, spiked mantle,
# floor-length robe with a rune strip, crescent staff. Distinct from Necromancer.
# ---------------------------------------------------------------------------

def archmage_body() -> np.ndarray:
    b = blank(24, 48)
    paste(b, R(24, [
        [(6, 6), (10, 10), (14, 14)],                        # crown spikes
        [(6, 6), (10, 10), (14, 14)],
        [(5, 7), (9, 11), (13, 15)],
        [(5, 15)], [(5, 15)],
        [(4, 16)],
        [(4, 9), (16, 16)],                                  # hood opening
        [(3, 8), (16, 16)],
        [(3, 8), (11, 12), (14, 14), (16, 16)],              # skull eyes
        [(3, 8), (10, 15), (16, 16)],
        [(3, 8), (11, 11), (13, 13), (15, 16)],              # teeth
        [(3, 9), (11, 14), (16, 17)],
        [(1, 1), (3, 17), (19, 19)],                         # mantle spikes
        [(0, 2), (3, 18)], [(0, 19)], [(1, 18)],
    ]), 0, 0)
    for y in range(16, 48):                                  # robe: waist in, hem flares
        x0, x1 = (2, 17) if y < 20 else (4, 15) if y < 30 else \
            (4 - (y - 30) // 5, 15 + (y - 30) // 4)
        b[y, max(0, x0):min(20, x1) + 1] = True
    b[17, :] = False
    b[17, 2:18] = True                                       # mantle edge
    b[16, 0:20] &= np.array([x % 3 != 2 for x in range(20)])
    b[20:34, 13] = False                                     # sleeve hangs in front
    for y in range(20, 34):
        b[y, 14:18] = True
    b[33, 13:19] = True
    b[34, 13:19] = False
    b[26, 4:13] = False                                      # belt
    b[27, 4:13] = np.array([x % 2 == 0 for x in range(4, 13)])
    over(b, "o.o\n.o.", 7, 26)                                # buckle skull
    for x0 in (6, 9, 12):                                    # robe folds (negative)
        for y in range(31, 46, 1):
            if (y + x0) % 4:
                b[y, x0 + (y - 31) // 8 * (1 if x0 > 9 else -1 if x0 < 9 else 0)] = False
    b[47, 1:20:3] = False                                    # ragged hem
    return b


def archmage() -> dict:
    i = archmage_body()
    # crescent staff at x 20..23
    over(i, "..##\n.#..\n#...\n#...\n.#..\n..##", 19, 0)
    i[3:48, 21] = True
    i[18:21, 19:22] = True                                   # hand on the staff
    c = fit(archmage_body(), 40, 48)
    over(c, "..##\n.#..\n#...\n#...\n.#..\n..##", 19, 0)
    c[3:48, 21] = True
    for k in range(3):                                       # casting arm, forward
        line(c, 14, 19 + k, 27, 17 + k)
    over(c, "###\n####\n###", 27, 16)
    # death orb: ring + core + motes, ahead of the palm
    yy, xx = np.mgrid[0:48, 0:40]
    r = np.hypot(xx - 34.5, yy - 18.5)
    c[(r > 3.6) & (r < 5.2)] = True
    c[r < 1.6] = True
    for x, y in ((31, 11), (38, 12), (39, 25), (30, 26), (35, 9)):
        c[y, x] = True
    return {"archmage_idle": i, "archmage_cast": c}


# ---------------------------------------------------------------------------
# Drain Life: twin dark strands spiralling (2-frame phase swap) + converging motes
# ---------------------------------------------------------------------------

def drain() -> dict:
    out = {}
    for k in (0, 1):
        b = blank(16, 8)
        for x in range(16):
            ph = x * 0.8 + k * np.pi / 2
            y1 = int(round(3.5 + 2.5 * np.sin(ph)))
            y2 = int(round(3.5 - 2.5 * np.sin(ph)))
            b[y1, x] = True
            if x % 2 == k:
                b[y2, x] = True
        b[2:6, 13:16] = True                                 # head bead
        b[3:5, 15] = False
        out[f"drain_fly{k + 1}"] = b
    h = blank(16, 16)
    for a in range(8):                                       # motes pulled inward
        th = a * np.pi / 4 + np.pi / 8
        for rr in (7, 4):
            x, y = int(round(7.5 + rr * np.cos(th))), int(round(7.5 + rr * np.sin(th)))
            h[y, x] = True
        line(h, int(round(7.5 + 6 * np.cos(th))), int(round(7.5 + 6 * np.sin(th))),
             int(round(7.5 + 5 * np.cos(th))), int(round(7.5 + 5 * np.sin(th))))
    over(h, ".##.\n####\n#..#\n.##.", 6, 6)                   # small heart-skull core
    out["drain_hit"] = h
    return out


# ---------------------------------------------------------------------------
# Hand pass: dead frames (32x16) and a lighter spider (32x24)
# ---------------------------------------------------------------------------

ZOMBIE_DEAD = T("""
................................
................................
................................
................................
................................
.........................#####..
....#.#.#...............#######.
.....#####..............###..##.
..##########.###......#.#######.
.############.####..###..#.#.#..
#####..#######.###########.###..
###..#.#.####..#####.##.###.....
.##...#..###########..#####.....
......##########################
.....#####...#.#..##.....#.#.#..
................................
""")

ORC_DEAD = T("""
................................
................................
................................
...................##...........
..................####.....#...#
...........#.#....####......#.#.
..........#####...#.##.....#####
.........###########......######
.#####..########.#####...###.###
######.###############.#########
###.###########..######.##.#.#..
.#.#############.##########.##..
..######...#######..############
..#####.....######......##.#.##.
................................
................................
""")

NECRO_DEAD = T("""
................................
................................
................................
................................
..............................#.
.............................###
............................#.#.
.....................#####...#..
...................#########.#..
.........#.#.#....##..#..###.#..
....##############...........#..
...###.#########.#####..####.#..
..#.#####.####.#####.######..#..
.#####.#####.####.#####.#######.
################################
................................
""")


def spider_frame(legs, body_dy: int = 0, fangs_open: bool = False) -> np.ndarray:
    """Lighter spider: 1-px legs (hip -> high knee -> foot), small body."""
    b = blank(32, 24)
    for (hx, hy), (kx, ky), (fx, fy) in legs:
        line(b, hx, hy + body_dy, kx, ky)
        line(b, kx, ky, fx, fy)
    body = R(32, [
        [(3, 7)], [(1, 9)], [(0, 10)], [(0, 10), (12, 15)], [(0, 16)], [(1, 15)],
        [(3, 7), (12, 14)]])
    body[2, 4] = body[3, 3] = body[3, 5] = body[4, 4] = False     # hourglass mark
    body[3, 14] = False                                       # eye
    paste(b, body, 8, 9 + body_dy)
    if fangs_open:
        over(b, "#..\n.#.\n#.#", 24, 12 + body_dy)
    else:
        over(b, "#.\n.#", 24, 14 + body_dy)
    return b


SP_WALK1 = [((11, 10), (6, 3), (1, 23)), ((14, 9), (11, 2), (7, 23)),
            ((19, 12), (23, 3), (26, 23)), ((21, 12), (27, 4), (31, 23))]
SP_WALK2 = [((11, 10), (7, 2), (3, 23)), ((14, 9), (10, 3), (9, 23)),
            ((19, 12), (24, 4), (24, 23)), ((21, 12), (26, 3), (29, 23))]
SP_BITE = [((11, 10), (6, 3), (1, 23)), ((14, 9), (11, 2), (7, 23)),
           ((19, 10), (24, 1), (30, 6)), ((21, 11), (27, 2), (31, 10))]


def spider() -> dict:
    w1 = spider_frame(SP_WALK1)
    w2 = spider_frame(SP_WALK2)
    # far-side legs, offset: 4 more 1-px legs make 8 without closing loops
    for b, legs in ((w1, SP_WALK2), (w2, SP_WALK1)):
        for (hx, hy), (kx, ky), (fx, fy) in legs:
            line(b, kx + 2, ky + 3, min(31, fx + 2), fy)
    bite = spider_frame(SP_BITE, -2, True)
    hurt = np.roll(spider_frame(SP_WALK2), (1, -1), (0, 1))
    hurt[0] = False
    hurt[:, -1] = False
    dead = T("""
................................
................................
.......#.#..#.#..#.#..#.#.......
......#...##...##...##...#......
......#...#.....#....#...#......
.......#..#.....#....#..#.......
........######..########........
......############.#######......
.....######.##############......
.....#######.#############......
......#####.#.#####..###.#......
.......##########..#####........
................................
................................
................................
................................
""")
    return {"spider_walk1": w1, "spider_walk2": w2, "spider_bite": bite,
            "spider_hurt": hurt, "spider_dead": dead}


INK = {"knight": "ink:cyan paper:black bright", "wizard": "ink:cyan paper:black bright",
       "archmage": "ink:magenta paper:black bright", "drain": "ink:blue paper:black bright",
       "zombie": "ink:green paper:black", "orc": "ink:green paper:black bright",
       "necro": "ink:magenta paper:black bright", "spider": "ink:red paper:black bright"}
AX = {"knight_power": 4, "knight_whirl": 8}


def build():
    hand = {"zombie_dead": ZOMBIE_DEAD, "orc_dead": ORC_DEAD, "necro_dead": NECRO_DEAD}
    for group in (knight(), wizard(), archmage(), drain(), hand, spider()):
        for n, bm in group.items():
            add(n, bm, INK[n.split("_")[0]], AX.get(n, 0))


def write():
    L = ["# WazHack/ZX CONCEPT round-3 sprite frames — GENERATED by tools/concept_r3_frames.py",
         "# (edit that script). Same block format as r2_frames.grid; frames with a round-2 name",
         "# (zombie/orc/necro dead, spider_*) supersede the round-2 drafts. DRAFT for review.", ""]
    for n, bm, ink, ax in FRAMES:
        h, w = bm.shape
        L.append(f"=== {n} {w}x{h} {ink} ax:{ax}")
        L += ["".join("#" if v else "." for v in r) for r in bm]
        L.append("")
    open(OUT, "w").write("\n".join(L))


if __name__ == "__main__":
    build()
    write()
    print(f"wrote {OUT}: {len(FRAMES)} frames")
