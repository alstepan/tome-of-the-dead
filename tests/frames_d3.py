#!/usr/bin/env python3
"""D3-4 frames check (no emulator): the Stage 3D frames resolve and are as drawn.

Reads build/wazhack.sna + .sym (build first) and the approved D3-3 grids
(assets/gfx/source/d3_grid/*.grid, game.md §6.1-6.4, §11.4):
  F1  every grid frame has FID_<name> < FID_COUNT <= FRT_MAX, inside its kind's
      range: Knight frames in K_KNIGHT; FX frames in K_FXM and/or K_FXW
      (spark_fizz1/2 in both: Spark + Whirlwind impact; staff_bonk Mage)
  F2  frame_tab row (bank 2) = cols W/8, H, FT_OFFR = -ax, FT_OFFL =
      -(W - ax - body_w) with ax from the grid (Knight body 24, FX 8)
  F3  fdesc_tab FD_FLAGS (bank 5): STATIONARY; SYM exactly for the
      mirror-symmetric FX (left = right)
  F4  the packed block (FD_BLK, banks 1/3) unpacks (tools/bin/dzx0) to the
      grid's pixels at FD_FRM: native rows [mask, data] per column, mask 1 =
      '.', data 1 = '#'
  F5  R6 gu_tab fid0 / fcnt of K_FXW / K_FXM (the last two ids) and the
      overlap (K_FXW starts at spark_fizz1 = the last 2 of K_FXM)
  F6  status icons (bank-1 vdata): 7 x 8 B glyphs + 7 attrs == status_icons.grid
Run: python3 tests/frames_d3.py
"""
import glob
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRIDS = os.path.join(REPO, "assets/gfx/source/d3_grid")
DZX0 = os.path.join(REPO, "tools/bin/dzx0")
FXW_ONLY = {"power_burst", "dagger_spin1", "dagger_spin2", "arrow_fly1", "arrow_fly2", "arrow_hit"}
SHARED = {"spark_fizz1", "spark_fizz2"}
COL = {"black": 0, "blue": 1, "red": 2, "magenta": 3, "green": 4, "cyan": 5, "yellow": 6, "white": 7}


def load():
    S = {}
    for ln in open(os.path.join(REPO, "build/wazhack.sym")):
        m = re.match(r"^([A-Za-z_][\w.]*):\s+EQU\s+0x([0-9A-Fa-f]+)", ln)
        if m:
            S[m.group(1)] = int(m.group(2), 16)
    d = open(os.path.join(REPO, "build/wazhack.sna"), "rb").read()
    assert len(d) == 131103, "want a 128K .sna"
    r48, p7 = d[27:27 + 49152], d[49181]
    banks = {5: r48[:16384], 2: r48[16384:32768], p7 & 7: r48[32768:]}
    off = 49183
    for b in range(8):
        if b not in banks:
            banks[b] = d[off:off + 16384]
            off += 16384
    # self-check: virt SRC6 window = bank 6 at the real address (needs a built tree)
    assert S["SRC6_VDELTA"] == 0x8000
    a = S["SRC6_ADDR"]
    assert virt(banks, a - S["SRC6_VDELTA"], 16) == banks[6][a - 0xC000:a - 0xC000 + 16]
    return S, banks


def mem(banks, addr, n):
    """CPU view with the standard $4000 = 5, $8000 = 2 mapping."""
    b, o = (5, addr - 0x4000) if addr < 0x8000 else (2, addr - 0x8000)
    return banks[b][o:o + n]


def virt(banks, v, n):
    """Virtual sprite-source / vdata address: $4000..$7FFF bank 6 (SRC6, real =
    virt + SRC6_VDELTA = virt + $8000), $8000.. bank 1, $C000.. bank 3."""
    assert v >= 0x4000, hex(v)
    if v < 0x8000:
        return banks[6][v - 0x4000:v - 0x4000 + n]
    return banks[1][v - 0x8000:v - 0x8000 + n] if v < 0xC000 else banks[3][v - 0xC000:v - 0xC000 + n]


def read_grid(path):
    meta, rows = {}, []
    for ln in open(path):
        ln = ln.rstrip("\n")
        if re.fullmatch(r"[.+#]+", ln) and len(ln) % 8 == 0 and "size" in meta:
            rows.append(ln)                     # a pixel row (may start with '#')
        else:
            m = re.match(r"# (\w+): (.*)", ln)
            if m:
                meta[m.group(1)] = m.group(2)
    w, h = map(int, meta["size"].split("x"))
    assert len(rows) == h and all(len(r) == w for r in rows), path
    return meta, rows


def native(rows):
    w = len(rows[0])
    out = bytearray()
    for r in rows:
        for c in range(0, w, 8):
            m = d = 0
            for x in range(8):
                ch = r[c + x]
                m |= (ch == ".") << (7 - x)
                d |= (ch == "#") << (7 - x)
            out += bytes((m, d))
    return bytes(out)


