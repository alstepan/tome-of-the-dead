#!/usr/bin/env python3
"""gen_missing_frames.py — deterministic authoring of the PROTO "Draft 3" frames.

Builds every frame listed in docs/design/prototype.md §10.2 (32 sprite frames +
the Wizard's ZAP1/ZAP2 bolt tiles) FROM THE CHARACTERS' EXISTING CANVAS FRAMES:
head/torso rows are copied from IDLE/WALK and re-posed with explicit, reviewable
edits (row pastes, region shifts, flips, rotations for lying poses, and small
hand-typed overlays). Nothing here comes from AI raster.

Outputs (review artefacts; the canvas stays the source of truth):
  assets/gfx/source/draft3_frames.html   canvas-convention fragment, grouped by
                                          character (+ FX TILES section) — the
                                          manager pastes it as the "Draft 3"
                                          artboard; tools/svg_sprites.py import
                                          also reads it as a draft sheet until
                                          the frames exist on the canvas.
  assets/gfx/sprites/draft3_sheet.png    new frames beside each IDLE, with the
                                          body box drawn from the anchor.
  assets/gfx/sprites/preview/*.gif       climb cycle, hurt->idle, death, attacks.

Anchors are NOT computed here: they are declared per frame in
tools/svg_sprites.py ANCHOR_X (the importer validates them against §5.3).

Usage: python3 tools/gen_missing_frames.py        (from anywhere)
"""

from __future__ import annotations

import html
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import svg_sprites as S  # noqa: E402

REPO = S.REPO
FRAGMENT = os.path.join(REPO, "assets/gfx/source/draft3_frames.html")
SHEET_PNG = os.path.join(REPO, "assets/gfx/sprites/draft3_sheet.png")
PREVIEW_DIR = os.path.join(REPO, "assets/gfx/sprites/preview")

# ---------------------------------------------------------------------------
# Pixel helpers (bool arrays, True = ink). Every edit is explicit.
# ---------------------------------------------------------------------------


def T(text: str, w: int | None = None) -> np.ndarray:
    """Hand-typed rows -> bitmap. '#' ink, anything else paper. Rows may be
    indented; blank lines are ignored. Row widths must agree."""
    rows = [r.strip() for r in text.strip("\n").splitlines() if r.strip()]
    rows = [r.split()[-1] if " " in r else r for r in rows]  # allow "r12 ...."
    width = w or len(rows[0])
    for r in rows:
        if len(r) != width:
            raise ValueError(f"row width {len(r)} != {width}: {r!r}")
    return np.array([[c == "#" for c in r] for r in rows], bool)


def blank(w: int, h: int) -> np.ndarray:
    return np.zeros((h, w), bool)


def paste(dst: np.ndarray, src: np.ndarray, x: int, y: int, copy: bool = False) -> None:
    """OR (or copy) src into dst at (x, y), clipped to dst."""
    h, w = src.shape
    H, W = dst.shape
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x0 >= x1 or y0 >= y1:
        return
    s = src[y0 - y:y1 - y, x0 - x:x1 - x]
    if copy:
        dst[y0:y1, x0:x1] = s
    else:
        dst[y0:y1, x0:x1] |= s


def over(dst: np.ndarray, text: str, x: int, y: int) -> None:
    """Overlay: '#' sets ink, 'o' forces paper, anything else leaves dst."""
    rows = [r.strip() for r in text.strip("\n").splitlines() if r.strip()]
    for dy, r in enumerate(rows):
        for dx, c in enumerate(r):
            yy, xx = y + dy, x + dx
            if 0 <= yy < dst.shape[0] and 0 <= xx < dst.shape[1]:
                if c == "#":
                    dst[yy, xx] = True
                elif c == "o":
                    dst[yy, xx] = False


def move(bm: np.ndarray, y0: int, y1: int, x0: int, x1: int, dx: int, dy: int) -> None:
    """Cut the region rows y0..y1-1 / cols x0..x1-1 and OR it back at +dx,+dy."""
    reg = bm[y0:y1, x0:x1].copy()
    bm[y0:y1, x0:x1] = False
    paste(bm, reg, x0 + dx, y0 + dy)


def shear_rows(bm: np.ndarray, shifts: dict[int, int]) -> np.ndarray:
    """Shift whole rows horizontally: {row: dx}. Rows not listed stay."""
    out = bm.copy()
    for y, dx in shifts.items():
        out[y] = False
        paste(out, bm[y:y + 1], dx, y)
    return out


def lean(bm: np.ndarray, y_top: int, y_pivot: int, dx_top: int) -> np.ndarray:
    """Lean the rows above y_pivot so row y_top moves dx_top px (linear, whole
    px steps -> stair offsets like hand-drawn lean; rows >= y_pivot stay)."""
    shifts = {}
    for y in range(bm.shape[0]):
        if y < y_pivot:
            t = (y_pivot - y) / max(1, (y_pivot - y_top))
            shifts[y] = int(round(dx_top * min(1.0, t)))
    return shear_rows(bm, shifts)


def fit(bm: np.ndarray, w: int, h: int, x: int = 0, y: int | None = None) -> np.ndarray:
    """Place bm into a w x h frame at x; bottom-aligned unless y given."""
    out = blank(w, h)
    paste(out, bm, x, h - bm.shape[0] if y is None else y)
    return out


