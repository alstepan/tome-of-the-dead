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
The header stores the FINAL GEN_RNG state (after room seeds).
Call order (every rnd call, in this order; a restart does NOT reseed):
 1. n_rooms = 7 + rnd(3);  start = rnd(9)
 2. DFS (stack): at cell, neighbours in order L,R,U,D that are unvisited; if
    k > 0: pick = rnd(k); link; push; stop when n_rooms visited. Else pop.
 3. loop edge: if rnd(2)==0: candidate non-tree adjacent present pairs in
    order r=0..8 (right pair r,r+1 if gx<2, then down pair r,r+3 if gy<2);
    if any: pick = rnd(count).
 4. horizontal edges e=0..5 (present only): storey = rnd(2); door = (rnd(3)==0).
 5. vertical links r=0..5 with r+3 linked: col = SHAFT_MIN + rnd(SHAFT_N)
    (stored as DNCOL of r and UPCOL of r+3).
 6. lair/start selection uses BFS only (no rnd).  D2+: arrival col (start),
    then level-exit col (lair): pick_feature(mandatory).
 7. per present room r=0..8: LAD1 (mandatory), then each optional gated by
    rnd(2)==0: PIT, LAD2, BLOCK.
 8. potions: n = 2 + rnd(2); each: room = non-start present rooms[rnd(len)],
    storey = rnd(2), col tries (8): 2 + rnd(28) must be legal; drop otherwise.
 9. room seeds r=0..8 present: rnd16.
pick_feature: up to FEAT_TRIES=8 tries of lo + rnd(hi-lo+1) accepted if
|c - f| >= FEAT_GAP for every footprint f already on the storeys it touches;
mandatory features then scan lo..hi for the first legal col; if none, the
whole level RESTARTS from step 1 (RNG continues). Optional -> dropped.
Block tries: side=rnd(2), storey=rnd(2), w=2+rnd(2) (8 tries).
Port notes: hardest bits are the DFS neighbour collection, BFS lair choice
and the legality test (footprint lists per storey) - all small loops, depth <= 9.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---- tunables (designer decision 2026-10-03) ---------------------------------
SHAFT_MIN = 5            # exit shafts (up/down/arrival/level-exit) left col 5..24
SHAFT_MAX = 24
SHAFT_N = SHAFT_MAX - SHAFT_MIN + 1
POTIONS_MIN = 2
LOOP_EDGE_ODDS = 2       # 1 in 2
DOOR_ODDS = 3            # 1 in 3
MAX_RESTARTS = 64


def load_defs(paths=None):
    syms = {}
    for p in (paths or [ROOT / "src" / "defs.asm", ROOT / "src" / "level_defs.asm"]):
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


def sym(name):
    if name not in D:
        raise SystemExit(f"levelgen: symbol {name} missing/unparsed in level_defs.asm")
    return D[name]


NEEDED = """RD_FLAGS RD_EXITS RD_UPCOL RD_DNCOL RD_ARRCOL RD_EXITCOL RD_LAD1 RD_LAD2
RD_PITCOL RD_BLOCK RD_SEED RD_SPARE RD_STRIDE RDF_PRESENT RDF_START RDF_LAIR
RDF_DEADEND RDX_L RDX_R RDX_U RDX_D RDX_LS1 RDX_RS1 RDB_WMASK RDB_S1 RDB_RIGHT
EG_LINK EG_DOOR FLOOR_MAX FL_STRIDE FL_ROOM FL_COL FL_ITEM FL_QTY FL_S1 FL_EMPTY
IT_POTION LVL_STATE LVL_DEPTH LVL_SEED GEN_RNG LVL_ATTR_FLOOR LVL_ATTR_WALL LVL_START
LVL_LAIR LVL_KEYROOM LVL_SANCTUM LVL_NROOMS LVL_FLAGS FLOOR_N MASTER_SEED EDGE_TAB
ROOM_DESC FLOOR_LIST LVL_STATE_END ROOM_NONE LF_GRATE_OPEN FEAT_W FEAT_GAP LAD_COL_MIN
LAD_COL_MAX FEAT_TRIES EDGES_H GRID_CELLS""".split()
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


LAST = (0, 0)               # (restarts, rnd calls) of the last generate()


class Room:
    def __init__(self):
        self.present = False
        self.start = self.lair = self.dead = False
        self.exits = 0
        self.up = self.dn = self.arr = self.exitcol = 0
        self.lad1 = self.lad2 = self.pit = self.block = 0
        self.seed = 0

    def fps(self, s):
        if s == 0:
            return [f for f in (self.up, self.arr, self.lad1, self.lad2, self.pit) if f]
        return [f for f in (self.dn, self.exitcol, self.lad1, self.lad2) if f]


def legal(room, c, storeys):
    return all(abs(c - f) >= D["FEAT_GAP"] for s in storeys for f in room.fps(s))


class Restart(Exception):
    pass


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