def main():
    S, B = load()
    fails = []

    def chk(what, got, want):
        if got != want:
            fails.append(f"{what}: got {got} want {want}")

    blocks = {S[k]: k for k in S if re.fullmatch(r"zblk_\d+", k)}
    unpacked = {}

    def block(addr):
        if addr not in unpacked:
            nm = blocks[addr]
            z = virt(B, addr, S[nm + "_packed"])
            with tempfile.TemporaryDirectory() as t:
                open(os.path.join(t, "b.zx0"), "wb").write(z)
                subprocess.run([DZX0, "-f", os.path.join(t, "b.zx0"), os.path.join(t, "b")],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                unpacked[addr] = open(os.path.join(t, "b"), "rb").read()
        return unpacked[addr]

    chk("FID_COUNT <= FRT_MAX", S["FID_COUNT"] <= S["FRT_MAX"], True)
    names = sorted(os.path.basename(g)[:-5] for g in glob.glob(os.path.join(GRIDS, "*.grid")))
    names.remove("status_icons")
    n = 0
    for nm in names:
        meta, rows = read_grid(os.path.join(GRIDS, nm + ".grid"))
        w, h = map(int, meta["size"].split("x"))
        ax = int(meta["anchor"].split()[0])
        fid = S.get(f"FID_{nm}")
        if fid is None or fid >= S["FID_COUNT"]:
            fails.append(f"F1 {nm}: no FID")
            continue
        n += 1
        knight = nm.startswith("knight_")
        ranges = (["KNIGHT"] if knight else ["FXW"] if nm in FXW_ONLY
                  else ["FXM", "FXW"] if nm in SHARED else ["FXM"])
        for k in ranges:
            f0, fc = S[f"KFID_{k}"], S[f"KFCNT_{k}"]
            chk(f"F1 {nm} in K_{k}", f0 <= fid < f0 + fc, True)
        bw = 24 if knight else 8
        ft = mem(B, S["frame_tab"] + fid * S["FT_STRIDE"], 4)
        chk(f"F2 {nm} frame_tab", list(ft), [w // 8, h, -ax & 0xFF, -(w - ax - bw) & 0xFF])
        fd = mem(B, S["fdesc_tab"] + fid * S["FDESC_STRIDE"], S["FDESC_STRIDE"])
        sym = (not knight) and all(r == r[::-1] for r in rows)
        chk(f"F3 {nm} FD_FLAGS", fd[S["FD_FLAGS"]], S["FF_SYM"] if sym else 0)
        blk = fd[0] | fd[1] << 8
        frm = (fd[2] | fd[3] << 8) - S["GEN_SCRATCH"]
        raw = native(rows)
        chk(f"F4 {nm} pixels", block(blk)[frm:frm + len(raw)] == raw, True)
    chk("F1 frame count (4 Knight + 23 FX)", n, 27)

    gu = B[6][S["gu_tab"] - 0xC000:S["gu_tab"] - 0xC000 + 2 * 32]   # 3F-T2: R6 gu_tab (was kind_tab KT_FID0 / KT_FCNT)
    for k in ("FXW", "FXM"):
        kid = S[f"K_{k}"]
        chk(f"F5 gu_tab K_{k} fid0 / fcnt", (gu[2 * kid], gu[2 * kid + 1]),
            (S[f"KFID_{k}"], S[f"KFCNT_{k}"]))
    chk("F5 ids", (S["K_FXW"], S["K_FXM"], S["K_FX_BASE"] + S["K_KNIGHT"], S["K_FX_BASE"] + S["K_WIZARD"]),
        (30, 31, 30, 31))
    chk("F5 overlap", S["KFID_FXW"], S["FID_spark_fizz1"])
    chk("F5 overlap end", S["KFID_FXM"] + S["KFCNT_FXM"], S["FID_spark_fizz2"] + 1)

    # F6 status icons
    txt = open(os.path.join(GRIDS, "status_icons.grid")).read()
    icons = re.findall(r"^=== (\w+) ink:(\w+) paper:(\w+)( bright)?\n((?:[.#]{8}\n){8})", txt, re.M)
    chk("F6 icon count", len(icons), 7)
    base = S["status_icons"]
    got = virt(B, base, 63)
    for i, (nm, ink, paper, br, body) in enumerate(icons):
        gly = bytes(int(r.replace("#", "1").replace(".", "0"), 2) for r in body.split())
        chk(f"F6 {nm} glyph", got[8 * i:8 * i + 8], gly)
        chk(f"F6 {nm} attr", got[56 + i], COL[ink] | COL[paper] << 3 | (0x40 if br else 0))
    chk("F6 attr table", S["status_icons_attr"] - base, 56)

    if fails:
        print("frames_d3: FAIL")
        for f in fails:
            print("  ", f)
        return 1
    print(f"frames_d3: PASS ({n} frames F1-F4, F5 FX kinds, F6 7 status icons)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
