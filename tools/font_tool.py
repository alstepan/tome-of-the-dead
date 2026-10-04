#!/usr/bin/env python3
"""font_tool.py — WazHack/ZX fonts: derive, validate, pack, preview.

Sources (text grids, deterministic; the 6x8 font is hand-authored, the others are DERIVED
from it by explicit rules and then committed as editable grids):
  assets/gfx/concept/grid/font6x8.grid    96 glyphs, ASCII 32-127, 6x8 cells
  assets/gfx/concept/grid/font6x8_bold.grid  round-5 bold 6x8 (comparison reference)
  assets/gfx/concept/grid/font8x16.grid   menu font, MENU_SET (derived from SK: `derive`)
  assets/gfx/concept/grid/title16.grid    title font 16x16, A-Z + space (derived from SK)
  assets/gfx/concept/grid/font8x16_bold.grid round-5 bold menu font (comparison reference)

Grid format: '=== <ascii code> <label>' then H rows of W chars ('#' ink, '.' paper).

Outputs (assets/gfx/fonts/):
  font6x8.asm/.bin    8 B/char, rows top-down, MSB-left (bits 7..2 used), code 32 first
  font8x16.asm/.bin   16 B/char, MSB-left, in MENU_SET order (+ a 128-entry code->index map in .asm)
  title16.asm/.bin    32 B/char, rows top-down, 2 bytes per row (left, right)
  fonts_preview.png   review sheet

Usage:
  python3 tools/font_tool.py derive    # regenerate font8x16.grid + title16.grid from the SK skeletons
  python3 tools/font_tool.py pack      # validate + pack + preview (round-trip checked)
"""

from __future__ import annotations

import os
import re
import sys

import numpy as np
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRID = os.path.join(REPO, "assets/gfx/concept/grid")
OUT = os.path.join(REPO, "assets/gfx/fonts")

MENU_SET = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,:;!?-'/()<>=+"
HDR = re.compile(r"^===\s+(\d+)\s*(.*)$")


def parse(path: str, w: int, h: int) -> dict[int, np.ndarray]:
    glyphs, cur, rows = {}, None, []
    def close():
        if cur is not None:
            if len(rows) != h:
                raise SystemExit(f"{path}: code {cur}: {len(rows)} rows, want {h}")
            glyphs[cur] = np.array(rows, bool)
    for raw in open(path).read().splitlines():
        m = HDR.match(raw.strip())
        if m:
            close()
            cur, rows = int(m.group(1)), []
            if cur in glyphs:
                raise SystemExit(f"{path}: duplicate code {cur}")
            continue
        line = raw.strip()
        if cur is not None and line and set(line) <= set("#.") and len(line) == w:
            rows.append([c == "#" for c in line])
        elif line and not line.startswith("#"):
            raise SystemExit(f"{path}: unparsable line {raw!r}")
        elif line.startswith("#") and len(line) == w and set(line) <= set("#."):
            rows.append([c == "#" for c in line])
    close()
    return glyphs


def write_grid(path: str, glyphs: dict[int, np.ndarray], header: list[str]) -> None:
    out = list(header) + [""]
    for c, b in glyphs.items():
        out.append(f"=== {c} {chr(c) if c != 32 else 'SPACE'}")
        out += ["".join("#" if v else "." for v in r) for r in b]
        out.append("")
    open(path, "w").write("\n".join(out))


# ---------------------------------------------------------------------------
# Derivation rules (explicit, reviewable)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Script letter skeletons (round 6, user: thinner, script / calligraphic). Each glyph is a list
# of strokes in a 4 x 8 cap box (x right, y DOWN, baseline y=8). A stroke is a list of points;
# arc() inserts points along an ellipse (degrees: 0 right, 90 down, -90 up). The renderer
# draws them with a 'vertical-emphasis' pen: near-vertical runs are 2 px (menu) / 3 px
# (title) wide, everything else is a 1-px hairline, and the whole glyph is slanted (italic).
# No dithering. Deterministic; editing a skeleton and re-running `derive` regenerates the grids.
# ---------------------------------------------------------------------------

def arc(cx, cy, rx, ry, a0, a1, n=24):
    return [(cx + rx * np.cos(np.radians(a)), cy + ry * np.sin(np.radians(a)))
            for a in np.linspace(a0, a1, n)]


