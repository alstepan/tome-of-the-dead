#!/usr/bin/env python3
"""tools/size_report.py -- per-bank / per-file size report + cross-bank duplicate-run scan.

Reads the artefacts tools/build.sh already writes (build/tome-of-the-dead.lst, .sld,
.sna, sjasmplus.log); nothing is added to the build.  Stdlib only.

  tools/size_report.py                  files per bank, bank totals, duplicate runs
  tools/size_report.py --min 16         duplicate-run minimum length (default 12)
  tools/size_report.py --top 10         rows shown per table (0 = all)
  tools/size_report.py --build          run tools/build.sh -DDEBUG_KIT=0 first
  tools/size_report.py -d DIR           use DIR/build instead of the repo's build/
  tools/size_report.py --check          self-check, exit 1 on mismatch: the bank-3 sizes
                                        summed from the listing must equal the build's
                                        DISPLAY lines ("bank-3 cold code" and "AY slot")

How a size is measured: every listing line carries the address at which it assembles;
a line's size is the next line's address minus its own, so a file's size is the sum over
its own lines (ALIGN / DS padding included, nested INCLUDEs counted to the inner file).
The bank of a line comes from the .sld (page of the instruction / label on that line).
ORG / MMU / DISP-style directive lines are not counted (so is the main.asm INCBIN
of the loading picture, a tape-saving trick over slot 1).  Lines inside DISP..ENT blocks
(overlay raw images assembled at a virtual address) go to the pseudo-bank "ovl" and are
excluded from totals and from the duplicate scan, since their address is not their
place in the snapshot.  "free" = 16384 - bytes emitted in that bank (gaps between
regions count as free; it is a lower-bound hint, the build's DISPLAY lines are exact).

The duplicate scan reads the bank contents from the .sna (128K snapshot), restricted to
bytes the listing says were emitted; runs made of < --min-distinct distinct byte values
(zero fill, simple pads) are ignored.  Score = length x (copies - 1) = bytes a shared
copy would save.
"""
import argparse
import collections
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK = 0x4000
# lst columns (sjasmplus): 4-digit line no + 2 marker cols, 4-hex address at [6:10],
# bytes field [11:24], source text from col 24.
SRC_COL = 24
NO_EMIT = {"ORG", "DISP", "ENT", "MMU", "SLOT", "PAGE", "DEVICE", "OPT", "ASSERT",
           "DISPLAY", "INCLUDE", "INCBIN", "END", "SAVETAP", "SAVESNA", "SAVEBIN",
           "EQU", "DEFL", "MACRO", "ENDM", "IF", "IFDEF", "IFNDEF", "ELSE", "ENDIF",
           "DEFINE", "UNDEFINE", "MODULE", "ENDMODULE", "TAPOUT", "EMPTYTAP",
           "OUTPUT", "SHELLEXEC", "LABELSLIST", "SIZE", "ENDS"}
# INCBIN emits bytes: it must be counted, so it is handled apart below.
NO_EMIT.discard("INCBIN")

OPEN_RE = re.compile(r"^# file (opened|closed): (.*)$")


def paths(bdir):
    b = os.path.join(bdir, "build")
    return {k: os.path.join(b, v) for k, v in
            dict(lst="tome-of-the-dead.lst", sld="tome-of-the-dead.sld",
                 sna="tome-of-the-dead.sna", log="sjasmplus.log").items()}


def load_sld(path):
    """(file basename, line) -> page, for instruction (T) and label (F) entries."""
    pg = {}
    with open(path, errors="replace") as f:
        for ln in f:
            p = ln.rstrip("\n").split("|")
            if len(p) >= 7 and p[6] in ("T", "F"):
                try:
                    page = int(p[4])
                except ValueError:
                    continue
                if page >= 0:
                    pg[(os.path.basename(p[0]), int(p[1]))] = page
    return pg


def parse_lst(path, sld):
    """-> list of records [file, line, addr, page, first_token, in_disp] in listing order."""
    recs = []
    stack = []
    in_disp = False
    with open(path, errors="replace") as f:
        for ln in f:
            if ln.startswith("#"):
                m = OPEN_RE.match(ln)
                if m:
                    if m.group(1) == "opened":
                        stack.append(os.path.basename(m.group(2)))
                    elif stack:
                        stack.pop()
                continue
            if len(ln) < 10 or not stack:
                continue
            try:
                lno = int(ln[0:4])
                addr = int(ln[6:10], 16)
            except ValueError:
                continue
            src = ln[SRC_COL:].split(";", 1)[0].rstrip("\n") if len(ln) > SRC_COL else ""
            toks = src.split()
            if toks and src and not src[0].isspace():     # a label in col 0
                toks = toks[1:] if not toks[0].upper() in NO_EMIT else toks
                # "label EQU x" keeps EQU as the first token
                if len(src.split()) > 1 and src.split()[1].upper() == "EQU":
                    toks = ["EQU"]
            first = toks[0].upper().rstrip(":") if toks else ""
            if first == "INCBIN" and ("slot1_park" in src or ".scr" in src):
                first = "EQU"       # the tape-saving park / restore of the loading picture
            if first == "DISP":
                in_disp = True
            f0 = stack[-1]
            recs.append([f0, lno, addr, sld.get((f0, lno), -1), first, in_disp])
            if first == "ENT":
                in_disp = False
    return recs


