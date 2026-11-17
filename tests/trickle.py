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
from spawn import w16  # noqa: E402
import levelgen as G  # noqa: E402
import respawn_model as RM  # noqa: E402
import room_model  # noqa: E402

fails = []
LPB, LPN = S["LP_STATE"], S["LP_LEN"]
REC = S["LP_REC"]
EF_RESPAWN = S["EF_RESPAWN"]
NR = S["GRID_CELLS"]                 # LARGER-D T4: 12 room slots (was 9)
NREC = NR * S["LR_STRIDE"]


def check(name, ok, got=None):
    if not ok:
        fails.append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f": got {got}"), flush=True)


def present(L):
    return [r for r in range(NR) if room_model.field(L.blk, r, "RD_FLAGS") & S["RDF_PRESENT"]]


def items_of(p):
    fl = p.z.read_memory(S["FLOOR_LIST"], 4 * S["FLOOR_MAX"])
    n = [0] * NR
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
    for r in range(NR):
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
    blob = p.z.read_memory(REC, NREC)
    out = []
    for r in range(NR):
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
    lp_kinds = list(p.z.read_memory(S["LP_KINDS"], 8))      # NEW-MON3 T3: 8 slots
    check(f"M d{d} LP_KINDS == levelgen LP_TAB", lp_kinds == [G.KROWS[k][0] for k in G.LP_TAB[d][0]], lp_kinds)
    fl0 = list(p.z.read_memory(S["FLOOR_LIST"], 4 * S["FLOOR_MAX"]))
    spawns = mism = 0
    pos_bad = [0]
    for c in range(n):
        recs = []
        for r in range(NR):
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
        if want is not None:                                 # the expected NREC B: one append
            r, kb, hp = want
            n0 = blob[9 * r] & 7
            blob[9 * r] += 1
            blob[9 * r + 1 + 2 * n0], blob[9 * r + 2 + 2 * n0] = kb, hp
        # ROOM-MEM2: LP_POS = 0 for a FRESH record, junk for a VISITED one; after trk_run every FRESH
        # record's bytes stay 0 and only the appended entry's byte changes (-> 0: no last cell)
        pos0 = [0 if recs[r] is None or not recs[r]["visited"] else rnd.randint(1, 255)
                for r in range(NR) for _ in range(4)]
        p.wmem(S["LP_POS"], pos0)
        want_pos = list(pos0)
        if want is not None:
            want_pos[4 * want[0] + (blob[9 * want[0]] & 7) - 1] = 0
        ok, ts = far6(p, "trk_run")
        got = read_recs(p, recs)
        pos1 = list(p.z.read_memory(S["LP_POS"], 4 * NR))
        if pos1 != want_pos:
            pos_bad[0] += 1
        good = (ok and got == rec_bytes(lv) and list(p.z.read_memory(REC, NREC)) == blob and p.rb("LP_RESPAWNS") == lv.resp and p.rw("RNG_STATE") == rng.x
                and p.rb("LP_LVL") == lplvl and room_slots(p) == sl0 and pos1 == want_pos)
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
    check(f"M d{d}: ROOM-MEM2 LP_POS: every FRESH record's bytes 0, the appended entry's byte 0, the rest kept",
          pos_bad[0] == 0, pos_bad[0])


# ---------------------------------------------------------------------------- E / R
def far0(p, target):
    """FARB0: farb with C = BANK_TEXT (bank-0 cold code), the game's SP."""
    return p.code([0x21] + w16(S[target]) + [0x0E, S["BANK_TEXT"], 0xCD] + w16(S["farb"]), game=True)


def desc_off(r, off):
    return S["ROOM_DESC"] + 16 * r + off


RD_STAMP = 15      # src/rsp0.asm RD_STAMP = RD_SPARE + 3


