#!/usr/bin/env python3
"""gen_art16.py — ART16 (2026-10-30) CONCEPT: the OGRE WARLORD and the GOLDEN PHARAOH
redrawn as true SIDE-VIEW profiles (facing right; the left facing is the mirror made at
level entry), three options each. Review artefact only: NOT engine data, nothing in
index*.asm / frames.asm / SRC6.

DROP-IN geometry (no engine change for the Ogre): every frame keeps the slot, size, flags,
ax and cycle of the frame it replaces.
  OGRE (K_OGRE, body 32, 48 rows, ax 0): ogre_walk1 32x48 WK0 (rest / idle / hurt base),
  ogre_walk2 32x48 WK4, ogre_raise 32x48 STA, ogre_slam 40x48 STA; og_move = MOVECYC2
  walk2, walk1; og_attack = RAISE 3 ticks -> SLAM 2 (impact); HURT = walk1 + the flash.
  PHARAOH (today the gold-tinted K_MUMMY frames, body 24, 40 rows, ax 0): pharaoh_walk1
  24x40 WK0, walk2 WK4, walk3 WK4, walk4 WK0, attack 32x40 STA; mu_move = MOVECYC4 walk2,
  walk4, walk3, walk1 (B4); attack = walk1 3 ticks -> ATTACK 2; HURT = walk1 + flash. The
  ATTACK frame is drawn to double as the SUMMON pose (crook / staff raised at the hero).

Walk rule (tests/walk_feet.py, applied here to the concept frames): for each consecutive
slot pair (cyclic) the next frame's sole row, put 4 px further on, overlaps the current
frame's sole row by >= 3 ink px (a planted foot), sole rows never empty, heights equal.
Head top constant over the walk frames (no bob).
Checks (exit 1): sizes, gfx_convert --layout native clash + data / mask round-trip in every
ink shown, walk contact, head top. Costs: frames.asm FRM pool formula + zx0 packed with the
zx0_sources.partition rule (blocks of <= 4 frames of one kind), against the frames in the
build today (zx0_pack.game_frames, the 40-px override).
Writes assets/gfx/concept/art16/: grid/*.grid, anim/*.gif, art16_ogre_pharaoh.svg.html
(board F3q), art16.png, costs.txt.   Usage: python3 tools/gen_art16.py
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_3f_art as G3  # noqa: E402
import gen_art13_nun as N  # noqa: E402  (also points zx0_pack at the main checkout's zx0)
import gen_art2_options as A  # noqa: E402
import svg_sprites as S  # noqa: E402
import zx0_pack as zp  # noqa: E402
import zx0_sources as zs  # noqa: E402

REPO = S.REPO
OUT = os.path.join(REPO, "assets/gfx/concept/art16")
GRID_OUT = os.path.join(OUT, "grid")
ANIM = os.path.join(OUT, "anim")

OGRE_INK = "#00FF00"                                # $44 Ogre Warlord
GOLD = (("$06 GOLD", "#D7D700"), ("$46 GLOW", "#FFFF00"), ("$47 GLOW", "#FFFFFF"))
PH_INK = "#D7D700"
SRC6_FREE = 57                                      # B free in the 16 SRC6 pages (2390dec)
POOL_CAP = 32269
NEED = {"D4 Warrior": 30240, "D4 Mage": 27168, "D5 Warrior": 24736, "D5 Mage": 21664}
FID_USED, FRT_MAX = 144, 144


# ===========================================================================
# drawing primitives (bool [y, x], True = ink)
# ===========================================================================
def cv(w, h):
    return np.zeros((h, w), bool)


def put(b, m, sep=False, on=True):
    if not on:
        b[m] = False
        return m
    if sep:
        b[G3.dilate4(m) & ~m] = False
    b |= m
    return m


def poly(b, pts, sep=False, on=True):
    im = Image.new("1", (b.shape[1], b.shape[0]), 0)
    ImageDraw.Draw(im).polygon([tuple(p) for p in pts], fill=1, outline=1)
    return put(b, np.array(im, bool), sep, on)


def ell(b, cx, cy, rx, ry, sep=False, on=True):
    return put(b, G3.ellipse(b.shape, cx, cy, rx, ry), sep, on)


def ln(b, pts, w=1, sep=False, on=True):
    m = np.zeros_like(b)
    for (a, c), (d, e) in zip(pts, pts[1:]):
        for x, y in G3.line_pts(a, c, d, e):
            y0, x0 = y - (w - 1) // 2, x - (w - 1) // 2
            m[max(y0, 0):max(y0 + w, 0), max(x0, 0):max(x0 + w, 0)] = True
    return put(b, m, sep, on)


def art(b, txt, x, y, sep=False):
    """'#' ink, 'o' paper cut, anything else untouched. sep rings the '#'+'o' area."""
    m, cut = np.zeros_like(b), np.zeros_like(b)
    for j, r in enumerate(txt.strip("\n").splitlines()):
        for i, c in enumerate(r):
            Y, X = y + j, x + i
            if 0 <= Y < b.shape[0] and 0 <= X < b.shape[1]:
                if c == "#":
                    m[Y, X] = True
                elif c == "o":
                    cut[Y, X] = True
    if sep:
        b[G3.dilate4(m | cut) & ~(m | cut)] = False
    b |= m
    b[cut] = False


def px(b, pts, on=True):
    for x, y in pts:
        if 0 <= y < b.shape[0] and 0 <= x < b.shape[1]:
            b[y, x] = on


def wraps(b, region, step=4, slope=1, phase=0):
    """Mummy bandage seams: diagonal paper lines inside `region` (bool mask)."""
    h, w = b.shape
    for y in range(h):
        for x in range(w):
            if region[y, x] and (x * slope + y + phase) % step == 0:
                b[y, x] = False


def hatch(b, region, phase=0):
    for y in range(b.shape[0]):
        for x in range(b.shape[1]):
            if region[y, x] and (x + phase) % 2:
                b[y, x] = False


def leg(b, hip, knee, ankle, w_th, w_sh, foot, sep):
    m = np.zeros_like(b)
    ln(m, [hip, knee], w_th)
    ln(m, [knee, ankle], w_sh)
    art(m, foot[0], foot[1], foot[2])
    return put(b, m, sep)


# ===========================================================================
# OGRE (32 x 48, floor row 47, faces right). Feet: walk1 (far heel p, near heel q),
# walk2 (p - 4, q + 4): walk2 -> walk1 the near foot is planted, walk1 -> walk2 the far.
# ===========================================================================
OH, OF = 48, 47
OG_FEET = {"walk1": (6, 15), "walk2": (2, 19)}
OG_FOOT = """
.#####...
########.
#########
#########
"""


def ogre_legs(b, pose, hips=((10, 33), (16, 33)), th=7, sh=6, knee_dy=0):
    fx, nx = OG_FEET[pose]
    for i, heel in enumerate((fx, nx)):
        hx, hy = hips[i]
        ax, ay = heel + 3, OF - 3
        kx, ky = (hx + ax) // 2 + 2, 39 + knee_dy
        leg(b, (hx, hy), (kx, ky), (ax, ay), th, sh, (OG_FOOT, heel, OF - 3), sep=(i == 1))


# --- the shared OGRE head: a profile with a low sloping brow, a deep eye socket under the
# brow ridge (the face edge steps back 3 px there), a bulb nose, a mouth line and an
# under-biting jaw with a tusk. Drawn WITHOUT a paper ring so its back melts into the hump;
# only the chin gets a cut line (OG_CHIN).
OG_HEAD = """
...######.......
.#########......
############....
#############...
###############.
#########oooo##.
#####o###o#o....
####o#o##oo##...
#####o#########.
################
#############...
#########ooo#...
##############..
###############.
.#############..
....#########...
"""


def og_head(b, x, y, chin=True):
    art(b, OG_HEAD, x, y)
    if chin:
        ln(b, [(x + 4, y + 16), (x + 13, y + 16)], 1, on=False)
        ln(b, [(x + 13, y + 15), (x + 14, y + 15)], 1, on=False)


def og_arm(b, pts, fist, w=5, fr=3.0):
    """Near arm: a shoulder ball, a thick limb, a fist; ringed in paper (in front)."""
    m = np.zeros_like(b)
    ell(m, pts[0][0], pts[0][1] + 1, 4, 3.5)
    ln(m, pts, w)
    ell(m, fist[0], fist[1], fr, fr)
    put(b, m, sep=True)
    return m


# --- A: CLUB BRUTE -----------------------------------------------------------
def ogre_a(pose):
    w = 40 if pose == "slam" else 32
    b = cv(w, OH)
    poly(b, [(5, 16), (7, 11), (11, 8), (16, 8), (19, 11), (24, 17), (28, 22), (29, 26),
             (28, 30), (24, 33), (8, 34), (5, 31), (4, 24)])
    og_head(b, 14, 3)
    ln(b, [(6, 29), (27, 29)], 1, on=False)            # belt
    ln(b, [(23, 20), (26, 25)], 1, on=False)           # belly fold
    px(b, [(8, 17), (7, 22), (9, 25)], on=False)       # hide warts
    ogre_legs(b, "walk2" if pose == "walk2" else "walk1")
    poly(b, [(17, 30), (24, 30), (23, 38), (18, 38)], sep=True)   # loincloth flap
    ln(b, [(18, 33), (23, 33)], 1, on=False)
    if pose in ("walk1", "walk2"):                      # club over the near shoulder
        ln(b, [(18, 24), (6, 6)], 2, sep=True)
        ell(b, 5, 4, 4.5, 4.5, sep=True)
        px(b, [(0, 1), (4, 0), (9, 1), (0, 6)])
        og_arm(b, [(11, 13), (12, 21), (17, 24)], (19, 24))
    elif pose == "raise":                               # club high behind the head
        ln(b, [(11, 2), (5, 12)], 2, sep=True)
        ell(b, 4, 15, 4.5, 4.5, sep=True)
        px(b, [(0, 11), (0, 18), (4, 21), (9, 19)])
        og_arm(b, [(11, 13), (9, 7), (11, 3)], (11, 2), fr=2.6)
    else:                                               # slam: club down in front
        og_arm(b, [(11, 13), (18, 19), (25, 22)], (26, 22))
        ln(b, [(27, 24), (33, 37)], 2, sep=True)
        ell(b, 34, 42, 4.5, 4.5, sep=True)
        px(b, [(39, 37), (29, 38), (39, 46), (28, 46), (27, 47), (39, 47)])
    return b


# --- B: WARLORD CLEAVER (horned helm, braided beard, pauldron, the Warlord's Cleaver) --
def ogre_b(pose):
    w = 40 if pose == "slam" else 32
    b = cv(w, OH)
    poly(b, [(5, 17), (8, 12), (12, 9), (17, 9), (21, 13), (25, 18), (28, 23), (28, 28),
             (26, 31), (22, 33), (8, 34), (5, 31), (4, 24)])
    og_head(b, 14, 4, chin=False)
    helm = np.zeros_like(b)                             # helm over the brow, rim at row 9
    poly(helm, [(14, 7), (16, 4), (19, 2), (24, 2), (27, 4), (29, 7)])
    put(b, helm, sep=True)
    ln(b, [(15, 6), (28, 6)], 1, on=False)
    ln(b, [(17, 4), (15, 1), (14, 0)], 2, sep=True)               # horn rising from the helm side
    px(b, [(14, 0)])
    for x in range(19, 28, 2):                          # braided beard over the jaw
        ln(b, [(x, 16), (x, 20 - (x - 19) // 3)], 1, on=False)
    ogre_legs(b, "walk2" if pose == "walk2" else "walk1")
    ln(b, [(5, 28), (27, 28)], 1, on=False)            # belt + buckle
    ln(b, [(5, 30), (26, 30)], 1, on=False)
    art(b, "###\n#o#\n###", 22, 28, sep=True)
    poly(b, [(16, 31), (24, 31), (25, 39), (17, 39)], sep=True)     # tasset
    ln(b, [(17, 34), (24, 34)], 1, on=False)
    paul = lambda: (ell(b, 11, 14, 5, 4, sep=True), ln(b, [(7, 15), (15, 15)], 1, on=False),
                    px(b, [(9, 13), (12, 12)], on=False))
    if pose in ("walk1", "walk2"):                      # cleaver held low, blade forward
        og_arm(b, [(11, 15), (13, 22), (18, 26)], (19, 26), w=5)
        art(b, "o######\n#####o#\n########\n########\n#######o\n######oo", 22, 21, sep=True)
        ln(b, [(19, 26), (22, 24)], 2, sep=True)
        ell(b, 19, 26, 2.6, 2.6, sep=True)
        paul()
    elif pose == "raise":                               # cleaver overhead, blade back
        paul()
        og_arm(b, [(11, 15), (8, 8), (10, 3)], (10, 2), fr=2.6)
        art(b, "o######\n#o#####\n#######\n#######\n######o\n#####oo", 1, 0, sep=True)
        ln(b, [(9, 2), (7, 2)], 2, sep=True)
        ell(b, 10, 2, 2.4, 2.2, sep=True)
    else:                                               # slam: cleaver chopped down in front
        paul()
        og_arm(b, [(11, 15), (19, 21), (26, 24)], (27, 24))
        ln(b, [(28, 26), (30, 32)], 2, sep=True)
        art(b, "#######\n#o######\n########\n########\n########\n########\n#######o\n######oo",
            29, 33, sep=True)
        px(b, [(38, 41), (37, 44), (28, 46), (39, 47), (28, 44)])
    return b


# --- C: KNUCKLE DRAGGER ------------------------------------------------------
def ogre_c(pose):
    w = 40 if pose == "slam" else 32
    b = cv(w, OH)
    poly(b, [(3, 22), (5, 14), (9, 9), (15, 7), (20, 9), (23, 13), (26, 18), (27, 24),
             (26, 29), (23, 33), (8, 34), (4, 30)])
    og_head(b, 17, 7)
    hatch(b, G3.ellipse(b.shape, 9, 12, 5, 3) & b)      # shaggy mane on the hump
    ln(b, [(5, 30), (25, 30)], 1, on=False)            # pelt belt
    px(b, [(8, 31), (12, 32), (16, 31), (20, 32)], on=False)
    ln(b, [(5, 18), (7, 14)], 1, on=False)
    ogre_legs(b, "walk2" if pose == "walk2" else "walk1", th=8, sh=6)
    knuck = ".####.\n######\n######\n#o#o##\n.####."
    if pose == "walk1":                                 # long near arm, knuckles low
        og_arm(b, [(13, 14), (16, 25), (20, 35)], (21, 36), w=6, fr=1)
        art(b, knuck, 18, 35, sep=True)
    elif pose == "walk2":
        og_arm(b, [(13, 14), (18, 25), (24, 32)], (25, 33), w=6, fr=1)
        art(b, knuck, 23, 32, sep=True)
    elif pose == "raise":                               # both fists up overhead
        og_arm(b, [(13, 14), (11, 8), (13, 3)], (13, 2), w=6, fr=1)
        art(b, ".######.\n########\n########\n#o#o#o##\n.######.", 9, 0, sep=True)
    else:                                               # slam: fists pound the floor ahead
        og_arm(b, [(13, 14), (21, 25), (28, 38)], (29, 39), w=6, fr=1)
        art(b, ".######.\n########\n########\n#o#o#o##\n########\n.######.", 26, 39, sep=True)
        px(b, [(36, 37), (38, 40), (24, 46), (39, 44), (37, 35)])
    return b


OGRE = {"A": ("CLUB BRUTE", ogre_a), "B": ("WARLORD CLEAVER", ogre_b), "C": ("KNUCKLE DRAGGER", ogre_c)}
OG_FRAMES = (("ogre_walk1", "walk1", "WK0", 32), ("ogre_walk2", "walk2", "WK4", 32),
             ("ogre_raise", "raise", "STA", 32), ("ogre_slam", "slam", "STA", 40))


# ===========================================================================
# PHARAOH (24 x 40, floor row 39, faces right). B4 cycle slots walk2, walk4, walk3, walk1:
# near foot heel 14, 10, 6, 10 (planted walk2 -> walk4 -> walk3), far foot 6, 10, 14, 10
# (planted walk3 -> walk1 -> walk2); the swinging foot is lifted 1-2 px (walk4: the far
# foot passing, walk1: the near foot drawn up beside the planted one = the rest stance).
# ===========================================================================
PH, PF = 40, 39
PH_FEET = {"walk2": ((6, 0), (14, 0)), "walk4": ((10, 2), (10, 0)),
           "walk3": ((14, 0), (6, 0)), "walk1": ((10, 0), (11, 1))}    # (far, near): (heel, lift)
PH_FOOT = ".###..\n######"
PH_FOOT_UP = ".###.\n#####"


def bandage(b, region, phase=0, every=3):
    """Mummy wrappings: short paper dashes on every `every`-th row, staggered row to row,
    never on a run's edge pixel (the silhouette stays whole)."""
    h, w = b.shape
    for y in range(h):
        if (y + phase) % every:
            continue
        k = (y + phase) // every
        for x in range(1, w - 1):
            if region[y, x] and region[y, x - 1] and region[y, x + 1] and (x + 2 * k) % 4 < 2:
                b[y, x] = False


