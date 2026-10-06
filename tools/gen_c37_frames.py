#!/usr/bin/env python3
"""gen_c37_frames.py — deterministic authoring of the Stage 3C C3-7 hero frames.

DRAFTS for the user's review on the Design canvas (no engine data): the frames
are built FROM THE HEROES' EXISTING CANVAS FRAMES (head/torso/robe rows copied
from IDLE, re-posed with explicit row moves and small hand-typed overlays,
'#' = ink, 'o' = force paper). Nothing here comes from AI raster.

  KNIGHT JUMP 1      24x48  take-off / landing crouch (game.md §2.4 ticks 0, 13)
  KNIGHT JUMP 2      24x48  airborne tuck (ticks 1..12, drawn in motion)
  WIZARD JUMP 1      24x48  crouch
  WIZARD JUMP 2      24x48  airborne, robe flared, boots tucked
  WIZARD STAFF SWING 40x48  melee strike (game.md §6.2: CAST1 -> STAFF_SWING)

Heroes face RIGHT; the engine mirrors for left (svg_sprites.py: only
SYMMETRIC back views skip the mirror).

Outputs:
  assets/gfx/source/c37_grid/<name>.grid   3-state grids (mask = filled
                                            silhouette + 1-px 8-neighbour
                                            outline, svg_sprites.make_mask)
  assets/gfx/source/c37_frames.svg.html    canvas-convention fragment (x4):
                                            new frames + a compare strip with
                                            the canvas IDLE/WALK frames
  --png-dir DIR                             PNG previews (review only)

Usage: python3 tools/gen_c37_frames.py [--png-dir DIR]
"""

from __future__ import annotations

import argparse
import html
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gfx_convert as GC  # noqa: E402
import svg_sprites as S  # noqa: E402

REPO = S.REPO
GRID_DIR = os.path.join(REPO, "assets/gfx/source/c37_grid")
FRAGMENT = os.path.join(REPO, "assets/gfx/source/c37_frames.svg.html")
ZX0 = os.path.join(REPO, "tools/bin/zx0")
SCALE = 4

# ---------------------------------------------------------------------------
# helpers (bool arrays, True = ink)
# ---------------------------------------------------------------------------


def blank(w: int, h: int) -> np.ndarray:
    return np.zeros((h, w), bool)


def paste(dst, src, x, y):
    h, w = src.shape
    H, W = dst.shape
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x0 < x1 and y0 < y1:
        dst[y0:y1, x0:x1] |= src[y0 - y:y1 - y, x0 - x:x1 - x]


def over(dst, text: str, x: int, y: int) -> None:
    """Overlay rows: '#' ink, 'o' paper, anything else leaves dst."""
    rows = [r for r in text.strip("\n").splitlines()]
    for dy, r in enumerate(rows):
        r = r.split("|", 1)[1] if "|" in r else r      # allow "37|row"
        if len(r) > dst.shape[1] - x:
            raise ValueError(f"overlay row {dy} too wide: {r!r}")
        for dx, c in enumerate(r):
            yy, xx = y + dy, x + dx
            if 0 <= yy < dst.shape[0] and 0 <= xx < dst.shape[1]:
                if c == "#":
                    dst[yy, xx] = True
                elif c == "o":
                    dst[yy, xx] = False


def clear(bm, y0, y1, x0, x1):
    bm[y0:y1, x0:x1] = False


SRC: dict[str, np.ndarray] = {}
INK: dict[str, str] = {}
_frames, _ = S.parse_sheet(S.SHEET)
for _f in _frames:
    if _f.kind == "sprite":
        p = S.CHAR_PREFIX[_f.character]
        SRC[f"{p}_{S.slug(_f.caption)}"] = _f.bitmap.copy()
        INK[p] = _f.ink_hex
CAPTION = {f"{S.CHAR_PREFIX[f.character]}_{S.slug(f.caption)}": f.caption
           for f in _frames if f.kind == "sprite"}


def src(n):
    return SRC[n].copy()


# ===========================================================================
# KNIGHT  (IDLE 1 rows: helmet 1-10, arms 11-15, shield/torso 16-29,
#          hips 29-33, legs 34-42, boots 44-46; sword grip col 21)
# ===========================================================================

def knight_jump1() -> np.ndarray:
    """Crouch: IDLE 1 rows 0..31 drop 5 px; knees bent wide over the boots."""
    i = src("knight_idle1")
    b = blank(24, 48)
    paste(b, i[0:32], 0, 5)            # helmet .. hip -> rows 5..36
    over(b, """
37|.........###..###.......
38|........####..####......
39|.......####....####.....
40|.......###.....#.###....
41|......####......###.....
42|......###.......####....
43|........................
44|.....#####......#####...
45|.....######.....######..
46|.....######.....######..
""", 0, 37)
    return b


