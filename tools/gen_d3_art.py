#!/usr/bin/env python3
"""gen_d3_art.py — Stage 3D D3-3 combat art: import + missing frames (DRAFTS).

For the user's review on the Design canvas BEFORE engine wiring: no
assets/gfx/sprites/*.asm, index.asm or src/ data is written here (that is D3-4,
after approval and re-vendoring). Everything is deterministic; no AI raster.

IMPORTED (approved concept rounds R3/R4, assets/gfx/concept/grid/sprites/*):
  game.md §6.1 spell projectiles + impacts, §6.2 power_burst / staff_bonk,
  §6.3 arrow fly/hit + dagger spin (2 frames, designer 2026-10-06), and the
  Warrior THROW / BOW / WHIRL frames. Pixels are taken verbatim; the ink is
  re-mapped to the attr game.md §6 specifies (Knight frames: the canvas
  Knight's #FFFFFF; arrows $07 -> #D7D7D7). The mask is re-derived with
  svg_sprites.make_mask (filled silhouette + 1-px 8-neighbour outline).

NEW (drawn here):
  KNIGHT POWER STRIKE 40x48 — canvas SLASH body (lunge stance), the sword
    brought down two-thirds of an overhead chop: broad blade (paper fuller)
    angled down-forward, a heavy 2-px swing arc over the helmet.
  STATUS ICONS 8x8 x7 (§6.4, panel glyphs row 21 cols 30-31): FROZEN $45,
    ASLEEP $41, STUNNED $07, CONFUSED $43, FEAR $42, POISON $44, WEAK $42.

Outputs:
  assets/gfx/source/d3_grid/<name>.grid    3-state grids (icons: 2-state tile)
  assets/gfx/source/d3_frames.svg.html     canvas-convention fragment (x4),
                                            NEW vs IMPORTED badges
  --png-dir DIR                             PNG previews (review only)

Validation (all must pass, else exit != 0): the fragment re-parses with the
canvas importer to the same bitmaps; canvas + fragment run through the REAL
pipeline (svg_sprites.import_sheet -> gfx_convert native/tile -> DEFB decode:
clash + data/mask round-trip) into a temp dir; per-frame raw + ZX0 sizes and
the zx0_sources block DP (<= 1,536 B unpack, <= 4 frames) with a dzx0
round-trip.

Usage: python3 tools/gen_d3_art.py [--png-dir DIR]
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
CONCEPT = os.path.join(REPO, "assets/gfx/concept/grid/sprites")
GRID_DIR = os.path.join(REPO, "assets/gfx/source/d3_grid")
FRAGMENT = os.path.join(REPO, "assets/gfx/source/d3_frames.svg.html")
SCALE = 4

# ---------------------------------------------------------------------------
# helpers (bool arrays, True = ink)
# ---------------------------------------------------------------------------


def blank(w: int, h: int) -> np.ndarray:
    return np.zeros((h, w), bool)


def over(dst, text: str, x: int, y: int) -> None:
    """Overlay rows: '#' ink, 'o' paper, anything else leaves dst."""
    for dy, r in enumerate(text.strip("\n").splitlines()):
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


def glyph(text: str) -> np.ndarray:
    rows = [r.strip() for r in text.strip("\n").splitlines()]
    assert len(rows) == 8 and all(len(r) == 8 for r in rows), rows
    return np.array([[c == "#" for c in r] for r in rows])


def concept(name: str) -> np.ndarray:
    fg, _solid, _w, _h = GC.parse_grid_text_mask(
        open(os.path.join(CONCEPT, name + ".grid")).read(), None, None)
    return np.array(fg, bool)


CANVAS: dict[str, np.ndarray] = {}
_frames, _ = S.parse_sheet(S.SHEET)
for _f in _frames:
    if _f.kind == "sprite":
        CANVAS[f"{S.CHAR_PREFIX[_f.character]}_{S.slug(_f.caption)}"] = _f.bitmap.copy()

# ===========================================================================
# NEW: KNIGHT POWER STRIKE 40x48 (ax 4, game.md §11.1)
# ===========================================================================


def knight_powerstrike() -> np.ndarray:
    """SLASH body and lunge (rows 19+ and cols < 23 unchanged); arm, sword
    and trail redrawn. A vertical overhead chop caught at the moment it
    lands: arm level at the shoulder (SLASH gauntlet), sword point-down in the
    target's column (cols 29-31: 3-px blade with a paper fuller), square
    crossguard, and a 2-px swing arc from above the helmet (where WIND-UP
    held the sword) over to the blade, thickening toward it. SLASH = level
    thrust with a thin trail, FOLLOW = low diagonal; this is the only
    point-down blade, so the three read apart at a glance."""
    b = CANVAS["knight_slash"].copy()
    b[0:19, 23:] = False                       # SLASH arm, sword and trail
    # swing arc: annulus centred on the fist, thickness grows along the swing
    cy, cx, r_out = 17.0, 28.0, 11.6
    for y in range(0, 30):
        for x in range(22, 40):
            r = np.hypot(y - cy, x - cx)
            t = np.degrees(np.arctan2(y - cy, x - cx))      # -90 = straight up
            if -100 <= t <= 12:
                w = 1.0 + 1.9 * (t + 100) / 112             # 1.0 .. 2.9 px
                if r_out - w <= r <= r_out:
                    b[y, x] = True
    over(b, """
