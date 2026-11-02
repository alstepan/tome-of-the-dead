#!/usr/bin/env python3
"""decor_density.py - D2-DECOR: decor objects per room, per depth (and why attempts fail).

Runs tools/levelgen.py generate() + tests/room_model.py render_room(decor=False) (the room as
build_room_map leaves it) + tools/decorgen.py (== the Z80 decor_room, world.py W13) over N seeds
x 8 depths x every present non-Sanctum room, and counts per depth:
  objects / room by class (patch pass, cobwebs, menu: large animated / mount / ceiling), cells,
  budget use vs MAX_LARGE / MAX_GLYPH / MAX_WALL, and every menu / patch attempt's outcome
  (placed, budget, footprint, support, ring) - the placement failure reasons.
Needs a build (game_lib reads build/wazhack.sym, WZ_BUILD_DIR honoured).

    python3 tools/decor_density.py [seeds=1000] [depth ...]
"""
import os
import sys
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tests"))
sys.path.insert(0, os.path.join(REPO, "tools"))
import decorgen as DG           # noqa: E402
import levelgen as G            # noqa: E402
import room_model as RM         # noqa: E402
from game_lib import S          # noqa: E402

COLS, ROWS = DG.COLS, DG.ROWS
CLS = {DG.C_MOUNT: "mount", DG.C_CEIL: "ceil", DG.C_FLOOR: "floor", DG.C_PATCH: "patch",
       DG.C_BRICK: "brick", DG.C_COMP: "patch"}


def why_not(m, row, col, w, h, cls, fl):
    """DG.fits() with the reason: footprint / support / ring."""
    req = DG.T_BRICK if cls == DG.C_BRICK else DG.T_AIR
    if any(m[(row + dy) * COLS + col + dx] != req for dy in range(h) for dx in range(w)):
        return "footprint"
    if cls == DG.C_CEIL:
        if row == 0:
            if fl & DG.F_MOSS:
                return "support"
        elif not DG.floorish(m[(row - 1) * COLS + col]):
            return "support"
    elif cls == DG.C_FLOOR:
        if not all(DG.floorish(m[(row + h) * COLS + col + dx]) for dx in range(w)):
            return "support"
    for rr in range(max(row - 1, 0), min(row + h, ROWS - 1) + 1):
        for cc in range(max(col - 1, 0), min(col + w, COLS - 1) + 1):
            t = m[rr * COLS + cc]
            if DG.T_LAD_L <= t <= DG.T_HOLE_R or DG.is_decor(t):
                return "ring"
    return None


class Probe(DG.Room):
    """DG.Room with try_place reporting the outcome of every attempt to self.log."""
    log = None

    def try_place(self, rng, obj, row_of):
        name, base, w, h, fl, cls = obj
        cmin = DG.CMIN[cls]
        col = cmin + rng.rnd(33 - w - 2 * cmin)
        s = rng.rnd(2)
        r0 = rng.rnd(6 - h)
        if cls in (DG.C_PATCH, DG.C_BRICK, DG.C_COMP):
            row = 9 * s + 1 + r0
        elif cls == DG.C_MOUNT:
            row = 9 * s + 1
        elif cls == DG.C_CEIL:
            row = 9 * s
        else:
            row = 9 * s + 8 - h
        area = DG.COMP_AREA if cls == DG.C_COMP else w * h
        dg = DG.counts(w, h, fl)
        large = 1 if fl & DG.F_LARGE else 0
        if self.nl + large > DG.MAX_LARGE:
            res = "budget_large"
        elif self.ng + dg > DG.MAX_GLYPH:
            res = "budget_glyph"
        elif cls in (DG.C_PATCH, DG.C_BRICK, DG.C_COMP) and self.nw + area > self.maxwall:
            res = "budget_wall"
        else:
            res = why_not(self.m, row, col, w, h, cls, fl)
        real = self._place(row, col, obj, area)
        assert real == (res is None), (name, res, real)
        self.log.append((name, cls, res or "placed", area, w * h))
        return real

    def _place(self, row, col, obj, area):
        name, base, w, h, fl, cls = obj
        m = self.m
        if not self.budget_ok(w, h, fl, cls, area) or not DG.fits(m, row, col, w, h, cls, fl):
            return False
        if cls == DG.C_COMP:
            m[row * COLS + col] = DG.D["T_WALL_PATCH"]
            m[row * COLS + col + 1] = DG.D["T_WALL_FADE"]
            m[(row + 1) * COLS + col] = DG.D["T_WALL_DITHER"]
            self.nw += DG.COMP_AREA
            return True
        i = base
        for dy in range(h):
            for dx in range(w):
                m[(row + dy) * COLS + col + dx] = i
                if not fl & DG.F_TILED:
                    i += 1
        self.nl += 1 if fl & DG.F_LARGE else 0
        self.ng += DG.counts(w, h, fl)
        self.nw += area if cls in (DG.C_PATCH, DG.C_BRICK) else 0
        return True


