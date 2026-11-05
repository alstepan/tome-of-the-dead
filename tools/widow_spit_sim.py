#!/usr/bin/env python3
"""Black Widow spit what-if: baseline + 4 variants (P in 12/6, period 3/4), average policy, W and M, same seed.
Usage: python3 tools/widow_spit_sim.py [--runs 10000] [--jobs 8] [--seed 1]   (reads the built image; WZ_BUILD_DIR honoured)"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import balance_sim as B  # noqa: E402

# WIDOW-SPIT is in the game since 2026-11-05 (the image default = spit P6 N4 + Warrior HP/level 5): the what-if
# grid is pinned to the pre-spit game (W_LVL_HP 4) so it reproduces docs/design/widow_spit_sim.md
PRE = {"WIDOW_SPIT": 0, "W_LVL_HP": 4}
VARIANTS = [("baseline", {"param": dict(PRE)})] + [
    ("P%d/N%d" % (p, n), {"param": dict(PRE, WIDOW_SPIT=1, WIDOW_POISON=p, WIDOW_PERIOD=n)})
    for p in (12, 6) for n in (3, 4)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=10000)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--seed", default="1")
    a = ap.parse_args()
    print("variant hero | win%% [95%% CI] | deaths%% of runs D4 D5 D6 | reach D6 %% | HP lost per Widow fight (fights/run) | Widow-killer %% of runs")
    for name, ov in VARIANTS:
        for hero in ("W", "M"):
            r = B.run_cell(ov, hero, "average", a.runs, a.seed, a.jobs)
            s = B.summarize(r)
            n = r["n"]
            dd = [100.0 * r["death_depth"][d] / n for d in (4, 5, 6)]
            wk = sum(v for k, v in r["dk"].items() if "Black Widow" in k)
            print("%s %s | %.1f [%.1f,%.1f] | %.1f %.1f %.1f | %.1f | %.2f (%.2f) | %.1f" % (
                name, hero, 100 * s["win"], 100 * s["lo"], 100 * s["hi"], dd[0], dd[1], dd[2],
                100.0 * r["reached"][6] / n, r["wloss"] / max(1, r["wfights"]), r["wfights"] / n, 100.0 * wk / n), flush=True)


if __name__ == "__main__":
    main()
