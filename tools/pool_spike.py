#!/usr/bin/env python3
"""3F pool spike (Python only; no src/ changes): exact per-level pre-shift pool
need D1..D8 for the LEAN 3F monster set, and the ZX0-packed source total.

Method
  * Per-frame pool bytes = the src/defs.asm FRM / POOLACC formula (PHASE_SHIFT 1),
    replayed on the real frame metadata (assets/gfx/sprites/<name>.asm) with the
    flags/body width from src/frames.asm.  Self-check against build/tome-of-the-dead.sym
    (POOL_MONSTERS / POOL_KNIGHT / POOL_WIZARD / POOL_FXM / POOL_FXW).
  * Missing 3F kinds are STAND-INS: each lean frame borrows the pixel bytes and
    the w/h/cols/ax of an existing frame of the same size (STAND_IN below), so
    pool and ZX0 sizes are real for that geometry; art content is a guess.
  * Packed sources: tools/zx0_sources.partition()/pack() (same per-kind DP over
    blocks of <= 4 frames / 1,536 B raw), one stream set per new kind.
  * Level need = monsters + shared frames + projectiles + hero (+ its class FX)
    + the POOL_NEED fixed part (2 select idles 2*576 + straddle 3*576, data.asm).

Usage: tools/pool_spike.py [--md docs/design/pool_spike.md]
"""
import argparse
import os
import re
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import zx0_pack as zp          # noqa: E402
import zx0_sources as zs       # noqa: E402

SPR = os.path.join(REPO, "assets/gfx/sprites")
SYM = os.path.join(REPO, "build/tome-of-the-dead.sym")
FIXED = 2 * 576 + 3 * 576      # data.asm POOL_NEED: select idles + straddle allowance
POOL_CAP_FALLBACK = 39804      # build/tome-of-the-dead.sym 2026-10-26 (task text says 39,792)
ZX0_PACKED_TOTAL_FALLBACK = 8908


def meta(name):
    out = {}
    for line in open(zp.sprite_asm(name)):
        m = re.match(rf"^{name}_(w|h|cols|ax)\s+EQU\s+(-?\d+)", line)
        if m:
            out[m.group(1)] = int(m.group(2))
    return out


def sym(name, default):
    try:
        for line in open(SYM):
            m = re.match(rf"^{name}: EQU 0x([0-9A-Fa-f]+)", line)
            if m:
                return int(m.group(1), 16)
    except OSError:
        pass
    return default


class Fr:
    """name = label shown; src = the sprite file supplying geometry + bytes."""
    def __init__(self, name, src, bw, flags):
        self.name, self.src, self.bw = name, src, bw
        f = set(flags.split("|"))
        self.mot, self.sym, self.ph4 = "MOT" in f, "SYM" in f, "WK4" in f
        m = meta(src)
        self.w, self.h, self.cols, self.ax = m["w"], m["h"], m["cols"], m["ax"]
        assert self.cols * 8 == self.w

    def pool(self):
        c, h = self.cols, self.h
        if self.mot:
            return h * 2 * (2 * c + 1) * (1 if self.sym else 2)
        ph = 4 if self.ph4 else 0
        n = h * 2 * (c + (((self.ax + ph) & 7) != 0))
        if not self.sym:
            n += h * 2 * (c + (((self.w - self.ax - self.bw + ph) & 7) != 0))
        return n

    def legal(self):
        d = self.w - self.ax - self.bw
        return self.ax % 4 == 0 and self.ax <= 8 and 0 <= d <= 16


# ---- real frame list (src/frames.asm) --------------------------------------
def real_frames():
    kinds, order = {}, []
    for line in open(os.path.join(REPO, "src/frames.asm")):
        m = re.match(r"\s+FRM\s+(\w+)\s*,\s*(\w+)\s*,\s*(\d+)\s*,\s*([\w|]+)", line.split(";")[0])
        if m:
            nm, kind, bw, fl = m.groups()
            if kind not in kinds:
                order.append(kind)
            kinds.setdefault(kind, []).append(Fr(nm, nm, int(bw), fl))
    return kinds


REAL = real_frames()


def F(kind, names=None):
    return [f for f in REAL[kind] if names is None or f.name in names]


