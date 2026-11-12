#!/usr/bin/env python3
"""C-T5: ISR-boundary fuzz of the stack blit (docs/design/mirror_c_split.md section 6 "T5").

blit_sprite borrows SP (blit_sp_on .. blit_sp_off, no DI) under the ISR write-back invariant: at every
instruction boundary the word below SP == BC, so an interrupt anywhere must leave the pool bytes
byte-identical and the blit's result unchanged. This test proves it empirically:

  1. A synthetic frame is built in a paged pool bank (random mask/data bytes) behind a poked FRT row, the
     screen bitmap is filled with random bytes, and a real `call blit_sprite` is run to the blit_sp_on
     probe (BC preloaded, SP not yet borrowed): the captured state.
  2. CLEAN run: single-step from the capture to blit_sp_off, recording the PC at every instruction
     boundary (n of them, k = 0 .. n) and the final registers / screen / pool.
  3. For boundary k (all of them, or a sampled set): reload the captured state, `run k` opcodes, inject an
     IM2 by hand exactly as the CPU does (SP -= 2, return PC written at SP, PC = ISR_ADDR; IFF stays off:
     the test runs under DI, so no real interrupt ever fires), run to the ISR's `ei` (isr_jp - 1), set PC
     = the return address (the `ei` is skipped so the host emulator never raises a real interrupt; the
     `jp` is replaced by the PC write), then run to blit_sp_off and compare with the clean run:
       registers (all but R / MEMPTR / IFF), the MMU map ($C000 bank), the screen bitmap, the pool bytes
       of the frame (+ 2 B below / above: the write-back word).
     Not compared (the ISR legitimately changes them): SYS_FRAMES, AY state, isr SMC (isr_rs+1 / isr_jp+1),
     the ISR stack area STACK_BOTTOM..ISR_STK, the free stack words below the caller's SP.

Cases (frame at $C000 -> BC preloaded from $BFFE, and mid-bank), each in both chains (general: fpy not
a multiple of 8, aligned: fpy % 8 == 0): a small sprite, EVERY boundary; a 40x48 shifted sprite (6 byte
columns), a sampled set of >= 200 boundaries.

C-T6: every clean run is also checked against a Python model of the blit (screen = (screen & mask) | data
per byte; mirrored: the row drawn from its last byte column leftwards, mask and data bit-reversed), so a
chain that is ISR-safe but draws the wrong pixels fails too.

Usage: ZRCP_PORT=<port> python3 tests/blit_isr.py [--quick] [--mirror] [--selftest]
  --selftest  mutates the ISR's write-back (push bc -> push hl) and expects the fuzz to FAIL (exit 0 if it does).
  --mirror  C-T6: the same cases through the MIRROR chain (left FRT entry = bank | $80, BL_LEFT 1), plus the
            normal ones (both chains, one run).
Exit status 1 on any mismatch.
"""
import os
import random
import re
import sys
import time

os.environ.setdefault("ZRCP_PORT", "10530")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from game_lib import Harness, Proto, S, EMU_ARGS  # noqa: E402

BREV = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))
STUB = S["LOWRAM_END_3B"]            # test stubs run here (bank 2, never paged)
STACK_TOP = S["WORKSTORE_TOP"]
FRT = S["FRT"]
FRT_STRIDE = S["FRT_STRIDE"]
FT_IN_ROW, FT_COLS, FT_H = S["FT_IN_ROW"], S["FT_COLS"], S["FT_H"]
SP_ON, SP_OFF = S["blit_sp_on"], S["blit_sp_off"]
ISR_ADDR, ISR_EI = S["ISR_ADDR"], S["isr_jp"] - 1       # isr_jp: the exit's `jp`; the `ei` is the byte before
BL_FID, BL_LEFT, BL_FPX, BL_FPY = S["BL_FID"], S["BL_LEFT"], S["BL_FPX"], S["BL_FPY"]
BLIT_CROWS = S["BLIT_CROWS"]
POOL_BANK = 4                         # any RAM bank other than 2 / 3 (BANK_AY) / 5 / 7; its $C000 page is scratch here
FID = 0                               # FRT row poked for the test (the game is never resumed)
BP_END, BP_OFF, BP_EI = 3, 4, 5       # breakpoint slots (1 / 2 = the Proto probes)
SCREEN, SCREEN_LEN = 0x4000, 6144
REGS = ("PC", "SP", "AF", "BC", "DE", "HL", "IX", "IY", "AF'", "BC'", "HL'", "DE'", "I")
rng = random.Random(0x5EED)
IX_CALLER = 0x5A3C                    # IX at the call: blit_sprite must hand it back (mirror2 uses IXL / IXH)


