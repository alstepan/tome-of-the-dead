#!/usr/bin/env python3
"""Stage 3D combat suite (ZRCP, tick-exact; tests/game_lib.py driver).

C1 (D3-5) — the FX engine (src/fx.asm): render-only projectile / impact
tracks. Abilities arrive in D3-7, so the scenarios queue descriptors
directly: fx_call() runs `fx_start` (HL = a descriptor poked into MSG_BUF)
through ZRCP from the wait_tick probe (return address pushed, PC set, run
back to the probe) — the debug entry costs no game bytes.

Every scenario checks, per tick, against an independent Python model of the
track (positions from the descriptor + the art's own w / ay / ATTR_SPRITE in
assets/gfx/sprites/<frame>.asm, not from fx_meta / frame_tab):
  * the desired state (FX_FID, FX_ATTR, FX_LEFT, footprint FX_COL..FX_ROWS) = model[k],
  * the drawn state (FX_DFID ..) = model[k-1] (render runs first in a tick),
  * the composed screen's attrs over the drawn footprint = the frame's attr,
  * displayed == composed at every probe_presented (A7: FX never stale),
then: FX_BUSY 0, the playfield back to its pre-FX bytes on both screens,
BLIT_MISS / CLIP_TRAP / DMG_OVERFLOW 0.

Usage: python3 tests/combat.py [C1 ...]     (exit 1 on any failure)
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import zx0_pack as zp  # noqa: E402  (sprite_asm: the 40-px override)
ONLY = [a for a in sys.argv[1:] if not a.startswith("-")]
sys.argv = [sys.argv[0]] + ["999"]           # keep game.py's item filter inert
import game  # noqa: E402
from game_lib import (Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, EF_ACTIVE, EF_HOSTILE,  # noqa: E402
                      RUN_LIMIT, attr_at, cell_bytes, stand_y)

REPO = os.path.dirname(HERE)
NONE = 0xFF
FXS = dict(IDLE=0, WAIT=1, FLY=2, IMP=3)
TRACKS = [S["FXT0"], S["FXT1"], S["FXT2"]]
F = {k: S[k] for k in ("FXD_COL", "FX_ST", "FX_FID", "FX_DFID", "FX_DCOL")}
PLAY_ROWS = 18


def art(name):
    """(w, h, ay, attr) of a frame from its sprite sheet .asm (the art, not the engine)."""
    src = open(zp.sprite_asm(name)).read()   # ANIM-IMPORT2: the 40-px override (sprites40/index40.asm)
    g = lambda k: int(re.search(rf"^{name}_{k}\s+EQU\s+(\d+)", src, re.M).group(1))  # noqa: E731
    attr = int(re.search(r"ATTR_SPRITE=\$([0-9A-F]{2})", src).group(1), 16)
    return g("w"), g("h"), g("ay"), attr


FIDNAME = {v: k[4:] for k, v in S.items() if k.startswith("FID_") and v < 0x100}


def desc(fa, fb, ia, ib, col, row, left=False, fast=False, delay=0, impt=0, segs=(0,), attr=0):
    fid = lambda n: NONE if n is None else S["FID_" + n]  # noqa: E731
    segs = list(segs)
    return dict(b=[fid(fa), fid(fb), fid(ia), fid(ib), attr, col, row,
                   (1 if left else 0) | (2 if fast else 0), delay, impt, len(segs)]
                + segs + [0] * (5 - len(segs)))


def model(d):
    """Desired state per fx_tick #k: None (hidden) or (fid, attr, left, col, row, cols, rows)."""
    b = d["b"]
    col, left, fast, delay, impt = b[5], b[7] & 1, b[7] & 2, b[8], b[9]
    segs = b[11:11 + b[10]]
    out, ph = [], 0

    def frame(fid):
        if fid == NONE:
            return None
        w, h, ay, at = art(FIDNAME[fid])
        fpx = col * 8 - ((w - 8) if left else 0)
        fpy = b[6] * 8 - ay
        if fpx < 0 or fpx // 8 + w // 8 > 32 or fpy < 0 or fpy + h > PLAY_ROWS * 8:
            return None
        return (fid, b[4] or at, left, fpx // 8, fpy // 8, w // 8, h // 8)

    def step():
        nonlocal col, left
        while segs[0] == 0:
            if len(segs) == 1:
                return False
            segs.pop(0)
            left ^= 1
        segs[0] -= 1
        col += -1 if left else 1
        return True

    for _ in range(delay):
        out.append(None)
    out.append(frame(b[0]))
    ph = 1
    while True:
        if not step():
            break
        if fast:
            step()
        out.append(frame(b[1] if ph & 1 else b[0]))
        ph += 1
    if b[2] != NONE and impt:
        for i in range(impt):
            out.append(frame(b[3] if i & 1 else b[2]))
    out.append(None)                                   # idle
    return out


class C(game.T):
    fails = []

    def check(self, tag, got, want):
        if got != want:
            C.fails.append(f"{tag}: got {got} want {want}")
            print(f"  [FAIL] {tag}: got {got} want {want}", flush=True)
            return False
        return True

    def fx_call(self, d):
        """fx_start(HL = d) from the wait_tick probe. Returns (accepted, A)."""
        z = self.z
        regs = z.cmd("get-registers")
        pc = int(regs[3:7], 16)
        sp = int(re.search(r"SP=([0-9a-f]{4})", regs).group(1), 16)
        assert pc == S["wait_tick"], hex(pc)
        z.cmd("write-memory %d %s" % (S["MSG_BUF"], " ".join(str(x) for x in d["b"])))
        sp -= 2
        z.cmd("write-memory %d %d %d" % (sp, pc & 0xFF, pc >> 8))
        z.cmd("set-register SP=%d" % sp)
        z.cmd("set-register HL=%d" % S["MSG_BUF"])
        z.cmd("set-register PC=%d" % S["fx_start"])
        z.cmd("run %d" % RUN_LIMIT)
        regs = z.cmd("get-registers")
        assert int(regs[3:7], 16) == pc, regs[:20]
        af = int(re.search(r"AF=([0-9a-f]{4})", regs).group(1), 16)
        return bool(af & 1), af >> 8

    def trk(self, i):
        return self.z.read_memory(TRACKS[i], 32)

    def playfield(self, fr):
        return [(bytes(cell_bytes(fr, c, r)), attr_at(fr, c, r)) for r in range(PLAY_ROWS) for c in range(32)]

    def run_tracks(self, tag, descs, max_ticks=80):
        """Start descs (one per track, in order, all at once) and follow them."""
        base5 = self.playfield(self.composed_frame())
        models = []
        for i, d in enumerate(descs):
            ok, a = self.fx_call(d)
            m = model(d)
            self.check(f"{tag} start {i} accepted", ok, True)
            land = next(k for k in range(len(m)) if m[k] and m[k][0] in (d["b"][2], d["b"][3])
                        and k > d["b"][8]) if d["b"][2] != NONE and d["b"][9] else len(m) - 1
            self.check(f"{tag} start {i} impact tick", a, land)
            models.append(m)
        self.present_watch(True)
        k = 0
        while k < max_ticks:
            self.tick()
            fr = self.composed_frame()
            for i, m in enumerate(models):
                t = self.trk(i)
                want = m[k] if k < len(m) else None
                got = None if t[F["FX_FID"]] == NONE else tuple(t[F["FX_FID"]:F["FX_FID"] + 7])
                self.check(f"{tag} t{i} tick {k} desired", got, want)
                wd = m[k - 1] if 0 < k <= len(m) else None
                gd = None if t[F["FX_DFID"]] == NONE else tuple(t[F["FX_DFID"]:F["FX_DFID"] + 7])
                self.check(f"{tag} t{i} tick {k} drawn", gd, wd)
                if gd:
                    c0, r0, nc, nr = gd[3:]
                    bad = [(c, r) for r in range(r0, r0 + nr) for c in range(c0, c0 + nc)
                           if attr_at(fr, c, r) != gd[1]]
                    self.check(f"{tag} t{i} tick {k} attrs", bad, [])
            k += 1
            if self.rb("FX_BUSY") == 0 and k > max(len(m) for m in models):
                break
        self.tick()                                    # present the last erase
        self.present_watch(False)
        self.check(f"{tag} FX_BUSY", self.rb("FX_BUSY"), 0)
        # busy until the render after the last idle model entry has erased it
        self.check(f"{tag} ticks", k, max(len(m) for m in models) + 1)
        self.check(f"{tag} displayed==composed each tick", [s for s in self.present_samples if s], [])
        self.check(f"{tag} playfield restored (composed)", self.playfield(self.composed_frame()) == base5, True)
        self.check(f"{tag} playfield restored (displayed)", self.playfield(self.frame()) == base5, True)
        for n in ("BLIT_MISS", "CLIP_TRAP", "DMG_OVERFLOW"):
            self.check(f"{tag} {n}", self.rb(n), 0)


ROW = stand_y(1, 6) + 2                                # the hero's flight row (top + 2)


def c1(h):
    print("== C1 FX engine (D3-5)", flush=True)
    p = C(h)
    p.boot(K_WIZARD)
    p.isolate()
    p.place(0, 2, stand_y(1, 6))
    p.settle(3)
    # straight flight (8x8, 8 px/tick, delay 2 = the CAST2 tick) + 2-frame impact
    p.run_tracks("straight", [desc("spark_fly1", "spark_fly2", "spark_fizz1", "spark_fizz2",
                                   6, ROW, delay=2, impt=3, segs=(7,))])
    # bounce chain: left, 3 segments (2 reversals), single-frame impact
    p.run_tracks("bounce", [desc("frost_fly", "frost_fly", "frost_crack", "frost_crack",
                                 20, ROW, left=True, impt=2, segs=(5, 12, 3))])
    # 16 px/tick bolt, odd segment (mid-tick reversal), 16x16 impact (ay 8)
    p.run_tracks("bolt16", [desc("lightning_fly1", "lightning_fly2", "lightning_flash", "lightning_flash",
                                 6, ROW, fast=True, impt=2, segs=(9, 4))])
    # left-facing 16-wide frames, alternating attrs ($46 / $42), 16x16 burst
    p.run_tracks("burst-left", [desc("firebolt_fly1", "firebolt_fly2", "firebolt_burst1", "firebolt_burst2",
                                     26, ROW, left=True, impt=3, segs=(8,))])
    # through a body (goblin repaired under the FX) + an attr override (Death Bolt style)
    p.place(3, 16, stand_y(1, 4), room=0, flags=EF_ACTIVE | EF_HOSTILE)
    p.settle(3)
    p.run_tracks("through-body", [desc("drain_fly1", "drain_fly2", "drain_hit", "drain_hit",
                                       8, ROW, impt=2, segs=(12,), attr=0x45)])
    # three tracks at once (cap) + 16x16 impacts at the edges of the band
    p.run_tracks("three", [
        desc("lightning_fly1", "lightning_fly2", "lightning_flash", "lightning_flash", 6, ROW, fast=True,
             impt=2, segs=(14, 6)),
        desc(None, None, "lightning_flash", "lightning_flash", 16, ROW, delay=1, impt=4, segs=(0,)),
        desc("spark_fly1", "spark_fly2", "spark_fizz1", "spark_fizz2", 25, ROW - 3, left=True,
             impt=2, segs=(6,))])
    p.set_ent(3, ROOM=0xFF)
    p.settle(3)
    # queue: 3 started, 2 queued (A = $FF), the 6th dropped (CF 0); the queued
    # ones run once tracks free (checked: everything ends idle and restored)
    base = p.playfield(p.composed_frame())
    d = desc("spark_fly1", "spark_fly2", None, None, 6, ROW, segs=(3,))
    res = [p.fx_call(d) for _ in range(6)]
    p.check("queue results", [(ok, a if not ok else (a if a == NONE else 0)) for ok, a in res],
            [(True, 0)] * 3 + [(True, NONE)] * 2 + [(False, res[5][1])])
    p.check("queue FXQ_N", p.rb("FXQ_N"), 2)
    seen = 0
    for _ in range(40):
        p.tick()
        seen = max(seen, p.rb("FXQ_N") == 0 and p.rb("FX_BUSY") != 0)
        if p.rb("FX_BUSY") == 0:
            break
    p.tick()
    p.check("queue drained + idle", (p.rb("FXQ_N"), p.rb("FX_BUSY"), seen), (0, 0, True))
    p.check("queue playfield restored", p.playfield(p.composed_frame()) == base, True)
    # turn_done waits for the FX: a WAIT turn with a 10-tick flight started in it
    t0 = p.rw("TURN_COUNTER")
    keys, _ = p._prep(("WAIT",))
    p.hold(*keys)
    for _ in range(6):
        p.tick()
        if p.rb("TURN_PHASE") == 1:
            break
    p.release()
    p.check("turn started", p.rb("TURN_PHASE"), 1)
    p.fx_call(desc("spark_fly1", "spark_fly2", "spark_fizz1", "spark_fizz2", 6, ROW, segs=(8,), impt=2))
    n = 0
    while p.rb("TURN_PHASE") == 1 and n < 60:
        p.tick()
        n += 1
    p.check("turn held until FX idle", (p.rb("FX_BUSY"), n >= 12, p.rw("TURN_COUNTER") == t0 + 1),
            (0, True, True))

    # Warrior: U_FXW frames, both facings, no-impact dagger
    p = C(h)
    p.boot(K_KNIGHT)
    p.isolate()
    p.place(0, 2, stand_y(1, 6))
    p.settle(3)
    p.run_tracks("warrior", [
        desc("arrow_fly1", "arrow_fly2", "arrow_hit", "arrow_hit", 28, ROW, left=True, impt=2, segs=(15,)),
        desc("dagger_spin1", "dagger_spin2", None, None, 6, ROW + 1, delay=1, segs=(10,), attr=0)])  # the hero's throw: fx_meta's own (THROW_ATTR)


TESTS = {"C1": c1}


def main():
    with Harness() as h:
        h.launch(EMU_ARGS)
        for name, fn in TESTS.items():
            if not ONLY or name in ONLY:
                fn(h)
    n = len(C.fails)
    print(f"[{'FAIL' if n else 'PASS'}] combat: {n} failures" + (f" (first: {C.fails[0]})" if n else ""))
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
