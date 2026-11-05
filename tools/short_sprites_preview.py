#!/usr/bin/env python3
"""short_sprites_preview.py — CONCEPT: hero/monster sprites redrawn 8 px shorter.

Review artefact only (no engine data, no canvas): the user compares CURRENT vs SHORT
before deciding whether to shrink the body box (BH_K_* 6 -> 5 rows for the 48-px kinds).

Each SHORT frame is a redraw of its canvas frame (assets/gfx/sprites/grid/<src>.grid):
rows are removed at chosen joints (one-shot proposal; EDITS stays empty in this draft) (helmet/hat, torso, beard, robe, shin, boot) and the
joints are hand-fixed by per-row edits (EDITS) — never a uniform squash, never a crop.
The foot line stays on the frame's bottom row (same blank-rows-below-feet as the source).

Writes
  assets/gfx/concept/short_sprites/<name>.grid        3-state grid (ink '#', mask '+')
  assets/gfx/concept/short_sprites/short_sprites.svg.html   review page (x4 + x1)
  <png> (optional --png FILE)                          side-by-side PNG for eyeballing
Validation (exit 1 on failure): every frame packed through tools/gfx_convert.py --layout
native (clash: <= 2 colours per 8x8 cell), DEFB decoded back == grid (data AND mask),
H == target, W == source W, foot line == source foot line.
Usage: python3 tools/short_sprites_preview.py [--png FILE]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gfx_convert  # noqa: E402
import svg_sprites as ss  # noqa: E402

REPO = ss.REPO
SRC_DIR = os.path.join(REPO, "assets/gfx/sprites/grid")
OUT_DIR = os.path.join(REPO, "assets/gfx/concept/short_sprites")
PAGE = os.path.join(OUT_DIR, "short_sprites.svg.html")

# name -> (source frame, role label, rows to DROP (source indices), {source row: new ink row})
# Every kind loses 8 rows. The goblin is already 24x32 (BH_K_GOBLIN 4): its SHORT is 24x24.
SPECS = {
    # KNIGHT 24x48 -> 24x40: helmet -1, torso -1, shield -1, thigh -1, shin -3, boot -1
    "knight_idle1": ("knight_idle1", "IDLE", {4, 18, 26, 35, 37, 40, 41, 46}, {}),
    "knight_walk1": ("knight_walk1", "WALK 1", {5, 19, 27, 32, 38, 39, 41, 46}, {}),
    "knight_slash": ("knight_slash", "SLASH (attack)", {4, 19, 24, 31, 33, 39, 42, 46}, {}),
    # WIZARD 24x48 -> 24x40: hat kept whole (identity), beard -2, robe -6
    "wizard_idle": ("wizard_idle", "IDLE", {20, 21, 30, 32, 37, 38, 39, 43}, {}),
    "wizard_walk1": ("wizard_walk1", "WALK 1", {21, 22, 31, 35, 37, 39, 41, 43}, {}),
    "wizard_staffswing": ("wizard_staffswing", "STAFF SWING (attack)",
                          {22, 23, 30, 32, 37, 38, 39, 43}, {}),
    # SKELETON 24x48 (art 44 rows) -> 24x40 (art 36 rows, same 4 blank rows on top)
    "skeleton_walk1": ("skeleton_walk1", "WALK 1 (= REST)", {8, 17, 18, 24, 33, 36, 39, 42}, {}),
    "skeleton_walk2": ("skeleton_walk2", "WALK 2", {7, 16, 17, 23, 26, 33, 38, 41}, {}),
    "skeleton_cut": ("skeleton_cut", "CUT (attack)", {8, 25, 26, 32, 34, 40, 42, 44}, {}),
    # GOBLIN 24x32 -> 24x24: head kept (-1 row, top margin -2), body -2, legs -3
    "goblin_walk1": ("goblin_walk1", "WALK 1 (= REST)", {0, 1, 6, 17, 18, 24, 25, 28}, {}),
    "goblin_walk2": ("goblin_walk2", "WALK 2", {0, 5, 16, 17, 23, 26, 27, 29}, {}),
    "goblin_smash": ("goblin_smash", "SMASH (attack)", {0, 1, 6, 17, 18, 24, 25, 28}, {}),
}
KINDS = [("KNIGHT", "knight", "#FFFFFF"), ("WIZARD", "wizard", "#00FFFF"),
         ("SKELETON", "skeleton", "#FFFFFF"), ("GOBLIN", "goblin", "#00FF00")]
# Reference (REST) frame per kind for the head-band anchor of wide attack frames.
REF = {"knight": "knight_idle1", "wizard": "wizard_idle",
       "skeleton": "skeleton_walk1", "goblin": "goblin_walk1"}


def load(name: str):
    bm, meta = ss.read_grid(os.path.join(SRC_DIR, name + ".grid"))
    ax, ay = (int(v) for v in meta.get("anchor", "0 0").split())
    return bm.astype(bool), meta, ax


def shorten(name: str) -> np.ndarray:
    src, _role, drop, edits = SPECS[name]
    bm, _meta, _ax = load(src)
    rows = []
    for y in range(bm.shape[0]):
        if y in drop:
            continue
        if y in edits:
            s = edits[y]
            assert len(s) == bm.shape[1], f"{name}: edit row {y} width"
            rows.append(np.array([c == "#" for c in s]))
        else:
            rows.append(bm[y])
    return np.array(rows, dtype=bool)


def foot_gap(bm: np.ndarray) -> int:
    """Blank rows under the lowest ink row (the foot line's distance to the frame bottom)."""
    ys = np.nonzero(bm.any(axis=1))[0]
    return bm.shape[0] - 1 - ys[-1]


def grid_text(name, bm, solid, caption, ink, ax) -> str:
    h, w = bm.shape
    lines = ["# Tome of the Dead gfx text grid — CONCEPT short sprite, tools/short_sprites_preview.py",
             f"# name: {name}_short", f"# size: {w}x{h}", f"# character: {name.split('_')[0].upper()}",
             f"# caption: {caption} SHORT", f"# ink: {ink}", f"# anchor: {ax} 0",
             f"# source: assets/gfx/sprites/grid/{SPECS[name][0]}.grid (rows dropped: "
             f"{', '.join(map(str, sorted(SPECS[name][2])))})",
             "# legend: '#' ink, '+' opaque paper (mask 0, data 0), '.' transparent", "#"]
    for y in range(h):
        lines.append("".join("#" if bm[y, x] else "+" if solid[y, x] else "." for x in range(w)))
    return "\n".join(lines) + "\n"


def pack_check(name: str, gpath: str, bm, solid, ink: str, td: str) -> list[str]:
    colour, bright = ss.INK_MAP[ink]
    out = os.path.join(td, name + ".asm")
    argv = ["--mode", "sprite", "--layout", "native", "--in", gpath, "--name", name + "_short",
            "--out", out, "--ink", gfx_convert.COL_NAME[colour], "--paper", "black",
            "--band-paper", "black", "--date", "concept"] + (["--bright"] if bright else [])
    try:
        ss._quiet(ss.run_gfx, argv)
    except SystemExit as e:
        return [f"{name}: {e}"]
    rows, _attr = ss.decode_asm(out)
    fg, sol = gfx_convert.unpack_sprite_mask(rows, bm.shape[1], "native")
    errs = []
    if not np.array_equal(fg, bm):
        errs.append(f"{name}: round-trip data mismatch")
    if not np.array_equal(sol, solid):
        errs.append(f"{name}: round-trip mask mismatch")
    return errs


# --- memory accounting (src/defs.asm FRM macro POOLACC, PHASE_SHIFT=1) -------------------

def frm_flags() -> dict:
    """frame name -> (MOT, SYM, PH4) from src/frames.asm (read-only)."""
    out = {}
    for line in open(os.path.join(REPO, "src/frames.asm")):
        m = re.match(r"\s*FRM\s+(\w+),\s*K_\w+,\s*(\d+),\s*([\w|]+)", line)
        if m:
            fl = m.group(3).split("|")
            out[m.group(1)] = ("MOT" in fl, "SYM" in fl, "WK4" in fl, int(m.group(2)))
    return out


def pool_bytes(h, cols, w, ax, bw, mot, sym, ph4) -> int:
    if mot:
        return (1 if sym else 2) * h * 2 * (2 * cols + 1)
    p = 4 if ph4 else 0
    n = h * 2 * (cols + (1 if (ax + p) & 7 else 0))
    if not sym:
        n += h * 2 * (cols + (1 if (w - ax - bw + p) & 7 else 0))
    return n


def src_bytes(h, cols) -> int:
    return h * cols * 2 + 1          # [mask,data] x cols x rows + ATTR descriptor


def asm_dims(name: str):
    t = open(os.path.join(REPO, "assets/gfx/sprites", name + ".asm")).read()
    g = {k: int(re.search(rf"^{name}_{k}\s+EQU\s+(\d+)", t, re.M).group(1))
         for k in ("w", "h", "cols", "ax")}
    return g


def kind_totals(prefix: str, cut: int, flags: dict):
    """(current, short) source and pool bytes of the whole kind if every frame of the
    kind's tallest height loses `cut` rows (shorter frames, e.g. DEAD, unchanged)."""
    names = [n for n in flags if n.startswith(prefix + "_")]
    dims = {n: asm_dims(n) for n in names}
    hmax = max(d["h"] for d in dims.values())
    s0 = s1 = p0 = p1 = 0
    for n in names:
        d = dims[n]
        mot, sym, ph4, bw = flags[n]
        h1 = d["h"] - cut if d["h"] == hmax else d["h"]
        s0 += src_bytes(d["h"], d["cols"])
        s1 += src_bytes(h1, d["cols"])
        p0 += pool_bytes(d["h"], d["cols"], d["w"], d["ax"], bw, mot, sym, ph4)
        p1 += pool_bytes(h1, d["cols"], d["w"], d["ax"], bw, mot, sym, ph4)
    return len(names), hmax, s0, s1, p0, p1


# --- HTML ------------------------------------------------------------------------------

def svg(bm, solid, ink, scale, show_mask=False, box_h=None, line_at=None) -> str:
    h, w = bm.shape
    bh = box_h or h
    oy = bh - h                                   # bottom-align (feet on the same line)
    parts = [f'<svg width="{w * scale}" height="{bh * scale}" viewBox="0 0 {w} {bh}" '
             f'shape-rendering="crispEdges" style="display:block;">',
             f'<rect width="{w}" height="{bh}" fill="#000000"></rect>']
    if scale > 1:
        cells = "".join(f"M{x} 0V{bh}" for x in range(8, w, 8))
        cells += "".join(f"M0 {y}H{w}" for y in range(bh - 8, 0, -8))
        parts.append(f'<path d="{cells}" stroke="#2a2a44" stroke-width="0.12" fill="none"></path>')
    if show_mask:
        m = solid & ~bm
        mp = ss.bitmap_to_path(np.pad(m, ((oy, 0), (0, 0))))
        if mp:
            parts.append(f'<path d="{mp}" fill="#2c2c3c"></path>')
    parts.append(f'<path d="{ss.bitmap_to_path(np.pad(bm, ((oy, 0), (0, 0))))}" fill="{ink}"></path>')
    if line_at is not None:
        parts.append(f'<path d="M0 {line_at}H{w}" stroke="#ff5050" stroke-width="0.25" '
                     f'stroke-dasharray="1 1" fill="none"></path>')
    parts.append("</svg>")
    return "".join(parts)


def figure(inner: str, cap: str, note: str = "") -> str:
    s = ('<div style="display:flex;flex-direction:column;gap:8px;align-items:flex-start;">'
         f'<div style="padding:8px;background:#000000;border:2px solid #26263a;">{inner}</div>'
         f'<div style="font-size:11px;letter-spacing:1px;color:#a9a7b8;">{cap}</div>')
    if note:
        s += f'<div style="font-size:10px;color:#77758a;max-width:220px;line-height:1.5;">{note}</div>'
    return s + "</div>"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--png")
    a = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)
    flags = frm_flags()
    errs, res = [], {}
    with tempfile.TemporaryDirectory() as td:
        for name, (src, role, drop, _e) in SPECS.items():
            kind = name.split("_")[0]
            ink = next(i for _, p, i in KINDS if p == kind)
            bm0, meta, ax0 = load(src)
            bm1 = shorten(name)
            want = bm0.shape[0] - 8
            if bm1.shape != (want, bm0.shape[1]):
                errs.append(f"{name}: {bm1.shape} != {(want, bm0.shape[1])}")
                continue
            if foot_gap(bm1) != foot_gap(bm0):
                errs.append(f"{name}: foot line moved ({foot_gap(bm0)} -> {foot_gap(bm1)})")
            res[name] = dict(bm0=bm0, bm1=bm1, sol0=ss.make_mask(bm0, True),
                             sol1=ss.make_mask(bm1, True), ink=ink, ax0=ax0, role=role)
        for name, r in res.items():
            kind = name.split("_")[0]
            ref = res[REF[kind]]["bm1"]
            ax1 = ss.best_anchor(ref, r["bm1"])[0] if r["bm1"].shape != ref.shape else 0
            r["ax1"] = ax1
            gpath = os.path.join(OUT_DIR, name + "_short.grid")
            with open(gpath, "w") as f:
                f.write(grid_text(name, r["bm1"], r["sol1"], r["role"], r["ink"], ax1))
            errs += pack_check(name, gpath, r["bm1"], r["sol1"], r["ink"], td)
    if errs:
        print("\n".join("ERROR: " + e for e in errs), file=sys.stderr)
        sys.exit(1)
    print(f"OK: {len(res)} frames, clash + round-trip (data+mask) + foot line")

    css = ("font-family:'Press Start 2P',monospace;background:#12121c;color:#e6e4f0;"
           "padding:24px;display:flex;flex-direction:column;gap:28px;")
    h = [f'<div style="{css}">',
         '<h2 style="margin:0;font-size:14px;">SHORT SPRITES CONCEPT (DRAFT FOR REVIEW)</h2>',
         '<div style="font-size:10px;color:#a9a7b8;max-width:1100px;line-height:1.7;">'
         'CURRENT vs SHORT (8 px shorter, same width). Redrawn by removing rows at joints '
         '(helmet/hat, beard, torso, shield, robe, thigh, shin, boot) &mdash; no squash, no crop; '
         'feet stay on the bottom line. Boxes are bottom-aligned at the old height; the red '
         'dashed line marks the SHORT top. Dim grey = opaque mask paper (1-px outline). '
         'Goblin is already 24&times;32 in the build (BH 4), so its SHORT is 24&times;24. '
         'Single ink on black per frame: clash-legal by construction, packed + round-tripped '
         'through gfx_convert.py --layout native.</div>']
    mem_rows = []
    for title, prefix, ink in KINDS:
        names = [n for n in SPECS if n.startswith(prefix + "_")]
        h += [f'<h2 style="margin:0;font-size:12px;">{title} · x4</h2>',
              '<div style="display:flex;gap:28px;flex-wrap:wrap;align-items:flex-end;">']
        for n in names:
            r = res[n]
            H0, W = r["bm0"].shape
            H1 = r["bm1"].shape[0]
            cols = W // 8
            f = flags[SPECS[n][0]]
            d = asm_dims(SPECS[n][0])
            s0, s1 = src_bytes(H0, cols), src_bytes(H1, cols)
            p0 = pool_bytes(H0, cols, W, d["ax"], f[3], f[0], f[1], f[2])
            p1 = pool_bytes(H1, cols, W, r["ax1"], f[3], f[0], f[1], f[2])
            cls = "MOT" if f[0] else ("WK4" if f[2] else "STA") + ("|SYM" if f[1] else "")
            mem_rows.append((n, r["role"], W, H0, H1, cls, s0, s1, p0, p1, d["ax"], r["ax1"]))
            note = (f"src {s0} &rarr; {s1} B ({s1 - s0:+d}); pool {p0} &rarr; {p1} B "
                    f"({p1 - p0:+d}) [{cls}]; ax {d['ax']}&rarr;{r['ax1']}")
            pair = ('<div style="display:flex;gap:10px;align-items:flex-end;">'
                    + svg(r["bm0"], r["sol0"], ink, 4, True)
                    + svg(r["bm1"], r["sol1"], ink, 4, True, box_h=H0, line_at=H0 - H1)
                    + "</div>")
            h.append(figure(pair, f"{r['role']} · {W}×{H0} | {W}×{H1}", note))
        h.append("</div>")
    # x1 actual size: every frame CURRENT then SHORT, on a floor line
    h += ['<h2 style="margin:0;font-size:12px;">x1 actual size · CURRENT row above, SHORT row '
          'below (bottom-aligned on the floor)</h2>']
    for label, key in (("CURRENT", "bm0"), ("SHORT", "bm1")):
        cells = []
        for n, r in res.items():
            kind = n.split("_")[0]
            ink = next(i for _, p, i in KINDS if p == kind)
            sol = r["sol0" if key == "bm0" else "sol1"]
            cells.append(svg(r[key], sol, ink, 1, False, box_h=48))
        h.append(figure('<div style="display:flex;gap:8px;align-items:flex-end;'
                        'border-bottom:2px solid #3a6ad0;">' + "".join(cells) + "</div>", label))
    # memory table
    th = ('style="text-align:right;padding:4px 10px;border-bottom:1px solid #26263a;"')
    h += ['<h2 style="margin:0;font-size:12px;">MEMORY · per frame (measured)</h2>',
          '<div style="font-size:10px;color:#a9a7b8;max-width:1100px;line-height:1.7;">'
          'src = unpacked source frame = rows &times; cols &times; 2 [mask,data] + 1 ATTR byte '
          '(the build stores it ZX0-packed in banks 1/3, so the packed saving is smaller). '
          'pool = resident pre-shift variants per src/defs.asm FRM / POOLACC with PHASE_SHIFT=1 '
          '(both facings; MOT = shifts 0+4, the shifted copy +1 spill col).</div>',
          '<table style="font-size:10px;border-collapse:collapse;">',
          "<tr>" + "".join(f"<th {th}>{c}</th>" for c in
                           ("frame", "size", "class", "src 48", "src short", "&Delta;",
                            "pool 48", "pool short", "&Delta;")) + "</tr>"]
    for n, role, W, H0, H1, cls, s0, s1, p0, p1, _a0, _a1 in mem_rows:
        h.append("<tr>" + "".join(f"<td {th}>{c}</td>" for c in (
            n, f"{W}×{H0}→{H1}", cls, s0, s1, s1 - s0, p0, p1, p1 - p0)) + "</tr>")
    h.append("</table>")
    h += ['<h2 style="margin:0;font-size:12px;">MEMORY · whole kind if every full-height frame '
          'is shortened by 8 rows</h2>',
          '<table style="font-size:10px;border-collapse:collapse;">',
          "<tr>" + "".join(f"<th {th}>{c}</th>" for c in
                           ("kind", "frames", "full h", "src now", "src short", "&Delta;",
                            "pool now", "pool short", "&Delta;")) + "</tr>"]
    totals = []
    for title, prefix, _ink in KINDS:
        n, hm, s0, s1, p0, p1 = kind_totals(prefix, 8, flags)
        totals.append((title, n, hm, s0, s1, p0, p1))
        h.append("<tr>" + "".join(f"<td {th}>{c}</td>" for c in (
            title, n, f"{hm}→{hm - 8}", s0, s1, s1 - s0, p0, p1, p1 - p0)) + "</tr>")
    h.append("</table>")
    h += ["</div>", ""]
    with open(PAGE, "w") as f:
        f.write("\n".join(h))
    print("wrote", os.path.relpath(PAGE, REPO))
    for row in mem_rows:
        print("  %-18s %2dx%d->%d %-7s src %4d->%4d (%+d)  pool %4d->%4d (%+d)  ax %d->%d" % (
            row[0], row[2], row[3], row[4], row[5], row[6], row[7], row[7] - row[6],
            row[8], row[9], row[9] - row[8], row[10], row[11]))
    for t in totals:
        print("  kind %-8s %2d frames h%d: src %5d->%5d (%+d)  pool %5d->%5d (%+d)" % (
            t[0], t[1], t[2], t[3], t[4], t[4] - t[3], t[5], t[6], t[6] - t[5]))
    if a.png:
        from PIL import Image
        sc, pad = 4, 6
        tiles = []
        for n, r in res.items():
            ink = tuple(int(r["ink"][i:i + 2], 16) for i in (1, 3, 5))
            for key, sk in (("bm0", "sol0"), ("bm1", "sol1")):
                bm, sol = r[key], r[sk]
                img = np.zeros((48, bm.shape[1], 3), np.uint8)
                img[:] = (18, 18, 28)
                oy = 48 - bm.shape[0]
                img[oy:][sol] = (44, 44, 60)
                img[oy:][bm] = ink
                tiles.append(img)
        wtot = sum(t.shape[1] + pad for t in tiles)
        canvas = np.full((48 + 2 * pad, wtot + pad, 3), 60, np.uint8)
        x = pad
        for t in tiles:
            canvas[pad:pad + 48, x:x + t.shape[1]] = t
            x += t.shape[1] + pad
        Image.fromarray(canvas).resize((canvas.shape[1] * sc, canvas.shape[0] * sc),
                                       Image.NEAREST).save(a.png)
        print("png ->", a.png)


if __name__ == "__main__":
    main()
