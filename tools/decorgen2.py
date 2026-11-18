#!/usr/bin/env python3
"""decorgen2.py - DECOR2 reference model (docs/design/decor_rules2.md, package P2 = P1 + R4..R7).

decorate(m, depth, seed, live=True, room=None) -> (m', anim, objs)
  m, depth, seed, live, anim  exactly as tools/decorgen.py decorate() (576 tile ids as build_room_map
                              leaves them, before decor; ANIM_LIST bytes)
  room  (rid, rd_flags, key) of the room (rid = room id 0..11, rd_flags = the descriptor's RDF_* byte,
        key = it is a key room: LVL_KEYROOM / LVL_KEYROOM2; the descriptor's RDF_KEY bit is never set);
        None = an ordinary room 0.
  objs  placement log [dict(name, cls, row, col, w, h, src, grp)] (metrics / previews; not Z80 state).
The old deriver (tools/decorgen.py) is untouched: this is a separate module that reuses its records,
ids, budgets and Room writer (so both stay in step with tileset_ids.inc).

Pass order (rules R1..R8 of the design doc; every random draw from the private xorshift, RNG order is
part of the contract the Z80 must repeat):
  1. mood           rnd(24), always one draw (R4); START -> CALM, LAIR / KEY -> LIT, dead end DARK 2/3
                    DIM 1/3, else by depth (LIT / DIM / DARK weights below)
  2. compositions   per mood (R5): FRAME / CENTRE / GALLERY / SINGLE; the pair is atomic; mirrored
  3. light lock     nl := MAX_LARGE: no light can come from the fill (C10)
  4. light pools    (R6) one patch cluster on a light's outer side (pair: at most one pool)
  5. patches        (R7) no pool -> one wall-anchored cluster; a 2nd (1/2, DARK 3/4), also anchored;
                    the old random 8-try loop only as a fallback
  6. cobwebs        (R7) odds by storey and mood, cap 2 (DARK 3)
  7. chains / moss  (R7) DARK + DIM: a chain cluster of 2-3 at pitch 2; DARK: a moss strip first
  8. fill           (R8) the old menu loop, tries by mood (LIT 6, DIM 8, DARK 6, CALM 6 and none of
                    mount / floor class on storey 1), R3: cols 3..28, 3-col halo, pit jump zone
R1: the three 1x1 patch records are gone from the menu; R2: MOSS = tiled strips w 2 / 3, support over
the full width.  No new tile id, no new art.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import decorgen as DG  # noqa: E402

COLS, ROWS = DG.COLS, DG.ROWS
T_AIR, T_BRICK = DG.T_AIR, DG.T_BRICK
MAX_LARGE, MAX_GLYPH = DG.MAX_LARGE, DG.MAX_GLYPH
C_MOUNT, C_CEIL, C_FLOOR, C_PATCH, C_BRICK, C_COMP = (DG.C_MOUNT, DG.C_CEIL, DG.C_FLOOR,
                                                      DG.C_PATCH, DG.C_BRICK, DG.C_COMP)
F_MOSS, F_TILED, F_LARGE = DG.F_MOSS, DG.F_TILED, DG.F_LARGE
T_RUBBLE = DG.D["T_RUBBLE"]
T_HOLE_L = DG.D["T_HOLE_L"]

# RD_FLAGS bits (src/level_defs.asm)
RDF_START, RDF_LAIR, RDF_DEADEND, RDF_KEY = 0x02, 0x04, 0x08, 0x10

# moods
LIT, DIM, DARK, CALM = "LIT", "DIM", "DARK", "CALM"
FILL_TRIES = {LIT: 6, DIM: 8, DARK: 6, CALM: 6}
FILL_BONUS = {2: 3}    # user 2026-11-17: D2 (many small objects, wall budget 13) gets 3 more fill tries
# R3 columns: mount / ceiling / floor 3..28; textures (patch, moss) 2..29
CMIN2 = {C_MOUNT: 3, C_CEIL: 3, C_FLOOR: 3, C_PATCH: 2, C_BRICK: 0, C_COMP: 2}
PAIR_RETRY = True      # a pair that does not fit at gap g tries the other gap before the SINGLE fallback
DEDUP = True           # fill: no same record on the same storey within 6 empty cols (measured near-dup rule)
DEDUP_GAP = 6
HALO_FILL = 3          # R3: 3-col halo for a fill mount / floor object
PIT_BEFORE, PIT_AFTER = 4, 3

# the depth's pair light (R5: floor lights on D2 / D3 / D5 / D8) and the lights SINGLE may pick
PAIR_LIGHT = {1: "TORCH_TALL", 2: "BRAZIER", 3: "BRAZIER_BIG", 4: "TORCH_TALL", 5: "BRAZIER_BIG",
              6: "TORCH_SLIM", 7: "TORCH_TALL", 8: "BRAZIER_BIG"}


def _rec(depth, name):
    return next(o for o in DG.LEVEL[depth] if o[0] == name)


def _moss(depth, w):
    """R2: MOSS as a tiled w-cell strip (same id, F_TILED)."""
    n, base, _w, _h, fl, cls = _rec(depth, "MOSS")
    return (n, base, w, 1, fl | F_TILED, cls)


def menu2(depth):
    """R1 / R2: CHAIN + the depth's objects, MOSS -> two strip records (w 2, w 3)."""
    out = [DG.COMMON[0]]            # CHAIN is the only common record left
    for o in DG.LEVEL[depth]:
        if o[0] == "MOSS":
            out += [_moss(depth, 2), _moss(depth, 3)]
        else:
            out.append(o)
    return out


