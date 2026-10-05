#!/usr/bin/env python3
"""Stage 3B world geometry suite (B3B-3: 2 storeys x 9 rows, plan "3B breakdown"
D3/D4, game.md §2.1). Drives build/wazhack.sna in ZEsarUX over ZRCP.

  W0  rooms: the four descriptors in memory == game_lib.ROOM_LADDERS, and every
      room map (built by the engine) obeys the 2x9 structure: floor rows 8/17,
      walls at cols 0/31 except the open exit storey, ladder cells exactly on
      rows 9s-1..9s+7, holes only in floor rows, potions on row 9s+7.
  W1  walk: one col per turn on the bottom storey, y = 9s+8-h throughout.
  W2  climb: {5,1} in room A, up 9 turns (one row each) to storey 0, down 9.
  W3  exits L / R / U / D each: A->B (R), B->C (D, {24,2}), C->B (U, {24,0}),
      B->A (L), C->D (L), D->C (R); arrival at x = 1 / 31-w / col and
      y = 9s+8-h; the panel rows 18..23 are not scrolled.
  W4  after every W1-W3 (and W5-W9) step: displayed (bank 7) == composed
      (bank 5), and every playfield cell outside the drawn sprites shows
      exactly its ROOM_MAP tile (glyph + attr) on both screens.
  B3B-5 (doors, pits, blocks, jump; rooms A-D carry one of each, data.asm):
  W5  door: C closes the open A|B door (1 turn), a bump on it opens it again
      (1 turn, no move), EDGE_TAB + map + both screens follow; through it into
      B, the same door shows open there; the close / open ticks are measured
      (input tick incl. the 2 x 6 cell repaint) against the 126k T budget.
  W6  locked: a bump on a LOCKed door = no turn, nothing changes, the message;
      an opener monster is refused too.
  W7  close refusals (no turn): a body in the door cells, not adjacent,
      facing away.
  W8  pit fall (B, p 20): H onto x == p -> step + 9-row drop at 8 px/tick
      (px = 8x), y = storey 1, HP -1..4, 1 turn; no soft-lock (the hero acts
      next turn); a monster in the landing box goes PENDING; at 1 HP the fall
      kills. Jump (game.md §2.4): K+L clears the pit (14-tick arc, py table),
      refused on the next turn, refused onto x == p.
  W9  walkers never step onto x == p (rat patrol in B), flyers cross it (bat);
      at a closed door an opener (goblin) opens it spending its step, a
      non-opener (rat) and a flyer (bat) are blocked (try_step unit stubs).
  B3B-8 (build_room_map v2 + level themes; rooms A-D are a PROTO level state
  since B3B-8, W0/W3 compare their maps with tests/room_model.py, W4 knows the
  row-17 ornament). Generated levels run through far3 level_gen +
  level_load_tiles + room_show + present_full (stubs; B3B-12 wires play):
  W11 per depth 1..8: floor / wall attrs == game.md §1.2, ids 32..63 (glyphs,
      attrs, TILE_FLAGS) == the bank-7 slot, every room: map == model, floor
      rows hold floor-class tiles only, both screens == map (+ ornament), all
      playfield attrs legal for the depth.
  W12 re-entry: 24 generated rooms built, left (another room shown), rebuilt:
      ROOM_MAP, bank 5, screen 2 and the shadow byte-identical.
  W12M 40 random (depth, seed, master): the Z80 block == levelgen.py and every
      room's engine map == the model of levelgen.py's block (doors, pits,
      blocks, arrival / exit shafts, 2nd ladders all seen) and passes the
      order-free invariants (invariants()); build T-states.
  W13 decor deriver (B3B-9): 12 generated levels (depths 1..8), every room: ROOM_MAP and
      ANIM_LIST == tools/decorgen.py byte for byte + an independent rules checker
      (cell class / solidity / rows / ladders / budgets); decor_room T-states.
      B3B-10: every room also built into NEXT_MAP (-> ANIM_N2 / ANIM_LIST2 only);
      a wall-heavy Python sweep (rooms with block / pit / door) and synthetic
      maps (structural cells inside the decor ring; 24 also through the Z80
      decor_room) under the same checker; large objects counted by their lead
      glyph cell (tileset_ids.inc), not 4-connected clusters.
  W14 decor_tick (B3B-10): room A of the PROTO level made a seeded depth-1
      room and played: 40 ticks against a Python model of decor_tick (lists,
      map, bank-5 cells, the shadow), displayed == composed at every present,
      shadow == map; a due cell under the hero holds, then steps once it left;
      decor_tick T (mean <= 2.5k, max <= 4k); the scroll A -> B brings room B's
      ANIM_LIST (B3B-9 review fix) and B animates.

  B3B-11 (panel engine, concept-screen §5; D5 queue: one item per tick, never
  in a turn's input tick):
  W15 static panel at start (log line, attrs, depth, HP / potion fields);
      quaff: the input tick leaves the panel untouched, the HP number / bar,
      the log line and the potion count are composed <= 3 ticks after it and
      displayed one tick later; 3 pushed messages: 2-row scroll (rows 22 / 23
      == the last two, attrs $07 / $47); B3B-11b: 2nd-frame ticks draw small
      items only, the log waits for a 1st-frame tick; ring overflow
      drops + counts, log_push_end replaces the newest; print6 tails exact; HP bar fill
      == round(32 * hp / max); T of a whole log item (scroll + 32 chars) and
      of print6 per char; the Mage's panel golden (w15_panel_mage).
  B3B-13 (token text, src/strings.txt -> tools/textpack.py):
  W17 every string decoded by tk_get into a buffer == its text (exact, 32..127)
      + the decode cost per char; every string pushed by id (msg_push) and
      drawn by item_log / print6t == the reference render; $C000 handed back;
      composed impact lines (show_impact_msg) == text; T per log item.
  B11 (user bug: the hero fell a storey where the floor is drawn, walking
  into the left room):
  W21 generated D1s (seed_fixed, 2 masters): every storey-0 horizontal exit,
      both ways: the exit turn never enters M_FALL, the hero arrives standing
      on storey 0 at x = 1 / 31-w with its HP, the new room's map == model and
      both screens == map; then walking on, the hero falls only at x == the
      pit col, onto a hole the screen shows (before the fix a left-exit step
      landed on x == 0 == "no pit" RD_PITCOL and dropped the hero).

Usage: ZRCP_PORT=10001 python3 tests/world.py [W1 W3 W11 ...] [--update-golden [--png DIR]]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_argv = sys.argv[1:]
sys.argv = [sys.argv[0], "999"]               # keep game.py's item filter inert
import game  # noqa: E402
import room_model  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import textpack  # noqa: E402
STRINGS = textpack.read_strings()           # [(name, text)], id order (B3B-13)
from game_lib import (Harness, S, EMU_ARGS, attr_at, cell_bytes, split_frame,  # noqa: E402
                      stand_y, is_standing, item_row, ladder_rows, ROOM_LADDERS,
                      ROOM_A, ROOM_B, ROOM_C, ROOM_D, ROOM_LETTER,
                      STOREY_ROWS, STOREY_AIR, STOREY_COUNT, PLAY_ROWS, PANEL_ROW,
                      MAP_LEN, GS_PLAYING, GS_DEAD, K_KNIGHT, K_WIZARD, EF_LEFT, EF_ACTIVE,
                      EF_PLAYER, EF_HOSTILE, EF_PENDING)

ONLY = {a.upper() for a in _argv if not a.startswith("--") and not os.path.isdir(a)}
game.UPDATE = "--update-golden" in _argv
game.PNG_DIR = _argv[_argv.index("--png") + 1] if "--png" in _argv else None


def want(tag):
    return not ONLY or tag in ONLY


class W(game.T):
    def screen_vs_map(self, tag):
        """W4: both screens == ROOM_MAP outside sprite footprints; displayed ==
        composed. Returns a list of problems (empty = ok)."""
        bad = []
        fr, comp = self.frame(), self.composed_frame()
        if fr != comp:
            diff = [i for i in range(len(fr)) if fr[i] != comp[i]]
            bad.append((tag, "displayed != composed", len(diff), diff[0]))
        tabs = self.bg_tables()
        covered = set()
        for s_ in range(16):
            e = self.ent(s_)
            if e["DVIS"] & 1:
                covered |= {(c, r) for c in range(e["DCOL"], e["DCOL"] + e["DCOLS"])
                            for r in range(e["DROW"], e["DROW"] + e["DROWS"])}
                if e["DROW"] + e["DROWS"] > PLAY_ROWS:
                    bad.append((tag, "sprite footprint below the playfield", s_, e["DROW"]))
        for scr, f in (("displayed", fr), ("composed", comp)):
            cells = []
            for r in range(PLAY_ROWS):
                for c in range(32):
                    if (c, r) in covered:
                        continue
                    g, a = room_model.expected_cell(*tabs, c, r)
                    if attr_at(f, c, r) != a or bytes(cell_bytes(f, c, r)) != g:
                        cells.append((c, r, tabs[0][r * 32 + c]))
            if cells:
                bad.append((tag, scr + " cells != ROOM_MAP", len(cells), cells[:4]))
        return bad


def map_structure(p, r):
    """W0 / W3 / W5 / W8 (B3B-8): the engine-built ROOM_MAP of room r (CUR_ROOM)
    == the spec model of room r (tests/room_model.py render_room) over the
    level state in memory (descriptors, EDGE_TAB door states, FLOOR_LIST)."""
    m = p.z.read_memory(S["ROOM_MAP"], MAP_LEN)[:32 * PLAY_ROWS]
    want = room_model.render_room(room_model.read_block(p), r)
    return [(r, i % 32, i // 32, m[i], want[i]) for i in range(len(want)) if m[i] != want[i]]


# ---------------------------------------------------------------------------
# B3B-8 (W11 / W12 / W12M): generated levels through the real engine path.
# A stub (free low RAM above LOWRAM_END_3B) runs far3 level_gen +
# level_load_tiles, then room_show + present_full per room (the B3B-12 level
# entry, not wired into play yet), or only far3 build_room_map (T-states).
# ---------------------------------------------------------------------------
STUB_ORG = S["LOWRAM_END_3B"]


def w16(v):
    return [v & 255, v >> 8]


def run_code(p, code, limit=4000000):
    """Run raw Z80 at STUB_ORG under DI up to its end (jr $). -> (ok, T)."""
    code = bytes(code) + b"\x18\xfe"
    end = STUB_ORG + len(code) - 2
    p.z.cmd("write-memory %d %s" % (STUB_ORG, " ".join(str(b) for b in code)))
    p.z.cmd("set-breakpoint 3 PC=%d" % end)
    p.extra_probes = {end}
    p.z.cmd("set-register PC=%d" % STUB_ORG)
    p.z.cmd("reset-tstates-partial")
    p.z.cmd("run %d" % limit)
    ts = int(p.z.cmd("get-tstates-partial"))
    ok = p.pc() == end
    p.z.cmd("set-breakpoint 3")
    p.extra_probes = set()
    return ok, ts


def head():
    return [0xF3, 0x31] + w16(S["WORKSTORE_TOP"])             # di ; ld sp,WORKSTORE_TOP


def gen_level(p, depth, seed, master=0):
    """Z80 level_gen (far3) + level_load_tiles. -> (ok, T gen, T tiles, block)."""
    p.z.cmd("write-memory %d %d %d" % (S["LVL_SEED"], seed & 255, seed >> 8))
    p.z.cmd("write-memory %d %d %d" % (S["MASTER_SEED"], master & 255, master >> 8))
    ok1, t1 = run_code(p, head() + [0x3E, depth, 0x21] + w16(S["level_gen"]) + [0xCD] + w16(S["far3"]))
    ok2, t2 = run_code(p, head() + [0x3A] + w16(S["LVL_DEPTH"]) + [0xCD] + w16(S["level_load_tiles"]))
    return ok1 and ok2, t1, t2, room_model.read_block(p)


def build_only(p, r, page=None):
    """far3 build_room_map (room r -> ROOM_MAP, or the map at `page`). -> (ok, T, map)."""
    page = S["ROOM_MAP"] >> 8 if page is None else page
    ok, t = run_code(p, head() + [0x3E, r, 0x16, page, 0x21] + w16(S["build_room_map"])
                     + [0xCD] + w16(S["far3"]))
    return ok, t, bytes(p.z.read_memory(page << 8, 32 * PLAY_ROWS))


def bank3_poke(p, addr, v):
    """Write one byte of bank 3 ($C000 window address) whatever is paged."""
    p.z.cmd("set-memory-zone 0")
    try:
        p.z.cmd("write-memory %d %d" % (3 * 16384 + addr - 0xC000, v))
    finally:
        p.z.cmd("set-memory-zone -1")


_DFLAGS = {}


def depth_flags(p, d):
    """TILE_FLAGS of depth d as level_load_tiles leaves them: the machine's
    common ids 0..31 (static) + the bank-7 slot's ids 32..63 (from the .sna)."""
    if d not in _DFLAGS:
        from game_lib import SNA_RAM
        slot = d - 1
        so = 7 * 16384 + (S["TSET_LO"] if slot < 4 else S["TSET_HI"]) - 0xC000 + (slot & 3) * S["TSET_STRIDE"]
        _DFLAGS[d] = bytes(p.z.read_memory(S["tile_flags"], 32)) + SNA_RAM[so + 288:so + 320]
    return _DFLAGS[d]


_LEAD = {}


def lead_ids(d):
    """Depth d's large animated objects -> the F1 id of each one's FIRST glyph-swap
    cell (row-major), parsed from assets/gfx/tiles/tileset_ids.inc (frame 1 vs 2):
    exactly one per placed object, so counting them never merges neighbours."""
    if not _LEAD:
        import re
        pat = re.compile(r"TS(\d)_([A-Z_]+?)_F(\d)_R(\d)C(\d)\s+EQU (\d+)")
        objs = {}
        path = os.path.join(os.path.dirname(HERE), "assets", "gfx", "tiles", "tileset_ids.inc")
        for line in open(path):
            mm = pat.match(line)
            if mm:
                dd, name, f, r, c, v = mm.groups()
                objs.setdefault((int(dd), name), {}).setdefault(int(f), {})[(int(r), int(c))] = int(v)
        for (dd, name), fr in objs.items():
            if 2 in fr:
                diff = sorted(k for k in fr[1] if fr[2][k] != fr[1][k])
                _LEAD.setdefault(dd, set()).add(fr[1][diff[0]])
    return _LEAD.get(d, set())


