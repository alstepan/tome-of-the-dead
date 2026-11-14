#!/usr/bin/env python3
"""items_model_test.py - selftest of the GEAR2 side of tools/items_model.py
(docs/design/gear_rules.md; vectors G2-1..G2-9 plus the GEAR3 selection vectors that are
pure model: G3-1..G3-9 target choice).  Python only, no emulator.

    python3 tools/items_model_test.py [--seeds N] [--baseline GITREF]

--seeds N     master seeds 0..N-1 x D1..D8 x both heroes (default 1000 = 16,000 levels)
--baseline R  also diff against the items_model.py of git ref R (default 864f0c3, the last
              pre-GEAR2 model): same levels must differ ONLY in gear TYPE (class pool) and
              numeric-gear QTY; everything else (placement, traps, non-gear) byte-identical.
"""
import argparse
import importlib.util
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import levelgen as G  # noqa: E402
import items_model as M  # noqa: E402

T, D = M.T, M.D
fails = []


def check(name, got, want):
    if got != want:
        fails.append(name)
        print(f"FAIL {name}: got {got!r} want {want!r}")


def load_old(ref):
    """The items_model.py at git `ref`, loaded as a separate module (own G / D)."""
    src = subprocess.run(["git", "show", f"{ref}:tools/items_model.py"], cwd=HERE.parent,
                         capture_output=True, text=True, check=True).stdout
    spec = importlib.util.spec_from_loader("items_model_old", loader=None)
    mod = importlib.util.module_from_spec(spec)
    mod.__file__ = str(HERE / "items_model_old.py")      # its sys.path.insert targets tools/
    exec(compile(src, mod.__file__, "exec"), mod.__dict__)
    return mod


def levels(nseeds):
    for m in range(nseeds):
        for d in range(1, 9):
            try:
                b = G.generate(d, M.level_seed(m, d), m)
            except RuntimeError:
                continue
            for hero in (M.HERO_WARRIOR, M.HERO_MAGE):
                yield m, d, hero, b


