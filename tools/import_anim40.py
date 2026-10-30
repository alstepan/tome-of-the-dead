#!/usr/bin/env python3
"""import_anim40.py — ANIM-IMPORT2 (2026-10-30): the user-picked 40-px frames that
are not already engine asm in assets/gfx/sprites40/ -> engine sprite sources there.

ART11 (branch feat/3f-art11-40px b2178b2) shipped native asm for the heroes, the
Skeleton family, the Orc V4 and the shared climb pair; this tool adds
  * ART12 PICKS (09f1870, board F3l): Mage HURT V3 (stagger), Mummy V2 (tomb
    guard), Necromancer V2 (bone caster): assets/gfx/sprites40/art12/grid/*_v<n>.grid;
  * the Vampire's own 40-px set (ART9 APPROVED, feat/3f-art9-final d75a366):
    assets/gfx/concept/art9_final/grid/vamp_*.grid (wired first on wip/anim-orc-vamp
    0390ff7 by tools/import_art9.py).
Each grid is copied to assets/gfx/sprites40/grid/<name>.grid (header: engine source)
and converted with tools/gfx_convert.py --layout native (clash + round-trip checked)
to assets/gfx/sprites40/<name>.asm; the build takes it once <name> is listed in
assets/gfx/sprites40/index40.asm (tools/zx0_pack.py sprite_asm). Frames are 40 rows,
bottom-anchored on the 48-row body (FRM: fpy = py + BH * 8 - H): 8 px lower, no pad.

Usage: python3 tools/import_anim40.py mage|mummy|necro|vamp
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART12 = "assets/gfx/sprites40/art12/grid"
ART9 = "assets/gfx/concept/art9_final/grid"
GRID = os.path.join(REPO, "assets/gfx/sprites40/grid")
SPR40 = os.path.join(REPO, "assets/gfx/sprites40")

# set: (ink, bright, src dir, {engine name: (source grid, anchor-x, flag note)})
SETS = {
    "mage": ("cyan", True, ART12, {"wizard_hurt": ("wizard_hurt_v3", 8, "HURT V3 stagger, STA")}),
    "mummy": ("yellow", False, ART12, {
        "mummy_walk1": ("mummy_walk1_v2", 0, "WK0 rest"), "mummy_walk2": ("mummy_walk2_v2", 0, "WK4"),
        "mummy_walk3": ("mummy_walk3_v2", 0, "WK4"), "mummy_walk4": ("mummy_walk4_v2", 0, "WK0"),
        "mummy_attack": ("mummy_attack_v2", 0, "STA")}),
    "necro": ("magenta", False, ART12, {
        "necro_walk1": ("necro_walk1_v2", 0, "WK0 rest"), "necro_walk2": ("necro_walk2_v2", 0, "WK4"),
        "necro_walk3": ("necro_walk3_v2", 0, "WK4"), "necro_walk4": ("necro_walk4_v2", 0, "WK0"),
        "necro_cast": ("necro_cast_v2", 0, "STA")}),
    "vamp": ("cyan", False, ART9, {
        "vamp_walk1": ("vamp_walk1", 0, "WK0 rest"), "vamp_walk2": ("vamp_walk2", 0, "WK4"),
        "vamp_walk3": ("vamp_walk3", 0, "WK4"), "vamp_bite": ("vamp_bite", 0, "STA"),
        "vamp_hurt": ("vamp_hurt", 0, "STA")}),
}
PICK = {"mage": "ART12 pick: Mage HURT V3 stagger", "mummy": "ART12 pick: Mummy V2 tomb guard",
        "necro": "ART12 pick: Necromancer V2 bone caster", "vamp": "ART9 final: the Vampire's own 40-px set"}


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in SETS:
        sys.exit(__doc__)
    key = sys.argv[1]
    ink, bright, src, frames = SETS[key]
    os.makedirs(GRID, exist_ok=True)
    for name, (sname, ax, flag) in frames.items():
        lines = open(os.path.join(REPO, src, sname + ".grid")).read().split("\n")
        assert lines[0].startswith("# WazHack/ZX gfx text grid"), sname
        assert any(ln.startswith("# size:") and ln.endswith("x40") for ln in lines), sname
        lines[0] = (f"# WazHack/ZX gfx text grid — {PICK[key]} (user 2026-10-30); from "
                    f"{src}/{sname}.grid; imported by tools/import_anim40.py (ANIM-IMPORT2)")
        lines = [f"# name: {name}" if ln.startswith("# name:") else ln for ln in lines]
        g = os.path.join(GRID, name + ".grid")
        open(g, "w").write("\n".join(lines))
        cmd = [sys.executable, os.path.join(REPO, "tools/gfx_convert.py"),
               "--in", os.path.relpath(g, REPO), "--src-path", "--name", name,
               "--out", os.path.join(SPR40, name + ".asm"), "--layout", "native",
               "--ink", ink, "--anchor-x", str(ax), "--date", "2026-10-30",
               "--note", f"{PICK[key]} ({flag}); tools/import_anim40.py (ANIM-IMPORT2)"]
        if bright:
            cmd.append("--bright")
        subprocess.run(cmd, check=True, cwd=REPO)


if __name__ == "__main__":
    main()
