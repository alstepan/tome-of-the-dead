# Delivery plan — WazHack/ZX

> Manager-owned control document and single source of truth for project state.
> Updated by the main thread (manager) as phases progress. Every phase has a
> **verifiable exit gate** — state is proven by build/run/test, not by opinion.
>
> Goal of this milestone track: a **playable vertical slice** on ZX Spectrum 128K.

## Status legend

`TODO` · `IN-PROGRESS` · `BLOCKED(reason)` · `DONE`

## Current state

- **Active phase:** P1 — Game design (pending launch of `game-designer`)
- **Last completed:** P0 — Project setup
- **Top risk:** rendering choice (P1) reorders all engine work; everything
  downstream of P1 is provisional until that doc lands.

---

## Phases

### P0 — Project setup · `DONE`
- **Owner:** manager
- **Goal:** repo skeleton, skills, agents, docs, conventions.
- **Exit gate:** `.claude/` skills+agents present; `docs/conventions.md` &
  `docs/memory-map.md` exist; git initialised. ✅

### P1 — Game design · `TODO`
- **Owner:** `game-designer` · **Depends:** P0
- **Goal:** define the Spectrum reinterpretation.
- **Exit gate:** `docs/design/spectrum-design.md` exists and is approved by the
  user, containing: **rendering approach (decided)**, vertical-slice scope
  (in/out list), keyboard controls, turn/entity model with field-level data
  shapes, combat + deterministic RNG model, and a playability checklist.
- **Unblocks:** the detailed engine sequencing in P3/P4.

### P2 — Engine skeleton & toolchain proof · `TODO`
- **Owner:** `z80-staff-engineer` · **Depends:** P1 (boot/loader is design-light;
  can start in parallel once P1 is approved)
- **Goal:** prove the pipeline end-to-end and lay the program skeleton.
- **Exit gate:** a smoke-test `build/wazhack.tap` boots on **both** Fuse (`run`)
  and ZEsarUX, **`debug` confirms ZRCP connectivity** (regs/memory readable),
  and the `test` skill captures its first golden. `docs/memory-map.md` seeded
  with the real program/origin layout.

### P3 — Core loop (input → turn → render) · `TODO`
- **Owner:** `z80-staff-engineer` (+ `graphics-artist` for placeholder tiles)
- **Depends:** P1, P2
- **Goal:** the heartbeat — read input, advance a turn, render the frame, per the
  chosen rendering approach.
- **Exit gate:** player moves around a static map, rendered correctly; turn
  counter advances; golden-screen + state assertions green via `test`.

### P4 — Vertical slice content · `TODO`
- **Owner:** `z80-staff-engineer` (+ `game-designer` for balance)
- **Depends:** P3
- **Goal:** one dungeon level (generation), melee combat, a handful of monsters
  and items, descend stairs, death.
- **Exit gate:** the P1 **playability checklist** passes end-to-end (player can
  reach the stairs, a monster can kill the player, no softlock); test scenarios
  green; deterministic seed reproduces runs.

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
| Rendering choice reshapes engine | P1 | Decide it explicitly in P1 before P3; keep P2 design-light |
| ZRCP flag names differ in this build | P2 | Validate on first `debug` run; fix the skill |
| Attribute clash on real art | P5 | Pipeline enforces ≤2 colours/cell + round-trip |
| Z80/byte budget overrun | P3+ | Reviewer tracks cycle/byte cost; memory-map gates allocation |
| Scope creep beyond a slice | all | Hard in/out list in P1; manager guards it |
