#!/usr/bin/env python3
"""D3-8d status cues (game.md §6.4.1 V1-V3; src/mark.asm, src/mark7.asm,
anim.asm idle_phase, combat3.asm dh_status) on a release build (DEBUG_KIT=0),
PROTO room A, every other monster parked.

  S   each mark status (FROZEN, ASLEEP, STUNNED, CONFUSED, FEAR) on a Goblin
      and on the hero: one mark, at the body's centre col / the row above its
      top row; the cell = its map glyph OR the panel icon's lines, attr = the
      icon's ($45 / $41 / $07 / $43 / $42); frame A then frame B = frame A
      shifted up 1 px (FROZEN / CONFUSED / FEAR) or BRIGHT-toggled (ASLEEP /
      STUNNED: full height) on the screen (derived, no new art), toggling with
      (TICK + 3 slot) & 8; MK_N = 1; POISON / WEAK alone: no mark
  P   priority HOLD > MIND (FROZEN + CONFUSED: the FROZEN glyph)
  C   cleared (ST 0) -> erased within 2 ticks: the cell == its map glyph +
      attr, R_MK 0, MK_N 0
  D   death: a FROZEN Goblin killed by deal_hit -> its mark erased, MK_N 0
  K   a body came over a drawn mark in heavy (2nd-frame) ticks, then the mark
      cleared: the body's cell intact (queued, not erased)
  Q   saturated: 2 ops spent on new marks, a later covered mark still
      forgotten the same tick; a waiting (covered) mark retries 1 tick in 8
  G   hidden: a flyer at a storey top row (y = 9s) has none; a body over the
      mark cell hides it (no mark pixels inside the body), it comes back when
      the body leaves
  F   follow: a mark tracks its body's cell column (x moved by 3)
  X   room exit: a FEAR hero walks A -> B with a FROZEN Goblin's mark on
      screen: nothing left behind (screen == map outside bodies / marks),
      the Goblin's record forgotten, the hero's mark rebuilt in B
  R   drip: a drop never drawn on a mark cell (a mark on the fall path: the
      drop lands above it); a mark drawn onto the hanging drop forgets it
  H   V1 pose hold: a FROZEN Bat (ANIM_FREEZE 0) keeps one frame 24 ticks,
      flaps again after the clear; the same for the hero (breathing)
  V   V3: a typeless ASLEEP apply (dh_status.sure, no reaction pending)
      flashes SLEEP_FLASH_ATTR ($4F) on the body's cells for 1 tick, then the
      $41 tint; with a hit pending: none
  B   budget: "mkmix" (the budget "mix" with 5 marked bodies, walkers
      moving): every ordinary tick <= CAP, MK_OPS <= 2 every tick, ticks with
      2 ops seen (their max reported); "lcast" (no status) cast max <= CAST_CAP
      and every fire tick MK_OPS 0
Run: ZRCP_PORT=<port> python3 tests/marks.py
"""
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
sys.argv = [sys.argv[0], "999"]               # keep game.py's item filter inert
import game  # noqa: E402
from game_lib import (Harness, S, EMU_ARGS, K_KNIGHT, K_GOBLIN, K_BAT, K_RAT,  # noqa: E402
                      stand_y, attr_at, cell_bytes, GS_PLAYING, mark_cells)
from proj3 import T, w16  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT = 1, 2, 4, 8
STF, ST1, ST2, STX = S["ST_FLAGS"], S["ST_T1"], S["ST_T2"], S["ST_X"]
FROZEN, ASLEEP, STUNNED = 1, 2, 3
FEAR, CONF = 1 << 2, 2 << 2
POISON, WEAK = 0x10, 0x20
HY = stand_y(1, 6)
HX = 12
NOWHERE = 7
STUB = S["LOWRAM_END_3B"]
MARKS = [("FROZEN", FROZEN, 0xF0, 1), ("ASLEEP", ASLEEP, 0xF0, 2), ("STUNNED", STUNNED, 0xF0, 3),
         ("CONFUSED", CONF, 0x0F, 4), ("FEAR", FEAR, 0x0F, 5)]


