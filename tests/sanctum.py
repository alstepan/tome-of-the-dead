#!/usr/bin/env python3
"""P3 SANCTUM-WIN: the real D8 ending (game.md §1.1 / §1.3; user rulings 2026-10-31).
Seeded generated games (F3_GEN build, DEBUG_KIT=0), the real level_descend D7 -> D8.

  G   generation: TOME_HP == TOME_MAX, the lair<->Sanctum edge LINK|DOOR|SEAL, LF_SEAL_OPEN
      clear; no FLOOR_LIST entry / trap in the Sanctum (6 D8 levels, both heroes)
  D0  the sealed door: a bump from the lair = "THE DOOR IS LOCKED", no turn
  K1  the Archmage killed by the hero (deal_hit): LF_SEAL_OPEN, EG_SEAL off the edge,
      "THE SEAL BREAKS"; the plank keeps its lock glyph until bumped
  K2  the Archmage killed by its own Mirror Helm return (deal_hit, attacker = the Archmage)
  D1  after the seal: the bump opens the door (1 turn, EG_OPEN), the hero walks into the Sanctum
  L   the Sanctum map: the lectern ids 15-18 on storey 1 at the dead-end wall == room_model
  H*  5 releases destroy the Tome, per attack type: melee bump, melee FIRE, Power Strike,
      Whirlwind, dagger, arrow (Warrior), Spark (Mage): TOME_HP 5 -> 0, "THE TOME SHUDDERS"
      per hit, the 5th -> GS_WIN + "THE TOME IS DESTROYED"; out of range / facing away: no hit
      (Power Strike refused: no turn, no MP)
  A   the aura: gap 5 -> -1 hp a turn (either facing), gap 6 / storey 0 -> none; HP 1 -> GS_DEAD
  R   leaving the Sanctum and coming back keeps TOME_HP (no regeneration), the lectern redrawn
ZRCP_PORT=<port> python3 tests/sanctum.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import levelgen as G  # noqa: E402
import items_model as M  # noqa: E402
import room_model  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, stand_y, F3  # noqa: E402
from lp import T as Proto, w16  # noqa: E402
from world import log_row, text6, STRINGS  # noqa: E402

STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT, EF_DYING = 1, 2, 4, S["EF_LEFT"], S["EF_DYING"]
GS_PLAYING, GS_WIN, GS_DEAD = S["GS_PLAYING"], S["GS_WIN"], S["GS_DEAD"]
TXT = dict(STRINGS)
EG = {k: S["EG_" + k] for k in ("LINK", "DOOR", "SEAL", "OPEN", "LOCK")}
fails = []


def check(name, ok, got=None):
    if not ok:
        fails.append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f": got {got}"), flush=True)


class D8:
    def __init__(self, p, master, hero=0):
        self.p = p
        p.proto_start = 0
        p.boot(hero=hero, freeze=1)
        p.wmem(S["MASTER_SEED"], w16(master))
        self.ingame([0x3E, 7, 0x32] + w16(S["LVL_DEPTH"]) + [0xCD] + w16(S["level_descend"]))
        p.release()
        p.settle(4)
        self.ok = p.rb("LVL_DEPTH") == 8 and p.rb("GAME_STATE") == GS_PLAYING
        self.blk = room_model.read_block(p)
        self.sn = p.rb("LVL_SANCTUM")
        self.lair = p.rb("LVL_LAIR")
        ex = room_model.field(self.blk, self.sn, "RD_EXITS")
        self.door_l = self.sn == 8                   # the lair's door to the Sanctum: its right side if S = 8
        self.s = 1 if ex & (S["RDX_LS1"] | S["RDX_RS1"]) else 0
        self.edge = S["EDGE_TAB"] + G.hedge(min(7, self.sn))
        self.kw = p.kb(p.rb("HERO_KIND"), "KT_BW")
        self.kh = p.kb(p.rb("HERO_KIND"), "KT_BH")
        self.left = self.sn == 6                     # the lectern on the Sanctum's left (cols 1-2)

    def ingame(self, code):
        p = self.p
        pc0 = p.pc()
        ok, _ = p.code(code, game=True)
        p.z.cmd("set-register PC=%d" % pc0)
        return ok

    def put_hero(self, r, x, s_, left=False):
        p = self.p
        p.wb("CUR_ROOM", r)
        y = stand_y(s_, self.kh)
        p.set_ent(0, ROOM=r, X=x, Y=y, PX=x * 8, PY=y * 8, HP=200, MAXHP=200,
                  FLAGS=EF_ACTIVE | EF_PLAYER | (EF_LEFT if left else 0), MODE=0, DVIS=0)
        self.ingame([0x3E, r, 0xCD] + w16(S["room_show"]) + [0xCD] + w16(S["vis_reset"])
                    + [0xCD] + w16(S["present_full"]))
        p.settle(2)

    def place(self, x, s_, left):
        y = stand_y(s_, self.kh)
        self.p.set_ent(0, X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0,
                       FLAGS=EF_ACTIVE | EF_PLAYER | (EF_LEFT if left else 0))
        self.p.tick(2)

    def at_gap(self, gap, facing=True, s_=1):
        """The hero on storey s_ of the Sanctum, `gap` empty cols from the lectern."""
        x = 3 + gap if self.left else 26 - gap
        self.place(x, s_, left=(self.left == facing))

    def arch(self, slot=1, hp=1):
        p = self.p
        k = S["K_ARCHMAGE"]
        y = stand_y(1, p.kb(k, "KT_BH"))
        x = 14
        p.set_ent(slot, KIND=k, ROOM=self.lair, X=x, Y=y, PX=x * 8, PY=y * 8, HP=hp, MAXHP=40, MODE=0,
                  FLAGS=EF_ACTIVE | EF_HOSTILE, REACT=0)
        p.wb(S["P_ENTITIES"] + slot * STRIDE + S["E_GOLD"], p.rb("LP_BOSS") & S["LEK_GOLD"])

    def deal(self, attacker, target, dmg):
        return self.ingame([0x3A] + w16(S["PORT_7FFD_SHADOW"]) + [0xF5, 0x3E, 3, 0xCD] + w16(S["page_bank"])
                           + [0xDD, 0x21] + w16(S["P_ENTITIES"] + attacker * STRIDE)
                           + [0x3E, target, 0x01, 0, dmg, 0x1E, 0, 0xCD] + w16(S["deal_hit"])
                           + [0xF1, 0xCD] + w16(S["restore_page"]))

    def last_line(self):
        p = self.p
        p.until(lambda: p.rb("LOG_QN") == 0, 200)
        p.settle(2)
        return log_row(p.frame(), 23)

    def door_key(self):
        return "L" if self.door_l else "H"              # game_lib: H = left, L = right


def play_mode(p):
    p.wb("GAME_STATE", GS_PLAYING)
    p.wb("TOME_HP", S["TOME_MAX"])


def items_absent(p):
    for hero in (0, 1):
        for m in (0x5300, 0x5301, 0x5302):
            L = D8(p, m + 16 * hero, hero)
            fl = p.z.read_memory(S["FLOOR_LIST"], S["FLOOR_MAX"] * S["FL_STRIDE"])
            rooms = [fl[i * S["FL_STRIDE"]] & S["FL_ROOM_MASK"] for i in range(S["FLOOR_MAX"])
                     if fl[i * S["FL_STRIDE"]] != S["FL_EMPTY"]]
            tr = p.z.read_memory(S["TRAP_LIST"], S["TRAP_MAX"] * S["TRAP_STRIDE"])
            trooms = [tr[i * S["TRAP_STRIDE"]] & S["TRF_ROOM_MASK"] for i in range(p.rb("TRAP_N"))]
            tag = f"G hero {hero} master {m + 16 * hero:#06x} (S {L.sn})"
            check(f"{tag}: D8, TOME_HP {S['TOME_MAX']}, sealed edge, LF_SEAL_OPEN clear",
                  L.ok and p.rb("TOME_HP") == S["TOME_MAX"]
                  and p.rb(L.edge) == EG["LINK"] | EG["DOOR"] | EG["SEAL"]
                  and not p.rb("LVL_FLAGS") & S["LF_SEAL_OPEN"], (L.ok, p.rb("TOME_HP"), p.rb(L.edge)))
            check(f"{tag}: no floor item / trap in the Sanctum", L.sn not in rooms and L.sn not in trooms,
                  (rooms, trooms))


def seal(p, master, mirror):
    L = D8(p, master)
    tag = f"{'K2' if mirror else 'K1'} S {L.sn}"
    lk_col = 1 if not L.door_l else 30
    x = 2 if not L.door_l else 30 - L.kw
    p.clear_slots()
    L.arch()
    L.put_hero(L.lair, x, L.s, left=not L.door_l)
    m = p.z.read_memory(S["ROOM_MAP"], 576)
    lock_cell = (9 * L.s + 4) * 32 + (1 if not L.door_l else 31)
    if not mirror:
        nt = p.no_turn(L.door_key())
        check(f"D0 S {L.sn}: the sealed door: a bump = no turn, '{TXT['locked']}'",
              nt and L.last_line() == text6(TXT["locked"]), (nt, m[lock_cell]))
    ok = L.deal(1 if mirror else 0, 1, 99)
    p.settle(2)
    check(f"{tag}: the Archmage dies ({'its own Mirror Helm return' if mirror else 'the hero'}): "
          "LF_SEAL_OPEN, EG_SEAL off the edge, the grate stays shut (LF_GRATE_OPEN clear)",
          ok and p.ent(1)["FLAGS"] & EF_DYING and p.rb("LVL_FLAGS") & S["LF_SEAL_OPEN"]
          and not p.rb("LVL_FLAGS") & S["LF_GRATE_OPEN"]
          and p.rb(L.edge) == EG["LINK"] | EG["DOOR"], (ok, p.ent(1), p.rb("LVL_FLAGS"), p.rb(L.edge)))
    check(f"{tag}: '{TXT['seal_breaks']}' logged", L.last_line() == text6(TXT["seal_breaks"]), "")
    m = p.z.read_memory(S["ROOM_MAP"], 576)
    check(f"{tag}: the plank keeps its lock glyph until opened", m[lock_cell] == S["T_DOOR_LOCK"], m[lock_cell])
    del lk_col
    if mirror:
        return None
    p.set_ent(1, FLAGS=0)
    t0 = p.rw("TURN_COUNTER")
    p.turn(L.door_key())
    check(f"D1 S {L.sn}: the bump opens the door (1 turn, EG_OPEN)",
          p.rw("TURN_COUNTER") == t0 + 1 and p.rb(L.edge) & EG["OPEN"], (p.rw("TURN_COUNTER") - t0, p.rb(L.edge)))
    for _ in range(8):
        if p.rb("CUR_ROOM") == L.sn:
            break
        p.turn(L.door_key())
    p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
    p.settle(2)
    check(f"D1 S {L.sn}: the hero walks into the Sanctum", p.rb("CUR_ROOM") == L.sn, p.rb("CUR_ROOM"))
    m = list(p.z.read_memory(S["ROOM_MAP"], 576))
    c0 = 1 if L.left else 29
    lect = [m[15 * 32 + c0], m[15 * 32 + c0 + 1], m[16 * 32 + c0], m[16 * 32 + c0 + 1]]
    want = room_model.render_room(room_model.read_block(p), L.sn)
    check(f"L S {L.sn}: the lectern 15-18 at cols {c0}-{c0 + 1} rows 15-16; ROOM_MAP == room_model",
          lect == [15, 16, 17, 18] and m == want,
          (lect, [(j % 32, j // 32, m[j], want[j]) for j in range(576) if m[j] != want[j]][:4]))
    return L


def five(L, tag, do, gap, setup=None):
    """5 releases at `gap` (facing it): each a hit, the 5th wins."""
    p = L.p
    play_mode(p)
    seen = []
    for i in range(5):
        L.at_gap(gap)
        if setup:
            setup()
        p.set_ent(0, HP=200)
        hp0 = p.rb("TOME_HP")
        do()
        p.until(lambda: p.idle(), 300)
        seen.append(hp0 - p.rb("TOME_HP"))
        if i == 0:
            check(f"{tag}: '{TXT['tome_hit']}'", L.last_line() == text6(TXT["tome_hit"]), "")
        if p.rb("GAME_STATE") != GS_PLAYING:
            break
    check(f"{tag}: 5 hits at gap {gap} destroy the Tome: TOME_HP 0, GS_WIN",
          seen == [1] * 5 and p.rb("TOME_HP") == 0 and p.rb("GAME_STATE") == GS_WIN,
          (seen, p.rb("TOME_HP"), p.rb("GAME_STATE")))
    p.tick(3)
    play_mode(p)


def miss(L, tag, do, gap, facing=True, turn=True):
    p = L.p
    play_mode(p)
    L.at_gap(gap, facing)
    p.set_ent(0, HP=200)
    t0, mp0 = p.rw("TURN_COUNTER"), p.rb("MP")
    do()
    p.until(lambda: p.idle(), 300)
    ok = p.rb("TOME_HP") == S["TOME_MAX"] and (turn or (p.rw("TURN_COUNTER") == t0 and p.rb("MP") == mp0))
    check(f"{tag}: no hit (gap {gap}, {'facing' if facing else 'facing away'})", ok,
          (p.rb("TOME_HP"), p.rw("TURN_COUNTER") - t0, mp0, p.rb("MP")))


def warrior_hits(p, L):
    key = "H" if L.left else "L"
    p.wb("MP", 99)
    p.wb("MAXMP", 99)
    p.wmem(S["ARANK"], w16(1 | 1 << 2))                     # Power Strike r1, Whirlwind r1
    p.wb("DAGGERS", 20)
    p.wb("ARROWS", 20)
    p.wb("HAS_BOW", 1)
    five(L, "H1 melee bump", lambda: p.turn(key), 0)
    five(L, "H2 melee FIRE (sword icon)", lambda: p.turn("C"), 0)
    miss(L, "H2 melee FIRE", lambda: p.no_turn("C"), 1, turn=False)
    five(L, "H3 Power Strike", lambda: p.turn("@1"), 0)
    miss(L, "H3 Power Strike refused", lambda: p.no_turn("@1"), 0, facing=False, turn=False)
    five(L, "H4 Whirlwind", lambda: p.turn("@2"), 0)
    five(L, "H5 dagger (range 6)", lambda: p.turn("@3"), 5)
    miss(L, "H5 dagger", lambda: p.turn("@3"), 6)
    five(L, "H6 arrow (range 14)", lambda: p.turn("@4"), 13)
    miss(L, "H6 arrow", lambda: p.turn("@4"), 3, facing=False)
    dodge(p, L)
    return key


def dodge(p, L):
    """H9 (review): one arrow that strikes the Tome AND is dodged by a Skeleton in its line (a named
    miss, nothing hit): exactly 2 lines, 'THE TOME SHUDDERS' then 'YOUR ARROW MISSES THE SKELETON'
    (the old `inc c` made act_fire's C = 1 a 2 and printed a 3rd, 'YOUR ARROW MISSES')."""
    k = S["K_SKELETON"]
    eva = S["kind_tab"] + S["KT_EVA"] + k
    e0 = p.rb(eva)
    p.wb(eva, 60)                                       # it always wins the roll (but a natural 20?)
    named = text6(TXT["cmb_arr_miss"] + " " + TXT["the"] + "SKELETON")
    got = None
    for seed in (0x1234, 0x4321, 0x7777, 0x0F0F):
        play_mode(p)
        L.at_gap(10)
        p.set_ent(0, HP=200)
        h = p.kb(k, "KT_BH")
        x = (3 + 4) if L.left else (26 - 4 - 1)            # 4 cols in front of the hero, in the line
        p.set_ent(1, KIND=k, ROOM=L.sn, X=x, Y=stand_y(1, h), PX=x * 8, PY=stand_y(1, h) * 8, HP=50, MAXHP=50,
                  MODE=0, REACT=0, FLAGS=EF_ACTIVE | EF_HOSTILE | (0 if L.left else EF_LEFT))
        p.wmem(S["RNG_STATE"], w16(seed))
        p.turn("@4")
        p.until(lambda: p.idle(), 300)
        p.until(lambda: p.rb("LOG_QN") == 0, 200)
        p.settle(2)
        fr = p.frame()
        got = (p.rb("TOME_HP"), log_row(fr, 22) == text6(TXT["tome_hit"]), log_row(fr, 23) == named, p.ent(1)["HP"])
        p.set_ent(1, FLAGS=0)
        if got[3] == 50:                                # the Skeleton dodged: the case happened
            break
    p.wb(eva, e0)
    check("H9 arrow strikes the Tome + a Skeleton dodges it: 2 lines only (TOME SHUDDERS, MISSES THE SKELETON)",
          got[0] == S["TOME_MAX"] - 1 and got[1] and got[2] and got[3] == 50, got)
    play_mode(p)


def aura(p, L):
    play_mode(p)
    for gap, facing, s_, want, tag in ((5, True, 1, 1, "gap 5, facing"), (0, False, 1, 1, "gap 0, facing away"),
                                       (6, True, 1, 0, "gap 6"), (2, True, 0, 0, "storey 0")):
        L.at_gap(gap, facing, s_)
        p.set_ent(0, HP=50)
        p.turn("WAIT")
        check(f"A aura {tag}: -{want} hp (untyped)", p.ent(0)["HP"] == 50 - want, p.ent(0)["HP"])
    L.at_gap(3)
    p.set_ent(0, HP=1)
    p.turn("WAIT")
    p.tick(3)
    check("A aura: the last hp -> GS_DEAD", p.rb("GAME_STATE") == GS_DEAD and p.ent(0)["HP"] == 0,
          (p.rb("GAME_STATE"), p.ent(0)["HP"]))


def revisit(p, L):
    play_mode(p)
    p.wb("TOME_HP", 3)
    # to the Sanctum's door, out to the lair and back in (real do_exit both ways)
    x = 2 if L.door_l else 30 - L.kw
    L.place(x, L.s, left=L.door_l)
    out, back = ("H", "L") if L.door_l else ("L", "H")
    for _ in range(6):
        if p.rb("CUR_ROOM") != L.sn:
            break
        p.turn(out)
    p.until(lambda: p.idle(), 600)
    left_ok = p.rb("CUR_ROOM") == L.lair
    for _ in range(6):
        if p.rb("CUR_ROOM") == L.sn:
            break
        p.turn(back)
    p.until(lambda: p.idle(), 600)
    p.settle(2)
    m = p.z.read_memory(S["ROOM_MAP"], 576)
    c0 = 1 if L.left else 29
    check("R out of the Sanctum and back: TOME_HP stays 3 (no regeneration), the lectern redrawn",
          left_ok and p.rb("CUR_ROOM") == L.sn and p.rb("TOME_HP") == 3 and m[15 * 32 + c0] == 15,
          (left_ok, p.rb("CUR_ROOM"), p.rb("TOME_HP"), m[15 * 32 + c0]))


def mage(p):
    L = D8(p, 0x5302, hero=1)
    p.clear_slots()
    L.put_hero(L.sn, 14, 1)
    p.wb("MP", 99)
    p.wb("MAXMP", 99)
    p.wmem(S["ARANK"], w16(1))                            # Spark r1 (range 6)
    five(L, "H7 Spark (Mage, range 6)", lambda: p.turn("@1"), 5)
    miss(L, "H7 Spark", lambda: p.turn("@1"), 6)
    five(L, "H8 staff (Mage melee FIRE)", lambda: p.turn("C"), 0)


def main():
    if not F3:
        print("[skip] sanctum needs the F3_GEN build", flush=True)
        return 0
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = Proto(h)
        items_absent(p)
        for master in (0x5302, 0x5300):                  # S = 6 / S = 8, the door on storey 1
            seal(p, master, mirror=True)
            L = seal(p, master, mirror=False)
            if L is None or p.rb("CUR_ROOM") != L.sn:
                continue
            revisit(p, L)
            warrior_hits(p, L)
            aura(p, L)
        mage(p)
    print(f"sanctum: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
