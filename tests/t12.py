#!/usr/bin/env python3
"""3E-T12 item effects (src/fx6.asm R6: fx_main / fx_quick / fx_use / fx_book /
tele_pick / pot_eff; bank-3 room_status; bank-7 do_exit's EX_TELE branch;
hunger6 hg_stage's HP_RG reset). Release build (DEBUG_KIT=0).
game.md §5 (books), §7 (food), §8 (potions / scrolls), §8.11 Q3 / Q6 / rulings 3.

PROTO room A, every monster parked unless placed:
  Q   quick FOOD: the lowest food eaten (Carrot before Meat), FOOD +10, 1 turn,
      "YOU EAT THE CARROT", bag compacted; FOOD 100 -> NO NEED, 0 turns, kept;
      no food -> NO FOOD, 0 turns; quick SCROLL = the largest stack (Fear x2 over
      Teleport x1), 1 turn; quick POTION line "YOU DRINK THE HEAL POTION"
  E   EAT: FOOD 45 + Pear -> 65: "YOU EAT THE PEAR" then "YOU FEEL WELL FED",
      HP_RG reset to 0; clamp at 100 (Meat at 90)
  D   page DRINK (page_post): Heal at HP 10 -> 20, consumed, the line, L 1
  R   READ Enchant: m +1, "YOUR WEAPON GLOWS!", consumed; at +3 / fists:
      "NOTHING HAPPENS", still consumed. Fear: the room's living monsters FEAR 6
      (MIND overwritten), a DYING one / another room untouched, "THEY FLEE IN
      TERROR!"; Sleep: ASLEEP 8 + the sleep flash, a FROZEN one skipped, "THEY
      FALL ASLEEP!"; empty room -> "NOTHING HAPPENS"; kinds immune by kx_tab skipped
  B   book READ (fx_main), RANK1 rule (game.md §5 rev 6, fx_book): starter (slot 0, 0 RNG) ->
      pity (BOOK_DRY 2) -> one uniform pick (RNG byte * n >> 8) -> Tome (Vigor / Power); depth
      gate, no keystone; B1-B8 scripted, B9 seeded random sweep and B10 whole-run sequences
      compared with tests/book_model.py (ARANK + BOOK_DRY, RNG state, line, tome stats)
Generated levels (seed_fixed):
  T   Teleport fuzz (quick SCROLL, real turns): every read = 1 turn, the scroll
      consumed, "YOU READ THE TELEPORT SCROLL" + "YOU ARE TELEPORTED!", a new room
      (present, != old, != Sanctum, != the lair while LF_UNIQUE = 0), hero E_ROOM =
      CUR_ROOM, standing on storey s at col 2..27, its 3 cols clear of the room's
      LP_CMAP footprint marks (ladders / shafts / exits / pit / block) and every
      unspent trap col, no non-pending body overlapping it, no active slot outside
      CUR_ROOM (no followers), GS_PLAYING, the screen synced; the T-cost of the
      transition (frames) and tele_pick
Run: ZRCP_PORT=<port> python3 tests/t12.py
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, stand_y, RUN_LIMIT  # noqa: E402
from proj3 import T, w16  # noqa: E402
from abil_melee import stream_text  # noqa: E402
import book_model as BM  # noqa: E402
import random  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_DYING, EF_PENDING = 1, 2, 4, 16, 64
HY = stand_y(1, 6)
HX = 12
NOWHERE = 7
STUB = S["LOWRAM_END_3B"]
RES = STUB + 200
I = lambda n: S["IT_" + n]                     # noqa: E731,E741
FOOD_SLOT = {0: 5, 1: 6}
POT_SLOT = {0: 6, 1: 7}
SCR_SLOT = {0: 7, 1: 8}
STF, ST1 = S["ST_FLAGS"], S["ST_T1"]
LP_CMW = 33


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
            print("[skip] t12 needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(h, p, check)
        print(f"t12: {len(fails)} failed" + (f": {fails[:12]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def run(h, p, check):
    lines = []
    LOGP = S["log_push"]
    WT = S["wait_tick"]
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

    def fx(op, arg):
        p.wb("FX_OP", op)
        p.wb("FX_ARG", arg)
        stub([0x21] + w16(S["fx_main"]) + [0xCD] + w16(S["far6"]))
        return p.rb("FX_OP")

    def bag():
        b = list(z.read_memory(S["BAG"], 60))
        return [(b[3 * i], b[3 * i + 1], b[3 * i + 2]) for i in range(20) if b[3 * i]]

    def put(items, worn=None, sync=True):
        flat = []
        for it in items:
            n, q = it if isinstance(it, tuple) else (it, 1)
            flat += [I(n), q, 0]
        p.wmem(S["BAG"], flat + [0] * (60 - len(flat)))
        if worn is not None:
            p.wmem(S["WORN"], [x for n in worn for x in ((I(n), 1, 0) if n else (0, 0, 0))])
        if sync:
            stub([0x21] + w16(S["pot_sync"]) + [0xCD] + w16(S["far6"]))

    def park():
        room = p.rb("CUR_ROOM")
        for sl in range(1, 16):
            e = p.ent(sl)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                p.set_ent(sl, ROOM=NOWHERE)

    def scene(hero=K_KNIGHT):
        p.boot(hero)
        park()
        p.wmem(STF, [0] * 16)
        p.wmem(ST1, [0] * 16)
        p.wmem(S["ST_T2"], [0] * 16)
        p.tick(3)
        z.cmd("set-breakpoint 5 PC=%d" % LOGP)
        lines.clear()

    def quick(slot_of, use_turn=True):
        k = p.rb("HERO_KIND")
        p.select_slot(slot_of[k])
        lines.clear()
        t0 = p.rw("TURN_COUNTER")
        if use_turn:
            ok = p.turn("FIRE")
        else:
            ok = not p.no_turn("FIRE")
        return p.rw("TURN_COUNTER") - t0, list(lines)

    # ======================= Q: quick use =========================================
    scene(K_KNIGHT)
    put(["F_MEAT", "P_HEAL", "F_CARROT"])
    p.wb("FOOD", 50)
    d, ln = quick(FOOD_SLOT)
    q1 = (d, ln, p.rb("FOOD"), [x[0] for x in bag()])
    check("Q1 quick FOOD: Carrot (lowest) eaten, FOOD 50 -> 60, 1 turn, the line, bag compacted",
          q1 == (1, ["YOU EAT THE CARROT"], 60, [I("F_MEAT"), I("P_HEAL")]), q1)
    p.wb("FOOD", 100)
    b0 = bag()
    d, ln = quick(FOOD_SLOT, use_turn=False)
    check("Q2 FOOD 100: NO NEED, 0 turns, nothing eaten", (d, ln, bag() == b0) == (0, ["NO NEED"], True), (d, ln))
    put(["P_HEAL"])
    d, ln = quick(FOOD_SLOT, use_turn=False)
    check("Q3 no food: NO FOOD, 0 turns", (d, ln) == (0, ["NO FOOD"]), (d, ln))
    put(["S_TELEPORT", ("S_FEAR", 2), "F_APPLE"])
    d, ln = quick(SCR_SLOT)
    q4 = (d, ln[:2], bag())
    check("Q4 quick SCROLL: the largest stack (Fear x2), 1 turn, 'YOU READ THE FEAR SCROLL', one left",
          q4 == (1, ["YOU READ THE FEAR SCROLL", "NOTHING HAPPENS"],
                 [(I("S_TELEPORT"), 1, 0), (I("S_FEAR"), 1, 0), (I("F_APPLE"), 1, 0)]), q4)
    p.wb("FOOD", 60)
    p.set_ent(0, HP=5)
    put(["P_HEAL", "F_APPLE"])
    d, ln = quick(POT_SLOT)
    check("Q5 quick POTION: 'YOU DRINK THE HEAL POTION' + 'YOU FEEL HEALTHIER', +10 HP, 1 turn",
          (d, ln, p.ent(0)["HP"] in (15, 16), [x[0] for x in bag()]) == (1, ["YOU DRINK THE HEAL POTION",
                                                                       "YOU FEEL HEALTHIER"], True,
                                                                       [I("F_APPLE")]), (d, ln, p.ent(0)["HP"]))
    put([])
    d, ln = quick(SCR_SLOT, use_turn=False)
    check("Q6 no scroll: NO SCROLL, 0 turns", (d, ln) == (0, ["NO SCROLL"]), (d, ln))

    # ======================= E: eat -> FED, clamp =================================
    put(["F_PEAR", "F_MEAT"])
    p.wb("FOOD", 45)
    p.wb("HSTAGE", 1)
    p.wb("HP_RG", 7)
    lines.clear()
    r = fx(S["FX_EAT"], 0)
    e1 = (r, list(lines), p.rb("FOOD"), p.rb("HSTAGE"), p.rb("HP_RG"), [x[0] for x in bag()])
    check("E1 EAT Pear at 45: 65, FED, 'YOU EAT THE PEAR' then 'YOU FEEL WELL FED', HP_RG 0, FXR_TURN",
          e1 == (1, ["YOU EAT THE PEAR", "YOU FEEL WELL FED"], 65, 0, 0, [I("F_MEAT")]), e1)
    p.wb("FOOD", 90)
    lines.clear()
    r = fx(S["FX_EAT"], 0)
    check("E2 EAT Meat at 90: clamped 100, bag empty", (r, p.rb("FOOD"), bag(), lines) ==
          (1, 100, [], ["YOU EAT THE MEAT"]), (r, p.rb("FOOD"), bag(), lines))
    put(["F_APPLE", "W_LONG"])
    check("E3 fx on gear with EAT/DRINK/READ: L 0 (no use verb), kept",
          (fx(S["FX_DRINK"], 1), len(bag())) == (0, 2))

    # ======================= D: page DRINK ========================================
    m0 = bytes(z.read_memory(S["ROOM_MAP"], S["PLAY_CELLS"]))
    put(["F_APPLE", "P_HEAL"])
    p.set_ent(0, HP=10)
    p.wmem(S["PAGE_MAP_SAVE"], list(m0))
    p.wmem(S["ROOM_MAP"], [0xEE] * S["PLAY_CELLS"])
    p.wb("PAGE_VERB", S["VB_DRINK"])
    p.wb("PAGE_SLOT", 1)
    lines.clear()
    stub([0x21] + w16(S["page_post"]) + [0xCD] + w16(S["far1"]) + [0x7D, 0x32] + w16(RES))
    dd = (p.rb(RES), p.ent(0)["HP"], bag(), list(lines), p.rb("PAGE_VERB"),
          bytes(z.read_memory(S["ROOM_MAP"], S["PLAY_CELLS"])) == m0, p.ent(0)["POT"])
    check("D1 page DRINK Heal at 10: L 1, HP 20, consumed, both lines, verb consumed, map back, E_POT 0",
          dd == (1, 20, [(I("F_APPLE"), 1, 0)], ["YOU DRINK THE HEAL POTION", "YOU FEEL HEALTHIER"], 0, True, 0), dd)
    # D2 Mana / Cure second lines
    put(["P_MANA", "P_CURE"])
    p.wb("MP", 0)
    p.wb(STF, S["STS_POISON"])
    p.wb(S["ST_T2"], 0x30)
    lines.clear()
    r1 = fx(S["FX_DRINK"], 0)
    r2 = fx(S["FX_DRINK"], 0)
    check("D2 DRINK Mana: + 'MANA SURGES!'; Cure (POISON): + 'YOU ARE CURED'", (r1, r2, lines) ==
          (1, 1, ["YOU DRINK THE MANA POTION", "MANA SURGES!", "YOU DRINK THE CURE POTION", "YOU ARE CURED"]),
          (r1, r2, lines))
    # D3 the quick FOOD / SCROLL icons grey with none in the bag (QS_CACHE via pot_sync;
    # IC1: the class QTY sums, not the stack counts)
    put(["F_APPLE", "S_FEAR", ("S_SLEEP", 2)])
    qa = tuple(z.read_memory(S["QS_CACHE"], 3))
    put(["P_HEAL"])
    qb = tuple(z.read_memory(S["QS_CACHE"], 3))
    p.tick(4)
    k = p.rb("HERO_KIND")
    sh = (p.rb(S["ICON_SH"] + FOOD_SLOT[k]) & 3, p.rb(S["ICON_SH"] + SCR_SLOT[k]) & 3)
    put(["F_APPLE", "S_FEAR"])
    p.tick(4)
    sh2 = (p.rb(S["ICON_SH"] + FOOD_SLOT[k]) & 3, p.rb(S["ICON_SH"] + SCR_SLOT[k]) & 3)
    check("D3 QS_CACHE food / scroll QTY (1, -, 3) -> (0, -, 0); drawn icons grey, then normal again",
          (qa[0], qa[2], qb[0], qb[2], sh, sh2) == (1, 3, 0, 0, (S["IS_GREY"],) * 2, (S["IS_NORMAL"],) * 2),
          (qa, qb, sh, sh2))

    # ======================= R: scrolls ===========================================
    put(["S_ENCHANT", "S_ENCHANT", "S_ENCHANT", "S_ENCHANT"], ["W_SHORT", "A_LEATHER", None, None])
    p.wmem(S["BAG"], [I("S_ENCHANT"), 4, 0] + [0] * 57)
    stub([0x21] + w16(S["hero_recalc"]) + [0xCD] + w16(S["far6"]))
    got = []
    for _ in range(4):
        lines.clear()
        r = fx(S["FX_READ"], 0)
        got.append((r, lines[-1] if lines else None, z.read_memory(S["WORN"] + 2, 1)[0],
                    p.rb(S["kind_tab"] + S["KT_BONUS"])))
    check("R1 READ Enchant x4: GLOWS m +1..+3 (bonus 1..3), the 4th NOTHING HAPPENS, all consumed",
          (got, bag()) == ([(1, "YOUR WEAPON GLOWS!", 0x20, 1), (1, "YOUR WEAPON GLOWS!", 0x40, 2),
                            (1, "YOUR WEAPON GLOWS!", 0x60, 3), (1, "NOTHING HAPPENS", 0x60, 3)], []), (got, bag()))
    put(["S_ENCHANT"], [None, "A_LEATHER", None, None])
    lines.clear()
    r = fx(S["FX_READ"], 0)
    check("R2 Enchant with fists: NOTHING HAPPENS, consumed", (r, lines, bag()) ==
          (1, ["YOU READ THE ENCHANT SCROLL", "NOTHING HAPPENS"], []), (r, lines))

    # monsters for Fear / Sleep: four slots into the room (one DYING), one elsewhere
    kxt = read_bank(p, 3, S["kx_tab"], 8 * 32)
    room = p.rb("CUR_ROOM")
    mons = [sl for sl in range(1, 16) if p.ent(sl)["FLAGS"] & EF_ACTIVE][:5]
    assert len(mons) == 5, mons

    def place_mons(flags_extra=None):
        for i, sl in enumerate(mons):
            fl = EF_ACTIVE | EF_HOSTILE | (EF_DYING if i == 3 else 0)
            p.set_ent(sl, ROOM=room if i < 4 else NOWHERE, FLAGS=fl, X=2 + 6 * i, Y=HY, REACT=0, FLT=0)
        p.wmem(STF, [0] * 16)
        p.wmem(ST1, [0] * 16)

    def imm(sl):
        return kxt[p.ent(sl)["KIND"] * 8 + S["KX_IMM"]]

    place_mons()
    p.wb(STF + mons[0], S["MIND_CONFUSED"])
    p.wb(ST1 + mons[0], 0x03)
    put(["S_FEAR"])
    lines.clear()
    r = fx(S["FX_READ"], 0)
    want_f = [sl for sl in mons[:3] if not imm(sl) & (S["IMMF_FEAR"] | 0x80)]
    st = {sl: (p.rb(STF + sl), p.rb(ST1 + sl)) for sl in mons}
    okf = all(st[sl] == ((S["MIND_FEAR"], 0x06) if sl in want_f else ((S["MIND_CONFUSED"], 3) if sl == mons[0]
                                                                         else (0, 0))) for sl in mons)
    check("R3 Fear: the room's living, non-immune monsters FEAR 6 (CONFUSED overwritten), the dying one / "
          "another room untouched; 'THEY FLEE IN TERROR!'",
          okf and r == 1 and lines == ["YOU READ THE FEAR SCROLL",
                                       "THEY FLEE IN TERROR!" if want_f else "NOTHING HAPPENS"], (st, want_f, lines))
    place_mons()
    p.wb(STF + mons[1], S["HOLD_FROZEN"])
    p.wb(ST1 + mons[1], 0x20)
    put(["S_SLEEP"])
    lines.clear()
    r = fx(S["FX_READ"], 0)
    want_s = [sl for sl in (mons[0], mons[2]) if not imm(sl) & (S["IMMF_SLEEP"] | 0x80)]
    st = {sl: (p.rb(STF + sl), p.rb(ST1 + sl), p.ent(sl)["FLT"]) for sl in mons}
    oks = all(st[sl] == ((S["HOLD_ASLEEP"], 0x80, S["SLEEP_FLASH"]) if sl in want_s else
                         ((S["HOLD_FROZEN"], 0x20, 0) if sl == mons[1] else (0, 0, 0))) for sl in mons)
    check("R4 Sleep: ASLEEP 8 + the sleep flash, the FROZEN one skipped; 'THEY FALL ASLEEP!'",
          oks and r == 1 and lines == ["YOU READ THE SLEEP SCROLL",
                                       "THEY FALL ASLEEP!" if want_s else "NOTHING HAPPENS"], (st, want_s, lines))
    print(f"[info] kx_tab immunities of the placed kinds: {[(p.ent(sl)['KIND'], imm(sl)) for sl in mons]}",
          flush=True)
    park()
    put(["S_SLEEP", "S_FEAR"])
    lines.clear()
    r1 = fx(S["FX_READ"], 0)
    r2 = fx(S["FX_READ"], 0)
    check("R5 Sleep / Fear in an empty room: NOTHING HAPPENS, consumed, 1 turn each",
          (r1, r2, lines, bag()) == (1, 1, ["YOU READ THE SLEEP SCROLL", "NOTHING HAPPENS",
                                            "YOU READ THE FEAR SCROLL", "NOTHING HAPPENS"], []), (r1, r2, lines))
    # cost: room_status with 3 bodies (direct, interrupts off)
    place_mons()
    put(["S_SLEEP"])
    p.wb("FX_OP", S["FX_READ"])
    p.wb("FX_ARG", 0)
    z.cmd("set-breakpoint 5")
    p.code([0x21] + w16(S["fx_main"]) + [0xCD] + w16(S["far6"]))
    t_sleep = p.tstates
    put(["S_ENCHANT"], sync=False)
    p.wb("FX_OP", S["FX_READ"])
    p.code([0x21] + w16(S["fx_main"]) + [0xCD] + w16(S["far6"]))
    t_ench = p.tstates
    put(["F_APPLE"], sync=False)
    p.wb("FOOD", 40)
    p.wb("FX_OP", S["FX_EAT"])
    p.code([0x21] + w16(S["fx_main"]) + [0xCD] + w16(S["far6"]))
    t_eat = p.tstates
    put(["P_HEAL"], sync=False)
    p.set_ent(0, HP=5)
    p.wb("FX_OP", S["FX_DRINK"])
    p.code([0x21] + w16(S["fx_main"]) + [0xCD] + w16(S["far6"]))
    t_drink = p.tstates
    print(f"[info] fx_main T: READ Sleep (3 bodies) {t_sleep}, READ Enchant {t_ench}, EAT {t_eat}, "
          f"DRINK {t_drink}", flush=True)
    check("R6 costs: every effect <= 25k T", max(t_sleep, t_ench, t_eat, t_drink) <= 25000,
          (t_sleep, t_ench, t_eat, t_drink))

    # ======================= B: books =============================================
    scene(K_KNIGHT)

    NAMES = {K_KNIGHT: ["POWER STRIKE", "WHIRLWIND"],
             K_WIZARD: ["SPARK", "FIREBOLT", "FROST SHARD", "DRAIN LIFE", "LIGHTNING"]}

    def book(depth, ranks=None, dry=0, seed=None):
        """One READ of a class book at LVL_DEPTH `depth`; ranks (per class slot) / dry / seed poked
        first when given (RANK1: BOOK_DRY = ARANK bits 10-11)."""
        put(["BOOK", "F_APPLE"])
        d0 = p.rb("LVL_DEPTH")
        p.wb("LVL_DEPTH", depth)
        if ranks is not None:
            p.wmem(S["ARANK"], w16(sum(r << (2 * k) for k, r in enumerate(ranks)) | dry << 10))
        if seed is not None:
            p.wmem(S["RNG_STATE"], w16(seed))
        lines.clear()
        e0 = p.ent(0)
        mp0 = p.rb("MP")
        r = fx(S["FX_READ"], 0)
        p.wb("LVL_DEPTH", d0)
        e1 = p.ent(0)
        return dict(r=r, lines=list(lines), arank=p.rw("ARANK"), rng=p.rw("RNG_STATE"),
                    bag=[x[0] for x in bag()], dhp=e1["HP"] - e0["HP"], dmhp=e1["MAXHP"] - e0["MAXHP"],
                    dmp=p.rb("MP") - mp0)

    def unpack(av, n):
        return [(av >> (2 * k)) & 3 for k in range(n)], (av >> 10) & 3

    def book_check(kind, depth, ranks, dry, seed):
        """One seeded read compared with tests/book_model.py: the new ARANK (ranks + BOOK_DRY), the RNG
        (0 or exactly 1 rng_next), the line, the tome's stats, the book consumed."""
        got = book(depth, ranks, dry, seed)
        exp = BM.book_read(kind, depth, ranks, dry, seed)
        n = len(ranks)
        e_ranks, e_dry = (exp["ranks"], exp["dry"]) if exp["act"] != "tome" else (ranks, dry)
        g_ranks, g_dry = unpack(got["arank"], n)
        nm = NAMES[kind]
        if exp["act"] == "learn":
            ln = "YOU LEARN " + nm[exp["k"]] + "!"
        elif exp["act"] == "rank":
            ln = nm[exp["k"]] + " RISES TO RANK " + str(e_ranks[exp["k"]])
        else:
            ln = "YOU FEEL MORE VIGOROUS" if kind == K_KNIGHT else "YOU FEEL MORE POWERFUL"
        stats = (3, 3, 1) if kind == K_KNIGHT else (1, 1, 3)       # tome: dHP, dMAXHP, dMP
        want_stats = stats if exp["act"] == "tome" else (0, 0, 0)
        ok = (got["r"] == 1 and (g_ranks, g_dry) == (e_ranks, e_dry) and got["rng"] == exp["rng"]
              and got["lines"][1:] == [ln] and got["bag"] == [I("F_APPLE")]
              and (got["dhp"], got["dmhp"], got["dmp"]) == want_stats)
        return ok, (kind, depth, ranks, dry, seed, got, exp)

    # B1..B8: scripted rules (the doc's step order)
    scene(K_KNIGHT)
    p.wb("MAXMP", 40)
    b1 = book(8, [0, 0], 0, 0x1234)
    check("B1 starter: no ability known -> slot 0 (Power Strike) at any depth, 0 RNG calls, book consumed",
          (b1["lines"], b1["arank"], b1["rng"], b1["bag"]) ==
          (["YOU READ THE WAR TOME", "YOU LEARN POWER STRIKE!"], 1, 0x1234, [I("F_APPLE")]), b1)
    b2 = book(1, None, 0, 0x2222)
    check("B2 Warrior D1, Power Strike known, Whirlwind locked: the one candidate = a rank-up (1 RNG call)",
          (b2["lines"][1], b2["arank"] & 0x3FF, b2["rng"] != 0x2222) == ("POWER STRIKE RISES TO RANK 2", 2, True), b2)
    b3 = book(3, [3, 0], 0, 0x3333)
    check("B3 Warrior D3, PS III: Whirlwind (unlock D3) is the only candidate -> learned",
          (b3["lines"][1], b3["arank"] & 0x3FF) == ("YOU LEARN WHIRLWIND!", 3 | 1 << 2), b3)
    b4 = book(3, [3, 3], 0, 0x4444)
    check("B4 Warrior all rank 3: Tome of Vigor HP / MAXHP +3, MP / MAXMP +1, 'YOU FEEL MORE VIGOROUS', 0 RNG",
          (b4["lines"][1], b4["dhp"], b4["dmhp"], b4["dmp"], b4["rng"]) ==
          ("YOU FEEL MORE VIGOROUS", 3, 3, 1, 0x4444), b4)
    scene(K_WIZARD)
    m1 = book(0, [0] * 5, 0, 0x5555)
    m2 = book(1, [1, 0, 0, 0, 0], 0, 0x6666)
    check("B5 Mage: the first book = Spark (any depth, 0 RNG); D1 with only Spark known: Spark II (never Firebolt)",
          (m1["lines"][1], m1["rng"], m2["lines"][1]) == ("YOU LEARN SPARK!", 0x5555, "SPARK RISES TO RANK 2"), (m1, m2))
    m3 = book(8, [3, 0, 0, 0, 0], 2, 0x7777)
    check("B6 pity: BOOK_DRY 2 + an eligible unlocked ability -> the earliest-depth one (Firebolt), 0 RNG, BOOK_DRY reset",
          (m3["lines"][1], m3["rng"], m3["arank"] >> 10) == ("YOU LEARN FIREBOLT!", 0x7777, 0), m3)
    m4 = book(8, [2, 3, 3, 3, 3], 0, 0x8888)
    check("B7 Mage Spark II + the rest rank 3: Spark III (the only candidate)",
          m4["lines"][1] == "SPARK RISES TO RANK 3", m4)
    m5 = book(8, [3] * 5, 0, 0x9999)
    check("B7 Mage all rank 3: Tome of Power (MAXMP / MP +3, HP / MAXHP +1), 0 RNG",
          (m5["lines"][1], m5["dmp"], m5["dhp"], m5["dmhp"], m5["rng"]) == ("YOU FEEL MORE POWERFUL", 3, 1, 1, 0x9999), m5)
    seen = set()
    for sd in range(1, 400, 7):
        seen.add(book(8, [3, 0, 0, 0, 0], 0, sd)["lines"][1])
    check("B8 no keystone: Mage Spark III at D8, BOOK_DRY 0: the pick is uniform over the 4 unlearned spells",
          len(seen) == 4 and "YOU LEARN FIREBOLT!" in seen, seen)

    # B9: a seeded random sweep == the model (every branch: depth gate, pity, uniform pick, tome, dry bookkeeping)
    rnd = random.Random(12)
    for kind in (K_KNIGHT, K_WIZARD):
        scene(kind)
        p.wb("MAXMP", 60)
        n = 2 if kind == K_KNIGHT else 5
        bad, tomes, cases = [], 0, 70
        for _ in range(cases):
            ranks = [rnd.choice((0, 0, 1, 2, 3)) for _ in range(n)]
            if not any(ranks):
                ranks[rnd.randrange(n)] = rnd.randrange(1, 4)
            ok, det = book_check(kind, rnd.randrange(0, 9), ranks, rnd.randrange(3), rnd.randrange(1, 65536))
            tomes += det[6]["act"] == "tome"
            if not ok:
                bad.append(det)
        check(f"B9 {'Warrior' if kind == K_KNIGHT else 'Mage'} {cases} seeded random reads == book_model "
              f"(ARANK + BOOK_DRY, RNG, line, tome stats; {tomes} tomes)", not bad, bad[:1])

    # B10: a whole run of books D1..D7 (a 2nd on D4..D7), seeded: ARANK after each read == the model
    for kind, seed0 in ((K_KNIGHT, 0xACE1), (K_WIZARD, 0xBEEF), (K_WIZARD, 0x1357)):
        scene(kind)
        p.wb("MAXMP", 60)
        n = 2 if kind == K_KNIGHT else 5
        ranks, dry, st = [0] * n, 0, seed0
        p.wmem(S["ARANK"], [0, 0])
        p.wmem(S["RNG_STATE"], w16(st))
        bad = []
        for depth in [1, 2, 3, 4, 4, 5, 5, 6, 7, 7]:
            exp = BM.book_read(kind, depth, ranks, dry, st)
            got = book(depth)
            if exp["act"] != "tome":
                ranks, dry = exp["ranks"], exp["dry"]
            st = exp["rng"]
            if (unpack(got["arank"], n), got["rng"]) != ((ranks, dry), st):
                bad.append((depth, got, exp))
        check(f"B10 {'Warrior' if kind == K_KNIGHT else 'Mage'} seed {seed0:#06x}: 10 sequential reads == book_model",
              not bad, bad[:1])

    # ======================= T: teleport fuzz (generated levels) ==================
    p.proto_start = 0
    tele_cost = []
    fuzz = []
    unsynced = []
    for si, seed in enumerate((0x1234, 0x9E37, 0x4242, 0x0101, 0xBEEF, 0x7A31, 0x5005, 0xC0DE)):
        p.load()
        p.wait_state(5)
        p.wb("seed_fixed", 1)
        z.cmd("write-memory %d %d %d" % (S["seed_value"], seed & 255, seed >> 8))
        p.wb("INPUT_REPEAT", 0)
        p.wb("ANIM_FREEZE", 1)
        p.wb("INPUT_SRC", 1)
        p.menu_start(K_KNIGHT if si % 2 == 0 else K_WIZARD)
        z.cmd("set-breakpoint 5 PC=%d" % LOGP)
        for n in range(6):
            put([("S_TELEPORT", 2)] if n % 2 == 0 else ["S_TELEPORT", "F_APPLE"])
            old = p.rb("CUR_ROOM")
            f0 = p.rw("SYS_FRAMES")
            d, ln = quick(SCR_SLOT)
            frames = (p.rw("SYS_FRAMES") - f0) & 0xFFFF
            res = tele_check(p, old)
            res.update(turns=d, lines=ln, bag=bag())
            nscr = sum(q for t, q, _ in res["bag"] if t == I("S_TELEPORT"))   # (an arrival pickup may add more)
            ok = (d == 1 and ln[:2] == ["YOU READ THE TELEPORT SCROLL", "YOU ARE TELEPORTED!"]
                  and nscr == (1 if n % 2 == 0 else 0) + ln.count("YOU PICK UP TELEPORT SCROLL") and not res["bad"])
            fuzz.append(ok)
            tele_cost.append(frames)
            if not ok:
                print(f"[detail] T seed {seed:#x} #{n}: {res}", flush=True)
            p.tick(3)
            fr, comp = p.frame(), p.composed_frame()
            diff = [i for i in range(6912) if fr[i] != comp[i]]
            # an animated-decor attr step (decor_tick) trails the display by one tick: attr-only,
            # only in a room with ANIM_N > 0; anything else is a stale / torn present
            if diff and not (all(i >= 6144 for i in diff) and p.rb("ANIM_N") and len(diff) <= 4):
                unsynced.append((seed, n, len(diff), diff[0]))
    check(f"T1 teleport fuzz ({len(fuzz)} reads over 8 seeds, both heroes): 1 turn, consumed, both lines, a legal room + "
          "spot, no body / pit / ladder box / trap under the hero, no followers, GS_PLAYING", all(fuzz),
          fuzz)
    check("T2 the displayed screen == composed after every teleport (but a decor attr step)", not unsynced,
          unsynced)
    # F: the fallbacks (review): lp_cmap's call NOPed, LP_CMAP poked; no traps
    hook = S["tp_room.cmap"]
    z.cmd("set-memory-zone 0")
    lin = 6 * 16384 + hook - 0xC000
    orig = list(z.read_memory(lin, 3))
    z.cmd("write-memory %d 0 0 0" % lin)
    z.cmd("set-memory-zone -1")
    trap_n = p.rb("TRAP_N")
    p.wb("TRAP_N", 0)
    z.cmd("set-breakpoint 5")

    def tp(s0, s1, seed):
        cm = [0 if c in s0 else 1 for c in range(LP_CMW)] + [0 if c in s1 else 1 for c in range(LP_CMW)]
        p.wmem(S["LP_CMAP"], cm)
        z.cmd("write-memory %d %d %d" % (S["RNG_STATE"], seed & 255, (seed >> 8) | 1))
        p.code([0x21] + w16(S["tele_pick"]) + [0xCD] + w16(S["far6"]))
        r = (p.rb("EXIT_COL"), p.rb("EXIT_KIND"), p.rb("EXIT_DEST"))
        p.wb("EXIT_KIND", 0)
        return r
    up, dn = S["EX_UP"], S["EX_DOWN"]
    f1 = [tp({5, 6, 7}, set(), 0x0101 * k + 7)[:2] for k in range(1, 21)]
    check("F1 storey 1 blocked, storey 0 cols 5..7 legal, 20 RNG seeds: always col 5 storey 0",
          f1 == [(5, dn)] * 20, f1)
    f2 = [tp(set(), {27, 28, 29}, sd)[:2] for sd in (0x3333, 0x4444, 0x5555)]
    f3 = tp(set(), {20, 21, 22}, 0x1111)[:2]
    check("F2 storey 1 cols 27..29 only -> col 27 (the scan reaches it); 20..22 -> col 20",
          (f2, f3) == ([(27, up)] * 3, (20, up)), (f2, f3))
    e = p.ent(0)
    f4 = tp(set(), set(), 0x6666)
    check("F3 no legal spot anywhere: every room dropped -> the current room, where the hero stands",
          f4 == (e["X"], up if e["Y"] >= 9 else dn, p.rb("CUR_ROOM")), (f4, e["X"], e["Y"], p.rb("CUR_ROOM")))
    z.cmd("set-memory-zone 0")
    z.cmd("write-memory %d %s" % (lin, " ".join(str(b) for b in orig)))
    z.cmd("set-memory-zone -1")
    p.wb("TRAP_N", trap_n)
    # tele_pick alone (direct, interrupts off; no transition)
    z.cmd("set-breakpoint 5")
    p.code([0x21] + w16(S["tele_pick"]) + [0xCD] + w16(S["far6"]))
    t_pick = p.tstates
    p.wb("EXIT_KIND", 0)
    print(f"[info] teleport turn (read -> settled) {min(tele_cost)}..{max(tele_cost)} frames; "
          f"tele_pick {t_pick} T", flush=True)
    check("T3 tele_pick (incl. lp_cmap + the line) <= 16k T", t_pick <= 16000, t_pick)


