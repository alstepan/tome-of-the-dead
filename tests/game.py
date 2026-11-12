#!/usr/bin/env python3
"""PROTO playability checklist (docs/design/prototype.md §11.3, items 1-40).

Drives build/tome-of-the-dead.sna in ZEsarUX over ZRCP. Fixed seed, INPUT_REPEAT=0
(edge-triggered), ANIM_FREEZE=1 unless a check needs idle motion. Scenario setup
uses pokes of the entity array (layout in docs/memory-map.md) where walking there
would only add time; the long no-softlock walkthrough (#37) plays the real game.

Usage:
    python3 tests/game.py                  # run everything
    python3 tests/game.py --update-golden  # refresh game_select / game_start
    python3 tests/game.py 1 2 30           # run only the listed items

RECLAIM-C2: the release build (-DDEBUG_KIT=0) has no ANIM_TRACE (the
render's (slot, frame_id) ring that items 2/10/11/13/17/19/20/24/46/53/66 read).
Run as a script on a build without it, this file assembles a private
-DDEBUG_KIT=0 -DANIM_TRACE_ON=1 copy (~5 s, temp dir) and re-runs itself on it
(WZ_BUILD_DIR); the trace build differs from the release only by the trace.
Build with -DANIM_TRACE_ON=1 yourself to skip that (e.g. a variant build).
"""
import hashlib
import os
import re
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _trace_build():
    """RECLAIM-C2: re-run on a private -DANIM_TRACE_ON=1 build when the build
    under test has no ANIM_TRACE (BEFORE game_lib reads the .sym at import)."""
    import subprocess
    bdir = os.environ.get("WZ_BUILD_DIR", os.path.join(os.path.dirname(HERE), "build"))
    try:
        sym = open(os.path.join(bdir, "tome-of-the-dead.sym")).read()
    except OSError:
        return                                   # game_lib reports the missing build
    if re.search(r"^ANIM_TRACE:", sym, re.M):
        return
    out = tempfile.mkdtemp(prefix="game_trace_")
    print(f"[game] {bdir} has no ANIM_TRACE (release): building -DDEBUG_KIT=0 -DANIM_TRACE_ON=1"
          f" -> {out}", flush=True)
    r = subprocess.run([os.path.join(os.path.dirname(HERE), "tools", "build.sh"), "-o", out,
                        "-DDEBUG_KIT=0", "-DANIM_TRACE_ON=1"], capture_output=True, text=True)
    if r.returncode:
        sys.exit("trace build failed:\n" + r.stdout[-2000:] + r.stderr[-500:])
    rc = subprocess.call([sys.executable, os.path.abspath(__file__)] + sys.argv[1:],
                         env=dict(os.environ, WZ_BUILD_DIR=os.path.join(out, "build")))
    shutil.rmtree(out, ignore_errors=True)
    sys.exit(rc)


if __name__ == "__main__":
    _trace_build()
