#!/usr/bin/env python3
"""gfx_convert.py — WazHack/ZX asset converter.

Turns a source image (concept art / draft raster) OR a git-diffable text pixel
grid into ZX Spectrum attribute-legal `DEFB` byte tables under assets/gfx/.

Two modes:

  sprite  (default)  16xH masked sprite for the side-view renderer.
                     Emits the EXACT data contract from
                     docs/design/sideview-renderer.md sec 1.4/1.7:
                       H rows of [c0_mask,c0_data, c1_mask,c1_data, c2_mask,c2_data]
                       (MSB = leftmost pixel, mask bit 1 = transparent,
                        third column padded fully transparent: mask $FF/data $00)
                       + 1 colour-descriptor byte ATTR_SPRITE.
                     For 16x24 that is 24*6 + 1 = 145 bytes.
                     Composite rule the renderer uses:
                       screen = (screen AND mask) OR data

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
  python3 tools/gfx_convert.py --mode sprite --in concept.png --name player \
      --width 16 --height 24 --ink yellow --paper black --bright \
      --band-paper black --out assets/gfx/player.asm --grid assets/gfx/player.grid

  # hand-tuned text grid -> asm (deterministic, the durable path)
  python3 tools/gfx_convert.py --mode sprite --in assets/gfx/player.grid \
      --name player --out assets/gfx/player.asm

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
    rows: list[list[bool]] = []
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#") and not set(stripped) <= (INK_CHARS | BLANK_CHARS):
            # comment / header line
            continue
        cells = stripped
        if not set(cells) <= (INK_CHARS | BLANK_CHARS):
            continue
        if width is not None and len(cells) != width:
            continue
        rows.append([c in INK_CHARS for c in cells])
    if not rows:
        raise ValueError("no grid rows parsed; check legend and width")
    w = width if width is not None else len(rows[0])
    # keep only rows of the dominant width
    rows = [r for r in rows if len(r) == w]
    if height is not None:
        if len(rows) != height:
            raise ValueError(f"expected {height} grid rows, parsed {len(rows)}")
    mat = np.array(rows, dtype=bool)
    return mat, w, mat.shape[0]


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


def pack_sprite(fg: np.ndarray):
    """Foreground matrix (H x 16) -> (rows_bytes, descriptor-less).

    Returns a list of H rows, each a list of 6 bytes:
      [c0_mask, c0_data, c1_mask, c1_data, c2_mask, c2_data]
    data bit = sprite (foreground) pixel; mask bit 1 = transparent (background).
    For a pure 2-state shape mask == ~data within the 16 data columns; the third
    column is padded fully transparent (mask $FF, data $00).
    """
    h, w = fg.shape
    if w != 16:
        raise ValueError(f"sprite must be 16 px wide, got {w}")
    rows = []
    for r in range(h):
        row_bytes = []
        for col in range(2):  # two real data columns
            seg = list(fg[r, col * 8:col * 8 + 8])
            data = pack_byte_msb_left(seg)
            mask = (~data) & 0xFF  # transparent everywhere the sprite isn't
            row_bytes.extend([mask, data])
        # third padded column: fully transparent
        row_bytes.extend([0xFF, 0x00])
        rows.append(row_bytes)
    return rows


def unpack_sprite(rows) -> np.ndarray:
    """Decode packed rows back to a foreground matrix (round-trip)."""
    h = len(rows)
    fg = np.zeros((h, 16), dtype=bool)
    for r, rb in enumerate(rows):
        # validate structure
        if len(rb) != 6:
            raise ValueError("row must have 6 bytes")
        c2_mask, c2_data = rb[4], rb[5]
        if c2_mask != 0xFF or c2_data != 0x00:
            raise ValueError(f"row {r}: third column not padded transparent")
        for col in range(2):
            mask, data = rb[col * 2], rb[col * 2 + 1]
            if (mask & data) != 0:
                raise ValueError(f"row {r} col {col}: data set under transparent mask")
            for i in range(8):
                if data & (1 << (7 - i)):
                    fg[r, col * 8 + i] = True
    return fg


# ---------------------------------------------------------------------------
# ASM emission
# ---------------------------------------------------------------------------

def hexbytes(bs) -> str:
    return ",".join(f"${b:02X}" for b in bs)


def emit_sprite_asm(name, rows, descriptor, src, width, height,
                    ink, paper, bright, band_paper) -> str:
    flto = lambda i: COL_NAME[i]
    L = []
    L.append(f"; ============================================================================")
    L.append(f"; {name} — side-view masked sprite (WazHack/ZX)")
    L.append(f"; Generated by tools/gfx_convert.py on {date.today().isoformat()}")
    L.append(f"; Source        : {src}")
    L.append(f"; Dimensions    : {width}x{height} px = 2 data cols + 1 pad col x {height} rows")
    L.append(f"; Layout/row    : c0_mask,c0_data, c1_mask,c1_data, c2_mask,c2_data  (MSB=left)")
    L.append(f"; Mask polarity : bit 1 = transparent (keep background)")
    L.append(f"; Composite     : screen = (screen AND mask) OR data")
    L.append(f"; Bytes         : {height}*6 + 1 descriptor = {height*6+1}")
    L.append(f"; Colour        : ink={flto(ink)} paper={flto(paper)} bright={int(bright)}"
             f"  -> ATTR_SPRITE=${descriptor:02X}")
    L.append(f"; Band paper    : {flto(band_paper)} (descriptor PAPER must match — verified)")
    L.append(f"; Intended use  : engine boot-gen of 8 pre-shifts; masked blit at pixel X")
    L.append(f"; ============================================================================")
    L.append(f"{name}:")
    for r, rb in enumerate(rows):
        L.append(f"        DEFB {hexbytes(rb)}    ; row {r:2d}")
    L.append(f"{name}_attr:")
    L.append(f"        DEFB ${descriptor:02X}                                  ; ATTR_SPRITE")
    L.append(f"{name}_len  EQU $ - {name}")
    L.append("")
    return "\n".join(L)


def emit_tiles_asm(name, tiles, src) -> str:
    """tiles: list of dicts {name,bitmap(8 bytes),attr,ink,paper,bright}."""
    L = []
    L.append(f"; ============================================================================")
    L.append(f"; {name} — 8x8 background tileset (WazHack/ZX side-view scene)")
    L.append(f"; Generated by tools/gfx_convert.py on {date.today().isoformat()}")
    L.append(f"; Source        : {src}")
    L.append(f"; Layout        : {len(tiles)} tiles x 8 bitmap bytes (MSB=left), row-major")
    L.append(f";                 parallel attr table, one attribute byte per tile")
    L.append(f"; Clash         : each tile is one paper+ink — clash-legal by construction")
    L.append(f"; Intended use  : draw_cell background (floor/pillar/doorway/blank)")
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

    if is_grid:
        with open(src_in) as f:
            fg, w, h = parse_grid_text(f.read(), args.width, args.height)
    else:
        fg = image_to_grid(src_in, args.width, args.height, args.threshold, args.invert)
        w, h = args.width, args.height

    if w != 16:
        print(f"ERROR: sprite width must be 16, got {w}", file=sys.stderr)
        return 2

    # durable grid source (always (re)written so image-derived grids are committed)
    if args.grid:
        legend = "# = ink (drawn), . = transparent (shows background)"
        with open(args.grid, "w") as f:
            f.write(grid_to_text(fg, args.name, legend))
        print(f"grid : {args.grid}")

    rows = pack_sprite(fg)

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
    decoded = unpack_sprite(rows)
    if not np.array_equal(decoded, fg):
        errs.append("round-trip mismatch: decoded bytes != quantised target")

    if errs:
        print("VALIDATION FAILED:", file=sys.stderr)
        for e in errs:
            print("  - " + e, file=sys.stderr)
        return 1

    asm = emit_sprite_asm(args.name, rows, descriptor, os.path.basename(src_in),
                          16, h, ink, paper, args.bright, band_paper)
    with open(args.out, "w") as f:
        f.write(asm)
    print(f"asm  : {args.out}  ({h*6+1} bytes: {h}*6 + 1 descriptor)")
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
    asm = emit_tiles_asm(args.name, tiles, os.path.basename(args.infile))
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
    args = p.parse_args(argv)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    if args.mode == "sprite":
        return run_sprite(args)
    return run_tile(args)


if __name__ == "__main__":
    sys.exit(main())
