#!/usr/bin/env python3
"""FINAL-1 rename gate (no emulator, no build): the game is "Tome of the Dead"; the old
project name must not appear (case-insensitive) in any tracked file CONTENT (text or
binary) or tracked file NAME. The one allowed mention is the credit phrase
"WazHack-inspired" (plus its credit link). docs/rename-map.md, docs/rename-user-steps.md and
THIRD-PARTY.md name it on purpose and are exempt by path. Run by tools/build.sh on every build; exit 1 on a hit.

Usage: tests/rename_gate.py [-q]"""
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD = "waz" + "hack"                                   # split: this file must pass its own gate
ALLOWED = ("Waz" + "Hack-inspired",                    # the credit phrase
           "https://www." + OLD + ".com/")              # the credit link (itch page)
EXEMPT = {"docs/rename-map.md", "docs/rename-user-steps.md",
          "THIRD-PARTY.md"}                             # attribution file: names the game on purpose
PAT = re.compile(OLD.encode(), re.I)


def main():
    try:
        out = subprocess.check_output(["git", "-C", REPO, "ls-files", "-z"], stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        print("rename_gate: SKIP (not a git checkout)")
        return 0
    files = [f for f in out.decode().split("\0") if f]
    bad = []
    for f in files:
        if f in EXEMPT:
            continue
        if OLD in f.lower():
            bad.append(f"{f}: file name")
        try:
            data = open(os.path.join(REPO, f), "rb").read()
        except OSError:
            continue                                    # deleted in the work tree
        for a in ALLOWED:
            data = data.replace(a.encode(), b"")
        for m in PAT.finditer(data):
            ln = data.count(b"\n", 0, m.start()) + 1
            bad.append(f"{f}:{ln}: content")
            break
    if bad:
        print(f"rename_gate: FAIL {len(bad)} file(s) mention the old project name:")
        for b in bad[:40]:
            print("  " + b)
        return 1
    if "-q" not in sys.argv:
        print(f"rename_gate: OK ({len(files)} tracked files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
