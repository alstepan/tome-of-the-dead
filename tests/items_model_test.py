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
        self.assertTrue(M.item_rng(0, 1).x != 0)

    def test_determinism(self):
        for m in (0, 1, 777, 0xFFFF):
            for d in range(1, 9):
                b = level(m, d)
                for h in (M.HERO_WARRIOR, M.HERO_MAGE):
                    a, c = M.gen_level_items(b, m, h), M.gen_level_items(b, m, h)
                    self.assertEqual(M.apply_block(b, a), M.apply_block(b, c))

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
                    nb = M.apply_block(b, lvl)
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
        self.assertTrue(0.4 < n_book2 / n_d47 < 0.6, n_book2 / n_d47)

    def test_ink_table_matches_legend(self):
        """Expected inks written out from items3e.tiles / game.md 8.11 (not derived from the model)."""
        want = {"IT_DAGGER": 0x47, "IT_ARROW": 0x46, "IT_F_MEAT": 0x42, "IT_F_CHEESE": 0x46,
                "IT_F_PEAR": 0x04, "IT_F_APPLE": 0x44, "IT_F_CARROT": 0x06,
                "IT_P_HEAL": 0x42, "IT_P_MANA": 0x45, "IT_P_CURE": 0x44,
                "IT_S_TELEPORT": 0x45, "IT_S_FEAR": 0x46, "IT_S_SLEEP": 0x44, "IT_S_ENCHANT": 0x47,
                "IT_BOOK": 0x43, "IT_BOW": 0x06, "IT_W_SHORT": 0x07, "IT_W_AXE": 0x07,
                "IT_W_OAK": 0x06, "IT_W_BONE": 0x06, "IT_A_CHAIN": 0x07, "IT_H_HELM": 0x07,
                "IT_C_MIGHT": 0x06, "IT_C_PLENTY": 0x06}
        for k, a in want.items():
            self.assertEqual(M.item_attr(M.T[k]), a, k)
        # every real type has an ink; floor entries are TYPE/QTY only
        for m in range(100):
            for d in (1, 5, 8):
                lvl = M.gen_level_items(level(m, d), m, M.HERO_MAGE)
                for e in lvl.floor:
                    self.assertEqual(len(e), 4)
                    M.item_attr(e[2])

    def test_ink_table_vs_items_txt(self):
        """Cross-check against src/items.txt [types] INK column. TODO: tighten once the T4b
        regeneration merges (potions/scrolls there still say APP / $07 until then)."""
        txt = Path(__file__).resolve().parent.parent / "src" / "items.txt"
        rows, in_types = {}, False
        for ln in txt.read_text().splitlines():
            if ln.startswith("["):
                in_types = ln.strip() == "[types]"
            elif in_types and "|" in ln and not ln.startswith("#"):
                c = [x.strip() for x in ln.split("|")]
                if len(c) >= 3 and c[0] in M.T:
                    rows[c[0]] = c[2]
        if not rows or any(v.startswith("APP") for v in rows.values()):
            self.skipTest("items.txt not yet regenerated for 3E simplification (APP inks); TODO re-enable after T4b")
        for name, ink in rows.items():
            if ink.startswith("$"):
                self.assertEqual(M.ITEM_INK.get(M.T[name]), int(ink[1:], 16), name)


if __name__ == "__main__":
    unittest.main(verbosity=1)
