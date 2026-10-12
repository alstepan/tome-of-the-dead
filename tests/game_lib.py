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
SCREEN_FRAME_LEN = 6912         # bitmap + attrs
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
    if S.get("KIT_DEBUG", 0) and not os.environ.get("GAME_ALLOW_DEBUG_KIT"):
        # D3-7: the suites and goldens assume the release start kit
        raise RuntimeError("build/wazhack.sna was built with DEBUG_KIT=1 (the default):"
                           " rebuild with tools/build.sh -DDEBUG_KIT=0 for the suites"
                           " (GAME_ALLOW_DEBUG_KIT=1 overrides)")
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
    "FIRE": (7, 0), "I": (5, 2), "CAPS": (0, 0),
    "4": (3, 3), "5": (3, 4), "0": (4, 0), "9": (4, 1), "8": (4, 2), "7": (4, 3), "6": (4, 4),
}
HERO_KEY = {0: "1", 1: "2"}                  # id 2 (Rogue) retired: hole in the K_* ids

ATTR_AIR, ATTR_WALL, ATTR_FLOOR, ATTR_LADDER = 0x00, 0x01, 0x0F, 0x02
TILE_ATTRS = {0x00, 0x01, 0x0F, 0x02, 0x42, 0x06, 0x46}
FLASH_ATTRS = {0x42, 0x44}                # ATTR_HIT, ATTR_HEAL (D3-0: the zap's $45 is gone)
KIND_ATTR = {0: 0x47, 1: 0x45, 2: 0x44, 3: 0x47, 4: 0x44, 5: 0x45, 6: 0x06, 7: 0x43, 8: 0x44}
K_KNIGHT, K_WIZARD, _K_RETIRED, K_SKELETON, K_GOBLIN, K_GHOST, K_RAT, K_BAT, K_SLIME = range(9)


