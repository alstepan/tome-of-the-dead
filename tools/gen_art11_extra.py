#!/usr/bin/env python3
"""gen_art11_extra.py — ART11 extra-frame PROPOSALS (coordinator 2026-10-30): strips only.

Top proposals drawn (the rest are costed in costs_extra.txt, not drawn):
  X1 ORC walk W2 W1 W3 W4: a 4th distinct pose W4 (the far-leg passing pose).
     Today W1 sits in BOTH odd slots, so one passing pose serves two different
     legs: the far foot cannot be planted on both sides of it (ART11 had to
     choose W1 feet 2 px apart -> strides 10 / 6 = a limp). With W4 the near
     chain W2 17 -> W1 13 -> W3 9 and the far chain W3 17 -> W4 13 -> W2 9 are
     both exact and both strides are 8. +1 frame (WK0), MOVECYC4 walk2, walk1,
     walk3, walk4 (phase rule: even slots WK4, odd WK0; W1 stays the rest pose).
  X2 VAMPIRE walk W2 W1 W3 W4: the same fix for the ART9 Vampire (far chain
     17 -> 11 -> 7 = slides 2 px; with W4: 17 -> 13 -> 9).
Writes assets/gfx/sprites40/extra/: grid/*.grid (proposal frames, 40 rows, clash +
round-trip checked), *_film.png / *.gif (old vs new, both facings),
art11_extra.svg.html (board section). Not engine data.
Usage: python3 tools/gen_art11_extra.py
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_art2_options as A  # noqa: E402
import gen_art7_orc_options as O  # noqa: E402
import gen_art8_vampire as V  # noqa: E402
import gen_art9_final as F  # noqa: E402
import gen_art10_short as T  # noqa: E402
import gen_art11_40px as G  # noqa: E402
import svg_sprites as S  # noqa: E402

OUT = os.path.join(G.OUT, "extra")
GRID_OUT = os.path.join(OUT, "grid")

# ---- X1 Orc: far, near ankle x, far lifted, near lifted, knee dx (ART9 table form)
ORC_LEGS_X1 = dict(G.ORC_LEGS40,
                   W2=(9, 17, True, False, -1, 2),       # far back 9 (was 7), heel up
                   W3=(17, 9, False, True, 2, -1),       # far front 17 (was 15)
                   W4=(13, 13, False, False, 1, 0))      # far planted (sole 11 = W3 15 - 4), near passing 2 px up
F.ORC_BALL.setdefault("W4", (19, 36))                     # pendulum mid (as W1)
F.ORC_FIST.setdefault("W4", 0)


class OrcX1(G.OrcFlat):
    def legs(self, cv, pose, y, x0=0):
        far, near, lf, ln, kf, kn = ORC_LEGS_X1[pose]
        hy = self.hy + y
        kny = hy + (44 - hy) // 2
        xf, xn = self.xf + x0, self.xn + x0
        for (hx, ax, lift, kd, sep) in ((xf, far + x0, lf, kf, False), (xn, near + x0, ln, kn, True)):
            ay = 42 if (pose == "W4" and sep) else 44      # W4: the swinging near foot clears the floor
            O.leg(cv, (hx, hy), ((hx + ax) // 2 + kd, kny), (ax, ay), self.thigh, self.shin,
                  self.foot, sep=sep, lifted=lift)

    def frame(self, pose):
        cv = O.Cv(24)
        self.back(cv, pose, 0, 0)
        self.legs(cv, pose, 0, x0=0)
        cv.stamp(self.BODY, 0, 0)
        self.front(cv, pose, 0, 0)
        return cv.b


def orc_x1(pose):
    o = OrcX1()
    rec = []
    o.rec = rec
    real = O.Cv
    O.Cv = lambda w: T._RecCv(w, rec)
    try:
        base = o.frame(pose)
    finally:
        O.Cv = real
    o.rec = None
    s = np.array([r for y, r in enumerate(base) if y not in T.ORC_DROP], bool)
    cv = O.Cv(base.shape[1])
    cv.b[8:] = s
    for op in rec:
        if op[0] == "stamp":
            _, txt, x, y, sep = op
            cv.stamp(txt, x, T._map(y) + 8, sep)
        else:
            _, x0, y0, x1, y1, sep = op
            F.OrcFinal.chain(o, cv, x0, T._map(y0) + 8, x1, T._map(y1) + 8, sep)
    return cv.b[8:].copy().astype(bool)


# ---- X2 Vampire: (hip, knee, ankle, toe) per leg, (first = far, second = near) as ART9
V_LEGS_X2 = dict(F.V_LEGS_FINAL,
                 stride_a=(((11, 27), (10, 36), (10, 42), (12, 46)),    # far back (toe 12 = W4 16 - 4)
                           ((14, 27), (16, 35), (18, 43), (22, 46))),
                 stride_b=(((14, 27), (16, 36), (17, 43), (21, 46)),    # near back toe 13 (= W1 17 - 4)
                           ((11, 27), (11, 36), (11, 42), (13, 46))),
                 pass_b=(((11, 27), (12, 36), (13, 43), (16, 46)),      # far planted 13
                         ((14, 27), (13, 35), (12, 41), (14, 44))))     # near swinging, lifted
V_CAPE_X2 = dict(V.CAPE, pass_b=V.CAPE["rest"])
F.V_ARM.setdefault("pass_b", 0)


def vamp_sets():
    old40, _m, d = F.vamp_frames()                  # ART9 final (also patches V.LEGS)
    V.LEGS.clear()
    V.LEGS.update(V_LEGS_X2)
    V.CAPE.update(V_CAPE_X2)
    new48 = {"W1": F._vampire("rest"), "W2": F._vampire("stride_a"), "W3": F._vampire("stride_b"),
             "W4": F._vampire("pass_b")}
    new40 = {p: np.array([r for y, r in enumerate(b) if y not in d], bool) for p, b in new48.items()}
    return old40, new40


def main() -> int:
    os.makedirs(GRID_OUT, exist_ok=True)
    res = G.orc_kind()
    orc_old = {p: res[F.ORC_NAME[p]]["b40"] for p in ("W1", "W2", "W3")}
    orc_new = {p: orc_x1(p) for p in ("W1", "W2", "W3", "W4")}
    v_old, v_new = vamp_sets()
    sets = [("orc_x1", "ORC X1 WALK W2 W1 W3 W4", G.ORC, orc_old, ("W2", "W1", "W3", "W1"),
             orc_new, ("W2", "W1", "W3", "W4")),
            ("vamp_x2", "VAMPIRE X2 WALK W2 W1 W3 W4", F.VAMP_INK, v_old, ("W2", "W1", "W3", "W1"),
             v_new, ("W2", "W1", "W3", "W4"))]
    h = [F.heading("F3k EXTRA — PROPOSALS X1 / X2 (4th distinct walk pose)"),
         F.sub("Old = W2 W1 W3 W1 (one passing pose for both legs: the far foot slides or the gait "
               "limps); new = W2 W1 W3 W4, both planted feet step back exactly 4 px per tick, equal strides.")]
    with tempfile.TemporaryDirectory() as td:
        for tag, lab, ink, old, oc, new, nc in sets:
            for p, b in new.items():
                assert b.shape[0] == 40, (tag, p, b.shape)
                solid = S.make_mask(b, outline=True)
                g = os.path.join(GRID_OUT, f"{tag}_{p.lower()}.grid")
                with open(g, "w") as fh:
                    fh.write(A.grid_text(f"{tag}_{p.lower()}", b, solid, f"{p} 40 (proposal)", ink,
                                         "ART11 extra-frame proposal (tools/gen_art11_extra.py)"))
                A.pack_check(f"{tag}_{p.lower()}", g, b, solid, ink, td)
            fo = {p: (b, 0) for p, b in old.items()}
            fn = {p: (b, 0) for p, b in new.items()}
            co = [(p, 1) for p in oc]
            cn = [(p, 1) for p in nc]
            cells = []
            for sfx, fr, cy in (("old", fo, co), ("new", fn, cn)):
                rows = []
                for facing in (1, -1):
                    tk, W, Hh = G.cycle_ticks(fr, cy, 24, True, facing, box=40)
                    rows.append(tk)
                G.ticks_gif(os.path.join(OUT, f"{tag}_{sfx}.gif"), rows, W, Hh, ink)
                G.ticks_film(os.path.join(OUT, f"{tag}_{sfx}_film.png"), rows, Hh, ink, f"{lab} {sfx}")
                rows1 = []
                for facing in (1, -1):
                    tk, W, Hh = G.cycle_ticks(fr, cy, 24, True, facing, reps=1, box=40)
                    rows1.append(tk)
                cells.append(G.anim_svg(rows1, ink, W, Hh, f"{lab} — {sfx.upper()}"))
            names = list(nc)
            sl_o = G.foot_slip({p: old[p] for p in oc}, list(oc))
            sl_n = G.foot_slip({p: new[p] for p in names}, names)
            print(f"{tag}: slip old {sl_o} new {sl_n}")
            h.append(F.heading(f"F3k {lab}"))
            h.append(F.row([S.svg_artboard_html(new[p], ink, f"{lab.split()[0]} {p} 40") for p in new]))
            h.append(F.row(cells))
            h.append(F.sub(f"planted-foot slip per tick (bottom row): old {sl_o} -> new {sl_n}"))
    with open(os.path.join(OUT, "art11_extra.svg.html"), "w") as fh:
        fh.write("\n".join(h) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
