#!/usr/bin/env python3
"""gen_art13c_nun.py — ART13c (user 2026-10-30): the nun Archmage FINAL look = option D
(side 2-pose shuffle) with a SIDE-VIEW cast: no frontal frame at all. Every frame is a
profile facing right; the left facing is the mirror (generated at level entry).
Concept / final art for review: NOT imported, not in index*.asm / frames.asm / SRC6.

Frames (24 x 40, bottom-anchored, ax 0, body 24):
  nun_walk1  WK0  rest pose, shoes together-ish (odd slot of MOVECYC2 walk2, walk1)
  nun_walk2  WK4  stride; the planted shoe steps back exactly 4 px per tick, head fixed
  nun_cast   STA  side cast: head tilted up 1 px at the face (top row fixed), both arms
                  raised toward the hero, cross lifted above the hands, rosary dangling,
                  eyes flare to a 3-px cross; stands on the WALK1 shoes
  nun_hurt   STA  head snapped 1 px back, scream, glow snuffed, arms flung, on WALK1 shoes
  (RAISE telegraph: not drawn — it costs a 5th fid and 480 B; the body ink already
   telegraphs the next spell.)
Profile head (stronger than ART13b): solid coif brim over a 1-row hood shadow, brow
ridge, 3x3 hollow socket with a 1-px glow, hooked nose, cheek hollow, open mouth with a
tooth, jaw and a shadow under the chin; veil hatched down the back.
Checks (exit 1): 40 rows, W % 8 == 0, gfx_convert clash + data / mask round-trip in
every ink shown, head top constant, walk planted-shoe slip 0, no frontal frame.
Writes assets/gfx/concept/art13/: grid/nun_*.grid, anim/c_*.gif, art13c_nun.svg.html
(board F3p), art13c_nun.png, costs_c.txt.  Usage: python3 tools/gen_art13c_nun.py
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_3f_art as G3  # noqa: E402
import gen_art13_nun as N  # noqa: E402
import gen_art2_options as A  # noqa: E402
import svg_sprites as S  # noqa: E402
import zx0_pack as zp  # noqa: E402

H, FLOOR, OX = N.H, N.FLOOR, 4
OUT, GRID_OUT, ANIM, REF = N.OUT, N.GRID_OUT, N.ANIM, N.REF
INKS = sorted({k for _, k in N.TIER + N.TELE})
SLACK = 3194
SHOW = (("$04 ARCHMAGE", "#00D700"), ("$42 FIRE", "#FF3030"), ("$45 FROST", "#00FFFF"))

PHEAD = [                                           # 16 cols, facing right
    "...vvvvvvvv.....",
    "..vVVVVVVVVvv...",
    ".vVVVVVVVVVVVv..",
    ".vVVVVVVVVVVVVv.",
    "vVVVVVVWWWWWWWWv",
    "vVVVVVWWWWWWWWWW",
    "vVVVVVWWoooooooo",
    "vVVVVVWWo******.",
    "vVVVVVWWo**ooo*.",
    "vVVVVVWWo**o*o**",
    "vVVVVVWWo**ooo**",
    "vVVVVVWWo*******",
    "vVVVVVWWo*o****.",
    "vVVVVVWWo*o**oo.",
    "vVVVVVWWo***o*..",
    "vVVVVVWWWo****..",
    "vVVVVVWWWWoooo..",
    "vVVVVVWWWWWWW...",
    "vVVVVVWWWWWWWWv.",
    "vVVVVVVWWWWWWWv.",
]
SCREAM = {13: "vVVVVVWWo*oooo..", 14: "vVVVVVWWo**ooo..", 15: "vVVVVVWWWo***..."}
GLOW = (12, 9)


def phatch(x):
    return x % 2 == 0


def phead(scream=False, hollow=False, flare=False, tilt=False):
    rows = list(PHEAD)
    if scream:
        for k, v in SCREAM.items():
            rows[k] = v
    b, _ = N.region(rows, w=16, hatch=phatch)
    b = b[:, :16]
    gx, gy = GLOW
    if hollow:
        b[gy, gx] = False
    if flare:
        N.px(b, [(gx, gy - 1), (gx - 1, gy), (gx + 1, gy), (gx, gy + 1)])
    if tilt:                                        # face tipped up: the face (cols >= 9,
        t = b.copy()                                # rows 7..16) rises 1 row into the hood
        t[6:16, 9:] = b[7:17, 9:]                   # shadow; coif brim and bib stay
        b = t
    return b


FEET = {"WALK1": (10, 14), "WALK2": (6, 14)}        # shoe ankle x (2-pose shuffle)


def nun(pose):
    walk = pose in FEET
    cast, hurt = pose == "CAST", pose == "HURT"
    w = 24
    b = np.zeros((H, w), bool)
    feet = FEET[pose if walk else "WALK1"]
    for y in range(19, 38):                         # habit: hem reaches back over the stride
        t = (y - 19) / 18
        back = min(feet) - 4
        l = max(int(round(OX - (OX - max(back, 1)) * t)) - (1 if hurt and y > 30 else 0), 0)
        r = min(int(round(OX + 15 + 2 * t)), w - 1)
        for x in range(l, r + 1):
            b[y, x] = phatch(x) or x in (l, r) or y in (19, 37)
    for x in range(w):                              # ragged hem
        if b[37, x] and x % 3 == 0:
            b[37, x] = False
    for x in feet:                                  # shoes
        m = np.zeros_like(b)
        m[FLOOR - 1:FLOOR + 1, x - 1:x + 3] = True
        b[G3.dilate4(m) & ~m] = False
        b |= m
    for y in range(20, 30):                         # veil down the back
        for x in range(OX - 1, OX + 2):
            b[y, x] = phatch(x) or x == OX - 1
    hd = phead(scream=hurt, hollow=hurt, flare=cast, tilt=cast)
    dx = OX - (1 if hurt else 0)
    m = np.zeros_like(b)
    for x in range(16):
        if 0 <= x + dx < w:
            m[:20, x + dx] = hd[:20, x]
    cl = G3.dilate4(m)
    cl[20:] = False
    b &= ~cl
    b |= m
    if cast:                                        # both arms raised toward the hero
        N.line(b, [(OX + 6, 22), (OX + 12, 20), (OX + 16, 14)], 2, sep=True)    # far arm
        N.line(b, [(OX + 8, 23), (OX + 14, 21), (OX + 18, 15)], 2, sep=True)    # near arm
        N.stamp(b, "##\n##", OX + 17, 12, sep=True)                            # pale hands
        N.stamp(b, ".#.\n###\n.#.\n.#.", OX + 17, 6, sep=True)                 # cross lifted
        N.px(b, [(OX + 19, 15), (OX + 19, 17), (OX + 18, 19)])                 # beads dangling
        N.px(b, [(OX + 16, 4), (OX + 19, 3), (OX + 19, 7)])                    # glints
    elif hurt:                                      # arms flung back / out, rosary flying
        N.line(b, [(OX + 10, 21), (OX + 14, 25), (OX + 16, 29)], 2, sep=True)
        N.line(b, [(OX + 6, 21), (OX + 1, 25), (OX - 1, 28)], 2, sep=True)
        N.rosary(b, OX + 14, 27, 1)
    else:                                           # clasped hands, rosary hanging
        hx = OX + 13
        N.line(b, [(OX + 8, 21), (hx, 24)], 1)
        N.stamp(b, "##.\n###\n.##", hx, 21, sep=True)
        N.rosary(b, hx + 2, 25, 0 if pose == "WALK1" else 1)
    return b


FRAMES = (("nun_walk1", "WALK1", "WK0"), ("nun_walk2", "WALK2", "WK4"),
          ("nun_cast", "CAST", "STA"), ("nun_hurt", "HURT", "STA"))
CYC = {"WALK": [("nun_walk2", 1), ("nun_walk1", 1)],
       "IDLE": [("nun_walk1", 6), ("nun_walk2", 2)],
       "CAST": [("nun_walk1", 3), ("nun_cast", 4), ("nun_walk1", 3)],
       "HURT": [("nun_walk1", 3), ("nun_hurt", 3), ("nun_walk1", 3)]}
NCYC = {"WALK": [("necro_walk2_v2", 1), ("necro_walk4_v2", 1), ("necro_walk3_v2", 1), ("necro_walk1_v2", 1)],
        "CAST": [("necro_walk1_v2", 3), ("necro_cast_v2", 3), ("necro_walk1_v2", 3)]}


def ticks(fr, cyc, facing, walk, reps=2):
    seq = [n for n, k in cyc for _ in range(k)] * reps
    W = (24 + 4 * len(seq) + 40) if walk else 64
    out = []
    for i, n in enumerate(seq):
        b = fr[n]
        xb = (8 + 4 * i if facing > 0 else W - 32 - 4 * i) if walk else 20
        if facing > 0:
            out.append((b, xb, H + 2 - b.shape[0], xb))
        else:
            out.append((np.fliplr(b), xb - (b.shape[1] - 24), H + 2 - b.shape[0], xb))
    return out, W, H + 2


def main() -> int:
    bad = []
    fr = {n: nun(p) for n, p, _f in FRAMES}
    flags = {n: f for n, _p, f in FRAMES}
    ref = {f"necro_{k}_v2": N.load_grid(os.path.join(REF, f"necro_{k}_v2.grid"))
           for k in ("walk1", "walk2", "walk3", "walk4", "cast")}
    raw = {}
    with tempfile.TemporaryDirectory() as td:
        for n, bm in fr.items():
            if bm.shape[0] != H or bm.shape[1] % 8:
                bad.append(f"{n}: shape {bm.shape}")
            solid = S.make_mask(bm, outline=True)
            g = os.path.join(GRID_OUT, n + ".grid")
            with open(g, "w") as fh:
                fh.write(A.grid_text(n, bm, solid, n.upper(), N.ARCH,
                                     f"ART13c nun Archmage (option D, side cast), {flags[n]}; "
                                     "tools/gen_art13c_nun.py; not imported")
                         .replace("tools/gen_art2_options.py", "tools/gen_art13c_nun.py"))
            for ink in INKS:
                raw[n] = A.pack_check(f"{n}_{ink[1:]}", g, bm, solid, ink, td)
        pk = len(zp.zx0(b"".join(raw[n] for n in fr), os.path.join(td, "zc")))
        pk3 = len(zp.zx0(b"".join(raw[n] for n in fr if n != "nun_hurt"), os.path.join(td, "zc3")))
    tops = {n: N.head_top(b) for n, b in fr.items()}
    if len(set(tops.values())) != 1:
        bad.append(f"head top {tops}")
    slip = N.foot_slip(fr, ["nun_walk2", "nun_walk1"])
    if any(slip):
        bad.append(f"slip {slip}")

    pool = {n: N.pool(H, b.shape[1], 0, 24, flags[n]) for n, b in fr.items()}
    tot = sum(pool.values())
    idle_only = sum(N.pool(H, 24, 0, 24, "STA") for _ in fr)
    L = ["# ART13c nun Archmage FINAL (option D, side cast) — costs (tools/gen_art13c_nun.py).",
         "# pool = src/defs.asm FRM formula, both facings stored (left = mirror), one shift",
         "# per flag: WK0 / STA shift 0, WK4 shift 4 (+1 col). No SYM, no frontal frame.",
         "# Today the Archmage shares the Necro frames: every byte below is extra, on D8 only.",
         "", "frame       flags  W  pool  src(raw)  new fid (FRM order, own unit U_ARCH)"]
    for i, (n, _p, f) in enumerate(FRAMES):
        L.append(f"{n:11s} {f:5s} 24  {pool[n]:4d}  {H * 3 * 2 + 1:5d}     KFID_ARCH + {i}")
    L += ["",
          f"TOTAL 4 fids  pool {tot} B  SRC6 zx0 ≈{pk} B   D8 Warrior slack {SLACK} -> {SLACK - tot:+d}",
          f"  without HURT (rest + flash, as today): 3 fids  pool {tot - pool['nun_hurt']} B  "
          f"SRC6 ≈{pk3} B  slack -> {SLACK - tot + pool['nun_hurt']:+d}",
          f"  idle-only (the Archmage never walks, A3: WALK2 drawn cell-aligned -> STA):  pool {idle_only} B"
          f"  slack -> {SLACK - idle_only:+d}",
          "  RAISE telegraph not drawn: +1 fid, +480 B (STA 24w).",
          "",
          "FRAME IDS: 4 of the 8 spare (FRT_MAX 144). Absolute numbers are assigned by FCTR at",
          "import: a new kind group KFID_ARCH (nun_walk1, nun_walk2, nun_cast, nun_hurt) inside the",
          "monster range after the Necro group (later fids shift by 4); appended at the end of",
          "the current list they would be FID_COUNT .. FID_COUNT + 3 (136..139 with 136 used).",
          "Sequences: ksm_ar-style own block: MOVECYC2 walk2, walk1; CAST = cast; HURT = hurt;",
          "idle = walk1 (rest). pool_gmap: Archmage -> U_ARCH + U_DEADH + U_NBOLT (no longer Necro).",
          "",
          "INK REGIONS (one ink; the telegraph recolours all of it): solid = coif brim rows 4-5,",
          "wimple / bib, face (brow, nose, cheek, jaw), hands, cross; 50 % hatch = veil + habit;",
          f"paper = hood shadow row 6, the 3x3 socket rows 8-10, mouth, chin shadow; 1-px glow at",
          f"face ({OX + GLOW[0]},{GLOW[1]}) (cast: 3-px cross). Round-tripped in " + ", ".join(INKS) + ".",
          f"checks: head top {sorted(set(tops.values()))}, shuffle slip {slip}, frontal frames 0."]
    with open(os.path.join(OUT, "costs_c.txt"), "w") as fh:
        fh.write("\n".join(L) + "\n")

    bd = [N.heading("F3p ART13c — NUN ARCHMAGE FINAL (OPTION D, SIDE CAST), 40 PX"),
          N.sub("All frames side view (profile facing right, mirrored for the left). 2-pose shuffle "
                "MOVECYC2 walk2, walk1 (WALK1 rest WK0, WALK2 WK4, planted shoe 4 px / tick), side "
                "CAST (arms raised at the hero, cross lifted, head tipped up, eyes flare), HURT. "
                f"Pool {tot} B (4 fids), SRC6 ≈{pk} B, D8 slack {SLACK - tot:+d}; without HURT "
                f"{tot - pool['nun_hurt']} B. Not imported."),
          N.row([S.svg_artboard_html(b, N.ARCH, n.upper().replace("_", " ")) for n, b in fr.items()]
                + [S.svg_artboard_html(ref["necro_walk1_v2"], N.ARCH, "NECRO V2 TODAY")])]
    for lab, ink in SHOW:
        bd.append(N.heading(f"F3p STRIPS {lab}"))
        cells = []
        for cl, cyc in CYC.items():
            rows = [ticks(fr, cyc, fc, cl == "WALK")[0] for fc in (1, -1)]
            _t, W, Hh = ticks(fr, cyc, 1, cl == "WALK")
            cells.append(N.anim_svg(rows, ink, W, Hh, f"NUN {cl} {lab}"))
            if ink == N.ARCH:
                N.ticks_gif(os.path.join(ANIM, f"c_{cl.lower()}.gif"), rows, W, Hh, ink)
        if ink != "#00FFFF":
            for cl, cyc in NCYC.items():
                rows = [ticks(ref, cyc, fc, cl == "WALK")[0] for fc in (1, -1)]
                _t, W, Hh = ticks(ref, cyc, 1, cl == "WALK")
                cells.append(N.anim_svg(rows, ink, W, Hh, f"NECRO V2 (today) {cl} {lab}"))
        bd.append(N.row(cells))
    bd.append(N.heading("F3p ALL INKS (WALK1 / CAST)"))
    bd.append(N.row([S.svg_artboard_html(fr["nun_walk1"], k, f"WALK1 {t}") for t, k in N.TIER + N.TELE[1:]]))
    bd.append(N.row([S.svg_artboard_html(fr["nun_cast"], k, f"CAST {t}") for t, k in N.TIER + N.TELE[1:]]))
    with open(os.path.join(OUT, "art13c_nun.svg.html"), "w") as fh:
        fh.write("\n".join(bd) + "\n")
    N.sheet(os.path.join(OUT, "art13c_nun.png"),
            [("NUN D FINAL $04", [(b, N.ARCH) for b in fr.values()]),
             ("NECRO V2 today", [(b, N.ARCH) for b in ref.values()]),
             ("walk1 tele inks", [(fr["nun_walk1"], k) for _, k in N.TELE]),
             ("cast tele inks", [(fr["nun_cast"], k) for _, k in N.TELE])])
    print("\n".join(L[6:14]))
    if bad:
        print("FAIL:\n  " + "\n  ".join(bad))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
