#!/usr/bin/env python3
"""Self-test of tools/balance_sim.py (BAL-1b).  No emulator; needs build/ (tests/combat_tables.load).
Run: python3 tests/balance_sim_selftest.py
Checks: tables load == tests/combat_tables transcription and overrides apply; determinism; hand-checkable
single-fight cases per hero (exact expectation computed here by DP / enumeration, compared with the sim's
own resolve functions); damage-pipeline cases (resist order, staff bonus before W, DEF); monotonicity."""
import os
import random
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(REPO, "tests"))
import balance_sim as B  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    if not ok:
        FAILS.append("%s %s" % (name, detail))


def new_game(D, hero, seed=1):
    g = B.Game(D, hero, "average", random.Random(seed))
    g.wall = 28
    g.behind = 5
    g.turns = 0
    return g


def test_tables(D):
    import combat_tables as C
    for name, rows in C.RANKS.items():
        stem = {"Whirl": "Whirl"}.get(name, name)
        for r, row in enumerate(rows):
            got = D.rank[stem][r]
            check("rank %s %d" % (name, r + 1), [got[k] & 0xFF for k in ("mp", "range", "die", "bonus", "bounces", "effect")] == list(row), str(got))
    check("xpn", D.xpn == C.XP_NEXT, str(D.xpn))
    check("ogre row", D.k[D.id("OGRE")]["hp"] == 36 and D.k[D.id("OGRE")]["res"][B.PHYS] == 0 and D.k[D.id("OGRE")]["res"][B.SHOCK] == 4)
    check("vampire fire N (package 4)", D.k[D.id("VAMPIRE")]["res"][B.FIRE] == 0)
    # overrides
    ov = B.parse_set(["ab_rank.Firebolt.1.range=9", "kx.SPIDER.FIRE=N", "kind.OGRE.hp=99", "param.HP_BONUS=5"])
    D2 = B.Data(ov)
    check("override rank", D2.rank["Firebolt"][0]["range"] == 9 and D.rank["Firebolt"][0]["range"] == 8)
    check("override kx", D2.k[D2.id("SPIDER")]["res"][B.FIRE] == 0)
    check("override kind", D2.k[D2.id("OGRE")]["hp"] == 99)
    import json
    A = B.Data(json.load(open(os.path.join(REPO, "tools/balance_optionA.json"))))
    check("optionA firebolt r1", (A.rank["Firebolt"][0]["range"], A.rank["Firebolt"][0]["die"], A.rank["Firebolt"][0]["bonus"]) == (8, 6, 2))
    check("optionA mummy phys N", A.k[A.id("MUMMY")]["res"][B.PHYS] == 0)
    check("optionA ghost cold R", A.k[A.id("GHOST")]["res"][B.COLD] == 1)


def test_determinism(D):
    a = B.run_batch(D, "M", "average", 40, "s", 0)
    b = B.run_batch(D, "M", "average", 40, "s", 0)
    c = B.run_batch(D, "M", "average", 40, "t", 0)
    check("determinism same seed", a == b)
    check("determinism other seed differs", a != c)
    p1 = B.run_batch(D, "M", "average", 20, "s", 0)
    p2 = B.run_batch(D, "M", "average", 20, "s", 20)
    both = B.merge_res(p1, p2)
    check("chunk additivity (jobs split)", both["n"] == 40 and both["wins"] == a["wins"] and both["death_depth"] == a["death_depth"])


