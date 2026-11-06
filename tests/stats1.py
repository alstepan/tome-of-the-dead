#!/usr/bin/env python3
"""STATS1 S1 (user 2026-11-01): end-of-game statistics. Release build (DEBUG_KIT=0), PROTO room A.

The hook is kill_note (bank 3, combat3.asm): deal_hit's monster-kill path, ATK_PTR == the hero.
ST1_KILLS (16-bit, no saturation: it wraps at 65,536), ST1_BXP / ST1_BL = the best kind (KXP >=: a
tie goes to the LATEST kill), TURN_COUNTER = the turns; ST1_KILLER (ENDCARD-G1) = the hero's killer.

U  unit (deal_hit called from a stub, attacker = slot A, target = slot T):
   U1 hero kills a Rat / Ogre / Goblin: kills 1 2 3, best = the Ogre (KXP 60), the lesser kill keeps it
   U2 a monster killing a monster: not counted
   U3 the Archmage killed by its OWN Mirror Helm return (attacker = target = the Archmage): not counted
   U4 the hero hit by a trap-like blow (target = the hero, not a kill): not counted
   U5 an EF_RESPAWN monster killed by the hero: counted
   U6 best kind ties: Giant Rat (KXP 3) then Slime (KXP 3): the latest (Slime) is the best; a Rat (KXP 2) after: stays
   U7 16-bit: 255 -> 256 carries into the high byte; 65535 -> 0 (wraps, documented)
   U8 the Archmage (KXP 0) as the only kill: counted, key stored (KXP 0 >= 0)
G  the real game (controls / turns), the counters read right after each:
   G1 Warrior bump kill, G2 Whirlwind kills 2 at once (+2), G3 dagger kill, G4 arrow kill,
   G5 Mage Spark kill, G6 new_game resets the counters (GS_DEAD -> menu -> start)
E  ENDCARD-G1 (user 2026-11-02, plan "ENDCARD-L1F-G1"): the full-screen end card, 3 cases x Warrior / Mage:
   killed by a monster (deal_hit stores ST1_KILLER = $80 | kind: title KILLED BY + the kind name, its
   portrait left), YOU DIED (the hero's own / a trap blow: ST1_KILLER 0, no portrait), YOU WIN! (+ the
   Tome line, the lectern left). Title in the menu font (menu_text_ok), the table CLASS / LEVEL /
   DEPTH / gap / KILLS / TURNS / BOOKS r/f / ITEMS (STATS2) / BEST KILL == text6 at the exact pixel x (no
   kills = no BEST row; rows below it blank down to the row above PRESS), PRESS on row EC_PRESS_ROW, then the whole frame against tests/golden/endcard_<case>_<hero>.hash (the portraits /
   attrs; --update-golden rewrites). PNGs to $STATS1_PNG when set
Run: ZRCP_PORT=<port> python3 tests/stats1.py [--update-golden]
"""
import hashlib
import os
import sys

UPDATE = "--update-golden" in sys.argv               # (before world.py, which resets sys.argv)
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import (Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, K_RAT, K_GOBLIN,  # noqa: E402
                      stand_y, frame_png)
from lp import T  # noqa: E402
from proj3 import w16  # noqa: E402
from world import log_row, text6, menu_text_ok, STRINGS  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT = 1, 2, 4, 8
EF_RESPAWN = S["EF_RESPAWN"]
GS_DEAD, GS_WIN = S["GS_DEAD"], S["GS_WIN"]
HY = stand_y(1, 6)
HX = 9
NOWHERE = 7
PNG = os.environ.get("STATS1_PNG")
GOLDEN_DIR = HERE / "golden"


def golden(name, fr):
    """ENDCARD-G1: the whole card (bitmap + attrs) hashed; --update-golden writes."""
    got = hashlib.sha256(bytes(fr[:6912])).hexdigest()
    path = GOLDEN_DIR / (name + ".hash")
    if UPDATE:
        path.write_text(f"frame {got}\n")
        print(f"[golden] wrote {path}", flush=True)
        return True
    try:
        ref = path.read_text().split()[1]
    except (FileNotFoundError, IndexError):
        print(f"[FAIL] golden missing: {path} (run --update-golden)", flush=True)
        return False
    return got == ref


def kname(kind):
    for n, t in STRINGS:
        if n.startswith("nm_") and S.get("TX_NM_" + n[3:].upper()) == S["TX_NM_KNIGHT"] + kind:
            return t
    raise KeyError(kind)


