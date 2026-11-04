"""T14 playthrough bot: the player.  Monitor and tick driver: tests/pt_mon.py.  CLI: tests/playthrough.py.

All gameplay goes through the real controls (p.turn / p.tap: injected keyboard matrix).  The only pokes
are counted in Bot.pokes ("nav": the hero's position inside the current room after a stuck streak,
"god_hp" / "god_food": top-ups when the bot would otherwise die / starve, "dead_hp": the GS_DEAD
variant's HP squeeze) and every one is logged.
"""
import collections

from pt_mon import *  # noqa: F401,F403
from pt_mon import (S, K_KNIGHT, K_WIZARD, EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT, EF_DYING, EF_PENDING, GS_WIN,
                    GS_DEAD, GS_PLAYING, STRIDE, stand_y, room_model)

IT = {k[3:]: v for k, v in S.items() if k.startswith("IT_") and isinstance(v, int)}
IT_NAME = {}
for _k, _v in IT.items():
    IT_NAME.setdefault(_v, _k)
RDX = {k: S["RDX_" + k] for k in ("L", "R", "U", "D", "LS1", "RS1")}
EG = {k: S["EG_" + k] for k in ("LINK", "DOOR", "OPEN", "LOCK", "SEAL")}
TF = {k: S["TF_" + k] for k in ("SOLID", "FLOOR", "HOLE", "LADDER", "DOOR", "LOCK", "ATTACK", "ANIM")}
CLOSE_SLOT, WIDTHS = 24, (1, 5, 5, 5, 5, 4)
HERO_W = 3
LF = {k: S["LF_" + k] for k in ("GRATE_OPEN", "SEAL_OPEN", "KEY_TAKEN", "GATE_HINT")}
FOOD_ITEMS = range(IT["F_CARROT"], IT["F_MEAT"] + 1)
# icon slots (0-based). Warrior: 1 Power Strike, 2 Whirlwind, 3 Daggers, 4 Bow. Mage: 1..5 Spark Firebolt
# Frost Drain Lightning.  7/8/9/10 (index 6..9): food, potion, scroll, bag (both heroes).
SLOT_FOOD, SLOT_POTION = 6, 7
GEAR_RANK = {
    K_KNIGHT: {"W_SHORT": 1, "W_LONG": 2, "W_AXE": 3, "W_CLEAVER": 4, "A_LEATHER": 1, "A_CHAIN": 2, "A_PLATE": 3,
               "A_SILK": 1, "A_GRAVE": 1, "H_HELM": 1, "H_KING": 2, "H_MIRROR": 3},
    K_WIZARD: {"W_OAK": 1, "W_IRON": 2, "W_RUNE": 3, "W_BONE": 4, "A_ROBE": 1, "A_SILK": 2, "A_GRAVE": 2,
               "H_HOOD": 1, "H_KING": 2, "H_MIRROR": 3},
}


def gear_kind(n):
    return n[0]


import os
TRACE = bool(os.environ.get("PT_TRACE"))
TRACE_FROM = int(os.environ.get("PT_TRACE") or 0)


class RunEnd(Exception):
    pass


