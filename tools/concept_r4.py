#!/usr/bin/env python3
"""concept_r4.py — round-4 CONCEPT content for tools/concept_screen.py (imported by its main()).

Final-layout mock screens (2 x 9-row storeys + 6-row panel, concept-screen.md rev 2b,
game.md rev 2), the Bloodstone-inspired structure tileset, exposed-brick patches, lectern,
panel ornament, the full 24x24 bar icon sets, Vampire / Ogre Warlord / Death Knight, and the
CURRENT section of concept_sheet.png. Everything is composed through the same attribute model
and validated by concept_screen.validate().
"""

from __future__ import annotations

import os

import numpy as np

import concept_screen as C

GRID = C.GRID
OUT = C.OUT

# Scheme per mock (game.md §1.2)
SCHEME = {"D1": ("BLUE KEEP", 0x0F, 0x01), "D4": ("ORC WARRENS", 0x28, 0x05),
          "D7": ("IRON FORTRESS", 0x4F, 0x41), "D8": ("SANCTUM", 0x1F, 0x03)}
R4_MOTION = {"vampire_walk1", "vampire_walk2", "ogre_walk1", "ogre_walk2",
             "dknight_walk1", "dknight_walk2"}
BODY_W = {"vampire": 24, "ogre": 32, "dknight": 24, "knight": 24, "wizard": 24}
INK = {"vampire": 0x42, "ogre": 0x43, "dknight": 0x47}

# Round 5: bar icons are 24x16 (3x2 cells), user decision
MAGE_BAR = [("staff2416", 0x46), ("spark2416", 0x43), ("firebolt2416", 0x42),
            ("frost2416", 0x45), ("drain2416", 0x43), ("lightning2416", 0x47),
            ("apple2416", 0x42), ("potion2416", 0x42), ("scroll2416", 0x47), ("bag2416", 0x06)]
WARRIOR_BAR = [("sword2416", 0x47), ("power2416", 0x42), ("whirl2416", 0x47),
               ("daggers2416", 0x47), ("bow2416", 0x06), ("apple2416", 0x42),
               ("potion2416", 0x42), ("scroll2416", 0x47), ("bag2416", 0x06), (None, 0x01)]
GEAR = {"mage": [("staff", 0x46), ("robe", 0x43), ("hood", 0x43), ("ring", 0x46)],
        "warrior": [("sword", 0x47), ("mail", 0x47), ("helm", 0x47), ("ring", 0x46)]}


def load(art) -> None:
    art.w4 = C.parse_blocks(os.path.join(GRID, "walls_r4.tiles"))
    art.d4 = C.parse_blocks(os.path.join(GRID, "decor_r4.grid"))
    art.orn = C.parse_blocks(os.path.join(GRID, "panel_r4.tiles"))
    art.ic24.update(C.parse_blocks(os.path.join(GRID, "icons24_r4.grid")))
    art.ic2416 = C.parse_blocks(os.path.join(GRID, "icons24x16.grid"))
    src = C.parse_blocks(os.path.join(GRID, "r4_frames.grid"))
    art.r4_names = list(src)
    art.r2.update(C.derive_spell_grids(src, "r4_frames.grid (from tools/concept_r4_frames.py)",
                                       "R4 FRAME"))
    art.ax.update({n: b["ax"] for n, b in src.items()})
    for n in ("knight_dead", "knight_slash", "wizard_cast2", "skeleton_walk2", "goblin_walk1"):
        if n not in art.r2:
            fg, so = C.load_sprite(n)
            art.r2[n] = (fg, so, 0x45)
    art.ax.setdefault("knight_dead", 8)
    art.ax.setdefault("knight_slash", 4)


# ---------------------------------------------------------------------------
# Screen composition (9 + 9 + 6)
# ---------------------------------------------------------------------------

def empty_slot24(h: int = 24) -> np.ndarray:
    b = np.zeros((h, 24), bool)
    b[0, ::2] = b[h - 1, ::2] = b[::2, 0] = b[::2, 23] = True
    return b


