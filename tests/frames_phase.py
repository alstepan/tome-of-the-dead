"""Static check of the phase-locked walk shifts (docs/conventions.md "Walk cycles").

No emulator: reads build/wazhack.sym + .sna (any DEBUG_KIT) and src/*.asm.
  * every non-flyer KS_MOVE cycle: 1 tick per entry, even length, even slots
    MOT or FF_PH4 (WK4), odd slots MOT or not FF_PH4 (WK0 / STA);
  * a WK4 frame (FF_PH4, drawn only at px & 4 = 4) is used nowhere else: not in
    any other cycle / sequence / climb-rest of any kind, hero_jump, abl_seq,
    wz_bonk, kind_rest, and not named in src/ outside the frame list and the
    MOVECYC lines; a KS_CLIMB that IS the move cycle (rat / slime) needs MOT
    even slots (drawn cell-aligned at any phase);
  * hero_jump JUMP2 (drawn mid-tween at both parities) is MOT.
With -DPHASE_SHIFT=0 (no FF_PH4 frames) the checks pass trivially.
Usage: python3 tests/frames_phase.py      exit 1 on any violation.
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = {}
for line in open(os.path.join(REPO, "build/wazhack.sym")):
    m = re.match(r"^([A-Za-z_][\w.]*):\s+EQU\s+0x([0-9A-Fa-f]+)", line)
    if m:
        S[m.group(1)] = int(m.group(2), 16)
sna = open(os.path.join(REPO, "build/wazhack.sna"), "rb").read()
RAM = sna[27:27 + 49152]                       # $4000..$FFFF as saved


def b(a):
    assert 0x4000 <= a < 0xC000, hex(a)        # bank 5 / bank 2 only (no paged reads)
    return RAM[a - 0x4000]


def w(a):
    return b(a) | b(a + 1) << 8


def flags(fid):
    return b(S["fdesc_tab"] + fid * S["FDESC_STRIDE"] + S["FD_FLAGS"])


MOT, PH4 = S["FF_MOTION"], S["FF_PH4"]
fails = []
names = {v: k[4:] for k, v in S.items() if k.startswith("FID_") and v < S["FID_COUNT"]}


def cycle(p):
    tot, out, p = b(p), [], p + 1
    while b(p) != 0xFF:
        out.append((b(p), b(p + 1)))
        p += 2
    return tot, out


def seq(p):
    out = []
    while b(p) != 0xFF:
        out.append(b(p))
        p += 3
    return out


uses = []                                       # (fid, where) outside the move cycles
movecyc = {}
for k in range(S["K_COUNT"]):
    base = S["kind_seqs"] + k * S["KS_STRIDE"]
    if w(base) == 0:
        continue                                # the retired Rogue hole
    flyer = b(S["kind_tab"] + S["KT_FLAGS"] + k) & S["KF_FLYER"]
    ptr = {n: w(base + S[n]) for n in ("KS_IDLE", "KS_MOVE", "KS_CLIMB", "KS_CLIMBREST",
                                       "KS_ATTACK", "KS_HURT", "KS_BLOCK", "KS_DEATH")}
    if not flyer:
        tot, ents = cycle(ptr["KS_MOVE"])
        movecyc[k] = ents
        if any(t != 1 for _, t in ents) or tot != len(ents) or tot % 2:
            fails.append(f"kind {k} move cycle {ents} total {tot}: not 1 tick/entry, even length")
        for i, (f, _) in enumerate(ents):
            fl = flags(f)
            if i % 2 == 0 and not fl & (MOT | PH4):
                fails.append(f"kind {k} move slot {i} {names[f]}: even slot, not MOT / WK4")
            if i % 2 == 1 and fl & PH4 and not fl & MOT:
                fails.append(f"kind {k} move slot {i} {names[f]}: odd slot flagged WK4")
    for n in ("KS_IDLE", "KS_CLIMB"):
        if n == "KS_CLIMB" and not flyer and ptr[n] == ptr["KS_MOVE"]:
            for i, (f, _) in enumerate(movecyc[k]):   # climb by coincidence: aligned, any phase
                if i % 2 == 0 and not flags(f) & MOT:
                    fails.append(f"kind {k} KS_CLIMB = move cycle: even slot {names[f]} not MOT")
            continue
        if n == "KS_CLIMB" and ptr[n] in (ptr["KS_IDLE"],):
            continue
        uses += [(f, f"kind {k} {n}") for f, _ in cycle(ptr[n])[1]]
    uses.append((b(ptr["KS_CLIMBREST"]), f"kind {k} KS_CLIMBREST"))
    for n in ("KS_ATTACK", "KS_HURT", "KS_BLOCK", "KS_DEATH"):
        uses += [(f, f"kind {k} {n}") for f in seq(ptr[n])]
    uses.append((b(S["kind_rest"] + k), f"kind {k} kind_rest"))
for h in range(2):
    j1, j2 = b(S["hero_jump"] + 2 * h), b(S["hero_jump"] + 2 * h + 1)
    uses.append((j1, f"hero {h} JUMP1"))
    if not flags(j2) & MOT:
        fails.append(f"hero {h} JUMP2 {names[j2]}: not MOT (drawn at both parities)")
for a in range(S["ABL_COUNT"]):
    uses += [(f, f"abl_seq {a}") for f in seq(w(S["abl_seq"] + a * S["ABS_STRIDE"]))]
uses += [(f, "wz_bonk") for f in seq(S["wz_bonk"])]

wk4 = {f for f in names if flags(f) & PH4 and not flags(f) & MOT}
for f, where in uses:
    if f in wk4:
        fails.append(f"WK4 frame {names[f]} also used at {where} (drawn cell-aligned: needs MOT)")
# source: a WK4 frame named anywhere but the frame list / the MOVECYC lines
pat = re.compile(r"\b(?:FID_)?(" + "|".join(re.escape(names[f]) for f in wk4) + r")\b") if wk4 else None
if pat:
    for fn in sorted(os.listdir(os.path.join(REPO, "src"))):
        if not fn.endswith(".asm") or fn == "frames.asm":
            continue
        for ln, line in enumerate(open(os.path.join(REPO, "src", fn)), 1):
            code = line.split(";")[0]
            if pat.search(code) and "MOVECYC" not in code and "CLIMBCYC" not in code \
                    and "CLIMBREST" not in code and "ROLE" not in code:
                fails.append(f"src/{fn}:{ln}: WK4 frame named outside its move cycle: {code.strip()}")

print(f"[info] PHASE_SHIFT={S.get('PHASE_SHIFT', 0)}; WK4 frames {sorted(names[f] for f in wk4)}; "
      f"move cycles {len(movecyc)}, other uses checked {len(uses)}")
for f in fails:
    print("[FAIL]", f)
print("frames_phase:", "OK" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
