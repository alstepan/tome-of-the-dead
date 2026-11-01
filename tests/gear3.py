#!/usr/bin/env python3
"""GEAR3: Enchant hits a random worn item (src/gear6.asm ench_any / ea_pick / ea_scan, called by
fx6.asm fx_read; docs/design/gear_rules.md 3 and vectors G3-1 .. G3-10). Release build (DEBUG_KIT=0).
PROTO room A, every monster parked; the scroll is read through the real fx path (fx_main FX_READ,
the t12 stub technique) or the quick SCROLL slot (G3-10).

  G3-1..2   worn SHORT 00 / LEATHER $60 / HELM 00: n = 2, ONE draw, the first L even -> k 0 (SHORT $20,
            "ENCHANTED: SHORT SWORD", KT_BONUS +1) / odd -> HELM $20 (HERO_DEF +1)
  G3-3      all three worn $60; bag [ENCHANT, HEAL, CHAIN $02]: the scroll leaves first; the bag fallback picks
            CHAIN (bag slot 1 after the take), 1 draw, CHAIN $22, HERO_DEF unchanged
  G3-4      all worn $60 (or empty) + a charm; no gear in the bag (potions only): NOTHING HAPPENS, 0 draws,
            scroll gone, 1 turn
  G3-5      fists, no armour / helmet, a worn MIGHT RING; bag [HOOD]: the charm is no candidate, HOOD $20
  G3-6      3 worn candidates; rng_mod(3) rejects a=3 (2 draws) -> the ARMOUR item
  G3-7      a unique (MIRROR HELM) qualifies; the others $60
  G3-8      CHAIN $A0 (m -3) the only candidate -> $C0, the page's " WORN OUT" gone
  G3-9      HELM $42 (m +2, q +2) -> $62, the page " +5 DEF+6"; a 2nd Enchant skips it (NOTHING HAPPENS)
  G3-10     quick SCROLL slot = G3-1's result
  G3-11     Rune Staff: KT_BONUS +1 (melee die bonus), TYPE and q bits untouched (the spell bonus stays by type)
  G3-12     the cap: 12 reads on a worn trio end at m +3 each ($60), then NOTHING HAPPENS
  G3-13     distribution: 400 seeds, 3 worn candidates: every target within 133 +- 40, and every seed equals
            tools/items_model.enchant_target (target, RNG state after)
  G3-14     random configurations (worn / bag mixes with charms, potions, +3 items): the Z80 == the model
            (the chosen item, the new ISTATE, the RNG draws); a charm is never changed; hero_recalc
            runs only for a worn target (the bag path leaves KT_BONUS / HERO_DEF alone)
Run: ZRCP_PORT=<port> python3 tests/gear3.py
"""
import random
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
import items_model as M  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
NOWHERE = 7
EF_ACTIVE = 1
STUB = S["LOWRAM_END_3B"]
RES = STUB + 200
BUF = STUB + 32
SCR_SLOT = {0: 8, 1: 8}
I = lambda n: S["IT_" + n]                     # noqa: E731,E741
NAMES = {}
for _ln in (HERE.parent / "src" / "items.txt").read_text().splitlines():
    _m = re.match(r"^(IT_\w+)\s*\|\s*([^|]+?)\s*\|", _ln)
    if _m and _m.group(2) != "-":
        NAMES[S[_m.group(1)]] = _m.group(2)
WORN, BAG, STR = S["WORN"], S["BAG"], S["IR_STRIDE"]