def icons():
    """status_icons (the D3-3 art, assets) -> 7 glyphs + 7 attrs."""
    src = (HERE.parent / "assets/gfx/sprites/status_icons.asm").read_text()
    rows = [[int(x, 16) for x in re.findall(r"\$([0-9A-Fa-f]{2})", ln)] for ln in src.splitlines()
            if ln.strip().startswith("DEFB")]
    glyphs = [bytes(r) for r in rows if len(r) == 8]
    attrs = [r[0] for r in rows if len(r) == 1]
    return glyphs, attrs


GLYPHS, ATTRS = icons()


def full(g):
    """ASLEEP / STUNNED use all 8 rows: frame B = a BRIGHT toggle, not a shift."""
    return GLYPHS[g - 1][7] != 0


def lines(g, frame_b):
    """The mark's 8 screen lines (game.md §6.4.1 frame B = A shifted up 1 px):
    a glyph with a blank bottom row rests one line down; a full one keeps its
    lines in both frames."""
    a = GLYPHS[g - 1]
    if full(g):
        return a
    rest = bytes([0]) + a[:7]
    return a if frame_b else rest


def mattr(g, frame_b):
    return ATTRS[g - 1] ^ (0x40 if full(g) and frame_b else 0)


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = Tm(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:700]}", flush=True)

        if KIT:
            print("[skip] marks needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(h, p, check)
        print(f"marks: {len(fails)} failed" + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


class Tm(T, game.T):
    pass


def run(h, p, check):
    kt, slots = {}, {}
    WT = S["wait_tick"]

    def place(slot, x, y, flags, hp=None):
        kw = dict(X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=p.rb("CUR_ROOM"), FLAGS=flags, REACT=0,
                  FLT=0, HIT=0)
        if hp is not None:
            kw.update(HP=hp, MAXHP=hp)
        p.set_ent(slot, **kw)

    def scene(mons, freeze=1, hx=HX):
        """Fresh Knight game in PROTO room A: monsters parked, mons = [(kind,
        x, y or None (standing), left)] -> their slots."""
        p.boot(K_KNIGHT, freeze=freeze)
        if not kt:
            kt.update(p.kinds())
            for sl in range(1, 16):
                slots.setdefault(p.ent(sl)["KIND"], sl)
        room = p.rb("CUR_ROOM")
        for sl in range(1, 16):
            e = p.ent(sl)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                p.set_ent(sl, ROOM=NOWHERE)
        place(0, hx, HY, EF_ACTIVE | EF_PLAYER, 200)
        out = []
        for kind, x, y, left in mons:
            sl = slots[kind]
            place(sl, x, HY + 6 - kt[kind]["bh"] if y is None else y,
                  EF_ACTIVE | EF_HOSTILE | (EF_LEFT if left else 0), 60)
            out.append(sl)
        for a in (STF, ST1, ST2, STX):
            p.wmem(a, [0] * 16)
        p.tick(3)
        return out

    def kattr(kind):
        return p.rb(S["kind_tab"] + S["KT_ATTR"] + kind)

    def setst(slot, f, t1=0, t2=0):
        p.wb(STF + slot, f)
        p.wb(ST1 + slot, t1)
        p.wb(ST2 + slot, t2)

    def rec(slot):
        b = p.z.read_memory(S["SLOTREC"] + slot * 16 + S["R_MK"], 2)
        if not b[0]:
            return None
        return dict(g=b[0] & 7, fb=bool(b[0] & 8), cell=(b[1] & 31, ((b[0] & 0x30) >> 1) | (b[1] >> 5)))

    def want_cell(slot):
        e = p.ent(slot)
        top = e["PY"] >> 3
        col = ((e["PX"] + 4) >> 3) + (kt[e["KIND"]]["bw"] - 1) // 2
        ftop = p.rb(S["SLOTREC"] + slot * 16 + S["R_ROW"])   # ANIM-IMPORT2: the drawn frame's top row
        if ftop > top:                                   # a 40-px frame on a 48-px body: above the head
            return (col, ftop - 1)
        if top % 9 == 0:
            return None
        return (col, top - 1)

    def bg(c, r):
        tabs = p.bg_tables()
        return bytes(tabs[1][tabs[0][r * 32 + c] * 8:][:8]), tabs[2][tabs[0][r * 32 + c]]

    def shown(slot, g):
        """(ok, detail): slot's mark drawn as wanted on the composed screen."""
        m = rec(slot)
        cell = want_cell(slot)
        if not m or m["cell"] != cell or m["g"] != g:
            return False, (m, cell, g)
        tick = p.rw("TICK_COUNTER")
        fb = bool((tick + 3 * slot) & 8) and not p.rb("ANIM_FREEZE")
        fr = p.composed_frame()
        tile, _ = bg(*cell)
        exp = bytes(t | l for t, l in zip(tile, lines(g, m["fb"])))
        got = bytes(cell_bytes(fr, *cell))
        return (m["fb"] == fb and got == exp and attr_at(fr, *cell) == mattr(g, m["fb"]),
                (m, fb, got.hex(), exp.hex(), hex(attr_at(fr, *cell))))

    def is_bg(cell):
        fr = p.composed_frame()
        g, _ = bg(*cell)
        sh = shadow_attr(cell)
        return bytes(cell_bytes(fr, *cell)) == g and attr_at(fr, *cell) == sh

    def shadow_attr(cell):
        c, r = cell
        p.z.cmd("set-memory-zone 0")
        try:
            a = p.z.read_memory(7 * 16384 + (S["SHADOW_ATTR"] - 0xC000) + r * 32 + c, 1)[0]
        finally:
            p.z.cmd("set-memory-zone -1")
        return a

    # ====================== S: every status on a Goblin and on the hero =========
    for who in ("goblin", "hero"):
        for name, f, t1, g in MARKS:
            gs = scene([(K_GOBLIN, HX + 8, None, True)], freeze=0)
            sl = gs[0] if who == "goblin" else 0
            setst(sl, f, t1)
            p.tick(2)
            ok, d = shown(sl, g)
            fb0 = rec(sl)["fb"] if rec(sl) else None
            seen = {fb0}
            okb = True
            for _ in range(10):                   # until the frame flips
                p.tick()
                m = rec(sl)
                if m and m["fb"] != fb0:
                    seen.add(m["fb"])
                    okb, db = shown(sl, g)
                    break
            fr = p.composed_frame()
            cell = want_cell(sl)
            a_lines = lines(g, False)
            b_lines = lines(g, True)
            check(f"S {who} {name}: mark g{g} at the centre col / row above, cell = map glyph | icon, attr "
                  f"{ATTRS[g - 1]:#04x}; MK_N 1", ok and p.rb("MK_N") == 1, d)
            if full(g):
                rule = b_lines == a_lines and mattr(g, True) == mattr(g, False) ^ 0x40
                what = "frame B = frame A BRIGHT-toggled (attr ^ $40, a full-height glyph)"
            else:
                rule = b_lines == a_lines[1:] + b"\0"
                what = "frame B = frame A shifted up 1 px"
            check(f"S {who} {name}: frame {'B' if not fb0 else 'A'} within 10 ticks, drawn exactly; {what}",
                  okb and seen == {False, True} and rule, (seen, okb, cell, a_lines.hex(), b_lines.hex()))
    # POISON / WEAK alone: no mark (panel icons only)
    g1, = scene([(K_GOBLIN, HX + 8, None, True)])
    setst(0, POISON | WEAK, 0, 0x99)
    p.tick(3)
    check("S POISON + WEAK hero: no mark (MK_N 0)", p.rb("MK_N") == 0 and rec(0) is None, rec(0))

    # ====================== P: HOLD > MIND ======================================
    g1, = scene([(K_GOBLIN, HX + 8, None, True)])
    setst(g1, FROZEN | CONF, 0xFF)
    p.tick(2)
    ok, d = shown(g1, 1)
    check("P FROZEN + CONFUSED Goblin: the FROZEN mark", ok, d)

    # ====================== C: cleared -> erased ================================
    cell = want_cell(g1)
    setst(g1, 0)
    p.tick(2)
    check("C cleared: within 2 ticks R_MK 0, MK_N 0, the cell == map glyph + shadow attr",
          rec(g1) is None and p.rb("MK_N") == 0 and is_bg(cell), (rec(g1), p.rb("MK_N"), cell))

    # ====================== D: death ============================================
    g1, = scene([(K_GOBLIN, HX + 4, None, True)])
    setst(g1, FROZEN, 0xF0)
    p.tick(2)
    cell = want_cell(g1)
    had = rec(g1) is not None
    pc0 = p.pc()
    inner = ([0xDD, 0x21] + w16(S["P_ENTITIES"]) + [0x3E, g1, 0x06, 99, 0x0E, 0, 0x1E, 0, 0xCD]
             + w16(S["deal_hit"]))
    p.wmem(STUB, p.bank3(inner) + [0xC3] + w16(WT))
    p.z.cmd("set-register PC=%d" % STUB)
    p.tick()
    assert p.pc() == WT, hex(pc0)
    p.tick(3)
    gone = rec(g1) is None and p.rb("MK_N") == 0
    p.turn("WAIT")                                # the DEATH sequence plays in a turn
    p.tick(10)
    check("D a FROZEN Goblin killed: its mark erased (R_MK 0, MK_N 0, cell == background)",
          had and gone and is_bg(cell) and p.ent(g1)["FLAGS"] == 0, (had, gone, rec(g1), p.ent(g1)["FLAGS"]))

    # ====================== G: hidden ==========================================
    b1, = scene([(K_BAT, HX + 8, 9, True)])
    setst(b1, FROZEN, 0xF0)
    p.tick(3)
    check("G a FROZEN Bat at y 9 (storey top row): no mark", rec(b1) is None and p.rb("MK_N") == 0, rec(b1))
    g1, b1 = scene([(K_GOBLIN, HX + 8, None, True), (K_BAT, 3, 10, False)])
    setst(g1, FROZEN, 0xF0)
    p.tick(2)
    cell = want_cell(g1)
    had = rec(g1) is not None
    by = cell[1] - 1                                 # the Bat's body over the mark cell
    place(b1, cell[0] - 1, by, EF_ACTIVE | EF_HOSTILE)
    p.tick(3)
    e = p.ent(b1)
    inside = e["DCOL"] <= cell[0] < e["DCOL"] + e["DCOLS"] and e["DROW"] <= cell[1] < e["DROW"] + e["DROWS"]
    hid = rec(g1) is None
    place(b1, 3, 10, EF_ACTIVE | EF_HOSTILE)
    p.tick(3)
    ok, d = shown(g1, 1)
    check("G a Bat over the Goblin's mark cell: the mark forgotten while covered, back once it left",
          had and inside and hid and ok, (had, inside, hid, d))

    # ====================== K: a body came over a mark in heavy ticks ==========
    # (review 1): the mark's damage test does not run in a 2nd-frame tick; a
    # later erase must not wipe the body now on the cell (queue it instead)
    PRD = S["probe_render_done"]

    def heavy_tick():
        """a tick whose mark_tick sees a 2nd frame: LAST_TICK_FRAME poked
        right after render (probe_render_done)."""
        p.z.cmd("set-breakpoint 3 PC=%d" % PRD)
        p.extra_probes = {PRD}
        p.tick()
        assert p.pc() == PRD, hex(p.pc())
        p.wb("LAST_TICK_FRAME", (p.rb("SYS_FRAMES") + 1) & 255)
        p.z.cmd("set-breakpoint 3")
        p.extra_probes = set()
        p.tick()

    def cell_now(cell):
        fr = p.composed_frame()
        return bytes(cell_bytes(fr, *cell)), attr_at(fr, *cell)
    g1, b1 = scene([(K_GOBLIN, HX + 8, None, True), (K_BAT, 3, 10, False)])
    setst(g1, FROZEN, 0xF0)
    p.tick(2)
    cell = want_cell(g1)
    had = rec(g1) is not None
    place(b1, cell[0] - 1, cell[1] - 1, EF_ACTIVE | EF_HOSTILE)
    for _ in range(3):
        heavy_tick()
    still = rec(g1) is not None                   # not seen: still "drawn"
    setst(g1, 0)                                  # cleared under the Bat
    p.tick(3)
    got = cell_now(cell)
    place(b1, 3, 10, EF_ACTIVE | EF_HOSTILE)      # the reference: the Bat there with no mark
    p.tick(3)
    place(b1, cell[0] - 1, cell[1] - 1, EF_ACTIVE | EF_HOSTILE)
    p.tick(3)
    ref = cell_now(cell)
    check("K a Bat over a drawn mark in 3 heavy ticks, then the mark cleared: the Bat's cell intact "
          "(== the Bat there with no mark), MK_N 0",
          had and still and got == ref and p.rb("MK_N") == 0, (had, still, got[0].hex(), ref[0].hex(), got[1], ref[1]))

    # ====================== Q: saturated ops still run the damage test ==========
    # hero (RLIST 0) + Rat (1) get new marks this tick = both ops; the Goblin's
    # (slot 3) drawn mark is covered by the Bat in the same tick: forgotten
    # (+ its cell queued) although no op was left
    r1, g1, b1 = scene([(K_RAT, HX + 4, None, True), (K_GOBLIN, HX + 9, None, True), (K_BAT, 3, 10, False)])
    setst(g1, FROZEN, 0xF0)
    p.tick(2)
    cell = want_cell(g1)
    had = rec(g1) is not None
    p.wb("MK_RR", 0)
    setst(0, FEAR, 0x0F)
    setst(r1, CONF, 0x0F)
    place(b1, cell[0] - 1, cell[1] - 1, EF_ACTIVE | EF_HOSTILE)
    p.tick()
    q = (p.rb("MK_OPS"), rec(0) is not None, rec(r1) is not None, rec(g1), p.rb("PEND_DMG_COUNT"))
    p.tick(2)
    fr = p.composed_frame()
    check("Q 2 ops spent on the hero / Rat's new marks; the Goblin's covered mark (later in RLIST) "
          "forgotten in the same tick, its cell queued; the Bat's cell no mark attr after",
          had and q[0] == 2 and q[1] and q[2] and q[3] is None and q[4] >= 1
          and attr_at(fr, *cell) != ATTRS[0], (had, q, hex(attr_at(fr, *cell))))
    # a covered (waiting) mark does not burn an op every tick
    opsl = []
    for _ in range(16):
        p.tick()
        opsl.append(p.rb("MK_OPS"))
    check("Q a mark waiting under the Bat retries on 1 tick in 8 (+ when the render touches it): "
          "<= 3 ops in 16 idle ticks besides the toggles", sum(opsl) <= 3 + 4, opsl)

    # ====================== F: follow ==========================================
    g1, = scene([(K_GOBLIN, HX + 8, None, True)])
    setst(g1, FEAR, 0x0F)
    p.tick(2)
    c0 = rec(g1)["cell"] if rec(g1) else None
    place(g1, HX + 11, HY + 6 - kt[K_GOBLIN]["bh"], EF_ACTIVE | EF_HOSTILE | EF_LEFT)
    p.tick(3)
    ok, d = shown(g1, 5)
    check("F a FEAR Goblin moved 3 cols: its mark follows (old cell background, MK_N 1)",
          c0 and ok and is_bg(c0) and p.rb("MK_N") == 1, (c0, d))

    # ====================== X: room exit =======================================
    g1, = scene([(K_GOBLIN, 6, None, False)], hx=26)
    setst(g1, FROZEN, 0xF0)
    setst(0, FEAR, 0x0F)
    p.tick(2)
    two = p.rb("MK_N") == 2
    for _ in range(4):
        p.turn("L")
        if p.rb("CUR_ROOM") != 0:
            break
    p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 200)
    p.tick(3)
    ok, d = shown(0, 5)
    bad = p.bg_mismatch()
    check("X FEAR hero A -> B with a FROZEN Goblin's mark drawn: B's screens == ROOM_MAP outside "
          "bodies / marks, the Goblin's record forgotten, the hero's mark rebuilt (MK_N 1)",
          two and p.rb("CUR_ROOM") == 1 and not bad and rec(g1) is None and ok and p.rb("MK_N") == 1,
          (two, p.rb("CUR_ROOM"), bad[:4], rec(g1), d, p.rb("MK_N")))

    # ====================== R: the drip ========================================
    # a source at (c, 9) of room A (PROTO: none of its own), a FROZEN Goblin
    # whose mark sits on the fall path; the drop must land above the mark
    g1, = scene([(K_GOBLIN, HX + 8, None, True)])
    setst(g1, FROZEN, 0xF0)
    p.tick(2)
    mc = want_cell(g1)
    m = p.z.read_memory(S["ROOM_MAP"], 32 * 18)
    col = mc[0]
    okcol = m[9 * 32 + col] == 0 and 1 <= m[8 * 32 + col] <= 3 and all(m[r * 32 + col] == 0
                                                                     for r in range(9, mc[1] + 1))
    p.z.cmd("write-memory %d 0 1 %d 255 0 1 90 %d 9" % (S["DRIP_ST"], col, col))
    rows, bad, landed = [], [], False
    for _ in range(120):
        p.tick()
        d = p.z.read_memory(S["DRIP_ST"], 6)
        marks = mark_cells(p)
        if d[4]:
            rows.append(d[3])
            if (d[2], d[3]) in marks:
                bad.append((d[2], d[3]))
        ok, dd = shown(g1, 1)
        if not ok:
            bad.append(("mark", dd))
        if rows and d[0] == S["DRS_IDLE"] and not d[4]:
            landed = True
            break
    check(f"R a drop falling onto a mark (col {col}, mark row {mc[1]}): never drawn on it, lands at row "
          f"{mc[1] - 1}, the mark intact every tick",
          okcol and landed and not bad and max(rows) == mc[1] - 1, (okcol, landed, bad[:4], rows[-6:]))
    # a mark appearing on the hanging drop: the drop is forgotten
    b1, = scene([(K_BAT, 3, 10, False)])
    p.tick()
    bx = ((p.ent(b1)["PX"] + 4) >> 3) + (kt[K_BAT]["bw"] - 1) // 2
    srcok = p.rb(S["ROOM_MAP"] + 9 * 32 + bx) == 0     # (an injected source: air is enough)
    p.z.cmd("write-memory %d 0 1 %d 255 0 1 90 %d 9" % (S["DRIP_ST"], bx, bx))
    p.until(lambda: p.rb("DRIP_DRAWN") and p.rb("DRIP_ST") == S["DRS_FORM"], 60)
    formed = p.rb("DRIP_DRAWN") == 1
    setst(b1, FROZEN, 0xF0)
    p.tick(2)
    ok, d = shown(b1, 1)
    check("R a FROZEN Bat's mark on the hanging drop's cell: drawn, the drop forgotten (DRAWN 0, IDLE)",
          srcok and formed and ok and p.rb("DRIP_DRAWN") == 0 and p.rb("DRIP_ST") == S["DRS_IDLE"],
          (srcok, formed, d, p.z.read_memory(S["DRIP_ST"], 6)))

    # ====================== H: V1 pose hold ====================================
    b1, = scene([(K_BAT, HX + 8, 11, True)], freeze=0)
    fids = set()
    for _ in range(16):
        p.tick()
        fids.add(p.ent(b1)["DFID"])
    flaps = len(fids) > 1
    setst(b1, FROZEN, 0xF0)
    p.tick(2)
    held = set()
    for _ in range(24):
        p.tick()
        held.add(p.ent(b1)["DFID"])
    setst(b1, 0)
    again = set()
    for _ in range(16):
        p.tick()
        again.add(p.ent(b1)["DFID"])
    check("H a FROZEN Bat holds one frame 24 ticks (it flapped before), flaps again after the clear",
          flaps and len(held) == 1 and len(again) > 1, (fids, held, again))
    scene([], freeze=0)
    fids = set()
    for _ in range(40):
        p.tick()
        fids.add(p.ent(0)["DFID"])
    setst(0, STUNNED, 0xF0)
    p.tick(2)
    held = set()
    for _ in range(3):                            # (a held hero's auto-Wait every 4 ticks)
        p.tick()
        held.add(p.ent(0)["DFID"])
    check("H the STUNNED hero holds his idle frame (it breathed before)",
          len(fids) > 1 and len(held) == 1, (fids, held))

    # ====================== V: V3 sleep flash ==================================
    g1, = scene([(K_GOBLIN, HX + 8, None, True)])

    def sure(react):
        p.set_ent(g1, REACT=react, FLT=0, FLA=0)
        setst(g1, 0)
        sets = []
        for lab, v in (("dh_slot", g1), ("dh_efx", S["EFX_ASLEEP"]), ("dh_eff", 4), ("dh_imm", 0), ("dh_rsp", 0)):
            sets += [0x3E, v, 0x32] + w16(S[lab])
        inner = ([0xDD, 0x21] + w16(S["P_ENTITIES"] + g1 * STRIDE) + [0x21] + w16(S["P_ENTITIES"])
                 + [0x22] + w16(S["ATK_PTR"]) + sets + [0xCD] + w16(S["dh_status.sure"]))
        p.wmem(STUB, p.bank3(inner) + [0xC3] + w16(WT))
        p.z.cmd("set-register PC=%d" % STUB)
        p.tick()
        e = p.ent(g1)
        return p.rb(STF + g1), e["FLT"], e["FLA"]
    def body_attrs():
        e = p.ent(g1)
        fr = p.composed_frame()
        return {attr_at(fr, c, r) for c in range(e["DCOL"], e["DCOL"] + e["DCOLS"])
                for r in range(e["DROW"], e["DROW"] + e["DROWS"])}
    a = sure(0)
    p.tick()
    shown1 = body_attrs()
    p.tick()
    shown2 = body_attrs()
    b = sure(S["RC_HURT"])
    fa = S["SLEEP_FLASH_ATTR"]
    check(f"V typeless ASLEEP (no reaction pending): ASLEEP set, E_FLT 1 / E_FLA {fa:#04x}; on screen the "
          f"body shows {fa:#04x} one tick (!= the kind attr {kattr(K_GOBLIN):#04x} and the $41 tint), then $41",
          a[0] == ASLEEP and a[1:] == (S["SLEEP_FLASH"], fa) and fa not in (0x41, kattr(K_GOBLIN))
          and shown1 == {fa} and shown2 == {0x41}, (a, shown1, shown2))
    check("V with a hit reaction pending: no flash (the impact is the cue)", b[0] == ASLEEP and b[1] == 0, b)

    # ====================== B: budget ==========================================
    import budget
    ops = []
    budget.TICK_HOOKS[:] = [lambda st: ops.append((st.p.rb("MK_OPS"), st.ticks[-1][0],
                                                   "probe_act_fire" in st.ticks[-1][1]))]
    st, _ = budget.run_scenario(h, budget.SCENARIOS["mkmix"])
    two = [t for o, t, _ in ops if o == 2]
    print(f"[info] B mkmix: {len(ops)} ticks, ordinary max {max(st.ordinary_t)} T, ops histogram "
          f"{dict(sorted({o: sum(1 for x, _, _ in ops if x == o) for o, _, _ in ops}.items()))}, "
          f"max tick with 2 ops {max(two) if two else 0} T", flush=True)
    check(f"B mkmix: every ordinary tick <= {budget.CAP}, MK_OPS <= 2 per tick, >= 1 tick with 2 ops",
          max(st.ordinary_t) <= budget.CAP and max(o for o, _, _ in ops) <= 2 and two,
          (max(st.ordinary_t), max(o for o, _, _ in ops), len(two)))
    ops.clear()
    st, _ = budget.run_scenario(h, budget.SCENARIOS["lcastf"])
    fire = [o for o, _, f in ops if f]
    print(f"[info] B lcastf (4 FROZEN marks): cast max {max(st.casts_t)} T, ordinary max {max(st.ordinary_t)} T, "
          f"ops on fire ticks {fire}", flush=True)
    check(f"B lcastf: cast ticks <= {budget.CAST_CAP}, ordinary <= {budget.CAP}, no mark op on a fire tick",
          max(st.casts_t) <= budget.CAST_CAP and max(st.ordinary_t) <= budget.CAP and fire and not any(fire),
          (max(st.casts_t), max(st.ordinary_t), fire))
    budget.TICK_HOOKS[:] = []


if __name__ == "__main__":
    sys.exit(main())
