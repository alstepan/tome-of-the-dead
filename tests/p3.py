#!/usr/bin/env python3
"""P3 scenarios: the input -> turn -> render core loop on the static map.

Drives ZEsarUX over ZRCP and asserts the design §6 playability conditions that
P3 covers. Each scenario reloads the snapshot fresh so the player starts at
(PLAYER_START_X, PLAYER_START_Y) = (1, 5) — against the left border wall, with
floor to the east and north-east.

Input injection (the point of the test, design §3 chord feature):
  The engine's scan_matrix copies the 8 keyboard half-rows into the KBD_MATRIX
  mirror in RAM, then sample_keys reads RAM (not the port). Setting INPUT_SRC!=0
  tells scan_matrix to LEAVE the mirror alone, so we can poke held keys directly
  and genuinely exercise the matrix-sampling + chord-summing path.

  Mirror bytes are active-low (bit CLEAR = key held), exactly as IN A,(C) returns.
  KBD_MATRIX index 6 = the ENTER/L/K/J/H half-row; bit1=L bit2=K bit3=J bit4=H.
    L held   = 0xFF & ~(1<<1) = 0xFD   (east)
    K+L held = 0xFF & ~(1<<1) & ~(1<<2) = 0xF9   (north-east diagonal chord)
    H held   = 0xFF & ~(1<<4) = 0xEF   (west, into the border wall)
  Index 7 = SPACE/.../B half-row; bit0=SPACE: 0xFE = wait.

Usage:
    python3 tests/p3.py                 # verify (exit non-zero on any mismatch)
    python3 tests/p3.py --update-golden # capture/refresh the golden frame hashes
"""
import hashlib
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from test_harness import Harness, REPO  # noqa: E402

SNA = os.path.join(REPO, "build", "wazhack.sna")
GOLDEN_DIR = os.path.join(HERE, "golden")

# --- stable test-observable addresses (docs/memory-map.md) -------------------
GAME_STATE = 0xBF00
TURN_COUNTER = 0xBF03   # word (LE)
INPUT_SRC = 0xBF05
KBD_MATRIX = 0xBF06     # 8-byte mirror; +idx selects a half-row
PLAYER_X = 0xB001
PLAYER_Y = 0xB002

GS_PLAYING = 0x02
START_X, START_Y = 1, 5

# keyboard half-row mirror indices / poked values
ROW_HJKL, ROW_SPACE = 6, 7
KEY_L, KEY_KL, KEY_H = 0xFD, 0xF9, 0xEF
# opposite-key chords on ROW_HJKL (bit1=L bit2=K bit3=J bit4=H), both -> (0,0):
KEY_LH = 0xED   # L+H held: dx = +1 (east) -1 (west) = 0
KEY_KJ = 0xF3   # K+J held: dy = -1 (north) +1 (south) = 0
KEY_SPACE = 0xFE
RELEASED = 0xFF

SETTLE = 0.7    # boot + full map render before the engine parks in get_action
ACT = 0.3       # let one injected action resolve

# viewport: map tile (mx,my) -> screen char cell (mx+1, my+1)
VIEW_OFF = 1


def cell_offsets(cc, rr):
    """Frame-byte offsets (into the 6912-byte bitmap+attr block) of char cell."""
    offs = set()
    base_high = 0x40 | (rr & 0x18)
    low = ((rr & 7) << 5) | cc
    for p in range(8):
        addr = ((base_high + p) << 8) | low      # bitmap scanline
        offs.add(addr - 0x4000)
    offs.add(6144 + rr * 32 + cc)                 # attribute byte
    return offs


def inject(h, idx, val):
    """Freeze the mirror (test mode) and poke one half-row byte."""
    h.write_byte(INPUT_SRC, 1)
    time.sleep(0.1)                                # let any in-flight scan finish
    h.write_byte(KBD_MATRIX + idx, val)
    time.sleep(ACT)


def boot(h):
    h.load(SNA, settle=SETTLE)