def time_off_cases(p, L, rnd):
    """E: BALANCE-PKG4: the time trickle is on again on D1-D8 (1/3 rate: period 48, chance 32/256): end_turn counts TRK_PHASE bits 0-5, sets TRK_TIME."""
    d = L.depth
    pr = present(L)
    cur = p.rb("CUR_ROOM")
    tgt = [r for r in pr if r not in (cur, L.lair, p.rb("LVL_SANCTUM"))][0]
    recs = [None if r not in pr else {"visited": r == tgt or r == cur, "ents": []} for r in range(NR)]
    write_state(p, d, recs, rnd)
    p.wb("TRK_PREV", cur)
    p.wb("LP_RESPAWNS", 0)
    p.wb("TRK_PHASE", 46)
    p.wmem(S["TRK_W"], [0xEE] * NR)
    heal(p)
    p.turn("WAIT")
    ok1 = p.rb("TRK_PHASE") == 47 and list(p.z.read_memory(S["TRK_W"], NR)) == [0xEE] * NR
    heal(p)
    p.turn("WAIT")                                           # the 48th turn: only TRK_TIME is set (no check on the turn tick)
    heal(p)
    p.turn("WAIT")                                           # the check ran on the idle INPUT tick before this turn started
    ran = list(p.z.read_memory(S["TRK_W"], NR)) != [0xEE] * NR
    check("E1 BALANCE-PKG4 time trickle: turn 47 counts, no check; the 48th sets TRK_TIME, the check (trk_run) runs on the next idle tick, "
          "the count restarts (the 3rd press is eaten by the idle check tick: TRK_PHASE 0, TRK_TIME / TRK_DUE clear)",
          ok1 and ran and p.rb("TRK_PHASE") == 0 and p.rb("LP_RESPAWNS") <= S["RESPAWN_MAX"], (ok1, ran, p.rb("TRK_PHASE"), p.rb("LP_RESPAWNS")))
    for _ in range(57):
        heal(p)
        p.turn("WAIT")
    check("E1b 60 presses from 46: 2 checks eat 2 presses, so 58 turns: TRK_PHASE 104 mod 48 = 8, RESPAWN_MAX holds", p.rb("TRK_PHASE") == 8
          and p.rb("LP_RESPAWNS") <= S["RESPAWN_MAX"], (p.rb("TRK_PHASE"), p.rb("LP_RESPAWNS")))
    p.wb("TRK_PHASE", 0)
    p.wmem(S["SPQ_K"], [S["K_RAT"] | 0xE0, 15, 1])           # sp_run turn: counted like any other
    heal(p)
    p.turn("WAIT")
    check("E2 a turn with sp_run: TRK_PHASE 1, the queue emptied", p.rb("TRK_PHASE") == 1 and p.rb("SPQ_K") == 0,
          (p.rb("TRK_PHASE"), p.rb("SPQ_K")))


def trk_entry_cases(p, L, rnd):
    """E3-E4 / R1 (was the end_turn path): trk_run's append stays the 9.5 record format; lp_enter places it."""
    d = L.depth
    pr = present(L)
    cur = p.rb("CUR_ROOM")
    tgt = [r for r in pr if r not in (cur, L.lair, p.rb("LVL_SANCTUM"))][0]
    recs = [None if r not in pr else {"visited": r == tgt or r == cur, "ents": []} for r in range(NR)]
    write_state(p, d, recs, rnd)
    p.wb("TRK_PREV", cur)
    p.wb("LP_RESPAWNS", 0)
    heal(p)
    made, sl_ok = 0, True
    for k in range(80):
        sl0 = room_slots(p)
        n0 = p.rb("LP_RESPAWNS")
        far6(p, "trk_run")
        sl_ok &= room_slots(p) == sl0
        made += p.rb("LP_RESPAWNS") - n0
        if made:
            break
    ent = [(p.rb(REC + 9 * tgt + 1 + 2 * i), p.rb(REC + 9 * tgt + 2 + 2 * i)) for i in range(p.rb(REC + 9 * tgt) & 7)]
    check("E3 trk_run (kept for D0 / tests): a spawn is a record append into the only eligible room, no slot touched",
          sl_ok and made == 1 and len(ent) == 1 and all(kb & G.LEK_RESPAWN for kb, _ in ent), (made, ent))
    if ent:
        kb, hp = ent[0]
        check("E4 the entry: a level kind (or its tier), full depth-scaled hp, not golden",
              hp == G.k3_hp(kb, d) and not kb & G.LEK_GOLD and G.K3_BY_ID[kb & 31] in kind_pool(d), (kb, hp))
        p.clear_slots()
        p.wmem(S["LP_HX"], [1, 0, 3])
        ok, _ = far3(p, "lp_enter", a=tgt)
        bodies = [p.ent(s_) for s_ in range(1, 16) if p.ent(s_)["FLAGS"] & 1 and p.ent(s_)["ROOM"] == tgt]
        kept = p.rb(REC + 9 * tgt) & 7
        hit = [e for e in bodies if e["KIND"] == ent[0][0] & 31 and e["HP"] == ent[0][1] and e["FLAGS"] & EF_RESPAWN]
        check("R1 lp_enter places the trickled entry: F_RESPAWN body, its kind and hp (or keeps it waiting)",
              ok and (hit or kept), (ok, [(e["KIND"], e["HP"], e["FLAGS"]) for e in bodies], kept))
        p.clear_slots()


