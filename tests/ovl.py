#!/usr/bin/env python3
"""3E-T1 overlays: ovl_run (src/lowram.asm), the GEN_SCRATCH window
(docs/memory-map.md "Overlays"). Drives build/wazhack.sna in ZEsarUX.

  O1  a self-test overlay (assembled here, test_overlay(): 3E-T2 dropped the
      built-in src/ovl_test.asm once the bag page overlay existed; tests/page.py
      round-trips that one), packed with tools/bin/zx0, poked into the free
      bank-1 tail and run through ovl_run from a low-RAM stub at the menu under
      DI, with bank 3 paged, IX = $4321 and a stale GEN_ZBLK: the unpacked
      image == the raw bytes (round trip), the overlay was entered with the caller's bank (3) and IX,
      BC / DE / HL / IX pass out, the caller's bank is paged afterwards
      although the overlay paged bank 4, the screen bit is kept, GEN_ZBLK = 0,
      and the whole 128K RAM differs from before only in the overlay image,
      the stub / result bytes, GEN_ZBLK, the shadow-free stack bytes
  O2  a 1,536-B (= GEN_SCRATCH_LEN) pseudo-random + repetitive overlay packed
      here with tools/bin/zx0, poked into the free bank-1 tail, run with
      interrupts ON from bank 0: round trip == the raw bytes, bank 0 back,
      nothing outside the window / ISR-owned bytes changed; reports T
Run: ZRCP_PORT=<port> python3 tests/ovl.py
"""
import os
import random
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.argv = [sys.argv[0], "999"]               # keep game.py's item filter inert
import game  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, GS_SELECT  # noqa: E402

BANK = 16384
STUB = S["LOWRAM_END_3B"]                     # free low RAM (the other suites' stub org)
RES = STUB + 0xC0                             # result bytes


def w(v):
    return [v & 255, v >> 8]


def ram128(p):
    p.z.cmd("set-memory-zone 0")
    try:
        return bytes(p.z.read_memory(0, 8 * BANK))
    finally:
        p.z.cmd("set-memory-zone -1")


def bank_write(p, b, addr, data):
    p.z.cmd("set-memory-zone 0")
    try:
        o = b * BANK + addr - 0xC000
        for i in range(0, len(data), 256):
            p.z.cmd("write-memory %d %s" % (o + i, " ".join(map(str, data[i:i + 256]))))
    finally:
        p.z.cmd("set-memory-zone -1")


def lin(addr, bank_c000=None):
    """Linear zone-0 offset of a mapped address ($4000 bank 5, $8000 bank 2)."""
    if 0x4000 <= addr < 0x8000:
        return 5 * BANK + addr - 0x4000
    if 0x8000 <= addr < 0xC000:
        return 2 * BANK + addr - 0x8000
    return bank_c000 * BANK + addr - 0xC000


def diffs(a, b, allowed):
    """Offsets where a != b outside the allowed [lo, hi) zone-0 ranges."""
    out = []
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y and not any(lo <= i < hi for lo, hi in allowed):
            out.append(i)
    return out


def stub_code(caller_bank, blob, blob_bank, ix, di):
    sh = S["PORT_7FFD_SHADOW"]
    return ([0xF3] if di else []) + (
        [0x3A] + w(sh) + [0xF5] +                                  # ld a,(sh) / push af
        [0x3E, caller_bank, 0xCD] + w(S["page_bank"]) +
        [0x21] + w(0xFFFF) + [0x22] + w(S["GEN_ZBLK"]) +           # a stale cache key
        [0xDD, 0x21] + w(ix) +
        [0x21] + w(blob) + [0x0E, blob_bank] + [0x11] + w(S["GEN_SCRATCH"]) +
        [0xCD] + w(S["ovl_run"]) +
        [0xED, 0x43] + w(RES) + [0xED, 0x53] + w(RES + 2) + [0x22] + w(RES + 4) +
        [0xDD, 0x22] + w(RES + 6) +
        [0x3A] + w(sh) + [0x32] + w(RES + 8) +
        [0xF1, 0xCD] + w(S["restore_page"]))                       # the menu's bank back


