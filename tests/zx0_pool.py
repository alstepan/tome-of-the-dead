#!/usr/bin/env python3
"""A5 gate: the pre-shift pool generated from ZX0-packed sources is byte-identical
to the one generated from the raw sources.

Builds two variants of src/main.asm into private temp dirs (tools/build.sh -o
DIR with -DZX0_SOURCES=1 and =0; build.sh runs tools/zx0_sources.py first),
boots each in ZEsarUX and dumps, at five points:
  boot     first select_tick (boot pool: monsters + the two select idles)
  knight   first tick_work after '1'
  wizard   first tick_work after '2' (fresh boot)
  k->w     knight game, GAME_STATE poked to DEAD, ENTER -> select -> '2':
           the wizard is regenerated AFTER a room was built, i.e. GEN_SCRATCH
           (= ROOM_MAP/NEXT_MAP) was overwritten — exercises the block-cache
           invalidation
  stale    (A6 negative cache test) wizard game -> select; at the select
           screen GEN_ZBLK is poked to the wizard's first block and
           GEN_SCRATCH is filled with garbage, then '2': alloc_restore must
           drop the cache, so the regenerated wizard equals the fresh one
the pool banks 0/4/6 (whole 16 KB each, read with set-memory-zone 0), the FRT
(FRT_MAX x 16 B; compared over the shorter of two builds' tables), SEL_FRT_SAVE
and the allocator state, and compares the variants byte-for-byte. Also asserts GEN_OVERFLOW = 0 and GEN_TRAP = 0 at
every point, and reports cold-path T-states (get-tstates-partial):
boot -> first select_tick, select key -> first tick_work.

Usage: python3 tests/zx0_pool.py [--baseline SRC_DIR]
  --baseline: also build SRC_DIR (e.g. a `git archive` of an older commit)
  with no -D flags — via its tools/build.sh if it has one, else its
  zx0_sources.py (if any) + sjasmplus — and compare it too (and time it).
Exit 1 on any mismatch / trap.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
from test_harness import Harness  # noqa: E402

EMU_ARGS = tuple(os.environ.get("GAME_EMU_ARGS",
                                "--emulatorspeed 1000 --vo null --ao null").split())
POOL_BANKS = (0, 4, 6)
RUN_LIMIT = 8000000
KEY = {"1": (3, 0), "2": (3, 1), "ENTER": (6, 0)}   # (KBD_MATRIX row, bit)
GS_DEAD, GS_SELECT, GS_PLAYING = 4, 5, 2


def build(src_root, defines, out):
    os.makedirs(os.path.join(out, "build"), exist_ok=True)
    flags = [f"-D{d}" for d in defines]
    if os.path.exists(os.path.join(src_root, "tools/build.sh")):
        cmd = [os.path.join(src_root, "tools/build.sh"), "-o", out] + flags
    else:   # pre-A6 checkout: no build.sh — pack (if it is a ZX0 build) + assemble
        if os.path.exists(os.path.join(src_root, "tools/zx0_sources.py")):
            bin_ = os.path.join(src_root, "tools/bin")
            if not os.path.exists(bin_):            # a git archive has no binaries
                os.symlink(os.path.join(REPO, "tools/bin"), bin_)
            subprocess.run([sys.executable, os.path.join(src_root, "tools/zx0_sources.py")],
                           check=True)
        cmd = ["sjasmplus", os.path.join(src_root, "src/main.asm"), "--fullpath",
               "--sym=build/wazhack.sym", "-i", os.path.join(src_root, "src")] + flags
    r = subprocess.run(cmd, cwd=out, capture_output=True, text=True)
    if r.returncode or "warning" in r.stdout.lower().replace("warnings: 0", ""):
        sys.exit(f"build failed ({defines}):\n{r.stdout}\n{r.stderr}")
    disp = [ln for ln in r.stdout.splitlines() if ln.startswith(">")]
    syms = {}
    for line in open(os.path.join(out, "build/wazhack.sym")):
        m = re.match(r"^([A-Za-z_][\w.]*):\s+EQU\s+0x([0-9A-Fa-f]+)", line)
        if m:
            syms[m.group(1)] = int(m.group(2), 16)
    return os.path.join(out, "build/wazhack.sna"), syms, disp


class Run:
    def __init__(self, h, sna, S):
        self.h, self.z, self.sna, self.S = h, h.z, sna, S

    def load(self):
        self.z.cmd("enter-cpu-step")
        self.z.cmd("smartload " + self.sna)
        self.z.cmd("enable-breakpoints")
        for n in range(1, 33):
            self.z.cmd("set-breakpoint %d" % n)

    def bp(self, *labels):
        for n in range(1, 33):
            self.z.cmd("set-breakpoint %d" % n)
        for i, lb in enumerate(labels, 1):
            self.z.cmd("set-breakpoint %d PC=%d" % (i, self.S[lb]))

    def pc(self):
        return int(self.z.cmd("get-registers")[3:7], 16)

    def run_to(self, *labels):
        """Run until PC hits one of labels; returns T-states since the call."""
        want = {self.S[lb] for lb in labels}
        self.bp(*labels)
        self.z.cmd("reset-tstates-partial")
        if self.pc() in want:
            self.z.cmd("cpu-step")            # leave the current probe first
        for _ in range(50):
            self.z.cmd("run %d" % RUN_LIMIT)
            if self.pc() in want:
                return int(self.z.cmd("get-tstates-partial"))
        raise RuntimeError(f"never reached {labels}")

    def wb(self, name, v):
        self.z.cmd("write-memory %d %d" % (self.S[name], v))

    def rb(self, name):
        return self.z.read_memory(self.S[name], 1)[0]

    def hold(self, *keys):
        rows = [0xFF] * 8
        for k in keys:
            r, b = KEY[k]
            rows[r] &= ~(1 << b) & 0xFF
        self.z.cmd("write-memory %d %s" % (self.S["KBD_MATRIX"], " ".join(map(str, rows))))

    def dump(self):
        self.z.cmd("set-memory-zone 0")
        try:
            ram = self.z.read_memory(0, 131072)
        finally:
            self.z.cmd("set-memory-zone -1")
        S = self.S
        frt = self.z.read_memory(S["FRT"], S["FRT_MAX"] * S["FRT_STRIDE"])
        return {
            "pool": {b: ram[b * 16384:(b + 1) * 16384] for b in POOL_BANKS},
            "FRT": frt,
            "FT": self.z.read_memory(S["frame_tab"], S["FRT_MAX"] * ft_layout(S)[0]),
            "FTL": ft_layout(S),
            "SEL_FRT_SAVE": self.z.read_memory(S["SEL_FRT_SAVE"], 2 * S["FRT_STRIDE"]),
            "alloc": self.z.read_memory(S["ALLOC_IDX"], 6),
            "GEN_OVERFLOW": self.rb("GEN_OVERFLOW"),
            "GEN_TRAP": self.rb("GEN_TRAP") if "GEN_TRAP" in S else 0,
        }

    def poke_stale_cache(self):
        """A6: a stale one-block cache that WOULD be hit — GEN_ZBLK = the
        wizard's first block — over garbage in GEN_SCRATCH."""
        S = self.S
        fid0 = S["FID_wizard_idle"]
        if "fdesc_tab" in S:
            # A6+: the block the generator would look up = fdesc_tab[fid0].FD_BLK
            # (bank 5 low RAM, always mapped); raw build: the virtual frame
            # address. Either way it must be non-zero (asserted in main), or
            # the poke would equal "no cached block" and test nothing.
            m = self.z.read_memory(S["fdesc_tab"] + fid0 * S["FDESC_STRIDE"] + S["FD_BLK"], 2)
            blk = m[0] | m[1] << 8
        else:
            # pre-A6 baseline: the block whose first frame is fid0
            n = [k[:-6] for k, v in S.items()
                 if k.startswith("zblk_") and k.endswith("_first") and v == fid0]
            blk = S[n[0]] if n else 0
        self.z.cmd("write-memory %d %d %d" % (S["GEN_ZBLK"], blk & 0xFF, blk >> 8))
        n = S["GEN_SCRATCH_LEN"]
        junk = [(i * 37 + 11) & 0xFF for i in range(n)]
        for o in range(0, n, 128):
            self.z.cmd("write-memory %d %s" % (S["GEN_SCRATCH"] + o,
                                                " ".join(map(str, junk[o:o + 128]))))
        return blk

    def select_hero(self, key):
        self.wb("INPUT_SRC", 1)
        self.hold(key)
        t = self.run_to("tick_work")
        self.hold()
        return t