import game_lib  # noqa: E402
from game_lib import (Harness, Proto, S, EMU_ARGS, holes, floor_band_ok, attr_at, kind_frames,  # noqa: E402
                       cell_bytes, TILE_ATTRS, FLASH_ATTRS, KIND_ATTR, split_frame, frame_png,
                       stand_y, is_standing, storey_of, item_row, STOREY_ROWS, STOREY_COUNT,
                       PLAY_ROWS, FLOOR_ROWS, MAP_LEN,
                       GS_PLAYING, GS_WIN, GS_DEAD, GS_SELECT, GS_TRANSITION, GS_ANYKEY, BOOT_WAITS,
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
SQZ_EXTRA = S["CLIMB_SQZ_N"] - 1              # B18: extra waits a yielding blocker may earn


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
    (bottom end of {col,t}, top end of {col,t+1}; the B8 flyer_lcost test)."""
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
        """(ROOM_MAP, TILE_GLYPHS, TILE_ATTRS, ORN_GLYPHS, the CUR_ROOM floor inks) from memory."""
        z = self.z
        ink = room_model.floor_inks(z.read_memory(S["FLOOR_LIST"], 128), self.rb("CUR_ROOM"))
        return (z.read_memory(S["ROOM_MAP"], MAP_LEN), z.read_memory(S["TILE_GLYPHS"], S["TILE_IDS"] * 8),
                z.read_memory(S["TILE_ATTRS"], S["TILE_IDS"]), z.read_memory(S["ORN_GLYPHS"], 64), ink)

    def is_bg(self, frame, c, r):
        """Cell (c,r) shows exactly its tile-map background (glyph + attr; B3B-8:
        the row-17 ornament over its floor cells)."""
        g, a = room_model.expected_cell(*self.bg_tables(), c, r)
        return attr_at(frame, c, r) == a and bytes(cell_bytes(frame, c, r)) == g

    def bg_mismatch(self):
        """Cells of rows 0-17 that differ from the tile-map background, outside
        every drawn sprite footprint (transition / erase correctness)."""
        return self.bg_mismatch_in(self.frame())

    def bg_mismatch_in(self, fr):
        """bg_mismatch of a given 6912-B screen (displayed or composed)."""
        tabs = self.bg_tables()
        covered = set()
        drip = game_lib.drip_cells(self)             # D3-8b: screen-only overlay
        for s_ in range(16):
            e = self.ent(s_)
            if e["DVIS"] & 1:
                covered |= {(c, r) for c in range(e["DCOL"], e["DCOL"] + e["DCOLS"])
                            for r in range(e["DROW"], e["DROW"] + e["DROWS"])}
        covered |= game_lib.mark_cells(self)        # D3-8d: screen-only overlay
        covered |= self.dn_cells()                  # D3-11: the flying numbers (screen-only overlay)
        bad = []
        for r in range(PLAY_ROWS):
            for c in range(32):
                if (c, r) in covered:
                    continue
                g, a = room_model.expected_cell(*tabs, c, r)
                if (attr_at(fr, c, r) != a or bytes(cell_bytes(fr, c, r)) != g) \
                        and not game_lib.drip_shown(fr, drip, c, r):
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
                self.turn("WAIT")
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
                self.turn("WAIT")
        return False

    def put_item(self, idx, rb, col, typ, qty=1):
        """FLOOR1: FLOOR_LIST entry idx = (rb, col, typ, qty) and the T_ITEM0 + k markers over its
        2x2 cells in ROOM_MAP (rb = room | FL_S1); call fi_refresh after."""
        self.z.cmd("write-memory %d %d %d %d %d" % (S["FLOOR_LIST"] + idx * S["FL_STRIDE"], rb, col, typ, qty))
        s1 = 1 if rb & S["FL_S1"] else 0
        top = S["STOREY_ROWS"] * s1 + S["STOREY_AIR"] - 2
        for k, r in enumerate((top, top + 1)):
            self.wmem(S["ROOM_MAP"] + r * 32 + col, [S["T_ITEM0"] + 2 * s1 + k] * 2)

    def fi_refresh(self, draw=True):
        """FLOOR1: at the wait_tick probe, far3 fi_full(CUR_ROOM) (the glyph cache
        from FLOOR_LIST) and, draw=True, fi_cells over the whole room + present_full
        (the items on both screens); play resumes at the probe."""
        pc0 = self.pc()
        w = lambda n: list(S[n].to_bytes(2, "little"))   # noqa: E731
        code = [0xF3, 0x3A] + w("PORT_7FFD_SHADOW") + [0xF5, 0x3A] + w("CUR_ROOM") + \
               [0x21] + w("fi_full") + [0xCD] + w("far3")
        if draw:
            code += [0x01, 0, 0, 0x11, S["PLAY_ROWS"], 32, 0xCD] + w("fi_cells") + [0xCD] + w("present_full")
        code += [0xF1, 0xCD] + w("restore_page") + [0xFB]
        ok = self.run_stub(code, org=S["LOWRAM_END_3B"])
        self.z.cmd("set-register PC=%d" % pc0)
        return ok

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
        f0, n = kind_frames(k)
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
            self.turn("WAIT")
            if self.rb("GAME_STATE") == GS_DEAD:
                return True
        return False

    def enter_to_select(self):
        ok = self.end_to_menu()                 # C3-6b: a digit / ENTER after a release
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
            p.wb("ANIM_FREEZE", 1)
            hold_torches(p)                   # C3-6: the torches hold frame 0
            golden(h, "game_select", p.frame())
            p.boot(K_KNIGHT)
            e = p.ent(0)
            h.expect("1 GS_PLAYING", p.rb("GAME_STATE"), GS_PLAYING)
            h.expect("1 HERO_KIND knight", p.rb("HERO_KIND"), K_KNIGHT)
            h.expect("1 CUR_ROOM A", p.rb("CUR_ROOM"), 0)
            h.expect("1 x", e["X"], 2)
            h.expect("1 y", e["Y"], Y1)
            h.expect("1 hp", e["HP"], 24)             # B20: Warrior HP 24 (game.md 4.0)
            h.expect("1 potions", e["POT"], 1)
            golden(h, "game_start", p.frame())
            h.expect("1 GEN_OVERFLOW 0 after boot + hero gen", p.rb("GEN_OVERFLOW"), 0)
            # A5: gen_frame never runs while GEN_SCRATCH (= room maps) is live
            h.expect("1 GEN_TRAP 0 after boot + hero gen", p.rb("GEN_TRAP"), 0)
            h.expect("1 SEQ_TRAP 0 after boot + hero gen", p.rb("SEQ_TRAP"), 0)
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
                p.turn("WAIT")
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
            p.turn("WAIT")
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
                    p.turn("WAIT")
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
                p.turn("WAIT")
                xs.append(p.ent(SLOT_RAT)["X"])
                if FID["rat_bite"] in p.trace_fids(SLOT_RAT) or p.ent(0)["HP"] < 24:
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
                p.turn("WAIT")
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
            h.expect("20 trace HURT then DEAD (the shared corpse, CORPSE-ASHES)",
                     FID["skeleton_hurt"] in tr and FID["small_corpse"] in tr, True)
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
                p.turn("WAIT")
                if p.rb("GAME_STATE") == GS_DEAD:
                    break
            h.expect("21 hero dies -> GS_DEAD", p.rb("GAME_STATE"), GS_DEAD)
            h.expect("22 hp never underflows (0)", p.ent(0)["HP"], 0)
            h.expect("21 ENTER -> GS_SELECT", p.end_to_menu(), True)
            p.settle()
            p.hold("1")
            p.wait_state(GS_PLAYING)
            p.release()
            p.settle()
            h.expect("21 new game POTIONS_TAKEN = 0", p.rb("POTIONS_TAKEN"), 0)
            h.expect("21 new game hero hp 24", p.ent(0)["HP"], 24)
            h.expect("21 new game skeleton back in C", (p.ent(SLOT_SKC)["ROOM"], p.ent(SLOT_SKC)["HP"]), (ROOM_C, 10))
            h.expect("21 new game RNG reseeded", p.rw("RNG_STATE"), 0xA55A)

        # ---------------- 19. D3-0: no ranged attack without a spell ----------
        # (was the PROTO reach-3 zap; game.md §5 / §11.4: a Mage with no spell
        # has only the staff melee). A rat at gap 3: L walks, nothing swings.
        if want(19):
            p.boot(K_WIZARD)
            p.isolate(keep=(SLOT_RAT,))
            p.place(0, 6, Y1)
            p.place(SLOT_RAT, 12, R1)            # wizard cols 6-8: gap 3
            p.settle()
            hp0 = p.ent(SLOT_RAT)["HP"]
            p.clear_trace()
            p.turn("L")
            atk = {FID[n] for n in ("wizard_cast1", "wizard_cast2",
                                    "wizard_staffraise", "wizard_staffswing")}
            h.expect("19 wizard at gap 3: no attack frame traced",
                     [f for f in p.trace_fids(0) if f in atk], [])
            h.expect("19 wizard walked (x 6 -> 7), rat untouched",
                     (p.ent(0)["X"], p.ent(SLOT_RAT)["HP"]), (7, hp0))

        # ---------------- 66. C3-7 hero frames: Mage staff melee + jump arcs ---
        if want(66):
            def runs(seq):
                out = []
                for f in seq:
                    if not out or out[-1][0] != f:
                        out.append([f, 0])
                    out[-1][1] += 1
                return out

            def jump_check(tag, hero, keys, x0, left):
                j1, j2 = FID[hero + "_jump1"], FID[hero + "_jump2"]
                p.isolate()
                p.place(0, x0, Y1, flags=EF_ACTIVE | 2 | (EF_LEFT if left else 0))
                p.turn("WAIT")                   # no two jumps in a row (§2.4)
                p.settle()
                smp, want_f = [], []

                def jt(fr, e):
                    smp.append((e["DFID"], e["DFPX"], e["DCOL"]))
                    want_f.append(p.rb(S["SLOTREC"] + 1))   # slot 0 R_FID (anim output)
                ok = p.turn(*keys, per_tick=jt)
                r = runs([d for d in want_f if d in (j1, j2)])
                h.expect(f"66 {tag}: jump ran, x {'-' if left else '+'}6",
                         (ok, p.ent(0)["X"]), (True, x0 - 6 if left else x0 + 6))
                # ANIM-IMPORT2 J-a: JUMP1 crouch at take-off / landing, JUMP2 every airborne tick
                h.expect(f"66 {tag}: arc frames JUMP1 -> JUMP2 x12 -> JUMP1",
                         [(f, n if f == j2 else 1) for f, n in r], [(j1, 1), (j2, 12), (j1, 1)])
                h.expect(f"66 {tag}: drawn JUMP2 x12, then the landing JUMP1",
                         ([n for f, n in runs([d for d, _, _ in smp if d in (j1, j2)]) if f == j2],
                          p.ent(0)["DFID"], bool(p.ent(0)["FLAGS"] & EF_LEFT)), ([12], j1, left))
                h.expect(f"66 {tag}: JUMP2 drawn at shift 4 and 0 (MOT frame), JUMP1 only aligned",
                         (any(d == j2 and px % 8 == 4 for d, px, _ in smp),
                          any(d == j2 and px % 8 == 0 for d, px, _ in smp),
                          [(d, px) for d, px, _ in smp if d == j1 and px % 8][:2]), (True, True, []))
                # ax = ax_L = 0 (24-px frames): the frame box is the body box
                # in both facings, so the drawn column == px // 8 every tick
                h.expect(f"66 {tag}: frame box == body box (no jump of the body)",
                         [(d, px, c) for d, px, c in smp if d in (j1, j2) and c != px // 8][:2], [])

            # Mage melee (gap 0): STAFF_RAISE wind-up -> STAFF_SWING, IMPACT on the swing
            p.boot(K_WIZARD)
            p.isolate(keep=(SLOT_RAT,))
            p.place(0, 6, Y1)
            p.place(SLOT_RAT, 9, R1)             # wizard cols 6-8, rat 9-12: gap 0
            p.set_ent(SLOT_RAT, FLAGS=EF_ACTIVE | EF_HOSTILE)
            p.settle()
            p.clear_trace()
            # a breakpoint on do_impact (an extra probe: tick() returns there
            # once mid-tick): HL = the sequence entry carrying SF_IMPACT
            p.z.cmd("set-breakpoint 5 PC=%d" % S["do_impact"])
            p.extra_probes = {S["do_impact"]}
            imps = []

            def chk66(frame, e):
                if p.pc() == S["do_impact"]:
                    r = p.z.cmd("get-registers")
                    hl = int(re.search(r"HL=([0-9a-fA-F]{4})", r).group(1), 16)
                    ix = int(re.search(r"IX=([0-9a-fA-F]{4})", r).group(1), 16)
                    imps.append((ix, p.rb(hl), p.rb(hl + 2), p.rb(hl - 3), p.rb(hl - 2)))
            ok = p.turn("L", per_tick=chk66)
            p.load_breakpoints()
            tr = [f for f in p.trace_fids(0)
                  if f in (FID["wizard_staffraise"], FID["wizard_staffswing"],
                           FID["wizard_cast1"], FID["wizard_cast2"])]
            h.expect("66 wizard melee: drawn STAFF_RAISE -> STAFF_SWING (no CAST)",
                     (ok, tr), (True, [FID["wizard_staffraise"], FID["wizard_staffswing"]]))
            # (hero IX, impact entry fid, its flags & SF_IMPACT, previous fid, its ticks)
            h.expect("66 wizard melee: one IMPACT, on the STAFF_SWING entry after a 2-tick STAFF_RAISE",
                     [(f, fl & 1, pf, pt) for ix, f, fl, pf, pt in imps if ix == S["P_ENTITIES"]],
                     [(FID["wizard_staffswing"], 1, FID["wizard_staffraise"], 2)])   # (the rat may hit back)
            h.expect("66 wizard melee: x unchanged", p.ent(0)["X"], 6)
            p.set_ent(SLOT_RAT, ROOM=NOWHERE)
            jump_check("wizard right", "wizard", ("K", "L"), 12, False)
            jump_check("wizard left (mirrored)", "wizard", ("K", "H"), 20, True)
            p.boot(K_KNIGHT)
            jump_check("knight right", "knight", ("K", "L"), 12, False)
            jump_check("knight left (mirrored)", "knight", ("K", "H"), 20, True)

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
            h.expect("35 arrive mid-ladder at the top of C's shaft x=24 (H1)", (e["X"], e["Y"]), (24, 0))
            h.expect("35 after B->C scroll: screen == room C tiles", p.bg_mismatch()[:4], [])
            g = p.ent(SLOT_GOBLIN)
            h.expect("26 goblin room = C, pending", (g["ROOM"], bool(g["FLAGS"] & EF_PENDING)), (ROOM_C, True))
            h.expect("26 bat does not follow", p.ent(SLOT_BATB)["ROOM"], 1)
            p.turn("J")                          # H1: climb down to storey 0 (2 turns)
            p.turn("J")
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
            p.turn("K")                          # H1: up-exit = a step (y 1) ...
            h.expect("35 K: one step up C's up-exit shaft, still in C", (p.rb("CUR_ROOM"), p.ent(0)["Y"]), (ROOM_C, 1))
            p.turn("K")                          # ... then head on row 0 + the transition
            e = p.ent(0)
            h.expect("35 K -> back in B mid-ladder at the shaft bottom x=24 (H1)", (p.rb("CUR_ROOM"), e["X"], e["Y"]),
                     (1, 24, PLAY_ROWS - 6))
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

        # ---------------- 53 (review A7) present keeps up: melee, potion, quaff
        # Per tick, right after the tick-start present (probe_presented):
        # displayed bank 7 == composed bank 5, through a wizard staff melee
        # (D3-0: was the zap overlay), a potion pickup (shadow_rect + PEND_DMG +
        # message) and a quaff (attr flash + HUD).
        if want(53):
            p.boot(K_WIZARD)
            p.isolate(keep=(SLOT_RAT,))
            p.place(0, 6, Y1)
            p.place(SLOT_RAT, 9, R1)             # gap 0: staff melee
            p.present_watch(True)
            p.clear_trace()
            p.turn("L")
            zapped = FID["wizard_staffswing"] in p.trace_fids(0)
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
            h.expect("53 setup: staff swing, potion taken, quaff", (zapped,
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
            p.end_to_menu()
            p.settle()
            p.menu_start(K_WIZARD, settle=None)  # '2' toggles HERO, '1' starts (C3-6 menu)
            wz0, wzn = kind_frames(K_WIZARD)
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

        # ---------------- 55-58 flyers vs ladder ends ----------------------
        # J1 (user 2026-10-06, prototype §3.5 / §6.4): FREE FLIGHT. Ladder
        # shafts and ladder-end boxes are ordinary air for flyers: they may
        # enter, cross, stop (dx = 0), wait and attack inside a box (the B8
        # cross-or-leave rule of 2026-10-02 is dropped). Only the hero's climb
        # is protected: anti-cork, forced yield on a blocked climb (a WAIT
        # turn), vertical fallback, squeeze past (#62-#65), B16.
        # Room A ladders {5,1}, {23,1} (B3B-3: both link storey 1 to storey 0;
        # their top end boxes are on storey 0). Fixed seed; flyer speeds unchanged.
        if want(55) or want(56) or want(57) or want(58):
            p.boot(K_KNIGHT)
            segs = ladder_segs(p, ROOM_A)

        if want(55):
            p.isolate()
            p.place(0, 5, Y1)                       # foot of {5,1}, storey 1
            p.place(SLOT_GHOST, 5, G0 - 1, room=0)  # INSIDE the top end box (storey 0)
            g_in = in_end_box(p, p.ent(SLOT_GHOST), segs)
            gx = []
            for w_ in range(3):                     # hero waits: the ghost may idle
                p.turn("WAIT")
                gx.append(p.ent(SLOT_GHOST)["X"])
            g_still = in_end_box(p, p.ent(SLOT_GHOST), segs)
            t0 = p.rw("TURN_COUNTER")
            up = p.climb("K")                       # the climb still gets past
            n_up = p.rw("TURN_COUNTER") - t0
            y_top = p.ent(0)["Y"]
            down = p.climb("J")
            h.expect("55 setup: ghost placed inside the top end box of {5,1}",
                     len(g_in) == 3, True)
            h.expect("55 free flight: the ghost idles in the end box (x kept, 3 waits)",
                     (gx, len(g_still)), ([5, 5, 5], 3))
            h.expect("55 hero still climbs {5,1} up past it (<= 9 + 3 turns)",
                     (up, y_top, n_up <= STOREY_ROWS + 3), (True, Y0, True))
            h.expect("55 hero climbs back down", (down, p.ent(0)["Y"]), (True, Y1))
            # bat wander (other storey) crosses shafts and keeps moving
            p.isolate()
            p.place(0, 14, Y1)                      # hero on storey 1
            p.place(SLOT_BATB, 12, R0 - 3, room=0)  # bat B on storey 0
            xs, crossed = set(), 0
            for i in range(40):
                p.turn("WAIT")
                b = p.ent(SLOT_BATB)
                xs.add(b["X"])
                crossed += bool(in_end_box(p, b, segs))
            h.expect("55 bat keeps moving (>= 4 distinct cols in 40 turns)", len(xs) >= 4, True)
            h.expect("55 bat crosses a shaft (turns ended in a box > 0)", crossed > 0, True)

        # 56: the Ghost crosses the {23,1} shaft (storey 0 box cols 23..25) to
        # reach the hero (91cf829 made shafts walls: it stopped at x 26).
        if want(56):
            p.isolate()
            p.place(0, 12, Y0)                      # hero storey 0, cols 12..14
            p.place(SLOT_GHOST, 27, G0 - 1, room=0, flags=EF_ACTIVE | EF_HOSTILE | EF_LEFT)
            gx, inbox = [], 0
            for i in range(16):
                p.turn("WAIT")
                g = p.ent(SLOT_GHOST)
                gx.append(g["X"])
                inbox += bool(in_end_box(p, g, segs))
            h.expect("56 ghost crosses the shaft: 5 turns in its end box", inbox, 5)
            h.expect("56 ghost reaches the hero (x 16, gap 1 = reach)", gx[-1], 16)
            h.expect("56 ghost x strictly decreasing to 16",
                     gx[:11], list(range(26, 15, -1)))

        # 57: free flight: the Ghost stops and fights INSIDE a ladder-end box.
        # Hero at x 2 (cols 2..4) beside {5,1}'s top box (cols 5..7). Ghost
        # from x 9: 8 (gap 3) -> 7 (in, gap 2) -> 6 (in, gap 1 = reach) ->
        # stays at 6 and attacks (B8 made it move on to 5 first).
        if want(57):
            p.isolate()
            p.place(0, 2, Y0)
            p.place(SLOT_GHOST, 9, G0 - 1, room=0, flags=EF_ACTIVE | EF_HOSTILE | EF_LEFT)
            seq = []
            for i in range(6):
                modes = set()
                p.turn("WAIT", per_tick=lambda fr, e: modes.add(p.ent(SLOT_GHOST)["MODE"]))
                seq.append((p.ent(SLOT_GHOST)["X"], S["M_SEQ"] in modes))
            h.expect("57 ghost x per turn 8,7,6,6,6,6 (stops in the box, in reach)",
                     [x for x, _ in seq], [8, 7, 6, 6, 6, 6])
            h.expect("57 ghost attacks from inside the box on turns 4..6 (M_SEQ), not before",
                     [a for _, a in seq], [False, False, False, True, True, True])

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
            # C3-8a: DOWN with no ladder below is a WAIT now (game.md §2.3 / §3.1,
            # deferred 3 ticks): it used to be a free no-op in the PROTO input.
            h.expect("59 DOWN on the bottom storey, no hole: a wait (1 turn)", p.turn("J"), True)
            p.place(0, 5, Y0)                       # top of {5,1} (storey 0)
            h.expect("59 UP at a down-only shaft top: no turn", p.no_turn("K"), True)
            h.expect("59 CLIMB_BLK clear after a terrain block", p.rb("CLIMB_BLK"), 0)

        # 62 (B14, user 2026-10-04: "a ghost blocks the ladder when a wall is
        # nearby"). Room A {5,1} (top box storey 0 cols 5..7, bottom box
        # storey 1); a solid column poked into ROOM_MAP (logic only, the
        # screen is not redrawn). The hero climbs K from the foot (x 5,
        # storey 1) and must stand on storey 0 within N turns.
        #  a: Ghost on the top box, wall at col 9 (one free col past the box):
        #     the yield went right (roomier side) 5 -> 6, the wall stopped
        #     it, the fallback went back 6 -> 5, "roomier" again ... for ever.
        #     Now, on the shaft col, the yield keeps its facing.
        #  b / c: Bat hovering over the hero's head at the foot (storey-1 band
        #     top, in the bottom box), wall left / right: the climb START is
        #     blocked (a wait), but the hero was standing, so no yield rule
        #     applied and the boxed bat stayed for ever. Now a blocked climb
        #     makes the monster phase yield to it (CLIMB_BLK -> cork_check).
        if want(62):
            def b14(tag, wall_col, wall_rows, slot, gx, gy, flags, n):
                p.boot(K_KNIGHT)
                p.isolate()
                for r_ in wall_rows:
                    p.wb(S["ROOM_MAP"] + 32 * r_ + wall_col, S["T_BRICK"])
                p.place(0, 5, Y1)
                p.place(slot, gx, gy, room=0, flags=flags)
                t0, path = p.rw("TURN_COUNTER"), []
                for _ in range(n):
                    if p.ent(0)["Y"] == Y0:
                        break
                    if not p.turn("K"):
                        p.turn("WAIT")
                    path.append((p.ent(0)["Y"], p.ent(slot)["X"], p.ent(slot)["Y"]))
                h.expect(f"62{tag}: hero reaches storey 0 on {{5,1}} within {n} turns",
                         (p.ent(0)["X"], p.ent(0)["Y"], p.rw("TURN_COUNTER") - t0 <= n), (5, Y0, True))
                return path
            # bounds: 9 climbing turns + the waits (a: none, the ghost yields
            # while the hero is still below it; b / c: the waits while the bat
            # sidesteps off the 3-col path (B18: a blocker that moved since its
            # last block earns another wait, up to CLIMB_SQZ_N blocks), then
            # the climb (or the squeeze))
            path = b14("a ghost on the top box, wall col 9", 9, range(0, 8), SLOT_GHOST, 5, 1,
                       EF_ACTIVE | EF_HOSTILE, 9)
            h.expect("62a ghost never steps back toward the wall (x non-increasing)",
                     all(b[1] <= a[1] for a, b in zip(path, path[1:])), True)
            b14("b bat over the foot, wall col 4", 4, range(9, 17), SLOT_BATB, 5, 9,
                EF_ACTIVE | EF_HOSTILE | EF_LEFT, 11 + SQZ_EXTRA)
            b14("c bat over the foot, wall col 8", 8, range(9, 17), SLOT_BATB, 5, 9,
                EF_ACTIVE | EF_HOSTILE, 11 + SQZ_EXTRA)

        # 63 (B14 review): two-body livelocks and the squeeze-past guarantee
        # (designer 2026-10-04, prototype §6.4 "B14 fix rules"). Walls poked
        # into ROOM_MAP as in #62. Room A {5,1}, hero at its foot climbing K.
        if want(63):
            import textpack
            names = [n for n, _ in textpack.read_strings()]
            ents, strs = textpack.encode([t for _, t in textpack.read_strings()])

            def msg_text():
                raw = p.z.read_memory(S["MSG_BUF"], 32)
                out = ""
                for b_ in raw:
                    if b_ == 0:
                        break
                    out += "".join(chr(c & 0x7F) for c in ents[b_ - 0x80]) if b_ >= 0x80 else chr(b_)
                return out

            def setup(walls, bodies):
                p.boot(K_KNIGHT)
                p.isolate()
                for col, rows in walls:
                    for r_ in rows:
                        p.wb(S["ROOM_MAP"] + 32 * r_ + col, S["T_BRICK"])
                p.place(0, 5, Y1)
                for slot, kind, x, y, fl in bodies:
                    p.set_ent(slot, KIND=kind, HP=p.rb(S["kind_tab"] + S["KT_HP"] + kind))
                    p.place(slot, x, y, room=0, flags=fl)

            def climb(n):
                t0 = p.rw("TURN_COUNTER")
                for _ in range(n):
                    if p.ent(0)["Y"] == Y0:
                        break
                    if not p.turn("K"):
                        p.turn("WAIT")
                return p.ent(0)["Y"] == Y0 and p.rw("TURN_COUNTER") - t0 <= n

            HB = EF_ACTIVE | EF_HOSTILE
            # (a) squeeze past: a Bat over the hero's head in a 3-col corridor
            # (walls at cols 4 and 8, storey 1): it can neither leave sideways
            # nor up. 1st K: a wait; 2nd K: the squeeze.
            setup([(4, range(9, 17)), (8, range(9, 17))], [(SLOT_BATB, K_BAT, 5, 9, HB | EF_LEFT)])
            t0 = p.rw("TURN_COUNTER")
            p.turn("K")
            e, b = p.ent(0), p.ent(SLOT_BATB)
            h.expect("63a 1st blocked climb: a wait (1 turn), hero still at the foot, CLIMB_BLK_N 1",
                     (p.rw("TURN_COUNTER") - t0, e["Y"], p.rb("CLIMB_BLK_N")), (1, Y1, 1))
            hp0 = e["HP"]
            p.turn("K")
            e, b = p.ent(0), p.ent(SLOT_BATB)
            h.expect("63a 2nd blocked climb by the same bat: squeeze (1 turn), hero y 10 "
                     "mid-ladder, bat PENDING at the foot (x 5, standing y 15), counter cleared",
                     (p.rw("TURN_COUNTER") - t0, e["Y"], bool(b["FLAGS"] & EF_PENDING), b["X"], b["Y"],
                      p.rb("CLIMB_BLK_N")), (2, Y1 - 1, True, 5, R1, 0))
            h.expect("63a no free attack from the squeeze (HP kept)", e["HP"], hp0)
            h.expect("63a log line", msg_text(), "YOU SQUEEZE PAST THE BAT")
            h.expect("63a hero then reaches storey 0 (8 more turns)", climb(8), True)
            p.turn("WAIT")
            p.turn("WAIT")
            b = p.ent(SLOT_BATB)
            h.expect("63a the bat materialised again once its box was free",
                     bool(b["FLAGS"] & EF_PENDING), False)
            # (b) a Ghost filling a 3-col corridor on the top box (walls at
            # cols 4 and 8, storey 0): it yields neither way; the hero waits
            # once when his head reaches it, then squeezes past.
            setup([(4, range(0, 8)), (8, range(0, 8))], [(SLOT_GHOST, K_GHOST, 5, 1, HB)])
            h.expect("63b ghost in a corridor: hero reaches storey 0 within 11 turns", climb(11), True)
            h.expect("63b it was a squeeze", msg_text(), "YOU SQUEEZE PAST THE GHOST")
            # (c) two-body livelock: Ghost on the top box, a Bat right beside it
            # (the ghost's facing side), a wall on the other side.
            setup([(4, range(0, 8))], [(SLOT_GHOST, K_GHOST, 5, 1, HB),
                                       (SLOT_BATB, K_BAT, 8, 1, HB)])
            h.expect("63c ghost + bat + wall: hero reaches storey 0 within 12 turns", climb(12), True)
            # (d) two bats over the foot (storey 1), wall left
            setup([(4, range(9, 17))], [(SLOT_BATB, K_BAT, 5, 9, HB | EF_LEFT),
                                        (SLOT_BATD, K_BAT, 7, 9, HB | EF_LEFT)])
            h.expect("63d two bats + wall: hero reaches storey 0 within 12 turns", climb(12), True)
            # (e) the vertical fallback (yield only, B8 ladder-end rule): a Bat
            # (3 cols wide) filling a 3-col corridor (walls 4 / 8) on the top
            # box at rows 1..2; hero mid-ladder below. Both x steps blocked: it
            # may only move up out of the climb path (y 0: rows 0..1, above the
            # standing box rows 2..7), never stay on it.
            setup([(4, range(0, 8)), (8, range(0, 8))], [(SLOT_BATB, K_BAT, 5, 1, HB)])
            p.place(0, 5, Y1 - 3)
            p.set_ent(0, AIDIR=0xFF)
            ys = []
            for _ in range(4):
                p.turn("K")
                ys.append((p.ent(SLOT_BATB)["X"], p.ent(SLOT_BATB)["Y"],
                           bool(p.ent(SLOT_BATB)["FLAGS"] & EF_PENDING)))
            h.expect("63e bat's vertical yield ends off the path (x 5, y 0), never pending "
                     "(no squeeze needed)", ys, [(5, 0, False)] * 4)
            h.expect("63e hero reaches storey 0 within 9 turns", climb(9), True)

        # 64 / 65 shared setup: room A {5,1} (top box storey 0 cols 5..7,
        # bottom box storey 1), walls poked into ROOM_MAP (logic only).
        HB = EF_ACTIVE | EF_HOSTILE

        def fly_setup(walls, hero, bodies):
            p.boot(K_KNIGHT)
            p.isolate()
            for col, rows in walls:
                for r_ in rows:
                    p.wb(S["ROOM_MAP"] + 32 * r_ + col, S["T_BRICK"])
            p.place(0, *hero)
            for slot, kind, x, y, fl in bodies:
                p.set_ent(slot, KIND=kind, HP=p.rb(S["kind_tab"] + S["KT_HP"] + kind))
                p.place(slot, x, y, room=0, flags=fl)

        def band_of(slot):
            """(storey, lo, hi) of a flyer's air band from its current y."""
            e = p.ent(slot)
            _, h_ = body(p, e["KIND"])
            s_ = storey_of(e["Y"], h_)
            return s_, STOREY_ROWS * s_, STOREY_ROWS * s_ + STOREY_ROWS - 1 - h_

        def drive(key, goal_y, n, slots):
            """Press key (SPACE if illegal) until the hero stands at goal_y or
            n turns pass. Returns (reached in <= n turns, [band violations]):
            a violation = a flyer (pending or not) outside the air band of the
            storey it started in, or in another room."""
            bands = {s_: band_of(s_) for s_ in slots}
            bad, t0 = [], p.rw("TURN_COUNTER")
            for _ in range(n + 4):
                if p.ent(0)["Y"] == goal_y and is_standing(goal_y, 6):
                    break
                if not p.turn(key):
                    p.turn("WAIT")
                for s_, (st, lo, hi) in bands.items():
                    e = p.ent(s_)
                    if not (lo <= e["Y"] <= hi) or e["ROOM"] != 0:
                        bad.append((s_, e["X"], e["Y"], e["ROOM"]))
            return p.ent(0)["Y"] == goal_y and p.rw("TURN_COUNTER") - t0 <= n, bad[:3]

        # 64 (B15, user 2026-10-05, seen on a build without the B14 fixes):
        # the hero on the TOP of {5,1} climbing DOWN, a flyer beside the
        # shaft with a wall on its far side. The B14 rules (forced yield,
        # squeeze past) must work for a downward climb exactly as upward.
        # A storey-0 flyer can never overlap a down climb from the top (the
        # hero's own standing box covers rows 2..7), so the blockers that
        # matter hover over the FOOT (storey 1, the hero's path rows 9..16);
        # the literal report (ghost left of the top box, wall left) is case e.
        if want(64):
            cases = [  # tag, walls, slot, kind, x, y, flags
                ("a ghost storey 1 left of the shaft, wall left", [(2, range(9, 17))],
                 SLOT_GHOST, K_GHOST, 3, 10, HB),
                ("b ghost storey 1 right of the shaft, wall right", [(10, range(9, 17))],
                 SLOT_GHOST, K_GHOST, 7, 10, HB | EF_LEFT),
                ("c bat storey 1 left, wall left", [(2, range(9, 17))],
                 SLOT_BATB, K_BAT, 3, 9, HB),
                ("d bat storey 1 right, wall right", [(10, range(9, 17))],
                 SLOT_BATB, K_BAT, 7, 9, HB | EF_LEFT),
                ("e ghost storey 0 left of the top box, wall left", [(1, range(0, 8))],
                 SLOT_GHOST, K_GHOST, 2, 1, HB),
                ("f ghost storey 0 right of the top box, wall right", [(11, range(0, 8))],
                 SLOT_GHOST, K_GHOST, 8, 1, HB | EF_LEFT),
                ("g ghost on the shaft col over the foot, wall left", [(4, range(9, 17))],
                 SLOT_GHOST, K_GHOST, 5, 9, HB),
                ("h ghost storey 1 corridor (walls 4 / 8): squeeze", [(4, range(9, 17)), (8, range(9, 17))],
                 SLOT_GHOST, K_GHOST, 5, 10, HB),
            ]
            for tag, walls, slot, kind, x, y, fl in cases:
                fly_setup(walls, (5, Y0), [(slot, kind, x, y, fl)])
                ok, bad = drive("J", Y1, 12 + SQZ_EXTRA, [slot])   # (B18: yield waits, see 62)
                h.expect(f"64{tag}: hero descends {{5,1}} to storey 1 within {12 + SQZ_EXTRA} turns", ok, True)
                h.expect(f"64{tag}: the flyer stays in its band", bad, [])

        # 65 (B16, user 2026-10-05: "a ghost sometimes falls to the floor
        # below"): flyers never leave their storey band. Root cause: the B14
        # squeeze moved every blocker to the hero's foot cell on the storey
        # the climb LEAVES, so a flyer of the other storey (a ghost over the
        # top box when the hero climbs up from storey 1) was dropped onto
        # the floor below. (a) the #63b corridor squeeze, up; (b) down;
        # (c) a deterministic fuzz: flyers anywhere near both shafts of room
        # A, the hero climbing / walking / waiting around them.
        if want(65):
            fly_setup([(4, range(0, 8)), (8, range(0, 8))], (5, Y1),
                      [(SLOT_GHOST, K_GHOST, 5, 1, HB)])
            ok, bad = drive("K", Y0, 11, [SLOT_GHOST])
            h.expect("65a ghost squeezed on the up climb: hero on storey 0 within 11 turns", ok, True)
            h.expect("65a the ghost never leaves its storey-0 band", bad, [])
            fly_setup([(4, range(0, 8)), (8, range(0, 8))], (5, Y1),
                      [(SLOT_BATB, K_BAT, 5, 3, HB)])
            ok, bad = drive("K", Y0, 11, [SLOT_BATB])
            h.expect("65a' bat (rows 3..4) in the top corridor: hero up within 11 turns", ok, True)
            h.expect("65a' the bat never leaves its storey-0 band", bad, [])
            fly_setup([(4, range(9, 17)), (8, range(9, 17))], (5, Y0),
                      [(SLOT_BATB, K_BAT, 5, 13, HB)])
            ok, bad = drive("J", Y1, 12, [SLOT_BATB])
            h.expect("65b bat squeezed on the down climb: hero on storey 1 within 12 turns", ok, True)
            h.expect("65b the bat never leaves its storey-1 band", bad, [])
            import random
            rnd = random.Random(16)
            viol = []
            for it in range(int(os.environ.get("FUZZ65", "24"))):
                col = rnd.choice((5, 23))
                kind, slot = rnd.choice(((K_GHOST, SLOT_GHOST), (K_BAT, SLOT_BATB)))
                _, fh = body(p, kind)
                fs = rnd.randint(0, 1)
                fy = rnd.randint(STOREY_ROWS * fs, STOREY_ROWS * fs + STOREY_ROWS - 1 - fh)
                fx = max(1, min(27, col + rnd.randint(-4, 4)))
                walls = []
                if rnd.random() < 0.6:
                    wc = fx - 1 if rnd.random() < 0.5 else fx + 3
                    if 1 <= wc <= 30 and not (col - 1 <= wc <= col + 3):
                        walls.append((wc, range(STOREY_ROWS * fs, STOREY_ROWS * fs + STOREY_ROWS - 1)))
                hero_s = rnd.randint(0, 1)
                hy = Y0 if hero_s == 0 else Y1
                fw = body(p, kind)[0]
                if fx < col + 3 and col < fx + fw and fy < hy + 6 and hy < fy + fh:
                    continue                        # starts inside the hero
                fly_setup(walls, (col, hy),
                          [(slot, kind, fx, fy, HB | (EF_LEFT if rnd.random() < 0.5 else 0))])
                fl = p.ent(slot)
                if fl["FLAGS"] & EF_PENDING:
                    continue
                st, lo, hi = band_of(slot)
                for t_ in range(14):
                    k_ = rnd.choice(("J", "K") * 3 + ("H", "L", "WAIT"))
                    if not p.turn(k_):
                        p.turn("WAIT")
                    e = p.ent(slot)
                    if not (lo <= e["Y"] <= hi) or e["ROOM"] != 0:
                        viol.append((it, col, kind, fx, fy, t_, e["X"], e["Y"]))
                        break
            h.expect("65c fuzz: no flyer ever leaves its storey band", viol[:3], [])

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
            h.expect("32 quaff hp 10 -> 22 (Heal +12, MORE-MON)", e["HP"], 22)
            h.expect("32 potions 1 -> 0", e["POT"], 0)
            h.expect("32 TURN_COUNTER += 1", p.rw("TURN_COUNTER") - tc, 1)
            h.expect("32 G with 0 potions: no turn", p.no_turn("G"), True)
            # 3E-T11: potions live in the BAG (E_POT = its potion count, pot_sync):
            # poke one Heal into the bag (+ the count the poke bypasses)
            p.wmem(S["BAG"], [S["IT_P_HEAL"], 1, 0])
            p.set_ent(0, HP=20, POT=1)
            p.turn("G")
            h.expect("32 heal capped at max", p.ent(0)["HP"], 24)
            # 33: a full BAG (20 gear records; was E_POT 9) refuses the potion
            p.wmem(S["BAG"], [S["IT_W_LONG"], 1, 0] * S["BAG_SLOTS"])
            pot33 = p.ent(0)["POT"]
            p.place(0, 24, Y0)
            for _ in range(3):
                p.turn("L")
            h.expect("33 full bag: the potion count stays", p.ent(0)["POT"], pot33)
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
                p.turn("WAIT")
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

        # ---------------- 46 (review B) a mid-ladder body blocks the reach line
        # (D3-0: was the zap line at gap 3; with reach 1 the climber sits at
        # gap 0 in front of a rat at gap 1, overlapping its cols).
        if want(46):
            def swing_past_climber(with_goblin):
                p.boot(K_WIZARD)
                p.isolate()
                p.place(0, 28, Y1)
                p.turn("L")
                p.turn("L")
                p.until(lambda: p.rb("CUR_ROOM") == 1 and p.idle())
                p.isolate()
                p.place(0, 1, Y1)                # storey 1 (the shaft foot), cols 1-3
                p.place(SLOT_RAT, 5, R1, room=1, flags=EF_ACTIVE | EF_HOSTILE | EF_LEFT)
                if with_goblin:                  # mid-ladder on B's {4,1} shaft, cols 4-6
                    p.place(SLOT_GOBLIN, 4, G1 - 1, room=1, flags=EF_ACTIVE | EF_HOSTILE)
                    p.set_ent(SLOT_GOBLIN, AIDIR=0xFF)
                p.settle()
                hp0 = p.ent(SLOT_RAT)["HP"]
                p.clear_trace()
                p.turn("L")
                return FID["wizard_staffswing"] in p.trace_fids(0), hp0
            cast, _ = swing_past_climber(False)
            h.expect("46 control: rat at gap 1 is struck", cast, True)
            cast, hp0 = swing_past_climber(True)
            h.expect("46 climbing goblin in the gap: no swing", cast, False)
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
            p.wb(cell, S["T_ITEM0"] + 3)                # FLOOR1: an item marker (s1 lower), no entry
            p.turn("WAIT")
            h.expect("48 unlisted potion tile: not taken", p.ent(0)["POT"], 1)
            h.expect("48 unlisted potion tile stays in the map", p.rb(cell), S["T_ITEM0"] + 3)
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
        # The .sna enters at `boot`; this loads a private copy of tome-of-the-dead.tap the
        # way a user does (reset -> 128 menu Tape Loader autoload -> BASIC ->
        # CODE -> start -> 2x LD-BYTES into banks 1/3 -> boot).
        if want(50):
            tap = os.path.join(tempfile.mkdtemp(prefix="game_tap_"), "tome-of-the-dead.tap")
            shutil.copyfile(os.path.join(os.environ.get("WZ_BUILD_DIR", os.path.join(os.path.dirname(HERE), "build")),
                                         "tome-of-the-dead.tap"), tap)      # (a variant build: WZ_BUILD_DIR, game_lib)
            p.wb("GAME_STATE", 0)                        # no stale GS_SELECT
            p.z.cmd("set-memory-zone 0")                 # scrub banks 1/3: sources
            for b in (1, 3):                             # must come off the tape
                p.z.cmd("write-memory %d %s" % (b * 16384, " ".join(["0"] * 64)))
            ayo = 3 * 16384 + S["AY_RESERVE"] - 0xC000   # A8: the AY slot block too
            p.z.cmd("write-memory %d %s" % (ayo, " ".join(["0"] * S["AY_LEN"])))
            p.z.cmd("write-memory %d %s" % (S["BANK_TEXT"] * 16384 + S["TEXT_ADDR"] - 0xC000,
                                            " ".join(["0"] * 64)))  # D3-TX text block (tx_tab)
            p.z.cmd("set-memory-zone -1")
            p.z.cmd("disable-breakpoints")
            p.z.cmd("exit-cpu-step")
            p.z.cmd("smartload " + tap)
            t0 = time.monotonic()
            gs = None
            while time.monotonic() - t0 < 60:            # fast tape traps: ~1 s
                time.sleep(0.25)
                gs = p.rb("GAME_STATE")
                if gs in BOOT_WAITS:                     # BOOT-ANYKEY / INSTR: picture + 3 help pages wait
                    p.wb("INPUT_SRC", 1)                 # for a key; inject one (the tape path has
                    p.release()                          # the host keyboard otherwise)
                    time.sleep(0.3)
                    p.hold("ENTER")
                    time.sleep(0.3)
                    p.release()
                    continue
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
            p.wb("ANIM_FREEZE", 1)
            hold_torches(p)                   # C3-6: the torches hold frame 0
            golden(h, "game_select", p.frame())
            p.hold("2")                       # C3-6 menu: '2' only toggles HERO ...
            p.tick()
            p.release()
            p.tick()
            p.hold("1")                       # ... '1' starts the game
            h.expect("51 HERO: WIZARD + '1' starts a wizard game", p.wait_state(GS_PLAYING), True)
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
            p.wb("ANIM_FREEZE", 1)
            hold_torches(p)                   # C3-6: the torches hold frame 0
            # C3-8a: HERO persists across games, so after the wizard game the
            # menu shows HERO: MAGE (no longer == the knight select frame)
            golden(h, "game_select_mage", p.frame())
            p.menu_start(K_KNIGHT)             # HERO persisted as WIZARD: toggle back, start
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
                    # D3-11: a flying number's timing follows the tick's frame budget (the
                    # pass runs only in a 1st-frame tick), so the two runs' windows may
                    # differ: they are masked (both runs' cells) before the compare
                    frames.append((frame[:6144], p.dn_cells()))
                    sk = p.ent(SLOT_SKC)
                    if (sk["DVIS"] & 1 and sk["DCOL"] < hero["DCOL"] + hero["DCOLS"]
                            and hero["DCOL"] < sk["DCOL"] + sk["DCOLS"]):
                        overlap[0] += 1
                    if toggle:
                        flip[0] ^= 1
                        p.set_ent(0, FLT=4, FLA=0x42 if flip[0] else 0x44)
                for _ in range(4):
                    p.turn("WAIT", per_tick=cb)
                return frames, overlap[0]
            fa, ova = skel_turn(False)
            fb, _ = skel_turn(True)
            def near(i):                          # +-2 ticks: an expired number's erase / repair
                cs = set()
                for j in range(max(0, i - 2), min(len(fa), len(fb), i + 3)):
                    cs |= fa[j][1] | fb[j][1]
                return cs
            diff = [i for i, ((a, _), (b, _)) in enumerate(zip(fa, fb))
                    if p.mask_cells(a, near(i)) != p.mask_cells(b, near(i))]
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
            h.expect("37 walkthrough reaches room D storey 0 x 3, still playing (bounded; "
                     "B3B-13: no PROTO chest win)", (res1["gs"], res1["end"]),
                     (GS_PLAYING, (ROOM_D, 3, 0)))
            print(f"[info] walkthrough: {res1['turns']} turns, OVERRUN_COUNT={res1['overrun']}, "
                  f"BLIT_MISS={res1['miss']}, hero hp={res1['hp']}")
            h.expect("40 OVERRUN_COUNT reported (target 0)", res1["overrun"], 0)
            h.expect("40 DMG_OVERFLOW 0 over the walkthrough", res1["dmgov"], 0)
            h.expect("40 CLIP_TRAP 0 over the walkthrough", res1["clip"], 0)
            h.expect("40 GEN_TRAP 0 over the walkthrough (rooms built + scrolled)",
                     res1["gentrap"], 0)
            h.expect("40 SEQ_TRAP 0 over the walkthrough", res1["seqtrap"], 0)
            h.expect("36 WIN (GS_WIN end screen): ENTER -> GS_SELECT", res1["select"], True)
            if want(38):
                res2 = walkthrough(h, p, check14=False)
                h.expect("38 determinism: identical end state", res2["state"], res1["state"])
                # B3B-8: no runtime write into the bank-7 tilesets (before B3B-12)
                from game_lib import SNA_RAM
                p.z.cmd("set-memory-zone 0")
                try:
                    o = 7 * 16384 + S["TSET_BASE"] - 0xC000     # MEM-RECLAIM w2a: one dedup block
                    n = S["B7D_LEN"]
                    h.expect("38 end: bank-7 tilesets == .sna",
                             bytes(p.z.read_memory(o, n)) == SNA_RAM[o:o + n], True)
                finally:
                    p.z.cmd("set-memory-zone -1")

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
    $C000+ with a bank other than 3 paged (A3 review carry-over), except the
    bank-1 UI code region with bank 1 paged (C3 review: far1 targets) and (D3-S2)
    the bank-7 cold code region with bank 7 paged (far7 targets)."""
    # D3-0: stop at the ISR's `call AY_PLAY` (isr.page, bank 2, after the OUT)
    # rather than at AY_PLAY itself: $E000+ is shared by the bank-3 AY slot
    # ($EDA0+ since MEM-SND), the bank-1 UI code (ui1_code..ui1_end, $EC68+)
    # and the bank-7 cold code ($E000+), and a PC probe fires in whichever
    # bank is paged (the scrolls run there).
    ay, done = S["isr.page"], S["isr.done"]
    # A3 carry-over: executing $C000+ with any bank but 3 = a paging bug. A
    # conditional (non-optimised) breakpoint: armed from the snapshot load
    # (boot, select, game start) through the transition below.
    p.load()
    # C3 review: bank-1 code (ui1_code..ui1_end: the scrolls, the info line,
    # entered by far1) is the one other bank allowed to run at $C000+.
    # D3-S2: and the bank-7 cold code (b7_code..b7_end, entered by far7).
    # 3E-T1: and, during boot only, the boot block (BOOT6_ADDR..SRC6_ADDR, bank
    # 6, entered by farb from boot; the pool overwrites it at the hero start).
    # (SRC6 spike: the SRC6 sources SRC6_ADDR..R6_ADDR between it and R6 are
    # data; the boot window below bounds bank-6 PCs only from below.)
    # R6 (2026-10-21): bank-6 code may run in the R6 region (R6_ADDR..r6_code_end,
    # far6 targets) at any time BY DESIGN; only the boot window adds the boot
    # block below it. Breakpoints 12 / 13 bound bank-6 PCs; 12 is re-armed at
    # the menu without the boot block.
    # M0 (L4): bank-0 code may run in the bank-0 cold code b0_code..b0_code_end (farb, BANK_TEXT);
    # M0 (L1): bank-7 code also in the high block b7h_code..b7h_end (after the tilesets).
    p.z.cmd("set-breakpoint 7 PC>=C000H and RAM<>3 and RAM<>1 and RAM<>7 and RAM<>6 and RAM<>0")
    p.z.cmd("set-breakpoint 8 RAM=1 and PC>=C000H and PC<%XH" % S["ui1_code"])
    p.z.cmd("set-breakpoint 9 RAM=1 and PC>=%XH" % S["ui1_end"])
    p.z.cmd("set-breakpoint 10 RAM=7 and PC>=C000H and PC<%XH" % S["b7_code"])
    p.z.cmd("set-breakpoint 11 RAM=7 and PC>=%XH and PC<%XH" % (S["b7_end"], S["b7h_code"]))
    p.z.cmd("set-breakpoint 15 RAM=7 and PC>=%XH" % S["b7h_end"])
    p.z.cmd("set-breakpoint 16 RAM=0 and PC>=C000H and PC<%XH" % S["b0_code"])
    p.z.cmd("set-breakpoint 17 RAM=0 and PC>=%XH" % S["b0_code_end"])
    p.z.cmd("set-breakpoint 12 RAM=6 and PC>=C000H and PC<%XH" % S["BOOT6_ADDR"])
    p.z.cmd("set-breakpoint 13 RAM=6 and PC>=%XH" % S["r6_code_end"])
    # 3F SRC6 is data only: executing inside it (also during boot, when 12 stops
    # at BOOT6_ADDR) is a bug
    p.z.cmd("set-breakpoint 14 RAM=6 and PC>=%XH and PC<%XH" % (S["SRC6_ADDR"], S["R6_ADDR"]))
    p.extra_probes = set()
    p.wait_state(GS_SELECT)
    p.z.cmd("set-breakpoint 12 RAM=6 and PC>=C000H and PC<%XH" % S["R6_ADDR"])
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
    from game_lib import SNA_RAM                 # 3E-T1: the load image is in the boot
    io = S["BANK_BOOT6"] * 16384 + S["isr_image"] - 0xC000   # block (bank 6 tail, pool later)
    # C-T3: the exit's `ld sp,nn` / `jp nn` operands are SMC (rewritten at every entry): masked
    smc = {a - S["ISR_ADDR"] for n in ("isr_rs", "isr_jp") for a in (S[n] + 1, S[n] + 2)}
    live, img = p.z.read_memory(S["ISR_ADDR"], S["ISR_LEN"]), SNA_RAM[io:io + S["ISR_LEN"]]
    h.expect("61 ISR copied to ISR_ADDR (SMC operands masked)",
             all(live[i] == img[i] for i in range(S["ISR_LEN"]) if i not in smc), True)
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
    # scroll, present_full -> bank 7). Stop in every ISR at its AY_PLAY call (bank 3
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
    for n in (5, 6, 7, 8, 9, 10, 11, 12, 13, 15, 16, 17):
        p.z.cmd("set-breakpoint %d" % n)
    print(f"[info] 61 transition: {ticks} ticks, ISR stops ay={n_ay} done={n_done},"
          f" interrupted $C000 banks {sorted(banks)}, screen bit sequence {scr}", flush=True)
    h.expect("61 transition reached room B", p.rb("CUR_ROOM"), 1)
    h.expect("61 no code at $C000+ with bank != 3, bar bank-1 UI / bank-7 cold code (boot..transition)", a7, [])
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


def hold_torches(p):
    """Leftovers 2026-11-03: deterministic menu-torch phase for the select goldens.
    With ANIM_FREEZE set, the next menu_torch swap (every MENU_TORCH_STEP frames) draws
    the held frame; forcing torch_t = 1 makes the very next menu frame do it, so the
    capture no longer depends on where the load / tape timing left the 8-frame counter."""
    p.wb("torch_t", 1)
    p.tick(3)


def tape_rest(h, p):
    """#50 after the tape reached GS_SELECT: screen, pool, banks, play."""
    p.tick(2)                                    # park on select_tick
    p.wb("ANIM_FREEZE", 1)
    hold_torches(p)                   # C3-6: the torches hold frame 0 (deterministic swap)
    golden(h, "game_select", p.frame())
    h.expect("50 tape GEN_OVERFLOW 0", p.rb("GEN_OVERFLOW"), 0)
    from game_lib import SNA_RAM
    p.z.cmd("set-memory-zone 0")
    try:
        ram = p.z.read_memory(0, 131072)
    finally:
        p.z.cmd("set-memory-zone -1")
    lo, hi = S["SRC_LEN_LO"], S["SRC_LEN_HI"]
    # C3-6 review: the bank-1 UI keeps its variables in one block (ui1_vars):
    # everything else of the bank-1 block must equal the .sna
    v0, v1 = S["ui1_vars"] - 0xC000, S["ui1_vars_end"] - 0xC000
    b1, s1 = bytearray(ram[16384:16384 + lo]), bytearray(SNA_RAM[16384:16384 + lo])
    b1[v0:v1] = s1[v0:v1] = bytes(v1 - v0)
    h.expect("50 bank 1 block (sources, data, UI code bar ui1_vars) == .sna", b1 == s1, True)
    # bank 3 block = source tail + bank-3 cold code (select, scrolls): BANK3_LEN >= hi
    b3 = S.get("BANK3_LEN", hi)
    h.expect("50 bank 3 sprite sources + cold code == .sna", ram[3 * 16384:3 * 16384 + b3] ==
             SNA_RAM[3 * 16384:3 * 16384 + b3], True)
    ayo = 3 * 16384 + S["AY_RESERVE"] - 0xC000
    # SND-2: the player + dispatcher state is one block (ay_vars): the ISR has
    # run since boot, so everything else of the AY slot must equal the .sna
    a0, a1 = S["ay_vars"] - S["AY_RESERVE"], S["ay_vars_end"] - S["AY_RESERVE"]
    ba, sa = bytearray(ram[ayo:ayo + S["AY_LEN"]]), bytearray(SNA_RAM[ayo:ayo + S["AY_LEN"]])
    ba[a0:a1] = sa[a0:a1] = bytes(a1 - a0)
    h.expect("50 bank 3 AY slot (A8 tape block, bar ay_vars) == .sna", ba == sa, True)
    o = 7 * 16384 + S["TSET_BASE"] - 0xC000      # B3B-8 / MEM-RECLAIM w2a: the tileset tape block
    h.expect("50 bank 7 tilesets (tape block) == .sna",
             ram[o:o + S["B7D_LEN"]] == SNA_RAM[o:o + S["B7D_LEN"]], True)
    o = 7 * 16384 + S["B7_CODE"] - 0xC000       # D3-S2: the bank-7 cold code (own tape block)
    h.expect("50 bank 7 cold code (D3-S2 tape block) == .sna",
             ram[o:o + S["B7_LEN"]] == SNA_RAM[o:o + S["B7_LEN"]], True)
    to = S["BANK_TEXT"] * 16384 + S["TEXT_ADDR"] - 0xC000   # D3-TX: the text block, bank 0
    tn = S["POOL_START"] - S["TEXT_ADDR"]                   # M0: + the bank-0 cold code + its reserve pad
    h.expect("50 bank 0 text block + b0 code (D3-TX / M0 tape block) == .sna", ram[to:to + tn] ==
             SNA_RAM[to:to + tn], True)
    # 3E-T1: the boot block (bank 6, below R6). Boot-only: the
    # hero start's pool overwrites it, but the boot pool ends in bank 4
    # (ALLOC_IDX < 2 here, ASSERTed in main.asm as POOL_BOOT_NEED), so at the
    # menu it is still byte-equal to the .sna — checked, not masked
    bo = S["BANK_BOOT6"] * 16384 + S["BOOT6_ADDR"] - 0xC000
    h.expect("50 boot block untouched by the boot pool (ALLOC_IDX < 2)", p.rb("ALLOC_IDX") < 2, True)
    h.expect("50 bank 6 boot block (3E-T1 tape block) == .sna", ram[bo:bo + S["BOOT6_LEN"]] ==
             SNA_RAM[bo:bo + S["BOOT6_LEN"]], True)
    # SRC6 spike: the bank-6 sprite sources ride on the boot block's tape block
    # (BOOT6_TAPE_LEN = boot block + SRC6_USED); read-only, compared whole
    so = S["BANK_SRC6"] * 16384 + S["SRC6_ADDR"] - 0xC000
    h.expect("50 boot tape block runs on through SRC6", S["BOOT6_TAPE_LEN"] ==
             S["BOOT6_LEN"] + S["SRC6_USED"] and S["BOOT6_ADDR"] + S["BOOT6_LEN"] == S["SRC6_ADDR"], True)
    h.expect("50 bank 6 SRC6 sources (boot tape block tail) == .sna", ram[so:so + S["SRC6_USED"]] ==
             SNA_RAM[so:so + S["SRC6_USED"]], True)
    # R6 (2026-10-21): the R6 region (bank 6 top, the last tape block, R6_USED B).
    # Its only runtime writes are drop_put's dp_* scratch (a kill with a drop):
    # none before the menu, so it is compared whole here
    ro = S["BANK_R6"] * 16384 + S["R6_ADDR"] - 0xC000
    h.expect("50 bank 6 R6 region (R6 tape block) == .sna", ram[ro:ro + S["R6_USED"]] ==
             SNA_RAM[ro:ro + S["R6_USED"]], True)
    # MEM-FT review: the FRT row image (frame_tab in row bytes 12..15) is .sna-only; on tape
    # instr_ovl in_ft (RECLAIM-D) rebuilds it from bank-0 ftz_zx0. At the menu every row == the .sna except bytes 0..11
    # of the two select idles' rows (gen_idles wrote their variant pointers; tails compared)
    fo, nf = 2 * 16384 + S["FRT"] - 0x8000, S["FID_COUNT"]
    ft, fs = bytearray(ram[fo:fo + 16 * nf]), bytearray(SNA_RAM[fo:fo + 16 * nf])
    for fid in (S["FID_knight_idle1"], S["FID_wizard_idle"]):
        ft[16 * fid:16 * fid + 12] = fs[16 * fid:16 * fid + 12] = bytes(12)
    h.expect("50 FRT[0..FID_COUNT*16) after tape boot == .sna (bar the idles' variant bytes)",
             [i for i in range(len(ft)) if ft[i] != fs[i]][:8], [])
    h.expect("50 tape: IM 2 installed by boot", " IM2 " in p.z.cmd("get-registers"), True)
    # CODE block starts in bank 5 low RAM (boot, generator) and runs into bank 2
    lo5 = S["lowram_code"] - 0x4000
    # TUT0-T1: instr_ovl in_stub copies the two blob stubs over check_paging (TUT_STUB_LEN B, tape
    # path only, dead after boot): compared against the assembled stub image `ovl_raw_stub`
    # (build/ovl/stub.bin), not blanked; check_paging sits in bank 5's low RAM
    l5, s5 = bytearray(ram[5 * 16384 + lo5:6 * 16384]), bytearray(SNA_RAM[5 * 16384 + lo5:6 * 16384])
    m0, n0 = S["check_paging"] - S["lowram_code"], S["TUT_STUB_LEN"]
    # C+TUT0: from build/ovl/stub.bin (main.asm SAVEBIN): the .sna's scratch copy is under the BOOT4 streams
    from game_lib import BUILD_DIR
    stub = open(os.path.join(BUILD_DIR, "ovl", "stub.bin"), "rb").read()[:n0]
    h.expect("50 tape: TUT stubs installed over check_paging == ovl_raw_stub", bytes(l5[m0:m0 + n0]), bytes(stub))
    l5[m0:m0 + n0] = s5[m0:m0 + n0] = bytes(n0)
    h.expect("50 bank 5 low-RAM cold code (bar the TUT stubs over check_paging) == .sna", l5 == s5, True)
    # the D0 blob (bank 4 BLOB_ORG..$FFFF) is unpacked once per power-on by instr_ovl in_tut
    bo4 = 4 * 16384 + S["BLOB_ORG"] - 0xC000
    h.expect("50 bank 4 D0 blob (BLOB_ORG..$FFFF, unpacked at boot) == .sna",
             ram[bo4:5 * 16384] == SNA_RAM[bo4:5 * 16384], True)
    p.wb("INPUT_REPEAT", 0)
    p.wb("ANIM_FREEZE", 1)
    p.wb("INPUT_SRC", 1)
    p.wb("proto_start", 3 if p.proto_start else 0)   # B3B-12: the tape loaded the default 0 (3F-T3: bit 1 = + Slime)
    p.arm_proto()                                    # D3-11: the PROTO fixture breakpoint (proto_hook)
    p.tut_off()                                      # TUT0-T6b: '1' would open the tutorial choice screen
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
            p.turn("WAIT")

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
    go_room(ROOM_C, "J")             # B {24,2} -> C (col 24, H1: mid-ladder at the top of the shaft)
    climb("J", 0)                    # H1: 2 ladder turns down to storey 0
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
        act("H" if foe_left() else "WAIT")
    if check14:
        print(f"[info] 14: C skeleton y {sk_y0} -> min {min_y}")
        h.expect("14 C skeleton climbs: y decreases by >= 9 within 30 turns",
                 sk_y0 - min_y >= STOREY_ROWS, True)
    go_x(24)
    climb("J", 1)                    # {24,1} down to storey 1
    go_room(ROOM_D, "H")             # C -> D (s1)
    go_x(22)
    climb("K", 0)                    # {22,1} up to storey 0 (potion 3 at col 17)
    go_x(3)                          # B3B-13: the old chest spot (the PROTO win is gone)
    p.until(lambda: p.idle(), 40)
    e0 = p.ent(0)
    res = dict(gs=p.rb("GAME_STATE"), end=(p.rb("CUR_ROOM"), e0["X"], storey_of(e0["Y"], body(p, K_KNIGHT)[1])),
               turns=p.rw("TURN_COUNTER"),
               overrun=p.rw("OVERRUN_COUNT"), miss=p.rb("BLIT_MISS"), hp=p.ent(0)["HP"],
               dmgov=p.rb("DMG_OVERFLOW"), clip=p.rb("CLIP_TRAP"), gentrap=p.rb("GEN_TRAP"), seqtrap=p.rb("SEQ_TRAP"))
    res["state"] = (p.rw("RNG_STATE"), p.rw("TURN_COUNTER"), p.rb("POTIONS_TAKEN"),
                    tuple((e["ROOM"], e["X"], e["Y"], e["HP"], e["FLAGS"] & 0x7F)
                          for e in (p.ent(s) for s in range(9))))
    # the end screen of a win (GS_WIN, as level_descend sets it from D8; the
    # real D8 descend is tests/world.py W16): ENTER -> hero select
    p.wb("GAME_STATE", GS_WIN)
    p.tick(2)
    res["select"] = p.end_to_menu()   # C3-6b: a digit / ENTER (after a release) leaves an end card
    p.settle()
    p.wb("ANIM_FREEZE", 1)
    hold_torches(p)                   # C3-6: the torches hold frame 0
    golden(h, "game_select", p.frame())             # after a WIN -> ENTER
    return res


if __name__ == "__main__":
    sys.exit(main())
