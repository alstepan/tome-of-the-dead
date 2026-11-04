#!/usr/bin/env python3
"""ENDCARD-K (user playtest 2026-11-04: "i died but the game over screen did not show the ghost who
killed me"). Release build (DEBUG_KIT=0), seeded generated games, the real level_descend (boss.Lair).

Cause: a Mage's Spark / Lightning (DTY_SHOCK) is reflected by a Ghost (RSP_X) and kills its caster;
ENDCARD-G1 counted that as his own bolt (ATK_PTR = the hero -> ST1_KILLER 0 -> "YOU DIED", no
portrait). Fix: proj3 records the reflector (pf_rfl), deal_hit's hero death -> bank-2 dh_killer.

The portrait model (every case): the killer's first KS_MOVE fid from the sequence MASTERS
(build/ovl/seq.bin, ksm_tab: not the game's per-level cache), its FRT row resident (shift 0, else the
shift-4 variant at x + 4: ec_port), and the card's cols 0..8 x rows EC_FEET-8..EC_FEET-1 == that
variant's data bytes on black (blit = (screen AND mask) OR data, line-major (mask, data) pairs) at
(EC_PCOL_L * 8, EC_FEET * 8 - FT_H), nothing else; the attr box rows EC_FEET-8.. x cols
EC_PCOL_L..+FT_COLS == the kind's KT_ATTR; the title KILLED BY + the kind name (menu font).

  K   every monster kind 2..29 (bases on an lp_dtab depth listing them, the bosses on their depth,
      tiers on their base's depth, K_VBAT on the Vampire's) killed the hero through deal_hit (stub,
      attacker = the kind, slot 1): ST1_KILLER = $80 | kind + the card; heroes alternate
  R1  Mage, D6, Ghost in line (right, then left): Spark (real cast, HP 1) reflected -> GS_DEAD,
      ST1_KILLER $85, the Ghost's portrait;  R2 the same with Lightning on D3 (pierce + reflect)
  R3  Warrior / Mage, D6: the Ghost's own DRAIN touch through real turns (ANIM_FREEZE 0) -> $85 + card
  N1  a reflected Spark the Mage survives (HP 200), then trap_hit at HP 1 (stub): ST1_KILLER 0 (no stale
      reflector), the card says YOU DIED with no portrait
Run: WZ_BUILD_DIR=<dir>/build ZRCP_PORT=<port> python3 tests/endcard_k.py [--png DIR]
"""
import os
import sys
from pathlib import Path

ARGV = list(sys.argv)                                   # (world.py, imported by boss, resets sys.argv)
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
import game_lib as GL                                   # noqa: E402
from game_lib import Harness, S, EMU_ARGS, cell_bytes, attr_at, frame_png  # noqa: E402
from boss import Lair                                   # noqa: E402
from lp import T, w16                                   # noqa: E402
from world import menu_text_ok, STRINGS                 # noqa: E402

PNG = Path(ARGV[ARGV.index("--png") + 1]) if "--png" in ARGV else None
KIT = bool(S.get("KIT_DEBUG", 0))
STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT = 1, 2, 4, S["EF_LEFT"]
GS_PLAYING, GS_DEAD = S["GS_PLAYING"], S["GS_DEAD"]
FEET, PCOL, TROW = S["EC_FEET"], S["EC_PCOL_L"], S["EC_TROW"]
K_GHOST = 5
NOWHERE = 7
fails = []


def check(name, ok, got=None):
    if not ok:
        fails.append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f": got {str(got)[:400]}"), flush=True)


def sna(bank, addr, n):
    o = bank * 16384 + (addr - 0xC000)
    return GL.SNA_RAM[o:o + n]


SEQ = (Path(GL.BUILD_DIR) / "ovl" / "seq.bin").read_bytes()


