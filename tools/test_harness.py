#!/usr/bin/env python3
"""Reusable ZRCP test harness for Tome of the Dead.

Launches ZEsarUX headless with the ZRCP remote protocol, smartloads a build,
and exposes small assert helpers (state reads + golden-screen hashing). Built on
tools/zrcp.py. Scenarios live under tests/ and use this module; see tests/game_lib.py.

Self-contained and repeatable: kills any stray emulator on the port before
launching and terminates its own emulator on exit (context-manager friendly).

ZRCP quirk worth remembering (this harness only READS, but pokers beware):
  - `read-memory  <addr> <len>`        addr may be hex or decimal.
  - `write-memory <addr> <b> [b ...]`  addr AND every byte value must be DECIMAL,
                                       space-separated, e.g. `write-memory 22528 71`.
"""
import atexit
import hashlib
import os
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zrcp import Zrcp  # noqa: E402

ZESARUX = "/Applications/zesarux.app/Contents/MacOS/zesarux"
# ZRCP_PORT: run suites from parallel worktrees without killing each other's
# emulator (launch() pkills whatever holds its port).
DEFAULT_PORT = int(os.environ.get("ZRCP_PORT", "10000"))
LAUNCH_ATTEMPTS = 3
# B9: seconds to wait for the ZRCP port after spawning (per attempt; Zrcp polls at 0.2 s).
LAUNCH_TIMEOUT = float(os.environ.get("WZ_LAUNCH_TIMEOUT", "10"))
# B9: optional wall-clock cap for the whole suite process (0/unset = none). On expiry
# the child emulators are killed and the suite exits 124 with a message, never hangs.
SUITE_TIMEOUT = float(os.environ.get("WZ_SUITE_TIMEOUT", "0"))
REPO =os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Full screen frame = bitmap (6144) + attributes (768). The golden unit.
SCREEN_ADDR = 0x4000
SCREEN_FRAME_LEN = 6912

# --- B9: guaranteed teardown ------------------------------------------------
# Every emulator we spawn is its own session/process group so one killpg takes it
# (and anything it forks) down. atexit + signal handlers make sure a killed or
# timed-out suite leaves no orphan ZEsarUX behind.
_children = set()
# Retry counters (B9), shown in the exit summary. WZ_STRICT=1 turns any retry into a
# suite failure so a flaky infra path cannot silently pass.
STRICT = os.environ.get("WZ_STRICT") == "1"
RETRIES = {"launch": 0, "tape": 0}
_hooks_installed = False


def _kill_proc(proc):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            proc.wait(timeout=3 if sig == signal.SIGTERM else 5)
            return
        except subprocess.TimeoutExpired:
            pass


def _kill_all():
    for proc in list(_children):
        _kill_proc(proc)
        _children.discard(proc)


def _retry_summary():
    if any(RETRIES.values()):
        print(f"[harness] infra retries: launch {RETRIES['launch']}, tape-load {RETRIES['tape']}"
              + (" (WZ_STRICT=1: counted as failures)" if STRICT else ""), flush=True)


def _on_term(signum, _frame):
    _kill_all()
    if signum == signal.SIGINT:
        # Ctrl-C keeps Python's normal semantics: callers' `except KeyboardInterrupt`
        # / finally blocks still run (children are already dead by now).
        raise KeyboardInterrupt
    sys.exit(128 + signum)


def _on_alarm(_signum, _frame):
    # WZ_SUITE_TIMEOUT uses the process-wide SIGALRM/ITIMER_REAL: suites must NOT use
    # signal.alarm/setitimer themselves. os._exit skips finally blocks, atexit and
    # buffered output, so flush both streams first and kill children explicitly.
    print(f"[harness] FAIL: suite wall-clock limit WZ_SUITE_TIMEOUT={SUITE_TIMEOUT:g}s exceeded; "
          "killing emulator and aborting", file=sys.stderr, flush=True)
    _kill_all()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(124)


def _install_hooks():
    global _hooks_installed
    if _hooks_installed:
        return
    _hooks_installed = True
    atexit.register(_kill_all)
    atexit.register(_retry_summary)
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        if signal.getsignal(sig) in (signal.SIG_DFL, signal.default_int_handler):
            signal.signal(sig, _on_term)
    if SUITE_TIMEOUT > 0:
        signal.signal(signal.SIGALRM, _on_alarm)
        signal.setitimer(signal.ITIMER_REAL, SUITE_TIMEOUT)


