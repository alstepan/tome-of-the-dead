#!/usr/bin/env python3
"""D8-AUDIT: the last level (the Necromancer Archmage lair + the Sanctum) under stress, empirically.
Seeded generated games (F3_GEN build, DEBUG_KIT=0), the real level_descend D7 -> D8, the hero walked
into the lair through the non-Sanctum door (real do_exit + lp_transition), then scripted fights.

  F   N-turn fights (Warrior + Mage, several seeds): every turn the invariants below; before / after
      the fight the canary regions (memory-map region list) are snapshotted and diffed:
      ROOM_MAP == room_model, NEXT_MAP, ITEM_RAM, LVL_STATE..LVL_STATE_END (FLOOR_LIST, TRAP_LIST,
      EDGE_TAB, TOME_HP; LVL_FLAGS / TRK_* masked), LP_STATE (the lair record), kind_tab (KT_ATTR
      Archmage masked), bank 7 TSET_BASE..$FFFF + B7_CODE..B7_LIMIT == the .sna, bank 0 text..POOL_START
      == the .sna, the pool (bank 0 POOL_START.., banks 4 / 6) + FRT == as at the lair entry, bank 6
      SRC6 + R6, bank 3 / bank 1 / AY reserve, the stack (pattern-filled: max depth), SP at every
      wait_tick probe (stack balance).
      Invariants per turn: GS_PLAYING, every live body in CUR_ROOM, <= 1 live summon-made body
      (the cap), a new summon: Skeleton, hp = max = KT_HP + depth - 1, E_GOLD 0, F_RESPAWN +
      RCD_SUMMONED, a legal box (sp_try rules) not on the hero / a body / ladder / hole; the
      Archmage: standing, never moves except a blink to the other storey (once a life), KT_ATTR in
      the ORDER inks; no slot DYING for > 12 turns (corpse / ash slots freed); summon cooldown >= 6
      turns between two summons (S) unless a blink reset it.
  E   the lair escort (game.md 9.4.4) alive, S not poked: the Archmage summons within 40 turns (hard check;
      the summon is exempt from LP_SIGMA_CAP, user 2026-11-01).
      Every other scenario removes the escort first (kill_escort).
  S   50 summons in a row (each killed at once, S poked 0): free-slot count stable.
  K   kills: by the Mirror Helm return; by a ranged attack at the door; while a summon lives (then
      leave + re-enter: summon discarded, Archmage not back, LF_UNIQUE); after: GS_PLAYING, seal
      open, the slot freed, 20 more turns clean.
  R   trk_run after the Archmage's death (D8: LF_SEAL_OPEN + LF_UNIQUE, LF_GRATE_OPEN never set):
      game.md 9.5 says the trickle stops; hard check (control: LF_GRATE_OPEN).
  T   teleport mid-fight (summon alive, FX in flight): summon discarded, FX idle after, the lair
      record holds the Archmage only; re-entry: KT_ATTR $43, ST_X init bit clear, P = 0.
  W   into the Sanctum (seal open) with a summon at the door: does it follow? lectern cells free;
      5 Tome hits -> gate open (WIN2), walk out, DOWN at the exit col -> GS_WIN; KT_ATTR after a new game D1 -> D8 lair entry = $43.
  C   a summon killed on the turn the Archmage re-summons: sp_run reuses the corpse slot before the next render;
      sp_place failing (blocked) or not, no corpse frame at the top-left (fix/d8-corpse-topleft).
  G   the Archmage drawn at every x on both storeys: the playfield outside the sprites == ROOM_MAP in
      source glyphs (gfx_integrity.screen_check), pool + FRT unchanged.
Exit 1 on a FAIL or an ANOMALY; NOTEs (design / doc mismatches) are listed only. ~16 min at the defaults.
Run: ZRCP_PORT=<port> WZ_BUILD_DIR=<dir>/build python3 tests/d8_stress.py [--turns N] [--seeds a,b,c] [--only EFSKRTWGC]
"""
import argparse
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import room_model  # noqa: E402
import game_lib as GL  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, stand_y, F3  # noqa: E402
from lp import T as Proto, w16  # noqa: E402
import gfx_integrity as GI  # noqa: E402

STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT, EF_DYING, EF_PENDING = 1, 2, 4, S["EF_LEFT"], S["EF_DYING"], S["EF_PENDING"]
GS_PLAYING, GS_WIN, GS_DEAD = S["GS_PLAYING"], S["GS_WIN"], S["GS_DEAD"]
KA, KSK = S["K_ARCHMAGE"], S["K_SKELETON"]
INK = S["kind_tab"] + S["KT_ATTR"] + KA
ORDER_INKS = {0x43, 0x45, 0x47, 0x44, 0x42}
RCD_SUMMONED, RCD_SUMMON = S["RCD_SUMMONED"], 0x3C
E_RCD, E_GOLD, E_MSG = S["E_RCD"], S["E_GOLD"], S["E_MSG"]
TF = {k: S["TF_" + k] for k in ("SOLID", "FLOOR", "HOLE", "LADDER", "DOOR")}
BANK = 16384
fails = []
anoms = []


def check(name, ok, got=None):
    if not ok:
        fails.append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f": got {str(got)[:1500]}"), flush=True)
    return ok


notes = []


def note(tag, detail):
    """A design / doc mismatch seen (not a failure): listed at the end."""
    notes.append((tag, detail))
    print(f"[NOTE] {tag}: {str(detail)[:800]}", flush=True)


def anomaly(tag, detail):
    anoms.append((tag, detail))
    print(f"[ANOM] {tag}: {str(detail)[:1500]}", flush=True)


# ------------------------------------------------------------------ symbols
_LAB = sorted((v, k) for k, v in S.items() if re.match(r"^[a-z_][a-z0-9_]*$", k) or k.isupper())


def near(addr):
    """Nearest symbol at or below addr (labels and EQUs; ambiguous for paged banks)."""
    best = None
    for v, k in _LAB:
        if v > addr:
            break
        if addr - v < 0x400:
            best = (v, k)
    return f"{best[1]}+{addr - best[0]:#x}" if best else "?"


def ranges(a, b, base):
    out, run = [], None
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            if run and i <= run[1] + 2:
                run[1] = i
            else:
                run = [i, i]
                out.append(run)
    return [(base + lo, base + hi) for lo, hi in out]


# ------------------------------------------------------------------ the listing: is a changed byte flagged SMC / scratch?
_LST = {}


def lst_index():
    if _LST:
        return _LST
    rx = re.compile(r"^\s*\d+[+~>]*\s*([0-9A-F]{4})\s((?:[0-9A-F]{2} ?)+)\s*(.*)$")
    rd = re.compile(r"^\s*\d+[+~>]*\s*([0-9A-F]{4})\s+(?:[A-Za-z_.][\w.]*:)?\s*(DS|DEFS|BLOCK)\b\s*([^;]*)", re.I)
    cur = "?"
    for line in open(Path(GL.BUILD_DIR) / "tome-of-the-dead.lst", errors="replace"):
        if line.startswith("# file opened:"):
            cur = line.split("/src/")[-1].strip() if "/src/" in line else line.split("/")[-1].strip()
            continue
        m = rx.match(line)
        if m:
            a = int(m.group(1), 16)
            for i in range(len(m.group(2).split())):
                _LST.setdefault(a + i, []).append((cur, line.rstrip()[:140]))
            continue
        m = rd.match(line)
        if m:
            a = int(m.group(1), 16)
            try:
                n = int(eval(m.group(3).split(",")[0].replace("$", "0x"), {}, dict(S)))
            except Exception:
                n = 1
            for i in range(min(n, 4096)):
                _LST.setdefault(a + i, []).append((cur, "DS " + line.rstrip()[:120]))
    return _LST


def classify(lo, hi):
    """'smc' / 'scratch' / 'unflagged' + a sample listing line for the changed range lo..hi."""
    ix = lst_index()
    kinds, sample = set(), None
    for a in range(lo, hi + 1):
        ls = [l_ for l_ in ix.get(a, []) if not l_[0].startswith("../build/zx0")]
        if any("SMC" in t for _, t in ls):
            kinds.add("smc")
            sample = sample or next(t for _, t in ls if "SMC" in t)
        elif any(t.startswith("DS ") for _, t in ls):
            kinds.add("scratch")
            sample = sample or next(f"{f}: {t}" for f, t in ls if t.startswith("DS "))
        else:
            kinds.add("unflagged")
            sample = sample or (ls[0] if ls else "(no listing line)")
    return ("unflagged" if "unflagged" in kinds else "smc" if "smc" in kinds else "scratch"), sample


def bank_read(p, b, addr, n):
    return GI.bank_read(p, b, addr, n)


def sna_bank(b, addr, n):
    return GI.sna_bank(b, addr, n)


