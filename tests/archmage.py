#!/usr/bin/env python3
"""3F-T11b: the Necromancer Archmage's spell AI (game.md §9.9 ARCHMAGE-SPEC; src/arch6.asm
arch_ai, bank-2 ai_mon, ranged6.asm rg_shoot / rg_line, turn3.asm rs_self) on a booted
Knight game, PROTO room A, rows 0..16 rewritten per case (rows 8 / 17 = the room's floors).

  A   A/B vs tools/ranged_model.py arch_decide: ARCH_N (default 1,500) seeded situations
      through the real hook (stub: build_live, cache_player, ACT_SLOT, ai_mon): both
      storeys, mid-ladder hero, counters C / S / H / P / blinked / init, hp at / under half
      (blink, P' legality: bricks / holes / bodies, the 1..8-col search), the summon gate
      (queue busy, summon-made bodies, the cap), hold lock (held / HOLD_GUARD hero), every
      rider and resistance, Mirror Helm (the ½ return + 2nd track), immunities (Sleep /
      Venom UNAFFECTED). Compared: E_RCD, ST_X state, facing, x / y, its hp / reaction,
      E_MSG, the hero's HP / ST_FLAGS / ST_T1 / ST_T2 / ST_X / reaction, RNG, RS_Q entries
      (R, flash, 16-B descriptor incl. the ink), RS_P, CNB, the body ink (KT_ATTR), the
      blink flash, the spawn queue. The staff (attack_if_reach melee) is outside the model:
      those cases compare the state / facing only.
  R   real turns (resolve_monsters, end_turn): the hero waiting in line at gap 9: a bolt on
      turns 2, 4, 6, 8 (C: none on the first), a summon on turn 1 made at end_turn (one
      Skeleton beside it, RCD_SUMMONED), something every turn; the body ink follows P.
  M   real turns with the Mirror Helm: the Death Bolts hurt the Archmage (½), the hero 0;
      two FX tracks start on a Death Bolt turn.
Run: ZRCP_PORT=<port> python3 tests/archmage.py
"""
import os
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_RAT, K_BAT, K_SKELETON, F3  # noqa: E402
from proj3 import T as PT, w16  # noqa: E402
import ranged_model as M  # noqa: E402

STUB = S["LOWRAM_END_3B"]
STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT, EF_DYING = 1, 2, 4, 8, 16
E_ = {k: S["E_" + k] for k in ("KIND", "ROOM", "FLAGS", "X", "Y", "HP", "MAXHP", "POT", "PX", "PY", "MODE",
                               "REACT", "REACTAT", "MSG", "TGT", "HIT", "FLT", "FLA", "GOLD")}
KA = S["K_ARCHMAGE"]
DEATH_FLAG = S["LF_SEAL_OPEN"] if F3 else S["LF_GRATE_OPEN"]   # P3: the D8 death breaks the seal
T_AIR, T_BRICK = S["T_AIR"], S["T_BRICK"]
N_A = int(os.environ.get("ARCH_N", "1500"))
INK = S["kind_tab"] + S["KT_ATTR"] + KA
TF = {k: S["TF_" + k] for k in ("SOLID", "FLOOR", "HOLE", "LADDER", "DOOR")}