def vectors():
    # G2-9 pools
    check("G2-9 W D1", M.gear_pool(1, M.HERO_WARRIOR), [T["IT_A_LEATHER"], T["IT_H_HELM"]])
    check("G2-9 M D3", M.gear_pool(3, M.HERO_MAGE),
          [T[k] for k in ("IT_W_IRON", "IT_A_ROBE", "IT_H_HOOD", "IT_C_MIGHT", "IT_C_WARD",
                          "IT_C_FIRE", "IT_C_MANA", "IT_C_PLENTY")])
    # pool sizes 1.3: W 2,6,9,10,10,11,11,11 ; M 2,6,8,9,9,9,9,9; NEW-MON3: + the Frost Charm from D5
    check("pool sizes W", [len(M.gear_pool(d, M.HERO_WARRIOR)) for d in range(1, 9)],
          [2, 6, 9, 10, 11, 12, 12, 12])
    check("pool sizes M", [len(M.gear_pool(d, M.HERO_MAGE)) for d in range(1, 9)],
          [2, 6, 8, 9, 10, 10, 10, 10])
    check("pool sizes W == old (+ Frost Charm D5+)", [len(M.gear_pool(d, M.HERO_WARRIOR)) for d in range(1, 9)],
          [len(M.gear_pool(d, M.HERO_WARRIOR, old=True)) + (d >= 5) for d in range(1, 9)])
    # encodings: q -1,0,+1,+2 <-> FL_QTY 8,1,2,3 <-> ISTATE 07,00,01,02
    for q, qty, ist in ((-1, 8, 0x07), (0, 1, 0), (1, 2, 1), (2, 3, 2)):
        check(f"q_to_qty {q}", M.q_to_qty(q), qty)
        check(f"qty_to_q {qty}", M.qty_to_q(qty), q)
        check(f"pickup_istate {qty}", M.pickup_istate(qty), ist)
        check(f"istate_q {ist:02X}", M.istate_q(ist), q)
    check("G2-3 pickup HELM qty 8", M.pickup_istate(8), 0x07)
    check("G2-7 qty-1 pickup", M.pickup_istate(1), 0)
    check("G2-8 HELM $A7 m,q,v", (M.istate_m(0xA7), M.istate_q(0xA7), M.istate_v(0xA7)), (-3, -1, -4))
    check("G3-9 HELM $42", (M.istate_m(0x42), M.istate_q(0x42), M.istate_v(0x42)), (2, 2, 4))
    # band table 2.3 (exact eighths)
    for depths, want in (((1, 2), {-1: 2, 0: 4, 1: 2, 2: 0}), ((3, 4, 5, 6), {-1: 1, 0: 4, 1: 2, 2: 1}),
                         ((7, 8), {-1: 0, 0: 4, 1: 2, 2: 2})):
        for d in depths:
            c = Counter(M.q_roll(w, d) for w in range(8))
            check(f"band eighths D{d}", {q: c.get(q, 0) for q in (-1, 0, 1, 2)}, want)
    # GEAR1 predicate
    W, Mg = M.HERO_WARRIOR, M.HERO_MAGE
    check("gate mage chain", M.gear_banned(Mg, T["IT_A_CHAIN"], 0), True)
    check("gate mage helm", M.gear_banned(Mg, 0, T["IT_H_HELM"]), True)
    check("gate mage mirror/silk/king/leather", [M.gear_banned(Mg, a, h) for a, h in (
        (T["IT_A_SILK"], T["IT_H_MIRROR"]), (T["IT_A_GRAVE"], T["IT_H_KING"]), (T["IT_A_LEATHER"], 0))],
        [False] * 3)
    check("gate war robe/hood", [M.gear_banned(W, T["IT_A_ROBE"], 0), M.gear_banned(W, 0, T["IT_H_HOOD"])],
          [True, True])
    check("gate war king+leather", M.gear_banned(W, T["IT_A_LEATHER"], T["IT_H_KING"]), False)

    # GEAR3 target selection (rng_mod semantics)
    def seq(*xs):
        it = iter(xs)
        return lambda: next(it)
    SH, LE, HE, CH = T["IT_W_SHORT"], T["IT_A_LEATHER"], T["IT_H_HELM"], T["IT_A_CHAIN"]
    worn = [(SH, 0), (LE, 0x60), (HE, 0)]
    check("G3-1", M.enchant_target(worn, [], seq(0x10)), ("worn", 0, 0x20))      # n=2, even -> k=0
    check("G3-2", M.enchant_target(worn, [], seq(0x11)), ("worn", 2, 0x20))      # odd -> k=1
    bag = [(T["IT_P_HEAL"], 0), (CH, 2)]
    check("G3-3", M.enchant_target([(SH, 0x60), (LE, 0x60), (HE, 0x60)], bag, seq(0)), ("bag", 1, 0x22))
    check("G3-4", M.enchant_target([(0, 0), (LE, 0x60), (T["IT_C_MIGHT"], 0)], [(T["IT_P_HEAL"], 0)], seq()), None)
    check("G3-5", M.enchant_target([(0, 0), (0, 0), (0, 0)], [(T["IT_H_HOOD"], 0)], seq(0)), ("bag", 0, 0x20))
    check("G3-6", M.enchant_target(worn := [(SH, 0), (LE, 0), (HE, 0)], [], seq(3, 1)), ("worn", 1, 0x20))
    check("G3-7", M.enchant_target([(SH, 0x60), (LE, 0x60), (T["IT_H_MIRROR"], 0)], [], seq(5)),
          ("worn", 2, 0x20))
    check("G3-8", M.enchant_target([(0, 0), (CH, 0xA0), (0, 0)], [], seq(0)), ("worn", 1, 0xC0))
    check("G3-9", M.enchant_target([(0, 0), (0, 0), (HE, 0x42)], [], seq(0)), ("worn", 2, 0x62))
    check("G3-9b", M.enchant_target([(0, 0), (0, 0), (HE, 0x62)], [], seq()), None)