O_ = arc(2, 4, 2, 4, -90, 270)
SK = {
    " ": [],
    "A": [[(-0.3, 8.3), (0.4, 7.6), (2.2, 0), (3.4, 6), (4.0, 8)], [(0.9, 5), (3.1, 5)]],
    "B": [[(-0.3, 0.6), (0.6, 0), (0.6, 8)], [(0.6, 0)] + arc(2.2, 2, 1.6, 2, -90, 90) + [(0.6, 4)],
          [(0.6, 4)] + arc(2.2, 6, 1.9, 2, -90, 90) + [(0.6, 8)]],
    "C": [arc(2.3, 4, 2.2, 4, -40, -320)],
    "D": [[(-0.3, 0.6), (0.6, 0), (0.6, 8)], [(0.6, 0)] + arc(1.6, 4, 2.4, 4, -90, 90) + [(0.6, 8)]],
    "E": [[(4, 0.6), (3.6, 0), (0.6, 0), (0.6, 8), (3.6, 8), (4, 7.4)], [(0.6, 4), (2.8, 4)]],
    "F": [[(4, 0.6), (3.6, 0), (0.6, 0), (0.6, 8), (0, 8.6)], [(0.6, 4), (2.8, 4)]],
    "G": [arc(2.3, 4, 2.2, 4, -40, -315) + [(4, 4.5), (2.6, 4.5)]],
    "H": [[(-0.3, 0.6), (0.6, 0), (0.6, 8)], [(3.4, 0), (3.4, 8), (4.1, 8.5)], [(0.6, 4), (3.4, 4)]],
    "I": [[(1.2, 0), (2.8, 0)], [(2, 0), (2, 8)], [(1.2, 8), (2.8, 8)]],
    "J": [[(1, 0), (4, 0)], [(3, 0), (3, 6)] + arc(1.8, 6, 1.2, 2, 0, 180) + [(0.5, 5)]],
    "K": [[(-0.3, 0.6), (0.6, 0), (0.6, 8)], [(3.6, 0), (0.6, 4.6)], [(1.6, 3.6), (3.4, 7.6), (4.1, 8.3)]],
    "L": [[(-0.3, 0.6), (0.6, 0), (0.6, 8), (4, 8), (4.2, 7.3)]],
    "M": [["h", (-0.4, 8.3), (0.0, 8), (0.9, 0)], ["h", (0.9, 0), (2.3, 7), (3.7, 0)],
          ["h", (3.7, 0), (3.9, 8), (4.3, 8.4)]],
    "N": [[(-0.2, 8.3), (0.5, 7.6), (0.5, 0)], ["h", (0.5, 0), (3.5, 8)],
          [(3.5, 8), (3.5, 0), (4.0, -0.4)]],
    "O": [O_],
    "P": [[(-0.3, 0.6), (0.6, 0), (0.6, 8.4)], [(0.6, 0)] + arc(2.2, 2.2, 1.7, 2.2, -90, 90) + [(0.6, 4.4)]],
    "Q": [O_, [(2.0, 6.0), (3.3, 8.0), (4.3, 8.6)]],
    "R": [[(-0.3, 0.6), (0.6, 0), (0.6, 8)], [(0.6, 0)] + arc(2.2, 2.2, 1.7, 2.2, -90, 90) + [(0.6, 4.4)],
          [(1.8, 4.4), (3.4, 7.6), (4.1, 8.3)]],
    "S": [arc(2.1, 2.1, 1.8, 2.1, -20, -270) + arc(2.0, 6.0, 2.0, 2.0, -90, 160)],
    "T": [[(-0.2, 0.8), (0.4, 0), (4, 0)], [(2, 0), (2, 8)]],
    "U": [[(-0.3, 0.6), (0.5, 0), (0.5, 5.5)] + arc(2, 5.5, 1.5, 2.5, 180, 0), [(3.5, 0), (3.5, 8), (4.1, 8.4)]],
    "V": [[(-0.3, 0.6), (0.3, 0), (2, 8)], ["h", (2, 8), (3.7, 0), (4.2, -0.4)]],
    "W": [["h", (-0.3, 0.6), (0.2, 0), (1, 8), (2, 3), (3, 8), (3.8, 0), (4.2, -0.4)]],
    "X": [[(0, 0), (4, 8)], [(4, 0), (0, 8)]],
    "Y": [[(-0.3, 0.6), (0.3, 0), (2, 4), (3.7, 0)], [(2, 4), (2, 8)]],
    "Z": [[(0, 0.6), (0.4, 0), (4, 0), (0, 8), (4, 8), (4.3, 7.4)], [(1, 4), (3, 4)]],
    "0": [arc(2, 4, 1.8, 4, -90, 270), [(1, 6.5), (3, 1.5)]],
    "1": [[(0.8, 1.6), (2, 0), (2, 8)], [(1, 8), (3, 8)]],
    "2": [arc(2, 2.2, 1.9, 2.2, -170, 20) + [(0, 8), (4, 8)]],
    "3": [arc(2, 2, 1.8, 2, -160, 90) + arc(2, 6, 2, 2, -90, 160)],
    "4": [[(3, 8), (3, 0), (0, 5.6), (4, 5.6)]],
    "5": [[(4, 0), (0.8, 0), (0.5, 3.6)] + arc(2, 5.6, 2, 2.4, -125, 150)],
    "6": [[(3.4, 0), (1.2, 2.2), (0.1, 5.5)] + arc(2, 5.8, 1.9, 2.2, 180, 540)],
    "7": [[(0, 0), (4, 0), (1.6, 8)]],
    "8": [arc(2, 2, 1.6, 2, -90, 270), arc(2, 6, 2, 2, -90, 270)],
    "9": [arc(2, 2.4, 1.9, 2.4, 0, 360) + [(3.9, 2.4), (3.4, 6), (1, 8)]],
    ".": [[(2, 7.6), (2, 8)]],
    ",": [[(2, 7.4), (2, 8), (1.4, 9.2)]],
    ":": [[(2, 2.6), (2, 3)], [(2, 7.6), (2, 8)]],
    ";": [[(2, 2.6), (2, 3)], [(2, 7.4), (2, 8), (1.4, 9.2)]],
    "!": [[(2, 0), (2, 5.4)], [(2, 7.6), (2, 8)]],
    "?": [arc(2, 2, 1.9, 2, -160, 60) + [(2, 4.6), (2, 5.6)], [(2, 7.6), (2, 8)]],
    "-": [[(1, 5), (3, 5)]],
    "'": [[(2.2, 0), (1.6, 2)]],
    "/": [[(4, 0), (0, 8)]],
    "(": [arc(4.2, 4, 3, 4.6, -125, -235)],
    ")": [arc(-0.2, 4, 3, 4.6, -55, 55)],
    "<": [[(4, 1), (0, 4.5), (4, 8)]],
    ">": [[(0, 1), (4, 4.5), (0, 8)]],
    "=": [[(0.5, 3), (3.5, 3)], [(0.5, 6), (3.5, 6)]],
    "+": [[(2, 2), (2, 7)], [(0, 4.5), (4, 4.5)]],
}
TITLE_SET = " ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def render(sk, W, H, sx, sy, ox, oy, slant, thick, gap_col):
    """Rasterise skeleton strokes: points -> px with italic slant; near-vertical runs stamp a
    `thick`-px horizontal nib, all other runs a 1-px hairline. Ink clipped to cols < gap_col."""
    g = np.zeros((H, W), bool)
    def to_px(x, y):
        return ox + x * sx + slant * (8 - y) * sy, oy + y * sy
    for stroke in sk:
        hair = bool(stroke) and stroke[0] == "h"            # "h" marker: hairline only
        if hair:
            stroke = stroke[1:]
        pts = [to_px(*p) for p in stroke]
        if len(pts) == 1:
            pts = pts * 2
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            vertical = not hair and abs(y1 - y0) > 3.0 * abs(x1 - x0)
            n = max(2, int(np.hypot(x1 - x0, y1 - y0) * 4))
            for t in np.linspace(0, 1, n):
                x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
                xi, yi = int(np.floor(x + 0.5)), int(np.floor(y + 0.5))
                for k in range(thick if vertical else 1):
                    if 0 <= yi < H and 0 <= xi + k < gap_col:
                        g[yi, xi + k] = True
    return g


