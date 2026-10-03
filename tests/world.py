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

  B3B-11 (panel engine, concept-screen §5; D5 queue: one item per tick, never
  in a turn's input tick):
  W15 static panel at start (log line, attrs, depth, HP / potion fields);
      quaff: the input tick leaves the panel untouched, the HP number / bar,
      the log line and the potion count are composed <= 3 ticks after it and
      displayed one tick later; 3 pushed messages: 2-row scroll (rows 22 / 23
      == the last two, attrs $07 / $47); the 2nd-frame budget path (scroll,
      then LOG_CHUNK chars per step); ring overflow drops + counts; HP bar fill
      == round(32 * hp / max); T of a whole log item (scroll + 32 chars) and
      of print6 per char; the Mage's panel golden (w15_panel_mage).

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


def build_only(p, r):
    """far3 build_room_map (room r -> ROOM_MAP). -> (ok, T, map)."""
    ok, t = run_code(p, head() + [0x3E, r, 0x16, S["ROOM_MAP"] >> 8, 0x21] + w16(S["build_room_map"])
                     + [0xCD] + w16(S["far3"]))
    return ok, t, bytes(p.z.read_memory(S["ROOM_MAP"], 32 * PLAY_ROWS))


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
    MSG = {k: S[k] for k in ("str_found", "str_locked", "str_fall", "str_died", "str_quaff")}
    TXT = {"str_found": "YOU FOUND A POTION", "str_locked": "THE DOOR IS LOCKED",
           "str_fall": "YOU FALL INTO A PIT", "str_died": "YOU DIED - PRESS ENTER",
           "str_quaff": "YOU DRINK A POTION"}
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
            code += [0x21] + w(MSG[n]) + [0xCD] + w(S["log_push"])
        stub(code, "push " + ",".join(names))

    def step(lim):
        return stub([0x3E, lim, 0x32] + w(S["P_LIM"]) + [0xCD] + w(S["panel_step"]), f"panel_step lim {lim}",
                    measure=True)

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
    check("W15 start: log row 23 = FIND THE TREASURE, row 22 blank",
          (log_row(fr, 23), log_row(fr, 22)) == (text6("FIND THE TREASURE"), text6("")), "")
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
    check("W15 quaff: scroll: row 22 = the previous newest line (FIND THE TREASURE)",
          log_row(p.composed_frame(), 22) == text6("FIND THE TREASURE"), "")

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
    check("W15 3 messages drained in 3 idle ticks (one item per tick)", n == 3, n)
    check("W15 scroll after 3: row 22 = THE DOOR IS LOCKED, row 23 = YOU FALL INTO A PIT (displayed)",
          (log_row(fr, 22), log_row(fr, 23)) == (text6(TXT["str_locked"]), text6(TXT["str_fall"])), "")
    check("W15 displayed == composed after the drain", fr == p.composed_frame(), "")

    # --- 2nd-frame budget path: scroll, then LOG_CHUNK chars per step -----
    chunk = S["LOG_CHUNK"]
    died = TXT["str_died"]
    push("str_died")
    t_scroll = step(chunk)
    comp = p.composed_frame()
    check("W15 chunked: step 1 = scroll only (row 22 = old 23, row 23 blank)",
          (log_row(comp, 22), log_row(comp, 23)) == (text6(TXT["str_fall"]), text6("")), "")
    t_c1 = step(chunk)
    check(f"W15 chunked: step 2 = the first {chunk} chars", log_row(p.composed_frame(), 23) == text6(died[:chunk]), "")
    t_c2 = step(chunk)
    check("W15 chunked: step 3 = the whole line, queue empty",
          (log_row(p.composed_frame(), 23), p.rb("LOG_QN"), p.rb("PANEL_DIRTY") & S["PD_LOG"]) ==
          (text6(died), 0, 0), "")
    p.tick(2)
    check("W15 chunked: displayed == composed", p.frame() == p.composed_frame(), "")

    # --- ring overflow -----------------------------------------------------
    push("str_found", "str_locked", "str_fall", "str_quaff", "str_died")
    check("W15 ring full: 5th push dropped (LOG_QN 4, LQ_DROP 1)",
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
    check("W15 32-char line drawn whole (P_LIM 0)", log_row(p.composed_frame(), 23) == text6(long32), "")
    push("long")
    t_s = step(chunk)                            # scroll alone
    t_p = step(0)                                # 32 chars alone
    p.tick(2)
    print(f"[info] W15 measured (contended, ZEsarUX): whole log item scroll + 32 chars {t_whole} T;"
          f" scroll of 24 cols {t_s} T; print 32 chars {t_p} T (~{t_p // 32} T/char incl. step);"
          f" chunked 22-char line: scroll {t_scroll} + {t_c1} + {t_c2} T", flush=True)
    check("W15 whole log item <= 30k T (first-frame ticks only: < 70.9k T used before it)", t_whole <= 30000, t_whole)
    check(f"W15 2nd-frame log steps <= 9k T each", max(t_scroll, t_c1, t_c2, t_s) <= 9000,
          (t_scroll, t_c1, t_c2, t_s))

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


def present_rooms(blk):
    return [r for r in range(9) if room_model.field(blk, r, "RD_FLAGS") & S["RDF_PRESENT"]]


def wall_decor_ids(d):
    """Tile ids of the wall-class decor objects (tools/decorgen.py: placed on
    T_BRICK cells only, so also on block cells) of depth d, common + per level."""
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
    import decorgen as DG
    ids = set()
    for name, base, w, h, fl in DG.COMMON + DG.level_objects()[d]:
        if fl & DG.F_WALL:
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
            if xc and not grate_open and row == F1 and xc <= c < xc + 3:
                on_lad = False                 # under the closed grate
                if t != T["T_GRATE"]:
                    bad.append(("grate", c, row, t))
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
            legal |= {attrs[T[k]] for k in ("T_CHAIN", "T_SKULLS", "T_TORCH_T", "T_TORCH_B", "T_CANDLES")}
            for r in present_rooms(blk):
                ok, tb, m = build_only(p, r)
                note("build_room_map", tb, f"D{d} r{r}")
                want_m = room_model.render_room(blk, r)
                bad = [(i % 32, i // 32, m[i], want_m[i]) for i in range(len(want_m)) if m[i] != want_m[i]]
                check(f"W11 D{d} r{r}: map == the spec model", ok and not bad, bad[:4])
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
    if want("W13"):
        rng = __import__("random").Random(0xB39)
        nroom = nplaced = 0
        sizes = {"anim": 0, "wall": 0, "air": 0}
        SOLID, ANIMF = S["TF_SOLID"], S["TF_ANIM"]
        T_AIR, T_BRICK = T["T_AIR"], T["T_BRICK"]
        lad = set(range(T["T_LAD_L"], T["T_HOLE_R"] + 1))
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
                if i < 3 and r % 3 == 0:                  # decor cost: build with RD_SEED zeroed
                    da = S["ROOM_DESC"] + r * S["RD_STRIDE"] + S["RD_SEED"]
                    sv = bytes(p.z.read_memory(da, 2))
                    p.z.cmd("write-memory %d 0 0" % da)
                    _, t0, _ = build_only(p, r)
                    p.z.cmd("write-memory %d %d %d" % (da, sv[0], sv[1]))
                    dT.append(t1 - t0)
                # ---- independent rules ----
                errs = []
                ch = [j for j in range(576) if m[j] != base[j]]
                for j in ch:
                    c, row = j % 32, j // 32
                    if base[j] == T_AIR:
                        sizes["air"] += 1
                        if flags[m[j]] & SOLID:
                            errs.append(("solid decor on an air cell", c, row))
                    elif base[j] == T_BRICK:
                        sizes["wall"] += 1
                        if not flags[m[j]] & SOLID:
                            errs.append(("non-solid decor on a wall cell", c, row))
                        if row % 9 == 0:
                            errs.append(("wall decor on the lintel row", c, row))
                    else:
                        errs.append(("decor on a structural cell", c, row, base[j]))
                    if row % 9 > 5:
                        errs.append(("decor in the 2 rows above a floor / floor row", c, row))
                    for dr in (-1, 0, 1):
                        for dc in (-1, 0, 1):
                            rr, cc = row + dr, c + dc
                            if 0 <= rr < 18 and 0 <= cc < 32 and base[rr * 32 + cc] in lad:
                                errs.append(("decor adjacent to a ladder", c, row))
                wallc = sum(1 for j in ch if base[j] == T_BRICK)
                if wallc > 6:
                    errs.append(("more than 6 wall-class cells", wallc))
                ents = [got_al[k:k + 4] for k in range(0, len(got_al), 4)]
                gl = [e for e in ents if e[2] >= 16]
                at = [e for e in ents if e[2] < 16]
                if len(gl) > 4 or len(at) > 8 or n > 12:
                    errs.append(("anim budget", len(gl), len(at)))
                cells = {(e[0], e[1]) for e in ents}
                for e in ents:
                    if e[0] > 31 or e[1] > 17:
                        errs.append(("ANIM entry off the map", e))
                        continue
                    if m[e[1] * 32 + e[0]] == base[e[1] * 32 + e[0]] or e[2] == 0:
                        errs.append(("ANIM entry not on a decor cell", e))
                    if e[2] >= 16 and not flags[m[e[1] * 32 + e[0]]] & ANIMF:
                        errs.append(("glyph-swap entry on a non-TF_ANIM id", e))
                for j in ch:
                    if flags[m[j]] & ANIMF and (j % 32, j // 32) not in cells:
                        errs.append(("TF_ANIM decor cell missing from ANIM_LIST", j % 32, j // 32))
                # large animated objects: 4-connected clusters holding a glyph entry
                gset = {(e[0], e[1]) for e in gl}
                seen, nclu = set(), 0
                for cell in cells:
                    if cell in seen:
                        continue
                    stack, comp = [cell], set()
                    while stack:
                        x = stack.pop()
                        if x in comp or x not in cells:
                            continue
                        comp.add(x)
                        stack += [(x[0] + 1, x[1]), (x[0] - 1, x[1]), (x[0], x[1] + 1), (x[0], x[1] - 1)]
                    seen |= comp
                    nclu += bool(comp & gset)
                if nclu > 2:
                    errs.append(("more than 2 large animated objects", nclu))
                nplaced += len(ch)
                sizes["anim"] += n
                check(f"W13 D{d} seed {seed:#06x} r{r}: decor rules (independent checker)", not errs, errs[:3])
        print(f"[info] W13: {nroom} rooms, {nplaced} decor cells (air {sizes['air']}, wall {sizes['wall']}), "
              f"{sizes['anim']} anim entries; decor_room cost T = {sorted(dT)}", flush=True)
        check("W13: >= 50 rooms over depths 1..8, decor present and animated",
              nroom >= 50 and nplaced > 100 and sizes["anim"] > 0 and sizes["wall"] > 0, (nroom, nplaced, sizes))
    if worst:
        print("[info] B3B-8 measured (DI, contended): " + ", ".join(
            f"{k} worst {v[0]} T ({v[1]})" for k, v in worst.items()), flush=True)
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

        # ================= B3B-11: panel engine (W15) =====================
        if want("W15"):
            w15(p, check)

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
