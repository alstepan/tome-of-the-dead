#!/usr/bin/env python3
"""Emit the ZX0-packed sprite SOURCES include for the build (Stage 3A tasks A5/A6).

Pre-build step (tools/build.sh runs it before sjasmplus). Writes
build/zx0/sprites_zx0.asm, which src/main.asm INCLUDEs at virtual $8000 in place
of assets/gfx/sprites/index.asm when ZX0_SOURCES = 1 (the default).

Format (docs/memory-map.md "Sprite sources (ZX0)"):
  * Generator frames (every frame named in a src/frames.asm FRM line) are grouped
    per kind (the FRM kind argument; D3-4), in FRM order (= fid order = gen_kind order, so the generator's
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

SRC6 (SRC6 spike, 3F memory plan): a second output, build/zx0/src6_zx0.asm,
INCLUDEd by src/main.asm at SRC6_ADDR in bank 6 (docs/memory-map.md "SRC6
region"). It holds
  * the blocks of every FRM kind named in SRC6_KINDS (below; env SRC6_KINDS=
    "K_RAT,K_SLIME" overrides it for a test build) — same partition, same
    EQUs, but nm EQU zblk_N - SRC6_VDELTA (virtual $4000..$7FFF = bank 6 in
    zx0_frame) and no bytes in banks 1/3;
  * the 3F pool-spike STAND-IN blocks (tools/pool_spike.py STAND_IN, one block
    per group, labels s6s_<i>), each assembled only if bit i of SRC6_STANDIN
    (defs.asm) is set. Nothing references them (no FRM line): they hold the
    room the lean 3F sources need and tests/zx0_pool.py decodes them through
    zx0_frame (S6). Retire them group by group as the real 3F art lands.

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
OUT6 = os.path.join(REPO, "build/zx0/src6_zx0.asm")
# FRM kinds whose packed sources live in the bank-6 SRC6 region (3F art goes
# here; 3F-T13: the 3F-A1 lean set + the shared groups; CORPSE-ASHES: G_DEADH retired).
# SRC6_KINDS in the environment overrides (test builds; it REPLACES the set).
SRC6_KINDS = {"K_SPIDER", "K_ORC", "K_NECRO", "K_MUMMY", "K_OGRE", "K_DKNIGHT", "G_CLIMBH",
              "G_NBOLT"}
if os.environ.get("SRC6_KINDS") is not None:
    SRC6_KINDS = {k.strip() for k in os.environ["SRC6_KINDS"].split(",") if k.strip()}
SCRATCH_LEN = 1536          # GEN_SCRATCH_LEN (src/defs.asm); ASSERTed in the output too
MAX_FRAMES = 4              # user decision: blocks of 3-4 frames of one kind


def fail(msg):
    sys.exit(f"zx0_sources: {msg}")


def frm_list():
    """[(name, kind)] in src/frames.asm FRM order (= fid order); kind = the
    FRM kind argument (K_*)."""
    out = []
    for line in open(DATA_ASM):
        m = re.match(r"\s+FRM\s+(\w+)\s*,\s*(\w+)\s*,", line.split(";")[0])
        if m:
            out.append((m.group(1), m.group(2)))
    return out


def frm_order():
    """Frame names in src/frames.asm FRM order (= fid order)."""
    return [n for n, _ in frm_list()]


def meta(name):
    """nm_w/h/cols/ax/ay EQU values (verbatim expressions) from <name>.asm."""
    out = {}
    for line in open(zp.sprite_asm(name)):
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


def standin_blocks(tmp):
    """SRC6 stand-ins: [(bit, group, [(name, raw)], raw, packed)] in
    tools/pool_spike.py STAND_IN order (bit i = SRC6_STANDIN bit), one ZX0
    block per group (its frames' bytes are borrowed from existing art)."""
    import pool_spike as ps                       # lazy: it imports this module
    frames = dict(zp.game_frames())
    out = []
    for i, g in enumerate(ps.STAND_IN_GROUPS):
        seg = [(f.name, frames[f.src]) for f in ps.GROUPS[g]]
        if len(partition(seg, tmp)) != 1:
            fail(f"SRC6 stand-in {g}: more than one block")
        raw = b"".join(d for _, d in seg)
        out.append((i, g, seg, raw, pack(raw, tmp)))
    return out


def write_if_changed(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    old = open(path).read() if os.path.exists(path) else None
    if old != text:                                     # keep mtime stable if unchanged
        with open(path, "w") as f:
            f.write(text)


def block_lines(label, z):
    return ([f"{label}:"] +
            ["        DB " + ",".join(f"${x:02X}" for x in z[i:i + 16]) for i in range(0, len(z), 16)] +
            [f"{label}_end:"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--out6", default=OUT6)
    ap.add_argument("--report", action="store_true", help="print the block table")
    a = ap.parse_args()
    if not os.path.exists(zp.ZX0):
        fail("tools/bin/zx0 missing — run tools/setup_zx0.sh once (needs network "
             "for the pinned clone; the build itself never does)")

    index_names = zp.index_names(SPR)
    frames = dict(zp.game_frames())                      # name -> raw pixel bytes
    order = [n for n in frm_order() if n in frames]      # generator frames, fid order
    packed_set = set(order)
    raw_files = [n for n in index_names if n not in packed_set]

    # group by the FRM kind argument (D3-4: the FX kinds mix name prefixes),
    # keeping first-appearance order of kinds in FRM order; a block never
    # mixes kinds (one gen_kind unpacks only its own blocks)
    fkind = dict(frm_list())
    kinds = {}
    for n in order:
        kinds.setdefault(fkind[n], []).append(n)

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

    unknown = SRC6_KINDS - set(fkind.values())
    if unknown:
        fail(f"SRC6_KINDS: no FRM kind {sorted(unknown)}")
    blocks, desc, tot_raw, tot_pk, rt = [], [], 0, 0, 0
    with tempfile.TemporaryDirectory() as tmp:
        standins = standin_blocks(tmp)
        for i, g, seg, raw, z in standins:
            rt += roundtrip(z, raw, tmp, f"s6s_{i}")
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
    lines6 = [
        "; " + "=" * 76,
        "; src6_zx0.asm — GENERATED by tools/zx0_sources.py (SRC6 spike). DO NOT EDIT.",
        "; Bank-6 SRC6 sprite sources, INCLUDEd by src/main.asm at SRC6_ADDR",
        "; (docs/memory-map.md \"SRC6 region\"). FD_BLK = real - SRC6_VDELTA.",
        "; " + "=" * 76,
        "SRC6_BLOCKS = 0",
        "SRC6_RAW = 0",
        "",
    ]
    first = 0
    for b, kname, seg, raw, z in blocks:
        names = ", ".join(n for n, _ in seg)
        if kname in SRC6_KINDS:              # a real kind's block in bank 6 (no bank-1/3 bytes)
            lines6.append(f"; block {b}: {kname} [{names}] raw {len(raw)} -> {len(z)} B")
            lines6 += block_lines(f"zblk_{b}", z)
            lines6 += [f"zblk_{b}_raw    EQU {len(raw)}", f"zblk_{b}_packed EQU {len(z)}",
                       f"zblk_{b}_first  EQU {first}", f"zblk_{b}_n      EQU {len(seg)}",
                       f"        ASSERT zblk_{b}_raw <= GEN_SCRATCH_LEN",
                       f"        ASSERT zblk_{b}_end - zblk_{b} == zblk_{b}_packed",
                       "SRC6_BLOCKS = SRC6_BLOCKS + 1", f"SRC6_RAW = SRC6_RAW + {len(raw)}"]
            first += len(seg)
            continue
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
    in6 = {b for b, kname, *_ in blocks if kname in SRC6_KINDS}
    for n, b, off, ln in desc:
        m = meta(n)
        if b in in6:
            lines.append(f"{n} EQU zblk_{b} - SRC6_VDELTA  ; FD_BLK (SRC6, bank 6); raw {ln} B")
        else:
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
    write_if_changed(a.out, "\n".join(lines) + "\n")

    lines6.append("; ---- 3F stand-in blocks (tools/pool_spike.py STAND_IN; bit i of SRC6_STANDIN) ----")
    for i, g, seg, raw, z in standins:
        lines6.append(f"; stand-in {i}: {g} [{', '.join(n for n, _ in seg)}] raw {len(raw)} -> {len(z)} B")
        lines6.append(f"    IF SRC6_STANDIN & (1 << {i})")
        lines6 += block_lines(f"s6s_{i}", z)
        lines6 += [f"s6s_{i}_raw    EQU {len(raw)}", f"s6s_{i}_packed EQU {len(z)}",
                   f"s6s_{i}_virt   EQU s6s_{i} - SRC6_VDELTA   ; its FD_BLK value",
                   f"        ASSERT s6s_{i}_raw <= GEN_SCRATCH_LEN",
                   f"        ASSERT s6s_{i}_end - s6s_{i} == s6s_{i}_packed",
                   "SRC6_BLOCKS = SRC6_BLOCKS + 1", f"SRC6_RAW = SRC6_RAW + {len(raw)}",
                   "    ENDIF"]
    lines6.append(f"        ASSERT SRC6_STANDIN >= 0 && SRC6_STANDIN < (1 << {len(standins)})")
    write_if_changed(a.out6, "\n".join(lines6) + "\n")
    n6 = len(in6)
    print(f"zx0_sources: {len(desc)} frames in {len(blocks)} blocks, raw {tot_raw} -> "
          f"packed {tot_pk} B ({tot_raw/tot_pk:.3f}x); "
          f"{'round-trip ok' if rt else 'dzx0 absent: no round-trip'}; -> "
          f"{os.path.relpath(a.out, REPO)}; SRC6: {n6} real blocks "
          f"({','.join(sorted(SRC6_KINDS)) or 'none'}) + {len(standins)} stand-ins "
          f"({sum(len(t[4]) for t in standins)} B) -> {os.path.relpath(a.out6, REPO)}")
    if a.report:
        for b, kname, seg, raw, z in blocks:
            print(f"  blk {b:2d} {kname:9s} n={len(seg)} raw={len(raw):5d} packed={len(z):4d} "
                  f"{len(raw)/len(z):.2f}x  " + ",".join(n for n, _ in seg))


if __name__ == "__main__":
    main()