def progress_cases(p, L, rnd):
    """G: LARGER-D T5 larger_depths 3.2 rsp_run (bank 0, far0): first-entry gate, p 0.75, unvisited quota + 1,
    visited >= 2 rooms away / unseen >= 150 turns, the cap, the stamp."""
    d = L.depth
    pr = present(L)
    cur = p.rb("CUR_ROOM")
    sanct = p.rb("LVL_SANCTUM")
    ex = {r: room_model.field(L.blk, r, "RD_EXITS") for r in pr}
    nb = set()
    for bit, delta in ((1, -1), (2, 1), (4, -3), (8, 3)):
        if ex[cur] & bit:
            nb.add(cur + delta)
    others = [r for r in pr if r not in (cur, L.lair, sanct)]

    def setup(visited, quota, stamp_old, resp=0, visits=1, prev=None):
        blob = []
        for r in range(NR):
            if r not in pr:
                blob += [0] * 9
            elif r in visited:
                blob += [0x80 | (quota.get(r, 1) if r != cur else 0)] + [r + 1, 5] * 4
            else:
                blob += [quota.get(r, 1)] + [rnd.randint(0, 31) for _ in range(8)]
        p.wmem(REC, blob)
        p.wmem(S["ROOM_VISITS"], [0] * 12)
        p.wb(S["ROOM_VISITS"] + cur, visits)
        p.wb("LP_RESPAWNS", resp)
        p.wb("TRK_PREV", prev if prev is not None else cur)
        p.wb("TRK_PHASE", 0x80)
        now = (p.rw("TURN_COUNTER") >> 2) & 255
        for r in range(NR):
            p.wb(desc_off(r, RD_STAMP), (now - (60 if r in stamp_old else 5)) & 255)
        return now

    # G1: unvisited targets: p ~ 0.75, one room + 1, never the lair / Sanctum / current room, LP_RESPAWNS + 1
    ev, bad, n = 0, [], 120
    for k in range(n):
        setup({cur}, {}, set())
        p.wmem(S["RNG_STATE"], [rnd.randint(1, 255), rnd.randint(1, 255)])
        before = list(p.z.read_memory(REC, NREC))
        far0(p, "rsp_run")
        after = list(p.z.read_memory(REC, NREC))
        ch = [r for r in range(NR) if before[9 * r] != after[9 * r]]
        if p.rb("LP_RESPAWNS") == 1:
            ev += 1
            if len(ch) != 1 or ch[0] not in others or after[9 * ch[0]] != before[9 * ch[0]] + 1:
                bad.append((ch, p.rb("LP_RESPAWNS")))
        elif ch or p.rb("LP_RESPAWNS") != 0:
            bad.append(("noevent", ch))
    check(f"G1 D{d} first entry, unvisited rooms: {ev}/{n} events (p 0.75), each = one eligible room's quota + 1",
          not bad and 0.62 * n <= ev <= 0.88 * n, (ev, bad[:3]))
    # G2: not a first entry (ROOM_VISITS 2): nothing, the RNG untouched
    setup({cur}, {}, set(), visits=2)
    rng0 = list(p.z.read_memory(S["RNG_STATE"], 2))
    r0 = list(p.z.read_memory(REC, NREC))
    far0(p, "rsp_run")
    check("G2 not a first entry: no record change, RNG_STATE untouched", list(p.z.read_memory(REC, NREC)) == r0
          and p.rb("LP_RESPAWNS") == 0 and list(p.z.read_memory(S["RNG_STATE"], 2)) == rng0, p.rb("LP_RESPAWNS"))
    # G3: the cap and the boss's death
    for tag, resp, dead in (("RESPAWN_MAX", RM.RESPAWN_MAX, False), ("boss dead", 0, True)):
        lf = p.rb("LVL_FLAGS")
        if dead:
            p.wb("LVL_FLAGS", lf | S["LF_GRATE_OPEN"])
        got = 0
        for k in range(30):
            setup({cur}, {}, set(), resp=resp)
            p.wmem(S["RNG_STATE"], [rnd.randint(1, 255), rnd.randint(1, 255)])
            r0 = list(p.z.read_memory(REC, NREC))
            far0(p, "rsp_run")
            got += list(p.z.read_memory(REC, NREC)) != r0
        check(f"G3 {tag}: 30 first entries, no record change", got == 0 and p.rb("LP_RESPAWNS") == resp, got)
        p.wb("LVL_FLAGS", lf)
    # G4: every room visited: a room >= 2 exits away and unseen >= 150 turns; an LEK_RESPAWN entry appended
    far_old = {r for r in others if r not in nb}
    hits, bad = 0, []
    for k in range(60):
        setup(set(pr), {r: 1 for r in pr}, far_old | set(nb))
        p.wmem(S["RNG_STATE"], [rnd.randint(1, 255), rnd.randint(1, 255)])
        before = list(p.z.read_memory(REC, NREC))
        far0(p, "rsp_run")
        after = list(p.z.read_memory(REC, NREC))
        ch = [r for r in range(NR) if before[9 * r] != after[9 * r]]
        if p.rb("LP_RESPAWNS"):
            hits += 1
            r = ch[0] if ch else -1
            ok = (len(ch) == 1 and r in far_old and after[9 * r] == before[9 * r] + 1
                  and after[9 * r + 1 + 2 * (before[9 * r] & 7)] & 0x80)
            if not ok:
                bad.append((ch, far_old))
        elif ch:
            bad.append(("noevent", ch))
    check(f"G4 D{d} all visited: {hits}/60 events, each into a room unseen >= 150 turns, not the current room / its "
          f"neighbours {sorted(nb)}, an LEK_RESPAWN entry", not bad and (hits > 0 or not far_old), (hits, bad[:3], sorted(far_old)))
    # G5: recently seen rooms are never chosen (all stamps 5 x 4 = 20 turns old)
    got = 0
    for k in range(40):
        setup(set(pr), {r: 1 for r in pr}, set())
        p.wmem(S["RNG_STATE"], [rnd.randint(1, 255), rnd.randint(1, 255)])
        r0 = list(p.z.read_memory(REC, NREC))
        far0(p, "rsp_run")
        got += list(p.z.read_memory(REC, NREC)) != r0
    check("G5 all visited and seen < 150 turns ago: skipped, no record change", got == 0, got)
    # G6: the stamp of the room just left = (TURN_COUNTER >> 2) & 255
    other = others[0]
    now = setup({cur}, {}, set(), visits=2, prev=other)
    far0(p, "rsp_run")
    check("G6 rsp_run stamps TRK_PREV with TURN_COUNTER >> 2", p.rb(desc_off(other, RD_STAMP)) == now,
          (p.rb(desc_off(other, RD_STAMP)), now))


