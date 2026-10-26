#!/usr/bin/env python3
"""RANK1 reference model of the class-book read (game.md §5 rev 6, src/fx6.asm
fx_book) and of the per-rank MP / auto-downcast rule. Pure Python; the Z80 is
compared against it by tests/t12.py (B section: seeded reads) and tests/rank1.py.

  book_read(kind, depth, ranks, dry, rng_state) -> dict(act, k, ranks, dry, rng, calls)
    act = "learn" | "rank" | "tome";  step 1 starter (0 RNG), 2 pity (0 RNG), 3 uniform pick
    (exactly ONE rng_next call: index = (byte * n) >> 8), 4 tome (0 RNG).
  downcast(costs, rank, mp) -> the rank cast: the highest <= rank with cost <= mp, rank 1 the floor.

`python3 tests/book_model.py` runs a Monte Carlo of a whole run's books against the designer's
estimates (game.md §5 "Expected yield") as a sanity check of the rule and prints the figures.
"""
import random
import sys

K_KNIGHT, K_WIZARD = 0, 1
PITY_N = 2
RANK_MAX = 3
UNLOCK = {K_KNIGHT: (1, 3), K_WIZARD: (1, 2, 3, 4, 5)}          # unlock depth per class slot (§4)
MP_COST = {                                                       # §5 rev 6, rank 1..3
    "Spark": (2, 4, 6), "Firebolt": (3, 5, 8), "Frost": (3, 5, 8), "Drain": (3, 5, 8),
    "Lightning": (5, 8, 12), "Power": (3, 5, 7), "Whirl": (4, 7, 10),
}


def rng_next(st):
    """The Z80 xorshift16 (io.asm rng_next): (new state, the byte = L)."""
    h, l = st >> 8, st & 255
    a = ((h & 1) << 7) | (l >> 1)
    h = a ^ h
    a = ((l & 1) << 7) | (h >> 1)
    l = a ^ l
    h = l ^ h
    return h << 8 | l, l


def book_read(kind, depth, ranks, dry, rng_state):
    n_slots = len(UNLOCK[kind])
    ranks = list(ranks)
    cands = []                                                    # (k, unlearned)
    for k in range(n_slots):
        if ranks[k] == 0:
            if UNLOCK[kind][k] <= depth:
                cands.append((k, True))
        elif ranks[k] < RANK_MAX:
            cands.append((k, False))
    out = dict(rng=rng_state, calls=0, dry=dry)
    if not any(ranks):                                            # 1. starter
        pick = (0, True)
    elif not cands:                                               # 4. tome
        out.update(act="tome", k=None, ranks=ranks)
        return out
    else:
        first = next((i for i, c in enumerate(cands) if c[1]), None)
        if dry == PITY_N and first is not None:                   # 2. pity: the earliest-depth unlearned
            pick = cands[first]
        else:                                                     # 3. one RNG call
            out["rng"], byte = rng_next(rng_state)
            out["calls"] = 1
            pick = cands[(byte * len(cands)) >> 8]
    k, learn = pick
    if learn:
        out["dry"] = 0
    elif any(c[1] for c in cands):
        out["dry"] = dry + 1
    else:
        out["dry"] = 0
    ranks[k] += 1
    out.update(act="learn" if learn else "rank", k=k, ranks=ranks)
    return out


def downcast(costs, rank, mp):
    """costs = (c1, c2, c3); the rank actually cast."""
    rank = max(rank, 1)
    while rank > 1 and costs[rank - 1] > mp:
        rank -= 1
    return rank


def run_books(kind, rng, books_by_depth=None):
    """One run: books found D1..D7 (1 each, a 2nd with 1 in 2 on D4..D7), read on the level found."""
    ranks, dry, st = [0] * len(UNLOCK[kind]), 0, rng.randrange(1, 65536)
    tomes = 0
    for depth in range(1, 8):
        for _ in range(1 + (1 if depth >= 4 and rng.random() < 0.5 else 0)):
            r = book_read(kind, depth, ranks, dry, st)
            st, dry = r["rng"], r["dry"]
            if r["act"] == "tome":
                tomes += 1
            else:
                ranks = r["ranks"]
    return ranks, tomes


def main():
    rng = random.Random(2026)
    n = 40000
    miss = [0] * 6
    fire_missing = 0
    top = 0
    for _ in range(n):
        ranks, _ = run_books(K_WIZARD, rng)
        m = sum(1 for r in ranks if r == 0)
        miss[m] += 1
        fire_missing += ranks[1] == 0
        top += ranks[0] == 3
    print("Mage books D1-D7: missing 0 / 1 / 2 spells: %.1f%% / %.1f%% / %.1f%% (doc ~61 / 36 / 3);"
          " Firebolt missing %.1f%% (doc ~2); Spark III %.1f%% (doc ~50)" % (
              100 * miss[0] / n, 100 * miss[1] / n, 100 * miss[2] / n, 100 * fire_missing / n, 100 * top / n))
    worst = 0
    for _ in range(n):
        ranks, tomes = run_books(K_KNIGHT, rng)
        worst += ranks != [3, 3]
    print("Warrior: not PS III + Whirlwind III at run end: %.2f%% (doc: end state fixed)" % (100 * worst / n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
