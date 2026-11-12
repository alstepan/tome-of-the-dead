# Delivery plan — Tome of the Dead

> Manager-owned control document: **current state only**. Every phase has a
> verifiable exit gate — state is proven by build/run/test, not by opinion.
> Past decisions and evidence (P0–P3, SPIKE-1..4, PROTO, Stage 2, the whole
> Stage 3 log with every bug/task row and ruling): `docs/history.md`.

Status legend: `TODO` · `IN-PROGRESS` · `BLOCKED(reason)` · `DONE`

## Baseline

The PROTO fighting prototype (`main` @ `75eeabd`, 2026-10-01) grew into the full
game: side-view rooms, Warrior + Mage, 8 depths, bosses, items/gear, AY sound,
end card. Spec: `docs/design/game.md`; layout: `docs/memory-map.md`; full baseline
and per-task evidence: `docs/history.md`.

## Status summary

| Phase | Status | Merge / evidence |
|-------|--------|------------------|
| C1 cleanup & pipeline | DONE | `feat/cleanup`, 2026-10-01 |
| Stage 2 — design before building (game.md, budget.md, art direction, E1/E2) | DONE | double buffer A7; real-hardware load A9 (user 2026-10-06) |
| 3A engine foundations | DONE | merged |
| 3B world & screen | DONE | squash `a791918` (2026-10-04) |
| 3C hero, controls & menu | DONE | squash `d92d0a4` (2026-10-06) |
| 3D combat & magic | DONE | merged |
| 3E items, inventory & survival | DONE | merged |
| 3F monsters, bosses & win | DONE | merged |
| 3G sound & polish | DONE | late batch merged: LOG-DMG `c64d21e`, D3-11 flying numbers `a7d2645`, LVL floater `90a6f02`, ROOM-MEM `80519a8`, INSTR pages, loading screen L3d, END-WAIT, BAL-1 FINAL, VAMP-BOSS, vbat, STATS1 S1, RECLAIM-*, TRAP-TILE, FLY-CLIMB, LEFTOVERS, DBG-1, GEAR1-3, WIN2, BOSS-RANGED, ENDCARD, SND-0 (sound), LOOK-1 |
| FINAL-1 rename to Tome of the Dead | DONE | `b25e043`; user completed the repo/remote/dir rename steps |
| FINAL-2 GitHub CI + releases | DONE (release job: PR #3) | PR #1 merged `7e670f6`; `v*` tag → GitHub Release (.tap/.sna/SHA256SUMS) |
| H1 visible climb across vertical exits + D1 entrance ladder | DONE (user approved in Fuse 2026-11-05; reviews: ship ×2) | `feat/h1-climb` abfba80 + 5fd61bf + d5962ed; bank 7 low 18 → 3, bank 2 16 → 9, bank 3 13 → 10; worst tick unchanged |
| H1-ARRIVAL every depth arrives mid-ladder at the shaft top (like D1) | DONE (user 2026-11-05; review fix-then-ship → trickle bound fixed) | `feat/h1-arrival` d209a9d + 22273a3; bank 3 10 → 92, bank 1 2 → **1** |
| WIDOW-SPIT Black Widow poison spit (P6 every 4th turn) + Warrior +5 HP/level | DONE (user 2026-11-05; sim W 40.5 / M 40.4; review: ship) | `feat/widow-spit` dff9837 + 528671a; R6 1 → 52, bank 3 92 → 36; budget `wroom4` (4 Widows spitting) 97,873 T work; **`wroom` gated on real ≤ 141,816 like `blair` (user accepted; walk tick 126,696 work)** |
| STATS2 end card BOOKS read/found + ITEMS found | DONE (user 2026-11-05; review: ship) | `feat/stats2` b2e0589; R6 52 → **3**, bank 3 36 → 17, bank 7 low 3 → 2, b0 16 → 14 (kit **0**) |
| TRAP-OR revealed trap plate OR-composited over decor (bug since 3E-T16 785d4ad) | DONE (user playtest 2026-11-05; colour: the trap keeps its own ink over decor, user ruling; reviews: ship ×2) | `fix/trap-or2`; bank 3 17 → **7** (kit 3), bank 7 low 2 → **1**; t16 F1 fixed (stale since H1-ARRIVAL) |
| FINAL-3 itch.io project + release | IN PROGRESS | 3a: page + licences done (uncommitted, feat/itch-page), media re-record running; 3b: repo public → tag v1.0 → user uploads; 3c dropped |

## Active / next

**TUT0 — DEPTH-0 TUTORIAL: DONE — merged to main 7ab186f (PR #19, squash, 2026-11-11).** Spec `docs/design/tutorial_d0.md`, decisions `docs/design/tut0_split.md`. Blob in bank 4 (now `$E1B4`, 8 B free after the C merge), mentor Brother Morrow, Goblin, mercy heal, sandbox reset into D1; R4 key clarity (pinned goal line, ▶ ANY KEY, nudges 6/18). Playtest round 3: OK. Known/accepted: B3 inside ICON MODE leaves row 20 blank until the turn ends.

**POST-TUT0 ROADMAP (user 2026-11-09, in this order; each starts after the previous merges):**
1. **C + C2 — blit-time sprite mirroring, FULL C — DONE on `feat/mirror-c` (f0550cc + merge of main 8141cc0 + layout commit; squash-merge required, 8141cc0 alone does not assemble).** SP-safe ISR (own stack, ISR_ROM_CHAIN dropped), pop blit 36 T/B, mirror chains `src/mirror2.asm`, monster phase 1 tick after the hero, dn_q2 gate, every non-SYM frame |MIR (incl. skeleton_walk, user 2026-11-11 "Full C, accept slowdown"). C+TUT0 layout: boot streams one bank-4 tape block `$C100..$DCDA` (TT_BOOT4_REC 6), in_tut unpacks to BLOB_ORG, BLOB_ORG `$E000`→`$E1B4`. **B0_FREE = `$CD88..$FC3D`, 11,958 B** (POOL_START `$FC3E`); min slack 2,976 B (D8 W). B0 carve capped by the D0 tutorial pool vs BLOB_ORG (212 B) — a bigger carve needs D0 pool rework (revisit with Tutorial v2). Budget: lwalk 151.0k real (10 ticks over) and lwalk4 160.9k (12 over) ungated measurements; rwalk 133.0k gated. Reviews: fix-then-ship ×2, fixed. Gate green (tut0 179, tut0_adv full soak 40 seeds 0 fail, game 342, world 2585, zx0_pool 303). Measurements: docs/design/perf_survey.md, docs/design/budget.md "C+TUT0". ADAPT-DEFER (user 2026-11-12 after A/B playtest): monster phase back on the input tick (main's tempo); defers only if the input tick is already in its 3rd frame. Budget rule: input ticks ≤ 3 frames (real 212,322), other ticks ≤ 141,816; rwalk/lw24/lw24g reported (render ticks of in-step walks, = main). Frames/turn = main everywhere except 5-body left walks (7.3→8.3) and D4 Ogre+3 Orcs left (8.4→8.8). Shelved: hot AI/try_player_turn → B0 (3–5 KB move incl. callees + new tape block; gain only on those walks); mirror cache if they matter. Playtest: "performance feels good".
2. **AI-SEEK2 — smarter pursuit** (`docs/design/ai_seek2.md`; defaults approved; `seek_col` in bank 6 via far6, not bank 2).
3. **New monsters + pit-stuck ranged fallback** (`docs/design/new_monsters.md`, approved with amendments: kind cap 5 on D4–D7 where the pool fits, Imp/Wraith share a kind_tab row (ASSERTed), new Frost Charm item, freeze 1-in-4; sources in C's carved bank-0 pages).
4. **DECOR2 — composed decor** (`docs/design/decor_rules2.md`): Python model + before/after room previews → user review → P1 (junior) → P2 planner in bank-0 cold code (NOT an R6 page: R6 is pinned at the boot-block ASSERT); re-run tools/tut0_level.py seed search (D0 ≤ 10 ids). **+ user 2026-11-09: some levels feel EMPTY — add more decor; user priority = (b) MORE OBJECT TYPES (over density):** (a) density per depth/room role in the DECOR2 mood tables (data, cheap); (b) more object types where per-level tile ids allow (D1/D3/D8 have no spare of the 28 per-level ids — needs id reclaim, e.g. sharing/deduplicating glyphs, or moving rarely-seen common ids to per-level); new art via the Design canvas.
4b. **"TOO WEAK TO LEAP" refusal message** (user 2026-11-09): engine-wide log line when WEAK blocks a jump (today silent; few bytes near try_jump in low RAM → needs C-era space).
4c. **Tutorial v2 — gear, stats & items lesson** (user 2026-11-09; widened 2026-11-10): Brother Morrow explains gear (weapon/armour/helm/ring/amulet: what each slot does, the stats it changes, blessed/cursed) **and the other items/treasures (what HOW TO PLAY covers today)** — designer spec first; blob space after Revision 2 ≈ 860 B, else C-era space.
4d. **DONE — PR #17 `845f1b7` (one wave per plate; left-behind wave bodies discarded; investigation `docs/design/alarm_investigation.md`).** ALARM trap escape (user 2026-11-09, playtest): after an ALARM a monster appears on every room enter/exit, so there is no escape without a fight. game.md §1.5 says ONE wave (1–2 monsters at the room's doors, awake, F_RESPAWN, counts toward RESPAWN_MAX 6). First investigate (junior/staff with ZRCP): bug vs intended interplay — awake wave bodies following through exits (follow rule), the re-arming plate re-firing on a back-and-forth, the §9.5 trickle into room records, or spawn-on-entry. Then designer: a deliberate escape (e.g. alarm bodies don't follow / follow limit, a cooldown, the wave spawns once in the trap room only).
5. **HOW TO PLAY always available — LIKELY DROPPED (user 2026-11-10: "might be dropped if we teach about items in the tutorial"; decide after 4c's spec — if the tutorial covers items + treasures, drop item 5 and reclaim the HOW TO PLAY streams (~2 KB boot stream) for the blob/B0).** Original (user 2026-11-09, LAST): a 3-option choice screen (1 TUTORIAL / 2 HOW TO PLAY / 3 START) with the HOW TO PLAY pages kept resident (~1.5 KB packed) in C's carved bank-0 pages — only if space remains after the new monsters' sources. The treasures stay on HOW TO PLAY (reference), not in the tutorial.

**FINAL-2 — GITHUB CI BUILD (user 2026-11-02; IN-PROGRESS, manager, branch `feat/github-ci`):** configure GitHub Actions so the game builds on GitHub where possible: install sjasmplus 1.20.x (pinned release/source build) and build `zx0`/`dzx0` (`tools/setup_zx0.sh`, pinned clone) on the runner; run `tools/build.sh` for release (`-DDEBUG_KIT=0`), kit and `-DF3_GEN=0` builds (0 warnings), then the non-emulator checks (tape_layout, combat_tables, zx0_roundtrip, balance_sim selftest, the FINAL-1 rename grep gate); upload the `.tap`/`.sna`/`.sym` as artifacts. ZEsarUX/ZRCP emulator suites are optional (try a headless ZEsarUX build in CI; if infeasible keep them local and say so). Trigger on push/PR to main; cache toolchain. Needs the user to enable Actions on the renamed repo; manager prepares the workflow file.

**FINAL-3 — ITCH.IO PROJECT SO PEOPLE CAN DOWNLOAD THE GAME (user 2026-11-05; TODO, after FINAL-2):**
- **3a — prepare the project (manager + designer + artist):** page copy (short pitch, story hook, features, controls incl. Kempston/redefine, "how to load" for Fuse / ZEsarUX / real 128K / divMMC, system requirements: ZX Spectrum 128K/+2/+3, credits incl. "WazHack-inspired"), cover image 630×500 (from the L3d loading screen), 3–5 screenshots + an animated GIF captured from ZEsarUX (golden-screen tooling), two 30–60 s gameplay videos (Warrior, Mage; MP4 from ZEsarUX captures, AY audio if feasible — itch embeds a YouTube/Vimeo link, the user uploads them there; user 2026-11-05), genre/tags (roguelike, zx-spectrum, retro, 8-bit), licence/price model, devlog post v1.0. Drafts in `docs/release/itch/`; the user reviews.
- **3b — publish (user + manager):** the user creates the itch.io project (account/login is the user's; agents cannot log in) as Downloadable; uploads `tome-of-the-dead-vX.tap` + `.sna` (+ `SHA256SUMS`) from the GitHub Release of the same tag; visibility draft → user check → public.
- **3c — optional:** play in browser (HTML5 zip with a JS Spectrum emulator embed — licence + 128K/AY support to check) and/or CI upload with `butler` on a `v*` tag (needs an `BUTLER_API_KEY` repo secret from the user).
- **Licence + credits (user 2026-11-05):** code MIT (`LICENSE`), art/music/text CC BY 4.0 (`LICENSE-ASSETS.md`), every third party credited with links (`THIRD-PARTY.md`: ZX0 BSD-3 notice must ship with the game, so the release job attaches all three files; Claude, Google Flow Music (music), tools, the WazHack-inspired credit, trademarks). Credit line "developed agentically"; cover b; Archmage name kept. **The repo goes PUBLIC before the `v1.0` tag** (the page links the source).
- **User decisions 2026-11-05:** FREE (no payments, no donation prompt unless asked later); upload BY HAND (no butler/CI push); NO browser play (3c dropped); this is the first public release → tag `v1.0`.

## Open items

| # | Item | Owner | Note |
|---|------|-------|------|
| B9 | Test harness: ZEsarUX launch/teardown stalls and flaky tape load (#50, W5/W8) under host load; not a game bug | junior | DONE (fix/b9): `tools/test_harness.py` bounded launch (`WZ_LAUNCH_TIMEOUT`, 3 attempts, kill+retry), emulator in own process group killed by atexit/SIGTERM/SIGHUP/SIGINT (no orphans), optional `WZ_SUITE_TIMEOUT` (exit 124 + message); `tests/game.py` #50 tape-load watchdog (60 s, one re-load) |
| B13 / D2 | Decor look and animation rework (user 2026-10-04/05), postponed until the game is mostly done | user + designer + artist | schedule a Design-canvas review session |
| B19b | Two PENDING bodies created overlapping (arrival + follower) can still pop one onto the other's corpse; rare (the B19c fix covered the same-kind follower case) | staff | **CLOSED 2026-11-12** (verified, no code change): corpse_hit is kind-agnostic; `tests/b19b.py` 72 cross-kind runs (arrival resident PENDING in place + follower PENDING at entry, all 72 overlapping), 0 pops / overlaps |
| BSIM1 | DONE 2026-11-12. `tests/balance_sim_selftest.py` `test_monotone` re-based (regen period scaled with max HP; also 6 stale data expectations refreshed: Ogre 36 HP / PHYS neutral, Firebolt R1 1d8+0 range 8, Vampire fire W / cold I) and re-included in the CI Checks loop (~60 s, passes with 4 seeds, `BSIM_SEED` env). The underlying finding stands as a REAL rule interaction (flat regen 1 HP/12 turns + food clock: +30 max HP drops Mage wins 0.41 -> 0.24 via hunger-limited rests); game rule kept, to be revisited in the larger-depths pacing pass (`docs/design/larger_depths.md`) | - | done |
| D8S1 | `tests/d8_stress.py` 2 failures already on main b25e043 (found in the H1 review): 'T teleport mid-fight W/M: re-entry … ST_X 0' — the Archmage's ST_X reads 128 after a mid-fight teleport and re-entry | staff | **done (stale test, no game change)**: ST_X 128 = init bit 7 set, P = H = 0, not blinked: exactly arch_ai's state after the entry turn already ran it (`.i1`); `tests/d8_stress.py` T now accepts `stx in (0, 0x80)`; `--only T` 0 failed |
| ECK1 | `tests/endcard_k.py` 16 failures: **stale scenario, not a game bug.** H1-ARRIVAL (`b98f705`) starts the hero mid-ladder at the arrival-shaft top, so `put()` placed the Ghost in the air and the cast / touch never lined up. Fix: `setup()` does 2 ladder turns (`J`) to stand the hero on storey 0. endcard_k 0 failed; 0 bytes (test only) | junior | done |
| MEM1 | Memory nearly exhausted after STATS2 (SUMMON-SFX 2026-11-05: R6 now 1 B, the rest unchanged): R6 3 B, bank 7 low 2 B, bank 3 7 B (kit 3) after TRAP-OR, b0/text kit 0 B. Any new feature needs a reclaim first (no-cut rule) | staff | open |
| LGZ8 | `tests/levelgen_z80.py --f3`: 43 D8 cases differ between the Z80 generator and `tools/levelgen.py` (237 pass), identical on main b25e043 | junior | fixed (fix/lgz8), test-only: the oracle ran non-f3 (a `-DF3_GEN=1` build puts no `F3_GEN` label in the .sym and `levelgen_z80.py` reset `F3` from it); Z80 and levelgen.py agree, 280/280 |
| B21 | Budget scenario for the deferred level-up + held key path (~115k T, unmeasured) in `tools/budget.py` | junior | – |
| B4 / R1 | Update `prototype.md` §6.4 text: ladder squeeze rule = up to `CLIMB_SQZ_N`=4 waits before the swap (user accepted 2026-10-19) | designer | doc-only |
| D-AI1c | Ladder deadlock rule: lower slot id has right of way, 2-turn swap backstop; 2-bit wait counter in ENT_STAT byte 3, ~80–120 B bank 2 | staff | unscheduled |
| D-AI1d | Milder follow: follow distance 4 -> 6 cells, awake/chasing monsters only; changes fleeing balance | designer + staff | **needs user approval**, unscheduled |
| D-AI1b | Banked-monster position memory — **superseded by ROOM-MEM** (`80519a8`: last two rooms remember monster cells/facing/state) | – | no work left |
| L3 | Level gen: no ladders next to walls (gap of one monster width beside every shaft) | designer -> generator | **ON HOLD** (user 2026-10-27/11-02; `feat/l3-ladder-gap` ca67db4) |
| M1(c) | Trim both fonts (6×8 log, 8×16 menu) to the glyphs used + build-time check that every string char exists (user 2026-10-06); memory lever | staff | open, only if space is needed; no-cut rule: reclaim, not feature cuts |
| SPR-S | Shorter sprites (48->40, 32->24) | artist -> user | LAST-RESORT memory fallback only; never degrade graphics; 48 px kinds only |
| UB1 | Dead-enemy frame on dagger throw (not reproducible) | – | parked; reopen only on a new report |
| B5 | Fuse load of the tape not yet tried (real-hardware load passed, A9) | user | open; low priority |
| WEB1 | Browser play on the itch page with **JSSpeccy 3 v3.2** (GPL-3, unmodified): `tools/web_bundle.sh v1.1` → `build/web/tome-of-the-dead-web-v1.1.zip` (index.html + jsspeccy/ + v1.1 .tap via the 128 loader; GPL text + corresponding source `third_party/jsspeccy3-v3.2-source.tar.gz` inside the zip). How-to: `docs/web_itch.md` | manager | **DONE — LIVE on itch 2026-11-12** (user-approved upload; kind HTML, 660×600, fullscreen button, screenshots column = Sidebar). Known: no Kempston/touch in JSSpeccy |

## How we control state

- This file is authoritative for phase status; the manager updates it on every
  phase transition and records the evidence (which gate passed).
- A phase is only `DONE` when its exit gate is **demonstrated** via build/run/
  test — never on assertion alone.
- Active phase tasks are mirrored into the live task list while in progress.
- Scope changes are decided by the manager + user and reflected here before work
  starts; agents build to the plan, not around it.

## Risk register

| Risk | Mitigation |
|------|------------|
| Z80/byte budget overrun (banks 2/3/7, R6 nearly full) | Reviewer tracks cycle/byte cost; `memory-map.md` gates allocation; no-cut rule: solve by reclaim |
| Tick budget (worst tick vs the 2-frame cap) | Gated `budget.py` scenarios; re-measure before any per-tick feature |
| Attribute clash on art | Pipeline enforces <= 2 colours/cell + round-trip |
| Flaky ZEsarUX harness hides regressions (B9) | Per-launch timeouts/retry; treat a stall as infra, rerun alone before concluding |
| Scope creep | Hard in/out list; manager guards it; new items need user approval |
| Release readiness (CI, tape load on real hardware, itch.io page) | FINAL-2/FINAL-3; real-hardware load already verified (A9) |

Retired risks (side-view feasibility, asset pipeline, colour under motion, ZRCP flag
names): `docs/history.md`.
