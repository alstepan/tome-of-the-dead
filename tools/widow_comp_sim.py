#!/usr/bin/env python3
"""Black Widow spit (P6 N4) + table-only compensation candidates; average policy, W and M, same seed.
Usage: python3 tools/widow_comp_sim.py [--runs 10000] [--jobs 8] [--seed 1] [--only name,name]"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import balance_sim as B  # noqa: E402

SPIT = {"WIDOW_SPIT": 1, "WIDOW_POISON": 6, "WIDOW_PERIOD": 4}


def v(name, kind=None, **param):
    ov = {"param": dict(SPIT, **param)}
    if kind:
        ov["kind"] = {"Black Widow": kind}
    return name, ov


VARIANTS = [
    ("baseline (no spit)", {}),
    v("spit P6 N4"),
    v("+ bite poison 18 (etn 9)", {"etn": 9}),
    v("+ bite poison 12 (etn 6)", {"etn": 6}),
    v("+ Widow hp 9", {"hp": 9}),
    v("+ Widow hp 8", {"hp": 8}),
    v("+ Widow atk 3", {"atk": 3}),
    v("+ bite 12 + atk 3 + hp 8", {"etn": 6, "atk": 3, "hp": 8}),
    v("+ Warrior start HP 25", None, W_HP0=25),
    v("+ Warrior start HP 26", None, W_HP0=26),
    v("+ Warrior HP/level 5", None, W_LVL_HP=5),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=10000)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--seed", default="1")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    only = [s for s in a.only.split(",") if s]
    print("variant | W win%% | M win%% | W reach D6 %% | W D5 deaths %% of runs")
    for name, ov in VARIANTS:
        if only and not any(o in name for o in only):
            continue
        out = {}
        for hero in ("W", "M"):
            out[hero] = B.run_cell(ov, hero, "average", a.runs, a.seed, a.jobs)
        w, m = out["W"], out["M"]
        print("%s | %.1f | %.1f | %.1f | %.1f" % (
            name, 100.0 * w["wins"] / w["n"], 100.0 * m["wins"] / m["n"],
            100.0 * w["reached"][6] / w["n"], 100.0 * w["death_depth"][5] / w["n"]), flush=True)


if __name__ == "__main__":
    main()
