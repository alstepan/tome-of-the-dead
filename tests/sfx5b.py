#!/usr/bin/env python3
"""SND-5b: step / ladder / icon-bar / item-survival effects (src/sfx2.asm mv_sfx, the hero step in
bank7 try_horizontal, try_step's hook in logic.asm, cursor_step, pickup7, ic_quaff / ic_no).
Release build (DEBUG_KIT=0): tools/build.sh -DDEBUG_KIT=0.

Part A (frame-exact ISR, the sfx.py stepper over the Lament):
  A1  STEP (prio 0, id 0<<5|idx) on an idle channel plays its decoded frames
  A2  STEP requested while KILL / MENU / LADDER plays: dropped, the playing effect finishes
      untouched (never cuts, not deferred); a STEP does not displace a pending higher request
  A3  SND_MODE gating of STEP's sfx_req: mode 2 accepted, 0 / 1 and SND_HOLD dropped
  A4  ids: SFX_NO == SFX_FIZZ; EAT exists (prio 3, peak >= 14); all new peaks 14-15
Part B (in play, every sfx_req logged by a patch at its entry: id order = call order):
  B1  the hero's step: one turn right in an empty room -> [STEP]
  B2  three Rats walking at him while he waits: >= 2 move, exactly ONE STEP; hero + monsters
      moving the same turn: one STEP; SND_MODE 0: no request at all from a monster-only turn
  B3  a Goblin mid-ladder (hero waits): [LADDER], no STEP
  B4  icon cursor: ICON_MODE, RIGHT x2 -> two MENU = two moves; the slot table with nothing else
      selectable: no move -> no MENU
  B5  pickup: a potion under the step -> [STEP, PICKUP]; full pack -> [STEP]; a dagger stack ->
      [STEP, PICKUP]; a full quiver -> [STEP]
  B6  quaff -> [QUAFF]; no potion -> [NO]; no daggers / no bow -> [NO]; NO MANA -> [FIZZ]
Run: ZRCP_PORT=<port> python3 tests/sfx5b.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
import game  # noqa: E402
import sfx as SFXT  # noqa: E402
import sfx2asm  # noqa: E402
from sound import Snd, Checks, SND_MODE, DONE, HOLD  # noqa: E402
from game_lib import (Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, K_RAT, K_GOBLIN, stand_y)  # noqa: E402
from proj3 import w16  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
SFX_REQ = S["SFX_REQ"]
EFF = SFXT.EFF
ID = {n: e["id"] for n, e in EFF.items()}
STUB = S["LOWRAM_END_3B"]
RES = STUB + 200                      # log pointer word, then the logged ids
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT = 1, 2, 4, 8
HX = 9
HY = stand_y(1, 6)
FLS = S["FL_STRIDE"]
IROW = 9 + 7


def part_a(h, check):
    s = Snd(h).menu_start(7)
    fx = SFXT.Fx(s)
    step = EFF["STEP"]
    check("A4 ids: SFX_NO == SFX_FIZZ, STEP prio 0, EAT prio 3, reserved ids follow SFX_COUNT (3E-T0)",
          S["SFX_NO"] == S["SFX_FIZZ"] and step["prio"] == 0 and step["id"] == step["idx"]
          and EFF["EAT"]["prio"] == 3 and S["SFX_COUNT"] == len(EFF)
          and S["SFX_IDX_BOSS_ROAR"] == S["SFX_COUNT"] and S["SFX_IDX_BOSS_DEATH"] == S["SFX_COUNT"] + 1
          and S["SFX_IDX_SPARE3F"] == S["SFX_COUNT"] + 2 and S["SFX_COUNT"] + 3 <= 32,
          (S["SFX_NO"], S["SFX_FIZZ"]))
    low = [n for n in ("STEP", "PICKUP", "QUAFF", "EAT")
           if max(f[1] for f in sfx2asm.decode(EFF[n]["data"])) < 14]
    check("A4 new effects peak 14-15", not low and all(
        max(f[1] for f in sfx2asm.decode(EFF[n]["data"])) <= 15 for n in EFF), low)
    # A1
    a_bad, m_bad, fr = fx.play("STEP")
    check("A1 STEP on an idle channel: channel A == its decoded frames, music untouched (prio 0: no duck)",
          a_bad is None and m_bad is None, (a_bad, m_bad))
    fx.play("STEP", n=0)
    s.frames(4)
    # A2: a playing higher effect is never cut by STEP
    res = []
    for name in ("KILL", "MENU", "LADDER", "PICKUP"):
        e = EFF[name]
        frames = sfx2asm.decode(e["data"])
        s.frames(3)
        s.wb(SFX_REQ, e["id"])
        bad = None
        for j in range(len(frames)):
            if j == 1:
                s.wb(SFX_REQ, step["id"])            # mid-effect
            s.frame()
            c = s.chip()
            if bad is None and not fx.a_ok(c, frames[j]):
                bad = j
        s.frame()
        nxt = s.mem(S["SFX_NEXT"], 1)[0]
        res.append((name, bad, nxt, s.mem(SFX_REQ, 1)[0]))
    check("A2 STEP mid KILL / MENU / LADDER / PICKUP: dropped, the effect finishes untouched, nothing deferred",
          all(r[1] is None and r[2] == 0 and r[3] == 0 for r in res), res)
    s.frames(3)
    # a STEP does not displace a pending higher request (same frame): sfx_req order
    r = SFXT.regs(s.z)
    SFXT.call_at_done(s, S["sfx_req"], a=ID["HIT"])
    SFXT.call_at_done(s, S["sfx_req"], a=step["id"])
    pend = s.mem(SFX_REQ, 1)[0]
    check("A2 a later STEP does not replace a pending HIT", pend == ID["HIT"], hex(pend))
    s.wb(SFX_REQ, 0)
    # A3 gating
    out = []
    for mode, want in ((3, step["id"]), (2, step["id"]), (1, 0), (0, 0), (3 | HOLD, 0), (2 | HOLD, 0)):
        s.wb(SFX_REQ, 0)
        s.wb(SND_MODE, mode)
        SFXT.call_at_done(s, S["sfx_req"], a=step["id"])
        out.append((mode, s.mem(SFX_REQ, 1)[0] == want))
    s.wb(SFX_REQ, 0)
    s.wb(SND_MODE, 3)
    check("A3 STEP via sfx_req: modes 3 / 2 accepted, 1 / 0 and SND_HOLD dropped", all(o[1] for o in out), out)


def install_log(p):
    """Patch sfx_req's first 3 bytes (push af / push bc / ld b,a) into JP stub; the stub appends A to
    the log at RES and runs them."""
    base = S["sfx_req"]
    orig = list(p.z.read_memory(base, 3))
    assert orig == [0xF5, 0xC5, 0x47], orig
    code = [0xE5, 0xF5, 0x2A] + w16(RES) + [0x77, 0x23, 0x22] + w16(RES) + [0xF1, 0xE1,
            0xF5, 0xC5, 0x47, 0xC3] + w16(base + 3)
    p.wmem(STUB, code)
    p.wmem(base, [0xC3] + w16(STUB))
    clear_log(p)


def clear_log(p):
    p.wmem(RES, w16(RES + 2))


def log(p):
    end = p.rb(RES) | p.rb(RES + 1) << 8
    return list(p.z.read_memory(RES + 2, end - RES - 2)) if end > RES + 2 else []


class GT(game.T):
    def wmem(self, addr, data):
        self.z.cmd("write-memory %d %s" % (addr, " ".join(str(b) for b in data)))

    def kinds(self):
        kt = {}
        for k in range(9):
            g = lambda f: self.rb(S["kind_tab"] + S[f] + k)  # noqa: E731
            kt[k] = dict(bw=g("KT_BW"), bh=g("KT_BH"))
        return kt


def part_b(h, check):
    p = GT(h)
    kt = {}
    slots = {}

    def scene(mons=(), cls=K_KNIGHT, hero=(HX, HY)):
        p.boot(cls)
        if not kt:
            kt.update(p.kinds())
        if not slots:
            for sl in range(1, 16):
                slots.setdefault(p.ent(sl)["KIND"], sl)
        p.isolate()
        p.set_ent(0, X=hero[0], Y=hero[1], PX=hero[0] * 8, PY=hero[1] * 8, MODE=0, HP=200, MAXHP=200,
                  ROOM=p.rb("CUR_ROOM"), FLAGS=EF_ACTIVE | EF_PLAYER)
        for sl, (kind, x) in enumerate(mons, 1):
            y = HY + kt[cls]["bh"] - kt[kind]["bh"]
            p.set_ent(sl, KIND=kind, X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=p.rb("CUR_ROOM"),
                      FLAGS=EF_ACTIVE | EF_HOSTILE | EF_LEFT, HP=60, MAXHP=60, REACT=0, FLT=0, HIT=0)
        p.wmem(S["ST_FLAGS"], [0] * 16)
        p.wmem(S["ST_T1"], [0] * 16)
        p.tick(3)
        install_log(p)

    # B1
    scene()
    p.turn("L")
    check("B1 the hero's step: [STEP]", log(p) == [ID["STEP"]], log(p))
    # B2
    scene([(K_RAT, 16), (K_RAT, 20), (K_RAT, 24)])
    xs0 = [p.ent(sl)["X"] for sl in range(1, 16) if p.ent(sl)["FLAGS"] & EF_HOSTILE and p.ent(sl)["ROOM"] == p.rb("CUR_ROOM")]
    clear_log(p)
    p.turn("WAIT")
    xs1 = [p.ent(sl)["X"] for sl in range(1, 16) if p.ent(sl)["FLAGS"] & EF_HOSTILE and p.ent(sl)["ROOM"] == p.rb("CUR_ROOM")]
    moved = sum(a != b for a, b in zip(xs0, xs1))
    check("B2 monsters only: >= 2 moved, exactly one STEP", moved >= 2 and log(p) == [ID["STEP"]], (moved, log(p)))
    clear_log(p)
    p.turn("H")
    xs2 = [p.ent(sl)["X"] for sl in range(1, 16) if p.ent(sl)["FLAGS"] & EF_HOSTILE and p.ent(sl)["ROOM"] == p.rb("CUR_ROOM")]
    check("B2 hero + monsters moving the same turn: one STEP",
          sum(a != b for a, b in zip(xs1, xs2)) >= 2 and log(p) == [ID["STEP"]], log(p))
    p.wb("SND_MODE", 0)
    clear_log(p)
    p.turn("WAIT")
    check("B2 SND_MODE 0: a monster-only turn makes no request", log(p) == [], log(p))
    p.wb("SND_MODE", 3)
    # B3
    scene()
    G1, Y0 = stand_y(1, 4), stand_y(0, 6)
    p.place(0, 5, Y0)
    p.place(game.SLOT_GOBLIN, 5, G1 - 1, room=0, flags=EF_ACTIVE | EF_HOSTILE)
    p.set_ent(game.SLOT_GOBLIN, AIDIR=0xFF)
    p.settle()
    clear_log(p)
    y0 = p.ent(game.SLOT_GOBLIN)["Y"]
    p.turn("WAIT")
    check("B3 a Goblin climbing: [LADDER] (and it moved)",
          log(p) == [ID["LADDER"]] and p.ent(game.SLOT_GOBLIN)["Y"] != y0, (log(p), y0, p.ent(game.SLOT_GOBLIN)["Y"]))
    # B4
    scene()
    p.wb("ICON_MODE", 1)
    p.tick(2)
    clear_log(p)
    s0 = p.rb("SEL_SLOT")
    p.tap("L", n=2)                                   # RIGHT (the keyboard alias of the stick)
    p.tap("L", n=2)
    s1 = p.rb("SEL_SLOT")
    check("B4 ICON MODE RIGHT x2: moved, two MENU", s1 != s0 and log(p) == [ID["MENU"]] * (len(log(p))) and len(log(p)) >= 1,
          (s0, s1, log(p)))
    n_mv = len(log(p))
    # the only selectable slot: the table with every other slot SA_EMPTY
    tab = S["slot_act_tab"]
    saved = list(p.z.read_memory(tab, 20))
    p.wmem(tab, [saved[0]] + [0] * 9 + [saved[10]] + [0] * 9)
    p.wb("SEL_SLOT", 0)
    clear_log(p)
    p.tap("L", n=2)
    p.tap("H", n=2)
    check("B4 nothing else selectable: the cursor stays, no MENU", p.rb("SEL_SLOT") == 0 and log(p) == [],
          (p.rb("SEL_SLOT"), log(p), n_mv))
    p.wmem(tab, saved)
    # B5 pickup
    def free_entry():
        for i in range(S["FLOOR_MAX"]):
            if p.rb(S["FLOOR_LIST"] + i * FLS) == S["FL_EMPTY"]:
                return i
        raise AssertionError

    def put(i, col, item, qty, tile):
        p.wmem(S["FLOOR_LIST"] + i * FLS, [p.rb("CUR_ROOM") | S["FL_S1"], col, item, qty])
        p.wb(S["ROOM_MAP"] + IROW * 32 + col, tile)

    col = HX + 3
    scene()
    put(free_entry(), col, S["IT_POTION"], 0, S["T_POTION"])
    p.set_ent(0, POT=0)
    p.turn("L")
    check("B5 potion: [STEP, PICKUP], pack 1", log(p) == [ID["STEP"], ID["PICKUP"]] and p.ent(0)["POT"] == 1,
          (log(p), p.ent(0)["POT"]))
    scene()
    put(free_entry(), col, S["IT_POTION"], 0, S["T_POTION"])
    p.set_ent(0, POT=S["MAX_POTIONS"])
    p.turn("L")
    check("B5 full pack: the potion stays, no PICKUP", log(p) == [ID["STEP"]], log(p))
    scene()
    put(free_entry(), col, S["IT_DAGGER"], 3, S["T_DAGGERS"])
    p.wb("DAGGERS", 3)
    p.turn("L")
    check("B5 dagger stack: [STEP, PICKUP]", log(p) == [ID["STEP"], ID["PICKUP"]] and p.rb("DAGGERS") == 6, (log(p), p.rb("DAGGERS")))
    scene()
    put(free_entry(), col, S["IT_ARROW"], 5, S["T_ARROWS"])
    p.wb("ARROWS", 24)
    p.turn("L")
    check("B5 full quiver: nothing taken, no PICKUP", log(p) == [ID["STEP"]] and p.rb("ARROWS") == 24, (log(p), p.rb("ARROWS")))
    # B6
    scene()
    p.set_ent(0, HP=50, POT=2)
    p.turn("G")
    check("B6 quaff: [QUAFF], potion spent", log(p) == [ID["QUAFF"]] and p.ent(0)["POT"] == 1, (log(p), p.ent(0)["POT"]))
    scene()
    p.set_ent(0, HP=50, POT=0)
    nt = p.no_turn("G")
    check("B6 no potion: [NO] (= FIZZ id), no turn", nt and log(p) == [ID["FIZZ"]] and S["SFX_NO"] == ID["FIZZ"], (nt, log(p)))
    scene()
    p.wb("DAGGERS", 0)
    p.select_slot(3)
    clear_log(p)
    nt = p.no_turn("FIRE")
    check("B6 no daggers: [NO]", nt and log(p) == [S["SFX_NO"]], (nt, log(p)))
    scene()
    p.wb("HAS_BOW", 0)
    p.select_slot(4)
    clear_log(p)
    nt = p.no_turn("FIRE")
    check("B6 no bow: [NO]", nt and log(p) == [S["SFX_NO"]], (nt, log(p)))
    scene()
    tab = S["slot_act_tab"]
    fs = [i for i in range(10) if p.rb(tab + i) == S["SA_FOOD"]]
    p.select_slot(fs[0])
    clear_log(p)
    nt = p.no_turn("FIRE")
    check("B6 no food: [NO]", nt and log(p) == [S["SFX_NO"]], (fs, nt, log(p)))
    scene()
    p.wb("ARANK", 0x0F)
    p.wb("MP", 0)
    p.select_slot(1)
    clear_log(p)
    nt = p.no_turn("FIRE")
    check("B6 NO MANA (Power Strike, MP 0): [FIZZ]", nt and log(p) == [ID["FIZZ"]], (nt, log(p), p.rb("MP")))


def main():
    Checks.n = 0
    Checks.bad = []
    with Harness() as h:
        h.launch(EMU_ARGS)

        def check(tag, cond, detail=""):
            Checks.check(tag, cond, detail)

        if KIT:
            print("[skip] sfx5b needs a DEBUG_KIT=0 build", flush=True)
        else:
            part_a(h, check)
            part_b(h, check)
    print(f"sfx5b: {'FAIL' if Checks.bad else 'PASS'} ({Checks.n - len(Checks.bad)}/{Checks.n} checks passed)"
          + (": " + ", ".join(Checks.bad) if Checks.bad else ""), flush=True)
    return 1 if Checks.bad else 0


if __name__ == "__main__":
    sys.exit(main())
