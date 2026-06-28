#!/usr/bin/env python3
"""ZRCP client for ZEsarUX — reusable plumbing for the debug/test skills.

ZRCP (ZEsarUX Remote Command Protocol) is a line-based TCP text protocol. Each
command is one line; the server replies with zero or more lines and then a
prompt (default "command> "). This client sends a command and reads until that
prompt, returning the body lines.

Usage as a library:
    from zrcp import Zrcp
    with Zrcp() as z:
        z.smartload("/abs/path/build/wazhack.sna")
        regs = z.cmd("get-registers")
        frame = z.read_memory(0x4000, 6912)   # -> bytes

Usage from the shell:
    python3 tools/zrcp.py get-registers
    python3 tools/zrcp.py read-memory 16384 16
    python3 tools/zrcp.py --load build/wazhack.sna get-registers
"""
import socket
import sys
import time

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 10000
PROMPT = b"command> "


class Zrcp:
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=10.0,
                 connect_retries=50):
        self.sock = None
        last = None
        for _ in range(connect_retries):
            try:
                self.sock = socket.create_connection((host, port), timeout=timeout)
                break
            except OSError as e:                       # listener not up yet
                last = e
                time.sleep(0.2)
        if self.sock is None:
            raise ConnectionError(f"cannot reach ZRCP at {host}:{port}: {last}")
        self.sock.settimeout(timeout)
        self._buf = b""
        self._read_until_prompt()                      # swallow the banner

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _read_until_prompt(self):
        while PROMPT not in self._buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            self._buf += chunk
        head, _, self._buf = self._buf.partition(PROMPT)
        return head.decode("latin-1")

    def cmd(self, line):
        """Send one command, return the response body (text, prompt stripped)."""
        self.sock.sendall(line.encode("latin-1") + b"\n")
        out = self._read_until_prompt()
        # ZRCP echoes nothing; the first line is the response. Trim trailing CRs.
        return out.replace("\r", "").strip("\n")

    def smartload(self, path):
        return self.cmd(f"smartload {path}")

    def read_memory(self, addr, length):
        """read-memory returns a hex string; decode to bytes."""
        resp = self.cmd(f"read-memory {addr} {length}")
        hexstr = "".join(resp.split())
        return bytes.fromhex(hexstr)

    def get_registers(self):
        return self.cmd("get-registers")

    def close(self):
        if self.sock:
            try:
                self.sock.sendall(b"quit\n")
            except OSError:
                pass
            self.sock.close()
            self.sock = None


def _main(argv):
    load = None
    args = argv[:]
    if args and args[0] == "--load":
        load = args[1]
        args = args[2:]
    if not args:
        print("usage: zrcp.py [--load <file>] <zrcp command...>", file=sys.stderr)
        return 2
    with Zrcp() as z:
        if load:
            print(z.smartload(load))
            time.sleep(0.3)
        print(z.cmd(" ".join(args)))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