def knight_jump2() -> np.ndarray:
    """Airborne tuck, sword raised (user review 2026-10-06): IDLE 1 upper
    body with the low sword + fist removed; the arm lifts the fist to helmet
    height, blade straight up beside the helmet; front knee up, back leg
    folded."""
    i = src("knight_idle1")
    b = blank(24, 48)
    paste(b, i[0:31], 0, 0)            # helmet .. belt
    clear(b, 0, 31, 19, 24)            # idle sword (blade rows 5-19) + fist
    over(b, """
 0|.....................##.
 1|.....................##.
 2|.....................##.
 3|.....................##.
 4|.....................##.
 5|.....................##.
 6|.....................##.
 7|.....................##.
 8|...................#####
 9|....................###.
10|...................####.
11|..................###o#.
12|.................####...
13|.................###....
14|.................##.....
""", 0, 0)
    over(b, """
31|.........#########......
32|........###########.....
33|........####.#######....
34|.......####...#######...
35|.......###.....###.##...
36|......####.....####.....
37|.....####......####.....
38|....####......####......
39|...#####......####......
40|..######.....######.....
41|..####.......#######....
42|...............######...
""", 0, 31)
    return b


# ===========================================================================
# WIZARD  (IDLE rows: hat 0-13, face 15-17, beard 18-24, robe 25-45,
#          boots 46-47; staff col 19 with the crook at cols 16-20 rows 3-13)
# ===========================================================================

def wizard_jump1() -> np.ndarray:
    """Crouch: hat..waist (rows 0..30) drop 4 px over the robe's lower half;
    the hem flares 1 px each side (knees bent under the robe)."""
    i = src("wizard_idle")
    b = blank(24, 48)
    paste(b, i[0:31], 0, 4)            # rows 0..30 -> 4..34
    paste(b, i[35:48], 0, 35)          # robe skirt + boots unchanged
    over(b, """
43|..####.#####.###..#.....
44|..####.#####.####.#.....
45|..#.#.#.#.#.#.#.........
""", 0, 43)
    return b


def wizard_jump2() -> np.ndarray:
    """Airborne: IDLE down to row 38, then the skirt flares and lifts,
    boots tucked under it."""
    i = src("wizard_idle")
    b = blank(24, 48)
    paste(b, i[0:39], 0, 0)
    over(b, """
39|...####.####.###.#.#....
40|..####.#####.####...#...
41|.####.######.#####......
42|####.#.#.#.#.#.#.##.....
43|........................
44|......####..#####.......
45|.....#####..######......
""", 0, 39)
    return b


def _wizard_nostaff() -> np.ndarray:
    """IDLE without the staff, its crook and the gripping hand."""
    b = src("wizard_idle")
    clear(b, 0, 46, 19, 24)            # shaft col 19 + crook cols 19-20
    clear(b, 3, 14, 16, 19)            # crook's top and left curl
    clear(b, 24, 28, 17, 19)           # gripping hand
    return b


def wizard_staffraise() -> np.ndarray:
    """Wind-up (user review 2026-10-06; precedes STAFF SWING, no spell
    spark): the upper body leans back 1-2 px, the sleeve rises to hat-brim
    height and lifts the staff 4 px (the idle crook now tops the frame), its
    foot off the floor."""
    i = _wizard_nostaff()
    b = blank(24, 48)
    paste(b, i[0:25], -2, 0)            # hat .. beard lean back 2 px
    paste(b, i[25:31], -1, 25)          # waist 1 px
    paste(b, i[31:48], 0, 31)           # skirt + boots planted
    crook = SRC["wizard_idle"][3:12, 16:21]
    paste(b, crook, 17, 0)              # crook rows 0..8, cols 17..21
    over(b, """
 9|.....................#..
10|.....................#..
11|.....................#..
12|...................####.
13|..................##o###
14|..................####o#
15|.................####.#.
16|................####..#.
17|...............###....#.
18|...............##.....#.
19|......................#.
20|......................#.
21|......................#.
22|......................#.
23|......................#.
24|......................#.
25|......................#.
26|......................#.
27|......................#.
28|......................#.
29|......................#.
30|......................#.
""", 0, 9)
    return b