def put_sprite(s, art, name, col, floor_row, attr, mirror=False, dx=0, dy=0, label=None):
    """Bottom-anchored: the frame's bottom row sits on the standing row above floor_row.
    `col` = the BODY's left column; the anchor ax shifts wide frames left (draw_x = body_x - ax).
    Mirrored frames put the overhang on the other side: draw_x = body_x - (W - ax - body_w)."""
    fg, so, _ = art.r2[name]
    h, w = fg.shape
    ax = art.ax.get(name, 0)
    bw = BODY_W.get(name.split("_")[0], 24)
    if mirror:
        fg, so = fg[:, ::-1], so[:, ::-1]
        x = col * 8 - (w - ax - bw)
    else:
        x = col * 8 - ax
    s.sprite(label or name, x + dx, floor_row * 8 - h + dy, fg, so, attr)


# Mid-room masonry fragments per mock (cols, rows, w, h), placed clear of sprites
CHUNKS = {"D1": [(5, 1, 3, 2), (15, 3, 2, 1), (23, 2, 2, 2), (9, 11, 2, 1), (27, 10, 2, 2),
                 (17, 9, 2, 1)],
          "D4": [(11, 1, 3, 2), (15, 4, 2, 1), (23, 1, 2, 2), (19, 10, 3, 2), (27, 12, 2, 1)],
          "D7": [(17, 1, 3, 2), (22, 3, 2, 2), (17, 5, 2, 1), (22, 10, 2, 2), (27, 11, 2, 1)],
          "D8": [(24, 1, 2, 2), (7, 0, 2, 1), (14, 6, 2, 1), (12, 10, 3, 1), (22, 12, 2, 2)]}


