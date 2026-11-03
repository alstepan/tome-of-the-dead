#!/usr/bin/env python3
"""3F-T7: monster ranged attacks (game.md §9.2 RANGED-SPEC; src/ranged6.asm,
src/ranged2.asm, turn3.asm hook) on a booted Knight game, PROTO room A,
storey 1 (rows 9..16 rewritten per case).

  A   A/B vs tools/ranged_model.py: RANGED_N (default 2,400) seeded situations
      through the real hook (stub: build_live, cache_player, TMP4 / H as
      ai_monster leaves them, ai_rhook): every shooter kind, range edges,
      counter 0..3, blocks on the flight row, bodies in the gap (dying ones
      not), mid-ladder / other-storey heroes, reflecting / resisting /
      FEAR-immune heroes, step-away legality (edges, bricks, bodies). Compared:
      CF, counter, facing, x / E_MODE, E_MSG, the hero's HP / ST_FLAGS / ST_T1 /
      E_REACT / E_REACTAT, RNG state, TP_SHOT, the RS_Q entry (R, flash tick,
      the 16-B FX descriptor), COMBAT_NOT_BEFORE, FX_DROP
  E   range edges: Archer gap 9 fires / 10 not, Slinger 5 / 6, Sniper 13 / 14,
      Necro 7 / 8 (counter 0, clear line)
  C   cadence through real turns (resolve_monsters): a stationary Archer in
      range shoots on turns 2, 4, 6 (N = 1, none on the first phase), a
      Necromancer on 2, 5, 8 (N = 2)
  B   a Rat in the gap: no shot, the Rat untouched; a mid-room block on the
      flight row: no shot; the hero mid-ladder / on the other storey: none
  S   gap 2, counter 1: the Archer steps away, the Sniper holds, a blocked
      Archer holds facing the hero
  D   PHYS = max(1, d - DEF); DARK ignores DEF, R halves; FEAR ~ 1/3 over 600
      Necro hits; Mirror Helm (DARK X) -> 0 shots in 100 turns
  K   an arrow kill: the hero's DEATH reaction at the impact tick (not
      before), GS_DEAD only after it; the FX track flew
  Q   3 Slingers in one phase: 3 tracks (released on ticks 2 / 3 by slot
      parity), FX_DROP 0; a 4th shooter queues (FXQ) and still starts
  L   climbers: an out-of-line Slinger walks to the ladder (.seek)
  G   BOSS-RANGED (golden only): A also draws golden / ordinary Goblins and Spiders (+ golden
      bits on every shooter: + GOLD_ATK, dmg + 1); fixed: a golden King / Queen fires at gap 5,
      not 6, an ordinary Goblin / Spider never (counter untouched, RNG untouched); between
      shots a golden King in range returns CF 0 (walks in); real turns: a golden King walks
      in AND shoots every 3rd turn; the spit poisons + 12 (fresh 12, 24 -> cap 30), Silk Cloak
      (IMMF_POISON) immune (damage still), a dagger hit never poisons
Run: ZRCP_PORT=<port> python3 tests/ranged.py
"""
import os
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_RAT, K_BAT, K_SKELETON  # noqa: E402
from proj3 import T as PT, w16  # noqa: E402
import ranged_model as M  # noqa: E402

STUB = S["LOWRAM_END_3B"]
RES = STUB + 200
STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT, EF_DYING = 1, 2, 4, 8, 16
E_ = {k: S["E_" + k] for k in ("KIND", "ROOM", "FLAGS", "X", "Y", "HP", "MAXHP", "POT", "PX", "PY", "MODE",
                               "REACT", "REACTAT", "MSG", "TGT", "HIT", "FLT", "FLA", "GOLD")}
K = dict(ARCHER=S["K_ARCHER"], SNIPER=S["K_SNIPER"], SLINGER=S["K_SLINGER"], NECRO=S["K_NECRO"],
         BONE=S["K_BONE_CALLER"])
SHOOTERS = list(K.values())
GOLDK = [S["K_GOBLIN"], S["K_SPIDER"]]                # BOSS-RANGED: rows only when golden
LEK_GOLD = 1 << S["LEK_GOLD_BIT"]
T_AIR, T_BRICK = S["T_AIR"], S["T_BRICK"]
S1 = 9                                   # storey 1 top row
N_A = int(os.environ.get("RANGED_N", "2400"))