def test_warrior_goblin(D):
    """Warrior L1 sword 1d6 vs D1 Goblin (6 hp, eva 1, DEF 0, neutral): P(hit) = (11+3-1)/20 = 0.65.
    Exact expected number of swings to deal >= 6 computed here by DP over a 1d6 + 65 % hit chain."""
    p = 0.65
    E = [0.0] * 7           # E[h] = expected swings with h hp left
    for h in range(1, 7):
        # swing: miss p'=0.35 -> same state; hit -> roll r in 1..6
        s = 1.0
        for r in range(1, 7):
            if h - r > 0:
                s += p / 6 * E[h - r]
        E[h] = s / (1 - (1 - p))
        E[h] = (1 + p * sum(E[h - r] for r in range(1, 7) if h - r > 0) / 6) / p
    want = E[6]
    n, tot = 4000, 0
    for i in range(n):
        g = new_game(D, "W", i)
        g.depth = 1
        m = B.Mon(D, D.id("GOBLIN"), 1)
        m.x = 1
        check_p = abs(g.hit_hero_chance(m.atk) - 0.0) >= 0  # touch
        sw = 0
        while m.hp > 0:
            sw += 1
            g.melee(m)
        tot += sw
    got = tot / n
    check("W goblin swings %.2f vs DP %.2f" % (got, want), abs(got - want) < 0.12 * want, "")
    g = new_game(D, "W")
    gob = B.Mon(D, D.id("GOBLIN"), 1)
    check("W hit chance 65%", abs(((11 + g.hero_atk() - gob.k["eva"]) / 20.0) - 0.65) < 1e-9)


def test_mage_spark(D):
    """Mage Spark R1 (1d4+1, always hits) vs D1 Goblin (6 hp): casts needed, exact by enumeration;
    MP spent 2 per cast; Oak Staff has no spell bonus."""
    from itertools import product
    want = 0.0
    # P(needing k casts): sum of k iid {2,3,4,5} >= 6
    dist = {0: 1.0}
    k = 0
    exp = 0.0
    while dist:
        k += 1
        nd, done = {}, 0.0
        for tot, pr in dist.items():
            for d in (2, 3, 4, 5):
                t = tot + d
                if t >= 6:
                    done += pr / 4
                else:
                    nd[t] = nd.get(t, 0) + pr / 4
        exp += k * done
        dist = nd
    n, tot = 3000, 0
    for i in range(n):
        g = new_game(D, "M", i)
        g.h.ranks["Spark"] = 1
        g.h.mp = g.h.maxmp = 12
        m = B.Mon(D, D.id("GOBLIN"), 1)
        m.x = 4
        al = [m]
        c = 0
        while m.hp > 0:
            mp0 = g.h.mp
            g.mage_act(al, m, al)
            c += 1
            check("spark costs 2 mp", mp0 - g.h.mp == 2, str(mp0 - g.h.mp))
        tot += c
    got = tot / n
    check("M spark casts %.2f vs exact %.2f" % (got, exp), abs(got - exp) < 0.05 * exp)


def test_damage_pipeline(D):
    """Resist order (docs combat3.asm): R halves the ROLL (min 1) then -DEF for PHYS; W doubles after R; spells
    ignore DEF; the staff bonus is added to the roll BEFORE the W multiplier."""
    g = new_game(D, "W")
    ogre = B.Mon(D, D.id("OGRE"), 4)           # PHYS neutral since the balance packages, DEF 2
    ogre.hp = ogre.maxhp = 100
    g.strike(ogre, B.PHYS, 6, melee=True)
    check("ogre 6 phys -> 6-2=4", ogre.hp == 96, str(ogre.hp))
    ogre.hp = 100
    g.strike(ogre, B.PHYS, 12, melee=True)
    check("ogre 12 phys -> 12-2=10", ogre.hp == 90, str(ogre.hp))
    m = new_game(D, "M")
    m.h.gear["w"] = "Bone Staff"
    m.recalc()
    m.h.ranks["Firebolt"] = 1
    m.h.mp = 30
    check("bone staff spell bonus", m.h.spellbonus == 2)
    vamp = B.Mon(D, D.id("VAMPIRE"), 1)       # FIRE N (package 4; was W)
    vamp.hp = vamp.maxhp = 500
    vamp.x = 3
    seen = set()
    for i in range(400):
        vamp.hp = 500
        m.h.mp = 30
        m.cast("Firebolt", 1, D.rank["Firebolt"][0], [vamp], vamp)
        seen.add(500 - vamp.hp)
    # Firebolt R1 1d8-1 (package 5; was 1d8+0), +2 staff, neutral: d+1 = 2..9
    check("firebolt N staff range", min(seen) == 2 and max(seen) == 9, str(sorted(seen)))
    ghost = B.Mon(D, D.id("GHOST"), 1)         # SHOCK R (package 4; was X): half damage, no reflect
    ghost.hp = ghost.maxhp = 50
    ghost.x = 3
    m.h.ranks["Spark"] = 1
    hp0 = m.h.hp
    m.h.hp = m.h.maxhp = 500
    m.cast("Spark", 1, D.rank["Spark"][0], [ghost], ghost)
    check("spark vs ghost (SHOCK R): ghost hurt, caster unharmed", ghost.hp < 50 and m.h.hp == 500, "%d %d" % (ghost.hp, m.h.hp))
    # Frost vs the Vampire (COLD I): no damage, no freeze
    sk = B.Mon(D, D.id("VAMPIRE"), 1)
    sk.x = 3
    m.h.ranks["Frost"] = 1
    m.cast("Frost", 1, D.rank["Frost"][0], [sk], sk)
    check("frost immune", sk.hp == sk.maxhp and not sk.hold)


