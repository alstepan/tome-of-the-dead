#!/usr/bin/env python3
"""3F-T7 reference model of the monster ranged hook (game.md §9.2 RANGED-SPEC),
written from the spec (+ the manager-approved counter rule: a shot needs the
counter at 0 on entry, then it decrements) — the Z80 is src/ranged6.asm
ai_ranged / rg_shoot (+ bank-3 hit_roll / deal_hit for the hero target).

decide(sit, rng) -> dict of the expected results. `sit` is a plain dict:
  kind (shooter kind id), row (its rd_tab row as a dict, see ROWS), slot,
  x, y, w, h, left (facing), standing, storey, counter (0..3),
  hero: x, y, w, h, storey, ladder (mid-ladder), hp, eva, held, res (3 B),
        def, imm, stf, st1 (ST_FLAGS / ST_T1 of slot 0), react (E_REACT)
  atk (shooter KT_ATK), turn_tick, map (dict row -> 32 tile flags (bit 0
  solid)), bodies: list of (slot, x, y, w, h, dying) — every live body but the
  shooter (the hero included), used by box_free.
The RNG is io.asm's (rng_next / rng_mod, mask-and-reject), passed as Rng.
"""

RSP_N, RSP_R, RSP_I, RSP_X = range(4)
DTY_PHYS, DTY_DARK = 0, 5
NODEF, EFX_SHIFT = 0x08, 4
EFX_FEAR = 4
RWF_SPELL, RWF_AWAY, RWF_NOIMP, RWF_PRE, RWF_NOREFL = 1, 2, 4, 8, 16
FEAR3 = (3 << 4) | 3
DARK_DHC = DTY_DARK | NODEF | (EFX_FEAR << EFX_SHIFT)
# kind -> (r, N, flags, die, bonus, dhc, dhe, fx name)
ROWS = {
    12: (10, 1, RWF_AWAY, 6, 0, DTY_PHYS, 0, "arrow_fly1"),                    # Archer
    28: (14, 1, 0, 8, 0, DTY_PHYS, 0, "arrow_fly1"),                           # Sniper
    21: (6, 2, RWF_AWAY | RWF_NOIMP, 3, 0, DTY_PHYS, 0, "dagger_spin1"),        # Slinger
    14: (8, 2, RWF_AWAY | RWF_SPELL, 6, 1, DARK_DHC, FEAR3, "nbolt_fly1"),     # Necromancer
    29: (8, 2, RWF_AWAY | RWF_SPELL | RWF_PRE, 6, 1, DARK_DHC, FEAR3, "nbolt_fly1"),  # Bone Caller
}
ARCHMAGE_ROW = (28, 2, RWF_SPELL | RWF_NOREFL | 0x40, 8, 3, DTY_DARK | NODEF, 0, "nbolt_fly1")
ROCK_ATTR = 0x06                                   # the Slinger's rock FX attr (§9.6)
PF_ROW_DY, RG_REL, CNB_MAX, PF_IMPT, FX_NONE = 2, 2, 8, 2, 0xFF
STS_HOLD, STS_MIND, MIND_FEAR, IMMF_FEAR = 0x03, 0x0C, 0x04, 0x08
MSG_M_HIT, MSG_M_MISS = 4, 5
RC_DEATH = 3
BC_CD, BC_LIVE = 8, 1                              # 3F-T9 Bone Caller summon (combat_defs.asm)


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