def room(art, depth: str, ornament: bool = True):
    name, fa, wa = SCHEME[depth]
    s, T, W = C.Screen(), art.tiles, art.w4
    g = lambda c, r, bm, a: s.glyph(c, r, bm, a)
    # floors: storey 0 (row 8) with a 3-col pit + ladder hole, storey 1 (row 17)
    pit = {"D1": (17, 19), "D4": (12, 14), "D7": None, "D8": None}[depth]
    for c in range(32):
        if pit and pit[0] <= c <= pit[1]:
            continue                                         # pit: AIR $00 (hole)
        if 24 <= c <= 26:
            g(c, 8, T[("ladder_l", "ladder_m", "ladder_r")[c - 24]], C.A_LADDER)
            continue
        hi = (pit and c in (pit[0] - 1, pit[1] + 1)) or c in (23, 27)
        if pit and c == pit[0] - 1:
            bm = T["platform_end_r"]
        elif pit and c == pit[1] + 1:
            bm = T["platform_end_l"]
        else:
            bm = W["platform_hi"]["bm"] if hi else T["platform"]
        g(c, 8, bm, fa)
    for r in range(9, 17):
        for c in range(24, 27):
            g(c, r, T[("ladder_l", "ladder_m", "ladder_r")[c - 24]], C.A_LADDER)
    # storey-1 floor = the panel's top frame
    if ornament:
        O = art.orn
        for c in range(32):
            if c == 0:
                n = "orn_cap_l"
            elif c == 31:
                n = "orn_cap_r"
            elif 14 <= c <= 17:
                n = ("orn_wing_l", "orn_skull_l", "orn_skull_r", "orn_wing_r")[c - 14]
            else:
                n = "orn_link" if c % 2 else "orn_bar"
            g(c, 17, O[n]["bm"], fa)
    else:
        for c in range(32):
            g(c, 17, T["platform"], fa)
    # structure: crumbling fragments
    def frag(c0, c1, r0, r1, open_r=False, open_l=False, open_t=False, open_b=False):
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                n = "wall_worn" if (r + c) % 3 == 0 else None
                if open_r and c == c1:
                    n = "wall_brk_r"
                if open_l and c == c0:
                    n = "wall_brk_l"
                if open_t and r == r0:
                    n = "wall_brk_top"
                if open_b and r == r1:
                    n = "wall_brk_bot"
                g(c, r, W[n]["bm"] if n else T["wall"], wa)
    def deco(n, c, r):
        b = art.d4.get(n) or art.big.get(n)
        C.place_big(s, c, r, b)
    def glyph(n, c, r, a=None):
        b = W[n]
        g(c, r, b["bm"], b["attr"] if a is None else a)
    def roots(c, r, frame=1):
        glyph("root_top", c, r)
        glyph(f"root_end{frame}", c, r + 1)
    def pillar(c, r0, r1):
        for r in range(r0, r1 + 1):
            glyph("pillar_l", c, r, wa)
            glyph("pillar_r", c + 1, r, wa)
    def door():
        frag(30, 31, 9, 9, open_b=True)
        g(30, 10, art.door["door_arch_l"]["bm"], C.A_DOOR)
        g(31, 10, art.door["door_arch_r"]["bm"], C.A_DOOR)
        for r in range(11, 17):
            g(30, r, art.door["door_l"]["bm"], C.A_DOOR)
            g(31, r, art.door["door_r_ring" if r == 13 else "door_r"]["bm"], C.A_DOOR)
    torch = lambda c, r: C.place_big(s, c, r, art.big["torch_tall_f1"])
    def chunk(c0, r0, w, h):
        """Broken masonry floating in the room (Bloodstone-style): ragged on every side
        that faces black, built only from the 12 common structure ids."""
        for r in range(r0, r0 + h):
            for c in range(c0, c0 + w):
                if h == 1:
                    n = "wall_brk_top" if (c - c0) % 2 == 0 else "wall_brk_bot"
                elif r == r0:
                    n = "wall_brk_top"
                elif r == r0 + h - 1:
                    n = "wall_brk_bot"
                elif c == c0:
                    n = "wall_brk_l"
                elif c == c0 + w - 1:
                    n = "wall_brk_r"
                else:
                    n = "wall_worn"
                g(c, r, W[n]["bm"], wa)
    for c0, r0, w, h in CHUNKS[depth]:
        chunk(c0, r0, w, h)

    if depth == "D1":
        frag(0, 2, 0, 7, open_r=True)
        frag(0, 0, 9, 16, open_r=True)
        door()
        glyph("rubble", 3, 7)
        glyph("rubble", 18, 16)
        torch(28, 1)
        deco("patch_a", 20, 1)
        deco("patch_b", 13, 10)
        roots(9, 0)
        roots(15, 9, 2)
        roots(5, 9)
    elif depth == "D4":
        frag(0, 1, 0, 3, open_r=True, open_b=True)
        frag(0, 0, 9, 16, open_r=True)
        door()
        pillar(20, 0, 7)
        deco("patch_a", 5, 1)
        roots(9, 0)
        roots(17, 9, 2)
        C.place_big(s, 16, 13, art.big["brazier_big_f1"])
        glyph("rubble", 2, 16)
        glyph("rubble", 29, 7)
    elif depth == "D7":
        frag(30, 31, 0, 7, open_l=True)
        frag(0, 0, 9, 16, open_r=True)
        door()
        C.place_big(s, 13, 1, art.big["window_arch"])
        pillar(3, 0, 7)
        pillar(20, 9, 16)
        C.place_big(s, 9, 9, art.big["banner_tall"])
        deco("patch_b", 2, 9)
        torch(27, 1)
        glyph("rubble", 23, 7)
    elif depth == "D8":
        frag(0, 1, 0, 7, open_r=True)
        frag(30, 31, 0, 7, open_l=True)
        frag(0, 0, 9, 16, open_r=True)
        frag(31, 31, 9, 16, open_l=True)
        pillar(9, 9, 16)
        pillar(18, 9, 16)
        deco("lectern", 14, 15)
        roots(4, 0)
        roots(27, 0, 2)
        torch(12, 1)
        deco("patch_a", 21, 10)
        glyph("rubble", 11, 16)
        glyph("rubble", 21, 16)
    return s