def ph_legs(b, pose, hips=((9, 29), (12, 29))):
    soles = np.zeros(b.shape[1], bool)
    for i, (heel, lift) in enumerate(PH_FEET[pose]):
        hx, hy = hips[i]
        ax, ay = heel + 2, PF - 2 - lift
        kx, ky = (hx + ax) // 2 + (1 if lift else 0), 34 - lift
        m = np.zeros_like(b)
        ln(m, [(hx, hy), (kx, ky)], 4)
        ln(m, [(kx, ky), (ax, ay)], 3)
        art(m, PH_FOOT_UP if lift else PH_FOOT, heel, PF - 1 - lift)
        bandage(m, m.copy() & (np.arange(PH)[:, None] < PF - 2), i)
        put(b, m, sep=(i == 1))
        if not lift:
            soles |= m[PF]
    b[PF] |= soles


# --- A: NEMES KING (crook) ---------------------------------------------------
PA_HEAD = """
....######.....
..#########....
.###########...
#############..
#ooo###oooooo#.
########o####..
#ooo####o#####.
########o##o#..
#ooo####o######
########o####..
#ooo####o#####.
########o#oo#..
#ooo#####o####.
.#######o#o##..
..######..o##..
...####....##..
"""


def ph_collar(b, x0, x1, y):
    poly(b, [(x0, y), (x1, y), (x1, y + 2), (x0, y + 2)], sep=True)
    px(b, [(x, y + 1) for x in range(x0 + 1, x1, 2)], on=False)


