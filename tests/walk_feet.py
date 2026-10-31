"""ANIM-IMPORT2: planted-foot check of the 40-px walk cycles (static, no emulator).

A walker steps 4 px per tick and shows the next MOVECYC slot each tick (docs/conventions.md
"Walk cycles"), so a foot that stays planted on the floor must move 4 px BACK inside the
frame from one slot to the next. For every consecutive slot pair (cyclic) of the listed
move cycles (src/seq_img.asm, read as text) this checks, from the frame pixels the build
packs (tools/zx0_pack.py game_frames / sprite_asm: the 40-px override), that
  * at least MIN_CONTACT ink pixels of the sole row (the frame's bottom row: frames are
    bottom-anchored) of slot n+1, put 4 px further on, land on sole ink pixels of slot n
    (a planted foot, not a 1-px graze), and
  * the sole row is not empty (the frame stands on the floor).
Sole = the frame's bottom row for every cycle except the Vampire (SOLE_ROWS): its boots slope, so an
exactly-planted foot shows only 2 px in the bottom row; vp_move uses the bottom 3 rows projected.
Right-facing art (the left facing is the mirror: the same relation). Exit 1 on a failure.
Usage: python3 tests/walk_feet.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import zx0_pack as zp  # noqa: E402
import zx0_sources as zs  # noqa: E402

# move cycles of the 40-px walkers (seq_img.asm labels)
CYCLES = ["kn_move", "wz_move", "sk_move", "ar_move", "or_move", "ne_move", "mu_move", "vp_move", "og_move"]
STEP = 4
MIN_CONTACT = 3            # px of sole that must stay on the same screen x (a 1-px touch is a slide)
# known art debt, reported but not failing (remove the entry when the art is fixed); ANIM-X12:
# the Vampire XFAIL is gone (X2 4th pose), none left
XFAIL = {}

frames = dict(zp.game_frames())


# The Vampire's boots slope (toe 1-2 px, heel/ankle a row or two higher): its sole is the bottom 3 rows
# projected (ANIM-X12 X2: the bottom row alone holds only 2 px of an exactly-planted foot). The other
# cycles have flat soles and keep the strict bottom row.
SOLE_ROWS = {"vp_move": 3}


def sole(name, nrows=1):
    """Set of ink x of the frame's bottom `nrows` rows (data bits; mask/data byte pairs per col)."""
    m = zs.meta(name)
    cols, h = int(m["cols"]), int(m["h"])
    raw = frames[name]
    xs = set()
    for r in range(h - nrows, h):
        row = raw[r * cols * 2:(r + 1) * cols * 2]
        for c in range(cols):
            d = row[2 * c + 1]
            for b in range(8):
                if d & (0x80 >> b):
                    xs.add(c * 8 + b - int(m["ax"]))
    return xs, h


src = open(os.path.join(REPO, "src/seq_img.asm")).read()
fails = 0
for lab in CYCLES:
    mo = re.search(rf"^{lab}:\s+MOVECYC[24]\s+([\w, ]+)", src, re.M)
    if not mo:
        print(f"[FAIL] {lab}: no MOVECYC line")
        fails += 1
        continue
    cyc = [n.strip() for n in mo.group(1).split(",")]
    bad = []
    for i, a in enumerate(cyc):
        b = cyc[(i + 1) % len(cyc)]
        sa, ha = sole(a, SOLE_ROWS.get(lab, 1))
        sb, hb = sole(b, SOLE_ROWS.get(lab, 1))
        if not sa or not sb:
            bad.append(f"{a if not sa else b}: empty sole row")
        elif len({x + STEP for x in sb} & sa) < MIN_CONTACT:
            bad.append(f"{a} -> {b}: planted contact {len({x + STEP for x in sb} & sa)} px < {MIN_CONTACT} "
                       f"(sole {sorted(sa)} vs next+4 {sorted(x + STEP for x in sb)})")
        if ha != hb:
            bad.append(f"{a} / {b}: heights {ha} / {hb}")
    ok = not bad
    xf = not ok and lab in XFAIL
    fails += not ok and not xf
    tag = "PASS" if ok else ("XFAIL" if xf else "FAIL")
    print(f"[{tag}] {lab} {cyc}" + ("" if ok else ": " + "; ".join(bad)) + (f" [{XFAIL[lab]}]" if xf else ""))
    if ok and lab in XFAIL:
        print(f"[XPASS] {lab}: drop its XFAIL entry")
print("walk_feet:", "OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
