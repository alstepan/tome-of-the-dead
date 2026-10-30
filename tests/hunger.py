#!/usr/bin/env python3
"""3E-T9 hunger (game.md §7, §8.11 (2)) on a release build (DEBUG_KIT=0),
PROTO room A, every monster parked. Code: src/hunger6.asm (R6: hunger_turn
from end_turn, hunger_add, item_food), the WEAK / HUNGRY hooks in hit_roll /
deal_hit (combat3), h_jump (status7), xp_turn (MP_HOLD).

  N   new game: FOOD 80 (FOOD_START), FED, timers 0, no STS_HWEAK
  B   burn: -1 on every 6th turn exactly; x2 period with the Food / Scarab
      amulet worn; floor at 0 (never negative, no death)
  J   a jump turn costs FOOD_JUMP 2 extra; WEAK (hunger): no jump, no turn
  S   stages at the thresholds 50 / 25 / 10 with ONE line each: FED -> OK
      none, OK -> HUNGRY "YOU ARE HUNGRY", HUNGRY -> WEAK "YOU ARE WEAK WITH
      HUNGER" (+ STS_HWEAK), the 50th WEAK turn faints (FAINT1); hunger_add: WEAK ->
      HUNGRY none, -> FED "YOU FEEL WELL FED"; saturates at 100
  R   MP regen: Mage period 6 -> 12 while HUNGRY; none while (hunger) WEAK;
      FED HP +1 per 12 turns (to MAXHP), OK none
  W   hunger WEAK = status WEAK, not stacked: deal_hit dmg 3 -> 2 with
      either or both; Cure leaves STS_HWEAK
  P   panel: FOOD bar + stage word redrawn (PD_FOOD), the stage attr on
      cols 15..23 of row 21
  K   kept across a level descent and a bag page open / close
  T   costs: hunger_turn (plain / with a line), item_food
Run: ZRCP_PORT=<port> python3 tests/hunger.py
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, K_GOBLIN, stand_y, RUN_LIMIT, attr_at  # noqa: E402
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
FOOD, TMR, HST = S["FOOD"], S["FOOD_TMR"], S["HSTAGE"]
STF = S["ST_FLAGS"]
HWEAK, WEAK = S["STS_HWEAK"], 1 << S["STS_WEAK_BIT"]
FED, OK, HUNGRY, WEAKS = 0, 1, 2, 3
L_HUNGRY, L_WEAK, L_FED = "YOU ARE HUNGRY", "YOU ARE WEAK WITH HUNGER", "YOU FEEL WELL FED"
ATTRS = {FED: 0x44, OK: 0x46, HUNGRY: 0x42, WEAKS: 0x42}


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
            print("[skip] hunger needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(h, p, check)
        print(f"hunger: {len(fails)} failed" + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def run(h, p, check):
    lines = []
    LOGP = S["log_push"]
    WT = S["wait_tick"]
    slots = {}

    def run_to_probe():
        for _ in range(400):
            p.z.cmd("run %d" % RUN_LIMIT)
            pc = p.pc()
            if pc == LOGP:
                regs = p.z.cmd("get-registers")
                hl = int(re.search(r"HL=([0-9a-fA-F]{4})", regs).group(1), 16)
                lines.append(stream_text(p.z.read_memory(hl, 48)).rstrip("."))
                p.z.cmd("cpu-step")
                continue
            if pc in p.probes:
                return
            raise RuntimeError(f"stopped at {pc:#06x}")

    def tick(n=1):
        for _ in range(n):
            p.z.cmd("cpu-step")
            run_to_probe()
    p.tick = tick

    def stub(body):
        assert p.pc() == WT, hex(p.pc())
        p.wmem(STUB, body + [0xC3] + w16(WT))
        p.z.cmd("set-register PC=%d" % STUB)
        run_to_probe()
        assert p.pc() == WT, "stub did not return"

    def far6(label, a=0):                      # MEM-RECLAIM w2b: the hunger logic is bank 7 (far7)
        stub([0x3E, a, 0x21] + w16(S[label]) + [0xCD] + w16(S["far7" if label in B7_LABELS else "far6"]))

    def deal(att, tgt, dmg):
        inner = ([0xDD, 0x21] + w16(S["P_ENTITIES"] + att * STRIDE) + [0x3E, tgt, 0x06, dmg, 0x0E, 0, 0x1E, 0,
                 0xCD] + w16(S["deal_hit"]) + [0x7D, 0x32] + w16(RES))
        stub(p.bank3(inner))
        return p.rb(RES)

    def place(slot, x, y, flags, hp):
        p.set_ent(slot, X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=p.rb("CUR_ROOM"), FLAGS=flags, REACT=0,
                  FLT=0, HIT=0, HP=hp, MAXHP=hp)

    def scene(hero=K_KNIGHT, hp=40, mp=0, maxmp=20, boot=True):
        if boot:
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
        p.wmem(STF, [0] * 16)
        p.wmem(S["ST_T2"], [0] * 16)
        p.wb("MP", mp)
        p.wb("MAXMP", maxmp)
        p.wb("MP_RG", 0)
        p.tick(3)
        p.z.cmd("set-breakpoint 5 PC=%d" % LOGP)
        lines.clear()

    def setfood(food, tmr=0, stage=None):
        p.wb(FOOD, food)
        p.wb(TMR, tmr)
        if stage is not None:
            p.wb(HST, stage)

    def hl():
        return [x for x in lines if x in (L_HUNGRY, L_WEAK, L_FED)]

    # ======================= N: new game =========================================
    scene()
    n = (p.rb(FOOD), p.rb(TMR), p.rb(HST), p.rb("HP_RG"), p.rb("HW_TMR"), p.rb(STF) & HWEAK)
    check("N1 new game: FOOD 80, FOOD_TMR 0, FED, HP_RG / HW_TMR 0, no STS_HWEAK", n == (80, 0, 0, 0, 0, 0), n)

    # ======================= B: burn period, amulet, floor ========================
    setfood(60)
    got = []
    for _ in range(13):
        p.turn("WAIT")
        got.append(p.rb(FOOD))
    want = [60 - (i + 1) // 6 for i in range(13)]
    check("B1 FOOD -1 on every 6th turn exactly (60 -> 58 in 13 turns)", got == want, (got, want))
    for amu in ("IT_C_PLENTY", "IT_C_SCARAB"):
        setfood(60)
        p.wb(S["WORN"] + 3 * S["WS_CHARM"], S[amu])
        got = []
        for _ in range(12):
            p.turn("WAIT")
            got.append(p.rb(FOOD))
        check(f"B2 {amu} worn: period 12 (60 -> 59 on the 12th turn only)",
              got == [60] * 11 + [59], got)
    p.wb(S["WORN"] + 3 * S["WS_CHARM"], 0)
    setfood(1, tmr=5, stage=WEAKS)
    p.turn("WAIT")
    a = p.rb(FOOD)
    p.wb(TMR, 5)
    p.turn("WAIT")
    check("B3 floor: FOOD 1 -> 0 -> 0 (never negative), the hero alive",
          (a, p.rb(FOOD), p.rb("GAME_STATE"), p.ent(0)["HP"] > 0) == (0, 0, S["GS_PLAYING"], True),
          (a, p.rb(FOOD), p.rb("GAME_STATE")))

    # ======================= J: jump cost, WEAK no jump ===========================
    scene()
    setfood(60)
    x0 = p.ent(0)["X"]
    ok = p.turn("K", "L")
    check("J1 a jump turn: FOOD 60 -> 58 (FOOD_TMR 1)",
          ok and p.ent(0)["X"] != x0 and p.rb(FOOD) == 58 and p.rb(TMR) == 1, (ok, p.ent(0)["X"], p.rb(FOOD)))
    p.turn("WAIT")
    p.turn("WAIT")
    check("J2 the following plain turns cost nothing extra", p.rb(FOOD) == 58, p.rb(FOOD))
    scene()
    setfood(5)
    p.turn("WAIT")                                  # the stage follows FOOD: WEAK
    t0 = p.rw("TURN_COUNTER")
    nt = p.no_turn("K", "L")
    check("J3 hunger WEAK: no jump, no turn", nt and p.ent(0)["X"] == HX and p.rw("TURN_COUNTER") == t0
          and p.rb(STF) & HWEAK, (nt, p.ent(0)["X"], hex(p.rb(STF))))

    # ======================= S: stages and lines ==================================
    scene()
    seq = []
    for food, tag in ((50, "FED->OK"), (25, "OK->HUNGRY"), (10, "HUNGRY->WEAK")):
        setfood(food, tmr=5)
        lines.clear()
        p.turn("WAIT")
        p.turn("WAIT")
        seq.append((tag, p.rb(FOOD), p.rb(HST), p.rb(STF) & HWEAK, hl()))
    want = [("FED->OK", 49, OK, 0, []), ("OK->HUNGRY", 24, HUNGRY, 0, [L_HUNGRY]),
            ("HUNGRY->WEAK", 9, WEAKS, HWEAK, [L_WEAK])]
    check("S1 thresholds 50 / 25 / 10: stage, STS_HWEAK, one line each (none into OK)", seq == want, seq)
    lines.clear()
    for _ in range(48):
        p.turn("WAIT")
    a = hl()
    p.turn("WAIT")
    check("S2 WEAK: no repeat line any more (FAINT1: the 50th WEAK turn faints instead, tests/status1.py): "
          "ASLEEP, 'YOU FAINT FROM HUNGER', HW_TMR 20",
          a == [] and lines.count("YOU FAINT FROM HUNGER") == 1 and L_WEAK not in hl()
          and p.rb(STF) & 3 in (0, 2) and p.rb("HW_TMR") in (20, 21), (a, hl(), lines, p.rb("HW_TMR")))
    p.wb(FOOD, 5)
    lines.clear()
    far6("hunger_add", 6)
    a = (p.rb(FOOD), p.rb(HST), p.rb(STF) & HWEAK, hl())
    far6("hunger_add", 40)
    b = (p.rb(FOOD), p.rb(HST), hl())
    far6("hunger_add", 100)
    c = (p.rb(FOOD), p.rb(HST), hl())
    check("S3 hunger_add: 5 + 6 = 11 HUNGRY (no line, STS_HWEAK off); + 40 = 51 FED 'YOU FEEL WELL FED'; "
          "+ 100 saturates at 100, no 2nd line",
          (a, b, c) == ((11, HUNGRY, 0, []), (51, FED, [L_FED]), (100, FED, [L_FED])), (a, b, c))

    # ======================= R: regen =============================================
    # HUNGRY: MP_RG advances on even TURN_COUNTER only, so the 1st gain lands on
    # turn 12 or 13 (parity), then every 12
    for food, per, tag in ((80, 6, "FED"), (20, 12, "HUNGRY"), (5, None, "WEAK")):
        scene(K_WIZARD, mp=0, maxmp=12)
        setfood(food)
        got = []
        for _ in range(30):
            p.turn("WAIT")
            got.append(p.rb("MP"))
        gains = [i + 1 for i in range(30) if got[i] != (got[i - 1] if i else 0)]
        if per is None:
            ok = gains == [] and p.rb("MP_RG") == 0
        elif per == 6:
            ok = gains == [6, 12, 18, 24, 30]
        else:
            ok = len(gains) == 2 and gains[0] in (12, 13) and gains[1] - gains[0] == 12
        check(f"R1 Mage MP regen while {tag}: " + ("none, MP_RG frozen" if per is None else f"+1 per {per} turns"),
              ok, (gains, got[-1], p.rb("MP_RG")))
    for food, inc, tag in ((80, 2, "FED"), (40, 0, "OK")):
        scene(hp=40)
        p.set_ent(0, HP=10)
        setfood(food)
        for _ in range(24):
            p.turn("WAIT")
        check(f"R2 {tag}: HP +{inc} in 24 turns", p.ent(0)["HP"] == 10 + inc, p.ent(0)["HP"])
    scene(hp=40)
    for _ in range(12):
        p.turn("WAIT")
    check("R3 FED regen never above MAXHP", p.ent(0)["HP"] == 40, p.ent(0)["HP"])

    # ======================= W: WEAK alias ========================================
    scene()
    g = slots[K_GOBLIN]
    place(g, HX + 12, HY + 2, EF_ACTIVE | EF_HOSTILE | EF_LEFT, 60)
    res = []
    for st, food in ((0, 80), (HWEAK, 5), (HWEAK | WEAK, 5), (WEAK, 80)):
        p.wb(STF, st)
        p.wb(FOOD, food)
        res.append(deal(0, g, 3))
    check("W1 deal_hit dmg 3: 3 / 2 hunger WEAK / 2 both (not stacked) / 2 status WEAK", res == [3, 2, 2, 2], res)
    p.wb(STF, HWEAK | WEAK)
    p.wb(S["ST_T2"], 5)
    stub([0x3E, S["IT_P_CURE"], 0x21] + w16(S["pot_eff"]) + [0xCD] + w16(S["far6"]))
    check("W2 Cure clears status WEAK only (STS_HWEAK kept)", p.rb(STF) == HWEAK, hex(p.rb(STF)))

    # ======================= P: panel ==============================================
    scene()
    shots = {}
    for food, stg in ((80, FED), (30, OK), (20, HUNGRY), (5, WEAKS)):
        setfood(food)
        p.turn("WAIT")
        p.tick(4)
        f = p.frame()
        shots[stg] = f
        at = [attr_at(f, c, S["STAT_ROW"]) for c in range(S["FOOD_BAR_COL"], S["GEAR_COL"])]
        check(f"P1 stage {stg} (FOOD {food}): PD_FOOD drained, row 21 cols 15..23 attr {ATTRS[stg]:#04x}",
              not p.rb("PANEL_DIRTY") & 4 and at == [ATTRS[stg]] * 9, (hex(p.rb("PANEL_DIRTY")), at))

    def word(f):
        r = S["STAT_ROW"]
        out = []
        for c in range(S["FOOD_BAR_COL"], S["GEAR_COL"]):
            for ln in range(8):
                out.append(f[((r & 0x18) << 8) | (ln << 8) | ((r & 7) << 5) | c])
        return bytes(out)
    ws = {k: word(v) for k, v in shots.items()}
    check("P2 bar + word cells differ per stage", len(set(ws.values())) == 4, None)

    # ======================= K: kept across descent / page ==========================
    p.proto_start = 0                               # a generated D1 (level_descend -> D2)
    p.boot(K_KNIGHT)
    p.settle(3)
    p.proto_start = 1
    setfood(42, tmr=3)
    p.turn("WAIT")
    k0 = (p.rb(FOOD), p.rb(TMR), p.rb(HST))
    t0 = p.rw("TURN_COUNTER")
    p.tap("I")
    op = p.rb("PAGE_OPEN")
    p.tick(4)
    p.tap("I")
    p.tick(4)
    check("K1 page open / close: FOOD / FOOD_TMR / HSTAGE and the turn count unchanged",
          op == 1 and p.rb("PAGE_OPEN") == 0 and (p.rb(FOOD), p.rb(TMR), p.rb(HST)) == k0
          and p.rw("TURN_COUNTER") == t0, (op, k0, p.rb(FOOD), p.rb(TMR)))
    p.wmem(STUB, [0xCD] + w16(S["level_descend"]) + [0xC3] + w16(WT))
    p.z.cmd("set-register PC=%d" % STUB)
    d0 = p.rb("LVL_DEPTH")
    for _ in range(3000):
        p.z.cmd("cpu-step")
        p.z.cmd("run %d" % RUN_LIMIT)
        if p.pc() == WT:
            break
    p.settle(3)
    check("K2 level descent keeps FOOD / FOOD_TMR / HSTAGE",
          p.rb("LVL_DEPTH") != d0 and (p.rb(FOOD), p.rb(TMR), p.rb(HST)) == k0,
          (d0, p.rb("LVL_DEPTH"), p.rb(FOOD), p.rb(TMR), p.rb(HST)))

    # ======================= T: costs ===============================================
    scene()
    p.z.cmd("set-breakpoint 5")

    def cost(label, food=60, tmr=0, stage=FED, a=0):
        setfood(food, tmr, stage)
        ok = p.code([0x3E, a, 0x21] + w16(S[label]) + [0xCD] + w16(S["far7" if label in B7_LABELS else "far6"]))
        return ok, p.tstates
    tt = {"plain": cost("hunger_turn"), "burn": cost("hunger_turn", tmr=5),
          "burn + HUNGRY line": cost("hunger_turn", food=25, tmr=5, stage=OK),
          "item_food HUNGRY": cost("item_food", food=20, stage=HUNGRY)}
    print(f"[info] costs incl. far6 / far7 (T): {tt}", flush=True)
    # MEM-RECLAIM w2b: hunger_turn is bank-7 code (contended, ~+0.25k measured) that end_turn calls
    # directly; the stub's far7 (~0.25k) is test overhead the game no longer pays (it paid far6 before):
    # the plain / burn cap incl. the far call is 1.5k (was 1.2k incl. far6; budget.py: every tick -88 T).
    check("T1 hunger_turn <= 1.5k T plain / burn incl. the test's far7, <= 5k with a line; item_food <= 9k (1st frame only)",
          all(v[0] for v in tt.values()) and tt["plain"][1] <= 1500 and tt["burn"][1] <= 1500
          and tt["burn + HUNGRY line"][1] <= 5000 and tt["item_food HUNGRY"][1] <= 9000, tt)


if __name__ == "__main__":
    sys.exit(main())
