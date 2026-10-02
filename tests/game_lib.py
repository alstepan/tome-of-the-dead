#!/usr/bin/env python3
"""Helpers for the game ZRCP tests (tests/game.py, tests/budget.py).

Addresses and frame ids are parsed from build/wazhack.sym, so the tests follow the
build instead of hard-coding numbers (docs/memory-map.md "PROTO" is the human
reference). Input is injected through the P3 contract: INPUT_SRC=1 freezes the
KBD_MATRIX mirror and we poke active-low half-row bytes.
"""
import hashlib
import os
import re
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
from test_harness import Harness  # noqa: E402,F401

BUILD_SNA = os.path.join(REPO, "build", "wazhack.sna")
SYM = os.path.join(REPO, "build", "wazhack.sym")

# Every ZRCP command must answer within this (a `run` is <= 1 emulated s of
# boot pool generation; everything else is instant). A stuck command raises
# TimeoutError in seconds instead of hanging the suite for hours.
CMD_TIMEOUT = float(os.environ.get("GAME_CMD_TIMEOUT", "30"))
# `run` opcode limit: a tick is <= ~40k opcodes, boot's pool gen ~1M. A run
# that hits the limit without reaching a probe is an anomaly (logged, retried).
RUN_LIMIT = 4000000
MAX_RUN_RETRIES = 3            # consecutive non-probe returns before failing
# ZEsarUX flags for the tick-exact suites. Results never depend on wall-clock
# pacing (every advance is a breakpoint-bounded `run`), so let the emulator run
# unthrottled and windowless: ~2x faster, and no GUI window for App Nap to
# throttle. Override with GAME_EMU_ARGS="" to watch it in the cocoa window.
EMU_ARGS = tuple(os.environ.get("GAME_EMU_ARGS",
                                "--emulatorspeed 1000 --vo null --ao null").split())


def load_syms(path=SYM):
    syms = {}
    for line in open(path):
        m = re.match(r"^([A-Za-z_][\w.]*):\s+EQU\s+0x([0-9A-Fa-f]+)", line)
        if m:
            syms[m.group(1)] = int(m.group(2), 16)
    return syms


S = load_syms()


def _private_snapshot():
    """Copy build/wazhack.sna once to a private temp file and load only that:
    a concurrent assemble rewrites build/wazhack.sna in place (SAVESNA path is
    hard-coded), and a smartload mid-write reads a torn file. Also parse the
    128K image so every load() can verify all 8 banks byte-for-byte."""
    data = open(BUILD_SNA, "rb").read()
    if len(data) != 131103:
        raise RuntimeError(f"{BUILD_SNA}: {len(data)} bytes, want a 128K .sna (131103)")
    fd, path = tempfile.mkstemp(prefix="game_", suffix=".sna")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    ram48, pc, p7ffd = data[27:27 + 49152], data[49179] | data[49180] << 8, data[49181]
    banks = {5: ram48[:16384], 2: ram48[16384:32768], p7ffd & 7: ram48[32768:]}
    off = 49183
    for b in range(8):
        if b not in banks:
            banks[b] = data[off:off + 16384]
            off += 16384
    if pc != S["boot"]:
        raise RuntimeError(f"wazhack.sna entry {pc:#06x} != wazhack.sym boot {S['boot']:#06x}:"
                           " .sna and .sym are from different builds (rebuild with --sym)")
    return path, hashlib.sha256(data).hexdigest(), b"".join(banks[i] for i in range(8)), p7ffd


SNA, SNA_SHA256, SNA_RAM, SNA_7FFD = _private_snapshot()
print(f"[game] snapshot {BUILD_SNA} sha256={SNA_SHA256[:16]} -> private copy {SNA}", flush=True)


def _cleanup_snapshot():
    try:
        os.unlink(SNA)
    except OSError:
        pass


import atexit  # noqa: E402
atexit.register(_cleanup_snapshot)