def read_bank(p, bank, addr, n):
    p.z.cmd("set-memory-zone 0")
    try:
        return p.z.read_memory(bank * 16384 + (addr - 0xC000), n)
    finally:
        p.z.cmd("set-memory-zone -1")


def tele_check(p, old):
    """The arrival invariants after a teleport (rebuilds nothing: reads LP_CMAP
    as lp_enter left it, minus the spawned bodies' own marks -> checked by box)."""
    bad = []
    room = p.rb("CUR_ROOM")
    e = p.ent(0)
    rd = S["ROOM_DESC"] + room * 16
    flags = p.rb(rd)
    if room == old:
        bad.append("same room")
    if not flags & 1:
        bad.append("room not present")
    if room == p.rb("LVL_SANCTUM"):
        bad.append("sanctum")
    if room == p.rb("LVL_LAIR") and not p.rb("LVL_FLAGS") & S["LF_UNIQUE"]:
        bad.append("lair while the boss lives")
    if e["ROOM"] != room:
        bad.append("hero E_ROOM")
    if p.rb("GAME_STATE") != 2 or p.rb("EXIT_KIND") != 0:
        bad.append("state")
    x, y = e["X"], e["Y"]
    s = 0 if y == stand_y(0, 6) else 1 if y == stand_y(1, 6) else None
    if s is None:
        bad.append(f"not standing y={y}")
        s = 1
    if not 2 <= x <= 27:
        bad.append(f"col {x}")
    # the static footprint marks (lp_cmap) the LP_CMAP keeps: recompute from the descriptor
    marks = static_marks(p, room)
    for c in range(x, x + 3):
        if c in marks[s]:
            bad.append(f"on a footprint col {c} s{s}")
    # traps
    for i in range(p.rb("TRAP_N")):
        b0, b1 = p.z.read_memory(S["TRAP_LIST"] + 2 * i, 2)
        if (b0 & 15) == room and not b0 & 0x40 and ((b0 >> 4) & 1) == s and x <= (b1 & 31) <= x + 2:
            bad.append("on a trap")
    # bodies / followers
    for sl in range(1, 16):
        m = p.ent(sl)
        if not m["FLAGS"] & EF_ACTIVE:
            continue
        if m["ROOM"] != room:
            bad.append(f"slot {sl} outside CUR_ROOM")
            continue
        if m["FLAGS"] & EF_PENDING:
            continue
        kb = p.rb(S["kind_tab"] + S["KT_BW"] + m["KIND"])
        kh = p.rb(S["kind_tab"] + S["KT_BH"] + m["KIND"])
        if m["X"] < x + 3 and x < m["X"] + kb and m["Y"] < y + 6 and y < m["Y"] + kh:
            bad.append(f"body overlap slot {sl}")
    return dict(room=room, x=x, s=s, bad=bad)


def static_marks(p, room):
    """lp_cmap's LPC_BAD cols per storey (lpop3.asm, the same rules)."""
    rd = list(p.z.read_memory(S["ROOM_DESC"] + room * 16, 16))
    m = [set(), set()]

    def mark(a, n, s):
        for c in range(a, a + n):
            if 0 <= c < LP_CMW:
                m[s].add(c)
    for s, idx in ((0, (2, 4, 6, 7)), (1, (3, 5, 6, 7))):
        for i in idx:
            if rd[i]:
                mark(rd[i] - 1, 5, s)
    if rd[8]:
        w = rd[12] or 3
        mark(rd[8] - 2, w + 4, 0)
        mark(rd[8] - 1, w + 2, 1)
    if rd[13]:
        mark(rd[13] - 2, rd[14] + 4, 0)
    if rd[9]:
        w = (rd[9] & 3) + 2
        s = (rd[9] >> 6) & 1
        mark(32 - w if rd[9] & 0x80 else 0, w, s)
    ex = rd[1]
    if ex & 1:
        mark(1, 4, 1 if ex & 0x10 else 0)
    if ex & 2:
        mark(27, 4, 1 if ex & 0x20 else 0)
    return m


if __name__ == "__main__":
    sys.exit(main())
