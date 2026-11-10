#!/usr/bin/env python3
"""tut0_level.py - the DEPTH 0 ("THE OLD CRYPT") level block for the TUT0 blob (task TUT0-T4).

Spec: docs/design/tutorial_d0.md §2 (rooms A = 1, B = 4, C = 5, hero state), §4.1 (the mentor
hovers one char row above the floor, 3 x 6 cells), docs/design/tut0_split.md "T4" and the F1
verdict (tile-id stamp: 17 ids from 32..59 are the mentor's (TUT0-F1: his always-blank cell takes none), so the decor may use
at most 28 - 17 = 11 distinct per-level ids, animation frame ids included).

Writes build/tut/tut0_level.asm: byte images (labels TUT0_*) of
    LVL_STATE header (16 B)   EDGE_TAB (6 B)   ROOM_DESC (9 x 16 B)
    TRAP_LIST area (16 B: 6 x 2 B + TRAP_N at +12 + 3 spare)   FLOOR_LIST (32 x 4 B)
plus the spot table, the 17 reserved mentor tile ids and the Goblin parameters.
Every field offset / bit value comes from src/level_defs.asm / src/item_defs.asm / src/defs.asm
(parsed by tools/levelgen.py), nothing is hard-coded here except the level design itself.

Decor: RD_SEED per room is searched (tools/decorgen.py, the Z80's reference) so that
  * the decor of A, B, C together uses <= TUT0_DECOR_IDS_MAX distinct ids in 32..59,
  * every mentor spot box (3 cols x 6 rows) stays all T_AIR after the decor,
  * no decorative drip source (drip7.asm model, DEPTH stays 1 in D0) falls in a spot's cols.
If no seed set meets that, RD_SEED = 0 (bare rooms, bank3.asm:643) would be emitted and said so.

Usage: tools/tut0_level.py [out.asm]     (default build/tut/tut0_level.asm; prints a summary)
"""
import itertools
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import decorgen  # noqa: E402
import levelgen as G  # noqa: E402

D = G.D
ROOT = G.ROOT
BASE = G.BASE
OFF_EDGE, OFF_DESC, OFF_FLOOR = G.OFF_EDGE, G.OFF_DESC, G.OFF_FLOOR
H = G.H

# ---- symbols not in levelgen's parse (drip.asm constants, the drip model) ----------------------
DRIP = {}
G._load_one(ROOT / "src" / "drip.asm", DRIP)

ROWS, COLS = D["PLAY_ROWS"], D["ROOM_COLS"]
F0, F1 = D["FLOOR_ROW0"], D["FLOOR_ROW1"]
SR, SA = D["STOREY_ROWS"], D["STOREY_AIR"]
T = {k: v for k, v in D.items() if k.startswith("T_")}
ID_LO = D["T_LVL_BASE"]                  # 32
ID_HI = D["T_LVL_OBJ"] - 1               # 59: decor uses 32..59 only (60..63 = per-level objects)
N_LVL_IDS = ID_HI - ID_LO + 1            # 28
MENTOR_CELLS = 18                        # 3 x 6 cells (F1 verdict)
MENTOR_BLANK = 17                        # TUT0-F1: source cell r5c2 is blank in every image (tests/tut0_level.py
                                         # checks aldous34.asm): it takes no id (T_AIR; mirrored: box cell 15)
MENTOR_IDS = MENTOR_CELLS - 1            # 17 ids, contiguous (tt_unstamp's range test)
DECOR_IDS_MAX = N_LVL_IDS - MENTOR_IDS   # 11: TORCH_TALL = 8 static + 3 flame frame ids
BOX_W, BOX_H = 3, 6
DEPTH = 1                                # D0 runs with LVL_DEPTH = 1 (spec §0 "Internal depth")

