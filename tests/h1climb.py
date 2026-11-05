#!/usr/bin/env python3
"""H1 visible climb across vertical room exits (user rulings 2026-11-05, game.md §2.1 "H1").
PROTO rooms (B: down-exit {24,2} above C: up-exit {24,0}), the real keys and turn loop.

  D   DOWN: B storey 1, J at the shaft = one step (feet on row 17) + the exit, 1 turn; arrival in C
      at the TOP of the shaft (y 0), mid-ladder, M_REST (the climb rest pose), E_AIDIR +1; no move
      and no turn without keys (30 ticks); then J, J = 2 ordinary ladder turns to storey 0.
  U   UP: C storey 0, K = a step (y 1, still in C, 1 turn), K = head on row 0 + the exit (1 turn);
      arrival in B at the BOTTOM of the shaft (y 18 - h), mid-ladder, M_REST, E_AIDIR -1; no move
      without keys; K = 1 turn to stand on storey 1.
  R   reversal at an arrival end: B y 18-h, J = the exit back down with no step (1 turn, C y 0);
      C y 0, K = the exit back up with no step (1 turn, B y 18-h).
  T   the teleport still lands STANDING (do_exit EX_TELE through far7), also when it is read
      mid-ladder on the exit shaft (the arrival y no longer depends on EXIT_KIND alone).
  F   a follower through a vertical exit (both ways): it arrives PENDING at the shaft foot, the
      hero keeps getting turns (every key = a turn) and it materialises once he walks off.
  C   cork_check bound (bank-2 unit stub): the hero on the up-exit shaft (y 1, dir -1) with a box
      in his columns below the path -> CF 0 after the y 0 probe (it wrapped to y 255 and read past
      KT_MOD9 before); a box on row 0 -> CF 1; the hero's blocked step onto row 17 (CLIMB_BLK,
      dir +1): row 17 box -> CF 1, a box past it -> CF 0; each <= 2k T, the hero's y restored.
  W   both screens == ROOM_MAP after every arrival (world.py W4).
Both heroes for D / U. Build with -DDEBUG_KIT=0.  Usage: python3 tests/h1climb.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import game  # noqa: E402
import world  # noqa: E402
from game_lib import (Harness, S, EMU_ARGS, stand_y, is_standing, GS_PLAYING, EF_PENDING,  # noqa: E402
                      EF_ACTIVE, EF_HOSTILE, K_KNIGHT, K_WIZARD, K_GOBLIN, ROOM_B, ROOM_C)
from lp import w16  # noqa: E402

COL = 24                                        # B's down-exit = C's up-exit col
STUB = S["LOWRAM_END_3B"]
fails = []


def main():
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = world.W(h)

        def check(tag, ok, got=""):
            print(f"[{'PASS' if ok else 'FAIL'}] {tag}" + ("" if ok else f": {got}"), flush=True)
            if not ok:
                fails.append(tag)

        def hero():
            return p.ent(0)

        def turns():
            return p.rw("TURN_COUNTER")

        def settle_in(dest):
            p.until(lambda: p.rb("CUR_ROOM") == dest and p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
            p.settle()

        def w4(tag):
            bad = p.screen_vs_map(tag)
            check(f"W {tag}: displayed == composed == ROOM_MAP", bad == [], bad[:3])

        def still(tag):
            """No keys for 30 ticks: no move, no turn."""
            e0, t0 = hero(), turns()
            p.tick(30)
            e1 = hero()
            check(f"{tag}: waits mid-ladder without keys (30 ticks: same y, no turn)",
                  (e1["X"], e1["Y"], turns() - t0) == (e0["X"], e0["Y"], 0), (e0["Y"], e1["Y"], turns() - t0))

        def to_b(kw):
            """A -> B through the right exit (storey 1), real keys."""
            p.place(0, 32 - 1 - kw, stand_y(1, 6))
            p.turn("L")
            settle_in(ROOM_B)
            p.isolate()

        def arrival(tag, dest, y, aidir):
            e = hero()
            check(f"{tag}: CUR_ROOM {dest}, (x, y) = ({COL}, {y}), mid-ladder, M_REST, E_AIDIR {aidir:+d}",
                  (p.rb("CUR_ROOM"), e["X"], e["Y"], is_standing(e["Y"], 6), e["MODE"], e["AIDIR"])
                  == (dest, COL, y, False, 0, aidir & 255),
                  (p.rb("CUR_ROOM"), e["X"], e["Y"], e["MODE"], e["AIDIR"]))

        def run_code(body):
            """DI, body, record CF, EI; -> (ok, T, CF)."""
            res = STUB + 100
            code = bytes([0xF3] + body + [0x9F, 0x32] + w16(res) + [0xFB, 0x00, 0x18, 0xFE])   # sbc a,a / ld (res),a
            end = STUB + len(code) - 3
            p.z.cmd("write-memory %d %s" % (STUB, " ".join(str(b) for b in code)))
            p.z.cmd("set-breakpoint 3 PC=%d" % end)
            p.extra_probes = {end}
            pc0 = p.pc()
            p.z.cmd("set-register PC=%d" % STUB)
            p.z.cmd("reset-tstates-partial")
            p.z.cmd("run 4000000")
            ts = int(p.z.cmd("get-tstates-partial"))
            ok = p.pc() == end
            p.z.cmd("set-breakpoint 3")
            p.extra_probes = set()
            cf = p.rb(res) != 0
            p.z.cmd("set-register PC=%d" % pc0)
            return ok, ts, cf

        def do_exit_stub(kind):
            p.wb("EXIT_KIND", kind)
            pc0 = p.pc()
            code = [0xF3, 0x3E, kind, 0x21] + w16(S["do_exit"]) + [0xCD] + w16(S["far7"]) + [0xFB, 0x00, 0x18, 0xFE]
            end = STUB + len(code) - 3
            p.wmem(STUB, code)
            p.z.cmd("set-breakpoint 3 PC=%d" % end)
            p.extra_probes = {end}
            p.z.cmd("set-register PC=%d" % STUB)
            for _ in range(40):
                p.z.cmd("run 50000000")
                if p.pc() == end:
                    break
            ok = p.pc() == end
            p.z.cmd("set-breakpoint 3")
            p.extra_probes = set()
            p.z.cmd("set-register PC=%d" % pc0)
            p.settle(4)
            return ok

        p.boot(K_KNIGHT)
        kw, kh = game.body(p, K_KNIGHT)
        assert kh == 6
        yb = S["PLAY_ROWS"] - kh                  # 12: feet on row 17 (the bottom of B's shaft)
        y1, y0 = stand_y(1, kh), stand_y(0, kh)

        for hk, hn in ((K_KNIGHT, "Warrior"), (K_WIZARD, "Mage")):
            # ---- D: B -> C ---------------------------------------------------------
            p.boot(hk)
            p.isolate()
            to_b(kw)
            p.place(0, COL, y1)
            t0 = turns()
            p.turn("J")
            settle_in(ROOM_C)
            check(f"D {hn}: J at B's shaft = step + exit in 1 turn", turns() - t0 == 1, turns() - t0)
            arrival(f"D {hn}", ROOM_C, 0, 1)
            w4(f"D {hn} arrival")
            still(f"D {hn}")
            ys = []
            t0 = turns()
            for _ in range(2):
                p.turn("J")
                ys.append(hero()["Y"])
            check(f"D {hn}: J, J = 2 ladder turns to stand on storey 0 (y 1, {y0})",
                  (ys, turns() - t0, is_standing(hero()["Y"], kh), p.rb("CUR_ROOM")) == ([1, y0], 2, True, ROOM_C),
                  (ys, turns() - t0))
            # ---- U: C -> B ---------------------------------------------------------
            t0 = turns()
            p.turn("K")
            e = hero()
            check(f"U {hn}: K at C's up-exit = a plain step (y 1, still C, 1 turn)",
                  (p.rb("CUR_ROOM"), e["Y"], turns() - t0, p.rb("EXIT_KIND")) == (ROOM_C, 1, 1, 0),
                  (p.rb("CUR_ROOM"), e["Y"], turns() - t0))
            t0 = turns()
            p.turn("K")
            settle_in(ROOM_B)
            check(f"U {hn}: K = head on row 0 + exit in 1 turn", turns() - t0 == 1, turns() - t0)
            arrival(f"U {hn}", ROOM_B, yb, -1)
            w4(f"U {hn} arrival")
            still(f"U {hn}")
            # ---- R: the exits back from the arrival ends (no step) -----------------
            t0 = turns()
            p.turn("J")
            settle_in(ROOM_C)
            check(f"R {hn}: B y {yb}, J = the exit back down, no step, 1 turn", turns() - t0 == 1, turns() - t0)
            arrival(f"R {hn} down", ROOM_C, 0, 1)
            t0 = turns()
            p.turn("K")
            settle_in(ROOM_B)
            check(f"R {hn}: C y 0, K = the exit back up, no step, 1 turn", turns() - t0 == 1, turns() - t0)
            arrival(f"R {hn} up", ROOM_B, yb, -1)
            w4(f"R {hn}")
            t0 = turns()
            p.turn("K")
            check(f"U {hn}: K from the bottom end = 1 turn, standing on storey 1",
                  (hero()["Y"], turns() - t0, p.rb("CUR_ROOM")) == (y1, 1, ROOM_B), (hero()["Y"], turns() - t0))

        # ---- T: the teleport lands standing ------------------------------------------
        for tag, y in (("standing", y1), ("mid-ladder on the exit shaft", yb)):
            p.boot(K_KNIGHT)
            p.isolate()
            to_b(kw)
            p.place(0, COL, y)
            ok = do_exit_stub(S["EX_TELE"])
            e = hero()
            check(f"T teleport from {tag}: lands standing (y {y1} / {y0}), EXIT_KIND 0",
                  ok and e["Y"] in (y1, y0) and is_standing(e["Y"], kh) and p.rb("EXIT_KIND") == 0
                  and e["MODE"] == 0, (ok, e["X"], e["Y"], p.rb("CUR_ROOM"), p.rb("EXIT_KIND")))
            w4(f"T {tag}")

        # ---- F: followers through the vertical exits ------------------------------------
        gh = game.body(p, K_GOBLIN)[1]
        mon = EF_ACTIVE | EF_HOSTILE | 8              # facing left (toward the shaft from the right)
        p.boot(K_KNIGHT)
        p.isolate()
        to_b(kw)
        sg = game.SLOT_GOBLIN
        p.set_ent(sg, KIND=K_GOBLIN, HP=30, MAXHP=30)
        p.place(0, COL, y1)
        p.place(sg, COL + 4, stand_y(1, gh), room=ROOM_B, flags=mon)   # gap 1 on storey 1
        p.turn("J")
        settle_in(ROOM_C)
        g = p.ent(sg)
        check("F down: the goblin follows, PENDING in C", (g["ROOM"], bool(g["FLAGS"] & EF_PENDING)) == (ROOM_C, True),
              (g["ROOM"], g["FLAGS"]))
        took = [p.turn("J"), p.turn("J")]
        for _ in range(6):
            if not p.ent(sg)["FLAGS"] & EF_PENDING:
                break
            took.append(p.turn("H"))
        g = p.ent(sg)
        check("F down: every key a turn (no deadlock), the goblin materialises once the hero walks off",
              all(took) and not g["FLAGS"] & EF_PENDING and g["ROOM"] == ROOM_C, (took, g["FLAGS"], g["X"], g["Y"]))
        # up: C storey 0 -> B
        p.place(0, COL, y0)
        p.place(sg, COL + 4, stand_y(0, gh), room=ROOM_C, flags=mon)
        p.wb(S["P_ENTITIES"] + sg * S["P_ENT_STRIDE"] + S["E_HP"], 30)
        took = [p.turn("K"), p.turn("K")]
        settle_in(ROOM_B)
        g = p.ent(sg)
        check("F up: 2 turns, the goblin follows, PENDING in B",
              all(took) and (g["ROOM"], bool(g["FLAGS"] & EF_PENDING)) == (ROOM_B, True), (took, g["ROOM"], g["FLAGS"]))
        took = [p.turn("K")]
        for _ in range(6):
            if not p.ent(sg)["FLAGS"] & EF_PENDING:
                break
            took.append(p.turn("H"))
        g = p.ent(sg)
        check("F up: every key a turn, the goblin materialises once the hero walks off",
              all(took) and not g["FLAGS"] & EF_PENDING and g["ROOM"] == ROOM_B, (took, g["FLAGS"], g["X"], g["Y"]))

        # ---- C: cork_check bound ----------------------------------------------------------
        p.boot(K_KNIGHT)
        p.isolate()
        hb = S["P_ENTITIES"]

        def cork(y, aidir, ladder, blk, box):
            c, b, d, e = box
            p.wb(hb + S["E_X"], COL)
            p.wb(hb + S["E_Y"], y)
            p.wb(hb + S["E_AIDIR"], aidir & 255)
            p.wb("PL_LADDER", ladder)
            p.wb("CLIMB_BLK", blk)
            ok, ts, cf = run_code([0x01] + [c, b] + [0x11, e, d] + [0xCD] + w16(S["cork_check"]))
            yy = p.rb(hb + S["E_Y"])
            p.wb("PL_LADDER", 0)
            p.wb("CLIMB_BLK", 0)
            return ok, ts, cf, yy

        cases = [("up shaft y 1, box rows 6-7 (below the path, in his cols)", (1, -1, 1, 0, (COL + 1, 6, 3, 2)), False),
                 ("up shaft y 1, box on row 0", (1, -1, 1, 0, (COL - 2, 0, 3, 1)), True),
                 ("up shaft y 0 (arrival end, dir -1 after a no-step exit)", (0, -1, 1, 0, (COL, 8, 3, 1)), False),
                 ("blocked step to row 17 (CLIMB_BLK, dir +1), box on row 17", (y1, 1, 0, 1, (COL, 17, 3, 1)), True),
                 ("blocked step to row 17, box past row 17", (y1, 1, 0, 1, (COL, 18, 3, 4)), False),
                 ("B bottom end y 12 dir +1 (stale dir), box rows 0-1", (yb, 1, 1, 0, (COL, 0, 3, 2)), False)]
        for tag, args, want_cf in cases:
            ok, ts, cf, yy = cork(*args)
            check(f"C cork_check {tag}: CF {int(want_cf)}, <= 2k T, y restored",
                  ok and cf == want_cf and ts <= 2000 and yy == args[0], (ok, cf, ts, yy))

    print(f"[summary] h1climb: {len(fails)} failed" + (f" {fails}" if fails else ""), flush=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
