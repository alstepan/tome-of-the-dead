#!/usr/bin/env python3
"""import_ogre_a.py — ART16 Ogre option A (Club Brute, user-approved 2026-10-31).

Drop-in replacement of the four Ogre frames (same names / sizes / flags / ax 0):
assets/gfx/concept/art16/grid/ogre_<f>_a.grid -> assets/gfx/sprites/grid/ogre_<f>.grid
-> tools/gfx_convert.py --layout native (clash + round-trip checked) ->
assets/gfx/sprites/ogre_<f>.asm.  Only the Ogre; the Pharaoh options are not imported.
Usage: python3 tools/import_ogre_a.py
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = "assets/gfx/concept/art16/grid"
DST = "assets/gfx/sprites"
FRAMES = ("raise", "slam", "walk1", "walk2")


def main():
    for f in FRAMES:
        src = f"{SRC}/ogre_{f}_a.grid"
        lines = open(os.path.join(REPO, src)).read().split("\n")
        assert lines[0].startswith("# WazHack/ZX gfx text grid"), src
        lines[0] = (f"# WazHack/ZX gfx text grid — ART16 Ogre option A (Club Brute), user-approved "
                    f"2026-10-31; from {src}; imported by tools/import_ogre_a.py")
        lines = [f"# name: ogre_{f}" if ln.startswith("# name:") else ln for ln in lines]
        lines = [f"# caption: {f.upper()}" if ln.startswith("# caption:") else ln for ln in lines]
        lines = [ln for ln in lines if not ln.startswith("# note:")]
        g = f"{DST}/grid/ogre_{f}.grid"
        open(os.path.join(REPO, g), "w").write("\n".join(lines))
        subprocess.run([sys.executable, "tools/gfx_convert.py", "--mode", "sprite", "--layout", "native",
                        "--in", g, "--name", f"ogre_{f}", "--out", f"{DST}/ogre_{f}.asm",
                        "--ink", "green", "--paper", "black", "--band-paper", "black",
                        "--anchor-x", "0", "--anchor-y", "0", "--src-path", "--date", "2026-10-31",
                        "--note", "ART16 Ogre option A Club Brute (approved); tools/import_ogre_a.py"],
                       check=True, cwd=REPO)


if __name__ == "__main__":
    main()
