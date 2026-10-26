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
    b3 = blocks[5]
    assert b3[0] == 0xFF, "bank-3 block flag"
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


def kx_row(res, imm, xp):
    b = [0, 0, 0]
    for t, r in res.items():
        i = TYPES.index(t)
        if r == "W":
            b[2] |= 1 << i
        else:
            b[i // 4] |= RESP[r] << (2 * (i % 4))
    return b + [imm, xp, 0, 0, 0]   # DEF = 0 in 3D (§11.4); KX_SPARE 2 B (MEM-1)


XP_NEXT = [40, 100, 200, 340, 500, 700, 920, 1150]          # levels 2..9
LEVELUP = [(4, 1), (3, 2)]                                   # Warrior, Mage (HP, MP)
STEPS = {4: (1, 0), 6: (0, 1), 8: (1, 0)}                    # level -> (atk, eva)

# rank table, §5: (MP, range, die, bonus, bounces, effect) per rank 1..3, cumulative
# effect: status = chance<<4 | turns; Firebolt = burst die (|$80 spare); Whirlwind = to-hit
RANKS = {
    "Spark":     [(2, 6, 4, 1, 0, 0x44), (2, 8, 4, 2, 0, 0x44), (2, 8, 4, 3, 0, 0x24)],
    "Firebolt":  [(3, 12, 8, 2, 0, 4), (3, 12, 8, 3, 0, 6), (3, 12, 8, 4, 0, 0x86)],
    "Frost":     [(3, 12, 6, 0, 1, 2), (3, 12, 6, 0, 2, 3), (3, 12, 6, 2, 2, 4)],
    "Drain":     [(3, 5, 6, 1, 0, 0), (3, 8, 6, 2, 0, 0), (2, 8, 6, 3, 0, 0)],
    "Lightning": [(5, 28, 8, 3, 2, 0), (5, 28, 8, 4, 2, 0), (4, 28, 8, 4, 3, 0)],
    "Power":     [(3, 0, 0, 0, 0, 1), (2, 0, 0, 0, 0, 1), (2, 0, 0, 0, 0, 2)],
    "Whirl":     [(4, 0, 0, 1, 0, 0), (4, 0, 0, 2, 0, 0), (3, 0, 0, 2, 0, 2)],
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
        want = kx_row(*KINDS[k][1:]) if k in KINDS else [0] * 8
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

    n = 32 + 8 + 2 + 8 + 21 + 2 + 9
    if fails:
        print("combat_tables: FAIL")
        for f in fails:
            print("  ", f)
        return 1
    print(f"combat_tables: PASS ({n} table groups; kx 256 B, rank 126 B, ammo 12 B, ab_def 90 B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