def wizard_staffswing() -> np.ndarray:
    """Strike: sleeve swings forward at beard height, fist at col 23, the
    staff levelled at the foe's head with the crook (idle crook turned 90°
    clockwise: hook on top) at the far end; an arc trail over the swing
    (knight SLASH convention)."""
    b = blank(40, 48)
    paste(b, _wizard_nostaff(), 0, 0)
    over(b, """
 0|......................#.#####...........
 1|...........................#####........
 2|...............................##...##..
 3|...................................#..#.
 4|..................................#....#
 5|..................................#....#
 6|.................................##...#.
 7|................................##......
 8|...............................##.......
 9|..............................##........
10|.............................##.........
11|............................##..........
12|...........................##...........
13|..........................##............
14|.........................##.............
15|......................####..............
16|..................#####o##..............
17|.................#####o####.............
18|.................####o#####.............
19|.................###o..###..............
20|.................#####..................
21|.................###....................
""", 0, 0)
    return b


FRAMES = [
    ("knight", "JUMP 1", knight_jump1),
    ("knight", "JUMP 2", knight_jump2),
    ("wizard", "JUMP 1", wizard_jump1),
    ("wizard", "JUMP 2", wizard_jump2),
    ("wizard", "STAFF RAISE", wizard_staffraise),
    ("wizard", "STAFF SWING", wizard_staffswing),
]
COMPARE = {"knight": ["knight_idle1", "knight_walk1", "knight_walk3", "knight_slash"],
           "wizard": ["wizard_idle", "wizard_walk1", "wizard_cast1", "wizard_cast2"]}
HEADING = {"knight": "KNIGHT", "wizard": "WIZARD"}
# Rev 2 (user review 2026-10-06): changed / new frames, flagged in the fragment.
REV2 = {"knight": "REV 2 (2026-10-06): JUMP 2 redrawn, sword raised. JUMP 1 unchanged.",
        "wizard": "REV 2 (2026-10-06): STAFF RAISE is new (wind-up before STAFF SWING, "
                  "no spell spark). JUMP 1/2 and STAFF SWING unchanged."}

# ---------------------------------------------------------------------------
# outputs
# ---------------------------------------------------------------------------


def svg(bm, ink):
    h, w = bm.shape
    gp = S.grid_path(w, h)
    return (f'<svg width="{w * SCALE}" height="{h * SCALE}" viewBox="0 0 {w} {h}" '
            f'shape-rendering="crispEdges" style="display: block;">'
            f'<rect width="{w}" height="{h}" fill="#000000"></rect>'
            f'<path d="{gp}" stroke="{S.GRID_STROKE}" stroke-width="0.12" fill="none"></path>'
            f'<path d="{S.bitmap_to_path(bm)}" fill="{ink}"></path></svg>')


def artboard(bm, ink, caption):
    h, w = bm.shape
    cap = html.escape(f"{caption} · {w}×{h}")
    return ('<div style="display: flex; flex-direction: column; gap: 8px; align-items: flex-start;">\n'
            '<div style="padding: 8px; background: #000000; border: 2px solid #26263a;">'
            f'{svg(bm, ink)}</div>\n'
            f'<div style="font-size: 11px; letter-spacing: 1px; color: #a9a7b8;">{cap}</div>\n</div>')


def heading(p):
    return ('<div style="font-family: \'Press Start 2P\', monospace; font-size: 13px; '
            f'color: #e8e6f0; margin: 24px 0 12px;">{HEADING[p]}</div>')


ROW = '<div style="display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-end;">'
NOTE = '<p style="font-size: 11px; color: #a9a7b8; margin: 8px 0;">{}</p>'


def pack(bm, solid):
    rows = GC.pack_sprite(bm, solid, layout="native")
    return bytes(x for r in rows for x in r)