def test_policy_sanity(D):
    # policies are the spec 4.3 table
    check("policy table", B.POLICIES["cautious"]["rest_hp"] == 0.70 and B.POLICIES["average"]["retreat"] == 0.25 and B.POLICIES["reckless"]["escape"] is None)


def win_rate(ov, hero, runs=500, pol="average", seed=os.environ.get("BSIM_SEED", "mono")):
    D = B.Data(ov)
    r = B.run_batch(D, hero, pol, runs, seed, 0)
    return r["wins"] / r["n"]


def progress(ov, hero, runs=500, pol="average", seed=os.environ.get("BSIM_SEED", "mono")):
    """(win rate, mean depth reached incl. the run's last level; a win counts 9)."""
    r = B.run_batch(B.Data(ov), hero, pol, runs, seed, 0)
    return r["wins"] / r["n"], sum(r["reached"][2:]) / r["n"] + 1 + r["wins"] / r["n"]


# Flat regen (+1 HP / FED_REGEN turns) vs a bigger HP pool is a real rule interaction (BSIM1): a longer rest-to-full burns food,
# so +HP can LOWER the win rate.  The monotone check therefore scales the regen period with max HP (12 * 30 / (30 + hp), ~ the
# mid-game pool) to isolate the HP effect itself.
def hp_param(hp):
    return {"HP_BONUS": hp, "FED_REGEN": max(1, round(12 * 30 / (30 + hp)))}


def test_monotone():
    """More HP never lowers the win rate when regen scales with the pool (Mage: paired seeds, tolerance ~2 sigma).  The
    Warrior has a structural wall (Ogre PHYS R + DEF: STALL), where extra HP turns deaths into stalls, so for him the
    monotone statistic is mean depth reached."""
    rates = [progress({"param": hp_param(hp)}, "M")[0] for hp in (0, 10, 30)]
    check("monotone HP M %s" % rates, rates[1] >= rates[0] - 0.045 and rates[2] >= rates[1] - 0.045 and rates[2] >= rates[0] - 0.045, str(rates))
    deep = [progress({"param": hp_param(hp)}, "W")[1] for hp in (0, 10, 30)]
    check("monotone HP W depth %s" % deep, deep[1] >= deep[0] - 0.1 and deep[2] >= deep[1] - 0.1 and deep[2] >= deep[0] - 0.1, str(deep))
    base = progress({}, "M")[0]
    strong = progress({"ab_rank": {"Firebolt": {str(r): {"bonus": 20} for r in (1, 2, 3)}}}, "M")[0]
    check("monotone firebolt dmg %.3f -> %.3f" % (base, strong), strong >= base - 0.045)
    d0 = progress({}, "W")[1]
    d1 = progress({"kx": {"OGRE": {"PHYS": "N"}}}, "W")[1]
    check("monotone ogre phys (W depth) %.2f -> %.2f" % (d0, d1), d1 >= d0 - 0.05)


