#!/usr/bin/env python3
"""Apply simulator override JSONs (tools/balance_*.json) to the game tables.

  python3 tools/apply_balance.py tools/balance_optionA.json tools/balance_pkgW3.json \
          tools/balance_pkgFINAL_B.json            # dry run: prints every cell old -> new
  ... --write                                      # edits src/combat_data3.asm, src/main.asm, tools/levelgen.py

JSONs are merged in order (balance_sim.merge semantics), then each cell is resolved to its source
location and CHECKED: a cell whose current value already equals the target is reported "same".
Cells handled: ab_rank (RANK rows of ab_rank), kx (KXROW resist columns, by the "; K_NAME" comment),
kind hp/atk/bonus/die (KROW columns of kind_tab in main.asm, + the hp copies in levelgen.KROWS and KINFO).
Run once on the pre-BAL-1 tables; re-running is idempotent (everything reports "same").
"""
import json, os, re, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CD3 = os.path.join(REPO, "src", "combat_data3.asm")
MAIN = os.path.join(REPO, "src", "main.asm")
LG = os.path.join(REPO, "tools", "levelgen.py")

SPELLS = ["Spark", "Firebolt", "Frost", "Drain", "Lightning", "Power", "Whirl"]
CELLS = ["mp", "range", "die", "bonus", "bounces", "effect"]
TYPES = ["PHYS", "FIRE", "COLD", "SHOCK", "DRAIN", "DARK"]
RSP = {"N": "0", "R": "RSP_R", "I": "RSP_I", "X": "RSP_X", "W": "RSP_W"}
KROW_COL = {"Ogre": 15}                         # kind_tab column (K_OGRE = 15)
KROW_LINE = {"hp": "; KT_HP", "atk": "; KT_ATK", "die": "; KT_DIE", "bonus": "; KT_BONUS"}


def merge(a, b):
    out = dict(a)
    for k, v in b.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = "--write" in sys.argv
    ov = {}
    for f in args:
        ov = merge(ov, json.load(open(f)))
    cd3 = open(CD3).read().split("\n")
    main_ = open(MAIN).read().split("\n")
    lg = open(LG).read()
    changes = same = 0
    log = []

    # ---- ab_rank: rows after the "ab_rank:" label, RANK lines in order spell*3 + rank-1
    rk_lines = []
    start = next(i for i, l in enumerate(cd3) if l.startswith("ab_rank:"))
    for i in range(start, len(cd3)):
        if re.match(r"\s+RANK\s", cd3[i]):
            rk_lines.append(i)
        if len(rk_lines) == 21:
            break
    assert len(rk_lines) == 21
    for sp, ranks in ov.get("ab_rank", {}).items():
        a = SPELLS.index(sp)
        for rnk, cells in ranks.items():
            li = rk_lines[a * 3 + int(rnk) - 1]
            m = re.match(r"(\s+RANK\s+)(.*?)(\s*;.*)?$", cd3[li])
            vals = [v.strip() for v in m.group(2).split(",", 5)]
            assert len(vals) == 6
            for c, v in cells.items():
                ci = CELLS.index(c)
                old = vals[ci]
                new = str(v)
                if c == "effect" and "RKE_SPARE" in old:
                    new = f"{v} | RKE_SPARE"            # keep the spare flag if the row has it
                if c == "effect" and v == 4 and old.startswith("("):
                    pass
                if old.replace(" ", "") == new.replace(" ", ""):
                    same += 1
                    continue
                log.append(f"ab_rank {sp} {rnk} {c}: {old} -> {new}  (src line {li + 1})")
                vals[ci] = new
                changes += 1
            cd3[li] = m.group(1) + ", ".join(vals) + (m.group(3) or "")

    # ---- kx: KXROW resist columns
    for kn, cells in ov.get("kx", {}).items():
        tag = f"; K_{kn.upper()}"
        hit = [i for i, l in enumerate(cd3) if "KXROW" in l and re.search(re.escape(tag) + r"(\b|:|\s|\()", l + " ")]
        hit = [i for i in hit if re.search(re.escape(tag) + r"(?![A-Z_0-9])", cd3[i])]
        assert len(hit) == 1, (kn, hit)
        li = hit[0]
        m = re.match(r"(\s+KXROW\s+)(.*?)(;.*)$", cd3[li])
        parts = [p.strip() for p in m.group(2).split(",")]
        for ty, rsp in cells.items():
            ci = TYPES.index(ty.upper())
            old, new = parts[ci], RSP[rsp]
            if old == new:
                same += 1
                continue
            log.append(f"kx {kn} {ty}: {old} -> {new}  (src line {li + 1})")
            parts[ci] = new
            changes += 1
        # keep the original spacing of the line: only the first 6 fields are rewritten
        rest = m.group(2)
        fields = re.split(r"(,\s*)", rest)
        for n_, p in enumerate(parts[:6]):
            fields[2 * n_] = p
        cd3[li] = m.group(1) + "".join(fields) + m.group(3)

    # ---- kind: KROW columns in main.asm kind_tab (+ levelgen hp)
    for kn, cells in ov.get("kind", {}).items():
        col = KROW_COL[kn]
        for c, v in cells.items():
            tag = KROW_LINE[c]
            li = next(i for i, l in enumerate(main_) if re.match(r"\s+KROW\s", l) and tag in l)
            m = re.match(r"(\s+KROW\s+)(.*?)(\s*;.*)$", main_[li])
            fields = re.split(r"(,\s*)", m.group(2))
            old = fields[2 * col].strip()
            if old == str(v):
                same += 1
                continue
            log.append(f"kind {kn} {c}: {old} -> {v}  (src/main.asm line {li + 1}, column {col})")
            fields[2 * col] = fields[2 * col].replace(old, str(v))
            main_[li] = m.group(1) + "".join(fields) + m.group(3)
            changes += 1
            if c == "hp":
                pat = re.compile(r'("K_%s":\s*\(\d+,\s*)(\d+)' % kn.upper())
                mm = pat.search(lg)
                assert mm, "levelgen KROWS " + kn
                log.append(f"levelgen KROWS K_{kn.upper()} hp: {mm.group(2)} -> {v}")
                lg = pat.sub(lambda x: x.group(1) + str(v), lg, count=1)
                pat2 = re.compile(r'("K_%s": \(\d+, )(\d+)' % kn.upper())      # KINFO mirror (body, hp, flyer)
                mm = pat2.search(lg)
                assert mm, "levelgen KINFO " + kn
                lg = pat2.sub(lambda x: x.group(1) + str(v), lg, count=1)
                log.append(f"levelgen KINFO K_{kn.upper()} hp -> {v}")
                changes += 1
    print("\n".join(log))
    print(f"{changes} cell(s) to change, {same} already at target")
    if write:
        open(CD3, "w").write("\n".join(cd3))
        open(MAIN, "w").write("\n".join(main_))
        open(LG, "w").write(lg)
        print("written")


if __name__ == "__main__":
    main()
