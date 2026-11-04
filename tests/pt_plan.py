"""T14 playthrough: the level planner (explore -> lair/boss -> exit; D8: Archmage -> seal -> Tome -> gate -> win)."""
import collections

from pt_bot import *  # noqa: F401,F403
from pt_bot import (Bot, RunEnd, IT, IT_NAME, LF, TF, EG, RDX, S, GS_PLAYING, GS_WIN, GS_DEAD, EF_ACTIVE,
                    HERO_W, K_KNIGHT, room_model)


class Player(Bot):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.picked_skip = set()
        self.sig = collections.deque(maxlen=90)
        self.unstick_n = 0
        self.skip_rooms = set()
        self.cur_goal = None
        self.last_fight = 0
        self.tome_log = []
        self.lvl_summ = {}
        self.boss_poke = 0                  # 0 off; True always; N = fallback after N god heals / 160 N ticks in the fight
        self.boss_t0 = {}
        self.live_t, self.live_n = -1, 0
        self.rch = collections.deque(maxlen=12)
        self.noop_n = 0
        self.branch = None

    # ------------------------------------------------------------------ main loop
    def play(self):
        try:
            while True:
                self.step()
        except RunEnd as e:
            return str(e)

    def step(self):
        p = self.p
        self.check_end()
        if self.mon.ticks == self.live_t:
            self.live_n += 1
            if self.live_n > 400:
                raise RunEnd(f"livelock: 400 bot steps without a tick (r{self.map_room}, goal {self.cur_goal})")
        else:
            self.live_t, self.live_n = self.mon.ticks, 0
        if self.rb("GAME_STATE") != GS_PLAYING:
            p.tick(1)
            return
        if self.blk is None or self.rb("LVL_DEPTH") != self.depth:
            self.finish_level()
            self.load_level()
            self.picked_skip = set()
            self.skip_rooms = set()
            self.sig.clear()
            self.unstick_n = 0
            self.lvl_summ = dict(depth=self.rb("LVL_DEPTH"), t0=self.mon.ticks, turn0=p.rw("TURN_COUNTER"),
                                 lvl0=self.rb("LVL"), kills0=p.rw("ST1_KILLS"))
            if self.mode == "dead" and self.depth >= self.dead_depth and not self.dead_phase:
                self.begin_dead()
        self.refresh_room()
        self.pingpong()
        if self.mon.ticks - self.lvl_t0 > self.level_cap:
            raise RunEnd(f"level cap D{self.depth} ({self.level_cap} ticks)")
        if self.boss_poke != 0 and self.map_room == self.lair:
            # lair-boss stalemate fallback (boss_poke True: always, a debugging aid; N: after N god heals / 160 N ticks
            # spent against that boss): its HP is set to 1; the kill, the drop, the seal / grate, the Tome, the win
            # are the game's.  Used for D1-D8 bosses alike (reported per run as boss_hp + the event log).
            for h in self.hostiles():
                if not (h["gold"] or h["kind"] in (S["K_OGRE"], S["K_DKNIGHT"], S["K_ARCHMAGE"])):
                    continue
                k = (self.depth, h["slot"])
                if k not in self.boss_t0:
                    self.boss_t0[k] = (self.mon.ticks, self.pokes["god_hp"])
                t0, g0 = self.boss_t0[k]
                if h["hp"] > 1 and (self.boss_poke is True or self.pokes["god_hp"] - g0 >= self.boss_poke
                                    or self.mon.ticks - t0 >= 160 * self.boss_poke):
                    p.set_ent(h["slot"], HP=1)
                    self.pokes["boss_hp"] += 1
                    self.ev(f"POKE boss: kind {h['kind']} (D{self.depth}) HP {h['hp']} -> 1 after "
                            f"{self.pokes['god_hp'] - g0} god heals / {self.mon.ticks - t0} ticks")
        e, s, x, standing = self.hero_pos()
        if not standing:
            self.continue_climb()
            return
        st = p.rb("ST_FLAGS")
        if st & S["STS_HOLD"]:                 # FROZEN / ASLEEP / STUNNED: the game plays the turns itself
            self.stats["held_ticks"] += 4
            hp, mx = self.hp()                 # a held hero cannot drink: the god top-up must not wait for the thaw
            if self.god and not self.dead_phase and (hp * 100 < mx * 60 or hp <= 8):
                p.poke_hp(0, mx)
                self.pokes["god_hp"] += 1
                self.pokes["god_hp_held"] += 1
                self.ev(f"POKE god: HP {hp} -> {mx} (hero held: stunned / frozen / asleep)")
            p.tick(1 if hp * 100 < mx * 80 else 4)
            self.sig.clear()
            return
        if self.survive():
            return
        if self.fight():
            self.last_fight = self.mon.ticks
            self.sig.clear()
            return
        if not self.hostiles() and self.manage_bag():
            return
        t_before = self.mon.ticks
        self.sig.append((self.map_room, s, x, self.p.rw("TURN_COUNTER") // 8))
        if len(self.sig) == self.sig.maxlen and len(set((a, b, c) for a, b, c, _ in self.sig)) <= 4:
            self.unstick()
            self.sig.clear()
            return
        self.progress()
        if self.mon.ticks == t_before:                 # a plan step that spent no tick: log the branch once in a while
            self.noop_n += 1
            if self.noop_n in (30, 300):
                r = self.map_room
                self.diag(f"no-op progress x{self.noop_n}: branch {self.branch} lair {self.lair} "
                          f"room_path->lair {self.room_path(r, self.lair)} neighbours {self.neighbours(r)} "
                          f"edges {[hex(self.edge_flags(m)) for m in (0, 1, 3, 4, 6, 7)]} flags {self.lflags():#x} "
                          f"goal {self.cur_goal}")
        else:
            self.noop_n = 0

    def pingpong(self):
        """Room ping-pong guard: >= 6 room changes alternating between two rooms within 500 ticks = a planner
        conflict (e.g. the fight and the explore goals each pointing out of a different room). Dump the state once
        per level, make the chased hostile ignored for 800 ticks and mark the other room visited."""
        r = self.map_room
        if not self.rch or self.rch[-1][1] != r:
            self.rch.append((self.mon.ticks, r))
        ch = list(self.rch)[-7:]
        if len(ch) >= 7 and ch[-1][0] - ch[0][0] < 500 and len({c[1] for c in ch}) == 2:
            self.stats["pingpong"] += 1
            if self.stats["pingpong"] <= 2:
                self.diag(f"room ping-pong {[c[1] for c in ch]}")
            for h in self.hostiles():
                self.ignore[h["slot"]] = self.mon.ticks + 800
            for c in ch:
                self.visited.add(c[1])
            self.skip_rooms |= {c[1] for c in ch if c[1] not in (self.lair, self.sanctum)}
            self.rch.clear()

    def diag(self, why):
        e, s, x, st = self.hero_pos()
        self.ev(f"DIAG {why}: hero s{s} x{x} standing {st} chase {self.chase} ignore {dict(self.ignore)} "
                f"hostiles {[(h['slot'], h['kind'], h['x'], h['y'], h['s']) for h in self.hostiles()]} "
                f"ladders {self.room_ladders()} fall {list(self.fall_range())} visited {sorted(self.visited)} "
                f"skip {sorted(self.skip_rooms)} rooms {self.rooms}")
        for row in range(18):
            self.log("   " + "".join("#" if self.cell_tf(c, row) & 1 else "L" if self.cell_tf(c, row) & 8 else
                                     "h" if self.cell_tf(c, row) & 16 else "." for c in range(32)))
        self.log(f"   reach s0 {self.reach_span(0)} s1 {self.reach_span(1)}")

    def finish_level(self):
        if self.lvl_summ:
            self.lvl_summ.update(t1=self.mon.ticks, turn1=self.p.rw("TURN_COUNTER"), lvl1=self.rb("LVL"),
                                 rooms=len(self.rooms), visited=len(self.visited), skipped=sorted(self.skip_rooms))
            self.levels.append(self.lvl_summ)
            self.lvl_summ = {}

    # ------------------------------------------------------------------ dead variant
    dead_depth = 3

    def begin_dead(self):
        self.dead_phase = True
        hp, mx = self.hp()
        self.p.poke_hp(0, 2)
        self.pokes["dead_hp"] += 1
        self.ev(f"POKE dead-variant: HP {hp}/{mx} -> 2, no healing / no god from here")

    # ------------------------------------------------------------------ stuck recovery
    def unstick(self):
        r = self.map_room
        if r == self.lair and self.hostiles():            # a fight in the lair that is simply going on: not stuck
            self.sig.clear()
            self.act("WAIT")
            return
        self.unstick_n += 1
        self.ev(f"STUCK #{self.unstick_n} in r{r} goal {self.cur_goal} hero {self.hero_pos()[1:]} st {self.rb('ST_FLAGS'):#x} ign {dict(self.ignore)} "
                f"hostiles {[(h['slot'], h['kind'], h['x'], h['y'], h['s'], h['react'], hex(h['fl'])) for h in self.hostiles()]}")
        if self.unstick_n % 3 == 1:
            self.act("WAIT")
            return
        if self.cur_goal and self.cur_goal[0] in (0, 1):
            s, x = self.cur_goal
            e, s0, x0, _ = self.hero_pos()
            if (s0, x0) != (s, x):
                self.poke_pos(s, x, "stuck streak")
                return
        # at the goal but the action keeps failing (locked door / no exit): leave this room out of the plan
        self.skip_rooms.add(r)
        for it in self.floor_items(r):
            self.picked_skip.add((r, it["i"]))
        self.ev(f"giving up on r{r}")
        if self.unstick_n > 14:
            raise RunEnd(f"unrecoverable stuck in r{r} D{self.depth}")

    # ------------------------------------------------------------------ the plan
    def progress(self):
        r = self.map_room
        fl = self.lflags()
        e0, s0, x0, _ = self.hero_pos()
        hs = [h for h in self.hostiles() if self.ignore.get(h["slot"], -1) < self.mon.ticks
              and abs(h["x"] - x0) <= 16]
        self.branch = 'items'
        # 1. floor items in this room (not while something hostile and near is around)
        if not hs:
            st = self.pickup_step()
            if st == "moved":
                return
        # 2. D8 endgame
        if self.depth == 8 and not fl & LF["GRATE_OPEN"]:
            if not fl & LF["SEAL_OPEN"]:
                return self.to_lair_fight()
            if self.rb("TOME_HP") > 0:
                return self.tome()
        # 3. boss dead / tome destroyed: leave through the lair exit
        if fl & LF["GRATE_OPEN"]:
            self.branch = 'leave'
            return self.leave_level()
        # 4. explore the rest of the level, the lair last
        todo = [q for q in self.rooms if q not in self.visited and q != self.lair and q != self.sanctum
                and q not in self.skip_rooms]
        if todo:
            self.branch = f'todo {todo}'
            todo.sort(key=lambda q: len(self.room_path(r, q) or [0] * 99))
            tgt = todo[0]
            st = self.goto_room(tgt)
            if st == "stuck" and not self.room_path(r, tgt):
                self.skip_rooms.add(tgt)
            return
        self.branch = 'to_lair'
        return self.to_lair_fight()

    def to_lair_fight(self):
        r = self.map_room
        if r != self.lair:
            if not self.room_path(r, self.lair):
                raise RunEnd(f"no path to the lair r{self.lair} from r{r}")
            self.cur_goal = None
            st = self.goto_room(self.lair)
            return
        # in the lair: the boss is somewhere: hunt it (fight() ignores far / other-storey ones)
        hs = self.hostiles()
        e, s, x, _ = self.hero_pos()
        if hs:
            h = min(hs, key=lambda h: abs(h["x"] - x) + (0 if h["s"] == s else 30))

            self.ignore.pop(h["slot"], None)
            self.approach(h, s, x) or self.act("WAIT")
            return
        # nothing alive here but the grate/seal is still shut: wait (a bleeding Tome of respawns?)
        self.act("WAIT")

    def leave_level(self):
        r = self.map_room
        if r != self.lair:
            self.goto_room(self.lair)
            return
        col = room_model.field(self.blk, r, "RD_EXITCOL")
        self.cur_goal = (1, col)
        st = self.go_node(1, col)
        if st == "there":
            d0 = self.depth
            self.ev(f"descend at the lair exit (col {col}) LVL {self.rb('LVL')} HP {self.hp()}")
            if not self.act("J"):
                self.act("WAIT")
            self.p.until(lambda: self.rb("GAME_STATE") == GS_PLAYING or self.rb("GAME_STATE") in (GS_WIN, GS_DEAD), 900)
            return

    def tome(self):
        r = self.map_room
        sn = self.sanctum
        if r != sn:
            self.goto_room(sn)
            return
        # in the Sanctum: storey 1, next to the lectern
        lect = [(c, rr) for rr in range(S["STOREY_ROWS"], 18) for c in range(32)
                if self.cell_tf(c, rr) & TF["ATTACK"]]
        if not lect:
            raise RunEnd("no lectern cells in the Sanctum map")
        left = min(c for c, _ in lect) < 16
        lo, hi = self.reach_span(1)
        tx = lo if left else hi
        self.cur_goal = (1, tx)
        e, s, x, _ = self.hero_pos()
        st = self.go_node(1, tx)
        if st != "there":
            return
        key = "H" if left else "L"
        hp0 = self.rb("TOME_HP")
        # watch the flash / border on the hit tick: sampled by the monitor; log the first hits' state
        ok = self.act(key)
        hp1 = self.rb("TOME_HP")
        self.tome_log.append((hp0, hp1, ok, self.rb("TOME_FL"), self.mon.border()))
        self.ev(f"Tome bump: ok {ok} TOME_HP {hp0}->{hp1} TOME_FL {self.rb('TOME_FL')} hero HP {self.hp()}")
        if not ok:
            self.act("WAIT")
