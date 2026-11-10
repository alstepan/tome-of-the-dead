#!/usr/bin/env python3
"""aldous_frames.py — review artefacts + checks for the D0 mentor "Aldous the Sexton".

Source: hand-authored 2-state grids assets/gfx/source/aldous/sxt_*.grid (24x48, one ink
#00D7D7 = cyan $05 non-bright on black paper; docs/design/tutorial_d0.md §4.1-4.2).
DRAFT art for the user's Design canvas: no engine asm is emitted here (the mentor's data
format is still open), nothing touches src/, sprites/index.asm or *_defs.asm.

Checks (exit 1 on failure):
  - every grid 24x48, whole 8-px cells, ink in svg_sprites.INK_MAP;
  - attribute legality: gfx_convert --layout native packs each grid (into a temp dir)
    with ink cyan / paper black and its clash + round-trip validation passes — one ink
    on black paper, so every 8x8 cell is 2-colour by construction;
  - sxt_fade.grid == fade(sxt_idle1.grid) (the documented derivation).
Writes into assets/gfx/source/aldous/:
  aldous_frames.svg.html   canvas artboards (svg_sprites export format) under a
                           13px Press-Start "SEXTON" heading, ready to paste
  aldous_preview.svg.html  animated SMIL previews: IDLE loop, TALK loop, BLINK (fade)
  aldous_{idle,talk,blink}.gif, aldous_sheet.png
Usage: python3 tools/aldous_frames.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import svg_sprites as S  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "assets/gfx/source/aldous")
FRAMES = ("idle1", "idle2", "talk1", "talk2", "point", "pointdn", "fade")
W, H = 24, 48
INK = "#00D7D7"
BAYER = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
HEM_ROW = 35                      # fade: 50% above, 25% from here down
LANTERN = (26, 35, 6, 15)         # fade keeps the lantern solid (rows y0..y1, cols x0..x1)

# Tutorial timings (tutorial_d0.md §4.3) in 50 Hz ticks; the preview shows them 1:1
SEQS = {
    "IDLE (toggles once per turn; shown at 0.5 s)": [("idle1", 25), ("idle2", 25)],
    "TALK (16-tick gesture, 4 ticks/frame x2, then pose)": [("talk1", 4), ("talk2", 4)] * 2
    + [("idle1", 24)],
    "BLINK (FADE 2 -> gone -> FADE 2 -> pose)": [("idle1", 25), ("fade", 2), (None, 6),
                                                 ("fade", 2), ("idle1", 25)],
    "POINT R / POINT L (mirror) / POINTDN": [("point", 25), ("point_l", 25), ("pointdn", 25)],
}


def fade(b: np.ndarray) -> np.ndarray:
    out = b.copy()
    y0, y1, x0, x1 = LANTERN
    for y in range(H):
        thr = 8 if y < HEM_ROW else 4
        for x in range(W):
            if out[y, x] and BAYER[y % 4][x % 4] >= thr and not (y0 <= y <= y1 and x0 <= x <= x1):
                out[y, x] = False
    return out


def clash_check(path: str, tmp: str) -> str | None:
    r = subprocess.run([sys.executable, os.path.join(REPO, "tools/gfx_convert.py"), "--mode", "sprite",
                        "--layout", "native", "--in", path, "--width", str(W), "--height", str(H),
                        "--ink", "cyan", "--paper", "black", "--name", "sxt_check",
                        "--out", os.path.join(tmp, os.path.basename(path) + ".asm"),
                        "--date", "2026-11-09"], capture_output=True, text=True)
    return None if r.returncode == 0 else (r.stdout + r.stderr).strip()


def anim_svg(seq, bms, label, scale=3):
    n = sum(t for _f, t in seq)
    total = n / 50.0
    out = [f'<svg width="{W * scale}" height="{(H + 8) * scale}" viewBox="0 0 {W} {H + 8}" '
           f'shape-rendering="crispEdges" style="display: block;">',
           f'<rect width="{W}" height="{H + 8}" fill="#000000"></rect>',
           f'<rect x="0" y="{H + 7}" width="{W}" height="1" fill="#26264a"></rect>']  # floor, 1 row of air
    ticks = [f for f, t in seq for _ in range(t)]          # one discrete value per 50 Hz tick
    for f in dict.fromkeys(x for x in ticks if x is not None):
        vals = ";".join("1" if x == f else "0" for x in ticks)
        out.append(f'<g opacity="{1 if ticks[0] == f else 0}"><path d="{S.bitmap_to_path(bms[f])}" '
                   f'fill="{INK}"></path><animate attributeName="opacity" values="{vals}" '
                   f'dur="{total:.2f}s" calcMode="discrete" repeatCount="indefinite"></animate></g>')
    out.append("</svg>")
    return ('<div style="display: flex; flex-direction: column; gap: 8px; align-items: flex-start;">\n'
            '<div style="padding: 8px; background: #000000; border: 2px solid #26263a;">'
            + "".join(out) + "</div>\n"
            f'<div style="font-size: 11px; letter-spacing: 1px; color: #a9a7b8;">{label}</div>\n</div>')


def rgb(b: np.ndarray, scale=4) -> Image.Image:
    a = np.zeros((H + 8, W, 3), np.uint8)
    a[H + 7, :] = (38, 38, 74)
    a[:H][b] = (0, 215, 215)
    return Image.fromarray(a).resize((W * scale, (H + 8) * scale), Image.NEAREST)


def main() -> int:
    bad: list[str] = []
    bms: dict[str, np.ndarray] = {}
    caps: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for f in FRAMES:
            p = os.path.join(SRC, f"sxt_{f}.grid")
            bm, meta = S.read_grid(p)
            if bm.shape != (H, W):
                bad.append(f"{f}: size {bm.shape[1]}x{bm.shape[0]} != {W}x{H}")
            if meta.get("ink", "").upper() != INK or INK not in S.INK_MAP:
                bad.append(f"{f}: ink {meta.get('ink')!r} != {INK}")
            err = clash_check(p, tmp)
            if err:
                bad.append(f"{f}: gfx_convert: {err}")
            bms[f] = bm.astype(bool)
            caps[f] = meta.get("caption", f.upper())
    if "idle1" in bms and "fade" in bms and not np.array_equal(fade(bms["idle1"]), bms["fade"]):
        bad.append("fade: sxt_fade.grid != fade(sxt_idle1.grid); regenerate it")
    bms["point_l"] = bms["point"][:, ::-1]

    head = ('<div style="font-family: \'Press Start 2P\', monospace; font-size: 13px; '
            'color: #e8e6f0; letter-spacing: 1px;">SEXTON</div>')
    arts = [S.svg_artboard_html(bms[f], INK, caps[f]) for f in FRAMES]
    row = '<div style="display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-start;">\n{}\n</div>'
    with open(os.path.join(SRC, "aldous_frames.svg.html"), "w") as fh:
        fh.write(head + "\n" + row.format("\n".join(arts)) + "\n")
    cells = [anim_svg(seq, bms, lab) for lab, seq in SEQS.items()]
    with open(os.path.join(SRC, "aldous_preview.svg.html"), "w") as fh:
        fh.write(head + "\n" + row.format("\n".join(cells)) + "\n")
    for tag, (lab, seq) in zip(("idle", "talk", "blink", "point"), SEQS.items()):
        ims = [rgb(bms[f]) if f else rgb(np.zeros((H, W), bool)) for f, _t in seq]
        durs = [t * 20 for _f, t in seq]
        ims[0].save(os.path.join(SRC, f"aldous_{tag}.gif"), save_all=True, append_images=ims[1:],
                    duration=durs, loop=0)
    sheet = Image.new("RGB", ((W * 4 + 8) * len(FRAMES), (H + 8) * 4), (0, 0, 0))
    for i, f in enumerate(FRAMES):
        sheet.paste(rgb(bms[f]), (i * (W * 4 + 8), 0))
    sheet.save(os.path.join(SRC, "aldous_sheet.png"))
    print(f"{len(FRAMES)} frames (+POINT L mirror) {W}x{H}, ink {INK} on black: "
          + ("FAIL\n  " + "\n  ".join(bad) if bad else "clash-legal, gfx_convert round-trip OK, fade in sync"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
