#!/usr/bin/env python3
"""D3-7 T6: the Warrior's dagger throw and bow shot (src/abil_ammo7.asm
abil_ammo / ammo_fire) as a split ability turn, the ammo pickup
(src/pickup7.asm floor_pickup / ap_take / ap_stamp), the ammo floor glyphs
in build_room_map, played through the real controls in PROTO room A on a
release build (DEBUG_KIT=0). Rules: game.md §6.3 (dagger r6 atk+1 1d4+2,
bow r14 atk 1d6+1, PHYS, both legal with no target, NO DAGGERS / NO BOW /
NO ARROWS, caps 9 / 24, QUIVER FULL), §11.4 (3D: the spent ammo is
consumed, no floor drop), §2.3 (no throws / shots mid-ladder), §6 "Logic"
(missiles roll F1, a miss flies on, no bounces: a wall stops them).

  R1  DAGGERS 0 -> NO DAGGERS        R2  no bow (ARROWS 5) -> NO BOW
  R3  bow, ARROWS 0 -> NO ARROWS     R4  mid-ladder -> NO TARGET (both)
      every refusal: no turn, the counters / TURN_PEND untouched, the line
  F1..F7  throws / shots: the accept spends 1 (DAGGERS / ARROWS), TURN_PEND
      = TP_ACT | TP_MON, ABL, 2, 3, the kn_throw / kn_bow sequence, PD_AMMO;
      the RNG poked with a seed the proj3 model picks at probe_act_prep
      (D3-8e: the flight starts in the accept, act_begin -> proj_pre; the
      model = a one-shot cast at the release, TURN_TICK 2); after the fire
      tick (probe_act_fire, TURN_TICK 2) pf_stop / pf_col / pf_tgt / pf_lost / pf_itick /
      pf_desc, the RNG and every body == the model; the line == "YOUR DAGGER
      / ARROW HITS THE <kind>" / "YOU KILL THE <kind>" / "... MISSES"; the
      monsters only after the FX; FX_DROP 0; the turn ends.
      F1 dagger hits a Rat (dmg 3..6)   F2 dagger misses the Rat (flies on
      to the range end)   F3 dagger: a Goblin 7 cells away is out of range (range
      end, no roll)   F4 bow hits that Goblin (dmg 2..7)   F5 bow kills a Rat
      F6 bow: the 1st roll misses, the arrow flies on and hits the 2nd body
      F7 no target: dagger into the wall 3 cells away (PFS_WALL, stops in
      front: missiles have no bounces)
  D1  bow vs dagger damage over the model: the same 300 seeds give 1d6+1 vs
      1d4+2 on a hit (independent of the emulator; documents F1/F4)
  P1  a 3-dagger stack under the hero's step: DAGGERS +3, the entry
      FL_EMPTY, the cell T_AIR, "YOU PICK UP 3 DAGGERS"
  P2  DAGGERS 8 + a stack of 3: DAGGERS 9, 2 stay (FL_QTY 2, cell
      T_DAGGERS), "YOU PICK UP 1 DAGGER" + "QUIVER FULL"
  P3  ARROWS 24 + 5: nothing taken, the stack stays, "QUIVER FULL"
  P4  no bow, ARROWS 20 + 6 sharing a cell with a potion (the arrows drawn,
      last in list order): the potion AND 4 arrows taken (each entry by its
      own rule), 2 stay + QUIVER FULL, the cell still T_ARROWS; then ARROWS 0
      and a wait: the 2 taken, the cell T_AIR
  P5  the Mage walks over a dagger stack: nothing taken
  B1  build_room_map stamps IT_DAGGER / IT_ARROW entries as T_DAGGERS /
      T_ARROWS on row 9s+7 (a shared cell shows the last entry)
  T7 (fix pass):
  G   the user report "an arrow flies through the Goblin making no damage":
      model-independent sweep (seed chosen by the first d20 only) at gaps
      0 / 1 / 3 / 9, both facings, bow and dagger: hit iff d20 >= 9 (bow) /
      8 (dagger) — a designed missed roll, no defect; a miss now logs "YOUR
      ARROW MISSES THE GOBLIN", sets pf_miss and RC_DODGE (E_REACTAT = the tick
      the FX passes) -> the ATTR_MISS flash on exactly that tick
  H   a 1-tick Right / WAIT tap during a log hold (LT_HOLD, 3 lines): held
      that tick, replayed from LOG_PDIR once the queue is empty
  P6  full pack + arrows over a potion: the potion stays, re-stamped + attr
  P7  ap_take sets PD_AMMO   P8 a storey-0 stack (row 7)
  P9  POTIONS_TAKEN bit for entry index < 8 only (5 / 9), cell + attr shadow
  P10 the floor_pickup pre-filter: no glyph under the body -> no scan
Run: ZRCP_PORT=<port> python3 tests/abil_ammo.py
"""
import copy
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import (Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, K_RAT, K_GOBLIN, K_SKELETON,  # noqa: E402
                      stand_y)
