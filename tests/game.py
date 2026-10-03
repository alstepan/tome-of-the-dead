#!/usr/bin/env python3
"""PROTO playability checklist (docs/design/prototype.md §11.3, items 1-40).

Drives build/wazhack.sna in ZEsarUX over ZRCP. Fixed seed, INPUT_REPEAT=0
(edge-triggered), ANIM_FREEZE=1 unless a check needs idle motion. Scenario setup
uses pokes of the entity array (layout in docs/memory-map.md) where walking there
would only add time; the long no-softlock walkthrough (#37) plays the real game.

Usage:
    python3 tests/game.py                  # run everything
    python3 tests/game.py --update-golden  # refresh game_select / game_start
    python3 tests/game.py 1 2 30           # run only the listed items
"""
import hashlib
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from game_lib import (Harness, Proto, S, EMU_ARGS, holes, floor_band_ok, attr_at,  # noqa: E402
                       cell_bytes, TILE_ATTRS, FLASH_ATTRS, KIND_ATTR, split_frame, frame_png,
                       stand_y, is_standing, storey_of, item_row, STOREY_ROWS, STOREY_COUNT,
                       PLAY_ROWS, FLOOR_ROWS, MAP_LEN,
                       GS_PLAYING, GS_WIN, GS_DEAD, GS_SELECT, GS_TRANSITION,
                       EF_LEFT, EF_PENDING, EF_ACTIVE, EF_HOSTILE,
                       K_KNIGHT, K_WIZARD, K_SKELETON, K_GOBLIN, K_RAT,
                       K_BAT, K_SLIME, K_GHOST, ROOM_A, ROOM_C, ROOM_D)
import room_model  # noqa: E402

GOLDEN_DIR = os.path.join(HERE, "golden")
UPDATE = "--update-golden" in sys.argv
PNG_DIR = sys.argv[sys.argv.index("--png") + 1] if "--png" in sys.argv else None
ONLY = {int(a) for a in sys.argv[1:] if a.isdigit()}

# B3B-3 (2 storeys x 9 rows): every coordinate below comes from the geometry
# helpers (game_lib, read from the .sym). Hero / skeleton (h 6), goblin /
# ghost (h 4), rat / bat / slime (h 2) standing rows:
Y1, Y0 = stand_y(1, 6), stand_y(0, 6)          # hero: bottom storey 11, top 2
G1, G0 = stand_y(1, 4), stand_y(0, 4)          # goblin 13 / 4
R1, R0 = stand_y(1, 2), stand_y(0, 2)          # rat / slime 15 / 6

# Scenarios not ported to 2x9 by B3B-3: {id: reason}. B3B-4 ports them; a
# skipped id is reported, never silently dropped.
SKIP = {}

FID = {k[4:]: v for k, v in S.items() if k.startswith("FID_")}
SLOT_RAT, SLOT_SLIME, SLOT_GOBLIN, SLOT_BATB, SLOT_SKC, SLOT_GHOST, SLOT_SKD, SLOT_BATD = range(1, 9)
NOWHERE = 7                                   # a room id that never exists


_orig_expect = Harness.expect


def _expect(self, name, got, want):
    if not isinstance(got, (int, str)) or not isinstance(want, (int, str)):
        got, want = str(got), str(want)
    return _orig_expect(self, name, got, want)


Harness.expect = _expect


_SKIPPED = set()


def want(n):
    if n in SKIP and (not ONLY or n in ONLY):
        if n not in _SKIPPED:
            _SKIPPED.add(n)
            print(f"[SKIP] {n}: {SKIP[n]}", flush=True)
        return False
    return not ONLY or n in ONLY


def bitrev(b):
    return int(f"{b:08b}"[::-1], 2)


def ladder_segs(p, room):
    """[(col, s)] ladder segments of room `room` (B3B-8: the 6 shaft / ladder
    col bytes of its ROOM_DESC entry, tests/room_model.py)."""
    import room_model
    return room_model.segments(room_model.read_block(p), room)


def body(p, kind):
    """(w, h) from kind_tab (KT_BW / KT_BH): never hard-coded in tests."""
    kt = S["kind_tab"]
    return p.rb(kt + S["KT_BW"] + kind), p.rb(kt + S["KT_BH"] + kind)


def in_end_box(p, e, segs):
    """Cols of entity e's body inside a ladder-end box of its storey
    (flyer_lcost's test: bottom end of {col,t}, top end of {col,t+1})."""
    w, h_ = body(p, e["KIND"])
    t = storey_of(e["Y"], h_)
    cols = set(range(e["X"], e["X"] + w))
    return sorted(cols & {c + k for c, s in segs if s - t in (0, 1) for k in range(3)})


def art_frame(name):
    import re
    t = open(os.path.join(os.path.dirname(HERE), "assets", "gfx", "sprites", name + ".asm")).read()
    rows = [[int(x, 16) for x in re.findall(r"\$([0-9A-F]{2})", l.split(";")[0])]
            for l in t.split("\n") if "DEFB" in l and "; row" in l]
    w = int(re.search(name + r"_w\s+EQU (\d+)", t).group(1))
    ax = int(re.search(name + r"_ax\s+EQU (\d+)", t).group(1))
    return rows, w, ax


def art_feet_line(name, px, left, bw):
    """256-char pixel line of the frame's bottom row drawn for body px."""
    rows, w, ax = art_frame(name)
    bits = "".join(f"{b:08b}" for b in rows[-1][1::2])
    if left:
        bits = bits[::-1]
        ax = w - ax - bw
    line = ["0"] * 256
    for i, c in enumerate(bits):
        if 0 <= px - ax + i < 256 and c == "1":
            line[px - ax + i] = "1"
    return "".join(line)


