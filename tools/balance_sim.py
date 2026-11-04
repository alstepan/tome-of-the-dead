#!/usr/bin/env python3
"""balance_sim.py - BAL-1b headless Monte Carlo balance simulator (docs/design/bal1_spells.md sec 4).

WHAT IS MODELLED
  * Whole runs D1..D8 for a Warrior (W) or Mage (M) under a bot policy (cautious / average / reckless,
    spec 4.3).  Win = Archmage dead AND Tome destroyed (GS_WIN).  Loss = HP 0 or a STALL (the bot
    cannot damage what blocks the way; counted as a loss, reported under killer "STALL").
  * Numbers come from the BUILT IMAGE (build/wazhack.tap + .sna + .sym, via tests/combat_tables.load):
    kind_tab (hp/atk/eva/die/bonus/period/weight/flags), kx_tab (resistances, immunity mask, KXP, DEF,
    on-hit effect), ab_rank (7 abilities x 3 ranks), ab_ammo, xpn_tab.  Ranged-monster rows come from
    tools/ranged_model.ROWS (+ GOLD_ROWS: BOSS-RANGED, the golden King / Queen only), books from tests/book_model.book_read, item pools/counts/trap counts from
    tools/items_model constants, trickle constants from tools/respawn_model.  Every game.md rule that
    is not in a table is a named constant in the RULES block below (with its section).  Also from the repo: golden-boss XP
    (src/data7.asm bxp_d + KXP_*), Archmage hp (kind_tab), TOME_MAX / TOME_AURA_R / TOME_REACH (.sym), item type ids, the per-depth
    q table, class gear pools, the GEAR1 gate and the GEAR3 Enchant target pick (tools/items_model.py).
  * Any table cell / rule constant can be overridden (JSON file or --set), so sweeps need no code edits.
  * Level: 6..9 rooms (D8: + Sanctum), monsters split per sec 9.4.1 (quota, ROOM_MAX, BFS-distance
    weights are a random 1..4 stand-in), kinds from LP_KINDS, tier roll sec 9.6 (T2/T3_BASE, LVL delta),
    Sigma reservation fit sec 9.4.3, golden bosses / Ogre / DK / Archmage (sec 9.9 cadence), lair last,
    boss hp persists across retreats, respawn trickle (every 48 turns, 96/256, <=6/level, sec 9.5).
  * Encounter geometry is 1-D (sec 4.2): monsters at gaps GAP_LO..GAP_HI, wall WALL ahead, BEHIND room
    for kiting, P_LINE same-storey probability else T_CLIMB turns out of line.  Monsters queue (no
    passing).  Melee F1 (d20+atk >= 10+eva), DEF, resist, speed periods, vampire bat form, parry,
    rage, Ogre SLAM, ranged cooldown N, Bone Caller summon, Archmage 7-spell cycle + blink + summon.
    Ranged (BOSS-RANGED): fires at gap < r (param.RANGED_LT), golden + 1 dmg (GOLD_RDMG), PHYS rows d20 + DEF,
    the Spider Queen's spit always POISON + 12 (cap 30, Silk Cloak immune); every shooter walks in between
    shots (right for the King / Queen: RWF_WALK; the other shooters' HOLD-in-range rule is not modelled).
  * Spells: sec 6 projectile rules on the line: first body, pierce once per pass, wall bounces,
    reflect (X) at the front col, caster valid after any reversal, loop guard 4, Firebolt burst +-1 col
    (caster at point-blank, rank 3 spares), staff bonus before resist, auto-downcast, Drain heal,
    Frost freeze (self-freeze 1), Spark confusion, boss halving, immunity masks.
  * Statuses: HOLD (frozen/stun/sleep), confuse, fear, poison (cap 30, -1 HP/4 turns, never below 1),
    WEAK (Mummy curse), hunger stages (FED regen, HUNGRY atk-1, WEAK atk-2 eva-1), food/potion/scroll/gear
    pickups per level (potions >=1 Heal, food 3-4, scrolls 1-2, gear 1-2, books, uniques), equip-best (GEAR1 gates; v = m + q),
    per-instance q (GEAR2), random Enchant (GEAR3: worn weapon/armour/helmet m < +3, else bag), class books with pity, level-ups
    and +atk/+eva steps, MP regen (period, MAXMP div 16).  FEAR-CAST (param.FEAR_CAST, default 1): a FEARed hero cannot cast
    (Mage: no spell, no staff melee either - fear_chk gates every melee-reach action) and the Warrior cannot melee / Power Strike /
    Whirlwind; heals, Cure, thrown daggers and arrows stay.  FEAR sources = the kx on-hit efx 4 kinds (table) + the Necromancer /
    Bone Caller bolt rider (1/3, FEAR 3) + the Archmage Death Bolt (85/256, FEAR 3).
  * TRAP2: the level's traps (items_model.TRAP_COUNT, type pool by depth) sit in distinct rooms (start / fight rooms / lair);
    every crossing (entering the room, each retreat-return, TRAP_PATH_P per trap per transit) fires with TRAP_HIT_P; no trap is
    ever removed.  ALARM waves only while the boss lives and LP_RESPAWNS < TRICKLE_MAX (a wave counts 1).
  * D8 ending (game.md 1.3 / WIN2): Archmage dead -> seal breaks -> walk to the Sanctum -> Tome TOME_MAX hits (melee, Power Strike,
    Whirlwind, spells, arrows, daggers: one hit per attack, resist ignored, never missed); untyped aura 1 HP per turn end while the
    hero is within TOME_AURA_R cols (gap < 6), so attacks released from gap >= 6 (range >= 7) are free; Tome gone -> the exit gate
    opens -> walk out -> win.  TOME_MAX / TOME_AURA_R / TOME_REACH come from the .sym.

WHAT IS NOT MODELLED (-> emulator spot-check, sec 4.5)
  two storeys, ladders, pits, jumps, squeeze/wedges; door-closing tactics (flyers blocked); real AI
  pathing; line-of-fire from real layouts; trap placement (traps sit in rooms; TELEPORT is a flat delay, no pits/falls;
  no jumping over a known plate); banking bugs; input skill; RNG-stream interleave; monsters on both
  sides of the hero (so Whirlwind rarely has 2 targets); weapon wear/notch/ACID; hunger faints; Rabbit Rat
  breeding is modelled, idle waves are not; floor items are collected on room clear (no item hunt);
  real level geometry / items_model.gen_level_items placement (counts and pools only, not cells).
  Results are distributions for TUNING DELTAS, not absolute truth: calibrate GAP/P_LINE/T_CLIMB per 4.5.

ASSUMPTIONS THE SPEC LEFT OPEN (all overridable or documented; sensitivity-test them before trusting a delta)
  * Damage order is the BUILT one (combat3.asm deal_hit): roll -> R halves (min 1) / W doubles -> minus DEF (PHYS only,
    min 1).  Power Strike multiplies the roll first.  Whirlwind +dmg is added to the roll first.
  * Golden-boss XP = bxp_d + KXP (game.md 4.1; param.GOLD_XP="image" default, null = base-kind KXP only, a list = explicit) and
    Archmage hp from kind_tab (60, +7 depth scaling = 67 at D8; param.ARCHMAGE_HP overrides).
  * JUMP (param.JUMP=1, 2.4): the bot jumps AWAY from an adjacent melee front monster (+6 cols, 1 turn, 2 FOOD, never two turns
    in a row, not when Weak/held, needs 6 free cols behind from the 1-D BEHIND budget; cautious always, average 1 in 2, reckless
    never; the Mage needs MP for a spell, the Warrior >= 2 daggers/arrows).  NOT modelled: jumping over low bodies, over pits,
    landing in a pit, the swept box / ledge geometry, climbing as the alternative, the real room depth behind the hero.
  * Hero-side knobs for design sweeps (CODE changes in the game, flagged): param.W_HP0/W_MP0/W_LVL_HP/W_LVL_MP, M_*, MAGE_REGEN,
    PS_R=1 (Power Strike ignores PHYS R), W_START_POWER, and gear.<Name>.<field> (weapon/armour table).
  * Bot: cautious/average rest to FULL before a boss lair (the boss never regenerates); retreat from a boss is free against
    melee (boss never follows; escorts within 2 cols follow and are fought); Mage casts the best dmg-per-MP spell (resist-aware),
    skips a bouncing spell that could come back unless HP >= 90 % and the self-hit cannot kill, skips piercing Lightning with a
    reflector in line; staff when MP < the cheapest rank-1 cost.  Warrior throws daggers/arrows at gap 3..range.
  * Floor loot is collected room by room (no hunting); gear equip by a fixed score (v = m + q), never a type the GEAR1 gate would ban; cursed gear does not exist (3E rev 6).
  * STALL = 220 turns in a fight or > 12 / 40 retreat cycles: the bot gives up, run counted as a loss.

USAGE
  python3 tools/balance_sim.py --hero W|M|both --policy cautious|average|reckless|all --runs 10000 \\
      --seed 1 [--overrides tools/balance_optionA.json] [--set key=val ...] [--json out.json] [--csv out.csv]
  python3 tools/balance_sim.py --compare tools/balance_optionA.json   # baseline vs override, full report
  override keys: ab_rank.Firebolt.1.range=8 | kx.Spider.FIRE=N | kind.Archmage.hp=60 | param.MAGE_REGEN=7
"""
import argparse
import json
import math
import os
import random
import re
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tests"))
sys.path.insert(0, os.path.join(REPO, "tools"))

