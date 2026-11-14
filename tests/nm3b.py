#!/usr/bin/env python3
"""NEW-MON3 T10a behaviours (docs/design/new_monsters.md §4.1 G-1 PERCH, §4.2 / §4.4 F-1 flyer shooter, §8 P-1
pit throws) on the real game (DEBUG_KIT=0 build, F3_GEN), Knight, generated D6 (Gargoyle, Fire Imp, Orc) / D7
(Frost Wraith). The current room's air rows are rewritten per case (walls at cols 0 / 31), bodies poked.

  W  wake rules (R6 perch6 / bank-3 afl_perch): the hero standing on the Gargoyle's storey at a box gap 0..2
     (either side) wakes it (RCD_AWAKE, faces him, the waking one-shot = its KS_CLIMB row, "WAKES UP" line);
     gap 3 / 4, the other storey, the hero mid-ladder: stays perched; through ai_monster: a perched far one
     does not move, an awake one flies; any HP loss (deal_hit) wakes it, a missed bump (do_attack, eva 99)
     wakes it; the rest pose (anim_entity): perched = garg_perch, awake = garg_fly
  R  re-perch on room re-entry (stub lp_transition, as do_exit): an awake Gargoyle left behind comes back
     perched (parked slot restored: RCD_SUMMON cleared), hp kept; a perched one is never a follow candidate,
     an awake one is (follow_select), and place_follower keeps it awake
  F  the flyer shot line (ai_flyer's F-1 hook: ai_rhook with H = 0) vs tools/ranged_model.decide (flyer
     rows, rd_x FX): NB_F seeded situations each for the Fire Imp (D6) and the Frost Wraith (D7): band rows,
     range edges, counter 0..3, blocks / bodies, other storey / mid-ladder, FIRE / COLD resists; fixed: an Imp
     at y = 9s never fires (fr = 9s + 1 above the hero), the Wraith at the cruise row fires at gap 5, not 6 (r 6)
  P  pit throws (R6 pit6, entered from ai_monster's refused .fstep): an Orc across a narrow pit throws
     (dagger_spin, $07, counter := 3), not at gap >= r, not while reloading (counter - 1), nothing when the
     refused col is not the pit's; the Goblin once (RCD_SPENT); never golden; the track limit waits with the
     counter untouched; Spider / Skeleton FX; the hero on the other storey: nothing; P0 the real ai_monster
     path (.fstep refused by the pit -> a throw)
Run: ZRCP_PORT=<port> python3 tests/nm3b.py   (NB_F = flyer situations per kind, default 300)
"""
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import levelgen as G                                    # noqa: E402
import room_model                                       # noqa: E402
import ranged_model as M                                # noqa: E402
from game_lib import Harness, S, EMU_ARGS, F3, stand_y  # noqa: E402
from lp import T as LPT, w16                            # noqa: E402

DRV = S["GEN_SRC"] + 0x2C0       # the play-free generator window (exit3e / items_gen): the low-RAM stub room is 43 B
RES = DRV - 1


class Proto(LPT):
    def code(self, body, limit=20000000, game=False):
        """lp.T.code at DRV (the stubs here outgrow LOWRAM_END_3B's 43 B). -> (ok, T)."""
        pre_ = [0xF3] if game else [0xF3, 0x31] + w16(S["WORKSTORE_TOP"])
        code = bytes(pre_ + body + ([0xFB] if game else []) + [0x00, 0x18, 0xFE])
        end = DRV + len(code) - 3
        assert len(code) < 0x200
        self.z.cmd("write-memory %d %s" % (DRV, " ".join(str(b) for b in code)))
        self.z.cmd("set-breakpoint 3 PC=%d" % end)
        self.extra_probes = {end}
        self.z.cmd("set-register PC=%d" % DRV)
        self.z.cmd("reset-tstates-partial")
        self.z.cmd("run %d" % limit)
        ts = int(self.z.cmd("get-tstates-partial"))
        ok = self.pc() == end
        self.z.cmd("set-breakpoint 3")
        self.extra_probes = set()
        return ok, ts

FAILS = []
NCHK = [0]