def level_info(depth):
    objs = DG.LEVEL[depth]
    large = [o for o in objs if o[4] & F_LARGE]
    plain = [o for o in objs if o[5] == C_MOUNT and not o[4] & F_LARGE]
    pats = [o for o in objs if o[0] in ("PATCH_A", "PATCH_B")] or [DG.COMP]
    return dict(pair=_rec(depth, PAIR_LIGHT[depth]), lights=large, plain=plain, pats=pats,
                has_moss=any(o[0] == "MOSS" for o in objs))


def is_ladder(t):
    return DG.T_LAD_L <= t <= DG.T_HOLE_R


# ----------------------------------------------------------------------------------------------
# structure scan (the planner's "one map-row scan per storey")
# ----------------------------------------------------------------------------------------------
def analyze(m):
    """-> per storey s: dict(runs = air runs of storey row 3 [(a, b)], faces = [(side, col, kind,
    runlen)] ('L': first air col of a run, 'R': its last; kind 'wall' / 'ladder'), focal = [(c, w,
    kind)] (interior non-air runs of row 3: ladder / block; the arrival shaft; the lair grate; the
    pit), span = widest clear run clipped to cols 3..28 and shrunk 1 for the ring or None)
    plus pit = (p, W) | None."""
    st = []
    pit = None
    row = DG.D["FLOOR_ROW0"]
    c = 1
    while c < 31:                                   # pit = T_AIR cells of the storey-0 floor row
        if m[row * COLS + c] == T_AIR:
            a = c
            while c < 31 and m[row * COLS + c] == T_AIR:
                c += 1
            pit = (a, c - a)
        else:
            c += 1
    for s in (0, 1):
        r3 = (9 * s + 3) * COLS
        runs, c = [], 0
        while c < COLS:
            if m[r3 + c] == T_AIR:
                a = c
                while c < COLS and m[r3 + c] == T_AIR:
                    c += 1
                runs.append((a, c - 1))
            else:
                c += 1
        faces = []
        for a, b in runs:
            if a >= 1:
                faces.append(("L", a, "ladder" if is_ladder(m[r3 + a - 1]) else "wall", b - a + 1))
            if b <= COLS - 2:
                faces.append(("R", b, "ladder" if is_ladder(m[r3 + b + 1]) else "wall", b - a + 1))
        focal, c = [], 0
        while c < COLS:                             # interior obstacles (not touching an edge col)
            if m[r3 + c] != T_AIR:
                a = c
                while c < COLS and m[r3 + c] != T_AIR:
                    c += 1
                if a > 0 and c <= COLS - 1:
                    kind = "ladder" if any(is_ladder(m[r3 + k]) for k in range(a, c)) else "block"
                    focal.append((a, c - a, kind))
            else:
                c += 1
        if s == 0:                                  # the arrival shaft: 3 rubble cells in map row 0
            for a in range(1, COLS - 3):
                if all(m[a + k] == T_RUBBLE for k in range(3)):
                    focal.append((a, 3, "arrival"))
        else:                                       # the down shaft / lair grate: 3 hole cells in map row 17
            for a in range(1, COLS - 3):
                if all(m[17 * COLS + a + k] == T_HOLE_L + k for k in range(3)):
                    focal.append((a, 3, "shaft"))
        best = None
        for a, b in runs:
            lo, hi = max(a, 3), min(b, 28)
            if hi - lo + 1 >= 3 and (best is None or hi - lo > best[1] - best[0]):
                best = (lo, hi)
        span = (best[0] + 1, best[1] - 1) if best else None
        st.append(dict(runs=runs, faces=faces, focal=focal, span=span))
    return st, pit


