#!/usr/bin/env python3
"""gfx_assess.py — WazHack/ZX sprite quality / legality assessor.

Given a packed sprite asm (the gfx_convert output) and an OPTIONAL reference
image, this tool:

  * decodes the DEFB byte table back to the 16xH foreground matrix
    (round-trip / structural validation of the data contract),
  * renders it back to an ASCII grid (#/.) and a NEAREST-scaled PNG so a human
    (or the manager) can eyeball the silhouette,
  * if a --ref image is given, reports load-bearing similarity metrics at the
    sprite's native cell grid:
        - silhouette IoU + Dice (the most load-bearing number at 16x24),
        - SSIM (numpy implementation; scikit-image is NOT installed),
        - per-8x8-cell pixel-difference counts,
  * reports clash / descriptor legality (one paper+ink; optional band-paper
    match check, the design sec 1.7 hard constraint),
  * OPTIONALLY asks a local Ollama vision model (llava:7b / moondream) to rate
    "recognizable side-on adventurer? 0-10 + one line" on an UPSCALED render
    (vision models fail on raw 16x24). Fully guarded: if Ollama is down/absent
    the tool still runs and exits on the structural+clash result only.

Exit code: 0 iff the data is structurally valid AND clash-legal. Similarity
metrics and the perceptual score are REPORTED, never gating — an AI front-end
producing a poor silhouette is a valid finding, not a tool failure.

Usage:
  python3 tools/gfx_assess.py --asm assets/gfx/player.asm
  python3 tools/gfx_assess.py --asm assets/gfx/player.asm --ref concept.png --vision
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

# Reuse the converter's packing/colour helpers (single source of truth).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gfx_convert as gc  # noqa: E402


# ---------------------------------------------------------------------------
# Parse a packed sprite .asm back into rows + descriptor
# ---------------------------------------------------------------------------

_DEFB_RE = re.compile(r"\bDEFB\s+([^;]+)", re.IGNORECASE)
_BYTE_RE = re.compile(r"\$([0-9A-Fa-f]{1,2})|(\d+)")


def parse_asm_bytes(text: str) -> list[int]:
    """Collect every DEFB byte in source order from an asm fragment."""
    out: list[int] = []
    for m in _DEFB_RE.finditer(text):
        for b in m.group(1).split(","):
            b = b.strip()
            if not b:
                continue
            mm = _BYTE_RE.search(b)
            if not mm:
                continue
            out.append(int(mm.group(1), 16) if mm.group(1) else int(mm.group(2)))
    return out


def split_sprite(bytes_: list[int], height: int):
    """Split a flat byte list into (rows[height][6], descriptor)."""
    need = height * 6 + 1
    if len(bytes_) != need:
        raise ValueError(
            f"expected {need} bytes ({height}*6 + 1 descriptor), got {len(bytes_)}"
        )
    rows = [bytes_[i * 6:i * 6 + 6] for i in range(height)]
    return rows, bytes_[-1]


# ---------------------------------------------------------------------------
# SSIM (numpy; uniform window box filter via sliding_window_view)
# ---------------------------------------------------------------------------

def _boxmean(x: np.ndarray, win: int) -> np.ndarray:
    pad = win // 2
    xp = np.pad(x, pad, mode="reflect")
    w = np.lib.stride_tricks.sliding_window_view(xp, (win, win))
    return w.mean(axis=(-1, -2))


def ssim(a: np.ndarray, b: np.ndarray, win: int = 7, L: float = 255.0) -> float:
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    win = min(win, a.shape[0], a.shape[1])
    if win % 2 == 0:
        win -= 1
    win = max(win, 3)
    C1 = (0.01 * L) ** 2
    C2 = (0.03 * L) ** 2
    mu_a = _boxmean(a, win)
    mu_b = _boxmean(b, win)
    mu_a2, mu_b2, mu_ab = mu_a * mu_a, mu_b * mu_b, mu_a * mu_b
    var_a = _boxmean(a * a, win) - mu_a2
    var_b = _boxmean(b * b, win) - mu_b2
    cov = _boxmean(a * b, win) - mu_ab
    num = (2 * mu_ab + C1) * (2 * cov + C2)
    den = (mu_a2 + mu_b2 + C1) * (var_a + var_b + C2)
    return float((num / den).mean())


# ---------------------------------------------------------------------------
# Reference reduction (image -> binary silhouette at sprite grid)
# ---------------------------------------------------------------------------

def ref_to_silhouette(path: str, w: int, h: int):
    """Return (binary_fg HxW, grayscale HxW uint8) for a reference image."""
    if Image is None:
        raise RuntimeError("Pillow not available")
    grid = gc.image_to_grid(path, w, h, threshold=None, invert=False)
    img = Image.open(path).convert("L")
    iw, ih = img.size
    tar = w / h
    src = iw / ih
    if src > tar:
        nw = int(round(ih * tar)); left = (iw - nw) // 2
        img = img.crop((left, 0, left + nw, ih))
    else:
        nh = int(round(iw / tar)); top = (ih - nh) // 2
        img = img.crop((0, top, iw, top + nh))
    gray = np.asarray(img.resize((w, h), Image.LANCZOS), dtype=np.uint8)
    return grid.astype(bool), gray


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def iou_dice(a: np.ndarray, b: np.ndarray):
    a = a.astype(bool); b = b.astype(bool)
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    sa, sb = a.sum(), b.sum()
    iou = inter / union if union else 1.0
    dice = (2 * inter) / (sa + sb) if (sa + sb) else 1.0
    return float(iou), float(dice)


def per_cell_diff(a: np.ndarray, b: np.ndarray):
    h, w = a.shape
    rows, cols = h // 8, w // 8
    diff = np.zeros((rows, cols), dtype=int)
    d = np.logical_xor(a, b)
    for r in range(rows):
        for c in range(cols):
            diff[r, c] = int(d[r * 8:r * 8 + 8, c * 8:c * 8 + 8].sum())
    return diff


# ---------------------------------------------------------------------------
# ASCII render-back
# ---------------------------------------------------------------------------

def ascii_grid(fg: np.ndarray) -> str:
    return "\n".join("".join("#" if v else "." for v in row) for row in fg)


# ---------------------------------------------------------------------------
# Optional Ollama vision rating (fully guarded)
# ---------------------------------------------------------------------------

def vision_rate(png_path: str, model: str, timeout: int = 120):
    """Ask a local vision model to rate the sprite. Returns text or None."""
    prompt = (
        "This is a tiny 1-bit ZX Spectrum game sprite, upscaled. Is it a "
        "recognizable side-on (profile) adventurer / humanoid figure? "
        "Answer strictly as: SCORE: <0-10> then one short sentence why. "
        f"Image: {png_path}"
    )
    try:
        r = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True, text=True, timeout=timeout,
        )
        if r.returncode != 0:
            return None
        return r.stdout.strip() or None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def upscale_png(fg: np.ndarray, descriptor: int, path: str, scale: int = 12):
    ink = descriptor & 7
    paper = (descriptor >> 3) & 7
    bright = bool(descriptor & 0x40)
    gc.render_sprite_png(fg, path, ink, paper, bright, scale=scale)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="WazHack/ZX sprite assessor")
    p.add_argument("--asm", required=True, help="packed sprite .asm to assess")
    p.add_argument("--height", type=int, default=24)
    p.add_argument("--ref", help="reference image for similarity metrics")
    p.add_argument("--band-paper", dest="band_paper", default=None,
                   choices=list(gc.COLOURS),
                   help="if set, assert descriptor PAPER == this band paper")
    p.add_argument("--png", help="write an upscaled render-back PNG here")
    p.add_argument("--vision", action="store_true",
                   help="ask a local Ollama vision model to rate the sprite")
    p.add_argument("--vision-model", default="llava:7b")
    args = p.parse_args(argv)

    with open(args.asm) as f:
        raw = f.read()

    fatal = []
    bytes_ = parse_asm_bytes(raw)
    try:
        rows, descriptor = split_sprite(bytes_, args.height)
    except ValueError as e:
        print(f"STRUCTURE FAILED: {e}", file=sys.stderr)
        return 1

    # round-trip / structural validation (raises on bad packing)
    try:
        fg = gc.unpack_sprite(rows)
    except ValueError as e:
        print(f"ROUND-TRIP FAILED: {e}", file=sys.stderr)
        return 1

    ink = descriptor & 7
    paper = (descriptor >> 3) & 7
    bright = bool(descriptor & 0x40)
    flash = bool(descriptor & 0x80)

    print(f"asm        : {args.asm}")
    print(f"bytes      : {len(bytes_)} ({args.height}*6 + 1 descriptor)  round-trip: OK")
    print(f"descriptor : ${descriptor:02X}  ink={gc.COL_NAME[ink]} "
          f"paper={gc.COL_NAME[paper]} bright={int(bright)} flash={int(flash)}")

    # clash / descriptor legality
    if ink == paper:
        fatal.append("descriptor ink == paper (sprite invisible)")
    if args.band_paper is not None:
        bp = gc.COLOURS[args.band_paper]
        if paper != bp:
            fatal.append(f"descriptor PAPER={gc.COL_NAME[paper]} != band "
                         f"paper {args.band_paper} (design sec 1.7)")
    print(f"clash      : {'FAIL' if fatal else 'OK'} "
          f"(one paper+ink always holds on hardware; descriptor legality checked)")

    coverage = fg.sum()
    print(f"coverage   : {coverage}/{fg.size} ink pixels "
          f"({100 * coverage / fg.size:.0f}%)")

    print("\nrender-back (ASCII #=ink .=transparent):")
    print(ascii_grid(fg))

    # render-back PNG
    png_path = args.png or os.path.splitext(args.asm)[0] + "_render.png"
    if Image is not None:
        upscale_png(fg, descriptor, png_path, scale=12)
        print(f"\nrender PNG : {png_path}")

    # similarity vs reference
    if args.ref:
        ref_fg, ref_gray = ref_to_silhouette(args.ref, 16, args.height)
        iou, dice = iou_dice(fg, ref_fg)
        spr_gray = np.where(fg, 255, 0).astype(np.uint8)
        ref_bin_gray = np.where(ref_fg, 255, 0).astype(np.uint8)
        ssim_bin = ssim(spr_gray, ref_bin_gray)
        ssim_gray = ssim(spr_gray, ref_gray)
        cell = per_cell_diff(fg, ref_fg)
        print(f"\nreference  : {args.ref}")
        print(f"silhouette : IoU={iou:.3f}  Dice={dice:.3f}  "
              f"(load-bearing at 16x{args.height})")
        print(f"SSIM       : vs-binarized={ssim_bin:.3f}  vs-grayscale={ssim_gray:.3f}")
        print(f"per-cell xor pixel diff (rows x cols of 8x8):")
        for r in range(cell.shape[0]):
            print("   " + "  ".join(f"{cell[r,c]:2d}" for c in range(cell.shape[1])))

    # optional perceptual rating
    if args.vision and Image is not None:
        up = tempfile.NamedTemporaryFile(suffix="_vis.png", delete=False).name
        upscale_png(fg, descriptor, up, scale=16)
        txt = vision_rate(up, args.vision_model)
        if txt is None:
            print(f"\nvision     : unavailable (Ollama down / model "
                  f"'{args.vision_model}' absent) — non-fatal")
        else:
            print(f"\nvision ({args.vision_model}):\n{txt}")

    if fatal:
        print("\nVALIDATION FAILED:", file=sys.stderr)
        for e in fatal:
            print("  - " + e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
