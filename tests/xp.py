#!/usr/bin/env python3
"""D3-9b: XP, levels, MP regen / bar, learn / rank-up (game.md §4, §4.1, §5, §7)
on a release build (DEBUG_KIT=0), PROTO room A, every other monster parked.
The award is deal_hit's (combat3.asm); the level-up + regen are xp_turn
(src/xp7.asm, end_turn); learn / rank-up abil_learn (xp7.asm); the MP item
item_mp + the poll (xp2.asm / icons.asm); the rank info line item_info (D3-9a).

  L   a kill through deal_hit -> XP += KXP; level-up exactly at the threshold
      (XP 37 + Goblin 3 = 40 -> L2; 36 + 3 = 39 stays L1); a respawned Goblin
      (EF_RESPAWN) gives 1; LVL_SH (panel digit at (31, 19)) follows
  G   gains: Warrior max/cur HP +4, MP +1; Mage HP +3, MP +2;
      "YOU REACH LEVEL 2!"
  S   steps: XP 919 -> 922 at L1 = 7 levels at once: gains x 7, atk +2 (L4, L8),
      eva +1 (L6) in the hero's kind_tab columns; lines REACH LEVEL 8 / STRIKE
      TRUER / FEEL NIMBLE; L9 cap (XP 9999 -> L9, nothing more); a new game
      restores LVL 1 and the base atk / eva
  M   MP regen: Warrior +1 on the 8th turn, Mage on the 5th; never above MAXMP;
      none while WEAK (MP_RG frozen); the panel's MP_SH follows MP
  R   abil_learn per ability (Mage k 0..4, Warrior k 0..1): ranks 1, 2, 3 ->
      RANK_ROWS row k == the ab_rank row of that rank; a 4th call returns 0;
      "YOU LEARN SPARK!", "SPARK RISES TO RANK 2"; the info line id of the
      selected rank-3 ability is its info_<name>3 line (D3-9a)
Run: ZRCP_PORT=<port> python3 tests/xp.py
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, K_GOBLIN, stand_y, RUN_LIMIT  # noqa: E402
from proj3 import T, w16  # noqa: E402
import combat_tables as CT  # noqa: E402
from abil_melee import stream_text  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT = 1, 2, 4, 8
EF_RESPAWN = S["EF_RESPAWN"]
HY = stand_y(1, 6)
HX = 12
NOWHERE = 7
STUB = S["LOWRAM_END_3B"]
RES = STUB + 200
TXT = None


def main():
    global TXT
    import textpack
    TXT = dict(textpack.read_strings())
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:600]}", flush=True)

        if KIT:
            print("[skip] xp needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(h, p, check)
        print(f"xp: {len(fails)} failed" + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def run(h, p, check):
    sym, b3 = CT.load()
    ab = sym["ab_rank"] - CT.BASE
    lines = []
    LOGP = S["log_push"]
    WT = S["wait_tick"]
    KT_ATK, KT_EVA, KTAB = S["KT_ATK"], S["KT_EVA"], S["kind_tab"]
    slots = {}

    def run_to_probe():
        for _ in range(200):
            p.z.cmd("run %d" % RUN_LIMIT)
            pc = p.pc()
            if pc == LOGP:
                regs = p.z.cmd("get-registers")
                hl = int(re.search(r"HL=([0-9a-fA-F]{4})", regs).group(1), 16)
                lines.append(stream_text(p.z.read_memory(hl, 48)).rstrip("."))
                p.z.cmd("cpu-step")
                continue
            if pc in p.probes:
                return
            raise RuntimeError(f"stopped at {pc:#06x}")

    def tick(n=1):
        for _ in range(n):
            p.z.cmd("cpu-step")
            run_to_probe()
    p.tick = tick

    def stub(body):
        assert p.pc() == WT, hex(p.pc())
        p.wmem(STUB, body + [0xC3] + w16(WT))
        p.z.cmd("set-register PC=%d" % STUB)
        run_to_probe()
        assert p.pc() == WT, "stub did not return"

    def far7(label, a=0):
        stub([0x3E, a, 0x21] + w16(S[label]) + [0xCD] + w16(S["far7"]) + [0x7D, 0x32] + w16(RES))
        return p.rb(RES)

    def deal(att, tgt, dmg, c=0, e=0):
        inner = ([0xDD, 0x21] + w16(S["P_ENTITIES"] + att * STRIDE) + [0x3E, tgt, 0x06, dmg, 0x0E, c, 0x1E, e,
                 0xCD] + w16(S["deal_hit"]))
        stub(p.bank3(inner))

    def place(slot, x, y, flags, hp):
        p.set_ent(slot, X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=p.rb("CUR_ROOM"), FLAGS=flags, REACT=0,
                  FLT=0, HIT=0, HP=hp, MAXHP=hp)

    def scene(hero, hp=40, mp=0, maxmp=20):
        p.boot(hero)
        if not slots:
            for sl in range(1, 16):
                slots.setdefault(p.ent(sl)["KIND"], sl)
        room = p.rb("CUR_ROOM")
        for sl in range(1, 16):
            e = p.ent(sl)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                p.set_ent(sl, ROOM=NOWHERE)
        place(0, HX, HY, EF_ACTIVE | EF_PLAYER, hp)
        p.wmem(S["ST_FLAGS"], [0] * 16)
        p.wb("MP", mp)
        p.wb("MAXMP", maxmp)
        p.wb("MP_RG", 0)
        p.tick(3)
        p.z.cmd("set-breakpoint 5 PC=%d" % LOGP)       # every log_push line -> `lines`
        lines.clear()

    def kill(xp0, kind=K_GOBLIN, flags=0):
        """XP = xp0, a kind far right (parked off the hero's path) killed by
        deal_hit (NODEF), then one Wait turn (end_turn -> xp_turn)."""
        p.wmem(S["XP"], w16(xp0))
        sl = slots[kind]
        place(sl, HX + 12, HY + 2, EF_ACTIVE | EF_HOSTILE | EF_LEFT | flags, 1)
        deal(0, sl, 50, S["DH_NODEF"])
        xp1 = p.rw("XP")
        p.turn("WAIT")
        p.tick(4)
        return xp1

    def info_tx():
        """INFO_TX lives in bank 1 (ui1_vars): read it with bank 1 paged."""
        stub([0x3A] + w16(S["PORT_7FFD_SHADOW"]) + [0xF5, 0x3E, 1, 0xCD] + w16(S["page_bank"])
             + [0x3A] + w16(S["INFO_TX"]) + [0x32] + w16(RES) + [0xF1, 0xCD] + w16(S["restore_page"]))
        return p.rb(RES)

    def hero_stats():
        e = p.ent(0)
        return p.rb("LVL"), e["HP"], e["MAXHP"], p.rb("MP"), p.rb("MAXMP")

    def katk(k):
        return p.rb(KTAB + KT_ATK + k), p.rb(KTAB + KT_EVA + k)

    # ======================= L / G: threshold, gains ============================
    scene(K_KNIGHT, hp=30, mp=3, maxmp=6)
    base_w = katk(K_KNIGHT)
    x = kill(36)
    check("L1 XP 36 + Goblin 3 = 39: stays L1", x == 39 and p.rb("LVL") == 1 and p.rb("XP_UP") == 0,
          (x, p.rb("LVL")))
    x = kill(37)
    st = hero_stats()
    check("L2 XP 37 + 3 = 40 = XP_NEXT[2]: L2, XP_UP cleared", x == 40 and st[0] == 2 and p.rb("XP_UP") == 0,
          (x, st))
    check("G1 Warrior: HP 30/30 -> 34/34, MP 3/6 -> 4/7", st[1:] == (34, 34, 4, 7), st)
    check("G1 'YOU REACH LEVEL 2!' logged once", lines.count(TXT["xp_reach"] + "2!") == 1, lines)
    check("L3 panel level digit: LVL_SH follows LVL", p.rb("LVL_SH") == 2, p.rb("LVL_SH"))
    check("G1 no step at L2: atk / eva unchanged", katk(K_KNIGHT) == base_w, (katk(K_KNIGHT), base_w))
    x = kill(37, flags=EF_RESPAWN)
    check("L4 a respawned Goblin awards KXP / 2 = 1 (37 -> 38)", x == 38, x)

    scene(K_WIZARD, hp=20, mp=5, maxmp=12)
    kill(39)
    st = hero_stats()
    check("G2 Mage: L2, HP 20/20 -> 23/23, MP 5/12 -> 7/14", st == (2, 23, 23, 7, 14), st)

    # ======================= S: steps, multi-level, cap, reset ===================
    scene(K_KNIGHT, hp=30, mp=0, maxmp=6)
    p.wb("MP_RG", 0)
    kill(919)
    st = hero_stats()
    a1 = katk(K_KNIGHT)
    check("S1 XP 922 from L1: L8 at once, HP +28, MP +7", st == (8, 58, 58, 7, 13), st)
    check("S1 atk +2 (L4, L8), eva +1 (L6)", a1 == (base_w[0] + 2, base_w[1] + 1), (a1, base_w))
    want = [TXT["xp_reach"] + "8!", TXT["xp_atk"], TXT["xp_eva"]]
    check("S1 lines: REACH LEVEL 8!, STRIKE TRUER, FEEL NIMBLE (once each)",
          all(lines.count(w) == 1 for w in want), lines)
    kill(9998)
    check("S2 L9 cap: XP 9999 -> L9, nothing beyond", p.rb("LVL") == 9 and p.rw("XP") == 9999, hero_stats())
    kill(9998)
    check("S2 at L9 another kill keeps L9", p.rb("LVL") == 9, p.rb("LVL"))
    scene(K_KNIGHT)
    check("S3 new game: LVL 1, XP 0, base atk / eva restored",
          p.rb("LVL") == 1 and p.rw("XP") == 0 and katk(K_KNIGHT) == base_w, (p.rb("LVL"), katk(K_KNIGHT)))

    # ======================= M: MP regen ==========================================
    for hero, per in ((K_KNIGHT, 8), (K_WIZARD, 5)):
        scene(hero, mp=0, maxmp=2)
        got = []
        for i in range(2 * per + 2):
            p.turn("WAIT")
            got.append(p.rb("MP"))
        want = [min(2, (i + 1) // per) for i in range(2 * per + 2)]
        check(f"M1 {'Warrior' if hero == K_KNIGHT else 'Mage'} +1 MP per {per} turns, capped at MAXMP",
              got == want, (got, want))
        p.tick(3)
        check("M2 panel MP_SH follows MP (item_mp)", p.rb("MP_SH") == p.rb("MP"), (p.rb("MP_SH"), p.rb("MP")))
    scene(K_WIZARD, mp=0, maxmp=12)
    p.wb(S["ST_FLAGS"], S["STS_WEAK"])
    p.wb(S["ST_T2"], 15)                               # WEAK 15 turns (low nibble)
    for i in range(10):
        p.turn("WAIT")
    check("M3 WEAK: no regen in 10 turns, MP_RG frozen", p.rb("MP") == 0 and p.rb("MP_RG") == 0,
          (p.rb("MP"), p.rb("MP_RG")))

    # ======================= R: learn / rank-up ===================================
    for hero, ks in ((K_WIZARD, range(5)), (K_KNIGHT, range(2))):
        scene(hero, mp=20, maxmp=20)
        bad = []
        for k in ks:
            abl = k if hero == K_WIZARD else k + S["ABL_POWER"]
            for r in (1, 2, 3):
                lines.clear()
                got = far7("abil_learn", k)
                rank = (p.rw("ARANK") >> (2 * k)) & 3
                row = list(p.z.read_memory(S["RANK_ROWS"] + 6 * k, 6))
                want = list(b3[ab + (abl * 3 + r - 1) * 6: ab + (abl * 3 + r) * 6])
                nm = TXT[["ab_spark", "ab_firebolt", "ab_frost", "ab_drain", "ab_lightning", "ab_power",
                          "ab_whirl"][abl]]
                wl = (TXT["bk_learn"] + nm + "!") if r == 1 else (nm + TXT["bk_rises"] + str(r))
                if (got, rank, row) != (r, r, want) or lines != [wl]:
                    bad.append((k, r, got, rank, row, want, lines, wl))
            if far7("abil_learn", k) != 0 or (p.rw("ARANK") >> (2 * k)) & 3 != 3:
                bad.append((k, "4th call"))
        check(f"R1 {'Mage' if hero == K_WIZARD else 'Warrior'} abil_learn ranks 1..3: RANK_ROWS == ab_rank"
              " row, lines, 4th call 0", not bad, bad)
        # D3-9a: the selected rank-3 ability's info line is its info_<name>3
        p.select_slot(1)
        p.tick(4)
        want = S["TX_INFO_SPARK3"] if hero == K_WIZARD else S["TX_INFO_POWER3"]
        check(f"R2 info line at rank 3 = info_*3 ({'Spark' if hero == K_WIZARD else 'Power Strike'})",
              info_tx() == want, (info_tx(), want))

    # ======================= C: cost + the 1st-frame gate of the lines ============
    def xp_code(xp0, xpu, first_frame):
        scene(K_KNIGHT, hp=30, mp=0, maxmp=6)
        p.z.cmd("set-breakpoint 5")
        p.wmem(S["XP"], w16(xp0))
        p.wb("XP_UP", xpu)
        p.wb("MP_RG", 7)                               # + a regen step in the same call
        sf = p.rb("SYS_FRAMES")
        p.wb("LAST_TICK_FRAME", sf if first_frame else (sf - 1) & 255)
        ok = p.code([0x21] + w16(S["xp_turn"]) + [0xCD] + w16(S["far7"]))   # (DI: SYS_FRAMES holds)
        return ok, p.tstates
    tt = {}
    for nm, xp0, xpu in (("regen only", 0, 0), ("XP no level", 10, 1), ("1 level + line", 40, 1),
                         ("L1->L4 + 2 lines", 200, 1), ("L1->L9 + 3 lines", 1200, 1)):
        tt[nm] = xp_code(xp0, xpu, True)[1]
    ok2, t9 = xp_code(1200, 1, False)
    pend = (p.rb("XP_UP"), p.rb("LVL"))
    print(f"[info] xp_turn costs (1st frame): {tt}; in a 2nd frame (level-up deferred): {t9} T", flush=True)
    # Limit 13,500 T (was 13,000; MEM-SND fix): the cost is mostly the 3 log lines'
    # decode / compose, which moves with the textpack dictionary: D3-9b 12,641 T,
    # SND-5 12,737 (+96: xp_level's sfx_req SFX_LEVELUP), SND-1 13,121 (+384: the
    # new snd_* strings retokenised the dictionary, ~+128 T per line; no xp code
    # changed). The level-up only runs in a tick's 1st frame (~84k T bound, C2),
    # so this is a drift guard, not a budget edge.
    check("C1 xp_turn L1 -> L9 at once with its 3 lines + regen <= 13.5k T (1st frame only: <= ~84k T)",
          tt["L1->L9 + 3 lines"] <= 13500, tt)
    check("C2 2nd frame: the level-up waits (XP_UP 1, LVL 1), regen only, <= 1k T",
          ok2 and pend == (1, 1) and t9 <= 1000, (ok2, pend, t9))
    # a deferred level-up lands on a later INPUT tick (turn_input -> xp_level)
    scene(K_KNIGHT, hp=30, mp=0, maxmp=6)
    p.wmem(S["XP"], w16(200))
    p.wb("XP_UP", 1)
    p.tick(2)
    check("C3 deferred level-up done by a later INPUT tick: L4, REACH LEVEL 4!, STRIKE TRUER; XP_UP 0",
          lines == [TXT["xp_reach"] + "4!", TXT["xp_atk"]] and p.rb("XP_UP") == 0 and p.rb("LVL") == 4,
          (lines, p.rb("XP_UP"), p.rb("LVL")))


if __name__ == "__main__":
    sys.exit(main())
