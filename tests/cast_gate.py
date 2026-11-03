#!/usr/bin/env python3
"""D3-8e2: cast-time resolution timing (game.md §6.5.1 "logic early, visible
output at impact"), played through the real controls, release build
(DEBUG_KIT=0). Ticks are read at the wait_tick probe: TURN_TICK there is the
next tick's (the play loop increments it after the panel item), so tick t =
TURN_TICK - 1 while a turn runs; the render of tick t + 1 shows tick t's
anim state.

  T1  "fzcast" (Lightning r1, Ghost <-> wall ping-pong, 16 strikes incl. the
      caster) with the hero at HP 3: after the accept pf_tgt != $FF and
      COMBAT_NOT_BEFORE = min(pf_ftick, ACT_FIRE_TICK + CNB_MAX) > the release;
      while tick < the gate the panel draws nothing (PANEL_HP_SH unchanged,
      LT_SERVED clear, LOG_QN not drained) and the game is not over; the bolt
      is drawn (an FX track's FX_DFID != FX_NONE) before the first log line /
      HP redraw; after the gate the lines drain; the gate is 0 once the turn
      ended (end_turn)
  T2  the same at HP 200: as T1, and the monster phase (TURN_PEND -> 0) runs
      only with the log drained or LOG_WAIT_MAX ticks past max(MON_AT, the gate)
  T3  a Spark into an empty room (nothing struck): COMBAT_NOT_BEFORE stays 0
      (a miss sets no gate); a missed bow shot (a Rat with eva 99): 0 too
  T4  a FROZEN Rat (HP 1) killed by a Spark: its desired attr (SLOTREC R_ATTR)
      keeps the frozen tint on every render while its DEATH is pending (the
      kill cleared its STATUS at the accept), then the death plays
  T5  a Frost Shard (effect forced to "always", 2 turns) freezing a Goblin
      (60 HP): ST_FLAGS shows FROZEN from the accept (logic early), R_ATTR
      stays the kind attr while the reaction is pending, the tint shows once
      the HURT and its flash are over
  T6  Lightning r3 at a Rat 22 cells away: pf_ftick > ACT_FIRE_TICK + CNB_MAX,
      the gate is capped there (§6.5.1 "Bound"), T1's panel checks hold (a spell
      strike now logs YOU CAST <SPELL> (LOG-FIX 9aa2ec8) and a kill logs YOU KILL
      THE <kind>: T4/T6 check the panel output is held to the gate; T6b is the
      bow variant)
  T6b a bow shot at a Rat 12 cells away (pf_ftick 13 > the cap) that hits: "YOUR
      ARROW HITS THE RAT" is held to the gate, then drains
Run: ZRCP_PORT=<port> python3 tests/cast_gate.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from game_lib import Harness, S, EMU_ARGS, K_WIZARD, K_KNIGHT, K_RAT, K_GOBLIN, stand_y  # noqa: E402
import budget as B  # noqa: E402
import game  # noqa: E402

EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT, EF_DYING = 1, 2, 4, 8, 16
STRIDE = S["P_ENT_STRIDE"]
FX_NONE = 0xFF
CNB = S["COMBAT_NOT_BEFORE"]
GATE_MAX = S["ACT_FIRE_TICK"] + S["CNB_MAX"]
SPARK, FROST = S["ABL_SPARK"], S["ABL_FROST"]


def sample(p, slot=None):
    tracks = [p.rb(S[f"FXT{i}"] + S["FX_DFID"]) for i in range(3)]
    d = dict(tt=p.rb("TURN_TICK"), ph=p.rb("TURN_PHASE"), pend=p.rb("TURN_PEND"), cnb=p.rb(CNB),
             hpsh=p.rb("PANEL_HP_SH"), served=p.rb("LOG_TURN") & 1, qn=p.rb("LOG_QN"),
             fx=any(f != FX_NONE for f in tracks), gs=p.rb("GAME_STATE"), hp=p.ent(0)["HP"],
             mon=p.rb("MON_AT"))
    if slot is not None:
        e = p.ent(slot)
        d.update(react=e["REACT"], flt=e["FLT"], attr=p.rb(S["SLOTREC"] + slot * 16 + S["R_ATTR"]),
                 stf=p.rb(S["ST_FLAGS"] + slot), flags=e["FLAGS"])
    return d


def run_turn(p, slot=None, max_ticks=120):
    """FIRE with the selected slot: stop at the end of the input tick (the
    accept done), then sample every tick until the turn is over. Returns
    (accept sample, [per-tick samples], pf_tgt, pf_ftick)."""
    t0 = p.rw("TURN_COUNTER")
    p.hold("FIRE")
    p.tick()
    p.release()
    for _ in range(5):
        p.tick()
        if p.rb("TURN_PHASE") == 1:
            break
    acc = sample(p, slot)
    tgt, ftick = p.rb("pf_tgt"), p.rb("pf_ftick")
    ticks = []
    for _ in range(max_ticks):
        p.tick()
        ticks.append(sample(p, slot))
        if p.rw("TURN_COUNTER") != t0 and p.idle():
            break
    return acc, ticks, tgt, ftick


def main():
    fails = []
    if S.get("KIT_DEBUG", 0):
        print("cast_gate: needs a DEBUG_KIT=0 build")
        return 1
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = game.T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:900]}", flush=True)

        def fz(hp):
            scen = B.SCENARIOS["fzcast"]
            p.boot(scen[3], freeze=0)
            p.isolate()
            p.place(0, 12, B.HERO_Y)
            for slot, x, y, flags in scen[1]:
                p.place(slot, x, y, room=0, flags=flags)
            B.fzcast_setup(p, scen[1], "fzcast")
            p.set_ent(0, HP=hp)
            p.settle()

        def gate_checks(tag, acc, ticks, hpsh0, tgt, ftick, silent=False):
            """The §6.5.1 panel gate on one cast turn."""
            gate = acc["cnb"]
            want = min(ftick, GATE_MAX)
            check(f"{tag}: accept struck (pf_tgt {tgt}), gate = min(pf_ftick {ftick}, {GATE_MAX}) > release",
                  tgt != 0xFF and gate == want and gate > S["ACT_FIRE_TICK"], (tgt, ftick, gate))
            # panel item of tick t presented at t + 1; the impact of tick t at t + 2
            pre = [t for t in ticks if t["ph"] == 1 and t["tt"] - 1 <= gate]
            check(f"{tag}: up to the gate tick {gate} no panel output (HP bar, log) and no game over",
                  pre and all(t["hpsh"] == hpsh0 and t["served"] == 0 and t["gs"] == acc["gs"] for t in pre),
                  [(t["tt"], t["hpsh"], t["served"], t["qn"], t["gs"]) for t in ticks[:14]])
            first_fx = next((t["tt"] for t in ticks if t["fx"]), None)
            first_out = next((t["tt"] for t in ticks if t["served"] or t["hpsh"] != hpsh0), None)
            check(f"{tag}: the bolt is drawn (sample {first_fx}) before the first panel output (sample {first_out};"
                  f" silent cast = none: no MP item exists, a spell strike logs no line)",
                  first_fx is not None and (first_out is None if silent else
                                            first_out is not None and first_fx < first_out and first_out - 1 > gate),
                  (first_fx, first_out, gate))
            # (end_turn's own lines — YOU DIED — come after the turn: ph 0)
            pushed = acc["qn"] > 0 or any(t["qn"] > 0 for t in ticks if t["ph"] == 1)
            if pushed:
                # SND-5 (bisected 2026-10-20): the ISR's longer frames push the last line's
                # draw (panel_tick's 1st-frame rule) one tick later, so ONE line may still be
                # pending on the turn's last sample (LOG-FIX 9aa2ec8: a spell cast now logs
                # "YOU CAST <SPELL>" too, so the cast line + a monster-phase line may both be
                # pending: <= 2); it must drain within 4 more ticks (the
                # next turn waits on it: LT_HOLD), never be dropped (LQ_DROP 0).
                last = [t for t in ticks if t["ph"] == 0]
                p.tick(4)
                # Leftovers 2026-11-03: a fatal cast (T1, the hero's own HP-3 self-hit) ends in
                # the full-screen end card (endcard-g1): the log drain stops there, so the
                # queued 'YOU DIED' line stays pending (LOG_QN 1) by design; every other
                # line must have drained.
                dead = p.rb("GAME_STATE") == S["GS_DEAD"]
                check(f"{tag}: the cast's log lines drain after the gate (<= 2 pending at the turn end, none 4 ticks later)",
                      any(t["served"] for t in ticks) and all(t["qn"] <= 2 for t in last)
                      and p.rb("LOG_QN") <= (1 if dead else 0) and p.rb(S["LOG_Q"] + S["LQ_DROP"]) == 0,
                      [(t["tt"], t["qn"], t["served"]) for t in ticks[:24]] + [p.rb("GAME_STATE"), p.rb("LOG_QN")])
            kmon = next((i for i, t in enumerate(ticks) if t["pend"] == 0), None)
            if kmon is not None:
                t = ticks[kmon]
                ok = t["qn"] == 0 or t["tt"] - 1 >= max(acc["mon"], gate) + S["LOG_WAIT_MAX"]
            else:
                ok = False
            check(f"{tag}: monster phase after the log drained (or LOG_WAIT_MAX past the gate)", ok,
                  (kmon, [(t["tt"], t["pend"], t["qn"], t["fx"]) for t in ticks[:24]]))
            return pushed

        # ---- T1 / T2: the gate on the fzcast ping-pong ----------------------
        for tag, hp in (("T1", 3), ("T2", 200)):
            fz(hp)
            hpsh0 = p.rb("PANEL_HP_SH")
            acc, ticks, tgt, ftick = run_turn(p)
            gate_checks(f"{tag} fzcast HP {hp}", acc, ticks, hpsh0, tgt, ftick)
            p.tick(2)
            check(f"{tag}: the gate is cleared once the turn ended", p.rb(CNB) == 0, p.rb(CNB))
            if hp == 3:
                check("T1: the hero died of his own cast (HP 3 self-hit)",
                      p.ent(0)["FLAGS"] & EF_DYING or p.rb("GAME_STATE") == S["GS_DEAD"],
                      (p.ent(0)["HP"], p.rb("GAME_STATE")))

        # ---- T3: nothing struck -> no gate -----------------------------------
        p.boot(K_WIZARD, freeze=0)
        p.isolate()
        p.place(0, 14, B.HERO_Y)
        B.lcast_setup(p, [], k=SPARK, r=1, x=14)
        p.settle()
        acc, ticks, tgt, _ = run_turn(p)
        check("T3 Spark into an empty room: pf_tgt $FF, no gate", tgt == 0xFF and acc["cnb"] == 0
              and all(t["cnb"] == 0 for t in ticks), (tgt, acc["cnb"]))
        p.boot(K_KNIGHT, freeze=0)
        p.isolate()
        p.place(0, 12, B.HERO_Y)
        ry = stand_y(1, 2)
        p.place(1, 20, ry, room=0, flags=EF_ACTIVE | EF_HOSTILE | EF_LEFT)
        p.set_ent(1, KIND=K_RAT, HP=60, MAXHP=60)
        B.acast_setup(p, [(1,)])
        p.wb(S["kind_tab"] + S["KT_EVA"] + K_RAT, 99)     # (runtime kind_tab: the next boot reloads it)
        p.settle()
        acc, ticks, tgt, _ = run_turn(p)
        check("T3 bow shot that misses (Rat eva 99): pf_tgt $FF, pf_miss = the Rat, no gate",
              tgt == 0xFF and p.rb("pf_miss") == 1 and acc["cnb"] == 0, (tgt, acc["cnb"], p.rb("pf_miss")))

        # ---- T4 / T5: status tints at the impact ------------------------------
        def tint_scene(k, rank, kind, hp, stf, effect=None):
            p.boot(K_WIZARD, freeze=0)
            p.isolate()
            p.place(0, 14, B.HERO_Y)
            B.lcast_setup(p, [], k=k, r=rank, x=14)
            p.set_ent(0, MAXHP=200, HP=200)
            g = lambda f, kd: p.rb(S["kind_tab"] + S[f] + kd)  # noqa: E731
            kt = {kd: dict(bh=g("KT_BH", kd), attr=g("KT_ATTR", kd)) for kd in (K_WIZARD, kind)}
            y = B.HERO_Y + kt[K_WIZARD]["bh"] - kt[kind]["bh"]
            p.place(1, 6, y, room=0, flags=EF_ACTIVE | EF_HOSTILE)
            p.set_ent(1, KIND=kind, HP=hp, MAXHP=max(hp, 60), REACT=0)
            p.wb(S["ST_FLAGS"] + 1, stf)
            p.wb(S["ST_T1"] + 1, 0x30 if stf else 0)
            assert effect in (None, 2)             # (Frost r1's own row: freeze 2, always; abil_load owns the row)
            p.settle()
            return p.rb(S["SLOTREC"] + 16 + S["R_ATTR"]), kt[kind]

        def held_ok(acc, ticks, want_attr):
            seq = [acc] + ticks
            bad = []
            for a, b in zip(seq, seq[1:]):
                pending = 0 < a["react"] < 0x80
                if pending and a["flt"] == 0 and b["attr"] != want_attr:
                    bad.append((b["tt"], a["react"], b["attr"]))
            npend = sum(1 for a in seq[:-1] if 0 < a["react"] < 0x80 and a["flt"] == 0)
            return bad, npend

        attr0, kt = tint_scene(SPARK, 1, K_RAT, 1, S["HOLD_FROZEN"])
        hpsh0 = p.rb("PANEL_HP_SH")
        acc, ticks, tgt, ftick = run_turn(p, slot=1)
        gate_checks("T4 Spark kill", acc, ticks, hpsh0, tgt, ftick)
        bad, npend = held_ok(acc, ticks, attr0)
        died = any(t["react"] & 0x80 for t in ticks) and acc["flags"] & EF_DYING
        check(f"T4 frozen Rat killed by a Spark: tint {attr0:#04x} kept while its DEATH is pending"
              f" ({npend} renders), STATUS cleared at the accept",
              attr0 != kt["attr"] and tgt == 1 and died and npend >= 2 and not bad and acc["stf"] == 0,
              (attr0, kt["attr"], tgt, died, npend, bad, acc["stf"]))

        attr0, kt = tint_scene(FROST, 1, K_GOBLIN, 60, 0, effect=0x02)
        hpsh0 = p.rb("PANEL_HP_SH")
        acc, ticks, tgt, ftick = run_turn(p, slot=1)
        check("T5: the freeze line was logged and drained after the gate",
              gate_checks("T5 Frost freeze", acc, ticks, hpsh0, tgt, ftick))
        bad, npend = held_ok(acc, ticks, attr0)
        end = ticks[-1]
        check(f"T5 Frost freezes a Goblin: FROZEN at the accept, kind attr {attr0:#04x} kept while"
              f" the HURT is pending ({npend} renders), then the tint",
              tgt == 1 and acc["stf"] & 3 == S["HOLD_FROZEN"] and npend >= 2 and not bad
              and attr0 == kt["attr"] and end["attr"] != attr0,
              (tgt, acc["stf"], npend, bad, attr0, kt["attr"], end["attr"]))

        # ---- T6: the bound — a long flight caps the gate at the release + CNB_MAX
        p.boot(K_WIZARD, freeze=0)
        p.isolate()
        p.place(0, 24, B.HERO_Y)
        B.lcast_setup(p, [], k=S["ABL_LIGHTNING"], r=3, x=24)
        y = B.HERO_Y + p.rb(S["kind_tab"] + S["KT_BH"] + K_WIZARD) - p.rb(S["kind_tab"] + S["KT_BH"] + K_RAT)
        p.place(1, 1, y, room=0, flags=EF_ACTIVE | EF_HOSTILE)
        p.set_ent(1, KIND=K_RAT, HP=99, MAXHP=99, REACT=0)
        p.settle()
        hpsh0 = p.rb("PANEL_HP_SH")
        acc, ticks, tgt, ftick = run_turn(p)
        check(f"T6 Lightning r3 at a Rat 22 cells away: pf_ftick {ftick} > {GATE_MAX}, gate capped",
              tgt == 1 and ftick > GATE_MAX and acc["cnb"] == GATE_MAX, (tgt, ftick, acc["cnb"]))
        gate_checks("T6 long flight", acc, ticks, hpsh0, tgt, ftick)

        # ---- T6b: the same bound on a long bow flight whose hit logs a line ----
        # (a spell strike logs nothing; "YOUR ARROW HITS THE RAT" is the line the
        # gate must hold back). The hit roll is d20-based: reseed the RNG until
        # the shot lands (deterministic: same boot, same seeds).
        for seed in range(1, 60):
            p.boot(K_KNIGHT, freeze=0)
            p.isolate()
            p.place(0, 3, B.HERO_Y)
            p.place(1, 16, stand_y(1, 2), room=0, flags=EF_ACTIVE | EF_HOSTILE | EF_LEFT)
            p.set_ent(1, KIND=K_RAT, HP=60, MAXHP=60)
            B.acast_setup(p, [(1,)])
            p.wb(S["kind_tab"] + S["KT_EVA"] + K_RAT, 0)
            p.settle()
            p.wb("RNG_STATE", seed & 255)
            p.wb(S["RNG_STATE"] + 1, seed >> 8)
            hpsh0 = p.rb("PANEL_HP_SH")
            acc, ticks, tgt, ftick = run_turn(p)
            if tgt == 1:
                break
        print("T6b seed", seed, tgt, ftick, acc["cnb"], flush=True)
        check(f"T6b bow at a Rat 12 cells away: pf_ftick {ftick} > {GATE_MAX}, gate capped",
              tgt == 1 and ftick > GATE_MAX and acc["cnb"] == GATE_MAX, (tgt, ftick, acc["cnb"]))
        check("T6b: the arrow-hit line was logged and released only after the gate",
              gate_checks("T6b long flight + line", acc, ticks, hpsh0, tgt, ftick))

        print(f"cast_gate: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
