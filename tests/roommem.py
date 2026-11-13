#!/usr/bin/env python3
"""ROOM-MEM (plan.md, user 2026-11-03; game.md §9.4.2 / §9.4.8 (d)): the last TWO rooms
left remember their monsters. A banked monster's slot is PARKED (level_defs.asm LPK_PARK);
on re-entry it tries its saved cell first (5-col arrival gap, no stream step) and is
restored in place: position, facing, hp, statuses, ranged cooldown kept, the summon counter
reset. PENDING followers follow the hero back out.

Part R (generated D1, seed_fixed, the real do_exit):
  R1  A -> B: B's residents spawn (first visit); their statuses / cooldown / facing poked
  R2  B -> A: B's record holds them, their slots are parked in place (x, y, facing, hp,
      ST_* bytes), no active slot outside CUR_ROOM
  R3  A -> B: every one is back in its own slot, same x / y / facing / hp / ST_* bytes,
      cooldown kept, summon counter 0; == levelgen.lp_enter with the parked list
  R4  PENDING followers: one on the hero's arrival box follows him back to A (PENDING
      there, not in B's record); one far from the door stays (B's record + parked)
Part S (stub transitions: far3 lp_transition as do_exit runs it, same game):
  S1  two-room depth: X -> Y -> Z -> X restores X exactly (A -> B -> C -> A); parked rooms
      after each step == the two last rooms left
  S2  a third room evicts the oldest: X -> W leaves {X, Z}; Y is then re-placed (model
      with no parked list)
  S3  kill then ping-pong: a dead one never comes back, no stale body
  S4  blocked saved cell: the hero arrives on it -> tries 1-8 (model), statuses kept
  S5  lair: the boss takes its post (not its saved cell), its hp and status kept
  R5  a ready ranged monster (Slinger, counter 0) comes back with counter 1: the first monster
      phase after the return only counts down (no shot), user 2026-11-03
  ADV (reviewer) 8 parked bodies + a FRESH room, a status through the eviction, the evicted
      room re-placed from its record; lp_transition worst <= LP_TRANS_GUARD (70,000 T)
  S6  level change: the real level_descend leaves no parked slot
Run with ZRCP_PORT=<port> (WZ_BUILD_DIR for a variant build).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import levelgen as G                                    # noqa: E402
import room_model                                       # noqa: E402
from game_lib import Harness, S, EMU_ARGS               # noqa: E402
from lp import (T, w16, parked_of, want_slots, G_entries, stand_y, mask, bank_model,   # noqa: E402
                gold_of, LPB)

EF_ACTIVE, EF_HOSTILE, EF_LEFT = 1, 4, S["EF_LEFT"]
EF_PENDING, EF_WALKIN, EF_DYING = S["EF_PENDING"], S["EF_WALKIN"], S["EF_DYING"]
PARK = S["LPK_PARK"]
GS_PLAYING = S["GS_PLAYING"]
STRIDE = S["P_ENT_STRIDE"]
E_RCD = S["E_POT"]
RCD_SUMMON = S["RCD_SUMMON"]
# lp_transition (2 x lp_bank + lp_enter + follow_admit) on the frozen transition screen: <= 70,000 T
# = under one 70,908-T frame (game.md §9.4.3 keeps lp_enter alone <= 46k). Measured: 4 bodies parked
# + 4 restored / re-placed (ADV, tests/lp.py A8) up to ~58.5k T; the 4-entry re-placement itself predates
# ROOM-MEM (lp_find adds <= ~0.7k T a unit of a VISITED room)
LP_TRANS_GUARD = 70000


def st_bytes(p, s_):
    return (p.rb(S["ST_FLAGS"] + s_), p.rb(S["ST_T1"] + s_), p.rb(S["ST_T2"] + s_), p.rb(S["ST_X"] + s_))


def body(p, s_):
    """what ROOM-MEM must keep: (slot, kind, x, y, facing, hp, ST_* bytes, cooldown bits)."""
    e = p.ent(s_)
    rcd = p.rb(S["P_ENTITIES"] + s_ * STRIDE + E_RCD)
    return (s_, e["KIND"], e["X"], e["Y"], bool(e["FLAGS"] & EF_LEFT), e["HP"], st_bytes(p, s_), rcd & 3)


def parked_rooms(p):
    return sorted({p.ent(s_)["ROOM"] & 0x0F for s_ in range(1, 16) if p.ent(s_)["ROOM"] & PARK})


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {detail}", flush=True)
        run(p, check)
        print(f"roommem: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def run(p, check):
    for M in (0x2468, 0x1357, 0x4242, 0x0BAD, 0x7171, 0x3C3C):
        if game(p, check, M):
            return
    check("R setup: a seed with a 2-room horizontal edge and >= 2 residents in B", False, "")


def game(p, check, M):
    p.proto_start = 0
    p.load()
    p.wait_state(S["GS_SELECT"])
    p.wb("seed_fixed", 1)
    p.wmem(S["seed_value"], w16(M))
    p.wb("INPUT_REPEAT", 0)
    p.wb("ANIM_FREEZE", 1)
    p.wb("INPUT_SRC", 1)
    p.hold("1")
    p.wait_state(GS_PLAYING)
    p.release()
    p.settle(3)
    blk = p.block()
    st = p.rb("CUR_ROOM")
    lair = blk[S["LVL_LAIR"] - G.BASE]
    sanct = blk[S["LVL_SANCTUM"] - G.BASE]
    kw = p.kb(S["K_KNIGHT"], "KT_BW")
    kh = p.kb(S["K_KNIGHT"], "KT_BH")

    def ingame(code, tag):
        pc0 = p.pc()
        ok, _ = p.code(code, game=True)
        p.z.cmd("set-register PC=%d" % pc0)
        if not ok:
            check(f"stub {tag} ran", ok, "")

    def put_hero(r, x, s_, left):
        p.wb("CUR_ROOM", r)
        p.set_ent(0, ROOM=r, X=x, Y=stand_y(s_, kh), PX=x * 8, PY=stand_y(s_, kh) * 8,
                  FLAGS=EF_ACTIVE | 2 | (EF_LEFT if left else 0), MODE=0, DVIS=0)
        ingame([0x3E, r, 0xCD] + w16(S["room_show"]) + [0xCD] + w16(S["vis_reset"])
               + [0xCD] + w16(S["present_full"]), f"show room {r}")
        p.settle(2)

    def walk_out(r, side, s_, place=True):
        x, key = (2, "H") if side == "L" else (32 - 2 - kw, "L")
        if place:
            put_hero(r, x, s_, side == "L")
        dest = r - 1 if side == "L" else r + 1
        for _ in range(8):
            if p.rb("CUR_ROOM") == dest:
                break
            p.turn(key)
        p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
        p.settle(2)
        return p.rb("CUR_ROOM") == dest

    def invariant(tag):
        bad = [x for x in p.slots() if x[2] != p.rb("CUR_ROOM")]
        check(f"{tag}: every active monster slot is in CUR_ROOM (§9.4.5)", bad == [], bad)

    pick = None
    for r in range(9):
        ex = room_model.field(blk, r, "RD_EXITS")
        if ex & S["RDX_R"] and r != st and r + 1 not in (lair, st, sanct) and r not in (lair, sanct):
            pick = (r, r + 1, 1 if ex & S["RDX_RS1"] else 0)
            break
    if not pick:
        return False
    a, b, s_ = pick
    ei = S["EDGE_TAB"] + room_model.edge_index(b, "L")
    p.wb(ei, p.rb(ei) | S["EG_OPEN"])
    # R1: A -> B. A is entered by put_hero (no lp_enter): make it an empty VISITED room, or
    # lp_bank would turn its FRESH quota into VISITED entries {0, 0} (a test artefact)
    p.wb(S["LP_REC"] + 9 * a, S["LR_VISITED"])
    if not walk_out(a, "R", s_):
        return False
    sl = p.slots()
    if len(sl) < 2:
        print(f"[roommem] seed {M:#06x}: room {b} has {len(sl)} resident(s), next seed", flush=True)
        return False
    print(f"[roommem] seed {M:#06x}: rooms {a} -> {b} (storey {s_}), {len(sl)} residents", flush=True)
    # every resident held (no move while the hero walks), statuses / cooldown / facing poked
    for i, x in enumerate(sl):
        s0 = x[0]
        if i == 0:
            p.wb(S["ST_FLAGS"] + s0, S["HOLD_FROZEN"])
            p.wb(S["ST_T1"] + s0, 0x90)
            p.set_ent(s0, HP=max(1, x[6] - 1))
            p.wb(S["P_ENTITIES"] + s0 * STRIDE + E_RCD, (p.rb(S["P_ENTITIES"] + s0 * STRIDE + E_RCD) & 0xC0) | 0x0C | 2)
        else:
            p.wb(S["ST_FLAGS"] + s0, S["HOLD_ASLEEP"] | (1 << S["STS_WEAK_BIT"]))
            p.wb(S["ST_T1"] + s0, 0x90)
            p.wb(S["ST_T2"] + s0, 0x07)
            p.set_ent(s0, FLAGS=x[5] ^ EF_LEFT)
    # R2: B -> A
    ok = walk_out(b, "L", s_)
    pre = [body(p, x[0]) for x in sl]
    pk = parked_of(p, b)
    ent = G_entries(p.lp(), b)
    check(f"R2 back in {a}: room {b}'s record holds {len(sl)} (kind, hp)",
          ok and sorted((e[0] & 31, e[1]) for e in ent) == sorted((q[1], q[5]) for q in pre), (ok, ent, pre))
    check(f"R2: {len(sl)} slots parked in place (E_ROOM = {b} | LPK_PARK, EF_ACTIVE clear)",
          [q[4] for q in pk] == [x[0] for x in sl]
          and all(not p.ent(x[0])["FLAGS"] & EF_ACTIVE and p.ent(x[0])["FLAGS"] for x in sl), (pk, sl))
    check("R2: parked bodies kept x / y (held: did not move) and the poked facing / status",
          all(q[2] == x[3] and q[3] == x[4] for q, x in zip(pre, sl))
          and pre[0][6][0] == S["HOLD_FROZEN"] and all(q[6][0] & 3 == S["HOLD_ASLEEP"] for q in pre[1:])
          and all(q[4] != bool(x[5] & EF_LEFT) for q, x in zip(pre[1:], sl[1:])), (pre, sl))
    invariant("R2")
    # R3: A -> B again
    lp_b = p.lp()
    in_a = [x for x in p.slots() if x[2] == a]          # A's residents (spawned on R2's entry) get banked
    ga = {x[0]: gold_of(p, x[0]) for x in in_a}
    ok = walk_out(a, "R", s_)
    got = p.slots()
    post = [body(p, q[0]) for q in pre]
    wl, out = G.lp_enter(blk, bank_model(lp_b, a, in_a, ga), b, s_, 1, kw, f3=True, parked=pk)
    rb = S["LP_REC"] - LPB + b * S["LR_STRIDE"]
    check(f"R3 re-entered {b}: same slots, x, y, facing, hp, ST_* bytes, cooldown ({len(pre)} bodies)",
          ok and post == pre, (pre, post))
    check("R3: the summon counter reset on the poked one (RCD_SUMMON 0), the cooldown bits kept",
          p.rb(S["P_ENTITIES"] + pre[0][0] * STRIDE + E_RCD) & RCD_SUMMON == 0
          and p.rb(S["P_ENTITIES"] + pre[0][0] * STRIDE + E_RCD) & 3 == 2,
          hex(p.rb(S["P_ENTITIES"] + pre[0][0] * STRIDE + E_RCD)))
    check("R3: == levelgen.lp_enter of the record + its parked bodies (try 0, no stream step)",
          got == want_slots(p, blk, b, out, got=got) and p.lp()[rb:rb + 9] == wl[rb:rb + 9]
          and all(q for q in G.LP_OUT_SLOT), (got, out, G.LP_OUT_SLOT, p.lp()[rb:rb + 9].hex(), wl[rb:rb + 9].hex()))
    check(f"R3: no slot parked for {b} any more", not [q for q in parked_of(p, b)], parked_of(p, b))
    invariant("R3")
    # R4: PENDING followers. The hero stands at B's left edge (x 2); a Goblin PENDING on his
    # box (x 1) follows him back to A; another PENDING one at x 20 stays in B.
    for x in p.slots():
        p.set_ent(x[0], FLAGS=0, ROOM=0)
    k = S["K_GOBLIN"]
    gh = p.kb(k, "KT_BH")
    gy = stand_y(s_, gh)
    for s0, gx in ((6, 1), (7, 20)):
        p.set_ent(s0, KIND=k, ROOM=b, FLAGS=EF_ACTIVE | EF_HOSTILE | EF_PENDING | EF_WALKIN, X=gx, Y=gy,
                  PX=gx * 8, PY=gy * 8, MODE=0, DVIS=0, HP=5, MAXHP=6)
        for arr in ("ST_FLAGS", "ST_T1", "ST_T2", "ST_X"):
            p.wb(S[arr] + s0, 0)
    lp_b = p.lp()
    put_hero(b, 2, s_, True)
    ok = walk_out(b, "L", s_, place=False)
    e6, e7 = p.ent(6), p.ent(7)
    ent = G_entries(p.lp(), b)
    check(f"R4 the PENDING follower on the hero's box followed him back to {a} (PENDING, x 31 - w)",
          ok and e6["ROOM"] == a and e6["FLAGS"] & EF_ACTIVE and e6["FLAGS"] & EF_PENDING
          and e6["X"] == 31 - p.kb(k, "KT_BW"), (ok, e6))
    check(f"R4 the far PENDING one stayed: in {b}'s record and parked there",
          e7["ROOM"] == b | PARK and not e7["FLAGS"] & EF_ACTIVE
          and [(e[0] & 31, e[1]) for e in ent].count((k, 5)) == 1, (e7, ent))
    invariant("R4")
    # R5: a READY ranged monster keeps the first-phase grace after the return (user 2026-11-03):
    # the far Goblin parked in B becomes a Slinger (tier row, Goblin frames) with its cooldown
    # counter 0 (= ready: stored c XOR 1 = 1); back in B its counter is 1 and the first monster
    # phase only counts it down (no shot, the hero's hp kept)
    ks = S["K_SLINGER"]
    rb_ = S["LP_REC"] + 9 * b
    rec = list(p.z.read_memory(rb_, 9))
    ie = next((i for i in range(rec[0] & 7) if rec[1 + 2 * i] & 31 == k and rec[2 + 2 * i] == 5), None)
    if ie is not None and p.ent(7)["ROOM"] == b | PARK:
        p.wb(rb_ + 1 + 2 * ie, (rec[1 + 2 * ie] & ~31 & 255) | ks)
        p.set_ent(7, KIND=ks)
        p.wb(S["P_ENTITIES"] + 7 * STRIDE + E_RCD, 1)
        for arr in ("ST_FLAGS", "ST_T1", "ST_T2", "ST_X"):
            p.wb(S[arr] + 7, 0)
        ok = walk_out(a, "R", s_)
        e7 = p.ent(7)
        rcd0 = p.rb(S["P_ENTITIES"] + 7 * STRIDE + E_RCD) & 3
        check("R5 the ready Slinger is back in its slot with its counter raised to 1 (stored 0): the grace",
              ok and e7["KIND"] == ks and e7["FLAGS"] & EF_ACTIVE and e7["ROOM"] == b and rcd0 == 0, (ok, e7, rcd0))
        hp0 = p.ent(0)["HP"]
        p.turn("WAIT")
        p.until(lambda: p.idle(), 300)
        rcd1 = p.rb(S["P_ENTITIES"] + 7 * STRIDE + E_RCD) & 3
        check("R5 the first monster phase after the return: no shot (the counter only counted down to 0, "
              "the hero's hp kept)", rcd1 == 1 and p.ent(0)["HP"] == hp0, (rcd1, hp0, p.ent(0)["HP"]))
    else:
        check("R5 setup: the far Goblin parked in B with its entry", False, (rec, p.ent(7)))
    if os.environ.get("RM_DEBUG"):
        ra = S["LP_REC"] + 9 * a
        print("[debug] after R4: rec a", bytes(p.z.read_memory(ra, 9)).hex(), "rec b",
              bytes(p.z.read_memory(S["LP_REC"] + 9 * b, 9)).hex(), flush=True)
        for q in range(16):
            e = p.ent(q)
            print("[debug] slot", q, e["KIND"], e["ROOM"], hex(e["FLAGS"]), e["X"], e["Y"], e["HP"], flush=True)
    part_s(p, check, blk, st, lair, sanct, kw, kh, b)
    return True


def part_s(p, check, blk, st, lair, sanct, kw, kh, cur):
    """Stub transitions (far3 lp_transition with the hero already placed, as do_exit .lpt)."""
    def xfer(dst, hx=1, hs=0):
        src = p.rb("CUR_ROOM")
        prev = p.rb("TRK_PREV")
        old = set(parked_rooms(p))
        lp0, pk, blk_ = p.lp(), parked_of(p, dst), blk
        alive = [x for x in p.slots() if x[2] == src]
        gold = {x[0]: gold_of(p, x[0]) for x in alive}
        p.set_ent(0, X=hx, Y=stand_y(hs, kh))
        p.wmem(S["CAND_LIST"], [0xFF] * 16)
        p.wb("FOLLOW_N", 0)
        p.wb("EXIT_DEST", dst)
        pc0 = p.pc()
        ok, ts = p.code([0x21] + w16(S["lp_transition"]) + [0xCD] + w16(S["far3"]), game=True)
        p.z.cmd("set-register PC=%d" % pc0)
        p.wb("TRK_PREV", src)
        p.wb("CUR_ROOM", dst)
        p.set_ent(0, ROOM=dst)
        lpb = bytearray(bank_model(lp0, src, alive, gold))
        try:
            wl, out = G.lp_enter(blk_, bytes(lpb), dst, hs, hx, kw, f3=True, parked=pk)
        except KeyError:
            ro = S["LP_REC"] - LPB + dst * S["LR_STRIDE"]
            print("[debug]", src, dst, lp0[ro:ro + 9].hex(), lpb[ro:ro + 9].hex(), alive, pk, flush=True)
            raise
        got = [x for x in p.slots()]
        model_ok = got == want_slots(p, blk_, dst, out, got=got)
        # the parked rooms: {src} (if a body was banked) + prev if it was parked; dst consumed
        # (a body of dst no cell was found for stays parked there)
        want = (({src} if [x for x in alive if not x[5] & EF_DYING] else set()) | (old & {prev})) - {dst}
        stale = {dst} if any(p.ent(q)["ROOM"] == dst | PARK for q in range(1, 16)) else set()
        model_ok = model_ok and set(parked_rooms(p)) == want | stale
        return ok, ts, model_ok, (got, out, pk, sorted(want | stale), parked_rooms(p))

    rooms = [r for r in range(9) if room_model.field(blk, r, "RD_FLAGS") & S["RDF_PRESENT"]
             and r not in (st, lair, sanct, cur)]
    if len(rooms) < 4:
        check("S setup: 4 plain rooms", False, rooms)
        return
    # X must have residents (else it banks nothing and is never parked: S1/S2 assert X parked); the
    # generator decides which rooms are populated, so probe the model on the fresh record
    def residents(r):
        try:
            return len(G.lp_enter(blk, bytes(p.lp()), r, 0, 1, kw, f3=True, parked=[])[1])
        except KeyError:
            return 0
    rooms.sort(key=lambda r: not residents(r))              # stable: populated rooms first
    X, Y, Z, W = rooms[:4]
    tsmax = 0
    ok, ts, mo, d = xfer(X)
    tsmax = max(tsmax, ts)
    sx = [body(p, x[0]) for x in p.slots()]
    check(f"S1 enter {X} (first visit) == model", ok and mo, d)
    if sx:
        s0 = sx[0][0]
        p.wb(S["ST_FLAGS"] + s0, S["MIND_FEAR"])
        p.wb(S["ST_T1"] + s0, 0x05)
        sx[0] = body(p, s0)
    for dst in (Y, Z):
        ok, ts, mo, d = xfer(dst)
        tsmax = max(tsmax, ts)
        check(f"S1 -> {dst}: == model; parked rooms {parked_rooms(p)} == the two last left",
              ok and mo and X in parked_rooms(p), d)
    ok, ts, mo, d = xfer(X)
    tsmax = max(tsmax, ts)
    back = [body(p, q[0]) for q in sx]
    check(f"S1 {X} -> {Y} -> {Z} -> {X}: {X}'s bodies exactly back (slot, x, y, facing, hp, statuses)",
          ok and back == sx and mo, (sx, back, d))
    check(f"S1: parked rooms now {parked_rooms(p)} (the two last left: {Z}, {Y})",
          set(parked_rooms(p)) <= {Y, Z} and Z in parked_rooms(p), parked_rooms(p))
    ok, ts, mo, d = xfer(W)
    tsmax = max(tsmax, ts)
    check(f"S2 {X} -> {W}: parked rooms {parked_rooms(p)}: {Y}, the oldest, evicted",
          ok and mo and Y not in parked_rooms(p) and X in parked_rooms(p), (d, parked_rooms(p)))
    ok, ts, mo, d = xfer(Y)
    tsmax = max(tsmax, ts)
    check(f"S2 -> {Y}: nothing parked for it, re-placed by the stream (model with no parked list)",
          ok and mo and d[2] == [], d)
    # S3: kill one, ping-pong (in a room that has residents: Y, else X / W)
    for cand in (X, W):
        if p.slots():
            break
        xfer(cand)
    Y = p.rb("CUR_ROOM")
    Z = next(r for r in rooms if r != Y)
    print(f"[roommem] S3 / S4 in room {Y} ({len(p.slots())} residents), away to {Z}", flush=True)
    # S4: blocked saved cell. Leave Y, come back with the hero arriving on a body's cell.
    sy = p.slots()
    if sy:
        s0, x0, y0 = sy[0][0], sy[0][3], sy[0][4]
        p.wb(S["ST_FLAGS"] + s0, S["MIND_CONFUSED"])
        p.wb(S["ST_T1"] + s0, 0x04)
        stb = st_bytes(p, s0)
        hs = 1 if y0 >= 9 else 0
        ok, ts, mo, d = xfer(Z)
        ok2, ts, mo2, d2 = xfer(Y, hx=x0, hs=hs)
        tsmax = max(tsmax, ts)
        e = p.ent(s0)
        check(f"S4 {Y}: the hero arrives on a body's saved cell -> tries 1-8 (== model), its status kept",
              ok and ok2 and mo2 and (not e["FLAGS"] & EF_ACTIVE                  # no cell: in the record
                                      or ((e["X"], e["Y"]) != (x0, y0) and st_bytes(p, s0) == stb)),
              (x0, y0, e, d2))
    sy = p.slots()
    if sy:
        p.set_ent(sy[0][0], FLAGS=0)                    # killed (anim_tick frees the slot)
        keep = [body(p, x[0]) for x in sy[1:]]
        n0 = len(sy) + len(G_entries(p.lp(), Y))
        ok, ts, mo, d = xfer(Z)
        tsmax = max(tsmax, ts)
        ok2, ts, mo2, d2 = xfer(Y)
        tsmax = max(tsmax, ts)
        back = [body(p, q[0]) for q in keep]
        n1 = len(p.slots()) + len(G_entries(p.lp(), Y))
        check(f"S3 kill one in {Y}, {Y} -> {Z} -> {Y}: count {n0} -> {n1}, the others exactly back",
              ok and ok2 and mo and mo2 and n1 == n0 - 1 and back == keep, (n0, n1, keep, back, d2))
    # S5: the lair
    ok, ts, mo, d = xfer(lair, hx=1, hs=0)
    tsmax = max(tsmax, ts)
    bl = [x for x in p.slots() if (x[1] | gold_of(p, x[0])) == p.rb("LP_BOSS")]
    check(f"S5 enter the lair {lair}: == model (posts)", ok and mo and len(bl) == 1, (d, bl))
    if bl:
        s0 = bl[0][0]
        p.set_ent(s0, HP=bl[0][6] - 2)
        p.wb(S["ST_FLAGS"] + s0, S["HOLD_STUNNED"])
        p.wb(S["ST_T1"] + s0, 0x30)
        hp, stb = p.ent(s0)["HP"], st_bytes(p, s0)
        ok, ts, mo, d = xfer(Y)
        ok2, ts, mo2, d2 = xfer(lair, hx=1, hs=0)
        tsmax = max(tsmax, ts)
        e = p.ent(s0)
        check("S5 lair -> out -> lair: the boss is back on its post (== model: lp_post, not the saved cell), "
              "hp and status kept, same slot",
              ok and ok2 and mo2 and e["FLAGS"] & EF_ACTIVE and e["HP"] == hp and st_bytes(p, s0) == stb, (e, d2))
    print(f"[roommem] S lp_transition (DI, incl. far3) worst {tsmax} T", flush=True)
    check(f"S lp_transition worst {tsmax} T <= {LP_TRANS_GUARD}", tsmax <= LP_TRANS_GUARD, tsmax)
    part_adv(p, check, blk, st, lair, sanct, kw, kh, cur)
    # S6: level change
    pc0 = p.pc()
    ok, _ = p.code([0x3E, 1, 0x32] + w16(S["LVL_DEPTH"]) + [0xCD] + w16(S["level_descend"]), game=True)
    p.z.cmd("set-register PC=%d" % pc0)
    p.release()
    p.settle(4)
    check("S6 level change (level_descend D1 -> D2): no slot parked, no stale parked mark",
          p.rb("LVL_DEPTH") == 2 and parked_rooms(p) == [], (p.rb("LVL_DEPTH"), parked_rooms(p)))


def part_adv(p, check, blk, st, lair, sanct, kw, kh, cur):
    """ADV (reviewer, 2026-11-03): 8 parked bodies (two rooms x 4) + a FRESH room's spawns, a status
    through the eviction, an evicted room re-placed from its record (the lp_transition worst)."""
    rooms = [r for r in range(9) if room_model.field(blk, r, "RD_FLAGS") & S["RDF_PRESENT"]
             and r not in (st, lair, sanct, cur)]
    X, Y, Z = rooms[:3]
    lpk = p.rb(S["LP_KINDS"])
    kh0, hp0 = p.kb(lpk, "KT_BH"), p.kb(lpk, "KT_HP")
    for s_ in range(1, 16):
        p.set_ent(s_, FLAGS=0, ROOM=0)

    def mk(slot, room, x, active):
        p.set_ent(slot, KIND=lpk, ROOM=room | (0 if active else PARK), X=x, Y=stand_y(0, kh0),
                  FLAGS=(EF_ACTIVE if active else 0) | EF_HOSTILE, HP=hp0 - 1, MAXHP=hp0, MODE=0, DVIS=0)
        for a_ in ("ST_FLAGS", "ST_T1", "ST_T2", "ST_X"):
            p.wb(S[a_] + slot, 0)
    xs = [9, 13, 17, 21]
    for i in range(4):
        mk(1 + i, X, xs[i], False)
        mk(5 + i, Y, xs[i], True)
    p.wmem(S["LP_REC"] + 9 * X, [0x80 | 4] + [lpk, hp0 - 1] * 4)
    p.wmem(S["LP_REC"] + 9 * Y, [0x80] + [0xEE] * 8)
    p.wb(S["ST_FLAGS"] + 5, S["HOLD_ASLEEP"])
    p.wb(S["ST_T1"] + 5, 0x90)
    stb5 = st_bytes(p, 5)
    p.wb("CUR_ROOM", Y)
    p.set_ent(0, ROOM=Y)
    p.wb("TRK_PREV", X)

    def xfer(dst, hx=1, hs=0):
        src = p.rb("CUR_ROOM")
        p.set_ent(0, X=hx, Y=stand_y(hs, kh))
        p.wmem(S["CAND_LIST"], [0xFF] * 16)
        p.wb("FOLLOW_N", 0)
        p.wb("EXIT_DEST", dst)
        pc0 = p.pc()
        ok, ts = p.code([0x21] + w16(S["lp_transition"]) + [0xCD] + w16(S["far3"]), game=True)
        p.z.cmd("set-register PC=%d" % pc0)
        p.wb("TRK_PREV", src)
        p.wb("CUR_ROOM", dst)
        p.set_ent(0, ROOM=dst)
        return ok, ts

    ok, ts1 = xfer(Z)
    act = [x for x in p.slots() if x[2] == Z]
    left = G_entries(p.lp(), Z)
    check("ADV1 Y -> Z with X, Y 4 parked each: X, Y stay parked, Z spawns, nothing left for want of a slot",
          ok and set(parked_rooms(p)) == {X, Y} and (len(left) == 0 or len(act) + 8 < 15), (act, left))
    ok, ts2 = xfer(Y)
    e5 = p.ent(5)
    check("ADV2 Z -> Y: Y restored with the asleep status, X evicted (E_ROOM 0, flags 0)",
          ok and e5["FLAGS"] & EF_ACTIVE and st_bytes(p, 5) == stb5 and X not in parked_rooms(p)
          and all(p.ent(s_)["FLAGS"] == 0 and p.ent(s_)["ROOM"] == 0 for s_ in range(1, 5)),
          [p.ent(s_) for s_ in range(1, 5)])
    ok, ts3 = xfer(X)
    ax = [x for x in p.slots() if x[2] == X]
    check("ADV3 Y -> X (evicted): re-placed from the record, 4 bodies",
          ok and len(ax) + len(G_entries(p.lp(), X)) == 4, ax)
    tsm = max(ts1, ts2, ts3)
    print(f"[roommem] ADV lp_transition {ts1} / {ts2} / {ts3} T", flush=True)
    check(f"ADV lp_transition worst {tsm} T <= {LP_TRANS_GUARD} (one frame: 70,908)", tsm <= LP_TRANS_GUARD, tsm)


if __name__ == "__main__":
    sys.exit(main())