def pharaoh_a(pose):
    w = 32 if pose == "attack" else 24
    b = cv(w, PH)
    ph_legs(b, "walk1" if pose == "attack" else pose)
    t = poly(cv(w, PH), [(6, 15), (14, 15), (15, 19), (15, 24), (14, 28), (7, 28), (6, 23)])
    put(b, t, sep=True)
    bandage(b, t, 0)
    poly(b, [(6, 26), (13, 26), (17, 31), (7, 31)], sep=True)          # shendyt kilt, apron front
    ln(b, [(12, 27), (15, 31)], 1, on=False)
    ln(b, [(7, 28), (11, 28)], 1, on=False)
    art(b, PA_HEAD, 3, 0, sep=True)
    px(b, [(16, 2), (16, 3)])                                           # uraeus
    ph_collar(b, 5, 14, 15)
    if pose != "attack":                                # crook held up before the chest
        ln(b, [(10, 18), (12, 22), (16, 21)], 3, sep=True)
        ln(b, [(18, 28), (18, 10)], 1, sep=True)
        art(b, ".##.\n#..#\n#..#\n...#", 18, 6)
        art(b, "##\n##", 17, 20, sep=True)
    else:                                               # curse / summon: crook raised at the hero
        ln(b, [(10, 18), (15, 16), (20, 14)], 3, sep=True)
        art(b, "###\n###", 21, 13, sep=True)
        ln(b, [(22, 12), (26, 4)], 1, sep=True)
        art(b, ".##.\n#..#\n#..#\n...#", 25, 0)
        ln(b, [(11, 20), (17, 21), (23, 20)], 2, sep=True)
        art(b, "#.#.#\n#.#.#", 24, 20)
        px(b, [(30, 6), (30, 9), (31, 3), (27, 23)])
    return b