def derive_menu(_f6=None) -> dict:
    """8x16 script menu glyph: cap box 4x8 -> ~5x12 px at rows 2..13, slight slant (~0.5 px; width is the priority),
    2-px downstrokes, 1-px hairlines, column 7 = letter gap."""
    return {ord(ch): render(SK[ch], 8, 16, 1.25, 1.45, 0.0, 2.0, 0.04, 2, 7) for ch in MENU_SET}


def derive_title(_f6=None) -> dict:
    """16x16 script title glyph, A-Z + space: cap box -> ~9x12 px at rows 2..13, slant ~2.4 px,
    3-px downstrokes, 1-px hairlines (calligraphic contrast), column 15 = letter gap."""
    return {ord(ch): render(SK[ch], 16, 16, 2.15, 1.5, 0.8, 2.0, 0.2, 3, 15) for ch in TITLE_SET}


# ---------------------------------------------------------------------------
# Validation + packing
# ---------------------------------------------------------------------------

def validate6(f6: dict) -> list[str]:
    errs = []
    want = set(range(32, 128))
    if set(f6) != want:
        errs.append(f"font6x8: codes missing {sorted(want - set(f6))} extra {sorted(set(f6) - want)}")
    for c, g in f6.items():
        if g.shape != (8, 6):
            errs.append(f"font6x8 {c}: shape {g.shape}")
        if g[:, 5].any():
            errs.append(f"font6x8 {c} '{chr(c)}': gap column 5 not blank")
        if g[0].any():
            errs.append(f"font6x8 {c} '{chr(c)}': line-gap row 0 not blank")
    return errs


