#!/usr/bin/env python3
"""D3-11 flying damage numbers (game.md §6.5, §6.5.1 Q2; src/dnum0.asm bank 0 =
the pass, dnum3.asm bank 3 = the spawn + FONT6 compose, dnum2.asm / dnfix2.asm /
dnum2b.asm bank 2 (the screen-2 draw, present's dn_fix), dnum3.asm dn_place (WIDOW-SPIT; was R6 dnum6.asm),
dnum7h.asm dn_evict, mark7.asm dn_reset; hooks: play_loop dn_gate, present
dn_fix, impact_line dn_sfx, hunger7 FED regen). PROTO room A, Knight
(Whirlwind: a Warrior scene), every other monster parked.
DNUM-SPRITE-FIX: the numbers live on the DISPLAYED screen only (bank 7), OR'd
over the composed bank-5 cell; frames are sampled at probe_presented (after
present + dn_fix) and checked EXACTLY against model7(): screen 2 = bank 5,
except each live number's drawn rows = bank-5 lines | its lines, attr = the
number's on a bare cell (bank-5 attr == the attr shadow), else the bank-5 one.

  H   a melee hit on a Goblin: the number spawns once its HURT / DEATH reaction
      started (never while pending; lag <= 2 ticks), value = -(HP lost), attr
      $47, width 2 / 3, row = the drawn top - 1, centred; rises 1 px a pass for
      8 passes, holds 4, gone after 12; then every window cell == background
  M   a melee miss on a Goblin: MISS ($45, 3 cells, value $80)
  P   the hero hit by a Goblin: -n in $42 on the hero
  E   the Heal potion (HP below max): +n in $44; a heal at max HP: nothing
  S   an unreacted hero HP loss while poisoned: -2 in $43
  D   a 9-bit delta: the hero 200 -> 40 = -99, 40 -> 200 = +99 (never wraps)
  L   a level-up (MAXHP and HP + 5 together): silent; a blow + a level-up between the
      same two passes: the blow's -n (the rise taken off)
  C   4 unreacted changes on one tick: one spawn a pass, LEFT TO RIGHT (E_X),
      <= 3 live, the 4th ends the oldest
  G   no ghost: a number replaced (opposite sign) on its own body: the old
      window is background again in the same pass (only the new start row drawn)
  W   Whirlwind r1 on 4 bodies (2 left, 2 right): every body gets -n or MISS,
      spawned one a pass in E_X order
  K   a FROZEN Goblin: its number ORs over its status mark cell (the mark's
      pixels and attr kept), bare cells in the number's attr
  V   (DNUM-SPRITE-FIX) a number left standing (its Rat parked) while the hero
      walks right through it: every tick screen 2 == model7 (the hero's pixels
      kept in the number cells, the digit OR'd over them; his attr there, the
      number's on bare cells); after expiry screen 2 == bank 5, and the frames
      after it == a control run with the same HP change made silent
  Q   (DNUM-SPRITE-FIX) the same with a Goblin walking through it (a monster's
      pixels / attr kept)
  X   a room exit: at the first scroll step the live number's cells are back
      to the old room's background, no entry is live after, and the arrival's
      displayed screen == the composed one (no digit left anywhere)
  Z   a body at the top row (Y 0): DL_ROW = 1 (window rows 0 / 1), bank-7 code
      untouched (review: the clamp once gave $FF)
  Y   (LVL-FLOATER) a real level-up (XP at the next threshold, XP_UP): "+LVL" (value MISS,
      attr $46, 3 cells, FONT6 text) spawns on the hero, lives 12 passes, erases cleanly,
      model7 exact, ROOM_MAP / bank-7 code untouched; a miss line + a level-up = one
      "+LVL"; a Goblin's MISS stays MISS; a blow first keeps the owed "+LVL"
      (LVL-KEEP) "+LVL" is filed as slot | $80: a blow / poison tick N = 1..8 passes after
      it takes its own entry, "+LVL" keeps its full 12 passes
  R   ROOM_MAP never written; after everything expired the composed screen ==
      the presented one
  every sampled tick of H / M / G / K / Y / V / Q: model7 exact (MODEL)
Run: ZRCP_PORT=<port> python3 tests/dnum.py   (DEBUG_KIT=0 build)
     DNUM_PNG=<dir>: also write 2x PNGs of the displayed screen (H a hit on the
     Goblin, P the hero hit, V / Q a body under a standing number)
"""
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
sys.argv = [sys.argv[0], "999"]               # keep game.py's item filter inert
import game  # noqa: E402
from game_lib import (Harness, S, EMU_ARGS, K_KNIGHT, K_GOBLIN, K_RAT,  # noqa: E402
                      stand_y, attr_at, cell_bytes, frame_png)
import os  # noqa: E402

PNG_DIR = os.environ.get("DNUM_PNG")


def shot(name, fr):
    if PNG_DIR and fr:
        os.makedirs(PNG_DIR, exist_ok=True)
        frame_png(fr, os.path.join(PNG_DIR, name + ".png"), scale=2)
        print(f"[png] {os.path.join(PNG_DIR, name + '.png')}", flush=True)
from proj3 import T, w16  # noqa: E402

STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT = 1, 2, 4, 8
STF, ST1, ST2, STX = S["ST_FLAGS"], S["ST_T1"], S["ST_T2"], S["ST_X"]
FROZEN = 1
HY = stand_y(1, 6)
HX = 12
NOWHERE = 7
LIVE, LSTR, NLIVE = S["DN_LIVE"], S["DN_LIVE_STRIDE"], S["DN_LIVE_N"]
DL = {k: S["DL_" + k] for k in ("SLOT", "COL", "ROW", "AGE", "ATTR", "W", "VAL")}
GLY = S["DL_GLY"]
SLOTS = S["DN_SLOT"]
PP = S["probe_presented"]
PP_BP = 5                                     # (1 / 2 probes, 3 X's scroll step, 4 present_watch)
LAG = 2                                       # dn_gate: a 2nd-frame tick spawns from the last scan's queue only


class Tm(T, game.T):
    pass


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = Tm(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:700]}", flush=True)

        if S.get("KIT_DEBUG", 0):
            print("[skip] dnum needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(h, p, check)
        print(f"dnum: {len(fails)} failed" + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def sval(v):
    return "MISS" if v == 0x80 else (v - 256 if v & 0x80 else v)


def run(h, p, check):
    kt, slots = {}, {}

    def place(slot, x, y, flags, hp=None):
        kw = dict(X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=p.rb("CUR_ROOM"), FLAGS=flags, REACT=0,
                  FLT=0, HIT=0)
        if hp is not None:
            kw.update(HP=hp, MAXHP=hp)
        p.set_ent(slot, **kw)

    def scene(mons, hx=HX, hhp=200, hero=K_KNIGHT, settle=4):
        p.boot(hero, freeze=0)
        if not kt:
            kt.update(p.kinds())
        room = p.rb("CUR_ROOM")
        for sl in range(1, 16):
            e = p.ent(sl)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                p.set_ent(sl, ROOM=NOWHERE)
        place(0, hx, HY, EF_ACTIVE | EF_PLAYER, hhp)
        out, used = [], set()
        for kind, x, y, left, hp in mons:
            pool = [s for s in range(1, 16) if s not in used]
            sl = next((s for s in pool if p.ent(s)["KIND"] == kind), pool[0])
            used.add(sl)
            p.set_ent(sl, KIND=kind)
            place(sl, x, HY + 6 - kt[kind]["bh"] if y is None else y,
                  EF_ACTIVE | EF_HOSTILE | (EF_LEFT if left else 0), hp)
            out.append(sl)
        for a in (STF, ST1, ST2, STX):
            p.wmem(a, [0] * 16)
        resync()
        p.tick(settle)
        return out

    def resync():
        """test pokes (HP / slots) are not game events: every slot resyncs, no number."""
        ps = p.rb("DN_PASS")
        for s in range(16):
            p.wb(SLOTS + 4 * s + S["DS_SEEN"], (ps + 128) & 255)
            p.wb(SLOTS + 4 * s + S["DS_FLG"], 0)
        for e in range(NLIVE):
            p.wb(LIVE + e * LSTR + DL["SLOT"], 0xFF)

    def live():
        out = []
        for e in range(NLIVE):
            r = p.z.read_memory(LIVE + e * LSTR, 8)
            d = {k: r[o] for k, o in DL.items()}
            if d["SLOT"] != 0xFF:
                out.append((e, d["SLOT"], d))
        return out

    def of(slot):
        for e, s, r in live():
            if s == slot:
                return r
        return None

    def bg(c, r):
        tabs = p.bg_tables()
        return bytes(tabs[1][tabs[0][r * 32 + c] * 8:][:8])

    def shadow_attr(c, r):
        p.z.cmd("set-memory-zone 0")
        try:
            a = p.z.read_memory(7 * 16384 + (S["SHADOW_ATTR"] - 0xC000) + r * 32 + c, 1)[0]
        finally:
            p.z.cmd("set-memory-zone -1")
        return a

    def is_bg(c, r, fr=None):
        fr = fr or p.composed_frame()
        return bytes(cell_bytes(fr, c, r)) == bg(c, r) and attr_at(fr, c, r) == shadow_attr(c, r)

    def window(r):
        return [(c, rr) for c in range(r["COL"], r["COL"] + r["W"]) for rr in (r["ROW"] - 1, r["ROW"])]

    def at_pres(n=1):
        """n ticks, each stopped at probe_presented (present + dn_fix done: screen 2 is
        final for the tick; bank 5 still holds the previous tick's render)."""
        p.z.cmd("set-breakpoint %d PC=%d" % (PP_BP, PP))
        p.extra_probes = {PP}
        try:
            for _ in range(n):
                for _ in range(4):
                    p.tick()
                    if p.pc() == PP:
                        break
        finally:
            p.z.cmd("set-breakpoint %d" % PP_BP)
            p.extra_probes = set()

    def shadow_all():
        p.z.cmd("set-memory-zone 0")
        try:
            return p.z.read_memory(7 * 16384 + (S["SHADOW_ATTR"] - 0xC000), 18 * 32)
        finally:
            p.z.cmd("set-memory-zone -1")

    def boff(c, r, line):
        y = r * 8 + line
        return ((y & 0xC0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2) | c

    stats = {"ticks": 0, "cells": 0, "sprite": 0, "kept_attr": 0, "num_attr": 0, "bad": []}

    def model7(tag, fr7=None):
        """Screen 2 vs the model (module doc), every cell of the screen. Returns (bad
        cells, {drawn cell: bank-5 lines != its map glyph, i.e. a body / mark / FX under
        the digit}); counts into stats (sprite = such cells, kept_attr / num_attr = the
        attr rule's two cases). A cell drawn by two live numbers is skipped (the later
        draw wins; the spawn order is not the record order)."""
        fr5 = p.composed_frame()
        fr7 = fr7 or p.frame()
        sh = shadow_all()
        tabs = p.bg_tables()
        exp = bytearray(fr5)
        owners = {}
        for e in range(NLIVE):
            r = p.z.read_memory(LIVE + e * LSTR, LSTR)
            if r[DL["SLOT"]] == 0xFF:
                continue
            k = min(r[DL["AGE"]] - 1, 8)
            for ci in range(r[DL["W"]]):
                z = bytes(8) + bytes(r[GLY + 8 * ci:GLY + 8 * ci + 8]) + bytes(8)
                c = r[DL["COL"]] + ci
                rows = []
                if k >= 1:
                    rows.append((r[DL["ROW"]] - 1, z[k:k + 8]))
                if k <= 7:
                    rows.append((r[DL["ROW"]], z[8 + k:16 + k]))
                for rr, src in rows:
                    owners[(c, rr)] = owners.get((c, rr), 0) + 1
                    for ln in range(8):
                        exp[boff(c, rr, ln)] = fr5[boff(c, rr, ln)] | src[ln]
                    a5 = fr5[6144 + rr * 32 + c]
                    exp[6144 + rr * 32 + c] = r[DL["ATTR"]] if a5 == sh[rr * 32 + c] else a5
        bad, under = [], {}
        for rr in range(24):
            for c in range(32):
                offs = [boff(c, rr, ln) for ln in range(8)] + [6144 + rr * 32 + c]
                if owners.get((c, rr), 0) < 2 and any(exp[o] != fr7[o] for o in offs):
                    bad.append((c, rr))
        for (c, rr), n in owners.items():
            if n > 1:
                continue
            stats["cells"] += 1
            g = bytes(tabs[1][tabs[0][rr * 32 + c] * 8:][:8])
            sp = bytes(fr5[boff(c, rr, ln)] for ln in range(8)) != g
            under[(c, rr)] = sp
            stats["sprite"] += sp
            if fr5[6144 + rr * 32 + c] != sh[rr * 32 + c]:
                stats["kept_attr"] += 1
            else:
                stats["num_attr"] += 1
        stats["ticks"] += 1
        if bad:
            stats["bad"].append((tag, bad[:6]))
        return bad, under

    def num_lines(r, fr):
        """The window's 16 lines per cell (rows row-1, row), minus the tile glyph."""
        out = []
        for c in range(r["COL"], r["COL"] + r["W"]):
            col = b""
            for rr in (r["ROW"] - 1, r["ROW"]):
                g = bg(c, rr)
                col += bytes(x & ~t & 0xFF for x, t in zip(cell_bytes(fr, c, rr), g))
            out.append(col)
        return out

    rnd = random.Random(11)
    rm0 = [None]

    def attack_until(want_hit, tries=40):
        """The Knight swings at the Goblin on his right until a hit (want_hit) /
        a miss; per tick from the input tick: (E_REACT, its live record, HP)."""
        for _ in range(tries):
            g = scene([(K_GOBLIN, HX + 3, None, True, 60)])[0]
            if rm0[0] is None:
                rm0[0] = bytes(p.z.read_memory(S["ROOM_MAP"], 576))
            hp0 = p.ent(g)["HP"]
            p.wmem(S["RNG_STATE"], [rnd.randrange(256), rnd.randrange(1, 256)])
            keys, _ = p._prep(("L",))
            t0 = p.rw("TURN_COUNTER")
            p.hold(*keys)
            for _ in range(5):
                p.tick()
                if p.rb("TURN_PHASE") == 1 or p.rw("TURN_COUNTER") != t0:
                    break
            p.release()
            tr, frames = [], []
            for i in range(40):
                at_pres()
                e = p.ent(g)
                tr.append((e["REACT"], of(g), e["HP"]))
                fr7 = p.frame()
                frames.append(fr7)
                model7("H/M", fr7)
            if (p.ent(g)["HP"] < hp0) == want_hit:
                return g, hp0, tr, frames
        return None

    # ====================== H: a melee hit =====================================
    res = attack_until(True)
    check("H setup: a Knight hit on the Goblin within 40 swings", res is not None)
    if res:
        g, hp0, tr, frames = res
        hp1 = tr[-1][2]
        first = next((i for i, t in enumerate(tr) if t[1]), None)
        started = next((i for i, t in enumerate(tr) if t[0] & 0x80), None)
        pend = [i for i, t in enumerate(tr) if 0 < t[0] < 0x80]
        check("H the number spawns once the reaction started (never while pending), lag <= 2",
              first is not None and started is not None and 0 <= first - started <= LAG and pend
              and max(pend) < first, (first, started, pend[:3], [(t[0], bool(t[1])) for t in tr[:16]]))
        if first is not None and started is not None:
            print(f"[info] H spawn lag after the reaction start: {first - started} tick(s)", flush=True)
        r = tr[first][1] if first is not None else None
        check("H value = -(HP lost), attr $47, width 2/3 cells",
              r and sval(r["VAL"]) == -(hp0 - hp1) and r["ATTR"] == 0x47 and r["W"] == (2 if hp0 - hp1 < 10 else 3),
              (r, hp0, hp1))
        if r:
            sr = p.rb(S["SLOTREC"] + g * 16 + S["R_ROW"])
            sc = p.rb(S["SLOTREC"] + g * 16 + S["R_COL"])
            sw = p.rb(S["SLOTREC"] + g * 16 + S["R_COLS"])
            check("H placed over the body: row = drawn top - 1, centred on R_COL / R_COLS",
                  r["ROW"] == sr - 1 and r["COL"] == sc + (sw - r["W"]) // 2, (r, sr, sc, sw))
            shot("dnum_hit_monster", frames[first + 3])
            seq = [num_lines(r, frames[first + 1 + k]) for k in range(9)]
            ok = all(seq[k + 1][0][:15] == seq[k][0][1:16] for k in range(7))
            nz = [any(c) for c in seq[0]]
            check("H drawn: every cell has number pixels; rises 1 px per pass for 8 passes",
                  ok and all(nz), ([s[0].hex() for s in seq[:3]], nz))
            ages = [t[1]["AGE"] if t[1] else None for t in tr[first:first + 14]]
            check("H lives 12 passes (age 1..12 seen), then the entry is free",
                  ages[:12] == list(range(1, 13)) and ages[12] is None, ages)
            at_pres(3)
            fr7 = p.frame()
            bad = [cl for cl in window(r) if not is_bg(*cl, fr=fr7)]
            check("H after expiry every displayed window cell == map glyph + shadow attr", not bad, bad)

    # ====================== M: a melee miss ====================================
    res = attack_until(False)
    check("M setup: a Knight miss within 40 swings", res is not None)
    if res:
        g, hp0, tr, frames = res
        first = next((i for i, t in enumerate(tr) if t[1]), None)
        r = tr[first][1] if first is not None else None
        check("M MISS spawned on the Goblin (value MISS, attr $45, 3 cells)",
              r and r["VAL"] == 0x80 and r["ATTR"] == 0x45 and r["W"] == 3, (first, r))

    # ====================== P: the hero hit ====================================
    got = None
    for _ in range(30):
        g = scene([(K_GOBLIN, HX + 3, None, True, 60)], hhp=200)[0]
        p.wb(S["kind_tab"] + S["KT_ATK"] + K_GOBLIN, 30)      # (the Goblin always hits)
        hp0 = p.ent(0)["HP"]
        p.turn("WAIT")
        for _ in range(30):
            if of(0):
                got = (of(0), hp0 - p.ent(0)["HP"])
                break
            p.tick()
        if got:
            if PNG_DIR:
                at_pres(3)
                shot("dnum_hit_hero", p.frame())
            break
    check("P the hero struck by a Goblin: -n in $42 on the hero",
          got and sval(got[0]["VAL"]) == -got[1] and got[0]["ATTR"] == 0x42, got)

    # ====================== E: a heal (potion) =================================
    scene([], hhp=200)
    p.set_ent(0, HP=5, MAXHP=30)
    resync()
    p.tick(3)
    p.turn("G")
    tr = []
    for i in range(20):
        tr.append((p.ent(0)["HP"], of(0)))
        p.tick()
    first = next((i for i, t in enumerate(tr) if t[1]), None)
    r = tr[first][1] if first is not None else None
    gain = tr[-1][0] - 5
    check("E Heal potion: +n (HP gained) in $44 on the hero",
          r and gain > 0 and sval(r["VAL"]) == gain and r["ATTR"] == 0x44, (first, r, gain))
    p.tick(14)
    p.set_ent(0, HP=30, MAXHP=30)
    resync()
    p.tick(3)
    p.turn("G")
    p.tick(6)
    check("E a heal at max HP: no number", of(0) is None, of(0))

    # ====================== S: a poison tick ===================================
    scene([], hhp=40)
    hp = p.ent(0)["HP"]
    p.wb(STX, 3)
    p.poke_hp(0, hp - 2)
    p.tick()
    r = of(0)
    check("S an unreacted hero HP loss while poisoned: -2 in $43", r and sval(r["VAL"]) == -2 and r["ATTR"] == 0x43, r)
    p.wb(STX, 0)

    # ====================== D: 9-bit deltas ====================================
    scene([], hhp=200)
    p.poke_hp(0, 40)
    p.tick(2)
    r = of(0)
    check("D the hero 200 -> 40: -99 (not +96)", r and sval(r["VAL"]) == -99 and r["ATTR"] == 0x42, r)
    p.tick(14)
    p.poke_hp(0, 200)
    p.tick(2)
    r = of(0)
    check("D the hero 40 -> 200: +99 (not -96)", r and sval(r["VAL"]) == 99 and r["ATTR"] == 0x44, r)

    # ====================== L: a level-up (silent) =============================
    scene([], hhp=50)
    p.tick(14)
    e = p.ent(0)
    p.wb(S["P_ENTITIES"] + S["E_MAXHP"], e["MAXHP"] + 5)   # the raw bytes: a real level-up
    p.poke_hp(0, e["HP"] + 5)
    p.tick(3)
    check("L MAXHP and HP + 5 together (level-up / tome): no number", of(0) is None, of(0))
    # D3-11 review: a blow and a level-up between the same two passes: the rise is taken off
    # the change, the blow still shows (was: dropped as silent -> a cyan "0" from the HURT)
    scene([], hhp=150)
    p.set_ent(0, MAXHP=200)
    p.tick(14)
    p.poke_hp(0, 143)                         # the blow: -7
    p.poke_hp(0, 148)                         # ... and the level-up's HP + 5 (raw: MAXHP + 5)
    p.wb(S["P_ENTITIES"] + S["E_MAXHP"], 205)
    p.wb(S["P_ENTITIES"] + S["E_REACT"], 0x80 | S["RC_HURT"])   # its HURT running
    p.tick(3)
    r = of(0)
    check("L a blow + a level-up between two passes: -7 in $42 (the rise taken off, not '0')",
          r and sval(r["VAL"]) == -7 and r["ATTR"] == 0x42, r)

    # ====================== C: 4 unreacted changes, left to right ==============
    xs = (20, 3, 25, 8)                       # slot order != x order
    gs = scene([(K_GOBLIN, x, None, x > HX, 60) for x in xs])
    for sl in gs:
        p.poke_hp(sl, 50)
    order, mx, seen = [], 0, []
    for i in range(6):
        p.tick()
        lv = live()
        mx = max(mx, len(lv))
        seen.append(sorted(s for _, s, _ in lv))
        for _, s, _ in lv:
            if s not in order:
                order.append(s)
    want = [sl for _, sl in sorted(zip(xs, gs))]
    check("C one spawn a pass, left to right (E_X), <= 3 live, the 4th ends the oldest",
          order == want and [len(x) for x in seen[:4]] == [1, 2, 3, 3] and mx == 3
          and want[0] not in seen[3], (want, order, seen))

    # ====================== G: no ghost on a replacement =======================
    g = scene([(K_GOBLIN, HX + 8, None, True, 60)])[0]
    p.poke_hp(g, 50)
    p.tick(6)                                 # -10 risen 5 px: both rows drawn
    r0 = dict(of(g) or {})
    p.poke_hp(g, 55)                          # +5: opposite sign, replaces it
    at_pres(2)                                # (the next pass replaces it; its marks presented)
    r1 = of(g)
    fr = p.frame()
    model7("G", fr)
    stale = [cl for cl in window(r0) if r1 and cl[1] == r0.get("ROW", 0) - 1 and not is_bg(*cl, fr=fr)]
    check("G a replaced number: +5 $44 at age 1, its old upper row is background in the same pass",
          r0 and r1 and sval(r1["VAL"]) == 5 and r1["AGE"] == 1 and r1["ATTR"] == 0x44 and not stale,
          (r0, r1, stale))

    # ====================== W: Whirlwind, the ripple ===========================
    for attempt in range(8):
        gs = scene([(K_GOBLIN, HX - kt[K_GOBLIN]["bw"], None, False, 40),
                    (K_RAT, HX + 3, None, True, 40)], settle=3)
        p.wmem(S["ARANK"], w16(1 << 2))       # Whirlwind rank 1
        p.wb("MP", 20)
        p.wb("MAXMP", 20)
        hp0 = {sl: p.ent(sl)["HP"] for sl in gs}
        p.select_slot(2)
        p.wmem(S["RNG_STATE"], [rnd.randrange(256), rnd.randrange(1, 256)])
        p.tap("FIRE")
        order, recs = [], {}
        for i in range(30):
            p.tick()
            for _, s, rr in live():
                if s not in order and s in gs:
                    order.append(s)
                    recs[s] = dict(rr)
        struck = [sl for sl in gs if sl in recs]
        if len(struck) == 2 and attempt >= 2:
            break
    xs = {sl: p.ent(sl)["X"] for sl in gs}
    ok_vals = all((sval(recs[s]["VAL"]) == -(hp0[s] - p.ent(s)["HP"])) if p.ent(s)["HP"] < hp0[s]
                  else recs[s]["VAL"] == 0x80 for s in struck)
    check("W Whirlwind: every struck body -n (its HP lost) or MISS, spawned in E_X order",
          len(struck) == 2 and ok_vals and order == sorted(order, key=lambda s: xs[s]),
          (gs, order, {s: (sval(r["VAL"]), hp0[s], p.ent(s)["HP"]) for s, r in recs.items()}, xs))

    # ====================== K: over a status mark ==============================
    g = scene([(K_GOBLIN, HX + 8, None, True, 60)])[0]
    p.wb(STF + g, FROZEN)
    p.wb(ST1 + g, 0xF0)
    p.tick(4)
    had = p.rb(S["SLOTREC"] + g * 16 + S["R_MK"]) != 0
    p.poke_hp(g, 50)
    at_pres(3)                                # spawned by the next pass, risen 1 px by the one after
    r = of(g)
    fr, fr5 = p.frame(), p.composed_frame()
    sh = shadow_all()
    bad, under = model7("K", fr)
    cells = window(r) if r and 1 <= r["AGE"] - 1 <= 7 else []      # k 1..7: both rows drawn
    marked = [cl for cl in cells if attr_at(fr5, *cl) != sh[cl[1] * 32 + cl[0]]]
    bare = [cl for cl in cells if cl not in marked]
    ok = (r and marked and all(attr_at(fr, *cl) == attr_at(fr5, *cl) and
                               all(a & b == b for a, b in zip(cell_bytes(fr, *cl), cell_bytes(fr5, *cl)))
                               for cl in marked)
          and all(attr_at(fr, *cl) == r["ATTR"] for cl in bare) and not bad)
    check("K a FROZEN Goblin's mark: the number ORs over it (the mark's pixels + attr kept, bare cells "
          "the number's attr; screen 2 == model7)", had and ok, (had, r, marked, bare, bad))
    p.wb(STF + g, 0)

    # ====================== X: a room exit =====================================
    # the Knight at room A's right exit (x 28, as game.py #34), a number live on him, walk right
    scene([], hx=28, hhp=200)
    p.poke_hp(0, 190)
    p.tick(2)
    r = dict(of(0) or {})
    tabs = p.bg_tables()
    exp = {(c, rr): bytes(tabs[1][tabs[0][rr * 32 + c] * 8:][:8]) for c, rr in window(r)} if r else {}
    step = S["hscroll_room.step"]
    hit = None
    room0 = p.rb("CUR_ROOM")
    if r:
        p.z.cmd("set-breakpoint 3 PC=%d" % step)
        p.extra_probes = {step}
        p.hold("L")
        for _ in range(200):
            p.tick()
            if p.pc() == step:
                fr = p.composed_frame()
                hit = [cl for cl, g8 in exp.items() if bytes(cell_bytes(fr, *cl)) != g8]
                break
        p.release()
        p.z.cmd("set-breakpoint 3")
        p.extra_probes = set()
        p.tick(30)
    at_pres()
    same = p.frame() == p.composed_frame()
    check("X a room exit: the number's cells are background at the first scroll step, none live after, "
          "the arrival's displayed screen == the composed one",
          r and hit == [] and not live() and p.rb("CUR_ROOM") != room0 and same,
          (r, hit, live(), p.rb("CUR_ROOM"), same))

    # ====================== R: ROOM_MAP, screens ===============================
    g = scene([(K_GOBLIN, HX + 8, None, True, 60)])[0]
    p.poke_hp(g, 40)
    p.tick(16)
    rm1 = bytes(p.z.read_memory(S["ROOM_MAP"], 576))
    check("R ROOM_MAP unchanged by the numbers (room A as the first scene)", rm0[0] == rm1)
    at_pres()
    check("R all expired: composed screen == presented (bank 7)", not live() and p.composed_frame() == p.frame())

    # ====================== Z: a body at the top row (Y 0) =====================
    # review of c7d72fe: dn_place's clamp gave DL_ROW $FF for a drawn top of 0 (row - 1 before the
    # compare), and the window wrote bank-7 code ($D8xx..$DFxx). The window must stay rows 0 / 1.
    def b7(a, n):
        p.z.cmd("set-memory-zone 0")
        try:
            return bytes(p.z.read_memory(7 * 16384 + (a - 0xC000), n))
        finally:
            p.z.cmd("set-memory-zone -1")

    zr = scene([(K_RAT, 20, 0, True, 40)])[0]
    code0 = b7(S["B7_CODE"], S["B7_LIMIT"] - S["B7_CODE"])
    p.poke_hp(zr, 30)
    zrec, zbad = None, []
    for _ in range(4):
        at_pres()
        zrec = zrec or (dict(of(zr)) if of(zr) else None)
        zbad += model7("Z")[0]
    check("Z a body at the top row (Y 0): the number's window = rows 0 / 1 (DL_ROW 1), bank-7 code untouched, "
          "screen 2 == model7", zrec and zrec["ROW"] == 1 and not zbad
          and b7(S["B7_CODE"], S["B7_LIMIT"] - S["B7_CODE"]) == code0, (zrec, zbad[:4]))

    # ====================== Y: LVL-FLOATER, "+LVL" at a real level-up ==========
    # xp7 .nr sets the hero's DS_FLG bit 7; dn_cls ranks it as a MISS-kind candidate, dn_lvt (bank 2)
    # puts "+LVL" + $46 in DN_TXT, dn_take composes it as MISS's 3-cell text. Render-only.
    def font_lines(txt):
        out = []
        for ci in range(3):
            col = []
            for ln in range(8):
                bits = 0
                for ch in txt:
                    g = p.z.read_memory(S["FONT6"] + (ln >> 1) * 256 + ord(ch) + (ln & 1) * S["FONT6_WB"], 1)[0]
                    bits = (bits << 6) | (g >> 2)
                col.append((bits >> (16 - 8 * ci)) & 0xFF)
            out.append(bytes(col))
        return out

    def ofl(slot):
        """LVL-KEEP: a live "+LVL" is filed as slot | $80 (dn_find never matches it)."""
        return of(slot | 0x80)

    code0 = b7(S["B7_CODE"], S["B7_LIMIT"] - S["B7_CODE"])
    scene([], hhp=50)
    xp_next = p.z.read_memory(S["xpn_tab"], 2)
    lvl0 = p.rb("LVL")
    map0 = bytes(p.z.read_memory(S["ROOM_MAP"], 576))
    p.wmem(S["XP"], [xp_next[0], xp_next[1]])
    p.wb("XP_UP", 1)
    p.turn("WAIT")
    tr, yrec, ybad, yglyph, yshot = [], None, [], b"", None
    for _ in range(30):
        at_pres()
        r = ofl(0)
        tr.append(dict(r) if r else None)
        if r and yrec is None:
            yrec = dict(r)
            yglyph = bytes(p.z.read_memory(LIVE + LSTR * next(e for e, s, _ in live() if s == 0x80) + GLY, 24))
            yshot = p.frame()
        ybad += model7("Y")[0]
    ages = [t["AGE"] if t else None for t in tr]
    first = next((i for i, t in enumerate(tr) if t), None)
    check("Y a level-up (LVL +1): +LVL spawns on the hero: value MISS, attr $46, 3 cells",
          p.rb("LVL") == lvl0 + 1 and yrec and yrec["VAL"] == 0x80 and yrec["ATTR"] == 0x46 and yrec["W"] == 3
          and yrec["SLOT"] == 0x80, (p.rb("LVL"), lvl0, yrec))
    if yrec:
        shot("dnum_levelup", yshot)
        want = b"".join(font_lines("+LVL"))
        miss = b"".join(font_lines("MISS"))
        check("Y the composed text is +LVL (FONT6 lines, not MISS), over the hero (row = drawn top - 1)",
              yglyph == want and want != miss and yrec["ROW"] == p.rb(S["SLOTREC"] + S["R_ROW"]) - 1,
              (yglyph.hex(), want.hex(), yrec))
        check("Y lives 12 passes then the entry is free; the DS_FLG bits are consumed",
              ages[first] <= 4 and ages[first:first + 13 - ages[first]] == list(range(ages[first], 13))
              and ages[first + 13 - ages[first]] is None and p.rb(SLOTS + S["DS_FLG"]) == 0,
              (ages[first:first + 14], p.rb(SLOTS + S["DS_FLG"])))   # (the first sample is a few passes in)
        at_pres(3)
        fr7 = p.frame()
        bad = [cl for cl in window(yrec) if not is_bg(*cl, fr=fr7)]
        check("Y after expiry every window cell == map glyph + shadow attr (erased cleanly), "
              "screen 2 == model7 every tick, ROOM_MAP and bank-7 code untouched",
              not bad and not ybad and bytes(p.z.read_memory(S["ROOM_MAP"], 576)) == map0
              and b7(S["B7_CODE"], S["B7_LIMIT"] - S["B7_CODE"]) == code0, (bad, ybad[:3]))
    # a hero miss line owed in the same pass as the level-up: one +LVL (both bits consumed)
    scene([], hhp=50)
    p.wb(SLOTS + S["DS_FLG"], 0x81)
    p.tick(2)
    r = ofl(0)
    check("Y a miss line + a level-up on the hero together: one +LVL ($46), both flag bits consumed",
          r and r["VAL"] == 0x80 and r["ATTR"] == 0x46 and p.rb(SLOTS + S["DS_FLG"]) == 0,
          (r, p.rb(SLOTS + S["DS_FLG"])))
    # a monster's MISS is never +LVL, even with the hero's bit pending
    g = scene([(K_GOBLIN, HX + 8, None, True, 60)])[0]
    p.wb(SLOTS + S["DS_FLG"], 0x80)
    p.wb(SLOTS + 4 * g + S["DS_FLG"], 1)
    p.tick(4)
    rg, rh = of(g), ofl(0)
    check("Y a Goblin's MISS stays MISS ($45) beside the hero's +LVL ($46), each on its body",
          rg and rh and rg["VAL"] == 0x80 and rg["ATTR"] == 0x45 and rh["ATTR"] == 0x46, (rg, rh))
    # a blow on the hero and a level-up between two passes: the blow's -n first, +LVL kept for after
    scene([], hhp=150)
    p.set_ent(0, MAXHP=200)
    p.tick(14)
    p.wb(SLOTS + S["DS_FLG"], 0x80)
    p.poke_hp(0, 143)
    p.wb(S["P_ENTITIES"] + S["E_REACT"], 0x80 | S["RC_HURT"])
    seen = []
    for _ in range(10):
        p.tick()
        r = of(0)
        seen.append((sval(r["VAL"]), r["ATTR"]) if r else None)
        r = ofl(0)
        seen.append((sval(r["VAL"]), r["ATTR"]) if r else None)
    check("Y a blow + a level-up: the -7 shows first, the +LVL is kept (not lost) and follows",
          (-7, 0x42) in seen and ("MISS", 0x46) in seen and seen.index((-7, 0x42)) < seen.index(("MISS", 0x46)),
          seen)

    # LVL-KEEP: a number spawned N passes after the +LVL must not replace it (it once did: the
    # MISS-valued "+LVL" was "replaceable"): +LVL keeps its whole 12 passes (value MISS, attr $46,
    # age +1 a pass, never rewritten) and the -n shows beside it in its own entry. N = 1..8, a monster
    # blow (hurt reaction) and a poison tick; model7 exact every tick.
    def lvl_then(n, poison):
        scene([], hhp=150)
        p.set_ent(0, MAXHP=200)
        p.tick(14)
        p.wb(SLOTS + S["DS_FLG"], 0x80)
        for _ in range(8):
            p.tick()
            if ofl(0):
                break
        at_lvl = ofl(0)
        k = 0
        while ofl(0) and ofl(0)["AGE"] < n + 1 and k < 20:
            at_pres()
            k += 1
        hp = p.ent(0)["HP"]
        if poison:
            p.wb(STX, 3)
            p.poke_hp(0, hp - 3)
        else:
            p.poke_hp(0, hp - 7)
            p.wb(S["P_ENTITIES"] + S["E_REACT"], 0x80 | S["RC_HURT"])
        want = -3 if poison else -7
        lv, dm, bad = [], [], []
        for _ in range(16):
            at_pres()
            a, d = ofl(0), of(0)
            lv.append((a["AGE"], a["VAL"], a["ATTR"]) if a else None)
            dm.append(sval(d["VAL"]) if d else None)
            bad += model7("Y")[0]
        if poison:
            p.wb(STX, 0)
        return at_lvl, lv, dm, bad, want

    for poison, ns in ((False, range(1, 9)), (True, (1, 4, 8))):
        for n in ns:
            at_lvl, lv, dm, bad, want = lvl_then(n, poison)
            live_l = [x for x in lv if x]
            ages = [x[0] for x in live_l]
            gone = lv.index(None) if None in lv else len(lv)
            ok = (at_lvl and live_l and all(x[1:] == (0x80, 0x46) for x in live_l)
                  and ages == sorted(set(ages)) and ages[-1] == 12 and all(x is None for x in lv[gone:])
                  and want in dm and not bad)
            check("Y a %s %d passes after the +LVL: +LVL keeps its full life (MISS $46, ages up to 12), the %d "
                  "appears beside it, model7 exact" % ("poison tick" if poison else "blow", n, want), ok,
                  (n, lv, dm, bad[:3]))

    # ====================== V / Q: a body walking through a standing number ====
    def walk_through(tag, walker, silent=False):
        """A Rat at x 18 takes -10 (silent: the same HP set as no event), its number
        spawns; the Rat is parked (the number stays, its body gone) and the walker
        crosses the window: None = the hero, holding right (real turns); else a
        Goblin from the right stepped 4 px left a tick (its PX / X poked before each
        render: a monster's AI walk is too slow for a number's 12 passes; render,
        its damage rects and present run as for a real step). Per tick at
        probe_presented: (screen 2, model7 result, the record, the walker's X)."""
        mons = [(K_RAT, HX + 6, None, True, 40)]
        if walker is not None:
            mons.append((walker, HX + 10, None, True, 60))    # right of the Rat (x 18..21, window 18..20)
        sl = scene(mons, hx=HX if walker is not None else HX + 3, settle=4)
        rat = sl[0]
        if silent:
            p.set_ent(rat, HP=30)
        else:
            p.poke_hp(rat, 30)
        at_pres(2)
        r = dict(of(rat) or {})
        p.set_ent(rat, ROOM=NOWHERE)
        if walker is None:
            p.hold("L")
        out = []
        for i in range(22):
            if walker is not None:
                px = p.ent(sl[-1])["PX"] - 4
                p.set_ent(sl[-1], PX=px, X=px // 8)
            at_pres()
            fr7 = p.frame()
            res = model7(tag, fr7) if not silent else ([], {})
            out.append((fr7, res, dict(of(rat) or {}), p.ent(sl[-1] if walker is not None else 0)["X"]))
        p.release()
        return r, out

    for tag, walker, who in (("V", None, "the hero"), ("Q", K_GOBLIN, "a Goblin")):
        n0 = dict(stats)
        r, run = walk_through(tag, walker)
        _, ctl = walk_through(tag, walker, silent=True)
        drawn = [i for i, (_, _, rr, _) in enumerate(run) if rr]
        bad = [(i, res[0][:4]) for i, (_, res, _, _) in enumerate(run) if res[0]]
        over = [i for i, (_, res, _, _) in enumerate(run) if any(res[1].values())]
        gone = drawn[-1] + 1 if drawn else 0
        if over:
            shot(f"dnum_walk_{'hero' if walker is None else 'goblin'}", run[over[len(over) // 2]][0])
        same_after = all(a[0] == b[0] for a, b in zip(run[gone + 1:], ctl[gone + 1:]))
        check(f"{tag} a number left standing while {who} walks through it: every tick screen 2 == model7, "
              f"{who}'s pixels under the digit in >= 2 ticks",
              r and drawn and not bad and len(over) >= 2, (r, drawn, bad[:3], over, [x[3] for x in run]))
        check(f"{tag} the attr rule seen: kept (a sprite's attr) and the number's (bare) cells",
              stats["kept_attr"] > n0["kept_attr"] and stats["num_attr"] > n0["num_attr"],
              (stats["kept_attr"] - n0["kept_attr"], stats["num_attr"] - n0["num_attr"]))
        check(f"{tag} after expiry screen 2 == the control run's (the same HP change, no number)",
              drawn and gone < len(run) - 2 and same_after,
              (gone, [i for i, (a, b) in enumerate(zip(run, ctl)) if a[0] != b[0]][:8]))

    check("MODEL every sampled tick (H M G K V Q): screen 2 == model7 (bank 5 | the number, attr rule)",
          not stats["bad"], stats["bad"][:6])
    print(f"[info] model7: {stats['ticks']} ticks, {stats['cells']} number cells, {stats['sprite']} over a "
          f"body / mark / FX, attr kept {stats['kept_attr']} / the number's {stats['num_attr']}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
