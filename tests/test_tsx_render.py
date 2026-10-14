"""Unit tests for tools/tsx_render.py. Run: python3 -I tests/test_tsx_render.py"""
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import tsx_render as T  # noqa: E402


class Tests(unittest.TestCase):
    def test_gain_envelope_hand_computed(self):
        # One A note held: target = AY[13]*0.28 = 0.74*0.28 = 0.2072, tau 6 ms.
        notes = [{"pitch": "A4", "midi": 69, "beats": 4.0, "stac": False}]
        f, g, tau = T.frame_targets(notes, "A", 60, 10)
        self.assertAlmostEqual(g[0], 0.2072)
        gs = T.settarget_track(g, tau, 0.0)
        for n in (0, 100, 735, 3000):  # inside and across frame boundaries
            want = 0.2072 * (1 - math.exp(-n / (0.006 * T.SR)))
            self.assertAlmostEqual(gs[n], want, places=9)
        # bass channel C uses level 14 -> 0.88*0.28
        _, gc, _ = T.frame_targets(notes, "C", 60, 1)
        self.assertAlmostEqual(gc[0], 0.88 * 0.28)

    def test_staccato_gate(self):
        notes = [{"pitch": "A4", "midi": 69, "beats": 1.0, "stac": True}]
        f, g, tau = T.frame_targets(notes, "A", 60, 60)  # 1 beat/s, frame = 1/60 beat
        self.assertGreater(g[26], 0)       # progress 26/60 = 0.433 <= 0.45
        self.assertGreater(g[27], 0)       # 0.45 exactly is not > 0.45
        self.assertEqual(g[28], 0)         # 0.467 > 0.45 -> cut
        self.assertEqual(f[28], 440.0)     # pitch still tracked
        self.assertEqual(g[59], 0)

    def test_rest_and_end(self):
        notes = [{"pitch": "R", "midi": None, "beats": 1.0, "stac": False}]
        f, g, tau = T.frame_targets(notes, "A", 60, 70)
        self.assertTrue(np.isnan(f[0]) and g[0] == 0 and tau[0] == T.TAU_REST)
        self.assertTrue(np.isnan(f[65]) and g[65] == 0)

    def test_frequency_portamento(self):
        fs = T.settarget_track(np.array([880.0, 880.0]), np.array([T.TAU_NOTE] * 2), 440.0)
        self.assertAlmostEqual(fs[300], 880 - 440 * math.exp(-300 / (0.006 * T.SR)), places=9)

    def test_oscillators(self):
        f = np.full(T.SR, 441.0)  # 100 samples/period exactly
        tri = T.oscillator("tri", f)
        self.assertAlmostEqual(tri[24], 1.0, places=6)   # phase is (n+1)/100 -> peak at 24
        self.assertAlmostEqual(tri[74], -1.0, places=6)
        saw = T.oscillator("saw", f)
        self.assertLess(abs(saw[0]), 0.1)                # phase 0 -> ~0
        self.assertAlmostEqual(saw[24], 0.48, delta=0.05)  # rising (p~.25 -> .5)
        self.assertLess(saw[60], 0)                      # past the jump
        sq = T.oscillator("square", f)
        self.assertAlmostEqual(sq[25], 1.0, places=6)
        self.assertAlmostEqual(sq[75], -1.0, places=6)
        self.assertLessEqual(np.max(np.abs(sq)), 1.2)

    def test_pan_law(self):
        l, r = T.panner_gains(0.0)
        self.assertAlmostEqual(l, math.sqrt(0.5)); self.assertAlmostEqual(r, math.sqrt(0.5))
        l, r = T.panner_gains(-1.0)
        self.assertAlmostEqual(l, 1.0); self.assertAlmostEqual(r, 0.0)

    def test_lowpass_dc_gain_unity(self):
        self.assertAlmostEqual(float(T.lowpass_ir(8000, 0.7).sum()), 1.0, places=6)

    def test_ir_normalised_and_seeded(self):
        a, b = T.make_ir(5), T.make_ir(5)
        self.assertTrue(np.array_equal(a, b))
        self.assertEqual(a.shape, (2, int(T.SR * 2.8)))
        self.assertAlmostEqual(math.sqrt(float(np.mean(a ** 2))), 0.00125, places=7)


if __name__ == "__main__":
    unittest.main()
