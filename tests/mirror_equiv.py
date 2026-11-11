#!/usr/bin/env python3
"""Option C premise (docs/design/mirror_c_split.md, task C-T2): blit-time mirroring of the
RIGHT pool variant is pixel-identical to the pre-mirrored LEFT variant the generator stores.

For every pool state the real game builds — the boot pool (the two select idles), D1..D8 x
both heroes (level_descend walk, as tests/zx0_pool.py) and the PROTO fixture per hero x
5 / 6 kinds — and every non-SYM fid with FRT entries, at each shift s in {0, 4}:
    right variant at s  --rowrev + bitrev-->  must equal  left variant at s   (byte for byte)
Row length = (cols + (s == 4)) pairs (mask, data); the bytes are read from the pool banks
over ZRCP (Run.dump), the geometry from frame_tab, the FD_FLAGS (SYM skip) from fdesc_tab.
A variant present on one facing only (a left shift != the right shift) is a failure too: the
mirrored left would not have the stored left's shift (the parity premise, §1).

C-T6 (FF_MIR frames: no stored left; the left FRT entries = the right ones | bank bit 7, mirrored by
blit_sprite at draw time):
  - FRT: every FF_MIR fid's left entries == its right entries with bit 7 set on the bank byte
    (FRT_NONE stays $FF), at every pool point;
  - premise: rowrev + bitrev(right variant) == the reference left variant the generator WOULD store
    (Python, from the raw frame pixels: mirror_src + gen_variant), byte for byte;
  - REAL BLIT: at the live points (each hero's last level, every PROTO pool) every non-SYM fid with a
    left variant (stored OR mirrored) is drawn by the real blit_sprite facing left (DI stub), on a $00
    and a $FF screen, cell-aligned and between cells: the screen must equal (bg & mask) | data of the
    reference left variant — pixel-exact incl. the mask.

Usage: ZRCP_PORT=10800 python3 tests/mirror_equiv.py [--no-proto] [--depths N]
Exit 1 on any mismatch.
"""
import argparse
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import zx0_pool as zp  # noqa: E402  (also puts tools/ on sys.path: test_harness)
from test_harness import Harness  # noqa: E402

BREV = zp.Ref.BREV
HERO = ("Warrior", "Mage")
RAW = None                                         # fid -> raw frame bytes (mask, data pairs)


def raw_frames(S):
    sys.path.insert(0, zp.REPO_TOOLS)
    import zx0_pack
    import zx0_sources
    frames = dict(zx0_pack.game_frames())
    names = [n for n in zx0_sources.frm_order() if n in frames]
    assert len(names) == S["FDESC_COUNT"], (len(names), S["FDESC_COUNT"])
    return [frames[n] for n in names]


def ref_left(fid, cols, h, s):
    """The left variant gen_frame would store: mirror_src (rowrev + bitrev) then gen_variant at shift s."""
    src = RAW[fid]
    mir = mirror_rows(src, cols)
    out = bytearray()
    for y in range(h):
        r = mir[y * cols * 2:(y + 1) * cols * 2]
        if not s:
            out += r
            continue
        pm, pd = 0xFF, 0
        for c in range(cols):
            m, d = r[2 * c], r[2 * c + 1]
            out += bytes((((pm << 4) & 0xF0) | (m >> 4), ((pd << 4) & 0xF0) | (d >> 4)))
            pm, pd = m, d
        out += bytes((((pm << 4) & 0xF0) | 0x0F, (pd << 4) & 0xF0))
    return bytes(out)


