#!/usr/bin/env python3
"""3E-T7: the Z80 item / trap generator overlay (src/items_ovl.asm, 3E-T6) vs
tools/items_model.py (rev 6, game.md §8.11 "3E simplification"), byte-exact.

  G0  the item ink table it_tab (R6 icons6.asm item_ink, read from the
      .sna's bank 6) == items_model.ITEM_INK for every type (IT_NONE / IT_KEY: 0).
  G1  batch parity: for master seeds 0..N-1 (default 1,000) x D1..D8 x both heroes,
      the Python levelgen block (levelgen.generate == the Z80 level_gen, proven by
      tests/levelgen_z80.py) is poked into LVL_STATE with HERO_KIND and the overlay
      is run through ovl_run (the real stream, bank 3 paged as from level_new).
      Compared: the whole 320-B block == items_model.apply_block (FLOOR_N,
      FLOOR_LIST incl. the FL_EMPTY tail, TRAP_LIST / TRAP_N, GEN_RNG restored,
      every other byte unchanged). Reports the worst overlay T-states (unpack +
      generation + the driver's copies, interrupts off).
  G2  integration: far3 level_new (level_gen + level_populate + the overlay) for a
      few (master, depth, hero): the same comparison on the real path.
Batches of 16 cases run in one emulator call: inputs / outputs in bank 4 (pool,
free in a fresh snapshot), driver assembled by sjasmplus at LOWRAM_END_3B.
Run: ZRCP_PORT=<port> python3 tests/items_gen.py [--seeds N] [--jobs-split K/M]
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
import levelgen as G                                    # noqa: E402
import items_model as M                                 # noqa: E402
from game_lib import Harness, Proto, S, EMU_ARGS, SNA_RAM   # noqa: E402

DRV = S["LOWRAM_END_3B"]
BANK = S["BANK_POOL1"]                                  # bank 4: batch buffers
SLOT = 1024
NSLOT = 16
OUT = 512
HEROES = ((M.HERO_WARRIOR, S["K_KNIGHT"]), (M.HERO_MAGE, S["K_WIZARD"]))

DRIVER = """
    DEVICE ZXSPECTRUM48
    ORG {DRV}
    di
    ld sp, {WORKSTORE_TOP}
    ld hl, {C000}
    ld ({PTR}), hl
loop:
    ld a, {BANK} : call {page_bank}
    ld hl, ({PTR}) : ld de, {LVL_STATE} : ld bc, {BLK} : ldir
    ld a, (hl) : ld ({HERO_KIND}), a
    ld a, {BANK3} : call {page_bank}
    ld hl, {ovl_items_zx0} : ld de, {ITEMS_ORG} : ld c, {BANK_OVL}
    call {ovl_run}
    ld a, {BANK} : call {page_bank}
    ld hl, ({PTR}) : ld de, {OUT} : add hl, de : ex de, hl
    ld hl, {LVL_STATE} : ld bc, {BLK} : ldir
    ld hl, ({PTR}) : ld de, {SLOT} : add hl, de : ld ({PTR}), hl
    ld a, (cnt) : dec a : ld (cnt), a
    jp nz, loop
done:
    nop
    jr done
cnt: db 0
    SAVEBIN "{out}", {DRV}, $ - {DRV}
