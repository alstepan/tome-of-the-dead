#!/usr/bin/env python3
"""BALANCE-PKG5: the monster melee depth ramp (src/dscl.asm dsc_roll, called by bank-3 dmg_roll).

D1  static: dsc_tab (the .sna) == round(s * 64) choices that make (32 + x * w) >> 6 == int(x * s + 0.5) for x in
    0..15, s = tools/balance_pkg5_final.json MON_DMG_SCALE_D (LVL_DEPTH 0 = the PROTO rooms: x 1).
D2  emulator: dsc_roll on every LVL_DEPTH 0..8 x every (N, B) kind_tab holds (+ the edges 1 / 15): C / D out == the
    sim's int(N * s + 0.5) / int(B * s + 0.5); IX kept.
D3  emulator: dmg_roll gates on EF_PLAYER: a hero's roll is 1..N + B unscaled on D8; a monster's 1..N' + B'
    (several seeds, every value in range, the max reached).
Run: ZRCP_PORT=<port> WZ_BUILD_DIR=<dir> python3 tests/dsc.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, SNA_RAM  # noqa: E402
import proj3 as P  # noqa: E402

SCALE = [1.0] + json.load(open(HERE.parent / "tools" / "balance_pkg5_final.json"))["param"]["MON_DMG_SCALE_D"]


def want(x, s):
    return int(x * s + 0.5)


def w16(v):
    return [v & 0xFF, v >> 8]


def ram(addr):
    """A bank-5 ($4000..$7FFF) / bank-2 ($8000..$BFFF) byte of the snapshot (SNA_RAM = banks 0..7)."""
    return SNA_RAM[(5 if addr < 0x8000 else 2) * 16384 + (addr & 0x3FFF)]


def main():
    fails = []
    tab = [ram(S["dsc_tab"] + d) for d in range(9)]
    for d, s in enumerate(SCALE):
        bad = [x for x in range(16) if (32 + x * tab[d]) >> 6 != want(x, s)]
        if bad:
            fails.append(f"D1 depth {d} w {tab[d]}: x {bad}")
    print(f"[D1] dsc_tab {tab}: {'ok' if not fails else fails}", flush=True)
    kt = S["kind_tab"]
    dies = sorted({ram(kt + S["KT_DIE"] + k) for k in range(2, 32)} | {1, 15})
    boni = sorted({ram(kt + S["KT_BONUS"] + k) for k in range(2, 32)})
    res = P.RES
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = P.T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                print(f"[detail] {tag}: {detail}", flush=True)

        p.boot(K_KNIGHT)
        n = 0
        for d in range(9):
            p.wb("LVL_DEPTH", d)
            for nd in dies:
                for b in boni:
                    # ld ix, $1234 / ld c, N / ld d, B / call dsc_roll / ld (res), bc / ld (res + 2), de / ld (res + 4), ix
                    body = ([0xDD, 0x21, 0x34, 0x12, 0x0E, nd, 0x16, b, 0xCD] + w16(S["dsc_roll"])
                            + [0xED, 0x43] + w16(res) + [0xED, 0x53] + w16(res + 2) + [0xDD, 0x22] + w16(res + 4))
                    ok = p.code(body)
                    r = [p.rb(res + i) for i in range(6)]
                    got = (r[0], r[3], r[4] | r[5] << 8)
                    exp = (want(nd, SCALE[d]), want(b, SCALE[d]), 0x1234)
                    n += 1
                    if not ok or got != exp:
                        fails.append(f"D2 depth {d} N {nd} B {b}: got {got} want {exp}")
        check(f"D2 dsc_roll == int(x * s + 0.5) for N / B, {n} cases, IX kept", not any(f.startswith("D2") for f in fails))
        # D3: dmg_roll through the real gate (bank 3), hero vs monster slot, D8 (s 3.0)
        p.wb("LVL_DEPTH", 8)
        stride = S["P_ENT_STRIDE"]
        ents = S["P_ENTITIES"]
        for slot, kind, player in ((0, K_KNIGHT, True), (1, S["K_DKNIGHT"], False)):
            base = ents + slot * stride
            nd, b = ram(kt + S["KT_DIE"] + kind), ram(kt + S["KT_BONUS"] + kind)
            if player:                         # the hero's column is runtime (gear6 hero_recalc)
                nd, b = p.rb(kt + S["KT_DIE"] + kind), p.rb(kt + S["KT_BONUS"] + kind)
                b = b - 256 if b >= 128 else b
            p.wb(base + S["E_KIND"], kind)
            p.wb(base + S["E_FLAGS"], 1 | (2 if player else 4))
            lo, hi = (1 + b, nd + b) if player else (1 + want(b, 3.0), want(nd, 3.0) + want(b, 3.0))
            seen = set()
            for seed in range(1, 400):
                p.z.cmd("write-memory %d %d %d" % (S["RNG_STATE"], seed & 0xFF, (seed * 37) & 0xFF))
                # ld ix, base / far3-free: page bank 3 around dmg_roll / ld (res), a
                body = p.bank3([0xDD, 0x21] + w16(base) + [0xCD] + w16(S["dmg_roll"]) + [0x32] + w16(res))
                ok = p.code(body)
                seen.add(p.rb(res))
            check(f"D3 {'hero' if player else 'Death Knight'} D8 dmg_roll in {lo}..{hi}, max reached",
                  min(seen) >= lo and max(seen) <= hi and max(seen) == hi, (sorted(seen), lo, hi))
    print("dsc:", "PASS" if not fails else "FAIL %s" % fails[:8])
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
