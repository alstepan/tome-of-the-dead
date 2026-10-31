#!/usr/bin/env python3
"""STATUS1 on a release build (DEBUG_KIT=0), PROTO room A, every monster parked.
FAINT1 (game.md §7.1), POIS1 (§6.4.3 + §7.2). STUN1 lives in tests/t16.py (S section).
Code: R6 hunger6.asm hg_faint + trap6.asm hero_hold, status7.asm st_step (POISON in ST_X),
combat3.asm deal_hit (.ps: halved param, add, PSN_CAP), fx6.asm fx_eat / pot_eff.

  F   hunger faint: the exact effect (ASLEEP 5, the GAS flash $44, 'YOU FAINT FROM HUNGER',
      HW_TMR 20); the timing over real turns (50 WEAK turns after the entry, then every 30);
      deferred (HW_TMR held at 49, no line) while mid-ladder / held / HOLD_GUARD /
      EXIT_KIND and then faints once clear; any HP loss wakes him; the Mummy WEAK status never
      faints; eating out of WEAK and back restarts the grace; costs
  P   poison: amounts 12 / 18 / 24 (kind-table param = half), DART 12, add per hit, cap 30 in
      ST_X; fresh 12 -> exactly 3 HP over 12 turns, then THE POISON WEARS OFF; HP 1 never
      drops; a poison tick wakes a sleeper; Cure zeroes ST_X; a level change keeps it
  E   poisoned hero cannot eat: TOO SICK TO EAT (before NO NEED), 0 turns, nothing consumed,
      the page verb (fx_main FX_EAT) and the quick FOOD slot; potions / scrolls unaffected;
      eats again after a Cure / when the timer runs out
Run: ZRCP_PORT=<port> python3 tests/status1.py
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, K_GOBLIN, stand_y, RUN_LIMIT  # noqa: E402
B7_LABELS = {"hunger_turn", "hunger_add", "trap_step", "trap_turn"}   # MEM-RECLAIM w2b: bank-7 cold code (far7), not R6
from proj3 import T, w16  # noqa: E402
from abil_melee import stream_text  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT = 1, 2, 4, 8
HY = stand_y(1, 6)
HX = 12
NOWHERE = 7
STUB = S["LOWRAM_END_3B"]
RES = STUB + 200
STF, ST1, STX = S["ST_FLAGS"], S["ST_T1"], S["ST_X"]
POIS, HWEAK, WEAK, GUARD = S["STS_POISON"], S["STS_HWEAK"], 1 << S["STS_WEAK_BIT"], 1 << S["STS_GUARD_BIT"]
ASLEEP, FROZEN, HOLD = S["HOLD_ASLEEP"], S["HOLD_FROZEN"], S["STS_HOLD"]
FOOD, TMR, HST, HW = S["FOOD"], S["FOOD_TMR"], S["HSTAGE"], S["HW_TMR"]
L_FAINT, L_WEAK, L_WAKE = "YOU FAINT FROM HUNGER", "YOU ARE WEAK WITH HUNGER", "YOU WAKE UP"
L_SICK, L_NEED, L_OFF, L_PSN = "TOO SICK TO EAT", "NO NEED", "THE POISON WEARS OFF", "YOU ARE POISONED!"
I = lambda n: S["IT_" + n]                     # noqa: E731,E741
FOOD_SLOT = {0: 6, 1: 6}
POT_SLOT = {0: 7, 1: 7}
SCR_SLOT = {0: 8, 1: 8}
EFX_POISON_C = S["DTY_PHYS"] | (S["EFX_POISON"] << S["DH_EFX_SHIFT"])


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
            print("[skip] status1 needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(h, p, check)
        print(f"status1: {len(fails)} failed" + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def run(h, p, check):
    lines = []
    LOGP = S["log_push"]
    WT = S["wait_tick"]
    z = p.z
    slots = {}

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

    def far6(label, a=0):                      # MEM-RECLAIM w2b: the hunger logic is bank 7 (far7)
        stub([0x3E, a, 0x21] + w16(S[label]) + [0xCD] + w16(S["far7" if label in B7_LABELS else "far6"]))

    def far7(label):
        stub([0x21] + w16(S[label]) + [0xCD] + w16(S["far7"]))

    def far3(label):
        stub([0x21] + w16(S[label]) + [0xCD] + w16(S["far3"]))

    def deal_psn(half, att=None, dmg=1):
        """deal_hit(IX = att, hero) with POISON, the param nibble = half the turns."""
        att = att or slots[K_GOBLIN]
        inner = ([0xDD, 0x21] + w16(S["P_ENTITIES"] + att * STRIDE) + [0x3E, 0, 0x06, dmg, 0x0E, EFX_POISON_C,
                 0x1E, half, 0xCD] + w16(S["deal_hit"]) + [0x7D, 0x32] + w16(RES))
        stub(p.bank3(inner))

    def place(slot, x, y, flags, hp):
        p.set_ent(slot, X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=p.rb("CUR_ROOM"), FLAGS=flags, REACT=0,
                  FLT=0, HIT=0, HP=hp, MAXHP=hp)

    def scene(hero=K_KNIGHT, hp=40, food=40):
        p.boot(hero)
        if not slots:
            for sl in range(1, 16):
                slots.setdefault(p.ent(sl)["KIND"], sl)
        room = p.rb("CUR_ROOM")
        for sl in range(1, 16):
            e = p.ent(sl)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                p.set_ent(sl, ROOM=NOWHERE)
        place(0, HX, HY, EF_ACTIVE | EF_PLAYER, hp)
        place(slots[K_GOBLIN], HX + 14, HY + 2, EF_ACTIVE | EF_HOSTILE | EF_LEFT, 60)
        p.set_ent(slots[K_GOBLIN], ROOM=NOWHERE)          # only the attacker of deal_hit: parked
        p.wb("HERO_DEF", 0)
        clear()
        setfood(food)
        p.wb("JUMP_TURN", 0xFF)
        p.wb(S["JUMP_TURN"] + 1, 0xFF)
        p.tick(3)
        z.cmd("set-breakpoint 5 PC=%d" % LOGP)
        lines.clear()

    def clear():
        p.wmem(STF, [0] * 16)
        p.wmem(ST1, [0] * 16)
        p.wmem(S["ST_T2"], [0] * 16)
        p.wmem(STX, [0] * 16)

    def setfood(food, tmr=0, stage=None):
        p.wb(FOOD, food)
        p.wb(TMR, tmr)
        p.wb(HST, stage if stage is not None else (0 if food >= 50 else 1 if food >= 25 else 2 if food >= 10 else 3))

    def weak(hw=49, food=5):
        clear()
        p.wb(S["EXIT_KIND"], 0)
        p.set_ent(0, X=HX, Y=HY, FLT=0, FLA=0)
        reactat(0)
        setfood(food, 0, 3)
        p.wb(STF, HWEAK)
        p.wb(HW, hw)
        lines.clear()

    def reactat(v):
        p.wb(S["P_ENTITIES"] + S["E_REACT"], v)           # a pending reaction (RC_HURT = 1)

    def state():
        e = p.ent(0)
        return dict(hold=p.rb(STF) & HOLD, t=p.rb(ST1) >> 4, hw=p.rb(HW), flt=e["FLT"], fla=e["FLA"],
                    lines=list(lines))

    # ======================= F: hunger faint ======================================
    scene()
    weak()
    far6("hunger_turn")
    s = state()
    check("F1 WEAK, HW_TMR 49 -> the 50th: ASLEEP 5, 'YOU FAINT FROM HUNGER', HW_TMR 20, the GAS flash $44, "
          "STS_HWEAK kept",
          (s["hold"], s["t"], s["hw"], s["lines"], s["flt"] > 0, s["fla"], p.rb(STF) & HWEAK) ==
          (ASLEEP, 5, 20, [L_FAINT], True, 0x44, HWEAK), s)
    # F4 wake on any HP loss
    lines.clear()
    far3("trap_hit")
    check("F4 asleep from a faint: any HP loss wakes him ('YOU WAKE UP')",
          (p.rb(STF) & HOLD, L_WAKE in lines) == (0, True), (hex(p.rb(STF)), lines))
    # F3 deferrals: HW_TMR held at 49, no sleep, no line; then (cleared) the faint comes
    res = {}

    def defer(tag, setter, clearer):
        weak()
        setter()
        far6("hunger_turn")
        a = (p.rb(STF) & HOLD == ASLEEP, p.rb(HW), list(lines))
        clearer()
        lines.clear()
        far6("hunger_turn")
        b = (p.rb(STF) & HOLD, p.rb(HW), list(lines))
        res[tag] = (a, b)
    defer("ladder", lambda: p.set_ent(0, Y=HY - 1), lambda: p.set_ent(0, Y=HY))
    defer("frozen", lambda: (p.wb(STF, HWEAK | FROZEN), p.wb(ST1, 0x30)), lambda: p.wmem(STF, [HWEAK]))
    defer("stunned", lambda: (p.wb(STF, HWEAK | HOLD), p.wb(ST1, 0x30)), lambda: p.wmem(STF, [HWEAK]))
    defer("guard", lambda: p.wb(STF, HWEAK | GUARD), lambda: p.wmem(STF, [HWEAK]))
    want_a, want_b = (False, 49, []), (ASLEEP, 20, [L_FAINT])
    bad = {k: v for k, v in res.items() if v[0] != want_a or v[1] != want_b}
    check("F3 deferred, not skipped: mid-ladder / frozen / stunned / HOLD_GUARD -> no faint, "
          "HW_TMR 49, no line; once clear the next turn faints", not bad, bad)
    # F3c the REAL exit path: end_turn runs do_exit (clears EXIT_KIND) BEFORE hunger_turn, so the
    # arrival turn must not faint (.ex stands the clock still); the next turn faints
    weak()
    p.wb(S["EXIT_KIND"], S["EX_TELE"])
    far7("end_turn")
    a = (p.rb(STF) & HOLD == ASLEEP, p.rb(HW), L_FAINT in lines, p.rb(S["EXIT_KIND"]))
    lines.clear()
    far6("hunger_turn")
    b = (p.rb(STF) & HOLD, p.rb(HW), list(lines))
    check("F3c exit turn through end_turn (teleport): no faint, HW_TMR 49; the next turn faints",
          (a, b) == ((False, 49, False, 0), (ASLEEP, 20, [L_FAINT])), (a, b))
    scene()
    # a stale E_REACTAT (the last reaction's tick, never cleared) with no pending E_REACT must not defer
    weak()
    p.wb(S["P_ENTITIES"] + S["E_REACTAT"], 5)
    far6("hunger_turn")
    check("F3b a stale E_REACTAT does not defer the faint (budget tfaint found it)",
          (p.rb(STF) & HOLD, p.rb(HW)) == (ASLEEP, 20), (hex(p.rb(STF)), p.rb(HW)))
    # the Mummy WEAK status never faints (the hunger stage is not WEAK)
    clear()
    setfood(80)
    p.wb(STF, WEAK)
    p.wb(S["ST_T2"], 5)
    p.wb(HW, 49)
    lines.clear()
    far6("hunger_turn")
    check("F5 the Mummy WEAK status (hunger FED) never faints: HW_TMR untouched, awake",
          (p.rb(STF) & HOLD, p.rb(HW), lines) == (0, 49, []), (hex(p.rb(STF)), p.rb(HW), lines))
    # eating out of WEAK and back restarts the grace (the entry sets HW_TMR to -1)
    weak(hw=40)
    far6("hunger_add", 6)
    a = (p.rb(HST), p.rb(HW))
    setfood(10, 5, 2)
    p.wb(STF, 0)
    lines.clear()
    far6("hunger_turn")
    check("F6 eat to FOOD >= 10 (HUNGRY), fall back to 9: the WEAK entry restarts HW_TMR at 0",
          (a[0], p.rb(HST), p.rb(HW), lines) == (2, 3, 0, [L_WEAK]), (a, p.rb(HST), p.rb(HW), lines))

    # F2 the timing over real turns: 50 WEAK turns after the entry, then every 30
    scene(K_WIZARD, hp=60, food=10)
    setfood(10, 5, 2)
    ent_turn = None
    faints, wakes, asleep_run = [], [], 0
    longest = 0
    for _ in range(125):
        lines.clear()
        p.turn("WAIT")
        c = p.rw("TURN_COUNTER")
        if L_WEAK in lines and ent_turn is None:
            ent_turn = c
        if L_FAINT in lines:
            faints.append(c)
        if L_WAKE in lines:
            wakes.append(c)
        asleep_run = asleep_run + 1 if p.rb(STF) & HOLD == ASLEEP else 0
        longest = max(longest, asleep_run)
    rel = [f - ent_turn for f in faints]
    check("F2 faints 50 WEAK turns after the entry, then every 30 turns (5 asleep turns each, then 'YOU WAKE UP')",
          rel[:3] == [50, 80, 110] and [w - f for f, w in zip(faints, wakes)] == [5] * len(wakes) and len(wakes) >= 2,
          (ent_turn, rel, wakes, longest, dict(hw=p.rb(HW), food=p.rb(FOOD), hst=p.rb(HST), stf=p.rb(STF),
                                               reactat=p.rb(S["P_ENTITIES"] + S["E_REACTAT"]), ek=p.rb(S["EXIT_KIND"]),
                                               y=p.ent(0)["Y"], hy=HY)))

    # ======================= P: poison =========================================
    scene(hp=40, food=40)
    got = {}
    for name, half in (("Spider / Giant Rat 12", 6), ("Spider Queen 18", 9), ("Black Widow 24", 12)):
        clear()
        lines.clear()
        deal_psn(half)
        got[name] = (p.rb(STX), p.rb(STF) & POIS, L_PSN in lines)
    clear()
    lines.clear()
    p.set_ent(0, HP=40)
    far3("trap_hit")
    got["DART 12"] = (p.rb(STX), p.rb(STF) & POIS, L_PSN in lines)
    check("P1 amounts: Spider / Rat 12, Queen 18, Widow 24, DART 12 (the nibble is half), POISON set, the line",
          got == {"Spider / Giant Rat 12": (12, POIS, True), "Spider Queen 18": (18, POIS, True),
                  "Black Widow 24": (24, POIS, True), "DART 12": (12, POIS, True)}, got)
    clear()
    seq = []
    for half in (6, 6, 6, 9, 12):
        deal_psn(half)
        seq.append(p.rb(STX))
    check("P2 adds per application, cap 30: 12, 24, 30 (cap), 30, 30", seq == [12, 24, 30, 30, 30], seq)
    clear()
    deal_psn(9)
    deal_psn(12)
    check("P2b Queen 18 + Widow 24 = 30 (cap)", p.rb(STX) == 30, p.rb(STX))
    check("P2c PSN_CAP / amounts in the build", (S["PSN_CAP"], S["PSN_SPIDER"], S["PSN_RAT"], S["PSN_QUEEN"],
                                                 S["PSN_WIDOW"], S["TRAP_DART_PSN"]) == (30, 12, 12, 18, 24, 12), None)
    # tick over real turns: fresh 12 -> exactly 3 HP (turns 4, 8, 12), the line on the 12th
    scene(hp=40, food=40)
    deal_psn(6)
    hp = [p.ent(0)["HP"]]
    tl = []
    for i in range(14):
        lines.clear()
        p.turn("WAIT")
        hp.append(p.ent(0)["HP"])
        tl.append((p.rb(STX), L_OFF in lines))
    drops = [i for i in range(1, 15) if hp[i] < hp[i - 1]]
    check("P3 fresh 12: -1 HP on the 4th / 8th / 12th turn only (3 HP), the timer 11 .. 0, "
          "'THE POISON WEARS OFF' on the 12th, POISON off",
          drops == [4, 8, 12] and [t for t in tl if t[1]] == [(0, True)] and tl[11] == (0, True)
          and tl[0][0] == 11 and not p.rb(STF) & POIS, (hp, drops, tl))
    # HP 1 never drops
    scene(hp=40, food=40)
    deal_psn(6)
    p.set_ent(0, HP=1)
    for _ in range(13):
        p.turn("WAIT")
    check("P4 HP 1: poison never lowers it (12+ turns), the hero alive, poison off",
          (p.ent(0)["HP"], p.rb("GAME_STATE"), p.rb(STF) & POIS) == (1, S["GS_PLAYING"], 0),
          (p.ent(0)["HP"], p.rb("GAME_STATE"), hex(p.rb(STF))))
    # a poison tick that costs HP wakes a sleeper
    scene(hp=40, food=40)
    p.wb(STF, POIS | ASLEEP)
    p.wb(ST1, 0x50)
    p.wb(STX, 5)                                 # -> 4 next turn: a tick
    lines.clear()
    p.turn("WAIT")
    check("P5 a poison tick (5 -> 4) costs 1 HP and wakes a sleeper ('YOU WAKE UP')",
          (p.ent(0)["HP"], p.rb(STF) & HOLD, L_WAKE in lines) == (39, 0, True), (p.ent(0)["HP"], hex(p.rb(STF)), lines))
    # Cure zeroes the timer
    scene(hp=30, food=40)
    p.wb(STF, POIS | HWEAK)
    p.wb(STX, 20)
    stub([0x3E, S["IT_P_CURE"], 0x21] + w16(S["pot_eff"]) + [0xCD] + w16(S["far6"]))
    check("P6 Cure: POISON cleared, ST_X zero (STS_HWEAK kept)", (p.rb(STF), p.rb(STX)) == (HWEAK, 0), (hex(p.rb(STF)), p.rb(STX)))
    # a level change keeps it (slot 0 carry)
    p.proto_start = 0
    p.boot(K_KNIGHT)
    p.settle(3)
    p.proto_start = 1
    p.wb(STF, POIS)
    p.wb(STX, 20)
    p.wmem(STUB, [0xCD] + w16(S["level_descend"]) + [0xC3] + w16(WT))
    z.cmd("set-register PC=%d" % STUB)
    d0 = p.rb("LVL_DEPTH")
    for _ in range(3000):
        z.cmd("cpu-step")
        z.cmd("run %d" % RUN_LIMIT)
        if p.pc() == WT:
            break
    p.settle(3)
    check("P7 a level descent keeps POISON and its ST_X timer (slot 0 carry)",
          p.rb("LVL_DEPTH") != d0 and (p.rb(STF) & POIS, p.rb(STX)) in ((POIS, 20), (POIS, 19)),
          (d0, p.rb("LVL_DEPTH"), hex(p.rb(STF)), p.rb(STX)))

    # ======================= E: poisoned, cannot eat ================================
    def bag():
        b = list(z.read_memory(S["BAG"], 60))
        return [(b[3 * i], b[3 * i + 1], b[3 * i + 2]) for i in range(20) if b[3 * i]]

    def put(items):
        flat = []
        for it in items:
            n, q = it if isinstance(it, tuple) else (it, 1)
            flat += [I(n), q, 0]
        p.wmem(S["BAG"], flat + [0] * (60 - len(flat)))
        stub([0x21] + w16(S["pot_sync"]) + [0xCD] + w16(S["far6"]))

    def quick(slot_of, use_turn=True):
        k = p.rb("HERO_KIND")
        p.select_slot(slot_of[k])
        lines.clear()
        t0 = p.rw("TURN_COUNTER")
        if use_turn:
            p.turn("FIRE")
        else:
            p.no_turn("FIRE")
        return p.rw("TURN_COUNTER") - t0, list(lines)

    def fx(op, arg):
        p.wb("FX_OP", op)
        p.wb("FX_ARG", arg)
        stub([0x21] + w16(S["fx_main"]) + [0xCD] + w16(S["far6"]))
        return p.rb("FX_OP")

    scene(hp=40, food=50)
    put(["F_MEAT", "P_HEAL", "S_FEAR"])
    p.wb(STF, POIS)
    p.wb(STX, 10)
    b0 = bag()
    t0 = p.rw("TURN_COUNTER")
    lines.clear()
    r = fx(S["FX_EAT"], 0)
    e1 = (r, list(lines), p.rb(FOOD), bag() == b0, p.rw("TURN_COUNTER") - t0, p.rb(STF) & POIS, p.rb(STX))
    check("E1 page EAT (fx_main FX_EAT) while poisoned: FXR_REFUSED, 'TOO SICK TO EAT', bag / FOOD / poison unchanged",
          e1 == (S["FXR_REFUSED"], [L_SICK], 50, True, 0, POIS, 10), e1)
    d, ln = quick(FOOD_SLOT, use_turn=False)
    check("E2 the FOOD quick slot (bag_pick FOOD -> fx_use): 'TOO SICK TO EAT', 0 turns, kept",
          (d, ln, p.rb(FOOD), bag() == b0) == (0, [L_SICK], 50, True), (d, ln, p.rb(FOOD)))
    p.wb(FOOD, 100)
    lines.clear()
    r = fx(S["FX_EAT"], 0)
    d, ln = quick(FOOD_SLOT, use_turn=False)
    check("E3 FOOD 100 poisoned: 'TOO SICK TO EAT' on both paths (not 'NO NEED')",
          (r, [L_SICK], d, ln) == (S["FXR_REFUSED"], lines[:1], 0, [L_SICK]), (r, lines, d, ln))
    p.wb(FOOD, 50)
    p.set_ent(0, HP=20)
    d, ln = quick(POT_SLOT)
    check("E4 the quick POTION slot still drinks while poisoned (Heal), 1 turn",
          (d, ln[:1], [x[0] for x in bag()]) == (1, ["YOU DRINK THE HEAL POTION"], [I("F_MEAT"), I("S_FEAR")]),
          (d, ln, bag()))
    d, ln = quick(SCR_SLOT)
    check("E5 the quick SCROLL slot still reads while poisoned, 1 turn", d == 1 and ln[:1] == ["YOU READ THE FEAR SCROLL"],
          (d, ln))
    # Cure, then EAT
    put(["F_MEAT", "P_CURE"])
    p.wb(STF, POIS)
    p.wb(STX, 10)
    p.set_ent(0, HP=40)
    d1, ln1 = quick(POT_SLOT)
    d2, ln2 = quick(FOOD_SLOT)
    check("E6 Cure potion, then the FOOD slot eats (1 turn, FOOD 50 -> 90)",
          (d1, ln1[:1], d2, ln2[:1], p.rb(FOOD)) == (1, ["YOU DRINK THE CURE POTION"], 1, ["YOU EAT THE MEAT"], 90),
          (d1, ln1, d2, ln2, p.rb(FOOD)))
    # the timer runs out
    put(["F_APPLE"])
    p.wb(FOOD, 50)
    p.wb(STF, POIS)
    p.wb(STX, 2)
    d0, ln0 = quick(FOOD_SLOT, use_turn=False)
    p.turn("WAIT")
    p.turn("WAIT")
    d3, ln3 = quick(FOOD_SLOT)
    check("E7 the timer runs out (2 turns): refused before, eats after",
          (d0, ln0, p.rb(STF) & POIS, d3, ln3[:1]) == (0, [L_SICK], 0, 1, ["YOU EAT THE APPLE"]),
          (d0, ln0, hex(p.rb(STF)), d3, ln3))

    # ======================= T: costs =============================================
    scene()
    z.cmd("set-breakpoint 5")

    def cost(label, setter):
        setter()
        ok = p.code([0x3E, 0, 0x21] + w16(S[label]) + [0xCD] + w16(S["far7" if label in B7_LABELS else "far6"]))
        return ok, p.tstates
    tt = {"hunger_turn WEAK, no faint": cost("hunger_turn", lambda: weak(hw=10)),
          "hunger_turn deferred": cost("hunger_turn", lambda: (weak(), p.set_ent(0, Y=HY - 1))),
          "hunger_turn faint": cost("hunger_turn", lambda: weak())}
    print(f"[info] costs incl. far6 / far7 (T): {tt}", flush=True)
    check("T1 hunger_turn: WEAK plain <= 1.2k T, deferred <= 2k, the faint turn <= 8k (line + sleep)",
          all(v[0] for v in tt.values()) and tt["hunger_turn WEAK, no faint"][1] <= 1200
          and tt["hunger_turn deferred"][1] <= 2000 and tt["hunger_turn faint"][1] <= 8000, tt)


if __name__ == "__main__":
    sys.exit(main())
