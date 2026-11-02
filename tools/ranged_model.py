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
  atk (shooter KT_ATK), gold (BOSS-RANGED: a golden body, + GOLD_ATK / dmg + 1), turn_tick, map (dict row -> 32 tile flags (bit 0
  solid)), bodies: list of (slot, x, y, w, h, dying) — every live body but the
  shooter (the hero included), used by box_free.
The RNG is io.asm's (rng_next / rng_mod, mask-and-reject), passed as Rng.
3F-T11b: arch_decide (bottom) = the Archmage's turn (src/arch6.asm arch_ai, game.md
§9.9), tests/archmage.py; deal_hero now models every on-hit effect + DH_HEAL.
NOTE: arch_decide was written alongside arch6.asm and MIRRORS the implementation
(its order of tests, the S-1-via-sp_summon detail, the blink search), checked
against the §9.9 text by review — it is not an independent from-spec oracle.
"""

RSP_N, RSP_R, RSP_I, RSP_X = range(4)
DTY_PHYS, DTY_DARK = 0, 5
NODEF, EFX_SHIFT = 0x08, 4
EFX_FEAR = 4
RWF_SPELL, RWF_AWAY, RWF_NOIMP, RWF_PRE, RWF_NOREFL, RWF_HEX, RWF_HOLD, RWF_WALK = 1, 2, 4, 8, 16, 32, 64, 128
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
# BOSS-RANGED (plan.md rulings): rows used ONLY by a golden body (ai_rhook's RK_GOLD1 gate) —
# the Goblin King's dagger (D1) and the Spider Queen's spit (D2, always POISON + 12 -> E = 6)
K_GOBLIN, K_SPIDER, GOLD_ATK = 4, 9, 2
GOLD_ROWS = {
    K_GOBLIN: (6, 2, RWF_WALK | RWF_NOIMP, 3, 0, DTY_PHYS, 0, "dagger_spin1"),                  # Goblin King
    K_SPIDER: (6, 2, RWF_WALK | RWF_NOIMP, 2, 0, DTY_PHYS | (6 << EFX_SHIFT), 12 // 2, "dagger_spin1"),  # Spider Queen
}


def row_of(kind, gold):
    """rk_tab + ai_rhook's gate: the kind's row tuple, or None (the walker / guard rules)."""
    if kind in GOLD_ROWS:
        return GOLD_ROWS[kind] if gold else None
    return ROWS.get(kind)
# 3F-T11b (game.md §9.9 A2): the Archmage's 7 spell rows (arch6.asm), spell index 0..6
DTY_FIRE, DTY_COLD, DTY_SHOCK, DTY_DRAIN = 1, 2, 3, 4
EFX_FROZEN, EFX_ASLEEP, EFX_STUNNED, EFX_CONFUSED, EFX_POISON, EFX_WEAK = 1, 2, 3, 5, 6, 7
DH_HEAL = 0x80
IMMF_SLEEP, IMMF_POISON = 0x01, 0x10
ARCH_ROWS = [   # (r, N, flags, die / hex: immunity bit, bon / hex: line, dhc, dhe, fx)
    (28, 1, RWF_SPELL | RWF_NOREFL, 8, 3, DTY_DARK | NODEF | (EFX_FEAR << 4), FEAR3, "nbolt_fly1"),     # Death Bolt
    (12, 1, RWF_SPELL | RWF_HOLD, 6, 1, DTY_COLD | NODEF | (EFX_FROZEN << 4), 0x22, "nbolt_fly1"),       # Frost
    (12, 1, RWF_SPELL, 8, 1, DTY_SHOCK | NODEF | (EFX_CONFUSED << 4), 0x24, "nbolt_fly1"),               # Lightning
    (5, 1, RWF_SPELL, 6, 1, DTY_DRAIN | NODEF | DH_HEAL | (EFX_WEAK << 4), 0x28, "nbolt_fly1"),          # Drain
    (12, 1, RWF_SPELL | RWF_HOLD, 8, 2, DTY_FIRE | NODEF | (EFX_STUNNED << 4), 0x31, "nbolt_fly1"),     # Firebolt
    (12, 0, RWF_SPELL | RWF_HEX | RWF_HOLD, IMMF_SLEEP, "TX_ST_ASLEEP", EFX_ASLEEP << 4, 3 << 4, "nbolt_fly1"),  # Sleep
    (12, 0, RWF_SPELL | RWF_HEX, IMMF_POISON, "TX_ST_POISONED", EFX_POISON << 4, 12, "nbolt_fly1"),            # Venom
]
ARCH_INK = [0x43, 0x45, 0x47, 0x44, 0x42, 0x41, 0x06]
AM_ORDER_N, AM_HEX_R, AM_HEX_CD, AM_SUM_CD, AM_BLINK_N = 5, 12, 4, 6, 8
TELE_FLASH_T, AM_BLINK_ATTR, MSG_M_SUMMON = 5, 0x47, 16
STS_GUARD, PSN_CAP = 0x40, 30
# deal_hit's efx_tab (combat3.asm): id -> (immunity bit, STATUS mask, value, timer field)
EFX_TAB = {1: (0, 0x03, 1, "t1hi"), 2: (0x01, 0x03, 2, "t1hi"), 3: (0x02, 0x03, 3, "t1hi"),
           4: (0x08, 0x0C, 4, "t1lo"), 5: (0x04, 0x0C, 8, "t1lo"), 6: (0x10, 0x10, 0x10, "x"),
           7: (0, 0x20, 0x20, "t2lo")}
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


def deal_hero(sit, rng, dmg, c, e, out, att=None):
    """combat3.asm deal_hit on the hero (slot 0): -> HP lost; out gets hp / stf / st1 / st2 / stx / react.
    3F-T11b: every on-hit effect (efx_tab, R2 order, HOLD rules, FIRE thaw); att = the attacker
    {hp, maxhp} healed by DH_HEAL (in place)."""
    H = sit["hero"]
    hp = H["hp"]
    out.update(hp=hp, stf=H["stf"], st1=H["st1"], st2=H.get("st2", 0), stx=H.get("stx", 0), react=H["react"])
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
        out["react"], out["stf"], out["st1"], out["st2"] = RC_DEATH, 0, 0, 0
    else:
        out["react"] = out["react"] if out["react"] == RC_DEATH else 1
        _hero_status(H, rng, c, e, rsp, out)
    if c & DH_HEAL and att is not None and att["hp"]:
        att["hp"] = min(att["maxhp"], att["hp"] + lost)
    return lost


def _hero_status(H, rng, c, e, rsp, out):
    """dh_status on the surviving hero."""
    stf, st1, st2, stx = out["stf"], out["st1"], out["st2"], out["stx"]
    if stf & STS_HOLD == 2:                         # ASLEEP wakes (any HP loss)
        stf &= ~STS_HOLD
        st1 &= 0x0F
    elif stf & STS_HOLD == 1 and c & 7 == DTY_FIRE:  # FIRE thaws FROZEN (+ HOLD_GUARD)
        stf = (stf & ~STS_HOLD) | STS_GUARD
        st1 &= 0x0F
    out.update(stf=stf & 0xFF, st1=st1 & 0xFF)
    efx = (c >> EFX_SHIFT) & 7
    if not efx:
        return
    ch = e >> 4
    if ch and rng.mod(ch) != 0:
        return
    imm, mask, val, tmr = EFX_TAB[efx]
    if H["imm"] & imm:
        return                                      # UNAFFECTED
    turns = e & 15
    if rsp == RSP_R:
        turns //= 2
    if not turns:
        return
    if efx < EFX_FEAR:
        if stf & STS_HOLD:
            return                                  # no HOLD on a held body
        if efx != EFX_ASLEEP and stf & STS_GUARD:
            return                                  # HOLD_GUARD
    same = (stf & mask) == val
    stf = (stf & ~mask) | val
    if tmr == "x":
        stx = turns * 2 if not same else min(PSN_CAP, stx + turns * 2)
    else:
        cur = st1 >> 4 if tmr == "t1hi" else st1 & 15 if tmr == "t1lo" else st2 & 15
        d = max(cur, turns) if same else turns
        if tmr == "t1hi":
            st1 = (st1 & 0x0F) | (d << 4)
        elif tmr == "t1lo":
            st1 = (st1 & 0xF0) | d
        else:
            st2 = (st2 & 0xF0) | d
    out.update(stf=stf & 0xFF, st1=st1 & 0xFF, st2=st2 & 0xFF, stx=stx)




def flight_row(sit):
    """§9.2 fr = shooter top + 2, inside the hero's rows; BOSS-RANGED: a 2-high shooter (the Spider
    Queen, top = 9s+6) fires from its top row (top + 2 would be its floor)."""
    return sit["y"] + (PF_ROW_DY if sit["h"] > 2 else 0)


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
        fr = flight_row(sit)
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
    if old and fl & RWF_WALK:                       # BOSS-RANGED: between shots it walks in (L = 0)
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
            hit = d20 + sit["atk"] + (GOLD_ATK if sit.get("gold") else 0) - 10 - eva >= 0
        hs = {}
        if hit:
            sh["imp"] = not fl & RWF_NOIMP
            dmg = rng.mod(die) + 1 + bon + (1 if sit.get("gold") else 0)   # 3F-T8: a golden shooter + 1
            sh["lost"] = deal_hero(sit, rng, dmg, dhc, dhe, hs)
            sh["gate"] = min(I, R + CNB_MAX)
        else:
            sh["msg"] = MSG_M_MISS
        sh["hero"] = hs
        anchor = first if d > 0 else first + gap - 1
        sh["desc"] = [fx, fx + 1] + ([fx + 2] * 2 if sh["imp"] else [FX_NONE] * 2) + \
            [ROCK_ATTR if fl & RWF_NOIMP else 0, anchor, flight_row(sit), 1 if d < 0 else 0, 0, PF_IMPT if sh["imp"] else 0, 1, gap, 0, 0, 0, 0]
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


# ---------------------------------------------------------------------------
# 3F-T11b the Archmage's turn (game.md §9.9 A3; src/arch6.asm arch_ai), from the spec.
# sit: x, y, w, h, slot, hp, maxhp, rcd (E_RCD), stx (ST_X + slot), storey, left,
#   turn_tick, map (row -> 32 tile flags, rows 0..17), bodies (as decide, the Archmage
#   excluded), summon_ok (sp_summon would queue), hero (as decide + st2, stx = his
#   ST_X poison), tf (TF_* values), xmin / xmax (LP_XMIN / LP_XMAX), ink (KT_ATTR
#   before), dark_res (the Archmage's DARK response).
# -> dict: rcd, stx, left, x, y, hp, msg (None = untouched), act (bolt / hex / blink /
#   summon / staff), spell, shots (RS_Q entries [R, FL] + 16-B desc), hero, cnb,
#   hreactat, ink, react / reactat (the Archmage: the Mirror Helm return), fl.
# The staff (attack_if_reach: hit_roll / melee) is not modelled: act "staff" only.
# ---------------------------------------------------------------------------
def arch_line(sit, r=28):
    """rg_line with the Death Bolt row loaded (r 28); the hex calls it with the Sleep row (r 12)."""
    H = sit["hero"]
    if H["ladder"] or H["storey"] != sit["storey"]:
        return None
    x, w = sit["x"], sit["w"]
    if H["x"] >= x + w:
        d, first, gap = 1, x + w, H["x"] - (x + w)
    elif x >= H["x"] + H["w"]:
        d, first, gap = -1, H["x"] + H["w"], x - (H["x"] + H["w"])
    else:
        return None
    if gap >= r:
        return None
    if gap:
        fr = sit["y"] + PF_ROW_DY
        if any(sit["map"][fr][c] & 1 for c in range(first, first + gap)):
            return None
        if not box_free(sit, (first, sit["y"], gap, sit["h"])):
            return None
    return d, first, gap


def arch_pick(sit, s, fb, gap):
    r, _, fl = ARCH_ROWS[s][:3]
    if gap >= r or (fl & RWF_HOLD and sit["hero"]["stf"] & (STS_HOLD | STS_GUARD)):
        return fb
    return s


def arch_cast(sit, rng, s, line, out, fx):
    d, first, gap = line
    r, N, fl, die, bon, dhc, dhe, _ = ARCH_ROWS[s]
    H = sit["hero"]
    out["left"] = d < 0
    out["rcd"] = (out["rcd"] & ~3) | (N ^ 1)
    R = sit["turn_tick"] + RG_REL + (sit["slot"] & 1)
    I = R + gap + 1
    hs = dict(hp=H["hp"], stf=H["stf"], st1=H["st1"], st2=H.get("st2", 0), stx=H.get("stx", 0),
              react=H["react"])
    lost, dmg = 0, 0
    if fl & RWF_HEX:                               # am_hex: the immunity mask only
        if not H["imm"] & die:
            if dhc == EFX_POISON << 4:
                hs["stx"] = dhe if not H["stf"] & 0x10 else min(PSN_CAP, H.get("stx", 0) + dhe)
                hs["stf"] = H["stf"] | 0x10
            else:
                hs["stf"] = (H["stf"] & ~STS_HOLD) | EFX_ASLEEP
                hs["st1"] = (H["st1"] & 0x0F) | dhe
        out["msg"] = 0
    else:
        dmg = rng.mod(die) + 1 + bon
        att = dict(hp=out["hp"], maxhp=sit["maxhp"])
        lost = deal_hero(sit, rng, dmg, dhc, dhe, hs, att)
        out["hp"] = att["hp"]
        out["msg"] = MSG_M_HIT
    out["hero"] = hs
    out["cnb"] = min(I, R + CNB_MAX)
    if lost:
        out["hreactat"] = I
    anchor = first if d > 0 else first + gap - 1
    desc = [fx, fx + 1, fx + 2, fx + 2, ARCH_INK[s], anchor, sit["y"] + PF_ROW_DY, 1 if d < 0 else 0, 0,
            PF_IMPT, 1, gap, 0, 0, 0, 0]
    out["shots"] = [[R, I if lost else 0] + desc]
    if s == 0 and hero_rsp(H["res"], DTY_DARK) == RSP_X:     # A6 the Mirror Helm return
        dm = max(1, dmg // 2) if sit["dark_res"] == RSP_R else dmg
        l2 = min(dm, out["hp"])
        out["hp"] -= l2
        if l2:
            out["react"] = RC_DEATH if out["hp"] == 0 else 1
            out["reactat"] = I + gap + 1
        back = list(desc)
        back[5] = 2 * first + gap - 1 - anchor
        back[7] ^= 1
        out["shots"].append([I, 0] + back)


def arch_sp_try(sit, cx, y):
    """spawn6.asm sp_try for the Archmage's walker box at (cx, y)."""
    tf, w, h = sit["tf"], sit["w"], sit["h"]
    if cx < sit["xmin"] or cx > sit["xmax"] or cx + w - 1 > sit["xmax"]:
        return False
    if not box_free(sit, (cx, y, w, h)):
        return False
    for c in range(cx, cx + w):
        if sit["map"][y + h][c] & (tf["FLOOR"] | tf["HOLE"] | tf["LADDER"]) != tf["FLOOR"]:
            return False
        if sit["map"][y + h - 1][c] & (tf["SOLID"] | tf["LADDER"] | tf["DOOR"]):
            return False
    return True


