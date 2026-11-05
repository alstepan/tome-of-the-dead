#!/usr/bin/env python3
"""concept_r4_frames.py — deterministic authoring of the CONCEPT round-4 sprite frames.

Writes assets/gfx/concept/grid/r4_frames.grid (2-state block format; tools/concept_screen.py
derives the 3-state F8 masks). Same method as concept_r2/r3_frames.py: polygons, inclusive
spans and existing canvas frames with explicit edits. Parts are LAYERED: a part drawn over
another first clears a 1-px paper gap around itself, so overlapping limbs stay readable in
one ink. No AI raster.

  vampire       walk1/2 24x48, bite 32x48, hurt 24x48, dead 32x16   (replaces the zombie)
  ogre          walk1/2 32x48, raise 40x48, slam 40x48, hurt 32x48, dead 40x16 (D4 boss)
  death knight  walk1/2 24x48, windup 32x48, cleave 40x48, block 32x48 — from the knight's
                own frames (horned helm, no plume, tattered cape). DEAD reuses knight_dead.

Usage: python3 tools/concept_r4_frames.py
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from concept_r2_frames import (R, src, fit, line, over, paste, blank, T, trim, lean,  # noqa: E402
                               LEGS_STRIDE, LEGS_PASS, dead_from)
from gen_missing_frames import poly  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "assets/gfx/concept/grid/r4_frames.grid")
FRAMES: list = []


def add(name, bm, ink, ax=0):
    h, w = bm.shape
    assert w % 8 == 0 and h % 8 == 0 and w <= 40, (name, w, h)
    assert ax % 4 == 0 and 0 <= ax <= 8, (name, ax)
    FRAMES.append((name, bm.astype(bool), ink, ax))


def dil(b):
    p = np.pad(b, 1)
    o = np.zeros_like(p)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            o |= np.roll(np.roll(p, dy, 0), dx, 1)
    return o[1:-1, 1:-1]


def layer(dst, part):
    """Draw `part` over `dst` with a 1-px paper separation (single-ink depth cue)."""
    dst &= ~dil(part)
    dst |= part
    return dst


def P(w, h, pts):
    b = blank(w, h)
    poly(b, pts)
    return b


def ell(w, h, cx, cy, rx, ry):
    yy, xx = np.mgrid[0:h, 0:w]
    return ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0


# ---------------------------------------------------------------------------
# Vampire (24x48): slick hair with a widow's peak, high collar, cape flaring behind,
# pale face with paper eyes and fangs, claws forward
# ---------------------------------------------------------------------------

def vampire_parts(legs: np.ndarray, reach: int = 0, open_mouth: bool = False, w: int = 24,
                  veil: bool = True):
    """veil=True: the classic pose, forearm raised, cape drawn across the lower face.
    veil=False: cape thrown open behind like wings, claws out, fangs bared."""
    back = P(w, 48, [(9, 12), (4, 10), (2, 14), (1, 30), (0, 44), (2, 42), (4, 46), (6, 43),
                     (8, 47), (10, 44), (11, 30)])
    if not veil:
        back |= P(w, 48, [(8, 12), (3, 6), (0, 8), (0, 30), (2, 27), (3, 33), (5, 29), (6, 34),
                          (9, 28)])                       # wing-like spread
    collar = P(w, 48, [(4, 2), (7, 7), (9, 12), (3, 12), (2, 8)])
    body = P(w, 48, [(9, 12), (15, 12), (16, 22), (15, 31), (8, 31), (8, 20)])
    lg = blank(w, 48)
    paste(lg, legs[:, :min(w, 24)] & (np.arange(min(w, 24)) >= 5), 0, 30)
    head = R(w, [[(10, 14)], [(9, 15)], [(8, 16)], [(8, 11), (13, 16)], [(8, 10), (14, 16)],
                 [(8, 16)], [(9, 16)], [(9, 16)], [(9, 15)], [(10, 14)]])
    hd = blank(w, 48)
    paste(hd, head, 0, 2)
    over(hd, "o..o", 12, 6)                                   # eyes (paper)
    over(hd, "oo...oo\n..o.o..\n...o...", 9, 3)               # widow's peak hairline
    if not veil:
        over(hd, "oooo\noooo", 12, 9)
        over(hd, "#.#\n...", 13, 9)                           # fangs
    b = back.copy()
    layer(b, collar)
    layer(b, lg)
    layer(b, body)
    layer(b, hd)
    if veil:
        front = P(w, 48, [(19, 8), (21, 9), (20, 13), (18, 22), (17, 31), (15, 29), (13, 32),
                          (11, 29), (9, 31), (9, 16), (12, 9)])      # cape held across the face
        layer(b, front)
        arm = blank(w, 48)
        for k in range(3):
            line(arm, 11, 15 + k, 19, 8 + k)                   # forearm under the cape edge
        b |= arm & ~dil(hd)
        over(b, "##\n##", 19, 7)                               # hand at the cape's edge
        b[9:30, 13] &= np.arange(9, 30) % 4 != 0               # cape fold (negative)
    else:
        arm = blank(w, 48)
        for k in range(3):
            line(arm, 13, 15 + k, 19 + reach, 18 + k)
        over(arm, "#.#.\n.#.#\n#.#.", 19 + reach, 17)        # claws
        layer(b, arm)
    return b


def vampire() -> dict:
    w1 = vampire_parts(LEGS_STRIDE)
    w2 = vampire_parts(LEGS_PASS)
    bite = fit(vampire_parts(LEGS_STRIDE, reach=6, open_mouth=True, w=32, veil=False), 32, 48)
    bite = lean(bite, 0, 30, 3)
    hurt = lean(w1, 0, 30, -3)
    dead = T("""