def heavy_cost(p, L, rnd):
    cur = p.rb("CUR_ROOM")
    sk, rat, gob = S["K_SKELETON"], S["K_RAT"], S["K_GOBLIN"]
    p.wmem(S["LP_KINDS"], [sk, rat, sk, rat] * 2)
    p.wb("LVL_LAIR", S["ROOM_NONE"])
    p.wb("LVL_SANCTUM", S["ROOM_NONE"])
    p.wb("TRK_PREV", cur)
    p.wb("LVL_FLAGS", p.rb("LVL_FLAGS") & ~S["LF_GRATE_OPEN"] & 255)
    rec = []
    for r in range(NR):
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
    print(f"[info] heavy state ({NR - 1} x 3 entries, 450 seeds): worst far6 trk_run no spawn {sc} T, with a spawn {sp} T",
          flush=True)
    # LARGER-D T5: 11 heavy rooms on the 3x4 grid (was 8): 13.1k / 17.7k T measured -> bound 20k (was 15k)
    check("T2 heavy state: trk_run <= 20k T (on the idle INPUT tick, ~30-35k T: far under the 126k cap)",
          sp <= 20000 and sc <= 20000, (sc, sp))


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
            recs = [None if r not in pr else {"visited": True, "ents": []} for r in range(NR)]
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
                time_off_cases(p, L, rnd)
                L = Lair(p, d, seed)
                trk_entry_cases(p, L, rnd)
                heavy_cost(p, L, rnd)
                L = Lair(p, d, seed)
                progress_cases(p, L, rnd)
                L = Lair(p, d, seed)
                prev_cases(p, L)
    print(f"[info] worst far6 trk_run with a spawn: {worst[0]} T ({worst[1]})", flush=True)
    # Sampled cases share the T2 heavy-state bound (15k T on the idle INPUT tick, far under the
    # 126k cap): one fixed RNG stream feeds every depth, so a layout change on D1 (H1) reshuffles
    # which D8 states get drawn (worst 11.2k on b25e043, 12.5k after H1 with no code change).
    check("T trk_run (far6 incl.) <= 15k T", 0 < worst[0] <= 15000, worst)
    print(f"trickle: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
