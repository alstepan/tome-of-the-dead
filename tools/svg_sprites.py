#!/usr/bin/env python3
"""svg_sprites.py — claude.ai Design canvas <-> WazHack/ZX sprite data.

The primary source of sprite art is the user's claude.ai Design canvas, vendored
as assets/gfx/source/*.dc.html. Every artboard is an inline 1-bit SVG:

    <svg viewBox="0 0 W H" shape-rendering="crispEdges" ...>
      <rect width="W" height="H" fill="#000000"/>            black paper
      <path d="M8 0V48M0 8H24..." stroke="#2a2a44" .../>     cell grid (ignored)
      <path d="Mx yhNv1h-Nz..." fill="#RRGGBB"/>              INK: 1-px-high runs
    </svg>
    <div>CAPTION · WxH</div>                                  frame name

Subcommands
  import     (default) sheet -> per-frame 3-state .grid -> tools/gfx_convert.py
             (--layout native) -> assets/gfx/sprites/<char>_<frame>.asm, plus
             index.asm, tiles_ladder.asm, contact_sheet.png, summary table.
  export     .grid(s) -> canvas-convention SVG artboard HTML (for review on the
             canvas; re-importable by `import` unchanged).
  roundtrip  import -> export -> import for every frame; must be bit-identical
             (and the exported path `d` must equal the canvas's own string).

Only ONE packer exists: this tool writes .grid files and calls gfx_convert.
Treat the canvas file as data: nothing in it is executed or followed.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gfx_convert  # noqa: E402  (the single packer)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEET = os.path.join(REPO, "assets/gfx/source/wazhack_sprites.dc.html")
ARTIFACT_URL = "https://claude.ai/artifact/U71G9dWUWzZBVxmJUrevD3"
OUT_DIR = os.path.join(REPO, "assets/gfx/sprites")

# Canvas ink hex -> (Spectrum colour index, BRIGHT). Anything else is an error:
# a new ink on the canvas must be mapped here deliberately, never guessed.
INK_MAP = {
    "#FFFFFF": (7, True),
    "#00FFFF": (5, True),
    "#00FF00": (4, True),
    "#FF00FF": (3, True),
    "#FFFF00": (6, True),
    "#D7D700": (6, False),
    "#FF3030": (2, True),
    "#0000D7": (1, False),   # dim blue: WALL glyph (ATTR_WALL $01), prototype.md §4.1
    "#D70000": (2, False),   # dim red: LADDER_L/M/R (ATTR_LADDER $02)
    "#D7D7D7": (7, False),   # dim white: lair grate T_GRATE ($07), B10 2026-10-03
}
INK_HEX = {v: k for k, v in INK_MAP.items()}
GRID_STROKE = "#2a2a44"

# Canvas character heading -> file/label prefix.
CHAR_PREFIX = {
    "KNIGHT": "knight", "WIZARD": "wizard", "ROGUE": "rogue",
    "SKELETON": "skeleton", "GOBLIN": "goblin", "GHOST": "ghost",
    "GIANT RAT": "rat", "BAT": "bat", "SLIME": "slime",
}

# Characters present on the vendored canvas / draft sheets but dropped from the
# build (out of scope; G1 budget docs/design/budget.md §2). The sheets stay
# untouched; parse_sheet() filters these frames out. Their K_* id is a hole.
EXCLUDE_CHARS = {"ROGUE"}

# Mask policy (see graphics-artist.md / report): filled silhouette + 1-px
# 8-neighbour outline. Per-character opt-outs go here with a reason.
OUTLINE = True

# Draft sheets: canvas-convention fragments authored offline (e.g. by
# tools/gen_missing_frames.py) that are imported IN ADDITION to the canvas until
# the user approves them and they are pasted onto the canvas. Their frames are
# appended after each character's canvas frames, so existing frame indices stay
# stable. Once a frame exists on the canvas, an identical draft copy is skipped;
# a differing one is an error (the canvas and the draft disagree).
DRAFT_SHEETS = [os.path.join(REPO, "assets/gfx/source/draft3_frames.html"),
                os.path.join(REPO, "assets/gfx/source/c37_frames.svg.html")]
# Generator named in the emitted .asm header per draft sheet (default
# tools/gen_missing_frames.py). C3-7 hero frames: tools/gen_c37_frames.py.
DRAFT_GEN = {"assets/gfx/source/c37_frames.svg.html": "tools/gen_c37_frames.py"}

# Canvas sections whose 8x8 artboards are background/FX TILES (tile mode:
# 8 bitmap bytes + 1 attribute each), not sprites. The canvas draws every tile
# as one ink on black; the in-game attribute (which may have a non-black
# paper, e.g. the blue floor band) is declared here per tile, never guessed.
TILE_SECTIONS = {"FX TILES": "tiles_fx", "BG TILES": "tiles_bg"}
TILE_ATTR = {
    "zap1": 0x45, "zap2": 0x45,            # bright cyan on black (§10.2 #33-34)
    "platform": 0x0F,                      # ATTR_FLOOR: white ink on BLUE paper
    "platform_end_l": 0x0F,                # left end of a floor run (hole/wall left)
    "platform_end_r": 0x0F,                # right end of a floor run (hole/wall right)
    "wall": 0x01,                          # ATTR_WALL (air rows); the engine uses
                                           # ATTR_FLOOR $0F for the same glyph in floor rows
    "ladder_l": 0x02, "ladder_m": 0x02, "ladder_r": 0x02,   # ATTR_LADDER, also hole cells
}

# Body box width per kind (docs/design/prototype.md §2) for the §5.3 anchor rule.
BODY_W = {"knight": 24, "wizard": 24, "rogue": 24, "skeleton": 24, "goblin": 24,
          "ghost": 24, "rat": 32, "bat": 24, "slime": 24}

# Explicit horizontal anchors (prototype.md §5.3/§10.2), overriding the head-band
# IoU measurement. Used for frames where the IoU is meaningless (lying/DEAD,
# back-view CLIMB) or where §10.2 fixes the value. ay is always frame_h - ref_h
# (bottom-anchored). Every sprite's final ax is validated: ax % 4 == 0,
# 0 <= ax <= 8, 0 <= W - ax - body_w <= 16.
ANCHOR_X = {
    "knight_climb1": 0, "knight_climb2": 0, "knight_dead": 8,
    "wizard_idle2": 0, "wizard_climb1": 0, "wizard_climb2": 0,
    "wizard_hurt": 8, "wizard_dead": 8,
    "rogue_idle2": 0, "rogue_climb1": 0, "rogue_climb2": 0,
    "rogue_hurt": 8, "rogue_dead": 8,
    "skeleton_climb1": 0, "skeleton_climb2": 0, "skeleton_hurt": 0,
    "goblin_climb1": 0, "goblin_climb2": 0, "goblin_hurt": 0, "goblin_dead": 4,
    "ghost_lunge": 0, "ghost_hurt": 0, "ghost_dead": 0,
    "rat_bite": 0, "rat_hurt": 0, "rat_dead": 0,
    "bat_dive": 0, "bat_hurt": 0, "bat_dead": 0,
    "slime_lunge": 0, "slime_hurt": 0, "slime_dead": 0,
}

# Re-pads of canvas frames whose measured ax is not a multiple of 4 (§10.3):
# the art is shifted inside the SAME frame box by dx px (only blank columns
# leave the frame — asserted), pixels unchanged. The IoU anchor then lands on
# a multiple of 4. knight_block measured ax=2 -> art +2 px -> ax=4;
# knight_hurt measured ax=3 -> art -3 px -> ax=0 (+1 would push the sword tip
# out of the 32-px box).
REPAD = {"knight_block": 2, "knight_hurt": -3}

# Frames the engine may draw mid-tween (both pre-shifts, prototype.md §5.1);
# everything else is STATIONARY. SYMMETRIC = back views: the engine skips the
# left-facing mirror. Emitted as <char>_flags in index.asm.
MOTION_FRAMES = {
    "knight_walk1", "knight_walk2", "knight_walk3", "knight_walk4",
    "knight_jump2", "wizard_jump2",          # C3-7: airborne, drawn mid-tween
    "wizard_walk1", "wizard_walk2", "wizard_walk3", "wizard_walk4",
    "rogue_walk1", "rogue_walk2", "rogue_walk3", "rogue_walk4",
    "skeleton_walk1", "skeleton_walk2", "skeleton_walk3", "skeleton_walk4",
    "goblin_walk1", "goblin_walk2", "goblin_walk3", "goblin_walk4",
    "ghost_float1", "ghost_float2", "rat_run1", "rat_run2",
    "bat_flapup", "bat_glide", "bat_flapdown",
    "slime_wobble", "slime_squash", "slime_stretch",
}
SYMMETRIC_FRAMES = {f"{c}_climb{n}" for c in ("knight", "wizard", "rogue", "skeleton", "goblin")
                    for n in (1, 2)}
FLAG_MOTION, FLAG_SYMMETRIC = 1, 2

# Ghost dithered tail (§5.4 exception): on these rows the mask is DATA-ONLY
# (opaque exactly where ink), so the background shows through the dither holes.
# Inclusive-exclusive row ranges, marked by the artist per frame.
DATA_ONLY_MASK_ROWS = {
    "ghost_float1": (23, 28),
    "ghost_float2": (24, 29),
    "ghost_lunge": (24, 30),
    "ghost_hurt": (17, 28),
    "ghost_dead": ((0, 19), (26, 31)),
}


def data_only_rows(name: str):
    r = DATA_ONLY_MASK_ROWS.get(name, ())
    return (r,) if r and isinstance(r[0], int) else r


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Frame:
    kind: str            # "sprite" | "item"
    character: str       # canvas heading, e.g. "GIANT RAT" / item label
    caption: str         # e.g. "WALK 2" (items: label)
    bitmap: np.ndarray   # H x W bool, True = ink
    ink_hex: str
    d: str = ""          # the canvas path string, verbatim (round-trip check)
    # derived
    name: str = ""
    solid: np.ndarray | None = None
    anchor: tuple[int, int] = (0, 0)
    pad_top: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def h(self) -> int:
        return self.bitmap.shape[0]

    @property
    def w(self) -> int:
        return self.bitmap.shape[1]


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


# ---------------------------------------------------------------------------
# SVG path <-> bitmap (the canvas convention)
# ---------------------------------------------------------------------------

RUN_RE = re.compile(r"M(\d+) (\d+)h(\d+)v1h-(\d+)z")


def path_to_bitmap(d: str, w: int, h: int) -> np.ndarray:
    """Strictly decode a run path; any deviation from the convention is fatal."""
    bm = np.zeros((h, w), dtype=bool)
    pos = 0
    for m in RUN_RE.finditer(d):
        if m.start() != pos:
            raise ValueError(f"unparseable path text at {pos}: {d[pos:pos + 40]!r}")
        pos = m.end()
        x, y, n, back = map(int, m.groups())
        if n != back or n == 0:
            raise ValueError(f"run M{x} {y}: h{n} closes with h-{back}")
        if x + n > w or y >= h:
            raise ValueError(f"run M{x} {y}h{n} outside {w}x{h}")
        if bm[y, x:x + n].any():
            raise ValueError(f"run M{x} {y}h{n} overlaps an earlier run")
        bm[y, x:x + n] = True
    if pos != len(d):
        raise ValueError(f"trailing path text: {d[pos:pos + 40]!r}")
    return bm


def bitmap_to_path(bm: np.ndarray) -> str:
    """Canonical encoding: rows top-down, maximal runs left-to-right."""
    out = []
    for y, row in enumerate(bm):
        x = 0
        w = len(row)
        while x < w:
            if row[x]:
                s = x
                while x < w and row[x]:
                    x += 1
                out.append(f"M{s} {y}h{x - s}v1h-{x - s}z")
            else:
                x += 1
    return "".join(out)


def grid_path(w: int, h: int) -> str:
    v = "".join(f"M{x} 0V{h}" for x in range(8, w, 8))
    hh = "".join(f"M0 {y}H{w}" for y in range(8, h, 8))
    return v + hh


def bitmap_to_svg(bm: np.ndarray, ink_hex: str, scale: int = 3) -> str:
    h, w = bm.shape
    gp = grid_path(w, h)
    grid = (f'<path d="{gp}" stroke="{GRID_STROKE}" stroke-width="0.12" fill="none"></path>'
            if gp else "")
    return (f'<svg width="{w * scale}" height="{h * scale}" viewBox="0 0 {w} {h}" '
            f'shape-rendering="crispEdges" style="display: block;">'
            f'<rect width="{w}" height="{h}" fill="#000000"></rect>{grid}'
            f'<path d="{bitmap_to_path(bm)}" fill="{ink_hex}"></path></svg>')


def svg_artboard_html(bm: np.ndarray, ink_hex: str, caption: str) -> str:
    """One frame cell exactly as the canvas lays it out (svg + caption div)."""
    h, w = bm.shape
    cap = html.escape(f"{caption} · {w}×{h}")
    return ('<div style="display: flex; flex-direction: column; gap: 8px; align-items: flex-start;">\n'
            '<div style="padding: 8px; background: #000000; border: 2px solid #26263a;">'
            f'{bitmap_to_svg(bm, ink_hex)}</div>\n'
            f'<div style="font-size: 11px; letter-spacing: 1px; color: #a9a7b8;">{cap}</div>\n</div>')


# ---------------------------------------------------------------------------
# Sheet parsing
# ---------------------------------------------------------------------------

TOKEN_RE = re.compile(
    r"(?P<svg><svg\b[^>]*viewBox=\"0 0 (?P<w>\d+) (?P<h>\d+)\"[^>]*>(?P<body>.*?)</svg>)"
    r"|<h2\b[^>]*>(?P<h2>[^<]*)</h2>"
    r"|<div\b(?P<dattr>[^>]*)>(?P<dtext>[^<]+)</div>",
    re.S,
)
CAPTION_RE = re.compile(r"^(.+?) · (\d+)×(\d+)$")


def parse_svg_body(body: str, w: int, h: int):
    """-> (ink_hex, d, bitmap) for a single-ink sprite svg; ValueError otherwise."""
    paths = re.findall(r"<path\b([^>]*)>", body)
    rects = re.findall(r"<rect\b([^>]*)>", body)
    if len(rects) != 1 or 'fill="#000000"' not in rects[0]:
        raise ValueError("expected exactly one black background rect")
    fills = []
    for attrs in paths:
        if "stroke=" in attrs:
            continue  # cell grid overlay: presentation only
        m = re.search(r'd="([^"]*)"', attrs)
        f = re.search(r'fill="(#[0-9A-Fa-f]{6})"', attrs)
        if not (m and f):
            raise ValueError(f"path without d/fill: {attrs[:60]}")
        fills.append((f.group(1).upper(), m.group(1)))
    if len(fills) != 1:
        raise ValueError(f"expected ONE ink path, found {len(fills)}")
    ink, d = fills[0]
    if ink not in INK_MAP:
        raise ValueError(f"unknown ink {ink}: add it to INK_MAP deliberately")
    return ink, d, path_to_bitmap(d, w, h)


def parse_sheet(path: str):
    """-> (frames, mock) where mock = (w, h, [(hex, d), ...]) or None."""
    text = open(path, encoding="utf-8").read()
    frames: list[Frame] = []
    mock = None
    section = None
    character = None
    pending: list[tuple] = []   # svg waiting for its caption/label
    for m in TOKEN_RE.finditer(text):
        if m.group("h2") is not None:
            section = m.group("h2").strip().upper()
            continue
        if m.group("svg"):
            w, h = int(m.group("w")), int(m.group("h"))
            if section == "IN-GAME MOCK" or (w, h) == (256, 192):
                runs = re.findall(r'<path d="([^"]*)" fill="(#[0-9A-Fa-f]{6})"', m.group("body"))
                mock = (w, h, [(c.upper(), d) for d, c in runs])
                continue
            if pending:
                raise ValueError(f"svg {pending[0][0]}x{pending[0][1]} has no caption")
            ink, d, bm = parse_svg_body(m.group("body"), w, h)
            pending.append((w, h, ink, d, bm))
            continue
        attrs, dtext = m.group("dattr"), html.unescape(m.group("dtext").strip())
        if not dtext:
            continue
        press = "Press Start 2P" in attrs
        if press and "font-size: 13px" in attrs:
            character = dtext.upper()
            if character not in CHAR_PREFIX:
                raise ValueError(f"unknown character heading {character!r}: add to CHAR_PREFIX")
            continue
        if not pending:
            continue
        w, h, ink, d, bm = pending[0]
        if section == "ITEMS":
            if press and "font-size: 10px" in attrs:
                frames.append(Frame("item", dtext.upper(), dtext.upper(), bm, ink, d))
                pending.clear()
            continue
        if section in TILE_SECTIONS:
            if press and "font-size: 10px" in attrs:
                if (w, h) != (8, 8):
                    raise ValueError(f"tile {dtext!r} must be 8x8, is {w}x{h}")
                frames.append(Frame("tile", section, dtext.upper(), bm, ink, d))
                pending.clear()
            continue
        cm = CAPTION_RE.match(dtext)
        if cm:
            if (int(cm.group(2)), int(cm.group(3))) != (w, h):
                raise ValueError(f"caption {dtext!r} disagrees with viewBox {w}x{h}")
            if character is None:
                raise ValueError(f"frame {dtext!r} before any character heading")
            frames.append(Frame("sprite", character, cm.group(1).upper(), bm, ink, d))
            pending.clear()
    if pending:
        raise ValueError("trailing svg without caption")
    frames = [f for f in frames if f.character not in EXCLUDE_CHARS]
    return frames, mock


# ---------------------------------------------------------------------------
# Mask + anchor
# ---------------------------------------------------------------------------

def filled_silhouette(bm: np.ndarray) -> np.ndarray:
    """Ink + every paper pixel NOT 4-connected to the frame border.

    Negative-space detail (eye slits, belt lines, robe folds) is enclosed paper;
    it must stay OPAQUE or the background shows through the character. Paper
    reachable from outside (gaps between legs, under an arm) stays transparent.
    4-connectivity so a diagonal ink step does not leak the outside in.
    """
    h, w = bm.shape
    outside = np.zeros_like(bm)
    stack = [(y, x) for y in range(h) for x in (0, w - 1) if not bm[y, x]]
    stack += [(y, x) for x in range(w) for y in (0, h - 1) if not bm[y, x]]
    while stack:
        y, x = stack.pop()
        if outside[y, x] or bm[y, x]:
            continue
        outside[y, x] = True
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not outside[ny, nx] and not bm[ny, nx]:
                stack.append((ny, nx))
    return ~outside


def repad(bm: np.ndarray, dx: int) -> np.ndarray:
    """Shift the art dx px inside the same box; only blank columns may leave."""
    w = bm.shape[1]
    gone = bm[:, w - dx:] if dx > 0 else bm[:, :-dx] if dx < 0 else bm[:, :0]
    if gone.any():
        raise ValueError(f"repad {dx:+d} would cut ink off the frame")
    return np.roll(bm, dx, axis=1)


def dilate8(m: np.ndarray) -> np.ndarray:
    """1-px 8-neighbour dilation, clipped to the frame box."""
    p = np.pad(m, 1)
    out = np.zeros_like(m)
    h, w = m.shape
    for dy in range(3):
        for dx in range(3):
            out |= p[dy:dy + h, dx:dx + w]
    return out


def make_mask(bm: np.ndarray, outline: bool, name: str = "") -> np.ndarray:
    sil = filled_silhouette(bm)
    m = dilate8(sil) if outline else sil
    for y0, y1 in data_only_rows(name):
        m[y0:y1] = bm[y0:y1]          # §5.4 dither exception: see-through
    return m


def best_anchor(ref: np.ndarray, frm: np.ndarray) -> tuple[int, int, float, float]:
    """(ax, ay, iou, iou_at_0) aligning `frm` to the character's reference frame.

    ax = px the frame's left edge sits LEFT of the reference's left edge
    (draw_x = body_x - ax); ay likewise vertically, frames bottom-aligned
    (feet on the floor line), so ay = frame_h - ref_h.

    * Same box as the reference (walk cycles, idles, same-size poses): ax = 0.
      The canvas draws those in register; "correcting" them per frame would
      turn leg/cloak motion into body jitter.
    * Wider/taller frames: best IoU of the filled silhouettes over the HEAD
      band (top 30% of the reference height). Measured on this sheet, the
      lower body is the worst reference — attack poses switch to a lunge stance
      (knight legs score ax=8, torso 0, head 4; the head is visibly 4 px right
      in the 40-px frames). The head/helmet is what the eye tracks.
      Ties -> smallest |ax|.
    """
    rs, fs = filled_silhouette(ref), filled_silhouette(frm)
    rh, rw = ref.shape
    fh, fw = frm.shape
    ay = fh - rh
    band = max(4, int(round(rh * 0.3)))
    a0 = rs[:band]
    b0 = fs[ay:ay + band] if ay >= 0 else np.pad(fs, ((-ay, 0), (0, 0)))[:band]
    results = []
    o = rw + fw + 8
    W = 2 * o + fw
    for ax in range(-(rw + 4), fw + 4):
        a = np.zeros((band, W), bool)
        b = np.zeros((band, W), bool)
        a[:, o:o + rw] = a0
        b[:, o - ax:o - ax + fw] = b0
        u = (a | b).sum()
        results.append((ax, (a & b).sum() / u if u else 0.0))
    iou0 = dict(results)[0]
    if frm.shape == ref.shape:
        return 0, 0, iou0, iou0
    best = max(results, key=lambda t: (round(t[1], 6), -abs(t[0])))
    return best[0], ay, best[1], iou0


# ---------------------------------------------------------------------------
# Grid I/O (gfx_convert 3-state text grid)
# ---------------------------------------------------------------------------

def grid_text(fr: Frame) -> str:
    h, w = fr.bitmap.shape
    lines = [
        "# WazHack/ZX gfx text grid — generated by tools/svg_sprites.py; the canvas is the source.",
        f"# name: {fr.name}",
        f"# size: {w}x{h}",
        f"# character: {fr.character}",
        f"# caption: {fr.caption}",
        f"# ink: {fr.ink_hex}",
        f"# anchor: {fr.anchor[0]} {fr.anchor[1]}",
        "# legend: '#' ink, '+' opaque paper (mask 0, data 0), '.' transparent",
        "#",
    ]
    for y in range(h):
        row = []
        for x in range(w):
            row.append("#" if fr.bitmap[y, x] else "+" if fr.solid[y, x] else ".")
        lines.append("".join(row))
    return "\n".join(lines) + "\n"


def read_grid(path: str):
    """-> (bitmap, meta dict) from a 2- or 3-state grid (ink = '#')."""
    text = open(path).read()
    fg, _solid, _w, _h = gfx_convert.parse_grid_text_mask(text, None, None)
    meta = {}
    for line in text.splitlines():
        m = re.match(r"#\s*(name|character|caption|ink|anchor):\s*(.*)$", line)
        if m:
            meta[m.group(1)] = m.group(2).strip()
    return fg, meta


# ---------------------------------------------------------------------------
# Ladder tiles (authored here: the canvas has none)
# ---------------------------------------------------------------------------

LADDER_GRID = """\
# WazHack/ZX ladder tiles — authored in tools/svg_sprites.py (LADDER_GRID).
# Sheet style: one ink on black paper. Dim yellow (INK 6, no BRIGHT) = wood,
# distinct from the cyan pillar/doorway and white-on-blue floor, and non-bright
# so the bright sprites stay on top visually (canvas mock: scenery is dim).
# Rails at x=1 and x=6 (one px in from each edge so stacked/adjacent cells keep
# a black gap from walls); rungs every 4 px so a 48-px climber always overlaps
# 12 rungs and the pattern tiles seamlessly vertically.
# ladder_top replaces the FLOOR cell the ladder passes through: its row 0 is a
# full-width tread continuing the floor's own top surface line (bg floor row 0
# is $FF), so the walkable line is unbroken and the hole reads as an opening.
=== ladder ink:yellow paper:black
.#....#.
.######.
.#....#.
.#....#.
.#....#.
.######.
.#....#.
.#....#.