def seed_for(pattern):
    """A gameplay RNG_STATE whose successive rng_next bytes satisfy pattern = [predicate(L), ...]."""
    for st in range(1, 65536):
        s, ok = st, True
        for pr in pattern:
            s, l = BM.rng_next(s)
            if not pr(l):
                ok = False
                break
        if ok:
            return st
    raise RuntimeError("no seed")


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
            print("[skip] gear3 needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(h, p, check)
        print(f"gear3: {len(fails)} failed" + (f": {fails[:12]}" if fails else ""), flush=True)
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

    def far6(sym):
        stub([0x21] + w16(S[sym]) + [0xCD] + w16(S["far6"]))

    def fx(op, arg):
        p.wb("FX_OP", op)
        p.wb("FX_ARG", arg)
        far6("fx_main")
        return p.rb("FX_OP")

    def bag_recs():
        b = list(z.read_memory(BAG, 60))
        return [(b[3 * i], b[3 * i + 1], b[3 * i + 2]) for i in range(20)]

    def bag():
        return [r for r in bag_recs() if r[0]]

    def worn():
        w = list(z.read_memory(WORN, 12))
        return [(w[3 * i], w[3 * i + 1], w[3 * i + 2]) for i in range(4)]

    def put(bag_items, worn_items):
        """bag_items: [(name, istate) | name]; worn_items: [(name, istate) | name | None] x4."""
        flat = []
        for it in bag_items:
            n, ist = it if isinstance(it, tuple) else (it, 0)
            flat += [I(n), 1, ist]
        p.wmem(BAG, flat + [0] * (60 - len(flat)))
        wf = []
        for it in worn_items:
            if it is None:
                wf += [0, 0, 0]
            else:
                n, ist = it if isinstance(it, tuple) else (it, 0)
                wf += [I(n), 1, ist]
        p.wmem(WORN, wf)
        far6("pot_sync")
        far6("hero_recalc")

    def park():
        room = p.rb("CUR_ROOM")
        for sl in range(1, 16):
            e = p.ent(sl)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                p.set_ent(sl, ROOM=NOWHERE)

    def scene(hero=K_KNIGHT):
        p.boot(hero)
        park()
        for nm in ("ST_FLAGS", "ST_T1", "ST_T2", "ST_X"):
            p.wmem(S[nm], [0] * 16)
        p.tick(3)
        z.cmd("set-breakpoint 5 PC=%d" % LOGP)
        lines.clear()

    def stats():
        k = p.rb("HERO_KIND")
        return dict(bon=p.rb(S["kind_tab"] + S["KT_BONUS"] + k), die=p.rb(S["kind_tab"] + S["KT_DIE"] + k),
                    df=p.rb("HERO_DEF"), mmp=p.rb("MAXMP"), gmp=p.rb("GEAR_MP"))

    def fmt(slot):
        """it_fmt of bag slot `slot` (the page's stat line)."""
        stub([0x3E, slot, 0x11] + w16(BUF) + [0x21] + w16(S["it_fmt"]) + [0xCD] + w16(S["far6"])
             + [0xED, 0x53] + w16(RES))
        end = int.from_bytes(bytes(z.read_memory(RES, 2)), 'little')
        return bytes(z.read_memory(BUF, end - BUF)).decode("latin-1")

    def read_enchant(rng, ctx=""):
        """Read the Enchant scroll at bag slot 0 with RNG_STATE = rng; returns the observation."""
        if rng is not None:
            p.wmem(S["RNG_STATE"], w16(rng))
        s0 = stats()
        lines.clear()
        r = fx(S["FX_READ"], 0)
        return dict(r=r, lines=list(lines), rng=p.rw("RNG_STATE"), worn=worn(), bag=bag(), s0=s0, s1=stats())

    def model(worn_in, bag_in, rng):
        """items_model.enchant_target on the post-take state; returns (result, draws, rng_after)."""
        st = [rng]
        n = [0]

        def step():
            st[0], l = BM.rng_next(st[0])
            n[0] += 1
            return l
        res = M.enchant_target([(t, i) for t, _, i in worn_in[:3]], [(t, i) for t, _, i in bag_in], step)
        return res, n[0], st[0]

    def draws(obs, rng):
        """How many rng_next calls produced obs['rng'] from rng (<= 40)."""
        s = rng
        for n in range(41):
            if s == obs["rng"]:
                return n
            s, _ = BM.rng_next(s)
        return None

    ENC = "S_ENCHANT"
    LINE_READ = "YOU READ THE ENCHANT SCROLL"

    # ---- G3-1 / G3-2 ----------------------------------------------------------------------
    seed_even = seed_for([lambda l: l % 2 == 0])
    seed_odd = seed_for([lambda l: l % 2 == 1])
    scene(K_KNIGHT)
    put([ENC], [("W_SHORT", 0x00), ("A_LEATHER", 0x60), ("H_HELM", 0x00), None])
    o = read_enchant(seed_even)
    check("G3-1 even L: n = 2, 1 draw, k 0: SHORT $20, ENCHANTED: SHORT SWORD, KT_BONUS +1, scroll gone",
          (o["r"], o["lines"], o["worn"][0][2], o["worn"][1][2], o["worn"][2][2], draws(o, seed_even),
           o["s1"]["bon"] - o["s0"]["bon"], o["s1"]["df"] - o["s0"]["df"], o["bag"]) ==
          (1, [LINE_READ, "ENCHANTED: SHORT SWORD"], 0x20, 0x60, 0x00, 1, 1, 0, []), o)
    put([ENC], [("W_SHORT", 0x00), ("A_LEATHER", 0x60), ("H_HELM", 0x00), None])
    o = read_enchant(seed_odd)
    check("G3-2 odd L: k 1 -> HELM $20, HERO_DEF +1, the sword untouched",
          (o["r"], o["lines"], o["worn"][0][2], o["worn"][2][2], draws(o, seed_odd),
           o["s1"]["df"] - o["s0"]["df"], o["s1"]["bon"] - o["s0"]["bon"]) ==
          (1, [LINE_READ, "ENCHANTED: HELM"], 0x00, 0x20, 1, 1, 0), o)

    # ---- G3-3: the bag fallback --------------------------------------------------------------
    put([ENC, "P_HEAL", ("A_CHAIN", 0x02)], [("W_SHORT", 0x60), ("A_LEATHER", 0x60), ("H_HELM", 0x60), None])
    o = read_enchant(seed_even)
    check("G3-3 all worn +3: the bag's CHAIN (slot 1 after the take) $02 -> $22, 1 draw, HERO_DEF / KT_BONUS unchanged",
          (o["lines"], o["bag"], draws(o, seed_even), o["s1"]["df"] - o["s0"]["df"],
           o["s1"]["bon"] - o["s0"]["bon"], o["worn"][0][2]) ==
          ([LINE_READ, "ENCHANTED: CHAIN MAIL"], [(I("P_HEAL"), 1, 0), (I("A_CHAIN"), 1, 0x22)], 1, 0, 0, 0x60), o)

    # ---- G3-4: nothing ------------------------------------------------------------------------
    for tag, wk, bg in (("all +3 + a charm, potions only",
                         [("W_SHORT", 0x60), ("A_LEATHER", 0x60), ("H_HELM", 0x60), ("C_MIGHT", 0)], ["P_HEAL", "P_MANA"]),
                        ("empty + a charm, empty bag", [None, None, None, ("C_WARD", 0)], []),
                        ("empty, the bag holds charms / bow / book / food only",
                         [None, None, None, None], ["C_MIGHT", "BOW", "BOOK", "F_APPLE", "S_FEAR"])):
        put([ENC] + bg, wk)
        b_before = bag()[1:]
        o = read_enchant(seed_even)
        check(f"G3-4 {tag}: NOTHING HAPPENS, 0 draws, scroll gone, 1 turn, bag/worn unchanged",
              (o["r"], o["lines"], o["rng"], o["bag"] == b_before) ==
              (1, [LINE_READ, "NOTHING HAPPENS"], seed_even, True), o)

    # ---- G3-5: a charm is no candidate -----------------------------------------------------------
    put([ENC, "H_HOOD"], [None, None, None, ("C_MIGHT", 0)])
    o = read_enchant(seed_even)
    check("G3-5 fists / no armour / no helmet / worn MIGHT RING: the charm skipped, the bag HOOD $20",
          (o["lines"], o["bag"], o["worn"][3][2], draws(o, seed_even)) ==
          ([LINE_READ, "ENCHANTED: HOOD"], [(I("H_HOOD"), 1, 0x20)], 0, 1), o)

    # ---- G3-6: rng_mod(3) rejection ---------------------------------------------------------------
    seed_rej = seed_for([lambda l: l & 3 == 3, lambda l: l & 3 == 1])
    put([ENC], [("W_SHORT", 0), ("A_LEATHER", 0), ("H_HELM", 0), None])
    o = read_enchant(seed_rej)
    check("G3-6 n = 3, L&3 = 3 rejected then 1: 2 draws, the ARMOUR item enchanted",
          (o["lines"][-1], draws(o, seed_rej), [w[2] for w in o["worn"][:3]]) ==
          ("ENCHANTED: LEATHER", 2, [0, 0x20, 0]), o)

    # ---- G3-7: a unique qualifies -------------------------------------------------------------------
    put([ENC], [("W_SHORT", 0x60), ("A_LEATHER", 0x60), ("H_MIRROR", 0x00), None])
    o = read_enchant(seed_even)
    check("G3-7 MIRROR HELM $00 the only candidate: $20, +1 DEF (2 -> 3)",
          (o["lines"][-1], o["worn"][2][2], o["s1"]["df"] - o["s0"]["df"]) == ("ENCHANTED: MIRROR HELM", 0x20, 1), o)

    # ---- G3-8: m -3 ----------------------------------------------------------------------------------
    put([ENC, ("A_CHAIN", 0xA0)], [("W_SHORT", 0x60), ("A_LEATHER", 0x60), ("H_HELM", 0x60), None])
    f0 = fmt(1)
    o = read_enchant(seed_even)
    f1 = fmt(0)
    check("G3-8 CHAIN $A0 (m -3) the only candidate -> $C0; the page ' WORN OUT' gone (' -2' after)",
          (f0.startswith(" WORN OUT"), o["bag"], f1) == (True, [(I("A_CHAIN"), 1, 0xC0)], " -2"), (f0, f1, o))

    # ---- G3-9: m +2 q +2, the page, the cap ------------------------------------------------------------
    put([ENC, ENC], [("W_SHORT", 0x60), ("A_LEATHER", 0x60), ("H_HELM", 0x42), None])
    o = read_enchant(seed_even)
    put([("H_HELM", o["worn"][2][2])], [None] * 4)         # the page line of the result, in the bag
    f = fmt(0)
    check("G3-9 HELM $42 -> $62; the page ' +5 DEF+6'", (o["worn"][2][2], f) == (0x62, " +5 DEF+6"), (o, f))
    put([ENC], [("W_SHORT", 0x60), ("A_LEATHER", 0x60), ("H_HELM", 0x62), None])
    o = read_enchant(seed_even)
    check("G3-9b a 2nd Enchant skips it: NOTHING HAPPENS, 0 draws",
          (o["lines"][-1], o["rng"]) == ("NOTHING HAPPENS", seed_even), o)

    # ---- G3-10: the quick SCROLL slot -----------------------------------------------------------------------
    scene(K_KNIGHT)
    put([ENC], [("W_SHORT", 0x00), ("A_LEATHER", 0x60), ("H_HELM", 0x00), None])
    p.wmem(S["RNG_STATE"], w16(seed_even))
    p.select_slot(SCR_SLOT[0])
    lines.clear()
    t0 = p.rw("TURN_COUNTER")
    ok = p.turn("FIRE")
    check("G3-10 quick SCROLL slot = G3-1: a turn, ENCHANTED: SHORT SWORD, SHORT $20, 1 draw",
          (p.rw("TURN_COUNTER") - t0, lines[-1:], worn()[0][2], draws(dict(rng=p.rw("RNG_STATE")), seed_even)) ==
          (1, ["ENCHANTED: SHORT SWORD"], 0x20, 1), (lines, worn()))

    # ---- G3-11: the Rune Staff ---------------------------------------------------------------------------------
    scene(K_WIZARD)
    put([ENC], [("W_RUNE", 0x01), None, None, None])        # q +1
    o = read_enchant(seed_even)
    check("G3-11 Rune Staff q+1: m +1 -> I $21, TYPE kept, KT_BONUS 1 -> 2 (melee only), die 4",
          (o["worn"][0][0], o["worn"][0][2], o["s0"]["bon"], o["s1"]["bon"], o["s1"]["die"]) ==
          (I("W_RUNE"), 0x21, 1, 2, 4), o)

    # ---- G3-12: the cap --------------------------------------------------------------------------------------------
    scene(K_KNIGHT)
    put([ENC] * 12, [("W_SHORT", 0), ("A_LEATHER", 0), ("H_HELM", 0), None])
    res = []
    for i in range(12):
        res.append(read_enchant(1234 + i))
    check("G3-12 12 reads on a worn trio: all end at m +3 ($60), reads 10..12 NOTHING HAPPENS, no q/m overflow",
          ([w[2] for w in res[-1]["worn"][:3]] == [0x60] * 3 and
           [o["lines"][-1] for o in res[9:]] == ["NOTHING HAPPENS"] * 3 and
           all(o["lines"][-1].startswith("ENCHANTED") for o in res[:9])), [o["lines"][-1] for o in res])

    # ---- G3-13: the distribution over 400 seeds ---------------------------------------------------------------------
    scene(K_KNIGHT)
    cnt = [0, 0, 0]
    bad = []
    for sd in range(1, 401):
        rng = (sd * 0x9E37) & 0xFFFF or 1
        put([ENC], [("W_SHORT", 0), ("A_LEATHER", 0), ("H_HELM", 0), None])
        o = read_enchant(rng)
        w3 = [w[2] for w in o["worn"][:3]]
        hit = [i for i, v in enumerate(w3) if v == 0x20]
        res, nd, rs = model([(I("W_SHORT"), 1, 0), (I("A_LEATHER"), 1, 0), (I("H_HELM"), 1, 0)], [], rng)
        if len(hit) != 1 or hit[0] != res[1] or o["rng"] != rs:
            bad.append((sd, hit, res, hex(o["rng"]), hex(rs)))
        else:
            cnt[hit[0]] += 1
    check("G3-13 400 seeds: Z80 == enchant_target (target + RNG state) every seed", not bad, bad[:3])
    check("G3-13 distribution weapon / armour / helmet within 133 +- 40", all(93 <= c <= 173 for c in cnt), cnt)

    # ---- G3-14: random configurations vs the model ------------------------------------------------------------------
    rnd = random.Random(20261101)
    wpn = ["W_SHORT", "W_LONG", "W_AXE", "W_CLEAVER", "W_RUNE"]
    arm = ["A_LEATHER", "A_CHAIN", "A_PLATE", "A_SILK", "A_ROBE"]
    hlm = ["H_HOOD", "H_HELM", "H_KING", "H_MIRROR"]
    chm = ["C_MIGHT", "C_WARD", "C_FIRE", "C_MANA", "C_SCARAB"]
    junk = ["P_HEAL", "P_MANA", "F_APPLE", "S_FEAR", "BOOK", "BOW", "S_TELEPORT"]
    mq = lambda: rnd.choice([0x00, 0x01, 0x07, 0x20, 0x40, 0x60, 0x62, 0xA0, 0xC1, 0xE7, 0x42])  # noqa: E731
    bad, nworn, nbag, nnone, bagk = [], 0, 0, 0, 0
    scene(K_KNIGHT)
    for it in range(150):
        wk = [(rnd.choice(wpn), mq()) if rnd.random() < .7 else None,
              (rnd.choice(arm), mq()) if rnd.random() < .7 else None,
              (rnd.choice(hlm), mq()) if rnd.random() < .6 else None,
              (rnd.choice(chm), 0) if rnd.random() < .5 else None]
        bg = []
        for _ in range(rnd.randint(0, 8)):
            c = rnd.random()
            if c < .45:
                bg.append((rnd.choice(wpn + arm + hlm), mq()))
            elif c < .6:
                bg.append((rnd.choice(chm), 0))
            else:
                bg.append(rnd.choice(junk))
        put([ENC] + bg, wk)
        wk_recs = worn()
        bg_recs = bag()[1:]
        rng = rnd.randint(1, 65535)
        res, nd, rs = model(wk_recs, bg_recs, rng)
        o = read_enchant(rng)
        exp_w = [list(w) for w in wk_recs]
        exp_b = [list(b) for b in bg_recs]
        recalc = False
        if res is None:
            nnone += 1
            exp_line = "NOTHING HAPPENS"
        else:
            where, i, nist = res
            if where == "worn":
                exp_w[i][2] = nist
                recalc = True
                nworn += 1
                exp_line = "ENCHANTED: " + NAMES[exp_w[i][0]]
            else:
                exp_b[i][2] = nist
                nbag += 1
                exp_line = "ENCHANTED: " + NAMES[exp_b[i][0]]
        okw = [list(w) for w in o["worn"]] == exp_w
        okb = [list(b) for b in o["bag"]] == exp_b
        ok_rng = o["rng"] == rs and draws(o, rng) == nd
        ok_line = o["lines"][-1] == exp_line
        charm_ok = o["worn"][3][2] == 0 and all(t < I("C_MIGHT") or i == 0 for t, _, i in o["bag"])
        ok_recalc = recalc or (o["s1"]["bon"] == o["s0"]["bon"] and o["s1"]["df"] == o["s0"]["df"])
        if not (okw and okb and ok_rng and ok_line and charm_ok and ok_recalc and o["r"] == 1):
            bad.append((it, wk_recs, bg_recs, hex(rng), res, o["worn"], o["bag"], o["lines"], hex(o["rng"]), hex(rs)))
    check("G3-14 150 random configs == the model (item, ISTATE, draws, line); charms untouched; recalc only for a worn target",
          not bad, bad[:1])
    check("G3-14 coverage: worn / bag / nothing outcomes all exercised", nworn > 20 and nbag > 5 and nnone > 5,
          (nworn, nbag, nnone))
    print(f"[info] G3-14 outcomes: worn {nworn}, bag {nbag}, none {nnone}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