class Proto:
    """Tick-exact driver. After load() ZEsarUX stays in cpu-step mode with
    breakpoints on wait_tick (once per 25 Hz game tick, render complete) and
    select_tick (menu_frame, bank 2: once per frame in the C3-6 menu, redefine
    and pause loops); every advance is an
    explicit `tick()`, so scenarios are deterministic and never race the
    renderer (no wall-clock sleeps)."""

    # B3B-12: new games start on a generated D1 by default; the suites written
    # for the PROTO rooms A-D (walkthrough, budget, flicker, W0-W15) poke the
    # cold-block flag proto_start = 1 right after every load (see load()).
    # Set proto_start = 0 on an instance for the generated start (W16).
    proto_start = 1
    # C3-8a: every suite plays the turn-intent controls (default KEYTAB).
    # The scenario vocabulary of the PROTO suites is kept as aliases that
    # hold() maps onto the real keys: L/H = right/left (P / O), K/J = up/down
    # (Q / A), WAIT = '.' (SYMBOL SHIFT + M). SPACE and FIRE are the FIRE key.
    # turn() / no_turn() add the new rules around them (see there): a tap
    # that turns the hero around first (0 turns), "C" = close door = FIRE with
    # the melee icon selected, "G" = quaff = select the potion slot, FIRE.
    NEW_KEYS = {"L": "P", "H": "O", "K": "Q", "J": "A", "WAIT": "."}
    POTION_SLOT = {0: 6, 1: 7}               # icon slot (0-based) per hero kind, game.md §3.5
    SLOT_KEY = "1234567890"                  # number key of slot i

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

    # A7 double buffer: bank 7 (displayed) trails the composed bank 5 by one
    # tick (present runs at the next tick start). At settled points (every
    # golden) they must be equal: tests/game.py records differences here.
    present_checks = 0
    present_mismatch = []

    def composed_frame(self):
        """The bank-5 screen ($4000): what render composes (shown only while
        $7FFD bit 3 = 0: boot, select, transitions)."""
        return self.h.frame_bytes()

    def frame(self):
        """The DISPLAYED screen (A7): bank 7's screen 2 when PORT_7FFD_SHADOW
        bit 3 = 1 (play), else bank 5. Read from the 128K RAM zone, whatever
        bank is paged at $C000. Same byte layout as frame_bytes()."""
        shadow = self.rb("PORT_7FFD_SHADOW")
        if not shadow & 0x08:
            return self.h.frame_bytes()
        self.z.cmd("set-memory-zone 0")              # 128K machine RAM, banks 0-7
        try:
            fr = self.z.read_memory(7 * 16384 + (S["SCREEN7_BITMAP"] - 0xC000),
                                    SCREEN_FRAME_LEN)
        finally:
            self.z.cmd("set-memory-zone -1")
        return fr

    def banks_differ(self):
        """Screen bytes where bank 7 (displayed) != bank 5 (composed)."""
        self.z.cmd("set-memory-zone 0")
        try:
            b5 = self.z.read_memory(5 * 16384, SCREEN_FRAME_LEN)
            b7 = self.z.read_memory(7 * 16384, SCREEN_FRAME_LEN)
        finally:
            self.z.cmd("set-memory-zone -1")
        return sum(1 for a, b in zip(b5, b7) if a != b)

    def present_watch(self, on):
        """A7: check banks_differ at every probe_presented (breakpoint 4)
        while on; samples collected in self.present_samples."""
        if on:
            self.present_samples = []
            self.present_probe = S["probe_presented"]
            self.z.cmd("set-breakpoint 4 PC=%d" % self.present_probe)
        else:
            self.present_probe = None
            self.z.cmd("set-breakpoint 4")

    def check_synced(self, tag):
        """A7: displayed == composed (settled screen). Recorded, asserted at the end."""
        fr, comp = self.frame(), self.composed_frame()
        Proto.present_checks += 1
        if fr != comp:
            bad = [i for i in range(SCREEN_FRAME_LEN) if fr[i] != comp[i]]
            Proto.present_mismatch.append((tag, len(bad), bad[0]))

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
        self.wb("proto_start", self.proto_start)     # B3B-12 (after the RAM check)
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
                if pc == getattr(self, "present_probe", None):
                    self.present_samples.append(self.banks_differ())
                    self.z.cmd("cpu-step")    # not a tick boundary: run on
                    continue
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
        """Fresh load, then START through the C3-6 main menu."""
        self.load()
        self.wait_state(GS_SELECT)
        self.wb("INPUT_REPEAT", repeat)
        self.wb("ANIM_FREEZE", freeze)
        self.wb("INPUT_SRC", 1)
        self.menu_start(hero)

    def menu_start(self, hero=K_KNIGHT, settle=3):
        """From the menu (GS_SELECT, INPUT_SRC = 1): '2' toggles HERO until it
        is `hero` (menu_hero persists between games), '1' starts. settle=None:
        return right after GS_PLAYING (first-ticks tests)."""
        self.release()
        self.tick(2)
        for _ in range(2):
            if self.rb("menu_hero") == hero:
                break
            self.tap("2")
        self.hold("1")
        self.wait_state(GS_PLAYING)
        self.release()
        if settle:
            self.settle(settle)

    def end_to_menu(self, key="ENTER"):
        """End screen (GS_DEAD / GS_WIN) -> the menu (C3-6b: a digit / ENTER,
        accepted only after every key was released once; FIRE does not)."""
        self.release()
        self.tick(3)
        self.hold(key)
        ok = self.wait_state(GS_SELECT)
        self.release()
        return ok

    def tap(self, *keys, n=1, step=None):
        """Press for n ticks, release for 1 (edge-driven consumers: menu,
        number keys, FIRE). step() advances one tick (default tick(); the
        budget / flicker recorders pass their own so the tap is measured)."""
        step = step or self.tick
        self.hold(*keys)
        for _ in range(n):
            step()
        self.release()
        step()

    # --- input --------------------------------------------------------------
    def release(self):
        self.z.cmd("write-memory %d %s" % (S["KBD_MATRIX"], " ".join(["255"] * 8)))

    def hold(self, *keys):
        rows = [0xFF] * 8
        for k in keys:
            k = self.NEW_KEYS.get(k, k)
            if k == ".":                      # SYMBOL SHIFT + M
                rows[7] &= ~0x06 & 0xFF
                continue
            r, bit = KEYS["FIRE" if k == "SPACE" else k]
            rows[r] &= ~(1 << bit) & 0xFF
        self.z.cmd("write-memory %d %s" % (S["KBD_MATRIX"], " ".join(str(x) for x in rows)))

    def select_slot(self, slot, step=None):
        """Icon cursor onto `slot` (number key; selects only, no turn)."""
        step = step or self.tick
        if self.rb("SEL_SLOT") != slot:
            self.tap(self.SLOT_KEY[slot], step=step)
            step()
            step()

    def _prep(self, keys, step=None):
        """Translate the PROTO scenario keys to the C3 controls (0-turn
        taps happen here): returns (keys to hold, fire?).
        - "C" (close door) = FIRE with the melee icon (slot 0) selected;
        - "G" (quaff) = the potion slot selected, then FIRE;
        - L / H against the facing: a tap first turns the hero around
          (0 turns, game.md §3.1), then the key walks as before."""
        keys = list(keys)
        fire = False
        if "C" in keys:
            keys.remove("C")
            self.select_slot(0, step)
            fire = True
        if "G" in keys:
            keys.remove("G")
            self.select_slot(self.POTION_SLOT[self.rb("HERO_KIND")], step)
            fire = True
        if "FIRE" in keys or "SPACE" in keys:
            fire = True
        e = self.ent(0)
        side = [k for k in keys if self.NEW_KEYS.get(k, k) in ("P", "O")]
        if len(side) == 1 and "K" not in keys and "Q" not in keys and e["FLAGS"] & EF_ACTIVE:
            right = self.NEW_KEYS.get(side[0], side[0]) == "P"
            if right == bool(e["FLAGS"] & EF_LEFT):
                self.tap(side[0], step=step)      # turn-around: 0 turns
                (step or self.tick)()             # key release latched
        if fire:
            keys.append("FIRE")
        return keys, fire

    def turn(self, *keys, per_tick=None, max_ticks=600):
        """Hold keys until a turn starts, then run it to completion (incl. any
        transition). True if a turn ran. per_tick(frame, hero) is called on
        every tick of the turn (render complete). FIRE acts on release (a
        1-tick tap); DOWN alone is deferred 3 ticks, so the start window is 5."""
        keys, fire = self._prep(keys)
        t0 = self.rw("TURN_COUNTER")
        self.hold(*keys)
        started = False
        if fire:
            self.tick()
            self.release()
        for _ in range(5):                    # INPUT is sampled every tick
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
        keys, fire = self._prep(keys)
        t0 = self.rw("TURN_COUNTER")
        self.hold(*keys)
        self.tick(2 if fire else 6)
        self.release()
        self.tick(3)
        return self.rw("TURN_COUNTER") == t0 and self.rb("TURN_PHASE") == 0

    def wait(self, n=1):
        for _ in range(n):
            self.turn("WAIT")

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


