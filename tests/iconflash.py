#!/usr/bin/env python3
"""ICON-FLASH (user 2026-11-18): a book that LEARNS a new ability (rank 0 -> 1) flashes that icon slot's 6 attr cells
(rows 18-19, cols 3 * slot..+2, hardware FLASH = attr bit 7) for ICON_FLASH_FR = 100 frames, independent of turns.
src/sv_r4.asm ic_learn (fx_book's .learn: far7 abil_learn, then arm ICON_FL / ICON_FLT), src/icfl_l.asm ic_fl (icon_poll's
hook), R4 ic_mark. Release build (-DDEBUG_KIT=0), PROTO room A.

  F1  a NEW ability (ARANK 0, k 0): ICON_FL = 3 * (k + 1) = 3, ICON_FLT = SYS_FRAMES; the 6 cells of the DISPLAYED screen carry
      bit 7 within a few ticks (after the icon redraw), the icon's pixels are there (the slot was drawn)
  F2  >= ICON_FLASH_FR frames later: ICON_FL = 0 and the 6 cells have bit 7 clear again (the slot's own attr back)
  F3  a RANK-UP (k already rank >= 1): no flash (ICON_FL 0, no bit 7)
  F4  the 2nd new ability (k 1, a Mage's Firebolt): its own slot (col 6), the first slot's cells are not flashing
  F5  D0 (item_depth's digit operand = '0' - 1, the tutorial's marker): a new ability arms nothing
  F6  level_reset clears ICON_FL; the 6 cells are redrawn without FLASH by panel_init
Run: ZRCP_PORT=<port> python3 tests/iconflash.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
import game_lib  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, K_WIZARD, attr_at, cell_bytes  # noqa: E402
from lp import T as LPT, w16  # noqa: E402

DRV = S["GEN_SRC"] + 0x2C0      # the play-free stub window (as nm3b.py): the low-RAM stub room is tiny now


class T(LPT):
    def code(self, body, limit=20000000):
        """nm3b.Proto.code(game=True): DI, body, EI, at DRV; -> ok."""
        code = bytes([0xF3] + body + [0xFB, 0x00, 0x18, 0xFE])
        end = DRV + len(code) - 3
        self.z.cmd("write-memory %d %s" % (DRV, " ".join(str(b) for b in code)))
        self.z.cmd("set-breakpoint 3 PC=%d" % end)
        self.extra_probes = {end}
        pc0 = self.pc()
        self.z.cmd("set-register PC=%d" % DRV)
        self.z.cmd("run %d" % limit)
        ok = self.pc() == end
        self.z.cmd("set-breakpoint 3")
        self.extra_probes = set()
        self.z.cmd("set-register PC=%d" % pc0)
        return ok

KIT = bool(S.get("KIT_DEBUG", 0))
ROW = S["ICON_ROW"]  # 18
FR = S["ICON_FLASH_FR"]


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:600]}", flush=True)

        if KIT:
            print("[skip] iconflash needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(h, p, check)
        print(f"iconflash: {len(fails)} failed" + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def run(h, p, check):
    p.boot(K_WIZARD)

    def frames():
        return p.rb("SYS_FRAMES") | p.rb(S["SYS_FRAMES"] + 1) << 8

    def flash_cells(col, f=None):
        f = f or p.frame()
        return [bool(attr_at(f, c, r) & 0x80) for r in (ROW, ROW + 1) for c in range(col, col + 3)]

    def learn(k):
        ok = p.code([0x3E, k, 0xCD] + w16(S["ic_learn"]))
        assert ok, "ic_learn stub did not return"

    def settle(n=8):
        p.tick(n)

    # F1 the first ability (the starter read): Mage k 0 = Spark, slot 1, cols 3..5
    p.wmem(S["ARANK"], [0, 0])
    t0 = frames()
    learn(0)
    check("F1 new ability k 0: ICON_FL = 3, ICON_FLT ~ SYS_FRAMES", p.rb("ICON_FL") == 3 and abs(p.rw("ICON_FLT") - t0) < 40,
          (p.rb("ICON_FL"), p.rw("ICON_FLT"), t0))
    settle()
    f = p.frame()
    check("F1 the 6 cells (3..5, rows 18-19) FLASH on the displayed screen", all(flash_cells(3, f)), flash_cells(3, f))
    check("F1 the Spark icon is drawn there (pixels in every cell)", all(any(cell_bytes(f, c, r)) for r in (ROW, ROW + 1) for c in range(3, 6)))
    check("F1 no other icon slot flashes", not any(flash_cells(6, f) + flash_cells(0, f) + flash_cells(9, f)))
    # F2 elapsed
    n = 0
    while frames() - t0 < FR + 6 and n < 400:
        p.tick(4)
        n += 1
    settle(4)
    f = p.frame()
    check(f"F2 after >= {FR} frames: ICON_FL = 0, the 6 cells FLASH-free", p.rb("ICON_FL") == 0 and not any(flash_cells(3, f)),
          (p.rb("ICON_FL"), flash_cells(3, f)))
    # F3 a rank-up: no flash
    learn(0)                                             # ARANK now has k 0 at rank 1: this is a rank-up (L = 2)
    settle()
    check("F3 a rank-up of a known ability: no flash", p.rb("ICON_FL") == 0 and not any(flash_cells(3)), (p.rb("ICON_FL"), flash_cells(3)))
    # F4 the next new ability: its own slot
    learn(1)
    settle()
    f = p.frame()
    check("F4 Firebolt (k 1) learned: ICON_FL = 6, cols 6..8 flash, cols 3..5 do not",
          p.rb("ICON_FL") == 6 and all(flash_cells(6, f)) and not any(flash_cells(3, f)), (p.rb("ICON_FL"), flash_cells(6, f), flash_cells(3, f)))
    # F5 D0: the tutorial's marker
    p.wb("ICON_FL", 0)
    p.wmem(S["ARANK"], [0, 0])
    keep = p.rb(S["item_depth.d"] + 1)
    p.wb(S["item_depth.d"] + 1, ord("0") - 1)
    learn(2)
    check("F5 D0 (the item_depth digit marker): a new ability arms nothing", p.rb("ICON_FL") == 0, p.rb("ICON_FL"))
    p.wb(S["item_depth.d"] + 1, keep)
    # F6 level_reset clears an armed flash
    p.wb("ICON_FL", 6)
    ok = p.code([0x21] + w16(S["level_reset"]) + [0xCD] + w16(S["far3"]))
    check("F6 level_reset (far3) clears ICON_FL", ok and p.rb("ICON_FL") == 0, (ok, p.rb("ICON_FL")))


if __name__ == "__main__":
    sys.exit(main())