def screen_line_bits(frame, y):
    base = ((y & 0xC0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2)
    return "".join(f"{frame[base + c]:08b}" for c in range(32))


def legal_attrs(p):
    kinds = {p.ent(s)["KIND"] for s in range(16) if p.ent(s)["FLAGS"] & EF_ACTIVE}
    return TILE_ATTRS | FLASH_ATTRS | {KIND_ATTR[k] for k in kinds}


def attr_violations(frame, legal):
    return [(c, r, hex(attr_at(frame, c, r))) for r in range(PLAY_ROWS) for c in range(32)
            if attr_at(frame, c, r) not in legal]


GOLDEN_PROTO = []                             # the Proto in use (A7 sync check)


def golden(h, name, data):
    """B3B-3 (plan R4): two hashes per golden, playfield (rows 0-17) and panel
    (rows 18-23), one `play <sha>` / `panel <sha>` line each, so a panel-only
    change (B3B-11) does not invalidate the room goldens and vice versa.
    --png DIR also dumps the screen for a human look before a rebase."""
    if GOLDEN_PROTO:
        GOLDEN_PROTO[0].check_synced(name)
    play, panel = split_frame(bytes(data))
    got = {"play": hashlib.sha256(play).hexdigest(), "panel": hashlib.sha256(panel).hexdigest()}
    path = os.path.join(GOLDEN_DIR, name + ".hash")
    if PNG_DIR:
        os.makedirs(PNG_DIR, exist_ok=True)
        frame_png(bytes(data), os.path.join(PNG_DIR, name + ".png"))
    if UPDATE:
        open(path, "w").write("".join(f"{k} {v}\n" for k, v in got.items()))
        print(f"[golden] wrote {path}")
        return
    try:
        lines = open(path).read().split("\n")
    except FileNotFoundError:
        print(f"[FAIL] golden missing: {path} (run --update-golden)")
        h.failures.append(name)
        return
    ref = dict(l.split() for l in lines if len(l.split()) == 2)
    for k in ("play", "panel"):
        h.expect(f"golden {name} {k}", got[k], ref.get(k, "<old single-hash format>"))


class T(Proto):
    def place(self, slot, x, y, room=None, flags=None):
        kw = dict(X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0)
        if room is not None:
            kw["ROOM"] = room
        if flags is not None:
            kw["FLAGS"] = flags
        self.set_ent(slot, **kw)
        self.settle()

    def bg_tables(self):
        """(ROOM_MAP, TILE_GLYPHS, TILE_ATTRS, ORN_GLYPHS) from memory."""
        z = self.z
        return (z.read_memory(S["ROOM_MAP"], MAP_LEN), z.read_memory(S["TILE_GLYPHS"], S["TILE_IDS"] * 8),
                z.read_memory(S["TILE_ATTRS"], S["TILE_IDS"]), z.read_memory(S["ORN_GLYPHS"], 64))

    def is_bg(self, frame, c, r):
        """Cell (c,r) shows exactly its tile-map background (glyph + attr; B3B-8:
        the row-17 ornament over its floor cells)."""
        g, a = room_model.expected_cell(*self.bg_tables(), c, r)
        return attr_at(frame, c, r) == a and bytes(cell_bytes(frame, c, r)) == g

    def bg_mismatch(self):
        """Cells of rows 0-17 that differ from the tile-map background, outside
        every drawn sprite footprint (transition / erase correctness)."""
        fr = self.frame()
        tabs = self.bg_tables()
        covered = set()
        for s_ in range(16):
            e = self.ent(s_)
            if e["DVIS"] & 1:
                covered |= {(c, r) for c in range(e["DCOL"], e["DCOL"] + e["DCOLS"])
                            for r in range(e["DROW"], e["DROW"] + e["DROWS"])}
        bad = []
        for r in range(PLAY_ROWS):
            for c in range(32):
                if (c, r) in covered:
                    continue
                g, a = room_model.expected_cell(*tabs, c, r)
                if attr_at(fr, c, r) != a or bytes(cell_bytes(fr, c, r)) != g:
                    bad.append((c, r))
        return bad

    def isolate(self, keep=()):
        """Park every monster of the current room in NOWHERE (except keep)."""
        room = self.rb("CUR_ROOM")
        for s in range(1, 16):
            e = self.ent(s)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room and s not in keep:
                self.set_ent(s, ROOM=NOWHERE)
        self.settle()

    def stand_y(self, s, h=6):
        return stand_y(s, h)

    def walk_to(self, x, limit=40):
        for _ in range(limit):
            cur = self.ent(0)["X"]
            if cur == x:
                return True
            if not self.turn("L" if x > cur else "H"):
                self.turn("SPACE")
        return self.ent(0)["X"] == x

    def climb(self, key, limit=20):
        """Climb until standing again (waits if briefly blocked)."""
        moved = False
        for _ in range(limit):
            e = self.ent(0)
            if moved and is_standing(e["Y"], 6):
                return True
            if self.turn(key):
                moved = True
            else:
                self.turn("SPACE")
        return False

    def run_stub(self, code, org=0x6000):
        """Execute raw Z80 `code` at `org` (ROOM_MAP, scratch until the next
        load) up to its final `jr $` (appended here). Unit-tests a routine
        in place; the caller reloads afterwards."""
        code = bytes(code) + b"\x18\xfe"
        self.z.cmd("write-memory %d %s" % (org, " ".join(str(b) for b in code)))
        end = org + len(code) - 2
        self.z.cmd("set-breakpoint 3 PC=%d" % end)
        self.extra_probes = {end}
        self.z.cmd("set-register PC=%d" % org)
        self.z.cmd("run %d" % 4000000)
        pc = self.pc()
        self.z.cmd("set-breakpoint 3")
        self.extra_probes = set()
        return pc == end

    def hero_pool(self):
        """(FRT rows, pre-shifted bytes of every generated variant) of the
        current hero's frames: the per-game hero sprite set."""
        k = self.rb("HERO_KIND")
        f0 = self.rb(S["kind_tab"] + S["KT_FID0"] + k)
        n = self.rb(S["kind_tab"] + S["KT_FCNT"] + k)
        frt = self.z.read_memory(S["FRT"] + f0 * 16, n * 16)
        fs = S["FT_STRIDE"]
        ft = self.z.read_memory(S["frame_tab"] + f0 * fs, n * fs)
        self.z.cmd("set-memory-zone 0")
        try:
            ram = self.z.read_memory(0, 131072)
        finally:
            self.z.cmd("set-memory-zone -1")
        data = []
        for f in range(n):
            cols, hh = ft[f * fs + S["FT_COLS"]], ft[f * fs + S["FT_H"]]
            for v in range(4):
                bank, lo, hi = frt[f * 16 + v * 3:f * 16 + v * 3 + 3]
                if bank == S["FRT_NONE"]:
                    continue
                a = bank * 16384 + ((hi << 8 | lo) - 0xC000)
                data.append(ram[a:a + hh * 2 * (cols + (v & 1))])
        return frt, data

    def die(self):
        """Hero at 1 hp next to skeleton C; wait until GS_DEAD."""
        self.isolate()
        self.place(SLOT_SKC, self.ent(0)["X"] + 4, Y1, room=0)
        self.set_ent(0, HP=1)
        for _ in range(16):
            self.turn("SPACE")
            if self.rb("GAME_STATE") == GS_DEAD:
                return True
        return False

    def enter_to_select(self):
        self.hold("ENTER")
        ok = self.wait_state(GS_SELECT)
        self.release()
        self.settle()
        return ok

    def sample_during_turn(self, key, fn):
        """Press key; call fn(frame, hero) on every tick of the turn (the
        renderer has finished that tick: frames are read at the wait_tick
        breakpoint). Returns the number of samples."""
        n = [0]

        def cb(frame, hero):
            n[0] += 1
            fn(frame, hero)
        self.turn(key, per_tick=cb)
        return n[0]


def main():
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)
        GOLDEN_PROTO.append(p)

        # ---------------- 1. boot & select --------------------------------
        if want(1):
            p.load()
            h.expect("1 boot GS_SELECT", p.wait_state(GS_SELECT), True)
            golden(h, "game_select", p.frame())
            p.boot(K_KNIGHT)
            e = p.ent(0)
            h.expect("1 GS_PLAYING", p.rb("GAME_STATE"), GS_PLAYING)
            h.expect("1 HERO_KIND knight", p.rb("HERO_KIND"), K_KNIGHT)
            h.expect("1 CUR_ROOM A", p.rb("CUR_ROOM"), 0)
            h.expect("1 x", e["X"], 2)
            h.expect("1 y", e["Y"], Y1)
            h.expect("1 hp", e["HP"], 22)
            h.expect("1 potions", e["POT"], 1)
            golden(h, "game_start", p.frame())
            h.expect("1 GEN_OVERFLOW 0 after boot + hero gen", p.rb("GEN_OVERFLOW"), 0)
            # A5: gen_frame never runs while GEN_SCRATCH (= room maps) is live
            h.expect("1 GEN_TRAP 0 after boot + hero gen", p.rb("GEN_TRAP"), 0)
            h.expect("39 start attrs legal", attr_violations(p.frame(), legal_attrs(p)), [])
            h.expect("8 floor band A at rest", floor_band_ok(p.frame(), holes(0)), [])

        # ---------------- 2-9 movement / floors ----------------------------
        if want(2) or want(3) or want(4) or want(5) or want(6) or want(7) or want(9):
            p.boot(K_KNIGHT)
            p.isolate()
            p.clear_trace()
            ok = p.turn("L")
            e = p.ent(0)
            walks = [f for f in p.trace_fids(0) if f in
                     (FID["knight_walk1"], FID["knight_walk2"], FID["knight_walk3"], FID["knight_walk4"])]
            h.expect("2 walk right turn", ok, True)
            h.expect("2 x 2->3", e["X"], 3)
            h.expect("2 TURN_COUNTER", p.rw("TURN_COUNTER"), 1)
            h.expect("2 facing right", e["FLAGS"] & EF_LEFT, 0)
            h.expect("2 >=2 WALK frames traced", len(walks) >= 2, True)
            h.expect("2 final px", e["PX"], 24)
            # 3. mirror: same idle pose, right at x=12 vs left at x=12
            p.place(0, 12, Y1)
            p.settle()
            fr = p.frame()
            right = [[cell_bytes(fr, 12 + c, Y1 + r) for c in range(3)] for r in range(6)]
            p.turn("H")                         # -> x=11 facing left
            p.place(0, 12, Y1)
            p.settle()
            fl = p.frame()
            h.expect("3 facing left", p.ent(0)["FLAGS"] & EF_LEFT, EF_LEFT)
            mirrored = True
            for r in range(6):
                for line in range(8):
                    rb = [right[r][c][line] for c in range(3)]
                    lb = [cell_bytes(fl, 12 + c, Y1 + r)[line] for c in range(3)]
                    if lb != [bitrev(b) for b in reversed(rb)]:
                        mirrored = False
            h.expect("3 sprite region == bit-mirrored render", mirrored, True)
            # 4. wall
            p.place(0, 1, Y1)
            h.expect("4 wall blocks, no turn", p.no_turn("H"), True)
            h.expect("4 x stays 1", p.ent(0)["X"], 1)
            # 7. no ladder no climb
            p.place(0, 2, Y1)
            h.expect("7 K at col 2: no turn", p.no_turn("K"), True)
            h.expect("7 y unchanged", p.ent(0)["Y"], Y1)
            # 5 + 9. climb up at col 5 ({5,1}), floor band (row 8) during the climb
            p.place(0, 5, Y1)
            tc = p.rw("TURN_COUNTER")
            bad, misal, samples = [], [], [0]

            def chk(frame, e):
                samples[0] += 1
                for c in range(32):
                    if (c, FLOOR_ROWS[0]) in holes(0):   # {5,1} and {23,1} holes
                        continue
                    if attr_at(frame, c, FLOOR_ROWS[0]) != 0x0F:
                        bad.append((c, hex(attr_at(frame, c, FLOOR_ROWS[0]))))
                if e["PX"] & 7:
                    misal.append(e["PX"])
            p.sample_during_turn("K", chk)
            h.expect("5 after first step: L no turn", p.no_turn("L"), True)
            h.expect("5 after first step: H no turn", p.no_turn("H"), True)
            for _ in range(STOREY_ROWS - 1):
                p.sample_during_turn("K", chk)
                chk(p.frame(), p.ent(0))
            h.expect("5 climb y 11->2", p.ent(0)["Y"], Y0)
            h.expect("5 TURN_COUNTER += 9", p.rw("TURN_COUNTER") - tc, STOREY_ROWS)
            h.expect("9 row 8 outside the hole cells all $0F", bad[:4], [])
            h.expect("9 >= 4 mid-turn samples", samples[0] >= 4, True)
            h.expect("9 px AND 7 == 0 throughout", misal, [])
            # 6. climb down
            for _ in range(STOREY_ROWS):
                p.turn("J")
            h.expect("6 climb down y = 11", p.ent(0)["Y"], Y1)
            h.expect("8 floor band A after climbing", floor_band_ok(p.frame(), holes(0)), [])

        # ---------------- 10 / 16 / 18. knight slash next to the hole --------
        if want(10) or want(16) or want(18):
            p.boot(K_KNIGHT)
            p.isolate(keep=(SLOT_RAT,))
            p.place(0, 9, Y1)
            p.turn("H")                          # face left, x=8
            p.place(0, 9, Y1)
            p.place(SLOT_RAT, 5, R1)             # rat cols 5-8, gap 0
            p.set_ent(SLOT_RAT, FLAGS=EF_ACTIVE | EF_HOSTILE)
            p.settle()
            ok_feet = {art_feet_line(n, 9 * 8, left=True, bw=24)[72:96] for n in
                       ("knight_idle1", "knight_idle2", "knight_windup", "knight_slash",
                        "knight_follow", "knight_hurt", "knight_block")}
            p.clear_trace()
            hp0 = p.ent(SLOT_RAT)["HP"]
            floor_bad, feet_bad = [], []

            def chk10(frame, e):
                floor_bad.extend(floor_band_ok(frame, holes(0)))
                line = screen_line_bits(frame, (Y1 + 6) * 8 - 1)[72:96]   # hero feet, cols 9-11
                if line not in ok_feet:
                    feet_bad.append((line, e["DFID"], e["DFPX"]))
            p.sample_during_turn("H", chk10)
            tr = p.trace_fids(0)
            h.expect("16 trace WIND-UP,SLASH,FOLLOW",
                     [f for f in tr if f in (FID["knight_windup"], FID["knight_slash"], FID["knight_follow"])][:3],
                     [FID["knight_windup"], FID["knight_slash"], FID["knight_follow"]])
            h.expect("16 x unchanged", p.ent(0)["X"], 9)
            rat = p.ent(SLOT_RAT)
            hit = p.ent(0)["HIT"]
            h.expect("16 seeded roll: hit => rat hp reduced, miss => unchanged",
                     (rat["HP"] < hp0) if hit else (rat["HP"] == hp0), True)
            h.expect("10 rows 8/17 intact on every sampled frame", floor_bad[:4], [])
            # The sheet's attack frames use a wide lunge stance, so the literal
            # "feet == IDLE" can't hold; the engine-owned property is that the
            # drawn feet line equals the art's feet line at px - ax(_L).
            h.expect("18 feet line == art at the computed anchor (every sample)", feet_bad[:2], [])

        # ---------------- 11. no combat on ladders ---------------------------
        if want(11):
            p.boot(K_KNIGHT)
            p.isolate(keep=(SLOT_RAT,))
            p.place(0, 5, Y1)
            p.turn("K")                          # y=10, mid-ladder
            p.place(SLOT_RAT, 8, R1)             # gap 0, rows overlap at 15
            hp_p, hp_r = p.ent(0)["HP"], p.ent(SLOT_RAT)["HP"]
            p.clear_trace()
            for _ in range(5):
                p.turn("SPACE")
            h.expect("11 hero hp unchanged x5 waits", p.ent(0)["HP"], hp_p)
            h.expect("11 rat hp unchanged", p.ent(SLOT_RAT)["HP"], hp_r)
            h.expect("11 no rat attack frames", FID["rat_bite"] in p.trace_fids(SLOT_RAT), False)
            h.expect("11 L toward it on the ladder: no turn", p.no_turn("L"), True)

        # ---------------- 12. yield ----------------------------------------
        if want(12):
            p.boot(K_KNIGHT)
            p.isolate(keep=(SLOT_RAT,))
            p.place(0, 5, Y1)
            p.turn("K")                          # y=10 climbing up
            p.place(SLOT_RAT, 4, R0, room=0)     # parked on the top ladder-end box
            x0 = p.ent(SLOT_RAT)["X"]
            p.turn("SPACE")
            h.expect("12 monster moves off within 1 turn", p.ent(SLOT_RAT)["X"] != x0, True)
            h.expect("12 hero completes the climb", p.climb("K"), True)
            h.expect("12 hero standing on storey 0", p.ent(0)["Y"], Y0)
            # 12b (review B 🔴): a MID-LADDER monster in the hero's path yields
            # along the ladder, never sideways off it. Goblin (h=4) just started
            # up A's {5,1} shaft (y=12, bottom climb row) as the hero starts down.
            p.boot(K_KNIGHT)
            p.isolate()
            p.place(0, 5, Y0)                    # hero standing on storey 0 at the shaft
            p.place(SLOT_GOBLIN, 5, G1 - 1, room=0, flags=EF_ACTIVE | EF_HOSTILE)
            p.set_ent(SLOT_GOBLIN, AIDIR=0xFF)   # climbing up (head-on)
            p.settle()
            off = []

            def gob_ok():
                g = p.ent(SLOT_GOBLIN)
                if g["X"] != 5 and not is_standing(g["Y"], 4):
                    off.append((g["X"], g["Y"]))
            p.turn("J")
            gob_ok()
            h.expect("12b goblin yields along the ladder (x 5, y 12 -> 13)",
                     (p.ent(SLOT_GOBLIN)["X"], p.ent(SLOT_GOBLIN)["Y"]), (5, G1))
            done = False
            for _ in range(20):
                if p.ent(0)["Y"] == Y1:
                    done = True
                    break
                if not p.turn("J"):
                    p.turn("SPACE")
                gob_ok()
            h.expect("12b hero completes the climb down", done, True)
            h.expect("12b goblin never off-shaft while mid-ladder", off, [])

        # ---------------- 13. walker approaches + attacks -------------------
        if want(13):
            p.boot(K_KNIGHT)
            xs = []
            p.clear_trace()
            attacked = False
            for _ in range(20):
                p.turn("SPACE")
                xs.append(p.ent(SLOT_RAT)["X"])
                if FID["rat_bite"] in p.trace_fids(SLOT_RAT) or p.ent(0)["HP"] < 22:
                    attacked = True
                    break
            h.expect("13 rat x decreases", xs[0] > xs[-1] or xs[0] < 16, True)
            h.expect("13 rat reaches gap <= 1", p.ent(SLOT_RAT)["X"] - 5 <= 1, True)
            h.expect("13 rat attack sequence traced", attacked, True)

        # ---------------- 17 / 20 / 22. monster attack, deaths ---------------
        if want(17) or want(20):
            p.boot(K_KNIGHT)
            p.isolate()
            p.place(SLOT_SKC, 6, Y1, room=0)     # skeleton from C, adjacent (gap 1)
            p.clear_trace()
            hp0 = p.ent(0)["HP"]
            hit = False
            for _ in range(6):
                p.turn("SPACE")
                tr = p.trace_fids(SLOT_SKC)
                if FID["skeleton_raise"] in tr and FID["skeleton_cut"] in tr:
                    hit = True
                    break
            h.expect("17 skeleton RAISE,CUT traced", hit, True)
            sk_hit = p.ent(SLOT_SKC)["HIT"]
            drop = hp0 - p.ent(0)["HP"]
            h.expect("17 seeded roll: hit => hp drops 1..4 (1d4), miss => 0",
                     (1 <= drop <= 4) if sk_hit else (drop == 0), True)
            # 20. kill it
            p.set_ent(SLOT_SKC, HP=1)
            dead = False
            rects = set()
            for _ in range(12):
                p.clear_trace()
                p.turn("L")
                sk = p.ent(SLOT_SKC)
                rects |= {(c, r) for c in range(sk["DCOL"], sk["DCOL"] + sk["DCOLS"])
                          for r in range(sk["DROW"], sk["DROW"] + sk["DROWS"])}
                if not sk["FLAGS"] & EF_ACTIVE:
                    dead = True
                    break
            tr = p.trace_fids(SLOT_SKC)
            h.expect("20 trace HURT then DEAD(COLLAPSED)",
                     FID["skeleton_hurt"] in tr and FID["skeleton_collapsed"] in tr, True)
            h.expect("20 skeleton killed, slot freed", dead, True)
            p.settle()
            fr = p.frame()
            he = p.ent(0)
            hero = {(c, r) for c in range(he["DCOL"], he["DCOL"] + he["DCOLS"])
                    for r in range(he["DROW"], he["DROW"] + he["DROWS"])}
            trail = [(c, r) for (c, r) in sorted(rects - hero) if not p.is_bg(fr, c, r)]
            h.expect("20 footprint == background (no trail)", trail, [])

        if want(21) or want(22):
            p.boot(K_KNIGHT)
            p.isolate()
            p.place(SLOT_SKC, 6, Y1, room=0)
            p.set_ent(0, HP=1)
            for _ in range(12):
                p.turn("SPACE")
                if p.rb("GAME_STATE") == GS_DEAD:
                    break
            h.expect("21 hero dies -> GS_DEAD", p.rb("GAME_STATE"), GS_DEAD)
            h.expect("22 hp never underflows (0)", p.ent(0)["HP"], 0)
            p.hold("ENTER")
            h.expect("21 ENTER -> GS_SELECT", p.wait_state(GS_SELECT), True)
            p.release()
            p.settle()
            p.hold("1")
            p.wait_state(GS_PLAYING)
            p.release()
            p.settle()
            h.expect("21 new game POTIONS_TAKEN = 0", p.rb("POTIONS_TAKEN"), 0)
            h.expect("21 new game hero hp 22", p.ent(0)["HP"], 22)
            h.expect("21 new game skeleton back in C", (p.ent(SLOT_SKC)["ROOM"], p.ent(SLOT_SKC)["HP"]), (ROOM_C, 10))
            h.expect("21 new game RNG reseeded", p.rw("RNG_STATE"), 0xA55A)

        # ---------------- 19. wizard reach-3 zap ---------------------------
        if want(19):
            p.boot(K_WIZARD)
            p.isolate(keep=(SLOT_RAT,))
            p.place(0, 6, Y1)
            p.place(SLOT_RAT, 12, R1)            # wizard cols 6-8: gap 3
            p.clear_trace()
            zap, over_rat = [0], []
            zr = Y1 + S["ZAP_ROW_OFF"]           # staff row

            def chkz(frame, e):
                if any(attr_at(frame, c, zr) == 0x45 and any(cell_bytes(frame, c, zr))
                       for c in (10, 11)):
                    zap[0] += 1
                r = p.ent(SLOT_RAT)             # the bolt never paints over the target
                if r["DVIS"] & 1 and r["DROW"] <= zr < r["DROW"] + r["DROWS"]:
                    over_rat.extend(c for c in range(r["DCOL"], r["DCOL"] + r["DCOLS"])
                                    if attr_at(frame, c, zr) == 0x45)
            p.sample_during_turn("L", chkz)
            h.expect("19 wizard attacked (CAST traced)", FID["wizard_cast2"] in p.trace_fids(0), True)
            h.expect("19 x unchanged", p.ent(0)["X"], 6)
            h.expect("19 ZAP tiles in the gap during impact", zap[0] > 0, True)
            h.expect("19 no ZAP attr inside the target's drawn footprint", over_rat[:4], [])

        # ---------------- 23/24/25/30/31/34/29/39 A <-> B ------------------
        if any(want(n) for n in (23, 24, 25, 29, 30, 31, 34, 39)):
            p.boot(K_KNIGHT)
            # 30. potion 0 in A (col 28, storey 0, cell row 7)
            pr0 = item_row(0)
            p.place(0, 24, Y0)
            for _ in range(3):
                p.turn("L")
            e = p.ent(0)
            fr = p.frame()
            h.expect("30 potions 1 -> 2", e["POT"], 2)
            h.expect("30 POTIONS_TAKEN bit0", p.rb("POTIONS_TAKEN") & 1, 1)
            p.place(0, 20, Y0)
            p.settle()
            fr = p.frame()
            h.expect("30 potion cell -> ATTR_AIR", attr_at(fr, 28, pr0), 0x00)
            h.expect("30 potion cell bitmap blank", any(cell_bytes(fr, 28, pr0)), False)
            # 23. damage the slime, remember it
            p.set_ent(SLOT_SLIME, HP=3)
            sl0 = p.ent(SLOT_SLIME)
            # 24. lure the rat: hero at x=28 s1, rat gap 1
            p.place(0, 28, Y1)
            p.place(SLOT_RAT, 23, R1)
            hud0 = p.frame()[0:6144]
            legal = legal_attrs(p)
            trans_viol, trans_samples = [], [0]
            # extra breakpoint on each scroll step: sample frames mid-transition
            p.z.cmd("set-breakpoint 3 PC=%d" % S["hscroll_room.step"])
            p.extra_probes = {S["hscroll_room.step"]}
            t0 = p.rw("TURN_COUNTER")
            p.hold("L")
            for _ in range(200):
                p.tick()
                if p.rb("GAME_STATE") == GS_TRANSITION:
                    trans_samples[0] += 1
                    trans_viol += attr_violations(p.frame(), TILE_ATTRS)
                if p.rw("TURN_COUNTER") != t0 and p.idle():
                    break
            p.release()
            p.z.cmd("disable-breakpoint 3")
            p.extra_probes = set()
            p.settle()
            e = p.ent(0)
            h.expect("34 CUR_ROOM = B", p.rb("CUR_ROOM"), 1)
            h.expect("34 hero x = 1", e["X"], 1)
            h.expect("34 hero storey 1 (y 11)", e["Y"], Y1)
            fr = p.frame()

            def hud_rows(f, rows):
                out = b""
                for r in rows:
                    for line in range(8):
                        a = ((0x40 | (r & 0x18)) + line) << 8 | ((r & 7) << 5)
                        out += bytes(f[a - 0x4000:a - 0x4000 + 32])
                return out
            h.expect("34 HUD rows 21-22 unchanged by the transition (not scrolled)",
                     hud_rows(fr, (21,)) == hud_rows(hud0 + bytes(768), (21,)), True)
            h.expect("34 after A->B scroll: screen == room B tiles", p.bg_mismatch()[:4], [])
            h.expect("29 >= 1 frame sampled in GS_TRANSITION", trans_samples[0] >= 1, True)
            h.expect("29 no sprite attr in rows 0-17 during transition", trans_viol[:4], [])
            rat = p.ent(SLOT_RAT)
            h.expect("24 rat room = B", rat["ROOM"], 1)
            h.expect("24 rat PENDING", rat["FLAGS"] & EF_PENDING, EF_PENDING)
            h.expect("24 nothing drawn for it", rat["DVIS"] & 1, 0)
            h.expect("25 slime stays in A", p.ent(SLOT_SLIME)["ROOM"], 0)
            p.clear_trace()
            steps = 0
            while p.ent(SLOT_RAT)["FLAGS"] & EF_PENDING and steps < 6:
                p.turn("L")
                steps += 1
            rat = p.ent(SLOT_RAT)
            h.expect("24 rat materialised within 4 hero steps", steps <= 4 and not rat["FLAGS"] & EF_PENDING, True)
            h.expect("24 rat x = 1 storey 1", (rat["X"], rat["Y"]), (1, R1))
            h.expect("24 rat faces right", rat["FLAGS"] & EF_LEFT, 0)
            h.expect("24 walk-in traced", any(f in (FID["rat_run1"], FID["rat_run2"])
                                              for f in p.trace_fids(SLOT_RAT)), True)
            h.expect("39 attrs legal in B", attr_violations(p.frame(), legal_attrs(p)), [])
            h.expect("8 floor band B", floor_band_ok(p.frame(), holes(1)), [])
            # back to A: 23 persistence + 31 potion absent
            p.isolate()
            p.place(0, 2, Y1)
            p.turn("H")
            p.turn("H")
            p.until(lambda: p.rb("GAME_STATE") == GS_PLAYING and p.idle())
            h.expect("23 back in A", p.rb("CUR_ROOM"), 0)
            h.expect("23 after B->A scroll: screen == room A tiles", p.bg_mismatch()[:4], [])
            sl = p.ent(SLOT_SLIME)
            h.expect("23 slime hp/x/y persisted", (sl["HP"], sl["X"], sl["Y"]), (sl0["HP"], sl0["X"], sl0["Y"]))
            fr = p.frame()
            h.expect("31 potion 0 still absent", attr_at(fr, 28, item_row(0)), 0x00)

        # ---------------- 26 / 35 vertical follow + transitions -------------
        if want(26) or want(35):
            p.boot(K_KNIGHT)
            # walk into B for real, then set up at the shaft
            p.isolate()
            p.place(0, 28, Y1)
            p.turn("L")
            p.turn("L")
            p.until(lambda: p.rb("CUR_ROOM") == 1 and p.idle())
            p.place(0, 24, Y1)
            p.place(SLOT_GOBLIN, 20, G1, room=1)   # gap 1, storey 1
            p.place(SLOT_BATB, 28, R1 - 3, room=1)  # bat in storey-1 band, gap 1
            p.turn("J")                          # down-exit: step + transition
            e = p.ent(0)
            h.expect("35 B col 24 J -> C", p.rb("CUR_ROOM"), ROOM_C)
            h.expect("35 arrive s0 x=24", (e["X"], e["Y"]), (24, Y0))
            h.expect("35 after B->C scroll: screen == room C tiles", p.bg_mismatch()[:4], [])
            g = p.ent(SLOT_GOBLIN)
            h.expect("26 goblin room = C, pending", (g["ROOM"], bool(g["FLAGS"] & EF_PENDING)), (ROOM_C, True))
            h.expect("26 bat does not follow", p.ent(SLOT_BATB)["ROOM"], 1)
            for _ in range(4):
                if not p.ent(SLOT_GOBLIN)["FLAGS"] & EF_PENDING:
                    break
                p.turn("H")
            g = p.ent(SLOT_GOBLIN)
            h.expect("26 goblin materialised at s0 x=24", (bool(g["FLAGS"] & EF_PENDING), g["X"], g["Y"]), (False, 24, G0))
            h.expect("8 floor band C", floor_band_ok(p.frame(), holes(ROOM_C)), [])
            # 35 back up
            p.set_ent(SLOT_GOBLIN, ROOM=NOWHERE)
            p.place(0, 24, Y0)
            p.turn("K")                          # up-exit: immediate transition
            e = p.ent(0)
            h.expect("35 K -> back in B s1 x=24", (p.rb("CUR_ROOM"), e["X"], e["Y"]), (1, 24, Y1))
            h.expect("35 after C->B scroll: screen == room B tiles", p.bg_mismatch()[:4], [])

        # ---------------- 27 cap / 28 arrival conflict ----------------------
        if want(27) or want(28):
            p.boot(K_KNIGHT)
            # B holds 3: goblin, bat, + skeleton D poked in. Two candidates in A
            # after the exit step (hero x=29): bat D (band rows 11-12, cols 25-27,
            # gap 1) and the rat (cols 21-24, gap 4). Only 1 fits (3 + 1 = 4).
            p.place(SLOT_SKD, 12, Y0, room=1)
            p.isolate()
            p.place(0, 28, Y1)
            p.place(SLOT_BATD, 25, Y1, room=0)
            p.place(SLOT_RAT, 21, R1, room=0)
            p.turn("L")
            p.until(lambda: p.rb("CUR_ROOM") == 1 and p.idle())
            h.expect("27 cap: nearest (bat) follows", p.ent(SLOT_BATD)["ROOM"], 1)
            h.expect("27 cap: second (rat) refused, stays", p.ent(SLOT_RAT)["ROOM"], 0)
            # tall cap: B has skeleton D + goblin turned skeleton; skeleton C candidate refused
            p2 = p
            p2.boot(K_KNIGHT)
            p2.place(SLOT_SKD, 12, Y0, room=1)
            p2.set_ent(SLOT_GOBLIN, KIND=K_SKELETON)
            p2.set_ent(SLOT_BATB, ROOM=NOWHERE)
            p2.isolate()
            p2.place(0, 28, Y1)
            p2.place(SLOT_SKC, 24, Y1, room=0)    # gap 1
            p2.turn("L")
            p2.until(lambda: p2.rb("CUR_ROOM") == 1 and p2.idle())
            h.expect("27 tall cap: skeleton refused (B has 2 tall)", p2.ent(SLOT_SKC)["ROOM"], 0)
            # 28 arrival conflict: goblin parked on B's arrival box
            p.boot(K_KNIGHT)
            p.isolate()
            p.place(SLOT_GOBLIN, 1, G1, room=1)
            p.place(0, 28, Y1)
            p.turn("L")
            p.until(lambda: p.rb("CUR_ROOM") == 1 and p.idle())
            g = p.ent(SLOT_GOBLIN)
            h.expect("28 conflicting monster PENDING in place", (bool(g["FLAGS"] & EF_PENDING), g["X"], g["Y"]), (True, 1, G1))
            for _ in range(4):
                p.turn("L")
            g = p.ent(SLOT_GOBLIN)
            h.expect("28 reappears once the hero moved off", bool(g["FLAGS"] & EF_PENDING), False)

        # ---------------- 52 (user bug B7) no old-room monster after a transition
        # Root cause: render runs first in a tick (A1 RENDER_FIRST), so the
        # first render after do_exit used the PREVIOUS tick's anim_tick output
        # (N_VIS, now SLOTREC R_VIS / RLIST of the old room): every monster of the room just left
        # was drawn at its old position on the new room for one tick, then
        # erased. Followers are irrelevant; the slime (slow, never follows)
        # shows it. Both scroll directions.
        if want(52):
            def ghost_check(tag, slot, key, dest):
                sl = p.ent(slot)
                h.expect(f"52 {tag} setup: slime drawn, not in {dest}",
                         (sl["DVIS"] & 1, sl["ROOM"] != dest), (1, True))
                old = {(c, r) for c in range(sl["DCOL"], sl["DCOL"] + sl["DCOLS"])
                       for r in range(sl["DROW"], sl["DROW"] + sl["DROWS"])}
                p.hold(key)
                seen, stale, after = [], [], 0
                for i in range(300):
                    p.tick()
                    if i == 1:
                        p.release()
                    if p.rb("CUR_ROOM") != dest or p.rb("GAME_STATE") != GS_PLAYING:
                        continue
                    after += 1                      # 1 = the tick do_exit ran in
                    fr = p.frame()                  # the DISPLAYED screen
                    cov = set()
                    for s_ in range(16):
                        e = p.ent(s_)
                        if not e["DVIS"] & 1:
                            continue
                        if e["ROOM"] != dest:
                            stale.append((after, s_, e["ROOM"]))
                        else:
                            cov |= {(c, r) for c in range(e["DCOL"], e["DCOL"] + e["DCOLS"])
                                    for r in range(e["DROW"], e["DROW"] + e["DROWS"])}
                    bad = [cr for cr in sorted(old - cov) if not p.is_bg(fr, *cr)]
                    if bad:
                        seen.append((after, bad[:3]))
                    if after >= 4:
                        break
                p.release()
                p.until(lambda: p.idle())
                h.expect(f"52 {tag} sampled 4 ticks after the transition", after, 4)
                h.expect(f"52 {tag} no entity of another room drawn", stale[:3], [])
                h.expect(f"52 {tag} slime's old cells show the new room's background",
                         seen[:3], [])

            p.boot(K_KNIGHT)
            p.isolate(keep=(SLOT_SLIME,))
            p.place(0, 28, Y1)                      # A storey 1 -> right exit
            ghost_check("A->B (horizontal)", SLOT_SLIME, "L", 1)
            p.isolate()
            p.place(SLOT_SLIME, 16, R0, room=1)     # B storey 0, far from the shafts
            p.place(0, 24, Y1)
            ghost_check("B->C (vertical)", SLOT_SLIME, "J", ROOM_C)

        # ---------------- 53 (review A7) present keeps up: zap, potion, quaff
        # Per tick, right after the tick-start present (probe_presented):
        # displayed bank 7 == composed bank 5, through a wizard zap (overlay
        # not in DMG_LIST), a potion pickup (shadow_rect + PEND_DMG + message)
        # and a quaff (attr flash + HUD).
        if want(53):
            p.boot(K_WIZARD)
            p.isolate(keep=(SLOT_RAT,))
            p.place(0, 6, Y1)
            p.place(SLOT_RAT, 12, R1)            # gap 3: zap
            p.present_watch(True)
            p.clear_trace()
            p.turn("L")
            zapped = FID["wizard_cast2"] in p.trace_fids(0)
            p.set_ent(SLOT_RAT, ROOM=NOWHERE)
            p.place(0, 24, Y0)                   # potion 0 at col 28, storey 0
            for _ in range(3):
                p.turn("L")
            pot = p.ent(0)["POT"]
            p.set_ent(0, HP=5)
            p.turn("G")
            p.settle()
            s_ = p.present_samples
            p.present_watch(False)
            h.expect("53 setup: zap cast, potion taken, quaff", (zapped,
                     pot >= 2, p.ent(0)["HP"] > 5), (True, True, True))
            h.expect("53 probe_presented sampled every tick", len(s_) >= 20, True)
            h.expect("53 bank 7 == bank 5 after every tick-start present",
                     [i for i, d in enumerate(s_) if d][:5], [])

        # ---------------- 54 (review A7, B7b) new game after death: no stale slot
        # new_game rewrote the entity table but left N_VIS / N_FID (now R_VIS / R_FID) / RLIST of
        # the dead game, so the first (render-first) tick of the new game drew
        # skeleton C (room C, parked in room A by die()) at its old position
        # and the hero with the DEAD knight's frame id from a pool that now
        # holds the wizard (BLIT_MISS stayed 0). Fix: new_game -> vis_reset.
        # Checked on the first 2 ticks after GS_PLAYING with a DIFFERENT hero.
        if want(54):
            p.boot(K_KNIGHT)
            died = p.die()
            sk = p.ent(SLOT_SKC)
            old = {(c, r) for c in range(sk["DCOL"], sk["DCOL"] + sk["DCOLS"])
                   for r in range(sk["DROW"], sk["DROW"] + sk["DROWS"])}
            h.expect("54 setup: knight died, skeleton C drawn in room A",
                     (died, sk["DVIS"] & 1, sk["ROOM"]), (True, 1, 0))
            p.hold("ENTER")
            p.wait_state(GS_SELECT)
            p.release()
            p.settle()
            p.hold("2")                         # wizard
            p.wait_state(GS_PLAYING)
            p.release()
            wz0 = p.rb(S["kind_tab"] + S["KT_FID0"] + K_WIZARD)
            wzn = p.rb(S["kind_tab"] + S["KT_FCNT"] + K_WIZARD)
            stale, badfid, badbg = [], [], []
            for t in (1, 2):
                p.tick()                        # first ticks of the new game
                cur = p.rb("CUR_ROOM")
                cov = set()
                for s_ in range(16):
                    e = p.ent(s_)
                    if not e["DVIS"] & 1:
                        continue
                    if e["ROOM"] != cur or not e["FLAGS"] & EF_ACTIVE:
                        stale.append((t, s_, e["ROOM"]))
                    cov |= {(c, r) for c in range(e["DCOL"], e["DCOL"] + e["DCOLS"])
                            for r in range(e["DROW"], e["DROW"] + e["DROWS"])}
                e0 = p.ent(0)
                if e0["DVIS"] & 1 and not wz0 <= e0["DFID"] < wz0 + wzn:
                    badfid.append((t, e0["DFID"]))
                fr = p.composed_frame()
                badbg += [(t, cr) for cr in sorted(old - cov) if not p.is_bg(fr, *cr)][:3]
            h.expect("54 new game ticks 1-2: no slot of another room / dead slot drawn",
                     stale[:3], [])
            h.expect("54 new game ticks 1-2: hero drawn only with a wizard frame",
                     badfid[:3], [])
            h.expect("54 new game ticks 1-2: skeleton C's old cells show background",
                     badbg[:3], [])
            h.expect("54 BLIT_MISS 0", p.rb("BLIT_MISS"), 0)

        # ---------------- 55-58 flyers vs ladder ends (B8) ------------------
        # User bug B8: the Ghost parked on a shaft's end box above the
        # climbing hero; the blocked climb cost no turn, so nothing moved.
        # Rule by user 2026-10-02 (prototype §3.5 / §6.4): flyers MAY cross a
        # shaft (enter a ladder-end box moving in x) but never wait, stop,
        # attack or reverse inside one; one inside at turn start must move
        # (keep crossing or step out). Fully boxed (both x steps illegal) it
        # may stay / attack. A climb blocked by an entity is a WAIT turn.
        # Room A ladders {5,1}, {23,1} (B3B-3: both link storey 1 to storey 0;
        # their top end boxes are on storey 0). Fixed seed; flyer speeds unchanged.
        if want(55) or want(56) or want(57) or want(58):
            p.boot(K_KNIGHT)
            segs = ladder_segs(p, ROOM_A)
            moved_in = []                         # violations: in a box, x kept

            def track(slot, prev, tag):
                e = p.ent(slot)
                if in_end_box(p, e, segs) and e["X"] == prev["X"]:
                    moved_in.append((tag, prev["X"], e["X"], e["Y"]))
                return e

        if want(55):
            p.isolate()
            p.place(0, 5, Y1)                       # foot of {5,1}, storey 1
            p.place(SLOT_GHOST, 5, G0 - 1, room=0)  # INSIDE the top end box (storey 0)
            g_in = in_end_box(p, p.ent(SLOT_GHOST), segs)
            out_after = None
            g = p.ent(SLOT_GHOST)
            for w_ in range(4):                     # hero waits: ghost moves out
                if not in_end_box(p, g, segs):
                    out_after = w_
                    break
                p.turn("SPACE")
                g = track(SLOT_GHOST, g, "wait%d" % w_)
            ys = []
            for i in range(STOREY_ROWS):            # climb up: 9 moving turns
                p.turn("K")
                ys.append(p.ent(0)["Y"])
                g = track(SLOT_GHOST, g, "up%d" % i)
            for _ in range(3):
                p.turn("SPACE")                     # ghost chases on storey 0
                g = track(SLOT_GHOST, g, "top")
            ys2 = []
            for i in range(STOREY_ROWS):            # and back down
                p.turn("J")
                ys2.append(p.ent(0)["Y"])
                g = track(SLOT_GHOST, g, "down%d" % i)
            h.expect("55 setup: ghost placed inside the top end box of {5,1}",
                     len(g_in) == 3, True)
            h.expect("55 ghost moves out of the ladder-end box within 3 turns",
                     out_after is not None and out_after <= 3, True)
            h.expect("55 hero climbs {5,1} up: one row per turn",
                     ys, list(range(Y1 - 1, Y0 - 1, -1)))
            h.expect("55 hero climbs back down: one row per turn",
                     ys2, list(range(Y0 + 1, Y1 + 1)))
            # bat wander/jitter (other storey) may cross shafts, never idles in
            # a box, keeps moving
            p.isolate()
            p.place(0, 14, Y1)                      # hero on storey 1
            p.place(SLOT_BATB, 12, R0 - 3, room=0)  # bat B on storey 0
            xs, crossed = set(), 0
            b = p.ent(SLOT_BATB)
            for i in range(40):
                p.turn("SPACE")
                b = track(SLOT_BATB, b, "bat%d" % i)
                xs.add(b["X"])
                crossed += bool(in_end_box(p, b, segs))
            h.expect("55 flyers never end a turn in a ladder-end box with x kept",
                     moved_in[:3], [])
            h.expect("55 bat keeps moving (>= 4 distinct cols in 40 turns)", len(xs) >= 4, True)
            h.expect("55 bat crosses a shaft (turns ended in a box > 0)", crossed > 0, True)

        # 56: the Ghost crosses the {23,1} shaft (storey 0 box cols 23..25) to
        # reach the hero (91cf829 made shafts walls: it stopped at x 26).
        if want(56):
            moved_in.clear()
            p.isolate()
            p.place(0, 12, Y0)                      # hero storey 0, cols 12..14
            p.place(SLOT_GHOST, 27, G0 - 1, room=0, flags=EF_ACTIVE | EF_HOSTILE | EF_LEFT)
            gx, inbox = [], 0
            g = p.ent(SLOT_GHOST)
            for i in range(16):
                p.turn("SPACE")
                g = track(SLOT_GHOST, g, "cross%d" % i)
                gx.append(g["X"])
                inbox += bool(in_end_box(p, g, segs))
            h.expect("56 ghost crosses the shaft: 5 turns in its end box", inbox, 5)
            h.expect("56 ghost reaches the hero (x 16, gap 1 = reach)", gx[-1], 16)
            h.expect("56 ghost x strictly decreasing to 16",
                     gx[:11], list(range(26, 15, -1)))
            h.expect("56 no x-kept turn inside a box", moved_in[:3], [])

        # 57: in a box the Ghost moves instead of attacking: hero at x 2
        # (cols 2..4) beside {5,1}'s top box (cols 5..7). Ghost from x 9:
        # 8 (gap 3) -> 7 (in, gap 2) -> 6 (in, gap 1: in reach, moves on) ->
        # 5 (in, gap 0) -> fully boxed (left = hero, right = a reversal that
        # stays inside): stays and may attack (the documented exception).
        if want(57):
            p.isolate()
            p.place(0, 2, Y0)
            p.place(SLOT_GHOST, 9, G0 - 1, room=0, flags=EF_ACTIVE | EF_HOSTILE | EF_LEFT)
            hp0 = p.ent(0)["HP"]
            seq = []
            for i in range(6):
                p.turn("SPACE")
                seq.append((p.ent(SLOT_GHOST)["X"], p.ent(0)["HP"] < hp0))
            first_hit = next((i for i, (_, hit) in enumerate(seq) if hit), None)
            h.expect("57 ghost x per turn 8,7,6,5,5,5", [x for x, _ in seq], [8, 7, 6, 5, 5, 5])
            h.expect("57 no attack before fully boxed at x 5 (first hit >= turn 5)",
                     first_hit is None or first_hit >= 4, True)

        # 58 (rule b): a climb blocked by an entity is a WAIT (monsters act; the
        # blocker yields), not a free no-op. Hero mid-ladder on {5,1} at y 6
        # climbing up; ghost (rows 2..5) parked on the next step (y 5).
        if want(58):
            p.isolate()
            p.place(0, 5, Y0 + 4)
            p.set_ent(0, AIDIR=0xFF)
            p.place(SLOT_GHOST, 5, Y0, room=0, flags=EF_ACTIVE | EF_HOSTILE | EF_LEFT)
            tc = p.rw("TURN_COUNTER")
            p.turn("K")
            h.expect("58 blocked climb consumes a turn", p.rw("TURN_COUNTER") - tc, 1)
            h.expect("58 hero did not move (y 6)", p.ent(0)["Y"], Y0 + 4)
            h.expect("58 blocker moved off (x != 5)", p.ent(SLOT_GHOST)["X"] != 5, True)
            h.expect("58 hero then reaches the top", p.climb("K"), True)
            h.expect("58 hero standing on storey 0 (y 2)", p.ent(0)["Y"], Y0)

        # 59 (rule b): terrain-blocked / illegal climbs stay free (no turn).
        if want(59):
            p.boot(K_KNIGHT)
            p.isolate()                             # hero x 2, storey 1: no ladder
            h.expect("59 UP without a ladder: no turn", p.no_turn("K"), True)
            h.expect("59 DOWN on the bottom storey, no hole: no turn", p.no_turn("J"), True)
            p.place(0, 5, Y0)                       # top of {5,1} (storey 0)
            h.expect("59 UP at a down-only shaft top: no turn", p.no_turn("K"), True)
            h.expect("59 CLIMB_BLK clear after a terrain block", p.rb("CLIMB_BLK"), 0)

        # ---------------- 60 (A7b review) merged move rects ------------------
        def dmg():
            n = p.rb("DMG_COUNT")
            b = p.z.read_memory(S["DMG_LIST"], n * 4) if n else []
            return [tuple(b[i * 4:i * 4 + 4]) for i in range(n)]

        # (a) DMG_LIST of a lone hero move: one union rect when old/new
        # footprints overlap or touch, two rects across a gap. DMG_LIST rows are
        # (c0, c1, r0, r1) with exclusive ends.
        if want(60):
            p.boot(K_KNIGHT)
            p.isolate()
            p.place(0, 3, Y1)
            fp0 = lambda e: (e["DCOL"], e["DCOL"] + e["DCOLS"], e["DROW"], e["DROW"] + e["DROWS"])

            def move(**kw):
                a = fp0(p.ent(0))
                p.set_ent(0, **kw)
                p.tick()
                return a, fp0(p.ent(0)), dmg()

            u = lambda a, b: (min(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), max(a[3], b[3]))
            px0 = p.ent(0)["PX"]
            a, b, d = move(PX=px0 + 2)
            h.expect("60 horizontal move: one union rect", d, [u(a, b)])
            px = p.ent(0)["PX"]
            p.set_ent(0, PX=px & 0xF8)
            p.tick(2)
            px = p.ent(0)["PX"]
            a, b, d = move(PX=px + 8 * (p.ent(0)["DCOLS"]))
            h.expect("60 touching footprints: one union rect", (len(d), d[0] == u(a, b)), (1, True))
            px = p.ent(0)["PX"]
            a, b, d = move(PX=px + 8 * (p.ent(0)["DCOLS"] + 3))
            h.expect("60 gap: two rects (old, new)", sorted(d), sorted([a, b]))
            p.place(0, 3, Y1)
            p.tick(2)
            py = p.ent(0)["PY"]
            a, b, d = move(PY=py - 2)
            h.expect("60 vertical (ladder) move: one union rect", d, [u(a, b)])

        # (b) per tick, for two adjacent sprites moving together (+ ladder-style
        # vertical and teleport-gap phases): the composed AND displayed screens
        # equal a full recomposition. The reference run forces a whole-playfield
        # PEND_DMG every tick, so the engine erases to background and repairs
        # every sprite in slot order; the incremental run must match it tick
        # for tick.
        if want(60):
            def phases(full):
                p.boot(K_KNIGHT)
                p.isolate(keep=(SLOT_RAT,))
                p.place(0, 3, Y1)
                p.place(SLOT_RAT, 7, Y1, flags=EF_ACTIVE | EF_LEFT)
                p.settle()
                out, moved = [], set()
                hx, rx = p.ent(0)["PX"], p.ent(SLOT_RAT)["PX"]
                hy = p.ent(0)["PY"]
                for t in range(60):
                    if t < 24:                        # side by side, both +2 px/tick
                        p.set_ent(0, PX=hx + 2 * t)
                        p.set_ent(SLOT_RAT, PX=rx + 2 * t)
                    elif t < 36:                      # hero vertical, rat horizontal
                        p.set_ent(0, PX=hx + 48, PY=hy - 2 * (t - 24))
                        p.set_ent(SLOT_RAT, PX=rx + 48 + 2 * (t - 24))
                    else:                             # hero teleports (gap), rat walks
                        p.set_ent(0, PX=hx + (96 if t & 1 else 0), PY=hy)
                        p.set_ent(SLOT_RAT, PX=rx + 72 + 2 * (t - 36))
                    if full:
                        p.z.cmd("write-memory %d 0 0 32 %d" % (S["PEND_DMG"], PLAY_ROWS))
                        p.wb("PEND_DMG_COUNT", 1)
                    p.tick()
                    moved |= {(s_, p.ent(s_)["DCOL"]) for s_ in (0, SLOT_RAT)}
                    out.append((p.composed_frame(), p.frame()))
                    if full and (0, 32, 0, PLAY_ROWS) not in dmg():
                        moved.add(("nofull", t))      # forced rect did not reach DMG_LIST
                return out, moved

            inc, moved = phases(False)
            ref, rmoved = phases(True)
            bad_c = [t for t in range(60) if inc[t][0] != ref[t][0]]
            bad_d = [t for t in range(60) if inc[t][1] != ref[t][1]]
            h.expect("60 both sprites moved over the run", len({m for m in moved if m[0] == 0}) > 6
                     and len({m for m in moved if m[0] != 0}) > 6, True)
            h.expect("60 reference run: whole-playfield rect in DMG_LIST every tick",
                     [m for m in rmoved if m[0] == "nofull"][:3], [])
            h.expect("60 screens differ tick to tick (sprites really move)",
                     len({f[0] for f in inc}) > 30, True)
            h.expect("60 composed == full recomposition at every tick (60)", bad_c[:5], [])
            h.expect("60 displayed == full recomposition at every tick (60)", bad_d[:5], [])
            h.expect("60 DMG_OVERFLOW 0", p.rb("DMG_OVERFLOW"), 0)

        # ---------------- 32 / 33 quaff & full pack --------------------------
        if want(32) or want(33):
            p.boot(K_KNIGHT)
            p.isolate()
            h.expect("32 G at full hp: no turn", p.no_turn("G"), True)
            p.set_ent(0, HP=10)
            tc = p.rw("TURN_COUNTER")
            p.turn("G")
            e = p.ent(0)
            h.expect("32 quaff hp 10 -> 18", e["HP"], 18)
            h.expect("32 potions 1 -> 0", e["POT"], 0)
            h.expect("32 TURN_COUNTER += 1", p.rw("TURN_COUNTER") - tc, 1)
            h.expect("32 G with 0 potions: no turn", p.no_turn("G"), True)
            p.set_ent(0, HP=20, POT=1)
            p.turn("G")
            h.expect("32 heal capped at max", p.ent(0)["HP"], 22)
            p.set_ent(0, POT=9)
            p.place(0, 24, Y0)
            for _ in range(3):
                p.turn("L")
            h.expect("33 full pack stays 9", p.ent(0)["POT"], 9)
            p.place(0, 20, Y0)
            p.settle()
            h.expect("33 potion stays on the floor", attr_at(p.frame(), 28, item_row(0)), 0x42)
            h.expect("33 POTIONS_TAKEN unchanged", p.rb("POTIONS_TAKEN") & 1, 0)

        # ---------------- 15 flyer 2D in B ---------------------------------
        if want(15):
            p.boot(K_KNIGHT)
            p.isolate()
            p.place(0, 28, Y1)
            p.turn("L")
            p.turn("L")
            p.until(lambda: p.rb("CUR_ROOM") == 1 and p.idle())
            p.place(SLOT_GOBLIN, 3, G1, room=NOWHERE)
            xs, ys = set(), set()
            for _ in range(10):
                p.turn("SPACE")
                b = p.ent(SLOT_BATB)
                xs.add(b["X"])
                ys.add(b["Y"])
            h.expect("15 bat x changes", len(xs) > 1, True)
            h.expect("15 bat y takes >= 2 values", len(ys) >= 2, True)
            band = (STOREY_ROWS * 0, R0)          # bat B on storey 0: 9s .. 9s+8-h
            h.expect("15 bat y always in its band 0..6", all(band[0] <= y <= band[1] for y in ys), True)

        # ---------------- 41 (extra, §3.1) hold-to-repeat -------------------
        # ---------------- 61 (A8) IM 2 + ISR + silent AY player slot ------
        if want(61):
            isr_tests(h, p)

        # ---------------- 43 (review A2) $7FFD paging lock at the tape entry
        if want(43):
            p.load()
            lo, lk = S["start.lo"], S["check_paging.locked"]
            p.z.cmd("set-breakpoint 4 PC=%d" % lo)
            p.z.cmd("set-breakpoint 5 PC=%d" % lk)
            p.extra_probes = {lo, lk}
            p.z.cmd("set-register PC=%d" % S["start"])
            p.z.cmd("run 400000")
            h.expect("43 unlocked: check passes (reaches start.lo)", p.pc(), lo)
            p.load()
            p.z.cmd("set-breakpoint 4 PC=%d" % lo)
            p.z.cmd("set-breakpoint 5 PC=%d" % lk)
            p.extra_probes = {lo, lk}
            # stub: ld a,$30 (bank 0 + ROM48 + LOCK); ld bc,$7FFD; out (c),a; jp start
            st = S["start"]
            stub = [0x3E, 0x30, 0x01, 0xFD, 0x7F, 0xED, 0x79, 0xC3, st & 0xFF, st >> 8]
            p.z.cmd("write-memory %d %s" % (0x6000, " ".join(map(str, stub))))
            p.z.cmd("set-register PC=%d" % 0x6000)
            p.z.cmd("run 4000000")
            h.expect("43 locked: stops at check_paging.locked", p.pc(), lk)
            fr = p.frame()
            h.expect("43 locked: message printed (row 11 not blank)",
                     any(any(cell_bytes(fr, c, 11)) for c in range(5, 24)), True)
            p.extra_probes = set()

        # ---------------- 44 (review A3) alloc filling a bank to exactly $10000
        if want(44):
            p.boot(K_KNIGHT)
            ai, ap, res = S["ALLOC_IDX"], S["ALLOC_PTR"], S["MSG_BUF"]
            p.wb("ALLOC_IDX", 0)
            p.z.cmd("write-memory %d 0 255" % ap)          # ptr = $FF00
            a = S["alloc"]
            # ld bc,$100; call alloc; ld (res),a; ld (res+1),hl;
            # ld bc,$10;  call alloc; ld (res+3),a; ld (res+4),hl
            code = [0x01, 0x00, 0x01, 0xCD, a & 0xFF, a >> 8, 0x32, res & 0xFF, res >> 8,
                    0x22, (res + 1) & 0xFF, (res + 1) >> 8,
                    0x01, 0x10, 0x00, 0xCD, a & 0xFF, a >> 8, 0x32, (res + 3) & 0xFF, (res + 3) >> 8,
                    0x22, (res + 4) & 0xFF, (res + 4) >> 8]
            h.expect("44 stub ran", p.run_stub(code), True)
            r = p.z.read_memory(res, 6)
            banks = [p.rb(S["pool_banks"] + i) for i in range(3)]
            h.expect("44 first alloc: bank 0 @ $FF00", (r[0], r[1] | r[2] << 8), (banks[0], 0xFF00))
            h.expect("44 next alloc opens the next bank @ $C000", (r[3], r[4] | r[5] << 8), (banks[1], 0xC000))
            h.expect("44 ALLOC_IDX 1, ptr $C010", (p.rb("ALLOC_IDX"), p.rw("ALLOC_PTR")), (1, 0xC010))

        # ---------------- 45 (review C R3/D5) damage-list overflow fallbacks
        if want(45):
            p.boot(K_KNIGHT)
            pd, qd, da = S["PEND_DMG"], S["queue_damage"], S["dmg_add"]
            p.wb("DMG_OVERFLOW", 0)
            p.wb("PEND_DMG_COUNT", 4)
            p.z.cmd("write-memory %d %s" % (pd + 12, "10 5 2 2"))     # last (c,r,cols,rows)
            # ld bc,$0608 (row 6, col 8); ld de,$0503 (5 cols, 3 rows); call queue_damage
            h.expect("45 stub (queue_damage full)", p.run_stub(
                [0x01, 0x08, 0x06, 0x11, 0x03, 0x05, 0xCD, qd & 0xFF, qd >> 8]), True)
            h.expect("45 full PEND_DMG: last rect grows to the bounding box",
                     tuple(p.z.read_memory(pd + 12, 4)), (8, 5, 5, 4))
            h.expect("45 PEND_DMG_COUNT stays 4", p.rb("PEND_DMG_COUNT"), 4)
            p.wb("DMG_COUNT", S["DMG_MAX"])
            h.expect("45 stub (dmg_add full)", p.run_stub(
                [0x01, 0x03, 0x04, 0x11, 0x01, 0x01, 0xCD, da & 0xFF, da >> 8]), True)
            h.expect("45 full DMG_LIST: last rect = whole playfield",
                     tuple(p.z.read_memory(S["DMG_LIST"] + 47 * 4, 4)), (0, 32, 0, PLAY_ROWS))
            h.expect("45 DMG_OVERFLOW counted both", p.rb("DMG_OVERFLOW"), 2)

        # ---------------- 46 (review B) a mid-ladder body blocks the zap line
        if want(46):
            def zap_past_climber(with_goblin):
                p.boot(K_WIZARD)
                p.isolate()
                p.place(0, 28, Y1)
                p.turn("L")
                p.turn("L")
                p.until(lambda: p.rb("CUR_ROOM") == 1 and p.idle())
                p.isolate()
                p.place(0, 1, Y1)                # storey 1 (the shaft foot), cols 1-3
                p.place(SLOT_RAT, 7, R1, room=1, flags=EF_ACTIVE | EF_HOSTILE | EF_LEFT)
                if with_goblin:                  # mid-ladder on B's {4,1} shaft, cols 4-6
                    p.place(SLOT_GOBLIN, 4, G1 - 1, room=1, flags=EF_ACTIVE | EF_HOSTILE)
                    p.set_ent(SLOT_GOBLIN, AIDIR=0xFF)
                p.settle()
                hp0 = p.ent(SLOT_RAT)["HP"]
                p.clear_trace()
                p.turn("L")
                return FID["wizard_cast2"] in p.trace_fids(0), hp0
            cast, _ = zap_past_climber(False)
            h.expect("46 control: rat at gap 3 is zapped", cast, True)
            cast, hp0 = zap_past_climber(True)
            h.expect("46 climbing goblin in the gap: no CAST", cast, False)
            h.expect("46 rat untouched", p.ent(SLOT_RAT)["HP"], hp0)

        # ---------------- 47 (review B) yield falls back to the other side
        if want(47):
            p.boot(K_KNIGHT)
            p.isolate()
            p.place(0, 5, Y1)
            p.turn("K")                          # y=10, climbing up A's {5,1}
            p.place(SLOT_RAT, 4, R0, room=0, flags=EF_ACTIVE | EF_HOSTILE | EF_LEFT)
            p.place(SLOT_GOBLIN, 1, G0, room=0, flags=EF_ACTIVE | EF_HOSTILE)  # blocks the left
            h.expect("47 corked hero still completes the climb", p.climb("K", limit=28), True)
            h.expect("47 hero standing on storey 0", p.ent(0)["Y"], Y0)

        # ---------------- 48 (review B) potion tile with no list entry
        if want(48):
            p.boot(K_KNIGHT)
            p.isolate()
            p.place(0, 10, Y1)
            cell = S["ROOM_MAP"] + item_row(1) * 32 + 11   # storey 1 potion row, under the hero
            p.wb(cell, S["T_POTION"])
            p.turn("SPACE")
            h.expect("48 unlisted potion tile: not taken", p.ent(0)["POT"], 1)
            h.expect("48 unlisted potion tile stays in the map", p.rb(cell), S["T_POTION"])
            h.expect("48 POTIONS_TAKEN unchanged", p.rb("POTIONS_TAKEN"), 0)

        # ---------------- 49 (review 🟢) stamp_rect clamps at col 31 + CLIP_TRAP
        if want(49):
            p.boot(K_KNIGHT)
            st = S["stamp_rect"]
            before = p.z.read_memory(0x5800 + 32, 2)        # row 1 cols 0-1
            # ld a,$42; ld bc,$001E (row 0, col 30); ld de,$0401 (4 cols, 1 row); call stamp_rect
            h.expect("49 stub", p.run_stub([0x3E, 0x42, 0x01, 0x1E, 0x00, 0x11, 0x01, 0x04,
                                            0xCD, st & 0xFF, st >> 8]), True)
            h.expect("49 cols 30-31 stamped", tuple(p.z.read_memory(0x5800 + 30, 2)), (0x42, 0x42))
            h.expect("49 no wrap into row 1", p.z.read_memory(0x5800 + 32, 2), before)
            h.expect("49 CLIP_TRAP counted", p.rb("CLIP_TRAP"), 1)

        # ---------------- 50 tape end-to-end (the real 128 Tape Loader path)
        # The .sna enters at `boot`; this loads a private copy of wazhack.tap the
        # way a user does (reset -> 128 menu Tape Loader autoload -> BASIC ->
        # CODE -> start -> 2x LD-BYTES into banks 1/3 -> boot).
        if want(50):
            tap = os.path.join(tempfile.mkdtemp(prefix="game_tap_"), "wazhack.tap")
            shutil.copyfile(os.path.join(os.path.dirname(HERE), "build", "wazhack.tap"), tap)
            p.wb("GAME_STATE", 0)                        # no stale GS_SELECT
            p.z.cmd("set-memory-zone 0")                 # scrub banks 1/3: sources
            for b in (1, 3):                             # must come off the tape
                p.z.cmd("write-memory %d %s" % (b * 16384, " ".join(["0"] * 64)))
            ayo = 3 * 16384 + S["AY_RESERVE"] - 0xC000   # A8: the AY slot block too
            p.z.cmd("write-memory %d %s" % (ayo, " ".join(["0"] * S["AY_LEN"])))
            p.z.cmd("set-memory-zone -1")
            p.z.cmd("disable-breakpoints")
            p.z.cmd("exit-cpu-step")
            p.z.cmd("smartload " + tap)
            t0 = time.monotonic()
            gs = None
            while time.monotonic() - t0 < 60:            # fast tape traps: ~1 s
                time.sleep(0.25)
                gs = p.rb("GAME_STATE")
                if gs == GS_SELECT:
                    break
            print(f"[info] 50 tape: GAME_STATE {gs} after {time.monotonic() - t0:.1f}s", flush=True)
            p.z.cmd("enter-cpu-step")
            p.load_breakpoints()
            if not h.expect("50 tape boots to GS_SELECT", gs, GS_SELECT):
                print("[info] 50 PC " + p.z.cmd("get-registers")[:40], flush=True)
            else:
                tape_rest(h, p)

        # ---------------- 51 select screen + hero sprites across games
        # (user bug: after a game, GS_SELECT drew the last game's hero in
        # another hero's slot; a 2nd game with a different hero must match a
        # fresh boot of that hero exactly).
        if want(51):
            p.boot(K_WIZARD)
            ref_start = p.frame()
            golden(h, "game_start_wizard", ref_start)
            ref_pool = p.hero_pool()
            p.boot(K_KNIGHT)
            h.expect("51 knight dies", p.die(), True)
            h.expect("51 ENTER -> GS_SELECT", p.enter_to_select(), True)
            golden(h, "game_select", p.frame())
            p.hold("2")
            h.expect("51 '2' starts a wizard game", p.wait_state(GS_PLAYING), True)
            p.release()
            p.settle(3)
            h.expect("51 2nd game wizard start screen == fresh wizard boot",
                     p.frame() == ref_start, True)
            golden(h, "game_start_wizard", p.frame())
            frt, data = p.hero_pool()
            h.expect("51 2nd game wizard FRT rows == fresh boot", frt == ref_pool[0], True)
            h.expect("51 2nd game wizard pool bytes == fresh boot", data == ref_pool[1], True)
            h.expect("51 GEN_TRAP 0 after a hero regen over built room maps",
                     p.rb("GEN_TRAP"), 0)
            h.expect("51 wizard dies", p.die(), True)
            h.expect("51 ENTER -> GS_SELECT (after 2 heroes)", p.enter_to_select(), True)
            golden(h, "game_select", p.frame())
            p.hold("1")
            p.wait_state(GS_PLAYING)
            p.release()
            p.settle(3)
            golden(h, "game_start", p.frame())

        # ---------------- 42 (review C R1) overlap repair of a DIRTY_ATTR sprite
        # The hero's attr is toggled every tick (DIRTY_ATTR, frame unchanged)
        # while an adjacent skeleton's wide attack frames are erased/redrawn
        # over the overlap. The bitmap must be identical, tick by tick, to the
        # same turn played without the toggle (attrs are the only difference).
        if want(42):
            def skel_turn(toggle):
                p.boot(K_KNIGHT)
                p.isolate()
                p.place(SLOT_SKC, 5, Y1, room=0, flags=EF_ACTIVE | EF_HOSTILE | EF_LEFT)
                frames, overlap = [], [0]
                flip = [0]

                def cb(frame, hero):
                    frames.append(frame[:6144])
                    sk = p.ent(SLOT_SKC)
                    if (sk["DVIS"] & 1 and sk["DCOL"] < hero["DCOL"] + hero["DCOLS"]
                            and hero["DCOL"] < sk["DCOL"] + sk["DCOLS"]):
                        overlap[0] += 1
                    if toggle:
                        flip[0] ^= 1
                        p.set_ent(0, FLT=4, FLA=0x42 if flip[0] else 0x44)
                for _ in range(4):
                    p.turn("SPACE", per_tick=cb)
                return frames, overlap[0]
            fa, ova = skel_turn(False)
            fb, _ = skel_turn(True)
            diff = [i for i, (a, b) in enumerate(zip(fa, fb)) if a != b]
            h.expect("42 skeleton rect overlaps the hero on some ticks", ova > 0, True)
            h.expect("42 same tick count", len(fa), len(fb))
            h.expect("42 flashing hero keeps its pixels under an overlapping redraw", diff[:4], [])

        if want(41):
            p.boot(K_KNIGHT, repeat=1)
            p.isolate()
            x0, t0 = p.ent(0)["X"], p.rw("TURN_COUNTER")
            p.hold("L")
            p.tick(20)
            p.release()
            p.until(lambda: p.idle())
            dx, dt = p.ent(0)["X"] - x0, p.rw("TURN_COUNTER") - t0
            h.expect("41 held L repeats: >= 9 steps in 20 ticks (2 ticks/step)", dx >= 9, True)
            h.expect("41 one turn per step", dt, dx)

        # ---------------- 36 / 37 / 38 / 40 walkthrough ---------------------
        if any(want(n) for n in (14, 36, 37, 38, 40)):
            res1 = walkthrough(h, p, check14=want(14))
            h.expect("37 walkthrough reaches GS_WIN (bounded)", res1["gs"], GS_WIN)
            print(f"[info] walkthrough: {res1['turns']} turns, OVERRUN_COUNT={res1['overrun']}, "
                  f"BLIT_MISS={res1['miss']}, hero hp={res1['hp']}")
            h.expect("40 OVERRUN_COUNT reported (target 0)", res1["overrun"], 0)
            h.expect("40 DMG_OVERFLOW 0 over the walkthrough", res1["dmgov"], 0)
            h.expect("40 CLIP_TRAP 0 over the walkthrough", res1["clip"], 0)
            h.expect("40 GEN_TRAP 0 over the walkthrough (rooms built + scrolled)",
                     res1["gentrap"], 0)
            h.expect("36 WIN: ENTER -> GS_SELECT", res1["select"], True)
            if want(38):
                res2 = walkthrough(h, p, check14=False)
                h.expect("38 determinism: identical end state", res2["state"], res1["state"])

        t0 = getattr(Proto, "_t0", None)
        if t0:
            print(f"[time] total {time.monotonic() - t0:.1f}s, last scenario"
                  f" {time.monotonic() - Proto._t_last:.1f}s", flush=True)
        print(f"[info] run anomalies (returns outside a probe): {Proto.anomalies}", flush=True)
        h.expect("harness: no run anomalies", Proto.anomalies, 0)
        # A7: at every wait_tick read during play, displayed bank 7 == bank 5
        print(f"[info] A7 present checks at goldens (displayed vs composed): "
              f"{Proto.present_checks}, mismatches {Proto.present_mismatch[:5]}", flush=True)
        h.expect("A7 present: displayed == composed at every golden", len(Proto.present_mismatch), 0)
        return 0 if h.ok else 1



