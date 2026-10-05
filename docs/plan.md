# Delivery plan — WazHack/ZX

> Manager-owned control document: **current state only**. Every phase has a
> verifiable exit gate — state is proven by build/run/test, not by opinion.
> Past decisions and evidence (P0–P3, SPIKE-1..4, PROTO): `docs/history.md`.

Status legend: `TODO` · `IN-PROGRESS` · `BLOCKED(reason)` · `DONE`

## Baseline (2026-10-01)

The PROTO fighting prototype is the **baseline game** (`main` @ `75eeabd`,
squash of `feat/project-scaffold` @ `238af0c`; tape sha256 `6fa4629d…`).

- Side-view, room-based (Cauldron-style transitions), 3 storeys + HUD, ladders.
- Heroes Knight/Wizard/Rogue (24×48); monsters Skeleton, Goblin, Ghost, Rat,
  Bat, Slime; melee + Wizard zap, HP/death, potions, hero select.
- Art source of truth: claude.ai Design canvas "WazHack Spectrum Sprites"
  (https://claude.ai/artifact/U71G9dWUWzZBVxmJUrevD3), imported via
  `tools/svg_sprites.py` → `tools/gfx_convert.py`.
- Spec: `docs/design/prototype.md`. Layout: `docs/memory-map.md`.
- Gate at baseline: 0 warnings; 179/179 ZRCP scenarios incl. tape E2E.

## Active

### C1 — Cleanup & pipeline · `DONE` (branch `feat/cleanup`, 2026-10-01)
- Remove spikes, legacy top-down build, legacy tests/goldens, AI-raster tools
  and concept art (archived outside the repo). ✅
- Agent roster + model split + token rules (`CLAUDE.md`). ✅
- PROTO → main rename (`src/main.asm`, `build/wazhack.*`, `tests/game*.py`) —
  `z80-junior` trial (Sonnet, ~47k tokens, no escalation). ✅
- Design docs: still-binding parts of the old docs → `docs/design/foundations.md`
  (F1–F9); old docs → `docs/archive/design/`; `heroes.md` dropped. ✅
- **Gate passed (manager):** build 0 warnings; `wazhack.sna` byte-identical to
  baseline; `tests/game.py` 179/179, goldens unchanged; no references to
  removed files. Tape sha256 `4db91773…` (only tape block names changed).
- Follow-ups from the designer: make the 16-entity-slot cap explicit in
  prototype.md; confirm whether nat-20/nat-1 (F1, optional) is implemented.

## Known bugs / open issues

| # | Issue | Owner | Notes |
|---|-------|-------|-------|
| B1 | Heavy fight = 154,852 T = **109%** of the 2-frame tick (ZEsarUX, contention emulated) | staff | **E0 RENDER_FIRST: 125,067 T = 88%, 0 overruns** (manager-verified 2026-10-01); still M1 encounter cap for double-buffer + AY headroom |
| B2 | **Single-buffer flicker — top bug** | staff | Stage 2 E1; `budget.md` §3 |
| B7 ✅ (A7: root cause = render-first used stale visible list; fix vis_room_sync; test #52; user confirmed in Fuse 2026-10-02) | **Old-room monsters visible for ~1 frame after a room transition** when they're left alive (user, 2026-10-02) | staff (A7) | Root-cause + regression test + fix folded into A7 |
| B8 ✅ (A7: `91cf829` + `5ee9ccf`, tests #55–#59) | **Stair softlock: Ghost (flyer) parks on a ladder end and the hero cannot pass** (user, 2026-10-02). Ghost speed 1 is per spec and stays (user) | staff (A7) | Fix (user): **flyers never stop in a ladder's top/bottom box** (mirror of the climber "yield ladder ends" rule, prototype §6.4); regression test. **Follow-up (user, 2026-10-02):** (a) flyers MAY cross a ladder shaft but never end a turn in a ladder-end box (91cf829 walled shafts off — revert that part); (b) a **blocked climb counts as a wait** (costs a turn, monsters act) |
| B9 (also: intermittent W5/W8 + ZRCP timeouts under load, 2026-10-03, pass on rerun) | **Test harness: ZEsarUX launch/teardown stalls** — game.py scenarios take 132 s but wall time hit 37 min (one single-scenario run 919 s, assertions 1.6 s); seen 2026-10-03 under heavy host load (Spotlight/Software Update). Not a game bug | J | Add per-launch timeouts + kill/retry in `tools/test_harness.py`; log launch/close durations |
| B10 ✅ `af48101` (user OK in Fuse 2026-10-03; art approved 2026-10-03: jambs **option B** `#.#.....` / `.....#.#`, grate id 26 over the down-exit hole; canvas artboard B10; art `1f8e7ef` feat/3b-tiles; ids → designer, wiring → staff) | **Open door looks like a glitch: only the top of the door frame (lintel/arch) remains** after opening (user, Fuse, 2026-10-03) | artist → staff | Needs an open-door state in the art (jambs/frame + open leaf per concept-screen door art) and B3B-5's `door_open` to stamp those tiles instead of `T_AIR`; keep the designer rule that arch/lintel cells stay solid. Do with B3B-8 (room builder v2) or the B3B-5 fixes |
| B11 ✅ (fix/b11-b14 `260116a`, merged 2026-10-04: left-exit x=0 matched RD_PITCOL=0 "no pit" → false fall; test W21) | **Invisible pit: falling into a pit where the floor is drawn**, typically when walking from the right room into the left one (user, Fuse, 2026-10-04). Suspects: pit cells built in ROOM_MAP but the scroll/arrival draws floor (NEXT_MAP vs shadow/ornament path), or the arrival x/fall check uses the wrong room's pit col after a horizontal exit | staff | Repro from a generated level; test: after every horizontal exit, screen == ROOM_MAP for pit cells and no fall without a visible hole |
| B12 | **Way down must be a specific, recognisable place, generated with the level map at init** (user, 2026-10-04). It already is generated at init (lair = farthest leaf, level exit `RD_EXITCOL`, game.md §1.1) — but with the 3B stand-in "grate always open" it is drawn as a plain hole identical to the room-to-room down holes, so descending feels random | designer → artist → staff | Make the level exit visually distinct (stairs/portal glyphs + attr, never confused with a down hole), optional log hint on entering the lair; verify only `RD_EXITCOL` triggers EX_LEVEL (fixed in `cd0af15`) |
| B13 | **Decor and animations don't look good** — needs a look/feel discussion (user, 2026-10-04) | user + designer + artist | Schedule a review session on the Design canvas before 3G polish |
| B14 ✅ (fix/b11-b14 `0064b60` + `c6690d3`, merged 2026-10-04: facing tie-break, forced yield, flyer vertical fallback, **squeeze past** on the 2nd block; tests #62/#63) | **Ghost blocks the ladder when a wall is nearby** (user, Fuse, 2026-10-04) — the B8 "fully boxed" flyer case: a flyer wedged between a wall and the shaft stays in the ladder-end box | staff (+ designer) | Fix so a boxed flyer still yields the ladder end (push out vertically within its band, or treat the hero's climb as forcing a yield); regression test with a wall next to a shaft |
| B15 ✅ (not reproducible with the B14 fixes; 8 down-climb cases in test #64) | **Ghost blocks a DOWN ladder** (user, Fuse, 2026-10-05, on the C3-2 build which does NOT yet contain the B14 fixes): hero on top wanting to climb down, ghost to the left with a wall on its left → hero can't descend, ghost doesn't move right | staff | Re-test on main (B14: forced yield + squeeze past); add a test for the downward climb (ladder top box) with a wall on the flyer's side; fix if still reproducible |
| B16 ✅ (`59f3830`: B14's squeeze moved a flyer from the other storey onto the hero's foot cell → crossed storeys; now a cross-storey flyer goes PENDING in place; test #65 band invariant + fuzz. If seen on the pre-B14 C3-2 build, another cause may remain — watch in playtests) | **Ghost sometimes falls to the floor below** (user, Fuse, 2026-10-05) — flyers must never fall (pits, ladder holes, down-exit holes, squeeze-past/yield displacement, PENDING placement) | staff | Repro + root cause + test |
| L1 | **Level layout (user, 2026-10-05):** the level exit is always on the bottom row of the map; no rooms above the entry room — the hero always goes down into the dungeon | designer → generator (Python + Z80) | Rule in game.md §1.1 + levelgen/levelcheck change; affects lair tiers and the 3×3 grid placement |
| D1 | **Decor placement (user, 2026-10-05):** heights look random/unnatural — windows and torches on one consistent height, candles on one height; cobweb is a corner sprite → only in corners; the designed plaster patches never appear; floor-standing decor must sit on the floor, never float | designer → decor deriver (Python + Z80) | Part of B13; rules in concept-screen §3.3 + decorgen/decor_gen changes |
| D2 | **Decor animations rework** — postponed until the game is mostly done (user, 2026-10-05) | 3G | – |
| H1 | **Vertical room transitions:** the hero should visibly climb to the top before the scroll up, and appear at the top of the ladder after the scroll down (user, 2026-10-05) — minor, later | 3G | – |
| B3 | Draft 3 art (32 frames + tiles) not yet reviewed on the canvas | user → artist | Imported provisionally from `assets/gfx/source/draft3_frames.html` |
| B4 | Spec §6.4 text for the new ladder rules | designer | |
| B5 | Fuse / real-hardware tape load not yet tried | user | |

## Stage 2 — design before building · `DONE` (design; E1/E2 continue in 3A) (decided 2026-10-01)

No new gameplay code until mechanics + graphics are designed and approved.
Engine work in this stage = flicker fix + real-hardware measurement only.

### Requirements (user, 2026-10-01)
- **Target: real 128K** (user has hardware). Timing is judged *contended*.
- **Cast:** Warrior (Knight) + Mage (Wizard). **Rogue out of scope** (memory).
- **Stats:** health, **mana**, **hunger**. Hunger **lowers stats** (no
  starvation death). Food: meat + monster drops (apple, carrot, pear, cheese).
- **Warrior uses mana for power attacks**; Mage for spells. **Mage melee =
  staff attack**, always available (the fallback at 0 mana, as in WazHack).
- **Ranged magic (WazHack-like):** each spell has its **own range**; some
  spells **reflect off walls**; each spell has its own projectile/impact
  animation.
- **Monster kinds: up to 4 per level** (+ boss level); pool generated per level.
- **Turn logic runs in the input tick** (+~40 ms latency accepted).
- **Storeys: 2, taller than PROTO's 7 rows**; frees screens/space for icons,
  inventory and menu.
- **Items + inventory:** full-screen inventory page (pauses play); the **bottom
  panel shows the currently selected spell/attack**.
- **Run:** **permadeath**, **no tape save**. **Win:** kill the final boss
  **Necromancer Archmage**, find the **Book of Absolute Death Magic** and
  destroy it.
- **Ranged attacks** with distinct animations per spell/weapon — **magic is the
  focus**.
- **Movement:** **jump = one discrete turn action**. **No attacks while
  climbing** (PROTO rule kept).
- **Screen: at most 2 storeys** (PROTO has 3).
- **Dungeon:** **doors** and **dead ends**; richer **background decoration**,
  some of it **animated**.
- **Controls:** redefinable keys in a **main menu**; **Kempston**, **Sinclair**
  (IF2 / +2 ports), keyboard. Cursor/Protek out of scope. Joystick type chosen
  in the menu (Kempston can't be auto-detected safely). **The whole game must be
  playable with 4 directions + diagonals + FIRE** (movement, jump, attack,
  spell select/cast, inventory); keyboard may add shortcuts but never required
  ones. **Control model (user, 2026-10-01): icon bar + bump-to-attack**
  (Barbarian/Myth-style, free in a turn-based game):
  - directions = move/climb; ↖/↗ = jump (one turn); walking into a monster =
    melee;
  - FIRE tap = use the selected icon toward facing;
  - FIRE held + ←/→ = move the icon cursor (no turn passes; auto-repeat delay);
  - FIRE held + ↓ = full-screen inventory page;
  - keyboard: number keys select icons directly;
  - icon bar in the bottom panel: melee, power attack (Warrior), known spells
    (Mage), quick food/potion, inventory; shows the selection, mana cost, and
    greys out icons that can't be afforded.
- **Sound:** not built this stage, but **memory + frame time reserved for an AY
  player** (music + FX).
- **Art:** graphics-artist drafts frames → user reviews on the Design canvas.
- **Concept review (user, 2026-10-01)** — mockups `assets/gfx/concept/` approved
  in direction (graphics, spells, inventory page). Decisions:
  - Layout **V1 family, revised**: bottom panel grows by **2 message rows**
    ("goblin attacks you and misses") at the expense of storey height
    (→ ~2×9 + 6, designer to confirm); **larger icons**; **worn gear shown in
    the panel** (larger icons if needed).
  - **Larger background objects** (tall torches à la Barbarian / Prince of
    Persia); **brick-wall tile** with patches of missing plaster.
  - **Tile ids → 64** (+288 B).
  - **Door 2 columns** wide. **Floor colours differ per level.**
  - **Warrior: two power attacks, a ranged throw and bow shots.**
  - **Bouncing spells can hit the caster.**
  - **Mage staff swing: dedicated frame.**
  - **Quick slots auto-fill.**
  - **Every level ends with a boss dropping unique gear.**
  - **New monsters:** zombie, mummy, orc, skeleton-archer, necromancer (regular
    caster), giant spider.
  - **Budget levers (user):** sprite sources compressed with **ZX0** (per frame);
    cold code out of bank 2 (generator + boot → bank 5 low RAM, menus → bank 3
    via trampoline) to raise `FRT_MAX`; per-level pool generation.
  - **Spells (Mage) and power attacks (Warrior) are learned only by reading
    books** found in the dungeon.
- **M1 review (user, 2026-10-01)** on `docs/design/game.md`: charm slot (4 gear
  slots) ✓; **longer run — more levels**; **two unique bosses** + the rest
  **"golden" bosses** (recolour + gold-glow attribute cycling); jump + pits ✓;
  **monster resistances** (immune/resist/reflect per damage type, e.g. undead
  immune to cold + life drain; reflected spells can hit the caster); HP regen
  while Fed ✓; **projectiles as real sprites where possible**; walls on **black
  paper with dithered light-brick patches**. User played the A1/A2 build:
  "works well".
- **game.md rev 2 answers (user, 2026-10-02):** Mage bar **keeps the BAG icon**
  (game.md §… to be revised: 10 icons × 24 px = 240 px fits); **AY reserve 7 KB**
  ✓; **Ogre Warlord (D4) + Death Knight (D7)** ✓. A4 measured ZX0: **1.80×**
  per frame (game), 1.69× (concept), **2.71× per kind block**.
- **Art review (user, 2026-10-02):** decor animations ✓; golden-boss glow =
  **SYNC** variant; ZX0 packing = **blocks of 3–4 frames per kind** (A5);
  screens to be redrawn at **9+9+6** for review (fallback 10+10+4); level colour
  schemes ✓; plaster damage = **1–2 "exposed brick" decor patches per room**,
  not whole-wall dithering; wall style **inspired by Bloodstone (ZX), not a
  copy** (ref: `assets/gfx/concept/ref/bloodstone.png`); **Zombie → Vampire**
  (decided 2026-10-02; can turn into the existing bat).
- **Round-4 review (user, 2026-10-02):** layout **9+9+6** ✓; panel ornament ✓;
  panel = **24×16 icons + full info row (name/cost/range) + 16×16 gear**;
  Death Knight = evil-twin Warrior with a **distinct silhouette**; fix-up pass
  (Ogre face, Vampire cape pose, plaster patches, denser wall fragments, Power
  Strike icon).
- **Round-5 review (user, 2026-10-02): concept APPROVED.** Additions: custom
  **6×8 font** for the log, info line and the **inventory page** (more info /
  larger icons there); a custom **larger menu font**; Warrior/Mage must
  **find** books, scrolls, arrows and throwing weapons, and the Warrior **can
  run out** of throwables.
- **Game name (user, 2026-10-02): "TOME OF THE DEAD".** Graphics approved; fonts approved
  (thin 6×8 for the log/info/inventory, 8×16 menu font, 16×16 script title).
  **Stage 2 design closed 2026-10-02.**
- **Pending game.md rev 3 (batch):** 6×8 font + cell-boundary colour rule +
  menu font; finite throwables/arrows found in the dungeon; panel layout 24×16 icons / 16×16 gear; Mage keeps BAG (10 icons); Zombie →
  Vampire on D3/D6/D8 (resists: undead set, weak to fire, drain attack);
  glow = SYNC; ZX0 blocks of 3–4 frames.
- B6 discarded. **B2 flicker is the top bug.**

### Tasks
| # | Task | Owner | Gate |
|---|------|-------|------|
| G1 ✅ | Budget after flicker fix: bytes per bank, contended T per tick, AY reserve, sprite-frame + decor-tile headroom, Rogue bytes reclaimed | z80-architect (read-only) | one budget table in `docs/design/budget.md` |
| M1 ✅ (revision in progress) | Mechanics: core loop, turn/real-time model incl. jump, 2-storey rooms, doors/dead ends/generation, HP/mana/hunger, items + inventory, spells + ranged, monster roster, encounter cap (B1), win/lose, menu + controls | game-designer (Opus) + user | `docs/design/game.md` approved by user |
| G2 ✅ (concept + fonts approved) | Art direction + asset list: Warrior/Mage frame list (jump, climb-attack, cast/ranged per spell), projectiles/FX, decor tiles, doors, HUD (HP/mana/hunger), inventory screen | game-designer → graphics-artist drafts on canvas | user approves on canvas |
| E0 ✅ (user: better, double buffer still needed) | Reorder experiment: render right after the HALT, anim/logic after it; measure render timing vs the beam. Also scouts a single-buffer approach for a possible future 48K port (48K itself out of scope) | z80-junior (manager-authorised exception: `play_loop` order only) | measured before/after + user eyeball; decides how E1 proceeds |
| E1 | Flicker fix: double buffer (option A or B, `budget.md` §3); clean background rebased to bank 7 `$E000` | z80-staff-engineer | tests green; user confirms no flicker in Fuse **and on hardware** |
| E2 | Real-hardware run: tape load + contended worst-tick measurement | staff + user | recorded worst tick vs budget |

Order: G1 → (M1 ⇄ G2) ; E0 → E1 (parallel to M1/G2) → E2.
Stage exit: game.md + budget.md + canvas art approved; E1/E2 done → Stage 3
(build) is planned from these.

## Stage 3 — build · `TODO` (draft 2026-10-01; detailed per phase once game.md lands)

Principle: foundations first (no gameplay change, provable by the existing 179
tests + flicker/budget scripts), then vertical features each ending playable.
Tags: **[S]** z80-staff-engineer (Opus), **[J]** z80-junior (Sonnet). Phases
3B–3F get a z80-architect breakdown when started (contracts + tests).

### 3A — Engine foundations · can start now (independent of M1)
| # | Task | Tag | Depends | Gate |
|---|------|-----|---------|------|
| A1 ✅ `10ad983` | Merge E0 `RENDER_FIRST` + `tests/flicker.py` as the flicker baseline | J | user eyeball | 179/179; flicker numbers recorded |
| A2 ✅ `10ad983` | Remove the Rogue (frames, tables, select screen, tests) | J | A1 | tests green; budget §2 bytes reclaimed |
| A3 ✅ review: ship (feat/cold-code) | Cold-code relocation: generator + boot → bank 5 low RAM; menus/select → bank 3 via bank-2 trampoline; memory-map | S | A2 | `.sna` behaviour identical; tests green; bank-2 headroom measured |
| A4 ✅ `4593389` (feat/zx0-tools) | ZX0 sprite sources: tool side (pack per frame in `gfx_convert`/`svg_sprites`, sjasmplus include) | J | A2 | round-trip decode test bit-exact |
| A5 ✅ review: ship (feat/zx0-engine) | ZX0 engine side: decompressor in fixed RAM, generator unpacks per frame into `GEN_SRC` | S | A3, A4 | pool bytes identical to today; boot time measured |
| A6 ✅ review: ship | Raise `FRT_MAX` (to the M1 number) + tile ids 32 → 64 | S | A3 | tests green; memory-map |
| A7 ✅ review: fix-then-ship → fixed (`91cf829`, `5ee9ccf`), merged 2026-10-03 | Double buffer (E1, option A/B — decide after A1 eyeball): bank-7 clean bg rebased to `$E000`, present/flip | S | A3 | flicker.py = 0 events; budget measured; user confirms on hardware |
| A7b ✅ review: ship → follow-ups `709dd67`, merged 2026-10-03: mix 140.2k → 121.4k T, heavy 144.9k → 121.0k, flicker a 146.0k → 122.1k, 0 overruns; test #60 (merged rects vs full recomposition) | **Renderer optimisation** (erase + overlap repair; render is 98k T of the worst tick) — **hard prerequisite for A8** (A7 re-review 2026-10-02: present = 26.4k T of the worst mix tick, render 98k → 107k, mix worst 98.8%; flicker-a worst 125.8k → 144.5k T, overruns; overrun ticks present mid-frame without HALT) and before 3D adds projectiles | S | A7 | worst within-cap tick ≤ ~126k T (141.8k − 13k AY − 1k stub − margin); ideas: attr-only present for DIRTY_ATTR cells, merged move rects; bank-2 room via boot-copy of present/pmark to $B200 |
| A8 ✅ review: ship (`5a3922d` + docs `953dfbd`), merged 2026-10-03: ISR 620 T/frame, worst mix 120.8k T, headroom for a 6.5k T/frame player ≈ 7.3k T | IM2 + ISR stub + silent AY player slot (**7 KB** reserved bank 3 at `$E400`, game.md §11.2), `SYS_FRAMES`/ROM chain kept | S | A3 | tests green; ISR cost measured; no DI windows |
| A9 | Real-hardware gate (E2): tape load + contended worst tick on the user's 128K | user + S | A7, A8 | recorded |

Parallel: A4 ‖ A3; A6 ‖ A7 ‖ A8 after A3. **User 2026-10-02: once A7 is merged, start 3B in parallel with A8 + A9** (3B does not touch the ISR).

A3 review carry-overs (z80-reviewer, 2026-10-02):
- **A6:** `ASSERT start == lowram_code` clashes with descriptors placed below
  `lowram_code` in the CODE block → place them after `start` or rewrite the
  assert + SAVETAP start.
- **A7:** `page_bank` forces bit 3 = 0 and `restore_page` restores the whole
  byte → keep the current screen bit in `page_bank`; `restore_page` takes only
  bits 0–2 from the saved value. Transition scrolls draw on the `$4000` screen.
- **3F:** generator must run before `build_room_map` and never during a
  do_exit scroll (`GEN_SCRATCH` aliases ROOM_MAP/NEXT_MAP) → add a debug trap
  counter in `gen_frame` asserted by tests.
- Optional: move the scroll LDI movers (~350 B) / `gen_variant` inner loop
  (~80 B) back to bank 2 to undo the +7% transition / +14% boot slowdown.
- Optional test: breakpoint on PC in `$C000-$DFFF` with `$7FFD&7 ≠ 3`.

A6 review carry-overs (z80-reviewer, 2026-10-02; **first part of A7**):
- Clear `GEN_ZBLK` at the top of `build_room_map` (where GEN_SCRATCH is
  overwritten), not only in alloc_*; 3F must still call alloc_reset/restore.
- tests/zx0_pool.py stale-cache check: look the block up via
  `fdesc_tab[FID_wizard_idle]` FD_BLK and assert it is non-zero.
- ASSERT `FT_OFFR == FT_H+1 && FT_OFFL == FT_OFFR+1`; ASSERT K_COUNT ≤ K_MAX
  and ≤ the KROW width.
- build.sh: skip the packer for `-DZX0_SOURCES=0`.
- gen_kind guard for a 0-frame kind (Rogue hole: B=0 → 256 frames).
Decisions (user, 2026-10-02):
- **Fonts** (6×8 768 B, menu ~0.96 KB, title 864 B) live in **bank 3** and are
  **copied at boot to runtime RAM `$B200..$B7FF`** (6×8 must be always
  mapped; menu/title may stay paged with the bank-3 menu code). Bank-2 image
  tail (677 B) is reserved for Stage-3 hot code.
- **Resistance table** cannot be 1 B/kind (6 types × 3 bits = 18 bits): give
  it its own 96 B table (third kind page or bank-5 spare) — confirm in 3D.

A5 review carry-overs (z80-reviewer, 2026-10-02; done in A6):
- Clear `GEN_ZBLK` in `alloc_reset`/`alloc_restore` so the unpack cache never
  outlives a session (3F safety); add a negative stale-cache test.
- Single build entry point (`tools/build.sh`: packer → sjasmplus), used by the
  build/test skills and tests — avoids assembling stale packed art.
- `tools/zx0_pack.py`: strict `DEFB $xx` parser (fail on other tokens).
- A6: fold block+offset into the low-RAM FDESC descriptors; drop the banked
  4-B descriptors + `copy_virt` in `zx0_frame`.

### 3B — World & screen · `DONE` (squash-merged 2026-10-04; feat/3b-world @ `a791918`)
2-storey rooms + new panel rows (icon bar, bars, worn gear, 2-row message log);
per-level floor colours; decor tiles (static, animated, large multi-cell, brick
walls); doors (2-col); dead ends; level generator; room transitions for the new
geometry. **Exit:** walk a generated level, doors open, decor animates, log shows.

**3B breakdown** (z80-architect, 2026-10-03). Decisions: D1 room id = 3×3 grid cell, fixed 16-B descriptor + 6-entry door edge table, level state ≈ 290 B in low RAM `$6D40..`; D2 `TILE_FLAGS[64]` collision via `map_cell`; D3 2 storeys × 9 rows (`ROOM_ROWS` 18, MOD9/DIV9 tables); D4 rows 0–17 playfield (row 17 scrolls), rows 18–23 panel only, HUD tracking for text rows 20–23; **D5 (user 2026-10-03): panel updates queued, one item per tick, never in the input tick, ≤ ~3 ticks latency**; D6 animated decor `ANIM_LIST` ≤ 12 cells, `decor_tick` ≤ 2 glyph + 3 attr cells/tick, writes bank 5 + bank-7 shadow, occupancy mask skips cells under sprites; D7 generator / `build_room_map` v2 / decor deriver / `panel_init` in bank 3 via `far3`; D8 6×8 font boot-copied to `$B200..$B4FF`, `$B500..$B7FF` kept for boot-copied hot code; D9 own `GEN_RNG`; **D10 (user 2026-10-03) stand-ins accepted**: potions only floor items, fixed per-room population with today's kinds, lair grate open, D8 descend = win, keyboard close-door until 3C. Budget: ≤ 126k T worst tick after A8 (~4.5k for all of 3B). Goldens: split playfield (rows 0–17) / panel (18–23) hashes; rebase only in separate `test: rebase goldens` commits after a PNG look.

| ID | Task | Tag | Deps | Exit |
|---|---|---|---|---|
| B3B-1 ✅ `95d6d44` (feat/3b-world; image byte-identical) | Layout allocation (`src/level_defs.asm`, memory-map), no behaviour change | S | A8 merged | build clean, suite unchanged |
| B3B-2 ✅ `4e813b9` + B10 `fcfde52` (feat/3b-tiles; jambs ids 11/14, grate 26; cobweb/moss per-level — D4/D5/D7 full at 28 so they get neither: designer may swap later); user to review previews; `T_GRATE` art missing (placeholder) | Tiles / icons converter + level tilesets (`tools/tiles_convert.py`) | J | B3B-1 (id enum) | attr legality, no decor in floor rows, byte counts |
| B3B-3 ✅ review: ship (`422ea2f` + goldens `a7a10e0`, feat/3b-world; nits folded into B3B-5): world W0–W4, game.py 269/269, worst 121.1k T | 2×9 geometry switch; rooms A–D re-authored as 2-storey | S | B3B-1 | `tests/world.py` W1–W4 |
| B3B-4 ✅ folded into B3B-3 (every scenario ported, no skips) | Port game/budget/flicker suites to 2×9 | J | B3B-3 | all green; budget recorded |
| B3B-5 ✅ fixes `7dc84c2` + hardening/B10 `af48101` (goldens `05eb7e6`), re-review: ship; user OK in Fuse — impl `355fd3e` (+ nits `6f55bb6`, goldens `cf85eaf`), review: fix-then-ship (flyer body-box vs door arch 🔴; PENDING bodies in close check; jump test gaps) — fixes in progress. Generator contract (→ levelcheck): a pit's landing cols p..p+2 on storey 1 must be floor with no ladder hole/block. UP+diagonal at a ladder foot now jumps (spec) | Collision, doors, pits, dead-end blocks | S | B3B-3 | W5–W9; mix ≤ 126k |
| B3B-6 ✅ `556969a` (feat/3b-levelgen): 8,000/8,000; full 65,536×8 scan: max 4 restarts, 15 reseeds, 774 rnd calls | Python reference generator + invariant checker | J | B3B-1 contract | 1,000 seeds pass |
| B3B-7 ✅ `8b62e17` (feat/3b-levelgen-z80; reviewed, fixes + pit geometry in): byte-exact Z80==Python (10,243 cases incl. 10k retry seeds), full 65,536×8 scan clean; ~1.7 KB bank 3; worst 1.36M T; pits/level 3.25 → 1.84 after the pit rules. **Exhausting d8 seeds now 55352–55354 → `level_gen` B=1/CF: B3B-12 loops until B=0.** B3B-12 also: LG_* scratch aliases GEN_SCRATCH → call before build_room_map, then alloc_* + gen_kind; check MASTER_SEED→LVL_SEED mixing; ≥1 Heal → 3E | Z80 level generator (bank 3) | J (→S) | B3B-1, -6 | W10: dump == levelgen.py, 20 seeds |
| B3B-8 ✅ `0d5cb81` + goldens `3068162` + review fixes `8f6c0a4` (review: ship): room builder v2 in bank 3, PROTO rooms as a level state (ids A0 B1 D3 C4), tilesets in bank 7 via 2 new tape blocks; user OK in Fuse | `build_room_map` v2 + theme load | S | B3B-5, -7 | W11, W12 |
| B3B-9 impl `a3f83d4` (merged into feat/3b-world `05aefc9`), review: fix-then-ship → fixes folded into B3B-10 (staff-only files): 🔴 ANIM_LIST stale after a NEXT_MAP build + scroll swap (fix: second list ANIM_N2/ANIM_LIST2 filled by NEXT_MAP builds, ldir into ANIM_LIST after the swap); 🟡 PROTO build must zero ANIM_N; memory-map/contract + decor_gen.asm cost header (47–72k T); W13 checker: wall-heavy sweep / synthetic maps, large-object count. Room entry ≈ 117k T static before the scroll (not a tick) — TRIES=12 kept | Decor deriver (bank 3) | J | B3B-8 | W13 |
| B3B-10 ✅ `3ec47e3` (review: fix-then-ship; caps 1 glyph + 2 attr/tick, OCC_MASK dropped for direct RLIST tests; no animation in PROTO rooms — visible from B3B-12) → **B3B-R2 ✅ `b85e352`** (review: ship): bank 2 207 → 1,745 B, bank 3 3,617 → 2,059 B (src/turn3.asm), heavy worst 116.2k → 120.5k T. **Raw build (-DZX0_SOURCES=0) is now the tightest gate** (bank 2 187 B, bank 3 675 B: turn3 assembles into bank 2 there) — manager decision: retire the raw build from the gate in B3B-12 (zx0_pool compares against Python reference pools) (was: bank 2 207 B: move ai_flyer, do_attack, potion/materialise (+ ai_monster) to bank 3 via far3, ≈1 KB). Contract for B3B-12: first room of a new level built into ROOM_MAP (or NEXT_MAP + room_shadow) so ANIM_LIST is valid. Was: (staff; + B3B-9 review fixes, + B3B-11b nits: x%8 ASSERTs; B3B-13 token getter must emit chars 32..127 only) | `decor_tick` | S | B3B-8 | W14; flicker 0; mix ≤ 126k |
| B3B-11 ✅ `05073a1` + goldens `003fb89` (review: fix-then-ship; LOG_TXT at $5B00 safe) → **B3B-11b ✅ `48dfb3d`** (review: ship): bank 3 back to 3,616 B free (vdata in bank 1), print6 678 → 461 T/char, heavy-fight log latency ≤ 6 ticks (**user 2026-10-04: accepted**), was: bank-3 relief (font + hot image → bank 1; bank 3 was 1,082 B free after the decor merge), quad print6 (~330 vs 678 T/char), D5 latency in heavy fights (was ≤ 7 ticks), GS_DEAD/WIN never dropped, MAXHP poll | Panel engine (`print6`, `log_push`, bars, `PANEL_DIRTY` queue) | S | B3B-3, -2 | W15; panel golden; mix ≤ 126k |
| B3B-12 ✅ `d289251` + review fixes `cd0af15` (review: fix-then-ship → fixed; nobody follows on descent — designer; level exit checks RD_EXITCOL + LF_GRATE_OPEN; HERO_CARRY mask for 3D statuses; open: master-seed entropy is weak (HALT-paced select loop) → mix key-hold timing in 3C's menu): new game on a generated D1, descend to D8 → win stand-in, DEPTH card, seed = master + depth×$9E37, raw build retired (zx0_pool vs Python reference), proto_start flag keeps rooms A–D for tests; level change ≈ 0.6–1.0 s (note from B3B-3 review: arriving via a shaft puts the hero inside a ladder-end box where a flyer is "fully boxed" and may attack every turn — keep flyer spawns away from the arrival shaft; designer to confirm) | Level change (`level_enter`: start + descend) | S | B3B-8, -11 | W16; `GEN_TRAP` 0 |
| B3B-13 ✅ `7eb4ab6` + goldens `bb68051` (review: ship) → B3B-13b ✅ `b0af542` (drips placed, "YOU PICK UP A POTION", notes; decor_room now 57–100k T per room entry) + drip 16-tick hold in decor_tick (manager decision; in progress): all messages via the log, token text (tools/textpack.py, build-time round trip; 24 strings, +39.5 T/char), PROTO chest/zap removed (ids 17/18 → T_DRIP1/2, placement rules → designer, deriver follow-up), rooms A–D kept for tests | Message strings via `log_push`; drop PROTO-only code; **text compression (user 2026-10-03):** dictionary-token format for log messages / item & monster names (upper-case charset + 1-byte tokens for common words, per-char decode in `print6`, random access, built by a Python tool from the real string list with a build-time round-trip check); ZX0 blocks for long static text (menus, help, book/scroll text, title/end screens) from 3C | J | B3B-11, -5 | strings ≤ 32 chars (ASSERT) |

Merge order: A8 → B3B-1 → B3B-3 (all budget numbers count after A8). Risks: tick budget (R1), bank-2 bytes ~1 KB new hot code vs 1,067 B (R2: boot-copy to `$B500`, delete PROTO code), bank 3 ≈ 4.1 KB of 7.4 KB (R3), golden churn (R4), Python↔Z80 generator byte equality (R5).

### 3C — Hero, controls & menu (needs game.md §2–4)
Main menu, redefine keys, joystick select (Kempston/Sinclair/keys); icon bar +
bump-to-attack + FIRE modes; jump; Warrior/Mage new frames (jump, staff swing).
**Exit:** whole game driveable by joystick alone (scripted ZRCP test per input).


**3C breakdown** (z80-architect, 2026-10-04): D1 one STICK byte from redefinable KEYTAB + Sinclair presets + Kempston (JOY_MIRROR for tests); D2 turn-intent machine (FIRE tap / hold+←→ cursor / FIRE+↓ bag / FIRE+↑ pause, ↓ = wait, turn-around 0 turns); D3 icon bar polled like HP; D4 menu/pause/end screens in **bank 1** via `far1`; D5 pause = 3-row overlay saved in GEN_SRC+GEN_MIR; D6 seed entropy from a busy-loop counter in the menu; D7 HERO_ST block (reserves 3D's LVL/XP/ranks/MP). **User 2026-10-04:** title "TOME OF THE DEAD"; Sinclair disables its half of the 1–0 shortcuts; pause Quit confirms; XP/levels/ranks logic in 3D (3C shows level digit + LV/XP line).

| ID | Task | Tag | Deps |
|---|---|---|---|
| C3-0 ✅ `3ab9232` | layout (HERO_ST, JOY_MIRROR, KEYTAB, bank-1 ui1_code) + `far1` + helpers restore the caller's bank | S | – |
| C3-1 ✅ `d49ed46` + review fixes `4dcea7c` (review: fix-then-ship → fixed; KROW removed, stack back to 768 B (measured max 40 B, W20), per-tick STICK, BREAK priority) | `read_stick` input (keys/Sinclair/Kempston) | S | C3-0 |
| C3-2 ✅ `8f7c9b0` (review pending; `legacy_input` flag keeps old controls for the suites until C3-8a; bank 2 +391 B) | turn-intent machine + icon dispatch | S | C3-1 |
| C3-3 ✅ `306c251` + goldens `8825c3f` (main merged `23dd851`; review pending; **bank 3 down to 278 B free → bank-3 relief before C3-6**; user 2026-10-05 tried C3-2: no visible cursor — confirms C3-3's highlight is the missing piece; also show which slot is the potion) | icon bar state, cursor, info line, level digit | S | C3-0, C3-4 |
| C3-4 ✅ `61ac18f` (feat/3c-strings; 85 strings 1,312 → 1,141 B, 33 tokens; ZX0 long-text blocks; **C3-6 must INCLUDE build/text/longtext.asm DISPed in bank 1 and size the unpack buffer LT_BUF_MAX; 42-char info lines must not use the 32-B MSG_BUF**) | info/refusal/menu strings + ZX0 long text | J | – |
| C3-5 ✅ `3b6f6ae` (feat/3c-menuart; 1,104 B: font 656 + title 277 + torch 107 + map 64) | menu fonts/title/torch art convert | J/artist | – |
| C3-6 | menu, redefine, pause overlay, end screens, seed entropy (bank 1) | S | C3-0/1/4/5 |
| C3-7 | JUMP1/2 + Mage STAFF_SWING frames (art first) | S | art |
| C3-2b ✅ `7c58ca7` (review pending) | **icon mode via DOWN+FIRE** replaces FIRE-held cursor moves (user 2026-10-05; designer defines §3.1/§3.5) — rework of C3-2's intent machine after C3-3 | S | C3-3 |
| C3-8a/b | port suites to the menu start + joystick-only exit runs | J | C3-1/2/6, C3-3 |

Bugs B11/B14 fixed on main (squash 2026-10-04). **Merging main into feat/3c-hero needs an address fix: B14's CLIMB_BLK_ID/N at $BFC7/$BFC8 clash with C3-1's PLAYER_SC at $BFC7 — reallocate one side.** B12 gate art: **user 2026-10-05 chose variant B** (lattice bar, `gate_raised_b`, `9d3b091` feat/3c-gate); marker above the exit: **glow** as a per-level id on every level (user 2026-10-05, option a; D5/D7 drop PILLAR, D4 drops one decor item); COBWEB_R + gate variant B in tiles `f8a78c8` (feat/d1-decor); staff to draw id 26 on the open lair exit (flag TF_LADDER|TF_HOLE, not TF_FLOOR) + glow + lair hint; closed 3F gate as drawn unless the user changes it.

### 3D — Combat & magic (needs game.md §4–6)
Projectile entities (range, wall reflection, can hit caster); spells; Warrior
power attacks ×2, throw, bow; mana; impact FX. **Exit:** spell/missile table
reproduced by tests.
3D also implements **status effects** (game.md §6.4, user 2026-10-03): `ENT_STAT` 16 × 4 B,
status step at each entity's phase start, HOLD/MIND/POISON/WEAK, held-hero auto-turns, tints
+ 2 panel icons, boss/resistance/immunity rules (§9.1 mask; 3rd `kind_tab` page). Tests:
seeded Frost freeze = exactly 2 skipped actions; sleeper wakes on damage; STUN_GUARD; poison
never below 1 HP; confused reversal + `YOU STUMBLE.`; boss halving.
3D also implements (game.md rev 5, user 2026-10-03): **ability ranks** (§5 rank table, `ARANK`
2 B, current-rank rows copied to bank 2, roman suffix on the info line), **ability gates**
(Mage: staff only until a book; Warrior: bow needs the bow bag item + ARROWS, `NO BOW.`), and
**XP/levels** (§4.1: `KXP` column, `XP_NEXT`, level-up W +4/+1, M +3/+2, atk L4/L8, eva L6,
panel digit at (31,19), BAG info line). Tests: seeded kill → XP and level-up at the
threshold; respawn half XP; rank 2/3 values per ability; no spell before the first book.

### 3E — Items, inventory & survival (needs game.md §7–8)
Inventory page (bank-5 screen), equip, quick slots auto-fill, food/hunger,
books → learning spells/power attacks, potions/scrolls, boss unique loot.
**Exit:** pick up → equip → eat → learn spell, all tested.
3E also implements (user 2026-10-03): **traps** (game.md §1.5: generator step placed last,
`T_TRAP` = id 10, search on Wait, Mage trap sense, levelcheck invariants; ALARM effect waits
for 3F's wave code), **blessed/cursed gear** (§8.7: odds, sticky curse, Enchant uncurses),
**light identification** (§8.8: per-run appearance shuffle, `KNOWN` byte, naming, unknowns
never auto-fill), the **item record** (§8.9) and the Sleep scroll / extended Cure (§8).
Tests: trap placement 1,000 seeds Python == Z80; trigger/search/jump-over; cursed unequip
refused until Enchant; identify-on-use + elimination.
**Rev 5 (user 2026-10-03) supersedes the cursed rule above:** cursed `m` ∈ {−2,−1,+1,+2}
rolled by depth (`ISTATE` bits 5–7, bit 2 HIDDEN until equipped), sticky until **Enchant
blesses** it (`m = max(m,+1)`) or a **projectile hit shatters** it (1 in 4, uniform among worn
cursed slots; DART counts); no regen penalty (§8.7). Book placement: generic class books,
content decided at READ (§5), 2nd book 1 in 2 on D4–D7. Tests: reveal on equip; Enchant
blesses all worn cursed; seeded shatter empties the slot (fists 1d2); book read order
(unlock → rank-up → tome); levelcheck includes the cursed value roll and extra books.

### 3F — Monsters, bosses & win (needs game.md §9–10)
Per-level pool generation (≤ 4 kinds + boss); new monsters (zombie, mummy, orc,
skeleton-archer, necromancer, giant spider) + ranged AI; level bosses; Necromancer
Archmage + Book of Absolute Death Magic → win. **Exit:** full run start → win.
3F also implements game.md §9.5 (respawn trickle while the boss lives; idle wave behind `IDLE_WAVE`, default off).
3F also implements **monster tiers** (game.md §9.6, user 2026-10-03): 12 tier rows (30/32
kinds), spawn roll from `T2_BASE`/`T3_BASE` + `Δ` (rev 5: `LVL − d`, game.md §9.6), tier abilities (on-hit
status, parry, rage, breed, summon, sniper/slinger), drop/XP scaling, and the ALARM trap wave.
3F also implements **gear wear** (game.md §8.10, rev 5, user 2026-10-03): NOTCH on parried
melee (Skeleton Guard/Knight, Death Knight, 1 in 2) and ACID on Black Widow bites (1 in 4,
armour else helmet), `m −1`, floor −3 then destroyed, blessed immune. Tests: seeded notch/acid
lowers `m`; destruction at −3 empties the slot (frees a cursed slot); blessed unchanged.

### 3G — Sound & polish (later)
AY music + FX on the A8 slot; balance pass; hardware hardening.

## How we control state

- This file is authoritative; the manager updates it on every transition and
  records which gate passed. Finished phases move to `docs/history.md`.
- A phase is `DONE` only when its exit gate is demonstrated via build/run/test.
- Scope changes are decided by manager + user and reflected here first.
- Delegation and token rules: `CLAUDE.md` (Delegation map, Token budget rules).

## Risk register

| Risk | Mitigation |
|------|------------|
| Frame-tick budget with more entities (B1) | Reviewer tracks T-cost per change; `tests/` budget scenario; staff-only for tick code |
| Attribute clash on new art | Canvas convention + importer validation + round-trip |
| Junior/staff contract drift at integration | Contracts carry args/clobbers/addresses; shared layout files staff-only; reviewer on combined diff |
| Scope creep | Next phases only after the concept review |