def trim(bm: np.ndarray) -> np.ndarray:
    ys, xs = np.nonzero(bm)
    return bm[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def del_cols(bm: np.ndarray, cols) -> np.ndarray:
    keep = [c for c in range(bm.shape[1]) if c not in set(cols)]
    return bm[:, keep]


def del_rows(bm: np.ndarray, rows) -> np.ndarray:
    keep = [r for r in range(bm.shape[0]) if r not in set(rows)]
    return bm[keep]


def dup_cols(bm: np.ndarray, col: int, n: int) -> np.ndarray:
    """Stretch: repeat column `col` n extra times (body elongation)."""
    return np.concatenate([bm[:, :col + 1]] + [bm[:, col:col + 1]] * n + [bm[:, col + 1:]], 1)


def checker(h: int, w: int, phase: int = 0) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    return (yy + xx + phase) % 2 == 0


def line(bm: np.ndarray, x0: int, y0: int, x1: int, y1: int, ink: bool = True) -> None:
    """1-px Bresenham line (staffs, blades, wisps)."""
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        if 0 <= y0 < bm.shape[0] and 0 <= x0 < bm.shape[1]:
            bm[y0, x0] = ink
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def poly(bm: np.ndarray, pts, ink: bool = True) -> None:
    """Filled polygon (integer vertices, PIL rasteriser — deterministic)."""
    h, w = bm.shape
    im = Image.new("1", (w, h), 0)
    ImageDraw.Draw(im).polygon(pts, fill=1, outline=1)
    m = np.array(im, bool)
    bm[m] = ink


def rot_head(name: str, y0: int, y1: int, x0: int, x1: int, k: int = 1) -> np.ndarray:
    """A head/helmet cut from a canvas frame, turned 90° (k=1: face up with the
    head pointing left = lying on the back; k=-1: face down, head right)."""
    return trim(np.rot90(SRC[name][y0:y1, x0:x1], k))


def sym(left_rows: str) -> np.ndarray:
    """12-px left halves -> 24-px symmetric rows (back views)."""
    L = T(left_rows)
    return np.concatenate([L, L[:, ::-1]], 1)


# ---------------------------------------------------------------------------
# Source frames (straight from the vendored canvas sheet)
# ---------------------------------------------------------------------------

_FRAMES, _ = S.parse_sheet(S.SHEET)
SRC = {}
for _f in _FRAMES:
    if _f.kind == "sprite":
        SRC[f"{S.CHAR_PREFIX[_f.character]}_{S.slug(_f.caption)}"] = _f.bitmap.copy()
INK = {S.CHAR_PREFIX[f.character]: f.ink_hex for f in _FRAMES if f.kind == "sprite"}
for _n, _dx in S.REPAD.items():             # previews use the re-padded frames
    SRC[_n] = S.repad(SRC[_n], _dx)
# anchors of existing wide frames after the §10.3 re-pad (for the previews)
KNOWN_AX = {"knight_windup": 4, "knight_slash": 4, "knight_follow": 4,
            "knight_block": 4, "knight_hurt": 0}


def src(name: str) -> np.ndarray:
    return SRC[name].copy()


NEW: list[tuple[str, str, np.ndarray]] = []   # (char prefix, caption, bitmap)


def add(char: str, caption: str, bm: np.ndarray, w: int, h: int) -> None:
    if bm.shape != (h, w):
        raise SystemExit(f"{char} {caption}: built {bm.shape[1]}x{bm.shape[0]}, §10 says {w}x{h}")
    NEW.append((char, caption, bm))


# ===========================================================================
# KNIGHT
# ===========================================================================

def knight_climb1() -> np.ndarray:
    """Back view. Helmet dome (12 wide, as IDLE's 11 + crest) with the visor rim
    as a paper line; kite shield slung on the back (paper ring + cross, the
    IDLE shield's motif); viewer-left arm up on the rail, right arm down with
    fist on a rung, right knee raised. CLIMB2 = exact mirror (body symmetric)."""
    return T("""
        .###....................
        .####......##...........
        .####.....####..........
        ..##...##########.......
        ..##..############......
        ..##..############......
        ..##..############......
        ..##..#..........#......
        ..##..############......
        ..##..############......
        ..##...##########.......
        ..###.....####..........
        ..###################...
        ...###################..
        .....#............#.##..
        .....#.##########.#.##..
        .....#.####..####.#.##..
        .....#.####..####.#.##..
        .....#.#........#.#.##..
        .....#.####..####.#.##..
        .....#.####..####.#.##..
        .....#.####..####.#.##..
        .....##.###..###.##.##..
        .....###.##..##.###.##..
        .....####.#..#.####.##..
        .....#####.##.#####.###.
        .....######..######.###.
        .....##############.###.
        .....#.#.#.##.#.#.#.....
        .....##############.....
        .......####..####.......
        .......####..####.......
        .......####..####.......
        .......####..####.......
        .......#..#..#..#.......
        .......####..####.......
        .......####..####.......
        .......####.............
        .......####..#####......
        .......####..#####......
        .......####..#####......
        .......####.............
        .......####.............
        ........................
        ......#####.............
        ......#####.............
        ......#####.............
        ........................
    """)


def knight_dead() -> np.ndarray:
    """On his back, head left: IDLE1's helmet turned face-up (visor slits now
    vertical) with the plume curling onto the floor, armoured torso (belt studs
    as in IDLE), legs out, boots toes-up; his kite shield (IDLE's cross motif)
    has fallen behind his legs and the sword lies on the floor in front of
    him. Body centred on the 24-px box (ax = 8)."""
    out = blank(40, 16)
    paste(out, rot_head("knight_idle1", 1, 11, 8, 19), 2, 3)   # helmet, face up
    over(out, """
        .#
        #.
        #.
        ##
        .#
    """, 0, 5)                                    # plume
    out[8:13, 13] = True                          # gorget (col 12 = neck gap)
    out[7:14, 14:24] = True                       # torso, 7 deep
    out[6, 14:18] = True                          # pauldron
    out[9, 16:23] = False                         # arm lying along the body
    out[7:14, 24] = False                         # belt line ...
    out[10, 24] = True                            # ... with buckle
    out[8:14, 25:35] = True                       # legs
    out[10, 26:35] = False                        # near/far leg
    out[8:10, 30] = False                         # knee
    over(out, """
        .###
        .###
        .###
        .###
        .###
        ####
        ####
        ####
        ####
        ####
    """, 35, 4)                                   # boots, toes up
    out[9, 35] = False
    over(out, """
        #######
        ###.###
        #.....#
        ###.###
        ###.###
        .##.##.
        ..###..
    """, 25, 0)                                   # shield, fallen behind
    over(out, """
        ...#...................
        #######################
    """, 12, 14)                                  # sword on the floor
    return out


# ===========================================================================
# WIZARD
# ===========================================================================

def wizard_idle2() -> np.ndarray:
    """IDLE breathing pair: hat tip dipped 1 px, staff hook/orb raised 1 px,
    robe hem swayed 1 px back."""
    w = src("wizard_idle")
    move(w, 0, 3, 0, 8, 0, 1)             # bent hat tip droops 1 px
    move(w, 3, 14, 16, 22, 0, -1)         # staff head up 1 px ...
    w[13, 20] = True                      # ... shaft stays continuous
    move(w, 40, 46, 0, 13, -1, 0)         # hem sways back 1 px
    return w


def _wizard_back(raise_left: bool) -> np.ndarray:
    b = T("""
        ........................
        ...........##...........
        ...........##...........
        ..........####..........
        ..........####..........
        .........######.........
        .........######.........
        ........########........
        ........#......#........
        .......##########.......
        .......##########.......
        ......############......
        .....##############.....
        ......############......
        ........########........
        .......##########.......
        ......############......
        ......############......
        ......############......
        ......############......
        ......############......
        ......#####..#####......
        ......#####..#####......
        ......#####..#####......
        .....######..######.....
        .....######..######.....
        .....######..######.....
        .....#.####..####.#.....
        .....#.####..####.#.....
        .....#.####..####.#.....
        .....#.####..####.#.....
        ....##.####..####.##....
        ....##.####..####.##....
        ....##.####..####.##....
        ....##.####..####.##....
        ....##.####..####.##....
        ....##.####..####.##....
        ...###.####..####.###...
        ...###.####..####.###...
        ...###.####..####.###...
        ...###.####..####.###...
        ...###.####..####.###...
        ...###.####..####.###...
        ...###.####..####.###...
        ...###.####..####.###...
        ...#.#.#.#.##.#.#.#.#...
        ........................
        ........................
    """)
    # climbing: the right half of the robe hem lifts with the raised knee
    b[40:46, 12:] = False
    over(b, "#.#.#.#.#", 12, 40)
    over(b, "#####", 13, 42)               # raised boot
    over(b, "#####", 13, 43)
    over(b, "#####", 6, 46)                # standing boot under the hem
    over(b, "######", 6, 47)
    # arms: left up on the rail beside the hat, right sleeve down to a rung
    over(b, """
        ###.
        ###.
        .##.
        .##.
        .##.
        .##.
        .###
        .###
        .###
        .###
        .###
        .###
        .###
        ..##
        ..##
        ...#
    """, 1, 2)
    over(b, """
        ##..
        ###.
        ###.
        ###.
        ###.
        ###.
        ###.
        .###
        .###
        .###
    """, 18, 15)
    return b if raise_left else b[:, ::-1].copy()


def _wizard_staff(b: np.ndarray) -> None:
    """Staff slung diagonally across the back (same side in both frames):
    hook over the right shoulder, shaft as a paper-edged line down to the
    left hip, foot poking out below the robe edge."""
    over(b, """
        ..##..
        .#..#.
        #...#.
        #..##.
    """, 17, 6)
    for i in range(0, 26):
        x, y = 20 - (i * 15) // 25, 10 + i
        b[y, x] = True
        if 0 <= x + 1 < 24:
            b[y, x + 1] = False
        if x - 1 >= 0:
            b[y, x - 1] = False


def wizard_climb(n: int) -> np.ndarray:
    b = _wizard_back(raise_left=(n == 1))
    _wizard_staff(b)
    return b


def wizard_hurt() -> np.ndarray:
    """IDLE recoiling backward, posed in blocks (as an animator would, not a
    per-row shear): head+hat 4 px back, hat tip knocked a further 2 px back
    and down (askew); beard/chest 2 px back; robe skirt stays planted. The
    staff is flung up in front, hook high. Body box at x 8..31 (ax = 8)."""
    w = src("wizard_idle")
    w[0:26, 15:] = False                  # staff + hand (re-drawn flung)
    out = fit(w, 32, 48, 8)
    move(out, 0, 15, 0, 32, -4, 0)         # head + hat back
    move(out, 0, 4, 0, 16, -2, 1)          # tip askew
    move(out, 15, 28, 0, 32, -2, 0)        # beard + chest back
    line(out, 22, 24, 28, 4)               # staff shaft, flung up
    over(out, """
        .##.
        #..#
        #...
        #..#
        .##.
    """, 26, 0)                            # staff hook/orb
    over(out, """
        ###
        ###
        .#.
    """, 21, 22)                           # hand on the staff
    return out


def wizard_dead() -> np.ndarray:
    """Face-down, head forward (right): the robe as a long heap with IDLE's
    fold lines (paper), the dithered beard spilling under the head, the hair
    at the head end; the hat (IDLE's bent-tip cone, small) has fallen off
    ahead; the staff's hook pokes out from under him at the back.
    Centred on the body (ax = 8)."""
    return T("""
        ........................................
        ........................................
        ........................................
        ........................................
        ........................................
        ........................................
        ........................................
        ..................................##....
        ...................................##...
        ............###########............###..
        .........##################...####.###..
        .......######.#####.#######..####.####..
        .##...######.#####.#######..#####.#####.
        #..#.######.#####.#.#.#.##.######.##.##.
        #...######.#####.#.#.#.#.##.####.#######
        ###############################.########
    """)


# ===========================================================================
# ROGUE
# ===========================================================================

def rogue_idle2() -> np.ndarray:
    """IDLE breathing pair: cloak tail flutters (lower cloak edge 1 px back and
    up), dagger hand 1 px lower."""
    r = src("rogue_idle")
    move(r, 35, 40, 0, 7, -1, -1)          # cloak tail flicks back
    move(r, 19, 28, 13, 19, 0, 1)          # dagger hand drops 1 px
    return r


def _rogue_back(raise_left: bool) -> np.ndarray:
    b = T("""
        ........................
        ........................
        ..........####..........
        .........######.........
        ........########........
        .......##########.......
        .......##########.......
        .......##########.......
        .......##########.......
        .......##########.......
        ........########........
        ........#......#........
        .........######.........
        ......############......
        .....##############.....
        .....##############.....
        .....######..######.....
        .....#####.##.#####.....
        .....#####.##.#####.....
        .....######..######.....
        ....#######..#######....
        ....#######..#######....
        ....###.###..###.###....
        ....###.###..###.###....
        ....###.###..###.###....
        ...####.###..###.####...
        ...####.###..###.####...
        ...####.###..###.####...
        ...####.###..###.####...
        ...###.####..####.###...
        ...###.####..####.###...
        ...###.####..####.###...
        ..####.####..####.####..
        ..####.####..####.####..
        ..###.#####..#####.###..
        ..##.##.##....##.##.##..
        ...#..#..........#..#...
        ........##....##........
        ........##....##........
        ........##....##........
        ........##....##........
        ........##....##........
        ........##....##........
        ........##....##........
        ......####....####......
        ......#####...#####.....
        ......#####...#####.....
        ........................
    """)
    # raised knee on the right: shorter shin, boot higher
    b[40:47, 12:] = False
    over(b, "######", 13, 39)
    over(b, "######", 13, 40)
    over(b, """
        ###.
        ####
        ####
        .##.
        .##.
        .##.
        .##.
        .##.
        .##.
        .###
        ..##
        ..##
        ..##
    """, 1, 0)
    over(b, """
        ###
        ###
        ####
        ####
    """, 20, 22)
    return b if raise_left else b[:, ::-1].copy()


def rogue_climb(n: int) -> np.ndarray:
    return _rogue_back(raise_left=(n == 1))


def rogue_hurt() -> np.ndarray:
    """Doubled over and stumbling back, posed in blocks: hood/head drops 3 px
    and pitches 1 px forward over the chest (hunched), chest 2 px back, hips
    1 px back; the cloak flares out behind into the extra cell (a wedge with
    IDLE's fold lines). Body box at x 8..31 (ax = 8)."""
    r = src("rogue_idle")
    out = fit(r, 32, 48, 8)
    move(out, 14, 28, 0, 32, -2, 0)        # chest back
    move(out, 28, 36, 0, 32, -1, 0)        # hips back
    move(out, 0, 14, 0, 32, 1, 3)          # head down + forward (doubled over)
    poly(out, [(12, 22), (2, 31), (1, 37), (6, 36), (9, 39), (13, 35)])
    line(out, 10, 26, 4, 34, False)        # cloak folds
    line(out, 12, 28, 8, 36, False)
    return out


def rogue_dead() -> np.ndarray:
    """Sprawled on his back, head left: IDLE's hood turned face-up, torso,
    one knee up, the cloak spread flat on the floor under him (wider than the
    body, ragged edge), the dagger dropped ahead. ax = 8."""
    out = blank(40, 16)
    paste(out, rot_head("rogue_idle", 2, 13, 7, 19), 3, 3)   # hood, face up
    over(out, """
        ...##########...........
        ..############....##....
        ..############...####...
        ..###.######.#..##..##..
        ..############.##....##.
        ..##############......##
    """, 12, 7)                            # torso + raised knee
    over(out, """
        .#.##.####.#######.#####.###..#
        ###############################
    """, 1, 14)                            # cloak spread on the floor
    over(out, """
        ..#.....
        #######.
        ..#.....
    """, 32, 11)                           # dropped dagger
    return out


# ===========================================================================
# SKELETON
# ===========================================================================

def _skeleton_back(raise_left: bool) -> np.ndarray:
    b = T("""
        ........................
        ........................
        ........................
        ........................
        .........######.........
        ........########........
        .......##########.......
        .......##########.......
        .......##########.......
        .......##########.......
        .......###.##.###.......
        ........########........
        .........######.........
        ...........##...........
        ...........##...........
        ......############......
        .....#.....##.....#.....
        .......#########........
        ...........##...........
        .......##########.......
        ...........##...........
        ........########........
        ...........##...........
        .........######.........
        ...........##...........
        ...........##...........
        ...........##...........
        .........######.........
        ........###..###........
        ........##....##........
        ........##....##........
        .........#....#.........
        .........##..##.........
        .........##..##.........
        .........##..##.........
        .........#....#.........
        ........##....##........
        ........##....##........
        ........#......#........
        ........##....##........
        ........##....##........
        ........##....##........
        ........##....##........
        ........#......#........
        ........##....##........
        ........##....##........
        ........................
        .......####..####.......
    """)
    b[17, 16] = True                           # ribcage symmetric
    # raised right knee: shin + foot higher
    b[36:48, 12:] = False
    over(b, """
        ..##
        ..##
        ..#.
        ..##
        ..####
    """, 12, 36)
    # bony arms: left up to the rail, right down to a rung
    over(b, """
        ####
        #.#.
        .##.
        .#..
        .#..
        .#..
        .#..
        .##.
        ..#.
        ..#.
        ..#.
        ..#.
        ..##
        ...#
        ...#
        ....#
    """, 2, 0)
    over(b, """
        #.
        .#
        .#
        .#
        .#
        .#
        .##
        ..#
        ..#
        ..#
        .###
        .#.#
    """, 18, 16)
    return b if raise_left else b[:, ::-1].copy()


def skeleton_climb(n: int) -> np.ndarray:
    return _skeleton_back(raise_left=(n == 1))


def skeleton_hurt() -> np.ndarray:
    """WALK1 struck: skull knocked back and up off the neck (1-px gap), ribs
    rattled (alternate rows jolted 1 px), sword arm flung back (the CUT blade,
    pointing back-up)."""
    s = src("skeleton_walk1")
    move(s, 4, 14, 0, 24, -3, -2)            # skull knocked back + up
    s = shear_rows(s, {15: -1, 17: 1, 19: -1, 21: 1})   # ribs rattled
    over(s, """
        #.......
        .#......
        ..#.....
        ...#....
        ....#...
        ....##..
        ......#.
        .......#
    """, 1, 12)                                # arm + blade flung back
    return s


# ===========================================================================
# GOBLIN
# ===========================================================================

def _goblin_back(raise_left: bool) -> np.ndarray:
    b = T("""
        ........................
        ........................
        .........######.........
        ...#...##########...#...
        ...##.############.##...
        ....################....
        .....##############.....
        .....##############.....
        ......############......
        ......############......
        ......############......
        .......##########.......
        ........########........
        ........................
        ........########........
        .......##########.......
        .......##########.......
        .......##########.......
        .......###.##.###.......
        .......##########.......
        ........#.#..#.#........
        .........##..##.........
        .........##..##.........
        .........##..##.........
        ........................
        .........##..##.........
        .........##..##.........
        ........###..###........
        ........###..###........
        ........###..###........
        ........................
        .......####..####.......
    """)
    b[24:32, 12:] = False                       # raised right knee
    over(b, """
        .##.
        ###.
        ###.
        ###.
        ....
        ####
    """, 12, 23)
    over(b, """
        ###
        ###
        .##
        .##
        .##
        .##
        .##
        .##
        .##
        ..##
        ..##
        ...##
        ....#
        .....#
    """, 0, 1)
    over(b, """
        #..
        ##.
        .#.
        .##
        .###
        .###
    """, 17, 14)
    return b if raise_left else b[:, ::-1].copy()


def goblin_climb(n: int) -> np.ndarray:
    b = _goblin_back(raise_left=(n == 1))
    over(b, """
        ...##
        ..###
        ..##.
        .#o..
        #o...
    """, 7, 14)                                 # club tucked in the belt
    return b


def goblin_hurt() -> np.ndarray:
    """WALK1 hit: head snapped back (2 px back, 1 up), club (the raised head
    over the shoulder) dropped low in front, knees buckled (legs 2 px shorter,
    bent)."""
    g = src("goblin_walk1")
    g[3:14, 16:] = False                        # raised club out
    move(g, 0, 13, 0, 16, -2, -1)               # head snapped back
    g = del_rows(g, [22, 26])                   # knees buckle: shorter legs
    g = np.vstack([blank(24, 2), g])
    over(g, """
        .##...
        ###...
        .#....
        ..#...
        ..#...
        ...#..
        ..###.
        .#####
        .#####
        ..###.
    """, 15, 15)                                 # club dropped low in the fist
    return g


def goblin_dead() -> np.ndarray:
    """Flat on its back: WALK1's big head (mouth-teeth dither row, pointed
    ear now trailing down-left) face-up at the left, small body, both legs
    kicked up in the air with boots, club lying beside. 32 wide, ax = 4."""
    return T("""
        ................................
        ................................
        ................................
        ..................###.###.......
        ..................###.###.......
        ...................##..##.......
        ....########.......##..##.......
        ...##########......##..##.......
        ..###.##.#####.....##..##.......
        ..############.....##.##........
        ..#.#.#.#.####..#######.........
        ..############.#########........
        .#############.##.#.####......##
        ##.##########..#########..######
        #...########...########.......##
        ......####.....#######..........
    """)


# ===========================================================================
# GHOST
# ===========================================================================

GHOST_TAIL = (23, 28)     # FLOAT1 dither rows (data-only mask, §5.4)


def ghost_lunge() -> np.ndarray:
    """FLOAT2 thrown forward: whole body 3 px forward, mouth gaping, the arm lobe replaced by two clawed arms reaching
    into the forward cell; the dithered tail streams 3 px behind. 32 wide,
    ax = 0 (overhang forward)."""
    g = src("ghost_float2")
    g[12:18, 17:] = False                  # old arm lobe
    out = fit(g, 32, 32, 3)
    tail = out[24:30].copy()
    out[24:30] = False
    paste(out, tail, -4, 24)
    over(out, "oooo", 16, 15)              # mouth gaping
    over(out, "oooo", 16, 16)
    over(out, """
        .........##.#
        ###########..
        ############.
        ###########..
        .........##.#
        .............
        ..#######.#..
        .#########.#.
        ..#######.#..
    """, 19, 10)                           # clawed arms
    return out


def ghost_hurt() -> np.ndarray:
    """FLOAT1 torn: silhouette jagged (rows jolted), eyes stretched tall, mouth
    torn open, extra dither holes punched through the lower body."""
    g = src("ghost_float1")
    g[13:17, 17:] = False                        # arm lobe torn off
    over(g, """
        ..oo.oo..
        ..oo.oo..
    """, 10, 5)                                   # eyes stretch up
    over(g, """
        .oooo.
        oooooo
        o.oo.o
    """, 11, 13)                                  # torn mouth
    holes = checker(6, 18, 0)
    holes[::2] = False
    g[17:23, 3:21] &= ~holes
    g = shear_rows(g, {2: -1, 4: 1, 6: -1, 12: 1, 15: -1, 19: 1, 21: -1})
    over(g, "#.#", 20, 12)
    return g


def ghost_dead() -> np.ndarray:
    """Dissolving: FLOAT1 sinks 3 px, the upper half thins to sparse dither
    (1-in-4, then 1-in-2 lower), wisps rising above."""
    g = src("ghost_float1")
    g[13:17, 17:] = False
    g = np.vstack([blank(24, 3), g[:-3]])
    sparse = checker(32, 24, 0) & (np.mgrid[0:32, 0:24][0] % 2 == 0)
    half = checker(32, 24, 1)
    g[0:12] &= sparse[0:12]
    g[12:19] &= half[12:19]
    over(g, """
        ..#.......#.....
        .#.......#......
        ..#.......#.....
        ...#.....#......
    """, 5, 0)
    return g


# ===========================================================================
# RAT
# ===========================================================================

def rat_bite() -> np.ndarray:
    """RUN1 stretched into a lunge: body 4 px longer (one body column
    repeated), the whole rat 4 px forward so the head overhangs 8 px, jaws
    wide (upper jaw up 1, lower jaw dropped 2), forelegs reaching forward,
    hind legs kicked back, tail straight. 40 wide, ax = 0."""
    r = src("rat_run1")
    r[11:16, 0:7] = False                  # curled tail
    r[12:16, 7:24] = False                 # legs (re-posed)
    r = dup_cols(r, 12, 4)                 # 36 wide
    out = fit(r, 40, 16, 4)
    move(out, 5, 10, 34, 40, 0, -1)        # upper jaw up
    move(out, 10, 13, 32, 40, 1, 2)        # lower jaw dropped
    out[11, 0:12] = True                   # tail straight back
    over(out, """
        ......##..................#..#.
        ....##...................#..#..
        ..##....................#..#...
    """, 7, 13)                            # hind legs back / forelegs out
    return out


def rat_hurt() -> np.ndarray:
    """RUN1 hunched: back arched up 2 px in the middle, head tucked down, tail
    kinked upward."""
    r = src("rat_run1")
    r[11:16, 0:6] = False
    move(r, 3, 12, 10, 22, 0, -2)                # arch the back
    r[10:12, 10:22] |= src("rat_run1")[10:12, 10:22]
    move(r, 3, 12, 22, 32, 0, 2)                 # head tucked down
    over(r, """
        .#.
        #.#
        ...
        ..#
        .##
    """, 3, 7)
    over(r, "#####", 4, 12)                      # tail kink
    return r


def rat_dead() -> np.ndarray:
    """On its back: RUN1 flipped upside down onto the floor line, feet up,
    tail limp along the floor, eye X."""
    r = src("rat_run1")
    r[11:16, 0:7] = False
    f = trim(r[::-1])
    out = blank(32, 16)
    paste(out, f, 32 - f.shape[1], 16 - f.shape[0])
    out[15, 0:8] = True                          # limp tail on the floor
    return out


# ===========================================================================
# BAT
# ===========================================================================

def bat_dive() -> np.ndarray:
    """Diving forward: GLIDE's head (ears, eyes, fangs) at the point, both
    wings swept back into a chevron with scalloped trailing edges, claws
    thrust ahead. The lower wing is the upper one mirrored. 32 wide, ax = 0
    (overhang forward)."""
    up = T("""
        ................................
        ##..............................
        .####...........................
        ..######........................
        ...##.######....................
        .....####.######................
        ........####.#######............
        ............#########...........
    """)
    b = np.vstack([up, up[::-1]])
    paste(b, src("bat_glide")[1:10, 8:16], 19, 3)    # head + body
    over(b, """
        ..#.#...
        .#####..
        ##.#.##.
        ########
        ########
        #######.
        .#.#.#..
    """, 19, 4)
    over(b, """
        #.#.
        .#.#
    """, 25, 12)                           # claws forward
    return b


def bat_hurt() -> np.ndarray:
    """Tumbling: GLIDE body tilted, one wing crumpled up (FLAP UP's), the
    other drooping (FLAP DOWN's), eyes shut."""
    up = src("bat_flapup")
    dn = src("bat_flapdown")
    b = blank(24, 16)
    paste(b, up[0:9, 0:9], 0, 1)                 # left wing crumpled up
    paste(b, dn[3:14, 14:24], 14, 3)             # right wing hanging
    paste(b, src("bat_glide")[1:10, 7:17], 7, 3)  # body/head
    over(b, """
        ..........
        ..........
        ...##.##..
    """, 7, 3)
    b = shear_rows(b, {3: 1, 4: 1, 5: 1})
    return b


def bat_dead() -> np.ndarray:
    """Wings folded around the body, upside down, lying on the floor line."""
    b = blank(24, 16)
    over(b, """
        .....#####.....
        ...#########...
        ..###########..
        .####.###.####.
        .#############.
        ..###########..
        ...#.#####.#...
        .....#.#.#.....
        ......#.#......
    """, 4, 7)
    return b


# ===========================================================================
# SLIME
# ===========================================================================

def slime_lunge() -> np.ndarray:
    """STRETCH-then-surge: the body thrown forward into a wave, the front edge
    raised and curling over, back end thinned. 32 wide, ax = 0."""
    s = blank(32, 16)
    over(s, """
        ....................#######.....
        .................###########....
        ...............######..#######..
        .............########.....####..
        ...........###########.....###..
        .........###..##..#####......#..
        .......####.##..########........
        ......##################........
        .....####################.......
        ....######################......
        ...##.#.#.#.#.#.#.#.#.####......
        ..#########################.....
        .###########################....
        ############################....
    """, 0, 2)
    return s


def slime_hurt() -> np.ndarray:
    """SQUASH splattered: flattened 3 px lower, droplets flying off both
    sides."""
    s = src("slime_squash")
    s = np.vstack([blank(24, 3), s[:-3]])
    s[15] = s[14] | s[15]
    over(s, """
        ..#..............#.....
        #....#........#.....#..
        ...........#...........
        .#..................#..
        .......................
        #....................#.
    """, 0, 2)
    over(s, "o..o..o", 8, 12)
    return s


def slime_dead() -> np.ndarray:
    """A flat puddle with a last bubble and the surface sheen."""
    return T("""
        ........................
        ........................
        .........##.............
        ........#..#............
        ......######.#####......
        ...##################...
        .####.#.#.#.#.#.#.######
        ########################
    """)


# ===========================================================================
# WIZARD FX: ZAP tiles (8x8, attr $45)
# ===========================================================================
# CAST2's staff hand + orb spans rows 21-22 of the 48-px frame -> cell row 2
# of the body (rows 16..23), in-cell rows 5-6. The bolt is centred there, and
# enters/leaves every tile on in-cell row 5 (cols 0-1 / 6-7) so it tiles
# seamlessly; ZAP1 arcs up, ZAP2 down (+ a spark) = crackle when alternated.

ZAP1 = T("""
    ........
    ........
    ........
    ...##...
    ..#..#..
    ##....##
    .....#..
    ........
""")
ZAP2 = T("""
    ........
    ........
    .#......
    ........
    ........
    ##....##
    ..#..#..
    ...##...
""")


# ===========================================================================
# BACKGROUND TILES (8x8, prototype.md rev B §3.3/§4.1/§10.2 #35-41)
# ===========================================================================
# Colour comes from the attr (svg_sprites.TILE_ATTR); the canvas shows the
# glyph as one ink on black. Brick courses are 3 px tall with a 1-px mortar
# line so they read at 1x, and every glyph tiles seamlessly both ways.

BG_TILES = [
    # PLATFORM, white-on-BLUE: paper = the brick, ink = mortar. Row 0 is a
    # full mortar line = the walkable top edge; courses offset half a brick.
    ("PLATFORM", "#FFFFFF", T("""
        ########
        ...#....
        ...#....
        ...#....
        ########
        .......#
        .......#
        .......#
    """)),
    # End caps: the run's end gets a closed vertical mortar edge so the blue
    # band stops cleanly at the black ladder hole. _L = left end of a run
    # (the hole/wall is on its LEFT), _R = right end.
    ("PLATFORM_END_L", "#FFFFFF", T("""
        ########
        #..#....
        #..#....
        #..#....
        ########
        #......#
        #......#
        #......#
    """)),
    ("PLATFORM_END_R", "#FFFFFF", T("""
        ########
        ...#...#
        ...#...#
        ...#...#
        ########
        .......#
        .......#
        .......#
    """)),
    # WALL: brick OUTLINE (mortar = ink) so it reads as bricks both as dim
    # blue on black (air rows) and white on blue (floor rows, same glyph);
    # half-width (4-px) bricks differ from PLATFORM's 8-px ones so a wall
    # cell inside a floor row is still identifiable.
    ("WALL", "#0000D7", T("""
        ########
        #...#...
        #...#...
        #...#...
        ########
        ..#...#.
        ..#...#.
        ..#...#.
    """)),
    # LADDER_L/M/R: 3 cells = the 24-px climber width. 2-px rails one px in
    # from the outer edges, rungs every 4 px (rows 1 and 5) so a 4-px climb
    # step always passes one rung. Also the hole cells in floor rows.
    ("LADDER_L", "#D70000", T("""
        .##.....
        .#######
        .##.....
        .##.....
        .##.....
        .#######
        .##.....
        .##.....
    """)),
    ("LADDER_M", "#D70000", T("""
        ........
        ########
        ........
        ........
        ........
        ########
        ........
        ........
    """)),
    ("LADDER_R", "#D70000", T("""
        .....##.
        #######.
        .....##.
        .....##.
        .....##.
        #######.
        .....##.
        .....##.
    """)),
]


# ---------------------------------------------------------------------------
# Build the list (canvas order within each character = delivery order)
# ---------------------------------------------------------------------------

def build() -> None:
    add("knight", "CLIMB 1", knight_climb1(), 24, 48)
    add("knight", "CLIMB 2", knight_climb1()[:, ::-1].copy(), 24, 48)
    add("knight", "DEAD", knight_dead(), 40, 16)
    add("wizard", "IDLE 2", wizard_idle2(), 24, 48)
    add("wizard", "CLIMB 1", wizard_climb(1), 24, 48)
    add("wizard", "CLIMB 2", wizard_climb(2), 24, 48)
    add("wizard", "HURT", wizard_hurt(), 32, 48)
    add("wizard", "DEAD", wizard_dead(), 40, 16)
    add("rogue", "IDLE 2", rogue_idle2(), 24, 48)
    add("rogue", "CLIMB 1", rogue_climb(1), 24, 48)
    add("rogue", "CLIMB 2", rogue_climb(2), 24, 48)
    add("rogue", "HURT", rogue_hurt(), 32, 48)
    add("rogue", "DEAD", rogue_dead(), 40, 16)
    add("skeleton", "CLIMB 1", skeleton_climb(1), 24, 48)
    add("skeleton", "CLIMB 2", skeleton_climb(2), 24, 48)
    add("skeleton", "HURT", skeleton_hurt(), 24, 48)
    add("goblin", "CLIMB 1", goblin_climb(1), 24, 32)
    add("goblin", "CLIMB 2", goblin_climb(2), 24, 32)
    add("goblin", "HURT", goblin_hurt(), 24, 32)
    add("goblin", "DEAD", goblin_dead(), 32, 16)
    add("ghost", "LUNGE", ghost_lunge(), 32, 32)
    add("ghost", "HURT", ghost_hurt(), 24, 32)
    add("ghost", "DEAD", ghost_dead(), 24, 32)
    add("rat", "BITE", rat_bite(), 40, 16)
    add("rat", "HURT", rat_hurt(), 32, 16)
    add("rat", "DEAD", rat_dead(), 32, 16)
    add("bat", "DIVE", bat_dive(), 32, 16)
    add("bat", "HURT", bat_hurt(), 24, 16)
    add("bat", "DEAD", bat_dead(), 24, 16)
    add("slime", "LUNGE", slime_lunge(), 32, 16)
    add("slime", "HURT", slime_hurt(), 24, 16)
    add("slime", "DEAD", slime_dead(), 24, 8)


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

PREFIX_CHAR = {v: k for k, v in S.CHAR_PREFIX.items()}
HEADING = ('<div style="font-family: \'Press Start 2P\', monospace; font-size: 13px; '
           'color: #e8e6f0; margin: 24px 0 12px;">{}</div>')
LABEL = ('<div style="font-family: \'Press Start 2P\', monospace; font-size: 10px; '
         'color: #a9a7b8;">{}</div>')


def write_fragment() -> None:
    parts = ['<!-- Tome of the Dead "Draft 3" artboard: PROTO missing frames (docs/design/'
             'prototype.md §10.2). Generated by tools/gen_missing_frames.py from the '
             'existing canvas frames; paste as one artboard for review. -->',
             '<h2>DRAFT 3</h2>']
    order = []
    for c, _, _ in NEW:
        if c not in order:
            order.append(c)
    for c in order:
        parts.append(HEADING.format(html.escape(PREFIX_CHAR[c])))
        parts.append('<div style="display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-end;">')
        for cc, cap, bm in NEW:
            if cc == c:
                parts.append(S.svg_artboard_html(bm, INK[c], cap))
        parts.append('</div>')
    for section, tiles in (("FX TILES", [("ZAP1", INK["wizard"], ZAP1), ("ZAP2", INK["wizard"], ZAP2)]),
                           ("BG TILES", BG_TILES)):
        parts.append(f'<h2>{section}</h2>')
        parts.append('<div style="display: flex; gap: 16px; align-items: flex-end;">')
        for cap, ink, bm in tiles:
            parts.append('<div style="display: flex; flex-direction: column; gap: 8px;">')
            parts.append('<div style="padding: 8px; background: #000000; border: 2px solid #26263a;">'
                         + S.bitmap_to_svg(bm, ink, 6) + '</div>')
            parts.append(LABEL.format(cap))
            parts.append('</div>')
        parts.append('</div>')
    with open(FRAGMENT, "w") as f:
        f.write("\n".join(parts) + "\n")


def ink_rgb(char: str):
    c, b = S.INK_MAP[INK[char]]
    return S.spec_rgb(c, b)


def render(bm: np.ndarray, rgb, scale: int, box=None) -> Image.Image:
    h, w = bm.shape
    a = np.zeros((h, w, 3), np.uint8)
    a[bm] = rgb
    img = Image.fromarray(a).resize((w * scale, h * scale), Image.NEAREST)
    if box:
        d = ImageDraw.Draw(img)
        x0, bw = box
        d.rectangle([x0 * scale, 0, (x0 + bw) * scale - 1, h * scale - 1], outline=(90, 60, 60))
    return img


REF = {"knight": "knight_idle1", "wizard": "wizard_idle", "rogue": "rogue_idle",
       "skeleton": "skeleton_walk1", "goblin": "goblin_walk1", "ghost": "ghost_float1",
       "rat": "rat_run1", "bat": "bat_glide", "slime": "slime_wobble"}


def write_sheet(scale: int = 4) -> None:
    rows = []
    order = []
    for c, _, _ in NEW:
        if c not in order:
            order.append(c)
    for c in order:
        items = [(f"{c.upper()} ref {REF[c].split('_', 1)[1]}", SRC[REF[c]], None)]
        for cc, cap, bm in NEW:
            if cc == c:
                ax = S.ANCHOR_X.get(f"{c}_{S.slug(cap)}", 0)
                items.append((cap, bm, (ax, S.BODY_W[c])))
        rows.append((c, items))
    rows.append(("fx", [("ZAP1", np.tile(ZAP1, (1, 4)), None), ("ZAP2", np.tile(ZAP2, (1, 4)), None)]))
    rows.append(("bg", [(n, np.tile(bm, (2, 3)), None) for n, _, bm in BG_TILES]))
    pad, lab = 14, 16
    W = 1500
    y = pad
    placed = []
    for c, items in rows:
        rgb = ink_rgb("wizard") if c == "fx" else (230, 230, 230) if c == "bg" else ink_rgb(c)
        x = pad
        rh = 0
        for cap, bm, box in items:
            img = render(bm, rgb, scale, box)
            placed.append((x, y, img, cap))
            x += img.width + pad
            rh = max(rh, img.height)
        y += rh + lab + pad
    sheet = Image.new("RGB", (W, y + 24), (16, 16, 24))
    d = ImageDraw.Draw(sheet)
    for x, yy, img, cap in placed:
        d.text((x, yy), cap, fill=(200, 200, 210))
        sheet.paste(img, (x, yy + lab))
    d.text((pad, y + 4), "Draft 3 new frames beside each kind's reference frame; dark red box = "
           "24/32-px body box placed by the frame's ax (§5.3). ZAP tiles 4x repeated, BG tiles 3x2 repeated (glyph only; in-game colours: preview/room_mock.png).",
           fill=(170, 170, 190))
    sheet.save(SHEET_PNG)


def frame(name: str) -> np.ndarray:
    for c, cap, bm in NEW:
        if f"{c}_{S.slug(cap)}" == name:
            return bm
    return SRC[name]


def gif(path: str, seq, char: str, scale: int = 4, bg_w: int | None = None) -> None:
    """seq = [(frame name, ticks)], 1 tick = 40 ms (25 Hz). Frames are placed by
    their anchors on a common stage, feet on one line (§5.3)."""
    ref = SRC[REF[char]]
    rh = ref.shape[0]
    rgb = ink_rgb(char)
    items = []
    for n, t in seq:
        bm = frame(n)
        ax = S.ANCHOR_X.get(n, KNOWN_AX.get(n, 0))
        items.append((bm, ax, t))
    left = max(ax for _, ax, _ in items) + 4
    W = left + max(bm.shape[1] - ax for bm, ax, _ in items) + 4
    H = max(rh, max(bm.shape[0] for bm, _, _ in items)) + 4
    frames, durs = [], []
    for bm, ax, t in items:
        st = np.zeros((H, W, 3), np.uint8)
        st[H - 2:, :] = (60, 60, 90)                 # floor line
        h, w = bm.shape
        x0 = left - ax
        y0 = H - 2 - h
        sub = st[y0:y0 + h, x0:x0 + w]
        sub[bm] = rgb
        frames.append(Image.fromarray(st).resize((W * scale, H * scale), Image.NEAREST))
        durs.append(40 * t)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durs, loop=0)


