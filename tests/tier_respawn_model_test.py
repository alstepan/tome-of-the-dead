#!/usr/bin/env python3
"""3F-T4 reference-model tests (Python only; no emulator): the §9.6 tier roll, escort /
golden boss / Sanctum in tools/levelgen.py, and the §9.5 respawn model.
Run: python3 tests/tier_respawn_model_test.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import levelgen as G                                    # noqa: E402
import respawn_model as RM                              # noqa: E402

n_ok = 0


def check(cond, msg):
    global n_ok
    if not cond:
        print("FAIL", msg)
        sys.exit(1)
    n_ok += 1


# ---- T1: odds (§9.6 table, rev 5) ----------------------------------------------
check(G.tier_odds(1, 1) == (24, 0), "D1 LVL1 = base, no tier 3")
check(G.tier_odds(4, 4) == (72, 16), "D4 LVL4 = bases")
check(G.tier_odds(4, 6) == (104, 32) and G.tier_odds(4, 9) == (104, 32), "delta clamps at +2")
check(G.tier_odds(4, 2) == (40, 0) and G.tier_odds(4, 0) == (40, 0), "delta clamps at -2; T3 floors at 0")
check(G.tier_odds(8, 10) == (128, 64), "D8 +2")
check(G.tier_odds(1, -1) == (0, 0), "T2 floors at 0")
check(all(G.tier_odds(d, l)[1] == 0 for d in (1, 2, 3) for l in range(1, 12)), "no tier 3 below D4")
check(all(G.tier_odds(d, l)[0] <= G.T2_CAP and G.tier_odds(d, l)[1] <= G.T3_CAP
          for d in range(1, 9) for l in range(-2, 14)), "caps")

# ---- T2: the roll (boundaries) ---------------------------------------------------
t2, t3 = G.tier_odds(5, 5)
check((t2, t3) == (80, 24), "D5 base odds")
check(G.tier_pick("K_SKELETON", t3 - 1, 5, 5) == "K_SKEL_KNIGHT", "r < T3 -> tier 3")
check(G.tier_pick("K_SKELETON", t3, 5, 5) == "K_SKEL_GUARD", "r = T3 -> tier 2")
check(G.tier_pick("K_SKELETON", t3 + t2 - 1, 5, 5) == "K_SKEL_GUARD", "r < T3+T2 -> tier 2")
check(G.tier_pick("K_SKELETON", t3 + t2, 5, 5) == "K_SKELETON", "r = T3+T2 -> base")
check(G.tier_pick("K_BAT", 0, 5, 5) == "K_SCREECH", "kind without tier 3: r < T3 -> tier 2")
check(G.tier_pick("K_RAT", 0, 5, 5) == "K_RABBIT_RAT" and G.tier_pick("K_RAT", t3, 5, 5) == "K_GIANT_RAT",
      "Rat: Rabbit Rat is tier 3, Giant Rat tier 2")
for k in ("K_SLIME", "K_VAMPIRE", "K_MUMMY", "K_OGRE", "K_DKNIGHT", "K_ARCHMAGE"):
    check(G.tier_pick(k, 0, 8, 8) == k, f"{k} is never tiered")
rng = G.Rng(77, 3)
x0 = rng.x
check(G.tier_roll(rng, "K_SLIME", 3, 3) == "K_SLIME" and rng.x == x0, "untiered kind: no rng step")
G.tier_roll(rng, "K_RAT", 3, 3)
check(rng.calls == 1, "tiered kind: exactly one step")
for d, l in ((2, 2), (4, 4), (7, 9), (8, 1)):          # exact distribution over r = 0..255
    cnt = {}
    for r in range(256):
        k = G.tier_pick("K_ORC" if d >= 4 else "K_GOBLIN", r, d, l)
        cnt[k] = cnt.get(k, 0) + 1
    a, b = G.tier_odds(d, l)
    if d < 4:
        check(cnt.get("K_SLINGER", 0) == min(256, a + b), f"D{d} L{l} tier-2 count")
    else:
        check(cnt.get("K_ORC_BOUNCER", 0) == b and cnt.get("K_ORC_BERSERK", 0) == min(256 - b, a),
              f"D{d} L{l} counts")
check(len(G.K3_BY_ID) == len(G.KROWS) == 27 and len(G.TIERS) == 9, "15 monster rows + 12 tiers")
check(sorted(G.K3_BY_ID) == list(range(3, 30)), "provisional ids unique, 3..29")
check(G.k3_weight(G.KROWS["K_SLINGER"][0]) == 4 and G.k3_weight(G.KROWS["K_GOBLIN"][0]) == 3, "Slinger weight 3+1")


# ---- T3: population with tiers, escort, golden ----------------------------------
def first_entries(depth, seed, lvl):
    b = G.generate(depth, seed, f3=True)
    lp = G.lp_budget(b, lvl, True)
    out = {}
    for r in range(9):
        if b[G.OFF_DESC + r * 16] & 1:
            lp2, placed = G.lp_enter(b, lp, r, 0, 14, 3, True)
            out[r] = (placed, lp2)
    return b, out


tiered = {1: 0, 10: 0}
for depth in (5, 6, 7, 8):
    for seed in range(1, 120):
        for lvl in (1, 10):
            b, out = first_entries(depth, seed, lvl)
            lair = b[G.H["LVL_LAIR"]]
            for r, (placed, lp2) in out.items():
                check(lp2[G.lp_off("LP_DISCARD")] == 0, "LP_DISCARD 0")
                for i, (kb, hp, *_) in enumerate(placed):
                    if r == lair:
                        if kb == G.k3_boss(depth):
                            check(hp == G.k3_hp(kb, depth), "boss hp")
                        else:
                            check(kb & G.LEK_GOLD == 0 and kb < 18, "escort: base tier, never golden")
                    else:
                        tiered[lvl] += kb >= 18
                        check(kb & ~G.LEK_ROW_MASK == 0, "no flags on a plain resident")
check(tiered[10] > tiered[1] * 1.5, f"high LVL spawns more tiers ({tiered})")
check(tiered[1] > 0, "tiers appear at LVL 1 on D5+")
for depth in (1, 2, 3):
    for seed in range(1, 60):
        b, out = first_entries(depth, seed, 12)
        check(all((kb & 31) < 18 or G.KROWS[G.K3_BY_ID[kb & 31]][6] == 2
                  for r, (p, _) in out.items() for kb, *_ in p), "D1-3: tier 2 at most")
for depth in range(1, 9):                                # golden: D1,2,3,5,6; unique: D4,7,8
    kb = G.k3_boss(depth)
    check(bool(kb & G.LEK_GOLD) == (depth in (1, 2, 3, 5, 6)), f"D{depth} golden flag")
    base = G.KROWS[G.BOSS3[depth][0]][1] + depth - 1
    check(G.k3_hp(kb, depth) == (2 * base + 6 if kb & G.LEK_GOLD else base), f"D{depth} boss hp")
    check(G.k3_weight(kb) == G.KROWS[G.BOSS3[depth][0]][4] + (1 if kb & G.LEK_GOLD else 0), "golden weight +1")
b = G.generate(3, 5)
lp = G.lp_budget(b, 5)
check(lp[G.lp_off("LP_KINDS"):G.lp_off("LP_KINDS") + 4] == bytes(G.D[k] for k in G.LP_TAB[3][0]),
      "f3 off: stand-in ids")

# ---- T4: Sanctum leaf + sealed edge ------------------------------------------------
for seed in range(1, 300):
    b = G.generate(8, seed, f3=True)
    sc, lair = b[G.H["LVL_SANCTUM"]], b[G.H["LVL_LAIR"]]
    check(lair == 7 and sc in (6, 8), "D8 lair 7, Sanctum 6/8")
    e = b[G.OFF_EDGE + G.hedge(min(7, sc))]
    check(e == G.D["EG_LINK"] | G.D["EG_DOOR"] | G.D["EG_SEAL"], "sealed edge")
    check(not b[G.H["LVL_FLAGS"]] & G.D["LF_GRATE_OPEN"], "grate closed")
    check(b[G.OFF_DESC + sc * 16 + G.D["RD_FLAGS"]] & G.D["RDF_SANCTUM"], "Sanctum flag")
    check(b == G.generate(8, seed, f3=True), "deterministic")
    check(G.generate(7, seed, f3=True)[G.H["LVL_SANCTUM"]] == G.D["ROOM_NONE"], "no Sanctum off D8")


# ---- T5: respawn model -----------------------------------------------------------------
def level(depth=5, lvl=5, visited=(0, 1, 2, 3, 4, 5, 6, 7, 8), lair=7, items=None):
    recs = [{"visited": r in visited, "ents": []} for r in range(9)]
    return RM.Level(depth, lvl, list(G.LP_TAB[depth][0]), lair, recs, items)


def run(lv, seed, turns, hero=(0, 1)):
    rng = G.Rng(seed, lv.depth)
    lv.prev, lv.cur = hero
    got = []
    for t in range(1, turns + 1):
        g = RM.trickle_check(lv, t, rng)
        if g:
            got.append((t, g))
    return got


lv = level()
check(RM.trickle_check(lv, 47, G.Rng(1, 5)) is None and RM.trickle_check(lv, 49, G.Rng(1, 5)) is None, "period")
r0 = G.Rng(3, 5)
x0 = r0.x
lv.prev, lv.cur = 0, 1
RM.trickle_check(lv, 47, r0)
check(r0.x == x0, "off-period turn draws nothing")
hits = checks = 0                                        # ~96/256 per check
rng = G.Rng(11, 5)
for k in range(1, 3000):
    lv = level()
    lv.prev, lv.cur = 0, 1
    checks += 1
    hits += RM.trickle_check(lv, 48 * k, rng) is not None
check(abs(hits / checks - 96 / 256) < 0.04, f"chance ~ 96/256 ({hits}/{checks})")
check(run(level(), 5, 6000) == run(level(), 5, 6000) != [], "same seed -> same spawns")
lv = level()
got = run(lv, 9, 100000)
check(len(got) == RM.RESPAWN_MAX == lv.resp, "capped at RESPAWN_MAX = 6")
for seed in range(1, 40):                                # exclusions
    lv = level(visited=(0, 1, 2, 3, 4, 5, 6, 7), lair=7)         # room 8 FRESH
    lv.recs[3]["ents"] = [(G.KROWS["K_RAT"][0], 3)] * 4          # full by count
    for t, (room, kb, hp) in run(lv, seed, 20000, hero=(2, 5)):
        check(room not in (5, 2, 7, 8, 3), f"excluded room {room}")
        check(kb & G.LEK_RESPAWN and (kb & G.LEK_ROW_MASK) not in (15, 16, 17), "F_RESPAWN, never a boss")
        check(lv.sigma(room) <= RM.ROOM_CAP_SIGMA and len(lv.recs[room]["ents"]) <= 4, "cap held")
        check(hp == G.k3_hp(kb, 5) and not kb & G.LEK_GOLD, "full hp, not golden")
        key = G.K3_BY_ID[kb & 31]
        check(key in lv.kinds or G.KROWS[key][5] in lv.kinds, "kind (or its tier) from the level's list")
lv = level(visited=())
lv.prev, lv.cur = 0, 1
r0 = G.Rng(4, 5)
x0 = r0.x
check(RM.trickle_check(lv, 48, r0) is None and r0.x == x0, "no eligible room: skip without a draw")
lv = level()
lv.boss_dead = True
check(run(lv, 2, 20000) == [], "no spawn after the boss dies")
lv = level(visited=(2,), lair=7)
lv.recs[2]["ents"] = [(G.KROWS["K_NECRO"][0], 12), (G.KROWS["K_ARCHER"][0], 8)]      # sigma 12
check(run(lv, 6, 20000, hero=(0, 1)) == [], "sigma-12 room refuses")
pick = {2: 0, 3: 0}                                      # item weights 7 vs 1
for seed in range(1, 400):
    lv = level(visited=(2, 3), items=[0, 0, 3, 0, 0, 0, 0, 0, 0])
    lv.prev, lv.cur = 0, 1
    g = RM.trickle_check(lv, 48, G.Rng(seed * 7, 5))
    if g:
        pick[g[0]] += 1
check(pick[2] > 3 * pick[3] > 0, f"item weight 7 vs 1 ({pick})")
check(RM.room_weight(0) == 1 and RM.room_weight(1) == 3 and RM.room_weight(3) == 7 and RM.room_weight(9) == 7,
      "room weights")
check(RM.respawn_xp(7) == 3 and RM.respawn_xp(1) == 1 and RM.respawn_xp(2) == 1, "half XP, min 1")
check(RM.drops_nothing(G.LEK_RESPAWN | 3) and not RM.drops_nothing(3), "F_RESPAWN cancels drops")
lv = level()
lv.enter(1)
lv.enter(2)
lv.enter(2)
check((lv.prev, lv.cur) == (1, 2), "prev_room updated on a room change only")

print(f"tier/respawn models: {n_ok} checks pass")
