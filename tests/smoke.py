#!/usr/bin/env python3
"""Boot smoke scenario: boot the engine and assert the deterministic frame.

Asserts the boot state (GAME_STATE, RNG_STATE at their stable addresses) and that
the rendered screen frame matches the committed golden hash.

UPDATED for P3: the engine no longer halts on a "WAZHACK" banner — it boots
straight into the playing turn loop (design §4.1). So at boot GAME_STATE is now
GS_PLAYING ($02, was GS_BOOT $01) and the deterministic frame is the initial map
render (border + two rooms + corridor) with the player '@' at (1,5). RNG_STATE is
unchanged (fixed seed $A55A). The golden was regenerated for this new boot frame.

Usage:
    python3 tests/smoke.py                 # verify (exit non-zero on any mismatch)
    python3 tests/smoke.py --update-golden # capture/refresh the golden hash
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from test_harness import Harness, REPO  # noqa: E402

SNA = os.path.join(REPO, "build", "wazhack.sna")
GOLDEN = os.path.join(HERE, "golden", "smoke.hash")

# Stable test-observable addresses (docs/memory-map.md).
GAME_STATE = 0xBF00   # byte
RNG_STATE = 0xBF01    # word (LE)
GS_PLAYING = 0x02
RNG_SEED = 0xA55A


def main():
    update = "--update-golden" in sys.argv
    with Harness() as h:
        h.launch()
        h.load(SNA, settle=0.7)

        h.expect("GAME_STATE", h.read_byte(GAME_STATE), GS_PLAYING)
        h.expect("RNG_STATE", h.read_word_le(RNG_STATE), RNG_SEED)

        sha = h.frame_sha256()
        if update:
            os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
            with open(GOLDEN, "w") as f:
                f.write(sha + "\n")
            print(f"[golden] wrote {GOLDEN}\n         {sha}")
        else:
            try:
                want = open(GOLDEN).read().strip()
            except FileNotFoundError:
                print(f"[FAIL] golden missing: {GOLDEN} "
                      f"(run with --update-golden to capture)")
                return 1
            h.expect("frame_sha256", sha, want)

        return 0 if h.ok else 1


if __name__ == "__main__":
    sys.exit(main())