def arch_decide(sit, rng, fx):
    """fx = FID_nbolt_fly1 -> the expected results of one arch_ai call."""
    rcd, stx = sit["rcd"], sit["stx"]
    half = sit["maxhp"] // 2
    if not stx & 0x80:                             # 0. fresh / re-entered
        stx = 0x80 | (0x40 if sit["hp"] <= half else 0)
    if stx & 0x38:                                 # 1. H, S, C
        stx -= 8
    if rcd & 0x3C:
        rcd -= 4
    c = (rcd ^ 1) & 3
    old = c
    rcd = (rcd & ~3) | ((max(0, c - 1)) ^ 1)
    out = dict(rcd=rcd, stx=stx, left=sit["left"], x=sit["x"], y=sit["y"], hp=sit["hp"], msg=None, act=None,
               spell=None, shots=[], hero=None, cnb=None, hreactat=None, ink=sit["ink"], react=None,
               reactat=None, fl=None)
    line = arch_line(sit)
    if line and old == 0:                          # 2. the bolt turn
        P = stx & 7
        nP = (P + 1) % AM_ORDER_N
        out["stx"] = (stx & ~7) | nP
        s = arch_pick(sit, P, 0, line[2])
        arch_cast(sit, rng, s, line, out, fx)
        out.update(act="bolt", spell=s, ink=ARCH_INK[nP])
        return out
    if not out["stx"] & 0x40 and sit["hp"] <= half:  # 3a. blink
        out["stx"] |= 0x40
        ty = 9 * (1 - sit["storey"]) + 8 - sit["h"]
        dr = 1 if sit["x"] < 15 else -1
        for k in range(AM_BLINK_N + 1):
            cx = sit["x"] + k * dr
            if arch_sp_try(sit, cx, ty):
                out.update(x=cx, y=ty, act="blink", fl=(TELE_FLASH_T, AM_BLINK_ATTR))
                out["rcd"] &= ~0x3C
                return out
    if not out["rcd"] & 0x3C and sit["summon_ok"]:  # 3b. summon
        out["rcd"] = (out["rcd"] & ~0x3C) | (AM_SUM_CD << 2)
        out.update(act="summon", msg=MSG_M_SUMMON)
        return out
    line = arch_line(sit, AM_HEX_R)
    if line and not out["stx"] & 0x38:             # 3c. hex
        out["stx"] |= AM_HEX_CD << 3
        s = arch_pick(sit, 5, 6, line[2])
        arch_cast(sit, rng, s, line, out, fx)
        out.update(act="hex", spell=s)
        return out
    out["left"] = sit["hero"]["x"] < sit["x"]      # 3d / e. staff or wait, facing him
    out["act"] = "staff"
    return out