# ------------------------------------------------------------------ the level
class D8:
    def __init__(self, p, master, hero, boot=True):
        self.p, self.master, self.hero = p, master, hero
        if boot:
            p.proto_start = 0
            p.boot(hero=hero, freeze=1)
        self.descend()

    def descend(self):
        """MASTER_SEED, the real level_descend D7 -> D8, the lair's non-Sanctum door unlocked."""
        p = self.p
        p.wmem(S["MASTER_SEED"], w16(self.master))
        self.ingame([0x3E, 7, 0x32] + w16(S["LVL_DEPTH"]) + [0xCD] + w16(S["level_descend"]))
        p.release()
        p.settle(4)
        self.ok = p.rb("LVL_DEPTH") == 8 and p.rb("GAME_STATE") == GS_PLAYING
        self.blk = room_model.read_block(p)
        self.sn, self.lair = p.rb("LVL_SANCTUM"), p.rb("LVL_LAIR")
        ex = room_model.field(self.blk, self.lair, "RD_EXITS")
        # the non-Sanctum horizontal neighbour of the lair
        self.side = "L" if self.sn == self.lair + 1 else "R"
        self.nb = self.lair - 1 if self.side == "L" else self.lair + 1
        self.s = 1 if ex & S["RDX_LS1" if self.side == "L" else "RDX_RS1"] else 0
        sside = "R" if self.side == "L" else "L"
        self.ss = 1 if ex & S["RDX_LS1" if sside == "L" else "RDX_RS1"] else 0
        self.sedge = S["EDGE_TAB"] + room_model.edge_index(self.lair, sside)
        ei = S["EDGE_TAB"] + room_model.edge_index(self.lair, self.side)
        p.wb(ei, (p.rb(ei) & ~(S["EG_LOCK"] | S["EG_SEAL"]) & 255) | (S["EG_OPEN"] if p.rb(ei) & S["EG_DOOR"] else 0))
        self.kw = p.kb(p.rb("HERO_KIND"), "KT_BW")
        self.kh = p.kb(p.rb("HERO_KIND"), "KT_BH")
        self.aw, self.ah = p.kb(KA, "KT_BW"), p.kb(KA, "KT_BH")
        self.tflags = list(p.z.read_memory(S["tile_flags"], 64))
        self.tag = f"{'W' if self.hero == 0 else 'M'} {self.master:#06x}"

    def ingame(self, code):
        p = self.p
        pc0 = p.pc()
        ok, _ = p.code(code, game=True)
        p.z.cmd("set-register PC=%d" % pc0)
        return ok

    def put_hero(self, r, x, s_, left=False):
        p = self.p
        p.wb("CUR_ROOM", r)
        y = stand_y(s_, self.kh)
        p.set_ent(0, ROOM=r, X=x, Y=y, PX=x * 8, PY=y * 8, FLAGS=EF_ACTIVE | EF_PLAYER | (EF_LEFT if left else 0),
                  MODE=0, DVIS=0)
        self.ingame([0x3E, r, 0xCD] + w16(S["room_show"]) + [0xCD] + w16(S["vis_reset"])
                    + [0xCD] + w16(S["present_full"]))
        p.settle(2)

    def place(self, x, s_, left=False):
        y = stand_y(s_, self.kh)
        self.p.set_ent(0, X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0,
                       FLAGS=EF_ACTIVE | EF_PLAYER | (EF_LEFT if left else 0))

    def enter(self):
        """From the non-Sanctum neighbour into the lair through the real do_exit."""
        p = self.p
        for k in range(1, 16):
            if p.ent(k)["ROOM"] != self.lair:
                p.set_ent(k, FLAGS=0)
        x, key = (32 - 2 - self.kw, "L") if self.side == "L" else (2, "H")
        ro = S["LP_REC"] + 9 * self.nb
        if not p.rb(ro) & 0x80:
            p.wmem(ro, [0x80] + [0] * 8)
        self.put_hero(self.nb, x, self.s, left=(self.side == "R"))
        for _ in range(24):
            if p.rb("CUR_ROOM") == self.lair:
                break
            p.set_ent(0, HP=200)
            p.turn(key)
        p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
        p.settle(2)
        return p.rb("CUR_ROOM") == self.lair

    def leave(self):
        p = self.p
        x = 2 if self.side == "L" else 32 - 2 - self.kw
        self.place(x, self.s, left=(self.side == "L"))
        p.tick(2)
        key = "H" if self.side == "L" else "L"
        for _ in range(12):
            if p.rb("CUR_ROOM") == self.nb:
                break
            p.set_ent(0, HP=200)
            p.turn(key)
        p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
        p.settle(2)
        return p.rb("CUR_ROOM") == self.nb

    def deal(self, attacker, target, dmg):
        return self.ingame([0x3A] + w16(S["PORT_7FFD_SHADOW"]) + [0xF5, 0x3E, 3, 0xCD] + w16(S["page_bank"])
                           + [0xDD, 0x21] + w16(S["P_ENTITIES"] + attacker * STRIDE)
                           + [0x3E, target, 0x01, 0, dmg, 0x1E, 0, 0xCD] + w16(S["deal_hit"])
                           + [0xF1, 0xCD] + w16(S["restore_page"]))

    # --- world reads
    def ents(self):
        b = self.p.z.read_memory(S["P_ENTITIES"], 16 * STRIDE)
        out = {}
        for s_ in range(16):
            r = b[s_ * STRIDE:(s_ + 1) * STRIDE]
            out[s_] = dict(KIND=r[0], ROOM=r[1], FLAGS=r[2], X=r[3], Y=r[4], HP=r[5], MAXHP=r[6], RCD=r[E_RCD],
                           GOLD=r[E_GOLD], MSG=r[E_MSG], raw=bytes(r))
        return out

    def arch(self, es=None):
        es = es or self.ents()
        for s_ in range(1, 16):
            e = es[s_]
            if e["FLAGS"] & EF_ACTIVE and not e["FLAGS"] & EF_DYING and e["KIND"] == KA:
                return s_
        return None

    def legal(self, m, kind, x, y, es, skip=()):
        """sp_try's rules on ROOM_MAP m (walker): cols in LP_XMIN..LP_XMAX, no live body overlap,
        floor cells TF_FLOOR without hole / ladder, standing-row cells not solid / ladder / door."""
        w, h = self.p.kb(kind, "KT_BW"), self.p.kb(kind, "KT_BH")
        why = []
        if x < S["LP_XMIN"] or x + w - 1 > S["LP_XMAX"]:
            why.append("cols")
        for s_, e in es.items():
            if s_ in skip or not e["FLAGS"] & EF_ACTIVE or e["FLAGS"] & EF_DYING:
                continue
            if e["ROOM"] != self.p.rb("CUR_ROOM") and s_ != 0:
                continue
            ew, eh = self.p.kb(e["KIND"], "KT_BW"), self.p.kb(e["KIND"], "KT_BH")
            if x < e["X"] + ew and e["X"] < x + w and y < e["Y"] + eh and e["Y"] < y + h:
                why.append(f"body{s_}")
        fr = y + h
        for c in range(x, x + w):
            if not 0 <= c < 32 or fr >= 18:
                why.append("oob")
                break
            f = self.tflags[m[fr * 32 + c] & 63]
            if f & (TF["FLOOR"] | TF["HOLE"] | TF["LADDER"]) != TF["FLOOR"]:
                why.append(f"floor{c}")
            g = self.tflags[m[(fr - 1) * 32 + c] & 63]
            if g & (TF["SOLID"] | TF["LADDER"] | TF["DOOR"]):
                why.append(f"stand{c}")
        return why


# ------------------------------------------------------------------ canaries
LOW = [("ROOM_MAP", S["ROOM_MAP"], 576), ("NEXT_MAP", S["NEXT_MAP"], 576), ("ITEM_RAM", S["ITEM_RAM"], S["ITEM_RAM_LEN"]),
       ("LVL_STATE", S["LVL_STATE"], S["LVL_STATE_END"] - S["LVL_STATE"]), ("LP_STATE", S["LP_STATE"], S["LP_LEN"]),
       ("kind_tab", S["kind_tab"], S["KT_END"])]
LVL_MASK = {S["LVL_FLAGS"], S["EDGE_TAB"] + 4, S["EDGE_TAB"] + 5, S["EDGE_TAB"] + 6, S["EDGE_TAB"] + 7,
            S["GEN_RNG"], S["GEN_RNG"] + 1}           # TRK_PHASE / TRK_PREV (EDGE_TAB + 6 / 7), the trickle's GEN_RNG


def snap(p):
    sn = {n: bytes(p.z.read_memory(a, ln)) for n, a, ln in LOW}
    sn["FRT"] = bytes(p.z.read_memory(S["FRT"], S["FRT_MAX"] * S["FRT_STRIDE"]))
    p.z.cmd("set-memory-zone 0")
    try:
        ram = bytes(p.z.read_memory(0, 8 * BANK))
    finally:
        p.z.cmd("set-memory-zone -1")
    for b in (0, 1, 3, 4, 6, 7):
        sn[f"bank{b}"] = ram[b * BANK:(b + 1) * BANK]
    sn["bank2"] = ram[2 * BANK:3 * BANK]
    return sn


def masked(name, a, b, base):
    rr = ranges(a, b, base)
    if name == "LVL_STATE":
        rr = [(lo, hi) for lo, hi in rr if not all(x in LVL_MASK for x in range(lo, hi + 1))]
    if name == "kind_tab":
        rr = [(lo, hi) for lo, hi in rr if not (lo == hi == INK)]
    return rr


def stack_fill(p):
    """Pattern below the live stack (STACK_BOTTOM .. SP - 32) at a probe; returns the fill top."""
    sp = int(re.search(r"SP=([0-9a-fA-F]{4})", p.z.cmd("get-registers")).group(1), 16)
    lo, top = 0xBE00, sp - 32
    p.wmem(lo, [0xA5] * (top - lo))
    return top


