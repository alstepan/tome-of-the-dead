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
| FINAL-2 GitHub CI | IN-PROGRESS | manager, branch `feat/github-ci` |
| FINAL-3 itch.io release | TODO | after FINAL-2 |

## Active / next

**FINAL-2 — GITHUB CI BUILD (user 2026-11-02; IN-PROGRESS, manager, branch `feat/github-ci`):** configure GitHub Actions so the game builds on GitHub where possible: install sjasmplus 1.20.x (pinned release/source build) and build `zx0`/`dzx0` (`tools/setup_zx0.sh`, pinned clone) on the runner; run `tools/build.sh` for release (`-DDEBUG_KIT=0`), kit and `-DF3_GEN=0` builds (0 warnings), then the non-emulator checks (tape_layout, combat_tables, zx0_roundtrip, balance_sim selftest, the FINAL-1 rename grep gate); upload the `.tap`/`.sna`/`.sym` as artifacts. ZEsarUX/ZRCP emulator suites are optional (try a headless ZEsarUX build in CI; if infeasible keep them local and say so). Trigger on push/PR to main; cache toolchain. Needs the user to enable Actions on the renamed repo; manager prepares the workflow file.

**FINAL-3 — PUBLISH ON ITCH.IO (user 2026-11-05; TODO, after FINAL-2):** publish the game on itch.io. Details to agree with the user first: the page, `.tap`/`.sna` downloads, screenshots, description, and an in-browser emulator embed option.

## Open items

| # | Item | Owner | Note |
|---|------|-------|------|
| H1 | Vertical room transition: the hero should visibly climb to the top before the scroll up and appear at the top of the ladder after the scroll down (user 2026-10-05) | staff | costed 2026-11-05 (architect): 0 RAM / frames / pool; bank 7 low ~20–28 B (18 free → ~10 B reclaim, e.g. move arrival override to `lp_transition` in bank 3) + bank 2 ~5 B `cork_check` y=0 bound; tick +<0.3k T. **User rulings 2026-11-05:** (1) the extra climb steps cost turns (normal ladder turns, monsters act, hunger ticks); (2) after arrival the hero waits mid-ladder for the player's keys; (3) symmetric: going DOWN the hero climbs to the ladder bottom before the scroll and appears at the ladder top; going UP he climbs to the top and appears at the ladder bottom. Cost to be re-measured with (3). |
| B9 | Test harness: ZEsarUX launch/teardown stalls and flaky tape load (#50, W5/W8) under host load; not a game bug | junior | per-launch timeouts + kill/retry in `tools/test_harness.py` |
| B13 / D2 | Decor look and animation rework (user 2026-10-04/05), postponed until the game is mostly done | user + designer + artist | schedule a Design-canvas review session |
| B19b | Two PENDING bodies created overlapping (arrival + follower) can still pop one onto the other's corpse; rare (the B19c fix covered the same-kind follower case) | staff | verify whether B19c closed it; else keep |
| BSIM1 | `tests/balance_sim_selftest.py` `test_monotone` FAILS on main (2026-11-05): Mage win rate 0.378 / 0.386 / **0.242** at HP +0/+10/+30; Warrior depth 6.89 / 7.24 / 7.05. Either a sim artefact (stall/turn cap) or a real rule interaction — not a stale threshold | junior → designer | excluded from the CI gate until fixed |
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
