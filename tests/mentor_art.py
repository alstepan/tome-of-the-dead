#!/usr/bin/env python3
"""mentor_art.py — checks for the mentor (Aldous) art converter and its generated asm.

Covers: image sizes (144 B x N, FRAMES EQU), ink-only data (no attribute bytes),
cell-major round-trip back to the source grids, horizontal-mirror correctness
(POINT_L), the 3/4 variant on synthetic grids, and staleness of the committed asm.

Usage: python3 tests/mentor_art.py     (exit 1 on any failure)
"""
import os
import random
import re
import sys
import tempfile
import unittest

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import mentor_convert as M  # noqa: E402

ASM = os.path.join(M.OUT_DIR, "aldous.asm")
Q34_ASM = os.path.join(M.OUT_DIR, "aldous34.asm")
EXPECT_LABELS = ["sxt_idle1", "sxt_idle2", "sxt_talk1", "sxt_talk2",
                 "sxt_point_l", "sxt_point_r", "sxt_pointdn", "sxt_fade"]


def parse_asm(path):
    """-> (FRAMES value, OrderedDict-like list of (label, bytes)) from a generated asm file."""
    with open(path) as fh:
        text = fh.read()
    m = re.search(r"^SXT(?:34)?_(?:FRAMES|IMAGES)\s+EQU\s+(\d+)", text, re.M)
    frames = int(m.group(1)) if m else None
    images, cur = [], None
    for line in text.splitlines():
        lm = re.match(r"^(\w+):\s*$", line)
        if lm:
            cur = (lm.group(1), bytearray())
            images.append(cur)
            continue
        dm = re.match(r"^\s+DEFB\s+([\$0-9A-Fa-f,\s]+?)\s*(;.*)?$", line)
        if dm and cur is not None:
            for tok in dm.group(1).split(","):
                cur[1].append(int(tok.strip().lstrip("$"), 16))
        else:
            s = line.strip()
            # anything but blank, comment, the FRAMES EQU or a label/DEFB is unexpected
            if s and not s.startswith(";") and "EQU" not in s:
                raise AssertionError(f"unexpected asm line: {line!r}")
    return frames, [(lab, bytes(b)) for lab, b in images]


def bitrev(b):
    return int(f"{b:08b}"[::-1], 2)


class MentorArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames, cls.images = parse_asm(ASM)
        cls.labels = [lab for lab, _ in cls.images]
        cls.data = dict(cls.images)

    # --- sizes -----------------------------------------------------------
    def test_frame_count_equ_matches_images(self):
        self.assertEqual(self.frames, len(self.images))
        self.assertEqual(self.frames, 8)

    def test_labels_in_engine_order(self):
        self.assertEqual(self.labels, EXPECT_LABELS)

    def test_each_image_is_144_bytes(self):
        for lab, data in self.images:
            self.assertEqual(len(data), M.FRAME_BYTES, lab)
        self.assertEqual(M.FRAME_BYTES, 144)

    def test_total_bytes(self):
        self.assertEqual(sum(len(d) for _, d in self.images), 144 * len(EXPECT_LABELS))

    def test_defb_bytes_only_no_stray_data(self):
        # parse_asm raises on unexpected lines; the byte total above proves no extras.
        with open(ASM) as fh:
            text = fh.read()
        defb_bytes = sum(len(re.findall(r"\$[0-9A-Fa-f]{2}", l))
                         for l in text.splitlines() if l.lstrip().startswith("DEFB"))
        self.assertEqual(defb_bytes, 144 * len(EXPECT_LABELS))

    # --- ink-only --------------------------------------------------------
    def test_ink_only_round_trip_is_exact(self):
        """1-bit data: every image decodes to a 24x48 bool bitmap and re-encodes byte-identically.
        Any attribute byte would break the 8-pixel-per-byte cell mapping and this round trip."""
        for lab, data in self.images:
            bm = M.decode(data)
            self.assertEqual(bm.shape, (48, 24), lab)
            self.assertEqual(M.encode(bm), data, lab)

    def test_no_per_cell_colour_fields(self):
        # 18 cells x 8 B per image: no 19th byte per cell, no trailing attr byte.
        for lab, data in self.images:
            self.assertEqual(len(data) % 8, 0, lab)
            self.assertEqual(len(data) // 8, 18, lab)

    # --- round trip to source grids -------------------------------------
    def test_round_trip_to_grids(self):
        for im in M.FRONT_IMAGES:
            src = M.load_grid(os.path.join(M.SRC, im.grid))
            want = M.mirror(src) if im.mirror else src
            got = M.decode(self.data[im.label])
            self.assertTrue(np.array_equal(got, want), im.label)

    # --- mirror ----------------------------------------------------------
    def test_point_l_is_mirror_of_point_r(self):
        pl = M.decode(self.data["sxt_point_l"])
        pr = M.decode(self.data["sxt_point_r"])
        self.assertTrue(np.array_equal(pl, pr[:, ::-1]))
        self.assertFalse(np.array_equal(pl, pr), "POINT_L == POINT_R: mirror not applied")

    def test_mirror_bytes_are_cell_swap_plus_bit_reverse(self):
        """Mirroring a 3-cell-wide image = swap cols c0<->c2 in each row and bit-reverse
        every byte (bit 7 is the leftmost pixel)."""
        rng = random.Random(1234)
        bm = np.array([[rng.random() < 0.5 for _ in range(24)] for _ in range(48)], dtype=bool)
        data = M.encode(bm)
        mir = M.encode(M.mirror(bm))
        for r in range(6):
            for c in range(3):
                src_cell = data[(r * 3 + (2 - c)) * 8:(r * 3 + (2 - c)) * 8 + 8]
                got_cell = mir[(r * 3 + c) * 8:(r * 3 + c) * 8 + 8]
                self.assertEqual(got_cell, bytes(bitrev(b) for b in src_cell), f"r{r}c{c}")

    def test_mirror_is_involution(self):
        rng = random.Random(7)
        bm = np.array([[rng.random() < 0.3 for _ in range(24)] for _ in range(48)], dtype=bool)
        self.assertTrue(np.array_equal(M.mirror(M.mirror(bm)), bm))

    # --- layout ----------------------------------------------------------
    def test_cell_major_layout_single_pixel(self):
        bm = np.zeros((48, 24), dtype=bool)
        bm[9, 17] = True                  # row 1 (r1), col 2 (c2): cell index 1*3+2 = 5
        data = M.encode(bm)                 # byte 1 of the cell (y=9 -> y%8=1), bit x%8=1 -> 0x40
        nz = [(i, b) for i, b in enumerate(data) if b]
        self.assertEqual(nz, [(5 * 8 + 1, 0x40)])

    def test_encode_decode_inverse_random(self):
        rng = random.Random(99)
        data = bytes(rng.randrange(256) for _ in range(144))
        self.assertEqual(M.encode(M.decode(data)), data)

    # --- 3/4 variant ----------------------------------------------------
    def test_q34_committed_asm(self):
        frames, images = parse_asm(Q34_ASM)
        self.assertEqual(frames, 7)
        self.assertEqual(len(images), 7)
        want = [f"sxt34_{f}_r" for f in M.Q34_FRAMES]
        self.assertEqual([lab for lab, _ in images], want)
        self.assertEqual(sum(len(d) for _, d in images), 1008)
        data = dict(images)
        for f in M.Q34_FRAMES:
            r = M.decode(data[f"sxt34_{f}_r"])
            src = M.load_grid(os.path.join(M.SRC, "q34", f"sxt34_{f}.grid"))
            self.assertTrue(np.array_equal(r, src), f"{f}: R != q34 grid")

    def test_q34_synthetic_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            rng = random.Random(5)
            for f in M.Q34_FRAMES:
                rows = ["".join("#" if rng.random() < 0.4 else "." for _ in range(24))
                        for _ in range(48)]
                with open(os.path.join(tmp, f"sxt34_{f}.grid"), "w") as fh:
                    fh.write("# ink: #00D7D7\n" + "\n".join(rows) + "\n")
            out = os.path.join(tmp, "aldous34.asm")
            self.assertEqual(M.main(["--variant", "34", "--src", tmp, "--out", out]), 0)
            frames, images = parse_asm(out)
            self.assertEqual(frames, 7)
            self.assertEqual(len(images), 7)
            self.assertTrue(all(len(d) == 144 for _, d in images))
            self.assertEqual(images[0][0], "sxt34_idle1_r")
            self.assertEqual(images[1][0], "sxt34_idle2_r")
            src = M.load_grid(os.path.join(tmp, "sxt34_idle1.grid"))
            self.assertTrue(np.array_equal(M.decode(images[0][1]), src))

    def test_bad_ink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "bad.grid")
            with open(p, "w") as fh:
                fh.write("# ink: #FF0000\n" + "\n".join(["#" * 24] * 48) + "\n")
            with self.assertRaises(ValueError):
                M.load_grid(p)

    def test_bad_size_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "small.grid")
            with open(p, "w") as fh:
                fh.write("# ink: #00D7D7\n" + "\n".join(["#" * 24] * 40) + "\n")
            with self.assertRaises(ValueError):
                M.load_grid(p)

    # --- freshness -------------------------------------------------------
    def test_committed_asm_is_fresh(self):
        self.assertEqual(M.main(["--check"]), 0)

    def test_committed_q34_asm_is_fresh(self):
        self.assertEqual(M.main(["--variant", "34", "--check"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=1, exit=True)