def check(name, ok, got=None):
    NCHK[0] += 1
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok or got is None else f": got {got}"), flush=True)
    if not ok:
        FAILS.append(name)


STRIDE = S["P_ENT_STRIDE"]
ENT = S["P_ENTITIES"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT, EF_DYING = 1, 2, 4, 8, 16
EF = {k: S["E_" + k] for k in ("KIND", "ROOM", "FLAGS", "X", "Y", "HP", "MAXHP", "POT", "PX", "PY", "MODE",
                               "SEQL", "SEQH", "MSG", "GOLD", "REACT")}
KG, KA, KK = S["K_GARGOYLE"], S["K_ALIAS"], S["K_KNIGHT"]
AWAKE = S["RCD_AWAKE"]
T_AIR, T_BRICK = S["T_AIR"], S["T_BRICK"]
LEK_GOLD = 1 << S["LEK_GOLD_BIT"]
NB_F = int(os.environ.get("NB_F", "300"))


def bank3(inner):
    return ([0x3A] + w16(S["PORT_7FFD_SHADOW"]) + [0xF5, 0x3E, S["BANK_COLD3"], 0xCD] + w16(S["page_bank"])
            + inner + [0xF1, 0xCD] + w16(S["restore_page"]))


def ingame(p, code):
    pc0 = p.pc()
    ok, ts = p.code(code, game=True)
    p.z.cmd("set-register PC=%d" % pc0)
    assert ok, "stub did not return"
    return ts


def descend_to(p, d):
    p.wb("MUS_CUR", 0)
    ingame(p, [0x3E, d - 1, 0x32] + w16(S["LVL_DEPTH"]) + [0xCD] + w16(S["level_descend"]))
    p.release()
    p.settle(4)
    return p.rb("LVL_DEPTH") == d and p.rb("GAME_STATE") == S["GS_PLAYING"]


class World:
    def __init__(self, p):
        self.p = p
        self.room = p.rb("CUR_ROOM")
        g = lambda f, k: p.rb(S["kind_tab"] + S[f] + k)  # noqa: E731
        self.kt = {k: dict(bw=g("KT_BW", k), bh=g("KT_BH", k), atk=g("KT_ATK", k), eva=g("KT_EVA", k),
                           fl=g("KT_FLAGS", k)) for k in range(S["K_COUNT"])}
        self.hw, self.hh = self.kt[KK]["bw"], self.kt[KK]["bh"]
        self.map0 = list(p.z.read_memory(S["ROOM_MAP"], 18 * 32))
        self.tflags = list(p.z.read_memory(S["tile_flags"], 64))
        self.desc = S["ROOM_DESC"] + self.room * S["RD_STRIDE"]
        self.pit0 = (p.rb(self.desc + S["RD_PITCOL"]), p.rb(self.desc + S["L2_PITW"]))

    def rows(self, bricks=()):
        """ROOM_MAP rows 0..17: air rows with walls at 0 / 31 (the floor rows 8 / 17 kept); bricks (row, col)."""
        m = list(self.map0)
        for r in list(range(0, 8)) + list(range(9, 17)):
            for c in range(32):
                m[r * 32 + c] = T_BRICK if c in (0, 31) else T_AIR
        for r, c in bricks:
            m[r * 32 + c] = T_BRICK
        self.p.wmem(S["ROOM_MAP"], m)
        return m

    def clear(self):
        p = self.p
        mem = bytearray(p.z.read_memory(ENT, 16 * STRIDE))
        for s_ in range(1, 16):
            mem[s_ * STRIDE + EF["FLAGS"]] = 0
            mem[s_ * STRIDE + EF["ROOM"]] = 0
        p.wmem(ENT, list(mem))
        p.wmem(S["ST_FLAGS"], [0] * 16)
        p.wmem(S["ST_T1"], [0] * 16)
        p.wmem(S["ST_T2"], [0] * 16)
        p.wmem(S["ST_X"], [0] * 16)
        p.wb("TURN_PEND", 0)
        p.wb("TURN_TICK", 0)
        p.wb("COMBAT_NOT_BEFORE", 0)
        p.wb("FX_DROP", 0)
        p.wb("SPQ_K", 0)
        p.wb("dh_rtick", 0)

    def put(self, slot, kind, x, y, flags=EF_ACTIVE | EF_HOSTILE, hp=20, rcd=1, gold=0, room=None):
        mem = [0] * STRIDE
        mem[EF["KIND"]], mem[EF["ROOM"]], mem[EF["FLAGS"]] = kind, self.room if room is None else room, flags
        mem[EF["X"]], mem[EF["Y"]], mem[EF["HP"]], mem[EF["MAXHP"]] = x, y, hp, hp
        mem[EF["POT"]], mem[EF["PX"]], mem[EF["PY"]], mem[EF["GOLD"]] = rcd, x * 8, y * 8, gold
        self.p.wmem(ENT + slot * STRIDE, mem)

    def hero(self, x, s_=1, dy=0, hp=200):
        self.put(0, KK, x, stand_y(s_, self.hh) - dy, flags=EF_ACTIVE | EF_PLAYER, hp=hp, rcd=0)

    def e(self, slot, f):
        return self.p.rb(ENT + slot * STRIDE + EF[f])


def pre(slot, seg=False):
    """build_live, cache_player (+ pl_seg3: bank 3, only inside bank3()), ACT_SLOT = slot, IX = the slot."""
    return ([0xCD] + w16(S["build_live"]) + [0xCD] + w16(S["cache_player"]) +
            ([0xCD] + w16(S["pl_seg3"]) if seg else []) +
            [0x3E, slot, 0x32] + w16(S["ACT_SLOT"]) + [0xDD, 0x21] + w16(ENT + slot * STRIDE))


def far6(target):
    return [0x21] + w16(S[target]) + [0xCD] + w16(S["far6"])


def seq_ptr(p, kind, ks):
    lo = p.rb(S["kind_tab"] + S["KT_SEQ"] + kind)
    a = (S["seq_rows"] & 0xFF00) | lo
    return p.rb(a + ks) | p.rb(a + ks + 1) << 8


# ------------------------------------------------------------------------------------------------- W
def part_w(p, w):
    s1 = 9
    gy = s1 + 1                                          # the cruise row 9s + 1 (sp_y)
    gw = w.kt[KG]["bw"]
    wake_ptr = seq_ptr(p, KG, S["KS_CLIMB"])
    for side in ("R", "L"):
        for gap in range(0, 5):
            w.clear()
            w.rows()
            if side == "R":                              # the Gargoyle right of the hero
                hx = 6
                gx = hx + w.hw + gap
            else:
                gx = 6
                hx = gx + gw + gap
            w.hero(hx)
            w.put(3, KG, gx, gy)
            ingame(p, pre(3) + far6("perch6"))
            awake = bool(w.e(3, "POT") & AWAKE)
            want = gap <= S["PERCH_GAP"]
            tag = f"W gap {gap} hero {'left' if side == 'R' else 'right'}"
            check(f"{tag}: awake {want}", awake == want, (awake, w.e(3, "POT")))
            if want:
                seq = w.e(3, "SEQL") | w.e(3, "SEQH") << 8
                check(f"{tag}: the waking one-shot (KS_CLIMB row, M_SEQ), faces the hero, x / y kept",
                      w.e(3, "MODE") == S["M_SEQ"] and seq == wake_ptr
                      and bool(w.e(3, "FLAGS") & EF_LEFT) == (side == "R") and (w.e(3, "X"), w.e(3, "Y")) == (gx, gy),
                      (w.e(3, "MODE"), hex(seq), hex(wake_ptr), w.e(3, "FLAGS")))
            else:
                check(f"{tag}: perched, the rest pose (M_REST)", w.e(3, "MODE") == 0, w.e(3, "MODE"))
    # the other storey / mid-ladder
    for tag, s_, dy in (("the hero on storey 0", 0, 0), ("the hero mid-ladder", 1, 1)):
        w.clear()
        w.rows()
        w.hero(6, s_, dy)
        w.put(3, KG, 6 + w.hw, gy)
        ingame(p, pre(3) + far6("perch6"))
        check(f"W gap 0, {tag}: stays perched", not w.e(3, "POT") & AWAKE and w.e(3, "MODE") == 0, w.e(3, "POT"))
    # through ai_monster (bank 3): a perched far one waits (no move, no RNG), an awake one flies at him
    for awake in (0, 1):
        w.clear()
        w.rows()
        w.hero(4)
        w.put(3, KG, 20, gy, rcd=1 | (AWAKE if awake else 0))
        rng0 = p.rw("RNG_STATE")
        ingame(p, bank3(pre(3, True) + [0xCD] + w16(S["ai_monster"])))
        moved = w.e(3, "MODE") == S["M_MOVE"]
        check(f"W ai_monster, {'awake' if awake else 'perched'} gap 13: {'flies' if awake else 'waits'}",
              moved == bool(awake) and (awake or (w.e(3, "X"), p.rw("RNG_STATE")) == (20, rng0)),
              (w.e(3, "MODE"), w.e(3, "X")))
    # ... and a perched near one wakes there (ai_monster -> afl_perch -> perch6)
    w.clear()
    w.rows()
    w.hero(6)
    w.put(3, KG, 6 + w.hw + 2, gy)
    ingame(p, bank3(pre(3, True) + [0xCD] + w16(S["ai_monster"])))
    check("W ai_monster, perched gap 2: wakes (the turn spent: no move)",
          w.e(3, "POT") & AWAKE and w.e(3, "MODE") == S["M_SEQ"] and w.e(3, "X") == 6 + w.hw + 2, w.e(3, "POT"))
    # damage wakes (deal_hit, any HP loss), silently
    w.clear()
    w.rows()
    w.hero(6)
    w.put(3, KG, 20, gy, hp=30)
    ingame(p, bank3([0xDD, 0x21] + w16(ENT) + [0x3E, 3, 0x06, 4, 0x0E, 0, 0x1E, 0, 0xCD] + w16(S["deal_hit"])))
    check("W deal_hit 4 PHYS on a perched Gargoyle: HP lost, awake",
          w.e(3, "HP") < 30 and w.e(3, "POT") & AWAKE, (w.e(3, "HP"), w.e(3, "POT")))
    # a missed bump wakes (eva 99: every d20 misses)
    w.clear()
    w.rows()
    w.hero(6)
    w.put(3, KG, 6 + w.hw, gy, hp=30)
    eva = S["kind_tab"] + S["KT_EVA"] + KG
    e0 = p.rb(eva)
    p.wb(eva, 99)
    ingame(p, bank3(pre(0) + [0xDD, 0x21] + w16(ENT) + [0x3E, 3, 0xCD] + w16(S["do_attack"])))
    p.wb(eva, e0)
    check("W a missed bump (do_attack, eva 99): HP kept, awake", w.e(3, "HP") == 30 and w.e(3, "POT") & AWAKE,
          (w.e(3, "HP"), w.e(3, "POT")))
    # the rest pose
    for awake, fid in ((0, "FID_garg_perch"), (1, "FID_garg_fly")):
        w.clear()
        w.put(3, KG, 20, gy, rcd=1 | (AWAKE if awake else 0))
        p.wb("ANIM_FREEZE", 1)
        ingame(p, [0xDD, 0x21] + w16(ENT + 3 * STRIDE) + [0x3E, 3, 0x32] + w16(S["ANIM_SLOT"]) +
               [0xCD] + w16(S["anim_entity"]) + [0x32] + w16(RES))
        check(f"W rest pose {'awake' if awake else 'perched'} = {fid[4:]}", p.rb(RES) == S[fid], p.rb(RES))


# ------------------------------------------------------------------------------------------------- R
def part_r(p, w):
    blk = bytes(p.z.read_memory(G.BASE, G.BLOCK_LEN))
    blk_rooms = [r for r in range(9) if r != w.room and room_model.field(blk, r, "RD_FLAGS") & S["RDF_PRESENT"]
                 and r not in (p.rb("LVL_LAIR"), p.rb("LVL_SANCTUM"))]
    X, Y = w.room, blk_rooms[0]
    gy = 10
    PARK = S["LPK_PARK"]

    def xfer(dst, hx=1, hs=1):
        src = p.rb("CUR_ROOM")
        p.set_ent(0, X=hx, Y=stand_y(hs, w.hh))
        p.wmem(S["CAND_LIST"], [0xFF] * 16)
        p.wb("FOLLOW_N", 0)
        p.wb("EXIT_DEST", dst)
        ingame(p, [0x21] + w16(S["lp_transition"]) + [0xCD] + w16(S["far3"]))
        p.wb("TRK_PREV", src)
        p.wb("CUR_ROOM", dst)
        p.set_ent(0, ROOM=dst)

    w.clear()
    w.hero(1)
    w.put(5, KG, 20, gy, hp=11, rcd=1 | AWAKE)
    w.p.wmem(S["P_ENTITIES"] + 5 * STRIDE + EF["MAXHP"], [14])
    xfer(Y)
    check(f"R1 leave room {X} -> {Y}: the awake Gargoyle parked (E_ROOM = X | LPK_PARK)",
          w.e(5, "ROOM") == X | PARK and w.e(5, "KIND") == KG, (w.e(5, "ROOM"), w.e(5, "KIND")))
    xfer(X, hx=1)
    g = [s_ for s_ in range(1, 16) if w.e(s_, "FLAGS") & EF_ACTIVE and w.e(s_, "ROOM") == X and w.e(s_, "KIND") == KG]
    check(f"R2 back in room {X}: the Gargoyle restored PERCHED (RCD_AWAKE clear), hp 11 kept",
          g and not w.e(g[0], "POT") & AWAKE and w.e(g[0], "HP") == 11,
          [(s_, w.e(s_, "POT"), w.e(s_, "HP")) for s_ in g])
    # follow candidates: a perched one never, an awake one yes; place_follower keeps it awake
    w.room = p.rb("CUR_ROOM")
    for awake in (0, 1):
        w.clear()
        w.rows()
        w.hero(1)
        w.put(3, KG, 1 + w.hw, gy, rcd=1 | (AWAKE if awake else 0))
        p.wb("EXIT_KIND", S["EX_LEFT"])
        p.wb("EXIT_STOREY", 1)
        p.wmem(S["CAND_LIST"], [0xFF] * 16)
        ingame(p, pre(3) + [0x21] + w16(S["follow_select"]) + [0xCD] + w16(S["far7"]))
        cand = p.rb(S["CAND_LIST"] + 3)
        check(f"R3 follow_select, {'awake' if awake else 'perched'} Gargoyle at gap 0: candidate {bool(awake)}",
              (cand == 3) == bool(awake), cand)
    p.wb("EXIT_DEST", Y)
    ingame(p, bank3([0xDD, 0x21] + w16(ENT + 3 * STRIDE) + [0xCD] + w16(S["place_follower"])))
    check("R4 place_follower: an awake Gargoyle stays awake", w.e(3, "POT") & AWAKE, w.e(3, "POT"))
    p.wb("EXIT_KIND", 0)


# ------------------------------------------------------------------------------------------------- F
def part_f(p, w, depth):
    row = list(M.alias_row(depth))
    fxn = row[7]
    row[7] = S["FID_" + fxn]
    xa, one, ximp = M.FLYER_X[fxn]
    xs = (xa, one, S["FID_" + ximp])
    name = "Wraith" if depth in M.NM3_B_DEPTHS else "Imp"
    k = w.kt[KA]
    fw, fh = k["bw"], k["bh"]
    s1 = 9
    rnd = random.Random(0xF1 + depth)
    bad, stats = [], dict(shot=0, no=0, walk=0)
    for n in range(NB_F):
        sy = rnd.randint(s1, s1 + 8 - fh)
        u = rnd.random()
        if u < 0.85:
            hy, hst, hlad = stand_y(1, w.hh), 1, 0
        elif u < 0.93:
            hy, hst, hlad = stand_y(0, w.hh), 0, 0
        else:
            hy, hst, hlad = stand_y(1, w.hh) - 1, 1, 1
        gap = rnd.choice([rnd.randint(0, 12), row[0] - 1, row[0], rnd.randint(1, 3)])
        if rnd.random() < 0.5:
            sx = rnd.randint(1, 30)
            hx = sx + fw + gap
        else:
            hx = rnd.randint(1, 30)
            sx = hx + w.hw + gap
        if not (1 <= sx and sx + fw - 1 <= 30 and 1 <= hx and hx + w.hw - 1 <= 30):
            continue
        fr = sy + fh - 1
        bricks = []
        if rnd.random() < 0.2:
            bricks = [(fr, rnd.randint(1, 30))]
        counter = rnd.randint(0, 3) if rnd.random() < 0.6 else 0
        res = [0, 0, 0]
        v = rnd.random()
        if v < 0.2:
            res[0] = 1 << 4                              # COLD R (the Frost Charm)
        elif v < 0.35:
            res[0] = 1 << 2                              # FIRE R (Ring of Fire Ward)
        elif v < 0.4:
            res[0] = 2 << 4                              # COLD I
        w.clear()
        m = w.rows(bricks)
        w.put(0, KK, hx, hy, flags=EF_ACTIVE | EF_PLAYER, hp=200, rcd=0)
        w.put(3, KA, sx, sy, rcd=counter ^ 1)
        bodies = [(0, hx, hy, w.hw, w.hh, False)]
        if rnd.random() < 0.15:                          # a Rat in the gap (box_free: my rows)
            rw_, rh_ = w.kt[S["K_RAT"]]["bw"], w.kt[S["K_RAT"]]["bh"]
            bx = rnd.randint(1, 31 - rw_)
            by = stand_y(1, rh_)
            if not any(bx <= x_ + bw_ - 1 and x_ <= bx + rw_ - 1 and by <= y_ + bh_ - 1 and y_ <= by + rh_ - 1
                       for _, x_, y_, bw_, bh_, _d in bodies + [(3, sx, sy, fw, fh, False)]):
                w.put(6, S["K_RAT"], bx, by)
                bodies.append((6, bx, by, rw_, rh_, False))
        p.wmem(S["HERO_RES"], res)
        p.wb("HERO_IMM", 0)
        p.wb("HERO_DEF", 0)
        seed = rnd.randint(1, 0xFFFF)
        p.wmem(S["RNG_STATE"], w16(seed))
        mp = {r_: [w.tflags[m[r_ * 32 + c]] for c in range(32)] for r_ in range(18)}
        sit = dict(kind=KA, row=row, slot=3, x=sx, y=sy, w=fw, h=fh, left=False, standing=True, storey=1,
                   counter=counter, atk=k["atk"], gold=False, turn_tick=0, map=mp, bodies=bodies, flyer=True,
                   hero=dict(x=hx, y=hy, w=w.hw, h=w.hh, storey=hst, ladder=hlad, hp=200, eva=w.kt[KK]["eva"],
                             held=False, res=res, imm=0, stf=0, st1=0, stx=0, react=0))
        sit["xfx"] = xs
        sit["hero"]["def"] = 0
        rng = M.Rng(seed)
        want = M.decide(sit, rng)
        ingame(p, bank3(pre(3) + [0xCD] + w16(S["storey_ref"]) + [0x32] + w16(S["TMP4"]) + [0x26, 0x00, 0xCD]
                        + w16(S["ai_rhook"]) + [0x9F, 0x32] + w16(RES)))
        got = dict(cf=p.rb(RES) != 0, counter=(w.e(3, "POT") & 3) ^ 1, hp=w.e(0, "HP"), rng=p.rw("RNG_STATE"),
                   tp=bool(p.rb("TURN_PEND") & S["TP_SHOT"]))
        exp = dict(cf=want["used"], counter=want["counter"], hp=200, rng=rng.st, tp=want["shot"] is not None)
        if want["shot"]:
            sh = want["shot"]
            exp["hp"] = sh["hero"].get("hp", 200)
            exp["q"] = [sh["R"], sh["flash"]] + sh["desc"]
            got["q"] = list(p.z.read_memory(S["RS_Q"], S["RS_STRIDE"]))
            stats["shot"] += 1
        elif want["counter"] != counter and counter:
            stats["walk"] += 1
        else:
            stats["no"] += 1
        if got != exp:
            bad.append(dict(n=n, sx=sx, sy=sy, hx=hx, hy=hy, gap=gap, ctr=counter,
                            diff={k_: (got.get(k_), exp.get(k_)) for k_ in exp if got.get(k_) != exp.get(k_)}))
    print(f"[info] F {name} D{depth}: {stats}", flush=True)
    check(f"F {name} D{depth}: {NB_F} seeded flyer situations, Z80 F-1 hook == ranged_model ({len(bad)} bad)",
          not bad and stats["shot"] > 10, bad[:3])

    def one(sy, gap, counter=0):
        w.clear()
        w.rows()
        hx = 4
        w.hero(hx)
        w.put(3, KA, hx + w.hw + gap, sy, rcd=counter ^ 1)
        p.wmem(S["HERO_RES"], [0, 0, 0])
        ingame(p, bank3(pre(3) + [0xCD] + w16(S["storey_ref"]) + [0x32] + w16(S["TMP4"]) + [0x26, 0x00, 0xCD]
                        + w16(S["ai_rhook"]) + [0x9F, 0x32] + w16(RES)))
        return p.rb(RES) != 0, bool(p.rb("TURN_PEND") & S["TP_SHOT"]), list(p.z.read_memory(S["RS_Q"], S["RS_STRIDE"]))

    if name == "Imp":
        cf, tp, _ = one(s1, 3)
        check("F Imp at y = 9s (fr = 9s + 1 above the hero's rows): not in line, no shot", not cf and not tp)
        cf, tp, q = one(s1 + 1, 5)
        check("F Imp at the cruise row, gap 5 (< r 6): fires; FX spark_fly1/2, impact spark_fizz1, $42, row 9s + 2",
              cf and tp and q[2:7] == [S["FID_spark_fly1"], S["FID_spark_fly2"], S["FID_spark_fizz1"],
                                       S["FID_spark_fizz1"], 0x42] and q[8] == s1 + 2, q)
        cf, tp, _ = one(s1 + 1, 6)
        check("F Imp gap 6 (= r): no shot", not tp)
    else:
        cf, tp, q = one(s1 + 1, 5)
        check("F Wraith at the cruise row, gap 5 (< r 6): fires; FX frost_fly x2, impact frost_crack, $45, row 9s + 4",
              cf and tp and q[2:7] == [S["FID_frost_fly"], S["FID_frost_fly"], S["FID_frost_crack"],
                                       S["FID_frost_crack"], 0x45] and q[8] == s1 + 4, q)
        cf, tp, _ = one(s1 + 1, 6)
        check("F Wraith gap 6 (= r): no shot", not tp)


# ------------------------------------------------------------------------------------------------- P
def part_p(p, w):
    PIT = 14
    hh = w.hh

    def setpit(col):
        p.wb(w.desc + S["RD_PITCOL"], col)
        p.wb(w.desc + S["L2_PITW"], 0)               # the narrow 3-col pit: fall range x == p

    def throw(kind, gap, counter=0, rcd_hi=0, gold=0, pit=PIT, hs=0, pend=False, via_ai=False):
        w.clear()
        w.rows()
        setpit(pit)
        kw_, kh_ = w.kt[kind]["bw"], w.kt[kind]["bh"]
        mx = PIT + 1                                  # the refused step x - 1 = p
        hx = mx - gap - w.hw
        w.hero(hx, hs)
        w.put(3, kind, mx, stand_y(0, kh_), rcd=(counter ^ 1) | rcd_hi, gold=gold)
        p.wmem(S["HERO_RES"], [0, 0, 0])
        p.wb("HERO_DEF", 0)
        p.wmem(S["RNG_STATE"], w16(0x2345))
        if pend:
            p.wb("TURN_PEND", S["TP_SHOT"])
            p.wb("RS_P", (S["RS_Q"] + 3 * S["RS_STRIDE"]) & 255)
        if via_ai:
            p.wb("ROOM_CUT", 0xFF)
            ingame(p, bank3(pre(3, True) + [0xCD] + w16(S["ai_monster"])))
        else:
            ingame(p, pre(3) + far6("pit6"))
        rcd = w.e(3, "POT")
        shot = bool(p.rb("TURN_PEND") & S["TP_SHOT"]) and not pend
        q = list(p.z.read_memory(S["RS_Q"], S["RS_STRIDE"]))
        return shot, (rcd & 3) ^ 1, rcd, q

    KO, KGB, KSP, KSK = S["K_ORC"], S["K_GOBLIN"], S["K_SPIDER"], S["K_SKELETON"]
    shot, c, _, q = throw(KO, 3)
    check("P1 Orc across the pit, gap 3 < r 5, counter 0: throws (dagger_spin, $07, row top + 2), counter := 3",
          shot and c == 3 and q[2] == S["FID_dagger_spin1"] and q[3] == S["FID_dagger_spin2"] and q[6] == 0x07
          and q[8] == stand_y(0, w.kt[KO]["bh"]) + 2, (shot, c, q))
    shot, c, _, _ = throw(KO, 5)
    check("P2 Orc gap 5 (= r): no throw, counter 0 stays 0", not shot and c == 0, (shot, c))
    shot, c, _, _ = throw(KO, 3, counter=2)
    check("P3 Orc reloading (counter 2): no throw, counter 1", not shot and c == 1, (shot, c))
    shot, c, _, _ = throw(KO, 3, counter=2, pit=5)
    check("P4 the refused col is not the pit's: nothing (counter untouched)", not shot and c == 2, (shot, c))
    shot, c, rcd, _ = throw(KGB, 3)
    check("P5 Goblin: throws once, RCD_SPENT set", shot and rcd & AWAKE, (shot, rcd))
    shot, c, rcd, _ = throw(KGB, 3, rcd_hi=AWAKE)
    check("P5 Goblin with its dagger spent: no throw (counter untouched)", not shot and c == 0, (shot, c))
    shot, c, _, _ = throw(KGB, 3, gold=LEK_GOLD)
    check("P6 a golden Goblin (the lair boss) never throws", not shot and c == 0, (shot, c))
    shot, c, _, _ = throw(KO, 3, counter=2, pend=True)
    check("P7 3 shots queued this phase (track limit): waits, counter untouched", c == 2
          and p.rb("RS_P") == (S["RS_Q"] + 3 * S["RS_STRIDE"]) & 255, (c, p.rb("RS_P")))
    shot, c, _, q = throw(KSP, 2)
    check("P8 Spider gap 2 < r 4: spits (spark_fly1, own ink 0)", shot and q[2] == S["FID_spark_fly1"] and q[6] == 0,
          (shot, q))
    shot, c, _, q = throw(KSK, 4)
    check("P9 Skeleton gap 4 < r 5: a bone (dagger_spin, $47)", shot and q[2] == S["FID_dagger_spin1"] and q[6] == 0x47,
          (shot, q))
    shot, c, _, _ = throw(KO, 3, hs=1)
    check("P10 the hero on storey 1: nothing", not shot, shot)
    shot, c, _, q = throw(KO, 3, via_ai=True)
    check("P0 ai_monster: the .fstep refused by the pit -> pit6 throws", shot and q[2] == S["FID_dagger_spin1"], (shot, q))
    p.wb(w.desc + S["RD_PITCOL"], w.pit0[0])
    p.wb(w.desc + S["L2_PITW"], w.pit0[1])


def main():
    if not F3:
        print("[skip] nm3b needs the F3_GEN build", flush=True)
        return 0
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = Proto(h)
        p.proto_start = 0
        p.boot(hero=0, freeze=1)
        p.wmem(S["MASTER_SEED"], w16(0x4D31))
        check("setup: level_descend -> D6", descend_to(p, 6))
        w = World(p)
        part_w(p, w)
        part_p(p, w)
        part_f(p, w, 6)
        part_r(p, w)
        check("setup: level_descend -> D7", descend_to(p, 7))
        w = World(p)
        part_f(p, w, 7)
    print(f"nm3b: {NCHK[0]} checks, {len(FAILS)} failed" + (f": {FAILS[:8]}" if FAILS else ""), flush=True)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