# ---- LEAN stand-ins (name, geometry/bytes source, body px, flags) ----------
# Rule: walk1 = MOT (it is also the rest frame, like Rat/Skeleton/Goblin walk1),
# walk2 = WK0 (aligned shift only); attack/special = STA; HURT = colour flash
# (no frame); DEAD = the shared per-body-class frame (DEAD_H / rat_dead).
STAND_IN = {
    # Spider 32x16 body: rat geometry, 3 frames (WALK1/2 + BITE)
    "SPIDER": [("spider_walk1", "rat_run1", 32, "MOT"), ("spider_walk2", "rat_run2", 32, "WK0"),
               ("spider_bite", "rat_bite", 32, "STA")],
    # Orc 24x48 (NOT in the lean ruling: assumed drawn as WALK1/2 + ATTACK like Mummy)
    "ORC": [("orc_walk1", "goblin_walk1", 24, "MOT"), ("orc_walk2", "goblin_walk2", 24, "WK0"),
            ("orc_attack", "skeleton_cut", 24, "STA")],
    # Necromancer 24x48 (also Vampire and Archmage): WALK1/2 + CAST
    "NECRO": [("necro_walk1", "wizard_walk1", 24, "MOT"), ("necro_walk2", "wizard_walk2", 24, "WK0"),
              ("necro_cast", "wizard_cast1", 24, "STA")],
    # Mummy 24x48 drawn NEW: WALK1/2 + ATTACK
    "MUMMY": [("mummy_walk1", "knight_walk1", 24, "MOT"), ("mummy_walk2", "knight_walk2", 24, "WK0"),
              ("mummy_attack", "knight_follow", 24, "STA")],
    # Ogre 32x48: WALK1/2 + SLAM 40x48
    "OGRE": [("ogre_walk1", "knight_throw", 32, "MOT"), ("ogre_walk2", "knight_bow", 32, "WK0"),
             ("ogre_slam", "knight_whirl", 32, "STA")],
    # Death Knight 24x48: WALK1/2 + CLEAVE 40x48 + BLOCK 32x48
    "DK": [("dk_walk1", "knight_walk3", 24, "MOT"), ("dk_walk2", "knight_walk4", 24, "WK0"),
           ("dk_cleave", "knight_powerstrike", 24, "STA"), ("dk_block", "knight_block", 24, "STA")],
    # Archer: Skeleton walk (shared) + ONE shoot frame
    "ARCHER_SHOOT": [("archer_shoot", "wizard_cast2", 24, "STA")],
    # one shared DEAD per humanoid body class (40x16 lying body, knight_dead geometry)
    "DEAD_H": [("dead_humanoid", "knight_dead", 24, "STA")],
    # Necro bolt 3 frames (Death Bolt = same): fly x2 + hit
    "NBOLT": [("nbolt_fly1", "drain_fly1", 8, "STA"), ("nbolt_fly2", "drain_fly2", 8, "STA"),
              ("nbolt_hit", "firebolt_burst1", 8, "STA")],
}
# group -> frames (Fr). Real groups first.
SKEL_WALK_NAMES = {"skeleton_walk1", "skeleton_walk2", "skeleton_walk3", "skeleton_walk4"}
GROUPS = {
    "RAT": F("K_RAT"), "BAT": F("K_BAT"), "SLIME": F("K_SLIME"), "GOBLIN": F("K_GOBLIN"),
    "GHOST": F("K_GHOST"), "SKELETON": F("K_SKELETON"),
    "SKEL_WALK": F("K_SKELETON", SKEL_WALK_NAMES),
    "DEAD_R": F("K_RAT", {"rat_dead"}),
    "ARROWS": F("U_FXW", {"arrow_fly1", "arrow_fly2", "arrow_hit"}),
}
for g, lst in STAND_IN.items():
    GROUPS[g] = [Fr(*t) for t in lst]
STAND_IN_GROUPS = list(STAND_IN)


def gsize(g):
    return sum(f.pool() for f in GROUPS[g])


