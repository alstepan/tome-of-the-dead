#!/usr/bin/env python3
"""levelgen.py - reference level generator for Stage 3B (B3B-6; Z80 port = B3B-7).

Produces the exact 320-byte level-state block the Z80 holds at LVL_STATE
($6D40..$6E7F): header(16) EDGE_TAB(@$10) ROOM_DESC(@$20, 9x16) FLOOR_LIST(@$C0,
32x4). Offsets/bit values are parsed from src/level_defs.asm (never copied).

GEN_RNG (port bit-exactly)
--------------------------
16-bit xorshift (Marsaglia 7,9,8; John Metcalf's Z80 form, period 65535):
    step:  x ^= x << 7;  x ^= x >> 9;  x ^= x << 8        (16-bit, wraps)
    rnd(n) = step, then (x & $FF) mod n        (n = 1..255; L mod n by repeated
             subtraction; cold code, bias ignored)
    rnd16  = step, then x                      (room seeds)
x never becomes 0 from a non-zero start.
Seeding: GEN_RNG = LVL_SEED ^ (depth * $0101); if that is 0 it becomes 1.
LVL_SEED itself (= f(MASTER_SEED, depth)) is the caller's business (CLI SEED).
RESEED: if no lair candidate exists (see step 6) the whole generation restarts
with seed+1 (fresh GEN_RNG from the formula above), at most RESEED_MAX=16
tries; the header LVL_SEED holds the seed actually used. Under the L1 level
shape this path is unreachable (tier (b) always has a candidate: the bottom row
is always present and reached by a horizontal edge, steps 2 + 3;
LAIR_RESEEDS stays 0, tools/levelgen_runs.py checks it); it is kept as a cheap
guard, mirrored by the Z80 port.
The header stores the FINAL GEN_RNG state (after room seeds).
Call order (every rnd call, in this order; a restart does NOT reseed):
 1. (L1) n_rooms = 7 + rnd(3) (D8: min(n, 8));  start = rnd(3) (top row);
    D8 only: sanctum S = 6 + 2*rnd(2) (reserved, never visited).
 2. DFS (stack): at cell, neighbours in order L,R,U,D that are unvisited (and
    not S); if k > 0: pick = rnd(k); link; push; stop when n_rooms visited AND
    cell 7 and (6 or 8) visited. Else pop.
 3. loop edge: if no tree edge joins 6-7 / 7-8 it is MANDATORY (no odds roll,
    candidates from r=6..8 only); else if rnd(2)==0: candidate non-tree adjacent
    present pairs in order r=0..8 (right pair r,r+1 if gx<2, then down pair
    r,r+3 if gy<2); if any: pick = rnd(count).
 4. horizontal edges e=0..5 (present only): storey = rnd(2); door = (rnd(3)==0).
 5. vertical links r=0..5 with r+3 linked: col = SHAFT_MIN + rnd(SHAFT_N)
    (stored as DNCOL of r and UPCOL of r+3).
 6. lair selection uses BFS only (no rnd): tier (a) farthest BOTTOM-ROW leaf
    with a horizontal edge, else (b) farthest bottom-row room with a horizontal
    edge (ties: lowest id; always exists by 2+3; none = RESEED, unreachable under L1). D8: the lair must also have
    a free (absent) horizontal grid neighbour (Sanctum cell) or it is not a
    candidate. D2+: arrival col (start), then level-exit col (lair):
    pick_feature(mandatory).
 7. per present room r=0..8: LAD1 (mandatory), then each optional gated by
    rnd(2)==0: PIT, LAD2, BLOCK. BLOCK is never tried in the start or lair
    room, and only on a side with NO horizontal exit (either storey).
 8. potions: total = 2 + rnd(2); each: room = non-start present
    rooms[rnd(len)], storey = rnd(2), col tries 2 + rnd(28) must be legal: up
    to 32 tries for the first two (failing -> Restart), 8 for the optional
    third (dropped). FL_ITEM = IT_POTION for all (no Heal subtype field exists
    in the 4-byte entry; 3E owns the enum).
 9. room seeds r=0..8 present: rnd16.
pick_feature: up to FEAT_TRIES=8 tries of lo + rnd(hi-lo+1) accepted if
|c - f| >= FEAT_GAP for every footprint f already on the storeys it touches;
mandatory features then scan lo..hi for the first legal col; if none, the
whole level RESTARTS from step 1 (RNG continues). Optional -> dropped.
Hero start x is NOT stored (derived: start_x(block), pure function of the
descriptors, see its docstring). Block tries: side=rnd(2), storey=rnd(2), w=2+rnd(2) (8 tries).
Port notes: hardest bits are the DFS neighbour collection, BFS lair choice
and the legality test (footprint lists per storey) - all small loops, depth <= 9.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---- 3F kind / tier table (game.md §9.1 roster, §9.6 tiers, §9.7 R1) ------------
# The 3F kind rows (3F-T3: the ids are the Z80's, src/defs.asm K_*, asserted below; golden
# bosses are a flag, not rows). Everything 3F in this module and in respawn_model.py
# (tier roll, escort, golden flag, respawn) reads it.
#   key           : name used by LP_TAB / the tests
#   (id, base hp (§9.1 / §9.6 stats column, before depth scaling), body cols,
#    flyer, §9.3 weight, base key or None, tier 1/2/3)
KROWS = {
    "K_RAT":        (6,   3, 4, False, 2, None,        1),    # §9.1
    "K_BAT":        (7,   3, 3, True,  2, None,        1),
    "K_SLIME":      (8,   6, 3, False, 2, None,        1),
    "K_GOBLIN":     (4,   6, 3, False, 3, None,        1),
    "K_SPIDER":     (9,   7, 4, False, 2, None,        1),
    "K_SKELETON":   (3,  10, 3, False, 5, None,        1),
    "K_VAMPIRE":    (10, 14, 3, False, 5, None,        1),
    "K_GHOST":      (5,   8, 3, True,  3, None,        1),
    "K_ORC":        (11, 14, 3, False, 5, None,        1),
    "K_ARCHER":     (12,  8, 3, False, 6, None,        1),
    "K_MUMMY":      (13, 18, 3, False, 5, None,        1),
    "K_NECRO":      (14, 12, 3, False, 6, None,        1),
    "K_OGRE":       (15, 40, 4, False, 6, None,        1),    # unique boss D4
    "K_DKNIGHT":    (16, 50, 3, False, 5, None,        1),    # unique boss D7
    "K_ARCHMAGE":   (17, 40, 3, False, 6, None,        1),    # unique boss D8
    # §9.6 tier rows, table order (hp from the stats column; a tier keeps its
    # base's body, flyer flag and weight, except the Slinger's +1)
    "K_GIANT_RAT":  (18,  5, 4, False, 2, "K_RAT",     2),
    "K_RABBIT_RAT": (19,  8, 4, False, 2, "K_RAT",     3),
    "K_SCREECH":    (20,  5, 3, True,  2, "K_BAT",     2),
    "K_SLINGER":    (21,  8, 3, False, 4, "K_GOBLIN",  2),    # weight 3 + 1
    "K_BLACK_WIDOW": (22, 10, 4, False, 2, "K_SPIDER", 2),
    "K_SKEL_GUARD": (23, 14, 3, False, 5, "K_SKELETON", 2),
    "K_SKEL_KNIGHT": (24, 18, 3, False, 5, "K_SKELETON", 3),
    "K_POLTERGEIST": (25, 11, 3, True,  3, "K_GHOST",  2),
    "K_ORC_BERSERK": (26, 18, 3, False, 5, "K_ORC",    2),
    "K_ORC_BOUNCER": (27, 24, 3, False, 5, "K_ORC",    3),
    "K_SNIPER":     (28, 10, 3, False, 6, "K_ARCHER",  2),
    "K_BONE_CALLER": (29, 14, 3, False, 6, "K_NECRO",  2),
}
# boss per depth (§8.6): (row key, golden). Golden = base row + LEK_GOLD (§9.7 R1)
BOSS3 = {1: ("K_GOBLIN", True), 2: ("K_SPIDER", True), 3: ("K_VAMPIRE", True),
         4: ("K_OGRE", False), 5: ("K_MUMMY", True), 6: ("K_NECRO", True),
         7: ("K_DKNIGHT", False), 8: ("K_ARCHMAGE", False)}
LEK_GOLD = 0x20                   # LE_KIND bit 5 (§9.7 R1; bits 0-4 row, 6 bred, 7 respawn)
LEK_BRED = 0x40
LEK_RESPAWN = 0x80
LEK_ROW_MASK = 0x1F
# §9.6 tier roll constants
T2_BASE = (None, 24, 48, 64, 72, 80, 88, 96, 96)             # index = depth
T3_BASE = (None, 0, 0, 0, 16, 24, 32, 40, 48)
TIER3_MIN_DEPTH, TIER_SHIFT2, TIER_SHIFT3, TIER_DELTA_MAX, T2_CAP, T3_CAP = 4, 16, 8, 2, 160, 80
# 3F-T3: the Z80 ids are authoritative (src/defs.asm K_*); this table must agree with them
# (checked below once defs.asm is parsed).
# derived (do not edit): id -> key, base key -> (tier2 key, tier3 key)
K3_BY_ID = {v[0]: k for k, v in KROWS.items()}
TIERS = {}
for _k, _v in KROWS.items():
    if _v[5]:
        TIERS.setdefault(_v[5], [None, None])[_v[6] - 2] = _k

# ---- tunables (designer decision 2026-10-03) ---------------------------------
SHAFT_MIN = 5            # exit shafts (up/down/arrival/level-exit) left col 5..24
SHAFT_MAX = 24
SHAFT_N = SHAFT_MAX - SHAFT_MIN + 1
POTIONS_MIN = 2
LOOP_EDGE_ODDS = 2       # 1 in 2
DOOR_ODDS = 3            # 1 in 3
MAX_RESTARTS = 64
PIT_MIN = 5              # pit col 5..24 (game.md 1.1 Pit geometry (1))
PIT_MAX = 24


def load_defs(paths=None):
    syms = {}
    for p in (paths or [ROOT / "src" / "defs.asm", ROOT / "src" / "level_defs.asm",
                        ROOT / "src" / "item_defs.asm"]):   # 3E-T3: IT_* moved there
        _load_one(Path(p), syms)
    return syms


def _load_one(path, syms):
    pat = re.compile(r"^([A-Z][A-Z0-9_]*)\s+EQU\s+([^;]+)")
    for line in path.read_text().splitlines():
        m = pat.match(line)
        if not m:
            continue
        expr = m.group(2).strip().replace("$", "0x")
        expr = re.sub(r"%([01]+)", lambda x: str(int(x.group(1), 2)), expr)
        try:
            syms[m.group(1)] = int(eval(expr, {}, dict(syms)))
        except Exception:
            pass                       # needs symbols we do not define


D = load_defs()
for _k, _v in KROWS.items():          # 3F-T3: KROWS ids == defs.asm K_* ids (the Z80 is the truth)
    if D.get(_k) != _v[0]:
        raise SystemExit(f"levelgen: KROWS {_k} id {_v[0]} != src/defs.asm {D.get(_k)}")


def sym(name):
    if name not in D:
        raise SystemExit(f"levelgen: symbol {name} missing/unparsed in level_defs.asm / item_defs.asm")
    return D[name]


NEEDED = """RD_FLAGS RD_EXITS RD_UPCOL RD_DNCOL RD_ARRCOL RD_EXITCOL RD_LAD1 RD_LAD2
RD_PITCOL RD_BLOCK RD_SEED RD_SPARE RD_STRIDE RDF_PRESENT RDF_START RDF_LAIR
RDF_DEADEND RDX_L RDX_R RDX_U RDX_D RDX_LS1 RDX_RS1 RDB_WMASK RDB_S1 RDB_RIGHT
EG_LINK EG_DOOR FLOOR_MAX FL_STRIDE FL_ROOM FL_COL FL_ITEM FL_QTY FL_S1 FL_EMPTY
IT_POTION LVL_STATE LVL_DEPTH LVL_SEED GEN_RNG LVL_ATTR_FLOOR LVL_ATTR_WALL LVL_START
LVL_LAIR LVL_KEYROOM LVL_SANCTUM LVL_NROOMS LVL_FLAGS FLOOR_N MASTER_SEED EDGE_TAB
ROOM_DESC FLOOR_LIST LVL_STATE_END ROOM_NONE LF_GRATE_OPEN FEAT_W FEAT_GAP LAD_COL_MIN
LAD_COL_MAX FEAT_TRIES EDGES_H GRID_CELLS EG_SEAL RDF_SANCTUM""".split()
for _n in NEEDED:
    sym(_n)

BASE = D["LVL_STATE"]
BLOCK_LEN = D["LVL_STATE_END"] - BASE
OFF_EDGE = D["EDGE_TAB"] - BASE
OFF_DESC = D["ROOM_DESC"] - BASE
OFF_FLOOR = D["FLOOR_LIST"] - BASE
H = {k: D[k] - BASE for k in ("LVL_DEPTH LVL_SEED GEN_RNG LVL_ATTR_FLOOR LVL_ATTR_WALL "
     "LVL_START LVL_LAIR LVL_KEYROOM LVL_SANCTUM LVL_NROOMS LVL_FLAGS FLOOR_N MASTER_SEED").split()}

ATTRS = {1: (0x0F, 0x01), 2: (0x27, 0x04), 3: (0x17, 0x02), 4: (0x28, 0x05),
         5: (0x30, 0x06), 6: (0x38, 0x07), 7: (0x4F, 0x41), 8: (0x1F, 0x03)}


class Rng:
    def __init__(self, seed, depth):
        s = (seed ^ (depth * 0x0101)) & 0xFFFF
        self.x = s or 1
        self.calls = 0           # rnd()/rnd16 calls (Z80 time budget stat)

    def step(self):
        x = self.x
        x ^= (x << 7) & 0xFFFF
        x ^= x >> 9
        x ^= (x << 8) & 0xFFFF
        self.x = x
        return x

    def rnd(self, n):
        self.calls += 1
        return (self.step() & 0xFF) % n

    def rnd16(self):
        self.calls += 1
        return self.step()

    def byte(self):
        """one step, low byte: the 0..255 tier / chance roll (no modulo)"""
        self.calls += 1
        return self.step() & 0xFF


LAIR_RESEEDS = 0            # L1: times no lair candidate existed (must stay 0)
LAST = (0, 0, 0)            # (restarts, rnd calls, reseeds) of the last generate()


# ---- L2 (game.md 1.1 "Mid-room block" / "Wide pit"): a LAST pass ------------------
# Descriptor fields in the RD_SPARE bytes (level_defs.asm): L2_PITW = wide-pit width W
# (4..6; 0 = RD_PITCOL is the ordinary 3-col pit), L2_MIDB = mid-block left col b
# (0 = none), L2_MIDW = its width w (2..3). RD_SPARE+3 stays 0.
L2_PITW = sym("L2_PITW")
L2_MIDB = sym("L2_MIDB")
L2_MIDW = sym("L2_MIDW")
# tuned on a 300-seed sweep (per level: mid-block / wide pit): D2-3 0.22 / 0.09, D4-8 ~0.65 / ~0.30
# (wide = 1 in 1: every eligible room tries; the geometry, not the odds, caps it near 0.3)
L2_ODDS_W = {2: 4, 3: 4, 4: 1, 5: 1, 6: 1, 7: 1, 8: 1}        # wide pit: 1 in N per room; none on D1
L2_ODDS_M = {2: 8, 3: 8, 4: 2, 5: 2, 6: 2, 7: 2, 8: 2}        # mid-block
L2_MAX = 2                                                     # per feature per level


class Room:
    def __init__(self):
        self.present = False
        self.start = self.lair = self.dead = self.sanct = False
        self.exits = 0
        self.up = self.dn = self.arr = self.exitcol = 0
        self.lad1 = self.lad2 = self.pit = self.block = 0
        self.seed = 0
        self.pitw = self.midb = self.midw = 0

    def fps(self, s):
        if s == 0:
            return [f for f in (self.up, self.arr, self.lad1, self.lad2, self.pit) if f]
        return [f for f in (self.dn, self.exitcol, self.lad1, self.lad2) if f]


def legal(room, c, storeys):
    return all(abs(c - f) >= D["FEAT_GAP"] for s in storeys for f in room.fps(s))


class Restart(Exception):
    pass


class Reseed(Exception):
    pass


RESEED_MAX = 16
SANCTUM_CELL_RULE = True    # D8: lair needs a free horizontal neighbour cell


def pick_feature(rng, room, lo, hi, storeys, mandatory):
    for _ in range(D["FEAT_TRIES"]):
        c = lo + rng.rnd(hi - lo + 1)
        if legal(room, c, storeys):
            return c
    if mandatory:
        for c in range(lo, hi + 1):
            if legal(room, c, storeys):
                return c
        raise Restart
    return 0


def nbrs(r):
    gx, gy = r % 3, r // 3
    out = []
    if gx > 0: out.append(r - 1)
    if gx < 2: out.append(r + 1)
    if gy > 0: out.append(r - 3)
    if gy < 2: out.append(r + 3)
    return out


def hedge(r):                      # EDGE_TAB index of the edge between r and r+1
    return r - r // 3


def block_hits(room, s, side_right, w):
    """block (cols 0..w-1 / 32-w..31, rubble w / 31-w) vs features on storey s"""
    lo, hi = (32 - w - 1, 31) if side_right else (0, w)
    spans = [(f, f + 2) for f in room.fps(s)]
    if s == 0 and room.pit:
        spans.append((room.pit - 1, room.pit + 3))
    return any(not (b < lo or a > hi) for a, b in spans)


def item_col_ok(room, s, col):
    for f in room.fps(s):
        if f <= col <= f + 2:
            return False
    if s == 0 and room.pit and room.pit - 1 <= col <= room.pit + 3:
        return False
    if room.block and ((room.block >> 6) & 1) == s:
        w = room.block & D["RDB_WMASK"]
        if room.block & D["RDB_RIGHT"]:
            if col >= 31 - w:
                return False
        elif col <= w:
            return False
    return 2 <= col <= 29


def l2_clear(room, mask_cols, x, lft, wd, rgt):
    """every footprint f of `mask_cols` keeps f+lft <= x or f >= x+wd+rgt"""
    return all(f + lft <= x or f >= x + wd + rgt for f in mask_cols if f)


def l2_items(floor, r, lo, hi):
    return any(e[0] == r and lo <= e[1] <= hi for e in floor)          # storey-0 items


def l2_pass(rng, rooms, floor, depth, start, lair):
    """L2 (designer 2026-10-07): per non-start/lair room in id order, wide pit
    first, else mid-block. A narrow pit is removed while trying (restored on
    failure); a 1-ladder room gets a 2nd ladder at a seeded col per try (3..26,
    FEAT_GAP both storeys, no item under it, not on an edge block), kept only
    if the feature fits. 8 tries; W / w, the ladder col, then p / b are rolled
    in that order every try."""
    odds = (L2_ODDS_W.get(depth, 0), L2_ODDS_M.get(depth, 0))
    if not (odds[0] or odds[1]):
        return
    cnt = [0, 0]
    for r in range(9):
        rm = rooms[r]
        if not rm.present or r == start or r == lair:
            continue
        for kind in (0, 1):                                    # 0 wide pit, 1 mid-block
            if rm.pitw or rm.midb:
                break
            if cnt[kind] >= L2_MAX or not odds[kind] or rng.rnd(odds[kind]):
                continue
            n_w, base, lft, rgt = ((3, 4, 7, 4), (2, 2, 6, 3))[kind]
            pit0 = rm.pit
            rm.pit = 0                                         # a narrow pit makes way
            for _ in range(D["FEAT_TRIES"]):
                W = base + rng.rnd(n_w)
                new = 0
                if not rm.lad2:                                # add the missing 2nd ladder
                    n = D["LAD_COL_MIN"] + rng.rnd(D["LAD_COL_MAX"] - D["LAD_COL_MIN"] + 1)
                    if not legal(rm, n, (0, 1)) or any((e[0] & 15) == r and n <= e[1] <= n + 2 for e in floor):
                        continue
                    if rm.block:
                        bw = rm.block & D["RDB_WMASK"]
                        blo, bhi = (31 - bw, 31) if rm.block & D["RDB_RIGHT"] else (0, bw)
                        if not (n + 2 < blo or n > bhi):
                            continue
                    new = n
                c1, c2 = min(rm.lad1, rm.lad2 or new), max(rm.lad1, rm.lad2 or new)
                lo, hi = c1 + lft, c2 - W - rgt
                if hi < lo:
                    continue
                p = lo + rng.rnd(hi - lo + 1)
                cols = (rm.up, rm.dn, rm.arr, rm.exitcol) if kind == 0 else (rm.up, rm.arr)
                if l2_clear(rm, cols, p, lft, W, rgt) and not l2_items(floor, r, p - 1, p + W):
                    if new:
                        rm.lad2 = new
                    if kind == 0:
                        rm.pit, rm.pitw = p, W
                    else:
                        rm.midb, rm.midw = p, W
                    cnt[kind] += 1
                    break
            else:
                rm.pit = pit0


def attempt(rng, depth, l2=True):
    rooms = [Room() for _ in range(9)]
    edges = [0] * 6
    n = 7 + rng.rnd(3)
    if depth == 8:
        n = min(n, 8)                   # L1 (2): the Sanctum cell is reserved
    start = rng.rnd(3)                  # L1 (1): top grid row, nothing above it
    sanct = 6 + 2 * rng.rnd(2) if depth == 8 else None    # L1 (5): never visited
    # DFS tree
    adj = {r: set() for r in range(9)}
    visited = {start}
    stack = [start]

    def done():                         # L1 (3): n rooms AND two adjacent bottom cells
        return len(visited) >= n and 7 in visited and (6 in visited or 8 in visited)
    while stack and not done():
        cur = stack[-1]
        free = [x for x in nbrs(cur) if x not in visited and x != sanct]
        if not free:
            stack.pop()
            continue
        nx = free[rng.rnd(len(free))]
        adj[cur].add(nx); adj[nx].add(cur)
        visited.add(nx)
        stack.append(nx)
    for r in visited:
        rooms[r].present = True
    # loop edge; L1 (4): mandatory (from the bottom-row pairs only) when no tree
    # edge joins two bottom-row rooms, and then the odds roll is skipped
    mand = not (7 in adj[6] or 8 in adj[7])
    if mand or rng.rnd(LOOP_EDGE_ODDS) == 0:
        cand = []
        for r in (range(6, 9) if mand else range(9)):
            if r not in visited:
                continue
            if r % 3 < 2 and r + 1 in visited and r + 1 not in adj[r]:
                cand.append((r, r + 1))
            if r // 3 < 2 and r + 3 in visited and r + 3 not in adj[r]:
                cand.append((r, r + 3))
        if cand:
            a, b = cand[rng.rnd(len(cand))]
            adj[a].add(b); adj[b].add(a)
    # horizontal edges
    for r in range(9):
        if r % 3 < 2 and r in visited and r + 1 in adj[r]:
            s = rng.rnd(2)
            door = rng.rnd(DOOR_ODDS) == 0
            edges[hedge(r)] = D["EG_LINK"] | (D["EG_DOOR"] if door else 0)
            rooms[r].exits |= D["RDX_R"] | (D["RDX_RS1"] if s else 0)
            rooms[r + 1].exits |= D["RDX_L"] | (D["RDX_LS1"] if s else 0)
    # vertical links
    for r in range(6):
        if r in visited and r + 3 in adj[r]:
            c = SHAFT_MIN + rng.rnd(SHAFT_N)
            rooms[r].dn = c; rooms[r].exits |= D["RDX_D"]
            rooms[r + 3].up = c; rooms[r + 3].exits |= D["RDX_U"]
    # BFS distances, leaves, lair
    dist = {start: 0}
    q = [start]
    for r in q:
        for x in sorted(adj[r]):
            if x not in dist:
                dist[x] = dist[r] + 1
                q.append(x)
    def has_h(r):
        return bool(rooms[r].exits & (D["RDX_L"] | D["RDX_R"]))
    leaves = [r for r in visited if len(adj[r]) == 1]

    def sanctum_ok(r):
        if depth != 8 or not SANCTUM_CELL_RULE:
            return True
        gx = r % 3
        return (gx > 0 and r - 1 not in visited) or (gx < 2 and r + 1 not in visited)
    lair = None
    for pool in ([r for r in leaves if r >= 6 and has_h(r) and sanctum_ok(r)],     # L1 (6): bottom row
                 [r for r in visited if r >= 6 and has_h(r) and sanctum_ok(r)]):
        if pool:
            lair = max(pool, key=lambda r: (dist[r], -r))
            break
    if lair is None:
        global LAIR_RESEEDS
        LAIR_RESEEDS += 1
        raise Reseed
    rooms[start].start = True
    rooms[lair].lair = True
    for r in leaves:
        rooms[r].dead = True
    # exits: arrival shaft, level exit
    if depth >= 2:
        rm = rooms[start]
        rm.arr = pick_feature(rng, rm, SHAFT_MIN, SHAFT_MAX, (0,), True)
    rm = rooms[lair]
    rm.exitcol = pick_feature(rng, rm, SHAFT_MIN, SHAFT_MAX, (1,), True)
    # in-room features
    for r in sorted(visited):
        rm = rooms[r]
        rm.lad1 = pick_feature(rng, rm, D["LAD_COL_MIN"], D["LAD_COL_MAX"], (0, 1), True)
        if rng.rnd(2) == 0:
            rm.pit = pick_feature(rng, rm, PIT_MIN, PIT_MAX, (0, 1), False)   # pit geometry (1),(4)
        if rng.rnd(2) == 0:
            rm.lad2 = pick_feature(rng, rm, D["LAD_COL_MIN"], D["LAD_COL_MAX"], (0, 1), False)
        if rng.rnd(2) == 0:
            for _ in range(0 if (r == start or r == lair) else D["FEAT_TRIES"]):
                right = rng.rnd(2); s = rng.rnd(2); w = 2 + rng.rnd(2)
                bit = (D["RDX_R"], D["RDX_RS1"]) if right else (D["RDX_L"], D["RDX_LS1"])
                if rm.exits & bit[0]:        # the side must have no exit at all
                    continue
                if rm.pit and ((rm.pit > 25 - w) if right else (rm.pit < w + 4)):
                    continue                 # pit geometry (3)/(4): keep the jump / landing zone
                if block_hits(rm, s, right, w):
                    continue
                rm.block = w | (D["RDB_S1"] if s else 0) | (D["RDB_RIGHT"] if right else 0)
                break
    # potions
    floor = []
    cands = sorted(r for r in visited if r != start)
    for k in range(POTIONS_MIN + rng.rnd(2)):
        r = cands[rng.rnd(len(cands))]
        s = rng.rnd(2)
        for _ in range(32 if k < POTIONS_MIN else D["FEAT_TRIES"]):
            col = 2 + rng.rnd(28)
            if item_col_ok(rooms[r], s, col):
                floor.append((r | (D["FL_S1"] if s else 0), col, D["IT_POTION"], 1))
                break
        else:
            if k < POTIONS_MIN:
                raise Restart
    for r in sorted(visited):
        rooms[r].seed = rng.rnd16()
    if l2:
        x0 = rng.x                       # the header keeps the pre-L2 GEN_RNG: LP budgets
        l2_pass(rng, rooms, floor, depth, start, lair)     # (and all earlier output) unchanged
        rng.x = x0
    return rooms, edges, floor, start, lair, len(visited)


SANCT_SALT = 0x5A17     # 3F: the Sanctum leaf's own stream (GEN_RNG and every earlier output untouched)


def sanctum_pass(rooms, edges, seed, lair):
    """3F D8 (game.md §1.1 L1 (5), 'D8 Sanctum'): the reserved bottom-row end
    cell S (the one of 6/8 the DFS never entered) becomes a leaf room hanging
    off the lair's free side behind a SEALED edge (EG_LINK|EG_DOOR|EG_SEAL; it
    opens on the Archmage's death, LF_SEAL_OPEN). Own Rng stream: edge storey,
    one ladder column, room seed. Returns S. Items/traps/L2 never see it."""
    sc = [c for c in (6, 8) if not rooms[c].present]
    assert len(sc) == 1 and lair == 7, "D8 Sanctum rule (L1 (5)) broken"
    S = sc[0]
    rng = Rng(seed ^ SANCT_SALT, 8)
    s = rng.rnd(2)
    rm = rooms[S]
    rm.present = rm.dead = rm.sanct = True
    if S == 6:
        rooms[6].exits |= D["RDX_R"] | (D["RDX_RS1"] if s else 0)
        rooms[7].exits |= D["RDX_L"] | (D["RDX_LS1"] if s else 0)
    else:
        rooms[7].exits |= D["RDX_R"] | (D["RDX_RS1"] if s else 0)
        rooms[8].exits |= D["RDX_L"] | (D["RDX_LS1"] if s else 0)
    edges[hedge(min(7, S))] = D["EG_LINK"] | D["EG_DOOR"] | D["EG_SEAL"]
    rm.lad1 = pick_feature(rng, rm, D["LAD_COL_MIN"], D["LAD_COL_MAX"], (0, 1), True)
    rm.seed = rng.rnd16()
    return S


def generate(depth, seed, master=0, l2=True, f3=False):
    global LAST
    restarts = reseeds = calls = 0
    for k in range(RESEED_MAX):
        rng = Rng(seed + k, depth)
        try:
            for _ in range(MAX_RESTARTS):
                try:
                    rooms, edges, floor, start, lair, n = attempt(rng, depth, l2)
                    break
                except Restart:
                    restarts += 1
            else:
                raise Reseed            # restart cap hit: same as no lair -> seed+1
            break
        except Reseed:
            reseeds += 1
            calls += rng.calls
    else:
        raise RuntimeError("levelgen: no lair after 16 reseeds")
    seed = (seed + k) & 0xFFFF
    sanct = None
    if f3 and depth == 8:
        sanct = sanctum_pass(rooms, edges, seed, lair)
        n += 1
    rng.calls += calls
    LAST = (restarts, rng.calls, reseeds)
    b = bytearray(BLOCK_LEN)
    b[H["LVL_DEPTH"]] = depth
    b[H["LVL_SEED"]:H["LVL_SEED"] + 2] = (seed & 0xFFFF).to_bytes(2, "little")
    b[H["GEN_RNG"]:H["GEN_RNG"] + 2] = rng.x.to_bytes(2, "little")
    b[H["LVL_ATTR_FLOOR"]], b[H["LVL_ATTR_WALL"]] = ATTRS[depth]
    b[H["LVL_START"]] = start
    b[H["LVL_LAIR"]] = lair
    b[H["LVL_KEYROOM"]] = D["ROOM_NONE"]
    b[H["LVL_SANCTUM"]] = D["ROOM_NONE"] if sanct is None else sanct
    b[H["LVL_NROOMS"]] = n
    b[H["LVL_FLAGS"]] = 0 if f3 else D["LF_GRATE_OPEN"]      # 3F: the grate opens on the boss's death
    b[H["FLOOR_N"]] = len(floor)
    b[H["MASTER_SEED"]:H["MASTER_SEED"] + 2] = (master & 0xFFFF).to_bytes(2, "little")
    for i, e in enumerate(edges):
        b[OFF_EDGE + i] = e
    for r, rm in enumerate(rooms):
        o = OFF_DESC + r * D["RD_STRIDE"]
        if not rm.present:
            continue
        fl = D["RDF_PRESENT"] | (D["RDF_START"] if rm.start else 0) | \
            (D["RDF_LAIR"] if rm.lair else 0) | (D["RDF_DEADEND"] if rm.dead else 0) | \
            (D["RDF_SANCTUM"] if rm.sanct else 0)
        b[o + D["RD_FLAGS"]] = fl
        b[o + D["RD_EXITS"]] = rm.exits
        b[o + D["RD_UPCOL"]] = rm.up
        b[o + D["RD_DNCOL"]] = rm.dn
        b[o + D["RD_ARRCOL"]] = rm.arr
        b[o + D["RD_EXITCOL"]] = rm.exitcol
        b[o + D["RD_LAD1"]] = rm.lad1
        b[o + D["RD_LAD2"]] = rm.lad2
        b[o + D["RD_PITCOL"]] = rm.pit
        b[o + D["RD_BLOCK"]] = rm.block
        b[o + L2_PITW] = rm.pitw
        b[o + L2_MIDB] = rm.midb
        b[o + L2_MIDW] = rm.midw
        b[o + D["RD_SEED"]:o + D["RD_SEED"] + 2] = rm.seed.to_bytes(2, "little")
    for i in range(D["FLOOR_MAX"]):
        o = OFF_FLOOR + i * D["FL_STRIDE"]
        ent = floor[i] if i < len(floor) else (D["FL_EMPTY"],) * 4
        b[o:o + 4] = bytes(ent)
    return bytes(b)


def start_x(b):
    """Hero start col (storey 0, DFS-root room); a pure function of the block.
    D1: 14; D2+: arrival col + 1 (arrival shaft exempt from the legality test).
    If that col is not 'legal' (other footprints) it moves to the
    nearest legal col (distance d = 1.., left first). Legal: 2..29 and cols
    x-1, x, x+1 touch no storey-0 footprint (up/arr/ladders; pit holes+caps)
    and no storey-0 block (cols 0..w / 31-w..31)."""
    def rd(r, k):
        return b[OFF_DESC + r * D["RD_STRIDE"] + D[k]]
    st = b[H["LVL_START"]]
    depth = b[H["LVL_DEPTH"]]
    # the arrival shaft itself is exempt (hero stands at arr+1 by rule, game.md 1.1)
    spans = [(f, f + 2) for f in (rd(st, "RD_UPCOL"), rd(st, "RD_LAD1"), rd(st, "RD_LAD2")) if f]
    p = rd(st, "RD_PITCOL")
    if p:
        spans.append((p - 1, p + 3))
    bl = rd(st, "RD_BLOCK")
    if bl and not (bl >> 6) & 1:
        w = bl & D["RDB_WMASK"]
        spans.append((32 - w - 1, 31) if bl & D["RDB_RIGHT"] else (0, w))
    ok = lambda x: 2 <= x <= 29 and not any(not (x + 1 < a or x - 1 > c) for a, c in spans)
    x0 = 14 if depth == 1 else rd(st, "RD_ARRCOL") + 1
    for d in range(0, 32):
        for x in (x0 - d, x0 + d):
            if ok(x):
                return x
    raise RuntimeError("no legal start col")



# ---- LP: lazy monster population (game.md §9.4.1-9.4.7) ----------------------
# Reference for the Z80 lp_budget / lp_enter (src/lpop3.asm), byte-exact.
#
# lp_budget(block, lvl): the LP_STATE block (LP_LEN B at LP_STATE) right after
#   generation: LP_KINDS / LP_BOSS / LP_TOTAL from LP_TAB[depth], LP_LVL = lvl,
#   LP_RMAX, every other header / scratch byte 0, ROOM_VISITS 0, every record
#   FRESH with its quota. Split (§9.4.1): N = total - 2; R = present rooms but
#   start / lair / Sanctum (id order); N >= |R| -> every room in R gets 1, the
#   rest one by one by a weighted pick (weight = BFS distance from the start)
#   over the rooms of R with quota < ROOM_MAX, v = rnd(sum) on a COPY of the
#   final GEN_RNG (the header keeps the post-generation state, so every earlier
#   output stays byte-identical); no eligible room -> LP_DISCARD. N < |R| -> the
#   N farthest (ties: lowest id) get 1. Lair quota = 2 (boss + escort).
# lp_enter(block, lp, r, hs, hx, hw): one room entry (§9.4.3) -> (lp', placed)
#   placed = [(kind_byte, hp, storey, col, facing_left)] in slot-fill order.
#   Stream: x = (LVL_SEED ^ ((r*16 + $0F) << 8) ^ ROOM_VISITS[r]) or 1, the
#   GEN_RNG algorithm. FRESH lair: [boss, escort = fit(rnd(4), cap 12)];
#   FRESH room: count x fit(rnd(4), SIGMA_INIT = max(8, ROOM_MAX * minW),
#   reserving left * minW for the units still to roll: the rolled kind, else the
#   other LP_KINDS in list order; the lightest always fits, so nothing is lost);
#   VISITED: its entries. Then
#   per unit, in order: LP_TRIES candidates, one GEN_RNG step v each: s = bit 8
#   of v, x = LP_XMIN + (v & $FF) mod (29 - w)
#   arrival gap >= LP_GAP (8) on tries 1-4, >= LP_GAP2 (5) on 5-8; a candidate
#   failing ONLY the gap is re-tested at the same x on the other storey
#   (the fresh lair's boss: all 8, the legal one farthest from the hero wins:
#   |x - hx| + 32 if another storey, first on ties; everyone else: the first
#   legal one). Unplaced units stay in the record (in order). Record -> VISITED.
#   ROOM_VISITS is NOT incremented here (the caller does it after admission).
LP_TAB = {1: (("K_RAT", "K_BAT", "K_SLIME", "K_GOBLIN"), "K_BOSS_D1", 11),
          2: (("K_GOBLIN", "K_SPIDER", "K_BAT", "K_RAT"), "K_BOSS_D2", 12),
          3: (("K_SKELETON", "K_VAMPIRE", "K_GHOST", "K_BAT"), "K_BOSS_D3", 12),
          4: (("K_ORC", "K_RAT", "K_SPIDER", "K_ARCHER"), "K_BOSS_D4", 13),
          5: (("K_MUMMY", "K_SKELETON", "K_ARCHER", "K_SPIDER"), "K_BOSS_D5", 13),
          6: (("K_VAMPIRE", "K_GHOST", "K_NECRO", "K_ORC"), "K_BOSS_D6", 14),
          7: (("K_ORC", "K_ARCHER", "K_GHOST", "K_NECRO"), "K_BOSS_D7", 14),
          8: (("K_NECRO", "K_SKELETON", "K_GHOST", "K_VAMPIRE"), "K_BOSS_D8", 11)}
# kind_tab mirror (main.asm KROW KT_BW / KT_HP / KF_FLYER; tests/lp.py checks
# it against the build): kind -> (body width, hp, flyer)
KINFO = {"K_SKELETON": (3, 10, False), "K_GOBLIN": (3, 6, False), "K_GHOST": (3, 8, True),
         "K_RAT": (4, 3, False), "K_BAT": (3, 3, True), "K_SLIME": (3, 6, False),
         # 3F-T3: the new rows (main.asm KT_BW / KT_HP / KF_FLYER; 3F-T13: BW = the real 3F-A1
         # body, hp the game.md §9.1 / §9.6 value before depth scaling)
         "K_SPIDER": (4, 7, False), "K_VAMPIRE": (3, 14, False), "K_ORC": (3, 14, False),
         "K_ARCHER": (3, 8, False), "K_MUMMY": (3, 18, False), "K_NECRO": (3, 12, False),
         "K_OGRE": (4, 40, False), "K_DKNIGHT": (3, 50, False), "K_ARCHMAGE": (3, 40, False),
         "K_GIANT_RAT": (4, 5, False), "K_RABBIT_RAT": (4, 8, False), "K_SCREECH": (3, 5, True),
         "K_SLINGER": (3, 8, False), "K_BLACK_WIDOW": (4, 10, False), "K_SKEL_GUARD": (3, 14, False),
         "K_SKEL_KNIGHT": (3, 18, False), "K_POLTERGEIST": (3, 11, True), "K_ORC_BERSERK": (3, 18, False),
         "K_ORC_BOUNCER": (3, 24, False), "K_SNIPER": (3, 10, False), "K_BONE_CALLER": (3, 14, False)}


def lp_kinfo(k):
    for n, v in KINFO.items():
        if D[n] == k:
            return v
    raise KeyError(k)


def lp_wt(k):
    for n in KINFO:
        if D[n] == k:
            return D["WT_" + n]
    raise KeyError(k)


# 3F-T3: KROWS (game.md) vs the Z80 rows (KINFO = kind_tab BW / HP / flyer, defs.asm WT_*).
# Intentional differences, NOT game changes (designer ruling pending): the prototype rows keep
# (D3-1: Slime / Ghost hp now match §9.1; 3F-T13: the Ogre's body is the real 32x48 = 4 cols,
# so no difference is left). key -> field names that may differ.
KNOWN_STANDIN_DIFFS = {}
for _k, _v in KROWS.items():
    _bw, _hp, _fl = KINFO[_k]
    _got = {"hp": _hp == _v[1], "body": _bw == _v[2], "flyer": _fl == _v[3], "weight": D["WT_" + _k] == _v[4]}
    _bad = {f for f, ok in _got.items() if not ok}
    if _bad != KNOWN_STANDIN_DIFFS.get(_k, set()):
        raise SystemExit(f"levelgen: KROWS {_k} differs from the Z80 row in {sorted(_bad)} "
                         f"(allowed: {sorted(KNOWN_STANDIN_DIFFS.get(_k, ()))})")


# ---- 3F: tier roll, golden flag, kind lookups (table at the top of the module) ----

def tier_odds(depth, lvl):
    """§9.6 spawn roll odds out of 256 -> (T2, T3). LVL_EXP(d) = d, Δ = clamp(LVL - d, -2, 2)."""
    dl = max(-TIER_DELTA_MAX, min(TIER_DELTA_MAX, lvl - depth))
    t2 = max(0, min(T2_CAP, T2_BASE[depth] + TIER_SHIFT2 * dl))
    t3 = max(0, min(T3_CAP, T3_BASE[depth] + TIER_SHIFT3 * dl)) if depth >= TIER3_MIN_DEPTH else 0
    return t2, t3


def tier_pick(base, r, depth, lvl):
    """Pure part of the roll: r in 0..255 -> row key. r < T3 -> tier 3 (tier 2 if the
    kind has none); r < T3 + T2 -> tier 2; else base. Untiered kinds stay base."""
    t = TIERS.get(base)
    if not t:
        return base
    t2, t3 = tier_odds(depth, lvl)
    if r < t3:
        return t[1] or t[0]
    if r < t3 + t2:
        return t[0]
    return base


def tier_roll(rng, base, depth, lvl):
    """One rng step (low byte) iff the kind has tiers; none otherwise (bosses, escorts,
    summons and breeding never call this)."""
    if base not in TIERS:
        return base
    return tier_pick(base, rng.byte(), depth, lvl)


def k3_row(key):
    return KROWS[key][0]


def k3_weight(kb):
    """§9.3 weight of a record kind byte (row | LEK_*): golden +1."""
    w = KROWS[K3_BY_ID[kb & LEK_ROW_MASK]][4]
    return w + (1 if kb & LEK_GOLD else 0)


def k3_info(kb):
    """(body cols, hp, flyer) of a record kind byte; hp = §9.1 depth-scaled by the
    caller via k3_hp."""
    v = KROWS[K3_BY_ID[kb & LEK_ROW_MASK]]
    return v[2], v[1], v[3]


def k3_hp(kb, depth):
    """Spawn hp: row hp + (depth - 1) (§9.1); golden = 2 x scaled + 6 (§9.7 R1)."""
    hp = KROWS[K3_BY_ID[kb & LEK_ROW_MASK]][1] + depth - 1
    return 2 * hp + 6 if kb & LEK_GOLD else hp


def k3_boss(depth):
    """LP_BOSS record kind byte: row | LEK_GOLD on the golden depths."""
    key, gold = BOSS3[depth]
    return KROWS[key][0] | (LEK_GOLD if gold else 0)


def lp_off(name):
    return D[name] - D["LP_STATE"]


def _rd(b, r, k):
    return b[OFF_DESC + r * D["RD_STRIDE"] + D[k]]


def _rb(b, r, off):
    return b[OFF_DESC + r * D["RD_STRIDE"] + off]


def lp_bfs(b):
    start = b[H["LVL_START"]]
    dist = {start: 0}
    q = [start]
    steps = ((D["RDX_L"], -1), (D["RDX_R"], 1), (D["RDX_U"], -3), (D["RDX_D"], 3))
    for r in q:
        ex = _rd(b, r, "RD_EXITS")
        for bit, dd in steps:
            if ex & bit and r + dd not in dist:
                dist[r + dd] = dist[r] + 1
                q.append(r + dd)
    return dist


def lp_budget(b, lvl=0, f3=False):
    depth = b[H["LVL_DEPTH"]]
    start, lair, sanct = b[H["LVL_START"]], b[H["LVL_LAIR"]], b[H["LVL_SANCTUM"]]
    kinds, boss, total = LP_TAB[depth]
    rmax = D["ROOM_MAX_LO"] if depth <= 2 else D["ROOM_MAX_HI"]
    dist = lp_bfs(b)
    R = [r for r in range(9) if _rd(b, r, "RD_FLAGS") & D["RDF_PRESENT"] and r not in (start, lair, sanct)]
    n = total - 2
    quota = [0] * 9
    if n >= len(R):
        for r in R:
            quota[r] = 1
        rem = n - len(R)
    else:
        for r in sorted(R, key=lambda r: (-dist[r], r))[:n]:
            quota[r] = 1
        rem = 0
    rng = Rng(0, 0)
    rng.x = int.from_bytes(b[H["GEN_RNG"]:H["GEN_RNG"] + 2], "little")
    discard = 0
    while rem:
        elig = [r for r in R if quota[r] < rmax]
        if not elig:
            discard += rem
            break
        v = rng.rnd(sum(dist[r] for r in elig))
        for r in elig:
            if v < dist[r]:
                quota[r] += 1
                break
            v -= dist[r]
        rem -= 1
    quota[lair] = 2
    lp = bytearray(D["LP_LEN"])
    for i, k in enumerate(kinds):
        lp[lp_off("LP_KINDS") + i] = KROWS[k][0] if f3 else D[k]
    lp[lp_off("LP_BOSS")] = k3_boss(depth) if f3 else D[boss]
    lp[lp_off("LP_TOTAL")] = total
    lp[lp_off("LP_LVL")] = lvl
    lp[lp_off("LP_DISCARD")] = discard
    lp[lp_off("LP_RMAX")] = rmax
    for r in range(9):
        lp[lp_off("LP_REC") + r * D["LR_STRIDE"]] = quota[r]
    return bytes(lp)


def lp_hits(b, r, s, lo, hi):
    """bank-3 `hits` (levelgen.asm): storey-s footprints f..f+2, the storey-0
    pit p-1..p+3, the storey-s block, against cols lo..hi."""
    fp = ("RD_UPCOL", "RD_ARRCOL", "RD_LAD1", "RD_LAD2") if s == 0 else \
         ("RD_DNCOL", "RD_EXITCOL", "RD_LAD1", "RD_LAD2")
    for k in fp:
        f = _rd(b, r, k)
        if f and f <= hi and f + 2 >= lo:
            return True
    p = _rd(b, r, "RD_PITCOL")
    pw = _rb(b, r, L2_PITW) or 3
    if s == 0 and p and p - 1 <= hi and p + pw >= lo:       # holes + caps (wide: W holes)
        return True
    mb, mw = _rb(b, r, L2_MIDB), _rb(b, r, L2_MIDW)
    if s == 0 and mb and mb - 1 <= hi and mb + mw >= lo:    # mid-block + both rubble cols
        return True
    bl = _rd(b, r, "RD_BLOCK")
    if bl and (bl >> 6) & 1 == s:
        w = bl & D["RDB_WMASK"]
        if bl & D["RDB_RIGHT"]:
            if hi + w >= 31:
                return True
        elif w >= lo:
            return True
    return False


def lp_legal(b, r, s, x, w, fly, hs, hx, hw, placed, gap=8):
    """§9.4.3 placement legality -> "ok" / "gap" (fails ONLY the arrival-gap
    test: the caller re-tests the same x on the other storey) / "bad"."""
    for ps, plo, phi in placed:                         # occupied (same storey, cols)
        if ps == s and plo <= x + w - 1 and x <= phi:
            return "bad"
    ex = _rd(b, r, "RD_EXITS")
    if ex & D["RDX_L"] and bool(ex & D["RDX_LS1"]) == (s == 1) and x <= 4:
        return "bad"                                    # left arrival box cols 1..4
    if ex & D["RDX_R"] and bool(ex & D["RDX_RS1"]) == (s == 1) and x + w - 1 >= 27:
        return "bad"                                    # right arrival box cols 27..30
    m = 1                                               # §9.4.3: footprints +-1 col (walkers and flyers)
    lo, hi = max(0, x - m), x + w - 1 + m
    if lp_hits(b, r, s, lo, hi):
        return "bad"
    p = _rd(b, r, "RD_PITCOL")
    if s == 1 and p and p <= hi and p + (_rb(b, r, L2_PITW) or 3) - 1 >= lo:   # a fall from storey 0 lands here
        return "bad"
    if s == hs and not (x >= hx + hw + gap or x + w + gap <= hx):
        return "gap"                                    # body gap to the arrival box
    return "ok"


def lp_seed(b, lp, r):
    seed = int.from_bytes(b[H["LVL_SEED"]:H["LVL_SEED"] + 2], "little")
    v = lp[lp_off("ROOM_VISITS") + r]
    x = seed ^ (((r * 16 + 0x0F) & 0xFF) << 8) ^ v
    return x or 1


LP_CALLS = 0                # rnd calls of the last lp_enter (tests: cost)


def lp_enter(b, lp, r, hs, hx, hw, f3=False):
    lp = bytearray(lp)
    rng = Rng(0, 0)
    rng.x = lp_seed(b, lp, r)
    lp[lp_off("LP_RNG"):lp_off("LP_RNG") + 2] = rng.x.to_bytes(2, "little")
    ro = lp_off("LP_REC") + r * D["LR_STRIDE"]
    hdr = lp[ro]
    kinds = [lp[lp_off("LP_KINDS") + i] for i in range(4)]
    sig = [0]
    depth, lvl = b[H["LVL_DEPTH"]], lp[lp_off("LP_LVL")]
    wt = k3_weight if f3 else lp_wt
    info = k3_info if f3 else lp_kinfo
    ROWM = LEK_ROW_MASK if f3 else D["LEK_KIND_MASK"]

    def hp0(k):
        return k3_hp(k, depth) if f3 else lp_kinfo(k)[1]

    minw = min(wt(k) for k in kinds)
    sigi = max(D["LP_SIGMA_INIT"], lp[lp_off("LP_RMAX")] * minw)

    def fit(cap, left=0, tier=False):
        """reservation fit (§9.4.3, designer 2026-10-06): accept a kind only if
        sum + w + left * minW <= cap; rolled first, then the others in list order.
        3F (tier=True, FRESH rooms only): the rolled kind gets the §9.6 tier roll
        (spawn stream, LP_LVL); a rejected tier falls back to its own base, then
        the other LP_KINDS at base tier (the escort is never rolled)."""
        i = rng.rnd(4)
        order = [kinds[i]] + [kinds[j] for j in range(4) if j != i]
        if f3 and tier:
            key = tier_roll(rng, K3_BY_ID[kinds[i]], depth, lvl)
            if KROWS[key][0] != kinds[i]:
                order.insert(0, KROWS[key][0])
        for k in order:
            if sig[0] + wt(k) + left * minw <= cap:
                sig[0] += wt(k)
                return k
        lp[lp_off("LP_DISCARD")] += 1
        return None
    boss = False
    if not hdr & D["LR_VISITED"]:
        units = []
        if r == b[H["LVL_LAIR"]]:
            k = lp[lp_off("LP_BOSS")]
            units.append((k, hp0(k)))
            sig[0] = wt(k)
            boss = True
            k = fit(D["LP_SIGMA_CAP"])                  # escort: base tier, never rolled
            if k is not None:
                units.append((k, hp0(k)))
        else:
            n = hdr & D["LR_CNT_MASK"]
            for u in range(n):
                k = fit(sigi, n - 1 - u, True)
                if k is not None:
                    units.append((k, hp0(k)))
    else:
        units = [(lp[ro + 1 + 2 * i], lp[ro + 2 + 2 * i]) for i in range(hdr & D["LR_CNT_MASK"])]
    placed, out, left = [], [], []
    for i, (kb, hp) in enumerate(units):
        w, _, fly = info(kb & ROWM)
        best = None
        for t in range(D["LP_TRIES"]):
            v = rng.rnd16()                             # one step per candidate
            s = (v >> 8) & 1
            x = D["LP_XMIN"] + (v & 0xFF) % (D["LP_XMAX"] - w)
            gap = D["LP_GAP"] if t < D["LP_TRIES"] // 2 else D["LP_GAP2"]
            res = lp_legal(b, r, s, x, w, fly, hs, hx, hw, placed, gap)
            if res == "gap":                            # other-storey retry, same x
                s ^= 1
                res = lp_legal(b, r, s, x, w, fly, hs, hx, hw, placed, gap)
            if res != "ok":
                continue
            if not (boss and i == 0):
                best = (s, x)
                break
            d = abs(x - hx) + (32 if s != hs else 0)
            if best is None or d > best[2]:
                best = (s, x, d)
        if best is None:
            left.append((kb, hp))
            continue
        s, x = best[0], best[1]
        placed.append((s, x, x + w - 1))
        out.append((kb, hp, s, x, x > hx))
    lp[ro] = D["LR_VISITED"] | len(left)
    global LP_CALLS
    LP_CALLS = rng.calls
    for i in range(D["LR_MAX"]):
        kb, hp = left[i] if i < len(left) else (0, 0)
        lp[ro + 1 + 2 * i], lp[ro + 2 + 2 * i] = kb, hp
    return bytes(lp), out

def render(b):
    g = lambda r, k: b[OFF_DESC + r * D["RD_STRIDE"] + D["%s" % k]]
    hdr = lambda k: b[H[k]]
    out = [f"depth {hdr('LVL_DEPTH')} seed {int.from_bytes(b[H['LVL_SEED']:H['LVL_SEED']+2],'little'):04X}"
           f" rooms {hdr('LVL_NROOMS')} start {hdr('LVL_START')} lair {hdr('LVL_LAIR')} startx {start_x(b)}"]
    for gy in range(3):
        row = vert = ""
        for gx in range(3):
            r = gy * 3 + gx
            fl = g(r, "RD_FLAGS")
            ex = g(r, "RD_EXITS")
            if not fl & D["RDF_PRESENT"]:
                row += " " * 10; vert += " " * 10; continue
            tag = ("S" if fl & D["RDF_START"] else "") + ("L" if fl & D["RDF_LAIR"] else "") + \
                  ("d" if fl & D["RDF_DEADEND"] else "")
            row += f"[{r}{tag:<3}]"
            if ex & D["RDX_R"]:
                e = b[OFF_EDGE + hedge(r)]
                row += ("D" if e & D["EG_DOOR"] else "-") + str(1 if ex & D["RDX_RS1"] else 0)
            else:
                row += "  "
            row += "  "[:0]
            vert += " " + ("v" if ex & D["RDX_D"] else " ") + "       "
        out.append(row.rstrip()); out.append(vert.rstrip())
    out.append("(edge: -s open passage / Ds door on storey s; v = vertical link to the room below)")
    for r in range(9):
        if not g(r, "RD_FLAGS") & D["RDF_PRESENT"]:
            continue
        names = [("up", "RD_UPCOL"), ("dn", "RD_DNCOL"), ("arr", "RD_ARRCOL"), ("exit", "RD_EXITCOL"),
                 ("lad1", "RD_LAD1"), ("lad2", "RD_LAD2"), ("pit", "RD_PITCOL")]
        f = " ".join(f"{n}={g(r, k)}" for n, k in names if g(r, k))
        bl = g(r, "RD_BLOCK")
        if bl:
            f += f" block(w{bl & 3},s{(bl >> 6) & 1},{'R' if bl & 128 else 'L'})"
        items = [(b[OFF_FLOOR + i * 4 + 1], b[OFF_FLOOR + i * 4] >> 7)
                 for i in range(hdr("FLOOR_N")) if b[OFF_FLOOR + i * 4] & 15 == r]
        if items:
            f += " potions@" + ",".join(f"{c}/s{s}" for c, s in items)
        out.append(f"  room {r}: {f}")
    return "\n".join(out)


def main(argv):
    if len(argv) < 3:
        print(__doc__.split("\n")[0]); print("usage: levelgen.py DEPTH SEED [--hex|--ascii] [--lp]"); return 2
    depth, seed = int(argv[1], 0), int(argv[2], 0)
    b = generate(depth, seed)
    if "--hex" in argv:
        for i in range(0, len(b), 16):
            print(f"{BASE + i:04X}: " + " ".join(f"{x:02X}" for x in b[i:i + 16]))
    if "--ascii" in argv or "--hex" not in argv:
        print(render(b))
    if "--lp" in argv:                  # LP budget + every room's first entry from its left edge / x 1
        lp = lp_budget(b, 1)
        o = D["LP_REC"] - D["LP_STATE"]
        print("LP quotas", [lp[o + 9 * r] for r in range(9)], "discard", lp[D["LP_DISCARD"] - D["LP_STATE"]])
        for r in range(9):
            if r != b[H["LVL_START"]] and _rd(b, r, "RD_FLAGS") & D["RDF_PRESENT"]:
                lp2, out = lp_enter(b, lp, r, 0, 1, 3)
                print(f"  room {r}: placed (kind, hp, s, x, left) {out}  left {lp2[o + 9 * r] & 7}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
