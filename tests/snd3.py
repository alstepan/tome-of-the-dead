#!/usr/bin/env python3
"""SND-3: music event cues that exist today (sound.md S1f; src/mus7.asm, end_turn).
Release build (DEBUG_KIT=0), PROTO room A.

  Y   hero death (a real end_turn): MUS_REQ 0 + MUS_SHOT 6 (Game Over), plays ONCE
      (one MS_SHOT edge over the end screen's redraws), MUS_SHOT consumed, loop stays 0
  W   mus_pick (far7): >= 4 awake hostiles in CUR_ROOM -> MUS_REQ 2 at exactly 4 (3 no);
      asleep / pending / dying / other-room bodies do not count; HP <= MAXHP/4 at exactly
      25 % (MAXHP 20: HP 5 yes, 6 no; MAXHP 21: HP 5 yes, 6 no)
  H   hysteresis: leaves at turn 16 of a calm run (>= 8 calm AND >= 16 dwell), never before;
      returns to MUS_ROOM (7); a seeded hover at the threshold == the Python model
      (300 turns, no W interval shorter than 16 turns, no exit with calm run < 8)
  M   music off (SND_MODE 2): the cue changes in the mailbox anyway (state consistent),
      nothing sounds; music on -> the current request sounds (MUS_CUR)
  R   a new level/game (level_enter) resets W (DNG_DWELL 0, MUS_REQ 7)
  C   cost of mus_pick (far7 incl. paging)
Run: ZRCP_PORT=<port> python3 tests/snd3.py
"""
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_GOBLIN, stand_y, RUN_LIMIT, GS_DEAD  # noqa: E402
from proj3 import T, w16  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT = 1, 2, 4, 8
EF_DYING, EF_PENDING = S["EF_DYING"], S["EF_PENDING"]
HY = stand_y(1, 6)
HX = 12
NOWHERE = 7
STUB = S["LOWRAM_END_3B"]
RES = STUB + 200
MUS_ROOM, MUS_DANGER, MUS_OVER = 7, 2, 6
DWELL, CALM = S["DNG_DWELL"], S["DNG_CALM"]
MUS_REQ, MUS_SHOT, MUS_STATE, MUS_CUR = (S[n] for n in ("MUS_REQ", "MUS_SHOT", "MUS_STATE", "MUS_CUR"))