def main():
    update = "--update-golden" in sys.argv
    with Harness() as h:
        h.launch()

        # --- boot state (design §4.1: engine reaches the playing turn loop) ---
        boot(h)
        h.expect("boot GAME_STATE", h.read_byte(GAME_STATE), GS_PLAYING)
        h.expect("boot PLAYER_X", h.read_byte(PLAYER_X), START_X)
        h.expect("boot PLAYER_Y", h.read_byte(PLAYER_Y), START_Y)
        h.expect("boot TURN", h.read_word_le(TURN_COUNTER), 0)
        pre_frame = h.frame_bytes()               # initial render (for §6.18)

        # --- §6.4 player moves east + §6.6 one keypress = one turn ------------
        boot(h)
        inject(h, ROW_HJKL, KEY_L)
        h.expect("move-E PLAYER_X", h.read_byte(PLAYER_X), START_X + 1)
        h.expect("move-E PLAYER_Y", h.read_byte(PLAYER_Y), START_Y)
        h.expect("move-E TURN", h.read_word_le(TURN_COUNTER), 1)

        # --- §6.18 dirty-cell: only old + new cells differ -------------------
        post_frame = h.frame_bytes()
        old_cell = cell_offsets(START_X + VIEW_OFF, START_Y + VIEW_OFF)
        new_cell = cell_offsets(START_X + 1 + VIEW_OFF, START_Y + VIEW_OFF)
        allowed = old_cell | new_cell
        changed = {i for i in range(len(pre_frame)) if pre_frame[i] != post_frame[i]}
        h.expect("dirty changed!=empty", bool(changed), True)
        h.expect("dirty subset old+new", changed.issubset(allowed), True)

        # --- diagonal chord K+L -> (+1,-1) in one turn (design §3 feature) ----
        boot(h)
        inject(h, ROW_HJKL, KEY_KL)
        h.expect("chord-NE PLAYER_X", h.read_byte(PLAYER_X), START_X + 1)
        h.expect("chord-NE PLAYER_Y", h.read_byte(PLAYER_Y), START_Y - 1)
        h.expect("chord-NE TURN", h.read_word_le(TURN_COUNTER), 1)

        # --- §6.5 walls block: into the west border wall, no move, no turn ----
        boot(h)
        inject(h, ROW_HJKL, KEY_H)
        h.expect("wall PLAYER_X", h.read_byte(PLAYER_X), START_X)
        h.expect("wall PLAYER_Y", h.read_byte(PLAYER_Y), START_Y)
        h.expect("wall TURN", h.read_word_le(TURN_COUNTER), 0)

        # --- WAIT consumes exactly one turn without moving (design §4.1) ------
        boot(h)
        inject(h, ROW_SPACE, KEY_SPACE)
        h.expect("wait PLAYER_X", h.read_byte(PLAYER_X), START_X)
        h.expect("wait PLAYER_Y", h.read_byte(PLAYER_Y), START_Y)
        h.expect("wait TURN", h.read_word_le(TURN_COUNTER), 1)

        # --- §3 opposite-key cancel: (dx,dy)=(0,0) -> no move, no turn --------
        # L+H sum to dx=0; the real scan_matrix->sample_keys->dirs_to_step path
        # must fold them to (0,0) so get_action loops without ever emitting an
        # action. Reviewer-verified manually; guarded here.
        boot(h)
        inject(h, ROW_HJKL, KEY_LH)
        h.expect("cancel-LH PLAYER_X", h.read_byte(PLAYER_X), START_X)
        h.expect("cancel-LH PLAYER_Y", h.read_byte(PLAYER_Y), START_Y)
        h.expect("cancel-LH TURN", h.read_word_le(TURN_COUNTER), 0)

        # Same for the vertical pair K+J (dy=0).
        boot(h)
        inject(h, ROW_HJKL, KEY_KJ)
        h.expect("cancel-KJ PLAYER_X", h.read_byte(PLAYER_X), START_X)
        h.expect("cancel-KJ PLAYER_Y", h.read_byte(PLAYER_Y), START_Y)
        h.expect("cancel-KJ TURN", h.read_word_le(TURN_COUNTER), 0)

        # --- §6.6 cross-turn debounce: one keypress = one turn, no auto-repeat -
        # Hold a legal move key across the loop: it must advance the turn EXACTLY
        # once (get_action parks in its release-wait while the key stays held).
        # Releasing then re-pressing the same key advances a second turn — proving
        # the release-required debounce, not a per-frame auto-repeat.
        boot(h)
        inject(h, ROW_HJKL, KEY_L)                 # press: 1st move resolves
        h.expect("debounce-press1 TURN", h.read_word_le(TURN_COUNTER), 1)
        h.expect("debounce-press1 PLAYER_X", h.read_byte(PLAYER_X), START_X + 1)
        inject(h, ROW_HJKL, RELEASED)              # held -> released: no new turn
        h.expect("debounce-hold TURN", h.read_word_le(TURN_COUNTER), 1)
        h.expect("debounce-hold PLAYER_X", h.read_byte(PLAYER_X), START_X + 1)
        inject(h, ROW_HJKL, KEY_L)                 # re-press: 2nd move resolves
        h.expect("debounce-press2 TURN", h.read_word_le(TURN_COUNTER), 2)
        h.expect("debounce-press2 PLAYER_X", h.read_byte(PLAYER_X), START_X + 2)

        # --- golden frame of the initial map render --------------------------
        sha = hashlib.sha256(pre_frame).hexdigest()
        golden = os.path.join(GOLDEN_DIR, "p3_start.hash")
        if update:
            os.makedirs(GOLDEN_DIR, exist_ok=True)
            with open(golden, "w") as f:
                f.write(sha + "\n")
            print(f"[golden] wrote {golden}\n         {sha}")
        else:
            try:
                want = open(golden).read().strip()
                h.expect("p3_start frame", sha, want)
            except FileNotFoundError:
                print(f"[FAIL] golden missing: {golden} (run --update-golden)")
                h.failures.append("p3_start frame")

        return 0 if h.ok else 1


if __name__ == "__main__":
    sys.exit(main())