10|.....##....
11|.....##....
12|.....##....
13|#######....
14|########...
15|.#######...
16|...#####...
17|.#########.
18|..#.....#..
19|...##o##...
20|...##o##...
21|...##o##...
22|...##o##...
23|...##o##...
24|...##o##...
25|...##o##...
26|...##o##...
27|...##o##...
28|...##o##...
29|...##o##...
30|...##o##...
31|...##o##...
32|...##o##...
33|...##o##...
34|...##o##...
35|....#o#....
36|....###....
37|.....#.....
""", 24, 10)
    b[13:16, 28] = True
    return b


# ===========================================================================
# NEW: STATUS ICONS 8x8 (game.md §6.4: panel row 21, cols 30-31)
# ===========================================================================

STATUS_ICONS = [
    # (name, attr, ink hex, glyph) — ink hex must map to the attr ink
    ("FROZEN", 0x45, "#00FFFF", """
        ...#....
        .#.#.#..
        ..###...
        #######.
        ..###...
        .#.#.#..
        ...#....
        ........"""),
    ("ASLEEP", 0x41, "#0000FF", """
        #####...
        ...#....
        ..#.....
        .#......
        #####...
        ....####
        .....##.
        ....####"""),
    ("STUNNED", 0x07, "#D7D7D7", """
        ..#.....
        .###..#.
        ..#..###
        ......#.
        .#......
        ###..#..
        .#..###.
        .....#.."""),
    ("CONFUSED", 0x43, "#FF00FF", """
        ..####..
        .##..##.
        .....##.
        ....##..
        ...##...
        ........
        ...##...
        ........"""),
    ("FEAR", 0x42, "#FF3030", """
        .######.
        ########
        #..##..#
        #..##..#
        ###..###
        .######.
        .#.#.#..
        ........"""),
    ("POISON", 0x44, "#00FF00", """
        ...#....
        ...#....
        ..###...
        .#####..
        .#.###..
        #.#####.
        #######.
        .#####.."""),
    ("WEAK", 0x42, "#FF3030", """
        ..###...
        ..###...
        ..###...
        ..###...
        #######.
        .#####..
        ..###...
        ...#...."""),
]

# ===========================================================================
# Frame list (fragment order). (heading, caption, source, ink, origin)
#   source: concept grid name (IMPORTED) or a callable (NEW)
# ===========================================================================

