#!/usr/bin/env python3
"""FLOOR1: floor items drawn as their 16x16 icons (game.md §8.11 Q1 rev 2026-10-26;
src/gfx.asm erase_rect .item, src/fi6.asm / fi3.asm glyph cache, src/lowram.asm
fi_cells). PROTO room A, DEBUG_KIT=0 build. The screen is compared with the
model (tests/room_model.py floor_cells: icon quarters + per-type ink over the
T_ITEM0..3 markers; bg_mismatch ignores the drawn sprites' footprints).

  F1  a body walking across an item (full bag: it stays) restores its 4 cells
      pixel-exact on every tick, both screens equal after
  F2  a 3-type room: 3 slots, every item cell == its icon quarter + ink
  F3  the 8-type INVARIANT (manager decision 2026-10-28: a room never holds more than 8
      distinct item types): 8 types in the room, a 9th-type drop (drop_put, a Rat's cheese)
      is REFUSED (no new entry), the 8 drawn items unchanged, also after a rebuild
  F4  a scroll with items in both rooms (A -> B -> A): every cell of the new
      room == the model after each transition
  F5  pickup when the body covers only the item's RIGHT col (c + 1)
  F6  (repro r9tops) 8 types on 9 cols (an apple twice) + a 9th-type drop: refused, the lone
      apple keeps its icon, also after the rebuild
  F7 / F8  the cache rebuilt after the pause / the page: a walk across items
  F9  a stack's top taken (arrows off a bow, bag full) reveals the bow's icon
  F10 footprint edges: storey 0 col 2, storey 1 cols 2 and 27..28
  F11 / F12  a vertical scroll / a teleport arrival into a room with items
  F13 slot exhaustion: 8 slots used, 7 types present: a new type's drop re-marks the
      cache (dp_cap) and gets its own footprint
  F14 (repro reveal) a pile's top (apple on a cheese) taken in a room of 8 types: the cheese
      is revealed with its own slot (no rebuild, no stale icon), also after a full redraw
  F15 a boss unique with the room at 8 types DISPLACES the first food / ammo / potion type
      (every entry of it, one on a pile: the pile's next item shows): the unique lands, 8 types,
      no mismatch, also after a pause and after a page rebuild
  F16 a unique with 7 types displaces nothing
  F17 (BOW-ICON) the bow shows its own icon: alone, in the generator's pile (bundle entry first, the
      bow LAST = the cell shows the last live entry) and not the arrow's; arrows alone = the arrow icon,
      a dagger alone = the dagger icon (the three glyphs differ)
Run: ZRCP_PORT=<port> python3 tests/floor1.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.argv = [sys.argv[0], "999"]               # keep game.py's item filter inert
import game  # noqa: E402
import room_model  # noqa: E402
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, EF_ACTIVE, EF_PLAYER, EF_LEFT  # noqa: E402

S1 = S["FL_S1"]
Y1 = game.Y1
TYPES = ("IT_F_APPLE", "IT_P_MANA", "IT_A_CHAIN", "IT_S_FEAR", "IT_C_MIGHT", "IT_BOOK", "IT_H_HOOD")
COLS = (8, 11, 14, 17, 20, 27)


def w16(v):
    return [v & 255, v >> 8]


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

        def free(n):
            out = [i for i in range(S["FLOOR_MAX"]) if p.rb(S["FLOOR_LIST"] + 4 * i) == S["FL_EMPTY"]]
            return out[:n]

        def full_bag():
            p.wmem(S["BAG"], [S["IT_W_LONG"], 1, 0] * S["BAG_SLOTS"])

        # ---- F1 a body crossing an item --------------------------------------------
        p.boot(K_KNIGHT)
        p.isolate()
        full_bag()
        i, = free(1)
        p.put_item(i, S1, 14, S["IT_F_APPLE"])
        p.fi_refresh()
        p.place(0, 8, Y1)
        p.settle()
        bad = []

        def each(fr, hero):                        # every tick of the turn: the composed screen
            mm = p.bg_mismatch_in(p.composed_frame())
            if mm:
                bad.append((hero["X"], mm[:3]))
        for _ in range(12):
            p.turn("L", per_tick=each)
            if p.ent(0)["X"] >= 18:
                break
        p.settle()
        mm = p.bg_mismatch() + p.bg_mismatch_in(p.composed_frame())
        check("F1 a body crossing an item: its uncovered cells == the icon on every tick, both screens after",
              not bad and not mm and p.ent(0)["X"] >= 18 and p.rb(S["FLOOR_LIST"] + 4 * i) == S1,
              (bad[:3], mm[:3], p.ent(0)["X"]))

        # ---- F2 a 3-type room -----------------------------------------------------
        p.boot(K_KNIGHT)
        p.isolate()
        for i, (c, t) in zip(free(3), ((8, "IT_F_APPLE"), (14, "IT_P_MANA"), (20, "IT_A_CHAIN"))):
            p.put_item(i, S1, c, S[t])
        p.fi_refresh()
        p.settle()
        used = [b for b in p.z.read_memory(S["FI_TYPE"], S["FI_SLOTS"]) if b != S["FI_NONE"]]
        check("F2 a 3-type room (+ the PROTO potion): 4 slots, every item cell == its icon + ink",
              sorted(used) == sorted([S["IT_POTION"], S["IT_F_APPLE"], S["IT_P_MANA"], S["IT_A_CHAIN"]])
              and not p.bg_mismatch(), (used, p.bg_mismatch()[:4]))

        # ---- F3 the 8-type cap ----------------------------------------------------
        p.boot(K_KNIGHT)
        p.isolate()
        types = TYPES
        cols = COLS
        slots = free(7)
        for k, (i, t) in enumerate(zip(slots, types)):
            rb, c = (S1, cols[k]) if k < 6 else (0, 14)
            p.put_item(i, rb, c, S[t])
        p.fi_refresh()
        p.settle()
        used = [b for b in p.z.read_memory(S["FI_TYPE"], S["FI_SLOTS"]) if b != S["FI_NONE"]]
        def body(cx):                              # a monster slot as the dead body, centre col cx
            kind = p.ent(1)["KIND"]
            w = p.rb(S["kind_tab"] + S["KT_BW"] + kind)
            hb = p.rb(S["kind_tab"] + S["KT_BH"] + kind)
            x = cx - w // 2
            p.set_ent(1, ROOM=p.rb("CUR_ROOM"), X=x, Y=game.stand_y(1, hb), PX=x * 8, PY=game.stand_y(1, hb) * 8)

        def drop(typ, unique=False):               # [uq_fit,] drop_put under slot 1; the new entry or None
            before = free(1)
            pc0 = p.pc()
            code = [0xF3, 0x3A] + w16(S["PORT_7FFD_SHADOW"]) + [0xF5]
            if unique:                             # mon_drop's boss path: uq_fit, then DROP_WHOLE
                code += [0x21] + w16(S["uq_fit"]) + [0xCD] + w16(S["far6"])   # 3F-T8 review: R6
            code += [0x3E, S["BANK_R6"], 0xCD] + w16(S["page_bank"]) + [0xDD, 0x21] + w16(S["P_ENTITIES"] + 32)
            code += [0x3E, typ, 0x11, S["DROP_WHOLE"] if unique else S["DROP_NEAR"], 1, 0xCD] + w16(S["drop_put"])
            code += [0xF1, 0xCD] + w16(S["restore_page"]) + [0xFB]
            ok = p.run_stub(code, org=S["LOWRAM_END_3B"])
            p.z.cmd("set-register PC=%d" % pc0)
            p.set_ent(1, ROOM=game.NOWHERE)
            p.settle(4)
            new = [i for i in before if p.rb(S["FLOOR_LIST"] + 4 * i) != S["FL_EMPTY"]]
            return ok, (list(p.z.read_memory(S["FLOOR_LIST"] + 4 * new[0], 4)) if new else None)

        def live():                                # [(index, col, type, storey)] of CUR_ROOM
            fl = list(p.z.read_memory(S["FLOOR_LIST"], 128))
            return [(i, fl[4 * i + 1], fl[4 * i + 2], fl[4 * i] >> 7) for i in range(S["FLOOR_MAX"])
                    if fl[4 * i] != S["FL_EMPTY"] and fl[4 * i] & S["FL_ROOM_MASK"] == p.rb("CUR_ROOM")]

        body(3)
        before = live()
        ok, fe = drop(S["IT_F_CHEESE"])
        mm = p.bg_mismatch()
        p.fi_refresh()                             # = pause resume / page / entry
        p.settle()
        check("F3 8 distinct types (7 + the potion): a 9th-type drop (cheese) is refused (no entry), "
              "the room unchanged and == the model, also after a rebuild",
              ok and len(used) == 8 and fe is None and live() == before and not mm and not p.bg_mismatch(),
              (ok, used, fe, mm[:4], p.bg_mismatch()[:4]))

        # ---- F4 scroll with items in both rooms -----------------------------------
        p.boot(K_KNIGHT)
        p.isolate()
        a, b, c = free(3)
        p.put_item(a, S1, 10, S["IT_F_APPLE"])
        p.put_item(b, S1, 20, S["IT_S_FEAR"])
        p.wmem(S["FLOOR_LIST"] + 4 * c, [1 | S1, 12, S["IT_C_MIGHT"], 1])   # room B (not built yet)
        p.fi_refresh()
        p.place(0, 28, Y1)
        res = []
        for key, room in (("L", 1), ("H", 0)):
            t0 = p.rw("TURN_COUNTER")
            p.hold(key)
            for _ in range(200):
                p.tick()
                if p.rb("CUR_ROOM") == room and p.rw("TURN_COUNTER") != t0 and p.idle():
                    break
            p.release()
            p.settle()
            res.append((p.rb("CUR_ROOM"), p.bg_mismatch()[:4]))
            if key == "L":
                p.place(0, 1, Y1)
                p.settle()
        check("F4 A -> B -> A with items in both rooms: each new room == the model (icons + inks)",
              res == [(1, []), (0, [])], res)

        # ---- F5 pickup by the right col -------------------------------------------
        p.boot(K_KNIGHT)
        p.isolate()
        i, = free(1)
        p.put_item(i, S1, 14, S["IT_F_PEAR"])
        p.fi_refresh()
        bw = p.rb(S["kind_tab"] + S["KT_BW"] + K_KNIGHT)
        p.place(0, 15 + 1, Y1, flags=EF_ACTIVE | EF_PLAYER | EF_LEFT)   # body 16..18
        p.settle()
        p.turn("H")                                # one step left: body 15..17 covers c + 1 only
        p.settle()
        x = p.ent(0)["X"]
        taken = p.rb(S["FLOOR_LIST"] + 4 * i) == S["FL_EMPTY"]
        check("F5 a body covering only the item's right col (c + 1) picks it up; the cells then T_AIR",
              x == 15 and x <= 15 < x + bw and taken and not p.bg_mismatch(), (x, taken, p.bg_mismatch()[:4]))

        # ---- F6 (repro r9tops) 8 types on 9 cols, a 9th-type drop: refused ----------
        def eight(extra_last=False):
            p.boot(K_KNIGHT)
            p.isolate()
            idx = free(8)
            for k, (i, t) in enumerate(zip(idx, types)):
                rb, c = (S1, cols[k]) if k < 6 else (0, 14)
                p.put_item(i, rb, c, S[t])
            return idx
        idx = eight()
        p.put_item(idx[7], 0, 22, S["IT_F_APPLE"])  # the 8th slot index: a 2nd, lone apple (8 types)
        p.fi_refresh()
        p.settle()
        body(4)
        ok, fe = drop(S["IT_F_CHEESE"])
        mm = p.bg_mismatch()
        p.fi_refresh()
        p.settle()
        check("F6 (r9) 8 types on 9 cols (the apple twice): a cheese drop is refused, every icon incl. "
              "the lone apple == the model, also after a rebuild",
              ok and fe is None and not mm and not p.bg_mismatch(), (ok, fe, mm[:4], p.bg_mismatch()[:4]))

        # ---- F7 / F8 the cache rebuilt after the pause and after the page ----------
        def cross_after(tag, open_close):
            p.boot(K_KNIGHT)
            p.isolate()
            full_bag()
            for i, (c, t) in zip(free(2), ((14, "IT_F_APPLE"), (20, "IT_W_LONG"))):
                p.put_item(i, S1, c, S[t])
            p.fi_refresh()
            p.place(0, 10, Y1)
            p.settle()
            open_close()
            p.settle(3)
            bad = []

            def each(fr, hero):
                mm = p.bg_mismatch_in(p.composed_frame())
                if mm:
                    bad.append((hero["X"], mm[:3]))
            for _ in range(12):
                p.turn("L", per_tick=each)
                if p.ent(0)["X"] >= 22:
                    break
            p.settle()
            check(f"F{tag}: after it, a walk across both items restores them from the rebuilt cache",
                  not bad and not p.bg_mismatch() and p.ent(0)["X"] >= 22, (bad[:3], p.ent(0)["X"]))

        def pause():
            p.hold("CAPS", "SPACE")
            p.until(lambda: p.rb("PAUSED") == 1, 60)
            p.release()
            p.tick(4)
            p.hold("SPACE")                        # FIRE on RESUME
            p.tick(3)
            p.release()
            p.until(lambda: p.rb("PAUSED") == 0, 200)

        def page():
            p.tap("I")
            p.until(lambda: p.rb("PAGE_OPEN") == 1, 20)
            p.tick(4)
            p.tap("I")
            p.until(lambda: p.rb("PAGE_OPEN") == 0, 20)
        cross_after("7 pause", pause)
        cross_after("8 page", page)

        # ---- F9 a stack's top picked up reveals the type under it -----------------
        p.boot(K_KNIGHT)
        p.isolate()
        full_bag()
        p.wb("ARROWS", 0)
        b, a = free(2)
        p.put_item(b, S1, 14, S["IT_BOW"])         # under (lower index)
        p.put_item(a, S1, 14, S["IT_ARROW"], 6)    # the top
        p.fi_refresh()
        p.place(0, 10, Y1)
        p.settle()
        top0 = p.bg_tables()[4].get((14, 16))
        for _ in range(3):
            p.turn("L")
        p.place(0, 6, Y1)
        p.settle(3)
        cells = p.bg_tables()[4]
        check("F9 arrows (top) taken off a bow pile, the bag full: the col now shows the bow's icon",
              p.rb("ARROWS") == 6 and p.rb(S["FLOOR_LIST"] + 4 * a) == S["FL_EMPTY"] and cells.get((14, 16)) != top0
              and not p.bg_mismatch(), (p.rb("ARROWS"), p.bg_mismatch()[:4]))

        # ---- F10 the footprint edges: storey 0, col 2, col 28 ----------------------
        p.boot(K_KNIGHT)
        p.isolate()
        for i, (rb, c, t) in zip(free(3), ((0, 2, "IT_F_PEAR"), (S1, 2, "IT_S_SLEEP"), (S1, 27, "IT_C_FIRE"))):
            p.put_item(i, rb, c, S[t])
        p.fi_refresh()
        p.settle()
        check("F10 items at the edges (storey 0 col 2, storey 1 cols 2 and 27..28) == their icons",
              not p.bg_mismatch(), p.bg_mismatch()[:4])

        # ---- F11 / F12 a vertical scroll and a teleport arrival with items ---------
        def do_exit(kind, dest=None, col=None):
            p.wb("EXIT_KIND", kind)
            if dest is not None:
                p.wb("EXIT_DEST", dest)
            if col is not None:
                p.wb("EXIT_COL", col)
            pc0 = p.pc()
            code = [0xF3, 0x3E, kind, 0x21] + w16(S["do_exit"]) + [0xCD] + w16(S["far7"]) + [0xFB, 0x00, 0x18, 0xFE]
            stub = S["LOWRAM_END_3B"]
            end = stub + len(code) - 3
            p.wmem(stub, code)
            p.z.cmd("set-breakpoint 3 PC=%d" % end)
            p.z.cmd("set-register PC=%d" % stub)
            for _ in range(40):
                p.z.cmd("run 50000000")
                if p.pc() == end:
                    break
            ok = p.pc() == end
            p.z.cmd("set-breakpoint 3")
            p.z.cmd("set-register PC=%d" % pc0)
            p.settle(3)
            return ok

        def seed_rooms(n):
            k = 0
            for i, r in zip(free(n), [r for r in range(9) if r != p.rb("CUR_ROOM")]):
                p.wmem(S["FLOOR_LIST"] + 4 * i, [r | S1, 12, S[types[k % len(types)]], 1])
                p.wmem(S["FLOOR_LIST"] + 4 * free(1)[0], [r, 16, S[types[(k + 1) % len(types)]], 1])
                k += 2
        p.boot(K_KNIGHT)
        p.isolate()
        vert, r0, d0 = [], None, None
        for r in range(9):                         # any PROTO room with a vertical exit: the scroll
            d = S["ROOM_DESC"] + 16 * r            # replaces all 18 rows, so it starts from there
            ex = p.rb(d + S["RD_EXITS"])
            if p.rb(d + S["RD_FLAGS"]) & 1 and ex & (S["RDX_D"] | S["RDX_U"]):
                vert = [(S["EX_DOWN"], 3, "RD_DNCOL")] if ex & S["RDX_D"] else [(S["EX_UP"], -3, "RD_UPCOL")]
                r0, d0 = r, d
                break
        if r0 is not None:
            p.wb("CUR_ROOM", r0)
            p.set_ent(0, ROOM=r0)
        if vert:
            kind, dd, colk = vert[0]
            seed_rooms(4)
            ok = do_exit(kind, r0 + dd, p.rb(d0 + S[colk]))
            check("F11 a vertical scroll into a room with items: the new room == the model",
                  ok and p.rb("CUR_ROOM") == r0 + dd and not p.bg_mismatch(), (ok, p.rb("CUR_ROOM"), p.bg_mismatch()[:4]))
        else:
            print("[info] F11: the start room has no vertical exit", flush=True)
        p.boot(K_KNIGHT)
        p.isolate()
        seed_rooms(4)
        ok = do_exit(S["EX_TELE"])
        check("F12 a teleport arrival (room_show): the new room's items == the model",
              ok and not p.bg_mismatch(), (ok, p.rb("CUR_ROOM"), p.bg_mismatch()[:4]))

        # ---- F13 slot exhaustion: stale slots, then a new type's drop ---------------
        idx = eight()
        p.fi_refresh()
        p.settle()
        p.wmem(S["FLOOR_LIST"] + 4 * idx[1], [0xFF] * 4)     # the Mana leaves the room (a pickup
        p.wmem(S["ROOM_MAP"] + 15 * 32 + 11, [0, 0])          # elsewhere): its slot stays used
        p.wmem(S["ROOM_MAP"] + 16 * 32 + 11, [0, 0])
        pc0 = p.pc()                               # its cells redrawn as air next render
        p.run_stub([0xF3, 0x01, 11, 15, 0x11, 2, 2, 0xCD] + w16(S["queue_damage"]) + [0xFB], org=S["LOWRAM_END_3B"])
        p.z.cmd("set-register PC=%d" % pc0)
        p.settle(2)
        sl = 1
        kind = p.ent(sl)["KIND"]
        w = p.rb(S["kind_tab"] + S["KT_BW"] + kind)
        hb = p.rb(S["kind_tab"] + S["KT_BH"] + kind)
        x = 3 - w // 2                             # centre col 3: a free footprint at 2..4
        p.set_ent(sl, ROOM=p.rb("CUR_ROOM"), X=x, Y=game.stand_y(1, hb), PX=x * 8, PY=game.stand_y(1, hb) * 8)
        ent = free(1)[0]
        pc0 = p.pc()
        ok = p.run_stub([0xF3, 0x3A] + w16(S["PORT_7FFD_SHADOW"]) + [0xF5, 0x3E, S["BANK_R6"], 0xCD]
                        + w16(S["page_bank"]) + [0xDD, 0x21] + w16(S["P_ENTITIES"] + 32 * sl)
                        + [0x3E, S["IT_F_CHEESE"], 0x11, S["DROP_NEAR"], 1, 0xCD] + w16(S["drop_put"])
                        + [0xF1, 0xCD] + w16(S["restore_page"]) + [0xFB], org=S["LOWRAM_END_3B"])
        p.z.cmd("set-register PC=%d" % pc0)
        fe = list(p.z.read_memory(S["FLOOR_LIST"] + 4 * ent, 4))
        p.set_ent(sl, ROOM=game.NOWHERE)
        p.settle(4)
        check("F13 8 slots used but 7 types present: a new type's drop rebuilds the cache and gets its own "
              "footprint (not a pile), drawn",
              ok and fe[2] == S["IT_F_CHEESE"] and fe[1] not in cols and not p.bg_mismatch(),
              (ok, fe, p.bg_mismatch()[:4]))
        # ---- F14 (repro reveal) a pile's top taken in a room of 8 types ------------
        cls = ("IT_P_MANA", "IT_A_CHAIN", "IT_S_FEAR", "IT_C_MIGHT", "IT_BOOK")   # + cheese, apple, the PROTO potion = 8
        p.boot(K_KNIGHT)
        p.isolate()
        fs = free(9)
        p.put_item(fs[0], S1, 8, S["IT_F_CHEESE"])  # the bottom of the pile
        p.put_item(fs[1], S1, 8, S["IT_F_APPLE"])   # its top
        for k, t in enumerate(cls):
            rb, c = (S1, (14, 17, 20, 27)[k]) if k < 4 else (0, 8)
            p.put_item(fs[2 + k], rb, c, S[t])
        p.put_item(fs[8], 0, 22, S["IT_F_APPLE"])   # the apple also elsewhere (8 types, 9 cols)
        p.fi_refresh()
        p.settle()
        p.place(0, 11, Y1, flags=EF_ACTIVE | EF_PLAYER | EF_LEFT)
        p.settle()
        for _ in range(3):
            p.turn("H")
            p.settle()
            if p.rb(S["FLOOR_LIST"] + 4 * fs[1]) == S["FL_EMPTY"]:
                break
        taken = p.rb(S["FLOOR_LIST"] + 4 * fs[1]) == S["FL_EMPTY"]
        p.place(0, 2, Y1, flags=EF_ACTIVE | EF_PLAYER | EF_LEFT)
        p.settle(4)
        mm = p.bg_mismatch()                       # the cheese shows at col 8 (its own slot)
        pc0 = p.pc()                               # a full redraw from the map + cache, no rebuild
        p.run_stub([0xF3, 0x3A] + w16(S["PORT_7FFD_SHADOW"]) + [0xF5, 0x01, 0, 0, 0x11, S["PLAY_ROWS"], 32, 0xCD]
                   + w16(S["fi_cells"]) + [0xCD] + w16(S["present_full"]) + [0xF1, 0xCD] + w16(S["restore_page"])
                   + [0xFB], org=S["LOWRAM_END_3B"])
        p.z.cmd("set-register PC=%d" % pc0)
        p.settle()
        check("F14 (reveal) the apple (top) taken off a cheese pile in a room of 8 types: the cheese shows, "
              "== the model after a full redraw",
              taken and not mm and not p.bg_mismatch(), (taken, mm[:4], p.bg_mismatch()[:4]))

        # ---- F15 / F16 a boss unique at 8 types / at 7 -----------------------------
        def unique_case(tag, nine):
            p.boot(K_KNIGHT)
            p.isolate()
            if nine:                                # 7 types + the PROTO potion (entry 0, col 28) = 8; a 2nd
                idx = free(7)                       # potion on top of the apple pile (col 8): the victim
                for k, (i, t) in enumerate(zip(idx, types)):          # type = the potion (first in list
                    rb, c = (S1, cols[k]) if k < 6 else (0, 14)       # order), the pile then shows the apple
                    p.put_item(i, rb, c, S[t])
                p.put_item(free(8)[7], S1, cols[0], S["IT_POTION"])
            else:
                for i, (rb, c, t) in zip(free(3), ((S1, 8, "IT_F_APPLE"), (S1, 14, "IT_S_FEAR"), (0, 20, "IT_BOOK"))):
                    p.put_item(i, rb, c, S[t])
            p.fi_refresh()
            p.settle()
            before = live()
            tset = {t for _, _, t, _ in before}
            vic = next((t for _, _, t, _ in before if t != S["IT_KEY"] and 1 <= t <= S["IT_P_CURE"]), None)
            body(4)
            ok, fe = drop(S["IT_H_KING"], unique=True)
            after = live()
            fe = next((e for e in after if e[2] == S["IT_H_KING"]), None)       # (the freed entry may be reused)
            kept = [e for e in before if e[2] != vic]
            if nine:
                good = (len(tset) == 8 and vic == S["IT_POTION"] and fe is not None
                        and [e for e in after if e[2] != S["IT_H_KING"]] == kept
                        and len({t for _, _, t, _ in after}) == 8)
            else:
                good = (len(tset) <= 7 and fe is not None and sorted(
                    e for e in after if e[2] != S["IT_H_KING"]) == sorted(before))
            mm = p.bg_mismatch()
            return ok, good, mm, (vic, before, after, fe)

        ok, good, mm, info = unique_case("15", True)
        check("F15 a unique at 8 types displaces the first food / ammo / potion type (all its entries, one on a "
              "pile); it lands, 8 types, the screen == the model", ok and good and not mm,
              (ok, good, mm[:4], info))
        p.fi_refresh()
        p.settle()
        check("F15 ... also after the rebuild (fi_full)", not p.bg_mismatch(), p.bg_mismatch()[:4])
        pause()
        p.settle(3)
        check("F15 ... after a pause", not p.bg_mismatch(), p.bg_mismatch()[:4])
        page()
        p.settle(3)
        check("F15 ... after a page", not p.bg_mismatch(), p.bg_mismatch()[:4])
        ok, good, mm, info = unique_case("16", False)
        check("F16 a unique with 3 types (no displacement): nothing destroyed, it lands, == the model",
              ok and good and not mm, (ok, good, mm[:4], info))
        p.fi_refresh()
        p.settle()
        check("F16 ... also after the rebuild", not p.bg_mismatch(), p.bg_mismatch()[:4])
        # ---- F17 the bow's floor icon (bow + 6-arrow bundle in one cell) --------------
        def glyph_of(t):
            sl = p.rb(S["FI_TSLOT"] + S[t])
            return bytes(p.z.read_memory(S["FI_GLY"] + 32 * sl, 32)) if sl < S["FI_SLOTS"] else None

        def one(entries, col=14):
            p.boot(K_KNIGHT)
            p.isolate()
            for i, (t, q) in zip(free(len(entries)), entries):
                p.put_item(i, S1, col, S[t], q)
            p.fi_refresh()
            p.settle()
            ul = p.rb(S["FI_CELL"] + 256 + 0xE0 + col)
            return ul // 32, p.bg_mismatch()

        sb, mb = one([("IT_BOW", 1)])
        gb = glyph_of("IT_BOW")
        sa, ma = one([("IT_ARROW", 6)])
        ga = glyph_of("IT_ARROW")
        sd, md = one([("IT_DAGGER", 2)])
        gd = glyph_of("IT_DAGGER")
        check("F17 bow / arrows / dagger alone: three distinct icons, screen == model",
              gb and ga and gd and len({gb, ga, gd}) == 3 and not (mb or ma or md), (mb[:2], ma[:2], md[:2]))
        sp, mp = one([("IT_ARROW", 6), ("IT_BOW", 1)])          # the generator's order
        gp = glyph_of("IT_BOW")
        check("F17 bundle + bow in one cell (bow last): the cell shows the bow's slot + glyph, == the model",
              gp == gb and p.rb(S["FI_TYPE"] + sp) == S["IT_BOW"] and not mp, (sp, mp[:4]))
    print(f"floor1: {len(fails)} failed" + (f": {fails}" if fails else ""), flush=True)
    return 1 if fails or h.failures else 0


if __name__ == "__main__":
    sys.exit(main())
