#!/usr/bin/env python3
"""STATS2 (user 2026-11-05, docs/design/stats2.md): the end card's BOOKS r/f and ITEMS counters.
Release build (DEBUG_KIT=0), PROTO room A. Counters (item_defs.asm, ITEM_RAM, zeroed by new_game):
ST2_BKR books read (R6 fx_book), ST2_BKF books found (R6 pu_add, IT_BOOK), ST2_ITM items found
(R6 pu_add any other type + bank-7 ap_take when n > 0); all saturate at 255. The card rows are
checked pixel-exact by tests/stats1.py E (table rows EC_TAB_ROW.., PRESS EC_PRESS_ROW).

  S0  a fresh game: 0 / 0 / 0
  S1  the class book picked up: found 1, read 0, items 0; READ it (fx_main FX_READ): 1/1, items 0
  S2  a potion, a food and an arrow stack (Warrior) picked up: items 3, books unchanged;
      DISCARD the potion (bag_discard): items stay 3
  S3  3 books picked up, 2 read (a rank-up: ARANK 1 = Power Strike I; the tome: ARANK $F, both
      Warrior abilities at rank 3): 2/3
  S4  saturation: 254 -> 255 -> 255 for read (READ), found (a book), items (a potion and an
      arrow stack: R6 st2_inc and the bank-7 inline increment)
  S5  refused pickups count nothing: a full bag (a book, a potion), a full quiver (n = 0),
      the Mage on an arrow stack
  S6  new_game zeroes the counters (end card -> menu -> start)
Run: ZRCP_PORT=<port> python3 tests/stats2.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, stand_y  # noqa: E402
from lp import T  # noqa: E402
from proj3 import w16  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
EF_ACTIVE, EF_PLAYER = 1, 2
HY = stand_y(1, 6)
HX = 9
NOWHERE = 7
FL, FLS = S["FLOOR_LIST"], S["FL_STRIDE"]
IROW = 9 + 7
BAG = S["BAG"]
IT = {k[3:]: v for k, v in S.items() if k.startswith("IT_") and isinstance(v, int)}


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:600]}", flush=True)

        if KIT:
            print("[skip] stats2 needs a DEBUG_KIT=0 build", flush=True)
            return 0

        def st():
            return (p.rb("ST2_BKR"), p.rb("ST2_BKF"), p.rb("ST2_ITM"))

        def scene(cls=K_KNIGHT, bagrecs=()):
            p.boot(cls)
            room = p.rb("CUR_ROOM")
            for sl in range(1, 16):
                e = p.ent(sl)
                if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                    p.set_ent(sl, ROOM=NOWHERE)
            p.set_ent(0, X=HX, Y=HY, PX=HX * 8, PY=HY * 8, MODE=0, ROOM=room, FLAGS=EF_ACTIVE | EF_PLAYER,
                      REACT=0, FLT=0, HIT=0, HP=200, MAXHP=200)
            for a in ("ST_FLAGS", "ST_T1", "ST_T2", "ST_X"):
                p.wmem(S[a], [0] * 16)
            flat = [v for r in bagrecs for v in r]
            p.wmem(BAG, flat + [0] * (60 - len(flat)))
            p.set_ent(0, POT=0)
            p.tick(3)

        def put(col, item, qty=1):
            """A FLOOR_LIST entry + its marker cells (as pickup3e.put): under the hero's body."""
            i = next(i for i in range(S["FLOOR_MAX"]) if p.rb(FL + i * FLS) == S["FL_EMPTY"])
            p.wmem(FL + i * FLS, [p.rb("CUR_ROOM") | S["FL_S1"], col, item, qty])
            p.wmem(S["ROOM_MAP"] + (IROW - 1) * 32 + col, [S["T_ITEM0"] + 2] * 2)
            p.wmem(S["ROOM_MAP"] + IROW * 32 + col, [S["T_ITEM0"] + 3] * 2)
            pg = S["FI_CELL"] + 256
            p.wmem(pg + ((((IROW - 1) & 7) << 5) | col), [0, 8])
            p.wmem(pg + (((IROW & 7) << 5) | col), [16, 24])
            return i

        def pick(item, qty=1):
            """One item under the standing hero, one WAIT turn (end_turn's floor_pickup)."""
            i = put(HX, item, qty)
            ok = p.turn("WAIT")
            return ok, p.rb(FL + i * FLS) == S["FL_EMPTY"]

        def call6(label, a=0):
            pc0 = p.pc()
            ok, _ = p.code([0x3E, a, 0x21] + w16(S[label]) + [0xCD] + w16(S["far6"]), game=True)
            p.z.cmd("set-register PC=%d" % pc0)
            return ok

        def bag_slot(t):
            b = p.z.read_memory(BAG, 60)
            return next(k for k in range(20) if b[3 * k] == t)

        def read(arank=None):
            if arank is not None:
                p.wmem(S["ARANK"], w16(arank))
            p.wb("FX_OP", S["FX_READ"])
            p.wb("FX_ARG", bag_slot(IT["BOOK"]))
            ok = call6("fx_main")
            return ok and p.rb("FX_OP") & 1

        # S0
        scene()
        check("S0 a fresh game: books 0/0, items 0", st() == (0, 0, 0), st())

        # S1
        r1 = pick(IT["BOOK"])
        s1 = st()
        r2 = read(0)
        check("S1 book picked up: 0/1 items 0; READ (starter): 1/1 items 0",
              r1 == (True, True) and s1 == (0, 1, 0) and r2 and st() == (1, 1, 0), (r1, s1, r2, st()))

        # S2
        scene()
        got = [pick(IT["P_HEAL"]), pick(IT["F_PEAR"]), pick(IT["ARROW"], 5)]
        s2 = st()
        call6("bag_discard", bag_slot(IT["P_HEAL"]))
        b = p.z.read_memory(BAG, 60)
        check("S2 potion + food + arrow stack: items 3, books 0/0; DISCARD the potion: items stay 3",
              all(g == (True, True) for g in got) and s2 == (0, 0, 3) and st() == (0, 0, 3)
              and IT["P_HEAL"] not in b[0::3] and p.rb("ARROWS") == 5, (got, s2, st(), p.rb("ARROWS")))

        # S3
        scene()
        for _ in range(3):
            pick(IT["BOOK"])
        a = read(1)                                  # Power Strike I -> II (a rank-up)
        ar = p.rw("ARANK") & 0x3FF
        b_ = read(0xF)                               # both at rank 3 (Warrior D1): the Vigor tome
        check("S3 3 books found, 2 read (a rank-up, the tome): 2/3",
              a and b_ and ar == 2 and st() == (2, 3, 0), (a, b_, ar, st()))

        # S4
        scene()
        p.wmem(S["ST2_BKR"], [254, 254, 254])
        seq = []
        for _ in range(2):
            pick(IT["BOOK"])
            read(0)
            pick(IT["P_HEAL"])
            seq.append(st())
        p.wb("ST2_ITM", 254)
        pick(IT["ARROW"], 2)
        am = p.rb("ST2_ITM")
        pick(IT["ARROW"], 2)
        check("S4 saturation: read / found / items 254 -> 255 -> 255 (R6 st2_inc; the ammo's inline inc)",
              seq == [(255, 255, 255)] * 2 and am == 255 and p.rb("ST2_ITM") == 255 and p.rb("ARROWS") == 4,
              (seq, am, st(), p.rb("ARROWS")))

        # S5
        full = [(IT["W_LONG"], 1, 0)] * 20
        scene(bagrecs=full)
        r = [pick(IT["BOOK"]), pick(IT["P_HEAL"])]
        sb = st()
        scene()
        p.wb("ARROWS", S["ARROWS_MAX"])
        r.append(pick(IT["ARROW"], 3))
        sq = st()
        scene(K_WIZARD)
        r.append(pick(IT["ARROW"], 3))
        check("S5 refused pickups count nothing: full bag (book, potion), full quiver, the Mage on arrows",
              [x[1] for x in r] == [False] * 4 and sb == sq == st() == (0, 0, 0), (r, sb, sq, st()))

        # S6
        scene()
        p.wmem(S["ST2_BKR"], [3, 5, 9])
        p.wb("GAME_STATE", S["GS_DEAD"])
        p.tick(8)
        ok = p.end_to_menu()
        p.menu_start(K_KNIGHT)
        check("S6 new_game zeroes the counters (end card -> menu -> start)", ok and st() == (0, 0, 0), (ok, st()))
        print(f"stats2: {len(fails)} failed" + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
