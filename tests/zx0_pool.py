#!/usr/bin/env python3
"""Pool gate (A5 -> B3B-12): the pre-shift pool the Z80 generator builds from
the ZX0-packed sources is bit-exact to a REFERENCE pool generated here in Python
from the raw frame data (tools/zx0_pack.game_frames(): the DEFB rows of the
frame .asm files, before packing). B3B-12 retired the raw-sources A/B build
(-DZX0_SOURCES=0) this test used to compare against.

Builds src/main.asm into a private temp dir (tools/build.sh -o DIR), boots it
in ZEsarUX and dumps, at five points:
  boot     first select_tick (boot pool: monsters + the two select idles)
  knight   first tick_work after '1' (a generated D1: level_enter runs no
           generator — the pool must be exactly boot + the knight)
  k->w     knight game, GAME_STATE poked to DEAD, ENTER -> select -> '2':
           the wizard is regenerated AFTER rooms were built, i.e. GEN_SCRATCH
           (= ROOM_MAP/NEXT_MAP) was overwritten — block-cache invalidation
  wizard   first tick_work after '2' (fresh boot)
  stale    (A6 negative cache test) wizard game -> select; GEN_ZBLK poked to
           the wizard's first block over garbage GEN_SCRATCH, then '2':
           alloc_restore must drop the cache
the pool banks 0/4/6 (whole 16 KB each), the whole FRT (FRT_MAX x 16 B),
SEL_FRT_SAVE and the allocator state (ALLOC_IDX/PTR, mark). The reference
replays the same generator sessions (boot: alloc_reset, every monster kind,
the two select idles, save + mark; each game: select restores the idles' FRT
rows, alloc_restore, gen_kind(hero), gen_kind(hero + K_FX_BASE) — D3-4: the
class FX kind with its overlapping fid range) over the bank / FRT bytes the snapshot
starts with: allocator, variant choice (MOTION: shift 0 + 4; else the anchor (+4 for FF_PH4)
one shift; SYM: left = right entries), mirror (bit-reversed bytes, reversed
column pairs), the 4-px shift with its spill column. Geometry (frame_tab cols,
H, anchor offsets), kind_tab FID0/FCNT and the frame flags (fdesc_tab
FD_FLAGS) are read from the image; the pixel data never is. Also asserts
GEN_OVERFLOW = 0 and GEN_TRAP = 0 at every point, and reports cold-path
T-states (boot -> first select_tick, select key -> first tick_work).

SRC6 spike: bank 6 is compared up to POOL6_END (= SRC6_ADDR); the SRC6 region
SRC6_ADDR..R6_ADDR must equal the snapshot at every point (never written).
S6: every SRC6 stand-in block is unpacked by zx0_frame from bank 6 bit-exact,
timed against a bank-1 block of similar raw size. Variant "src6" (skip with
--no-src6): the whole run again with the WIZARD's blocks in SRC6
(SRC6_KINDS=K_WIZARD, -DSRC6_PAGES=9): boot idle + wizard games read bank 6.

Usage: python3 tests/zx0_pool.py [--baseline SRC_DIR] [--no-src6]
  --baseline: also build SRC_DIR (e.g. a `git archive` of an older commit)
  and compare its pools to the same reference (and time it).
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


def build(src_root, defines, out, env=None):
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
    r = subprocess.run(cmd, cwd=out, capture_output=True, text=True,
                       env=dict(os.environ, **(env or {})))
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
        if not hasattr(self, "init"):              # the bytes the generator starts from
            self.init = self.dump()

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
            "static": {"kt": self.z.read_memory(S["kind_tab"], 512),
                       "fdesc": self.z.read_memory(S["fdesc_tab"], S["FDESC_COUNT"] * S["FDESC_STRIDE"])}
            if "fdesc_tab" in S else None,
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
        """C3-8a: through the C3-6 menu. '2' toggles HERO (menu_hero persists
        between games: toggled only if it is not the wanted hero), '1' = START;
        the returned T-states are START -> the first play tick (the timed
        generator cold path), as before."""
        self.wb("INPUT_SRC", 1)
        want = 1 if key == "2" else 0
        if "menu_hero" not in self.S:               # --baseline: a pre-C3-6 checkout
            self.hold(key)
            t = self.run_to("tick_work")
            self.hold()
            return t
        if self.rb("menu_hero") != want:
            self.hold("2")
            self.run_to("select_tick")
            self.hold()
            self.run_to("select_tick")
        self.hold("1")
        t = self.run_to("tick_work")
        self.hold()
        return t


def scenario_run(r):
    """-> ({point: dump}, {timing: T})"""
    out, tm = {}, {}
    r.load()
    tm["boot->select"] = r.run_to("select_tick")
    out["boot"] = r.dump()
    tm["select '1'->tick"] = r.select_hero("1")
    out["knight"] = r.dump()
    # knight -> (dead) -> select -> wizard: room maps were built in between
    r.wb("GAME_STATE", GS_DEAD)
    r.run_to("tick_work")                     # C3-6b: the end card arms after a release
    r.run_to("tick_work")
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
    r.run_to("tick_work")                     # C3-6b: the end card arms after a release
    r.run_to("tick_work")
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


def pool6_end(S):
    """SRC6 spike: bank 6's pool ends at POOL6_END (= SRC6_ADDR, below SRC6 +
    R6); older checkouts (--baseline): at R6_ADDR."""
    return S.get("POOL6_END", S["R6_ADDR"])


def decode_call(r, virt):
    """SRC6 S6: zx0_frame(DE = virt, BC = GEN_SCRATCH) from a DI stub with the
    one-block cache cleared -> (T of the call incl. CALL/RET, scratch bytes, HL,
    GEN_ZBLK, $7FFD shadow after)."""
    S, z = r.S, r.z
    stub, res = S["LOWRAM_END_3B"], S["LOWRAM_END_3B"] + 64
    w = lambda v: [v & 0xFF, v >> 8]
    code = ([0xF3, 0x21, 0, 0, 0x22] + w(S["GEN_ZBLK"]) + [0x11] + w(virt) +
            [0x01] + w(S["GEN_SCRATCH"]) + [0xCD] + w(S["zx0_frame"]) +
            [0x22] + w(res) + [0xFB, 0x00, 0x18, 0xFE])
    end = stub + len(code) - 3
    z.cmd("write-memory %d %s" % (stub, " ".join(map(str, code))))
    for n in range(1, 33):
        z.cmd("set-breakpoint %d" % n)
    z.cmd("set-breakpoint 1 PC=%d" % end)
    z.cmd("set-register PC=%d" % stub)
    z.cmd("reset-tstates-partial")
    z.cmd("run %d" % RUN_LIMIT)
    t = int(z.cmd("get-tstates-partial"))
    if r.pc() != end:
        raise RuntimeError(f"zx0_frame stub did not return (virt {virt:#06x})")
    t -= 4 + 10 + 16 + 10 + 10 + 16 + 4            # the stub's own DI / loads / EI
    hl = z.read_memory(res, 2)
    zb = z.read_memory(S["GEN_ZBLK"], 2)
    return (t, z.read_memory(S["GEN_SCRATCH"], S["GEN_SCRATCH_LEN"]),
            hl[0] | hl[1] << 8, zb[0] | zb[1] << 8, r.rb("PORT_7FFD_SHADOW"))


def src6_decode(r, fails, name):
    """S6 (SRC6 spike): every SRC6 stand-in block present in this build is
    unpacked by zx0_frame from bank 6 (virtual FD_BLK = real - SRC6_VDELTA)
    bit-exact to its raw stand-in bytes; GEN_ZBLK = the virtual key, bank 6
    paged after. Its cost is compared with a bank-1 block of similar raw size."""
    import zx0_sources as zs
    S = r.S
    r.load()
    r.run_to("select_tick")                       # generator idle, GEN_SCRATCH free
    with tempfile.TemporaryDirectory() as tmp:
        st = zs.standin_blocks(tmp)
    if name == "src6":
        # race guard: the variant shares the checkout's build/zx0 with tools/build.sh;
        # if that was overwritten with default sources the wizard idle block is in
        # bank 1/3 ($8000+) and this variant would silently test nothing
        fd = S["fdesc_tab"] + S["FID_wizard_idle"] * S["FDESC_STRIDE"]
        blk = r.z.read_memory(fd, 2)
        blk = blk[0] | blk[1] << 8
        ok = blk < 0x8000
        print(f"[{'PASS' if ok else 'FAIL'}] {name} wizard idle FD_BLK {blk:#06x} is in bank 6 (< $8000)")
        if not ok:
            fails.append(f"{name}/wizard-idle-not-in-bank6")
    seen = 0
    for i, g, seg, raw, z_ in st:
        if f"s6s_{i}" not in S:
            continue
        seen += 1
        virt = S[f"s6s_{i}_virt"]
        t, scr, hl, zb, shadow = decode_call(r, virt)
        ok = (scr[:len(raw)] == raw and hl == S["GEN_SCRATCH"] and zb == virt
              and shadow & 7 == S["BANK_SRC6"] and virt < 0x8000)
        b1 = min((k for k in S if re.fullmatch(r"zblk_\d+_raw", k)
                  and 0x8000 <= S[k[:-4]] < 0xC000),          # a bank-1 block
                 key=lambda k: abs(S[k] - len(raw)))[:-4]
        t1, scr1, _, _, sh1 = decode_call(r, S[b1])
        print(f"[{'PASS' if ok else 'FAIL'}] {name} S6 SRC6 stand-in {i} {g}: virt {virt:#06x} "
              f"(bank 6 {S[f's6s_{i}']:#06x}) {len(z_)} -> {len(raw)} B, zx0_frame {t:,} T "
              f"(bank-1 {b1} {S[b1 + '_packed']} -> {S[b1 + '_raw']} B: {t1:,} T, bank {sh1 & 7})")
        if not ok:
            fails.append(f"{name}/S6/{g}")
    if not seen:
        print(f"[FAIL] {name} S6: no SRC6 stand-in block in this build")
        fails.append(f"{name}/S6/none")


def ft_layout(S):
    """(stride, cols offset, H offset) of frame_tab: A6 = 4 B, pre-A6 = 8 B."""
    return S.get("FT_STRIDE", 8), S.get("FT_COLS", 2), S.get("FT_H", 3)


def diff_bytes(a, b, base):
    bad = [i for i in range(len(a)) if a[i] != b[i]]
    if not bad:
        return "identical"
    return f"{len(bad)} B differ, first at {base + bad[0]:#06x}, last {base + bad[-1]:#06x}"


REPO_TOOLS = os.path.join(REPO, "tools")


class Ref:
    """Python model of the boot generator (lowram.asm alloc / gen_kind /
    gen_frame / gen_facing / gen_variant / mirror_src, sel_frt_copy) over raw
    frame pixels. State: the pool banks, the FRT bytes, the allocator, the
    select-idle save; seeded from the snapshot's own bytes (Run.init)."""
    BREV = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))

    def __init__(self, S, init, raw):
        self.S, self.raw = S, raw
        self.pool = {b: bytearray(init["pool"][b]) for b in POOL_BANKS}
        self.frt = bytearray(init["FRT"])
        self.ft, (self.fs, self.oc, self.oh) = init["FT"], init["FTL"]
        st = init["static"]
        self.kt, self.fdesc = st["kt"], st["fdesc"]
        self.idx, self.ptr, self.mark, self.save = 0, S["POOL_START"], (0, S["POOL_START"]), bytearray(32)
        self.overflow = 0

    def alloc(self, n):
        while True:
            if self.idx >= 3:
                return None
            end = self.ptr + n
            lim = pool6_end(self.S) if self.idx == 2 else 0x10000   # bank 6's pool ends below SRC6 / R6
            if end <= lim:
                a, bank = self.ptr, (0, 4, 6)[self.idx]
                if end == 0x10000:
                    self.ptr, self.idx = 0xC000, self.idx + 1
                else:
                    self.ptr = end
                return bank, a
            self.idx, self.ptr = self.idx + 1, 0xC000

    def frame(self, fid):
        S = self.S
        S_FRT = S["FRT_STRIDE"]
        row = fid * S_FRT
        for v in range(4):
            self.frt[row + 3 * v] = S["FRT_NONE"]
        cols, h = self.ft[fid * self.fs + self.oc], self.ft[fid * self.fs + self.oh]
        offr = self.ft[fid * self.fs + S["FT_OFFR"]]
        offl = self.ft[fid * self.fs + S["FT_OFFL"]]
        flags = self.fdesc[fid * S["FDESC_STRIDE"] + S["FD_FLAGS"]]
        src = self.raw[fid]
        assert len(src) == cols * h * 2, (fid, len(src), cols, h)
        self.facing(fid, src, cols, h, flags, offr, 0)
        if flags & S["FF_SYM"]:
            self.frt[row + 6:row + 12] = self.frt[row:row + 6]
            return
        mir = bytearray()
        for y in range(h):
            r = src[y * cols * 2:(y + 1) * cols * 2]
            for c in range(cols - 1, -1, -1):
                mir += bytes((self.BREV[r[2 * c]], self.BREV[r[2 * c + 1]]))
        self.facing(fid, bytes(mir), cols, h, flags, offl, 2)

    def facing(self, fid, src, cols, h, flags, off, var):
        if flags & self.S["FF_MOTION"]:
            self.variant(fid, src, cols, h, var, 0)
            self.variant(fid, src, cols, h, var + 1, 4)
        elif (off + (flags & self.S.get("FF_PH4", 0))) & 7 == 0:   # PHASE_SHIFT: px & 4 = 4
            self.variant(fid, src, cols, h, var, 0)
        else:
            self.variant(fid, src, cols, h, var + 1, 4)

    def variant(self, fid, src, cols, h, var, shift):
        out = bytearray()
        for y in range(h):
            r = src[y * cols * 2:(y + 1) * cols * 2]
            if not shift:
                out += r
                continue
            pm, pd = 0xFF, 0
            for c in range(cols):
                m, d = r[2 * c], r[2 * c + 1]
                out += bytes((((pm << 4) & 0xF0) | (m >> 4), ((pd << 4) & 0xF0) | (d >> 4)))
                pm, pd = m, d
            out += bytes((((pm << 4) & 0xF0) | 0x0F, (pd << 4) & 0xF0))
        a = self.alloc(len(out))
        if a is None:
            self.overflow = 1
            return
        bank, addr = a
        o = fid * self.S["FRT_STRIDE"] + 3 * var
        self.frt[o:o + 3] = bytes((bank, addr & 0xFF, addr >> 8))
        self.pool[bank][addr - 0xC000:addr - 0xC000 + len(out)] = out

    def kind(self, k):
        S = self.S
        f0, n = self.kt[S["KT_FID0"] + k], self.kt[S["KT_FCNT"] + k]
        for f in range(f0, f0 + n):
            self.frame(f)

    def idles(self):
        S = self.S
        return [S["FID_knight_idle1"], S["FID_wizard_idle"]]

    def boot(self):
        S, st = self.S, self.S["FRT_STRIDE"]
        self.idx, self.ptr = 0, S["POOL_START"]   # D3-TX: the text block is under bank 0's pool
        for k in range(S["K_SKELETON"], S["K_COUNT"]):
            self.kind(k)
        for f in self.idles():
            self.frame(f)
        self.save = bytearray(b"".join(self.frt[f * st:(f + 1) * st] for f in self.idles()))
        self.mark = (self.idx, self.ptr)

    def game(self, hero):
        st = self.S["FRT_STRIDE"]
        for i, f in enumerate(self.idles()):          # sel_run: sel_frt_copy restore
            self.frt[f * st:(f + 1) * st] = self.save[i * st:(i + 1) * st]
        self.idx, self.ptr = self.mark                 # alloc_restore
        self.kind(hero)
        if "K_FX_BASE" in self.S:                      # D3-4: + the class FX kind
            self.kind(hero + self.S["K_FX_BASE"])

    def dump(self):
        a = bytes((self.idx, self.ptr & 0xFF, self.ptr >> 8,
                   self.mark[0], self.mark[1] & 0xFF, self.mark[1] >> 8))
        return {"pool": {b: bytes(self.pool[b]) for b in POOL_BANKS}, "FRT": bytes(self.frt),
                "SEL_FRT_SAVE": bytes(self.save), "alloc": a, "GEN_OVERFLOW": self.overflow}


