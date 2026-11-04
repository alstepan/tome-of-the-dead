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
  C  close distance (rule 2): gap < VB_FAR (6), no cut: walks; a pit col in the floor row or a solid
     cell in the standing row between: bat (also at gap 4); gap >= 6 .. VB_GAP (12) on open floor: bat;
     gap 13 (also with a pit): walks; gap 0: walks (vb_cut D = 0 is safe)
  B  bat chase on flat ground (VAMP-BAT-CHASE): E_RCD bit 3 RCD_VSEEN set by the first close-distance
     transform; no flapping over 6 turns hovering at gap 3-5 (a bat stays, a humanoid walks); real
     turns: a Vampire 10 cols away turns into a bat, reaches adjacency, reverts at gap <= 2 (<= 2
     kind changes), and the line is logged once for the body (a second transform is silent);
     info: turns to adjacency from gap 10
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
  V  VBAT-ART (user playtest: the bat form "FLASHED"; the fade-out death stand-in blinked): K_VBAT
     draws in the Bat's ink; every tick of a flee + a close-distance cycle (real turns) has no
     FLASH bit (attr bit 7) in either screen's attributes, the drawn bat-form cells (outside the
     hero's) = the Bat's attr while no flash / tint is on, and the alive bat is never hidden but on
     its transform tick; HURT = the glide frame + the ATTR_HIT flash; DEAD = the Vampire's
     small_corpse lying on the floor (rect bottom = the standing row), never hidden (no blink)
     until the slot frees. On D6, then D3 (the Bat resident) and D8.
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
ONCE, VFLEE, VSEEN = 0x80, S["RCD_VFLEE"], S.get("RCD_VSEEN", 8)
MIND_FEAR, STS_MIND = S["MIND_FEAR"], S["STS_MIND"]
GOLD = S["LEK_GOLD"]
ATTR_BAT = None                                # the Bat's KT_ATTR (read at run time)
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
        for d in (3, 8):
            L, r = level(p, lines, d, 0x7601, need=12)
            check(f"setup: D{d} + a 12-col standable run", L is not None, r)
            if L:
                visual(p, r, f"D{d}")
    print(f"vbat: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
    return 1 if fails else 0


def run(p, lines, r):
    global ATTR_BAT
    s_, c0 = r
    ATTR_BAT = p.rb(S["kind_tab"] + S["KT_ATTR"] + S["K_BAT"])
    check("V0 K_VBAT draws in the Bat's ink (KT_ATTR)", p.rb(S["kind_tab"] + S["KT_ATTR"] + KB) == ATTR_BAT,
          (p.rb(S["kind_tab"] + S["KT_ATTR"] + KB), ATTR_BAT))
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
    # ------------------------------------------------------------------ M  (VAMP-BOSS: a climbing Vampire keeps its form)
    setup(p, s_, c0, vx, hp=4)                 # flee case, mid-ladder (feet off the standing row), odd turn
    p.set_ent(1, Y=vy - 2, PY=(vy - 2) * 8)
    build_live(p)
    vb_turn(p, 3)
    e = p.ent(1)
    check("M1 mid-ladder, hp 5-of-14 flee case, odd turn: stays a Vampire (no RCD bits, no FEAR)",
          e["KIND"] == KV and e["POT"] & (ONCE | VFLEE) == 0 and fear(p, 1)[0] != MIND_FEAR, (e, fear(p, 1)))
    p.set_ent(1, Y=vy, PY=vy * 8)
    vb_turn(p, 3)
    check("M2 the same Vampire standing again: flees into a bat (the control)", p.ent(1)["KIND"] == KB, p.ent(1))
    setup(p, s_, c0, c0 + 3 + 6)               # close-distance case: gap 6 with a pit between
    p.set_ent(1, Y=vy - 2, PY=(vy - 2) * 8)
    build_live(p)
    old = cell(p, 9 * s_ + 8, c0 + 5, S["T_AIR"])
    vb_turn(p, 3)
    check("M3 mid-ladder, close-distance case (a pit between): stays a Vampire", p.ent(1)["KIND"] == KV, p.ent(1))
    cell(p, 9 * s_ + 8, c0 + 5, old)
    # ------------------------------------------------------------------ C
    vx = c0 + 3 + 6                            # gap 6
    setup(p, s_, c0, vx)
    vb_turn(p, 3)
    fr, sr = 9 * s_ + 8, 9 * s_ + 7
    check("C1 gap 6, no cut (open floor): bat, RCD_VSEEN, no flee bits",
          p.ent(1)["KIND"] == KB and p.ent(1)["POT"] & (ONCE | VFLEE | VSEEN) == VSEEN, p.ent(1))
    setup(p, s_, c0, c0 + 3 + 5)
    vb_turn(p, 3)
    check("C1b gap 5, no cut: walks (below VB_FAR)", p.ent(1)["KIND"] == KV, p.ent(1))
    setup(p, s_, c0, c0 + 3 + 12)
    vb_turn(p, 3)
    check("C1c gap 12 (VB_GAP): bat", p.ent(1)["KIND"] == KB, p.ent(1))
    setup(p, s_, c0, c0 + 3 + 13)
    vb_turn(p, 3)
    check("C1d gap 13: walks", p.ent(1)["KIND"] == KV, p.ent(1))
    setup(p, s_, c0, c0 + 3)
    vb_turn(p, 3)
    check("C1e gap 0 (touching): walks / bites", p.ent(1)["KIND"] == KV, p.ent(1))
    setup(p, s_, c0, vx)
    old = cell(p, fr, c0 + 5, S["T_AIR"])
    vb_turn(p, 3)
    cell(p, fr, c0 + 5, old)
    setup(p, s_, c0, c0 + 3 + 4)
    old = cell(p, fr, c0 + 5, S["T_AIR"])
    vb_turn(p, 3)
    check("C1f gap 4 (< VB_FAR) with a pit between: bat (the cut rule stays)", p.ent(1)["KIND"] == KB, p.ent(1))
    cell(p, fr, c0 + 5, old)
    setup(p, s_, c0, vx)
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
    setup(p, s_, c0, c0 + 3 + 13)
    old = cell(p, fr, c0 + 5, S["T_AIR"])
    vb_turn(p, 3)
    check("C4 gap 13 with a pit: walks", p.ent(1)["KIND"] == KV, p.ent(1))
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
    setup(p, s_, c0, c0 + 3 + 8, k=KB)
    hero_at(p, c0, s_ ^ 1)
    vb_turn(p, 4)
    e = p.ent(1)
    check("N5 the hero on the other storey: a (close-distance) bat reverts to the humanoid, standing", e["KIND"] == KV and e["Y"] == vy, e)
    vb_turn(p, 5)
    vb_turn(p, 6)
    check("N5b ... and stays one (no re-transform with the hero elsewhere)", p.ent(1)["KIND"] == KV, p.ent(1))
    setup(p, s_, c0, c0 + 3 + 8, k=KB)
    hero_at(p, c0, s_ ^ 1)
    olds = [cell(p, fr, c, S["T_AIR"]) for c in range(c0 + 10, c0 + 13)]
    vb_turn(p, 4)
    check("N5c ... only when the humanoid box is legal (over a pit it stays a bat)", p.ent(1)["KIND"] == KB, p.ent(1))
    for c, t in zip(range(c0 + 10, c0 + 13), olds):
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
    p.wb(S["P_ENTITIES"] + S["E_HIT"], 0)          # LOG-DMG: IX = an attacker with E_HIT 0 -> no " -D" tail
    for k in (KV, KB):
        keep_pc(lambda q: q.code([0xDD, 0x21] + w16(S["P_ENTITIES"]) + [0x06, S["MSG_M_HIT"], 0x0E, k, 0xCD]
                                 + w16(S["impact_line"]), game=True))(p)
        got.append(stream_text(p.z.read_memory(S["MSG_BUF"], 32)).rstrip("."))
    check("D1 the bite hit: 'THE VAMPIRE DRAINS YOU' (humanoid) / 'THE VAMPIRE HITS YOU' (bat form)",
          got == ["THE VAMPIRE DRAINS YOU", "THE VAMPIRE HITS YOU"], got)
    # ------------------------------------------------------------------ T
    clear_room(p)
    hero_at(p, c0, s_)
    build_live(p)
    _, t0 = vb_turn(p, 3)
    setup(p, s_, c0, c0 + 3 + 5)                # (gap 5: stays humanoid, VB_FAR is 6)
    _, t1 = vb_turn(p, 3)
    setup(p, s_, c0, c0 + 3, hp=4)
    _, t2 = vb_turn(p, 3)
    print(f"[info] vb_turn T-states (far7 incl.): none {t0}, a Vampire staying {t1}, a flee transform {t2}", flush=True)
    check("T vb_turn <= 2.5k T without a candidate, <= 6.3k staying (was 6k; VAMP-BOSS adds the is_standing test ~130 T and the figure includes the AY ISR, 5.4k..6.2k seen), <= 12k a transform (end_turn tick)",
          t0 <= 2500 and t1 <= 6300 and t2 <= 12000, (t0, t1, t2))
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
    # ------------------------------------------------------------------ B
    for gap in (3, 4, 5):                      # hovering: no flapping over 6 turns (3 each parity)
        setup(p, s_, c0, c0 + 3 + gap, k=KB)
        ks = [(vb_turn(p, n), p.ent(1)["KIND"])[1] for n in range(3, 9)]
        setup(p, s_, c0, c0 + 3 + gap)
        kh = [(vb_turn(p, n), p.ent(1)["KIND"])[1] for n in range(3, 9)]
        check(f"B1 gap {gap}, 6 turns: a bat stays a bat only while a cut is between (here none: it reverts "
              f"once at gap <= 2), a humanoid never turns", kh == [KV] * 6 and (
              ks == [KB] * 6 if gap > 2 else True), (ks, kh))
    lines.arm()
    for rep_ in (1, 2):
        vx = c0 + 3 + 10 if rep_ == 1 else c0 + 3 + 8
        if rep_ == 1:
            setup(p, s_, c0, vx)
            lines.lines.clear()
        else:
            p.set_ent(1, X=vx, PX=vx * 8)     # a second cycle for the same body (RCD_VSEEN kept)
            build_live(p)
        kinds, adj, flips, xs = [], None, 0, []
        for t in range(1, 41):
            heal(p)
            p.turn("WAIT")
            e = p.ent(1)
            if kinds and kinds[-1] != e["KIND"]:
                flips += 1
            kinds.append(e["KIND"])
            xs.append(e["X"])
            if adj is None and abs(e["X"] - c0) <= 4:             # melee reach: gap <= 1 col
                adj = t
            if adj is not None and e["KIND"] == KV:
                break
        n_ln = sum("TURNS INTO A BAT" in ln for ln in lines.lines)
        print(f"[info] chase from gap {vx - c0 - 3}: bat at turn {kinds.index(KB) + 1 if KB in kinds else None}, "
              f"adjacent at turn {adj}, kind flips {flips}, lines so far {n_ln}, hero x {c0}, x {xs}", flush=True)
        check(f"B2.{rep_} flat room, hero {vx - c0 - 3} cols away: it becomes a bat, reaches adjacency, "
              f"reverts (<= 2 flips)", KB in kinds and adj is not None and kinds[-1] == KV and flips <= 2
              and p.ent(1)["POT"] & VSEEN, (kinds, adj, flips, p.ent(1)))
        check(f"B3.{rep_} the line is logged once per body ({n_ln})", n_ln == 1, lines.lines)
    p.z.cmd("set-breakpoint 5")
    screen_safe(p)
    visual(p, r, "D6", cycles=True)


def attr_scan(p, bad, tag):
    """V: one rendered tick: no FLASH bit in either screen's attributes; the drawn bat form's
    cells (bank 5, outside the hero's drawn rect) = the Bat's attr while no flash / tint / reaction."""
    cf = p.composed_frame()
    for nm, fr in (("b5", cf), ("shown", p.frame())):
        f = [(i // 32, i % 32, fr[6144 + i]) for i in range(768) if fr[6144 + i] & 0x80]
        if f:
            bad.append((tag, nm, "FLASH", f[:3]))
    e = p.ent(1)
    if not e["FLAGS"] & 1 or e["KIND"] != KB:
        return
    if not e["DVIS"] & 1:
        bad.append((tag, "bat hidden"))
        return
    if e["FLT"] or e["REACT"] or p.rb(S["ST_FLAGS"] + 1) & S["STS_TINTED"]:
        return
    if e["DFID"] not in (S["FID_bat_flapup"], S["FID_bat_glide"]):
        return                                 # the transform tick: the drawn state is still the old kind's
    h = p.ent(0)
    hero = {(r_, c) for r_ in range(h["DROW"], h["DROW"] + h["DROWS"])
            for c in range(h["DCOL"], h["DCOL"] + h["DCOLS"])} if h["DVIS"] & 1 else set()
    cells = [cf[6144 + r_ * 32 + c] for r_ in range(e["DROW"], e["DROW"] + e["DROWS"])
             for c in range(e["DCOL"], e["DCOL"] + e["DCOLS"]) if (r_, c) not in hero]
    if any(a != ATTR_BAT for a in cells):
        bad.append((tag, "attr", e["DROW"], e["DCOL"], cells[:6]))


def turns(p, n, bad, tag, keys=("WAIT",), hp=None):
    """n real turns + 2 idle ticks each, attr_scan every rendered tick (the transform tick may hide
    the slot once: R_VIS, fix/vamp-corruption) -> the kinds after each turn."""
    ks = []
    for t in range(n):
        heal(p)
        if hp is not None and p.ent(1)["KIND"] == KV:
            p.set_ent(1, HP=hp)
        k0 = p.ent(1)["KIND"]
        sub = []
        p.turn(*keys, per_tick=lambda fr, hero: attr_scan(p, sub, f"{tag} t{t}"))
        for _ in range(2):
            p.tick()
            attr_scan(p, sub, f"{tag} t{t}i")
        if p.ent(1)["KIND"] != k0:             # a transform this turn: one hidden tick allowed
            hid = [b for b in sub if b[1:] == ("bat hidden",)]
            sub = [b for b in sub if b[1:] != ("bat hidden",)] + hid[1:]
        bad += sub
        ks.append(p.ent(1)["KIND"])
    return ks


def visual(p, r, tag, cycles=False):
    s_, c0 = r
    bad = []
    if cycles:                                 # D6: a flee + a close-distance cycle, real turns
        setup(p, s_, c0 + 3, c0 + 6, hp=4)
        ks = turns(p, 12, bad, tag + " flee", hp=4)
        fr, old = 9 * s_ + 8, None
        setup(p, s_, c0, c0 + 9)
        old = cell(p, fr, c0 + 5, S["T_AIR"])
        ks2 = turns(p, 6, bad, tag + " close")
        cell(p, fr, c0 + 5, old)
        check(f"V1 {tag} flee {ks} / close {ks2}: the bat form appears; no FLASH bit, the Bat's attr "
              "on its cells, never hidden but the transform tick", KB in ks and KB in ks2 and not bad, bad[:4])
    else:                                      # D3 / D8: a resting bat form, 3 turns
        setup(p, s_, c0, c0 + 6, k=KB)
        ks = turns(p, 3, bad, tag)
        check(f"V1 {tag} a bat form, 3 turns: no FLASH bit, the Bat's attr on its cells", not bad, bad[:4])
    # HURT / DEAD: a bat form beside the hero, eva 0 (the hit lands); hp 30 then hp 1
    eva = S["kind_tab"] + S["KT_EVA"] + KB
    eva0 = p.rb(eva)
    p.wb(eva, 0)
    for hp in (30, 1):
        rec = []

        def pt(fr, hero):
            e = p.ent(1)
            cf = p.composed_frame()
            a = [cf[6144 + r_ * 32 + c] for r_ in range(e["DROW"], e["DROW"] + e["DROWS"])
                 for c in range(e["DCOL"] + 1, e["DCOL"] + e["DCOLS"] - 1)]   # the inner cols (no hero spill)
            rec.append((e["FLAGS"], e["DVIS"] & 1, e["DFID"], e["DROW"] + e["DROWS"] - 1, e["HP"], a))
        for _ in range(4):
            setup(p, s_, c0, c0 + 3, k=KB, hp=hp, maxhp=14)
            rec.clear()
            p.turn("L", per_tick=pt)
            for _ in range(12):
                p.tick()
                pt(None, None)
            if any(x[4] < hp for x in rec):
                break
        if hp == 30:
            hurt = [x for x in rec if x[1] and x[2] == S["FID_bat_glide"] and x[5] and all(v == S["ATTR_HIT"] for v in x[5])]
            check(f"V2 {tag} HURT: the glide frame + the ATTR_HIT flash", bool(hurt), rec[:6])
        else:
            dying = [x for x in rec if x[0] & 1 and x[0] & S["EF_DYING"]]
            dead = [x for x in dying if x[2] == S["FID_small_corpse"]]
            check(f"V3 {tag} DEAD: never hidden while dying (no blink), the Vampire's small_corpse on the "
                  f"floor (rect bottom row {9 * s_ + 7})",
                  dying and all(x[1] for x in dying) and dead and all(x[3] == 9 * s_ + 7 for x in dead)
                  and not p.ent(1)["FLAGS"] & 1, (len(dying), dying[-3:], p.ent(1)["FLAGS"]))
    p.wb(eva, eva0)


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
