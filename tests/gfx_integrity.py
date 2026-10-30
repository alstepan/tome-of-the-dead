#!/usr/bin/env python3
"""GI: graphics-data integrity (fix/3d-artefacts, user report 2026-10-06:
stray lines in ladders / door arch / potion / bricks / around the hero).

Every runtime graphics table is compared byte-for-byte with its assembled
source (read from the .sna the suite loads, never from the running machine):

  GI0  at the menu (after boot): TILE_GLYPHS ids 0..31 == tiles_common_glyphs,
       TILE_ATTRS 0..31 == tiles_common_attrs, ORN_GLYPHS == orn_glyphs,
       FONT6 planes == font6x8 re-laid (bits 1..0 masked, holes skipped)
       (3E-T1: those four sources from the .sna's boot block, bank 6 tail),
       bank-1 vdata, the bank-1 menu art (menu_font .. menu_torch_end),
       bank-7 tileset slots 0..7, the bank-7 cold code B7_CODE..B7_LIMIT (D3-S2:
       the old bitmap shadow; canary — no SMC / data writes there), bank-0
       text block — all == the .sna
  GI1  generated new game (seed_fixed) and every depth D1..D8 entered through
       the real level_descend (in-game stub), each followed by play (walk
       left / right through the rooms: room changes + LP spawns):
       the GI0 tables again (TILE_ATTRS minus the theme_ids, which follow the
       depth), ids 32..63 glyphs / attrs / tile_flags == the bank-7 slot,
       the sprite pool (bank 0 POOL_START.., banks 4 / 6) + FRT (3F-T1, the
       per-level pool): the part below the LEVEL mark (idles + hero + its class
       FX) and the non-monster FRT rows == as built at the hero start (D3-4:
       the FX kind checked generated — one variant per facing for each fid of
       its range — once); at each depth every frame of the level's generation
       kinds (LP_KINDS + LP_BOSS through pool_gmap) has a variant per facing,
       every other monster frame's FRT row is NONE, and after play the whole
       pool + FRT == as built at that depth's entry; and the displayed playfield == ROOM_MAP drawn from the
       SOURCE glyphs (every cell not under a sprite; row 17 may hold an
       ornament glyph) + (IC1) the panel's quick potion icon == a source 16x16 potion icon.
Run with ZRCP_PORT=<port>.  `--depths N` (default 8).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import game_lib as GL                                   # noqa: E402
from game_lib import Harness, S, EMU_ARGS, cell_bytes   # noqa: E402
from lp import T, w16                                   # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import items_model as IM                                # noqa: E402
import room_model                                       # noqa: E402

BANK = 16384


def sna_bank(b, addr, n):
    """Bytes of bank b at $C000-window address addr (the loaded .sna)."""
    o = b * BANK + (addr - 0xC000)
    return GL.SNA_RAM[o:o + n]


def sna_virt(v, n):
    """Virtual sprite-source / vdata address (copy_virt): $4000..$7FFF = bank 6
    (SRC6 blocks, real = virt + SRC6_VDELTA), $8000.. = bank 1, $C000.. = bank 3."""
    assert v >= 0x4000, hex(v)
    if v < 0x8000:
        return sna_bank(6, v + S["SRC6_VDELTA"], n)
    return sna_bank(1, v + 0x4000, n) if v < 0xC000 else sna_bank(3, v, n)


# self-check: the SRC6 window maps to bank 6 at the real address, not bank 1
assert sna_virt(S["SRC6_ADDR"] - S["SRC6_VDELTA"], 16) == sna_bank(6, S["SRC6_ADDR"], 16)
assert S["SRC6_VDELTA"] == 0x8000


def sna_boot(addr, n):
    """3E-T1: the boot-only data sits in the boot block (bank 6 tail,
    BOOT6_ADDR..SRC6_ADDR) — read from the .sna, the pool overwrites it later."""
    assert S["BOOT6_ADDR"] <= addr and addr + n <= S["SRC6_ADDR"], hex(addr)
    return sna_bank(S["BANK_BOOT6"], addr, n)


TC = S["TILE_COMMON"]
TILE_IDS = 64
SRC_GLY = sna_boot(S["tiles_common_glyphs"], TC * 8)
SRC_ATT = sna_boot(S["tiles_common_attrs"], TC)
SRC_ORN = sna_boot(S["orn_glyphs"], S["ORN_COUNT"] * 8)
SRC_FONT = sna_boot(S["font6x8"], 96 * 8)


def bank_read(p, b, addr, n):
    """n bytes of bank b at its $C000-window address addr (memory zone 0 =
    the 128K RAM, banks 0-7; nothing is paged)."""
    p.z.cmd("set-memory-zone 0")
    try:
        return bytes(p.z.read_memory(b * BANK + (addr - 0xC000), n))
    finally:
        p.z.cmd("set-memory-zone -1")


def font_planes():
    """FONT6 (memory-map: line l of char c at FONT6 + (l>>1)*256 + c +
    (l&1)*FONT6_WB) from font6x8, bits 1..0 masked -> {addr: byte}."""
    want = {}
    for c in range(32, 128):
        for l_ in range(8):
            a = S["FONT6"] + (l_ >> 1) * 256 + c + (l_ & 1) * S["FONT6_WB"]
            want[a] = SRC_FONT[(c - 32) * 8 + l_] & 0xFC
    return want


FONT_WANT = font_planes()


def diff_ranges(got, want, base):
    bad, run = [], None
    for i, (g, w) in enumerate(zip(got, want)):
        if g != w:
            if run and i == run[1] + 1:
                run[1] = i
            else:
                run = [i, i]
                bad.append(run)
    return [f"{base + a:#06x}..{base + b:#06x}" for a, b in bad]


def tables(p, check, tag, depth):
    """The source-vs-runtime table checks (depth 0 = at the menu)."""
    TG, TA = S["TILE_GLYPHS"], S["TILE_ATTRS"]
    g = bytes(p.z.read_memory(TG, TILE_IDS * 8))
    a = bytes(p.z.read_memory(TA, TILE_IDS))
    bad = diff_ranges(g[:TC * 8], SRC_GLY, TG)
    check(f"GI {tag}: TILE_GLYPHS ids 0..31 == tiles_common_glyphs", bad == [],
          (bad[:6], sorted({(int(r[:6], 16) - TG) // 8 for r in bad})))
    lists, t = [], S["theme_ids"]          # floor ids, 0, wall ids, 0 (level_load_tiles .patch; FLOOR1:
    for _ in range(2):                     # no item-glyph list: the markers 60..63 keep the slot attrs)
        ids = []
        while (v := p.rb(t)) != 0:
            ids.append(v)
            t += 1
        t += 1
        lists.append(ids)
    theme = set(lists[0]) | set(lists[1])
    ab = [i for i in range(TC) if (depth == 0 or i not in theme) and a[i] != SRC_ATT[i]]
    check(f"GI {tag}: TILE_ATTRS ids 0..31 == tiles_common_attrs (theme / item ids aside)", ab == [], ab)
    if depth:
        th = ([i for i in lists[0] if a[i] != p.rb("LVL_ATTR_FLOOR")]
              + [i for i in lists[1] if a[i] != p.rb("LVL_ATTR_WALL")])
        check(f"GI {tag}: theme ids carry LVL_ATTR_FLOOR / WALL", th == [], (lists, th))
        slot = depth - 1
        src = GL.tset_slot(lambda a_, n_: sna_bank(7, a_, n_), slot)   # MEM-RECLAIM w2a: dedup records
        n = (TILE_IDS - TC)
        tf = bytes(p.z.read_memory(S["tile_flags"] + TC, n))
        bad = (diff_ranges(g[TC * 8:], src[:n * 8], TG + TC * 8)
               + diff_ranges(a[TC:], src[n * 8:n * 9], TA + TC)
               + diff_ranges(tf, src[n * 9:n * 10], S["tile_flags"] + TC))
        check(f"GI {tag}: ids 32..63 glyphs / attrs / tile_flags == bank-7 slot {slot}", bad == [], bad[:6])
    o = bytes(p.z.read_memory(S["ORN_GLYPHS"], len(SRC_ORN)))
    bad = diff_ranges(o, SRC_ORN, S["ORN_GLYPHS"])
    check(f"GI {tag}: ORN_GLYPHS == orn_glyphs", bad == [], bad)
    f = bytes(p.z.read_memory(S["FONT6"], 4 * 256))
    bad = [hex(ad) for ad, w in FONT_WANT.items() if f[ad - S["FONT6"]] != w]
    check(f"GI {tag}: FONT6 planes == font6x8 (bits 1..0 masked)", bad == [], bad[:8])
    # banked read-only data == the .sna
    for (b, lo, hi, name) in (
            (1, S["vdata"] + 0x4000, S["vdata_end"] + 0x4000, "bank-1 vdata (panel / status icons; 3E-T1: the boot-only part is in the boot block)"),
            (1, S["menu_font"], S["menu_torch_end"], "bank-1 menu art (font, title, torch)"),
            (7, S["tilesets"], S["data7_end"], "bank-7 tilesets (w2a: dedup) + data7 (w2b: bank-7 code tables)"),
            (7, S["B7_CODE"], S["B7_LIMIT"], "bank-7 cold code + unused tail (D3-S2: the "
             "freed bitmap shadow, w2a + the old tileset slots 0..3, is never written)"),
            (0, S["text_img"], S["text_img_end"], "bank-0 text block")):
        got = bank_read(p, b, lo, hi - lo)
        bad = diff_ranges(got, sna_bank(b, lo, hi - lo), lo)
        check(f"GI {tag}: {name} == .sna", bad == [], bad[:6])


POOL = ((0, S["POOL_START"], 0x10000), (4, 0xC000, 0x10000), (6, 0xC000, 0x10000))


def pool_snap(p):
    snap = {b: bank_read(p, b, lo, hi - lo) for b, lo, hi in POOL}
    snap["FRT"] = bytes(p.z.read_memory(S["FRT"], S["FRT_MAX"] * S["FRT_STRIDE"]))
    return snap


def pool_check(p, check, tag, snap0, snapd=None):
    """3F-T1: snap0 = at the hero start (D1 entry), snapd = at this depth's
    entry (None: this IS the entry — check the level part, return the snap)."""
    now = pool_snap(p)
    st, f0, fn = S["FRT_STRIDE"], S["KFID_MONSTERS"], S["KFCNT_MONSTERS"]
    if snapd is not None:                      # after play: nothing regenerated
        for k in snapd:
            lo = S["FRT"] if k == "FRT" else dict((b, l) for b, l, _ in POOL)[k]
            bad = diff_ranges(now[k], snapd[k], lo)
            check(f"GI {tag}: sprite pool {'FRT' if k == 'FRT' else f'bank {k}'} == as built at the depth's entry",
                  bad == [], bad[:6])
        return snapd
    # below the level mark (ALLOC_MARK, start_game): idles + hero + class FX
    mi = p.rb("ALLOC_MARK_IDX")
    mp = p.z.read_memory(S["ALLOC_MARK_PTR"], 2)
    mp = mp[0] | mp[1] << 8
    for b, lo, hi in POOL:
        i = (0, 4, 6).index(b)
        end = hi if i < mi else (mp if i == mi else lo)
        bad = diff_ranges(now[b][:end - lo], snap0[b][:end - lo], lo)
        check(f"GI {tag}: pool bank {b} below the level mark ({mi}, {mp:#06x}) == as built at hero start",
              bad == [], bad[:6])
    keep = list(range(0, f0 * st)) + list(range((f0 + fn) * st, len(now["FRT"])))
    bad = [hex(S["FRT"] + i) for i in keep if now["FRT"][i] != snap0["FRT"][i]]
    check(f"GI {tag}: FRT rows outside the monster fids == as built at hero start", bad == [], bad[:6])
    # the level's generation kinds (pool_list's rule) generated, the rest NONE
    gu = bank_read(p, S["BANK_R6"], S["gu_tab"], 2 * S["GU_N"])     # 3F-T2: the generation units
    kt = lambda col, k: gu[2 * k + (col == "KT_FCNT")]                # (was kind_tab KT_FID0 / KT_FCNT)
    gm = bank_read(p, S["BANK_R6"], S["pool_gmap"], 3 * S["PGMAP_N"])
    kinds = []
    for k in lp_kinds(p):
        # 3F-T13: every pool_gmap record of the kind applies (no record: its own unit)
        us = [u for r in range(S["PGMAP_N"]) if gm[3 * r] == k
              for u in gm[3 * r + 1:3 * r + 3] if u != 0xFF] or [k]
        kinds += [u for u in us if u not in kinds]
    fids = {f for k in kinds for f in range(kt("KT_FID0", k), kt("KT_FID0", k) + kt("KT_FCNT", k))}
    bad = []
    for f in range(f0, f0 + fn):
        row = now["FRT"][f * st:(f + 1) * st]
        if f in fids:
            for side in (0, 2):
                vs = [v for v in (side, side + 1) if row[3 * v] != S["FRT_NONE"]]
                if not vs or any(row[3 * v] not in (0, 4, 6) for v in vs):   # MOT: 2 shifts
                    bad.append((f, side))
        elif any(row[3 * v] != S["FRT_NONE"] for v in range(4)):
            bad.append((f, "not NONE"))
    check(f"GI {tag}: level kinds {kinds} generated ({len(fids)} frames), other monster frames NONE",
          bad == [] and p.rb("GEN_OVERFLOW") == 0 and p.rb("GEN_TRAP") == 0, bad[:6])
    return now


def fx_check(p, check):
    """D3-4: the hero's class FX kind (K_FX_BASE + HERO_KIND) is resident at the
    hero start: every fid of its gu_tab unit range has a right (v0/v1) and a
    left (v2/v3) variant in a pool bank whose bytes lie inside the pool."""
    hk = p.rb("HERO_KIND")
    k = S["K_FX_BASE"] + hk
    f0, fc = bank_read(p, S["BANK_R6"], S["gu_tab"] + 2 * k, 2)     # 3F-T2: R6 gu_tab
    want = ("KFID_FXW", "KFCNT_FXW") if hk == S["K_KNIGHT"] else ("KFID_FXM", "KFCNT_FXM")
    check(f"GI FX: kind {k} range == {want[0]}", (f0, fc) == (S[want[0]], S[want[1]]), (f0, fc))
    frt = bytes(p.z.read_memory(S["FRT"] + f0 * S["FRT_STRIDE"], fc * S["FRT_STRIDE"]))
    bad = []
    for i in range(fc):
        row = frt[i * S["FRT_STRIDE"]:(i + 1) * S["FRT_STRIDE"]]
        for side in (0, 2):
            vs = [row[3 * v:3 * v + 3] for v in (side, side + 1) if row[3 * v] != S["FRT_NONE"]]
            if len(vs) != 1 or vs[0][0] not in (0, 4, 6) or (vs[0][1] | vs[0][2] << 8) < 0xC000:
                bad.append((f0 + i, side))
    check(f"GI FX: hero {hk} class FX frames ({fc}) generated, one variant per facing", bad == [], bad[:6])


def screen_check(p, check, tag, depth):
    """Displayed playfield == ROOM_MAP drawn with the SOURCE glyphs."""
    fr = p.frame()
    m = bytes(p.z.read_memory(S["ROOM_MAP"], 32 * S["PLAY_ROWS"]))
    slot = depth - 1
    gly = SRC_GLY + GL.tset_slot(lambda a_, n_: sna_bank(7, a_, n_), slot)[:(TILE_IDS - TC) * 8]
    lvl = {gly[i:i + 8] for i in range(TC * 8, TILE_IDS * 8, 8)}
    orn = {SRC_ORN[i:i + 8] for i in range(0, len(SRC_ORN), 8)}
    covered = set()
    drip = GL.drip_cells(p)                        # D3-8b: screen-only overlay
    for s_ in range(16):
        e = p.ent(s_)
        if e["DVIS"] & 1:
            covered |= {(c, r) for c in range(e["DCOL"], e["DCOL"] + e["DCOLS"])
                        for r in range(e["DROW"], e["DROW"] + e["DROWS"])}
    items = room_model.floor_cells(p.z.read_memory(S["FLOOR_LIST"], 128), p.rb("CUR_ROOM"))
    bad, n, ni = [], 0, 0
    for i, t in enumerate(m):
        c, r = i % 32, i // 32
        if (c, r) in covered:
            continue
        n += 1
        cb = cell_bytes(fr, c, r)
        if t >= S["T_ITEM0"]:                      # FLOOR1: a marker shows its icon quarter + ink
            ni += 1
            g, a = items.get((c, r), (None, None))
            if cb != g or GL.attr_at(fr, c, r) != a:
                bad.append((c, r, t, "item"))
            continue
        if cb == gly[t * 8:t * 8 + 8] or (r == 17 and cb in orn):
            continue
        # decor glyph swap (decor_tick): a level id may show its partner frame
        if not (t >= TC and cb in lvl) and not GL.drip_shown(fr, drip, c, r):
            bad.append((c, r, t))
    check(f"GI {tag}: playfield ({n} uncovered cells, {ni} item cells) == ROOM_MAP in source glyphs, "
          f"items as their 16x16 icons", n > 300 and bad == [], bad[:6])
    # IC1: the quick POTION slot shows a 16x16 potion icon (Heal / Mana / Cure, the pick) ==
    # its source (assets/gfx/icons/icons16.asm), not the 8x8 T_POTION glyph any more
    col = 18 + 3 * p.rb("HERO_KIND")
    pots = [GL.icon16_cells(S[n] - S["IT_BAG_LO"]) for n in ("IT_P_HEAL", "IT_P_MANA", "IT_P_CURE")]
    check(f"GI {tag}: panel quick potion icon (cols {col}-{col + 1}, rows 18-19) == a source 16x16 potion icon",
          any(all(cell_bytes(fr, col + dc, 18 + dr) == b for (dc, dr), b in ic.items()) for ic in pots), "")


def floor_check(p, check, tag, room=None, m=None):
    """FLOOR1: the 2x2 marker invariant floor_pickup's pre-filter, erase_rect and
    drop_put rely on (level_defs.asm T_ITEM0): every live FLOOR_LIST entry of the
    room has T_ITEM0 + 2s on cols c..c+1 of row 9s+6 and T_ITEM0 + 2s + 1 on row
    9s+7, and no other cell of the map holds a marker. Default: CUR_ROOM in the
    live ROOM_MAP; else room `room` built into `m`."""
    fl = p.z.read_memory(S["FLOOR_LIST"], S["FLOOR_MAX"] * S["FL_STRIDE"])
    if m is None:
        m = bytes(p.z.read_memory(S["ROOM_MAP"], 32 * S["PLAY_ROWS"]))
        room = p.rb("CUR_ROOM")
    want = {}
    for i in range(S["FLOOR_MAX"]):
        r, col = fl[i * 4], fl[i * 4 + 1]
        if r == S["FL_EMPTY"] or (r & S["FL_ROOM_MASK"]) != room:
            continue
        sto = 1 if r & S["FL_S1"] else 0
        for k in (0, 1):
            for h in (0, 1):
                want[(col + h, 9 * sto + 6 + k)] = S["T_ITEM0"] + 2 * sto + k
    bad = [(c, r, m[r * 32 + c], t) for (c, r), t in want.items() if m[r * 32 + c] != t]
    stray = [(i % 32, i // 32, t) for i, t in enumerate(m) if t >= S["T_ITEM0"] and (i % 32, i // 32) not in want]
    check(f"GI {tag}: FLOOR_LIST live entries ({len(want) // 4}) all show their 2x2 markers in ROOM_MAP, "
          f"no stray marker", bad == [] and stray == [], (bad[:4], stray[:4]))
    return len(want) // 4


SCROLL_PCS = (S["hscroll_room.step"], S["vscroll_room.step"])


def forced_exit(p, stats):
    """3E-T6 R3, deterministic: from CUR_ROOM take the first exit (L, R, U, D)
    whose destination holds floor items through the real do_exit (far7, in
    play), stopping at every scroll step (breakpoints 5 / 6) for scroll_ink
    (the displayed bank-5 screen: every entering-room item cell already
    scrolled in carries its type's ink; inside a step the item glyph ids'
    TILE_ATTRS are 0: blank, never a wrong ink)."""
    r = p.rb("CUR_ROOM")
    d0 = S["ROOM_DESC"] + 16 * r
    ex = p.rb(d0 + S["RD_EXITS"])
    fl = p.z.read_memory(S["FLOOR_LIST"], 128)
    rooms = {fl[4 * i] & 15 for i in range(32) if fl[4 * i] != S["FL_EMPTY"]}
    for bit, kind, dd, colk in ((S["RDX_L"], S["EX_LEFT"], -1, None), (S["RDX_R"], S["EX_RIGHT"], 1, None),
                                (S["RDX_U"], S["EX_UP"], -3, "RD_UPCOL"), (S["RDX_D"], S["EX_DOWN"], 3, "RD_DNCOL")):
        if ex & bit and r + dd in rooms:
            break
    else:
        return False
    p.wb("EXIT_KIND", kind)
    p.wb("EXIT_DEST", r + dd)
    if colk:
        p.wb("EXIT_COL", p.rb(d0 + S[colk]))
    for n, pc in zip((5, 6), SCROLL_PCS):
        p.z.cmd("set-breakpoint %d PC=%d" % (n, pc))
    pc0 = p.pc()
    code = [0xF3, 0x3E, kind, 0x21] + w16(S["do_exit"]) + [0xCD] + w16(S["far7"]) + [0xFB, 0x00, 0x18, 0xFE]
    stub = S["LOWRAM_END_3B"]
    end = stub + len(code) - 3
    p.wmem(stub, code)
    p.z.cmd("set-breakpoint 3 PC=%d" % end)
    p.z.cmd("set-register PC=%d" % stub)
    for _ in range(200):
        p.z.cmd("run 50000000")
        pc = p.pc()
        if pc == end:
            break
        if pc in SCROLL_PCS:
            scroll_ink(p, stats)
            p.z.cmd("cpu-step")
    ok = p.pc() == end
    p.z.cmd("set-breakpoint 3")
    for n in (5, 6):
        p.z.cmd("set-breakpoint %d" % n)
    p.z.cmd("set-register PC=%d" % pc0)
    return ok and p.rb("CUR_ROOM") == r + dd


def scroll_ink(p, stats):
    """FLOOR1: at a scroll step, every entering-room item cell already scrolled in
    shows its icon quarter + ink (room_model.floor_cells of EXIT_DEST, shifted)."""
    k, kind, dest = p.rb("TMP5"), p.rb("TMP4"), p.rb("EXIT_DEST")
    fl = p.z.read_memory(S["FLOOR_LIST"], 128)
    fr = bytes(p.z.read_memory(S["SCREEN_BITMAP"], 6144)) + bytes(p.z.read_memory(S["SCREEN_ATTR"], 768))
    dc = dr = 0
    if kind == S["EX_RIGHT"]:
        dc = 32 - 2 * k
    elif kind == S["EX_LEFT"]:
        dc = 2 * k - 32
    elif kind == S["EX_DOWN"]:
        dr = S["PLAY_ROWS"] - k
    else:
        dr = k - S["PLAY_ROWS"]
    stats["steps"] += 1
    for (c, r), (g, a) in room_model.floor_cells(fl, dest).items():
        row, col = r + dr, c + dc
        if 0 <= row < S["PLAY_ROWS"] and 0 <= col < 32:
            stats["cells"] += 1
            if cell_bytes(fr, col, row) != g or GL.attr_at(fr, col, row) != a:
                stats["bad"].append((kind, k, dest, c, r, row, col))


SEQ_BIN = Path(__file__).resolve().parent.parent / "build" / "ovl" / "seq.bin"


def lp_kinds(p):
    """LP_KINDS[0..3] + LP_BOSS as kind rows (3F-T5: LP_BOSS carries LEK_GOLD on the golden depths)."""
    return [k & S["LEK_KIND_MASK"] for k in p.z.read_memory(S["LP_KINDS"], 5)]


def seq_check(p, check, tag, kinds):
    """3F-T2 review: the hero and every kind in `kinds` has a sequence cache
    row (seq_rows page | kind_tab KT_SEQ) and the row's 8 sequences (from the
    row pointer to the block's end) + KS_IMPACT equal the master block in
    build/ovl/seq.bin (the raw SQ_IMG); a non-hero kind must not fall back to
    slot 0 (the hero's row)."""
    img = SEQ_BIN.read_bytes()
    ib = lambda a: img[a - S["SQ_IMG"]]
    iw = lambda a: ib(a) | ib(a + 1) << 8
    kt = p.z.read_memory(S["kind_tab"] + S["KT_SEQ"], 32)
    pg, slot0 = S["seq_rows"] & 0xFF00, S["seq_rows"] & 0xFF
    hero = p.rb("HERO_KIND")
    bad = []
    for k in sorted({hero, *kinds}):
        blk = iw(S["ksm_tab"] + 2 * k)
        if blk == 0 or (k != hero and kt[k] == slot0):
            bad.append((k, "no row"))
            continue
        rb = p.z.read_memory(pg | kt[k], 17)
        n = ib(blk)
        for i in range(8):
            mo = blk + 10 + ib(blk + 2 + i)
            ln = blk + 10 + n - mo
            got = bytes(p.z.read_memory(rb[2 * i] | rb[2 * i + 1] << 8, ln))
            if got != img[mo - S["SQ_IMG"]:mo - S["SQ_IMG"] + ln]:
                bad.append((k, "seq", i))
                break
        else:
            if rb[16] != ib(blk + 1):
                bad.append((k, "impact"))
    check(f"GI {tag}: sequence cache rows of hero {hero} + kinds {sorted(kinds)} == the masters", bad == [], bad)


def seq_sweep(p, check):
    """seq_check for both heroes on D1..D8 (level_descend stub) and the PROTO start."""
    p.proto_start = 0
    for hero in ("1", "2"):
        p.load()
        p.wait_state(S["GS_SELECT"])
        p.wb("seed_fixed", 1)
        p.wmem(S["seed_value"], w16(0x1234))
        p.wb("INPUT_REPEAT", 0)
        p.wb("ANIM_FREEZE", 1)
        p.wb("INPUT_SRC", 1)
        p.menu_start(GL.K_WIZARD if hero == "2" else GL.K_KNIGHT)
        seq_check(p, check, f"SQ hero {hero} D1", lp_kinds(p))
        check(f"GI B1: hero {hero} D1 TILE_GLYPHS[0..7] == 0 (erase_rect T_AIR path)",
              list(p.z.read_memory(S["TILE_GLYPHS"], 8)) == [0] * 8)
        for d in range(2, 9):
            pc0 = p.pc()
            ok, _ = p.code([0x3E, d - 1, 0x32] + w16(S["LVL_DEPTH"])
                           + [0xCD] + w16(S["level_descend"]), game=True)
            p.z.cmd("set-register PC=%d" % pc0)
            p.release()
            p.settle(4)
            check(f"GI SQ hero {hero} D{d}: level_descend stub ran", ok and p.rb("LVL_DEPTH") == d, p.rb("LVL_DEPTH"))
            seq_check(p, check, f"SQ hero {hero} D{d}", lp_kinds(p))
            check(f"GI B1: hero {hero} D{d} TILE_GLYPHS[0..7] == 0",
                  list(p.z.read_memory(S["TILE_GLYPHS"], 8)) == [0] * 8)
    p.proto_start = 1
    p.load()
    p.wait_state(S["GS_SELECT"])
    p.wb("INPUT_REPEAT", 0)
    p.wb("INPUT_SRC", 1)
    p.menu_start(GL.K_KNIGHT)
    seq_check(p, check, "SQ PROTO", list(range(S["K_SKELETON"], S["K_PROTO_END"])))
    p.proto_start = 0


def floor_build_check(p, check, tag):
    """Every room of the level, seeded with a dagger stack (storey 0, col 16), an
    arrow stack under a potion (storey 1, col 20) and a potion under arrows
    (storey 1, col 24): build_room_map (into NEXT_MAP) stamps FLOOR1's 2x2
    markers of every seeded footprint. The seeds are removed after."""
    free = [i for i in range(S["FLOOR_MAX"]) if p.rb(S["FLOOR_LIST"] + 4 * i) == S["FL_EMPTY"]][:5]
    if len(free) < 5:
        check(f"GI {tag}: FLOOR_LIST has 5 free entries for the build check", False, free)
        return
    D, A, P, S1 = S["IT_DAGGER"], S["IT_ARROW"], S["IT_POTION"], S["FL_S1"]
    n, bad = 0, []
    for room in range(p.rb("LVL_NROOMS")):
        seeds = [(room, 16, D), (room | S1, 20, A), (room | S1, 20, P), (room | S1, 24, P), (room | S1, 24, A)]
        for i, (r, c, it) in zip(free, seeds):
            p.wmem(S["FLOOR_LIST"] + 4 * i, [r, c, it, 2])
        pc0 = p.pc()                          # (in play at the tick probe, as the
        ok, _ = p.code([0x3E, room, 0x16, S["NEXT_MAP"] >> 8, 0x21] + w16(S["build_room_map"])
                       + [0xCD] + w16(S["far3"]), game=True)      # descend stub)
        p.z.cmd("set-register PC=%d" % pc0)
        m = bytes(p.z.read_memory(S["NEXT_MAP"], 32 * S["PLAY_ROWS"]))
        t0 = S["T_ITEM0"]
        want = {(16 + h, 6 + k): t0 + k for h in (0, 1) for k in (0, 1)}
        want.update({(c + h, 15 + k): t0 + 2 + k for c in (20, 24) for h in (0, 1) for k in (0, 1)})
        got = [(c, r, m[r * 32 + c]) for (c, r), t in want.items() if m[r * 32 + c] != t]
        if not ok or got:
            bad.append((room, ok, got[:3]))
        n += 1
        for i in free:
            p.wb(S["FLOOR_LIST"] + 4 * i, S["FL_EMPTY"])
    check(f"GI {tag}: build_room_map stamps every seeded entry's 2x2 markers ({n} rooms)",
          n >= 1 and bad == [], bad)


def main():
    depths = 8
    if "--depths" in sys.argv:
        depths = int(sys.argv[sys.argv.index("--depths") + 1])
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail not in ("", None):
                    print(f"[detail] {tag}: {detail}", flush=True)

        p.proto_start = 0
        p.load()
        p.wait_state(S["GS_SELECT"])
        tables(p, check, "GI0 menu", 0)
        p.wb("seed_fixed", 1)
        p.wmem(S["seed_value"], w16(0x1234))
        p.wb("INPUT_REPEAT", 0)
        p.wb("ANIM_FREEZE", 1)
        p.wb("INPUT_SRC", 1)
        p.hold("1")
        p.wait_state(S["GS_PLAYING"])
        p.release()
        p.settle(3)
        snap0 = pool_snap(p)
        lim6 = S["alloc.lim6"] + 1
        check("GI lim6: a normal start leaves alloc's bank-6 limit at HIGH POOL6_END, GEN_TRAP 0",
              p.rb(lim6) == (S["SRC6_ADDR"] >> 8) and p.rb("GEN_TRAP") == 0, (p.rb(lim6), p.rb("GEN_TRAP")))
        fx_check(p, check)
        ink = {"steps": 0, "cells": 0, "bad": [], "exits": 0}
        for d in range(1, depths + 1):
            if d > 1:
                pc0 = p.pc()
                ok, _ = p.code([0x3E, d - 1, 0x32] + w16(S["LVL_DEPTH"])
                               + [0xCD] + w16(S["level_descend"]), game=True)
                p.z.cmd("set-register PC=%d" % pc0)
                check(f"GI D{d}: level_descend stub ran", ok and p.rb("LVL_DEPTH") == d, p.rb("LVL_DEPTH"))
                p.release()
                p.settle(4)
            tag = f"GI1 D{d} entry"
            tables(p, check, tag, d)
            screen_check(p, check, tag, d)
            floor_check(p, check, tag)
            snapd = pool_check(p, check, tag, snap0)
            if forced_exit(p, ink):                # 3E-T6 R3 (+ the new room's shadow inks)
                ink["exits"] += 1
                p.settle(3)
                floor_check(p, check, f"GI1 D{d} after a forced exit (room {p.rb('CUR_ROOM')})")
            # play: walk right then left (room changes, LP spawns); keep the hero alive
            for key in ("L", "H"):
                for _ in range(6):
                    p.set_ent(0, HP=99)
                    p.hold(key)
                    p.tick(40)
                    p.release()
                    p.tick(2)
                    if p.rb("GAME_STATE") != S["GS_PLAYING"]:
                        break
            p.until(lambda: p.idle(), 300)
            p.settle(3)
            tag = f"GI1 D{d} after play (room {p.rb('CUR_ROOM')})"
            tables(p, check, tag, d)
            screen_check(p, check, tag, d)
            floor_check(p, check, tag)
            pool_check(p, check, tag, snap0, snapd)
            floor_build_check(p, check, tag)
            if p.rb("GAME_STATE") != S["GS_PLAYING"]:
                print(f"[info] D{d}: GAME_STATE {p.rb('GAME_STATE')} — stop", flush=True)
                break
        check(f"GI R3: scroll steps show the entering room's floor items ({ink['exits']} exits, {ink['steps']} steps, "
              f"{ink['cells']} item cells)", ink["steps"] > 0 and ink["cells"] > 0 and not ink["bad"], ink["bad"][:6])
        check("GI R4: SEQ_TRAP 0 (every sq_load kind had a block and a slot)", p.rb("SEQ_TRAP") == 0, p.rb("SEQ_TRAP"))
        seq_sweep(p, check)
        check("GI R4: SEQ_TRAP 0 after the sequence sweep", p.rb("SEQ_TRAP") == 0, p.rb("SEQ_TRAP"))
        # 3F-T13 R6 guard: a PROTO start moves alloc's limit over SRC6; a level_enter after it
        # (pool_list) must bump GEN_TRAP and put the limit back (a PROTO session needs a reload)
        p.proto_start = 1
        p.load()
        p.wait_state(S["GS_SELECT"])
        p.wb("INPUT_REPEAT", 0)
        p.wb("ANIM_FREEZE", 1)
        p.wb("INPUT_SRC", 1)
        p.hold("1")
        p.wait_state(S["GS_PLAYING"])
        p.release()
        p.settle(3)
        check("GI lim6: the PROTO start moved the limit to HIGH R6_ADDR, GEN_TRAP 0",
              p.rb(lim6) == (S["R6_ADDR"] >> 8) and p.rb("GEN_TRAP") == 0, (p.rb(lim6), p.rb("GEN_TRAP")))
        # level_enter's pool step (alloc_restore + far6 pool_list); the rest of level_enter would
        # gen_list from the overwritten SRC6 sources (garbage by design: reload after PROTO)
        pc0 = p.pc()
        ok, _ = p.code([0xCD] + w16(S["alloc_restore"]) + [0x21] + w16(S["pool_list"])
                       + [0xCD] + w16(S["far6"]), game=True)
        p.z.cmd("set-register PC=%d" % pc0)
        check("GI lim6: PROTO then level_enter's pool step (pool_list) ran, tripped GEN_TRAP once and reset the limit",
              ok and p.rb("GEN_TRAP") == 1 and p.rb(lim6) == (S["SRC6_ADDR"] >> 8),
              (ok, p.rb("GEN_TRAP"), p.rb(lim6)))
        print(f"[info] run anomalies: {T.anomalies}", flush=True)
    print(f"gfx_integrity: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
    return 1 if fails else 0


if __name__ == "__main__":
    GL.Proto.snd_mode = 2                          # SND-4a: no stinger hold in descents
    sys.exit(main())