# entity layout (defs.asm)
STRIDE = 32
E = dict(KIND=0, ROOM=1, FLAGS=2, X=3, Y=4, HP=5, MAXHP=6, AIDIR=7, POT=8,
         PX=9, PY=10, MODE=11, REACT=15, HIT=22, FLT=18, FLA=19, DVIS=24, DFID=25,
         DFPX=26, DFPY=27, DCOL=28, DROW=29, DCOLS=30, DROWS=31)
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT, EF_DYING, EF_WALKIN, EF_PENDING = 1, 2, 4, 8, 16, 32, 64

GS_PLAYING, GS_WIN, GS_DEAD, GS_SELECT, GS_TRANSITION = 2, 3, 4, 5, 6

# keys: (mirror row index, bit)
KEYS = {
    "L": (6, 1), "K": (6, 2), "J": (6, 3), "H": (6, 4), "ENTER": (6, 0),
    "P": (5, 0), "O": (5, 1), "Q": (2, 0), "A": (1, 0), "G": (1, 4),
    "SPACE": (7, 0), "1": (3, 0), "2": (3, 1), "3": (3, 2),
}
HERO_KEY = {0: "1", 1: "2"}                  # id 2 (Rogue) retired: hole in the K_* ids

ATTR_AIR, ATTR_WALL, ATTR_FLOOR, ATTR_LADDER = 0x00, 0x01, 0x0F, 0x02
TILE_ATTRS = {0x00, 0x01, 0x0F, 0x02, 0x42, 0x06, 0x46}
FLASH_ATTRS = {0x42, 0x44, 0x45}          # ATTR_HIT, ATTR_HEAL, zap
KIND_ATTR = {0: 0x47, 1: 0x45, 2: 0x44, 3: 0x47, 4: 0x44, 5: 0x45, 6: 0x06, 7: 0x43, 8: 0x44}
K_KNIGHT, K_WIZARD, _K_RETIRED, K_SKELETON, K_GOBLIN, K_GHOST, K_RAT, K_BAT, K_SLIME = range(9)


