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
      per hit, the 5th (WIN2, user 2026-11-01) -> NOT GS_WIN: "THE TOME IS DESTROYED" + "A GATE
      GLEAMS, THE WAY DOWN", LF_GRATE_OPEN, the run goes on; out of range / facing away: no hit
      (Power Strike refused: no turn, no MP)
  A   the aura: gap 5 -> -1 hp a turn (either facing), gap 6 / storey 0 -> none; HP 1 -> GS_DEAD
  R   leaving the Sanctum and coming back keeps TOME_HP (no regeneration), the lectern redrawn
  W1  the destroyed Tome: a bump = a wall (no turn, no line), no aura, a dagger strikes nothing (never twice)
  W2  the 5th hit with a Skeleton alive in the Sanctum: the gate opens anyway, the Skeleton stays
  W3  the 5th hit at HP 1: the Tome's aura is gone with it, the hero lives, the gate opens
  W4  before the Tome: DOWN on the lair's shut D8 grate = no turn
  W5  the aura kills on a non-final hit (TOME_HP 2 -> 1, HP 1): GS_DEAD, the gate stays shut
  FX  TOME-FX (user 2026-11-03): every hit flashes the 2x2 lectern ATTR_TOME_FLASH for the turn (TILE_ATTRS
      and the displayed attrs; the glyphs stay), end_turn restores it before the death check (W5 dies
      unflashed); the last hit leaves the ASH attr (4 cells) which persists across leave / re-enter and
      into the end card; a new level restores the book / stand attrs; SFX_HIT per hit, SFX_KILL on the last
  FX7 TOME-FX2 (user 2026-11-03): the flash is exactly 2 ticks on the displayed screen for EVERY attack (bump, FIRE,
      Power Strike, dagger, arrow, staff, Spark, Firebolt), the border (TOME_BORDER 1) white / yellow (last hit) for the
      same 2 ticks then black, never touched with TOME_BORDER 0; FX8 a white border is blacked by the bag, the pause,
      a room exit and the death card (TOME_BORDER 1)
  W6  after the Tome: the hero walks out into the lair (real do_exit): the grate T_GRATE x 3 (opened
      off-screen), ROOM_MAP == room_model; re-entry (room_show) keeps it; DOWN at c with HP 1 ->
      GS_WIN, depth stays 8, the last line "YOU WIN!" 