W_INK = "#FFFFFF"            # canvas Knight
FRAMES = [
    ("KNIGHT", "THROW", "knight_throw", W_INK, "IMPORTED"),
    ("KNIGHT", "BOW", "knight_bow", W_INK, "IMPORTED"),
    ("KNIGHT", "WHIRL", "knight_whirl", W_INK, "IMPORTED"),
    ("KNIGHT", "POWER STRIKE", knight_powerstrike, W_INK, "NEW"),
    # §6.1 spells (projectile -> impact). Firebolt alternates yellow/red per
    # frame as drawn in concept R3 (§6.1 lists $46 for the flight).
    ("SPARK", "FLY 1", "spark_fly1", "#FF00FF", "IMPORTED"),
    ("SPARK", "FLY 2", "spark_fly2", "#FF00FF", "IMPORTED"),
    ("SPARK", "FIZZ 1", "spark_fizz1", "#FF00FF", "IMPORTED"),
    ("SPARK", "FIZZ 2", "spark_fizz2", "#FF00FF", "IMPORTED"),
    ("FIREBOLT", "FLY 1", "firebolt_fly1", "#FFFF00", "IMPORTED"),
    ("FIREBOLT", "FLY 2", "firebolt_fly2", "#FF3030", "IMPORTED"),
    ("FIREBOLT", "BURST 1", "firebolt_burst1", "#FFFF00", "IMPORTED"),
    ("FIREBOLT", "BURST 2", "firebolt_burst2", "#FF3030", "IMPORTED"),
    ("FROST", "FLY", "frost_fly", "#00FFFF", "IMPORTED"),
    ("FROST", "CRACK", "frost_crack", "#00FFFF", "IMPORTED"),
    ("DRAIN", "FLY 1", "drain_fly1", "#FF00FF", "IMPORTED"),
    ("DRAIN", "FLY 2", "drain_fly2", "#FF00FF", "IMPORTED"),
    ("DRAIN", "HIT", "drain_hit", "#FF00FF", "IMPORTED"),
    ("LIGHTNING", "FLY 1", "lightning_fly1", "#FFFFFF", "IMPORTED"),
    ("LIGHTNING", "FLY 2", "lightning_fly2", "#FFFFFF", "IMPORTED"),
    ("LIGHTNING", "FLASH", "lightning_flash", "#FFFFFF", "IMPORTED"),
    # §6.2 / §6.3 Warrior FX, §6.2 Mage melee impact
    ("POWER STRIKE", "BURST", "power_burst", "#FFFFFF", "IMPORTED"),
    ("DAGGER", "SPIN 1", "dagger_spin1", "#FFFFFF", "IMPORTED"),
    ("DAGGER", "SPIN 2", "dagger_spin2", "#FFFFFF", "IMPORTED"),
    ("ARROW", "FLY 1", "arrow_fly1", "#D7D7D7", "IMPORTED"),
    ("ARROW", "FLY 2", "arrow_fly2", "#D7D7D7", "IMPORTED"),
    ("ARROW", "HIT", "arrow_hit", "#D7D7D7", "IMPORTED"),
    ("STAFF", "BONK", "staff_bonk", "#FFFF00", "IMPORTED"),
]
# zx0 grouping for the report (one generator kind each; engineer may regroup)
GROUPS = {"warrior frames": ["KNIGHT"],
          "spell FX": ["SPARK", "FIREBOLT", "FROST", "DRAIN", "LIGHTNING"],
          "warrior/mage FX": ["POWER STRIKE", "DAGGER", "ARROW", "STAFF"]}
# §11.1 "lean set": one impact frame each for Spark and Firebolt
LEAN_DROP = {"spark_fizz2", "firebolt_burst2"}
NOTE_TEXT = {
    "KNIGHT": "THROW / BOW / WHIRL imported from concept R3 (pixels verbatim, ink = canvas "
              "Knight). POWER STRIKE is NEW (vertical chop on the SLASH body, ax 4).",
    "SPARK": "§6.1 Spark $43: fly 1/2 -> fizz 1/2 (lean set: fizz 1 only).",
    "FIREBOLT": "§6.1 Firebolt: frames alternate $46 / $42 as drawn (lean set: burst 1 only).",
    "FROST": "§6.1 Frost Shard $45. CRACK is 8x8 as drawn (§6.1 says 16x16; §11.1 bytes "
             "assume 8x8).",
    "DRAIN": "§6.1 Drain Life $43: fly 1/2 -> hit.",
    "LIGHTNING": "§6.1 Lightning $47: fly 1/2 (16 px/tick) -> flash.",
    "POWER STRIKE": "§6.2 power_burst $47 (impact on the struck body).",
    "DAGGER": "§6.3 dagger spin $47, 2 frames (designer 2026-10-06).",
    "ARROW": "§6.3 arrow $07: fly 1/2 -> hit.",
    "STAFF": "§6.2 Mage STAFF_SWING impact, $46.",
}