# --- B: RISEN LURCHER (torn nemes, skull face, arms out) -----------------------
PB_HEAD = """
...######.....
.#########....
###########...
############..
#oo#oooooo###.
#######o####..
#oo####o#####.
#######o#oo#..
#oo####o#oo##.
#######o#####.
#o#o###o#o#o#.
#.#.###o#####.
#...#.##o###..
........###...
"""


def pharaoh_b(pose):
    w = 32 if pose == "attack" else 24
    b = cv(w, PH)
    ph_legs(b, "walk1" if pose == "attack" else pose)
    t = poly(cv(w, PH), [(5, 16), (9, 14), (14, 15), (16, 19), (15, 24), (14, 29), (7, 29), (5, 23)])
    put(b, t, sep=True)
    bandage(b, t, 1)
    art(b, PB_HEAD, 6, 1, sep=True)
    poly(b, [(6, 27), (14, 27), (15, 30), (6, 30)], sep=True)          # belt sash
    ln(b, [(7, 28), (14, 28)], 1, on=False)
    trail = {"walk1": [(7, 29), (4, 33), (3, 37)], "walk2": [(7, 29), (3, 32), (1, 35)],
             "walk3": [(7, 29), (3, 33), (2, 37)], "walk4": [(7, 29), (4, 32), (2, 35)],
             "attack": [(7, 29), (3, 31), (0, 33)]}[pose]
    ln(b, trail, 1)                                                     # loose bandage trailing
    if pose != "attack":                                # both arms stretched at the hero
        reach = 21
        ln(b, [(9, 17), (16, 18), (reach, 18)], 3)                     # far arm
        ln(b, [(10, 20), (16, 21), (reach, 22)], 3, sep=True)          # near arm
        art(b, "#.#\n#.#", reach - 1, 24)
        dang = {"walk1": (15, 25), "walk2": (14, 26), "walk3": (16, 26), "walk4": (15, 27)}[pose]
        ln(b, [(15, 23), dang], 1)                                      # dangling wrap
    else:                                               # lunge-grab / summon: hands up and out
        ln(b, [(9, 17), (17, 15), (27, 11)], 3)
        ln(b, [(10, 20), (18, 19), (28, 17)], 3, sep=True)
        art(b, "#.#.#\n#.#.#\n#...#", 27, 7)
        art(b, "#.#.#\n#.#.#", 28, 19)
        px(b, [(31, 14), (25, 9), (30, 23)])
    return b


