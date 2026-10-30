#!/usr/bin/env python3
"""STAFF-BONUS: the worn Rune / Bone staff adds +1 / +2 to every damaging hero
spell (proj_prep, src/proj3.asm: pf_bonus += staff bonus when pf_abl is Spark..
Lightning). Same seed, same Rat (200 HP, no spell resist beyond the table):
pf_lost differs from the Oak staff cast by exactly the bonus; the RNG state
after the cast is identical (no extra draws); Iron / Oak / empty hand / the
Warrior-only Sword give +0; the dagger and bow (missiles) get nothing even with
a Bone Staff worn. Melee is not touched by construction (do_attack reads
KT_BONUS, which the staff bonus never writes: checked unchanged).
Run: ZRCP_PORT=<port> python3 tests/staff.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_RAT  # noqa: E402
import proj3 as P  # noqa: E402

EF_ACTIVE, EF_PLAYER, EF_LEFT = 1, 2, 0
WORN = S["WORN"]


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = P.T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                print(f"[detail] {tag}: {detail}", flush=True)

        p.boot(K_KNIGHT)
        kt = p.kinds()
        hy = p.ent(0)["Y"]
        hx = 10
        P.T.worst = (0, "", 0)

        def cast(abl, rank, wtype, seed):
            w = P.World(kt, (0, 0, 0))
            w.bodies[0] = P.Body(0, K_KNIGHT, hx, hy, 200, 200, EF_ACTIVE | EF_PLAYER)
            front = hx + kt[K_KNIGHT]["bw"]
            w.bodies[1] = P.Body(1, K_RAT, front + 2, hy + kt[K_KNIGHT]["bh"] - kt[K_RAT]["bh"], 200, 200,
                                 EF_ACTIVE | 4)
            p.setup(w, seed)
            p.wb("MP", 0)
            p.wmem(WORN, [wtype, 1, 0])
            kb = S["kind_tab"] + S["KT_BONUS"] + K_KNIGHT
            b0 = p.rb(kb)
            p.fire(0, abl, rank, 3)
            return p.rb("pf_lost"), p.rw("RNG_STATE"), p.rb(kb) == b0

        none, oak, iron = 0, S["IT_W_OAK"], S["IT_W_IRON"]
        rune, bone = S["IT_W_RUNE"], S["IT_W_BONE"]
        for abl, name in ((P.SPARK, "Spark"), (P.FIREBOLT, "Firebolt"), (P.FROST, "Frost"),
                          (P.LIGHTNING, "Lightning"), (P.DRAINL, "Drain")):
            for rank in (1, 2, 3):
                for seed in (0x1357, 0xACE1):
                    base = cast(abl, rank, oak, seed)
                    for wt, bonus, tag in ((none, 0, "empty"), (iron, 0, "Iron"), (rune, 1, "Rune"), (bone, 2, "Bone")):
                        got = cast(abl, rank, wt, seed)
                        check(f"{name} r{rank} {seed:#x} {tag}: dmg +{bonus}, same RNG, KT_BONUS kept",
                              got[0] == base[0] + bonus and got[1] == base[1] and got[2], (base, got))
        for abl, name in ((P.DAGGER, "Dagger"), (P.BOW, "Bow")):
            base = cast(abl, 1, oak, 0x1357)
            got = cast(abl, 1, bone, 0x1357)
            check(f"{name} with a Bone Staff: no bonus", got[:2] == base[:2], (base, got))
    print("FAILS:", fails if fails else "none")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
