#!/usr/bin/env python3
"""B3B-7 (W10): Z80 level_gen / level_start_x (+ LP lp_budget) vs tools/levelgen.py, byte-exact.

Loads build/wazhack.sna, then for each (depth, seed[, master]) pokes the header
seed, runs a probe stub (far3 -> level_gen, far3 -> level_start_x) and compares
the 320-byte block with levelgen.generate() and the start col with start_x().
Reports T-states of the worst cases (interrupts are off in the stub, so the
count is the generator alone). `--random N` sets the random-seed count (200).
Run with ZRCP_PORT=<port>.

`--f3` (3F-T10): builds the -DF3_GEN=1 variant into a temp dir (WZ_BUILD_DIR, game_lib) and
compares against generate(..., f3=True): the D8 Sanctum leaf, the sealed edge, LVL_FLAGS = 0,
NROOMS + 1, GEN_RNG untouched; the LP budget is still compared with the default (non-f3) lp_budget.
Half of the `--random N` cases are forced to D8."""
import os
import random
import subprocess
import tempfile
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
F3 = "--f3" in sys.argv
if F3 and "WZ_BUILD_DIR" not in os.environ:
    # re-run against a -DF3_GEN=1 build, BEFORE game_lib is imported (it reads WZ_BUILD_DIR
    # and the .sym at import, so the checkout's build/ need not exist or be DEBUG_KIT=0)
    _root = Path(__file__).resolve().parent.parent
    _out = tempfile.mkdtemp(prefix="f3gen_")
    os.makedirs(os.path.join(_out, "build"), exist_ok=True)
    _r = subprocess.run([str(_root / "tools/build.sh"), "-o", _out, "-DDEBUG_KIT=0", "-DF3_GEN=1"],
                        cwd=_out, capture_output=True, text=True)
    if _r.returncode or "warning" in _r.stdout.lower().replace("warnings: 0", ""):
        sys.exit("f3 build failed:\n" + _r.stdout[-2000:] + _r.stderr[-500:])
    sys.exit(subprocess.call([sys.executable, __file__] + sys.argv[1:],
                             env=dict(os.environ, WZ_BUILD_DIR=os.path.join(_out, "build"))))
import levelgen as G                                    # noqa: E402
from game_lib import Harness, Proto, S, EMU_ARGS        # noqa: E402

ORG = S["LOWRAM_END_3B"]                                # free low RAM (above the LP state)
RES = ORG + 40                                          # result bytes
BASE = G.BASE


def stub(depth, ei=False):
    sp = S["WORKSTORE_TOP"]
    far3 = S["far3"]
    code = [0xFB if ei else 0xF3,                       # di: T-state count = generator only (ei: ISR + AY slot run too)
            0x31, sp & 255, sp >> 8,                    # ld sp,WORKSTORE_TOP
            0x3E, depth,                                # ld a,depth
            0x21, S["level_gen"] & 255, S["level_gen"] >> 8,
            0xCD, far3 & 255, far3 >> 8,
            0x78, 0x32, RES & 255, RES >> 8,            # ld a,b : ld (RES),a
            0x21, S["level_start_x"] & 255, S["level_start_x"] >> 8,
            0xCD, far3 & 255, far3 >> 8,
            0x78, 0x32, (RES + 1) & 255, (RES + 1) >> 8,
            0x21, S["lp_budget"] & 255, S["lp_budget"] >> 8,    # LP (game.md §9.4.1)
            0xCD, far3 & 255, far3 >> 8,
            0x00]
    return code


class T(Proto):
    def run(self, depth, seed, master, ei=False):
        code = bytes(stub(depth, ei))
        end = ORG + len(code) - 1                       # the NOP: probe, then jr $
        code += b"\x18\xfe"
        z = self.z
        z.cmd("write-memory %d %s" % (ORG, " ".join(str(b) for b in code)))
        z.cmd("write-memory %d %d %d" % (S["LVL_SEED"], seed & 255, seed >> 8))
        z.cmd("write-memory %d %d %d" % (S["MASTER_SEED"], master & 255, master >> 8))
        z.cmd("set-breakpoint 3 PC=%d" % end)
        self.extra_probes = {end}
        z.cmd("set-register PC=%d" % ORG)
        z.cmd("reset-tstates-partial")
        z.cmd("run 20000000")
        ts = int(z.cmd("get-tstates-partial"))
        ok = self.pc() == end
        z.cmd("set-breakpoint 3")
        self.extra_probes = set()
        blk = bytes(z.read_memory(BASE, G.BLOCK_LEN))
        r = bytes(z.read_memory(RES, 2))
        lp = bytes(z.read_memory(S["LP_STATE"], S["LP_LEN"]))
        return ok, ts, blk, r[0], r[1], lp