def test_features(D):
    """SIM-UPD: image-read constants, GEAR1 gate, GEAR2 q / v, GEAR3 Enchant, FEAR-CAST, the Tome ending."""
    import items_model as IM
    check("gold xp image", D.params["GOLD_XP"] == [20, 30, 45, 60, 65, 80, 90, 0], str(D.params["GOLD_XP"]))
    check("tome consts", (D.params["TOME_HP"], D.params["TOME_AURA_R"]) == (5, 6))
    check("archmage hp image", D.k[D.id("ARCHMAGE")]["hp"] == 60)
    g = new_game(D, "M")
    g.equip_consider("Chain Mail", 2)                     # banned type for the Mage: never worn
    g.equip_consider("Helm", 0)
    check("gear1 gate equip", g.h.gear["a"] == "Robe" and g.h.gear["h"] is None and not g.h.gear_ban)
    g.h.gear["a"] = "Chain Mail"
    g.recalc()
    check("gear1 gate ban", g.h.gear_ban)
    g = new_game(D, "W")
    df0, mp0 = g.h.df, g.h.maxmp
    g.equip_consider("Chain Mail", 2)
    check("v = m + q on DEF", g.h.gear["a"] == "Chain Mail" and g.h.df == 2 + 2)
    g.h.scr["ench"] = 3
    g.use_enchant()
    check("enchant spent", g.h.scr["ench"] == 0 and sum(g.h.m.values()) == 3 and max(g.h.m.values()) <= 3, str(g.h.m))
    g = new_game(D, "M")
    g.h.fearT = 3
    g.D.params["FEAR_CAST"] = 1
    g.h.ranks["Spark"] = 1
    mp = g.h.mp
    front = B.Mon(D, D.id("RAT"), 1)
    front.x = 4
    check("fear-cast no spell", g.mage_act([front], front, [front]) == "skip" and g.h.mp == mp)
    g = new_game(D, "M")
    g.h.fearT = 0
    g.h.ranks["Spark"] = 1
    check("no fear casts", g.mage_act([front], front, [front]) == "act" and g.h.mp < mp)
    # the ending: a bare Warrior walks 6 aura cols and lands 5 melee hits (the last one ends the run): 6 + 5 - 1 = 10 aura turns
    g = new_game(D, "W")
    g.stats = {}
    g.h.hp = g.h.maxhp = 99
    g.h.daggers, g.h.arrows, g.h.bow = 0, 0, False
    g.depth = 8
    g.in_boss_dead = True
    g.sanctum()
    check("tome melee aura", g.stats.get("tome_aura") == 10, str(g.stats))
    g = new_game(D, "W")
    g.stats = {}
    g.h.hp = g.h.maxhp = 99
    g.h.bow, g.h.arrows = True, 5
    g.depth = 8
    g.in_boss_dead = True
    g.sanctum()
    check("tome arrows free", g.stats.get("tome_aura") == 0, str(g.stats))


