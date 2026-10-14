#!/usr/bin/env python3
"""D3-8b decorative drip (game.md §6.4.1 "Decorative drip"; src/drip.asm,
src/drip7.asm) on a release build (DEBUG_KIT=0), generated levels (seed_fixed).

  R  sources: on the start room's entry DRIP_N / DRIP_SRC == a Python model of
     drip_room (the LFSR seeded from RD_SEED, the old B3B-13b placement rules
     on ROOM_MAP); PROTO rooms (depth 0) have none
  A  ambient run (hero idle, then walking): every tick (wait_tick) ROOM_MAP and
     RNG_STATE unchanged by the drip, a drawn drop is never inside a drawn body
     footprint nor a drawn FX, its cell shows exactly one of the 3 drip glyphs
     with attr $05; FORM -> DROP -> FALL all seen, the drop lands and restarts
  C  cover: the hero teleported onto the drawn falling drop -> the drip forgets
     it the same tick and the next render repairs the cell (no $05 attr, no
     drop pixels outside the hero's mask); a drop above the hero lands on his
     head row - 1 (never enters his footprint)
  H  drip_hide (hide_sprites) erases a drawn drop: the cell == its map glyph
  M  drip_room on the same map at depths 0..8 == the model (PROTO / D8 none,
     2-source depths match), DRIP_ROW $FF after it
  X  a real exit (do_exit + scroll) while a drop is drawn: nothing left behind
     on either screen, the new room's sources == the model; walking back =
     the same sources (re-entry)
  P  PROTO room A: no drip
  T  cost: drip_tick T per tick (budget.Stepper, drip_tick .. decor_tick):
     max <= 4,000, reported with the mean
  TL the same in the loaded budget scenarios (mix, lightning, cast, lcast,
     wcast4: 4 monsters, casts, live FX) with a source injected into PROTO
     room A next to the fight: max <= 5,000, <= 250 T on fire ticks, every
     tick within its budget.py cap (reported per scenario; SND-2: gated like
     budget.py, ordinary / cast WORK vs CAP / CAST_CAP + the real deadline)
Run: ZRCP_PORT=<port> python3 tests/drip.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.argv = [sys.argv[0], "999"]               # keep game.py's item filter inert
import game  # noqa: E402
from game_lib import (Harness, S, EMU_ARGS, K_KNIGHT, GS_SELECT, GS_PLAYING,  # noqa: E402
                      attr_at, cell_bytes, PLAY_ROWS)

KIT = bool(S.get("KIT_DEBUG", 0))
G_DROP = bytes([0x3C, 0x18, 0x00, 0x00, 0x10, 0x38, 0x38, 0x10])
G_FORM = bytes([0x3C, 0x18, 0x18, 0x3C, 0x3C, 0x18, 0x00, 0x00])
G_FALL = bytes([0x00, 0x00, 0x00, 0x00, 0x10, 0x38, 0x38, 0x10])
GLYPH = {S["DRS_FORM"]: G_FORM, S["DRS_DROP"]: G_DROP, S["DRS_FALL"]: G_FALL}


def lfsr(x):
    x <<= 1
    return (x ^ 0x1D) & 255 if x > 255 else x


def model_room(rmap, depth, seed):
    """drip_room: -> list of (col, row) sources."""
    st = [(seed & 255) ^ (seed >> 8) or 1]

    def rnd():
        st[0] = lfsr(st[0])
        return st[0]
    if depth == 0 or depth >= 8:
        return []
    n = 1 if (depth - 1) % 3 == 0 else 2
    src = []
    for _ in range(n):
        for _ in range(S["DRIP_TRIES"]):
            c = rnd() & 31
            sr = rnd() & 3
            e = rnd()
            if sr == 3:
                continue
            r = sr + (9 if e & 1 else 0)
            if r == 0 or rmap[r * 32 + c] != 0 or not 1 <= rmap[(r - 1) * 32 + c] <= 3 \
                    or rmap[(r + 1) * 32 + c] != 0:
                continue
            if src and abs(src[0][0] - c) < S["DRIP_DMIN"]:
                continue
            src.append((c, r))
            break
    return src


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = game.T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:600]}", flush=True)

        if KIT:
            print("[skip] drip needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(p, check)
        print(f"drip: {len(fails)} failed" + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def start(p, master):
    p.proto_start = 0
    p.load()
    p.wait_state(GS_SELECT)
    p.wb("INPUT_REPEAT", 1)
    p.wb("ANIM_FREEZE", 1)
    p.wb("INPUT_SRC", 1)
    p.wb("seed_fixed", 1)
    p.z.cmd("write-memory %d %d %d" % (S["seed_value"], master & 255, master >> 8))
    p.menu_start(K_KNIGHT, settle=1)


def drip(p):
    b = p.z.read_memory(S["DRIP_ST"], 11)
    return dict(st=b[0], t=b[1], col=b[2], row=b[3], drawn=b[4], n=b[5],
                src=[(b[7 + 2 * i], b[8 + 2 * i]) for i in range(b[5])])


def boxes(p):
    out = set()
    for s_ in range(16):
        e = p.ent(s_)
        if e["DVIS"] & 1:
            out |= {(c, r) for c in range(e["DCOL"], e["DCOL"] + e["DCOLS"])
                    for r in range(e["DROW"], e["DROW"] + e["DROWS"])}
    for t in ("FXT0", "FXT1", "FXT2"):
        f = p.z.read_memory(S[t] + S["FX_DFID"], 7)
        if f[0] != 255:
            out |= {(c, r) for c in range(f[3], f[3] + f[5]) for r in range(f[4], f[4] + f[6])}
    return out


LOADED = ("mix", "lightning", "cast", "lcast", "wcast4")


def call7(p, label):
    """far7 `label` from a stub at the wait_tick probe (play resumes there)."""
    pc0 = p.pc()
    ok = p.run_stub([0xF3, 0x21, S[label] & 255, S[label] >> 8,
                     0xCD, S["far7"] & 255, S["far7"] >> 8, 0xFB], org=S["LOWRAM_END_3B"])
    p.z.cmd("set-register PC=%d" % pc0)
    return ok


def open_side(m):
    """(storey, key, edge col) of an open horizontal exit of the room, or None."""
    for s_ in (1, 0):
        for key, col in (("L", 31), ("H", 0)):
            if all(m[(9 * s_ + r) * 32 + col] == 0 for r in range(1, 8)):
                return s_, key, col
    return None


def inject_src(p):
    """budget.EXTRA_SETUP: a drip source in PROTO room A near the fight (the
    col nearest 14 on storey-1 row 9 that drip_room's rules accept), the
    first drop due on the next first-frame tick."""
    m = p.z.read_memory(S["ROOM_MAP"], 32 * PLAY_ROWS)
    ok = [c for c in range(4, 28) if m[9 * 32 + c] == 0 and 1 <= m[8 * 32 + c] <= 3 and m[10 * 32 + c] == 0]
    c = min(ok, key=lambda x: abs(x - 14))
    p.z.cmd("write-memory %d 0 1 %d 255 0 1 90 %d 9" % (S["DRIP_ST"], c, c))


def anim_cells(p):
    na = p.rb("ANIM_N")
    al = p.z.read_memory(S["ANIM_LIST"], 4 * na) if 0 < na <= 12 else b""
    return {(al[i], al[i + 1]) for i in range(0, len(al), 4)}


def exit_room(p, check, exit_, want):
    """Walk out through exit_ while a drop is drawn, check the new room, come back."""
    s_, key, col = exit_
    kw, kh = game.body(p, K_KNIGHT)
    y = 9 * s_ + 8 - kh
    room0 = p.rb("CUR_ROOM")
    p.place(0, 31 - kw if key == "L" else 0, y)
    p.until(lambda: drip(p)["drawn"] and drip(p)["st"] == S["DRS_FORM"], 600)
    d0 = drip(p)
    for _ in range(6):
        p.turn(key)
        if p.rb("CUR_ROOM") != room0:
            break
    p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 200)
    room1 = p.rb("CUR_ROOM")
    p.tick()
    d1 = drip(p)
    rm1 = bytes(p.z.read_memory(S["ROOM_MAP"], 32 * PLAY_ROWS))
    sd = p.z.read_memory(S["ROOM_DESC"] + room1 * S["RD_STRIDE"] + S["RD_SEED"], 2)
    want1 = model_room(rm1, p.rb("LVL_DEPTH"), sd[0] | sd[1] << 8)
    na = p.rb("ANIM_N")                           # decor attr cycles / glyph swaps (W14's)
    al = p.z.read_memory(S["ANIM_LIST"], 4 * na) if 0 < na <= 12 else b""
    anim = {(al[i], al[i + 1]) for i in range(0, len(al), 4)}
    bad = [cr for cr in p.bg_mismatch() + p.bg_mismatch_in(p.composed_frame()) if cr not in anim]
    check(f"X exit {key} storey {s_} with a drop drawn ({d0['col']}, {d0['row']}): room {room0} -> {room1}, "
          f"no drop left behind (both screens == ROOM_MAP bar a drop of this room), sources == the model {want1}",
          room1 != room0 and d0["drawn"] and not bad and d1["src"] == want1, (room1, d0, d1, bad[:4]))
    back = "H" if key == "L" else "L"
    for _ in range(8):
        p.turn(back)
        if p.rb("CUR_ROOM") == room0:
            break
    p.until(lambda: p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 200)
    p.tick()
    d2 = drip(p)
    check(f"X back in room {room0}: the same sources {want} (re-entry), screens == ROOM_MAP",
          p.rb("CUR_ROOM") == room0 and d2["src"] == want
          and not [cr for cr in p.bg_mismatch() if cr not in anim_cells(p)], (d2, p.rb("CUR_ROOM")))


def run(p, check):
    # ---- R: a generated start room with a source (D1: 1 source) -------------
    for master in range(0x1234, 0x1234 + 80):
        start(p, master)
        d = drip(p)
        exit_ = open_side(bytes(p.z.read_memory(S["ROOM_MAP"], 32 * PLAY_ROWS)))
        if d["n"] and exit_:
            break
    room = p.rb("CUR_ROOM")
    a = S["ROOM_DESC"] + room * S["RD_STRIDE"] + S["RD_SEED"]
    seed = p.z.read_memory(a, 2)
    seed = seed[0] | seed[1] << 8
    rmap0 = bytes(p.z.read_memory(S["ROOM_MAP"], 32 * PLAY_ROWS))
    want = model_room(rmap0, p.rb("LVL_DEPTH"), seed)
    check(f"R start room (master {master:#06x}, D{p.rb('LVL_DEPTH')}, room {room}): sources == "
          f"the drip_room model {want}", d["n"] and d["src"] == want, (d, want))
    # ---- M: drip_room at every depth on this map (D2 / D3 / D5 / D6: 2 sources) --
    dep0 = p.rb("LVL_DEPTH")
    got, rows = {}, set()
    for dep in range(0, 9):
        p.wb("LVL_DEPTH", dep)
        call7(p, "drip_room")
        got[dep] = drip(p)["src"]
        rows.add(drip(p)["row"])
    p.wb("LVL_DEPTH", dep0)
    call7(p, "drip_room")
    wantd = {dep: model_room(rmap0, dep, seed) for dep in range(9)}
    check(f"M drip_room at depths 0..8 == the model (PROTO 0 and D8 none; 2-source depths: "
          f"{[dep for dep in range(9) if len(wantd[dep]) == 2]}); DRIP_ROW $FF after each",
          got == wantd and not got[0] and not got[8] and any(len(v) == 2 for v in got.values())
          and rows == {0xFF}, (got, wantd, rows))
    # ---- A: ambient, hero idle ------------------------------------------------
    rng0 = p.rw("RNG_STATE")
    na = p.rb("ANIM_N")                           # decor glyph swaps rewrite their map cell
    al = p.z.read_memory(S["ANIM_LIST"], 4 * na) if na else b""
    swaps = {al[i + 1] * 32 + al[i] for i in range(0, len(al), 4) if al[i + 2] >= S["AL_GLYPH_MIN"]}
    seen, bad, lands, falls = set(), [], 0, []
    prev = None

    def watch(tag):
        nonlocal prev, lands
        d = drip(p)
        m = bytes(p.z.read_memory(S["ROOM_MAP"], 32 * PLAY_ROWS))
        diff = [(j % 32, j // 32) for j in range(len(m)) if m[j] != rmap0[j] and j not in swaps]
        if diff:
            bad.append((tag, "ROOM_MAP changed", diff[:3]))
        if d["drawn"]:
            seen.add(d["st"])
            cell = (d["col"], d["row"])
            if cell in boxes(p):
                bad.append((tag, "drop inside a drawn body / FX", cell))
            fr = p.composed_frame()
            if attr_at(fr, *cell) != S["DRIP_ATTR"] or bytes(cell_bytes(fr, *cell)) != GLYPH.get(d["st"]):
                bad.append((tag, "cell", cell, d["st"], hex(attr_at(fr, *cell)), bytes(cell_bytes(fr, *cell)).hex()))
            if d["st"] == S["DRS_FALL"]:
                falls.append(cell)
        if prev and prev["drawn"] and prev["st"] == S["DRS_FALL"] and not d["drawn"]:
            lands += 1
        prev = d
        return d

    for t in range(400):
        p.tick()
        watch(t)
    check("A 400 idle ticks: ROOM_MAP (bar decor glyph swaps) and RNG_STATE untouched, every drawn drop shows its glyph + $05, "
          "never in a drawn body / FX footprint",
          not bad and p.rw("RNG_STATE") == rng0, (bad[:4], hex(rng0), hex(p.rw("RNG_STATE"))))
    check(f"A FORM / DROP / FALL all drawn, {lands} drops landed (>= 3), the fall moves down one row "
          "per step in the source col",
          seen == set(GLYPH) and lands >= 3 and all(c in [s_[0] for s_ in want] for c, _ in falls),
          (seen, lands, falls[:8]))
    # ---- A2: walking about (bodies move; the drip still holds its rules) -----
    bad.clear()
    for k in ("L", "L", "L", "H", "H", "H", "H", "H", "L", "L") * 3:
        p.turn(k)
        watch("walk " + k)
    check("A walking 30 turns: the same invariants every tick of the turns' ends", not bad, bad[:4])
    # ---- C: cover (the hero teleported onto the falling drop) ------------------
    hero = p.ent(0)
    kw, kh = game.body(p, K_KNIGHT)
    res = None
    for _ in range(600):
        p.tick()
        d = drip(p)
        if d["drawn"] and d["st"] == S["DRS_FALL"]:
            c, r = d["col"], d["row"]
            s_ = r // 9
            ytop = 9 * s_ + 8 - kh
            if r >= ytop and c + kw <= 31:
                x = max(1, c - kw // 2)
                p.set_ent(0, X=x, Y=ytop, PX=x * 8, PY=ytop * 8, MODE=0)
                p.tick()
                d1 = drip(p)
                pend = p.rb("PEND_DMG_COUNT")
                p.tick()
                fr = p.composed_frame()
                res = (c, r, d1["drawn"], d1["st"], pend, attr_at(fr, c, r), (c, r) in boxes(p))
                break
    check("C the hero moved onto a drawn falling drop: forgotten that tick (DRAWN 0, IDLE, the cell "
          "queued), next render: the cell is the hero's (attr != $05)",
          res and res[2] == 0 and res[3] == S["DRS_IDLE"] and res[4] >= 1 and res[5] != S["DRIP_ATTR"]
          and res[6], res)
    # a drop falling onto the hero: lands above his head row
    hero = p.ent(0)
    top, x0 = hero["DROW"], hero["DCOL"]
    ok_land, rows = None, []
    for _ in range(800):
        p.tick()
        d = drip(p)
        e = p.ent(0)
        if d["drawn"] and d["st"] == S["DRS_FALL"]:
            rows.append((d["col"], d["row"]))
            if (d["col"], d["row"]) in boxes(p):
                ok_land = False
                break
        if d["st"] == S["DRS_FORM"] and d["drawn"] and ok_land is None and len(rows) > 0:
            # put the hero under the source (its next drop falls onto him)
            c, r = d["col"], d["row"]
            s_ = r // 9
            ytop = 9 * s_ + 8 - kh
            x = max(1, min(31 - kw, c - kw // 2))
            p.set_ent(0, X=x, Y=ytop, PX=x * 8, PY=ytop * 8, MODE=0)
            rows.clear()
            ok_land = "armed"
            src_col, top = c, ytop
        elif ok_land == "armed" and d["st"] == S["DRS_IDLE"]:
            ok_land = bool(rows) and max(r for _, r in rows) == top - 1
            break
    check("C a drop falling onto the hero's column lands at his head row - 1, never inside him",
          ok_land is True, (ok_land, rows[-4:], top))
    # ---- H: drip_hide ----------------------------------------------------------
    p.until(lambda: drip(p)["drawn"], 600)
    d = drip(p)
    pc0 = p.pc()
    ok = p.run_stub([0xF3, 0x21, S["drip_hide"] & 255, S["drip_hide"] >> 8,
                     0xCD, S["far7"] & 255, S["far7"] >> 8, 0xFB], org=S["LOWRAM_END_3B"])
    p.z.cmd("set-register PC=%d" % pc0)
    fr = p.composed_frame()
    c, r = d["col"], d["row"]
    tabs = p.bg_tables()
    g = bytes(tabs[1][tabs[0][r * 32 + c] * 8:][:8])
    check("H drip_hide: the drawn drop erased (cell == its map glyph, DRAWN 0, DRIP_N 0)",
          ok and d["drawn"] and bytes(cell_bytes(fr, c, r)) == g and not drip(p)["drawn"] and drip(p)["n"] == 0,
          (ok, d, bytes(cell_bytes(fr, c, r)).hex(), g.hex()))
    # ---- X: a real exit with a drop on screen, then back (re-entry) ---------------
    start(p, master)
    exit_room(p, check, exit_, want)
    # ---- P: PROTO rooms have none -----------------------------------------------
    p.proto_start = 1
    p.boot(K_KNIGHT)
    p.tick(100)
    check("P PROTO room A: DRIP_N 0, nothing drawn after 100 ticks", drip(p)["n"] == 0 and not drip(p)["drawn"],
          drip(p))
    # ---- T: cost ----------------------------------------------------------------
    p.proto_start = 0
    start(p, master)
    import budget
    budget.PHASES = budget.PHASES + ["drip_tick"]
    stp = budget.Stepper(p)
    for _ in range(300):
        stp.tick()
    stp.close()
    dts = [sp.get("drip_tick", 0) for _, sp in stp.ticks]
    act = [x for x in dts if x > 200]
    print(f"[info] T drip_tick over 300 ticks: max {max(dts)} T, mean {sum(dts) // len(dts)} T, "
          f"mean of the {len(act)} stepping ticks {sum(act) // max(1, len(act))} T; "
          f"tick max {max(t for t, _ in stp.ticks)} T", flush=True)
    check("T drip_tick <= 4,000 T in every tick (300 ticks of a room with a drip)", max(dts) <= 4000, dts)
    # ---- TL: cost in the loaded budget scenarios (4 monsters, casts, live FX) --
    budget.EXTRA_SETUP[:] = [inject_src]
    worst = {}
    for key in LOADED:
        st, _ = budget.run_scenario(p.h, budget.SCENARIOS[key])
        dl = [sp.get("drip_tick", 0) for _, sp in st.ticks]
        fire = [st.ticks[i][1].get("drip_tick", 0) for i in st.cast_ix]
        ft = [sp.get("drip_tick", 0) for _, sp in st.ticks if "probe_act_fire" in sp]
        # SND-2 T5/T6: gate like budget.py: ordinary WORK (ISR time in the window removed)
        # <= the scenario cap, cast work <= CAST_CAP, real (total + PRE_MAX) <= BUDGET
        worst[key] = (max(dl), sum(dl) // len(dl), sum(1 for x in dl if x > 200), max(fire) if fire else 0,
                      max(st.ordinary_t, default=0), max(ft) if ft else 0, max(st.casts_t, default=0),
                      len(st.real_over))
    budget.EXTRA_SETUP[:] = []
    print("[info] TL drip_tick in loaded rooms (max, mean, stepping ticks, max on cast-class ticks, ordinary work max,"
          " max on fire ticks, cast work max, ticks over the real deadline): "
          + "; ".join(f"{k} {v}" for k, v in worst.items()), flush=True)
    caps = {k: (budget.CAP if k in budget.CAP_GATED else budget.BUDGET) for k in LOADED}
    check("TL loaded scenarios (" + ", ".join(LOADED) + ") with a drip next to the fight: drip_tick "
          "<= 5,000 T in every tick, <= 250 T (the early exit, to the next probe) on a fire tick, every tick within its budget.py cap"
          " (work: ordinary / CAST_CAP; real <= budget)",
          max(v[0] for v in worst.values()) <= 5000 and all(v[4] <= caps[k] for k, v in worst.items())
          and all(v[6] <= budget.CAST_CAP and v[7] == 0 for v in worst.values())
          and all(v[5] <= 250 for v in worst.values()), worst)   # the early exit + decor_gate's
                                                                  # own TP_FIRE ret + the panel skip
                                                                  # to the panel_done probe (~190 T)


if __name__ == "__main__":
    sys.exit(main())
