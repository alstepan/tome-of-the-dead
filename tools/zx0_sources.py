#!/usr/bin/env python3
"""Emit the ZX0-packed sprite SOURCES include for the build (Stage 3A tasks A5/A6).

Pre-build step (tools/build.sh runs it before sjasmplus). Writes
build/zx0/sprites_zx0.asm, which src/main.asm INCLUDEs at virtual $8000 in place
of assets/gfx/sprites/index.asm when ZX0_SOURCES = 1 (the default).

Format (docs/memory-map.md "Sprite sources (ZX0)"):
  * Generator frames (every frame named in a src/frames.asm FRM line) are grouped
    per kind, in FRM order (= fid order = gen_kind order, so the generator's
    one-block cache never thrashes), into blocks of <= ZX0_MAX_FRAMES
    consecutive frames whose raw size is <= GEN_SCRATCH_LEN (1,536 B, the
    generator-time scratch they unpack into). The partition per kind is the
    one with the fewest packed bytes (exhaustive DP over 1..4-frame blocks).
    Each block = one ZX0 stream (v2, standard, forward, no header).
  * Every packed frame becomes EQUs only (A6: no bytes in banks 1/3):
      nm      EQU zblk_N   virtual address of its packed block (FD_BLK)
      nm_zoff EQU offset   raw offset of the frame inside the block
    plus nm_w/h/cols/ax/ay copied from its .asm and nm_len = raw pixel bytes
    (cols*h*2; NO trailing ATTR byte — the raw build's nm_len includes it).
    The FRM list assembles them into the bank-5 frame descriptors (fdesc_tab:
    DW nm, DW GEN_SCRATCH + nm_zoff, DB flags; src/defs.asm FD_*).
  * Items + tiles (index.asm entries that are not generator frames) are NOT
    emitted (B3B-13): nothing at runtime reads them since B3B-8 (init_tiles
    takes tiles_common / the zap glyphs from the vdata block; the tools read
    the .asm files from disk).
  * index.asm's per-kind tables (<kind>_frames/_meta/_flags/...) are not
    emitted: nothing in the engine reads them.
Build-time metadata per block (EQUs, also in the .sym): zblk_N_raw,
zblk_N_packed, zblk_N_first (FRM-order index of its first frame), zblk_N_n.

Deterministic (zx0 optimal output is deterministic; the DP breaks ties toward
the earlier/larger split). No network: needs tools/bin/zx0 (tools/setup_zx0.sh).
If tools/bin/dzx0 exists, every block is round-tripped bit-exact.

Usage: tools/zx0_sources.py [--out build/zx0/sprites_zx0.asm] [--report]
"""
import argparse
import hashlib
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import zx0_pack as zp  # noqa: E402

SPR = os.path.join(REPO, "assets/gfx/sprites")
DATA_ASM = os.path.join(REPO, "src/frames.asm")
DZX0 = os.path.join(REPO, "tools/bin/dzx0")
OUT = os.path.join(REPO, "build/zx0/sprites_zx0.asm")
SCRATCH_LEN = 1536          # GEN_SCRATCH_LEN (src/defs.asm); ASSERTed in the output too
MAX_FRAMES = 4              # user decision: blocks of 3-4 frames of one kind


def fail(msg):
    sys.exit(f"zx0_sources: {msg}")


def frm_order():
    """Frame names in src/frames.asm FRM order (= fid order)."""
    names = []
    for line in open(DATA_ASM):
        m = re.match(r"\s+FRM\s+(\w+)\s*,", line.split(";")[0])
        if m:
            names.append(m.group(1))
    return names


