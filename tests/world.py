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

Usage: ZRCP_PORT=10001 python3 tests/world.py [W1 W3 ...]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_argv = sys.argv[1:]
sys.argv = [sys.argv[0], "999"]               # keep game.py's item filter inert
import game  # noqa: E402
from game_lib import (Harness, S, EMU_ARGS, attr_at, cell_bytes, split_frame,  # noqa: E402
                      stand_y, is_standing, item_row, ladder_rows, ROOM_LADDERS,
                      STOREY_ROWS, STOREY_AIR, STOREY_COUNT, PLAY_ROWS, PANEL_ROW,
                      MAP_LEN, GS_PLAYING, GS_DEAD, K_KNIGHT, EF_LEFT, EF_ACTIVE,
                      EF_PLAYER, EF_HOSTILE, EF_PENDING)

ONLY = {a.upper() for a in _argv}
ROOMS = ("room_a", "room_b", "room_c", "room_d")
EXIT_NONE = 0xFF


def want(tag):
    return not ONLY or tag in ONLY


def desc(p, r):
    """Parsed PROTO descriptor (data.asm layout) of room r."""
    a = S[ROOMS[r]]
    b = p.z.read_memory(a, 64)
    exits = dict(Ls=b[0], Ld=b[1], Rs=b[2], Rd=b[3], U=b[4], D=b[5],
                 eL=b[S["RD_EDGE_L"]], eR=b[S["RD_EDGE_R"]],
                 pit=b[S["RD_PITCOL"]], block=b[S["RD_BLOCK"]])
    n = b[S["RD_LADDERS"]]
    o = S["RD_LADDERS"] + 1
    lad = [(b[o + 2 * i], b[o + 2 * i + 1]) for i in range(n)]
    o += 2 * n
    npot = b[o]
    pots = [tuple(b[o + 1 + 3 * i:o + 4 + 3 * i]) for i in range(npot)]
    return exits, lad, pots


class W(game.T):
    def screen_vs_map(self, tag):
        """W4: both screens == ROOM_MAP outside sprite footprints; displayed ==
        composed. Returns a list of problems (empty = ok)."""
        bad = []
        fr, comp = self.frame(), self.composed_frame()
        if fr != comp:
            diff = [i for i in range(len(fr)) if fr[i] != comp[i]]
            bad.append((tag, "displayed != composed", len(diff), diff[0]))
        rmap = self.z.read_memory(S["ROOM_MAP"], MAP_LEN)
        glyphs = self.z.read_memory(S["TILE_GLYPHS"], S["TILE_IDS"] * 8)
        attrs = self.z.read_memory(S["TILE_ATTRS"], S["TILE_IDS"])
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
                    t = rmap[r * 32 + c]
                    if attr_at(f, c, r) != attrs[t] or cell_bytes(f, c, r) != glyphs[t * 8:t * 8 + 8]:
                        cells.append((c, r, t))
            if cells:
                bad.append((tag, scr + " cells != ROOM_MAP", len(cells), cells[:4]))
        return bad