# ---------------------------------------------------------------------------
# outputs
# ---------------------------------------------------------------------------

BADGE = ('<p style="margin: 0; font-family: \'Press Start 2P\', monospace; font-size: 8px; '
         'color: {c};">{t}</p>')
BADGE_C = {"NEW": "#ffd84a", "IMPORTED": "#7d7b90"}
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


def artboard(bm, ink, caption, origin):
    h, w = bm.shape
    cap = html.escape(f"{caption} · {w}×{h}")
    return ('<div style="display: flex; flex-direction: column; gap: 6px; align-items: flex-start;">\n'
            f'{box(bm, ink)}\n'
            f'<div style="font-size: 11px; letter-spacing: 1px; color: #a9a7b8;">{cap}</div>\n'
            f'{BADGE.format(c=BADGE_C[origin], t=origin)}\n</div>')


def icon_board(bm, ink, label):
    return ('<div style="display: flex; flex-direction: column; gap: 6px; align-items: flex-start;">\n'
            f'{box(bm, ink)}\n'
            '<div style="font-family: \'Press Start 2P\', monospace; font-size: 10px; '
            f'color: #e8e6f0;">{label}</div>\n'
            f'{BADGE.format(c=BADGE_C["NEW"], t="NEW")}\n</div>')


def heading(name):
    return ('<div style="font-family: \'Press Start 2P\', monospace; font-size: 13px; '
            f'color: #e8e6f0; margin: 24px 0 12px;">{name}</div>')


def grid_text(name, heading_, caption, bm, solid, ink, ax, ay, origin):
    h, w = bm.shape
    src = ("NEW, drawn in tools/gen_d3_art.py" if origin == "NEW" else
           f"IMPORTED from assets/gfx/concept/grid/sprites/{name}.grid (pixels verbatim)")
    lines = ["# Tome of the Dead gfx text grid — DRAFT generated by tools/gen_d3_art.py "
             "(edit that); D3-3, not on the canvas yet.",
             f"# source: {src}",
             f"# name: {name}", f"# size: {w}x{h}", f"# character: {heading_}",
             f"# caption: {caption}", f"# ink: {ink}", f"# anchor: {ax} {ay}",
             "# legend: '#' ink, '+' opaque paper (mask 0, data 0), '.' transparent", "#"]
    lines += ["".join("#" if bm[y, x] else "+" if solid[y, x] else "." for x in range(w))
              for y in range(h)]
    return "\n".join(lines) + "\n"


def icons_grid_text():
    L = ["# Tome of the Dead status icons — DRAFT generated by tools/gen_d3_art.py (edit that);",
         "# game.md §6.4: 7 panel glyphs x 8 B (row 21, cols 30-31), one attr per cell,",
         "# NOT tile ids. gfx_convert --mode tile format (8 B + 1 attr each)."]
    for n, a, _ink, g in STATUS_ICONS:
        L.append(f"=== {n.lower()} ink:{GC.COL_NAME[a & 7]} paper:{GC.COL_NAME[(a >> 3) & 7]}"
                 + (" bright" if a & 0x40 else ""))
        L += ["".join("#" if v else "." for v in row) for row in glyph(g)]
        L.append("")
    return "\n".join(L)


