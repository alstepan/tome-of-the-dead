#!/usr/bin/env python3
"""3F-T12 respawn trickle (game.md §9.5; R6 src/trickle6.asm, bank-7 end_turn / do_exit hooks)
against tools/respawn_model.py trickle_check, on seeded generated levels (the real level_descend).

  M  model equivalence: random record states (VISITED / FRESH, 0-4 entries of the level's kinds and
     tiers), CUR_ROOM / TRK_PREV / LP_RESPAWNS / LVL / RNG_STATE / boss-dead, floor items taken at
     random: far6 trk_run == trickle_check(turn 48) on every record byte, LP_RESPAWNS and the
     final RNG_STATE (D1, D5, D8 incl. the Sanctum); LP_LVL / slots untouched
  E  end_turn: TRK_PHASE counts the level's turns; the 48th only sets TRK_DUE (no check on the
     turn-ending tick), the next INPUT tick runs the check ALONE (no turn starts in it; a held key's
     turn starts on the tick after); a spawn is a record append only (the slots unchanged);
     RESPAWN_MAX holds; boss dead: nothing; a turn whose end_turn runs sp_run holds the count
  F  a real 48-turn play from arrival (no TRK_PHASE poke): no check through turn 47, the check runs
     after the 48th
  P  prev_room: a real do_exit into the lair -> TRK_PREV = the room left; a teleport -> the lair
  R  the appended entry is placed by lp_enter on entry: F_RESPAWN body, the kind, the scaled hp
  B  boss dead (D1/D5: UNIQUE or GRATE_OPEN; D8: SEAL_OPEN|UNIQUE, no grate): 120 trk_run calls, no respawn
  T  cost: worst far6 trk_run over the M cases + a heavy state (8 VISITED records x 3 entries, a
     spawn through the Skeleton-fails / Rat-retry path, 450 seeds; review measured 14.1k)
Build with -DDEBUG_KIT=0. ZRCP_PORT=<port> python3 tests/trickle.py
"""
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, GS_PLAYING  # noqa: E402
from lp import T  # noqa: E402
from boss import Lair  # noqa: E402
from spawn import far6, far3, room_slots, heal  # noqa: E402
import levelgen as G  # noqa: E402
import respawn_model as RM  # noqa: E402
import room_model  # noqa: E402

fails = []
LPB, LPN = S["LP_STATE"], S["LP_LEN"]
REC = S["LP_REC"]
EF_RESPAWN = S["EF_RESPAWN"]


def check(name, ok, got=None):
    if not ok:
        fails.append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f": got {got}"), flush=True)


def present(L):
    return [r for r in range(9) if room_model.field(L.blk, r, "RD_FLAGS") & S["RDF_PRESENT"]]


def items_of(p):
    fl = p.z.read_memory(S["FLOOR_LIST"], 4 * S["FLOOR_MAX"])
    n = [0] * 9
    for i in range(S["FLOOR_MAX"]):
        b = fl[4 * i]
        if b != S["FL_EMPTY"]:
            n[b & S["FL_ROOM_MASK"]] += 1
    return n


def kind_pool(depth):
    keys = list(G.LP_TAB[depth][0])
    out = []
    for k in keys:
        out.append(k)
        out += [t for t in G.TIERS.get(k, []) if t]
    return out


def write_state(p, depth, recs, rnd):
    """recs[r] = None | {"visited", "ents"}: the LP records (FRESH: a quota, stale bytes)."""
    blob = []
    for r in range(9):
        rec = recs[r]
        if rec is None or not rec["visited"]:
            q = rnd.randint(0, 3) if rec is not None else 0
            blob += [q] + [rnd.randint(0, 31) for _ in range(8)]
        else:
            e = rec["ents"]
            body = []
            for kb, hp in e:
                body += [kb, hp]
            body += [rnd.randint(0, 255) for _ in range(8 - len(body))]
            blob += [0x80 | len(e)] + body
    p.wmem(REC, blob)
    return blob


def model_level(p, L, recs, items, cur, prev, resp, lvl, dead):
    d = L.depth
    lv = RM.Level(d, lvl, list(G.LP_TAB[d][0]), L.lair, [None if r is None else
                  {"visited": r["visited"], "ents": list(r["ents"])} for r in recs], items)
    lv.sanctum = p.rb("LVL_SANCTUM") if p.rb("LVL_SANCTUM") != S["ROOM_NONE"] else None
    lv.cur, lv.prev, lv.resp, lv.boss_dead = cur, prev, resp, dead
    return lv


def rec_bytes(lv):
    out = []
    for rec in lv.recs:
        out.append(None if rec is None or not rec["visited"] else [(kb, hp) for kb, hp in rec["ents"]])
    return out