=== ladder_top ink:yellow paper:black
########
.#....#.
.#....#.
.#....#.
.#....#.
.######.
.#....#.
.#....#.
"""


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def run_gfx(argv: list[str]) -> None:
    rc = gfx_convert.main(argv)
    if rc != 0:
        raise SystemExit(f"gfx_convert failed ({rc}): {' '.join(argv)}")


def decode_asm(path: str):
    """Parse DEFB bytes of the emitted asm (end-to-end, independent of packer)."""
    rows, attr = [], None
    in_attr = False
    for line in open(path):
        s = line.split(";")[0].strip()
        if s.endswith("_attr:"):
            in_attr = True
            continue
        if s.startswith("DEFB"):
            bs = [int(b.strip()[1:], 16) for b in s[4:].split(",")]
            if in_attr:
                attr = bs[0]
            else:
                rows.append(bs)
    return rows, attr


def assign_names(frames: list[Frame]) -> None:
    for fr in frames:
        if fr.kind == "item":
            fr.name = f"item_{slug(fr.caption)}"
        else:
            fr.name = f"{CHAR_PREFIX[fr.character]}_{slug(fr.caption)}"
    names = [f.name for f in frames]
    dup = {n for n in names if names.count(n) > 1}
    if dup:
        raise ValueError(f"duplicate frame names: {sorted(dup)}")


def reference_frame(frames: list[Frame]) -> Frame:
    """IDLE / IDLE 1 if present, else the first frame of the character."""
    for fr in frames:
        if fr.caption in ("IDLE", "IDLE 1"):
            return fr
    return frames[0]


def prepare(frames: list[Frame]) -> None:
    assign_names(frames)
    by_char: dict[str, list[Frame]] = {}
    for fr in frames:
        if fr.kind == "sprite":
            by_char.setdefault(fr.character, []).append(fr)
    for fr in frames:
        if fr.name in REPAD:
            fr.bitmap = repad(fr.bitmap, REPAD[fr.name])
            fr.extra["repad"] = REPAD[fr.name]
    for chars in by_char.values():
        ref = reference_frame(chars)
        for fr in chars:
            ax, ay, iou, iou0 = best_anchor(ref.bitmap, fr.bitmap)
            if fr.name in ANCHOR_X:
                ax, iou = ANCHOR_X[fr.name], float("nan")
                fr.extra["declared"] = True
            fr.anchor = (ax, ay)
            fr.extra.update(ref=ref.name, iou=iou, iou0=iou0)
            check_anchor(fr)
    for fr in frames:
        if fr.kind == "item" and fr.h % 8:
            # pad to whole cells at the TOP: the item keeps sitting on the floor
            fr.pad_top = 8 - fr.h % 8
            fr.bitmap = np.pad(fr.bitmap, ((fr.pad_top, 0), (0, 0)))
            fr.anchor = (0, fr.pad_top)
        fr.solid = make_mask(fr.bitmap, OUTLINE, fr.name)


def check_anchor(fr: Frame) -> None:
    """prototype.md §5.3: W % 8 == 0, ax % 4 == 0, 0 <= ax <= 8 (back overhang
    <= 1 cell), 0 <= ax_L = W - ax - body_w <= 16 (forward overhang <= 2)."""
    body = BODY_W[CHAR_PREFIX[fr.character]]
    ax = fr.anchor[0]
    ax_l = fr.w - ax - body
    fr.extra["ax_l"] = ax_l
    bad = []
    if fr.w % 8:
        bad.append(f"W={fr.w} not a multiple of 8")
    if ax % 4:
        bad.append(f"ax={ax} not a multiple of 4 (re-pad the frame: REPAD)")
    if not 0 <= ax <= 8:
        bad.append(f"ax={ax} outside 0..8")
    if not 0 <= ax_l <= 16:
        bad.append(f"ax_L={ax_l} outside 0..16")
    if bad:
        raise SystemExit(f"{fr.name}: §5.3 anchor rule: " + "; ".join(bad))


def frame_flags(name: str) -> int:
    return ((FLAG_MOTION if name in MOTION_FRAMES else 0)
            | (FLAG_SYMMETRIC if name in SYMMETRIC_FRAMES else 0))


def merge_drafts(frames: list[Frame], drafts: list[str]) -> list[Frame]:
    """Append draft-sheet frames after their character's canvas frames (stable
    indices). Identical duplicates (already pasted on the canvas) are skipped;
    differing duplicates are fatal."""
    canvas = {(f.character, f.caption): f for f in frames}
    out = list(frames)
    for path in drafts:
        if not os.path.exists(path):
            continue
        dframes, _ = parse_sheet(path)
        for d in dframes:
            key = (d.character, d.caption)
            if key in canvas:
                if not np.array_equal(canvas[key].bitmap, d.bitmap):
                    raise SystemExit(f"draft {os.path.basename(path)}: {key} differs from the canvas")
                continue
            d.extra["draft"] = os.path.relpath(path, REPO)
            if d.kind == "sprite":
                last = max((i for i, f in enumerate(out)
                            if f.kind == "sprite" and f.character == d.character), default=None)
                if last is None:
                    raise SystemExit(f"draft frame {key}: character has no canvas frames")
                out.insert(last + 1, d)
            else:
                out.append(d)
            canvas[key] = d
    return out


def import_sheet(sheet: str, out_dir: str, gen_date: str | None,
                 drafts: list[str] | None = None) -> list[Frame]:
    frames, mock = parse_sheet(sheet)
    frames = merge_drafts(frames, DRAFT_SHEETS if drafts is None else drafts)
    tiles = [f for f in frames if f.kind == "tile"]
    frames = [f for f in frames if f.kind != "tile"]
    prepare(frames)
    grid_dir = os.path.join(out_dir, "grid")
    os.makedirs(grid_dir, exist_ok=True)
    rel_sheet = os.path.relpath(sheet, REPO)
    for fr in frames:
        gpath = os.path.join(grid_dir, fr.name + ".grid")
        with open(gpath, "w") as f:
            f.write(grid_text(fr))
        colour, bright = INK_MAP[fr.ink_hex]
        src_note = ([f"DRAFT (not yet on the canvas): {fr.extra['draft']}",
                     "generated by " + DRAFT_GEN.get(fr.extra["draft"],
                                                     "tools/gen_missing_frames.py")]
                    if "draft" in fr.extra
                    else [f"canvas {ARTIFACT_URL}", f"vendored as {rel_sheet}"])
        notes = src_note + [
                 f"artboard: {fr.character} / {fr.caption} ({fr.bitmap.shape[1]}x"
                 f"{fr.h - fr.pad_top}), ink {fr.ink_hex}",
                 f"grid: {os.path.relpath(gpath, REPO)} (via tools/svg_sprites.py)"]
        if fr.pad_top:
            notes.append(f"padded {fr.pad_top} transparent rows on top to whole cells")
        if fr.kind == "sprite":
            if fr.extra.get("declared"):
                notes.append(f"anchor declared (prototype.md §10.2, svg_sprites ANCHOR_X); "
                             f"ax_L={fr.extra['ax_l']}")
            else:
                notes.append(f"anchor reference: {fr.extra['ref']} (head-band IoU "
                             f"{fr.extra['iou']:.2f}); ax_L={fr.extra['ax_l']}")
            if "repad" in fr.extra:
                notes.append(f"re-padded {fr.extra['repad']:+d} px inside the frame "
                             "(§10.3; pixels unchanged)")
            if data_only_rows(fr.name):
                notes.append("data-only mask rows (§5.4 dither exception): "
                             + ", ".join(f"{a}..{b - 1}" for a, b in data_only_rows(fr.name)))
            notes.append("class: " + ("MOTION" if fr.name in MOTION_FRAMES else "STATIONARY")
                         + (", SYMMETRIC" if fr.name in SYMMETRIC_FRAMES else ""))
        argv = ["--mode", "sprite", "--layout", "native", "--in", os.path.relpath(gpath, REPO),
                "--name", fr.name, "--out", os.path.join(out_dir, fr.name + ".asm"),
                "--ink", gfx_convert.COL_NAME[colour], "--paper", "black",
                "--band-paper", "black", "--anchor-x", str(fr.anchor[0]),
                "--anchor-y", str(fr.anchor[1]), "--src-path"]
        for n in notes:
            argv += ["--note", n]
        if bright:
            argv.append("--bright")
        if gen_date:
            argv += ["--date", gen_date]
        cwd = os.getcwd()
        os.chdir(REPO)
        try:
            _quiet(run_gfx, argv)
        finally:
            os.chdir(cwd)
        validate(fr, os.path.join(out_dir, fr.name + ".asm"))
    # ladder tiles
    lgrid = os.path.join(out_dir, "grid", "tiles_ladder.grid")
    with open(lgrid, "w") as f:
        f.write(LADDER_GRID)
    cwd = os.getcwd()
    os.chdir(REPO)
    try:
        argv = ["--mode", "tile", "--in", os.path.relpath(lgrid, REPO), "--src-path",
                "--name", "tiles_ladder", "--out", os.path.relpath(
                    os.path.join(out_dir, "tiles_ladder.asm"), REPO),
                "--note", "authored in tools/svg_sprites.py LADDER_GRID (canvas has none)",
                "--use", "draw_cell: ladder (air cells) / ladder_top (replaces the floor "
                         "cell the ladder passes through)"]
        if gen_date:
            argv += ["--date", gen_date]
        _quiet(run_gfx, argv)
    finally:
        os.chdir(cwd)
    tile_sets = import_tiles(tiles, out_dir, gen_date)
    write_index(frames, out_dir, rel_sheet, gen_date, tile_sets)
    contact_sheet(frames + tiles, os.path.join(out_dir, "contact_sheet.png"), lgrid)
    if mock:
        render_mock(mock, os.path.join(REPO, "assets/gfx/source/wazhack_mock_256x192.png"))
    return frames + tiles


def import_tiles(tiles: list[Frame], out_dir: str, gen_date) -> list[str]:
    """Canvas TILE sections -> one tileset asm per section (gfx_convert tile
    mode). Glyph from the canvas; attribute from TILE_ATTR (the canvas cannot
    express a non-black paper). The canvas ink colour must equal the attr ink."""
    sets: dict[str, list[Frame]] = {}
    for t in tiles:
        t.name = re.sub(r"[^a-z0-9_]", "", t.caption.lower().replace(" ", "_"))
        t.solid = np.ones_like(t.bitmap)
        t.extra["bytes"] = 9
        sets.setdefault(TILE_SECTIONS[t.character], []).append(t)
    for set_name, ts in sets.items():
        L = [f"# WazHack/ZX {set_name} — generated by tools/svg_sprites.py from the "
             f"canvas/draft {ts[0].character} section; do not hand-edit.",
             "# attr per tile from svg_sprites.TILE_ATTR (prototype.md §4.1/§10.2)."]
        for t in ts:
            if t.name not in TILE_ATTR:
                raise SystemExit(f"tile {t.name}: no TILE_ATTR entry (declare it deliberately)")
            a = TILE_ATTR[t.name]
            ink, paper, bright = a & 7, (a >> 3) & 7, bool(a & 0x40)
            if INK_MAP[t.ink_hex][0] != ink:
                raise SystemExit(f"tile {t.name}: canvas ink {t.ink_hex} != attr ink {ink}")
            L.append(f"=== {t.name} ink:{gfx_convert.COL_NAME[ink]} "
                     f"paper:{gfx_convert.COL_NAME[paper]}" + (" bright" if bright else ""))
            L += ["".join("#" if v else "." for v in row) for row in t.bitmap]
            L.append("")
        gpath = os.path.join(out_dir, "grid", set_name + ".grid")
        with open(gpath, "w") as f:
            f.write("\n".join(L))
        argv = ["--mode", "tile", "--in", os.path.relpath(gpath, REPO), "--src-path",
                "--name", set_name, "--out", os.path.relpath(
                    os.path.join(out_dir, set_name + ".asm"), REPO),
                "--note", ("DRAFT: " + ts[0].extra["draft"]) if "draft" in ts[0].extra
                else f"canvas {ARTIFACT_URL}",
                "--use", TILE_USE.get(set_name, "draw_cell")]
        if gen_date:
            argv += ["--date", gen_date]
        cwd = os.getcwd()
        os.chdir(REPO)
        try:
            _quiet(run_gfx, argv)
        finally:
            os.chdir(cwd)
        # round-trip: decode the emitted DEFB bytes back to the canvas glyphs
        parsed = gfx_convert.parse_tile_file(open(gpath).read())
        text = open(os.path.join(out_dir, set_name + ".asm")).read()
        for t, pt in zip(ts, parsed):
            m = re.search(rf"^{set_name}_{t.name}:\n\s+DEFB ([^;]+)", text, re.M)
            bs = [int(x.strip()[1:], 16) for x in m.group(1).split(",")]
            dec = np.array([[bool(b & (0x80 >> x)) for x in range(8)] for b in bs])
            if not np.array_equal(dec, t.bitmap) or pt["attr"] != TILE_ATTR[t.name]:
                raise SystemExit(f"tile {t.name}: round-trip mismatch")
    return list(sets)


TILE_USE = {
    "tiles_fx": "Wizard CAST2 bolt: ZAP1/ZAP2 alternate per tick in the gap cells on the "
                "staff row (body cell row 2; bolt joins on in-cell row 5 = frame row 21, CAST2 staff hand)",
    "tiles_bg": "PROTO room tiles via draw_cell (prototype.md §3.3/§4.1)",
}


def _quiet(fn, *a):
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a)


def validate(fr: Frame, asm_path: str) -> None:
    """Clash + end-to-end round trip from the emitted DEFB text."""
    rows, attr = decode_asm(asm_path)
    fg, solid = gfx_convert.unpack_sprite_mask(rows, fr.w, "native")
    if not np.array_equal(fg, fr.bitmap):
        raise SystemExit(f"{fr.name}: round-trip data != source bitmap")
    if not np.array_equal(solid, fr.solid):
        raise SystemExit(f"{fr.name}: round-trip mask != derived mask")
    colour, bright = INK_MAP[fr.ink_hex]
    if attr != gfx_convert.attr_byte(colour, 0, bright):
        raise SystemExit(f"{fr.name}: descriptor ${attr:02X} != ink {fr.ink_hex} on black")
    # Clash: every 8x8 cell holds at most {ink, black paper} -> one attribute.
    h, w = fr.bitmap.shape
    if h % 8 or w % 8:
        raise SystemExit(f"{fr.name}: {w}x{h} is not whole cells")
    for cy in range(0, h, 8):
        for cx in range(0, w, 8):
            cols = {0}
            if fr.bitmap[cy:cy + 8, cx:cx + 8].any():
                cols.add(colour)
            assert len(cols) <= 2, f"{fr.name}: cell {cx // 8},{cy // 8} clashes"
    fr.extra["bytes"] = sum(len(r) for r in rows) + 1


# ---------------------------------------------------------------------------
# index.asm
# ---------------------------------------------------------------------------

def write_index(frames: list[Frame], out_dir: str, rel_sheet: str, gen_date,
                tile_sets: list[str] = ()) -> None:
    from datetime import date
    L = [
        "; ============================================================================",
        "; sprites/index.asm — WazHack/ZX canvas sprite set (heroes, monsters, items)",
        f"; Generated by tools/svg_sprites.py on {gen_date or date.today().isoformat()}",
        f"; Source        : {rel_sheet}",
        f";                 canvas {ARTIFACT_URL}",
        "; Frame format  : native masked sprite, H rows x [mask,data] x (W/8) cols,",
        ";                 MSB=left, mask 1 = transparent; +1 ATTR_SPRITE byte.",
        "; Tables        : <char>_frames = DEFW frame pointers in canvas order",
        ";                 <char>_meta   = DEFB cols, h, ax, ay per frame (same order)",
        ";                 ax/ay: draw_x = body_x - ax, draw_y = body_y - ay",
        ";                 (right-facing; body origin = the character's reference",
        ";                 frame's top-left, see each frame header).",
        ";                 <char>_flags  = DEFB per frame: bit0 MOTION (store both",
        ";                 pre-shifts), bit1 SYMMETRIC (skip the left mirror)",
        ";                 (prototype.md §5.1/§5.2). STATIONARY = no bit0.",
        "; Order         : canvas order per character; frames added later (draft",
        ";                 sheets) are APPENDED, so existing indices never move.",
        "; Bytes         : unshifted, masked; engine pre-shifts at boot / offline.",
        "; ============================================================================",
        "",
    ]
    for fr in frames:
        L.append(f'        INCLUDE "{fr.name}.asm"')
    L.append('        INCLUDE "tiles_ladder.asm"')
    for ts in tile_sets:
        L.append(f'        INCLUDE "{ts}.asm"')
    L.append("")
    L.append("FRAME_F_MOTION    EQU %d" % FLAG_MOTION)
    L.append("FRAME_F_SYMMETRIC EQU %d" % FLAG_SYMMETRIC)
    L.append("")
    groups: dict[str, list[Frame]] = {}
    for fr in frames:
        key = CHAR_PREFIX[fr.character] if fr.kind == "sprite" else "item"
        groups.setdefault(key, []).append(fr)
    grand = 0
    for key, frs in groups.items():
        total = sum(f.extra["bytes"] for f in frs)
        grand += total
        L.append(f"; ---- {key}: {len(frs)} frames, {total} bytes")
        L.append(f"{key}_frames:")
        for f in frs:
            L.append(f"        DEFW {f.name}")
        L.append(f"{key}_meta:")
        for f in frs:
            L.append(f"        DEFB {f.w // 8},{f.h},{f.anchor[0]},{f.anchor[1]}"
                     f"        ; {f.name:22s} {f.w}x{f.h}")
        for i, f in enumerate(frs):
            L.append(f"{f.name.upper()}_IDX EQU {i}")
        L.append(f"{key}_flags:")
        L.append("        DEFB " + ",".join(str(frame_flags(f.name)) for f in frs))
        L.append(f"{key}_frame_count EQU {len(frs)}")
        L.append(f"{key}_bytes       EQU " + " + ".join(f"{f.name}_len" for f in frs)
                 + f"   ; = {total}")
        L.append("")
    L.append(f"sprites_frame_count EQU {len(frames)}")
    L.append(f"sprites_total_bytes EQU " + " + ".join(f"{k}_bytes" for k in groups)
             + f"   ; = {grand} (unshifted, masked, incl. descriptors)")
    L.append("")
    with open(os.path.join(out_dir, "index.asm"), "w") as f:
        f.write("\n".join(L))


# ---------------------------------------------------------------------------
# Contact sheet + mock render
# ---------------------------------------------------------------------------

def spec_rgb(colour: int, bright: bool):
    return gfx_convert.colour_rgb(colour, bright)


def backdrop(w: int, h: int, ink_rgb) -> np.ndarray:
    """Busy background (brick courses) in the sprite's ink: attribute-follow means
    covered cells take the sprite ink, so this is the worst case for legibility."""
    bg = np.zeros((h, w), bool)
    for y in range(h):
        if y % 4 == 0:
            bg[y, :] = True
        else:
            off = 0 if (y // 4) % 2 else 4
            bg[y, off::8] = True
    rgb = np.zeros((h, w, 3), np.uint8)
    rgb[bg] = ink_rgb
    return rgb


def frame_panels(fr: Frame, scale: int) -> Image.Image:
    colour, bright = INK_MAP[fr.ink_hex]
    ink = spec_rgb(colour, bright)
    h, w = fr.bitmap.shape
    a = np.zeros((h, w, 3), np.uint8)
    a[fr.bitmap] = ink
    m = np.full((h, w, 3), (40, 40, 90), np.uint8)       # transparent = blue-grey
    m[fr.solid] = (0, 0, 0)                               # opaque paper = black
    m[fr.bitmap] = (255, 255, 255)                        # ink = white
    edge = fr.solid & ~filled_silhouette(fr.bitmap)
    m[edge] = (110, 110, 110)                             # outline ring = grey
    c = backdrop(w, h, ink)
    c[fr.solid] = (0, 0, 0)
    c[fr.bitmap] = ink
    gap = 2
    strip = np.zeros((h, w * 3 + gap * 2, 3), np.uint8)
    strip[:, :] = (24, 24, 36)
    for i, p in enumerate((a, m, c)):
        strip[:, i * (w + gap):i * (w + gap) + w] = p
    return Image.fromarray(strip).resize((strip.shape[1] * scale, h * scale), Image.NEAREST)


def contact_sheet(frames: list[Frame], path: str, ladder_grid: str, scale: int = 4) -> None:
    cells = []
    for fr in frames:
        img = frame_panels(fr, scale)
        label = f"{fr.name} {fr.w}x{fr.h} ax={fr.anchor[0]} ay={fr.anchor[1]}"
        cells.append((img, label))
    # ladder tiles: 3x6 stack of ladder with ladder_top in the floor row + floor
    tiles = gfx_convert.parse_tile_file(open(ladder_grid).read())
    bgt = gfx_convert.parse_tile_file(open(os.path.join(REPO, "assets/gfx/bg_tiles.grid")).read())
    tb = {t["name"]: t for t in tiles + bgt}
    layout = [["pillar", "blank", "blank", "ladder", "blank"],
              ["pillar", "blank", "blank", "ladder", "blank"],
              ["pillar", "blank", "blank", "ladder", "blank"],
              ["floor", "floor", "floor", "ladder_top", "floor"],
              ["ground", "ground", "ground", "ladder", "ground"]]
    lh, lw = len(layout) * 8, len(layout[0]) * 8
    lad = np.zeros((lh, lw, 3), np.uint8)
    for ty, row in enumerate(layout):
        for tx, nm in enumerate(row):
            t = tb[nm]
            ink = spec_rgb(t["ink"], t["bright"])
            pap = spec_rgb(t["paper"], t["bright"])
            for y in range(8):
                for x in range(8):
                    on = t["bitmap"][y] & (0x80 >> x)
                    lad[ty * 8 + y, tx * 8 + x] = ink if on else pap
    cells.append((Image.fromarray(lad).resize((lw * scale, lh * scale), Image.NEAREST),
                  "tiles_ladder (in bg_tiles context)"))
    pad, lab = 12, 14
    maxw = 1800
    x = y = pad
    rowh = 0
    places = []
    for img, label in cells:
        if x + img.width > maxw:
            x = pad
            y += rowh + lab + pad
            rowh = 0
        places.append((x, y, img, label))
        x += img.width + pad
        rowh = max(rowh, img.height)
    H = y + rowh + lab + pad + 20
    sheet = Image.new("RGB", (maxw, H), (16, 16, 24))
    dr = ImageDraw.Draw(sheet)
    dr.text((pad, H - 18), "panels: sprite | mask (white ink, black opaque, grey outline, "
            "blue transparent) | composite over worst-case same-ink bricks", fill=(170, 170, 190))
    for x, y, img, label in places:
        sheet.paste(img, (x, y + lab))
        dr.text((x, y), label, fill=(200, 200, 210))
    sheet.save(path)


def render_mock(mock, path: str, scale: int = 3) -> None:
    w, h, layers = mock
    rgb = np.zeros((h, w, 3), np.uint8)
    for hexc, d in layers:
        bm = path_to_bitmap(d, w, h)
        rgb[bm] = tuple(int(hexc[i:i + 2], 16) for i in (1, 3, 5))
    Image.fromarray(rgb).resize((w * scale, h * scale), Image.NEAREST).save(path)


# ---------------------------------------------------------------------------
# Export + round-trip
# ---------------------------------------------------------------------------

def cmd_export(args) -> int:
    parts = []
    for g in args.grid:
        bm, meta = read_grid(g)
        ink = args.ink or meta.get("ink")
        if not ink or ink.upper() not in INK_MAP:
            print(f"ERROR: {g}: ink {ink!r} not in INK_MAP (pass --ink #RRGGBB)", file=sys.stderr)
            return 2
        caption = args.caption or meta.get("caption") or os.path.splitext(os.path.basename(g))[0].upper()
        parts.append(svg_artboard_html(bm, ink.upper(), caption))
    out = "\n".join(parts) + "\n"
    if args.out:
        with open(args.out, "w") as f:
            f.write(out)
        print(f"wrote {args.out} ({len(parts)} artboards)")
    else:
        sys.stdout.write(out)
    return 0


def cmd_roundtrip(args) -> int:
    canvas, _ = parse_sheet(args.sheet)
    frames = merge_drafts(list(canvas), DRAFT_SHEETS)
    bad = 0
    for fr in frames:
        if fr.kind == "tile":
            snippet = bitmap_to_svg(fr.bitmap, fr.ink_hex)
            m = re.search(r'<path d="([^"]*)" fill', snippet)
            if path_to_bitmap(m.group(1), 8, 8).tolist() != fr.bitmap.tolist() or m.group(1) != fr.d:
                bad += 1
                print(f"MISMATCH tile {fr.caption}")
            continue
        snippet = svg_artboard_html(fr.bitmap, fr.ink_hex, fr.caption)
        m = TOKEN_RE.search(snippet)
        ink, d, bm = parse_svg_body(m.group("body"), int(m.group("w")), int(m.group("h")))
        ok = np.array_equal(bm, fr.bitmap) and ink == fr.ink_hex and d == fr.d
        # and the caption parses back
        cap = re.search(r">([^<]+ · \d+×\d+)<", snippet)
        ok = ok and cap and CAPTION_RE.match(html.unescape(cap.group(1))).group(1) == fr.caption
        if not ok:
            bad += 1
            print(f"MISMATCH {fr.character}/{fr.caption}")
    # grid route too: grid file -> export -> parse (undoing pad_top / REPAD)
    sprites = [f for f in frames if f.kind != "tile"]
    if os.path.isdir(os.path.join(OUT_DIR, "grid")):
        prepare(sprites)
        for fr in sprites:
            g = os.path.join(OUT_DIR, "grid", fr.name + ".grid")
            if not os.path.exists(g):
                bad += 1
                print(f"GRID MISSING {fr.name}")
                continue
            gbm, meta = read_grid(g)
            if fr.pad_top:
                gbm = gbm[fr.pad_top:]
            if "repad" in fr.extra:
                gbm = np.roll(gbm, -fr.extra["repad"], axis=1)
            if bitmap_to_path(gbm) != fr.d or meta.get("ink") != fr.ink_hex:
                bad += 1
                print(f"GRID MISMATCH {fr.name}")
    print(f"roundtrip: {len(frames)} frames ({len(frames) - len(canvas)} from draft sheets), "
          f"{bad} mismatches")
    return 1 if bad else 0


def cmd_import(args) -> int:
    frames = import_sheet(args.sheet, args.out_dir, args.date)
    print(f"{'frame':24s} {'w x h':>7s} {'bytes':>6s} {'ax':>4s} {'ay':>4s}  ref / IoU(best, at 0)")
    total = 0
    for fr in frames:
        b = fr.extra["bytes"]
        total += b
        if fr.kind == "sprite":
            ref = ("declared" if fr.extra.get("declared") else
                   f"{fr.extra['ref']} {fr.extra['iou']:.2f} {fr.extra['iou0']:.2f}")
            ref += f"  ax_L={fr.extra['ax_l']}" + ("  DRAFT" if "draft" in fr.extra else "")
            ref += f"  repad {fr.extra['repad']:+d}" if "repad" in fr.extra else ""
        else:
            ref = fr.kind
        print(f"{fr.name:24s} {fr.w:>3d}x{fr.h:<3d} {b:>6d} {fr.anchor[0]:>4d} "
              f"{fr.anchor[1]:>4d}  {ref}")
    print(f"TOTAL {len(frames)} frames, {total} bytes (unshifted, masked, incl. descriptors)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd")
    pi = sub.add_parser("import", help="canvas sheet -> grids -> asm (default)")
    pi.add_argument("--sheet", default=SHEET)
    pi.add_argument("--out-dir", default=OUT_DIR)
    pi.add_argument("--date", default=None, help="header date override")
    pe = sub.add_parser("export", help=".grid -> canvas SVG artboard HTML")
    pe.add_argument("grid", nargs="+")
    pe.add_argument("--ink", help="#RRGGBB (default: grid '# ink:' header)")
    pe.add_argument("--caption", help="caption name (default: grid '# caption:')")
    pe.add_argument("--out", help="write HTML fragment here (default stdout)")
    pr = sub.add_parser("roundtrip", help="import -> export -> import self-test")
    pr.add_argument("--sheet", default=SHEET)
    args = p.parse_args(argv)
    if args.cmd is None:
        args = p.parse_args(["import"] + (argv or sys.argv[1:]))
    return {"import": cmd_import, "export": cmd_export, "roundtrip": cmd_roundtrip}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
