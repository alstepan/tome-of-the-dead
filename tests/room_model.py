"""B3B-8: Python model of a built room (build_room_map v2) and of the row-17
ornament, written from the spec (game.md §1.1 / §2.1 / §2.5 / §3.3 / §1.4,
concept-screen §3.1, docs/memory-map.md "3B contracts"), NOT from the Z80.

  render_room(blk, r)  -> 576 tile ids (rows 0..17 x 32) of room r of a level
                          block (the 320 B at LVL_STATE: tools/levelgen.py
                          generate() or read from memory)
  orn_index(col)       -> ORN_GLYPHS index of logical col `col` (row 17)
  expected_cell(...)   -> (glyph 8 B, attr) the screen must show for a map cell
  segments(blk, r)     -> [(col, s)] ladder segments in descriptor order
  fall_range(blk, r)   -> the storey-0 x range the hero falls at (L2 wide pits)
Every number comes from the .sym (game_lib.S) or tools/levelgen.py's parse of
src/level_defs.asm, never typed here.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import decorgen  # noqa: E402
import items_model as IM  # noqa: E402
from game_lib import S  # noqa: E402

ROWS, COLS = S["PLAY_ROWS"], 32
F0, F1 = S["FLOOR_ROW0"], S["FLOOR_ROW1"]
SR, SA = S["STOREY_ROWS"], S["STOREY_AIR"]
BASE = S["LVL_STATE"]
OFF_EDGE, OFF_DESC, OFF_FLOOR = S["EDGE_TAB"] - BASE, S["ROOM_DESC"] - BASE, S["FLOOR_LIST"] - BASE
BLOCK_LEN = S["LVL_STATE_END"] - BASE
T = {k: S[k] for k in S if k.startswith("T_")}
# descriptor order of the 6 shaft / ladder col bytes and their storeys
SEG_FIELDS = (("RD_UPCOL", 0), ("RD_DNCOL", 2), ("RD_ARRCOL", 0), ("RD_EXITCOL", 2),
              ("RD_LAD1", 1), ("RD_LAD2", 1))
# PROTO decor (seed-0 rooms; mirror of bank3.asm proto_decor): room -> [(tile, col, row)]
# (B3B-13: the room-D chest stand-in is gone with the PROTO win)
PROTO_DECOR = {}                 # DEC1: the room-A small torch (ids 15 / 16) is gone
# per-depth (ATTR_FLOOR, ATTR_WALL), game.md §1.2 (depth 0 = PROTO = D1)
THEME = {1: (0x0F, 0x01), 2: (0x27, 0x04), 3: (0x17, 0x02), 4: (0x28, 0x05),
         5: (0x30, 0x06), 6: (0x38, 0x07), 7: (0x4F, 0x41), 8: (0x1F, 0x03)}
THEME[0] = THEME[1]
FLOOR_IDS = ("T_PLAT", "T_WALLF", "T_END_L", "T_END_R")
WALL_IDS = ("T_BRICK", "T_WALL_DITHER", "T_WALL_PATCH", "T_WALL_FADE", "T_RUBBLE")


def desc(blk, r):
    o = OFF_DESC + r * S["RD_STRIDE"]
    return blk[o:o + S["RD_STRIDE"]]


def field(blk, r, name):
    return desc(blk, r)[S[name]]


def pit_width(d):
    """W of the descriptor's storey-0 pit: L2_PITW (wide, 4..6), 0 there = the narrow 3."""
    return d[S["L2_PITW"]] or 3


def fall_range(blk, r):
    """game.md §2.5 / §1.1 "Wide pit" (4): the storey-0 x a 3-col hero falls at (body fully
    over holes) and every walker refuses: p .. p+W-3 (empty without a pit)."""
    d = desc(blk, r)
    p = d[S["RD_PITCOL"]]
    return range(p, p + pit_width(d) - 2) if p else range(0)


def segments(blk, r):
    return [(field(blk, r, f), s) for f, s in SEG_FIELDS if field(blk, r, f)]