def w16(v):
    return [v & 255, v >> 8]


class Fuzz:
    def __init__(self, h):
        self.p = Proto(h)
        self.z = self.p.z
        self.ncmd = 0

    # --- low-level ----------------------------------------------------------
    def cmd(self, c):
        self.ncmd += 1
        return self.z.cmd(c)

    def regs(self):
        r = self.cmd("get-registers")
        d = {}
        for n in REGS:
            d[n] = int(re.search(r"(?:^|\s)" + re.escape(n) + r"=([0-9a-fA-F]+)", r).group(1), 16)
        d["MMU"] = re.search(r"MMU=([0-9a-fA-F]+)", r).group(1)
        return d

    def set_regs(self, d):
        for n in REGS:
            self.cmd("set-register %s=%d" % (n, d[n]))

    def write(self, addr, data):
        data = bytes(data)
        for i in range(0, len(data), 64):
            self.cmd("write-memory %d %s" % (addr + i, " ".join(str(b) for b in data[i:i + 64])))

    def read(self, addr, n):
        return bytes(self.z.read_memory(addr, n))

    def run_to(self, bp, pc, limit=2000000):
        """Run until `pc` (breakpoint slot bp). The current PC must not already be pc."""
        self.cmd("set-breakpoint %d PC=%d" % (bp, pc))
        r = self.cmd("run %d" % limit)
        self.cmd("set-breakpoint %d" % bp)
        got = int(self.cmd("get-registers")[3:7], 16)
        if got != pc:
            raise RuntimeError("run stopped at %#06x, wanted %#06x: %s" % (got, pc, r[:80]))

    def run_stub(self, code):
        end = STUB + len(code) - 2                      # the trailing jr $
        self.write(STUB, code)
        self.cmd("set-register SP=%d" % STACK_TOP)
        self.cmd("set-register PC=%d" % STUB)
        self.run_to(BP_END, end)

    # --- the case ------------------------------------------------------------
    def setup(self, bank_addr, cols, rows, fpx, fpy, mirror=False):
        """Build the frame + screen and run `call blit_sprite` to blit_sp_on. Returns the capture dict."""
        shifted = bool(fpx & 4)
        width = cols + (1 if shifted else 0)
        size = width * rows * 2
        variant = (3 if shifted else 0) + (6 if mirror else 0)     # C-T6: a mirrored entry is a LEFT one
        # 1. page the pool bank at $C000 (DI first: no real interrupt during the whole test)
        self.run_stub([0xF3, 0x31] + w16(STACK_TOP) + [0x3E, POOL_BANK, 0xCD] + w16(S["page_bank"]) + [0x18, 0xFE])
        # 2. frame bytes (mask, data pairs), the word below the frame, FRT row, blit params
        frame = bytes(rng.randrange(256) for _ in range(size))
        below = bytes(rng.randrange(256) for _ in range(2))
        if bank_addr == 0xC000:
            self.write(0xC000, frame)
            self.write(0xBFFE, below)                    # DH_EFF scratch (bank 2): BC preloads from here
        else:
            self.write(bank_addr - 2, below + frame)
        row = FRT + FID * FRT_STRIDE
        self.write(row + variant, [POOL_BANK | (0x80 if mirror else 0)] + w16(bank_addr))
        self.write(row + FT_IN_ROW + FT_COLS, [cols])
        self.write(row + FT_IN_ROW + FT_H, [rows])
        self.write(BL_FID, [FID])
        self.write(BL_LEFT, [1 if mirror else 0])
        self.write(BL_FPX, [fpx])
        self.write(BL_FPY, [fpy])
        self.write(SCREEN, bytes(rng.randrange(256) for _ in range(SCREEN_LEN)))
        # 3. real call to the probe
        self.write(STUB, [0xCD] + w16(S["blit_sprite"]) + [0x00, 0x18, 0xFE])
        self.cmd("set-register IX=%d" % IX_CALLER)        # C-T6: the mirror chain borrows IX
        self.cmd("set-register SP=%d" % STACK_TOP)
        self.cmd("set-register PC=%d" % STUB)
        self.run_to(BP_END, SP_ON)
        cap = {"regs": self.regs(), "size": size, "addr": bank_addr, "frame": frame, "width": width,
               "rows": rows, "fpx": fpx, "fpy": fpy, "mirror": mirror}
        lo = bank_addr - 2
        cap["pool_lo"], cap["pool_len"] = lo, min(size + 4, 0x10000 - lo)   # the write-back word below + 2 B above (C-F1: none above $FFFF)
        cap["pool"] = self.read(lo, cap["pool_len"])
        cap["screen"] = self.read(SCREEN, SCREEN_LEN)
        cap["crows"] = self.read(BLIT_CROWS, 1)
        assert cap["regs"]["PC"] == SP_ON
        return cap

    def restore(self, cap, dirty_screen):
        """Back to the captured state (screen: only the bytes that changed; pool: rewritten if touched)."""
        for a, b in dirty_screen:
            self.write(a, b)
        self.write(BLIT_CROWS, cap["crows"])
        self.set_regs(cap["regs"])

    @staticmethod
    def diff_runs(base, now, org):
        """[(addr, bytes)] runs where `now` differs from `base`."""
        runs, i, n = [], 0, len(base)
        while i < n:
            if base[i] != now[i]:
                j = i
                while j < n and (base[j] != now[j] or (j + 1 < n and base[j + 1] != now[j + 1])):
                    j += 1
                runs.append((org + i, base[i:j]))
                i = j
            else:
                i += 1
        return runs

    def snapshot(self, cap):
        return {"regs": self.regs(), "pool": self.read(cap["pool_lo"], cap["pool_len"]),
                "screen": self.read(SCREEN, SCREEN_LEN)}

    def clean(self, cap):
        """Single-step capture -> blit_sp_off. Returns (pcs, final snapshot)."""
        pcs = [SP_ON]
        for _ in range(100000):
            r = self.cmd("cpu-step")
            pc = int(r[3:7], 16)
            if pc == SP_OFF:
                break
            pcs.append(pc)
        else:
            raise RuntimeError("clean run never reached blit_sp_off")
        pcs.append(SP_OFF)
        return pcs, self.snapshot(cap)

    def goto(self, k, pcs):
        """Advance k instructions from the capture. `run <k>` is NOT used: ZEsarUX sometimes returns a few
        opcodes early while still reporting k, so the boundary is reached by breakpoint on pcs[k], counting
        its visits (loops revisit a PC once per line) against the clean trace."""
        if k == 0:
            return
        target = pcs[k]
        want = sum(1 for j in range(1, k + 1) if pcs[j] == target)   # visits (after the capture) to reach
        self.cmd("set-breakpoint %d PC=%d" % (BP_OFF, target))
        seen = 0
        pc = int(self.cmd("cpu-step")[3:7], 16)          # also steps off the capture PC (run re-fires on a bp PC)
        while True:
            if pc == target:
                seen += 1
                if seen == want:
                    break
                pc = int(self.cmd("cpu-step")[3:7], 16)  # step off the counted visit
            else:
                self.cmd("run 2000000")                  # a spurious early return lands elsewhere: run on
                pc = int(self.cmd("get-registers")[3:7], 16)
        self.cmd("set-breakpoint %d" % BP_OFF)

    def trial(self, cap, k, pcs, ref, dirty):
        """Restore, run k opcodes, inject the interrupt, finish the blit. Returns (list of differences, dirty)."""
        self.restore(cap, dirty)
        self.goto(k, pcs)
        r = self.regs()
        if r["PC"] != pcs[k]:
            return ["boundary PC %#06x != clean trace %#06x" % (r["PC"], pcs[k])], dirty
        retpc, sp = r["PC"], r["SP"]
        # the CPU's interrupt acknowledge: push PC, jump to the handler (IFF already off)
        self.write((sp - 2) & 0xFFFF, w16(retpc))
        self.cmd("set-register SP=%d" % ((sp - 2) & 0xFFFF))
        self.cmd("set-register PC=%d" % ISR_ADDR)
        self.run_to(BP_EI, ISR_EI)                       # the ISR body + exit up to its `ei`
        self.cmd("set-register PC=%d" % retpc)           # = `ei` + `jp`, without enabling interrupts
        if retpc != SP_OFF:
            self.run_to(BP_OFF, SP_OFF)
        now = self.snapshot(cap)
        bad = []
        for n in REGS:
            if now["regs"][n] != ref["regs"][n]:
                bad.append("%s %#06x != clean %#06x" % (n, now["regs"][n], ref["regs"][n]))
        if now["regs"]["MMU"] != ref["regs"]["MMU"]:
            bad.append("MMU %s != clean %s" % (now["regs"]["MMU"], ref["regs"]["MMU"]))
        if now["pool"] != ref["pool"]:
            idx = [i for i in range(len(ref["pool"])) if now["pool"][i] != ref["pool"][i]]
            bad.append("pool bytes differ at %s" % ["%#06x" % (cap["pool_lo"] + i) for i in idx[:6]])
        if now["screen"] != ref["screen"]:
            idx = [i for i in range(SCREEN_LEN) if now["screen"][i] != ref["screen"][i]]
            bad.append("screen differs at %s (%d bytes)" % (["%#06x" % (SCREEN + i) for i in idx[:6]], len(idx)))
        if now["pool"] != cap["pool"]:                   # a corrupted pool must not poison the next trials
            self.write(cap["pool_lo"], cap["pool"])
        # next restore: the screen bytes this trial changed relative to the capture
        return bad, self.diff_runs(cap["screen"], now["screen"], SCREEN)

    @staticmethod
    def model(cap):
        """The screen the blit must leave: (s & mask) | data per byte; mirrored = row reversed + bit-reversed."""
        scr = bytearray(cap["screen"])
        w, col0, f = cap["width"], cap["fpx"] >> 3, cap["frame"]
        for r in range(cap["rows"]):
            y = cap["fpy"] + r
            base = ((y & 0xC0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2)
            for i in range(w):
                m, d = f[2 * (r * w + i)], f[2 * (r * w + i) + 1]
                if cap["mirror"]:
                    a, m, d = base + col0 + w - 1 - i, BREV[m], BREV[d]
                else:
                    a = base + col0 + i
                scr[a] = (scr[a] & m) | d
        return bytes(scr)

    def run_case(self, name, bank_addr, cols, rows, fpx, fpy, sample, mirror=False):
        t0 = time.monotonic()
        cap = self.setup(bank_addr, cols, rows, fpx, fpy, mirror)
        pcs, ref = self.clean(cap)
        n = len(pcs) - 1
        changed = sum(a != b for a, b in zip(cap["screen"], ref["screen"]))
        sane = ref["pool"] == cap["pool"] and ref["regs"]["SP"] == cap["regs"]["SP"] and changed > 0
        drawn_ok = ref["screen"] == self.model(cap)
        keep = ref["regs"]["IX"] == IX_CALLER and ref["regs"]["IY"] == cap["regs"]["IY"]
        ks = list(range(n + 1))                          # every boundary 0 .. n (n = blit_sp_off itself)
        if sample and sample < len(ks):
            step = len(ks) / sample
            ks = sorted({int(i * step + rng.random() * step) for i in range(sample)} | {0, 1, 2, n - 1, n})
        dirty = self.diff_runs(cap["screen"], ref["screen"], SCREEN)    # the clean run left the screen changed
        fails = []
        for k in ks:
            bad, dirty = self.trial(cap, k, pcs, ref, dirty)
            if bad:
                fails.append((k, pcs[k], bad))
        # leave the screen as the capture for the next case's setup (it rewrites it anyway)
        dt = time.monotonic() - t0
        ok = sane and drawn_ok and keep and not fails
        print("[%s] %-34s n=%4d boundaries, tested %4d, mismatches %d, screen bytes changed %d, %.1fs" % (
            "PASS" if ok else "FAIL", name, n, len(ks), len(fails), changed, dt), flush=True)
        if not sane:
            print("    sanity: clean run left the pool changed, SP moved, or drew nothing", flush=True)
        if not drawn_ok:
            print("    model: the clean run's screen != the Python blit model", flush=True)
        if not keep:
            print("    IX / IY not preserved by the clean run", flush=True)
        for k, pc, bad in fails[:8]:
            print("    boundary %d PC=%#06x: %s" % (k, pc, "; ".join(bad)), flush=True)
        return ok, len(ks), len(fails)


def main():
    quick = "--quick" in sys.argv[1:]
    selftest = "--selftest" in sys.argv[1:]
    mirror = "--mirror" in sys.argv[1:]
    t0 = time.monotonic()
    cases = []
    for mir in ((False, True) if mirror else (False,)):
        tag = "mirror " if mir else ""
        for place, addr in (("$C000", 0xC000), ("mid $D140", 0xD140)):
            # small: 1 data column shifted (width 2), 16 rows (two char rows): every boundary
            cases.append((tag + "small general %s" % place, addr, 1, 16, 4, 20, 0, mir))
            cases.append((tag + "small aligned %s" % place, addr, 1, 16, 4, 16, 0, mir))
            # 40x48 shifted slash (5 data cols + spill = 6): sampled
            cases.append((tag + "40x48 general %s" % place, addr, 5, 48, 44, 20, 40 if quick else 240, mir))
            cases.append((tag + "40x48 aligned %s" % place, addr, 5, 48, 44, 16, 40 if quick else 240, mir))
        # C-F1: the top of the address space: the frame ends at $10000 (SP wraps to 0 after the last pop) and
        # at $FFFE (SP ends there); 1 data col shifted x 16 rows = 64 B; every boundary
        cases.append((tag + "small general ends $10000 (SP wraps)", 0x10000 - 64, 1, 16, 4, 20, 0, mir))
        cases.append((tag + "small aligned ends $10000 (SP wraps)", 0x10000 - 64, 1, 16, 4, 16, 0, mir))
        cases.append((tag + "small general ends $FFFE", 0xFFFE - 64, 1, 16, 4, 20, 0, mir))
        # C-F1: an 8-row frame (one char row) not char-aligned: 8 - (fpy & 7) = 4 lines, then 4 (the mirror
        # chain's BLIT_CROWS split; BLIT_CROWS = 4 after the first segment)
        cases.append((tag + "8-row fpy 20 (fpy&7 = 4)", 0xD140, 1, 8, 4, 20, 0, mir))
        cases.append((tag + "8-row fpy 23 (fpy&7 = 7)", 0xD140, 1, 8, 4, 23, 0, mir))
        if mir:
            # unshifted, 3 cols, fpy 7 (1-line first segment, 7-line last), col 0: every boundary
            cases.append(("mirror 24x16 unshifted fpy 7 col 0", 0xD140, 3, 16, 0, 7, 0, True))
    ok_all, total, nbad = True, 0, 0
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = Proto(h)
        p.boot()                                           # a playing game: bank 2 / 3 / 5 / 7 state as in play
        f = Fuzz(h)
        if selftest:
            assert f.read(ISR_ADDR + 5, 1) == b"\xc5"           # ex (sp),hl / ld (nn),hl / pop hl / push bc
            f.write(ISR_ADDR + 5, [0xE5])                        # push hl: the write-back stores the wrong word
            cases = [c for c in cases if c[7] == mirror][:2]
        for c in cases:
            ok, n, b = f.run_case(*c)
            ok_all &= ok
            total += n
            nbad += b
        print("[%s] blit_isr: %d boundaries, %d mismatches, %d ZRCP commands, %.0fs" % (
            "PASS" if ok_all else "FAIL", total, nbad, f.ncmd, time.monotonic() - t0), flush=True)
    if selftest:
        print("[%s] selftest: the mutated ISR %s" % ("PASS" if not ok_all else "FAIL",
              "was caught" if not ok_all else "was NOT caught"))
        return 0 if not ok_all else 1
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
