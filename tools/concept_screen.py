#!/usr/bin/env python3
"""concept_screen.py — deterministic ZX Spectrum mock-ups of the screen CONCEPT.

Composes docs/design/concept-screen.md into real Spectrum screens (.scr, 6912 B,
loadable in Fuse/ZEsarUX) plus 3x PNG previews, a contact sheet of the new
draft art and an animated GIF of the animated decor + spell projectiles.

Nothing here is engine data: it is a review mock. Inputs are all text grids,
no AI raster:
  existing  assets/gfx/sprites/grid/{tiles_bg,item_torch,wizard_cast2,
            skeleton_walk2,goblin_walk1}.grid   (read-only)
  new draft assets/gfx/concept/grid/{decor,door,icons8}.tiles  (gfx_convert tile fmt)
            assets/gfx/concept/grid/icons16.grid, spells.grid  (block fmt, WxH)
  derived   assets/gfx/concept/grid/sprites/<spell>.grid  (3-state, F8 mask;
            packable by tools/gfx_convert.py --layout native)
Text uses the 48K ROM charset ($3D00), exactly as the game does (ROM_CHARSET);
the ROM is read from the local Fuse/ZEsarUX install (override: ZX_ROM48=path).

Sprites are composited exactly as the engine would: pre-masked
screen = (screen AND mask) OR data, then ATTR_SPRITE stamped on the frame's
cell footprint (F8/F9).

Usage:
  python3 tools/concept_screen.py            # build everything + validate
Exit status is non-zero if any validation fails.
"""

from __future__ import annotations

import os
import re
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gfx_convert  # noqa: E402  (tile parser, sprite packer)
import svg_sprites  # noqa: E402  (make_mask: the one mask rule)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPR = os.path.join(REPO, "assets/gfx/sprites/grid")
OUT = os.path.join(REPO, "assets/gfx/concept")
GRID = os.path.join(OUT, "grid")
SCALE = 3

ROM_CANDIDATES = [
    os.environ.get("ZX_ROM48", ""),
    "/Applications/Fuse for macOS/Fuse.app/Contents/Resources/48.rom",
    "/Applications/zesarux.app/Contents/Resources/48.rom",
    os.path.expanduser("~/zxspectrum/zx roms/48.rom"),
]
ROM_CHARSET = 0x3D00

# ---------------------------------------------------------------------------
# Attributes (named, prototype.md §4.1 + concept-screen.md)
# ---------------------------------------------------------------------------
BRIGHT, PAPER_BLUE = 0x40, 0x08
A_AIR, A_WALL, A_FLOOR, A_LADDER = 0x00, 0x01, 0x0F, 0x02
A_DOOR, A_TORCH = 0x06, 0x46
A_GREY, A_GREY_SEL = 0x07, 0x0F
A_MAGE, A_SKEL, A_GOB = 0x45, 0x47, 0x44


def sel(attr: int) -> int:
    """Selected (cursor) state: same ink + bright, PAPER blue (attr-only)."""
    return (attr & 0x47) | PAPER_BLUE


def rgb(idx: int, bright: bool) -> tuple[int, int, int]:
    """Spectrum palette: $D7 normal / $FF bright (same as the canvas INK_MAP)."""
    hi = 0xFF if bright else 0xD7
    return (hi if idx & 2 else 0, hi if idx & 4 else 0, hi if idx & 1 else 0)


def attr_rgb(a: int):
    b = bool(a & 0x40)
    return rgb(a & 7, b), rgb((a >> 3) & 7, b)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_font() -> dict[str, np.ndarray]:
    for p in ROM_CANDIDATES:
        if p and os.path.isfile(p):
            rom = open(p, "rb").read()
            break
    else:
        raise SystemExit("48K ROM not found (set ZX_ROM48=path/to/48.rom)")
    font = {}
    for c in range(32, 128):
        b = rom[ROM_CHARSET + (c - 32) * 8: ROM_CHARSET + (c - 31) * 8]
        font[chr(c)] = bytes_to_bm(b)
    return font


def bytes_to_bm(bs) -> np.ndarray:
    return np.array([[(v >> (7 - i)) & 1 for i in range(8)] for v in bs], bool)


HDR_RE = re.compile(r"^===\s*(\S+)(?:\s+(\d+)x(\d+))?(.*)$")