class Proto:
    """Tick-exact driver. After load() ZEsarUX stays in cpu-step mode with
    breakpoints on wait_tick (once per 25 Hz game tick, render complete) and
    select_loop (once per frame on the hero-select screen); every advance is an
    explicit `tick()`, so scenarios are deterministic and never race the
    renderer (no wall-clock sleeps)."""

    def __init__(self, h):
        self.h = h
        self.z = h.z

    # --- raw access ---------------------------------------------------------
    def rb(self, name_or_addr):
        a = S[name_or_addr] if isinstance(name_or_addr, str) else name_or_addr
        return self.h.read_byte(a)

    def rw(self, name):
        return self.h.read_word_le(S[name])

    def wb(self, name_or_addr, v):
        a = S[name_or_addr] if isinstance(name_or_addr, str) else name_or_addr
        self.h.write_byte(a, v)

    def ent(self, slot):
        b = self.z.read_memory(S["P_ENTITIES"] + slot * STRIDE, STRIDE)
        return {k: b[o] for k, o in E.items()}

    def set_ent(self, slot, **kw):
        base = S["P_ENTITIES"] + slot * STRIDE
        for k, v in kw.items():
            self.h.write_byte(base + E[k], v)

    def frame(self):
        return self.h.frame_bytes()

    # --- stepping -----------------------------------------------------------
    # Stop PCs a `run` may legitimately return on. Tests that add their own
    # breakpoint (e.g. #29's hscroll_room.step) add its PC here too.
    anomalies = 0

    @property
    def probes(self):
        return {S["wait_tick"], S["select_tick"]} | getattr(self, "extra_probes", set())

    def pc(self):
        return int(self.z.cmd("get-registers")[3:7], 16)

    def load(self, attempts=3):
        """Fresh snapshot, never leaving cpu-step mode: smartload inside step
        mode is synchronous, so nothing runs on wall-clock time (the old
        exit-cpu-step / sleep / enter-cpu-step reload raced the emulator thread
        under host load: a reload could silently not take, or land late in
        the next scenario). The reload is verified — all 128K of RAM equals
        the .sna, PC = boot, $7FFD as saved — or this raises."""
        now = time.monotonic()
        t0 = getattr(Proto, "_t0", None) or now
        Proto._t0 = t0
        Proto._loads = getattr(Proto, "_loads", 0) + 1
        prev = now - getattr(Proto, "_t_last", now)
        Proto._t_last = now
        print(f"[time] load #{Proto._loads} at +{now - t0:.1f}s"
              f" (previous scenario {prev:.1f}s)", flush=True)
        self.z.sock.settimeout(CMD_TIMEOUT)
        self.z.cmd("enter-cpu-step")
        for i in range(attempts):
            self.z.cmd("smartload " + SNA)
            self.z.cmd("set-memory-zone 0")          # 128K machine RAM, banks 0-7
            try:
                ram = self.z.read_memory(0, 131072)
            finally:
                self.z.cmd("set-memory-zone -1")     # back to the mapped view
            regs = self.z.cmd("get-registers")
            mmu = re.search(r"MMU=([0-9a-fA-F]+)", regs)
            # MMU field (128K): 4 x 4-hex segments; seg 3 = bank at $C000
            c000 = int(mmu.group(1)[12:16], 16) if mmu else -1
            if ram == SNA_RAM and int(regs[3:7], 16) == S["boot"] and c000 == (SNA_7FFD & 7):
                break
            bad = sum(a != b for a, b in zip(ram, SNA_RAM))
            print(f"[WARN] reload {i} did not take: {bad} RAM bytes differ, {regs[:7]},"
                  f" $C000 bank {c000}", flush=True)
        else:
            raise RuntimeError("snapshot reload failed %d times" % attempts)
        self.load_breakpoints()

    def load_breakpoints(self):
        """Probe breakpoints only (1 wait_tick, 2 select_tick); 3..32 cleared."""
        self.extra_probes = set()
        self.z.cmd("enable-breakpoints")
        self.z.cmd("set-breakpoint 1 PC=%d" % S["wait_tick"])
        self.z.cmd("set-breakpoint 2 PC=%d" % S["select_tick"])
        for n in range(3, 33):                       # no stale per-test/profiler breakpoints
            self.z.cmd("set-breakpoint %d" % n)

    def tick(self, n=1):
        """Advance to the next probe breakpoint, n times. `run` can also return
        on socket data, a menu event or the opcode limit; a return anywhere but
        a probe PC is logged and re-run, and fails loudly if it persists."""
        for _ in range(n):
            self.z.cmd("cpu-step")            # step off the breakpoint PC first:
            for attempt in range(MAX_RUN_RETRIES + 1):
                r = self.z.cmd("run %d" % RUN_LIMIT)  # `run` re-fires on the current PC
                m = re.search(r"^PC=([0-9a-fA-F]{4})", r, re.M)
                pc = int(m.group(1), 16) if m else self.pc()
                if pc in self.probes:
                    break
                Proto.anomalies += 1
                print(f"[ANOMALY] run returned at PC={pc:#06x} (not a probe): {r[:90]!r}",
                      flush=True)
            else:
                raise RuntimeError("run keeps returning outside the probes")

    def until(self, pred, max_ticks=400):
        for _ in range(max_ticks):
            if pred():
                return True
            self.tick()
        return pred()

    def settle(self, n=3):
        self.tick(n)

    def wait_state(self, gs, max_ticks=600):
        return self.until(lambda: self.rb("GAME_STATE") == gs, max_ticks)

    def idle(self):
        return self.rb("TURN_PHASE") == 0 and self.rb("GAME_STATE") in (GS_PLAYING, GS_DEAD, GS_WIN)

    # --- boot / select ------------------------------------------------------
    def boot(self, hero=K_KNIGHT, repeat=0, freeze=1):
        self.load()
        self.wait_state(GS_SELECT)
        self.wb("INPUT_REPEAT", repeat)
        self.wb("ANIM_FREEZE", freeze)
        self.wb("INPUT_SRC", 1)
        self.hold(HERO_KEY[hero])
        self.wait_state(GS_PLAYING)
        self.release()
        self.settle(3)

    # --- input --------------------------------------------------------------
    def release(self):
        self.z.cmd("write-memory %d %s" % (S["KBD_MATRIX"], " ".join(["255"] * 8)))

    def hold(self, *keys):
        rows = [0xFF] * 8
        for k in keys:
            r, bit = KEYS[k]
            rows[r] &= ~(1 << bit) & 0xFF
        self.z.cmd("write-memory %d %s" % (S["KBD_MATRIX"], " ".join(str(x) for x in rows)))

    def turn(self, *keys, per_tick=None, max_ticks=600):
        """Hold keys until a turn starts, then run it to completion (incl. any
        transition). True if a turn ran. per_tick(frame, hero) is called on
        every tick of the turn (render complete)."""
        t0 = self.rw("TURN_COUNTER")
        self.hold(*keys)
        started = False
        for _ in range(3):                    # INPUT is sampled every tick
            self.tick()
            if self.rb("TURN_PHASE") == 1 or self.rw("TURN_COUNTER") != t0:
                started = True
                break
        self.release()
        if not started:
            self.tick(2)                      # engine sees the release
            return False
        for _ in range(max_ticks):
            if per_tick:
                per_tick(self.frame(), self.ent(0))
            if self.rw("TURN_COUNTER") != t0 and self.idle():
                break
            self.tick()
        self.tick()                           # one INPUT tick: release latched
        return True

    def no_turn(self, *keys):
        t0 = self.rw("TURN_COUNTER")
        self.hold(*keys)
        self.tick(6)
        self.release()
        self.tick(2)
        return self.rw("TURN_COUNTER") == t0 and self.rb("TURN_PHASE") == 0

    def wait(self, n=1):
        for _ in range(n):
            self.turn("SPACE")

    # --- trace --------------------------------------------------------------
    def clear_trace(self):
        self.z.cmd("write-memory %d %s" % (S["ANIM_TRACE"], " ".join(["255"] * 32)))
        self.wb("ANIM_TRACE_IDX", 0)

    def trace(self):
        """ANIM_TRACE entries in write order (since the last clear_trace)."""
        raw = self.z.read_memory(S["ANIM_TRACE"], 32)
        idx = self.rb("ANIM_TRACE_IDX")
        out = []
        for i in range(16):
            o = (idx + 2 * i) % 32
            if raw[o] != 0xFF:
                out.append((raw[o], raw[o + 1]))
        return out

    def trace_fids(self, slot):
        return [f for s, f in self.trace() if s == slot]


