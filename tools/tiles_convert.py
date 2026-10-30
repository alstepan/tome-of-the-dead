#!/usr/bin/env python3
"""tiles_convert.py — Stage 3B B3B-2: approved concept grids -> engine tile / panel data.

Reads the approved concept art (assets/gfx/concept/grid/*, assets/gfx/sprites/grid/*,
the live sprite-sheet tile asm for the ids the engine already uses) and writes
cold-data DEFB tables:

  assets/gfx/tiles/tiles_common.asm   32 glyphs x 8 B + 32 attrs      (ids 0..31)
  assets/gfx/tiles/tilesets.asm       8 slot records (glyph index + attrs + flag set) + glyph pool, bank 7
  assets/gfx/tiles/tileset_ids.inc    EQUs: per-level object -> tile id
  assets/gfx/panel/panel_orn.asm      ORN_GLYPHS 8 x 8 B (+ 8 default attrs)
  assets/gfx/panel/panel_icons.asm    10 bar icons 24x16 (54 B each) + outline icons + 8x8 labels
  /private/tmp/.../scratchpad/tiles_b3b2/*.png   previews (--preview DIR)

Contract (docs/memory-map.md "3B contracts", src/level_defs.asm):
  tile ids 0..31 common, 32..63 per level (60..63 = floor-item glyphs FLASK/FOOD/WEAPON/WORN; the D8 Sanctum lectern is swapped in by 3E-T6),
  slot = 32 glyphs (ids 32..63, id order) + 32 attrs; per-level decor <= 28 ids (32..59).

Usage: python3 tools/tiles_convert.py [--check] [--preview DIR]
  --check : validate only, write nothing (CI gate).  Exit 1 on any violation.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gfx_convert  # noqa: E402  (COLOURS / attr_byte)

GRID = os.path.join(REPO, "assets/gfx/concept/grid")
SPR = os.path.join(REPO, "assets/gfx/sprites")
OUT_T = os.path.join(REPO, "assets/gfx/tiles")
OUT_P = os.path.join(REPO, "assets/gfx/panel")

# --------------------------------------------------------------------------------------
# MAPPING TABLES (edit here; everything below is mechanical)
# --------------------------------------------------------------------------------------
# Common ids 0..31.  (id, enum name, source)
#   ("zero",)                      blank glyph
#   ("live", "<asm label>", attr)  bytes of the sheet tile the engine uses today (byte-identical)
#   ("item", "<item asm>", row0, attr)  8 rows of an item sprite's DATA bytes (init_tiles .pick)
#   ("grid", "<file>", "<block>")  concept tile block; attr from its header
#   ("cell", "<file>", "<block>", k)  k-th cell of a 1-row multi-cell block (DEC1 bones)
#   ("hold",)                      reserved spare (blank, attr 0)
#   ("placeholder", attr, rows)    NO APPROVED ART: marked placeholder
# Pit caps are NOT here: T_PIT_L/T_PIT_R alias T_END_R/T_END_L (level_defs.asm), designer
# 2026-10-03: the end shape faces the hole (cap at p-1 = RIGHT-end shape = id 20, cap at
# p+3 = LEFT-end shape = id 19) which is exactly the current alias; no swap needed.
T3F = "../../sprites/grid/tiles_3f.grid"   # 3F-T8: the approved 3F common tiles (GRID-relative)
A_AIR, A_FLOOR, A_WALL, A_LAD = 0x00, 0x0F, 0x01, 0x02     # defs.asm ATTR_* defaults (depth 1)
COMMON = [
    (0,  "T_AIR",        ("zero",)),
    (1,  "T_PLAT",       ("live", "tiles_bg_platform", A_FLOOR)),
    (2,  "T_BRICK",      ("live", "tiles_bg_wall", A_WALL)),            # = T_WALL_DARK
    (3,  "T_WALLF",      ("live", "tiles_bg_wall", A_FLOOR)),
    (4,  "T_LAD_L",      ("live", "tiles_bg_ladder_l", A_LAD)),
    (5,  "T_LAD_M",      ("live", "tiles_bg_ladder_m", A_LAD)),
    (6,  "T_LAD_R",      ("live", "tiles_bg_ladder_r", A_LAD)),
    (7,  "T_HOLE_L",     ("live", "tiles_bg_ladder_l", A_LAD)),
    (8,  "T_HOLE_M",     ("live", "tiles_bg_ladder_m", A_LAD)),
    (9,  "T_HOLE_R",     ("live", "tiles_bg_ladder_r", A_LAD)),
    (10, "T_TRAP",       ("grid", "items3e.tiles", "trap")),            # 3E revealed trap plate, $42 (§1.5)
    (11, "T_DOOR_JAMB_L", ("grid", "b10_door_grate.tiles", "door_jamb_l")),  # B10 open door (was cobweb)
    (12, "T_CHAIN",      ("grid", "decor.tiles", "chain")),             # chest TR
    (13, "T_GRATE_SHUT", ("grid", T3F, "grate_shut")),                  # 3F-T8 closed lair gate, $07 (§9.7 R2)
    (14, "T_DOOR_JAMB_R", ("grid", "b10_door_grate.tiles", "door_jamb_r")),  # B10 open door (was moss)
    (15, "T_LECT_TL",    ("grid", T3F, "lectern_tl")),                  # 3F-T8 Sanctum lectern 2x2 (§9.7 R2)
    (16, "T_LECT_TR",    ("grid", T3F, "lectern_tr")),
    # D3-7 T6 (game.md §6.3): ids 17 / 18 = the dropped-ammo floor glyphs (were the drips,
    # no longer placed). Concept ammo.tiles (draft 2026-10-13, canvas review pending).
    # 3E (game.md §8.11 Q1, user-approved items3e.tiles): 17 = AMMO (daggers + arrows, one bundle,
    # $47 default; T_DAGGERS = T_ARROWS = 17), 18 = PAGES (scroll / book, $07).
    # FLOOR1: 17 / 18 no longer placed; 3F-T8: the lectern's bottom row
    (17, "T_LECT_BL",    ("grid", T3F, "lectern_bl")),
    (18, "T_LECT_BR",    ("grid", T3F, "lectern_br")),
    (19, "T_END_L",      ("live", "tiles_bg_platform_end_l", A_FLOOR)), # = T_PIT_R (cap at p+3)
    (20, "T_END_R",      ("live", "tiles_bg_platform_end_r", A_FLOOR)), # = T_PIT_L (cap at p-1)
    (21, "T_DOOR_ARCH_L", ("grid", "door.tiles", "door_arch_l")),
    (22, "T_DOOR_ARCH_R", ("grid", "door.tiles", "door_arch_r")),
    (23, "T_DOOR_L",     ("grid", "door.tiles", "door_l")),
    (24, "T_DOOR_R",     ("grid", "door.tiles", "door_r")),
    (25, "T_DOOR_LOCK",  ("grid", "door.tiles", "door_r_ring")),        # plank-R + ring/lock plate
    (26, "T_GRATE",      ("grid", "b12_gate.tiles", "gate_raised_b")),  # B12 raised portcullis, row 17 x3
    (27, "T_RUBBLE",     ("grid", "walls_r4.tiles", "rubble")),
    # contract ids 28..30 were the round-3 dither set; the approved round-4 art replaced it
    # with ragged wall fragments (concept walls_r4.tiles): mapping below, designer may remap.
    (28, "T_WALL_DITHER", ("grid", "walls_r4.tiles", "wall_worn")),
    (29, "T_WALL_PATCH", ("grid", "walls_r4.tiles", "wall_brk_top")),
    (30, "T_WALL_FADE",  ("grid", "walls_r4.tiles", "wall_brk_bot")),
    (31, "T_FREE31",     ("hold",)),                                  # DEC2: was T_BONES_3 (dropped 2026-10-26)
]
# ids whose attr follows ATTR_FLOOR[depth] / ATTR_WALL[depth] at runtime (engine patches)
FLOOR_IDS = {1, 3, 19, 20}              # platform, wall-in-floor-row, end caps (= pit caps)
WALL_IDS = {2, 28, 29, 30}
DECOR_IDS = {12}   # air-band decor: never in a floor row
LIVE_UNCHANGED = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 19, 20}   # byte-identical to init_tiles
LEGACY_ALIASED = {11, 12, 14}   # chest/zap ids reused by decor / door jambs (B3B-13) / ammo (D3-7)

# Per-level colour schemes (game.md §1.2): (ATTR_FLOOR, ATTR_WALL)
SCHEME = [(0x0F, 0x01), (0x27, 0x04), (0x17, 0x02), (0x28, 0x05),
          (0x30, 0x06), (0x38, 0x07), (0x4F, 0x41), (0x1F, 0x03)]

# Objects for per-level sets: name -> (follow_wall_ink, [frame, ...]); a frame is a 2-D list
# of (file, block, r, c) cell refs ("bm" blocks > 8x8 are cut into cells, r/c given) — built
# by obj_big()/obj_tiles() below.
BIG = "bigdecor.grid"
OBJ_SPEC = {
    # name:        (follow_wall, kind, args)
    "TORCH_TALL":  (False, "big", BIG, ["torch_tall_f1", "torch_tall_f2"]),     # 2x4, 2 frames
    "TORCH_SLIM":  (False, "big", BIG, ["torch_slim_f1", "torch_slim_f2"]),     # 1x3
    "BRAZIER_BIG": (False, "big", BIG, ["brazier_big_f1", "brazier_big_f2"]),   # 2x4
    "BANNER_TALL": (False, "big", BIG, ["banner_tall"]),                        # 2x5
    "WINDOW_ARCH": (False, "big", BIG, ["window_arch"]),                        # 3x4
    "PILLAR":      (True,  "tiles", "walls_r4.tiles", [[["pillar_l", "pillar_r"]]]),   # 2x1 repeat
    "PATCH_A":     (True,  "big", "decor_r4.grid", ["patch_a"]),                # 2x2
    "PATCH_B":     (True,  "big", "decor_r4.grid", ["patch_b"]),                # 3x2
    "BRAZIER":     (False, "tiles", "decor.tiles", [[["brazier_flame1"], ["brazier_bowl"]],
                                                    [["brazier_flame2"], ["brazier_bowl"]]]),
    "BANNER":      (False, "tiles", "decor.tiles", [[["banner_top"], ["banner_tail"]]]),
    "WINDOW_BAR":  (False, "tiles", "decor.tiles", [[["window", "window"], ["window", "window"]]]),
    "BOOKSHELF":   (False, "tiles", "decor.tiles", [[["bookshelf", "bookshelf"],
                                                     ["bookshelf", "bookshelf"]]]),
    # left the common range 2026-10-03 (ids 11/14 = door jambs): 1 per-level id each
    "COBWEB":      (False, "tiles", "decor.tiles", [[["cobweb"]]]),     # left corner (top-left anchor)
    "COBWEB_R":    (False, "mirror", "decor.tiles", [[["cobweb"]]]),    # right corner = h-mirror
    # B12 lair-exit marker (user 2026-10-05, option a): 1 per-level id on EVERY level, stamped
    # by the room builder on row 16 above the exit hole centre; never placed by decorgen.
    "GLOW":        (False, "tiles", "b12_gate.tiles", [[["gate_glow"]]]),
    "MOSS":        (False, "tiles", "decor.tiles", [[["moss"]]]),
}
# PROPOSAL (the docs leave the per-level picks to G2; designer reviews). <= 28 ids each.
# COBWEB / MOSS (per-level since 2026-10-03) are appended last so earlier ids stay stable;
# they go only where the set has room (D4 / D5 / D7 are full at 28: adding them there would
# mean cutting WINDOW_ARCH / PILLAR first, per concept-screen §3.3 -- designer's call).
# COBWEB_R (D1 decor rules 2026-10-05, concept-screen §3.3 corner rule) goes with every
# COBWEB; D1 / D3 / D8 were at the cap and drop PILLAR (2 ids) to fit it.
# GLOW (B12, user 2026-10-05 option a) is last in every set: D5 / D7 drop PILLAR, D4 drops
# WINDOW_BAR (1 id, the least-used item there) to fit it.
LEVEL_OBJECTS = [
    ["TORCH_TALL", "WINDOW_ARCH", "BANNER", "COBWEB", "MOSS", "COBWEB_R", "GLOW"],  # D1 Blue Keep
    ["PATCH_A", "PATCH_B", "TORCH_SLIM", "BRAZIER", "WINDOW_BAR", "BANNER",
     "COBWEB", "MOSS", "COBWEB_R", "GLOW"],                               # D2
    ["BRAZIER_BIG", "BANNER_TALL", "PATCH_A", "BOOKSHELF", "COBWEB", "COBWEB_R", "GLOW"],  # D3
    ["TORCH_TALL", "BANNER_TALL", "PATCH_A", "GLOW"],         # D4 Warrens (-WINDOW_BAR)
    ["BRAZIER_BIG", "WINDOW_ARCH", "PATCH_A", "GLOW"],                    # D5 Sandstone (-PILLAR)
    ["TORCH_SLIM", "BOOKSHELF", "BANNER", "PATCH_A", "PATCH_B", "WINDOW_BAR",
     "COBWEB", "MOSS", "COBWEB_R", "GLOW"],                               # D6 (-PILLAR: MEM-RECLAIM w2a,
                                                                          # never placed since 2026-10-12)
    ["TORCH_TALL", "BANNER_TALL", "PATCH_B", "GLOW"],                     # D7 Fortress (-PILLAR)
    ["BRAZIER_BIG", "BOOKSHELF", "BANNER_TALL", "TORCH_SLIM", "COBWEB", "COBWEB_R", "GLOW"],  # D8
]
LECTERN = ("decor_r4.grid", "lectern")      # D8 Sanctum only: 2x2 attackable, ids 60..63 swapped in by T6
                                            # (tileset_lectern); the D8 slot itself carries the items
# 3E floor-item class glyphs in slot 28..31 (ids 60..63) of EVERY depth (game.md §8.11 Q1)
ITEM_SLOTS = [("T_FLASK", ("item", "item_potion", 0, 0x42)),    # the old T_POTION glyph bytes
              ("T_FOOD", ("grid", "items3e.tiles", "food")),
              ("T_WEAPON", ("grid", "items3e.tiles", "weapon")),
              ("T_WORN", ("grid", "items3e.tiles", "worn"))]

# Panel: bar icons (concept_r4.py MAGE_BAR / WARRIOR_BAR inks = approved screen) in id order
BAR_ICONS = [("STAFF", "staff2416", 0x46), ("SPARK", "spark2416", 0x43),
             ("FIREBOLT", "firebolt2416", 0x42), ("FROST", "frost2416", 0x45),
             ("DRAIN", "drain2416", 0x43), ("LIGHTNING", "lightning2416", 0x47),
             ("SWORD", "sword2416", 0x47), ("POWER", "power2416", 0x42),
             ("WHIRL", "whirl2416", 0x47), ("BAG", "bag2416", 0x06)]
# (AMMO-COUNT: the Warrior's dagger / bow slots are 16x16 quick-style icons now: no 24x16 art)
ORN_ORDER = ["orn_cap_l", "orn_link", "orn_bar", "orn_wing_l", "orn_skull_l", "orn_skull_r",
             "orn_wing_r", "orn_cap_r"]     # layout order: cap, chain, wing skull skull wing, chain, cap
LABELS = [("HEART", "icons8.tiles", "heart"), ("DROP", "icons8.tiles", "drop"),
          ("DRUMSTICK", "icons8.tiles", "drumstick"), ("KEY", "item_key", None)]

# --------------------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------------------
HDR = re.compile(r"^===\s*(\S+)(?:\s+(\d+)x(\d+))?(.*)$")
errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


_cache: dict = {}


def blocks(fname: str) -> dict:
    """concept block file -> {name: {w,h,rows[str],attr,cells|None}}"""
    if fname in _cache:
        return _cache[fname]
    path = os.path.join(GRID, fname)
    out, cur = {}, None
    for raw in open(path).read().splitlines():
        line = raw.strip()
        m = HDR.match(line)
        if m:
            name, w, h, rest = m.group(1), int(m.group(2) or 8), int(m.group(3) or 8), m.group(4)
            ink = paper = 0
            bright, cells = False, None
            for tok in rest.split():
                if tok.startswith("cells:"):
                    cells = [[int(v, 16) for v in r.split(",")] for r in tok[6:].split(";")]
                elif tok.startswith("ink:"):
                    ink = gfx_convert.COLOURS[tok[4:]]
                elif tok.startswith("paper:"):
                    paper = gfx_convert.COLOURS[tok[6:]]
                elif tok == "bright":
                    bright = True
            cur = out[name] = {"w": w, "h": h, "rows": [], "cells": cells,
                               "attr": gfx_convert.attr_byte(ink, paper, bright)}
        elif cur and len(line) == cur["w"] and set(line) <= set("#.") and len(cur["rows"]) < cur["h"]:
            cur["rows"].append(line)
    for n, b in out.items():
        if len(b["rows"]) != b["h"]:
            fail(f"{fname}:{n}: {len(b['rows'])} rows, want {b['h']}")
    _cache[fname] = out
    return out


def pack_rows(rows) -> bytes:
    """rows of '#'/'.' chars (width multiple of 8) -> row-major bytes, MSB left."""
    out = bytearray()
    for r in rows:
        for x in range(0, len(r), 8):
            v = 0
            for ch in r[x:x + 8]:
                v = (v << 1) | (ch == "#")
            out.append(v)
    return bytes(out)


def tile8(fname: str, name: str):
    b = blocks(fname)[name]
    assert b["w"] == 8 and b["h"] == 8, (fname, name)
    return pack_rows(b["rows"]), b["attr"]


def cells_of(fname: str, name: str):
    """big block -> 2-D list of (glyph8, attr) cells."""
    b = blocks(fname)[name]
    out = []
    for r in range(b["h"] // 8):
        row = []
        for c in range(b["w"] // 8):
            g = pack_rows([s[c * 8:c * 8 + 8] for s in b["rows"][r * 8:r * 8 + 8]])
            row.append((g, b["cells"][r][c] if b["cells"] else b["attr"]))
        out.append(row)
    return out


def asm_bytes(path: str, label: str) -> bytes:
    """bytes of the DEFB lines directly after `label:` (until the next label/blank/EQU)."""
    txt = open(path).read().splitlines()
    out, on = bytearray(), False
    for ln in txt:
        if re.match(rf"^{re.escape(label)}:", ln):
            on = True
            continue
        if on:
            m = re.match(r"^\s+DEFB\s+([^;]*)", ln)
            if m:
                out += bytes(int(v.strip().lstrip("$"), 16) for v in m.group(1).split(","))
            elif ln.strip() and not ln.strip().startswith(";") or not ln.strip():
                break
    return bytes(out)


def live_tile(label: str) -> bytes:
    for f in ("tiles_bg.asm", "tiles_fx.asm"):
        b = asm_bytes(os.path.join(SPR, f), label)
        if b:
            return b[:8]
    fail(f"live tile label {label} not found")
    return bytes(8)


def item_tile(name: str, row0: int) -> bytes:
    b = asm_bytes(os.path.join(SPR, name + ".asm"), name)
    data = b[1::2]                       # [mask,data] pairs, 1 col: data = odd bytes
    return bytes(data[row0:row0 + 8])


def key8() -> tuple[bytes, int]:
    rows = []
    body = False
    for ln in open(os.path.join(SPR, "grid/item_key.grid")).read().splitlines():
        if ln == "#":                      # end of the header comment block
            body = True
        elif body and len(ln) == 8:
            rows.append(ln)
    assert len(rows) == 8
    return pack_rows(["".join("#" if ch == "#" else "." for ch in r) for r in rows]), 0x46


# --------------------------------------------------------------------------------------
# enum cross-check (defs.asm + level_defs.asm)
# --------------------------------------------------------------------------------------
def enum_values() -> dict:
    vals: dict = {}
    pend = []
    for f in ("src/defs.asm", "src/level_defs.asm"):
        for ln in open(os.path.join(REPO, f)).read().splitlines():
            m = re.match(r"^((?:T|TF)_\w+)\s+EQU\s+(%?\w+)", ln)
            if m:
                pend.append((m.group(1), m.group(2)))
    for _ in range(4):
        for n, v in pend:
            if v.isdigit():
                vals[n] = int(v)
            elif v.startswith("%"):
                vals[n] = int(v[1:], 2)
            elif v in vals:
                vals[n] = vals[v]
    return vals


# --------------------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------------------
def build_common(enum):
    glyphs, attrs, names = [bytes(8)] * 32, [0] * 32, [""] * 32
    notes = [""] * 32
    for i, n, src in COMMON:
        if enum.get(n) != i:
            fail(f"common id {i} {n}: level_defs/defs enum says {enum.get(n)}")
        names[i] = n
        k = src[0]
        if k == "zero":
            g, a = bytes(8), 0
        elif k == "hold":
            g, a = bytes(8), 0
        elif k == "live":
            g, a = live_tile(src[1]), src[2]
        elif k == "item":
            g, a = item_tile(src[1], src[2]), src[3]
        elif k == "grid":
            g, a = tile8(src[1], src[2])
        elif k == "cell":                       # cell src[3] (left to right) of a 1-row block
            g, a = cells_of(src[1], src[2])[0][src[3]]
        elif k == "placeholder":
            g, a = pack_rows(src[2]), src[1]
            notes[i] = "PLACEHOLDER (no approved art)"
        else:
            raise SystemExit(f"bad source {src}")
        glyphs[i], attrs[i] = g, a
    # enum ids not covered (common range)
    if sorted(i for i, _, _ in COMMON) != list(range(32)):
        fail("COMMON table must cover ids 0..31 exactly once")
    return glyphs, attrs, names, notes


def obj_frames(name):
    """object -> list of frames; frame = 2-D list of (glyph, attr)."""
    follow, kind, fname, spec = OBJ_SPEC[name]
    frames = []
    if kind == "big":
        for bn in spec:
            frames.append(cells_of(fname, bn))
    else:
        for fr in spec:
            frames.append([[tile8(fname, bn) for bn in row] for row in fr])
        if kind == "mirror":            # horizontal mirror of each cell, cells right-to-left
            flip = lambda g: bytes(int(f"{b:08b}"[::-1], 2) for b in g)  # noqa: E731
            frames = [[[(flip(g), a) for g, a in row[::-1]] for row in fr] for fr in frames]
    return follow, frames


def build_level(d):
    """-> (glyphs[32], attrs[32], ids{name: [frame -> [[id]]]}, lectern, n) for depth d (1..8)."""
    wall_attr = SCHEME[d - 1][1]
    slots: dict = {}
    glyphs, attrs = [bytes(8)] * 32, [0] * 32
    ids = {}
    nxt = 0
    for on in LEVEL_OBJECTS[d - 1]:
        follow, frames = obj_frames(on)
        fid = []
        for fr in frames:
            grid = []
            for row in fr:
                irow = []
                for g, a in row:
                    if follow:
                        if (a >> 3) & 7:
                            fail(f"D{d} {on}: follow-wall cell has non-black paper")
                        a = wall_attr
                    key = (g, a)
                    if key not in slots:
                        if nxt >= 28:
                            fail(f"D{d}: > 28 decor ids (cut window_arch / pillar first)")
                            break
                        slots[key] = nxt
                        glyphs[nxt], attrs[nxt] = g, a
                        nxt += 1
                    irow.append(slots.get(key, 0))
                grid.append(irow)
            fid.append(grid)
        ids[on] = fid
    for k, (_, src) in enumerate(ITEM_SLOTS):
        if src[0] == "item":
            glyphs[28 + k], attrs[28 + k] = item_tile(src[1], src[2]), src[3]
        else:
            glyphs[28 + k], attrs[28 + k] = tile8(src[1], src[2])
    lect = [[28 + 2 * r + c for c in range(2)] for r in range(2)] if d == 8 else None
    return glyphs, attrs, ids, lect, nxt


def level_flags(d, ids, lect, enum):
    """B3B-8: TILE_FLAGS of slot ids 32..63 (src/level_defs.asm TF_*, loaded with the set).
    Solidity = the cell class (game.md §1.2 "Solidity of decor"): the wall-ink objects
    (OBJ_SPEC follow_wall: pillar, plaster patches) are wall-set variants -> TF_SOLID (they
    only ever replace solid wall cells); everything else is non-solid air-band decor.
    TF_ANIM = a glyph-swap cell (its id differs between the object's frames, both frames'
    ids); attr-cycle cells are the deriver's business (B3B-9/-10). D8 lectern 60..63 =
    TF_SOLID | TF_ATTACK (game.md §1.3)."""
    fl = [0] * 32
    for on, frames in ids.items():
        follow = OBJ_SPEC[on][0]
        for grid in frames:
            for row in grid:
                for v in row:
                    if follow and not on.startswith("PATCH"):
                        fl[v] |= enum["TF_SOLID"]
        for f in frames[1:]:
            for r, row in enumerate(f):
                for c, v in enumerate(row):
                    v0 = frames[0][r][c]
                    if v != v0:
                        fl[v] |= enum["TF_ANIM"]
                        fl[v0] |= enum["TF_ANIM"]
    return fl                   # 28..31 (ids 60..63) = floor items: flags 0 (the lectern: tileset_lectern)


def validate_common(glyphs, attrs):
    for i, a in enumerate(attrs):
        if a & 0x80:
            fail(f"common {i}: FLASH set")
    for i in DECOR_IDS & FLOOR_IDS:
        fail(f"decor id {i} is a floor id")
    for i in DECOR_IDS:
        if (attrs[i] >> 3) & 7:
            fail(f"decor id {i}: paper not black (air band; F9)")
    for i in FLOOR_IDS:
        if (attrs[i] >> 3) & 7 != 1:
            fail(f"floor id {i}: paper not blue")
    for i in WALL_IDS:
        if (attrs[i] >> 3) & 7:
            fail(f"wall id {i}: paper not black")
    # byte-identity of the live ids vs the engine's own sources (re-derived independently)
    for i, n, src in COMMON:
        if i in LIVE_UNCHANGED and src[0] in ("live", "item"):
            again = live_tile(src[1]) if src[0] == "live" else item_tile(src[1], src[2])
            if again != glyphs[i]:
                fail(f"common {i} {n} differs from live bitmap")
    if len(LIVE_UNCHANGED & {i for i, _, s in COMMON if s[0] in ("live", "item", "zero")}) \
            != len(LIVE_UNCHANGED):
        fail("LIVE_UNCHANGED id has a non-live source")


def validate_level(d, glyphs, attrs, nxt):
    for i in range(32):
        if (attrs[i] >> 3) & 7 and glyphs[i] != bytes(8):
            fail(f"D{d} slot {i}: paper not black (decor must be air-band)")
        if attrs[i] & 0x80:
            fail(f"D{d} slot {i}: FLASH")
    for k in range(4):
        if not any(glyphs[28 + k]):
            fail(f"D{d}: slot {28 + k} (id {60 + k}) must hold a floor-item glyph")
    if nxt > 28:
        fail(f"D{d}: {nxt} ids")


# --------------------------------------------------------------------------------------
# emit
# --------------------------------------------------------------------------------------
def defb(bs: bytes, per=8) -> list[str]:
    return ["        DEFB " + ",".join(f"${b:02X}" for b in bs[i:i + per]) for i in range(0, len(bs), per)]


def emit_common(g, a, names, notes):
    L = ["; ============================================================================",
         "; tiles_common — common tile set, ids 0..31 (8 B glyph each + 1 attr each)",
         "; GENERATED by tools/tiles_convert.py (edit the tool / concept grids, not this file)",
         "; Sources     : sprite-sheet tiles (live ids, byte-identical), concept grids decor.tiles /",
         ";               door.tiles / walls_r4.tiles / (bones.tiles/cauldron: DEC2-dropped); mapping table: top of the tool.",
         "; Layout      : tiles_common_glyphs = 32 x 8 B (id order, MSB = left); tiles_common_attrs",
         ";               = 32 B (default depth-1 attrs: engine patches ATTR_FLOOR/ATTR_WALL ids).",
         "; Size        : 256 + 32 = 288 B.   Clash: one ink+paper per tile by construction.",
         "; Aliases     : T_WALL_DARK = T_BRICK (2), T_PIT_R = T_END_L (19), T_PIT_L = T_END_R (20).",
         "; Retired ids : 11-14 / 17-18 were chest / zap: 11/14 = open-door jambs, 12/13 = decor",
         ";               (cobweb/moss moved per-level), 17 = T_AMMO (daggers + arrows), 18 = T_PAGES",
         ";               (3E, items3e.tiles).  Id 10 = T_TRAP (the potion moved to id 60 FLASK).",
         "; ============================================================================",
         "tiles_common_glyphs:"]
    for i in range(32):
        L.append(f"        DEFB " + ",".join(f"${b:02X}" for b in g[i]) +
                 f"    ; {i:2d} {names[i]}" + (f"  [{notes[i]}]" if notes[i] else ""))
    L.append("tiles_common_attrs:")
    for i in range(32):
        L.append(f"        DEFB ${a[i]:02X}    ; {i:2d} {names[i]}")
    L += ["TILES_COMMON_LEN EQU $ - tiles_common_glyphs", ""]
    return "\n".join(L)


def emit_tilesets(sets):
    """MEM-RECLAIM w2a: the 8 slots share one glyph pool + one flag-set table (dedup).
    -> (asm text, (pool glyphs, flag sets))."""
    pool, pidx, fsets, fidx, recs = [], {}, [], {}, []
    for d, (g, a, n, fl) in enumerate(sets, 1):
        ix = []
        for i in range(32):
            gb = bytes(g[i])
            if gb not in pidx:
                pidx[gb] = len(pool)
                pool.append(gb)
            ix.append(pidx[gb])
        fb = bytes(fl)
        if fb not in fidx:
            fidx[fb] = len(fsets)
            fsets.append(fb)
        recs.append((d, ix, bytes(a), fidx[fb], n))
    if len(pool) > 256 or len(fsets) > 8:
        fail(f"tileset pool {len(pool)} glyphs / {len(fsets)} flag sets: over the 1-byte index")
    total = 8 * 65 + 32 * len(fsets) + 8 * len(pool)
    L = ["; ============================================================================",
         "; tilesets — 8 per-level tile sets, bank-7 deduplicated format (src/level_defs.asm TSET_*)",
         "; GENERATED by tools/tiles_convert.py (MEM-RECLAIM w2a: was 8 x 320 B raw slots)",
         "; tset_slots: 8 records x 65 B (TSET_STRIDE), record i = depth i+1:",
         ";   +0  TSET_GIDX  32 B: tset_pool glyph index of ids 32..63 (id order)",
         ";   +32 TSET_ATTRS 32 B: attrs of ids 32..63",
         ";   +64 TSET_FSET   1 B: tset_fsets index (TILE_FLAGS of ids 32..63, 32 B a set:",
         ";                        TF_SOLID wall-ink objects, TF_ANIM glyph swaps)",
         "; tset_fsets: the distinct flag sets; tset_pool: the distinct 8-B glyphs.",
         "; Ids 60..63 (record glyph 28..31) = floor-item glyphs FLASK FOOD WEAPON WORN on every depth",
         ";   (the D8 lectern is NOT in a slot: swapped in by T6, game.md §8.11 Q1).",
         f"; Total {total} B = 520 + {len(fsets)} x 32 + {len(pool)} x 8 (raw: 2560).  Object -> id: tileset_ids.inc",
         "; Attr rule: wall-ink objects (plaster patches) carry ATTR_WALL[depth]; paper black.",
         "; ============================================================================",
         "tilesets:",
         "tset_slots:"]
    for d, ix, a, fi, n in recs:
        L.append(f"tileset_d{d}:                       ; D{d}: ATTR_FLOOR ${SCHEME[d-1][0]:02X} "
                 f"ATTR_WALL ${SCHEME[d-1][1]:02X}, {n} decor ids")
        L += ["        ; glyph indices"] + [ "        DEFB " + ",".join(f"{v:3d}" for v in ix[k:k + 8])
                                             for k in range(0, 32, 8)]
        L += ["        ; attrs"] + defb(a, 8)
        L.append(f"        DEFB {fi}                    ; flag set")
    L.append("tset_fsets:")
    for i, fb in enumerate(fsets):
        L += [f"        ; flag set {i}"] + defb(fb, 8)
    L.append("tset_pool:")
    for i, gb in enumerate(pool):
        L.append("        DEFB " + ",".join(f"${b:02X}" for b in gb) + f"    ; {i}")
    L += ["tilesets_end:", f"TSET_NPOOL EQU {len(pool)}", f"TSET_NFSET EQU {len(fsets)}", ""]
    return "\n".join(L), total


def emit_ids(all_ids):
    L = ["; tileset_ids.inc — per-level object -> tile id (GENERATED by tools/tiles_convert.py)",
         "; TS<depth>_<OBJECT>_F<frame>_R<row>C<col> = tile id (32..59); frames = glyph-swap steps.",
         "; Pure EQUs (emit no bytes).  D8 lectern: TS8_LECTERN_R<r>C<c> = 60..63.", ""]
    for d, (ids, lect) in enumerate(all_ids, 1):
        for on, frames in ids.items():
            for f, grid in enumerate(frames):
                for r, row in enumerate(grid):
                    for c, v in enumerate(row):
                        L.append(f"TS{d}_{on}_F{f+1}_R{r}C{c}".ljust(34) + f" EQU {32+v}")
        if lect:
            for r in range(2):
                for c in range(2):
                    L.append(f"TS8_LECTERN_R{r}C{c}".ljust(34) + f" EQU {32+lect[r][c]}")
    return "\n".join(L) + "\n"


def icon24(name):
    b = blocks("icons24x16.grid")[name]
    assert b["w"] == 24 and b["h"] == 16
    return pack_rows(b["rows"]), b["attr"]


def empty24():
    rows = [["."] * 24 for _ in range(16)]
    for x in range(0, 24, 2):
        rows[0][x] = rows[15][x] = "#"
    for y in range(0, 16, 2):
        rows[y][0] = rows[y][23] = "#"
    return pack_rows(["".join(r) for r in rows])


def cell_attrs(a, cw, ch):
    return bytes([a] * (cw * ch))


def emit_panel():
    icons = []
    for nm, blk, ink in BAR_ICONS:
        bm, a0 = icon24(blk)
        if (ink >> 3) & 7:
            fail(f"icon {nm}: paper not black")
        if (a0 & 7) != (ink & 7):
            fail(f"icon {nm}: inventory ink {a0 & 7} != approved-screen ink {ink & 7}")
        icons.append((nm, bm, cell_attrs(ink, 3, 2)))
    e24 = (empty24(), cell_attrs(0x01, 3, 2))
    e16bm = pack_rows(blocks("icons16.grid")["empty"]["rows"])
    e16 = (e16bm, cell_attrs(0x01, 2, 2))
    L = ["; ============================================================================",
         "; panel_icons — concept-screen §5/§6 panel glyphs (unmasked, opaque; PAPER black)",
         "; GENERATED by tools/tiles_convert.py.  Source: icons24x16.grid (10 bar icons; inks =",
         "; approved screen tools/concept_r4.py), icons16.grid empty, icons8.tiles labels, item_key.",
         "; Bar icon record (ICON_LEN 54 B) : +0 bitmap 16 rows x 3 B (row-major, MSB = left)",
         ";                                   +48 attrs 6 B (cell row-major, 3 cols x 2 rows).",
         "; Normal-state attrs shown; engine ORs state: selected = paper blue, greyed = $07.",
         "; ============================================================================",
         "ICON_LEN        EQU 54", "ICON_ATTR_OFF   EQU 48", "icon_tab:"]
    for i, (nm, bm, at) in enumerate(icons):
        L.append(f"ICON_{nm}".ljust(18) + f" EQU {i}")
    for nm, bm, at in icons:
        L.append(f"icon_{nm.lower()}:")
        L += defb(bm, 12) + ["        ; attrs"] + defb(at, 6)
    L += ["ICON_COUNT EQU 10", "icon_tab_end:", "        ASSERT icon_tab_end - icon_tab == ICON_COUNT * ICON_LEN", "",
          "; outline icons (empty slot): 24x16 (54 B, ink $01) and 16x16 gear (32 B + 4 attrs)",
          "; empty24 = dotted outline per concept_r4.empty_slot24 rule; empty16 = icons16.grid 'empty'.",
          "icon_empty24:"] + defb(e24[0], 12) + ["        ; attrs"] + defb(e24[1], 6) + \
        ["icon_empty16:"] + defb(e16[0], 8) + ["        ; attrs"] + defb(e16[1], 4)
    # labels
    L += ["", "; 8x8 labels (row 21 / key slot): 8 B glyph + 1 attr each", "ICON8_LEN EQU 9", "labels8:"]
    lab = []
    for nm, f, b in LABELS:
        g, a = key8() if f == "item_key" else tile8(f, b)
        if (a >> 3) & 7:
            fail(f"label {nm}: paper not black")
        lab.append((nm, g, a))
        L.append(f"label_{nm.lower()}:")
        L += defb(g, 8) + [f"        DEFB ${a:02X}    ; attr"]
    L += ["labels8_end:", "        ASSERT labels8_end - labels8 == 4 * ICON8_LEN", ""]
    if len(icons) * 54 != 540:
        fail("icon bytes")
    return "\n".join(L), icons, e24, e16, lab


def emit_orn():
    L = ["; ============================================================================",
         "; panel_orn — ORN_GLYPHS (row 17 ornament, 8 glyphs x 8 B = 64 B, src/level_defs.asm)",
         "; GENERATED by tools/tiles_convert.py.  Source: concept panel_r4.tiles.  NOT tile ids;",
         "; same on every level, attr = ATTR_FLOOR[depth] (default $0F shown).  Indices:",
         "; " + "  ".join(f"{i}={n[4:]}" for i, n in enumerate(ORN_ORDER)),
         "; Row-17 layout (concept §3.3): cap_l, chain (link/bar alternating), wing_l skull_l",
         "; skull_r wing_r at cols 14-17, chain, cap_r.  Boot copies orn_glyphs to ORN_GLYPHS.",
         "; ============================================================================",
         "orn_glyphs:"]
    gl = []
    for i, n in enumerate(ORN_ORDER):
        g, a = tile8("panel_r4.tiles", n)
        if a != 0x0F:
            fail(f"{n}: attr ${a:02X} != floor $0F")
        gl.append(g)
        L.append("        DEFB " + ",".join(f"${b:02X}" for b in g) + f"    ; {i} {n}")
    L += ["orn_glyphs_end:", "        ASSERT orn_glyphs_end - orn_glyphs == 64"]
    for i, n in enumerate(ORN_ORDER):
        L.append(f"ORN_{n[4:].upper()}".ljust(18) + f" EQU {i}")
    L.append("")
    return "\n".join(L), gl


# --------------------------------------------------------------------------------------
# preview (PNG)
# --------------------------------------------------------------------------------------
PAL = {0: (0, 0, 0), 1: (0, 0, 0xCD), 2: (0xCD, 0, 0), 3: (0xCD, 0, 0xCD), 4: (0, 0xCD, 0),
       5: (0, 0xCD, 0xCD), 6: (0xCD, 0xCD, 0), 7: (0xCD, 0xCD, 0xCD)}


def rgb(c, bright):
    r = PAL[c]
    return tuple(255 if (bright and v) else v for v in r)


def draw_cell(img, x0, y0, glyph, attr, scale=4):
    ink, paper, br = attr & 7, (attr >> 3) & 7, bool(attr & 0x40)
    px = img.load()
    for y in range(len(glyph) // 1):
        for x in range(8):
            col = rgb(ink, br) if glyph[y] & (0x80 >> x) else rgb(paper, br)
            for sy in range(scale):
                for sx in range(scale):
                    px[x0 + x * scale + sx, y0 + y * scale + sy] = col


def preview(dirpath, cg, ca, names, sets, all_ids, icons, e24, e16, lab, orn):
    from PIL import Image
    os.makedirs(dirpath, exist_ok=True)
    S = 4
    cell = 8 * S + 4

    def sheet(items, cols, fn):
        rows = (len(items) + cols - 1) // cols
        img = Image.new("RGB", (cols * cell + 4, rows * cell + 4), (40, 40, 60))
        for k, (g, a) in enumerate(items):
            draw_cell(img, 4 + (k % cols) * cell, 4 + (k // cols) * cell, g, a, S)
        img.save(os.path.join(dirpath, fn))

    sheet([(cg[i], ca[i]) for i in range(32)], 16, "common.png")
    for d, (g, a, n) in enumerate(sets, 1):
        # glyph sheet (32 slots) + an object strip row per object frame
        img = Image.new("RGB", (16 * cell + 4, 2 * cell + 4 + 0), (40, 40, 60))
        for k in range(32):
            draw_cell(img, 4 + (k % 16) * cell, 4 + (k // 16) * cell, g[k], a[k], S)
        img.save(os.path.join(dirpath, f"tileset_d{d}_slots.png"))
        ids, lect = all_ids[d - 1]
        W = 12 * cell
        objs = [(on, f, grid) for on, fr in ids.items() for f, grid in enumerate(fr)]
        # lay objects left-to-right with wrap
        x = y = 4
        rowh = 0
        placed = []
        for on, f, grid in objs:
            w, h = len(grid[0]) * cell, len(grid) * cell
            if x + w > 14 * cell:
                x, y, rowh = 4, y + rowh + 8, 0
            placed.append((x, y, grid))
            x += w + 8
            rowh = max(rowh, h)
        img = Image.new("RGB", (14 * cell + 8, y + rowh + 8), (40, 40, 60))
        for px_, py_, grid in placed:
            for r, row in enumerate(grid):
                for c, v in enumerate(row):
                    draw_cell(img, px_ + c * cell, py_ + r * cell, g[v], a[v], S)
        img.save(os.path.join(dirpath, f"tileset_d{d}_objects.png"))
    # panel: icons 24x16 (scale 3) with normal / selected states
    S2 = 3
    img = Image.new("RGB", (13 * (24 * S2 + 6) + 6, 2 * (16 * S2 + 6) + 6 + 40), (40, 40, 60))
    pxs = img.load()

    def draw_icon(x0, y0, bm, at, cw, ch, sel=False):
        for r in range(ch * 8):
            for c in range(cw * 8):
                a = at[(r // 8) * cw + c // 8]
                if sel:
                    a = (a & 0xC7) | (1 << 3)
                bit = bm[r * cw + c // 8] & (0x80 >> (c % 8))
                col = rgb(a & 7, bool(a & 0x40)) if bit else rgb((a >> 3) & 7, bool(a & 0x40))
                for sy in range(S2):
                    for sx in range(S2):
                        pxs[x0 + c * S2 + sx, y0 + r * S2 + sy] = col

    allic = [(bm, at) for _, bm, at in icons] + [e24]
    for k, (bm, at) in enumerate(allic):
        draw_icon(6 + k * (24 * S2 + 6), 6, bm, at, 3, 2)
        draw_icon(6 + k * (24 * S2 + 6), 6 + 16 * S2 + 6, bm, at, 3, 2, sel=True)
    img.crop((0, 0, img.width, 2 * (16 * S2 + 6) + 6)).save(os.path.join(dirpath, "panel_icons.png"))
    items = [(g, a) for _, g, a in lab] + [(orn[i], 0x0F) for i in range(8)]
    sheet(items, 12, "panel_labels_orn.png")


# --------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--preview", metavar="DIR")
    args = ap.parse_args()
    enum = enum_values()
    cg, ca, names, notes = build_common(enum)
    validate_common(cg, ca)
    sets, all_ids = [], []
    for d in range(1, 9):
        g, a, ids, lect, n = build_level(d)
        validate_level(d, g, a, n)
        sets.append((g, a, n, level_flags(d, ids, lect, enum)))
        all_ids.append((ids, lect))
    # ids referenced by every object exist (< 28, glyph non-blank)
    for d, (ids, lect) in enumerate(all_ids, 1):
        for on, fr in ids.items():
            for grid in fr:
                for row in grid:
                    for v in row:
                        if not 0 <= v < 28:
                            fail(f"D{d} {on}: id slot {v} out of range")
    panel_txt, icons, e24, e16, lab = emit_panel()
    orn_txt, orn = emit_orn()
    common_txt = emit_common(cg, ca, names, notes)
    sets_txt, sets_len = emit_tilesets([(g, bytes(a), n, fl) for g, a, n, fl in sets])
    # byte counts vs contract
    if len(cg) * 8 != 256 or len(ca) != 32:
        fail("common size")
    if sum(1 for _ in sets) != 8 or any(len(g) != 32 or len(a) != 32 or len(fl) != 32
                                        for g, a, _, fl in sets):
        fail("tileset slot size")
    if len(orn) * 8 != 64:
        fail("ORN size")
    print(f"common: 32 glyphs 256 B + 32 attrs = 288 B; tilesets: {sets_len} B deduplicated (raw 8 x 320 = 2560); "
          f"ORN 64 B; bar icons 10 x 54 = 540 B (+ empty24 54, empty16 36, labels 4 x 9)")
    print("decor ids per level:", ", ".join(f"D{d}={n}" for d, (_, _, n, _) in enumerate(sets, 1)),
          "(cap 28; ids 60..63 = floor-item glyphs on every depth)")
    if errors:
        print("VALIDATION FAILED:")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print("validation: OK (enum ids, byte counts, attr legality, no decor in floor rows, live ids identical)")
    if args.check:
        return
    os.makedirs(OUT_T, exist_ok=True)
    os.makedirs(OUT_P, exist_ok=True)
    open(os.path.join(OUT_T, "tiles_common.asm"), "w").write(common_txt)
    open(os.path.join(OUT_T, "tilesets.asm"), "w").write(sets_txt)
    open(os.path.join(OUT_T, "tileset_ids.inc"), "w").write(emit_ids(all_ids))
    open(os.path.join(OUT_P, "panel_icons.asm"), "w").write(panel_txt)
    open(os.path.join(OUT_P, "panel_orn.asm"), "w").write(orn_txt)
    if args.preview:
        preview(args.preview, cg, ca, names, [x[:3] for x in sets], all_ids, icons, e24, e16, lab, orn)
        print("previews ->", args.preview)


if __name__ == "__main__":
    main()