def meta(name):
    """nm_w/h/cols/ax/ay EQU values (verbatim expressions) from <name>.asm."""
    out = {}
    for line in open(os.path.join(SPR, name + ".asm")):
        m = re.match(rf"^{name}_(w|h|cols|ax|ay)\s+EQU\s+([^;]+)", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    if set(out) != {"w", "h", "cols", "ax", "ay"}:
        fail(f"{name}.asm: missing metadata EQUs (have {sorted(out)})")
    return out


_cache = {}


def pack(data: bytes, tmp: str) -> bytes:
    key = hashlib.sha256(data).hexdigest()
    if key not in _cache:
        _cache[key] = zp.zx0(data, os.path.join(tmp, key[:16]))
    return _cache[key]


def partition(frames, tmp):
    """frames: [(name, bytes)] of one kind. Min packed-size split into
    contiguous blocks of 1..MAX_FRAMES frames, raw <= SCRATCH_LEN."""
    n = len(frames)
    best = [(0, [])] + [None] * n          # best[i] = (packed bytes, blocks) for frames[:i]
    for i in range(1, n + 1):
        for k in range(min(MAX_FRAMES, i), 0, -1):   # larger blocks first on ties
            seg = frames[i - k:i]
            raw = b"".join(d for _, d in seg)
            if len(raw) > SCRATCH_LEN or best[i - k] is None:
                continue
            cost = best[i - k][0] + len(pack(raw, tmp))
            if best[i] is None or cost < best[i][0]:
                best[i] = (cost, best[i - k][1] + [(i - k, k)])
    if best[n] is None:
        fail(f"a frame of {frames[0][0]} exceeds {SCRATCH_LEN} B")
    return best[n][1]


def roundtrip(z: bytes, raw: bytes, tmp: str, tag: str):
    if not os.path.exists(DZX0):
        return False
    src, dst = os.path.join(tmp, tag + ".rt.zx0"), os.path.join(tmp, tag + ".rt.out")
    open(src, "wb").write(z)
    subprocess.run([DZX0, "-f", src, dst], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if open(dst, "rb").read() != raw:
        fail(f"block {tag}: dzx0 round-trip mismatch")
    return True


def raw_source_total(index_names):
    """Bytes the raw build assembles from index.asm (frames + attr bytes +
    tables): every DEFB/DEFW item of index.asm and its includes. Strict: a
    DEFB item must be a numeric literal ($xx hex or decimal -128..255), a DEFW
    item a label or literal; DB/DW/DEFS/DS or anything unparsable fails."""
    def count(path):
        n = 0
        for ln, line in enumerate(open(path), 1):
            code = line.split(";")[0].strip()
            if ":" in code and not code.upper().startswith(("DEFB", "DEFW")):
                code = code.split(":", 1)[1].strip()          # "label: DEFB ..."
            if not code:
                continue
            kw = code.split(None, 1)[0].upper()
            if kw in ("DB", "DW", "DEFS", "DS", "DEFM", "DM", "BLOCK"):
                fail(f"{os.path.relpath(path, REPO)}:{ln}: unsupported data directive {kw!r}")
            if kw not in ("DEFB", "DEFW"):
                continue
            items = [t.strip() for t in code[len(kw):].split(",")]
            for t in items:
                ok = (re.fullmatch(r"\$[0-9A-Fa-f]{1,2}|-?\d{1,3}", t) and -128 <= zp.literal(t) <= 255) \
                    if kw == "DEFB" else re.fullmatch(r"[A-Za-z_]\w*|\$[0-9A-Fa-f]{1,4}|\d+", t)
                if not ok:
                    fail(f"{os.path.relpath(path, REPO)}:{ln}: bad {kw} item {t!r}")
            n += (1 if kw == "DEFB" else 2) * len(items)
        return n
    return count(os.path.join(SPR, "index.asm")) + sum(
        count(os.path.join(SPR, nm + ".asm")) for nm in index_names)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--report", action="store_true", help="print the block table")
    a = ap.parse_args()
    if not os.path.exists(zp.ZX0):
        fail("tools/bin/zx0 missing — run tools/setup_zx0.sh once (needs network "
             "for the pinned clone; the build itself never does)")

    index_names = re.findall(r'INCLUDE\s+"(\w+)\.asm"',
                             open(os.path.join(SPR, "index.asm")).read())
    frames = dict(zp.game_frames())                      # name -> raw pixel bytes
    order = [n for n in frm_order() if n in frames]      # generator frames, fid order
    packed_set = set(order)
    raw_files = [n for n in index_names if n not in packed_set]

    # group by kind, keeping first-appearance order of kinds in FRM order
    kinds = {}
    for n in order:
        kinds.setdefault(zp.kind(n), []).append(n)

    lines = [
        "; " + "=" * 76,
        "; sprites_zx0.asm — GENERATED by tools/zx0_sources.py (A5). DO NOT EDIT.",
        "; ZX0-packed sprite sources, INCLUDEd by src/main.asm at virtual $8000",
        "; (banks 1/3) when ZX0_SOURCES = 1. Format: see the tool's docstring and",
        "; docs/memory-map.md \"Sprite sources (ZX0)\".",
        "; " + "=" * 76,
        "",
        f"; (B3B-13: the {len(raw_files)} raw item / tile files of index.asm are not emitted:",
        "; nothing at runtime reads them.)",
        "",
    ]

    blocks, desc, tot_raw, tot_pk, rt = [], [], 0, 0, 0
    with tempfile.TemporaryDirectory() as tmp:
        for kname, names in kinds.items():
            fr = [(n, frames[n]) for n in names]
            for start, k in partition(fr, tmp):
                seg = fr[start:start + k]
                raw = b"".join(d for _, d in seg)
                z = pack(raw, tmp)
                b = len(blocks)
                rt += roundtrip(z, raw, tmp, f"zblk_{b}")
                blocks.append((b, kname, seg, raw, z))
                off = 0
                for n, d in seg:
                    desc.append((n, b, off, len(d)))
                    off += len(d)
                tot_raw += len(raw)
                tot_pk += len(z)

    lines.append("; ---- packed blocks: ZX0 v2 standard forward streams ----")
    first = 0
    for b, kname, seg, raw, z in blocks:
        names = ", ".join(n for n, _ in seg)
        lines.append(f"; block {b}: {kname} [{names}] raw {len(raw)} -> {len(z)} B "
                     f"({len(raw)/len(z):.2f}x)")
        # a stream that would run from bank 1 (virtual ..$BFFF) into bank 3
        # starts at bank 3 instead (dzx0 reads one bank's $C000 window)
        lines.append(f"    IF ($ < BANK_WINDOW) && ($ + {len(z)} > BANK_WINDOW)")
        lines.append("        DS BANK_WINDOW - $, 0")
        lines.append("    ENDIF")
        lines.append(f"zblk_{b}:")
        for i in range(0, len(z), 16):
            lines.append("        DB " + ",".join(f"${x:02X}" for x in z[i:i + 16]))
        lines.append(f"zblk_{b}_end:")
        lines.append(f"zblk_{b}_raw    EQU {len(raw)}")
        lines.append(f"zblk_{b}_packed EQU {len(z)}")
        lines.append(f"zblk_{b}_first  EQU {first}")
        lines.append(f"zblk_{b}_n      EQU {len(seg)}")
        lines.append(f"        ASSERT zblk_{b}_raw <= GEN_SCRATCH_LEN")
        lines.append(f"        ASSERT zblk_{b}_end - zblk_{b} == zblk_{b}_packed")
        # dzx0 reads the stream through the $C000 window of ONE bank: it must
        # not run from bank 1's end (virtual $BFFF) into bank 3
        lines.append(f"        ASSERT (zblk_{b}_end <= BANK_WINDOW) || (zblk_{b} >= BANK_WINDOW)")
        first += len(seg)
    lines.append("")
    lines.append("; ---- per-frame EQUs (A6: the descriptors are fdesc_tab in bank 5) ----")
    for n, b, off, ln in desc:
        m = meta(n)
        lines.append(f"{n} EQU zblk_{b}                ; FD_BLK; raw {ln} B")
        lines.append(f"{n}_zoff EQU {off}               ; FD_FRM = GEN_SCRATCH + {off}")
        for f in ("w", "h", "cols", "ax", "ay"):
            lines.append(f"{n}_{f} EQU {m[f]}")
        lines.append(f"{n}_len EQU {ln}                ; raw pixel bytes (no ATTR byte)")
        lines.append(f"        ASSERT {n}_cols * {n}_h * 2 == {n}_len")
        lines.append(f"        ASSERT {off} + {n}_len <= zblk_{b}_raw")
    lines.append("")
    lines.append(f"ZX0_BLOCKS        EQU {len(blocks)}")
    lines.append(f"ZX0_FRAMES        EQU {len(desc)}")
    lines.append(f"ZX0_PACKED_RAW    EQU {tot_raw}       ; raw bytes of the packed frames")
    lines.append(f"ZX0_PACKED_TOTAL  EQU {tot_pk}        ; their packed streams")
    lines.append(f"ZX0_RAW_SRC_TOTAL EQU {raw_source_total(index_names)}   "
                 "; what the ZX0_SOURCES=0 build assembles from index.asm")
    text = "\n".join(lines) + "\n"

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    old = open(a.out).read() if os.path.exists(a.out) else None
    if old != text:                                     # keep mtime stable if unchanged
        with open(a.out, "w") as f:
            f.write(text)
    print(f"zx0_sources: {len(desc)} frames in {len(blocks)} blocks, raw {tot_raw} -> "
          f"packed {tot_pk} B ({tot_raw/tot_pk:.3f}x); "
          f"{'round-trip ok' if rt else 'dzx0 absent: no round-trip'}; -> "
          f"{os.path.relpath(a.out, REPO)}")
    if a.report:
        for b, kname, seg, raw, z in blocks:
            print(f"  blk {b:2d} {kname:9s} n={len(seg)} raw={len(raw):5d} packed={len(z):4d} "
                  f"{len(raw)/len(z):.2f}x  " + ",".join(n for n, _ in seg))


if __name__ == "__main__":
    main()
