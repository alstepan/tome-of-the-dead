#!/usr/bin/env python3
"""gfx_convert.py — WazHack/ZX asset converter.

Turns a source image (concept art / draft raster) OR a git-diffable text pixel
grid into ZX Spectrum attribute-legal `DEFB` byte tables under assets/gfx/.

Two modes:

  sprite  (default)  16xH masked sprite for the side-view renderer.
                     Emits the EXACT data contract from
                     docs/design/foundations.md F8:
                       H rows of [c0_mask,c0_data, c1_mask,c1_data, c2_mask,c2_data]
                       (MSB = leftmost pixel, mask bit 1 = transparent,
                        third column padded fully transparent: mask $FF/data $00)
                       + 1 colour-descriptor byte ATTR_SPRITE.
                     For 16x24 that is 24*6 + 1 = 145 bytes.
                     Composite rule the renderer uses:
                       screen = (screen AND mask) OR data

  sprite --layout native   (canvas sprite set, driven by tools/svg_sprites.py)
                     W in 8/16/24/32/40: W/8 [mask,data] columns, NO pad column,
                     from a 3-state .grid ('#' ink, '+' opaque paper, '.'
                     transparent) so the mask can be the filled silhouette +
                     outline. Adds <name>_w/_h/_cols (+ _ax/_ay anchor) EQUs.
                     Legacy mode output is unchanged byte-for-byte.

  tile               One or more 8x8 background tiles. Emits 8 bitmap bytes per
                     tile (MSB=left) plus a parallel attribute-byte table.
                     Clash-legal by construction (one paper+ink per cell).

The committed artefacts are the .asm byte table AND the .grid text source — never
raw AI raster. Concept PNGs are kept only for re-derivation.

Validation (must pass or the tool exits non-zero):
  * clash check  — sprite: descriptor is one paper+ink AND its PAPER bits equal
                   the band paper (the design's hard constraint, sec 1.7).
                   tile: each tile resolves to one paper+ink (always true here as
                   we author 1-bit grids + explicit ink/paper).
  * round-trip   — decode the emitted bytes back to the foreground/mask grid and
                   confirm it matches the quantised target. Catches packing bugs.

Usage examples:
  # image -> derive grid + asm
  python3 tools/gfx_convert.py --mode sprite --in concept.png --name hero \
      --width 16 --height 24 --ink yellow --paper black --bright \
      --band-paper black --out assets/gfx/sprites/hero.asm --grid assets/gfx/sprites/hero.grid

  # hand-tuned text grid -> asm (deterministic, the durable path)
  python3 tools/gfx_convert.py --mode sprite --in assets/gfx/sprites/hero.grid \
      --name hero --out assets/gfx/sprites/hero.asm

  # multi-tile text grid -> asm
  python3 tools/gfx_convert.py --mode tile --in assets/gfx/tiles.grid \
      --name bgtiles --out assets/gfx/tiles.asm
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date

import numpy as np

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

# ---------------------------------------------------------------------------
# Spectrum palette / attribute helpers
# ---------------------------------------------------------------------------

COLOURS = {
    "black": 0, "blue": 1, "red": 2, "magenta": 3,
    "green": 4, "cyan": 5, "yellow": 6, "white": 7,
}
COL_NAME = {v: k for k, v in COLOURS.items()}

# Approximate RGB for round-trip PNGs (normal vs bright intensity).
_NORMAL = 0xCD
_BRIGHT = 0xFF


def colour_rgb(idx: int, bright: bool) -> tuple[int, int, int]:
    hi = _BRIGHT if bright else _NORMAL
    b = hi if (idx & 1) else 0
    r = hi if (idx & 2) else 0
    g = hi if (idx & 4) else 0
    return (r, g, b)


def attr_byte(ink: int, paper: int, bright: bool = False, flash: bool = False) -> int:
    return (ink & 7) | ((paper & 7) << 3) | (0x40 if bright else 0) | (0x80 if flash else 0)


def attr_paper(a: int) -> int:
    return (a >> 3) & 7


def attr_ink(a: int) -> int:
    return a & 7


# Grid glyph alphabet (tolerant, so hand-editing is forgiving).
INK_CHARS = set("#X*@")
BLANK_CHARS = set("._ ")
# 3-state grids (svg_sprites.py): '+' = OPAQUE paper — not drawn (data 0) but
# mask 0, so it punches the background out (filled interior / 1-px outline).
# Legacy 2-state grids never contain it, so their mask stays ~data.
OPAQUE_CHARS = set("+")


# ---------------------------------------------------------------------------
# Grid <-> foreground matrix
# ---------------------------------------------------------------------------

def parse_grid_text(text: str, width: int | None, height: int | None):
    """Parse a .grid text file into a boolean foreground matrix (H x W).

    A "grid line" is a line whose stripped content is composed solely of the
    ink/blank alphabet and (if width is known) is exactly `width` chars wide.
    Everything else (comment lines, headers, blank-out-of-band) is ignored.
    Returns (matrix, width, height).
    """
    fg, _solid, w, h = parse_grid_text_mask(text, width, height)
    return fg, w, h


def parse_grid_text_mask(text: str, width: int | None, height: int | None):
    """As parse_grid_text, but also returns the OPAQUE matrix (mask 0 = solid).

    solid = ink | '+' cells. For a legacy 2-state grid solid == fg, so the mask
    is exactly ~data (byte-identical to the historical behaviour).
    Returns (fg, solid, width, height).
    """
    alphabet = INK_CHARS | BLANK_CHARS | OPAQUE_CHARS
    rows: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#") and not set(stripped) <= alphabet:
            # comment / header line
            continue
        cells = stripped
        if not set(cells) <= alphabet:
            continue
        if width is not None and len(cells) != width:
            continue
        rows.append(cells)
    if not rows:
        raise ValueError("no grid rows parsed; check legend and width")
    # width unknown: the dominant row length (a lone "#" comment line would
    # otherwise masquerade as a 1-px-wide first row)
    w = width if width is not None else max(set(map(len, rows)),
                                            key=lambda n: sum(len(r) == n for r in rows))
    # keep only rows of the dominant width
    rows = [r for r in rows if len(r) == w]
    if height is not None:
        if len(rows) != height:
            raise ValueError(f"expected {height} grid rows, parsed {len(rows)}")
    fg = np.array([[c in INK_CHARS for c in r] for r in rows], dtype=bool)
    solid = np.array([[c in INK_CHARS or c in OPAQUE_CHARS for c in r] for r in rows],
                     dtype=bool)
    return fg, solid, w, fg.shape[0]


def grid_to_text(mat: np.ndarray, name: str, legend: str) -> str:
    h, w = mat.shape
    out = [
        "# WazHack/ZX gfx text grid — durable, git-diffable source of truth.",
        f"# name: {name}",
        f"# size: {w}x{h}",
        f"# legend: {legend}",
        "#",
    ]
    for row in mat:
        out.append("".join("#" if c else "." for c in row))
    return "\n".join(out) + "\n"


def image_to_grid(path: str, width: int, height: int,
                  threshold: int | None, invert: bool) -> np.ndarray:
    """Reduce/crop an image to a width x height boolean foreground matrix.

    Background is detected from the border pixels; the foreground class is the
    non-border luminance class. `--threshold`/`--invert` override the heuristic.
    """
    if Image is None:
        raise RuntimeError("Pillow not available")
    img = Image.open(path).convert("L")
    # centre-crop to target aspect, then resize.
    tw, th = width, height
    iw, ih = img.size
    target_ar = tw / th
    src_ar = iw / ih
    if src_ar > target_ar:  # too wide -> crop width
        new_w = int(round(ih * target_ar))
        left = (iw - new_w) // 2
        img = img.crop((left, 0, left + new_w, ih))
    else:  # too tall -> crop height
        new_h = int(round(iw / target_ar))
        top = (ih - new_h) // 2
        img = img.crop((0, top, iw, top + new_h))
    img = img.resize((tw, th), Image.LANCZOS)
    arr = np.asarray(img, dtype=np.float64)

    if threshold is None:
        threshold = float(arr.mean())
    bright_mask = arr > threshold  # True = bright pixel

    # Decide which class is background by majority vote on the border ring.
    border = np.ones((th, tw), dtype=bool)
    border[1:-1, 1:-1] = False
    border_bright_frac = bright_mask[border].mean() if border.any() else 0.5
    bg_is_bright = border_bright_frac >= 0.5
    # foreground = pixels NOT in the background class
    fg = (~bright_mask) if bg_is_bright else bright_mask
    if invert:
        fg = ~fg
    return fg.astype(bool)


# ---------------------------------------------------------------------------
# Packing
# ---------------------------------------------------------------------------

def pack_byte_msb_left(bits: list[bool]) -> int:
    """8 booleans -> byte, bits[0] is the MSB (leftmost pixel)."""
    b = 0
    for i, on in enumerate(bits):
        if on:
            b |= 1 << (7 - i)
    return b


NATIVE_WIDTHS = (8, 16, 24, 32, 40)


def pack_sprite(fg: np.ndarray, solid: np.ndarray | None = None,
                layout: str = "legacy"):
    """Foreground matrix (H x W) -> row byte lists (descriptor-less).

    solid  : optional opaque matrix (mask 0 where True). None -> mask = ~data.
    layout : "legacy" (policy below) or "native": W/8 data columns, never a pad
             column, W in NATIVE_WIDTHS (the canvas sprite set, svg_sprites.py).

    Width policy (matches docs/design/foundations.md F8):
      * W==16 : 2 real data columns + 1 pad column (fully transparent),
                i.e. 6 bytes/row — the legacy 16xH sprite/cat contract.
      * W==32 : 4 real data columns, NO pad column (the engine boot-gen adds
                the 5th shifted column), i.e. 8 bytes/row — the 32x48 hero
                contract (48 rows of [mask,data]x4 = 384 bytes).

    Each row: [c0_mask,c0_data, c1_mask,c1_data, ...] MSB=leftmost pixel,
    mask bit 1 = transparent (background), data bit = sprite pixel.
    """
    h, w = fg.shape
    if layout == "native":
        if w not in NATIVE_WIDTHS:
            raise ValueError(f"native sprite width must be one of {NATIVE_WIDTHS}, got {w}")
        pad = False
    else:
        if w not in (16, 32):
            raise ValueError(f"sprite must be 16 or 32 px wide, got {w}")
        pad = (w == 16)       # 16px keeps the legacy transparent pad column
    if solid is not None and not np.array_equal(solid | fg, solid):
        raise ValueError("solid matrix must cover every ink pixel")
    ncols = w // 8            # real data columns
    rows = []
    for r in range(h):
        row_bytes = []
        for col in range(ncols):
            seg = list(fg[r, col * 8:col * 8 + 8])
            data = pack_byte_msb_left(seg)
            if solid is None:
                mask = (~data) & 0xFF  # transparent everywhere the sprite isn't
            else:
                mask = (~pack_byte_msb_left(list(solid[r, col * 8:col * 8 + 8]))) & 0xFF
            row_bytes.extend([mask, data])
        if pad:
            row_bytes.extend([0xFF, 0x00])
        rows.append(row_bytes)
    return rows


def unpack_sprite(rows, width: int = 16, layout: str = "legacy") -> np.ndarray:
    """Decode packed rows back to a foreground matrix (round-trip)."""
    return unpack_sprite_mask(rows, width, layout)[0]


def unpack_sprite_mask(rows, width: int = 16, layout: str = "legacy"):
    """Decode packed rows back to (foreground, solid) matrices (round-trip)."""
    h = len(rows)
    ncols = width // 8
    pad = (width == 16) and layout != "native"
    expect = ncols * 2 + (2 if pad else 0)
    fg = np.zeros((h, width), dtype=bool)
    solid = np.zeros((h, width), dtype=bool)
    for r, rb in enumerate(rows):
        if len(rb) != expect:
            raise ValueError(f"row {r} must have {expect} bytes, got {len(rb)}")
        if pad:
            c_mask, c_data = rb[ncols * 2], rb[ncols * 2 + 1]
            if c_mask != 0xFF or c_data != 0x00:
                raise ValueError(f"row {r}: pad column not fully transparent")
        for col in range(ncols):
            mask, data = rb[col * 2], rb[col * 2 + 1]
            if (mask & data) != 0:
                raise ValueError(f"row {r} col {col}: data set under transparent mask")
            for i in range(8):
                if data & (1 << (7 - i)):
                    fg[r, col * 8 + i] = True
                if not mask & (1 << (7 - i)):
                    solid[r, col * 8 + i] = True
    return fg, solid


# ---------------------------------------------------------------------------
# ASM emission
# ---------------------------------------------------------------------------

def hexbytes(bs) -> str:
    return ",".join(f"${b:02X}" for b in bs)


def emit_sprite_asm(name, rows, descriptor, src, width, height,
                    ink, paper, bright, band_paper, layout_mode="legacy",
                    notes=None, anchor=None, gen_date=None) -> str:
    flto = lambda i: COL_NAME[i]
    native = layout_mode == "native"
    L = []
    L.append(f"; ============================================================================")
    L.append(f"; {name} — side-view masked sprite (WazHack/ZX)")
    L.append(f"; Generated by tools/gfx_convert.py on {gen_date or date.today().isoformat()}")
    L.append(f"; Source        : {src}")
    for n in notes or []:
        L.append(f";                 {n}")
    ncols = width // 8
    pad = width == 16 and not native
    bpr = ncols * 2 + (2 if pad else 0)  # bytes per row
    layout = ", ".join(f"c{c}_mask,c{c}_data" for c in range(ncols))
    if native:
        dims = (f"{width}x{height} px = {ncols} data cols x {height} rows, no pad col "
                f"(engine pre-shift spills into col {ncols})")
    elif width == 16:
        dims = f"{width}x{height} px = 2 data cols + 1 pad col x {height} rows"
        layout += ", c{}_mask,c{}_data(pad $FF/$00)".format(ncols, ncols)
    else:
        dims = f"{width}x{height} px = 4 data cols x {height} rows (engine boot-gens 5th shifted col)"
    L.append(f"; Dimensions    : {dims}")
    L.append(f"; Layout/row    : {layout}  (MSB=left)")
    L.append(f"; Mask polarity : bit 1 = transparent (keep background)")
    if native:
        L.append(f"; Mask shape    : filled silhouette (+ outline if any) — enclosed paper is opaque")
    L.append(f"; Composite     : screen = (screen AND mask) OR data")
    L.append(f"; Bytes         : {height}*{bpr} + 1 descriptor = {height*bpr+1}")
    L.append(f"; Colour        : ink={flto(ink)} paper={flto(paper)} bright={int(bright)}"
             f"  -> ATTR_SPRITE=${descriptor:02X}")
    L.append(f"; Band paper    : {flto(band_paper)} (descriptor PAPER must match — verified)")
    L.append(f"; Intended use  : engine boot-gen of 8 pre-shifts; masked blit at pixel X")
    if anchor is not None:
        L.append(f"; Anchor        : ax={anchor[0]} ay={anchor[1]}  draw_x = body_x - ax, "
                 f"draw_y = body_y - ay (right-facing; body_x/y = reference frame origin)")
    L.append(f"; ============================================================================")
    L.append(f"{name}:")
    for r, rb in enumerate(rows):
        L.append(f"        DEFB {hexbytes(rb)}    ; row {r:2d}")
    L.append(f"{name}_attr:")
    L.append(f"        DEFB ${descriptor:02X}                                  ; ATTR_SPRITE")
    L.append(f"{name}_len  EQU $ - {name}")
    if native:
        L.append(f"{name}_w    EQU {width}                ; px")
        L.append(f"{name}_h    EQU {height}                ; px (rows)")
        L.append(f"{name}_cols EQU {ncols}                 ; byte columns (x2 bytes each)")
    if anchor is not None:
        L.append(f"{name}_ax   EQU {anchor[0]}                 ; x-anchor, px left of body origin")
        L.append(f"{name}_ay   EQU {anchor[1]}                 ; y-anchor, px above body origin")
    L.append("")
    return "\n".join(L)


def emit_tiles_asm(name, tiles, src, notes=None, gen_date=None, use=None) -> str:
    """tiles: list of dicts {name,bitmap(8 bytes),attr,ink,paper,bright}."""
    L = []
    L.append(f"; ============================================================================")
    L.append(f"; {name} — 8x8 background tileset (WazHack/ZX side-view scene)")
    L.append(f"; Generated by tools/gfx_convert.py on {gen_date or date.today().isoformat()}")
    L.append(f"; Source        : {src}")
    for n in notes or []:
        L.append(f";                 {n}")
    L.append(f"; Layout        : {len(tiles)} tiles x 8 bitmap bytes (MSB=left), row-major")
    L.append(f";                 parallel attr table, one attribute byte per tile")
    L.append(f"; Clash         : each tile is one paper+ink — clash-legal by construction")
    L.append(f"; Intended use  : {use or 'draw_cell background (floor/pillar/doorway/blank)'}")
    L.append(f"; ============================================================================")
    L.append(f"{name}:")
    for t in tiles:
        L.append(f"{name}_{t['name']}:")
        L.append(f"        DEFB {hexbytes(t['bitmap'])}    ; {t['name']}")
    L.append("")
    L.append(f"{name}_attr:")
    for t in tiles:
        cb = COL_NAME[t['ink']]; cp = COL_NAME[t['paper']]
        L.append(f"        DEFB ${t['attr']:02X}    ; {t['name']:8s} ink={cb} paper={cp} bright={int(t['bright'])}")
    L.append(f"{name}_count EQU {len(tiles)}")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Multi-tile grid parsing
# ---------------------------------------------------------------------------

def parse_tile_file(text: str):
    """Parse a multi-tile grid file.

    Each tile begins with a header line:
        === <tilename> ink:<colour> paper:<colour> [bright]
    followed by exactly 8 grid lines of 8 chars.
    """
    tiles = []
    cur = None
    rows: list[list[bool]] = []

    def flush():
        nonlocal cur, rows
        if cur is None:
            return
        if len(rows) != 8:
            raise ValueError(f"tile {cur['name']}: expected 8 rows, got {len(rows)}")
        bitmap = [pack_byte_msb_left(r) for r in rows]
        cur['bitmap'] = bitmap
        cur['attr'] = attr_byte(cur['ink'], cur['paper'], cur['bright'])
        tiles.append(cur)
        cur = None
        rows = []

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("==="):
            flush()
            parts = line.strip("= ").split()
            tname = parts[0]
            ink = paper = 0
            bright = False
            for p in parts[1:]:
                if p.startswith("ink:"):
                    ink = COLOURS[p[4:]]
                elif p.startswith("paper:"):
                    paper = COLOURS[p[6:]]
                elif p == "bright":
                    bright = True
            cur = {"name": tname, "ink": ink, "paper": paper, "bright": bright}
            rows = []
            continue
        # A valid pixel row must be matched BEFORE comment detection: a fully
        # inked row ("########") legitimately starts with '#', which must not be
        # mistaken for a comment line.
        if len(line) == 8 and set(line) <= (INK_CHARS | BLANK_CHARS):
            rows.append([c in INK_CHARS for c in line])
            continue
        if not line or line.startswith("#"):
            continue
    flush()
    if not tiles:
        raise ValueError("no tiles parsed")
    return tiles


# ---------------------------------------------------------------------------
# Render-back PNG (for eyeballing / assess)
# ---------------------------------------------------------------------------

def render_sprite_png(fg: np.ndarray, path: str, ink, paper, bright, scale=8):
    if Image is None:
        return
    h, w = fg.shape
    ink_rgb = colour_rgb(ink, bright)
    paper_rgb = colour_rgb(paper, bright)
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    rgb[fg] = ink_rgb
    rgb[~fg] = paper_rgb
    img = Image.fromarray(rgb, "RGB").resize((w * scale, h * scale), Image.NEAREST)
    img.save(path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_sprite(args) -> int:
    src_in = args.infile
    is_grid = src_in.lower().endswith(".grid") or src_in.lower().endswith(".txt")

    native = args.layout == "native"
    solid = None
    if is_grid:
        with open(src_in) as f:
            text = f.read()
        if native:
            # native reads the grid's own width (8..40) and the 3-state mask
            fg, solid, w, h = parse_grid_text_mask(text, None, None)
        else:
            fg, w, h = parse_grid_text(text, args.width, args.height)
    else:
        if native:
            print("ERROR: --layout native requires a .grid input", file=sys.stderr)
            return 2
        fg = image_to_grid(src_in, args.width, args.height, args.threshold, args.invert)
        w, h = args.width, args.height

    allowed = NATIVE_WIDTHS if native else (16, 32)
    if w not in allowed:
        print(f"ERROR: sprite width must be one of {allowed}, got {w}", file=sys.stderr)
        return 2

    # durable grid source (always (re)written so image-derived grids are committed)
    if args.grid:
        legend = "# = ink (drawn), . = transparent (shows background)"
        with open(args.grid, "w") as f:
            f.write(grid_to_text(fg, args.name, legend))
        print(f"grid : {args.grid}")

    rows = pack_sprite(fg, solid, args.layout)

    ink = COLOURS[args.ink]
    paper = COLOURS[args.paper]
    band_paper = COLOURS[args.band_paper]
    descriptor = attr_byte(ink, paper, args.bright, args.flash)

    # ---- validation: clash / descriptor legality ----
    errs = []
    if attr_paper(descriptor) != band_paper:
        errs.append(f"descriptor PAPER={COL_NAME[attr_paper(descriptor)]} "
                    f"!= band paper={args.band_paper} (design sec 1.7 hard constraint)")
    if attr_ink(descriptor) == attr_paper(descriptor):
        errs.append("descriptor ink == paper (sprite would be invisible)")

    # ---- validation: round-trip ----
    decoded, dsolid = unpack_sprite_mask(rows, w, args.layout)
    if not np.array_equal(decoded, fg):
        errs.append("round-trip mismatch: decoded bytes != quantised target")
    exp_solid = fg if solid is None else solid
    if not np.array_equal(dsolid, exp_solid):
        errs.append("round-trip mismatch: decoded mask != source mask")

    if errs:
        print("VALIDATION FAILED:", file=sys.stderr)
        for e in errs:
            print("  - " + e, file=sys.stderr)
        return 1

    anchor = None
    if args.anchor_x is not None or args.anchor_y is not None:
        anchor = (args.anchor_x or 0, args.anchor_y or 0)
    src_label = src_in if args.src_path else os.path.basename(src_in)
    asm = emit_sprite_asm(args.name, rows, descriptor, src_label,
                          w, h, ink, paper, args.bright, band_paper,
                          layout_mode=args.layout, notes=args.note,
                          anchor=anchor, gen_date=args.date)
    bpr = len(rows[0])
    with open(args.out, "w") as f:
        f.write(asm)
    print(f"asm  : {args.out}  ({h*bpr+1} bytes: {h}*{bpr} + 1 descriptor)")
    print(f"clash: OK (descriptor ${descriptor:02X}, paper matches band)")
    print(f"round-trip: OK")

    if args.png:
        render_sprite_png(fg, args.png, ink, paper, args.bright)
        print(f"png  : {args.png}")

    return 0


def run_tile(args) -> int:
    with open(args.infile) as f:
        tiles = parse_tile_file(f.read())
    # round-trip each tile bitmap
    for t in tiles:
        for by in t['bitmap']:
            if not (0 <= by <= 255):
                print(f"ERROR: tile {t['name']} bad byte", file=sys.stderr)
                return 1
    src_label = args.infile if args.src_path else os.path.basename(args.infile)
    asm = emit_tiles_asm(args.name, tiles, src_label, notes=args.note, gen_date=args.date,
                         use=args.use)
    with open(args.out, "w") as f:
        f.write(asm)
    names = ", ".join(t['name'] for t in tiles)
    print(f"asm  : {args.out}  ({len(tiles)} tiles: {names})")
    print(f"clash: OK (each tile one paper+ink)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="WazHack/ZX gfx converter")
    p.add_argument("--mode", choices=["sprite", "tile"], default="sprite")
    p.add_argument("--in", dest="infile", required=True, help="PNG or .grid/.txt input")
    p.add_argument("--name", default="sprite", help="asm label base")
    p.add_argument("--out", required=True, help="output .asm path")
    p.add_argument("--grid", help="(sprite) write derived/used text grid here")
    p.add_argument("--png", help="(sprite) write a render-back PNG here")
    p.add_argument("--width", type=int, default=16)
    p.add_argument("--height", type=int, default=24)
    p.add_argument("--ink", default="yellow", choices=list(COLOURS))
    p.add_argument("--paper", default="black", choices=list(COLOURS))
    p.add_argument("--band-paper", dest="band_paper", default="black", choices=list(COLOURS))
    p.add_argument("--bright", action="store_true")
    p.add_argument("--flash", action="store_true")
    p.add_argument("--threshold", type=int, default=None,
                   help="(image) luminance threshold; default = mean")
    p.add_argument("--invert", action="store_true", help="(image) flip fg/bg choice")
    p.add_argument("--layout", choices=["legacy", "native"], default="legacy",
                   help="(sprite) legacy: 16w+pad col / 32w; native: W/8 cols, no pad, "
                        "W in 8..40, 3-state grid ('+' = opaque paper)")
    p.add_argument("--anchor-x", dest="anchor_x", type=int, default=None,
                   help="(sprite) x-anchor EQU (px left of body origin)")
    p.add_argument("--anchor-y", dest="anchor_y", type=int, default=None,
                   help="(sprite) y-anchor EQU (px above body origin)")
    p.add_argument("--note", action="append", default=None,
                   help="extra header line under Source (repeatable)")
    p.add_argument("--use", default=None, help="(tile) 'Intended use' header text")
    p.add_argument("--date", default=None, help="header date override (reproducible output)")
    p.add_argument("--src-path", dest="src_path", action="store_true",
                   help="record the input path as given, not its basename")
    args = p.parse_args(argv)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    if args.mode == "sprite":
        return run_sprite(args)
    return run_tile(args)


if __name__ == "__main__":
    sys.exit(main())
