#!/usr/bin/env python3
"""D3-1 combat-table check (no emulator). Reads the bank-3 block out of
build/wazhack.tap (6th tape block: BASIC hdr/data, CODE hdr/data, bank-1
headless, bank-3 headless at $C000), locates tables via build/wazhack.sym and
compares every byte with a Python transcription written straight from
docs/design/game.md (§4.1, §5, §6.0-6.3, §9.1, §11.4). Build first.
Run: python3 tests/combat_tables.py"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = 0xC000
R6BLK = b""


def load():
    sym = {}
    for ln in open(os.path.join(REPO, "build/wazhack.sym")):
        m = re.match(r"(\S+): EQU 0x([0-9A-Fa-f]+)", ln)
        if m:
            sym[m.group(1)] = int(m.group(2), 16)
    tap = open(os.path.join(REPO, "build/wazhack.tap"), "rb").read()
    blocks, i = [], 0
    while i < len(tap):
        n = tap[i] | tap[i + 1] << 8
        blocks.append(tap[i + 2:i + 2 + n])
        i += 2 + n
    b3 = blocks[7]                      # +2 since b918cc5: loading-screen header + SCREEN$ blocks precede the code header
    assert b3[0] == 0xFF, "bank-3 block flag"
    global R6BLK
    R6BLK = blocks[13]                 # TAPE_BLOCKS order (main.asm): the R6 region, at R6_ADDR (3F-T5: drop_tab lives there)
    assert R6BLK[0] == 0xFF, "R6 block flag"
    R6BLK = R6BLK[1:-1]
    return sym, b3[1:-1]


# ---- independent transcription (game.md text) --------------------------------
# damage types order §6.0: PHYS FIRE COLD SHOCK DRAIN DARK
TYPES = ["PHYS", "FIRE", "COLD", "SHOCK", "DRAIN", "DARK"]
RESP = {"N": 0, "R": 1, "I": 2, "X": 3}
SLEEP, STUN, CONFUSE, FEAR, POISON = 1, 2, 4, 8, 16

# kind id -> (name, {type: R/I/X/W}, imm mask, KXP) ; ids from defs.asm
KINDS = {
    0: ("Knight", {}, 0, 0),
    1: ("Wizard", {}, 0, 0),
    3: ("Skeleton", {"COLD": "I", "DRAIN": "I", "DARK": "I"}, SLEEP | POISON, 6),
    4: ("Goblin", {}, 0, 3),
    5: ("Ghost", {"PHYS": "R", "COLD": "I", "SHOCK": "X", "DRAIN": "I", "DARK": "I"}, SLEEP | POISON, 6),
    6: ("Rat", {}, 0, 2),
    7: ("Bat", {"SHOCK": "W"}, 0, 2),
    8: ("Slime", {"PHYS": "R", "FIRE": "W"}, SLEEP | CONFUSE | FEAR, 3),
}


# 3F-T3 rows (game.md §9.1 resistances / immunity set / KXP / DEF, §9.6 tiers; ids = defs.asm K_*)
BOSS = 0x80
UNDEAD = SLEEP | POISON
SK_RES = {"COLD": "I", "DRAIN": "I", "DARK": "I"}
KINDS.update({
    9: ("Spider", {"FIRE": "W"}, 0, 4),
    10: ("Vampire", {"FIRE": "W", "COLD": "I", "DRAIN": "I", "DARK": "I"}, UNDEAD, 9),
    2: ("Vampire bat form", {"FIRE": "W", "COLD": "I", "DRAIN": "I", "DARK": "I"}, UNDEAD, 9),   # 3F-T9 K_VBAT: the Vampire's row, PHYS bite
    11: ("Orc", {"FIRE": "R"}, 0, 9),
    12: ("Skeleton Archer", SK_RES, UNDEAD, 7),
    13: ("Mummy", {"PHYS": "R", "FIRE": "W", "COLD": "I", "DRAIN": "I", "DARK": "I"}, UNDEAD, 12),
    14: ("Necromancer", {"COLD": "R", "DRAIN": "I", "DARK": "I"}, 0, 10),
    15: ("Ogre Warlord", {"PHYS": "R", "COLD": "R", "SHOCK": "W"}, BOSS, 60),
    16: ("Death Knight", {"FIRE": "X", "COLD": "I", "SHOCK": "W", "DRAIN": "I", "DARK": "I"}, BOSS, 90),
    17: ("Archmage", {"COLD": "X", "SHOCK": "X", "DRAIN": "I", "DARK": "R"}, BOSS, 0),
    18: ("Giant Rat", {}, 0, 3),
    19: ("Rabbit Rat", {}, 0, 4),
    20: ("Screech Bat", {"SHOCK": "W"}, 0, 3),
    21: ("Goblin Slinger", {}, 0, 4),
    22: ("Black Widow", {"FIRE": "W"}, 0, 6),
    23: ("Skeleton Guard", SK_RES, UNDEAD, 9),
    24: ("Skeleton Knight", SK_RES, UNDEAD, 12),
    25: ("Poltergeist", {"PHYS": "R", "COLD": "I", "SHOCK": "X", "DRAIN": "I", "DARK": "I"}, UNDEAD, 9),
    26: ("Orc Berserker", {"FIRE": "R"}, FEAR, 13),          # FEAR-immune extra (§9.6)
    27: ("Orc Bouncer", {"FIRE": "R"}, 0, 18),
    28: ("Skeleton Sniper", SK_RES, UNDEAD, 10),
    29: ("Bone Caller", {"COLD": "R", "DRAIN": "I", "DARK": "I"}, 0, 15),
})
# monster DEF (KX_DEF): the §9.1 / §9.6 DEF column (D3-1: Skeleton and Slime 1 too; the other 3D rows 0)
DEF3F = {3: 1, 8: 1, 11: 1, 13: 2, 15: 2, 16: 3, 17: 1, 23: 2, 24: 3, 26: 1, 27: 2}


def kx_row(res, imm, xp, d=0):
    b = [0, 0, 0]
    for t, r in res.items():
        i = TYPES.index(t)
        if r == "W":
            b[2] |= 1 << i
        else:
            b[i // 4] |= RESP[r] << (2 * (i % 4))
    return b + [imm, xp, d, 0, 0]   # KX_MELEE 2 B (3F-T2: below)


# 3F-T2: KX_MELEE (was combat3.asm kx_melee) = the kind's melee hit: dty |
# efx << 4, chance << 4 | turns (game.md §9.1: PHYS everywhere, the Ghost's 1d4
# DRAIN touch, 1 in 4 -> CONFUSED 4). EFX ids: defs (EFX_CONFUSED).
# 3F-T3 on-hit rows (POISON turns are HALF the turns, PSN_*; chance = 1 in N, 0 = always):
#   id -> (dty, efx, chance, turns)
MELEE3F = {
    9: ("PHYS", "POISON", 0, 6),                  # Spider bite POISON 12
    10: ("DRAIN|HEAL", None, 0, 0),               # Vampire: the drain bite heals it
    13: ("PHYS", "WEAK", 3, 12),                  # Mummy curse 1 in 3 -> WEAK 12
    18: ("PHYS", "POISON", 4, 6),                 # Giant Rat 1 in 4 -> POISON 12
    20: ("PHYS", "CONFUSED", 4, 2),               # Screech Bat 1 in 4 -> CONFUSED 2
    22: ("PHYS", "POISON", 0, 12),                # Black Widow POISON 24
    24: ("PHYS", "STUNNED", 4, 1),                # Skeleton Knight 1 in 4 -> STUNNED 1
    25: ("DRAIN", "FEAR", 3, 3),                  # Poltergeist touch 1 in 3 -> FEAR 3
    27: ("PHYS", "STUNNED", 3, 1),                # Orc Bouncer 1 in 3 -> STUNNED 1
}


def kx_melee(k, sym):
    if k == 5:
        return [TYPES.index("DRAIN") | sym["EFX_CONFUSED"] << sym["DH_EFX_SHIFT"], 4 << 4 | 4]
    if k in MELEE3F:
        dty, efx, ch, tn = MELEE3F[k]
        v = TYPES.index("DRAIN") if dty.startswith("DRAIN") else 0
        if dty.endswith("HEAL"):
            v |= 0x80
        if efx:
            v |= sym["EFX_" + efx] << sym["DH_EFX_SHIFT"]
        return [v, ch << 4 | tn]
    return [TYPES.index("PHYS"), 0]


XP_NEXT = [40, 100, 200, 340, 500, 700, 920, 1150]          # levels 2..9
LEVELUP = [(4, 1), (3, 2)]                                   # Warrior, Mage (HP, MP)
STEPS = {4: (1, 0), 6: (0, 1), 8: (1, 0)}                    # level -> (atk, eva)

# rank table, §5: (MP, range, die, bonus, bounces, effect) per rank 1..3, cumulative
# effect: status = chance<<4 | turns; Firebolt = burst die (|$80 spare); Whirlwind = to-hit
# RANK1 (game.md §5 rev 6): MP per rank 2/4/6, 3/5/8 x3, 5/8/12, 3/5/7, 4/7/10 and the damage columns.
# Power Strike: die = multiplier code (0/1/2 = x2 / x2.5 / x3), bounces = extra to-hit (+2 base in ab_def).
RANKS = {
    "Spark":     [(2, 6, 4, 1, 0, 0x44), (4, 8, 8, 2, 0, 0x44), (6, 8, 8, 4, 0, 0x24)],
    "Firebolt":  [(3, 12, 8, 2, 0, 4), (5, 12, 8, 5, 0, 6), (8, 12, 10, 7, 0, 0x86)],
    "Frost":     [(3, 12, 6, 0, 1, 2), (5, 12, 6, 1, 2, 3), (8, 12, 6, 3, 2, 4)],
    "Drain":     [(3, 5, 6, 1, 0, 0), (5, 8, 6, 3, 0, 0), (8, 8, 8, 5, 0, 0)],
    "Lightning": [(5, 28, 8, 3, 2, 0), (8, 28, 8, 6, 2, 0), (12, 28, 8, 8, 3, 0)],
    "Power":     [(3, 0, 0, 0, 0, 1), (5, 0, 1, 0, 1, 1), (7, 0, 2, 0, 2, 2)],
    "Whirl":     [(4, 0, 0, 1, 0, 0), (7, 0, 0, 3, 0, 0), (10, 0, 0, 4, 0, 2)],
}
AMMO = [(0, 6, 4, 2, 0, 0), (0, 14, 6, 1, 0, 0)]             # dagger r6 1d4+2, bow r14 1d6+1

# ab_def fids (D3-4, game.md §6.1-6.3): projectile 1/2, impact 1/2 by frame name
# (None = FXF_NONE $FF: melee has no projectile, the dagger no impact sprite);
# and the class whose FX kind must contain them (Whirlwind: the Warrior's).
FIDS = [
    (("spark_fly1", "spark_fly2", "spark_fizz1", "spark_fizz2"), "FXM"),
    (("firebolt_fly1", "firebolt_fly2", "firebolt_burst1", "firebolt_burst2"), "FXM"),
    (("frost_fly", "frost_fly", "frost_crack", "frost_crack"), "FXM"),
    (("drain_fly1", "drain_fly2", "drain_hit", "drain_hit"), "FXM"),
    (("lightning_fly1", "lightning_fly2", "lightning_flash", "lightning_flash"), "FXM"),
    ((None, None, "power_burst", "power_burst"), "FXW"),
    ((None, None, "spark_fizz1", "spark_fizz2"), "FXW"),
    (("dagger_spin1", "dagger_spin2", None, None), "FXW"),
    (("arrow_fly1", "arrow_fly2", "arrow_hit", "arrow_hit"), "FXW"),
]

# ab_def rows: dty, att1, att2, speed, flags, hit
SPELL, PIERCE, BURST, HEAL, DMGX2, AOE, MELEE, AMMOF = 1, 2, 4, 8, 16, 32, 64, 128
DEFS = [
    (3, 0x43, 0x43, 8, SPELL, 0),                 # Spark SHOCK
    (1, 0x46, 0x42, 8, SPELL | BURST, 0),         # Firebolt FIRE yellow/red
    (2, 0x45, 0x45, 8, SPELL, 0),                 # Frost COLD
    (4, 0x43, 0x43, 8, SPELL | HEAL, 0),          # Drain DRAIN
    (3, 0x47, 0x47, 16, SPELL | PIERCE, 0),       # Lightning SHOCK 16 px/tick
    (0, 0, 0, 0, MELEE | DMGX2, 2),               # Power Strike to-hit +2
    (0, 0, 0, 0, MELEE | AOE, 0),                 # Whirlwind
    (0, 0x47, 0x47, 8, AMMOF, 1),                 # dagger atk+1
    (0, 0x07, 0x07, 8, AMMOF, 0),                 # bow
]


def main():
    sym, m = load()
    fails = []

    def at(name):
        return sym[name] - BASE

    def chk(what, got, want):
        if list(got) != list(want):
            fails.append(f"{what}: got {list(got)} want {list(want)}")

    chk("kx_tab base", [sym["kx_tab"]], [BASE])
    kx = at("kx_tab")
    for k in range(32):
        want = kx_row(*KINDS[k][1:], DEF3F.get(k, 0))[:6] + kx_melee(k, sym) if k in KINDS else [0] * 8
        chk(f"kx[{k}]", m[kx + 8 * k:kx + 8 * k + 8], want)
    chk("kx_tab length (dg_bad follows, L-RELIEF)", [sym["dg_bad"] - sym["kx_tab"]], [256])

    # D3-9b: XP_NEXT is ONE table, bank-2 xpn_tab (read from the .sna: 27-B
    # header, then RAM $4000..$FFFF with bank 2 at $8000); the bank-3 copy, the
    # bank-1 xp_next and the bank-3 level-up tables are gone (xp7.asm immediates,
    # checked at runtime by tests/xp.py).
    sna = open(os.path.join(REPO, "build/wazhack.sna"), "rb").read()
    x = 27 + sym["xpn_tab"] - 0x4000
    chk("xpn_tab in bank 2", [0x8000 <= sym["xpn_tab"] < 0xC000], [True])
    chk("xp_next", [sna[x + 2 * i] | sna[x + 2 * i + 1] << 8 for i in range(8)], XP_NEXT)
    for gone in ("xp_next", "lvlup_tab", "lvl_step_tab"):
        chk(f"{gone} removed (single source)", [gone in sym], [False])

    # 3F-T3: the new kind_tab rows (bank 2, from the .sna) and the per-kind weight / drop
    # tables, transcribed from game.md §9.1 / §9.3 / §9.6 (hp atk eva before depth scaling;
    # die = dmg die sides, bonus; period; weight). BW / BH / ink are the STAND-IN frames' until
    # T13 (checked only for consistency with the stand-in unit, not against the doc).
    kt = sym["kind_tab"]

    def kcol(off, k):
        return sna[27 + kt + off - 0x4000 + k]

    # id: (hp, atk, eva, die, bonus, period, weight)
    K3 = {9: (7, 3, 3, 4, 0, 1, 2), 10: (14, 2, 1, 6, 0, 2, 5), 11: (14, 3, 1, 8, 0, 1, 5),
          12: (8, 2, 2, 4, 0, 1, 6), 13: (18, 3, 0, 8, 0, 2, 5), 14: (12, 2, 2, 4, 0, 1, 6),
          15: (40, 5, 1, 10, 2, 1, 6), 16: (50, 6, 3, 10, 3, 1, 5), 17: (40, 4, 3, 6, 0, 1, 6),
          18: (5, 1, 1, 3, 0, 1, 2), 19: (8, 2, 3, 4, 0, 1, 2), 20: (5, 2, 4, 3, 0, 1, 2),
          21: (8, 2, 1, 4, 0, 1, 4), 22: (10, 4, 3, 4, 0, 1, 2), 23: (14, 3, 2, 6, 0, 1, 5),
          24: (18, 4, 2, 8, 0, 1, 5), 25: (11, 3, 3, 4, 0, 1, 3), 26: (18, 4, 0, 8, 2, 1, 5),
          27: (24, 5, 1, 10, 0, 1, 5), 28: (10, 3, 2, 4, 0, 1, 6), 29: (14, 3, 2, 4, 0, 1, 6),
          2: (14, 1, 4, 2, 0, 1, 5)}           # 3F-T9 K_VBAT: Vampire hp / weight, the Bat's atk / eva, 1d2, every turn
    ASSERT_LW = sym["lp_wt"] == sym["kind_tab"] + sym["KT_REACH"]   # MEM-RECLAIM w3: lp_wt is the old KT_REACH slot, ONE copy (bank 2)
    chk("lp_wt == kind_tab + KT_REACH", [ASSERT_LW], [True])
    for k, (hp, atk, eva, die, bon, per, wt) in K3.items():
        chk(f"kind_tab[{k}] hp/atk/eva/die/bonus/period",
            [kcol(sym["KT_HP"], k), kcol(sym["KT_ATK"], k), kcol(sym["KT_EVA"], k), kcol(sym["KT_DIE"], k),
             kcol(sym["KT_BONUS"], k), kcol(sym["KT_PERIOD"], k)], [hp, atk, eva, die, bon, per])
        chk(f"lp_wt[{k}]", [kcol(sym["KT_REACH"], k)], [wt])
    # tiers keep their base's body / flags / BH (§9.6), differ only in the ink from it
    for tier, base in ((18, 6), (19, 6), (20, 7), (21, 4), (22, 9), (23, 3), (24, 3), (25, 5),
                       (26, 11), (27, 11), (28, 12), (29, 14)):
        for col in ("KT_BW", "KT_BH", "KT_FLAGS"):
            chk(f"kind_tab {col}[{tier}] == base {base}", [kcol(sym[col], tier)], [kcol(sym[col], base)])
        chk(f"tier {tier} ink != base {base} ink", [kcol(sym["KT_ATTR"], tier) != kcol(sym["KT_ATTR"], base)], [True])
    # climbers: Goblin / Skeleton (+ tiers) and the heroes (§9.7 R3); 3F-T13bc (user 2026-10-29):
    # + Orc (Berserker 26, Bouncer 27), Archer (Sniper 28), Necro (Bone Caller 29), + Mummy 13, Spider 9 + Black Widow 22 (fix/archer-climb; the Pharaoh boss guard is the AI's)
    CLIMB = {0, 1, 3, 4, 9, 21, 22, 23, 24, 11, 12, 13, 14, 26, 27, 28, 29}
    for k in range(30):
        chk(f"KF_CLIMBER[{k}]", [kcol(sym["KT_FLAGS"], k) & sym["KF_CLIMBER"] != 0], [k in CLIMB])
    # drop_tab: (kind, item, N, k) = "k in N" (§8.11 + §9.6: the base numerator + 1 per tier above 1)
    dt = sym["drop_tab"] - sym["R6_ADDR"]       # 3F-T5: drop_tab moved to R6 (tier6.asm)
    DROPS = [(6, "IT_F_CHEESE", 4, 1), (4, "IT_F_APPLE", 4, 1), (11, "IT_F_MEAT", 3, 1), (12, "IT_ARROW", 2, 1),
             (14, "IT_P_MANA", 3, 1), (18, "IT_F_CHEESE", 4, 2), (19, "IT_F_CHEESE", 4, 3),
             (21, "IT_F_APPLE", 4, 2), (26, "IT_F_MEAT", 3, 2), (27, "IT_F_MEAT", 3, 3),
             (28, "IT_ARROW", 2, 2), (29, "IT_P_MANA", 3, 2),
             # 3F-T6: the tiers of a base with no drop: a random food (type 0 = Carrot / Apple / Pear) 1 in 4
             (20, 0, 4, 1), (22, 0, 4, 1), (23, 0, 4, 1), (24, 0, 4, 1), (25, 0, 4, 1)]
    chk("DROP_ROWS", [sym["DROP_ROWS"]], [len(DROPS)])
    for i, (kd, it, n, kk) in enumerate(DROPS):
        chk(f"drop_tab[{i}]", R6BLK[dt + 4 * i:dt + 4 * i + 4], [kd, sym[it] if isinstance(it, str) else it, n, kk])

    rk = at("ab_rank")
    for a, (name, rows) in enumerate(RANKS.items()):
        for r, row in enumerate(rows):
            o = rk + (a * 3 + r) * 6
            chk(f"rank {name} {r + 1}", m[o:o + 6], row)
    am = at("ab_ammo")
    for i, row in enumerate(AMMO):
        chk(f"ammo {i}", m[am + 6 * i:am + 6 * i + 6], row)

    df = at("ab_def")
    for i, (dty, a1, a2, spd, fl, hit) in enumerate(DEFS):
        r = m[df + 10 * i:df + 10 * i + 10]
        chk(f"def {i} dty", [r[0]], [dty])
        chk(f"def {i} attr/speed/flags/hit", r[5:10], [a1, a2, spd, fl, hit])
        # fids (D3-4): the named frames, never the placeholder where a sprite
        # exists, each inside its class FX kind's range (generated with the hero)
        names, cls = FIDS[i]
        chk(f"def {i} fids", r[1:5], [0xFF if n is None else sym[f"FID_{n}"] for n in names])
        f0, fn = sym[f"KFID_{cls}"], sym[f"KFCNT_{cls}"]
        for n in names:
            if n is not None and not f0 <= sym[f"FID_{n}"] < f0 + fn:
                fails.append(f"def {i} fid {n} outside K_{cls} [{f0}, {f0 + fn})")

    # RANK1: every ranked info line shows its rank's MP cost and range (name field 16 | numbers 12 | notes 14)
    info = {}
    for ln in open(os.path.join(REPO, "src/strings.txt")):
        m = re.match(r'^(info_\w+)\s+"(.*)"\s*$', ln)
        if m:
            info[m.group(1)] = m.group(2)
    stems = {"Spark": "spark", "Firebolt": "firebolt", "Frost": "frost", "Drain": "drain",
             "Lightning": "lightning", "Power": "power", "Whirl": "whirl"}
    for name, rows in RANKS.items():
        for r, row in enumerate(rows):
            line = info[f"info_{stems[name]}" + ("" if r == 0 else str(r + 1))]
            mm = re.match(r"^(.{16})MP(\d+) RNG(\d+)", line)
            chk(f"info line {name} rank {r + 1} fits 42", [len(line) <= 42], [True])
            chk(f"info line {name} rank {r + 1} MP / RNG", [mm and int(mm.group(2)), mm and int(mm.group(3))],
                [row[0], row[1] if row[1] else 1])

    n = 32 + 8 + 2 + 8 + 21 + 2 + 9 + 42 + 40 + 48 + 30 + 13   # 3F-T3: kind_tab / lp_wt / climbers / drop_tab
    if fails:
        print("combat_tables: FAIL")
        for f in fails:
            print("  ", f)
        return 1
    print(f"combat_tables: PASS ({n} table groups; kx 256 B, rank 126 B, ammo 12 B, ab_def 90 B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