def panel(s, art, hero: str, depth: str, sel_idx: int, info: str, msgs,
          hp=(18, 22), mp=(5, 12), food=0.6, stage="HUNGRY", ammo="", greyed=()):
    """Round-5 panel (rows 18-23):
      18-19  10 bar icons 24x16 at cols 3i..3i+2; cols 30-31: depth (row 18), key (row 19)
      20     full info line, 32 chars: name + cost + range/bounce/effect (no truncation)
      21     HP / MP / FOOD bars, 32 px each, + hunger stage word + ammo
      22-23  2-row message log, 24 chars (cols 0-23)
      22-23  worn gear, 4 x 16x16 at cols 24-31 (weapon, armour, helmet, charm)"""
    F = art.font
    bar = MAGE_BAR if hero == "mage" else WARRIOR_BAR
    for i, (ic, a) in enumerate(bar):
        bm = empty_slot24(16) if ic is None else art.ic2416[ic]["bm"]
        if ic is None:
            a = 0x01
        if i in greyed:
            a = C.A_GREY_SEL if i == sel_idx else C.A_GREY
        elif i == sel_idx:
            a = C.sel(a)
        s.glyph(3 * i, 18, bm, a)
    s.text(30, 18, depth, 0x47, F)
    s.glyph(30, 19, KEY8, 0x46)
    s.text(31, 19, " ", 0x00, F)
    assert len(info) <= 32, info
    s.text(0, 20, f"{info:<32s}", 0x47, F)
    s.glyph(0, 21, art.ic8["heart"]["bm"], 0x42)
    C.put_bar(s, 1, 21, 4, hp[0] / hp[1], 0x42)
    s.text(5, 21, f"{hp[0]:2d}", 0x42, F)
    s.glyph(7, 21, art.ic8["drop"]["bm"], 0x45)
    C.put_bar(s, 8, 21, 4, mp[0] / mp[1], 0x45)
    s.text(12, 21, f"{mp[0]:2d}", 0x45, F)
    s.glyph(14, 21, art.ic8["drumstick"]["bm"], 0x44)
    stage_attr = {"FED": 0x44, "HUNGRY": 0x46, "WEAK": 0x42}.get(stage, 0x46)
    C.put_bar(s, 15, 21, 4, food, stage_attr)
    s.text(19, 21, f"{stage:<7.6s}", stage_attr, F)          # cols 19-24 + gap
    s.text(26, 21, f"{ammo:>6.6s}", 0x47, F)                  # e.g. "D6 A12"
    for k, (n, a) in enumerate(GEAR[hero]):
        b = art.ic16.get(n) or art.ic16b[n]
        s.glyph(24 + 2 * k, 22, b["bm"], a)
    for r, m in zip((22, 23), msgs):
        assert len(m) <= 24, m
        s.text(0, r, f"{m:<24s}", 0x07 if r == 22 else 0x47, F)


KEY8 = np.array([[c == "#" for c in r] for r in """........
.##.....
#..#####
#..#.#.#
.##.....
........
........
........""".split()], bool)


def screen_d1(art, ornament=True):
    s = room(art, "D1", ornament)
    put_sprite(s, art, "wizard_cast2", 4, 17, C.A_MAGE)
    fb, fbs, fba = art.spells["firebolt_fly1"]
    s.sprite("firebolt", 11 * 8, 13 * 8, fb, fbs, fba)
    put_sprite(s, art, "goblin_walk1", 19, 17, C.A_GOB, mirror=True)
    put_sprite(s, art, "skeleton_walk2", 10, 8, C.A_SKEL)
    panel(s, art, "mage", "D1", 2, "FIREBOLT 3MP RANGE 12 BURST",
          ["THE GOBLIN MISSES YOU.", "THE FIREBOLT FLIES."], greyed={5})
    return s


def screen_d4(art):
    s = room(art, "D4")
    put_sprite(s, art, "knight_power", 3, 17, C.A_MAGE)
    put_sprite(s, art, "ogre_raise", 10, 17, INK["ogre"], mirror=True)
    put_sprite(s, art, "orc_walk2", 27, 8, 0x44, mirror=True)
    put_sprite(s, art, "spider_walk1", 4, 8, 0x42)
    panel(s, art, "warrior", "D4", 1, "POWER STRIKE 3MP REACH DMG X2",
          ["THE OGRE WARLORD ROARS!", "YOU STRIKE THE OGRE (12)"],
          hp=(25, 36), mp=(9, 15), food=0.8, stage="FED", ammo="D3 A8")
    return s


