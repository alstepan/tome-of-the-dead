#!/usr/bin/env python3
"""3F-B1 ERASE-AIR: erase_rect's T_AIR path (src/gfx.asm .air) writes 8 zero lines without
reading the glyph, so TILE_GLYPHS[0..7] (tile id 0) MUST stay all zero for the whole game.
Build time: ASSERT in src/boot6.asm (tiles_common). Here (runtime): the 8 bytes are zero after
the start, every tick of a walk, a pause, a page, and the screen == the map (bg_mismatch).

  EA1 TILE_GLYPHS[0..7] == 0 at the start of a game (both heroes)
  EA2 ... on every tick of a walk, after a pause and after a page; the screen matches the map
Run: ZRCP_PORT=<port> python3 tests/eraseair.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.argv = [sys.argv[0], "999"]               # keep game.py's item filter inert
import game  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD  # noqa: E402

G0 = S["TILE_GLYPHS"]


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

        def zero():
            return [p.rb(G0 + i) for i in range(8)] == [0] * 8

        def pause():
            p.hold("CAPS", "SPACE")
            p.until(lambda: p.rb("PAUSED") == 1, 60)
            p.release()
            p.tick(4)
            p.hold("SPACE")
            p.tick(3)
            p.release()
            p.until(lambda: p.rb("PAUSED") == 0, 200)

        def page():
            p.tap("I")
            p.until(lambda: p.rb("PAGE_OPEN") == 1, 20)
            p.tick(4)
            p.tap("I")
            p.until(lambda: p.rb("PAGE_OPEN") == 0, 20)

        for hero, name in ((K_KNIGHT, "knight"), (K_WIZARD, "wizard")):
            p.boot(hero)
            check(f"EA1 {name}: TILE_GLYPHS[0..7] == 0 at the start", zero())
            check(f"EA1 {name}: screen == map", not p.bg_mismatch(), p.bg_mismatch()[:4])
            bad = 0
            for _ in range(24):
                p.hold("P")
                p.tick(1)
                bad += 0 if zero() else 1
            p.release()
            p.settle()
            check(f"EA2 {name}: zero on every tick of a walk, screen == map", bad == 0 and not p.bg_mismatch(),
                  (bad, p.bg_mismatch()[:4]))
            pause()
            p.settle(3)
            check(f"EA2 {name}: zero + screen == map after a pause", zero() and not p.bg_mismatch())
            page()
            p.settle(3)
            check(f"EA2 {name}: zero + screen == map after a page", zero() and not p.bg_mismatch())
    print(f"eraseair: {len(fails)} failed" + (f": {fails}" if fails else ""), flush=True)
    return 1 if fails or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
