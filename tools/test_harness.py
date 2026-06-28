#!/usr/bin/env python3
"""Reusable ZRCP test harness for WazHack/ZX.

Launches ZEsarUX headless with the ZRCP remote protocol, smartloads a build,
and exposes small assert helpers (state reads + golden-screen hashing). Built on
tools/zrcp.py. Scenarios live under tests/ and use this module; see tests/smoke.py.

Self-contained and repeatable: kills any stray emulator on the port before
launching and terminates its own emulator on exit (context-manager friendly).

ZRCP quirk worth remembering (this harness only READS, but pokers beware):
  - `read-memory  <addr> <len>`        addr may be hex or decimal.
  - `write-memory <addr> <b> [b ...]`  addr AND every byte value must be DECIMAL,
                                       space-separated, e.g. `write-memory 22528 71`.
"""
import hashlib
import os
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zrcp import Zrcp  # noqa: E402

ZESARUX = "/Applications/zesarux.app/Contents/MacOS/zesarux"
DEFAULT_PORT = 10000
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Full screen frame = bitmap (6144) + attributes (768). The golden unit.
SCREEN_ADDR = 0x4000
SCREEN_FRAME_LEN = 6912


class Harness:
    """Owns an emulator process + a ZRCP connection and accumulates failures."""

    def __init__(self, port=DEFAULT_PORT):
        self.port = port
        self.proc = None
        self.z = None
        self.failures = []

    # --- lifecycle ----------------------------------------------------------
    def launch(self):
        # Kill a stray emulator holding our port so runs are repeatable.
        subprocess.run(["pkill", "-f", f"remoteprotocol-port {self.port}"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.5)
        self.proc = subprocess.Popen(
            [ZESARUX, "--machine", "128k",
             "--enable-remoteprotocol", "--remoteprotocol-port", str(self.port),
             "--nosplash", "--noconfigfile"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.z = Zrcp(port=self.port)   # retries the connect until the port is up
        return self

    def load(self, sna_path, settle=0.6):
        """smartload an .sna; it auto-runs from $8000. Settle so boot completes."""
        self.z.smartload(os.path.abspath(sna_path))
        time.sleep(settle)

    def close(self):
        try:
            if self.z:
                self.z.close()
        finally:
            self.z = None
            if self.proc:
                self.proc.send_signal(signal.SIGTERM)
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                self.proc = None

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
        """Full screen frame (bitmap+attrs) as raw bytes — the golden unit."""
        return self.z.read_memory(SCREEN_ADDR, SCREEN_FRAME_LEN)

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
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: got {gs} want {ws}")
        if not ok:
            self.failures.append(name)
        return ok

    @property
    def ok(self):
        return not self.failures