# ---- level kind sets (game.md §9.1 Depths column) --------------------------
LEVELS = {
    1: ["Rat", "Bat", "Slime", "Goblin"],
    2: ["Goblin", "Spider", "Bat", "Rat"],
    3: ["Skeleton", "Vampire", "Ghost", "Bat"],
    4: ["Orc", "Rat", "Spider", "Archer", "Ogre"],
    5: ["Mummy", "Skeleton", "Archer", "Spider"],
    6: ["Vampire", "Ghost", "Necro", "Orc"],
    7: ["Orc", "Archer", "Ghost", "Necro", "DK"],
    8: ["Necro", "Skeleton", "Ghost", "Vampire", "Archmage"],
}
# kind -> groups it needs.  (own = the shared-frame group this kind may duplicate)
KIND_GROUPS = {
    "Rat": ["RAT"], "Bat": ["BAT"], "Slime": ["SLIME"], "Goblin": ["GOBLIN"],
    "Ghost": ["GHOST"], "Skeleton": ["SKELETON"],
    "Spider": ["SPIDER", "DEAD_R"],
    "Orc": ["ORC", "DEAD_H"], "Mummy": ["MUMMY", "DEAD_H"],
    "Ogre": ["OGRE", "DEAD_H"], "DK": ["DK", "DEAD_H"],
    "Necro": ["NECRO", "NBOLT", "DEAD_H"],
    "Archer": ["SKEL_WALK", "ARCHER_SHOOT", "DEAD_H"],
    "Vampire": ["NECRO", "DEAD_H"],               # + BAT when the bat-form set is on
    "Archmage": ["NECRO", "NBOLT", "DEAD_H"],     # drawn with Necro frames
}
# groups that Vampire / Archmage / Archer take as private pool copies in OWN mode
OWN_COPY = {"Vampire": "NECRO", "Archmage": "NECRO", "Archer": "SKEL_WALK"}

HEROES = {  # hero kind sets incl. class FX (PHASE_SHIFT 1)
    "Warrior": sum(f.pool() for f in REAL["K_KNIGHT"]) + sum(f.pool() for f in REAL["U_FXW"]),
    # U_FXM kind frames + the two shared fizz frames (FRM'd under U_FXW): POOL_FXM = 1,152
    "Mage": sum(f.pool() for f in REAL["K_WIZARD"]) + sum(f.pool() for f in REAL["U_FXM"])
            + sum(f.pool() for f in REAL["U_FXW"] if f.name in ("spark_fizz1", "spark_fizz2")),
}


def level_need(d, hero, bat=True, own=False):
    """-> (total, parts dict).  own: Vampire/Archmage/Archer keep private copies."""
    kinds = LEVELS[d]
    copies = []
    # shared pool: union of groups; own: extra copies for the three sharers
    union = set()
    for k in kinds:
        for g in KIND_GROUPS[k]:
            if g in ("RAT", "BAT") and g in union:
                continue
            union.add(g)
        if k == "Vampire" and bat:
            union.add("BAT")
    if "Rat" in kinds:
        union.discard("DEAD_R")                      # rat_dead is already in RAT
    for g in union:
        copies.append((g, ""))
    if own:
        for k in kinds:
            if k in OWN_COPY:
                g = OWN_COPY[k]
                # first copy of the group already counted if its natural owner is on
                # the level (Necro for NECRO, Skeleton for SKEL_WALK); otherwise the
                # sharer's copy IS the only copy -> not a duplicate.
                owner_here = ("Necro" in kinds) if g == "NECRO" else ("Skeleton" in kinds)
                if k == "Archmage" and "Vampire" in kinds and not owner_here:
                    owner_here = True                # Vampire's copy exists; Archmage duplicates it
                if owner_here:
                    copies.append((g, k))
        # Vampire-without-Necro level: group counted once above acts as Vampire's copy.
    monsters = sum(gsize(g) for g, _ in copies if g not in ("ARROWS",) and g not in
                   ("DEAD_H", "DEAD_R", "NBOLT"))
    shared = sum(gsize(g) for g, _ in copies if g in ("DEAD_H", "DEAD_R"))
    proj = sum(gsize(g) for g, _ in copies if g == "NBOLT")
    arrows = 0
    if hero == "Mage" and "Archer" in kinds:
        arrows = gsize("ARROWS")
    tot = monsters + shared + proj + arrows + HEROES[hero] + FIXED
    return tot, dict(monsters=monsters, shared=shared, proj=proj, arrows=arrows,
                     hero=HEROES[hero], fixed=FIXED, copies=[c for c in copies])


