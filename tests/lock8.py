#!/usr/bin/env python3
"""LARGER-D T8 + KEY-POLISH: the level-key runtime (larger_depths.md §2.1 rev 2 / rev 3, §6; src/lockl.asm).
PROTO rooms A-D (LVL_DEPTH poked to 1 where the engine pickup must run), plus one generated game.

  K1  KEY-POLISH floor key: an IT_KEY entry in LVL_KEYROOM (B) is drawn on entry (key icon, $45) and the
      entry grants NOTHING; standing on it picks it up: LF_KEYC, LVL_KEYROOM kept (W21-FIX: DECOR2 reads it), the entry
      FL_EMPTY, the cell no longer a marker, "YOU FIND A CYAN KEY", SFX_PICKUP, KEY-PANEL: the cyan panel
      key cell (24-25, 21) attr $45 + the key glyph, the magenta one (27-28, 21) blank; a re-entry gives nothing
  K2  the IT_KEY entry in LVL_KEYROOM2 (A) is magenta ($43); its pickup: LF_KEYM, "YOU FIND A MAGENTA KEY",
      KEY-PANEL both key cells drawn ($45 / $43, (30, 19) blank: no "both" state); the bag page: CYAN KEY ($45) at col 6 and MAGENTA KEY ($43) at col 16 on
      row 3, each once; row 1 (the counters, ARROWS 12) holds no key text (the T8 "2 CYAN KEYS" bug: the
      key line sat right of "ARROWS 12" and read as a count)
  K3  bump a locked door without its key: 0 turns, THE DOOR IS LOCKED, SFX_LAND; the other colour's key = no key;
      KEY-PANEL magenta only: (27-28, 21) drawn, (24-25, 21) blank
  K4  bump with the key: 1 turn, EG_LOCK cleared + open (jambs), the key used up, YOU UNLOCK THE DOOR,
      both panel key cells blank, the bag page shows no key line any more; KEY-PANEL: both held, a magenta
      unlock blanks (27-28, 21) only, then a cyan unlock blanks (24-25, 21)
  K5  far-side bolt (EG_NEARR: the near room is the other one): 1 turn, opens keyless, no line,
      keys untouched; a near-side bump of the same lock stays locked (K3)
  K6  monsters: an opener (Goblin) is refused by a locked door from either side (try_step)
  K7  KEY-POLISH: a locked closed door = 1 T_DOOR_LOCK plate cell (plank row DOOR_PLATE_DY) and ALL its
      12 plank cells in its key colour on the screen AND in the bank-7 attr shadow, room_show (cyan /
      magenta) and through a vertical scroll (B -> C, the D|C door magenta); an ordinary door $06;
      the room map == room_model; ink only (paper 0: no clash)
  K9  DOOR-FRAME (user playtest 2026-11-16): the 2 arch cells (row 9s+1) of a locked door in its key colour
      on both screens + the shadow (room_show cyan / magenta, the B -> C scroll), the lintel (T_BRICK row
      9s) never; back to $06 after the key unlock (K4) and the far-side bolt (K5); a sealed door and an
      ordinary closed door: arch + planks $06
  KM  KEY-PANEL for the Wizard: cyan only, magenta only, both, none (16x8 icons, the gap col blank)
  K8  generated D1 (fixed seed): every lock's EG_NEARR == its start side (flood of G without it); each
      key room holds one IT_KEY floor entry and no key is held at the start; after keys are held,
      level_enter (descend) clears LF_KEYC / LF_KEYM and the panel key cell
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
                      K_KNIGHT, K_WIZARD, EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT)
from world import text6, log_row, w16, bank7, map_structure  # noqa: E402
from game_lib import frame_png  # noqa: E402
PNG_DIR = os.environ.get("WZ_BUILD_DIR") or os.path.join(os.path.dirname(HERE), "build")

ONLY = {a.upper() for a in _argv if not a.startswith("--")}
LINK, DOOR, OPEN, LOCK = S["EG_LINK"], S["EG_DOOR"], S["EG_OPEN"], S["EG_LOCK"]
LOCKC, NEARR = S["EG_LOCKC"], S["EG_NEARR"]
KEYC, KEYM = S["LF_KEYC"], S["LF_KEYM"]
E_AB = S["EDGE_TAB"] + S["EDGE_AB"]
E_DC = S["EDGE_TAB"] + S["EDGE_DC"]
# KEY-PANEL 16x8 icon = assets/gfx/icons/floor_key.grid rows 8..15, (left cell, right cell)
_FK = [ln for ln in open(os.path.join(os.path.dirname(HERE), "assets/gfx/icons/floor_key.grid")).read().splitlines()
       if ln and not ln.startswith("#")][8:16]
KEY_GLY = tuple(bytes(int(r[h * 8:h * 8 + 8].replace("#", "1").replace(".", "0"), 2) for r in _FK) for h in (0, 1))


def keys_want_(c, m):
    """KEY-PANEL want: cyan icon cols 24-25, blank gap 26, magenta 27-28; an unheld icon is blank with the
    panel clear's attr ATTR_HUD (the goldens keep their hash)."""
    blank = (S["ATTR_HUD"], bytes(8))
    icon = lambda on, at: [(at, KEY_GLY[0]), (at, KEY_GLY[1])] if on else [blank, blank]  # noqa: E731
    return tuple(icon(c, S["ATTR_KEY_C"]) + [blank] + icon(m, S["ATTR_KEY_M"]))