def test_nm3(D0):
    """SIM1 (NEWMON3 flag): default off = 4-slot lists / no ember path; on = 8-slot lists, perch wake, ember, Wraith freeze, charm."""
    check("nm3 default off", not D0.nm3 and all(len(v) == 4 for v in D0.lp.values()))
    D = B.Data({"param": {"NEWMON3": 1}})
    check("nm3 lists 8 slots", all(len(v) == 8 for v in D.lp.values()))
    check("nm3 alias disjoint", all(not ({D.kid["FIRE_IMP"]} & set(D.lp[d]) and {D.kid["FROST_WRAITH"]} & set(D.lp[d])) for d in D.lp))
    check("nm3 imp D4/D6, wraith D5/D7/D8", [d for d in D.lp if D.kid["FIRE_IMP"] in D.lp[d]] == [4, 6]
          and [d for d in D.lp if D.kid["FROST_WRAITH"] in D.lp[d]] == [5, 7, 8])
    g = new_game(D, "W")
    g.depth = 5
    ga = B.Mon(D, D.kid["GARGOYLE"], 5)
    ga.x = 6
    g.turns = 1
    g.monster_turn(ga, [ga], [ga])
    check("perch waits at x 6", not ga.awake and ga.x == 6)
    ga.x = 3
    g.monster_turn(ga, [ga], [ga])
    check("perch wakes at x 3, spends the turn", ga.awake and ga.x == 3)
    gb = B.Mon(D, D.kid["GARGOYLE"], 5)
    gb.x = 9
    gb.hp -= 1
    g.monster_turn(gb, [gb], [gb])
    check("damage wakes", gb.awake)
    g = new_game(D, "W")
    g.depth = 4
    im = B.Mon(D, D.kid["FIRE_IMP"], 4)
    im.x = 4
    hp = g.h.hp
    g.monster_turn(im, [im], [im])
    check("imp ember 2..5 auto-hit, cooldown", 2 <= hp - g.h.hp <= 5 and im.cd == D.params["IMP_COOL"], str((hp - g.h.hp, im.cd)))
    g = new_game(D, "W")
    g.depth = 5
    g.h.hp = g.h.maxhp = 999
    g.D.params["WRAITH_FRZ_N"] = 1
    wr = B.Mon(D, D.kid["FROST_WRAITH"], 5)
    wr.x = 1
    wr.atk = 99
    g.mon_melee(wr, 1)
    check("wraith freeze on a landed touch: 1 on the Warrior (innate COLD R halves 2, T10a follow-up)",
          g.h.hold == 1 and g.h.holdkind == "frozen" and g.h.res[B.COLD] == 1, str(g.h.hold))
    gm = new_game(D, "M")
    gm.depth = 6
    gm.h.hp = gm.h.maxhp = 999
    gm.recalc()
    gm.mon_melee(wr, 1)
    check("wraith freeze 2 on the Mage (no innate COLD R)", gm.h.hold == 2 and gm.h.res[B.COLD] == 0, str(gm.h.hold))
    check("the Warrior's COLD hits halve (min 1)", g.hero_res(B.COLD, 7) == 3 and g.hero_res(B.COLD, 1) == 1
          and gm.hero_res(B.COLD, 7) == 7)
    g.h.hold = 0
    g.h.res[B.COLD] = 2
    hp = g.h.hp
    g.mon_melee(wr, 1)
    check("cold I: no damage, no freeze", g.h.hold == 0 and g.h.hp == hp)
    g = new_game(D, "M")
    g.h.charm = True
    g.depth = 5
    g.recalc()
    check("frost charm COLD R on Wraith depth", g.h.res[B.COLD] == 1)
    g.depth = 6
    g.recalc()
    check("frost charm not worn on D6", g.h.res[B.COLD] == 0)


def test_bal_knobs(D):
    """LARGER-D re-sweep knobs: defaults = today's game, bal_conf wiring, progress respawns fire and obey the live cap."""
    check("bal defaults", B.PARAMS["RESP_MODE"] == "time" and B.PARAMS["FED_REGEN_L"] is None and B.PARAMS["FED_REGEN_K"] is None)
    o = B.bal_conf("level:4", "prog:0.5:6", "1.5", {})["param"]
    check("bal_conf level/prog/dens", o["FED_REGEN_L"] == 4 and o["RESP_MODE"] == "progress" and o["RESP_P"] == 0.5
          and o["TRICKLE_MAX"] == 6 and o["MON_COUNT"][0] == 20 and o["ROOMS_LO"] == 12)
    o = B.bal_conf("maxhp:24", "progtime:1.0:8", "1.35", {})["param"]
    check("bal_conf maxhp/progtime", o["FED_REGEN_K"] == 24 and o["RESP_MODE"] == "progress+time" and o["MON_COUNT"][0] == 18)
    D2 = B.Data(B.bal_conf("flat", "prog:1.0:6", "1.5", {}))
    g = new_game(D2, "W", 3)
    g.build_level(1)
    order = list(range(len(g.rooms)))
    g.seen_t = {}
    base = sum(len(r) for r in g.rooms)
    for i in range(len(order)):
        g.progress_respawn(order, i)
        g.seen_t[order[i]] = -1000
        check("progress live cap", g.live_resp() <= 6)
    check("progress spawns some", sum(len(r) for r in g.rooms) + len(g.respawns_pending) > base)
    r = B.run_batch(D2, "M", "average", 10, "bk", 0)
    check("met counted", r["met"] > 10 * 5)


