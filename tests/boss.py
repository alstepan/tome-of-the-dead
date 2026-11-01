#!/usr/bin/env python3
"""3F-T8 bosses (game.md §9.2 'Boss guard', §1.1 / §9.4.4 the lair grate, §9.7 R1 golden, §9.1
Ogre SLAM, §8.6 never follows). Seeded generated games, the real level_descend to D1 / D4 / D7,
the hero walked into the lair through its door (real do_exit + lp_transition).

  E1  first lair entry: the boss slot == levelgen.lp_enter (post on the grate / the G1a shift),
      "THE GATE IS BARRED" logged, the 3 exit cells T_GRATE_SHUT, LF_GRATE_OPEN clear, BOSS_TRAP 0;
      golden: E_GOLD = LEK_GOLD, E_MAXHP = 2 x scaled + 6
  E2  DOWN on the shut grate (x = c, storey 1): no turn (F4), no exit, depth unchanged
  G1  leash: the hero standing on storey 1 at |x - c| = 9 -> the boss holds its post (5 turns);
      at 8 -> it engages (leaves the post toward him)
  G2  PROVOKED: a hit from outside the leash (deal_hit stub) -> LF_PROVOKED, the boss chases past
      R; the hero on storey 0 -> it walks home to c
  G3  leave + re-enter: PROVOKED cleared, the boss back at its post with its exact hp
  F1  (user playtest bug) the boss next to the hero at the lair door: the hero leaves -> the boss
      stays in the lair (record), comes back with exact hp; BOSS_TRAP 0
  F2  Teleport (EX_TELE) with the boss adjacent: the boss stays in the lair record; BOSS_TRAP 0
  S1  Ogre (D4): counter 2 -> it SLAMs from gap 2; a SLAM hit: hero HP lost in 1.5 x [1d10+2]
      and STUNNED; counter 3 -> 1 next turn; at counter 0 a gap-2 hero is not attacked
  K1  the boss killed on the grate (hero standing ON the open grate when it dies): tiles 13 -> 26,
      LF_GRATE_OPEN, "A GATE GLEAMS" logged, the hero did not fall; DOWN at c descends
  X   golden-boss XP: the boss kill adds game.md 4.1's XP (D1 20 .. D7 90); an escort of its kind gives base KXP
  GL  golden glow: a stationary golden boss steps its attr in both screens (bank 7 == bank 5 on
      its footprint every tick, 3 distinct attrs seen over 16 ticks)
Build with -DDEBUG_KIT=0. ZRCP_PORT=<port> python3 tests/boss.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import levelgen as G  # noqa: E402
import room_model  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, stand_y, attr_at, F3  # noqa: E402
from lp import T as Proto, w16, want_slots  # noqa: E402
from world import log_row, text6, STRINGS  # noqa: E402

STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT, EF_DYING = 1, 2, 4, S["EF_LEFT"], S["EF_DYING"]
GS_PLAYING = S["GS_PLAYING"]
F1 = S["FLOOR_ROW1"]
TXT = dict(STRINGS)
fails = []
GXP = {1: 20, 2: 30, 3: 45, 4: 60, 5: 65, 6: 80, 7: 90}      # game.md 4.1 boss XP by depth
KXP_BASE = {1: 3, 2: 4, 3: 9, 5: 12, 6: 10}


def check(name, ok, got=None):
    if not ok:
        fails.append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f": got {got}"), flush=True)


def eb(p, slot, off):
    return p.rb(S["P_ENTITIES"] + slot * STRIDE + S[off])


def boss_slot(p):
    want = p.rb("LP_BOSS")
    for s_ in range(1, 16):
        e = p.ent(s_)
        if e["FLAGS"] & EF_ACTIVE and not e["FLAGS"] & EF_DYING and e["ROOM"] == p.rb("LVL_LAIR") \
                and (e["KIND"] | eb(p, s_, "E_GOLD")) == want:
            return s_
    return None


def rec_entries(p, r):
    ro = S["LP_REC"] + 9 * r
    hdr = p.rb(ro)
    return [(p.rb(ro + 1 + 2 * i), p.rb(ro + 2 + 2 * i)) for i in range(hdr & 7)], hdr


class Lair:
    def __init__(self, p, depth, seed, hero=0):
        self.p = p
        self.depth = depth
        p.proto_start = 0
        p.boot(hero=hero, freeze=1)
        p.wmem(S["MASTER_SEED"], w16(seed))
        pc0 = p.pc()
        ok, _ = p.code([0x3E, depth - 1, 0x32] + w16(S["LVL_DEPTH"]) + [0xCD] + w16(S["level_descend"]), game=True)
        p.z.cmd("set-register PC=%d" % pc0)
        p.release()
        p.settle(4)
        self.ok = ok and p.rb("LVL_DEPTH") == depth
        self.blk = room_model.read_block(p)
        b = self.blk
        self.lair = b[S["LVL_LAIR"] - room_model.BASE]
        self.c = room_model.field(b, self.lair, "RD_EXITCOL")
        ex = room_model.field(b, self.lair, "RD_EXITS")
        self.side = "L" if ex & S["RDX_L"] else "R"
        self.nb = self.lair - 1 if self.side == "L" else self.lair + 1
        self.s = 1 if ex & S["RDX_LS1" if self.side == "L" else "RDX_RS1"] else 0
        ei = S["EDGE_TAB"] + room_model.edge_index(self.lair, self.side)
        p.wb(ei, (p.rb(ei) & ~(S["EG_LOCK"] | S["EG_SEAL"]) & 255) | (S["EG_OPEN"] if p.rb(ei) & S["EG_DOOR"] else 0))
        self.kw = p.kb(p.rb("HERO_KIND"), "KT_BW")
        self.kh = p.kb(p.rb("HERO_KIND"), "KT_BH")
        self.trap0 = p.rb("BOSS_TRAP")

    def ingame(self, code):
        p = self.p
        pc0 = p.pc()
        ok, _ = p.code(code, game=True)
        p.z.cmd("set-register PC=%d" % pc0)
        return ok

    def put_hero(self, r, x, s_, left=False):
        p = self.p
        p.wb("CUR_ROOM", r)
        p.set_ent(0, ROOM=r, X=x, Y=stand_y(s_, self.kh), PX=x * 8, PY=stand_y(s_, self.kh) * 8,
                  FLAGS=EF_ACTIVE | EF_PLAYER | (EF_LEFT if left else 0), MODE=0, DVIS=0)
        self.ingame([0x3E, r, 0xCD] + w16(S["room_show"]) + [0xCD] + w16(S["vis_reset"])
                    + [0xCD] + w16(S["present_full"]))
        p.settle(2)

    def place_hero(self, x, s_, left=False):
        """In the current room (no rebuild)."""
        self.p.set_ent(0, X=x, Y=stand_y(s_, self.kh), PX=x * 8, PY=stand_y(s_, self.kh) * 8,
                       FLAGS=EF_ACTIVE | EF_PLAYER | (EF_LEFT if left else 0), MODE=0)

    def enter(self):
        """From the door-side neighbour (nobody else there) into the lair through the real do_exit."""
        p = self.p
        for k in range(1, 16):
            if p.ent(k)["ROOM"] != self.lair:
                p.set_ent(k, FLAGS=0)
        x, key = (32 - 2 - self.kw, "L") if self.side == "L" else (2, "H")
        ro = S["LP_REC"] + 9 * self.nb                # the hero is put there without an lp_enter:
        if not p.rb(ro) & 0x80:                       # a FRESH record would bank its quota as
            p.wmem(ro, [0x80] + [0] * 8)              # garbage entries (lp_bank's VISITED bit)
        self.put_hero(self.nb, x, self.s, left=(self.side == "R"))
        self.lp_before = p.lp()
        for _ in range(24):
            if p.rb("CUR_ROOM") == self.lair:
                break
            p.turn(key)
        p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
        p.settle(2)
        return p.rb("CUR_ROOM") == self.lair

    def leave(self):
        p = self.p
        x = 2 if self.side == "L" else 32 - 2 - self.kw
        self.place_hero(x, self.s, left=(self.side == "L"))
        key = "H" if self.side == "L" else "L"
        for _ in range(12):
            if p.rb("CUR_ROOM") == self.nb:
                break
            p.turn(key)
        p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
        p.settle(2)
        return p.rb("CUR_ROOM") == self.nb


def boss_at(p, sl, x):
    h = p.kb(p.ent(sl)["KIND"], "KT_BH")
    p.set_ent(sl, X=x, PX=x * 8, Y=stand_y(1, h), PY=stand_y(1, h) * 8, MODE=0)


def main():
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = Proto(h)
        model_sweep()
        post_overlap()
        trap_ub7(p)
        for depth, seed in ((1, 0x1B21), (2, 0x2B22), (3, 0x3B23), (4, 0x4B24), (5, 0x5B25), (6, 0x6B26)):
            reentry(p, depth, seed)
        for depth, seed in ((1, 0x1B01), (2, 0x2B02), (3, 0x3B03), (4, 0x4B04), (5, 0x5B05), (6, 0x6B16), (7, 0x7B07)):
            run(p, depth, seed)
        glow(p)
    print(f"boss: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
    return 1 if fails else 0


def run(p, depth, seed):
    L = Lair(p, depth, seed)
    tag = f"D{depth}"
    check(f"{tag} setup: level_descend to D{depth}", L.ok, p.rb("LVL_DEPTH"))
    if not L.ok:
        return
    lair, c = L.lair, L.c
    # ---------------- E1 -------------------------------------------------
    ok = L.enter()
    hx = 1 if L.side == "L" else 31 - L.kw
    wl, out = G.lp_enter(L.blk, _visited(L.lp_before, L.nb), lair, L.s, hx, L.kw, f3=True)
    sl = p.slots()
    bs = boss_slot(p)
    check(f"{tag} E1 entered the lair r{lair} (door {L.side}, storey {L.s}, c {c})", ok, p.rb("CUR_ROOM"))
    check(f"{tag} E1 slots == levelgen.lp_enter (boss post / escort; no stream step for them)",
          sl == want_slots(p, L.blk, lair, out), (sl, out))
    check(f"{tag} E1 the boss stands on storey 1 at c {c} (or the G1a shift)",
          bs is not None and p.ent(bs)["Y"] >= 9
          and (p.ent(bs)["X"] == c or L.s == 1), (bs, bs and p.ent(bs)))
    m = p.z.read_memory(S["ROOM_MAP"], 576)
    check(f"{tag} E1 grate shut: T_GRATE_SHUT x 3 on row 17, LF_GRATE_OPEN clear",
          all(m[F1 * 32 + c + k] == S["T_GRATE_SHUT"] for k in range(3)) and not p.rb("LVL_FLAGS") & 1,
          (list(m[F1 * 32 + c:F1 * 32 + c + 3]), p.rb("LVL_FLAGS")))
    p.until(lambda: p.rb("LOG_QN") == 0, 200)
    p.settle(2)
    check(f"{tag} E1 '{TXT['gate_barred']}' logged on the first lair entry",
          log_row(p.frame(), 23) == text6(TXT["gate_barred"]), "")
    if bs is not None:
        kb = p.rb("LP_BOSS")
        check(f"{tag} E1 E_GOLD / E_MAXHP of the boss (golden 2 x scaled + 6)",
              eb(p, bs, "E_GOLD") == kb & 0x20 and p.ent(bs)["MAXHP"] == G.k3_hp(kb, depth),
              (eb(p, bs, "E_GOLD"), p.ent(bs)["MAXHP"]))
    check(f"{tag} E1 BOSS_TRAP unchanged", p.rb("BOSS_TRAP") == L.trap0, p.rb("BOSS_TRAP"))
    if bs is None:
        return
    hp0 = p.ent(bs)["HP"]
    # clear everyone but the boss
    for k in range(1, 16):
        if k != bs:
            p.set_ent(k, FLAGS=0)
    # ---------------- E2 -------------------------------------------------
    boss_at(p, bs, c + 8 if c + 8 + 4 <= 29 else c - 8)
    L.place_hero(c, 1)
    d0, t0 = p.rb("LVL_DEPTH"), p.rw("TURN_COUNTER")
    nt = p.no_turn("J")
    check(f"{tag} E2 DOWN on the shut grate: no turn, no exit (F4)",
          nt and p.rb("LVL_DEPTH") == d0 and p.rb("EXIT_KIND") == 0, (nt, p.rw("TURN_COUNTER") - t0))
    # ---------------- G1 leash -------------------------------------------
    boss_at(p, bs, c)
    wb = p.kb(p.ent(bs)["KIND"], "KT_BW")
    far = c + 9 if c + 9 + L.kw <= 29 else c - 9
    if far >= 2:
        L.place_hero(far, 1, left=far > c)
        for _ in range(5):
            p.turn("WAIT")
        check(f"{tag} G1 hero at |dx| 9 on storey 1: the boss holds the post (5 turns)",
              p.ent(bs)["X"] == c, p.ent(bs)["X"])
        near = c + 8 if far > c else c - 8
        L.place_hero(near, 1, left=near > c)
        for _ in range(2):
            p.turn("WAIT")
        check(f"{tag} G1 hero at |dx| 8: engaged, the boss leaves the post toward him",
              p.ent(bs)["KIND"] == S["K_NECRO"]         # a ranged caster engages by casting from its post
              or (p.ent(bs)["X"] != c and (p.ent(bs)["X"] - c) * (near - c) > 0),
              p.ent(bs)["X"])
    # ---------------- G2 PROVOKED ----------------------------------------
    boss_at(p, bs, c)
    p.set_ent(bs, HP=hp0)
    far = c + 12 if c + 12 + L.kw <= 29 else c - 12
    if far >= 2:
        L.place_hero(far, 1, left=far > c)
        ok = L.ingame([0x3A] + w16(S["PORT_7FFD_SHADOW"]) + [0xF5, 0x3E, 3, 0xCD] + w16(S["page_bank"])
                      + [0xDD, 0x21] + w16(S["P_ENTITIES"]) + [0x3E, bs, 0x01, 0, 1, 0x1E, 0,
                                                               0xCD] + w16(S["deal_hit"])
                      + [0xF1, 0xCD] + w16(S["restore_page"]))
        check(f"{tag} G2 a hit from |dx| 12 (deal_hit): LF_PROVOKED set", ok and p.rb("LVL_FLAGS") & S["LF_PROVOKED"],
              p.rb("LVL_FLAGS"))
        hp1 = p.ent(bs)["HP"]
        for _ in range(4):
            p.turn("WAIT")
        bx = p.ent(bs)["X"]
        check(f"{tag} G2 provoked: the boss chases past the leash (x {bx})",
              (bx - c) * (far - c) > 0, bx)
        # hero to storey 0 (anywhere standable: the start of the lair's storey 0 band)
        L.place_hero(far, 0, left=far > c)
        for _ in range(14):
            p.turn("WAIT")
            if p.ent(bs)["X"] == c:
                break
        check(f"{tag} G2 hero on storey 0: the boss walks home to c", p.ent(bs)["X"] == c, p.ent(bs)["X"])
        # ---------------- G3 leave + re-enter -----------------------------
        ok1 = L.leave()
        ent, hdr = rec_entries(p, lair)
        kb = p.rb("LP_BOSS")
        check(f"{tag} G3 left the lair: the boss banked with exact hp {hp1}",
              ok1 and (kb, hp1) in [(k & 0x3F, v) for k, v in ent], (ok1, ent))
        ok2 = L.enter()
        bs = boss_slot(p)
        check(f"{tag} G3 re-entered: PROVOKED cleared, the boss at its post with hp {hp1}",
              ok2 and bs is not None and not p.rb("LVL_FLAGS") & S["LF_PROVOKED"] and p.ent(bs)["HP"] == hp1
              and (p.ent(bs)["X"] == c or L.s == 1), (ok2, bs, p.rb("LVL_FLAGS")))
        if bs is None:
            return
    # ---------------- F1 the boss never follows (user playtest) ---------
    for k in range(1, 16):
        if k != bs:
            p.set_ent(k, FLAGS=0)
    hp2 = p.ent(bs)["HP"]
    dx = 2 if L.side == "L" else 32 - 2 - L.kw
    bh = p.kb(p.ent(bs)["KIND"], "KT_BH")
    bxx = dx + L.kw + 1 if L.side == "L" else dx - wb - 1
    p.set_ent(bs, X=bxx, PX=bxx * 8, Y=stand_y(L.s, bh), PY=stand_y(L.s, bh) * 8, MODE=0)
    p.wb("LVL_FLAGS", p.rb("LVL_FLAGS") | S["LF_PROVOKED"])
    ok1 = L.leave()
    nb_boss = [x for x in p.slots() if x[2] == L.nb and (x[1] | eb(p, x[0], "E_GOLD")) == p.rb("LP_BOSS")]
    ent, _ = rec_entries(p, lair)
    check(f"{tag} F1 the boss beside the hero at the lair door: it does NOT follow, stays banked in the lair (hp {hp2})",
          ok1 and not nb_boss and (p.rb("LP_BOSS"), hp2) in [(k & 0x3F, v) for k, v in ent], (ok1, nb_boss, ent))
    check(f"{tag} F1 BOSS_TRAP unchanged", p.rb("BOSS_TRAP") == L.trap0, p.rb("BOSS_TRAP"))
    ok2 = L.enter()
    bs = boss_slot(p)
    check(f"{tag} F1 back in the lair: the boss is there with hp {hp2}",
          ok2 and bs is not None and p.ent(bs)["HP"] == hp2, (ok2, bs))
    if bs is None:
        return
    # ---------------- F2 teleport with the boss adjacent -----------------
    bx = p.ent(bs)["X"]
    hxx = bx + wb + 1 if bx + wb + 1 + L.kw <= 29 else bx - L.kw - 1
    L.place_hero(hxx, 1, left=hxx > bx)
    p.wb("EXIT_KIND", S["EX_TELE"])
    p.turn("WAIT")
    p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
    ent, _ = rec_entries(p, lair)
    check(f"{tag} F2 teleport with the boss adjacent: hero left the lair, the boss is in the lair record",
          p.rb("CUR_ROOM") != lair and (p.rb("LP_BOSS"), hp2) in [(k & 0x3F, v) for k, v in ent],
          (p.rb("CUR_ROOM"), ent))
    check(f"{tag} F2 BOSS_TRAP unchanged (the boss exists)", p.rb("BOSS_TRAP") == L.trap0, p.rb("BOSS_TRAP"))
    ok2 = L.enter()
    bs = boss_slot(p)
    if bs is None:
        check(f"{tag} F2 re-entry: the boss", False, p.slots())
        return
    for k in range(1, 16):
        if k != bs:
            p.set_ent(k, FLAGS=0)
    # ---------------- S1 Ogre SLAM ---------------------------------------
    if p.ent(bs)["KIND"] == S["K_OGRE"]:
        slam(p, L, bs, c, wb, tag)
    # ---------------- X  golden-boss XP by depth (this review: bxp_d) ----
    bxx = c + 3 if c + 3 + wb - 1 <= 29 else c - wb
    golden = bool(p.rb("LP_BOSS") & S["LEK_GOLD"])
    if golden:                                  # an escort of the same kind (E_GOLD 0): base KXP, no gate
        fl = p.ent(bs)["FLAGS"]
        sv = bytes(p.z.read_memory(S["P_ENTITIES"] + bs * STRIDE, STRIDE))
        es = next(k for k in range(1, 16) if k != bs and not p.ent(k)["FLAGS"] & EF_ACTIVE)
        p.set_ent(bs, FLAGS=0)
        p.wmem(S["P_ENTITIES"] + es * STRIDE, list(sv))
        p.wb(S["P_ENTITIES"] + es * STRIDE + S["E_GOLD"], 0)
        p.set_ent(es, HP=1, MAXHP=1, FLAGS=fl & ~EF_LEFT & 255 | (EF_LEFT if bxx > c else 0))
        boss_at(p, es, bxx)
        L.place_hero(c, 1, left=bxx < c)
        p.set_ent(0, HP=99)
        xp0 = p.rw("XP")
        for _ in range(20):
            if not p.ent(es)["FLAGS"] & EF_ACTIVE or p.ent(es)["FLAGS"] & EF_DYING:
                break
            p.turn("L" if bxx > c else "H")
        p.settle(6)
        check(f"{tag} X escort of the boss kind (E_GOLD 0): +base KXP {KXP_BASE[depth]}, grate stays shut",
              p.rw("XP") - xp0 == KXP_BASE[depth] and not p.rb("LVL_FLAGS") & 1, (p.rw("XP") - xp0, p.rb("LVL_FLAGS")))
        p.set_ent(es, FLAGS=0)
        p.wmem(S["P_ENTITIES"] + bs * STRIDE, list(sv))
    # ---------------- K1 kill on the grate -------------------------------
    xp0 = p.rw("XP")
    p.set_ent(bs, HP=1)
    boss_at(p, bs, bxx)
    L.place_hero(c, 1, left=bxx < c)
    if bxx > c:
        p.set_ent(bs, FLAGS=p.ent(bs)["FLAGS"] | EF_LEFT)
    p.set_ent(0, HP=99)
    y0 = p.ent(0)["Y"]
    key = "L" if bxx > c else "H"
    lines = []

    def grab(fr, _e):
        for r_ in range(19, 24):
            ln = log_row(fr, r_)
            if ln not in lines:
                lines.append(ln)
    for _ in range(20):
        if p.rb("LVL_FLAGS") & 1:
            break
        p.turn(key, per_tick=grab)
    for _ in range(300):
        if p.idle() and p.rb("LOG_QN") == 0:
            break
        p.tick()
        grab(p.frame(), None)
    p.settle(4)
    check(f"{tag} X boss kill: XP delta == game.md 4.1 ({GXP[depth]})", p.rw("XP") - xp0 == GXP[depth], p.rw("XP") - xp0)
    m = p.z.read_memory(S["ROOM_MAP"], 576)
    check(f"{tag} K1 the boss killed beside / the hero ON the grate: LF_GRATE_OPEN, tiles 13 -> 26",
          p.rb("LVL_FLAGS") & 1 and all(m[F1 * 32 + c + k] == S["T_GRATE"] for k in range(3)),
          (p.rb("LVL_FLAGS"), list(m[F1 * 32 + c:F1 * 32 + c + 3])))
    check(f"{tag} K1 '{TXT['gate_gleams']}' logged", text6(TXT["gate_gleams"]) in lines, "")
    check(f"{tag} K1 the hero did not fall (y {y0})", p.ent(0)["Y"] == y0 and p.ent(0)["X"] == c,
          (p.ent(0)["X"], p.ent(0)["Y"]))
    d0 = p.rb("LVL_DEPTH")
    p.turn("J")
    p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 900)
    check(f"{tag} K1 DOWN at c on the open grate descends (D{d0} -> D{d0 + 1})", p.rb("LVL_DEPTH") == d0 + 1,
          p.rb("LVL_DEPTH"))


def model_sweep():
    """R0 (UB6 / the D2 Spider Queen report): main's lp_enter re-placed a BANKED boss through
    lp_place's 8 random tries and kept it in the record, invisible, when none was legal (main's
    model: 5-10 % of lair re-entries, D4 10.5 %, D2 9.2 %). lp_post places it at its post on every
    entry: 0 misses over 1,750 levels x 3 re-entries x 2 arrivals."""
    import random
    D = G.D
    rng = random.Random(7)
    tot = miss = 0
    for i in range(1750):
        d = 1 + i % 7
        b = G.generate(d, rng.randrange(1, 65536), f3=F3)
        lp = G.lp_budget(b, d, f3=True)
        lair = b[G.H["LVL_LAIR"]]
        ex = G._rd(b, lair, "RD_EXITS")
        s_ = 1 if ex & D["RDX_LS1" if ex & D["RDX_L"] else "RDX_RS1"] else 0
        hx = 1 if ex & D["RDX_L"] else 28
        lp2, out = G.lp_enter(b, lp, lair, s_, hx, 3, f3=True)
        boss = lp[G.lp_off("LP_BOSS")]
        lp2 = bytearray(lp2)
        ro = G.lp_off("LP_REC") + lair * 9
        lp2[ro] = 0x80 | len(out)
        for k, (kb, hp, *_r) in enumerate(out):
            lp2[ro + 1 + 2 * k], lp2[ro + 2 + 2 * k] = kb, hp
        for v in range(1, 4):
            lp2[G.lp_off("ROOM_VISITS") + lair] = v
            for s2, hx2 in ((s_, hx), (0, 14)):
                tot += 1
                miss += not any(kb & 0x3F == boss for kb, *_r in G.lp_enter(b, bytes(lp2), lair, s2, hx2, 3, f3=True)[1])
    check(f"R0 model: a banked boss is placed on every lair re-entry ({tot} re-entries)", miss == 0, miss)


def post_overlap():
    """P1 (T8 review): a body placed before the boss in the same record over the post's cols
    (LPC_BODY: never exempt) shifts the post (model; the Z80 == model: tests/lp.py A7)."""
    D = G.D
    b = G.generate(2, 0x2222, f3=F3)
    lp = G.lp_budget(b, 2, f3=True)
    lair = b[G.H["LVL_LAIR"]]
    c = G._rd(b, lair, "RD_EXITCOL")
    kb = lp[G.lp_off("LP_BOSS")]
    w = G.k3_info(kb)[0]
    free = G.lp_post(b, lp, lair, kb, w, False, 0, 14, 3, [], G.k3_info, G.LEK_ROW_MASK)
    hit = G.lp_post(b, lp, lair, kb, w, False, 0, 14, 3, [(1, c, c + 2)], G.k3_info, G.LEK_ROW_MASK)
    check(f"P1 model: the post is c {c} with the cells free; a body over c..c+2 -> shifted off it",
          free == (1, c) and (hit is None or hit[1] >= c + 3 or hit[1] + w - 1 < c), (free, hit))


def trap_ub7(p):
    """T1 (T8 review): the UB7 state (the boss left in the lair record while the hero enters: here
    every slot is taken, so lp_spawn cannot place it) trips BOSS_TRAP; the normal entry does not."""
    L = Lair(p, 2, 0x2B77)
    if not (L.ok and L.enter()):
        check("T1 setup", False, "")
        return
    bs = boss_slot(p)
    check("T1 first entry: the boss is a slot, BOSS_TRAP unchanged", bs is not None and p.rb("BOSS_TRAP") == L.trap0,
          (bs, p.rb("BOSS_TRAP")))
    L.leave()
    t0 = p.rb("BOSS_TRAP")
    for k in range(1, 16):                         # every slot busy elsewhere (room $0F: never a room)
        if p.ent(k)["ROOM"] != L.lair or not p.ent(k)["FLAGS"] & EF_ACTIVE:
            p.set_ent(k, FLAGS=EF_ACTIVE | EF_HOSTILE, ROOM=0x0F)
    x = 32 - 2 - L.kw if L.side == "L" else 2
    L.place_hero(x, L.s, left=(L.side == "R"))
    key = "L" if L.side == "L" else "H"
    for _ in range(12):
        if p.rb("CUR_ROOM") == L.lair:
            break
        p.turn(key)
    p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
    ent, _ = rec_entries(p, L.lair)
    check("T1 the boss could not spawn (no free slot): it is only in the lair record, BOSS_TRAP + 1",
          p.rb("CUR_ROOM") == L.lair and boss_slot(p) is None
          and any(k & 0x3F == p.rb("LP_BOSS") for k, _v in ent) and p.rb("BOSS_TRAP") == (t0 + 1) & 255,
          (p.rb("CUR_ROOM"), ent, p.rb("BOSS_TRAP") - t0))


def reentry(p, depth, seed):
    """R1 (UB6 / D2 report): enter the lair, damage the boss, leave by the door, go 2 rooms away
    (the neighbour's other neighbour, real do_exit), come back, 4 times: the boss is in the lair
    every time with its exact hp; BOSS_TRAP unchanged."""
    L = Lair(p, depth, seed)
    tag = f"R1 D{depth}"
    if not (L.ok and L.enter()):
        check(f"{tag} setup", False, (L.ok, p.rb("CUR_ROOM")))
        return
    bs = boss_slot(p)
    if bs is None:
        check(f"{tag} the boss on the first entry", False, p.slots())
        return
    hp = max(1, p.ent(bs)["HP"] - 3)
    p.set_ent(bs, HP=hp)
    ok_all, seen = True, []
    for n in range(4):
        for k in range(1, 16):
            if k != boss_slot(p):
                p.set_ent(k, FLAGS=0)              # nothing else in the hero's way
        if not L.leave():
            ok_all = False
            break
        far = L.nb - 1 if L.side == "L" else L.nb + 1
        exn = room_model.field(L.blk, L.nb, "RD_EXITS")
        bit = S["RDX_L"] if L.side == "L" else S["RDX_R"]
        if far // 3 == L.nb // 3 and 0 <= far <= 8 and exn & bit:   # 2 rooms away, then back
            s2 = 1 if exn & S["RDX_LS1" if L.side == "L" else "RDX_RS1"] else 0
            ei = S["EDGE_TAB"] + room_model.edge_index(L.nb, L.side)
            p.wb(ei, (p.rb(ei) & ~(S["EG_LOCK"] | S["EG_SEAL"]) & 255) | (S["EG_OPEN"] if p.rb(ei) & S["EG_DOOR"] else 0))
            x0 = 2 if L.side == "L" else 32 - 2 - L.kw
            L.place_hero(x0, s2, left=(L.side == "L"))
            for _ in range(12):
                if p.rb("CUR_ROOM") == far:
                    break
                p.turn("H" if L.side == "L" else "L")
            p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
            for k in range(1, 16):
                p.set_ent(k, FLAGS=0) if p.ent(k)["ROOM"] == far else None
            x1 = 32 - 2 - L.kw if L.side == "L" else 2
            L.place_hero(x1, s2, left=(L.side == "R"))
            for _ in range(12):
                if p.rb("CUR_ROOM") == L.nb:
                    break
                p.turn("L" if L.side == "L" else "H")
            p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
        ok = L.enter()
        bs = boss_slot(p)
        seen.append((ok, bs and p.ent(bs)["HP"]))
        ok_all &= ok and bs is not None and p.ent(bs)["HP"] == hp
    check(f"{tag}: leave, 2 rooms away, back x 4: the boss is in its lair every time with hp {hp}", ok_all, seen)
    check(f"{tag}: BOSS_TRAP unchanged", p.rb("BOSS_TRAP") == L.trap0, p.rb("BOSS_TRAP"))


def slam(p, L, bs, c, wb, tag):
    """The Ogre: counter 2 -> a reach-2 SLAM; a hit = x 1.5 and STUNNED 1."""
    boss_at(p, bs, c)
    hx = c + wb + 2                                   # gap 2 to the right
    if hx + L.kw - 1 > 29:
        hx = c - 2 - L.kw
    rcd = S["P_ENTITIES"] + bs * STRIDE + S["E_RCD"]
    # counter 0, gap 2: no attack (reach 1); counter advances (1)
    L.place_hero(hx, 1, left=hx > c)
    p.set_ent(0, HP=99, MAXHP=99)
    p.wb(rcd, 0)
    p.set_ent(bs, FLAGS=(p.ent(bs)["FLAGS"] & ~EF_LEFT & 255) | (EF_LEFT if hx < c else 0))
    p.turn("WAIT")
    x1 = p.ent(bs)["X"]
    check(f"{tag} S1 counter 0, gap 2: no SLAM (hero HP 99), counter 1",
          p.ent(0)["HP"] == 99 and p.rb(rcd) & 3 == 1, (p.ent(0)["HP"], p.rb(rcd)))
    hit = None
    for _ in range(12):
        boss_at(p, bs, c)
        L.place_hero(hx, 1, left=hx > c)
        p.set_ent(0, HP=99)
        p.wb(S["ST_FLAGS"], 0)
        p.wb(rcd, 2)
        p.turn("WAIT")
        lost = 99 - p.ent(0)["HP"]
        check(f"{tag} S1 counter 2: the Ogre attacks from gap 2 (counter -> 3)", p.rb(rcd) & 3 == 3, p.rb(rcd))
        if lost:
            hit = lost
            break
    if hit is None:
        check(f"{tag} S1 a SLAM hit in 12 tries", False, "")
        return
    lo, hi = 3 + 3 // 2, 12 + 12 // 2 + 1       # 1d10+2 (depth scaling on hp only) x 1.5, rounding down; DEF may cut
    check(f"{tag} S1 SLAM hit: hero lost {hit} (1.5 x [3..12] - DEF, min 1) and is STUNNED",
          1 <= hit <= hi and p.rb(S["ST_FLAGS"]) & 3 == S["HOLD_STUNNED"], (hit, p.rb(S["ST_FLAGS"])))
    p.wb(S["ST_FLAGS"], 0)
    p.wb(S["ST_T1"], 0)
    L.place_hero(c - 8 if c - 8 >= 2 else c + wb + 8, 1)
    t0 = p.rw("TURN_COUNTER")
    for _ in range(4):                               # (the stun's held-wait / release latch)
        p.turn("WAIT")
        if p.rw("TURN_COUNTER") != t0:
            break
    check(f"{tag} S1 the turn after a SLAM: counter 3 -> 1", p.rb(rcd) & 3 == 1,
          (p.rb(rcd), p.rw("TURN_COUNTER") - t0, p.ent(bs)))


def glow(p):
    """A stationary golden boss (D1) cycles $06/$46/$47/$46 on its footprint in both screens."""
    L = Lair(p, 1, 0x1B11)
    if not L.ok or not L.enter():
        check("GL setup", False, "")
        return
    bs = boss_slot(p)
    if bs is None:
        check("GL boss", False, "")
        return
    for k in range(1, 16):
        if k != bs:
            p.set_ent(k, FLAGS=0)
    L.place_hero(L.c + 14 if L.c + 14 + L.kw <= 29 else L.c - 14, 0)
    seen, bad = set(), []
    for t in range(24):
        p.tick()
        e = p.ent(bs)
        if not e["DVIS"]:
            continue
        fr, comp = p.frame(), p.composed_frame()
        for cc in range(e["DCOL"], e["DCOL"] + e["DCOLS"]):
            for rr in range(e["DROW"], e["DROW"] + e["DROWS"]):
                if attr_at(fr, cc, rr) != attr_at(comp, cc, rr):
                    bad.append((t, cc, rr))
        seen.add(attr_at(fr, e["DCOL"] + 1, e["DROW"] + 2))
    check("GL golden glow: bank 7 attrs == bank 5 attrs on the boss's footprint every tick", not bad, bad[:4])
    check("GL golden glow: the attr steps $06 / $46 / $47 while it stands", {0x06, 0x46, 0x47} <= seen, seen)


def _visited(lp, r):
    lp = bytearray(lp)
    ro = S["LP_REC"] - S["LP_STATE"] + r * S["LR_STRIDE"]
    lp[ro] |= S["LR_VISITED"]
    return bytes(lp)


if __name__ == "__main__":
    sys.exit(main())