# ---- packed sources --------------------------------------------------------
def packed_sizes():
    """-> (existing_total, {group: packed}, blocks) via zx0_sources partition/pack."""
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        for g in STAND_IN_GROUPS:
            out[g] = GROUPS[g]
        frames = dict(zp.game_frames())
        res = {}
        for g, fl in out.items():
            seg = [(f.name, frames[f.src]) for f in fl]
            parts = zs.partition(seg, tmp)
            tot = sum(len(zs.pack(b"".join(d for _, d in seg[s:s + k]), tmp)) for s, k in parts)
            res[g] = (tot, sum(len(d) for _, d in seg), len(parts))
        # the OWN-copy source delta: Necro set again (Vampire, Archmage) + Skeleton walk
        sk = [(f.name, frames[f.name]) for f in GROUPS["SKEL_WALK"]]
        parts = zs.partition(sk, tmp)
        res["SKEL_WALK(copy)"] = (sum(len(zs.pack(b"".join(d for _, d in sk[s:s + k]), tmp))
                                      for s, k in parts), sum(len(d) for _, d in sk), len(parts))
        # existing total, recomputed with the build tool's own method
        total = 0
        fkind = dict(zs.frm_list())
        order = [n for n in zs.frm_order() if n in frames]
        kinds = {}
        for n in order:
            kinds.setdefault(fkind[n], []).append(n)
        for k, names in kinds.items():
            fr = [(n, frames[n]) for n in names]
            for s, c in zs.partition(fr, tmp):
                total += len(zs.pack(b"".join(d for _, d in fr[s:s + c]), tmp))
    return total, res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", default=os.path.join(REPO, "docs/design/pool_spike.md"))
    a = ap.parse_args()

    # self-check vs the build
    chk = {
        "POOL_MONSTERS": sum(f.pool() for k in ("K_SKELETON", "K_GOBLIN", "K_GHOST", "K_RAT", "K_BAT", "K_SLIME")
                             for f in REAL[k]),
        "POOL_KNIGHT": sum(f.pool() for f in REAL["K_KNIGHT"]),
        "POOL_WIZARD": sum(f.pool() for f in REAL["K_WIZARD"]),
    }
    for k, v in chk.items():
        s = sym(k, None)
        assert s is None or s == v, f"{k}: model {v} != build {s}"
    cap = sym("POOL_CAP", POOL_CAP_FALLBACK)
    pk_tot = sym("ZX0_PACKED_TOTAL", ZX0_PACKED_TOTAL_FALLBACK)
    ex_total, new = packed_sizes()
    assert ex_total == pk_tot, f"packed model {ex_total} != ZX0_PACKED_TOTAL {pk_tot}"

    for g in STAND_IN_GROUPS:
        for f in GROUPS[g]:
            if not f.legal():
                print(f"WARN stand-in {f.name} violates the FRM anchor rule")

    L = []
    w = L.append
    w("# 3F pool spike (junior, Python only, 2026-10-26)\n")
    w("Generated by `tools/pool_spike.py` (re-run to refresh). Stand-in frames, `PHASE_SHIFT 1`, "
      "`src/` untouched.\n")
    w(f"Baseline checks: model reproduces the build (POOL_MONSTERS {chk['POOL_MONSTERS']:,}, Knight "
      f"{chk['POOL_KNIGHT']:,}, Wizard {chk['POOL_WIZARD']:,}); packed sources recomputed with "
      f"`zx0_sources.partition` = {ex_total:,} = `ZX0_PACKED_TOTAL`. "
      f"`POOL_CAP` = **{cap:,}** (build sym; already excludes the text block and `R6_LEN`; the task text "
      f"said 39,792 = 12 B older).\n")
    w("## Assumptions\n")
    w("* Level kinds = game.md section 9.1 Depths column; Ogre on D4 and Death Knight on D7 always (lair), Archmage D8.")
    w("* Lean sets (HURT = flash; DEAD shared per body class): Spider walk1/2 + bite; **Orc walk1/2 + attack "
      "(Orc is not in the 2026-10-20 lean ruling: assumed like Mummy)**; Necro walk1/2 + cast; Mummy walk1/2 + attack; "
      "Ogre walk1/2 + slam; Death Knight walk1/2 + cleave + block; Archer = Skeleton walk1-4 (shared) + 1 shoot frame; "
      "Vampire and Archmage = Necro frames; Necro bolt 3 frames. New-kind walk1 = MOT (it is the rest frame, like "
      "Rat/Skeleton walk1), walk2 = WK0.")
    w("* Shared DEAD: `dead_humanoid` (40x16, knight_dead geometry) once per level with any new humanoid kind; "
      "Spider shares `rat_dead` (counted only when Rat is absent). If the humanoid DEAD were instead an existing "
      "frame (e.g. skeleton_collapsed) levels with that kind save its cost "
      f"({gsize('DEAD_H'):,} B).")
    w("* Arrows (3 frames, " + f"{gsize('ARROWS')} B) are added for the Mage on levels with an Archer; the Warrior's FX already holds them. "
      "Necro bolt frames (" + f"{gsize('NBOLT')} B) on Necro / Archmage levels.")
    w(f"* Fixed part as `data.asm` POOL_NEED: 2 select idles + 3 x 576 straddle = {FIXED:,}. "
      f"Hero: Warrior = Knight + U_FXW = {HEROES['Warrior']:,}; Mage = Wizard + U_FXM = {HEROES['Mage']:,}.\n")

    w("## Group sizes (pool bytes)\n")
    w("| Group | frames | pool B |")
    w("|---|---|---|")
    for g in GROUPS:
        w(f"| {g} | {len(GROUPS[g])} | {gsize(g):,} |")
    w("")

    def row(d, hero, bat=True, own=False):
        return level_need(d, hero, bat, own)

    w("## Baseline: lean set, shared frames, Bat set on D6/D8\n")
    w("| Level | Kinds | Monsters | DEAD | Bolt | Hero (W) | Total W | Slack W | Hero (M) + arrows | Total M | Slack M |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    base = {}
    for d in LEVELS:
        tw, pw = row(d, "Warrior")
        tm, pm = row(d, "Mage")
        base[d] = (tw, tm)
        w(f"| D{d} | {', '.join(LEVELS[d])} | {pw['monsters']:,} | {pw['shared']:,} | {pw['proj']:,} | "
          f"{pw['hero']:,} | {tw:,} | {cap - tw:,} | {pm['hero']:,} + {pm['arrows']} | {tm:,} | {cap - tm:,} |")
    wd = max(base, key=lambda d: max(base[d]))
    wtot = max(base[wd])
    w(f"\nTotal = monsters + DEAD + bolt (+ arrows) + hero + {FIXED:,} fixed; slack = POOL_CAP {cap:,} - total.\n")

    w("## Variants (total / slack, worst hero)\n")
    w("Columns: S = Vampire/Archmage/Archer share frames, O = each keeps a private pool copy; Bat = bat-form "
      "set on D6/D8 (D3 always has it).\n")
    w("| Level | S + Bat | S no Bat | O + Bat | O no Bat |")
    w("|---|---|---|---|---|")
    var = {}
    for d in LEVELS:
        cells = []
        for own in (False, True):
            for bat in (True, False):
                t = max(row(d, "Warrior", bat, own)[0], row(d, "Mage", bat, own)[0])
                var[(d, own, bat)] = t
        cells = [var[(d, False, True)], var[(d, False, False)], var[(d, True, True)], var[(d, True, False)]]
        w(f"| D{d} | " + " | ".join(f"{t:,} / {cap - t:,}" for t in cells) + " |")
    w("")
    w("Pool need = max over levels (the pool is sized for the worst level):\n")
    w("| Variant | Worst level | Max need | Slack vs POOL_CAP |")
    w("|---|---|---|---|")
    summary = {}
    for own in (False, True):
        for bat in (True, False):
            dmax = max(LEVELS, key=lambda d: var[(d, own, bat)])
            t = var[(dmax, own, bat)]
            summary[(own, bat)] = (dmax, t)
            w(f"| {'O' if own else 'S'} + {'Bat' if bat else 'no Bat'} | D{dmax} | {t:,} | {cap - t:,} |")
    w("")

    # drivers of the worst level
    dmax, tmax = summary[(False, True)]
    hero_w = "Warrior" if row(dmax, "Warrior")[0] >= row(dmax, "Mage")[0] else "Mage"
    _, parts = row(dmax, hero_w)
    w(f"## Worst level D{dmax} ({hero_w}) drivers (S + Bat)\n")
    w("| Component | Pool B |")
    w("|---|---|")
    w(f"| hero + class FX | {parts['hero']:,} |")
    w(f"| fixed (select idles + straddle) | {parts['fixed']:,} |")
    for g, tag in parts["copies"]:
        w(f"| {g}{'@' + tag if tag else ''} | {gsize(g):,} |")
    w("")

    w("## Packed sources (ZX0, `zx0_sources` partition)\n")
    w("| New group | frames | raw B | packed B | blocks |")
    w("|---|---|---|---|---|")
    new_tot = 0
    for g in STAND_IN_GROUPS:
        pk, raw, nb = new[g]
        new_tot += pk
        w(f"| {g} | {len(GROUPS[g])} | {raw:,} | {pk:,} | {nb} |")
    w(f"| **Lean new total** | | | **{new_tot:,}** | |")
    w("")
    own_extra = 2 * new["NECRO"][0] + new["SKEL_WALK(copy)"][0]
    w(f"* Existing `ZX0_PACKED_TOTAL` {pk_tot:,} + lean new {new_tot:,} = **{pk_tot + new_tot:,} B** "
      f"(= SRC6 need before block-overhead/alignment slop).")
    w(f"* If Vampire, Archmage and Archer were separately drawn/stored instead of sharing: "
      f"+{own_extra:,} B packed (2 x Necro set {new['NECRO'][0]:,} + Skeleton-walk copy "
      f"{new['SKEL_WALK(copy)'][0]:,}) -> {pk_tot + new_tot + own_extra:,} B.")
    est = {"SPIDER": 180, "OGRE": 410, "DK": 500, "ARCHER_SHOOT": 150, "NBOLT": 100, "MUMMY": 400}
    w("* Plan 2026-10-20 estimates vs stand-in packed: " +
      ", ".join(f"{k} {v} vs {new[k][0]}" for k, v in est.items()) + ".\n")

    # cheapest cuts (S + Bat, worst hero): what removing X from the worst level does to the global max
    w("## Cheapest cuts at the worst level\n")
    w("Pool is sized by the max level, so a cut only helps down to the next-highest level.\n")
    w("| Cut (on D%d) | saves on D%d | new global max | slack |" % (dmax, dmax))
    w("|---|---|---|---|")
    others = max(t for d, t in ((d, var[(d, False, True)]) for d in LEVELS) if d != dmax)
    cuts = []
    orig = list(LEVELS[dmax])
    for k in orig:
        LEVELS[dmax] = [x for x in orig if x != k]
        sv = tmax - max(row(dmax, "Warrior")[0], row(dmax, "Mage")[0])
        cuts.append((f"drop kind {k}", sv))
    LEVELS[dmax] = orig
    for fn, g in (("dk_block", "DK"), ("dk_cleave", "DK"), ("archer_shoot", "ARCHER_SHOOT")):
        cuts.append((f"drop frame {fn}", next(f.pool() for f in GROUPS[g] if f.name == fn)))
    for lbl, sv in sorted(cuts, key=lambda c: c[1]):
        nm = max(others, tmax - sv)
        w(f"| {lbl} | {sv:,} | {nm:,} | {cap - nm:,} |")
    w(f"\n(next-highest level: {others:,}; any single cut on D{dmax} is worth at most {tmax - others:,} B.)\n")

    slack_min = cap - wtot
    w("## Carve available\n")
    w(f"* Worst level S + Bat: **D{dmax}**, need {wtot:,} of {cap:,}, slack **{slack_min:,} B**. "
      f"This is the total that SRC6 + any R6 growth + the straddle/boot margin may take 1:1 from `POOL_CAP`.")
    w(f"* SRC6 needs about {new_tot:,} B packed (lean new sources) -> left for R6 growth / 3F data: "
      f"**{slack_min - new_tot:,} B**.")
    for (own, bat), (dm, t) in summary.items():
        w(f"* {'O' if own else 'S'} + {'Bat' if bat else 'no Bat'}: worst D{dm}, slack {cap - t:,}, "
          f"after SRC6 {cap - t - new_tot:,}.")
    text = "\n".join(L) + "\n"
    os.makedirs(os.path.dirname(a.md), exist_ok=True)
    open(a.md, "w").write(text)
    print(text)


if __name__ == "__main__":
    main()