def test_pkg5(D0):
    """Package 5 knobs (balance_v2.md sec 6): defaults = package 4; option A/B/C override files take effect."""
    import json
    jl = lambda n: json.load(open(os.path.join(REPO, "tools", "balance_pkg5_%s.json" % n)))
    P0 = B.PARAMS
    check("pkg5 defaults", P0["TRK_MIN_DEPTH"] == 1 and P0["FOOD_N_D"] is None and P0["HEAL_EXTRA_D"] is None and P0["GOLD_DRAIN_DIV"] == 1)
    base = B.ld_preset(True)
    D4 = B.Data(base)
    ghost = lambda D: D.k[D.kid["GHOST"]]
    # BALANCE-PKG5 built: the asm kx_tab the sim reads already carries option A's Ghost 1 in 8
    check("pkg5 asm ghost confuse 1 in 8", ghost(D4)["efx"] == 5 and ghost(D4)["ech"] == 8, str((ghost(D4)["efx"], ghost(D4)["ech"])))
    DA = B.Data(B.merge(base, jl("A")))
    cnt = lambda D, d, n: D.lp[d].count(D.kid[n])
    check("A ghost confuse 1 in 8", ghost(DA)["ech"] == 8)
    check("A D3 mix", (cnt(D4, 3, "GHOST"), cnt(D4, 3, "GOBLIN"), cnt(DA, 3, "GHOST"), cnt(DA, 3, "GOBLIN")) == (3, 1, 2, 2))   # (lists: the json preset, not the asm)
    check("A D4 count", D4.params["MON_COUNT"][3] == 23 and DA.params["MON_COUNT"][3] == 24 and DA.params["MON_COUNT"][2] == 21)
    check("A keeps other depths", all(DA.lp[d] == D4.lp[d] for d in (1, 2, 4, 5, 6, 7, 8)))
    DB = B.Data(B.merge(base, jl("B")))
    for D, want in ((D4, True), (DB, False)):
        g = new_game(D, "W", 5)
        g.depth = 3
        g.visited_cleared = 1
        g.resp_count = 0
        g.in_boss_dead = False
        g.respawns_pending = []
        g.P = dict(g.P, TRICKLE_P=1.0)
        g.trickle(0, 4800)
        check("B trickle at D3 " + str(want), bool(g.respawns_pending) == want)
        g.depth, g.resp_count, g.respawns_pending = 4, 0, []
        g.trickle(0, 4800)
        check("B trickle at D4", bool(g.respawns_pending))
    DC = B.Data(B.merge(base, jl("C")))
    def floor(D, d):
        g = new_game(D, "W", 7)
        g.level_items(d)
        return g.floor
    for sd in range(20):
        g = new_game(DC, "W", sd)
        g.level_items(3)
        check("C D3 food 4-5", 4 <= len(g.floor["food"]) <= 5)
        g.level_items(2)
        check("C D2 food unchanged", 3 <= len(g.floor["food"]) <= 5)
    pots = lambda D: sum(floor(D, 3)["pots"].count("heal") for _ in range(1))
    g4, gc = new_game(D4, "W", 7), new_game(DC, "W", 7)
    g4.level_items(3)
    gc.level_items(3)
    check("C D3 extra heal", gc.floor["pots"].count("heal") >= g4.floor["pots"].count("heal") + 1 - 3 and len(gc.floor["pots"]) == len(g4.floor["pots"]) + 1,
          str((g4.floor["pots"], gc.floor["pots"])))
    # golden drain-bite: the Vampire Lord heals dm // 2 (base Vampire full)
    for D, div in ((D4, 1), (DC, 2)):
        g = new_game(D, "W", 3)
        g.depth = 3
        g.h.hp = g.h.maxhp
        for gold, want in ((True, 6 // div), (False, 6)):
            m = B.Mon(D, D.kid["VAMPIRE"], 3, gold=gold)
            m.hp = 1
            m.maxhp = 100
            m.x = 1
            g.rr = lambda: 0.0
            g.hit_hero_chance = lambda atk: 1.0
            D.k[D.kid["VAMPIRE"]].update(die=1, bonus=5, efx=0)
            g.h.df = 0
            g.h.res = [0] * 6
            g.dmg_hero = lambda dm, *a, **k: None
            g.hero_res = lambda ty, dm: 6
            g.mon_melee(m, 1)
            check("drain heal gold=%s div=%d" % (gold, div), m.hp - 1 == want, str(m.hp - 1))


def test_pkg5v2(D0):
    """Package 5 v2 knobs: PICKUP, BOOK_ORDER, FOOD_BURN (hunger); defaults = package 4."""
    check("v2 defaults", B.PARAMS["PICKUP"] == 1.0 and B.PARAMS["BOOK_ORDER"] == 0 and B.PARAMS["FOOD_BURN"] == 6)
    D = B.Data({"param": {"PICKUP": 0.0}})
    g = new_game(D, "W", 4)
    g.build_level(1)
    n0 = len(g.floor["pots"]) + len(g.floor["food"])
    g.pick_some(1.0)
    check("PICKUP 0 takes nothing", len(g.floor["pots"]) + len(g.floor["food"]) == n0 and n0 > 0)
    Do = B.Data({"param": {"BOOK_ORDER": 1}})
    g = new_game(Do, "M", 4)
    g.depth = 3
    for _ in range(3):
        g.read_book()
    check("BOOK_ORDER mage D3: Spark, Firebolt, Frost", [g.h.ranks[a] for a in B.ABIL[:5]] == [1, 1, 1, 0, 0], str(g.h.ranks))
    g.depth = 5
    for _ in range(2):
        g.read_book()
    check("BOOK_ORDER D5: Drain, Lightning", [g.h.ranks[a] for a in B.ABIL[:2]] == [1, 1] and g.h.ranks[B.ABIL[3]] == 1 and g.h.ranks[B.ABIL[4]] == 1)
    g.read_book()
    check("BOOK_ORDER falls back to rank-up/tome", sum(g.h.ranks[a] for a in B.ABIL[:5]) == 6 or getattr(g.h, "power", 0) == 1)
    g = new_game(Do, "W", 4)
    g.depth = 2
    g.h.ranks["Power"] = 1
    g.read_book()
    check("BOOK_ORDER W before D3: no Whirl", g.h.ranks["Whirl"] == 0)
    g.depth = 3
    g.read_book()
    check("BOOK_ORDER W D3: Whirl", g.h.ranks["Whirl"] == 1)
    Db = B.Data({"param": {"FOOD_BURN": 8}})
    g = new_game(Db, "W", 4)
    f0 = g.h.food
    g.t = 0
    g.adv(96)
    check("FOOD_BURN 8: 12 food per 96 turns", f0 - g.h.food == 12, str(f0 - g.h.food))


def test_pkg5v3(D0):
    """Package 5 v2 (balance_v2.md sec 7) knobs: defaults = package 4; scroll weights / guarantee, Fear turns, respawn cap, Firebolt-first, avoid_pro, stats."""
    P0 = B.PARAMS
    check("v3 defaults", P0["TELE_AMBUSH"] == 0.0 and P0["SCR_W"] is None and P0["SCR_GUAR_D2"] == 0 and P0["FEAR_SCR_T"] == 6
          and P0["RESPAWN_MAX_D4"] is None and P0["MAGE_FB_FIRST"] == 0)
    D = B.Data({"param": {"SCR_W": [8, 0, 0, 0], "SCR_N": [2, 2]}})
    g = new_game(D, "W", 3)
    g.build_level(1)
    check("SCR_W all Teleport", g.floor["scr"] == ["tele", "tele"], str(g.floor["scr"]))
    D = B.Data({"param": {"SCR_W": [0, 0, 0, 8], "SCR_N": [2, 2], "SCR_GUAR_D2": 1}})
    g = new_game(D, "W", 3)
    g.build_level(2)
    check("SCR_GUAR_D2 forces a Teleport", "tele" in g.floor["scr"] and len(g.floor["scr"]) == 2, str(g.floor["scr"]))
    g.build_level(3)
    check("SCR_GUAR_D2 only D2", "tele" not in g.floor["scr"])
    D = B.Data({"param": {"RESPAWN_MAX_D4": 8}})
    g = new_game(D, "W", 3)
    g.depth = 3
    c3 = g.rmax()
    g.depth = 4
    check("RESPAWN_MAX_D4", c3 == 6 and g.rmax() == 8)
    D = B.Data({"param": {"MAGE_FB_FIRST": 1}})
    g = new_game(D, "M", 3)
    g.depth = 1
    g.read_book()
    g.depth = 2
    g.read_book()
    check("MAGE_FB_FIRST: Spark then Firebolt", g.h.ranks["Spark"] == 1 and g.h.ranks["Firebolt"] == 1, str(g.h.ranks))
    pol = B.POLICIES["expert+charm_food+rest_fed-no_rest_full-no_jump_p+avoid_pro"]
    check("avoid_pro flag", pol.get("avoid_pro") == 1 and not pol.get("avoid") and pol.get("rest_fed") == 1 and pol["jump_p"] == 0.0, str(pol))
    r = B.run_batch(B.Data(B.ld_preset(True)), "M", "average", 12, "v3", 0)
    check("stats present", r["n"] == 12 and len(r["food3"]) > 0 and 0 <= r["hungry5"] <= 12 and "xs" in r)


def test_pkg5v4(D0):
    """Package 5 v3 knobs: per-depth monster HP / damage scales (round half up), boss exemption, defaults off."""
    P0 = B.PARAMS
    check("v4 defaults", P0["MON_HP_SCALE_D"] is None and P0["MON_DMG_SCALE_D"] is None and P0["MON_ATK_D"] is None and P0["MON_SCALE_NO_BOSS"] == 0)
    sc = [1.0, 1.0, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5]
    D = B.Data({"param": {"MON_HP_SCALE_D": sc, "MON_DMG_SCALE_D": sc, "MON_ATK_D": [0, 0, 1, 1, 1, 1, 1, 1]}})
    k = D.kid["ORC"]
    m1, m4 = B.Mon(D0, k, 4), B.Mon(D, k, 4)
    check("HP scale D4 round half up", m4.maxhp == int((m1.maxhp) * 1.5 + 0.5), str((m1.maxhp, m4.maxhp)))
    check("atk +1, dsc 1.5", m4.atk == m1.atk + 1 and m4.dsc == 1.5 and B.Mon(D, k, 2).maxhp == B.Mon(D0, k, 2).maxhp and B.Mon(D, k, 2).dsc == 1.0)
    Db = B.Data({"param": {"MON_HP_SCALE_D": sc, "MON_DMG_SCALE_D": sc, "MON_SCALE_NO_BOSS": 1}})
    og = D.kid["OGRE"]
    check("boss exempt", B.Mon(Db, og, 4).maxhp == B.Mon(D0, og, 4).maxhp and B.Mon(Db, og, 4).dsc == 1.0 and B.Mon(Db, k, 4).dsc == 1.5)


def test_pkg5final(D0):
    """Package 5 final: DROP_ALL_P (a kill drops one random food, tagged), eat_pop splits eaten food floor / drop."""
    check("drop default off", B.PARAMS["DROP_ALL_P"] is None)
    D = B.Data({"param": {"DROP_ALL_P": [1.0] * 8}})
    g = new_game(D, "W", 5)
    g.depth = 3
    n0 = len(g.h.bagfood)
    m = B.Mon(D, D.kid["SKELETON"], 3)
    g.kill(m)
    check("drop food on kill", len(g.h.bagfood) == n0 + 1 and isinstance(g.h.bagfood[-1], B.DropFood), str(g.h.bagfood))
    mr = B.Mon(D, D.kid["SKELETON"], 3, resp=True)
    g.kill(mr)
    check("no drop from a respawn", len(g.h.bagfood) == n0 + 1)
    g.h.bagfood = [B.DropFood(20), 10]
    g.eat_pop()
    g.eat_pop()
    check("eat_pop split", g.xc.get("eat_drop") == 10 or g.xc.get("eat_floor") == 10, str(g.xc))


def main():
    D = B.Data()
    for t in (test_pkg5final, test_pkg5v4, test_pkg5v3, test_pkg5v2, test_pkg5, test_bal_knobs, test_nm3, test_features, test_tables, test_determinism, test_warrior_goblin, test_mage_spark, test_damage_pipeline, test_policy_sanity):
        t(D)
    test_monotone()
    if FAILS:
        print("balance_sim_selftest: FAIL")
        for f in FAILS:
            print("  ", f)
        return 1
    print("balance_sim_selftest: PASS (tables+overrides, determinism, W/M single-fight DP cases, damage pipeline, monotonicity)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