def assign_sizes(recs):
    """Fill page gaps and return rows (file, line, addr, size, page, in_disp)."""
    n = len(recs)
    # page of a line without sld info: the next known page in the same slot within the
    # same file, else the last known page of that slot
    last = {}
    nxt = [None] * n
    seen = {}
    for i in range(n - 1, -1, -1):
        f, _, addr, pg, _, _ = recs[i]
        slot = addr >> 14
        if pg >= 0:
            seen[(f, slot)] = pg
        nxt[i] = seen.get((f, slot))
    for i in range(n):
        f, _, addr, pg, _, _ = recs[i]
        slot = addr >> 14
        if pg >= 0:
            last[slot] = pg
        else:
            recs[i][3] = nxt[i] if nxt[i] is not None else last.get(slot, -1)
            if recs[i][3] >= 0:
                last[slot] = recs[i][3]
    rows = []
    for i in range(n - 1):
        f, lno, addr, pg, first, dsp = recs[i]
        if first in NO_EMIT:
            continue
        d = recs[i + 1][2] - addr
        if d <= 0 or d > 0x4000:
            continue
        rows.append((f, lno, addr, d, pg, dsp))
    return rows


def report(rows, top):
    banks = collections.defaultdict(lambda: collections.defaultdict(int))
    for f, _, _, d, pg, dsp in rows:
        banks[("ovl" if dsp else pg)][f] += d
    out = []
    totals = {}
    for b in sorted(banks, key=lambda x: (isinstance(x, str), x)):
        files = banks[b]
        tot = sum(files.values())
        totals[b] = tot
        free = "" if b == "ovl" else f", free {BANK - tot} of {BANK}"
        out.append(f"bank {b}: total {tot} B{free}")
        items = sorted(files.items(), key=lambda kv: -kv[1])
        for f, d in (items if not top else items[:top]):
            out.append(f"    {d:6d}  {f}")
        if top and len(items) > top:
            out.append(f"    ...    ({len(items) - top} more files, "
                       f"{sum(d for _, d in items[top:])} B)")
    return banks, totals, out


def load_sna(path):
    with open(path, "rb") as f:
        d = f.read()
    if len(d) < 27 + 3 * BANK + 4 + 5 * BANK:
        raise SystemExit(f"{path}: not a 128K snapshot ({len(d)} B)")
    paged = d[27 + 3 * BANK + 2 + 1] & 7
    banks = {5: d[27:27 + BANK], 2: d[27 + BANK:27 + 2 * BANK],
             paged: d[27 + 2 * BANK:27 + 3 * BANK]}
    off = 27 + 3 * BANK + 4
    for b in range(8):
        if b not in banks:
            banks[b] = d[off:off + BANK]
            off += BANK
    return banks