def drip_rules(m, base, flags, ents, d):
    """W13 independent drip checker, from concept-screen 3.3 "Drip placement": -> [errors]."""
    T = room_model.T
    SOLID = S["TF_SOLID"]
    D1, D2 = T["T_DRIP1"], T["T_DRIP2"]
    cells = [(j % 32, j // 32) for j in range(576) if m[j] == D1]
    errs = []
    if len(cells) > {1: 1, 2: 2, 3: 2, 4: 1, 5: 2, 6: 2, 7: 1, 8: 0}[d]:
        errs.append(("too many drips for the depth", d, len(cells)))
    # structural cells: ladder / hole, door jambs, pit caps, door arch / planks / lock, grate, rubble
    avoid = set(range(T["T_LAD_L"], T["T_HOLE_R"] + 1)) | {T["T_DOOR_JAMB_L"], T["T_DOOR_JAMB_R"]} \
        | set(range(T["T_PIT_R"], T["T_RUBBLE"] + 1))
    for c, row in cells:
        j = row * 32 + c
        if base[j] != T["T_AIR"]:
            errs.append(("drip on a non-air base cell (decor / item / trap)", c, row))
        if row % 9 > 2 or row == 0:
            errs.append(("drip outside storey rows 0..2 (or no cell above)", c, row))
            continue
        if not flags[m[j - 32]] & (SOLID | S["TF_FLOOR"]):    # ceiling brick or the platform above
            errs.append(("drip: cell above not solid", c, row))
        if flags[m[j + 32]] & SOLID or m[j + 32] != T["T_AIR"]:
            errs.append(("drip: cell below not air", c, row))
        st = row // 9 * 9
        for rr in range(st, st + 9):
            for cc in (c - 1, c, c + 1):
                if 0 <= cc < 32 and base[rr * 32 + cc] in avoid:
                    errs.append(("drip within 1 col of a ladder / door / jamb / grate / cap / hole", c, row))
        for c2, r2 in cells:
            if (c2, r2) != (c, row) and abs(c2 - c) < 6:
                errs.append(("drips < 6 cols apart", c, c2))
        if [list(e) for e in ents if (e[0], e[1]) == (c, row)] != [[c, row, D2, (c + row) & 7]]:
            errs.append(("drip ANIM_LIST entry wrong (one glyph swap -> DRIP2, phase (col+row)&7)", c, row))
    if d == 8 and cells:
        errs.append(("drip on D8", cells))
    if sum(1 for e in ents if e[2] >= 16) > 4:
        errs.append(("more than 4 glyph-swap entries with drips", len(ents)))
    return errs


DECOR_MOUNT = {"TORCH_TALL", "TORCH_SLIM", "WINDOW_ARCH", "WINDOW_BAR", "BANNER", "BANNER_TALL",
               "BOOKSHELF", "TORCH_SMALL"}
DECOR_CEIL = {"CHAIN", "MOSS"}
DECOR_FLOOR = {"SKULLS", "CANDLES", "CAULDRON", "BRAZIER", "BRAZIER_BIG"}
DECOR_PATCH = {"PATCH_A", "PATCH_B", "WALL_DITHER", "WALL_PATCH", "WALL_FADE"}
DECOR_BRICK = {"PILLAR"}
DECOR_COB = {"COBWEB", "COBWEB_R"}
_OBJS = {}


def decor_objs(d):
    """(id -> object name, shape(id, comp, r0, c0) -> the {cell: id} the whole object would
    occupy at the component's top-left, None if unknown) of depth d: frame-1 ids parsed
    from tileset_ids.inc + the common small decor (concept-screen 3.3 catalogue)."""
    import re
    T = room_model.T
    if d not in _OBJS:
        objs = {}                                   # name -> {(r, c): id}
        path = os.path.join(os.path.dirname(HERE), "assets", "gfx", "tiles", "tileset_ids.inc")
        for line in open(path):
            mm = re.match(r"TS(\d)_([A-Z_]+?)_(?:F(\d)_)?R(\d)C(\d)\s+EQU (\d+)", line)
            if mm and int(mm.group(1)) == d and int(mm.group(3) or 1) == 1:
                objs.setdefault(mm.group(2), {})[(int(mm.group(4)), int(mm.group(5)))] = int(mm.group(6))
        objs["CHAIN"] = {(0, 0): T["T_CHAIN"], (1, 0): T["T_CHAIN"]}
        objs["SKULLS"] = {(0, 0): T["T_SKULLS"]}
        objs["TORCH_SMALL"] = {(0, 0): T["T_TORCH_T"], (1, 0): T["T_TORCH_B"]}
        objs["CANDLES"] = {(0, 0): T["T_CANDLES"]}
        for nm, k in (("WALL_DITHER", "T_WALL_DITHER"), ("WALL_PATCH", "T_WALL_PATCH"),
                      ("WALL_FADE", "T_WALL_FADE")):
            objs[nm] = {(0, 0): T[k]}
        names = {}
        for nm, g in objs.items():
            if nm == "LECTERN":
                continue
            for v in g.values():
                names.setdefault(v, nm)
        _OBJS[d] = (names, objs)
    names, objs = _OBJS[d]
    T = room_model.T
    comp_ids = (T["T_WALL_PATCH"], T["T_WALL_FADE"], T["T_WALL_DITHER"])

    def shape(i, comp, r0, c0):
        nm = names.get(i)
        if nm in ("WALL_DITHER", "WALL_PATCH", "WALL_FADE") and len(comp) == 3:
            return {r0 * 32 + c0: comp_ids[0], r0 * 32 + c0 + 1: comp_ids[1], (r0 + 1) * 32 + c0: comp_ids[2]}
        if nm is None:
            return None
        return {(r0 + r) * 32 + c0 + c: v for (r, c), v in objs[nm].items()}
    return names, shape


def decor_rules(m, base, flags, al, d, sizes, need_patch=True):
    """W13 independent decor checker (docs, not the generator): -> [errors].
    m / base = the room with / without decor, flags = TILE_FLAGS[64] of the
    depth, al = ANIM_LIST bytes; sizes (dict) accumulates air / wall / anim /
    large counts."""
    T = room_model.T
    SOLID, ANIMF = S["TF_SOLID"], S["TF_ANIM"]
    T_AIR, T_BRICK = T["T_AIR"], T["T_BRICK"]
    lad = set(range(T["T_LAD_L"], T["T_HOLE_R"] + 1))
    errs = []
    ch = [j for j in range(576) if m[j] != base[j]]
    names, shape = decor_objs(d)
    drip = {T["T_DRIP1"], T["T_DRIP2"]}
    floorish = lambda t: t in (T["T_PLAT"], T["T_WALLF"])          # noqa: E731
    for j in ch:                                                    # per cell: base class vs solidity
        c, row = j % 32, j // 32
        if m[j] in drip:
            continue                                # drips: drip_rules()
        nm = names.get(m[j])
        if nm is None:
            errs.append(("unknown decor id", c, row, m[j]))
            continue
        patch = nm in DECOR_PATCH
        want_base = T_BRICK if nm in DECOR_BRICK else T_AIR
        if base[j] != want_base:
            errs.append((f"{nm} on a {base[j]} cell (wants {want_base})", c, row))
        sizes["wall" if base[j] == T_BRICK else "air"] = sizes.get("wall" if base[j] == T_BRICK else "air", 0) + 1
        if patch:
            # game.md 1.2 (D1 amendment): back-wall patches are NON-solid, on T_AIR. The TILE_FLAGS
            # solid bit of their ids is staff data: counted, not failed, while still set.
            if flags[m[j]] & SOLID:
                sizes["patch_solid"] = sizes.get("patch_solid", 0) + 1
        elif nm in DECOR_BRICK:
            if not flags[m[j]] & SOLID:
                errs.append(("pillar not solid", c, row))
        elif flags[m[j]] & SOLID:
            errs.append(("solid decor on an air cell", c, row))
        if nm in DECOR_FLOOR:
            pass                                    # floor class: exempt from the 2-rows-above rule
        elif row % 9 > 5:
            errs.append((f"{nm} in the 2 rows above a floor / floor row", c, row))
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                rr, cc = row + dr, c + dc
                if 0 <= rr < 18 and 0 <= cc < 32 and base[rr * 32 + cc] in lad:
                    errs.append(("decor adjacent to a ladder", c, row))
    # components (8-connected, drips apart: their own rules): one whole object each, by class
    cells = {j for j in ch if m[j] not in drip and m[j] in names}
    seen, ncob, npatch_cells, npatch = set(), 0, 0, 0
    for j0 in sorted(cells):
        if j0 in seen:
            continue
        comp, stack = set(), [j0]
        while stack:
            x = stack.pop()
            if x in comp or x not in cells:
                continue
            comp.add(x)
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    rr, cc = x // 32 + dr, x % 32 + dc
                    if 0 <= rr < 18 and 0 <= cc < 32:
                        stack.append(rr * 32 + cc)
        seen |= comp
        r0, c0 = min(x // 32 for x in comp), min(x % 32 for x in comp)
        r1 = max(x // 32 for x in comp)
        nm = names[m[j0]]
        want = shape(m[min(comp)], comp, r0, c0)
        if want is None or want != {x: m[x] for x in comp}:
            errs.append(("decor cells are not exactly one whole object (touching objects?)", c0, r0, nm))
            continue
        top, bot = r0 % 9, r1 % 9
        cols_ok = lambda lo, hi: all(lo <= x % 32 <= hi for x in comp)      # noqa: E731
        if nm in DECOR_MOUNT:
            if top != 1 or not cols_ok(1, 30):
                errs.append((f"{nm}: mount top row must be storey row 1, cols 1..30", c0, r0))
        elif nm in DECOR_CEIL:
            above = base[(r0 - 1) * 32 + c0] if r0 else None
            if top != 0 or not cols_ok(1, 30) or (above is None and (nm == "MOSS")) \
                    or (above is not None and not floorish(above)):
                errs.append((f"{nm}: ceiling row 0, hung from T_PLAT / T_WALLF (chain also screen top)", c0, r0))
        elif nm in DECOR_FLOOR:
            if bot != 7 or not cols_ok(1, 30) or \
                    not all(floorish(base[(r1 + 1) * 32 + x % 32]) for x in comp if x // 32 == r1):
                errs.append((f"{nm}: floor object must end on row 7 over T_PLAT / T_WALLF", c0, r0))
        elif nm in DECOR_PATCH:
            npatch += 1
            npatch_cells += len(comp)
            if top < 1 or bot > 5 or not cols_ok(2, 29):
                errs.append((f"{nm}: patch inside storey rows 1..5, cols 2..29", c0, r0))
        elif nm in DECOR_BRICK:
            npatch_cells += len(comp)
            if top < 1 or bot > 5:
                errs.append(("pillar inside storey rows 1..5", c0, r0))
        elif nm in DECOR_COB:
            ncob += 1
            ok_l = all(base[(r0 + k) * 32 + c0 - 1] == T_BRICK for k in range(3)) if c0 else False
            ok_r = all(base[(r0 + k) * 32 + c0 + 1] == T_BRICK for k in range(3)) if c0 < 31 else False
            above = base[(r0 - 1) * 32 + c0] if r0 else None
            if top != 0 or not (ok_l or ok_r) or (above is not None and not floorish(above)):
                errs.append(("cobweb outside a corner (row 0, brick column in rows 0..2, ceiling above)", c0, r0))
    if ncob > 2:
        errs.append(("more than 2 cobwebs", ncob))
    if npatch_cells > 6:
        errs.append(("more than 6 patch / pillar cells", npatch_cells))
    if need_patch and not npatch:
        errs.append(("no back-wall patch in the room (>= 1 guaranteed)",))
    n = len(al) // 4
    ents = [al[k:k + 4] for k in range(0, len(al), 4)]
    gl = [e for e in ents if e[2] >= 16]
    at = [e for e in ents if e[2] < 16]
    if len(gl) > 4 or len(at) > 8 or n > 12:
        errs.append(("anim budget", len(gl), len(at)))
    cells = {(e[0], e[1]) for e in ents}
    for e in ents:
        if e[0] > 31 or e[1] > 17:
            errs.append(("ANIM entry off the map", e))
            continue
        j = e[1] * 32 + e[0]
        if m[j] == base[j] or e[2] == 0:
            errs.append(("ANIM entry not on a decor cell", e))
        if e[2] >= 16 and not flags[m[j]] & ANIMF:
            errs.append(("glyph-swap entry on a non-TF_ANIM id", e))
        if e[2] >= 16 and (not flags[e[2]] & ANIMF or flags[e[2]] & SOLID):
            errs.append(("glyph-swap alternate id not a non-solid TF_ANIM id", e))
        if e[2] < 16 and e[2] not in (1, 2):
            errs.append(("attr-cycle kind not 1 / 2", e))
        if e[3] != (e[3] & 7):
            errs.append(("AL_PHASE not a 0..7 stagger", e))
    for j in ch:
        if flags[m[j]] & ANIMF and (j % 32, j // 32) not in cells:
            errs.append(("TF_ANIM decor cell missing from ANIM_LIST", j % 32, j // 32))
    # large animated objects: one lead glyph cell each (B3B-9 review: the old
    # 4-connected cluster count merged touching objects)
    lead = lead_ids(d)
    nlarge = sum(1 for e in gl if m[e[1] * 32 + e[0]] in lead)
    if nlarge > 2:
        errs.append(("more than 2 large animated objects", nlarge))
    if [e for e in gl if e[2] != T["T_DRIP2"]] and not nlarge:
        errs.append(("glyph-swap entries without a large object", gl[:2]))
    errs += drip_rules(m, base, flags, ents, d)
    sizes["anim"] += n
    sizes["large"] += nlarge
    return errs


def show_room(p, r):
    """room_show + present_full (bank 5, shadow, screen 2). -> (ok, T)."""
    return run_code(p, head() + [0x3E, r, 0xCD] + w16(S["room_show"]) + [0xCD] + w16(S["present_full"]))


def bank7(p, addr, n):
    p.z.cmd("set-memory-zone 0")
    try:
        return bytes(p.z.read_memory(7 * 16384 + addr - 0xC000, n))
    finally:
        p.z.cmd("set-memory-zone -1")


def snapshot(p):
    """ROOM_MAP + bank-5 screen + screen 2 + the shadow's rows 0-17."""
    sh = bank7(p, S["SHADOW_BITMAP"], 6144) + bank7(p, S["SHADOW_ATTR"], 32 * PLAY_ROWS)
    return (bytes(p.z.read_memory(S["ROOM_MAP"], 32 * PLAY_ROWS)), bytes(p.composed_frame()),
            bytes(p.frame()), sh)


# ---------------------------------------------------------------------------
# B3B-11 (W15): the panel engine. Expected text is rendered here from the
# font source (assets/gfx/fonts/font6x8.bin, 6-px pitch from x = 0).
# ---------------------------------------------------------------------------
FONT6 = open(os.path.join(os.path.dirname(HERE), "assets", "gfx", "fonts", "font6x8.bin"), "rb").read()
LOG_COLS = S["LOG_COLS"]


def text6(msg, x0=0, cols=LOG_COLS):
    """8 lines x cols bytes of msg drawn with the 6x8 font from pixel x0."""
    rows = [bytearray(cols) for _ in range(8)]
    for i, ch in enumerate(msg):
        g = FONT6[(ord(ch) - 32) * 8:(ord(ch) - 32) * 8 + 8]
        x = x0 + 6 * i
        for ln in range(8):
            for b in range(6):
                if g[ln] & (0x80 >> b):
                    px = x + b
                    rows[ln][px >> 3] |= 0x80 >> (px & 7)
    return [bytes(r) for r in rows]


def log_row(frame, row, c0=0, cols=LOG_COLS):
    """8 lines x cols bitmap bytes of char row `row` from col c0."""
    cells = [cell_bytes(frame, c, row) for c in range(c0, c0 + cols)]
    return [bytes(cells[c][ln] for c in range(cols)) for ln in range(8)]


def bar_bytes(fill):
    """Expected 4 bytes per pixel line of a 32-px bar (concept bar_cells):
    frame lines 1 / 6, end caps, the first `fill` px of lines 2..5."""
    full, caps = (1 << 32) - 1, (1 << 31) | 1
    fillb = ((1 << fill) - 1) << (32 - fill)
    rows = [0, full] + [fillb | caps] * 4 + [full, 0]
    return [r.to_bytes(4, "big") for r in rows]


def w15(p, check):
    # B3B-13: messages are token streams pushed by id (msg_push); the expected
    # text comes from src/strings.txt
    TXT = {"str_" + n: t for n, t in STRINGS if n in ("found", "locked", "fall", "died", "quaff")}
    MSG = {k: S["TX_" + k[4:].upper()] for k in TXT}
    WELCOME = dict(STRINGS)["welcome"]
    STUB = S["LOWRAM_END_3B"]

    def w(v):
        return [v & 0xFF, v >> 8]

    def stub(code, tag, measure=False):
        """Run code (DI ... EI) in place from the wait_tick probe; play resumes
        there (PC put back). -> T-states if measure."""
        pc0 = p.pc()
        if measure:
            p.z.cmd("reset-tstates-partial")
        ok = p.run_stub([0xF3] + code + [0xFB], org=STUB)
        t = int(p.z.cmd("get-tstates-partial")) if measure else 0
        check(f"W15 stub {tag} ran", ok, "")
        p.z.cmd("set-register PC=%d" % pc0)
        return t

    def push(*names):
        code = []
        for n in names:
            if n in TXT:                          # a string id: msg_push (B3B-13)
                code += [0x3E, MSG[n], 0xCD] + w(S["msg_push"])
            else:                                 # plain text in RAM: log_push
                code += [0x21] + w(MSG[n]) + [0xCD] + w(S["log_push"])
        stub(code, "push " + ",".join(names))

    def step(c):
        """panel_step with C = c (0: any item, as in a 1st-frame tick; else
        small items only, as in a 2nd-frame tick) -> T-states."""
        return stub([0x0E, c, 0xCD] + w(S["panel_step"]), f"panel_step c {c}", measure=True)

    def drained():
        return p.rb("LOG_QN") == 0 and not p.rb("PANEL_DIRTY")

    def hp_ok(fr):
        e = p.ent(0)
        num = "%2d" % e["HP"]
        f = round(32 * e["HP"] / e["MAXHP"])
        bar = [bytes(cell_bytes(fr, c, 21)[ln] for c in range(1, 5)) for ln in range(8)]
        return bar == bar_bytes(f) and log_row(fr, 21, 5, 2) == text6(num, 0, 2)

    # --- static panel at start ------------------------------------------
    p.boot(K_KNIGHT)
    p.isolate()
    fr = p.frame()
    check(f"W15 start: log row 23 = {WELCOME}, row 22 blank",
          (log_row(fr, 23), log_row(fr, 22)) == (text6(WELCOME), text6("")), "")
    check("W15 start: log attrs row 22 $07 / row 23 $47 (cols 0-23)",
          [attr_at(fr, c, 22) for c in range(24)] + [attr_at(fr, c, 23) for c in range(24)]
          == [S["ATTR_LOG_OLD"]] * 24 + [S["ATTR_LOG_NEW"]] * 24, "")
    check("W15 start: depth D1 at (30, 18)", log_row(fr, 18, 30, 2) == text6("D1", 0, 2), "")
    check("W15 start: HP bar + number == hero HP", hp_ok(fr), p.ent(0)["HP"])
    check("W15 start: queue empty, nothing dirty, nothing dropped",
          (p.rb("LOG_QN"), p.rb("PANEL_DIRTY"), p.rb(S["LOG_Q"] + S["LQ_DROP"])) == (0, 0, 0), "")

    # --- quaff: never in the input tick, <= 3 ticks after it --------------
    p.set_ent(0, HP=5)
    p.settle(2)                                   # HP 5 shown (poll: idle ticks)
    check("W15 HP poke reaches the panel within 2 idle ticks", hp_ok(p.composed_frame()), "")
    panel = lambda f: split_frame(f)[1]
    before = panel(p.composed_frame())
    tc0 = p.rw("TURN_COUNTER")
    p.hold("G")
    p.tick()
    p.release()
    in_input = p.rb("TURN_PHASE") == 1 or p.rw("TURN_COUNTER") != tc0
    check("W15 quaff: the turn started in this tick (HP healed)", in_input and p.ent(0)["HP"] > 5,
          (p.rb("TURN_PHASE"), p.ent(0)["HP"]))
    check("W15 quaff: panel untouched in the input tick (composed rows 18-23)",
          panel(p.composed_frame()) == before, "")
    want_log = text6(TXT["str_quaff"])
    seen = {}
    for k in range(1, 7):
        p.tick()
        fr, comp = p.frame(), p.composed_frame()
        if "log" not in seen and log_row(comp, 23) == want_log:
            seen["log"] = k
        if "hp" not in seen and hp_ok(comp):
            seen["hp"] = k
        if "pot" not in seen and log_row(comp, 19, 20, 1) == text6("0", 0, 1):
            seen["pot"] = k
        if "shown" not in seen and log_row(fr, 23) == want_log:
            seen["shown"] = k
    check("W15 quaff: HP, log line, potion count composed <= 3 ticks after the input tick",
          all(seen.get(k, 99) <= 3 for k in ("log", "hp", "pot")), seen)
    check("W15 quaff: the log line displayed one tick after it is composed",
          seen.get("shown", 99) == seen.get("log", 0) + 1, seen)
    check(f"W15 quaff: scroll: row 22 = the previous newest line ({WELCOME})",
          log_row(p.composed_frame(), 22) == text6(WELCOME), "")

    # --- 3 messages: 2-row scroll ----------------------------------------
    push("str_found", "str_locked", "str_fall")
    check("W15 3 pushes queued (LOG_QN 3, PD_LOG)", (p.rb("LOG_QN"), p.rb("PANEL_DIRTY") & S["PD_LOG"])
          == (3, S["PD_LOG"]), p.rb("LOG_QN"))
    n = 0
    while not drained() and n < 12:
        p.tick()
        n += 1
    p.tick()
    fr = p.frame()
    check("W15 3 messages drained in 1 idle tick (B3B-11b: items while in the 1st frame)", n == 1, n)
    check("W15 scroll after 3: row 22 = THE DOOR IS LOCKED, row 23 = YOU FALL INTO A PIT (displayed)",
          (log_row(fr, 22), log_row(fr, 23)) == (text6(TXT["str_locked"]), text6(TXT["str_fall"])), "")
    check("W15 displayed == composed after the drain", fr == p.composed_frame(), "")

    # --- 2nd-frame rule (B3B-11b): small items only, the log waits ----------
    push("str_died")
    p.set_ent(0, HP=6)
    t_hp2 = step(1)
    comp = p.composed_frame()
    check("W15 2nd frame: HP drawn, log item left queued (LOG_QN 1, PD_LOG)",
          (hp_ok(comp), p.rb("LOG_QN"), p.rb("PANEL_DIRTY") & S["PD_LOG"]) == (True, 1, S["PD_LOG"]),
          (p.rb("LOG_QN"), p.rb("PANEL_DIRTY")))
    t_none = step(1)
    check("W15 2nd frame: a waiting log item alone is not drawn (row 23 = old line)",
          (log_row(p.composed_frame(), 23), p.rb("LOG_QN")) == (text6(TXT["str_fall"]), 1), "")
    step(0)
    check("W15 1st frame: the whole line in one item, queue empty",
          (log_row(p.composed_frame(), 22), log_row(p.composed_frame(), 23), p.rb("LOG_QN"),
           p.rb("PANEL_DIRTY") & S["PD_LOG"]) == (text6(TXT["str_fall"]), text6(TXT["str_died"]), 0, 0), "")
    p.tick(2)
    check("W15 displayed == composed", p.frame() == p.composed_frame(), "")

    # --- GS_DEAD / GS_WIN lines are never dropped (log_push_end) -------------
    push("str_found", "str_locked", "str_fall", "str_quaff")
    stub([0x3E, MSG["str_died"], 0xCD] + w(S["msg_push_end"]), "msg_push_end")
    check("W15 ring full: log_push_end replaces the newest pending (LOG_QN 4, LQ_DROP 1)",
          (p.rb("LOG_QN"), p.rb(S["LOG_Q"] + S["LQ_DROP"])) == (4, 1), "")
    p.until(drained, 12)
    p.tick()
    check("W15 log_push_end: newest shown = YOU DIED (after THE FALL line)",
          (log_row(p.frame(), 22), log_row(p.frame(), 23)) == (text6(TXT["str_fall"]), text6(TXT["str_died"])), "")
    p.wb(S["LOG_Q"] + S["LQ_DROP"], 0)

    # --- ring overflow -----------------------------------------------------
    push("str_found", "str_locked", "str_fall", "str_quaff", "str_died")
    check("W15 ring full: 5th push (log_push) dropped (LOG_QN 4, LQ_DROP 1)",
          (p.rb("LOG_QN"), p.rb(S["LOG_Q"] + S["LQ_DROP"])) == (4, 1), "")
    p.until(drained, 12)
    p.tick()
    check("W15 overflow drained: newest shown = the 4th push (YOU DRINK A POTION)",
          log_row(p.frame(), 23) == text6(TXT["str_quaff"]), "")

    # --- costs: whole log item (scroll + 32 chars), print6 per char ----------
    long32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"
    p.z.cmd("write-memory %d %s" % (STUB + 0x100, " ".join(str(ord(c)) for c in long32 + "\0")))
    MSG["long"] = STUB + 0x100
    push("long")
    t_whole = step(0)
    check("W15 32-char line drawn whole", log_row(p.composed_frame(), 23) == text6(long32), "")
    t_s = stub([0xCD] + w(S["log_scroll"]), "log_scroll", measure=True)
    pr = lambda n: stub([0x21] + w(MSG["long"] + 32 - n) + [0x06, 23, 0x1E, 0, 0xCD] + w(S["print6"]),
                        f"print6 {n}", measure=True)
    t_p = pr(32)
    check("W15 print6 32 chars (direct) == the font", log_row(p.composed_frame(), 23) == text6(long32), "")
    t_p4 = pr(4)
    row23 = S["SCREEN_BITMAP"] + ((23 & 0x18) << 8) + ((23 & 7) << 5)

    def clear23():
        """row 23 bitmap -> 0, marked whole for present (EXT / PW 23 = 24)."""
        for ln in range(8):
            p.z.cmd("write-memory %d %s" % (row23 + ln * 256, " ".join(["0"] * 32)))
        p.wb(S["HUD4_EXT"] + 3, LOG_COLS)
        p.wb(S["HUD4_PW"] + 3, LOG_COLS)
        p.wb("PRES_ANY", 1)
    # odd-length tails and an x > 0 start: exact bytes, neighbours untouched
    for n, x in ((1, 8), (2, 16), (3, 0), (5, 40), (7, 64)):
        txt = long32[:n]
        p.z.cmd("write-memory %d %s" % (STUB + 0x140, " ".join(str(ord(c)) for c in txt + "\0")))
        clear23()
        # sentinel ink on row 23 after the run's last byte
        nb = (6 * n + 7) // 8
        sent = row23 + x // 8 + nb
        for ln in range(8):
            p.wb(sent + ln * 256, 0xA5)
        ex = stub([0x21] + w(STUB + 0x140) + [0x06, 23, 0x1E, x, 0xCD] + w(S["print6"],) + [0x7B, 0x32] + w(STUB + 0x13F),
                  f"print6 tail {n}")
        got = log_row(p.composed_frame(), 23)
        want = text6(txt, x)
        ok = all(got[ln][:x // 8 + nb] == want[ln][:x // 8 + nb] and got[ln][x // 8 + nb] == 0xA5 for ln in range(8))
        check(f"W15 print6 {n} chars at x {x}: exact bytes, next byte untouched, E out = x + 6n",
              ok and p.rb(STUB + 0x13F) == x + 6 * n, (n, x, p.rb(STUB + 0x13F)))
    clear23()
    p.tick(2)
    print(f"[info] W15 measured (contended, ZEsarUX): whole log item scroll + 32 chars {t_whole} T;"
          f" scroll of 24 cols {t_s} T; print6 32 chars {t_p} T (~{t_p // 32} T/char), 4 chars {t_p4} T;"
          f" 2nd-frame HP item {t_hp2} T, idle step {t_none} T", flush=True)
    check("W15 whole log item <= 25k T (1st-frame ticks only: < 70.9k T used before it)", t_whole <= 25000, t_whole)
    check("W15 2nd-frame small item (HP) <= 5k T (worst 2nd-frame pre-panel ~117k + 5k < 126k cap)", t_hp2 <= 5000, t_hp2)
    check("W15 print6 <= 500 T/char (32 chars)", t_p <= 500 * 32, t_p)

    # --- bars follow HP ------------------------------------------------------
    for hp in (1, 7, 13, 22):
        p.set_ent(0, HP=hp)
        p.tick(2)
        check(f"W15 HP {hp}: bar fill round(32 hp / max) + number (displayed)", hp_ok(p.frame()), hp)

    # --- the Mage's panel golden --------------------------------------------
    p.boot(K_WIZARD)
    n0 = len(p.h.failures)
    game.golden(p.h, "w15_panel_mage", p.frame())
    check("W15 golden w15_panel_mage (the Mage's start screen: play + panel hashes)",
          len(p.h.failures) == n0, p.h.failures[n0:])


def w17(p, check):
    """B3B-13: the token text. (a) tk_get decodes every string of
    src/strings.txt into a buffer == its text (exact bytes, 0-terminated), +
    the decode cost vs a plain-fetch getter over the same text; (b) every
    string pushed by id (msg_push) and drawn by the real item_log (print6t)
    == the reference 6x8 render of its text on row 23, $C000 handed back, T
    per item; (c) composed impact lines (show_impact_msg, all 5 kinds x the
    monster names) drawn == their text."""
    STUB = S["LOWRAM_END_3B"]
    w = w16
    texts = [t for _, t in STRINGS]
    n_chars = sum(len(t) for t in texts)

    def stub(code, tag, measure=False):
        pc0 = p.pc()
        if measure:
            p.z.cmd("reset-tstates-partial")
        ok = p.run_stub([0xF3] + code + [0xFB], org=STUB)
        t = int(p.z.cmd("get-tstates-partial")) if measure else 0
        check(f"W17 stub {tag} ran", ok, "")
        p.z.cmd("set-register PC=%d" % pc0)
        return t

    def asm(items):
        """tiny assembler: ints = bytes, ('L', name) = label, ('jr', cc, name)
        = relative jump (cc opcode)."""
        out, labels, fix = [], {}, []
        for it in items:
            if isinstance(it, int):
                out.append(it)
            elif it[0] == "L":
                labels[it[1]] = len(out)
            else:
                out += [it[1], 0]
                fix.append((len(out) - 1, it[2]))
        for at, nm in fix:
            out[at] = (labels[nm] - (at + 1)) & 0xFF
        return out

    p.boot(K_KNIGHT)
    p.isolate()
    p.settle(2)
    # --- (a) decode every string into a buffer --------------------------------
    BUF, GET = STUB + 0x100, STUB + 0xF0
    plain_get = [0x0A, 0x03, 0xB7, 0xC9]          # ld a,(bc) / inc bc / or a / ret
    p.z.cmd("write-memory %d %s" % (GET, " ".join(map(str, plain_get))))

    def decode_loop(getter, plain):
        return asm([0x3A] + w(S["PORT_7FFD_SHADOW"]) + [0xF5,               # ld a,(shadow) / push af
                    0x3E, S["BANK_TEXT"], 0xCD] + w(S["page_bank"]) +
                   [0x11] + w(BUF + (0x200 if plain else 0)) +             # ld de, out
                   ([0x01] + w(BUF) if plain else []) +                     # plain: BC walks BUF
                   [0xAF, ("L", "lp"), 0xF5, 0xCD] + w(S["tx_ptr"]) +       # xor a / push af / call tx_ptr
                   ([0x00, 0x00] if plain else [0x44, 0x4D]) +              # (nop nop) / ld b,h / ld c,l
                   [("L", "in"), 0xCD] + w(getter) + [0x12, 0x13, 0xB7, ("jr", 0x20, "in"),
                    0xF1, 0x3C, 0xFE, S["TX_COUNT"], ("jr", 0x38, "lp"),
                    0xF1, 0xCD] + w(S["restore_page"]))
    sh0 = p.rb("PORT_7FFD_SHADOW")
    t_tk = stub(decode_loop(S["tk_get"], False), "tk_get decode loop", measure=True)
    got = bytes(p.z.read_memory(BUF, n_chars + len(texts)))
    want = b"".join(t.encode() + b"\0" for t in texts)
    check(f"W17 tk_get: all {len(texts)} strings decode bit-exact (0-terminated, in id order)",
          got == want, [(i, a, b) for i, (a, b) in enumerate(zip(got, want)) if a != b][:4])
    check("W17 tk_get: decoded chars are 32..127 only",
          all(c == 0 or 32 <= c <= 127 for c in got), "")
    check("W17 decode loop: the caller's $C000 bank handed back", p.rb("PORT_7FFD_SHADOW") == sh0,
          (sh0, p.rb("PORT_7FFD_SHADOW")))
    t_pl = stub(decode_loop(GET, True), "plain getter loop", measure=True)
    check("W17 plain-getter loop re-reads the same text", bytes(p.z.read_memory(BUF + 0x200, len(want))) == want, "")
    per = (t_tk - t_pl) / n_chars
    # --- (b) every string through msg_push + item_log (print6t) ---------------
    row_ok, worst, sh_bad = [], (0, ""), []
    for sid, (nm, txt) in enumerate(STRINGS):
        sh0 = p.rb("PORT_7FFD_SHADOW")
        t = stub([0x3E, sid, 0xCD] + w(S["msg_push"]) + [0x21] + w(S["PANEL_DIRTY"]) +
                 [0xCD] + w(S["item_log"]), f"msg_push + item_log {nm}", measure=True)
        if p.rb("PORT_7FFD_SHADOW") != sh0:
            sh_bad.append(nm)
        if log_row(p.composed_frame(), 23) != text6(txt):
            row_ok.append(nm)
        if t > worst[0]:
            worst = (t, nm)
    check(f"W17 every string ({len(STRINGS)}) drawn by item_log == the reference render of its text",
          row_ok == [], row_ok)
    check("W17 msg_push + item_log hand the caller's $C000 bank back", sh_bad == [], sh_bad)
    check("W17 log queue drained (LOG_QN 0, nothing dropped)",
          (p.rb("LOG_QN"), p.rb(S["LOG_Q"] + S["LQ_DROP"])) == (0, 0), "")
    check("W17 worst push + log item <= 25k T", worst[0] <= 25000, worst)
    # --- (c) composed impact lines ------------------------------------------
    T_ = dict(STRINGS)
    names = {k: T_["nm_" + k] for k in ("skeleton", "goblin", "ghost", "rat", "bat", "slime")}
    pre = {1: T_["you_hit"], 2: T_["you_miss"], 3: T_["you_kill"], 4: T_["the"], 5: T_["the"]}
    post = {1: "", 2: "", 3: "", 4: T_["hits_you"], 5: T_["misses"]}
    ent = lambda sl, k: S["P_ENTITIES"] + sl * 32 + S[k]
    bad, t_imp = [], 0
    for kn, nmtxt in names.items():
        kind = S["K_" + kn.upper()]
        for m in (1, 2, 3, 4, 5):
            p.wb(ent(1, "E_KIND"), kind)
            if m < 4:
                p.wb(ent(0, "E_MSG"), m)
                p.wb(ent(0, "E_TGT"), 1)
                slot = 0
            else:
                p.wb(ent(1, "E_MSG"), m)
                slot = 1
            ix = S["P_ENTITIES"] + slot * 32
            t = stub([0xDD, 0x21] + w(ix) + [0xCD] + w(S["show_impact_msg"]) + [0x21] + w(S["PANEL_DIRTY"]) +
                     [0xCD] + w(S["item_log"]), f"impact {kn} {m}", measure=True)
            t_imp = max(t_imp, t)
            exp = pre[m] + nmtxt + post[m]
            if log_row(p.composed_frame(), 23) != text6(exp):
                bad.append((kn, m, exp))
    p.wb(ent(0, "E_MSG"), 0)
    p.wb(ent(1, "E_MSG"), 0)
    check("W17 composed impact lines (5 kinds x 6 monsters) drawn == text", bad == [], bad[:4])
    print(f"[info] W17 measured (contended, ZEsarUX): tk_get decode loop {t_tk} T vs plain getter {t_pl} T"
          f" over {n_chars} chars -> decode +{per:.1f} T/char (vs a called plain fetch);"
          f" worst msg_push + log item {worst[0]} T ({worst[1]}); worst impact compose + item {t_imp} T",
          flush=True)
    p.tick(2)


# ---------------------------------------------------------------------------
# B3B-10 (W14): decor_tick. The PROTO level is turned into a depth-1 level with
# seeded rooms A and B (LVL_DEPTH 1 + RD_SEED, D1 tileset), A rebuilt in place
# (room_show + present_full from the wait_tick probe), then played.
# ---------------------------------------------------------------------------
def dt_sim(ents, rmap, covered, tab):
    """Model of one decor_tick (written from the B3B-10 contract, src/decor.asm
    header): every AL_PHASE += 1; due when & 3 == 0 (glyph swaps: & 15 == 0); per tick caps 1 glyph /
    2 attr steps and 3 occupancy tries; a due entry past a cap waits a tick
    (phase - 1), a tried entry under a sprite skips the step (cell holds); a
    glyph swap exchanges the map id with AL_TYPE. -> {entry index: attr shown}."""
    caps = {"g": S["DT_MAX_GLYPH"], "a": S["DT_MAX_ATTR"], "t": S["DT_MAX_TRIES"]}
    shown = {}
    for k, e in enumerate(ents):
        e[3] = (e[3] + 1) & 255
        if e[3] & S["DT_STEP_MASK"]:
            continue
        kind = "g" if e[2] >= S["AL_GLYPH_MIN"] else "a"
        if kind == "g" and e[3] & (S["DT_GLYPH_HOLD"] - 1):
            continue                              # drips hold 16 ticks
        if caps[kind] == 0 or caps["t"] == 0:
            e[3] = (e[3] - 1) & 255
            continue
        caps["t"] -= 1
        if covered(e[0], e[1]):
            continue
        caps[kind] -= 1
        if kind == "g":
            j = e[1] * 32 + e[0]
            rmap[j], e[2] = e[2], rmap[j]
            shown[k] = None                       # = TILE_ATTRS[new id]
        else:
            shown[k] = tab[(e[2] - 1) * 8 + ((e[3] >> 2) & 7)]
    return shown


def shadow_frame(p):
    """The bank-7 clean-background shadow in frame_bytes() layout (rows 0-17;
    rows 18-23 of the bitmap / attrs are not part of it)."""
    bm = bank7(p, S["SHADOW_BITMAP"], 6144)
    at = bank7(p, S["SHADOW_ATTR"], 32 * PLAY_ROWS)
    return bm + at + bytes(768 - len(at))


def w14(p, check):
    BASE = room_model.BASE
    T = room_model.T
    kw, kh = game.body(p, K_KNIGHT)
    y1 = stand_y(1, kh)
    p.boot(K_KNIGHT)
    p.isolate()
    blk = bytearray(room_model.read_block(p))
    blk[S["LVL_DEPTH"] - BASE] = 1
    so = lambda r: room_model.OFF_DESC + r * S["RD_STRIDE"] + S["RD_SEED"]
    hero0 = p.ent(0)
    hbox = {(c, r) for c in range(hero0["DCOL"], hero0["DCOL"] + hero0["DCOLS"])
            for r in range(hero0["DROW"], hero0["DROW"] + hero0["DROWS"])}

    def pick(r, cond):
        for sd in range(1, 6000):
            b = bytearray(blk)
            b[so(r)], b[so(r) + 1] = sd & 255, sd >> 8
            al = []
            room_model.render_room(bytes(b), r, anim=al)
            ents = [al[k:k + 4] for k in range(0, len(al), 4)]
            if cond(ents):
                return sd, al
        raise RuntimeError("W14: no seed for room %d" % r)
    sa, ala = pick(ROOM_A, lambda e: sum(x[2] >= 16 for x in e) >= 2 and sum(x[2] < 16 for x in e) >= 3
                   and not any((x[0], x[1]) in hbox for x in e) and len(e) <= 7)   # D1: a short list, so the round robin visits the injected entry every tick
    sb, alb = pick(ROOM_B, lambda e: len(e) >= 2)
    blk[so(ROOM_A)], blk[so(ROOM_A) + 1] = sa & 255, sa >> 8
    blk[so(ROOM_B)], blk[so(ROOM_B) + 1] = sb & 255, sb >> 8
    p.z.cmd("write-memory %d %s" % (BASE, " ".join(str(b) for b in blk)))
    pc0 = p.pc()
    ok = p.run_stub([0x3E, 1, 0xCD] + w16(S["level_load_tiles"])
                    + [0x3E, ROOM_A, 0xCD] + w16(S["room_show"]) + [0xCD] + w16(S["present_full"]),
                    org=S["LOWRAM_END_3B"])
    p.z.cmd("set-register PC=%d" % pc0)
    n = p.rb("ANIM_N")
    got = list(p.z.read_memory(S["ANIM_LIST"], 4 * n)) if n else []
    p.set_ent(0, DVIS=0)                          # room_show painted over the hero: redraw it
    want_ma = room_model.render_room(bytes(blk), ROOM_A)
    check(f"W14 room A seeded (D1, seed {sa:#06x}): rebuilt, ROOM_MAP == model, ANIM_LIST == decorgen "
          f"({len(ala) // 4} entries)",
          ok and got == ala and list(p.z.read_memory(S["ROOM_MAP"], 576)) == want_ma, (ok, n, got, ala))
    p.settle(3)
    # ---- N ticks against the model (dt_sim), every tick ------------------
    tab = list(p.z.read_memory(S["dt_attr_tab"], 16))
    check("W14 attr tables: flame cycles $46/$42/$06 only, candle the same inks",
          set(tab[:8]) == {0x46, 0x42, 0x06} and set(tab[8:]) <= {0x46, 0x42, 0x06}, tab)
    ents = [list(p.z.read_memory(S["ANIM_LIST"] + 4 * k, 4)) for k in range(n)]
    rmap = list(p.z.read_memory(S["ROOM_MAP"], 576))
    glyphs = p.z.read_memory(S["TILE_GLYPHS"], 512)
    attrs = p.z.read_memory(S["TILE_ATTRS"], 64)
    comp0 = p.composed_frame()
    shown = {k: attr_at(comp0, e[0], e[1]) for k, e in enumerate(ents)}
    cov = set()
    for s_ in range(16):
        e = p.ent(s_)
        if e["DVIS"] & 1:
            cov |= {(c, r) for c in range(e["DCOL"], e["DCOL"] + e["DCOLS"])
                    for r in range(e["DROW"], e["DROW"] + e["DROWS"])}
    bad, steps, seen = [], [0] * n, [set() for _ in range(n)]
    p.present_watch(True)
    for t in range(40):
        st_ = dt_sim(ents, rmap, lambda c, r: (c, r) in cov, tab)
        p.tick()
        for k, v in st_.items():
            steps[k] += 1
            shown[k] = attrs[rmap[ents[k][1] * 32 + ents[k][0]]] if v is None else v
        zl = [list(p.z.read_memory(S["ANIM_LIST"] + 4 * k, 4)) for k in range(n)]
        zm = list(p.z.read_memory(S["ROOM_MAP"], 576))
        comp = p.composed_frame()
        shf = shadow_frame(p)
        if zl != ents or zm != rmap:
            bad.append((t, "list / map != model", zl, ents))
        for k, e in enumerate(ents):
            c, r = e[0], e[1]
            g = bytes(glyphs[rmap[r * 32 + c] * 8:rmap[r * 32 + c] * 8 + 8])
            seen[k].add((attr_at(comp, c, r), bytes(cell_bytes(comp, c, r))))
            if attr_at(comp, c, r) != shown[k] or bytes(cell_bytes(comp, c, r)) != g:
                bad.append((t, "cell", c, r, hex(attr_at(comp, c, r)), hex(shown[k])))
            if attr_at(shf, c, r) != attr_at(comp, c, r) or cell_bytes(shf, c, r) != cell_bytes(comp, c, r):
                bad.append((t, "shadow != screen", c, r))
    p.present_watch(False)
    check("W14 40 ticks: ANIM_LIST + ROOM_MAP == the decor_tick model every tick, each cell shows "
          "its cycle attr / swapped glyph on bank 5 and the shadow", not bad, bad[:3])
    check("W14 in 40 ticks attr entries stepped 8-10 times (period 4; a capped step waits a tick), "
          "drips 2-3 times (hold 16), attr cells took >= 2 attrs, glyph cells both frames",
          all((x in (2, 3)) if ents[k][2] >= 16 else (x in (8, 9, 10)) for k, x in enumerate(steps)) and all(len(x) >= 2 for x in seen), (steps, [len(x) for x in seen]))
    ps = p.present_samples
    check("W14 displayed == composed at every tick-start present (probe_presented)",
          ps and not any(ps), (len(ps), [x for x in ps if x][:4]))
    sm = shadow_frame(p)
    tabs = p.bg_tables()
    acells = {(e[0], e[1]) for e in ents if e[2] < 16}
    sbad = []
    for r in range(PLAY_ROWS):
        for c in range(32):
            g, a = room_model.expected_cell(*tabs, c, r)
            if bytes(cell_bytes(sm, c, r)) != g or ((c, r) not in acells and attr_at(sm, c, r) != a):
                sbad.append((c, r))
    check("W14 shadow == ROOM_MAP after animation (glyphs everywhere; attrs except the cycling cells)",
          not sbad, sbad[:4])
    # ---- a cell under a sprite holds -------------------------------------
    h = p.ent(0)
    hc, hr = h["DCOL"] + 1, h["DROW"] + 1
    k = min(n, S["ANIM_MAX"] - 1)
    p.z.cmd("write-memory %d %d %d 1 3" % (S["ANIM_LIST"] + 4 * k, hc, hr))
    p.wb("ANIM_N", k + 1)
    a0 = attr_at(p.composed_frame(), hc, hr)
    g0 = bytes(cell_bytes(p.composed_frame(), hc, hr))
    held = []
    for _ in range(9):
        p.tick()
        f = p.composed_frame()
        held.append((p.rb(S["ANIM_LIST"] + 4 * k + 3), attr_at(f, hc, hr), bytes(cell_bytes(f, hc, hr)) == g0))
    check("W14 a cell under the hero holds: its due steps (phases 4, 8) are skipped, the hero's "
          "attr / pixels stay", [x[0] for x in held] == list(range(4, 13))
          and all(x[1:] == (a0, True) for x in held), held)
    p.place(0, h["X"] + 6, h["Y"])
    p.tick(4)
    ph = p.rb(S["ANIM_LIST"] + 4 * k + 3)
    want_a = tab[(ph >> 2) & 7]
    check("W14 ... and steps once the hero has left (attr = the flame cycle at its phase)",
          attr_at(p.composed_frame(), hc, hr) == want_a, (ph, hex(attr_at(p.composed_frame(), hc, hr))))
    p.wb("ANIM_N", n)
    # ---- decor_tick cost (idle room A, budget.Stepper) ---------------------
    import budget
    stp = budget.Stepper(p)
    for _ in range(24):
        stp.tick()
    stp.close()
    dts = [sp.get("decor_tick", 0) for _, sp in stp.ticks]
    print(f"[info] W14 decor_tick ({n} entries, hero only): max {max(dts)} T, mean {sum(dts) // len(dts)} T", flush=True)
    check("W14 decor_tick: mean <= 2.5k T per tick, every tick <= 4k (budget.md 6; idle room, real D1 decor)",
          sum(dts) <= 2500 * len(dts) and max(dts) <= 4000, dts)
    # ---- room change by scroll: ANIM_LIST follows (B3B-9 review fix) -------
    p.place(0, 32 - 1 - kw, y1)
    p.turn("L")
    p.until(lambda: p.rb("CUR_ROOM") == ROOM_B and p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
    nb = p.rb("ANIM_N")
    gb = list(p.z.read_memory(S["ANIM_LIST"], 4 * nb)) if nb else []
    gb0 = [gb[i] if i % 4 != 3 else 0 for i in range(len(gb))]
    alb0 = [alb[i] if i % 4 != 3 else 0 for i in range(len(alb))]
    check(f"W14 after the scroll A -> B: ANIM_LIST == room B's (seed {sb:#06x}, {len(alb) // 4} entries; "
          f"A had {len(ala) // 4}): cols / rows match",
          nb == len(alb) // 4 and alb != ala and all(
              gb[i] == alb[i] for i in range(len(alb)) if i % 4 in (0, 1)), (nb, gb, alb))
    mb = list(p.z.read_memory(S["ROOM_MAP"], 576))
    want_mb = room_model.render_room(bytes(blk), ROOM_B)
    # the map differs from the build only at glyph-swap cells (swapped with their entry)
    sw = {(gb[i], gb[i + 1]): gb[i + 2] for i in range(0, len(gb), 4) if gb[i + 2] >= 16}
    mbad = [(j % 32, j // 32) for j in range(576)
            if mb[j] != want_mb[j] and not ((j % 32, j // 32) in sw and sw[(j % 32, j // 32)] == want_mb[j])]
    check("W14 room B: ROOM_MAP == model (glyph cells possibly swapped with their entry)", not mbad, mbad[:4])
    p.present_watch(True)
    ph0 = [gb[i + 3] for i in range(0, len(gb), 4)]
    p.tick(16)
    p.present_watch(False)
    gb2 = list(p.z.read_memory(S["ANIM_LIST"], 4 * nb))
    ph1 = [gb2[i + 3] for i in range(0, len(gb2), 4)]
    hb = p.ent(0)
    hbx = {(c, r) for c in range(hb["DCOL"], hb["DCOL"] + hb["DCOLS"])
           for r in range(hb["DROW"], hb["DROW"] + hb["DROWS"])}
    check("W14 room B animates (every phase not under the hero advanced) and displayed == composed "
          "at every present",
          all(((b - a) & 255) >= 12 or (gb2[4 * i], gb2[4 * i + 1]) in hbx
              for i, (a, b) in enumerate(zip(ph0, ph1))) and not any(p.present_samples),
          (ph0, ph1, [x for x in p.present_samples if x][:4]))
    comp = p.composed_frame()
    sm = shadow_frame(p)
    tabs = p.bg_tables()
    acells = {(gb2[i], gb2[i + 1]) for i in range(0, len(gb2), 4) if gb2[i + 2] < 16}
    sbad = []
    for r in range(PLAY_ROWS):
        for c in range(32):
            g, a = room_model.expected_cell(*tabs, c, r)
            if bytes(cell_bytes(sm, c, r)) != g or (attr_at(sm, c, r) != (attr_at(comp, c, r) if (c, r) in acells else a)):
                sbad.append((c, r))
    check("W14 room B: shadow == ROOM_MAP (attr-cycle cells == the screen's attr)", not sbad, sbad[:4])
    p.load()


def present_rooms(blk):
    return [r for r in range(9) if room_model.field(blk, r, "RD_FLAGS") & S["RDF_PRESENT"]]


def wall_decor_ids(d):
    """Tile ids of the brick-class decor (D1: only the pillar goes on T_BRICK cells, so also
    on block cells; back-wall patches moved to T_AIR) of depth d."""
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
    import decorgen as DG
    ids = set()
    for name, base, w, h, fl, cls in DG.COMMON + DG.LEVEL[d]:
        if cls == DG.C_BRICK:
            ids |= set(range(base, base + w * h))
    return ids


def invariants(blk, r, m, d):
    """W12M (review B3B-8): order-free checks on an engine map, from the
    descriptor alone (room_model applies features in the Z80's order, so an
    ordering bug would match there): footprints never overlap, ladder / hole
    cells exactly on the segments, block cells all wall (B3B-9: or wall-class
    decor of depth d, which the deriver puts on T_BRICK cells), end caps only beside a
    row-8 hole or at p-1 / p+3, door tiles only in cols 0-1 / 30-31 of a door's
    exit storey, row 17 only floor / hole / grate (ornament never on a hole)."""
    T = room_model.T
    F0, F1, SR, SA = S["FLOOR_ROW0"], S["FLOOR_ROW1"], STOREY_ROWS, STOREY_AIR
    fld = lambda k: room_model.field(blk, r, k)
    bad = []
    lad = {}                                   # (c, row) -> segment
    for col, st in room_model.segments(blk, r):
        for row in range(SR * st - 1, SR * st + SA):
            if 0 <= row < PLAY_ROWS:
                for k in range(3):
                    lad[(col + k, row)] = (col, st)
    pit = set()
    p_ = fld("RD_PITCOL")
    if p_:
        pit = {(c, F0) for c in range(p_ - 1, p_ + 4)}
    door = set()
    ex = fld("RD_EXITS")
    for side, bit, sbit, c0 in (("L", "RDX_L", "RDX_LS1", 0), ("R", "RDX_R", "RDX_RS1", 30)):
        if ex & S[bit] and blk[room_model.OFF_EDGE + room_model.edge_index(r, side)] & S["EG_DOOR"]:
            st = 1 if ex & S[sbit] else 0
            door |= {(c, row) for c in (c0, c0 + 1) for row in range(SR * st, SR * st + SA)}
    blkc = set()
    b = fld("RD_BLOCK")
    w = b & S["RDB_WMASK"]
    if w:
        st = 1 if b & S["RDB_S1"] else 0
        cols = range(32 - w, 32) if b & S["RDB_RIGHT"] else range(w)
        blkc = {(c, row) for c in cols for row in range(SR * st, SR * st + SA + 1)}
    for a_, b_, n in ((blkc, door, "block/door"), (blkc, set(lad), "block/ladder"), (blkc, pit, "block/pit"),
                      (pit, set(lad), "pit/ladder"), (door, set(lad), "door/ladder")):
        if a_ & b_:
            bad.append(("overlap " + n, sorted(a_ & b_)[:2]))
    ladder_ids = {T[k] for k in ("T_LAD_L", "T_LAD_M", "T_LAD_R", "T_HOLE_L", "T_HOLE_M", "T_HOLE_R")}
    door_ids = {T[k] for k in ("T_DOOR_ARCH_L", "T_DOOR_ARCH_R", "T_DOOR_L", "T_DOOR_R", "T_DOOR_LOCK",
                               "T_DOOR_JAMB_L", "T_DOOR_JAMB_R")}
    grate_open = blk[S["LVL_FLAGS"] - S["LVL_STATE"]] & S["LF_GRATE_OPEN"]
    xc = fld("RD_EXITCOL")
    holes8 = {c for (c, row) in lad if row == F0}
    wall_ok = {T["T_BRICK"], T["T_WALLF"]} | wall_decor_ids(d)
    for row in range(PLAY_ROWS):
        for c in range(32):
            t = m[row * 32 + c]
            on_lad = (c, row) in lad
            if xc and row == F1 and xc <= c < xc + 3:
                on_lad = False                 # under the gate: raised (open, B12) / closed
                if t != (T["T_GRATE"] if grate_open else T["T_GRATE_SHUT"]):
                    bad.append(("grate", c, row, t))
            if t == T["T_GRATE"] and not (xc and row == F1 and xc <= c < xc + 3):
                bad.append(("gate tile off the level exit", c, row, t))
            if d and t == room_model.glow_id(d) and not (
                    xc and grate_open and row == F1 - 1 and c == xc + 1):
                bad.append(("glow off the exit's middle cell", c, row, t))
            if row == 0 and fld("RD_ARRCOL") and fld("RD_ARRCOL") <= c < fld("RD_ARRCOL") + 3:
                on_lad = False                 # the arrival shaft's rubble cap
            if (t in ladder_ids) != on_lad:
                bad.append(("ladder cell", c, row, t))
            if (c, row) in blkc and t not in wall_ok:
                bad.append(("block cell", c, row, t))
            if t in door_ids and (c, row) not in door:
                bad.append(("door tile", c, row, t))
            if t in (T["T_END_L"], T["T_END_R"]):
                ok = row == F0 and ((t == T["T_PIT_L"] and c == p_ - 1) or (t == T["T_PIT_R"] and c == p_ + 3)
                                    or (t == T["T_END_R"] and c + 1 in holes8)
                                    or (t == T["T_END_L"] and c - 1 in holes8))
                if not ok:
                    bad.append(("cap", c, row, t))
            if row == F1 and t not in ladder_ids | {T["T_PLAT"], T["T_WALLF"], T["T_GRATE"]}:
                bad.append(("row 17", c, row, t))
            if row == F1 and t in (T["T_PLAT"], T["T_WALLF"]) and on_lad:
                bad.append(("ornament over a hole", c, row, t))
    return bad


def run_gen_suites(p, check):
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
    import levelgen as G
    from game_lib import SNA_RAM
    T = room_model.T
    worst = {}

    def note(k, v, tag):
        if v > worst.get(k, (0, ""))[0]:
            worst[k] = (v, tag)

    p.boot(K_KNIGHT)
    # ---------------- W11: per-depth theme + floor-row legality ------------
    if want("W11"):
        for d in range(1, 9):
            seed = (0x2B3B * d) & 0xFFFF
            ok, tg, tt, blk = gen_level(p, d, seed, master=d)
            check(f"W11 D{d}: level_gen + level_load_tiles ran, block == levelgen.py",
                  ok and blk == G.generate(d, seed, d), (ok, d, seed))
            note("level_load_tiles", tt, f"D{d}")
            fl, wl = room_model.THEME[d]
            attrs = p.z.read_memory(S["TILE_ATTRS"], S["TILE_IDS"])
            glyphs = p.z.read_memory(S["TILE_GLYPHS"], S["TILE_IDS"] * 8)
            flags = p.z.read_memory(S["tile_flags"], S["TILE_IDS"])
            check(f"W11 D{d}: floor ids attr == ATTR_FLOOR {fl:#04x}, wall ids == ATTR_WALL {wl:#04x}",
                  all(attrs[T[k]] == fl for k in room_model.FLOOR_IDS)
                  and all(attrs[T[k]] == wl for k in room_model.WALL_IDS),
                  [hex(attrs[T[k]]) for k in room_model.FLOOR_IDS + room_model.WALL_IDS])
            slot = d - 1
            so = 7 * 16384 + (S["TSET_LO"] if slot < 4 else S["TSET_HI"]) - 0xC000 + (slot & 3) * S["TSET_STRIDE"]
            sl = SNA_RAM[so:so + S["TSET_STRIDE"]]
            check(f"W11 D{d}: ids 32..63 glyphs / attrs / TILE_FLAGS == the bank-7 slot {slot}",
                  (bytes(glyphs[256:]), bytes(attrs[32:]), bytes(flags[32:]))
                  == (sl[:256], sl[256:288], sl[288:320]), "")
            floor_cls = {T[k] for k in ("T_PLAT", "T_WALLF", "T_END_L", "T_END_R", "T_HOLE_L",
                                        "T_HOLE_M", "T_HOLE_R", "T_GRATE", "T_AIR")}
            legal = {fl, wl, S["ATTR_AIR"], S["ATTR_LADDER"], S["ATTR_DOOR"], S["ATTR_GRATE"],
                     S["ATTR_POTION"]}
            # B3B-9 decor: the level's own decor ids + the common small decor
            legal |= {attrs[i] for i in range(S["T_LVL_BASE"], S["T_LVL_OBJ"])}
            legal |= {attrs[T[k]] for k in ("T_CHAIN", "T_SKULLS", "T_TORCH_T", "T_TORCH_B", "T_CANDLES",
                                    "T_DRIP1", "T_DRIP2")}      # B3B-13b drips
            for r in present_rooms(blk):
                ok, tb, m = build_only(p, r)
                note("build_room_map", tb, f"D{d} r{r}")
                want_m = room_model.render_room(blk, r)
                bad = [(i % 32, i // 32, m[i], want_m[i]) for i in range(len(want_m)) if m[i] != want_m[i]]
                check(f"W11 D{d} r{r}: map == the spec model", ok and not bad, bad[:4])
                # B12: the raised gate only on the lair's 3 exit cells, its glow above the middle
                lair = blk[S["LVL_LAIR"] - S["LVL_STATE"]]
                gates = [i for i in range(576) if m[i] == T["T_GRATE"]]
                glows = [i for i in range(576) if m[i] == room_model.glow_id(d)]
                xc = room_model.field(blk, r, "RD_EXITCOL")
                F1 = S["FLOOR_ROW1"]
                want_g = [F1 * 32 + xc + k for k in range(3)] if r == lair else []
                check(f"W11 D{d} r{r}: gate (id {T['T_GRATE']}) {'+ glow on the level exit' if r == lair else 'nowhere: not the lair'}",
                      bool(xc) == (r == lair) and gates == want_g
                      and glows == ([(F1 - 1) * 32 + xc + 1] if r == lair else []), (xc, gates, glows))
                ok, ts = show_room(p, r)
                note("room_show + present_full", ts, f"D{d} r{r}")
                rows = [(c, row, m[row * 32 + c]) for row in (S["FLOOR_ROW0"], S["FLOOR_ROW1"])
                        for c in range(32) if m[row * 32 + c] not in floor_cls]
                check(f"W11 D{d} r{r}: floor rows 8 / 17 hold only floor-class tiles (no decor)",
                      ok and not rows, rows[:4])
                pit_air = [c for c in range(32) if m[S["FLOOR_ROW1"] * 32 + c] == T["T_AIR"]]
                check(f"W11 D{d} r{r}: no AIR in row 17 (pits are storey-0 only)", not pit_air, pit_air[:3])
                comp, disp = p.composed_frame(), p.frame()
                tabs = p.bg_tables()
                badc, bada = [], []
                for row in range(PLAY_ROWS):
                    for c in range(32):
                        g, a = room_model.expected_cell(*tabs, c, row)
                        for f in (comp, disp):
                            if attr_at(f, c, row) != a or bytes(cell_bytes(f, c, row)) != g:
                                badc.append((c, row))
                            if attr_at(f, c, row) not in legal:
                                bada.append((c, row, hex(attr_at(f, c, row))))
                        if row in (S["FLOOR_ROW0"], S["FLOOR_ROW1"]) and \
                                m[row * 32 + c] in (T["T_PLAT"], T["T_WALLF"], T["T_END_L"], T["T_END_R"]) \
                                and a != fl:
                            bada.append((c, row, "floor attr", hex(a)))
                check(f"W11 D{d} r{r}: both screens == map tiles (+ row-17 ornament)", not badc, badc[:4])
                check(f"W11 D{d} r{r}: playfield attrs legal for D{d} (floor = ATTR_FLOOR)", not bada, bada[:4])
            # the lair's level exit with the grate CLOSED (3B always opens it,
            # game.md §1.4; the closed branch is the 3F boss rule): T_GRATE x 3
            lair = blk[S["LVL_LAIR"] - S["LVL_STATE"]]
            fo = S["LVL_FLAGS"] - S["LVL_STATE"]
            p.wb(S["LVL_FLAGS"], blk[fo] & ~S["LF_GRATE_OPEN"] & 255)
            ok, _, m = build_only(p, lair)
            closed = bytearray(blk)
            closed[fo] &= ~S["LF_GRATE_OPEN"] & 255
            want_m = room_model.render_room(bytes(closed), lair)
            xc = room_model.field(blk, lair, "RD_EXITCOL")
            check(f"W11 D{d} lair r{lair}: grate closed -> T_GRATE over the exit hole, map == model",
                  ok and m == bytes(want_m) and xc and m[S["FLOOR_ROW1"] * 32 + xc] == T["T_GRATE"],
                  (ok, xc))
            p.wb(S["LVL_FLAGS"], blk[fo])
    # ---------------- W12: re-entry byte-identical ------------------------
    if want("W12"):
        n = 0
        rng = __import__("random").Random(0xB3B8)
        while n < 24:
            d = 1 + n % 8
            seed = rng.randrange(65536)
            ok, _, _, blk = gen_level(p, d, seed)
            rooms = present_rooms(blk)
            for r in rooms[:3]:
                other = rooms[-1] if rooms[-1] != r else rooms[0]
                ok1, _ = show_room(p, r)
                a = snapshot(p)
                ok2, _ = show_room(p, other)
                ok3, _ = show_room(p, r)
                b = snapshot(p)
                check(f"W12 D{d} seed {seed:#06x} r{r} (via r{other}): re-entry == first entry "
                      "(ROOM_MAP, bank 5, screen 2, shadow)",
                      ok and ok1 and ok2 and ok3 and a == b,
                      [i for i in range(4) if a[i] != b[i]])
                n += 1
    # ---------------- W12M: engine rooms == the spec model, many seeds -----
    if want("W12M"):
        rng = __import__("random").Random(0x12B)
        nroom = bad_n = 0
        feats = dict(doors=0, pits=0, blocks=0, arr=0, exit=0, lad2=0)
        for i in range(40):
            d, seed, master = rng.randint(1, 8), rng.randrange(65536), rng.randrange(65536)
            want_blk = G.generate(d, seed, master)
            ok, _, _, blk = gen_level(p, d, seed, master)
            if not ok or blk != want_blk:
                check(f"W12M d{d} seed {seed:#06x}: Z80 block == levelgen.py", False, ok)
                continue
            for r in present_rooms(want_blk):
                ok, tb, m = build_only(p, r)
                note("build_room_map", tb, f"D{d} seed {seed:#06x} r{r}")
                want_m = room_model.render_room(want_blk, r)
                nroom += 1
                bad = [(j % 32, j // 32, m[j], want_m[j]) for j in range(len(want_m)) if m[j] != want_m[j]]
                if bad or not ok:
                    bad_n += 1
                    check(f"W12M D{d} seed {seed:#06x} r{r}: engine map == model(levelgen.py)", False, bad[:4])
                inv = invariants(want_blk, r, m, d)
                if inv:
                    bad_n += 1
                    check(f"W12M D{d} seed {seed:#06x} r{r}: order-free invariants", False, inv[:4])
                fld = lambda k: room_model.field(want_blk, r, k)
                feats["pits"] += bool(fld("RD_PITCOL"))
                feats["blocks"] += bool(fld("RD_BLOCK") & 3)
                feats["arr"] += bool(fld("RD_ARRCOL"))
                feats["exit"] += bool(fld("RD_EXITCOL"))
                feats["lad2"] += bool(fld("RD_LAD2"))
                feats["doors"] += sum(1 for side in ("L", "R")
                                      if fld("RD_EXITS") & S["RDX_" + side]
                                      and want_blk[room_model.OFF_EDGE + room_model.edge_index(r, side)]
                                      & S["EG_DOOR"])
        print(f"[info] W12M: {nroom} rooms of 40 levels, features seen {feats}", flush=True)
        check(f"W12M: every built room == the model + order-free invariants ({nroom} rooms, every feature kind seen)",
              bad_n == 0 and nroom > 250 and all(feats.values()), (bad_n, nroom, feats))
    # ---------------- W13: decor deriver (B3B-9) ----------------------------
    # Z80 decor_room == tools/decorgen.py (ROOM_MAP + ANIM_LIST byte for byte), and
    # the rules re-checked from the docs (concept-screen 3.3 / game.md 1.2), not
    # from the generator: only AIR / BRICK cells change, solidity (TILE_FLAGS read
    # from the machine) follows the cell class, never in a floor row or the 2
    # rows above one, lintel row, ladder neighbourhood, budgets, ANIM_LIST sane.
    # B3B-10 (B3B-9 review): every room is also built into NEXT_MAP (-> ANIM_N2 /
    # ANIM_LIST2, ANIM_LIST untouched); a wall-heavy Python sweep and synthetic
    # maps (ladder / door / pit / block / rubble / potion cells inside the decor
    # ring) run the same checker, the synthetic ones also through the Z80.
    if want("W13"):
        rng = __import__("random").Random(0xB39)
        nroom = nplaced = 0
        sizes = {"anim": 0, "wall": 0, "air": 0, "large": 0}
        dT = []
        for i in range(12):
            d = 1 + i % 8
            seed, master = rng.randrange(65536), rng.randrange(65536)
            ok, _, _, blk = gen_level(p, d, seed, master)
            if not ok or blk != G.generate(d, seed, master):
                check(f"W13 D{d} seed {seed:#06x}: level generated", False, ok)
                continue
            flags = bytes(p.z.read_memory(S["tile_flags"], 64))
            for r in present_rooms(blk):
                base = room_model.render_room(blk, r, decor=False)
                al = []
                want_m = room_model.render_room(blk, r, anim=al)
                ok, t1, m = build_only(p, r)
                n = p.z.read_memory(S["ANIM_N"], 1)[0]
                got_al = list(p.z.read_memory(S["ANIM_LIST"], 4 * n)) if n else []
                nroom += 1
                m = list(m)
                bad = [(j % 32, j // 32, m[j], want_m[j]) for j in range(576) if m[j] != want_m[j]]
                check(f"W13 D{d} seed {seed:#06x} r{r}: ROOM_MAP == decorgen.py", ok and not bad, bad[:3])
                check(f"W13 D{d} seed {seed:#06x} r{r}: ANIM_LIST == decorgen.py", got_al == al, (n, got_al[:52], al))
                # the NEXT_MAP build (do_exit) fills ANIM_N2 / ANIM_LIST2 only
                p.z.cmd("write-memory %d 99" % S["ANIM_N2"])
                okn, _, mn = build_only(p, r, page=S["NEXT_MAP"] >> 8)
                n2 = p.z.read_memory(S["ANIM_N2"], 1)[0]
                got2 = list(p.z.read_memory(S["ANIM_LIST2"], 4 * n2)) if 0 < n2 <= 12 else ([] if n2 == 0 else None)
                after = list(p.z.read_memory(S["ANIM_LIST"], 4 * n)) if n else []
                check(f"W13 D{d} seed {seed:#06x} r{r}: NEXT_MAP build == decorgen.py, ANIM_LIST2 == its list, "
                      "ANIM_N / ANIM_LIST untouched",
                      okn and list(mn) == want_m and got2 == al
                      and p.z.read_memory(S["ANIM_N"], 1)[0] == n and after == got_al,
                      (okn, n2, len(al) // 4, list(mn) == want_m, n, p.z.read_memory(S["ANIM_N"], 1)[0],
                       after == got_al, got2, al))
                if i < 3 and r % 3 == 0:                  # decor cost: build with RD_SEED zeroed
                    da = S["ROOM_DESC"] + r * S["RD_STRIDE"] + S["RD_SEED"]
                    sv = bytes(p.z.read_memory(da, 2))
                    p.z.cmd("write-memory %d 0 0" % da)
                    _, t0, _ = build_only(p, r)
                    p.z.cmd("write-memory %d %d %d" % (da, sv[0], sv[1]))
                    dT.append(t1 - t0)
                errs = decor_rules(m, base, flags, got_al, d, sizes)
                nplaced += sum(1 for j in range(576) if m[j] != base[j])
                check(f"W13 D{d} seed {seed:#06x} r{r}: decor rules (independent checker)", not errs, errs[:3])
        print(f"[info] W13: {nroom} rooms, {nplaced} decor cells (air {sizes['air']}, wall {sizes['wall']}), "
              f"{sizes['anim']} anim entries, {sizes['large']} large animated objects; "
              f"decor_room cost T = {sorted(dT)}; patch cells still TF_SOLID in the tileset flags "
              f"(staff: clear per game.md 1.2 D1): {sizes.get('patch_solid', 0)}", flush=True)
        check("W13: >= 50 rooms over depths 1..8, decor present and animated",
              nroom >= 50 and nplaced > 100 and sizes["anim"] > 0, (nroom, nplaced, sizes))
        # ---- wall-heavy sweep (Python deriver, same checker): rooms with a
        # dead-end block / door / pit, 400 levels (D1 rules: patches are non-solid AIR decor, so
        # the only wall-class (T_BRICK, solid) decor left is a level's PILLAR - D6 after the
        # set cuts - hence 400 extra D6 levels to exercise that path)
        sw = {"rooms": 0, "wall": 0, "air": 0, "anim": 0, "large": 0}
        sbad = []
        rng = __import__("random").Random(0xB3B10)
        for i in range(800):
            d, seed, master = (6 if i >= 400 else 1 + i % 8), rng.randrange(65536), rng.randrange(65536)
            blk = G.generate(d, seed, master)
            fl = depth_flags(p, d)
            for r in present_rooms(blk):
                dd = room_model.desc(blk, r)
                if not (dd[S["RD_BLOCK"]] & 3 or dd[S["RD_PITCOL"]] or dd[S["RD_EXITS"]] & 3):
                    continue
                base = room_model.render_room(blk, r, decor=False)
                al = []
                m = room_model.render_room(blk, r, anim=al)
                sw["rooms"] += 1
                e = decor_rules(m, base, fl, al, d, sw)
                if e:
                    sbad.append((d, seed, master, r, e[:2]))
        print(f"[info] W13 sweep: {sw}", flush=True)
        check(f"W13 wall-heavy sweep: {sw['rooms']} rooms (block / pit / door), checker clean",
              not sbad and sw["rooms"] > 1000 and sw["wall"] > 0, sbad[:3])
        # ---- synthetic maps: structural cells scattered inside the decor rows
        # (rows 9s..9s+5 and their ring) -> Python checker on 600 maps, the Z80
        # deriver == Python on 24 of them (decor_room called directly: TMP1 =
        # ROOM_MAP page, IX = descriptor, dg_dst = ANIM_N)
        struct = [T[k] for k in ("T_LAD_L", "T_LAD_M", "T_LAD_R", "T_HOLE_L", "T_HOLE_R",
                                 "T_DOOR_ARCH_L", "T_DOOR_R", "T_DOOR_JAMB_L", "T_PIT_L",
                                 "T_PIT_R", "T_RUBBLE", "T_POTION", "T_DOOR_LOCK", "T_WALLF")]
        rng = __import__("random").Random(0x5E7)
        ybad, zbad, nsyn, nz = [], [], 0, 0
        for i in range(600):
            d, seed, master = 1 + i % 8, rng.randrange(65536), rng.randrange(65536)
            blk = G.generate(d, seed, master)
            r = rng.choice(present_rooms(blk))
            base = room_model.render_room(blk, r, decor=False)
            for _ in range(rng.randint(3, 12)):
                row = 9 * rng.randint(0, 1) + rng.randint(0, 6)
                base[row * 32 + rng.randint(1, 30)] = rng.choice(struct)
            rs = room_model.desc(blk, r)[S["RD_SEED"]] | room_model.desc(blk, r)[S["RD_SEED"] + 1] << 8
            m, al = room_model.decorgen.decorate(base, d, rs)
            nsyn += 1
            fl = depth_flags(p, d)
            e = decor_rules(m, base, fl, al, d, {"wall": 0, "air": 0, "anim": 0, "large": 0}, need_patch=False)
            if e:
                ybad.append((d, seed, r, e[:2]))
            if i % 25 == 0:
                okg, _, _, _ = gen_level(p, d, seed, master)
                nz += 1
                p.z.cmd("write-memory %d %s" % (S["ROOM_MAP"], " ".join(str(b) for b in base)))
                bank3_poke(p, S["dg_dst"], S["ANIM_N"] & 255)
                p.wb("ANIM_N", 0)
                ok, _ = run_code(p, head() + [0x3E, S["ROOM_MAP"] >> 8, 0x32] + w16(S["TMP1"])
                                 + [0xDD, 0x21] + w16(S["ROOM_DESC"] + r * S["RD_STRIDE"])
                                 + [0x3E, r, 0x21] + w16(S["decor_room"]) + [0xCD] + w16(S["far3"]))
                zm = list(p.z.read_memory(S["ROOM_MAP"], 576))
                zn = p.rb("ANIM_N")
                zal = list(p.z.read_memory(S["ANIM_LIST"], 4 * zn)) if 0 < zn <= 12 else []
                if not (okg and ok and zm == m and zal == al):
                    zbad.append((d, seed, r, okg, ok, zm == m, zal, al))
        check(f"W13 synthetic maps: {nsyn} maps with structural cells in the decor ring, checker clean",
              not ybad, ybad[:3])
        check(f"W13 synthetic maps: Z80 decor_room == decorgen.py on {nz} of them", not zbad, zbad[:2])
    if worst:
        print("[info] B3B-8 measured (DI, contended): " + ", ".join(
            f"{k} worst {v[0]} T ({v[1]})" for k, v in worst.items()), flush=True)
    p.load()


# ---------------------------------------------------------------------------
# B3B-12 (W16): level change. New game on a generated D1 (proto_start = 0,
# seed_fixed + seed_value), descend through the lair's level exit, D1 -> D8,
# the reseed-exhausting D8 seeds, D8 descend = GS_WIN.
# ---------------------------------------------------------------------------
LVL_MUL = S["LVL_SEED_MUL"]
GEN_NOWHERE = 15                               # not a room id of a generated level


def lvl_seed(master, d):
    return (master + d * LVL_MUL) & 0xFFFF


def bank3_bytes(p, addr, n):
    p.z.cmd("set-memory-zone 0")
    try:
        return bytes(p.z.read_memory(3 * 16384 + addr - 0xC000, n))
    finally:
        p.z.cmd("set-memory-zone -1")


def pop_model(p, blk, depth):
    """The stand-in population (bank3.asm level_populate), written from its
    rule: [(kind, room, x, y, flags, hp)] in slot order 1..15."""
    kinds = bank3_bytes(p, S["pop_kinds"], S["POP_KINDS"])
    cols = bank3_bytes(p, S["pop_cols"], 18)
    kt = S["kind_tab"]
    rd = lambda r, k: room_model.field(blk, r, k)  # noqa: E731
    start = blk[S["LVL_START"] - room_model.BASE]

    def hits(r, s_, lo, hi):
        fp = ("RD_UPCOL", "RD_ARRCOL", "RD_LAD1", "RD_LAD2") if s_ == 0 else \
             ("RD_DNCOL", "RD_EXITCOL", "RD_LAD1", "RD_LAD2")
        for k in fp:
            f = rd(r, k)
            if f and f <= hi and f + 2 >= lo:
                return True
        pit = rd(r, "RD_PITCOL")
        if s_ == 0 and pit and pit - 1 <= hi and pit + 3 >= lo:
            return True
        if s_ == 1 and pit and pit <= hi and pit + 2 >= lo:     # the fall's landing cols
            return True
        bl = rd(r, "RD_BLOCK")
        if bl and (bl >> 6) & 1 == s_:
            w = bl & S["RDB_WMASK"]
            if (bl & 0x80 and hi + w >= 31) or (not bl & 0x80 and w >= lo):
                return True
        return False
    out = []
    for r in range(9):
        if r == start or not rd(r, "RD_FLAGS") & S["RDF_PRESENT"]:
            continue
        for e in range(2):
            if len(out) == 15:
                return out
            k = kinds[(r + 3 * e + depth) % 6]
            w, h = p.rb(kt + S["KT_BW"] + k), p.rb(kt + S["KT_BH"] + k)
            fly = p.rb(kt + S["KT_FLAGS"] + k) & S["KF_FLYER"]
            m, s_, x = (3 if fly else 1), 1 - e, cols[2 * r + e]
            for _ in range(S["POP_TRIES"]):
                if not hits(r, s_, x - m, x + w - 1 + m):
                    y = 9 * s_ + 1 if fly else 9 * s_ + 8 - h
                    fl = EF_ACTIVE | EF_HOSTILE | (EF_LEFT if x >= 15 else 0)
                    out.append((k, r, x, y, fl, p.rb(kt + S["KT_HP"] + k)))
                    break
                x += 3
                if x > S["POP_XMAX"]:
                    x -= S["POP_XMAX"] + 1 - S["POP_XMIN"]
    return out


def w16_level(p, check):
    import levelgen as G
    kw, kh = game.body(p, K_KNIGHT)
    y0, y1 = stand_y(0, kh), stand_y(1, kh)
    M = 0x1234
    rom = bytes(p.z.read_memory(S["ROM_CHARSET"], 96 * 8))
    STUB = S["LOWRAM_END_3B"]
    info = {}

    def ingame(code, tag):
        """Run code (DI ... EI) from the wait_tick probe, play resumes there."""
        pc0 = p.pc()
        ok = p.run_stub([0xF3] + code + [0xFB], org=STUB)
        p.z.cmd("set-register PC=%d" % pc0)
        check(f"W16 stub {tag} ran", ok, "")

    def card_ok(fr, d):
        txt = "DEPTH %d" % d
        r, c0 = S["CARD_ROW"], S["CARD_COL"]
        return all(bytes(cell_bytes(fr, c0 + i, r)) == rom[(ord(ch) - 32) * 8:(ord(ch) - 31) * 8]
                   for i, ch in enumerate(txt))

    def level_ok(d, master, tag, hero_keep=None, seed=None):
        """Everything a fresh level must satisfy (tag: where we are)."""
        blk = room_model.read_block(p)
        want = G.generate(d, lvl_seed(master, d) if seed is None else seed, master)
        check(f"W16 {tag}: LVL_DEPTH {d}, block == levelgen.generate({d}, master + {d} * MUL)",
              p.rb("LVL_DEPTH") == d and blk == want, (p.rb("LVL_DEPTH"), hex(p.rw("LVL_SEED"))))
        st = blk[S["LVL_START"] - room_model.BASE]
        e = p.ent(0)
        check(f"W16 {tag}: hero on the start room, x = start_x, standing on storey 0",
              (p.rb("CUR_ROOM"), e["ROOM"], e["X"], e["Y"]) == (st, st, G.start_x(blk), y0),
              (p.rb("CUR_ROOM"), st, e["X"], e["Y"], G.start_x(blk)))
        if hero_keep:
            check(f"W16 {tag}: HP / MAXHP / potions / kind carried over",
                  (e["HP"], e["MAXHP"], e["POT"], e["KIND"]) == hero_keep, (e, hero_keep))
        check(f"W16 {tag}: GS_PLAYING, EXIT_KIND 0, GEN_TRAP 0, GEN_OVERFLOW 0",
              (p.rb("GAME_STATE"), p.rb("EXIT_KIND"), p.rb("GEN_TRAP"), p.rb("GEN_OVERFLOW"))
              == (GS_PLAYING, 0, 0, 0),
              (p.rb("GAME_STATE"), p.rb("EXIT_KIND"), p.rb("GEN_TRAP"), p.rb("GEN_OVERFLOW")))
        fa, wa = room_model.THEME[d]
        lvl = S["TILE_GLYPHS"] + S["T_LVL_BASE"] * 8
        slot = (S["TSET_LO"] if d <= 4 else S["TSET_HI"]) + ((d - 1) & 3) * S["TSET_STRIDE"]
        check(f"W16 {tag}: theme D{d} (floor / wall attrs, ids 32..63 == bank-7 slot {d - 1})",
              (p.rb("LVL_ATTR_FLOOR"), p.rb("LVL_ATTR_WALL")) == (fa, wa)
              and bytes(p.z.read_memory(lvl, 256)) == bank7(p, slot, 256),
              (hex(p.rb("LVL_ATTR_FLOOR")), hex(p.rb("LVL_ATTR_WALL"))))
        mods = pop_model(p, blk, d)
        got = []
        for s_ in range(1, 16):
            q = p.ent(s_)
            got.append((q["KIND"], q["ROOM"], q["X"], q["Y"], q["FLAGS"], q["HP"]) if q["FLAGS"] else None)
        check(f"W16 {tag}: population == the stand-in rule ({len(mods)} monsters, start room empty)",
              got[:len(mods)] == mods and all(g is None for g in got[len(mods):])
              and not any(m[1] == st for m in mods), (got, mods))
        bad = placement_props(blk)
        check(f"W16 {tag}: every monster clear of holes / ladders / pit cells in its built room "
              "(property check on the engine's maps)", bad == [], bad[:4])
        p.settle(2)
        fr = p.frame()
        check(f"W16 {tag}: panel depth D{d} at (30, 18)", log_row(fr, 18, 30, 2) == text6("D%d" % d, 0, 2), "")
        stale = [s_ for s_ in range(16) if p.ent(s_)["DVIS"] & 1 and
                 (p.ent(s_)["ROOM"] != p.rb("CUR_ROOM") or not p.ent(s_)["FLAGS"] & EF_ACTIVE)]
        check(f"W16 {tag}: no stale sprite (B7: every drawn slot is in CUR_ROOM)", stale == [], stale)
        check(f"W16 {tag}: first play tick: ROOM_MAP == model, ANIM_LIST == the start room's, "
              "screens == map (before any decor_tick)", fresh.get(d) == [], fresh.get(d))
        return blk

    def placement_props(blk):
        """Independent of pop_model: build every room holding monsters into
        NEXT_MAP (scratch while playing; the build fills ANIM_N2 only) and test
        each body on the ENGINE's map + tile_flags: no TF_LADDER / TF_HOLE cell
        in its storey rows within its margin (walker 1 col, flyer 3), walkers'
        floor cells under the body TF_FLOOR, no hole / air cell in the floor
        rows bounding its storey within the margin (pit holes, the cols a fall
        from storey 0 lands on), no solid cell in its body box."""
        tf = p.z.read_memory(S["tile_flags"], 64)
        LAD, HOLE, FLOOR, SOLID = S["TF_LADDER"], S["TF_HOLE"], S["TF_FLOOR"], S["TF_SOLID"]
        kt = S["kind_tab"]
        rooms = {}
        for s_ in range(1, 16):
            e = p.ent(s_)
            if e["FLAGS"] & EF_ACTIVE:
                rooms.setdefault(e["ROOM"], []).append(e)
        bad = []
        page = S["NEXT_MAP"] >> 8
        for r, ents in rooms.items():
            ingame([0x3E, r, 0x16, page, 0x21] + w16(S["build_room_map"]) + [0xCD] + w16(S["far3"]),
                   f"build room {r} -> NEXT_MAP")
            m = p.z.read_memory(S["NEXT_MAP"], 576)
            for e in ents:
                k = e["KIND"]
                w, h = p.rb(kt + S["KT_BW"] + k), p.rb(kt + S["KT_BH"] + k)
                fly = p.rb(kt + S["KT_FLAGS"] + k) & S["KF_FLYER"]
                mg = 3 if fly else 1
                s_ = 1 if e["Y"] >= 9 else 0
                c0, c1 = max(0, e["X"] - mg), min(31, e["X"] + w - 1 + mg)
                cell = lambda c, rr: tf[m[rr * 32 + c]]  # noqa: E731
                for rr in range(9 * s_, 9 * s_ + 9):
                    for c in range(c0, c1 + 1):
                        if cell(c, rr) & (LAD | HOLE):
                            bad.append((r, k, e["X"], s_, "ladder/hole", c, rr))
                for fr_ in ((8,) if s_ == 0 else (8, 17)):
                    for c in range(c0, c1 + 1):
                        if not cell(c, fr_) & FLOOR:
                            bad.append((r, k, e["X"], s_, "floor gap", c, fr_))
                for rr in range(e["Y"], e["Y"] + h):
                    for c in range(e["X"], e["X"] + w):
                        if cell(c, rr) & SOLID:
                            bad.append((r, k, e["X"], s_, "solid", c, rr))
        return bad

    fresh = {}

    def fresh_ok(tag):
        """At the first wait_tick of a new level (no decor_tick / render yet):
        ROOM_MAP, ANIM_LIST (phases = the build's stagger) and both screens."""
        d = p.rb("LVL_DEPTH")
        blk = room_model.read_block(p)
        st = p.rb("CUR_ROOM")
        errs = []
        al = []
        want_m = room_model.render_room(blk, st, anim=al)
        n = p.rb("ANIM_N")
        got_al = list(p.z.read_memory(S["ANIM_LIST"], 4 * n)) if 0 < n <= 12 else []
        if list(p.z.read_memory(S["ROOM_MAP"], 576)) != want_m:
            errs.append("ROOM_MAP != model")
        if got_al != al or n != len(al) // 4:
            errs.append(("ANIM_LIST", n, got_al[:12], al[:12]))
        errs += p.screen_vs_map(tag)
        fresh[d] = errs

    def to_exit(blk, tag, walk=True, adjacent=False):
        """Teleport the hero next to the lair's level exit (storey 1), the
        lair's monsters out, walk onto {EXITCOL,2}, J: descend. -> (frames
        while the card was shown at level_new, T of the turn's ticks)."""
        lair = blk[S["LVL_LAIR"] - room_model.BASE]
        ex = room_model.field(blk, lair, "RD_EXITCOL")
        x = ex - 2 if ex - 2 >= 2 else ex + 2
        mons = [s_ for s_ in range(1, 16) if p.ent(s_)["FLAGS"] & EF_ACTIVE and p.ent(s_)["ROOM"] == lair]
        for s_ in mons:
            if not adjacent:
                p.set_ent(s_, ROOM=GEN_NOWHERE)
        if adjacent:                              # the lair keeps its monsters; one
            s_ = mons[0] if mons else 1           # walker right beside the hero
            k = S["K_GOBLIN"]
            gh = p.rb(S["kind_tab"] + S["KT_BH"] + k)
            gx = ex + kw if ex + kw + 2 <= 29 else ex - 2
            p.set_ent(s_, KIND=k, ROOM=lair, FLAGS=EF_ACTIVE | EF_HOSTILE | EF_LEFT, X=gx,
                      Y=stand_y(1, gh), PX=gx * 8, PY=stand_y(1, gh) * 8, MODE=0, DVIS=0,
                      HP=p.rb(S["kind_tab"] + S["KT_HP"] + k))
        p.z.cmd("write-memory %d %d" % (S["CUR_ROOM"], lair))
        p.set_ent(0, ROOM=lair, X=x if walk else ex, Y=y1, PX=(x if walk else ex) * 8, PY=y1 * 8,
                  MODE=0, DVIS=0)
        ingame([0x3E, lair, 0xCD] + w16(S["room_show"]) + [0xCD] + w16(S["vis_reset"])
               + [0xCD] + w16(S["present_full"]), "teleport " + tag)
        p.settle(2)
        if walk:
            check(f"W16 {tag}: walked to the level exit col {ex}", p.walk_to(ex), (p.ent(0)["X"], ex))
        cards = []
        p.z.cmd("set-breakpoint 4 PC=%d" % S["level_new"])
        p.extra_probes = {S["level_new"]}

        d0 = p.rb("LVL_DEPTH")

        def per(fr, e):
            if p.pc() == S["level_new"]:
                cards.append((fr, p.rb("LVL_DEPTH"), p.rw("SYS_FRAMES")))
            elif p.pc() == S["wait_tick"] and p.rb("LVL_DEPTH") != d0 and p.rb("LVL_DEPTH") not in fresh:
                fresh_ok(tag)
        f0 = p.rw("SYS_FRAMES")
        ran = p.turn("J", per_tick=per)
        p.z.cmd("set-breakpoint 4")
        p.extra_probes = set()
        p.until(lambda: p.idle(), 100)
        return ran, cards, (p.rw("SYS_FRAMES") - f0) & 0xFFFF

    HINT = dict(STRINGS)["gate_gleams"]

    def lair_visit(tag):
        """B12: walk into the lair (real do_exit) from its door-side neighbour,
        twice: the gate hint is logged on the first entry only; the lair shows
        the raised gate + glow (map == model, screens == map); J on the exit col
        with the grate closed is no exit (EX_LEVEL only through LF_GRATE_OPEN)."""
        blk = room_model.read_block(p)
        lair = blk[S["LVL_LAIR"] - room_model.BASE]
        ex = room_model.field(blk, lair, "RD_EXITS")
        side = "L" if ex & S["RDX_L"] else "R"
        nb = lair - 1 if side == "L" else lair + 1
        s_ = 1 if ex & S["RDX_LS1" if side == "L" else "RDX_RS1"] else 0
        ei = S["EDGE_TAB"] + room_model.edge_index(lair, side)
        p.wb(ei, p.rb(ei) & ~(S["EG_LOCK"] | S["EG_SEAL"]) & 255)   # test: never a locked way in
        for k in range(1, 16):
            p.set_ent(k, FLAGS=0)                 # nobody in the way, nothing else logs
        x, key, back = (32 - 2 - kw, "L", "H") if side == "L" else (2, "H", "L")
        fl = EF_ACTIVE | EF_PLAYER | (0 if side == "L" else EF_LEFT)

        def to_nb():
            p.z.cmd("write-memory %d %d" % (S["CUR_ROOM"], nb))
            p.set_ent(0, ROOM=nb, X=x, Y=stand_y(s_, kh), PX=x * 8, PY=stand_y(s_, kh) * 8,
                      FLAGS=fl, MODE=0, DVIS=0)
            ingame([0x3E, nb, 0xCD] + w16(S["room_show"]) + [0xCD] + w16(S["vis_reset"])
                   + [0xCD] + w16(S["present_full"]), "lair neighbour " + tag)
            p.settle(2)

        def walk_in():
            for _ in range(24):
                if p.rb("CUR_ROOM") == lair:
                    break
                p.turn(key)
            p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
            p.until(lambda: p.rb("LOG_QN") == 0, 200)
            p.settle(4)
        check(f"W16 {tag}: LF_GATE_HINT clear on a fresh level",
              not p.rb("LVL_FLAGS") & S["LF_GATE_HINT"], hex(p.rb("LVL_FLAGS")))
        to_nb()
        walk_in()
        fr = p.frame()
        if game.PNG_DIR:                          # --png DIR: the lair as entered, for a look
            from game_lib import frame_png
            os.makedirs(game.PNG_DIR, exist_ok=True)
            frame_png(bytes(fr), os.path.join(game.PNG_DIR, f"b12_lair_{tag}.png"))
        check(f"W16 {tag}: first entry to the lair r{lair}: '{HINT}' logged, LF_GATE_HINT set",
              p.rb("CUR_ROOM") == lair and log_row(fr, 23) == text6(HINT)
              and bool(p.rb("LVL_FLAGS") & S["LF_GATE_HINT"]),
              (p.rb("CUR_ROOM"), hex(p.rb("LVL_FLAGS")), log_row(fr, 23) == text6(HINT)))
        xc = room_model.field(blk, lair, "RD_EXITCOL")
        m = p.z.read_memory(S["ROOM_MAP"], 576)
        F1 = S["FLOOR_ROW1"]
        check(f"W16 {tag}: lair (do_exit build) map == model: gate x3 on the exit, the glow above",
              not map_structure(p, lair) and all(m[F1 * 32 + xc + k] == S["T_GRATE"] for k in range(3))
              and m[(F1 - 1) * 32 + xc + 1] == room_model.glow_id(p.rb("LVL_DEPTH")),
              (map_structure(p, lair)[:3], list(m[F1 * 32 + xc:F1 * 32 + xc + 3]), m[(F1 - 1) * 32 + xc + 1]))
        # the gate / glow cells and row 17 on both screens (the whole-room check
        # would trip over the torches' attr cycle, decor_tick)
        tabs = p.bg_tables()
        cells = [(c, F1) for c in range(32)] + [(xc + 1, F1 - 1)]
        bad = [(scr, c, r_) for scr, f in (("displayed", p.frame()), ("composed", p.composed_frame()))
               for c, r_ in cells
               if (attr_at(f, c, r_), bytes(cell_bytes(f, c, r_))) != room_model.expected_cell(*tabs, c, r_)[::-1]]
        check(f"W16 {tag}: lair screens == map on row 17 + the glow cell (gate $46, glow, ornament)",
              not bad and p.rb(S["TILE_ATTRS"] + S["T_GRATE"]) == S["ATTR_GRATE"], bad[:4])
        # a marker line, then out and back in: no second hint
        ingame([0x3E, S["TX_FOUND"], 0xCD] + w16(S["msg_push"]), "marker " + tag)
        p.until(lambda: p.rb("LOG_QN") == 0, 200)
        p.settle(4)
        for _ in range(24):
            if p.rb("CUR_ROOM") == nb:
                break
            p.turn(back)
        p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
        walk_in()
        check(f"W16 {tag}: second entry to the lair: no second hint (row 23 = the marker)",
              p.rb("CUR_ROOM") == lair and log_row(p.frame(), 23) == text6(dict(STRINGS)["found"]),
              p.rb("CUR_ROOM"))
        # the exit col with the grate CLOSED: J is no exit (and no turn)
        fo = p.rb("LVL_FLAGS")
        p.wb("LVL_FLAGS", fo & ~S["LF_GRATE_OPEN"] & 255)
        p.place(0, xc, y1, room=lair, flags=EF_ACTIVE | EF_PLAYER)
        d0 = p.rb("LVL_DEPTH")
        nt = p.no_turn("J")
        check(f"W16 {tag}: grate closed: J on the exit col {xc} = no turn, no EX_LEVEL",
              nt and p.rb("EXIT_KIND") == 0 and p.rb("LVL_DEPTH") == d0, (nt, p.rb("EXIT_KIND")))
        p.wb("LVL_FLAGS", fo)
        return blk

    # ---- new game on a generated D1 --------------------------------------
    p.proto_start = 0
    try:
        p.load()
        p.wait_state(S["GS_SELECT"])
        p.wb("seed_fixed", 1)
        p.z.cmd("write-memory %d %d %d" % (S["seed_value"], M & 255, M >> 8))
        p.wb("INPUT_REPEAT", 0)
        p.wb("ANIM_FREEZE", 1)
        p.wb("INPUT_SRC", 1)
        p.hold("1")
        p.wait_state(GS_PLAYING)
        fresh_ok("D1 start")                     # the first wait_tick of the game
        p.release()
        p.settle(3)
        check("W16 new game: MASTER_SEED = seed_value (seed_fixed), LVL_SEED = master + MUL",
              (p.rw("MASTER_SEED"), p.rb("LVL_DEPTH")) == (M, 1), hex(p.rw("MASTER_SEED")))
        blk = level_ok(1, M, "D1 start")
        hero_k = tuple(p.ent(0)[k] for k in ("HP", "MAXHP", "POT", "KIND"))
        # level_enter cost (cold), measured on its own (DI: no ISR; screen /
        # card / generator / build / panel / presents), D2 of this game
        d1 = room_model.read_block(p)
        lair_visit("D1")                        # B12
        # ---- descend D1 -> D2 by walking onto the exit -----------------
        ran, cards, fr_n = to_exit(blk, "D1")
        check("W16 D1 -> D2: J on {EXITCOL,2} is one turn (first step animated) + the level change",
              ran, "")
        check("W16 D1 -> D2: the DEPTH 2 card is displayed while the level is generated",
              len(cards) == 1 and cards[0][1] in (1, 2) and card_ok(cards[0][0], 2), len(cards))
        info["descend D1->D2 frames (input tick .. idle)"] = fr_n
        blk2 = level_ok(2, M, "D2 after descend", hero_keep=hero_k)
        check("W16 D2: colours / tileset differ from D1",
              d1[S["LVL_ATTR_FLOOR"] - room_model.BASE] != blk2[S["LVL_ATTR_FLOOR"] - room_model.BASE], "")
        # ---- room change + re-entry on the new level -------------------
        for s_ in range(1, 16):
            p.set_ent(s_, FLAGS=0)                    # nobody interferes with the walk
        st = blk2[S["LVL_START"] - room_model.BASE]
        ex = room_model.field(blk2, st, "RD_EXITS")
        if ex & (S["RDX_R"] | S["RDX_L"]):
            side = "R" if ex & S["RDX_R"] else "L"
            s_ = 1 if ex & (S["RDX_RS1"] if side == "R" else S["RDX_LS1"]) else 0
            key, back = ("L", "H") if side == "R" else ("H", "L")
            dest = st + (1 if side == "R" else -1)
            pos = (32 - 2 - kw if side == "R" else 2, stand_y(s_, kh),
                   EF_ACTIVE | EF_PLAYER | (0 if side == "R" else EF_LEFT))
        elif ex & S["RDX_U"]:
            side, key, back, dest = "U", "K", "J", st - 3
            pos = (room_model.field(blk2, st, "RD_UPCOL"), y0, EF_ACTIVE | EF_PLAYER)
        else:
            side, key, back, dest = "D", "J", "K", st + 3
            pos = (room_model.field(blk2, st, "RD_DNCOL"), y1, EF_ACTIVE | EF_PLAYER)
        m0 = bytes(p.z.read_memory(S["ROOM_MAP"], 576))
        al0 = []
        room_model.render_room(room_model.read_block(p), st, anim=al0)
        p.place(0, pos[0], pos[1], flags=pos[2])

        def go(k, target):
            for _ in range(24):
                if p.rb("CUR_ROOM") == target:
                    break
                p.turn(k)
            p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)

        def anim_cells():
            """ANIM_LIST as {(col, row): {type, map id}} (decor_tick swaps / steps
            between the build and now: compare cells + id pairs, not phases)."""
            n = p.rb("ANIM_N")
            raw = p.z.read_memory(S["ANIM_LIST"], 4 * n)
            m = p.z.read_memory(S["ROOM_MAP"], 576)
            return {(raw[i], raw[i + 1]): frozenset((raw[i + 2], m[raw[i + 1] * 32 + raw[i]]))
                    for i in range(0, 4 * n, 4)}

        def model_cells(blk, r):
            al = []
            mm = room_model.render_room(blk, r, anim=al)
            return {(al[i], al[i + 1]): frozenset((al[i + 2], mm[al[i + 1] * 32 + al[i]]))
                    for i in range(0, len(al), 4)}
        go(key, dest)
        p.settle()
        blk_now = room_model.read_block(p)
        check(f"W16 D2: room change {st} -> {dest} ({side}): CUR_ROOM, ANIM_LIST cells == the room's, GEN_TRAP 0",
              p.rb("CUR_ROOM") == dest and anim_cells() == model_cells(blk_now, dest) and p.rb("GEN_TRAP") == 0,
              (p.rb("CUR_ROOM"), sorted(anim_cells()), sorted(model_cells(blk_now, dest))))
        go(back, st)
        p.settle()
        mm = bytes(p.z.read_memory(S["ROOM_MAP"], 576))
        # cells under ANIM_LIST may hold the other glyph frame: compare the rest
        cells = {(al0[i], al0[i + 1]) for i in range(0, len(al0), 4)}
        same = all(mm[i] == m0[i] for i in range(576) if (i % 32, i // 32) not in cells)
        check(f"W16 D2: re-entry {dest} -> {st}: ROOM_MAP == the first build (decor cells aside), "
              "ANIM_LIST cells == the room's, GEN_TRAP 0",
              p.rb("CUR_ROOM") == st and same and anim_cells() == model_cells(blk_now, st)
              and p.rb("GEN_TRAP") == 0, p.rb("CUR_ROOM"))
        lair_visit("D2")                        # B12: once per level, again on D2
        # ---- D2 .. D7: descend on the exit (teleported onto it) ---------
        blk = room_model.read_block(p)
        for d in range(3, 8):
            hero_k = tuple(p.ent(0)[k] for k in ("HP", "MAXHP", "POT", "KIND"))
            ran, cards, fr_n = to_exit(blk, f"D{d - 1}", walk=False, adjacent=(d == 3))
            if d == 3:
                check("W16 D2 -> D3 with the lair's monsters present and a goblin adjacent: "
                      "one turn, descended, HP unchanged (monsters don't act on an exit turn)",
                      ran and p.rb("LVL_DEPTH") == 3 and p.ent(0)["HP"] == hero_k[0], (ran, p.rb("LVL_DEPTH")))
            check(f"W16 D{d - 1} -> D{d}: card DEPTH {d} shown", len(cards) == 1 and card_ok(cards[0][0], d), "")
            blk = level_ok(d, M, f"D{d}", hero_keep=hero_k)
        # ---- D7 -> D8 with the seeds that exhausted the 16 reseeds before L1
        # (2026-10-05: the L1 level shape never reseeds, so level_new's retry
        # path is no longer reachable by any seed; these now generate first time)
        for bad_seed in (55352, 55353, 55354):
            m8 = (bad_seed - 8 * LVL_MUL) & 0xFFFF
            p.z.cmd("write-memory %d %d %d" % (S["MASTER_SEED"], m8 & 255, m8 >> 8))
            p.wb("LVL_DEPTH", 7)
            fresh.pop(8, None)
            ran, cards, fr_n = to_exit(blk, f"D7 (seed {bad_seed})", walk=False)
            info[f"descend D7->D8 seed {bad_seed} frames"] = fr_n
            blk = level_ok(8, m8, f"D8 from former exhausting seed {bad_seed}", seed=bad_seed)
            check(f"W16 D8 seed {bad_seed}: generated first time (no reseed under L1)",
                  p.rw("LVL_SEED") == bad_seed, p.rw("LVL_SEED"))
        # ---- D8 descend = GS_WIN (stand-in) -----------------------------
        ran, cards, fr_n = to_exit(blk, "D8", walk=False)
        check("W16 D8: descending = GS_WIN (game.md §1.4 stand-in), no card, depth stays 8",
              (p.rb("GAME_STATE"), p.rb("LVL_DEPTH"), len(cards), p.rb("EXIT_KIND")) == (S["GS_WIN"], 8, 0, 0),
              (p.rb("GAME_STATE"), p.rb("LVL_DEPTH"), len(cards)))
        # ---- win -> new game: fresh D1, a new master seed ---------------
        def new_game_from_end(tag, prev_master):
            p.hold("ENTER")
            p.wait_state(S["GS_SELECT"])
            p.release()
            p.tick(3)
            p.wb("seed_fixed", 0)                     # the real seed source
            p.hold("1")
            p.wait_state(GS_PLAYING)
            fresh.pop(1, None)
            fresh_ok(tag)
            p.release()
            p.settle(3)
            ms = p.rw("MASTER_SEED")
            hp = p.rb(S["kind_tab"] + S["KT_HP"] + K_KNIGHT)
            e = p.ent(0)
            check(f"W16 {tag}: new game = fresh D1 (HP {hp}/{hp}, 1 potion, turn 0), new master seed",
                  (p.rb("LVL_DEPTH"), e["HP"], e["MAXHP"], e["POT"]) == (1, hp, hp, 1)
                  and p.rw("TURN_COUNTER") == 0 and ms != prev_master, (e, hex(ms), hex(prev_master)))
            level_ok(1, ms, tag)
            return ms
        ms = new_game_from_end("after the win", m8)
        # ---- descend, then die -> new game: fresh D1 -------------------
        blk = room_model.read_block(p)
        to_exit(blk, "new game D1", walk=False)
        check("W16 new game: descended to D2", p.rb("LVL_DEPTH") == 2, p.rb("LVL_DEPTH"))
        e = p.ent(0)
        k = S["K_SKELETON"]
        sh = p.rb(S["kind_tab"] + S["KT_BH"] + k)
        sx = e["X"] + kw if e["X"] + kw + 3 <= 29 else e["X"] - 3
        p.set_ent(1, KIND=k, ROOM=p.rb("CUR_ROOM"), FLAGS=EF_ACTIVE | EF_HOSTILE | (EF_LEFT if sx > e["X"] else 0),
                  X=sx, Y=stand_y(0, sh), PX=sx * 8, PY=stand_y(0, sh) * 8, MODE=0, DVIS=0, HP=20)
        p.set_ent(0, HP=1, POT=0)
        for _ in range(30):
            if p.rb("GAME_STATE") == GS_DEAD:
                break
            p.turn("SPACE")
        check("W16 D2: the hero dies (GS_DEAD)", p.rb("GAME_STATE") == GS_DEAD, p.rb("GAME_STATE"))
        new_game_from_end("after death on D2", ms)
        # ---- cost: level_enter alone (DI), D2 of this run ---------------
        p.z.cmd("reset-tstates-partial")
        pc0 = p.pc()
        ok = p.run_stub([0xF3, 0x3E, 2, 0x11] + w16(S["TX_DESCEND"]) + [0xCD] + w16(S["level_enter"]) + [0xFB],
                        org=STUB)
        t = int(p.z.cmd("get-tstates-partial"))
        p.z.cmd("set-register PC=%d" % pc0)
        info["level_enter D2 T (DI)"] = t
        check("W16 level_enter (D2, DI) ran, cold path < 3.5M T (~1 s)", ok and t < 3500000, t)
    finally:
        p.proto_start = 1
    print("[info] W16 measured: " + ", ".join(f"{k} {v:,}" for k, v in info.items()), flush=True)


def w21_exits(p, check):
    """W21 (B11): walk every storey-0 horizontal exit of generated D1s both
    ways (hero teleported next to it, monsters out, doors opened), then on
    across the room until the pit (if any)."""
    kw, kh = game.body(p, K_KNIGHT)
    y0 = stand_y(0, kh)
    F0 = S["FLOOR_ROW0"]
    p.proto_start = 0
    n_exits = n_pits = 0
    try:
        for M in (0x0007, 0x1234):
            p.load()
            p.wait_state(S["GS_SELECT"])
            p.wb("seed_fixed", 1)
            p.z.cmd("write-memory %d %d %d" % (S["seed_value"], M & 255, M >> 8))
            p.wb("INPUT_REPEAT", 0)
            p.wb("ANIM_FREEZE", 1)
            p.wb("INPUT_SRC", 1)
            p.hold("1")
            p.wait_state(GS_PLAYING)
            p.release()
            p.settle(3)
            blk = room_model.read_block(p)
            et = S["EDGE_TAB"]
            for i in range(S["EDGES_H"]):              # every door open: walk through
                v = blk[et - room_model.BASE + i]
                if v & S["EG_DOOR"]:
                    p.wb(et + i, (v | S["EG_OPEN"]) & ~(S["EG_LOCK"] | S["EG_SEAL"]) & 255)
            for s_ in range(1, 16):
                p.set_ent(s_, ROOM=GEN_NOWHERE)
            for r in present_rooms(blk):
                ex = room_model.field(blk, r, "RD_EXITS")
                for bit, s1, key, x0, dst, xa in (("RDX_L", "RDX_LS1", "H", 3, r - 1, 31 - kw),
                                                  ("RDX_R", "RDX_RS1", "L", 29 - kw, r + 1, 1)):
                    if not ex & S[bit] or ex & S[s1]:
                        continue
                    tag = f"M{M:#06x} {r}->{dst}"
                    p.z.cmd("write-memory %d %d" % (S["CUR_ROOM"], r))
                    p.set_ent(0, ROOM=r, X=x0, Y=y0, PX=x0 * 8, PY=y0 * 8, MODE=0, DVIS=0)
                    pc0 = p.pc()
                    ok = p.run_stub([0xF3, 0x3E, r, 0xCD] + w16(S["room_show"]) + [0xCD]
                                    + w16(S["vis_reset"]) + [0xCD] + w16(S["present_full"]) + [0xFB],
                                    org=S["LOWRAM_END_3B"])
                    p.z.cmd("set-register PC=%d" % pc0)
                    p.settle(2)
                    hp0 = p.ent(0)["HP"]
                    modes = set()
                    for _ in range(8):
                        if p.rb("CUR_ROOM") != r:
                            break
                        p.turn(key, per_tick=lambda fr, e: modes.add(e["MODE"]))
                    p.settle(2)
                    e = p.ent(0)
                    n_exits += 1
                    check(f"W21 {tag}: storey-0 exit, no fall, arrival (room, x, y, HP) = "
                          f"({dst}, {xa}, {y0}, {hp0})",
                          ok and S["M_FALL"] not in modes
                          and (p.rb("CUR_ROOM"), e["X"], e["Y"], e["HP"]) == (dst, xa, y0, hp0),
                          (sorted(modes), p.rb("CUR_ROOM"), e["X"], e["Y"], e["HP"]))
                    n = p.rb("ANIM_N")                    # animated decor cells step
                    al = p.z.read_memory(S["ANIM_LIST"], 4 * n) if 0 < n <= 12 else b""
                    anim = {(al[i], al[i + 1]) for i in range(0, len(al), 4)}
                    bad = map_structure(p, dst)
                    for scr, fr in (("displayed", p.frame()), ("composed", p.composed_frame())):
                        cells = [(c, r_) for c, r_ in p.bg_mismatch_in(fr) if (c, r_) not in anim]
                        if cells:
                            bad.append((scr, len(cells), cells[:4]))
                    check(f"W21 {tag}: map == model, both screens == map (bar sprites and "
                          "animated decor cells)", bad == [], bad[:3])
                    pit = room_model.field(blk, dst, "RD_PITCOL")
                    if not pit or p.rb("CUR_ROOM") != dst:
                        continue
                    n_pits += 1
                    shown = None
                    for _ in range(32):                  # walk on to the pit
                        e = p.ent(0)
                        if e["Y"] != y0:
                            break
                        tabs = p.bg_tables()
                        fr = p.frame()
                        shown = [(c, p.is_bg(fr, c, F0)) for c in range(pit, pit + 3)
                                 if not e["X"] <= c < e["X"] + kw]
                        p.turn(key)
                    e = p.ent(0)
                    check(f"W21 {tag}: falls only at x == p {pit}, from a visible hole (uncovered "
                          "hole cells == map)", e["Y"] != y0 and e["X"] == pit and shown
                          and all(v for _, v in shown) and tabs[0][F0 * 32 + pit] == S["T_AIR"],
                          (e["X"], e["Y"], shown))
        check("W21 exercised >= 6 storey-0 exits and >= 3 pits", n_exits >= 6 and n_pits >= 3,
              (n_exits, n_pits))
    finally:
        p.proto_start = 1
        p.load()


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = W(h)
        game.GOLDEN_PROTO.append(p)

        def check(tag, cond, detail=""):
            if not h.expect(tag, cond, True):
                fails.append(tag)
                if detail:
                    print(f"[detail] {tag}: {detail}", flush=True)

        def w4(tag):
            bad = p.screen_vs_map(tag)
            check(f"W4 {tag}: displayed == composed == ROOM_MAP (rows 0-17)", bad == [], bad[:3])

        def hero():
            return p.ent(0)

        p.boot(K_KNIGHT)
        kw, kh = game.body(p, K_KNIGHT)          # from kind_tab (after the load)
        # ---------------- W0 rooms ----------------------------------------
        if want("W0") or want("W3"):
            blk = room_model.read_block(p)
            for r in (ROOM_A, ROOM_B, ROOM_C, ROOM_D):
                lad = room_model.segments(blk, r)
                check(f"W0 room {ROOM_LETTER[r]} ladders (ROOM_DESC) == game_lib.ROOM_LADDERS",
                      lad == ROOM_LADDERS[r], (lad, ROOM_LADDERS[r]))
            e = hero()
            check("W0 start: room A, x 2, standing on storey 1 (y = 9+8-h)",
                  (p.rb("CUR_ROOM"), e["X"], e["Y"]) == (0, 2, stand_y(1, kh)), (e["X"], e["Y"]))
            bad = map_structure(p, 0)
            check("W0 room A map structure", bad == [], bad[:4])
            w4("start")
            # (B3B-11: the panel rows 18-23 are W15's)

        # ---------------- W1 walk -----------------------------------------
        if want("W1"):
            p.boot(K_KNIGHT)
            p.isolate()
            xs, ys = [], set()
            for _ in range(6):
                p.turn("L")
                xs.append(hero()["X"])
                ys.add(hero()["Y"])
            for _ in range(3):
                p.turn("H")
                xs.append(hero()["X"])
                ys.add(hero()["Y"])
            check("W1 walk right x 3..8, then left 7..5 (one col per turn)",
                  xs == [3, 4, 5, 6, 7, 8, 7, 6, 5], xs)
            check("W1 y stays 9s+8-h (storey 1)", ys == {stand_y(1, kh)}, ys)
            check("W1 facing left after H", bool(hero()["FLAGS"] & EF_LEFT), "")
            p.place(0, 1, stand_y(1, kh))
            check("W1 wall at col 0 (no left exit in A): no turn", p.no_turn("H"), "")
            w4("walk")

        # ---------------- W2 climb ----------------------------------------
        if want("W2"):
            p.boot(K_KNIGHT)
            p.isolate()
            p.place(0, 5, stand_y(1, kh))           # foot of A's {5,1}
            tc = p.rw("TURN_COUNTER")
            up, stood = [], []
            for _ in range(STOREY_ROWS):
                p.turn("K")
                e = hero()
                up.append(e["Y"])
                stood.append(is_standing(e["Y"], kh))
                if e["PX"] & 7:
                    up.append(("px", e["PX"]))
            y1 = stand_y(1, kh)
            check(f"W2 climb up: one row per turn, {STOREY_ROWS} turns",
                  up == list(range(y1 - 1, y1 - STOREY_ROWS - 1, -1)), up)
            check("W2 standing only at the top (storey 0, y = 8-h)",
                  stood == [False] * (STOREY_ROWS - 1) + [True] and up[-1] == stand_y(0, kh), stood)
            check("W2 TURN_COUNTER += 9", p.rw("TURN_COUNTER") - tc == STOREY_ROWS, p.rw("TURN_COUNTER") - tc)
            check("W2 K at the top of an internal ladder (no up-exit): no turn", p.no_turn("K"), "")
            w4("climb top")
            down = []
            for _ in range(STOREY_ROWS):
                p.turn("J")
                down.append(hero()["Y"])
            check("W2 climb down: one row per turn back to storey 1",
                  down == list(range(stand_y(0, kh) + 1, y1 + 1)), down)
            check("W2 J at the bottom storey, no hole: no turn", p.no_turn("J"), "")
            w4("climb bottom")

        # ---------------- W3 exits L/R/U/D ----------------------------------
        if want("W3"):
            p.boot(K_KNIGHT)
            p.isolate()
            y1, y0 = stand_y(1, kh), stand_y(0, kh)

            def go(key, dest, tag, want_xy):
                pn0 = split_frame(p.frame())[1]
                t0 = p.rw("TURN_COUNTER")
                p.turn(key)
                p.until(lambda: p.rb("CUR_ROOM") == dest and p.idle()
                        and p.rb("GAME_STATE") == GS_PLAYING, 600)
                p.settle()
                e = hero()
                check(f"W3 {tag}: CUR_ROOM {ROOM_LETTER[dest]}, arrival (x, y) = {want_xy}",
                      (p.rb("CUR_ROOM"), e["X"], e["Y"]) == (dest, *want_xy),
                      (p.rb("CUR_ROOM"), e["X"], e["Y"]))
                check(f"W3 {tag}: exit took one turn", p.rw("TURN_COUNTER") - t0 == 1,
                      p.rw("TURN_COUNTER") - t0)
                pn1 = split_frame(p.frame())[1]
                # the panel is never scrolled; only the room-letter HUD row 23 may
                # change (split_frame: 6 rows x 256 bitmap B, then 6 x 32 attrs)
                rows_18_22 = lambda b: b[:5 * 256] + b[6 * 256:6 * 256 + 5 * 32]
                check(f"W3 {tag}: panel rows 18-22 unchanged by the transition",
                      rows_18_22(pn0) == rows_18_22(pn1), "")
                bad = map_structure(p, dest)
                check(f"W3 {tag}: room {ROOM_LETTER[dest]} map == the spec model", bad == [], bad[:4])
                w4(tag)
                p.isolate()

            p.place(0, 32 - 1 - kw, y1)             # A, right edge of storey 1
            go("L", 1, "R exit A->B", (1, y1))
            p.place(0, 24, y1)                      # B: down-exit {24,2}
            go("J", ROOM_C, "D exit B->C", (24, y0))
            go("K", 1, "U exit C->B", (24, y1))
            p.place(0, 1, y1)
            go("H", 0, "L exit B->A", (32 - 1 - kw, y1))
            # C <-> D on storey 1: via B -> C again
            p.place(0, 32 - 1 - kw, y1)
            go("L", 1, "R exit A->B (2)", (1, y1))
            p.place(0, 24, y1)
            go("J", ROOM_C, "D exit B->C (2)", (24, y0))
            # C's left exit is on storey 1, behind the D|C door (B3B-5: starts
            # closed): bump it open from x = 2 (1 turn), step into it, exit
            p.place(0, 2, y1, flags=EF_ACTIVE | EF_PLAYER | EF_LEFT)
            t0 = p.rw("TURN_COUNTER")
            p.turn("H")
            check("W3 C: bump opens the D|C door (1 turn, no move)",
                  (p.rw("TURN_COUNTER") - t0, hero()["X"],
                   p.rb(S["EDGE_TAB"] + S["EDGE_DC"]) & S["EG_OPEN"]) == (1, 2, S["EG_OPEN"]),
                  (p.rw("TURN_COUNTER") - t0, hero()["X"], p.rb(S["EDGE_TAB"] + S["EDGE_DC"])))
            p.turn("H")
            go("H", ROOM_D, "L exit C->D", (32 - 1 - kw, y1))
            go("L", ROOM_C, "R exit D->C", (1, y1))

        # ================= B3B-5: doors, pits, blocks, jump ================
        import budget                                 # Stepper: per-tick T-states
        y1, y0 = stand_y(1, kh), stand_y(0, kh)
        HERO_R = EF_ACTIVE | EF_PLAYER
        MON_L = EF_ACTIVE | EF_HOSTILE | EF_LEFT
        MON_R = EF_ACTIVE | EF_HOSTILE
        SLOT_RAT, SLOT_GOBLIN, SLOT_BATB = 1, 3, 4
        NOWHERE = 7
        e_ab = S["EDGE_TAB"] + S["EDGE_AB"]
        LINK, DOOR, OPEN, LOCK = S["EG_LINK"], S["EG_DOOR"], S["EG_OPEN"], S["EG_LOCK"]
        pit = S["PIT_B"]
        worst = {}

        def planks(c0=32 - S["DOOR_COLS"], s_=1):
            m = p.z.read_memory(S["ROOM_MAP"], MAP_LEN)
            return {(c, r): m[r * 32 + c] for c in (c0, c0 + 1)
                    for r in range(STOREY_ROWS * s_ + 2, STOREY_ROWS * s_ + STOREY_AIR)}

        def closed(pl, c0=32 - S["DOOR_COLS"]):
            return all(t == (S["T_DOOR_L"] if c == c0 else S["T_DOOR_R"]) for (c, _), t in pl.items())

        def is_open(pl, c0=32 - S["DOOR_COLS"]):
            """B10: an open door's opening rows show the jambs (non-solid)."""
            return all(t == (S["T_DOOR_JAMB_L"] if c == c0 else S["T_DOOR_JAMB_R"])
                       for (c, _), t in pl.items())

        def measured(tag, *keys):
            """One turn under budget.Stepper: worst tick, its read_turn_input."""
            st = budget.Stepper(p)
            n0 = len(st.ticks)
            st.turn(*keys)
            st.close()
            ticks = st.ticks[n0:]
            tot, split = max(ticks, key=lambda x: x[0])
            inp = max(sp.get("read_turn_input", 0) for _, sp in ticks)
            worst[tag] = (tot, inp)
            print(f"[info] {tag}: worst tick {tot} T, input phase max {inp} T"
                  f" ({len(ticks)} ticks)", flush=True)
            check(f"{tag}: worst tick <= 126k T (3B budget)", tot <= 126000, tot)

        def enter_b():
            p.boot(K_KNIGHT)
            p.isolate()
            p.place(0, 32 - 1 - kw, y1)
            p.turn("L")
            p.until(lambda: p.rb("CUR_ROOM") == 1 and p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
            p.settle()
            p.isolate()

        def stub_step(slot, dx, dy=0, yld=0):
            """try_step(IX = slot, D = dx, E = dy) in place (lowram spare),
            YIELD_FLAG = yld during the call; MSG_BUF = $FF if it returned
            CF = 1. Entered from the wait_tick probe, so play resumes there
            afterwards (PC put back; no register is live across that call)."""
            def w(v):
                return [v & 0xFF, v >> 8]
            pc0 = p.pc()
            code = ([0xCD] + w(S["build_live"]) + [0xCD] + w(S["cache_player"]) +
                    [0x3E, slot, 0x32] + w(S["ACT_SLOT"]) +
                    [0x3E, yld, 0x32] + w(S["YIELD_FLAG"]) +
                    [0xDD, 0x21] + w(S["P_ENTITIES"] + 32 * slot) +
                    [0x16, dx & 0xFF, 0x1E, dy & 0xFF, 0xCD] + w(S["try_step"]) +
                    [0x9F, 0x32] + w(S["MSG_BUF"]) +
                    [0xAF, 0x32] + w(S["YIELD_FLAG"]))
            ok = p.run_stub(code, org=S["LOWRAM_END_3B"])
            check(f"W9 stub (slot {slot}) ran", ok, "")
            p.z.cmd("set-register PC=%d" % pc0)
            return p.rb("MSG_BUF")

        # ---------------- W5 door: close (C), bump opens, shared state -----
        if want("W5"):
            p.boot(K_KNIGHT)
            p.isolate()
            check("W5 A|B door starts open (LINK|DOOR|OPEN), jambs in A (B10)",
                  (p.rb(e_ab), is_open(planks())) == (LINK | DOOR | OPEN, True), p.rb(e_ab))
            p.place(0, 27, y1, flags=HERO_R)          # adjacent: x + w = 30, facing it
            t0 = p.rw("TURN_COUNTER")
            measured("W5 close (C)", "C")
            check("W5 C closes it: 1 turn, OPEN cleared, planks T_DOOR_L/R",
                  (p.rw("TURN_COUNTER") - t0, p.rb(e_ab), closed(planks())) == (1, LINK | DOOR, True),
                  (p.rw("TURN_COUNTER") - t0, p.rb(e_ab)))
            p.settle()
            w4("W5 closed")
            t0 = p.rw("TURN_COUNTER")
            measured("W5 bump open (L)", "L")
            e = hero()
            check("W5 bump opens it: 1 turn, no move, OPEN set, jambs (B10)",
                  (p.rw("TURN_COUNTER") - t0, e["X"], p.rb(e_ab), is_open(planks()))
                  == (1, 27, LINK | DOOR | OPEN, True), (p.rw("TURN_COUNTER") - t0, e["X"], p.rb(e_ab)))
            p.settle()
            w4("W5 opened")
            p.turn("L")
            check("W5 into the open door: x 28", hero()["X"] == 28, hero()["X"])
            p.turn("L")
            p.until(lambda: p.rb("CUR_ROOM") == 1 and p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
            p.settle()
            pl = planks(0)
            check("W5 B after the exit: the shared door shows open (cols 0-1 jambs, arch, lintel)",
                  is_open(pl, 0) and p.rb(S["ROOM_MAP"] + 10 * 32) == S["T_DOOR_ARCH_L"]
                  and p.rb(S["ROOM_MAP"] + 9 * 32 + 1) == S["T_BRICK"], pl)
            bad = map_structure(p, 1)
            check("W5 room B map structure (door open, pit)", bad == [], bad[:4])
            w4("W5 B")

        # ---------------- W6 locked ----------------------------------------
        if want("W6"):
            p.boot(K_KNIGHT)
            p.isolate()
            p.place(0, 27, y1, flags=HERO_R)
            p.turn("C")
            p.wb(e_ab, LINK | DOOR | LOCK)
            check("W6 bump on a locked door: no turn", p.no_turn("L"), "")
            check("W6 locked door unchanged (state, planks, hero x)",
                  (p.rb(e_ab), closed(planks()), hero()["X"]) == (LINK | DOOR | LOCK, True, 27),
                  (p.rb(e_ab), hero()["X"]))
            got = log_row(p.composed_frame(), 23)
            check("W6 the newest log row shows THE DOOR IS LOCKED", got == text6("THE DOOR IS LOCKED"), "")
            p.wb("INPUT_REPEAT", 1)                    # held: printed once per press
            t0 = p.rw("TURN_COUNTER")
            p.hold("L")
            p.tick(2)
            shown = p.rb("LOCK_SHOWN")
            p.release()
            p.tick(2)
            check("W6 locked message latched while held (LOCK_SHOWN 1), cleared on release, no turn",
                  (shown, p.rb("LOCK_SHOWN"), p.rw("TURN_COUNTER") - t0) == (1, 0, 0),
                  (shown, p.rb("LOCK_SHOWN")))
            p.wb("INPUT_REPEAT", 0)
            p.place(0, 10, y1, flags=HERO_R)
            p.place(SLOT_GOBLIN, 27, stand_y(1, 4), room=0, flags=MON_R)
            r = stub_step(SLOT_GOBLIN, 1)
            check("W6 opener vs a locked door: refused, door unchanged",
                  (r, p.rb(e_ab), closed(planks()), p.ent(SLOT_GOBLIN)["X"]) == (0, LINK | DOOR | LOCK, True, 27),
                  (r, p.rb(e_ab)))

        # ---------------- W7 close refusals --------------------------------
        if want("W7"):
            p.boot(K_KNIGHT)
            p.isolate()
            p.place(0, 27, y1, flags=HERO_R)
            p.place(SLOT_BATB, 29, STOREY_ROWS, room=0, flags=MON_L)   # in the door's lintel/arch cells
            check("W7 C with a body in the door cells: no turn, still open",
                  p.no_turn("C") and p.rb(e_ab) == LINK | DOOR | OPEN, p.rb(e_ab))
            p.place(SLOT_BATB, 10, STOREY_ROWS, room=NOWHERE)
            p.place(0, 26, y1, flags=HERO_R)
            check("W7 C not adjacent (x + w = 29): no turn", p.no_turn("C"), "")
            p.place(0, 27, y1, flags=HERO_R | EF_LEFT)
            check("W7 C facing away: no turn", p.no_turn("C"), "")
            p.place(0, 27, y1, flags=HERO_R)
            check("W7 C adjacent, facing, free: closes (1 turn)",
                  p.turn("C") and p.rb(e_ab) == LINK | DOOR, p.rb(e_ab))
            check("W7 C on a closed door: no turn", p.no_turn("C"), "")
            # designer 2026-10-03: a PENDING body in the door cells blocks the
            # close; a living hostile within 2 cols of the hero or the door too
            p.turn("L")                                # bump: open again
            p.place(SLOT_GOBLIN, 29, stand_y(1, 4) - 4, room=0, flags=EF_ACTIVE | EF_PENDING)  # not hostile
            check("W7 C with a PENDING body in the door cells: no turn",
                  p.no_turn("C") and p.rb(e_ab) == LINK | DOOR | OPEN, p.rb(e_ab))
            p.set_ent(SLOT_GOBLIN, ROOM=NOWHERE)
            p.place(SLOT_RAT, 21, stand_y(1, 2), room=0, flags=MON_R)   # cols 21-24: gap 2
            check("W7 C with a hostile 2 cols from the hero: no turn", p.no_turn("C"), "")
            p.place(SLOT_RAT, 20, stand_y(1, 2), room=0, flags=MON_R)   # gap 3
            check("W7 C with the nearest hostile 3 cols away: closes",
                  p.turn("C") and p.rb(e_ab) == LINK | DOOR, p.rb(e_ab))
            p.set_ent(SLOT_RAT, ROOM=NOWHERE)
            p.settle()
            w4("W7 closed")

        # ---------------- W8 pit fall + jump --------------------------------
        if want("W8"):
            enter_b()
            bad = map_structure(p, 1)
            check("W8 room B map: pit holes 20-22 AIR, caps 19 / 23", bad == [], bad[:4])
            hp0 = hero()["HP"]
            p.place(0, pit + 1, y0, flags=HERO_R | EF_LEFT)
            t0 = p.rw("TURN_COUNTER")
            samples = []
            p.sample_during_turn("H", lambda fr, e: samples.append((e["PX"], e["PY"], e["MODE"])))
            e = hero()
            check("W8 fall: x == p, lands standing on storey 1, 1 turn",
                  (e["X"], e["Y"], p.rw("TURN_COUNTER") - t0, e["MODE"], p.rb("CUR_ROOM"))
                  == (pit, y1, 1, 0, 1), (e["X"], e["Y"], p.rw("TURN_COUNTER") - t0, e["MODE"]))
            check("W8 fall: 1d4 damage", 1 <= hp0 - e["HP"] <= 4, (hp0, e["HP"]))
            drop = [(px, py) for px, py, _ in samples if py != 8 * y0]
            check("W8 drop: px = 8p throughout, py steps of 8 down to storey 1 (9 ticks)",
                  [py for _, py in drop if py < 8 * y1] + [8 * y1] == list(range(8 * y0 + 8, 8 * y1 + 1, 8))
                  and all(px == 8 * pit for px, _ in drop), samples)
            p.settle()
            w4("W8 landed")
            check("W8 no soft-lock: the hero walks on after the fall",
                  p.turn("L") and hero()["X"] == pit + 1, hero()["X"])
            # a monster in the landing box goes PENDING in place
            p.place(0, pit + 1, y0, flags=HERO_R | EF_LEFT)
            p.place(SLOT_GOBLIN, pit, stand_y(1, 4), room=1, flags=MON_L)
            p.turn("H")
            g = p.ent(SLOT_GOBLIN)
            check("W8 landing box occupied: that monster PENDING in place",
                  (bool(g["FLAGS"] & EF_PENDING), g["X"], hero()["Y"]) == (True, pit, y1),
                  (g["FLAGS"], g["X"], hero()["Y"]))
            p.settle()
            w4("W8 pending")
            for _ in range(4):
                p.turn("L")
            check("W8 the pending monster materialises once the box is free",
                  not p.ent(SLOT_GOBLIN)["FLAGS"] & EF_PENDING, p.ent(SLOT_GOBLIN)["FLAGS"])
            # jump (game.md §2.4) over the pit
            p.isolate()
            p.place(0, pit - 4, y0, flags=HERO_R)
            t0 = p.rw("TURN_COUNTER")
            samples = []
            ok = p.turn("K", "L", per_tick=lambda fr, e: samples.append((e["PX"], e["PY"])))
            e = hero()
            rise = [py - 8 * y0 for _, py in samples if py != 8 * y0]
            check("W8 jump K+L: x + 6 over the pit, standing on storey 0, 1 turn",
                  (ok, e["X"], e["Y"], p.rw("TURN_COUNTER") - t0, e["MODE"]) == (True, pit + 2, y0, 1, 0),
                  (ok, e["X"], e["Y"], p.rw("TURN_COUNTER") - t0))
            check("W8 jump arc: py offsets -4,-8,-12,-16 x5,-12,-8,-4 (px 4 px/tick)",
                  rise == [-4, -8, -12, -16, -16, -16, -16, -16, -12, -8, -4], samples)
            check("W8 jump refused on the next turn", p.no_turn("K", "L"), "")
            p.turn("SPACE")
            measured("W8 jump", "K", "L")
            check("W8 jump again after a non-jump turn: x + 6", hero()["X"] == pit + 8, hero()["X"])
            p.place(0, pit - 6, y0, flags=HERO_R)
            check("W8 jump onto x == p refused (no turn)", p.no_turn("K", "L"), "")
            p.place(0, pit + 1, y0, flags=HERO_R | EF_LEFT)
            measured("W8 fall", "H")
            # more jump legality (game.md §2.4)
            p.isolate()
            p.place(0, pit + 5, y0, flags=HERO_R | EF_LEFT)
            check("W8 jump left (K+H): x - 6", p.turn("K", "H") and hero()["X"] == pit - 1, hero()["X"])
            p.turn("SPACE")
            p.place(0, 6, y0, flags=HERO_R | EF_LEFT)
            check("W8 jump to x' = 0 refused", p.no_turn("K", "H"), "")
            p.place(0, 7, y0, flags=HERO_R | EF_LEFT)
            check("W8 jump to x' = 1 allowed", p.turn("K", "H") and hero()["X"] == 1, hero()["X"])
            p.turn("SPACE")
            p.place(0, 23, y0, flags=HERO_R)
            check("W8 jump to x' + w > 31 refused", p.no_turn("K", "L"), "")
            p.place(0, pit - 4, y0, flags=HERO_R)
            p.place(SLOT_GOBLIN, pit - 1, stand_y(0, 4), room=1, flags=MON_L)
            check("W8 jump refused: a tall body (goblin) in the swept box", p.no_turn("K", "L"), "")
            p.set_ent(SLOT_GOBLIN, ROOM=NOWHERE)
            p.place(2, pit - 1, stand_y(0, 2), room=1, flags=MON_L)          # the slime
            check("W8 jump over a Slime (low body) allowed",
                  p.turn("K", "L") and hero()["X"] == pit + 2, hero()["X"])
            p.set_ent(2, ROOM=NOWHERE)
            # a wall / dead-end block in the swept box (room D, block cols 29-31, s0)
            p.boot(K_KNIGHT)
            p.isolate()
            p.place(0, 32 - 1 - kw, y1)
            p.turn("L")
            p.until(lambda: p.rb("CUR_ROOM") == 1 and p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
            p.isolate()
            p.place(0, 24, y1)
            p.turn("J")
            p.until(lambda: p.rb("CUR_ROOM") == ROOM_C and p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
            p.isolate()
            p.place(0, 2, y1, flags=HERO_R | EF_LEFT)
            for _ in range(3):
                p.turn("H")
            p.until(lambda: p.rb("CUR_ROOM") == ROOM_D and p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
            p.isolate()
            check("W8 reached room D", p.rb("CUR_ROOM") == ROOM_D, p.rb("CUR_ROOM"))
            p.place(0, 22, y0, flags=HERO_R)
            check("W8 jump refused: the dead-end block in the swept box", p.no_turn("K", "L"), "")
            p.place(0, 26, y0, flags=HERO_R)               # cols 26-28 (rubble at 28: decor)
            check("W8 walk into the block: no turn", p.no_turn("L") and hero()["X"] == 26, hero()["X"])
            # a fall at 1 HP kills
            enter_b()
            p.place(0, pit + 1, y0, flags=HERO_R | EF_LEFT)
            p.set_ent(0, HP=1)
            p.turn("H")
            check("W8 fall at 1 HP: GS_DEAD", p.wait_state(GS_DEAD, 200), p.rb("GAME_STATE"))

        # ---------------- W9 walkers vs pits, flyers, openers ---------------
        if want("W9"):
            enter_b()
            p.place(SLOT_RAT, pit + 3, stand_y(0, 2), room=1, flags=MON_L)
            xs = []
            for _ in range(10):
                p.turn("SPACE")
                xs.append(p.ent(SLOT_RAT)["X"])
            check("W9 rat patrol on storey 0 never steps onto x == p (reverses at p+1)",
                  pit not in xs and min(xs) == pit + 1, xs)
            p.place(SLOT_RAT, 10, stand_y(0, 2), room=NOWHERE)
            p.place(SLOT_BATB, pit + 3, stand_y(0, 2), room=1, flags=MON_L)
            xs = []
            for _ in range(8):
                p.turn("SPACE")
                xs.append(p.ent(SLOT_BATB)["X"])
            check("W9 bat flies over the pit (x == p and beyond)", pit in xs and min(xs) < pit, xs)
            p.settle()
            w4("W9 B")
            # closed door + openers (try_step unit stubs, room A)
            p.boot(K_KNIGHT)
            p.isolate()
            p.place(0, 27, y1, flags=HERO_R)
            p.turn("C")
            p.place(0, 10, y1, flags=HERO_R)
            p.place(SLOT_RAT, 26, stand_y(1, 2), room=0, flags=MON_R)
            r = stub_step(SLOT_RAT, 1)
            check("W9 non-opener (rat) at a closed door: blocked, door closed",
                  (r, p.rb(e_ab), p.ent(SLOT_RAT)["X"]) == (0, LINK | DOOR, 26), (r, p.rb(e_ab)))
            p.set_ent(SLOT_RAT, ROOM=NOWHERE)
            p.set_ent(SLOT_BATB, ROOM=0, X=27, Y=stand_y(1, 2), PX=27 * 8, PY=stand_y(1, 2) * 8,
                      FLAGS=MON_R)
            r = stub_step(SLOT_BATB, 1)
            check("W9 flyer (bat) at a closed door: blocked, door closed",
                  (r, p.rb(e_ab), p.ent(SLOT_BATB)["X"]) == (0, LINK | DOOR, 27), (r, p.rb(e_ab)))
            p.set_ent(SLOT_BATB, ROOM=NOWHERE)
            p.set_ent(SLOT_GOBLIN, ROOM=0, X=27, Y=stand_y(1, 4), PX=27 * 8, PY=stand_y(1, 4) * 8,
                      FLAGS=MON_R)
            r = stub_step(SLOT_GOBLIN, 1, yld=1)
            check("W9 opener on a YIELD step: no door opening (blocked)",
                  (r, p.rb(e_ab), p.ent(SLOT_GOBLIN)["X"]) == (0, LINK | DOOR, 27), (r, p.rb(e_ab)))
            r = stub_step(SLOT_GOBLIN, 1)
            check("W9 opener (goblin) at a closed door: opens it, spends the step (no move)",
                  (r, p.rb(e_ab), is_open(planks()), p.ent(SLOT_GOBLIN)["X"])
                  == (0xFF, LINK | DOOR | OPEN, True, 27), (r, p.rb(e_ab)))
            p.settle(4)                                # play resumes: repaint + present
            w4("W9 door opened by the goblin")
            # flyers and the open door's arch / lintel (game.md §9.1, whole body box)
            p.set_ent(SLOT_GOBLIN, ROOM=NOWHERE)
            p.set_ent(SLOT_BATB, ROOM=0, X=27, Y=11, PX=27 * 8, PY=88, FLAGS=MON_R, MODE=0)
            r = stub_step(SLOT_BATB, 1)
            check("W9 bat into the open door's opening rows (11-12): allowed",
                  (r, p.ent(SLOT_BATB)["X"]) == (0xFF, 28), (r, p.ent(SLOT_BATB)["X"]))
            r = stub_step(SLOT_BATB, 0, -1)
            check("W9 bat up into the arch row (col 30 row 10): refused",
                  (r, p.ent(SLOT_BATB)["Y"]) == (0, 11), (r, p.ent(SLOT_BATB)["Y"]))
            p.set_ent(SLOT_BATB, X=27, Y=9, PX=27 * 8, PY=72, MODE=0)
            r = stub_step(SLOT_BATB, 1)
            check("W9 bat sideways into the lintel / arch rows (9-10): refused",
                  (r, p.ent(SLOT_BATB)["X"]) == (0, 27), (r, p.ent(SLOT_BATB)["X"]))
            p.settle(4)
            w4("W9 bat at the door")

        # ========== B3B-R2 review: a monster opens a door inside the bank-3
        # monster phase (try_step -> mon_door -> door_paint -> shadow_rect
        # pages bank 7) — the real resolve_monsters via far3 (W9R) ==========
        if want("W9") or want("W9R"):
            p.boot(K_KNIGHT)
            p.isolate()
            p.place(0, 27, y1, flags=HERO_R)
            p.turn("C")                                 # close the A|B door
            check("W9R A|B door closed", p.rb(e_ab) == LINK | DOOR, p.rb(e_ab))
            p.place(0, 10, y0, flags=HERO_R)            # hero on the other storey
            ktf = S["kind_tab"] + S["KT_FLAGS"] + S["K_GOBLIN"]
            gf = p.rb(ktf)
            p.wb(ktf, gf & ~S["KF_CLIMBER"] & 0xFF)     # patrol (facing) instead of
            gw = game.body(p, S["K_GOBLIN"])[0]         # seeking a ladder: walks into the door
            gx = 32 - S["DOOR_COLS"] - gw
            p.place(SLOT_GOBLIN, gx, stand_y(1, game.body(p, S["K_GOBLIN"])[1]), room=0, flags=MON_R)
            p.place(SLOT_BATB, 20, 1, room=0, flags=MON_L)   # a later slot: must still act
            bx0 = p.ent(SLOT_BATB)["X"]
            probe = S["resolve_monsters.next"]
            p.z.cmd("set-breakpoint 4 PC=%d" % probe)
            p.extra_probes = {probe}
            seen = {}
            p.hold("SPACE")
            for _ in range(12):
                p.tick()
                if p.pc() == probe:
                    seen[p.rb("MON_SLOT")] = p.rb("PORT_7FFD_SHADOW") & 7
                    if 4 in seen:
                        break
            p.release()
            p.z.cmd("set-breakpoint 4")
            p.extra_probes = set()
            p.until(lambda: p.idle(), 100)
            p.wb(ktf, gf)
            check("W9R goblin opened the door through the real monster phase (no move)",
                  (p.rb(e_ab), p.ent(SLOT_GOBLIN)["X"]) == (LINK | DOOR | OPEN, gx), (p.rb(e_ab), p.ent(SLOT_GOBLIN)["X"]))
            check("W9R bank 3 paged after the goblin's door opening (PORT_7FFD_SHADOW & 7 == 3), "
                  "the phase continued to slot 4", seen.get(SLOT_GOBLIN) == 3 and seen.get(SLOT_BATB) == 3, seen)
            check("W9R the bat (slot 4, after the goblin) acted", p.ent(SLOT_BATB)["X"] != bx0,
                  (bx0, p.ent(SLOT_BATB)["X"]))
            p.settle(4)
            w4("W9R door opened in the monster phase")

        # ================= B3B-10: animated decor (W14) =====================
        if want("W14"):
            w14(p, check)

        # ================= B3B-11: panel engine (W15) =====================
        if want("W15"):
            w15(p, check)

        # ================= B3B-13: token text (W17) ======================
        if want("W17"):
            w17(p, check)

        # ================= B11: storey-0 exits, invisible pit (W21) ========
        if want("W21"):
            w21_exits(p, check)

        # ================= B3B-12: level change (W16) =======================
        if want("W16"):
            w16_level(p, check)

        # ================= B3B-8: generated rooms + level themes ===========
        if want("W11") or want("W12") or want("W12M") or want("W13"):
            run_gen_suites(p, check)

        if worst:
            print("[info] B3B-5 measured: " + ", ".join(f"{k} {v[0]} T (input {v[1]})"
                                                       for k, v in worst.items()), flush=True)
        print(f"[info] run anomalies (returns outside a probe): {game.Proto.anomalies}", flush=True)
        check("harness: no run anomalies", game.Proto.anomalies == 0, game.Proto.anomalies)
    print(f"[{'FAIL' if fails else 'PASS'}] world W0-W4: {len(fails)} failing: {fails[:8]}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
