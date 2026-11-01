#!/usr/bin/env python3
"""3E-T17 exit gate: one seeded Warrior run end to end through every 3E system, then the
3E per-tick budget scenarios. Release build (DEBUG_KIT=0). game.md §8.11 "3E simplification
(2026-10-20)": blessed / cursed / identification are DROPPED, so there is no cursed-until-Enchant
step; gear stats are fixed and READ Enchant is a plain weapon +1.

PROTO room A, every monster parked, the hero on storey 1:
  P  pick up a floor Long Sword by walking onto it: bag record, "YOU PICK UP LONG SWORD", entry gone
  E  equip it through the bag page's verb path (page_post VB_EQUIP): worn row, the Short Sword swapped
     into the bag, the page's stat line (it_fmt) for the sword, hero_recalc moved kind_tab (ATK / DIE)
  F  eat: Pear at FOOD 45 -> hunger_add +20, "YOU EAT THE PEAR" + "YOU FEEL WELL FED" (HSTAGE FED);
     then the quick FOOD icon at FOOD 100 -> "NO NEED", no turn, nothing eaten
  D  drink a Heal potion (fx DRINK): +10 HP, both lines, consumed
  R  read Enchant (GEAR3: worn sword + armour are the candidates, RNG seeded so the first draw picks
     the sword): the sword m +1 (KT_BONUS +1), "ENCHANTED: LONG SWORD", consumed
  B  read a class book (fx_book -> abil_learn): "YOU LEARN POWER STRIKE!", ARANK slot 0 rank 1
  T  traps: a hidden DART under the next step fires (line, poison, known + drawn T_TRAP); a hidden
     one 6 cols off found by WAITs ("TRAP FOUND: DART")
  G  budget: tests/budget.py pmix (pickup + kill-drop), umix (eat / drink / read quick uses), tdart
     (trap fire), tsearch (trap find) run with the existing gates; worst work tick <= CAP and the
     real (ISR-adjusted) tick <= 2 frames. There is no equip scenario in budget.py: the equip is a
     page verb (the page is a full-screen state, not a play tick); its cost is reported by tests/page.py.
Run: ZRCP_PORT=<port> python3 tests/exit3e.py        (BUDGET_SKIP=1 skips part G)
"""
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, stand_y, attr_at, RUN_LIMIT  # noqa: E402
from proj3 import T, w16  # noqa: E402
from abil_melee import stream_text  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
EF_ACTIVE, EF_PLAYER = 1, 2
HX = 9
HY = stand_y(1, 6)
NOWHERE = 7
STUB = S["LOWRAM_END_3B"]
RES = STUB + 200
I = lambda n: S["IT_" + n]                     # noqa: E731,E741
STF, ST1 = S["ST_FLAGS"], S["ST_T1"]
FL, FLS = S["FLOOR_LIST"], S["FL_STRIDE"]
FLS1 = S["FL_S1"]
IROW = 9 + 7
TL = S["TRAP_LIST"]
KNOWN, SPENT, TS1 = S["TRF_KNOWN"], S["TRF_SPENT"], S["TRF_S1"]
DART = 0
T_TRAP = S["T_TRAP"]
FOOD_SLOT = {0: 6, 1: 6}


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:900]}", flush=True)

        if KIT:
            print("[skip] exit3e needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(h, p, check)
        failed_emu = bool(h.failures)
    if not KIT and not os.environ.get("BUDGET_SKIP"):
        budget(check_list := [], fails)
        for tag, ok, detail in check_list:
            print(f"[{'PASS' if ok else 'FAIL'}] {tag}" + ("" if ok else f" -- {detail}"), flush=True)
    print(f"exit3e: {len(fails)} failed" + (f": {fails[:12]}" if fails else ""), flush=True)
    return 1 if fails or failed_emu else 0


def run(h, p, check):
    lines = []
    LOGP = S["log_push"]
    WT = S["wait_tick"]
    KTAB = S["kind_tab"]
    z = p.z

    def run_to_probe():
        for _ in range(4000):
            z.cmd("run %d" % RUN_LIMIT)
            pc = p.pc()
            if pc == LOGP:
                regs = z.cmd("get-registers")
                hl = int(re.search(r"HL=([0-9a-fA-F]{4})", regs).group(1), 16)
                lines.append(stream_text(z.read_memory(hl, 48)).rstrip("."))
                z.cmd("cpu-step")
                continue
            if pc in p.probes:
                return
            raise RuntimeError(f"stopped at {pc:#06x}")

    def tick(n=1):
        for _ in range(n):
            z.cmd("cpu-step")
            run_to_probe()
    p.tick = tick

    def stub(body):
        assert p.pc() == WT, hex(p.pc())
        p.wmem(STUB, body + [0xC3] + w16(WT))
        z.cmd("set-register PC=%d" % STUB)
        run_to_probe()
        assert p.pc() == WT, "stub did not return"

    def farcall(far, label, a=0):
        stub([0x3E, a, 0x21] + w16(S[label]) + [0xCD] + w16(S[far]) + [0x7D, 0x32] + w16(RES))
        return p.rb(RES)

    def fx(op, arg):
        p.wb("FX_OP", op)
        p.wb("FX_ARG", arg)
        stub([0x21] + w16(S["fx_main"]) + [0xCD] + w16(S["far6"]))
        return p.rb("FX_OP")

    def bag():
        b = list(z.read_memory(S["BAG"], 60))
        return [(b[3 * i], b[3 * i + 1], b[3 * i + 2]) for i in range(20) if b[3 * i]]

    def setbag(items):
        flat = [x for n in items for x in (I(n), 1, 0)]
        p.wmem(S["BAG"], flat + [0] * (60 - len(flat)))
        stub([0x21] + w16(S["pot_sync"]) + [0xCD] + w16(S["far6"]))

    def worn():
        b = list(z.read_memory(S["WORN"], 12))
        return [b[3 * i] for i in range(4)]

    def kt(f):
        return p.rb(KTAB + S[f] + p.rb("HERO_KIND"))

    def stats():
        return dict(atk=kt("KT_ATK"), die=kt("KT_DIE"), bon=kt("KT_BONUS"), df=p.rb("HERO_DEF"))

    def fmt(slot):
        stub([0x3E, slot, 0x11] + w16(RES) + [0x21] + w16(S["it_fmt"]) + [0xCD] + w16(S["far6"])
             + [0xAF, 0x12])
        raw = bytes(z.read_memory(RES, 40))
        return raw[:raw.index(0)].decode()

    def act(*keys):
        lines.clear()
        t0 = p.rw("TURN_COUNTER")
        p.turn(*keys)
        return p.rw("TURN_COUNTER") - t0, list(lines)

    def heal():
        p.set_ent(0, HP=250, MAXHP=250)
        p.wmem(STF, [0] * 16)
        p.wmem(ST1, [0] * 16)
        p.wmem(S["ST_T2"], [0] * 16)

    def put_hero(x):
        p.set_ent(0, X=x, Y=HY, PX=x * 8, PY=HY * 8, MODE=0, REACT=0, FLT=0, FLAGS=EF_ACTIVE | EF_PLAYER)
        tick(2)

    # ---- scene ---------------------------------------------------------------------
    p.proto_start = 1
    p.boot(K_KNIGHT)
    room = p.rb("CUR_ROOM")
    for sl in range(1, 16):
        e = p.ent(sl)
        if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
            p.set_ent(sl, ROOM=NOWHERE)
    p.set_ent(0, HP=200, MAXHP=200)
    p.wmem(TL, [0] * 13)
    put_hero(HX)
    tick(2)
    z.cmd("set-breakpoint 5 PC=%d" % LOGP)
    lines.clear()
    setbag(["P_HEAL", "F_APPLE"])             # the start-kit bag; Short Sword + Leather worn
    check("S0 start kit: Short Sword + Leather worn, bag Heal / Apple",
          (worn()[:2], [b[0] for b in bag()]) == ([I("W_SHORT"), I("A_LEATHER")], [I("P_HEAL"), I("F_APPLE")]),
          (worn(), bag()))
    s_before = stats()

    # ---- P pickup --------------------------------------------------------------------
    free = [i for i in range(S["FLOOR_MAX"]) if p.rb(FL + i * FLS) == S["FL_EMPTY"]]
    col = HX + 3
    p.wmem(FL + free[0] * FLS, [room | FLS1, col, I("W_LONG"), 1])
    p.wmem(S["ROOM_MAP"] + (IROW - 1) * 32 + col, [S["T_ITEM0"] + 2] * 2)
    p.wmem(S["ROOM_MAP"] + IROW * 32 + col, [S["T_ITEM0"] + 3] * 2)
    d, ln = act("L")
    ent = list(z.read_memory(FL + free[0] * FLS, 4))
    check("P1 walk onto a Long Sword: 1 turn, 'YOU PICK UP LONG SWORD', bag slot 2, floor entry gone",
          (d, ln, bag()[2:], ent[0]) == (1, ["YOU PICK UP LONG SWORD"], [(I("W_LONG"), 1, 0)], S["FL_EMPTY"]),
          (d, ln, bag(), ent))

    # ---- E equip through the page verb -------------------------------------------------
    line_sw = fmt(2)
    m0 = bytes(z.read_memory(S["ROOM_MAP"], S["PLAY_CELLS"]))
    p.wmem(S["PAGE_MAP_SAVE"], list(m0))
    p.wmem(S["ROOM_MAP"], [0xEE] * S["PLAY_CELLS"])
    p.wb("PAGE_VERB", S["VB_EQUIP"])
    p.wb("PAGE_SLOT", 2)
    lines.clear()
    r = farcall("far1", "page_post")
    s_after = stats()
    check("E1 EQUIP Long Sword: L 1 (a turn), the line, worn[0] = Long Sword, Short Sword in the bag, map restored",
          (r, lines, worn()[0], bag()[2][0], bytes(z.read_memory(S["ROOM_MAP"], S["PLAY_CELLS"])) == m0)
          == (1, ["YOU EQUIP LONG SWORD"], I("W_LONG"), I("W_SHORT"), True), (r, lines, worn(), bag()))
    check("E2 hero_recalc moved the weapon stats (ATK / DIE of kind_tab) and the page stat line shows a dice term",
          (s_after != s_before and (s_after["atk"], s_after["die"]) != (s_before["atk"], s_before["die"])
           and line_sw.startswith(" 1D")), (s_before, s_after, line_sw))

    # ---- F eat -------------------------------------------------------------------------
    setbag(["F_PEAR", "P_HEAL", "S_ENCHANT", "BOOK"])
    p.wb("FOOD", 45)
    p.wb("HSTAGE", 1)
    p.wb("HP_RG", 7)
    lines.clear()
    r = fx(S["FX_EAT"], 0)
    e1 = (r, lines, p.rb("FOOD"), p.rb("HSTAGE"), p.rb("HP_RG"), [b[0] for b in bag()][:1])
    check("F1 EAT Pear at FOOD 45: hunger_add -> 65, FED, both lines, HP_RG 0, consumed, a turn",
          e1 == (1, ["YOU EAT THE PEAR", "YOU FEEL WELL FED"], 65, 0, 0, [I("P_HEAL")]), e1)
    setbag(["F_APPLE"])
    p.wb("FOOD", 100)
    k = p.rb("HERO_KIND")
    p.select_slot(FOOD_SLOT[k])
    lines.clear()
    nt = p.no_turn("FIRE")
    check("F2 quick FOOD at FOOD 100: NO NEED, no turn, the Apple kept",
          (nt, lines, p.rb("FOOD"), len(bag())) == (True, ["NO NEED"], 100, 1), (nt, lines, bag()))

    # ---- D drink -----------------------------------------------------------------------
    setbag(["P_HEAL", "S_ENCHANT", "BOOK"])
    p.set_ent(0, HP=10)
    lines.clear()
    r = fx(S["FX_DRINK"], 0)
    check("D1 DRINK Heal at HP 10: a turn, +10 HP, 'YOU DRINK THE HEAL POTION' + 'YOU FEEL HEALTHIER', consumed",
          (r, lines, p.ent(0)["HP"], [b[0] for b in bag()]) ==
          (1, ["YOU DRINK THE HEAL POTION", "YOU FEEL HEALTHIER"], 20, [I("S_ENCHANT"), I("BOOK")]),
          (r, lines, p.ent(0)["HP"], bag()))

    # ---- R read a scroll (Enchant on the equipped sword) -------------------------------
    b0 = stats()["bon"]
    p.wmem(S["RNG_STATE"], w16(0x1234))            # rng_next -> L $30: even, so k = 0 of n = 2 (the sword)
    lines.clear()
    r = fx(S["FX_READ"], 0)
    check("R1 READ Enchant: a turn, 'ENCHANTED: LONG SWORD', sword m +1 -> kind_tab bonus +1, scroll consumed",
          (r, lines[-1:], z.read_memory(S["WORN"] + 2, 1)[0], stats()["bon"] - b0, [b[0] for b in bag()])
          == (1, ["ENCHANTED: LONG SWORD"], 0x20, 1, [I("BOOK")]), (r, lines, stats(), bag()))

    # ---- B learn a spell from a book (abil_learn) --------------------------------------
    p.wmem(S["ARANK"], w16(0))
    lines.clear()
    r = fx(S["FX_READ"], 0)
    check("B1 READ the War Tome with nothing known: 'YOU LEARN POWER STRIKE!', ARANK slot 0 rank 1, book consumed",
          (r, lines, p.rw("ARANK") & 3, bag()) ==
          (1, ["YOU READ THE WAR TOME", "YOU LEARN POWER STRIKE!"], 1, []), (r, lines, p.rw("ARANK"), bag()))

    # UB2: every book read plays SFX_LEVELUP (learn, rank-up and tome); a scroll read does not.
    # sfx_req's entry is patched to log each id (tests/sfx5b.py install_log; own log area, the stubs use STUB..+120).
    LOGB = STUB + 120
    base = S["sfx_req"]
    p.wmem(STUB + 160, [0xE5, 0xF5, 0x2A] + w16(LOGB) + [0x77, 0x23, 0x22] + w16(LOGB) + [0xF1, 0xE1,
           0xF5, 0xC5, 0x47, 0xC3] + w16(base + 3))
    p.wmem(base, [0xC3] + w16(STUB + 160))

    def sfx_read(arank, item):
        setbag([item])
        p.wmem(S["ARANK"], w16(arank))
        p.wmem(LOGB, w16(LOGB + 2))
        fx(S["FX_READ"], 0)
        end = p.rb(LOGB) | p.rb(LOGB + 1) << 8
        n = end - LOGB - 2                    # (read_memory with a length of 0 reads a default span)
        return (list(z.read_memory(LOGB + 2, n)) if n else []), p.rw("ARANK") & 0x3FF

    LU = S["SFX_LEVELUP"]
    ids = [sfx_read(0, "BOOK"), sfx_read(1, "BOOK"), sfx_read(0x3FF, "BOOK"), sfx_read(0, "S_ENCHANT")]
    check("UB2 SFX_LEVELUP once per book read: learn, rank-up, tome (ARANK unchanged); none for a scroll",
          ids == [([LU], 1), ([LU], 2), ([LU], 0x3FF), ([], 0)], ids)

    # ---- T traps ------------------------------------------------------------------------
    def trap(c, typ=DART):
        p.wmem(TL, [room | TS1, c | (typ << 5)] + [0] * 10 + [1])

    def tent():
        return tuple(z.read_memory(TL, 2))
    heal()
    put_hero(12)
    trap(15)
    hp0 = p.ent(0)["HP"]
    d, ln = act("L")
    check("T1 step onto a hidden DART: 'A DART HITS YOU!' + 'YOU ARE POISONED!', HP lost, POISON set, known (not "
          "spent), T_TRAP in the map",
          (d, ln[:2], p.ent(0)["HP"] < hp0, bool(p.rb(STF) & S["STS_POISON"]), tent()[0] & (KNOWN | SPENT),
           p.rb(S["ROOM_MAP"] + (9 + 7) * 32 + 15)) ==
          (1, ["A DART HITS YOU!", "YOU ARE POISONED!"], True, True, KNOWN, T_TRAP), (d, ln, tent()))
    heal()
    put_hero(12)
    trap(12 + 8)
    found, ln = None, []
    for i in range(16):
        heal()
        _, ln = act("WAIT")
        if tent()[0] & KNOWN:
            found = i + 1
            break
    check("T2 WAIT searches: a hidden DART 6 cols off the body is found within 16 waits, 'TRAP FOUND: DART', drawn",
          (found is not None, ln[-1:], p.rb(S["ROOM_MAP"] + (9 + 7) * 32 + 20)) == (True, ["TRAP FOUND: DART"], T_TRAP),
          (found, ln))


def budget(out, fails):
    """tests/budget.py for the 3E scenarios; parse each scenario's worst ticks and gate them."""
    src = (HERE / "budget.py").read_text()
    cap = int(re.search(r"^CAP = (\d+)", src, re.M).group(1))
    bud = int(re.search(r"^BUDGET = 2 \* (\d+)", src, re.M).group(1)) * 2
    keys = "pmix,umix,tdart,tsearch"
    env = dict(os.environ, BUDGET_ONLY=keys)
    r = subprocess.run([sys.executable, str(HERE / "budget.py")], env=env, capture_output=True, text=True,
                       timeout=1500)
    txt = r.stdout + r.stderr
    names = {"pmix": "pickup + kill-drop", "umix": "eat / drink / read", "tdart": "trap fire",
             "tsearch": "trap find"}
    blocks = re.split(r"^== ", txt, flags=re.M)[1:]
    out.append(("G0 budget.py ran the four scenarios", len(blocks) == 4, f"rc {r.returncode}, {len(blocks)} blocks"))
    for key, blk in zip(keys.split(","), blocks):
        m = re.search(r"ordinary (\d+) / (\d+) / (\d+);", blk)
        mx = re.search(r"max tick\s+: (\d+) T", blk)
        if not m:
            out.append((f"G {key}", False, blk[:200]))
            continue
        total, work, real = int(m.group(1)), int(m.group(2)), int(m.group(3))
        print(f"[budget] {key} ({names[key]}): max tick {mx.group(1)} T, ordinary total/work/real "
              f"{total}/{work}/{real} (cap {cap}, 2 frames {bud})", flush=True)
        out.append((f"G {key} ({names[key]}): worst work tick {work} <= {cap}, real {real} <= {bud}",
                    work <= cap and real <= bud, (work, real)))
    out.append(("G budget.py gate line PASS", "[PASS] budget gate" in txt and r.returncode == 0,
                txt[-300:]))
    for tag, ok, _ in out:
        if not ok:
            fails.append(tag[:14])


if __name__ == "__main__":
    sys.exit(main())
