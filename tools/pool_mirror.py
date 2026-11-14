#!/usr/bin/env python3
"""Option C ledger (docs/design/mirror_c_split.md, task C-T1): how many pool bytes
blit-time sprite mirroring would free, per level / hero, by frame class.

Offline: no emulator. Reads
  src/frames.asm       FRM name, kind, bwpx, flags  (the frame list, fid order)
  src/pool6.asm        gu_tab (generation units: fid0, fcnt)
  build .sym           nm_w/_h/_cols/_ax, FID_*, KFID_*, flags, U_FX_BASE ...
  build output         -DPOOL_LVL_VERBOSE=1 "level pool D<d> hero <h>: units mask
                       <lo> / <hi>, N B; ... straddle waste W" (the per-level kinds,
                       as the units set the build's own need uses)
and recomputes what gen_frame allocates per frame (defs.asm FRM / POOLACC):
  MOT   non-SYM: per facing h*2*(2c+1)   (shift 0 + shift 4)     SYM: one copy
  STA   per facing h*2*(c + ((anchor + FF_PH4) & 7 != 0))        SYM: one copy
A level need = hero unit + class FX unit + the two select idles (right + left) + the level's
units; LEVEL_NEED (tests/zx0_pool.py) = that total + straddle waste + POOL_SIM_MARGIN (64).

C-T6: an FF_MIR frame (frames.asm `|MIR`) stores no left: `left` = the stored left bytes, `MIR` = the left
bytes FF_MIR already frees; the class columns and the policies stay relative to an all-pre-mirrored pool.
Classes of a frame's LEFT bytes (a SYM frame has no left; its bytes are the SYM column):
  walk   WK4 / WK0 (PHASE_SHIFT one-shift walk poses)
  mot    MOT (two shifts per facing)
  hurt   a non-walk, non-MOT frame whose name contains "hurt"
  other  every other STA frame
Policies (bytes freed = the left bytes no longer stored):
  (a) full C   : mirror every non-SYM left
  (b) hybrid   : keep walk + MOT + hurt pre-mirrored, mirror the rest
  (c) hybrid+h : keep walk + MOT, mirror hurt too

Usage: python3 tools/pool_mirror.py [--build DIR] [--keep]
  --build DIR: reuse DIR (a tools/build.sh -o DIR output with out.txt, i.e. the build log
               saved as DIR/build.log); default: build into a temp dir.
Exit 1 on an ASSERT / reconciliation failure.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "tests"))
sys.path.insert(0, HERE)

CLASSES = ("walk", "mot", "hurt", "other")
SIM_MARGIN = 64


def build(out):
    r = subprocess.run([os.path.join(REPO, "tools/build.sh"), "-o", out, "-DDEBUG_KIT=0",
                        "-DPOOL_LVL_VERBOSE=1"], cwd=REPO, capture_output=True, text=True)
    log = r.stdout + r.stderr
    open(os.path.join(out, "build.log"), "w").write(log)
    if r.returncode or "Errors: 0, warnings: 0" not in log:
        sys.exit("pool_mirror: build failed:\n" + log[-2000:])
    return log


def load_syms(path):
    S = {}
    for line in open(path):
        m = re.match(r"^([A-Za-z_][\w.]*):\s+EQU\s+0x([0-9A-Fa-f]+)", line)
        if m:
            v = int(m.group(2), 16)
            S[m.group(1)] = v - (1 << 32) if v >= 1 << 31 else v
    return S


def read_frm(S):
    """[(name, kind, bwpx, flag expr text, flags value)] of the frames that exist, fid order."""
    ph = S["PHASE_SHIFT"]
    env = dict(S, STA=0, MOT=S["FF_MOTION"], SYM=S["FF_SYM"], MIR=S.get("FF_MIR", 0),
               WK4=S["FF_PH4"] if ph else S["FF_MOTION"], WK0=0 if ph else S["FF_MOTION"])
    out = []
    for line in open(os.path.join(REPO, "src/frames.asm")):
        m = re.match(r"\s+FRM\s+(\w+)\s*,\s*(\w+)\s*,\s*([^,]+),\s*([^;]+)", line)
        if not m:
            continue
        nm, kind, bw, fl = m.group(1), m.group(2), m.group(3).strip(), m.group(4).strip()
        if S.get("FID_" + nm, -1) < 0:
            continue                                   # FRM_OK = 0 (stand-in rule): no fid
        out.append((nm, kind, eval(bw, {}, env), fl, eval(fl, {}, env)))
    return out


def read_gu(S):
    """[(fid0, fcnt)] = gu_tab rows (unit index order)."""
    txt = open(os.path.join(REPO, "src/pool6.asm")).read()
    body = txt[txt.index("\ngu_tab:"):txt.index("\ngu_tab_end:")]
    rows = []
    for line in body.splitlines():
        m = re.match(r"\s+GU\s+([^,]+),\s*([^;]+)", line)
        if m:
            rows.append((eval(m.group(1).strip(), {}, S), eval(m.group(2).strip(), {}, S)))
    return rows


class Frame:
    __slots__ = ("name", "fid", "cls", "sym", "mir", "right", "left", "wl")


def frame_bytes(S, nm, bwpx, fl, flags, fid, failures):
    w, h, c, ax = (S[f"{nm}_{k}"] for k in ("w", "h", "cols", "ax"))
    # the geometry premises of option C (mirror_c_split.md §1: left shift == right shift)
    for ok, what in ((w % 8 == 0, f"_w={w} %8"), (bwpx % 8 == 0, f"bwpx={bwpx} %8"),
                     (ax in (0, 4, 8), f"ax={ax} not in 0/4/8")):
        if not ok:
            failures.append(f"{nm}: {what}")
    f = Frame()
    f.name, f.fid = nm, fid
    f.sym = bool(flags & S["FF_SYM"])
    ph = flags & S["FF_PH4"]
    axl = w - ax - bwpx
    if flags & S["FF_MOTION"]:
        per = h * 2 * (2 * c + 1)
        f.right = per
    else:
        per = h * 2 * (c + (((ax + ph) & 7) != 0))
        f.right = per
        perl = h * 2 * (c + (((axl + ph) & 7) != 0))
        if per != perl and not f.sym:
            failures.append(f"{nm}: left/right shift parity differs ({per} vs {perl})")
    f.mir = bool(flags & S.get("FF_MIR", 0)) and not f.sym     # C-T6: no stored left (blit-time mirror)
    f.wl = 0 if f.sym else f.right                    # the left bytes a pre-mirrored left would store
    f.left = 0 if f.mir else f.wl                     # ... and what the pool stores now
    toks = set(re.findall(r"\w+", fl))
    if toks & {"WK4", "WK0"} and S["PHASE_SHIFT"]:
        f.cls = "walk"
    elif flags & S["FF_MOTION"]:
        f.cls = "mot"
    elif "hurt" in nm:
        f.cls = "hurt"
    else:
        f.cls = "other"
    return f


def ledger(frames_in_level):
    """-> dict of totals: right, left, sym, left_by_class, freed per policy."""
    t = {"right": 0, "left": 0, "sym": 0, "mir": 0, "cls": dict.fromkeys(CLASSES, 0)}
    for f in frames_in_level:
        if f.sym:
            t["sym"] += f.right
        else:
            t["right"] += f.right
            t["left"] += f.left                       # stored
            t["mir"] += f.wl - f.left                 # C-T6: freed already by FF_MIR frames
            t["cls"][f.cls] += f.wl                   # policies: vs an all-pre-mirrored pool
    c = t["cls"]
    t["a"] = t["left"]
    t["b"] = c["other"]
    t["c"] = c["other"] + c["hurt"]
    t["total"] = t["right"] + t["left"] + t["sym"]
    return t


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", help="existing build dir (with build.log + build/*.sym)")
    a = ap.parse_args()
    if a.build:
        out = a.build
        log = open(os.path.join(out, "build.log")).read()
    else:
        out = tempfile.mkdtemp(prefix="poolmirror_")
        log = build(out)
    S = load_syms(os.path.join(out, "build/tome-of-the-dead.sym"))
    import zx0_pool
    need = zx0_pool.LEVEL_NEED

    failures = []
    frm = read_frm(S)
    byfid = {}
    for nm, kind, bw, fl, flags in frm:
        byfid[S["FID_" + nm]] = frame_bytes(S, nm, bw, fl, flags, S["FID_" + nm], failures)
    gu = read_gu(S)
    kfx = S["U_FX_BASE"]

    rows = {}
    for line in log.splitlines():
        m = re.search(r"level pool D(\d) hero (\d): units mask 0x([0-9A-Fa-f]+) / 0x([0-9A-Fa-f]+), "
                      r"(\d+) B; need (\d+) of (\d+) .*straddle waste (-?\d+)", line)
        if m:
            d, hero = int(m.group(1)), int(m.group(2))
            rows[(hero, d)] = (int(m.group(3), 16) | int(m.group(4), 16) << 32, int(m.group(5)),
                               int(m.group(6)), int(m.group(8)), int(m.group(7)))
    if len(rows) != 16:
        sys.exit(f"pool_mirror: {len(rows)} level rows in the build log (want 16; -DPOOL_LVL_VERBOSE=1)")

    def unit_frames(u):
        f0, n = gu[u]
        return [byfid[f] for f in range(f0, f0 + n)]

    idles = [byfid[S["FID_knight_idle1"]], byfid[S["FID_wizard_idle"]]]
    names = ("Warrior", "Mage")
    print("bytes: right / left / SYM = one copy;  left by class: walk mot hurt other;  "
          "freed: (a) full C  (b) hybrid  (c) hybrid+hurt\n")
    hdr = (f"{'lvl':8}{'total':>8}{'right':>8}{'left':>8}{'SYM':>7} |{'walk':>7}{'mot':>7}{'hurt':>7}"
           f"{'other':>7} |{'(a)':>8}{'(b)':>8}{'(c)':>8} |{'need':>7}{'diff':>6}{'MIR':>6}")
    print(hdr)
    worst = {}
    for hero in (0, 1):
        for d in range(1, 9):
            mask, pln, nd, straddle, cap = rows[(hero, d)]
            fl = list(idles) + unit_frames(hero) + unit_frames(hero + kfx)
            for u in range(len(gu)):
                if mask >> u & 1:
                    fl += unit_frames(u)
            t = ledger(fl)
            # reconciliation: total + straddle + SIM_MARGIN == LEVEL_NEED == the build's need
            diff = need[(hero, d)] - t["total"] - straddle - SIM_MARGIN
            if nd != need[(hero, d)] or not (0 <= diff <= straddle + SIM_MARGIN) or diff:
                failures.append(f"D{d} {names[hero]}: total {t['total']} + straddle {straddle} + {SIM_MARGIN} "
                                f"!= need {need[(hero, d)]} (build {nd}, diff {diff})")
            c = t["cls"]
            print(f"{names[hero][0]}-D{d:<5}{t['total']:>8}{t['right']:>8}{t['left']:>8}{t['sym']:>7} |"
                  f"{c['walk']:>7}{c['mot']:>7}{c['hurt']:>7}{c['other']:>7} |"
                  f"{t['a']:>8}{t['b']:>8}{t['c']:>8} |{need[(hero, d)]:>7}{diff:>6}{t['mir']:>6}")
            worst[(hero, d)] = (nd, cap, t, straddle)
        print()
    (hero, d), (nd, cap, t, st) = max(worst.items(), key=lambda kv: kv[1][0])
    print(f"binding level: D{d} {names[hero]}: need {nd:,} of POOL_CAP {cap:,} (slack {cap - nd:,}); "
          f"freed (a) {t['a']:,}  (b) {t['b']:,}  (c) {t['c']:,}; SYM {t['sym']:,}; straddle {st}")
    for lo, hi in ((1, 3), (4, 6), (7, 8)):
        for hero in (0, 1):
            ks = [worst[(hero, d)][2] for d in range(lo, hi + 1)]
            print(f"  D{lo}-{hi} {names[hero]:8} freed min/max  (a) {min(k['a'] for k in ks):,}/"
                  f"{max(k['a'] for k in ks):,}  (b) {min(k['b'] for k in ks):,}/{max(k['b'] for k in ks):,}"
                  f"  (c) {min(k['c'] for k in ks):,}/{max(k['c'] for k in ks):,}")
    print(f"frames {len(byfid)}, ASSERTs (_w%8, bwpx%8, ax in 0/4/8, left/right shift parity): "
          f"{'FAIL' if failures else 'ok'}")
    for f in failures:
        print("  FAIL " + f)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