class T(PT):
    def kt(self):
        g = lambda f, k: self.rb(S["kind_tab"] + S[f] + k)  # noqa: E731
        return {k: dict(bw=g("KT_BW", k), bh=g("KT_BH", k), atk=g("KT_ATK", k), eva=g("KT_EVA", k))
                for k in range(S["K_COUNT"])}

    def hook(self, slot):
        """build_live, cache_player, ACT_SLOT, TMP4 / H as ai_monster, ai_rhook -> CF."""
        ent = S["P_ENTITIES"] + slot * STRIDE
        inner = ([0xCD] + w16(S["build_live"]) + [0xCD] + w16(S["cache_player"]) +
                 [0x3E, slot, 0x32] + w16(S["ACT_SLOT"]) + [0xDD, 0x21] + w16(ent) +
                 [0xCD] + w16(S["storey_ref"]) + [0x32] + w16(S["TMP4"]) +
                 [0xCD] + w16(S["is_standing"]) + [0x26, 0x00, 0x28, 0x01, 0x24] +
                 [0xCD] + w16(S["ai_rhook"]) + [0x9F, 0x32] + w16(RES))
        assert self.code(self.bank3(inner)), "ai_rhook stub did not return"
        return self.rb(RES) != 0


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:1500]}", flush=True)

        p.boot(K_KNIGHT)
        kt = p.kt()
        tflags = list(p.z.read_memory(S["tile_flags"], 64))
        room = p.rb("CUR_ROOM")
        hw, hh = kt[K_KNIGHT]["bw"], kt[K_KNIGHT]["bh"]
        map0 = list(p.z.read_memory(S["ROOM_MAP"] + S1 * 32, 9 * 32))

        def put_world(sit, ents, rows):
            mem = bytearray(p.z.read_memory(S["P_ENTITIES"], 16 * STRIDE))
            for s_ in range(16):
                o = s_ * STRIDE
                e = ents.get(s_)
                if e is None:
                    mem[o + E_["FLAGS"]] = 0
                    continue
                for k_, v in e.items():
                    mem[o + E_[k_]] = v & 255
                mem[o + E_["ROOM"]] = room
                mem[o + E_["PX"]], mem[o + E_["PY"]] = e["X"] * 8, e["Y"] * 8
            p.wmem(S["P_ENTITIES"], list(mem))
            p.wmem(S["ROOM_MAP"] + S1 * 32, rows)

        def ent_of(kind, x, y, flags, hp=30, **kw):
            d = dict(KIND=kind, X=x, Y=y, FLAGS=flags, HP=hp, MAXHP=hp, MODE=0, REACT=0, REACTAT=0, MSG=0,
                     TGT=0, HIT=0, FLT=0, POT=0, GOLD=0)
            d.update(kw)
            return d

        # ------------------------------------------------------------- A
        # stub baseline: the same stub with a non-shooter (ai_rhook's reject) -> the hook's own T below
        put_world(None, {0: ent_of(K_KNIGHT, 6, S1 + 8 - hh, EF_ACTIVE | EF_PLAYER),
                         3: ent_of(K_RAT, 20, S1 + 8 - kt[K_RAT]["bh"], EF_ACTIVE | EF_HOSTILE)}, map0)
        p.hook(3)
        t_base, tmax = p.tstates, {}
        rnd = random.Random(0x7A7)
        LPK = list(p.z.read_memory(S["LP_KINDS"], 4))         # 3F-T9: the Bone Caller's summon kind
        WT = {k_: S[n_] for k_, n_ in ((K_RAT, "WT_K_RAT"), (K_BAT, "WT_K_BAT"), (K_SKELETON, "WT_K_SKELETON"),
              (S["K_GHOST"], "WT_K_GHOST"), (S["K_ARCHER"], "WT_K_ARCHER"), (S["K_SNIPER"], "WT_K_SNIPER"),
              (S["K_SLINGER"], "WT_K_SLINGER"), (S["K_NECRO"], "WT_K_NECRO"),
              (S["K_BONE_CALLER"], "WT_K_BONE_CALLER"), (S["K_GOBLIN"], "WT_K_GOBLIN"), (S["K_SPIDER"], "WT_K_SPIDER"))}
        bad_a, n_a, stats = [], 0, dict(shot=0, step=0, hold=0, no=0, hit=0, fear=0)
        while n_a < N_A:
            kind = rnd.choice(SHOOTERS + GOLDK + GOLDK)
            gold = rnd.random() < (0.6 if kind in GOLDK else 0.15)
            mrow = M.row_of(kind, gold)
            row = list(mrow or M.GOLD_ROWS[kind])
            row[7] = S["FID_" + row[7]]
            w, hgt = kt[kind]["bw"], kt[kind]["bh"]
            slot = rnd.randint(1, 15)
            standing = rnd.random() > 0.05
            sy = S1 + 8 - hgt - (0 if standing else 1)
            # hero: storey 1 standing / storey 0 / mid-ladder
            u = rnd.random()
            if u < 0.86:
                hy_, hst, hlad = S1 + 8 - hh, 1, 0
            elif u < 0.93:
                hy_, hst, hlad = 8 - hh, 0, 0
            else:
                hy_, hst, hlad = S1 + 8 - hh - rnd.randint(1, 3), 1, 1
            gap = rnd.choice([rnd.randint(0, 16), row[0] - 1, row[0], rnd.randint(0, 3)])
            right = rnd.random() < 0.5                      # hero to the right of the shooter
            if right:
                sx = rnd.randint(1, 30)
                hx = sx + w + gap
            else:
                hx = rnd.randint(1, 30)
                sx = hx + hw + gap
            if not (1 <= sx and sx + w - 1 <= 30 and 1 <= hx and hx + hw - 1 <= 30):
                continue
            # rows 9..16: air, walls at 0 / 31; bricks on the flight row / standing row
            rows = [T_AIR] * (8 * 32)
            for r_ in range(8):
                rows[r_ * 32] = rows[r_ * 32 + 31] = T_BRICK
            fr = M.flight_row(dict(y=sy, h=hgt)) - S1
            if rnd.random() < 0.25:
                for _ in range(rnd.randint(1, 2)):
                    rows[fr * 32 + rnd.randint(1, 30)] = T_BRICK
            if rnd.random() < 0.2:
                rows[(7) * 32 + rnd.randint(1, 30)] = T_BRICK
            rows = rows + map0[8 * 32:]
            mp = {S1 + r_: [tflags[rows[r_ * 32 + c]] for c in range(32)] for r_ in range(9)}
            counter = rnd.randint(0, 3) if rnd.random() < 0.6 else 0
            hi = rnd.randint(0, 15) << 2
            left = rnd.random() < 0.5
            ents = {0: ent_of(K_KNIGHT, hx, hy_, EF_ACTIVE | EF_PLAYER, hp=rnd.randint(1, 40))}
            ents[slot] = ent_of(kind, sx, sy, EF_ACTIVE | EF_HOSTILE | (EF_LEFT if left else 0), POT=(counter ^ 1) | hi,
                                GOLD=LEK_GOLD if gold else 0)
            bodies = [(0, hx, hy_, hw, hh, False)]
            for _ in range(rnd.choice([0, 0, 1, 2, 3])):
                bs = rnd.randint(1, 15)
                if bs in ents:
                    continue
                bk = rnd.choice([K_RAT, K_BAT, K_SKELETON])
                bw_, bh_ = kt[bk]["bw"], kt[bk]["bh"]
                by = S1 + 1 if bk == K_BAT else S1 + 8 - bh_
                bx = rnd.randint(1, 31 - bw_)
                dying = rnd.random() < 0.15
                ents[bs] = ent_of(bk, bx, by, EF_ACTIVE | EF_HOSTILE | (EF_DYING if dying else 0))
                bodies.append((bs, bx, by, bw_, bh_, dying))
            res = [0, 0, 0]
            v = rnd.random()
            if v < 0.15:
                res[1] = 3 << 2                              # DARK X (Mirror Helm)
            elif v < 0.3:
                res[1] = 1 << 2                              # DARK R
            elif v < 0.4:
                res[0] = rnd.choice([1, 2])                  # PHYS R / I
            hdef, imm = rnd.randint(0, 3), (8 if rnd.random() < 0.1 else 0)
            if rnd.random() < 0.15:
                imm |= S["IMMF_POISON"]                      # BOSS-RANGED: Silk Cloak
            stf, st1 = 0, 0
            v = rnd.random()
            if v < 0.1:
                stf, st1 = 0x04, rnd.randint(1, 5)           # FEAR on
            elif v < 0.15:
                stf, st1 = 0x02, 0x30                        # ASLEEP (held: eva 0, wakes)
            stx = 0
            if rnd.random() < 0.25:
                stf, stx = stf | (1 << S["STS_POISON_BIT"]), rnd.randint(1, 15) * 2   # POISON on (ST_X turns)
            tt = rnd.randint(0, 5)
            seed = rnd.randint(1, 0xFFFF)
            put_world(None, ents, rows)
            p.wmem(S["ST_FLAGS"], [stf] + [0] * 15)
            p.wmem(S["ST_T1"], [st1] + [0] * 15)
            p.wmem(S["ST_T2"], [0] * 16)
            p.wb(S["ST_X"], stx)
            p.wmem(S["HERO_RES"], res)
            p.wb("HERO_IMM", imm)
            p.wb("HERO_DEF", hdef)
            p.wb("TURN_TICK", tt)
            p.wb("TURN_PEND", 0)
            p.wb("COMBAT_NOT_BEFORE", 0)
            p.wb("FX_DROP", 0)
            p.wb("HSTAGE", 0)
            p.wmem(S["RNG_STATE"], w16(seed))
            p.wb("SPQ_K", 0)                                 # 3F-T9: the spawn queue free (end_turn empties it)
            # 3F-T9 Bone Caller summon (spawn6.asm sp_summon): S = 0, < BC_LIVE summons (none here: the
            # bodies carry no RCD_SUMMONED), a free slot (<= 5 used), the cap: < ROOM_CAP live, Σ + w <= 12
            live = [e_["KIND"] for s_, e_ in ents.items() if s_ and not e_["FLAGS"] & EF_DYING]
            sw = WT[K_SKELETON] if K_SKELETON in LPK else WT[S["K_GHOST"]]
            sig = sum(WT[k_] for k_ in live) + sum(1 for s_, e_ in ents.items()      # a golden body weighs + 1
                                                    if s_ and not e_["FLAGS"] & EF_DYING and e_.get("GOLD"))
            summon_ok = len(live) < S["ROOM_CAP"] and sig + sw <= S["LP_SIGMA_CAP"]
            sit = dict(kind=kind, row=row, slot=slot, x=sx, y=sy, w=w, h=hgt, left=left, standing=standing,
                       storey=1, counter=counter, atk=kt[kind]["atk"], gold=gold, turn_tick=tt, map=mp,
                       bodies=bodies, s=hi >> 2, summon_ok=summon_ok,
                       hero=dict(x=hx, y=hy_, w=hw, h=hh, storey=hst, ladder=hlad, hp=ents[0]["HP"],
                                 eva=kt[K_KNIGHT]["eva"], held=stf & 3 != 0, res=res, def_=hdef, imm=imm,
                                 stf=stf, st1=st1, stx=stx, react=0))
            sit["hero"]["def"] = hdef
            rng = M.Rng(seed)
            if mrow is None:                                 # an ordinary Goblin / Spider: ai_rhook's gate ->
                want = dict(used=False, counter=counter, left=left, x=sx, moved=False, shot=None)   # ai_ghook
                stats["plain"] = stats.get("plain", 0) + 1
            else:
                want = M.decide(sit, rng)
            cf = p.hook(slot)
            cat = "shot" if want["shot"] else "step" if want["moved"] else "hold" if want["used"] else "no"
            tmax[cat] = max(tmax.get(cat, 0), p.tstates)
            mem = p.z.read_memory(S["P_ENTITIES"], 16 * STRIDE)
            e = lambda s_, f: mem[s_ * STRIDE + E_[f]]  # noqa: E731
            got = dict(cf=cf, counter=(e(slot, "POT") & 3) ^ 1, hi=e(slot, "POT") & ~3 & 255,
                       left=bool(e(slot, "FLAGS") & EF_LEFT), x=e(slot, "X"),
                       moved=e(slot, "MODE") == S["M_MOVE"], rng=p.rw("RNG_STATE"),
                       tp=bool(p.rb("TURN_PEND") & S["TP_SHOT"]), drop=p.rb("FX_DROP"))
            exp = dict(cf=want["used"], counter=want["counter"], hi=want.get("s", hi >> 2) << 2, left=want["left"],
                       x=want["x"], moved=want["moved"], rng=rng.st, tp=want["shot"] is not None, drop=0)
            got["sq"] = p.rb("SPQ_K")
            exp["sq"] = 0
            if want.get("summon"):
                stats["summon"] = stats.get("summon", 0) + 1
                got["msg"] = e(slot, "MSG")
                exp["msg"] = S["MSG_M_SUMMON"]
                exp["sq"] = (K_SKELETON if K_SKELETON in LPK else S["K_GHOST"]) | 0xC0
            sh = want["shot"]
            if sh:
                hs = sh["hero"]
                got.update(msg=e(slot, "MSG"), hhp=e(0, "HP"), stf=p.rb(S["ST_FLAGS"]), st1=p.rb(S["ST_T1"]),
                           stx=p.rb(S["ST_X"]), cnb=p.rb("COMBAT_NOT_BEFORE"), rsp=p.rb("RS_P"))
                q = list(p.z.read_memory(S["RS_Q"], S["RS_STRIDE"]))
                got.update(q=q)
                exp.update(msg=sh["msg"], hhp=hs.get("hp", sit["hero"]["hp"]), stf=hs.get("stf", stf),
                           st1=hs.get("st1", st1), stx=hs.get("stx", stx), cnb=sh["gate"] or 0,
                           rsp=(S["RS_Q"] + S["RS_STRIDE"]) & 255,
                           q=[sh["R"], sh["flash"]] + sh["desc"])
                if sh["lost"]:
                    got.update(react=e(0, "REACT"), reactat=e(0, "REACTAT"))
                    exp.update(react=hs["react"], reactat=sh["I"])
                stats["shot"] += 1
                stats["hit"] += sh["lost"] > 0
                stats["fear"] += (hs.get("stf", 0) & 0x0C) == 4 and not (stf & 0x0C)
                if kind in GOLDK:
                    stats["gshot"] = stats.get("gshot", 0) + 1
                    stats["psn"] = stats.get("psn", 0) + (hs.get("stx", stx) != stx)
            elif kind in GOLDK and mrow and want["counter"] != counter and not want["used"] and counter:
                stats["gwalk"] = stats.get("gwalk", 0) + 1
            elif want["moved"]:
                stats["step"] += 1
            elif want["used"]:
                stats["hold"] += 1
            else:
                stats["no"] += 1
            if got != exp and len(bad_a) < 5:
                bad_a.append(dict(n=n_a, kind=kind, slot=slot, sx=sx, hx=hx, gap=gap, sy=sy, hy=hy_,
                                  diff={k_: (got.get(k_), exp.get(k_)) for k_ in exp if got.get(k_) != exp.get(k_)}))
            elif got != exp:
                bad_a.append(None)
            n_a += 1
        print(f"[info] A {n_a} situations: {stats}; stub T with a non-shooter {t_base}, worst extra T per "
              f"outcome (far6 + ai_ranged, contended stub incl.): "
              f"{ {k_: v - t_base for k_, v in tmax.items()} }", flush=True)
        check(f"A {n_a} seeded situations: Z80 hook == ranged_model (mismatches {len(bad_a)})", not bad_a,
              [b for b in bad_a if b][:3])
        # ------------------------------------------------- hook-level fixed cases
        clean = [T_AIR] * (8 * 32)
        for r_ in range(8):
            clean[r_ * 32] = clean[r_ * 32 + 31] = T_BRICK
        clean = clean + map0[8 * 32:]

        def hk(kind, gap, counter=0, slot=3, extra=(), bricks=(), res=(0, 0, 0), hdef=0, imm=0, seed=0x1357,
               hx=6, hhp=200, stf=0, hy=None, sy=None, gold=0, stx=None):
            """One hook call: the hero at hx, the shooter to its right at gap; -> (cf, entities, shooter x)."""
            w, hgt = kt[kind]["bw"], kt[kind]["bh"]
            sx = hx + hw + gap
            hy = S1 + 8 - hh if hy is None else hy
            sy = S1 + 8 - hgt if sy is None else sy
            ents = {0: ent_of(K_KNIGHT, hx, hy, EF_ACTIVE | EF_PLAYER, hp=hhp),
                    slot: ent_of(kind, sx, sy, EF_ACTIVE | EF_HOSTILE, POT=counter ^ 1, GOLD=gold)}
            for s_, k_, x_ in extra:
                ents[s_] = ent_of(k_, x_, S1 + 8 - kt[k_]["bh"], EF_ACTIVE | EF_HOSTILE, hp=5)
            rows = list(clean)
            for r_, c_ in bricks:
                rows[(r_ - S1) * 32 + c_] = T_BRICK
            put_world(None, ents, rows)
            p.wmem(S["ST_FLAGS"], [stf] + [0] * 15)
            p.wmem(S["ST_T1"], [0x30 if stf & 3 else 0] + [0] * 15)
            if stx is not None:
                p.wb(S["ST_X"], stx)
            p.wmem(S["HERO_RES"], list(res))
            p.wb("HERO_IMM", imm)
            p.wb("HERO_DEF", hdef)
            p.wb("TURN_TICK", 0)
            p.wb("TURN_PEND", 0)
            p.wb("COMBAT_NOT_BEFORE", 0)
            p.wmem(S["RNG_STATE"], w16(seed))
            cf = p.hook(slot)
            return cf, p.z.read_memory(S["P_ENTITIES"], 16 * STRIDE), sx

        def shot(mem, slot=3):
            return mem[slot * STRIDE + E_["MSG"]] in (S["MSG_M_HIT"], S["MSG_M_MISS"])

        # T the hook's own cost: the same world with the shooter re-kinded to a Skeleton (same body, no
        # rk_tab row: ai_rhook's reject) as the baseline; contended-stub T (ZEsarUX), far6 included
        def hook_t(kind, gap, **kw):
            hk(K_SKELETON, gap, **kw)
            t0 = p.tstates
            hk(kind, gap, **kw)
            return p.tstates - t0
        tcost = dict(other_storey=hook_t(K["ARCHER"], 5, hy=8 - hh), out_of_range=hook_t(K["ARCHER"], 12),
                     hold_gap9=hook_t(K["ARCHER"], 9, counter=1), step_away=hook_t(K["ARCHER"], 2, counter=1),
                     shot_necro=hook_t(K["NECRO"], 7), shot_archer=hook_t(K["ARCHER"], 9, stf=2))
        print(f"[info] T hook cost over the reject (T): {tcost}", flush=True)

        # E range edges
        edge = {}
        for nm, kind, r in (("Archer", K["ARCHER"], 10), ("Slinger", K["SLINGER"], 6), ("Sniper", K["SNIPER"], 14),
                            ("Necro", K["NECRO"], 8)):
            res_ = []
            for g in (r - 1, r):
                cf, mem, _ = hk(kind, g, hx=2)
                res_.append(shot(mem))
            edge[nm] = res_
        check("E range edges: Archer 9 fires / 10 not, Slinger 5 / 6, Sniper 13 / 14, Necro 7 / 8",
              all(v == [True, False] for v in edge.values()), edge)

        # B blocking (hook level)
        cf, mem, sx = hk(K["ARCHER"], 6, extra=[(5, K_RAT, 6 + hw + 2)])
        ratb = (cf, shot(mem), mem[5 * STRIDE + E_["HP"]], mem[E_["HP"]])
        cf, mem, sx = hk(K["ARCHER"], 6, bricks=[(S1 + 8 - kt[K["ARCHER"]]["bh"] + 2, 6 + hw + 3)])
        blk = (cf, shot(mem))
        cf, mem, sx = hk(K["ARCHER"], 6, bricks=[(S1 + 7, 6 + hw + 3)])     # a solid cell below the flight row
        low = shot(mem)
        cf, mem, sx = hk(K["NECRO"], 5, hy=S1 + 8 - hh - 2)                  # hero mid-ladder
        lad = (cf, shot(mem))
        cf, mem, sx = hk(K["NECRO"], 5, hy=8 - hh)                           # hero on storey 0
        oth = (cf, shot(mem))
        check("B blocked: a Rat in the gap (no shot, Rat HP 5), a flight-row block (none), a block on row 9s+7 only "
              "does not block; mid-ladder / other-storey hero: CF 0, no shot",
              ratb == (False, False, 5, 200) and blk == (False, False) and low and lad == (False, False)
              and oth == (False, False), (ratb, blk, low, lad, oth))

        # S step-away at gap 2 (counter 1)
        cf, mem, sx = hk(K["ARCHER"], 2, counter=1)
        a1 = (cf, mem[3 * STRIDE + E_["X"]] - sx, bool(mem[3 * STRIDE + E_["FLAGS"]] & EF_LEFT))
        cf, mem, sx = hk(K["SNIPER"], 2, counter=1)
        a2 = (cf, mem[3 * STRIDE + E_["X"]] - sx, bool(mem[3 * STRIDE + E_["FLAGS"]] & EF_LEFT))
        cf, mem, sx = hk(K["ARCHER"], 2, counter=1, extra=[(6, K_RAT, 6 + hw + 2 + 3)])
        a3 = (cf, mem[3 * STRIDE + E_["X"]] - sx, bool(mem[3 * STRIDE + E_["FLAGS"]] & EF_LEFT))
        cf, mem, sx = hk(K["ARCHER"], 3, counter=1)
        a4 = (cf, mem[3 * STRIDE + E_["X"]] - sx)
        check("S gap 2: the Archer steps away (+1, faces away), the Sniper holds facing the hero, a blocked Archer "
              "holds facing the hero; gap 3 reloading: hold", a1 == (True, 1, False) and a2 == (True, 0, True)
              and a3 == (True, 0, True) and a4 == (True, 0), (a1, a2, a3, a4))

        # D damage rules + FEAR rate + Mirror Helm
        def lost_of(kind, hdef, res=(0, 0, 0), n=40):
            out = []
            for i_ in range(n):
                cf, mem, _ = hk(kind, 4, hdef=hdef, res=res, seed=0x100 + 37 * i_, stf=2)   # held: eva 0
                if shot(mem) and mem[3 * STRIDE + E_["MSG"]] == S["MSG_M_HIT"]:
                    out.append(200 - mem[E_["HP"]])
            return out
        phys = lost_of(K["ARCHER"], 10)
        dark = lost_of(K["NECRO"], 10)
        darkr = lost_of(K["NECRO"], 0, res=(0, 1 << 2, 0))
        check("D PHYS = max(1, d - DEF) (DEF 10: always 1); DARK ignores DEF (2..7); DARK R halves (1..3)",
              phys and set(phys) == {1} and set(dark) <= set(range(2, 8)) and len(set(dark)) > 3
              and set(darkr) <= {1, 2, 3}, (sorted(set(phys)), sorted(set(dark)), sorted(set(darkr))))
        fear = 0
        NF = 600
        for i_ in range(NF):
            cf, mem, _ = hk(K["NECRO"], 4, seed=(0x2000 + 97 * i_) & 0xFFFF)
            fear += (p.rb(S["ST_FLAGS"]) & 0x0C) == 4
        check(f"D FEAR on a DARK hit ~ 1/3 (85/256): {fear}/{NF}", 0.28 < fear / NF < 0.39, fear)
        mh = 0
        for i_ in range(100):
            cf, mem, _ = hk(rnd.choice([K["NECRO"], K["BONE"]]), rnd.randint(2, 7), res=(0, 3 << 2, 0),
                            seed=i_ + 1)
            mh += shot(mem) or cf
        check("D Mirror Helm (DARK X): 0 Necro / Bone Caller shots (and no turn used) in 100 tries", mh == 0, mh)

        # G BOSS-RANGED: golden-only rows, range 6, walk between shots, the spit's poison
        KG, KS = S["K_GOBLIN"], S["K_SPIDER"]
        ge = {}
        for nm, kind in (("King", KG), ("Queen", KS)):
            ge[nm] = [shot(hk(kind, g, hx=2, gold=LEK_GOLD)[1]) for g in (5, 6)]
        plain = []
        for kind in (KG, KS):
            cf, mem, sx = hk(kind, 3, counter=0)
            plain.append((cf, shot(mem), (mem[3 * STRIDE + E_["POT"]] & 3) ^ 1, p.rw("RNG_STATE") == 0x1357))
        walk = []
        for kind in (KG, KS):
            cf, mem, sx = hk(kind, 3, counter=1, gold=LEK_GOLD)
            walk.append((cf, shot(mem), (mem[3 * STRIDE + E_["POT"]] & 3) ^ 1))
        check("G golden King / Queen fire at gap 5, not 6; ordinary Goblin / Spider: CF 0, no shot, counter 0 kept, "
              "RNG untouched; golden, counter 1, gap 3: CF 0 (walker rules), no shot, counter 0",
              all(v == [True, False] for v in ge.values()) and all(x == (False, False, 0, True) for x in plain)
              and all(x == (False, False, 0) for x in walk), (ge, plain, walk))
        PSN = 1 << S["STS_POISON_BIT"]

        def spit(kind, stx0, imm=0, n=60):
            """hits on a held hero (eva 0): -> list of (HP lost, ST_X after, POISON bit)."""
            out = []
            for i_ in range(n):
                cf, mem, _ = hk(kind, 4, gold=LEK_GOLD, stf=2 | (PSN if stx0 else 0), stx=stx0, imm=imm, hdef=0,
                                seed=0x300 + 41 * i_)
                if shot(mem) and mem[3 * STRIDE + E_["MSG"]] == S["MSG_M_HIT"]:
                    out.append((200 - mem[E_["HP"]], p.rb(S["ST_X"]), bool(p.rb(S["ST_FLAGS"]) & PSN)))
            return out
        fresh, capd, silk, dag = spit(KS, 0), spit(KS, 24), spit(KS, 0, imm=S["IMMF_POISON"]), spit(KG, 0)
        check("G spit: every hit poisons + 12 (fresh 12, 24 -> cap 30), dmg 1d2 + 1 golden (2..3); Silk Cloak "
              "(IMMF_POISON): damage, no poison; the King's dagger 1d3 + 1 (2..4), no poison",
              fresh and capd and silk and dag
              and all(x[1:] == (12, True) for x in fresh) and all(x[1:] == (30, True) for x in capd)
              and all(x[1:] == (0, False) for x in silk) and all(x[1:] == (0, False) for x in dag)
              and {x[0] for x in fresh + silk} == {2, 3} and {x[0] for x in dag} == {2, 3, 4},
              (fresh[:4], capd[:4], silk[:4], dag[:6], len(fresh), len(dag)))

        # ATTR: every shot's colour (FXD_ATTR 0 = fx_meta, the model's descriptors); the hero's thrown dagger is $47
        fm = S["fx_meta"] - S["KFID_FXM"]
        meta = {nm: p.rb(fm + S["FID_" + nm]) & 0x7F for nm in
                ("dagger_spin1", "dagger_spin2", "spark_fly1", "spark_fly2", "arrow_fly1", "arrow_fly2",
                 "nbolt_fly1", "nbolt_fly2")}
        check("ATTR monster shots: rock / King dagger (dagger_spin) = ROCK_ATTR $06, Queen spark $43, arrow $07, "
              "Necro bolt $43; the hero's throw THROW_ATTR $47 (proj3 writes it; tests/proj3 + abil_ammo model)",
              meta == {"dagger_spin1": 6, "dagger_spin2": 6, "spark_fly1": 0x43, "spark_fly2": 0x43, "arrow_fly1": 7,
                       "arrow_fly2": 7, "nbolt_fly1": 0x43, "nbolt_fly2": 0x43}
              and S["ROCK_ATTR"] == 6 and S["THROW_ATTR"] == 0x47, meta)

        # --------------------------------------------------- real turns
        seqk = {K["ARCHER"]: K_SKELETON, K["SNIPER"]: K_SKELETON, K["NECRO"]: K_SKELETON,
                K["BONE"]: K_SKELETON, K["SLINGER"]: S["K_GOBLIN"]}

        def arena(shooters, hx=6, hy=None, hhp=200):
            """Room A's map as booted, the hero at hx storey 1, shooters [(slot, kind, x[, y])]; the
            unpooled kinds draw with the Skeleton / Goblin sequences (KT_SEQ poke)."""
            for k_, b_ in seqk.items():
                p.wb(S["kind_tab"] + S["KT_SEQ"] + k_, p.rb(S["kind_tab"] + S["KT_SEQ"] + b_))
            ents = {0: ent_of(K_KNIGHT, hx, S1 + 8 - hh if hy is None else hy, EF_ACTIVE | EF_PLAYER, hp=hhp)}
            for sl, k_, x_, *yy in shooters:
                ents[sl] = ent_of(k_, x_, yy[0] if yy else S1 + 8 - kt[k_]["bh"], EF_ACTIVE | EF_HOSTILE | EF_LEFT,
                                  hp=60, POT=0)
            put_world(None, ents, map0)
            p.wmem(S["ST_FLAGS"], [0] * 16)
            p.wmem(S["ST_T1"], [0] * 16)
            p.wmem(S["HERO_RES"], [0, 0, 0])
            p.wb("HERO_DEF", 0)
            p.wb("FX_DROP", 0)
            p.wb("TURN_PEND", 0)
            p.settle(3)

        def turns(n, slots, heal=True):
            """n Wait turns; -> per turn the set of slots that shot."""
            out = []
            for _ in range(n):
                for sl in slots:
                    p.wb(S["P_ENTITIES"] + sl * STRIDE + E_["MSG"], 0)
                if heal:
                    p.wb(S["P_ENTITIES"] + E_["HP"], 200)
                p.turn("WAIT", max_ticks=200)
                out.append({sl for sl in slots if p.rb(S["P_ENTITIES"] + sl * STRIDE + E_["MSG"]) in
                            (S["MSG_M_HIT"], S["MSG_M_MISS"])})
            return out

        def start_turn():
            p.hold("WAIT")
            for _ in range(5):
                p.tick()
                if p.rb("TURN_PHASE") == 1:
                    break
            p.release()

        p.boot(K_KNIGHT)                                   # the stubs above left the game loop
        arena([(3, K["ARCHER"], 15)])
        ca = [i_ + 1 for i_, v in enumerate(turns(7, [3])) if v]
        arena([(4, K["NECRO"], 14)])
        cn = [i_ + 1 for i_, v in enumerate(turns(9, [4])) if v]
        check("C cadence: Archer (N 1) shoots on turns 2, 4, 6; Necromancer (N 2) on 2, 5, 8 (none on the first)",
              ca == [2, 4, 6] and cn == [2, 5, 8], (ca, cn))
        arena([(3, K["ARCHER"], 17), (5, K_RAT, 12)])
        tb = turns(4, [3])
        check("B real turns: a Rat between: the Archer never shoots (the Rat untouched by it)",
              not any(tb) and p.ent(5)["HP"] == 60, (tb, p.ent(5)["HP"]))

        # K an arrow kill: DEATH at the impact tick, GS_DEAD after it
        kres = None
        for sd in range(1, 40):
            arena([(3, K["ARCHER"], 16)], hhp=1)
            p.set_ent(3, POT=1)                            # counter 0: shoots this turn
            p.wmem(S["RNG_STATE"], w16(0x4000 + sd * 77))
            log = []
            start_turn()
            for _ in range(400):
                e0 = p.ent(0)
                log.append((p.rb("TURN_TICK"), e0["HP"], e0["REACT"], p.rb(S["P_ENTITIES"] + E_["REACTAT"]), e0["MODE"],
                            p.rb("GAME_STATE"), p.rb("FX_BUSY")))
                if p.rb("GAME_STATE") == S["GS_DEAD"] or (log[0][1] and p.idle()):
                    break
                p.tick()
            if log and log[0][1] == 0:
                kres = log
                break
        ok_k, det = False, kres
        if kres:
            I = kres[0][3]
            cut = next((i_ for i_, x in enumerate(kres) if x[0] > I), len(kres))
            pre, post = kres[:cut], kres[cut:]               # probes after ticks < I / from I on
            ok_k = (all(x[4] != S["M_SEQ"] and x[2] == 3 and x[5] == S["GS_PLAYING"] for x in pre)
                    and post and post[0][4] == S["M_SEQ"] and any(x[6] for x in kres)
                    and kres[-1][5] == S["GS_DEAD"] and I == 0 + 2 + 1 + 7 + 1)
            det = (I, kres[:14], kres[-2:], len(kres))
        check("K arrow kill: HP 0 on the input tick, DEATH pending until the impact tick I (= 0 + 2 + slot 3 parity"
              " + gap 7 + 1), the death sequence from I, the FX flew, GS_DEAD only after", ok_k, det)

        # Q the FX queue: 2 tracks busy, 2 Slingers (both sides) -> one track + one queued, both start
        p.boot(K_KNIGHT)                                   # K ended the game
        arena([(1, K["SLINGER"], 14), (2, K["SLINGER"], 1)], hx=7)
        for sl in (1, 2):
            p.set_ent(sl, POT=1)
        p.set_ent(2, FLAGS=EF_ACTIVE | EF_HOSTILE)
        dummy = [S["FID_arrow_fly1"], S["FID_arrow_fly2"], 255, 255, 0, 2, 3, 0, 0, 0, 1, 22, 0, 0, 0, 0]
        start_turn()                                       # the input tick ran: shots queued (R 2 / 3)
        for i_, trk in enumerate(("FXT0", "FXT1")):          # 2 tracks busy now (fx_load by hand)
            p.wmem(S[trk], dummy + [S["FXS_WAIT"], 0, 255])
            p.wb(S[trk] + S["FX_DFID"], 255)
        p.wb("FX_BUSY", p.rb("FX_BUSY") | 3)
        assert S["FX_ST"] == 16 and S["FX_PH"] == 17 and S["FX_FID"] == 18
        qlog = []
        for _ in range(80):
            qlog.append((p.rb("TURN_TICK"), p.rb("FX_BUSY"), p.rb("FXQ_N"), p.rb("TURN_PEND"), p.rb("FX_DROP")))
            if p.idle():
                break
            p.tick()
        shots_q = [p.rb(S["P_ENTITIES"] + sl * STRIDE + E_["MSG"]) for sl in (1, 2)]
        check("Q 2 tracks busy + 2 Slingers: released on ticks 2 / 3 by slot parity, the 2nd waits in FXQ, "
              "both start, FX_DROP 0, the turn ends",
              all(m_ in (S["MSG_M_HIT"], S["MSG_M_MISS"]) for m_ in shots_q) and any(x[2] == 1 for x in qlog)
              and qlog[-1][4] == 0 and p.idle(), (shots_q, qlog[:16]))

        # L a climbing shooter out of line walks to the ladder (.seek)
        p.settle(30)
        arena([(3, K["SLINGER"], 14, 8 - kt[K["SLINGER"]]["bh"])], hx=12)
        xs = []
        for _ in range(12):
            p.wb(S["P_ENTITIES"] + E_["HP"], 200)
            p.turn("WAIT", max_ticks=200)
            e3 = p.ent(3)
            xs.append((e3["X"], e3["Y"]))
        check("L the Slinger on the other storey seeks a ladder (walks to col 5 / 23, then climbs)",
              any(y_ != xs[0][1] for _, y_ in xs) or xs[-1][0] in (5, 23), xs)

        # G real turns: a golden Goblin King walks in from far away, shoots every 3rd turn once in range
        # (gap < 6), keeps walking between the shots, then melees
        p.boot(K_KNIGHT)
        arena([(3, S["K_GOBLIN"], 18)], hx=4)
        p.wb(S["P_ENTITIES"] + 3 * STRIDE + E_["GOLD"], LEK_GOLD)
        glog = []
        for t_ in range(14):
            p.wb(S["P_ENTITIES"] + 3 * STRIDE + E_["MSG"], 0)
            p.wb(S["P_ENTITIES"] + E_["HP"], 200)
            x0 = p.ent(3)["X"]
            p.turn("WAIT", max_ticks=200)
            glog.append((t_ + 1, x0, p.ent(3)["X"], p.rb(S["P_ENTITIES"] + 3 * STRIDE + E_["MSG"])))
        gap0 = {t_: x0 - (4 + hw) for t_, x0, _, _ in glog}
        shots_t = [t_ for t_, _, _, m_ in glog if m_ in (S["MSG_M_HIT"], S["MSG_M_MISS"]) and gap0[t_] > 1]   # gap <= 1: melee
        moved_in = [t_ for t_, x0, x1, m_ in glog if x1 < x0 and 1 < gap0[t_] < 6 and t_ not in shots_t]
        check("G real turns: the golden King shoots only at gap < 6, 3 turns apart, and walks in (x - 1) on a "
              "turn between shots while in range",
              len(shots_t) >= 2 and all(b - a == 3 for a, b in zip(shots_t, shots_t[1:]))
              and all(gap0[t_] < 6 for t_ in shots_t) and moved_in, glog)

    print(f"[{'FAIL' if fails else 'PASS'}] ranged: {fails or 'all checks'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
