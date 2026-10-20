#!/usr/bin/env python3
"""3E-T10: item_name (bank 1) and the bag helpers bag_add / bag_find / bag_take /
bag_pick (bank 3), called through a tiny stub with set registers (no game loop).

  N1  item_name for every bag type (IT_BAG_LO..IT_COUNT-1) x both hero kinds == the
      name src/items.txt composes (<HERO> TOME -> WAR / SPELL), DE advanced by exactly
      len, CF = 0, no terminator written (the next byte untouched), IX / IY kept
  N2  types with no name (0..4) -> empty, CF = 0
  N3  truncation: H = 0..len+1 for every name: the first H chars, CF = 1 iff
      H < len, nothing written past H
  N5  item_name time (worst name) <= 6k T
  B1  bag_add rejects ids < IT_BAG_LO (incl. the legacy potion 1) and >= IT_COUNT (L=1,
      BAG untouched); gear / bow / book never merge
  B2  stackables merge on equal type up to STACK_MAX, then open a second slot
  B3  full at BAG_SLOTS: L = 1, BAG unchanged; a merge into an existing stack still works
  B4  bag_find: slot / $FF / first free slot (IT_NONE); keeps B, DE, IX, IY
  B5  bag_take: decrement, to zero compacts (later records shift down, last cleared),
      over-take empties; A = QTY left
  B6  bag_pick: lowest type present (food / potion), largest stack with lowest-type
      ties (scrolls), IT_NONE when absent
Every call also checks IX / IY survive. Prints bytes and T-states.
Run: ZRCP_PORT=<port> python3 tests/bag.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
import itempack as ip                                    # noqa: E402
from game_lib import Harness, Proto, S, EMU_ARGS         # noqa: E402

ROOT = HERE.parent
DRV = S["LOWRAM_END_3B"]
BAG, SLOTS, STRIDE = S["BAG"], S["BAG_SLOTS"], S["IR_STRIDE"]
IT = {k[3:]: v for k, v in S.items() if k.startswith("IT_") and isinstance(v, int)}
IT_COUNT, BAG_LO = S["IT_COUNT"], S["IT_BAG_LO"]
GUARD_IX, GUARD_IY = 0x1357, 0x2468
BANK1, BANK3 = S["BANK_UI1"], S["BANK_COLD3"]
DEST = S["MSG_BUF"]
FILL = 0x21


class T(Proto):
    proto_start = 0

    def stub(self, bank, target, **r):
        """Run `target` in `bank` with registers a, b, c, d, e, h, l set."""
        g = lambda n: r.get(n, 0)                        # noqa: E731
        code = [0xF3, 0x31, S["WORKSTORE_TOP"] & 255, S["WORKSTORE_TOP"] >> 8,
                0xDD, 0x21, GUARD_IX & 255, GUARD_IX >> 8,
                0xFD, 0x21, GUARD_IY & 255, GUARD_IY >> 8,
                0x3E, bank, 0xCD, S["page_bank"] & 255, S["page_bank"] >> 8,
                0x01, g("c"), g("b"), 0x11, g("e"), g("d"), 0x21, g("l"), g("h"),
                0x3E, g("a"), 0xCD, target & 255, target >> 8]
        done = DRV + len(code)
        code += [0x18, 0xFE]                              # done: jr done
        self.z.cmd("write-memory %d %s" % (DRV, " ".join(map(str, code))))
        self.z.cmd("set-breakpoint 3 PC=%d" % done)
        self.extra_probes = {done}
        self.z.cmd("set-register PC=%d" % DRV)
        self.z.cmd("reset-tstates-partial")
        self.z.cmd("run 20000000")
        if self.pc() != done:
            raise RuntimeError("stub did not return: PC %04X" % self.pc())
        self.ts = int(self.z.cmd("get-tstates-partial"))
        r = self.regs()
        if (r["IX"], r["IY"]) != (GUARD_IX, GUARD_IY):
            self.h.failures.append("IX/IY clobbered by %04X" % target)
            print("[FAIL] IX/IY clobbered by routine at %04X" % target)
        return r

    def regs(self):
        out = {}
        for tok in self.z.cmd("get-registers").replace("\n", " ").split():
            if "=" in tok and "'" not in tok:
                k, v = tok.split("=", 1)
                try:
                    out[k.upper()] = int(v.lstrip("#"), 16)
                except ValueError:
                    pass
        out.update(A=out["AF"] >> 8, F=out["AF"] & 255, B=out["BC"] >> 8, C=out["BC"] & 255,
                   D=out["DE"] >> 8, E=out["DE"] & 255, H=out["HL"] >> 8, L=out["HL"] & 255)
        return out

    def bag(self):
        return bytes(self.z.read_memory(BAG, SLOTS * STRIDE))

    def set_bag(self, recs):
        b = bytearray(SLOTS * STRIDE)
        for i, (t, q, s) in enumerate(recs):
            b[i * STRIDE:i * STRIDE + 3] = bytes((t, q, s))
        self.z.cmd("write-memory %d %s" % (BAG, " ".join(map(str, b))))
        return bytes(b)


def main():
    syms = ip.parse_defs(str(ROOT / "src" / "item_defs.asm"))
    rows = ip.parse_items(str(ROOT / "src" / "items.txt"), syms).rows
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)
        p.load()
        expect = h.expect

        def ex(name, got, want):
            c = lambda v: v if isinstance(v, int) else (v.hex() if isinstance(v, bytes) else repr(v))   # noqa: E731
            expect(name, c(got), c(want))
        h.expect = ex

        def name_of(t, kind):
            n = rows[t].name
            return "" if n is None else n.replace("<HERO>", "WAR" if kind == 0 else "SPELL")

        def call_name(t, hmax, kind):
            p.z.cmd("write-memory %d %s" % (DEST, " ".join([str(FILL)] * 40)))
            p.wb("HERO_KIND", kind)
            r = p.stub(BANK1, S["item_name"], a=t, e=DEST & 255, d=DEST >> 8, h=hmax)
            return r, r["DE"] - DEST, bytes(p.z.read_memory(DEST, 40))

        pad = lambda n: bytes([FILL]) * (40 - n)         # noqa: E731
        bad = []
        for kind in (0, 1):
            for t in range(BAG_LO, IT_COUNT):
                want = name_of(t, kind).encode()
                r, n, raw = call_name(t, 32, kind)
                if not (n == len(want) and raw[:n] == want and raw[n:] == pad(n) and not r["F"] & 1):
                    bad.append((t, kind, raw[:n], want, hex(r["F"])))
        h.expect("N1 item_name == items.txt, all bag types x both heroes", len(bad), 0)
        if bad:
            print("  detail:", bad[:4])
        bad = []
        for t in range(0, BAG_LO):
            r, n, raw = call_name(t, 32, 0)
            if n or r["F"] & 1 or raw[:1] != pad(0)[:1]:
                bad.append(t)
        h.expect("N2 nameless types (0..4) -> empty, CF 0", len(bad), 0)
        bad = []
        for kind in (0, 1):
            for t in range(BAG_LO, IT_COUNT):
                full = name_of(t, kind).encode()
                for hm in sorted({0, 1, 2, 3, 4, len(full) - 1, len(full), len(full) + 1} - {-1}):
                    r, n, raw = call_name(t, hm, kind)
                    want = full[:hm]
                    if n != len(want) or raw[:n] != want or bool(r["F"] & 1) != (hm < len(full)) \
                            or raw[n:] != pad(n):
                        bad.append((t, kind, hm, raw[:n], want, hex(r["F"])))
        h.expect("N3 truncation (H = 0..len+1, CF = cut, nothing past H)", len(bad), 0)
        if bad:
            print("  detail:", bad[:4])
        worst = max(((len(name_of(t, 1)), t) for t in range(BAG_LO, IT_COUNT)))[1]
        call_name(worst, 32, 1)
        print("  item_name worst (%s) %d T incl. stub (page_bank ~0.3k)" % (name_of(worst, 1), p.ts))
        h.expect("N5 item_name <= 6k T", int(p.ts <= 6000), 1)

        def add(t, q=1, ist=0):
            r = p.stub(BANK3, S["bag_add"], a=t, b=q, c=ist)
            return r["L"], r

        p.set_bag([])
        before = p.bag()
        rej = [0, 1, 2, 3, 4, IT_COUNT, 200, 255]
        h.expect("B1 rejects ids < IT_BAG_LO / >= IT_COUNT (L=1)", [add(t)[0] for t in rej], [1] * len(rej))
        h.expect("B1 BAG untouched by rejects", p.bag(), before)
        for t, ist in ((IT["W_SHORT"], 0x20), (IT["W_SHORT"], 0x20), (IT["BOW"], 0), (IT["BOOK"], 0),
                       (IT["BOOK"], 0)):
            _, r = add(t, 1, ist)
        want = bytes([IT["W_SHORT"], 1, 0x20] * 2 + [IT["BOW"], 1, 0] + [IT["BOOK"], 1, 0] * 2) + bytes(45)
        h.expect("B1 gear / bow / book never stack", p.bag(), want)
        h.expect("B1 bag_add keeps B, C", (r["B"], r["C"]), (1, 0))
        p.set_bag([])
        res = [add(IT["P_HEAL"])[0] for _ in range(9)]
        h.expect("B2 nine heals: all L 0, one slot of 9", (res, p.bag()[:6]),
                 ([0] * 9, bytes([IT["P_HEAL"], 9, 0, 0, 0, 0])))
        add(IT["P_HEAL"])
        add(IT["F_APPLE"])
        add(IT["P_HEAL"], 2)
        h.expect("B2 tenth heal opens a 2nd slot; apple 3rd; +2 heals tops up slot 2",
                 p.bag()[:12], bytes([IT["P_HEAL"], 9, 0, IT["P_HEAL"], 3, 0, IT["F_APPLE"], 1, 0, 0, 0, 0]))
        add(IT["P_HEAL"], 9)                       # 9 would overflow slot 2 (4+9): a new slot
        h.expect("B2 a stack that would pass 9 takes a new slot", p.bag()[9:12],
                 bytes([IT["P_HEAL"], 9, 0]))
        p.set_bag([(IT["P_MANA"], 1, 0)] + [(IT["W_LONG"], 1, 0)] * (SLOTS - 1))
        full = p.bag()
        h.expect("B3 full bag: gear add -> L 1", add(IT["W_SHORT"])[0], 1)
        h.expect("B3 full bag unchanged", p.bag(), full)
        h.expect("B3 full: merge into the existing mana stack -> L 0", add(IT["P_MANA"])[0], 0)
        h.expect("B3 mana now 2", p.bag()[1], 2)
        h.expect("B3 full: new stackable type -> L 1", add(IT["F_PEAR"])[0], 1)

        def find(t):
            return p.stub(BANK3, S["bag_find"], a=t, b=0x5A, d=0x6B, e=0x7C)
        p.set_bag([(IT["F_CARROT"], 1, 0), (IT["P_HEAL"], 2, 0), (IT["P_HEAL"], 3, 0)])
        r = find(IT["P_HEAL"])
        h.expect("B4 find heal -> slot 1 (first)", r["A"], 1)
        h.expect("B4 find keeps B, DE", (r["B"], r["DE"]), (0x5A, 0x6B7C))
        h.expect("B4 find absent -> $FF", find(IT["S_FEAR"])["A"], 0xFF)
        h.expect("B4 find IT_NONE -> first free slot 3", find(0)["A"], 3)
        p.set_bag([(IT["F_CARROT"], 1, 0)] * SLOTS)
        h.expect("B4 find IT_NONE in a full bag -> $FF", find(0)["A"], 0xFF)
        p.set_bag([(IT["F_CARROT"], 1, 0)] * (SLOTS - 1) + [(IT["BOW"], 1, 0)])
        h.expect("B4 find in the last slot -> 19", find(IT["BOW"])["A"], SLOTS - 1)

        def take(s, q):
            return p.stub(BANK3, S["bag_take"], a=s, b=q)
        p.set_bag([(IT["F_CARROT"], 1, 0), (IT["P_HEAL"], 5, 0), (IT["W_AXE"], 1, 0x40), (IT["S_FEAR"], 2, 0)])
        h.expect("B5 take 2 of 5 -> A 3, record updated", (take(1, 2)["A"], p.bag()[4]), (3, 3))
        h.expect("B5 take rest -> A 0", take(1, 3)["A"], 0)
        h.expect("B5 compacted (axe, fear shift down; tail cleared)", p.bag(),
                 bytes([IT["F_CARROT"], 1, 0, IT["W_AXE"], 1, 0x40, IT["S_FEAR"], 2, 0]) + bytes(SLOTS * 3 - 9))
        p.set_bag([(IT["F_CARROT"], 1, 0)] * SLOTS)
        take(SLOTS - 1, 1)
        h.expect("B5 emptying the last slot", p.bag(), bytes([IT["F_CARROT"], 1, 0] * (SLOTS - 1)) + bytes(3))
        p.set_bag([(IT["F_CARROT"] + i % 3, 1, i) for i in range(SLOTS)])
        take(0, 1)
        want = bytes(x for i in range(1, SLOTS) for x in (IT["F_CARROT"] + i % 3, 1, i)) + bytes(3)
        h.expect("B5 emptying slot 0 of a full bag shifts 19 records", p.bag(), want)
        ts_shift = p.ts
        p.set_bag([(IT["P_MANA"], 2, 0), (IT["F_APPLE"], 1, 0)])
        take(0, 9)
        h.expect("B5 over-take empties", p.bag()[:6], bytes([IT["F_APPLE"], 1, 0, 0, 0, 0]))

        def pick(lo, size, mode):
            return p.stub(BANK3, S["bag_pick"], b=lo, d=2 * size + mode)
        FOOD, POT, SCR = (IT["F_CARROT"], 5), (IT["P_HEAL"], 3), (IT["S_TELEPORT"], 4)
        p.set_bag([(IT["F_MEAT"], 3, 0), (IT["F_PEAR"], 1, 0), (IT["F_CHEESE"], 2, 0)])
        h.expect("B6 food = lowest type present (pear)", pick(*FOOD, 0)["A"], IT["F_PEAR"])
        h.expect("B6 potion class empty -> IT_NONE", pick(*POT, 0)["A"], 0)
        p.set_bag([(IT["P_CURE"], 9, 0), (IT["P_MANA"], 1, 0), (IT["P_HEAL"], 1, 0)])
        h.expect("B6 potion = lowest id (heal) regardless of stack size", pick(*POT, 0)["A"], IT["P_HEAL"])
        p.set_bag([(IT["S_SLEEP"], 2, 0), (IT["S_ENCHANT"], 5, 0), (IT["S_FEAR"], 5, 0)])
        h.expect("B6 scroll = largest stack, ties -> lowest id (fear)", pick(*SCR, 1)["A"], IT["S_FEAR"])
        p.set_bag([(IT["S_SLEEP"], 2, 0), (IT["S_TELEPORT"], 2, 0)])
        h.expect("B6 scroll tie 2/2 -> teleport", pick(*SCR, 1)["A"], IT["S_TELEPORT"])
        p.set_bag([(IT["P_HEAL"], 4, 0), (IT["W_AXE"], 1, 0)])
        h.expect("B6 scroll class absent -> IT_NONE", pick(*SCR, 1)["A"], 0)
        ts_pick = p.ts
        p.set_bag([(IT["S_ENCHANT"], 1, 0)])
        h.expect("B6 last type of the class is reachable", pick(*SCR, 1)["A"], IT["S_ENCHANT"])
        p.set_bag([(IT["F_CARROT"], 1, 0)] * (SLOTS - 1) + [(IT["W_SHORT"], 1, 0)])
        add(IT["W_AXE"])
        ts_add = p.ts
        print("  T incl. stub (~0.3k): bag_add full-scan %d, bag_take shift-19 %d, bag_pick scrolls absent %d" %
              (ts_add, ts_shift, ts_pick))
        print("  bytes: item_name %d (bank 1), bag helpers %d (bank 3)" % (S["ITEM_NAME_LEN"], S["BAG3_LEN"]))
        return 1 if h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
