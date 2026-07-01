#!/usr/bin/env python3
"""Side-view feasibility SPIKE scenario (docs/design/sideview-renderer.md §5).

Drives the SEPARATE spike build (build/spike.sna) over ZRCP and asserts the
design's LEGALITY checks (NOT identity — attributes legitimately change every
frame as the coloured sprite re-tints its footprint):

  liveness  FRAME_COUNTER advances (the HALT-synced loop never wedges)
  motion    holding East (L) moves SPRITE_PX east via the reused input path
  sub-byte  SPRITE_PX AND 7 is non-zero at some sample (pre-shifted blits run)
  scroll    VIEW_ORIGIN_COL advances and a tracked pillar moves one cell/8px
  5a legal  every attr byte in $5800-$5AFF is in {AIR $05, GROUND $4F, SPRITE $46}
  5b colour the current footprint cells == ATTR_SPRITE ($46)
  5c trail  a vacated cell == ATTR_AIR ($05), and its bitmap == background (0)

Input injection reuses the P3 contract: INPUT_SRC!=0 freezes the KBD_MATRIX
mirror so we poke held keys directly (active-low: bit clear = held).

Usage:
    python3 tests/sideview.py                 # verify (non-zero exit on mismatch)
    python3 tests/sideview.py --update-golden # capture the init-scene golden hash
"""
import hashlib
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from test_harness import Harness, REPO  # noqa: E402

SNA = os.path.join(REPO, "build", "spike.sna")
GOLDEN_DIR = os.path.join(HERE, "golden")

# --- stable test-observable addresses (docs/memory-map.md, spike block) -------
CUR_SC = 0xBF10
SPRITE_PX = 0xBF12        # word (LE) — player world pixel X
VIEW_ORIGIN_COL = 0xBF15
FRAME_COUNTER = 0xBF16    # word (LE)
INPUT_SRC = 0xBF05
KBD_MATRIX = 0xBF06

ROW_HJKL = 6
KEY_L = 0xFD             # L held -> east (bit1 clear)
RELEASED = 0xFF

# attribute legality set + landmark (design §2.2 / §5.2)
ATTR_AIR, ATTR_GROUND, ATTR_SPRITE = 0x05, 0x4F, 0x46
LEGAL_ATTRS = {ATTR_AIR, ATTR_GROUND, ATTR_SPRITE}
TRACK_COL = 28           # world col of the trackable pillar
PILLAR_TOP = 0x7E        # bg_tiles_pillar row 0 signature
SPRITE_PX_INIT = 120

SETTLE = 0.6


def cell_byte(frame, cc, rr, p):
    """Bitmap byte at char cell (cc,rr), pixel row p, from the 6912-B frame."""
    high = (0x40 | (rr & 0x18)) + p
    low = ((rr & 7) << 5) | cc
    return frame[((high << 8) | low) - 0x4000]


def attr_byte(frame, cc, rr):
    return frame[6144 + rr * 32 + cc]


def inject(h, idx, val):
    h.write_byte(INPUT_SRC, 1)
    time.sleep(0.1)
    h.write_byte(KBD_MATRIX + idx, val)


def main():
    update = "--update-golden" in sys.argv
    with Harness() as h:
        h.launch()
        h.load(SNA, settle=SETTLE)

        # --- liveness: the per-frame loop advances FRAME_COUNTER --------------
        f1 = h.read_word_le(FRAME_COUNTER)
        time.sleep(0.2)
        f2 = h.read_word_le(FRAME_COUNTER)
        h.expect("liveness FRAME_COUNTER advances", f2 > f1, True)

        # --- boot state ------------------------------------------------------
        h.expect("boot SPRITE_PX", h.read_word_le(SPRITE_PX), SPRITE_PX_INIT)
        h.expect("boot VIEW_ORIGIN_COL", h.read_byte(VIEW_ORIGIN_COL), 0)

        # --- init-scene golden (sprite at rest -> single-buffer screen static) -
        init_frame = h.frame_bytes()
        h.expect("boot pillar visible @col28",
                 cell_byte(init_frame, TRACK_COL, 12, 0), PILLAR_TOP)
        sha = hashlib.sha256(init_frame).hexdigest()
        golden = os.path.join(GOLDEN_DIR, "sideview_start.hash")
        if update:
            os.makedirs(GOLDEN_DIR, exist_ok=True)
            with open(golden, "w") as f:
                f.write(sha + "\n")
            print(f"[golden] wrote {golden}\n         {sha}")
        else:
            try:
                want = open(golden).read().strip()
                h.expect("sideview_start frame", sha, want)
            except FileNotFoundError:
                print(f"[FAIL] golden missing: {golden} (run --update-golden)")
                h.failures.append("sideview_start frame")

        # --- drive East; sample the sub-byte X path during motion ------------
        inject(h, ROW_HJKL, KEY_L)
        subbyte_seen = False
        for _ in range(8):
            if h.read_word_le(SPRITE_PX) & 7:
                subbyte_seen = True
            time.sleep(0.05)
        time.sleep(0.5)                       # let it cross the dead zone + scroll

        # release and settle to a static frame for at-rest assertions
        h.write_byte(KBD_MATRIX + ROW_HJKL, RELEASED)
        time.sleep(0.25)

        px = h.read_word_le(SPRITE_PX)
        origin = h.read_byte(VIEW_ORIGIN_COL)
        sc = (px >> 3) - origin
        h.expect("moved east (SPRITE_PX>init)", px > SPRITE_PX_INIT, True)
        h.expect("sub-byte X exercised", subbyte_seen, True)
        h.expect("viewport scrolled (origin>0)", origin > 0, True)
        h.expect("origin left of tracker", origin < TRACK_COL, True)

        frame = h.frame_bytes()

        # 5a — every playfield attribute byte is clash-legal (sanctioned value)
        attrs = frame[6144:6912]
        bad = sorted({a for a in attrs if a not in LEGAL_ATTRS})
        if bad:
            print(f"       illegal attr values present: {[hex(b) for b in bad]}")
        h.expect("5a all attrs legal (count)", len(bad), 0)

        # 5b — current footprint (3x3) is coloured ATTR_SPRITE
        foot_ok = all(
            attr_byte(frame, c, r) == ATTR_SPRITE
            for r in (15, 16, 17) for c in (sc, sc + 1, sc + 2)
        )
        h.expect("5b footprint == ATTR_SPRITE", foot_ok, True)

        # 5c — a vacated cell reverted to band colour AND background bitmap
        vac_c, vac_r = sc - 1, 16
        h.expect("5c vacated attr == ATTR_AIR",
                 attr_byte(frame, vac_c, vac_r), ATTR_AIR)
        vac_bitmap = [cell_byte(frame, vac_c, vac_r, p) for p in range(8)]
        h.expect("5c vacated bitmap == background (no trail)",
                 any(vac_bitmap), False)

        # scroll #4 — the tracked pillar moved left by `origin` cells (8px each)
        h.expect("pillar moved with scroll",
                 cell_byte(frame, TRACK_COL - origin, 12, 0), PILLAR_TOP)

        return 0 if h.ok else 1


if __name__ == "__main__":
    sys.exit(main())
