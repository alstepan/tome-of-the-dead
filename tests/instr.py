#!/usr/bin/env python3
"""INSTR-BUILD / INSTR-P3: the two-page HOW TO PLAY screen (instr_ovl.asm; game.md §3.2.1 option A
flow, pages per docs/design/instructions_screen.md / .txt).
  I1  page 1 (GS_HELP1) bitmap + attrs == the approved render model (tools/gen_instr_mock.py
      page(1), same spec as the build: tools/instr_pack.py) byte for byte
  I2  the page-1 key still held: no page 2 until it is released (no timeout either)
  I9  page 2 (GS_HELP3, TREASURES; TUT0-T2 dropped the items page, GS_HELP2 unused) == page(2)
      byte for byte (differing rows reported)
  I9a icon cells: 13 records, 32 bitmap bytes + 4 attrs each, text attr beside them (cells 2 / 18)
  I9b empty half (rows 17-18 cells 16-31; rows 14, 18 outside the icons)
  I9c full-width rows 03 / 05 (cells 15, 16, 31)
  I9d plain rows 01 / 11 / 19 zero, 20-22 attr $05, 23 == the footer model
  I4  page 2's key ('1') -> menu, swallowed (no START), menu answers a real press
  I5  BREAK on page 1 skips page 2 -> menu (GS_SELECT), never GS_HELP3
  I6  static: the boot pool's start (POOL_START) equals the frame_tab stream (RECLAIM-D), page 1 right after it, i.e. the
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
                      GS_HELP1, GS_HELP2, GS_HELP3)
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


def bad_rows(a, b):
    """Character rows (0..23) whose bitmap or attrs differ."""
    r = set()
    for i in range(6912):
        if a[i] != b[i]:
            r.add(((i >> 5 & 7) + (i >> 11 & 3) * 8) if i < 6144 else (i - 6144) >> 5)
    return sorted(r)


def cell(scr, r, c):
    """The 8 bitmap bytes of cell (r, c)."""
    return bytes(scr[((r & 24) << 8) | ((r & 7) << 5) | (y << 8) | c] for y in range(8))


def at(scr, r, c):
    return scr[6144 + r * 32 + c]


def icons_ok(h, scr):
    """I9a-d on a page-2 screen dump (decoded icons from the render model's source tables)."""
    import instr_pack
    bad, rowat = [], {3: 0x47, 4: 0x47, 5: 0x45, 6: 0x45, 7: 0x47, 8: 0x47, 9: 0x45, 10: 0x45,
                      13: 0x47, 14: 0x47, 15: 0x45, 16: 0x45, 17: 0x47, 18: 0x47}
    for ic in instr_pack.PAGES[2]["icons"]:
        _, name, r, c, a = ic
        bm = gen_instr_mock.icon16(name)
        for i, (dr, dc) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
            want = bytes(sum(int(bm[dr * 8 + y, dc * 8 + x]) << (7 - x) for x in range(8)) for y in range(8))
            if cell(scr, r + dr, c + dc) != want or at(scr, r + dr, c + dc) != a:
                bad.append((name, i))
        for dr in (0, 1):
            for cc in (c + 2,):
                if at(scr, r + dr, cc) != rowat[r + dr]:
                    bad.append((name, "textattr", r + dr, cc))
    h.expect("I9a 13 icon records: bitmap + attr + beside-text attr (bad %s)" % bad[:6], len(bad), 0)
    z = [(r, c) for r in (17, 18) for c in range(16, 32) if any(cell(scr, r, c)) or at(scr, r, c) != 0x47]
    z += [(14, c) for c in range(32) if not (c < 2 or 16 <= c < 18) and any(cell(scr, 14, c))]
    z += [(18, c) for c in range(2, 32) if any(cell(scr, 18, c))]
    h.expect("I9b empty half / icon-only rows clean (bad %s)" % z[:6], len(z), 0)
    c3 = [any(cell(scr, 3, c)) for c in (16, 31)] + [any(cell(scr, 5, c)) for c in (15, 16, 31)]
    h.expect("I9c rows 03 (16,31) / 05 (15,16,31) filled %s" % c3, int(all(c3)), 1)
    pl = [(r, c) for r in (1, 11, 19) for c in range(32) if any(cell(scr, r, c)) or at(scr, r, c)]
    pl += [(r, c) for r in (20, 21, 22) for c in range(32) if at(scr, r, c) != 0x05]
    m = model(2)
    pl += [(23, c) for c in range(32) if cell(scr, 23, c) != cell(m, 23, c)]
    h.expect("I9d plain rows (bad %s)" % pl[:6], len(pl), 0)


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
        ok = p.until(lambda: p.rb("GAME_STATE") == GS_HELP3, 60)
        h.expect("I2b released -> page 2 (TREASURES, GS_HELP3)", ok, True)
        p.tick(25)
        h.expect("I9t no timeout on page 2", p.rb("GAME_STATE"), GS_HELP3)
        n, cells = diffs(screen(p), model(2))
        h.expect("I9 page 2 == approved render (%d bytes differ, cells %s, rows %s)" % (
                 n, cells, bad_rows(screen(p), model(2))), n, 0)
        scr = screen(p)
        icons_ok(h, scr)
        p.hold("1")
        ok = p.until(lambda: p.rb("GAME_STATE") == GS_SELECT, 60)
        h.expect("I4 page 2 key -> menu", ok, True)
        p.tick(12)
        h.expect("I4b '1' swallowed: no START", p.rb("GAME_STATE"), GS_SELECT)
        pool = S["POOL_START"]
        p.release()
        p.tick(3)
        p.tut_off()                               # TUT0-T6b: '1' now opens the choice screen
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
        h.expect("I5b page 2 never shown (states %s)" % sorted(seen), GS_HELP3 in seen, False)
        # I6: the boot pool (2 idles) starts at POOL_START = the first boot-only stream byte
        # (RECLAIM-D: the frame_tab stream ftz_zx0, then page 1 right after it)
        h.expect("I6 POOL_START = the frame_tab stream, then page 1 (boot pool overwrites them)",
                 pool == S["ftz_zx0"] and S["ftz_zx0_end"] == S["instr_p1_zx0"], True)
    print("instr:", "OK" if h.ok else "FAIL %s" % h.failures)
    return 0 if h.ok else 1


if __name__ == "__main__":
    sys.exit(main())