from proj3 import T, w16, World, Body, Rng  # noqa: E402
import proj3  # noqa: E402
import combat_tables as CT  # noqa: E402
import textpack  # noqa: E402
import world  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT, EF_DYING, EF_PENDING = 1, 2, 4, 8, 16, 64
E_REACT, E_REACTAT = 15, 16
DAGGER, BOW = S["ABL_DAGGER"], S["ABL_BOW"]
SLOT = {DAGGER: 3, BOW: 4}                        # bar_knight: sword, power, whirl, daggers, bow
HY = stand_y(1, 6)                                # the hero on room A's bottom storey
HX = 9
NOWHERE = 7
NONE = 0xFF
FL, FLS = S["FLOOR_LIST"], S["FL_STRIDE"]
STRINGS = textpack.read_strings()
TXT = dict(STRINGS)
NM = {K_RAT: "RAT", K_GOBLIN: "GOBLIN", K_SKELETON: "SKELETON"}
IMG = textpack.parse_emitted(os.path.join(HERE.parent, "build", "text", "strings.asm"))
PD_AMMO = S["PD_AMMO"]


def stream_text(raw):
    """A log ring entry (token stream / plain text) -> text."""
    t0 = 2 * len(STRINGS)
    out = []
    for a in raw:
        if a == 0:
            break
        if a < 0x80:
            out.append(chr(a))
            continue
        q = int.from_bytes(IMG[t0 + 2 * (a - 0x80):t0 + 2 * (a - 0x80) + 2], "little")
        while True:
            c = IMG[q]
            q += 1
            out.append(chr(c & 0x7F))
            if c & 0x80:
                break
    return "".join(out)


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:700]}", flush=True)

        if KIT:
            print("[skip] abil_ammo needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(h, p, check)
        print(f"abil_ammo: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def run(h, p, check):
    kt = {}
    probe = S["probe_act_fire"]
    prep = S["probe_act_prep"]                    # D3-8e: act_begin, before proj_pre
    slots = {}

    def stand(kind, cls=K_KNIGHT):
        return HY + kt[cls]["bh"] - kt[kind]["bh"]

    def place(slot, x, y, flags, hp=None):
        kw = dict(X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=p.rb("CUR_ROOM"), FLAGS=flags, REACT=0,
                  FLT=0, HIT=0)
        if hp is not None:
            kw.update(HP=hp, MAXHP=hp)
        p.set_ent(slot, **kw)

    def scene(mons, daggers=3, arrows=0, bow=0, hero=(HX, HY), cls=K_KNIGHT):
        """Fresh game in PROTO room A: every monster parked, the hero at
        `hero` facing right (HP 200), mons = [(kind, x, hp)] standing on the
        hero's floor facing him; the ammo counters poked."""
        p.boot(cls)
        if not kt:
            kt.update(p.kinds())
        if not slots:
            for sl in range(1, 16):
                slots.setdefault(p.ent(sl)["KIND"], sl)
        room = p.rb("CUR_ROOM")
        for sl in range(1, 16):
            e = p.ent(sl)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                p.set_ent(sl, ROOM=NOWHERE)
        place(0, hero[0], hero[1], EF_ACTIVE | EF_PLAYER, 200)
        out = {}
        for kind, x, hp in mons:
            sl = slots[kind]
            place(sl, x, stand(kind, cls), EF_ACTIVE | EF_HOSTILE | EF_LEFT, hp)
            out[sl] = kind
        p.wmem(S["ST_FLAGS"], [0] * 16)
        p.wmem(S["ST_T1"], [0] * 16)
        p.wb("DAGGERS", daggers)
        p.wb("ARROWS", arrows)
        p.wb("HAS_BOW", bow)
        p.wb("FX_DROP", 0)
        p.tick(3)
        return out

    def ring():
        q = S["LOG_Q"]
        return (p.rb(q + S["LQ_RD"]) + p.rb("LOG_QN")) % S["LOG_SLOTS"], p.rb("LOG_QN")

    def ring_lines(w0, n):
        out = []
        for i in range(n):
            sl = (w0 + i) % S["LOG_SLOTS"]
            out.append(stream_text(p.z.read_memory(S["LOG_TXT"] + sl * S["LOG_SLOT_LEN"], S["LOG_SLOT_LEN"])))
        return out

    def last_line():
        p.until(lambda: p.rb("LOG_QN") == 0, 30)
        p.tick(2)
        return world.log_row(p.composed_frame(), 23)

    def counters():
        return dict(d=p.rb("DAGGERS"), a=p.rb("ARROWS"))

    def refuse(tag, abl, want_txt):
        c0 = counters()
        p.select_slot(SLOT[abl])
        t0 = p.rw("TURN_COUNTER")
        nt = p.no_turn("FIRE")
        got = dict(no_turn=nt, tc=p.rw("TURN_COUNTER") - t0, c=counters(), pend=p.rb("TURN_PEND"),
                   line=last_line() == world.text6(want_txt))
        check(f"{tag}: refused, no turn, ammo / TURN_PEND untouched, {want_txt!r}",
              got == dict(no_turn=True, tc=0, c=c0, pend=0, line=True), got)

    def model_world():
        cur = p.rb("CUR_ROOM")
        w = World(kt, list(p.z.read_memory(S["HERO_RES"], 3)), p.rb("HERO_DEF"))
        w.hero_imm = p.rb("HERO_IMM")
        w.turn_tick = p.rb("TURN_TICK")
        stf = p.z.read_memory(S["ST_FLAGS"], 16)
        st1 = p.z.read_memory(S["ST_T1"], 16)
        for sl in range(16):
            e = p.ent(sl)
            if e["FLAGS"] & (EF_ACTIVE | EF_PENDING) != EF_ACTIVE or e["ROOM"] != cur:
                continue
            b = Body(sl, e["KIND"], e["X"], e["Y"], e["HP"], e["MAXHP"], e["FLAGS"])
            b.stf, b.st1 = stf[sl], st1[sl]
            w.bodies[sl] = b
        row0 = w.bodies[0].y + S["PF_ROW_DY"]
        w.row = list(p.z.read_memory(S["ROOM_MAP"] + row0 * 32, 32))
        tf = p.z.read_memory(S["tile_flags"], 64)
        solid = {i for i in range(64) if tf[i] & S["TF_SOLID"]}
        return w, solid

    def shoot(tag, abl, mons, want, daggers=3, arrows=10, extra=None, setup=None):
        """One throw / shot through the controls; want(res, w) picks the seed."""
        kinds = scene(mons, daggers=daggers, arrows=arrows, bow=1)
        if setup:
            setup()
        c0 = counters()
        p.select_slot(SLOT[abl])
        t0 = p.rw("TURN_COUNTER")
        p.wb("PANEL_DIRTY", 0)
        p.z.cmd("set-breakpoint 3 PC=%d" % prep)  # D3-8e: the flight starts in the accept
        p.extra_probes = {prep}
        p.tap("FIRE")                             # (stops at the probe, mid input tick)
        at_prep = p.pc() == prep
        w0, solid = model_world()                 # the world before the first strike
        w0.turn_tick = S["ACT_FIRE_TICK"]         # a one-shot cast at the release
        for seed in range(1, 30000):
            w = copy.deepcopy(w0)
            rng = Rng(seed)
            res = w.fire(rng, 0, abl, 1, 0, solid)
            if want(res, w):
                break
        else:
            raise AssertionError("no seed")
        p.wmem(S["RNG_STATE"], w16(seed))
        p.z.cmd("set-breakpoint 3")
        p.extra_probes = set()
        if at_prep:
            p.tick()                              # the rest of the input tick
        check(f"{tag}: the accept reaches proj_pre (probe_act_prep)", at_prep, p.pc())
        e0 = p.z.read_memory(S["P_ENTITIES"], STRIDE)
        seq = S["kn_throw" if abl == DAGGER else "kn_bow"]
        acc = dict(c=counters(), pend=list(p.z.read_memory(S["TURN_PEND"], 4)), ph=p.rb("TURN_PHASE"),
                   seq=seq <= (e0[13] << 8 | e0[12]) < seq + 7)
        want_c = dict(d=c0["d"] - (abl == DAGGER), a=c0["a"] - (abl == BOW))
        want_acc = dict(c=want_c, pend=[S["TP_ACT"] | S["TP_MON"], abl, 2, 3], ph=1, seq=True)
        check(f"{tag}: the accept spends 1, TURN_PEND set, the sequence", acc == want_acc, (acc, want_acc))
        p.z.cmd("set-breakpoint 3 PC=%d" % probe)
        p.extra_probes = {probe}
        for _ in range(6):
            p.tick()
            if p.pc() == probe:
                break
        at = p.pc() == probe and p.rb("TURN_TICK") == 2
        check(f"{tag}: the release on TURN_TICK 2", at, (p.pc(), p.rb("TURN_TICK")))
        if not at:
            p.z.cmd("set-breakpoint 3")
            p.extra_probes = set()
            return None
        wr0, qn0 = ring()                         # (the lines come with the release)
        p.z.cmd("set-breakpoint 3")
        p.extra_probes = set()
        p.tick()                                  # the rest of the fire tick
        got = {n: p.rb(n) for n in ("pf_stop", "pf_col", "pf_tgt", "pf_lost", "pf_itick", "pf_miss")}
        got["desc"] = list(p.z.read_memory(S["pf_desc"], 16))
        got["rng"] = p.rw("RNG_STATE")
        mem = p.z.read_memory(S["P_ENTITIES"], 16 * STRIDE)
        got["bodies"] = {sl: (mem[sl * STRIDE + 5], bool(mem[sl * STRIDE + 2] & EF_DYING),
                              mem[sl * STRIDE + E_REACTAT] if mem[sl * STRIDE + E_REACT] else None)
                         for sl in w.bodies}
        exp = {"pf_stop": res["stop"], "pf_col": res["col"], "pf_tgt": res["tgt"], "pf_lost": res["lost"],
               "pf_miss": res["miss"],
               "pf_itick": res["itick"], "desc": res["desc"], "rng": rng.st,
               "bodies": {sl: (b.hp, bool(b.flags & EF_DYING), b.reactat if b.react else None)
                          for sl, b in w.bodies.items()}}
        bad = [(n, got[n], exp[n]) for n in exp if got[n] != exp[n]]
        check(f"{tag}: the flight == the proj3 model (stop {proj3.PFS_NAME[res['stop']]}, tgt {res['tgt']},"
              f" lost {res['lost']}, col {res['col']})", not bad, bad)
        wr1, qn1 = ring()
        lines = ring_lines(wr0, qn1 - qn0)
        name = "dag" if abl == DAGGER else "arr"
        tg, mi = res["tgt"], res["miss"]
        exp_l = []
        if mi not in (0, NONE) and mi != tg:      # T7: the first body missed is named
            exp_l.append(TXT[f"cmb_{name}_miss"] + " THE " + NM[kinds[mi]])
        if tg == NONE:
            exp_l = exp_l or [TXT[f"cmb_{name}_miss"]]
        elif w.bodies[tg].hp == 0:
            exp_l.append(TXT["you_kill"] + NM[kinds[tg]])
        elif tg != 0:
            exp_l.append(TXT[f"cmb_{name}_hit"] + NM[kinds[tg]])
        check(f"{tag}: the line {exp_l}", [l.rstrip(".") for l in lines] == [l.rstrip(".") for l in exp_l],
              (lines, exp_l))
        if extra:
            extra(res, w)
        seen = []
        for _ in range(120):
            seen.append((p.rb("TURN_PEND"), p.rb("FX_BUSY")))
            if p.rw("TURN_COUNTER") != t0 and p.idle():
                break
            p.tick()
        kmon = next((i for i, s in enumerate(seen) if s[0] == 0), None)
        check(f"{tag}: monsters only after the FX is idle, the turn ends, the count stays, FX_DROP 0",
              kmon is not None and seen[kmon][1] == 0 and p.rw("TURN_COUNTER") == t0 + 1
              and counters() == want_c and p.rb("FX_DROP") == 0,
              (kmon, seen[:10], p.rw("TURN_COUNTER") - t0, counters(), p.rb("FX_DROP")))
        return res

    sx = HX + 3                                   # the first cell in front of the Knight (bw 3)

    # ---- refusals ---------------------------------------------------------------
    scene([(K_RAT, sx + 3, 40)], daggers=0, arrows=5, bow=1)
    refuse("R1 DAGGERS 0", DAGGER, TXT["no_daggers"])
    scene([(K_RAT, sx + 3, 40)], daggers=3, arrows=5, bow=0)
    refuse("R2 no bow", BOW, TXT["no_bow"])
    scene([(K_RAT, sx + 3, 40)], daggers=3, arrows=0, bow=1)
    refuse("R3 ARROWS 0", BOW, TXT["no_arrows"])
    scene([], daggers=3, arrows=5, bow=1, hero=(5, HY))
    p.turn("K")                                   # one row up the {5,1} shaft: mid-ladder
    check("R4 hero mid-ladder", p.ent(0)["Y"] == HY - 1, p.ent(0)["Y"])
    refuse("R4 dagger mid-ladder", DAGGER, TXT["no_target"])
    refuse("R4 bow mid-ladder", BOW, TXT["no_target"])

    # ---- throws / shots ------------------------------------------------------------
    lost_in = lambda lo, hi: (lambda res, w: res["tgt"] not in (0, NONE) and lo <= res["lost"] <= hi  # noqa: E731
                                            and w.bodies[res["tgt"]].hp > 0)
    shoot("F1 dagger hits a Rat", DAGGER, [(K_RAT, sx + 3, 40)], lost_in(3, 6))
    shoot("F2 dagger misses the Rat (flies on to the range end)", DAGGER, [(K_RAT, sx + 3, 40)],
          lambda res, w: res["tgt"] == NONE)
    shoot("F3 dagger: a Goblin 7 cells away is out of range", DAGGER, [(K_GOBLIN, sx + 6, 40)],
          lambda res, w: res["stop"] == proj3.PFS["RANGE"] and res["tgt"] == NONE)
    shoot("F4 bow hits that Goblin", BOW, [(K_GOBLIN, sx + 6, 40)], lost_in(2, 7))
    shoot("F5 bow kills a Rat", BOW, [(K_RAT, sx + 4, 3)],
          lambda res, w: res["tgt"] not in (0, NONE) and w.bodies[res["tgt"]].hp == 0)

    def first_missed(res, w):
        return res["tgt"] == slots.get(K_GOBLIN) and w.bodies[slots[K_RAT]].hp == 40

    shoot("F6 bow: misses the Rat, flies on, hits the Goblin", BOW,
          [(K_RAT, sx + 2, 40), (K_GOBLIN, sx + 6, 40)], first_missed)
    # F7: a wall 3 cells ahead on the flight row (poked into ROOM_MAP for this case)
    def wall_case():
        p.wb(S["ROOM_MAP"] + (HY + S["PF_ROW_DY"]) * 32 + sx + 3, S["T_BRICK"])

    res = shoot("F7 dagger, no target: into a wall 3 cells away", DAGGER, [], lambda res, w: True,
                setup=wall_case)
    if res:
        check("F7 the wall stops it on the free cell in front (no bounce)",
              res["stop"] == proj3.PFS["WALL"] and res["col"] == sx + 2, res)

    # ---- G: the user report (T7) "an arrow flies through the Goblin making no damage" ----
    # Model-independent: the seed is chosen by the FIRST d20 only (proj_fire's first
    # draw for the first body in line), every expectation comes from F1 and the
    # geometry, not from the proj3 walk model. Bow: atk 2 + 0 vs eva 1 -> hit iff
    # d20 >= 9; dagger +1 -> d20 >= 8. Distances: adjacent (gap 0), 1, 3, 9 cells,
    # both facings. A miss must fly on (designed, game.md §6 "Logic") AND say so:
    # "YOUR ARROW MISSES THE GOBLIN" + the goblin's dodge flash (RC_DODGE at the tick
    # the FX passes its first col -> ATTR_MISS for MISS_FLASH ticks).
    gob = slots[K_GOBLIN]

    def d20_seed(want):
        for seed in range(1, 5000):
            if Rng(seed).mod(20) + 1 == want:
                return seed
        raise AssertionError("no seed")

    def sweep(tag, abl, hx, left, gap, d20):
        thr = 9 - (1 if abl == DAGGER else 0)
        hit = d20 >= thr
        x = hx - gap - 3 if left else hx + 3 + gap
        scene([(K_GOBLIN, x, 40)], daggers=3, arrows=10, bow=1, hero=(hx, HY))
        if left:
            p.set_ent(0, FLAGS=EF_ACTIVE | EF_PLAYER | EF_LEFT)
            p.set_ent(gob, FLAGS=EF_ACTIVE | EF_HOSTILE)
            p.tick()
        p.select_slot(SLOT[abl])
        p.z.cmd("set-breakpoint 3 PC=%d" % prep)  # D3-8e: the d20 is drawn in the accept
        p.extra_probes = {prep}
        p.tap("FIRE")
        at = p.pc() == prep
        p.wmem(S["RNG_STATE"], w16(d20_seed(d20)))
        p.z.cmd("set-breakpoint 3 PC=%d" % probe)
        p.extra_probes = {probe}
        for _ in range(6):
            p.tick()
            if p.pc() == probe:
                break
        at = at and p.pc() == probe
        wr0, qn0 = ring()
        p.z.cmd("set-breakpoint 3")
        p.extra_probes = set()
        if not at:
            check(f"{tag}: reached the release", False)
            return
        p.tick()
        g = p.ent(gob)
        mem = p.z.read_memory(S["P_ENTITIES"] + gob * STRIDE, STRIDE)
        wr1, qn1 = ring()
        lines = [l.rstrip(".") for l in ring_lines(wr0, qn1 - qn0)]
        name = "dag" if abl == DAGGER else "arr"
        near = x + 2 if left else x
        got = dict(tgt=p.rb("pf_tgt"), miss=p.rb("pf_miss"), lost=40 - g["HP"], lines=lines)
        if hit:
            lo, hi = (3, 6) if abl == DAGGER else (2, 7)
            ok = (got["tgt"] == gob and got["miss"] == NONE and lo <= got["lost"] <= hi
                  and p.rb("pf_stop") == proj3.PFS["BODY"] and p.rb("pf_col") == near
                  and lines == [TXT[f"cmb_{name}_hit"] + "GOBLIN"])
        else:
            want_at = 2 + gap + 1                 # TURN_TICK 2 + FXD_DELAY 0 + move index gap + 1
            ok = (got["tgt"] == NONE and got["miss"] == gob and got["lost"] == 0
                  and lines == [TXT[f"cmb_{name}_miss"] + " THE GOBLIN"]
                  and mem[E_REACT] == S["RC_DODGE"] and mem[E_REACTAT] == want_at)
            got.update(react=mem[E_REACT], at=mem[E_REACTAT], want_at=want_at)
            seen = None
            for _ in range(20):
                p.tick()
                e = p.ent(gob)
                if e["FLT"] and e["FLA"] == S["ATTR_MISS"]:
                    seen = p.rb("TURN_TICK") - 1      # TURN_TICK steps at the tick's end
                    break
            got["flash"] = seen
            ok = ok and seen == want_at
        check(f"{tag} d20 {d20}: {'hit' if hit else 'miss + MISSES THE GOBLIN + dodge flash'}", ok, got)

    for abl, hx, left, gap, d20s in ((BOW, HX, False, 0, (8, 9)), (BOW, HX, False, 1, (8, 9)),
                                     (BOW, HX, False, 3, (1, 20)), (BOW, HX, False, 9, (8, 9)),
                                     (BOW, 22, True, 0, (8, 9)), (BOW, 22, True, 1, (8, 12)),
                                     (DAGGER, HX, False, 0, (7, 8)), (DAGGER, 22, True, 1, (7, 8))):
        for d20 in d20s:
            sweep(f"G {'bow' if abl == BOW else 'dagger'} {'left' if left else 'right'} gap {gap}",
                  abl, hx, left, gap, d20)

    # ---- H: T7 review — a 1-tick direction tap during a log hold is not lost --------
    # 3 lines pending + LT_HOLD (as end_turn leaves a starved turn): the tap's tick only
    # draws a line (no turn), the key is released before the hold ends; LOG_PDIR
    # replays it: the step runs once the queue is empty.
    for tag, keys, dx in (("Right", ("L",), 1), ("WAIT", ("WAIT",), 0)):
        scene([])
        for k in range(3):
            txt = [ord(c) for c in f"TEST LINE {k}"] + [0]
            sl = (p.rb(S["LOG_Q"] + S["LQ_RD"]) + k) % S["LOG_SLOTS"]
            p.wmem(S["LOG_TXT"] + sl * S["LOG_SLOT_LEN"], txt)
        p.wb("LOG_QN", 3)
        p.wb("PANEL_DIRTY", p.rb("PANEL_DIRTY") | S["PD_LOG"])
        p.wb("LOG_TURN", S["LT_HOLD"])
        x0, t0 = p.ent(0)["X"], p.rw("TURN_COUNTER")
        p.hold(*keys)
        p.tick()
        held = dict(turn=p.rw("TURN_COUNTER") - t0, ph=p.rb("TURN_PHASE"), qn=p.rb("LOG_QN"))
        p.release()
        for _ in range(12):
            p.tick()
            if p.rw("TURN_COUNTER") != t0 and p.idle():
                break
        got = dict(held=held["ph"] == 0 and held["qn"] < 3, turns=p.rw("TURN_COUNTER") - t0,
                   dx=p.ent(0)["X"] - x0, qn=p.rb("LOG_QN"), pdir=p.rb("LOG_PDIR"))
        check(f"H a 1-tick {tag} tap during a log hold: held that tick, replayed after the drain",
              got == dict(held=True, turns=1, dx=dx, qn=0, pdir=0), (got, held))

    # ---- D1: dagger vs bow damage (model) --------------------------------------------
    dd = {DAGGER: set(), BOW: set()}
    for abl in (DAGGER, BOW):
        rr = proj3.rank_row(abl, 1)
        for seed in range(1, 301):
            rng = Rng(seed)
            dd[abl].add(rng.mod(rr[1]) + 1 + rr[2])
    check("D1 dagger r6 1d4+2 = 3..6, bow r14 1d6+1 = 2..7 (ab_ammo rows, game.md §6.3)",
          dd[DAGGER] == set(range(3, 7)) and dd[BOW] == set(range(2, 8))
          and tuple(proj3.rank_row(DAGGER, 1)[:3]) == (6, 4, 2)
          and tuple(proj3.rank_row(BOW, 1)[:3]) == (14, 6, 1),
          (dd, proj3.rank_row(DAGGER, 1), proj3.rank_row(BOW, 1)))

    # ---- pickup ------------------------------------------------------------------------
    S1 = S["FL_S1"]
    IROW = 9 + 7                                  # the bottom storey's item row (9s + 7)

    def free_entries(n):
        out = []
        for i in range(S["FLOOR_MAX"]):
            if p.rb(FL + i * FLS) == S["FL_EMPTY"]:
                out.append(i)
                if len(out) == n:
                    return out
        raise AssertionError("floor list full")

    def put(i, col, item, qty, tile=None):
        p.wmem(FL + i * FLS, [p.rb("CUR_ROOM") | S1, col, item, qty])
        if tile is not None:
            p.wb(S["ROOM_MAP"] + IROW * 32 + col, tile)

    def entry(i):
        return list(p.z.read_memory(FL + i * FLS, 4))

    def cell(col):
        return p.rb(S["ROOM_MAP"] + IROW * 32 + col)

    def step_on(tag, keys=("L",)):
        wr0, qn0 = ring()
        t0 = p.rw("TURN_COUNTER")
        p.turn(*keys)
        ok = p.rw("TURN_COUNTER") == t0 + 1
        wr1, qn1 = ring()                         # (the panel may have drawn some already:
        n = (wr1 - wr0) % S["LOG_SLOTS"]          # count by the write position)
        return ok, [l.rstrip(".") for l in ring_lines(wr0, n)]

    col = HX + 3                                  # one step right: the body covers HX+1..HX+3
    pick = TXT["cmb_pick"]
    scene([], daggers=3)
    i, = free_entries(1)
    put(i, col, S["IT_DAGGER"], 3, S["T_DAGGERS"])
    ok, lines = step_on("P1")
    got = dict(ok=ok, d=p.rb("DAGGERS"), e=entry(i)[0], c=cell(col), lines=lines)
    check("P1 3 daggers picked up: DAGGERS 6, entry FL_EMPTY, cell T_AIR, the line",
          got == dict(ok=True, d=6, e=S["FL_EMPTY"], c=S["T_AIR"], lines=[pick + "3" + TXT["cmb_daggers"]]), got)

    scene([], daggers=8)
    i, = free_entries(1)
    put(i, col, S["IT_DAGGER"], 3, S["T_DAGGERS"])
    ok, lines = step_on("P2")
    got = dict(ok=ok, d=p.rb("DAGGERS"), e=entry(i), c=cell(col), lines=lines)
    want = dict(ok=True, d=9, e=[p.rb("CUR_ROOM") | S1, col, S["IT_DAGGER"], 2], c=S["T_DAGGERS"],
                lines=[pick + "1" + TXT["cmb_dagger"], TXT["quiver_full"]])
    check("P2 DAGGERS 8 + 3: 1 taken (cap 9), 2 stay, QUIVER FULL", got == want, (got, want))

    scene([], arrows=24, bow=1)
    i, = free_entries(1)
    put(i, col, S["IT_ARROW"], 5, S["T_ARROWS"])
    ok, lines = step_on("P3")
    got = dict(ok=ok, a=p.rb("ARROWS"), e=entry(i)[3], c=cell(col), lines=lines)
    check("P3 ARROWS 24 + 5: nothing taken, QUIVER FULL",
          got == dict(ok=True, a=24, e=5, c=S["T_ARROWS"], lines=[TXT["quiver_full"]]), got)

    scene([], arrows=20, bow=0)
    i, j = free_entries(2)
    pot0 = p.ent(0)["POT"]
    put(i, col, S["IT_POTION"], 1)
    put(j, col, S["IT_ARROW"], 6, S["T_ARROWS"])  # the last entry of the cell is drawn
    ok, lines = step_on("P4")
    got = dict(ok=ok, a=p.rb("ARROWS"), ep=entry(i)[0], e=entry(j)[3], c=cell(col), pot=p.ent(0)["POT"],
               lines=lines)
    check("P4 no bow, ARROWS 20 + 6 over a potion: the potion and 4 arrows taken, QUIVER FULL, the arrows drawn",
          got == dict(ok=True, a=24, ep=S["FL_EMPTY"], e=2, c=S["T_ARROWS"], pot=pot0 + 1,
                      lines=[TXT["found"], pick + "4" + TXT["cmb_arrows"], TXT["quiver_full"]]), got)
    p.wb("ARROWS", 0)
    ok, lines = step_on("P4b", ("WAIT",))
    got = dict(ok=ok, a=p.rb("ARROWS"), e=entry(j)[0], c=cell(col), lines=lines)
    check("P4 ARROWS 0 + a wait: the 2 left taken, the cell T_AIR",
          got == dict(ok=True, a=2, e=S["FL_EMPTY"], c=S["T_AIR"], lines=[pick + "2" + TXT["cmb_arrows"]]), got)

    scene([], daggers=0, cls=K_WIZARD)
    i, = free_entries(1)
    put(i, col, S["IT_DAGGER"], 3, S["T_DAGGERS"])
    ok, lines = step_on("P5")
    got = dict(ok=ok, d=p.rb("DAGGERS"), e=entry(i)[3], c=cell(col))
    check("P5 the Mage takes no daggers", got == dict(ok=True, d=0, e=3, c=S["T_DAGGERS"]), got)

    # ---- P6..P9: T7 review gaps ---------------------------------------------------------
    def shadow_attr(row, c):
        return world.bank7(p, S["SHADOW_ATTR"] + row * 32 + c, 1)[0]

    def tile_attr(t):
        return p.rb(S["TILE_ATTRS"] + t)

    # P6 full pack (E_POT 9) + 3 arrows over a potion: the potion stays (and is drawn
    # again, the last live entry), the arrows taken, PD_AMMO set, the attr shadow follows
    scene([], arrows=0, bow=1)
    i, j = free_entries(2)
    p.set_ent(0, POT=9)
    put(i, col, S["IT_POTION"], 1)
    put(j, col, S["IT_ARROW"], 3, S["T_ARROWS"])
    ok, lines = step_on("P6")
    got = dict(ok=ok, a=p.rb("ARROWS"), pot=p.ent(0)["POT"], ep=entry(i), ea=entry(j)[0], c=cell(col),
               sh=shadow_attr(IROW, col) == tile_attr(S["T_POTION"]), lines=lines)
    want = dict(ok=True, a=3, pot=9, ep=[p.rb("CUR_ROOM") | S1, col, S["IT_POTION"], 1], ea=S["FL_EMPTY"],
                c=S["T_POTION"], sh=True, lines=[pick + "3" + TXT["cmb_arrows"]])
    check("P6 full pack: potion stays (re-stamped T_POTION + attr shadow), 3 arrows taken", got == want, (got, want))

    # P7 ap_take sets PD_AMMO when it took something: read at the tick end_turn ran
    # (the panel clears the bit on the next tick: no ammo item is drawn yet)
    scene([], daggers=3)
    i, = free_entries(1)
    put(i, col, S["IT_DAGGER"], 2, S["T_DAGGERS"])
    p.wb("PANEL_DIRTY", 0)
    t0 = p.rw("TURN_COUNTER")
    p.hold("L")
    seen = None
    for k in range(40):
        p.tick()
        if p.rb("TURN_PHASE"):
            p.release()
        if p.rw("TURN_COUNTER") != t0:
            seen = p.rb("PANEL_DIRTY") & PD_AMMO
            break
    p.release()
    p.until(lambda: p.idle(), 60)
    check("P7 ap_take: PD_AMMO set when ammo was taken", seen == PD_AMMO and p.rb("DAGGERS") == 5,
          (seen, p.rb("DAGGERS")))

    # P8 a storey-0 stack: the hero on the top storey (room A {5,1} shaft top) waits on it
    scene([], daggers=3, hero=(HX, stand_y(0, 6)))
    if p.ent(0)["Y"] == stand_y(0, 6):
        i, = free_entries(1)
        c0 = HX + 1
        p.wmem(FL + i * FLS, [p.rb("CUR_ROOM"), c0, S["IT_DAGGER"], 2])
        p.wb(S["ROOM_MAP"] + 7 * 32 + c0, S["T_DAGGERS"])
        ok, lines = step_on("P8", ("WAIT",))
        got = dict(ok=ok, d=p.rb("DAGGERS"), e=entry(i)[0], c=p.rb(S["ROOM_MAP"] + 7 * 32 + c0),
                   sh=shadow_attr(7, c0) == tile_attr(S["T_AIR"]), lines=lines)
        check("P8 storey 0: 2 daggers taken from row 7, cell + attr shadow T_AIR",
              got == dict(ok=True, d=5, e=S["FL_EMPTY"], c=S["T_AIR"], sh=True,
                          lines=[pick + "2" + TXT["cmb_daggers"]]), got)

    # P9 POTIONS_TAKEN: entry index < 8 sets its bit, >= 8 sets none
    for idx in (5, 9):
        scene([])
        if entry(idx)[0] != S["FL_EMPTY"]:
            check(f"P9 entry {idx} free", False, entry(idx))
            continue
        pt0 = p.rb("POTIONS_TAKEN")
        put(idx, col, S["IT_POTION"], 1, S["T_POTION"])
        ok, lines = step_on("P9")
        want_bit = (1 << idx) if idx < 8 else 0
        got = dict(ok=ok, bits=p.rb("POTIONS_TAKEN") ^ pt0, e=entry(idx)[0], c=cell(col),
                   sh=shadow_attr(IROW, col) == tile_attr(S["T_AIR"]), lines=lines)
        check(f"P9 potion in entry {idx}: POTIONS_TAKEN bit {'set' if idx < 8 else 'none'}, cell + attr T_AIR",
              got == dict(ok=True, bits=want_bit, e=S["FL_EMPTY"], c=S["T_AIR"], sh=True, lines=[TXT["found"]]), got)

    # P10 the pre-filter keeps the invariant: a stack whose cell does NOT show it (poked,
    # never happens in play) is not scanned — documents what the filter relies on
    scene([], daggers=3)
    i, = free_entries(1)
    put(i, col, S["IT_DAGGER"], 2)                # no glyph stamped
    ok, lines = step_on("P10")
    check("P10 pre-filter: no item glyph under the body -> no scan (the stack stays)",
          ok and p.rb("DAGGERS") == 3 and entry(i)[3] == 2 and lines == [], (ok, p.rb("DAGGERS"), entry(i), lines))

    # ---- B1: build_room_map stamps the ammo glyphs ----------------------------------------
    scene([])
    room = p.rb("CUR_ROOM")
    a, b, c, d = free_entries(4)
    p.wmem(FL + a * FLS, [room | S1, 20, S["IT_DAGGER"], 2])
    p.wmem(FL + b * FLS, [room, 6, S["IT_ARROW"], 5])          # storey 0
    p.wmem(FL + c * FLS, [room | S1, 24, S["IT_ARROW"], 1])    # shared: arrows first, the potion last
    p.wmem(FL + d * FLS, [room | S1, 24, S["IT_POTION"], 1])
    ok, tb, m = world.build_only(p, room)
    got = dict(ok=ok, d=m[16 * 32 + 20], a=m[7 * 32 + 6], s=m[16 * 32 + 24])
    check("B1 build_room_map: daggers / arrows glyphs on row 9s+7, a shared cell shows the last entry",
          got == dict(ok=True, d=S["T_DAGGERS"], a=S["T_ARROWS"], s=S["T_POTION"]), got)


if __name__ == "__main__":
    sys.exit(main())
