#!/usr/bin/env python3
"""UB8: the REDEFINE KEYS prompt names the direction being asked (row 20,
"PRESS KEY FOR <UP|DOWN|LEFT|RIGHT|FIRE>").  Drives the menu with key 4, taps
five distinct non-reserved keys and checks, per prompt, the mk_buf text AND the
rendered row-20 pixels/attributes (ink != paper, glyph pixels present).
   python3 tests/redefine.py [--png DIR]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game_lib  # noqa: E402
from game_lib import Harness, Proto, S, EMU_ARGS, frame_png  # noqa: E402

PNG = sys.argv[sys.argv.index("--png") + 1] if "--png" in sys.argv else None
NAMES = ["UP", "DOWN", "LEFT", "RIGHT", "FIRE"]
KEYSET = ["W", "S", "A", "D", "F"]   # keys 5 distinct; real set checked below
ROW = 20


def row_state(fr):
    """(pixel bytes set on row 20, attr bytes with ink==paper count, attrs)"""
    px = 0
    for r in range(8):
        y = ROW * 8 + r
        base = ((y & 0xC0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2)
        px += sum(bin(b).count("1") for b in fr[base:base + 32])
    attrs = fr[6144 + ROW * 32: 6144 + ROW * 32 + 32]
    same = sum(1 for a in attrs if (a & 7) == (a >> 3 & 7))
    return px, same, bytes(attrs)


def main():
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = Proto(h)
        p.load()
        p.wait_state(game_lib.GS_SELECT)
        p.wb("INPUT_SRC", 1)
        p.release()
        p.tick(3)
        p.hold("4")
        p.tick(3)
        p.release()
        p.tick(3)
        keys = ["Q", "A", "O", "P", "SPACE"]
        for i, nm in enumerate(NAMES):
            p.tick(3)
            a = S["mk_buf"]
            txt = bytes(h.z.read_memory(a, 40)).split(b"\0")[0].decode()
            want = "PRESS KEY FOR " + nm + " (BREAK=QUIT)"
            fr = p.frame()
            px, same, attrs = row_state(fr)
            if PNG:
                os.makedirs(PNG, exist_ok=True)
                frame_png(fr, os.path.join(PNG, "redefine_%d_%s.png" % (i, nm)))
            h.expect("prompt %d text" % i, txt, want)
            h.expect("prompt %d row-20 pixels drawn (%d)" % (i, px), px > 40, True)
            h.expect("prompt %d ink != paper on text cells (%s)" % (i, attrs[:14].hex()),
                     any((x & 7) != (x >> 3 & 7) for x in attrs[:14]), True)
            if i == 1:                           # "KEY IN USE": UP's key again
                p.hold(keys[0])
                p.tick(3)
                p.release()
                p.tick(3)
                fr = p.frame()
                if PNG:
                    frame_png(fr, os.path.join(PNG, "redefine_in_use.png"))
                txt = bytes(h.z.read_memory(S["mk_buf"], 40)).split(b"\0")[0].decode()
                h.expect("KEY IN USE shown", txt, "KEY IN USE")
                p.tick(40)                       # the beat, then asked again
                txt = bytes(h.z.read_memory(S["mk_buf"], 40)).split(b"\0")[0].decode()
                h.expect("asked again", txt, want)
            p.hold(keys[i])
            p.tick(3)
            p.release()
            p.tick(3)
    print("redefine:", "OK" if h.ok else "FAIL %s" % h.failures)
    return 0 if h.ok else 1


if __name__ == "__main__":
    sys.exit(main())