def parse_blocks(path: str) -> dict:
    """'=== name [WxH] ink:c paper:c [bright]' + H rows of W ('#'/'.').
    8x8 blocks without WxH are exactly gfx_convert tile format."""
    blocks, cur = {}, None
    for raw in open(path).read().splitlines():
        line = raw.strip()
        m = HDR_RE.match(line)
        if m:
            name, w, h, rest = m.group(1), int(m.group(2) or 8), int(m.group(3) or 8), m.group(4)
            ink = paper = 0
            bright = False
            cells, ax = None, 0
            for tok in rest.split():
                if tok.startswith("cells:"):
                    cells = np.array([[int(v, 16) for v in r.split(",")]
                                      for r in tok[6:].split(";")], np.uint8)
                    if cells.shape != (h // 8, w // 8):
                        raise SystemExit(f"{path}: {name}: cells map {cells.shape} != "
                                         f"{(h // 8, w // 8)}")
                    continue
                if tok.startswith("ax:"):
                    ax = int(tok[3:])
                    continue
                if tok.startswith("ink:"):
                    ink = gfx_convert.COLOURS[tok[4:]]
                elif tok.startswith("paper:"):
                    paper = gfx_convert.COLOURS[tok[6:]]
                elif tok == "bright":
                    bright = True
            if name in blocks:
                raise SystemExit(f"{path}: duplicate block {name}")
            cur = blocks[name] = {"name": name, "w": w, "h": h, "rows": [],
                                  "attr": gfx_convert.attr_byte(ink, paper, bright),
                                  "cells": cells, "ax": ax}
            continue
        if cur is not None and len(line) == cur["w"] and set(line) <= set("#."):
            if len(cur["rows"]) >= cur["h"]:
                raise SystemExit(f"{path}: {cur['name']} has more than {cur['h']} rows")
            cur["rows"].append([c == "#" for c in line])
            continue
        if line and not line.startswith("#"):
            raise SystemExit(f"{path}: unparsable line {raw!r}")
        if line.startswith("#") and cur is not None and len(line) == cur["w"] \
                and len(cur["rows"]) < cur["h"]:
            raise SystemExit(f"{path}: {cur['name']}: row {raw!r} has bad chars")
    for b in blocks.values():
        if len(b["rows"]) != b["h"]:
            raise SystemExit(f"{path}: {b['name']} has {len(b['rows'])} rows, want {b['h']}")
        b["bm"] = np.array(b["rows"], bool)
        del b["rows"]
    # 8x8 tile files must stay gfx_convert-compatible (and round-trip)
    if path.endswith(".tiles"):
        for t in gfx_convert.parse_tile_file(open(path).read()):
            if not np.array_equal(bytes_to_bm(t["bitmap"]), blocks[t["name"]]["bm"]) \
                    or t["attr"] != blocks[t["name"]]["attr"]:
                raise SystemExit(f"{path}: gfx_convert disagrees on {t['name']}")
    return blocks


def load_sprite(name: str, mirror: bool = False):
    fg, solid, _w, _h = gfx_convert.parse_grid_text_mask(
        open(os.path.join(SPR, name + ".grid")).read(), None, None)
    if mirror:
        fg, solid = fg[:, ::-1], solid[:, ::-1]
    return fg, solid


def derive_spell_grids(spells: dict, srcfile: str = "spells.grid",
                       character: str = "SPELL FX") -> dict:
    """<srcfile> (2-state) -> grid/sprites/<name>.grid (3-state F8 mask)."""
    d = os.path.join(GRID, "sprites")
    os.makedirs(d, exist_ok=True)
    out = {}
    for name, b in spells.items():
        bm = b["bm"]
        solid = svg_sprites.make_mask(bm, svg_sprites.OUTLINE, name)
        ink, paper = b["attr"] & 7, (b["attr"] >> 3) & 7
        hexink = svg_sprites.INK_HEX.get((ink, bool(b["attr"] & 0x40)), "?")
        lines = [
            "# WazHack/ZX gfx text grid — DERIVED by tools/concept_screen.py from",
            f"# assets/gfx/concept/grid/{srcfile} (edit that); CONCEPT draft, not on the canvas yet.",
            f"# name: {name}",
            f"# size: {b['w']}x{b['h']}",
            f"# character: {character}",
            f"# caption: {name.upper()}",
            f"# ink: {hexink}",
            f"# attr: ${b['attr']:02X} (ink {gfx_convert.COL_NAME[ink]}, paper "
            f"{gfx_convert.COL_NAME[paper]}, bright {int(bool(b['attr'] & 0x40))})",
            f"# anchor: {b.get('ax', 0)} 0",
            "# legend: '#' ink, '+' opaque paper (mask 0, data 0), '.' transparent",
            "#",
        ]
        for y in range(b["h"]):
            lines.append("".join("#" if bm[y, x] else "+" if solid[y, x] else "."
                                 for x in range(b["w"])))
        open(os.path.join(d, name + ".grid"), "w").write("\n".join(lines) + "\n")
        out[name] = (bm, solid, b["attr"])
    return out


# ---------------------------------------------------------------------------
# Screen model: 1-bit bitmap + 32x24 attrs, with an "intended colour" layer
# ---------------------------------------------------------------------------

class Screen:
    def __init__(self, rows: int = 24):
        self.rows = rows
        self.bm = np.zeros((rows * 8, 256), bool)
        self.attr = np.zeros((rows, 32), np.uint8)
        self.bg_attr = np.zeros((rows, 32), np.uint8)
        # intended ink attr of every set pixel (-1 = none): lets validation find
        # pixels the attribute grid cannot colour as intended (true clash)
        self.want = np.full((rows * 8, 256), -1, np.int16)
        self.sprite_px = np.zeros((rows * 8, 256), bool)
        self.sprites: list[dict] = []

    def glyph(self, col: int, row: int, bm: np.ndarray, attr: int):
        """Opaque cell-aligned glyph (tile / icon / text): sets bitmap + attrs."""
        h, w = bm.shape
        assert h % 8 == 0 and w % 8 == 0, (h, w)
        y, x = row * 8, col * 8
        self.bm[y:y + h, x:x + w] = bm
        self.want[y:y + h, x:x + w] = np.where(bm, attr & 0x47, -1)
        self.attr[row:row + h // 8, col:col + w // 8] = attr
        self.bg_attr[row:row + h // 8, col:col + w // 8] = attr

    def set_attr(self, col: int, row: int, attr: int, w: int = 1, h: int = 1):
        self.attr[row:row + h, col:col + w] = attr
        self.bg_attr[row:row + h, col:col + w] = attr
        sub = self.want[row * 8:(row + h) * 8, col * 8:(col + w) * 8]
        sub[sub >= 0] = attr & 0x47

    def text(self, col: int, row: int, s: str, attr: int, font):
        for i, ch in enumerate(s):
            self.glyph(col + i, row, font[ch], attr)

    def sprite(self, name: str, x: int, y: int, fg, solid, attr: int):
        """Engine composite: (scr AND mask) OR data, then stamp ATTR_SPRITE."""
        h, w = fg.shape
        reg = self.bm[y:y + h, x:x + w]
        reg &= ~solid
        reg |= fg
        wr = self.want[y:y + h, x:x + w]
        wr[solid] = -1
        wr[fg] = attr & 0x47
        self.sprite_px[y:y + h, x:x + w] |= fg
        c0, c1, r0, r1 = x // 8, (x + w - 1) // 8, y // 8, (y + h - 1) // 8
        cells = [(c, r) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)]
        self.sprites.append({"name": name, "attr": attr, "cells": cells,
                             "bg": {cr: int(self.bg_attr[cr[1], cr[0]]) for cr in cells}})
        for c, r in cells:
            self.attr[r, c] = attr

    # --- output ---------------------------------------------------------
    def to_scr(self) -> bytes:
        assert self.rows == 24
        out = bytearray(6912)
        for y in range(192):
            base = ((y & 0xC0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2)
            for xb in range(32):
                v = 0
                for i in range(8):
                    v = (v << 1) | int(self.bm[y, xb * 8 + i])
                out[base + xb] = v
        out[6144:] = self.attr.flatten().tobytes()
        return bytes(out)

    def rgb_image(self) -> np.ndarray:
        return render_rgb(self.bm, self.attr)


def render_rgb(bm: np.ndarray, attr: np.ndarray) -> np.ndarray:
    h, w = bm.shape
    img = np.zeros((h, w, 3), np.uint8)
    for r in range(h // 8):
        for c in range(w // 8):
            ink, paper = attr_rgb(int(attr[r, c]))
            cell = bm[r * 8:r * 8 + 8, c * 8:c * 8 + 8]
            img[r * 8:r * 8 + 8, c * 8:c * 8 + 8] = np.where(cell[..., None], ink, paper)
    return img


def decode_scr(data: bytes):
    assert len(data) == 6912
    bm = np.zeros((192, 256), bool)
    for y in range(192):
        base = ((y & 0xC0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2)
        for xb in range(32):
            v = data[base + xb]
            for i in range(8):
                bm[y, xb * 8 + i] = (v >> (7 - i)) & 1
    attr = np.frombuffer(data[6144:], np.uint8).reshape(24, 32)
    return bm, attr


def save_png(img: np.ndarray, path: str, scale: int = SCALE):
    Image.fromarray(img).resize((img.shape[1] * scale, img.shape[0] * scale),
                                Image.NEAREST).save(path)


# ---------------------------------------------------------------------------
# Asset bundle
# ---------------------------------------------------------------------------

class Art:
    def __init__(self):
        self.font = load_font()
        self.decor = parse_blocks(os.path.join(GRID, "decor.tiles"))
        self.door = parse_blocks(os.path.join(GRID, "door.tiles"))
        self.ic8 = parse_blocks(os.path.join(GRID, "icons8.tiles"))
        self.ic16 = parse_blocks(os.path.join(GRID, "icons16.grid"))
        self.spells_src = parse_blocks(os.path.join(GRID, "spells.grid"))
        self.spells = derive_spell_grids(self.spells_src)
        # --- round 2
        self.big = parse_blocks(os.path.join(GRID, "bigdecor.grid"))
        self.walls = parse_blocks(os.path.join(GRID, "walls.tiles"))
        self.ic16b = parse_blocks(os.path.join(GRID, "icons16_r2.grid"))
        self.ic24 = parse_blocks(os.path.join(GRID, "icons24.grid"))
        self.ic8b = parse_blocks(os.path.join(GRID, "icons8_r2.tiles"))
        self.proj_src = parse_blocks(os.path.join(GRID, "projectiles.grid"))
        self.proj = derive_spell_grids(self.proj_src, "projectiles.grid", "PROJECTILE FX")
        self.r2_src = parse_blocks(os.path.join(GRID, "r2_frames.grid"))
        self.r2 = derive_spell_grids(self.r2_src, "r2_frames.grid (from tools/concept_r2_frames.py)",
                                     "R2 FRAME")
        self.ax = {n: b["ax"] for n, b in self.r2_src.items()}
        # --- round 3 (frames with a round-2 name supersede the round-2 drafts)
        self.r3_src = parse_blocks(os.path.join(GRID, "r3_frames.grid"))
        r3 = derive_spell_grids(self.r3_src, "r3_frames.grid (from tools/concept_r3_frames.py)",
                                "R3 FRAME")
        self.r2.update(r3)
        self.r3_names = list(self.r3_src)
        self.ax.update({n: b["ax"] for n, b in self.r3_src.items()})
        self.walls3 = parse_blocks(os.path.join(GRID, "walls_r3.tiles"))
        for n in ("wizard_idle", "wizard_cast1", "skeleton_hurt", "skeleton_collapsed",
                  "goblin_walk1", "goblin_hurt", "knight_idle1", "knight_walk1", "knight_windup"):
            fg, so = load_sprite(n)
            self.r2.setdefault(n, (fg, so, {"wizard": A_MAGE, "skeleton": A_SKEL,
                                            "goblin": A_GOB, "knight": A_MAGE}[n.split("_")[0]]))
        # existing tiles (read-only): platform, ends, wall, ladder_l/m/r
        self.tiles = {t["name"]: bytes_to_bm(t["bitmap"]) for t in gfx_convert.parse_tile_file(
            open(os.path.join(SPR, "tiles_bg.grid")).read())}
        torch, _ = load_sprite("item_torch")         # 8x16, same glyphs init_tiles picks
        self.tiles["torch_t"], self.tiles["torch_b"] = torch[:8], torch[8:]
        self.mage = load_sprite("wizard_cast2")
        self.skel = load_sprite("skeleton_walk2")
        self.gob = load_sprite("goblin_walk1", mirror=True)   # facing left


def bar_cells(ncells: int, fill_px: int) -> np.ndarray:
    """Status bar bitmap (engine-drawn, not an asset): outline rows 1/6, end caps,
    fill rows 2-5 for the first fill_px pixels."""
    bm = np.zeros((8, ncells * 8), bool)
    bm[1, :] = bm[6, :] = True
    bm[1:7, 0] = bm[1:7, -1] = True
    bm[2:6, :fill_px] = True
    return bm


def put_bar(s: Screen, col: int, row: int, ncells: int, frac: float, attr: int) -> int:
    fill = int(round(frac * ncells * 8))
    bm = bar_cells(ncells, fill)
    for i in range(ncells):
        s.glyph(col + i, row, bm[:, i * 8:i * 8 + 8], attr)
    return fill


# ---------------------------------------------------------------------------
# Scene (concept-screen.md §3)
# ---------------------------------------------------------------------------

LAYOUT = {
    # storey-0 floor row, storey-1 floor row, door arch row, offset for storey-1 rows
    "v1": {"f0": 9, "f1": 19, "arch": 13, "s1": 0},
    "v2": {"f0": 10, "f1": 21, "arch": 15, "s1": 2},
}

HP, HP_MAX, MP, MP_MAX, HUNGER = 18, 22, 5, 12, 0.6
BAR_ICONS = [("staff", None), ("spark", None), ("firebolt", None), ("frost", None),
             ("lightning", None), ("apple", None), ("potion", 0x42), ("scroll", 0x47),
             ("bag", None)]
SELECTED, GREYED = 2, {4}          # Firebolt selected; Lightning (cost 6 > MP 5) greyed


def icon_state_attr(base: int, idx: int) -> int:
    if idx in GREYED:
        return A_GREY_SEL if idx == SELECTED else A_GREY
    return sel(base) if idx == SELECTED else base


def build_room(art: Art, lay: str) -> tuple[Screen, list[int]]:
    L = LAYOUT[lay]
    f0, f1, arch = L["f0"], L["f1"], L["arch"]
    s, T, D = Screen(), art.tiles, art.decor

    # storey 0: dead end cols 0-2, rubble, open exit col 31 (air)
    for r in range(f0):
        for c in range(3):
            s.glyph(c, r, T["wall"], A_WALL)
    # floor rows
    def floor_row(row, solid_cols, holes):
        for c in range(32):
            if c in solid_cols:
                s.glyph(c, row, T["wall"], A_FLOOR)
            elif c in holes:
                s.glyph(c, row, T[holes[c]], A_LADDER)
            else:
                left = (c - 1) in solid_cols or (c - 1) in holes
                right = (c + 1) in solid_cols or (c + 1) in holes
                s.glyph(c, row, T["platform_end_l" if left else "platform_end_r" if right
                                  else "platform"], A_FLOOR)
    ladder = {24: "ladder_l", 25: "ladder_m", 26: "ladder_r"}
    floor_row(f0, {0, 1, 2, 31}, ladder)
    floor_row(f1, {0, 31}, {})
    # storey 1: left edge, ladder, lintel + door
    for r in range(f0 + 1, f1):
        s.glyph(0, r, T["wall"], A_WALL)
        for c, n in ladder.items():
            s.glyph(c, r, T[n], A_LADDER)
    for r in range(f0 + 1, arch):
        for c in (30, 31):
            s.glyph(c, r, T["wall"], A_WALL)
    s.glyph(30, arch, art.door["door_arch_l"]["bm"], A_DOOR)
    s.glyph(31, arch, art.door["door_arch_r"]["bm"], A_DOOR)
    for r in range(arch + 1, f1):
        s.glyph(30, r, art.door["door_l"]["bm"], A_DOOR)
        s.glyph(31, r, art.door["door_r"]["bm"], A_DOOR)

    # decor (§3.3 "In the mock scene"); animated ones shown at step 0
    def dec(name, c, r):
        s.glyph(c, r, D[name]["bm"], D[name]["attr"])
    u = f0 + 1                                     # first air row of storey 1
    dec("cobweb", 3, 0)
    dec("cobweb", 1, u)
    for r in (2, 3):
        for c in (6, 7):
            dec("window", c, r)
    dec("brazier_flame1", 16, f0 - 2)
    dec("brazier_bowl", 16, f0 - 1)
    dec("drip1", 20, 0)
    s.glyph(28, 1, T["torch_t"], A_TORCH)
    s.glyph(28, 2, T["torch_b"], A_TORCH)
    s.glyph(3, u + 1, T["torch_t"], A_TORCH)
    s.glyph(3, u + 2, T["torch_b"], A_TORCH)
    dec("moss", 8, u)
    dec("moss", 9, u)
    dec("banner_top", 15, u)
    dec("banner_tail", 15, u + 1)
    for r in range(u, u + 3):
        dec("chain", 28, r)
    dec("candles", 2, f1 - 1)
    dec("skulls", 17, f1 - 1)
    dec("rubble", 3, f0 - 1)

    # characters (§3.2): bottom rows on the standing row
    mfg, msol = art.mage
    s.sprite("mage CAST2", 4 * 8, (f1 - 6) * 8, mfg, msol, A_MAGE)
    sfg, ssol = art.skel
    s.sprite("skeleton WALK2", 10 * 8, (f0 - 6) * 8, sfg, ssol, A_SKEL)
    gfg, gsol = art.gob
    s.sprite("goblin WALK1 (L)", 19 * 8, (f1 - 4) * 8, gfg, gsol, A_GOB)
    fb, fbs, fba = art.spells["firebolt_fly1"]
    s.sprite("firebolt", 11 * 8, (f1 - 4) * 8, fb, fbs, fba)

    floor_rows = [f0, f1]
    return s, floor_rows


def panel_v1(s: Screen, art: Art):
    F = art.font
    for i, (name, ink) in enumerate(BAR_ICONS):
        b = art.ic16[name]
        base = b["attr"] if ink is None else ink
        s.glyph(2 * i, 20, b["bm"], icon_state_attr(base, i))
    for r in (20, 21):
        s.glyph(18, r, art.ic8["separator"]["bm"], art.ic8["separator"]["attr"])
    s.text(19, 20, "FIREBOLT".ljust(13), 0x47, F)
    s.text(19, 21, "COST3 MEDIUM".ljust(13), 0x46, F)
    s.glyph(0, 22, art.ic8["heart"]["bm"], 0x42)
    put_bar(s, 1, 22, 5, HP / HP_MAX, 0x42)
    s.text(6, 22, f"{HP:2d}", 0x42, F)
    s.text(8, 22, " ", 0x00, F)
    s.glyph(9, 22, art.ic8["drop"]["bm"], 0x45)
    put_bar(s, 10, 22, 5, MP / MP_MAX, 0x45)
    s.text(15, 22, f"{MP:2d} ", 0x45, F)
    s.glyph(18, 22, art.ic8["drumstick"]["bm"], 0x44)
    put_bar(s, 19, 22, 5, HUNGER, 0x46)            # peckish stage attr
    s.text(24, 22, " ", 0x00, F)
    for i, (name, a) in enumerate([("staff8", 0x46), ("robe8", 0x43), ("hood8", 0x43),
                                   ("ring8", 0x46), ("empty8", 0x01)]):
        s.glyph(25 + i, 22, art.ic8[name]["bm"], a)
    s.text(30, 22, "D3", 0x47, F)
    s.text(0, 23, "THE FIREBOLT FLIES.".ljust(32), 0x07, F)


def panel_v2(s: Screen, art: Art):
    F = art.font
    names8 = ["staff8", "spark8", "firebolt8", "frost8", "lightning8", "apple8",
              "potion8", "scroll8", "bag8"]
    for i, n in enumerate(names8):
        ink = BAR_ICONS[i][1]
        base = art.ic8[n]["attr"] if ink is None else ink
        s.glyph(i, 22, art.ic8[n]["bm"], icon_state_attr(base, i))
    s.text(9, 22, "FIREBOLT", 0x47, F)
    s.text(17, 22, " 3MP MEDIUM".ljust(15), 0x46, F)
    s.glyph(0, 23, art.ic8["heart"]["bm"], 0x42)
    put_bar(s, 1, 23, 7, HP / HP_MAX, 0x42)
    s.text(8, 23, f"{HP:2d} ", 0x42, F)
    s.glyph(11, 23, art.ic8["drop"]["bm"], 0x45)
    put_bar(s, 12, 23, 7, MP / MP_MAX, 0x45)
    s.text(19, 23, f"{MP:2d} ", 0x45, F)
    s.glyph(22, 23, art.ic8["drumstick"]["bm"], 0x44)
    put_bar(s, 23, 23, 7, HUNGER, 0x46)
    s.text(30, 23, "D3", 0x47, F)


def inventory(art: Art) -> Screen:
    s, F, I = Screen(), art.font, art.ic16
    s.text(0, 0, " INVENTORY            MAGE   D3 ", 0x47, F)
    s.text(1, 2, "WORN", 0x46, F)
    s.text(13, 2, "BAG", 0x46, F)
    worn = [("staff", 0x46, "STAFF"), ("robe", 0x43, "ROBE"), ("hood", 0x43, "HOOD"),
            ("ring", 0x46, "RING"), ("empty", 0x01, "-")]
    for k, (ic, a, nm) in enumerate(worn):
        r = 3 + 3 * k
        s.glyph(1, r, I[ic]["bm"], a)
        s.text(4, r, nm, 0x07, F)
    bag = [[("meat", 0x43, 2), ("apple", 0x42, 3), ("carrot", 0x46, 1), ("pear", 0x44, 1),
            ("cheese", 0x46, 2)],
           [("potion", 0x42, 2), ("potion", 0x45, 1), ("scroll", 0x47, 1), ("scroll", 0x43, 1),
            ("empty", 0x01, 0)]] + [[("empty", 0x01, 0)] * 5] * 2
    for j, rowl in enumerate(bag):
        for i, (ic, a, q) in enumerate(rowl):
            c, r = 13 + 3 * i, 3 + 3 * j
            cursor = (i, j) == (1, 0)                  # on Apple, cols 16-17 rows 3-4
            s.glyph(c, r, I[ic]["bm"], sel(a) if cursor else a)
            if q > 1:
                s.text(15 + 3 * i, 4 + 3 * j, str(q), 0x47, F)
    s.text(13, 15, "HP 18/22  MP 5/12", 0x07, F)
    s.text(13, 16, "ATK3 DEF2", 0x07, F)
    s.text(13, 17, "FOOD", 0x07, F)
    put_bar(s, 18, 17, 5, HUNGER, 0x46)
    s.text(24, 17, "PECKISH", 0x07, F)
    s.text(13, 19, "EAT", A_GREY_SEL, F)              # selected verb: PAPER blue
    s.text(18, 19, "QUICK", 0x07, F)
    s.text(25, 19, "DROP", 0x07, F)
    s.text(1, 21, "APPLE", 0x47, F)
    s.text(17, 21, "EAT: +4 FOOD", 0x47, F)
    s.text(1, 22, "A CRISP APPLE.", 0x07, F)
    s.text(1, 23, "FIRE:ACTIONS  FIRE+DOWN:BACK", 0x01, F)
    return s


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(name: str, s: Screen, scr: bytes, floor_rows: list[int], panel_rows: range):
    """Returns (errors, report lines)."""
    errs, rep = [], []
    bm, attr = decode_scr(scr)
    if not (np.array_equal(bm, s.bm) and np.array_equal(attr, s.attr)):
        errs.append("scr round-trip mismatch")
    img = render_rgb(bm, attr)
    over2 = 0
    for r in range(24):
        for c in range(32):
            cols = {tuple(p) for p in img[r * 8:r * 8 + 8, c * 8:c * 8 + 8].reshape(-1, 3)}
            if len(cols) > 2:
                over2 += 1
    # mis-colouring: a set pixel whose intended ink differs from its cell's ink
    sprite_cells = {cr for sp in s.sprites for cr in sp["cells"]}
    clash, follow = 0, 0
    clash_cells = set()
    for r in range(24):
        for c in range(32):
            ink = int(attr[r, c]) & 0x47
            w = s.want[r * 8:r * 8 + 8, c * 8:c * 8 + 8]
            sp = s.sprite_px[r * 8:r * 8 + 8, c * 8:c * 8 + 8]
            bad = (w >= 0) & (w != ink)
            if not bad.any():
                continue
            if (c, r) in sprite_cells and not (bad & sp).any():
                follow += int(bad.sum())             # F9 attr-follow on background px
            else:
                clash += int(bad.sum())
                clash_cells.add((c, r))
    f9 = []
    for sp in s.sprites:
        for (c, r), bga in sp["bg"].items():
            if (bga >> 3) & 7 != 0 or r in floor_rows or r in panel_rows:
                f9.append(f"{sp['name']} on ({c},{r}) bg ${bga:02X}")
    rep.append(f"{name}: cells with >2 colours: {over2}; mis-coloured sprite/bg pixels: "
               f"{clash} in {len(clash_cells)} cells; F9 attr-follow recoloured bg px: {follow}; "
               f"sprite cells off black paper / in floor or panel rows: {len(f9)}")
    for sp in s.sprites:
        cs = sp["cells"]
        rep.append(f"    {sp['name']:18s} attr ${sp['attr']:02X} cells "
                   f"{min(c for c, _ in cs)}-{max(c for c, _ in cs)} x "
                   f"{min(r for _, r in cs)}-{max(r for _, r in cs)}")
    if over2:
        errs.append(f"{over2} cells with >2 colours")
    if clash:
        errs.append(f"{clash} mis-coloured px in cells {sorted(clash_cells)}")
    errs += f9
    return errs, rep


# ---------------------------------------------------------------------------
# Contact sheet + GIF
# ---------------------------------------------------------------------------

SHEET_BG = (34, 34, 48)
ART_ZOOM = 2          # art drawn 2x the label scale on the sheet
LABEL = (200, 200, 210)


class Sheet:
    def __init__(self, font, width_px: int = 360):
        self.font, self.w = font, width_px
        self.items: list[tuple[int, int, np.ndarray]] = []   # (x, y, rgb) in sheet px (1x)
        self.x, self.y, self.line_h = 4, 4, 0

    def label(self, x, y, s, colour=LABEL):
        for i, ch in enumerate(s):
            g = self.font[ch]
            img = np.zeros((8, 8, 3), np.uint8)
            img[:] = SHEET_BG
            img[g] = colour
            self.items.append((x + i * 8, y, img))

    def heading(self, s):
        self.newline()
        self.y += 4
        self.label(4, self.y, s, (255, 255, 120))
        self.y += 12

    def newline(self):
        if self.x > 4:
            self.y += self.line_h + 6
        self.x, self.line_h = 4, 0

    def add(self, imgs: list[np.ndarray], caption: str):
        """A frame strip with a caption (caption may be wider than the art)."""
        w = sum(i.shape[1] * ART_ZOOM for i in imgs) + 2 * (len(imgs) - 1)
        h = max(i.shape[0] * ART_ZOOM for i in imgs)
        bw = max(w, len(caption) * 8)
        if self.x + bw > self.w:
            self.newline()
        x = self.x
        for im in imgs:
            im = np.kron(im, np.ones((ART_ZOOM, ART_ZOOM, 1), np.uint8))
            self.items.append((x, self.y + (h - im.shape[0]), im))
            x += im.shape[1] + 2
        self.label(self.x, self.y + h + 2, caption)
        self.x += bw + 10
        self.line_h = max(self.line_h, h + 12)

    def render(self, scale=4) -> np.ndarray:
        self.newline()
        H = self.y + 4
        img = np.zeros((H, self.w + 8, 3), np.uint8)
        img[:] = SHEET_BG
        for x, y, im in self.items:
            img[y:y + im.shape[0], x:x + im.shape[1]] = im
        return img


def glyph_rgb(bm: np.ndarray, attr: int) -> np.ndarray:
    h, w = bm.shape
    return render_rgb(bm, np.full((h // 8, w // 8), attr, np.uint8))


def sprite_rgb(bm, solid, attr) -> np.ndarray:
    """Sprite on black paper; the mask outline shown as dark grey for review."""
    ink, _ = attr_rgb(attr)
    img = np.zeros(bm.shape + (3,), np.uint8)
    img[solid & ~bm] = (60, 60, 90)
    img[bm] = ink
    return img


def contact_sheet(art: Art, sizes: dict) -> np.ndarray:
    sh = Sheet(art.font, 720)
    import concept_r4
    concept_r4.sheet_current(sh, art)
    D = art.decor
    sh.heading("R1 DECOR (8x8 GLYPHS, ATTR AS IN GAME)")
    tor = np.vstack([art.tiles["torch_t"], art.tiles["torch_b"]])
    sh.add([glyph_rgb(tor, a) for a in (0x46, 0x42, 0x06)], "TORCH(EXISTS)")
    bra = [np.vstack([D[f]["bm"], D["brazier_bowl"]["bm"]]) for f in ("brazier_flame1",
                                                                      "brazier_flame2")]
    imgs = []
    for k in range(4):
        im = glyph_rgb(bra[k % 2], 0x07)
        im[:8] = glyph_rgb(bra[k % 2][:8], (0x46, 0x46, 0x42, 0x42)[k])
        imgs.append(im)
    sh.add(imgs, "BRAZIER")
    sh.add([glyph_rgb(D["candles"]["bm"], a) for a in (0x46, 0x06)], "CANDLES")
    sh.add([glyph_rgb(D[f]["bm"], 0x45) for f in ("drip1", "drip2")], "DRIP")
    sh.add([glyph_rgb(D["cobweb"]["bm"], 0x07)], "WEB")
    sh.add([glyph_rgb(np.vstack([D["chain"]["bm"]] * 3), 0x07)], "CHAIN")
    sh.add([glyph_rgb(np.vstack([D["banner_top"]["bm"], D["banner_tail"]["bm"]]), 0x43)],
           "BANNER")
    sh.add([glyph_rgb(D["skulls"]["bm"], 0x47)], "SKULLS")
    w = D["window"]["bm"]
    sh.add([glyph_rgb(np.block([[w, w], [w, w]]), 0x05)], "WINDOW")
    m = D["moss"]["bm"]
    sh.add([glyph_rgb(np.hstack([m, m, m]), 0x04)], "MOSS")
    sh.add([glyph_rgb(D["rubble"]["bm"], 0x01)], "RUBBLE")
    b = D["bookshelf"]["bm"]
    sh.add([glyph_rgb(np.block([[b, b], [b, b]]), 0x06)], "BOOKS")
    sh.add([glyph_rgb(np.hstack([D["cauldron_l"]["bm"], D[f]["bm"]]), 0x44)
            for f in ("cauldron_r1", "cauldron_r2")], "CAULDRON(DEF)")
    sh.heading("R1 DOOR: CLOSED / OPEN / +RING (LOCK PLATE)")
    Do = art.door
    wall = art.tiles["wall"]
    def door_img(planks: bool, ring: bool):
        bmx = np.zeros((64, 16), bool)
        bmx[0:8, 0:8] = bmx[0:8, 8:16] = wall
        bmx[8:16, 0:8], bmx[8:16, 8:16] = Do["door_arch_l"]["bm"], Do["door_arch_r"]["bm"]
        for k in range(5):
            if planks:
                bmx[16 + 8 * k:24 + 8 * k, 0:8] = Do["door_l"]["bm"]
                rr = "door_r_ring" if (ring and k == 2) else "door_r"
                bmx[16 + 8 * k:24 + 8 * k, 8:16] = Do[rr]["bm"]
        at = np.full((8, 2), A_DOOR, np.uint8)
        at[0] = A_WALL
        return render_rgb(bmx, at)
    sh.add([door_img(True, False), door_img(False, False), door_img(True, True)], "DOOR")

    sh.heading("R1 ICONS 16x16 (BAR USE SUPERSEDED BY 24x24; PAGE/QUICK STILL 16)")
    for n, b in art.ic16.items():
        a = b["attr"]
        if n in ("staff", "spark", "firebolt", "frost", "lightning", "bag"):
            sh.add([glyph_rgb(b["bm"], x) for x in (a, sel(a), A_GREY, A_GREY_SEL)], n.upper())
        elif n == "potion":
            sh.add([glyph_rgb(b["bm"], x) for x in (0x42, 0x45, 0x44)], "POTION H/M/C")
        elif n == "scroll":
            sh.add([glyph_rgb(b["bm"], x) for x in (0x47, 0x43, 0x46)], "SCROLL X3")
        else:
            sh.add([glyph_rgb(b["bm"], a)], n.upper())
    sh.heading("R1 ICONS 8x8 (LABELS, GEAR, FLOOR; V2 BAR SUPERSEDED)")
    for n, b in art.ic8.items():
        sh.add([glyph_rgb(b["bm"], b["attr"])], n.replace("8", "").upper()[:6])
    sh.heading("R1 SPELLS (MASK OUTLINE IN GREY)")
    groups = [("SPARK", ["spark_fly1", "spark_fly2"]), ("FIZZLE", ["spark_fizz1", "spark_fizz2"]),
              ("FIREBOLT", ["firebolt_fly1", "firebolt_fly2"]),
              ("BURST", ["firebolt_burst1", "firebolt_burst2"]),
              ("FROST", ["frost_fly"]), ("CRACK", ["frost_crack"]),
              ("LIGHTNING", ["lightning_fly1", "lightning_fly2"]),
              ("FLASH", ["lightning_flash"]), ("POWER", ["power_burst"])]
    for cap, frames in groups:
        sh.add([sprite_rgb(*art.spells[f]) for f in frames], cap)
    r2_sheet(sh, art)
    r3_sheet(sh, art)
    return sh.render()


def anim_gif(art: Art, path: str, nframes: int = 96):
    """Animated decor (attr cycles + glyph swaps per §3.3) and the four spells in
    flight per §4, rendered through the attribute model. 1 GIF frame = 1 tick
    (2 TV frames = 40 ms)."""
    import concept_r4
    D, T, F = art.decor, art.tiles, art.font
    candle_tab = [(0x46, 5), (0x06, 1), (0x46, 3), (0x06, 2), (0x46, 7), (0x06, 1),
                  (0x46, 2), (0x06, 3)]                 # RNG-free, 8 steps, 24 ticks
    ctab = [a for a, n in candle_tab for _ in range(n)]
    lanes = [  # name, fly frames, end fx frames, range cells, walls (cols), bounces, px/tick
        ("SPARK", ["spark_fly1", "spark_fly2"], ["spark_fizz1", "spark_fizz2"], 6, [], 0, 4),
        ("FIREBOLT", ["firebolt_fly1", "firebolt_fly2"], ["firebolt_burst1", "firebolt_burst2"],
         12, [12], 0, 4),                         # wall before max range: bursts on it
        ("FROST", ["frost_fly"], ["frost_crack"], 12, [11], 1, 4),
        ("LIGHTNING", ["lightning_fly1", "lightning_fly2"], ["lightning_flash"], 28, [1, 13], 2, 8),
    ]
    frames = []
    for t in range(nframes):
        s = Screen(rows=78)
        # --- decor strip: rows 0-2 air, row 3 floor
        for c in range(32):
            s.glyph(c, 3, T["platform"], A_FLOOR)
        s.glyph(2, 1, T["torch_t"], (0x46, 0x42, 0x06)[(t // 4) % 3])
        s.glyph(2, 2, T["torch_b"], A_TORCH)
        k = t // 3
        s.glyph(6, 1, D[("brazier_flame1", "brazier_flame2")[k % 2]]["bm"],
                (0x46, 0x46, 0x42, 0x42)[k % 4])
        s.glyph(6, 2, D["brazier_bowl"]["bm"], 0x07)
        s.glyph(10, 2, D["candles"]["bm"], ctab[t % len(ctab)])
        dp = t % 20                                     # bead 4, fall 4, hold 12 (bead)
        s.glyph(14, 0, D["drip2" if 4 <= dp < 8 else "drip1"]["bm"], 0x45)
        cf = ("cauldron_r1", "cauldron_r2")[(t // 4) % 2]
        s.glyph(18, 2, D["cauldron_l"]["bm"], 0x44)
        s.glyph(19, 2, D[cf]["bm"], 0x44)
        s.text(22, 1, "DECOR", 0x07, F)
        # --- spell lanes
        for li, (nm, fly, fx, rng, walls, bounces, spd) in enumerate(lanes):
            top = 4 + 3 * li
            row = top + 1
            s.text(1, top + 2, f"{nm} R{rng}" + (f" BOUNCE{bounces}" if bounces else ""),
                   0x07, F)
            for wc in walls:
                for r in (top, top + 1):
                    s.glyph(wc, r, T["wall"], A_WALL)
            x0 = 16                                     # caster's staff tip, col 2
            right_wall = min([w for w in walls if w * 8 > x0] or [32])
            left_wall = max([w for w in walls if w * 8 < x0] or [-1])
            fw = art.spells[fly[0]][0].shape[1]
            lo, hi = (left_wall + 1) * 8, right_wall * 8 - fw
            # simulate the whole flight: range in px, reflect at walls while
            # bounces remain, otherwise stop (burst/fizzle) at the wall
            flight, x, d, left, b = [], x0, 1, rng * 8, bounces
            while left > 0:
                if (d > 0 and x >= hi) or (d < 0 and x <= lo):
                    if b == 0:
                        break
                    b, d = b - 1, -d
                x += d
                left -= 1
                flight.append((x, d))
            fly_ticks = max(1, len(flight) // spd)
            fx_ticks = 6
            period = fly_ticks + fx_ticks + 6
            tt = t % period
            x, d = flight[min(tt * spd, len(flight)) - 1] if tt else (x0, 1)
            if tt < fly_ticks:
                fg, so, a = art.spells[fly[tt % len(fly)]]
                if d < 0:
                    fg, so = fg[:, ::-1], so[:, ::-1]
                s.sprite(nm, x, row * 8, fg, so, a)
            elif tt < fly_ticks + fx_ticks:
                f = fx[min((tt - fly_ticks) // 3, len(fx) - 1)]
                fg, so, a = art.spells[f]
                fh, fwx = fg.shape
                cx = x + fw // 2 - fwx // 2
                cx = max(lo, min(cx, right_wall * 8 - fwx))
                y = row * 8 if fh == 8 else top * 8
                s.sprite(nm + " fx", cx, y, fg, so, a)
        r2_gif_layer(art, s, t, 16)
        r3_gif_layer(art, s, t, 46)
        concept_r4.gif_layer(art, s, t, 62)
        frames.append(Image.fromarray(s.rgb_image()).resize((256 * 2, 78 * 8 * 2),
                                                            Image.NEAREST))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=40, loop=0,
                   optimize=False)



# ---------------------------------------------------------------------------
# Round 2: large decor, plaster walls, level colours, warrior art, 24x24 trial,
# staff swing, books + boss loot, new monsters
# ---------------------------------------------------------------------------

# Per-level colour schemes (attr only, F9-legal: air-band walls keep PAPER black because
# sprites stand next to / in front of them; floor rows are sprite-free so any paper is legal;
# the ladder keeps $02 on black paper because climbers cover it).
SCHEMES = [("BLUE KEEP", 0x0F, 0x01), ("RED CRYPT", 0x17, 0x02),
           ("GREEN CAVES", 0x27, 0x04), ("SANDSTONE", 0x30, 0x06)]

# Animated large decor: glyph-swap frames (cells that differ between _fN blocks) + attr
# cycles on named cells. step = ticks per animation step.
# LOOK-1 (2026-11-02): the IN-GAME torches / big brazier no longer cycle attrs (RAG art, fixed $42,
# bigdecor.grid <obj>_look1_f1/f2, tools/tiles_convert.py OBJ_SPEC). This table + the _fN blocks are
# kept only for the concept sheets and the MENU torches (tools/menu_art.py, src/menu1.asm).
BIG_ANIM = {
    "torch_tall": {"frames": 3, "step": 3, "cycle": {(0, 0): [0x46, 0x46, 0x42],
                                                     (1, 0): [0x46, 0x46, 0x42]}},
    "torch_slim": {"frames": 3, "step": 3, "cycle": {(0, 0): [0x46, 0x46, 0x42]}},
    "brazier_big": {"frames": 3, "step": 4, "cycle": {(0, 0): [0x46, 0x42, 0x46],
                                                      (1, 0): [0x46, 0x42, 0x46]}},
}
# Boss-loot treatments: (a) attr shimmer cycle, 4 ticks/step (~0.12k T/cell/step);
# (b) hardware FLASH bit (0 T: the ULA swaps ink/paper every 16 frames = 8 ticks).
LOOT_SHIMMER = [0x46, 0x47, 0x45, 0x47]
FLASH = 0x80

MONSTERS = {   # kind: (frames, body width px, motion frames)
    "zombie": (["zombie_walk1", "zombie_walk2", "zombie_claw", "zombie_hurt", "zombie_dead"], 24,
               {"zombie_walk1", "zombie_walk2"}),
    "mummy": (["mummy_walk1", "mummy_walk2", "mummy_grab", "mummy_hurt", "mummy_dead"], 24,
              {"mummy_walk1", "mummy_walk2"}),
    "orc": (["orc_walk1", "orc_walk2", "orc_chop", "orc_hurt", "orc_dead"], 24,
            {"orc_walk1", "orc_walk2"}),
    "skelarch": (["skelarch_walk1", "skelarch_walk2", "skelarch_draw", "skelarch_shoot"], 24,
                 {"skelarch_walk1", "skelarch_walk2"}),
    "necro": (["necro_walk1", "necro_walk2", "necro_cast", "necro_hurt", "necro_dead"], 24,
              {"necro_walk1", "necro_walk2"}),
    "spider": (["spider_walk1", "spider_walk2", "spider_bite", "spider_hurt", "spider_dead"], 32,
               {"spider_walk1", "spider_walk2"}),
}
MON_ATTR = {"zombie": 0x04, "mummy": 0x06, "orc": 0x44, "skelarch": 0x47, "necro": 0x43,
            "spider": 0x42}
PROJ_MOTION = {"arrow_fly1", "arrow_fly2", "dagger_spin1", "dagger_spin2", "dagger_spin3",
               "dagger_spin4", "axe_spin1", "axe_spin2", "axe_spin3", "axe_spin4",
               "necro_bolt1", "necro_bolt2"}


def cell_glyphs(b: dict) -> list:
    """(cx, cy, glyph bytes, attr) for every 8x8 cell of a multi-cell block."""
    out = []
    for cy in range(b["h"] // 8):
        for cx in range(b["w"] // 8):
            g = b["bm"][cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8]
            a = int(b["cells"][cy, cx]) if b["cells"] is not None else b["attr"]
            out.append((cx, cy, np.packbits(g, axis=1).tobytes(), a))
    return out


def big_object(art, base: str) -> dict:
    """Group the _fN frames of a large decor object; count tile ids and anim cells."""
    names = [n for n in art.big if n == base or n.startswith(base + "_f")]
    frames = [art.big[n] for n in names]
    ids = {(g, a) for f in frames for _, _, g, a in cell_glyphs(f)}
    swap = set()
    if len(frames) > 1:
        c0 = cell_glyphs(frames[0])
        for f in frames[1:]:
            for (cx, cy, g, _), (_, _, g0, _) in zip(cell_glyphs(f), c0):
                if g != g0:
                    swap.add((cx, cy))
    cyc = set(BIG_ANIM.get(base, {}).get("cycle", {}))
    return {"frames": frames, "ids": len(ids), "swap": swap, "cycle": cyc,
            "w": frames[0]["w"], "h": frames[0]["h"]}


BIG_OBJECTS = ["torch_tall", "torch_slim", "brazier_big", "banner_tall", "window_arch", "pillar"]


def big_rgb(b: dict, cycle_override: dict | None = None) -> np.ndarray:
    at = b["cells"].copy()
    for (cx, cy), a in (cycle_override or {}).items():
        at[cy, cx] = a
    return render_rgb(b["bm"], at)


def place_big(s: Screen, col: int, row: int, b: dict, cyc: dict | None = None):
    for cx, cy, _g, a in cell_glyphs(b):
        a = (cyc or {}).get((cx, cy), a)
        s.glyph(col + cx, row + cy, b["bm"][cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8], a)


def wall_demo(art, wall_attr: int = A_WALL, floor_attr: int = A_FLOOR) -> np.ndarray:
    """A 10x6 wall patch: plaster with holes/cracks, a crumbling edge row, bare brick
    below, floor row. Letters: P plaster, C crack, H hole, E edge, B existing wall."""
    plan = ["PPHPPPCPPP", "PCPPPHPPPP", "PPPPPPPPCP", "EEEEPPPEEE", "BBBBEEEBBB", "FFFFFFFFFF"]
    key = {"P": art.walls["plaster"]["bm"], "C": art.walls["plaster_crack"]["bm"],
           "H": art.walls["plaster_hole"]["bm"], "E": art.walls["plaster_edge"]["bm"],
           "B": art.tiles["wall"], "F": art.tiles["platform"]}
    bm = np.block([[key[c] for c in r] for r in plan])
    at = np.array([[floor_attr if c == "F" else wall_attr for c in r] for r in plan], np.uint8)
    return render_rgb(bm, at)


def scheme_slice(art, floor_attr: int, wall_attr: int) -> np.ndarray:
    """8x5 cells: wall (plaster + brick) at cols 0-1, air, ladder cols 5-7 (row 4 = hole)."""
    T, Wl = art.tiles, art.walls
    bm = np.zeros((40, 64), bool)
    at = np.zeros((5, 8), np.uint8)
    wall_cells = [["plaster", "plaster_hole"], ["plaster_crack", "plaster"],
                  ["plaster_edge", "plaster_edge"], [None, None]]
    for r in range(5):
        for c in range(8):
            g, a = None, A_AIR
            if r < 4 and c < 2:
                n = wall_cells[r][c]
                g, a = (Wl[n]["bm"] if n else T["wall"]), wall_attr
            elif c >= 5:
                g, a = T[("ladder_l", "ladder_m", "ladder_r")[c - 5]], A_LADDER
            elif r == 4:
                g = T["platform_end_r"] if c == 4 else T["platform"]
                a = floor_attr
            if g is not None:
                bm[r * 8:r * 8 + 8, c * 8:c * 8 + 8] = g
            at[r, c] = a
    for c in range(2):                                   # wall cells in the floor row
        bm[32:40, c * 8:c * 8 + 8] = T["wall"]
        at[4, c] = floor_attr
    return render_rgb(bm, at)


def r2_sheet(sh: "Sheet", art) -> None:
    D = art.big
    sh.heading("R2 LARGE DECOR (FRAMES; ATTR CYCLE SHOWN)")
    for base in BIG_OBJECTS:
        o = big_object(art, base)
        an = BIG_ANIM.get(base)
        imgs = []
        for k, f in enumerate(o["frames"]):
            cyc = {cc: seq[k % len(seq)] for cc, seq in an["cycle"].items()} if an else None
            imgs.append(big_rgb(f, cyc))
        tag = f"{base.upper()} {o['w'] // 8}X{o['h'] // 8} ID{o['ids']}"
        if o["swap"] or o["cycle"]:
            tag += f" SW{len(o['swap'])} AC{len(o['cycle'])}"
        sh.add(imgs, tag)
    sh.heading("R2 PLASTER WALL -- SUPERSEDED (R4 FRAGMENTS + PATCHES)")
    sh.add([glyph_rgb(art.walls[n]["bm"], A_WALL) for n in art.walls] + [glyph_rgb(art.tiles["wall"], A_WALL)],
           "PLAS CRACK HOLE EDGE +WALL")
    sh.add([wall_demo(art)], "PATCH (AIR ROWS)")
    sh.heading("R2 COLOUR SCHEMES -- SUPERSEDED BY GAME.MD 8 SCHEMES")
    for name, fa, wa in SCHEMES:
        sh.add([scheme_slice(art, fa, wa)], f"{name} ${fa:02X}/${wa:02X}")
    sh.heading("R2 WARRIOR ICONS 16x16: NORMAL / SELECTED / GREYED")
    for n, b in art.ic16b.items():
        a = b["attr"]
        if n == "book":
            sh.add([glyph_rgb(b["bm"], x) for x in (0x43, 0x42, 0x45)], "BOOK SPELL/ARMS/?")
        elif n in ("mail", "helm", "shield"):
            sh.add([glyph_rgb(b["bm"], a)], n.upper())
        else:
            sh.add([glyph_rgb(b["bm"], x) for x in (a, sel(a), A_GREY)], n.upper().replace("_", " "))
    sh.add([glyph_rgb(b["bm"], b["attr"]) for b in art.ic8b.values()], "8X8 SWORD MAIL HELM SHLD BOOK")
    sh.heading("R2 ICON SIZE TRIAL (DECIDED: 24x24)")
    for n16, n24 in (("staff", "staff24"), ("firebolt", "firebolt24"), ("apple", "apple24"),
                     ("bag", "bag24")):
        a = art.ic16[n16]["attr"]
        sh.add([glyph_rgb(art.ic16[n16]["bm"], a), glyph_rgb(art.ic24[n24]["bm"], a),
                glyph_rgb(art.ic24[n24]["bm"], sel(a))], n16.upper())
    sh.heading("R2 LOOT: SHIMMER = FLOOR, FLASH = PANEL/PAGE (DECIDED)")
    sw = art.ic16b["sword"]["bm"]
    sh.add([glyph_rgb(sw, a) for a in LOOT_SHIMMER], "SHIMMER 46>47>45>47")
    sh.add([glyph_rgb(sw, 0x47), render_rgb(~sw, np.full((2, 2), 0x47, np.uint8))],
           "FLASH $C7 (BOTH PHASES)")
    sh.heading("R2 PROJECTILES + IMPACTS (AXE DROPPED; DAGGER 2 FRAMES)")
    for cap, fr in (("ARROW", ["arrow_fly1", "arrow_fly2"]), ("HIT", ["arrow_hit"]),
                    ("AXE SPIN", ["axe_spin1", "axe_spin2", "axe_spin3", "axe_spin4"]),
                    ("AXE HIT", ["axe_hit"]),
                    ("DAGGER", ["dagger_spin1", "dagger_spin2", "dagger_spin3", "dagger_spin4"]),
                    ("BONK", ["staff_bonk"]), ("NECRO BOLT", ["necro_bolt1", "necro_bolt2"]),
                    ("N.HIT", ["necro_hit"])):
        src = art.proj if fr[0] in art.proj else art.r2
        sh.add([sprite_rgb(*src[f]) for f in fr], cap)
    sh.heading("R2 MAGE STAFF SWING: IDLE / CAST1 / SWING 40X48 + BONK")
    sh.add([sprite_rgb(*art.r2[f]) for f in ("wizard_idle", "wizard_cast1", "wizard_staffswing")]
           + [sprite_rgb(*art.proj["staff_bonk"])], "MAGE")
    sh.heading("R2 MONSTERS (ZOMBIE SUPERSEDED BY VAMPIRE; SPIDER/DEAD = R3)")
    for kind, (frames, _bw, _mo) in MONSTERS.items():
        imgs = [sprite_rgb(*art.r2[f]) for f in frames]
        if kind == "skelarch":
            imgs += [sprite_rgb(*art.r2[f]) for f in ("skeleton_hurt", "skeleton_collapsed")]
        sh.add(imgs, {"skelarch": "SKELETON ARCHER (HURT/DEAD REUSED)",
                      "necro": "NECROMANCER"}.get(kind, kind.upper()))


def pool_bytes(w: int, h: int, ax: int, bw: int, motion: bool) -> int:
    """src/data.asm POOLACC for one frame, both facings (non-SYM)."""
    cols = w // 8
    if motion:
        return 2 * h * 2 * (2 * cols + 1)
    return h * 2 * (cols + int(ax & 7 != 0)) + h * 2 * (cols + int((w - ax - bw) & 7 != 0))


def r2_bytes(art) -> list[str]:
    L = []
    def t(name, n):
        L.append(f"  {name:34s} {n:5d} B")
    L.append("round 2 — tiles/icons (bank 5, 9 B per tile id = 8 glyph + 1 attr):")
    tot_ids = 0
    for base in BIG_OBJECTS:
        o = big_object(art, base)
        tot_ids += o["ids"]
        anim = (f"  glyph-swap cells {len(o['swap'])}, attr-cycle cells {len(o['cycle'])}"
                if o["swap"] or o["cycle"] else "")
        t(f"{base} {o['w'] // 8}x{o['h'] // 8} ({o['ids']} tile ids){anim}", o["ids"] * 9)
    t(f"walls plaster x{len(art.walls)} ({len(art.walls)} tile ids)", 9 * len(art.walls))
    tot_ids += len(art.walls)
    L.append(f"  -> new tile ids: {tot_ids}")
    for n in art.ic16b:
        t(f"icon16 {n}", 33)
    for n in art.ic24:
        t(f"icon24 {n}", 73)
    for n in art.ic8b:
        t(f"icon8 {n}", 9)
    L.append("round 2 — sprite frames (1 frame id each; source = H*W/4 masked native; "
             "pool = POOLACC both facings; +24 B bank 2 per id):")
    L.append(f"  {'frame':22s} {'WxH':6s} ax {'src':>5s} {'pool':>5s}  kind")
    tot = {"ids": 0, "src": 0, "pool": 0}
    def frame(n, fg, ax, bw, motion, who):
        h, w = fg.shape
        sb, pb = h * w // 4, pool_bytes(w, h, ax, bw, motion)
        L.append(f"  {n:22s} {w}x{h:<3d} {ax:2d} {sb:5d} {pb:5d}  {who}{' MOTION' if motion else ''}")
        tot["ids"] += 1; tot["src"] += sb; tot["pool"] += pb
        return sb, pb
    for kind, (frames, bw, mo) in MONSTERS.items():
        ks = kp = 0
        for f in frames:
            sb, pb = frame(f, art.r2[f][0], art.ax.get(f, 0), bw, f in mo, kind)
            ks += sb; kp += pb
        L.append(f"  == {kind}: {len(frames)} frame ids, source {ks} B, pool {kp} B")
    hs = frame("wizard_staffswing", art.r2["wizard_staffswing"][0], 0, 24, False, "hero")
    for n, (fg, _so, _a) in art.proj.items():
        frame(n, fg, 0, fg.shape[1], n in PROJ_MOTION, "proj/fx")
    for n in ("axe_spin1", "axe_spin2", "axe_spin3", "axe_spin4"):
        frame(n, art.r2[n][0], 0, 16, True, "proj")
    L.append(f"  == all round-2 frames: {tot['ids']} ids, source {tot['src']} B, pool {tot['pool']} B")
    # pack round-trip for every derived round-2 sprite
    for n in list(art.proj) + [n for n in art.r2_src]:
        fg, so, _ = (art.proj.get(n) or art.r2[n])
        rows = gfx_convert.pack_sprite(fg, so, "native")
        dfg, dso = gfx_convert.unpack_sprite_mask(rows, fg.shape[1], "native")
        if not (np.array_equal(dfg, fg) and np.array_equal(dso, so)):
            raise SystemExit(f"{n}: pack round-trip mismatch")
    return L


def r2_validate(art) -> list[str]:
    """Clash-legality of the round-2 glyph art: every 8x8 cell has one attr with
    PAPER black (air band), so 2 colours max; check that and the F9 paper rule."""
    errs = []
    for n, b in art.big.items():
        if ((b["cells"] >> 3) & 7).any():
            errs.append(f"bigdecor {n}: a cell has non-black paper (air band, F9)")
    for n, b in art.walls.items():
        if (b["attr"] >> 3) & 7:
            errs.append(f"walls {n}: paper not black")
    for name, fa, wa in SCHEMES:
        if (wa >> 3) & 7:
            errs.append(f"scheme {name}: air-band wall paper not black")
        img = scheme_slice(art, fa, wa)
        for r in range(5):
            for c in range(8):
                if len({tuple(p) for p in img[r * 8:r * 8 + 8, c * 8:c * 8 + 8].reshape(-1, 3)}) > 2:
                    errs.append(f"scheme {name}: cell ({c},{r}) > 2 colours")
    return errs


def r2_gif_layer(art, s: "Screen", t: int, top: int):
    """Rows top..top+31 of the review GIF: large decor + boss loot, warrior/necro
    projectile lanes, the staff swing and the new monsters' cycles."""
    D, T, F = art.big, art.tiles, art.font
    # --- band 1 (top..top+5): large decor + loot, floor at top+5
    fl = top + 5
    for c in range(32):
        s.glyph(c, fl, T["platform"], A_FLOOR)
    for base, col in (("torch_tall", 1), ("torch_slim", 4), ("brazier_big", 6)):
        an = BIG_ANIM[base]
        k = (t // an["step"] + {"torch_tall": 0, "torch_slim": 1, "brazier_big": 2}[base])
        f = D[f"{base}_f{k % an['frames'] + 1}"]
        cyc = {cc: seq[k % len(seq)] for cc, seq in an["cycle"].items()}
        h = f["h"] // 8
        lift = 0 if base == "brazier_big" else 1       # torches hang on the wall
        place_big(s, col, fl - h - lift, f, cyc)
    place_big(s, 9, fl - 5, D["banner_tall"])
    place_big(s, 12, fl - 4, D["window_arch"])
    sw = art.ic16b["sword"]["bm"]
    s.glyph(16, top + 2, sw, LOOT_SHIMMER[(t // 4) % len(LOOT_SHIMMER)])
    flash_on = (t // 8) % 2 == 1                       # ULA flash: 16 frames = 8 ticks
    s.glyph(21, top + 2, ~sw if flash_on else sw, 0x47)   # ($C7: ink/paper swap emulated)
    s.glyph(27, fl - 1, art.ic8b["sword8"]["bm"], LOOT_SHIMMER[(t // 4) % len(LOOT_SHIMMER)])
    s.text(16, top + 1, "BOSS LOOT", 0x07, F)
    s.text(15, top + 4, "SHIM", 0x07, F)
    s.text(20, top + 4, "FLASH", 0x07, F)
    s.text(25, top + 3, "FLOOR", 0x07, F)
    # --- band 2 (top+6..top+15): projectile lanes (each: 2 sprite rows + label row)
    lanes = [("ARROW R28", ["arrow_fly1", "arrow_fly2"], ["arrow_hit"], 8, 16, 8),
             ("THROWN AXE R12", ["axe_spin1", "axe_spin2", "axe_spin3", "axe_spin4"],
              ["axe_hit"], 4, 16, 16),
             ("DAGGER R12", ["dagger_spin1", "dagger_spin2", "dagger_spin3", "dagger_spin4"],
              ["arrow_hit"], 4, 8, 8)]
    for li, (nm, fly, fx, spd, fw, fh) in enumerate(lanes):
        lt = top + 6 + 3 * li
        s.text(1, lt + 2, nm, 0x07, F)
        for r in (lt, lt + 1):
            s.glyph(28, r, T["wall"], A_WALL)
        x0, xend = 16, 28 * 8 - fw
        n = (xend - x0) // spd
        period = n + 10
        tt = t % period
        src = lambda f: art.proj.get(f) or art.r2[f]
        if tt < n:
            fg, so, a = src(fly[tt % len(fly)])
            s.sprite(nm, x0 + tt * spd, (lt + 2) * 8 - fh, fg, so, a)
        elif tt < n + 6:
            fg, so, a = src(fx[0])
            s.sprite(nm + " fx", 28 * 8 - fg.shape[1], (lt + 2) * 8 - fg.shape[0], fg, so, a)
    # --- band 3 (top+15..top+21): staff swing vs goblin, zombie, mummy, orc
    fl3 = top + 21
    for c in range(32):
        s.glyph(c, fl3, T["platform"], A_FLOOR)
    cyc = t % 16
    mage = "wizard_idle" if cyc < 6 else "wizard_cast1" if cyc < 9 else "wizard_staffswing"
    fg, so, a = art.r2[mage]
    s.sprite("mage", 0, fl3 * 8 - 48, fg, so, a)
    hit = 9 <= cyc < 13
    gf, gs, ga = art.r2["goblin_hurt" if hit else "goblin_walk1"]
    gf, gs = gf[:, ::-1], gs[:, ::-1]
    s.sprite("goblin", 5 * 8, fl3 * 8 - gf.shape[0], gf, gs, 0x42 if hit else ga)
    if hit:
        fg, so, a = art.proj["staff_bonk"]
        s.sprite("bonk", 32, fl3 * 8 - 24, fg, so, a)
    def mon(kind, col, row_floor, phase):
        frames = MONSTERS[kind][0]
        k = (t + phase) % 40
        f = (frames[0] if (k // 4) % 2 == 0 else frames[1]) if k < 24 else \
            frames[2] if k < 32 else frames[3] if k < 36 else frames[0]
        fg, so, _ = art.r2[f]
        x = col * 8 - art.ax.get(f, 0)
        if k < 24:
            x += (k // 4) * 2                           # walk 2 px per step
        s.sprite(kind, x, row_floor * 8 - fg.shape[0], fg, so, MON_ATTR[kind])
    mon("zombie", 9, fl3, 0)
    mon("mummy", 16, fl3, 13)
    mon("orc", 23, fl3, 26)
    # --- band 4 (top+22..top+28): skeleton archer + arrow, necromancer + bolt, spider
    fl4 = top + 28
    for c in range(32):
        s.glyph(c, fl4, T["platform"], A_FLOOR)
    k = t % 24
    sf = "skelarch_walk1" if k < 4 else "skelarch_walk2" if k < 8 else \
        "skelarch_draw" if k < 14 else "skelarch_shoot" if k < 18 else "skelarch_walk1"
    fg, so, _ = art.r2[sf]
    s.sprite("skelarch", 0, fl4 * 8 - 48, fg, so, 0x47)
    if 14 <= k < 22:
        fg, so, a = art.proj[("arrow_fly1", "arrow_fly2")[k % 2]]
        s.sprite("arrow", 32 + (k - 14) * 8, fl4 * 8 - 48 + 14, fg, so, a)
    k = t % 24
    nf = "necro_walk1" if k < 4 else "necro_walk2" if k < 8 else "necro_cast" if k < 16 else \
        "necro_walk1"
    fg, so, _ = art.r2[nf]
    s.sprite("necro", 13 * 8, fl4 * 8 - 48, fg, so, 0x43)
    if 10 <= k < 18:
        fg, so, a = art.proj[("necro_bolt1", "necro_bolt2")[k % 2]]
        s.sprite("bolt", 17 * 8 + (k - 10) * 4, fl4 * 8 - 48 + 16, fg, so, 0x44)
    k = t % 24
    spf = "spider_walk1" if (k // 3) % 2 == 0 else "spider_walk2"
    if k >= 16:
        spf = "spider_bite" if k < 21 else "spider_hurt"
    fg, so, _ = art.r2[spf]
    s.sprite("spider", 26 * 8 - min(k, 16) // 2 * 2 - 8, fl4 * 8 - fg.shape[0], fg, so, 0x42)


# ---------------------------------------------------------------------------
# Round 3: dithered walls, hero frames, Archmage, spell sprites, gold glow, hand pass
# ---------------------------------------------------------------------------

R3_HERO = ["knight_jump1", "knight_jump2", "knight_power", "knight_whirl", "knight_throw",
           "knight_bow", "wizard_jump1", "wizard_jump2"]
R3_MOTION = {"knight_jump2", "wizard_jump2", "drain_fly1", "drain_fly2"}
# Lean spell-sprite set (user: spells as real masked sprites, <= 2 flight frames each)
SPELL_SET = [("SPARK", ["spark_fly1", "spark_fly2"], ["spark_fizz1"]),
             ("FIREBOLT", ["firebolt_fly1", "firebolt_fly2"], ["firebolt_burst1"]),
             ("FROST", ["frost_fly"], ["frost_crack"]),
             ("LIGHTNING", ["lightning_fly1", "lightning_fly2"], ["lightning_flash"]),
             ("DRAIN LIFE", ["drain_fly1", "drain_fly2"], ["drain_hit"])]
GOLD = [0x06, 0x46, 0x47, 0x46]          # gold glow: dim yellow -> bright yellow -> white


def wall3_demo(art, ink_attr: int) -> np.ndarray:
    """10x6 wall: mostly dark, dithered patches, a fade row into full dither, the
    existing WALL tile for comparison (right column), floor row."""
    plan = ["DDDDPDDDDB", "DPDDDDDDDB", "DDDDDDPDDB", "FFFFDDDFFB", "WWWWDDDWWB", "LLLLLLLLLL"]
    k = {"D": art.walls3["wall_dark"]["bm"], "P": art.walls3["wall_dith_patch"]["bm"],
         "F": art.walls3["wall_dith_fade"]["bm"], "W": art.walls3["wall_dith"]["bm"],
         "B": art.tiles["wall"], "L": art.tiles["platform"]}
    bm = np.block([[k[c] for c in r] for r in plan])
    at = np.array([[A_FLOOR if c == "L" else ink_attr for c in r] for r in plan], np.uint8)
    return render_rgb(bm, at)


def glow_attrs(t: int, cells, mode: str) -> dict:
    """Per-cell attr for the gold glow at tick t. 'sync': all cells together;
    'sweep': a diagonal band travelling across the footprint (phase = col + row)."""
    out = {}
    for (c, r) in cells:
        ph = (t // 2) if mode == "sync" else (t // 2 - (c + r))
        out[(c, r)] = GOLD[ph % len(GOLD)]
    return out


def sprite_with_cell_attrs(fg, solid, attrs: dict, h_cells: int, w_cells: int) -> np.ndarray:
    img = np.zeros(fg.shape + (3,), np.uint8)
    for (c, r), a in attrs.items():
        ink, _ = attr_rgb(a)
        sub = fg[r * 8:r * 8 + 8, c * 8:c * 8 + 8]
        img[r * 8:r * 8 + 8, c * 8:c * 8 + 8][sub] = ink
    return img


def r3_sheet(sh, art) -> None:
    sh.heading("R3 WALLS -- SUPERSEDED (R4 FRAGMENTS + PATCHES)")
    sh.add([glyph_rgb(b["bm"], A_WALL) for b in art.walls3.values()]
           + [glyph_rgb(art.tiles["wall"], A_WALL)], "DARK DITH PATCH FADE +OLD")
    sh.add([wall3_demo(art, A_WALL)], "INK $01")
    sh.add([wall3_demo(art, 0x07)], "INK $07 (LIGHTER)")
    for name, fa, wa in SCHEMES[1:]:
        sh.add([wall3_demo(art, wa)], f"{name} ${wa:02X}")
    sh.heading("R3 WARRIOR: IDLE JUMP1 JUMP2 POWER WHIRL THROW BOW")
    sh.add([sprite_rgb(*art.r2[f]) for f in ["knight_idle1"] + R3_HERO[:6]], "KNIGHT")
    sh.heading("R3 MAGE: IDLE JUMP1 JUMP2 / ARCHMAGE (BOSS): IDLE CAST")
    sh.add([sprite_rgb(*art.r2[f]) for f in ("wizard_idle", "wizard_jump1", "wizard_jump2")],
           "MAGE")
    sh.add([sprite_rgb(art.r2[f][0], art.r2[f][1], 0x43) for f in ("archmage_idle",
                                                                    "archmage_cast")],
           "ARCHMAGE")
    sh.heading("R3 SPELLS AS SPRITES (LEAN SET: FLY <=2 + 1 IMPACT)")
    for cap, fly, fx in SPELL_SET:
        src = lambda f: art.spells.get(f) or art.r2[f]
        sh.add([sprite_rgb(*src(f)) for f in fly + fx], cap)
    sh.heading("R3 GOLD GLOW (SWEEP REJECTED; SYNC DECIDED)")
    fg, so, _ = art.r2["orc_walk1"]
    cells = [(c, r) for r in range(6) for c in range(3)]
    sh.add([sprite_with_cell_attrs(fg, so, glow_attrs(t, cells, "sync"), 6, 3)
            for t in (0, 2, 4, 6)], "SYNC 06>46>47>46")
    sh.add([sprite_with_cell_attrs(fg, so, glow_attrs(t, cells, "sweep"), 6, 3)
            for t in (0, 2, 4, 6)], "SWEEP")
    sh.heading("R3 HAND PASS: DEAD FRAMES + LIGHTER SPIDER")
    for f, a in (("zombie_dead", 0x04), ("orc_dead", 0x44), ("necro_dead", 0x43)):
        sh.add([sprite_rgb(art.r2[f][0], art.r2[f][1], a)], f.upper().replace("_", " "))
    sh.add([sprite_rgb(art.r2[f][0], art.r2[f][1], 0x42) for f in MONSTERS["spider"][0]],
           "SPIDER")


def glow_gif(art, path: str, nframes: int = 32):
    """Standalone strip: gold glow, SYNC only (user decision, round 4), on 4 bodies (attr-only)."""
    frames = []
    for t in range(nframes):
        s = Screen(rows=8)
        for c in range(32):
            s.glyph(c, 7, art.tiles["platform"], A_FLOOR)
        for i, (n, mode, col) in enumerate((("orc_walk1", "sync", 2), ("ogre_walk1", "sync", 9),
                                            ("dknight_walk1", "sync", 17), ("goblin_walk1", "sync", 23))):
            fg, so, _ = art.r2[n]
            h = fg.shape[0] // 8
            y0 = 7 - h
            s.sprite(n, col * 8, y0 * 8, fg, so, 0x46)
            wc = fg.shape[1] // 8
            for (c, r), a in glow_attrs(t, [(c, r) for r in range(h) for c in range(wc)], mode).items():
                s.attr[y0 + r, col + c] = a
            s.text(col, 0, n.split("_")[0].upper()[:5], 0x07, art.font)
        frames.append(Image.fromarray(s.rgb_image()).resize((256 * 3, 64 * 3), Image.NEAREST))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=40, loop=0)


def r3_bytes(art) -> list[str]:
    L = ["round 3 — tiles: walls_r3 x4 = 4 tile ids, 36 B (replace the 4 round-2 plaster ids)",
         "round 3 — sprite frames (src = W/8*H*2 raw; pool = POOLACC both facings):",
         f"  {'frame':20s} {'WxH':6s} ax {'src':>5s} {'pool':>5s}"]
    tot = {}
    def fr(n, bw, motion, grp):
        fg = art.r2[n][0]
        h, w = fg.shape
        ax = art.ax.get(n, 0)
        sb, pb = h * w // 4, pool_bytes(w, h, ax, bw, motion)
        L.append(f"  {n:20s} {w}x{h:<3d} {ax:2d} {sb:5d} {pb:5d}  {grp}{' MOTION' if motion else ''}")
        g = tot.setdefault(grp, [0, 0, 0])
        g[0] += 1; g[1] += sb; g[2] += pb
    for n in R3_HERO:
        fr(n, 24, n in R3_MOTION, "warrior" if n.startswith("knight") else "mage")
    for n in ("archmage_idle", "archmage_cast"):
        fr(n, 24, False, "archmage")
    for n in ("drain_fly1", "drain_fly2", "drain_hit"):
        fr(n, 16 if "hit" in n else 16, n in R3_MOTION, "drain")
    for n in ("zombie_dead", "orc_dead", "necro_dead") + tuple(MONSTERS["spider"][0]):
        fr(n, 32 if n.startswith("spider") else 24, n in MONSTERS["spider"][2], "handpass(replaces)")
    for g, (i, sb, pb) in tot.items():
        L.append(f"  == {g}: {i} ids, source {sb} B, pool {pb} B")
    # lean spell-sprite set (round-1 + drain)
    ids = sb = pb = 0
    for cap, fly, fx in SPELL_SET:
        for f in fly + fx:
            fg = (art.spells.get(f) or art.r2[f])[0]
            h, w = fg.shape
            ids += 1; sb += h * w // 4; pb += pool_bytes(w, h, 0, w, f in fly)
    L.append(f"  == spell sprites, lean set (5 spells): {ids} ids, source {sb} B, pool {pb} B")
    for n in art.r3_names:
        fg, so, _ = art.r2[n]
        rows = gfx_convert.pack_sprite(fg, so, "native")
        dfg, dso = gfx_convert.unpack_sprite_mask(rows, fg.shape[1], "native")
        if not (np.array_equal(dfg, fg) and np.array_equal(dso, so)):
            raise SystemExit(f"{n}: pack round-trip mismatch")
    return L


def r3_validate(art) -> list[str]:
    errs = [f"walls_r3 {n}: paper not black" for n, b in art.walls3.items() if (b["attr"] >> 3) & 7]
    for n in art.r3_names:
        w = art.r2[n][0].shape[1]
        if w > 40 or w % 8 or art.ax.get(n, 0) % 4:
            errs.append(f"{n}: width/anchor rule")
    return errs


def r3_gif_layer(art, s, t: int, top: int):
    """Rows top..top+15: warrior + mage action cycles, archmage casting Drain-style bolt,
    drain-life lane, and the gold-glow champion (sweep)."""
    T, F = art.tiles, art.font
    fl = top + 7
    for c in range(32):
        s.glyph(c, fl, T["platform"], A_FLOOR)
    # knight: idle, jump arc (game.md §2.4), power, whirl, throw, bow
    k = t % 48
    yo = [0, -4, -8, -12, -16, -16, -16, -16, -16, -12, -8, -4, 0]
    if k < 14:
        f = "knight_jump1" if k in (0, 13) else "knight_jump2"
        x, y = 8 + (min(k, 12) * 4 if k else 0), (yo[k - 1] if 1 <= k <= 13 else 0)
    else:
        seq = ["knight_idle1"] * 4 + ["knight_windup"] * 3 + ["knight_power"] * 5 + \
              ["knight_whirl"] * 6 + ["knight_throw"] * 4 + ["knight_bow"] * 8 + ["knight_idle1"] * 4
        f, x, y = seq[(k - 14) % len(seq)], 56, 0
    fg, so, _ = art.r2[f]
    ax = {"knight_windup": 4, "knight_power": 4, "knight_whirl": 8}.get(f, 0)
    s.sprite("knight", x - ax, fl * 8 - 48 + y, fg, so, 0x45)
    # mage jump
    k = t % 24
    if k < 14:
        f = "wizard_jump1" if k in (0, 13) else "wizard_jump2"
        x, y = 120 + (min(k, 12) * 4 if k else 0), (yo[k - 1] if 1 <= k <= 13 else 0)
    else:
        f, x, y = "wizard_idle", 120 + 48, 0
    fg, so, _ = art.r2[f]
    s.sprite("mage", x, fl * 8 - 48 + y, fg, so, 0x45)
    # gold glow champion (orc), sweep
    fg, so, _ = art.r2[("orc_walk1", "orc_walk2")[(t // 4) % 2]]
    x0, y0 = 28 * 8, fl * 8 - 48
    s.sprite("champion", x0, y0, fg, so, 0x46)
    for (c, r), a in glow_attrs(t, [(c, r) for r in range(6) for c in range(3)], "sweep").items():
        s.attr[y0 // 8 + r, x0 // 8 + c] = a
    s.text(25, top, "GOLD", 0x46, F)
    # band 2: archmage idle/cast + drain-life lane
    fl2 = top + 15
    for c in range(32):
        s.glyph(c, fl2, T["platform"], A_FLOOR)
    k = t % 24
    f = "archmage_idle" if k < 8 else "archmage_cast"
    fg, so, _ = art.r2[f]
    s.sprite("archmage", 0, fl2 * 8 - 48, fg, so, 0x43)
    if k >= 10:
        fg, so, a = art.spells[("lightning_fly1", "lightning_fly2")[k % 2]]
        s.sprite("death bolt", 40 + (k - 10) * 8, fl2 * 8 - 32, fg, so, 0x43)
    # drain life: mage (right) drains a zombie (left of it)
    fg, so, _ = art.r2["wizard_cast2"] if "wizard_cast2" in art.r2 else art.r2["wizard_cast1"]
    s.sprite("mage cast", 26 * 8, fl2 * 8 - 48, fg[:, ::-1], so[:, ::-1], 0x45)
    zf, zs, _ = art.r2["zombie_hurt" if k % 6 < 3 else "zombie_walk1"]
    s.sprite("zombie", 16 * 8, fl2 * 8 - 48, zf, zs, 0x04)
    if k < 18:
        fg, so, a = art.r2[("drain_fly1", "drain_fly2")[k % 2]]
        s.sprite("drain", 19 * 8 + (k % 6) * 8, fl2 * 8 - 32, fg, so, a)
    else:
        fg, so, a = art.r2["drain_hit"]
        s.sprite("drain hit", 26 * 8, fl2 * 8 - 40, fg, so, a)
    s.text(9, top + 9, "DRAIN LIFE", 0x07, F)


# ---------------------------------------------------------------------------
# Byte accounting
# ---------------------------------------------------------------------------

def asset_bytes(art: Art) -> tuple[list[str], dict]:
    lines, tot = [], {}
    def add(group, name, n):
        lines.append(f"  {group:8s} {name:18s} {n:4d} B")
        tot[group] = tot.get(group, 0) + n
    for grp, blocks in (("decor", art.decor), ("door", art.door), ("icon8", art.ic8)):
        for n in blocks:
            add(grp, n, 8 + 1)                      # glyph + attr
    for n, b in art.ic16.items():
        add("icon16", n, b["w"] * b["h"] // 8 + 1)  # 32 + attr
    for n, (fg, so, a) in art.spells.items():
        rows = gfx_convert.pack_sprite(fg, so, "native")
        dfg, dso = gfx_convert.unpack_sprite_mask(rows, fg.shape[1], "native")
        if not (np.array_equal(dfg, fg) and np.array_equal(dso, so)):
            raise SystemExit(f"spell {n}: pack round-trip mismatch")
        add("spell", n, sum(len(r) for r in rows) + 1)   # native [mask,data] + ATTR_SPRITE
    return lines, tot


# ---------------------------------------------------------------------------

def main() -> int:
    import concept_r4
    import concept_fonts
    art = Art()
    concept_r4.load(art)
    concept_fonts.load(art)
    os.makedirs(OUT, exist_ok=True)
    all_errs, report = [], []
    for lay in ("v1", "v2"):
        s, floors = build_room(art, lay)
        (panel_v1 if lay == "v1" else panel_v2)(s, art)
        scr = s.to_scr()
        open(os.path.join(OUT, f"screen_{lay}.scr"), "wb").write(scr)
        save_png(s.rgb_image(), os.path.join(OUT, f"screen_{lay}.png"))
        prow = range(20, 24) if lay == "v1" else range(22, 24)
        e, r = validate(f"screen_{lay}", s, scr, floors, prow)
        all_errs += [f"screen_{lay}: {x}" for x in e]
        report += r
    s = inventory(art)
    scr = s.to_scr()
    open(os.path.join(OUT, "inventory.scr"), "wb").write(scr)
    save_png(s.rgb_image(), os.path.join(OUT, "inventory.png"))
    e, r = validate("inventory", s, scr, [], range(0))
    all_errs += [f"inventory: {x}" for x in e]
    report += r

    lines, tot = asset_bytes(art)
    save_png(contact_sheet(art, tot), os.path.join(OUT, "concept_sheet.png"), 3)
    anim_gif(art, os.path.join(OUT, "decor_anim.gif"))
    all_errs += r2_validate(art) + r3_validate(art) + concept_r4.r4_validate(art)
    e4, rep4 = concept_r4.write_screens(art)
    ef, repf = concept_fonts.write_all(art)
    e4 += ef
    rep4 += repf
    all_errs += e4
    report += rep4
    r2_lines = r2_bytes(art) + r3_bytes(art) + concept_r4.r4_bytes(art)
    glow_gif(art, os.path.join(OUT, "boss_glow.gif"))

    print("\n".join(report))
    print("asset bytes (8x8 = 8+1 attr; 16x16 = 32+1; masked sprite = H*W/8*2+1):")
    print("\n".join(lines))
    print("  totals: " + ", ".join(f"{k} {v} B" for k, v in tot.items())
          + f"; all {sum(tot.values())} B")
    print("\n".join(r2_lines))
    if all_errs:
        print("VALIDATION FAILED:\n  " + "\n  ".join(all_errs), file=sys.stderr)
        return 1
    print("validation: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
