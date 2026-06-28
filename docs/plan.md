# Delivery plan — WazHack/ZX

> Manager-owned control document and single source of truth for project state.
> Updated by the main thread (manager) as phases progress. Every phase has a
> **verifiable exit gate** — state is proven by build/run/test, not by opinion.
>
> Goal of this milestone track: a **playable vertical slice** on ZX Spectrum 128K.

## Status legend

`TODO` · `IN-PROGRESS` · `BLOCKED(reason)` · `DONE`

## Current state

- **Active phase:** P4 — Vertical slice content
- **Last completed:** P3 — Core loop (verified 2026-06-28; z80-reviewer verdict
  fix-then-ship, all gating fixes applied; evidence in the P3 section)
- **Decision (2026-06-26, manager+user):** movement uses a **4-key layout**
  (`hjkl` + `QAOP`, no `yubn`), with **diagonals via two-key chords** — pressing
  two orthogonal keys together moves diagonally, so all 8 directions are reachable
  from 4 keys. Input sums held-key contributions into `(dx,dy)`. Revises the
  design's original 8-key assumption; design §3/§5.3/§8.7 updated; AI stays
  4-connected (monsters orthogonal), player may step diagonally.
- **Milestone strategy (decided 2026-06-26):** the eventual target look is
  **side-view bitmap sprites (WazHack feel)**, but we **stage** it.
  **Slice 1 = top-down char-cell** — proves turn loop, combat, RNG, level gen,
  items, and the test harness fast and clash-free. **Milestone 2 = side-view
  renderer** built on top of the proven game logic. Phases P1–P6 below are the
  Slice 1 (top-down) track; **M2** is appended after them.
- **Top risk (mitigated by staging):** side-view rendering is expensive (runtime
  clash management, pre-shifted masked sprites, banked assets, pixel-coord
  entities). Staging defers that risk to M2 and keeps Slice 1 small.

---

## Phases

### P0 — Project setup · `DONE`
- **Owner:** manager
- **Goal:** repo skeleton, skills, agents, docs, conventions.
- **Exit gate:** `.claude/` skills+agents present; `docs/conventions.md` &
  `docs/memory-map.md` exist; git initialised. ✅

### P1 — Game design · `DONE`
- **Owner:** `game-designer` · **Depends:** P0
- **Goal:** define the Spectrum reinterpretation.
- **Exit gate:** `docs/design/spectrum-design.md` exists and is approved by the
  user, containing: **rendering approach (decided)**, vertical-slice scope
  (in/out list), keyboard controls, turn/entity model with field-level data
  shapes, combat + deterministic RNG model, and a playability checklist.
- **Unblocks:** the detailed engine sequencing in P3/P4.

### P2 — Engine skeleton & toolchain proof · `DONE`
- **Owner:** `z80-staff-engineer` · **Depends:** P1 (boot/loader is design-light;
  can start in parallel once P1 is approved)
- **Goal:** prove the pipeline end-to-end and lay the program skeleton.
- **Exit gate:** a smoke-test `build/wazhack.tap` boots on **both** Fuse (`run`)
  and ZEsarUX, **`debug` confirms ZRCP connectivity** (regs/memory readable),
  and the `test` skill captures its first golden. `docs/memory-map.md` seeded
  with the real program/origin layout.