def screen_d7(art):
    s = room(art, "D7")
    put_sprite(s, art, "knight_throw", 4, 17, C.A_MAGE)
    dg, dgs, dga = art.proj["dagger_spin2"]
    s.sprite("dagger", 10 * 8, 12 * 8, dg, dgs, dga)
    put_sprite(s, art, "dknight_block", 14, 17, INK["dknight"], mirror=True)
    put_sprite(s, art, "skelarch_draw", 6, 8, 0x47)
    ar, ars, ara = art.proj["arrow_fly1"]
    s.sprite("arrow", 11 * 8, 4 * 8, ar, ars, ara)
    panel(s, art, "warrior", "D7", 3, "DAGGERS X6 RANGE 6 RECOVERABLE",
          ["DEATH KNIGHT PARRIES!", "YOU THROW A DAGGER."],
          hp=(30, 54), mp=(4, 16), food=0.4, greyed={1}, ammo="D6 A12")
    return s


def screen_d8(art):
    s = room(art, "D8")
    put_sprite(s, art, "wizard_cast2", 3, 8, C.A_MAGE)
    lf, lfs, lfa = art.spells["lightning_fly1"]
    s.sprite("lightning", 10 * 8, 4 * 8, lf, lfs, lfa)
    put_sprite(s, art, "archmage_cast", 19, 8, 0x43, mirror=True)
    put_sprite(s, art, "necro_walk1", 27, 17, 0x43, mirror=True)
    put_sprite(s, art, "skeleton_walk2", 5, 17, C.A_SKEL)
    panel(s, art, "mage", "D8", 5, "LIGHTNING 5MP RANGE 28 BOUNCE 2",
          ["THE BOOK WHISPERS: -1HP", "LIGHTNING HITS ARCHMAGE!"],
          hp=(21, 48), mp=(7, 20), food=0.3, stage="WEAK")
    return s


def write_screens(art) -> tuple[list[str], list[str]]:
    errs, rep = [], []
    shots = [("screen_9x9", lambda: screen_d1(art)),
             ("screen_d4_warrens", lambda: screen_d4(art)),
             ("screen_d7_fortress", lambda: screen_d7(art)),
             ("screen_d8_sanctum", lambda: screen_d8(art))]
    import concept_fonts
    depth_of = {"screen_9x9": "D1", "screen_d4_warrens": "D4", "screen_d7_fortress": "D7",
                "screen_d8_sanctum": "D8"}
    for fn, mk in shots:
        s = mk()
        concept_fonts.apply_panel6(s, art, depth_of[fn])       # info line + log in 6x8
        scr = s.to_scr()
        open(os.path.join(OUT, fn + ".scr"), "wb").write(scr)
        C.save_png(s.rgb_image(), os.path.join(OUT, fn + ".png"))
        e, r = C.validate(fn, s, scr, [8, 17], range(18, 24))
        errs += [f"{fn}: {x}" for x in e]
        rep += r
    return errs, rep


# ---------------------------------------------------------------------------
# Sheet: CURRENT section
# ---------------------------------------------------------------------------

