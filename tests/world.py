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
  C3-0 (bank-1 UI code, far1):
  W18 a target in free bank 1 entered via far1 from a stub with bank 0 paged:
      bank 1 paged + A passed in it; still bank 1 after msg_push (queued),
      copy_virt3 (from virtual $C000: pages bank 3) and a nested far1; back in
      the stub bank 0 is paged and the target's BC / DE / HL passed through.
  C3-1 (read_stick, game.md §3.1 / §3.2):
  W19 each source — default KEYTAB (Q/A/O/P/SPACE), a redefined KEYTAB
      (M/Z/V/T/ENTER: half-rows $7F/$FE/$FB/$BF), Sinclair 1 (6-0), Sinclair 2
      (1-5), Kempston via JOY_MIRROR — gives STICK == the one JOY bit for each
      of R/L/D/U/F, PLAYER_DIR == STICK & $0F, FIRE never sets DK_WAIT (C3-8a:
      FIRE is intent_tick's, the PROTO "FIRE = wait" went with legacy_input); keys stay live
      (ORed) with every joystick; (the PROTO H/J/K/L aliases are gone, C3-8a); shortcuts 1-0 / I /
      BREAK -> PLAYER_SC, a Sinclair half turns off its 1-0 shortcuts (and
      DK_1..3 for Sinclair 2); JOY_MIRROR is ignored unless JM_KEMPSTON, and
      with INPUT_SRC = 0 the IN ($1F) is reached only in JM_KEMPSTON; a
      Kempston byte with bits 5-7 set is ignored; read_stick T per mode;
      STICK follows every tick (ANIM too); BREAK masks FIRE; hero select
      works in JM_SINC2.
  C3-2 (turn-intent machine; game.md §2.3 / §3.1 / §3.5):
  W22 FIRE tap (release < 10 ticks) uses the icon on release; a longer hold
      or FIRE + a direction does not; ICON MODE (C3-2b, game.md §3.1): DOWN +
      FIRE either first within 3 ticks enters it (no turn, play frozen: timers
      held, slot inverse, info line '>' prefix), R/L move the cursor at once,
      after 10 ticks, then every 4 (unlearned / empty skipped, wrap), 1-0
      jump, FIRE on a greyed icon refuses and stays, BREAK / UP leave (no
      pause), a turn-costing use (potion) returns to play; FIRE + UP = pause
      request; BREAK priority; DOWN alone waits 3 ticks (a shorter tap commits
      on release); a reverse tap only turns (0 turns), a held reverse key
      walks after 10 ticks; DOWN with no ladder = wait; a low diagonal acts
      as the side; '.' waits; shortcuts select (unlearned: NOT LEARNED).
  W23 icon use: melee attacks the faced monster / closes the faced door /
      else NO TARGET (no turn); quick potion drinks (1 turn) then NO POTION;
      Bow / food / scroll / Bag / daggers-at-0 refusals print their line and
      cost no turn; ENTER uses the icon (Bag: the page, 3E-T2); I = the page; the FIRE melee tick's
      T vs the 126k budget.
  C3-6 (bank 1 menu1.asm):
  W24 menu golden (no cursor); digits-only controls / hero (C3-6b);
      redefine (duplicates refused, KEYTAB written when complete); seed
      entropy (MENU_SPIN) vs seed_fixed; pause overlay restored byte for
      byte, QUIT asks Y/N; the death card (menu font), digit-after-release back to menu.
  W20 stack low-water: $BD00..$BEFF pattern-filled before boot, then boot,
      a generated D1 start and 80 seeded random turns (walk / climb / jump /
      wait, fights, exits); the lowest byte touched must leave >= 512 B of
      the 768-B stack unused (reports the measured max depth).
  B11 (user bug: the hero fell a storey where the floor is drawn, walking
  into the left room):
  W21 generated D1s (seed_fixed, 2 masters): every storey-0 horizontal exit,
      both ways: the exit turn never enters M_FALL, the hero arrives standing
      on storey 0 at x = 1 / 31-w with its HP, the new room's map == model and
      both screens == map; then walking on, the hero falls only at x == the
      pit col, onto a hole the screen shows (before the fix a left-exit step
      landed on x == 0 == "no pit" RD_PITCOL and dropped the hero).

  L2 (game.md §1.1 "Mid-room block" / "Wide pit", §2.4 / §2.5):
  W26 Python: room_model maps of a D2-D8 seed sweep == levelcheck's storey-0
      divider model (walk components, fall x = p .. p+W-3). Emulator, forced L2
      rooms (W 4/5/6, w 2/3): map == model, screens == map (bar animated
      decor cells), the hero falls only
      over the span (walk from both sides, cut-short jumps), walkers refuse it,
      a flyer crosses; the mid-block stops walking and jumping from both faces
      and walkers; re-entry byte-identical.

Usage: ZRCP_PORT=10001 python3 tests/world.py [W1 W3 W11 ...] [--update-golden [--png DIR]]
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_argv = sys.argv[1:]
sys.argv = [sys.argv[0], "999"]               # keep game.py's item filter inert
import game  # noqa: E402
import room_model  # noqa: E402
import game_lib  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import textpack  # noqa: E402
STRINGS = textpack.read_strings()           # [(name, text)], id order (B3B-13)
from game_lib import (Harness, S, EMU_ARGS, attr_at, cell_bytes, split_frame,  # noqa: E402
                      stand_y, is_standing, item_row, ladder_rows, ROOM_LADDERS,
                      ROOM_A, ROOM_B, ROOM_C, ROOM_D, ROOM_LETTER,
                      STOREY_ROWS, STOREY_AIR, STOREY_COUNT, PLAY_ROWS, PANEL_ROW,
                      MAP_LEN, GS_PLAYING, GS_DEAD, GS_SELECT, K_KNIGHT, K_WIZARD, EF_LEFT, EF_ACTIVE,
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
        drip = game_lib.drip_cells(self)             # D3-8b: screen-only overlay
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
                    if (attr_at(f, c, r) != a or bytes(cell_bytes(f, c, r)) != g) \
                            and not game_lib.drip_shown(f, drip, c, r):
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


DECOR_MOUNT = {"TORCH_TALL", "TORCH_SLIM", "WINDOW_ARCH", "WINDOW_BAR", "BANNER", "BANNER_TALL",
               "BOOKSHELF"}
DECOR_CEIL = {"CHAIN", "MOSS"}
DECOR_FLOOR = {"BONES", "CAULDRON", "BRAZIER", "BRAZIER_BIG"}
BONES_DEPTHS = {3: 2, 4: 3, 5: 2, 7: 3, 8: 2}      # DEC1 (concept-screen 3.3): depth -> gate 1 in n
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
        objs["BONES"] = {(0, k): T[f"T_BONES_{k}"] for k in range(4)}      # DEC1: ids 13 / 15 / 16 / 31
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
    drip = {T["T_DAGGERS"], T["T_ARROWS"]}                         # D3-7 T6: the drips are gone
    floorish = lambda t: t in (T["T_PLAT"], T["T_WALLF"])          # noqa: E731
    for j in ch:                                                    # per cell: base class vs solidity
        c, row = j % 32, j // 32
        if m[j] in drip:
            errs.append(("the deriver placed an ammo floor glyph (17 / 18: no drips since D3-7 T6)", c, row))
            continue
        nm = names.get(m[j])
        if nm is None:
            errs.append(("unknown decor id", c, row, m[j]))
            continue
        if nm in DECOR_BRICK:
            errs.append(("pillar (wall-class decor) must not be placed: no decor on walls", c, row))
        patch = nm in DECOR_PATCH
        want_base = T_AIR                           # user 2026-10-12: never on a wall / block cell
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
        if nm == "BONES" and d not in BONES_DEPTHS:
            errs.append(("bones on a depth without a Skeleton-family pool (only D3 D4 D5 D7 D8)", c, row))
        if nm in DECOR_FLOOR:
            pass                                    # floor class: exempt from the 2-rows-above rule
        elif row % 9 > 5:
            errs.append((f"{nm} in the 2 rows above a floor / floor row", c, row))
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                rr, cc = row + dr, c + dc
                if 0 <= rr < 18 and 0 <= cc < 32 and base[rr * 32 + cc] in lad:
                    errs.append(("decor adjacent to a ladder", c, row))
    # components (8-connected): one whole object each, by class
    cells = {j for j in ch if m[j] not in drip and m[j] in names}
    seen, ncob, npatch_cells, npatch, nbones = set(), 0, 0, 0, 0
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
            if nm == "BONES":
                nbones += 1
                if len(comp) != 4 or r0 != r1 or r1 % 9 != 7:
                    errs.append(("bones: one 4 x 1 pile on the standing row", c0, r0))
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
    if nbones > 1:
        errs.append(("more than 1 bones pile in a room", nbones))
    sizes["bones"] = sizes.get("bones", 0) + nbones
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
        if e[2] < 16 and e[2] != 1:
            errs.append(("attr-cycle kind not 1 (DEC1: no candles)", e))
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
    if gl and not nlarge:
        errs.append(("glyph-swap entries without a large object", gl[:2]))
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


def bank_bytes(p, bank, addr, n):
    p.z.cmd("set-memory-zone 0")
    try:
        return bytes(p.z.read_memory(bank * 16384 + addr - 0xC000, n))
    finally:
        p.z.cmd("set-memory-zone -1")


def menu_text_ok(p, fr, row, col, txt):
    """C3-6: txt drawn in the 8x16 menu font (bank-1 menu_font / _map) at
    cell (col, row): each char = 2 cells (rows row, row+1), 1 col."""
    fmap = bank_bytes(p, 1, S["menu_font_map"], 64)
    font = bank_bytes(p, 1, S["menu_font"], S["MENU_FONT_COUNT"] * 16)
    for i, ch in enumerate(txt):
        g = fmap[ord(ch) - 32]
        g = 0 if g == 0xFF else g
        gl = font[g * 16:g * 16 + 16]
        if bytes(cell_bytes(fr, col + i, row)) != gl[:8] or bytes(cell_bytes(fr, col + i, row + 1)) != gl[8:]:
            return False
    return True


def shadow_bitmap(p):
    """D3-S2: there is no bitmap shadow — erase_rect redraws ROOM_MAP glyphs
    (+ the row-17 ornament) — so the 'virtual shadow' (6,144 B, screen layout)
    is that model. Its old home, bank 7 B7_CODE..B7_LIMIT, now holds the
    bank-7 cold code: it must still equal the .sna image (AssertionError
    otherwise: something wrote the code / its unused tail)."""
    import game_lib
    lo, n = S["B7_CODE"], S["B7_LIMIT"] - S["B7_CODE"]
    raw = bank7(p, lo, n)
    img = game_lib.SNA_RAM[7 * 16384 + lo - 0xC000:7 * 16384 + lo - 0xC000 + n]
    bad = [i for i in range(n) if raw[i] != img[i]]
    assert not bad, f"D3-S2: bank-7 code area written at {[hex(lo + i) for i in bad[:4]]}"
    tabs = p.bg_tables()
    bm = bytearray(6144)
    for r in range(PLAY_ROWS):
        for c in range(32):
            g, _ = room_model.expected_cell(*tabs, c, r)
            for ln in range(8):
                bm[((r & 0x18) << 8) | ((r & 7) << 5) | c | (ln << 8)] = g[ln]
    return bytes(bm)


def snapshot(p):
    """ROOM_MAP + bank-5 screen + screen 2 + the (virtual) shadow's rows 0-17."""
    sh = shadow_bitmap(p) + bank7(p, S["SHADOW_ATTR"], 32 * PLAY_ROWS)
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
    TXT = {"str_" + n: t for n, t in STRINGS if n in ("descend", "locked", "fall", "died", "quaff")}
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
    # C3-8a: quaff = the potion slot selected (key 7: selects only), then a FIRE tap;
    # the turn starts in the tick that sees FIRE released (the "input tick").
    p.select_slot(6)
    p.settle(4)                                   # the cursor / info line repaint is done
    before = panel(p.composed_frame())
    tc0 = p.rw("TURN_COUNTER")
    p.hold("FIRE")
    p.tick()
    p.release()
    p.tick()
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
    push("str_descend", "str_locked", "str_fall")
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
    push("str_descend", "str_locked", "str_fall", "str_quaff")
    stub([0x3E, MSG["str_died"], 0xCD] + w(S["msg_push_end"]), "msg_push_end")
    check("W15 ring full: log_push_end replaces the newest pending (LOG_QN 4, LQ_DROP 1)",
          (p.rb("LOG_QN"), p.rb(S["LOG_Q"] + S["LQ_DROP"])) == (4, 1), "")
    p.until(drained, 12)
    p.tick()
    check("W15 log_push_end: newest shown = YOU DIED (after THE FALL line)",
          (log_row(p.frame(), 22), log_row(p.frame(), 23)) == (text6(TXT["str_fall"]), text6(TXT["str_died"])), "")
    p.wb(S["LOG_Q"] + S["LQ_DROP"], 0)

    # --- ring overflow -----------------------------------------------------
    push("str_descend", "str_locked", "str_fall", "str_quaff", "str_died")
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
    check("W15 2nd-frame small item (HP) <= 5.2k T (worst 2nd-frame pre-panel ~117k + 5.2k < 126k cap; C3-3: + icon_poll ~0.1k)",
          t_hp2 <= 5200, t_hp2)
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


def w18(p, check):
    """C3-0: far1 + "helpers hand $C000 back as they found it" from bank-1 code
    (the B3B-R2 W9R pattern for bank 1). The target is copied into free bank 1
    (ui1_end..) by the stub, entered through far1 with bank 0 paged."""
    STUB = S["LOWRAM_END_3B"]
    w = w16
    SH, RES = S["PORT_7FFD_SHADOW"], S["MSG_BUF"]
    T = S["ui1_end"]                      # free bank-1 RAM at runtime (C3-0: ui1 empty)
    RET = T + 0x80                        # a lone RET: the nested far1's target
    DATA = STUB + 0x100
    SID = 0
    tgt = ([0x32] + w(RES) +                                       # ld (RES+0),a: the arg
           [0x3A] + w(SH) + [0x32] + w(RES + 1) +                  # bank inside the target
           [0x3A] + w(RES) + [0xCD] + w(S["msg_push"]) +
           [0x3A] + w(SH) + [0x32] + w(RES + 2) +
           [0x21] + w(0xC000) + [0x11] + w(S["GEN_SRC"]) +         # virtual $C000 = bank 3
           [0x01] + w(8) + [0xCD] + w(S["copy_virt3"]) +
           [0x3A] + w(SH) + [0x32] + w(RES + 3) +
           [0x21] + w(RET) + [0xCD] + w(S["far1"]) +               # nested far1
           [0x3A] + w(SH) + [0x32] + w(RES + 4) +
           [0x01] + w(0x9ABC) + [0x11] + w(0x5678) + [0x21] + w(0x1234) + [0xC9])
    assert RET >= T + len(tgt) and RET < 0x10000
    code = ([0x3A] + w(SH) + [0xF5] +                              # ld a,(sh) / push af
            [0x3E, S["BANK_UI1"], 0xCD] + w(S["page_bank"]) +
            [0x21] + w(DATA) + [0x11] + w(T) + [0x01] + w(len(tgt)) + [0xED, 0xB0] +
            [0x3E, 0xC9, 0x32] + w(RET) +
            [0x3E, S["BANK_POOL0"], 0xCD] + w(S["page_bank"]) +    # the caller's bank: 0
            [0x21] + w(T) + [0x3E, SID, 0xCD] + w(S["far1"]) +
            [0xED, 0x43] + w(RES + 5) + [0xED, 0x53] + w(RES + 7) + [0x22] + w(RES + 9) +
            [0x3A] + w(SH) + [0x32] + w(RES + 11) +
            [0xF1, 0xCD] + w(S["restore_page"]))                   # play's bank back
    p.boot(K_KNIGHT)
    p.isolate()
    p.settle(2)
    q0 = (p.rb("LOG_QN"), p.rb(S["LOG_Q"] + S["LQ_DROP"]))
    p.z.cmd("write-memory %d %s" % (DATA, " ".join(map(str, tgt))))
    pc0 = p.pc()
    ok = p.run_stub(code, org=STUB)
    p.z.cmd("set-register PC=%d" % pc0)
    check("W18 stub ran (far1 into bank 1 returned)", ok, "")
    r = p.z.read_memory(RES, 12)
    q1 = (p.rb("LOG_QN"), p.rb(S["LOG_Q"] + S["LQ_DROP"]))
    b1 = S["BANK_UI1"]
    check("W18 far1: bank 1 paged in the target, A passed through",
          (r[1] & 7, r[0]) == (b1, SID), (r[1] & 7, r[0]))
    check("W18 msg_push from bank-1 code: bank 1 paged afterwards, message queued",
          r[2] & 7 == b1 and (q1[0] == q0[0] + 1 or q1[1] == q0[1] + 1), (r[2] & 7, q0, q1))
    check("W18 copy_virt3 (pages bank 3) from bank-1 code: bank 1 paged afterwards",
          r[3] & 7 == b1, r[3] & 7)
    check("W18 nested far1: bank 1 paged afterwards", r[4] & 7 == b1, r[4] & 7)
    check("W18 far1 hands the caller's bank (0) back; BC / DE / HL of the target pass through",
          (r[11] & 7, r[5] | r[6] << 8, r[7] | r[8] << 8, r[9] | r[10] << 8)
          == (S["BANK_POOL0"], 0x9ABC, 0x5678, 0x1234),
          (r[11] & 7, hex(r[5] | r[6] << 8), hex(r[7] | r[8] << 8), hex(r[9] | r[10] << 8)))
    check("W18 screen bit kept (shadow bit 3 == displayed bank 7 in play)",
          all(x & 0x18 == 0x18 for x in (r[1], r[2], r[3], r[4], r[11])), [hex(x) for x in r[1:5]])



# C3-1 key positions: name -> (KBD_MATRIX row, bit)
W19_KEYS = {
    "Q": (2, 0), "A": (1, 0), "O": (5, 1), "P": (5, 0), "SPACE": (7, 0),
    "M": (7, 2), "Z": (0, 1), "V": (0, 4), "T": (2, 4), "ENTER": (6, 0),
    "H": (6, 4), "J": (6, 3), "K": (6, 2), "L": (6, 1), "I": (5, 2), "CAPS": (0, 0), "S": (1, 1),
    "1": (3, 0), "2": (3, 1), "3": (3, 2), "4": (3, 3), "5": (3, 4),
    "0": (4, 0), "9": (4, 1), "8": (4, 2), "7": (4, 3), "6": (4, 4),
}
W19_ROW = [(S["KBD_MATRIX"] & 0xFF) + r for r in range(8)]   # KEYTAB row byte of row r


def w19(p, check):
    """C3-1: read_stick / sample_input over injected KBD_MATRIX + JOY_MIRROR."""
    STUB = S["LOWRAM_END_3B"]
    RES = S["MSG_BUF"]
    w = w16
    # C3-6b (game.md §3.2): the menu reads raw digits only. With JM_SINC2 the
    # '2' (a joystick key in game) still toggles HERO and '1' still starts; a
    # Kempston FIRE (JOY_MIRROR) does nothing and STICK stays 0 in the menu.
    p.load()
    p.wait_state(GS_SELECT)
    p.wb("INPUT_SRC", 1)
    p.wb("JOY_MODE", 3)
    p.hold("2")
    p.tick(6)
    p.release()
    p.tick(2)
    tog = p.rb("menu_hero") == K_WIZARD
    p.wb("JOY_MODE", 1)
    p.wb("JOY_MIRROR", 0x10)   # JOY_F (Kempston bit 4)
    p.tick(8)
    kemp = p.rb("GAME_STATE") == GS_SELECT and p.rb("STICK") == 0
    p.wb("JOY_MIRROR", 0)
    p.wb("JOY_MODE", 3)
    p.hold("2")
    p.tick(6)
    p.release()
    p.tick(2)
    tog = tog and p.rb("menu_hero") == K_KNIGHT
    p.hold("1")
    sel_ok = p.wait_state(GS_PLAYING, 200)
    p.release()
    check("W19 menu in JM_SINC2: '2' toggles HERO and '1' starts (digits are raw); Kempston FIRE ignored, STICK 0",
          tog and kemp and sel_ok and p.rb("HERO_KIND") == K_KNIGHT, (tog, kemp, sel_ok, p.rb("HERO_KIND")))
    p.boot(K_KNIGHT)
    p.isolate()
    p.settle(2)
    # STICK follows every tick, ANIM ticks included (C3-1 review: C3-2's edges)
    p.hold("P")                                   # a walk: several ANIM ticks
    p.until(lambda: p.rb("TURN_PHASE") == 1, 6)
    p.hold("H")
    ph = p.rb("TURN_PHASE")                       # 1: the next tick is an ANIM tick
    p.tick()
    an = (ph, p.rb("STICK"), p.rb("STICK_OLD"))
    p.release()
    p.tick()
    an2 = (p.rb("STICK"), p.rb("STICK_OLD"))
    check("W19 STICK / STICK_OLD update every tick (in ANIM too)",
          an == (1, 2, 1) and an2 == (0, 2), (an, an2))   # P -> O (left) -> none
    p.settle(6)
    pc0 = p.pc()
    sp0 = int(re.search(r"SP=([0-9a-fA-F]{4})", p.z.cmd("get-registers")).group(1), 16)
    code = ([0xCD] + w(S["input_tick"]) + [0xCD] + w(S["sample_input"]) +
            [0x32] + w(RES))

    def keytab(keys):
        b = []
        for k in keys:
            r, bit = W19_KEYS[k]
            b += [W19_ROW[r], 1 << bit]
        p.z.cmd("write-memory %d %s" % (S["KEYTAB"], " ".join(map(str, b))))

    def sample(keys=(), mode=0, mirror=0, src=1):
        rows = [0xFF] * 8
        for k in keys:
            r, bit = W19_KEYS[k]
            rows[r] &= ~(1 << bit) & 0xFF
        p.z.cmd("write-memory %d %s" % (S["KBD_MATRIX"], " ".join(map(str, rows))))
        p.wb("JOY_MODE", mode)
        p.wb("JOY_MIRROR", mirror)
        p.wb("INPUT_SRC", src)
        ok = p.run_stub(code, org=STUB)
        return dict(ok=ok, a=p.rb(RES), stick=p.rb("STICK"), old=p.rb("STICK_OLD"),
                    dir=p.rb("PLAYER_DIR"), disc=p.rb("PLAYER_DISC"), sc=p.rb("PLAYER_SC"))

    DEF = ["P", "O", "A", "Q", "SPACE"]                 # R L D U F (JOY bit order)
    RED = ["M", "Z", "V", "T", "ENTER"]
    S1 = ["7", "6", "8", "9", "0"]
    S2 = ["2", "1", "3", "4", "5"]
    JM = dict(keys=0, kemp=1, s1=2, s2=3)
    dkw = S["DK_WAIT"]
    kt0 = list(p.z.read_memory(S["KEYTAB"], 10))
    want_kt = []
    for k in DEF:
        r, bit = W19_KEYS[k]
        want_kt += [W19_ROW[r], 1 << bit]
    check("W19 boot KEYTAB == KEYTAB_DEFAULTS (P/O/A/Q/SPACE), JOY_MODE keys",
          kt0 == want_kt and p.rb("JOY_MODE") == 0, (kt0, p.rb("JOY_MODE")))

    def source(tag, mode, keys=None, mirror=False):
        bad = []
        for i in range(5):
            r = sample((keys[i],) if keys else (), JM[mode], (1 << i) if mirror else 0)
            want = 1 << i
            # C3-8a: sample_input's A (NZ iff held) counts directions only: FIRE
            # is intent_tick's (FIRE_ST), no longer the PROTO "FIRE = wait" (ENTER, as a
            # redefined FIRE key, is still the ENTER shortcut)
            if not (r["ok"] and r["stick"] == want and r["dir"] == want & 0x0F and
                    not r["disc"] & dkw and (r["a"] != 0) == (i < 4 or bool(keys) and keys[i] == "ENTER")):
                bad.append((i, r))
        r = sample((), JM[mode])
        if not (r["stick"] == 0 and r["dir"] == 0 and r["a"] == 0):
            bad.append(("idle", r))
        check(f"W19 {tag}: STICK == the JOY bit for R/L/D/U/F, DIR == STICK & $0F, no DK_WAIT",
              bad == [], bad[:2])

    source("default keys", "keys", DEF)
    source("default keys (Kempston selected)", "kemp", DEF)
    source("Sinclair 1 (6-0)", "s1", S1)
    source("Sinclair 2 (1-5)", "s2", S2)
    source("Kempston via JOY_MIRROR", "kemp", mirror=True)
    keytab(RED)
    source("redefined KEYTAB M/Z/V/T/ENTER", "keys", RED)
    r = sample(("P",), 0)
    check("W19 redefined KEYTAB: the old default key P is dead", r["stick"] == 0, r)
    keytab(DEF)

    # ORing: keys + joystick, STICK_OLD
    r = sample(("O",), JM["kemp"], 1 << 0)
    check("W19 OR: key O + Kempston R -> R|L (opposites both reported)", r["stick"] == 3, r)
    r = sample(("P", "9"), JM["s1"])
    check("W19 OR: key P + Sinclair 1 U(9) -> R|U", r["stick"] == 0x09, r)
    r = sample(("Q", "5"), JM["s2"])
    check("W19 OR: key Q + Sinclair 2 F(5) -> U|F (FIRE is not DK_WAIT, C3-8a)", r["stick"] == 0x18 and not r["disc"] & dkw, r)
    r2 = sample(("A",), 0)
    check("W19 STICK_OLD = the previous sample", r2["old"] == 0x18 and r2["stick"] == 0x04, r2)
    # C3-8a: the PROTO H/J/K/L aliases were removed with legacy_input: the keys are dead
    bad = [(k, sample((k,), JM["s2"])["stick"]) for k in ("L", "H", "J", "K")]
    check("W19 PROTO aliases L/H/J/K are gone (C3-8a): no stick bit", all(s_ == 0 for _, s_ in bad), bad)

    # Kempston not read unless selected; floating-bus guard
    bad = []
    for m in ("keys", "s1", "s2"):
        r = sample((), JM[m], 0x1F)
        if r["stick"] != 0:
            bad.append((m, r["stick"]))
    check("W19 JOY_MIRROR ignored unless JM_KEMPSTON", bad == [], bad)
    bad = [(v, sample((), JM["kemp"], v)["stick"]) for v in (0xFF, 0x20 | 1, 0x40 | 2, 0x80 | 0x10)]
    check("W19 Kempston byte with bits 5-7 set ignored (absent interface / floating bus)",
          all(x == 0 for _, x in bad), bad)
    r = sample(("P",), JM["kemp"], 0xFF)
    check("W19 ignored Kempston byte keeps the keys", r["stick"] == 1, r)
    # INPUT_SRC = 0: break on the IN ($1F)
    rs = [0xCD] + w(S["read_stick"]) + [0x32] + w(RES)
    p.z.cmd("set-breakpoint 4 PC=%d" % S["read_stick.port"])
    hit = {}
    for m in ("keys", "s1", "s2", "kemp"):
        p.wb("JOY_MODE", JM[m])
        p.wb("INPUT_SRC", 0)
        ok = p.run_stub(rs, org=STUB)
        hit[m] = (not ok) and p.pc() == S["read_stick.port"]
        p.z.cmd("set-register SP=%d" % sp0)
    p.z.cmd("set-breakpoint 4")
    p.wb("INPUT_SRC", 1)
    check("W19 live (INPUT_SRC 0): IN ($1F) reached only in JM_KEMPSTON",
          hit == dict(keys=False, s1=False, s2=False, kemp=True), hit)

    # shortcuts
    exp = {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "0": 10}
    dk = {"1": S["DK_1"], "2": S["DK_2"], "3": S["DK_3"]}
    for mode, off in (("keys", ""), ("kemp", ""), ("s1", "67890"), ("s2", "12345")):
        bad = []
        for k, slot in exp.items():
            r = sample((k,), JM[mode])
            want = 0 if k in off else slot
            wdk = 0 if k in off else dk.get(k, 0)
            if (r["sc"] & 0x0F) != want or (r["disc"] & (S["DK_1"] | S["DK_2"] | S["DK_3"])) != wdk:
                bad.append((k, r["sc"], r["disc"]))
        check(f"W19 shortcuts 1-0 in {mode}: slot n (0 = 10){', off: ' + off if off else ''}",
              bad == [], bad[:3])
    r = sample(("3", "7"), 0)
    check("W19 two digits held: the lower slot wins", r["sc"] & 0x0F == 3, r)
    r = sample(("I",), 0)
    r2 = sample(("CAPS", "SPACE"), 0)
    check("W19 I -> SC_INV, CAPS+SPACE -> SC_BREAK (FIRE masked: BREAK has priority), A NZ",
          r["sc"] == 1 << S["SC_INV_BIT"] and r["a"] != 0 and r2["sc"] == 1 << S["SC_BREAK_BIT"]
          and r2["stick"] == 0 and not r2["disc"] & dkw, (r["sc"], r2))
    r = sample(("CAPS", "O"), 0)
    check("W19 CAPS alone does not mask FIRE / directions", r["stick"] == 2, r)

    # cost (DI, uncontended bank-2 routine; stub overhead subtracted)
    t = {}
    for m in ("keys", "kemp", "s1"):
        p.wb("JOY_MODE", JM[m])
        _, ts = run_code(p, [0xF3, 0xCD] + w(S["read_stick"]) + [0xFB])
        t[m] = ts - 8
    p.wb("JOY_MODE", 0)
    _, ts_s = run_code(p, [0xF3, 0xCD] + w(S["input_tick"]) + [0xFB])
    _, ts_i = run_code(p, [0xF3, 0xCD] + w(S["sample_input"]) + [0xFB])
    print(f"[info] W19 measured: read_stick {t} T; input_tick (injected, keys) {ts_s - 8} T;"
          f" sample_input {ts_i - 8} T",
          flush=True)
    check("W19 read_stick <= 1.0k T in every mode", max(t.values()) <= 1000, t)
    p.z.cmd("set-register SP=%d" % sp0)
    p.z.cmd("set-register PC=%d" % pc0)


def w20(p, check):
    """C3-1 review: measured stack depth (pattern fill below WORKSTORE_TOP)."""
    import random
    lo, top = S["STACK_BOTTOM"], S["WORKSTORE_TOP"]
    PAT = 0x5A
    keep = p.proto_start
    p.proto_start = 0                               # generated D1: level_gen too
    p.load()
    p.proto_start = keep
    p.z.cmd("write-memory %d %s" % (lo, " ".join([str(PAT)] * (top - lo))))
    p.wait_state(GS_SELECT)
    p.wb("INPUT_REPEAT", 0)
    p.wb("ANIM_FREEZE", 1)
    p.wb("INPUT_SRC", 1)
    p.hold("1")
    p.wait_state(GS_PLAYING)
    p.release()
    p.settle(3)
    rnd = random.Random(0xC31)
    keys = [("P",), ("O",), ("Q",), ("A",), ("Q", "P"), ("Q", "O"), ("SPACE",), ("P",), ("O",)]
    turns = 0
    for _ in range(80):
        if p.rb("GAME_STATE") != GS_PLAYING:
            break
        turns += p.turn(*rnd.choice(keys))
    m = p.z.read_memory(lo, top - lo)
    low = next((lo + i for i, b in enumerate(m) if b != PAT), top)
    depth = top - low
    print(f"[info] W20 measured: max stack depth {depth} B (lowest byte touched {low:#06x}) over boot,"
          f" a generated D1 start and {turns} turns (rooms visited end {p.rb('CUR_ROOM')})", flush=True)
    check("W20 stack: max depth <= 256 B of the 768-B stack (STACK_BOTTOM never reached)",
          0 < depth <= 256, depth)



W22_KEYS = dict(W19_KEYS, SYM=(7, 1), B=(7, 4), Y=(5, 4))


def w22_23(p, check, which):
    from game_lib import K_RAT
    """C3-2: the turn-intent machine, driven through KBD_MATRIX (default
    KEYTAB: P R, O L, A D, Q U, SPACE F)."""
    import budget
    TXT = dict(STRINGS)
    kw, kh = game.body(p, K_KNIGHT)
    y1 = stand_y(1, kh)

    def hold(*keys):
        rows = [0xFF] * 8
        for k in keys:
            if k == ".":
                rows[7] &= ~0x06 & 0xFF               # SYM + M
                continue
            r, bit = W22_KEYS[k]
            rows[r] &= ~(1 << bit) & 0xFF
        p.z.cmd("write-memory %d %s" % (S["KBD_MATRIX"], " ".join(map(str, rows))))

    def tap(*keys, n=1):
        hold(*keys)
        p.tick(n)
        hold()
        p.tick()

    def log_line():
        """The log line drawn last (row 23) once the queue is drained."""
        p.until(lambda: p.rb("LOG_QN") == 0, 20)
        p.tick(2)
        return log_row(p.composed_frame(), 23)

    def shows(name):
        return log_line() == text6(TXT[name])

    def fresh(x=12):
        p.boot(K_KNIGHT)
        p.isolate()
        p.wb("INPUT_REPEAT", 1)                       # the game's default
        p.place(0, x, y1, flags=EF_ACTIVE | EF_PLAYER)   # facing right
        p.settle(2)

    tc = lambda: p.rw("TURN_COUNTER")
    hero = lambda: p.ent(0)

    if which == "W22":
        fresh()
        pc0 = p.pc()
        hold()
        _, t_idle = run_code(p, [0xF3, 0xCD] + w16(S["intent_tick"]) + [0xFB])
        hold("SPACE", "P")                            # FIRE + R pressed: a cursor step (far3)
        _, t_cur = run_code(p, [0xF3, 0xCD] + w16(S["input_tick"]) + [0xCD] + w16(S["intent_tick"]) + [0xFB])
        _, t_in = run_code(p, [0xF3, 0xCD] + w16(S["input_tick"]) + [0xFB])
        hold()
        p.z.cmd("set-register PC=%d" % pc0)
        p.wb("SEL_SLOT", 0)
        p.wb("FIRE_ST", 0)
        p.settle(2)
        print(f"[info] W22 measured: intent_tick idle {t_idle - 8} T; intent_tick with a cursor step"
              f" {t_cur - t_in} T (input_tick {t_in - 8} T)", flush=True)
        check("W22 intent_tick idle + cursor step within the +1.5k T input allowance",
              t_idle - 8 <= 1500, t_idle - 8)
        # --- FIRE tap / hold ---
        t0 = tc()
        tap("SPACE", n=2)
        check("W22 FIRE tap (2 ticks): melee on nothing -> NO TARGET, no turn",
              shows("no_target") and tc() == t0 and p.rb("INTENT") == 0, (tc() - t0, p.rb("INTENT")))
        p.wb("LOG_QN", 0)
        q0 = p.rb(S["LOG_Q"] + S["LQ_RD"])
        hold("SPACE")
        p.tick(12)
        st = p.rb("FIRE_ST")
        hold()
        p.tick(3)
        check("W22 FIRE held 12 ticks: not a tap (FIRE_ST USED), nothing on release",
              st == S["FS_USED"] and p.rb("INTENT") == 0 and p.rb("LOG_QN") == 0
              and p.rb(S["LOG_Q"] + S["LQ_RD"]) == q0 and tc() == t0, (st, p.rb("LOG_QN")))
        # --- outside ICON MODE: FIRE + side does not move the cursor (C3-2b) ---
        hold("SPACE", "P")
        p.tick(3)
        hold()
        p.tick(2)
        check("W22 outside ICON MODE: FIRE + R neither moves the cursor nor uses the icon",
              (p.rb("SEL_SLOT"), p.rb("INTENT"), tc() - t0, p.rb("ICON_MODE")) == (0, 0, 0, 0),
              (p.rb("SEL_SLOT"), p.rb("INTENT"), p.rb("ICON_MODE")))
        # --- ICON MODE: DOWN first, FIRE within 3 ticks ---
        p.wb(S["P_ENTITIES"] + S["E_FLT"], 0)
        hold("A")
        p.tick()
        hold("A", "SPACE")
        p.tick()
        hold()
        p.tick()
        fr = p.composed_frame()
        inv = [fr[6144 + r * 32 + c] for r in (18, 19) for c in range(3)]
        sword = TXT["info_sword"]
        pref = ">" + sword[:15] + sword[16:]
        log_line()
        fr = p.composed_frame()
        check("W22 DOWN then FIRE: ICON MODE, no turn, slot 1 inverse, info line '>' + sword line",
              p.rb("ICON_MODE") == 1 and tc() == t0 and log_row(fr, 20, 0, 32) == text6(pref, 0, 32)
              and all(x & 0x38 and not x & 0x07 for x in
                      [fr[6144 + r * 32 + c] for r in (18, 19) for c in range(3)]),
              (p.rb("ICON_MODE"), tc() - t0, inv))
        # frozen world: a flash timer does not run down, no turn
        p.wb(S["P_ENTITIES"] + S["E_FLT"], 10)
        p.tick(5)
        check("W22 ICON MODE freezes play (hero flash timer held, no turn)",
              p.rb(S["P_ENTITIES"] + S["E_FLT"]) == 10 and tc() == t0, p.rb(S["P_ENTITIES"] + S["E_FLT"]))
        p.wb(S["P_ENTITIES"] + S["E_FLT"], 0)
        # cursor: R at once, +10 ticks, then every 4 (1-2 unlearned skipped, 9 empty)
        hold("P")
        seq = []
        for _ in range(30):
            p.tick()
            seq.append(p.rb("SEL_SLOT"))
        hold()
        p.tick(2)
        moves = [(i, v) for i, v in enumerate(seq) if i == 0 or v != seq[i - 1]]
        want = [(0, 3), (10, 4), (14, 5), (18, 6), (22, 7), (26, 8)]
        check("W22 ICON MODE R: cursor 0 -> 3 at once (1-2 unlearned skipped), +10 ticks, then every 4",
              moves == want and p.rb("ICON_MODE") == 1, moves)
        tap("P")
        check("W22 cursor wraps 8 -> 0 (slot 9 empty skipped)", p.rb("SEL_SLOT") == 0, p.rb("SEL_SLOT"))
        tap("O")
        check("W22 cursor wraps 0 -> 8 leftwards", p.rb("SEL_SLOT") == 8, p.rb("SEL_SLOT"))
        tap("5")
        check("W22 ICON MODE: key 5 jumps the cursor to slot 4", p.rb("SEL_SLOT") == 4, p.rb("SEL_SLOT"))
        p.wb("LOG_QN", 0)
        tap("SPACE")
        check("W22 ICON MODE: FIRE on the greyed bow = NO BOW, no turn, the mode stays",
              shows("no_bow") and tc() == t0 and p.rb("ICON_MODE") == 1, (tc() - t0, p.rb("ICON_MODE")))
        pr = p.rb("PAUSE_REQ")
        tap("CAPS", "SPACE")
        check("W22 BREAK in ICON MODE: exits, no pause request, no turn",
              (p.rb("ICON_MODE"), p.rb("PAUSE_REQ") - pr, tc() - t0) == (0, 0, 0),
              (p.rb("ICON_MODE"), p.rb("PAUSE_REQ") - pr))
        log_line()
        check("W22 after the exit: the info line has no '>' (bow line), selection kept",
              log_row(p.composed_frame(), 20, 0, 32) == text6(TXT["info_bow"], 0, 32) and p.rb("SEL_SLOT") == 4, "")
        # FIRE first, DOWN within 3 ticks; UP exits
        hold("SPACE")
        p.tick()
        hold("SPACE", "A")
        p.tick()
        m1 = p.rb("ICON_MODE")
        hold()
        p.tick(2)
        tap("Q")
        check("W22 FIRE then DOWN: ICON MODE; UP exits (no use, no turn)",
              (m1, p.rb("ICON_MODE"), tc() - t0, p.rb("INTENT")) == (1, 0, 0, 0), (m1, p.rb("ICON_MODE")))
        # DOWN late (> 3 ticks after FIRE): no mode
        hold("SPACE")
        p.tick(4)
        hold("SPACE", "A")
        p.tick()
        m2 = p.rb("ICON_MODE")
        hold()
        p.tick(2)
        check("W22 FIRE held 4 ticks, then DOWN: no ICON MODE, no use", (m2, tc() - t0) == (0, 0), m2)
        # use from the mode: potion (slot 7) drinks -> turn, back to play
        hp_a = S["P_ENTITIES"] + S["E_HP"]
        p.wb(hp_a, 5)
        hold("A")
        p.tick()
        hold("A", "SPACE")
        p.tick()
        hold()
        p.tick()
        tap("7")
        tap("SPACE")
        p.until(lambda: p.idle(), 40)
        check("W22 ICON MODE: FIRE on the potion drinks it (1 turn) and returns to play",
              (tc() - t0, p.rb("ICON_MODE"), hero()["HP"] > 5) == (1, 0, True), (tc() - t0, p.rb("ICON_MODE")))
        t0 = tc()
        p.wb("SEL_SLOT", 0)
        # --- FIRE + UP = pause (outside the mode) ---
        pr = p.rb("PAUSE_REQ")
        hold("SPACE")
        p.tick()
        hold("SPACE", "Q")
        p.tick()
        hold()
        p.tick(2)
        check("W22 FIRE+UP: a pause request (C3-6: the overlay is up), no turn, no tap",
              p.rb("PAUSE_REQ") == pr + 1 and p.rb("PAUSED") == 1 and tc() == t0 and p.rb("INTENT") == 0,
              (p.rb("PAUSE_REQ") - pr, p.rb("PAUSED")))
        tap("SPACE")                                  # RESUME
        p.tick(2)
        # --- BREAK priority ---
        p.wb("LOG_QN", 0)
        hold("SPACE")
        p.tick()
        hold("SPACE", "CAPS")
        p.tick()
        hold()
        p.tick(3)
        check("W22 BREAK (CAPS+SPACE) after FIRE: pause request, the FIRE tap is cancelled",
              p.rb("PAUSE_REQ") == pr + 2 and tc() == t0 and p.rb("LOG_QN") == 0, (p.rb("PAUSE_REQ") - pr,))
        tap("SPACE")                                  # RESUME
        p.tick(2)
        # --- DOWN alone: held back 3 ticks; a shorter tap commits on release ---
        hold("A")
        ph = []
        for _ in range(3):
            p.tick()
            ph.append(p.rb("TURN_PHASE"))
        hold()
        p.until(lambda: p.idle(), 20)
        check("W22 DOWN held: the wait starts on the 3rd tick (ICON MODE window)",
              ph == [0, 0, 1] and tc() - t0 == 1, (ph, tc() - t0))
        t0 = tc()
        tap("A")
        p.until(lambda: p.idle() and tc() != t0, 20)
        check("W22 DOWN tapped 1 tick: the wait still happens (commit on release)", tc() - t0 == 1, tc() - t0)
        t0 = tc()
        # --- turn-around (0 turns), held reverse walks after 10 ticks ---
        x0 = hero()["X"]
        tap("O")
        e = hero()
        check("W22 reverse tap: turns left, no move, 0 turns",
              (e["FLAGS"] & EF_LEFT, e["X"], tc() - t0) == (EF_LEFT, x0, 0), (e["FLAGS"], e["X"], tc() - t0))
        hold("P")                                     # from facing left
        n = 0
        while hero()["X"] == x0 and n < 30:
            p.tick()
            n += 1
        hold()
        p.until(lambda: p.idle(), 40)
        check("W22 held reverse key: turns, then walks after the 10-tick delay (1 turn)",
              10 <= n <= 12 and not hero()["FLAGS"] & EF_LEFT and tc() - t0 >= 1, (n, tc() - t0))
        p.settle(2)
        # --- DOWN with no ladder = wait; '.' = wait; low diagonal = side ---
        t1, e0 = tc(), hero()
        p.turn("A")
        e = hero()
        check("W22 DOWN with no ladder below: a wait (1 turn, no move)",
              (tc() - t1, e["X"], e["Y"]) == (1, e0["X"], e0["Y"]), (tc() - t1, e["X"], e["Y"]))
        t1 = tc()
        hold(".")
        p.until(lambda: tc() != t1, 4)
        hold()
        p.until(lambda: p.idle(), 20)
        check("W22 '.' waits (1 turn)", tc() - t1 == 1, tc() - t1)
        x1 = hero()["X"]
        hold("A", "P")
        p.until(lambda: hero()["X"] != x1, 6)
        hold()
        p.until(lambda: p.idle(), 20)
        check("W22 DOWN+RIGHT walks right (no wait)", hero()["X"] == x1 + 1, hero()["X"] - x1)
        # --- shortcuts ---
        p.wb("LOG_QN", 0)
        tap("5")
        a = p.rb("SEL_SLOT")
        tap("2")
        b = p.rb("SEL_SLOT")
        nl = shows("not_learned")
        tap("0")
        c = p.rb("SEL_SLOT")
        check("W22 shortcuts: 5 selects slot 4 (greyed bow), 2 = NOT LEARNED (stays), 0 = empty (stays)",
              (a, b, nl, c) == (4, 4, True, 4), (a, b, nl, c))
        # --- review fixes (C3-2b) ---
        hp_a = S["P_ENTITIES"] + S["E_HP"]

        def enter_mode():
            hold("A")
            p.tick()
            hold("A", "SPACE")
            p.tick()
            hold()
            p.tick(2)

        pot_a = S["P_ENTITIES"] + S["E_POT"]
        p.wb(pot_a, 3)                                # potions to drink (a tap would)
        p.wmem(S["BAG"], [S["IT_P_HEAL"], 3, 0])      # 3E-T11: ... from the BAG
        p.wb(hp_a, 5)
        p.wb("SEL_SLOT", 6)
        p.settle(2)
        t0, pr = tc(), p.rb("PAUSE_REQ")
        hold("CAPS", "SPACE")
        p.tick(2)
        hold("SPACE")                                 # CAPS lifted first
        p.tick(2)
        hold()
        p.until(lambda: p.idle(), 40)
        p.tick(2)
        check("W22r BREAK, CAPS lifted before SPACE: a pause request, no tap (no potion, no turn)",
              (tc() - t0, p.rb("PAUSE_REQ") - pr, p.rb(hp_a)) == (0, 1, 5), (tc() - t0, p.rb(hp_a)))
        tap("SPACE")                                  # RESUME (C3-6 overlay)
        p.tick(2)
        enter_mode()
        m = p.rb("ICON_MODE")
        hold("CAPS", "SPACE")
        p.tick(2)
        hold("SPACE")
        p.tick(2)
        hold()
        p.until(lambda: p.idle(), 40)
        p.tick(2)
        check("W22r BREAK in ICON MODE, CAPS lifted first: mode left, no use, no pause",
              (m, p.rb("ICON_MODE"), tc() - t0, p.rb("PAUSE_REQ") - pr, p.rb(hp_a)) == (1, 0, 0, 1, 5),
              (m, p.rb("ICON_MODE"), tc() - t0, p.rb(hp_a)))
        enter_mode()
        x1 = hero()["X"]
        hold("SPACE")
        p.tick()
        hold("P")                                     # FIRE released, RIGHT held at once
        p.until(lambda: hero()["X"] != x1 and p.idle(), 60)
        hold()
        p.until(lambda: p.idle(), 20)
        check("W22r FIRE use from ICON MODE (potion), then RIGHT held: the hero walks (no exit lock)",
              p.rb(hp_a) > 5 and hero()["X"] > x1 and p.rb("EXIT_LOCK") == 0, (p.rb(hp_a), hero()["X"] - x1))
        t0, x1 = tc(), hero()["X"]
        p.wb("DN_COMMIT", 1)                          # a buffered DOWN tap ...
        hold("P")                                     # ... and RIGHT asked this tick
        p.until(lambda: tc() != t0, 6)
        hold()
        p.until(lambda: p.idle(), 20)
        p.tick(6)
        check("W22r buffered DOWN + RIGHT: the walk only, the DOWN is dropped (1 turn, no later wait)",
              (tc() - t0, hero()["X"] - x1, p.rb("DN_COMMIT")) == (1, 1, 0), (tc() - t0, hero()["X"] - x1))
        p.wb("INPUT_REPEAT", 0)
        p.wb("NEED_RELEASE", 1)
        t0 = tc()
        p.wb("DN_COMMIT", 1)
        p.until(lambda: tc() != t0, 6)
        p.until(lambda: p.idle(), 20)
        p.tick(2)
        t1, x1 = tc(), hero()["X"]
        hold("P")
        p.until(lambda: tc() != t1, 6)
        hold()
        p.until(lambda: p.idle(), 20)
        check("W22r INPUT_REPEAT 0 + NEED_RELEASE + a buffered DOWN: the wait runs, then input works",
              (t1 - t0, tc() - t1, hero()["X"] - x1) == (1, 1, 1), (t1 - t0, tc() - t1, hero()["X"] - x1))
        p.wb("INPUT_REPEAT", 1)
        return

    # ---------------- W23: icon use ------------------------------------------
    def refusal(key_slot, name):
        """Shortcut to a slot, tap FIRE: the line `name`, no turn."""
        tap(key_slot)
        t1 = tc()
        p.wb("LOG_QN", 0)
        tap("SPACE")
        ok = shows(name) and tc() == t1
        return ok

    fresh(x=12)
    rat = 1
    _, rh = game.body(p, K_RAT)
    p.place(rat, 12 + kw, stand_y(1, rh), room=p.rb("CUR_ROOM"), flags=EF_ACTIVE | EF_HOSTILE | EF_LEFT)
    p.settle(2)
    t0 = tc()
    st = budget.Stepper(p)
    n0 = len(st.ticks)
    st.turn("SPACE")
    st.close()
    worst = max(t for t, _ in st.ticks[n0:])
    tgt = p.rb(S["P_ENTITIES"] + S["E_TGT"])
    p.until(lambda: p.idle(), 60)
    print(f"[info] W23 measured: FIRE melee attack, worst tick {worst} T over {len(st.ticks) - n0} ticks",
          flush=True)
    check("W23 FIRE on the sword, rat faced: an attack on it (1 turn)",
          (tc() - t0, tgt) == (1, rat), (tc() - t0, tgt))
    check("W23 FIRE melee turn: worst tick <= 126k T", worst <= 126000, worst)
    # melee with nothing faced next to the A|B door: closes it
    fresh(x=12)
    e_ab = S["EDGE_TAB"] + S["EDGE_AB"]
    OPEN = S["EG_OPEN"]
    p.place(0, 30 - kw, y1, flags=EF_ACTIVE | EF_PLAYER)
    t0 = tc()
    tap("SPACE")
    p.until(lambda: p.idle(), 40)
    check("W23 FIRE on the sword facing the open door: closes it (1 turn; replaces key C)",
          (tc() - t0, p.rb(e_ab) & OPEN) == (1, 0), (tc() - t0, p.rb(e_ab)))
    # quick potion (Warrior slot 7 = key 7)
    fresh(x=12)
    hpa = S["P_ENTITIES"] + S["E_HP"]
    p.wb(hpa, 5)
    tap("7")
    sel = p.rb("SEL_SLOT")
    t0 = tc()
    tap("SPACE")
    p.until(lambda: p.idle(), 40)
    e = hero()
    check("W23 key 7 + FIRE: quick potion drunk (1 turn, HP up, potion used)",
          (sel, tc() - t0, e["HP"] > 5, e["POT"]) == (6, 1, True, 0), (sel, tc() - t0, e["HP"], e["POT"]))
    t0 = tc()
    p.wb("LOG_QN", 0)
    tap("SPACE")
    check("W23 again with no potion: NO POTION, no turn", shows("no_potion") and tc() == t0, tc() - t0)
    # greyed / missing refusals
    bad = []
    for key, name in (("5", "no_bow"), ("6", "no_food"), ("8", "no_scroll")):
        if not refusal(key, name):
            bad.append(name)
    p.wb("DAGGERS", 0)
    if not refusal("4", "no_daggers"):
        bad.append("no_daggers")
    check("W23 refusals (bow, food, scroll, daggers at 0): their line, no turn", bad == [], bad)
    # ENTER uses the icon; I = the bag (3E-T2: the page opens; BREAK or I closes it, 3E-T13: FIRE selects; tests/page.py)
    tap("9")
    t0 = tc()
    n0 = p.rb("PAGE_N")
    tap("ENTER")
    a = p.rb("PAGE_OPEN")
    tap("CAPS", "SPACE")
    tap("I")
    b = p.rb("PAGE_OPEN")
    tap("CAPS", "SPACE")
    check("W23 ENTER uses the selected icon (Bag: the page opens); I = the page; no turn",
          (a, b, (p.rb("PAGE_N") - n0) & 255, p.rb("PAGE_OPEN"), tc() - t0) == (1, 1, 2, 0, 0),
          (a, b, p.rb("PAGE_N") - n0, tc() - t0))


def w15_icons(p, check):
    """C3-3: icon bar states (concept-screen §5), cursor attr move, info line
    text per icon (row 20, 42 chars, game.md §3.4), level digit (31, 19)."""
    TXT = dict(STRINGS)
    p.boot(K_KNIGHT)
    p.isolate()
    p.settle(4)

    def attrs(fr, slot):
        return [fr[6144 + r * 32 + 3 * slot + c] for r in (18, 19) for c in range(3)]

    def cells(fr, slot):
        return [bytes(cell_bytes(fr, 3 * slot + c, r)) for r in (18, 19) for c in range(3)] + [attrs(fr, slot)]

    def info(fr):
        return log_row(fr, 20, 0, 32)

    def line(*fields):
        """42-char info line from (char pos, text) pieces."""
        t = [" "] * 42
        for at, txt in fields:
            t[at:at + len(txt)] = list(txt)
        return "".join(t).rstrip()

    def settle_panel():
        p.until(lambda: p.rb("PANEL_DIRTY") == 0, 20)
        p.tick(2)
        return p.frame()

    fr = settle_panel()
    a = {i: attrs(fr, i) for i in range(10)}
    sel = all(x & 0x38 == 0x08 for x in a[0])
    others_black = all(x & 0x38 == 0 for i in range(1, 10) for x in a[i])
    hidden = cells(fr, 1) == cells(fr, 2) == cells(fr, 9)
    grey = all(x == S["ATTR_P_GREY"] for i in (4, 5, 7) for x in a[i])
    normal = all(x != S["ATTR_P_GREY"] for i in (3, 8) for x in a[i])
    pot = (a[6][3], a[6][5], log_row(fr, 19, 20, 1) == text6("1", 0, 1))
    check("W15i Warrior start: slot 1 selected (PAPER blue), others black paper",
          sel and others_black, a[0])
    check("W15i unlearned Power / Whirl = the empty outline (== spare slot 10)", hidden, "")
    check("W15i greyed: bow (not found), quick food, quick scroll ($07); daggers (3) and Bag normal",
          grey and normal, (a[4], a[5], a[7], a[3], a[8]))
    check("W15i quick potion: glyph ATTR_POTION, count '1' (ATTR_HUD)",
          pot == (S["ATTR_POTION"], S["ATTR_HUD"], True), pot)
    check("W15i level digit '1' at (31, 19), attr $46",
          log_row(fr, 19, 31, 1) == text6("1", 0, 1) and fr[6144 + 19 * 32 + 31] == 0x46, "")
    check("W15i info line = the sword's line (row 20), field attrs $47 / $46 / $45",
          info(fr) == text6(TXT["info_sword"], 0, 32) and
          [fr[6144 + 20 * 32 + c] for c in (0, 11, 12, 20, 21, 31)] == [0x47, 0x47, 0x46, 0x46, 0x45, 0x45],
          "")
    # cursor move = attr move + info line
    p.wb("SEL_SLOT", 3)
    fr = settle_panel()
    check("W15i cursor -> slot 4 (daggers): PAPER blue moves, slot 1 back to black, info = daggers",
          all(x & 0x38 == 0x08 for x in attrs(fr, 3)) and all(x & 0x38 == 0 for x in attrs(fr, 0))
          and info(fr) == text6(TXT["info_daggers"], 0, 32), (attrs(fr, 3), attrs(fr, 0)))
    p.wb("DAGGERS", 0)
    fr = settle_panel()
    check("W15i daggers at 0: selected + greyed = $0F", all(x == 0x0F for x in attrs(fr, 3)), attrs(fr, 3))
    p.wb("SEL_SLOT", 6)
    fr = settle_panel()
    check("W15i potion line: 'POTION  X1  FIRE: DRINK' (count in the numbers field)",
          info(fr) == text6(line((0, "POTION"), (16, "X1"), (28, "FIRE: DRINK")), 0, 32), "")
    p.wb("SEL_SLOT", 8)
    fr = settle_panel()
    check("W15i Bag line: 'BAG  LV 1  XP 0/40' (game.md §4.1)",
          info(fr) == text6(line((0, "BAG"), (16, "LV 1"), (28, "XP 0/40")), 0, 32), "")
    p.wb("XP", 39)
    p.wb(S["XP"] + 1, 1)                          # 295
    p.wb("LVL", 4)
    p.wb("SEL_SLOT", 3)
    settle_panel()
    p.wb("SEL_SLOT", 8)
    fr = settle_panel()
    check("W15i Bag line follows LVL / XP; level digit follows LVL",
          info(fr) == text6(line((0, "BAG"), (16, "LV 4"), (28, "XP 295/340")), 0, 32)
          and log_row(fr, 19, 31, 1) == text6("4", 0, 1), "")
    check("W15i displayed == composed", fr == p.composed_frame(), "")


def w24(p, check):
    """C3-6 (bank 1, menu1.asm; game.md §3.1 / §3.2): the menu (golden), cursor
    + controls + hero, Sinclair digit masking, redefine (duplicates refused,
    KEYTAB only when complete), seed entropy (MENU_SPIN; seed_fixed exact),
    the pause overlay (rows restored byte for byte, QUIT asks Y/N), the death
    card."""
    keep_p = p.proto_start

    def hold(*keys):
        rows = [0xFF] * 8
        for k in keys:
            r, bit = W22_KEYS[k]
            rows[r] &= ~(1 << bit) & 0xFF
        p.z.cmd("write-memory %d %s" % (S["KBD_MATRIX"], " ".join(map(str, rows))))

    def tap(*keys, n=2):
        hold(*keys)
        p.tick(n)
        hold()
        p.tick(2)

    def to_menu(proto=1):
        p.proto_start = proto
        p.load()
        p.wait_state(GS_SELECT)
        p.wb("INPUT_SRC", 1)
        p.wb("ANIM_FREEZE", 1)                       # the torches hold frame 0 (golden)
        hold()
        p.tick(4)

    try:
        to_menu()
        fr = p.frame()
        game.golden(p.h, "w24_menu", fr)
        check("W24 menu: title / items in the menu font ('1 START' at (4, 8), 'HERO: WARRIOR')",
              menu_text_ok(p, fr, 8, 4, "1 START") and menu_text_ok(p, fr, 11, 4, "2 HERO: WARRIOR"), "")
        # no cursor; '3' cycles the controls (keys > Kempston > S1 > S2 > keys); other
        # keys, FIRE and a Kempston FIRE do nothing
        tap("A")
        tap("SPACE")
        p.wb("JOY_MIRROR", 0x10)   # JOY_F (Kempston bit 4)
        tap("Q")
        p.wb("JOY_MIRROR", 0)
        idle = p.rb("GAME_STATE") == GS_SELECT and p.rb("JOY_MODE") == 0 and p.rb("menu_hero") == K_KNIGHT
        modes = []
        for _ in range(4):
            tap("3")
            modes.append(p.rb("JOY_MODE"))
        check("W24 digits only: A / FIRE / Kempston FIRE ignored; '3' x4 cycles JOY_MODE 1, 2, 3, 0",
              idle and modes == [1, 2, 3, 0], (idle, modes))
        # Sinclair 2 selected: '1' / '2' are still the menu digits (HERO toggles)
        p.wb("JOY_MODE", 3)
        tap("2")
        tg = p.rb("menu_hero")
        tap("2")
        p.wb("JOY_MODE", 0)
        check("W24 Sinclair 2 selected: key '2' still toggles HERO (menu is raw digits)",
              tg == K_WIZARD and p.rb("menu_hero") == K_KNIGHT and p.rb("GAME_STATE") == GS_SELECT, tg)
        # redefine: M Z V T, a duplicate M and reserved ENTER / 5 refused, then B
        kt0 = bytes(p.z.read_memory(S["KEYTAB"], 10))
        tap("4")
        for k in ("M", "Z", "V", "T"):
            tap(k)
        mid = bytes(p.z.read_memory(S["KEYTAB"], 10))
        refused = []
        for k in ("M", "ENTER", "5", "I", "S", "CAPS"):
            tap(k)
            p.tick(30)                               # the "KEY IN USE / RESERVED" beat
            refused.append(p.rb("rd_i"))
        tap("B")
        p.tick(4)
        kt = bytes(p.z.read_memory(S["KEYTAB"], 10))
        row = lambda r: (S["KBD_MATRIX"] & 0xFF) + r
        want = bytes([row(2), 1 << 4, row(0), 1 << 4, row(0), 1 << 1, row(7), 1 << 2, row(7), 1 << 4])
        check("W24 redefine U=M D=Z L=V R=T F=B: KEYTAB unchanged until complete; duplicate M and the "
              "reserved ENTER / 5 / I / S / CAPS refused",
              mid == kt0 and refused == [4] * 6 and kt == want, (kt0.hex(), mid.hex(), refused, kt.hex()))
        # BREAK cancels a redefine: the old KEYTAB stays
        tap("4")
        tap("M")
        tap("CAPS", "SPACE")
        p.tick(4)
        check("W24 BREAK at a redefine prompt cancels it (KEYTAB unchanged)",
              bytes(p.z.read_memory(S["KEYTAB"], 10)) == want and p.rb("GAME_STATE") == GS_SELECT, "")
        p.z.cmd("write-memory %d %s" % (S["KEYTAB"], " ".join(map(str, kt0))))
        # hero toggle + START
        tap("2")
        tap("1")
        ok = p.wait_state(GS_PLAYING, 400)
        check("W24 '2' toggles the hero, '1' starts: the Mage plays", ok and p.rb("HERO_KIND") == K_WIZARD,
              (ok, p.rb("HERO_KIND")))
        # seed entropy (generated start): START on the same menu frame, a DOWN
        # tapped earlier at different frames -> different seeds (the key-edge
        # mixing, not only the START frame); the same timing -> the same seed
        seeds = []
        for down_at, fixed in ((5, 0), (11, 0), (5, 0), (5, 1)):
            to_menu(proto=0)
            p.wb("seed_fixed", fixed)
            p.tick(down_at)
            tap("A")
            tap("Q")
            p.tick(30 - down_at)
            hold("1")
            p.wait_state(GS_PLAYING, 600)
            hold()
            seeds.append(p.rw("MASTER_SEED"))
        check("W24 seed: an earlier keypress's timing changes MASTER_SEED (same START frame); same timing = "
              "same seed; seed_fixed = seed_value",
              seeds[0] != seeds[1] and seeds[0] == seeds[2] and seeds[3] == p.rw("seed_value"),
              [hex(x) for x in seeds])
        # pause: overlay, resume restores rows 7-9 byte for byte
        to_menu()
        tap("1")
        p.wait_state(GS_PLAYING, 400)
        p.isolate()
        p.settle(4)

        def rows79():
            return (bytes(p.composed_frame()), bytes(p.frame()))   # C3-6 review: whole screens
        before = rows79()
        hold("SPACE")
        p.tick()
        hold("SPACE", "Q")
        p.tick(2)
        hold()
        p.tick(3)
        fr = p.frame()
        paused = p.rb("PAUSED")
        boxed = menu_text_ok(p, fr, 8, 1, "RESUME") and menu_text_ok(p, fr, 8, 27, "QUIT")
        tap("SPACE")
        p.tick(4)
        check("W24 FIRE+UP: pause overlay (RESUME / QUIT); FIRE on RESUME: the whole composed and displayed "
              "screens restored byte for byte (no torch in row 0)",
              paused == 1 and boxed and p.rb("PAUSED") == 0 and rows79() == before
              and p.frame() == p.composed_frame(), (paused, boxed, p.rb("PAUSED")))
        # QUIT: Y/N, "no" returns to the box, FIRE = yes -> the menu
        hold("CAPS", "SPACE")
        p.tick(2)
        hold()
        p.tick(3)
        tap("P")                                     # -> SOUND (SND-1)
        tap("P")                                     # -> QUIT
        tap("SPACE")                                 # QUIT? Y/N
        asked = menu_text_ok(p, p.frame(), 8, 11, "QUIT? Y/N")
        tap("A")                                     # any other: no
        back = p.rb("PAUSED") == 1 and p.rb("GAME_STATE") == GS_PLAYING
        tap("SPACE")
        tap("SPACE")                                 # yes
        p.tick(10)
        check("W24 BREAK pauses; QUIT asks Y/N, another key = no, FIRE = yes -> the menu",
              asked and back and p.rb("GAME_STATE") == GS_SELECT, (asked, back, p.rb("GAME_STATE")))
        # D3-0 (user): the Y key is yes too
        hold()
        tap("1")
        p.wait_state(GS_PLAYING, 400)
        p.settle(2)
        hold("CAPS", "SPACE")
        p.tick(2)
        hold()
        p.tick(3)
        tap("P")                                     # -> SOUND (SND-1)
        tap("P")                                     # -> QUIT
        tap("SPACE")                                 # QUIT? Y/N
        asked = menu_text_ok(p, p.frame(), 8, 11, "QUIT? Y/N")
        tap("Y")                                     # yes
        p.tick(10)
        check("W24 QUIT? Y/N: the Y key = yes -> the menu (D3-0)",
              asked and p.rb("GAME_STATE") == GS_SELECT, (asked, p.rb("GAME_STATE")))
        # death card
        hold()
        tap("1")
        p.wait_state(GS_PLAYING, 400)
        p.settle(2)
        hold("2")                                    # a digit still down when the hero dies
        p.wb("GAME_STATE", GS_DEAD)
        p.tick(4)
        fr = p.frame()
        card = p.rb("END_SHOWN") == 1 and menu_text_ok(p, fr, 8, 12, "YOU DIED")
        p.tick(4)
        held = p.rb("GAME_STATE") == GS_DEAD         # no release yet: not accepted
        hold()
        p.tick(3)
        armed = p.rb("END_SHOWN") == 2
        tap("SPACE")
        p.wb("JOY_MIRROR", 0x10)   # JOY_F (Kempston bit 4)
        p.tick(4)
        p.wb("JOY_MIRROR", 0)
        still = p.rb("GAME_STATE") == GS_DEAD        # FIRE (key or stick) does not return
        check("W24 death: the 'YOU DIED' card (menu font, rows 8-9); a held digit, FIRE and a stick "
              "press do not return to the menu",
              card and held and armed and still, (card, held, armed, still))
        tap("2")
        p.tick(6)
        check("W24 death card: a digit after a release returns to the menu", p.rb("GAME_STATE") == GS_SELECT,
              p.rb("GAME_STATE"))
    finally:
        p.proto_start = keep_p

# C3-8b: the 3C exit gate (W25): one joystick-only run per input source.
# Source = the 5 inputs R L D U F: default keys, a redefined KEYTAB (made in
# the REDEFINE menu), Sinclair 1 / 2 (number-row halves), Kempston (JOY_MIRROR).
W25_SRC = {                                   # name -> (JOY_MODE, [R, L, D, U, F] keys)
    "keys": (0, ["P", "O", "A", "Q", "SPACE"]),
    "redef": (0, ["T", "V", "Z", "M", "B"]),       # UP M, DOWN Z, LEFT V, RIGHT T, FIRE B
    "s1": (2, ["7", "6", "8", "9", "0"]),
    "s2": (3, ["2", "1", "3", "4", "5"]),
    "kemp": (1, None),
}
W25_DIR = {"R": 0, "L": 1, "D": 2, "U": 3, "F": 4}


def w25(p, check):
    """Every in-game step is driven only by the source's own 5 inputs (the
    menu is digits-only, C3-6b: '3' selects the mode, '4' REDEFINE, '1' START). PROTO rooms: walk, turn-around (0 turns), jump
    (UP + side), close the A|B door (FIRE, melee), quaff (ICON MODE: DOWN +
    FIRE, cursor R to the potion, FIRE), pause + resume (FIRE held + UP).
    Generated D1 (fixed seed): walk to the lair exit, DOWN descends."""
    kw, kh = game.body(p, K_KNIGHT)
    y0, y1 = stand_y(0, kh), stand_y(1, kh)
    keep = p.proto_start
    e_ab = S["EDGE_TAB"] + S["EDGE_AB"]
    LINK, DOOR, OPEN = S["EG_LINK"], S["EG_DOOR"], S["EG_OPEN"]
    tc = lambda: p.rw("TURN_COUNTER")
    hero = lambda: p.ent(0)

    def hold(src, *dirs):
        mode, keys = W25_SRC[src]
        if keys is None:                          # Kempston: the JOY_MIRROR byte
            p.wb("JOY_MIRROR", sum(1 << W25_DIR[d] for d in dirs))
            dirs = ()
            keys = []
        rows = [0xFF] * 8
        for d in dirs:
            r, bit = W22_KEYS[keys[W25_DIR[d]]]
            rows[r] &= ~(1 << bit) & 0xFF
        p.z.cmd("write-memory %d %s" % (S["KBD_MATRIX"], " ".join(map(str, rows))))

    def tap(src, *dirs, n=2):
        hold(src, *dirs)
        p.tick(n)
        hold(src)
        p.tick(2)

    def idle():
        p.until(lambda: p.idle(), 80)
        p.tick(2)

    def step(src, *dirs):
        """Press until a turn starts, release, run it out. -> turns taken."""
        t0 = tc()
        hold(src, *dirs)
        for _ in range(8):
            p.tick()
            if p.rb("TURN_PHASE") == 1 or tc() != t0:
                break
        hold(src)
        idle()
        return tc() - t0

    def fire(src):
        """FIRE tap (acts on release). -> turns taken."""
        t0 = tc()
        hold(src, "F")
        p.tick()
        hold(src)
        for _ in range(4):
            p.tick()
            if p.rb("TURN_PHASE") == 1 or tc() != t0:
                break
        idle()
        return tc() - t0

    def dhold(*keys):
        rows = [0xFF] * 8
        for k in keys:
            r, bit = W22_KEYS[k]
            rows[r] &= ~(1 << bit) & 0xFF
        p.z.cmd("write-memory %d %s" % (S["KBD_MATRIX"], " ".join(map(str, rows))))

    def dtap(*keys, n=2):
        dhold(*keys)
        p.tick(n)
        dhold()
        p.tick(2)

    def start_menu(src, proto, fixed_seed=False):
        """Boot to the menu and START using only `src`."""
        p.proto_start = proto
        p.load()
        p.wait_state(GS_SELECT)
        p.wb("INPUT_SRC", 1)
        p.wb("ANIM_FREEZE", 1)
        p.wb("INPUT_REPEAT", 1)                   # the game's default
        if fixed_seed:
            p.wb("seed_fixed", 1)                 # seed_value = the default $1234
        dhold()
        p.tick(4)
        mode, keys = W25_SRC[src]
        if src == "redef":                        # item 4 (REDEFINE) by its digit
            dtap("4")
            for d in ("U", "D", "L", "R", "F"):   # the prompts: UP DOWN LEFT RIGHT FIRE
                tap("redef", d)
            p.tick(4)
            kt = bytes(p.z.read_memory(S["KEYTAB"], 10))
            row = lambda r: (S["KBD_MATRIX"] & 0xFF) + r
            want = bytes([row(2), 1 << 4, row(0), 1 << 4, row(0), 1 << 1, row(7), 1 << 2, row(7), 1 << 4])
            check("W25 redef: KEYTAB made in the REDEFINE menu (U=M D=Z L=V R=T F=B)", kt == want, kt.hex())
        for _ in range(mode):                     # CONTROLS (item 3): '3' cycles the mode
            dtap("3")
        dhold("ENTER")                            # START (key 1 would be Sinclair 2's LEFT in game)
        p.tick(1)
        dhold()
        ok = p.wait_state(GS_PLAYING, 600)
        p.tick(3)
        check(f"W25 {src}: menu driven by digits, START; the source is live in game (JOY_MODE {mode}, Knight)",
              ok and p.rb("JOY_MODE") == mode and p.rb("HERO_KIND") == K_KNIGHT,
              (ok, p.rb("JOY_MODE"), p.rb("HERO_KIND")))

    def ingame(code):
        pc0 = p.pc()
        ok = p.run_stub([0xF3] + code + [0xFB], org=S["LOWRAM_END_3B"])
        p.z.cmd("set-register PC=%d" % pc0)
        return ok

    try:
        for src in W25_SRC:
            # ---------------- PROTO rooms ----------------------------------
            start_menu(src, 1)
            p.isolate()
            p.settle(3)
            e = hero()
            t0 = tc()
            n = sum(step(src, "R") for _ in range(3))
            check(f"W25 {src}: walk R x3: x + 3, 3 turns", (hero()["X"], n) == (e["X"] + 3, 3),
                  (hero()["X"], n))
            tap(src, "L")
            e2 = hero()
            check(f"W25 {src}: L tap turns around (0 turns, no move)",
                  (bool(e2["FLAGS"] & EF_LEFT), e2["X"], tc() - t0) == (True, e["X"] + 3, 3), (e2["FLAGS"], tc() - t0))
            n = step(src, "L")
            check(f"W25 {src}: L walks left (1 turn)", (hero()["X"], n) == (e["X"] + 2, 1), (hero()["X"], n))
            # jump: UP + side
            p.place(0, 9, y1, flags=EF_ACTIVE | EF_PLAYER)
            n = step(src, "U", "R")
            e3 = hero()
            check(f"W25 {src}: jump UP+R: x + 6, back on storey 1, 1 turn",
                  (e3["X"], e3["Y"], n) == (15, y1, 1), (e3["X"], e3["Y"], n))
            # close the A|B door with melee (FIRE, slot 0)
            p.place(0, 27, y1, flags=EF_ACTIVE | EF_PLAYER)
            was = p.rb(e_ab)
            n = fire(src)
            check(f"W25 {src}: FIRE (melee) facing the open A|B door closes it (1 turn)",
                  (was, p.rb(e_ab), n) == (LINK | DOOR | OPEN, LINK | DOOR, 1), (was, p.rb(e_ab), n))
            # quaff via ICON MODE
            pot0 = hero()["POT"]
            p.set_ent(0, HP=5)
            p.settle(2)
            t0 = tc()
            hold(src, "D")
            p.tick()
            hold(src, "D", "F")
            p.tick()
            hold(src)
            p.tick(2)
            mode = p.rb("ICON_MODE")
            seq = []
            for _ in range(4):
                tap(src, "R")
                seq.append(p.rb("SEL_SLOT"))
            n = fire(src)
            e4 = hero()
            check(f"W25 {src}: ICON MODE (DOWN+FIRE), R x4 to the potion (slots {seq}), FIRE drinks it: "
                  "HP up, one potion used, back in play, 1 turn",
                  (mode, seq, e4["HP"] > 5, e4["POT"], p.rb("ICON_MODE"), tc() - t0)
                  == (1, [3, 4, 5, 6], True, pot0 - 1, 0, 1), (mode, seq, e4["HP"], e4["POT"], tc() - t0))
            # pause + resume
            t0 = tc()
            hold(src, "F")
            p.tick()
            hold(src, "F", "U")
            p.tick(2)
            hold(src)
            p.tick(3)
            paused = (p.rb("PAUSED"), tc() - t0)
            tap(src, "F")                         # RESUME is the default item
            p.tick(3)
            check(f"W25 {src}: FIRE held + UP pauses (no turn); FIRE on RESUME plays on",
                  paused == (1, 0) and p.rb("PAUSED") == 0 and tc() == t0 and p.rb("GAME_STATE") == GS_PLAYING,
                  (paused, p.rb("PAUSED")))
            # ---------------- generated D1: descend ------------------------
            start_menu(src, 0, fixed_seed=True)
            blk = room_model.read_block(p)
            lair = blk[S["LVL_LAIR"] - room_model.BASE]
            ex = room_model.field(blk, lair, "RD_EXITCOL")
            for s_ in range(1, 16):
                p.set_ent(s_, FLAGS=0)            # nobody interferes (a fixed, hazard-free route)
            x = ex - 2 if ex - 2 >= 2 else ex + 2
            p.z.cmd("write-memory %d %d" % (S["CUR_ROOM"], lair))
            p.set_ent(0, ROOM=lair, X=x, Y=y1, PX=x * 8, PY=y1 * 8,
                      FLAGS=EF_ACTIVE | EF_PLAYER | (EF_LEFT if x > ex else 0), MODE=0, DVIS=0)
            ok = ingame([0x3E, lair, 0xCD] + w16(S["room_show"]) + [0xCD] + w16(S["vis_reset"])
                        + [0xCD] + w16(S["present_full"]))
            p.settle(3)
            d0, hp0 = p.rb("LVL_DEPTH"), hero()["HP"]
            t0 = tc()
            key = "R" if ex > x else "L"
            n = sum(step(src, key) for _ in range(abs(ex - x)))
            check(f"W25 {src}: walk to the lair exit col {ex} ({abs(ex - x)} turns)",
                  ok and (hero()["X"], n) == (ex, abs(ex - x)), (ok, hero()["X"], n))
            hold(src, "D")
            for _ in range(700):
                p.tick()
                if p.rb("LVL_DEPTH") != d0:
                    break
            hold(src)
            p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
            p.settle(3)
            check(f"W25 {src}: DOWN on the exit descends D1 -> D2 (descend = 1 turn after the walk)",
                  (d0, p.rb("LVL_DEPTH"), tc() - t0, hero()["HP"] >= hp0)
                  == (1, 2, abs(ex - x) + 1, True), (d0, p.rb("LVL_DEPTH"), tc() - t0))
        # ---------------- seed entropy: START timing on the real input path
        seeds = []
        for wait in (7, 19, 7):
            p.proto_start = 0
            p.load()
            p.wait_state(GS_SELECT)
            p.wb("INPUT_SRC", 1)
            p.wb("ANIM_FREEZE", 1)
            dhold()
            p.tick(wait)
            dhold("1")                            # START
            p.tick(1)
            dhold()
            p.wait_state(GS_PLAYING, 600)
            seeds.append(p.rw("MASTER_SEED"))
        check("W25 seed: START at menu frame 7 vs 19 -> different MASTER_SEEDs; the same timing repeats",
              seeds[0] != seeds[1] and seeds[0] == seeds[2], [hex(s_) for s_ in seeds])
    finally:
        p.proto_start = keep


def w17(p, check):
    """B3B-13: the token text. (a) tk_get decodes every string of
    src/strings.txt into a buffer == its text (exact bytes, 0-terminated), +
    the decode cost vs a plain-fetch getter over the same text; (b) every
    string pushed by id (msg_push) and drawn by the real item_log (print6t)
    == the reference 6x8 render of its text on row 23 (C3-4: all but the
    info_* / ft_* lines, which are up to 42 chars and never go to the log), $C000 handed back, T
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
    # C3-4 grew the text to ~1.3 KB and B14 grew the cold block down: the
    # buffer below lowram_code no longer holds it all, so the strings are
    # decoded in id batches that fit (stub area 0x3C B; the plain loop reads
    # and writes the buffer in place: same bytes, same cost per char).
    BUF, GET = STUB + 0x40, STUB + 0x3C
    room = S["lowram_code"] - BUF
    plain_get = [0x0A, 0x03, 0xB7, 0xC9]          # ld a,(bc) / inc bc / or a / ret
    p.z.cmd("write-memory %d %s" % (GET, " ".join(map(str, plain_get))))

    def decode_loop(getter, plain, first, last):
        return asm([0x3A] + w(S["PORT_7FFD_SHADOW"]) + [0xF5,               # ld a,(shadow) / push af
                    0x3E, S["BANK_TEXT"], 0xCD] + w(S["page_bank"]) +
                   [0x11] + w(BUF) +                                        # ld de, out (plain: in place)
                   ([0x01] + w(BUF) if plain else []) +                     # plain: BC walks BUF
                   [0x3E, first, ("L", "lp"), 0xF5, 0xCD] + w(S["tx_ptr"]) +  # ld a,first / push af / call tx_ptr
                   ([0x00, 0x00] if plain else [0x44, 0x4D]) +              # (nop nop) / ld b,h / ld c,l
                   [("L", "in"), 0xCD] + w(getter) + [0x12, 0x13, 0xB7, ("jr", 0x20, "in"),
                    0xF1, 0x3C, 0xFE, last, ("jr", 0x38, "lp"),
                    0xF1, 0xCD] + w(S["restore_page"]))
    assert len(decode_loop(GET, True, 0, 1)) + 4 <= GET - STUB, "W17: stub overlaps GET"
    batches, i = [], 0
    while i < len(texts):
        j, n = i, 0
        while j < len(texts) and n + len(texts[j]) + 1 <= room:
            n += len(texts[j]) + 1
            j += 1
        assert j > i, "W17: one string longer than the buffer"
        batches.append((i, j))
        i = j
    sh0 = p.rb("PORT_7FFD_SHADOW")
    t_tk = t_pl = 0
    bad, bad_pl, bad_rng = [], [], False
    for first, last in batches:
        want_b = b"".join(t.encode() + b"\0" for t in texts[first:last])
        t_tk += stub(decode_loop(S["tk_get"], False, first, last), f"tk_get decode loop {first}..{last}", measure=True)
        got = bytes(p.z.read_memory(BUF, len(want_b)))
        bad += [(first, k, x, y) for k, (x, y) in enumerate(zip(got, want_b)) if x != y][:4]
        bad_rng |= not all(c == 0 or 32 <= c <= 127 for c in got)
        t_pl += stub(decode_loop(GET, True, first, last), f"plain getter loop {first}..{last}", measure=True)
        if bytes(p.z.read_memory(BUF, len(want_b))) != want_b:
            bad_pl.append(first)
    check(f"W17 tk_get: all {len(texts)} strings decode bit-exact (0-terminated, in id order; "
          f"{len(batches)} batches)", bad == [], bad[:4])
    check("W17 tk_get: decoded chars are 32..127 only", not bad_rng, "")
    check("W17 decode loop: the caller's $C000 bank handed back", p.rb("PORT_7FFD_SHADOW") == sh0,
          (sh0, p.rb("PORT_7FFD_SHADOW")))
    check("W17 plain-getter loop re-reads the same text", bad_pl == [], bad_pl)
    per = (t_tk - t_pl) / n_chars
    # --- (b) every string through msg_push + item_log (print6t) ---------------
    row_ok, worst, sh_bad = [], (0, ""), []
    log_ids = [(sid, nm, txt) for sid, (nm, txt) in enumerate(STRINGS)
               if not nm.startswith(("info_", "ft_"))]
    for sid, nm, txt in log_ids:
        sh0 = p.rb("PORT_7FFD_SHADOW")
        t = stub([0x3E, sid, 0xCD] + w(S["msg_push"]) + [0x21] + w(S["PANEL_DIRTY"]) +
                 [0xCD] + w(S["item_log"]), f"msg_push + item_log {nm}", measure=True)
        if p.rb("PORT_7FFD_SHADOW") != sh0:
            sh_bad.append(nm)
        if log_row(p.composed_frame(), 23) != text6(txt):
            row_ok.append(nm)
        if t > worst[0]:
            worst = (t, nm)
    check(f"W17 every log-width string ({len(log_ids)} of {len(STRINGS)}) drawn by item_log == the reference render of its text",
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
            continue                              # glyph swaps hold 16 ticks
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
    """The clean background in frame_bytes() layout (rows 0-17; rows 18-23 of
    the bitmap / attrs are not part of it): the ROOM_MAP glyph model (D3-S2,
    shadow_bitmap) + the bank-7 attr shadow."""
    bm = shadow_bitmap(p)
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
    sa, ala = pick(ROOM_A, lambda e: sum(x[2] >= 16 for x in e) >= 2 and sum(x[2] < 16 for x in e) >= 2   # DEC1: the small torch / candle attr cells are gone
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
    check("W14 attr table: flame cycles $46/$42/$06 only (DEC1: no candle kind)",
          set(tab[:8]) == {0x46, 0x42, 0x06}, tab)
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
          "glyph swaps 2-3 times (hold 16), attr cells took >= 2 attrs, glyph cells both frames",
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
    # DEC1: the room's attr cells now come in a same-phase pair (one torch): if the pair is due on the
    # injected entry's first tick the cap of 2 attr steps makes it wait, so start it a phase earlier
    q = [p.rb(S["ANIM_LIST"] + 4 * j + 3) for j in range(n) if p.rb(S["ANIM_LIST"] + 4 * j + 2) < 16]
    p0 = 2 if any(x & 3 == 3 for x in q) else 3
    p.z.cmd("write-memory %d %d %d 1 %d" % (S["ANIM_LIST"] + 4 * k, hc, hr, p0))
    p.wb("ANIM_N", k + 1)
    a0 = attr_at(p.composed_frame(), hc, hr)
    g0 = bytes(cell_bytes(p.composed_frame(), hc, hr))
    held = []
    for _ in range(9):
        p.tick()
        f = p.composed_frame()
        held.append((p.rb(S["ANIM_LIST"] + 4 * k + 3), attr_at(f, hc, hr), bytes(cell_bytes(f, hc, hr)) == g0))
    check("W14 a cell under the hero holds: its due steps (phases 4, 8) are skipped, the hero's "
          "attr / pixels stay", [x[0] for x in held] == list(range(p0 + 1, p0 + 10))
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
    pw = room_model.pit_width(room_model.desc(blk, r))      # L2: wide pit W 4..6
    if p_:
        pit = {(c, F0) for c in range(p_ - 1, p_ + pw + 1)}
        for c in range(p_, p_ + pw):
            if m[F0 * 32 + c] != T["T_AIR"]:
                bad.append(("pit hole", c, F0, m[F0 * 32 + c]))
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
    mb, mw = fld("L2_MIDB"), fld("L2_MIDW")
    if mb:                                     # L2 mid-room block: storey 0, rubble both faces
        midc = {(c, row) for c in range(mb, mb + mw) for row in range(SA + 1)}
        if blkc & midc:
            bad.append(("overlap block/mid-block", sorted(blkc & midc)[:2]))
        blkc |= midc
        for c in (mb - 1, mb + mw):
            if m[(SA - 1) * 32 + c] != T["T_RUBBLE"]:
                bad.append(("mid-block rubble", c, SA - 1, m[(SA - 1) * 32 + c]))
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
                ok = row == F0 and ((t == T["T_PIT_L"] and c == p_ - 1) or (t == T["T_PIT_R"] and c == p_ + pw)
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
            obj = S["T_LVL_OBJ"] - 32               # 3E-T6: item glyph ids' TILE_ATTRS 0 (fl_attr inks)
            check(f"W11 D{d}: ids 32..63 glyphs / attrs / TILE_FLAGS == the bank-7 slot {slot}",
                  (bytes(glyphs[256:]), bytes(attrs[32:]), bytes(flags[32:]))
                  == (sl[:256], sl[256:256 + obj] + bytes(32 - obj), sl[288:320]), "")
            floor_cls = {T[k] for k in ("T_PLAT", "T_WALLF", "T_END_L", "T_END_R", "T_HOLE_L",
                                        "T_HOLE_M", "T_HOLE_R", "T_GRATE", "T_AIR")}
            legal = {fl, wl, S["ATTR_AIR"], S["ATTR_LADDER"], S["ATTR_DOOR"], S["ATTR_GRATE"],
                     S["ATTR_POTION"], 0x42}       # (+ the legacy IT_POTION ink, item_ink)
            # B3B-9 decor: the level's own decor ids + the common small decor
            legal |= {attrs[i] for i in range(S["T_LVL_BASE"], S["T_LVL_OBJ"])}
            legal |= {attrs[T[k]] for k in ("T_CHAIN", "T_BONES_0", "T_BONES_1", "T_BONES_2", "T_BONES_3",
                                    "T_DAGGERS", "T_ARROWS")}   # D3-7 T6: ammo floor stacks
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
                tabs = p.bg_tables()[:4] + (room_model.floor_inks(        # 3E-T6: room r's inks
                    p.z.read_memory(S["FLOOR_LIST"], 128), r),)
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
        feats = dict(doors=0, pits=0, blocks=0, arr=0, exit=0, lad2=0, wide=0, mid=0)
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
                feats["wide"] += bool(fld("L2_PITW"))            # L2 (W26 plays them)
                feats["mid"] += bool(fld("L2_MIDB"))
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
        # dead-end block (edge / L2 mid-room) / door / pit, 800 levels; user 2026-10-12: decor
        # never on a wall cell, so "wall" (decor over a T_BRICK / T_WALLF base) must stay 0
        sw = {"rooms": 0, "wall": 0, "air": 0, "anim": 0, "large": 0}
        sbad = []
        rng = __import__("random").Random(0xB3B10)
        for i in range(800):
            d, seed, master = (1 + i % 8), rng.randrange(65536), rng.randrange(65536)
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
              not sbad and sw["rooms"] > 1000 and sw["wall"] == 0, sbad[:3])
        # ---- DEC1 bones rate by depth (Python deriver; the Z80 == Python is proven above): the
        # per-room chance is at most the gate (1/2 D3 D5 D8, 1/3 D4 D7), never on D1 D2 D6, and
        # not far below it (6 two-call tries nearly always find a legal pile on a roomy floor)
        rng = __import__("random").Random(0xDEC1)
        tot, got = {d: 0 for d in range(1, 9)}, {d: 0 for d in range(1, 9)}
        for i in range(480):
            d, seed, master = 1 + i % 8, rng.randrange(65536), rng.randrange(65536)
            blk = G.generate(d, seed, master)
            for r in present_rooms(blk):
                mm = room_model.render_room(blk, r)
                tot[d] += 1
                got[d] += T["T_BONES_0"] in mm
        rate = {d: got[d] / tot[d] for d in tot}
        print(f"[info] W13 bones rate by depth: " + ", ".join(f"D{d} {got[d]}/{tot[d]}" for d in tot), flush=True)
        okr = all(got[d] == 0 for d in (1, 2, 6)) and all(
            tot[d] and rate[d] <= 1 / n + 4 * (0.25 / tot[d]) ** 0.5 and rate[d] >= 0.5 / n
            for d, n in BONES_DEPTHS.items())
        check("W13 bones rate: none on D1 D2 D6; D3 D5 D8 <= 1/2, D4 D7 <= 1/3 (and >= half the gate)", okr, rate)
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
            if i % 25 == 0 or (d in BONES_DEPTHS and i % 5 == 0):
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


def lp_model(p, blk):
    """LP (game.md §9.4.1): the level budget + the start room's entry (quota 0:
    no monster; record VISITED, ROOM_VISITS[start] = 1), from tools/levelgen.py.
    The scratch bytes LP_HX..ROOM_VISITS are masked."""
    import levelgen as G
    st = blk[S["LVL_START"] - room_model.BASE]
    kw = p.rb(S["kind_tab"] + S["KT_BW"] + p.ent(0)["KIND"])
    lp, out = G.lp_enter(blk, G.lp_budget(blk, p.rb("LVL")), st, 0, p.ent(0)["X"], kw)
    lp = bytearray(lp)
    lp[S["ROOM_VISITS"] - S["LP_STATE"] + st] += 1
    got = bytearray(p.z.read_memory(S["LP_STATE"], S["LP_LEN"]))
    for i in range(S["LP_HX"] - S["LP_STATE"], S["ROOM_VISITS"] - S["LP_STATE"]):
        lp[i] = got[i] = 0
    return bytes(got), bytes(lp), out


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
        """C3-6: "DEPTH n" in the menu font at (12, 11) (level_card, bank 1)."""
        return menu_text_ok(p, fr, 11, 12, "DEPTH %d" % d)

    def level_ok(d, master, tag, hero_keep=None, seed=None):
        """Everything a fresh level must satisfy (tag: where we are)."""
        blk = room_model.read_block(p)
        want = G.generate(d, lvl_seed(master, d) if seed is None else seed, master)
        import items_model as IM                   # 3E-T6: + the item / trap generator
        hero = IM.HERO_WARRIOR if p.rb("HERO_KIND") == S["K_KNIGHT"] else IM.HERO_MAGE
        want = IM.apply_block(want, IM.gen_level_items(want, master, hero))
        check(f"W16 {tag}: LVL_DEPTH {d}, block == items_model(levelgen.generate({d}, master + {d} * MUL))",
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
        got_lp, want_lp, out = lp_model(p, blk)
        got = [s_ for s_ in range(1, 16) if p.ent(s_)["FLAGS"]]
        check(f"W16 {tag}: LP block == levelgen.lp_budget + the start room's entry; "
              "no monster slot (start quota 0, game.md §9.4.1)",
              got_lp == want_lp and out == [] and got == [], (got_lp.hex(), want_lp.hex(), got))
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
        ingame([0x3E, S["TX_DESCEND"], 0xCD] + w16(S["msg_push"]), "marker " + tag)
        p.until(lambda: p.rb("LOG_QN") == 0, 200)
        p.settle(4)
        for _ in range(24):
            if p.rb("CUR_ROOM") == nb:
                break
            p.turn(back)
        p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
        walk_in()
        check(f"W16 {tag}: second entry to the lair: no second hint (row 23 = the marker)",
              p.rb("CUR_ROOM") == lair and log_row(p.frame(), 23) == text6(dict(STRINGS)["descend"]),
              p.rb("CUR_ROOM"))
        # the exit col with the grate CLOSED: J is no exit (C3-8a: DOWN with no
        # ladder / exit below is a plain wait, 1 turn; it used to be no turn)
        fo = p.rb("LVL_FLAGS")
        p.wb("LVL_FLAGS", fo & ~S["LF_GRATE_OPEN"] & 255)
        p.place(0, xc, y1, room=lair, flags=EF_ACTIVE | EF_PLAYER)
        d0 = p.rb("LVL_DEPTH")
        nt = p.turn("J")
        check(f"W16 {tag}: grate closed: J on the exit col {xc} = a wait, no EX_LEVEL",
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
        # D3-0: the 3D status arrays + HERO3D are runtime RAM (garbage at
        # boot): new_game must zero all of them, slot 0 included
        ST = ("ST_FLAGS", "ST_T1", "ST_T2", "ST_X")
        h3 = S["HERO3D_END"] - S["HERO3D"]

        def st_poke(v):
            for a in ST:
                p.z.cmd("write-memory %d %s" % (S[a], " ".join([str(v)] * 16)))

        def st_read():
            return {a: list(p.z.read_memory(S[a], 16)) for a in ST}
        st_poke(0xA5)
        p.z.cmd("write-memory %d %s" % (S["HERO3D"], " ".join(["165"] * h3)))
        p.hold("1")
        p.wait_state(GS_PLAYING)
        fresh_ok("D1 start")                     # the first wait_tick of the game
        p.release()
        p.settle(3)
        check("W16 new game: MASTER_SEED = seed_value (seed_fixed), LVL_SEED = master + MUL",
              (p.rw("MASTER_SEED"), p.rb("LVL_DEPTH")) == (M, 1), hex(p.rw("MASTER_SEED")))
        h3_want = [0] * h3                       # D3-6a: but the Warrior's HERO_DEF = 1 (Leather)
        h3_want[S["HERO_DEF"] - S["HERO3D"]] = 1 if p.ent(0)["KIND"] == S["K_KNIGHT"] else 0
        h3_want[S["MP_SH"] - S["HERO3D"]] = p.rb("MP")  # D3-9b: item_mp drew MP since (MP_SH = MP)
        check("W16 new game (D3-0): ST_* arrays (all 16 slots) and HERO3D zeroed (D3-6a: HERO_DEF = class DEF)",
              (st_read(), list(p.z.read_memory(S["HERO3D"], h3)))
              == ({a: [0] * 16 for a in ST}, h3_want), (st_read(), list(p.z.read_memory(S["HERO3D"], h3))))
        blk = level_ok(1, M, "D1 start")
        hero_k = tuple(p.ent(0)[k] for k in ("HP", "MAXHP", "POT", "KIND"))
        # level_enter cost (cold), measured on its own (DI: no ISR; screen /
        # card / generator / build / panel / presents), D2 of this game
        d1 = room_model.read_block(p)
        lair_visit("D1")                        # B12
        # ---- descend D1 -> D2 by walking onto the exit -----------------
        st_poke(0x5A)                           # D3-0: hero status must carry; D3-8: slot 0
        for a_, v_ in (("ST_FLAGS", 0x20), ("ST_T1", 0), ("ST_T2", 0x0F)):   # a valid WEAK 15
            p.wb(S[a_], v_)                      # (the status step runs every hero turn now)
        tc_carry = p.rw("TURN_COUNTER")
        ran, cards, fr_n = to_exit(blk, "D1")
        check("W16 D1 -> D2: J on {EXITCOL,2} is one turn (first step animated) + the level change",
              ran, "")
        check("W16 D1 -> D2: the DEPTH 2 card is displayed while the level is generated",
              len(cards) == 1 and cards[0][1] in (1, 2) and card_ok(cards[0][0], 2), len(cards))
        info["descend D1->D2 frames (input tick .. idle)"] = fr_n
        blk2 = level_ok(2, M, "D2 after descend", hero_keep=hero_k)
        n_ = p.rw("TURN_COUNTER") - tc_carry    # D3-8: WEAK 15 stepped once per turn
        want_ = {a: [v_] + [0] * 15 for a, v_ in zip(ST, (0x20, 0, 0x0F - n_, 0x5A))}
        check("W16 D2 (D3-0 HERO_CARRY): ST_* slot 0 carried, slots 1..15 cleared by level_reset",
              0 < n_ < 15 and st_read() == want_, (n_, st_read()))
        p.tick(4)                               # D3-8 review: panel_init (level_show) resets
        fr_ = p.composed_frame()                # STAT_SH to $FF, so the carried WEAK icon redraws
        check("W16 D2: carried WEAK icon redrawn after level_show (STAT_SH 7, a glyph at (30, 21))",
              p.rb("STAT_SH") == 7 and any(cell_bytes(fr_, 30, 21)),
              (p.rb("STAT_SH"), cell_bytes(fr_, 30, 21)))
        st_poke(0)
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
            p.turn("WAIT")
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

L2_CASES = (("wide", 4, 13, 7), ("wide", 4, 1, 7), ("wide", 4, 5, 0),     # W 4 / 5 / 6
            ("mid", 4, 4, 4), ("mid", 4, 2, 8))                           # w 2 / 3


def l2_walk_parts(m, kh):
    """W26 (Python): the storey-0 hero walk graph read off a built map (decor off):
    x in 1..28 stands iff the body cells (rows 8-kh..7, cols x..x+2) hold no solid
    tile and not all 3 floor cells below are T_AIR (body fully over holes = a fall).
    -> (standing x set, fall x set, components as sorted lists)."""
    T = room_model.T
    F0, SA = S["FLOOR_ROW0"], S["STOREY_AIR"]
    solid = {T[k] for k in ("T_BRICK", "T_WALLF", "T_DOOR_ARCH_L", "T_DOOR_ARCH_R", "T_DOOR_L",
                            "T_DOOR_R", "T_DOOR_LOCK")}
    stand, fall = set(), set()
    for x in range(1, 29):
        if any(m[row * 32 + c] in solid for row in range(SA - kh, SA) for c in range(x, x + 3)):
            continue
        if all(m[F0 * 32 + c] == T["T_AIR"] for c in range(x, x + 3)):
            fall.add(x)
        else:
            stand.add(x)
    comps, seen = [], set()
    for x in sorted(stand):
        if x in seen:
            continue
        comp, y = [], x
        while y in stand:
            comp.append(y)
            seen.add(y)
            y += 1
        comps.append(comp)
    return stand, fall, comps


def w26_l2(p, check):
    """W26 (L2 engine, game.md §1.1 "Mid-room block" / "Wide pit", §2.4 / §2.5).
    Python: the room_model maps of a seed sweep (D2-D8) agree with levelcheck's
    storey-0 model (one divider at p / b: walk components {x < d} / {x >= d}; the
    fall x set == p .. p+W-3; no divider = one component). Emulator, per forced
    L2 room (L2_CASES, generated by the Z80 level_gen into a PROTO game, then
    room_show): map == model, both screens == map; wide pit: walking in falls at
    x == p (from the left) / p+W-3 (from the right) and stands at p-1 / p+W-2,
    a jump over it is cut short and falls at p+W-3 / p; walkers (try_step) refuse
    p / p+W-3 and take p-1 / p+W-2, a flyer crosses; mid-block: walking into
    either face = no turn, the rubble col is walkable, a jump across = no turn,
    walkers refuse both faces; re-entry: ROOM_MAP + both screens + shadow
    byte-identical."""
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
    import levelgen as G
    T = room_model.T
    kw, kh = game.body(p, K_KNIGHT)
    # ---- Python: levelcheck's divider model == the room_model map ----------
    nl2 = nbad = 0
    for d in range(2, 9):
        for sd in range(1, 41):
            blk = G.generate(d, sd, 0)
            for r in present_rooms(blk):
                m = room_model.render_room(blk, r, decor=False)
                stand, fall, comps = l2_walk_parts(m, kh)
                dsc = room_model.desc(blk, r)
                div = dsc[S["RD_PITCOL"]] or dsc[S["L2_MIDB"]]
                nl2 += bool(dsc[S["L2_PITW"]] or dsc[S["L2_MIDB"]])
                want_c = [[x for x in sorted(stand) if x < div], [x for x in sorted(stand) if x >= div]] \
                    if div else [sorted(stand)]
                if comps != want_c or fall != set(room_model.fall_range(blk, r)):
                    nbad += 1
                    if nbad <= 3:
                        check(f"W26 D{d} seed {sd} r{r}: map walk graph == levelcheck divider", False,
                              (div, comps, sorted(fall), list(room_model.fall_range(blk, r))))
    check(f"W26 Python sweep D2-D8 x 40 seeds: storey-0 walk components / fall x of every "
          f"room map == levelcheck's divider model ({nl2} L2 rooms)", nbad == 0 and nl2 >= 40, (nbad, nl2))
    # ---- emulator: forced L2 rooms ------------------------------------------
    y0, y1 = stand_y(0, kh), stand_y(1, kh)
    HERO_R = EF_ACTIVE | EF_PLAYER

    def stub_step(slot, x, y, dx):
        """try_step(IX = slot at (x, y), D = dx) in place; -> 0xFF moved / 0 refused."""
        p.set_ent(slot, ROOM=p.rb("CUR_ROOM"), X=x, Y=y, PX=8 * x, PY=8 * y, MODE=0,
                  FLAGS=EF_ACTIVE | EF_HOSTILE | (EF_LEFT if dx < 0 else 0))
        pc0 = p.pc()
        code = ([0xF3, 0xCD] + w16(S["build_live"]) + [0xCD] + w16(S["cache_player"]) +
                [0x3E, slot, 0x32] + w16(S["ACT_SLOT"]) + [0xAF, 0x32] + w16(S["YIELD_FLAG"]) +
                [0xDD, 0x21] + w16(S["P_ENTITIES"] + 32 * slot) +
                [0x16, dx & 0xFF, 0x1E, 0, 0xCD] + w16(S["try_step"]) +
                [0x9F, 0x32] + w16(S["MSG_BUF"]) + [0xFB])
        ok = p.run_stub(code, org=S["LOWRAM_END_3B"])
        p.z.cmd("set-register PC=%d" % pc0)
        res = p.rb("MSG_BUF")
        p.set_ent(slot, ROOM=GEN_NOWHERE)
        return res if ok else None

    def hero_at(x, y=None, left=False):
        p.set_ent(0, X=x, Y=y0 if y is None else y, PX=8 * x, PY=8 * (y0 if y is None else y), MODE=0,
                  HP=20, FLAGS=HERO_R | (EF_LEFT if left else 0))
        p.wb("JUMP_TURN", 0xFF)
        p.wb(S["JUMP_TURN"] + 1, 0xFF)
        p.settle()

    def screens_ok(tag):
        """W4 bar the animated decor cells (decor_tick steps them; W14 owns those)."""
        n = p.rb("ANIM_N")
        al = p.z.read_memory(S["ANIM_LIST"], 4 * n) if 0 < n <= 12 else b""
        anim = {(al[i], al[i + 1]) for i in range(0, len(al), 4)}
        bad = []
        for scr, fr in (("displayed", p.frame()), ("composed", p.composed_frame())):
            cells = [(c, r_) for c, r_ in p.bg_mismatch_in(fr) if (c, r_) not in anim]
            if cells:
                bad.append((tag, scr, len(cells), cells[:4]))
        return bad

    try:
        for kind, d, sd, r in L2_CASES:
            want_blk = G.generate(d, sd, 0)
            dsc = room_model.desc(want_blk, r)
            p.boot(K_KNIGHT)
            kinds = {s_: p.ent(s_)["KIND"] for s_ in range(1, 16)}
            for s_ in range(1, 16):
                p.set_ent(s_, ROOM=GEN_NOWHERE)
            p.z.cmd("write-memory %d %d %d" % (S["LVL_SEED"], sd & 255, sd >> 8))
            p.z.cmd("write-memory %d 0 0" % S["MASTER_SEED"])
            pc0 = p.pc()
            ok = p.run_stub([0xF3, 0x3E, d, 0x21] + w16(S["level_gen"]) + [0xCD] + w16(S["far3"])
                            + [0x3A] + w16(S["LVL_DEPTH"]) + [0xCD] + w16(S["level_load_tiles"])
                            + [0x3E, r, 0x32] + w16(S["CUR_ROOM"])
                            + [0x3E, r, 0xCD] + w16(S["room_show"]) + [0xCD] + w16(S["vis_reset"])
                            + [0xCD] + w16(S["present_full"]) + [0xFB], org=S["LOWRAM_END_3B"])
            p.z.cmd("set-register PC=%d" % pc0)
            p.set_ent(0, ROOM=r)
            blk = room_model.read_block(p)
            tag = f"W26 {kind} D{d} seed {sd} r{r}"
            check(f"{tag}: Z80 level_gen == levelgen.py, the L2 room shown", ok and blk == want_blk, ok)
            # hero somewhere safe first (storey 1, x = 2..) for the screen check
            hero_at(14, y1)
            bad = map_structure(p, r) + invariants(blk, r, bytes(p.z.read_memory(S["ROOM_MAP"], 576)), d)
            bad += screens_ok(tag)
            check(f"{tag}: map == model + invariants, both screens == ROOM_MAP", bad == [], bad[:3])
            walker = [s_ for s_, k in kinds.items() if k == S["K_GOBLIN"]][0]
            wide4 = [s_ for s_, k in kinds.items() if k == S["K_RAT"]][0]
            flyer = [s_ for s_, k in kinds.items() if k == S["K_BAT"]][0]
            gy = stand_y(0, game.body(p, S["K_GOBLIN"])[1])
            ry = stand_y(0, game.body(p, S["K_RAT"])[1])
            if kind == "wide":
                pp, W = dsc[S["RD_PITCOL"]], dsc[S["L2_PITW"]]
                for left, x0, keys, xs_stand, xf in ((False, pp - 3, "L", (pp - 2, pp - 1), pp),
                                                      (True, pp + W, "H", (pp + W - 1, pp + W - 2), pp + W - 3)):
                    hero_at(x0, left=left)
                    xs = []
                    for _ in range(4):
                        p.turn(keys)
                        e = p.ent(0)
                        xs.append((e["X"], e["Y"]))
                        if e["Y"] != y0:
                            break
                    e = p.ent(0)
                    check(f"{tag} (p {pp}, W {W}): walking {'left' if left else 'right'} stands at "
                          f"{xs_stand}, falls at x {xf} onto storey 1, 1d4",
                          xs == [(xs_stand[0], y0), (xs_stand[1], y0), (xf, y1)] and 16 <= e["HP"] <= 19
                          and e["MODE"] == 0, (xs, e["HP"], e["MODE"]))
                    p.settle()
                    bad = screens_ok(tag + " fell")
                    check(f"{tag}: after the fall both screens == ROOM_MAP", bad == [], bad[:3])
                for left, x0, xf in ((False, pp - 3, pp + W - 3), (True, pp + W, pp)):
                    hero_at(x0, left=left)
                    ok = p.turn("K", "H" if left else "L")
                    e = p.ent(0)
                    check(f"{tag}: a jump {'left' if left else 'right'} from x {x0} is cut short, falls at {xf}",
                          (ok, e["X"], e["Y"]) == (True, xf, y1) and e["HP"] < 20, (ok, e["X"], e["Y"], e["HP"]))
                    p.settle()
                hero_at(14, y1)
                res = [stub_step(walker, pp - 2, gy, 1), stub_step(walker, pp - 1, gy, 1),
                       stub_step(wide4, pp + W - 1, ry, -1), stub_step(wide4, pp + W - 2, ry, -1)]
                check(f"{tag}: walkers take p-1 / p+W-2, refuse p / p+W-3 (goblin, rat)",
                      res == [0xFF, 0, 0xFF, 0], res)
                fy = stand_y(0, game.body(p, S["K_BAT"])[1])
                res = [stub_step(flyer, pp - 1, fy, 1), stub_step(flyer, pp + 1, fy, 1)]
                check(f"{tag}: a flyer crosses the span", res == [0xFF, 0xFF], res)
            else:
                b, w = dsc[S["L2_MIDB"]], dsc[S["L2_MIDW"]]
                hero_at(b - 4)
                ok1 = p.turn("L") and p.ent(0)["X"] == b - 3
                ok2 = p.no_turn("L") and p.ent(0)["X"] == b - 3
                ok3 = p.no_turn("K", "L") and p.ent(0)["X"] == b - 3
                hero_at(b - 6)
                ok4 = p.no_turn("K", "L")
                hero_at(b + w + 1, left=True)
                ok5 = p.turn("H") and p.ent(0)["X"] == b + w
                ok6 = p.no_turn("H") and p.ent(0)["X"] == b + w
                ok7 = p.no_turn("K", "H") and p.ent(0)["X"] == b + w
                check(f"{tag} (b {b}, w {w}): walks onto the rubble cols, the block stops walking "
                      "and jumping from both faces (no turn)", (ok1, ok2, ok3, ok4, ok5, ok6, ok7) == (True,) * 7,
                      (ok1, ok2, ok3, ok4, ok5, ok6, ok7, p.ent(0)["X"]))
                hero_at(14, y1)
                rw = game.body(p, S["K_RAT"])[0]
                res = [stub_step(wide4, b - rw - 1, ry, 1), stub_step(wide4, b - rw, ry, 1),
                       stub_step(walker, b + w + 1, gy, -1), stub_step(walker, b + w, gy, -1)]
                check(f"{tag}: walkers stop at both faces (rat, goblin)", res == [0xFF, 0, 0xFF, 0], res)
            # re-entry byte-identical (W12): build, leave via another room, rebuild
            other = [x for x in present_rooms(blk) if x != r][0]
            ok1, _ = show_room(p, r)
            a = snapshot(p)
            ok2, _ = show_room(p, other)
            ok3, _ = show_room(p, r)
            b_ = snapshot(p)
            check(f"{tag}: re-entry == first entry (ROOM_MAP, bank 5, screen 2, shadow)",
                  ok1 and ok2 and ok3 and a == b_, [i for i in range(4) if a[i] != b_[i]])
    finally:
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
            # C3-8a: DOWN with no ladder below is a wait now (game.md §2.3): a turn
            check("W2 J at the bottom storey, no hole: a wait (1 turn)", p.turn("J"), "")
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
            p.turn("WAIT")
            measured("W8 jump", "K", "L")
            check("W8 jump again after a non-jump turn: x + 6", hero()["X"] == pit + 8, hero()["X"])
            # J1 (user 2026-10-06, §2.4): a jump landing on x == p falls (1d4)
            def free_jump():
                p.wb("JUMP_TURN", 0xFF)                # "not twice in a row" off
                p.wb(S["JUMP_TURN"] + 1, 0xFF)
            for left in (False, True):
                tag = "left (K+H)" if left else "right (K+L)"
                p.isolate()
                free_jump()
                p.place(0, pit + 6 if left else pit - 6, y0, flags=HERO_R | (EF_LEFT if left else 0))
                p.set_ent(0, HP=20)
                t0 = p.rw("TURN_COUNTER")
                samples = []
                ok = p.turn("K", "H" if left else "L",
                            per_tick=lambda fr, e: samples.append((e["PX"], e["PY"], e["MODE"])))
                e = hero()
                check(f"W8 jump {tag} onto x == p: falls to storey 1 at x = p, 1 turn",
                      (ok, e["X"], e["Y"], p.rw("TURN_COUNTER") - t0, e["MODE"]) == (True, pit, y1, 1, 0),
                      (ok, e["X"], e["Y"], p.rw("TURN_COUNTER") - t0, e["MODE"]))
                check(f"W8 jump {tag} into the pit: 1d4 damage", 1 <= 20 - e["HP"] <= 4, e["HP"])
                pys = [py for _, py, _ in samples]
                rise = [v - 8 * y0 for v in pys if v < 8 * y0]
                drop = [(px, py) for px, py, _ in samples if py > 8 * y0]
                last_up = max(i for i, v in enumerate(pys) if v < 8 * y0)
                first_dn = min(i for i, v in enumerate(pys) if v > 8 * y0)
                check(f"W8 jump {tag} into the pit: the full D = 6 arc, then the 9-row drop at px = 8p",
                      rise == [-4, -8, -12, -16, -16, -16, -16, -16, -12, -8, -4]
                      and [py for _, py in drop if py < 8 * y1] + [8 * y1]
                      == list(range(8 * y0 + 8, 8 * y1 + 1, 8))
                      and all(px == 8 * pit for px, _ in drop) and first_dn > last_up, samples)
                p.settle()
            w4("W8 jump fall")
            # wide pit (room B's L2_PITW poked to W = 5, logic only: the map
            # keeps 3 holes; W26 plays real generated wide pits): a jump whose
            # span holds a hole is cut short and falls at x_f = p+W-3 (right) /
            # p (left), arc 2 |x_f - x| ticks
            pitw_b = S["ROOM_DESC"] + S["RD_STRIDE"] + S["L2_PITW"]
            p.wb(pitw_b, 5)
            for left, x0, xf in ((False, pit - 3, pit + 2), (True, pit + 5, pit)):
                p.isolate()
                free_jump()
                p.place(0, x0, y0, flags=HERO_R | (EF_LEFT if left else 0))
                p.set_ent(0, HP=20)
                samples = []
                ok = p.turn("K", "H" if left else "L",
                            per_tick=lambda fr, e: samples.append((e["PX"], e["PY"])))
                e = hero()
                rise = [py - 8 * y0 for _, py in samples if py < 8 * y0]
                check(f"W8 wide pit (L2_PITW 5 poked) {'left' if left else 'right'}: cut short, falls at x_f",
                      (ok, e["X"], e["Y"], rise) == (True, xf, y1, [-4, -8, -12, -16, -16, -16, -16, -16, -12, -8]),
                      (ok, e["X"], e["Y"], rise))
                p.settle()
            p.wb(pitw_b, 0)
            p.isolate()
            free_jump()
            p.place(0, pit - 6, y0, flags=HERO_R)
            measured("W8 jump into the pit", "K", "L")
            p.settle()
            # J1 low-body extension (§2.4): Rat / Spider (K_SPIDER == K_RAT, 32x16)
            def jtry(x0, left, bodies):
                """Hero at x0 on storey 0, bodies = [(slot, x, h)]: K+H / K+L.
                Returns the hero's x after the jump, None when no turn ran;
                jtry.rise = the arc's py offsets, one per tick."""
                p.isolate()
                free_jump()
                for slot, bx, bh in bodies:
                    p.place(slot, bx, stand_y(0, bh), room=1, flags=MON_L)
                p.place(0, x0, y0, flags=HERO_R | (EF_LEFT if left else 0))
                p.set_ent(0, HP=20)                    # the falls / rat bites add up
                samples = []
                ok = p.turn("K", "H" if left else "L", per_tick=lambda fr, e: samples.append(e["PY"]))
                x = hero()["X"] if ok else None
                for slot, _, _ in bodies:
                    p.set_ent(slot, ROOM=NOWHERE)
                p.settle()
                jtry.rise = [v - 8 * y0 for v in samples if v < 8 * y0]
                return x
            xr = 3
            xj = jtry(xr, False, [(SLOT_RAT, xr + 3, 2)])
            check("W8 jump over an adjacent Rat (r = x+3): D = 7, lands at x + 7", xj == xr + 7, xj)
            samples7 = jtry.rise
            free_jump()
            p.place(0, xr, y0, flags=HERO_R)
            p.place(SLOT_RAT, xr + 3, stand_y(0, 2), room=1, flags=MON_L)
            measured("W8 jump D = 7", "K", "L")
            p.set_ent(SLOT_RAT, ROOM=NOWHERE)
            p.settle()
            check("W8 D = 7 arc: -4,-8,-12,-16 x7,-12,-8,-4 (14 airborne ticks)",
                  samples7 == [-4, -8, -12] + [-16] * 7 + [-12, -8, -4], samples7)
            check("W8 jump left over an adjacent Rat/Spider (mirror): lands at x - 7",
                  jtry(xr + 10, True, [(SLOT_RAT, xr + 10 - 4, 2)]) == xr + 3, hero()["X"])
            check("W8 jump refused: a Rat at r = x+4 (overlaps x+7)",
                  jtry(xr, False, [(SLOT_RAT, xr + 4, 2)]) is None, hero()["X"])
            check("W8 jump refused (left): a Rat at r = x-5 (overlaps x-7 .. x-5)",
                  jtry(xr + 10, True, [(SLOT_RAT, xr + 10 - 5, 2)]) is None, hero()["X"])
            check("W8 jump over an adjacent Slime (3 wide): D = 6",
                  jtry(xr, False, [(2, xr + 3, 2)]) == xr + 6, hero()["X"])
            check("W8 jump refused: adjacent Rat, a Goblin in the D = 7 landing box",
                  jtry(xr, False, [(SLOT_RAT, xr + 3, 2), (SLOT_GOBLIN, xr + 9, 4)]) is None, hero()["X"])
            check("W8 jump refused: a Goblin in the D = 6 landing box",
                  jtry(xr, False, [(SLOT_GOBLIN, xr + 6, 4)]) is None, hero()["X"])
            p.isolate()
            free_jump()
            p.set_ent(0, HP=20)
            p.place(0, pit + 1, y0, flags=HERO_R | EF_LEFT)
            measured("W8 fall", "H")
            # more jump legality (game.md §2.4)
            p.isolate()
            p.place(0, pit + 5, y0, flags=HERO_R | EF_LEFT)
            check("W8 jump left (K+H): x - 6", p.turn("K", "H") and hero()["X"] == pit - 1, hero()["X"])
            p.turn("WAIT")
            p.place(0, 6, y0, flags=HERO_R | EF_LEFT)
            check("W8 jump to x' = 0 refused", p.no_turn("K", "H"), "")
            p.place(0, 7, y0, flags=HERO_R | EF_LEFT)
            check("W8 jump to x' = 1 allowed", p.turn("K", "H") and hero()["X"] == 1, hero()["X"])
            p.turn("WAIT")
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
                p.turn("WAIT")
                xs.append(p.ent(SLOT_RAT)["X"])
            check("W9 rat patrol on storey 0 never steps onto x == p (reverses at p+1)",
                  pit not in xs and min(xs) == pit + 1, xs)
            p.place(SLOT_RAT, 10, stand_y(0, 2), room=NOWHERE)
            p.place(SLOT_BATB, pit + 3, stand_y(0, 2), room=1, flags=MON_L)
            xs = []
            for _ in range(8):
                p.turn("WAIT")
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
            p.hold("WAIT")
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
            w15_icons(p, check)

        # ================= B3B-13: token text (W17) ======================
        if want("W17"):
            w17(p, check)

        # ================= C3-0: far1 / bank-1 code (W18) =====================
        if want("W18"):
            w18(p, check)

        # ================= C3-1: read_stick input (W19) =====================
        if want("W19"):
            w19(p, check)

        # ================= C3-2: turn-intent machine (W22 / W23) ============
        for tag in ("W22", "W23"):
            if want(tag):
                w22_23(p, check, tag)

        # ================= C3-6: menu / pause / cards (W24) =================
        if want("W24"):
            w24(p, check)

        # ================= C3-8b: joystick-only runs (W25) ===================
        if want("W25"):
            w25(p, check)

        # ================= C3-1 review: stack low-water (W20) =================
        if want("W20"):
            w20(p, check)

        # ================= B11: storey-0 exits, invisible pit (W21) ========
        if want("W21"):
            w21_exits(p, check)

        # ================= L2: wide pits + mid-room blocks (W26) ============
        if want("W26"):
            w26_l2(p, check)

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
    game_lib.Proto.snd_mode = 2                   # SND-4a: no stinger hold in descents (music not under test)
    sys.exit(main())