# --- C: CROWNED SORCERER (hedjet, ankh staff) ---------------------------------
PC_HEAD = """
.....###.....
....#####....
....#####....
....######...
...#######...
...#######...
..########...
.##########..
#oooooooooo#.
###########..
##o#o#######.
###o####o##..
#############
##########...
###########..
#########o#..
.#########...
..#####o##...
...###..##...
........#....
"""


def pharaoh_c(pose):
    w = 32 if pose == "attack" else 24
    b = cv(w, PH)
    ph_legs(b, "walk1" if pose == "attack" else pose)
    t = poly(cv(w, PH), [(6, 18), (14, 18), (15, 21), (15, 25), (14, 29), (7, 29), (6, 25)])
    put(b, t, sep=True)
    bandage(b, t, 2)
    poly(b, [(3, 18), (7, 18), (7, 31), (3, 33)], sep=True)            # cloak down the back
    ln(b, [(5, 20), (5, 31)], 1, on=False)
    art(b, PC_HEAD, 4, 0, sep=True)
    ph_collar(b, 6, 14, 18)
    if pose != "attack":                                # ankh staff carried upright
        ln(b, [(10, 21), (14, 24), (17, 23)], 3, sep=True)
        ln(b, [(19, 13), (19, 34)], 1, sep=True)
        art(b, ".#.\n#o#\n#o#\n.#.\n###\n.#.", 18, 7, sep=True)
        art(b, "##\n##", 18, 22, sep=True)
    else:                                               # ankh thrust at the hero / summon
        ln(b, [(10, 21), (16, 19), (22, 18)], 3, sep=True)
        art(b, "##\n##", 22, 17, sep=True)
        ln(b, [(14, 18), (25, 18)], 1, sep=True)
        art(b, ".#.\n#o#\n#o#\n.#.", 26, 13, sep=True)
        art(b, "#.#", 25, 17)
        px(b, [(30, 11), (31, 15), (30, 20), (25, 10), (25, 23)])
    return b


