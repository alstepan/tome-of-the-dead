#!/usr/bin/env python3
"""GI: graphics-data integrity (fix/3d-artefacts, user report 2026-10-06:
stray lines in ladders / door arch / potion / bricks / around the hero).

Every runtime graphics table is compared byte-for-byte with its assembled
source (read from the .sna the suite loads, never from the running machine):

  GI0  at the menu (after boot): TILE_GLYPHS ids 0..31 == tiles_common_glyphs,
       TILE_ATTRS 0..31 == tiles_common_attrs, ORN_GLYPHS == orn_glyphs,
       FONT6 planes == font6x8 re-laid (bits 1..0 masked, holes skipped),
       bank-1 vdata, the bank-1 menu art (menu_font .. menu_torch_end),
       bank-7 tileset slots 0..7, the bank-7 cold code B7_CODE..B7_LIMIT (D3-S2:
       the old bitmap shadow; canary — no SMC / data writes there), bank-0
       text block — all == the .sna
  GI1  generated new game (seed_fixed) and every depth D1..D8 entered through
       the real level_descend (in-game stub), each followed by play (walk
       left / right through the rooms: room changes + LP spawns):
       the GI0 tables again (TILE_ATTRS minus the theme_ids, which follow the
       depth), ids 32..63 glyphs / attrs / tile_flags == the bank-7 slot,
       the sprite pool (bank 0 POOL_START.., banks 4 / 6) + FRT == as built at
       the hero start (D3-4: which includes the hero's class FX kind, checked
       generated — one variant per facing for each fid of its range — once), and the displayed playfield == ROOM_MAP drawn from the
       SOURCE glyphs (every cell not under a sprite; row 17 may hold an
       ornament glyph) + the panel's potion glyph == the source T_POTION.
Run with ZRCP_PORT=<port>.  `--depths N` (default 8).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import game_lib as GL                                   # noqa: E402
from game_lib import Harness, S, EMU_ARGS, cell_bytes   # noqa: E402
from lp import T, w16                                   # noqa: E402

BANK = 16384


def sna_bank(b, addr, n):
    """Bytes of bank b at $C000-window address addr (the loaded .sna)."""
    o = b * BANK + (addr - 0xC000)
    return GL.SNA_RAM[o:o + n]


def sna_virt(v, n):
    """Virtual sprite-source / vdata address (copy_virt): $8000.. = bank 1,
    $C000.. = bank 3."""
    return sna_bank(1, v + 0x4000, n) if v < 0xC000 else sna_bank(3, v, n)


TC = S["TILE_COMMON"]
TILE_IDS = 64
SRC_GLY = sna_virt(S["tiles_common_glyphs"], TC * 8)
SRC_ATT = sna_virt(S["tiles_common_attrs"], TC)
SRC_ORN = sna_virt(S["orn_glyphs"], S["ORN_COUNT"] * 8)
SRC_FONT = sna_virt(S["font6x8"], 96 * 8)


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
    lists, t = [], S["theme_ids"]          # floor ids, 0, wall ids, 0 (level_load_tiles .patch)
    for _ in range(2):
        ids = []
        while (v := p.rb(t)) != 0:
            ids.append(v)
            t += 1
        t += 1
        lists.append(ids)
    theme = set(lists[0]) | set(lists[1])
    ab = [i for i in range(TC) if (depth == 0 or i not in theme) and a[i] != SRC_ATT[i]]
    check(f"GI {tag}: TILE_ATTRS ids 0..31 == tiles_common_attrs (theme ids aside)", ab == [], ab)
    if depth:
        th = ([i for i in lists[0] if a[i] != p.rb("LVL_ATTR_FLOOR")]
              + [i for i in lists[1] if a[i] != p.rb("LVL_ATTR_WALL")])
        check(f"GI {tag}: theme ids carry LVL_ATTR_FLOOR / WALL", th == [], (lists, th))
        slot = depth - 1
        base = (S["TSET_LO"] if slot < 4 else S["TSET_HI"]) + (slot & 3) * S["TSET_STRIDE"]
        src = sna_bank(7, base, S["TSET_STRIDE"])
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
            (1, S["vdata"] + 0x4000, S["vdata_end"] + 0x4000, "bank-1 vdata (font / icons / hot img / tiles / orn)"),
            (1, S["menu_font"], S["menu_torch_end"], "bank-1 menu art (font, title, torch)"),
            (7, S["TSET_LO"], S["TSET_LO"] + 4 * S["TSET_STRIDE"], "bank-7 tilesets 0..3"),
            (7, S["TSET_HI"], S["TSET_HI"] + 4 * S["TSET_STRIDE"], "bank-7 tilesets 4..7"),
            (7, S["B7_CODE"], S["B7_LIMIT"], "bank-7 cold code + unused tail (D3-S2: the "
             "freed bitmap shadow $E000..$F7FF is never written)"),
            (0, S["text_img"], S["text_img_end"], "bank-0 text block")):
        got = bank_read(p, b, lo, hi - lo)
        bad = diff_ranges(got, sna_bank(b, lo, hi - lo), lo)
        check(f"GI {tag}: {name} == .sna", bad == [], bad[:6])


POOL = ((0, S["POOL_START"], 0x10000), (4, 0xC000, 0x10000), (6, 0xC000, 0x10000))


def pool_snap(p):
    snap = {b: bank_read(p, b, lo, hi - lo) for b, lo, hi in POOL}
    snap["FRT"] = bytes(p.z.read_memory(S["FRT"], S["FRT_MAX"] * S["FRT_STRIDE"]))
    return snap


def pool_check(p, check, tag, snap0):
    now = pool_snap(p)
    for k in snap0:
        lo = S["FRT"] if k == "FRT" else dict((b, l) for b, l, _ in POOL)[k]
        bad = diff_ranges(now[k], snap0[k], lo)
        check(f"GI {tag}: sprite pool {'FRT' if k == 'FRT' else f'bank {k}'} == as built at hero start",
              bad == [], bad[:6])


def fx_check(p, check):
    """D3-4: the hero's class FX kind (K_FX_BASE + HERO_KIND) is resident at the
    hero start: every fid of its KT_FID0/KT_FCNT range has a right (v0/v1) and a
    left (v2/v3) variant in a pool bank whose bytes lie inside the pool."""
    hk = p.rb("HERO_KIND")
    k = S["K_FX_BASE"] + hk
    f0 = p.z.read_memory(S["kind_tab"] + S["KT_FID0"] + k, 1)[0]
    fc = p.z.read_memory(S["kind_tab"] + S["KT_FCNT"] + k, 1)[0]
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
    base = (S["TSET_LO"] if slot < 4 else S["TSET_HI"]) + (slot & 3) * S["TSET_STRIDE"]
    gly = SRC_GLY + sna_bank(7, base, (TILE_IDS - TC) * 8)
    lvl = {gly[i:i + 8] for i in range(TC * 8, TILE_IDS * 8, 8)}
    orn = {SRC_ORN[i:i + 8] for i in range(0, len(SRC_ORN), 8)}
    covered = set()
    drip = GL.drip_cells(p)                        # D3-8b: screen-only overlay
    for s_ in range(16):
        e = p.ent(s_)
        if e["DVIS"] & 1:
            covered |= {(c, r) for c in range(e["DCOL"], e["DCOL"] + e["DCOLS"])
                        for r in range(e["DROW"], e["DROW"] + e["DROWS"])}
    bad, n = [], 0
    for i, t in enumerate(m):
        c, r = i % 32, i // 32
        if (c, r) in covered:
            continue
        n += 1
        cb = cell_bytes(fr, c, r)
        if cb == gly[t * 8:t * 8 + 8] or (r == 17 and cb in orn):
            continue
        # decor glyph swap (decor_tick): a level id may show its partner frame
        if not (t >= TC and cb in lvl) and not GL.drip_shown(fr, drip, c, r):
            bad.append((c, r, t))
    check(f"GI {tag}: playfield ({n} uncovered cells) == ROOM_MAP in source glyphs", n > 300 and bad == [], bad[:6])
    pg = SRC_GLY[S["T_POTION"] * 8:S["T_POTION"] * 8 + 8]
    check(f"GI {tag}: panel potion glyph (row 19) == source T_POTION",
          any(cell_bytes(fr, c, 19) == pg for c in range(32)), "")


def floor_check(p, check, tag, room=None, m=None):
    """T7 review: the FLOOR_LIST invariant floor_pickup's pre-filter relies on
    (level_defs.asm FLOOR_LIST): every live entry of the room shows on its cell
    (row 9s+7) — the glyph of the LAST live entry of that cell in list order.
    Default: CUR_ROOM in the live ROOM_MAP; else room `room` built into `m`."""
    fl = p.z.read_memory(S["FLOOR_LIST"], S["FLOOR_MAX"] * S["FL_STRIDE"])
    if m is None:
        m = bytes(p.z.read_memory(S["ROOM_MAP"], 32 * S["PLAY_ROWS"]))
        room = p.rb("CUR_ROOM")
    tile = {S["IT_POTION"]: S["T_POTION"], S["IT_DAGGER"]: S["T_DAGGERS"], S["IT_ARROW"]: S["T_ARROWS"]}
    want = {}
    for i in range(S["FLOOR_MAX"]):
        r, col, item = fl[i * 4], fl[i * 4 + 1], fl[i * 4 + 2]
        if r == S["FL_EMPTY"] or (r & S["FL_ROOM_MASK"]) != room or item not in tile:
            continue
        sto = 1 if r & S["FL_S1"] else 0
        want[(col, 9 * sto + 7)] = tile[item]
    bad = [(c, r, m[r * 32 + c], t) for (c, r), t in want.items() if m[r * 32 + c] != t]
    check(f"GI {tag}: FLOOR_LIST live entries ({len(want)} cells) all show their glyph in ROOM_MAP", bad == [], bad)
    return len(want)


def floor_build_check(p, check, tag):
    """Every room of the level, seeded with a dagger stack (storey 0, col 16), an
    arrow stack under a potion (storey 1, col 20: the potion is the last entry)
    and a potion under arrows (storey 1, col 24): build_room_map (into NEXT_MAP)
    stamps the last live entry of each cell. The seeds are removed after."""
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
        got = (m[7 * 32 + 16], m[16 * 32 + 20], m[16 * 32 + 24])
        if not ok or got != (S["T_DAGGERS"], S["T_POTION"], S["T_ARROWS"]):
            bad.append((room, ok, got))
        n += 1
        for i in free:
            p.wb(S["FLOOR_LIST"] + 4 * i, S["FL_EMPTY"])
    check(f"GI {tag}: build_room_map stamps every seeded entry, the last of a shared cell ({n} rooms)",
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
        fx_check(p, check)
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
            pool_check(p, check, tag, snap0)
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
            pool_check(p, check, tag, snap0)
            floor_build_check(p, check, tag)
            if p.rb("GAME_STATE") != S["GS_PLAYING"]:
                print(f"[info] D{d}: GAME_STATE {p.rb('GAME_STATE')} — stop", flush=True)
                break
        print(f"[info] run anomalies: {T.anomalies}", flush=True)
    print(f"gfx_integrity: {len(fails)} failed" + (f": {fails[:8]}" if fails else ""), flush=True)
    return 1 if fails else 0


if __name__ == "__main__":
    GL.Proto.snd_mode = 2                          # SND-4a: no stinger hold in descents
    sys.exit(main())