def variants(d, S, fid):
    """-> {var: bytes | None} of fid's 4 FRT variants (None = NONE), + (cols, h, flags)."""
    stride, oc, oh = d["FTL"]
    cols, h = d["FT"][fid * stride + oc], d["FT"][fid * stride + oh]
    flags = d["static"]["fdesc"][fid * S["FDESC_STRIDE"] + S["FD_FLAGS"]]
    row = bytes(d["FRT"][fid * S["FRT_STRIDE"]:(fid + 1) * S["FRT_STRIDE"]])
    out = {}
    for v in range(4):
        bank, lo, hi = row[3 * v:3 * v + 3]
        if bank == S["FRT_NONE"]:
            out[v] = None
            continue
        bank &= 0x7F                                # C-T6: bit 7 = mirrored at blit time
        addr = lo | hi << 8
        n = h * 2 * (cols + (v & 1))               # even var = shift 0, odd = shift 4 (+1 column)
        out[v] = bytes(d["pool"][bank][addr - 0xC000:addr - 0xC000 + n])
        assert len(out[v]) == n, (fid, v, bank, addr, n)
    return out, cols, h, flags, row


def mirror_rows(b, rowlen):
    """rowrev + bitrev: every row of rowlen (mask, data) pairs reversed, each byte bit-reversed."""
    out = bytearray()
    for o in range(0, len(b), 2 * rowlen):
        r = b[o:o + 2 * rowlen]
        for c in range(rowlen - 1, -1, -1):
            out += bytes((BREV[r[2 * c]], BREV[r[2 * c + 1]]))
    return bytes(out)


def check_point(name, d, S, stats, fails):
    n_fid = n_cmp = n_bad = n_mir = 0
    for fid in range(S["FRT_MAX"]):
        vs, cols, h, flags, row = variants(d, S, fid)
        if all(v is None for v in vs.values()) or flags & S["FF_SYM"]:
            continue
        n_fid += 1
        mir = bool(flags & S.get("FF_MIR", 0))
        if mir:                                      # C-T6: left entries = right | bank bit 7, same address
            n_mir += 1
            want = bytearray(row[0:6])
            for v in (0, 3):
                if want[v] != S["FRT_NONE"]:
                    want[v] |= 0x80
            if bytes(row[6:12]) != bytes(want):
                n_bad += 1
                fails.append(f"{name} fid {fid} FF_MIR: left FRT {row[6:12].hex()} != right|$80 {want.hex()}")
        for s, (rv, lv) in ((0, (0, 2)), (4, (1, 3))):
            r, l = vs[rv], vs[lv]
            if r is None and l is None:
                continue
            n_cmp += 1
            if r is None or l is None:
                n_bad += 1
                fails.append(f"{name} fid {fid} shift {s}: {'right' if l is None else 'left'} variant only")
            elif mirror_rows(r, cols + (s == 4)) != (ref_left(fid, cols, h, s) if mir else l):
                n_bad += 1
                fails.append(f"{name} fid {fid} shift {s}: mirror(right) != left" + (" (reference)" if mir else ""))
    stats.append((name, n_fid, n_cmp, n_bad))
    print(f"[{'PASS' if not n_bad else 'FAIL'}] {name}: {n_fid} non-SYM fids ({n_mir} FF_MIR), {n_cmp} variant "
          f"pairs, {n_bad} mismatches")