# ----------------------------------------------------------------------------------------------
# RULES: tunable constants (every one overridable as param.NAME).  Section = game.md.
# ----------------------------------------------------------------------------------------------
PARAMS = {
    "GAP_LO": 3, "GAP_HI": 20,          # 4.2 spec: monster gaps uniform 3..20
    "WALL_MAX": 28, "BEHIND_MAX": 10,   # 4.2 spec
    "P_LINE": 0.7, "T_CLIMB_LO": 4, "T_CLIMB_HI": 8,
    "TRANSIT_LO": 20, "TRANSIT_HI": 60,  # 4.2 between rooms
    "MAGE_REGEN": 6, "WARRIOR_REGEN": 8,  # 4.0 periods
    "FED_REGEN": 12,                    # 7: +1 HP per 12 turns when FOOD >= 50
    "HEAL_AMT": 12, "MANA_AMT": 8, "CURE_HP": 4,  # 8 consumables
    "PITY_N": 2,                        # 5
    "ARCHMAGE_HP": None,                # null = the image's kind_tab row (60; 67 at D8 after the depth term)
    "T2_BASE": [24, 48, 64, 72, 80, 88, 96, 96], "T3_BASE": [0, 0, 0, 16, 24, 32, 40, 48],  # 9.6
    "TIER_SHIFT2": 16, "TIER_SHIFT3": 8, "TIER_DELTA_MAX": 2, "T2_CAP": 160, "T3_CAP": 80, "TIER3_MIN_DEPTH": 4,
    "ROOM_MAX": [3, 3, 3, 3, 3, 3, 3, 3],  # 9.4.1
    "MON_COUNT": [13, 14, 14, 15, 16, 15, 15, 12],  # 9.4 MORE-MON medium (D8: 11 + Archmage)
    "ROOMS_LO": 6, "ROOMS_HI": 9,       # 9.4.1 |R| >= 5 plus start+lair (+Sanctum on D8)
    "DAGGER_DMG": 4, "DAGGER_BONUS": 2, "BOW_DMG": 6, "BOW_BONUS": 1,  # 6.3 (also ab_ammo)
    "TRAP_HIT_P": 0.5, "TRAP_DMG": 3,   # 1.5 flat stand-in: expected 2-4 HP / level
    "TRICKLE_PERIOD": 48, "TRICKLE_P": 96 / 256, "TRICKLE_MAX": 6, "TRICKLE_MEET_P": 0.4,  # 9.5
    "FIGHT_STALL": 220,                 # turns in one fight before the bot gives up (STALL)
    "REST_MAX": 500,
    "FOOD_START": 80, "FOOD_BURN": 6,   # 7
    "EAT_AT": 24,                       # 4.3: eat at HUNGRY (<25)
    "QUEEN_POISON": 36, "SLAM_EVERY": 3,
    "ESCORT_FOLLOW_GAP": 2,
    "HP_BONUS": 0,                      # sweep/test knob: flat extra max HP for both heroes
    "NO_MIRROR_FEAR_P": 85 / 256,
    # XP of a golden boss: null = what the build does (base-kind KXP: combat3.asm reads kx_tab only);
    # game.md 4.1 says King 20 / Queen 30 / Lord 45 / Pharaoh 65 / H.Necro 80 -> set this list to test it
    "GOLD_XP": "image",                 # "image" = bxp_d + KXP_<base> (src/data7.asm + .sym); null = base-kind KXP only; or a list
    "JUMP": 1,                          # 2.4: jump-then-cast / jump-to-range bot tactic (0 = off)
    "JUMP_COLS": 6, "JUMP_FOOD": 2,     # D = 6 cols, 1 turn + 2 FOOD, never two turns in a row
    "W_HP0": 24, "W_MP0": 6, "W_LVL_HP": 4, "W_LVL_MP": 1,     # 4 / 4.1 (hero_st_init / xp7 immediates = CODE)
    "M_HP0": 16, "M_MP0": 10, "M_LVL_HP": 3, "M_LVL_MP": 2,
    "PS_R": 0,                          # 1 = Power Strike ignores PHYS R (CODE flag; BAL-1d W1 option)
    "BC_LIVE": None,                    # Bone Caller: max live summon-made bodies in the room (null = .sym BC_LIVE = 1; the sim used to have no cap at all)
    "AM_LIVE": None, "AM_SUM_CD": None,   # Archmage summon: max live Skeletons / cooldown (null = .sym AM_LIVE 1 / AM_SUM_CD 6; exempt from the room cap)
    "TOME_HP": None, "TOME_AURA_R": None,   # null = .sym TOME_MAX (5) / TOME_AURA_R (6); aura 1 HP untyped per turn end, gap < R
    "EXIT_LO": 10, "EXIT_HI": 30,       # WIN2: turns Sanctum -> exit gate (the exit col sits in the lair next to the Sanctum)
    "NECRO_FEAR_N": 3, "NECRO_FEAR_T": 3, "ARCH_FEAR_N": 3,   # rd_tab FEAR3_1IN3 (chance 1 in N, turns) for Necromancer / Bone Caller / Archmage Death Bolt
    "FEAR_CAST": 1,                     # FEAR-CAST (planned rule): a FEARed hero cannot cast (Mage also not melee); 0 = old rule
    "TRAP_PATH_P": 0.3,                 # TRAP2: P(a transit crosses a given known plate); fires with TRAP_HIT_P
    "W_START_POWER": 0,                 # Warrior starts with Power Strike at this rank after the D1 book (CODE)
    # BOSS-RANGED (2026-11-02): 1 = what the build does; 0 / 0 / 0 reproduces FINAL B
    "RANGED_LT": 1,                     # a shooter fires at gap < r (ranged6.asm rg_line); 0 = the old sim's gap <= r
    "GOLD_RDMG": 1,                     # a golden shooter's ranged dmg + 1 (rg_shoot, §9.7 R1: the High Necromancer too)
    "BOSS_RANGED": 1,                   # the golden Goblin King daggers / Spider Queen spit (ranged_model.GOLD_ROWS)
}
POLICIES = {   # 4.3: rest_hp, rest_mp(Mage), heal, escape, kite_p, boss_retreat (fractions; None = never)
    "cautious": dict(rest_hp=0.70, rest_mp=0.70, heal=0.35, escape=0.25, kite=1.0, retreat=0.40),
    "average":  dict(rest_hp=0.50, rest_mp=0.50, heal=0.25, escape=0.15, kite=0.5, retreat=0.25),
    "reckless": dict(rest_hp=0.25, rest_mp=0.25, heal=0.15, escape=None, kite=0.0, retreat=None),
}
SPELLS = ["Spark", "Firebolt", "Frost", "Drain", "Lightning"]
ABIL = SPELLS + ["Power", "Whirl"]
TYPES = ["PHYS", "FIRE", "COLD", "SHOCK", "DRAIN", "DARK"]
PHYS, FIRE, COLD, SHOCK, DRAIN, DARK = range(6)
RESP = "NRIX"
ROSTER = {  # 9.4 (kind names -> sym K_ names)
    1: ["RAT", "BAT", "SLIME", "GOBLIN"], 2: ["GOBLIN", "SPIDER", "BAT", "RAT"],
    3: ["SKELETON", "VAMPIRE", "GHOST", "BAT"], 4: ["ORC", "RAT", "SPIDER", "ARCHER"],
    5: ["MUMMY", "SKELETON", "ARCHER", "SPIDER"], 6: ["VAMPIRE", "GHOST", "NECRO", "ORC"],
    7: ["ORC", "NECRO", "GHOST", "NECRO"], 8: ["NECRO", "SKELETON", "GHOST", "VAMPIRE"],
}
BOSS_KIND = {1: "GOBLIN", 2: "SPIDER", 3: "VAMPIRE", 4: "OGRE", 5: "MUMMY", 6: "NECRO", 7: "DKNIGHT", 8: "ARCHMAGE"}
BOSS_NAME = {1: "Goblin King", 2: "Spider Queen", 3: "Vampire Lord", 4: "Ogre Warlord", 5: "Pharaoh",
             6: "High Necromancer", 7: "Death Knight", 8: "Archmage"}
TIERS = {"RAT": ("GIANT_RAT", "RABBIT_RAT"), "BAT": ("SCREECH", None), "GOBLIN": ("SLINGER", None),
         "SPIDER": ("BLACK_WIDOW", None), "SKELETON": ("SKEL_GUARD", "SKEL_KNIGHT"), "GHOST": ("POLTERGEIST", None),
         "ORC": ("ORC_BERSERK", "ORC_BOUNCER"), "ARCHER": ("SNIPER", None), "NECRO": ("BONE_CALLER", None)}
PARRY = {"SKEL_GUARD": 1 / 4, "SKEL_KNIGHT": 1 / 3, "DKNIGHT": 1 / 3}   # 9.6 / 9.1
# hero gear (8): name -> dict(slot, def, eva, mp, atk, die, bonus, spell, regen, food, res{type:resp}, cls)
GEAR = {
    "Short Sword": dict(slot="w", die=6, bonus=0, atk=0), "Long Sword": dict(slot="w", die=8, bonus=0, atk=1),
    "War Axe": dict(slot="w", die=10, bonus=0, atk=-1), "Cleaver": dict(slot="w", die=10, bonus=1, atk=1),
    "Oak Staff": dict(slot="w", die=4, bonus=0, atk=0), "Iron Staff": dict(slot="w", die=6, bonus=0, atk=0),
    "Rune Staff": dict(slot="w", die=4, bonus=0, atk=0, spell=1), "Bone Staff": dict(slot="w", die=6, bonus=0, atk=0, spell=2),
    "Robe": dict(slot="a", mp=2), "Leather": dict(slot="a", df=1), "Chain Mail": dict(slot="a", df=2),
    "Plate": dict(slot="a", df=3, regen=2.0), "Silk Cloak": dict(slot="a", df=1, eva=2, poison=1),
    "Gravecloak": dict(slot="a", df=2, res={DRAIN: 1, DARK: 1}),
    "Hood": dict(slot="h", mp=1), "Helm": dict(slot="h", df=1), "Goblin Helm": dict(slot="h", df=1, eva=1),
    "Mirror Helm": dict(slot="h", df=2, mirror=1),
    "Ring of Might": dict(slot="c", atk=1), "Ring of Warding": dict(slot="c", df=1),
    "Ring of Fire Ward": dict(slot="c", res={FIRE: 1}), "Amulet of Mana": dict(slot="c", regen=0.5),
    "Amulet of Plenty": dict(slot="c", food=0.5), "Scarab": dict(slot="c", regen=0.5, food=0.5),
    "Ring of the Grave": dict(slot="c", mp=2, res={DARK: 2}),
}
ITEM_GEAR = {"IT_A_ROBE": "Robe", "IT_A_LEATHER": "Leather", "IT_W_LONG": "Long Sword", "IT_W_AXE": "War Axe", "IT_W_IRON": "Iron Staff", "IT_W_RUNE": "Rune Staff",
             "IT_A_CHAIN": "Chain Mail", "IT_A_PLATE": "Plate", "IT_H_HOOD": "Hood", "IT_H_HELM": "Helm",
             "IT_C_MIGHT": "Ring of Might", "IT_C_WARD": "Ring of Warding", "IT_C_FIRE": "Ring of Fire Ward",
             "IT_C_MANA": "Amulet of Mana", "IT_C_PLENTY": "Amulet of Plenty"}
# gear name -> items_model type id name (GEAR1 gate / GEAR3 Enchant target use type ids); uniques included
NAME_TYPE = dict((v, k) for k, v in ITEM_GEAR.items())
NAME_TYPE.update({"Short Sword": "IT_W_SHORT", "Oak Staff": "IT_W_OAK", "Cleaver": "IT_W_CLEAVER", "Bone Staff": "IT_W_BONE",
                  "Silk Cloak": "IT_A_SILK", "Gravecloak": "IT_A_GRAVE", "Goblin Helm": "IT_H_KING", "Mirror Helm": "IT_H_MIRROR",
                  "Scarab": "IT_C_SCARAB", "Ring of the Grave": "IT_C_GRAVE"})
BAG_GEAR_MAX = 8
UNIQUE = {1: "Goblin Helm", 2: "Silk Cloak", 3: "Gravecloak", 4: ("Cleaver", "Bone Staff"), 5: "Scarab",
          6: "Ring of the Grave", 7: "Mirror Helm"}
FOODS = [10, 15, 20, 30, 40]   # 7 / 8: Carrot Apple Pear Cheese Meat (uniform)
DROP_FOOD = {"RAT": (30, 1, 4), "GOBLIN": (15, 1, 4), "ORC": (40, 1, 3)}   # (value, k, N) 8.6/9.6
LEVELUP = {"W": (4, 1), "M": (3, 2)}
HERO0 = {"W": dict(hp=24, mp=6, atk=3, eva=2), "M": dict(hp=16, mp=12, atk=1, eva=1)}

# ----------------------------------------------------------------------------------------------
# Data loading from the built image
# ----------------------------------------------------------------------------------------------


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