def reference(S, init):
    """{point: reference dump} for scenario()'s five points."""
    sys.path.insert(0, REPO_TOOLS)
    import zx0_pack as zp
    import zx0_sources as zs
    frames = dict(zp.game_frames())
    names = [n for n in zs.frm_order() if n in frames]
    if len(names) != S["FDESC_COUNT"]:
        sys.exit(f"reference: {len(names)} raw frames vs FDESC_COUNT {S['FDESC_COUNT']}")
    raw = [frames[n] for n in names]
    K, W = S["K_KNIGHT"], S["K_WIZARD"]
    out = {}
    r = Ref(S, init, raw)
    r.boot()
    out["boot"] = r.dump()
    r.game(K)
    out["knight"] = r.dump()
    r.game(W)
    out["k->w"] = r.dump()
    r = Ref(S, init, raw)
    r.boot()
    r.game(W)
    out["wizard"] = r.dump()
    r.game(W)
    out["stale"] = r.dump()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", help="source root of another checkout to compare too")
    ap.add_argument("--no-src6", action="store_true",
                    help="skip the SRC6 E2E variant (wizard sources in bank 6)")
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="zx0pool_")
    kit = ["DEBUG_KIT=0"]          # D3-7: suites run on the release start kit
    kit += os.environ.get("ZX0POOL_DEFS", "").split()   # e.g. "PHASE_SHIFT=1"
    variants = [("zx0", REPO, kit, None)]
    if not a.no_src6:
        # SRC6 spike E2E: the WIZARD's real blocks moved to the bank-6 SRC6
        # region (2,055 B packed: 9 pages with the Spider stand-in; pool slack
        # 169) — the boot select idle and every wizard game read their
        # sources from bank 6 while the pool is written to banks 4 / 6
        variants.append(("src6", REPO, kit + ["SRC6_PAGES=9"], {"SRC6_KINDS": "K_WIZARD"}))
    if a.baseline:                 # (an older checkout ignores the unknown define)
        variants.append(("baseline", os.path.abspath(a.baseline), kit, None))
    res, fails = {}, []
    for name, root, defs, env in variants:
        try:
            sna, S, disp = build(root, defs, os.path.join(tmp, name), env)
        finally:
            if env:                # the variant rewrote build/zx0/*: put the default back
                subprocess.run([sys.executable, os.path.join(REPO, "tools/zx0_sources.py")],
                               check=True, stdout=subprocess.DEVNULL)
        print(f"[{name}] built {sna}")
        for d in disp:
            if "sprite sources" in d or "ZX0" in d or "low-RAM" in d or "SRC6" in d:
                print(f"[{name}]   {d}")
        h = Harness()
        h.launch(EMU_ARGS)
        try:
            h.z.sock.settimeout(60)
            r = Run(h, sna, S)
            out, tm = scenario_run(r)
            res[name] = (out, tm, S, r.init)
            if "SRC6_ADDR" in S and name != "baseline":
                src6_decode(r, fails, name)
        finally:
            h.close()
        for pt, d in out.items():
            for k in ("GEN_OVERFLOW", "GEN_TRAP"):
                if d[k]:
                    fails.append(f"{name}/{pt} {k}={d[k]}")
        print(f"[{name}] timings: " + ", ".join(f"{k} {v:,} T" for k, v in tm.items()))

    for name in res:
        out, tm, S, init = res[name]
        ref = reference(S, init)
        for pt, d in out.items():
            for b in POOL_BANKS:
                # bank 6: the pool part only (R6 is live variable space: gd_* / hr_*)
                lim = (pool6_end(S) - 0xC000) if b == 6 else 0x4000
                s_ = diff_bytes(d["pool"][b][:lim], ref[pt]["pool"][b][:lim], 0xC000)
                print(f"[{'PASS' if s_ == 'identical' else 'FAIL'}] {name} vs reference {pt:7s} pool bank {b}: {s_}")
                if s_ != "identical":
                    fails.append(f"{name}/{pt}/bank{b}")
            if "SRC6_ADDR" in S:       # SRC6 spike: the source region is never written
                a0, a1 = S["SRC6_ADDR"] - 0xC000, S["R6_ADDR"] - 0xC000
                s_ = diff_bytes(d["pool"][6][a0:a1], init["pool"][6][a0:a1], S["SRC6_ADDR"])
                print(f"[{'PASS' if s_ == 'identical' else 'FAIL'}] {name} {pt:7s} SRC6 region "
                      f"{S['SRC6_ADDR']:#06x}..{S['R6_ADDR'] - 1:#06x} == snapshot: {s_}")
                if s_ != "identical":
                    fails.append(f"{name}/{pt}/SRC6")
            for k in ("FRT", "SEL_FRT_SAVE", "alloc", "GEN_OVERFLOW"):
                ok = d[k] == ref[pt][k] if k != "FRT" else bytes(d[k]) == ref[pt][k]
                print(f"[{'PASS' if ok else 'FAIL'}] {name} vs reference {pt:7s} {k}: "
                      f"{'identical' if ok else 'DIFFER'}")
                if not ok:
                    fails.append(f"{name}/{pt}/{k}")
        blk = out["stale"]["blk"]
        print(f"[{'PASS' if blk else 'FAIL'}] {name} stale-cache poke uses a real block "
              f"(fdesc_tab[FID_wizard_idle].FD_BLK = {blk:#06x}, non-zero)")
        if not blk:
            fails.append(f"{name}/stale-blk")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"zx0_pool: {'OK' if not fails else 'FAIL ' + ', '.join(fails)}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