def mmu_c000(regs):
    """Bank at $C000 from get-registers' 128K MMU field (segment 3)."""
    import re
    return int(re.search(r"MMU=([0-9a-fA-F]+)", regs).group(1)[12:16], 16)


def port_7ffd(p):
    """The value last written to $7FFD as the emulator holds it (not the shadow)."""
    for line in p.z.cmd("get-io-ports").splitlines():
        if line.startswith("Spectrum 7FFD port:"):
            return int(line.split(":")[1].strip(), 16)
    raise RuntimeError("get-io-ports: no 7FFD line")


def isr_regs(regs):
    import re
    return {k: int(v, 16) for k, v in re.findall(r"(\b[A-Z]{2}'?)=([0-9a-f]{4})\b", regs)}


def isr_tests(h, p):
    """#61 (A8): IM 2 active; SYS_FRAMES / AY_PLAY at 50 Hz; the ISR preserves
    every register and the $C000 bank / screen bit for every bank paged; across
    a room transition (screen bit flips 1 -> 0 -> 1) the ISR pages bank 3 for
    the player and restores exactly PORT_7FFD_SHADOW; no code ever runs at
    $C000+ with a bank other than 3 paged (A3 review carry-over)."""
    ay, done = S["AY_PLAY"], S["isr.done"]
    # A3 carry-over: executing $C000+ with any bank but 3 = a paging bug. A
    # conditional (non-optimised) breakpoint: armed from the snapshot load
    # (boot, select, game start) through the transition below.
    p.load()
    p.z.cmd("set-breakpoint 7 PC>=C000H and RAM<>3")
    p.extra_probes = set()
    p.wait_state(GS_SELECT)
    p.wb("INPUT_REPEAT", 0)
    p.wb("ANIM_FREEZE", 1)
    p.wb("INPUT_SRC", 1)
    p.hold("1")
    p.wait_state(GS_PLAYING)
    p.release()
    p.settle(3)
    regs = p.z.cmd("get-registers")
    h.expect("61 IM 2 active", " IM2 " in regs, True)
    h.expect("61 I = vector table page", int(regs.split(" I=")[1][:2], 16),
             S["ISR_VEC_TABLE"] >> 8)
    h.expect("61 vector table: 257 x ISR_VEC_BYTE",
             set(p.z.read_memory(S["ISR_VEC_TABLE"], S["ISR_VEC_LEN"])), {S["ISR_VEC_BYTE"]})
    h.expect("61 ISR copied to ISR_ADDR", p.z.read_memory(S["ISR_ADDR"], S["ISR_LEN"]) ==
             p.z.read_memory(S["isr_image"], S["ISR_LEN"]), True)
    # 50 Hz: 50 idle ticks = 100 frames = 100 AY_PLAY calls, ~70,908 T each
    def frames():
        b = p.z.read_memory(S["SYS_FRAMES"], 3)
        return b[0] | b[1] << 8 | b[2] << 16
    f0, a0, o0 = frames(), p.rw("AY_CALLS"), p.rw("OVERRUN_COUNT")
    p.z.cmd("reset-tstates-partial")
    p.tick(50)
    t = int(p.z.cmd("get-tstates-partial"))
    df, da = frames() - f0, p.rw("AY_CALLS") - a0
    print(f"[info] 61 50 ticks: SYS_FRAMES +{df}, AY_CALLS +{da}, {t} T"
          f" ({t / max(df, 1):.0f} T/frame)", flush=True)
    h.expect("61 SYS_FRAMES: 2 frames per tick (50 ticks, no overrun)",
             (df, p.rw("OVERRUN_COUNT") - o0), (100, 0))
    h.expect("61 SYS_FRAMES at 50 Hz (|T - frames x 70,908| < 1 frame)",
             abs(t - df * 70908) < 70908, True)
    h.expect("61 AY_PLAY once per frame", da, df)
    # room transition: hero at A's right edge walks right (do_exit: show_bank5,
    # scroll, present_full -> bank 7). Stop in every ISR at AY_PLAY (bank 3
    # paged by OUT only) and at isr.done (port restored from the shadow).
    # Held L repeats (INPUT_REPEAT 1): the hero keeps walking in room B for
    # 30 ticks after arrival, so the ISR also lands in blits (pool banks).
    p.isolate()
    p.place(0, 28, Y1)
    p.settle()
    p.wb("INPUT_REPEAT", 1)
    p.z.cmd("set-breakpoint 5 PC=%d" % ay)
    p.z.cmd("set-breakpoint 6 PC=%d" % done)
    bad, banks, scr, n_ay, n_done, ticks, a7, after = [], set(), [], 0, 0, 0, [], 0
    p.hold("L")
    while ticks < 400:
        p.z.cmd("cpu-step")
        p.z.cmd("run %d" % 4000000)
        regs = p.z.cmd("get-registers")
        pc = int(regs[3:7], 16)
        if pc in (ay, done):
            sh, port, c000 = p.rb("PORT_7FFD_SHADOW"), port_7ffd(p), mmu_c000(regs)
            if pc == ay:
                n_ay += 1
                banks.add(sh & 7)
                if not scr or scr[-1] != sh & 8:
                    scr.append(sh & 8)
                if (port, c000) != ((sh & 0xF8) | S["BANK_AY"], S["BANK_AY"]):
                    bad.append(("ay", hex(sh), hex(port), c000))
            else:
                n_done += 1
                if (port, c000) != (sh, sh & 7):
                    bad.append(("done", hex(sh), hex(port), c000))
            continue
        if pc == S["wait_tick"]:
            ticks += 1
            if p.rb("CUR_ROOM") == 1 and p.rb("GAME_STATE") == GS_PLAYING:
                after += 1
                if after == 30:
                    break
            continue
        a7.append(hex(pc))                       # breakpoint 7 (or a stray return)
        break
    p.release()
    p.wb("INPUT_REPEAT", 0)
    for n in (5, 6, 7):
        p.z.cmd("set-breakpoint %d" % n)
    print(f"[info] 61 transition: {ticks} ticks, ISR stops ay={n_ay} done={n_done},"
          f" interrupted $C000 banks {sorted(banks)}, screen bit sequence {scr}", flush=True)
    h.expect("61 transition reached room B", p.rb("CUR_ROOM"), 1)
    h.expect("61 no code at $C000+ with bank != 3 (boot..transition)", a7, [])
    h.expect("61 every ISR: bank 3 for AY_PLAY, port == shadow after", bad[:4], [])
    h.expect("61 ISR ran on both screens across the flip (bit 3: 8 -> 0 -> 8)",
             scr[:3] == [8, 0, 8] and n_ay == n_done and n_ay > 50, True)
    h.expect("61 ISR interrupted the transition + play with >= 3 different $C000 banks",
             len(banks) >= 3, True)
    # register probe per bank: page it, load patterns into every register
    # (alternate set too), EI + 2 HALTs = exactly 2 ISRs, all must survive.
    pb = S["page_bank"]
    want_regs = {"AF": 0xA5C3, "BC": 0xB1C1, "DE": 0xD1E1, "HL": 0x4151, "IX": 0x1A2B,
                 "IY": 0x3C4D, "AF'": 0x1357, "BC'": 0x2468, "DE'": 0x9ABC, "HL'": 0xDEF0}
    sh0 = p.rb("PORT_7FFD_SHADOW")
    # ZEsarUX quirk (also on the IM 1 baseline): the first HALT executed after
    # a wait_tick stop falls through without an interrupt. A throwaway
    # ei/halt/halt stub first, so every probe starts from the same state.
    p.run_stub([0xFB, 0x76, 0x76])
    for bank in (0, 1, 3, 4, 6, 7):
        code = [0xF3, 0x3E, bank, 0xCD, pb & 0xFF, pb >> 8,         # di; ld a,b; call page_bank
                0x21, 0x57, 0x13, 0xE5, 0xF1, 0x08,                 # AF' = 1357
                0xD9, 0x01, 0x68, 0x24, 0x11, 0xBC, 0x9A, 0x21, 0xF0, 0xDE, 0xD9,
                0x21, 0xC3, 0xA5, 0xE5, 0xF1,                       # AF = A5C3
                0x01, 0xC1, 0xB1, 0x11, 0xE1, 0xD1, 0x21, 0x51, 0x41,
                0xDD, 0x21, 0x2B, 0x1A, 0xFD, 0x21, 0x4D, 0x3C,
                0xFB, 0x76, 0x76]                                   # ei; halt; halt
        sp0 = isr_regs(p.z.cmd("get-registers"))["SP"]
        a0 = p.rw("AY_CALLS")
        ran = p.run_stub(code)
        regs = p.z.cmd("get-registers")
        r = isr_regs(regs)
        got = {k: r.get(k) for k in want_regs}
        sh = p.rb("PORT_7FFD_SHADOW")
        h.expect(f"61 bank {bank}: 2 ISRs, every register preserved",
                 (ran, p.rw("AY_CALLS") - a0, got, r["SP"]), (True, 2, want_regs, sp0))
        h.expect(f"61 bank {bank}: $C000 bank + port == shadow (screen bit kept)",
                 (mmu_c000(regs), port_7ffd(p), sh), (bank, sh, (sh0 & 0xF8) | bank))
    p.load()                                     # IY / room map / bank clobbered