def read_recs(p, recs):
    blob = p.z.read_memory(REC, 81)
    out = []
    for r in range(9):
        if recs[r] is None or not recs[r]["visited"]:
            out.append(None)
            continue
        h = blob[9 * r]
        out.append([(blob[9 * r + 1 + 2 * i], blob[9 * r + 2 + 2 * i]) for i in range(h & 7)])
    return out


# ---------------------------------------------------------------------------- M / T
def model_cases(p, L, rnd, n, worst):
    d = L.depth
    pr = present(L)
    pool = kind_pool(d)
    st = L.blk[S["LVL_START"] - G.BASE]
    lp_kinds = list(p.z.read_memory(S["LP_KINDS"], 4))
    check(f"M d{d} LP_KINDS == levelgen LP_TAB", lp_kinds == [G.KROWS[k][0] for k in G.LP_TAB[d][0]], lp_kinds)
    fl0 = list(p.z.read_memory(S["FLOOR_LIST"], 4 * S["FLOOR_MAX"]))
    spawns = mism = 0
    for c in range(n):
        recs = []
        for r in range(9):
            if r not in pr:
                recs.append(None)
                continue
            vis = rnd.random() < 0.75 or r == st
            ents = []
            if vis:
                for _ in range(rnd.choice((0, 0, 1, 1, 2, 2, 3, 4))):
                    kb = G.KROWS[rnd.choice(pool)][0] | (G.LEK_RESPAWN if rnd.random() < 0.3 else 0)
                    ents.append((kb, rnd.randint(1, 40)))
            recs.append({"visited": vis, "ents": ents})
        blob = write_state(p, d, recs, rnd)
        fl = list(fl0)                                       # take some floor items
        for i in range(S["FLOOR_MAX"]):
            if fl[4 * i] != S["FL_EMPTY"] and rnd.random() < 0.3:
                fl[4 * i] = S["FL_EMPTY"]
        p.wmem(S["FLOOR_LIST"], fl)
        cur = rnd.choice(pr)
        prev = rnd.choice(pr + [0])
        resp = rnd.choice((0, 0, 1, 3, 5, 6))
        lvl = rnd.randint(1, 12)
        dead = rnd.random() < 0.1
        x = rnd.randint(1, 0xFFFF)
        p.wb("CUR_ROOM", cur)
        p.wb("TRK_PREV", prev)
        p.wb("LP_RESPAWNS", resp)
        p.wb("LVL", lvl)
        lf = p.rb("LVL_FLAGS") & ~S["LF_GRATE_OPEN"] & 255
        p.wb("LVL_FLAGS", lf | (S["LF_GRATE_OPEN"] if dead else 0))
        p.wmem(S["RNG_STATE"], [x & 255, x >> 8])
        lplvl = p.rb("LP_LVL")
        sl0 = room_slots(p)
        lv = model_level(p, L, recs, items_of(p), cur, prev, resp, lvl, dead)
        rng = G.Rng(1, d)
        rng.x = x
        want = RM.trickle_check(lv, RM.RESPAWN_PERIOD, rng)
        if want is not None:                                 # the expected 81 B: one append
            r, kb, hp = want
            n0 = blob[9 * r] & 7
            blob[9 * r] += 1
            blob[9 * r + 1 + 2 * n0], blob[9 * r + 2 + 2 * n0] = kb, hp
        ok, ts = far6(p, "trk_run")
        got = read_recs(p, recs)
        good = (ok and got == rec_bytes(lv) and list(p.z.read_memory(REC, 81)) == blob and p.rb("LP_RESPAWNS") == lv.resp and p.rw("RNG_STATE") == rng.x
                and p.rb("LP_LVL") == lplvl and room_slots(p) == sl0)
        spawns += want is not None
        if not good:
            mism += 1
            check(f"M d{d} case {c}: trk_run == trickle_check", False,
                  (ok, want, got, rec_bytes(lv), p.rb("LP_RESPAWNS"), lv.resp, hex(p.rw("RNG_STATE")), hex(rng.x)))
        if want is not None and ts > worst[0]:
            worst[:] = [ts, f"d{d} case {c}"]
        p.wb("LVL_FLAGS", lf)
    p.wmem(S["FLOOR_LIST"], fl0)
    check(f"M d{d}: {n} cases == the model ({spawns} spawns, {mism} mismatches)", mism == 0 and spawns > 0,
          (spawns, mism))


