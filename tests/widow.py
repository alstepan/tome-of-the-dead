#!/usr/bin/env python3
"""WIDOW-SPIT (user 2026-11-05): the Black Widow spits poison (src/ranged6.asm rd_tab row RK_WIDOW,
src/ranged2.asm rk_tab[K_BLACK_WIDOW]; game.md §9 Black Widow row, §6.4.3), on a booted Knight game,
PROTO room A, storey 1 (the tests/ranged.py harness: the real ai_rhook through a stub, then real turns).

  H   hook: a Widow (any body, not golden) fires at gap 5, not 6; an ordinary Spider at gap 3 / counter 0
      never (CF 0, counter kept, RNG untouched); the golden Spider Queen still fires at gap 5, not 6
  P   spit hits on a held hero (eva 0): every hit adds POISON + 6 (fresh 6, 12 -> 18, 24 -> cap 30), dmg
      1d2 - DEF (DEF 0: 1..2, DEF 2: always 1; no golden + 1); Silk Cloak (IMMF_POISON): damage, no poison;
      the golden Queen unchanged (fresh 12, dmg 2..3)
  F   the shot's RS_Q descriptor: spark_fly1 / fly2, no impact frame, FXD_ATTR 0 (the frames' magenta),
      the flight row = the Widow's top row (2-high), SFX / line = the hit line (MSG_M_HIT)
  C   real turns: a Widow walks in from far away, spits only at gap < 6, every 4th turn (4 turns apart),
      walks in (x - 1) on a turn between shots while in range; an ordinary Spider in the same arena never
      spits
Run: ZRCP_PORT=<port> python3 tests/widow.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_SKELETON  # noqa: E402
from proj3 import w16  # noqa: E402
from ranged import T, STRIDE, E_, EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT, LEK_GOLD, T_AIR, T_BRICK, S1  # noqa: E402

KW, KS = S["K_BLACK_WIDOW"], S["K_SPIDER"]


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
        room = p.rb("CUR_ROOM")
        hw, hh = kt[K_KNIGHT]["bw"], kt[K_KNIGHT]["bh"]
        map0 = list(p.z.read_memory(S["ROOM_MAP"] + S1 * 32, 9 * 32))
        check("static: rk_tab[K_BLACK_WIDOW] = RK_WIDOW < RK_GOLD1, rk_tab[K_SPIDER] = RK_SQUEEN (golden only); "
              "the row = range 6, N 3, RWF_WALK | RWF_NOIMP, 1d2 + 0, PHYS + POISON, E 3, spark_fly1; KT_BH 2",
              p.rb(S["rk_tab"] + KW) == S["RK_WIDOW"] < S["RK_GOLD1"] and p.rb(S["rk_tab"] + KS) == S["RK_SQUEEN"]
              and kt[KW]["bh"] == 2 and S["BW_PSN_T"] == 6 and S["BW_SPIT_N"] == 3)

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
            p.wmem(S["ROOM_MAP"] + S1 * 32, rows)

        def ent_of(kind, x, y, flags, hp=30, **kw):
            d = dict(KIND=kind, X=x, Y=y, FLAGS=flags, HP=hp, MAXHP=hp, MODE=0, REACT=0, REACTAT=0, MSG=0,
                     TGT=0, HIT=0, FLT=0, POT=0, GOLD=0)
            d.update(kw)
            return d

        clean = [T_AIR] * (8 * 32)
        for r_ in range(8):
            clean[r_ * 32] = clean[r_ * 32 + 31] = T_BRICK
        clean = clean + map0[8 * 32:]

        def hk(kind, gap, counter=0, slot=3, hdef=0, imm=0, seed=0x1357, hx=2, hhp=200, stf=0, gold=0, stx=None):
            sx = hx + hw + gap
            ents = {0: ent_of(K_KNIGHT, hx, S1 + 8 - hh, EF_ACTIVE | EF_PLAYER, hp=hhp),
                    slot: ent_of(kind, sx, S1 + 8 - kt[kind]["bh"], EF_ACTIVE | EF_HOSTILE, POT=counter ^ 1, GOLD=gold)}
            put_world(ents, list(clean))
            p.wmem(S["ST_FLAGS"], [stf] + [0] * 15)
            p.wmem(S["ST_T1"], [0x30 if stf & 3 else 0] + [0] * 15)
            if stx is not None:
                p.wb(S["ST_X"], stx)
            p.wmem(S["HERO_RES"], [0, 0, 0])
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

        # ----------------------------------------------------------------- H
        we = [shot(hk(KW, g)[1]) for g in (5, 6)]
        qe = [shot(hk(KS, g, gold=LEK_GOLD)[1]) for g in (5, 6)]
        cf, mem, _ = hk(KS, 3, counter=0)
        plain = (cf, shot(mem), (mem[3 * STRIDE + E_["POT"]] & 3) ^ 1, p.rw("RNG_STATE") == 0x1357)
        cf, mem, _ = hk(KW, 3, counter=1)
        walk = (cf, shot(mem), (mem[3 * STRIDE + E_["POT"]] & 3) ^ 1)
        cf, mem, _ = hk(KW, 3, counter=0)
        cnt = (mem[3 * STRIDE + E_["POT"]] & 3) ^ 1
        check("H the Widow fires at gap 5, not 6; the golden Queen at 5, not 6; an ordinary Spider never "
              "(CF 0, counter 0, RNG untouched); Widow counter 1: CF 0 (walks), no shot; a shot sets the counter 3",
              we == [True, False] and qe == [True, False] and plain == (False, False, 0, True)
              and walk == (False, False, 0) and cnt == 3, (we, qe, plain, walk, cnt))

        # ----------------------------------------------------------------- P
        PSN = 1 << S["STS_POISON_BIT"]

        def spit(kind, stx0, imm=0, hdef=0, gold=0, n=60):
            out = []
            for i_ in range(n):
                cf, mem, _ = hk(kind, 4, gold=gold, stf=2 | (PSN if stx0 else 0), stx=stx0, imm=imm, hdef=hdef,
                                seed=0x300 + 41 * i_)
                if shot(mem) and mem[3 * STRIDE + E_["MSG"]] == S["MSG_M_HIT"]:
                    out.append((200 - mem[E_["HP"]], p.rb(S["ST_X"]), bool(p.rb(S["ST_FLAGS"]) & PSN)))
            return out
        fresh, add, capd = spit(KW, 0), spit(KW, 12), spit(KW, 24)
        def2, silk = spit(KW, 0, hdef=2), spit(KW, 0, imm=S["IMMF_POISON"])
        qf = spit(KS, 0, gold=LEK_GOLD)
        check("P Widow spit: every hit POISON + 6 (fresh 6, 12 -> 18, 24 -> cap 30), dmg 1d2 - DEF (DEF 0: 1..2, "
              "DEF 2: 1), Silk Cloak: damage, no poison; golden Queen unchanged (+ 12, 2..3)",
              fresh and add and capd and def2 and silk and qf
              and all(x[1:] == (6, True) for x in fresh) and all(x[1:] == (18, True) for x in add)
              and all(x[1:] == (30, True) for x in capd) and all(x[1:] == (0, False) for x in silk)
              and {x[0] for x in fresh + silk} == {1, 2} and {x[0] for x in def2} == {1}
              and all(x[1:] == (12, True) for x in qf) and {x[0] for x in qf} == {2, 3},
              (fresh[:4], add[:3], capd[:3], def2[:3], silk[:3], qf[:4]))

        # ----------------------------------------------------------------- F
        cf, mem, sx = hk(KW, 4, stf=2, seed=0x0321)
        q = list(p.z.read_memory(S["RS_Q"], S["RS_STRIDE"]))
        d = q[S["RS_D"]:]
        wy = S1 + 8 - kt[KW]["bh"]
        fo = dict(fida=d[S["FXD_FIDA"]], fidb=d[S["FXD_FIDB"]], impa=d[S["FXD_IMPA"]], attr=d[S["FXD_ATTR"]],
                  row=d[S["FXD_ROW"]], col=d[S["FXD_COL"]], left=d[S["FXD_FLAGS"]] & 1, seg=d[S["FXD_SEGS"]])
        check("F the descriptor: spark_fly1 / fly2, no impact frame (NOIMP), FXD_ATTR 0 (fx_meta magenta $43), "
              "flight row = the Widow's top, col = the cell left of it, flies left the gap",
              fo == dict(fida=S["FID_spark_fly1"], fidb=S["FID_spark_fly2"], impa=0xFF, attr=0, row=wy, col=sx - 1,
                         left=1, seg=4) and (p.rb(S["fx_meta"] - S["KFID_FXM"] + S["FID_spark_fly1"]) & 0x7F) == 0x43,
              (fo, wy, sx))

        # ----------------------------------------------------------------- C real turns
        def arena(kind, x, hx=4):
            for k_ in (KW, KS):                          # draw with the Skeleton's sequences (pool-independent)
                p.wb(S["kind_tab"] + S["KT_SEQ"] + k_, p.rb(S["kind_tab"] + S["KT_SEQ"] + K_SKELETON))
            ents = {0: ent_of(K_KNIGHT, hx, S1 + 8 - hh, EF_ACTIVE | EF_PLAYER, hp=200),
                    3: ent_of(kind, x, S1 + 8 - kt[kind]["bh"], EF_ACTIVE | EF_HOSTILE | EF_LEFT, hp=60, POT=0)}
            put_world(ents, map0)
            p.wmem(S["ST_FLAGS"], [0] * 16)
            p.wmem(S["ST_T1"], [0] * 16)
            p.wb(S["ST_X"], 0)
            p.wmem(S["HERO_RES"], [0, 0, 0])
            p.wb("HERO_DEF", 0)
            p.wb("FX_DROP", 0)
            p.wb("TURN_PEND", 0)
            p.settle(3)

        def walk_log(kind, n=16, hx=4):
            arena(kind, 20, hx)
            log = []
            for t_ in range(n):
                p.wb(S["P_ENTITIES"] + 3 * STRIDE + E_["MSG"], 0)
                p.wb(S["P_ENTITIES"] + E_["HP"], 200)
                p.wmem(S["ST_FLAGS"], [0] * 16)
                p.wb(S["ST_X"], 0)
                x0 = p.ent(3)["X"]
                p.turn("WAIT", max_ticks=200)
                log.append((t_ + 1, x0, p.ent(3)["X"], p.rb(S["P_ENTITIES"] + 3 * STRIDE + E_["MSG"]),
                            p.rb(S["FX_DROP"])))
            return log

        p.boot(K_KNIGHT)                                 # the stubs above left the game loop
        glog = walk_log(KW)
        gap0 = {t_: x0 - (4 + hw) for t_, x0, _, _, _ in glog}
        shots_t = [t_ for t_, _, _, m_, _ in glog if m_ in (S["MSG_M_HIT"], S["MSG_M_MISS"]) and gap0[t_] > 1]
        moved_in = [t_ for t_, x0, x1, m_, _ in glog if x1 < x0 and 1 < gap0[t_] < 6 and t_ not in shots_t]
        check("C real turns: the Widow spits only at gap < 6, 4 turns apart (every 4th turn), and walks in "
              "(x - 1) on a turn between shots while in range; FX_DROP 0",
              len(shots_t) >= 2 and all(b - a == 4 for a, b in zip(shots_t, shots_t[1:]))
              and all(gap0[t_] < 6 for t_ in shots_t) and moved_in and not any(x[4] for x in glog), glog)
        slog = walk_log(KS)
        sg = {t_: x0 - (4 + hw) for t_, x0, _, _, _ in slog}
        sshots = [t_ for t_, _, _, m_, _ in slog if m_ in (S["MSG_M_HIT"], S["MSG_M_MISS"]) and sg[t_] > 1]
        check("C an ordinary Spider in the same arena never spits (no hit / miss line at gap > 1)",
              not sshots and any(x1 < x0 for _, x0, x1, _, _ in slog), slog)

    print(f"[{'FAIL' if fails else 'PASS'}] widow: {fails or 'all checks'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