class Harness:
    """Owns an emulator process + a ZRCP connection and accumulates failures."""

    def __init__(self, port=DEFAULT_PORT):
        self.port = port
        self.proc = None
        self.z = None
        self.failures = []

    # --- lifecycle ----------------------------------------------------------
    def launch(self, extra_args=()):
        """extra_args: appended ZEsarUX flags. Only for suites whose results
        do not depend on wall-clock pacing (e.g. the tick-exact PROTO driver
        uses --emulatorspeed / --vo null); settle-based suites keep defaults."""
        # B9: a launch that never opens the ZRCP port (Zrcp gives up after ~10 s)
        # is killed and retried instead of hanging/failing the whole suite.
        _install_hooks()
        for attempt in range(1, LAUNCH_ATTEMPTS + 1):
            t0 = time.monotonic()
            # Kill a stray emulator holding our port so runs are repeatable.
            # anchored: port 10606 must not match 106060 / a prefix of another port
            subprocess.run(["pkill", "-f", rf"remoteprotocol-port {self.port}( |$)"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.5)
            self.proc = subprocess.Popen(
                [ZESARUX, "--machine", "128k",
                 "--enable-remoteprotocol", "--remoteprotocol-port", str(self.port),
                 "--nosplash", "--noconfigfile", *extra_args],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)
            _children.add(self.proc)
            try:
                # retries the connect until the port is up, bounded by LAUNCH_TIMEOUT
                self.z = Zrcp(port=self.port, connect_retries=max(1, int(LAUNCH_TIMEOUT / 0.2)))
            except (ConnectionError, OSError) as e:
                print(f"[harness] launch attempt {attempt} failed after "
                      f"{time.monotonic() - t0:.1f}s: {e}", file=sys.stderr, flush=True)
                self.close()
                self.note_retry("launch", f"attempt {attempt}")
                if attempt == LAUNCH_ATTEMPTS:
                    raise
                continue
            print(f"[harness] launch {time.monotonic() - t0:.1f}s (attempt {attempt})", flush=True)
            return self

    def note_retry(self, kind, detail=""):
        """Count an infra retry (kind: 'launch' | 'tape'); a failure under WZ_STRICT=1."""
        RETRIES[kind] += 1
        if STRICT:
            self.failures.append(f"infra retry: {kind} {detail}".strip())

    def load(self, sna_path, settle=0.6):
        """smartload an .sna; it auto-runs from $8000. Settle so boot completes."""
        self.z.smartload(os.path.abspath(sna_path))
        time.sleep(settle)

    def close(self):
        t0 = time.monotonic()
        try:
            if self.z:
                self.z.close()
        finally:
            self.z = None
            if self.proc:
                _kill_proc(self.proc)           # TERM then KILL on the whole group
                _children.discard(self.proc)
                self.proc = None
            print(f"[harness] close {time.monotonic() - t0:.1f}s", flush=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- reads --------------------------------------------------------------
    def read_byte(self, addr):
        return self.z.read_memory(addr, 1)[0]

    def read_word_le(self, addr):
        b = self.z.read_memory(addr, 2)
        return b[0] | (b[1] << 8)

    def frame_bytes(self):
        """Full screen frame (bitmap+attrs) as raw bytes — the golden unit.

        Reads bank 5 ($4000) unconditionally: the boot/golden buffer. For the
        128K shadow double-buffer (SPIKE-4) use displayed_frame_bytes() to follow
        whichever bank ULA is showing.
        """
        return self.z.read_memory(SCREEN_ADDR, SCREEN_FRAME_LEN)

    def displayed_frame_bytes(self, shadow_addr=0xBF18):
        """The frame ULA is CURRENTLY displaying, per PORT_7FFD_SHADOW bit3.

        bit3=0 -> bank 5 @ $4000 (also the single-buffer / non-paged case);
        bit3=1 -> bank 7 @ $C000 (the shadow screen). Returned bytes are indexed
        identically to frame_bytes() (offset 0 = first bitmap byte), so the
        cell/attr helpers work unchanged regardless of which bank is shown.
        """
        shadow = self.read_byte(shadow_addr)
        base = 0xC000 if (shadow & 0x08) else SCREEN_ADDR
        return self.z.read_memory(base, SCREEN_FRAME_LEN)

    def frame_sha256(self):
        return hashlib.sha256(self.frame_bytes()).hexdigest()

    # --- writes (ZRCP write-memory: addr AND values must be DECIMAL) ---------
    def write_byte(self, addr, value):
        self.z.cmd(f"write-memory {int(addr)} {int(value) & 0xFF}")

    # --- assertions ---------------------------------------------------------
    def expect(self, name, got, want):
        ok = got == want
        gs = got if isinstance(got, str) else hex(got)
        ws = want if isinstance(want, str) else hex(want)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: got {gs} want {ws}", flush=True)
        if not ok:
            self.failures.append(name)
        return ok

    @property
    def ok(self):
        return not self.failures