# ----------------------------------------------------------------------------------------------
# the room under construction
# ----------------------------------------------------------------------------------------------
class Room2(DG.Room):
    def __init__(self, m, live, maxwall, depth):
        super().__init__(m, live, maxwall)
        self.depth = depth
        self.info = level_info(depth)
        self.st, self.pit = analyze(self.m)
        self.objs = []
        self.lights = []          # placed light records (for the pools)
        self.grp = 0

    # -- geometry -----------------------------------------------------------------------------
    def row_of(self, obj, s, r0=0):
        cls, h = obj[5], obj[3]
        if cls in (C_PATCH, C_BRICK, C_COMP):
            return 9 * s + 1 + r0
        if cls == C_MOUNT:
            return 9 * s + 1
        if cls == C_CEIL:
            return 9 * s
        return 9 * s + 8 - h

    def zone_hit(self, col, w, row):
        if self.pit is None or row >= 9:
            return False
        p, pw = self.pit
        return col <= p + pw + PIT_AFTER and col + w - 1 >= p - PIT_BEFORE

    def can_place(self, obj, row, col, halo=1, ring="full", cmin=None, budget=True):
        name, base, w, h, fl, cls = obj
        cmin = CMIN2[cls] if cmin is None else cmin
        if col < cmin or col + w - 1 > COLS - 1 - cmin or row < 0 or row + h > ROWS - 1:
            return False
        area = DG.COMP_AREA if cls == C_COMP else w * h
        if budget and not self.budget_ok(w, h, fl, cls, area):
            return False
        m = self.m
        if any(m[(row + dy) * COLS + col + dx] != T_AIR for dy in range(h) for dx in range(w)):
            return False
        if cls == C_CEIL:                          # R2: every cell has floor above (moss: not row 0)
            if row == 0:
                if fl & F_MOSS:
                    return False
            elif not all(DG.floorish(m[(row - 1) * COLS + col + dx]) for dx in range(w)):
                return False
        elif cls == C_FLOOR:
            if not all(DG.floorish(m[(row + h) * COLS + col + dx]) for dx in range(w)):
                return False
            if self.zone_hit(col, w, row):         # R3 pit jump zone
                return False
        for rr in range(max(row - 1, 0), min(row + h, ROWS - 1) + 1):
            for cc in range(max(col - halo, 0), min(col + w - 1 + halo, COLS - 1) + 1):
                t = m[rr * COLS + cc]
                if is_ladder(t) or (ring == "full" and DG.is_decor(t)):
                    return False
        return True

    def place(self, obj, row, col, src, grp=None, **kw):
        if not self.can_place(obj, row, col, **kw):
            return False
        self._write(obj, row, col, src, grp)
        return True

    def _write(self, obj, row, col, src, grp):
        m = self.m
        name, base, w, h, fl, cls = obj
        area = DG.COMP_AREA if cls == C_COMP else w * h
        self.objs.append(dict(name=name, cls=cls, row=row, col=col, w=w, h=h, src=src, grp=grp))
        if cls == C_COMP:
            m[row * COLS + col] = DG.D["T_WALL_PATCH"]
            m[row * COLS + col + 1] = DG.D["T_WALL_FADE"]
            m[(row + 1) * COLS + col] = DG.D["T_WALL_DITHER"]
            self.nw += DG.COMP_AREA
            return
        ph = (col + row) & 7
        alt, i = base + area, base
        for dy in range(h):
            for dx in range(w):
                m[(row + dy) * COLS + col + dx] = i
                if not fl & F_TILED:
                    i += 1
                typ = 0
                if fl & DG.F_GROW0 and (dy == 0 or (dy == 1 and (fl & DG.F_GROW1 or (fl & DG.F_LO0 and dx == 0)))):
                    typ, alt = alt, alt + 1
                if typ and self.live:
                    self.anim += [col + dx, row + dy, typ, ph]
        self.nl += 1 if fl & F_LARGE else 0
        self.ng += DG.counts(w, h, fl)
        self.nw += area if cls in (C_PATCH, C_BRICK) else 0
        if fl & F_LARGE:
            self.lights.append(dict(obj=obj, row=row, col=col, s=row // 9, grp=grp))

    def group(self, items, src):
        """atomic placement of [(obj, row, col, tag)]: all or none (pairs, galleries, clusters)."""
        snap = (list(self.m), self.nl, self.ng, self.nw, list(self.anim), len(self.objs), len(self.lights))
        self.grp += 1
        for obj, row, col, tag in items:
            if not self.can_place(obj, row, col):
                break
            self._write(obj, row, col, src, self.grp)
            self.objs[-1]["tag"] = tag
            if self.lights and self.lights[-1]["row"] == row and self.lights[-1]["col"] == col:
                self.lights[-1]["tag"] = tag
        else:
            return True
        self.m, self.nl, self.ng, self.nw, self.anim = snap[0], snap[1], snap[2], snap[3], snap[4]
        del self.objs[snap[5]:]
        del self.lights[snap[6]:]
        return False


# ----------------------------------------------------------------------------------------------
# R4 mood
# ----------------------------------------------------------------------------------------------
def draw_mood(rng, depth, flags, key):
    x = rng.rnd(24)                      # always one draw (fixed RNG order)
    if flags & RDF_START:
        return CALM
    if flags & RDF_LAIR or key:
        return LIT
    if flags & RDF_DEADEND:
        return DARK if x < 16 else DIM                   # DARK 2/3, DIM 1/3
    if depth <= 3:
        return LIT if x < 6 else DIM if x < 18 else DARK  # 1/4, 1/2, 1/4
    if depth <= 7:
        return LIT if x < 6 else DIM if x < 15 else DARK  # 1/4, 3/8, 3/8
    return LIT if x < 12 else DIM                         # D8: 1/2, 1/2


# ----------------------------------------------------------------------------------------------
# R5 templates
# ----------------------------------------------------------------------------------------------
def light_pair(R, rng, s, fc, fw, src):
    L = R.info["pair"]
    g0 = 1 + rng.rnd(2)
    row = R.row_of(L, s)
    for g in (g0, 3 - g0):             # gap g = 1 + rnd(2), the other gap if the first does not fit (PAIR_RETRY)
        cl, cr = fc - g - L[2], fc + fw + g
        if R.group([(L, row, cl, "L"), (L, row, cr, "R")], src):
            return cl, cr
        if not PAIR_RETRY:
            break
    return None


def single_light(R, rng, s, fc=None, fw=0):
    """one light on the side that fits: beside a focal (g = 1) or wall-anchored."""
    L = R.info["lights"][rng.rnd(len(R.info["lights"]))] if len(R.info["lights"]) > 1 else R.info["lights"][0]
    row = R.row_of(L, s)
    cands = []
    if fc is not None:                                  # fallback of a failed pair: beside the focal
        side = rng.rnd(2)
        cands = [fc - 1 - L[2], fc + fw + 1]
        if side:
            cands.reverse()
    else:
        ladders = [f for f in R.st[s]["focal"] if f[2] == "ladder"]
        walls = [f for f in R.st[s]["faces"] if f[2] == "wall" and f[3] >= 6]
        pick = rng.rnd(2)
        if ladders and (pick or not walls):
            c0, w0, _ = ladders[rng.rnd(len(ladders))]
            side = rng.rnd(2)
            cands = [c0 - 1 - L[2], c0 + w0 + 1]
            if side:
                cands.reverse()
        if walls:
            sd, edge, _k, _n = walls[rng.rnd(len(walls))]
            off = rng.rnd(3)
            cands += [max(edge + 1, 3) + off] if sd == "L" else [min(edge - 1, 28) - off - L[2] + 1]
    for c in cands:
        if R.place(L, row, c, "single"):
            R.lights[-1]["tag"] = "S"
            return True
    return False


def centre(R, rng, s, lit):
    """CENTRE: a non-animated mount object at the middle of the widest clear span, flanked by the
    mirrored light pair (lit) or, 1 in 2, by a second plain object (unlit).  -> (col, w) | None."""
    plain, span = R.info["plain"], R.st[s]["span"]
    if not plain or span is None:
        return None
    obj = plain[rng.rnd(len(plain))]
    lo, hi = span
    w = obj[2]
    if hi - lo + 1 < w:
        return None
    col = lo + (hi - lo + 1 - w) // 2
    if not R.place(obj, R.row_of(obj, s), col, "centre"):
        return None
    if lit:
        if light_pair(R, rng, s, col, w, "frame") is None:
            single_light(R, rng, s, col, w)
    else:
        flank = [o for o in plain if o is not obj]
        if flank and rng.rnd(2):
            fo = flank[rng.rnd(len(flank))]
            g = 1 + rng.rnd(2)
            row = R.row_of(fo, s)
            R.group([(fo, row, col - g - fo[2], "L"), (fo, row, col + w + g, "R")], "flank")
    return col, w


def gallery(R, rng, s, align=None):
    """GALLERY: k copies of one plain mount object at a fixed pitch, centred in the widest span
    (aligned to `align` cols in the lair).  Atomic; skipped if the span is too short."""
    plain, span = R.info["plain"], R.st[s]["span"]
    if not plain or span is None:
        return False
    obj = plain[rng.rnd(len(plain))]
    w = obj[2]
    row = R.row_of(obj, s)
    if align:
        cols = [c + (a_w - w) // 2 for c, a_w in align]
    else:
        k = 3 if w == 1 else 2
        pitch = w + 3 + rng.rnd(2)
        lo, hi = span
        total = (k - 1) * pitch + w
        if hi - lo + 1 < total:
            return False
        c0 = lo + (hi - lo + 1 - total) // 2
        cols = [c0 + i * pitch for i in range(k)]
    return R.group([(obj, row, c, "G%d" % i) for i, c in enumerate(cols)], "gallery")


def frame(R, rng, s, focal, src="frame"):
    """FRAME on a focal (c, w, kind): the mirrored pair, else one light beside it.
    -> (pair cols | None, any light placed)."""
    fc, fw, _k = focal
    r = light_pair(R, rng, s, fc, fw, src)
    if r:
        return r, True
    return None, single_light(R, rng, s, fc, fw)


def pick_focal(R, rng, s, role=None):
    fl = [f for f in R.st[s]["focal"] if f[2] != "shaft" or role == "shaft"]
    if s == 0 and R.pit and R.info["pair"][5] != C_FLOOR:
        fl.append((R.pit[0], R.pit[1], "pit"))     # a pit is a focal for mount lights only
    if role:
        want = [f for f in fl if f[2] == role]
        if want:
            return want[0]
    return fl[rng.rnd(len(fl))] if fl else None


def lit_storey(R, rng, s, kind, role=None):
    """one lit storey: FRAME (falls to CENTRE without a focal) or CENTRE; a storey that got no light
    gets a wall-anchored single so a LIT room never has none.  -> the mirrored pair's cols | None."""
    if kind == "frame":
        f = pick_focal(R, rng, s, role)
        if f:
            pair, any_ = frame(R, rng, s, f)
            if any_:
                return pair
        kind = "centre"
    centre(R, rng, s, True)
    if not any(l["s"] == s for l in R.lights):
        single_light(R, rng, s)
    return None


def unlit_storey(R, rng, s):
    if rng.rnd(2):
        gallery(R, rng, s)
    else:
        centre(R, rng, s, False)


def compose(R, rng, mood, flags, rid, key):
    if mood == CALM:                                       # start room: one composition on storey 0
        arr = [f for f in R.st[0]["focal"] if f[2] == "arrival"]
        if arr:
            frame(R, rng, 0, arr[0])
        else:
            centre(R, rng, 0, False)
    elif mood == LIT and flags & RDF_LAIR:                 # focal = the grate; storey 0 gallery on its axis
        r = lit_storey(R, rng, 1, "frame", role="shaft")
        if isinstance(r, tuple):
            gallery(R, rng, 0, align=[(r[0], R.info["pair"][2]), (r[1], R.info["pair"][2])])
        else:
            unlit_storey(R, rng, 0)
    elif mood == LIT:
        t = 1 if key else (rng.rnd(3) + rid) % 3
        sl = rng.rnd(2)
        if t == 2:                                          # gallery storey + the light storey
            gallery(R, rng, sl)
            lit_storey(R, rng, 1 - sl, "frame")
        else:
            lit_storey(R, rng, sl, "frame" if t == 0 else "centre")
            unlit_storey(R, rng, 1 - sl)
    elif mood == DIM:
        s = rng.rnd(2)
        if not single_light(R, rng, s):
            single_light(R, rng, 1 - s)


# ----------------------------------------------------------------------------------------------
# R6 pools, R7 textures
# ----------------------------------------------------------------------------------------------
def pool_at(R, rng, light, outer):
    pats = R.info["pats"]
    obj = pats[rng.rnd(len(pats))]
    pw, ph = obj[2], obj[3]
    lc, lw = light["col"], light["obj"][2]
    col = lc - pw - 1 if outer == "L" else lc + lw + 1
    s = light["s"]
    top = min(light["row"] - 9 * s + rng.rnd(2), 6 - ph)
    return R.place(obj, 9 * s + max(top, 1), col, "pool", ring="lad")


def pools(R, rng, mood):
    made, seen = 0, set()
    for l in list(R.lights):
        if l["grp"] in seen:
            continue
        pair = [x for x in R.lights if x["grp"] == l["grp"]] if l["grp"] else [l]
        if l["grp"]:
            seen.add(l["grp"])
        if len(pair) == 2:
            if rng.rnd(2):
                continue
            pick = pair[rng.rnd(2)]
            outers = [pick.get("tag", "L")]
        else:
            if mood != DIM and rng.rnd(2):
                continue
            pick = pair[0]
            first = "L" if rng.rnd(2) == 0 else "R"
            outers = [first, "R" if first == "L" else "L"]
        for o in outers:                                    # preferred side, then the other for a single
            if pool_at(R, rng, pick, o):
                made += 1
                break
    return made


def anchored_patch(R, rng, s=None):
    """one wall-anchored cluster (cols within 3 of a wall / block face, rows 1..5); the old random
    8-try loop is the fallback.  -> True if placed."""
    pats = R.info["pats"]
    if s is None:
        s = rng.rnd(2)
    obj = pats[rng.rnd(len(pats))]
    w, h = obj[2], obj[3]
    top = 1 + rng.rnd(6 - h)
    faces = [f for f in R.st[s]["faces"] if f[2] == "wall" and f[3] >= w + 2]
    if faces:
        k0 = rng.rnd(len(faces))
        off = rng.rnd(3)
        for k in range(len(faces)):
            sd, edge, _kd, _n = faces[(k0 + k) % len(faces)]
            col = max(edge, 2) + off if sd == "L" else min(edge, 29) - off - w + 1
            if R.place(obj, 9 * s + top, col, "anchor"):
                return True
    for _ in range(DG.PATCH_TRIES):                          # fallback: the old random loop
        o = pats[rng.rnd(len(pats))]
        col = 2 + rng.rnd(33 - o[2] - 4)
        s2 = rng.rnd(2)
        r0 = rng.rnd(6 - o[3])
        if R.place(o, 9 * s2 + 1 + r0, col, "pfallback"):
            return True
    return False


def cobwebs(R, rng, mood):
    ids = DG.COBWEB[R.depth]
    if not ids:
        return
    m = R.m
    cap = 3 if mood == DARK else DG.MAX_COB
    n = 0
    for s in range(2):
        if mood == LIT and s:
            break
        odds = (1 if mood == DARK else 2) if s == 0 else (2 if mood == DARK else 4)   # 1 in odds
        row = 9 * s
        for c in range(1, COLS - 1):
            if m[row * COLS + c] != T_AIR:
                continue
            if row and not DG.floorish(m[(row - 1) * COLS + c]):
                continue
            if all(m[(row + k) * COLS + c - 1] == T_BRICK for k in range(3)):
                gid = ids[0]
            elif all(m[(row + k) * COLS + c + 1] == T_BRICK for k in range(3)):
                gid = ids[1]
            else:
                continue
            if not DG.fits(m, row, c, 1, 1, C_COMP + 1, 0):
                continue
            if odds > 1 and rng.rnd(odds):
                continue
            m[row * COLS + c] = gid
            R.objs.append(dict(name="COBWEB", cls=C_COMP + 1, row=row, col=c, w=1, h=1, src="cob", grp=None))
            n += 1
            if n == cap:
                return


def chain_cluster(R, rng, s=None):
    """DARK / DIM: 2-3 chains at pitch 2 within 6 cols of a wall / block face."""
    chain = DG.COMMON[0]
    k = 2 + rng.rnd(2)
    if s is None:
        s = rng.rnd(2)
    faces = [f for f in R.st[s]["faces"] if f[3] >= 8]
    if not faces:
        return False
    k0, off = rng.rnd(len(faces)), rng.rnd(2)
    for j in range(len(faces)):
        sd, edge, _kd, _n = faces[(k0 + j) % len(faces)]
        if sd == "L":
            cols = [max(edge + 1, 3) + off + 2 * i for i in range(k)]
        else:
            cols = [min(edge - 1, 28) - off - 2 * i for i in range(k)]
        if R.group([(chain, 9 * s, c, None) for c in cols], "chains"):
            return True
    return False


def moss_strip(R, rng):
    if not R.info["has_moss"]:
        return False
    w = 2 + rng.rnd(2)
    obj = _moss(R.depth, w)
    cand = [c for c in range(2, COLS - 2 - w + 1) if R.can_place(obj, 9, c, cmin=2)]
    if not cand:
        return False
    return R.place(obj, 9, cand[rng.rnd(len(cand))], "moss", cmin=2)


def storey_empty(R, s):
    return not any(DG.is_decor(R.m[(9 * s + r) * COLS + c]) for r in range(9) for c in range(COLS))


def ensure_storeys(R, rng, mood):
    """no empty storey (user 2026-11-17): a storey with no decor element gets, in order, a wall-anchored
    patch, a plain centrepiece (not on a CALM storey 1), a chain cluster, a moss strip, one lone chain."""
    for s in (0, 1):
        if not storey_empty(R, s):
            continue
        anchored_patch(R, rng, s)
        if storey_empty(R, s) and not (mood == CALM and s == 1):
            centre(R, rng, s, False)
        if storey_empty(R, s):
            chain_cluster(R, rng, s)
        if storey_empty(R, s) and R.info["has_moss"] and s == 1:
            moss_strip(R, rng)
        if storey_empty(R, s):
            chain = DG.COMMON[0]
            for c in range(3, 29):
                if R.place(chain, 9 * s, c, "ensure"):
                    break


def fill(R, rng, mood):
    mn = menu2(R.depth)
    for _ in range(FILL_TRIES[mood] + FILL_BONUS.get(R.depth, 0)):
        obj = mn[rng.rnd(len(mn))]
        name, base, w, h, fl, cls = obj
        cmin = 2 if fl & F_MOSS else CMIN2[cls]
        col = cmin + rng.rnd(33 - w - 2 * cmin)
        s = rng.rnd(2)
        r0 = rng.rnd(6 - h)
        if mood == CALM and s == 1 and cls in (C_MOUNT, C_FLOOR):
            continue
        row = R.row_of(obj, s, r0)
        if DEDUP and cls in (C_MOUNT, C_FLOOR, C_CEIL) and any(
                o["name"] == name and o["row"] // 9 == row // 9
                and max(col - (o["col"] + o["w"]), o["col"] - (col + w)) <= DEDUP_GAP for o in R.objs):
            continue
        R.place(obj, row, col, "fill", halo=HALO_FILL if cls in (C_MOUNT, C_FLOOR) else 1, cmin=cmin)


class ObjLog(list):
    """the placement log + the room's mood (metrics only)."""
    mood = None


# ----------------------------------------------------------------------------------------------
def decorate(m, depth, seed, live=True, room=None):
    rid, flags, key = room or (0, 0, False)
    rng = DG.Rng(seed)
    R = Room2(m, live, DG.WALL_MAX[depth], depth)
    mood = draw_mood(rng, depth, flags, key)
    R.mood = mood
    compose(R, rng, mood, flags, rid, key)
    R.nl = MAX_LARGE                                         # light lock (C10): fill can never add a light
    npool = pools(R, rng, mood)
    if not npool:
        anchored_patch(R, rng)
    if rng.rnd(4) < (3 if mood == DARK else 2):              # 2nd patch: 1/2 (DARK 3/4), anchored too
        anchored_patch(R, rng)
    cobwebs(R, rng, mood)
    if mood in (DARK, DIM):
        chain_cluster(R, rng)
    if mood == DARK:
        moss_strip(R, rng)
    fill(R, rng, mood)
    ensure_storeys(R, rng, mood)
    log = ObjLog(R.objs)
    log.mood = mood
    return R.m, R.anim, log


# ----------------------------------------------------------------------------------------------
# Z80 tables (src/decor_gen.asm, the GENERATED block; --asm / --asm-bad)
# ----------------------------------------------------------------------------------------------
LEG_COMMON = DG.COMMON                        # the legacy (D0 / PROTO) menu's 4 commons, records 0..3
RECORDS2 = list(DG.COMMON) + list(DG.LEVEL[1])  # records 4..7: the legacy D1 block (old MOSS w 1)
LEG_FIRST, LEG_N = len(DG.COMMON), len(DG.COMMON) + len(DG.LEVEL[1])
FIRST2 = {}
for _d in range(1, 9):
    FIRST2[_d] = len(RECORDS2)
    RECORDS2 += menu2(_d)[1:]
FIRST2[9] = len(RECORDS2)


def emit_asm():
    """the DECOR2 record tables (record = base | w + h*4 + class*32 | flags, as tools/decorgen.py)."""
    out = ["; GENERATED by tools/decorgen2.py --asm (edit the tool, re-run, paste)",
           "; record (3 B): base id | w + h*4 + class*32 | flags (bit0 moss, 1 tiled, 2 glyph row 0, 3 glyph row 1 too,",
           ";                 4 only its col 0, 7 large animated); class 0 mount, 1 ceiling, 2 floor, 3 patch, 5 composite",
           "; records 0..3 = the legacy commons (CHAIN + the 3 1x1 patches), 4..7 = the legacy D1 block (D0 / PROTO",
           "; levels: LVL_KEYROOM = ROOM_NONE, tools/decorgen.py); then per depth menu2 minus CHAIN (MOSS = w 2, w 3)",
           f"DG_LEG_FIRST    EQU {LEG_FIRST}",
           f"DG_LEG_N        EQU {LEG_N}",
           "dg_dtab:        ; per depth (DG_DTAB B, = the DGV order dg_wmax .. dg_nlev): wall budget + 1,",
           ";                 PATCH_A/B records (0 = composite), pair light record (| $80 floor class),",
           ";                 cobweb left / right id (0 = none), first record, record count"]
    for d in range(1, 9):
        name = PAIR_LIGHT[d]
        i = next(i for i in range(FIRST2[d], FIRST2[d + 1]) if RECORDS2[i][0] == name)
        pr = i | (0x80 if RECORDS2[i][5] == C_FLOOR else 0)
        lft, rgt = DG.COBWEB[d] or (0, 0)
        row = [DG.WALL_MAX[d] + 1, DG.PATCHK[d], pr, lft, rgt, FIRST2[d], FIRST2[d + 1] - FIRST2[d]]
        out.append("                DEFB " + ", ".join(f"{v:3d}" for v in row) + f"     ; D{d}")
    out.append("DG_DTAB         EQU 7")
    out.append("dg_crec:        ; the composite patch record (D1 / D8)")
    out.append(f"                DEFB 0, {DG.COMP[2] + DG.COMP[3] * 4 + DG.COMP[5] * 32}, 0")
    out.append("dg_recs:")
    for i, (name, base, w, h, fl, cls) in enumerate(RECORDS2):
        if i < LEG_FIRST:
            tag = "common"
        elif i < LEG_N:
            tag = "legacy D1"
        else:
            tag = "D%d" % next(d for d in range(1, 9) if FIRST2[d] <= i < FIRST2[d + 1])
        nm = name + (str(w) if name == "MOSS" and i >= LEG_N else "")
        out.append(f"                DEFB {base:3d}, {w + h * 4 + cls * 32:3d}, ${fl:02X}      ; {i:2d} {tag} {nm}")
    n = len(RECORDS2)                         # DECOR2-SHIP: a Z80-only probe record after the model's (dg_cobwebs runs
    out.append(f"                DEFB   0,  {1 + 1 * 4 + C_CEIL * 32:2d}, $00      ; {n} the cobweb probe (1x1 ceiling class, "
               "no flags: dg_cobwebs' dg_chk)")   # its candidates through dg_chk = floorish + DG.fits)
    out.append(f"DG_REC_COB      EQU {n}")
    out.append(f"DG_NREC         EQU {n + 1}")
    return "\n".join(out)


def emit_bad_asm():
    """dg_bad (64 B, src/dg_bad2.asm; the shipped deriver keeps its 0 / 1 dg_bad0.asm): bit 0 = a decor id,
    bit 1 = a ladder / hole id (dg_ring ANDs its mask: 3 = the full ring, 2 = ladders only (the light
    pools)), bit 2 = air-like (T_AIR or a decor id: dg_scan's row-3 runs)."""
    bad = [(2 if DG.T_LAD_L <= t <= DG.T_HOLE_R else 0) | (5 if DG.is_decor(t) else 4 if t == T_AIR else 0)
           for t in range(64)]
    out = ["; GENERATED by tools/decorgen2.py --asm-bad (edit the tool, re-run, paste)",
           "; DECOR2 lookup: bit 0 decor id, bit 1 ladder / hole id, bit 2 air-like (T_AIR / decor); bank 0, one page (ASSERT)",
           "dg_bad:"]
    for k in range(0, 64, 16):
        out.append("                DEFB " + ", ".join(str(v) for v in bad[k:k + 16]))
    return "\n".join(out)


if __name__ == "__main__" and "--asm" in sys.argv:
    print(emit_asm())
elif __name__ == "__main__" and "--asm-bad" in sys.argv:
    print(emit_bad_asm())
elif __name__ == "__main__":
    for d in range(1, 9):
        print(f"D{d}: menu2 " + ", ".join(f"{o[0]}{o[2]}" if o[0] == 'MOSS' else o[0] for o in menu2(d)))