................................
................................
................................
................................
................................
................................
................................
................................
..............#..#..............
...#.#.....#########...#..#.....
....###..#############.###......
..#######.##.#####.##########...
.###########.###.#.###########..
###.#####.####.##.####.######.#.
.#..#.#..#.##.#..#.#.#..#.#..#..
................................
""")                                                          # cape heap + dust
    return {"vampire_walk1": w1, "vampire_walk2": w2, "vampire_bite": bite,
            "vampire_hurt": hurt, "vampire_dead": dead}


# ---------------------------------------------------------------------------
# Ogre Warlord (32x48 body): hunched mass, small horned head thrust forward, tusks,
# pot belly, thick legs, the Warlord's Cleaver
# ---------------------------------------------------------------------------

CLEAVER_BLADE = T("""
.#######
########
########
########
########
#######.
######..
""")


def ogre_body(stride: bool) -> np.ndarray:
    b = blank(32, 48)
    mass = P(32, 48, [(5, 12), (9, 7), (16, 6), (22, 9), (26, 14), (27, 24), (25, 32),
                      (8, 33), (5, 26)])
    belly = ell(32, 48, 18, 27, 8.5, 7)
    lg = blank(32, 48)
    if stride:
        poly(lg, [(9, 33), (15, 33), (13, 41), (11, 47), (5, 47), (7, 41)])
        poly(lg, [(17, 33), (23, 33), (25, 41), (27, 47), (20, 47), (19, 41)])
    else:
        poly(lg, [(10, 33), (16, 33), (16, 47), (9, 47)])
        poly(lg, [(18, 33), (23, 33), (24, 47), (17, 47)])
    back_arm = P(32, 48, [(5, 13), (8, 15), (7, 30), (8, 35), (3, 35), (2, 30), (3, 15)])
    loin = P(32, 48, [(9, 31), (24, 31), (22, 37), (18, 35), (15, 38), (12, 35)])
    hd = blank(32, 48)
    paste(hd, T("""
