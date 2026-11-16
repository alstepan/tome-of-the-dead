#!/usr/bin/env python3
"""LARGER-D T8: the level-key runtime (larger_depths.md §2.1 rev 2 / rev 3, §6; src/lockl.asm).
PROTO rooms A-D (LVL_DEPTH poked to 1 where the engine pickup must run), plus one generated game.

  K1  first entry into LVL_KEYROOM (B): LF_KEYC, LVL_KEYROOM := ROOM_NONE, "YOU FIND A CYAN KEY",
      panel key cell (30, 19) attr $45 + the key glyph; a re-entry gives nothing
  K2  first entry into LVL_KEYROOM2 (A): LF_KEYM, "YOU FIND A MAGENTA KEY", panel $EB (both held);
      the bag page: CYAN KEY (row 1, $45) and MAGENTA KEY (row 3, $43) at col 23
  K3  bump a locked door without its key: 0 turns, THE DOOR IS LOCKED; the other colour's key = no key
  K4  bump with the key: 1 turn, EG_LOCK cleared + open (jambs), the key used up, YOU UNLOCK THE DOOR,
      panel attr back to 0
  K5  far-side bolt (EG_NEARR: the near room is the other one): 1 turn, opens keyless, no line,
      keys untouched; a near-side bump of the same lock stays locked (K3)
  K6  monsters: an opener (Goblin) is refused by a locked door from either side (try_step)
  K7  plate: a locked closed door = 1 T_DOOR_LOCK cell (plank row DOOR_PLATE_DY) in its key colour on
      the screen AND in the bank-7 attr shadow, room_show (cyan / magenta) and through a vertical
      scroll (B -> C, the D|C door magenta); the room map == room_model; ink only (paper 0: no clash)
  K8  generated D1 (fixed seed): every lock's EG_NEARR == its start side (flood of G without it);
      after keys are held, level_enter (descend) clears LF_KEYC / LF_KEYM and the panel key cell
Run: ZRCP_PORT=<port> python3 tests/lock8.py [K1 ...]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_argv = sys.argv[1:]
import world  # noqa: E402  (keeps game.py's item filter inert; helpers)
import game  # noqa: E402
import room_model  # noqa: E402
from game_lib import (Harness, S, EMU_ARGS, attr_at, cell_bytes, stand_y, GS_PLAYING,  # noqa: E402
                      K_KNIGHT, EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT)
from world import text6, log_row, w16, bank7, map_structure  # noqa: E402

ONLY = {a.upper() for a in _argv if not a.startswith("--")}
LINK, DOOR, OPEN, LOCK = S["EG_LINK"], S["EG_DOOR"], S["EG_OPEN"], S["EG_LOCK"]
LOCKC, NEARR = S["EG_LOCKC"], S["EG_NEARR"]
KEYC, KEYM = S["LF_KEYC"], S["LF_KEYM"]
E_AB = S["EDGE_TAB"] + S["EDGE_AB"]
E_DC = S["EDGE_TAB"] + S["EDGE_DC"]
KEY_GLY = bytes([0x00, 0x60, 0x90, 0x9F, 0x65, 0x00, 0x00, 0x00])   # panel_icons.asm label_key
PLATE_ROW1 = S["STOREY_ROWS"] + 2 + S["DOOR_PLATE_DY"]               # storey-1 plate row (14)
SLOT_GOBLIN = 3
NOWHERE = 7


def want(tag):
    return not ONLY or tag in ONLY


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = world.W(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, cond, True):
                fails.append(tag)
                if detail:
                    print(f"[detail] {tag}: {detail}", flush=True)

        def hero():
            return p.ent(0)

        def ingame(code, tag):
            pc0 = p.pc()
            ok = p.run_stub([0xF3] + code + [0xFB], org=S["LOWRAM_END_3B"])
            p.z.cmd("set-register PC=%d" % pc0)
            check(f"{tag}: stub ran", ok, "")

        def drain():
            p.until(lambda: p.rb("LOG_QN") == 0 and p.rb("PANEL_DIRTY") == 0, 200)
            p.settle(3)

        def newest():
            return log_row(p.composed_frame(), 23)

        def marker():
            ingame([0x3E, S["TX_DESCEND"], 0xCD] + w16(S["msg_push"]), "marker")
            drain()

        p.boot(K_KNIGHT)
        kw, kh = game.body(p, K_KNIGHT)
        y1 = stand_y(1, kh)
        HERO_R = EF_ACTIVE | EF_PLAYER

        def walk(key, dest):
            p.turn(key)
            p.until(lambda: p.rb("CUR_ROOM") == dest and p.idle() and p.rb("GAME_STATE") == GS_PLAYING, 600)
            drain()

        def a_to_b():
            p.isolate()
            p.place(0, 32 - 1 - kw, y1, flags=HERO_R)
            walk("L", 1)

        def b_to_a():
            p.isolate()
            p.place(0, 1, y1, flags=HERO_R | EF_LEFT)
            walk("H", 0)

        def key_cell(fr):
            return attr_at(fr, S["DEPTH_COL"], S["ICON_ROW"] + 1), bytes(cell_bytes(fr, S["DEPTH_COL"], S["ICON_ROW"] + 1))

        # ---------------- K1 / K2 pickup + panel + bag ----------------------
        if want("K1") or want("K2"):
            p.boot(K_KNIGHT)
            p.isolate()
            fr = p.composed_frame()
            check("K0 panel key cell blank at the start (attr 0, no glyph)",
                  key_cell(fr) == (0, bytes(8)), key_cell(fr))
            p.wb("LVL_DEPTH", 1)
            p.wb("LVL_KEYROOM", 1)
            p.wb("LVL_KEYROOM2", 0xFF)
            a_to_b()
            fr = p.composed_frame()
            check("K1 entry into B: LF_KEYC, LVL_KEYROOM := ROOM_NONE",
                  (p.rb("LVL_FLAGS") & (KEYC | KEYM), p.rb("LVL_KEYROOM")) == (KEYC, 0xFF),
                  (hex(p.rb("LVL_FLAGS")), p.rb("LVL_KEYROOM")))
            check("K1 log: YOU FIND A CYAN KEY", log_row(fr, 23) == text6("YOU FIND A CYAN KEY"), "")
            check("K1 panel key cell: glyph, attr $45 (composed + displayed)",
                  key_cell(fr) == (S["ATTR_KEY_C"], KEY_GLY) and key_cell(p.frame()) == key_cell(fr),
                  (key_cell(fr), key_cell(p.frame())))
            marker()
            b_to_a()
            a_to_b()
            check("K1 second entry into B: no second key line, flags unchanged",
                  newest() == text6(dict(world.STRINGS)["descend"]) and p.rb("LVL_FLAGS") & (KEYC | KEYM) == KEYC,
                  hex(p.rb("LVL_FLAGS")))
            p.wb("LVL_KEYROOM2", 0)
            b_to_a()
            fr = p.composed_frame()
            check("K2 entry into A (LVL_KEYROOM2): LF_KEYM too, LVL_KEYROOM2 := ROOM_NONE",
                  (p.rb("LVL_FLAGS") & (KEYC | KEYM), p.rb("LVL_KEYROOM2")) == (KEYC | KEYM, 0xFF),
                  (hex(p.rb("LVL_FLAGS")), p.rb("LVL_KEYROOM2")))
            check("K2 log: YOU FIND A MAGENTA KEY", log_row(fr, 23) == text6("YOU FIND A MAGENTA KEY"), "")
            check("K2 panel key cell: both held = $EB (FLASH)", key_cell(fr) == (S["ATTR_KEY_CM"], KEY_GLY), key_cell(fr))
            # the bag page (I): one line per held key at col 23, rows 1 / 3, in its colour
            p.hold("I")
            for _ in range(60):
                p.tick()
                if p.rb("PAGE_OPEN") == 1 and p.pc() == S["select_tick"]:
                    break
            p.release()
            p.tick(6)
            fr = p.frame()
            x0 = S["PG_KEY_COL"] * 8
            cy = log_row(fr, 1, S["PG_KEY_COL"], 9) == text6("CYAN KEY", 0, 9)
            mg = log_row(fr, 3, S["PG_KEY_COL"], 9) == text6("MAGENTA KEY", 0, 9)
            at = (attr_at(fr, S["PG_KEY_COL"], 1), attr_at(fr, S["PG_KEY_COL"], 3))
            check(f"K2 bag: CYAN KEY row 1 / MAGENTA KEY row 3 at x {x0}, attrs $45 / $43",
                  cy and mg and at == (S["ATTR_KEY_C"], S["ATTR_KEY_M"]), (cy, mg, at))
            p.tap("I")
            p.tick(10)

        # ---------------- K3 / K4 / K5 / K6 bump --------------------------
        if any(want(k) for k in ("K3", "K4", "K5", "K6")):
            p.boot(K_KNIGHT)
            p.isolate()
            p.place(0, 27, y1, flags=HERO_R)
            p.turn("C")                                   # close the A|B door
            p.wb(E_AB, LINK | DOOR | LOCK)               # cyan, near = A (the hero's room)
            p.wb("LVL_FLAGS", (p.rb("LVL_FLAGS") & 0x3F) | KEYM)   # only the other colour
            marker()
            check("K3 locked (cyan), magenta key only: no turn", p.no_turn("L"), "")
            drain()
            check("K3 THE DOOR IS LOCKED, door + keys unchanged",
                  newest() == text6("THE DOOR IS LOCKED") and p.rb(E_AB) == LINK | DOOR | LOCK
                  and p.rb("LVL_FLAGS") & (KEYC | KEYM) == KEYM, (p.rb(E_AB), hex(p.rb("LVL_FLAGS"))))
            p.wb("LVL_FLAGS", p.rb("LVL_FLAGS") & 0x3F)
            check("K3 no key at all: no turn", p.no_turn("L"), "")
            # K4: with the cyan key
            p.wb("LVL_FLAGS", (p.rb("LVL_FLAGS") & 0x3F) | KEYC)
            p.wb("PANEL_DIRTY", p.rb("PANEL_DIRTY") | 0x80)
            drain()
            t0 = p.rw("TURN_COUNTER")
            ok = p.turn("L")
            drain()
            m = p.z.read_memory(S["ROOM_MAP"], 576)
            jambs = all(m[r * 32 + 31] == S["T_DOOR_JAMB_R"] for r in range(S["STOREY_ROWS"] + 2, 2 * S["STOREY_ROWS"] - 1))
            check("K4 with the key: 1 turn, LOCK cleared + OPEN, hero stays, jambs",
                  (ok, p.rw("TURN_COUNTER") - t0, p.rb(E_AB), hero()["X"], jambs) == (True, 1, LINK | DOOR | OPEN, 27, True),
                  (ok, p.rw("TURN_COUNTER") - t0, p.rb(E_AB), hero()["X"], jambs))
            check("K4 the key is used up, YOU UNLOCK THE DOOR, panel key attr 0",
                  p.rb("LVL_FLAGS") & (KEYC | KEYM) == 0 and newest() == text6("YOU UNLOCK THE DOOR")
                  and key_cell(p.composed_frame())[0] == 0, (hex(p.rb("LVL_FLAGS")), key_cell(p.composed_frame())))
            sh = bank7(p, S["SHADOW_ATTR"] + PLATE_ROW1 * 32 + 31, 1)[0]
            check("K4 the old plate cell's shadow attr = plank $06", sh == S["ATTR_PLANK"], hex(sh))
            # K5: far-side bolt
            p.turn("C")
            p.wb(E_AB, LINK | DOOR | LOCK | LOCKC | NEARR)   # magenta, near = B: A is the far side
            marker()
            t0 = p.rw("TURN_COUNTER")
            ok = p.turn("L")
            drain()
            check("K5 far side, no key: 1 turn, opens (LOCK cleared), no line, keys untouched",
                  (ok, p.rw("TURN_COUNTER") - t0, p.rb(E_AB) & (LOCK | OPEN), newest() == text6(dict(world.STRINGS)["descend"]),
                   p.rb("LVL_FLAGS") & (KEYC | KEYM)) == (True, 1, OPEN, True, 0),
                  (ok, p.rw("TURN_COUNTER") - t0, hex(p.rb(E_AB)), hex(p.rb("LVL_FLAGS"))))
            # K6: an opener never passes a lock, near or far side
            p.turn("C")
            p.place(0, 10, y1, flags=HERO_R)
            for tag, eg in (("near", LINK | DOOR | LOCK), ("far", LINK | DOOR | LOCK | NEARR)):
                p.wb(E_AB, eg)
                p.place(SLOT_GOBLIN, 27, stand_y(1, 4), room=0, flags=EF_ACTIVE | EF_HOSTILE)
                r = world_stub_step(p, check, SLOT_GOBLIN, 1)
                check(f"K6 Goblin (opener) vs a locked door, {tag} side: refused, door unchanged",
                      (r, p.rb(E_AB), p.ent(SLOT_GOBLIN)["X"]) == (0, eg, 27), (r, hex(p.rb(E_AB))))
            p.set_ent(SLOT_GOBLIN, ROOM=NOWHERE)

        # ---------------- K7 plate ------------------------------------------
        if want("K7"):
            p.boot(K_KNIGHT)
            p.isolate()
            for tag, eg, at in (("cyan", LINK | DOOR | LOCK, S["ATTR_KEY_C"]),
                                ("magenta", LINK | DOOR | LOCK | LOCKC, S["ATTR_KEY_M"])):
                p.wb(E_AB, eg)
                p.place(0, 10, y1, flags=HERO_R)
                ingame([0x3E, 0, 0xCD] + w16(S["room_show"]) + [0xCD] + w16(S["vis_reset"])
                       + [0xCD] + w16(S["present_full"]), "K7 room_show A")
                p.settle(3)
                m = p.z.read_memory(S["ROOM_MAP"], 576)
                col = [m[r * 32 + 31] for r in range(S["STOREY_ROWS"] + 2, S["STOREY_ROWS"] + 8)]
                want_col = [S["T_DOOR_R"]] * 6
                want_col[S["DOOR_PLATE_DY"]] = S["T_DOOR_LOCK"]
                fr, fc = p.frame(), p.composed_frame()
                sh = bank7(p, S["SHADOW_ATTR"] + PLATE_ROW1 * 32 + 31, 1)[0]
                others = {attr_at(fc, 31, r) for r in range(S["STOREY_ROWS"] + 2, S["STOREY_ROWS"] + 8) if r != PLATE_ROW1}
                check(f"K7 {tag} (room_show A): one plate cell, map == room_model",
                      col == want_col and map_structure(p, 0) == [], (col, map_structure(p, 0)[:3]))
                check(f"K7 {tag}: plate attr {at:#x} on both screens + the shadow, other planks $06, paper 0",
                      (attr_at(fr, 31, PLATE_ROW1), attr_at(fc, 31, PLATE_ROW1), sh, others) == (at, at, at, {S["ATTR_PLANK"]})
                      and at & 0x38 == 0, (attr_at(fr, 31, PLATE_ROW1), attr_at(fc, 31, PLATE_ROW1), sh, others))
                bad = p.screen_vs_map(f"K7 {tag}")
                check(f"K7 {tag}: screens == ROOM_MAP (room_model.plate_cells: the plate's own attr)", not bad, bad[:3])
            # through the vertical scroll: the D|C door (C's left door, storey 1) magenta
            p.wb(E_AB, LINK | DOOR | OPEN)
            ingame([0x3E, 0, 0xCD] + w16(S["room_show"]) + [0xCD] + w16(S["vis_reset"])
                   + [0xCD] + w16(S["present_full"]), "K7 room_show A (open)")
            p.wb(E_DC, LINK | DOOR | LOCK | LOCKC)
            a_to_b()
            p.isolate()
            p.place(0, 24, y1, flags=HERO_R)
            walk("J", 4)
            fr, fc = p.frame(), p.composed_frame()
            sh = bank7(p, S["SHADOW_ATTR"] + PLATE_ROW1 * 32 + 1, 1)[0]
            m = p.z.read_memory(S["ROOM_MAP"], 576)
            check("K7 scroll B -> C: C's left door plate (1, 14) magenta on both screens + shadow, map == model",
                  (attr_at(fr, 1, PLATE_ROW1), attr_at(fc, 1, PLATE_ROW1), sh, m[PLATE_ROW1 * 32 + 1]) ==
                  (S["ATTR_KEY_M"],) * 3 + (S["T_DOOR_LOCK"],) and map_structure(p, 4) == [],
                  (attr_at(fr, 1, PLATE_ROW1), attr_at(fc, 1, PLATE_ROW1), sh, m[PLATE_ROW1 * 32 + 1], map_structure(p, 4)[:3]))

        # ---------------- K8 generated level: EG_NEARR + descend reset -------
        if want("K8"):
            M = 0x4B1D
            p.proto_start = 0
            try:
                p.load()
                p.wait_state(S["GS_SELECT"])
                p.wb("seed_fixed", 1)
                p.z.cmd("write-memory %d %d %d" % (S["seed_value"], M & 255, M >> 8))
                p.hold("1")
                p.wait_state(GS_PLAYING)
                p.release()
                p.settle(3)
                for d in (1, 2):
                    blk = room_model.read_block(p)
                    bad = nearr_errors(blk)
                    nl = sum(1 for e in range(S["EDGES_H"]) if blk[S["EDGE_TAB"] - room_model.BASE + e] & LOCK)
                    check(f"K8 D{d}: {nl} lock(s), each EG_NEARR == its start side", nl >= 1 and not bad, bad)
                    p.wb("LVL_FLAGS", p.rb("LVL_FLAGS") | KEYC | KEYM)
                    p.wb("PANEL_DIRTY", p.rb("PANEL_DIRTY") | 0x80)
                    drain()
                    nd = d + 1
                    pc0 = p.pc()
                    ok = p.run_stub([0xF3, 0x3E, nd, 0x11] + w16(S["TX_DESCEND"]) + [0xCD] + w16(S["level_enter"]) + [0xFB],
                                    org=S["LOWRAM_END_3B"])
                    p.z.cmd("set-register PC=%d" % pc0)
                    p.settle(4)
                    drain()
                    kc = key_cell(p.composed_frame())
                    check(f"K8 descend D{d} -> D{nd}: keys cleared, key rooms fresh, panel key cell blank",
                          ok and p.rb("LVL_DEPTH") == nd and p.rb("LVL_FLAGS") & (KEYC | KEYM) == 0
                          and p.rb("LVL_KEYROOM") != 0xFF and kc[0] == 0,
                          (ok, p.rb("LVL_DEPTH"), hex(p.rb("LVL_FLAGS")), p.rb("LVL_KEYROOM"), kc))
            finally:
                p.proto_start = 1
    print(f"lock8: {'FAIL ' + str(len(fails)) if fails else 'PASS'} {fails}", flush=True)
    return 1 if fails else 0


def nearr_errors(blk):
    """Every locked edge: EG_NEARR set iff the start-side room is the right one (flood of G = RD_EXITS
    from LVL_START without that edge)."""
    base = room_model.BASE
    st = blk[S["LVL_START"] - base]
    errs = []
    for e in range(S["EDGES_H"]):
        eb = blk[S["EDGE_TAB"] - base + e]
        if not eb & LOCK:
            continue
        a = e + e // 2                           # the edge's left room (3 wide)
        seen, todo = {st}, [st]
        while todo:
            r = todo.pop()
            ex = room_model.field(blk, r, "RD_EXITS")
            for bit, dn in ((S["RDX_L"], -1), (S["RDX_R"], 1), (S["RDX_U"], -3), (S["RDX_D"], 3)):
                n = r + dn
                if not ex & bit or {r, n} == {a, a + 1} or n in seen:
                    continue
                seen.add(n)
                todo.append(n)
        if (a in seen) == (a + 1 in seen):
            errs.append((e, "not a bridge"))
        elif bool(eb & NEARR) != (a + 1 in seen):
            errs.append((e, hex(eb)))
    return errs


def world_stub_step(p, check, slot, dx):
    """try_step(IX = slot, D = dx) in place (as world.py W9's stub_step); CF -> MSG_BUF ($FF)."""
    pc0 = p.pc()
    code = ([0xCD] + w16(S["build_live"]) + [0xCD] + w16(S["cache_player"]) +
            [0x3E, slot, 0x32] + w16(S["ACT_SLOT"]) +
            [0x3E, 0, 0x32] + w16(S["YIELD_FLAG"]) +
            [0xDD, 0x21] + w16(S["P_ENTITIES"] + 32 * slot) +
            [0x16, dx & 0xFF, 0x1E, 0, 0xCD] + w16(S["try_step"]) +
            [0x9F, 0x32] + w16(S["MSG_BUF"]))
    ok = p.run_stub(code, org=S["LOWRAM_END_3B"])
    check(f"K6 stub (slot {slot}) ran", ok, "")
    p.z.cmd("set-register PC=%d" % pc0)
    return p.rb("MSG_BUF")


if __name__ == "__main__":
    sys.exit(main())
