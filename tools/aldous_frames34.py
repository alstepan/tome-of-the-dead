#!/usr/bin/env python3
"""aldous_frames34.py — 3/4-view VARIANT of the D0 mentor "Aldous the Sexton", for comparison
with the front-facing draft (tools/aldous_frames.py, assets/gfx/source/aldous/sxt_*.grid).

Source: hand-authored 2-state grids assets/gfx/source/aldous/q34/sxt34_*.grid (24x48, one ink
#00D7D7 = cyan $05 non-bright on black; docs/design/tutorial_d0.md §4.1-4.3). Every frame is
RIGHT-facing (turned toward the hero); left = engine mirror, so all 7 ids have a facing
(7 x 2 = 14 stored images if pre-mirrored, vs 8 for the front draft). DRAFT only: no asm, nothing
touches src/, sprites/index.asm or *_defs.asm; the front draft and its outputs are not modified.

Checks (exit 1 on failure):
  - every grid 24x48, ink in svg_sprites.INK_MAP;
  - attribute legality via gfx_convert --layout native (clash + round-trip), cyan on black;
  - sxt34_fade.grid == fade34(sxt34_idle1.grid)  (run with --regen-fade to rewrite it).
Writes into assets/gfx/source/aldous/q34/:
  aldous34_frames.svg.html   canvas artboards under a "SEXTON 3/4" heading
  aldous34_compare.svg.html  per frame: front draft | 3/4 R | 3/4 mirrored L
  aldous34_preview.svg.html  animated IDLE / TALK / BLINK / POINT (R, L, POINTDN)
  aldous34_{idle,talk,blink,point}.gif, aldous34_sheet.png (row 1 front, row 2 3/4, row 3 mirror)
Usage: python3 tools/aldous_frames34.py [--regen-fade]
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aldous_frames as A  # noqa: E402  (shared W/H/INK/BAYER, clash_check, anim_svg, rgb)
import svg_sprites as S  # noqa: E402

SRC = os.path.join(A.REPO, "assets/gfx/source/aldous/q34")
FRONT = A.SRC
FRAMES = A.FRAMES
W, H, INK = A.W, A.H, A.INK
HEM_ROW = 35                      # fade: 50% above, 25% from here down (same as front)
LANTERN = (26, 35, 11, 20)        # 3/4 lantern box kept solid (rows y0..y1, cols x0..x1)
SEQS = A.SEQS                     # same timings (tutorial_d0.md §4.3)

HEADER = """\
# Tome of the Dead gfx text grid — DERIVED by tools/aldous_frames34.py --regen-fade; do not hand-edit.
# name: sxt34_fade
# size: 24x48
# character: SEXTON 3/4
# caption: SXT34 FADE
# ink: #00D7D7
# anchor: 0 0
# pose: SXT34 IDLE1 through a 4x4 Bayer dither: 50% above row {hem}, 25% on hem + wisp; lantern (rows {y0}-{y1}, cols {x0}-{x1}) kept solid. RIGHT-facing (left = engine mirror)
# spec: docs/design/tutorial_d0.md §4.1-4.3 (Aldous the Sexton, ink cyan $05 on black, no mask)
# legend: '#' ink, '.' paper (2-state: unmasked, drawn into the background)
#
"""


def fade34(b: np.ndarray) -> np.ndarray:
    out = b.copy()
    y0, y1, x0, x1 = LANTERN
    for y in range(H):
        thr = 8 if y < HEM_ROW else 4
        for x in range(W):
            if out[y, x] and A.BAYER[y % 4][x % 4] >= thr and not (y0 <= y <= y1 and x0 <= x <= x1):
                out[y, x] = False
    return out


def load(path: str, bad: list[str], tmp: str, tag: str):
    bm, meta = S.read_grid(path)
    if bm.shape != (H, W):
        bad.append(f"{tag}: size {bm.shape[1]}x{bm.shape[0]} != {W}x{H}")
    if meta.get("ink", "").upper() != INK or INK not in S.INK_MAP:
        bad.append(f"{tag}: ink {meta.get('ink')!r} != {INK}")
    err = A.clash_check(path, tmp)
    if err:
        bad.append(f"{tag}: gfx_convert: {err}")
    return bm.astype(bool), meta


def main() -> int:
    if "--regen-fade" in sys.argv:
        bm, _ = S.read_grid(os.path.join(SRC, "sxt34_idle1.grid"))
        f = fade34(bm.astype(bool))
        y0, y1, x0, x1 = LANTERN
        with open(os.path.join(SRC, "sxt34_fade.grid"), "w") as fh:
            fh.write(HEADER.format(hem=HEM_ROW, y0=y0, y1=y1, x0=x0, x1=x1)
                     + "\n".join("".join("#" if v else "." for v in r) for r in f) + "\n")

    bad: list[str] = []
    q: dict[str, np.ndarray] = {}
    caps: dict[str, str] = {}
    front: dict[str, np.ndarray] = {}
    fcaps: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for f in FRAMES:
            q[f], meta = load(os.path.join(SRC, f"sxt34_{f}.grid"), bad, tmp, f"sxt34_{f}")
            caps[f] = meta.get("caption", f"SXT34 {f.upper()}")
            fb, fm = S.read_grid(os.path.join(FRONT, f"sxt_{f}.grid"))   # read-only, for compare
            front[f], fcaps[f] = fb.astype(bool), fm.get("caption", f"SXT {f.upper()}")
    if not np.array_equal(fade34(q["idle1"]), q["fade"]):
        bad.append("fade: sxt34_fade.grid != fade34(sxt34_idle1.grid); run with --regen-fade")
    q["point_l"] = q["point"][:, ::-1]
    ink = {f: int(q[f].sum()) for f in FRAMES}
    fink = {f: int(front[f].sum()) for f in FRAMES}

    head = ('<div style="font-family: \'Press Start 2P\', monospace; font-size: 13px; '
            'color: #e8e6f0; letter-spacing: 1px;">SEXTON 3/4</div>')
    row = '<div style="display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-start;">\n{}\n</div>'
    with open(os.path.join(SRC, "aldous34_frames.svg.html"), "w") as fh:
        fh.write(head + "\n" + row.format("\n".join(S.svg_artboard_html(q[f], INK, caps[f])
                                                    for f in FRAMES)) + "\n")

    chead = ('<div style="font-family: \'Press Start 2P\', monospace; font-size: 13px; '
             'color: #e8e6f0; letter-spacing: 1px;">SEXTON FRONT vs 3/4</div>')
    groups = []
    for f in FRAMES:
        trio = [S.svg_artboard_html(front[f], INK, fcaps[f]),
                S.svg_artboard_html(q[f], INK, caps[f]),
                S.svg_artboard_html(q[f][:, ::-1], INK, caps[f] + " L")]
        groups.append('<div style="display: flex; gap: 8px; align-items: flex-start; padding: 8px; '
                      'border: 1px solid #26263a;">\n' + "\n".join(trio) + "\n</div>")
    with open(os.path.join(SRC, "aldous34_compare.svg.html"), "w") as fh:
        fh.write(chead + "\n" + row.format("\n".join(groups)) + "\n")

    cells = [A.anim_svg(seq, q, lab) for lab, seq in SEQS.items()]
    with open(os.path.join(SRC, "aldous34_preview.svg.html"), "w") as fh:
        fh.write(head + "\n" + row.format("\n".join(cells)) + "\n")
    for tag, (_lab, seq) in zip(("idle", "talk", "blink", "point"), SEQS.items()):
        ims = [A.rgb(q[f]) if f else A.rgb(np.zeros((H, W), bool)) for f, _t in seq]
        ims[0].save(os.path.join(SRC, f"aldous34_{tag}.gif"), save_all=True, append_images=ims[1:],
                    duration=[t * 20 for _f, t in seq], loop=0)

    cw, ch = W * 4 + 8, (H + 8) * 4 + 8
    sheet = Image.new("RGB", (cw * len(FRAMES), ch * 3), (0, 0, 0))
    for i, f in enumerate(FRAMES):
        for r, bm in enumerate((front[f], q[f], q[f][:, ::-1])):
            sheet.paste(A.rgb(bm), (i * cw, r * ch))
    sheet.save(os.path.join(SRC, "aldous34_sheet.png"))

    print(f"{len(FRAMES)} 3/4 frames {W}x{H}, ink {INK} on black: "
          + ("FAIL\n  " + "\n  ".join(bad) if bad else "clash-legal, gfx_convert round-trip OK, fade in sync"))
    print("ink px 3/4 vs front: " + ", ".join(f"{f} {ink[f]}/{fink[f]}" for f in FRAMES))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