def dup_scan(rows, snap, mn, mind, top):
    """Maximal duplicate runs of >= mn bytes over emitted bytes of all banks."""
    # emitted mask + origin (file, line) per (bank, addr)
    where = {}
    for f, lno, addr, d, pg, dsp in rows:
        if dsp or pg < 0 or pg > 7:
            continue
        for a in range(addr, addr + d):
            where[(pg, a & 0x3FFF if a >= 0x4000 else a)] = (f, lno, a)
    # linear sequence: tuples of (bank, offset) in order, None = break
    seq = []
    bytes_ = []
    for b in range(8):
        for off in range(BANK):
            if (b, off + BANK * (1 if b == 5 else 0)) in where or (b, off) in where \
                    or (b, off + 0x4000 * 1) in where or (b, off + 0x8000) in where \
                    or (b, off + 0xC000) in where:
                seq.append((b, off))
                bytes_.append(snap[b][off])
            else:
                seq.append(None)
                bytes_.append(-1)
        seq.append(None)
        bytes_.append(-1)
    N = len(bytes_)
    groups = collections.defaultdict(list)
    for i in range(N - mn + 1):
        if bytes_[i + mn - 1] < 0:
            continue
        w = bytes_[i:i + mn]
        if -1 in w:
            continue
        groups[bytes(w)].append(i)
    consumed = bytearray(N)
    found = []
    for key in sorted((k for k, v in groups.items() if len(v) > 1),
                      key=lambda k: groups[k][0]):
        pos = groups[key]
        if all(consumed[p] for p in pos):
            continue
        ln = mn
        while all(p + ln < N and bytes_[p + ln] >= 0 and
                  bytes_[p + ln] == bytes_[pos[0] + ln] for p in pos):
            ln += 1
        run = bytes_[pos[0]:pos[0] + ln]
        if len(set(run)) < mind:
            continue
        # periodic self-overlap inside one place is not a copy: keep non-overlapping
        keep = []
        for p in pos:
            if not keep or p >= keep[-1] + ln:
                keep.append(p)
        if len(keep) < 2:
            continue
        for p in keep:
            for q in range(p, p + ln):
                consumed[q] = 1
        found.append((ln * (len(keep) - 1), ln, keep))

    def loc(i):
        b, off = seq[i]
        # address as seen in the listing: try the slot where the origin exists
        for base in (0xC000, 0x8000, 0x4000, 0):
            o = where.get((b, off + base)) or where.get((b, off))
            if o:
                return f"{b}:{o[2]:04X} {o[0]}:{o[1]}"
        return f"{b}:{off:04X}"
    found.sort(key=lambda t: (-t[0], -t[1]))
    out = []
    for score, ln, keep in (found if not top else found[:top]):
        out.append(f"{ln:5d} B x {len(keep)}  save {score:5d} B   " +
                   "  |  ".join(loc(p) for p in keep[:4]) +
                   (f"  | +{len(keep) - 4} more" if len(keep) > 4 else ""))
    return found, out


def display_ints(logpath):
    """(cold_len, ay_len) from the DISPLAY lines of the build log."""
    txt = open(logpath, errors="replace").read()
    m1 = re.search(r"bank-3 cold code: 0x([0-9A-F]+)\.\.0x([0-9A-F]+) \((\d+) B\)", txt)
    m2 = re.search(r"AY slot \(bank 3\): 0x([0-9A-F]+)\.\.0x([0-9A-F]+) \((\d+) B of", txt)
    if not (m1 and m2):
        raise SystemExit("--check: bank-3 DISPLAY lines not found in " + logpath)
    return ((int(m1.group(1), 16), int(m1.group(2), 16), int(m1.group(3))),
            (int(m2.group(1), 16), int(m2.group(2), 16), int(m2.group(3))))


def check(rows, logpath):
    (c0, c1, cl), (a0, a1, al) = display_ints(logpath)
    cold = sum(d for f, l, a, d, pg, dsp in rows if pg == 3 and not dsp and c0 <= a <= c1)
    ay = sum(d for f, l, a, d, pg, dsp in rows if pg == 3 and not dsp and a0 <= a <= a1)
    bad = []
    if cold != cl:
        bad.append(f"bank-3 cold code: report {cold} B vs DISPLAY {cl} B")
    if ay != al:
        bad.append(f"bank-3 AY slot: report {ay} B vs DISPLAY {al} B")
    if bad:
        print("size_report --check: FAIL\n  " + "\n  ".join(bad))
        return 1
    print(f"size_report --check: OK (bank-3 cold {cold} B + AY slot {ay} B match DISPLAY)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--min", type=int, default=12, help="duplicate run minimum bytes")
    ap.add_argument("--min-distinct", type=int, default=3,
                    help="ignore runs with fewer distinct byte values (fill)")
    ap.add_argument("--top", type=int, default=0, help="rows per table (0 = all)")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--no-dups", action="store_true")
    ap.add_argument("--build", action="store_true", help="run tools/build.sh -DDEBUG_KIT=0 first")
    ap.add_argument("-d", "--dir", default=ROOT, help="tree whose build/ to read")
    a = ap.parse_args()
    if a.build:
        subprocess.run([os.path.join(ROOT, "tools", "build.sh"), "-DDEBUG_KIT=0"], check=True)
    p = paths(a.dir)
    for k in ("lst", "sld", "log") + (() if a.check or a.no_dups else ("sna",)):
        if not os.path.exists(p[k]):
            raise SystemExit(f"missing {p[k]} -- run tools/build.sh (or pass --build)")
    rows = assign_sizes(parse_lst(p["lst"], load_sld(p["sld"])))
    if a.check:
        return check(rows, p["log"])
    _, _, lines = report(rows, a.top)
    print("\n".join(lines))
    if not a.no_dups:
        found, out = dup_scan(rows, load_sna(p["sna"]), a.min, a.min_distinct, a.top)
        print(f"\nduplicate runs >= {a.min} B ({len(found)} runs, "
              f"{sum(s for s, _, _ in found)} B shareable); location bank:addr file:line")
        print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
