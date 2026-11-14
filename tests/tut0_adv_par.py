#!/usr/bin/env python3
"""Parallel front end for tests/tut0_adv.py (chore/test-speed).

The soak is emulation-bound (one ZEsarUX `run` per tick, ~16 ticks/s in-game), so a seed costs minutes
no matter the emulator flags; but every (class, seed) and every scripted scenario is independent (fresh
snapshot load, own RNG), so they shard across emulators with identical inputs and checks. Each job is one
tut0_adv.py process on its own ZRCP port (base port .. base+jobs-1; the 10730-10739 range by default).

Usage: python3 tests/tut0_adv_par.py [--jobs 8] [--base-port 10730] [--seeds N] [--inputs N] [--seed0 K]
                                     [--hero 0|1] [--no-scen] [--no-soak]
Output: per-job PASS/FAIL lines in job order (scenario / seed lines of the children), then a summary;
exit 1 if any job failed. A failed job prints its last 40 output lines.
"""
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ADV = os.path.join(HERE, "tut0_adv.py")
argv = sys.argv[1:]


def opt(name, default, cast=int):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


def scen_ids():
    return re.findall(r'^@scen\("([^"]+)"', open(ADV).read(), re.M)


def main():
    jobs_n, base = opt("--jobs", 8), opt("--base-port", 10730)
    seeds, inputs, seed0 = opt("--seeds", 20), opt("--inputs", 3000), opt("--seed0", 1)
    heroes = (opt("--hero", 0),) if "--hero" in argv else (0, 1)
    jobs = []                                       # (label, tut0_adv args); longest first = better packing
    if "--no-soak" not in argv:
        for seed in range(seed0, seed0 + seeds):
            for hero in heroes:
                jobs.append((f"soak hero{hero} seed{seed}", ["--no-scen", "--hero", str(hero), "--seed0", str(seed),
                                                            "--seeds", "1", "--inputs", str(inputs)]))
    if "--no-scen" not in argv:
        for sid in scen_ids():
            a = ["--no-soak", "--only", sid]
            if "--hero" in argv:
                a += ["--hero", str(heroes[0])]
            jobs.append((f"scen {sid}", a))
    t0 = time.monotonic()
    free, running, done = list(range(jobs_n)), {}, {}
    queue = list(enumerate(jobs))
    while queue or running:
        while queue and free:
            i, (label, a) = queue.pop(0)
            port = base + free.pop(0)
            env = dict(os.environ, ZRCP_PORT=str(port))
            running[i] = (subprocess.Popen([sys.executable, ADV, *a], env=env, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, text=True), port, label)
        time.sleep(1)
        for i, (p, port, label) in list(running.items()):
            if p.poll() is not None:
                done[i] = (label, p.returncode, p.stdout.read())
                free.append(port - base)
                del running[i]
                print(f"[par] {label}: rc={p.returncode} ({time.monotonic() - t0:.0f}s)", flush=True)
    bad = [done[i][0] for i in sorted(done) if done[i][1]]
    for i in sorted(done):
        label, rc, out = done[i]
        keep = [l for l in out.splitlines() if l.startswith(("[PASS]", "[FAIL]", "tut0_adv:", "  VIOL", "  repro"))]
        print(f"== {label} (rc={rc})")
        print("\n".join(keep if not rc else out.splitlines()[-40:]))
    print(f"tut0_adv_par: {len(bad)} failed of {len(done)} jobs: {bad} ({time.monotonic() - t0:.0f}s, {jobs_n} emulators)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
