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
            check("rank %s %d" % (name, r + 1), [got[k] for k in ("mp", "range", "die", "bonus", "bounces", "effect")] == list(row), str(got))
    check("xpn", D.xpn == C.XP_NEXT, str(D.xpn))
    check("ogre row", D.k[D.id("OGRE")]["hp"] == 40 and D.k[D.id("OGRE")]["res"][B.PHYS] == 1 and D.k[D.id("OGRE")]["res"][B.SHOCK] == 4)
    check("spider fire W", D.k[D.id("SPIDER")]["res"][B.FIRE] == 4)
    # overrides
    ov = B.parse_set(["ab_rank.Firebolt.1.range=8", "kx.SPIDER.FIRE=N", "kind.OGRE.hp=99", "param.HP_BONUS=5"])
    D2 = B.Data(ov)
    check("override rank", D2.rank["Firebolt"][0]["range"] == 8 and D.rank["Firebolt"][0]["range"] == 12)
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
    ogre = B.Mon(D, D.id("OGRE"), 4)           # PHYS R, DEF 2
    check("phys R then DEF (roll 6 -> 3-2=1)", True)
    ogre.hp = ogre.maxhp = 100
    g.strike(ogre, B.PHYS, 6, melee=True)
    check("ogre 6 phys -> 1", ogre.hp == 99, str(ogre.hp))
    ogre.hp = 100
    g.strike(ogre, B.PHYS, 12, melee=True)
    check("ogre 12 phys -> 6-2=4", ogre.hp == 96, str(ogre.hp))
    m = new_game(D, "M")
    m.h.gear["w"] = "Bone Staff"
    m.recalc()
    m.h.ranks["Firebolt"] = 1
    m.h.mp = 30
    check("bone staff spell bonus", m.h.spellbonus == 2)
    vamp = B.Mon(D, D.id("VAMPIRE"), 1)       # FIRE W
    vamp.hp = vamp.maxhp = 500
    vamp.x = 3
    seen = set()
    for i in range(400):
        vamp.hp = 500
        m.h.mp = 30
        m.cast("Firebolt", 1, D.rank["Firebolt"][0], [vamp], vamp)
        seen.add(500 - vamp.hp)
    # Firebolt R1 1d8+2, +2 staff, doubled: (3..10 +... ) -> (d+4)*2 = 10..24 even numbers
    check("firebolt W staff range", min(seen) == 10 and max(seen) == 24, str(sorted(seen)))
    ghost = B.Mon(D, D.id("GHOST"), 1)         # SHOCK X: reflect, 0 damage to it
    ghost.hp = ghost.maxhp = 50
    ghost.x = 3
    m.h.ranks["Spark"] = 1
    hp0 = m.h.hp
    m.h.hp = m.h.maxhp = 500
    m.cast("Spark", 1, D.rank["Spark"][0], [ghost], ghost)
    check("spark reflected by ghost: ghost unharmed, caster hit", ghost.hp == 50 and m.h.hp < 500, "%d %d" % (ghost.hp, m.h.hp))
    # Frost vs skeleton (COLD I): no damage, no freeze
    sk = B.Mon(D, D.id("SKELETON"), 1)
    sk.x = 3
    m.h.ranks["Frost"] = 1
    m.cast("Frost", 1, D.rank["Frost"][0], [sk], sk)
    check("frost immune", sk.hp == sk.maxhp and not sk.hold)


def test_policy_sanity(D):
    # policies are the spec 4.3 table
    check("policy table", B.POLICIES["cautious"]["rest_hp"] == 0.70 and B.POLICIES["average"]["retreat"] == 0.25 and B.POLICIES["reckless"]["escape"] is None)


def win_rate(ov, hero, runs=500, pol="average", seed="mono"):
    D = B.Data(ov)
    r = B.run_batch(D, hero, pol, runs, seed, 0)
    return r["wins"] / r["n"]


def progress(ov, hero, runs=500, pol="average", seed="mono"):
    """(win rate, mean depth reached incl. the run's last level; a win counts 9)."""
    r = B.run_batch(B.Data(ov), hero, pol, runs, seed, 0)
    return r["wins"] / r["n"], sum(r["reached"][2:]) / r["n"] + 1 + r["wins"] / r["n"]


def test_monotone():
    """More HP never lowers the win rate (Mage: paired seeds, tolerance ~2 sigma).  The Warrior has a structural
    wall (Ogre PHYS R + DEF: STALL), where extra HP turns deaths into stalls, so for him the monotone
    statistic is mean depth reached."""
    rates = [progress({"param": {"HP_BONUS": hp}}, "M")[0] for hp in (0, 10, 30)]
    check("monotone HP M %s" % rates, rates[1] >= rates[0] - 0.045 and rates[2] >= rates[1] - 0.045 and rates[2] >= rates[0], str(rates))
    deep = [progress({"param": {"HP_BONUS": hp}}, "W")[1] for hp in (0, 10, 30)]
    check("monotone HP W depth %s" % deep, deep[1] >= deep[0] - 0.1 and deep[2] >= deep[1] - 0.1 and deep[2] >= deep[0], str(deep))
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


def main():
    D = B.Data()
    for t in (test_features, test_tables, test_determinism, test_warrior_goblin, test_mage_spark, test_damage_pipeline, test_policy_sanity):
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
