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
  W4  after every W1-W3 step: displayed (bank 7) == composed (bank 5), and every
      playfield cell outside the drawn sprites shows exactly its ROOM_MAP tile
      (glyph + attr) on both screens; no attr in rows 0..17 outside the tile /
      sprite set.

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
                      MAP_LEN, GS_PLAYING, K_KNIGHT, EF_LEFT)

ONLY = {a.upper() for a in _argv}
ROOMS = ("room_a", "room_b", "room_c", "room_d")
EXIT_NONE = 0xFF


def want(tag):
    return not ONLY or tag in ONLY


def desc(p, r):
    """Parsed PROTO descriptor (data.asm layout) of room r."""
    a = S[ROOMS[r]]
    b = p.z.read_memory(a, 64)
    exits = dict(Ls=b[0], Ld=b[1], Rs=b[2], Rd=b[3], U=b[4], D=b[5])
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
    open_rows = {0: set(), 31: set()}
    for side, col in (("L", 0), ("R", 31)):
        s = exits[side + "s"]
        if s != EXIT_NONE:
            open_rows[col] = set(range(STOREY_ROWS * s, STOREY_ROWS * s + STOREY_AIR))
    for row in range(PLAY_ROWS):
        floor = (row + 1) % STOREY_ROWS == 0
        for c in range(32):
            t = cell(c, row)
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
            p.place(0, 1, y1)                       # C's left exit is on storey 1
            go("H", 3, "L exit C->D", (32 - 1 - kw, y1))
            go("L", 2, "R exit D->C", (1, y1))

        print(f"[info] run anomalies (returns outside a probe): {game.Proto.anomalies}", flush=True)
        check("harness: no run anomalies", game.Proto.anomalies == 0, game.Proto.anomalies)
    print(f"[{'FAIL' if fails else 'PASS'}] world W0-W4: {len(fails)} failing: {fails[:8]}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