PLATE_ROW1 = S["STOREY_ROWS"] + 2 + S["DOOR_PLATE_DY"]               # storey-1 plate row (14)
SLOT_GOBLIN = 3
NOWHERE = 7
KEY_COL = 10                                                        # the PROTO floor keys' col (storey 1)
KEY_SLOT = S["FLOOR_MAX"] - 1                                        # their FLOOR_LIST entry (B: 31, A: 30)
SPY = S["LOWRAM_END_3B"] + 48                                        # the sfx_req spy (past the stubs' bytes)
SPY_REC = SPY + 12
PLANK_TOP1 = S["STOREY_ROWS"] + S["DOOR_PLANK_DY"]                   # storey-1 plank rows 11..16
ARCH_ROW1 = S["STOREY_ROWS"] + S["DOOR_ARCH_DY"]                     # DOOR-FRAME: storey-1 arch row (10)
LINTEL_ROW1 = S["STOREY_ROWS"]                                       # storey-1 lintel (T_BRICK) row (9)


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

        def spy_on():
            """KEY-POLISH: sfx_req -> jp SPY (ld (SPY_REC), a; the 3 bytes it replaced; jp sfx_req + 3)."""
            a = S["sfx_req"]
            org = list(p.z.read_memory(a, 3))
            p.wmem(SPY, [0x32] + w16(SPY_REC) + org + [0xC3] + w16(a + 3))
            p.wb(SPY_REC, 0)
            p.wmem(a, [0xC3] + w16(SPY))
            return org

        def spy_off(org):
            p.wmem(S["sfx_req"], org)

        def floor_key(slot, room, col=KEY_COL):
            p.wmem(S["FLOOR_LIST"] + slot * S["FL_STRIDE"], [room | S["FL_S1"], col, S["IT_KEY"], 1])

        def key_icon_ok(fr, at, col=KEY_COL):
            cells = [(bytes(cell_bytes(fr, col + h, PLATE_ROW1 + 1 + r)), attr_at(fr, col + h, PLATE_ROW1 + 1 + r))
                     for h in (0, 1) for r in (0, 1)]
            want_ = [(room_model.icon_cell(S["IT_KEY"], h, r), at) for h in (0, 1) for r in (0, 1)]
            return cells == want_, cells

        def bag_rows():
            p.hold("I")
            for _ in range(60):
                p.tick()
                if p.rb("PAGE_OPEN") == 1 and p.pc() == S["select_tick"]:
                    break
            p.release()
            p.tick(6)
            fr = p.frame()
            p.tap("I")
            p.tick(10)
            return fr

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

        def show_a(tag):
            ingame([0x3E, 0, 0xCD] + w16(S["room_show"]) + [0xCD] + w16(S["vis_reset"])
                   + [0xCD] + w16(S["present_full"]), tag)
            p.settle(3)

        def tri(cells):
            """{(displayed, composed, bank-7 shadow) attr} over (col, row) cells."""
            fr, fc = p.frame(), p.composed_frame()
            sh = bank7(p, S["SHADOW_ATTR"], 768)
            return {(attr_at(fr, c, r), attr_at(fc, c, r), sh[r * 32 + c]) for c, r in cells}

        ARCH_R = [(30, ARCH_ROW1), (31, ARCH_ROW1)]
        LINTEL_R = [(30, LINTEL_ROW1), (31, LINTEL_ROW1)]

        def key_cell(fr):
            """KEY-PANEL: (attr, glyph) of the 5 cells KEY_PAN_COL.. on row STAT_ROW (cyan 2, gap, magenta 2)."""
            return tuple((attr_at(fr, S["KEY_PAN_COL"] + i, S["STAT_ROW"]),
                          bytes(cell_bytes(fr, S["KEY_PAN_COL"] + i, S["STAT_ROW"]))) for i in range(S["KEY_PAN_W"]))

        def keys_want(c, m):
            return keys_want_(c, m)

        def old_cell(fr):
            return attr_at(fr, S["DEPTH_COL"], S["ICON_ROW"] + 1), bytes(cell_bytes(fr, S["DEPTH_COL"], S["ICON_ROW"] + 1))

        # ---------------- K1 / K2 floor key pickup + panel + bag -------------
        if want("K1") or want("K2"):
            p.boot(K_KNIGHT)
            p.isolate()
            fr = p.composed_frame()
            check("K0 both panel key cells blank at the start (no glyph, ATTR_HUD)",
                  key_cell(fr) == keys_want(0, 0), key_cell(fr))
            p.wb("LVL_DEPTH", 1)
            p.wb("LVL_KEYROOM", 1)
            p.wb("LVL_KEYROOM2", 0xFF)
            floor_key(KEY_SLOT, 1)
            a_to_b()
            fr = p.composed_frame()
            ok, cells = key_icon_ok(fr, S["ATTR_KEY_C"])
            check("K1 entry into B: no key granted (flags, LVL_KEYROOM unchanged), the floor key drawn: icon, $45",
                  ok and p.rb("LVL_FLAGS") & (KEYC | KEYM) == 0 and p.rb("LVL_KEYROOM") == 1,
                  (cells[:1], hex(p.rb("LVL_FLAGS")), p.rb("LVL_KEYROOM")))
            org = spy_on()
            p.place(0, KEY_COL - 1, y1, flags=HERO_R)
            p.turn("WAIT")
            sfx = p.rb(SPY_REC)
            drain()
            spy_off(org)
            fr = p.composed_frame()
            ent = p.z.read_memory(S["FLOOR_LIST"] + KEY_SLOT * 4, 1)[0]
            mk = p.z.read_memory(S["ROOM_MAP"] + (PLATE_ROW1 + 2) * 32 + KEY_COL, 1)[0]
            check("K1 standing on it: LF_KEYC, LVL_KEYROOM kept (W21-FIX), entry FL_EMPTY, no marker left",
                  (p.rb("LVL_FLAGS") & (KEYC | KEYM), p.rb("LVL_KEYROOM"), ent, mk < S["T_ITEM0"]) == (KEYC, 1, 0xFF, True),
                  (hex(p.rb("LVL_FLAGS")), p.rb("LVL_KEYROOM"), ent, mk))
            check("K1 log: YOU FIND A CYAN KEY", log_row(fr, 23) == text6("YOU FIND A CYAN KEY"), "")
            check("K1 the pickup sound: SFX_PICKUP", sfx == S["SFX_PICKUP"], hex(sfx))
            check("K1 cyan only: (24-25, 21) glyph + $45, (27-28, 21) blank (composed + displayed)",
                  key_cell(fr) == keys_want(1, 0) and key_cell(p.frame()) == key_cell(fr),
                  (key_cell(fr), key_cell(p.frame())))
            marker()
            b_to_a()
            a_to_b()
            check("K1 second entry into B: no second key line, flags unchanged",
                  newest() == text6(dict(world.STRINGS)["descend"]) and p.rb("LVL_FLAGS") & (KEYC | KEYM) == KEYC,
                  hex(p.rb("LVL_FLAGS")))
            p.wb("LVL_KEYROOM2", 0)
            floor_key(KEY_SLOT - 1, 0)
            b_to_a()
            ok, cells = key_icon_ok(p.composed_frame(), S["ATTR_KEY_M"])
            check("K2 entry into A (LVL_KEYROOM2): the floor key magenta ($43), nothing granted",
                  ok and p.rb("LVL_FLAGS") & (KEYC | KEYM) == KEYC, (cells[:1], hex(p.rb("LVL_FLAGS"))))
            p.place(0, KEY_COL - 1, y1, flags=HERO_R)
            p.turn("WAIT")
            drain()
            fr = p.composed_frame()
            check("K2 its pickup: LF_KEYM too, LVL_KEYROOM2 kept (W21-FIX)",
                  (p.rb("LVL_FLAGS") & (KEYC | KEYM), p.rb("LVL_KEYROOM2")) == (KEYC | KEYM, 0),
                  (hex(p.rb("LVL_FLAGS")), p.rb("LVL_KEYROOM2")))
            check("K2 log: YOU FIND A MAGENTA KEY", log_row(fr, 23) == text6("YOU FIND A MAGENTA KEY"), "")
            check("K2 both held: both key cells drawn ($45 / $43), the old (30, 19) cell blank (composed + displayed)",
                  key_cell(fr) == keys_want(1, 1) and key_cell(p.frame()) == key_cell(fr) and old_cell(fr) == (0, bytes(8)),
                  (key_cell(fr), old_cell(fr)))
            if not ONLY or want("K2"):
                frame_png(p.frame(), os.path.join(PNG_DIR, "keypanel_both.png"), 3)
            # the bag page (I): row 3, CYAN KEY col 6 / MAGENTA KEY col 16, each once; row 1 = counters only
            p.wb("ARROWS", 12)
            fr = bag_rows()
            c0, c1 = S["PG_KEY_COL"], S["PG_KEY_COL"] + S["PG_KEY_W"] + 1
            cy = log_row(fr, 3, c0, 9) == text6("CYAN KEY", 0, 9)
            mg = log_row(fr, 3, c1, 9) == text6("MAGENTA KEY", 0, 9)
            at = (attr_at(fr, c0, 3), attr_at(fr, c1, 3))
            r1 = [bytes(cell_bytes(fr, c, 1)) for c in range(22, 32)]
            check(f"K2 bag: CYAN KEY (col {c0}) / MAGENTA KEY (col {c1}) on row 3, attrs $45 / $43",
                  cy and mg and at == (S["ATTR_KEY_C"], S["ATTR_KEY_M"]), (cy, mg, at))
            check("K2 bag (2-key regression): row 1 right of ARROWS 12 is empty (no key line beside a count)",
                  all(x == bytes(8) for x in r1), [i + 22 for i, x in enumerate(r1) if x != bytes(8)])

        # ---------------- KM KEY-PANEL for the Wizard (the panel row 21 is the other hero's) ----
        if want("KM"):
            p.boot(K_WIZARD)
            p.isolate()
            for c, m in ((1, 0), (0, 1), (1, 1), (0, 0)):
                p.wb("LVL_FLAGS", (p.rb("LVL_FLAGS") & 0x3F) | (KEYC if c else 0) | (KEYM if m else 0))
                p.wb("PANEL_DIRTY", p.rb("PANEL_DIRTY") | S["PD_DEPTH"])
                marker()
                fr = p.composed_frame()
                check(f"KM Wizard cyan {c} magenta {m}: 16x8 icons (24-25 / 27-28, 21), gap 26 blank (composed + displayed)",
                      key_cell(fr) == keys_want(c, m) and key_cell(p.frame()) == key_cell(fr), key_cell(fr))
            p.wb("LVL_FLAGS", p.rb("LVL_FLAGS") | KEYC | KEYM)
            p.wb("PANEL_DIRTY", p.rb("PANEL_DIRTY") | S["PD_DEPTH"])
            marker()
            frame_png(p.frame(), os.path.join(PNG_DIR, "keypanel_both_wizard.png"), 3)

        # ---------------- K3 / K4 / K5 / K6 bump --------------------------
        if any(want(k) for k in ("K3", "K4", "K5", "K6", "K9")):
            p.boot(K_KNIGHT)
            p.isolate()
            p.place(0, 27, y1, flags=HERO_R)
            p.turn("C")                                   # close the A|B door
            p.wb(E_AB, LINK | DOOR | LOCK)               # cyan, near = A (the hero's room)
            p.wb("LVL_FLAGS", (p.rb("LVL_FLAGS") & 0x3F) | KEYM)   # only the other colour
            p.wb("PANEL_DIRTY", p.rb("PANEL_DIRTY") | S["PD_DEPTH"])
            marker()
            fr = p.composed_frame()
            check("K3 magenta only: (27-28, 21) glyph + $43, (24-25, 21) blank (composed + displayed)",
                  key_cell(fr) == keys_want(0, 1) and key_cell(p.frame()) == key_cell(fr), key_cell(fr))
            org = spy_on()
            check("K3 locked (cyan), magenta key only: no turn", p.no_turn("L"), "")
            sfx = p.rb(SPY_REC)
            spy_off(org)
            drain()
            check("K3 the bump sound: SFX_LAND", sfx == S["SFX_LAND"], hex(sfx))
            check("K3 THE DOOR IS LOCKED, door + keys unchanged",
                  newest() == text6("THE DOOR IS LOCKED") and p.rb(E_AB) == LINK | DOOR | LOCK
                  and p.rb("LVL_FLAGS") & (KEYC | KEYM) == KEYM, (p.rb(E_AB), hex(p.rb("LVL_FLAGS"))))
            p.wb("LVL_FLAGS", p.rb("LVL_FLAGS") & 0x3F)
            check("K3 no key at all: no turn", p.no_turn("L"), "")
            # K4: with the cyan key
            p.wb("LVL_FLAGS", (p.rb("LVL_FLAGS") & 0x3F) | KEYC)
            p.wb("PANEL_DIRTY", p.rb("PANEL_DIRTY") | S["PD_DEPTH"])
            show_a("K9 room_show A (locked cyan)")
            g = tri(ARCH_R)
            check("K9 locked cyan: arch (30/31, 10) $45 on both screens + shadow", g == {(S["ATTR_KEY_C"],) * 3}, g)
            drain()
            t0 = p.rw("TURN_COUNTER")
            ok = p.turn("L")
            drain()
            p.settle(2)
            g = tri(ARCH_R)
            check("K9 after the key unlock: arch back to $06 on both screens + shadow", g == {(S["ATTR_PLANK"],) * 3}, g)
            bad = p.screen_vs_map("K9 key unlock")
            check("K9 after the key unlock: screens == ROOM_MAP (no key colour left)", not bad, bad[:3])
            m = p.z.read_memory(S["ROOM_MAP"], 576)
            jambs = all(m[r * 32 + 31] == S["T_DOOR_JAMB_R"] for r in range(S["STOREY_ROWS"] + 2, 2 * S["STOREY_ROWS"] - 1))
            check("K4 with the key: 1 turn, LOCK cleared + OPEN, hero stays, jambs",
                  (ok, p.rw("TURN_COUNTER") - t0, p.rb(E_AB), hero()["X"], jambs) == (True, 1, LINK | DOOR | OPEN, 27, True),
                  (ok, p.rw("TURN_COUNTER") - t0, p.rb(E_AB), hero()["X"], jambs))
            check("K4 the key is used up, YOU UNLOCK THE DOOR, both panel key cells blank",
                  p.rb("LVL_FLAGS") & (KEYC | KEYM) == 0 and newest() == text6("YOU UNLOCK THE DOOR")
                  and key_cell(p.composed_frame()) == keys_want(0, 0), (hex(p.rb("LVL_FLAGS")), key_cell(p.composed_frame())))
            sh = bank7(p, S["SHADOW_ATTR"] + PLATE_ROW1 * 32 + 31, 1)[0]
            check("K4 the old plate cell's shadow attr = plank $06", sh == S["ATTR_PLANK"], hex(sh))
            fr = bag_rows()
            r3 = [bytes(cell_bytes(fr, c, 3)) for c in range(S["PG_KEY_COL"], S["PG_KEY_COL"] + 2 * S["PG_KEY_W"] + 1)]
            check("K4 the used key is gone from the bag page (row 3 empty)", all(x == bytes(8) for x in r3), "")
            # KEY-PANEL: both held; unlock magenta (only (27-28, 21) goes), then cyan (both blank)
            p.wb("LVL_FLAGS", p.rb("LVL_FLAGS") | KEYC | KEYM)
            p.wb("PANEL_DIRTY", p.rb("PANEL_DIRTY") | S["PD_DEPTH"])
            drain()
            fr = p.composed_frame()
            check("K4 both held: both key cells drawn", key_cell(fr) == keys_want(1, 1) and key_cell(p.frame()) == key_cell(fr),
                  key_cell(fr))
            for tag, eg, left in (("magenta", LINK | DOOR | LOCK | LOCKC, (1, 0)), ("cyan", LINK | DOOR | LOCK, (0, 0))):
                p.turn("C")
                p.wb(E_AB, eg)                           # near = A (the hero's room): only the key opens it
                ok = p.turn("L")
                drain()
                fr = p.composed_frame()
                check(f"K4 {tag} unlock: door open, that key cell blank, the other as held {left}",
                      ok and p.rb(E_AB) & (LOCK | OPEN) == OPEN and key_cell(fr) == keys_want(*left)
                      and key_cell(p.frame()) == key_cell(fr), (ok, hex(p.rb(E_AB)), key_cell(fr)))
            # K5: far-side bolt
            p.turn("C")
            p.wb(E_AB, LINK | DOOR | LOCK | LOCKC | NEARR)   # magenta, near = B: A is the far side
            show_a("K9 room_show A (locked magenta)")
            g = tri(ARCH_R + [(c, r) for r in range(PLANK_TOP1, PLANK_TOP1 + S["DOOR_PLANK_H"]) for c in (30, 31)])
            check("K9 locked magenta (far side): arch + planks $43 on both screens + shadow", g == {(S["ATTR_KEY_M"],) * 3}, g)
            marker()
            t0 = p.rw("TURN_COUNTER")
            ok = p.turn("L")
            drain()
            check("K5 far side, no key: 1 turn, opens (LOCK cleared), no line, keys untouched",
                  (ok, p.rw("TURN_COUNTER") - t0, p.rb(E_AB) & (LOCK | OPEN), newest() == text6(dict(world.STRINGS)["descend"]),
                   p.rb("LVL_FLAGS") & (KEYC | KEYM)) == (True, 1, OPEN, True, 0),
                  (ok, p.rw("TURN_COUNTER") - t0, hex(p.rb(E_AB)), hex(p.rb("LVL_FLAGS"))))
            p.settle(2)
            g = tri(ARCH_R)
            check("K9 after the far-side bolt: arch back to $06 on both screens + shadow", g == {(S["ATTR_PLANK"],) * 3}, g)
            bad = p.screen_vs_map("K9 bolt")
            check("K9 after the far-side bolt: screens == ROOM_MAP", not bad, bad[:3])
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
        if want("K7") or want("K9"):
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
                cells = [(c, r) for r in range(PLANK_TOP1, PLANK_TOP1 + S["DOOR_PLANK_H"]) for c in (30, 31)]
                sh = bank7(p, S["SHADOW_ATTR"], 768)
                got = {(attr_at(fr, c, r), attr_at(fc, c, r), sh[r * 32 + c]) for c, r in cells}
                check(f"K7 {tag} (room_show A): one plate cell, map == room_model",
                      col == want_col and map_structure(p, 0) == [], (col, map_structure(p, 0)[:3]))
                check(f"K7 {tag}: all 12 plank cells attr {at:#x} on both screens + the shadow, paper 0",
                      got == {(at, at, at)} and at & 0x38 == 0, got)
                g = tri(ARCH_R)
                check(f"K9 {tag} (room_show): arch (30/31, 10) {at:#x} on both screens + shadow", g == {(at,) * 3}, g)
                g = tri(LINTEL_R)
                check(f"K9 {tag}: lintel (T_BRICK, row 9) not tinted", all(at not in x for x in g), g)
                mm = p.z.read_memory(S["ROOM_MAP"], 576)
                left = {attr_at(fc, c, r) for r in range(S["PLAY_ROWS"]) for c in (0, 1)
                        if mm[r * 32 + c] in (S["T_DOOR_L"], S["T_DOOR_R"])}
                check(f"K7 {tag}: any other closed door keeps $06", left <= {S["ATTR_PLANK"]}, left)
                bad = p.screen_vs_map(f"K7 {tag}")
                check(f"K7 {tag}: screens == ROOM_MAP (room_model.plate_cells: the plate's own attr)", not bad, bad[:3])
            # DOOR-FRAME: a sealed door and an ordinary closed door keep $06 (arch + planks)
            for tag, eg in (("sealed", LINK | DOOR | S["EG_SEAL"]), ("ordinary", LINK | DOOR)):
                p.wb(E_AB, eg)
                show_a(f"K9 room_show A ({tag})")
                g = tri(ARCH_R + [(c, r) for r in range(PLANK_TOP1, PLANK_TOP1 + S["DOOR_PLANK_H"]) for c in (30, 31)])
                check(f"K9 {tag} door: arch + planks $06 on both screens + shadow", g == {(S["ATTR_PLANK"],) * 3}, g)
                bad = p.screen_vs_map(f"K9 {tag}")
                check(f"K9 {tag}: screens == ROOM_MAP", not bad, bad[:3])
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
            sh = bank7(p, S["SHADOW_ATTR"], 768)
            m = p.z.read_memory(S["ROOM_MAP"], 576)
            cells = [(c, r) for r in range(PLANK_TOP1 - 1, PLANK_TOP1 + S["DOOR_PLANK_H"]) for c in (0, 1)]
            got = {(attr_at(fr, c, r), attr_at(fc, c, r), sh[r * 32 + c]) for c, r in cells}   # + DOOR-FRAME arch
            check("K7/K9 scroll B -> C: C's left door (plate (1, 14), all 12 planks + the 2 arch cells) magenta on both screens + shadow, "
                  "map == model",
                  got == {(S["ATTR_KEY_M"],) * 3} and m[PLATE_ROW1 * 32 + 1] == S["T_DOOR_LOCK"] and map_structure(p, 4) == [],
                  (got, m[PLATE_ROW1 * 32 + 1], map_structure(p, 4)[:3]))

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
                    fl = p.z.read_memory(S["FLOOR_LIST"], 128)
                    kr = [k for k in (p.rb("LVL_KEYROOM"), p.rb("LVL_KEYROOM2")) if k != 0xFF]
                    keys = sorted(fl[4 * i] & 15 for i in range(32) if fl[4 * i] != 0xFF and fl[4 * i + 2] == S["IT_KEY"])
                    check(f"K8 D{d}: one IT_KEY floor entry per key room {kr}, none held",
                          keys == sorted(kr) and len(kr) == nl and p.rb("LVL_FLAGS") & (KEYC | KEYM) == 0,
                          (keys, kr, hex(p.rb("LVL_FLAGS"))))
                    p.wb("LVL_FLAGS", p.rb("LVL_FLAGS") | KEYC | KEYM)
                    p.wb("PANEL_DIRTY", p.rb("PANEL_DIRTY") | S["PD_DEPTH"])
                    drain()
                    nd = d + 1
                    pc0 = p.pc()
                    ok = p.run_stub([0xF3, 0x3E, nd, 0x11] + w16(S["TX_DESCEND"]) + [0xCD] + w16(S["level_enter"]) + [0xFB],
                                    org=S["LOWRAM_END_3B"])
                    p.z.cmd("set-register PC=%d" % pc0)
                    p.settle(4)
                    drain()
                    kc = key_cell(p.composed_frame())
                    kc = (0,) if kc == keys_want(0, 0) else (1, kc)
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
