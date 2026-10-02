#!/usr/bin/env python3
"""Pack every sprite frame's source bytes with ZX0 and report ratios (A4, tools only).

Frame source bytes = exactly what the build stores: H rows x [mask,data] x W/8,
MSB=left, mask 1 = transparent. The trailing ATTR_SPRITE byte of the .asm
(<name>_attr) is NOT included: the frame descriptor carries it, and the
budget's "source = W/8 x H x 2" excludes it.

Sets:
  game    assets/gfx/sprites/*.asm  (DEFB rows parsed back to bytes, in file order)
  concept assets/gfx/concept/grid/sprites/*.grid (packed via gfx_convert native layout)

Outputs (build/zx0/<set>/): <frame>.bin (raw), <frame>.zx0, <kind>.kblock.{bin,zx0}
and report.txt. zx0 flags: default = optimal, forward, v2 format, no header
(-q would be faster but non-optimal; -b backwards is only needed for in-place
decompression with overlapping buffers, which the engine does not do: it
decompresses from a source bank into the pool).

Usage: tools/zx0_pack.py [--set game|concept|all]   (run tools/setup_zx0.sh first)
"""
import argparse
import glob
import os
import re
import statistics
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
ZX0 = os.path.join(REPO, "tools/bin/zx0")
OUT = os.path.join(REPO, "build/zx0")


def game_frames():
    """[(name, bytes)] in index.asm include order."""
    d = os.path.join(REPO, "assets/gfx/sprites")
    names = re.findall(r'INCLUDE\s+"(\w+)\.asm"', open(os.path.join(d, "index.asm")).read())
    out = []
    for n in names:
        buf, on = bytearray(), False
        for line in open(os.path.join(d, n + ".asm")):
            code = line.split(";")[0].strip()
            if code == n + ":":
                on = True
            elif code.startswith(n + "_attr"):
                break
            elif on and code.upper().startswith("DEFB"):
                buf += bytes(int(t.strip().lstrip("$"), 16) for t in code[4:].split(","))
        out.append((n, bytes(buf)))
    return out


def concept_frames():
    import gfx_convert as gc
    out = []
    for p in sorted(glob.glob(os.path.join(REPO, "assets/gfx/concept/grid/sprites/*.grid"))):
        text = open(p).read()
        fg, solid, w, h = gc.parse_grid_text_mask(text, None, None)
        m = re.search(r"#\s*size:\s*(\d+)x(\d+)", text)
        if m:
            assert (w, h) == (int(m[1]), int(m[2])), p
        rows = gc.pack_sprite(fg, solid, layout="native")
        out.append((os.path.basename(p)[:-5], bytes(b for r in rows for b in r)))
    return out


def zx0(data: bytes, base: str) -> bytes:
    """Compress data; writes base.bin and base.zx0, returns the packed bytes."""
    with open(base + ".bin", "wb") as f:
        f.write(data)
    subprocess.run([ZX0, "-f", base + ".bin", base + ".zx0"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(base + ".zx0", "rb") as f:
        return f.read()


def kind(name):
    return name.split("_")[0]


def stats(label, raw, pk):
    r, p = sum(raw), sum(pk)
    ratios = [a / b for a, b in zip(raw, pk)]
    return (f"{label}: n={len(raw)} raw={r} packed={p} ratio={r/p:.3f}x | "
            f"packed/frame min={min(pk)} med={statistics.median(pk)} max={max(pk)} | "
            f"per-frame ratio min={min(ratios):.2f} med={statistics.median(ratios):.2f} "
            f"max={max(ratios):.2f}")


def run_set(name, frames):
    d = os.path.join(OUT, name)
    os.makedirs(d, exist_ok=True)
    lines, raw, pk = [], [], []
    for n, data in frames:
        z = zx0(data, os.path.join(d, n))
        raw.append(len(data))
        pk.append(len(z))
        lines.append(f"  {n:24s} raw={len(data):4d} packed={len(z):4d} {len(data)/len(z):5.2f}x")
    rep = [f"== {name} ==", stats("per-frame", raw, pk)]
    kinds = {}
    for n, data in frames:
        kinds.setdefault(kind(n), bytearray()).extend(data)
    kr, kp = [], []
    for k, data in kinds.items():
        z = zx0(bytes(data), os.path.join(d, k + ".kblock"))
        kr.append(len(data))
        kp.append(len(z))
    rep.append(stats("per-kind-block", kr, kp))
    n = len(frames)
    rep.append(f"pointer/length table: per-frame = {n} x 2 B (packed offset; length = next - this) = {2*n} B"
               f"; per-kind = {len(kinds)} x 2 B block ptrs ({2*len(kinds)} B) + {n} x 2 B"
               f" in-block raw offsets = {2*len(kinds)+2*n} B")
    rep.append(f"net incl. tables: per-frame {sum(pk)+2*n} B ({sum(raw)/(sum(pk)+2*n):.3f}x); "
               f"per-kind {sum(kp)+2*len(kinds)+2*n} B "
               f"({sum(raw)/(sum(kp)+2*len(kinds)+2*n):.3f}x)")
    rep.append("per-frame detail:")
    rep += lines
    with open(os.path.join(d, "report.txt"), "w") as f:
        f.write("\n".join(rep) + "\n")
    print("\n".join(rep[:5]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["game", "concept", "all"], default="all")
    a = ap.parse_args()
    if not os.path.exists(ZX0):
        sys.exit("tools/bin/zx0 missing: run tools/setup_zx0.sh")
    if a.set in ("game", "all"):
        run_set("game", game_frames())
    if a.set in ("concept", "all"):
        run_set("concept", concept_frames())


if __name__ == "__main__":
    main()