def scenario(h, sna, S):
    """-> ({point: dump}, {timing: T})"""
    r = Run(h, sna, S)
    out, tm = {}, {}
    r.load()
    tm["boot->select"] = r.run_to("select_tick")
    out["boot"] = r.dump()
    tm["select '1'->tick"] = r.select_hero("1")
    out["knight"] = r.dump()
    # knight -> (dead) -> select -> wizard: room maps were built in between
    r.wb("GAME_STATE", GS_DEAD)
    r.hold("ENTER")
    r.run_to("select_tick")
    r.hold()
    r.run_to("select_tick")
    tm["k->w select '2'->tick"] = r.select_hero("2")
    out["k->w"] = r.dump()
    r.load()
    r.run_to("select_tick")
    tm["select '2'->tick"] = r.select_hero("2")
    out["wizard"] = r.dump()
    # wizard -> (dead) -> select; stale cache + garbage scratch -> '2'
    r.wb("GAME_STATE", GS_DEAD)
    r.hold("ENTER")
    r.run_to("select_tick")
    r.hold()
    r.run_to("select_tick")
    blk = r.poke_stale_cache()
    print(f"  stale-cache poke: GEN_ZBLK={blk:#06x}, GEN_SCRATCH garbage")
    tm["stale select '2'->tick"] = r.select_hero("2")
    out["stale"] = r.dump()
    out["stale"]["blk"] = blk
    return out, tm


