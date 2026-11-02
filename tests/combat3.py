#!/usr/bin/env python3
"""D3-6a: the shared combat core (src/combat3.asm) — hit_roll / deal_hit unit
cases, run as stubs at LOWRAM_END_3B (bank 3 paged by the stub) on a booted
Knight game (PROTO room A, every monster parked). Rules: game.md §4.1 (XP),
§6.0 (responses), §6.4 (effects), §7 (F1, damage), §11.4 (hero DEF).

  C1  response matrix on the hero (HERO_RES poked): every type x N/R/I/X/W,
      dmg 6 and 1 (R min 1); I/X lose 0 and change nothing
  C2  kx_tab rows on monsters: Ghost PHYS R, Ghost COLD I, Bat SHOCK W,
      Slime FIRE W, Rat N
  C3  hero DEF 1: PHYS - DEF min 1, DH_NODEF and non-PHYS types ignore it
  C4  saturation: lost = the HP left, EF_DYING + RC_DEATH; a 0-HP target: 0
  C5  DH_HEAL heals the attacker by the HP lost (cap max); an I target / no flag: 0
  C6  FIRE thaws FROZEN, COLD does not; any HP loss wakes ASLEEP
  C7  effect apply: HOLD / MIND / POISON / WEAK fields, same effect = max,
      group overwrite, groups independent, R halves (1 -> none), immunity
      mask, HOLD_GUARD, kill -> no effect + status cleared, chance 1 in 1
  C8  XP: kill awards KXP, EF_RESPAWN KXP/2 min 1, XP_MAX saturation,
      XP_UP set; the hero's death awards nothing
  C9  hit_roll == d20 + atk + mod >= 10 + eva (d20 drawn from the same seed),
      held target: eva 0
  C10 do_attack (real melee): Ghost touch on the Mage — DRAIN 1d4, no
      heal (§9.1: only the Vampire's bite heals), CONFUSED 4 on some hits only
Run: ZRCP_PORT=<port> python3 tests/combat3.py
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from game_lib import Harness, Proto, S, EMU_ARGS, K_KNIGHT, K_WIZARD, K_GHOST, K_RAT, K_BAT, K_SLIME, K_SKELETON  # noqa: E402

STUB = S["LOWRAM_END_3B"]
RES = STUB + 200
STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_DYING = 1, 2, 4, 16
EF_RESPAWN = S["EF_RESPAWN"]
RC_HURT, RC_DEATH = S["RC_HURT"], S["RC_DEATH"]
PHYS, FIRE, COLD, SHOCK, DRAIN, DARK = range(6)
N, R, I, X, W = 0, 1, 2, 3, 4
NODEF = S["DH_NODEF"]
HEAL = S["DH_HEAL"]
EFS = S["DH_EFX_SHIFT"]
FROZEN, ASLEEP, STUNNED, FEAR, CONFUSED, POISON, WEAK = range(1, 8)
STF, ST1, ST2, STX = S["ST_FLAGS"], S["ST_T1"], S["ST_T2"], S["ST_X"]


def w16(v):
    return [v & 255, v >> 8]


def res_bytes(t, r):
    """3-B RES record with response r for type t, N elsewhere."""
    b = [0, 0, 0]
    if r == W:
        b[2] = 1 << t
    else:
        b[t // 4] = r << (2 * (t % 4))
    return b


class T(Proto):
    def code(self, body, limit=20000000):
        code = bytes([0xF3, 0x31] + w16(S["WORKSTORE_TOP"]) + body + [0x00, 0x18, 0xFE])
        end = STUB + len(code) - 3
        assert STUB + len(code) <= RES
        self.wmem(STUB, code)
        self.z.cmd("set-breakpoint 3 PC=%d" % end)
        self.extra_probes = {end}
        self.z.cmd("set-register PC=%d" % STUB)
        self.z.cmd("run %d" % limit)
        ok = self.pc() == end
        self.z.cmd("set-breakpoint 3")
        self.extra_probes = set()
        return ok

    def wmem(self, addr, data):
        self.z.cmd("write-memory %d %s" % (addr, " ".join(str(b) for b in data)))

    def bank3(self, inner):
        """push shadow, page bank 3, inner, restore."""
        return ([0x3A] + w16(S["PORT_7FFD_SHADOW"]) + [0xF5, 0x3E, S["BANK_COLD3"], 0xCD] + w16(S["page_bank"])
                + inner + [0xF1, 0xCD] + w16(S["restore_page"]))

    def deal(self, att, tgt, dmg, flags, eff=0):
        inner = ([0xDD, 0x21] + w16(S["P_ENTITIES"] + att * STRIDE) +
                 [0x3E, tgt, 0x06, dmg, 0x0E, flags, 0x1E, eff, 0xCD] + w16(S["deal_hit"]) +
                 [0x7D, 0x32] + w16(RES))
        assert self.code(self.bank3(inner)), "deal_hit stub did not return"
        return self.rb(RES)

    def roll(self, att, tgt, mod):
        """-> (hit_roll A, d20 from the same seed)."""
        seed = self.rw("RNG_STATE")
        inner = ([0xDD, 0x21] + w16(S["P_ENTITIES"] + att * STRIDE) +
                 [0x3E, tgt, 0x06, mod & 255, 0xCD] + w16(S["hit_roll"]) + [0x32] + w16(RES))
        assert self.code(self.bank3(inner))
        hit = self.rb(RES)
        self.wmem(S["RNG_STATE"], w16(seed))
        assert self.code([0x0E, 20, 0xCD] + w16(S["rng_mod"]) + [0x32] + w16(RES))
        return hit, self.rb(RES) + 1

    def attack(self, att, tgt):
        inner = [0xDD, 0x21] + w16(S["P_ENTITIES"] + att * STRIDE) + [0x3E, tgt, 0xCD] + w16(S["do_attack"])
        assert self.code(self.bank3(inner))

    def mon(self, slot, kind, hp, maxhp=None, flags=0):
        self.set_ent(slot, KIND=kind, ROOM=self.rb("CUR_ROOM"), FLAGS=EF_ACTIVE | EF_HOSTILE | flags,
                     HP=hp, MAXHP=maxhp or hp, REACT=0)

    def hero(self, hp=40, maxhp=60, res=(0, 0, 0), imm=0, deff=0):
        self.set_ent(0, HP=hp, MAXHP=maxhp, REACT=0, FLAGS=EF_ACTIVE | EF_PLAYER)
        self.wmem(S["HERO_RES"], list(res))
        self.wb("HERO_IMM", imm)
        self.wb("HERO_DEF", deff)

    def st(self, slot, f=0, t1=0, t2=0):
        self.wb(STF + slot, f)
        self.wb(ST1 + slot, t1)
        self.wb(ST2 + slot, t2 & 255)
        self.wb(STX + slot, t2 >> 8)               # POIS1: the third field = ST_T2 | ST_X << 8

    def gst(self, slot):
        return self.rb(STF + slot), self.rb(ST1 + slot), self.rb(ST2 + slot) | self.rb(STX + slot) << 8


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

        p.boot(K_KNIGHT)
        room = p.rb("CUR_ROOM")
        for s_ in range(1, 16):
            p.set_ent(s_, FLAGS=0)
        check("C0 hero_st_init: Warrior HERO_DEF = 1 (Leather)", p.rb("HERO_DEF") == 1, p.rb("HERO_DEF"))

        # --- C1 response matrix on the hero (attacker = a Rat, slot 1) ---
        bad = []
        for t in range(6):
            for r, want6, want1 in ((N, 6, 1), (R, 3, 1), (I, 0, 0), (X, 0, 0), (W, 12, 2)):
                for dmg, want in ((6, want6), (1, want1)):
                    p.mon(1, K_RAT, 3)
                    p.hero(res=res_bytes(t, r))
                    p.st(0)
                    lost = p.deal(1, 0, dmg, t)
                    e = p.ent(0)
                    if lost != want or e["HP"] != 40 - want or (want == 0 and e["REACT"] != 0):
                        bad.append((t, r, dmg, lost, e["HP"], e["REACT"]))
        check("C1 response matrix (6 types x N/R/I/X/W, dmg 6 and 1)", not bad, bad)

        # --- C2 real kx_tab rows (hero attacks slot 1) ---
        p.hero()
        cases = [(K_GHOST, PHYS, 5, 2), (K_GHOST, COLD, 5, 2), (K_BAT, SHOCK, 3, 6),
                 (K_SLIME, FIRE, 4, 8), (K_SLIME, PHYS, 1, 1), (K_RAT, PHYS, 2, 2), (K_SKELETON, DRAIN, 4, 0)]
        bad = []
        for k, t, dmg, want in cases:
            p.mon(1, k, 20)
            lost = p.deal(0, 1, dmg, t)
            if lost != want or p.ent(1)["HP"] != 20 - want:
                bad.append((k, t, dmg, lost))
        check("C2 kx_tab responses: Ghost PHYS R / COLD R (BAL-1 FINAL B), Bat SHOCK W, Slime FIRE W, Rat N, Skeleton DRAIN I", not bad, bad)

        # --- C3 hero DEF ---
        bad = []
        for dmg, flags, want in ((4, PHYS, 3), (1, PHYS, 1), (2, PHYS, 1), (4, PHYS | NODEF, 4),
                                 (4, FIRE, 4), (4, DRAIN, 4), (4, DARK, 4)):
            p.mon(1, K_RAT, 3)
            p.hero(deff=1)
            lost = p.deal(1, 0, dmg, flags)
            if lost != want:
                bad.append((dmg, flags, lost))
        p.mon(1, K_RAT, 3)
        p.hero(deff=1, res=res_bytes(PHYS, R))
        l2 = p.deal(1, 0, 6, PHYS)                       # 6/2 = 3, - 1 = 2
        check("C3 hero DEF 1: PHYS - DEF min 1; NODEF / non-PHYS ignore it; R then DEF",
              not bad and l2 == 2, (bad, l2))

        # --- C4 saturation / kill / 0-HP target ---
        p.hero()
        p.mon(1, K_RAT, 3)
        lost = p.deal(0, 1, 9, PHYS)
        e = p.ent(1)
        check("C4 overkill: lost = HP left (3), HP 0, EF_DYING, RC_DEATH",
              (lost, e["HP"], bool(e["FLAGS"] & EF_DYING), e["REACT"]) == (3, 0, True, RC_DEATH), (lost, e))
        lost = p.deal(0, 1, 5, PHYS)
        check("C4 a target already at 0 HP: lost 0", lost == 0, lost)
        p.mon(1, K_RAT, 5)
        lost = p.deal(0, 1, 2, PHYS)
        check("C4 non-lethal: RC_HURT, HP 3", (lost, p.ent(1)["HP"], p.ent(1)["REACT"]) == (2, 3, RC_HURT), p.ent(1))

        # --- C5 drain heal ---
        p.mon(1, K_GHOST, 3, 8)
        p.hero()
        lost = p.deal(1, 0, 4, DRAIN | HEAL)
        g1 = p.ent(1)["HP"]
        p.mon(1, K_GHOST, 3, 8)
        p.hero()
        p.deal(1, 0, 9, DRAIN | HEAL)
        g2 = p.ent(1)["HP"]
        p.hero(hp=10, maxhp=24)
        p.mon(1, K_RAT, 3)
        p.deal(0, 1, 6, DRAIN | HEAL)                    # lost 3 (rat's HP) -> hero 13
        h3 = p.ent(0)["HP"]
        p.hero(hp=10, maxhp=24)
        p.mon(1, K_SKELETON, 10)
        p.deal(0, 1, 6, DRAIN | HEAL)                    # skeleton DRAIN I
        h4 = p.ent(0)["HP"]
        p.mon(1, K_GHOST, 3, 8)
        p.hero()
        p.deal(1, 0, 4, DRAIN)                           # no DH_HEAL: no heal
        g5 = p.ent(1)["HP"]
        check("C5 DH_HEAL: the attacker heals the HP lost, capped at max; I heals nothing; no flag no heal",
              (lost, g1, g2, h3, h4, g5) == (4, 7, 8, 13, 10, 3), (lost, g1, g2, h3, h4, g5))

        # --- C6 thaw / wake (monster slot 1) ---
        p.hero()
        p.mon(1, K_RAT, 9)
        p.st(1, FROZEN, 0x20)
        p.deal(0, 1, 1, FIRE)
        a = p.gst(1)
        p.mon(1, K_RAT, 9)
        p.st(1, FROZEN, 0x23)
        p.deal(0, 1, 1, COLD)
        b = p.gst(1)
        p.mon(1, K_RAT, 9)
        p.st(1, ASLEEP | (2 << 2), 0x52)                 # asleep + confused
        p.deal(0, 1, 1, SHOCK)
        c = p.gst(1)
        p.hero()
        p.st(0, ASLEEP, 0x80)
        p.mon(1, K_RAT, 3)
        p.deal(1, 0, 1, PHYS)
        d = p.gst(0)
        check("C6 FIRE thaws FROZEN (sets HOLD_GUARD); COLD keeps it; any HP loss wakes ASLEEP (MIND kept)",
              a[:2] == (0x40, 0) and b[:2] == (FROZEN, 0x23) and c[:2] == (2 << 2, 0x02) and d[:2] == (0, 0),
              (a, b, c, d))

        # --- C7 effect apply (hero target, attacker Rat) ---
        def eff(efx, turns, chance=0, t=PHYS, res=(0, 0, 0), imm=0, hp=40, st=None):
            p.hero(hp=hp, res=res, imm=imm)
            if st is not None:
                p.st(0, *st)
            p.mon(1, K_RAT, 3)
            p.deal(1, 0, 1, t | (efx << EFS), (chance << 4) | turns)
            return p.gst(0)

        r = []
        r.append(("confused 3", eff(CONFUSED, 3, st=(0, 0, 0)), (2 << 2, 0x03, 0)))
        r.append(("refresh 2 keeps 3", eff(CONFUSED, 2), (2 << 2, 0x03, 0)))
        r.append(("refresh 5 -> 5", eff(CONFUSED, 5), (2 << 2, 0x05, 0)))
        r.append(("FEAR overwrites MIND", eff(FEAR, 2), (1 << 2, 0x02, 0)))
        r.append(("FROZEN independent (HOLD)", eff(FROZEN, 2), ((1 << 2) | FROZEN, 0x22, 0)))
        r.append(("STUNNED refused on a held body (D3-8c)", eff(STUNNED, 1), ((1 << 2) | FROZEN, 0x22, 0)))
        r.append(("POISON 9 (half: 18 turns, ST_X)", eff(POISON, 9), ((1 << 2) | FROZEN | 0x10, 0x22, 18 << 8)))
        r.append(("WEAK 12", eff(WEAK, 12), ((1 << 2) | FROZEN | 0x30, 0x22, (18 << 8) | 12)))
        r.append(("POISON adds 4 (8 turns) to 18 -> 26", eff(POISON, 4), ((1 << 2) | FROZEN | 0x30, 0x22, (26 << 8) | 12)))
        r.append(("POISON caps at 30", eff(POISON, 4), ((1 << 2) | FROZEN | 0x30, 0x22, (30 << 8) | 12)))
        r.append(("STUNNED overwrites nothing: HOLD clear -> lands", eff(STUNNED, 1, st=(0, 0, 0)), (STUNNED, 0x10, 0)))
        r.append(("R halves 3 -> 1", eff(CONFUSED, 3, res=res_bytes(PHYS, R), st=(0, 0, 0)), (2 << 2, 0x01, 0)))
        r.append(("R halves 1 -> none", eff(CONFUSED, 1, res=res_bytes(PHYS, R), st=(0, 0, 0)), (0, 0, 0)))
        r.append(("immune mask CONFUSE", eff(CONFUSED, 3, imm=S["IMMF_CONFUSE"], st=(0, 0, 0)), (0, 0, 0)))
        r.append(("I type: no effect", eff(FROZEN, 2, t=COLD, res=res_bytes(COLD, I), st=(0, 0, 0)), (0, 0, 0)))
        r.append(("HOLD_GUARD refuses STUNNED", eff(STUNNED, 1, st=(0x40, 0, 0)), (0x40, 0, 0)))
        r.append(("HOLD_GUARD refuses FROZEN", eff(FROZEN, 2, st=(0x40, 0, 0)), (0x40, 0, 0)))
        r.append(("chance 1 in 1 applies", eff(FROZEN, 2, chance=1, st=(0, 0, 0)), (FROZEN, 0x20, 0)))
        r.append(("kill: no effect, status cleared", eff(FROZEN, 2, hp=1, st=(0x31, 0x45, 0x67)), (0, 0, 0)))
        bad = [(n, g, w) for n, g, w in r if g != w]
        check("C7 effect apply rules (%d cases)" % len(r), not bad, bad)
        # chance 1 in N consumes exactly one draw and applies iff it is 0
        seeds = [0x1234, 0xBEEF, 0x0F0F, 0x4321, 0x7777, 0x2468, 0x1357, 0x9999]
        bad = []
        n_ap = 0
        for sd in seeds:
            p.wmem(S["RNG_STATE"], w16(sd))
            assert p.code([0x0E, 4, 0xCD] + w16(S["rng_mod"]) + [0x32] + w16(RES))
            want = p.rb(RES) == 0
            p.wmem(S["RNG_STATE"], w16(sd))
            g = eff(CONFUSED, 4, chance=4, st=(0, 0, 0))
            n_ap += want
            if (g == (2 << 2, 4, 0)) != want:
                bad.append((hex(sd), g, want))
        check("C7 chance 1 in 4 == (rng_mod 4 == 0) for 8 seeds", not bad, (bad, n_ap))

        # --- C8 XP ---
        def kill(kind, xp0=0, flags=0):
            p.wmem(S["XP"], w16(xp0))
            p.wb("XP_UP", 0)
            p.hero()
            p.mon(1, kind, 1, flags=flags)
            p.deal(0, 1, 5, PHYS)
            return p.rw("XP"), p.rb("XP_UP")
        x = [kill(K_RAT), kill(K_RAT, flags=EF_RESPAWN), kill(K_GHOST, 100), kill(K_GHOST, 100, EF_RESPAWN),
             kill(K_SLIME, 0, EF_RESPAWN), kill(K_GHOST, 9998)]
        want = [(2, 1), (1, 1), (106, 1), (103, 1), (1, 1), (9999, 1)]
        p.wmem(S["XP"], w16(50))
        p.wb("XP_UP", 0)
        p.hero(hp=1)
        p.mon(1, K_RAT, 3)
        p.deal(1, 0, 3, PHYS)
        hx = (p.rw("XP"), p.rb("XP_UP"), bool(p.ent(0)["FLAGS"] & EF_DYING))
        check("C8 XP: KXP, respawn /2 min 1 (Slime 3 -> 1), saturation 9999, XP_UP; hero death none",
              x == want and hx == (50, 0, True), (x, hx))

        # --- C9 hit_roll ---
        p.hero()
        p.mon(1, K_RAT, 3)                               # Rat atk 0; Knight eva 2
        katk = p.rb(S["kind_tab"] + S["KT_ATK"] + K_RAT)
        keva = p.rb(S["kind_tab"] + S["KT_EVA"] + K_KNIGHT)
        bad = []
        rng = random.Random(7)
        for i in range(40):
            mod = rng.randint(-3, 12)
            held = i % 2
            p.st(0, STUNNED if held else 0, 0x10 if held else 0)
            p.wmem(S["RNG_STATE"], w16(rng.randrange(1, 65536)))
            hit, d20 = p.roll(1, 0, mod)
            want = d20 + katk + mod >= 10 + (0 if held else keva)
            if bool(hit) != want:
                bad.append((mod, held, d20, hit))
        p.st(0)
        check("C9 hit_roll == F1 (d20 + atk + mod >= 10 + eva; held: eva 0), 40 rolls", not bad, bad)

        # --- C10 real melee: Ghost touch on the Mage ---
        p.boot(K_WIZARD)
        for s_ in range(1, 16):
            p.set_ent(s_, FLAGS=0)
        check("C10 hero_st_init: Mage HERO_DEF = 0", p.rb("HERO_DEF") == 0, p.rb("HERO_DEF"))
        hits = conf = 0
        bad = []
        for i in range(40):
            p.hero(hp=60, maxhp=60)
            p.st(0)
            p.mon(1, K_GHOST, 2, 8)
            p.wmem(S["RNG_STATE"], w16(0x1000 + 977 * i))
            p.attack(1, 0)
            lost = 60 - p.ent(0)["HP"]
            gain = p.ent(1)["HP"] - 2
            f, t1, _ = p.gst(0)
            if lost:
                hits += 1
                conf += f == (2 << 2)
                if gain or not 1 <= lost <= 4 or f not in (0, 2 << 2) or (f and t1 != 4):
                    bad.append((i, lost, gain, f, t1))
            elif gain or f:
                bad.append((i, lost, gain, f, t1))
        check("C10 Ghost touch: 1d4 DRAIN (no DEF, no heal: §9.1), CONFUSED 4 on some hits (%d of %d)" % (conf, hits),
              not bad and hits > 5 and 0 < conf < hits, bad)
        del room

        print(f"combat3: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