def move_fid(kind):
    """The first fid of kind's KS_MOVE cycle in the sequence masters (ksm_tab: tiers name their base)."""
    t = S["ksm_tab"] - S["SQ_IMG"]
    blk = SEQ[t + 2 * kind] | SEQ[t + 2 * kind + 1] << 8
    b = blk - S["SQ_IMG"]
    off = SEQ[b + S["KSM_OFF"] + S["KS_MOVE"] // 2]
    return SEQ[b + S["KSM_SEQ"] + off + 1]              # cycle: DB total, fid, ticks, ...


def kname(kind):
    for n, t in STRINGS:
        if n.startswith("nm_") and S.get("TX_NM_" + n[3:].upper()) == S["TX_NM_KNIGHT"] + kind:
            return t
    raise KeyError(kind)


def kind_depths():
    """kind -> a depth whose level generates its frames: lp_dtab (bank 3) kinds + boss, tier rows
    (R6 tier_tab) -> their base's depth, K_VBAT -> the Vampire's."""
    lp = sna(3, S["lp_dtab"], 8 * S["LP_DROW"])
    dep = {}
    for d in range(8):
        row = lp[d * 6:d * 6 + 5]
        for k in row:
            dep.setdefault(k & S["LEK_KIND_MASK"], d + 1)
    tt = sna(S["BANK_R6"], S["tier_tab"], 3 * S["TIER_N"])
    for i in range(S["TIER_N"]):
        for t in tt[i * 3 + 1:i * 3 + 3]:
            if t:
                dep.setdefault(t, dep[tt[i * 3]])
    dep.setdefault(S["K_VBAT"], dep[S["K_VAMPIRE"]])
    return dep


def portrait_ok(p, fr, kind):
    """(ok, detail): the card's left portrait == kind's first KS_MOVE frame (model in the docstring)."""
    fid = move_fid(kind)
    row = p.z.read_memory(S["FRT"] + fid * S["FRT_STRIDE"], S["FRT_STRIDE"])
    cols, hh = row[S["FT_IN_ROW"] + S["FT_COLS"]], row[S["FT_IN_ROW"] + S["FT_H"]]
    v, x = 0, PCOL * 8
    if row[0] == S["FRT_NONE"]:
        v, x = 1, x + 4
    bank, lo, hi = row[3 * v:3 * v + 3]
    if bank == S["FRT_NONE"] or fid < S["KFID_MONSTERS"]:
        return False, f"fid {fid}: no resident variant (bank {bank}) / a hero fid"
    w = cols + v
    p.z.cmd("set-memory-zone 0")
    try:
        data = bytes(p.z.read_memory(bank * 16384 + ((hi << 8 | lo) - 0xC000), hh * 2 * w))
    finally:
        p.z.cmd("set-memory-zone -1")
    y0 = FEET * 8 - hh
    want = {}
    for ln in range(hh):
        for b in range(w):
            want[(y0 + ln, (x >> 3) + b)] = data[(ln * w + b) * 2 + 1]
    bad = []
    for y in range((FEET - 8) * 8, FEET * 8):
        for c in range(0, 9):
            a = ((y & 0xC0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2) | c
            if fr[a] != want.get((y, c), 0):
                bad.append((c, y, fr[a], want.get((y, c), 0)))
    att = p.kb(kind, "KT_ATTR")
    abad = [(c, r) for r in range(FEET - 8, FEET) for c in range(PCOL, PCOL + cols + 1) if attr_at(fr, c, r) != att]
    ink = sum(bin(b).count("1") for b in want.values())
    return (not bad and not abad and ink > 0), f"fid {fid} v{v} ink {ink} bad {bad[:4]} attr {abad[:4]}"


def main():
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)
        if KIT:
            print("[skip] endcard_k needs a DEBUG_KIT=0 build", flush=True)
            return 0
        if not S.get("ENDCARD_RK"):
            print("[skip] endcard_k needs ENDCARD_RK = 1 (release, no ANIM_TRACE_ON)", flush=True)
            return 0

        def ingame(code):
            pc0 = p.pc()
            ok, _ = p.code(code, game=True)
            p.z.cmd("set-register PC=%d" % pc0)
            return ok

        def bank3_call(body):
            return ingame([0x3A] + w16(S["PORT_7FFD_SHADOW"]) + [0xF5, 0x3E, 3, 0xCD] + w16(S["page_bank"])
                          + body + [0xF1, 0xCD] + w16(S["restore_page"]))

        def setup(depth, hero, seed):
            L = Lair(p, depth, seed, hero=hero)
            room = p.rb("CUR_ROOM")
            for k in range(1, 16):
                if p.ent(k)["ROOM"] == room:
                    p.set_ent(k, ROOM=NOWHERE)
            p.wb("ST1_KILLER", 0)
            return L.ok, room

        def put(kind, room, dx, left_hero=False):
            """Slot 1 = kind, |dx| cols from the hero on his floor, facing him; the hero faces it."""
            e0 = p.ent(0)
            hk = p.rb("HERO_KIND")
            y = e0["Y"] + p.kb(hk, "KT_BH") - p.kb(kind, "KT_BH")
            x = e0["X"] + dx
            p.set_ent(1, KIND=kind, X=x, Y=y, PX=x * 8, PY=y * 8, ROOM=room, MODE=0, REACT=0, FLT=0, HIT=0,
                      HP=5, MAXHP=5, FLAGS=EF_ACTIVE | EF_HOSTILE | (EF_LEFT if dx > 0 else 0))
            p.wmem(S["ST_FLAGS"] + 1, [0])
            p.wmem(S["ST_T1"] + 1, [0])
            p.set_ent(0, FLAGS=(e0["FLAGS"] & ~EF_LEFT & 0xFF) | (EF_LEFT if dx < 0 else 0))

        def card(tag, kind):
            """GS_DEAD reached (or set): tick to the card, then the title + portrait checks."""
            if p.rb("GAME_STATE") != GS_DEAD:
                p.wb("GAME_STATE", GS_DEAD)
            p.end_card(8)
            p.settle(4)
            fr = p.frame()
            if PNG:
                frame_png(fr, PNG / f"{tag.replace(' ', '_')}.png")
            if kind is None:
                ok = menu_text_ok(p, fr, TROW, 12, "YOU DIED")
                blank = all(cell_bytes(fr, c, r) == bytes(8) for r in range(FEET - 8, FEET) for c in range(9))
                check(f"{tag}: YOU DIED, no portrait", ok and blank, (ok, blank))
                return
            nm = kname(kind)
            tc = (22 - len(nm)) // 2
            ok = menu_text_ok(p, fr, TROW, tc, "KILLED BY") and menu_text_ok(p, fr, TROW, tc + 10, nm)
            pok, det = portrait_ok(p, fr, kind)
            check(f"{tag}: title KILLED BY {nm}", ok)
            check(f"{tag}: portrait == {nm}'s first KS_MOVE frame + KT_ATTR box", pok, det)

        def cast(slot, abl):
            p.wmem(S["ARANK"], w16(1 << (2 * abl)))
            p.wb("MAXMP", 40)
            p.wb("MP", 40)
            p.tick(2)
            p.select_slot(slot)
            t0 = p.rw("TURN_COUNTER")
            p.tap("FIRE")
            for _ in range(300):
                if p.rb("GAME_STATE") == GS_DEAD or (p.rw("TURN_COUNTER") != t0 and p.idle()):
                    break
                p.tick()
            return p.rb("pf_rev"), p.rb("pf_rfl")

        # ------------------------------------------------------------- K: every killer kind
        dep = kind_depths()
        kinds = sorted(k for k in dep if 2 <= k < S["K_COUNT"])
        check("K setup: every monster kind 2..29 has a depth", kinds == list(range(2, S["K_COUNT"])),
              sorted(set(range(2, S["K_COUNT"])) - set(kinds)))
        for i, k in enumerate(kinds):
            d, hero = dep[k], i & 1
            ok, room = setup(d, hero, 0x4E00 + 16 * d + k)
            put(k, room, 4)
            p.set_ent(0, HP=1)
            bank3_call([0xDD, 0x21] + w16(S["P_ENTITIES"] + STRIDE) + [0x3E, 0, 0x01, 0, 99, 0x1E, 0, 0xCD]
                       + w16(S["deal_hit"]))
            got = p.rb("ST1_KILLER")
            check(f"K {kname(k)} (kind {k}) D{d} hero {hero}: ST1_KILLER = {0x80 | k:#x}",
                  ok and got == 0x80 | k and p.ent(0)["HP"] == 0, (ok, hex(got), p.ent(0)["HP"]))
            card(f"K {kname(k)}", k)

        # ------------------------------------------------------------- R: reflected bolts
        for dx in (4, -4):
            ok, room = setup(6, 1, 0x6E06)
            put(K_GHOST, room, dx)
            p.set_ent(0, HP=1)
            rev, rfl = cast(1, S["ABL_SPARK"])
            check(f"R1 Mage D6 Spark reflected by the Ghost (dx {dx}): GS_DEAD, ST1_KILLER $85",
                  ok and rev >= 1 and rfl == 1 and p.rb("GAME_STATE") == GS_DEAD and p.rb("ST1_KILLER") == 0x85,
                  (ok, rev, rfl, p.rb("GAME_STATE"), hex(p.rb("ST1_KILLER"))))
            card(f"R1 Spark dx {dx}", K_GHOST)
        ok, room = setup(3, 1, 0x3E03)
        put(K_GHOST, room, 4)
        p.set_ent(0, HP=1)
        rev, rfl = cast(1 + S["ABL_LIGHTNING"], S["ABL_LIGHTNING"])
        check("R2 Mage D3 Lightning reflected by the Ghost: GS_DEAD, ST1_KILLER $85",
              ok and rev >= 1 and p.rb("GAME_STATE") == GS_DEAD and p.rb("ST1_KILLER") == 0x85,
              (ok, rev, rfl, p.rb("GAME_STATE"), hex(p.rb("ST1_KILLER"))))
        card("R2 Lightning", K_GHOST)
        for hero in (0, 1):
            ok, room = setup(6, hero, 0x6E16)
            p.wb("ANIM_FREEZE", 0)
            put(K_GHOST, room, 4)
            n = 0
            while p.rb("GAME_STATE") != GS_DEAD and n < 30:
                if not p.ent(0)["FLAGS"] & S["EF_DYING"]:
                    p.set_ent(0, HP=1)
                p.turn("WAIT")
                n += 1
            check(f"R3 hero {hero} D6: the Ghost's touch through real turns -> GS_DEAD, ST1_KILLER $85",
                  ok and p.rb("GAME_STATE") == GS_DEAD and p.rb("ST1_KILLER") == 0x85,
                  (ok, n, p.rb("GAME_STATE"), hex(p.rb("ST1_KILLER"))))
            card(f"R3 touch hero {hero}", K_GHOST)

        # ------------------------------------------------------------- N: no stale reflector
        ok, room = setup(6, 1, 0x6E06)
        put(K_GHOST, room, 4)
        p.set_ent(0, HP=200, MAXHP=200)
        rev, rfl = cast(1, S["ABL_SPARK"])
        alive = p.rb("GAME_STATE") == GS_PLAYING and p.ent(0)["HP"] > 0
        p.set_ent(1, ROOM=NOWHERE)
        p.set_ent(0, HP=1)
        bank3_call([0xCD] + w16(S["trap_hit"]))
        check("N1 a reflected Spark survived (pf_rfl set), then a trap kills: ST1_KILLER 0",
              ok and rfl == 1 and alive and p.ent(0)["HP"] == 0 and p.rb("ST1_KILLER") == 0,
              (ok, rfl, alive, p.ent(0)["HP"], hex(p.rb("ST1_KILLER"))))
        card("N1 trap after reflect", None)
    print(f"endcard_k: {len(fails)} failed" + (f": {fails[:10]}" if fails else ""), flush=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