....######..
..#########.
.##########.
.###########
#.######.##.
#.######..##
.#.#########
.###########
.#########.#
.######.#.##
..#########.
...######...
"""), 18, 3)                                                  # brow, eye, nose, ear, tusk
    layer(b, back_arm)
    layer(b, lg)
    layer(b, mass)
    b |= belly
    layer(b, loin)
    layer(b, hd)
    b[22, 9:26] &= np.arange(9, 26) % 2 == 0                  # belt studs
    b[23, 9:26] = False
    for x, y in ((12, 11), (16, 10), (20, 12)):               # spiked pauldron
        b[y - 2:y, x] = True
    return b


def ogre_arm(b, hand, blade_at=None, blade_rot=0):
    arm = blank(b.shape[1], 48)
    for k in range(4):
        line(arm, 21, 15 + k, hand[0], hand[1] + k)
    over(arm, "####\n####\n####", hand[0], hand[1])
    layer(b, arm)
    if blade_at:
        bl = np.rot90(CLEAVER_BLADE, blade_rot)
        part = blank(b.shape[1], 48)
        paste(part, bl, *blade_at)
        layer(b, part)


def ogre() -> dict:
    w1, w2 = ogre_body(True), ogre_body(False)
    for b in (w1, w2):
        ogre_arm(b, (24, 26))
        line(b, 27, 29, 29, 33)                               # haft down-forward
        part = blank(32, 48)
        paste(part, CLEAVER_BLADE[:, :5], 27, 33)
        layer(b, part)
    raise_ = fit(ogre_body(True), 40, 48)
    arm = blank(40, 48)
    for k in range(4):
        line(arm, 18 + k, 14, 24 + k, 3)                      # arm straight up
    layer(raise_, arm)
    line(raise_, 25, 3, 33, 1)                                # haft back over the head
    part = blank(40, 48)
    paste(part, np.rot90(CLEAVER_BLADE, 1), 31, 0)
    layer(raise_, part)
    slam = fit(ogre_body(True), 40, 48)
    ogre_arm(slam, (27, 27))
    line(slam, 30, 30, 34, 37)
    part = blank(40, 48)
    paste(part, CLEAVER_BLADE, 32, 38)
    layer(slam, part)
    over(slam, "#..#..#\n.......\n#.#.#.#", 31, 45)          # ground cracks / dust
    over(slam, "#...\n.#..\n..#.", 36, 30)
    hurt = lean(w1, 0, 33, -3)
    dead = dead_from(w2, 40, 16, 3, 2)
    return {"ogre_walk1": w1, "ogre_walk2": w2, "ogre_raise": raise_, "ogre_slam": slam,
            "ogre_hurt": hurt, "ogre_dead": dead}


# ---------------------------------------------------------------------------
# Death Knight: the knight's frames, re-armoured (no plume -> horns, tattered cape)
# ---------------------------------------------------------------------------

def dk_body(legs: np.ndarray, w: int = 24, arm_to=None) -> np.ndarray:
    """Death Knight: crowned great helm with horns, spiked pauldrons, breastplate, tasset,
    tattered cape, armoured legs. Body occupies x 0..21 (24-px body box, ax 0)."""
    cape = P(w, 48, [(6, 13), (1, 18), (0, 41), (2, 38), (3, 45), (5, 40), (7, 46), (9, 36)])
    lg = blank(w, 48)
    paste(lg, legs, 0, 30)
    torso = P(w, 48, [(7, 15), (16, 15), (17, 22), (16, 29), (7, 29), (6, 22)])
    torso[16:28, 11] = False                                  # breastplate ridge
    tasset = R(w, [[(6, 17)], [(5, 18)], [(5, 8), (10, 13), (15, 18)], [(5, 7), (10, 12), (16, 18)]])
    ts = blank(w, 48)
    paste(ts, tasset, 0, 28)
    paul = blank(w, 48)
    for cx in (6, 17):
        yy, xx = np.mgrid[0:48, 0:w]
        paul |= ((xx - cx) / 5.2) ** 2 + ((yy - 15.5) / 3.2) ** 2 <= 1
    for x in (3, 6, 17, 20):                                  # pauldron spikes
        line(paul, x, 12, x, 10)
    paul[16, :] &= np.arange(w) % 2 == 0                      # rivet line
    helm = R(w, [[(8, 8), (11, 12), (15, 15)], [(8, 9), (11, 12), (14, 15)],   # crown
                 [(8, 15)], [(7, 16)], [(7, 16)], [(7, 16)], [(7, 16)],
                 [(7, 8), (16, 16)],                                        # eye slit
                 [(7, 16)], [(7, 12), (14, 16)], [(7, 12), (14, 16)],      # breath slot
                 [(8, 15)]])
    hm = blank(w, 48)
    paste(hm, helm, 0, 1)
    for k in (0, 1):                                          # horns, sweeping out and up
        line(hm, 6, 5 + k, 3, 2 + k)
        line(hm, 17, 5 + k, 20, 2 + k)
    hm[0:2, 2:4] = True
    hm[0:2, 20:22] = True
    b = cape.copy()
    layer(b, lg)
    layer(b, torso)
    layer(b, ts)
    layer(b, paul)
    layer(b, hm)
    return b


def greatsword(b, hilt, tip, guard_half=3):
    """2-handed greatsword: 3-px blade from the hilt to the tip, crossguard at the hilt."""
    (hx, hy), (tx, ty) = hilt, tip
    part = blank(b.shape[1], 48)
    for k in (-1, 0, 1):
        if abs(tx - hx) > abs(ty - hy):
            line(part, hx, hy + k, tx, ty + k)
        else:
            line(part, hx + k, hy, tx + k, ty)
    dx, dy = tx - hx, ty - hy
    n = max(1, int(np.hypot(dx, dy)))
    px, py = -dy / n, dx / n                                  # perpendicular
    line(part, int(round(hx - guard_half * px)), int(round(hy - guard_half * py)),
         int(round(hx + guard_half * px)), int(round(hy + guard_half * py)))
    layer(b, part)


def fist(b, x, y):
    part = blank(b.shape[1], 48)
    part[y:y + 4, x:x + 4] = True
    layer(b, part)


def arm(b, frm, to, t=3):
    part = blank(b.shape[1], 48)
    for k in range(t):
        line(part, frm[0], frm[1] + k, to[0], to[1] + k)
    layer(b, part)


def death_knight() -> dict:
    out = {}
    for k, legs in ((1, LEGS_STRIDE), (2, LEGS_PASS)):
        b = dk_body(legs)
        arm(b, (17, 17), (19, 21))
        greatsword(b, (20, 23), (21, 46), 3)                  # point down, rests on the floor
        fist(b, 18, 20)
        out[f"dknight_walk{k}"] = b
    wu = fit(dk_body(LEGS_STRIDE), 32, 48)
    arm(wu, (17, 16), (21, 10))
    greatsword(wu, (21, 9), (31, 0), 3)                       # raised high, ready to cleave
    fist(wu, 19, 8)
    out["dknight_windup"] = wu
    cl = fit(dk_body(LEGS_STRIDE), 40, 48)
    arm(cl, (17, 17), (24, 21))
    greatsword(cl, (26, 22), (39, 40), 3)                     # swung down-forward
    fist(cl, 23, 19)
    for t in np.linspace(-1.3, 0.6, 14):                      # swing trail
        x, y = int(round(25 + 14 * np.cos(t))), int(round(22 + 18 * np.sin(t)))
        if 0 <= x < 40 and 0 <= y < 48 and (x + y) % 2:
            cl[y, x] = True
    out["dknight_cleave"] = cl
    bl = fit(lean(dk_body(LEGS_PASS), 0, 30, -1), 32, 48)
    arm(bl, (17, 17), (21, 20))
    greatsword(bl, (23, 24), (23, 2), 4)                      # blade upright: parry
    fist(bl, 21, 23)
    over(bl, "#.\n.#\n#.", 27, 8)                             # parry spark
    out["dknight_block"] = bl
    return out


INK = {"vampire": "ink:red paper:black bright", "ogre": "ink:magenta paper:black bright",
       "dknight": "ink:white paper:black bright"}
AX = {}


def build():
    for g in (vampire(), ogre(), death_knight()):
        for n, bm in g.items():
            add(n, bm, INK[n.split("_")[0]], AX.get(n, 0))


def write():
    L = ["# Tome of the Dead CONCEPT round-4 sprite frames — GENERATED by tools/concept_r4_frames.py",
         "# (edit that script). Same block format as r2/r3_frames.grid. DRAFT for review.", ""]
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