def stack_low(p, top):
    m = p.z.read_memory(0xBE00, top - 0xBE00)
    for i, v in enumerate(m):
        if v != 0xA5:
            return 0xBE00 + i
    return None


def sp_now(p):
    return int(re.search(r"SP=([0-9a-fA-F]{4})", p.z.cmd("get-registers")).group(1), 16)


def _bank_of(f):
    m = re.search(r"(\d)\.asm$", f)
    return int(m.group(1)) if m and f[:-5] not in ("main", "ay") else None


def classify_b(b, lo, hi):
    """classify() with the listing lines of files named for another bank (x3.asm, x6.asm..) dropped."""
    ix = lst_index()
    kinds, sample = set(), None
    for a in range(lo, hi + 1):
        ls = [l_ for l_ in ix.get(a, []) if not l_[0].startswith("../build/zx0")
              and (_bank_of(l_[0]) in (None, b) or b is None)]
        if any("SMC" in t for _, t in ls):
            kinds.add("smc")
            sample = sample or next(f"{f}: {t}" for f, t in ls if "SMC" in t)
        elif any(t.startswith("DS ") for _, t in ls):
            kinds.add("scratch")
            sample = sample or next(f"{f}: {t}" for f, t in ls if t.startswith("DS "))
        elif any(re.search(r"\b(DB|DW|DEFB|DEFW)\b", t) for _, t in ls):
            kinds.add("var")
            sample = sample or next(f"{f}: {t}" for f, t in ls if re.search(r"\b(DB|DW|DEFB|DEFW)\b", t))
        else:
            kinds.add("unflagged")
            sample = sample or (f"{ls[0][0]}: {ls[0][1]}" if ls else "(no listing line)")
    return ("unflagged" if "unflagged" in kinds else "var" if "var" in kinds else
            "smc" if "smc" in kinds else "scratch"), sample


SEEN_CODE = {}


RUNTIME = {3: [(S["ay_vars"], S["ay_vars_end"])]}     # the AY player's state (ay.asm: ONE runtime block)


def code_diffs(b, old, cur, lo, tag, bad):
    rr = ranges(old, cur, lo)
    rr = [(a, z) for a, z in rr if not any(x <= a and z < y for x, y in RUNTIME.get(b, []))]
    unf = []
    for a, z in rr:
        k, smp = classify_b(b, a, z)
        SEEN_CODE.setdefault((b, k), set()).add((a, z, smp[:110] if smp else ""))
        if k == "unflagged":
            unf.append((f"{a:#06x}..{z:#06x}", smp[:120] if smp else ""))
    if unf:
        bad.append((f"bank {b} unflagged writes", unf[:10] + ([f"+{len(unf) - 10} more"] if len(unf) > 10 else [])))