def feature_cells(p, exits):
    """B3B-5: {(col, row): tile} of the doors (EDGE_TAB state), the storey-0
    pit and the dead-end block of a room (concept-screen §3.1, game.md §2.5,
    level_defs.asm RD_BLOCK)."""
    out = {}
    edge = p.z.read_memory(S["EDGE_TAB"], S["EDGES_H"])
    for side, c0 in (("L", 0), ("R", 32 - S["DOOR_COLS"])):
        e, st = exits["e" + side], exits[side + "s"]
        if e >= S["EDGES_H"] or not edge[e] & S["EG_DOOR"]:
            continue
        top = STOREY_ROWS * st
        out[(c0, top)] = out[(c0 + 1, top)] = S["T_BRICK"]
        out[(c0, top + 1)], out[(c0 + 1, top + 1)] = S["T_DOOR_ARCH_L"], S["T_DOOR_ARCH_R"]
        lock = edge[e] & (S["EG_LOCK"] | S["EG_SEAL"])
        for row in range(top + 2, top + STOREY_AIR):
            if edge[e] & S["EG_OPEN"]:                # B10: open = the jambs
                out[(c0, row)], out[(c0 + 1, row)] = S["T_DOOR_JAMB_L"], S["T_DOOR_JAMB_R"]
            else:
                out[(c0, row)] = S["T_DOOR_L"]
                out[(c0 + 1, row)] = S["T_DOOR_LOCK"] if lock else S["T_DOOR_R"]
    pit = exits["pit"]
    if pit:
        f0 = STOREY_AIR
        out[(pit - 1, f0)], out[(pit + 3, f0)] = S["T_PIT_L"], S["T_PIT_R"]
        for c in range(pit, pit + 3):
            out[(c, f0)] = S["T_AIR"]
    blk = exits["block"]
    w = blk & S["RDB_WMASK"]
    if w:
        st = 1 if blk & S["RDB_S1"] else 0
        cols = range(32 - w, 32) if blk & S["RDB_RIGHT"] else range(w)
        for c in cols:
            for row in range(STOREY_ROWS * st, STOREY_ROWS * st + STOREY_AIR):
                out[(c, row)] = S["T_BRICK"]
            out[(c, STOREY_ROWS * st + STOREY_AIR)] = S["T_WALLF"]
        out[((31 - w) if blk & S["RDB_RIGHT"] else w, STOREY_ROWS * st + STOREY_AIR - 1)] = S["T_RUBBLE"]
    return out