def orw(a, b):
    return [bytes(x | y for x, y in zip(r, s)) for r, s in zip(a, b)]


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
            print("[skip] stats1 needs a DEBUG_KIT=0 build", flush=True)
            return 0

        def st():
            return (p.rw("ST1_KILLS"), p.rb("ST1_BL") >> 3, p.rb("ST1_BXP"))

        def place(slot, x, y, flags, hp=None):
            kw = dict(X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=p.rb("CUR_ROOM"),
                      FLAGS=flags, REACT=0, FLT=0, HIT=0)
            if hp is not None:
                kw.update(HP=hp, MAXHP=hp)
            p.set_ent(slot, **kw)

        seed = [0x1357]

        def scene(cls=K_KNIGHT):
            p.boot(cls)
            seed[0] = (seed[0] * 75 + 74) % 65537 or 1   # each scene its own rolls (the snapshot's RNG is fixed)
            p.wmem(S["RNG_STATE"], w16(seed[0] & 0xFFFF or 1))
            room = p.rb("CUR_ROOM")
            for sl in range(1, 16):
                e = p.ent(sl)
                if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                    p.set_ent(sl, ROOM=NOWHERE)
            place(0, HX, HY, EF_ACTIVE | EF_PLAYER, 200)
            p.wb("MAXMP", 40)
            p.wb("MP", 40)
            p.wmem(S["ST_FLAGS"], [0] * 16)
            p.wmem(S["ST_T1"], [0] * 16)
            p.wb("FX_DROP", 0)
            p.tick(3)

        def mon(slot, kind, hp=5, extra=0, x=HX + 3, cls=K_KNIGHT, left=True):
            y = HY + p.kb(cls, "KT_BH") - p.kb(kind, "KT_BH")
            place(slot, x, y, EF_ACTIVE | EF_HOSTILE | (EF_LEFT if left else 0) | extra, hp)
            p.set_ent(slot, KIND=kind)

        def deal(att, tgt, dmg=99):
            pc0 = p.pc()
            ok, _ = p.code([0x3A] + w16(S["PORT_7FFD_SHADOW"]) + [0xF5, 0x3E, 3, 0xCD] + w16(S["page_bank"])
                           + [0xDD, 0x21] + w16(S["P_ENTITIES"] + att * STRIDE)
                           + [0x3E, tgt, 0x01, 0, dmg, 0x1E, 0, 0xCD] + w16(S["deal_hit"])
                           + [0xF1, 0xCD] + w16(S["restore_page"]), game=True)
            p.z.cmd("set-register PC=%d" % pc0)
            return ok

        KX = {k: S["K_" + k] for k in ("RAT", "OGRE", "GOBLIN", "ARCHMAGE", "GIANT_RAT", "SLIME")}

        # ------------------------------------------------------------------ unit
        scene()
        check("U0 the counters start at 0 / 0 / 0", st() == (0, 0, 0) and p.rb("ST1_BL") == 0, st())
        got = []
        for slot, k in ((1, "RAT"), (2, "OGRE"), (3, "GOBLIN")):
            mon(slot, KX[k])
            ok = deal(0, slot)
            got.append((ok,) + st())
        check("U1 hero kills Rat / Ogre / Goblin: kills 1 2 3; best = the Ogre (KXP 60), the Goblin keeps it",
              [g[1] for g in got] == [1, 2, 3] and [g[2] for g in got] == [KX["RAT"], KX["OGRE"], KX["OGRE"]]
              and got[2][3] == 60 and all(g[0] for g in got), got)
        s0 = st()
        mon(1, KX["RAT"])
        mon(2, KX["GOBLIN"])
        deal(2, 1)
        check("U2 a monster killing a monster: not counted", st() == s0 and p.ent(1)["FLAGS"] & S["EF_DYING"], st())
        mon(1, KX["ARCHMAGE"], hp=5)
        deal(1, 1)
        check("U3 the Archmage killed by its own Mirror Helm return (attacker = itself): not counted",
              st() == s0 and p.ent(1)["FLAGS"] & S["EF_DYING"], st())
        deal(0, 0, 1)
        check("U4 the hero hit by a trap-like blow (target = the hero): not counted", st() == s0, st())
        mon(1, KX["RAT"], extra=EF_RESPAWN)
        deal(0, 1)
        check("U5 an EF_RESPAWN monster killed by the hero is counted", st()[0] == s0[0] + 1, st())
        scene()
        for slot, k in ((1, "GIANT_RAT"), (2, "SLIME"), (3, "RAT")):
            mon(slot, KX[k])
            deal(0, slot)
        check("U6 tie: Giant Rat then Slime (KXP 3): the latest is the best; a Rat (KXP 2) after: stays",
              st() == (3, KX["SLIME"], 3), st())
        p.wmem(S["ST1_KILLS"], [255, 0])
        mon(1, KX["RAT"])
        deal(0, 1)
        a = p.rw("ST1_KILLS")
        p.wmem(S["ST1_KILLS"], [255, 255])
        mon(1, KX["RAT"])
        deal(0, 1)
        check("U7 16-bit: 255 -> 256 carries; 65535 -> 0 (wraps)", a == 256 and p.rw("ST1_KILLS") == 0,
              (a, p.rw("ST1_KILLS")))
        scene()
        mon(1, KX["ARCHMAGE"], hp=5)
        deal(0, 1)
        check("U8 the Archmage (KXP 0) as the only kill: counted, key stored", st() == (1, KX["ARCHMAGE"], 0), st())

        # ------------------------------------------------------------------ game
        def run_turn(act, ticks=200):
            t0 = p.rw("TURN_COUNTER")
            act()
            for _ in range(ticks):
                if p.rw("TURN_COUNTER") != t0 and p.idle() and p.rb("LOG_QN") == 0:
                    break
                p.tick()
            p.tick(3)

        def game_scene(cls, mons, learn=None, daggers=0, arrows=0, bow=0):
            scene(cls)
            for sl, k, x, left in mons:
                mon(sl, k, hp=1, x=x, cls=cls, left=left)
            av = 0
            for k, r in (learn or {}).items():
                av |= r << (2 * k)
            p.wmem(S["ARANK"], w16(av))
            p.wb("DAGGERS", daggers)
            p.wb("ARROWS", arrows)
            p.wb("HAS_BOW", bow)
            p.tick(2)

        def fire(slot):
            p.select_slot(slot)
            run_turn(lambda: p.tap("FIRE"))

        for rep in range(6):
            game_scene(K_KNIGHT, [(1, K_RAT, HX + 3, True)])
            fire(0)
            if st()[0]:
                break
        check("G1 Warrior bump kills a Rat: 1 kill, best Rat", st() == (1, K_RAT, 2), st())
        for rep in range(6):
            game_scene(K_KNIGHT, [(1, K_RAT, HX + 3, True), (3, K_GOBLIN, HX - 3, False)], learn={1: 1})
            fire(2)
            if st()[0] == 2:
                break
        check("G2 Whirlwind kills a Rat and a Goblin in one blow: +2, best Goblin",
              st()[0] == 2 and st()[1] == K_GOBLIN, st())
        for rep in range(8):
            game_scene(K_KNIGHT, [(1, K_RAT, HX + 6, True)], daggers=3)
            fire(3)
            if st()[0]:
                break
        check("G3 a thrown dagger kills a Rat: counted", st()[0] == 1 and p.rb("DAGGERS") == 2, (st(), p.rb("DAGGERS")))
        for rep in range(8):
            game_scene(K_KNIGHT, [(1, K_RAT, HX + 6, True)], arrows=5, bow=1)
            fire(4)
            if st()[0]:
                break
        check("G4 an arrow kills a Rat: counted", st()[0] == 1 and p.rb("ARROWS") == 4, (st(), p.rb("ARROWS")))
        for rep in range(4):
            game_scene(K_WIZARD, [(1, K_RAT, HX + 3, True)], learn={0: 1})
            fire(1)
            if st()[0]:
                break
        check("G5 a Spark kills a Rat (Mage): counted", st()[0] == 1 and p.rb("MP") < 40, (st(), p.rb("MP")))

        p.wmem(S["ST1_KILLS"], [9, 0])
        p.wmem(S["ST2_BKR"], [1, 2, 3])                   # STATS2: zeroed with them
        p.wb("GAME_STATE", GS_DEAD)
        p.tick(8)
        ok = p.end_to_menu()
        p.menu_start(K_KNIGHT)
        check("G6 new_game zeroes the counters (end card -> menu -> start)",
              ok and st() == (0, 0, 0) and p.rb("ST1_BL") == 0 and p.rw("TURN_COUNTER") < 20
              and list(p.z.read_memory(S["ST2_BKR"], 3)) == [0, 0, 0], (ok, st()))

        # ------------------------------------------------------------------ end card
        def card(cls, case, kills, turns, best, tag, books=(0, 0), items=0):
            """ENDCARD-G1: the full-screen card, pixel-exact text + the golden frame."""
            scene(cls)
            p.wmem(S["ST2_BKR"], [books[0], books[1], items])    # STATS2: read, found, items
            p.wmem(S["ST1_KILLS"], w16(kills))
            p.wb("ST1_BL", best * 8 + 4 if kills else 0)
            p.wb("ST1_BXP", 60 if kills else 0)
            p.wmem(S["TURN_COUNTER"], w16(turns))
            p.wb("LVL", 7)
            p.wb("LVL_DEPTH", 5)
            if case == "win":
                gs = GS_WIN
            else:
                gs = GS_DEAD
                p.wb("ST1_KILLER", 0)
                place(0, HX, HY, EF_ACTIVE | EF_PLAYER, 1)
                if case == "killer":
                    mon(1, KILLER, cls=cls)
                    deal(1, 0)
                else:
                    deal(0, 0)                       # the hero's own blow (a trap): no killer
                want = 0x80 | KILLER if case == "killer" else 0
                check(f"E {tag}: ST1_KILLER = {want:#x} after the fatal hit", p.rb("ST1_KILLER") == want,
                      p.rb("ST1_KILLER"))
            p.wb("GAME_STATE", gs)
            p.end_card(8)                            # END-WAIT: the card needs a key after the quiet (was tick(8))
            p.settle(4)
            fr = p.frame()
            if PNG:
                frame_png(fr, Path(PNG) / f"{tag}.png")
            if case == "killer":
                tc = (22 - len(kname(KILLER))) // 2      # the title is 10 + len cols, centred on col 16
                t_ok = (menu_text_ok(p, fr, TROW, tc, "KILLED BY")
                        and menu_text_ok(p, fr, TROW, tc + 10, kname(KILLER)))
            elif case == "died":
                t_ok = menu_text_ok(p, fr, TROW, 12, "YOU DIED")
            else:
                t_ok = (menu_text_ok(p, fr, TROW, 12, "YOU WIN!")
                        and log_row(fr, TROW + 2, 0, 32) == text6("THE TOME IS DESTROYED", 64, 32))
            PR = S["EC_PRESS_ROW"]
            r0, lx = S["EC_TAB_ROW"], S["EC_TAB_X"]    # one table position for all three cards
            check(f"E {tag}: title", t_ok)
            vx = lx + S["EC_VX"]
            rows = [("CLASS", "WARRIOR" if cls == K_KNIGHT else "MAGE"), ("LEVEL", "7"), ("DEPTH", "5"), None,
                    ("KILLS", str(kills)), ("TURNS", str(turns)),
                    ("BOOKS", f"{books[0]}/{books[1]}"), ("ITEMS", str(items))]   # STATS2 rows 17 / 18
            rows.append(("BEST KILL", kname(best)) if kills else None)
            rows += [None] * (PR - 1 - r0 - len(rows) + 1)   # nothing else down to the row above PRESS
            for i, rw in enumerate(rows):
                c0 = lx // 8                     # the table's columns (the portraits / lectern lie outside)
                want = orw(text6(rw[0], 0, 24 - c0), text6(rw[1], vx - lx, 24 - c0)) if rw else [bytes(24 - c0)] * 8
                check(f"E {tag}: row {r0 + i} = {rw}", log_row(fr, r0 + i, c0, 24 - c0) == want)
            check(f"E {tag}: row {PR} = PRESS 1-5 OR ENTER", log_row(fr, PR, 0, 32) == text6("PRESS 1-5 OR ENTER", 72, 32))
            check(f"E {tag}: state {gs} held", p.rb("GAME_STATE") == gs, p.rb("GAME_STATE"))
            check(f"E {tag}: golden", golden(tag, fr))

        KILLER = K_GOBLIN
        TROW = S["EC_TROW"]
        for cls, hn in ((K_KNIGHT, "warrior"), (K_WIZARD, "mage")):
            card(cls, "killer", 37, 4512, KX["OGRE"], f"endcard_killer_{hn}", (3, 5), 12)
            card(cls, "died", 0, 0, 0, f"endcard_died_{hn}")
            card(cls, "win", 1234, 65535, S["K_DKNIGHT"], f"endcard_win_{hn}", (255, 255), 255)
        print(f"stats1: {len(fails)} failed" + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
