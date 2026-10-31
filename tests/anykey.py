#!/usr/bin/env python3
"""BOOT-ANYKEY: after boot the loading picture stays up (music playing) until a
key; the menu then appears and the key is swallowed (boot6_wait, boot6.asm).
The .sna does not hold the loading screen (the tape's SCREEN$ block is not in
it), so the test pokes assets/gfx/loading/loading_l3c.scr into $4000 first.
   ZRCP_PORT=<port> python3 tests/anykey.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game_lib  # noqa: E402
from game_lib import Harness, Proto, S, EMU_ARGS, GS_SELECT, GS_ANYKEY, GS_PLAYING  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCR = open(os.path.join(REPO, "assets/gfx/loading/loading_l3c.scr"), "rb").read()


def poke(p, addr, data):
    for i in range(0, len(data), 1024):
        chunk = data[i:i + 1024]
        p.z.cmd("write-memory %d %s" % (addr + i, " ".join(str(b) for b in chunk)))


def screen(p):
    return bytes(p.z.read_memory(0x4000, 6912))


def diff_outside_prompt(a, b):
    """Offsets differing between two screens, outside rows 22-23 (bitmap + attrs)."""
    bad = []
    for i in range(6144):
        y = ((i >> 8) & 7) | ((i >> 2) & 0x38) | ((i >> 5) & 0xC0)
        if y < 176 and a[i] != b[i]:
            bad.append(i)
    bad += [6144 + i for i in range(22 * 32) if a[6144 + i] != b[6144 + i]]
    return bad


def main():
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = Proto(h)
        p.load()
        poke(p, 0x4000, SCR)                      # what the tape's SCREEN$ block leaves
        p.wb("INPUT_SRC", 1)                      # boot6_init zeroes it: re-set below
        reached = p.until(lambda: p.rb("GAME_STATE") == GS_ANYKEY, 600)
        h.expect("1 boot reaches the anykey wait", reached, True)
        p.wb("INPUT_SRC", 1)
        p.hold("1")                               # LOAD "" key still down: must not count
        p.tick(12)
        h.expect("2 held key at arrival does not dismiss", p.rb("GAME_STATE"), GS_ANYKEY)
        p.release()
        p.tick(25)                                # a second of waiting, nothing pressed
        h.expect("3 no timeout / no key: still waiting", p.rb("GAME_STATE"), GS_ANYKEY)
        scr = screen(p)
        bad = diff_outside_prompt(scr, SCR)
        h.expect("4 loading picture intact outside rows 22-23 (%d diffs %s)" % (len(bad), bad[:6]), len(bad), 0)
        h.expect("5 attrs of rows 22-23 untouched", scr[6144 + 22 * 32:] == SCR[6144 + 22 * 32:], True)
        px = sum(bin(b).count("1") for y in range(176, 184)
                 for b in scr[((y & 0xC0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2):][:32])
        h.expect("6 PRESS ANY KEY drawn on row 22 (%d px)" % px, px > 40, True)
        h.expect("7 row 23 still blank", all(
            b == 0 for y in range(184, 192)
            for b in scr[((y & 0xC0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2):][:32]), True)
        h.expect("8 title tune requested", p.rb("MUS_REQ"), 7)
        h.expect("9 title tune sounding (MUS_CUR)", p.rb("MUS_CUR"), 7)
        # a '1' (START) as the dismissing key must not start the game
        p.hold("1")
        ok = p.until(lambda: p.rb("GAME_STATE") == GS_SELECT, 60)
        h.expect("10 key -> menu (GS_SELECT)", ok, True)
        p.tick(12)                                # '1' still down through the menu
        h.expect("11 key swallowed: '1' did not START", p.rb("GAME_STATE"), GS_SELECT)
        p.release()
        p.tick(3)
        h.expect("12 menu screen replaced the picture", screen(p)[:6144] != SCR[:6144], True)
        h.expect("13 menu still answers a real press", (p.hold("1"), p.wait_state(GS_PLAYING, 200))[1], True)
    print("anykey:", "OK" if h.ok else "FAIL %s" % h.failures)
    return 0 if h.ok else 1


if __name__ == "__main__":
    sys.exit(main())