def canary_compare(p, L, s0, s1, tag, room_ok=True):
    """s0 = at the lair entry, s1 = after. Report every changed range outside the expected set."""
    bad = []
    lair_rec = range(S["LP_REC"] + L.lair * S["LR_STRIDE"], S["LP_REC"] + (L.lair + 1) * S["LR_STRIDE"])
    # floor items: the hero may pick up the lair's generated items (an entry -> FL_EMPTY); nothing may
    # appear (summons are F_RESPAWN: no drops) or change otherwise
    fo = S["FLOOR_LIST"] - S["LVL_STATE"]
    f0, f1 = s0["LVL_STATE"][fo:fo + 128], s1["LVL_STATE"][fo:fo + 128]
    picked = [i for i in range(32) if f0[4 * i:4 * i + 4] != f1[4 * i:4 * i + 4] and f1[4 * i] == S["FL_EMPTY"]]
    other = [i for i in range(32) if f0[4 * i:4 * i + 4] != f1[4 * i:4 * i + 4] and f1[4 * i] != S["FL_EMPTY"]]
    if other:
        bad.append(("FLOOR_LIST entries added / changed (a drop?)", [(i, list(f0[4 * i:4 * i + 4]), list(f1[4 * i:4 * i + 4])) for i in other]))
    for n, a, ln in LOW:
        rr = masked(n, s0[n], s1[n], a)
        if n == "ROOM_MAP":       # compared with room_model below (pickups remove markers)
            continue
        if n == "LVL_STATE":
            rr = [(lo, hi) for lo, hi in rr if not (S["FLOOR_LIST"] <= lo and hi < S["FLOOR_LIST"] + 128)]
        if n == "ITEM_RAM":       # FOOD .. MP_HOLD (hunger_turn) tick every few turns; a pickup changes the bag / quick slots
            rr = [(lo, hi) for lo, hi in rr if not (S["FOOD"] <= lo and hi <= S["MP_HOLD"])]
            # STATS1 (merged after this test): ST1_CNT (KILLS word, best-kind BL / BXP) changes on every hero kill,
            # e.g. the Mage's Spark on a summoned Skeleton (the only diff of F M 0x5310 / 0x5312 on VAMP-BOSS)
            rr = [(lo, hi) for lo, hi in rr if not (S["ST1_CNT"] <= lo and hi <= S["ST2_CNT"] + S["ST2_LEN"] - 1)]   # + STATS2
            if picked:
                rr = []
        if n == "LP_STATE":       # the trickle (T12) state / other rooms' records may change; the lair's must not
            rr = [(lo, hi) for lo, hi in rr if any(x in lair_rec for x in range(lo, hi + 1))]
        if rr:
            bad.append((n, [(f"{lo:#06x}..{hi:#06x}", near(lo)) for lo, hi in rr[:6]]))
    rr = ranges(s0["FRT"], s1["FRT"], S["FRT"])
    if rr:
        bad.append(("FRT", [f"{lo:#06x}..{hi:#06x}" for lo, hi in rr[:6]]))
    if room_ok:
        m = list(p.z.read_memory(S["ROOM_MAP"], 576))
        want = room_model.render_room(room_model.read_block(p), p.rb("CUR_ROOM"))
        al = p.z.read_memory(S["ANIM_LIST"], S["ANIM_MAX"] * S["AL_STRIDE"])
        swap = {}
        for i in range(p.rb("ANIM_N")):
            e = al[i * S["AL_STRIDE"]:(i + 1) * S["AL_STRIDE"]]
            if e[S["AL_TYPE"]] >= S["AL_GLYPH_MIN"]:
                swap[e[S["AL_ROW"]] * 32 + e[S["AL_COL"]]] = e[S["AL_TYPE"]]
        # B3B-10 decor_tick exchanges a glyph-swap cell's id with its ANIM_LIST partner in ROOM_MAP
        diff = [(j % 32, j // 32, m[j], want[j]) for j in range(576)
                if m[j] != want[j] and swap.get(j) != want[j]]
        if diff:
            bad.append(("ROOM_MAP vs room_model", diff[:8]))
    for b, lo, hi in ((7, S["TSET_BASE"], 0x10000), (7, S["B7_CODE"], S["B7_LIMIT"]), (0, S["text_img"], S["POOL_START"])):
        rr = ranges(sna_bank(b, lo, hi - lo), s1[f"bank{b}"][lo - 0xC000:hi - 0xC000], lo)
        if rr:
            bad.append((f"bank {b} {lo:#06x}..{hi:#06x} != .sna", [(f"{a:#06x}..{z:#06x}", near(a)) for a, z in rr[:10]]))
    for b, lo, hi in ((0, S["POOL_START"], 0x10000), (4, 0xC000, 0x10000), (6, 0xC000, S["SRC6_ADDR"])):
        rr = ranges(s0[f"bank{b}"][lo - 0xC000:hi - 0xC000], s1[f"bank{b}"][lo - 0xC000:hi - 0xC000], lo)
        if rr:
            bad.append((f"pool bank {b} {lo:#06x}..{hi:#06x} != at the lair entry", [f"{a:#06x}..{z:#06x}" for a, z in rr[:10]]))
    # code banks: any change must be a flagged SMC operand or DS scratch (listing)
    for b, lo in ((6, S["SRC6_ADDR"]), (1, 0xC000), (3, 0xC000)):
        code_diffs(b, s0[f"bank{b}"][lo - 0xC000:], s1[f"bank{b}"][lo - 0xC000:], lo, tag, bad)
    b2o, b2n = s0["bank2"][:S["kind_tab"] - 0x8000], s1["bank2"][:S["kind_tab"] - 0x8000]
    code_diffs(2, b2o, b2n, 0x8000, tag, bad)
    lo2 = S["kind_tab"] + S["KT_SIZE"]
    code_diffs(2, s0["bank2"][lo2 - 0x8000:S["FRT"] - 0x8000], s1["bank2"][lo2 - 0x8000:S["FRT"] - 0x8000], lo2, tag, bad)
    return bad


# ------------------------------------------------------------------ the fight
class Fight:
    def __init__(self, L, rnd, mirror=False, keep_arch=True, kill_summons=3, poke_s=False, turns=300):
        self.L, self.p, self.rnd = L, L.p, rnd
        self.mirror, self.keep_arch, self.kill_summons, self.poke_s, self.turns = mirror, keep_arch, kill_summons, poke_s, turns
        self.n = 0
        self.summons_made = 0
        self.summon_turns = []
        self.summon_extra = []              # game turns beyond the 1st inside the detecting action (@2 / H cost 2)
        self.tc_pre = 0
        self.blinks = 0
        self.seen_slots = {}
        self.dying_since = {}
        self.sp0 = None
        self.stats = dict(casts=0, hexes=0, staff=0, wait=0, lost=0, other=0, noturn=0, storey_swaps=0)
        self.known = set()
        self.arch_pos = None
        self.arch_blinked = False
        self.inks = set()
        self.min_free = 15
        self.blink_turn = -99
        self.blink_tc = []
        self.room0 = self.p.rb("CUR_ROOM")

    def hero_prep(self):
        p = self.p
        p.set_ent(0, HP=200, MAXHP=200)
        p.wb("MP", 99)
        p.wb("MAXMP", 99)
        if self.mirror:
            r = p.rb(S["HERO_RES"] + 1)
            p.wb(S["HERO_RES"] + 1, r | (3 << 2))

    def action(self, es):
        """A scripted hero action (keys for p.turn)."""
        L, p, r = self.L, self.p, self.rnd
        a = L.arch(es)
        hx = es[0]["X"]
        u = r.random()
        toward = None
        if a is not None:
            toward = "L" if es[a]["X"] > hx else "H"
        st = 0 if es[0]["Y"] < 9 else 1
        if u < 0.30:
            return ("WAIT",)
        if u < 0.50 and toward:
            return (toward,)
        if u < 0.60 and toward:
            return ("H" if toward == "L" else "L",)
        if u < 0.68:
            return ("J",) if st == 0 else (r.choice(("K", "J")),)
        if u < 0.73:
            return ("place",)
        if L.hero == 0:
            return (r.choice(("C", "@1", "@2", "@3", "@4")),)
        return (r.choice(("C", "@1", "@1", "@2")),)

    def do(self, act, es):
        L, p = self.L, self.p
        hx = es[0]["X"]
        if act[0] in ("L", "H") and ((act[0] == "H" and hx <= 3) or (act[0] == "L" and hx + L.kw >= 29)):
            act = ("WAIT",)                       # never walk out of the room
        if act[0] == "place":
            m = list(p.z.read_memory(S["ROOM_MAP"], 576))
            for _ in range(30):
                s_ = self.rnd.randint(0, 1)
                x = self.rnd.randint(2, 29 - L.kw)
                if not L.legal(m, p.rb("HERO_KIND"), x, stand_y(s_, L.kh), es, skip=(0,)):
                    L.place(x, s_, left=self.rnd.random() < 0.5)
                    p.tick(2)
                    break
            act = ("WAIT",)
        ok = p.turn(*act, max_ticks=600)
        if not ok:
            self.stats["noturn"] += 1
            ok = p.turn("WAIT", max_ticks=600)
        if not ok:
            p.tick(6)
        return ok

    def check_turn(self, tag):
        L, p = self.L, self.p
        es = L.ents()
        gs = p.rb("GAME_STATE")
        cur = p.rb("CUR_ROOM")
        sp = sp_now(p)
        if self.sp0 is None:
            self.sp0 = sp
        elif sp != self.sp0:
            anomaly(f"{tag} turn {self.n}: SP at wait_tick moved", (hex(self.sp0), hex(sp)))
            self.sp0 = sp
        if gs != GS_PLAYING:
            return es, gs
        ink = p.rb(INK)
        self.inks.add(ink)
        if ink not in ORDER_INKS:
            anomaly(f"{tag} turn {self.n}: KT_ATTR Archmage not an ORDER ink", hex(ink))
        free = sum(1 for s_ in range(1, 16) if es[s_]["FLAGS"] == 0)
        self.min_free = min(self.min_free, free)
        m = list(p.z.read_memory(S["ROOM_MAP"], 576))
        live_summ = []
        for s_ in range(1, 16):
            e = es[s_]
            if not e["FLAGS"] & EF_ACTIVE:
                self.dying_since.pop(s_, None)
                continue
            if e["FLAGS"] & EF_DYING:
                d0 = self.dying_since.setdefault(s_, self.n)
                if self.n - d0 > 12:
                    anomaly(f"{tag} turn {self.n}: slot {s_} DYING since turn {d0}", e)
                    self.dying_since[s_] = self.n
                continue
            self.dying_since.pop(s_, None)
            if e["ROOM"] != cur and not e["FLAGS"] & EF_PENDING:
                anomaly(f"{tag} turn {self.n}: slot {s_} active in room {e['ROOM']} != CUR_ROOM {cur}", e)
            if e["RCD"] & RCD_SUMMONED:
                live_summ.append(s_)
            key = (s_, e["raw"][0], e["RCD"] & RCD_SUMMONED)
            if e["RCD"] & RCD_SUMMONED and key not in self.known and cur == L.lair and not e["FLAGS"] & EF_PENDING:
                self.known.add(key)
                self.summons_made += 1
                self.summon_turns.append(p.rw("TURN_COUNTER"))
                self.summon_extra.append(max(0, p.rw("TURN_COUNTER") - self.tc_pre - 1))
                want_hp = p.kb(KSK, "KT_HP") + p.rb("LVL_DEPTH") - 1
                why = L.legal(m, e["KIND"], e["X"], e["Y"], es, skip=(s_,))
                ok = (e["KIND"] == KSK and e["HP"] == want_hp and e["MAXHP"] == want_hp and e["GOLD"] == 0
                      and e["FLAGS"] & S["EF_RESPAWN"] and not why
                      and e["Y"] == stand_y(e["Y"] // 9 if e["Y"] < 9 else 1, p.kb(KSK, "KT_BH")))
                if not ok:
                    anomaly(f"{tag} turn {self.n}: summon slot {s_} wrong (want Skeleton hp {want_hp}, legal box)",
                            (e, why))
        for k in [k for k in self.known if not (es[k[0]]["FLAGS"] & EF_ACTIVE and es[k[0]]["RCD"] & RCD_SUMMONED)]:
            self.known.discard(k)
        if len(live_summ) > 1:
            anomaly(f"{tag} turn {self.n}: {len(live_summ)} live summons (cap: 1)", live_summ)
        a = L.arch(es)
        if a is not None:
            e = es[a]
            st = 0 if e["Y"] < 9 else 1
            if e["Y"] != stand_y(st, L.ah):
                anomaly(f"{tag} turn {self.n}: Archmage not standing", e)
            if e["GOLD"] != (p.rb("LP_BOSS") & S["LEK_GOLD"]):
                anomaly(f"{tag} turn {self.n}: Archmage E_GOLD", e["GOLD"])
            pos = (a, e["X"], e["Y"])
            if self.arch_pos and self.arch_pos[0] == a and pos != self.arch_pos:
                if (self.arch_pos[2] < 9) == (e["Y"] < 9):
                    anomaly(f"{tag} turn {self.n}: Archmage moved on its storey", (self.arch_pos, pos))
                self.blinks += 1
                self.blink_turn = self.n
                self.blink_tc.append(p.rw("TURN_COUNTER"))
                why = L.legal(m, KA, e["X"], e["Y"], es, skip=(a,))
                if why:
                    anomaly(f"{tag} turn {self.n}: blink box illegal", (pos, why))
                if self.blinks > 1:
                    anomaly(f"{tag} turn {self.n}: a 2nd blink in one life", pos)
            self.arch_pos = pos
            # box overlap with the hero
            h = es[0]
            if (e["X"] < h["X"] + L.kw and h["X"] < e["X"] + L.aw and e["Y"] < h["Y"] + L.kh and h["Y"] < e["Y"] + L.ah):
                anomaly(f"{tag} turn {self.n}: hero box overlaps the Archmage", (h, e))
        return es, gs

    def run(self, tag, n=None, on_turn=None):
        L, p = self.L, self.p
        n = n or self.turns
        for i in range(n):
            self.n += 1
            self.hero_prep()
            es = L.ents()
            a = L.arch(es)
            if a is not None and self.keep_arch and es[a]["HP"] < 10:
                p.set_ent(a, HP=30)
            if a is not None and self.poke_s:
                p.wb(S["P_ENTITIES"] + a * STRIDE + E_RCD, es[a]["RCD"] & ~RCD_SUMMON & 255)
            # kill summons that lived kill_summons turns
            if self.kill_summons is not None:
                for s_ in range(1, 16):
                    e = es[s_]
                    if e["FLAGS"] & EF_ACTIVE and not e["FLAGS"] & EF_DYING and e["RCD"] & RCD_SUMMONED:
                        t0 = self.seen_slots.setdefault((s_, self.summons_made), self.n)
                        if self.n - t0 >= self.kill_summons:
                            L.deal(0, s_, 99)
                            # (fix/d8-corpse-topleft: the next summon may take this slot on the same turn,
                            # so the slot never reads free in between: forget the body now)
                            self.known.discard((s_, e["raw"][0], e["RCD"] & RCD_SUMMONED))
            act = self.action(es)
            self.tc_pre = p.rw("TURN_COUNTER")
            self.do(act, es)
            if on_turn:
                on_turn(self)
            if p.rb("CUR_ROOM") != self.room0 and p.rb("GAME_STATE") == GS_PLAYING:
                anomaly(f"{tag} turn {self.n}: the hero left the room (script)", p.rb("CUR_ROOM"))
                return -1
            es, gs = self.check_turn(tag)
            if gs != GS_PLAYING:
                return gs
        return GS_PLAYING


def kill_escort(p, L):
    """Remove the lair's escort (game.md 9.4.4) so it cannot stand in a line of fire / shape the scenario."""
    es = L.ents()
    k = [s_ for s_ in range(1, 16) if es[s_]["FLAGS"] & EF_ACTIVE and es[s_]["KIND"] != KA]
    for s_ in k:
        p.set_ent(s_, FLAGS=0)            # gone (no death / no drop: FLOOR_LIST stays as generated)
    p.settle(4)
    return [(s_, es[s_]["KIND"]) for s_ in k]


def escort_blocks(p, master, hero, turns=40):
    """E: with the lair escort PRESENT (no poke of S, no kill_escort) the Archmage summons within `turns`
    (user 2026-11-01: its summon is exempt from LP_SIGMA_CAP; the audit saw 0 summons in 24 turns)."""
    L = D8(p, master, hero)
    tag = f"E escort {L.tag}"
    if not check(f"{tag}: D8 + lair entry", L.ok and L.enter(), ""):
        return
    es = L.ents()
    esc = [(s_, es[s_]["KIND"], p.rb(S["lp_wt"] + es[s_]["KIND"])) for s_ in range(1, 16)
           if es[s_]["FLAGS"] & EF_ACTIVE and es[s_]["KIND"] != KA]
    F = Fight(L, random.Random(master), kill_summons=3)
    F.run(tag, turns)
    print(f"[info] {tag}: lair escort {esc}: {F.summons_made} summons in {turns} turns at {F.summon_turns[:6]}", flush=True)
    check(f"{tag}: the escort {esc} alive, the Archmage summons within {turns} turns ({F.summons_made})",
          bool(esc) and F.summons_made >= 1, (esc, F.summons_made))
    return esc, F.summons_made


def fight_canaries(p, master, hero, turns, mirror=False):
    L = D8(p, master, hero)
    tag = f"F {L.tag}{' mirror' if mirror else ''}"
    if not check(f"{tag}: D8 + lair entry", L.ok and L.enter(), (L.ok, p.rb("CUR_ROOM"))):
        return None
    kill_escort(p, L)
    p.wmem(S["ARANK"], w16(1 | 1 << 2))
    p.wb("DAGGERS", 30)
    p.wb("ARROWS", 30)
    p.wb("HAS_BOW", 1)
    top = stack_fill(p)
    s0 = snap(p)
    rnd = random.Random(master * 7 + hero)
    F = Fight(L, rnd, mirror=mirror, turns=turns)
    gs = F.run(tag)
    p.until(lambda: p.idle(), 300)
    p.settle(3)
    s1 = snap(p)
    low = stack_low(p, top)
    bad = canary_compare(p, L, s0, s1, tag)
    a = L.arch()
    print(f"[info] {tag}: blink TURN_COUNTERs {F.blink_tc}", flush=True)
    print(f"[info] {tag}: {F.n} turns, summons {F.summons_made} at {F.summon_turns[:12]}, blinks {F.blinks}, inks "
          f"{sorted(hex(i) for i in F.inks)}, min free slots {F.min_free}, no-turn keys {F.stats['noturn']}, "
          f"stack low {low and hex(low)}, Archmage {a and L.ents()[a]['HP']}", flush=True)
    check(f"{tag}: {F.n} turns, GS_PLAYING", gs == GS_PLAYING, gs)
    check(f"{tag}: canary regions: only expected changes", not bad, bad)
    check(f"{tag}: stack depth <= 256 B (lowest byte touched)", low is None or low >= 0xBE00 + 1, low and hex(low))
    gaps = [b - a_ for a_, b in zip(F.summon_turns, F.summon_turns[1:])]
    # (a summon made inside a 2-turn action is only SEEN after it: its TURN_COUNTER is late by the extra turn,
    # so the next gap reads 1 short: tolerated by summon_extra; verified on 0x5302 mirror turn 189 -> 195)
    short = [(F.summon_turns[i], g) for i, g in enumerate(gaps) if g < S["AM_SUM_CD"] - F.summon_extra[i]
             and not any(F.summon_turns[i] < t <= F.summon_turns[i + 1] for t in F.blink_tc)]
    check(f"{tag}: summons happened ({F.summons_made}); every gap (TURN_COUNTER) >= AM_SUM_CD {S['AM_SUM_CD']} "
          f"unless a blink reset S (min {min(gaps) if gaps else None})", F.summons_made >= 1 and not short, (F.summons_made, short))
    return L, F


# ------------------------------------------------------------------ S: 50 summons
def summons50(p, master, hero):
    L = D8(p, master, hero)
    tag = f"S {L.tag}"
    if not check(f"{tag}: D8 + lair entry", L.ok and L.enter(), (L.ok, p.rb("CUR_ROOM"))):
        return
    kill_escort(p, L)
    es = L.ents()
    free0 = sum(1 for s_ in range(1, 16) if es[s_]["FLAGS"] == 0)
    F = Fight(L, random.Random(master), kill_summons=1, poke_s=True)
    F.action = lambda es: ("WAIT",)
    frees = []
    for _ in range(400):
        if F.summons_made >= 50:
            break
        if F.run(tag, 1) != GS_PLAYING:
            break
        es = L.ents()
        frees.append(sum(1 for s_ in range(1, 16) if es[s_]["FLAGS"] == 0))
    for _ in range(4):
        F.kill_summons = 0
        F.poke_s = False
        F.run(tag, 1)
    p.settle(30)
    es = L.ents()
    free1 = sum(1 for s_ in range(1, 16) if es[s_]["FLAGS"] == 0)
    print(f"[info] {tag}: {F.summons_made} summons in {F.n} turns, free slots at entry {free0}, min {min(frees or [0])},"
          f" after {free1}", flush=True)
    check(f"{tag}: 50 summons made", F.summons_made >= 50, F.summons_made)
    check(f"{tag}: free-slot count stable (entry {free0} == after {free1}; min during {min(frees or [0])} >= entry - 2)",
          free1 == free0 and min(frees or [0]) >= free0 - 2, (free0, free1, frees[-10:]))


# ------------------------------------------------------------------ K: kills
def after_kill(p, L, F, tag, more=20):
    p.until(lambda: p.idle(), 300)
    p.settle(4)
    es = L.ents()
    a = [s_ for s_ in range(1, 16) if es[s_]["KIND"] == KA and es[s_]["FLAGS"] & EF_ACTIVE and not es[s_]["FLAGS"] & EF_DYING]
    fl = p.rb("LVL_FLAGS")
    check(f"{tag}: the Archmage dead, LF_SEAL_OPEN + LF_UNIQUE, the seal off the edge, GS_PLAYING",
          not a and fl & S["LF_SEAL_OPEN"] and fl & S["LF_UNIQUE"] and not p.rb(L.sedge) & S["EG_SEAL"]
          and p.rb("GAME_STATE") == GS_PLAYING, (a, fl, p.rb(L.sedge), p.rb("GAME_STATE")))
    F.keep_arch = False
    gs = F.run(tag + " after", more)
    es = L.ents()
    stuck = [s_ for s_ in range(1, 16) if es[s_]["KIND"] == KA and es[s_]["FLAGS"]]
    check(f"{tag}: {more} turns after the kill clean, the Archmage slot freed", gs == GS_PLAYING and not stuck,
          (gs, stuck, [es[s_] for s_ in stuck]))


def kill_mirror(p, master, hero):
    L = D8(p, master, hero)
    tag = f"K1 mirror-return {L.tag}"
    if not check(f"{tag}: D8 + lair entry", L.ok and L.enter(), ""):
        return
    kill_escort(p, L)                     # (else it may stand in the line of fire)
    F = Fight(L, random.Random(master + 1), mirror=True, keep_arch=False, kill_summons=None)
    # its summons would stand between (sp_place: the hero's side first) and block the line: S held at 15
    a = L.arch()
    p.set_ent(a, HP=6)
    killed = False
    # stand in line on the Archmage's storey, waiting: its Death Bolts come back
    for i in range(60):
        es = L.ents()
        a = L.arch(es)
        if a is None:
            killed = True
            break
        st = 0 if es[a]["Y"] < 9 else 1
        hx = es[a]["X"] + L.aw + 8 if es[a]["X"] + L.aw + 8 + L.kw <= 29 else es[a]["X"] - 8 - L.kw
        if es[0]["X"] != hx or (es[0]["Y"] < 9) != (st == 0):
            L.place(hx, st, left=hx > es[a]["X"])
            p.tick(2)
        F.n += 1
        F.hero_prep()
        p.wb(S["P_ENTITIES"] + a * STRIDE + E_RCD, es[a]["RCD"] | RCD_SUMMON)
        p.turn("WAIT", max_ticks=600)
        F.check_turn(tag)
    check(f"{tag}: the Archmage killed by its own Death Bolt return within 60 turns", killed, L.ents()[a] if a else "")
    if killed:
        after_kill(p, L, F, tag)
    return L, F


def kill_ranged_door(p, master, hero):
    L = D8(p, master, hero)
    tag = f"K2 ranged at the door {L.tag}"
    if not check(f"{tag}: D8 + lair entry", L.ok and L.enter(), ""):
        return
    kill_escort(p, L)                     # (else it may stand in the line of fire)
    F = Fight(L, random.Random(master + 2), keep_arch=False, kill_summons=None)
    p.wmem(S["ARANK"], w16(1 | 1 << 2))       # Warrior PS / WW, Mage Spark / Firebolt (Spark is SHOCK: X on it)
    p.wb("ARROWS", 30)
    p.wb("HAS_BOW", 1)
    a = L.arch()
    # the hero at the door cell he came in by, the Archmage moved onto his storey 4 cols away
    hx = 1 if L.side == "L" else 31 - L.kw
    ax = hx + L.kw + 4 if L.side == "L" else hx - 4 - L.aw
    ay = stand_y(L.s, L.ah)
    p.set_ent(a, X=ax, Y=ay, PX=ax * 8, PY=ay * 8, HP=1)
    p.wb(S["ST_X"] + a, 0)
    for s_ in range(1, 16):
        if s_ != a:
            p.set_ent(s_, FLAGS=0)                # nothing between the door and it
    shots = 0
    for _ in range(8):                        # an arrow can miss (hit roll vs EVA); a spell never does
        es = L.ents()
        if L.arch(es) is None:
            break
        for s_ in range(1, 16):
            if s_ != a and es[s_]["FLAGS"]:
                p.set_ent(s_, FLAGS=0)
        p.wb(S["P_ENTITIES"] + a * STRIDE + E_RCD, es[a]["RCD"] | RCD_SUMMON)
        L.place(hx, L.s, left=(L.side == "R"))
        p.tick(3)
        F.hero_prep()
        p.turn("@4" if hero == 0 else "@2", max_ticks=600)
        p.until(lambda: p.idle(), 300)
        shots += 1
    print(f"[info] {tag}: {shots} shot(s)", flush=True)
    es = L.ents()
    check(f"{tag}: the {'arrow' if hero == 0 else 'Firebolt'} from the door kills it (gap 4)",
          L.arch(es) is None, (es[a], p.rb("CUR_ROOM")))
    if L.arch(es) is None:
        after_kill(p, L, F, tag)


def kill_with_summon(p, master, hero):
    L = D8(p, master, hero)
    tag = f"K3 killed while a summon lives {L.tag}"
    if not check(f"{tag}: D8 + lair entry", L.ok and L.enter(), ""):
        return
    kill_escort(p, L)
    F = Fight(L, random.Random(master + 3), kill_summons=None, poke_s=True)
    F.action = lambda es: ("WAIT",)
    for _ in range(30):
        F.run(tag, 1)
        if F.summons_made:
            break
    F.poke_s = False
    es = L.ents()
    sm = [s_ for s_ in range(1, 16) if es[s_]["FLAGS"] & EF_ACTIVE and es[s_]["RCD"] & RCD_SUMMONED]
    if not check(f"{tag}: a summon lives", sm, F.summons_made):
        return
    a = L.arch(es)
    L.deal(0, a, 99)
    after_kill(p, L, F, tag, more=6)
    es = L.ents()
    sm2 = [s_ for s_ in range(1, 16) if es[s_]["FLAGS"] & EF_ACTIVE and not es[s_]["FLAGS"] & EF_DYING
           and es[s_]["RCD"] & RCD_SUMMONED]
    print(f"[info] {tag}: summons alive after the Archmage's death: {sm2}", flush=True)
    # leave + re-enter: the summon discarded, no Archmage, the record
    for s_ in range(1, 16):
        if es[s_]["FLAGS"] & EF_ACTIVE and not es[s_]["RCD"] & RCD_SUMMONED:
            p.set_ent(s_, FLAGS=0)            # nothing but the summon in the lair (the door path free)
    left = L.leave()
    ro = S["LP_REC"] + 9 * L.lair
    rec = list(p.z.read_memory(ro, 9))
    es = L.ents()
    anywhere = [s_ for s_ in range(1, 16) if es[s_]["FLAGS"] & EF_ACTIVE and es[s_]["RCD"] & RCD_SUMMONED]
    followed = [s_ for s_ in anywhere if es[s_]["ROOM"] == L.nb]
    if followed:
        note(f"{tag}: the summon FOLLOWED the hero out of the lair (follow_select admits summons, place_follower "
             f"keeps RCD_SUMMONED): game.md 9.4.4 'discarded on leave' holds only for non-followers", followed)
    check(f"{tag}: left the lair: the summon discarded or a follower (no other slot, not in the lair record {rec})",
          left and not [s_ for s_ in anywhere if s_ not in followed]
          and all((rec[1 + 2 * i] & 0x3F) != KSK for i in range(rec[0] & 7)), (left, anywhere, rec))
    ok = L.enter()
    es = L.ents()
    back = [(s_, es[s_]["KIND"]) for s_ in range(1, 16) if es[s_]["FLAGS"] & EF_ACTIVE]
    check(f"{tag}: re-entered: no Archmage, no summon (slots {back})",
          ok and not any(k in (KA,) for _, k in back) and not any(es[s_]["RCD"] & RCD_SUMMONED for s_, _ in back),
          (ok, back))


# ------------------------------------------------------------------ R: the trickle after the Archmage's death
def trickle_after(p, master, hero, n=120):
    """game.md 9.5 (U): the trickle stops permanently the turn the boss dies. trk_run (R6) tests
    LF_GRATE_OPEN | LF_UNIQUE (P3: the D8 death sets LF_SEAL_OPEN + LF_UNIQUE, the grate stays shut). n trk_run calls (far6, GEN_RNG varied, TRK_PREV = the lair) after the kill: LP_RESPAWNS must
    stay; control: the same with LF_GRATE_OPEN set."""
    L = D8(p, master, hero)
    tag = f"R trickle after the death {L.tag}"
    if not check(f"{tag}: D8 + lair entry", L.ok and L.enter(), ""):
        return
    kill_escort(p, L)
    a = L.arch()
    L.deal(0, a, 99)
    p.until(lambda: p.idle(), 300)
    p.settle(4)
    fl = p.rb("LVL_FLAGS")
    res = {}
    for ctl in (False, True):
        p.wb("LVL_FLAGS", fl | (S["LF_GRATE_OPEN"] if ctl else 0))
        p.wb("LP_RESPAWNS", 0)
        rec = lambda: bytes(p.z.read_memory(S["LP_REC"], 9 * S["LR_STRIDE"]))  # noqa: E731
        lp0 = rec()
        ts = []
        for i in range(n):
            p.wb("TRK_PREV", L.lair)
            p.wmem(S["GEN_RNG"], w16(0x1357 + 97 * i))
            pc0 = p.pc()
            ok, t = p.code([0x21] + w16(S["trk_run"]) + [0xCD] + w16(S["far6"]), game=True)
            p.z.cmd("set-register PC=%d" % pc0)
            ts.append(t)
        res[ctl] = (p.rb("LP_RESPAWNS"), max(ts), rec() != lp0)
        p.wb("LVL_FLAGS", fl)
    print(f"[info] {tag}: LVL_FLAGS {fl:#04x}; after the death: LP_RESPAWNS {res[False][0]}, worst trk_run "
          f"{res[False][1]} T, records changed {res[False][2]}; control (LF_GRATE_OPEN): {res[True]}", flush=True)
    check(f"{tag}: after the death trk_run does nothing (LF_UNIQUE; flags {fl:#04x})",
          res[False][0] == 0 and not res[False][2] and res[False][1] < 1000, res[False])
    check(f"{tag}: control: with LF_GRATE_OPEN trk_run stops at step 2", res[True][0] == 0 and not res[True][2], res[True])


# ------------------------------------------------------------------ T: teleport mid-fight
def teleport_mid(p, master, hero):
    L = D8(p, master, hero)
    tag = f"T teleport mid-fight {L.tag}"
    if not check(f"{tag}: D8 + lair entry", L.ok and L.enter(), ""):
        return
    kill_escort(p, L)
    F = Fight(L, random.Random(master + 4), kill_summons=None, poke_s=True)
    F.action = lambda es: ("WAIT",)
    for _ in range(30):
        F.run(tag, 1)
        if F.summons_made:
            break
    F.poke_s = False
    es = L.ents()
    a = L.arch(es)
    hp_a = es[a]["HP"] if a else None
    sm = [s_ for s_ in range(1, 16) if es[s_]["FLAGS"] & EF_ACTIVE and es[s_]["RCD"] & RCD_SUMMONED]
    check(f"{tag}: a summon lives before the teleport", sm, F.summons_made)
    # line up for a bolt and arm the teleport for the next turn (FX of the previous turn may still fly)
    p.wb("EXIT_KIND", S["EX_TELE"])
    p.set_ent(0, HP=200)
    p.turn("WAIT", max_ticks=600)
    p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
    p.settle(3)
    es = L.ents()
    anywhere = [s_ for s_ in range(1, 16) if es[s_]["FLAGS"] & EF_ACTIVE and es[s_]["RCD"] & RCD_SUMMONED]
    ro = S["LP_REC"] + 9 * L.lair
    rec = list(p.z.read_memory(ro, 9))
    ents_rec = [(rec[1 + 2 * i], rec[2 + 2 * i]) for i in range(rec[0] & 7)]
    fx = (p.rb("FX_BUSY") & 7, p.rb("FXQ_N"), p.rb("SPQ_K"))
    check(f"{tag}: teleported out (room {p.rb('CUR_ROOM')}), the summon discarded, lair record "
          f"{ents_rec} = the Archmage hp {hp_a} only, FX idle {fx}",
          p.rb("CUR_ROOM") != L.lair and not anywhere and [(k & 0x3F, v) for k, v in ents_rec] == [(KA, hp_a)]
          and fx == (0, 0, 0), (p.rb("CUR_ROOM"), anywhere, ents_rec, fx))
    F.check_turn(tag)
    # walk back in: the Archmage re-entered (P 0, init clear, ink $43)
    p.wb(INK, 0x45)
    ok = L.enter()
    es = L.ents()
    a = L.arch(es)
    stx = p.rb(S["ST_X"] + a) if a else None
    check(f"{tag}: re-entry: the Archmage back with hp {hp_a}, KT_ATTR $43, ST_X 0 (init: P = H = 0)",
          ok and a and es[a]["HP"] == hp_a and p.rb(INK) == 0x43 and stx == 0, (ok, a and es[a], hex(p.rb(INK)), stx))
    F.arch_pos = None
    F.blinks = 0
    gs = F.run(tag + " re-entered", 25)
    check(f"{tag}: 25 turns after the re-entry clean", gs == GS_PLAYING, gs)


# ------------------------------------------------------------------ W: the Sanctum with a summon at the door
def sanctum_walk(p, master, hero):
    L = D8(p, master, hero)
    tag = f"W Sanctum {L.tag}"
    if not check(f"{tag}: D8 + lair entry", L.ok and L.enter(), ""):
        return
    kill_escort(p, L)
    F = Fight(L, random.Random(master + 5), kill_summons=None, poke_s=True)
    F.action = lambda es: ("WAIT",)
    for _ in range(30):
        F.run(tag, 1)
        if F.summons_made:
            break
    es = L.ents()
    sm = [s_ for s_ in range(1, 16) if es[s_]["FLAGS"] & EF_ACTIVE and es[s_]["RCD"] & RCD_SUMMONED]
    a = L.arch(es)
    L.deal(0, a, 99)
    p.until(lambda: p.idle(), 300)
    p.settle(20)
    # the hero at the Sanctum door, the summon right behind him on the same storey
    sside = "R" if L.side == "L" else "L"
    hx = 30 - L.kw if sside == "R" else 2
    for s_ in range(1, 16):
        if s_ not in sm:
            p.set_ent(s_, FLAGS=0)
    L.place(hx, L.ss, left=(sside == "L"))
    if sm:
        s_ = sm[0]
        sx = hx - 1 - p.kb(KSK, "KT_BW") if sside == "R" else hx + L.kw + 1
        sy = stand_y(L.ss, p.kb(KSK, "KT_BH"))
        p.set_ent(s_, X=sx, Y=sy, PX=sx * 8, PY=sy * 8, MODE=0, HP=99)
        p.wb(S["ST_FLAGS"] + s_, 0)
    p.tick(3)
    key = "L" if sside == "R" else "H"
    for _ in range(10):
        if p.rb("CUR_ROOM") == L.sn:
            break
        p.set_ent(0, HP=200)
        p.turn(key)
    p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
    p.settle(3)
    es = L.ents()
    inside = [(s_, es[s_]["KIND"], es[s_]["X"], es[s_]["Y"], es[s_]["RCD"]) for s_ in range(1, 16)
              if es[s_]["FLAGS"] & EF_ACTIVE and es[s_]["ROOM"] == L.sn]
    check(f"{tag}: the hero in the Sanctum (room {p.rb('CUR_ROOM')} == {L.sn})", p.rb("CUR_ROOM") == L.sn, p.rb("CUR_ROOM"))
    print(f"[info] {tag}: bodies in the Sanctum after the entry: {inside} (summon followed: "
          f"{any(r & RCD_SUMMONED for *_, r in inside)})", flush=True)
    if any(r & RCD_SUMMONED for *_, r in inside):
        note(f"{tag}: a live summon follows the hero into the Sanctum (after the seal broke)", inside)
    m = list(p.z.read_memory(S["ROOM_MAP"], 576))
    c0 = 1 if L.sn == 6 else 29
    lect = [m[15 * 32 + c0], m[15 * 32 + c0 + 1], m[16 * 32 + c0], m[16 * 32 + c0 + 1]]
    # 30 turns in the Sanctum (the summon, if it followed, walks / fights), then 5 melee hits
    G = Fight(L, random.Random(master + 6), kill_summons=None)
    G.action = lambda es: ("WAIT",) if G.rnd.random() < 0.5 else (G.rnd.choice(("L", "H")),)
    gs = G.run(tag + " inside", 30)
    es = L.ents()
    on_lect = [(s_, es[s_]) for s_ in range(1, 16) if es[s_]["FLAGS"] & EF_ACTIVE and es[s_]["ROOM"] == L.sn
               and es[s_]["X"] <= c0 + 1 and es[s_]["X"] + p.kb(es[s_]["KIND"], "KT_BW") > c0 and es[s_]["Y"] >= 9]
    m2 = list(p.z.read_memory(S["ROOM_MAP"], 576))
    want = room_model.render_room(room_model.read_block(p), L.sn)
    al = p.z.read_memory(S["ANIM_LIST"], S["ANIM_MAX"] * S["AL_STRIDE"])
    swap = {al[i * 4 + 1] * 32 + al[i * 4]: al[i * 4 + 2] for i in range(p.rb("ANIM_N")) if al[i * 4 + 2] >= 16}
    md = [(j % 32, j // 32, m2[j], want[j]) for j in range(576) if m2[j] != want[j] and swap.get(j) != want[j]]
    check(f"{tag}: 30 turns in the Sanctum: GS_PLAYING (aura), the lectern intact {lect}, ROOM_MAP == room_model, "
          f"no body on the lectern cells", gs in (GS_PLAYING, GS_DEAD) and lect == [15, 16, 17, 18] and not md
          and not on_lect, (gs, lect, md[:6], on_lect))
    # the Tome: 5 melee hits (the summon removed so nothing stands in the way)
    for s_ in range(1, 16):
        p.set_ent(s_, FLAGS=0)
    p.wb("GAME_STATE", GS_PLAYING)
    p.wb("TOME_HP", S["TOME_MAX"])
    xg = 3 if L.sn == 6 else 29 - L.kw         # gap 0 to the lectern (cols 1-2 / 29-30)
    hits = []
    for i in range(5):
        L.place(xg, 1, left=(L.sn == 6))
        p.tick(2)
        p.set_ent(0, HP=200)
        h0 = p.rb("TOME_HP")
        p.turn("C", max_ticks=600)
        p.until(lambda: p.idle(), 300)
        hits.append(h0 - p.rb("TOME_HP"))
        if p.rb("GAME_STATE") != GS_PLAYING:
            break
    # WIN2 (user 2026-11-01): the 5th hit destroys the Tome and opens the gate (LF_GRATE_OPEN); the run goes on
    check(f"{tag}: 5 melee hits ({hits}): the Tome destroyed, the gate open, still GS_PLAYING (the win is the descent)",
          p.rb("GAME_STATE") == GS_PLAYING and p.rb("TOME_HP") == 0 and p.rb("LVL_FLAGS") & S["LF_GRATE_OPEN"],
          (hits, p.rb("GAME_STATE"), p.rb("TOME_HP"), p.rb("LVL_FLAGS")))
    # walk out into the lair (the Sanctum door is on the side facing the lair), then DOWN at the exit col
    left_door = L.sn != 6
    x = 2 if left_door else 30 - L.kw
    L.place(x, 1, left=left_door)
    p.tick(2)
    for _ in range(6):
        if p.rb("CUR_ROOM") != L.sn:
            break
        p.set_ent(0, HP=200)
        p.turn("H" if left_door else "L")
    p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
    p.settle(2)
    c = room_model.field(room_model.read_block(p), L.lair, "RD_EXITCOL")
    check(f"{tag}: walked out into the lair (room {p.rb('CUR_ROOM')} == {L.lair})", p.rb("CUR_ROOM") == L.lair, p.rb("CUR_ROOM"))
    L.place(c, 1, left=False)
    p.set_ent(0, HP=1)
    p.turn("J")
    p.until(lambda: p.idle(), 900)
    p.until(lambda: p.rb("LOG_QN") == 0, 200)
    p.settle(2)
    check(f"{tag}: DOWN at the exit col {c} through the open gate -> GS_WIN, depth stays 8",
          p.rb("GAME_STATE") == GS_WIN and p.rb("LVL_DEPTH") == 8, (p.rb("GAME_STATE"), p.rb("LVL_DEPTH")))
    # a new game after the win: D1, then D8 again: the lair entry resets the Archmage ink
    ink_end = p.rb(INK)
    p.tick(3)
    ok = p.end_to_menu()
    p.menu_start(hero)
    d1 = (p.rb("LVL_DEPTH"), hex(p.rb(INK)))
    L2 = D8(p, master, hero, boot=False)
    ok2 = L2.ok and L2.enter()
    a = L2.arch()
    check(f"{tag}: new game after the win (menu {ok}): D1 KT_ATTR Archmage {d1[1]} (stale from D8 {ink_end:#x}), "
          f"D8 lair entry -> $43", ok2 and a is not None and p.rb(INK) == 0x43, (ok2, a, hex(p.rb(INK)), d1))


# ------------------------------------------------------------------ G: drawing at every x
def draw_sweep(p, master, hero):
    L = D8(p, master, hero)
    tag = f"G draw {L.tag}"
    if not check(f"{tag}: D8 + lair entry", L.ok and L.enter(), ""):
        return
    pool0 = GI.pool_snap(p)
    a = L.arch()
    for s_ in range(1, 16):
        if s_ != a:
            p.set_ent(s_, FLAGS=0)
    bad = []
    m = list(p.z.read_memory(S["ROOM_MAP"], 576))
    n = 0
    hpos = None
    for st in (0, 1):
        for x in range(2, 30 - L.aw + 1):
            es = L.ents()
            y = stand_y(st, L.ah)
            # the hero parked far away on the other storey
            hs = 1 - st
            hx = 2 if x > 15 else 29 - L.kw
            if hpos != (hx, hs):
                L.place(hx, hs)
                hpos = (hx, hs)
            p.set_ent(a, X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0)
            p.tick(3)
            sub = []
            GI.screen_check(p, lambda t, c, d="": sub.append((t, d)) if not c else None, f"{tag} x {x} s {st}", 8)
            n += 1
            if sub:
                bad.append((x, st, sub[0][1]))
    check(f"{tag}: the Archmage at {n} (x, storey) spots: playfield outside the sprites == ROOM_MAP glyphs",
          not bad, bad[:6])
    # its states: hurt (a hit), cast (a turn in line), dead
    F = Fight(L, random.Random(master + 7), kill_summons=1)
    F.action = lambda es: ("WAIT",)
    st = 1
    p.set_ent(a, X=14, Y=stand_y(st, L.ah), PX=14 * 8, PY=stand_y(st, L.ah) * 8, MODE=0)
    L.place(14 + L.aw + 6, st, left=True)
    p.tick(2)
    F.run(tag, 6)
    L.deal(0, a, 3)
    for _ in range(6):
        p.tick(1)
    L.deal(0, a, 99)
    for _ in range(40):
        p.tick(1)
    sub = []
    GI.screen_check(p, lambda t, c, d="": sub.append((t, d)) if not c else None, f"{tag} after hurt / dead", 8)
    mk = GL.mark_cells(p)
    left = [(t, [c for c in d if (c[0], c[1]) not in mk]) for t, d in sub if isinstance(d, list)]
    left = [x for x in left if x[1]] + [x for x in sub if not isinstance(x[1], list)]
    print(f"[info] {tag}: after hurt / dead: hero ST_FLAGS {p.rb(S['ST_FLAGS']):#04x}, mark cells {sorted(mk)}, "
          f"screen mismatches {sub[:1]}", flush=True)
    check(f"{tag}: after cast / hurt / dead: playfield == ROOM_MAP glyphs (status-mark cells aside)", not left, left[:2])
    GI.pool_check(p, lambda t, c, d="": check(t, c, d), f"{tag} pool after the sweep", None, pool0)


# ------------------------------------------------------------------ C: a summon's corpse slot reused (fix/d8-corpse-topleft)
def corpse_reuse(p, master, hero, block):
    """The summon dies on the turn's last tick while the Archmage queues the next one: end_turn's sp_run reuses
    the just-freed corpse slot (sp_init zeroes E_PX / E_PY) BEFORE the next render, which still holds the
    corpse's R_VIS 1 / R_FID. block = 1: two Skeletons beside the Archmage at the room's left edge, so
    sp_place fails (the slot keeps px = py = 0): before the fix the corpse was blitted at the top-left for a
    tick (user playtest: the nun's / the Pharaoh's summoned Skeleton). Hard check: the displayed playfield
    cols 0-4 rows 0-8 == ROOM_MAP glyphs on the 4 ticks after the turn, and no drawn record there."""
    L = D8(p, master, hero)
    tag = f"C corpse-slot {'blocked' if block else 'placed'} {L.tag}"
    if not check(f"{tag}: D8 + lair entry", L.ok and L.enter(), ""):
        return
    kill_escort(p, L)
    F = Fight(L, random.Random(master), kill_summons=None, poke_s=True)
    F.action = lambda es: ("WAIT",)
    for _ in range(30):
        F.run(tag, 1)
        if F.summons_made:
            break
    es = L.ents()
    a = L.arch(es)
    sm = [s_ for s_ in range(1, 16) if es[s_]["FLAGS"] & EF_ACTIVE and es[s_]["RCD"] & RCD_SUMMONED]
    if not check(f"{tag}: a summon lives", a is not None and sm, (a, sm)):
        return
    k = sm[0]
    st = 0 if es[a]["Y"] < 9 else 1
    sy = stand_y(st, p.kb(KSK, "KT_BH"))
    ax = 2                                    # block = 0: an x with a legal cell beside it (sp_place succeeds)
    if not block:
        m = list(p.z.read_memory(S["ROOM_MAP"], 576))
        ax = next((x for x in range(4, 18) if not L.legal(m, KSK, x + L.aw, sy, {})), 2)
    p.set_ent(a, X=ax, PX=ax * 8, MODE=0)
    p.set_ent(k, X=24, Y=sy, PX=192, PY=sy * 8, MODE=0, HP=1)
    L.place(14, 1 - st)
    free = [s_ for s_ in range(1, 16) if es[s_]["FLAGS"] == 0]
    for j, x in zip(free[:2] if block else [], (2 + L.aw, 2 + L.aw + 3)):
        p.set_ent(j, KIND=KSK, ROOM=p.rb("CUR_ROOM"), FLAGS=EF_ACTIVE | EF_HOSTILE, X=x, Y=sy, PX=x * 8, PY=sy * 8,
                  HP=50, MAXHP=50, MODE=0, DVIS=0)
        p.wb(S["P_ENTITIES"] + j * STRIDE + E_RCD, 0)
        p.wb(S["ST_FLAGS"] + j, 0)
    p.tick(4)
    p.wb(S["P_ENTITIES"] + a * STRIDE + E_RCD, p.rb(S["P_ENTITIES"] + a * STRIDE + E_RCD) & ~RCD_SUMMON & 255)
    L.deal(0, k, 99)
    p.turn("WAIT")
    bad = []
    for i in range(4):
        sub = []
        GI.screen_check(p, lambda t, c, d="": sub.append((t, d)) if not c else None, tag, 8)
        bad += [(i, c) for t, d in sub if isinstance(d, list) for c in d if c[0] < 5 and c[1] < 9]
        e = p.ent(k)
        if e["DVIS"] & 1 and e["DCOL"] < 5 and e["DROW"] < 9:
            bad.append((i, "drawn", e))
        if e["DVIS"] & 1 and e["FLAGS"] & EF_ACTIVE and not e["FLAGS"] & EF_DYING and e["DFID"] == S["FID_small_corpse"]:
            bad.append((i, "new body drawn as a corpse", e))
        p.tick(1)
    e = p.ent(k)
    print(f"[info] {tag}: slot {k} after the turn: flags {e['FLAGS']:#04x} x {e['X']} px {e['PX']} py {e['PY']}", flush=True)
    check(f"{tag}: summon {'not ' if block else ''}made in slot {k}", bool(e["FLAGS"] & EF_ACTIVE) != bool(block), e)
    check(f"{tag}: no corpse frame at the top-left / on the new body after the slot's reuse (sp_init hides R_VIS)",
          not bad, bad[:4])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=300)
    ap.add_argument("--seeds", default="0x5300,0x5302,0x5304")
    ap.add_argument("--only", default="EFSKRTWGC")
    args = ap.parse_args()
    seeds = [int(s, 0) for s in args.seeds.split(",")]
    if not F3:
        print("[skip] d8_stress needs the F3_GEN build", flush=True)
        return 0
    total_turns = 0
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = Proto(h)
        if "F" in args.only:
            for hero in (0, 1):
                for i, m in enumerate(seeds):
                    r = fight_canaries(p, m + 16 * hero, hero, args.turns, mirror=(i == 1))
                    if r:
                        total_turns += r[1].n
        if "E" in args.only:
            for hero in (0, 1):
                for m in seeds:
                    escort_blocks(p, m + 16 * hero, hero)
        if "S" in args.only:
            summons50(p, seeds[0], 0)
            summons50(p, seeds[0] + 16, 1)
        if "K" in args.only:
            for hero in (0, 1):
                kill_mirror(p, seeds[0] + 16 * hero, hero)
                kill_ranged_door(p, seeds[1 % len(seeds)] + 16 * hero, hero)
                kill_with_summon(p, seeds[-1] + 16 * hero, hero)
        if "R" in args.only:
            trickle_after(p, seeds[0], 0)
        if "T" in args.only:
            for hero in (0, 1):
                teleport_mid(p, seeds[0] + 16 * hero, hero)
        if "W" in args.only:
            for hero in (0, 1):
                sanctum_walk(p, seeds[1 % len(seeds)] + 16 * hero, hero)
        if "G" in args.only:
            for hero in (0, 1):
                draw_sweep(p, seeds[0] + 16 * hero, hero)
        if "C" in args.only:
            for hero in (0, 1):
                for block in (1, 0):
                    corpse_reuse(p, seeds[0] + 16 * hero, hero, block)
    for (b, k), v in sorted(SEEN_CODE.items()):
        print(f"[info] code-bank writes bank {b} {k}: {len(v)} ranges, e.g. "
              f"{sorted(v)[:3] if k != 'var' else sorted({x[2][:60] for x in v})[:12]}", flush=True)
    print(f"[info] fight turns {total_turns}; anomalies {len(anoms)}", flush=True)
    for t, d in anoms[:40]:
        print(f"[ANOM] {t}: {str(d)[:400]}")
    for t, d in notes:
        print(f"[NOTE] {t}: {str(d)[:300]}")
    print(f"d8_stress: {len(fails)} failed, {len(anoms)} anomalies, {len(notes)} notes" + (f": {fails[:10]}" if fails else ""), flush=True)
    return 1 if fails or anoms else 0


if __name__ == "__main__":
    sys.exit(main())