def attr_at(frame, col, row):
    return frame[6144 + row * 32 + col]


def cell_bytes(frame, col, row):
    out = []
    for p in range(8):
        high = (0x40 | (row & 0x18)) + p
        low = ((row & 7) << 5) | col
        out.append(frame[((high << 8) | low) - 0x4000])
    return bytes(out)


def floor_band_ok(frame, room_holes, open_cells=()):
    """Every cell of floor rows 6/13/20 outside hole cells is ATTR_FLOOR."""
    bad = []
    for row in (6, 13, 20):
        for col in range(32):
            if (col, row) in room_holes or (col, row) in open_cells:
                continue
            if attr_at(frame, col, row) != ATTR_FLOOR:
                bad.append((col, row, hex(attr_at(frame, col, row))))
    return bad


# hole cells per room: ladder segments {col, s} -> floor row 7s-1 (s>=1)
ROOM_LADDERS = {0: [(5, 2), (23, 1)], 1: [(10, 2), (4, 1), (24, 3)],
                2: [(24, 0), (24, 1), (6, 2)], 3: [(22, 2), (8, 1)]}


def holes(room):
    cells = set()
    for col, s in ROOM_LADDERS[room]:
        row = 7 * s - 1
        if 0 <= row <= 20:
            for c in range(col, col + 3):
                cells.add((c, row))
    return cells