def fragment_demo(art, wa=0x01, fa=0x0F) -> np.ndarray:
    """10x6 structure demo: a ragged fragment, a pillar, roots, a patch, rubble, a ledge."""
    W, T = art.w4, art.tiles
    bm = np.zeros((48, 80), bool)
    at = np.zeros((6, 10), np.uint8)
    def put(c, r, g, a):
        bm[r * 8:r * 8 + 8, c * 8:c * 8 + 8] = g
        at[r, c] = a
    plan = {(0, 0): "wall_brk_top", (1, 0): "wall_brk_top", (2, 0): "wall_brk_top",
            (0, 1): "WALL", (1, 1): "wall_worn", (2, 1): "wall_brk_r",
            (0, 2): "wall_worn", (1, 2): "WALL", (2, 2): "wall_brk_r",
            (0, 3): "wall_brk_bot", (1, 3): "wall_brk_bot",
            (0, 4): "wall_brk_l", (1, 4): "wall_brk_r"}
    for (c, r), n in plan.items():
        put(c, r, T["wall"] if n == "WALL" else W[n]["bm"], wa)
    for r in range(5):
        put(4, r, W["pillar_l"]["bm"], wa)
        put(5, r, W["pillar_r"]["bm"], wa)
    put(7, 0, W["root_top"]["bm"], 0x05)
    put(7, 1, W["root_end1"]["bm"], 0x05)
    put(3, 0, W["root_top"]["bm"], 0x05)
    put(3, 1, W["root_end2"]["bm"], 0x05)
    p = art.d4["patch_a"]["bm"]
    bm[16:32, 56:72] = p
    at[2:4, 7:9] = 0x07
    put(9, 4, W["rubble"]["bm"], 0x07)
    put(6, 4, W["rubble"]["bm"], 0x07)
    for c in range(10):
        put(c, 5, W["platform_hi"]["bm"] if c in (3, 6) else T["platform"], fa)
    return C.render_rgb(bm, at)


def panel_strip(art, ornament: bool) -> np.ndarray:
    s = room(art, "D1", ornament)
    panel(s, art, "mage", "D1", 2, "FIREBOLT 3MP RANGE 12 BURST",
          ["THE GOBLIN MISSES YOU.", "THE FIREBOLT FLIES."], greyed={5})
    import concept_fonts
    concept_fonts.apply_panel6(s, art, "D1")
    img = s.rgb_image()
    return img[16 * 8:24 * 8]