class T(PT):
    def kt(self):
        g = lambda f, k: self.rb(S["kind_tab"] + S[f] + k)  # noqa: E731
        return {k: dict(bw=g("KT_BW", k), bh=g("KT_BH", k), eva=g("KT_EVA", k)) for k in range(S["K_COUNT"])}

    def hook(self, slot):
        """build_live, cache_player, ACT_SLOT, IX, ai_mon (the real bank-2 entry)."""
        ent = S["P_ENTITIES"] + slot * STRIDE
        inner = ([0xCD] + w16(S["build_live"]) + [0xCD] + w16(S["cache_player"]) +
                 [0x3E, slot, 0x32] + w16(S["ACT_SLOT"]) + [0xDD, 0x21] + w16(ent) +
                 [0xCD] + w16(S["ai_mon"]))
        assert self.code(self.bank3(inner)), "ai_mon stub did not return"


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:1800]}", flush=True)

        p.boot(K_KNIGHT)
        kt = p.kt()
        tflags = list(p.z.read_memory(S["tile_flags"], 64))
        room = p.rb("CUR_ROOM")
        hw, hh = kt[K_KNIGHT]["bw"], kt[K_KNIGHT]["bh"]
        aw, ah = kt[KA]["bw"], kt[KA]["bh"]
        map0 = list(p.z.read_memory(S["ROOM_MAP"], 18 * 32))
        WT = {K_RAT: S["WT_K_RAT"], K_BAT: S["WT_K_BAT"], K_SKELETON: S["WT_K_SKELETON"], KA: S["WT_K_ARCHMAGE"]}
        fx = S["FID_nbolt_fly1"]
        p.wb(S["kind_tab"] + S["KT_SEQ"] + KA, p.rb(S["kind_tab"] + S["KT_SEQ"] + K_SKELETON))

        def put_world(ents, rows):
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
            p.wmem(S["ROOM_MAP"], rows)

        def ent_of(kind, x, y, flags, hp=30, **kw):
            d = dict(KIND=kind, X=x, Y=y, FLAGS=flags, HP=hp, MAXHP=hp, MODE=0, REACT=0, REACTAT=0, MSG=0,
                     TGT=0, HIT=0, FLT=0, FLA=0, POT=0, GOLD=0)
            d.update(kw)
            return d

        # ------------------------------------------------------------- A
        rnd = random.Random(0xA4C)
        bad, n_a, stats, tmax = [], 0, {}, {}
        while n_a < N_A:
            slot = rnd.randint(1, 15)
            ast = rnd.choice([1, 1, 1, 0])
            ay = 9 * ast + 8 - ah
            u = rnd.random()
            if u < 0.8:
                hst, hlad = ast, 0
            elif u < 0.9:
                hst, hlad = 1 - ast, 0
            else:
                hst, hlad = 1, 1
            hy = 9 * hst + 8 - hh - (rnd.randint(1, 3) if hlad else 0)
            gap = rnd.choice([rnd.randint(0, 20), rnd.randint(0, 3), 4, 5, 11, 12])
            if rnd.random() < 0.5:
                ax = rnd.randint(2, 27)
                hx = ax + aw + gap
            else:
                hx = rnd.randint(1, 27)
                ax = hx + hw + gap
            if not (2 <= ax <= 29 - aw + 1 and 1 <= hx and hx + hw - 1 <= 30):
                continue
            rows = [T_AIR] * (18 * 32)
            for r_ in range(18):
                if r_ in (8, 17):
                    rows[r_ * 32:(r_ + 1) * 32] = map0[r_ * 32:(r_ + 1) * 32]
                else:
                    rows[r_ * 32] = rows[r_ * 32 + 31] = T_BRICK
            fr = ay + 2
            if rnd.random() < 0.2:
                rows[fr * 32 + rnd.randint(1, 30)] = T_BRICK
            if rnd.random() < 0.4:                   # the blink target's standing row: blocks
                ts = 1 - ast
                for _ in range(rnd.randint(1, 3)):
                    rows[(9 * ts + 7) * 32 + rnd.randint(1, 30)] = T_BRICK
            mp = {r_: [tflags[rows[r_ * 32 + c]] for c in range(32)] for r_ in range(18)}
            maxhp = 67
            ahp = rnd.choice([maxhp, rnd.randint(12, maxhp), rnd.randint(12, 33), 33, 34])
            c = rnd.choice([0, 0, 1])
            sv = rnd.choice([0, 0, 0, 1, 2, 6])
            rcd = (c ^ 1) | (sv << 2)
            if rnd.random() < 0.15:
                stx = 0
            else:
                stx = 0x80 | rnd.randint(0, 4) | (rnd.choice([0, 0, 1, 2, 4]) << 3) | (0x40 if rnd.random() < 0.5 else 0)
            left = rnd.random() < 0.5
            ents = {0: ent_of(K_KNIGHT, hx, hy, EF_ACTIVE | EF_PLAYER, hp=rnd.randint(1, 60))}
            ents[slot] = ent_of(KA, ax, ay, EF_ACTIVE | EF_HOSTILE | (EF_LEFT if left else 0), hp=ahp, MAXHP=maxhp,
                                POT=rcd)
            bodies = [(0, hx, hy, hw, hh, False)]
            for _ in range(rnd.choice([0, 0, 1, 2, 3])):
                bs = rnd.randint(1, 15)
                if bs in ents:
                    continue
                bk = rnd.choice([K_RAT, K_BAT, K_SKELETON])
                bw_, bh_ = kt[bk]["bw"], kt[bk]["bh"]
                st_ = rnd.randint(0, 1)
                by = 9 * st_ + 1 if bk == K_BAT else 9 * st_ + 8 - bh_
                bx = rnd.randint(1, 31 - bw_)
                dying = rnd.random() < 0.1
                ents[bs] = ent_of(bk, bx, by, EF_ACTIVE | EF_HOSTILE | (EF_DYING if dying else 0),
                                  POT=0x40 if rnd.random() < 0.4 else 0)
                bodies.append((bs, bx, by, bw_, bh_, dying))
            res = [0, 0, 0]
            v = rnd.random()
            if v < 0.25:
                res[1] |= 3 << 2                       # DARK X (Mirror Helm)
            elif v < 0.35:
                res[1] |= 1 << 2                       # DARK R
            if rnd.random() < 0.2:
                res[0] |= rnd.choice([1, 2]) << 2      # FIRE R / I
            if rnd.random() < 0.2:
                res[0] |= rnd.choice([1, 2]) << 4      # COLD R / I
            if rnd.random() < 0.15:
                res[1] |= rnd.choice([1, 2])           # DRAIN R / I
            imm = sum(b for b in (1, 2, 4, 8, 16) if rnd.random() < 0.12)
            stf, st1, st2, hstx = 0, 0, 0, 0
            v = rnd.random()
            if v < 0.12:
                stf, st1 = 0x02, 0x30                  # ASLEEP
            elif v < 0.22:
                stf, st1 = 0x01, 0x20                  # FROZEN
            elif v < 0.3:
                stf = 0x40                             # HOLD_GUARD
            elif v < 0.4:
                stf, hstx = 0x10, rnd.randint(1, 30)   # POISON on
            elif v < 0.48:
                stf, st1 = 0x04, 2                     # FEAR
            elif v < 0.54:
                stf, st2 = 0x20, 3                     # WEAK
            tt = rnd.randint(0, 5)
            seed = rnd.randint(1, 0xFFFF)
            ink = rnd.choice([0x04, 0x43, 0x45])
            busy = rnd.random() < 0.1
            put_world(ents, rows)
            p.wmem(S["ST_FLAGS"], [stf] + [0] * 15)
            p.wmem(S["ST_T1"], [st1] + [0] * 15)
            p.wmem(S["ST_T2"], [st2] + [0] * 15)
            stxa = [hstx] + [0] * 15
            stxa[slot] = stx
            p.wmem(S["ST_X"], stxa)
            p.wmem(S["HERO_RES"], res)
            p.wb("HERO_IMM", imm)
            p.wb("HERO_DEF", rnd.randint(0, 3))
            p.wb("TURN_TICK", tt)
            p.wb("TURN_PEND", 0)
            p.wb("COMBAT_NOT_BEFORE", 0)
            p.wb("FX_DROP", 0)
            p.wb("HSTAGE", 0)
            p.wb(INK, ink)
            p.wmem(S["RNG_STATE"], w16(seed))
            p.wmem(S["SPQ_K"], [K_RAT if busy else 0, 0, 0])
            live = [(s_, e_) for s_, e_ in ents.items() if s_ and not e_["FLAGS"] & EF_DYING]
            ns = sum(1 for s_, e_ in live if e_["POT"] & 0x40)
            free = any(s_ not in ents for s_ in range(1, 16))
            summon_ok = (not busy and ns < S["AM_LIVE"] and free and len(live) < S["ROOM_CAP"])
            # (user 2026-11-01: the Archmage's summon is exempt from LP_SIGMA_CAP; one live summon)
            hero = dict(x=hx, y=hy, w=hw, h=hh, storey=hst, ladder=hlad, hp=ents[0]["HP"], res=res,
                        def_=0, imm=imm, stf=stf, st1=st1, st2=st2, stx=hstx, react=0)
            hero["def"] = p.rb("HERO_DEF")
            sit = dict(x=ax, y=ay, w=aw, h=ah, slot=slot, hp=ahp, maxhp=maxhp, rcd=rcd, stx=stx, storey=ast,
                       left=left, turn_tick=tt, map=mp, bodies=bodies, summon_ok=summon_ok, hero=hero, tf=TF,
                       xmin=S["LP_XMIN"], xmax=S["LP_XMAX"], ink=ink, dark_res=M.RSP_R)
            rng = M.Rng(seed)
            want = M.arch_decide(sit, rng, fx)
            p.hook(slot)
            act = want["act"]
            tag = act + (str(want["spell"]) if want["spell"] is not None else "")
            stats[tag] = stats.get(tag, 0) + 1
            tmax[act] = max(tmax.get(act, 0), p.tstates)
            mem = p.z.read_memory(S["P_ENTITIES"], 16 * STRIDE)
            e = lambda s_, f: mem[s_ * STRIDE + E_[f]]  # noqa: E731
            got = dict(rcd=e(slot, "POT"), stx=p.rb(S["ST_X"] + slot), left=bool(e(slot, "FLAGS") & EF_LEFT),
                       x=e(slot, "X"), y=e(slot, "Y"), hp=e(slot, "HP"), ink=p.rb(INK))
            exp = dict(rcd=want["rcd"], stx=want["stx"], left=want["left"], x=want["x"], y=want["y"],
                       hp=want["hp"], ink=want["ink"])
            if act != "staff":
                got.update(rng=p.rw("RNG_STATE"), msg=e(slot, "MSG"), sq=list(p.z.read_memory(S["SPQ_K"], 3)))
                exp.update(rng=rng.st, msg=want["msg"] if want["msg"] is not None else 0,
                           sq=[K_SKELETON | 0xC0, slot, 1] if act == "summon" else [K_RAT if busy else 0, 0, 0])
            if act == "blink":
                got["fl"] = (e(slot, "FLT"), e(slot, "FLA"))
                exp["fl"] = want["fl"]
            if want["shots"]:
                hs = want["hero"]
                got.update(hhp=e(0, "HP"), stf=p.rb(S["ST_FLAGS"]), st1=p.rb(S["ST_T1"]), st2=p.rb(S["ST_T2"]),
                           hstx=p.rb(S["ST_X"]), cnb=p.rb("COMBAT_NOT_BEFORE"), rsp=p.rb("RS_P"),
                           q=[list(p.z.read_memory(S["RS_Q"] + i_ * S["RS_STRIDE"], S["RS_STRIDE"]))
                              for i_ in range(len(want["shots"]))], drop=p.rb("FX_DROP"))
                exp.update(hhp=hs["hp"], stf=hs["stf"], st1=hs["st1"], st2=hs["st2"], hstx=hs["stx"],
                           cnb=want["cnb"], rsp=(S["RS_Q"] + len(want["shots"]) * S["RS_STRIDE"]) & 255,
                           q=want["shots"], drop=0)
                if want["hreactat"]:
                    got.update(hreact=e(0, "REACT"), hreactat=e(0, "REACTAT"))
                    exp.update(hreact=hs["react"], hreactat=want["hreactat"])
                if want["reactat"]:
                    got.update(react=e(slot, "REACT"), reactat=e(slot, "REACTAT"))
                    exp.update(react=want["react"], reactat=want["reactat"])
            if got != exp:
                if len(bad) < 5:
                    bad.append(dict(n=n_a, act=tag, slot=slot, ax=ax, ay=ay, hx=hx, hy=hy, gap=gap, stx=stx,
                                    rcd=rcd, stf=stf, res=res, imm=imm,
                                    diff={k_: (got.get(k_), exp.get(k_)) for k_ in exp if got.get(k_) != exp.get(k_)}))
                else:
                    bad.append(None)
            n_a += 1
        print(f"[info] A {n_a} situations: {dict(sorted(stats.items()))}; worst stub T per act (far6 + arch_ai incl.):"
              f" {tmax}", flush=True)
        check(f"A {n_a} seeded situations: Z80 arch_ai == ranged_model.arch_decide (mismatches {len(bad)})", not bad,
              [b for b in bad if b][:3])
        check("A coverage: every bolt / hex spell, blink, summon and staff seen",
              all(stats.get(k_, 0) for k_ in ("bolt0", "bolt1", "bolt2", "bolt3", "bolt4", "hex5", "hex6",
                                               "blink", "summon", "staff")), stats)

        # ------------------------------------------------------------- R / M real turns
        p.boot(K_KNIGHT)
        p.wb(S["kind_tab"] + S["KT_SEQ"] + KA, p.rb(S["kind_tab"] + S["KT_SEQ"] + K_SKELETON))
        map0 = list(p.z.read_memory(S["ROOM_MAP"], 18 * 32))

        def arena(hres=(2 << 4, 0, 0), pot=0x3C):
            ents = {0: ent_of(K_KNIGHT, 6, 17 - hh, EF_ACTIVE | EF_PLAYER, hp=200),
                    5: ent_of(KA, 6 + hw + 9, 17 - ah, EF_ACTIVE | EF_HOSTILE | EF_LEFT, hp=67, MAXHP=67, POT=pot)}
            put_world(ents, map0)
            p.wmem(S["ST_FLAGS"], [0] * 16)
            p.wmem(S["ST_T1"], [0] * 16)
            p.wmem(S["ST_T2"], [0] * 16)
            p.wmem(S["ST_X"], [0] * 16)
            p.wmem(S["HERO_RES"], list(hres))
            p.wb("HERO_IMM", 0x1F)                     # no status: the hero keeps waiting
            p.wb("HERO_DEF", 0)
            p.wb("TURN_PEND", 0)
            p.wb("SPQ_K", 0)
            p.wb(INK, 0x43)
            p.settle(3)

        def turns(n, mirror=False):
            log = []
            for _ in range(n):
                p.wb(S["P_ENTITIES"] + 5 * STRIDE + E_["MSG"], 0)
                p.wb(S["P_ENTITIES"] + E_["HP"], 200)
                hp0 = p.ent(5)["HP"]
                busy = [0]

                def pt(*_):
                    busy[0] = max(busy[0], bin(p.rb("FX_BUSY") & 7).count("1") + p.rb("FXQ_N"))
                assert p.turn("WAIT", per_tick=pt, max_ticks=200), "no turn"
                busy = busy[0]
                m_ = p.rb(S["P_ENTITIES"] + 5 * STRIDE + E_["MSG"])
                sm = [sl for sl in range(1, 16) if sl != 5 and p.ent(sl)["FLAGS"] & 1 and p.ent(sl)["POT"] & 0x40]
                log.append(dict(msg=m_, ink=p.rb(INK), summons=sm, hp=p.ent(5)["HP"], dhp=hp0 - p.ent(5)["HP"],
                                hero=p.ent(0)["HP"], tracks=busy, P=p.rb(S["ST_X"] + 5) & 7,
                                st=(p.rb("HERO_IMM"), p.rb(S["ST_FLAGS"]), p.rw("TURN_COUNTER"),
                                    p.rb(S["ST_X"] + 5), p.ent(5)["POT"])))
            return log

        arena(pot=0)                                   # S = 0, C = 1: the first turn summons
        l1 = turns(1)
        check("R real turn 1 (S 0, C 1): a summon, one summon-made Skeleton made at end_turn",
              l1[0]["msg"] == S["MSG_M_SUMMON"] and len(l1[0]["summons"]) == 1
              and p.ent(l1[0]["summons"][0])["KIND"] == K_SKELETON, l1)
        arena()                                        # S 15: no summon in the cadence run
        lg = turns(9)
        bolts = [i_ + 1 for i_, x in enumerate(lg) if x["msg"] == S["MSG_M_HIT"]]
        check("R real turns at gap 9 (COLD I hero): bolts on turns 2, 4, 6, 8 (C: none on the first); the body ink "
              "= ORDER[P] after every bolt; P cycles",
              bolts == [2, 4, 6, 8] and all(lg[b - 1]["ink"] == M.ARCH_INK[lg[b - 1]["P"]] for b in bolts)
              and [lg[b - 1]["P"] for b in bolts] == [1, 2, 3, 4],
              [(x["msg"], x["ink"], x["P"], x["st"]) for x in lg])
        arena(hres=(0, 3 << 2, 0))
        lg = turns(5, mirror=True)
        db = [x for x in lg if x["msg"] == S["MSG_M_HIT"]]
        check("M Mirror Helm: Death Bolt turns cost the hero 0 and the Archmage 1..5 (½ of 1d8+3), 2 tracks fly",
              db and db[0]["hero"] == 200 and 1 <= db[0]["dhp"] <= 5 and db[0]["tracks"] >= 2,
              [(x["msg"], x["dhp"], x["hero"], x["tracks"], x["P"]) for x in lg])

        # ------------------------------------------------------------- K killed by its own return
        # Mirror Helm hero, the Archmage at hp 2 (any Death Bolt roll 4..11 -> 2..5 back: lethal), the lair
        # boss of a D8 lair (LVL_LAIR / LP_BOSS / depth 8, LF_UNIQUE clear): deal_hit's kill path (EF_DYING,
        # RC_DEATH, mon_drop -> grate_open; D8: no unique, no drop roll) runs inside am_cast, which then
        # still sets the reaction tick I2, queues the return track (rg_q) and re-inks it (.ink).
        def lair(hp, depth=8):
            p.wb("LVL_LAIR", room)
            p.wb("LP_BOSS", KA)
            p.wb("LVL_DEPTH", depth)
            p.wb("LVL_FLAGS", p.rb("LVL_FLAGS") & ~(S["LF_UNIQUE"] | S["LF_GRATE_OPEN"] | S["LF_SEAL_OPEN"]) & 255)
            p.set_ent(5, HP=hp)
        arena(hres=(0, 3 << 2, 0), pot=0x3C | 1)           # C 0: this turn is a bolt turn (P 0: Death Bolt)
        lair(2)
        seed = 0x2468
        p.wmem(S["RNG_STATE"], w16(seed))
        p.wb("TURN_TICK", 0)
        e5 = p.ent(5)
        p.hook(5)
        ek = p.ent(5)
        gap = e5["X"] - (6 + hw)
        r0 = 0 + 2 + (5 & 1)
        i1 = r0 + gap + 1
        rng = M.Rng(seed)
        roll = rng.mod(8) + 1 + 3
        q = [list(p.z.read_memory(S["RS_Q"] + i_ * S["RS_STRIDE"], S["RS_STRIDE"])) for i_ in range(2)]
        kres = dict(hp=ek["HP"], dying=bool(ek["FLAGS"] & EF_DYING), react=ek["REACT"], reactat=p.rb(S["P_ENTITIES"] + 5 * STRIDE + E_["REACTAT"]),
                    rsp=p.rb("RS_P"), rng=p.rw("RNG_STATE"), flags=p.rb("LVL_FLAGS"), q0=q[0][:2], q1=q[1][:2],
                    attr=(q[0][2 + 4], q[1][2 + 4]), col=(q[0][2 + 5], q[1][2 + 5]), hero=p.ent(0)["HP"])
        check("K killed by its own Mirror Helm return: hp 0, DYING, DEATH at I2 = I + gap + 1, both tracks queued "
              "(R / I, re-inked $43, anchors swapped), RNG = the roll only (D8: no drop roll), LF_SEAL_OPEN (P3: "
              "the D8 boss-death flow, F3_GEN; the grate stays shut) + LF_UNIQUE set, the hero untouched",
              kres["hp"] == 0 and kres["dying"] and kres["react"] == 3 and kres["reactat"] == i1 + gap + 1
              and kres["rsp"] == (S["RS_Q"] + 2 * S["RS_STRIDE"]) & 255 and kres["rng"] == rng.st
              and kres["q0"] == [r0, 0] and kres["q1"] == [i1, 0] and kres["attr"] == (0x43, 0x43)
              and kres["col"] == (6 + hw + gap - 1, 6 + hw) and kres["flags"] & DEATH_FLAG
              and not kres["flags"] & S["LF_GRATE_OPEN"] * F3
              and kres["flags"] & S["LF_UNIQUE"] and kres["hero"] == 200, (kres, roll, gap, i1))
        # the same through a real turn: the death plays out, the game goes on (the slot freed, GS_PLAYING)
        p.boot(K_KNIGHT)
        p.wb(S["kind_tab"] + S["KT_SEQ"] + KA, p.rb(S["kind_tab"] + S["KT_SEQ"] + K_SKELETON))
        arena(hres=(0, 3 << 2, 0), pot=0x3C | 1)
        lair(3)
        p.wb(S["ST_X"] + 5, 0x80)
        assert p.turn("WAIT", max_ticks=300)
        for _ in range(3):
            p.turn("WAIT", max_ticks=300)
        kr = dict(state=p.rb("GAME_STATE"), flags5=p.ent(5)["FLAGS"], hp5=p.ent(5)["HP"], lvl=p.rb("LVL_FLAGS"),
                  hero=p.ent(0)["HP"], fxdrop=p.rb("FX_DROP"), tp=p.rb("TURN_PEND"))
        check("K real turn: the self-killed Archmage dies (slot inactive / dying done), GS_PLAYING, FX_DROP 0, the "
              "next turns run (TURN_PEND 0)",
              kr["state"] == S["GS_PLAYING"] and kr["hp5"] == 0 and not (kr["flags5"] & EF_ACTIVE and
                                                                          not kr["flags5"] & EF_DYING)
              and kr["fxdrop"] == 0 and kr["tp"] == 0 and kr["lvl"] & DEATH_FLAG, kr)

        # ------------------------------------------------------------- L blink box beside a ladder top
        # A legal blink box (sp_try: no ladder / hole floor cell, no ladder standing cell) may sit beside the
        # top of a shaft, overlapping the box the hero climbs into. The Archmage never yields (it skips
        # ai_monster's yield rule). Documented non-lock: the hero is never held there — he either gets out at
        # the top or can always climb back down (no combat either way while he is mid-ladder).
        p.boot(K_KNIGHT)
        p.wb(S["kind_tab"] + S["KT_SEQ"] + KA, p.rb(S["kind_tab"] + S["KT_SEQ"] + K_SKELETON))
        map0 = list(p.z.read_memory(S["ROOM_MAP"], 18 * 32))
        fl = lambda r_, c_: tflags[map0[r_ * 32 + c_]]  # noqa: E731
        shafts = [c_ for c_ in range(2, 29) if fl(8, c_) & (TF["HOLE"] | TF["LADDER"]) and fl(12, c_) & TF["LADDER"]]
        mp0 = {r_: [fl(r_, c_) for c_ in range(32)] for r_ in range(18)}
        lres = None
        for c in shafts:
            spots = [x_ for x_ in range(c - aw - 2, c + hw + 2) if M.arch_sp_try(
                dict(tf=TF, w=aw, h=ah, xmin=S["LP_XMIN"], xmax=S["LP_XMAX"], map=mp0, bodies=[]), x_, 8 - ah)]
            if not spots:
                continue
            ax = spots[0]

            def world(hx):
                ents = {0: ent_of(K_KNIGHT, hx, 17 - hh, EF_ACTIVE | EF_PLAYER, hp=200),
                        5: ent_of(KA, 26, 17 - ah, EF_ACTIVE | EF_HOSTILE | EF_LEFT, hp=67, MAXHP=67, POT=0x3D)}
                put_world(ents, map0)
                for a_ in ("ST_FLAGS", "ST_T1", "ST_T2", "ST_X"):
                    p.wmem(S[a_], [0] * 16)
                p.wb("SPQ_K", 0)
                p.settle(3)
            hx = None
            for cand in (c, c - 1, c - 2, c + 1):           # the hero x that climbs this shaft (control run)
                world(cand)
                p.turn("K", max_ticks=200)
                if p.ent(0)["Y"] < 17 - hh:
                    hx = cand
                    break
            if hx is None:
                continue
            ov = [x_ for x_ in range(hx - aw + 1, hx + hw) if x_ in spots]   # legal AND over his exit box
            ax = ov[0] if ov else spots[0]
            world(hx)
            ys = []
            for i_ in range(12):
                if i_ == 2:                                # mid-ladder now: the Archmage "blinks" beside the top
                    p.set_ent(5, X=ax, Y=8 - ah, PX=8 * ax, PY=8 * (8 - ah))
                p.turn("K", max_ticks=200)
                ys.append(p.ent(0)["Y"])
            top = ys[-1] == 8 - hh
            down = []
            if not top:
                for _ in range(12):
                    p.turn("J", max_ticks=200)
                    down.append(p.ent(0)["Y"])
            lres = dict(shaft=c, hero_x=hx, arch_x=ax, overlap_legal=ov, up=ys, down=down, out_top=top,
                        back_down=bool(down) and down[-1] == 17 - hh)
            break
        print(f"[info] L ladder-top blink box: {lres}", flush=True)
        check("L a blink box overlapping a ladder top's exit box: the hero gets out at the top or climbs back "
              "down (documented non-lock)", lres and (lres["out_top"] or lres["back_down"]), lres)

    print(f"[{'FAIL' if fails else 'PASS'}] archmage: {fails or 'all checks'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