def case(h, p, depth, seed, master=0, tag="", ei=False):
    want = G.generate(depth, seed, master, f3=F3)
    wx = G.start_x(want)
    ok, ts, blk, rc, sx, lp = p.run(depth, seed, master, ei)
    wlp = G.lp_budget(want, p.rb("LVL"))
    good = ok and rc == 0 and blk == want and sx == wx and lp == wlp
    if not good:
        d = next((i for i in range(len(want)) if blk[i] != want[i]), None)
        if d is not None and os.environ.get("LG_DUMP"):
            print("   got ", blk.hex(), "\n   want", want.hex())
        print(f"  FAIL d{depth} seed {seed:#06x} {tag}: ran={ok} rc={rc} first diff @{d}"
              f" got {blk[d] if d is not None else '-'} want {want[d] if d is not None else '-'}"
              f" startx {sx}/{wx} lp_budget {'ok' if lp == wlp else lp.hex() + ' want ' + wlp.hex()}",
              flush=True)
    h.expect(f"d{depth} seed {seed:#06x} {tag}", good, True) if not good else None
    return good, ts


def _lastscan(seeds):
    out = []
    for seed in seeds:
        for d in range(1, 9):
            try:
                G.generate(d, seed)
            except RuntimeError:
                continue
            if G.LAST[0] or G.LAST[2]:
                out.append((d, seed))
    return out


def retry_cases():
    """every (depth, seed) of the full scan that needed a restart or a reseed"""
    from multiprocessing import Pool
    chunks = [range(i, min(i + 1024, 65536)) for i in range(0, 65536, 1024)]
    with Pool() as pool:
        return sorted(x for part in pool.map(_lastscan, chunks) for x in part)


def worst_seeds():
    """worst restarts / reseeds / rnd calls over depth 8 (+ scan of a seed range)"""
    best = {"restarts": (0, 0), "reseeds": (0, 0), "calls": (0, 0)}
    for seed in range(0, 3000):
        for depth in (8, 5, 2):
            G.generate(depth, seed)
            rs, calls, rsd = G.LAST
            for k, v in (("restarts", rs), ("reseeds", rsd), ("calls", calls)):
                if v > best[k][0]:
                    best[k] = (v, seed)
                    best[k + "_d"] = depth
    return best


def main():
    nrand = 200
    if "--random" in sys.argv:
        nrand = int(sys.argv[sys.argv.index("--random") + 1])
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)
        p.load()
        npass = nfail = 0
        worst = (0, "")

        def go(depth, seed, master=0, tag=""):
            nonlocal npass, nfail, worst
            good, ts = case(h, p, depth, seed, master, tag)
            npass += good
            nfail += not good
            if ts > worst[0]:
                worst = (ts, f"d{depth} seed {seed:#06x}")
            return ts

        pairs = [(d, s) for d in range(1, 9) for s in (0x0001, 0x1234, 0xBEEF)]
        pairs += [(8, 12634), (8, 0), (8, 0xFFFF), (1, 0xFFFE)]
        # full 65,536-seed scan after L1: max restarts d8 seed 770, max rnd calls d7
        # seed 8823; no seed reseeds (lair reseeds 0, nothing exhausts the 16)
        pairs += [(8, 770), (7, 8823), (8, 55355), (8, 55352)]
        # L2: seeds with a wide pit / a mid-block / both (and none) at every depth 2..8
        for d in range(2, 9):
            nw = nm = 0
            for sd in range(1, 20000):
                if nw >= 3 and nm >= 3:
                    break
                bb = G.generate(d, sd)
                kw = any(bb[G.OFF_DESC + 16 * r + G.L2_PITW] for r in range(9))
                km = any(bb[G.OFF_DESC + 16 * r + G.L2_MIDB] for r in range(9))
                if (kw and nw < 3) or (km and nm < 3):
                    pairs.append((d, sd))
                    nw += kw
                    nm += km
        pairs += [(d, d * 0x0101) for d in range(1, 9)]        # seed ^ depth*$0101 == 0 -> x = 1
        for d, s in pairs:
            ts = go(d, s, master=(s * 7) & 0xFFFF, tag="fixed")
            if (d, s) in ((8, 12634), (8, 770), (7, 8823)):
                print(f"  T-states d{d} seed {s}: {ts}", flush=True)
        for d, sd in ((5, 0x1234), (8, 2609)):                 # interrupts on: ISR + AY slot during gen
            good, ts = case(h, p, d, sd, 0x55AA, "ei", ei=True)
            npass += good
            nfail += not good
        print(f"fixed: {npass} pass {nfail} fail; worst {worst}", flush=True)
        if "--all-retries" in sys.argv:
            t0 = time.monotonic()
            cases = retry_cases()
            if "--sample" in sys.argv:
                k = int(sys.argv[sys.argv.index("--sample") + 1])
                cases = random.Random(7).sample(cases, min(k, len(cases)))
            print(f"retry/reseed cases: {len(cases)} (scan {time.monotonic() - t0:.0f}s)", flush=True)
            t0 = time.monotonic()
            f0 = nfail
            for d, sd in cases:
                go(d, sd, (sd * 3) & 0xFFFF, "retry")
            print(f"all retry/reseed cases: {len(cases)} run, {nfail - f0} fail, {time.monotonic() - t0:.0f}s", flush=True)
        rng = random.Random(0x3B7)
        t0 = time.monotonic()
        for i in range(nrand):
            go(8 if F3 and i % 2 == 0 else rng.randint(1, 8), rng.randrange(65536), rng.randrange(65536), "rand")
        print(f"random {nrand}: {time.monotonic() - t0:.1f}s; total {npass} pass {nfail} fail;"
              f" worst T {worst}", flush=True)
        return 1 if nfail or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