def pack_rows(g: np.ndarray) -> bytes:
    """Rows top-down; each row MSB-left, padded on the right to whole bytes."""
    h, w = g.shape
    nb = (w + 7) // 8
    out = bytearray()
    for r in g:
        bits = np.zeros(nb * 8, bool)
        bits[:w] = r
        out += np.packbits(bits).tobytes()
    return bytes(out)


def unpack_rows(data: bytes, w: int, h: int) -> np.ndarray:
    nb = (w + 7) // 8
    a = np.unpackbits(np.frombuffer(data, np.uint8)).reshape(h, nb * 8)
    return a[:, :w].astype(bool)


def emit(name: str, glyphs: dict, order: list[int], w: int, h: int, header: list[str],
         extra_asm: list[str] = ()) -> bytes:
    blob = bytearray()
    asm = [f"; {l}" for l in header] + [""]
    label = name.upper()
    asm.append(f"{label}_W      EQU {w}")
    asm.append(f"{label}_H      EQU {h}")
    asm.append(f"{label}_STRIDE EQU {len(pack_rows(glyphs[order[0]]))}")
    asm.append(f"{label}_COUNT  EQU {len(order)}")
    asm.append("")
    asm.append(f"{name}:")
    for c in order:
        b = pack_rows(glyphs[c])
        if not np.array_equal(unpack_rows(b, w, h), glyphs[c]):
            raise SystemExit(f"{name}: pack round-trip mismatch on {c}")
        if name == "font6x8" and any(v & 3 for v in b):
            # print6 (src/panel_hot.asm) composes 4 chars per 3 bytes: bits 1..0
            # would land in the next char's pixels (panel_boot masks them off
            # anyway, so they would silently vanish).
            raise SystemExit(f"{name}: glyph {c} uses bits 1..0 (6-px cells only)")
        blob += b
        lab = chr(c) if 33 <= c < 127 and chr(c) not in ";'\"\\" else f"#{c}"
        asm.append(f"    DEFB {', '.join(f'${v:02X}' for v in b)}   ; {c:3d} {lab}")
    asm += [""] + list(extra_asm)
    open(os.path.join(OUT, name + ".asm"), "w").write("\n".join(asm) + "\n")
    open(os.path.join(OUT, name + ".bin"), "wb").write(bytes(blob))
    return bytes(blob)