# ---- the level design (spec §2) -----------------------------------------------------------------
ROOM_A, ROOM_B, ROOM_C = 1, 4, 5          # grid cells: A top row, B below A, C right of B
LVL_SEED_D0 = 0x0D00                      # level seed / GEN_RNG start: only used by nothing at runtime (no generation)
LAIR_EDGE = ROOM_B                        # EDGE_TAB index: edge between B and C = e = gy*2 + gx = 1*2 + 1
EDGE_BC = (ROOM_B // 3) * 2 + ROOM_B % 3
GOB_ROOM, GOB_X, GOB_S = ROOM_C, 22, 1    # spec §2.3: Goblin x = 22, storey 1, on the grate

# spot spec: name -> (room, storey, spec x). x = the box's LEFT col (hero / entity convention),
# the box = cols x..x+2, map rows 9s+1 .. 9s+6 (one empty row 9s+7 above the floor).
SPOT_SPEC = [("A1", ROOM_A, 0, 9), ("A2", ROOM_A, 0, 25), ("A3", ROOM_A, 1, 18),
             ("B1", ROOM_B, 0, 10), ("B2", ROOM_B, 0, 21), ("B3", ROOM_B, 1, 22),
             ("C1", ROOM_C, 1, 6), ("GRATE", ROOM_C, 1, 26)]   # GRATE: right of the grate (spec: "beside")

# floor items: (room, storey, col, IT_*, qty)  spec §2.1-2.3
ITEMS = [(ROOM_A, 0, 24, "IT_BOOK", 1), (ROOM_A, 1, 17, "IT_F_PEAR", 1),
         (ROOM_B, 0, 19, "IT_P_CURE", 1),
         (ROOM_C, 1, 4, "IT_S_SLEEP", 1), (ROOM_C, 1, 9, "IT_P_HEAL", 1)]
TRAPS = [(ROOM_B, 0, 13, "TT_DART")]      # hidden (TRF_KNOWN clear)

SEED_MAX = 0xFFFF


def desc_bytes():
    """9 x RD_STRIDE bytes (RD_SEED filled later)."""
    d = [bytearray(D["RD_STRIDE"]) for _ in range(9)]

    def put(r, f, v):
        d[r][D[f]] = v
    # A: start, leaf. arrival shaft {5,0}, down-exit {5,2}, L1 {12,1}, pit 19, L2 {26,1}
    put(ROOM_A, "RD_FLAGS", D["RDF_PRESENT"] | D["RDF_START"] | D["RDF_DEADEND"])
    put(ROOM_A, "RD_EXITS", D["RDX_D"])
    put(ROOM_A, "RD_DNCOL", 5)
    put(ROOM_A, "RD_ARRCOL", 5)
    put(ROOM_A, "RD_LAD1", 12)
    put(ROOM_A, "RD_PITCOL", 19)
    put(ROOM_A, "RD_LAD2", 26)
    # B: key room (RDF_KEY + LVL_KEYROOM). up-exit {5,0}, L1 {24,1}, door right on storey 1
    put(ROOM_B, "RD_FLAGS", D["RDF_PRESENT"] | D["RDF_KEY"])
    put(ROOM_B, "RD_EXITS", D["RDX_U"] | D["RDX_R"] | D["RDX_RS1"])
    put(ROOM_B, "RD_UPCOL", 5)
    put(ROOM_B, "RD_LAD1", 24)
    # C: lair, leaf. door left on storey 1, level exit {22,2}, L1 {12,1}
    put(ROOM_C, "RD_FLAGS", D["RDF_PRESENT"] | D["RDF_LAIR"] | D["RDF_DEADEND"])
    put(ROOM_C, "RD_EXITS", D["RDX_L"] | D["RDX_LS1"])
    put(ROOM_C, "RD_EXITCOL", 22)
    put(ROOM_C, "RD_LAD1", 12)
    return d


def build_block(seeds):
    """The 320-B LVL_STATE block (G.BLOCK_LEN) with RD_SEED = seeds[room]."""
    b = bytearray(G.BLOCK_LEN)
    b[H["LVL_DEPTH"]] = DEPTH
    b[H["LVL_SEED"]:H["LVL_SEED"] + 2] = LVL_SEED_D0.to_bytes(2, "little")
    b[H["GEN_RNG"]:H["GEN_RNG"] + 2] = (LVL_SEED_D0 | 1).to_bytes(2, "little")
    b[H["LVL_ATTR_FLOOR"]], b[H["LVL_ATTR_WALL"]] = G.ATTRS[1]       # spec §2: ATTR_FLOOR[1]
    b[H["LVL_START"]] = ROOM_A
    b[H["LVL_LAIR"]] = ROOM_C
    b[H["LVL_KEYROOM"]] = ROOM_B
    b[H["LVL_SANCTUM"]] = D["ROOM_NONE"]
    b[H["LVL_NROOMS"]] = 3
    b[H["LVL_FLAGS"]] = D["LF_UNIQUE"]       # grate SHUT (LF_GRATE_OPEN clear), boss_chk / trickle silenced
    b[H["FLOOR_N"]] = len(ITEMS)
    # MASTER_SEED stays 0 in the image: the blob copies only the first TUT0_HDR_COPY bytes
    b[OFF_EDGE + EDGE_BC] = D["EG_LINK"] | D["EG_DOOR"] | D["EG_LOCK"]
    for r, rd in enumerate(desc_bytes()):
        o = OFF_DESC + r * D["RD_STRIDE"]
        b[o:o + D["RD_STRIDE"]] = rd
        if r in seeds:
            b[o + D["RD_SEED"]:o + D["RD_SEED"] + 2] = seeds[r].to_bytes(2, "little")
    for i in range(D["FLOOR_MAX"]):
        o = OFF_FLOOR + i * D["FL_STRIDE"]
        if i < len(ITEMS):
            r, s, col, it, q = ITEMS[i]
            b[o:o + 4] = bytes((r | (D["FL_S1"] if s else 0), col, D[it], q))
        else:
            b[o:o + 4] = bytes((D["FL_EMPTY"],) * 4)
    tl = D["TRAP_LIST"] - BASE
    for i, (r, s, col, tt) in enumerate(TRAPS):
        b[tl + i * D["TRAP_STRIDE"] + D["TR_B0"]] = r | (D["TRF_S1"] if s else 0)
        b[tl + i * D["TRAP_STRIDE"] + D["TR_B1"]] = col | (D[tt] << D["TR_TYPE_SHIFT"])
    b[D["TRAP_N"] - BASE] = len(TRAPS)
    return bytes(b)


# ---- room model (spec-derived, == tests/room_model.py render_room for these rooms) ---------------
def desc(blk, r):
    o = OFF_DESC + r * D["RD_STRIDE"]
    return blk[o:o + D["RD_STRIDE"]]


def structure(blk, r):
    """tile ids (rows x cols flat) as build_room_map leaves them BEFORE decor: shell, edge doors,
    pit, ladders / shafts, arrival cap, floor items (no grate: it is stamped after the decor)."""
    m = [[T["T_AIR"]] * COLS for _ in range(ROWS)]
    for row in range(ROWS):
        floor = row in (F0, F1)
        for c in range(COLS):
            if c in (0, 31):
                m[row][c] = T["T_WALLF"] if floor else T["T_BRICK"]
            else:
                m[row][c] = T["T_PLAT"] if floor else T["T_AIR"]
    d = desc(blk, r)
    ex = d[D["RD_EXITS"]]
    edges = blk[OFF_EDGE:OFF_EDGE + D["EDGES_H"]]
    for side, bit, sbit, col, dcol in (("L", "RDX_L", "RDX_LS1", 0, 0), ("R", "RDX_R", "RDX_RS1", 31, 30)):
        if not ex & D[bit]:
            continue
        s = 1 if ex & D[sbit] else 0
        for row in range(SR * s, SR * s + SA):
            m[row][col] = T["T_AIR"]
        mm = r - 1 if side == "L" else r
        st = edges[(mm // 3) * 2 + mm % 3]
        if not st & D["EG_DOOR"]:
            continue
        top = SR * s
        m[top][dcol] = m[top][dcol + 1] = T["T_BRICK"]
        m[top + 1][dcol], m[top + 1][dcol + 1] = T["T_DOOR_ARCH_L"], T["T_DOOR_ARCH_R"]
        for row in range(top + 2, top + SA):
            m[row][dcol] = T["T_DOOR_L"]
            m[row][dcol + 1] = T["T_DOOR_LOCK"] if st & (D["EG_LOCK"] | D["EG_SEAL"]) else T["T_DOOR_R"]
    p = d[D["RD_PITCOL"]]
    if p:
        m[F0][p - 1], m[F0][p + 3] = T["T_PIT_L"], T["T_PIT_R"]
        for c in range(p, p + 3):
            m[F0][c] = T["T_AIR"]
    for f, s in (("RD_UPCOL", 0), ("RD_DNCOL", 2), ("RD_ARRCOL", 0), ("RD_EXITCOL", 2), ("RD_LAD1", 1), ("RD_LAD2", 1)):
        col = d[D[f]]
        if not col:
            continue
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
    arr = d[D["RD_ARRCOL"]]
    if arr:
        for k in range(3):
            m[0][arr + k] = T["T_RUBBLE"]
    for i in range(D["FLOOR_MAX"]):
        o = OFF_FLOOR + i * D["FL_STRIDE"]
        room, col, item = blk[o], blk[o + 1], blk[o + 2]
        if room != D["FL_EMPTY"] and room & D["FL_ROOM_MASK"] == r and item:
            s = 1 if room & D["FL_S1"] else 0
            for k in (0, 1):                  # FLOOR1: T_ITEM0 + 2s (+1 lower row) over 2 x 2 cells
                m[SR * s + SA - 2][col + k] = T["T_ITEM0"] + 2 * s
                m[SR * s + SA - 1][col + k] = T["T_ITEM0"] + 2 * s + 1
    return [t for row in m for t in row]


def final_room(blk, r):
    """== room_model.render_room(blk, r) for a PRESENT room: structure, the decor derived from
    RD_SEED (seed 0 = bare), then the shut level-exit gate."""
    d = desc(blk, r)
    flat = structure(blk, r)
    seed = d[D["RD_SEED"]] | d[D["RD_SEED"] + 1] << 8
    if seed:
        flat, _ = decorgen.decorate(flat, DEPTH, seed)
    xc = d[D["RD_EXITCOL"]]
    if xc and not blk[D["LVL_FLAGS"] - BASE] & D["LF_GRATE_OPEN"]:
        for k in range(3):
            flat[F1 * COLS + xc + k] = T["T_GRATE_SHUT"]
    return flat


# ---- drip model (tests/drip.py model_room == src/drip7.asm drip_room) ----------------------------
def drip_sources(rmap, depth, seed):
    def lfsr(x):
        x <<= 1
        return (x ^ 0x1D) & 255 if x > 255 else x
    st = [((seed & 255) ^ (seed >> 8)) or 1]

    def rnd():
        st[0] = lfsr(st[0])
        return st[0]
    if depth == 0 or depth >= D["LEVELS"]:
        return []
    n = 1 if (depth - 1) % 3 == 0 else 2
    src = []
    for _ in range(n):
        for _ in range(DRIP["DRIP_TRIES"]):
            c = rnd() & 31
            sr = rnd() & 3
            e = rnd()
            if sr == 3:
                continue
            r = sr + (9 if e & 1 else 0)
            if r == 0 or rmap[r * COLS + c] != 0 or not 1 <= rmap[(r - 1) * COLS + c] <= 3 \
                    or rmap[(r + 1) * COLS + c] != 0:
                continue
            if src and abs(src[0][0] - c) < DRIP["DRIP_DMIN"]:
                continue
            src.append((c, r))
            break
    return src


# ---- spots ----------------------------------------------------------------------------------------
def box_cells(col, top):
    return [(top + dr) * COLS + col + dc for dr in range(BOX_H) for dc in range(BOX_W)]


def box_air(flat, col, top):
    return all(flat[i] == T["T_AIR"] for i in box_cells(col, top))


def spot_top(s):
    return SR * s + 1


def pick_spots(blk):
    """For each spec spot the legal x (box all T_AIR in the decor-free structure, cols 2..28,
    clear of trap plates) nearest the spec x (left of it first on a tie -> the lower x)."""
    structs = {r: structure(blk, r) for r in (ROOM_A, ROOM_B, ROOM_C)}
    out = []
    for name, r, s, x0 in SPOT_SPEC:
        top = spot_top(s)
        cand = []
        for x in range(2, 30 - BOX_W):
            if not box_air(structs[r], x, top):
                continue
            if any(tr == r and ts == s and not (x + BOX_W - 1 < tc or x > tc + 1) for tr, ts, tc, _ in TRAPS):
                continue
            cand.append((abs(x - x0), x))
        out.append((name, r, s, min(cand)[1], x0))
    return out


# ---- decor seed search ----------------------------------------------------------------------------
def room_candidates(blk, r, spots):
    """{frozenset(decor ids 32..59, map + animation frames): (richness, seed)} over every seed that keeps the room's boxes
    all T_AIR and its drip sources out of the boxes' cols (same storey)."""
    base = structure(blk, r)
    boxes = [(s, x) for (_, rr, s, x, _) in spots if rr == r]
    xc = desc(blk, r)[D["RD_EXITCOL"]]
    best = {}
    for seed in range(1, SEED_MAX + 1):
        m, anim = decorgen.decorate(list(base), DEPTH, seed)
        if xc:
            for k in range(3):
                m[F1 * COLS + xc + k] = T["T_GRATE_SHUT"]
        if not all(box_air(m, x, spot_top(s)) for s, x in boxes):
            continue
        dr = drip_sources(m, DEPTH, seed)
        if any(sr // SR == s and x <= c < x + BOX_W for (c, sr) in dr for s, x in boxes):
            continue
        # TUT0-F1: + the ANIM_LIST alternate glyph ids (AL_TYPE = base + area + k: never in the map
        # at derive time, swapped in by decor_tick; e.g. TORCH_TALL 32 -> flames 40..42)
        ids = frozenset(t for t in list(m) + anim[2::4] if ID_LO <= t <= ID_HI)
        rich = sum(1 for a, b2 in zip(m, base) if a != b2)
        if ids not in best or rich > best[ids][0]:
            best[ids] = (rich, seed)
    return best


DECOR_MARGIN = 0          # TUT0-F1: the model now counts the animation frame ids too (the slack hid the flame
                          # overlap); the D1 torch needs the whole 11-id budget


def choose_seeds(blk, spots):
    cands = {r: room_candidates(blk, r, spots) for r in (ROOM_A, ROOM_B, ROOM_C)}
    ca, cb, cc = (sorted(cands[r].items(), key=lambda kv: (len(kv[0]), -kv[1][0])) for r in (ROOM_A, ROOM_B, ROOM_C))
    for limit in (DECOR_IDS_MAX - DECOR_MARGIN, DECOR_IDS_MAX):
        best = None
        for (ia, (ra, sa)), (ib, (rb, sb)) in itertools.product(ca, cb):
            uab = ia | ib
            if len(uab) > limit:
                continue
            for ic, (rc, sc) in cc:
                u = uab | ic
                if len(u) > limit:
                    continue
                key = (ra + rb + rc, -len(u))      # richest decor inside the limit
                if best is None or key > best[0]:
                    best = (key, {ROOM_A: sa, ROOM_B: sb, ROOM_C: sc}, u,
                            {ROOM_A: ia, ROOM_B: ib, ROOM_C: ic})
        if best:
            break
    return best, {r: len(c) for r, c in cands.items()}


# ---- asm emit -------------------------------------------------------------------------------------
def dump(label, data, per=16, comment=None):
    out = [f"{label}:" + (f"        ; {comment}" if comment else "")]
    for i in range(0, len(data), per):
        out.append("                DEFB " + ", ".join(f"${v:02X}" for v in data[i:i + per]))
    return out


def emit(blk, spots, free_ids, seeds, used, per_room):
    lo = lambda name: D[name] - BASE   # noqa: E731
    hdr = blk[0:D["LVL_HDR_LEN"]]
    edge = blk[OFF_EDGE:OFF_EDGE + D["EDGES_H"]]
    rdesc = blk[OFF_DESC:OFF_DESC + 9 * D["RD_STRIDE"]]
    trap = blk[D["TRAP_LIST"] - BASE:D["TRAP_LIST"] - BASE + 16]
    floor = blk[OFF_FLOOR:OFF_FLOOR + D["FLOOR_MAX"] * D["FL_STRIDE"]]
    o = ["; GENERATED by tools/tut0_level.py (edit the tool, re-run). The TUT0 D0 level block (spec",
         "; docs/design/tutorial_d0.md §2, tut0_split.md T4). Field layouts: src/level_defs.asm / item_defs.asm.",
         f"; LVL_DEPTH stays {DEPTH} during D0 (spec §0). The blob copies each image to its address.",
         f"TUT0_ROOM_A     EQU {ROOM_A}",
         f"TUT0_ROOM_B     EQU {ROOM_B}",
         f"TUT0_ROOM_C     EQU {ROOM_C}",
         f"TUT0_HDR_COPY   EQU {H['MASTER_SEED']}      ; copy only the first 14 header bytes: MASTER_SEED (2 B) belongs to the game",
         "; no item identification state exists in this build (item_defs.asm ITEM_RAM: no ID_MAP / KNOWN,",
         "; game.md 8.8 CUT): D0 potions / scroll are known by construction, the blob needs nothing"]
    o += dump("tut0_lvl_state", hdr, comment=f"-> LVL_STATE ({len(hdr)} B)")
    o += dump("tut0_edge_tab", edge, comment=f"-> EDGE_TAB ({len(edge)} B; B-C edge = index {EDGE_BC}: LINK|DOOR|LOCK)")
    o += dump("tut0_room_desc", rdesc, comment=f"-> ROOM_DESC (9 x {D['RD_STRIDE']} B; rooms {ROOM_A} A, {ROOM_B} B, {ROOM_C} C)")
    o += dump("tut0_trap_list", trap, comment=f"-> TRAP_LIST (16 B: 6 x 2 B, TRAP_N at +{D['TRAP_N'] - D['TRAP_LIST']} = {len(TRAPS)}, 3 spare)")
    o += dump("tut0_floor_list", floor, comment=f"-> FLOOR_LIST ({D['FLOOR_MAX']} x {D['FL_STRIDE']} B; FLOOR_N = {len(ITEMS)})")
    o += [f"TUT0_FLOOR_N     EQU {len(ITEMS)}",
          "; spot table: 3 B per spot = room, col (box left), map row (box top); box = 3 cols x 6 rows, all T_AIR",
          f"TUT0_SPOT_N      EQU {len(spots)}",
          "tut0_spots:"]
    for i, (name, r, s, x, x0) in enumerate(spots):
        o.append(f"                DEFB {r}, {x:2d}, {spot_top(s):2d}        ; {i} {name:5s} storey {s}" +
                 ("" if x == x0 else f" (spec x {x0}, moved to {x})"))
    for i, (name, *_rest) in enumerate(spots):
        o.append(f"TUT0_SP_{name:5s} EQU {i}")
    ids = list(free_ids) + [T["T_AIR"]]      # source cell i -> id (cell MENTOR_BLANK: T_AIR, no glyph)
    left = [ids[3 * (i // 3) + 2 - i % 3] for i in range(MENTOR_CELLS)]
    o += [f"; the {MENTOR_IDS} per-level tile ids (32..59) the decor of A / B / C does not use (map ids + the",
          "; ANIM_LIST flame frame ids, TUT0-F1): id i holds source cell i (row i // 3, col i % 3) of the image",
          f"; (bit-reversed when facing left); cell {MENTOR_BLANK} is blank in every image: T_AIR. tut_stamp: box cell",
          "; (r, c) := tut0_mentor_ids[3r + c] (right) / tut0_mentor_ids_l[3r + c] (left: each row reversed)",
          "tut0_mentor_ids:",
          "                DEFB " + ", ".join(str(i) for i in ids[:9]),
          "                DEFB " + ", ".join(str(i) for i in ids[9:]),
          "tut0_mentor_ids_l:",
          "                DEFB " + ", ".join(str(i) for i in left[:9]),
          "                DEFB " + ", ".join(str(i) for i in left[9:]),
          f"TUT0_MENTOR_N    EQU {MENTOR_IDS}      ; ids in use (contiguous from TUT0_MENTOR_ID0)",
          f"TUT0_MENTOR_ID0  EQU {free_ids[0]}",
          f"; Goblin (spec §2.3): parked in room C, asleep, on the shut grate",
          f"TUT0_GOB_ROOM    EQU {GOB_ROOM}",
          f"TUT0_GOB_X       EQU {GOB_X}",
          f"TUT0_GOB_S       EQU {GOB_S}",
          f"; decor: seeds A {seeds[ROOM_A]:#06x} B {seeds[ROOM_B]:#06x} C {seeds[ROOM_C]:#06x}; "
          f"distinct ids in use {sorted(used)} ({len(used)} <= {DECOR_IDS_MAX})",
          f"TUT0_DECOR_IDS_MAX EQU {DECOR_IDS_MAX}"]
    return "\n".join(o) + "\n"


def build(verbose=True):
    blk0 = build_block({})
    spots = pick_spots(blk0)
    best, ncand = choose_seeds(blk0, spots)
    if best is None:
        seeds = {ROOM_A: 0, ROOM_B: 0, ROOM_C: 0}          # user-approved fallback: bare rooms
        used, per_room = frozenset(), {r: frozenset() for r in seeds}
        print("tut0_level: NO seed set fits the id budget -> RD_SEED 0 (bare rooms)")
    else:
        _, seeds, used, per_room = best
    blk = build_block(seeds)
    free = [i for i in range(ID_LO, ID_HI + 1) if i not in used][:MENTOR_IDS]
    assert len(free) == MENTOR_IDS, f"fewer than {MENTOR_IDS} free ids"
    assert free == list(range(free[0], free[0] + MENTOR_IDS)), f"mentor ids not contiguous: {free}"
    if verbose:
        print("seed candidates per room:", ncand)
        print("seeds:", {("A", "B", "C")[[ROOM_A, ROOM_B, ROOM_C].index(r)]: f"{s:#06x}" for r, s in seeds.items()})
        print("decor ids per room:", {("A", "B", "C")[[ROOM_A, ROOM_B, ROOM_C].index(r)]: sorted(per_room[r]) for r in seeds},
              "total", len(used))
        print("spots:", [(n, r, x, spot_top(s)) for n, r, s, x, _ in spots])
        print("mentor ids:", free)
    return blk, spots, free, seeds, used, per_room


def main(argv):
    out = Path(argv[1]) if len(argv) > 1 else ROOT / "build" / "tut" / "tut0_level.asm"
    blk, spots, free, seeds, used, per_room = build()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(emit(blk, spots, free, seeds, used, per_room))
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv)