# ---------------------------------------------------------------------------- E / R
def end_turn_cases(p, L, rnd):
    d = L.depth
    pr = present(L)
    cur = p.rb("CUR_ROOM")
    others = [r for r in pr if r not in (cur, L.lair, p.rb("LVL_SANCTUM"))]
    tgt = others[0]
    recs = [None if r not in pr else {"visited": r == tgt or r == cur, "ents": []} for r in range(9)]
    write_state(p, d, recs, rnd)
    p.wb("TRK_PREV", cur)
    p.wb("LP_RESPAWNS", 0)
    heal(p)
    # phase 46 -> 47: no check (LP_RESPAWNS / record unchanged, no RNG spent by the trickle itself)
    p.wb("TRK_PHASE", 46)
    p.turn("WAIT")
    check("E1 phase 46 -> 47 after a turn, no check", p.rb("TRK_PHASE") == 47 and p.rb("LP_RESPAWNS") == 0
          and p.rb(REC + 9 * tgt) == 0x80, (p.rb("TRK_PHASE"), p.rb("LP_RESPAWNS"), p.rb(REC + 9 * tgt)))
    made, ok0, sl_ok = 0, True, True
    for k in range(60):                                       # each 48th turn: ~38 % a spawn (1 room)
        p.wb("TRK_PHASE", 47)
        sl0 = room_slots(p)
        n0 = p.rb("LP_RESPAWNS")
        heal(p)
        p.turn("WAIT")
        ok0 &= p.rb("TRK_PHASE") == 0
        sl_ok &= room_slots(p) == sl0
        made += p.rb("LP_RESPAWNS") - n0
        if made:
            break
    ent = [(p.rb(REC + 9 * tgt + 1 + 2 * i), p.rb(REC + 9 * tgt + 2 + 2 * i)) for i in range(p.rb(REC + 9 * tgt) & 7)]
    check("E2 the 48th turn checks (TRK_PHASE -> 0); spawns are record appends into the only eligible room",
          ok0 and made == 1 and len(ent) == 1 and all(kb & G.LEK_RESPAWN for kb, _ in ent), (ok0, made, ent))
    check("E3 a trickle turn never touches a slot", sl_ok)
    if ent:
        kb, hp = ent[0]
        check("E4 the entry: a level kind (or its tier), full depth-scaled hp, not golden",
              hp == G.k3_hp(kb, d) and not kb & G.LEK_GOLD
              and G.K3_BY_ID[kb & 31] in kind_pool(d), (kb, hp))
    # RESPAWN_MAX and the boss's death
    for tag, resp, dead in (("RESPAWN_MAX reached", RM.RESPAWN_MAX, False), ("the boss dead", 0, True)):
        p.wb("LP_RESPAWNS", resp)
        lf = p.rb("LVL_FLAGS")
        if dead:
            p.wb("LVL_FLAGS", lf | S["LF_GRATE_OPEN"])
        r0 = list(p.z.read_memory(REC, 81))
        got = 0
        for _ in range(12):
            p.wb("TRK_PHASE", 47)
            heal(p)
            p.turn("WAIT")
            got += list(p.z.read_memory(REC, 81)) != r0
        check(f"E5 {tag}: 12 checks, no record changes", got == 0 and p.rb("LP_RESPAWNS") == resp, got)
        p.wb("LVL_FLAGS", lf)
    # R: the entry is placed on entry by lp_enter (the slots of tgt)
    if ent:
        p.clear_slots()
        p.wmem(S["LP_HX"], [1, 0, 3])
        ok, _ = far3(p, "lp_enter", a=tgt)
        bodies = [p.ent(s_) for s_ in range(1, 16) if p.ent(s_)["FLAGS"] & 1 and p.ent(s_)["ROOM"] == tgt]
        kept = p.rb(REC + 9 * tgt) & 7
        hit = [e for e in bodies if e["KIND"] == ent[0][0] & 31 and e["HP"] == ent[0][1] and e["FLAGS"] & EF_RESPAWN]
        check("R1 lp_enter places the trickled entry: F_RESPAWN body, its kind and hp (or keeps it waiting)",
              ok and (hit or kept), (ok, [(e["KIND"], e["HP"], e["FLAGS"]) for e in bodies], kept))
        p.clear_slots()