def write_previews() -> None:
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    P = lambda n: os.path.join(PREVIEW_DIR, n)  # noqa: E731
    for c, idle in (("knight", "knight_idle1"), ("wizard", "wizard_idle"),
                    ("rogue", "rogue_idle"), ("skeleton", "skeleton_walk1"),
                    ("goblin", "goblin_walk1")):
        gif(P(f"{c}_climb.gif"), [(f"{c}_climb1", 4), (f"{c}_climb2", 4)] * 3, c)
    for c, idle in (("wizard", "wizard_idle"), ("rogue", "rogue_idle")):
        gif(P(f"{c}_idle.gif"), [(idle, 16), (f"{c}_idle2", 16)] * 2, c)
    hurt = {"knight": "knight_hurt"}
    rest = {"knight": "knight_idle1", "wizard": "wizard_idle", "rogue": "rogue_idle",
            "skeleton": "skeleton_walk1", "goblin": "goblin_walk1", "ghost": "ghost_float1",
            "rat": "rat_run1", "bat": "bat_glide", "slime": "slime_wobble"}
    dead = {"skeleton": "skeleton_collapsed"}
    for c, r in rest.items():
        h = hurt.get(c, f"{c}_hurt")
        gif(P(f"{c}_hurt.gif"), [(r, 12), (h, 3), (r, 12), (h, 3)], c)
        gif(P(f"{c}_death.gif"), [(r, 12), (h, 3), (dead.get(c, f"{c}_dead"), 24)], c)
    gif(P("ghost_attack.gif"), [("ghost_float1", 6), ("ghost_float2", 2), ("ghost_lunge", 4)] * 2, "ghost")
    gif(P("rat_attack.gif"), [("rat_run1", 6), ("rat_bite", 4)] * 2, "rat")
    gif(P("bat_attack.gif"), [("bat_glide", 6), ("bat_flapup", 2), ("bat_dive", 4)] * 2, "bat")
    gif(P("slime_attack.gif"), [("slime_wobble", 6), ("slime_squash", 2), ("slime_lunge", 4)] * 2, "slime")
    gif(P("knight_block_hurt.gif"), [("knight_idle1", 8), ("knight_block", 4), ("knight_idle1", 8),
                                     ("knight_hurt", 4)], "knight")