PHARAOH = {"A": ("NEMES KING", pharaoh_a), "B": ("RISEN LURCHER", pharaoh_b),
           "C": ("CROWNED SORCERER", pharaoh_c)}
PH_FRAMES = (("pharaoh_walk1", "walk1", "WK0", 24), ("pharaoh_walk2", "walk2", "WK4", 24),
             ("pharaoh_walk3", "walk3", "WK4", 24), ("pharaoh_walk4", "walk4", "WK0", 24),
             ("pharaoh_attack", "attack", "STA", 32))
OG_CYC = ["walk2", "walk1"]
PH_CYC = ["walk2", "walk4", "walk3", "walk1"]


# ===========================================================================
# checks / costs
# ===========================================================================
def sole(bm):
    return {x for x in range(bm.shape[1]) if bm[-1, x]}


def contact(fr, cyc):
    out, bad = [], []
    for i, a in enumerate(cyc):
        nb = cyc[(i + 1) % len(cyc)]
        sa, sb = sole(fr[a]), sole(fr[nb])
        c = len({x + 4 for x in sb} & sa)
        out.append(c)
        if not sa or not sb or c < 3 or fr[a].shape[0] != fr[nb].shape[0]:
            bad.append(f"{a}->{nb} contact {c}")
    return out, bad


def packed_kind(raws, td):
    fr = list(raws)
    tot = 0
    for st, k in zs.partition(fr, td):
        tot += len(zs.pack(b"".join(d for _, d in fr[st:st + k]), td))
    return tot


def cur_frames(names):
    gf = dict(zp.game_frames())
    return [(n, gf[n]) for n in names]


def cur_bitmaps(names):
    out = {}
    for n in names:
        for d in ("assets/gfx/sprites40/grid", "assets/gfx/sprites/grid"):
            p = os.path.join(REPO, d, n + ".grid")
            if os.path.exists(p):
                out[n] = N.load_grid(p)
                break
    return out


# ===========================================================================
# rendering
# ===========================================================================
def strip(fr, seq, h, bw, facing, walk):
    W = (bw + 4 * len(seq) + 48) if walk else bw + 40
    out = []
    for i, n in enumerate(seq):
        bm = fr[n]
        xb = (8 + 4 * i if facing > 0 else W - bw - 8 - 4 * i) if walk else 16
        if facing > 0:
            out.append((bm, xb, 1, xb))
        else:
            out.append((np.fliplr(bm), xb - (bm.shape[1] - bw), 1, xb))
    return out, W, h + 2


def sheet(path, rows, scale=3):
    ims = []
    for lab, cells in rows:
        hh = max(b.shape[0] for b, _ in cells) + 4
        ps = []
        for bm, ink in cells:
            a = np.full((hh, bm.shape[1] + 4, 3), N.BG, np.uint8)
            N.blit(a, bm, 2, hh - 2 - bm.shape[0], ink)
            a[hh - 2, :] = (60, 60, 140)
            ps.append(Image.fromarray(a).resize((a.shape[1] * scale, hh * scale), Image.NEAREST))
        r = Image.new("RGB", (190 + sum(p.width + 6 for p in ps), hh * scale + 6), N.BG)
        ImageDraw.Draw(r).text((4, 4), lab, fill=(255, 255, 120))
        x = 190
        for p in ps:
            r.paste(p, (x, 3))
            x += p.width + 6
        ims.append(r)
    sh = Image.new("RGB", (max(i.width for i in ims), sum(i.height for i in ims)), N.BG)
    y = 0
    for i in ims:
        sh.paste(i, (0, y))
        y += i.height
    sh.save(path)


def gif(path, rows, W, Hh, ink, scale=3, ms=150):
    imgs = []
    for i in range(len(rows[0])):
        a = np.full((Hh * len(rows), W, 3), N.BG, np.uint8)
        for r, tk in enumerate(rows):
            sub = a[r * Hh:(r + 1) * Hh]
            sub[Hh - 1, :] = (60, 60, 140)
            b, x, y, _xb = tk[i]
            N.blit(sub, b, x, y, ink)
        imgs.append(Image.fromarray(a).resize((W * scale, a.shape[0] * scale), Image.NEAREST))
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=ms, loop=0)


# ===========================================================================
def build(kind, opts, frames, cyc, h, bw, inks, td, bad):
    """-> {opt: {frame: bitmap}}, {opt: packed}, pool per frame."""
    res, pk = {}, {}
    for o, (title, fn) in opts.items():
        fr = {}
        raws = []
        for name, pose, flag, w in frames:
            bm = fn(pose)
            if bm.shape != (h, w):
                bad.append(f"{kind} {o} {name}: shape {bm.shape}")
            fr[pose] = bm
            solid = S.make_mask(bm, outline=True)
            nm = f"{name}_{o.lower()}"
            g = os.path.join(GRID_OUT, nm + ".grid")
            with open(g, "w") as fh:
                fh.write(A.grid_text(nm, bm, solid, f"{kind} {o} {title} {pose.upper()}", inks[0],
                                     f"ART16 {kind} option {o} ({title}), {flag}, ax 0, body {bw}; "
                                     "tools/gen_art16.py; not imported")
                         .replace("tools/gen_art2_options.py", "tools/gen_art16.py"))
            for ink in inks:
                raw = A.pack_check(f"{nm}_{ink[1:]}", g, bm, solid, ink, td)
            raws.append((nm, raw))
        res[o] = fr
        pk[o] = packed_kind(raws, td)
        tops = {p: N.head_top(fr[p]) for p in cyc}
        if len(set(tops.values())) != 1:
            bad.append(f"{kind} {o}: walk head top {tops}")
        _c, cb = contact(fr, cyc)
        bad += [f"{kind} {o}: {x}" for x in cb]
    return res, pk


