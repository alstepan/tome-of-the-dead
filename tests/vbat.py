#!/usr/bin/env python3
"""3F-T9 the Vampire's bat form (game.md §9.2; src/vbat6.asm + bank7.asm vb_turn). Seeded D6 (a
Vampire level without the Bat): bodies placed by hand, bank-7 vb_turn called through far7 with
TURN_COUNTER poked (the end_turn decision), plus real turns for the flee flight.

  P  pool: D6 generates the Bat's flapup / glide (K_VBAT, 2 frames, not the other 4), KT_SEQ of
     K_VBAT is a cached row of its own, SEQ_TRAP 0
  F  flee (rule 1): hp <= 1/3 max, the hero on its storey, odd turn -> K_VBAT, same x / top row,
     M_REST, RCD_ONCE | RCD_VFLEE, FEAR 8, LIVE_LIST box 3x2; even turn + FEAR on: stays; FEAR
     over: back to the Vampire standing, VFLEE cleared, once kept; once: never flees again;
     an even turn never turns a humanoid, an odd one never reverts a bat
  O  the hero on the other storey / the Vampire held (STUNNED): no change
  C  close distance (rule 2): gap 6, no cut: walks; a pit col in the floor row or a solid cell in
     the standing row between: bat; gap 11 with a pit: walks
  N  revert near: gap <= 2, no cut, even turn: Vampire; a cut between at gap 2: stays a bat;
     over a pit (illegal humanoid box): stays a bat, y kept; gap 3: stays
  G  the golden Lord: LP_BOSS follows its kind (K_VBAT | LEK_GOLD and back)
  R  real turns (WAIT): a low-hp Vampire beside the hero logs "THE VAMPIRE TURNS INTO A BAT!",
     flees (gap grows), reverts within 14 turns
  K  lp_bank: a bat form is banked as K_VBAT with its exact hp
  D  impact_line: the Vampire's bite hit reads "THE VAMPIRE DRAINS YOU", its bat form's "THE VAMPIRE HITS YOU"
  S  the transform turn on the top storey (real turns): the log rows' attrs unchanged, no body drawn
     outside the playfield (fix/vamp-corruption: the stale old-kind frame by the new KT_BH)
  T  costs: vb_turn (far7 incl.) with no candidate / a candidate staying / a transform
Build with -DDEBUG_KIT=0. ZRCP_PORT=<port> python3 tests/vbat.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, stand_y  # noqa: E402
from lp import T, w16  # noqa: E402
from boss import rec_entries  # noqa: E402
from abil_melee import stream_text  # noqa: E402
from spawn import (Lines, kt, heal, clear_room, mon, hero_at, level, far3, keep_pc, check,  # noqa: E402
                   fails, good_cols)

KV, KB = S["K_VAMPIRE"], S["K_VBAT"]
ONCE, VFLEE = 0x80, S["RCD_VFLEE"]
MIND_FEAR, STS_MIND = S["MIND_FEAR"], S["STS_MIND"]
GOLD = S["LEK_GOLD"]
ATTRS = 0x5800                                 # the bank-5 attribute file (hardware)


@keep_pc
def vb_turn(p, turn):
    """bank-7 vb_turn at TURN_COUNTER = turn (far7, interrupts on) -> (ok, T)."""
    p.wmem(S["TURN_COUNTER"], w16(turn))
    p.z.cmd("set-breakpoint 5")
    return p.code([0x21] + w16(S["vb_turn"]) + [0xCD] + w16(S["far7"]), game=True)


def build_live(p):
    keep_pc(lambda q: q.code([0xCD] + w16(S["build_live"]), game=True))(p)


def ll_box(p, sl):
    n = p.rb("LIVE_N")
    ll = p.z.read_memory(S["LIVE_LIST"], 5 * n)
    for i in range(n):
        if ll[5 * i] == sl:
            return ll[5 * i + 3], ll[5 * i + 4]
    return None


def fear(p, sl):
    return p.rb(S["ST_FLAGS"] + sl) & STS_MIND, p.rb(S["ST_T1"] + sl) & 15


def cell(p, row, col, tile=None):
    a = S["ROOM_MAP"] + row * 32 + col
    old = p.rb(a)
    if tile is not None:
        p.wb(a, tile)
    return old


def setup(p, s_, hx, vx, k=KV, hp=14, maxhp=14, pot=0):
    clear_room(p)
    hero_at(p, hx, s_)
    heal(p)
    mon(p, 1, k, vx, s_, hp=maxhp, pot=pot)
    p.set_ent(1, HP=hp)
    build_live(p)


def main():
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)
        lines = Lines(p)
        L, r = level(p, lines, 6, 0x7601, need=20)
        check("setup: D6 + a 20-col standable run", L is not None, r)
        if L:
            run(p, lines, r)
    print(f"vbat: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
    return 1 if fails else 0


def run(p, lines, r):
    s_, c0 = r
    vy = stand_y(s_, 6)
    # ------------------------------------------------------------------ P
    frt = lambda f: p.rb(S["FRT"] + 16 * f)
    gen = [frt(S["FID_bat_" + n]) != S["FRT_NONE"] for n in ("flapup", "glide", "flapdown", "dive", "hurt", "dead")]
    check("P1 D6 pool: bat flapup / glide generated, flapdown / dive / hurt / dead not", gen == [1, 1, 0, 0, 0, 0], gen)
    ksq = p.rb(S["kind_tab"] + S["KT_SEQ"] + KB)
    check("P2 KT_SEQ[K_VBAT] = a cached row of its own (not the hero's slot 0, not the Vampire's), SEQ_TRAP 0",
          ksq != p.rb(S["kind_tab"] + S["KT_SEQ"] + p.rb("HERO_KIND"))
          and ksq != p.rb(S["kind_tab"] + S["KT_SEQ"] + KV) and p.rb("SEQ_TRAP") == 0, ksq)
    # ------------------------------------------------------------------ F
    vx = c0 + 3
    setup(p, s_, c0, vx, hp=5)
    vb_turn(p, 2)
    check("F0 an even turn never turns a humanoid", p.ent(1)["KIND"] == KV, p.ent(1))
    ok, _ = vb_turn(p, 3)
    e = p.ent(1)
    check("F1 hp 5 of 14, odd turn: K_VBAT at the same x / top row, M_REST, px / py snapped",
          ok and e["KIND"] == KB and e["X"] == vx and e["Y"] == vy and e["MODE"] == 0
          and e["PX"] == vx * 8 and e["PY"] == vy * 8, e)
    check("F2 RCD_ONCE | RCD_VFLEE, FEAR 8 turns, LIVE_LIST box 3x2",
          e["POT"] & (ONCE | VFLEE) == ONCE | VFLEE and fear(p, 1) == (MIND_FEAR, S["VB_FLEE_T"])
          and ll_box(p, 1) == (3, 2), (e["POT"], fear(p, 1), ll_box(p, 1)))
    check("F2b the slot is hidden for the next render (R_VIS 0: RENDER_FIRST would place the old kind's "
          "frame by the new KT_BH)", p.rb(S["SLOTREC"] + 16 * 1 + S["R_VIS"]) == 0,
          p.rb(S["SLOTREC"] + 16 * 1 + S["R_VIS"]))
    vb_turn(p, 4)
    check("F3 even turn, FEAR on: stays a bat", p.ent(1)["KIND"] == KB, p.ent(1))
    p.wb(S["ST_FLAGS"] + 1, 0)
    p.wb(S["ST_T1"] + 1, 0)
    vb_turn(p, 5)
    check("F4 an odd turn never reverts a bat", p.ent(1)["KIND"] == KB, p.ent(1))
    vb_turn(p, 6)
    e = p.ent(1)
    check("F5 FEAR over, even turn: the Vampire standing again, VFLEE cleared, once kept, box 3x6",
          e["KIND"] == KV and e["Y"] == vy and e["POT"] & (ONCE | VFLEE) == ONCE and ll_box(p, 1) == (3, 6), e)
    p.set_ent(1, HP=3)
    vb_turn(p, 7)
    check("F6 once: hp 3, odd turn -> no second flight", p.ent(1)["KIND"] == KV, p.ent(1))
    # ------------------------------------------------------------------ O
    setup(p, s_ ^ 1, c0, vx, hp=4)
    hero_at(p, c0, s_)
    p.set_ent(1, Y=stand_y(s_ ^ 1, 6), PY=stand_y(s_ ^ 1, 6) * 8)
    build_live(p)
    vb_turn(p, 3)
    check("O1 the hero on the other storey: no change", p.ent(1)["KIND"] == KV, p.ent(1))
    setup(p, s_, c0, vx, hp=4)
    p.wb(S["ST_FLAGS"] + 1, S["HOLD_STUNNED"])
    p.wb(S["ST_T1"] + 1, 0x20)
    vb_turn(p, 3)
    check("O2 held (STUNNED): no change", p.ent(1)["KIND"] == KV, p.ent(1))
    # ------------------------------------------------------------------ C
    vx = c0 + 3 + 6                            # gap 6
    setup(p, s_, c0, vx)
    vb_turn(p, 3)
    check("C1 gap 6, no cut: walks", p.ent(1)["KIND"] == KV, p.ent(1))
    fr, sr = 9 * s_ + 8, 9 * s_ + 7
    old = cell(p, fr, c0 + 5, S["T_AIR"])
    vb_turn(p, 3)
    check("C2 a pit col in the floor row between: bat (no flee bits)",
          p.ent(1)["KIND"] == KB and p.ent(1)["POT"] & (ONCE | VFLEE) == 0, p.ent(1))
    cell(p, fr, c0 + 5, old)
    setup(p, s_, c0, vx)
    old = cell(p, sr, c0 + 6, S["T_BRICK"])
    vb_turn(p, 3)
    check("C3 a solid cell in the standing row between: bat", p.ent(1)["KIND"] == KB, p.ent(1))
    cell(p, sr, c0 + 6, old)
    setup(p, s_, c0, c0 + 3 + 11)
    old = cell(p, fr, c0 + 5, S["T_AIR"])
    vb_turn(p, 3)
    check("C4 gap 11 with a pit: walks", p.ent(1)["KIND"] == KV, p.ent(1))
    # ------------------------------------------------------------------ N
    by = 9 * s_ + 1
    setup(p, s_, c0, c0 + 3 + 2, k=KB)
    vb_turn(p, 4)
    check("N1 gap 2 with a pit between: stays a bat", p.ent(1)["KIND"] == KB, p.ent(1))
    cell(p, fr, c0 + 5, old)
    setup(p, s_, c0, c0 + 3 + 3, k=KB)
    vb_turn(p, 4)
    check("N2 gap 3: stays a bat", p.ent(1)["KIND"] == KB, p.ent(1))
    setup(p, s_, c0, c0 + 3 + 2, k=KB)
    vb_turn(p, 4)
    e = p.ent(1)
    check("N3 gap 2, no cut, even turn: the Vampire, standing", e["KIND"] == KV and e["Y"] == vy, e)
    setup(p, s_, c0, c0 + 4, k=KB)
    olds = [cell(p, fr, c, S["T_AIR"]) for c in range(c0 + 4, c0 + 7)]
    vb_turn(p, 4)
    e = p.ent(1)
    check("N4 over a pit (illegal humanoid box): stays a bat, y kept", e["KIND"] == KB and e["Y"] == by, e)
    for c, t in zip(range(c0 + 4, c0 + 7), olds):
        cell(p, fr, c, t)
    # ------------------------------------------------------------------ G
    lpb = p.rb("LP_BOSS")
    setup(p, s_, c0, c0 + 3, hp=5, maxhp=38)
    p.wb(S["P_ENTITIES"] + 32 + S["E_GOLD"], GOLD)
    p.wb("LP_BOSS", KV | GOLD)
    vb_turn(p, 3)
    g1 = p.rb("LP_BOSS")
    p.wb(S["ST_FLAGS"] + 1, 0)
    p.wb(S["ST_T1"] + 1, 0)
    vb_turn(p, 4)
    g2 = p.rb("LP_BOSS")
    check("G1 golden Lord: LP_BOSS = K_VBAT | LEK_GOLD as a bat, K_VAMPIRE | LEK_GOLD again after",
          g1 == KB | GOLD and g2 == KV | GOLD and p.ent(1)["KIND"] == KV, (g1, g2, p.ent(1)))
    p.wb("LP_BOSS", lpb)
    # ------------------------------------------------------------------ K
    setup(p, s_, c0, c0 + 3, k=KB, hp=7)
    room = p.rb("CUR_ROOM")
    far3(p, "lp_bank", a=room, e=0)
    ents, _ = rec_entries(p, room)
    check("K1 lp_bank: the bat form banked as K_VBAT with its hp", [(k_ & 0x1F, hp) for k_, hp in ents] == [(KB, 7)], ents)
    # ------------------------------------------------------------------ D
    got = []
    for k in (KV, KB):
        keep_pc(lambda q: q.code([0x06, S["MSG_M_HIT"], 0x0E, k, 0xCD] + w16(S["impact_line"]), game=True))(p)
        got.append(stream_text(p.z.read_memory(S["MSG_BUF"], 32)).rstrip("."))
    check("D1 the bite hit: 'THE VAMPIRE DRAINS YOU' (humanoid) / 'THE VAMPIRE HITS YOU' (bat form)",
          got == ["THE VAMPIRE DRAINS YOU", "THE VAMPIRE HITS YOU"], got)
    # ------------------------------------------------------------------ T
    clear_room(p)
    hero_at(p, c0, s_)
    build_live(p)
    _, t0 = vb_turn(p, 3)
    setup(p, s_, c0, c0 + 3 + 6)
    _, t1 = vb_turn(p, 3)
    setup(p, s_, c0, c0 + 3, hp=4)
    _, t2 = vb_turn(p, 3)
    print(f"[info] vb_turn T-states (far7 incl.): none {t0}, a Vampire staying {t1}, a flee transform {t2}", flush=True)
    check("T vb_turn <= 2.5k T without a candidate, <= 6k staying, <= 12k a transform (end_turn tick)",
          t0 <= 2500 and t1 <= 6000 and t2 <= 12000, (t0, t1, t2))
    # ------------------------------------------------------------------ R
    lines.arm()
    vx = c0 + 6
    setup(p, s_, c0 + 3, vx, hp=4)
    lines.lines.clear()
    turned = flew = back = None
    gap0 = vx - (c0 + 6)
    for t in range(1, 21):
        heal(p)
        if turned is None:
            p.set_ent(1, HP=4)                 # (its drain bite would heal it past 1/3)
        p.turn("WAIT")
        e = p.ent(1)
        if turned is None and e["KIND"] == KB:
            turned = t
        if turned and e["X"] - (c0 + 6) > gap0 + 2:
            flew = flew or t
        if turned and e["KIND"] == KV:
            back = t
            break
    check(f"R1 'THE VAMPIRE TURNS INTO A BAT!' within 2 turns (turn {turned})",
          turned is not None and turned <= 2 and "THE VAMPIRE TURNS INTO A BAT!" in lines.lines, (turned, lines.lines))
    check(f"R2 it flees (gap > 2 by turn {flew}) and reverts within 14 turns (turn {back})",
          flew is not None and back is not None and back - turned <= 14, (flew, back, p.ent(1)))
    p.z.cmd("set-breakpoint 5")
    screen_safe(p)


def screen_safe(p):
    """S (fix/vamp-corruption, user playtest D3): the transform turn on the TOP storey through real
    turns. Before the fix the next RENDER_FIRST render placed the Vampire's 48-px frame by the bat's
    2-row KT_BH: fpy = 16 + 16 - 48 = -16 -> R_ROW 30 -> blit / erase into the attributes (log rows
    22 / 23 at the body's cols) and the bank-5 RAM above them. The log rows' attrs must not change,
    and no body may ever be drawn outside the playfield rows."""
    ok = [c for c in range(2, 20) if all(good_cols(p, 0)[c:c + 3])]
    run0 = next((c for c in ok if c + 6 in ok), None)
    check("S0 a top-storey spot for the hero + a Vampire beside it", run0 is not None, ok)
    if run0 is None:
        return
    setup(p, 0, run0, run0 + 3, hp=4)
    log_attr = lambda: p.z.read_memory(ATTRS + 22 * 32, 64)
    a0 = log_attr()
    turned, bad_row, diffs = None, None, []
    for t in range(1, 5):
        heal(p)
        if turned is None:
            p.set_ent(1, HP=4)
        p.turn("WAIT")
        e = p.ent(1)
        if e["DVIS"] & 1 and e["DROW"] + e["DROWS"] > 18:
            bad_row = (t, e["DROW"], e["DROWS"])
        a1 = log_attr()
        diffs += [(t, 22 + i // 32, i % 32, a1[i]) for i in range(64) if a1[i] != a0[i]]
        if e["KIND"] == KB:
            turned = t
            break
    check(f"S1 top storey: the Vampire turns into a bat (turn {turned}), log-row attrs unchanged, drawn "
          "rows inside the playfield", turned is not None and not diffs and bad_row is None,
          (turned, diffs[:6], bad_row))


if __name__ == "__main__":
    sys.exit(main())
