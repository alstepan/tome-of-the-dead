#!/usr/bin/env python3
"""3F-T9 mid-room spawns (game.md §9.6 Rabbit Rat breed / Bone Caller summon, §1.5 ALARM wave,
plan.md PHARAOH ABILITY): the producers fill the 1-entry spawn queue (SPQ_*), end_turn's R6
sp_run makes the bodies (src/spawn6.asm). Seeded generated games (the real level_descend).

  R  Rabbit Rat (D1): the hero hits it (hp 99) until it breeds: exactly one base Rat, summon-made
     (E_RCD bit 6) + F_RESPAWN, standing beside it, depth-scaled hp; the Rabbit's once bit
     (E_RCD bit 7) set; it never breeds again (15 more hits); lp_bank: the Rat is discarded, the
     Rabbit's record entry carries LEK_BRED; lp_enter restores the once bit
  B  Bone Caller (D6, no Skeleton in LP_KINDS -> a Ghost): the first in-line turn summons ("THE
     SUMMONER SUMMONS!", S = 8), the Ghost in its cruise row beside the caster; <= 1 live summon
     (10 more turns: none); the summon dead -> the next S = 0 turn summons again; lp_bank drops it
  C  the cap: Bone Caller + 3 Skeletons (4 monsters) -> no summon, S stays 0, the queue empty
  P  Golden Pharaoh (D5 lair): with its escort (Σ >= 9 + 5 > 12) no summon; escort gone -> 1
     minion (Skeleton / Mummy, summon-made) beside it, S = 8; PH_LIVE 1: one at a time; leaving
     the lair discards it (record = the boss); P6: the minion killed on a re-summon turn -> the new one
     takes its freed slot, no corpse frame at the top-left (fix/d8-corpse-topleft)
  A  ALARM (D5, boss alive): "AN ALARM BELL RINGS!", 1-2 bodies of LP_KINDS PENDING at a door
     (F_RESPAWN, not summon-made), walked in after the next turns; boss dead (LF_UNIQUE): the bell
     line and nothing
  N  sp_try with a parent at x = 2: a negative candidate x ($FF + width wraps) is refused, a legal col is not
  X  sp_run on an exit turn (EXIT_KIND) / a dying hero: the queue is emptied, nothing made
  T  costs: sp_run (far6 incl.) for a summon / an offspring / a 2-body wave
Build with -DDEBUG_KIT=0. ZRCP_PORT=<port> python3 tests/spawn.py
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, stand_y, RUN_LIMIT  # noqa: E402
from lp import T, w16, RES  # noqa: E402
from boss import Lair, boss_slot, rec_entries  # noqa: E402
from abil_melee import stream_text  # noqa: E402

STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_HOSTILE, EF_PENDING, EF_RESPAWN = 1, 4, S["EF_PENDING"], S["EF_RESPAWN"]
EF_DYING, EF_LEFT = S["EF_DYING"], S["EF_LEFT"]
K = {n: S["K_" + n] for n in ("RAT", "RABBIT_RAT", "BONE_CALLER", "SKELETON", "GHOST", "MUMMY")}
SUMM, ONCE = 0x40, 0x80
fails = []


def check(name, ok, got=None):
    if not ok:
        fails.append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f": got {got}"), flush=True)


class Lines:
    """log_push capture (breakpoint 5), as tests/t16.py: every pushed line in order."""
    def __init__(self, p):
        self.p, self.z, self.lines = p, p.z, []
        self.logp = S["log_push"]

        def tick(n=1):
            for _ in range(n):
                self.z.cmd("cpu-step")
                self._run()
        p.tick = tick

    def arm(self):
        self.z.cmd("set-breakpoint 5 PC=%d" % self.logp)
        self.lines.clear()

    def _run(self):
        p, z = self.p, self.z
        for _ in range(4000):
            z.cmd("run %d" % RUN_LIMIT)
            pc = p.pc()
            if pc == self.logp:
                regs = z.cmd("get-registers")
                hl = int(re.search(r"HL=([0-9a-fA-F]{4})", regs).group(1), 16)
                self.lines.append(stream_text(z.read_memory(hl, 48)).rstrip("."))
                z.cmd("cpu-step")
                continue
            if pc in p.probes:
                return
            raise RuntimeError(f"stopped at {pc:#06x}")


def kt(p, k, off):
    return p.rb(S["kind_tab"] + S[off] + k)


def eb(p, sl, off):
    return p.rb(S["P_ENTITIES"] + sl * STRIDE + S[off])


def heal(p):
    p.set_ent(0, HP=250, MAXHP=250)
    p.wmem(S["ST_FLAGS"], [0])
    p.wmem(S["ST_T1"], [0])
    p.wmem(S["ST_T2"], [0])
    p.wmem(S["ST_X"], [0])


def good_cols(p, s_):
    """Cols where a walker may stand on storey s_ (sp_try's terrain rule)."""
    tf = p.z.read_memory(S["tile_flags"], 64)
    m = p.z.read_memory(S["ROOM_MAP"], 576)
    fr, sr = 9 * s_ + 8, 9 * s_ + 7
    ok = []
    for c in range(32):
        f, st = tf[m[fr * 32 + c]], tf[m[sr * 32 + c]]
        ok.append(bool(f & 0x80) and not f & 0x18 and not st & 0x0B)
    return ok


def run_of(p, need):
    """(storey, first col) of a run of >= need standable cols inside 2..29, or None."""
    for s_ in (1, 0):
        ok = good_cols(p, s_)
        n = 0
        for c in range(2, 30):
            n = n + 1 if ok[c] else 0
            if n >= need:
                return s_, c - need + 1
    return None


def clear_room(p):
    for sl in range(1, 16):
        p.set_ent(sl, FLAGS=0)
    p.wb("SPQ_K", 0)


def mon(p, sl, k, x, s_, hp=30, pot=0, flags=0):
    h = kt(p, k, "KT_BH")
    y = 9 * s_ + 1 if kt(p, k, "KT_FLAGS") & 1 else stand_y(s_, h)
    p.set_ent(sl, KIND=k, ROOM=p.rb("CUR_ROOM"), X=x, Y=y, PX=x * 8, PY=y * 8, HP=hp, MAXHP=hp, POT=pot,
              FLAGS=EF_ACTIVE | EF_HOSTILE | flags, MODE=0, REACT=0, FLT=0, DVIS=0)
    p.wb(S["P_ENTITIES"] + sl * STRIDE + S["E_GOLD"], 0)
    for a in ("ST_FLAGS", "ST_T1", "ST_T2", "ST_X"):
        p.wb(S[a] + sl, 0)


def hero_at(p, x, s_, left=False):
    h = kt(p, p.rb("HERO_KIND"), "KT_BH")
    p.set_ent(0, X=x, Y=stand_y(s_, h), PX=x * 8, PY=stand_y(s_, h) * 8, MODE=0, REACT=0, FLT=0,
              FLAGS=EF_ACTIVE | 2 | (EF_LEFT if left else 0))


def room_slots(p):
    r = p.rb("CUR_ROOM")
    return [s_ for s_ in range(1, 16) if p.ent(s_)["FLAGS"] & EF_ACTIVE and p.ent(s_)["ROOM"] == r]


def new_slots(p, before):
    return [s_ for s_ in room_slots(p) if s_ not in before]


def keep_pc(fn):
    """T.code / T.far3 leave PC on the stub's end loop: put the game's PC back after."""
    def w(p, *a, **kw):
        pc0 = p.pc()
        try:
            return fn(p, *a, **kw)
        finally:
            p.z.cmd("set-register PC=%d" % pc0)
    return w


@keep_pc
def far6(p, target):
    return p.code([0x21] + w16(S[target]) + [0xCD] + w16(S["far6"]), game=True)


@keep_pc
def far3(p, target, a=None, e=None):
    body = ([0x3E, a] if a is not None else []) + ([0x1E, e] if e is not None else [])
    return p.code(body + [0x21] + w16(S[target]) + [0xCD] + w16(S["far3"]), game=True)   # (the game's SP, EI)


@keep_pc
def code(p, body):
    return p.code(body, game=True)


def stands_on_floor(p, sl):
    e = p.ent(sl)
    k = e["KIND"]
    w, h = kt(p, k, "KT_BW"), kt(p, k, "KT_BH")
    if e["Y"] + h not in (8, 17):
        return False
    ok = good_cols(p, 0 if e["Y"] + h == 8 else 1)
    return all(ok[c] for c in range(e["X"], e["X"] + w))


def main():
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)
        lines = Lines(p)
        rabbit(p, lines)
        bone_caller(p, lines)
        pharaoh(p, lines)
        alarm(p, lines)
        bounds(p, lines)
        exits(p, lines)
    print(f"spawn: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
    return 1 if fails else 0


def level(p, lines, depth, seed, need=16):
    for k in range(6):
        L = Lair(p, depth, seed + k)
        lines.arm()
        if not L.ok:
            continue
        r = run_of(p, need)
        if r:
            return L, r
    return None, None


# ---------------------------------------------------------------------------- R
def rabbit(p, lines):
    L, r = level(p, lines, 1, 0x7101)
    check("R setup: D1 + a standable run on a storey", L is not None, r)
    if not L:
        return
    s_, c0 = r
    clear_room(p)
    hero_at(p, c0 + 2, s_)
    hw = kt(p, p.rb("HERO_KIND"), "KT_BW")
    rx = c0 + 2 + hw
    mon(p, 1, K["RABBIT_RAT"], rx, s_, hp=99)
    heal(p)
    rat, turns = None, 0
    for turns in range(1, 61):
        heal(p)
        p.set_ent(1, HP=99, X=rx, PX=rx * 8)
        before = room_slots(p)
        p.turn("L")
        ns = new_slots(p, before)
        if ns:
            rat = ns[0]
            break
    check(f"R1 the Rabbit Rat bred within {turns} hits", rat is not None, turns)
    if rat is None:
        return
    e = p.ent(rat)
    hp_want = kt(p, K["RAT"], "KT_HP") + p.rb("LVL_DEPTH") - 1
    rw = kt(p, K["RAT"], "KT_BW")
    check("R2 one base Rat: summon-made (E_RCD bit 6) + F_RESPAWN, depth-scaled hp, not PENDING",
          e["KIND"] == K["RAT"] and e["POT"] & SUMM and e["FLAGS"] & EF_RESPAWN and not e["FLAGS"] & EF_PENDING
          and e["MAXHP"] == hp_want, e)
    rb_ = p.ent(1)
    check("R3 beside the Rabbit (<= SP_R cols off), standing on a floor cell, no body overlap",
          (e["X"] >= rb_["X"] + 2 and e["X"] - (rb_["X"] + 2) < S["SP_R"]
           or e["X"] + rw <= rb_["X"] and rb_["X"] - (e["X"] + rw) < S["SP_R"]) and stands_on_floor(p, rat), (e, rb_))
    check("R4 the Rabbit's once bit (E_RCD bit 7) set, the queue empty",
          rb_["POT"] & ONCE and p.rb("SPQ_K") == 0, (rb_["POT"], p.rb("SPQ_K")))
    p.set_ent(rat, FLAGS=0)
    more = 0
    for _ in range(15):
        heal(p)
        p.set_ent(1, HP=99, X=rx, PX=rx * 8)
        before = room_slots(p)
        p.turn("L")
        more += len(new_slots(p, before))
    check("R5 never breeds again (15 more hits)", more == 0, more)
    # bank: a fresh offspring (poked) is discarded, the Rabbit's entry carries LEK_BRED
    mon(p, 2, K["RAT"], 2, s_, hp=5, pot=SUMM)
    room = p.rb("CUR_ROOM")
    far3(p, "lp_bank", a=room, e=0)
    ents, hdr = rec_entries(p, room)
    check("R6 lp_bank: the summon-made Rat discarded, the Rabbit banked with LEK_BRED (bit 6)",
          ents == [(K["RABBIT_RAT"] | 0x40, 99)] or (len(ents) == 1 and ents[0][0] == K["RABBIT_RAT"] | 0x40),
          ents)
    p.wmem(S["LP_HX"], [2, s_ ^ 1, hw])
    far3(p, "lp_enter", a=room)
    got = [s2 for s2 in room_slots(p) if p.ent(s2)["KIND"] == K["RABBIT_RAT"]]
    check("R7 lp_enter: the Rabbit back with its once bit (E_RCD bit 7)",
          len(got) == 1 and p.ent(got[0])["POT"] & ONCE, [(s2, p.ent(s2)["POT"]) for s2 in got])


# ---------------------------------------------------------------------------- sfx_req log
# (tests/sfx5b.py's patch: sfx_req's first 3 bytes -> JP stub that appends A to a log, then runs them)
SFX_STUB = S["LOWRAM_END_3B"]
SFX_RES = SFX_STUB + 200


def sfx_log_install(p):
    base = S["sfx_req"]
    assert list(p.z.read_memory(base, 3)) == [0xF5, 0xC5, 0x47]
    w = lambda v: [v & 255, v >> 8]  # noqa: E731
    code = [0xE5, 0xF5, 0x2A] + w(SFX_RES) + [0x77, 0x23, 0x22] + w(SFX_RES) + [0xF1, 0xE1,
            0xF5, 0xC5, 0x47, 0xC3] + w(base + 3)
    p.z.cmd("write-memory %d %s" % (SFX_STUB, " ".join(str(b) for b in code)))
    p.z.cmd("write-memory %d %s" % (base, " ".join(str(b) for b in [0xC3] + w(SFX_STUB))))
    p.z.cmd("write-memory %d %s" % (SFX_RES, " ".join(str(b) for b in w(SFX_RES + 2))))
    p.wb("SND_MODE", 3)


def sfx_log_remove(p):
    p.z.cmd("write-memory %d 245 197 71" % S["sfx_req"])   # push af / push bc / ld b,a


def sfx_log(p):
    end = p.rb(SFX_RES) | p.rb(SFX_RES + 1) << 8
    return list(p.z.read_memory(SFX_RES + 2, end - SFX_RES - 2)) if end > SFX_RES + 2 else []


# ---------------------------------------------------------------------------- B / C
def bone_caller(p, lines):
    L, r = level(p, lines, 6, 0x7601, need=20)
    check("B setup: D6 + a 20-col standable run", L is not None, r)
    if not L:
        return
    lpk = list(p.z.read_memory(S["LP_KINDS"], 4))
    want_k = K["SKELETON"] if K["SKELETON"] in lpk else K["GHOST"]
    s_, c0 = r
    clear_room(p)
    hero_at(p, c0, s_)
    bx = c0 + 3 + 6
    mon(p, 1, K["BONE_CALLER"], bx, s_, hp=60)
    heal(p)
    lines.lines.clear()
    sfx_log_install(p)
    p.turn("WAIT")
    sfx_ids = sfx_log(p)
    sfx_log_remove(p)
    sm = [s2 for s2 in room_slots(p) if s2 != 1]
    e = p.ent(sm[0]) if sm else None
    check("B1s the summon cast requests SFX_DRAIN exactly once (sfx_msg MSG_M_SUMMON at the IMPACT)",
          sfx_ids.count(S["SFX_DRAIN"]) == 1, sfx_ids)
    check(f"B1 the first in-line turn summons one {'Skeleton' if want_k == K['SKELETON'] else 'Ghost'}"
          " (summon-made, F_RESPAWN)",
          len(sm) == 1 and e["KIND"] == want_k and e["POT"] & SUMM and e["FLAGS"] & EF_RESPAWN, (sm, e, lpk))
    check("B2 'THE SUMMONER SUMMONS!' logged; the caster's S = BC_CD",
          "THE SUMMONER SUMMONS!" in lines.lines and (p.ent(1)["POT"] >> 2) & 15 == S["BC_CD"],
          (lines.lines, p.ent(1)["POT"]))
    if e:
        w = kt(p, e["KIND"], "KT_BW")
        fly = kt(p, e["KIND"], "KT_FLAGS") & 1
        cx = p.ent(1)["X"]
        check("B3 beside the caster (<= SP_R cols), its row = the cruise row (flyer) / standing",
              (e["Y"] == 9 * s_ + 1 if fly else stands_on_floor(p, sm[0]))
              and (0 <= e["X"] - (cx + 3) < S["SP_R"] or 0 <= cx - (e["X"] + w) < S["SP_R"]), (e, cx))
    n = 0
    for _ in range(10):
        heal(p)
        p.set_ent(1, HP=60)
        before = room_slots(p)
        p.turn("WAIT")
        n += len(new_slots(p, before))
    check("B4 <= 1 live summon: 10 more turns, no 2nd", n == 0, n)
    for s2 in sm:
        p.set_ent(s2, FLAGS=0)
    p.set_ent(1, X=bx, PX=bx * 8, POT=p.ent(1)["POT"] & 0xC3)     # S = 0 now
    hero_at(p, c0, s_)
    heal(p)
    before = room_slots(p)
    p.turn("WAIT")
    again = new_slots(p, before)
    check("B5 the summon dead, S = 0: the next in-line turn summons again", len(again) == 1, again)
    room = p.rb("CUR_ROOM")
    far3(p, "lp_bank", a=room, e=0)
    ents, _ = rec_entries(p, room)
    check("B6 lp_bank: only the Bone Caller is banked (its summon discarded)",
          [k_ & 0x1F for k_, _ in ents] == [K["BONE_CALLER"]], ents)
    # ------------------------------------------------------------------ C
    clear_room(p)
    p.wb("SPQ_K", 0)
    hero_at(p, c0, s_)
    mon(p, 1, K["BONE_CALLER"], bx, s_, hp=60)
    for i, x in enumerate((c0 + 13, c0 + 16, 2)):
        mon(p, 2 + i, K["SKELETON"], x, s_ if i < 2 else s_ ^ 1, hp=30)
    heal(p)
    before = room_slots(p)
    p.turn("WAIT")
    check("C1 the cap (4 monsters): no summon, S stays 0, the queue empty",
          not new_slots(p, before) and (p.ent(1)["POT"] >> 2) & 15 == 0 and p.rb("SPQ_K") == 0,
          (new_slots(p, before), p.ent(1)["POT"], p.rb("SPQ_K")))


# ---------------------------------------------------------------------------- P
def pharaoh(p, lines):
    L = Lair(p, 5, 0x7501)
    lines.arm()
    check("P setup: D5", L.ok, p.rb("LVL_DEPTH"))
    if not L.ok:
        return
    ok = L.enter()
    bs = boss_slot(p)
    check("P0 in the lair, the Golden Pharaoh (a golden Mummy) live", ok and bs is not None
          and p.ent(bs)["KIND"] == K["MUMMY"], (ok, bs))
    if bs is None:
        return
    esc = [s2 for s2 in room_slots(p) if s2 != bs]
    heal(p)
    n = 0
    if esc:
        for _ in range(3):
            heal(p)
            before = room_slots(p)
            p.turn("WAIT")
            n += len(new_slots(p, before))
        check("P1 with its escort (Σ 6 + escort + 5 > 12): no summon", n == 0, (n, esc))
        for s2 in esc:
            p.set_ent(s2, FLAGS=0)
    mins = []
    for _ in range(3):
        heal(p)
        before = room_slots(p)
        p.turn("WAIT")
        mins += new_slots(p, before)
        if mins:
            break
    e = p.ent(mins[0]) if mins else None
    check("P2 escort gone: one minion (Skeleton / Mummy), summon-made, F_RESPAWN; S = PH_CD",
          len(mins) == 1 and e["KIND"] in (K["SKELETON"], K["MUMMY"]) and e["POT"] & SUMM and e["FLAGS"] & EF_RESPAWN
          and (p.ent(bs)["POT"] >> 2) & 15 == S["PH_CD"], (mins, e, p.ent(bs)["POT"]))
    if e:
        bx = p.ent(bs)["X"]
        w = kt(p, e["KIND"], "KT_BW")
        bw = kt(p, K["MUMMY"], "KT_BW")
        check("P3 the minion stands beside the Pharaoh (<= SP_R cols)",
              stands_on_floor(p, mins[0]) and (0 <= e["X"] - (bx + bw) < S["SP_R"] or 0 <= bx - (e["X"] + w) < S["SP_R"]),
              (e, bx))
    n = 0
    for _ in range(12):
        heal(p)
        before = room_slots(p)
        p.turn("WAIT")
        n += len(new_slots(p, before))
    check("P4 one minion at a time (PH_LIVE 1; 6 + 5 + 5 > 12 anyway): 12 turns, none", n == 0, n)
    if mins:
        corpse_reuse(p, bs, mins[0])
    ok = L.leave()
    ents, _ = rec_entries(p, L.lair)
    check("P5 leaving the lair discards the minion: the record holds the boss only",
          ok and [k_ for k_, _ in ents] == [p.rb("LP_BOSS")], (ok, ents))


def corpse_reuse(p, bs, k):
    """P6 (fix/d8-corpse-topleft, user playtest: the nun's / the Pharaoh's summoned Skeleton): the minion
    killed (deal_hit, hp 1) and the Pharaoh's next summon queued the same turn (SPQ_* poked as ph_summon
    fills them: the Mummy's own timing rarely lines up in a test): end_turn's sp_run reuses the just-freed
    slot while LIVE_LIST still lists it and its render record still shows the corpse. The new minion is
    placed (sp_init: ACT_SLOT = its own slot, box_free skips it) and the corpse frame is never drawn at
    the top-left (sp_init: R_VIS 0) nor on it. Before the fix: no minion (every sp_try saw the slot's own
    box) and the corpse blitted at px = py = 0 for a tick."""
    hero_at(p, 2 if p.ent(bs)["X"] > 15 else 27, 0)
    p.tick(3)
    p.set_ent(k, HP=1)
    p.wb(S["P_ENTITIES"] + bs * STRIDE + S["E_RCD"], p.ent(bs)["POT"] | 0x3C)   # S 15: no own summon
    code(p, [0x3A] + w16(S["PORT_7FFD_SHADOW"]) + [0xF5, 0x3E, 3, 0xCD] + w16(S["page_bank"])
         + [0xDD, 0x21] + w16(S["P_ENTITIES"]) + [0x3E, k, 0x01, 0, 99, 0x1E, 0, 0xCD] + w16(S["deal_hit"])
         + [0xF1, 0xCD] + w16(S["restore_page"]))
    heal(p)
    p.wmem(S["SPQ_K"], [K["SKELETON"] | S["SQF_SUMM"] | S["SQF_RESP"], bs, 1])   # {kind, SPQ_P, SPQ_N}
    p.turn("WAIT")
    bad = []
    for i in range(4):
        q = p.ent(k)
        if q["DVIS"] & 1 and q["DCOL"] < 5 and q["DROW"] < 9:
            bad.append((i, "top-left", q))
        if q["DVIS"] & 1 and q["FLAGS"] & EF_ACTIVE and not q["FLAGS"] & EF_DYING and q["DFID"] == S["FID_small_corpse"]:
            bad.append((i, "new body drawn as a corpse", q))
        p.tick(1)
    q = p.ent(k)
    check("P6 the minion killed as the next one is queued: the new minion takes its freed slot (placed), "
          "no corpse frame at the top-left / on it", q["FLAGS"] & EF_ACTIVE and not q["FLAGS"] & EF_DYING
          and q["POT"] & SUMM and stands_on_floor(p, k) and not bad, (q, bad[:3]))

# ---------------------------------------------------------------------------- A
def alarm(p, lines):
    L, r = level(p, lines, 5, 0x7A01, need=10)
    check("A setup: D5", L is not None, r)
    if not L:
        return
    s_, c0 = r
    TL = S["TRAP_LIST"]
    lpk = list(p.z.read_memory(S["LP_KINDS"], 4))
    for dead in (False, True):
        clear_room(p)
        room = p.rb("CUR_ROOM")
        hero_at(p, c0, s_)
        heal(p)
        fl = p.rb("LVL_FLAGS")
        p.wb("LVL_FLAGS", (fl | S["LF_UNIQUE"]) if dead else (fl & ~S["LF_UNIQUE"] & 255))
        hw = kt(p, p.rb("HERO_KIND"), "KT_BW")
        p.wmem(TL, [room | (S["TRF_S1"] if s_ else 0), (c0 + hw) | (S["TT_ALARM"] << 5)] + [0] * 10 + [1])
        lines.lines.clear()
        before = room_slots(p)
        p.turn("L")
        ns = new_slots(p, before)
        if dead:
            check("A4 boss dead (LF_UNIQUE): 'A BELL RINGS. NOTHING COMES', no wave",
                  "A BELL RINGS. NOTHING COMES" in lines.lines and not ns, (lines.lines, ns))
            continue
        es = [p.ent(s2) for s2 in ns]
        check("A1 'AN ALARM BELL RINGS!' logged; the queue empty after end_turn",
              "AN ALARM BELL RINGS!" in lines.lines and p.rb("SPQ_K") == 0, (lines.lines, p.rb("SPQ_K")))
        check("A2 1-2 wave bodies of LP_KINDS, PENDING, F_RESPAWN, not summon-made",
              1 <= len(es) <= 2 and all(e["KIND"] in lpk and e["FLAGS"] & EF_PENDING and e["FLAGS"] & EF_RESPAWN
                                         and not e["POT"] & SUMM for e in es), (es, lpk))
        ex = p.rb(S["ROOM_DESC"] + room * 16 + 1)
        okx = []
        for e in es:
            w = kt(p, e["KIND"], "KT_BW")
            if ex & 3:
                okx.append(e["X"] in (1, 31 - w))
            else:
                okx.append(e["X"] in (p.rb(S["ROOM_DESC"] + room * 16 + 2), p.rb(S["ROOM_DESC"] + room * 16 + 3)))
        check("A3 at a door (x = 1 / 31 - w) or a ladder-end col", all(okx), [(e["X"], e["Y"]) for e in es])
        for _ in range(6):
            heal(p)
            p.turn("WAIT")
        mat = [s2 for s2 in ns if p.ent(s2)["FLAGS"] & EF_ACTIVE and not p.ent(s2)["FLAGS"] & EF_PENDING]
        check("A5 the wave materialised within 6 turns (walked / popped in)", mat == [s2 for s2 in ns
              if p.ent(s2)["FLAGS"] & EF_ACTIVE], [(s2, p.ent(s2)) for s2 in ns])


# ---------------------------------------------------------------------------- N
@keep_pc
def try_x(p, sl, x):
    """sp_try (bank 6, called direct) for slot sl at candidate x -> CF (the carry of the call)."""
    sh = S["PORT_7FFD_SHADOW"]
    body = ([0x3A] + w16(sh) + [0xF5, 0x3E, S["BANK_R6"], 0xCD] + w16(S["page_bank"])
            + [0x3E, 0xFF, 0x32] + w16(S["ACT_SLOT"])
            + [0xDD, 0x21] + w16(S["P_ENTITIES"] + sl * STRIDE) + [0x3E, x, 0xCD] + w16(S["sp_try"])
            + [0x9F, 0x32] + w16(RES) + [0xF1, 0xCD] + w16(S["restore_page"]))      # sbc a,a = 0 / $FF
    ok, _ = p.code(body, game=True)
    return ok, p.rb(RES) != 0


def bounds(p, lines):
    L, r = level(p, lines, 5, 0x7A01, need=10)
    check("N setup: D5", L is not None, r)
    if not L:
        return
    s_, c0 = r
    clear_room(p)
    hero_at(p, c0 + 8, s_)
    mon(p, 1, K["SKELETON"], 2, s_, hp=60)                    # the parent at x = 2
    mon(p, 2, K["GHOST"], 2, s_, hp=60)                       # a flyer body: no terrain test after the bounds
    for sl, tag in ((1, "walker"), (2, "flyer")):
        for x in (0xFF, 0xFE, 0xFD):
            ok, cf = try_x(p, sl, x)
            check(f"N1 sp_try {tag} x = ${x:02X} (negative): refused", ok and cf, (ok, cf))
    ok, cf = try_x(p, 1, c0 + 4)
    check("N2 sp_try walker on a legal free col: accepted", ok and not cf, (ok, cf))


# ---------------------------------------------------------------------------- X / T
def exits(p, lines):
    L, r = level(p, lines, 6, 0x7E01, need=20)
    check("X setup: D6", L is not None, r)
    if not L:
        return
    s_, c0 = r
    clear_room(p)
    hero_at(p, c0, s_)
    bx = c0 + 9
    mon(p, 1, K["BONE_CALLER"], bx, s_, hp=60)
    q = [K["GHOST"] | 0xC0, 1, 1]
    for tag, ek, dying in (("an exit turn", 1, False), ("a dying hero", 0, True)):
        p.wmem(S["SPQ_K"], q)
        p.wb("EXIT_KIND", ek)
        if dying:
            p.set_ent(0, FLAGS=p.ent(0)["FLAGS"] | EF_DYING)
        before = room_slots(p)
        far6(p, "sp_run")
        check(f"X sp_run on {tag}: the queue emptied, nothing made",
              p.rb("SPQ_K") == 0 and room_slots(p) == before, (p.rb("SPQ_K"), room_slots(p)))
        p.wb("EXIT_KIND", 0)
        p.set_ent(0, FLAGS=p.ent(0)["FLAGS"] & ~EF_DYING & 255)
    # costs: an offspring / a summon beside the caster, a 2-body wave (interrupts on: the real path)
    costs = {}
    for tag, qq in (("summon", [K["GHOST"] | 0xC0, 1, 1]), ("offspring", [K["RAT"] | 0xE0, 1, 1]),
                    ("wave x2", [0x80, 0xFF, 2])):
        clear_room(p)
        hero_at(p, c0, s_)
        if qq[1] != 0xFF:
            mon(p, 1, K["BONE_CALLER"], bx, s_, hp=60)        # the parent (the wave has none: its cap room)
        code(p, [0xCD] + w16(S["build_live"]))
        p.wmem(S["SPQ_K"], qq)
        ok, ts = far6(p, "sp_run")
        costs[tag] = ts
        made = len(room_slots(p)) - (qq[1] != 0xFF)
        check(f"T sp_run {tag}: made {qq[2]} bod{'y' if qq[2] == 1 else 'ies'}", ok and made == qq[2], (ok, made))
    print("[info] sp_run T-states (far6 incl.): " + ", ".join(f"{k} {v}" for k, v in costs.items()), flush=True)
    check("T sp_run <= 12k T a body, <= 16k a 2-body wave (end_turn tick)",
          costs["summon"] <= 12000 and costs["offspring"] <= 12000 and costs["wave x2"] <= 16000, costs)


if __name__ == "__main__":
    sys.exit(main())