def decorate(m, depth, seed):
    """DG.decorate() on a Probe -> (map, room); cobwebs counted from the map diff."""
    rng = DG.Rng(seed)
    room = Probe(m, True, DG.WALL_MAX[depth])
    room.log = []
    DG.patch_pass(room, rng, depth)
    before = list(room.m)
    DG.cobwebs(room, rng, depth)
    room.ncob = sum(1 for a, b in zip(before, room.m) if a != b)
    mn = DG.menu(depth)
    for _ in range(DG.tries_of(depth)):
        room.try_place(rng, mn[rng.rnd(len(mn))], None)
    return room.m, room


def main(argv):
    n = int(argv[1]) if len(argv) > 1 else 1000
    depths = [int(x) for x in argv[2:]] or list(range(1, 9))
    rows = {}
    for d in depths:
        agg, res, att = Counter(), Counter(), Counter()
        nrooms = checked = 0
        for seed in range(1, n + 1):
            blk = bytearray(G.generate(d, seed * 7919 & 0xFFFF or 1))
            for r in range(9):
                o = RM.OFF_DESC + r * S["RD_STRIDE"]
                fl = blk[o + S["RD_FLAGS"]]
                if not fl & S["RDF_PRESENT"] or fl & S["RDF_SANCTUM"]:
                    continue
                base = RM.render_room(bytes(blk), r, decor=False)
                sd = blk[o + S["RD_SEED"]] | blk[o + S["RD_SEED"] + 1] << 8
                m, room = decorate(base, d, sd)
                if checked < 20:                      # == the reference deriver (and so the Z80)
                    m2, _al = DG.decorate(base, d, sd)
                    assert m2 == m, (d, seed, r)
                    checked += 1
                nrooms += 1
                placed = Counter()
                for name, cls, rs, area, cells in room.log:
                    att[(name, rs)] += 1
                    res[rs] += 1
                    if rs == "placed":
                        placed[CLS[cls]] += 1
                nobj = sum(placed.values()) + room.ncob
                agg["objects"] += nobj
                agg["cob"] += room.ncob
                for k, v in placed.items():
                    agg[k] += v
                agg["large"] += room.nl
                agg["glyph"] += room.ng
                agg["wall"] += room.nw
                agg["nl_full"] += room.nl == DG.MAX_LARGE
                agg["ng_full"] += room.ng >= DG.MAX_GLYPH
                agg["nw_full"] += room.nw >= room.maxwall
                agg["bare"] += not nobj
                vis = placed["mount"] + placed["ceil"] + placed["floor"]      # torch / window / banner / chain...
                agg["vis"] += vis
                agg["sparse"] += vis <= 2                                     # <= 2 non-wall objects
                agg["cells"] += sum(1 for a, b in zip(base, m) if a != b)   # decor cells (all classes)
        rows[d] = (nrooms, agg, res, att)
    print(f"{n} seeds per depth; per room (non-Sanctum rooms):")
    print("D  rooms | obj/room  patch mount ceil floor cob | large glyph wall (avg) | "
          "full: large glyph wall | bare rooms")
    for d, (nr, a, res, att) in rows.items():
        f = lambda k: a[k] / nr                         # noqa: E731
        print(f"D{d} {nr:5d} | {f('objects'):5.2f}   {f('patch'):5.2f} {f('mount'):5.2f} {f('ceil'):5.2f} "
              f"{f('floor'):5.2f} {f('cob'):4.2f} | {f('large'):4.2f} {f('glyph'):4.2f} {f('wall'):4.2f}"
              f"      | {a['nl_full'] / nr:5.1%} {a['ng_full'] / nr:5.1%} {a['nw_full'] / nr:5.1%}"
              f" | {a['bare'] / nr:5.1%}")
    print("\nvisible objects (mount + ceiling + floor classes; cobwebs and wall patches excluded):")
    print("D  vis/room  rooms with <= 2 | decor cells/room (all classes)")
    for d, (nr, a, res, att) in rows.items():
        print(f"D{d} {a['vis'] / nr:6.2f}   {a['sparse'] / nr:6.1%}        | {a['cells'] / nr:5.1f}")
    print("\nattempt outcomes per depth (patch pass + 12 menu tries, % of attempts):")
    for d, (nr, a, res, att) in rows.items():
        tot = sum(res.values())
        print(f"D{d} {tot / nr:5.1f}/room: " + ", ".join(f"{k} {v / tot:.0%}" for k, v in res.most_common()))
    print("\nper object: attempts/room -> placed% (failure reasons)")
    for d, (nr, a, res, att) in rows.items():
        names = sorted({k[0] for k in att})
        out = []
        for nm in names:
            t = sum(v for k, v in att.items() if k[0] == nm)
            pl = att[(nm, "placed")]
            bad = ", ".join(f"{k[1]} {v / t:.0%}" for k, v in sorted(att.items(), key=lambda kv: -kv[1])
                            if k[0] == nm and k[1] != "placed")
            out.append(f"{nm} {t / nr:.2f}->{pl / t:.0%} ({bad})")
        print(f"D{d}: " + "; ".join(out))


if __name__ == "__main__":
    main(sys.argv)
