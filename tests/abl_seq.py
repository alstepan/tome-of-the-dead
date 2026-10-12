#!/usr/bin/env python3
"""D3-7 T2 static check (no emulator): ability animation sequences.

Reads build/wazhack.sna + .sym (build first).
  S1  every abl_seq row (ABL_COUNT x 3 B {DW seq, DB fire tick}) points at a
      well-formed (fid,ticks,flags)*,$FF sequence whose fids are < FID_COUNT
  S2  fire tick == sum of the entry ticks before the release entry (the first
      SF_IMPACT entry, else the last entry)
  S3  Mage casts (ABL 0..4) = CAST1 2 -> CAST2 3, no SF_IMPACT, fire tick 2
Run: python3 tests/abl_seq.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from frames_d3 import load, mem  # noqa: E402


def seq(banks, a):
    out = []
    while True:
        b = mem(banks, a, 1)[0]
        if b == 0xFF:
            return out
        f, t, fl = mem(banks, a, 3)
        out.append((f, t, fl))
        a += 3
        assert len(out) < 16, "unterminated sequence"


def main():
    S, banks = load()
    fails = []
    n = S["ABL_COUNT"]
    row = mem(banks, S["abl_seq"], 3 * n)
    for i in range(n):
        ptr = row[3 * i] | row[3 * i + 1] << 8
        fire = row[3 * i + 2]
        s = seq(banks, ptr)
        if not s:
            fails.append(f"abl {i}: empty seq")
            continue
        for f, t, fl in s:
            if f >= S["FID_COUNT"] or t == 0:
                fails.append(f"abl {i}: bad entry fid={f} ticks={t}")
        rel = next((k for k, e in enumerate(s) if e[2] & 1), len(s) - 1)
        want = sum(e[1] for e in s[:rel])
        if fire != want:
            fails.append(f"abl {i}: fire {fire} != preceding ticks {want}")
        if fire != 2:
            fails.append(f"abl {i}: fire {fire} != 2 (designer ruling)")
        if i <= 4:
            if [(f, t) for f, t, _ in s] != [(S["FID_wizard_cast1"], 2), (S["FID_wizard_cast2"], 3)] \
               or any(e[2] for e in s) or fire != 2:
                fails.append(f"abl {i}: not the Mage cast (CAST1 2 -> CAST2 3, no impact, fire 2)")
    print(f"abl_seq: {'PASS' if not fails else 'FAIL'} ({n} rows, {len(fails)} failures)")
    for f in fails:
        print("  " + f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