def preview(f6, f8, ft, path, f6b=None, f8b=None):
    """Review sheet: thin 6x8 set; BOLD vs THIN comparison lines; menu font NEW vs OLD;
    title A-Z and the game name."""
    def tile(g, ink=(255, 255, 255)):
        im = np.zeros(g.shape + (3,), np.uint8)
        im[g] = ink
        return im
    def line6(font, text, ink=(255, 255, 255)):
        return np.hstack([tile(font[ord(ch)], ink) for ch in text])
    blocks = []
    for i in range(32, 128, 32):
        blocks.append(np.hstack([tile(f6[c]) for c in range(i, i + 32)]))
    for t in ("THE GOBLIN ATTACKS YOU AND MISSES. (12)  ",
              "LIGHTNING 5MP RANGE 28 BOUNCE 2 PIERCES   ",
              "N/H M/W 0/O 1/I/l rn/m 5/S 8/B 2/Z c/e   "):
        if f6b:
            blocks.append(line6(f6b, t, (255, 200, 120)))     # bold (old), amber
        blocks.append(line6(f6, t))                           # thin (new), white
    m_new = [np.hstack([tile(f8[ord(c)]) for c in MENU_SET[i:i + 26]]) for i in (0, 26)]
    m_old = [np.hstack([tile(f8b[ord(c)], (255, 200, 120)) for c in MENU_SET[i:i + 26]])
             for i in (0, 26)] if f8b else []
    t1 = np.hstack([tile(ft[ord(c)]) for c in TITLE_SET[1:14]])
    t2 = np.hstack([tile(ft[ord(c)]) for c in TITLE_SET[14:]])
    t3 = np.hstack([tile(ft[ord(c)], (255, 255, 0)) for c in "TOME OF THE DEAD"])
    allb = blocks + m_old[:1] + m_new[:1] + m_old[1:] + m_new[1:] + [t1, t2, t3]
    W = max(a.shape[1] for a in allb)
    img = np.vstack([np.pad(a, ((2, 2), (0, W - a.shape[1]), (0, 0)), constant_values=40)
                     for a in allb])
    Image.fromarray(img).resize((img.shape[1] * 3, img.shape[0] * 3), Image.NEAREST).save(path)


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    f6 = parse(os.path.join(GRID, "font6x8.grid"), 6, 8)
    errs = validate6(f6) + [e.replace("font6x8", "font6x8_bold") for e in validate6(
        parse(os.path.join(GRID, "font6x8_bold.grid"), 6, 8))]
    if errs:
        print("\n".join(errs), file=sys.stderr)
        return 1
    cmd = sys.argv[1] if len(sys.argv) > 1 else "pack"
    p8 = os.path.join(GRID, "font8x16.grid")
    pt = os.path.join(GRID, "title16.grid")
    if cmd == "derive":
        f8 = derive_menu()
        write_grid(p8, f8, [
            "# WazHack/ZX menu font 8x16, SCRIPT (round 6) — DERIVED by tools/font_tool.py derive from",
            f"# the SK skeletons (italic, 2-px downstrokes, 1-px hairlines, no dither). Set: {MENU_SET!r}",
            "# Editable after derivation (pack reads this file). Column 7 = letter gap."])
        write_grid(pt, derive_title(), [
            "# WazHack/ZX title font 16x16, SCRIPT (round 6) — DERIVED by tools/font_tool.py derive",
            f"# from the SK skeletons (italic, 3-px downstrokes, hairlines). Set: {TITLE_SET!r}"])
        print(f"derived {p8}, {pt}")
        return 0
    f8 = parse(p8, 8, 16)
    ft = parse(pt, 16, 16)
    for ch in MENU_SET:
        if ord(ch) not in f8:
            print(f"font8x16 missing {ch!r}", file=sys.stderr)
            return 1
    b6 = emit("font6x8", f6, list(range(32, 128)), 6, 8, [
        "WazHack/ZX 6x8 font (concept, from assets/gfx/concept/grid/font6x8.grid via",
        "tools/font_tool.py pack; do not hand-edit). ASCII 32-127, 8 B/char, rows top-down,",
        "MSB-left, bits 7..2 used (6 px incl. the 1-px gap). Address = font6x8 + (code-32)*8.",
        "Used by: message log, info line, inventory page (42 chars per 256 px)."])
    idx = [0xFF] * 128
    for i, ch in enumerate(MENU_SET):
        idx[ord(ch)] = i
    b8 = emit("font8x16", f8, [ord(c) for c in MENU_SET], 8, 16, [
        "WazHack/ZX menu font 8x16 (concept). 16 B/char in MENU_SET order; font8x16_map maps",
        f"ASCII 0-127 -> glyph index ($FF = not in set). Set: {MENU_SET}"],
        ["font8x16_map:"] + [f"    DEFB {', '.join(f'${v:02X}' for v in idx[i:i + 16])}"
                             for i in range(0, 128, 16)])
    bt = emit("title16", ft, [ord(c) for c in TITLE_SET], 16, 16, [
        f"WazHack/ZX title glyphs 16x16 (concept). 32 B/char, 2 B per row. Set: {TITLE_SET}",
        "Index = code-32 for space, code-64 for A-Z (A=1). 'TOME OF THE DEAD' fits 2 rows."])
    f6b = parse(os.path.join(GRID, "font6x8_bold.grid"), 6, 8)
    emit("font6x8_bold", f6b, list(range(32, 128)), 6, 8, [
        "WazHack/ZX 6x8 font, BOLD round-5 variant (comparison only). Same layout as font6x8."])
    f8b = parse(os.path.join(GRID, "font8x16_bold.grid"), 8, 16)
    preview(f6, f8, ft, os.path.join(OUT, "fonts_preview.png"), f6b, f8b)
    print(f"font6x8: {len(f6)} glyphs, {len(b6)} B")
    print(f"font8x16: {len(MENU_SET)} glyphs, {len(b8)} B (+128 B map)")
    print(f"title16: {len(TITLE_SET)} glyphs, {len(bt)} B")
    print(f"full 16x16 A-Z+0-9 would be {36 * 32} B; full 8x16 ASCII 96 would be {96 * 16} B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