def tape_rest(h, p):
    """#50 after the tape reached GS_SELECT: screen, pool, banks, play."""
    p.tick(2)                                    # park on select_tick
    golden(h, "game_select", p.frame())
    h.expect("50 tape GEN_OVERFLOW 0", p.rb("GEN_OVERFLOW"), 0)
    from game_lib import SNA_RAM
    p.z.cmd("set-memory-zone 0")
    try:
        ram = p.z.read_memory(0, 131072)
    finally:
        p.z.cmd("set-memory-zone -1")
    lo, hi = S["SRC_LEN_LO"], S["SRC_LEN_HI"]
    h.expect("50 bank 1 sprite sources == .sna", ram[1 * 16384:1 * 16384 + lo] ==
             SNA_RAM[1 * 16384:1 * 16384 + lo], True)
    # bank 3 block = source tail + bank-3 cold code (select, scrolls): BANK3_LEN >= hi
    b3 = S.get("BANK3_LEN", hi)
    h.expect("50 bank 3 sprite sources + cold code == .sna", ram[3 * 16384:3 * 16384 + b3] ==
             SNA_RAM[3 * 16384:3 * 16384 + b3], True)
    ayo = 3 * 16384 + S["AY_RESERVE"] - 0xC000
    h.expect("50 bank 3 AY slot (A8 tape block) == .sna", ram[ayo:ayo + S["AY_LEN"]] ==
             SNA_RAM[ayo:ayo + S["AY_LEN"]], True)
    for nm in ("TSET_LO", "TSET_HI"):            # B3B-8: the bank-7 tileset blocks
        o = 7 * 16384 + S[nm] - 0xC000
        h.expect(f"50 bank 7 tilesets {nm} (B3B-8 tape block) == .sna",
                 ram[o:o + S["TSET_HALF_LEN"]] == SNA_RAM[o:o + S["TSET_HALF_LEN"]], True)
    h.expect("50 tape: IM 2 installed by boot", " IM2 " in p.z.cmd("get-registers"), True)
    # CODE block starts in bank 5 low RAM (boot, generator) and runs into bank 2
    lo5 = S["lowram_code"] - 0x4000
    h.expect("50 bank 5 low-RAM cold code == .sna", ram[5 * 16384 + lo5:6 * 16384] ==
             SNA_RAM[5 * 16384 + lo5:6 * 16384], True)
    p.wb("INPUT_REPEAT", 0)
    p.wb("ANIM_FREEZE", 1)
    p.wb("INPUT_SRC", 1)
    p.hold("1")
    h.expect("50 tape: '1' starts the game", p.wait_state(GS_PLAYING), True)
    p.release()
    p.settle(3)
    golden(h, "game_start", p.frame())