ZRCP_PORT=<port> python3 tests/sanctum.py
"""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import levelgen as G  # noqa: E402
import items_model as M  # noqa: E402
import room_model  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, stand_y, F3  # noqa: E402
from lp import T as Proto, w16  # noqa: E402
from world import log_row, text6, STRINGS, map_structure, menu_text_ok  # noqa: E402

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


LATTR = S["TILE_ATTRS"] + S["T_LECT_TL"]
A_TOP, A_FOOT, A_FLASH, A_ASH = (S["ATTR_LECT_TOP"], S["ATTR_LECT_FOOT"], S["ATTR_TOME_FLASH"],
                                 S["ATTR_TOME_ASH"])
NORM = [A_TOP, A_TOP, A_FOOT, A_FOOT]


def lect_attrs(p):
    return list(p.z.read_memory(LATTR, 4))


def lect_norm(p):
    p.wmem(LATTR, NORM)


def shown(fr, left, row0=15, col0=None):
    """The displayed attrs of the 2x2 lectern (TL TR BL BR) from a frame."""
    c0 = col0 if col0 is not None else (1 if left else 29)
    return [fr[6144 + row0 * 32 + c0], fr[6144 + row0 * 32 + c0 + 1],
            fr[6144 + (row0 + 1) * 32 + c0], fr[6144 + (row0 + 1) * 32 + c0 + 1]]


def border(p):
    """The last value written to port $FE (ZRCP get-io-ports "Spectrum FE port"): bits 0-2 = the border."""
    m = re.search(r"Spectrum FE port:\s*([0-9A-Fa-f]+)", p.z.cmd("get-io-ports"))
    return int(m.group(1), 16)


def border_set(L, v):
    L.ingame([0x3E, v, 0xD3, 0xFE])                        # ld a, v / out ($FE), a (bits 3 / 4 = 0: no beeper)


def play_mode(p):
    p.wb("GAME_STATE", GS_PLAYING)
    p.wb("TOME_HP", S["TOME_MAX"])
    p.wb("LVL_FLAGS", p.rb("LVL_FLAGS") & ~S["LF_GRATE_OPEN"] & 0xFF)


def gone_ok(L):
    """After the 5th hit: TOME_HP 0, LF_GRATE_OPEN, still GS_PLAYING, the 2 lines."""
    p = L.p
    L.last_line()
    fr = p.frame()
    return (p.rb("TOME_HP") == 0 and p.rb("LVL_FLAGS") & S["LF_GRATE_OPEN"] and p.rb("GAME_STATE") == GS_PLAYING
            and log_row(fr, 22) == text6(TXT["win"]) and log_row(fr, 23) == text6(TXT["gate_gleams"]))


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
    # LOOK-1 / FLAME-RATE: animated decor cells hold either flame glyph (world.map_structure
    # compares them as the pair {map id, AL_TYPE}, as world.py W0 / W3 since 9c8a16b)
    ms = map_structure(p, L.sn)
    check(f"L S {L.sn}: the lectern 15-18 at cols {c0}-{c0 + 1} rows 15-16; ROOM_MAP == room_model",
          lect == [15, 16, 17, 18] and not ms, (lect, ms[:4]))
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
            tl = TXT["tome_hit"] + " -1 HP %d" % p.rb("TOME_HP")    # LOG-DMG: msg_push_t
            check(f"{tag}: '{tl}'", L.last_line() == text6(tl), "")
        if p.rb("GAME_STATE") != GS_PLAYING:
            break
    check(f"{tag}: 5 hits at gap {gap} destroy the Tome: TOME_HP 0, the gate opens, still GS_PLAYING, "
          f"'{TXT['win']}' + '{TXT['gate_gleams']}'",
          seen == [1] * 5 and gone_ok(L), (seen, p.rb("TOME_HP"), p.rb("GAME_STATE"), p.rb("LVL_FLAGS")))
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
        tl = TXT["tome_hit"] + " -1 HP %d" % p.rb("TOME_HP")        # LOG-DMG: msg_push_t
        got = (p.rb("TOME_HP"), log_row(fr, 22) == text6(tl), log_row(fr, 23) == named, p.ent(1)["HP"])
        p.set_ent(1, FLAGS=0)
        if got[3] == 50:                                # the Skeleton dodged: the case happened
            break
    p.wb(eva, e0)
    check("H9 arrow strikes the Tome + a Skeleton dodges it: 2 lines only (TOME SHUDDERS, MISSES THE SKELETON)",
          got[0] == S["TOME_MAX"] - 1 and got[1] and got[2] and got[3] == 50, got)
    play_mode(p)


def fx_hit(p, L, key, hp):
    """TOME_HP hp -> hp-1 by a real bump turn: the 2x2 flashes during the turn (TILE_ATTRS and the screen),
    and is back (norm, or ash after the last hit) when the turn is idle. Returns the tick samples."""
    play_mode(p)
    p.wb("TOME_HP", hp)
    L.at_gap(0)
    p.set_ent(0, HP=200)
    smp = []
    p.turn(key, per_tick=lambda fr, hero: smp.append((lect_attrs(p), shown(fr, L.left), p.rb("TILE_ATTRS"))))
    p.until(lambda: p.idle(), 300)
    for _ in range(5):                                     # the INPUT ticks after it: lect_back, then present
        smp.append((lect_attrs(p), shown(p.frame(), L.left), p.rb("TILE_ATTRS")))
        p.tick()
    return smp


def fx_tests(p, L, key):
    """FX1-FX4: the flash, the restore, the ash, its persistence (room re-entry), the sound."""
    check("FX0 the lectern attrs: book / stand / flash / ash all distinct as needed (flash != foot, ash != foot, "
          "flash != ash), boot TILE_ATTRS == the constants",
          A_FLASH != A_FOOT and A_ASH != A_FOOT and A_FLASH != A_ASH and A_FLASH != A_TOP and A_ASH != A_TOP,
          (A_TOP, A_FOOT, A_FLASH, A_ASH))
    lect_norm(p)
    smp = fx_hit(p, L, key, 2)                             # a non-final hit
    glyph = list(p.z.read_memory(S["ROOM_MAP"] + 15 * 32 + (1 if L.left else 29), 1)) == [15]
    check("FX1 a hit: the 2x2 shows the flash attr on a tick of the hit turn (TILE_ATTRS and displayed), "
          "TOME_HP 1, glyph unchanged",
          any(t == [A_FLASH] * 4 for t, _, _ in smp) and any(sh == [A_FLASH] * 4 for _, sh, _ in smp)
          and p.rb("TOME_HP") == 1 and glyph, ([(t, sh) for t, sh, _ in smp][:6], p.rb("TOME_HP")))
    fr = p.frame()
    check("FX1 end_turn restores the book / stand attrs (TILE_ATTRS and displayed)",
          lect_attrs(p) == NORM and shown(fr, L.left) == NORM, (lect_attrs(p), shown(fr, L.left)))
    tl = TXT["tome_hit"] + " -1 HP 1"
    check(f"FX1 the line '{tl}'", L.last_line() == text6(tl), "")
    smp = fx_hit(p, L, key, 1)                             # the last hit
    fr = p.frame()
    ok_flash = any(t == [A_FLASH] * 4 for t, _, _ in smp) and any(sh == [A_FLASH] * 4 for _, sh, _ in smp)
    check("FX2 the last hit: flash during the turn, then ASH x 4 (TILE_ATTRS and displayed), glyph unchanged, "
          "'THE TOME IS DESTROYED' / 'A GATE GLEAMS' in order",
          ok_flash and lect_attrs(p) == [A_ASH] * 4 and shown(fr, L.left) == [A_ASH] * 4 and gone_ok(L),
          (ok_flash, lect_attrs(p), shown(fr, L.left)))
    # persistence: out of the Sanctum and back (room_show redraws from TILE_ATTRS), the map as room_model
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
    p.settle(3)
    fr = p.frame()
    ms = map_structure(p, L.sn)
    check("FX3 the ash persists across leaving / re-entering the Sanctum (TILE_ATTRS and displayed), "
          "ROOM_MAP == room_model, TOME_HP 0",
          left_ok and p.rb("CUR_ROOM") == L.sn and lect_attrs(p) == [A_ASH] * 4
          and shown(fr, L.left) == [A_ASH] * 4 and not ms and p.rb("TOME_HP") == 0,
          (left_ok, lect_attrs(p), shown(fr, L.left), ms[:3]))
    # the sounds: tome_strike called directly (no ISR consumes SFX_REQ under the stub)
    p.wb("SND_MODE", (p.rb("SND_MODE") | S["SND_SFX"]) & ~S["SND_HOLD"] & 0xFF)
    got = []
    play_mode(p)
    lect_norm(p)
    p.wb("TOME_HP", 2)
    L.at_gap(0)
    for _ in range(2):
        p.wb("SFX_REQ", 0)
        p.wb("SFX_NEXT", 0)
        L.ingame([0x21] + w16(S["tome_strike"]) + [0xCD] + w16(S["far7"]))
        got.append((p.rb("SFX_REQ"), p.rb("TOME_HP"), lect_attrs(p) == [A_FLASH] * 4))
    check("FX4 SFX_HIT on a hit, SFX_KILL on the last, the flash painted by tome_strike itself",
          got == [(S["SFX_HIT"], 1, True), (S["SFX_KILL"], 0, True)], got)
    p.wb("SFX_REQ", 0)
    p.wb("SFX_NEXT", 0)
    L.ingame([0x21] + w16(S["lect_back"]) + [0xCD] + w16(S["far7"]))
    p.settle(3)
    check("FX4 lect_back (end_turn): TOME_HP 0 -> ASH, a flash only (no flash: no repaint, attrs kept)",
          lect_attrs(p) == [A_ASH] * 4, lect_attrs(p))
    lect_norm(p)
    L.ingame([0x21] + w16(S["lect_back"]) + [0xCD] + w16(S["far7"]))
    check("FX4 lect_back with no flash: nothing changes (the book is not repainted)", lect_attrs(p) == NORM,
          lect_attrs(p))
    play_mode(p)
    lect_norm(p)
    p.wb("TOME_HP", S["TOME_MAX"])
    if not S.get("TOME_FX2", 0):                         # (a kit build keeps the TOME-FX timing: no hook)
        return
    fx_timing(p, L, [("melee bump", (key,), 0, False), ("melee FIRE", ("C",), 0, False), ("Power Strike", ("@1",), 0, True),
                     ("Whirlwind", ("@2",), 0, True), ("dagger", ("@3",), 5, False), ("arrow", ("@4",), 13, False)], "Warrior")
    if BORDER_ON:                                        # (TOME_BORDER 1; a -D define is not in the .sym)
        fx_modal(p, L)


def fx_timing(p, L, cases, tag):
    """FX7 (TOME-FX2, user 2026-11-03): the lectern flash lasts exactly 2 ticks for EVERY attack (cases = [(label,
    keys, gap, swing_fx)]) -- a spell's long projectile turn no longer holds it. Samples, one per tick (TOME_FL,
    TILE_ATTRS BL, displayed BL attr, port $FE & 7), from the turn's start to 6 ticks after it is idle; ref = the
    first sample with TOME_FL != 0 (the strike's tick, after dn_tm's first count). Expected: TILE_ATTRS flash on
    [ref, ref + 1] (restored when dn_tm queues it), the displayed flash on [ref + 2, ref + 3] (paint and restore
    each reach the screen 2 ticks after they are queued; skipped for a swing_fx attack: Power Strike / Whirlwind
    draw their own white swing over the cells), the border (TOME_BORDER 1: white, yellow on the last hit) on
    [ref + 1, ref + 2] (written at the end of the tick before the one that presents the flash) then black;
    TOME_BORDER 0 never touches it. The last hit leaves the ASH attrs, TOME_FL 0."""
    border_on = BORDER_ON
    for label, keys, gap, swing in cases:
        for hp, col in ((3, S["BORDER_TOME"]), (1, S["BORDER_TOME_END"])):
            play_mode(p)
            lect_norm(p)
            border_set(L, 0)
            p.wb("TOME_HP", hp)
            L.at_gap(gap)
            p.set_ent(0, HP=200)
            smp = []

            def snap(fr, hero):
                smp.append((p.rb("TOME_FL"), lect_attrs(p)[2], shown(fr, L.left)[2], border(p) & 7))
            p.turn(*keys, per_tick=snap)
            p.until(lambda: p.idle(), 300)
            for _ in range(6):
                smp.append((p.rb("TOME_FL"), lect_attrs(p)[2], shown(p.frame(), L.left)[2], border(p) & 7))
                p.tick()
            ref = next((i for i, x in enumerate(smp) if x[0]), -9)
            tile = [i for i, x in enumerate(smp) if x[1] == A_FLASH]
            shw = [i for i, x in enumerate(smp) if x[2] == A_FLASH]
            bd = [i for i, x in enumerate(smp) if x[3] != 0]
            rest = A_ASH if hp == 1 else A_FOOT
            ok = tile == [ref, ref + 1] and (swing or shw == [ref + 2, ref + 3]) and smp[-1][1] == rest
            ok = ok and p.rb("TOME_HP") == hp - 1 and p.rb("TOME_FL") == 0
            if border_on:
                ok = ok and bd == [ref + 1, ref + 2] and all(smp[i][3] == col for i in bd) and smp[-1][3] == 0
            else:
                ok = ok and not bd and border(p) & 7 == 0
            check(f"FX7 {tag} {label} (TOME_HP {hp} -> {hp - 1}): flash = 2 ticks (tile attrs"
                  + ("" if swing else " + displayed") + ")"
                  + (f", border {col} on the same 2 ticks, then black" if border_on else ", border untouched")
                  + (", ash after" if hp == 1 else ", book / stand after") + ", TOME_FL 0",
                  ok, (ref, tile, shw, bd, smp[:12]))
    play_mode(p)
    lect_norm(p)


def fx_modal(p, L):
    """FX8 (TOME_BORDER 1): the border is never left changed by a modal screen or the death card: with the hook idle
    (TOME_FL 0: nothing else would black it) a white border is cleared by the bag page, the pause overlay, the
    room exit (transition scroll) and the end card; MIC / EAR stay 0."""
    play_mode(p)
    lect_norm(p)
    L.at_gap(3)
    p.set_ent(0, HP=200)
    p.wb("TOME_FL", 0)
    border_set(L, BORDER_W)
    p.tap("I")
    opened = p.rb("PAGE_OPEN") == 1
    b_bag = border(p)
    p.tap("I")
    p.tick(3)
    check("FX8 the bag page blacks a Tome-hit border (and it stays black)", opened and b_bag == 0 and border(p) == 0,
          (opened, b_bag, border(p)))
    border_set(L, BORDER_W)
    p.hold("SPACE")
    p.tick()
    p.hold("SPACE", "Q")
    p.tick()
    p.hold()
    p.tick(2)
    paused, b_pause = p.rb("PAUSED") == 1, border(p)
    p.tap("SPACE")                                         # RESUME
    p.tick(2)
    check("FX8 the pause overlay blacks a Tome-hit border", paused and b_pause == 0, (paused, b_pause))
    play_mode(p)
    x = 2 if L.door_l else 30 - L.kw
    L.place(x, L.s, left=L.door_l)
    border_set(L, BORDER_W)
    out = "H" if L.door_l else "L"
    for _ in range(6):
        if p.rb("CUR_ROOM") != L.sn:
            break
        p.turn(out)
    p.until(lambda: p.idle(), 600)
    check("FX8 a room exit (transition scroll) blacks a Tome-hit border",
          p.rb("CUR_ROOM") == L.lair and border(p) == 0, (p.rb("CUR_ROOM"), border(p)))
    L.put_hero(L.sn, 14, 1)                                # back in the Sanctum for the next suites
    play_mode(p)


def fx_death(p, L):
    """FX8 (TOME_BORDER 1), last in the run: the death's end card blacks a Tome-hit border (the card draws over the
    room, so nothing after it may rely on the screen)."""
    L.put_hero(L.sn, 14, 1)
    play_mode(p)
    L.at_gap(3)
    p.set_ent(0, HP=1)
    p.wb("END_SHOWN", 0)                                   # (an earlier GS_DEAD leaves it set: no card then)
    border_set(L, BORDER_W)
    p.turn("WAIT")                                         # the aura kills: GS_DEAD, the end card
    p.end_card(12)                                         # (END-WAIT: the card waits for a key)
    check("FX8 death (the end card) blacks a Tome-hit border",
          p.rb("GAME_STATE") == GS_DEAD and border(p) == 0, (p.rb("GAME_STATE"), border(p)))


BORDER_W = S["BORDER_TOME"]
BORDER_ON = S["TOME_FL_N"] == 4


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


def gate(p, L, key):
    """W1-W4: the destroyed Tome, a live summon, the last hit at HP 1, the shut grate before."""
    play_mode(p)
    p.wb("TOME_HP", 1)
    L.at_gap(0)
    p.set_ent(0, HP=200)
    p.turn(key)
    p.until(lambda: p.idle(), 300)
    check("W1 setup: the last bump destroys the Tome", gone_ok(L), (p.rb("TOME_HP"), p.rb("LVL_FLAGS")))
    q0 = p.rb("LOG_QN")
    nt = p.no_turn(key)
    check("W1 the destroyed Tome: a bump = a wall (no turn, no line, TOME_HP 0)",
          nt and p.rb("TOME_HP") == 0 and p.rb("LOG_QN") == q0 and L.last_line() == text6(TXT["gate_gleams"]),
          (nt, p.rb("TOME_HP")))
    p.set_ent(0, HP=50)
    p.wb("HP_RG", 0)                                    # no FED regen on these turns (12 turns away)
    p.turn("WAIT")
    check("W1 the destroyed Tome: no aura (gap 0, a WAIT: HP 50)", p.ent(0)["HP"] == 50 and p.rb("TOME_HP") == 0,
          p.ent(0)["HP"])
    L.at_gap(5)
    p.turn("@3")
    p.until(lambda: p.idle(), 300)
    check("W1 the destroyed Tome: a dagger at gap 5 strikes nothing (TOME_HP 0, no SHUDDERS), never twice",
          p.rb("TOME_HP") == 0 and L.last_line() != text6(TXT["tome_hit"]) and p.rb("GAME_STATE") == GS_PLAYING,
          p.rb("TOME_HP"))
    # W2: a Skeleton alive in the Sanctum (out of reach), the 5th hit
    play_mode(p)
    p.wb("TOME_HP", 1)
    L.at_gap(0)
    k = S["K_SKELETON"]
    h = p.kb(k, "KT_BH")
    x = 20 if L.left else 8
    p.set_ent(1, KIND=k, ROOM=L.sn, X=x, Y=stand_y(0, h), PX=x * 8, PY=stand_y(0, h) * 8, HP=50, MAXHP=50,
              MODE=0, REACT=0, FLAGS=EF_ACTIVE | EF_HOSTILE)
    p.set_ent(0, HP=200)
    p.turn(key)
    p.until(lambda: p.idle(), 300)
    check("W2 the 5th hit with a Skeleton alive: the gate opens anyway, the Skeleton stays",
          gone_ok(L) and p.ent(1)["FLAGS"] & EF_ACTIVE and p.ent(1)["HP"] == 50, (p.rb("LVL_FLAGS"), p.ent(1)))
    p.set_ent(1, FLAGS=0)
    # W3: the 5th hit at HP 1: the aura goes with the Tome
    play_mode(p)
    p.wb("TOME_HP", 1)
    L.at_gap(0)
    p.set_ent(0, HP=1)
    p.wb("HP_RG", 0)
    p.turn(key)
    p.until(lambda: p.idle(), 300)
    p.tick(3)
    check("W3 the 5th hit at HP 1: no aura on that turn end, the hero lives (HP 1, GS_PLAYING), the gate opens",
          gone_ok(L) and p.ent(0)["HP"] == 1, (p.rb("GAME_STATE"), p.ent(0)["HP"]))
    # W4: before the Tome, DOWN on the lair's shut grate
    play_mode(p)
    c = room_model.field(L.blk, L.lair, "RD_EXITCOL")
    L.put_hero(L.lair, c, 1)
    nt = p.no_turn("J")
    check(f"W4 before the Tome: DOWN at c {c} on the shut D8 grate = no turn, depth 8",
          c and nt and p.rb("LVL_DEPTH") == 8 and p.rb("GAME_STATE") == GS_PLAYING, (c, nt))
    L.put_hero(L.sn, 14, 1)


def aura_hit_death(p, L, key):
    """W5: the aura kills on a non-final hit: GS_DEAD, the gate stays shut."""
    play_mode(p)
    p.wb("TOME_HP", 2)
    L.at_gap(0)
    p.set_ent(0, HP=1)
    p.turn(key)
    p.until(lambda: p.idle(), 300)
    p.tick(3)
    check("W5 the aura kills on the 4th hit (TOME_HP 1, HP 0): GS_DEAD, LF_GRATE_OPEN clear",
          p.rb("GAME_STATE") == GS_DEAD and p.rb("TOME_HP") == 1 and not p.rb("LVL_FLAGS") & S["LF_GRATE_OPEN"],
          (p.rb("GAME_STATE"), p.rb("TOME_HP"), p.rb("LVL_FLAGS")))
    check("W5 TOME-FX: the flash was restored before the death check (a lethal turn ends unflashed)",
          lect_attrs(p) == NORM, lect_attrs(p))


def exit_win(p, L, key):
    """W6: the gate opened off-screen; the hero walks out into the lair and leaves through it."""
    play_mode(p)
    p.wb("TOME_HP", 1)
    L.at_gap(0)
    p.set_ent(0, HP=200)
    p.turn(key)
    p.until(lambda: p.idle(), 300)
    check("W6 setup: the Tome destroyed in the Sanctum", gone_ok(L), p.rb("LVL_FLAGS"))
    x = 2 if L.door_l else 30 - L.kw
    L.place(x, L.s, left=L.door_l)
    out = "H" if L.door_l else "L"
    for _ in range(6):
        if p.rb("CUR_ROOM") != L.sn:
            break
        p.turn(out)
    p.until(lambda: p.idle(), 600)
    p.settle(2)
    c = room_model.field(L.blk, L.lair, "RD_EXITCOL")
    F1 = S["FLOOR_ROW1"]
    for tag in ("walked in (do_exit)", "re-entered (room_show)"):
        if tag[0] == "r":
            L.put_hero(L.lair, 14, 1)
        m = list(p.z.read_memory(S["ROOM_MAP"], 576))
        ms = map_structure(p, L.lair)               # (animated decor as the pair: see L above)
        check(f"W6 the lair {tag}: the gate open off-screen (T_GRATE x 3 at c {c}), ROOM_MAP == room_model",
              p.rb("CUR_ROOM") == L.lair and all(m[F1 * 32 + c + k] == S["T_GRATE"] for k in range(3))
              and not ms, (p.rb("CUR_ROOM"), m[F1 * 32 + c:F1 * 32 + c + 3], ms[:4]))
    L.place(c, 1, left=False)
    p.set_ent(0, HP=1)
    p.wb("END_SHOWN", 0)    # ENDCARD-G1: an earlier GS_DEAD (A / W5, revived by play_mode) left it set; a real
                            # run's new_game clears it, else GS_WIN skips the card (end_screen draws it once)
    p.turn("J")
    p.until(lambda: p.idle(), 900)
    p.until(lambda: p.rb("LOG_QN") == 0, 200)
    p.settle(2)
    p.end_card()                                           # END-WAIT: the card waits for a key
    p.settle(2)
    # ENDCARD-G1 (30dc3b1): GS_WIN shows the full-screen end card (no panel / log row 23 any more):
    # its title "YOU WIN!" (menu font, row EC_TROW, col 12) replaces the old last-log-line check
    fr = p.frame()
    ec = shown(fr, False, row0=S["EC_FEET"] - 2, col0=S["EC_PCOL_L"] + 3)
    check("W6 TOME-FX: the win end card draws the destroyed lectern in the ASH attr (TILE_ATTRS persists)",
          ec == [A_ASH] * 4 and p.rb("GAME_STATE") == GS_WIN, (ec, lect_attrs(p)))
    check("W6 DOWN at c with HP 1: GS_WIN, depth stays 8, the end card 'YOU WIN!'",
          p.rb("GAME_STATE") == GS_WIN and p.rb("LVL_DEPTH") == 8
          and menu_text_ok(p, p.frame(), S["EC_TROW"], 12, "YOU WIN!"),
          (p.rb("GAME_STATE"), p.rb("LVL_DEPTH"), p.rb("END_SHOWN")))


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
    p.wmem(S["ARANK"], w16(1 | 1 << 2))                   # Spark r1, Firebolt r1
    if S.get("TOME_FX2", 0):
        fx_timing(p, L, [("staff FIRE", ("C",), 0, False), ("Spark", ("@1",), 5, False),
                         ("Firebolt", ("@2",), 5, False)], "Mage")


def offd8(p):
    """FX6: TOME_HP is 0 off D8: end_turn's lect_back never repaints / rewrites the lectern attrs (a depth-1
    game: a few turns, the attrs stay as loaded; never ash)."""
    p.proto_start = 0
    p.boot(hero=0, freeze=1)
    p.release()
    p.settle(4)
    lect_norm(p)
    for _ in range(3):
        p.turn("WAIT")
    check("FX6 off D8 (TOME_HP 0): 3 turns leave the lectern attrs untouched", p.rb("TOME_HP") == 0
          and p.rb("LVL_DEPTH") == 1 and lect_attrs(p) == NORM, (p.rb("TOME_HP"), p.rb("LVL_DEPTH"), lect_attrs(p)))


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
            check(f"FX5 master {master:#06x}: a NEW D8 starts with the book / stand attrs (a previous game's ash "
                  "is reset by level_tiles7's tail)", lect_attrs(p) == NORM, lect_attrs(p))
            L = seal(p, master, mirror=False)
            if L is None or p.rb("CUR_ROOM") != L.sn:
                continue
            revisit(p, L)
            key = warrior_hits(p, L)
            aura(p, L)                                  # (first: its storey-0 case sees no FED regen turn)
            gate(p, L, key)
            aura_hit_death(p, L, key)
            if S.get("TOME_FX", 1):                     # (0 only in a trace test build: no FX there)
                fx_tests(p, L, key)
            exit_win(p, L, key)
            if S.get("TOME_FX2", 0) and BORDER_ON:
                fx_death(p, L)
        mage(p)
        offd8(p)
    print(f"sanctum: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