class Data:
    """Tables from the build, with overrides applied.  Plain python structures, no state."""

    def __init__(self, overrides=None):
        import combat_tables as C
        self.C = C
        sym, m = C.load()
        sna = open(os.path.join(REPO, "build/wazhack.sna"), "rb").read()
        self.sym = sym
        ov = overrides or {}
        self.params = dict(PARAMS)
        self.params.update(ov.get("param", {}))
        # --- kinds
        self.kid = {n[2:]: v for n, v in sym.items() if n.startswith("K_") and not n.startswith("K_BOSS") and v < 30
                    and n not in ("K_COUNT",)}
        self.kname = {i: C.KINDS[i][0] if i in C.KINDS else str(i) for i in range(30)}
        kt = sym["kind_tab"]
        self.k = {}
        kx = sym["kx_tab"] - C.BASE
        for i in range(2, 30):
            col = lambda off: sna[27 + kt + off - 0x4000 + i]
            e = m[kx + 8 * i:kx + 8 * i + 8]
            res = [0] * 6
            wmask = e[2]
            for t in range(6):
                res[t] = (e[t // 4] >> (2 * (t % 4))) & 3
                if wmask >> t & 1:
                    res[t] = 4        # W
            md = e[6]
            efx = (md >> sym["DH_EFX_SHIFT"]) & 7
            self.k[i] = dict(
                id=i, name=self.kname[i], hp=col(sym["KT_HP"]), atk=col(sym["KT_ATK"]), eva=col(sym["KT_EVA"]),
                die=col(sym["KT_DIE"]), bonus=col(sym["KT_BONUS"]), period=2 if col(sym["KT_FLAGS"]) & sym["KF_SLOW"] else 1,
                wt=col(sym["KT_REACH"]), flags=col(sym["KT_FLAGS"]), res=res, imm=e[3], kxp=e[4], df=e[5],
                boss=bool(e[3] & 0x80), mdty=DRAIN if md & 7 == 3 else PHYS, heal=bool(md & 0x80),
                efx=efx, ech=e[7] >> 4, etn=e[7] & 15)
        # --- ranks (ab_rank 7 x 3 x (mp, range, die, bonus, bounces, effect))
        rk = sym["ab_rank"] - C.BASE
        self.rank = {}
        for a, name in enumerate(ABIL):
            self.rank[name] = [dict(zip(("mp", "range", "die", "bonus", "bounces", "effect"), m[rk + (a * 3 + r) * 6:rk + (a * 3 + r) * 6 + 6]))
                               for r in range(3)]
        am = sym["ab_ammo"] - C.BASE
        self.ammo = [dict(zip(("mp", "range", "die", "bonus", "bounces", "effect"), m[am + 6 * i:am + 6 * i + 6])) for i in range(2)]
        x = 27 + sym["xpn_tab"] - 0x4000
        self.xpn = [sna[x + 2 * i] | sna[x + 2 * i + 1] << 8 for i in range(8)]
        # --- overrides
        for key, val in ov.get("ab_rank", {}).items():
            for rnk, cells in val.items():
                self.rank[key][int(rnk) - 1].update(cells)
        for kn, cells in ov.get("kx", {}).items():
            for ty, rsp in cells.items():
                code = {"N": 0, "R": 1, "I": 2, "X": 3, "W": 4}[rsp]
                self.k[self.kid[kn.upper().replace(" ", "_")]]["res"][TYPES.index(ty.upper())] = code
        for kn, cells in ov.get("kind", {}).items():
            self.k[self.kid[kn.upper().replace(" ", "_")]].update(cells)
        # --- derived
        self.id = lambda n: self.kid[n]
        self.k[self.kid["ARCHMAGE"]]["df"] = 1
        import ranged_model as RM
        self.rows = RM.ROWS
        self.grows = RM.GOLD_ROWS               # BOSS-RANGED: golden-only rows (ai_rhook's RK_GOLD1 gate)
        import copy
        self.gear = copy.deepcopy(GEAR)
        for gn, cells in ov.get("gear", {}).items():
            self.gear[gn].update(cells)
        P = self.params
        if P["ARCHMAGE_HP"] is not None and "hp" not in ov.get("kind", {}).get("Archmage", {}):
            self.k[self.kid["ARCHMAGE"]]["hp"] = P["ARCHMAGE_HP"]
        if P["GOLD_XP"] == "image":
            P["GOLD_XP"] = self.image_gold_xp()
        if P["BC_LIVE"] is None:
            P["BC_LIVE"] = sym["BC_LIVE"]
        if P["AM_LIVE"] is None:
            P["AM_LIVE"] = sym["AM_LIVE"]
        if P["AM_SUM_CD"] is None:
            P["AM_SUM_CD"] = sym["AM_SUM_CD"]
        if P["TOME_HP"] is None:
            P["TOME_HP"] = sym["TOME_MAX"]
        if P["TOME_AURA_R"] is None:
            P["TOME_AURA_R"] = sym["TOME_AURA_R"]
        self.tiers = {self.kid[b]: tuple(self.kid[t] if t else None for t in ts) for b, ts in TIERS.items()}
        self.tier_base = {t: b for b, ts in self.tiers.items() for t in ts if t is not None}

    def image_gold_xp(self):
        """Golden-boss XP by depth = bxp_d[depth - 1] (src/data7.asm, boss7 grate_open) + the base kind's KXP (kx_tab, in the
        image); D4 Ogre / D7 Death Knight / D8 Archmage are not golden (delta 0) and do not use this list."""
        txt = open(os.path.join(REPO, "src", "data7.asm")).read()
        mm = re.search(r"^bxp_d:\s*DB\s+([0-9, ]+)", txt, re.M)
        delta = [int(v) for v in mm.group(1).split(",")]
        return [delta[d] + self.k[self.kid[BOSS_KIND[d + 1]]]["kxp"] for d in range(8)]

    def describe(self):
        return {"ab_rank": self.rank, "params": self.params}


def parse_set(pairs):
    """--set key=val -> override dict."""
    ov = {}
    for p in pairs or []:
        k, v = p.split("=", 1)
        try:
            val = json.loads(v)
        except ValueError:
            val = v
        parts = k.split(".")
        if parts[0] == "ab_rank":
            ov.setdefault("ab_rank", {}).setdefault(parts[1], {}).setdefault(parts[2], {})[parts[3]] = val
        elif parts[0] == "kx":
            ov.setdefault("kx", {}).setdefault(parts[1], {})[parts[2]] = val
        elif parts[0] == "kind":
            ov.setdefault("kind", {}).setdefault(parts[1], {})[parts[2]] = val
        elif parts[0] == "param":
            ov.setdefault("param", {})[parts[1]] = val
        else:
            raise SystemExit("bad --set key " + k)
    return ov


def merge(a, b):
    out = dict(a)
    for k, v in b.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


# ----------------------------------------------------------------------------------------------
# Entities
# ----------------------------------------------------------------------------------------------
class Mon:
    __slots__ = ("kind", "k", "hp", "maxhp", "x", "atk", "df", "gold", "boss", "hold", "holdkind", "conf", "fear",
                 "cd", "climb", "scd", "sumlive", "resp", "bred", "slam", "blink", "pidx", "hexcd", "line", "back",
                 "tail", "summoned", "guard")

    def __init__(self, D, kind, depth, gold=False, resp=False):
        k = D.k[kind]
        self.kind, self.k = kind, k
        self.gold = gold
        hp = k["hp"] + depth - 1
        self.atk = k["atk"] + (depth - 1) // 3 + (2 if gold else 0)
        self.df = k["df"] + (1 if gold else 0)
        if gold:
            hp = 2 * hp + 6
        self.hp = self.maxhp = hp
        self.boss = k["boss"] or gold
        self.x = 0
        self.hold = self.holdkind = self.conf = self.fear = 0
        self.cd = self.scd = self.hexcd = 0
        self.climb = 0
        self.sumlive = 0
        self.resp = resp
        self.bred = False
        self.slam = 0
        self.blink = False
        self.pidx = 0
        self.line = True
        self.back = 0
        self.tail = 0
        self.summoned = False
        self.guard = False

    def label(self):
        return self.k["name"]


class Hero:
    pass


# ----------------------------------------------------------------------------------------------
# The game
# ----------------------------------------------------------------------------------------------
class Dead(Exception):
    def __init__(self, killer, cause):
        self.killer, self.cause = killer, cause


class Stall(Exception):
    pass


class Game:
    def __init__(self, D, hero, policy, rng, stats=None):
        self.D, self.P = D, D.params
        self.hero, self.pol, self.rng = hero, POLICIES[policy], rng
        self.G = D.gear
        self.jumped = False
        self.committed = False
        self.pname = policy
        self.rr = rng.random
        self.t = 0
        self.depth = 1
        self.lvlturn = 0
        self.stats = stats
        # hero state
        h = Hero()
        self.h = h
        z = dict(HERO0[hero])
        z["hp"], z["mp"] = (self.P["W_HP0"], self.P["W_MP0"]) if hero == "W" else (self.P["M_HP0"], self.P["M_MP0"])
        h.maxhp, h.hp, h.base_mp = z["hp"], z["hp"], z["mp"]
        h.atk0, h.eva0 = z["atk"], z["eva"]
        h.lvl, h.xp = 1, 0
        h.food = self.P["FOOD_START"]
        h.gear = {"w": "Short Sword" if hero == "W" else "Oak Staff", "a": "Leather" if hero == "W" else "Robe",
                  "h": None, "c": None}
        h.q = {"w": 0, "a": 0, "h": 0, "c": 0}     # GEAR2 per-instance offsets of the worn items (start kit q 0)
        h.m = {"w": 0, "a": 0, "h": 0, "c": 0}     # GEAR3 Enchant steps per worn item
        h.ranks = {n: 0 for n in ABIL}
        h.dry = 0
        h.bagfood = [15]
        h.heal = 1
        h.mana = 1 if hero == "M" else 0
        h.cure = 0
        h.scr = {"tele": 0, "fear": 0, "sleep": 0, "ench": 0}
        h.daggers = 3 if hero == "W" else 0
        h.arrows = 0
        h.bow = False
        h.bag_gear = []
        h.poison = 0
        h.weak = 0
        h.fearT = 0
        h.confT = 0
        h.hold = 0
        h.holdguard = False
        h.maxmp_extra = 0
        self.recalc()
        h.mp = h.maxmp
        self.books_state = 0
        self.bookrng = rng.randrange(1, 65536)
        self.ranks = h.ranks
        self.respawns_pending = []
        self.resp_count = 0
        self.rooms = []
        self.mage_dmg = {n: 0.0 for n in SPELLS}
        self.mage_casts = {n: 0 for n in SPELLS}
        self.overkill = [0.0, 0.0]
        self.potions_used = 0
        self.scrolls_used = 0
        self.entry = []      # (hp, mp, food, lvl) at each depth entry
        self.killer = None
        self.in_boss_dead = False
        self.visited_cleared = 0
        self.lp_lvl = 1
        self.boss_prep = False
        self.traps, self.trap_known, self.slot_start, self.slot_lair = {}, set(), -1, -2

    # ---- hero derived stats ----------------------------------------------------------------
    def hp0(self):
        return self.P["W_HP0"] if self.hero == "W" else self.P["M_HP0"]

    def lvl_gain(self):
        P = self.P
        return (P["W_LVL_HP"], P["W_LVL_MP"]) if self.hero == "W" else (P["M_LVL_HP"], P["M_LVL_MP"])

    def main_stat(self, g):
        """The stat v = m + q adds to (gear_rules 2.4): weapon die bonus; DEF for armour / helmets with DEF; MP for Robe / Hood."""
        d = self.G[g]
        if d["slot"] == "w":
            return "bonus"
        if d["slot"] in ("a", "h"):
            return "df" if "df" in d else "mp" if "mp" in d else None
        return None            # charms are never numeric

    def gear_prop(self, key, default=0):
        h = self.h
        tot = 0
        for sl, g in h.gear.items():
            if g:
                tot += self.G[g].get(key, default)
                if key == self.main_stat(g):
                    tot += h.q[sl] + h.m[sl]
        return tot

    def recalc(self):
        h = self.h
        lv = h.lvl
        h.maxhp = self.P["HP_BONUS"] + self.hp0() + (lv - 1) * self.lvl_gain()[0] + getattr(h, "vigor", 0) * 3 + getattr(h, "powerhp", 0)
        h.maxmp = h.base_mp + (lv - 1) * self.lvl_gain()[1] + max(0, self.gear_prop("mp")) + getattr(h, "power", 0) * 3 + getattr(h, "vigor", 0)
        w = self.G[h.gear["w"]]
        h.df = max(0, self.gear_prop("df"))
        # GEAR1 gate (gear_rules 1.2): worn Chain / Plate / Helm bans the Mage's spells, Robe / Hood the Warrior's power attacks
        import items_model as IM
        tid = lambda sl: IM.T[NAME_TYPE[h.gear[sl]]] if h.gear[sl] else 0
        h.gear_ban = IM.gear_banned(IM.HERO_MAGE if self.hero == "M" else IM.HERO_WARRIOR, tid("a"), tid("h"))
        h.atk_base = h.atk0 + (1 if lv >= 4 else 0) + (1 if lv >= 8 else 0) + self.gear_prop("atk")   # weapon atk is in GEAR
        h.eva_base = h.eva0 + (1 if lv >= 6 else 0) + self.gear_prop("eva")
        h.wdie, h.wbonus = w["die"], w["bonus"] + h.q["w"] + h.m["w"]
        h.spellbonus = w.get("spell", 0)
        h.regen_mult = 1.0
        for g in h.gear.values():
            if g:
                h.regen_mult *= self.G[g].get("regen", 1.0)
        h.food_mult = 1.0
        for g in h.gear.values():
            if g:
                h.food_mult *= self.G[g].get("food", 1.0)
        h.mirror = bool(self.gear_prop("mirror"))
        h.poison_imm = bool(self.gear_prop("poison"))
        h.res = [0] * 6
        for g in h.gear.values():
            if g:
                for ty, rs in self.G[g].get("res", {}).items():
                    h.res[ty] = max(h.res[ty], rs)   # 1 R, 2 I (3 X for the Mirror Helm below)
        if h.mirror:
            h.res[DARK] = 3
        if hasattr(h, "mp"):
            h.mp = min(h.mp, h.maxmp)
            h.hp = min(h.hp, h.maxhp)

    def hunger_stage(self):
        f = self.h.food
        return 0 if f >= 50 else 1 if f >= 25 else 2 if f >= 10 else 3   # FED OK HUNGRY WEAK

    def weak_active(self):
        return self.h.weak > 0 or self.h.food < 10

    def hero_atk(self):
        h = self.h
        a = h.atk_base
        st = self.hunger_stage()
        if st == 2:
            a -= 1
        if self.weak_active():
            a -= 2
        return a

    def hero_eva(self):
        h = self.h
        if h.hold:
            return 0
        return h.eva_base - (1 if self.weak_active() else 0)

    # ---- time -----------------------------------------------------------------------------
    def adv(self, n):
        """Advance n turns of passive effects (food, regen, poison, timers, trickle)."""
        h = self.h
        P = self.P
        while n > 0:
            c = min(n, 12 - self.t % 12)
            t0, t1 = self.t, self.t + c
            self.t, self.lvlturn = t1, self.lvlturn + c
            n -= c
            # food (fractional burn through food_mult)
            b = t1 // P["FOOD_BURN"] - t0 // P["FOOD_BURN"]
            if b:
                if h.food_mult == 1.0:
                    h.food = max(0, h.food - b)
                else:
                    h.fb = getattr(h, "fb", 0.0) + b * h.food_mult
                    d = int(h.fb)
                    h.fb -= d
                    h.food = max(0, h.food - d)
            if h.poison:
                k = min(c, h.poison)
                ticks = (t0 + k) // 4 - t0 // 4
                h.hp = max(1, h.hp - ticks)
                h.poison -= k
            if h.weak:
                h.weak = max(0, h.weak - c)
            st = self.hunger_stage()
            if st == 0 and h.hp < h.maxhp:
                h.hp = min(h.maxhp, h.hp + t1 // P["FED_REGEN"] - t0 // P["FED_REGEN"])
            if h.mp < h.maxmp and st < 3 and not h.weak:
                per = P["MAGE_REGEN"] if self.hero == "M" else P["WARRIOR_REGEN"]
                per = per * (2 if st == 2 else 1) * h.regen_mult
                per = max(1, per)
                g = 1 + h.maxmp // 16
                k = int(t1 / per) - int(t0 / per)
                if k:
                    h.mp = min(h.maxmp, h.mp + k * g)
            self.trickle(t0, t1)

    def trickle(self, t0, t1):
        P = self.P
        if self.in_boss_dead or self.resp_count >= P["TRICKLE_MAX"] or self.depth > 8:
            return
        k = t1 // P["TRICKLE_PERIOD"] - t0 // P["TRICKLE_PERIOD"]
        for _ in range(k):
            if self.resp_count < P["TRICKLE_MAX"] and self.rr() < P["TRICKLE_P"] and self.visited_cleared > 0:
                kind = self.roll_kind(self.D.id(self.rng.choice(ROSTER[self.depth])), self.depth, self.lp_lvl)
                m = Mon(self.D, kind, self.depth, resp=True)
                self.respawns_pending.append(m)
                self.resp_count += 1

    # ---- monster spawning -------------------------------------------------------------------
    def roll_kind(self, base, depth, lvl):
        D, P = self.D, self.P
        tr = D.tiers.get(base)
        if not tr:
            return base
        delta = max(-P["TIER_DELTA_MAX"], min(P["TIER_DELTA_MAX"], lvl - depth))
        t2 = max(0, min(P["T2_CAP"], P["T2_BASE"][depth - 1] + P["TIER_SHIFT2"] * delta))
        t3 = max(0, min(P["T3_CAP"], P["T3_BASE"][depth - 1] + P["TIER_SHIFT3"] * delta)) if depth >= P["TIER3_MIN_DEPTH"] else 0
        r = int(self.rr() * 256)
        if r < t3:
            return tr[1] if tr[1] else tr[0]
        if r < t3 + t2:
            return tr[0]
        return base

    def build_level(self, depth):
        D, P, rng = self.D, self.P, self.rng
        self.depth = depth
        self.lvlturn = 0
        self.lp_lvl = self.h.lvl
        self.resp_count = 0
        self.respawns_pending = []
        self.in_boss_dead = False
        self.visited_cleared = 0
        nrooms = rng.randint(P["ROOMS_LO"], P["ROOMS_HI"]) + (1 if depth == 8 else 0)
        base = [D.id(n) for n in ROSTER[depth]]
        N = P["MON_COUNT"][depth - 1] - 2
        nonspecial = nrooms - 2 - (1 if depth == 8 else 0)    # minus start, lair, (Sanctum)
        quota = [0] * nonspecial
        dist = [rng.randint(1, 4) for _ in range(nonspecial)]
        if N >= nonspecial:
            quota = [1] * nonspecial
            left = N - nonspecial
        else:
            order = sorted(range(nonspecial), key=lambda i: (-dist[i], i))
            for i in order[:N]:
                quota[i] = 1
            left = 0
        rmax = P["ROOM_MAX"][depth - 1]
        for _ in range(left):
            el = [i for i in range(nonspecial) if quota[i] < rmax]
            if not el:
                break
            tot = sum(dist[i] for i in el)
            r = rng.random() * tot
            for i in el:
                r -= dist[i]
                if r <= 0:
                    quota[i] += 1
                    break
        minw = min(D.k[b]["wt"] for b in base)
        sigma = max(8, rmax * minw)
        rooms = []
        for q in quota:
            sig, mons = 0, []
            for u in range(q):
                left_u = q - u - 1
                bi = rng.randrange(4)
                kind = self.roll_kind(base[bi], depth, self.lp_lvl)
                cand = [kind, base[bi]] + [b for i, b in enumerate(base) if i != bi]
                for kd in cand:
                    w = D.k[kd]["wt"]
                    if sig + w + left_u * minw <= sigma or w == minw:
                        mons.append(kd)
                        sig += w
                        break
            rooms.append([Mon(D, kd, depth) for kd in mons])
        self.rooms = rooms
        # lair: boss + escort
        boss = Mon(D, D.id(BOSS_KIND[depth]), depth, gold=depth in (1, 2, 3, 5, 6))
        esc = Mon(D, base[rng.randrange(4)], depth)
        self.lair = [boss, esc]
        self.boss = boss
        # items
        self.level_items(depth)

    def level_items(self, depth):
        import items_model as IM
        rng, h = self.rng, self.h
        items = []
        npot = 2 + rng.randrange(2)
        pots = ["heal"] + [("heal", "mana", "cure")[rng.randrange(3)] for _ in range(npot - 1)]
        food = [FOODS[rng.randrange(5)] for _ in range(3 + rng.randrange(2))]
        scr = [("tele", "fear", "sleep", "ench")[rng.randrange(4)] for _ in range(1 + rng.randrange(2))]
        gp = [ITEM_GEAR[next(n for n, v in IM.T.items() if v == t)] for t in IM.gear_pool(depth, IM.HERO_WARRIOR if self.hero == "W" else IM.HERO_MAGE)]
        gear = []
        for _ in range(1 + rng.randrange(2)):
            g = gp[rng.randrange(len(gp))]
            w = rng.randrange(8)       # GEAR2 2.3: one rnd(8) per gear entry; charms draw but keep q 0
            gear.append((g, IM.q_roll(w, depth) if self.G[g]["slot"] in ("w", "a", "h") else 0))
        books = 0
        if 1 <= depth <= 7:
            books = 1 + (1 if depth >= 4 and rng.randrange(2) == 0 else 0)
        self.floor = dict(pots=pots, food=food, scr=scr, gear=gear, books=books, dag=0, arr=0, bow=False)
        if self.hero == "W" and depth <= 7:
            self.floor["dag"] = 2 + rng.randrange(2)
            self.floor["arr"] = 5 + rng.randrange(4)
            if depth == 2:
                self.floor["bow"] = True
                self.floor["arr"] += 6
        # D1 book is in the start room: read immediately (starter)
        if depth == 1:
            self.floor["books"] -= 1
            self.read_book()
        self.collect_frac = 0.0
        self.setup_traps(depth)

    # ---- traps (TRAP2: every plate re-arms and stays) ---------------------------------------------
    def setup_traps(self, depth):
        """items_model.TRAP_COUNT[depth] plates, type uniform from the depth pool, in distinct slots: 0..len(rooms)-1 = fight rooms,
        len(rooms) = the start room (crossed when the hero leaves it), len(rooms)+1 = the lair (crossed on entry)."""
        import items_model as IM
        names = {IM.T["TT_DART"]: "dart", IM.T["TT_GAS"]: "gas", IM.T["TT_TELEPORT"]: "teleport", IM.T["TT_STUN"]: "stun",
                 IM.T["TT_ALARM"]: "alarm"}
        pool = [names[t] for t in IM.trap_pool(depth)]
        n = len(self.rooms)
        slots = list(range(n + 2))
        self.rng.shuffle(slots)
        self.traps = {sl: pool[self.rng.randrange(len(pool))] for sl in slots[:IM.TRAP_COUNT[depth]]}
        self.trap_known = set()
        self.slot_start, self.slot_lair = n, n + 1

    def cross_trap(self, slot):
        """The hero's move brings a plate under the body: fires with TRAP_HIT_P (a known plate fires again on every new crossing)."""
        t = self.traps.get(slot)
        if t is None or self.rr() >= self.P["TRAP_HIT_P"]:
            return
        h, rng = self.h, self.rng
        self.trap_known.add(slot)
        self.stat_add("trap_" + t)
        if t == "dart":
            self.dmg_hero(max(1, rng.randint(1, 4) + 1 - h.df), "trap", "trap")      # 1d4+1 PHYS, DEF applies
            if not h.poison_imm:
                h.poison = min(30, h.poison + 12)
        elif t == "gas":
            self.adv(4)                                                             # ASLEEP 4, no monster in the room yet
        elif t == "teleport":
            self.adv(rng.randint(5, 20))                                            # a flat walk back; never the lair while the boss lives
        elif t == "stun":
            self.dmg_hero(max(1, rng.randint(1, 3) - h.df), "trap", "trap")          # 1d3 PHYS + STUNNED 2-3
            self.adv(rng.randint(2, 3))
        elif t == "alarm":
            if not self.in_boss_dead and self.resp_count < self.P["TRICKLE_MAX"]:
                self.resp_count += 1                                                # a wave counts toward LP_RESPAWNS < 6
                wave = []
                for _ in range(1 + rng.getrandbits(1)):
                    kind = self.roll_kind(self.D.id(rng.choice(ROSTER[self.depth])), self.depth, self.lp_lvl)
                    wave.append(Mon(self.D, kind, self.depth, resp=True))
                self.visit(wave, "room")

    def cross_known(self):
        """A transit passes some of the known plates again (TRAP_PATH_P each)."""
        for sl in sorted(self.trap_known):
            if self.rr() < self.P["TRAP_PATH_P"]:
                self.cross_trap(sl)

    # ---- pickups ---------------------------------------------------------------------------
    def pick_some(self, frac):
        """Collect `frac` of the remaining floor loot (room-by-room approximation)."""
        f, h, rng = self.floor, self.h, self.rng

        def take(lst):
            k = len(lst)
            out = []
            for _ in range(k):
                if self.rr() < frac:
                    out.append(lst.pop(0))
                else:
                    lst.append(lst.pop(0))
            return out
        for p in take(f["pots"]):
            if p == "heal":
                h.heal += 1
            elif p == "mana":
                h.mana += 1
            else:
                h.cure += 1
        for v in take(f["food"]):
            h.bagfood.append(v)
        for s in take(f["scr"]):
            h.scr[s] += 1
        for g, q in take(f["gear"]):
            self.equip_consider(g, q)
        nb = f["books"]
        for _ in range(nb):
            if self.rr() < frac:
                f["books"] -= 1
                self.read_book()
        if self.hero == "W":
            if self.rr() < frac and f["dag"]:
                h.daggers = min(9, h.daggers + f["dag"])
                f["dag"] = 0
            if self.rr() < frac and f["arr"]:
                h.arrows = min(24, h.arrows + f["arr"])
                f["arr"] = 0
            if f["bow"] and self.rr() < frac:
                h.bow = True
                f["bow"] = False
        for _ in range(len(f["scr"]) + 0):
            pass
        self.use_enchant()

    def use_enchant(self):
        """GEAR3 (gear_rules 3.1): every Enchant scroll goes through items_model.enchant_target with the sim's own RNG as `step`:
        a random worn weapon / armour / helmet with m < +3, else a bag item, else NOTHING HAPPENS (scroll kept here, so the loop ends)."""
        import items_model as IM
        h = self.h
        ist = lambda q, m: ((m & 7) << 5) | (q & 7)
        step = lambda: self.rng.getrandbits(16)
        while h.scr["ench"]:
            slots = ("w", "a", "h")
            worn = [(IM.T[NAME_TYPE[h.gear[sl]]], ist(h.q[sl], h.m[sl])) if h.gear[sl] else (0, 0) for sl in slots]
            bag = [(IM.T[NAME_TYPE[n]], ist(q, m)) for n, q, m in h.bag_gear]
            r = IM.enchant_target(worn, bag, step)
            if r is None:
                break
            h.scr["ench"] -= 1
            where, i, new = r
            if where == "worn":
                h.m[slots[i]] = IM.istate_m(new)
                self.recalc()
            else:
                n, q, _ = h.bag_gear[i]
                h.bag_gear[i] = (n, q, IM.istate_m(new))
            self.stat_add("enchants")

    def equip_consider(self, g, q=0):
        h = self.h
        import items_model as IM
        gd = self.G[g]
        slot = gd["slot"]
        cur = h.gear.get(slot)
        banned = IM.type_banned_for(IM.HERO_MAGE if self.hero == "M" else IM.HERO_WARRIOR, IM.T[NAME_TYPE[g]])
        if not banned and self.gear_score(g, q, 0) > (self.gear_score(cur, h.q[slot], h.m[slot]) if cur else -1):
            if cur:
                self.to_bag(cur, h.q[slot], h.m[slot])
            h.gear[slot] = g
            h.q[slot], h.m[slot] = q, 0
            self.recalc()
        else:
            self.to_bag(g, q, 0)

    def to_bag(self, g, q, m):
        if self.G[g]["slot"] in ("w", "a", "h") and len(self.h.bag_gear) < BAG_GEAR_MAX:
            self.h.bag_gear.append((g, q, m))

    def gear_score(self, g, q=0, m=0):
        if not g:
            return -1
        d = self.G[g]
        v = (q + m) if d["slot"] in ("w", "a", "h") else 0     # v = m + q on the main stat (gear_rules 2.4)
        if d["slot"] == "w":
            avg = (d["die"] + 1) / 2 + d["bonus"] + v + (d.get("atk", 0) * 0.5)
            if self.hero == "M":
                avg += d.get("spell", 0) * 2.5
            return avg
        df = d.get("df", 0) + (v if "df" in d else 0)
        mp = d.get("mp", 0) + (v if "df" not in d and "mp" in d else 0)
        s = df * 3 + d.get("eva", 0) * 2 + d.get("poison", 0) * 1
        if self.hero == "M":
            s += mp * 1.5 + (4 if d.get("regen") == 0.5 else 0) - (6 if d.get("regen") == 2.0 else 0)
            s += d.get("atk", 0) * 0.2
            if g == "Ring of the Grave":
                s += 3
        else:
            s += d.get("atk", 0) * 3 + mp * 0.3 - (1 if d.get("regen") == 2.0 else 0) + (3 if d.get("regen") == 0.5 else 0)
        if d.get("food"):
            s += 2
        if d.get("mirror"):
            s += 6
        if d.get("res"):
            s += 1.5 * len(d["res"])
        return s

    def read_book(self):
        import book_model as BM
        h = self.h
        kind = BM.K_KNIGHT if self.hero == "W" else BM.K_WIZARD
        n = len(BM.UNLOCK[kind])
        cur = [h.ranks[(ABIL[:5] if self.hero == "M" else ["Power", "Whirl"])[i]] for i in range(n)]
        self.D.params["PITY_N"]
        BM.PITY_N = self.P["PITY_N"]
        r = BM.book_read(kind, self.depth, cur, self.books_state, self.bookrng)
        self.bookrng, self.books_state = r["rng"], r["dry"]
        names = ABIL[:5] if self.hero == "M" else ["Power", "Whirl"]
        if r["act"] == "tome":
            if self.hero == "W":
                h.vigor = getattr(h, "vigor", 0) + 1
            else:
                h.power = getattr(h, "power", 0) + 1
                h.powerhp = getattr(h, "powerhp", 0) + 1
            self.recalc()
            h.hp = min(h.maxhp, h.hp + 3)
            h.mp = min(h.maxmp, h.mp + 3)
        else:
            h.ranks[names[r["k"]]] = r["ranks"][r["k"]]
        if self.hero == "W" and h.ranks["Power"] and h.ranks["Power"] < self.P["W_START_POWER"]:
            h.ranks["Power"] = self.P["W_START_POWER"]

    # ---- XP --------------------------------------------------------------------------------
    def gain_xp(self, mon):
        h = self.h
        if mon.k["id"] == self.D.id("ARCHMAGE"):
            return
        x = mon.k["kxp"]
        if mon.gold and self.P["GOLD_XP"]:
            x = self.P["GOLD_XP"][self.depth - 1]
        if mon.resp or mon.summoned:
            x = max(1, x // 2)
        h.xp += x
        while h.lvl < 9 and h.xp >= self.D.xpn[h.lvl - 1]:
            h.lvl += 1
            hp, mp = self.lvl_gain()
            h.hp += hp
            h.mp += mp
            self.recalc()
            h.hp = min(h.hp, h.maxhp)

    # ---- resource helpers -------------------------------------------------------------------
    def eat_if_needed(self, force=False):
        h = self.h
        if h.poison and not h.poison_imm:
            return
        if h.food <= self.P["EAT_AT"] or force:
            if h.bagfood:
                h.bagfood.sort()
                h.food = min(100, h.food + h.bagfood.pop(0))

    def heal_pct(self):
        return self.h.hp / self.h.maxhp

    def dmg_hero(self, amt, killer, cause="melee"):
        h = self.h
        if amt <= 0:
            return
        h.hp -= amt
        if h.hold and h.holdkind == "sleep":
            h.hold = 0
        if h.hp <= 0:
            raise Dead(killer, cause)

    # ---- resting ---------------------------------------------------------------------------
    def rest(self, hp_to=1.0, mp_to=1.0, cap=None):
        h = self.h
        P = self.P
        cap = cap or P["REST_MAX"]
        used = 0
        while used < cap:
            need_hp = h.hp < h.maxhp * hp_to
            need_mp = (self.hero == "M" or (self.boss_prep and (h.ranks["Power"] or h.ranks["Whirl"]))) and h.mp < h.maxmp * mp_to
            if self.hunger_stage() >= 1:
                self.eat_if_needed(force=self.hunger_stage() >= 1 and h.food < 50 and bool(h.bagfood) and len(h.bagfood) > 2)
                if self.hunger_stage() >= 1:
                    need_hp = False
            if self.hunger_stage() >= 3 or h.weak:
                need_mp = False
            if not (need_hp or need_mp):
                break
            if h.food <= P["EAT_AT"]:
                self.eat_if_needed()
            self.adv(6)
            used += 6
        self.stat_add("rest_turns", used)
        return used

    def stat_add(self, key, v=1):
        if self.stats is not None:
            self.stats[key] = self.stats.get(key, 0) + v

    # ---- main --------------------------------------------------------------------------------
    def play(self):
        """Returns (won, depth_reached, killer, cause)."""
        self.stats_out = {}
        try:
            for depth in range(1, 9):
                self.entry.append((self.h.hp / self.h.maxhp, self.h.mp, self.h.food, self.h.lvl))
                self.stat_depth = depth
                self.build_level(depth)
                self.run_level(depth)
            return True, 8, None, None
        except Dead as d:
            return False, self.depth, d.killer, d.cause
        except Stall:
            return False, self.depth, "STALL", "stall"

    def run_level(self, depth):
        P, h, rng = self.P, self.h, self.rng
        self.cross_trap(self.slot_start)
        order = list(range(len(self.rooms)))
        rng.shuffle(order)
        n = len(order)
        for i, ri in enumerate(order):
            self.transit()
            self.pre_room_rest()
            self.cross_trap(ri)
            self.visit(self.rooms[ri], "room", slot=ri)
            self.visited_cleared += 1
            self.pick_some(1.0 / (n - i + 0.0) * 1.0 if i < n else 1.0)
            self.meet_respawns()
        self.pick_some(1.0)
        # lair
        self.transit()
        self.meet_respawns()
        self.pre_room_rest(lair=True)
        self.cross_trap(self.slot_lair)
        self.lair_fight(depth)
        self.in_boss_dead = True
        # boss unique
        u = UNIQUE.get(depth)
        if u:
            if isinstance(u, tuple):
                u = u[0] if self.hero == "W" else u[1]
            self.equip_consider(u, 0)
        if depth == 8:
            self.sanctum()

    def transit(self):
        self.adv(self.rng.randint(self.P["TRANSIT_LO"], self.P["TRANSIT_HI"]))
        self.eat_if_needed()
        self.cross_known()

    def meet_respawns(self):
        keep = []
        for m in self.respawns_pending:
            if self.rr() < self.P["TRICKLE_MEET_P"]:
                self.pre_room_rest()
                self.visit([m], "room")
            else:
                keep.append(m)
        self.respawns_pending = keep

    def pre_room_rest(self, lair=False):
        h, pol = self.h, self.pol
        if lair and self.pname != "reckless":
            # assumption: cautious/average rest to full before a boss lair (the boss never regenerates, so it is free)
            self.boss_prep = True      # the Warrior also rests for MP before a boss (power attacks are his boss tool)
            self.rest(1.0, 1.0)
            self.boss_prep = False
            return
        hp_need = self.heal_pct() < pol["rest_hp"]
        mp_need = self.hero == "M" and h.mp < h.maxmp * pol["rest_mp"]
        if hp_need or mp_need:
            self.rest(1.0, 1.0)
        elif self.hero == "M" and h.mp < h.maxmp:
            pass

    def visit(self, mons, kind, slot=None):
        """Fight a room's monsters until all dead; the bot may retreat (non-boss: stall/escape)."""
        tries = 0
        while mons:
            res = self.fight(mons, boss_room=False)
            tries += 1
            if res == "clear":
                return
            # escaped / retreated: rest and come back (monsters persisted with exact hp)
            self.stat_add("retreats")
            self.rest(1.0, 1.0)
            self.cross_trap(slot)          # the way back into the room crosses the plate again
            if tries > 12:
                raise Stall()

    def lair_fight(self, depth):
        self.committed = False
        mons = self.lair
        tries = 0
        while self.boss.hp > 0:
            res = self.fight(mons, boss_room=True)
            if res == "clear":
                return
            self.stat_add("boss_retreats")
            self.boss_prep = True
            self.rest(1.0, 1.0)
            self.boss_prep = False
            # a hero that could not rest back above the retreat line (HUNGRY / WEAK stage, empty bag) commits to the fight:
            # retreating again would only loop (it used to burn 40 cycles and count as a STALL loss)
            self.committed = self.pol["retreat"] is not None and self.h.hp / self.h.maxhp < self.pol["retreat"] + 0.25
            self.cross_trap(self.slot_lair)
            tries += 1
            if tries > 40:
                raise Stall()

    def sanctum(self):
        """D8 ending (WIN2): the Archmage is dead -> the seal broke -> walk to the Sanctum -> destroy the Tome (TOME_HP hits, one per
        attack released inside its reach / range, never missed, resist ignored) -> the exit gate opens -> leave through it -> win.
        Aura: 1 HP untyped at every turn end while gap < TOME_AURA_R.  The turn of the last hit ends the run before its aura tick."""
        D, P, h, pol = self.D, self.P, self.h, self.pol
        self.transit()
        self.meet_respawns()
        self.boss_prep = True
        self.rest(1.0, 1.0)             # no timer in the Sanctum; the bot arrives full and un-feared
        self.boss_prep = False
        h.fearT = h.confT = 0
        T, R = P["TOME_HP"], P["TOME_AURA_R"]
        nA = nB = 0                     # attacks from gap R (outside the aura: range > R) / from gap range-1 (< R)
        gB = 0
        if self.hero == "M" and not h.gear_ban:
            opts = [(D.rank[s][r]["range"], D.rank[s][r]["mp"]) for s in SPELLS for r in range(h.ranks[s])]
            a = [c for rg, c in opts if rg > R]
            if a and h.mp >= min(a):
                nA = min(T, h.mp // min(a))
                left = h.mp - nA * min(a)
                b = [(rg, c) for rg, c in opts if 2 <= rg <= R and c <= left]
                if b and nA < T:
                    gB, cB = max(b)[0] - 1, min(c for rg, c in b if rg == max(b)[0])
                    nB = min(T - nA, left // cB)
            else:
                b = [(rg, c) for rg, c in opts if 2 <= rg <= R and c <= h.mp]
                if b:
                    gB, cB = max(b)[0] - 1, min(c for rg, c in b if rg == max(b)[0])
                    nB = min(T, h.mp // cB)
        elif self.hero == "W":
            if h.bow and D.ammo[1]["range"] > R:
                nA = min(T, h.arrows)
            if nA < T and h.daggers and 2 <= D.ammo[0]["range"] <= R:
                gB = D.ammo[0]["range"] - 1
                nB = min(T - nA, h.daggers)
            elif nA < T and h.daggers and D.ammo[0]["range"] > R:
                nA = min(T, nA + h.daggers)
        nM = T - nA - nB                # melee / Power Strike / Whirlwind / staff on the lectern: 1 hit each, gap 0
        g_final = 0 if nM else (gB if nB else R)
        approach = max(0, R - g_final)
        shots = nB + nM
        aura_turns = approach + shots - 1 if shots else 0
        self.stat_add("tome_aura", aura_turns)
        n = aura_turns
        while n > 0:
            n -= 1
            self.adv(1)
            self.dmg_hero(1, "Tome aura", "aura")
            if h.hp / h.maxhp < pol["heal"] and h.heal:      # a potion costs a turn inside the aura
                h.heal -= 1
                h.hp = min(h.maxhp, h.hp + P["HEAL_AMT"])
                n += 1
        # the gate opens: the way out of the lair (the exit col sits there)
        self.adv(self.rng.randint(P["EXIT_LO"], P["EXIT_HI"]))
        self.eat_if_needed()
        self.cross_known()
        self.meet_respawns()

    # ---- the fight ---------------------------------------------------------------------------
    def setup_geometry(self, mons, boss_room):
        P, rng = self.P, self.rng
        gaps = sorted(rng.randint(P["GAP_LO"], P["GAP_HI"]) for _ in mons)
        if boss_room:
            gaps = sorted(rng.randint(8, P["GAP_HI"]) for _ in mons)
        mons_sorted = sorted(mons, key=lambda m: m.x if m.x else 0)
        order = list(mons)
        rng.shuffle(order)
        prev = 0
        for m, g in zip(order, gaps):
            g = max(g, prev + 2) if prev else g
            m.x = g
            prev = g
            m.climb = rng.randint(P["T_CLIMB_LO"], P["T_CLIMB_HI"]) if self.rr() > P["P_LINE"] else 0
            m.back = rng.randint(0, 6)
            m.cd = 0 if m.k["id"] != self.D.id("ARCHMAGE") else 1
            m.hold = m.hold if m.boss else 0
            m.hold = 0
            m.conf = m.fear = 0
            m.slam = 0
        # Archmage is far (never walks)
        for m in mons:
            if m.k["id"] == self.D.id("ARCHMAGE"):
                m.x = rng.randint(10, 22)
        self.wall = rng.randint(max(g for g in gaps) + 2, max(P["WALL_MAX"], max(gaps) + 2))
        self.behind = rng.randint(0, P["BEHIND_MAX"])
        self.hx = 0   # hero shifts by kiting; monsters coordinates absolute

    def fight(self, mons, boss_room):
        """Returns 'clear' or 'retreat'.  Raises Dead / Stall.  Mutates the monster list in place."""
        D, P, h, pol = self.D, self.P, self.h, self.pol
        mons[:] = [m for m in mons if m.hp > 0]
        self.setup_geometry(mons, boss_room)
        self.hx = 0
        self.jumped = False
        self.turns = 0
        h.hold = 0
        start_t = self.t
        while True:
            alive = [m for m in mons if m.hp > 0]
            if not alive:
                mons[:] = []
                self.after_fight()
                return "clear"
            if self.turns >= P["FIGHT_STALL"]:
                # the bot cannot make progress: walk away (monsters stay, banked)
                self.stat_add("stall_fights")
                if self.stalls_count() > 3:
                    raise Stall()
                mons[:] = alive
                return "retreat"
            self.turns += 1
            # --- hero phase
            self.adv(1)
            if h.hold:
                h.hold -= 1
                if h.hold == 0:
                    h.holdguard = True
            else:
                res = self.hero_turn(alive, mons, boss_room)
                self.jumped = res == "jump"
                h.holdguard = False if res not in ("skip", "jump") else h.holdguard
                if res == "retreat":
                    mons[:] = [m for m in mons if m.hp > 0]
                    return "retreat"
            alive = [m for m in mons if m.hp > 0]
            if not alive:
                continue
            # --- monster phase
            for m in alive:
                if m.hp <= 0:
                    continue
                self.monster_turn(m, alive, mons)
            if h.fearT:
                h.fearT -= 1
            if h.confT:
                h.confT -= 1

    def stalls_count(self):
        self._stalls = getattr(self, "_stalls", 0) + 1
        return self._stalls

    def after_fight(self):
        h = self.h
        # recover thrown daggers/arrows (spec 6.3 expectation) after a clear
        if self.hero == "W":
            h.daggers = min(9, h.daggers + getattr(self, "dag_floor", 0))
            self.dag_floor = 0
            h.arrows = min(24, h.arrows + getattr(self, "arr_floor", 0))
            self.arr_floor = 0
        h.holdguard = False

    # ---- monster side -----------------------------------------------------------------------
    def in_line(self, m):
        return m.climb <= 0

    def front(self, alive):
        c = [m for m in alive if self.in_line(m)]
        return min(c, key=lambda m: m.x) if c else None

    def mon_res(self, m, ty):
        return m.k["res"][ty]

    def apply_res(self, m, ty, roll, ign=False):
        r = m.k["res"][ty]
        if ign and r == 1:
            r = 0
        if r == 4:
            return roll * 2, "W"
        if r == 1:
            return max(1, roll // 2), "R"
        if r == 2:
            return 0, "I"
        if r == 3:
            return 0, "X"
        return roll, "N"

    def hero_res(self, ty, roll):
        r = self.h.res[ty]
        if r == 1:
            return max(1, roll // 2)
        if r >= 2:
            return 0
        return roll

    def mrow(self, m):
        """rk_tab + ai_rhook: the shooter row of m, or None (BOSS-RANGED: the Goblin / Spider rows only when golden)."""
        kid = m.k["id"]
        if kid in self.D.grows:
            return self.D.grows[kid] if m.gold and self.P["BOSS_RANGED"] else None
        return self.D.rows.get(kid)

    def in_rng(self, gap, r):
        """rg_line's range test: gap < r (RANGED_LT 0: the old sim's gap <= r)."""
        return gap < r if self.P["RANGED_LT"] else gap <= r

    def ranged_hit(self, m, row):
        """rg_shoot of a PHYS (non-spell) row on the hero: d20 vs EVA, 1dDIE + BON (+1 golden) - DEF (min 1);
        a poison rider (BOSS-RANGED Spider Queen: chance 0 = always) adds DHE x 2 turns, cap 30 (Silk Cloak immune)."""
        h = self.h
        if self.rr() < self.hit_hero_chance(m.atk):
            dm = self.rng.randint(1, row[3]) + row[4] + (1 if m.gold and self.P["GOLD_RDMG"] else 0)
            self.dmg_hero(max(1, dm - h.df), m.k["name"], "ranged")
            if (row[5] >> 4) & 7 == 6 and not h.poison_imm:
                h.poison = min(30, h.poison + (row[6] & 15) * 2)

    def hit_hero_chance(self, atk):
        p = (11 + atk - self.hero_eva()) / 20.0
        return 0.0 if p < 0 else 1.0 if p > 1 else p

    def monster_turn(self, m, alive, mons):
        D, P, h = self.D, self.P, self.h
        k = m.k
        kid = k["id"]
        if m.climb > 0:
            m.climb -= 1
            return
        if m.hold:
            m.hold -= 1
            if m.hold == 0:
                m.guard = True
            return
        m.guard = False
        # speed
        per = k["period"]
        if kid == D.id("VAMPIRE") and m.x > 2:
            per = 1
        if per > 1 and self.turns % per:
            return
        if m.conf and self.rr() < 0.5:
            m.conf -= 1
            return
        if m.conf:
            m.conf -= 1
        if kid == D.id("ARCHMAGE"):
            return self.archmage_turn(m, alive, mons)
        if m.fear:
            m.fear -= 1
            m.x += 1
            return
        row = self.mrow(m)
        gap = m.x
        if row:
            r, N, flags, die, bonus = row[0], row[1], row[2], row[3], row[4]
            if kid == D.id("BONE_CALLER") and m.scd <= 0 and len([o for o in mons if o.summoned and o.hp > 0]) < P["BC_LIVE"]:
                m.scd = 8
                base = D.id("SKELETON") if D.id("SKELETON") in [D.id(n) for n in ROSTER[self.depth]] else D.id("GHOST")
                s = Mon(D, base, self.depth, resp=True)
                s.summoned = True
                s.x = max(1, m.x - 1)
                s.climb = 0
                mons.append(s)
                alive.append(s)
                return
            m.scd -= 1
            away = flags & 2
            if gap < 3 and away and kid != D.id("SNIPER") and m.back > 0:
                m.x += 1
                m.back -= 1
                return
            if gap > 1 and self.in_rng(gap, r) and m.cd <= 0 and self.front(alive) is m:
                m.cd = N
                spell = flags & 1
                if not spell:                           # PHYS rows: Archer / Sniper / Slinger / Goblin King / Spider Queen
                    self.ranged_hit(m, row)
                else:
                    dm = self.rng.randint(1, die) + bonus + (1 if m.gold and P["GOLD_RDMG"] else 0)
                    dm = self.hero_res(DARK, dm)
                    if h.res[DARK] == 3:     # Mirror: reflected to the shooter at x1/2
                        m.hp -= max(1, dm // 2) if dm else 0
                        dm = 0
                    self.dmg_hero(dm, k["name"], "ranged")
                    if dm and self.rr() < 1.0 / P["NECRO_FEAR_N"] and not h.fearT:
                        h.fearT = P["NECRO_FEAR_T"]
                return
            m.cd -= 1
        # melee / walking
        reach = 2 if (kid == D.id("OGRE") and m.slam >= P["SLAM_EVERY"] - 1) else 1
        if self.front(alive) is m or True:
            blocked = any(o is not m and o.hp > 0 and o.x < m.x and m.x - o.x < 2 for o in alive)
        if m.x <= reach:
            self.mon_melee(m, reach)
        elif not blocked:
            m.x -= 1
            if m.x < 1:
                m.x = 1

    def mon_melee(self, m, reach):
        D, P, h = self.D, self.P, self.h
        k = m.k
        kid = k["id"]
        m.slam += 1
        slam = kid == D.id("OGRE") and m.slam >= P["SLAM_EVERY"]
        atk = m.atk
        if kid == D.id("ORC_BERSERK") and m.hp <= m.maxhp // 2:
            atk += 2
        if self.rr() >= self.hit_hero_chance(atk):
            if slam:
                m.slam = 0
            return
        dm = self.rng.randint(1, k["die"]) + k["bonus"] + (1 if m.gold else 0)
        if slam:
            m.slam = 0
            dm = dm + dm // 2
        dm = dm - 0
        wk = self.weak_active()
        dty = k["mdty"]
        dm = self.hero_res(dty, dm)
        dm = max(1 if dm else 0, dm - h.df)
        if dm:
            self.dmg_hero(dm, BOSS_LBL(m, self.depth), "melee")
        if k["heal"]:
            m.hp = min(m.maxhp, m.hp + dm)
        if kid == self.D.id("MUMMY"):
            h.food = max(0, h.food - 5)
            if self.rr() < 1 / 3:
                h.weak = max(h.weak, 12)
        # on-hit effect (kx melee byte)
        e = k["efx"]
        if e and k["id"] not in (self.D.id("MUMMY"),) and dm >= 0:
            ch = k["ech"]
            if ch == 0 or self.rr() < 1.0 / ch:
                tn = k["etn"]
                if e == 6 and not h.poison_imm:
                    h.poison = min(30, h.poison + tn * 2 + (6 if m.gold and kid == D.id("SPIDER") else 0))
                elif e == 5:
                    h.confT = max(h.confT, tn)
                elif e == 4:
                    h.fearT = max(h.fearT, tn)
                elif e == 3 and not h.holdguard and not h.hold:
                    h.hold, h.holdkind = tn, "stun"
        if slam and not h.holdguard and not h.hold:
            h.hold, h.holdkind = 1, "stun"

    def archmage_turn(self, m, alive, mons):
        D, h, P = self.D, self.h, self.P
        m.hexcd = max(0, m.hexcd - 1)
        m.scd = max(0, m.scd - 1)
        order = [("Death", DARK, 28, 8, 3, "fear", 1.0 / P["ARCH_FEAR_N"]), ("Frost", COLD, 12, 6, 1, "frz", 0.5),
                 ("Light", SHOCK, 12, 8, 1, "conf", 0.5), ("Drain", DRAIN, 5, 6, 1, "weak", 0.5),
                 ("Fire", FIRE, 12, 8, 2, "stun", 85 / 256)]
        gap = m.x
        if m.cd <= 0 and self.in_line(m):
            nm, ty, rg, die, bon, eff, ch = order[m.pidx]
            hold_row = eff in ("frz", "stun")
            if gap >= rg or (hold_row and (h.hold or h.holdguard)):
                nm, ty, rg, die, bon, eff, ch = order[0]
            m.pidx = (m.pidx + 1) % 5
            m.cd = 1
            dm = self.rng.randint(1, die) + bon
            if ty == DARK and h.res[DARK] == 3:
                m.hp -= max(1, dm // 2)
                dm = 0
            else:
                dm = self.hero_res(ty, dm)
            if dm:
                self.dmg_hero(dm, "Archmage", "ranged")
                if ty == DRAIN:
                    m.hp = min(m.maxhp, m.hp + dm)
                if self.rr() < ch:
                    if eff == "fear":
                        h.fearT = max(h.fearT, P["NECRO_FEAR_T"])
                    elif eff == "frz" and not h.hold and not h.holdguard:
                        h.hold, h.holdkind = 2, "frozen"
                    elif eff == "conf":
                        h.confT = max(h.confT, 4)
                    elif eff == "weak":
                        h.weak = max(h.weak, 8)
                    elif eff == "stun" and not h.hold and not h.holdguard:
                        h.hold, h.holdkind = 1, "stun"
            return
        if m.cd > 0:
            m.cd -= 1
        if not m.blink and m.hp <= m.maxhp // 2:
            m.blink = True
            m.x = min(22, m.x + self.rng.randint(4, 8))     # the blink does not touch the summon counter S (arch6.asm)
            return
        live = len([o for o in mons if o.summoned and o.hp > 0])
        if m.scd <= 0 and live < P["AM_LIVE"]:
            base = D.id("SKELETON")
            s = Mon(D, base, self.depth, resp=True)
            s.summoned = True
            s.x = max(2, m.x - 1)
            mons.append(s)
            alive.append(s)
            m.scd = P["AM_SUM_CD"]
            return
        if m.hexcd <= 0 and gap < 12 and self.in_line(m):
            m.hexcd = 4
            if not h.hold and not h.holdguard:
                h.hold, h.holdkind = 3, "sleep"
            elif not h.poison_imm:
                h.poison = min(30, h.poison + 12)
            return
        if gap <= 1:
            if self.rr() < self.hit_hero_chance(m.atk):
                self.dmg_hero(max(1, self.rng.randint(1, 6) - h.df), "Archmage", "melee")

    # ---- hero side --------------------------------------------------------------------------
    def hero_turn(self, alive, mons, boss_room):
        D, P, h, pol = self.D, self.P, self.h, self.pol
        rr = self.rr
        if h.confT and rr() < 1 / 3:
            return "skip"
        pc = h.hp / h.maxhp
        front = self.front(alive)
        # emergency: heal / escape
        if pc < pol["heal"] and h.heal and not (front is None):
            h.heal -= 1
            h.hp = min(h.maxhp, h.hp + P["HEAL_AMT"])
            self.stat_add("heals")
            return "skip"
        if pol["escape"] is not None and pc < pol["escape"] and front is not None:
            if h.scr["tele"]:
                h.scr["tele"] -= 1
                self.stat_add("tele_scrolls")
                return "retreat"
            if h.scr["sleep"]:
                h.scr["sleep"] -= 1
                for m in alive:
                    if not m.boss and not (m.k["imm"] & 1):
                        m.hold, m.holdkind = 8, "sleep"
                return "skip"
            if h.scr["fear"]:
                h.scr["fear"] -= 1
                for m in alive:
                    if not m.boss and not (m.k["imm"] & 8):
                        m.fear = 6
                return "skip"
        if boss_room and not self.committed and pol["retreat"] is not None and pc < pol["retreat"] and self.boss.hp > 0 and self.boss in alive:
            if self.boss.x >= 2 or True:
                return self.do_retreat(alive, mons)
        cure_gap = 1 if self.hero == "W" else 8 if P["FEAR_CAST"] else -1     # Warrior: monster at melee reach; Mage (FEAR-CAST): in spell range
        if h.fearT and h.cure and front is not None and front.x <= cure_gap:
            h.cure -= 1
            h.fearT = 0
            h.weak = 0
            h.poison = 0
            h.hp = min(h.maxhp, h.hp + P["CURE_HP"])
            return "skip"
        # Mana potion when dry
        if self.hero == "M" and h.mana and h.mp < self.min_cost() and front is not None and len(alive) > 0:
            h.mana -= 1
            h.mp = min(h.maxmp, h.mp + P["MANA_AMT"])
            return "skip"
        if front is None:
            # all monsters out of line: wait / eat
            return "skip"
        if self.hero == "M":
            return self.mage_act(alive, front, mons)
        return self.warrior_act(alive, front)

    def do_retreat(self, alive, mons):
        h = self.h
        # walk to the exit: BEHIND turns; ranged shooters in line shoot; adjacent escorts follow (fought next)
        for _ in range(max(1, self.behind)):
            self.adv(1)
            for m in alive:
                row = self.mrow(m)
                if m.hp > 0 and row and m.cd <= 0 and self.in_rng(m.x, row[0]) and self.in_line(m):
                    m.cd = row[1]
                    self.ranged_hit(m, row)
                else:
                    m.cd -= 1
        followers = [m for m in alive if not m.boss and m.x <= self.P["ESCORT_FOLLOW_GAP"]]
        if followers:
            fl = followers
            for m in fl:
                if m in mons:
                    mons.remove(m)
            saved = mons[:]
            self.setup_geometry(fl, False)
            for m in fl:
                m.x = 1 + fl.index(m) * 2
                m.climb = 0
            tmp = list(fl)
            res = self.fight(tmp, boss_room=False)
            # if the followers were not cleared they stay with the hero's retreat (accept)
            mons[:] = saved
        return "retreat"

    def min_cost(self):
        h = self.h
        c = [self.D.rank[s][0]["mp"] for s in SPELLS if h.ranks[s]]
        return min(c) if c else 99

    # --- Warrior
    def warrior_act(self, alive, front):
        D, P, h, pol = self.D, self.P, self.h, self.pol
        gap = front.x
        k = front.k
        if h.fearT and gap <= 1:
            # cannot melee: step back or throw
            if gap <= 1 and (h.daggers or (h.bow and h.arrows)):
                return self.warrior_ranged(front, gap)
            return "skip"
        if gap <= 2 and self.try_jump(alive, front):
            return "jump"
        # kite slow monsters
        if gap < 3 and k["period"] > 1 and self.rr() < pol["kite"] and self.hx > -self.behind and gap > 1:
            self.hx -= 1
            for m in alive:
                m.x += 1
            return "skip"
        if gap >= 2:
            if gap >= 3 and (h.daggers or (h.bow and h.arrows)) and gap <= 14:
                return self.warrior_ranged(front, gap)
            if gap > 1:
                # advance toward the monster (monsters approach as well): wait if they come, else step
                if front.k["id"] in D.rows or front.k["id"] == D.id("ARCHMAGE") or front.k["period"] > 1 or front.climb:
                    self.hero_step(alive)
                    return "skip"
                # same-speed walker will close: wait (free ranged opportunities used above)
                return "skip" if gap > 2 else "skip"
        # melee reach
        adj = [m for m in alive if m.x <= 1 and self.in_line(m)]
        r = h.ranks
        if r["Whirl"] and len(adj) >= 2 and h.mp >= D.rank["Whirl"][0]["mp"] and not h.gear_ban:
            return self.whirlwind(adj)
        if r["Power"] and not h.gear_ban and gap <= 1 and (front.hp > 2 * ((h.wdie + 1) / 2 + h.wbonus)) and h.mp >= D.rank["Power"][0]["mp"] and not front.k["res"][PHYS] == 2:
            return self.power_strike(front)
        return self.melee(front)

    def hero_step(self, alive):
        # step toward the nearest monster (same-speed approach; the gap shrinks by one)
        f = min(alive, key=lambda m: m.x)
        if f.k["id"] == self.D.id("ARCHMAGE"):
            if f.x > 1:
                f.x -= 1
        else:
            f.x = max(1, f.x - 1)
            for m in alive:
                if m is not f:
                    m.x = max(1, m.x - 0)

    def warrior_ranged(self, front, gap):
        D, P, h = self.D, self.P, self.h
        use_bow = h.bow and h.arrows and gap <= D.ammo[1]["range"]
        if use_bow:
            row, ammo = D.ammo[1], "arr"
            h.arrows -= 1
        elif h.daggers and gap <= D.ammo[0]["range"]:
            row, ammo = D.ammo[0], "dag"
            h.daggers -= 1
        else:
            return self.hero_wait()
        atk = self.hero_atk() + (1 if ammo == "dag" else 0)
        ev = 0 if front.hold else front.k["eva"]
        pr = (11 + atk - ev) / 20.0
        hit = self.rr() < max(0.0, min(1.0, pr))
        if hit:
            roll = self.rng.randint(1, row["die"]) + row["bonus"]
            self.strike(front, PHYS, roll, melee=True)
            if ammo == "dag" and self.rr() >= 0.25:
                self.dag_floor = getattr(self, "dag_floor", 0) + 1
        else:
            if ammo == "dag" and self.rr() >= 0.25:
                self.dag_floor = getattr(self, "dag_floor", 0) + 1
            if ammo == "arr" and self.rr() < 0.5:
                self.arr_floor = getattr(self, "arr_floor", 0) + 1
        return "act"

    def hero_wait(self):
        return "skip"

    def melee(self, tgt, mult=1.0, hitbonus=0, dmgbonus=0, stun=0, ign=False):
        h = self.h
        ev = 0 if tgt.hold else tgt.k["eva"]
        pr = (11 + self.hero_atk() + hitbonus - ev) / 20.0
        if self.rr() >= max(0.0, min(1.0, pr)):
            return "act"
        pk = PARRY.get(tgt.k["name"], 0)
        k = tgt.k
        for nm, p in (("SKEL_GUARD", 1 / 4), ("SKEL_KNIGHT", 1 / 3), ("DKNIGHT", 1 / 3)):
            if tgt.kind == self.D.id(nm):
                if self.rr() < p:
                    return "act"
        roll = self.rng.randint(1, h.wdie) + h.wbonus + dmgbonus
        if self.weak_active():
            roll = max(1, roll - 1)
        roll = int(roll * mult)
        before = tgt.hp
        res = self.strike(tgt, PHYS, roll, melee=True, ign=ign)
        if stun and tgt.hp > 0 and res not in ("I", "X", "R"):
            self.try_hold(tgt, stun, "stun")
        return "act"

    def power_strike(self, tgt):
        D, h = self.D, self.h
        rk = h.ranks["Power"]
        costs = [D.rank["Power"][i]["mp"] for i in range(3)]
        rank = self.downcast(costs, rk)
        h.mp -= costs[rank - 1]
        row = D.rank["Power"][rank - 1]
        mult = (2.0, 2.5, 3.0)[row["die"] if row["die"] < 3 else 2]
        return self.melee(tgt, mult=mult, hitbonus=2 + row["bounces"], stun=row["effect"], ign=bool(self.P["PS_R"]))

    def whirlwind(self, adj):
        D, h = self.D, self.h
        costs = [D.rank["Whirl"][i]["mp"] for i in range(3)]
        rank = self.downcast(costs, h.ranks["Whirl"])
        h.mp -= costs[rank - 1]
        row = D.rank["Whirl"][rank - 1]
        for m in adj:
            self.melee(m, hitbonus=row["effect"], dmgbonus=row["bonus"])
        return "act"

    def downcast(self, costs, rank):
        rank = max(rank, 1)
        while rank > 1 and costs[rank - 1] > self.h.mp:
            rank -= 1
        return rank

    def try_jump(self, alive, front):
        """2.4 jump-away: +JUMP_COLS between hero and every monster (hero jumps toward the room edge), 1 turn,
        2 FOOD, never two turns in a row, not when Weak / held / a shooter is the front.  Needs JUMP_COLS of
        free room behind (the 1-D BEHIND budget; kiting steps and earlier jumps use it up).  Returns True if jumped."""
        P, h, D = self.P, self.h, self.D
        if not P["JUMP"] or self.jumped or h.hold or self.weak_active():
            return False
        if front.x > 2 or front.k["id"] in D.rows or front.k["id"] == D.id("ARCHMAGE"):
            return False
        if self.behind + self.hx < P["JUMP_COLS"]:
            return False
        if self.rr() >= self.pol["kite"]:
            return False
        if self.hero == "M":
            if h.mp < self.min_cost():
                return False
        elif not (h.daggers >= 2 or (h.bow and h.arrows >= 2)):
            return False
        self.hx -= P["JUMP_COLS"]
        for m in alive:
            m.x += P["JUMP_COLS"]
        self.wall += P["JUMP_COLS"]
        h.food = max(0, h.food - P["JUMP_FOOD"])
        self.stat_add("jumps")
        return True

    # --- Mage
    def mage_act(self, alive, front, mons):
        D, P, h, pol = self.D, self.P, self.h, self.pol
        gap = front.x
        if gap <= 2 and self.try_jump(alive, front):
            return "jump"
        # kite: step back at gap < 3 vs slow monsters when room behind
        if gap < 3 and front.k["period"] > 1 and gap > 1 and self.rr() < pol["kite"] and self.hx > -self.behind:
            self.hx -= 1
            for m in alive:
                m.x += 1
            return "skip"
        if P["FEAR_CAST"] and h.fearT:
            return "skip"      # FEAR-CAST: no spell, and fear_chk also stops the staff melee (waits it out; heals / Cure ran above)
        best = None
        for s in SPELLS:
            rk = h.ranks[s]
            if not rk or h.gear_ban:
                continue
            costs = [D.rank[s][i]["mp"] for i in range(3)]
            if h.mp < costs[0]:
                continue
            rank = self.downcast(costs, rk)
            row = D.rank[s][rank - 1]
            if gap > row["range"]:
                continue
            ty = {"Spark": SHOCK, "Firebolt": FIRE, "Frost": COLD, "Drain": DRAIN, "Lightning": SHOCK}[s]
            if front.k["res"][ty] in (2, 3):
                continue
            if s == "Lightning" and any(m.k["res"][ty] == 3 for m in alive if self.in_line(m)):
                continue          # a piercing bolt reaching a reflector comes back at the caster
            # self-risk: a bouncing projectile that can come back
            if row["bounces"] > 0 and 2 * self.wall <= row["range"] + 2:
                if h.hp < h.maxhp * 0.9 or row["die"] + row["bonus"] + h.spellbonus >= h.hp:
                    continue
            avg = (row["die"] + 1) / 2 + row["bonus"] + h.spellbonus
            r = front.k["res"][ty]
            avg = avg * 2 if r == 4 else (max(1, avg // 2) if r == 1 else avg)
            extra = 0
            if s == "Firebolt":
                extra = 1.0 * (len([m for m in alive if abs(m.x - front.x) <= 1 and m is not front]))
            if s == "Lightning":
                extra = avg * 0.7 * (len([m for m in alive if m is not front and m.x > front.x]) > 0)
            if s == "Drain":
                extra = avg * 0.3 * (h.hp < h.maxhp * 0.6)
            sc = (min(avg, front.hp + 2) + extra) / costs[rank - 1]
            if best is None or sc > best[0]:
                best = (sc, s, rank, row)
        if best:
            return self.cast(best[1], best[2], best[3], alive, front)
        if gap <= 1:
            return self.melee(front)
        # no spell, not adjacent: let it come (hero waits) unless slow monster
        return "skip"

    def cast(self, s, rank, row, alive, front):
        D, h = self.D, self.h
        cost = D.rank[s][rank - 1]["mp"]
        h.mp -= cost
        self.mage_casts[s] += 1
        ty = {"Spark": SHOCK, "Firebolt": FIRE, "Frost": COLD, "Drain": DRAIN, "Lightning": SHOCK}[s]
        pierce = s == "Lightning"
        burst = s == "Firebolt"
        bounces = row["bounces"]
        x, d = 0, 1
        rng_left = row["range"]
        revs = 0
        struck = set()
        hit_any = False
        spare = bool(row["effect"] & 0x80)
        bdie = row["effect"] & 15
        targets = [m for m in alive if self.in_line(m)]
        while rng_left > 0 and revs <= 4:
            x += d
            rng_left -= 1
            if d == 1 and x >= self.wall:
                x = self.wall
                if bounces > 0:
                    bounces -= 1
                    d = -1
                    revs += 1
                    struck = set()
                    continue
                break
            if d == -1 and x <= 0:
                self.self_hit(s, ty, row, rank)
                break
            body = None
            for m in targets:
                if m.hp > 0 and m.x == x and id(m) not in struck:
                    body = m
                    break
            if body is None:
                continue
            struck.add(id(body))
            roll = self.rng.randint(1, row["die"]) + row["bonus"] + h.spellbonus
            res = body.k["res"][ty]
            if res == 3:
                d = -d
                revs += 1
                struck = set()
                continue
            dealt = self.strike(body, ty, roll, melee=False, spell=s, row=row, rank=rank)
            hit_any = True
            if burst:
                ix = x
                if bdie:
                    for m in targets:
                        if m is not body and m.hp > 0 and abs(m.x - ix) <= 1:
                            br = self.rng.randint(1, bdie & 7 if bdie & 7 else 4)
                            br2, _ = self.apply_res(m, FIRE, br)
                            self.strike_raw(m, FIRE, br2)
                    if not spare and ix <= 2:
                        br = self.rng.randint(1, bdie & 7 if bdie & 7 else 4)
                        self.dmg_hero(self.hero_res(FIRE, br), "own Firebolt", "self")
                if body.hp > 0 and abs(body.x - ix) <= 1:
                    pass
            if not pierce:
                break
        return "act"

    def self_hit(self, s, ty, row, rank):
        h = self.h
        roll = self.rng.randint(1, row["die"]) + row["bonus"] + h.spellbonus
        roll = self.hero_res(ty, roll)
        self.stat_add("self_hits")
        if s == "Frost":
            if not h.hold:
                h.hold, h.holdkind = 1, "frozen"
        self.dmg_hero(roll, "own " + s, "self")

    def strike_raw(self, m, ty, dmg):
        if dmg <= 0 or m.hp <= 0:
            return
        m.hp -= dmg
        if ty == FIRE and m.hold and m.holdkind == "frozen":
            m.hold = 0
        if m.hold and m.holdkind == "sleep":
            m.hold = 0
        if m.hp <= 0:
            self.kill(m)

    def strike(self, m, ty, roll, melee, spell=None, row=None, rank=0, ign=False):
        """Apply a direct strike; returns the response letter."""
        if melee:
            roll_r, resp = self.apply_res(m, ty, roll, ign)
            if resp in ("I", "X"):
                return resp
            dmg = max(1, roll_r - m.df)
        else:
            dmg, resp = self.apply_res(m, ty, roll)
            if resp in ("I", "X"):
                return resp
        dealt = min(dmg, m.hp)
        if spell:
            self.mage_dmg[spell] += dealt
            self.overkill[0] += dmg - dealt
            self.overkill[1] += dmg
        m.hp -= dmg
        if ty == FIRE and m.hold and m.holdkind == "frozen":
            m.hold = 0
        if m.hold and m.holdkind == "sleep":
            m.hold = 0
        if spell == "Drain":
            h = self.h
            h.hp = min(h.maxhp, h.hp + dealt)
        if m.hp > 0 and spell and row:
            if spell == "Frost":
                tn = row["effect"] & 15
                self.try_hold(m, tn, "frozen", resp)
            elif spell == "Spark":
                ch, tn = row["effect"] >> 4, row["effect"] & 15
                if ch and self.rr() < 1.0 / ch and not (m.k["imm"] & 4):
                    tn2 = tn // 2 if (m.boss or resp == "R") else tn
                    if tn2:
                        m.conf = max(m.conf, tn2)
        if m.hp > 0 and m.kind == self.D.id("RABBIT_RAT") and not m.bred and self.rr() < 0.25 and melee is not None:
            m.bred = True
        if m.hp <= 0:
            self.kill(m)
        return resp

    def try_hold(self, m, turns, kind, resp="N"):
        if m.hold:
            return
        if m.boss:
            turns //= 2
        if resp == "R":
            turns //= 2
        if turns > 0 and not (kind == "sleep" and (m.k["imm"] & 1)):
            m.hold, m.holdkind = turns, kind

    def kill(self, m):
        h = self.h
        self.gain_xp(m)
        # drops (food / arrows / mana)
        base = self.D.tier_base.get(m.kind, m.kind)
        dr = {self.D.id("RAT"): (30, 4), self.D.id("GOBLIN"): (15, 4), self.D.id("ORC"): (40, 3)}.get(base)
        if dr and not m.resp and not m.summoned:
            tier = 1 + (m.kind != base) + (m.kind in [t[1] for t in self.D.tiers.values() if t[1]])
            if self.rr() < tier / dr[1]:
                h.bagfood.append(dr[0])
        if base == self.D.id("NECRO") and not m.resp and self.rr() < 1 / 3:
            h.mana += 1
        if self.stats is not None:
            self.stat_add("kills")


def BOSS_LBL(m, depth):
    if m.boss:
        return BOSS_NAME[depth]
    return m.k["name"]


# ----------------------------------------------------------------------------------------------
# Batch runner / reports
# ----------------------------------------------------------------------------------------------
def run_batch(D, hero, policy, runs, seed, first=0):
    res = dict(n=0, wins=0, death_depth=[0] * 9, killers={}, dk={}, entry=[[0, 0.0, 0.0, 0.0] for _ in range(9)],
               spell_dmg={s: 0.0 for s in SPELLS}, spell_casts={s: 0 for s in SPELLS}, stalls=0, causes={},
               turns=0, overkill=[0.0, 0.0], lvl_entry=[0.0] * 9, reached=[0] * 9)
    for i in range(first, first + runs):
        rng = random.Random("%s/%s/%s/%d" % (seed, hero, policy, i))
        g = Game(D, hero, policy, rng)
        won, depth, killer, cause = g.play()
        res["n"] += 1
        res["turns"] += g.t
        for j, (hp, mp, food, lvl) in enumerate(g.entry):
            res["reached"][j + 1] += 1
            res["entry"][j + 1][1] += hp
            res["entry"][j + 1][2] += lvl
            res["entry"][j + 1][3] += food
        if won:
            res["wins"] += 1
        else:
            res["death_depth"][depth] += 1
            res["killers"][killer] = res["killers"].get(killer, 0) + 1
            kk = "D%d %s" % (depth, killer)
            res["dk"][kk] = res["dk"].get(kk, 0) + 1
            res["causes"][cause] = res["causes"].get(cause, 0) + 1
        for s in SPELLS:
            res["spell_dmg"][s] += g.mage_dmg[s]
            res["spell_casts"][s] += g.mage_casts[s]
        res["overkill"][0] += g.overkill[0]
        res["overkill"][1] += g.overkill[1]
    return res


def merge_res(a, b):
    out = dict(a)
    for k in ("n", "wins", "turns", "stalls"):
        out[k] = a[k] + b[k]
    for k in ("death_depth", "lvl_entry", "reached"):
        out[k] = [x + y for x, y in zip(a[k], b[k])]
    out["entry"] = [[x[0] + y[0], x[1] + y[1], x[2] + y[2], x[3] + y[3]] for x, y in zip(a["entry"], b["entry"])]
    for k in ("killers", "causes", "dk"):
        d = dict(a[k])
        for kk, v in b[k].items():
            d[kk] = d.get(kk, 0) + v
        out[k] = d
    for k in ("spell_dmg", "spell_casts"):
        out[k] = {s: a[k][s] + b[k][s] for s in SPELLS}
    out["overkill"] = [a["overkill"][0] + b["overkill"][0], a["overkill"][1] + b["overkill"][1]]
    return out


def _worker(args):
    ov, hero, policy, runs, seed, first = args
    D = Data(ov)
    return run_batch(D, hero, policy, runs, seed, first)


def run_cell(ov, hero, policy, runs, seed, jobs):
    if jobs <= 1:
        return _worker((ov, hero, policy, runs, seed, 0))
    import multiprocessing as mp
    per = runs // jobs
    chunks = []
    first = 0
    for j in range(jobs):
        n = per + (runs - per * jobs if j == jobs - 1 else 0)
        chunks.append((ov, hero, policy, n, seed, first))
        first += n
    with mp.Pool(jobs) as pool:
        parts = pool.map(_worker, chunks)
    out = parts[0]
    for p in parts[1:]:
        out = merge_res(out, p)
    return out


def summarize(r):
    n = r["n"]
    p, lo, hi = wilson(r["wins"], n)
    surv = []
    alive = n
    for d in range(1, 9):
        surv.append(r["reached"][d] / n if n else 0)
    return dict(n=n, win=p, lo=lo, hi=hi, surv=surv)


def report(name, results, runs):
    lines = ["== %s ==" % name]
    lines.append("hero policy    win%%   95%% CI          survive-at-entry D2..D8 / deaths%%")
    gap = {}
    for (hero, pol), r in results.items():
        s = summarize(r)
        gap.setdefault(pol, {})[hero] = s["win"]
        tot = max(1, sum(r["death_depth"]))
        dd = " ".join("%2d" % round(100 * r["death_depth"][d] / tot) for d in range(1, 9))
        sv = " ".join("%3d" % round(100 * (r["reached"][d] / r["n"])) for d in range(2, 9))
        lines.append("%-4s %-9s %5.1f  [%4.1f,%4.1f]  %s | dth %s" % (hero, pol, 100 * s["win"], 100 * s["lo"], 100 * s["hi"], sv, dd))
    for hero_pol in results:
        pass
    lines.append("-- mean LVL / FOOD at depth entry D1..D8 (expected LVL = depth) --")
    for (hero, pol), r in results.items():
        lines.append("%s/%s: %s" % (hero, pol, "  ".join("%.1f/%d" % (r["entry"][d][2] / max(1, r["reached"][d]), r["entry"][d][3] / max(1, r["reached"][d])) for d in range(1, 9))))
    lines.append("-- top killers (share of deaths) --")
    for (hero, pol), r in results.items():
        tot = max(1, sum(r["killers"].values()))
        top = sorted(r["killers"].items(), key=lambda kv: -kv[1])[:5]
        lines.append("%s/%s: %s" % (hero, pol, ", ".join("%s %d%%" % (k, round(100 * v / tot)) for k, v in top)))
    lines.append("-- top depth x killer (share of deaths) --")
    for (hero, pol), r in results.items():
        tot = max(1, sum(r["killers"].values()))
        top = sorted(r.get("dk", {}).items(), key=lambda kv: -kv[1])[:7]
        lines.append("%s/%s: %s" % (hero, pol, ", ".join("%s %d%%" % (k, round(100 * v / tot)) for k, v in top)))
    lines.append("-- Warrior-Mage gap (tolerance 5 pp average, 8 pp cautious/reckless) --")
    for pol, d in gap.items():
        if "W" in d and "M" in d:
            g = 100 * (d["W"] - d["M"])
            tol = 5 if pol == "average" else 8
            lines.append("%-9s W %.1f  M %.1f  gap %+.1f pp  %s" % (pol, 100 * d["W"], 100 * d["M"], g, "OK" if abs(g) <= tol else "OVER"))
    mage = [(k, r) for k, r in results.items() if k[0] == "M"]
    for (hero, pol), r in mage:
        tot = sum(r["spell_dmg"].values()) or 1
        lines.append("M/%s spell dmg share: %s overkill %.0f%%" % (pol, " ".join("%s %d%%" % (s, round(100 * r["spell_dmg"][s] / tot)) for s in SPELLS),
                                                                   100 * r["overkill"][0] / max(1, r["overkill"][1])))
    return "\n".join(lines)


def to_json(name, results):
    out = {}
    for (hero, pol), r in results.items():
        s = summarize(r)
        out["%s/%s" % (hero, pol)] = dict(n=r["n"], win=s["win"], ci95=[s["lo"], s["hi"]], death_depth=r["death_depth"],
                                          killers=r["killers"], dk=r["dk"], causes=r["causes"], reached=r["reached"],
                                          mean_turns=r["turns"] / max(1, r["n"]), spell_dmg=r["spell_dmg"], spell_casts=r["spell_casts"])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="BAL-1b balance Monte Carlo")
    ap.add_argument("--hero", default="both", choices=["W", "M", "both"])
    ap.add_argument("--policy", default="all", choices=list(POLICIES) + ["all"])
    ap.add_argument("--runs", type=int, default=10000)
    ap.add_argument("--seed", default="1")
    ap.add_argument("--overrides", action="append", help="JSON override file (see tools/balance_optionA.json); repeatable, merged in order")
    ap.add_argument("--set", action="append", dest="sets", help="key=val override (repeatable)")
    ap.add_argument("--compare", help="override JSON: run baseline AND the override, print both")
    ap.add_argument("--json", help="write results JSON here")
    ap.add_argument("--csv", help="write a flat CSV here")
    ap.add_argument("--jobs", type=int, default=1, help="processes (deterministic per chunk layout)")
    a = ap.parse_args(argv)
    heroes = ["W", "M"] if a.hero == "both" else [a.hero]
    pols = list(POLICIES) if a.policy == "all" else [a.policy]
    ov = {}
    for f in a.overrides or []:
        ov = merge(ov, json.load(open(f)))
    if a.sets:
        ov = merge(ov, parse_set(a.sets))
    configs = [("baseline" if not ov and not a.compare else "run", ov)]
    if a.compare:
        configs = [("baseline" + (" +sets" if ov else ""), ov), ("override:" + os.path.basename(a.compare), merge(ov, json.load(open(a.compare))))]
    allj, csvrows = {}, []
    for name, o in configs:
        t0 = time.time()
        res = {}
        for hero in heroes:
            for pol in pols:
                res[(hero, pol)] = run_cell(o, hero, pol, a.runs, a.seed, a.jobs)
        print(report(name, res, a.runs))
        print("(%d runs/cell, %.1f s)\n" % (a.runs, time.time() - t0))
        allj[name] = to_json(name, res)
        for (hero, pol), r in res.items():
            s = summarize(r)
            csvrows.append((name, hero, pol, r["n"], s["win"], s["lo"], s["hi"]))
    if a.json:
        json.dump(allj, open(a.json, "w"), indent=1)
    if a.csv:
        with open(a.csv, "w") as f:
            f.write("config,hero,policy,n,win,ci_lo,ci_hi\n")
            for row in csvrows:
                f.write(",".join(str(x) for x in row) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
