#!/usr/bin/env python3
"""gen_art13_nun.py — ART13 (2026-10-30) CONCEPT: the ARCHMAGE (D8 final boss) as a
horror NUN (black habit, white wimple / coif, pale hollow-eyed face, rosary, glowing
eyes; a trope homage, no film character details). Review artefact only: NOT engine
data, nothing in index*.asm / frames.asm / SRC6.

Two options, 40 rows, bottom-anchored, 24-px body (cast 32 wide, ax 0):
  A GLIDING (frontal, floats 2 px off the floor): GLIDE1 / GLIDE2 sway (idle loop),
    RAISE (telegraph: arms up, eyes flare), CAST (arm + cross thrust at the hero),
    HURT (head snapped aside, scream). Frontal frames are SYM (one facing stored):
    the Archmage never walks and its posts are cell-aligned, so one shift suffices.
  B WALKING (3/4 view, shoes on the ART12 walk rig): WALK1..4 (B4 cycle W2 W4 W3 W1:
    planted foot steps back exactly 4 px per tick, legs swap, constant head row,
    WALK1 = WK0 rest / WALK2 = WK4), CAST (32 wide), HURT (recoil).

Two tones in ONE ink (the telegraph recolours the whole body): the habit / veil are
a 50 % vertical hatch (reads dark in any ink), the wimple / coif, face and hands are
SOLID ink (reads as the brightest region in any ink), eyes / mouth / nose are paper
holes, each eye one ink pixel (the glow) inside a 3x3 hollow socket.

Checks (exit 1): 40 rows, W % 8 == 0; gfx_convert --layout native clash + data /
mask round-trip in every ink shown; head top constant (both options); B walk:
planted-foot slip 0. Writes assets/gfx/concept/art13/: grid/*.grid, anim/*.gif,
art13_nun.svg.html (board F3m), art13_nun.png, costs.txt.
Reference: the current shared Archmage sprite = Necromancer V2 bone caster (ART12
pick), copied into art13/ref/ from feat/3f-art11-40px 09f1870.
Usage: python3 tools/gen_art13_nun.py
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_3f_art as G3  # noqa: E402
import gen_art2_options as A  # noqa: E402
import gfx_convert  # noqa: E402
import svg_sprites as S  # noqa: E402
import zx0_pack as zp  # noqa: E402

REPO = S.REPO
OUT = os.path.join(REPO, "assets/gfx/concept/art13")
GRID_OUT = os.path.join(OUT, "grid")
ANIM = os.path.join(OUT, "anim")
REF = os.path.join(OUT, "ref")
H, FLOOR, BW = 40, 39, 24

ARCH = "#00D700"                                   # $04 Archmage base ink
TIER = (("$03 NECRO", "#D700D7"), ("$04 ARCHMAGE", "#00D700"), ("$06 BONE CALLER", "#D7D700"))
TELE = (("$04 BASE", "#00D700"), ("$42 FIRE", "#FF3030"), ("$45 FROST", "#00FFFF"),
        ("$47 LIGHTNING", "#FFFFFF"), ("$43 DARK", "#FF00FF"), ("$44 DRAIN", "#00FF00"))
ALL_INKS = sorted({k for _, k in TIER + TELE})

if not os.path.exists(zp.ZX0):                     # worktree: use the main checkout's binary
    alt = os.path.join(os.path.dirname(REPO.split("/.claude/")[0] + "/"), "tools/bin/zx0")
    if os.path.exists(alt):
        zp.ZX0 = alt


# ===========================================================================
# drawing primitives
# ===========================================================================
def hatch_on(x):
    """Symmetric vertical hatch about the 24-px body centre (cols 11 | 12)."""
    return min(x, 23 - x) % 2 == 0


def region(rows, x0=0, y0=0, w=24, hatch=hatch_on):
    """Region map -> bitmap. 'v' / '#' solid ink, 'V' hatch (ink on hatch_on cols),
    'W' solid (wimple / face), 'o' paper (inside the silhouette), '*' ink, '.' none."""
    b = np.zeros((H, w), bool)
    paper = np.zeros((H, w), bool)
    for j, r in enumerate(rows):
        for i, c in enumerate(r):
            y, x = y0 + j, x0 + i
            if not (0 <= y < H and 0 <= x < w):
                continue
            if c in "v#W*":
                b[y, x] = True
            elif c == "V":
                b[y, x] = hatch(x - x0)
            elif c == "o":
                paper[y, x] = True
    return b, paper


def put(b, src, dx=0, dy=0, sep=False):
    """OR src (shifted) into b; sep clears a 1-px 4-neighbour ring around it first."""
    s = np.zeros_like(b)
    h, w = src.shape
    for y in range(h):
        for x in range(w):
            if src[y, x] and 0 <= y + dy < b.shape[0] and 0 <= x + dx < b.shape[1]:
                s[y + dy, x + dx] = True
    if sep:
        b[G3.dilate4(s) & ~s] = False
    b |= s
    return s


def stamp(b, txt, x, y, sep=False):
    rows = txt.strip("\n").splitlines()
    m = np.zeros_like(b)
    cut = np.zeros_like(b)
    for j, r in enumerate(rows):
        for i, c in enumerate(r):
            if 0 <= y + j < b.shape[0] and 0 <= x + i < b.shape[1]:
                if c == "#":
                    m[y + j, x + i] = True
                elif c == "o":
                    cut[y + j, x + i] = True
    if sep:
        b[G3.dilate4(m | cut) & ~(m | cut)] = False
    b |= m
    b[cut] = False


def line(b, pts, w=1, sep=False, on=True):
    m = np.zeros_like(b)
    for (a, c), (d, e) in zip(pts, pts[1:]):
        for x, y in G3.line_pts(a, c, d, e):
            m[max(y, 0):max(y + w, 0), max(x - w // 2, 0):max(x - w // 2 + w, 0)] = True
    m = m[:b.shape[0], :b.shape[1]]
    if not on:
        b[m] = False
        return m
    if sep:
        b[G3.dilate4(m) & ~m] = False
    b |= m
    return m


def px(b, pts, on=True):
    for x, y in pts:
        if 0 <= y < b.shape[0] and 0 <= x < b.shape[1]:
            b[y, x] = on


# ===========================================================================
# the head (frontal), shared by A and (turned) by B
# ===========================================================================
HEAD = [                                           # rows 0..19, 24 cols, symmetric
    "........vvvvvvvv........",
    "......vvVVVVVVVVvv......",
    ".....vVVVVVVVVVVVVv.....",
    "....vVVVVWWWWWWVVVVv....",
    "...vVVVWWWWWWWWWWVVVv...",
    "...vVVWWWWWWWWWWWWVVv...",
    "..vVVWWWooooooooWWWVVv..",
    "..vVVWWWo******oWWWVVv..",
    "..vVVWWoooo**ooooWWVVv..",
    "..vVVWWoo*o**o*ooWWVVv..",
    "..vVVWWoooo**ooooWWVVv..",
    "..vVVWWo***oo***oWWVVv..",
    "..vVVWWo********oWWVVv..",
    "..vVVWWo*oooooo*oWWVVv..",
    "..vVVWWWo*o**o*oWWWVVv..",
    "..vVVWWWWo****oWWWWVVv..",
    "..vVVWWWWWooooWWWWWVVv..",
    "..vVVWWWWWWWWWWWWWWVVv..",
    ".vVVWWWWWWWWWWWWWWWWVVv.",
    ".vVWWWWWWWWWWWWWWWWWWVv.",
]
SCREAM = {13: "..vVVWWo*oooooo*oWWVVv..", 14: "..vVVWWWo*oooo*oWWWVVv..",
          15: "..vVVWWWWo*oo*oWWWWVVv.."}


def head(scream=False, flare=False, hollow=False):
    rows = list(HEAD)
    if scream:
        for k, v in SCREAM.items():
            rows[k] = v
    b, _ = region(rows)
    if flare:                                       # eyes flare: a 3-px glow cross per socket
        px(b, [(9, 8), (8, 9), (10, 9), (9, 10), (14, 8), (13, 9), (15, 9), (14, 10)])
    if hollow:                                      # glow snuffed (hurt)
        px(b, [(9, 9), (14, 9)], False)
    return b


# ===========================================================================
# option A — gliding, frontal
# ===========================================================================
def habit_rows(y0, y1, hw0, hw1, shear=lambda y: 0, hem_y=37):
    """Solid-edged, hatched habit trapezoid; returns (bitmap, (l, r) per row)."""
    b = np.zeros((H, BW), bool)
    spans = {}
    for y in range(y0, y1 + 1):
        t = (y - y0) / max(1, y1 - y0)
        hw = int(round(hw0 + (hw1 - hw0) * t))
        s = shear(y)
        l, r = max(12 - hw + s, 0), min(11 + hw + s, BW - 1)
        spans[y] = (l, r)
        for x in range(l, r + 1):
            b[y, x] = hatch_on(x - s) or x in (l, r) or y in (y0, y1)
    return b, spans


def tatters(b, spans, y, phase):
    """Ragged floating hem on row y (and wisps on y+1): every 3rd column dropped."""
    l, r = spans[y]
    for x in range(l + 1, r):
        if (x + phase) % 3 == 0:
            b[y, x] = False
    for x in range(l, r + 1):
        if (x + phase) % 4 == 1:
            b[y + 1, x] = True


HANDS = """
..##..
.####.
.####.
##..##
"""
CROSS = """
.#.
###
.#.
.#.
"""


def rosary(b, x0, y0, dx_end):
    """Beads hanging from (x0, y0) down 6 rows, drifting dx_end px, then the cross;
    cut into a paper channel so they read over the hatch."""
    pts = []
    for k in range(4):
        pts.append((x0 + int(round(dx_end * k / 4)), y0 + 2 * k))
    ch = np.zeros_like(b)
    for x, y in pts:
        ch[max(y - 1, 0):y + 2, max(x - 1, 0):x + 2] = True
    cx = x0 + dx_end
    ch[y0 + 7:y0 + 12, cx - 2:cx + 3] = True
    b[ch] = False
    # re-close the habit edge where the channel cut it is not needed: channel is inside
    px(b, pts)
    stamp(b, CROSS, cx - 1, y0 + 8)


def nun_a(pose):
    """-> bitmap for GLIDE1 / GLIDE2 / RAISE / CAST / HURT."""
    cast = pose == "CAST"
    w = 32 if cast else 24
    sway = {"GLIDE1": -1, "GLIDE2": 1}.get(pose, 0)

    def shear(y):                                   # hem sways, the head never moves
        if y < 26:
            return 0
        return int(round(sway * 2 * (y - 26) / 11))
    hb, spans = habit_rows(19, 37, 9, 11, shear)
    b = np.zeros((H, w), bool)
    b[:, :BW] |= hb
    tatters(b[:, :BW], spans, 37, 1 if sway > 0 else 0)
    b[38:40] = False                                # floats: rows 38..39 stay clear
    px(b, [(x, 38) for x in range(spans[37][0], spans[37][1] + 1, 4)])   # one wisp row
    hd = head(scream=(pose == "HURT"), flare=(pose in ("RAISE", "CAST")),
              hollow=(pose == "HURT"))
    if pose == "HURT":                              # head snapped 2 px aside, 1 px down
        hd2 = np.zeros_like(hd)
        hd2[1:20, 0:22] = hd[0:19, 2:24]
        hd2[0, :] = hd[0, :]                        # keep the head-top row (constant)
        hd2[0, 22:] = False
        hd = hd2
    b[0:20, :BW] &= ~(G3.dilate4(hd[0:20]))        # head over the habit top
    b[0:20, :BW] |= hd[0:20]
    if pose in ("GLIDE1", "GLIDE2"):
        line(b, [(4, 21), (9, 25)], 1)              # sleeve folds to the clasped hands
        line(b, [(19, 21), (14, 25)], 1)
        line(b, [(3, 26), (8, 28)], 1)
        line(b, [(20, 26), (15, 28)], 1)
        stamp(b, HANDS, 9, 21, sep=True)
        rosary(b, 12 if sway > 0 else 11, 27, -sway)
    elif pose == "RAISE":                           # sleeves thrown up beside the veil
        for s in (1, -1):
            xa = 4 if s > 0 else 19
            xe = 1 if s > 0 else 22
            line(b, [(xa, 21), (xe, 15), (xe, 11)], 3, sep=True)
            for y in range(11, 21):                 # hatch the raised sleeve
                for x in range(max(xe - 1, 0), min(xe + 2, BW)):
                    if b[y, x] and not hatch_on(x) and 0 < x < 23 and y > 12:
                        b[y, x] = False
            stamp(b, "#.#\n###\n.#.", xe - 1, 8)    # pale claw
        stamp(b, ".###.\n#####\n.###.", 9, 23, sep=True)   # the rosary bunched at the chest
        stamp(b, CROSS, 10, 26, sep=True)
        px(b, [(1, 4), (22, 4), (0, 6), (23, 6)])  # flare sparks
    elif pose == "CAST":                            # near arm thrust at the hero, cross held out
        line(b, [(19, 21), (24, 19), (28, 19)], 3, sep=True)
        for y in range(18, 22):
            for x in range(19, 27):
                if b[y, x] and x % 2 == 1 and 19 <= y <= 20:
                    b[y, x] = False
        stamp(b, "##\n##\n##", 28, 18, sep=True)    # pale hand
        stamp(b, ".#.\n###\n.#.\n.#.\n.#.", 29, 12, sep=True)   # cross raised in the fist
        px(b, [(27, 10), (31, 10), (29, 9), (26, 13)])           # glints
        px(b, [(30, 22), (29, 24), (30, 26), (29, 28)])          # beads dangling
        line(b, [(4, 21), (9, 25)], 1)
        stamp(b, ".###.\n#####\n.###.", 9, 23, sep=True)        # far hand at the chest
    elif pose == "HURT":                            # sleeves flung down and apart
        line(b, [(4, 21), (1, 27), (1, 31)], 2, sep=True)
        line(b, [(19, 21), (22, 27), (22, 31)], 2, sep=True)
        stamp(b, "##\n#.", 0, 32, sep=True)
        stamp(b, "##\n.#", 22, 32, sep=True)
        rosary(b, 11, 25, 2)
    return b


A_POSES = ("GLIDE1", "GLIDE2", "RAISE", "CAST", "HURT")
A_FLAG = {"GLIDE1": "STA|SYM", "GLIDE2": "STA|SYM", "RAISE": "STA|SYM", "CAST": "STA",
          "HURT": "STA|SYM"}

# ===========================================================================
# option B — walking, 3/4 view facing right (ART12 walk rig)
# ===========================================================================
FEET = {"W2": (16, "g", 8, "g"), "W4": (12, "g", 14, "up"),
        "W3": (8, "g", 16, "g"), "W1": (14, "g", 12, "g")}
B_CYCLE = ("W2", "W4", "W3", "W1")
B_NAME = {"W1": "walk1", "W2": "walk2", "W3": "walk3", "W4": "walk4"}


def head_turned():
    """The frontal head turned 1 px toward the facing: the face, wimple and veil
    front edge move right; the veil grows 2 px down the back (left)."""
    hd = head()
    t = np.zeros_like(hd)
    t[:, 1:] = hd[:, :-1]
    return t


def nun_b(pose):
    cast, hurt = pose == "CAST", pose == "HURT"
    w = 32 if cast else 24
    p = "W1" if (cast or hurt) else pose
    n_x, n_s, f_x, f_s = FEET[p]
    b = np.zeros((H, w), bool)
    # habit: hem follows the stride (front edge to the leading shoe)
    xs = [x for x, s in ((n_x, n_s), (f_x, f_s)) if s == "g"]
    hem_l, hem_r = min(xs) - 3, max(xs) + 5
    for y in range(19, 38):
        t = (y - 19) / 18
        l = int(round(4 + (min(hem_l, 4) - 4) * t))
        r = int(round(19 + (max(hem_r, 19) - 19) * t))
        l, r = max(l, 0), min(r, 23)
        for x in range(l, r + 1):
            b[y, x] = hatch_on(x) or x in (l, r) or y in (19, 37)
    n_back = min(xs)                                # the fold to the leading foot
    line(b, [(12, 26), (max(xs) + 1, 37)], 1)
    for y in range(36, 38):                         # ragged hem
        for x in range(0, 24):
            if b[y, x] and (x + y) % 4 == 0:
                b[y, x] = False
    for x, s in ((f_x, f_s), (n_x, n_s)):           # shoes
        if s == "up":
            continue
        m = np.zeros_like(b)
        m[FLOOR - 1:FLOOR + 1, x - 1:x + 4] = True
        b[G3.dilate4(m) & ~m] = False
        b |= m
    hd = head_turned()
    if hurt:                                        # recoil: head 2 px back, scream, hollow eyes
        hd = head(scream=True, hollow=True)
        t = np.zeros_like(hd)
        t[:, 0:23] = hd[:, 1:24]
        hd = t
    elif cast:
        hd = head(flare=True)
        t = np.zeros_like(hd)
        t[:, 1:] = hd[:, :-1]
        hd = t
    b[0:20, :BW] &= ~(G3.dilate4(hd[0:20, :BW]))
    b[0:20, :BW] |= hd[0:20, :BW]
    # the veil hangs down the back (behind = left)
    for y in range(20, 30):
        for x in (1, 2):
            b[y, x] = (x == 1) or hatch_on(x)
    if cast:
        line(b, [(18, 21), (23, 19), (27, 19)], 3, sep=True)
        stamp(b, "##\n##\n##", 27, 18, sep=True)
        stamp(b, ".#.\n###\n.#.\n.#.\n.#.", 28, 12, sep=True)
        px(b, [(26, 10), (30, 10), (28, 9), (25, 13), (29, 22), (28, 24), (29, 26)])
        stamp(b, ".###.\n#####\n.###.", 10, 23, sep=True)
    elif hurt:
        line(b, [(17, 21), (21, 26), (22, 30)], 2, sep=True)
        stamp(b, "##\n.#", 21, 31, sep=True)
        line(b, [(6, 21), (3, 26), (2, 30)], 2, sep=True)
        rosary(b, 12, 26, 2)
    else:
        sw = {"W2": -1, "W4": 0, "W3": 1, "W1": 0}[p]   # hands swing a pixel with the stride
        line(b, [(17, 21), (14 + sw, 25)], 1)
        line(b, [(6, 21), (10 + sw, 25)], 1)
        stamp(b, HANDS, 10 + sw, 21, sep=True)
        rosary(b, 13 + sw, 27, 1)
    return b


B_POSES = ("W1", "W2", "W3", "W4", "CAST", "HURT")
B_FLAG = {"W1": "WK0", "W2": "WK4", "W3": "WK4", "W4": "WK0", "CAST": "STA", "HURT": "STA"}


# ===========================================================================
# checks, costs
# ===========================================================================
def pool(h, w, ax, bw, flags):
    """src/defs.asm FRM formula (= gen_art10_short.pool): per facing H x 2 x (cols + 1
    if off the 8-px grid at its shift); MOT both shifts; SYM one facing."""
    f = set(flags.split("|"))
    cols = w // 8
    if "MOT" in f:
        return (1 if "SYM" in f else 2) * h * 2 * (2 * cols + 1)
    ph = 4 if "WK4" in f else 0
    left = h * 2 * (cols + (((ax + ph) & 7) != 0))
    right = 0 if "SYM" in f else h * 2 * (cols + (((w - ax - bw + ph) & 7) != 0))
    return left + right


def head_top(bm):
    return int(np.where(bm.any(1))[0][0])


def runs(row):
    r, x = [], 0
    while x < len(row):
        if row[x]:
            e = x
            while e < len(row) and row[e]:
                e += 1
            r.append((x, e))
            x = e
        else:
            x += 1
    return r


def foot_slip(fr, names):
    out = []
    for i in range(len(names)):
        a, b = fr[names[i]], fr[names[(i + 1) % len(names)]]
        best = None
        for a0, a1 in runs(a[-1]):
            for b0, b1 in runs(b[-1]):
                for s in (b0 + 4 - a0, b1 + 4 - a1):
                    if best is None or abs(s) < abs(best):
                        best = s
        out.append(best)
    return out


def load_grid(path):
    rows = [ln.rstrip("\n") for ln in open(path) if ln.strip() and not ln.startswith("#")]
    return np.array([[c == "#" for c in r] for r in rows], bool)


# ===========================================================================
# rendering (board SVG, GIF, PNG)
# ===========================================================================
BG = (16, 16, 24)


def rgb(ink):
    c, br = S.INK_MAP[ink]
    return S.spec_rgb(c, br)


def blit(a, bm, x, y, ink):
    solid = S.make_mask(bm, outline=True)
    col = rgb(ink)
    for yy in range(bm.shape[0]):
        for xx in range(bm.shape[1]):
            Y, X = y + yy, x + xx
            if 0 <= Y < a.shape[0] and 0 <= X < a.shape[1]:
                if bm[yy, xx]:
                    a[Y, X] = col
                elif solid[yy, xx]:
                    a[Y, X] = (0, 0, 0)


def place(fr, n, xb, facing, sym):
    b, ax = fr[n]
    if facing > 0 or n in sym:
        return b, xb - ax
    return np.fliplr(b), xb - (b.shape[1] - ax - BW)


def ticks(fr, cyc, facing, walk, sym=(), reps=2):
    seq = [n for n, k in cyc for _ in range(k)] * reps
    W = (24 + 4 * len(seq) + 40) if walk else 64
    out = []
    for i, n in enumerate(seq):
        xb = (8 + 4 * i if facing > 0 else W - 32 - 4 * i) if walk else 20
        b, x = place(fr, n, xb, facing, sym)
        out.append((b, x, H + 2 - b.shape[0], xb))
    return out, W, H + 2


def path_d(bm, xo, yo):
    d = []
    for yy in range(bm.shape[0]):
        for x0, x1 in runs(bm[yy]):
            d.append(f"M{x0 + xo} {yy + yo}h{x1 - x0}v1h-{x1 - x0}z")
    return "".join(d)


def anim_svg(rows, ink, W, Hh, label, dur_ms=150, scale=3):
    n = len(rows[0])
    total = n * dur_ms / 1000.0
    Ht = Hh * len(rows)
    out = [f'<svg width="{W * scale}" height="{Ht * scale}" viewBox="0 0 {W} {Ht}" '
           f'shape-rendering="crispEdges" style="display: block;">',
           f'<rect width="{W}" height="{Ht}" fill="#000000"></rect>']
    for r, tk in enumerate(rows):
        out.append(f'<rect x="0" y="{(r + 1) * Hh - 1}" width="{W}" height="1" fill="#26264a"></rect>')
        groups = {}
        for i, (bm, x, y, _xb) in enumerate(tk):
            groups.setdefault((bm.tobytes(), bm.shape, x, y), (bm, x, y, []))[3].append(i)
        for bm, x, y, idx in groups.values():
            vals = ";".join("1" if j in idx else "0" for j in range(n))
            out.append(f'<g opacity="{1 if 0 in idx else 0}"><path d="{path_d(bm, x, y + r * Hh)}" '
                       f'fill="{ink}"></path><animate attributeName="opacity" values="{vals}" '
                       f'dur="{total:.2f}s" calcMode="discrete" repeatCount="indefinite"></animate></g>')
    out.append("</svg>")
    return ('<div style="display: flex; flex-direction: column; gap: 8px; align-items: flex-start;">\n'
            '<div style="padding: 8px; background: #000000; border: 2px solid #26263a;">'
            + "".join(out) + "</div>\n"
            f'<div style="font-size: 11px; letter-spacing: 1px; color: #a9a7b8;">{label}</div>\n</div>')


def ticks_gif(path, rows, W, Hh, ink, scale=3, ms=150):
    imgs = []
    for i in range(len(rows[0])):
        a = np.full((Hh * len(rows), W, 3), BG, np.uint8)
        for r, tk in enumerate(rows):
            sub = a[r * Hh:(r + 1) * Hh]
            sub[Hh - 1, :] = (60, 60, 140)
            b, x, y, _xb = tk[i]
            blit(sub, b, x, y - 1, ink)
        imgs.append(Image.fromarray(a).resize((W * scale, a.shape[0] * scale), Image.NEAREST))
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=ms, loop=0)


def heading(t):
    return ('<div style="font-family: \'Press Start 2P\', monospace; font-size: 13px; '
            f'color: #e8e6f0; margin: 24px 0 12px;">{t}</div>')


def sub(t):
    return f'<div style="font-size: 12px; color: #e8e6f0; margin: 12px 0 6px;">{t}</div>'


def row(cells):
    return ('<div style="display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-end;">\n'
            + "\n".join(cells) + "\n</div>")


def panel(bm, ink, scale=3):
    a = np.full((H + 4, 36, 3), BG, np.uint8)
    blit(a, bm, 2, H + 2 - bm.shape[0], ink)
    a[H + 2, :] = (60, 60, 140)
    return Image.fromarray(a).resize((36 * scale, (H + 4) * scale), Image.NEAREST)


def sheet(path, rows, scale=3):
    ims = []
    for lab, cells in rows:
        ps = [panel(b, k, scale) for b, k in cells]
        r = Image.new("RGB", (150 + sum(p.width + 6 for p in ps), (H + 4) * scale + 6), BG)
        ImageDraw.Draw(r).text((4, 4), lab, fill=(255, 255, 120))
        x = 150
        for p in ps:
            r.paste(p, (x, 3))
            x += p.width + 6
        ims.append(r)
    sh = Image.new("RGB", (max(i.width for i in ims), sum(i.height for i in ims)), BG)
    y = 0
    for i in ims:
        sh.paste(i, (0, y))
        y += i.height
    sh.save(path)


# ===========================================================================
def main() -> int:
    for d in (GRID_OUT, ANIM):
        os.makedirs(d, exist_ok=True)
    bad = []
    fa = {f"nun_a_{p.lower()}": (nun_a(p), 0) for p in A_POSES}
    fb = {f"nun_b_{B_NAME.get(p, p.lower())}": (nun_b(p), 0) for p in B_POSES}
    ref = {f"necro_{n}_v2": (load_grid(os.path.join(REF, f"necro_{n}_v2.grid")), 0)
           for n in ("walk1", "walk2", "walk3", "walk4", "cast")}
    raw = {}
    with tempfile.TemporaryDirectory() as td:
        for name, (bm, ax) in list(fa.items()) + list(fb.items()):
            if bm.shape[0] != H or bm.shape[1] % 8:
                bad.append(f"{name}: shape {bm.shape}")
            solid = S.make_mask(bm, outline=True)
            g = os.path.join(GRID_OUT, name + ".grid")
            with open(g, "w") as fh:
                fh.write(A.grid_text(name, bm, solid, name.upper(), ARCH,
                                     "ART13 nun Archmage concept (tools/gen_art13_nun.py); review only")
                         .replace("tools/gen_art2_options.py", "tools/gen_art13_nun.py"))
            for ink in ALL_INKS:
                raw[name] = A.pack_check(f"{name}_{ink[1:]}", g, bm, solid, ink, td)

        def zx(names):
            return len(zp.zx0(b"".join(raw[n] for n in names), os.path.join(td, "z" + names[0])))
        pk_a4 = zx(["nun_a_glide1", "nun_a_glide2", "nun_a_cast", "nun_a_hurt"])
        pk_a5 = zx(["nun_a_glide1", "nun_a_glide2", "nun_a_raise", "nun_a_cast", "nun_a_hurt"])
        pk_b = zx(list(fb))
    # checks
    for lab, fr in (("A", fa), ("B", fb)):
        tops = {n: head_top(b) for n, (b, _a) in fr.items()}
        if len(set(tops.values())) != 1:
            bad.append(f"{lab}: head top {tops}")
    walk = [f"nun_b_{B_NAME[p]}" for p in B_CYCLE]
    slip = foot_slip({n: fb[n][0] for n in walk}, walk)
    if any(slip):
        bad.append(f"B foot slip {slip}")

    # ---- costs ----
    def prow(name, bm, flags):
        cols = bm.shape[1] // 8
        return name, flags, bm.shape[1], cols, pool(H, bm.shape[1], 0, BW, flags), H * cols * 2 + 1
    ca = [prow(n, b, A_FLAG[n.split("_")[2].upper()]) for n, (b, _a) in fa.items()]
    cb = [prow(n, b, B_FLAG[{v: k for k, v in B_NAME.items()}.get(n.split("_")[2], n.split("_")[2].upper())])
          for n, (b, _a) in fb.items()]
    a4 = sum(r[4] for r in ca if "raise" not in r[0])
    a5 = sum(r[4] for r in ca)
    bt = sum(r[4] for r in cb)
    L = ["# ART13 nun Archmage — costs (tools/gen_art13_nun.py). CONCEPT, not wired.",
         "# pool = src/defs.asm FRM formula, both facings (SYM = one facing): per facing",
         "# H x 2 x (cols + 1 if off the 8-px grid at its shift). src = H x cols x 2 + 1 raw.",
         "# Today the Archmage shares the Necro frames (0 B extra; Necro is on D8 anyway).",
         "# Any own Archmage set is ALL extra on D8 only. D8 Warrior slack 3,194 B, target <= ~1,597.",
         "", "frame               flags      W cols  pool   src"]
    for r in ca + cb:
        L.append(f"{r[0]:19s} {r[1]:9s} {r[2]:2d} {r[3]:4d} {r[4]:5d} {r[5]:5d}")
    L += ["",
          f"A  (GLIDE1, GLIDE2, CAST, HURT)          4 fids  pool {a4:5d}  SRC6 zx0 {pk_a4:4d} B",
          f"A+ (+ RAISE telegraph pose)              5 fids  pool {a5:5d}  SRC6 zx0 {pk_a5:4d} B",
          f"B  (WALK1..4, CAST, HURT)                6 fids  pool {bt:5d}  SRC6 zx0 {pk_b:4d} B",
          "",
          f"D8 Warrior slack after: A {3194 - a4:+d}, A+ {3194 - a5:+d}, B {3194 - bt:+d}",
          "Assumptions (engineer to confirm): A's frontal frames are SYM (one stored facing, drawn",
          "unmirrored both ways, as the climb pairs) and every Archmage frame is one shift (STA:",
          "the G1d post and the blink target are cell-aligned). Without SYM: A 1360 -> 2080;",
          "without one-shift (MOT): A -> 3120 (over budget) — then cut HURT (rest + flash, as today).",
          "FRT ids: 8 spare of 144 -> A 4 (4 left), A+ 5 (3 left), B 6 (2 left).",
          "SRC6: + 1 ZX0 block per option (unit U_ARCH, own pool_gmap record replacing the",
          "Archmage -> Necro record; Necro stays for the D8 Necromancers + U_NBOLT unchanged).",
          "B: the Archmage NEVER walks (A3: G1d post, blink only), so B's 4 walk frames would only",
          "ever play as an idle cycle: 2,240 B of pool for motion the rules never show.",
          "",
          "INK REGIONS (one ink, the telegraph recolours all of it; legible by DENSITY not hue):",
          "  solid ink  : coif band rows 4-5, wimple ring cols 5-6 / 17-18 rows 4-17, bib rows 16-19,",
          "               face cols 8-15 rows 7-15, hands, cross  -> brightest region in every ink",
          "  50% hatch  : veil rows 0-19 outside the wimple, habit rows 19-37 -> reads dark / 'black'",
          "  paper      : face ring (1 px), 3x3 eye sockets rows 8-10, nose, mouth -> hollow face",
          "  1-px ink   : the eye glows (9,9) / (14,9) inside the sockets; RAISE / CAST flare to a",
          "               3-px cross per eye",
          "  Checked packed + round-tripped in " + ", ".join(ALL_INKS) + ".",
          "",
          "checks: head top " + str(sorted({head_top(b) for b, _ in list(fa.values()) + list(fb.values())}))
          + f", B walk slip {slip}"]
    with open(os.path.join(OUT, "costs.txt"), "w") as fh:
        fh.write("\n".join(L) + "\n")

    # ---- board ----
    symA = {n for n in fa if "SYM" in A_FLAG[n.split("_")[2].upper()]}
    cyc = {
        "A GLIDE (idle loop)": (fa, [("nun_a_glide1", 4), ("nun_a_glide2", 4)], False, symA),
        "A TELEGRAPH-CAST": (fa, [("nun_a_glide1", 3), ("nun_a_raise", 3), ("nun_a_cast", 3),
                                  ("nun_a_glide1", 3)], False, symA),
        "A HURT": (fa, [("nun_a_glide1", 3), ("nun_a_hurt", 3), ("nun_a_glide1", 3)], False, symA),
        "B WALK W2 W4 W3 W1": (fb, [(f"nun_b_{B_NAME[p]}", 1) for p in B_CYCLE], True, ()),
        "B CAST": (fb, [("nun_b_walk1", 3), ("nun_b_cast", 3), ("nun_b_walk1", 3)], False, ()),
        "B HURT": (fb, [("nun_b_walk1", 3), ("nun_b_hurt", 3), ("nun_b_walk1", 3)], False, ()),
        "NECRO V2 (today) WALK": (ref, [(f"necro_walk{k}_v2", 1) for k in (2, 4, 3, 1)], True, ()),
        "NECRO V2 (today) CAST": (ref, [("necro_walk1_v2", 3), ("necro_cast_v2", 3),
                                        ("necro_walk1_v2", 3)], False, ()),
    }
    strips = {}
    for lab, (fr, c, walk, sym) in cyc.items():
        rows_ = []
        for facing in (1, -1):
            tk, W, Hh = ticks(fr, c, facing, walk, sym)
            rows_.append(tk)
        strips[lab] = (rows_, W, Hh)
        ticks_gif(os.path.join(ANIM, lab.replace("(today) ", "").lower().replace(" ", "_").replace("-", "_")
                               .replace("(", "").replace(")", "") + ".gif"),
                  rows_, W, Hh, ARCH)

    def cap(n):
        return n.replace("nun_a_", "NUN A ").replace("nun_b_", "NUN B ").replace("_v2", " V2").upper()
    bd = [heading("F3m ART13 — ARCHMAGE AS A HORROR NUN (CONCEPT, 40 PX)"),
          sub("Black habit + veil = 50% hatch, white coif / wimple / face / hands = solid ink, hollow "
              "3x3 eye sockets with a 1-px glow. One ink: the spell telegraph recolours the whole body, "
              "the face stays the brightest region in every ink. Not wired; review only."),
          heading("F3m TODAY — NECROMANCER V2 BONE CASTER (shared Archmage sprite) | NUN A | NUN B"),
          sub("Tier inks: $03 Necro, $04 Archmage, $06 Bone Caller.")]
    for tl, ink in TIER:
        bd.append(row([S.svg_artboard_html(ref["necro_walk1_v2"][0], ink, f"NECRO V2 {tl}"),
                       S.svg_artboard_html(fa["nun_a_glide1"][0], ink, f"NUN A {tl}"),
                       S.svg_artboard_html(fb["nun_b_walk1"][0], ink, f"NUN B {tl}")]))
    bd.append(heading("F3m TELEGRAPH INKS (A GLIDE1 / A CAST / B WALK1)"))
    bd.append(row([S.svg_artboard_html(fa["nun_a_glide1"][0], ink, f"A {tl}") for tl, ink in TELE]))
    bd.append(row([S.svg_artboard_html(fa["nun_a_cast"][0], ink, f"A CAST {tl}") for tl, ink in TELE]))
    bd.append(row([S.svg_artboard_html(fb["nun_b_walk1"][0], ink, f"B {tl}") for tl, ink in TELE]))
    bd.append(heading("F3m OPTION A — GLIDING (frontal, floats 2 px)"))
    bd.append(sub(f"GLIDE1 / GLIDE2 sway (hem + rosary, head fixed), RAISE telegraph, CAST, HURT. "
                  f"Pool {a4} B (4 fids) / {a5} B with RAISE (5 fids); SRC6 ≈ {pk_a4} / {pk_a5} B."))
    bd.append(row([S.svg_artboard_html(b, ARCH, cap(n)) for n, (b, _a) in fa.items()]))
    bd.append(row([anim_svg(*strips[k][:1], ARCH, strips[k][1], strips[k][2], k)
                   for k in ("A GLIDE (idle loop)", "A TELEGRAPH-CAST", "A HURT")]))
    bd.append(heading("F3m OPTION B — WALKING (3/4 view, ART12 walk rig)"))
    bd.append(sub(f"WALK1..4 (B4: W2 W4 W3 W1, planted foot 4 px/tick, legs swap, constant head), "
                  f"CAST 32w, HURT. Pool {bt} B (6 fids); SRC6 ≈ {pk_b} B. Over the D8 slack budget."))
    bd.append(row([S.svg_artboard_html(b, ARCH, cap(n)) for n, (b, _a) in fb.items()]))
    bd.append(row([anim_svg(*strips[k][:1], ARCH, strips[k][1], strips[k][2], k)
                   for k in ("B WALK W2 W4 W3 W1", "B CAST", "B HURT")]))
    bd.append(heading("F3m REFERENCE — NECROMANCER V2 TODAY"))
    bd.append(row([anim_svg(*strips[k][:1], ARCH, strips[k][1], strips[k][2], k)
                   for k in ("NECRO V2 (today) WALK", "NECRO V2 (today) CAST")]))
    bd.append(sub("Costs: " + "; ".join(" ".join(x.split()) for x in L if x[:2] in ("A ", "A+", "B ")
                                       and "fids" in x) + ". " + " ".join(L[[i for i, x in enumerate(L)
                                       if x.startswith("D8 Warrior slack after")][0]].split())))
    with open(os.path.join(OUT, "art13_nun.svg.html"), "w") as fh:
        fh.write("\n".join(bd) + "\n")

    sh = [("NECRO V2 today $04", [(b, ARCH) for b, _ in ref.values()]),
          ("NUN A $04", [(b, ARCH) for b, _ in fa.values()]),
          ("NUN B $04", [(b, ARCH) for b, _ in fb.values()]),
          ("A GLIDE1 telegraph", [(fa["nun_a_glide1"][0], k) for _, k in TELE]),
          ("A CAST telegraph", [(fa["nun_a_cast"][0], k) for _, k in TELE]),
          ("tiers N2 / A / B", [(x, k) for _, k in TIER
                                for x in (ref["necro_walk1_v2"][0], fa["nun_a_glide1"][0],
                                          fb["nun_b_walk1"][0])])]
    sheet(os.path.join(OUT, "art13_nun.png"), sh)
    print("\n".join(L[-22:]))
    if bad:
        print("FAIL:\n  " + "\n  ".join(bad))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
