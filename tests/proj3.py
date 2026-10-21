#!/usr/bin/env python3
"""D3-6b: proj_fire (src/proj3.asm) — the projectile logic resolved at cast
time — against an independent Python model written from game.md §6 ("Logic
(instant at cast time)", §6.0 responses / reflect / pierce / loop guard, §6.1
spells, §6.3 missiles; ability rows from the doc transcription in
tests/combat_tables.py, resistances from its KINDS). Stubs run at
LOWRAM_END_3B with bank 3 paged on a booted Knight game (PROTO room A, every
other slot cleared); the flight row (caster top + 2) of ROOM_MAP is rewritten
per case (walls / exits), bodies are poked into slots 1..15.

Checked per case (model == Z80): pf_stop (L), pf_col, pf_tgt, pf_lost, every
body's HP / EF_DYING / E_REACTAT (struck: the FX tick), ST_FLAGS / ST_T1, the
RNG state after the cast (=> the exact draw order), the FX descriptor
(pf_desc) and the started track (FXT0 = it, FX_BUSY = 1).

  P0  pf_dhc_tab (deal_hit C per ability) == the doc's type / NODEF / HEAL /
      effect columns; static, from the tape
  P1  THE TABLE (stage exit): every projectile row of game.md §6.1 / §6.3 at
      every rank — range (a body on the last cell is struck, one cell further
      the projectile fizzles at range end), dmg 1dN + bonus of its type,
      spells ignore DEF, missiles roll F1; the effect column (Spark CONFUSED,
      Frost FROZEN, Drain heals the caster, Firebolt burst, Lightning pierce +
      16 px FX, bounces)
  P2  §6.0 responses through projectiles: Bat SHOCK W, Ghost SHOCK X
      (reflect back onto the caster, no bounce used), Skeleton COLD / DRAIN I
      (stops, 0 dmg, no heal), Slime FIRE W, Ghost PHYS R (arrow)
  P3  walls: no bounce -> stop on the free cell in front; Frost bounces and
      freezes the caster; point-blank wall (impact-only FX); Firebolt at
      point-blank burns the caster, rank 3 spares him
  P4  loop guard: reflecting hero (HERO_RES SHOCK X) + Ghost -> 4 reversals
  P5  pierce: Lightning hits each body once per pass, again after a bounce;
      a reflector ends the piercing (reverses)
  P6  a mid-ladder body absorbs harmlessly (D3-7 T4: no Firebolt burst
      after it); Drain reflected onto its caster hits without healing (D3-7
      T4); open exit edge ends it (no impact)
  P7  FX row: a Rat below the flight row -> its nearest row
  P8  fuzz: 120 random rooms (walls, exits, 1-5 bodies incl. flyers /
      mid-ladder / reflectors, both facings, every ability and rank, delays,
      seeds) == model
  P9  D3-7 T1 (the split ability turn): TURN_TICK is 0 after boot; casts at
      TURN_TICK 5 shift pf_itick / every struck body's E_REACTAT by 5 (model
      == Z80: Spark, Lightning pierce + bounce, Firebolt burst);
      set_reaction_at adds TURN_TICK; act_begin (bank 7, far7) refuses a
      lead col 0 / 31 (L = 0, TURN_PEND untouched) and accepts 1 / 30
      (TURN_PEND = TP_ACT | TP_MON, ACT_ABL, ACT_AT = 2, MON_AT = 3);
      act_fire fizzles (L = 0) at lead col 0 / 31; fx_start's drop counts
      in FX_DROP
  P10 D3-8 review 2: the adversarial fuzz case #208 (Lightning r2, a
      reflecting Ghost + 2 Slimes + a Bat over the caster, 3 kills, walls at
      cols 3 / 31) == model + the PF_ROWF invariant (flags = solid | edge,
      count = candidates not DONE; struck-dead ones stay DONE), its T printed;
      pf_cands' x1 guard (a body poked to x 30, 3 wide: x1 clamped to 31)
  P11 D3-8e: the re-review's 5-body fuzz worst casts #666 / #678 and the
      ROOM_CAP-legal worst of a model search (tests/budget.py "fzcast" /
      "fzcast2": Ghost <-> wall ping-pong through a stack, 16 strikes) ==
      model + the PF_ROWF invariant, their T printed; the split cast
      (proj_pre at TURN_TICK 0, proj_rel at ACT_FIRE_TICK) == the one-shot
      model at the fire tick (pf_part PFP_MID / PFP_DONE after the accept,
      pf_prep used up); a stale set-up of another ability is re-cast whole
Run: ZRCP_PORT=<port> python3 tests/proj3.py
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from game_lib import Harness, Proto, S, EMU_ARGS, K_KNIGHT, K_GHOST, K_RAT, K_BAT, K_SLIME, K_SKELETON, K_GOBLIN  # noqa: E402
import combat_tables as CT  # noqa: E402

import os  # noqa: E402
PROFILE = os.environ.get("PROJ_PROFILE")
STUB = S["LOWRAM_END_3B"]
RES = STUB + 200
STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT, EF_DYING = 1, 2, 4, 8, 16
E_REACT, E_REACTAT = 15, 16
STF, ST1 = S["ST_FLAGS"], S["ST_T1"]
PHYS, FIRE, COLD, SHOCK = range(4)
N, R, I, X = 0, 1, 2, 3
NODEF, HEAL, EFS = S["DH_NODEF"], S["DH_HEAL"], S["DH_EFX_SHIFT"]
FROZEN, CONFUSED = 1, 5
PFS = dict(RANGE=0, WALL=1, BODY=2, ABSORB=3, EXIT=4, LOOP=5)
PFS_NAME = {v: k for k, v in PFS.items()}
NONE = 0xFF
T_AIR, T_BRICK = S["T_AIR"], S["T_BRICK"]
ROW_DY, MAXREV, IMPT = S["PF_ROW_DY"], S["PF_MAXREV"], S["PF_IMPT"]
SPARK, FIREBOLT, FROST, DRAINL, LIGHTNING, DAGGER, BOW = 0, 1, 2, 3, 4, 7, 8
ABL_NAMES = {0: "Spark", 1: "Firebolt", 2: "Frost", 3: "Drain", 4: "Lightning", 7: "dagger", 8: "bow"}
RANK_KEYS = ["Spark", "Firebolt", "Frost", "Drain", "Lightning"]
SPELLF, PIERCEF, BURSTF, HEALF = CT.SPELL, CT.PIERCE, CT.BURST, CT.HEAL


def w16(v):
    return [v & 255, v >> 8]


# ---- the doc's ability rows (combat_tables transcription of game.md §5/§6) ----
def rank_row(abl, rank):
    """(range, die, bonus, bounces, effect) of ability abl at rank 1..3."""
    if abl in (DAGGER, BOW):
        return CT.AMMO[abl - DAGGER][1:]
    return CT.RANKS[RANK_KEYS[abl]][rank - 1][1:]


def row_addr(abl, rank):
    if abl in (DAGGER, BOW):
        return S["ab_ammo"] + (abl - DAGGER) * 6
    return S["ab_rank"] + (abl * 3 + rank - 1) * 6


def ab(abl):
    dty, a1, a2, spd, fl, hit = CT.DEFS[abl]
    names, _ = CT.FIDS[abl]
    fids = [NONE if n is None else S["FID_" + n] for n in names]
    return dict(dty=dty, speed=spd, flags=fl, hit=hit, fids=fids)


def dhc_doc(abl):
    """deal_hit C from the doc columns: type, spells ignore DEF (§6.1), Drain
    heals, Spark confuses, Frost freezes."""
    d = ab(abl)
    if d["flags"] & CT.MELEE:
        return 0
    c = d["dty"] | (NODEF if d["flags"] & SPELLF else 0) | (HEAL if d["flags"] & HEALF else 0)
    c |= {SPARK: CONFUSED, FROST: FROZEN}.get(abl, 0) << EFS
    return c


# ---- RNG (io.asm rng_next / rng_mod) ------------------------------------------
class Rng:
    def __init__(self, st):
        self.st = st

    def next(self):
        h, l = self.st >> 8, self.st & 255
        h1 = (((h & 1) << 7) | (l >> 1)) ^ h
        l1 = (((l & 1) << 7) | (h1 >> 1)) ^ l
        h2 = l1 ^ h1
        self.st = (h2 << 8) | l1
        return l1

    def mod(self, n):
        b = n - 1
        a = (b >> 1) | b
        a = (a >> 2) | a
        m = (a >> 4) | a
        while True:
            v = self.next() & m
            if v < n:
                return v


# ---- 3E-T11 mon_drop (pickup6.asm, R6): the drop chance on the gameplay RNG ----------
# drop_tab first match by kind (the defs.asm stand-in aliases: K_ORC / K_NECRO =
# Goblin, K_ARCHER = Skeleton): Rat 1/4, Goblin 1/4, Skeleton (archer) arrows
# 1/2 in a Warrior run only (no roll for the Mage). EF_RESPAWN and the hero:
# no roll. (The lair boss's unique is not rolled; the models run outside lairs.)
EF_RESPAWN = 0x80
DROP_N = {K_RAT: 4, K_GOBLIN: 4}


def drop_roll(rng, T, hero):
    if T.flags & (EF_PLAYER | EF_RESPAWN):
        return None
    n = DROP_N.get(T.kind)
    if n is None and T.kind == K_SKELETON and (hero is None or hero.kind == K_KNIGHT):
        n = 2
    return None if n is None else rng.mod(n) == 0


# ---- the model -----------------------------------------------------------------
class Body:
    def __init__(self, slot, kind, x, y, hp, maxhp=None, flags=EF_ACTIVE | EF_HOSTILE):
        self.slot, self.kind, self.x, self.y = slot, kind, x, y
        self.hp, self.maxhp, self.flags = hp, maxhp or hp, flags
        self.react, self.reactat, self.stf, self.st1 = 0, 0, 0, 0


class World:
    def __init__(self, kt, hero_res=(0, 0, 0), hero_def=1):
        self.kt = kt                 # kind -> dict(bw, bh, atk, eva, fly)
        self.bodies = {}
        self.hero_res, self.hero_def = list(hero_res), hero_def
        self.row = [T_AIR] * 32      # the flight row's tiles
        self.row[0] = self.row[31] = T_BRICK
        self.kx_over = {}            # kind -> RES 3 B poked into kx_tab for one case

    def resp(self, b, t):
        """(response, weak) of body b to type t."""
        if b.flags & EF_PLAYER:
            rb = self.hero_res
        elif b.kind in self.kx_over:
            rb = self.kx_over[b.kind]
        else:
            rb = CT.kx_row(*CT.KINDS[b.kind][1:])[:3] if b.kind in CT.KINDS else [0, 0, 0]
        return (rb[t // 4] >> (2 * (t % 4))) & 3, (rb[2] >> t) & 1

    def imm(self, b):
        if b.flags & EF_PLAYER:
            return self.hero_imm
        return CT.KINDS[b.kind][2] if b.kind in CT.KINDS else 0

    hero_imm = 0
    turn_tick = 0                # D3-7 T1: TURN_TICK at the cast (pf_tick adds it)

    def deal(self, rng, att, tgt, dmg, c, e):
        """combat3.asm deal_hit (HP, death, reaction, FROZEN / CONFUSED, heal)."""
        T = self.bodies[tgt]
        if T.hp == 0:
            return 0
        t = c & 7
        rsp, weak = self.resp(T, t)
        if rsp >= I:
            return 0
        if rsp == R:
            dmg = max(1, dmg // 2)
        if weak:
            dmg = min(255, dmg * 2)
        if t == PHYS and not c & NODEF:
            dmg = max(1, dmg - (self.hero_def if T.flags & EF_PLAYER else 0))
        dmg = max(1, dmg)
        lost = min(dmg, T.hp)
        T.hp -= lost
        if T.hp == 0:
            T.flags |= EF_DYING
            T.react = 3
            T.stf = T.st1 = 0
            drop_roll(rng, T, self.bodies.get(0))          # 3E-T11 mon_drop
        else:
            T.react = T.react if T.react == 3 else 1
            if T.stf & 3 == FROZEN and t == FIRE:          # thaw
                T.stf = (T.stf & ~3) | 0x40                # HOLD_GUARD (D3-8c)
                T.st1 &= 0x0F
            efx = (c >> EFS) & 7
            if efx:
                ch = e >> 4
                ok = True
                if ch:
                    ok = rng.mod(ch) == 0
                turns = e & 15
                imm_bit = {FROZEN: 0, CONFUSED: S["IMMF_CONFUSE"]}[efx]
                if self.imm(T) & imm_bit:
                    ok = False                             # D3-8f R2 (1): immunity first
                if ok and rsp == R:
                    turns //= 2
                if ok and turns:
                    if efx == FROZEN and (T.stf & 3 or T.stf & 0x40):
                        pass                               # D3-8c: held body / HOLD_GUARD
                    elif efx == FROZEN:
                        if att == tgt:
                            turns = 1                      # D3-8c: self-freeze
                        same = (T.stf & 3) == FROZEN
                        cur = T.st1 >> 4
                        T.stf = (T.stf & ~3) | FROZEN
                        T.st1 = (T.st1 & 0x0F) | (max(cur, turns) if same else turns) << 4
                    else:
                        same = (T.stf & 0x0C) == (2 << 2)
                        cur = T.st1 & 15
                        T.stf = (T.stf & ~0x0C) | (2 << 2)
                        T.st1 = (T.st1 & 0xF0) | (max(cur, turns) if same else turns)
        A = self.bodies[att]
        if c & HEAL and A.hp > 0:
            A.hp = min(A.maxhp, A.hp + lost)
        return lost

    def hit_roll(self, rng, att, tgt, mod):
        d20 = rng.mod(20) + 1
        held = self.bodies[tgt].stf & 3
        eva = 0 if held else self.kt[self.bodies[tgt].kind]["eva"]
        return d20 + self.kt[self.bodies[att].kind]["atk"] + mod - 10 - eva >= 0

    def fire(self, rng, cs, abl, rank, delay, solid_ids):
        """proj_fire. Returns dict(stop, col, tgt, lost, desc, flashes)."""
        C = self.bodies[cs]
        d = ab(abl)
        rng_, die, bonus, bnc, eff = rank_row(abl, rank)
        dhc = dhc_doc(abl)
        t = dhc & 7
        fast = d["speed"] == 16
        kc = self.kt[C.kind]
        ly0, ly1 = C.y, C.y + kc["bh"] - 1
        row0 = C.y + ROW_DY
        left = bool(C.flags & EF_LEFT)
        dirn = -1 if left else 1
        pos = C.x if left else C.x + kc["bw"] - 1
        # candidates: slot order, alive, rows overlap the caster's
        cands = []
        for s in sorted(self.bodies):
            b = self.bodies[s]
            if not b.flags & EF_ACTIVE or b.flags & EF_DYING:
                continue
            k = self.kt[b.kind]
            if b.y > ly1 or b.y + k["bh"] - 1 < ly0:
                continue
            ladder = not k["fly"] and (b.y + k["bh"]) % 9 != 8
            cands.append(dict(x0=b.x, x1=b.x + k["bw"] - 1, s=s, ladder=ladder,
                              refl=self.resp(b, t)[0] == X, done=False))
        res = dict(tgt=NONE, lost=0, stopper=NONE, miss=NONE)
        segs, anchor, fxleft = [], None, None
        fxrow = [None]
        rev, cok, moves = 0, False, 0
        left_cells = rng_

        def tick(m):
            return self.turn_tick + delay + ((m + 1) // 2 if fast else m) + 1

        def rowof(s):
            b = self.bodies[s]
            bot = b.y + self.kt[b.kind]["bh"] - 1
            return min(max(row0, b.y), bot)

        def setrow(s):
            if fxrow[0] is None:
                fxrow[0] = rowof(s)

        def enter(col):
            nonlocal pos, left_cells, anchor, fxleft, moves
            pos = col
            left_cells -= 1
            if anchor is None:
                anchor, fxleft = col, dirn < 0
                segs.append(0)
            else:
                segs[-1] += 1
                moves += 1

        def bodies(col, m):
            for cd in cands:
                if not cd["x0"] <= col <= cd["x1"] or cd["done"]:
                    continue
                if cd["s"] == cs and not cok:
                    continue
                if self.bodies[cd["s"]].flags & EF_DYING:
                    continue
                cd["done"] = True
                if cd["ladder"] or cd["refl"]:
                    setrow(cd["s"])
                    if cd["ladder"]:
                        res["stopper"] = cd["s"]
                        return "ABSORB"
                    return "REFLECT"
                if not d["flags"] & SPELLF:
                    if not self.hit_roll(rng, cs, cd["s"], d["hit"]):
                        # T7: a miss flies on; the first one is pf_miss, every missed
                        # body dodges (RC_DODGE 4) when the FX passes, unless a
                        # reaction is pending already
                        if res["miss"] == NONE:
                            res["miss"] = cd["s"]
                        mb = self.bodies[cd["s"]]
                        if not mb.react:
                            mb.react, mb.reactat = 4, tick(m)
                        continue
                setrow(cd["s"])
                dmg = rng.mod(die) + 1 + bonus
                # D3-7 T4 (game.md §6): Drain on its own caster heals nothing
                lost = self.deal(rng, cs, cd["s"], dmg, dhc & ~HEAL if cd["s"] == cs else dhc, eff)
                if res["tgt"] == NONE:
                    res["tgt"], res["lost"] = cd["s"], lost
                tk = tick(m)
                if self.bodies[cd["s"]].react:
                    self.bodies[cd["s"]].reactat = tk
                if d["flags"] & PIERCEF:
                    continue
                res["stopper"] = cd["s"]
                return "BODY"
            return None

        def reverse():
            nonlocal rev, dirn, cok
            rev += 1
            dirn = -dirn
            cok = True
            for cd in cands:
                cd["done"] = False
            if anchor is not None:
                segs.append(0)

        while True:
            if left_cells == 0:
                stop = "RANGE"
                break
            nxt = pos + dirn
            if self.row[nxt] in solid_ids:
                if bnc == 0:
                    stop = "WALL"
                    break
                bnc -= 1
                if rev >= MAXREV:
                    stop = "LOOP"
                    break
                reverse()
                continue
            if nxt in (0, 31):
                enter(nxt)
                stop = "EXIT"
                break
            m = 0 if anchor is None else moves + 1
            r = bodies(nxt, m)
            if r == "REFLECT":
                if rev >= MAXREV:
                    stop = "LOOP"
                    break
                reverse()
                continue
            enter(nxt)
            if r:
                stop = r
                break
        fids = list(d["fids"])
        if anchor is None:
            anchor, fxleft = pos, dirn < 0
            segs.append(0)
            fids[0] = fids[1] = NONE
        if stop == "EXIT":
            fids[2] = NONE
        itick = tick(moves)
        if d["flags"] & BURSTF and stop not in ("EXIT", "ABSORB"):   # D3-7 T4: no burst after an absorb
            for cd in cands:
                if not cd["x0"] - 1 <= pos <= cd["x1"] + 1:
                    continue
                if cd["s"] == res["stopper"]:
                    continue
                if cd["s"] == cs and eff & 0x80:
                    continue
                dmg = rng.mod(eff & 15) + 1
                self.deal(rng, cs, cd["s"], dmg, FIRE | NODEF, 0)
                if self.bodies[cd["s"]].react:
                    self.bodies[cd["s"]].reactat = itick
        desc = fids + [0, anchor, row0 if fxrow[0] is None else fxrow[0],
                       (1 if fxleft else 0) | (2 if fast else 0), delay, IMPT, len(segs)] + segs + [0] * (5 - len(segs))
        res.update(stop=PFS[stop], col=pos, desc=desc, itick=itick)
        return res


# ---- the emulator side -----------------------------------------------------------
class T(Proto):
    worst = (0, "", 0)        # (T-states incl. the stub's paging + fx_reset, ability, rank)
    def code(self, body, limit=20000000):
        code = bytes([0xF3, 0x31] + w16(S["WORKSTORE_TOP"]) + body + [0x00, 0x18, 0xFE])
        end = STUB + len(code) - 3
        assert STUB + len(code) <= RES
        self.wmem(STUB, code)
        self.z.cmd("set-breakpoint 3 PC=%d" % end)
        self.extra_probes = {end}
        self.z.cmd("set-register PC=%d" % STUB)
        self.z.cmd("reset-tstates-partial")
        self.z.cmd("run %d" % limit)
        self.tstates = int(self.z.cmd("get-tstates-partial"))
        ok = self.pc() == end
        self.z.cmd("set-breakpoint 3")
        self.extra_probes = set()
        return ok

    def wmem(self, addr, data):
        self.z.cmd("write-memory %d %s" % (addr, " ".join(str(b) for b in data)))

    def bank3(self, inner):
        return ([0x3A] + w16(S["PORT_7FFD_SHADOW"]) + [0xF5, 0x3E, S["BANK_COLD3"], 0xCD] + w16(S["page_bank"])
                + inner + [0xF1, 0xCD] + w16(S["restore_page"]))

    def kinds(self):
        kt = {}
        for k in range(9):
            g = lambda f: self.rb(S["kind_tab"] + S[f] + k)  # noqa: E731
            kt[k] = dict(bw=g("KT_BW"), bh=g("KT_BH"), atk=g("KT_ATK"), eva=g("KT_EVA"),
                         fly=bool(g("KT_FLAGS") & S["KF_FLYER"]))
        return kt

    def setup(self, w, seed):
        """Write world w: slots, ST arrays, hero RES / DEF, the flight row."""
        room = self.rb("CUR_ROOM")
        mem = self.z.read_memory(S["P_ENTITIES"], 16 * STRIDE)
        mem = bytearray(mem)
        for s in range(16):
            o = s * STRIDE
            b = w.bodies.get(s)
            if b is None:
                mem[o + 2] = 0
                continue
            mem[o + 0], mem[o + 1], mem[o + 2] = b.kind, room, b.flags
            mem[o + 3], mem[o + 4], mem[o + 5], mem[o + 6] = b.x, b.y, b.hp, b.maxhp
            mem[o + E_REACT], mem[o + E_REACTAT] = 0, 0
        self.wmem(S["P_ENTITIES"], list(mem))
        self.wmem(STF, [0] * 16)
        self.wmem(ST1, [0] * 16)
        self.wmem(S["ST_T2"], [0] * 16)
        self.wmem(S["HERO_RES"], w.hero_res)
        self.wb("HERO_IMM", w.hero_imm)
        self.wb("HERO_DEF", w.hero_def)
        hero = w.bodies[0]
        row0 = hero.y + ROW_DY
        self.wmem(S["ROOM_MAP"] + row0 * 32, w.row)
        self.wmem(S["RNG_STATE"], w16(seed))
        self.wb("TURN_TICK", w.turn_tick)

    def fire(self, cs, abl, rank, delay):
        inner = ([0xCD] + w16(S["fx_reset"]) + [0xCD] + w16(S["build_live"]) +   # (try_player_turn does)
                 [0xDD, 0x21] + w16(S["P_ENTITIES"] + cs * STRIDE) +
                 [0x3E, abl, 0x21] + w16(row_addr(abl, rank)) + [0x1E, delay, 0xCD] + w16(S["proj_fire"]) +
                 [0x7D, 0x32] + w16(RES))
        assert self.code(self.bank3(inner)), "proj_fire stub did not return"
        T.worst = max(T.worst, (self.tstates, ABL_NAMES[abl], rank))
        if PROFILE:
            print(f"[T] {self.tstates:6d} {ABL_NAMES[abl]} r{rank}", flush=True)
        return self.rb(RES)

    def result(self, w):
        g = {k: self.rb(k) for k in ("pf_stop", "pf_col", "pf_tgt", "pf_lost", "pf_itick", "pf_miss")}
        g["desc"] = list(self.z.read_memory(S["pf_desc"], 16))
        g["rng"] = self.rw("RNG_STATE")
        g["busy"] = self.rb("FX_BUSY")
        g["tracks"] = [list(self.z.read_memory(S[f"FXT{i}"], 16)) for i in range(3)]
        mem = self.z.read_memory(S["P_ENTITIES"], 16 * STRIDE)
        stf = self.z.read_memory(STF, 16)
        st1 = self.z.read_memory(ST1, 16)
        g["bodies"] = {s: (mem[s * STRIDE + 5], bool(mem[s * STRIDE + 2] & EF_DYING),
                           mem[s * STRIDE + E_REACTAT] if mem[s * STRIDE + E_REACT] else None,
                           stf[s], st1[s]) for s in w.bodies}
        return g


def expect(w, res, seed_end):
    m = {"pf_stop": res["stop"], "pf_col": res["col"], "pf_tgt": res["tgt"], "pf_lost": res["lost"],
         "pf_itick": res["itick"], "pf_miss": res["miss"], "desc": res["desc"], "rng": seed_end}
    m["busy"] = 1                                  # one track: the projectile
    m["tracks"] = [res["desc"]]
    m["bodies"] = {s: (b.hp, bool(b.flags & EF_DYING), b.reactat if b.react else None, b.stf, b.st1)
                   for s, b in w.bodies.items()}
    return m


def compare(got, want):
    bad = []
    for k, v in want.items():
        if k == "tracks":
            g = got["tracks"][:len(v)]
            if g != v:
                bad.append((k, g, v))
        elif got[k] != v:
            bad.append((k, got[k], v))
    return bad


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

        # --- P0 static: pf_dhc_tab vs the doc columns ---
        sym, b3 = CT.load()
        tab = b3[sym["pf_dhc_tab"] - CT.BASE:sym["pf_dhc_tab"] - CT.BASE + 9]
        want = [dhc_doc(a) for a in range(9)]
        check("P0 pf_dhc_tab == doc type / NODEF / HEAL / effect per ability", list(tab) == want, (list(tab), want))

        p.boot(K_KNIGHT)
        tt_boot = p.rb("TURN_TICK")                  # P9: 0 throughout INPUT
        kt = p.kinds()
        hero0 = p.ent(0)
        hy, hx = hero0["Y"], 10
        solid = {T_BRICK}
        # sanity: the RNG port
        p.wmem(S["RNG_STATE"], w16(0x1234))
        assert p.code([0x0E, 20, 0xCD] + w16(S["rng_mod"]) + [0x32] + w16(RES))
        r = Rng(0x1234)
        check("P0 RNG model == rng_mod (one draw)", (p.rb(RES), p.rw("RNG_STATE")) == (r.mod(20), r.st))

        def world(hero_left=False, hero_x=hx, hero_res=(0, 0, 0), hero_hp=200):
            w = World(kt, hero_res)
            w.bodies[0] = Body(0, K_KNIGHT, hero_x, hy, hero_hp, 200,
                               EF_ACTIVE | EF_PLAYER | (EF_LEFT if hero_left else 0))
            return w

        def stand(kind):
            return hy + kt[K_KNIGHT]["bh"] - kt[kind]["bh"]      # same floor as the hero

        def run(tag, w, abl, rank, seed=0x2468, delay=3):
            """One cast on the emulator and the model; returns (bad, model result)."""
            p.setup(w, seed)
            rng = Rng(seed)
            res = w.fire(rng, 0, abl, rank, delay, solid)
            want = expect(w, res, rng.st)
            stop = p.fire(0, abl, rank, delay)
            got = p.result(w)
            bad = compare(got, want)
            if stop != res["stop"]:
                bad.append(("L", stop, res["stop"]))
            return bad, res

        allbad = []

        def case(tag, w, abl, rank, seed=0x2468, delay=3, must=None):
            bad, res = run(tag, w, abl, rank, seed, delay)
            if must is not None:
                ok = must(res, w)
                if not ok:
                    bad.append(("must", PFS_NAME[res["stop"]], res["col"], res["tgt"], res["lost"]))
            if bad:
                allbad.append((tag, bad))
            return res

        # --- P1 THE TABLE: every projectile row x rank -----------------------
        rows = [(a, r) for a in (SPARK, FIREBOLT, FROST, DRAINL, LIGHTNING) for r in (1, 2, 3)] + [(DAGGER, 1), (BOW, 1)]
        table_bad = []
        for abl, rank in rows:
            rg, die, bonus, bnc, eff = rank_row(abl, rank)
            d = ab(abl)
            front = hx + kt[K_KNIGHT]["bw"]             # first cell in front of the hero
            # a Rat whose first col is the range-th cell: struck (spell) / rolled (missile)
            for dist, hit_expected in ((rg, True), (rg + 1, False)):
                rx = front + dist - 1
                if rx + kt[K_RAT]["bw"] - 1 > 30:
                    hero_x = 30 - (kt[K_RAT]["bw"] - 1) - (dist - 1) - kt[K_KNIGHT]["bw"]
                else:
                    hero_x = hx
                if hero_x < 1:                           # Lightning 28: no room for a body
                    hero_x = 1                           # at the range edge; open corridor
                    rx = None
                else:
                    rx = hero_x + kt[K_KNIGHT]["bw"] + dist - 1
                for sd in (0x1357, 0xACE1, 0x0F0F, 0x7777):
                    w = world(hero_x=hero_x)
                    if rx is not None:
                        w.bodies[1] = Body(1, K_RAT, rx, stand(K_RAT), 200)
                    bad, res = run(f"P1 {ABL_NAMES[abl]} r{rank} d{dist}", w, abl, rank, sd)
                    if bad:
                        table_bad.append((ABL_NAMES[abl], rank, dist, hex(sd), bad))
                    segs = res["desc"][11:11 + res["desc"][10]]
                    if res["stop"] == PFS["RANGE"] and 1 + sum(segs) != rg:
                        table_bad.append(("range cells", ABL_NAMES[abl], rank, segs, rg))
                    if res["desc"][7] & 2 != (2 if d["speed"] == 16 else 0):
                        table_bad.append(("speed", ABL_NAMES[abl]))
                    if rx is None:
                        break                            # one open-corridor run per seed set
                    if rx is not None and hit_expected and d["flags"] & SPELLF:
                        if res["tgt"] != 1 or not (1 + bonus <= res["lost"] <= die + bonus):
                            table_bad.append(("spell must hit in range", ABL_NAMES[abl], rank, res["tgt"], res["lost"]))
                    if not hit_expected and res["tgt"] != NONE and not d["flags"] & PIERCEF:
                        table_bad.append(("out of range struck", ABL_NAMES[abl], rank))
                    if not hit_expected and bnc == 0 and res["stop"] != PFS["RANGE"]:
                        table_bad.append(("range end", ABL_NAMES[abl], rank, PFS_NAME[res["stop"]]))
        check(f"P1 game.md §6.1/§6.3 table: {len(rows)} rows x range edge x 4 seeds == model "
              "(range, 1dN+bonus, type, NODEF, F1, effects, FX)", not table_bad, table_bad[:6])

        # damage spread over many seeds: min / max == 1 + bonus / die + bonus (spells, N target)
        spread_bad = []
        for abl, rank in rows:
            if abl in (DAGGER, BOW):
                continue
            rg, die, bonus, bnc, eff = rank_row(abl, rank)
            seen = set()
            for i in range(40):
                w = world()
                kk = K_GOBLIN if abl != DRAINL else K_RAT      # (Goblin: N to every type)
                w.bodies[1] = Body(1, kk, hx + 6, stand(kk), 200)
                bad, res = run("spread", w, abl, rank, (0x0101 + 2671 * i) & 0xFFFF or 1)
                if bad:
                    spread_bad.append((ABL_NAMES[abl], rank, bad))
                seen.add(res["lost"])
            if min(seen) != 1 + bonus or max(seen) != die + bonus:
                spread_bad.append((ABL_NAMES[abl], rank, sorted(seen), (1 + bonus, die + bonus)))
        check("P1 spell damage 1dN + bonus spans [1 + bonus, N + bonus] over 40 seeds (every spell rank)",
              not spread_bad, spread_bad[:4])

        # --- P2 responses ---------------------------------------------------
        def two(kind, abl, x=hx + 6, hp=50, hero_res=(0, 0, 0)):
            w = world(hero_res=hero_res)
            w.bodies[1] = Body(1, kind, x, stand(kind) if not kt[kind]["fly"] else hy + 1, hp)
            return w
        case("P2 Spark on Bat (W)", two(K_BAT, SPARK), SPARK, 1,
                 must=lambda res, w: res["tgt"] == 1 and 4 <= res["lost"] <= 10)
        case("P2 Spark on Ghost (X): reflected onto the caster, no bounce used", two(K_GHOST, SPARK), SPARK, 1,
                 must=lambda res, w: res["tgt"] == 0 and res["stop"] == PFS["BODY"] and w.bodies[1].hp == 50)
        case("P2 Lightning on Ghost (X): pierce stops, reverses", two(K_GHOST, LIGHTNING), LIGHTNING, 1,
                 must=lambda res, w: w.bodies[1].hp == 50 and res["tgt"] == 0)
        case("P2 Frost on Skeleton (COLD I): stops, 0 dmg, no freeze", two(K_SKELETON, FROST), FROST, 1,
                 must=lambda res, w: res["tgt"] == 1 and res["lost"] == 0 and w.bodies[1].stf == 0)
        case("P2 Drain on Skeleton (I): no heal", two(K_SKELETON, DRAINL), DRAINL, 1,
                 must=lambda res, w: res["lost"] == 0)
        w = two(K_RAT, DRAINL)
        w.bodies[0].hp = 100
        case("P2 Drain on Rat: caster heals the HP lost", w, DRAINL, 1,
                 must=lambda res, w: w.bodies[0].hp == 100 + res["lost"] and res["lost"] >= 2)
        case("P2 Firebolt on Slime (W)", two(K_SLIME, FIREBOLT), FIREBOLT, 1,
                 must=lambda res, w: res["lost"] >= 6)
        case("P2 bow on Ghost (PHYS R)", two(K_GHOST, BOW), BOW, 1, seed=0x5A5A)
        case("P2 Spark confuses 1 in 4 (Goblin)", two(K_GOBLIN, SPARK), SPARK, 3, seed=0x4321)
        conf = 0
        for i in range(24):
            w = two(K_GOBLIN, SPARK, hp=200)
            res = case("P2 Spark confusion rate", w, SPARK, 1, seed=(0x0303 + 977 * i) & 0xFFFF)
            conf += w.bodies[1].stf == (2 << 2)
        check("P2 Spark CONFUSED 4 on some hits only (1 in 4): %d of 24" % conf, 0 < conf < 24)
        w = two(K_GOBLIN, FROST)
        case("P2 Frost freezes 2 (Goblin)", w, FROST, 1,
             must=lambda res, w: w.bodies[1].stf == FROZEN and w.bodies[1].st1 == 0x20)

        # --- P3 walls / bounces / point-blank --------------------------------
        w = world()
        w.row[hx + 3 + 4] = T_BRICK                  # wall 5 cells ahead
        case("P3 Spark, no bounce: stops on the free cell in front of the wall", w, SPARK, 1,
             must=lambda res, w: res["stop"] == PFS["WALL"] and res["col"] == hx + 3 + 3)
        w = world()
        w.row[hx + 3 + 4] = T_BRICK
        case("P3 Frost r1 bounces once and freezes the caster", w, FROST, 1,
             must=lambda res, w: res["tgt"] == 0 and w.bodies[0].stf == FROZEN and res["desc"][10] == 2)
        w = world()
        w.row[hx + 3] = T_BRICK                      # wall right in front
        case("P3 point-blank wall: impact-only FX on the caster's front col", w, SPARK, 1,
             must=lambda res, w: res["stop"] == PFS["WALL"] and res["desc"][0] == NONE and res["col"] == hx + 2)
        w = world()
        w.row[hx + 3] = T_BRICK
        case("P3 Firebolt r1 point-blank: the burst burns the caster", w, FIREBOLT, 1,
             must=lambda res, w: w.bodies[0].hp < 200)
        w = world()
        w.row[hx + 3] = T_BRICK
        case("P3 Firebolt r3 point-blank: RKE_SPARE spares the caster", w, FIREBOLT, 3,
             must=lambda res, w: w.bodies[0].hp == 200)
        w = world()
        w.row[hx + 3 + 6] = T_BRICK
        w.bodies[1] = Body(1, K_RAT, hx + 3 + 3, stand(K_RAT), 100)
        w.bodies[2] = Body(2, K_SLIME, hx + 3 + 7, stand(K_SLIME), 100)
        case("P3 Firebolt on a Rat: the struck body takes no burst; the Slime behind the wall col does",
             w, FIREBOLT, 2)
        w = world(hero_left=True, hero_x=20)
        w.row[20 - 6] = T_BRICK
        case("P3 facing left: wall, Frost r2 (2 bounces)", w, FROST, 2)

        # --- P4 loop guard --------------------------------------------------
        refl = [0, 0, 0]
        refl[0] = X << (2 * SHOCK)
        w = world(hero_res=refl)
        w.bodies[1] = Body(1, K_GHOST, hx + 4, hy + 1, 50)           # one free cell between them
        case("P4 loop guard: hero + Ghost both reflect SHOCK -> PFS_LOOP after 4 reversals", w, SPARK, 1,
             must=lambda res, w: res["stop"] == PFS["LOOP"] and res["desc"][10] == 5)
        w = world(hero_res=refl)
        w.bodies[1] = Body(1, K_GHOST, hx + 9, hy + 1, 50)
        case("P4 loop guard with Lightning (range 28)", w, LIGHTNING, 3,
             must=lambda res, w: res["stop"] == PFS["LOOP"])

        # --- P5 pierce --------------------------------------------------------
        w = world(hero_x=3)
        w.bodies[1] = Body(1, K_RAT, 10, stand(K_RAT), 200)
        w.bodies[2] = Body(2, K_GOBLIN, 16, stand(K_GOBLIN), 200)
        case("P5 Lightning r1: pierces both, bounces, hits again", w, LIGHTNING, 1,
             must=lambda res, w: w.bodies[1].hp < 200 and w.bodies[2].hp < 200)
        w = world(hero_x=3)
        w.bodies[1] = Body(1, K_RAT, 10, stand(K_RAT), 200)
        w.bodies[2] = Body(2, K_GHOST, 18, stand(K_GHOST), 200)
        case("P5 Lightning: a reflector ends the pass (reverses)", w, LIGHTNING, 2)
        w = world(hero_x=3)
        for s, x in ((1, 8), (2, 12), (3, 16), (4, 20)):
            w.bodies[s] = Body(s, K_RAT, x, stand(K_RAT), 3)
        case("P5 Lightning kills: dying bodies are skipped on later passes", w, LIGHTNING, 3)

        # --- P6 absorb / exit ------------------------------------------------
        w = world()
        w.bodies[1] = Body(1, K_GOBLIN, hx + 7, stand(K_GOBLIN) - 1, 50)      # feet off the floor: mid-ladder
        case("P6 mid-ladder Goblin absorbs harmlessly", w, SPARK, 1,
             must=lambda res, w: res["stop"] == PFS["ABSORB"] and w.bodies[1].hp == 50 and res["tgt"] == NONE)
        # D3-7 T4 (game.md §6 "no Firebolt burst" after an absorb): a Rat inside the
        # mid-ladder Goblin's burst radius takes nothing
        w = world()
        w.bodies[1] = Body(1, K_GOBLIN, hx + 7, stand(K_GOBLIN) - 1, 50)
        w.bodies[2] = Body(2, K_RAT, hx + 8, stand(K_RAT), 50)
        case("P6 Firebolt absorbed mid-ladder: no burst", w, FIREBOLT, 1,
             must=lambda res, w: res["stop"] == PFS["ABSORB"] and w.bodies[1].hp == 50 and w.bodies[2].hp == 50)
        # D3-7 T4 (game.md §6): Drain Life reflected onto its caster is a normal
        # DRAIN hit with no heal (a Ghost poked to reflect DRAIN in kx_tab)
        kxa = 3 * 16384 + S["kx_tab"] - 0xC000 + K_GHOST * 6
        p.z.cmd("set-memory-zone 0")
        kx_old = list(p.z.read_memory(kxa, 3))
        drx = list(kx_old)
        drx[1] = (drx[1] & ~3) | X                      # DRAIN (type 4): byte 1 bits 1-0
        p.wmem(kxa, drx)
        p.z.cmd("set-memory-zone -1")
        w = world(hero_hp=100)
        w.kx_over = {K_GHOST: drx}
        w.bodies[1] = Body(1, K_GHOST, hx + 5, hy + 1, 50)
        case("P6 Drain reflected onto the caster: hit, no heal", w, DRAINL, 1,
             must=lambda res, w: res["tgt"] == 0 and 0 < res["lost"] and w.bodies[0].hp == 100 - res["lost"])
        # D3-8f (game.md §6.4.1 B3): a Ghost poked to reflect COLD sends a rank-3
        # Frost Shard (FROZEN 4) back onto the hero: the self-freeze is 1 turn
        frx = list(kx_old)
        frx[0] = (frx[0] & ~(3 << (2 * COLD))) | (X << (2 * COLD))
        p.z.cmd("set-memory-zone 0")
        p.wmem(kxa, frx)
        p.z.cmd("set-memory-zone -1")
        w = world()
        w.kx_over = {K_GHOST: frx}
        w.bodies[1] = Body(1, K_GHOST, hx + 5, hy + 1, 50)
        case("P6 Ghost reflects rank-3 Frost onto the hero: FROZEN 1 (self-freeze), the Ghost unhurt", w, FROST, 3,
             must=lambda res, w: res["tgt"] == 0 and w.bodies[0].stf == FROZEN and w.bodies[0].st1 == 0x10
             and w.bodies[1].hp == 50)
        p.z.cmd("set-memory-zone 0")
        p.wmem(kxa, kx_old)
        p.z.cmd("set-memory-zone -1")
        w = world(hero_x=25)
        w.row[31] = T_AIR
        case("P6 open exit edge: enter col 31, no impact", w, LIGHTNING, 1,
             must=lambda res, w: res["stop"] == PFS["EXIT"] and res["col"] == 31 and res["desc"][2] == NONE)
        w = world(hero_left=True, hero_x=3)
        w.row[0] = T_AIR
        case("P6 open exit edge, facing left", w, BOW, 1)

        # --- P7 FX row --------------------------------------------------------
        w = world()
        w.bodies[1] = Body(1, K_RAT, hx + 6, stand(K_RAT), 50)
        case("P7 a Rat below the flight row: the FX flies at its top row", w, SPARK, 1,
             must=lambda res, w: res["desc"][6] == stand(K_RAT))

        check(f"P2-P7 rule cases == model ({len(allbad)} bad)", not allbad, allbad[:4])
        allbad.clear()

        # --- P8 fuzz ------------------------------------------------------------
        rnd = random.Random(0xD36B)
        abls = [(a, r) for a in (SPARK, FIREBOLT, FROST, DRAINL, LIGHTNING) for r in (1, 2, 3)] + [(DAGGER, 1), (BOW, 1)]
        stops = {}
        for i in range(120):
            hl = rnd.random() < 0.5
            hxr = rnd.randint(4, 24)
            hres = [0, 0, 0]
            if rnd.random() < 0.2:
                t = rnd.randrange(6)
                v = rnd.choice((R, I, X))
                hres[t // 4] |= v << (2 * (t % 4))
            w = world(hero_left=hl, hero_x=hxr, hero_res=hres, hero_hp=rnd.randint(5, 40))
            for c in range(1, 31):
                if rnd.random() < 0.07 and not hxr - 1 <= c <= hxr + 3:
                    w.row[c] = T_BRICK
            if rnd.random() < 0.3:
                w.row[0] = T_AIR
            if rnd.random() < 0.3:
                w.row[31] = T_AIR
            occ = set(range(hxr, hxr + 3))
            for s in range(1, rnd.randint(2, 6)):
                k = rnd.choice((K_RAT, K_BAT, K_GOBLIN, K_GHOST, K_SKELETON, K_SLIME))
                bw = kt[k]["bw"]
                for _ in range(20):
                    x = rnd.randint(1, 31 - bw)
                    if not occ & set(range(x, x + bw)):
                        break
                else:
                    continue
                occ |= set(range(x, x + bw))
                if kt[k]["fly"]:
                    y = rnd.randint(hy - 1, hy + 4)
                elif rnd.random() < 0.15:
                    y = stand(k) - rnd.randint(1, 3)         # mid-ladder
                else:
                    y = stand(k)
                w.bodies[s] = Body(s, k, x, y, rnd.randint(1, 30))
            abl, rank = rnd.choice(abls)
            res = case(f"P8 #{i}", w, abl, rank, seed=rnd.randrange(1, 65536), delay=rnd.randint(0, 6))
            stops[PFS_NAME[res["stop"]]] = stops.get(PFS_NAME[res["stop"]], 0) + 1
        check(f"P8 fuzz 120 random casts == model (stops {stops})", not allbad, allbad[:3])

        # --- P9 D3-7 T1: the split ability turn -------------------------------
        p9_bad = []
        p.setup(world(), 1)
        p.wb("TURN_TICK", 0)
        for tt in (5,):
            w = world(hero_x=3)
            w.turn_tick = tt
            w.bodies[1] = Body(1, K_RAT, 9, stand(K_RAT), 200)
            case(f"P9 Spark at TURN_TICK {tt}", w, SPARK, 1,
                 must=lambda res, w: res["itick"] > tt and w.bodies[1].reactat == res["itick"])
            w = world(hero_x=3)
            w.turn_tick = tt
            w.bodies[1] = Body(1, K_RAT, 10, stand(K_RAT), 200)
            w.bodies[2] = Body(2, K_GOBLIN, 16, stand(K_GOBLIN), 200)
            case(f"P9 Lightning pierce + bounce at TURN_TICK {tt}", w, LIGHTNING, 1, delay=0)
            w = world()
            w.turn_tick = tt
            w.row[hx + 3 + 6] = T_BRICK
            w.bodies[1] = Body(1, K_RAT, hx + 3 + 3, stand(K_RAT), 100)
            w.bodies[2] = Body(2, K_SLIME, hx + 3 + 7, stand(K_SLIME), 100)
            case(f"P9 Firebolt burst at TURN_TICK {tt}", w, FIREBOLT, 2, delay=0)
        # the same cast at TURN_TICK 0 and 5: E_REACTAT / pf_itick differ by 5
        got = []
        for tt in (0, 5):
            w = world(hero_x=3)
            w.turn_tick = tt
            w.bodies[1] = Body(1, K_RAT, 9, stand(K_RAT), 200)
            p.setup(w, 0x1111)
            p.fire(0, SPARK, 1, 2)
            got.append((p.rb("pf_itick"), p.rb(S["P_ENTITIES"] + STRIDE + E_REACTAT)))
        if got[1] != (got[0][0] + 5, got[0][1] + 5):
            p9_bad.append(("shift", got))
        p.wb("TURN_TICK", 0)
        # set_reaction_at: impact tick + TURN_TICK
        imp = p.rb(S["kind_seqs"] + S["KS_IMPACT"] + K_KNIGHT * S["KS_STRIDE"])
        for tt in (0, 3):
            p.setup(two(K_RAT, SPARK), 1)
            p.wb("TURN_TICK", tt)
            inner = ([0x21] + w16(S["P_ENTITIES"]) + [0x22] + w16(S["ATK_PTR"]) +
                     [0xDD, 0x21] + w16(S["P_ENTITIES"] + STRIDE) + [0x0E, S["RC_HURT"], 0xCD] + w16(S["set_reaction_at"]))
            assert p.code(p.bank3(inner)), "set_reaction_at stub"
            ra = p.rb(S["P_ENTITIES"] + STRIDE + E_REACTAT)
            if ra != imp + tt:
                p9_bad.append(("set_reaction_at", tt, ra, imp + tt))
        p.wb("TURN_TICK", 0)

        # act_begin / act_fire (bank 7 via far7): lead col guard
        bw = kt[K_KNIGHT]["bw"]
        pend = S["TURN_PEND"]

        def call7(label, a=0, b=0):
            """Bank-7 routine called with bank 7 paged (far7 does not pass B)."""
            p.wmem(pend, [0] * 4)
            inner = ([0xDD, 0x21] + w16(S["P_ENTITIES"]) + [0x3E, a, 0x06, b, 0xCD] + w16(S[label]) +
                     [0x7D, 0x32] + w16(RES))
            code = ([0x3A] + w16(S["PORT_7FFD_SHADOW"]) + [0xF5, 0x3E, S["BANK_COLD7"], 0xCD] + w16(S["page_bank"])
                    + inner + [0xF1, 0xCD] + w16(S["restore_page"]))
            assert p.code(code), label + " stub"
            return p.rb(RES), list(p.z.read_memory(pend, 4))

        for left, x, ok in ((True, 0, 0), (False, 31 - bw + 1, 0), (True, 1, 1), (False, 30 - bw + 1, 1)):
            p.setup(world(hero_left=left, hero_x=x), 1)
            l, blk = call7("act_begin", b=SPARK + 3)
            want = (ok, [3, SPARK + 3, 2, 3] if ok else [0, 0, 0, 0])
            if (l, blk) != want:
                p9_bad.append(("act_begin", left, x, (l, blk), want))
            l, _ = call7("act_fire", a=LIGHTNING)
            if l != ok:
                p9_bad.append(("act_fire guard", left, x, l, ok))
        if tt_boot != 0:
            p9_bad.append(("TURN_TICK after boot", tt_boot))
        if (S["TP_ACT"], S["TP_MON"], S["ACT_FIRE_TICK"]) != (1, 2, 2):
            p9_bad.append(("TP_* / ACT_FIRE_TICK", S["TP_ACT"], S["TP_MON"], S["ACT_FIRE_TICK"]))
        p.wmem(pend, [0] * 5)
        # FX_DROP: 3 tracks + 2 queued busy, a 6th descriptor is dropped and counted
        p.wb("FX_DROP", 0)
        p.setup(world(), 1)
        inner = [0xCD] + w16(S["fx_reset"])
        for i in range(6):
            inner += [0x21] + w16(S["pf_desc"]) + [0xCD] + w16(S["fx_start"])
        assert p.code(inner), "fx_start x6 stub"
        if p.rb("FX_DROP") != 1:
            p9_bad.append(("FX_DROP", p.rb("FX_DROP")))
        p.wb("FX_DROP", 0)
        assert p.code([0xCD] + w16(S["fx_reset"]))
        check(f"P9 D3-7 split turn: TURN_TICK shift (pf_itick / E_REACTAT / set_reaction_at), act_begin /"
              f" act_fire lead-col guard, FX_DROP ({len(allbad)} model / {len(p9_bad)} other bad)",
              not allbad and not p9_bad, (allbad[:3], p9_bad[:4]))

        # --- P10 D3-8 review 2: the adversarial PF_ROWF geometry ---------------
        def rowf_inv(w):
            """PF_ROWF after a cast: low bits = TF_SOLID | edge, count = the
            candidates not DONE (PFCF_DEAD ones stay DONE) covering the col."""
            rowf = list(p.z.read_memory(S["PF_ROWF"], 32))
            cand = list(p.z.read_memory(S["pf_cand"], 3 * 17 + 1))
            cnt, j = [0] * 32, 0
            while cand[j] != 0xFF:
                x0, x1, f = cand[j:j + 3]
                if not f & 0x40:
                    for c in range(x0, x1 + 1):
                        cnt[c] += 1
                j += 3
            return [(c, rowf[c], cnt[c]) for c in range(32)
                    if rowf[c] >> 3 != cnt[c] or rowf[c] & 7 != ((w.row[c] in solid) | (4 if c in (0, 31) else 0))]

        p10_bad = []
        # fuzz #208 (the reviewer's adversarial run, ROOM_CAP 4): Lightning r2 from
        # x 26 facing right, a Bat (HP 1) over the caster, a SHOCK-reflecting Ghost,
        # 2 Slimes; walls at cols 3 / 31 (+ 0): bounces + reflections walk the line
        # 4 times over the caster, 3 kills. tests/budget.py "advcast" = the real cast.
        w = World(kt, (0, 1, 0))
        w.bodies[0] = Body(0, K_KNIGHT, 26, hy, 40, 200, EF_ACTIVE | EF_PLAYER)
        for s, k, x, hp in ((1, K_BAT, 28, 1), (2, K_GHOST, 19, 6), (3, K_SLIME, 24, 6), (4, K_SLIME, 21, 23)):
            w.bodies[s] = Body(s, k, x, 15, hp, 30)
        w.row[3] = T_BRICK
        bad, res = run("P10 #208", w, LIGHTNING, 2, seed=8705, delay=2)
        t208 = p.tstates
        dead = sum(1 for s in range(1, 5) if w.bodies[s].flags & EF_DYING)
        p10_bad += bad + [("inv",) + i for i in rowf_inv(w)]
        if dead != 3 or res["stop"] != PFS["RANGE"]:
            p10_bad.append(("#208 shape", dead, PFS_NAME[res["stop"]]))
        # pf_cands' x1 guard: a body poked past col 31 (x 30, 3 wide) is clamped
        # to col 31 — no count lands past PF_ROWF's page end (= PF_RAM's start)
        w = world(hero_x=20)
        w.bodies[1] = Body(1, K_GOBLIN, 30, stand(K_GOBLIN), 50)
        w.row[31] = T_AIR
        bad, res = run("P10 x1 guard", w, LIGHTNING, 1)
        cand = list(p.z.read_memory(S["pf_cand"], 7))
        p10_bad += bad + [("inv",) + i for i in rowf_inv(w)]
        if cand[3:5] != [30, 31]:
            p10_bad.append(("x1 not clamped", cand[:7]))
        check(f"P10 adversarial: fuzz #208 (Lightning r2, reflecting Ghost + 2 Slimes + Bat over the caster,"
              f" 3 kills) == model, PF_ROWF invariant, {t208} T; pf_cands x1 clamp", not p10_bad, p10_bad[:4])

        # --- P11 D3-8e: the budget-fuzz geometries + the split cast ------------
        p11_bad, p11_t = [], {}

        def geo(hero, bodies, bricks, hres=(0, 0, 0)):
            """World from (x, left, hp) + [(slot, kind, x, y, hp)], flight row =
            air but the brick cols."""
            w = World(kt, hres)
            x, left, hp = hero
            w.bodies[0] = Body(0, K_KNIGHT, x, hy, hp, 200, EF_ACTIVE | EF_PLAYER | (EF_LEFT if left else 0))
            for s, k, bx, by, bhp in bodies:
                w.bodies[s] = Body(s, k, bx, by, bhp, max(bhp, 30))
            w.row = [T_BRICK if c in bricks else T_AIR for c in range(32)]
            return w

        # the re-review's 5-body fuzz worst casts (scratch adv2, NB 3..5, seeds
        # 0x444 #666 / 0x555 #678: 74.7k / 73.7k T then). 5 monsters: over
        # ROOM_CAP (4), so a model check only; the budget gate is "fzcast"
        FZ666 = ((7, True, 24), [(1, K_RAT, 5, 15, 6), (2, K_SKELETON, 0, 11, 11), (3, K_RAT, 12, 15, 12),
                                 (4, K_BAT, 0, 14, 18), (5, K_SLIME, 5, 15, 5)], (0, 14))
        FZ678 = ((1, True, 43), [(1, K_GOBLIN, 29, 11, 28), (2, K_RAT, 27, 15, 3), (3, K_GHOST, 9, 11, 1),
                                 (4, K_RAT, 0, 15, 1), (5, K_GOBLIN, 5, 13, 22)], (0, 31))
        for tag, g, rank, seed, delay in (("#666", FZ666, 1, 10267, 3), ("#678", FZ678, 3, 7378, 0)):
            w = geo(*g)
            bad, res = run("P11 " + tag, w, LIGHTNING, rank, seed=seed, delay=delay)
            p11_t[tag] = p.tstates
            p11_bad += [(tag,) + tuple(b) for b in bad] + [(tag, "inv") + i for i in rowf_inv(w)]
        # the ROOM_CAP-legal worst of a 2M-layout model search (box_free-disjoint
        # bodies, no ladder bodies, all 60 HP): tests/budget.py "fzcast" (the
        # real cast, render-heavy stack) and "fzcast2" mirror these
        FZC = ((23, True, 200), [(1, K_RAT, 26, 15, 60), (2, K_BAT, 20, 15, 60), (3, K_GHOST, 17, 16, 60),
                                 (4, K_BAT, 20, 10, 60)], (4, 27))
        FZC2 = ((18, False, 200), [(1, K_SLIME, 15, 15, 60), (2, K_BAT, 12, 14, 60), (3, K_GHOST, 21, 15, 60),
                                   (4, K_BAT, 14, 12, 60)], (12, 31))
        for tag, g, rank, seed in (("fzcast", FZC, 1, 44133), ("fzcast2", FZC2, 3, 18038)):
            w = geo(*g)
            bad, res = run("P11 " + tag, w, LIGHTNING, rank, seed=seed, delay=0)
            p11_t[tag] = p.tstates
            p11_bad += [(tag,) + tuple(b) for b in bad] + [(tag, "inv") + i for i in rowf_inv(w)]

        # the split cast (D3-8e): proj_pre on the input tick (TURN_TICK 0: the
        # set-up + PF_PRE_HITS strikes, E = ACT_FIRE_TICK), proj_rel on the fire
        # tick (TURN_TICK = ACT_FIRE_TICK: the rest + the FX) == the model's
        # one-shot cast at the fire tick (delay 0): same draws, HP, E_REACTAT,
        # pf_itick, descriptor. pf_part after the accept: PFP_MID (parked) for
        # 16 strikes, PFP_DONE for a short cast (its FX waits for the release)
        aft = S["ACT_FIRE_TICK"]

        def split(tag, w, abl, rank, seed, rel_abl=None, want_part=None):
            w.turn_tick = 0
            p.setup(w, seed)
            row = row_addr(abl, rank)
            assert p.code(p.bank3([0xCD] + w16(S["fx_reset"]) + [0xCD] + w16(S["build_live"]) +
                                  [0xDD, 0x21] + w16(S["P_ENTITIES"]) + [0x3E, abl, 0x11] + w16(row) +
                                  [0xCD] + w16(S["proj_pre"]))), tag + " proj_pre stub"
            t_pre = p.tstates
            part = p.rb("pf_part")
            if want_part is not None and part != want_part:
                p11_bad.append((tag, "pf_part", part, want_part))
            p.wb("TURN_TICK", aft)
            rel_abl = abl if rel_abl is None else rel_abl
            assert p.code(p.bank3([0xDD, 0x21] + w16(S["P_ENTITIES"]) + [0x3E, rel_abl, 0x11] +
                                  w16(row_addr(rel_abl, rank)) + [0xCD] + w16(S["proj_rel"]) +
                                  [0x7D, 0x32] + w16(RES) +            # pf_prep is bank-3 data:
                                  [0x3A] + w16(S["pf_prep"]) + [0x32] + w16(RES + 1))), tag + " proj_rel stub"
            w.turn_tick = aft
            rng = Rng(seed)
            res = w.fire(rng, 0, rel_abl, rank, 0, solid)
            want = expect(w, res, rng.st)
            bad = compare(p.result(w), want)
            if p.rb(RES) != res["stop"]:
                bad.append(("L", p.rb(RES), res["stop"]))
            if p.rb(RES + 1) != 0:                 # (read while bank 3 was paged)
                bad.append(("pf_prep not used up", p.rb(RES + 1)))
            p11_bad.extend((tag,) + tuple(b) for b in bad)
            p11_t[tag] = (t_pre, p.tstates)
            w.turn_tick = 0

        split("split fzcast", geo(*FZC), LIGHTNING, 1, 44133, want_part=S["PFP_MID"])
        split("split fzcast2", geo(*FZC2), LIGHTNING, 3, 18038, want_part=S["PFP_MID"])
        w = world(hero_x=hx)
        w.bodies[1] = Body(1, K_GOBLIN, hx + 5, stand(K_GOBLIN), 50)
        split("split short", w, SPARK, 1, 0x2468, want_part=S["PFP_DONE"])
        # a stale set-up (another ability) is never walked: proj_rel runs the
        # whole cast (Spark r1 set up with nothing in its range, Lightning released)
        w = world(hero_x=2)
        w.bodies[1] = Body(1, K_GOBLIN, 20, stand(K_GOBLIN), 50)
        split("split stale", w, SPARK, 1, 0x1357, rel_abl=LIGHTNING)
        p.wb("TURN_TICK", 0)
        check(f"P11 D3-8e: fuzz #666 / #678 (5 bodies) and the ROOM_CAP worst fzcast / fzcast2 == model +"
              f" PF_ROWF invariant ({p11_t}); the split cast (proj_pre at the accept, proj_rel at the fire tick)"
              f" == the one-shot model, pf_part parked / done, a stale set-up re-cast", not p11_bad, p11_bad[:4])

        print(f"proj3: worst cast {T.worst[0]} T ({T.worst[1]} r{T.worst[2]}; incl. ~3k T of stub: paging, fx_reset, build_live"
              "; deal_hit messages included)", flush=True)
        print(f"proj3: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
