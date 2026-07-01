#!/usr/bin/env python3
"""SPIKE-2 — byte-shift horizontal scroll legality / no-tear (plan SPIKE-2).

Drives the spike build (build/spike.sna) over ZRCP and proves the byte-shift
scroll path (scroll_view_east/west: shift the visible playfield one byte-column
in place + redraw only the newly-exposed column) is TEAR-FREE, by reconstructing
the *expected* visible window from the world layout and comparing it byte-for-
byte against screen memory after scrolling:

  full-window  every visible cell (32x24, minus the 3x3 sprite footprint) equals
               the tile WORLD_BUF holds at world col (VIEW_ORIGIN_COL + screen_col)
               -> NO tear, NO doubled/dropped column, NO stale rightmost column,
                  NO bitmap trail (vacated cells == background).
  rightmost    the newly-exposed column (screen col 31) matches the world — the
               single check the byte-shift exists to make cheap.
  spacing      two world features keep their exact 8px spacing on screen.
  bands        rows 0-17 == ATTR_AIR (minus footprint), rows 18-23 == ATTR_GROUND
               -> the colour bands survive the attribute shift.
  footprint    the 3x3 sprite cells == ATTR_SPRITE and carry sprite pixels
               (sprite still renders post-scroll).
  repeatable   a second scroll burst re-verifies the whole window at a new origin.

Reuses the P3 INPUT_SRC/KBD_MATRIX injection contract. Deterministic: the test
reads the ACTUAL origin/px and verifies the window against them, so it is robust
to emulator timing.

Usage:  python3 tests/scroll.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from test_harness import Harness, REPO  # noqa: E402

SNA = os.path.join(REPO, "build", "spike.sna")

# --- stable test-observable addresses (docs/memory-map.md, spike block) -------
SPRITE_PX = 0xBF12          # word (LE) — player world pixel X
VIEW_ORIGIN_COL = 0xBF15
FRAME_COUNTER = 0xBF16      # word (LE)
INPUT_SRC = 0xBF05
KBD_MATRIX = 0xBF06

ROW_HJKL = 6
KEY_L = 0xFD               # L held -> east
KEY_H = 0xEF               # H held -> west (bit4 clear)
RELEASED = 0xFF

ATTR_AIR, ATTR_GROUND, ATTR_SPRITE = 0x05, 0x4F, 0x46

# Sprite footprint geometry (spike_sideview.asm).
FOOT_ROWS = (15, 16, 17)
GROUND_ROW = 18

# --- world model: must mirror build_world + bg_tiles.asm exactly ---------------
TILE_BYTES = {
    "blank":   [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
    "floor":   [0xFF, 0x49, 0x00, 0x92, 0x00, 0x49, 0x00, 0x92],
    "ground":  [0x00, 0x24, 0x00, 0x92, 0x00, 0x49, 0x00, 0x92],
    "pillar":  [0x7E, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x7E],
    "doorway": [0xFF, 0x81, 0x81, 0x81, 0x81, 0x81, 0x81, 0x81],
}
PILLAR_COLS = (28, 44, 52)
DOORWAY_COL = 36


def expected_tile(wc, r):
    """Tile id WORLD_BUF holds at (world col wc, char row r)."""
    if r == GROUND_ROW:
        return "floor"
    if r > GROUND_ROW:
        return "ground"
    # r <= 17 (air band)
    if wc in PILLAR_COLS and 12 <= r <= 17:
        return "pillar"
    if wc == DOORWAY_COL and 14 <= r <= 17:
        return "doorway"
    return "blank"


def cell_byte(frame, cc, rr, p):
    """Bitmap byte at char cell (cc,rr), pixel row p, from the 6912-B frame."""
    high = (0x40 | (rr & 0x18)) + p
    low = ((rr & 7) << 5) | cc
    return frame[((high << 8) | low) - 0x4000]


def cell_bytes(frame, cc, rr):
    return [cell_byte(frame, cc, rr, p) for p in range(8)]


def attr_byte(frame, cc, rr):
    return frame[6144 + rr * 32 + cc]


def inject(h, idx, val):
    h.write_byte(INPUT_SRC, 1)
    time.sleep(0.1)
    h.write_byte(KBD_MATRIX + idx, val)


def verify_window(h, frame, origin, sc, tag):
    """Every visible cell (minus the 3x3 footprint) matches the world buffer."""
    foot_cols = {sc, sc + 1, sc + 2}
    bitmap_bad = 0
    air_bad = 0
    ground_bad = 0
    for r in range(24):
        for c in range(32):
            in_foot = (c in foot_cols) and (r in FOOT_ROWS)
            wc = origin + c
            # --- bitmap: faithful render of the world window (no tear/trail) ---
            if not in_foot:
                want = TILE_BYTES[expected_tile(wc, r)]
                if cell_bytes(frame, c, r) != want:
                    bitmap_bad += 1
            # --- attribute bands survive the shift ----------------------------
            a = attr_byte(frame, c, r)
            if r <= 17 and not in_foot and a != ATTR_AIR:
                air_bad += 1
            if r >= GROUND_ROW and a != ATTR_GROUND:
                ground_bad += 1
    h.expect(f"{tag}: window bitmap matches world (mismatched cells)",
             bitmap_bad, 0)
    h.expect(f"{tag}: air band intact (rows 0-17 == ATTR_AIR)", air_bad, 0)
    h.expect(f"{tag}: ground band intact (rows 18-23 == ATTR_GROUND)",
             ground_bad, 0)


def scroll_and_settle(h, key, hold):
    inject(h, ROW_HJKL, key)
    time.sleep(hold)
    h.write_byte(KBD_MATRIX + ROW_HJKL, RELEASED)
    time.sleep(0.3)
    px = h.read_word_le(SPRITE_PX)
    origin = h.read_byte(VIEW_ORIGIN_COL)
    return px, origin, (px >> 3) - origin


def main():
    with Harness() as h:
        h.launch()
        h.load(SNA, settle=0.6)

        f1 = h.read_word_le(FRAME_COUNTER)

        # --- burst 1: scroll several columns east, then verify the window -----
        px, origin, sc = scroll_and_settle(h, KEY_L, 1.0)
        h.expect("scrolled east (origin>0)", origin > 0, True)
        frame = h.frame_bytes()
        verify_window(h, frame, origin, sc, "east")

        # rightmost newly-exposed column matches the world (the byte-shift's job)
        rc = 31
        rc_ok = all(
            cell_bytes(frame, rc, r) == TILE_BYTES[expected_tile(origin + rc, r)]
            for r in range(24))
        h.expect("rightmost col matches world (no stale column)", rc_ok, True)

        # feature spacing preserved on screen: any two visible pillars 8/16 apart
        vis = [pc - origin for pc in PILLAR_COLS if 0 <= pc - origin <= 31]
        if len(vis) >= 2:
            ok = all(cell_byte(frame, vc, 12, 0) == 0x7E for vc in vis)
            h.expect("visible pillars aligned (no doubled/dropped col)", ok, True)

        # sprite still renders post-scroll: footprint carries sprite pixels
        sprite_pixels = any(
            any(cell_bytes(frame, c, r)) for r in FOOT_ROWS
            for c in (sc, sc + 1, sc + 2))
        h.expect("sprite renders post-scroll (footprint non-blank)",
                 sprite_pixels, True)
        foot_attr_ok = all(
            attr_byte(frame, c, r) == ATTR_SPRITE
            for r in FOOT_ROWS for c in (sc, sc + 1, sc + 2))
        h.expect("footprint == ATTR_SPRITE", foot_attr_ok, True)

        # --- burst 2: scroll further east, re-verify at a new origin ----------
        px2, origin2, sc2 = scroll_and_settle(h, KEY_L, 0.7)
        h.expect("scrolled further (origin advanced)", origin2 > origin, True)
        frame2 = h.frame_bytes()
        verify_window(h, frame2, origin2, sc2, "east2")

        # --- liveness --------------------------------------------------------
        f2 = h.read_word_le(FRAME_COUNTER)
        h.expect("loop alive (FRAME_COUNTER advanced)", f2 > f1, True)

        return 0 if h.ok else 1


if __name__ == "__main__":
    sys.exit(main())