def room_mock(path: str, scale: int = 3) -> None:
    """One PROTO room (prototype.md §3.3): 3 storeys (air rows 7s..7s+5, floor
    row 7s+6), walls at cols 0/31 (ATTR_WALL in air rows, ATTR_FLOOR in floor
    rows), ladder segments {12,2} (hole in floor row 13) and {22,1} (hole in
    row 6), the Knight mid-climb through row 13 (CLIMB1, px = col*8), a Goblin
    standing on storey 2, a Bat in storey 0 and the Wizard's bolt. Rendered
    with real Spectrum attribute rules (one ink+paper per cell, masked sprites,
    exact-footprint attr stamp) — HUD rows 21-23 left black."""
    tiles = {n.lower(): bm for n, _, bm in BG_TILES}
    tiles["zap1"] = ZAP1
    bmp = np.zeros((192, 256), bool)
    attr = np.zeros((24, 32), np.uint8)
    cells = {}
    for r in range(21):
        floor = r % 7 == 6
        for c in range(32):
            if c in (0, 31):
                cells[(r, c)] = ("wall", 0x0F if floor else 0x01)
            elif floor:
                cells[(r, c)] = ("platform", 0x0F)
    for col, s_ in ((12, 2), (22, 1)):
        for r in range(7 * s_ - 1, 7 * s_ + 6):
            for i, n in enumerate(("ladder_l", "ladder_m", "ladder_r")):
                cells[(r, col + i)] = (n, 0x02)
        fr = 7 * s_ - 1
        cells[(fr, col - 1)] = ("platform_end_r", 0x0F)
        cells[(fr, col + 3)] = ("platform_end_l", 0x0F)
    for (r, c), (n, a) in cells.items():
        bmp[r * 8:r * 8 + 8, c * 8:c * 8 + 8] = tiles[n]
        attr[r, c] = a

    def sprite(name: str, char: str, px: int, py: int) -> None:
        bm = frame(name)
        solid = S.make_mask(bm, S.OUTLINE, name)
        h, w = bm.shape
        reg = bmp[py:py + h, px:px + w]
        reg &= solid == False  # noqa: E712
        reg |= bm
        c, b = S.INK_MAP[INK[char]]
        a = c | (0x40 if b else 0)
        attr[py // 8:(py + h + 7) // 8, px // 8:(px + w + 7) // 8] = a

    sprite("knight_climb1", "knight", 12 * 8, 10 * 8)        # rows 10..15, through row 13
    sprite("goblin_walk1", "goblin", 22 * 8, 16 * 8)        # storey 2: rows 16..19
    sprite("bat_glide", "bat", 15 * 8, 3 * 8)              # storey 0 air band
    sprite("wizard_cast2", "wizard", 3 * 8, 0 * 8)          # storey 0: rows 0..5
    for c in range(7, 10):                                   # bolt in the gap cells
        bmp[16:24, c * 8:c * 8 + 8] = ZAP1
        attr[2, c] = 0x45
    rgb = np.zeros((192, 256, 3), np.uint8)
    for r in range(24):
        for c in range(32):
            a = int(attr[r, c])
            br = bool(a & 0x40)
            ink = gfx_rgb(a & 7, br)
            pap = gfx_rgb((a >> 3) & 7, br)
            blk = bmp[r * 8:r * 8 + 8, c * 8:c * 8 + 8]
            rgb[r * 8:r * 8 + 8, c * 8:c * 8 + 8] = np.where(blk[..., None], ink, pap)
    Image.fromarray(rgb).resize((256 * scale, 192 * scale), Image.NEAREST).save(path)


def gfx_rgb(c: int, bright: bool):
    return S.gfx_convert.colour_rgb(c, bright)


def main() -> int:
    build()
    write_fragment()
    write_sheet()
    write_previews()
    room_mock(os.path.join(PREVIEW_DIR, "room_mock.png"))
    print(f"built {len(NEW)} sprite frames + 2 ZAP tiles + {len(BG_TILES)} background tiles")
    print(f"wrote {os.path.relpath(FRAGMENT, REPO)}, {os.path.relpath(SHEET_PNG, REPO)}, "
          f"{os.path.relpath(PREVIEW_DIR, REPO)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