def sweep(nseeds, old):
    n = 0
    onoff_bad = base_bad = viol = 0
    hist = {}                                  # band -> Counter(q)
    charm_bad = 0
    type_chg_lvls = qty_chg_lvls = any_chg_lvls = ngear = 0
    for m, d, hero, b in levels(nseeds):
        n += 1
        on = M.gen_level_items(b, m, hero)
        off = M.gen_level_items(b, m, hero, gear2=False)
        viol += bool(M.check_items(b, on, hero))
        gears = [e for e in on.floor if M.is_gear(e[2])]
        ngear += len(gears)
        # G2-1: on/off identical except qty of numeric gear; ITEM_RNG advanced by n_gear steps
        strip = lambda l: [(e[0], e[1], e[2], e[3] if not M.is_gear(e[2]) else 0) for e in l.floor]
        if strip(on) != strip(off) or on.traps != off.traps:
            onoff_bad += 1
        for e in on.floor:
            if M.is_gear(e[2]):
                if e[2] >= D["IT_CHARM_LO"]:
                    charm_bad += e[3] != 1
                else:
                    band = 0 if d <= 2 else (1 if d <= 6 else 2)
                    hist.setdefault(band, Counter())[M.qty_to_q(e[3])] += 1
        if old is not None:
            ob = old.gen_level_items(b, m, hero)
            if len(ob.floor) != len(on.floor) or ob.traps != on.traps:
                base_bad += 1
                continue
            tchg = qchg = False
            for eo, en in zip(ob.floor, on.floor):
                if eo[:2] != en[:2]:
                    base_bad += 1
                    break
                if eo[2] != en[2]:
                    # only gear types may change, both ends gear
                    if not (M.is_gear(eo[2]) and M.is_gear(en[2])) or eo[3] != 1:
                        base_bad += 1
                        break
                    tchg = True
                if eo[3] != en[3]:
                    if not M.is_numeric_gear(en[2]) or eo[3] != 1:
                        base_bad += 1
                        break
                    qchg = True
            type_chg_lvls += tchg
            qty_chg_lvls += qchg
            any_chg_lvls += tchg or qchg
    return dict(n=n, onoff_bad=onoff_bad, base_bad=base_bad, viol=viol, hist=hist, charm_bad=charm_bad,
                type_chg=type_chg_lvls, qty_chg=qty_chg_lvls, any_chg=any_chg_lvls, ngear=ngear)


def rng_steps_check(nseeds):
    """G2-1: the q pass consumes exactly one ITEM_RNG step per gear entry (state advance)."""
    bad = tot = 0
    for m, d, hero, b in levels(min(nseeds, 200)):
        caps = []
        orig = M.item_rng

        def spy(master, depth):
            r = orig(master, depth)
            caps.append(r)
            return r
        M.item_rng = spy
        try:
            on = M.gen_level_items(b, m, hero)
            off = M.gen_level_items(b, m, hero, gear2=False)
        finally:
            M.item_rng = orig
        ngear = sum(1 for e in on.floor if M.is_gear(e[2]))
        r_on, r_off = caps
        for _ in range(ngear):
            r_off.rnd(8)
        tot += 1
        bad += (r_on.x, r_on.calls) != (r_off.x, r_off.calls)
    return bad, tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=1000)
    ap.add_argument("--baseline", default="864f0c3")
    a = ap.parse_args()
    vectors()
    old = load_old(a.baseline) if a.baseline != "none" else None
    sb, st = rng_steps_check(a.seeds)
    check("G2-1 extra ITEM_RNG steps == gear entries", sb, 0)
    r = sweep(a.seeds, old)
    check("check_items violations", r["viol"], 0)
    check("G2-1 on/off differs beyond gear qty", r["onoff_bad"], 0)
    check("charms always qty 1", r["charm_bad"], 0)
    if old is not None:
        check("diff vs baseline outside gear type/qty", r["base_bad"], 0)
    want = {0: {-1: 2, 0: 4, 1: 2, 2: 0}, 1: {-1: 1, 0: 4, 1: 2, 2: 1}, 2: {-1: 0, 0: 4, 1: 2, 2: 2}}
    for band, c in sorted(r["hist"].items()):
        tot = sum(c.values())
        for q in (-1, 0, 1, 2):
            pct, wpct = 100 * c.get(q, 0) / tot, 100 * want[band][q] / 8
            check(f"G2-2 band{band} q{q:+d} {pct:.1f}% vs {wpct:.1f}% (+-2pp, n={tot})",
                  abs(pct - wpct) <= 2.0, True)
        print(f"  band {band}: n={tot} " + " ".join(f"q{q:+d}={100 * c.get(q, 0) / tot:.1f}%" for q in (-1, 0, 1, 2)))
    print(f"levels {r['n']}, gear entries {r['ngear']}, rng-step check {st} levels")
    if old is not None:
        print(f"vs {a.baseline}: levels with changed gear type {r['type_chg']}, with changed gear qty "
              f"{r['qty_chg']}, any item-list change {r['any_chg']} of {r['n']}")
    print("PASS" if not fails else f"FAIL {len(fails)}: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