def map_structure(p, r):
    """W0: the engine-built ROOM_MAP of room r (CUR_ROOM) against its descriptor."""
    T = {k: S[k] for k in ("T_AIR", "T_PLAT", "T_BRICK", "T_WALLF", "T_LAD_L", "T_HOLE_L",
                           "T_POTION", "T_END_L", "T_END_R")}
    m = p.z.read_memory(S["ROOM_MAP"], MAP_LEN)
    exits, lad, pots = desc(p, r)
    cell = lambda c, row: m[row * 32 + c]
    bad = []
    ladder_cells = {}
    for col, s in lad:
        for row in ladder_rows(s):
            for k in range(3):
                floor = (row + 1) % STOREY_ROWS == 0
                ladder_cells[(col + k, row)] = (T["T_HOLE_L"] if floor else T["T_LAD_L"]) + k
    taken = p.rb("POTIONS_TAKEN")
    pot_cells = {(col, item_row(s)) for pid, col, s in pots if not taken & (1 << pid)}
    special = feature_cells(p, exits)
    open_rows = {0: set(), 31: set()}
    for side, col in (("L", 0), ("R", 31)):
        s = exits[side + "s"]
        if s != EXIT_NONE:
            open_rows[col] = set(range(STOREY_ROWS * s, STOREY_ROWS * s + STOREY_AIR))
    for row in range(PLAY_ROWS):
        floor = (row + 1) % STOREY_ROWS == 0
        for c in range(32):
            t = cell(c, row)
            if (c, row) in special:
                if t != special[(c, row)]:
                    bad.append((r, c, row, t, special[(c, row)], "B3B-5 feature"))
                continue
            if (c, row) in ladder_cells:
                want_t = ladder_cells[(c, row)]
            elif (c, row) in pot_cells:
                want_t = T["T_POTION"]
            elif c in (0, 31):
                want_t = T["T_AIR"] if row in open_rows[c] else (T["T_WALLF"] if floor else T["T_BRICK"])
                if not floor and t in (S["T_TORCH_T"], S["T_TORCH_B"]):
                    continue                     # decor on a wall cell (room A)
            elif floor:
                want_t = (T["T_PLAT"], T["T_END_L"], T["T_END_R"])
            else:
                want_t = None                    # air band: air or decor
            if isinstance(want_t, tuple):
                if t not in want_t:
                    bad.append((r, c, row, t, "floor"))
            elif want_t is not None and t != want_t:
                bad.append((r, c, row, t, want_t))
            if not floor and want_t is None and t in (T["T_PLAT"], T["T_WALLF"]):
                bad.append((r, c, row, t, "floor tile in an air row"))
    # holes only in floor rows and only under a ladder; the down-exit hole only
    # in row 17 and only when the room has a down exit
    for col, s in lad:
        if s == STOREY_COUNT and exits["D"] == EXIT_NONE:
            bad.append((r, "down-exit hole without a D exit", col))
        if s == 0 and exits["U"] == EXIT_NONE:
            bad.append((r, "up-exit shaft without a U exit", col))
    return bad


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
            for r in range(4):
                _, lad, _ = desc(p, r)
                check(f"W0 room {'ABCD'[r]} ladders == game_lib.ROOM_LADDERS", lad == ROOM_LADDERS[r],
                      (lad, ROOM_LADDERS[r]))
            e = hero()
            check("W0 start: room A, x 2, standing on storey 1 (y = 9+8-h)",
                  (p.rb("CUR_ROOM"), e["X"], e["Y"]) == (0, 2, stand_y(1, kh)), (e["X"], e["Y"]))
            bad = map_structure(p, 0)
            check("W0 room A map structure", bad == [], bad[:4])
            w4("start")
            pf, pn = split_frame(p.frame())
            check("W0 panel rows 18-20 blank at start (only HUD text on 21-23)",
                  all(b == 0 for b in pn[:3 * 8 * 32]), "")
            # split_frame panel = 6 rows x 256 bitmap B, then 6 x 32 attrs
            pa = pn[6 * 256:6 * 256 + 3 * 32]
            check("W0 panel rows 18-20 attrs == ATTR_HUD (3 x 32 cells)",
                  all(b == S["ATTR_HUD"] for b in pa), sorted({hex(b) for b in pa}))

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
                check(f"W3 {tag}: CUR_ROOM {'ABCD'[dest]}, arrival (x, y) = {want_xy}",
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
                check(f"W3 {tag}: room {'ABCD'[dest]} map structure", bad == [], bad[:4])
                w4(tag)
                p.isolate()

            p.place(0, 32 - 1 - kw, y1)             # A, right edge of storey 1
            go("L", 1, "R exit A->B", (1, y1))
            p.place(0, 24, y1)                      # B: down-exit {24,2}
            go("J", 2, "D exit B->C", (24, y0))
            go("K", 1, "U exit C->B", (24, y1))
            p.place(0, 1, y1)
            go("H", 0, "L exit B->A", (32 - 1 - kw, y1))
            # C <-> D on storey 1: via B -> C again
            p.place(0, 32 - 1 - kw, y1)
            go("L", 1, "R exit A->B (2)", (1, y1))
            p.place(0, 24, y1)
            go("J", 2, "D exit B->C (2)", (24, y0))
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
            go("H", 3, "L exit C->D", (32 - 1 - kw, y1))
            go("L", 2, "R exit D->C", (1, y1))

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
            row = S["HUD_ROW"] + 1
            ink = any(cell_bytes(p.composed_frame(), c, row) != bytes(8) for c in range(18))
            check("W6 the message row shows text (THE DOOR IS LOCKED)", ink, "")
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
            p.until(lambda: p.rb("CUR_ROOM") == 2 and p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
            p.isolate()
            p.place(0, 2, y1, flags=HERO_R | EF_LEFT)
            for _ in range(3):
                p.turn("H")
            p.until(lambda: p.rb("CUR_ROOM") == 3 and p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
            p.isolate()
            check("W8 reached room D", p.rb("CUR_ROOM") == 3, p.rb("CUR_ROOM"))
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

        if worst:
            print("[info] B3B-5 measured: " + ", ".join(f"{k} {v[0]} T (input {v[1]})"
                                                       for k, v in worst.items()), flush=True)
        print(f"[info] run anomalies (returns outside a probe): {game.Proto.anomalies}", flush=True)
        check("harness: no run anomalies", game.Proto.anomalies == 0, game.Proto.anomalies)
    print(f"[{'FAIL' if fails else 'PASS'}] world W0-W4: {len(fails)} failing: {fails[:8]}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