def sheet_current(sh, art) -> None:
    sh.heading("CURRENT (R5) -- LAYOUT 9+9+6: SEE screen_9x9 / d4 / d7 / d8 PNG")
    sh.heading("R4 STRUCTURE TILESET (12 COMMON IDS) + FRAGMENT DEMO")
    sh.add([C.glyph_rgb(b["bm"], b["attr"]) for b in art.w4.values()],
           "WORN BRK-T/B/L/R PIL-L/R LEDGE RUBBLE ROOTS")
    for name, fa, wa in (SCHEME["D1"], SCHEME["D4"], SCHEME["D7"], SCHEME["D8"]):
        sh.add([fragment_demo(art, wa, fa)], name)
    sh.heading("R5 DECOR: PLASTER PATCHES (BRICK THROUGH A HOLE) / LECTERN / ROOTS")
    for n in ("patch_a", "patch_b", "lectern"):
        b = art.d4[n]
        sh.add([C.render_rgb(b["bm"], b["cells"])], f"{n.upper()} {b['w'] // 8}X{b['h'] // 8}")
    W = art.w4
    sh.add([C.glyph_rgb(np.vstack([W["root_top"]["bm"], W[f"root_end{k}"]["bm"]]), 0x05)
            for k in (1, 2)], "ROOTS 1X2 (SW1)")
    sh.heading("R5 PANEL: ICONS 18-19, INFO 20, BARS 21, LOG+GEAR 22-23 (ORNAMENT KEPT)")
    sh.add([panel_strip(art, True)], "WITH ORNAMENT (DECIDED; 8 GLYPHS, 72 B)")
    sh.heading("R5 BAR ICONS 24x16 (3x2 CELLS): MAGE / WARRIOR; GEAR 16x16")
    sh.add([C.glyph_rgb(art.ic2416[n]["bm"], a) for n, a in MAGE_BAR], "MAGE")
    sh.add([C.glyph_rgb(art.ic2416[n]["bm"] if n else empty_slot24(16), a)
            for n, a in WARRIOR_BAR], "WARRIOR")
    sh.add([C.glyph_rgb(art.ic2416["power2416"]["bm"], a) for a in (0x42, C.sel(0x42), C.A_GREY)],
           "POWER STRIKE N/SEL/GREY")
    for hero in ("mage", "warrior"):
        sh.add([C.glyph_rgb((art.ic16.get(n) or art.ic16b[n])["bm"], a) for n, a in GEAR[hero]],
               f"GEAR {hero.upper()}")
    sh.heading("R5 BOSSES (DEATH KNIGHT REDRAWN) + VAMPIRE (CAPE POSE)")
    sh.add([C.sprite_rgb(art.r2[n][0], art.r2[n][1], INK["ogre"]) for n in
            ("ogre_walk1", "ogre_walk2", "ogre_raise", "ogre_slam", "ogre_hurt", "ogre_dead")],
           "OGRE WARLORD")
    sh.add([C.sprite_rgb(art.r2[n][0], art.r2[n][1], INK["dknight"]) for n in
            ("dknight_walk1", "dknight_walk2", "dknight_windup", "dknight_cleave",
             "dknight_block", "knight_dead")], "DEATH KNIGHT (DEAD = KNIGHT_DEAD, RECOLOURED)")
    sh.add([C.sprite_rgb(art.r2[n][0], art.r2[n][1], INK["vampire"]) for n in
            ("vampire_walk1", "vampire_walk2", "vampire_bite", "vampire_hurt", "vampire_dead")],
           "VAMPIRE (BAT FORM = EXISTING BAT)")
    sh.heading("FONTS (R6 THIN/SCRIPT): 6x8 768 B / MENU 8x16 832 B / TITLE A-Z 864 B")
    f6, f16, ft = art.f6, art.f16, art.ft
    def strip(glyphs, codes, ink=(255, 255, 255)):
        ims = []
        for c in codes:
            g = glyphs[c]
            im = np.zeros(g.shape + (3,), np.uint8)
            im[g] = ink
            ims.append(im)
        return np.hstack(ims)
    for i in range(32, 128, 32):
        sh.add([strip(f6, range(i, i + 32))], f"6X8 {i}-{i + 31}")
    import font_tool
    sh.add([strip(f16, [ord(c) for c in font_tool.MENU_SET[:26]])], "MENU 8X16")
    sh.add([strip(f16, [ord(c) for c in font_tool.MENU_SET[26:]])], "MENU 8X16 (2)")
    sh.add([strip(ft, [ord(c) for c in "ABCDEFGHIJKLM"])], "TITLE 16X16 A-M")
    sh.add([strip(ft, [ord(c) for c in "NOPQRSTUVWXYZ"])], "TITLE 16X16 N-Z")
    sh.heading("R4 GOLD GLOW (SYNC, DECIDED)")
    fg, so, _ = art.r2["orc_walk1"]
    cells = [(c, r) for r in range(6) for c in range(3)]
    sh.add([C.sprite_with_cell_attrs(fg, so, C.glow_attrs(t, cells, "sync"), 6, 3)
            for t in (0, 2, 4, 6)], "SYNC 06>46>47>46")
    sh.heading("===== ARCHIVE: ROUNDS 1-3 (SUPERSEDED ITEMS MARKED) =====")


# ---------------------------------------------------------------------------
# GIF band, bytes, validation
# ---------------------------------------------------------------------------

