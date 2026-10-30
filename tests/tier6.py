#!/usr/bin/env python3
"""3F-T6: tier abilities + gear wear (src/combat3.asm hooks, src/abil6.asm, tier6.asm drop rows).
Stub-driven on a booted Knight game (as tests/combat3.py).

  P1  parry rates over 3,000 seeded PHYS hits each: Skeleton Guard ~64/256, Skeleton Knight and
      Death Knight ~85/256; Skeleton / Goblin 0; a FIRE hit on a Guard never parries
  P2  a parry: L = 0, H = 1, HP unchanged; the Death Knight gets RC_PARRY (3F-T13bc), a Guard no reaction;
      P2b: RC_PARRY starts as the 1-tick ATTR_PARRY flash (anim_entity), no sequence
  P3  do_attack on a Guard: parried -> E_MSG MSG_P_PARRY, E_HIT 0, the line "THE BONEGUARD PARRIES!"
  W1  NOTCH: a melee parry 1 in 2 lowers the weapon m, WEAR_PEND = the line, hero_recalc NOT run
      yet (KT_BONUS unchanged); hunger_turn (end_turn) applies line + recalc + clears it;
      a shot parry never notches; m -3 -> destroyed, slot empty, fists, "YOUR WEAPON BREAKS!"
  W2  ACID (Black Widow bite, 1 in 4): armour m-1, else helmet, else nothing; destroyed at -3
  R1  rage: an Orc Berserker at hp <= max/2 hits at atk + 2
  M1  Mummy: a hit costs 5 FOOD (floor 0); a miss nothing
  X1  F_RESPAWN kill awards half XP (Skeleton Guard 9 -> 4)
  D1  tier food drops: Screech / Widow / Guard / Knight / Poltergeist drop a Carrot / Apple / Pear 1 in 4
Run: ZRCP_PORT=<port> python3 tests/tier6.py
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_SKELETON, K_GOBLIN  # noqa: E402
B7_LABELS = {"hunger_turn", "hunger_add", "trap_step", "trap_turn"}   # MEM-RECLAIM w2b: bank-7 cold code (far7), not R6
from proj3 import T as PT, w16  # noqa: E402
import textpack  # noqa: E402

STUB = S["LOWRAM_END_3B"]
RES = STUB + 200
STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE = 1, 2, 4
PHYS, FIRE = 0, 1
STRINGS = textpack.read_strings()
TXT = dict(STRINGS)
IMG = textpack.parse_emitted(os.path.join(HERE.parent, "build", "text", "strings.asm"))
WORN, BAG = S["WORN"], S["BAG"]
IT = {k[3:]: v for k, v in S.items() if k.startswith("IT_") and isinstance(v, int)}


def stream_text(raw):
    return textpack.expand(IMG, raw)   # w2d: the layout lives in textpack


class T(PT):
    def mon(self, slot, kind, hp, flags=0):
        self.set_ent(slot, KIND=kind, ROOM=self.rb("CUR_ROOM"), FLAGS=EF_ACTIVE | EF_HOSTILE | flags,
                     HP=hp, MAXHP=hp, REACT=0, HIT=0)
        self.wb(S["P_ENTITIES"] + slot * STRIDE + S["E_MSG"], 0)

    def emsg(self, slot):
        return self.rb(S["P_ENTITIES"] + slot * STRIDE + S["E_MSG"])

    def hero(self, hp=200):
        self.set_ent(0, HP=hp, MAXHP=hp, REACT=0, FLAGS=EF_ACTIVE | EF_PLAYER)

    def deal(self, att, tgt, dmg, flags, rtick=0):
        """-> (L, H)."""
        inner = ([0x3E, rtick, 0x32] + w16(S["dh_rtick"]) +
                 [0xDD, 0x21] + w16(S["P_ENTITIES"] + att * STRIDE) +
                 [0x3E, tgt, 0x06, dmg, 0x0E, flags, 0x1E, 0, 0xCD] + w16(S["deal_hit"]) +
                 [0x7D, 0x32] + w16(RES) + [0x7C, 0x32] + w16(RES + 1) +
                 [0xAF, 0x32] + w16(S["dh_rtick"]))
        assert self.code(self.bank3(inner)), "deal_hit stub did not return"
        return self.rb(RES), self.rb(RES + 1)

    def loop(self, tgt, flags, n, dmg=3):
        """n deal_hit calls hero -> tgt (its HP reset each); -> the number parried (H = 1)."""
        hp = S["P_ENTITIES"] + tgt * STRIDE + S["E_HP"]
        b = [0x21, 0, 0, 0x22] + w16(RES) + [0x21] + w16(n) + [0x22] + w16(RES + 2)
        top = len(b)
        b += [0x3E, 200, 0x32] + w16(hp) + [0xDD, 0x21] + w16(S["P_ENTITIES"]) + \
             [0x3E, tgt, 0x06, dmg, 0x0E, flags, 0x1E, 0, 0xCD] + w16(S["deal_hit"]) + \
             [0x5C, 0x16, 0, 0x2A] + w16(RES) + [0x19, 0x22] + w16(RES) + \
             [0x2A] + w16(RES + 2) + [0x2B, 0x22] + w16(RES + 2) + [0x7C, 0xB5]
        b += [0x20, (top - (len(b) + 2)) & 255]
        assert self.code(self.bank3(b), limit=200000000), "loop stub did not return"
        return self.rb(RES) | self.rb(RES + 1) << 8

    def attack(self, att, tgt):
        inner = [0xDD, 0x21] + w16(S["P_ENTITIES"] + att * STRIDE) + [0x3E, tgt, 0xCD] + w16(S["do_attack"])
        assert self.code(self.bank3(inner))

    def far6(self, label):                     # MEM-RECLAIM w2b: hunger_turn is bank 7 (far7)
        assert self.code([0x21] + w16(S[label]) + [0xCD] + w16(S["far7" if label in B7_LABELS else "far6"]))

    def hunger(self):
        self.far6("hunger_turn")

    def log_since(self, w0):
        wr0 = (w0[0] + w0[1]) % S["LOG_SLOTS"]
        wr1 = (self.rb(S["LOG_Q"] + S["LQ_RD"]) + self.rb("LOG_QN")) % S["LOG_SLOTS"]
        out = []
        for k in range((wr1 - wr0) % S["LOG_SLOTS"]):
            sl = (wr0 + k) % S["LOG_SLOTS"]
            out.append(stream_text(self.z.read_memory(S["LOG_TXT"] + sl * S["LOG_SLOT_LEN"], S["LOG_SLOT_LEN"])))
        return out

    def ring(self):
        return self.rb(S["LOG_Q"] + S["LQ_RD"]), self.rb("LOG_QN")


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:600]}", flush=True)

        p.boot(K_KNIGHT)
        for s_ in range(1, 16):
            p.set_ent(s_, FLAGS=0)
        p.wmem(WORN, [0] * 12)                                   # nothing worn: no notch noise
        p.wb("WEAR_PEND", 0)
        K = {n: S["K_" + n] for n in ("SKEL_GUARD", "SKEL_KNIGHT", "DKNIGHT", "BLACK_WIDOW", "MUMMY", "ORC_BERSERK",
                                       "SCREECH", "POLTERGEIST")}

        # --- P1 rates ---
        N = 3000
        p.hero()
        rate = {}
        for nm, kind in (("guard", K["SKEL_GUARD"]), ("knight", K["SKEL_KNIGHT"]), ("dk", K["DKNIGHT"]),
                         ("skeleton", K_SKELETON), ("goblin", K_GOBLIN)):
            p.mon(1, kind, 200)
            rate[nm] = p.loop(1, PHYS, N) / N
        p.mon(1, K["SKEL_GUARD"], 200)
        fire = p.loop(1, FIRE, 300)
        print("[info] parry rates", {k: round(v, 3) for k, v in rate.items()}, flush=True)
        check("P1 parry rates: Guard ~25%, Knight ~33%, Death Knight ~33%; none else; FIRE never",
              0.22 < rate["guard"] < 0.28 and 0.30 < rate["knight"] < 0.365 and 0.30 < rate["dk"] < 0.365
              and rate["skeleton"] == 0 and rate["goblin"] == 0 and fire == 0, (rate, fire))

        # --- P2 a parry ---
        def until_parry(kind, tries=60, rtick=0):
            for _ in range(tries):
                p.mon(1, kind, 100)
                p.hero()
                lh = p.deal(0, 1, 3, PHYS, rtick)
                if lh[1] == 1:
                    return lh
            return None
        lh = until_parry(K["DKNIGHT"])
        e = p.ent(1)
        check("P2 Death Knight parry: L 0, H 1, HP kept, RC_PARRY (3F-T13bc: no BLOCK frame)",
              lh == (0, 1) and e["HP"] == 100 and e["REACT"] == S["RC_PARRY"], (lh, e["HP"], e["REACT"]))
        # 3F-T13bc: the reaction starts (anim_entity .rest at E_REACTAT) as the 1-tick ATTR_PARRY flash,
        # no sequence: E_REACT -> 0, E_FLT = PARRY_FLASH, E_FLA = ATTR_PARRY, the body stays at rest
        p.set_ent(1, MODE=S["M_REST"], FLT=0, FLA=0)
        p.wb(S["P_ENTITIES"] + STRIDE + S["E_REACTAT"], 0)
        p.wb(S["TURN_PHASE"], 1)
        p.wb(S["TURN_TICK"], 0)
        p.wb(S["ANIM_SLOT"], 1)
        assert p.code([0xDD, 0x21] + w16(S["P_ENTITIES"] + STRIDE) + [0xCD] + w16(S["anim_entity"]))
        e = p.ent(1)
        p.wb(S["TURN_PHASE"], 0)
        check("P2b Death Knight parry reaction: flash ATTR_PARRY for PARRY_FLASH ticks, no sequence",
              (e["REACT"], e["FLT"], e["FLA"], e["MODE"]) == (0, S["PARRY_FLASH"], S["ATTR_PARRY"], S["M_REST"]),
              (e["REACT"], e["FLT"], e["FLA"], e["MODE"]))
        lh = until_parry(K["SKEL_GUARD"])
        e = p.ent(1)
        check("P2 Guard parry: L 0, H 1, HP kept, no BLOCK reaction",
              lh == (0, 1) and e["HP"] == 100 and e["REACT"] == 0, (lh, e["HP"], e["REACT"]))

        # --- P3 do_attack + the line ---
        got = None
        for _ in range(80):
            p.mon(1, K["SKEL_GUARD"], 100)
            p.hero()
            p.set_ent(0, HIT=0)
            p.wb(S["P_ENTITIES"] + S["E_MSG"], 0)
            p.attack(0, 1)
            if p.ent(1)["HP"] == 100 and p.emsg(0) == S["MSG_P_PARRY"]:
                got = True
                break
        w0 = p.ring()
        if got:
            assert p.code([0xDD, 0x21] + w16(S["P_ENTITIES"]) + [0xCD] + w16(S["show_impact_msg"]))
        lines = p.log_since(w0)
        check("P3 do_attack parried: E_MSG MSG_P_PARRY, E_HIT 0, line 'THE BONEGUARD PARRIES!'",
              got and p.ent(0)["HIT"] == 0 and lines == ["THE BONEGUARD" + TXT["cmb_parries"]],
              (got, lines, p.ent(0)["HIT"]))

        # --- W1 NOTCH ---
        def worn(slot, typ, m):
            p.wmem(WORN + 3 * slot, [typ, 1, (m & 7) << 5])

        def worn_m(slot):
            v = p.rb(WORN + 3 * slot + 2) >> 5
            return v - 8 if v > 3 else v
        worn(0, IT["W_LONG"], 2)
        p.far6("hero_recalc")
        bon0 = p.rb(S["kind_tab"] + S["KT_BONUS"] + K_KNIGHT)
        n_try = 0
        while p.rb("WEAR_PEND") == 0 and n_try < 400:
            until_parry(K["SKEL_KNIGHT"], 5)
            n_try += 1
        bon1 = p.rb(S["kind_tab"] + S["KT_BONUS"] + K_KNIGHT)
        pend = p.rb("WEAR_PEND")
        check("W1 melee parry notches 1 in 2: m 2 -> 1, WEAR_PEND bit 0, recalc NOT yet run",
              worn_m(0) == 1 and pend == 1 and bon1 == bon0, (worn_m(0), pend, bon0, bon1))
        w0 = p.ring()
        p.hunger()
        bon2 = p.rb(S["kind_tab"] + S["KT_BONUS"] + K_KNIGHT)
        check("W1 hunger_turn (end_turn) applies it: the line, hero_recalc (bonus -1), WEAR_PEND 0",
              p.log_since(w0) == [TXT["cmb_notch"]] and p.rb("WEAR_PEND") == 0 and bon2 == bon1 - 1,
              (p.log_since(w0), p.rb("WEAR_PEND"), bon1, bon2))
        worn(0, IT["W_LONG"], 2)
        for _ in range(40):
            until_parry(K["SKEL_KNIGHT"], 5, rtick=4)
        check("W1 a shot / thrown parry never notches", p.rb("WEAR_PEND") == 0 and worn_m(0) == 2,
              (p.rb("WEAR_PEND"), worn_m(0)))
        worn(0, IT["W_LONG"], -3)
        n_try = 0
        while p.rb("WEAR_PEND") == 0 and n_try < 400:
            until_parry(K["SKEL_KNIGHT"], 5)
            n_try += 1
        pend_brk = p.rb("WEAR_PEND")
        slot = list(p.z.read_memory(WORN, 3))
        w0 = p.ring()
        p.hunger()
        die = p.rb(S["kind_tab"] + S["KT_DIE"] + K_KNIGHT)
        check("W1 m -3 + notch: destroyed (slot empty), 'YOUR WEAPON BREAKS!', fists (1d2)",
              slot == [0, 0, 0] and pend_brk == 2 and p.log_since(w0) == [TXT["cmb_wpn_breaks"]] and die == 2,
              (slot, p.log_since(w0), die))

        # --- W2 ACID ---
        def acid_run(setup, n=400):
            hits = 0
            for _ in range(n):
                setup()
                p.wb("WEAR_PEND", 0)
                p.far6("acid6")
                hits += p.rb("WEAR_PEND") != 0
            return hits

        def arm_only():
            p.wmem(WORN, [0] * 12)
            worn(1, IT["A_CHAIN"], 0)
        hits = acid_run(arm_only)
        check("W2 acid 1 in 4 over 400 bites; armour m-1; line ACID EATS YOUR ARMOUR", 70 < hits < 130
              and (worn_m(1) == -1) == (p.rb("WEAR_PEND") == 4) and p.rb("WEAR_PEND") in (0, 4),
              (hits, worn_m(1), p.rb("WEAR_PEND")))
        p.wmem(WORN, [0] * 12)
        worn(2, IT["H_HELM"], 0)
        for _ in range(60):
            p.far6("acid6")
        check("W2 no armour: the helmet takes it (m < 0 or destroyed)", worn_m(2) < 0 or p.rb(WORN + 6) == 0,
              (worn_m(2), p.rb(WORN + 6)))
        p.wmem(WORN, [0] * 12)
        p.wb("WEAR_PEND", 0)
        for _ in range(60):
            p.far6("acid6")
        check("W2 nothing worn: nothing happens", p.rb("WEAR_PEND") == 0)
        worn(1, IT["A_CHAIN"], -3)
        for _ in range(60):
            if p.rb(WORN + 3) == 0:
                break
            p.far6("acid6")
        check("W2 armour at m -3: destroyed, 'YOUR ARMOUR FALLS APART!'",
              p.rb(WORN + 3) == 0 and p.rb("WEAR_PEND") == 8, (p.rb(WORN + 3), p.rb("WEAR_PEND")))
        p.wb("WEAR_PEND", 0)
        p.wmem(WORN, [0] * 12)


        # --- H1 a held target cannot parry (game.md §6.4) ---
        p.hero()
        held = {}
        for nm, hv in (("stunned", S["HOLD_STUNNED"]), ("frozen", S["HOLD_FROZEN"])):
            p.mon(1, K["SKEL_KNIGHT"], 200)
            p.wb(S["ST_FLAGS"] + 1, hv)
            held[nm] = p.loop(1, PHYS, 600)
            p.wb(S["ST_FLAGS"] + 1, 0)
        held["asleep"] = 0                       # (a hit wakes a sleeper: re-poked before each of 300 hits)
        for _ in range(300):
            p.mon(1, K["SKEL_KNIGHT"], 200)
            p.wb(S["ST_FLAGS"] + 1, S["HOLD_ASLEEP"])
            held["asleep"] += p.deal(0, 1, 3, PHYS)[1]
        p.wb(S["ST_FLAGS"] + 1, 0)
        p.mon(1, K["SKEL_KNIGHT"], 200)
        p.wb(S["ST_FLAGS"] + 1, 0)
        free = p.loop(1, PHYS, 600) / 600
        check("H1 STUNNED / FROZEN / ASLEEP Knight never parries over 600 hits; unheld still ~1 in 3",
              held == {"stunned": 0, "frozen": 0, "asleep": 0} and 0.28 < free < 0.40, (held, free))

        # --- S1 a parried shot: pf_strike stores pf_lost = $FF (ammo_fire prints the PARRIES line) ---
        def strike(kind):
            p.mon(1, kind, 100)
            p.hero()
            for nm, v in (("pf_aflg", S["ABF_SPELL"]), ("pf_fxrow", 1), ("pf_mnext", 1), ("pf_tb", 1), ("pf_bonus", 2),
                          ("pf_dhc", 0), ("pf_cslot", 0), ("pf_eff", 0), ("pf_tgt", 255), ("pf_slim", 127),
                          ("pf_lost", 0)):
                p.wb(nm, v)
            p.wmem(S["pf_dmc"], [3, 3])
            assert p.code(p.bank3([0xDD, 0x21] + w16(S["P_ENTITIES"]) + [0x3E, 1, 0xCD] + w16(S["pf_strike"])))
            return p.rb("pf_lost"), p.ent(1)["HP"]
        res = [strike(K["SKEL_GUARD"]) for _ in range(60)]
        par = [r for r in res if r[0] == 255]
        lost = [r for r in res if r[0] != 255]
        check("S1 shot at a Guard: parried -> pf_lost $FF, HP kept, no notch; else pf_lost = the HP lost",
              par and all(r[1] == 100 for r in par) and lost and all(r[0] == 100 - r[1] and 0 < r[0] < 10 for r in lost)
              and p.rb("WEAR_PEND") == 0, (res[:8], p.rb("WEAR_PEND")))
        g = [strike(K_GOBLIN) for _ in range(10)]
        check("S1 a Goblin never parries: pf_lost = the HP lost", all(r[0] == 100 - r[1] and 0 < r[0] < 10 for r in g), g)

        # --- W3 two wear events in one turn: both apply, both cells redrawn, the break line is kept ---
        import game_lib
        p.wmem(WORN, [0] * 12)
        worn(0, IT["W_LONG"], -3)
        worn(1, IT["A_CHAIN"], 0)
        p.wb("WEAR_PEND", 0)
        n_try = 0
        while not (p.rb("WEAR_PEND") & 2) and n_try < 400:
            until_parry(K["SKEL_KNIGHT"], 5)
            n_try += 1
        n_try = 0
        while not (p.rb("WEAR_PEND") & 4) and n_try < 400:
            p.far6("acid6")
            n_try += 1
        pend = p.rb("WEAR_PEND")
        p.wb("LOG_QN", 0)                        # the earlier tests' queued lines (a full ring drops new ones)
        w0 = p.ring()
        p.hunger()
        lines3 = p.log_since(w0)
        fr = p.composed_frame()
        ph = S["ICONS16_PH"]
        cell_ok = True
        for slot, ix in ((0, ph + 0), (1, S["IT_A_CHAIN"] - S["IT_BAG_LO"])):
            col = S["GEAR_COL"] + 2 * slot
            for (dc, dr), want in game_lib.icon16_cells(ix).items():
                cell_ok &= game_lib.cell_bytes(fr, col + dc, S["LOG_ROW"] + dr) == want
        check("W3 weapon broke + armour acid in one turn: both bits, both lines (break kept), weapon cell = placeholder, "
              "armour cell redrawn, armour m -1, WEAR_PEND 0",
              pend & 6 == 6 and lines3 == [TXT["cmb_wpn_breaks"], TXT["cmb_acid_arm"]]
              and p.rb(WORN) == 0 and worn_m(1) == -1 and p.rb("WEAR_PEND") == 0 and cell_ok,
              (pend, lines3, worn_m(1), cell_ok))
        p.wmem(WORN, [0] * 12)

        # --- N1 a negative weapon bonus lowers the damage (min 1); m >= 0 unchanged ---
        worn_dmg = {}
        for m in (2, 0, -1, -2):
            worn(0, IT["W_LONG"], m)
            p.far6("hero_recalc")
            die = p.rb(S["kind_tab"] + S["KT_DIE"] + K_KNIGHT)
            seen = set()
            for _ in range(60):
                p.mon(1, K_GOBLIN, 100)
                p.hero()
                p.set_ent(0, FLAGS=EF_ACTIVE | EF_PLAYER)
                p.set_ent(1, ROOM=p.rb("CUR_ROOM"))
                p.wmem(S["P_ENTITIES"] + STRIDE * 1 + S["E_HP"], [100])
                for _t in range(1):
                    p.attack(0, 1)
                seen.add(100 - p.ent(1)["HP"])
            worn_dmg[m] = (die, min(seen - {0}), max(seen))
        d0 = worn_dmg[0]
        check("N1 weapon m: dmg = max(1, 1dN + m): +2 -> [3, N+2], 0 -> [1, N], -1 -> [1, N-1], -2 -> [1, N-2]",
              worn_dmg[2][1:] == (3, d0[0] + 2) and d0[1:] == (1, d0[0]) and worn_dmg[-1][1:] == (1, d0[0] - 1)
              and worn_dmg[-2][1:] == (1, d0[0] - 2), worn_dmg)
        p.wmem(WORN, [0] * 12)
        p.far6("hero_recalc")

        # --- R1 rage ---
        p.hero()
        katk = p.rb(S["kind_tab"] + S["KT_ATK"] + K["ORC_BERSERK"])
        keva = p.rb(S["kind_tab"] + S["KT_EVA"] + K_KNIGHT)
        bad = []
        for hp, mx in ((18, 18), (10, 18), (9, 18), (9, 19), (5, 19), (1, 18)):
            rage = 2 * hp <= mx
            for sd in range(1, 41):
                seed = (sd * 977) & 0xFFFF or 1
                p.mon(1, K["ORC_BERSERK"], hp)
                p.set_ent(1, MAXHP=mx)
                p.wmem(S["RNG_STATE"], w16(seed))
                assert p.code(p.bank3([0xDD, 0x21] + w16(S["P_ENTITIES"] + STRIDE) + [0x3E, 0, 0x06, 0, 0xCD] +
                                      w16(S["hit_roll"]) + [0x32] + w16(RES)))
                hit = p.rb(RES)
                p.wmem(S["RNG_STATE"], w16(seed))
                assert p.code([0x0E, 20, 0xCD] + w16(S["rng_mod"]) + [0x32] + w16(RES))
                d20 = p.rb(RES) + 1
                if bool(hit) != (d20 + katk + (2 if rage else 0) >= 10 + keva):
                    bad.append((hp, mx, sd))
        check("R1 rage: Berserker hit_roll = d20 + atk (+2 at hp <= max/2) >= 10 + eva, 240 rolls", not bad, bad[:5])

        # --- M1 Mummy ---
        res = []
        for _ in range(60):
            p.mon(1, K["MUMMY"], 100)
            p.hero()
            p.wb("FOOD", 100)
            p.attack(1, 0)
            res.append((p.ent(1)["HIT"], p.rb("FOOD")))
        check("M1 Mummy: every hit costs 5 FOOD, a miss nothing (60 swings)",
              any(r[0] for r in res) and any(not r[0] for r in res)
              and all(r[1] == (95 if r[0] else 100) for r in res), res[:8])
        p.wb("FOOD", 3)
        for _ in range(40):
            p.mon(1, K["MUMMY"], 100)
            p.hero()
            p.attack(1, 0)
            if p.ent(1)["HIT"]:
                break
        check("M1 FOOD floors at 0", p.rb("FOOD") == 0, p.rb("FOOD"))

        # --- X1 half XP ---
        xp = []
        for fl in (0, S["EF_RESPAWN"]):
            p.wmem(S["XP"], [0, 0])
            p.hero()
            p.mon(1, K["SKEL_GUARD"], 1, flags=fl)
            p.deal(0, 1, 9, FIRE)
            xp.append(p.rw("XP"))
        check("X1 Skeleton Guard kill: 9 XP, F_RESPAWN 4", xp == [9, 4], xp)

        # --- D1 tier food drops ---
        FL, FLS = S["FLOOR_LIST"], S["FL_STRIDE"]
        ty = {}
        for nm in ("SCREECH", "BLACK_WIDOW", "SKEL_GUARD", "SKEL_KNIGHT", "POLTERGEIST"):
            foods = 0
            seen = set()
            for _ in range(120):
                p.wmem(FL, [S["FL_EMPTY"]] * (S["FLOOR_MAX"] * FLS))
                p.hero()
                p.mon(1, K[nm], 1)
                p.set_ent(1, X=18, Y=p.ent(0)["Y"])
                p.deal(0, 1, 9, FIRE)
                es = [list(p.z.read_memory(FL + i * FLS, FLS)) for i in range(S["FLOOR_MAX"])]
                for en in es:
                    if en[0] != S["FL_EMPTY"]:
                        seen.add(en[2])
                        foods += 1
            ty[nm] = (foods, sorted(seen))
        ok = all(15 < f < 48 and set(t) <= {IT["F_CARROT"], IT["F_APPLE"], IT["F_PEAR"]} and len(t) >= 2
                 for f, t in ty.values())
        check("D1 tier rows drop a random Carrot/Apple/Pear ~1 in 4 (120 kills each)", ok, ty)

        print(f"tier6: {len(fails)} failed" + (f": {fails}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
