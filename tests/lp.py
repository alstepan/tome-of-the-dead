#!/usr/bin/env python3
"""LP (game.md §9.4.1-9.4.7): lazy monster population, Z80 vs tools/levelgen.py.

Part A (unit, stubs at LOWRAM_END_3B under DI, from the loaded snapshot):
  A1  lp_budget block == levelgen.lp_budget (persistent fields; the scratch
      LP_HX..LP_PL is masked) for fixed + random (depth, seed) pairs
  A2  lp_enter of every present room, random arrival box: slots + record ==
      levelgen.lp_enter (§9.4.7 #1, #5), worst T-states (budget <= 15k)
  A3  independent placement properties on the room model (room_model.render_room
      + the build's tile_flags): no ladder / hole within 1 col, solid
      floor under walkers, no body in an arrival box, gap >= 5 cols (8 on tries 1-4) to the
      arrival on its storey, flyers at 9s+1 (§9.4.7 #7)
  A4  bank + re-enter: one monster damaged, one dying; lp_bank -> record ==
      model (exact hp, the dead one gone); ROOM_VISITS + 1, lp_enter again ==
      model (§9.4.7 #3, #4, #8 on the lair's boss)
  A6  lp_mark clips out-of-range runs to the cell map (fix/3d-artefacts)
  A5  visit order: the first-visit contents of every room are the same when
      the rooms are entered in reverse order (§9.4.7 #6)
Part B (game, real do_exit on a generated D1, seed_fixed):
  B1  walk into a neighbour room: slots == levelgen.lp_enter of the record
      read before, invariant: every active non-hero slot in CUR_ROOM (#2)
  B2  damage one, kill one, walk back out and in again: the survivor's hp kept,
      the dead one gone, the old room's record holds them meanwhile (#3, #4)
  B3  followers: a candidate next to the hero is admitted (PENDING into the
      destination), with the destination full (cap) it is banked into the
      room left instead (prototype §3.7 + §9.4.3 step 3)
  A7  3F-T5 sweep: >= 1,000 (depth, seed, hero, LVL) levels, every room entered
      once: the tools/levelgen.py f3 reference (tier roll, escort, golden flag,
      depth-scaled hp) == the Z80 record by record (+ E_MAXHP / E_GOLD of the
      slots), all 8 depths and both heroes; counts the tier rows and golden
      bosses seen (a sweep that never rolls a tier proves nothing)
Run with ZRCP_PORT=<port>.  `--random N` (A1/A2 random pairs, default 40);
`--sweep N` (A7 levels, default 1000; 0 skips it).
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import levelgen as G                                    # noqa: E402
import room_model                                       # noqa: E402
from game_lib import Harness, Proto, S, EMU_ARGS, attr_at, cell_bytes, F3   # noqa: E402

STUB = S["LOWRAM_END_3B"]
RES = STUB + 120
LPB = S["LP_STATE"]
LPN = S["LP_LEN"]
SCR = (S["LP_HX"] - LPB, S["ROOM_VISITS"] - LPB)       # scratch range (masked)
KT = S["kind_tab"]
EF_ACTIVE, EF_HOSTILE, EF_LEFT, EF_PENDING, EF_DYING = 1, 4, S["EF_LEFT"], S["EF_PENDING"], S["EF_DYING"]
GS_PLAYING = S["GS_PLAYING"]
STRIDE = S["P_ENT_STRIDE"]
LP_T_GUARD = 46000                 # lp_enter worst (DI, incl. far3): game.md §9.8 D3-2: worst <= 46k, mean <= 22k (a room entry on a frozen screen, not a tick)


def w16(v):
    return [v & 255, v >> 8]


def gold_of(p, slot):
    """E_GOLD of an entity slot (tests/game_lib.py's E table does not carry it)."""
    return p.rb(S["P_ENTITIES"] + slot * STRIDE + S["E_GOLD"])


def mask(b):
    b = bytearray(b)
    for i in range(*SCR):
        b[i] = 0
    return bytes(b)


class T(Proto):
    def code(self, body, limit=20000000, game=False):
        """DI, SP, body, NOP probe. -> (ok, T). game: in play (no SP reset,
        EI before the probe)."""
        sp = S["WORKSTORE_TOP"]
        pre = [0xF3] if game else [0xF3, 0x31] + w16(sp)
        code = bytes(pre + body + ([0xFB] if game else []) + [0x00, 0x18, 0xFE])
        end = STUB + len(code) - 3
        assert STUB + len(code) <= RES
        self.z.cmd("write-memory %d %s" % (STUB, " ".join(str(b) for b in code)))
        self.z.cmd("set-breakpoint 3 PC=%d" % end)
        self.extra_probes = {end}
        self.z.cmd("set-register PC=%d" % STUB)
        self.z.cmd("reset-tstates-partial")
        self.z.cmd("run %d" % limit)
        ts = int(self.z.cmd("get-tstates-partial"))
        ok = self.pc() == end
        self.z.cmd("set-breakpoint 3")
        self.extra_probes = set()
        return ok, ts

    def far3(self, target, a=None, e=None):
        body = []
        if a is not None:
            body += [0x3E, a]
        if e is not None:
            body += [0x1E, e]
        return self.code(body + [0x21] + w16(S[target]) + [0xCD] + w16(S["far3"]))

    def lp(self):
        return bytes(self.z.read_memory(LPB, LPN))

    def block(self):
        return bytes(self.z.read_memory(G.BASE, G.BLOCK_LEN))

    def wmem(self, addr, data):
        self.z.cmd("write-memory %d %s" % (addr, " ".join(str(b) for b in data)))

    def slots(self):
        out = []
        for s_ in range(1, 16):
            e = self.ent(s_)
            if e["FLAGS"] & EF_ACTIVE:
                out.append((s_, e["KIND"], e["ROOM"], e["X"], e["Y"], e["FLAGS"], e["HP"]))
        return out

    def clear_slots(self):
        for s_ in range(1, 16):
            self.set_ent(s_, FLAGS=0)

    def kb(self, k, off):
        return self.rb(KT + S[off] + k)


def want_slots(p, blk, r, out, first_slot=1):
    """levelgen.lp_enter's placed list -> the slots spawn_one makes (in order)."""
    res = []
    for i, (kb, hp, s_, x, left) in enumerate(out):
        k = kb & S["LEK_KIND_MASK"]
        fly = p.kb(k, "KT_FLAGS") & S["KF_FLYER"]
        y = 9 * s_ + 1 if fly else 9 * s_ + 8 - p.kb(k, "KT_BH")
        fl = EF_ACTIVE | EF_HOSTILE | (EF_LEFT if left else 0) | (kb & S["LEK_RESPAWN"])
        res.append((first_slot + i, k, r, x, y, fl, hp))
    return res


def props(p, blk, r, slots, hs, hx, hw, tf):
    """A3: placement properties from the room model + tile flags, written from
    §9.4.3 (not from lp_legal)."""
    m = room_model.render_room(blk, r, decor=False)
    LAD, HOLE, FLOOR = S["TF_LADDER"], S["TF_HOLE"], S["TF_FLOOR"]
    ex = room_model.field(blk, r, "RD_EXITS")
    bad = []
    for (_, k, _, x, y, fl, _) in slots:
        w, h = p.kb(k, "KT_BW"), p.kb(k, "KT_BH")
        fly = p.kb(k, "KT_FLAGS") & S["KF_FLYER"]
        s_ = 1 if y >= 9 else 0
        if fly and y != 9 * s_ + 1:
            bad.append((k, x, y, "flyer off its band"))
        mg = 1                                      # §9.4.3: footprints +-1 col
        c0, c1 = max(0, x - mg), min(31, x + w - 1 + mg)
        for rr in range(9 * s_, 9 * s_ + 9):
            for c in range(c0, c1 + 1):
                if tf[m[rr * 32 + c]] & (LAD | HOLE):
                    bad.append((k, x, s_, "ladder/hole", c, rr))
        for fr in ((8,) if s_ == 0 else (8, 17)):
            for c in range(c0, c1 + 1):
                if not tf[m[fr * 32 + c]] & FLOOR:
                    bad.append((k, x, s_, "floor gap", c, fr))
        if x < 2 or x + w - 1 > 29:
            bad.append((k, x, "door cols"))
        for bit, s1, lo, hi in ((S["RDX_L"], S["RDX_LS1"], 1, 4), (S["RDX_R"], S["RDX_RS1"], 27, 30)):
            if ex & bit and bool(ex & s1) == (s_ == 1) and x <= hi and x + w - 1 >= lo \
                    and not (s_ == 1 and x == room_model.field(blk, r, "RD_EXITCOL")):
                # 3F-T8 (game.md §9.2 G1): the boss's post ON the grate (c in 5..24, a 4-col body
                # reaches col 27) is exempt; a shifted post / the escort obey the rule
                bad.append((k, x, s_, "arrival box", lo))
        if s_ == hs and not (x >= hx + hw + 5 or x + w + 5 <= hx):
            bad.append((k, x, s_, "within 5 cols of the arrival (8 on tries 1-4)", hx))
        # L2 (game.md 1.1): written from the rules, straight off the descriptor bytes
        o = G.OFF_DESC + r * 16
        mb, mw, pw, pp = blk[o + G.L2_MIDB], blk[o + G.L2_MIDW], blk[o + G.L2_PITW], blk[o + G.D["RD_PITCOL"]]
        if s_ == 0 and mb and x <= mb + mw and x + w - 1 >= mb - 1:
            bad.append((k, x, s_, "inside / against the mid-block", mb, mw))
        if pw and ((s_ == 0 and x <= pp + pw and x + w - 1 >= pp - 1) or
                   (s_ == 1 and x <= pp + pw - 1 and x + w - 1 >= pp)):
            bad.append((k, x, s_, "on a wide-pit fall column", pp, pw))
    return bad


def sync_bodies(p):
    """KROWS carries the game.md body widths; the Z80 kind_tab carries the STAND-IN frames' until T13
    (tools/levelgen.py KNOWN_STANDIN_DIFFS: the Ogre, 4 vs 3). Placement is a function of the Z80 body, so the
    reference runs on kind_tab's KT_BW (hp / weight / flyer stay the doc's: any drift there fails)."""
    diff = []
    for key, v in list(G.KROWS.items()):
        bw = p.kb(v[0], "KT_BW")
        if bw != v[2]:
            G.KROWS[key] = v[:2] + (bw,) + v[3:]
            diff.append(f"{key} {v[2]}->{bw}")
    if diff and not getattr(sync_bodies, "told", False):
        sync_bodies.told = True
        print(f"[lp] reference body widths taken from kind_tab (stand-in frames): {', '.join(diff)}", flush=True)


def scaled_ok(p, sl, out, depth):
    """3F-T5: every placed slot's E_MAXHP == the depth-scaled max (golden 2 x + 6) and E_GOLD == the
    record's LEK_GOLD (levelgen.k3_hp), one slot per placed unit, in order."""
    if len(sl) != len(out):
        return False
    for (slot, *_), (kb, *_) in zip(sl, out):
        if p.ent(slot)["MAXHP"] != G.k3_hp(kb, depth) or gold_of(p, slot) != (kb & G.LEK_GOLD):
            return False
    return True


def part_a(h, p, check, nrand):
    p.load()
    sync_bodies(p)
    tf = p.z.read_memory(S["tile_flags"], 64)
    for n, (w, hp, fly) in G.KINFO.items():
        k = S[n]
        check(f"A0 levelgen.KINFO {n} == kind_tab (BW, HP, flyer)",
              (p.kb(k, "KT_BW"), p.kb(k, "KT_HP"), bool(p.kb(k, "KT_FLAGS") & S["KF_FLYER"])) == (w, hp, fly),
              (p.kb(k, "KT_BW"), p.kb(k, "KT_HP")))
        check(f"A0 levelgen.CLIMBERS {n} == kind_tab KF_CLIMBER (3F-T13bc)",
              bool(p.kb(k, "KT_FLAGS") & S["KF_CLIMBER"]) == (n in G.CLIMBERS), p.kb(k, "KT_FLAGS"))
    rng = random.Random(0x1F9)
    pairs = [(d, s) for d in range(1, 9) for s in (0x0001, 0x1234, 0xBEEF)]
    pairs += [(rng.randint(1, 8), rng.randrange(65536)) for _ in range(nrand)]
    l2set = set()                                   # targeted L2 levels: outside the T mean (they are worst cases)
    for d in range(2, 9):                           # L2: levels with a wide pit / a mid-block
        nw = nm = 0
        for sd in range(1, 20000):
            if nw >= 2 and nm >= 2:
                break
            bb = G.generate(d, sd, f3=F3)
            kw = any(bb[G.OFF_DESC + 16 * r + G.L2_PITW] for r in range(9))
            km = any(bb[G.OFF_DESC + 16 * r + G.L2_MIDB] for r in range(9))
            if (kw and nw < 2) or (km and nm < 2):
                pairs.append((d, sd))
                l2set.add((d, sd))
                nw += kw
                nm += km
    worst = (0, "")
    nb = ne = 0
    tss = []
    for d, seed in pairs:
        lvl = rng.randint(1, 9)
        p.wb("LVL", lvl)
        p.wmem(S["LVL_SEED"], w16(seed))
        ok1, _ = p.far3("level_gen", a=d)
        ok2, tb = p.far3("lp_budget")
        blk = p.block()
        want_b = G.generate(d, seed, f3=F3)
        wl = G.lp_budget(want_b, lvl, f3=True)
        got = p.lp()
        good = ok1 and ok2 and blk == want_b and mask(got) == mask(wl)
        nb += good
        check(f"A1 d{d} seed {seed:#06x}: lp_budget == levelgen.lp_budget (f3)", good,
              (ok1, ok2, blk == want_b, got.hex(), wl.hex()))
        # A2/A3: every present room, random arrival, in id order
        lp_ = got
        st = blk[S["LVL_START"] - G.BASE]
        for r in range(9):
            if not room_model.field(blk, r, "RD_FLAGS") & S["RDF_PRESENT"] or r == st:
                continue
            hs, hw = rng.randint(0, 1), 3
            hx = rng.choice((1, 28, rng.randint(5, 24)))
            p.clear_slots()
            p.wmem(S["LP_HX"], [hx, hs, hw])
            ok, ts = p.far3("lp_enter", a=r)
            wl2, out = G.lp_enter(blk, lp_, r, hs, hx, hw, f3=True)
            got2 = p.lp()
            sl = p.slots()
            ws = want_slots(p, blk, r, out)
            good = ok and sl == ws and mask(got2) == mask(wl2) and scaled_ok(p, sl, out, d)
            ne += good
            check(f"A2 d{d} seed {seed:#06x} room {r} (arrival s{hs} x{hx}): lp_enter == levelgen.lp_enter",
                  good, (ok, sl, ws, got2.hex(), wl2.hex()))
            bad = props(p, blk, r, sl, hs, hx, hw, tf)
            check(f"A3 d{d} seed {seed:#06x} room {r}: placement properties", bad == [], bad[:3])
            if (d, seed) not in l2set:
                tss.append(ts)
            if ts > worst[0]:
                worst = (ts, f"d{d} {seed:#06x} r{r} n{len(sl)} rnd calls {G.LP_CALLS}")
            lp_ = got2
    tss.sort()
    print(f"[lp] A1 {nb}/{len(pairs)} budgets, A2 {ne} entries ok; lp_enter (DI, incl. far3 ~0.4k) "
          f"mean {sum(tss) // len(tss)} T, median {tss[len(tss) // 2]}, 90% {tss[len(tss) * 9 // 10]}, "
          f"worst {worst[0]} T ({worst[1]})", flush=True)
    # game.md §9.4.3 (revised 2026-10-06): accepted mean <= 20k, worst <= 40k T.
    # Mean limit 21k since L2 (manager 2026-10-07): mid-blocks / wide pits add obstacles
    # (measured 20,119 T); the worst limit is unchanged.
    check(f"A2 lp_enter worst {worst[0]} T <= {LP_T_GUARD}, mean {sum(tss) // len(tss)} <= 22000",
          worst[0] <= LP_T_GUARD and sum(tss) // len(tss) <= 22000, worst)
    return worst


def fast_slots(p):
    """p.slots() + E_MAXHP / E_GOLD from ONE memory read: [(slot, kind, room, x, y, flags, hp, maxhp, gold)]."""
    b = p.z.read_memory(S["P_ENTITIES"] + STRIDE, 15 * STRIDE)
    out = []
    for s_ in range(15):
        o = s_ * STRIDE
        if b[o + 2] & EF_ACTIVE:
            out.append((s_ + 1, b[o], b[o + 1], b[o + 3], b[o + 4], b[o + 2], b[o + 5], b[o + 6], b[o + S["E_GOLD"]]))
    return out


def part_a7(h, p, check, nlev):
    """A7 (3F-T5): the tier / escort / golden / scaled-hp reference vs the Z80, record by record."""
    p.load()
    sync_bodies(p)
    rng = random.Random(0x5EED5)
    heroes = (S["K_KNIGHT"], S["K_WIZARD"])
    nrooms = nunits = ntier = ngold = nbad = 0
    tiers_by_depth = {d: 0 for d in range(1, 9)}
    tss = []
    worst = (0, "")
    bad = []
    for i in range(nlev):
        d = 1 + i % 8
        hero = heroes[(i // 8) & 1]
        seed = rng.randrange(1, 65536)
        lvl = max(1, d + rng.randint(-3, 4)) if i % 5 else rng.randint(1, 12)
        p.wb("HERO_KIND", hero)
        p.wb("LVL", lvl)
        p.wmem(S["LVL_SEED"], w16(seed))
        ok1, _ = p.far3("level_gen", a=d)
        ok2, _ = p.far3("lp_budget")
        blk = p.block()
        lp_ = p.lp()
        wb_ = G.lp_budget(blk, lvl, f3=True)
        if not (ok1 and ok2 and mask(lp_) == mask(wb_)):
            bad.append((d, seed, "budget"))
            continue
        st = blk[S["LVL_START"] - G.BASE]
        hw = p.kb(hero, "KT_BW")
        for r in range(9):
            if not room_model.field(blk, r, "RD_FLAGS") & S["RDF_PRESENT"] or r == st:
                continue
            hs = rng.randint(0, 1)
            hx = rng.choice((1, 28, rng.randint(5, 24)))
            p.wmem(S["P_ENTITIES"] + STRIDE, [0] * (15 * STRIDE))        # slots 1..15 free
            p.wmem(S["LP_HX"], [hx, hs, hw])
            ok, ts = p.far3("lp_enter", a=r)
            wl, out = G.lp_enter(blk, lp_, r, hs, hx, hw, f3=True)
            got = p.lp()
            sl = fast_slots(p)
            ws = want_slots(p, blk, r, out)
            good = (ok and [x[:7] for x in sl] == ws and mask(got) == mask(wl)
                    and [(x[7], x[8]) for x in sl] == [(G.k3_hp(kb, d), kb & G.LEK_GOLD) for kb, *_ in out])
            nrooms += 1
            nunits += len(sl)
            for kb, *_ in out:
                ntier += (kb & G.LEK_ROW_MASK) >= 18
                ngold += bool(kb & G.LEK_GOLD)
                tiers_by_depth[d] += (kb & G.LEK_ROW_MASK) >= 18
            tss.append(ts)
            if ts > worst[0]:
                worst = (ts, f"d{d} {seed:#06x} r{r} n{len(sl)}")
            if not good:
                nbad += 1
                if len(bad) < 6:
                    bad.append((d, seed, lvl, hero, r, sl, ws, got.hex(), wl.hex()))
            lp_ = got
    tss.sort()
    print(f"[lp] A7 {nlev} levels / {nrooms} rooms / {nunits} spawned units: {ntier} tier rows, {ngold} golden "
          f"bosses; tiers by depth {tiers_by_depth}; lp_enter (DI, incl. far3 + far6 hooks) mean {sum(tss) // len(tss)} T, "
          f"median {tss[len(tss) // 2]}, 90% {tss[len(tss) * 9 // 10]}, worst {worst[0]} T ({worst[1]})", flush=True)
    check(f"A7 {nlev} levels x both heroes x all depths: {nrooms} room entries == levelgen f3 reference "
          f"(records, slots, E_MAXHP, E_GOLD)", nbad == 0 and not bad, bad[:3])
    check("A7 the sweep rolled tiers at every depth and golden bosses (a sweep without them proves nothing)",
          all(v > 0 for v in tiers_by_depth.values()) and ngold > 0, (tiers_by_depth, ngold))
    check(f"A7 lp_enter worst {worst[0]} T <= {LP_T_GUARD}, mean {sum(tss) // len(tss)} <= 22000",
          worst[0] <= LP_T_GUARD and sum(tss) // len(tss) <= 22000, worst)


def bank_model(lp, r, slots, gold=None):
    """§9.4.2: append every alive slot of room r (exact hp, EF_RESPAWN, 3F-T5: LEK_GOLD) in slot order."""
    gold = gold or {}
    lp = bytearray(lp)
    ro = S["LP_REC"] - LPB + r * S["LR_STRIDE"]
    n = lp[ro] & 7
    for (sl_, k, rr, _, _, fl, hp) in slots:
        if rr != r or fl & EF_DYING:
            continue
        lp[ro + 1 + 2 * n] = k | (fl & S["EF_RESPAWN"]) | gold.get(sl_, 0)
        lp[ro + 2 + 2 * n] = hp
        n += 1
    lp[ro] = S["LR_VISITED"] | n
    return bytes(lp)


def part_a6(h, p, check):
    """A6 (fix/3d-artefacts): lp_mark clips to LP_CMAP[storey][0..LP_CMW-1];
    out-of-range calls (the old wrapped gap zone $F7 x 16, a negative start,
    a run past col 32, a start beyond the map) never write outside the map:
    the 256 B before / after LP_CMAP (NEXT_MAP rows, TILE_GLYPHS) unchanged."""
    p.load()
    cm, W = S["LP_CMAP"], S["LP_CMW"]
    lo, hi = cm - 256, cm + 2 * W + 256
    for a, b, st in ((0xF7, 16, 0), (0xFE, 5, 1), (30, 10, 0), (30, 10, 1), (40, 2, 0),
                     (0x80, 127, 1), (0, W, 0), (0xF8, 3, 0)):
        p.wmem(cm, [0] * (2 * W))
        before = bytes(p.z.read_memory(lo, hi - lo))
        ok, _ = p.code([0x3E, 3, 0xCD] + w16(S["page_bank"])
                       + [0x3E, a, 0x06, b, 0x0E, st, 0x1E, 2, 0xCD] + w16(S["lp_mark"]))
        after = bytes(p.z.read_memory(lo, hi - lo))
        sa = a - 256 if a >= 128 else a
        want = bytearray(before)
        for c in range(max(sa, 0), min(sa + b, W)):
            want[cm - lo + st * W + c] |= 2
        out = [hex(lo + i) for i in range(len(after)) if after[i] != want[i]]
        check(f"A6 lp_mark({sa}, {b}, storey {st}) clipped to the map, nothing written outside",
              ok and out == [], (ok, out[:8]))


def part_a4(h, p, check):
    """A4 + A5 on a few levels."""
    p.load()
    sync_bodies(p)
    for d, seed in ((1, 0x1234), (3, 0xBEEF), (7, 0x0042), (4, 0x7777)):
        p.wb("LVL", 1)
        p.wmem(S["LVL_SEED"], w16(seed))
        p.far3("level_gen", a=d)
        p.far3("lp_budget")
        blk = p.block()
        base = p.lp()
        st = blk[S["LVL_START"] - G.BASE]
        lair = blk[S["LVL_LAIR"] - G.BASE]
        rooms = [r for r in range(9) if room_model.field(blk, r, "RD_FLAGS") & S["RDF_PRESENT"] and r != st]
        first = {}
        for order in (rooms, rooms[::-1]):            # A5: two visit orders
            p.wmem(LPB, base)
            for r in order:
                p.clear_slots()
                p.wmem(S["LP_HX"], [1, 0, 3])
                p.far3("lp_enter", a=r)
                sl = [x[1:] for x in p.slots()]
                if r in first:
                    check(f"A5 d{d} room {r}: first-visit contents independent of the visit order",
                          sl == first[r], (sl, first[r]))
                else:
                    first[r] = sl
        # A4: the lair (boss) and the first room with >= 2 monsters
        for r in [lair] + [x for x in rooms if x != lair]:
            p.wmem(LPB, base)
            p.clear_slots()
            p.wmem(S["LP_HX"], [28, 1, 3])
            p.far3("lp_enter", a=r)
            sl = p.slots()
            if len(sl) < (1 if r == lair else 2):
                continue
            p.set_ent(sl[0][0], HP=max(1, sl[0][6] - 1))           # damaged (the boss in the lair)
            if len(sl) > 1:
                p.set_ent(sl[1][0], FLAGS=sl[1][5] | EF_DYING)       # dying: never returns
            sl = p.slots()
            gold = {x[0]: gold_of(p, x[0]) for x in sl}
            lp0 = p.lp()
            ok, tb = p.far3("lp_bank", a=r, e=0)
            lp1 = p.lp()
            check(f"A4 d{d} room {r}: lp_bank -> record == model (exact hp, golden bit, dead dropped), slots freed",
                  ok and mask(lp1) == mask(bank_model(lp0, r, sl, gold)) and p.slots() == [],
                  (lp1.hex(), bank_model(lp0, r, sl, gold).hex(), p.slots()))
            p.wb(S["ROOM_VISITS"] + r, p.rb(S["ROOM_VISITS"] + r) + 1)
            lp1 = p.lp()
            p.wmem(S["LP_HX"], [1, 0, 3])
            p.far3("lp_enter", a=r)
            wl, out = G.lp_enter(blk, lp1, r, 0, 1, 3, f3=True)
            got = p.slots()
            alive = [(x[1], x[6]) for x in sl if not x[5] & EF_DYING] + [
                (e[0] & 31, e[1]) for e in G_entries(lp0, r)]
            check(f"A4 d{d} room {r}: re-entry == levelgen.lp_enter of the banked record; "
                  f"kinds + hp kept {alive}",
                  got == want_slots(p, blk, r, out) and mask(p.lp()) == mask(wl)
                  and scaled_ok(p, got, out, d)
                  and sorted([(x[1], x[6]) for x in got] + [
                      (e[0] & 31, e[1]) for e in G_entries(p.lp(), r)]) == sorted(alive),
                  (got, out))
            if r == lair:
                print(f"[lp] A4 d{d}: lair boss hp {sl[0][6]} kept across bank / re-entry", flush=True)
            else:
                break


def G_entries(lp, r):
    ro = S["LP_REC"] - LPB + r * S["LR_STRIDE"]
    return [(lp[ro + 1 + 2 * i], lp[ro + 2 + 2 * i]) for i in range(lp[ro] & 7)]


# ---------------------------------------------------------------------------
# Part B: the real do_exit on a generated D1
# ---------------------------------------------------------------------------
def stand_y(s_, h_):
    return 9 * s_ + 8 - h_


def part_b(h, p, check):
    M = 0x2468
    p.proto_start = 0
    p.load()
    p.wait_state(S["GS_SELECT"])
    p.wb("seed_fixed", 1)
    p.wmem(S["seed_value"], w16(M))
    p.wb("INPUT_REPEAT", 0)
    p.wb("ANIM_FREEZE", 1)
    p.wb("INPUT_SRC", 1)
    TG, TA, TC = S["TILE_GLYPHS"], S["TILE_ATTRS"], S["TILE_COMMON"]
    glyphs0 = bytes(p.z.read_memory(TG, TC * 8))          # init_tiles' common set (boot)
    p.hold("1")
    p.wait_state(GS_PLAYING)
    p.release()
    p.settle(3)
    blk = p.block()
    # B0G (fix/3d-artefacts): level_populate read the hero through an IX that
    # lp_budget's bfs had clobbered: LP_HX / LP_HW garbage, the gap-zone mark
    # wrapped past LP_CMAP and ORed LPC_BODY into the T_HOLE_L/M glyphs (stray
    # red lines on every ladder-in-floor cell). LP_HX..LP_HW are masked in B0.
    e0 = p.ent(0)
    hb = (p.rb("LP_HX"), p.rb("LP_HS"), p.rb("LP_HW"))
    check("B0G new game: start-room arrival box LP_HX/HS/HW == hero x / storey 0 / KT_BW",
          hb == (e0["X"], 0, p.kb(p.rb("HERO_KIND"), "KT_BW")), hb)
    g1 = bytes(p.z.read_memory(TG, TC * 8))
    a1 = bytes(p.z.read_memory(TA, TC))       # (the level theme re-colours some common ids)
    check("B0G new game: common tile glyphs (ids 0..31) unchanged since boot",
          g1 == glyphs0,
          [i // 8 for i in range(TC * 8) if g1[i] != glyphs0[i]][:8])
    # every ladder / hole cell on screen not under a body == the boot glyph
    fr = p.frame()
    m = bytes(p.z.read_memory(S["ROOM_MAP"], 32 * S["PLAY_ROWS"]))
    covered = set()
    for s_ in range(16):
        e = p.ent(s_)
        if e["FLAGS"] & EF_ACTIVE and e["DVIS"]:
            covered |= {(c, r) for c in range(e["DCOL"], e["DCOL"] + e["DCOLS"])
                        for r in range(e["DROW"], e["DROW"] + e["DROWS"])}
    lad = range(S["T_LAD_L"], S["T_HOLE_R"] + 1)
    bad, n = [], 0
    for i, t in enumerate(m):
        c, r = i % 32, i // 32
        if t in lad and (c, r) not in covered:
            n += 1
            if cell_bytes(fr, c, r) != glyphs0[t * 8:t * 8 + 8] or attr_at(fr, c, r) != a1[t]:
                bad.append((c, r, t))
    check(f"B0G new game: {n} ladder / hole cells on screen == the boot glyph + attr",
          n > 0 and bad == [], bad[:6])
    st = p.rb("CUR_ROOM")
    kw = p.kb(S["K_KNIGHT"], "KT_BW")
    kh = p.kb(S["K_KNIGHT"], "KT_BH")
    lp0 = p.lp()
    exp0 = _visit(G.lp_enter(blk, G.lp_budget(blk, p.rb("LVL"), f3=True), st, 0, p.ent(0)["X"], kw, f3=True)[0], st)
    check("B0 new game: LP block == levelgen.lp_budget + the start room's entry (VISITED, visits 1)",
          mask(lp0) == mask(exp0), (lp0.hex(), exp0.hex()))
    check("B0 new game: no monster slot (start room quota 0)", p.slots() == [], p.slots())

    def ingame(code, tag):
        pc0 = p.pc()
        ok, _ = p.code(code, game=True)
        p.z.cmd("set-register PC=%d" % pc0)
        check(f"B stub {tag} ran", ok, "")

    def put_hero(r, x, s_, left):
        p.wb("CUR_ROOM", r)
        p.set_ent(0, ROOM=r, X=x, Y=stand_y(s_, kh), PX=x * 8, PY=stand_y(s_, kh) * 8,
                  FLAGS=EF_ACTIVE | 2 | (EF_LEFT if left else 0), MODE=0, DVIS=0)
        ingame([0x3E, r, 0xCD] + w16(S["room_show"]) + [0xCD] + w16(S["vis_reset"])
               + [0xCD] + w16(S["present_full"]), f"show room {r}")
        p.settle(2)

    def walk_out(r, side, s_):
        """from room r (hero already there, nothing in its way) out through side."""
        x, key = (2, "H") if side == "L" else (32 - 2 - kw, "L")
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

    # a horizontal edge between two non-start rooms A -> B (B not the lair)
    lair = blk[S["LVL_LAIR"] - G.BASE]
    pick = None
    for r in range(9):
        ex = room_model.field(blk, r, "RD_EXITS")
        if ex & S["RDX_R"] and r != st and r + 1 != lair and r + 1 != st:
            pick = (r, r + 1, 1 if ex & S["RDX_RS1"] else 0)
            break
    check("B setup: a horizontal edge between two plain rooms", pick is not None, "")
    if not pick:
        return
    a, b, s_ = pick
    ei = S["EDGE_TAB"] + room_model.edge_index(b, "L")
    p.wb(ei, p.rb(ei) | S["EG_OPEN"])                   # an open way (door or not)
    # B1: A -> B (first entry of B)
    lp_a = p.lp()
    ok = walk_out(a, "R", s_)
    wl, out = G.lp_enter(blk, _bank_all(lp_a, a), b, s_, 1, kw, f3=True)
    sl = p.slots()
    check(f"B1 walked {a} -> {b} through the real do_exit", ok, p.rb("CUR_ROOM"))
    check(f"B1 room {b}: slots == levelgen.lp_enter (FRESH, arrival s{s_} x1)",
          sl == want_slots(p, blk, b, out), (sl, out))
    check(f"B1 ROOM_VISITS[{b}] = 1, record VISITED",
          p.rb(S["ROOM_VISITS"] + b) == 1 and p.rb(S["LP_REC"] + 9 * b) & 0x80, p.lp().hex())
    invariant("B1")
    if len(sl) < 1:
        print("[lp] B2 skipped: no monster spawned in room", b, flush=True)
        return
    # B2: damage the first, kill the second (if any) -> leave left (back to A) -> re-enter
    p.set_ent(sl[0][0], HP=sl[0][6] - 1 if sl[0][6] > 1 else 1)
    if len(sl) > 1:
        p.set_ent(sl[1][0], FLAGS=0)                    # killed (slot freed as anim_tick does)
    keep = [(x[1], p.ent(x[0])["HP"]) for x in p.slots()] + [(e[0] & 31, e[1]) for e in G_entries(p.lp(), b)]
    for x in p.slots():                                 # out of the way of the walk
        p.set_ent(x[0], X=14, PX=14 * 8)
    ok = walk_out(b, "L", s_)
    ent = G_entries(p.lp(), b)
    check(f"B2 back in {a}: room {b}'s record holds the survivors {keep} (exact hp, dead gone)",
          ok and sorted((e[0] & 31, e[1]) for e in ent) == sorted(keep), (ok, ent, keep))
    invariant("B2 out")
    lp_b = p.lp()
    ok = walk_out(a, "R", s_)
    wl, out = G.lp_enter(blk, _bank_all(lp_b, a), b, s_, 1, kw, f3=True)
    got = p.slots()
    check(f"B2 re-entered {b}: slots == levelgen.lp_enter of the record; kinds + hp {keep}",
          ok and got == want_slots(p, blk, b, out)
          and sorted([(x[1], x[6]) for x in got] + [(e[0] & 31, e[1]) for e in G_entries(p.lp(), b)])
          == sorted(keep), (got, out, keep))
    invariant("B2 in")
    # B3: followers. A goblin beside the hero at the right edge of room B: it
    # follows into C... use the edge B -> A instead (known open): the goblin
    # stands next to the hero, both leave left; A's residents spawn first.
    for x in p.slots():
        p.set_ent(x[0], FLAGS=0)
    k = S["K_GOBLIN"]
    gh = p.kb(k, "KT_BH")
    put_hero(b, 2, s_, True)
    p.set_ent(5, KIND=k, ROOM=b, FLAGS=EF_ACTIVE | EF_HOSTILE | EF_LEFT, X=2 + kw + 1,
              Y=stand_y(s_, gh), PX=(2 + kw + 1) * 8, PY=stand_y(s_, gh) * 8, MODE=0, DVIS=0,
              HP=5, MAXHP=6)
    ingame([0xCD] + w16(S["vis_reset"]), "vis")
    lpb = p.lp()
    for _ in range(4):
        if p.rb("CUR_ROOM") == a:
            break
        p.turn("H")
    p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
    gob = [x for x in p.slots() if x[1] == k and x[6] == 5]
    res = len(G_entries(lpb, a))
    check(f"B3 follower admitted into {a} after its {res} resident(s) spawned (hp 5 kept)",
          p.rb("CUR_ROOM") == a and len(gob) == 1, p.slots())
    invariant("B3 admitted")
    # B3b: fill A's record to the cap (4 skeletons = sum 20 > 12) -> rejected, banked into B
    for x in p.slots():
        if x[1] != k:
            p.set_ent(x[0], FLAGS=0)
    for x in p.slots():
        p.set_ent(x[0], FLAGS=0)
    ro = S["LP_REC"] + 9 * a
    p.wmem(ro, [0x84] + [S["K_SKELETON"], 1] * 4)       # VISITED, 4 entries
    p.wmem(S["LP_REC"] + 9 * b, [0x80] + [0] * 8)
    put_hero(b, 2, s_, True)
    p.set_ent(5, KIND=k, ROOM=b, FLAGS=EF_ACTIVE | EF_HOSTILE | EF_LEFT, X=2 + kw + 1,
              Y=stand_y(s_, gh), PX=(2 + kw + 1) * 8, PY=stand_y(s_, gh) * 8, MODE=0, DVIS=0,
              HP=4, MAXHP=6)
    ingame([0xCD] + w16(S["vis_reset"]), "vis")
    for _ in range(4):
        if p.rb("CUR_ROOM") == a:
            break
        p.turn("H")
    p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
    entb = G_entries(p.lp(), b)
    check(f"B3 room {a} full (cap): the candidate is rejected and banked into {b} (hp 4)",
          p.rb("CUR_ROOM") == a and (k, 4) in [(e[0] & 31, e[1]) for e in entb]
          and not [x for x in p.slots() if x[1] == k and x[6] == 4], (entb, p.slots()))
    invariant("B3 rejected")
    # B3c (3F-T5 review): the golden +1 counts in the 9.3 cap (12) for residents (record / spawned slots) and followers
    G_, GOLD = S["K_GOBLIN"], S["LEK_GOLD"]
    for tag, res, fgold, admit in (("golden resident 4+3+3, plain follower 3 = 13", [G_ | GOLD, G_, G_], 0, False),
                                   ("plain residents 3+3+3, golden follower 4 = 13", [G_, G_, G_], GOLD, False),
                                   ("golden resident 4+3, plain follower 3 = 10", [G_ | GOLD, G_], 0, True),
                                   ("plain residents 3+3+3, plain follower 3 = 12", [G_, G_, G_], 0, True)):
        for x in p.slots():
            p.set_ent(x[0], FLAGS=0)
        p.wmem(S["LP_REC"] + 9 * a, [0x80 | len(res)] + [v for kk in res for v in (kk, 6)] + [0] * (8 - 2 * len(res)))
        p.wmem(S["LP_REC"] + 9 * b, [0x80] + [0] * 8)
        put_hero(b, 2, s_, True)
        p.set_ent(5, KIND=k, ROOM=b, FLAGS=EF_ACTIVE | EF_HOSTILE | EF_LEFT, X=2 + kw + 1,
                  Y=stand_y(s_, gh), PX=(2 + kw + 1) * 8, PY=stand_y(s_, gh) * 8, MODE=0, DVIS=0,
                  HP=4, MAXHP=6)
        p.wb(S["P_ENTITIES"] + 5 * STRIDE + S["E_GOLD"], fgold)
        ingame([0xCD] + w16(S["vis_reset"]), "vis")
        for _ in range(4):
            if p.rb("CUR_ROOM") == a:
                break
            p.turn("H")
        p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
        got = [x for x in p.slots() if x[1] == k and x[6] == 4]
        entb = [(e[0] & 31, e[1]) for e in G_entries(p.lp(), b)]
        ok = p.rb("CUR_ROOM") == a and ((len(got) == 1 and (k, 4) not in entb) if admit
                                        else (not got and (k, 4) in entb))
        check(f"B3c cap with the golden +1: {tag}: follower {'admitted' if admit else 'rejected, banked back'}",
              ok, (p.slots(), entb))
        invariant("B3c")


def _visit(lp, r):
    lp = bytearray(lp)
    lp[S["ROOM_VISITS"] - LPB + r] += 1
    return bytes(lp)


def _bank_all(lp, r):
    """The room left by a lone hero: record VISITED (nothing to bank)."""
    lp = bytearray(lp)
    ro = S["LP_REC"] - LPB + r * S["LR_STRIDE"]
    lp[ro] |= S["LR_VISITED"]
    return bytes(lp)


def main():
    nrand = 40
    if "--random" in sys.argv:
        nrand = int(sys.argv[sys.argv.index("--random") + 1])
    nsweep = 1000
    if "--sweep" in sys.argv:
        nsweep = int(sys.argv[sys.argv.index("--sweep") + 1])
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {detail}", flush=True)
        if "--only-b" not in sys.argv:
            part_a(h, p, check, nrand)
            part_a4(h, p, check)
            part_a6(h, p, check)
            if nsweep:
                part_a7(h, p, check, nsweep)
        part_b(h, p, check)
        print(f"lp: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
