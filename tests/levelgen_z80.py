#!/usr/bin/env python3
"""B3B-7 (W10): Z80 level_gen / level_start_x vs tools/levelgen.py, byte-exact.

Loads build/wazhack.sna, then for each (depth, seed[, master]) pokes the header
seed, runs a probe stub (far3 -> level_gen, far3 -> level_start_x) and compares
the 320-byte block with levelgen.generate() and the start col with start_x().
Reports T-states of the worst cases (interrupts are off in the stub, so the
count is the generator alone). `--random N` sets the random-seed count (200).
Run with ZRCP_PORT=<port>."""
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import levelgen as G                                    # noqa: E402
from game_lib import Harness, Proto, S, EMU_ARGS        # noqa: E402

ORG = 0x6EC0                                            # free low RAM (above ORN_GLYPHS)
RES = ORG + 40                                          # result bytes
BASE = G.BASE


def stub(depth):
    sp = S["WORKSTORE_TOP"]
    far3 = S["far3"]
    code = [0xF3,                                       # di: T-state count = generator only
            0x31, sp & 255, sp >> 8,                    # ld sp,WORKSTORE_TOP
            0x3E, depth,                                # ld a,depth
            0x21, S["level_gen"] & 255, S["level_gen"] >> 8,
            0xCD, far3 & 255, far3 >> 8,
            0x78, 0x32, RES & 255, RES >> 8,            # ld a,b : ld (RES),a
            0x21, S["level_start_x"] & 255, S["level_start_x"] >> 8,
            0xCD, far3 & 255, far3 >> 8,
            0x78, 0x32, (RES + 1) & 255, (RES + 1) >> 8,
            0x00]
    return code


class T(Proto):
    def run(self, depth, seed, master):
        code = bytes(stub(depth))
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
        return ok, ts, blk, r[0], r[1]


def case(h, p, depth, seed, master=0, tag=""):
    want = G.generate(depth, seed, master)
    wx = G.start_x(want)
    ok, ts, blk, rc, sx = p.run(depth, seed, master)
    good = ok and rc == 0 and blk == want and sx == wx
    if not good:
        d = next((i for i in range(len(want)) if blk[i] != want[i]), None)
        print(f"  FAIL d{depth} seed {seed:#06x} {tag}: ran={ok} rc={rc} first diff @{d}"
              f" got {blk[d] if d is not None else '-'} want {want[d] if d is not None else '-'}"
              f" startx {sx}/{wx}", flush=True)
    h.expect(f"d{depth} seed {seed:#06x} {tag}", good, True) if not good else None
    return good, ts


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
        # full 65,536-seed scan (depths 1..8): max restarts d6 seed 2184, max rnd
        # calls / reseeds (15) d8 seed 31306; d8 seeds 28962/55353/55354 exhaust
        # the 16 reseeds (Python raises, Z80 returns B=1)
        pairs += [(6, 2184), (8, 31306), (8, 2609)]
        for d, s in pairs:
            ts = go(d, s, master=(s * 7) & 0xFFFF, tag="fixed")
            if (d, s) in ((8, 12634), (8, 31306), (6, 2184), (8, 2609)):
                print(f"  T-states d{d} seed {s}: {ts}", flush=True)
        for seed in (28962, 55353, 55354):
            ok, ts, blk, rc, sx = p.run(8, seed, 0)
            h.expect(f"d8 seed {seed} exhausts reseeds (B=1)", bool(ok and rc == 1), True)
            print(f"  exhaust d8 seed {seed}: {ts} T rc={rc}", flush=True)
        print(f"fixed: {npass} pass {nfail} fail; worst {worst}", flush=True)
        rng = random.Random(0x3B7)
        t0 = time.monotonic()
        for _ in range(nrand):
            go(rng.randint(1, 8), rng.randrange(65536), rng.randrange(65536), "rand")
        print(f"random {nrand}: {time.monotonic() - t0:.1f}s; total {npass} pass {nfail} fail;"
              f" worst T {worst}", flush=True)
        return 1 if nfail or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
