#!/usr/bin/env python3
"""Packer tests for tools/textpack.py (no emulator): style checks, token
round trip, @long ZX0 blocks. Run: python3 tests/textpack_test.py"""
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import textpack as tp  # noqa: E402


def parse(body):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(body)
    try:
        return tp.read_source(f.name)
    finally:
        os.unlink(f.name)


class Style(unittest.TestCase):
    def bad(self, body):
        with self.assertRaises(SystemExit):
            parse(body)

    def test_real_source_parses(self):
        strs, longs = tp.read_source()
        self.assertGreaterEqual(len(strs), 24)
        self.assertEqual(strs[0], ("welcome", "YOU ENTER THE DUNGEON"))
        self.assertTrue(longs)

    def test_violations(self):
        self.bad('a "lower"\n')
        self.bad('a "TOO LONG TOO LONG TOO LONG TOO LONG"\n')
        self.bad('a "FULL STOP."\n')
        self.bad('a "DOUBLE  SPACE"\n')
        self.bad('a "X"\na "Y"\n')
        self.bad('a "\xe9"\n')
        self.bad('info_x "NAME  "\n')                        # trailing space
        self.bad('info_x "' + "N" * 16 + '5"\n')             # name too long
        self.bad('info_x "NAME' + " " * 13 + 'MP1"\n')       # numbers off boundary
        self.bad('info_x "NAME' + " " * 25 + 'NOTE"\n')      # notes off boundary
        self.bad('@long a\nlower\n@end\n')
        self.bad('@long a\nX\n')                              # no @end

    def test_limits(self):
        parse('ft_a "' + "A" * 42 + '"\n')
        self.bad('ft_a "' + "A" * 43 + '"\n')
        self.bad('b "' + "A" * 33 + '"\n')
        parse('info_ok "' + "NAME".ljust(16) + "MP1 RNG6".ljust(12) + "NOTE" + '"\n')

    def test_id_count(self):
        # D3-0: ids are bytes indexed 16-bit by tx_ptr: 256 strings, not 128
        many = lambda n: "".join(f's{i} "X"\n' for i in range(n))
        self.assertEqual(len(parse(many(200))[0]), 200)
        parse(many(tp.MAX_STRINGS))
        self.bad(many(tp.MAX_STRINGS + 1))


class RoundTrip(unittest.TestCase):
    def test_tokens(self):
        strs, _ = tp.read_source()
        names, texts = [n for n, _ in strs], [t for _, t in strs]
        ents, packed = tp.encode(texts)
        img, _, _ = tp.layout(ents, packed)
        for i, t in enumerate(texts):
            got = tp.decode(img, len(texts), i)
            self.assertEqual(bytes(got), t.encode(), names[i])
            self.assertTrue(all(32 <= c <= 127 for c in got))

    def test_long_zx0(self):
        lines = ["CONTROLS", "", "  INDENTED LINE", "A" * 42]
        raw = tp.long_image(lines)
        packed = tp.zx0_pack(raw)
        self.assertEqual(tp.zx0_unpack(packed), raw)
        self.assertEqual(tp.long_unpack(raw), lines)
        blocks = [("t", lines, raw, packed)]
        ids, asm, n = tp.emit_long(blocks)
        img = tp.parse_long_asm(asm)
        self.assertEqual(len(img), n)
        self.assertEqual(int.from_bytes(img[0:2], "little"), 4)
        self.assertEqual(int.from_bytes(img[2:4], "little"), len(raw))
        self.assertEqual(tp.zx0_unpack(img[4:4 + len(packed)]), raw)


if __name__ == "__main__":
    unittest.main()