def walkthrough(h, p, check14=False):
    """§8.2 reference walkthrough, fixed seed, Knight. Bump-attacks whatever
    blocks the way; quaffs below 9 hp."""
    p.boot(K_KNIGHT)
    budget = [400]

    def act(key):
        budget[0] -= 1
        if p.ent(0)["HP"] < 9 and p.ent(0)["POT"] > 0:
            p.turn("G")
        if not p.turn(key):
            p.turn("SPACE")

    def go_x(x):
        while p.ent(0)["X"] != x and budget[0] > 0 and p.rb("GAME_STATE") == GS_PLAYING:
            act("L" if x > p.ent(0)["X"] else "H")

    def go_room(room, key):
        while p.rb("CUR_ROOM") != room and budget[0] > 0 and p.rb("GAME_STATE") == GS_PLAYING:
            act(key)

    def climb(key, storey):
        while budget[0] > 0 and p.rb("GAME_STATE") == GS_PLAYING:
            e = p.ent(0)
            if is_standing(e["Y"], 6) and storey_of(e["Y"], 6) == storey:
                return
            act(key)

    # B3B-3 route (2 storeys; rooms re-authored from §8.2, same shape):
    go_room(1, "L")                  # A -> B (storey 1)
    go_x(24)
    go_room(ROOM_C, "J")             # B {24,2} -> C (s0, col 24)
    sk_y0 = p.ent(5)["Y"]
    go_x(27)                         # potion 2 (C col 29, storey 0)
    def foe_left():
        """A live hostile body touching the hero's left side (gap 0)."""
        e = p.ent(0)
        for s_ in range(1, 16):
            m = p.ent(s_)
            if (m["FLAGS"] & (EF_ACTIVE | EF_HOSTILE | EF_PENDING | 16) == EF_ACTIVE | EF_HOSTILE
                    and m["ROOM"] == p.rb("CUR_ROOM")):
                w, hh = body(p, m["KIND"])
                if m["X"] + w == e["X"] and m["Y"] < e["Y"] + 6 and e["Y"] < m["Y"] + hh:
                    return True
        return False

    min_y = sk_y0
    # Let C's skeleton come up {6,1} (spawn col 12: its nearest climb, away
    # from the hero's arrival shaft {24,0}/{24,1}); the ghost (boxed on its
    # top end) is fought off. B3B-3 made this wait reactive on purpose (an
    # intended change from the PROTO fixed script): attack only when a live
    # hostile actually touches the hero's left side (foe_left), else wait.
    for _ in range(30):
        min_y = min(min_y, p.ent(5)["Y"])
        if sk_y0 - min_y >= STOREY_ROWS:
            break
        act("H" if foe_left() else "SPACE")
    if check14:
        print(f"[info] 14: C skeleton y {sk_y0} -> min {min_y}")
        h.expect("14 C skeleton climbs: y decreases by >= 9 within 30 turns",
                 sk_y0 - min_y >= STOREY_ROWS, True)
    go_x(24)
    climb("J", 1)                    # {24,1} down to storey 1
    go_room(ROOM_D, "H")             # C -> D (s1)
    go_x(22)
    climb("K", 0)                    # {22,1} up to storey 0 (potion 3 at col 17)
    go_x(3)
    p.until(lambda: p.rb("GAME_STATE") != GS_PLAYING, 40)
    res = dict(gs=p.rb("GAME_STATE"), turns=p.rw("TURN_COUNTER"),
               overrun=p.rw("OVERRUN_COUNT"), miss=p.rb("BLIT_MISS"), hp=p.ent(0)["HP"],
               dmgov=p.rb("DMG_OVERFLOW"), clip=p.rb("CLIP_TRAP"), gentrap=p.rb("GEN_TRAP"))
    res["state"] = (p.rw("RNG_STATE"), p.rw("TURN_COUNTER"), p.rb("POTIONS_TAKEN"),
                    tuple((e["ROOM"], e["X"], e["Y"], e["HP"], e["FLAGS"] & 0x7F)
                          for e in (p.ent(s) for s in range(9))))
    p.hold("ENTER")
    res["select"] = p.wait_state(GS_SELECT)
    p.release()
    p.settle()
    golden(h, "game_select", p.frame())             # after a WIN -> ENTER
    return res


if __name__ == "__main__":
    sys.exit(main())
