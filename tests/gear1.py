#!/usr/bin/env python3
"""GEAR1: the class gear gate in ic_abil (src/intent7.asm; docs/design/gear_rules.md 1.2, vectors 6).
Played through the real controls (number key + FIRE) in PROTO room A, release build (DEBUG_KIT=0).
The worn type bytes (WORN + slot * IR_STRIDE) are poked; the gate reads them live, so poking the
type = equip / remove (the bag page only moves the byte).

  G1-1  Mage, Spark learned, MP 12, CHAIN / PLATE: GEAR line, MP 12, no turn, TURN_PEND 0
        (all 5 spells; the fizz is ic_no's: asserted by the code path, ic_refuse alone has none)
  G1-2  Mage, helmet HELM: as G1-1 (a bare helmet)
  G1-3  Mage, PLATE, Firebolt unlearned: NOT LEARNED (checked first)
  G1-4  Mage, CHAIN, MP 0: GEAR line, not NO MANA
  G1-5  Mage, uniques (MIRROR + GRAVE, SILK, KING), LEATHER, ROBE, HOOD: cast accepted (MP paid, 1 turn)
  G1-6  Mage, CHAIN: staff melee still works (the turn passes)
  G1-7  Warrior, ROBE; / HOOD: Power Strike and Whirlwind refused, GEAR line, MP kept, no turn
  G1-8  Warrior, ROBE, daggers, bow + arrows: dagger throw, bow shot and sword melee accepted
  G1-9  Warrior, KING HELM + LEATHER (and CHAIN, PLATE, HELM): Power Strike accepted
  G1-10 the gate follows equip / remove (type poked to the banned id then back to 0)
Run: ZRCP_PORT=<port> python3 tests/gear1.py
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD_DIR = os.environ.get("WZ_BUILD_DIR", str(HERE.parent / "build"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, K_GOBLIN, K_RAT, stand_y  # noqa: E402
from proj3 import T, w16  # noqa: E402
import textpack  # noqa: E402
import world  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT = 1, 2, 4, 8
HY = stand_y(1, 6)
HX = 12
NOWHERE = 7
WORN, STR = S["WORN"], S["IR_STRIDE"]
ARM, HELM = WORN + S["WS_ARMOUR"] * STR, WORN + S["WS_HELM"] * STR
ROBE, LEATHER, CHAIN, PLATE, SILK, GRAVEC = (S[k] for k in (
    "IT_A_ROBE", "IT_A_LEATHER", "IT_A_CHAIN", "IT_A_PLATE", "IT_A_SILK", "IT_A_GRAVE"))
HOOD, HELMT, KING, MIRROR = (S[k] for k in ("IT_H_HOOD", "IT_H_HELM", "IT_H_KING", "IT_H_MIRROR"))
GEAR_TXT = dict(textpack.read_strings())["gear_ban"]
assert GEAR_TXT == "YOUR GEAR FORBIDS IT" and len(GEAR_TXT) <= 21
SPARK, FROST = S["ABL_SPARK"], S["ABL_FROST"]
POWER, WHIRL = S["ABL_POWER"], S["ABL_WHIRL"]


def main():
    fails = []
    if KIT:
        print("[skip] gear1 needs a DEBUG_KIT=0 build")
        return 0
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)
        kt = {}

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:600]}", flush=True)

        def place(slot, x, y, flags, hp):
            p.set_ent(slot, X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=p.rb("CUR_ROOM"), FLAGS=flags,
                      REACT=0, FLT=0, HIT=0, HP=hp, MAXHP=hp)

        def scene(kind, arm, helm, learn, mp, mon_dx=3):
            """Fresh game of `kind`, worn armour / helmet types poked, `learn` = {slot-index k: rank},
            a Goblin mon_dx cols in front (left-facing), the hero at HX facing right, HP 200."""
            p.boot(kind)
            if not kt:
                kt.update(p.kinds())
            room = p.rb("CUR_ROOM")
            for sl in range(1, 16):
                e = p.ent(sl)
                if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                    p.set_ent(sl, ROOM=NOWHERE)
            place(0, HX, HY, EF_ACTIVE | EF_PLAYER, 200)
            gob = next(sl for sl in range(1, 16) if p.ent(sl)["KIND"] == K_GOBLIN)
            place(gob, HX + mon_dx, HY + 6 - kt[K_GOBLIN]["bh"], EF_ACTIVE | EF_HOSTILE | EF_LEFT, 200)
            p.wb(ARM, arm)
            p.wb(HELM, helm)
            p.wb("MP", mp)
            p.wb("MAXMP", max(mp, 1))
            av = 0
            for k, r in learn.items():
                av |= r << (2 * k)
            p.wmem(S["ARANK"], w16(av))
            p.wb("FX_DROP", 0)
            p.tick(3)

        def last_line():
            p.until(lambda: p.rb("LOG_QN") == 0, 30)
            p.tick(2)
            return world.log_row(p.composed_frame(), 23)

        def fire(slot, hold_ticks=None):
            """Select + FIRE; returns (turn passed, MP delta, the row-23 line)."""
            p.select_slot(slot)
            mp0, t0 = p.rb("MP"), p.rw("TURN_COUNTER")
            nt = p.no_turn("FIRE")
            line = last_line()
            return (not nt) or p.rw("TURN_COUNTER") != t0, p.rb("MP") - mp0, line

        def gear_refused(tag, slot):
            mp0 = p.rb("MP")
            turn, dmp, line = fire(slot)
            check(f"{tag}: GEAR FORBIDS IT, MP kept, no turn, TURN_PEND 0",
                  not turn and dmp == 0 and line == world.text6(GEAR_TXT) and p.rb("TURN_PEND") == 0,
                  (turn, dmp, line, mp0))

        def accepted(tag, slot, pays=True):
            turn, dmp, line = fire(slot)
            check(f"{tag}: accepted (turn passed, MP {'paid' if pays else 'n/a'}, no GEAR line)",
                  turn and line != world.text6(GEAR_TXT) and (dmp < 0 or not pays), (turn, dmp, line))

        # ---- G1-1 / G1-2: the Mage -------------------------------------------------
        for name, arm, helm in (("CHAIN", CHAIN, 0), ("PLATE", PLATE, 0), ("HELM", 0, HELMT),
                                ("CHAIN+HOOD", CHAIN, HOOD)):
            for k in range(5):
                scene(K_WIZARD, arm, helm, {k: 1}, 12)
                gear_refused(f"G1-1 Mage {name} spell {k}", k + 1)
        # ---- G1-3 / G1-4 -----------------------------------------------------------
        scene(K_WIZARD, PLATE, 0, {SPARK: 1}, 12)
        p.wb("SEL_SLOT", S["ABL_FIREBOLT"] + 1)     # the cursor refuses an unlearned slot: forced
        p.tick()
        nt = p.no_turn("FIRE")
        check("G1-3 Mage PLATE, Firebolt unlearned: NOT LEARNED first, no turn",
              nt and last_line() == world.text6(dict(textpack.read_strings())["not_learned"]))
        scene(K_WIZARD, CHAIN, 0, {SPARK: 1}, 0)
        mp0 = p.rb("MP")
        gear_refused("G1-4 Mage CHAIN, MP 0 (GEAR, not NO MANA)", 1)
        # ---- G1-5: exempt / neutral ------------------------------------------------
        for name, arm, helm in (("MIRROR+GRAVECLOAK", GRAVEC, MIRROR), ("SILK", SILK, 0), ("KING", 0, KING),
                                ("LEATHER", LEATHER, 0), ("ROBE+HOOD", ROBE, HOOD), ("none", 0, 0)):
            scene(K_WIZARD, arm, helm, {SPARK: 1}, 12)
            accepted(f"G1-5 Mage {name} Spark", 1)
        # ---- G1-6: staff melee with CHAIN -------------------------------------------
        scene(K_WIZARD, CHAIN, 0, {SPARK: 1}, 12, mon_dx=3)
        accepted("G1-6 Mage CHAIN staff swing", 0, pays=False)
        # ---- G1-7: the Warrior ------------------------------------------------------
        for name, arm, helm in (("ROBE", ROBE, 0), ("HOOD", 0, HOOD), ("ROBE+HOOD", ROBE, HOOD)):
            for abl, slot in ((POWER, 1), (WHIRL, 2)):
                scene(K_KNIGHT, arm, helm, {0: 1, 1: 1}, 20)
                gear_refused(f"G1-7 Warrior {name} {'Power' if abl == POWER else 'Whirl'}", slot)
        # ---- G1-8: daggers / bow / sword with ROBE ----------------------------------
        scene(K_KNIGHT, ROBE, HOOD, {0: 1, 1: 1}, 20)
        p.wb("DAGGERS", 3)
        accepted("G1-8 Warrior ROBE+HOOD dagger throw", 3, pays=False)
        scene(K_KNIGHT, ROBE, HOOD, {0: 1, 1: 1}, 20)
        p.wb("HAS_BOW", 1)
        p.wb("ARROWS", 5)
        accepted("G1-8 Warrior ROBE+HOOD bow shot", 4, pays=False)
        scene(K_KNIGHT, ROBE, HOOD, {0: 1, 1: 1}, 20, mon_dx=3)
        accepted("G1-8 Warrior ROBE+HOOD sword melee", 0, pays=False)
        # ---- G1-9: neutral / exempt, Warrior ----------------------------------------
        for name, arm, helm in (("KING+LEATHER", LEATHER, KING), ("CHAIN", CHAIN, 0), ("PLATE+HELM", PLATE, HELMT),
                                ("SILK+MIRROR", SILK, MIRROR), ("GRAVECLOAK", GRAVEC, 0)):
            scene(K_KNIGHT, arm, helm, {0: 1, 1: 1}, 20)
            accepted(f"G1-9 Warrior {name} Power Strike", 1)
        scene(K_KNIGHT, LEATHER, KING, {0: 1, 1: 1}, 20)
        accepted("G1-9 Warrior KING+LEATHER Whirlwind", 2)
        # ---- G1-10: the gate follows equip / remove ---------------------------------
        scene(K_KNIGHT, 0, 0, {0: 1, 1: 1}, 20)
        p.wb(ARM, ROBE)
        gear_refused("G1-10 Warrior ROBE put on", 1)
        p.wb(ARM, 0)
        accepted("G1-10 Warrior ROBE taken off", 1)
        print(f"gear1: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