def due_cases(p, L, rnd):
    """E6-E9: the DUE flag / idle-tick execution, the sp_run hold (TRK_PHASE not poked in F)."""
    d = L.depth
    pr = present(L)
    cur = p.rb("CUR_ROOM")
    tgt = [r for r in pr if r not in (cur, L.lair, p.rb("LVL_SANCTUM"))][0]
    recs = [None if r not in pr else {"visited": r == tgt or r == cur, "ents": []} for r in range(9)]
    keys, _ = p._prep(("WAIT",))
    # F: a real 48-turn play from the arrival (TRK_PHASE as level_gen left it)
    write_state(p, d, recs, rnd)
    p.wb("TRK_PREV", cur)
    p.wb("LP_RESPAWNS", 0)
    p.wmem(S["TRK_W"], [0xEE] * 9)
    ph0 = p.rb("TRK_PHASE")
    for _ in range(47):
        heal(p)
        p.turn("WAIT")
    check("F1 47 turns from the arrival: count 47, no check (TRK_W untouched)",
          ph0 == 0 and p.rb("TRK_PHASE") == 47 and list(p.z.read_memory(S["TRK_W"], 9)) == [0xEE] * 9,
          (ph0, p.rb("TRK_PHASE"), list(p.z.read_memory(S["TRK_W"], 9))))
    # E6-E8 on the 48th turn, tick by tick with the key held
    heal(p)
    t0, n0 = p.rw("TURN_COUNTER"), p.rb("LP_RESPAWNS")
    rep0 = p.rb("INPUT_REPEAT")
    p.wb("INPUT_REPEAT", 1)                                    # held keys repeat (the default game setting)
    p.hold(*keys)
    log = []
    for _ in range(40):
        p.tick()
        log.append((p.rw("TURN_COUNTER") - t0, p.rb("TURN_PHASE"), p.rb("TRK_PHASE"),
                    p.rb(S["TRK_W"] + tgt), p.rb("LP_RESPAWNS")))
        if log[-1][0] >= 2:
            break
    p.release()
    p.wb("INPUT_REPEAT", rep0)
    p.tick(2)
    e = next((i for i, x in enumerate(log) if x[0] == 1), None)
    ok6 = e is not None and log[e][2] == S["TRK_DUE"] and log[e][3] == 0xEE and log[e][4] == n0
    check("E6 the 48th turn's ending tick only sets TRK_DUE (no check: TRK_W / LP_RESPAWNS untouched)", ok6,
          log[:e + 3] if e is not None else log)
    ok7 = ok6 and e + 1 < len(log) and log[e + 1][:3] == (1, 0, 0) and log[e + 1][3] != 0xEE
    check("E7 the next INPUT tick runs the check alone (TRK_DUE clear, w_r written, no turn started)", ok7,
          log[e:e + 3] if e is not None else log)
    ok8 = ok7 and any(x[0] == 2 or x[1] == 1 for x in log[e + 2:e + 4])
    check("F2 / E8 the held key's next turn starts right after the check tick", ok8,
          log[e:e + 5] if e is not None else log)
    # E9: a turn whose end_turn runs sp_run does not advance the count
    p.wb("TRK_PHASE", 10)
    p.wmem(S["SPQ_K"], [S["K_RAT"] | 0xE0, 15, 1])           # an offspring of an empty slot: emptied, none made
    heal(p)
    p.turn("WAIT")
    check("E9 a turn with sp_run holds the count (10 -> 10), the queue emptied",
          p.rb("TRK_PHASE") == 10 and p.rb("SPQ_K") == 0, (p.rb("TRK_PHASE"), p.rb("SPQ_K")))
    heal(p)
    p.turn("WAIT")
    check("E9b the next plain turn counts again (10 -> 11)", p.rb("TRK_PHASE") == 11, p.rb("TRK_PHASE"))


def heavy_cost(p, L, rnd):
    cur = p.rb("CUR_ROOM")
    sk, rat, gob = S["K_SKELETON"], S["K_RAT"], S["K_GOBLIN"]
    p.wmem(S["LP_KINDS"], [sk, rat, sk, rat])
    p.wb("LVL_LAIR", S["ROOM_NONE"])
    p.wb("LVL_SANCTUM", S["ROOM_NONE"])
    p.wb("TRK_PREV", cur)
    p.wb("LVL_FLAGS", p.rb("LVL_FLAGS") & ~S["LF_GRATE_OPEN"] & 255)
    rec = []
    for r in range(9):
        rec += [0x80] + [0] * 8 if r == cur else [0x83, gob, 9, gob, 9, rat, 7, 0, 0]
    res = []
    for lvl in (3, 7, 12):
        for _ in range(150):
            p.wmem(S["LP_REC"], rec)
            p.wb("LP_RESPAWNS", 0)
            p.wb("LVL", lvl)
            p.wmem(S["RNG_STATE"], [rnd.randrange(256), rnd.randrange(1, 256)])
            ok, t = far6(p, "trk_run")
            res.append((t, p.rb("LP_RESPAWNS")))
    sc = max(t for t, n in res if not n)
    sp = max(t for t, n in res if n)
    print(f"[info] heavy state (8 x 3 entries, 450 seeds): worst far6 trk_run no spawn {sc} T, with a spawn {sp} T",
          flush=True)
    check("T2 heavy state: trk_run <= 15k T (on the idle INPUT tick, ~25-30k T: far under the 126k cap)",
          sp <= 15000 and sc <= 15000, (sc, sp))


