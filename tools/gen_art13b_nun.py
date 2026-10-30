#!/usr/bin/env python3
"""gen_art13b_nun.py — ART13b (user 2026-10-30): the nun Archmage with AT MOST ONE
player-facing (frontal) frame (the reveal / cast); every other frame is a SIDE VIEW
like every other monster (profile facing right, mirrored for the left facing).
CONCEPT, review only: nothing in index*.asm / frames.asm / SRC6.

Options (40 rows, bottom-anchored; same look as ART13 A: hatched habit / veil, solid
coif / wimple / face / hands, 3x3 hollow eye socket with a 1-px glow):
  C  SIDE GLIDE: GLIDE1 / GLIDE2 (profile, floats 2 px, hem trails, rosary swings),
     REVEAL = the ONE frontal frame (ART13 A RAISE: arms up, eyes flare; used for the
     telegraph AND the cast), HURT side (head snapped back, scream).
  D  SIDE SHUFFLE: WALK2 / WALK1 2-pose shuffle (MOVECYC2 walk2, walk1: WALK1 rest WK0
     odd slot, WALK2 WK4; planted shoe steps back exactly 4 px per tick, head fixed),
     REVEAL frontal, HURT side.
  E  HEAD-TURN: C's glide pair + HURT, the CAST is SIDE (32 wide, arm + cross thrust at
     the hero) with only the HEAD turned 3/4 to the player: no frontal body at all.
  F  SLIM (artist's pick): C at a 16-px body (BW 2: a nun in profile is 14 px deep);
     every side frame is 2 cells instead of 3, the frontal REVEAL stays 24 wide (ax 4).
Checks (exit 1): 40 rows, W % 8 == 0, gfx_convert clash + data / mask round-trip in
every ink shown, head top constant per option, D walk planted-shoe slip 0.
Writes assets/gfx/concept/art13/: grid/*.grid, anim/*.gif, art13b_nun.svg.html (board
F3n), art13b_nun.png, costs_b.txt.  Usage: python3 tools/gen_art13b_nun.py
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

H, FLOOR = N.H, N.FLOOR
OUT, GRID_OUT, ANIM = N.OUT, N.GRID_OUT, N.ANIM
TIER_INK = ("$04 ARCHMAGE", "#00D700")
TELE_INK = ("$42 FIRE", "#FF3030")
INKS = sorted({k for _, k in N.TIER + N.TELE})
SLACK = 3194

# profile head, facing right, 16 cols (veil back = left, nose = col 15)
PHEAD = [
    "....vvvvvvv.....",
    "..vvVVVVVVVvv...",
    ".vVVVVVVVVVVVv..",
    ".vVVVVVVWWWWWWv.",
    "vVVVVVVWWWWWWWWv",
    "vVVVVVWWoooooo..",
    "vVVVVVWWo*****..",
    "vVVVVVWWo*ooo**.",
    "vVVVVVWWo*o*o***",
    "vVVVVVWWo*ooo**.",
    "vVVVVVWWo*****..",
    "vVVVVVWWo**o**..",
    "vVVVVVWWo***oo..",
    "vVVVVVWWo**o*o..",
    "vVVVVVWWWo***...",
    "vVVVVVWWWWWW....",
    "vVVVVVWWWWWWW...",
    "vVVVVVWWWWWWWW..",
    "vVVVVVWWWWWWWWv.",
    "vVVVVVVWWWWWWWv.",
]
P_SCREAM = {11: "vVVVVVWWo**o**..", 12: "vVVVVVWWo*oooo..", 13: "vVVVVVWWo*ooo...",
            14: "vVVVVVWWWo**....", }


def phatch(x):
    return x % 2 == 0


def phead(scream=False, hollow=False, flare=False):
    rows = list(PHEAD)
    if scream:
        for k, v in P_SCREAM.items():
            rows[k] = v
    b, _ = N.region(rows, w=16, hatch=phatch)
    b = b[:, :16]
    if hollow:
        b[8, 11] = False
    if flare:
        N.px(b, [(11, 7), (10, 8), (12, 8), (11, 9)])
    return b


def turned_head():
    """3/4 head for E's cast: the frontal head squeezed toward the facing — the far
    wimple side and veil cut 3 px, the face (both sockets) kept whole."""
    f = N.head(flare=True)
    t = np.zeros((H, 24), bool)
    keep = [c for c in range(24) if c not in (2, 3, 4)]     # drop 3 back-veil columns
    for i, c in enumerate(keep):
        t[:20, i + 3] = f[:20, c]
    return t


def side(pose, W=24, ox=4, bw=24):
    """Side-view nun (facing right). pose: GLIDE1 / GLIDE2 / HURT / WALK1 / WALK2 /
    CASTSIDE. ox = head column; the habit is drawn from ox - 2 .. ox + 17 (clipped)."""
    castside = pose == "CASTSIDE"
    walk = pose.startswith("WALK")
    hurt = pose == "HURT"
    w = 32 if castside else W
    b = np.zeros((H, w), bool)
    sway = {"GLIDE1": -1, "GLIDE2": 1}.get(pose, 0)
    hem_y = 37 if not walk else 37
    fr_end = min(ox + 17, bw - 1)
    for y in range(19, hem_y + 1):
        t = (y - 19) / (hem_y - 19)
        s = int(round(sway * 2 * max(0, y - 26) / 11)) if not walk else 0
        l = max(int(round(ox - 2 * t)) - (1 if hurt and y > 30 else 0) + min(s, 0) * 1, 0)
        r = min(int(round(ox + 15 + (fr_end - ox - 15) * t)) + max(s, 0), bw - 1)
        if s < 0:                                   # trailing hem: back edge further back
            l = max(l + s, 0)
        for x in range(l, r + 1):
            b[y, x] = phatch(x) or x in (l, r) or y in (19, hem_y)
    for x in range(0, w):                           # ragged hem
        if b[hem_y, x] and (x + (sway > 0)) % 3 == 0:
            b[hem_y, x] = False
    if walk:                                        # shoes: 2-pose shuffle
        feet = {"WALK1": (ox + 6, ox + 10), "WALK2": (ox + 6, ox + 14)}[pose] if bw == 24 else None
        feet = {"WALK1": (10, 14), "WALK2": (6, 14)}[pose]
        for x in feet:
            m = np.zeros_like(b)
            m[FLOOR - 1:FLOOR + 1, x - 1:x + 3] = True
            b[G3.dilate4(m) & ~m] = False
            b |= m
    else:                                           # floats: one wisp row
        b[38:40] = False
        for x in range(0, w):
            if b[hem_y - 1, x] and x % 4 == (2 if sway > 0 else 0):
                b[38, x] = True
    # the veil down the back
    for y in range(20, 30):
        for x in range(max(ox - 1, 0), ox + 2):
            if x < w:
                b[y, x] = phatch(x) or x == max(ox - 1, 0)
    if castside:
        hd = np.zeros((H, w), bool)
        hd[:, :24] = np.roll(turned_head(), ox - 4, axis=1)
        b[:20] &= ~G3.dilate4(hd[:20])
        b[:20] |= hd[:20]
    else:
        hd = phead(scream=hurt, hollow=hurt)
        dx = ox - (1 if hurt else 0)                # hurt: head snapped 1 px back
        m = np.zeros_like(b)
        for x in range(16):
            if 0 <= x + dx < w:
                m[:20, x + dx] = hd[:20, x]
        cl = G3.dilate4(m)
        cl[20:] = False                             # keep the habit's top edge (row 20+)
        b &= ~cl
        b |= m
    hx = min(ox + 13, w - 4)                        # hands / rosary in front of the chest
    if castside:
        N.line(b, [(ox + 13, 21), (ox + 19, 19), (ox + 24, 19)], 3, sep=True)
        N.stamp(b, "##\n##\n##", ox + 24, 18, sep=True)
        N.stamp(b, ".#.\n###\n.#.\n.#.\n.#.", ox + 25, 12, sep=True)
        N.px(b, [(ox + 23, 10), (ox + 27, 10), (ox + 25, 9), (ox + 26, 22), (ox + 25, 24), (ox + 26, 26)])
    elif hurt:                                      # arms flung back / up, rosary flying
        N.line(b, [(ox + 11, 21), (ox + 14, 25), (min(ox + 16, w - 2), 29)], 2, sep=True)
        N.line(b, [(ox + 6, 21), (max(ox + 1, 1), 25), (max(ox - 1, 0), 28)], 2, sep=True)
        N.rosary(b, min(ox + 14, w - 3), 27, 1)
    else:
        sw = 0 if walk else -sway
        N.line(b, [(ox + 8, 21), (hx, 24)], 1)
        N.stamp(b, "##.\n###\n.##", hx, 21, sep=True)  # pale clasped hands (profile)
        N.rosary(b, min(hx + 2, w - 3), 25, sw)
    return b


# ===========================================================================
REVEAL = N.nun_a("RAISE")                           # the one frontal frame (24 wide, SYM)


def opt_frames():
    """-> {opt: {name: (bm, ax, flags, frontal)}}, + per-option bw."""
    c = {"nun_c_glide1": (side("GLIDE1"), 0, "STA", False),
         "nun_c_glide2": (side("GLIDE2"), 0, "STA", False),
         "nun_c_reveal": (REVEAL, 0, "STA|SYM", True),
         "nun_c_hurt": (side("HURT"), 0, "STA", False)}
    d = {"nun_d_walk1": (side("WALK1"), 0, "WK0", False),
         "nun_d_walk2": (side("WALK2"), 0, "WK4", False),
         "nun_d_reveal": (REVEAL, 0, "STA|SYM", True),
         "nun_d_hurt": (side("HURT"), 0, "STA", False)}
    e = {"nun_e_glide1": c["nun_c_glide1"], "nun_e_glide2": c["nun_c_glide2"],
         "nun_e_cast": (side("CASTSIDE"), 0, "STA", False), "nun_e_hurt": c["nun_c_hurt"]}
    f = {"nun_f_glide1": (side("GLIDE1", 16, 0, 16), 0, "STA", False),
         "nun_f_glide2": (side("GLIDE2", 16, 0, 16), 0, "STA", False),
         "nun_f_reveal": (REVEAL, 4, "STA|SYM", True),
         "nun_f_hurt": (side("HURT", 16, 0, 16), 0, "STA", False)}
    return {"C": (c, 24), "D": (d, 24), "E": (e, 24), "F": (f, 16)}


CYC = {
    "C": {"IDLE": [("nun_c_glide1", 4), ("nun_c_glide2", 4)],
          "CAST": [("nun_c_glide1", 3), ("nun_c_reveal", 4), ("nun_c_glide1", 3)],
          "HURT": [("nun_c_glide1", 3), ("nun_c_hurt", 3), ("nun_c_glide1", 3)]},
    "D": {"WALK": [("nun_d_walk2", 1), ("nun_d_walk1", 1)],
          "CAST": [("nun_d_walk1", 3), ("nun_d_reveal", 4), ("nun_d_walk1", 3)],
          "HURT": [("nun_d_walk1", 3), ("nun_d_hurt", 3), ("nun_d_walk1", 3)]},
    "E": {"IDLE": [("nun_e_glide1", 4), ("nun_e_glide2", 4)],
          "CAST": [("nun_e_glide1", 3), ("nun_e_cast", 4), ("nun_e_glide1", 3)],
          "HURT": [("nun_e_glide1", 3), ("nun_e_hurt", 3), ("nun_e_glide1", 3)]},
    "F": {"IDLE": [("nun_f_glide1", 4), ("nun_f_glide2", 4)],
          "CAST": [("nun_f_glide1", 3), ("nun_f_reveal", 4), ("nun_f_glide1", 3)],
          "HURT": [("nun_f_glide1", 3), ("nun_f_hurt", 3), ("nun_f_glide1", 3)]},
    "A": {"IDLE": [("nun_a_glide1", 4), ("nun_a_glide2", 4)],
          "CAST": [("nun_a_glide1", 3), ("nun_a_raise", 3), ("nun_a_cast", 3), ("nun_a_glide1", 3)],
          "HURT": [("nun_a_glide1", 3), ("nun_a_hurt", 3), ("nun_a_glide1", 3)]},
}
TITLE = {"A": "A FRONTAL GLIDE (ART13, ref)", "C": "C SIDE GLIDE + FRONTAL REVEAL",
         "D": "D SIDE SHUFFLE + FRONTAL REVEAL", "E": "E SIDE + HEAD-TURN CAST (no frontal)",
         "F": "F SLIM 16-PX SIDE GLIDE + FRONTAL REVEAL"}


def ticks(fr, cyc, facing, walk, bw, reps=2):
    seq = [n for n, k in cyc for _ in range(k)] * reps
    W = (24 + 4 * len(seq) + 40) if walk else 64
    out = []
    for i, n in enumerate(seq):
        b, ax, fl, _f = fr[n]
        xb = (8 + 4 * i if facing > 0 else W - 32 - 4 * i) if walk else 20
        if facing > 0 or "SYM" in fl:
            out.append((b, xb - ax, H + 2 - b.shape[0], xb))
        else:
            out.append((np.fliplr(b), xb - (b.shape[1] - ax - bw), H + 2 - b.shape[0], xb))
    return out, W, H + 2


def main() -> int:
    bad = []
    opts = opt_frames()
    fa = {f"nun_a_{p.lower()}": (N.nun_a(p), 0, N.A_FLAG[p], p != "x") for p in N.A_POSES}
    opts_all = dict(opts)
    opts_all["A"] = (fa, 24)
    raw = {}
    with tempfile.TemporaryDirectory() as td:
        for o, (fr, bw) in opts.items():
            for name, (bm, ax, fl, _f) in fr.items():
                if bm.shape[0] != H or bm.shape[1] % 8:
                    bad.append(f"{name}: shape {bm.shape}")
                solid = S.make_mask(bm, outline=True)
                g = os.path.join(GRID_OUT, name + ".grid")
                with open(g, "w") as fh:
                    fh.write(A.grid_text(name, bm, solid, name.upper(), N.ARCH,
                                         f"ART13b option {o} concept (tools/gen_art13b_nun.py); review only")
                             .replace("tools/gen_art2_options.py", "tools/gen_art13b_nun.py")
                             .replace("# anchor: 0 0", f"# anchor: {ax} 0"))
                for ink in INKS:
                    raw[name] = A.pack_check(f"{name}_{ink[1:]}", g, bm, solid, ink, td)
        packed = {o: len(zp.zx0(b"".join(raw[n] for n in fr), os.path.join(td, "z" + o)))
                  for o, (fr, _bw) in opts.items()}
        packed_nohurt = {o: len(zp.zx0(b"".join(raw[n] for n in fr if "hurt" not in n),
                                       os.path.join(td, "y" + o))) for o, (fr, _bw) in opts.items()}
    for o, (fr, _bw) in opts.items():
        tops = {n: N.head_top(v[0]) for n, v in fr.items()}
        if len(set(tops.values())) != 1:
            bad.append(f"{o}: head top {tops}")
        if sum(v[3] for v in fr.values()) > 1:
            bad.append(f"{o}: more than one frontal frame")
    walk = ["nun_d_walk2", "nun_d_walk1"]
    slip = N.foot_slip({n: opts["D"][0][n][0] for n in walk}, walk)
    if any(slip):
        bad.append(f"D slip {slip}")

    # ---- costs ----
    L = ["# ART13b nun Archmage, side-view options — costs (tools/gen_art13b_nun.py). CONCEPT.",
         "# pool = src/defs.asm FRM formula (= gen_art13_nun.pool): per stored facing H x 2 x",
         "# (cols + 1 if off the 8-px grid at its shift); side frames store BOTH facings (the",
         "# left one is the mirror, generated at level entry); SYM = one stored facing, drawn",
         "# unmirrored both ways (the climb pairs' flag) — only for the frontal REVEAL.",
         "# Assumptions (engineer to confirm): (1) SYM accepted on a monster frame; (2) one shift",
         "# per frame (STA): the Archmage never walks, its G1d post and blink target are",
         "# cell-aligned (D's walk keeps WK0 / WK4 in case it ever moves); (3) F: Archmage body",
         "# width BW 2 (16 px; the Spider already has its own BW); (4) today HURT = rest + flash,",
         "# so every HURT frame is optional (the '-' totals).",
         f"# D8 Warrior slack {SLACK} B; target for the recommendation <= ~{SLACK // 2}.", "",
         "opt frame              flags     W  ax frontal  pool   src"]
    tot = {}
    for o in ("A", "C", "D", "E", "F"):
        fr, bw = opts_all[o]
        t = th = 0
        for n, (bm, ax, fl, fro) in fr.items():
            if o == "A":
                fro = "SYM" in fl
            p = N.pool(H, bm.shape[1], ax, bw, fl)
            t += p
            th += 0 if "hurt" in n else p
            L.append(f" {o}  {n:18s} {fl:9s} {bm.shape[1]:2d} {ax:3d}  {'YES' if fro else '-':5s}  {p:5d} "
                     f"{H * (bm.shape[1] // 8) * 2 + 1:5d}")
        if o == "A":
            t -= N.pool(H, 24, 0, 24, "STA|SYM")    # A recommended = without RAISE
            th = t - N.pool(H, 24, 0, 24, "STA|SYM")
        tot[o] = (t, th, len(fr) - (1 if o == "A" else 0))
    L.append("")
    L.append("opt  fids  pool total  slack left | without HURT (rest + flash): fids pool slack | SRC6 zx0 (no hurt)")
    for o in ("A", "C", "D", "E", "F"):
        t, th, n = tot[o]
        pk = f"{packed[o]} ({packed_nohurt[o]})" if o in packed else "477 (ART13)"
        L.append(f" {o}    {n}    {t:6d}    {SLACK - t:+6d}   |  {n - 1}  {th:5d}  {SLACK - th:+6d}      | {pk}")
    L += ["", "FRT ids: 8 spare of 144. Frontal frames per option: A all (ref), C/D/F one (REVEAL),",
          "E none (CAST is side-view, only the head turns 3/4).",
          f"checks: head top constant per option, D shuffle planted-shoe slip {slip}, packed and",
          "round-tripped in " + ", ".join(INKS) + "."]
    with open(os.path.join(OUT, "costs_b.txt"), "w") as fh:
        fh.write("\n".join(L) + "\n")

    # ---- board F3n ----
    bd = [N.heading("F3n ART13b — NUN ARCHMAGE, SIDE VIEW (≤ 1 FRONTAL FRAME), CONCEPT 40 PX"),
          N.sub("Rule (user): at most one player-facing frame (the reveal / cast); every other frame "
                "is a profile facing right, mirrored for the left facing. Same look as ART13 A: hatched "
                "habit, solid wimple / face, 3x3 hollow socket + 1-px glow. Strips: top row facing right, "
                "bottom row facing left. Not wired; review only.")]
    for o in ("A", "C", "D", "E", "F"):
        fr, bw = opts_all[o]
        t, th, n = tot[o]
        bd.append(N.heading(f"F3n {TITLE[o]}"))
        bd.append(N.sub(f"{n} fids, pool {t} B (slack left {SLACK - t:+d}); without HURT {th} B "
                        f"(slack {SLACK - th:+d})."
                        + (" A = the ART13 option without RAISE." if o == "A" else
                           f" SRC6 ≈ {packed[o]} B packed.")))
        bd.append(N.row([S.svg_artboard_html(v[0], N.ARCH, n2.replace("nun_", "NUN ").replace("_", " ").upper()
                                             + (" FRONTAL" if (v[3] and o != "A") else ""))
                         for n2, v in fr.items()]))
        cells = []
        for lab, ink in (TIER_INK, TELE_INK):
            for cl, cyc in CYC[o].items():
                rows = [ticks(fr, cyc, fc, cl == "WALK", bw)[0] for fc in (1, -1)]
                _t, W, Hh = ticks(fr, cyc, 1, cl == "WALK", bw)
                cells.append(N.anim_svg(rows, ink, W, Hh, f"{o} {cl} {lab}"))
                if ink == N.ARCH:
                    N.ticks_gif(os.path.join(ANIM, f"b_{o.lower()}_{cl.lower()}.gif"), rows, W, Hh, ink)
        bd.append(N.row(cells))
    bd.append(N.sub("Costs: " + " | ".join(" ".join(x.split()) for x in L if x[:2] in (" A", " C", " D", " E", " F")
                                           and "|" in x)))
    with open(os.path.join(OUT, "art13b_nun.svg.html"), "w") as fh:
        fh.write("\n".join(bd) + "\n")
    sh = [(TITLE[o][:22], [(v[0], N.ARCH) for v in opts_all[o][0].values()]) for o in ("A", "C", "D", "E", "F")]
    sh.append(("C $42 / F $45 / E $47", [(opts["C"][0]["nun_c_glide1"][0], "#FF3030"),
                                         (opts["F"][0]["nun_f_glide1"][0], "#00FFFF"),
                                         (opts["E"][0]["nun_e_cast"][0], "#FFFFFF"),
                                         (opts["D"][0]["nun_d_walk2"][0], "#FF00FF")]))
    N.sheet(os.path.join(OUT, "art13b_nun.png"), sh)
    print("\n".join(L[-10:]))
    if bad:
        print("FAIL:\n  " + "\n  ".join(bad))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