def attempt(rng, depth):
    rooms = [Room() for _ in range(9)]
    edges = [0] * 6
    n = 7 + rng.rnd(3)
    start = rng.rnd(9)
    # DFS tree
    adj = {r: set() for r in range(9)}
    visited = {start}
    stack = [start]
    while stack and len(visited) < n:
        cur = stack[-1]
        free = [x for x in nbrs(cur) if x not in visited]
        if not free:
            stack.pop()
            continue
        nx = free[rng.rnd(len(free))]
        adj[cur].add(nx); adj[nx].add(cur)
        visited.add(nx)
        stack.append(nx)
    for r in visited:
        rooms[r].present = True
    # loop edge
    if rng.rnd(LOOP_EDGE_ODDS) == 0:
        cand = []
        for r in range(9):
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
    lair = None
    for pool in ([r for r in leaves if r != start and has_h(r)],
                 [r for r in visited if r != start and has_h(r)],
                 [r for r in visited if r != start]):
        if pool:
            lair = max(pool, key=lambda r: (dist[r], -r))
            break
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
            rm.pit = pick_feature(rng, rm, 3, 26, (0,), False)
        if rng.rnd(2) == 0:
            rm.lad2 = pick_feature(rng, rm, D["LAD_COL_MIN"], D["LAD_COL_MAX"], (0, 1), False)
        if rng.rnd(2) == 0:
            for _ in range(D["FEAT_TRIES"]):
                right = rng.rnd(2); s = rng.rnd(2); w = 2 + rng.rnd(2)
                bit = (D["RDX_R"], D["RDX_RS1"]) if right else (D["RDX_L"], D["RDX_LS1"])
                if rm.exits & bit[0] and bool(rm.exits & bit[1]) == bool(s):
                    continue
                if block_hits(rm, s, right, w):
                    continue
                rm.block = w | (D["RDB_S1"] if s else 0) | (D["RDB_RIGHT"] if right else 0)
                break
    # potions
    floor = []
    cands = sorted(r for r in visited if r != start)
    for _ in range(POTIONS_MIN + rng.rnd(2)):
        r = cands[rng.rnd(len(cands))]
        s = rng.rnd(2)
        for _ in range(D["FEAT_TRIES"]):
            col = 2 + rng.rnd(28)
            if item_col_ok(rooms[r], s, col):
                floor.append((r | (D["FL_S1"] if s else 0), col, D["IT_POTION"], 1))
                break
    for r in sorted(visited):
        rooms[r].seed = rng.rnd16()
    return rooms, edges, floor, start, lair, len(visited)


def generate(depth, seed, master=0):
    rng = Rng(seed, depth)
    global LAST
    restarts = 0
    for _ in range(MAX_RESTARTS):
        try:
            rooms, edges, floor, start, lair, n = attempt(rng, depth)
            break
        except Restart:
            restarts += 1
            continue
    else:
        raise RuntimeError("levelgen: too many restarts")
    LAST = (restarts, rng.calls)
    b = bytearray(BLOCK_LEN)
    b[H["LVL_DEPTH"]] = depth
    b[H["LVL_SEED"]:H["LVL_SEED"] + 2] = (seed & 0xFFFF).to_bytes(2, "little")
    b[H["GEN_RNG"]:H["GEN_RNG"] + 2] = rng.x.to_bytes(2, "little")
    b[H["LVL_ATTR_FLOOR"]], b[H["LVL_ATTR_WALL"]] = ATTRS[depth]
    b[H["LVL_START"]] = start
    b[H["LVL_LAIR"]] = lair
    b[H["LVL_KEYROOM"]] = D["ROOM_NONE"]
    b[H["LVL_SANCTUM"]] = D["ROOM_NONE"]
    b[H["LVL_NROOMS"]] = n
    b[H["LVL_FLAGS"]] = D["LF_GRATE_OPEN"]
    b[H["FLOOR_N"]] = len(floor)
    b[H["MASTER_SEED"]:H["MASTER_SEED"] + 2] = (master & 0xFFFF).to_bytes(2, "little")
    for i, e in enumerate(edges):
        b[OFF_EDGE + i] = e
    for r, rm in enumerate(rooms):
        o = OFF_DESC + r * D["RD_STRIDE"]
        if not rm.present:
            continue
        fl = D["RDF_PRESENT"] | (D["RDF_START"] if rm.start else 0) | \
            (D["RDF_LAIR"] if rm.lair else 0) | (D["RDF_DEADEND"] if rm.dead else 0)
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
        b[o + D["RD_SEED"]:o + D["RD_SEED"] + 2] = rm.seed.to_bytes(2, "little")
    for i in range(D["FLOOR_MAX"]):
        o = OFF_FLOOR + i * D["FL_STRIDE"]
        ent = floor[i] if i < len(floor) else (D["FL_EMPTY"],) * 4
        b[o:o + 4] = bytes(ent)
    return bytes(b)


def render(b):
    g = lambda r, k: b[OFF_DESC + r * D["RD_STRIDE"] + D["%s" % k]]
    hdr = lambda k: b[H[k]]
    out = [f"depth {hdr('LVL_DEPTH')} seed {int.from_bytes(b[H['LVL_SEED']:H['LVL_SEED']+2],'little'):04X}"
           f" rooms {hdr('LVL_NROOMS')} start {hdr('LVL_START')} lair {hdr('LVL_LAIR')}"]
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
        print(__doc__.split("\n")[0]); print("usage: levelgen.py DEPTH SEED [--hex|--ascii]"); return 2
    depth, seed = int(argv[1], 0), int(argv[2], 0)
    b = generate(depth, seed)
    if "--hex" in argv:
        for i in range(0, len(b), 16):
            print(f"{BASE + i:04X}: " + " ".join(f"{x:02X}" for x in b[i:i + 16]))
    if "--ascii" in argv or "--hex" not in argv:
        print(render(b))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
