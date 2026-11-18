#!/usr/bin/env python3
"""decor_density.py - D2-DECOR: decor objects per room, per depth (and why attempts fail).

Runs tools/levelgen.py generate() + tests/room_model.py render_room(decor=False) (the room as
build_room_map leaves it) + tools/decorgen.py (== the Z80 decor_room, world.py W13) over N seeds
x 8 depths x every present non-Sanctum room, and counts per depth:
  objects / room by class (patch pass, cobwebs, menu: large animated / mount / ceiling), cells,
  budget use vs MAX_LARGE / MAX_GLYPH / MAX_WALL, and every menu / patch attempt's outcome
  (placed, budget, footprint, support, ring) - the placement failure reasons.
Needs a build (game_lib reads build/tome-of-the-dead.sym, WZ_BUILD_DIR honoured).

    python3 tools/decor_density.py [seeds=1000] [depth ...]
    python3 tools/decor_density.py [seeds=1000] --decor2 [--md]     # DECOR2 old-vs-new metric report (decor_rules2.md §5)
"""
import os
import sys
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tests"))
sys.path.insert(0, os.path.join(REPO, "tools"))
import decorgen as DG           # noqa: E402
import decorgen2 as D2          # noqa: E402
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
    objs = None

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
        if real:
            self.objs.append(dict(name=name, cls=cls, row=row, col=col, w=w, h=h, src="old", grp=None))
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
    room.objs = []
    DG.patch_pass(room, rng, depth)
    before = list(room.m)
    DG.cobwebs(room, rng, depth)
    room.ncob = sum(1 for a, b in zip(before, room.m) if a != b)
    room.objs += [dict(name="COBWEB", cls=DG.C_COMP + 1, row=i // COLS, col=i % COLS, w=1, h=1, src="old", grp=None)
                  for i, (a, b) in enumerate(zip(before, room.m)) if a != b]
    mn = DG.menu(depth)
    for _ in range(DG.tries_of(depth)):
        room.try_place(rng, mn[rng.rnd(len(mn))], None)
    return room.m, room


# ----------------------------------------------------------------------------------------------
# DECOR2 metrics (docs/design/decor_rules2.md §5): the same measurements on the old and the new deriver
# ----------------------------------------------------------------------------------------------
LIGHTS = ("TORCH_TALL", "TORCH_SLIM", "BRAZIER", "BRAZIER_BIG")
PLANNED = ("frame", "centre", "flank", "gallery", "single")


def patch_ids(depth):
    ids = {DG.D["T_WALL_DITHER"], DG.D["T_WALL_PATCH"], DG.D["T_WALL_FADE"]}
    for o in DG.LEVEL[depth]:
        if o[0] in ("PATCH_A", "PATCH_B"):
            ids |= set(range(o[1], o[1] + o[2] * o[3]))
    return ids


def comps(cells):
    """sizes of the 8-connected components of a set of (r, c)."""
    left, out = set(cells), []
    while left:
        stack = [left.pop()]
        n = 1
        while stack:
            r, c = stack.pop()
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    q = (r + dr, c + dc)
                    if q in left:
                        left.remove(q)
                        stack.append(q)
                        n += 1
        out.append(n)
    return out


def gap(a, b):
    """empty cols between two objects' column spans (negative = overlap)."""
    return max(b["col"] - (a["col"] + a["w"]), a["col"] - (b["col"] + b["w"]))


def room_metrics(base, m, objs, flags, key, depth):
    """-> dict of per-room measurements (summarize() says what each means)."""
    st, pit = D2.analyze(base)
    out = {}
    vis = [o for o in objs if o["cls"] in (DG.C_MOUNT, DG.C_CEIL, DG.C_FLOOR)]
    lights = [o for o in objs if o["name"] in LIGHTS]
    pids = patch_ids(depth)
    cells = [(i // COLS, i % COLS) for i, t in enumerate(m) if t in pids]
    out["speckle"] = sum(1 for n in comps(cells) if n == 1)

    def near(o):
        s = o["row"] // 9
        for l in lights:
            if l is not o and l["row"] // 9 == s and gap(o, l) <= 3:
                return True
        for sd, edge, kind, _n in st[s]["faces"]:
            if kind == "wall" and ((sd == "L" and 0 <= o["col"] - edge <= 3) or
                                   (sd == "R" and 0 <= edge - (o["col"] + o["w"] - 1) <= 3)):
                return True
        return False

    out["vis"] = len(vis)
    out["anch"] = sum(1 for o in vis if o["src"] in PLANNED or (o["cls"] == DG.C_CEIL and near(o)))
    pats = [o for o in objs if o["cls"] in (DG.C_PATCH, DG.C_COMP)]
    out["patches"] = len(pats)
    out["patch_anch"] = sum(1 for o in pats if near(o))
    out["patch_anch"] = sum(1 for o in pats if near(o))
    # mirrored pair: same record, same row, the gap's centre = a focal / object centre +- 1/2 col
    mir = framed = False
    for i, a in enumerate(vis):
        for b in vis[i + 1:]:
            if a["name"] != b["name"] or a["row"] != b["row"]:
                continue
            a_, b_ = (a, b) if a["col"] < b["col"] else (b, a)
            lo, hi = a_["col"] + a_["w"], b_["col"] - 1
            if hi < lo or hi - lo > 12:
                continue
            mid = (lo + hi) / 2
            s = a_["row"] // 9
            cand = [(c + (w - 1) / 2, k) for c, w, k in st[s]["focal"]]
            if s == 0 and pit:
                cand.append((pit[0] + (pit[1] - 1) / 2, "pit"))
            cand += [(o["col"] + (o["w"] - 1) / 2, "obj") for o in vis if o is not a and o is not b
                     and o["row"] // 9 == s and lo <= o["col"] and o["col"] + o["w"] - 1 <= hi]
            for cc, kind in cand:
                if abs(cc - mid) <= 0.5:
                    mir = True
                    framed = framed or (kind == "shaft" and a["name"] in LIGHTS)
    out["mirrored"], out["lair_framed"] = mir, framed
    nl = len(lights)
    out["nlights"], out["lit"] = nl, nl > 0
    # near-duplicates: same record, same storey, <= 6 empty cols apart, not one pair / gallery / cluster
    out["neardup"] = sum(1 for i, a in enumerate(vis) for b in vis[i + 1:]
                         if a["name"] == b["name"] and a["row"] // 9 == b["row"] // 9 and gap(a, b) <= 6
                         and not (a["grp"] is not None and a["grp"] == b["grp"]))
    # fill spacing: gaps between neighbouring mount / floor objects of a storey (not within one group)
    gaps = []
    for s in (0, 1):
        mf = sorted((o for o in vis if o["cls"] in (DG.C_MOUNT, DG.C_FLOOR) and o["row"] // 9 == s),
                    key=lambda o: o["col"])
        for a, b in zip(mf, mf[1:]):
            if a["row"] + a["h"] <= b["row"] or b["row"] + b["h"] <= a["row"]:
                continue                                                         # no shared rows (banner over a brazier)
            if (a["src"] in ("fill", "old") or b["src"] in ("fill", "old")) \
                    and not (a["grp"] is not None and a["grp"] == b["grp"]):     # unrelated = one of them is fill / old
                gaps.append(b["col"] - (a["col"] + a["w"]))
    out["gaps"] = gaps
    # negative space: largest decor-free col run in rows 1..7 of each storey
    free = []
    for s in (0, 1):
        best = cur = 0
        for c in range(1, COLS - 1):
            if any(DG.is_decor(m[(9 * s + r) * COLS + c]) for r in range(1, 8)):
                cur = 0
            else:
                cur += 1
                best = max(best, cur)
        free.append(best)
    out["free"] = free
    out["empty"] = sum(1 for s in (0, 1) if not any(DG.is_decor(m[(9 * s + r) * COLS + c]) for r in range(9) for c in range(COLS)))
    # clearance (R3)
    mf = [o for o in vis if o["cls"] in (DG.C_MOUNT, DG.C_FLOOR)]
    out["margin"] = sum(1 for o in mf if o["col"] <= 2 or o["col"] + o["w"] - 1 >= 29)
    out["margin_ceil"] = sum(1 for o in vis if o["cls"] == DG.C_CEIL and o["name"] != "MOSS"
                             and (o["col"] <= 2 or o["col"] + o["w"] - 1 >= 29))
    zone = type("Z", (), {"pit": pit})()
    out["pit_zone"] = sum(1 for o in vis if o["cls"] == DG.C_FLOOR and D2.Room2.zone_hit(zone, o["col"], o["w"], o["row"]))
    # gradient
    cob = [o for o in objs if o["name"] == "COBWEB"]
    out["cob"], out["cob0"] = len(cob), sum(1 for o in cob if o["row"] < 9)
    moss = [o for o in objs if o["name"] == "MOSS"]
    out["moss_cells"] = sum(o["w"] for o in moss)
    out["moss_strip_cells"] = sum(o["w"] for o in moss if o["w"] >= 2)
    # roles
    out["start_s1"] = sum(1 for o in mf if o["row"] >= 9) if flags & D2.RDF_START else None
    out["deadend_dark"] = (not nl) if flags & D2.RDF_DEADEND and not flags & (D2.RDF_START | D2.RDF_LAIR) and not key else None
    out["lair_lit"] = bool(nl) if flags & D2.RDF_LAIR else None
    out["key_lit"] = bool(nl) if key else None
    return out


def collect(n, depths, mode):
    """-> {depth: [room metric dicts]}; mode 'old' = decorgen via Probe, 'new' = decorgen2."""
    res = {d: [] for d in depths}
    for d in depths:
        for seed in range(1, n + 1):
            blk = bytes(G.generate(d, seed * 7919 & 0xFFFF or 1))
            for r in range(G.NCELL):
                o = G.LOFF_DESC + r * S["RD_STRIDE"]
                fl = blk[o + S["RD_FLAGS"]]
                if not fl & S["RDF_PRESENT"] or fl & S["RDF_SANCTUM"]:
                    continue
                base = RM.base_room(blk, r)
                sd = blk[o + S["RD_SEED"]] | blk[o + S["RD_SEED"] + 1] << 8
                rid, flags, key = RM.room_role(blk, r)
                if mode == "old":
                    m, room = decorate(base, d, sd)
                    objs = room.objs
                    nl, ng, nw, mw = room.nl, room.ng, room.nw, room.maxwall
                else:
                    m, _al, objs = D2.decorate(base, d, sd, True, (rid, flags, key))
                    nl = sum(1 for x in objs if x["name"] in LIGHTS)
                    ng = sum(x["w"] for x in objs if x["name"] in LIGHTS)
                    nw = sum(DG.COMP_AREA if x["cls"] == DG.C_COMP else x["w"] * x["h"]
                             for x in objs if x["cls"] in (DG.C_PATCH, DG.C_COMP))
                    mw = DG.WALL_MAX[d]
                assert nl <= DG.MAX_LARGE and ng <= DG.MAX_GLYPH and nw <= mw, (mode, d, seed, r, nl, ng, nw)
                # solidity / footprint: decor only ever lands on T_AIR cells of the base map
                assert all(a == b or a == DG.T_AIR for a, b in zip(base, m)), (mode, d, seed, r)
                mm = room_metrics(base, m, objs, flags, key, d)
                mm["mood"] = getattr(objs, "mood", None)
                mm["cells"] = sum(1 for a, b in zip(base, m) if a != b)
                mm["objects"] = len(objs)
                mm["ids"] = len({t for t in m if 32 <= t < 60} - {t for t in base if 32 <= t < 60})
                mm["flags"], mm["key"] = flags, key
                res[d].append(mm)
    return res


def median(v):
    v = sorted(v)
    return v[len(v) // 2] if v else float("nan")


def summarize(rooms):
    """metric name -> value for a list of per-room dicts."""
    n = len(rooms) or 1
    sm = lambda k: sum(r[k] for r in rooms)                                     # noqa: E731
    sel = lambda k: [r[k] for r in rooms if r[k] is not None]                    # noqa: E731
    frac = lambda v: 100 * sum(1 for x in v if x) / len(v) if v else float("nan")   # noqa: E731
    gaps = [g for r in rooms for g in r["gaps"]]
    free = [f for r in rooms for f in r["free"]]
    lit = [r for r in rooms if r["lit"]]
    return {
        "rooms": len(rooms),
        "objects/room": sm("objects") / n,
        "decor cells/room": sm("cells") / n,
        "bare rooms %": 100 * sum(1 for r in rooms if not r["objects"]) / n,
        "visible obj/room (mount+ceil+floor)": sm("vis") / n,
        "speckle cells/room": sm("speckle") / n,
        "rooms with speckle %": 100 * sum(1 for r in rooms if r["speckle"]) / n,
        "anchored ratio % (visible objs)": 100 * sm("anch") / (sm("vis") or 1),
        "patches anchored % (light/wall)": 100 * sm("patch_anch") / (sm("patches") or 1),
        "mirrored rooms % (all)": frac([r["mirrored"] for r in rooms]),
        "mirrored % of rooms with a light": frac([r["mirrored"] for r in lit]),
        "mirrored % of LIT-mood rooms": frac([r["mirrored"] for r in rooms if r["mood"] == "LIT"]),
        "mood LIT %": 100 * sum(1 for r in rooms if r["mood"] == "LIT") / n,
        "mood DIM %": 100 * sum(1 for r in rooms if r["mood"] == "DIM") / n,
        "mood DARK %": 100 * sum(1 for r in rooms if r["mood"] == "DARK") / n,
        "mood CALM %": 100 * sum(1 for r in rooms if r["mood"] == "CALM") / n,
        "near-dup rooms %": 100 * sum(1 for r in rooms if r["neardup"]) / n,
        "gap min (mount/floor)": min(gaps) if gaps else float("nan"),
        "gap median": median(gaps),
        "gaps < 3 %": 100 * sum(1 for g in gaps if g < 3) / (len(gaps) or 1),
        "storeys with free run >= 8 %": 100 * sum(1 for f in free if f >= 8) / (len(free) or 1),
        "median largest free run": median(free),
        "empty storeys %": 100 * sm("empty") / (2 * n),
        "margin violations mount/floor": sm("margin"),
        "margin violations chain": sm("margin_ceil"),
        "pit-zone floor objects": sm("pit_zone"),
        "lair: lights flank grate %": frac([r["lair_framed"] for r in rooms if r["flags"] & D2.RDF_LAIR]),
        "start: storey-1 mount/floor objs": sum(sel("start_s1")),
        "dead ends without lights %": frac(sel("deadend_dark")),
        "lair rooms lit %": frac(sel("lair_lit")),
        "key rooms lit %": frac(sel("key_lit")),
        "rooms with 0 lights %": 100 * sum(1 for r in rooms if not r["nlights"]) / n,
        "rooms with 2 lights %": 100 * sum(1 for r in rooms if r["nlights"] >= 2) / n,
        "cobwebs/room": sm("cob") / n,
        "cobwebs on storey 0 %": 100 * sm("cob0") / (sm("cob") or 1),
        "moss cells in strips %": 100 * sm("moss_strip_cells") / sm("moss_cells") if sm("moss_cells") else float("nan"),
        "distinct decor ids/room": sm("ids") / n,
    }


def decor2_report(n, depths, md=False):
    old, new = collect(n, depths, "old"), collect(n, depths, "new")
    so = {d: summarize(old[d]) for d in depths}
    sn = {d: summarize(new[d]) for d in depths}
    so["all"] = summarize([r for d in depths for r in old[d]])
    sn["all"] = summarize([r for d in depths for r in new[d]])
    cols = [f"D{d}" for d in depths] + ["all"]
    fmt = lambda v: "-" if v != v else (f"{v:.0f}" if abs(v) >= 100 or v == int(v) else f"{v:.2f}")   # noqa: E731
    if md:
        print("| metric | " + " | ".join(cols) + " |")
        print("|---|" + "---|" * len(cols))
    else:
        print(f"{n} seeds per depth, non-Sanctum rooms; old = decorgen.py, new = decorgen2.py (DECOR2 P2)")
        print(f"{'metric':42s} " + " ".join(f"{c:>8s}" for c in cols))
    for k in so["all"]:
        for tag, S_ in (("old", so), ("new", sn)):
            cells = [fmt(S_[d][k]) for d in depths] + [fmt(S_["all"][k])]
            if md:
                print(f"| {k} ({tag}) | " + " | ".join(cells) + " |")
            else:
                print(f"{k + ' ' + tag:42s} " + " ".join(f"{c:>8s}" for c in cells))
    return so, sn


def main(argv):
    flags = [a for a in argv[1:] if a.startswith("--")]
    argv = [argv[0]] + [a for a in argv[1:] if not a.startswith("--")]
    n = int(argv[1]) if len(argv) > 1 else 1000
    depths = [int(x) for x in argv[2:]] or list(range(1, 9))
    if "--decor2" in flags:
        decor2_report(n, depths, "--md" in flags)
        return
    rows = {}
    for d in depths:
        agg, res, att = Counter(), Counter(), Counter()
        nrooms = checked = 0
        for seed in range(1, n + 1):
            blk = bytearray(G.generate(d, seed * 7919 & 0xFFFF or 1))
            for r in range(G.NCELL):                # LARGER-D: the 3 x 4 room grid
                o = G.LOFF_DESC + r * S["RD_STRIDE"]
                fl = blk[o + S["RD_FLAGS"]]
                if not fl & S["RDF_PRESENT"] or fl & S["RDF_SANCTUM"]:
                    continue
                base = RM.base_room(bytes(blk), r)
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