def box_hit(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax <= bx + bw - 1 and bx <= ax + aw - 1 and ay <= by + bh - 1 and by <= ay + ah - 1


def box_free(sit, box):
    return not any(box_hit(box, (x, y, w, h)) for _, x, y, w, h, dying in sit["bodies"] if not dying)


def hero_rsp(res, t):
    return (res[t // 4] >> (2 * (t % 4))) & 3


def deal_hero(sit, rng, dmg, c, e, out):
    """combat3.asm deal_hit on the hero (slot 0): -> HP lost; out gets hp / stf / st1 / react."""
    H = sit["hero"]
    hp = H["hp"]
    out.update(hp=hp, stf=H["stf"], st1=H["st1"], react=H["react"])
    if hp == 0:
        return 0
    t = c & 7
    rsp = hero_rsp(H["res"], t)
    weak = (H["res"][2] >> t) & 1
    if rsp >= RSP_I:
        return 0
    if rsp == RSP_R:
        dmg = max(1, dmg // 2)
    if weak:
        dmg = min(255, dmg * 2)
    if t == DTY_PHYS and not c & NODEF:
        dmg = max(1, dmg - H["def"])
    dmg = max(1, dmg)
    lost = min(dmg, hp)
    hp -= lost
    out["hp"] = hp
    if hp == 0:
        out["react"], out["stf"], out["st1"] = RC_DEATH, 0, 0
        return lost
    out["react"] = out["react"] if out["react"] == RC_DEATH else 1
    stf, st1 = out["stf"], out["st1"]
    if stf & STS_HOLD == 2:                         # ASLEEP wakes (any HP loss)
        stf &= ~STS_HOLD
        st1 &= 0x0F
    efx = (c >> EFX_SHIFT) & 7
    if efx == EFX_FEAR:
        ch = e >> 4
        ok = rng.mod(ch) == 0 if ch else True
        if ok:
            if H["imm"] & IMMF_FEAR:
                pass                                # UNAFFECTED
            else:
                turns = e & 15
                if rsp == RSP_R:
                    turns //= 2
                if turns:
                    same = (stf & STS_MIND) == MIND_FEAR
                    cur = st1 & 15
                    stf = (stf & ~STS_MIND) | MIND_FEAR
                    st1 = (st1 & 0xF0) | (max(cur, turns) if same else turns)
    out["stf"], out["st1"] = stf & 0xFF, st1 & 0xFF
    return lost


def decide(sit, rng):
    """-> dict: used, counter, left, x, moved, shot (None or the shot's results)."""
    r, N, fl, die, bon, dhc, dhe, fx = sit["row"]
    old = sit["counter"]
    out = dict(used=False, counter=max(0, old - 1), left=sit["left"], x=sit["x"], moved=False, shot=None)
    H = sit["hero"]
    if not sit["standing"] or H["ladder"] or H["storey"] != sit["storey"]:
        return out
    x, w = sit["x"], sit["w"]
    if H["x"] >= x + w:
        d, first, gap = 1, x + w, H["x"] - (x + w)
    elif x >= H["x"] + H["w"]:
        d, first, gap = -1, H["x"] + H["w"], x - (H["x"] + H["w"])
    else:
        return out
    if gap >= r:
        return out
    if gap:
        fr = sit["y"] + PF_ROW_DY
        if any(sit["map"][fr][c] & 1 for c in range(first, first + gap)):
            return out
        if not box_free(sit, (first, sit["y"], gap, sit["h"])):
            return out
    if fl & RWF_SPELL and not fl & RWF_NOREFL and hero_rsp(H["res"], DTY_DARK) == RSP_X:
        return out
    if fl & RWF_PRE:                                # 3F-T9 caster pre-rule (spawn6.asm sp_summon):
        s = sit.get("s", 0)                         # S (E_RCD bits 2-5) > 0: S - 1 and on to the shot;
        if s:                                       # S = 0 and the room takes a summon (sit["summon_ok"]:
            out["s"] = s - 1                        # queue free, < BC_LIVE summons, a free slot, the cap)
        elif sit.get("summon_ok"):                  # -> the turn is the summon: S := BC_CD, no shot
            out.update(used=True, summon=True, s=BC_CD)
            return out
    out["used"] = True
    if old == 0:                                    # SHOOT
        out["left"] = d < 0
        out["counter"] = N
        R = sit["turn_tick"] + RG_REL + (sit["slot"] & 1)
        I = R + gap + 1
        sh = dict(R=R, I=I, msg=MSG_M_HIT, lost=0, imp=False, gate=None)
        hit = True
        if not fl & RWF_SPELL:
            d20 = rng.mod(20) + 1
            eva = 0 if H["held"] else H["eva"]
            hit = d20 + sit["atk"] - 10 - eva >= 0
        hs = {}
        if hit:
            sh["imp"] = not fl & RWF_NOIMP
            dmg = rng.mod(die) + 1 + bon
            sh["lost"] = deal_hero(sit, rng, dmg, dhc, dhe, hs)
            sh["gate"] = min(I, R + CNB_MAX)
        else:
            sh["msg"] = MSG_M_MISS
        sh["hero"] = hs
        anchor = first if d > 0 else first + gap - 1
        sh["desc"] = [fx, fx + 1] + ([fx + 2] * 2 if sh["imp"] else [FX_NONE] * 2) + \
            [ROCK_ATTR if fl & RWF_NOIMP else 0, anchor, sit["y"] + PF_ROW_DY, 1 if d < 0 else 0, 0, PF_IMPT if sh["imp"] else 0, 1, gap, 0, 0, 0, 0]
        sh["flash"] = I if sh["lost"] else 0
        out["shot"] = sh
        return out
    if gap <= 2 and fl & RWF_AWAY:                  # step away
        nx = x - d
        lead = nx if -d < 0 else nx + w - 1
        legal = (nx >= 1 and nx + w - 1 <= 30 and not sit["map"][sit["y"] + sit["h"] - 1][lead] & 1
                 and box_free(sit, (nx, sit["y"], w, sit["h"])))
        if legal:
            out["x"], out["moved"], out["left"] = nx, True, -d < 0
            return out
    out["left"] = d < 0                             # HOLD (or a blocked step-away)
    return out