"""


def assemble():
    d = tempfile.mkdtemp(prefix="items_gen_")
    out = os.path.join(d, "drv.bin")
    sym = dict(DRV=DRV, WORKSTORE_TOP=S["WORKSTORE_TOP"], C000=0xC000, BANK=BANK,
               page_bank=S["page_bank"], LVL_STATE=S["LVL_STATE"], BLK=G.BLOCK_LEN,
               HERO_KIND=S["HERO_KIND"], BANK3=S["BANK_COLD3"],
               ovl_items_zx0=S["ovl_items_zx0"], ITEMS_ORG=S["ITEMS_ORG"],
               BANK_OVL=S["BANK_OVL_ITEMS"], ovl_run=S["ovl_run"], OUT=OUT, SLOT=SLOT, out=out,
               PTR=S["GEN_SRC"] + 0x200)                # a scratch word in GEN_SRC
    p = os.path.join(d, "drv.asm")
    Path(p).write_text(DRIVER.format(**sym))
    r = subprocess.run(["sjasmplus", "--nologo", "--sym=" + os.path.join(d, "drv.sym"), p],
                       capture_output=True, text=True)
    if r.returncode or "error:" in r.stdout + r.stderr:
        raise RuntimeError(r.stdout + r.stderr)
    syms = {}
    for line in Path(os.path.join(d, "drv.sym")).read_text().splitlines():
        if ": EQU " in line:
            k, v = line.split(": EQU ")
            syms[k.strip()] = int(v, 16)
    return Path(out).read_bytes(), syms["done"], syms["cnt"]


def expected(b, master, hero):
    return M.apply_block(b, M.gen_level_items(b, master, hero))


def table_check(h):
    """G0: it_tab (FLOOR1: R6, bank 6 in the .sna) inks vs the model (the class
    glyphs are gone; the ink drives the floor / page icon attr)."""
    def ram(a, n):
        o = 6 * 16384 + (a - 0xC000)
        return SNA_RAM[o:o + n]
    tab = ram(S["it_tab"], S["IT_COUNT"])
    bad = []
    for t in range(S["IT_COUNT"]):
        v = tab[t]
        ink = (v & 7) | (0x40 if v & 8 else 0)
        wi = M.ITEM_INK.get(t, 0x42 if t == S["IT_POTION"] else 0)
        if ink != wi:
            bad.append((t, hex(ink), hex(wi)))
    h.expect("G0 it_tab ink == items_model ITEM_INK (all types)", len(bad), 0)
    if bad:
        print("  G0 detail:", bad[:6], flush=True)


class T(Proto):
    proto_start = 0

    def setup(self):
        self.code, self.done, self.cnt = assemble()
        self.wmem(DRV, self.code)
        self.z.cmd("set-breakpoint 3 PC=%d" % self.done)
        self.extra_probes = {self.done}

    def wmem(self, addr, data):
        self.z.cmd("write-memory %d %s" % (addr, " ".join(map(str, data))))

    def zone(self, fn):
        self.z.cmd("set-memory-zone 0")
        try:
            return fn()
        finally:
            self.z.cmd("set-memory-zone -1")

    def batch(self, ins):
        """ins: list of (block + hero) records -> (out blocks, T-states of the batch)."""
        base = BANK * 16384
        buf = bytearray(SLOT * len(ins))
        for k, r in enumerate(ins):
            buf[k * SLOT:k * SLOT + len(r)] = r

        def w():
            for i in range(0, len(buf), 2048):
                self.wmem(base + i, buf[i:i + 2048])
        self.zone(w)
        self.wb(self.cnt, len(ins))
        self.z.cmd("set-register PC=%d" % DRV)
        self.z.cmd("reset-tstates-partial")
        self.z.cmd("run 200000000")
        ts = int(self.z.cmd("get-tstates-partial"))
        if self.pc() != self.done:
            raise RuntimeError("driver did not finish: PC %04X" % self.pc())
        raw = self.zone(lambda: bytes(self.z.read_memory(base, SLOT * len(ins))))
        return [raw[k * SLOT + OUT:k * SLOT + OUT + G.BLOCK_LEN] for k in range(len(ins))], ts


def cases(nseeds, part, parts):
    for m in range(nseeds):
        if m % parts != part:
            continue
        for d in range(1, 9):
            try:
                b = G.generate(d, M.level_seed(m, d), m)
            except RuntimeError:
                continue
            for hero, hk in HEROES:
                yield m, d, hero, hk, b


def compare(got, want):
    if got == want:
        return []
    i = next(i for i in range(len(want)) if got[i] != want[i])
    return [f"block@{i} got {got[i]:#04x} want {want[i]:#04x}"]


def main():
    nseeds = int(sys.argv[sys.argv.index("--seeds") + 1]) if "--seeds" in sys.argv else 1000
    part, parts = 0, 1
    if "--jobs-split" in sys.argv:
        part, parts = map(int, sys.argv[sys.argv.index("--jobs-split") + 1].split("/"))
    fails = n = 0
    worst = (0, None)
    t0 = time.monotonic()
    with Harness() as h:
        table_check(h)
        h.launch(EMU_ARGS)
        p = T(h)
        p.load()
        p.setup()
        pend = []

        def flush():
            nonlocal fails, n, worst
            outs, ts = p.batch([c[0] for c in pend])
            per = ts // len(pend)
            for (rec, tag, want), out in zip(pend, outs):
                n += 1
                bad = compare(out, want)
                if bad:
                    fails += 1
                    if fails <= 10:
                        print(f"  FAIL {tag}: {bad}", flush=True)
            if per > worst[0]:
                worst = (per, pend[0][1])
            pend.clear()

        for m, d, hero, hk, b in cases(nseeds, part, parts):
            pend.append((bytes(b) + bytes([hk]), f"m{m} d{d} {hero}", expected(b, m, hero)))
            if len(pend) == NSLOT:
                flush()
        if pend:
            flush()
        h.expect(f"G1 items parity {n} levels", fails, 0)
        print(f"G1: {n} levels ({nseeds} seeds / part {part}/{parts}), {fails} fail, "
              f"{time.monotonic() - t0:.0f}s; mean-batch T per level worst {worst}", flush=True)
        # G2: the real level_new path (+ level_populate), a few cases
        g2 = 0
        for m, d, hk in ((0x1234, 1, 0), (0x1234, 1, 1), (0xBEEF, 2, 0), (0x0042, 8, 0),
                         (0x0042, 8, 1), (0x7777, 4, 0), (0x0001, 7, 1)):
            hero = HEROES[hk][0]
            p.load()
            p.wb("HERO_KIND", hk)
            p.wmem(S["MASTER_SEED"], [m & 255, m >> 8])
            stub = [0xF3, 0x31, S["WORKSTORE_TOP"] & 255, S["WORKSTORE_TOP"] >> 8,
                    0x3E, d, 0x21, S["level_new"] & 255, S["level_new"] >> 8,
                    0xCD, S["far3"] & 255, S["far3"] >> 8, 0x00, 0x18, 0xFE]
            p.wmem(DRV, stub)
            end = DRV + 12
            p.z.cmd("set-breakpoint 3 PC=%d" % end)
            p.extra_probes = {end}
            p.z.cmd("set-register PC=%d" % DRV)
            p.z.cmd("run 50000000")
            ok = p.pc() == end
            want = expected(bytes(G.generate(d, M.level_seed(m, d), m)), m, hero)
            bad = ([] if ok else ["did not finish"]) + \
                compare(bytes(p.z.read_memory(S["LVL_STATE"], G.BLOCK_LEN)), want)
            g2 += not bad
            h.expect(f"G2 level_new m{m:#06x} d{d} {hero}", int(bool(bad)), 0)
            if bad:
                print(f"  G2 detail: {bad}", flush=True)
        print(f"G2: {g2}/7 level_new cases ok", flush=True)
        return 1 if fails or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
