#!/usr/bin/env python3
"""Pool gate (A5 -> B3B-12): the pre-shift pool the Z80 generator builds from
the ZX0-packed sources is bit-exact to a REFERENCE pool generated here in Python
from the raw frame data (tools/zx0_pack.game_frames(): the DEFB rows of the
frame .asm files, before packing). B3B-12 retired the raw-sources A/B build
(-DZX0_SOURCES=0) this test used to compare against.

Builds src/main.asm into a private temp dir (tools/build.sh -o DIR), boots it
in ZEsarUX and dumps, at five points:
  boot     first select_tick (3F-T1: boot pool = the two select idles only)
  knight   first tick_work after '1': idles + knight + its FX (the LEVEL
           mark), then D1's monster kinds (level_enter: LP_KINDS + LP_BOSS
           through pool_gmap, dedup, FRT monster rows NONE first)
  k->w     knight game, GAME_STATE poked to DEAD, ENTER -> select -> '2':
           the wizard is regenerated AFTER rooms were built, i.e. GEN_SCRATCH
           (= ROOM_MAP/NEXT_MAP) was overwritten — block-cache invalidation
  wizard   first tick_work after '2' (fresh boot)
  stale    (A6 negative cache test) wizard game -> select; GEN_ZBLK poked to
           the wizard's first block over garbage GEN_SCRATCH, then '2':
           alloc_restore must drop the cache
the pool banks 0/4/6 (whole 16 KB each), the whole FRT (FRT_MAX x 16 B),
SEL_FRT_SAVE and the allocator state (ALLOC_IDX/PTR, mark). The reference
replays the same generator sessions (3F-T1 — boot: alloc_reset, the two
select idles, save; each game: select restores the idles' FRT rows,
alloc_reset + the idles again, (3F-T2 pool_hero: monster FRT rows + the FX
rows outside the class FX NONE) gen(hero), gen(hero + K_FX_BASE) —
D3-4: the class FX kind with its overlapping fid range —, alloc_mark; each
level: alloc_restore, FRT monster rows + non-class FX rows NONE, the level's generation units
from the LP_KINDS / LP_BOSS bytes read at that point and the snapshot's
pool_gmap) over the bank / FRT bytes the snapshot
starts with: allocator, variant choice (MOTION: shift 0 + 4; else the anchor (+4 for FF_PH4)
one shift; SYM: left = right entries), mirror (bit-reversed bytes, reversed
column pairs), the 4-px shift with its spill column. Geometry (frame_tab cols,
H, anchor offsets), R6 gu_tab fid0 / fcnt (3F-T2) and the frame flags (fdesc_tab
FD_FLAGS) are read from the image; the pixel data never is. Also asserts
GEN_OVERFLOW = 0 and GEN_TRAP = 0 at every point, and reports cold-path
T-states (boot -> first select_tick, select key -> first tick_work).

3F-T1 "levels" (skip with --no-levels): a knight game descends D2..D8 through
the real level_descend (DI stub, like tests/gfx_integrity.py); at every depth
the pool / FRT / allocator == the reference, GEN_OVERFLOW / GEN_TRAP 0, the
pool top + POOL_SIM_MARGIN <= the build's POOL_NEED, and the
level_enter cost (stub T) is reported against the 2 s (7.1M T) budget.
MEM-PS2: the Mage walks D1..D8 too (vs the reference), and at every depth of both
walks plus a PROTO start per hero x 5 / 6 kinds the real ALLOC_IDX / ALLOC_PTR must
EQUAL the build's simulated pool top (main.asm PS_*, POOL_LVL_VERBOSE DISPLAY): an
undercount would let POOL_NEED <= POOL_CAP pass a pool that overflows.

SRC6 spike: bank 6 is compared up to POOL6_END (= SRC6_ADDR); the SRC6 region
SRC6_ADDR..R6_ADDR must equal the snapshot at every point (never written).
S6: every SRC6 block (3F-T13: the real 3F-A1 art) is unpacked by zx0_frame from bank 6 bit-exact,
timed against a bank-1 block of similar raw size. Variant "src6" (skip with
--no-src6): the whole run again with the WIZARD's blocks in SRC6
(SRC6_KINDS=+K_WIZARD, -DSRC6_PAGES=19, minus K_DKNIGHT; 3F-T13): boot idle + wizard games read bank 6.

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


# 3F-D7LEV: the per-level pool need (POOL_FIXED + hero + level monsters, B), (hero, depth);
# hero 0 = Warrior, 1 = Mage. Was (3F-T13) D7 Warrior 34,080: Skeleton / Goblin walk
# rotated (WALK1 one shift: -576 B a Skeleton / Archer / Goblin level, -384 B D1) and the
# Ghost's FLOAT1 one shift (-512 B on D3 / D6 / D7 / D8). 3F-T13bc: the ART2 / ART3 frames
# (Orc / Ogre RAISE, Vampire BITE (+ Necro walk3, no cast), Necro walk3, Mummy walk3/4, the
# shared climb pair for Orc / Necro / Archer levels, the symmetric small corpse (-128 B a Rat /
# Spider level), dk_block out, the DK B3 walk3 +768 on D7) and ARCHER-DEPTHS H1 (no Archer on D7: the 2nd Necro, no Mage
# arrows there). MEM-W1: skeleton_collapsed 24x48 -> 24x16 (-384 a Skeleton level) and
# knight_windup 40x48 -> 32x48 (-192, Warrior); pixels unchanged. fix/archer-climb: the Archer / Sniper climb on the SKELETON's own pair (unit U_SKCLIMB): D4 +576 (Orc keeps the shared pair), D5 unchanged (the Mummy needs the shared pair, the Archer shares the Skeleton's). Update with a reason only.
# CORPSE-ASHES: skeleton_collapsed / goblin_dead / dead_humanoid -> the shared small_corpse (U_DEADR):
# W D1..D8 -320 -320 -384 -320 -512 -192 -192 -384 (Mage the same).
# JUMP-ALT (user 2026-10-29): knight_jump2 / wizard_jump2 MOT -> WK4, the jump pose picked by px parity: every need -576.
# ANIM-IMPORT2 (1) heroes at 40 px (J-a: jump2 MOT again, +480 at 40 rows) + the select idles at 40
# rows (POOL_FIXED -192): Warrior -1,920 - 192 = -2,112, Mage -1,120 - 192 = -1,312 every level.
# ANIM-IMPORT2 (2) Skeleton family (U_SKARCH / U_SKCLIMB / U_SKREST) + the shared climb pair at 40 px:
# both heroes D1..D8 0 0 -864 -864 -960 -96 -96 -960.
# ANIM-IMPORT2 (3) Orc V4 at 40 px (6 frames: +orc_walk3 / orc_hurt), Mummy V2 + Necro V2 at 40 px
# (the Vampire still draws the Necro walk): both heroes D1..D8 0 0 -448 +640 -576 +64 +64 -576.
# ANIM-IMPORT2 (4) the Vampire's own 40-px set (5 frames, unit K_VAMPIRE; was the Necro walk + U_VBITE):
# both heroes D1..D8 0 0 -128 0 0 +2112 0 +2112 (POOL_CAP 33,050 -> 32,538: SRC6 13 -> 15 pages).
# ANIM-X12 X1 + X2 (Orc / Vampire 4th walk pose, +1 fid each = +480 B pool on every level that has the
# kind): both heroes D1..D8 0 0 +480 +480 0 +960 +480 +480; SRC6 15 -> 16 pages (POOL_CAP 32,538 -> 32,269).
# SPIDER-CLIMB (spider_climb1/2 STA|SYM 32x16 in the K_SPIDER unit, 128 B pool each): both heroes D2 D4 D5
# +256 (the Spider levels); POOL_CAP unchanged (SRC6 +163 B, 57 free of 16 pages).
# 3F-T9 VAMPIRE BAT FORM (K_VBAT = the Bat's flapup / glide, 2 MOT frames, 448 B each, via pool_gmap
# K_VAMPIRE; on D3 merged into the Bat's unit by pl_unit): both heroes D6 D8 +896; D8 is the worst level now.
# MEM-PS2: the need is the SIMULATED pool top (main.asm PS_*: alloc replayed variant by variant, the real
# skipped bank tails) + POOL_SIM_MARGIN 64, no longer + POOL_FIXED's 3 x 576 straddle guess: every need
# -1,728 + 64 + the level's real straddle waste (Warrior 25 B everywhere; Mage D1..D8 25 89 41 281 153 41 281 217).
# 3F-T11 the nun Archmage's own 4 frames (unit K_ARCHMAGE: walk1 WK0 480, walk2 WK4 640, cast / hurt STA
# 480; was the Necro's walk + U_NCAST, which the D8 Necro still loads): both heroes D8 only, Warrior +2,160
# (2,080 + the bank 0 -> 4 straddle 25 -> 105), Mage +2,080; sources in bank 1, POOL_CAP unchanged.
# M0 (L4, 2026-10-31): POOL_START fixed at $C960 (text 2,326 + 45 B reserve + the 29-B bank-0 cold-code
# reserve: +74 B under bank 0, POOL_CAP 32,490 -> 32,416): every need is the old one - 74 + the level's new
# bank 0 -> 4 straddle waste: Warrior D1..D7 -10 (straddle 25 -> 89), D8 -74 (worst level, slack 1,264 kept);
# Mage D1 +54, D2 -74, D3 +166, D4 -74, D5 -74, D6 +166, D7 -74, D8 -74 (slack D3 / D6 Mage 8,896 / 6,688).
# M1 (2026-11-01, user-approved 240-B step): POOL_START $C960 -> $CA40 (text 2,378 + 40 B headroom + 206 B
# bank-0 cold-code room = 2,624 B under bank 0, POOL_CAP 32,416 -> 32,192): Warrior D8 +16 (straddle), the
# Mage levels +32 / +160 / +96 / +96 / +224 / +96 / +96 / +96; D8 Warrior slack 1,264 -> 1,024.
# VAMP-BOSS (2026-11-02): the Vampire climbs, pool_gmap adds U_CLIMBH for K_VAMPIRE: D3 (the only level
# without the shared climb pair: D6 / D8 already pool it via Orc / Necro / Mummy) +480 for both heroes
# (Warrior 26,528 -> 27,008, Mage 23,616 -> 24,096; slack 5,184 / 8,096), every other level unchanged.
# BOSS-RANGED rebaseline: +12 on every level = RECLAIM-B T1 (text -12 B -> POOL_START 12 B lower: the
# need is measured to the pool top; the slack line is unchanged); BOSS-RANGED itself adds no pool frames
# (dagger_spin is already pooled on D1 / D2 for both heroes)
# D3-11 (user-approved slack step, 2026-11-02): POOL_START 492 B higher (B0_CODE_RES 212 -> 704, the
# flying numbers in bank 0; POOL_CAP 32,204 -> 31,712): every need is the old one - 12 + the level's new
# bank 0 -> 4 straddle (Warrior D1..D7 -12, D8 +148 (worst level, slack 1,024 -> 384); Mage D1 -44, D2 +20,
# D3..D7 -172, D8 -236); no pool frame changed
# SPIT-SPARK (2026-11-03): the Warrior's spark_fly1/2 extra (the Queen's spit) on the Spider levels: D2 / D4 / D5 +64
# (Warrior only; the Mage's class FX holds the frames); D8 (the binding level, slack 384) unchanged.
LEVEL_NEED = {
    (0, 1): 22528, (0, 2): 22304, (0, 3): 27008, (0, 4): 28640,
    (0, 5): 23136, (0, 6): 28736, (0, 7): 27744, (0, 8): 31328,
    (1, 1): 19456, (1, 2): 19296, (1, 3): 23936, (1, 4): 25632,
    (1, 5): 20128, (1, 6): 25664, (1, 7): 24672, (1, 8): 27936,
}


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
               "--sym=build/tome-of-the-dead.sym", "-i" + os.path.join(src_root, "src")] + flags
    r = subprocess.run(cmd, cwd=out, capture_output=True, text=True,
                       env=dict(os.environ, **(env or {})))
    if r.returncode or "warning" in r.stdout.lower().replace("warnings: 0", ""):
        sys.exit(f"build failed ({defines}):\n{r.stdout}\n{r.stderr}")
    disp = [ln for ln in r.stdout.splitlines() if ln.startswith(">")]
    syms = {}
    for line in open(os.path.join(out, "build/tome-of-the-dead.sym")):
        m = re.match(r"^([A-Za-z_][\w.]*):\s+EQU\s+0x([0-9A-Fa-f]+)", line)
        if m:
            syms[m.group(1)] = int(m.group(2), 16)
    return os.path.join(out, "build/tome-of-the-dead.sna"), syms, disp


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
                if "select_tick" in labels and self.S.get("GS_ANYKEY") and \
                        self.rb("GAME_STATE") in (self.S["GS_ANYKEY"], self.S.get("GS_HELP1"), self.S.get("GS_HELP2"),
                                          self.S.get("GS_HELP3")):
                    self.anykey(want)             # BOOT-ANYKEY: answer, run on to the menu
                    continue
                return int(self.z.cmd("get-tstates-partial"))
        raise RuntimeError(f"never reached {labels}")

    def anykey(self, want):
        """instr_main's key waits (GS_ANYKEY, GS_HELP1 / 2 / 3; one call each, probe = select_tick): released for 2 frames, ENTER for 2,
        released for 2 (ENTER and '1' share a menu bit), each frame = one select_tick."""
        self.wb("INPUT_SRC", 1)
        for keys in ((), (), ("ENTER",), ("ENTER",), (), ()):
            self.hold(*keys)
            self.z.cmd("cpu-step")
            self.z.cmd("run %d" % RUN_LIMIT)
        self.hold()

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
            "LP": [k & S["LEK_KIND_MASK"] for k in self.z.read_memory(S["LP_KINDS"], 5)],   # LP_KINDS[0..3] + LP_BOSS (3F-T5: minus LEK_GOLD)
            "depth": self.rb("LVL_DEPTH"),
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

    def descend(self, depth):
        """3F-T1: from a play tick, LVL_DEPTH = depth - 1 + the real
        level_descend from a DI stub (no ISR: stinger_wait returns at once,
        as in tests/gfx_integrity.py) -> T of the stub; PC put back."""
        S, z = self.S, self.z
        stub = S["LOWRAM_END_3B"]
        w = lambda v: [v & 0xFF, v >> 8]
        code = ([0xF3, 0x3E, depth - 1, 0x32] + w(S["LVL_DEPTH"]) + [0xCD] + w(S["level_descend"])
                + [0xFB, 0x00, 0x18, 0xFE])
        end = stub + len(code) - 3
        pc0 = self.pc()
        z.cmd("write-memory %d %s" % (stub, " ".join(map(str, code))))
        for n in range(1, 33):
            z.cmd("set-breakpoint %d" % n)
        z.cmd("set-breakpoint 1 PC=%d" % end)
        z.cmd("set-register PC=%d" % stub)
        z.cmd("reset-tstates-partial")
        z.cmd("run %d" % (4 * RUN_LIMIT))
        t = int(z.cmd("get-tstates-partial"))
        if self.pc() != end:
            raise RuntimeError(f"level_descend stub to D{depth} did not return")
        z.cmd("set-register PC=%d" % pc0)
        return t

    def proto_poke(self):
        """D3-11: the PROTO rooms are a test fixture (build/ovl/proto.bin, next to the
        .sna): poked at PROTO_FIX_ORG while start_game waits at proto_hook."""
        img = open(os.path.join(os.path.dirname(self.sna), "ovl", "proto.bin"), "rb").read()
        for i in range(0, len(img), 64):
            self.z.cmd("write-memory %d %s" % (self.S["PROTO_FIX_ORG"] + i, " ".join(str(b) for b in img[i:i + 64])))

    def select_hero(self, key, proto=False):
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
        if proto:                                   # D3-11: the fixture at proto_hook
            self.run_to("proto_hook")
            self.proto_poke()
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
    r.wb("END_SHOWN", r.S["ES_CARD"])         # END-WAIT: card up, quiet spent = waiting for a key
    r.run_to("tick_work")
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
    r.wb("END_SHOWN", r.S["ES_CARD"])         # END-WAIT: card up, quiet spent = waiting for a key
    r.run_to("tick_work")
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


def levels_run(r, depths, key="1", pre=""):
    """3F-T1: knight game ('1'; MEM-PS2: '2' = the Mage, points prefixed pre), D1 then
    D2..depths via level_descend -> ({'<pre>D<n>': dump}, {T})."""
    out, tm = {}, {}
    r.load()
    r.run_to("select_tick")
    r.select_hero(key)
    r.wb("SND_MODE", 2)                # SFX only: no stinger to wait for (a DI stub
    out[f"{pre}D1"] = r.dump()         # would hang in stinger_wait's menu_frame)
    for d in range(2, depths + 1):
        r.run_to("tick_work")
        tm[f"{pre}level_enter D{d}"] = r.descend(d)
        out[f"{pre}D{d}"] = r.dump()
    return out, tm


def proto_run(r):
    """MEM-PS2: a PROTO-fixture game per hero and kind count (proto_start 1 = 5 kinds,
    3 = + the Slime) -> {(hero, kinds): ALLOC_IDX / PTR / GEN_OVERFLOW / GEN_TRAP} at the
    first play tick (pool_proto's session done). Each starts from a fresh load (a PROTO
    session pools over SRC6)."""
    out = {}
    for hero, key in ((0, "1"), (1, "2")):
        for kinds, ps in ((5, 1), (6, 3)):
            r.load()
            r.wb("proto_start", ps)
            r.run_to("select_tick")
            r.select_hero(key, proto=True)
            a = r.z.read_memory(r.S["ALLOC_IDX"], 3)
            out[(hero, kinds)] = {"alloc": a, "GEN_OVERFLOW": r.rb("GEN_OVERFLOW"),
                                  "GEN_TRAP": r.rb("GEN_TRAP")}
    return out


def linear_top(S, idx, ptr):
    """The pool top as main.asm PS_LINEAR: bank 0 from POOL_START, a skipped bank tail used."""
    return [(ptr - S["POOL_START"]),
            (0x10000 - S["POOL_START"]) + (ptr - 0xC000),
            (0x10000 - S["POOL_START"]) + 0x4000 + (ptr - 0xC000)][min(idx, 2)]


def sim_check(name, what, S, real, sim, fails):
    """MEM-PS2: the build's simulated pool top (idx, ptr) must equal the real one; an
    undercount (simulated < real) would let the ASSERT pass a pool that overflows."""
    ri, rp = real[0], real[1] | real[2] << 8
    si, sp = sim
    ru, su = linear_top(S, ri, rp), linear_top(S, si, sp)
    ok = (ri, rp) == (si, sp)
    tag = "" if ok else (" UNDERCOUNT" if su < ru else " (over)")
    print(f"[{'PASS' if ok else 'FAIL'}] {name} pool sim {what}: real idx {ri} ptr {rp:#06x} "
          f"({ru:,} B) == simulated idx {si} ptr {sp:#06x} ({su:,} B){tag}")
    if not ok:
        fails.append(f"{name}/sim/{what}")


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
    """S6 (SRC6 spike; 3F-T13: the real 3F-A1 blocks, the stand-ins are retired):
    every SRC6 block of this build (zblk_N at a bank-6 address in SRC6_ADDR..
    R6_ADDR) is unpacked by zx0_frame from bank 6 (virtual FD_BLK = real -
    SRC6_VDELTA) bit-exact to the raw bytes of its frames (zblk_N_first ..
    + zblk_N_n in FRM order); GEN_ZBLK = the virtual key, bank 6 paged after.
    Its cost is compared with a bank-1 block of similar raw size."""
    import zx0_pack as zp
    import zx0_sources as zs
    S = r.S
    r.load()
    r.run_to("select_tick")                       # generator idle, GEN_SCRATCH free
    frames = dict(zp.game_frames())
    names = [n for n in zs.frm_order() if n in frames]
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
    for b in range(S["ZX0_BLOCKS"]):
        lab = f"zblk_{b}"
        if not (S["SRC6_ADDR"] <= S[lab] < S["R6_ADDR"]):
            continue
        seen += 1
        f0, n = S[lab + "_first"], S[lab + "_n"]
        raw = b"".join(frames[nm] for nm in names[f0:f0 + n])
        virt = S[lab] - S["SRC6_VDELTA"]
        t, scr, hl, zb, shadow = decode_call(r, virt)
        ok = (len(raw) == S[lab + "_raw"] and scr[:len(raw)] == raw and hl == S["GEN_SCRATCH"]
              and zb == virt and shadow & 7 == S["BANK_SRC6"] and virt < 0x8000)
        b1 = min((k for k in S if re.fullmatch(r"zblk_\d+_raw", k)
                  and 0x8000 <= S[k[:-4]] < 0xC000),          # a bank-1 block
                 key=lambda k: abs(S[k] - len(raw)))[:-4]
        t1, scr1, _, _, sh1 = decode_call(r, S[b1])
        print(f"[{'PASS' if ok else 'FAIL'}] {name} S6 SRC6 block {b} [{', '.join(names[f0:f0 + n])}]: "
              f"virt {virt:#06x} (bank 6 {S[lab]:#06x}) {S[lab + '_packed']} -> {len(raw)} B, zx0_frame {t:,} T "
              f"(bank-1 {b1} {S[b1 + '_packed']} -> {S[b1 + '_raw']} B: {t1:,} T, bank {sh1 & 7})")
        if not ok:
            fails.append(f"{name}/S6/{lab}")
    if not seen:
        print(f"[FAIL] {name} S6: no SRC6 block in this build")
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
        a = init["alloc"]                              # 3F-T1: boot sets no mark any more
        self.idx, self.ptr, self.save = 0, S["POOL_START"], bytearray(32)
        self.mark = (a[3], a[4] | a[5] << 8)
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

    def unit(self, u):
        """(fid0, fcnt) of generation unit u (3F-T2: R6 gu_tab, read from the
        snapshot's bank 6; was kind_tab KT_FID0 / KT_FCNT)."""
        if "gu_tab" not in self.S:                  # --baseline: a pre-3F-T2 checkout
            return self.kt[self.S["KT_FID0"] + u], self.kt[self.S["KT_FCNT"] + u]
        o = self.S["gu_tab"] - 0xC000 + 2 * u
        return self.pool[6][o], self.pool[6][o + 1]

    def kind(self, k):
        f0, n = self.unit(k)
        for f in range(f0, f0 + n):
            self.frame(f)

    def frt_none(self, f0, n):
        st = self.S["FRT_STRIDE"]
        k = self.S.get("FT_IN_ROW", st)                # MEM-FT: the row tail is frame_tab (kept)
        for f in range(f0, f0 + n):
            self.frt[f * st:f * st + k] = bytes([self.S["FRT_NONE"]]) * k

    def begin(self, hero):
        """R6 pl_begin (3F-T2), every pool_hero / pool_list session: monster
        FRT rows NONE, then the FX rows outside the hero's class FX unit."""
        S = self.S
        self.frt_none(S["KFID_MONSTERS"], S["KFCNT_MONSTERS"])
        if "gu_tab" not in S:                          # --baseline: pre-3F-T2 keeps the other FX rows
            return
        fx0, fxn = S["KFID_FXM"], S["KFID_FXW"] + S["KFCNT_FXW"]
        h0, hn = self.unit(hero + S["K_FX_BASE"])
        if h0 > fx0:
            self.frt_none(fx0, h0 - fx0)
        if fxn > h0 + hn:
            self.frt_none(h0 + hn, fxn - h0 - hn)

    def idles(self):
        S = self.S
        return [S["FID_knight_idle1"], S["FID_wizard_idle"]]

    def gen_idles(self):
        S = self.S
        self.idx, self.ptr, self.overflow = 0, S["POOL_START"], 0   # alloc_reset (D3-TX: above the text)
        for f in self.idles():
            self.frame(f)

    def boot(self):
        st = self.S["FRT_STRIDE"]
        self.gen_idles()                               # 3F-T1: the idles only
        self.save = bytearray(b"".join(self.frt[f * st:(f + 1) * st] for f in self.idles()))

    def game(self, hero, lp):
        st = self.S["FRT_STRIDE"]
        for i, f in enumerate(self.idles()):          # sel_run: sel_frt_copy restore
            self.frt[f * st:(f + 1) * st] = self.save[i * st:(i + 1) * st]
        self.gen_idles()                               # start_game (3F-T1): from the bottom
        self.hero = hero
        self.begin(hero)                               # 3F-T2 pool_hero
        self.kind(hero)
        if "K_FX_BASE" in self.S:                      # D3-4: + the class FX kind
            self.kind(hero + self.S["K_FX_BASE"])
        self.mark = (self.idx, self.ptr)               # alloc_mark: the LEVEL mark
        self.level(lp)

    def gen_list(self, lp):
        """pool_list (R6): LP_KINDS + LP_BOSS through pool_gmap, dedup, in order."""
        S = self.S
        o = S["pool_gmap"] - 0xC000
        gm = self.pool[6][o:o + 3 * S["PGMAP_N"]]      # R6 never changes in play here
        nx = S.get("PXMAP_N", 0) if "pool_xmap" in S else 0     # --baseline: pre-3F-T2 has none
        o = S.get("pool_xmap", 0xC000) - 0xC000        # 3F-T2 hero extras: kind, hero, unit
        xm = self.pool[6][o:o + 3 * nx]
        out = []
        for k in lp:
            # 3F-T13: every pool_gmap record of the kind applies (no record: its own unit)
            us = [u for r in range(S["PGMAP_N"]) if gm[3 * r] == k
                  for u in gm[3 * r + 1:3 * r + 3] if u != 0xFF] or [k]
            us += [xm[3 * r + 2] for r in range(nx)
                   if xm[3 * r] == k and xm[3 * r + 1] == self.hero]
            out += [u for u in us if u not in out and self.unit(u)[1]]
        return out

    def level(self, lp):
        S, st = self.S, self.S["FRT_STRIDE"]
        self.idx, self.ptr = self.mark                 # alloc_restore
        self.begin(self.hero)                          # 3F-T2 pool_list's pl_begin
        # pl_unit (R6) keeps one range per fid0, the longer count (3F-T9: K_VBAT's 2 Bat frames
        # merge into the Bat's unit on D3), in first-seen order
        rng = {}
        for k in self.gen_list(lp):
            f0, n = self.unit(k)
            rng[f0] = max(rng.get(f0, 0), n)
        for f0, n in rng.items():
            for f in range(f0, f0 + n):
                self.frame(f)

    def dump(self):
        a = bytes((self.idx, self.ptr & 0xFF, self.ptr >> 8,
                   self.mark[0], self.mark[1] & 0xFF, self.mark[1] >> 8))
        return {"pool": {b: bytes(self.pool[b]) for b in POOL_BANKS}, "FRT": bytes(self.frt),
                "SEL_FRT_SAVE": bytes(self.save), "alloc": a, "GEN_OVERFLOW": self.overflow}


def reference(S, init, out_run, lv=None):
    """{point: reference dump} for scenario()'s five points (+ levels_run's)."""
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
    lp = lambda pt: bytes(out_run[pt]["LP"])
    r = Ref(S, init, raw)
    r.boot()
    out["boot"] = r.dump()
    r.game(K, lp("knight"))
    out["knight"] = r.dump()
    r.game(W, lp("k->w"))
    out["k->w"] = r.dump()
    r = Ref(S, init, raw)
    r.boot()
    r.game(W, lp("wizard"))
    out["wizard"] = r.dump()
    r.game(W, lp("stale"))
    out["stale"] = r.dump()
    if lv:
        r = Ref(S, init, raw)
        r.boot()
        r.game(K, bytes(lv["D1"]["LP"]))
        out["D1"] = r.dump()
        for d in range(2, 9):
            if f"D{d}" in lv:
                r.level(bytes(lv[f"D{d}"]["LP"]))
                out[f"D{d}"] = r.dump()
        if "M-D1" in lv:                               # MEM-PS2: the Mage's walk
            r = Ref(S, init, raw)
            r.boot()
            r.game(W, bytes(lv["M-D1"]["LP"]))
            out["M-D1"] = r.dump()
            for d in range(2, 9):
                if f"M-D{d}" in lv:
                    r.level(bytes(lv[f"M-D{d}"]["LP"]))
                    out[f"M-D{d}"] = r.dump()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", help="source root of another checkout to compare too")
    ap.add_argument("--no-src6", action="store_true",
                    help="skip the SRC6 E2E variant (wizard sources in bank 6)")
    ap.add_argument("--no-levels", action="store_true",
                    help="skip the 3F-T1 D1..D8 level-pool walk")
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="zx0pool_")
    kit = ["DEBUG_KIT=0"]          # D3-7: suites run on the release start kit
    kit += os.environ.get("ZX0POOL_DEFS", "").split()   # e.g. "PHASE_SHIFT=1"
    variants = [("zx0", REPO, kit + ["POOL_LVL_VERBOSE=1"], None)]   # (+ DISPLAYs only)
    if not a.no_src6:
        # SRC6 spike E2E: the WIZARD's real blocks moved to the bank-6 SRC6
        # region (2,055 B packed: 9 pages with the Spider stand-in; pool slack
        # 169) — the boot select idle and every wizard game read their
        # sources from bank 6 while the pool is written to banks 4 / 6
        # 3F-T2: R6 grew 8 pages, so 9 SRC6 pages leave POOL_CAP below the
        # PROTO rooms' need: this variant never enters PROTO (POOL_PROTO_CHECK=0)
        # 3F-T13: the 3F-A1 blocks live in SRC6 by default (10 pages); the variant adds the
        # Wizard's 4 blocks (2,055 B) -> 18 pages: POOL_CAP is then below the D7 Warrior need
        # too, so the variant also skips the level-need ASSERT (POOL_LVL_CHECK=0: it never
        # descends; its D1 sessions fit)
        sys.path.insert(0, REPO_TOOLS)
        import zx0_sources as zs
        # 3F-T7: R6_GROW 8->10 leaves at most 19 SRC6 pages (SRC6 at $C800, the lowest the defs.asm
        # ASSERT allows); the default set (3,231 B) + the Wizard's 2,055 B needs 21, so the variant
        # keeps the Dark Knight's block (486 B) in banks 1 / 3 (S6 still checks every block in SRC6)
        # 3F-T8: R6_GROW 10->13 leaves at most 16 SRC6 pages: the Ogre's and the Mummy's blocks stay in
        # banks 1 / 3 too (3,721 of 4,096 B)
        # ANIM-IMPORT2: + the Vampire's own blocks (675 B) stay in banks 1 / 3 as well
        # MEM-RECLAIM w4: R6_GROW 13 -> 14 leaves at most 15 SRC6 pages (SRC6 at $C800); the set is
        # 3,644 of 3,840 B
        # 3F-T11b: R6_GROW 14 -> 15 leaves at most 14 SRC6 pages (SRC6 at $C800, 3,584 B): the set is the
        # Spider, Necro, Ogre, the climb pair + the Wizard (1,908 B packed); the Vampire, Orc and Death
        # Knight (1,900 B) go to banks 1 / 3 (8 B less than the Wizard there: bank 1 has ~no slack)
        s6 = ",".join(sorted((zs.SRC6_KINDS - {"K_DKNIGHT", "K_ORC", "K_MUMMY", "K_VAMPIRE"}) | {"K_WIZARD"}))
        variants.append(("src6", REPO, kit + ["SRC6_PAGES=14", "POOL_PROTO_CHECK=0", "POOL_LVL_CHECK=0"],
                         {"SRC6_KINDS": s6}))
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
        sims = {}
        if name == "zx0" and not os.environ.get("ZX0POOL_DEFS"):
            # 3F-D7LEV: the build's per-level pool need (main.asm POOL_LVL_VERBOSE), both heroes
            got = {}
            for d in disp:
                m = re.search(r"level pool D(\d) hero (\d): .*, (\d+) B; need (\d+) of \d+ "
                              r"\(sim top idx (\d+) ptr (\d+)", d)
                if m:
                    got[(int(m.group(2)), int(m.group(1)))] = int(m.group(4))
                    sims[(int(m.group(2)), int(m.group(1)))] = (int(m.group(5)), int(m.group(6)))
                m = re.search(r"pool sim PROTO kinds (\d) hero (\d): top idx (\d+) ptr (\d+)", d)
                if m:
                    sims[(int(m.group(2)), "P" + m.group(1))] = (int(m.group(3)), int(m.group(4)))
            for (hero, dep), want in sorted(LEVEL_NEED.items()):
                ok = got.get((hero, dep)) == want
                print(f"[{'PASS' if ok else 'FAIL'}] {name} level need D{dep} "
                      f"{('Warrior', 'Mage')[hero]}: {got.get((hero, dep))} == {want}")
                if not ok:
                    fails.append(f"{name}/need/D{dep}h{hero}")
        for d in disp:
            if "sprite sources" in d or "ZX0" in d or "low-RAM" in d or "SRC6" in d:
                print(f"[{name}]   {d}")
        h = Harness()
        h.launch(EMU_ARGS)
        try:
            h.z.sock.settimeout(60)
            r = Run(h, sna, S)
            out, tm = scenario_run(r)
            lv = None
            if name == "zx0" and not a.no_levels:
                lv, tl = levels_run(r, 8)
                lvm, tlm = levels_run(r, 8, "2", "M-")     # MEM-PS2: the Mage's walk too
                for hero, pre in ((0, ""), (1, "M-")):
                    for d in range(1, 9):
                        dd = (lv if not hero else lvm)[f"{pre}D{d}"]
                        ok = dd["depth"] == d
                        print(f"[{'PASS' if ok else 'FAIL'}] {name} levels {pre}: LVL_DEPTH == {d}")
                        if not ok:
                            fails.append(f"{name}/levels/{pre}D{d}-depth")
                        if not os.environ.get("ZX0POOL_DEFS"):
                            sim_check(name, f"{('Warrior', 'Mage')[hero]} D{d}", S, dd["alloc"],
                                      sims.get((hero, d), (-1, -1)), fails)
                lv.update(lvm)
                tl.update(tlm)
                tm.update(tl)
                if not os.environ.get("ZX0POOL_DEFS"):
                    for (hero, kinds), pd in sorted(proto_run(r).items()):
                        what = f"{('Warrior', 'Mage')[hero]} PROTO {kinds} kinds"
                        sim_check(name, what, S, pd["alloc"], sims.get((hero, f"P{kinds}"), (-1, -1)), fails)
                        for k in ("GEN_OVERFLOW", "GEN_TRAP"):
                            if pd[k]:
                                fails.append(f"{name}/{what} {k}={pd[k]}")
                worst = max(v for k, v in tl.items())
                ok = worst <= 2 * 3546900
                print(f"[{'PASS' if ok else 'FAIL'}] {name} levels: worst level_enter {worst:,} T "
                      f"({worst / 3546900:.2f} s) <= 2 s")
                if not ok:
                    fails.append(f"{name}/levels/time")
            res[name] = (out, tm, S, r.init, lv)
            if "SRC6_ADDR" in S and name != "baseline":
                src6_decode(r, fails, name)
        finally:
            h.close()
        for pt, d in list(out.items()) + list((lv or {}).items()):
            for k in ("GEN_OVERFLOW", "GEN_TRAP"):
                if d[k]:
                    fails.append(f"{name}/{pt} {k}={d[k]}")
        print(f"[{name}] timings: " + ", ".join(f"{k} {v:,} T" for k, v in tm.items()))

    for name in res:
        out, tm, S, init, lv = res[name]
        ref = reference(S, init, out, lv)
        if lv:
            out = dict(out, **lv)
            # the pool top at every depth vs the build's bound: MEM-PS2 POOL_NEED = the
            # worst simulated top + POOL_SIM_MARGIN (bank 0 starts at POOL_START; a
            # skipped bank tail counts as used); the exact match is sim_check above
            for pt in lv:
                a = lv[pt]["alloc"]
                idx, ptr = a[0], a[1] | a[2] << 8
                used = linear_top(S, idx, ptr)
                ok = used + S["POOL_SIM_MARGIN"] <= S["POOL_NEED"] and idx <= 2
                print(f"[{'PASS' if ok else 'FAIL'}] {name} {pt} pool top: bank idx {idx}, "
                      f"{used:,} B used of POOL_NEED {S['POOL_NEED']:,} (POOL_CAP {S['POOL_CAP']:,})")
                if not ok:
                    fails.append(f"{name}/{pt}/pool-top")
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
