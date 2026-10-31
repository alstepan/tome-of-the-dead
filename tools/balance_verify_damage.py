#!/usr/bin/env python3
"""BAL-1c verification (a): exact Warrior damage distribution vs a target, straight from the built tables, with
the damage order of src/combat3.asm deal_hit (.np/.nr/.nw/.def) and src/rank3.asm melee_hit:

  roll = 1dN + KT_BONUS(weapon incl. Enchant) [+ Whirlwind RK_BONUS]; Power Strike: roll*2 / roll+roll*... (x2, 2d+d/2, x3)
  deal_hit: R -> roll>>1 (min 1);  W -> x2;  PHYS: dmg - DEF (min 1).    (parry/WEAK/etc. not shown)
Usage: python3 tools/balance_verify_damage.py [KIND] [DEPTH]    (default OGRE 4)"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO + "/tools")
import balance_sim as B  # noqa: E402

WEAPONS = {"Short Sword 1d6": (6, 0, 0), "Long Sword 1d8 atk+1": (8, 0, 1), "War Axe 1d10 atk-1": (10, 0, -1),
            "Cleaver 1d10+1 atk+1": (10, 1, 1)}


def after_deal(D, kind, roll, ty=B.PHYS, gold=False):
    k = D.k[kind]
    r = k["res"][ty]
    if r == 1:
        roll = max(1, roll >> 1)
    elif r == 4:
        roll *= 2
    elif r in (2, 3):
        return 0
    return max(1, roll - k["df"] - (1 if gold else 0))


def dist(D, kind, die, bonus, mult=None, wwb=0):
    out = {}
    for d in range(1, die + 1):
        roll = max(1, d + bonus + wwb)
        if mult == 2:
            roll *= 2
        elif mult == 2.5:
            roll = 2 * roll + roll // 2
        elif mult == 3:
            roll *= 3
        v = after_deal(D, kind, roll)
        out[v] = out.get(v, 0) + 1.0 / die
    return out


def main():
    D = B.Data()
    name = sys.argv[1] if len(sys.argv) > 1 else "OGRE"
    depth = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    kind = D.id(name)
    k = D.k[kind]
    hp = k["hp"] + depth - 1
    print("%s D%d: hp %d, DEF %d, PHYS resp %s, eva %d, atk %d" % (name, depth, hp, k["df"], "NRIXW"[k["res"][0]] if k["res"][0] < 4 else "W", k["eva"], k["atk"] + (depth - 1) // 3))
    print("%-24s %-9s %s" % ("attack (enchant 0)", "mean dmg", "distribution dmg:prob"))
    for wn, (die, bon, atk) in WEAPONS.items():
        for lab, mult, wwb in (("sword/swing", None, 0), ("Power Strike I x2", 2, 0), ("Power Strike II x2.5", 2.5, 0), ("Power Strike III x3", 3, 0),
                               ("Whirlwind III +4", None, 4)):
            d = dist(D, kind, die, bon, mult, wwb)
            mean = sum(v * p for v, p in d.items())
            print("%-24s %-22s %.2f   %s" % (wn, lab, mean, " ".join("%d:%.2f" % (v, p) for v, p in sorted(d.items()))))
    print("\nWarrior by level (hit chance, expected dmg/swing, swings to kill, Ogre-type hits taken), sword+Cleaver, enchant +3:")
    for lvl in range(1, 9):
        atk = 3 + (lvl >= 4) + (lvl >= 8)
        for wn in ("Short Sword 1d6", "Cleaver 1d10+1 atk+1"):
            die, bon, wa = WEAPONS[wn]
            p = max(0, min(1, (11 + atk + wa - k["eva"]) / 20.0))
            d = dist(D, kind, die, bon + 3)
            mean = sum(v * q for v, q in d.items())
            print("  L%d %-22s hit %.2f dmg/swing %.2f -> %.0f swings for %d hp" % (lvl, wn, p, p * mean, hp / (p * mean), hp))


if __name__ == "__main__":
    main()
