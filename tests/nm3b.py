#!/usr/bin/env python3
"""NEW-MON3 T10a behaviours (docs/design/new_monsters.md §4.1 G-1 PERCH, §4.2 / §4.4 F-1 flyer shooter, §8 P-1
pit throws) on the real game (DEBUG_KIT=0 build, F3_GEN), Knight, generated D6 (Gargoyle, Fire Imp, Orc) / D7
(Frost Wraith). The current room's air rows are rewritten per case (walls at cols 0 / 31), bodies poked.

  W  wake rules (bank-1 perch1 / bank-3 afl_perch; GARG-PASS 2026-11-18: a perched Gargoyle = EF_GHOST, intangible):
     the hero standing on the Gargoyle's storey at a box gap 0..2 (either side) wakes it (EF_GHOST off, RCD_AWAKE,
     faces him, the waking one-shot = its KS_CLIMB row, "WAKES UP" line);
     gap 3 / 4, the other storey, the hero mid-ladder: stays perched; through ai_monster: a perched far one
     does not move, an awake one flies; a SOLID not-yet-awake one (a door arrival): any HP loss (deal_hit), a missed
     bump (do_attack, eva 99), a POISON tick wake it; an EF_WALKIN (ALARM wave) body walks in solid (materialise
     clears bit 5) and perch1 sets it awake on its first turn (rule 4); the rest pose (anim_entity): ghost =
     garg_perch, awake / solid = the fly cycle (GARG-FLY 2026-11-16: garg_fly 4 / garg_fly2 4
     on TICK_COUNTER while hovering; the attack = windup, a hit = garg_hurt then the cycle again, death = hurt then
     garg_dead; re-perched (EF_GHOST) = the statue again)
  G  GARG-PASS (user 2026-11-18): a monster (try_step) and the hero (try_horizontal) walk through a ghost (a solid
     one blocks / is bumped); the hero's find_target ignores it; the wake is delayed while the hero or a monster
     overlaps its box and happens on the first turn the box is clear; a dagger (proj_fire) flies through it and
     hits the body behind (a solid one is the target); arrival_conflicts leaves it alone; G6 try_close's
     room_bodies: a ghost is no hostile near the door but still fills the door cells; G3p a PENDING body
     on the statue's box delays the wake too
  R  re-perch on room re-entry (stub lp_transition, as do_exit): an awake Gargoyle left behind comes back
     perched (parked slot restored: RCD_SUMMON cleared), hp kept; a perched one is never a follow candidate,
     an awake one is (follow_select), and place_follower keeps it awake
  F  the flyer shot line (ai_flyer's F-1 hook: ai_rhook with H = 0) vs tools/ranged_model.decide (flyer
     rows, rd_x FX): NB_F seeded situations each for the Fire Imp (D6) and the Frost Wraith (D7): band rows,
     range edges, counter 0..3, blocks / bodies, other storey / mid-ladder, FIRE / COLD resists; fixed: an Imp
     at y = 9s never fires (fr = 9s + 1 above the hero), the Wraith at the cruise row fires at gap 7, not 8 (r 8)
  P  pit throws (R6 pit6, entered from ai_monster's refused .fstep): an Orc across a narrow pit throws
     (dagger_spin, $07, counter := 3), not at gap >= r, not while reloading (counter - 1), nothing when the
     refused col is not the pit's; the Goblin once (RCD_SPENT); never golden; the track limit waits with the
     counter untouched; Spider / Skeleton FX; the hero on the other storey: nothing; P0 the real ai_monster
     path (.fstep refused by the pit -> a throw)
  D  (T10b, user 2026-11-14) one Goblin dagger per LIFE: thrown (RCD_SPENT = RCD_ONCE), the hero leaves and comes
     back (parked slot restored; then via 3 other rooms: banked as LEK_BRED, lp_spawn restores it): the bit is kept
     and pit6 throws nothing; a Gargoyle in the same trip still re-perches (bit 2 cleared)
  C  (T10a follow-up) the Warrior's innate COLD R: HERO_RES with / without the Frost Charm, deal_hit COLD halves
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
EF_PENDING = S["EF_PENDING"]
GH = S["EF_GHOST"]
PERCHED = EF_ACTIVE | EF_HOSTILE | GH                   # GARG-PASS: a resident perched Gargoyle (spawn_one)
EF = {k: S["E_" + k] for k in ("KIND", "ROOM", "FLAGS", "X", "Y", "HP", "MAXHP", "POT", "PX", "PY", "MODE",
                               "SEQL", "SEQH", "MSG", "GOLD", "REACT", "REACTAT", "TMR")}
KG, KA, KK = S["K_GARGOYLE"], S["K_ALIAS"], S["K_KNIGHT"]
AWAKE = S["RCD_AWAKE"]
SPENT = 1 << S["RCD_SPENT_BIT"]
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


def far1(target):
    return [0x21] + w16(S[target]) + [0xCD] + w16(S["far1"])


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
            w.put(3, KG, gx, gy, flags=PERCHED)
            ingame(p, pre(3) + far1("perch1"))
            awake = bool(w.e(3, "POT") & AWAKE)
            want = gap <= S["PERCH_GAP"]
            tag = f"W gap {gap} hero {'left' if side == 'R' else 'right'}"
            check(f"{tag}: awake {want}, EF_GHOST {not want}", awake == want and bool(w.e(3, "FLAGS") & GH) != want,
                  (awake, w.e(3, "POT"), w.e(3, "FLAGS")))
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
        w.put(3, KG, 6 + w.hw, gy, flags=PERCHED)
        ingame(p, pre(3) + far1("perch1"))
        check(f"W gap 0, {tag}: stays perched", not w.e(3, "POT") & AWAKE and w.e(3, "MODE") == 0
              and w.e(3, "FLAGS") & GH, (w.e(3, "POT"), w.e(3, "FLAGS")))
    # through ai_monster (bank 3): a perched far one waits (no move, no RNG), an awake one flies at him
    for awake in (0, 1):
        w.clear()
        w.rows()
        w.hero(4)
        w.put(3, KG, 20, gy, rcd=1 | (AWAKE if awake else 0), flags=EF_ACTIVE | EF_HOSTILE if awake else PERCHED)
        rng0 = p.rw("RNG_STATE")
        ingame(p, bank3(pre(3, True) + [0xCD] + w16(S["ai_monster"])))
        moved = w.e(3, "MODE") == S["M_MOVE"]
        check(f"W ai_monster, {'awake' if awake else 'perched'} gap 13: {'flies' if awake else 'waits'}",
              moved == bool(awake) and (awake or (w.e(3, "X"), p.rw("RNG_STATE")) == (20, rng0)),
              (w.e(3, "MODE"), w.e(3, "X")))
    # ... and a perched near one wakes there (ai_monster -> afl_perch -> perch1)
    w.clear()
    w.rows()
    w.hero(6)
    w.put(3, KG, 6 + w.hw + 2, gy, flags=PERCHED)
    ingame(p, bank3(pre(3, True) + [0xCD] + w16(S["ai_monster"])))
    check("W ai_monster, perched gap 2: wakes (the turn spent: no move)",
          w.e(3, "POT") & AWAKE and w.e(3, "MODE") == S["M_SEQ"] and w.e(3, "X") == 6 + w.hw + 2, w.e(3, "POT"))
    # damage wakes (deal_hit, any HP loss), silently
    w.clear()
    w.rows()
    w.hero(6)
    w.put(3, KG, 20, gy, hp=30)
    ingame(p, bank3([0xDD, 0x21] + w16(ENT) + [0x3E, 3, 0x06, 4, 0x0E, 0, 0x1E, 0, 0xCD] + w16(S["deal_hit"])))
    check("W deal_hit 4 PHYS on a solid not-yet-awake Gargoyle (a door arrival): HP lost, awake",
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
    check("W a missed bump on a solid not-yet-awake Gargoyle (do_attack, eva 99): HP kept, awake", w.e(3, "HP") == 30 and w.e(3, "POT") & AWAKE,
          (w.e(3, "HP"), w.e(3, "POT")))
    # T10a review: a POISON tick (st_step, mon_status far7) is an HP loss: it wakes a perched Gargoyle (defensive)
    w.clear()
    w.rows()
    w.hero(4)
    w.put(3, KG, 20, gy, hp=30)
    p.wb(S["ST_FLAGS"] + 3, 1 << S["STS_POISON_BIT"])
    p.wb(S["ST_X"] + 3, 5)                               # 5 -> 4: a multiple of 4 costs 1 HP
    ingame(p, bank3(pre(3) + [0x3E, 3, 0x21] + w16(S["mon_status"]) + [0xCD] + w16(S["far7"])))
    check("W a POISON tick on a solid not-yet-awake Gargoyle: HP - 1, awake", w.e(3, "HP") == 29 and w.e(3, "POT") & AWAKE,
          (w.e(3, "HP"), w.e(3, "POT")))
    kxi = GI_bank3(p, S["kx_tab"] + KG * S["KX_STRIDE"] + S["KX_IMM"])
    check("W (and its kx row is POISON-immune: no monster source poisons it)", kxi & S["IMMF_POISON"], kxi)
    # an ALARM-wave Gargoyle walks in SOLID (materialise clears PENDING | WALKIN = bit 5 = EF_GHOST, rule 4) and
    # perch1 sets it awake on its first turn (no statue at the door)
    w.clear()
    w.rows()
    w.hero(14)
    w.put(4, KG, 1, gy, flags=EF_ACTIVE | EF_HOSTILE | S["EF_PENDING"] | S["EF_WALKIN"])
    ingame(p, bank3([0xCD] + w16(S["build_live"]) + [0xCD] + w16(S["materialise"])))
    check("W an EF_WALKIN wave Gargoyle materialises and walks in (M_MOVE from px 0) solid (no EF_GHOST), not awake yet",
          not w.e(4, "FLAGS") & (S["EF_PENDING"] | GH) and w.e(4, "MODE") == S["M_MOVE"] and w.e(4, "PX") == 0
          and not w.e(4, "POT") & AWAKE, (w.e(4, "FLAGS"), w.e(4, "MODE"), w.e(4, "PX"), w.e(4, "POT")))
    ingame(p, pre(4) + far1("perch1"))
    check("W ... its first own turn (perch1): awake, still solid", w.e(4, "POT") & AWAKE and not w.e(4, "FLAGS") & GH,
          (w.e(4, "FLAGS"), w.e(4, "POT")))
    # the rest pose (ANIM_FREEZE: phase 0 = the cycle's first frame)
    for awake, fid, fl, tg in ((0, "FID_garg_perch", PERCHED, "perched"),
                               (1, "FID_garg_fly", EF_ACTIVE | EF_HOSTILE, "awake"),
                               (0, "FID_garg_fly", EF_ACTIVE | EF_HOSTILE, "solid not yet awake (door arrival)")):
        w.clear()
        w.put(3, KG, 20, gy, rcd=1 | (AWAKE if awake else 0), flags=fl)
        p.wb("ANIM_FREEZE", 1)
        ingame(p, [0xDD, 0x21] + w16(ENT + 3 * STRIDE) + [0x3E, 3, 0x32] + w16(S["ANIM_SLOT"]) +
               [0xCD] + w16(S["anim_entity"]) + [0x32] + w16(RES))
        check(f"W rest pose {tg} = {fid[4:]}", p.rb(RES) == S[fid], p.rb(RES))
    part_fly(p, w, gy)


def anim_n(p, n, tick=True, pre_=()):
    """n anim_entity calls on slot 3 (TICK_COUNTER + 1 before each when tick) -> the n fids."""
    out = RES - n
    body = list(pre_)
    for i in range(n):
        if tick:
            body += [0x21] + w16(S["TICK_COUNTER"]) + [0x34]                      # ld hl, TICK_COUNTER; inc (hl)
        body += ([0xDD, 0x21] + w16(ENT + 3 * STRIDE) + [0x3E, 3, 0x32] + w16(S["ANIM_SLOT"]) +
                 [0xCD] + w16(S["anim_entity"]) + [0x32] + w16(out + i))
    ingame(p, body)
    return list(p.z.read_memory(out, n))


def part_fly(p, w, gy):
    """GARG-FLY (user 2026-11-16): an awake Gargoyle hovering at rest plays garg_fly / garg_fly2 (4 ticks each,
    phase = TICK_COUNTER + 5 * slot) for N ticks; the attack = windup; a hit = garg_hurt x3 then the cycle again;
    death = garg_hurt x3 then garg_dead; re-perched (RCD_AWAKE clear) = the statue."""
    F1, F2 = S["FID_garg_fly"], S["FID_garg_fly2"]
    p.wb("ANIM_FREEZE", 0)
    w.clear()
    w.put(3, KG, 20, gy, rcd=1 | AWAKE)
    t0 = p.rb("TICK_COUNTER")
    n = 24
    got = anim_n(p, n)
    want = [F1 if ((t0 + 1 + i + 15) & 7) < 4 else F2 for i in range(n)]
    check(f"GF awake hovering {n} ticks: garg_fly / garg_fly2 alternate every 4 ticks", got == want, (got, want))
    # attack: KS_ATTACK started (as rg_pose / do_attack): windup for 2 ticks (stop before the claw's impact)
    pre_ = ([0xDD, 0x21] + w16(ENT + 3 * STRIDE) + [0xCD] + w16(S["kind_seq_ptr"]) + [0x11] + w16(S["KS_ATTACK"]) +
            [0x19, 0x7E, 0x23, 0x66, 0x6F, 0xCD] + w16(S["start_seq"]))
    got = anim_n(p, 2, pre_=pre_)
    check("GF attack: garg_windup x2", got == [S["FID_garg_windup"]] * 2, got)
    # a hit (RC_HURT reaction): hurt 3 ticks, then the fly cycle again
    for rc, tag in ((S["RC_HURT"], "hit"), (S["RC_DEATH"], "death")):
        w.clear()
        w.put(3, KG, 20, gy, rcd=1 | AWAKE)
        b = ENT + 3 * STRIDE
        p.wb(b + EF["REACT"], rc)
        p.wb(b + EF["REACTAT"], 0)
        p.wb("TURN_PHASE", 1)
        p.wb("TURN_TICK", 5)
        got = anim_n(p, 5)
        p.wb("TURN_PHASE", 0)
        p.wb("TURN_TICK", 0)
        H = S["FID_garg_hurt"]
        if tag == "hit":
            ok = got[:3] == [H] * 3 and got[3] in (F1, F2) and got[4] in (F1, F2)
        else:
            ok = got == [H] * 3 + [S["FID_garg_dead"]] * 2
        check(f"GF {tag}: garg_hurt x3 then " + ("the fly cycle" if tag == "hit" else "garg_dead"), ok, got)
    # sits back (as lp re-perch: spawn_one sets EF_GHOST): the statue for every tick
    w.clear()
    w.put(3, KG, 20, gy, rcd=1, flags=PERCHED)
    got = anim_n(p, 8)
    check("GF re-perched: garg_perch on every tick", got == [S["FID_garg_perch"]] * 8, got)
    p.wb("ANIM_FREEZE", 1)


# ------------------------------------------------------------------------------------------------- G
def part_g(p, w):
    """GARG-PASS (user 2026-11-18): a perched Gargoyle (EF_GHOST) is fully intangible; the wake waits for a clear box."""
    gy = 10
    KO = S["K_ORC"]
    ob, oh = w.kt[KO]["bw"], w.kt[KO]["bh"]
    gw = w.kt[KG]["bw"]
    gx = 14
    solid = EF_ACTIVE | EF_HOSTILE
    # G1 a monster walks through (try_step); a solid one is a wall
    for fl, tag in ((PERCHED, "ghost"), (solid, "solid")):
        w.clear()
        w.rows()
        w.hero(2)
        w.put(3, KG, gx, gy, flags=fl, rcd=1 | (0 if fl & GH else AWAKE))
        w.put(5, KO, gx + gw, stand_y(1, oh))
        xs = []
        n = gw + ob + 1
        for _ in range(n):
            ingame(p, pre(5) + [0x16, 0xFF, 0x1E, 0x00, 0xCD] + w16(S["try_step"]))
            xs.append(w.e(5, "X"))
        want = [gx + gw - 1 - i for i in range(n)] if fl & GH else [gx + gw] * n
        check(f"G1 an Orc steps left into / through a {tag} Gargoyle: x {want}", xs == want, xs)
    # G2 the hero walks through (try_horizontal, far7): no bump (find_target $FF), no wake, no HP loss
    for fl, tag in ((PERCHED, "ghost"), (solid, "solid")):
        w.clear()
        w.rows()
        w.hero(gx - w.hw)
        w.put(3, KG, gx, gy, flags=fl, hp=30, rcd=1 | (0 if fl & GH else AWAKE))
        ingame(p, pre(0) + [0x3E, 1, 0x32] + w16(S["TMP6"]) + [0xCD] + w16(S["find_target"]) + [0x32] + w16(RES))
        ft = p.rb(RES)
        if fl & GH:
            xs = []
            for _ in range(gw + w.hw):
                ingame(p, pre(0) + [0x16, 0x01, 0x21] + w16(S["try_horizontal"]) + [0xCD] + w16(S["far7"]))
                xs.append(w.e(0, "X"))
            want = [gx - w.hw + 1 + i for i in range(gw + w.hw)]
            check(f"G2 the hero walks right through a ghost Gargoyle: find_target $FF, x {want}, hp 30, still a ghost",
                  ft == 0xFF and xs == want and w.e(3, "HP") == 30 and w.e(3, "FLAGS") & GH,
                  (ft, xs, w.e(3, "HP"), w.e(3, "FLAGS")))
        else:
            check("G2 control: a solid Gargoyle in front is the hero's bump target", ft == 3, ft)
    # G3 the wake is delayed while a body overlaps the statue, then happens on the first clear turn
    for who in ("hero", "monster"):
        w.clear()
        w.rows()
        if who == "hero":
            w.hero(gx + 1)                                   # overlapping the statue's box
        else:
            w.hero(gx + gw + 1)                              # gap 1: in wake reach
            w.put(5, KO, gx, stand_y(1, oh))                 # an Orc standing in the statue's box
        w.put(3, KG, gx, gy, flags=PERCHED)
        ingame(p, pre(3) + far1("perch1"))
        held = not w.e(3, "POT") & AWAKE and w.e(3, "FLAGS") & GH and w.e(3, "MODE") == 0
        if who == "hero":
            w.hero(gx + gw + 1)
        else:
            p.wb(ENT + 5 * STRIDE + EF["FLAGS"], 0)
        ingame(p, pre(3) + far1("perch1"))
        woke = w.e(3, "POT") & AWAKE and not w.e(3, "FLAGS") & GH and w.e(3, "MODE") == S["M_SEQ"]
        check(f"G3 the {who} overlaps the ghost (hero in reach): no wake; box clear next turn: wakes (solid, M_SEQ)",
              held and woke, (held, w.e(3, "POT"), w.e(3, "FLAGS"), w.e(3, "MODE")))
    # G3p (GARG-REDRAW, closes the §4.1 known limit) a PENDING body (squeezed / door arrival) on the statue's box
    # delays the wake too (perch1 -> pend_hit.go); once it is gone the hero in reach wakes it
    w.clear()
    w.rows()
    w.hero(gx + gw + 1)                                  # gap 1: in wake reach
    w.put(5, KO, gx, stand_y(1, oh), flags=EF_ACTIVE | EF_HOSTILE | S["EF_PENDING"])
    w.put(3, KG, gx, gy, flags=PERCHED)
    ingame(p, pre(3) + far1("perch1"))
    held = not w.e(3, "POT") & AWAKE and w.e(3, "FLAGS") & GH and w.e(3, "MODE") == 0
    p.wb(ENT + 5 * STRIDE + EF["FLAGS"], 0)
    ingame(p, pre(3) + far1("perch1"))
    woke = w.e(3, "POT") & AWAKE and not w.e(3, "FLAGS") & GH and w.e(3, "MODE") == S["M_SEQ"]
    check("G3p a PENDING Orc on the ghost's box (hero in reach): no wake; gone next turn: wakes",
          held and woke, (held, w.e(3, "POT"), w.e(3, "FLAGS"), w.e(3, "MODE")))
    # G4 a dagger flies through the ghost and hits the Orc behind it; a solid Gargoyle is the target instead
    for fl, tag in ((PERCHED, "ghost"), (solid, "solid")):
        w.clear()
        w.rows()
        w.hero(4)
        w.put(3, KG, 8, gy, flags=fl, hp=30, rcd=1 | (0 if fl & GH else AWAKE))
        w.put(5, KO, 12, stand_y(1, oh), hp=30)
        ev = [p.rb(S["kind_tab"] + S["KT_EVA"] + k) for k in (KO, KG)]
        p.wb(S["kind_tab"] + S["KT_EVA"] + KO, 0)
        p.wb(S["kind_tab"] + S["KT_EVA"] + KG, 0)
        ingame(p, bank3([0xCD] + w16(S["fx_reset"]) + [0xCD] + w16(S["build_live"]) + [0xDD, 0x21] + w16(ENT) +
                        [0x3E, S["ABL_DAGGER"], 0x21] + w16(S["ab_ammo"]) + [0x1E, 0, 0xCD] + w16(S["proj_fire"])))
        p.wb(S["kind_tab"] + S["KT_EVA"] + KO, ev[0])
        p.wb(S["kind_tab"] + S["KT_EVA"] + KG, ev[1])
        tgt = p.rb("pf_tgt")
        cl = list(p.z.read_memory(S["pf_cand"], 16))
        cands = []
        for i in range(0, 15, 3):
            if cl[i] == 0xFF:
                break
            cands.append(cl[i + 2] & S["PFCF_SLOT"])
        ingame(p, bank3([0xCD] + w16(S["fx_reset"])))       # (no FX track left for the P part's track limit)
        if fl & GH:
            check("G4 a dagger passes the ghost Gargoyle: not a candidate (the Orc behind is), the Gargoyle untouched",
                  3 not in cands and 5 in cands and tgt != 3 and w.e(3, "HP") == 30 and w.e(3, "FLAGS") & GH,
                  (cands, tgt, w.e(3, "HP")))
        else:
            check("G4 control: a solid Gargoyle is a candidate in front of the Orc", [c for c in cands if c][:1] == [3] and 5 in cands,
                  (cands, tgt))
    # G6 (review fix 1) try_close's room_bodies (bank 0): with A = EF_HOSTILE (the "hostile within 2 cols" span) a ghost
    # is skipped, a solid Gargoyle counts; with A = 0 (the door cells) the ghost still fills them, and so does a
    # PENDING | WALKIN follower (bit 5 set too: not a ghost)
    def rbod(mask):
        ingame(p, [0x3A] + w16(S["PORT_7FFD_SHADOW"]) + [0xF5, 0x3E, S["BANK_TEXT"], 0xCD] + w16(S["page_bank"]) +
               [0x01, 0, 0, 0x11, 32, 18, 0x3E, mask, 0xCD] + w16(S["room_bodies"]) +
               [0x9F, 0x32] + w16(RES) + [0xF1, 0xCD] + w16(S["restore_page"]))
        return p.rb(RES) != 0
    for fl, tag, want_h, want_any in ((PERCHED, "ghost", False, True), (solid, "solid", True, True),
                                      (solid | S["EF_PENDING"] | S["EF_WALKIN"], "PENDING | WALKIN follower", True, True)):
        w.clear()
        w.rows()
        w.hero(2)
        w.put(3, KG, gx, gy, flags=fl, rcd=1 | (0 if fl == PERCHED else AWAKE))
        got = (rbod(EF_HOSTILE), rbod(0))
        check(f"G6 room_bodies with a {tag}: hostile span {want_h}, door cells {want_any}", got == (want_h, want_any), got)
    # G5 arrival_conflicts (the hero's arrival box on the statue) never makes it PENDING
    w.clear()
    w.rows()
    w.hero(gx)
    w.put(3, KG, gx, gy, flags=PERCHED)
    ingame(p, [0x21] + w16(S["arrival_conflicts"]) + [0xCD] + w16(S["far7"]))
    check("G5 arrival_conflicts: the hero's arrival box on a ghost leaves it non-PENDING (a ghost)",
          w.e(3, "FLAGS") == PERCHED, w.e(3, "FLAGS"))

# ------------------------------------------------------------------------------------------------- GC
def part_gc(p, w):
    """GARG-CHAIN (new_monsters.md 4.1b): the first proximity wake arms GARG_STIR (storey + 1); each later monster
    pass (real resolve_monsters) wakes the first eligible perched Gargoyle on that storey, one a pass."""
    gy1, gy0 = 10, 1                                     # the cruise rows of storey 1 / 0
    gw = w.kt[KG]["bw"]
    KO = S["K_ORC"]
    oh = w.kt[KO]["bh"]
    ax = 14
    pas = [0xCD] + w16(S["build_live"]) + [0xCD] + w16(S["resolve_monsters"])

    def awake(sl):
        return bool(w.e(sl, "POT") & AWAKE) and not w.e(sl, "FLAGS") & GH

    def lines():
        return p.rb("LOG_QN")

    def setup(statues, hero_x):
        w.clear()
        w.rows()
        w.hero(hero_x)
        for sl, x, y in statues:
            w.put(sl, KG, x, y, flags=PERCHED)
        p.wb("GARG_STIR", 0)
        p.wb("GARG_SPENT", 0)
        p.wb("LOG_QN", 0)

    # GC1 pass 1: A (slot 3) wakes by proximity and arms the chain (storey 1 -> 2); B / D (storey 1) stay perched
    # (the pass is spent); the other-storey C never wakes; "THE STATUES STIR!" + the wake line = 2 log lines
    setup([(3, ax, gy1), (4, 26, gy1), (5, 24, gy0), (6, 4, gy1)], ax + gw + 1)   # D far left, B far right: A / B fly off
    ingame(p, pas)
    st = [awake(3), awake(4), awake(5), awake(6)]
    check("GC1 proximity wake of A arms the chain (GARG_STIR = 2) and spends the pass: B, C, D still perched",
          st == [True, False, False, False] and p.rb("GARG_STIR") == 2 and p.rb("GARG_SPENT") == 1, (st, p.rb("GARG_STIR")))
    check("GC1 the STIR line + the wake line were queued (2 lines)", lines() == 2, lines())
    # GC2 pass 2: B (first perched on the storey, slot 4) wakes; pass 3: D; pass 4: C (storey 0) never
    seq = []
    for _ in range(3):
        ingame(p, pas)
        seq.append((awake(4), awake(5), awake(6)))
    check("GC2 one chain wake a pass in slot order: pass 2 -> B, pass 3 -> D, pass 4 nothing (C, other storey, stays perched)",
          seq == [(True, False, False), (True, False, True), (True, False, True)], seq)
    check("GC2 the chained wakes printed the wake line only (no 2nd STIR): 4 lines in all", lines() == 4, lines())
    # GC3 STIR only with a joiner: A alone; A + a statue on the other storey only
    for tag, others in (("alone", []), ("with a statue on the other storey only", [(4, 24, gy0)])):
        setup([(3, ax, gy1)] + others, ax + gw + 1)
        ingame(p, pas)
        check(f"GC3 {tag}: A wakes, the chain is armed, but no STIR line (1 line)",
              awake(3) and p.rb("GARG_STIR") == 2 and lines() == 1, (lines(), p.rb("GARG_STIR")))
    # GC4 an overlapped statue is skipped (the next one wakes), retried once the body is gone (PENDING counts too)
    for pend in (0, EF_PENDING):
        setup([(4, 24, gy1), (6, 20, gy1)], 2)
        p.wb("GARG_STIR", 2)
        w.put(5, KO, 24, stand_y(1, oh), flags=EF_ACTIVE | EF_HOSTILE | pend)   # an Orc on B's box (slot 5)
        ingame(p, pas)
        first = (awake(4), awake(6))
        p.wb(ENT + 5 * STRIDE + EF["FLAGS"], 0)
        ingame(p, pas)
        check(f"GC4 {'PENDING ' if pend else ''}body on B: skipped, D wakes first; body gone: B wakes next pass",
              first == (False, True) and awake(4), (first, awake(4)))
    # GC5 the other storey's chain never reaches a statue on this storey
    setup([(3, 20, gy1)], 2)
    p.wb("GARG_STIR", 1)                                 # armed on storey 0
    ingame(p, pas)
    check("GC5 chain armed on storey 0: a storey-1 statue (hero far) stays perched", not awake(3), w.e(3, "POT"))
    # GC6 cleared by vis_reset (a level change / new game; its tail is vis_room_sync)
    p.wb("GARG_STIR", 2)
    ingame(p, [0xCD] + w16(S["vis_reset"]))
    check("GC6 vis_reset clears GARG_STIR", p.rb("GARG_STIR") == 0, p.rb("GARG_STIR"))
    w.clear()


def GI_bank3(p, addr):
    """one byte of bank 3 at addr ($C000..): paged in by a stub."""
    ingame(p, bank3([0x3A] + w16(addr) + [0x32] + w16(RES)))
    return p.rb(RES)


# ------------------------------------------------------------------------------------------------- C
def part_c(p, w):
    """T10a follow-up (user 2026-11-14): the Warrior's innate COLD R (hero_recalc's base): HERO_RES B0 COLD = R with
    nothing worn and with the Frost Charm (no stacking); a COLD hit (the Wraith bolt / touch, the Archmage Frost row:
    all deal_hit DTY_COLD) halves (min 1); a PHYS hit does not."""
    R = S["RSP_R"]
    worn0 = list(p.z.read_memory(S["WORN"], 12))
    ingame(p, far6("hero_recalc"))
    r0 = list(p.z.read_memory(S["HERO_RES"], 3))
    cs = S["WORN"] + S["WS_CHARM"] * S["IR_STRIDE"]
    p.wmem(cs, [S["IT_C_FROST"], 1, 0])
    ingame(p, far6("hero_recalc"))
    r1 = list(p.z.read_memory(S["HERO_RES"], 3))
    p.wmem(S["WORN"], worn0)
    ingame(p, far6("hero_recalc"))
    check("C Warrior HERO_RES: COLD R innate (B0 bits 4-5), the same with the Frost Charm (no stacking)",
          r0[0] & 0x30 == R << 4 and r1[0] & 0x30 == R << 4 and r0[1:] == [0, 0], (r0, r1))
    for dhc, roll, want, tag in ((S["DTY_COLD"] | S["DH_NODEF"], 7, 3, "COLD 7 -> 3"),
                                 (S["DTY_COLD"] | S["DH_NODEF"], 1, 1, "COLD 1 -> 1 (min 1)"),
                                 (S["DTY_PHYS"], 4, 4 - p.rb("HERO_DEF"), "PHYS 4 - DEF (untouched)")):
        w.clear()
        w.hero(6, hp=100)
        w.put(3, KA, 20, 10)
        ingame(p, bank3([0xDD, 0x21] + w16(ENT + 3 * STRIDE) + [0x3E, 0, 0x06, roll, 0x0E, dhc, 0x1E, 0, 0xCD]
                        + w16(S["deal_hit"])))
        check(f"C deal_hit on the Warrior: {tag}", 100 - w.e(0, "HP") == max(1, want), 100 - w.e(0, "HP"))


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
    p.wb("GARG_STIR", 2)
    xfer(Y)
    ingame(p, [0xCD] + w16(S["vis_room_sync"]))         # do_exit .in's call (also vis_reset's tail: a level change)
    check("R1 a room exit (do_exit's vis_room_sync) clears GARG_STIR", p.rb("GARG_STIR") == 0, p.rb("GARG_STIR"))
    check(f"R1 leave room {X} -> {Y}: the awake Gargoyle parked (E_ROOM = X | LPK_PARK)",
          w.e(5, "ROOM") == X | PARK and w.e(5, "KIND") == KG, (w.e(5, "ROOM"), w.e(5, "KIND")))
    xfer(X, hx=1)
    g = [s_ for s_ in range(1, 16) if w.e(s_, "FLAGS") & EF_ACTIVE and w.e(s_, "ROOM") == X and w.e(s_, "KIND") == KG]
    check(f"R2 back in room {X}: the Gargoyle restored PERCHED (RCD_AWAKE clear, EF_GHOST), hp 11 kept",
          g and not w.e(g[0], "POT") & AWAKE and w.e(g[0], "FLAGS") & GH and w.e(g[0], "HP") == 11,
          [(s_, w.e(s_, "POT"), w.e(s_, "HP")) for s_ in g])
    # follow candidates: a perched one never, an awake one yes; place_follower keeps it awake
    w.room = p.rb("CUR_ROOM")
    for awake in (0, 1):
        w.clear()
        w.rows()
        w.hero(1)
        w.put(3, KG, 1 + w.hw, gy, rcd=1 | (AWAKE if awake else 0), flags=EF_ACTIVE | EF_HOSTILE if awake else PERCHED)
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
        seq = w.e(3, "SEQL") | w.e(3, "SEQH") << 8
        check("F Imp shot pose (T10b): rg_pose plays KS_BLOCK = its attack (fly1 -> spit)",
              seq == seq_ptr(p, KA, S["KS_BLOCK"]) == seq_ptr(p, KA, S["KS_ATTACK"]), (seq, seq_ptr(p, KA, S["KS_BLOCK"])))
        cf, tp, _ = one(s1 + 1, 6)
        check("F Imp gap 6 (= r): no shot", not tp)
    else:
        cf, tp, q = one(s1 + 1, 7)
        check("F Wraith at the cruise row, gap 7 (< r 8): fires; FX frost_fly x2, impact frost_crack, $45, row 9s + 4",
              cf and tp and q[2:7] == [S["FID_frost_fly"], S["FID_frost_fly"], S["FID_frost_crack"],
                                       S["FID_frost_crack"], 0x45] and q[8] == s1 + 4, q)
        seq = w.e(3, "SEQL") | w.e(3, "SEQH") << 8
        cast = seq_ptr(p, KA, S["KS_BLOCK"])
        check("F Wraith FROST BOLT pose (T10b): rg_pose plays KS_BLOCK = drift -> wraith_cast (not the touch)",
              seq == cast and p.rb(cast + 3) == S["FID_wraith_cast"] and cast != seq_ptr(p, KA, S["KS_ATTACK"]),
              (seq, cast, p.rb(cast + 3)))
        cf, tp, _ = one(s1 + 1, 8)
        check("F Wraith gap 8 (= r): no shot", not tp)


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
        p.wb("TMP6", 0xFF)                            # the refused step toward the hero (GARG-PASS: part_g leaves 1)
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
    check("P5 Goblin: throws once, RCD_SPENT set", shot and rcd & SPENT, (shot, rcd))
    shot, c, rcd, _ = throw(KGB, 3, rcd_hi=SPENT)
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


# ------------------------------------------------------------------------------------------------- D
def part_d(p, w):
    """T10b: the Goblin's one dagger survives room re-entry (parked and banked); the Gargoyle still re-perches."""
    blk = bytes(p.z.read_memory(G.BASE, G.BLOCK_LEN))
    X = p.rb("CUR_ROOM")
    others = [r for r in range(9) if r != X and room_model.field(blk, r, "RD_FLAGS") & S["RDF_PRESENT"]
              and r not in (p.rb("LVL_LAIR"), p.rb("LVL_SANCTUM"))]
    KGB = S["K_GOBLIN"]
    PIT = 14
    gh = w.kt[KGB]["bh"]

    def xfer(dst):
        src = p.rb("CUR_ROOM")
        p.set_ent(0, X=1, Y=stand_y(1, w.hh))
        p.wmem(S["CAND_LIST"], [0xFF] * 16)
        p.wb("FOLLOW_N", 0)
        p.wb("EXIT_DEST", dst)
        ingame(p, [0x21] + w16(S["lp_transition"]) + [0xCD] + w16(S["far3"]))
        p.wb("TRK_PREV", src)
        p.wb("CUR_ROOM", dst)
        p.set_ent(0, ROOM=dst)

    def find(kind):
        return [s_ for s_ in range(1, 16) if w.e(s_, "FLAGS") & EF_ACTIVE and w.e(s_, "ROOM") == X
                and w.e(s_, "KIND") == kind]

    def pit_throw(slot):
        """put the body at slot across the narrow pit from the hero (gap 3), run pit6 -> shot?"""
        w.rows()
        p.wb(w.desc + S["RD_PITCOL"], PIT)
        p.wb(w.desc + S["L2_PITW"], 0)
        mx = PIT + 1
        w.hero(mx - 3 - w.hw, 0)
        p.set_ent(slot, X=mx, Y=stand_y(0, gh), PX=8 * mx, PY=8 * stand_y(0, gh), MODE=S["M_REST"])
        p.wb(ENT + slot * STRIDE + EF["POT"], (p.rb(ENT + slot * STRIDE + EF["POT"]) & ~3 & 255) | 1)  # counter 0
        p.wb("TURN_PEND", 0)
        p.wb("TMP6", 0xFF)                            # .fstep's refused dx: -1 (toward the hero, into the pit)
        ingame(p, pre(slot) + far6("pit6"))
        shot = bool(p.rb("TURN_PEND") & S["TP_SHOT"])
        p.wb("TURN_PEND", 0)
        p.wb(w.desc + S["RD_PITCOL"], w.pit0[0])
        p.wb(w.desc + S["L2_PITW"], w.pit0[1])
        return shot

    w.clear()
    w.hero(1)
    w.put(3, KGB, 20, stand_y(0, gh), rcd=1, hp=6)
    w.put(5, KG, 26, 10, rcd=1 | AWAKE, hp=9)
    check("D1 the Goblin throws its dagger (RCD_SPENT set)", pit_throw(3) and w.e(3, "POT") & SPENT, w.e(3, "POT"))
    for trip, hops in (("parked", others[:1]), ("banked", others[:3])):
        if len(hops) < (1 if trip == "parked" else 3):
            check(f"D {trip}: needs {3} other rooms on this level", False, others)
            continue
        for r in hops:
            xfer(r)
        xfer(X)
        gb, ga = find(KGB), find(KG)
        check(f"D2 {trip} re-entry: the Goblin keeps RCD_SPENT", gb and w.e(gb[0], "POT") & SPENT,
              [(s_, w.e(s_, "POT")) for s_ in gb])
        check(f"D3 {trip} re-entry: no second throw", gb and not pit_throw(gb[0]), gb)
        check(f"D4 {trip} re-entry: the Gargoyle re-perched (RCD_AWAKE clear)", ga and not w.e(ga[0], "POT") & AWAKE,
              [(s_, w.e(s_, "POT")) for s_ in ga])
        if ga:
            w.p.wb(ENT + ga[0] * STRIDE + EF["POT"], w.e(ga[0], "POT") | AWAKE)


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
        part_c(p, w)
        part_w(p, w)
        part_g(p, w)
        part_gc(p, w)
        part_p(p, w)
        part_f(p, w, 6)
        part_r(p, w)
        w = World(p)
        part_d(p, w)
        check("setup: level_descend -> D7", descend_to(p, 7))
        w = World(p)
        part_f(p, w, 7)
    print(f"nm3b: {NCHK[0]} checks, {len(FAILS)} failed" + (f": {FAILS[:8]}" if FAILS else ""), flush=True)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
