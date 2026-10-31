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

ANIM-X12 (X1 / X2, user 2026-10-30): `orcx` / `vampx` import the 4-pose walk W2 W1 W3 W4 from
assets/gfx/sprites40/extra/grid (tools/gen_art11_extra.py): W2 / W3 replace the existing frames
(far foot re-placed), W4 is the new WK0 frame <name>_walk4; W1 (= walk1, the rest pose) is unchanged.

3F-T11 (`nun`, user 2026-10-30 NUN ARCHMAGE APPROVED): the Archmage's own four frames from
assets/gfx/concept/art13/grid (tools/gen_art13c_nun.py, ART13c option D): nun_walk1 WK0,
nun_walk2 WK4, nun_cast / nun_hurt STA (ink green = KT_ATTR $04).

3F-PHARAOH (`pharaoh`, user 2026-10-31 GOLDEN PHARAOH option A NEMES KING): replaces the five Mummy
frames in place (same names / slots / sizes / flags / ink; all Mummies, gold included) from
assets/gfx/concept/art16/grid/pharaoh_*_a.grid (tools/gen_art16.py). Supersedes `mummy`.

ART19-IMPORT (`ghost_h`, user 2026-10-31 GHOST option H WISP SHROUD): replaces the five Ghost frames in
place (assets/gfx/sprites/, 32-px set; same names / sizes 24x32 + lunge 32x32 / flags / ax 0 / ink cyan
bright $45) from assets/gfx/concept/art19/grid/ghost_*_h.grid (tools/gen_art19b.py). The Poltergeist /
golden variants keep their attr-only differences.

Usage: python3 tools/import_anim40.py mage|mummy|necro|vamp|orcx|vampx|nun|pharaoh|ghost_h
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART12 = "assets/gfx/sprites40/art12/grid"
ART9 = "assets/gfx/concept/art9_final/grid"
EXTRA = "assets/gfx/sprites40/extra/grid"
ART13 = "assets/gfx/concept/art13/grid"
ART16 = "assets/gfx/concept/art16/grid"
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
    "orcx": ("green", False, EXTRA, {
        "orc_walk2": ("orc_x1_w2", 0, "WK4"), "orc_walk3": ("orc_x1_w3", 0, "WK4"),
        "orc_walk4": ("orc_x1_w4", 0, "WK0")}),
    "vampx": ("cyan", False, EXTRA, {
        "vamp_walk2": ("vamp_x2_w2", 0, "WK4"), "vamp_walk3": ("vamp_x2_w3", 0, "WK4"),
        "vamp_walk4": ("vamp_x2_w4", 0, "WK0")}),
    "nun": ("green", False, ART13, {
        "nun_walk1": ("nun_walk1", 0, "WK0 rest"), "nun_walk2": ("nun_walk2", 0, "WK4"),
        "nun_cast": ("nun_cast", 0, "STA"), "nun_hurt": ("nun_hurt", 0, "STA")}),
    "pharaoh": ("yellow", False, ART16, {
        "mummy_walk1": ("pharaoh_walk1_a", 0, "WK0 rest"), "mummy_walk2": ("pharaoh_walk2_a", 0, "WK4"),
        "mummy_walk3": ("pharaoh_walk3_a", 0, "WK4"), "mummy_walk4": ("pharaoh_walk4_a", 0, "WK0"),
        "mummy_attack": ("pharaoh_attack_a", 0, "STA")}),
}
PICK = {"mage": "ART12 pick: Mage HURT V3 stagger", "mummy": "ART12 pick: Mummy V2 tomb guard",
        "necro": "ART12 pick: Necromancer V2 bone caster", "vamp": "ART9 final: the Vampire's own 40-px set",
        "orcx": "ANIM-X12 X1: Orc 4-pose walk W2 W1 W3 W4", "vampx": "ANIM-X12 X2: Vampire 4-pose walk W2 W1 W3 W4",
        "pharaoh": "ART16 pick: Golden Pharaoh option A Nemes King (all Mummies)",
        "nun": "ART13c final: the nun Archmage (option D, side cast; 3F-T11)"}


def ghost_h():
    """ART19 Ghost option H -> assets/gfx/sprites/ghost_<f>.asm (the 32-px set, like import_ogre_a.py)."""
    src, dst = "assets/gfx/concept/art19/grid", "assets/gfx/sprites"
    for f in ("float1", "float2", "lunge", "hurt", "dead"):
        s = f"{src}/ghost_{f}_h.grid"
        lines = open(os.path.join(REPO, s)).read().split("\n")
        assert lines[0].startswith("# WazHack/ZX gfx text grid"), s
        lines[0] = ("# WazHack/ZX gfx text grid — ART19 Ghost option H (Wisp Shroud), user-approved "
                    f"2026-10-31; from {s}; imported by tools/import_anim40.py ghost_h")
        lines = [f"# name: ghost_{f}" if ln.startswith("# name:") else ln for ln in lines]
        lines = [ln for ln in lines if not ln.startswith("# note:")]
        g = f"{dst}/grid/ghost_{f}.grid"
        open(os.path.join(REPO, g), "w").write("\n".join(lines))
        subprocess.run([sys.executable, "tools/gfx_convert.py", "--mode", "sprite", "--layout", "native",
                        "--in", g, "--name", f"ghost_{f}", "--out", f"{dst}/ghost_{f}.asm",
                        "--ink", "cyan", "--bright", "--paper", "black", "--band-paper", "black",
                        "--anchor-x", "0", "--anchor-y", "0", "--src-path", "--date", "2026-10-31",
                        "--note", "ART19 Ghost option H Wisp Shroud (approved); tools/import_anim40.py ghost_h"],
                       check=True, cwd=REPO)


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "ghost_h":
        return ghost_h()
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
        lines = [ln for ln in lines if not (ln.startswith("# note:") and "not imported" in ln)]
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