def zx0_len(data: bytes) -> int:
    with tempfile.TemporaryDirectory() as d:
        i, o = os.path.join(d, "f.bin"), os.path.join(d, "f.zx0")
        open(i, "wb").write(data)
        subprocess.run([ZX0, "-f", i, o], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        return os.path.getsize(o)


def grid_text(name, p, caption, bm, solid, ink, ax, ay):
    h, w = bm.shape
    lines = ["# WazHack/ZX gfx text grid — DRAFT generated by tools/gen_c37_frames.py "
             "(edit that); C3-7, not on the canvas yet.",
             f"# name: {name}", f"# size: {w}x{h}", f"# character: {HEADING[p]}",
             f"# caption: {caption}", f"# ink: {ink}", f"# anchor: {ax} {ay}",
             "# legend: '#' ink, '+' opaque paper (mask 0, data 0), '.' transparent", "#"]
    for y in range(h):
        lines.append("".join("#" if bm[y, x] else "+" if solid[y, x] else "."
                             for x in range(w)))
    return "\n".join(lines) + "\n"


def render(bm, solid, ink, scale=SCALE):
    h, w = bm.shape
    rgb = tuple(int(ink[i:i + 2], 16) for i in (1, 3, 5))
    a = np.zeros((h, w, 3), np.uint8)
    a[:] = (52, 52, 84)                 # transparent = slate
    a[solid] = (0, 0, 0)
    a[bm] = rgb
    return Image.fromarray(a).resize((w * scale, h * scale), Image.NEAREST)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--png-dir")
    args = ap.parse_args()
    os.makedirs(GRID_DIR, exist_ok=True)
    built = []
    for p, cap, fn in FRAMES:
        bm = fn()
        name = f"{p}_{S.slug(cap)}"
        ref = SRC["knight_idle1" if p == "knight" else "wizard_idle"]
        ax, ay, iou, _ = S.best_anchor(ref, bm)
        solid = S.make_mask(bm, S.OUTLINE, name)
        # attribute legality: one ink + black paper per cell by construction;
        # gfx_convert's own validation runs on the packed bytes below.
        raw = pack(bm, solid)
        exp = bm.shape[0] * 2 * bm.shape[1] // 8
        assert len(raw) == exp, (name, len(raw), exp)
        z = zx0_len(raw)
        body = S.BODY_W[p]
        ax_l = bm.shape[1] - ax - body
        ok = ax % 4 == 0 and 0 <= ax <= 8 and 0 <= ax_l <= 16
        with open(os.path.join(GRID_DIR, name + ".grid"), "w") as f:
            f.write(grid_text(name, p, cap, bm, solid, INK[p], ax, ay))
        built.append((p, cap, name, bm, solid, raw, z, ax, ay, ok))
        print(f"{name:22s} {bm.shape[1]}x{bm.shape[0]} raw={len(raw):4d} zx0={z:4d} "
              f"({len(raw)/z:.2f}x) ax={ax} ay={ay} iou={iou:.2f} anchor_ok={ok}")
    for p in ("knight", "wizard"):
        blk = b"".join(r for q, *_rest in built if q == p for r in [_rest[4]])
        print(f"{p} block raw={len(blk)} zx0={zx0_len(blk)} (GEN_SCRATCH 1536)")
    # fragment
    out = ["<!-- WazHack/ZX C3-7 DRAFT artboard (Stage 3C): hero JUMP 1/2 and the Wizard's "
           "STAFF SWING. Generated by tools/gen_c37_frames.py from the canvas IDLE/WALK frames; "
           "paste as one artboard for review. Heroes face right (the engine mirrors). -->",
           "<h2>C3-7 DRAFT</h2>"]
    for p in ("knight", "wizard"):
        out.append(heading(p))
        out.append(NOTE.format(REV2[p]))
        out.append(ROW)
        for q, cap, name, bm, *_ in built:
            if q == p:
                out.append(artboard(bm, INK[p], cap))
        out.append("</div>")
        out.append(NOTE.format("Compare: canvas frames beside the new ones "
                               "(identical copies, skipped on import)."))
        out.append(ROW)
        for n in COMPARE[p]:
            out.append(artboard(SRC[n], INK[p], CAPTION[n]))
        for q, cap, name, bm, *_ in built:
            if q == p:
                out.append(artboard(bm, INK[p], cap))
        out.append("</div>")
    with open(FRAGMENT, "w") as f:
        f.write("\n".join(out) + "\n")
    # importability self-check: the fragment parses with the canvas importer
    fr, _ = S.parse_sheet(FRAGMENT)
    for q, cap, name, bm, *_ in built:
        hit = [f for f in fr if S.CHAR_PREFIX[f.character] == q and f.caption == cap]
        assert hit and all(np.array_equal(h.bitmap, bm) for h in hit), name
    print(f"wrote {os.path.relpath(FRAGMENT, REPO)} ({len(fr)} artboards, parse OK)")
    if args.png_dir:
        os.makedirs(args.png_dir, exist_ok=True)
        for q, cap, name, bm, solid, *_ in built:
            render(bm, solid, INK[q]).save(os.path.join(args.png_dir, name + ".png"))
        for p in ("knight", "wizard"):
            ims = [render(SRC[n], S.make_mask(SRC[n], True), INK[p]) for n in COMPARE[p]]
            ims += [render(bm, solid, INK[p]) for q, c, n, bm, solid, *_ in built if q == p]
            W = sum(i.width for i in ims) + 16 * (len(ims) - 1)
            strip = Image.new("RGB", (W, 48 * SCALE), (24, 24, 36))
            x = 0
            for im in ims:
                strip.paste(im, (x, 0))
                x += im.width + 16
            strip.save(os.path.join(args.png_dir, f"{p}_compare.png"))
        print(f"previews -> {args.png_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