def zx0_pack(raw):
    with tempfile.TemporaryDirectory() as td:
        fi, fo = os.path.join(td, "o.bin"), os.path.join(td, "o.zx0")
        open(fi, "wb").write(raw)
        subprocess.run([os.path.join(REPO, "tools", "bin", "zx0"), "-f", fi, fo], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return open(fo, "rb").read()


def test_overlay():
    """The old src/ovl_test.asm at GEN_SCRATCH: records the shadow at entry and
    IX (3 result bytes at its end), pages BANK_POOL1, returns BC $9ABC,
    DE $5678, HL $1234. Returns (raw bytes, result offset)."""
    org = S["GEN_SCRATCH"]
    res = org + 25
    code = ([0x3A] + w(S["PORT_7FFD_SHADOW"]) + [0x32] + w(res) +
            [0xDD, 0x22] + w(res + 1) + [0x3E, S["BANK_POOL1"], 0xCD] + w(S["page_bank"]) +
            [0x01, 0xBC, 0x9A, 0x11, 0x78, 0x56, 0x21, 0x34, 0x12, 0xC9])
    assert len(code) == 25
    return bytes(code + [0, 0, 0]), 25


def run(p, check):
    p.load()
    p.wait_state(GS_SELECT)
    p.tick(2)
    sh0 = p.rb("PORT_7FFD_SHADOW")
    st = S["STACK_BOTTOM"], S["WORKSTORE_TOP"]
    stack = (lin(st[0]), lin(st[1]))
    stub_r = (lin(STUB), lin(RES + 16))
    zblk = (lin(S["GEN_ZBLK"]), lin(S["GEN_ZBLK"]) + 2)

    # ---- O1: the built-in overlay ------------------------------------------
    raw, res_off = test_overlay()
    n = len(raw)
    packed1 = zx0_pack(raw)
    # R6 (2026-10-21): O1 streams from the free R6 tail (bank 6, C = BANK_R6),
    # like the page / items overlays now; O2 from the free bank-1 tail
    tail = S["r6_end"]
    check("O1 packed self-test overlay fits the free R6 tail", tail + len(packed1) <= 0x10000)
    bank_write(p, S["BANK_R6"], tail, list(packed1))
    code = stub_code(S["BANK_COLD3"], tail, S["BANK_R6"], 0x4321, True)
    before = ram128(p)
    pc0 = p.pc()
    ok = p.run_stub(code, org=STUB)
    after = ram128(p)
    check("O1 stub ran (ovl_run returned)", ok)
    img = bytes(p.z.read_memory(S["GEN_SCRATCH"], n))
    check("O1 round trip: GEN_SCRATCH == the raw overlay (bar its 3 result bytes)",
          img[:res_off] == raw[:res_off], img.hex())
    r = p.z.read_memory(RES, 9)
    check("O1 the overlay ran with the caller's bank (3) and IX $4321",
          (img[res_off] & 7, img[res_off + 1] | img[res_off + 2] << 8) == (S["BANK_COLD3"], 0x4321),
          (img[res_off], img[res_off + 1:res_off + 3].hex()))
    check("O1 BC / DE / HL / IX pass out", (r[0] | r[1] << 8, r[2] | r[3] << 8, r[4] | r[5] << 8,
                                            r[6] | r[7] << 8) == (0x9ABC, 0x5678, 0x1234, 0x4321),
          r.hex() if hasattr(r, "hex") else r)
    check("O1 caller's bank (3) paged after ovl_run although the overlay paged bank 4; "
          "screen bit kept", (r[8] & 7, r[8] & 0x18) == (S["BANK_COLD3"], sh0 & 0x18), (hex(r[8]), hex(sh0)))
    check("O1 GEN_ZBLK cleared (stale key $FFFF poked before)", p.rw("GEN_ZBLK") == 0, p.rw("GEN_ZBLK"))
    win = (lin(S["GEN_SCRATCH"]), lin(S["GEN_SCRATCH"]) + n)
    blob = (lin(tail, S["BANK_R6"]), lin(tail, S["BANK_R6"]) + len(packed1))
    bad = diffs(before, after, [win, stack, stub_r, zblk, blob])
    check("O1 nothing else in the 128K RAM changed (window, stub, GEN_ZBLK, stack aside; DI)",
          bad == [], [hex(x) for x in bad[:12]])
    p.z.cmd("set-register PC=%d" % pc0)

    # ---- O2: a full-window blob, interrupts on ------------------------------
    rnd = random.Random(0x3E71)
    big = bytearray([0xC9])                       # ret
    L = S["GEN_SCRATCH_LEN"]
    while len(big) < L:
        if rnd.random() < 0.5 and len(big) > 16:  # a back-reference
            o = rnd.randrange(1, min(len(big), 600))
            k = rnd.randrange(2, 24)
            for _ in range(k):
                big.append(big[-o])
        else:
            big.extend(rnd.randrange(256) for _ in range(rnd.randrange(1, 12)))
    big = bytes(big[:L])
    packed = zx0_pack(big)
    tail = S["bank1_end"]
    check("O2 packed blob fits the free bank-1 tail", tail + len(packed) <= 0x10000,
          (hex(tail), len(packed)))
    bank_write(p, S["BANK_UI1"], tail, list(packed))
    code = stub_code(S["BANK_POOL0"], tail, S["BANK_UI1"], 0, False)
    before = ram128(p)
    pc0 = p.pc()
    p.z.cmd("reset-tstates-partial")
    ok = p.run_stub(code, org=STUB)
    t = int(p.z.cmd("get-tstates-partial"))
    after = ram128(p)
    check("O2 stub ran (EI)", ok)
    img = bytes(p.z.read_memory(S["GEN_SCRATCH"], L))
    check("O2 round trip: %d raw B (%d packed) == GEN_SCRATCH" % (L, len(packed)), img == big,
          sum(a != b for a, b in zip(img, big)))
    r = p.z.read_memory(RES, 9)
    check("O2 caller's bank (0) paged after ovl_run", r[8] & 7 == S["BANK_POOL0"], hex(r[8]))
    win = (lin(S["GEN_SCRATCH"]), lin(S["GEN_SCRATCH"]) + L)
    isr = [(lin(S["ay_vars"], 3), lin(S["ay_vars_end"], 3)),          # the ISR's own bytes
           (lin(S["SYS_FRAMES"]), lin(S["SYS_FRAMES"]) + 3), (lin(S["AY_CALLS"]), lin(S["AY_CALLS"]) + 2),
           (lin(S["SND_MODE"]), lin(S["SFX_NEXT"]) + 1)]                   # the mailbox
    bad = diffs(before, after, [win, stack, stub_r, zblk] + isr)
    check("O2 nothing else changed (window, stub, GEN_ZBLK, stack, ISR-owned bytes aside)",
          bad == [], [hex(x) for x in bad[:12]])
    print(f"[info] O2 ovl_run of {L} raw / {len(packed)} packed B: {t} T for the whole stub "
          f"(~{t / L:.1f} T per raw byte, ISR time included)", flush=True)
    p.z.cmd("set-register PC=%d" % pc0)


def alloc_r6(p, check):
    """R1 (R6, 2026-10-21): the pool allocator stops at R6_ADDR in bank 6 (the
    permanent R6 region above it) and still fills banks 0 / 4 up to $10000."""
    p.load()
    p.wait_state(GS_SELECT)
    idx, ptr, al = S["ALLOC_IDX"], S["ALLOC_PTR"], S["alloc"]

    def case(i, at, n):
        code = ([0x3E, i, 0x32] + w(idx) + [0x21] + w(at) + [0x22] + w(ptr) +
                [0x01] + w(n) + [0xCD] + w(al) + [0xF5, 0x22] + w(RES) + [0xE1, 0x22] + w(RES + 2))
        ok = p.run_stub(code, org=STUB)
        r = p.z.read_memory(RES, 4)
        return ok, r[0] | r[1] << 8, r[3], r[2] & 1, p.rb("ALLOC_IDX"), p.rw("ALLOC_PTR")
    r6 = S["R6_ADDR"]
    check("R1 bank 6: an allocation ending exactly at R6_ADDR fits (bank 6, ptr -> R6_ADDR)",
          case(2, r6 - 100, 100) == (True, r6 - 100, S["BANK_R6"], 0, 2, r6), case(2, r6 - 100, 100))
    got = case(2, r6 - 100, 101)
    check("R1 bank 6: one byte into R6 = pool full (CF, ALLOC_IDX 3)", got[0] and got[3:5] == (1, 3), got)
    check("R1 bank 4: an allocation ending exactly at $10000 fits, next bank opens",
          case(1, 0xFF00, 0x100) == (True, 0xFF00, S["BANK_POOL1"], 0, 2, 0xC000), case(1, 0xFF00, 0x100))
    got = case(0, 0xFF00, 0x101)
    check("R1 bank 0: past $10000 -> the next bank (4) from $C000",
          got == (True, 0xC000, S["BANK_POOL1"], 0, 1, 0xC101), got)


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = game.T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:600]}", flush=True)

        run(p, check)
        alloc_r6(p, check)
        print(f"ovl: {len(fails)} failed" + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