- **Evidence (verified by manager 2026-06-26):**
  - Build clean (0 warnings). ZEsarUX 12.1 launches headless with ZRCP;
    `get-registers`/`read-memory`/`write-memory` all work (`write-memory` needs
    **decimal** addr+value — recorded in the harness). Top P2 risk ("ZRCP flag
    names differ") **retired**.
  - Smoke frame is deterministic and ROM-independent: own glyph blitter draws
    "WAZHACK" (verified by decoding `$4000` from screen RAM), attributes flooded
    to `$47`, boot state `GAME_STATE=$01` / `RNG_STATE=$A55A`, CPU in halt loop.
  - First golden committed: `tests/golden/smoke.hash`
    (`8e0ba62a…d54c4e6`); `tests/smoke.py` via `tools/test_harness.py` asserts
    state + golden, exits non-zero on mismatch. Re-run green.
  - `docs/memory-map.md` seeded (program origin, screen regions, working storage,
    stable test-observable addresses, SP/state-block constraint).
  - **Caveat:** ZEsarUX (the testable path) is fully green; Fuse on macOS is
    GUI-only and not headlessly verifiable — the `.tap` autoloader is built and
    valid, Fuse boot is a manual `run` confirmation.
  - **Reusable for P3:** `draw_cell` (blit one 8×8 glyph to char cell (col,row),
    no per-row address recompute) is the dirty-cell render primitive P3 builds on.

### P3 — Core loop (input → turn → render) · `DONE`
- **Owner:** `z80-staff-engineer` (+ `graphics-artist` for placeholder tiles)
- **Depends:** P1, P2
- **Goal:** the heartbeat — read input, advance a turn, render the frame, per the
  chosen rendering approach.
- **Exit gate:** player moves around a static map, rendered correctly; turn
  counter advances; golden-screen + state assertions green via `test`.
- **Evidence (verified by manager 2026-06-28):**
  - Build clean (0 warnings). `tests/smoke.py` green; `tests/p3.py` **31/31**
    green and repeatable. Asserts: boot state, move-E (§6.4), one-keypress-one-turn
    (§6.6), dirty-cell subset (§6.18), **diagonal chord K+L → (+1,−1)**, wall-block
    no-move/no-turn (§6.5), WAIT, opposite-key-cancel no-turn, cross-turn debounce
    / no-auto-repeat.
  - `z80-reviewer` verdict **fix-then-ship**, no runtime bugs. Gating fixes done:
    memory-map synced to real addresses/size (code+data `$8000..$84CC`, 1228 B);
    two missing input-invariant tests committed; redundant `push/pop bc` removed.
    `IY=$5C3A` invariant documented in `docs/conventions.md`.
  - Built: 4-key chordable input (`hjkl`+`QAOP`, diagonals via two-key chords),
    static 30×21 map, dirty-cell renderer on `draw_cell`, 16-slot entity array
    (`$B000`, laid out for P4), turn loop. Stable addrs: `GAME_STATE/RNG_STATE/`
    `TURN_COUNTER`, `PLAYER_X/Y`, `KBD_MATRIX/INPUT_SRC` (test injection).
- **Carried into P4 (manager note):** diagonal **corner-cutting is permitted**
  (diagonal legal iff destination walkable; no corner-block). Accepted for the
  slice; P4 must make a conscious call given monsters become 4-connected and
  combat is adjacency-based — keep it, or add corner-blocking with documented cost.

### P4 — Vertical slice content · `IN-PROGRESS`
- **Owner:** `z80-staff-engineer` (+ `game-designer` for balance)
- **Depends:** P3
- **Goal:** procedurally generated levels, melee combat, a handful of monsters
  and items, **descend stairs generates the next level (≥2 levels)**, death.
- **Exit gate:** the P1 **playability checklist** passes end-to-end (player can
  reach the stairs, **descend generates a fresh, reachable level 2**, a monster
  can kill the player, no softlock); test scenarios green; deterministic seed
  reproduces runs.

### P5 — Graphics pass · `TODO`
- **Owner:** `graphics-artist` · **Depends:** P3 (slots), P4 (asset list)
- **Goal:** replace placeholders with real clash-legal tiles/sprites via the
  `gfx-convert` pipeline.
- **Exit gate:** all slice assets clash-validated and round-trip-verified,
  integrated; goldens updated with a reviewed reason.

### P6 — Slice hardening & review · `TODO`
- **Owner:** `z80-reviewer` → manager · **Depends:** P4, P5
- **Goal:** correctness/perf/regression hardening of the whole slice.
- **Exit gate:** `z80-reviewer` verdict = ship; full regression suite green;
  `docs/memory-map.md` matches code. **→ Vertical slice milestone reached.**

### P7 — Sound · `BLOCKED(needs music format + Z80 player; defer until post-P3)`
- **Owner:** `sound-composer` · **Depends:** engine loop (P3) + chosen format
- **Goal:** AY-3-8912 music + beeper FX.
- **Exit gate:** player routine integrated (T-state cost documented); cues play
  without stalling the turn loop.

### M2 — Side-view renderer (target look) · `TODO`
- **Owner:** `z80-staff-engineer` + `graphics-artist` · **Depends:** P6 (proven
  game logic)
- **Goal:** replace the top-down renderer with the WazHack-style side-view —
  pixel-coordinate entities, scrolling viewport, pre-shifted masked sprites,
  runtime attribute-clash management, banked sprite assets. Game logic (turn
  loop, combat, RNG, level gen, items) is reused; the renderer + entity-coord
  model + level structure are rebuilt.
- **Exit gate:** the playability checklist passes with the side-view renderer;
  clash managed (no illegal cells); turn redraw within frame budget. This is
  where the bulk of the graphics + clash engineering lands.

---

## How we control state

- This file is authoritative for phase status; the manager updates it on every
  phase transition and records the evidence (which gate passed).
- A phase is only `DONE` when its exit gate is **demonstrated** via build/run/
  test — never on assertion alone.
- Active phase tasks are mirrored into the live task list while in progress.
- Scope changes are decided by the manager + user and reflected here before work
  starts; agents build to the plan, not around it.

## Risk register

| Risk | Phase | Mitigation |
|------|-------|------------|
| Side-view rendering cost (clash, sprites, banking) | M2 | Target = side-view, but **staged**: Slice 1 is top-down; side-view deferred to M2 on proven logic |
| ZRCP flag names differ in this build | P2 | Validate on first `debug` run; fix the skill |
| Attribute clash on real art | P5 | Pipeline enforces ≤2 colours/cell + round-trip |
| Z80/byte budget overrun | P3+ | Reviewer tracks cycle/byte cost; memory-map gates allocation |
| Scope creep beyond a slice | all | Hard in/out list in P1; manager guards it |
