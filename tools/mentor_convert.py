#!/usr/bin/env python3
"""mentor_convert.py — artist .grid frames -> mentor sprite data (assets/gfx/mentor/).

Input : 24x48 2-state grids (ink '#', paper '.', ink meta '#00D7D7'), read with
        svg_sprites.read_grid exactly as tools/aldous_frames.py does.
Output: a generated Z80 asm file, one label per image, cell-major:
          image = 6 cell rows (r0..r5) x 3 cell cols (c0..c2), row-major;
          cell  = 8 bytes top->bottom, bit 7 = leftmost pixel (one 8x8 tile glyph);
          144 B per image; ink = 1; attr implicit (no attribute bytes).
        Cell-aligned only: no sub-cell anchor offsets. All-blank cells allowed.

Variants:
  front (default): assets/gfx/source/aldous/sxt_*.grid -> assets/gfx/mentor/aldous.asm
                   8 images: IDLE1 IDLE2 TALK1 TALK2 POINT_L POINT_R POINTDN FADE.
                   POINT_L is the horizontal mirror of sxt_point.grid (POINT_R).
  34:              assets/gfx/source/aldous/q34/sxt34_<frame>.grid (RIGHT-facing only)
                   -> assets/gfx/mentor/aldous34.asm, 7 RIGHT-facing images: index =
                   frame; frames IDLE1 IDLE2 TALK1 TALK2 POINT POINTDN FADE. TUT0-T7: LEFT
                   is mirrored at runtime by the blob (cells c0<->c2 + BITREV_TAB), not stored.
                   Labels sxt34_<frame>_r; SXT34_IMAGES EQU 7.

Usage:
  python3 tools/mentor_convert.py                  # write front-facing aldous.asm
  python3 tools/mentor_convert.py --check          # exit 1 if the asm is stale
  python3 tools/mentor_convert.py --variant 34     # 3/4 variant -> aldous34.asm
Regenerate after any grid edit; never hand-edit the output.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import svg_sprites as S  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "assets/gfx/source/aldous")
OUT_DIR = os.path.join(REPO, "assets/gfx/mentor")

W, H = 24, 48                 # image size in pixels
COLS, ROWS = W // 8, H // 8   # 3 cell columns, 6 cell rows
CELL_BYTES = 8
FRAME_BYTES = COLS * ROWS * CELL_BYTES   # 144
INK = "#00D7D7"               # attr $05 (cyan, non-bright) on black paper


@dataclass(frozen=True)
class Image:
    label: str        # asm label, e.g. sxt_point_l
    grid: str         # grid file name under the variant's source dir
    mirror: bool      # True: horizontal mirror of the grid bitmap


# Front-facing set, in engine order. POINT_L is derived; POINT_R is drawn.
FRONT_IMAGES = (
    Image("sxt_idle1", "sxt_idle1.grid", False),
    Image("sxt_idle2", "sxt_idle2.grid", False),
    Image("sxt_talk1", "sxt_talk1.grid", False),
    Image("sxt_talk2", "sxt_talk2.grid", False),
    Image("sxt_point_l", "sxt_point.grid", True),
    Image("sxt_point_r", "sxt_point.grid", False),
    Image("sxt_pointdn", "sxt_pointdn.grid", False),
    Image("sxt_fade", "sxt_fade.grid", False),
)

# 3/4 set: the artist draws RIGHT-facing grids only; LEFT = mirror of RIGHT, made at
# runtime by the blob (TUT0-T7: -1,008 B raw). Image index = frame.
Q34_FRAMES = ("idle1", "idle2", "talk1", "talk2", "point", "pointdn", "fade")
Q34_IMAGES = tuple(Image(f"sxt34_{f}_r", f"sxt34_{f}.grid", False) for f in Q34_FRAMES)


def rel(path: str) -> str:
    """Repo-relative path for messages; absolute when outside the repo (tests, tmp dirs)."""
    r = os.path.relpath(path, REPO)
    return path if r.startswith("..") else r


def load_grid(path: str) -> np.ndarray:
    """-> bool bitmap (True = ink), validated against the mentor format."""
    bm, meta = S.read_grid(path)
    if bm.shape != (H, W):
        raise ValueError(f"{os.path.basename(path)}: size {bm.shape[1]}x{bm.shape[0]} != {W}x{H}")
    ink = meta.get("ink", "").upper()
    if ink and ink != INK:
        raise ValueError(f"{os.path.basename(path)}: ink {ink} != {INK}")
    return bm.astype(bool)


def mirror(bm: np.ndarray) -> np.ndarray:
    """Horizontal mirror of a whole image (POINT_L from POINT_R's source)."""
    return bm[:, ::-1].copy()


def encode(bm: np.ndarray) -> bytes:
    """bool bitmap (H x W) -> 144 B cell-major (see module docstring)."""
    if bm.shape != (H, W):
        raise ValueError(f"encode: shape {bm.shape} != {H}x{W}")
    out = bytearray()
    for r in range(ROWS):
        for c in range(COLS):
            for y in range(8):
                byte = 0
                for x in range(8):
                    if bm[r * 8 + y, c * 8 + x]:
                        byte |= 0x80 >> x
                out.append(byte)
    return bytes(out)


def decode(data: bytes) -> np.ndarray:
    """144 B cell-major -> bool bitmap (H x W). Inverse of encode()."""
    if len(data) != FRAME_BYTES:
        raise ValueError(f"decode: {len(data)} B != {FRAME_BYTES}")
    bm = np.zeros((H, W), dtype=bool)
    i = 0
    for r in range(ROWS):
        for c in range(COLS):
            for y in range(8):
                for x in range(8):
                    bm[r * 8 + y, c * 8 + x] = bool(data[i] & (0x80 >> x))
                i += 1
    return bm


def build(src_dir: str, images: tuple[Image, ...]) -> list[tuple[str, bytes]]:
    out = []
    for im in images:
        bm = load_grid(os.path.join(src_dir, im.grid))
        if im.mirror:
            bm = mirror(bm)
        out.append((im.label, encode(bm)))
    return out


def render_asm(items: list[tuple[str, bytes]], variant: str, src_desc: str,
               count_name: str, order_note: list[str]) -> str:
    n = len(items)
    lines = [
        f"; mentor sprite data ({variant}) — GENERATED by tools/mentor_convert.py; do not hand-edit.",
        f"; Source: {src_desc}",
        "; Format: 24x48 1-bit, ink = 1 (attr implicit $05 cyan on black; NO attribute bytes).",
        "; Cell-major: 6 cell rows r0..r5 x 3 cell cols c0..c2, row-major; each cell is 8 B",
        "; top->bottom, bit 7 = leftmost pixel = one 8x8 tile glyph. 144 B per image.",
        "; Cell-aligned only (no sub-cell anchor offsets). All-blank cells allowed.",
        "; Labels are in engine order; each image is exactly FRAME_BYTES = 144 bytes.",
        *order_note,
        "",
        f"{count_name:<16}EQU {n}",
        "",
    ]
    for label, data in items:
        lines.append(f"{label}:")
        for i in range(ROWS * COLS):
            cell = data[i * CELL_BYTES:(i + 1) * CELL_BYTES]
            r, c = divmod(i, COLS)
            vals = ",".join(f"${b:02X}" for b in cell)
            lines.append(f"        DEFB {vals}      ; r{r}c{c}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--variant", choices=("front", "34"), default="front")
    ap.add_argument("--src", help="source dir (default: per variant)")
    ap.add_argument("--out", help="output asm (default: per variant)")
    ap.add_argument("--check", action="store_true", help="do not write; exit 1 if output is stale")
    args = ap.parse_args(argv)

    if args.variant == "front":
        src = args.src or SRC
        images, out = FRONT_IMAGES, args.out or os.path.join(OUT_DIR, "aldous.asm")
        count_name, order_note = "SXT_FRAMES", []
        desc = ("assets/gfx/source/aldous/sxt_*.grid (front-facing; POINT_L = horizontal "
                "mirror of sxt_point.grid = POINT_R)")
    else:
        src = args.src or os.path.join(SRC, "q34")
        images, out = Q34_IMAGES, args.out or os.path.join(OUT_DIR, "aldous34.asm")
        count_name = "SXT34_IMAGES"
        order_note = [
            "; Order: index = frame, RIGHT-facing only:",
            ";   0 IDLE1  1 IDLE2  2 TALK1  3 TALK2  4 POINT  5 POINTDN  6 FADE",
            "; LEFT = the blob mirrors at runtime (cells c0<->c2, bytes via BITREV_TAB).",
        ]
        desc = ("assets/gfx/source/aldous/q34/sxt34_<frame>.grid (3/4 view, RIGHT-facing "
                "drawn; LEFT = mirror)")

    try:
        items = build(src, images)
    except (OSError, ValueError) as e:
        print(f"mentor_convert: {e}", file=sys.stderr)
        return 1
    text = render_asm(items, args.variant, desc, count_name, order_note)

    if args.check:
        try:
            with open(out) as fh:
                current = fh.read()
        except OSError:
            current = ""
        if current != text:
            print(f"mentor_convert: {rel(out)} is stale; regenerate", file=sys.stderr)
            return 1
        print(f"mentor_convert: {rel(out)} up to date ({len(items)} images)")
        return 0

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as fh:
        fh.write(text)
    print(f"mentor_convert: wrote {rel(out)}: {len(items)} images x "
          f"{FRAME_BYTES} B = {len(items) * FRAME_BYTES} B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
