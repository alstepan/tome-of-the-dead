#!/usr/bin/env python3
"""ZX0 round-trip: pack every frame and per-kind block (tools/zx0_pack.py), decompress
with the reference dzx0 and compare bit-exact. Exit 1 on any mismatch."""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import zx0_pack as zp  # noqa: E402

DZX0 = os.path.join(REPO, "tools/bin/dzx0")


def main():
    if not os.path.exists(DZX0) or not os.path.exists(zp.ZX0):
        sys.exit("tools/bin/{zx0,dzx0} missing: run tools/setup_zx0.sh")
    sets = {"game": zp.game_frames(), "concept": zp.concept_frames()}
    bad = checked = 0
    for s, frames in sets.items():
        d = os.path.join(zp.OUT, s)
        os.makedirs(d, exist_ok=True)
        items = list(frames)
        kinds = {}
        for n, data in frames:
            kinds.setdefault(zp.kind(n), bytearray()).extend(data)
        items += [(k + ".kblock", bytes(v)) for k, v in kinds.items()]
        for n, data in items:
            base = os.path.join(d, n)
            zp.zx0(data, base)
            subprocess.run([DZX0, "-f", base + ".zx0", base + ".out"], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            checked += 1
            with open(base + ".out", "rb") as f:
                if f.read() != data:
                    bad += 1
                    print(f"MISMATCH {s}/{n}")
            os.remove(base + ".out")
    print(f"zx0 round-trip: {checked - bad}/{checked} ok")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