class Bot:
    def __init__(self, p, hero, mode="win", god=True, max_ticks=900000, level_cap=60000, log=print):
        self.p, self.hero_kind, self.mode, self.god = p, hero, mode, god
        self.max_ticks, self.level_cap, self.log = max_ticks, level_cap, log
        self.mon = p.mon
        self.pokes = collections.Counter()
        self.stats = collections.Counter()
        self.levels = []
        self.blocked = {}                      # (room, s, x, move) -> tick it was refused 3x; expires after 250 ticks
        self.map_room = None
        self.fails = 0
        self.ignore = {}
        self.events = []
        self.item_fail = collections.Counter()
        self.lvl_t0 = 0
        self.kw = self.kh = None
        self.climb = None
        self.deaths = 0
        self.dead_phase = False
        self.blk = None
        self.depth = 0
        self.goal_fail = collections.Counter()
        self.chase = None                      # (slot, tick the chase began)

    # ---------------------------------------------------------------- reads
    def rb(self, n):
        return self.p.rb(n)

    def ev(self, text):
        t = self.mon.ticks
        self.events.append((t, text))
        self.log(f"[bot t={t} D{self.rb('LVL_DEPTH')} r{self.rb('CUR_ROOM')}] {text}")

    def heroe(self):
        return self.p.ent(0)

    def storey_of(self, y, h):
        return min(1, (y + h) // S["STOREY_ROWS"])

    def hero_pos(self):
        e = self.heroe()
        return e, self.storey_of(e["Y"], self.kh), e["X"], (e["Y"] + self.kh) % S["STOREY_ROWS"] == S["STOREY_AIR"]

    def kb(self, k, f):
        return self.p.rb(S["kind_tab"] + S[f] + k)

    def hostiles(self):
        out = []
        room = self.rb("CUR_ROOM")
        raw = self.p.z.read_memory(S["P_ENTITIES"], 16 * STRIDE)
        for s in range(1, 16):
            b = raw[s * STRIDE:(s + 1) * STRIDE]
            fl = b[S["E_FLAGS"]]
            if not fl & EF_ACTIVE or fl & EF_DYING or b[S["E_ROOM"]] != room or not fl & EF_HOSTILE:
                continue
            k = b[S["E_KIND"]]
            w, h = self.kb(k, "KT_BW"), self.kb(k, "KT_BH")
            x, y = b[S["E_X"]], b[S["E_Y"]]
            out.append(dict(slot=s, kind=k, x=x, y=y, w=w, h=h, hp=b[S["E_HP"]], fl=fl, pend=bool(fl & EF_PENDING),
                            s=self.storey_of(y, h), left=bool(fl & EF_LEFT), react=b[S["E_REACT"]], gold=bool(b[S["E_GOLD"]] & S["LEK_GOLD"])))
        return out

    def lflags(self):
        return self.rb("LVL_FLAGS")

    def ranks(self):
        a = self.p.rw("ARANK")
        return [(a >> (2 * i)) & 3 for i in range(5)]

    def bag(self):
        raw = self.p.z.read_memory(S["BAG"], S["BAG_SLOTS"] * S["IR_STRIDE"])
        return [(raw[i * 3], raw[i * 3 + 1]) for i in range(S["BAG_SLOTS"])]

    def worn(self):
        raw = self.p.z.read_memory(S["WORN"], 12)
        return [raw[i * 3] for i in range(4)]

    def count(self, types):
        return sum(q for t, q in self.bag() if t in types)

    def floor_items(self, room):
        raw = self.p.z.read_memory(S["FLOOR_LIST"], S["FLOOR_MAX"] * S["FL_STRIDE"])
        out = []
        for i in range(S["FLOOR_MAX"]):
            rb_, col, typ, qty = raw[4 * i:4 * i + 4]
            if rb_ == S["FL_EMPTY"] or rb_ & S["FL_ROOM_MASK"] != room:
                continue
            out.append(dict(i=i, s=1 if rb_ & S["FL_S1"] else 0, x=col, type=typ, qty=qty))
        return out

    # ---------------------------------------------------------------- geometry
    def load_room(self):
        p = self.p
        self.map_room = self.rb("CUR_ROOM")
        self.map = bytes(p.z.read_memory(S["ROOM_MAP"], 576))
        self.tf = bytes(p.z.read_memory(S["tile_flags"], 64))
        self.blocked = {}
        self.ignore = {}
        self.climb = None
        self.fails = 0
        self.chase = None
        self.visited.add(self.map_room)
        self.map_check()

    DYN = {S[k] for k in ("T_ITEM0", "T_DOOR_ARCH_L", "T_DOOR_ARCH_R", "T_DOOR_L", "T_DOOR_R", "T_DOOR_LOCK", "T_GRATE",
                          "T_GRATE_SHUT", "T_RUBBLE", "T_LECT_TL", "T_LECT_TR", "T_LECT_BL", "T_LECT_BR", "T_TRAP",
                          "T_DOOR_JAMB_L", "T_DOOR_JAMB_R", "T_GLOW")} | {S["T_ITEM0"] + k for k in range(4)}

    def map_check(self):
        """ROOM_MAP of the room just entered == the generator's model (room_model.render_room) outside the
        cells that change in play (items, doors, grate, Tome, traps)."""
        got = self.map
        blk = room_model.read_block(self.p)
        exp = room_model.render_room(blk, self.map_room)
        bad = [(i % 32, i // 32, exp[i], got[i]) for i in range(576)
               if exp[i] != got[i] and exp[i] not in self.DYN and got[i] not in self.DYN
               and not (self.tf[exp[i]] | self.tf[got[i]]) & TF["ANIM"]]
        self.stats["map_checks"] += 1
        if any(g >= S["TILE_IDS"] for g in got):
            self.mon.v("MAP", f"r{self.map_room}: tile id >= TILE_IDS")
        if bad:
            self.mon.v("MAP", f"r{self.map_room} D{self.rb('LVL_DEPTH')}: {len(bad)} cells differ from the model: {bad[:6]}")

    def refresh_room(self):
        if self.map_room != self.rb("CUR_ROOM"):
            self.load_room()

    def cell_tf(self, c, r):
        return self.tf[self.map[r * 32 + c]]

    def free(self, s, x):
        if x < 0 or x + HERO_W > 32:
            return False
        y0 = S["STOREY_ROWS"] * s + S["STOREY_AIR"] - self.kh
        for r in range(y0, y0 + self.kh):
            for c in range(x, x + HERO_W):
                if self.cell_tf(c, r) & TF["SOLID"]:
                    return False
        return True

    def fall_range(self):
        return room_model.fall_range(self.blk, self.map_room)

    def room_ladders(self, r=None):
        r = self.map_room if r is None else r
        return [c for c in (room_model.field(self.blk, r, "RD_LAD1"), room_model.field(self.blk, r, "RD_LAD2")) if c]

    def is_blocked(self, key):
        t = self.blocked.get(key)
        return t is not None and self.mon.ticks - t < 250

    def jump_ok(self, x, dx):
        """a storey-0 jump from col x toward dx (+1 / -1), D = 6: swept box x+1..x+8 (rows top-2..bottom) free of
        solids, landing box free, not on the fall range, inside 0..27 (game.md 2.4)."""
        lx = x + 6 * dx
        if lx < 0 or lx > 27 or not self.free(0, lx) or lx in set(self.fall_range()):
            return False
        y0 = S["STOREY_AIR"] - self.kh
        cols = range(x + 1, x + 9) if dx > 0 else range(x - 6, x + 3)
        for r in range(max(0, y0 - 2), y0 + self.kh):
            for c in cols:
                if 0 <= c < 32 and self.cell_tf(c, r) & TF["SOLID"]:
                    return False
        return True

    def explore(self, start=None):
        """Dijkstra over (s, x) from start: walk 1, jump 4 (storey 0, over narrow pits), ladder 9.
        -> {node: (prev, action)}; action = key tuple for p.turn."""
        import heapq
        if start is None:
            _, s0, x0, _ = self.hero_pos()
            start = (s0, x0)
        rm = self.map_room
        lads = self.room_ladders()
        fr = set(self.fall_range())
        prev = {start: (None, None)}
        dist = {start: 0}
        q = [(0, start)]
        while q:
            d, n = heapq.heappop(q)
            if d > dist[n]:
                continue
            s, x = n
            nb = []
            for dx, key in ((-1, "H"), (1, "L")):
                nx = x + dx
                if self.free(s, nx) and not (s == 0 and nx in fr) and not self.is_blocked((rm, s, x, key)):
                    nb.append(((s, nx), 1, (key,)))
                if s == 0 and not self.is_blocked((rm, s, x, "J" + key)) and self.jump_ok(x, dx):
                    nb.append(((s, x + 6 * dx), 4, ("K", key)))
            if x in lads:
                nb.append(((1 - s, x), 9, ("J",) if s == 0 else ("K",)))
            for m, c, act in nb:
                if m not in dist or d + c < dist[m]:
                    dist[m] = d + c
                    prev[m] = (n, act)
                    heapq.heappush(q, (d + c, m))
        return prev

    def path_to(self, goals):
        """[(node, action-to-reach-it)] from the hero's node to the nearest goal, or None."""
        prev = self.explore()
        best = None
        for g in goals:
            if g in prev:
                path = []
                n = g
                while n is not None:
                    pn, act = prev[n]
                    path.append((n, act))
                    n = pn
                path.reverse()
                if best is None or len(path) < len(best):
                    best = path
        return best

    def reach_span(self, s):
        prev = self.explore()
        xs = [x for (ss, x) in prev if ss == s]
        return (min(xs), max(xs)) if xs else (None, None)

    # ---------------------------------------------------------------- level graph
    def load_level(self):
        self.blk = room_model.read_block(self.p)
        self.depth = self.rb("LVL_DEPTH")
        self.lair = self.rb("LVL_LAIR")
        self.sanctum = self.rb("LVL_SANCTUM") if self.depth == 8 else None
        self.keyroom = self.rb("LVL_KEYROOM")
        self.visited = set()
        self.map_room = None
        self.ignore = {}
        self.lvl_t0 = self.mon.ticks
        self.kw, self.kh = self.kb(self.hero_kind, "KT_BW"), self.kb(self.hero_kind, "KT_BH")
        self.goal_fail = collections.Counter()
        self.rooms = [r for r in range(9) if room_model.field(self.blk, r, "RD_EXITS")]
        self.stats["levels"] += 1
        self.ev(f"LEVEL D{self.depth}: seed {self.p.rw('LVL_SEED'):#06x} start r{self.rb('LVL_START')} "
                f"lair r{self.lair} key r{self.keyroom} sanctum {self.sanctum} rooms {self.rooms} "
                f"HP {self.hp()} LVL {self.rb('LVL')} FOOD {self.rb('FOOD')}")
        self.load_room()

    def edge_flags(self, m):
        return self.rb(S["EDGE_TAB"] + m - m // 3)

    def neighbours(self, r):
        out = []
        ex = room_model.field(self.blk, r, "RD_EXITS")
        if ex & RDX["L"] and r % 3 and self.edge_flags(r - 1) & EG["LINK"]:
            out.append((r - 1, "L"))
        if ex & RDX["R"] and r % 3 != 2 and self.edge_flags(r) & EG["LINK"]:
            out.append((r + 1, "R"))
        if ex & RDX["D"] and r + 3 < 9:
            out.append((r + 3, "D"))
        if ex & RDX["U"] and r - 3 >= 0:
            out.append((r - 3, "U"))
        return out

    def room_path(self, a, b):
        prev = {a: None}
        q = collections.deque([a])
        while q:
            r = q.popleft()
            if r == b:
                path = []
                while r is not None:
                    path.append(r)
                    r = prev[r]
                return path[::-1]
            for n, _ in self.neighbours(r):
                if n not in prev:
                    prev[n] = r
                    q.append(n)
        return None

    # ---------------------------------------------------------------- low-level
    def act(self, *keys):
        ok = self.p.turn(*keys)
        if TRACE and self.mon.ticks >= TRACE_FROM:
            e = self.heroe()
            self.log(f"  act t={self.mon.ticks} {keys} ok={ok} hero x{e['X']} y{e['Y']} hp{e['HP']} st{self.rb('ST_FLAGS'):#x} "
                     f"left={bool(e['FLAGS'] & EF_LEFT)} hs={[(h['kind'], h['x'], h['y'], h['hp']) for h in self.hostiles()]}")
        self.stats["turns" if ok else "refused"] += 1
        if self.mon.ticks > self.max_ticks:
            raise RunEnd("tick cap")
        return ok

    def check_end(self):
        g = self.rb("GAME_STATE")
        if g == GS_WIN:
            raise RunEnd("win")
        if g == GS_DEAD:
            raise RunEnd("dead")

    def hp(self):
        e = self.heroe()
        return e["HP"], e["MAXHP"]

    def poke_pos(self, s, x, why):
        p = self.p
        y = stand_y(s, self.kh)
        e = self.heroe()
        p.set_ent(0, X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, FLAGS=EF_ACTIVE | EF_PLAYER | (e["FLAGS"] & EF_LEFT))
        p.tick(3)
        self.pokes["nav"] += 1
        self.ev(f"POKE nav ({why}): hero -> s{s} x{x}")

    # ---------------------------------------------------------------- bag page
    def bag_nav(self, slot):
        p = self.p
        row, col = (0, 0) if slot == CLOSE_SLOT else (5, slot - 20) if slot >= 20 else (1 + slot // 5, slot % 5)
        rc = lambda: (p.rb("pg_rc"), p.rb(S["pg_rc"] + 1))  # noqa: E731
        for _ in range(8):
            r = rc()[0]
            if r == row:
                break
            p.tap("A" if (row - r) % 6 <= 3 else "Q")
        for _ in range(6):
            if min(rc()[1], WIDTHS[row] - 1) == col:
                break
            p.tap("P")
        return rc()[0] == row and min(rc()[1], WIDTHS[row] - 1) == col

    def bag_use(self, slot):
        """Bag page: select bag slot, FIRE (verb strip, first enabled verb), FIRE: applied on return (1 turn)."""
        p = self.p
        p.tap("I")
        if not p.until(lambda: p.rb("PAGE_OPEN") == 1 and p.pc() == S["select_tick"], 14):
            self.ev("bag page did not open")
            return False
        ok = self.bag_nav(slot)
        if ok:
            p.tap("FIRE")
            p.tap("FIRE")
        else:
            p.tap("CAPS", "SPACE")
        if not p.until(lambda: p.rb("PAGE_OPEN") == 0, 14):
            p.tap("CAPS", "SPACE")
            p.until(lambda: p.rb("PAGE_OPEN") == 0, 14)
        p.tick(3)
        p.until(lambda: p.idle() and self.rb("LOG_QN") == 0, 80)
        self.stats["bag_uses"] += 1
        return ok

    def manage_bag(self):
        bag = self.bag()
        for i, (t, q) in enumerate(bag):
            if t == IT["BOOK"] and self.item_fail[(t, i)] < 3:
                r0 = self.ranks()
                n0 = sum(1 for t_, _ in bag if t_ == IT["BOOK"])
                self.bag_use(i)
                self.stats["books_read"] += 1
                if sum(1 for t_, _ in self.bag() if t_ == IT["BOOK"]) >= n0:
                    self.item_fail[(t, i)] += 1
                self.ev(f"READ book (bag {i}): ranks {r0} -> {self.ranks()} MP {self.rb('MP')}/{self.rb('MAXMP')}")
                return True
        rank = GEAR_RANK[self.hero_kind]
        worn = self.worn()
        for i, (t, q) in enumerate(bag):
            n = IT_NAME.get(t, "")
            if n in rank and self.item_fail[(t, i)] < 2:
                cur = [w for w in worn if w and gear_kind(IT_NAME.get(w, "?")) == gear_kind(n)
                       and IT_NAME.get(w, "") in rank]
                cur_rank = max([rank.get(IT_NAME.get(w, ""), 0) for w in cur] or [0])
                if rank[n] > cur_rank:
                    self.ev(f"EQUIP {n} (worn {[IT_NAME.get(w) for w in worn if w]})")
                    self.bag_use(i)
                    self.item_fail[(t, i)] += 1
                    self.stats["equips"] += 1
                    return True
        return False

    # ---------------------------------------------------------------- survival
    def survive(self):
        p = self.p
        hp, mx = self.hp()
        if self.dead_phase:
            return False
        threat = bool(self.hostiles())
        if hp * 100 < mx * (65 if threat else 35) or hp <= 7:
            if self.count({IT["P_HEAL"]}):
                self.ev(f"drink Heal at HP {hp}/{mx}")
                if self.act("G"):
                    self.stats["potions"] += 1
                    return True
            if self.god:
                p.poke_hp(0, mx)
                self.pokes["god_hp"] += 1
                self.ev(f"POKE god: HP {hp} -> {mx} (no Heal potion)")
        food = self.rb("FOOD")
        has_food = self.count(set(FOOD_ITEMS))
        if food <= 45 and has_food:
            self.ev(f"eat at FOOD {food}")
            if self.act("@%d" % SLOT_FOOD):
                self.stats["meals"] += 1
                return True
        if food <= 8 and self.god and not has_food:
            p.wb("FOOD", 60)
            self.pokes["god_food"] += 1
            self.ev(f"POKE god: FOOD {food} -> 60 (no food in the bag)")
        return False

    # ---------------------------------------------------------------- combat
    def mp_cost(self, idx):
        return 1       # the bot just tries: a refused cast costs no turn

    def fight(self):
        """-> True if a combat turn (or an approach turn) was spent."""
        # A PENDING body (squeezed past on a ladder / arrival conflict, game.md 9.2) is hidden, collides with nothing
        # and does not act until its cell is free: not a target.  Chasing it as "the nearest hostile" (its box overlaps
        # the hero's: gap -1) refused every walk / melee while a live Ghost beside it kept hitting the hero (D7 W 0x1234
        # stall, 666 overlap_skips); it materialises by itself once the hero has walked off its cell.
        hs = [h for h in self.hostiles() if self.ignore.get(h["slot"], -1) < self.mon.ticks and not h["pend"]]
        if not hs:
            return False
        e, s, x, standing = self.hero_pos()
        if not standing:
            return False                      # mid-ladder: climb on
        cand = []
        for h in hs:
            gap = h["x"] - (x + HERO_W) if h["x"] > x else x - (h["x"] + h["w"])
            h["rgap"] = gap
            gap = max(gap, -1)
            same = h["s"] == s
            cand.append((0 if same else 1, gap if same else abs(h["x"] - x) + 20, h))
        # engaged = same storey within 14 cols, or another storey within 14 cols of x (a far hostile is not chased:
        # that would fight the plan's own goal; the lair boss is hunted by the planner when the rest is done)
        # Hysteresis: once a hostile is chased it stays the target (any distance) until dead / ignored / 600 ticks,
        # else the chase and the plan's own goal would pull the hero back and forth across the 14-col threshold.
        cs = self.chase
        if cs and (self.mon.ticks - cs[1] > 600) and self.map_room != self.lair:   # (the lair boss is never given up)
            self.ignore[cs[0]] = self.mon.ticks + 500
            self.ev(f"chase of slot {cs[0]} timed out (600 ticks): ignored for 500")
            self.chase = cs = None
        keep = [c for c in cand if cs and c[2]["slot"] == cs[0]]
        # the way out is open (boss dead; D8: Tome destroyed): only self-defence from here on (a ranged straggler
        # such as a Necromancer would otherwise pull the hero up and down the exit ladder for ever)
        leaving = bool(self.lflags() & LF["GRATE_OPEN"]) and (self.depth < 8 or self.rb("TOME_HP") == 0)
        if leaving:
            keep = []
        if keep:
            cand = keep
        elif leaving:
            cand = [c for c in cand if c[0] == 0 and c[1] <= 2]
            self.chase = None
            if not cand:
                return False
            cand.sort(key=lambda c: (c[0], c[1], c[2]["slot"]))
        else:
            cand = [c for c in cand if (c[0] == 0 and c[1] <= 14) or (c[0] == 1 and abs(c[2]["x"] - x) <= 14)]
            self.chase = None
            if not cand:
                return False
            cand.sort(key=lambda c: (c[0], c[1], c[2]["slot"]))
            self.chase = (cand[0][2]["slot"], self.mon.ticks)
        cand.sort(key=lambda c: (c[0], c[1], c[2]["slot"]))
        same, gap, h = cand[0]
        same = same == 0
        if TRACE and self.mon.ticks >= TRACE_FROM:
            self.log(f"  fight: hero s{s} x{x} cand {[(c[0], c[1], c[2]['kind'], c[2]['x'], c[2]['s']) for c in cand]} "
                     f"ign {dict(self.ignore)} rk {self.ranks()} mp {self.rb('MP')}")
        if not same:
            # a hostile on the other storey: only worth leaving the plan if it is near; else the plan continues
            return self.approach(h, s, x)
        key = "L" if h["x"] > x else "H"
        facing_right = not (e["FLAGS"] & EF_LEFT)
        if h["rgap"] < 0 and h["s"] == s:
            # boxes overlap (a flyer parked over the hero): nothing is "in front", every walk / melee is refused
            # and a spell misses.  Do not wait on it (a passive Wraith never moves): let the plan act; a climb
            # blocked twice in a row swaps hero and blocker (game.md 9.2), so the exit shaft still works.
            self.stats["overlap_skips"] += 1
            self.chase = None
            return False
        if self.rb("ST_FLAGS") & S["MIND_FEAR"] and gap <= 3:       # AFRAID: no melee; back away
            self.stats["afraid_turns"] += 1
            if not self.act("H" if key == "L" else "L"):
                self.act("WAIT")
            return True
        mp = self.rb("MP")
        rk = self.ranks()
        dag, arr = self.rb("DAGGERS"), self.rb("ARROWS")
        if self.hero_kind == K_KNIGHT:
            if gap <= 1:
                if rk[1] and mp >= 2 and sum(1 for o in hs if o["s"] == s) >= 2 and self.act("@2"):
                    return True
                if rk[0] and mp >= 2 and self.act("@1"):
                    return True
            elif gap <= 9:
                face_ok = (key == "L") == facing_right
                if face_ok and self.rb("HAS_BOW") and arr and self.act("@4"):
                    return True
                if face_ok and dag and self.act("@3"):
                    return True
        else:
            sp = self.pick_spell(h, gap, mp, rk)
            if sp is not None:
                if (key == "L") != facing_right:        # turn to face first (0-turn tap), then cast
                    self.p.tap("P" if key == "L" else "O")
                if self.act("@%d" % (sp + 1)):
                    return True
            else:
                ban = self.banned(h["kind"])
                useful = [i for i in range(5) if rk[i] and i not in ban and not (i == 3)]
                # kiting: Firebolt (the only spell this target allows) needs a 3-col gap: step back, then cast
                if 1 in useful and mp >= 5 and 0 <= gap < 3 and h["rgap"] >= 0:
                    self.stats["kite_steps"] += 1
                    if self.act("H" if key == "L" else "L"):
                        return True
                # a spell exists for it but the MP is short: rest while it is not on top of us
                elif useful and gap >= 2 and h["hp"] > 4 and mp < min(self.SPELL_MP[i] for i in useful):
                    self.stats["mp_rests"] += 1
                    if self.act("WAIT"):
                        return True
        if gap <= 1 or (gap <= 2):
            ok = self.act(key)
            if not ok:
                self.goal_fail[("fight", h["slot"])] += 1
                if self.goal_fail[("fight", h["slot"])] > 6 and self.map_room != self.lair:
                    self.ignore[h["slot"]] = self.mon.ticks + 400
                    self.ev(f"ignoring slot {h['slot']} kind {h['kind']} (melee refused)")
                self.act("WAIT")
            return True
        return self.step_toward(s, h["x"] - HERO_W if h["x"] > x else h["x"] + h["w"], h)

    # Mage spell choice (game.md 6.1 table + the resistance table): Spark 0 SHOCK, Firebolt 1 FIRE, Frost 2 COLD,
    # Drain 3, Lightning 4 SHOCK.  MP / range from the 6.1 table.  A reflected bolt hits the caster, so the bot
    # never casts a spell its target reflects (Ghost: SHOCK; Death Knight: FIRE; Archmage: COLD + SHOCK).
    SPELL_MP = (2, 5, 3, 3, 5)
    SPELL_RANGE = (6, 8, 10, 6, 16)

    def banned(self, kind):
        K = lambda *n: {S["K_" + x] for x in n}  # noqa: E731
        skel = K("SKELETON", "ARCHER", "SKEL_GUARD", "SKEL_KNIGHT", "SNIPER")
        undead = skel | K("VAMPIRE", "GHOST", "POLTERGEIST", "MUMMY", "DKNIGHT", "ARCHMAGE", "BONE_CALLER")
        out = set()
        if kind in K("GHOST", "POLTERGEIST", "ARCHMAGE"):
            out |= {0, 4}
        if kind in K("DKNIGHT") | K("ORC", "ORC_BERSERK", "ORC_BOUNCER"):
            out.add(1)
        if kind in skel | K("GHOST", "POLTERGEIST", "VAMPIRE", "MUMMY", "DKNIGHT", "ARCHMAGE", "NECRO",
                            "BONE_CALLER", "OGRE"):
            out.add(2)
        if kind in undead:
            out.add(3)
        return out

    def pick_spell(self, h, gap, mp, rk):
        ban = self.banned(h["kind"])
        for i in (4, 1, 2, 3, 0):                       # strongest first
            if rk[i] and i not in ban and mp >= self.SPELL_MP[i] and 0 <= gap <= self.SPELL_RANGE[i] - 1:
                if i == 1 and gap <= 2:                 # Firebolt's burst scorches a caster at point blank
                    continue
                if i == 3 and self.hp()[0] * 100 >= self.hp()[1] * 90:
                    continue                            # Drain Life only when it heals something
                return i
        return None

    def step_toward(self, s, tx, h):
        e, s0, x, standing = self.hero_pos()
        goals = [(s, tx), (s, tx - 1), (s, tx + 1)]
        path = self.path_to(goals)
        if path is None or len(path) < 2:
            key = "L" if h["x"] > x else "H"
            if not self.act(key):
                self.goal_fail[("fight", h["slot"])] += 1
                if self.goal_fail[("fight", h["slot"])] > 4:
                    self.ignore[h["slot"]] = self.mon.ticks + 300
                    return False
            return True
        return self.follow(path)

    def approach(self, h, s, x):
        goals = [(h["s"], h["x"] - HERO_W), (h["s"], h["x"] + h["w"])]
        path = self.path_to(goals)
        if path is None:
            self.ignore[h["slot"]] = self.mon.ticks + 200
            return False
        if len(path) < 2:
            return False
        return self.follow(path)

    # ---------------------------------------------------------------- movement
    def follow(self, path):
        """Execute the first move of path ([(node, action)]). -> True if a turn passed."""
        (s, x), _ = path[0]
        (s2, x2), act = path[1]
        rm = self.map_room
        ok = self.act(*act)
        if act[0] == "K" and len(act) == 1 or act == ("J",):
            self.climb = act[0]
        if not ok:
            self.fails += 1
            if self.fails >= 3:
                tag = "J" + act[1] if len(act) == 2 else act[0]
                self.blocked[(rm, s, x, tag)] = self.mon.ticks
                self.fails = 0
        else:
            self.fails = 0
        return ok

    def continue_climb(self):
        """mid-ladder: keep going the way we were going (no attacks on a ladder)."""
        e, s, x, standing = self.hero_pos()
        if standing:
            self.climb = None
            return False
        key = self.climb or ("J" if e["Y"] < S["STOREY_ROWS"] + 2 else "K")
        if not self.act(key):
            self.act("WAIT")
        return True

    def go_node(self, s, x, why=""):
        """one step toward node (s, x) of the current room. -> 'there' | 'moved' | 'stuck'."""
        e, s0, x0, standing = self.hero_pos()
        if (s0, x0) == (s, x):
            return "there"
        path = self.path_to([(s, x)])
        if path is None or len(path) < 2:
            self.act("WAIT")                     # no way right now (blocked moves expire after 250 ticks)
            return "stuck"
        return "moved" if self.follow(path) else "stuck"

    def do_exit(self, kind):
        """walk out of the current room by exit kind L/R/U/D. one action per call."""
        r = self.map_room
        ex = room_model.field(self.blk, r, "RD_EXITS")
        if kind in "LR":
            s = 1 if ex & RDX["LS1" if kind == "L" else "RS1"] else 0
            lo, hi = self.reach_span(s)
            if lo is None:                       # (every way there is blocked right now: pass a turn, the blocks expire)
                self.act("WAIT")
                return "stuck"
            tx = lo if kind == "L" else hi
            st = self.go_node(s, tx)
            if st == "there":
                key = "H" if kind == "L" else "L"
                if self.act(key):
                    return "moved"
                self.act("WAIT")
                return "stuck"
            return st
        if kind == "D":
            col = room_model.field(self.blk, r, "RD_DNCOL")
            st = self.go_node(1, col)
            if st == "there":
                return "moved" if self.act("J") else "stuck"
            return st
        col = room_model.field(self.blk, r, "RD_UPCOL")
        st = self.go_node(0, col)
        if st == "there":
            return "moved" if self.act("K") else "stuck"
        return st

    def goto_room(self, target, why=""):
        """one action toward room `target`."""
        r = self.map_room
        path = self.room_path(r, target)
        if path is None or len(path) < 2:
            return "stuck"
        nxt = path[1]
        kind = next(k for m, k in self.neighbours(r) if m == nxt)
        return self.do_exit(kind)

    # ---------------------------------------------------------------- pickups
    def want_item(self, it):
        t = it["type"]
        if (it["i"], self.rb("LVL_DEPTH")) in self.picked_skip:
            return False
        return True

    def pickup_step(self):
        """walk onto the next floor item of this room. -> 'none' | 'moved' | 'stuck'."""
        r = self.map_room
        items = [i for i in self.floor_items(r) if (r, i["i"]) not in self.picked_skip]
        if not items:
            return "none"
        e, s0, x0, _ = self.hero_pos()
        best = None
        for it in items:
            for dx in (0, 1, -1, 2):
                path = self.path_to([(it["s"], it["x"] + dx)])
                if path is not None and (best is None or len(path) < len(best[0])):
                    best = (path, it)
                    break
        if best is None:
            for it in items:
                self.picked_skip.add((r, it["i"]))
            self.ev(f"items unreachable in r{r}: {[(i['type'], i['x'], i['s']) for i in items]}")
            return "none"
        path, it = best
        if len(path) < 2:
            # standing on it but not picked: item may be refused (full bag / ammo cap): skip it
            self.goal_fail[("item", r, it["i"])] += 1
            if self.goal_fail[("item", r, it["i"])] > 2:
                self.picked_skip.add((r, it["i"]))
                self.ev(f"item {IT_NAME.get(it['type'])} x{it['qty']} not picked up (refused?), skipped")
            self.act("WAIT")
            return "moved"
        self.goal_fail[("itemwalk", r, it["i"])] += 1
        if self.goal_fail[("itemwalk", r, it["i"])] > 150:
            self.picked_skip.add((r, it["i"]))
            self.ev(f"item {IT_NAME.get(it['type'])} walk too long, skipped")
            return "none"
        n0 = self.bag_total()
        ok = self.follow(path)
        if len(path) == 2 and ok:
            self.stats["item_visits"] += 1
        return "moved" if ok else "stuck"

    def bag_total(self):
        return sum(q for _, q in self.bag())
