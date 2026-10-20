#!/usr/bin/env python3
"""3E-T5: pure-Python unit tests for tools/items_model.py (no emulator, no build).
Run: python3 tests/items_model_test.py   (exit 0 = all pass)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import decorgen  # noqa: E402
import items_model as M  # noqa: E402
import levelgen as G  # noqa: E402

D = G.D


def level(master, d):
    return G.generate(d, M.level_seed(master, d), master)


class ItemsModel(unittest.TestCase):
    def test_rng_matches_gen_algorithm(self):
        r = M.item_rng(0x1234, 3)
        g = G.Rng(M.level_seed(0x1234, 3 | 0x80), 3 | 0x80)
        self.assertEqual([r.rnd(200) for _ in range(20)], [g.rnd(200) for _ in range(20)])
        self.assertNotEqual(M.item_rng(0x1234, 3).x, G.Rng(M.level_seed(0x1234, 3), 3).x)
        self.assertNotEqual(M.item_rng(5, 1).x, M.id_rng(5).x)
        self.assertTrue(M.item_rng(0, 1).x != 0)

    def test_determinism(self):
        for m in (0, 1, 777, 0xFFFF):
            for d in range(1, 9):
                b = level(m, d)
                for h in (M.HERO_WARRIOR, M.HERO_MAGE):
                    a, c = M.gen_level_items(b, m, h), M.gen_level_items(b, m, h)
                    self.assertEqual(M.apply_block(b, a), M.apply_block(b, c))

    def test_light_id_map(self):
        for m in range(300):
            mp = M.light_id_map(m)
            self.assertEqual(len(mp), D["ID_TYPES"])
            self.assertEqual(len(set(mp[:3])), 3)
            self.assertEqual(len(set(mp[3:])), 4)
            self.assertTrue(max(mp[:3]) < D["ID_POT_APP"] and max(mp[3:]) < D["ID_SCR_APP"])
        self.assertGreater(len({tuple(M.light_id_map(m)) for m in range(300)}), 100)

    def test_independent_of_gen_streams(self):
        """Generating items must not change level / decor output (8.11 Q8)."""
        flat0 = [0] * (32 * D["PLAY_ROWS"])
        for m in (3, 99, 4242):
            for d in range(1, 9):
                b = level(m, d)
                dec = decorgen.decorate(list(flat0), d, 0x1357 ^ m)
                lg = (G.LAST, G.LAIR_RESEEDS)
                for h in (M.HERO_WARRIOR, M.HERO_MAGE):
                    lvl = M.gen_level_items(b, m, h)
                    nb, _ = M.apply_block(b, lvl)
                    # only FLOOR_LIST/FLOOR_N/TRAP bytes may differ
                    diff = [i for i in range(len(b)) if b[i] != nb[i]]
                    ok = lambda i: (G.OFF_FLOOR <= i < G.OFF_FLOOR + 128 or i == G.H["FLOOR_N"]
                                    or M.OFF_TRAP <= i <= M.OFF_TRAPN)
                    self.assertTrue(all(ok(i) for i in diff))
                self.assertEqual(level(m, d), b)
                self.assertEqual(decorgen.decorate(list(flat0), d, 0x1357 ^ m), dec)
                self.assertEqual((G.LAST, G.LAIR_RESEEDS), lg)

    def test_invariants_small_sweep(self):
        bad, st = M.sweep((range(0, 2000, 3), range(1, 9)))
        self.assertEqual(bad, [])
        self.assertEqual(st["ids_bad"], 0)

    def test_books_bow_traps(self):
        n_book2 = n_d47 = 0
        for m in range(400):
            for d in range(1, 9):
                b = level(m, d)
                w = M.gen_level_items(b, m, M.HERO_WARRIOR)
                mg = M.gen_level_items(b, m, M.HERO_MAGE)
                books = sum(e[2] == M.IT_BOOK for e in w.floor)
                self.assertEqual(books, sum(e[2] == M.IT_BOOK for e in mg.floor) or books)
                if d == 8:
                    self.assertEqual(books, 0)
                elif d < 4:
                    self.assertLessEqual(books, 1)
                else:
                    self.assertIn(books, (0, 1, 2))
                    n_d47 += 1
                    n_book2 += books == 2
                self.assertEqual(sum(e[2] == M.IT_BOW for e in w.floor), 1 if d == 2 else 0)
                self.assertEqual(sum(e[2] == M.IT_BOW for e in mg.floor), 0)
                self.assertEqual(len(w.fl_ist()), 32)
        self.assertTrue(0.4 < n_book2 / n_d47 < 0.6, n_book2 / n_d47)

    def test_cursed_values(self):
        seen = {}
        for m in range(600):
            for d in (1, 5, 8):
                b = level(m, d)
                for e, s in zip(*[(l := M.gen_level_items(b, m, M.HERO_MAGE)).floor, l.ist]):
                    if s & 3 == 2:
                        seen.setdefault(d, set()).add(M.ist_m(s))
        self.assertEqual(seen[1], {-1, 1})
        self.assertEqual(seen[5], {-2, -1, 1, 2})


if __name__ == "__main__":
    unittest.main(verbosity=1)
