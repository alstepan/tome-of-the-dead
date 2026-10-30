#!/usr/bin/env python3
"""icons16.py — IC1: the 45 true 16x16 item icons -> raw DEFB table + review page.

Source (the single source of truth, hand-authored, deterministic):
  assets/gfx/icons/<name>.grid   16 rows x 16 chars, '#' ink, '.' paper ('# ' lines = comments).
  <name> = the IT_* type name lower-cased without "IT_" (f_carrot .. c_grave) for the 39 bag
  types, ph_weapon / ph_armour / ph_helmet / ph_charm for the 4 empty-worn-slot placeholders,
  ammo_dagger / ammo_arrow for the 2 floor-ammo counters (FLOOR1; IT_DAGGER / IT_ARROW).

Writes:
  assets/gfx/icons/icons16.asm       icons16: 43 x 32 B raw (the tests' reference, under IF 0) +
                                     icpk_idx / icpk, the packed form the build holds (MEM-RECLAIM w2c)
  assets/gfx/icons/icons16.svg.html  review page (x4 per class, x1 row, bag/worn simulation)

Format (game.md §8.11 Q5): 1 bit, NO mask, 32 B per icon: rows 0..15 top-down, each row the
left byte then the right byte, bit 7 = leftmost pixel, set = ink, clear = paper. Drawn as a COPY
into 2x2 byte-aligned cells. Index = type - IT_BAG_LO (0..38); placeholders at 39 + worn slot
(weapon, armour, helmet, charm); 43 / 44 = floor ammo (IT_DAGGER, IT_ARROW: ITEM_INK). One ink per icon = it_tab / items_model.ITEM_INK (paper black;
page cursor = paper blue); placeholders ink $05.

Validation (exit 1 on any failure): every grid 16x16 of '#'/'.' only; the 1-px margin (row 0,
row 15, col 0, col 15) is paper; no empty icon; the 43 bitmaps pairwise distinct; the index map
matches src/item_defs.asm (type - IT_BAG_LO, IT_COUNT - IT_BAG_LO = 39 bag types; ammo 43/44);
each ink is a
legal non-black, non-blue ink on black paper and on blue cursor paper; attribute clash: every
8x8 cell of every icon uses exactly that one ink + paper (true by construction: 1 bit, 1 attr);
round-trip: the emitted DEFB text is parsed back and must equal the grids bit for bit.

Usage: python3 tools/icons16.py [--check]     (--check: validate + round-trip, write nothing)
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import items_model as IM  # noqa: E402  (ITEM_INK = the it_tab ink source, D = item_defs EQUs)

ICON_DIR = os.path.join(REPO, "assets/gfx/icons")
OUT_ASM = os.path.join(ICON_DIR, "icons16.asm")
OUT_HTML = os.path.join(ICON_DIR, "icons16.svg.html")
W = H = 16
ICON_BYTES = W // 8 * H                      # 32
PH_INK = 0x05                                # §8.11 Q5: placeholder ink, dim cyan
CURSOR_PAPER = 1                             # §8.11 Q3: page cursor = paper blue
PH_NAMES = ["ph_weapon", "ph_armour", "ph_helmet", "ph_charm"]   # index 39 + worn slot
AMMO_NAMES = [("ammo_dagger", "IT_DAGGER"), ("ammo_arrow", "IT_ARROW")]  # index 43, 44 (FLOOR1)
N_ICONS = 39 + len(PH_NAMES) + len(AMMO_NAMES)                     # 45 logical indices
# FLOOR1 (user 2026-10-27): the 3 potions share ONE shape (p_heal's), told apart by their ink
# (it_tab: Heal $42 red, Mana $45 cyan, Cure $44 green); p_mana / p_cure keep their grids
# (review page) but get no table entry: logical 6 / 7 -> physical 5 (icons6.asm ic_addr)
SHARED = ("p_mana", "p_cure")                                       # logical 6, 7 -> 5 (p_heal)

# Review grouping (class order requested for the page), by grid name prefix / name.
GROUPS = [
    ("WEAPONS", ["w_short", "w_long", "w_axe", "w_cleaver", "w_oak", "w_iron", "w_rune",
                 "w_bone", "bow"]),
    ("ARMOUR", ["a_robe", "a_leather", "a_chain", "a_plate", "a_silk", "a_grave"]),
    ("HELMETS", ["h_hood", "h_helm", "h_king", "h_mirror"]),
    ("CHARMS", ["c_might", "c_ward", "c_fire", "c_grave", "c_mana", "c_plenty", "c_scarab"]),
    ("FOOD", ["f_carrot", "f_apple", "f_pear", "f_cheese", "f_meat"]),
    ("POTIONS", ["p_heal", "p_mana", "p_cure"]),
    ("SCROLLS", ["s_teleport", "s_fear", "s_sleep", "s_enchant"]),
    ("BOOKS", ["book"]),
    ("EMPTY WORN SLOTS (placeholders)", PH_NAMES),
    ("FLOOR AMMO (counters, never in the bag)", [n for n, _ in AMMO_NAMES]),
]

INK_NAME = ["black", "blue", "red", "magenta", "green", "cyan", "yellow", "white"]
PAL = [(0, 0, 0), (0, 0, 0xD7), (0xD7, 0, 0), (0xD7, 0, 0xD7),
       (0, 0xD7, 0), (0, 0xD7, 0xD7), (0xD7, 0xD7, 0), (0xD7, 0xD7, 0xD7)]


class Fail(Exception):
    pass


def zx_hex(c: int, bright: bool) -> str:
    return "#%02X%02X%02X" % tuple(0xFF if (bright and v) else v for v in PAL[c & 7])


# ------------------------------------------------------------------------------ model
def index_map():
    """[(idx, grid name, IT_ name or None, ink attr)] for idx 0..44, from item_defs + ITEM_INK."""
    lo, cnt = IM.D["IT_BAG_LO"], IM.D["IT_COUNT"]
    by_id = {v: k for k, v in IM.T.items() if k.startswith("IT_") and k not in
             ("IT_BAD", "IT_COUNT") and not k.endswith(("_LO", "_HI"))}
    out = []
    for typ in range(lo, cnt):
        it = by_id[typ]
        out.append((typ - lo, it[3:].lower(), it, IM.ITEM_INK[typ]))
    if len(out) != 39:
        raise Fail("expected 39 bag types IT_BAG_LO..IT_COUNT-1, got %d" % len(out))
    for slot, n in enumerate(PH_NAMES):
        out.append((cnt - lo + slot, n, None, PH_INK))
    for n, it in AMMO_NAMES:                 # appended: indices 0..42 stay unchanged
        out.append((len(out), n, it, IM.ITEM_INK[IM.T[it]]))
    return out


def read_grid(name: str):
    path = os.path.join(ICON_DIR, name + ".grid")
    if not os.path.exists(path):
        raise Fail("missing %s" % os.path.relpath(path, REPO))
    rows, note = [], ""
    for ln in open(path):
        ln = ln.rstrip("\n")
        if not ln or ln.startswith("# ") or ln == "#":
            if ln.startswith("# note:"):
                note = ln[7:].strip()
            continue
        rows.append(ln)
    if len(rows) != H or any(len(r) != W or set(r) - set("#.") for r in rows):
        raise Fail("%s: need %d rows of %d chars in '#.'" % (name, H, W))
    bits = [[c == "#" for c in r] for r in rows]
    if any(bits[0]) or any(bits[H - 1]) or any(r[0] or r[W - 1] for r in bits):
        raise Fail("%s: ink in the 1-px margin (row 0/15, col 0/15 must be paper)" % name)
    if not any(any(r) for r in bits):
        raise Fail("%s: empty icon" % name)
    return bits, note


def pack(bits) -> bytes:
    """FLOOR1: 4 quarters of 8 lines (UL, UR, LL, LR), 8 contiguous bytes each, so a
    draw steps one byte a line (erase_rect's floor-item cells, the page / panel)."""
    out = bytearray()
    for y0 in (0, 8):
        for b0 in (0, 8):
            for y in range(y0, y0 + 8):
                v = 0
                for i in range(8):
                    v = (v << 1) | int(bits[y][b0 + i])
                out.append(v)
    return bytes(out)


def unpack(b: bytes):
    return [[bool(b[(y // 8) * 16 + (x // 8) * 8 + y % 8] & (0x80 >> (x % 8))) for x in range(W)]
            for y in range(H)]


def check_ink(name: str, attr: int):
    ink, paper, flash = attr & 7, (attr >> 3) & 7, attr & 0x80
    if paper != 0 or flash or attr & 0x38:
        raise Fail("%s: ink attr $%02X must be paper black, no flash" % (name, attr))
    if ink in (0, CURSOR_PAPER):
        raise Fail("%s: ink %d invisible on black / blue cursor paper" % (name, ink))


def clash_check(name: str, bits, attr: int):
    """Per 8x8 cell: the cell's colours = {ink if any set} + {paper if any clear} <= 2, and the
    cell attr is the icon attr (1 ink per icon -> both of its 2x2 cells' attrs are legal)."""
    for cy in (0, 8):
        for cx in (0, 8):
            cell = [bits[y][x] for y in range(cy, cy + 8) for x in range(cx, cx + 8)]
            cols = ({attr & 7} if any(cell) else set()) | ({0} if not all(cell) else set())
            if len(cols) > 2:
                raise Fail("%s: cell (%d,%d) needs %d colours" % (name, cx, cy, len(cols)))


# ------------------------------------------------------------------------------ asm
def physical(model, packed):
    """(model rows, packed icons) of the emitted table: the SHARED icons dropped."""
    keep = [i for i, m in enumerate(model) if m[1] not in SHARED]
    return [model[i] for i in keep], [packed[i] for i in keep]


# ------------------------------------------------------------------- MEM-RECLAIM w2c packing
# The build assembles the PACKED stream, not the raw table (icons6.asm ic_unp decodes it).
# Per physical icon p (FLOOR1 32-B layout in, byte-exact out):
#   the left column = UL then LL octs, the right column = UR then LR octs; an oct = 1 mask
#   byte (bit 7 = its line 0; 1 = "repeat the column's previous byte", 0 = a literal byte
#   follows) + its literals. Each column's "previous" starts at 0 (so blank lines cost a
#   bit). MIRROR icons (UR / LR = UL / LL bit-reversed, line by line) store only the left
#   column; ic_unp rebuilds the right one.
#   icpk_idx[p] = MIRROR << 7 | (off_p - PK_K * p - dmin)  (7 bits: ASSERTed here), so the
#   stream of p is at icpk_base + PK_K * p + (icpk_idx[p] & $7F), icpk_base = icpk + dmin.
PK_K = 22                                    # bytes per icon on average (keeps the 7-bit delta)


def _rev8(v: int) -> int:
    return int("{:08b}".format(v)[::-1], 2)


def _pk_col(octs) -> bytes:
    out, prev = bytearray(), 0
    for oc in octs:
        m, lit = 0, bytearray()
        for v in oc:
            m <<= 1
            if v == prev:
                m |= 1
            else:
                lit.append(v)
                prev = v
        out.append(m)
        out += lit
    return bytes(out)


def pk_icon(b: bytes):
    """(mirror flag, stream bytes) of one 32-B icon."""
    ul, ur, ll, lr = b[0:8], b[8:16], b[16:24], b[24:32]
    mir = list(ur) == [_rev8(v) for v in ul] and list(lr) == [_rev8(v) for v in ll]
    s = _pk_col((ul, ll))
    if not mir:
        s += _pk_col((ur, lr))
    return mir, s


def pk_all(phys):
    """(idx bytes, stream bytes, dmin) for the physical icons; raises Fail if a delta overflows."""
    enc = [pk_icon(b) for b in phys]
    off, offs = 0, []
    for _, s in enc:
        offs.append(off)
        off += len(s)
    d = [o - PK_K * p for p, o in enumerate(offs)]
    dmin = min(d)
    if max(d) - dmin > 127:
        raise Fail("packed delta range %d > 127: retune PK_K" % (max(d) - dmin))
    idx = bytes(((0x80 if m else 0) | (dp - dmin)) for (m, _), dp in zip(enc, d))
    return idx, b"".join(s for _, s in enc), dmin


def pk_decode(idx: bytes, stream: bytes, dmin: int, p: int) -> bytes:
    """Python model of ic_unp (icons6.asm): physical p -> its 32 B."""
    pos = PK_K * p + (idx[p] & 0x7F) + dmin
    out = bytearray(32)

    def col(dst):
        nonlocal pos
        prev = 0
        for d0 in dst:
            m = stream[pos]
            pos += 1
            for k in range(8):
                if not (m << k) & 0x80:
                    prev = stream[pos]
                    pos += 1
                out[d0 + k] = prev
    col((0, 16))
    if idx[p] & 0x80:
        for k in list(range(0, 8)) + list(range(16, 24)):
            out[k + 8] = _rev8(out[k])
    else:
        col((8, 24))
    return bytes(out)


def emit_asm(model, packed) -> str:
    model, packed = physical(model, packed)
    idx, stream, dmin = pk_all(packed)
    if [pk_decode(idx, stream, dmin, p) for p in range(len(packed))] != list(packed):
        raise Fail("packed stream does not decode to the raw icons")
    L = [";" + "=" * 78,
         "; icons16.asm — IC1 true 16x16 item icons (game.md §8.11 Q5). GENERATED by",
         "; tools/icons16.py from assets/gfx/icons/<name>.grid: do not hand-edit.",
         ";",
         "; %d icons x %d B = %d B raw, 1 bit, NO mask, no attributes in this table."
         % (len(packed), ICON_BYTES, len(packed) * ICON_BYTES),
         "; Per icon (FLOOR1 layout): 4 quarters of 8 lines, UL, UR, LL, LR (+0 / 8 / 16 / 24),",
         "; each 8 bytes top-down; bit 7 = leftmost pixel; set = ink, clear = paper. COPY (not",
         "; OR) into 2x2 byte-aligned cells.",
         "; Index = type - IT_BAG_LO (0..38); 39 + worn slot = empty-slot placeholders",
         "; (weapon, armour, helmet, charm); 43 / 44 = floor ammo (IT_DAGGER, IT_ARROW;",
         "; counters, never in the bag). Raw: icons16 + index * 32 (reference only, below).",
         "; Ink per icon = it_tab (src/lowram.asm; source tools/items_model.py ITEM_INK) with",
         "; paper black (cursor: paper blue); placeholders ink $05; ammo = ITEM_INK. Ink per icon",
         "; is listed below for reference only; the draw takes it from it_tab.",
         "; 1 ink per 16x16 icon -> each 8x8 cell is ink + paper: clash-free by construction.",
         ";" + "=" * 78,
         "ICONS16_W       EQU %d" % W,
         "ICONS16_H       EQU %d" % H,
         "ICONS16_BYTES   EQU %d              ; per icon" % ICON_BYTES,
         "ICONS16_COUNT   EQU %d              ; logical: 39 bag types + 4 placeholders + 2 ammo"
         % N_ICONS,
         "ICONS16_PHYS    EQU %d              ; in this table: the 3 potions share one shape" % len(packed),
         "ICONS16_SHARE_LO EQU 6             ; logical 6 / 7 (Mana, Cure) -> physical 5 (Heal's shape)",
         "ICONS16_SHARE_N EQU 2",
         "ICONS16_PH      EQU %d              ; first placeholder index (39 + worn slot)"
         % (39),
         "ICONS16_AMMO_DAGGER EQU %d          ; floor ammo IT_DAGGER" % (39 + len(PH_NAMES)),
         "ICONS16_AMMO_ARROW  EQU %d          ; floor ammo IT_ARROW" % (40 + len(PH_NAMES)),
         "ICONS16_INK_PH  EQU $%02X             ; placeholder ink (dim cyan)" % PH_INK,
         "ICONS16_PK_K    EQU %d              ; MEM-RECLAIM w2c: icpk_idx delta base (B per icon)" % PK_K,
         "                ASSERT ICONS16_COUNT == 45 && ICONS16_AMMO_ARROW == ICONS16_COUNT - 1",
         "                ASSERT ICONS16_PHYS == ICONS16_COUNT - ICONS16_SHARE_N",
         "",
         "; The RAW table: the reference the tests compare the screen against (tests/game_lib.py",
         "; icons16_table) — NOT assembled (MEM-RECLAIM w2c): the build holds icpk below.",
         "    IF 0",
         "icons16:"]
    for (i, name, it, attr), b in zip(model, packed):
        L.append("; %2d %-12s %-14s ink $%02X" % (i, name, it or "(placeholder)", attr))
        for half in (0, 16):
            L.append("                DEFB " + ",".join("$%02X" % v for v in b[half:half + 16]))
    L.append("                ASSERT $ - icons16 == ICONS16_PHYS * ICONS16_BYTES")
    L.append("    ENDIF")
    L += ["",
          "; MEM-RECLAIM w2c: the PACKED icons (%d + %d B, was %d raw), decoded byte-exact by"
          % (len(idx), len(stream), len(packed) * ICON_BYTES),
          "; icons6.asm ic_unp. Per physical icon p: icpk_idx[p] = MIRROR << 7 | delta; its stream",
          "; at icpk_base + ICONS16_PK_K * p + delta: the left column (UL oct, LL oct), then, unless",
          "; MIRROR (right = left bit-reversed), the right column (UR oct, LR oct). An oct = a mask",
          "; byte (bit 7 = line 0; 1 = repeat the column's previous byte, from 0) + its literals.",
          "icpk_idx:"]
    for k in range(0, len(idx), 16):
        L.append("                DEFB " + ",".join("$%02X" % v for v in idx[k:k + 16]))
    L.append("icpk:")
    L.append("icpk_base       EQU icpk + (%d)" % dmin)
    pos = 0
    enc = [pk_icon(b) for b in packed]
    for (i, name, it, attr), (m, s) in zip(model, enc):
        L.append("; %2d %-12s%s" % (i, name, " MIRROR" if m else ""))
        for k in range(0, len(s), 16):
            L.append("                DEFB " + ",".join("$%02X" % v for v in s[k:k + 16]))
        pos += len(s)
    L.append("                ASSERT $ - icpk_idx == %d && icpk_idx + ICONS16_PHYS == icpk"
             % (len(idx) + len(stream)))
    return "\n".join(L) + "\n"


def parse_asm(text: str):
    body = text.split("icons16:", 1)[1].split("    ENDIF", 1)[0]
    vals = [int(h, 16) for line in body.splitlines() if "DEFB" in line
            for h in re.findall(r"\$([0-9A-F]{2})", line.split(";")[0])]
    return [bytes(vals[i:i + ICON_BYTES]) for i in range(0, len(vals), ICON_BYTES)]


# ------------------------------------------------------------------------------ html
def svg(bits, ink_hex: str, scale: int, paper: str = "#000000", grid: bool = False) -> str:
    runs = []
    for y, r in enumerate(bits):
        x = 0
        while x < W:
            if r[x]:
                x0 = x
                while x < W and r[x]:
                    x += 1
                runs.append("M%d %dh%dv1h-%dz" % (x0, y, x - x0, x - x0))
            else:
                x += 1
    g = ('<path d="M8 0V16M0 8H16" stroke="#2a2a44" stroke-width="0.08" fill="none"/>'
         if grid else "")
    return ('<svg width="%d" height="%d" viewBox="0 0 16 16" shape-rendering="crispEdges" '
            'style="display:block"><rect width="16" height="16" fill="%s"/>%s'
            '<path d="%s" fill="%s"/></svg>' % (W * scale, H * scale, paper, g, "".join(runs), ink_hex))


def ink_label(attr: int) -> str:
    return "$%02X %s%s" % (attr, "bright " if attr & 0x40 else "", INK_NAME[attr & 7])


def bag_scene(model, bm) -> str:
    """Page rows 2..16 (bag rows 2..13: 2x2 at col 3+6c, row 2+3r; worn row 15..16 at cols
    3/9/15/21), x2. Bag = 20 sample icons, slot 7 under the cursor (paper blue)."""
    S, X0, Y0, ROWS = 2, 0, 2, 15
    by_name = {m[1]: m for m in model}
    bag = ["w_short", "a_leather", "f_apple", "f_meat", "p_heal",
           "p_mana", "p_cure", "s_teleport", "s_fear", "book",
           "bow", "h_helm", "c_might", "c_mana", "f_cheese",
           "w_axe", "a_chain", "s_enchant", "f_carrot", "c_scarab"]
    worn = ["w_long", "a_plate", "ph_helmet", "ph_charm"]
    cursor = 7
    parts = ['<svg width="%d" height="%d" viewBox="0 0 256 %d" shape-rendering="crispEdges" '
             'style="display:block"><rect width="256" height="%d" fill="#000000"/>'
             % (256 * S, ROWS * 8 * S, ROWS * 8, ROWS * 8)]

    def put(name, col, row, sel=False):
        _, _, _, attr = by_name[name]
        x, y = col * 8, (row - Y0) * 8
        paper = zx_hex(CURSOR_PAPER, False) if sel else "#000000"
        parts.append('<g transform="translate(%d %d)">%s</g>'
                     % (x, y, svg(bm[name], zx_hex(attr, bool(attr & 0x40)), 1, paper)
                        .replace('width="16" height="16" viewBox', 'viewBox')
                        .replace('<svg ', '<svg width="16" height="16" ')))
    for i, n in enumerate(bag):
        r, c = divmod(i, 5)
        put(n, 3 + 6 * c, 2 + 3 * r, i == cursor)
    for slot, n in enumerate(worn):
        put(n, 3 + 6 * slot, 15)
    parts.append("</svg>")
    return "".join(parts)


FLOOR_GLYPH = [0xFF, 0x10, 0x10, 0x10, 0xFF, 0x01, 0x01, 0x01]   # tiles_common id 1 T_PLAT
FLOOR_ATTR = 0x0F                    # D1 ATTR_FLOOR (tilesets.asm): white ink, blue paper
HERO_GRID = os.path.join(REPO, "assets/gfx/sprites/grid/knight_idle1.grid")   # 24x48 scale ref


def floor_scene(name, attr, bm) -> str:
    """x3 floor-line mock, 10 x 7 cells: floor row (T_PLAT, ATTR_FLOOR) at cell row 6; the 16x16
    icon standing on it at cols 6..7 rows 4..5 (paper black, its ink), with the floor cells at
    cols 5 and 8 beside its base; the 24x48 knight_idle1 silhouette (grey) at cols 1..3 rows 0..5."""
    S, CW, CH = 3, 10, 7
    p = ['<svg width="%d" height="%d" viewBox="0 0 %d %d" shape-rendering="crispEdges" '
         'style="display:block"><rect width="%d" height="%d" fill="#000000"/>'
         % (CW * 8 * S, CH * 8 * S, CW * 8, CH * 8, CW * 8, CH * 8)]
    fi, fp = zx_hex(FLOOR_ATTR & 7, bool(FLOOR_ATTR & 0x40)), zx_hex(FLOOR_ATTR >> 3 & 7, False)
    for cx in range(CW):
        x = cx * 8
        p.append('<rect x="%d" y="48" width="8" height="8" fill="%s"/>' % (x, fp))
        for y, v in enumerate(FLOOR_GLYPH):
            for b in range(8):
                if v & (0x80 >> b):
                    p.append('<rect x="%d" y="%d" width="1" height="1" fill="%s"/>'
                             % (x + b, 48 + y, fi))
    if os.path.exists(HERO_GRID):
        rows = [ln.rstrip("\n") for ln in open(HERO_GRID) if ln.strip() and not ln.startswith("#")]
        for y, r in enumerate(rows[:48]):
            for x, c in enumerate(r[:24]):
                if c == "#":
                    p.append('<rect x="%d" y="%d" width="1" height="1" fill="#8a8a9a"/>'
                             % (8 + x, y))
    ink = zx_hex(attr, bool(attr & 0x40))
    for y, r in enumerate(bm[name]):
        for x, on in enumerate(r):
            if on:
                p.append('<rect x="%d" y="%d" width="1" height="1" fill="%s"/>'
                         % (48 + x, 32 + y, ink))
    p.append("</svg>")
    return "".join(p)


def emit_html(model, bm, notes) -> str:
    by_name = {m[1]: m for m in model}
    o = ['<div style="font-family:\'Press Start 2P\',monospace;background:#12121c;color:#e6e4f0;'
         'padding:24px;display:flex;flex-direction:column;gap:28px;">',
         '<h2 style="margin:0;font-size:14px;">IC1 16&#215;16 ITEM ICONS (DRAFT FOR REVIEW)</h2>',
         '<div style="font-size:10px;color:#77758a;max-width:900px;line-height:1.6;">'
         'game.md &#167;8.11 Q5: 1 bit, no mask, 32 B each, one ink per icon from it_tab '
         '(paper black; page cursor paper blue). Index = type &#8722; IT_BAG_LO; 39 + worn slot = '
         'empty-slot placeholders (ink $05, dashed); 43 / 44 = floor ammo (dagger, arrow). '
         '45 icons = 1,440 B. Source: '
         'assets/gfx/icons/*.grid &#8594; tools/icons16.py &#8594; icons16.asm.</div>']
    for title, names in GROUPS:
        o.append('<h3 style="margin:0;font-size:12px;color:#c9c7d8;">%s</h3>' % html.escape(title))
        o.append('<div style="display:flex;gap:20px;flex-wrap:wrap;align-items:flex-start;">')
        for n in names:
            idx, _, it, attr = by_name[n]
            ink = zx_hex(attr, bool(attr & 0x40))
            o.append('<figure style="margin:0;display:flex;flex-direction:column;gap:6px;width:150px;">'
                     '<div style="display:flex;gap:6px;align-items:flex-end;">'
                     '<div style="padding:4px;background:#000;border:2px solid #26263a;">%s</div>'
                     '<div style="padding:4px;background:%s;border:2px solid #26263a;">%s</div></div>'
                     '<figcaption style="font-size:9px;color:#a9a7b8;line-height:1.5;">%s<br/>'
                     '<span style="color:%s">%s</span> &#183; idx %d<br/>'
                     '<span style="color:#77758a;">%s</span></figcaption></figure>'
                     % (svg(bm[n], ink, 4, grid=True), zx_hex(CURSOR_PAPER, False),
                        svg(bm[n], ink, 2, zx_hex(CURSOR_PAPER, False)),
                        html.escape((it or n).replace("IT_", "")), ink, ink_label(attr), idx,
                        html.escape(notes[n])))
        o.append("</div>")
    # 1x actual size, all 43 in index order
    o.append('<h3 style="margin:0;font-size:12px;color:#c9c7d8;">ACTUAL SIZE (1&#215;, index order, all 45)</h3>')
    o.append('<div style="display:flex;gap:2px;background:#000;padding:8px;width:max-content;">')
    for idx, n, _, attr in model:
        o.append(svg(bm[n], zx_hex(attr, bool(attr & 0x40)), 1))
    o.append("</div>")
    o.append('<h3 style="margin:0;font-size:12px;color:#c9c7d8;">BAG PAGE SIMULATION (rows 2&#8211;16, '
             '&#215;2): 20 bag slots at col 3+6c, row 2+3r, cursor on slot 8 (paper blue); worn row '
             '15&#8211;16 at cols 3/9/15/21 (helmet + charm empty)</h3>')
    o.append('<div style="padding:8px;background:#000;border:2px solid #26263a;width:max-content;">%s</div>'
             % bag_scene(model, bm))
    o.append('<h3 style="margin:0;font-size:12px;color:#c9c7d8;">FLOOR-LINE MOCK (&#215;3): 16&#215;16 '
             'ammo icon standing on the floor row (T_PLAT, ATTR_FLOOR $0F) between floor cells, '
             'next to the 24&#215;48 hero (knight_idle1, grey) for scale</h3>')
    o.append('<div style="display:flex;gap:20px;">')
    for n, _ in AMMO_NAMES:
        _, _, _, attr = by_name[n]
        o.append('<div style="padding:8px;background:#000;border:2px solid #26263a;">%s</div>'
                 % floor_scene(n, attr, bm))
    o.append("</div>")
    o.append("</div>")
    return "\n".join(o) + "\n"


# ------------------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="validate + round-trip, write nothing")
    a = ap.parse_args()
    try:
        model = index_map()
        bm, notes, packed = {}, {}, []
        for idx, name, it, attr in model:
            bits, note = read_grid(name)
            check_ink(name, attr)
            clash_check(name, bits, attr)
            bm[name], notes[name] = bits, note
            packed.append(pack(bits))
            if unpack(packed[-1]) != bits:
                raise Fail("%s: pack/unpack mismatch" % name)
        if [m[0] for m in model] != list(range(N_ICONS)):
            raise Fail("index map not 0..%d" % (N_ICONS - 1))
        if len(set(packed)) != len(packed):
            raise Fail("duplicate icon bitmaps")
        extra = sorted(set(f[:-5] for f in os.listdir(ICON_DIR) if f.endswith(".grid")) - set(bm))
        if extra:
            raise Fail("grids not in the index map: %s" % ", ".join(extra))
        asm = emit_asm(model, packed)
        back = parse_asm(asm)
        pm, pp = physical(model, packed)
        if back != pp or [unpack(b) for b in back] != [bm[m[1]] for m in pm]:
            raise Fail("round-trip: emitted DEFB != grids")
        if len(pp) * ICON_BYTES != (N_ICONS - len(SHARED)) * ICON_BYTES or N_ICONS != 45:
            raise Fail("table size %d != %d" % (len(pp) * ICON_BYTES, (N_ICONS - len(SHARED)) * ICON_BYTES))
        inks = [m[3] for m in model if m[1] in ("p_heal",) + SHARED]
        if len(set(inks)) != len(inks):
            raise Fail("the shared potion shape needs a distinct ink per type: %s" % inks)
        if a.check:
            if os.path.exists(OUT_ASM) and open(OUT_ASM).read() != asm:
                raise Fail("icons16.asm is stale: run tools/icons16.py")
        else:
            with open(OUT_ASM, "w") as f:
                f.write(asm)
            with open(OUT_HTML, "w") as f:
                f.write(emit_html(model, bm, notes))
    except Fail as e:
        print("icons16: FAIL: %s" % e, file=sys.stderr)
        return 1
    print("icons16: OK — %d icons (%d in the table: the potions share one shape), %d B, clash-free, "
          "round-trip exact%s" % (len(packed), len(pp), len(pp) * ICON_BYTES, "" if a.check else " (written)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
