#!/usr/bin/env python3
"""INSTR-BUILD: the two-page HOW TO PLAY screen (instr_ovl.asm; game.md §3.2.1 option A
flow, pages per docs/design/instructions_screen.md / .txt).
  I1  page 1 (GS_HELP1) bitmap + attrs == the approved render model (tools/gen_instr_mock.py
      page(1), same spec as the build: tools/instr_pack.py) byte for byte
  I2  the page-1 key still held: no page 2 until it is released (no timeout either)
  I3  page 2 (GS_HELP2) == page(2) byte for byte
  I4  page 2's key ('1') -> menu, swallowed (no START), menu answers a real press
  I5  BREAK on page 1 skips page 2 -> menu (GS_SELECT), never GS_HELP2
  I6  static: the boot pool's start (POOL_START) equals the page-1 stream label, i.e. the
      pool is laid over the streams; that it only runs after the help screens is not
      checked here (resident cost: build DISPLAYs)
The reference is a model, not a stored hash: a golden is the approved render itself.
   ZRCP_PORT=<port> python3 tests/instr.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import game_lib  # noqa: E402
from game_lib import (Harness, Proto, S, EMU_ARGS, GS_SELECT, GS_ANYKEY, GS_PLAYING,  # noqa: E402
                      GS_HELP1, GS_HELP2)
import gen_instr_mock  # noqa: E402  (render model; main() only runs as a script)


def model(n):
    """Expected 6912 screen bytes of page n (Spectrum bitmap layout + attrs)."""
    s = gen_instr_mock.page(n)
    out = bytearray(6912)
    for y in range(192):
        for xb in range(32):
            v = 0
            for b in range(8):
                v = v << 1 | int(s.bm[y, xb * 8 + b])
            out[((y & 0xC0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2) | xb] = v
    for r in range(24):
        for c in range(32):
            out[6144 + r * 32 + c] = int(s.at[r, c])
    return bytes(out)


def screen(p):
    return bytes(p.z.read_memory(0x4000, 6912))


def diffs(a, b):
    d = [i for i in range(6912) if a[i] != b[i]]
    cells = sorted({((i >> 3 & 0x18) | (i >> 5 & 7), i & 31) if i < 6144 else
                    ((i - 6144) >> 5, (i - 6144) & 31) for i in d})
    return len(d), cells[:8]


def tap(p, *keys):
    p.hold(*keys)
    p.tick(2)
    p.release()


def to_page1(p):
    p.load()
    p.wb("INPUT_SRC", 1)
    ok = p.until(lambda: p.rb("GAME_STATE") == GS_ANYKEY, 600)
    p.wb("INPUT_SRC", 1)
    p.release()
    p.tick(2)
    tap(p, "ENTER")
    ok = ok and p.until(lambda: p.rb("GAME_STATE") == GS_HELP1, 60)
    p.tick(3)                                 # drawn; its 'all released once' seen
    return ok


def main():
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = Proto(h)
        h.expect("I0 boot -> picture wait -> page 1", to_page1(p), True)
        n, cells = diffs(screen(p), model(1))
        h.expect("I1 page 1 == approved render (%d bytes differ, cells %s)" % (n, cells), n, 0)
        # I2: hold a key on page 1 for a while: page 2 only after the release
        p.hold("Q")
        p.tick(15)
        h.expect("I2 page-1 key held: still page 1", p.rb("GAME_STATE"), GS_HELP1)
        p.release()
        ok = p.until(lambda: p.rb("GAME_STATE") == GS_HELP2, 60)
        h.expect("I2b released -> page 2", ok, True)
        p.tick(25)
        h.expect("I3a no timeout on page 2", p.rb("GAME_STATE"), GS_HELP2)
        n, cells = diffs(screen(p), model(2))
        h.expect("I3 page 2 == approved render (%d bytes differ, cells %s)" % (n, cells), n, 0)
        p.hold("1")
        ok = p.until(lambda: p.rb("GAME_STATE") == GS_SELECT, 60)
        h.expect("I4 page 2 key -> menu", ok, True)
        p.tick(12)
        h.expect("I4b '1' swallowed: no START", p.rb("GAME_STATE"), GS_SELECT)
        pool = S["POOL_START"]
        p.release()
        p.tick(3)
        h.expect("I4c menu answers a real press", (p.hold("1"), p.wait_state(GS_PLAYING, 200))[1], True)
        # I5: BREAK on page 1 -> straight to the menu
        h.expect("I5a reload -> page 1", to_page1(p), True)
        seen = set()
        p.hold("CAPS", "SPACE")
        for _ in range(4):
            p.tick()
            seen.add(p.rb("GAME_STATE"))
        p.release()
        ok = p.until(lambda: (seen.add(p.rb("GAME_STATE")), p.rb("GAME_STATE") == GS_SELECT)[1], 80)
        h.expect("I5 BREAK on page 1 -> menu", ok, True)
        h.expect("I5b page 2 never shown (states %s)" % sorted(seen), GS_HELP2 in seen, False)
        # I6: the boot pool (2 idles) starts at POOL_START = the first stream byte
        h.expect("I6 POOL_START = the page-1 stream (boot pool overwrites the help)",
                 pool == S["instr_p1_zx0"], True)
    print("instr:", "OK" if h.ok else "FAIL %s" % h.failures)
    return 0 if h.ok else 1


if __name__ == "__main__":
    sys.exit(main())