def gif_layer(art, s, t: int, top: int):
    """Rows top..top+15: boss cycles, vampire, roots sway, patch on the r4 fragment wall."""
    T, W, F = art.tiles, art.w4, art.font
    fl = top + 7
    for c in range(32):
        s.glyph(c, fl, T["platform"], C.A_FLOOR)
    k = t % 32
    f = ["ogre_walk1", "ogre_walk2"][(k // 4) % 2] if k < 12 else \
        "ogre_raise" if k < 18 else "ogre_slam" if k < 24 else "ogre_hurt" if k < 27 else "ogre_walk1"
    put_sprite(s, art, f, 1, fl, INK["ogre"])
    k = t % 32
    f = ["dknight_walk1", "dknight_walk2"][(k // 4) % 2] if k < 10 else \
        "dknight_windup" if k < 14 else "dknight_cleave" if k < 19 else \
        "dknight_block" if k < 25 else "dknight_walk1"
    put_sprite(s, art, f, 12, fl, INK["dknight"])
    k = t % 24
    f = ["vampire_walk1", "vampire_walk2"][(k // 4) % 2] if k < 12 else \
        "vampire_bite" if k < 18 else "vampire_hurt" if k < 21 else "vampire_walk1"
    put_sprite(s, art, f, 22, fl, INK["vampire"])
    # band 2: structure fragment with swaying roots and a patch
    fl2 = top + 15
    for c in range(32):
        s.glyph(c, fl2, W["platform_hi"]["bm"] if c % 7 == 3 else T["platform"], C.A_FLOOR)
    for r in range(top + 8, fl2):
        for c in (0, 1):
            n = "wall_brk_r" if c == 1 else ("wall_worn" if r % 3 == 0 else None)
            s.glyph(c, r, W[n]["bm"] if n else T["wall"], C.A_WALL)
    for c in (5, 12, 19):
        s.glyph(c, top + 8, W["root_top"]["bm"], 0x05)
        s.glyph(c, top + 9, W["root_end1" if (t // 6 + c) % 2 else "root_end2"]["bm"], 0x05)
    C.place_big(s, 8, top + 10, art.d4["patch_b"])
    for c in range(22, 24):
        for r in range(top + 8, fl2):
            s.glyph(c, r, W["pillar_l" if c == 22 else "pillar_r"]["bm"], C.A_WALL)
    s.glyph(26, fl2 - 1, W["rubble"]["bm"], 0x07)
    C.place_big(s, 28, fl2 - 2, art.d4["lectern"])
    if (t // 4) % 6 == 0:                                    # lectern hit flash
        s.set_attr(28, fl2 - 2, 0x47, 2, 1)
    s.text(13, top + 13, "ROOTS SWAY 1 CELL", 0x07, F)


def r4_bytes(art) -> list[str]:
    L = [f"round 4 — tiles: structure {len(art.w4)} common ids ({9 * len(art.w4)} B); "
         f"patch_a 4 ids, patch_b 6 ids, lectern 4 ids (per-level, 9 B each); "
         f"panel ornament {len(art.orn)} glyphs = {8 * len(art.orn)} B + {len(art.orn)} attr "
         f"(drawn once); 24x24 icons +{len(art.ic24) - 4} x 73 B",
         "round 4 — sprite frames (src = W/8*H*2 raw; pool = POOLACC both facings):",
         f"  {'frame':20s} {'WxH':6s} ax {'src':>5s} {'pool':>5s}"]
    tot = {}
    for n in art.r4_names:
        fg = art.r2[n][0]
        h, w = fg.shape
        ax = art.ax.get(n, 0)
        kind = n.split("_")[0]
        mo = n in R4_MOTION
        sb, pb = h * w // 4, C.pool_bytes(w, h, ax, BODY_W[kind], mo)
        L.append(f"  {n:20s} {w}x{h:<3d} {ax:2d} {sb:5d} {pb:5d}  {kind}{' MOTION' if mo else ''}")
        g = tot.setdefault(kind, [0, 0, 0])
        g[0] += 1
        g[1] += sb
        g[2] += pb
        rows = C.gfx_convert.pack_sprite(fg, art.r2[n][1], "native")
        dfg, dso = C.gfx_convert.unpack_sprite_mask(rows, w, "native")
        if not (np.array_equal(dfg, fg) and np.array_equal(dso, art.r2[n][1])):
            raise SystemExit(f"{n}: pack round-trip mismatch")
    for k, (i, sb, pb) in tot.items():
        L.append(f"  == {k}: {i} ids, source {sb} B, pool {pb} B")
    return L


def r4_validate(art) -> list[str]:
    errs = []
    for n, b in list(art.w4.items()) + list(art.orn.items()):
        paper = (b["attr"] >> 3) & 7
        if n in ("platform_hi",) or n.startswith("orn_"):
            continue                                         # floor-row glyphs: floor attr
        if paper:
            errs.append(f"{n}: air-band tile with non-black paper")
    for n, b in art.d4.items():
        if ((b["cells"] >> 3) & 7).any():
            errs.append(f"{n}: decor cell with non-black paper")
    for n in art.r4_names:
        w = art.r2[n][0].shape[1]
        if w > 40 or w % 8 or art.ax.get(n, 0) % 4:
            errs.append(f"{n}: width/anchor rule")
    return errs