def blit_point(name, r, S, bstats, fails):
    """C-T6: the real blit_sprite, facing left, of every non-SYM fid with a left variant at the LIVE pool
    (destructive: the caller reloads afterwards)."""
    d = r.dump()
    z = r.z
    stub = S["LOWRAM_END_3B"]
    w = lambda v: [v & 0xFF, v >> 8]
    n_bl = n_bad = n_mir = 0
    for fid in range(S["FRT_MAX"]):
        vs, cols, h, flags, row = variants(d, S, fid)
        if flags & S["FF_SYM"]:
            continue
        mir = bool(flags & S.get("FF_MIR", 0))
        for v in (2, 3):
            if vs[v] is None:
                continue
            s = 4 * (v & 1)
            ref = ref_left(fid, cols, h, s)
            wd = cols + (v & 1)
            col = 4
            n_mir += mir
            for fpy in (16, 21):
                for bg in (0x00, 0xFF):
                    code = ([0xF3, 0x21] + w(0x4000) + [0x36, bg, 0x11] + w(0x4001) + [0x01] + w(6143)
                            + [0xED, 0xB0, 0xCD] + w(S["blit_sprite"]) + [0x00, 0x18, 0xFE])
                    end = stub + len(code) - 2
                    z.cmd("write-memory %d %s" % (stub, " ".join(map(str, code))))
                    r.wb("BL_FID", fid)
                    r.wb("BL_LEFT", 1)
                    r.wb("BL_FPX", col * 8 + s)
                    r.wb("BL_FPY", fpy)
                    for n in range(1, 33):
                        z.cmd("set-breakpoint %d" % n)
                    z.cmd("set-breakpoint 1 PC=%d" % end)
                    z.cmd("set-register SP=%d" % S["WORKSTORE_TOP"])
                    z.cmd("set-register PC=%d" % stub)
                    z.cmd("run %d" % zp.RUN_LIMIT)
                    if r.pc() != end:
                        raise RuntimeError(f"{name}: blit stub fid {fid} did not return")
                    scr = bytes(z.read_memory(0x4000, 6144))
                    exp = bytearray([bg]) * 6144
                    for y in range(h):
                        py = fpy + y
                        base = ((py & 0xC0) << 5) | ((py & 7) << 8) | ((py & 0x38) << 2)
                        for i in range(wd):
                            m, dd = ref[2 * (y * wd + i)], ref[2 * (y * wd + i) + 1]
                            exp[base + col + i] = (bg & m) | dd
                    n_bl += 1
                    if scr != bytes(exp):
                        n_bad += 1
                        nd = sum(a != b for a, b in zip(scr, exp))
                        fails.append(f"{name} blit fid {fid} var {v}{' MIR' if mir else ''} fpy {fpy} bg "
                                     f"{bg:02x}: {nd} screen bytes differ")
    bstats.append((name, n_bl, n_bad))
    print(f"[{'PASS' if not n_bad else 'FAIL'}] {name} real blits facing left: {n_bl} ({n_mir} mirrored), "
          f"{n_bad} mismatches")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-proto", action="store_true")
    ap.add_argument("--depths", type=int, default=8)
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="mirror_equiv_")
    sna, S, _ = zp.build(zp.REPO, ["DEBUG_KIT=0"], tmp)
    global RAW
    RAW = raw_frames(S)
    stats, fails, bstats = [], [], []
    h = Harness()
    h.launch(zp.EMU_ARGS)
    try:
        h.z.sock.settimeout(60)
        r = zp.Run(h, sna, S)
        r.load()
        r.run_to("select_tick")
        check_point("boot", r.dump(), S, stats, fails)
        for hero, key, pre in ((0, "1", ""), (1, "2", "M-")):
            lv, _ = zp.levels_run(r, a.depths, key, pre)
            for dd in range(1, a.depths + 1):
                check_point(f"{HERO[hero]} D{dd}", lv[f"{pre}D{dd}"], S, stats, fails)
            blit_point(f"{HERO[hero]} D{a.depths}", r, S, bstats, fails)
        if not a.no_proto:
            for hero, key in ((0, "1"), (1, "2")):
                for kinds, ps in ((5, 1), (6, 3)):
                    r.load()
                    r.wb("proto_start", ps)
                    r.run_to("select_tick")
                    r.select_hero(key, proto=True)
                    check_point(f"{HERO[hero]} PROTO {kinds} kinds", r.dump(), S, stats, fails)
                    blit_point(f"{HERO[hero]} PROTO {kinds} kinds", r, S, bstats, fails)
    finally:
        h.close()
        shutil.rmtree(tmp, ignore_errors=True)
    tf, tc, tb = (sum(s[i] for s in stats) for i in (1, 2, 3))
    for f in fails[:40]:
        print("  " + f)
    nb, bb = sum(b[1] for b in bstats), sum(b[2] for b in bstats)
    print(f"mirror_equiv: {'OK' if not fails else 'FAIL'}: {len(stats)} pools, {tf} fid-instances, "
          f"{tc} variant pairs, {tb} mismatches; {nb} real left blits, {bb} mismatches")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
