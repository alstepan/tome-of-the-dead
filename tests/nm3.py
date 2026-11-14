#!/usr/bin/env python3
"""NEW-MON3 T9: the A-1 alias patch (row 31 = Fire Imp on D4 / D6, Frost Wraith on D5 / D7 / D8) and the
new_monsters.md §5 per-depth kind lists, on the real game (DEBUG_KIT=0 build, F3_GEN), both heroes.

  L  per depth D1..D8 (the real level_descend): LP_KINDS / LP_BOSS == lp_dtab == levelgen.LP_TAB; every
     record / live body of the level is a listed kind (or its tier) / the boss; a K_ALIAS body / record
     has the variant's depth-scaled hp (levelgen.k3_hp); NM3_VAR = the depth's variant.
  A  the patch: kind_tab (bank 2) / rk_tab, kx_tab row 31 (bank 3), gu_tab row 31 + drop_imp (R6) == the
     nm3_var groups' A or B column (read from the .sna's bank-0 table); the generated frames are the
     variant's (FRT rows of KFID_WRAITH vs KFID_IMP: one generated, the other NONE); the cached sequence
     row of K_ALIAS (KT_SEQ) = the variant's master block (build/ovl/seq.bin: ksm_ia / ksm_wr); the name
     (tx_dec TX_NM_FIRE_IMP) = FIRE IMP / the Wraith's; B0_CODE2 / text untouched (== .sna).
     Order D1..D8 then D4 again: Imp -> Wraith -> Imp -> Wraith -> Imp both ways.
  N  a new game after dying on a Wraith depth (D7): D1 is variant A again (tables / name), and its D4 too.
  S  the alias appears in the records of its depths (some seed of a few).
Run: ZRCP_PORT=<port> python3 tests/nm3.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import levelgen as G                                    # noqa: E402
import game_lib as GL                                   # noqa: E402
from game_lib import Harness, S, EMU_ARGS, F3           # noqa: E402
from lp import T as Proto, w16                          # noqa: E402
import gfx_integrity as GI                              # noqa: E402

FAILS = []
NCHK = [0]


def check(name, ok, got=None):
    NCHK[0] += 1
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok or got is None else f": got {got}"), flush=True)
    if not ok:
        FAILS.append(name)


KA = S["K_ALIAS"]
GS_PLAYING, GS_DEAD = S["GS_PLAYING"], S["GS_DEAD"]
SEQ = open(os.path.join(os.path.dirname(GL.SYM), "ovl", "seq.bin"), "rb").read()


def sna0(addr, n):
    return GI.sna_bank(0, addr, n)


def group(name, end):
    """nm3_var group -> [(addr, A, B)] (bank-0 table in the .sna)."""
    raw = sna0(S[name], S[end] - S[name])
    out = []
    for i in range(0, len(raw), 4):
        a = raw[i] | raw[i + 1] << 8
        if a == 0:
            break
        out.append((a, raw[i + 2], raw[i + 3]))
    return out


G_B2 = group("nm3_var_b2", "nm3_var_b3")
G_B3 = group("nm3_var_b3", "nm3_var_r6")
G_R6 = group("nm3_var_r6", "nm3_var_img")
check("A0 table: 9 bank-2 / 8 kx / 3 R6 entries, A != B somewhere in each",
      (len(G_B2), len(G_B3), len(G_R6)) == (9, 8, 3)
      and all(any(a != b for _, a, b in g) for g in (G_B2, G_B3, G_R6)), (len(G_B2), len(G_B3), len(G_R6)))
B0_LO, B0_HI = S["b0c2_code"], S["b0c2_end"]
B0_SNA = sna0(B0_LO, B0_HI - B0_LO)
TX_LO = S["TEXT_ADDR"]
TX_SNA = sna0(TX_LO, B0_LO - TX_LO)


def block_of(ksm):
    o = ksm - S["SQ_IMG"]
    n, imp, offs = SEQ[o], SEQ[o + 1], list(SEQ[o + 2:o + 10])
    return n, imp, offs, SEQ[o + 10:o + 10 + n]


BLK = {0: block_of(S["ksm_ia"]), 1: block_of(S["ksm_wr"])}
NAME = {0: "FIRE IMP"}


def ingame(p, code):
    pc0 = p.pc()
    ok, _ = p.code(code, game=True)
    p.z.cmd("set-register PC=%d" % pc0)
    return ok


def descend_to(p, d):
    """The real level_descend from depth d - 1 (d = 1: a new D1 of the same game). MUS_CUR := 0 first: the
    previous level's stinger may still be playing, and stinger_wait (menu_frame) would wait on the DI'd ISR."""
    p.wb("MUS_CUR", 0)
    ok = ingame(p, [0x3E, d - 1, 0x32] + w16(S["LVL_DEPTH"]) + [0xCD] + w16(S["level_descend"]))
    p.release()
    p.settle(4)
    return ok and p.rb("LVL_DEPTH") == d and p.rb("GAME_STATE") == GS_PLAYING


def name31(p):
    ingame(p, [0x3E, S["TX_NM_FIRE_IMP"], 0xCD] + w16(S["tx_dec"]))
    raw = bytes(p.z.read_memory(S["TX_DEC"], S["TX_DEC_LEN"]))
    return raw.split(b"\0")[0].decode("latin-1")


def frt_generated(p, fid):
    row = bytes(p.z.read_memory(S["FRT"] + fid * S["FRT_STRIDE"], S["FT_IN_ROW"]))
    return any(b != S["FRT_NONE"] for b in row[0::3])


def seq_row_ok(p, v):
    lo = p.rb(S["kind_tab"] + S["KT_SEQ"] + KA)
    row = bytes(p.z.read_memory((S["seq_rows"] & 0xFF00) | lo, S["KS_STRIDE"]))
    ptr = [row[2 * i] | row[2 * i + 1] << 8 for i in range(8)]
    n, imp, offs, body = BLK[v]
    base = ptr[0] - offs[0]
    got = bytes(p.z.read_memory(base, n))
    return row[S["KS_IMPACT"]] == imp and all(ptr[i] - base == offs[i] for i in range(8)) and got == body


def check_variant(p, d, tag):
    v = G.nm3_variant(d)
    check(f"{tag} D{d}: NM3_VAR = {v}", p.rb("NM3_VAR") == v, p.rb("NM3_VAR"))
    bad = [(hex(a), p.rb(a), (a_, b_)) for a, a_, b_ in G_B2 if p.rb(a) != (b_ if v else a_)]
    check(f"{tag} D{d}: kind_tab / rk_tab row 31 = variant {'AB'[v]}", not bad, bad)
    k3 = GI.bank_read(p, 3, G_B3[0][0], len(G_B3))
    check(f"{tag} D{d}: kx_tab row 31 (bank 3) = variant {'AB'[v]}",
          list(k3) == [b_ if v else a_ for _, a_, b_ in G_B3], k3.hex())
    r6 = [GI.bank_read(p, 6, a, 1)[0] for a, _, _ in G_R6]
    check(f"{tag} D{d}: gu_tab row 31 + drop_imp kind (R6) = variant {'AB'[v]}",
          r6 == [b_ if v else a_ for _, a_, b_ in G_R6], r6)
    listed = KA in [p.rb(S["LP_KINDS"] + i) for i in range(8)]
    if listed:
        fw, fi = frt_generated(p, S["KFID_WRAITH"]), frt_generated(p, S["KFID_IMP"])
        check(f"{tag} D{d}: frames generated = the variant's (Wraith {fw}, Imp {fi})", (fw, fi) == (bool(v), not v))
        check(f"{tag} D{d}: K_ALIAS seq row = {'ksm_wr' if v else 'ksm_ia'}", seq_row_ok(p, v))
    nm = name31(p)
    if v and 1 not in NAME:
        NAME[1] = nm
    check(f"{tag} D{d}: name of kind 31 = {NAME.get(v, '(the Wraith name)')!r}",
          nm == NAME.get(v, nm) and (nm != NAME[0]) == bool(v), nm)
    b0 = GI.bank_read(p, 0, B0_LO, B0_HI - B0_LO)
    tx = GI.bank_read(p, 0, TX_LO, B0_LO - TX_LO)
    check(f"{tag} D{d}: B0_CODE2 + text == .sna (no runtime write)", b0 == B0_SNA and tx == TX_SNA)


def level_kinds(p, d, tag, seen):
    want = [G.KROWS[k][0] for k in G.LP_TAB[d][0]]
    got = [p.rb(S["LP_KINDS"] + i) for i in range(8)]
    check(f"{tag} D{d}: LP_KINDS = the §5 list", got == want, got)
    allowed = set(want)
    for k in list(allowed):
        allowed |= {G.KROWS[t][0] for t in G.TIERS.get(G.K3_BY_ID[k], []) if t}
    boss = p.rb(S["LP_BOSS"]) & S["LEK_KIND_MASK"]
    allowed.add(boss)
    units = []
    for r in range(9):
        o = S["LP_REC"] + r * S["LR_STRIDE"]
        hdr = p.rb(o)
        n = hdr & S["LR_CNT_MASK"] if hdr & S["LR_VISITED"] else 0     # unvisited: a quota, no entries yet
        units += [(p.rb(o + 1 + 2 * i) & S["LEK_KIND_MASK"], p.rb(o + 1 + 2 * i) & ~S["LEK_KIND_MASK"] & 255,
                   p.rb(o + 2 + 2 * i), "rec") for i in range(n)]
    for s_ in range(1, 16):
        e = p.ent(s_)
        if e["FLAGS"] & 1:
            units.append((e["KIND"], 0, e["HP"], "ent"))
    bad = [u for u in units if u[0] not in allowed]
    check(f"{tag} D{d}: every record / body is a listed kind, tier or the boss ({len(units)} units)", not bad, bad)
    # every other present room's first entry through the real lp_enter (far3: lp_gen + spawn_one): the bodies
    blk = bytes(p.z.read_memory(G.BASE, G.BLOCK_LEN))
    st = blk[S["LVL_START"] - G.BASE]
    for r in range(9):
        o = S["LP_REC"] + r * S["LR_STRIDE"]
        if r == st or p.rb(o) & S["LR_VISITED"] or not GI.room_model.field(blk, r, "RD_FLAGS") & S["RDF_PRESENT"]:
            continue
        p.clear_slots()
        p.wmem(S["LP_HX"], [1, 0, 3])
        ingame(p, [0x3E, r, 0x21] + w16(S["lp_enter"]) + [0xCD] + w16(S["far3"]))
        for s_ in range(1, 16):
            e = p.ent(s_)
            if e["FLAGS"] & 1:
                units.append((e["KIND"], 0, e["HP"], f"room {r} body"))
    p.clear_slots()
    bad = [u for u in units if u[0] not in allowed]
    check(f"{tag} D{d}: every room's spawn is a listed kind, tier or the boss ({len(units)} units)", not bad, bad)
    for k, fl, hp, src in units:
        seen.setdefault(d, set()).add(k)
        if k == KA:
            check(f"{tag} D{d}: K_ALIAS {src} hp {hp} = {'Wraith' if G.nm3_variant(d) else 'Imp'} depth-scaled",
                  hp == G.k3_hp(k | (fl & 0x80), d), hp)


def run_game(p, hero, master, tag, seen):
    p.proto_start = 0
    p.boot(hero=hero, freeze=1)
    p.wmem(S["MASTER_SEED"], w16(master))
    for d in list(range(1, 9)) + [4, 5]:
        ok = descend_to(p, d)
        check(f"{tag}: level_descend -> D{d}", ok, (p.rb("LVL_DEPTH"), p.rb("GAME_STATE")))
        if not ok:
            return
        level_kinds(p, d, tag, seen)
        check_variant(p, d, tag)


def new_game_after_wraith(p, hero, tag):
    p.proto_start = 0
    p.boot(hero=hero, freeze=1)
    check(f"{tag}: to D7", descend_to(p, 7))
    check_variant(p, 7, tag)
    p.wb("GAME_STATE", GS_DEAD)                       # die on the Wraith depth -> end card -> menu -> START
    p.end_to_menu("ENTER")
    p.tick(3)
    p.hold("1")
    p.wait_state(GS_PLAYING)
    p.release()
    p.settle(3)
    check(f"{tag}: new game on D1", p.rb("LVL_DEPTH") == 1, p.rb("LVL_DEPTH"))
    check_variant(p, 1, tag + " new game")
    check(f"{tag} new game: to D4", descend_to(p, 4))
    check_variant(p, 4, tag + " new game")


def main():
    if not F3:
        print("[skip] nm3 needs the F3_GEN build", flush=True)
        return 0
    seen = {}
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = Proto(h)
        for hero, master in ((0, 0x4D31), (1, 0x4D47)):
            run_game(p, hero, master, "WM"[hero], seen)
        for m in (0x1234, 0x2345, 0x3456):
            if all(KA in seen.get(d, ()) for d in (4, 5, 6, 7, 8)):
                break
            run_game(p, 0, m, f"S{m:#06x}", seen)
        for d in (4, 5, 6, 7, 8):
            check(f"S D{d}: the alias spawns (records / bodies over the seeds)", KA in seen.get(d, ()))
        for d in (1, 2, 3):
            check(f"S D{d}: no alias / Gargoyle", not ({KA, S["K_GARGOYLE"]} & seen.get(d, set())))
        new_game_after_wraith(p, 0, "N W")
        new_game_after_wraith(p, 1, "N M")
    print(f"nm3: {NCHK[0]} checks, {len(FAILS)} failed" + (f": {FAILS[:8]}" if FAILS else ""), flush=True)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
