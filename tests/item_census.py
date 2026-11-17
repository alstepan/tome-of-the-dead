#!/usr/bin/env python3
"""ITEM-CENSUS: what the real Z80 item generator (src/items_ovl.asm, run through the real
ovl_run stream exactly as tests/items_gen.py does) puts on D1..D4 floors, per hero.

For every (master seed, depth, hero) the Python levelgen block (== the Z80 level_gen, proven by
tests/levelgen_z80.py) is poked into LVL_STATE, the overlay is run on the emulator, and the
resulting FLOOR_LIST is read back and counted by item type: food (and its food value), potions
by kind, scrolls by kind, class books, gear.  Spells are NOT floor items: a spell / rank comes
from reading a class book (fx_book, tests/book_model.book_read, chosen at READ time from the
hero's unlocked, unlearned / unmaxed slots), so the "spell source" is the book count plus a
Monte-Carlo of the book rule over the census's own per-depth book counts.
Monster drops are NOT pre-rolled: src/drop3.asm mon_drop -> src/tier6.asm drop_row rolls
"k in N" on the gameplay RNG when the monster dies, so drops are estimated from drop_tab, not
censused.

Run: ZRCP_PORT=<10991..10999> WZ_BUILD_DIR=<dir holding tome-of-the-dead.sna/.sym, ovl/> \
     python3 tests/item_census.py [--seeds N]
"""
import random
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
import items_gen as IG                                  # noqa: E402
import levelgen as G                                    # noqa: E402
import items_model as M                                 # noqa: E402
import book_model as BM                                 # noqa: E402
from game_lib import Harness, S, EMU_ARGS, F3           # noqa: E402

DEPTHS = (1, 2, 3, 4)
FOODS = ("F_CARROT", "F_APPLE", "F_PEAR", "F_CHEESE", "F_MEAT")
FVAL = {"F_CARROT": 10, "F_APPLE": 15, "F_PEAR": 20, "F_CHEESE": 30, "F_MEAT": 40}   # item_defs.asm
NAMES = {}
for _k, _v in S.items():
    if (_k.startswith("IT_") and isinstance(_v, int) and _k != "IT_COUNT"
            and not _k.endswith(("_LO", "_HI", "_BIT"))):          # drop the range aliases (IT_POT_LO == IT_P_HEAL ...)
        NAMES.setdefault(_v, _k[3:])


def census_block(b):
    """{item name: live floor entries} of a post-overlay 320-B block."""
    c = defaultdict(int)
    for i in range(b[G.H["FLOOR_N"]]):
        o = G.OFF_FLOOR + i * M.D["FL_STRIDE"]
        if b[o] != M.D["FL_EMPTY"]:
            c[NAMES.get(b[o + 2], "?%d" % b[o + 2])] += 1
    return c


def book_mc(kind, books, rng, runs=20000):
    """After the books of D1..d (counts = the census means, every one read): P(slot 1 learned)
    [Mage: Firebolt; Warrior: Power Strike is slot 0, slot 1 = Whirlwind], P(slot 2), mean slot-0 rank."""
    out = {d: defaultdict(float) for d in DEPTHS}
    for _ in range(runs):
        ranks, dry, st = [0] * len(BM.UNLOCK[kind]), 0, rng.randrange(1, 65536)
        for d in DEPTHS:
            nb = books[d]
            for _k in range(int(nb) + (1 if rng.random() < nb - int(nb) else 0)):
                r = BM.book_read(kind, d, ranks, dry, st)
                st, dry = r["rng"], r["dry"]
                if r["act"] != "tome":
                    ranks = r["ranks"]
            out[d]["slot1"] += ranks[1] > 0
            out[d]["slot2"] += len(ranks) > 2 and ranks[2] > 0
            out[d]["rank0"] += ranks[0]
    return {d: {k: v / runs for k, v in o.items()} for d, o in out.items()}


def main():
    nseeds = int(sys.argv[sys.argv.index("--seeds") + 1]) if "--seeds" in sys.argv else 60
    tot = {(h, d): defaultdict(float) for h in ("W", "M") for d in DEPTHS}
    nl = defaultdict(int)
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = IG.T(h)
        p.load()
        p.setup()
        pend = []

        def flush():
            outs, _ = p.batch([c[0] for c in pend])
            for (_rec, key), out in zip(pend, outs):
                nl[key] += 1
                for name, n in census_block(out).items():
                    tot[key][name] += n
                tot[key]["_entries"] += out[G.H["FLOOR_N"]]
            pend.clear()

        for m in range(nseeds):
            for d in DEPTHS:
                try:
                    b = G.generate(d, M.level_seed(m, d), m, f3=F3)
                except RuntimeError:
                    continue
                for hero, hk in IG.HEROES:
                    pend.append((bytes(b) + bytes([hk]), ("W" if hk == 0 else "M", d)))
                    if len(pend) == IG.NSLOT:
                        flush()
        if pend:
            flush()

    def mean(key, *names):
        return sum(tot[key][n] for n in names) / max(1, nl[key])
    print(f"levels per (hero, depth): {dict(nl)}")
    print("hero depth |  food  food-val | heal mana cure | scrolls (tele fear sleep ench) | books | gear | entries")
    for hero in ("W", "M"):
        for d in DEPTHS:
            k = (hero, d)
            fv = sum(tot[k][n] * FVAL[n] for n in FOODS) / max(1, nl[k])
            gear = sum(v for n, v in tot[k].items() if n[:2] in ("W_", "A_", "H_", "C_")) / max(1, nl[k])
            print(f"  {hero}   D{d}  | {mean(k, *FOODS):5.2f} {fv:6.1f}  | {mean(k, 'P_HEAL'):4.2f} {mean(k, 'P_MANA'):4.2f} "
                  f"{mean(k, 'P_CURE'):4.2f} | {mean(k, 'S_TELEPORT', 'S_FEAR', 'S_SLEEP', 'S_ENCHANT'):.2f} "
                  f"({mean(k, 'S_TELEPORT'):.2f} {mean(k, 'S_FEAR'):.2f} {mean(k, 'S_SLEEP'):.2f} {mean(k, 'S_ENCHANT'):.2f}) "
                  f"| {mean(k, 'BOOK'):.2f}  | {gear:.2f} | {mean(k, '_entries'):.1f}")
    rng = random.Random(7)
    for hero, kind in (("W", BM.K_KNIGHT), ("M", BM.K_WIZARD)):
        mc = book_mc(kind, {d: mean((hero, d), "BOOK") for d in DEPTHS}, rng)
        for d in DEPTHS:
            print(f"{hero} all books read through D{d}: slot1 learned {mc[d]['slot1']:.2f}  slot2 {mc[d]['slot2']:.2f}  "
                  f"slot0 rank {mc[d]['rank0']:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