# --- B3B-3 geometry (game.md §2.1), read from the .sym: never hard-coded ---
STOREY_ROWS = S["STOREY_ROWS"]          # 9: 8 air rows + 1 floor row
STOREY_AIR = S["STOREY_AIR"]            # 8
STOREY_COUNT = S["STOREY_COUNT"]        # 2 (s = 0 is the TOP storey)
PLAY_ROWS = S["PLAY_ROWS"]              # 18: playfield rows 0..17
PANEL_ROW = S["PANEL_ROW"]              # 18: panel rows 18..23 (never stamped / scrolled)
FLOOR_ROWS = tuple(STOREY_ROWS * s + STOREY_AIR for s in range(STOREY_COUNT))   # (8, 17)
MAP_LEN = 32 * PLAY_ROWS


def stand_y(s, h):
    """Standing top row of a body of height h on storey s: 9s+8-h."""
    return STOREY_ROWS * s + STOREY_AIR - h


def is_standing(y, h):
    return (y + h) % STOREY_ROWS == STOREY_AIR


def storey_of(y, h):
    """storey_ref: min(STOREY_COUNT-1, (y+h) div 9)."""
    return min(STOREY_COUNT - 1, (y + h) // STOREY_ROWS)


def item_row(s):
    """Potion / floor-item cell row of storey s (the standing row 9s+7)."""
    return STOREY_ROWS * s + STOREY_AIR - 1


def ladder_rows(s):
    """Rows of segment {col, s}: 9s-1 .. 9s+7 clipped to the playfield."""
    return [r for r in range(STOREY_ROWS * s - 1, STOREY_ROWS * s + STOREY_AIR) if 0 <= r < PLAY_ROWS]


def split_frame(frame):
    """(playfield, panel) bytes of a 6912-B screen: char rows 0..PLAY_ROWS-1 and
    PANEL_ROW..23, bitmap lines + attrs each (B3B-3 golden split, plan R4)."""
    def rows(rr):
        out = bytearray()
        for r in rr:
            for line in range(8):
                a = (((r & 0x18) | line) << 8) | ((r & 7) << 5)
                out += frame[a:a + 32]
        for r in rr:
            out += frame[6144 + r * 32:6144 + r * 32 + 32]
        return bytes(out)
    return rows(range(PLAY_ROWS)), rows(range(PANEL_ROW, 24))


def floor_band_ok(frame, room_holes, open_cells=()):
    """Every cell of the floor rows (8 / 17) outside hole cells is ATTR_FLOOR."""
    bad = []
    for row in FLOOR_ROWS:
        for col in range(32):
            if (col, row) in room_holes or (col, row) in open_cells:
                continue
            if attr_at(frame, col, row) != ATTR_FLOOR:
                bad.append((col, row, hex(attr_at(frame, col, row))))
    return bad


# B3B-8: PROTO room ids = 3x3 grid cells (data.asm): A 0, B 1, D 3, C 4.
ROOM_A, ROOM_B, ROOM_C, ROOM_D = 0, 1, 4, 3
ROOM_LETTER = {ROOM_A: "A", ROOM_B: "B", ROOM_C: "C", ROOM_D: "D"}
# ladder segments per room in descriptor order (RD_UPCOL, RD_DNCOL, RD_ARRCOL,
# RD_EXITCOL, RD_LAD1, RD_LAD2; mirror of bank3.asm proto_rooms; tests/world.py
# W0 checks this table against ROOM_DESC in memory). {col,0} up-exit,
# {col,1} internal, {col,2} down-exit hole.
ROOM_LADDERS = {ROOM_A: [(5, 1), (23, 1)], ROOM_B: [(24, 2), (4, 1), (11, 1)],
                ROOM_C: [(24, 0), (24, 1), (6, 1)], ROOM_D: [(22, 1), (8, 1)]}


# B3B-5 storey-0 pits per room (mirror of proto_rooms RD_PITCOL): left hole col p
ROOM_PITS = {ROOM_B: 20}


def holes(room):
    """Floor-row hole cells: segment {col, s} -> row 9s-1 (s >= 1), plus the
    storey-0 pit holes p..p+2 (B3B-5)."""
    cells = set()
    if room in ROOM_PITS:
        cells |= {(c, FLOOR_ROWS[0]) for c in range(ROOM_PITS[room], ROOM_PITS[room] + 3)}
    for col, s in ROOM_LADDERS[room]:
        row = STOREY_ROWS * s - 1
        if 0 <= row < PLAY_ROWS:
            for c in range(col, col + 3):
                cells.add((c, row))
    return cells


def frame_png(frame, path, scale=2):
    """Write a 6912-B Spectrum screen as a PNG (needs Pillow; FLASH ignored).
    Used by `tests/game.py --update-golden --png DIR` to dump every golden for
    a human look before a rebase (plan R4)."""
    from PIL import Image
    pal = []
    for bright in (0xD7, 0xFF):
        for c in range(8):
            pal.append(((c >> 1 & 1) * bright, (c >> 2 & 1) * bright, (c & 1) * bright))
    img = Image.new("RGB", (256, 192))
    px = img.load()
    for y in range(192):
        base = ((y & 0xC0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2)
        for cx in range(32):
            b = frame[base + cx]
            a = frame[6144 + (y >> 3) * 32 + cx]
            br = 8 if a & 0x40 else 0
            ink, paper = pal[br + (a & 7)], pal[br + (a >> 3 & 7)]
            for bit in range(8):
                px[cx * 8 + bit, y] = ink if b & (0x80 >> bit) else paper
    if scale != 1:
        img = img.resize((256 * scale, 192 * scale), Image.NEAREST)
    img.save(path)