def model(state, cond):
    """The spec, independently: state = [dwell, calm]; returns the new MUS_REQ or None."""
    if state[0] == 0:
        if cond:
            state[:] = [1, 0]
            return MUS_DANGER
        return None
    state[0] = min(255, state[0] + 1)
    if cond:
        state[1] = 0
        return None
    state[1] += 1
    if state[1] >= 8 and state[0] >= 16:
        state[:] = [0, 0]
        return MUS_ROOM
    return None


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)
        n = [0]

        def check(tag, cond, detail=""):
            n[0] += 1
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:600]}", flush=True)

        if KIT:
            print("[skip] snd3 needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(h, p, check)
        print(f"snd3: {len(fails)} failed of {n[0]}"
              + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def run(h, p, check):
    WT = S["wait_tick"]
    slots = {}

    def run_to_probe():
        for _ in range(200):
            p.z.cmd("run %d" % RUN_LIMIT)
            if p.pc() in p.probes:
                return
        raise RuntimeError("no probe")

    def stub(body):
        assert p.pc() == WT, hex(p.pc())
        p.wmem(STUB, body + [0xC3] + w16(WT))
        p.z.cmd("set-register PC=%d" % STUB)
        run_to_probe()
        assert p.pc() == WT, "stub did not return"

    def pick():
        stub([0xCD] + w16(S["build_live"]) + [0x21] + w16(S["mus_pick"]) + [0xCD] + w16(S["far7"]))

    def place(slot, flags, hp=5, room=None):
        p.set_ent(slot, X=HX + 12, Y=HY, PX=(HX + 12) * 8, PY=HY * 8, MODE=0,
                  ROOM=p.rb("CUR_ROOM") if room is None else room, FLAGS=flags, REACT=0,
                  FLT=0, HIT=0, HP=hp, MAXHP=hp)

    def scene(hp=40, maxhp=40):
        p.boot(K_KNIGHT)
        room = p.rb("CUR_ROOM")
        for sl in range(1, 16):
            e = p.ent(sl)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                p.set_ent(sl, ROOM=NOWHERE)
        p.set_ent(0, X=HX, Y=HY, PX=HX * 8, PY=HY * 8, MODE=0, ROOM=room, FLAGS=EF_ACTIVE | EF_PLAYER,
                  REACT=0, FLT=0, HIT=0, HP=hp, MAXHP=maxhp)
        p.wmem(S["ST_FLAGS"], [0] * 16)
        p.tick(3)

    HOST = EF_ACTIVE | EF_HOSTILE
    n_hosts = lambda n: [place(sl, HOST, 5) for sl in range(1, n + 1)]  # noqa: E731

    def req():
        return p.rb("MUS_REQ")

    # ---- W: monster count ---------------------------------------------------
    scene()
    check("R0 boot: MUS_REQ = room tune 7, DNG_DWELL 0", req() == MUS_ROOM and p.rb(DWELL) == 0)
    n_hosts(3)
    pick()
    check("W1 3 awake hostiles: no Dangerous", req() == MUS_ROOM and p.rb(DWELL) == 0)
    place(4, HOST)
    pick()
    check("W2 the 4th awake hostile: MUS_REQ 2, dwell 1, calm 0",
          req() == MUS_DANGER and p.rb(DWELL) == 1 and p.rb(CALM) == 0, (req(), p.rb(DWELL)))
    # not counted: asleep / pending / dying / another room
    for what, fl, room in (("asleep", None, None), ("pending", HOST | EF_PENDING, None),
                           ("dying", HOST | EF_DYING, None), ("other room", HOST, NOWHERE)):
        scene()
        n_hosts(3)
        if what == "asleep":
            place(4, HOST)
            p.wb(S["ST_FLAGS"] + 4, S["HOLD_ASLEEP"])
        else:
            place(4, fl, room=room)
        pick()
        check(f"W3 {what} body is not counted (3 awake + it)", req() == MUS_ROOM and p.rb(DWELL) == 0)
    scene()
    n_hosts(4)
    p.wb(S["ST_FLAGS"] + 4, S["HOLD_FROZEN"])
    pick()
    check("W4 a frozen (awake) hostile counts", req() == MUS_DANGER)
    # ---- W: HP ---------------------------------------------------------------
    for mx, hp, want in ((20, 6, False), (20, 5, True), (21, 6, False), (21, 5, True), (40, 10, True),
                         (40, 11, False), (3, 1, False)):
        scene(hp=hp, maxhp=mx)
        pick()
        check(f"W5 HP {hp}/{mx} -> {'W' if want else 'room'}", (req() == MUS_DANGER) == want, req())

    # ---- H: hysteresis ----------------------------------------------------------
    scene()
    n_hosts(4)
    pick()                                   # turn 1: enter
    place(4, 0)                              # calm from turn 2
    seen = []
    for t in range(2, 20):
        pick()
        seen.append((t, req()))
    off_at = next((t for t, r in seen if r == MUS_ROOM), None)
    check("H1 calm run: stays W until turn 16 (dwell 16, calm 15), then the room tune",
          off_at == 16 and all(r == MUS_DANGER for t, r in seen if t < 16), seen)
    check("H2 left: state reset", p.rb(DWELL) == 0 and p.rb(CALM) == 0)
    # a late entry: dwell 20, calm run 7 then the condition returns -> calm restarts
    scene()
    n_hosts(4)
    pick()
    for _ in range(25):
        pick()                               # dwell 26, still on (cond)
    place(4, 0)
    for _ in range(7):
        pick()
    stay = req() == MUS_DANGER
    place(4, HOST)
    pick()
    check("H3 7 calm turns then the condition: still W, calm reset", stay and req() == MUS_DANGER and p.rb(CALM) == 0)
    place(4, 0)
    for _ in range(7):
        pick()
    stay = req() == MUS_DANGER
    pick()
    check("H4 8th calm turn (dwell >= 16) leaves", stay and req() == MUS_ROOM)
    # seeded hover at the threshold (3 <-> 4 hostiles) vs the model
    rnd = random.Random(0x5EED)
    PCOND = 0.12
    scene()
    n_hosts(3)
    st = [0, 0]
    bad, ons, run_len, cur_on, flips = [], [], 0, False, 0
    on_state = False
    prev = MUS_ROOM
    for t in range(300):
        cond = rnd.random() < PCOND
        place(4, HOST if cond else 0)
        want = model(st, cond)
        pick()
        got = req()
        exp = want if want is not None else prev
        if got != exp:
            bad.append((t, cond, got, exp))
            break
        if got != prev:
            flips += 1
            if got == MUS_ROOM:
                ons.append(run_len)
        if got == MUS_DANGER:
            run_len = run_len + 1 if prev == MUS_DANGER else 1
        prev = got
    check("H5 seeded hover (300 turns, p=0.12) == model", not bad, bad)
    check(f"H6 no flapping: every closed W interval >= 15 W turns + the leaving turn ({flips} switches, intervals {ons})",
          all(r >= 15 for r in ons) and len(ons) >= 2, ons)

    # ---- M: music off / on -------------------------------------------------------
    scene()
    n_hosts(3)
    p.tick(2)
    p.wb("SND_MODE", 2)                      # SFX only: music off
    p.tick(3)
    place(4, HOST)
    pick()
    p.tick(3)
    check("M1 music off: the request changes (W), nothing sounds", req() == MUS_DANGER and p.rb(MUS_CUR) == 0
          and p.rb(MUS_STATE) & 3 == 0, (req(), p.rb(MUS_CUR)))
    place(4, 0)
    for _ in range(16):
        pick()
    check("M2 music off: leaves W after the dwell, request = room tune", req() == MUS_ROOM and p.rb(DWELL) == 0)
    place(4, HOST)
    pick()
    p.wb("SND_MODE", 3)
    p.tick(4)
    check("M3 music on while W: the Dangerous tune sounds", p.rb(MUS_CUR) == MUS_DANGER, p.rb(MUS_CUR))
    p.wb("SND_MODE", 2)
    place(4, 0)
    for _ in range(20):
        pick()
    p.wb("SND_MODE", 3)
    p.tick(4)
    check("M4 left W while off, music on: the room tune sounds", req() == MUS_ROOM and p.rb(MUS_CUR) == MUS_ROOM,
          p.rb(MUS_CUR))

    # ---- R: reset on a new game -----------------------------------------------------
    scene()
    n_hosts(4)
    pick()
    on = req() == MUS_DANGER
    h.write_byte(S["GAME_STATE"], S["GS_PLAYING"])
    p.boot(K_KNIGHT)                         # menu -> start_game -> level_enter
    check("R1 a new game resets W: DNG 0/0, MUS_REQ 7", on and p.rb(DWELL) == 0 and p.rb(CALM) == 0 and req() == MUS_ROOM)

    # ---- Y: death ---------------------------------------------------------------------
    scene(hp=1, maxhp=40)
    p.wb("MUS_SHOT", 0)
    shots = edges = 0
    p.set_ent(0, FLAGS=EF_ACTIVE | EF_PLAYER | EF_DYING, HP=0)
    stub([0x21] + w16(S["end_turn"]) + [0xCD] + w16(S["far7"]))     # the real end_turn
    p.tick(1)
    died = p.rb("GAME_STATE") == GS_DEAD
    check("Y0 end_turn with a DYING hero: GS_DEAD", died)
    if died:
        prev_st = 0
        seen_cur = set()
        for _ in range(150):
            p.tick()
            st = p.rb(MUS_STATE) & 3
            if st == 2 and prev_st != 2:
                edges += 1
            prev_st = st
            seen_cur.add(p.rb(MUS_CUR))
        check("Y1 Game Over cue: loop off (MUS_REQ 0), shot consumed", req() == 0 and p.rb(MUS_SHOT) == 0
              and MUS_OVER in seen_cur, (req(), p.rb(MUS_SHOT), seen_cur))
        check(f"Y2 plays once over the end screen ({edges} MS_SHOT edge(s))", edges == 1, edges)
    # ---- G: no cue change after a win; music-off death ------------------------------------
    scene()
    n_hosts(4)
    p.wb("MUS_REQ", 0)
    p.wb("GAME_STATE", S["GS_WIN"])
    stub([0xCD] + w16(S["build_live"]) + [0x21] + w16(S["end_turn"]) + [0xCD] + w16(S["far7"]))
    check("G1 end_turn after GS_WIN: mus_pick does not touch MUS_REQ", req() == 0 and p.rb(DWELL) == 0, (req(), p.rb(DWELL)))
    scene(hp=1, maxhp=40)
    p.wb("SND_MODE", 2)
    p.tick(2)
    p.set_ent(0, FLAGS=EF_ACTIVE | EF_PLAYER | EF_DYING, HP=0)
    stub([0x21] + w16(S["end_turn"]) + [0xCD] + w16(S["far7"]))
    p.tick(10)
    check("G2 music-off death: GS_DEAD, MUS_SHOT consumed, nothing sounds",
          p.rb("GAME_STATE") == GS_DEAD and p.rb(MUS_SHOT) == 0 and p.rb(MUS_CUR) == 0 and p.rb(MUS_STATE) & 3 == 0,
          (p.rb(MUS_SHOT), p.rb(MUS_CUR), p.rb(MUS_STATE)))
    # ---- C: cost -----------------------------------------------------------------------
    scene()
    n_hosts(2)                                   # no early out: full scan + the HP test
    p.wmem(RES + 100, [0xC9])
    ok0 = p.code([0xCD] + w16(S["build_live"]) + [0x21] + w16(RES + 100) + [0xCD] + w16(S["far7"]))
    t0 = p.tstates
    scene()
    n_hosts(2)                                   # no early out: full scan + the HP test
    ok = p.code([0xCD] + w16(S["build_live"]) + [0x21] + w16(S["mus_pick"]) + [0xCD] + w16(S["far7"]))
    t_full = p.tstates - t0
    check(f"C1 mus_pick full scan (far7 paging subtracted): {t_full} T (< 1,500)", ok and ok0 and t_full < 1500, t_full)
    print(f"[info] mus_pick full scan {t_full} T excl. far7", flush=True)


if __name__ == "__main__":
    sys.exit(main())