def ft_layout(S):
    """(stride, cols offset, H offset) of frame_tab: A6 = 4 B, pre-A6 = 8 B."""
    return S.get("FT_STRIDE", 8), S.get("FT_COLS", 2), S.get("FT_H", 3)


def variants_of(d, fids, stride):
    """Pool bytes of every generated variant of fids, via FRT (bank, addr) and
    the frame_tab size: (cols + (variant odd = shift 4)) * 2 * H."""
    out = b""
    fs, oc, oh = d["FTL"]
    for f in fids:
        cols, h = d["FT"][f * fs + oc], d["FT"][f * fs + oh]
        for v in range(4):
            bank, lo, hi = d["FRT"][f * stride + 3 * v:f * stride + 3 * v + 3]
            if bank == 0xFF:
                continue
            a = (lo | hi << 8) - 0xC000
            out += d["pool"][bank][a:a + (cols + (v & 1)) * 2 * h]
    return out


def diff_bytes(a, b, base):
    bad = [i for i in range(len(a)) if a[i] != b[i]]
    if not bad:
        return "identical"
    return f"{len(bad)} B differ, first at {base + bad[0]:#06x}, last {base + bad[-1]:#06x}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", help="source root of another checkout to compare too")
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="zx0pool_")
    variants = [("zx0", REPO, ["ZX0_SOURCES=1"]), ("raw", REPO, ["ZX0_SOURCES=0"])]
    if a.baseline:
        variants.append(("baseline", os.path.abspath(a.baseline), []))
    res, fails = {}, []
    for name, root, defs in variants:
        sna, S, disp = build(root, defs, os.path.join(tmp, name))
        print(f"[{name}] built {sna}")
        for d in disp:
            if "sprite sources" in d or "ZX0" in d or "low-RAM" in d:
                print(f"[{name}]   {d}")
        h = Harness()
        h.launch(EMU_ARGS)
        try:
            h.z.sock.settimeout(60)
            res[name] = scenario(h, sna, S) + (S,)
        finally:
            h.close()
        for pt, d in res[name][0].items():
            for k in ("GEN_OVERFLOW", "GEN_TRAP"):
                if d[k]:
                    fails.append(f"{name}/{pt} {k}={d[k]}")
        print(f"[{name}] timings: " + ", ".join(f"{k} {v:,} T" for k, v in res[name][1].items()))

    ref = res["raw"][0]
    for name in res:
        if name == "raw":
            continue
        for pt, d in res[name][0].items():
            for b in POOL_BANKS:
                s = diff_bytes(d["pool"][b], ref[pt]["pool"][b], 0xC000)
                print(f"[{'PASS' if s == 'identical' else 'FAIL'}] {name} vs raw {pt:7s} pool bank {b}: {s}")
                if s != "identical":
                    fails.append(f"{name}/{pt}/bank{b}")
            for k in ("FRT", "SEL_FRT_SAVE", "alloc"):
                n = min(len(d[k]), len(ref[pt][k]))     # FRT_MAX may differ (A6: 96 -> 160)
                ok = d[k][:n] == ref[pt][k][:n]
                print(f"[{'PASS' if ok else 'FAIL'}] {name} vs raw {pt:7s} {k}: "
                      f"{'identical' if ok else 'DIFFER'}")
                if not ok:
                    fails.append(f"{name}/{pt}/{k}")
    # within each variant, the wizard regenerated after a knight game (room maps
    # built over GEN_SCRATCH in between) must equal the fresh-boot wizard: its
    # FRT rows, every variant's pool bytes and the allocator state (knight
    # rows, skipped bank tails and bytes above the end legitimately differ)
    for name, root, defs in variants:
        S = res[name][2]
        b_ = res[name][0]["wizard"]
        wz = sorted(v for k, v in S.items() if k.startswith("FID_wizard_") and v < 0x8000)
        st = S["FRT_STRIDE"]
        rows = lambda d: b"".join(d["FRT"][f * st:(f + 1) * st] for f in wz)  # noqa: E731
        vb = variants_of(b_, wz, st)
        blk = res[name][0]["stale"]["blk"]
        print(f"[{'PASS' if blk else 'FAIL'}] {name} stale-cache poke uses a real block "
              f"(fdesc_tab[FID_wizard_idle].FD_BLK = {blk:#06x}, non-zero)")
        if not blk:
            fails.append(f"{name}/stale-blk")
        for pt in ("k->w", "stale"):
            a_ = res[name][0][pt]
            va = variants_of(a_, wz, st)
            ok = rows(a_) == rows(b_) and a_["alloc"] == b_["alloc"] and va == vb and len(va) > 0
            print(f"[{'PASS' if ok else 'FAIL'}] {name} {pt} wizard (FRT rows, alloc, "
                  f"{len(va)} B of variants) == fresh-boot wizard")
            if not ok:
                fails.append(f"{name}/{pt}")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"zx0_pool: {'OK' if not fails else 'FAIL ' + ', '.join(fails)}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