def boss_dead_cases(p, L, rnd):
    """B game.md 9.5 (U): the trickle stops the turn the boss dies. D1-D7: grate_open sets LF_UNIQUE then
    LF_GRATE_OPEN; D8: .seal sets LF_SEAL_OPEN | LF_UNIQUE and never the grate. trk_run must do nothing
    for either flag alone; the control (both clear) must spawn on the same states."""
    d = L.depth
    pr = present(L)
    st = L.blk[S["LVL_START"] - G.BASE]
    fl0 = p.rb("LVL_FLAGS")
    base = fl0 & ~(S["LF_GRATE_OPEN"] | S["LF_UNIQUE"] | S["LF_SEAL_OPEN"]) & 255
    cur = next(r for r in pr if r != L.lair)
    for name, bits in (("alive", 0), ("D8 death (SEAL_OPEN|UNIQUE)", S["LF_SEAL_OPEN"] | S["LF_UNIQUE"]),
                       ("UNIQUE", S["LF_UNIQUE"]), ("GRATE_OPEN", S["LF_GRATE_OPEN"])):
        resp = worst = 0
        for i in range(120):
            recs = [None if r not in pr else {"visited": True, "ents": []} for r in range(9)]
            write_state(p, d, recs, rnd)
            p.wb("CUR_ROOM", cur)
            p.wb("TRK_PREV", L.lair)
            p.wb("LP_RESPAWNS", 0)
            p.wb("LVL", 6)
            p.wb("LVL_FLAGS", base | bits)
            x = rnd.randint(1, 0xFFFF)
            p.wmem(S["RNG_STATE"], [x & 255, x >> 8])
            ok, ts = far6(p, "trk_run")
            resp += p.rb("LP_RESPAWNS")
            worst = max(worst, ts)
        p.wb("LVL_FLAGS", fl0)
        if bits:
            check(f"B d{d} {name}: 120 trk_run calls, no respawn, worst {worst} T",
                  ok and resp == 0 and worst < 1000, (resp, worst))
        else:
            check(f"B d{d} control (boss alive) respawns: {resp}", resp > 0, resp)


def prev_cases(p, L):
    ok = L.enter()
    check("P1 a real do_exit into the lair: TRK_PREV = the room left", ok and p.rb("TRK_PREV") == L.nb,
          (ok, p.rb("TRK_PREV"), L.nb))
    for k in range(1, 16):
        if p.ent(k)["FLAGS"] & 1 and p.ent(k)["ROOM"] == L.lair:
            p.set_ent(k, FLAGS=0)
    p.wb("EXIT_KIND", S["EX_TELE"])
    p.turn("WAIT")
    p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
    check("P2 a teleport out of the lair: TRK_PREV = the lair", p.rb("TRK_PREV") == L.lair
          and p.rb("CUR_ROOM") != L.lair, (p.rb("TRK_PREV"), p.rb("CUR_ROOM")))


def main():
    rnd = random.Random(0x7120)
    worst = [0, ""]
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)
        for d, seed in ((1, 0x7111), (5, 0x7151), (8, 0x7181)):
            L = Lair(p, d, seed)
            check(f"setup D{d}: generated, TRK_PHASE {p.rb('TRK_PHASE')} / TRK_PREV {p.rb('TRK_PREV')} "
                  "reset by level_gen", L.ok and p.rb("TRK_PHASE") < 8 and p.rb("TRK_PREV") == 0,
                  (L.ok, p.rb("TRK_PHASE"), p.rb("TRK_PREV")))
            if not L.ok:
                continue
            model_cases(p, L, rnd, 120 if d != 8 else 80, worst)
            boss_dead_cases(p, L, rnd)
            if d == 5:
                L = Lair(p, d, seed)
                due_cases(p, L, rnd)
                L = Lair(p, d, seed)
                end_turn_cases(p, L, rnd)
                heavy_cost(p, L, rnd)
                L = Lair(p, d, seed)
                prev_cases(p, L)
    print(f"[info] worst far6 trk_run with a spawn: {worst[0]} T ({worst[1]})", flush=True)
    check("T trk_run (far6 incl.) <= 12k T", 0 < worst[0] <= 12000, worst)
    print(f"trickle: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