def main() -> int:
    for d in (GRID_OUT, ANIM):
        os.makedirs(d, exist_ok=True)
    bad = []
    og_names = [n for n, *_ in OG_FRAMES]
    mu_names = ["mummy_walk1", "mummy_walk2", "mummy_walk3", "mummy_walk4", "mummy_attack"]
    with tempfile.TemporaryDirectory() as td:
        og, og_pk = build("OGRE", OGRE, OG_FRAMES, OG_CYC, OH, 32, [OGRE_INK], td, bad)
        ph, ph_pk = build("PHARAOH", PHARAOH, PH_FRAMES, PH_CYC, PH, 24, [k for _, k in GOLD], td, bad)
        og_cur = packed_kind(cur_frames(og_names), td)
        mu_cur = packed_kind(cur_frames(mu_names), td)
    og_ref = cur_bitmaps(og_names)
    mu_ref = cur_bitmaps(mu_names)
    og_pool = sum(N.pool(OH, w, 0, 32, f) for _n, _p, f, w in OG_FRAMES)
    ph_pool = sum(N.pool(PH, w, 0, 24, f) for _n, _p, f, w in PH_FRAMES)
    ph_pool3 = N.pool(PH, 24, 0, 24, "WK0") + N.pool(PH, 24, 0, 24, "WK4") + N.pool(PH, 32, 0, 24, "STA")

    def pages(extra):
        need = max(0, extra - SRC6_FREE)
        return -(-need // 256)

    L = ["# ART16 Ogre / Golden Pharaoh side-view options — costs (tools/gen_art16.py).",
         "# pool = src/defs.asm FRM formula (both facings, one shift per flag); packed = zx0 with",
         "# the zx0_sources.partition rule, today's frames from zx0_pack.game_frames (40-px override).",
         f"# SRC6: {SRC6_FREE} B free of 16 pages; each further page costs 256 B of POOL_CAP on EVERY level.",
         f"# POOL_CAP {POOL_CAP}; slack today: " + ", ".join(f"{k} {POOL_CAP - v:,}" for k, v in NEED.items()),
         "",
         f"OGRE (drop-in: same 4 fids / sizes / flags / ax; pool {og_pool} B unchanged on D4)",
         f"  today  packed {og_cur} B"]
    for o in OGRE:
        d = og_pk[o] - og_cur
        L.append(f"  {o} {OGRE[o][0]:16s} packed {og_pk[o]} B  delta {d:+d} B SRC6"
                 + (f"  -> +{pages(d)} page(s): POOL_CAP -{256 * pages(d)} every level" if pages(d) else
                    "  (fits the free bytes)" if d > 0 else "  (saves)"))
    L += ["",
          "GOLDEN PHARAOH: today = the K_MUMMY frames + the gold glow attr (boss7 ai_guard: K_MUMMY |",
          "LEK_GOLD). A side-view Pharaoh that differs from the Mummy NEEDS ITS OWN FRAMES:",
          f"  5 fids (walk1..4 + attack, the Mummy's slots / flags / B4 cycle): pool +{ph_pool} B on D5 only",
          f"    (D5 slack Warrior {POOL_CAP - NEED['D5 Warrior']:,} -> {POOL_CAP - NEED['D5 Warrior'] - ph_pool:,},"
          f" Mage {POOL_CAP - NEED['D5 Mage']:,} -> {POOL_CAP - NEED['D5 Mage'] - ph_pool:,})",
          f"  frame ids: {FID_USED} of FRT_MAX {FRT_MAX} used (4 spare, earmarked for the approved nun Archmage):",
          "    5 more need FRT_MAX raised (engine: FRT table + kind/frame-group hook for the gold Mummy).",
          f"  lean alt (3 fids walk1/walk2 MOVECYC2 + attack, not drawn): pool +{ph_pool3} B on D5.",
          f"  today Mummy packed {mu_cur} B (unchanged: the Mummy keeps its frames)"]
    for o in PHARAOH:
        L.append(f"  {o} {PHARAOH[o][0]:16s} packed {ph_pk[o]} B = SRC6 +{ph_pk[o]} B"
                 f"  -> +{pages(ph_pk[o])} page(s): POOL_CAP -{256 * pages(ph_pk[o])} every level"
                 f" (D4 Warrior slack {POOL_CAP - NEED['D4 Warrior']:,} -> "
                 f"{POOL_CAP - NEED['D4 Warrior'] - 256 * pages(ph_pk[o]):,})")
    L += ["",
          "ZERO-COST alternative: apply the chosen Pharaoh option to the K_MUMMY frames themselves",
          "(Mummy and Pharaoh share the new side-view art again, gold = attr only): pool 0, fids 0,",
          "SRC6 delta = option packed - today Mummy packed: "
          + ", ".join(f"{o} {ph_pk[o] - mu_cur:+d} B" + (f" (+{pages(ph_pk[o] - mu_cur)} page)"
                                                         if pages(ph_pk[o] - mu_cur) else "")
                      for o in PHARAOH) + f" (free {SRC6_FREE} B, shared with the Ogre delta).",
          "  It changes the approved Mummy V2 look too (user call)."]
    with open(os.path.join(OUT, "costs.txt"), "w") as fh:
        fh.write("\n".join(L) + "\n")

    # ---- board ---------------------------------------------------------------
    bd = [N.heading("F3q ART16 — OGRE WARLORD + GOLDEN PHARAOH, SIDE VIEW (3 OPTIONS EACH)"),
          N.sub("Concept, not imported. Profiles face right (left = mirror). Drop-in geometry: same "
                "slots, sizes, flags, ax 0, cycles. HURT = the WALK1 rest pose + the hit flash (no frame, "
                "as today). The Pharaoh ATTACK frame doubles as the SUMMON pose.")]
    seq_og = {"WALK": [p for p in OG_CYC] * 3, "IDLE/HURT": ["walk1"] * 4,
              "SLAM": ["walk1"] * 3 + ["raise"] * 3 + ["slam"] * 2 + ["walk1"] * 3}
    seq_ph = {"WALK": PH_CYC * 3, "IDLE/HURT": ["walk1"] * 4,
              "ATTACK/SUMMON": ["walk1"] * 3 + ["attack"] * 3 + ["walk1"] * 3}
    for kind, res, opts, frames, seqs, h, bw, inks, ref in (
            ("OGRE", og, OGRE, OG_FRAMES, seq_og, OH, 32, [OGRE_INK], og_ref),
            ("PHARAOH", ph, PHARAOH, PH_FRAMES, seq_ph, PH, 24, [k for _, k in GOLD], mu_ref)):
        bd.append(N.heading(f"F3q {kind} TODAY"))
        bd.append(N.row([S.svg_artboard_html(b, inks[0], n.upper().replace("_", " ")) for n, b in ref.items()]))
        for o, (title, _fn) in opts.items():
            pk = (og_pk if kind == "OGRE" else ph_pk)[o]
            bd.append(N.heading(f"F3q {kind} {o} — {title}"))
            bd.append(N.sub(f"packed {pk} B (" + (f"today {og_cur} B, {pk - og_cur:+d}" if kind == "OGRE"
                                                  else f"own frames: pool +{ph_pool} B on D5") + ")"))
            bd.append(N.row([S.svg_artboard_html(res[o][p], inks[0], f"{kind} {o} {p.upper()}")
                             for _n, p, _f, _w in frames]))
            cells = []
            for lab, seq in seqs.items():
                walk = lab == "WALK"
                rows = [strip(res[o], seq, h, bw, fc, walk)[0] for fc in (1, -1)]
                _t, W, Hh = strip(res[o], seq, h, bw, 1, walk)
                for ink in inks[:1] if kind == "OGRE" else inks[:1]:
                    cells.append(N.anim_svg(rows, ink, W, Hh, f"{kind} {o} {lab}"))
                gif(os.path.join(ANIM, f"{kind.lower()}_{o.lower()}_{lab.split('/')[0].lower()}.gif"),
                    rows, W, Hh, inks[0])
            if kind == "PHARAOH":                       # the gold glow cycle on the walk
                rows = [strip(res[o], seq_ph["WALK"], h, bw, 1, True)[0]]
                _t, W, Hh = strip(res[o], seq_ph["WALK"], h, bw, 1, True)
                for lab, ink in GOLD[1:]:
                    cells.append(N.anim_svg(rows, ink, W, Hh, f"PHARAOH {o} WALK {lab}"))
            bd.append(N.row(cells))
    with open(os.path.join(OUT, "art16_ogre_pharaoh.svg.html"), "w") as fh:
        fh.write("\n".join(bd) + "\n")
    rows = [("OGRE today", [(b, OGRE_INK) for b in og_ref.values()])]
    rows += [(f"OGRE {o} {t}", [(og[o][p], OGRE_INK) for _n, p, _f, _w in OG_FRAMES]) for o, (t, _) in OGRE.items()]
    rows += [("MUMMY/PHARAOH today", [(b, PH_INK) for b in mu_ref.values()])]
    rows += [(f"PHARAOH {o} {t}", [(ph[o][p], PH_INK) for _n, p, _f, _w in PH_FRAMES]) for o, (t, _) in PHARAOH.items()]
    sheet(os.path.join(OUT, "art16.png"), rows)
    print("\n".join(L[6:]))
    if bad:
        print("FAIL:\n  " + "\n  ".join(bad))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