def edge_index(r, side):
    """EDGE_TAB index of room r's left ('L') / right ('R') edge: e = gy*2 + gx
    of the edge's left room m."""
    m = r - 1 if side == "L" else r
    return (m // 3) * 2 + m % 3


def orn_index(col):
    if col == 0:
        return S["ORN_CAP_L"]
    if col == 31:
        return S["ORN_CAP_R"]
    if S["ORN_MID_COL"] <= col < S["ORN_MID_COL"] + S["ORN_MID_N"]:
        return S["ORN_WING_L"] + col - S["ORN_MID_COL"]
    return S["ORN_LINK"] if col & 1 else S["ORN_BAR"]


def item_tile(item):
    """FLOOR1: build_room_map draws every live entry (any type but IT_NONE) as
    the markers T_ITEM0 + k on its 2x2 cells (k = 2s upper row, 2s + 1 lower);
    the id of the upper row on storey 0 (None = not drawn)."""
    return T["T_ITEM0"] if item else None


def item_ink(item):
    """lowram item_ink: the floor attr of a type (items_model.ITEM_INK; the legacy
    IT_POTION $42)."""
    if item == S["IT_POTION"]:
        return 0x42
    return IM.ITEM_INK.get(item, 0)


def item_icon(item):
    """FLOOR1 fi_new: the icons16 index of a floor type (type - IT_BAG_LO; the
    legacy IT_POTION = Heal, daggers / arrows = the 2 floor-ammo icons)."""
    if item >= S["IT_BAG_LO"]:
        return item - S["IT_BAG_LO"]
    return {S["IT_POTION"]: S["IT_P_HEAL"] - S["IT_BAG_LO"], S["IT_DAGGER"]: S["ICONS16_AMMO_DAGGER"],
            S["IT_ARROW"]: S["ICONS16_AMMO_ARROW"]}.get(item, S["ICONS16_PH"])


def icon_cell(item, h, r):
    """The 8 bitmap bytes of half h (0 left / 1 right col), row r (0 top / 1
    bottom) of the type's 16x16 icon (icons16: 4 quarters of 8 lines)."""
    from game_lib import icon16_bytes
    ic = icon16_bytes(item_icon(item))
    return bytes(ic[16 * r + 8 * h:16 * r + 8 * h + 8])        # FLOOR1: quarters of 8 lines


def floor_cells(fl, room, slots=None):
    """FLOOR1: {(col, row): (glyph 8 B, attr)} the screen shows over room's
    marker cells (fl = the 128-B FLOOR_LIST): each col of a storey shows its TOP
    entry (the last live one in list order). INVARIANT (2026-10-28): a room holds
    <= FI_SLOTS (8) distinct item types, so every top has a glyph slot (the model
    asserts it: a 9th type is a test bug, drop_put refuses it). Cells c..c+1,
    rows 9s+6..9s+7."""
    slots = S["FI_SLOTS"] if slots is None else slots
    tops, types = {}, set()
    for i in range(S["FLOOR_MAX"]):
        rb, col, it = fl[4 * i], fl[4 * i + 1], fl[4 * i + 2]
        if rb == S["FL_EMPTY"] or rb & S["FL_ROOM_MASK"] != room:
            continue
        tops[(rb, col)] = it
        types.add(it)
    assert len(types) <= slots, "room %d holds %d distinct item types (> %d)" % (room, len(types), slots)
    out = {}
    for (rb, col), it in tops.items():
        top = SR * (1 if rb & S["FL_S1"] else 0) + SA - 2
        for h in (0, 1):
            for r in (0, 1):
                out[(col + h, top + r)] = (icon_cell(it, h, r), item_ink(it))
    return out


floor_inks = floor_cells             # (pre-FLOOR1 name: the per-cell inks)


def expected_cell(rmap, glyphs, attrs, orn, ink, c, r, logical_col=None):
    """(glyph, attr) the screen shows for map cell (c, r): its tile, except the
    row-17 ornament over PLAT / WALLF cells (glyph by logical col) and FLOOR1
    a floor-item cell (`ink` = floor_cells: its icon quarter + ink)."""
    if ink and (c, r) in ink:
        return ink[(c, r)]
    t = rmap[r * 32 + c]
    g = glyphs[t * 8:t * 8 + 8]
    if r == F1 and t in (T["T_PLAT"], T["T_WALLF"]):
        k = orn_index(c if logical_col is None else logical_col)
        g = orn[k * 8:k * 8 + 8]
    return bytes(g), attrs[t]


def render_room(blk, r, decor=True, anim=None):
    """decor=True applies the B3B-9 deriver (tools/decorgen.py); anim, if a list, receives
    its ANIM_LIST bytes (the room built into ROOM_MAP)."""
    m = [[T["T_AIR"]] * COLS for _ in range(ROWS)]
    for row in range(ROWS):
        floor = row in (F0, F1)
        for c in range(COLS):
            if c in (0, 31):
                m[row][c] = T["T_WALLF"] if floor else T["T_BRICK"]
            else:
                m[row][c] = T["T_PLAT"] if floor else T["T_AIR"]
    d = desc(blk, r)
    ex = d[S["RD_EXITS"]]
    edges = blk[OFF_EDGE:OFF_EDGE + S["EDGES_H"]]
    for side, bit, sbit, col, dcol in (("L", "RDX_L", "RDX_LS1", 0, 0),
                                        ("R", "RDX_R", "RDX_RS1", 31, 30)):
        if not ex & S[bit]:
            continue
        s = 1 if ex & S[sbit] else 0
        for row in range(SR * s, SR * s + SA):
            m[row][col] = T["T_AIR"]
        st = edges[edge_index(r, side)]
        if not st & S["EG_DOOR"]:
            continue
        top = SR * s
        m[top][dcol] = m[top][dcol + 1] = T["T_BRICK"]
        m[top + 1][dcol], m[top + 1][dcol + 1] = T["T_DOOR_ARCH_L"], T["T_DOOR_ARCH_R"]
        for row in range(top + 2, top + SA):
            if st & S["EG_OPEN"]:
                m[row][dcol], m[row][dcol + 1] = T["T_DOOR_JAMB_L"], T["T_DOOR_JAMB_R"]
            else:
                m[row][dcol] = T["T_DOOR_L"]
                m[row][dcol + 1] = T["T_DOOR_LOCK"] if st & (S["EG_LOCK"] | S["EG_SEAL"]) \
                    else T["T_DOOR_R"]
    p = d[S["RD_PITCOL"]]
    if p:                                      # L2 (game.md §1.1 "Wide pit"): W holes
        pw = pit_width(d)
        m[F0][p - 1], m[F0][p + pw] = T["T_PIT_L"], T["T_PIT_R"]
        for c in range(p, p + pw):
            m[F0][c] = T["T_AIR"]
    blk_b = d[S["RD_BLOCK"]]
    w = blk_b & S["RDB_WMASK"]
    if w:
        s = 1 if blk_b & S["RDB_S1"] else 0
        right = bool(blk_b & S["RDB_RIGHT"])
        cols = range(32 - w, 32) if right else range(w)
        for c in cols:
            for row in range(SR * s, SR * s + SA):
                m[row][c] = T["T_BRICK"]
            m[SR * s + SA][c] = T["T_WALLF"]
        m[SR * s + SA - 1][31 - w if right else w] = T["T_RUBBLE"]
    b = d[S["L2_MIDB"]]
    if b:                                      # L2 mid-room block (game.md §1.1): storey 0,
        w = d[S["L2_MIDW"]]                    # wall like an edge block, rubble on both faces
        for c in range(b, b + w):
            for row in range(SA):
                m[row][c] = T["T_BRICK"]
            m[F0][c] = T["T_WALLF"]
        m[SA - 1][b - 1] = m[SA - 1][b + w] = T["T_RUBBLE"]
    for col, s in segments(blk, r):
        for row in range(SR * s - 1, SR * s + SA):
            if not 0 <= row < ROWS:
                continue
            if row == F1:
                base = T["T_HOLE_L"]
            elif row == F0:
                base = T["T_HOLE_L"]
                if m[row][col - 1] == T["T_PLAT"]:
                    m[row][col - 1] = T["T_END_R"]
                if m[row][col + 3] == T["T_PLAT"]:
                    m[row][col + 3] = T["T_END_L"]
            else:
                base = T["T_LAD_L"]
            for k in range(3):
                m[row][col + k] = base + k
    arr = d[S["RD_ARRCOL"]]
    if arr:
        for k in range(3):
            m[0][arr + k] = T["T_RUBBLE"]
    xc = d[S["RD_EXITCOL"]]
    grate_open = blk[S["LVL_FLAGS"] - BASE] & S["LF_GRATE_OPEN"]
    if xc and not grate_open:                  # 3F closed gate (own id: TODO 3F)
        for k in range(3):
            m[F1][xc + k] = T["T_GRATE_SHUT"]
    for i in range(S["FLOOR_MAX"]):
        o = OFF_FLOOR + i * S["FL_STRIDE"]
        room, col, item = blk[o], blk[o + 1], blk[o + 2]
        tile = item_tile(item)                 # FLOOR1: T_ITEM over the 2x2 footprint
        if room != S["FL_EMPTY"] and room & S["FL_ROOM_MASK"] == r and tile is not None:
            s = 1 if room & S["FL_S1"] else 0
            for k in (0, 1):
                m[SR * s + SA - 2][col + k] = tile + 2 * s
                m[SR * s + SA - 1][col + k] = tile + 2 * s + 1
    seed = d[S["RD_SEED"]] | d[S["RD_SEED"] + 1] << 8
    flat = [t for row in m for t in row]
    if seed == 0:
        for name, c, row in PROTO_DECOR.get(r, []):
            flat[row * COLS + c] = T[name]
    elif decor:
        flat, al = decorgen.decorate(flat, blk[S["LVL_DEPTH"] - BASE], seed)
        if anim is not None:
            anim[:] = al
    if xc and grate_open:
        # B12 (concept-screen B3B-8 #4): the open level exit = the raised gate over
        # its 3 hole cells, after the decor (whose ring rule saw the holes), + the
        # depth's GLOW on the standing row above the middle cell if it is still air
        for k in range(3):
            flat[F1 * COLS + xc + k] = T["T_GRATE"]
        g = (F1 - 1) * COLS + xc + 1
        if flat[g] == T["T_AIR"]:
            flat[g] = glow_id(blk[S["LVL_DEPTH"] - BASE])
    return flat


def glow_id(depth):
    """B12: the per-level GLOW tile id (assets/gfx/tiles/tileset_ids.inc)."""
    return S[f"TS{depth}_GLOW_F1_R0C0"]


def read_block(p):
    return bytes(p.z.read_memory(BASE, BLOCK_LEN))