def render(bm, solid, ink, scale=SCALE, paper=(52, 52, 84)):
    h, w = bm.shape
    rgb = tuple(int(ink[i:i + 2], 16) for i in (1, 3, 5))
    a = np.zeros((h, w, 3), np.uint8)
    a[:] = paper                        # transparent = slate
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


def zsize(data: bytes, tmp: str) -> int:
    return len(ZS.pack(data, tmp))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--png-dir")
    args = ap.parse_args()
    os.makedirs(GRID_DIR, exist_ok=True)
    built = []
    for hd, cap, srcx, ink, origin in FRAMES:
        bm = srcx() if callable(srcx) else concept(srcx)
        name = f"{S.CHAR_PREFIX[hd]}_{S.slug(cap)}"
        built.append(dict(hd=hd, cap=cap, name=name, bm=bm, ink=ink, origin=origin,
                          solid=S.make_mask(bm, S.OUTLINE, name)))
    # ---- fragment
    out = ["<!-- Tome of the Dead D3-3 DRAFT artboard (Stage 3D combat art). Generated by "
           "tools/gen_d3_art.py; paste as one artboard for review. NEW = drawn for D3-3, "
           "IMPORTED = concept R3/R4 grids (pixels verbatim, ink per game.md §6). "
           "Heroes and projectiles face right (the engine mirrors). -->",
           "<h2>D3 DRAFT</h2>"]
    for hd in dict.fromkeys(b["hd"] for b in built):
        out.append(heading(hd))
        out.append(NOTE.format(html.escape(NOTE_TEXT[hd])))
        out.append(ROW)
        out += [artboard(b["bm"], b["ink"], b["cap"], b["origin"]) for b in built if b["hd"] == hd]
        out.append("</div>")
    out.append("<h2>STATUS ICONS</h2>")
    out.append(NOTE.format("NEW. game.md §6.4 panel glyphs (row 21, cols 30-31), 8 B each, "
                           "one attr per cell: FROZEN $45, ASLEEP $41, STUNNED $07, "
                           "CONFUSED $43, FEAR $42, POISON $44, WEAK $42."))
    out.append(ROW)
    out += [icon_board(glyph(g), ink, n) for n, _a, ink, g in STATUS_ICONS]
    out.append("</div>")
    with open(FRAGMENT, "w") as f:
        f.write("\n".join(out) + "\n")
    # ---- re-parse check: the fragment reads back to the same bitmaps
    fr, _ = S.parse_sheet(FRAGMENT)
    sprites = [f for f in fr if f.kind == "sprite"]
    icons = [f for f in fr if f.kind == "tile"]
    assert len(sprites) == len(built) and len(icons) == len(STATUS_ICONS)
    for f, b in zip(sprites, built):
        assert (f.character, f.caption) == (b["hd"], b["cap"]) and np.array_equal(f.bitmap, b["bm"]), b["name"]
    for f, (n, _a, ink, g) in zip(icons, STATUS_ICONS):
        assert f.caption == n and f.ink_hex == ink and np.array_equal(f.bitmap, glyph(g)), n
    # ---- the real pipeline: canvas + fragment -> grids -> gfx_convert -> DEFB
    #      decode (clash, data + mask round-trip, attr) into a temp dir
    with tempfile.TemporaryDirectory() as tmp:
        sheet = os.path.join(tmp, "sheet.html")
        with open(sheet, "w") as f:
            f.write(open(S.SHEET).read() + "\n" + open(FRAGMENT).read())
        frames = S.import_sheet(sheet, os.path.join(tmp, "out"), "2026-10-06")
        by = {f.name: f for f in frames}
        for b in built:
            f = by[b["name"]]
            assert np.array_equal(f.solid, b["solid"]), b["name"]
            b["ax"], b["ay"] = f.anchor
            b["axl"] = f.extra["ax_l"]
            b["iou"] = f.extra.get("iou")
            b["raw"] = S.decode_asm(os.path.join(tmp, "out", b["name"] + ".asm"))[0]
            b["raw"] = bytes(x for r in b["raw"] for x in r)
        st = open(os.path.join(tmp, "out", "status_icons.asm")).read()
        print("pipeline: canvas + fragment imported, clash + round-trip OK "
              f"({len(frames)} frames/tiles); status_icons.asm {st.count('DEFB')} DEFB rows")
        # ---- sizes
        zdir = os.path.join(tmp, "z")
        os.makedirs(zdir)
        tot_r = tot_z = 0
        print(f"{'frame':22s} {'WxH':>6s} {'raw':>4s} {'zx0':>4s} ax ay axL origin")
        for b in built:
            h, w = b["bm"].shape
            assert len(b["raw"]) == h * w // 4, b["name"]
            b["z"] = zsize(b["raw"], zdir)
            tot_r += len(b["raw"])
            tot_z += b["z"]
            print(f"{b['name']:22s} {w:>2d}x{h:<3d} {len(b['raw']):>4d} {b['z']:>4d} "
                  f"{b['ax']:>2d} {b['ay']:>2d} {b['axl']:>3d} {b['origin']}")
        print(f"per-frame TOTAL {len(built)} frames raw {tot_r} zx0 {tot_z}")
        icon_raw = 8 * len(STATUS_ICONS)
        print(f"status icons: 7 x 8 B = {icon_raw} B raw (+7 attr B)")
        for lean in (False, True):
            gr = gz = 0
            for g, heads in GROUPS.items():
                fl = [(b["name"], b["raw"]) for b in built if b["hd"] in heads
                      and not (lean and b["name"] in LEAN_DROP)]
                parts = ZS.partition(fl, zdir)
                for i, (s0, k) in enumerate(parts):
                    raw = b"".join(d for _, d in fl[s0:s0 + k])
                    z = ZS.pack(raw, zdir)
                    ZS.roundtrip(z, raw, zdir, f"{g[:4]}{i}{int(lean)}")
                    gr += len(raw)
                    gz += len(z)
                    if not lean:
                        print(f"  block {g:16s} {[n for n, _ in fl[s0:s0 + k]]} "
                              f"raw {len(raw)} -> {len(z)}")
            print(f"blocks{' (lean: -' + ','.join(sorted(LEAN_DROP)) + ')' if lean else ''}: "
                  f"raw {gr} -> zx0 {gz} ({gr / gz:.2f}x), every block <= {ZS.SCRATCH_LEN} B, "
                  "dzx0 round-trip OK")
    # ---- grids
    for b in built:
        with open(os.path.join(GRID_DIR, b["name"] + ".grid"), "w") as f:
            f.write(grid_text(b["name"], b["hd"], b["cap"], b["bm"], b["solid"], b["ink"],
                              b["ax"], b["ay"], b["origin"]))
    with open(os.path.join(GRID_DIR, "status_icons.grid"), "w") as f:
        f.write(icons_grid_text())
    print(f"wrote {len(built)} grids + status_icons.grid -> {os.path.relpath(GRID_DIR, REPO)}, "
          f"{os.path.relpath(FRAGMENT, REPO)}")
    # ---- previews
    if args.png_dir:
        d = args.png_dir
        os.makedirs(d, exist_ok=True)
        for b in built:
            render(b["bm"], b["solid"], b["ink"]).save(os.path.join(d, b["name"] + ".png"))
        kn = [render(CANVAS[n], S.make_mask(CANVAS[n], True), W_INK)
              for n in ("knight_idle1", "knight_windup", "knight_slash", "knight_follow")]
        kn += [render(b["bm"], b["solid"], b["ink"]) for b in built if b["hd"] == "KNIGHT"]
        hstrip(kn).save(os.path.join(d, "knight_compare.png"))
        fx = [render(b["bm"], b["solid"], b["ink"], scale=8) for b in built if b["hd"] != "KNIGHT"]
        hstrip(fx).save(os.path.join(d, "fx_strip.png"))
        ic = [render(glyph(g), np.ones((8, 8), bool), ink, scale=12) for _n, _a, ink, g in STATUS_ICONS]
        hstrip(ic).save(os.path.join(d, "status_icons.png"))
        print(f"previews -> {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
