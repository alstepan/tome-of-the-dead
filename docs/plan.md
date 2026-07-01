# Delivery plan — WazHack/ZX

> Manager-owned control document and single source of truth for project state.
> Updated by the main thread (manager) as phases progress. Every phase has a
> **verifiable exit gate** — state is proven by build/run/test, not by opinion.
>
> Goal of this milestone track: a **playable vertical slice** on ZX Spectrum 128K.

## Status legend

`TODO` · `IN-PROGRESS` · `BLOCKED(reason)` · `DONE`

## Current state

- **Active phase:** SPIKE-3 — smoothness lever (prove sub-frame scroll before the
  side-view commit; decided with user 2026-07-01: "one more smoothness lever first")
- **Commit decision (2026-07-01, user):** side-view feasibility is accepted, but
  before folding it forward as the Slice 1 renderer and building P4 on it, prove
  **one sub-frame smoothness lever** so movement is demonstrably smooth, not merely
  hitch-tolerable (the SPIKE-2 burst is ~2 frames/step). Candidate levers: shift
  only the ~12 non-sky content rows (~1.3 frames); amortized incremental scroll
  (spread the shift across the 4 inter-scroll frames / pixel-scroll 2px/frame);
  shadow-screen double-buffer. Pick one, prove it, then commit.
- **Last completed:** P3 — Core loop (verified 2026-06-28; z80-reviewer verdict
  fix-then-ship, all gating fixes applied; evidence in the P3 section)
- **Plan reorder (2026-06-28, manager+user):** the original plan retired the
  least-risky work first (top-down game logic on a clash-free grid) and the
  **most-risky, most-defining** feature last (the side-view sprite renderer — the
  actual WazHack look, where graphics carry the gameplay). We are **pulling a
  side-view feasibility SPIKE forward, before P4 content**, to retire that #1 risk
  early. P2/P3 are renderer-agnostic (turn loop, input, RNG, test harness) and are
  kept. After the spike's evidence we re-decide: continue side-view as the Slice 1
  renderer (fold M2 forward) or revert to the staged top-down-first order. **P4 is
  paused** pending the spike outcome.
- **Spike scope decisions (2026-06-28, user):**
  - **Prove colour too** — the spike must manage **attribute clash under a moving
    sprite** (not just monochrome). The hardest, most WazHack-like part; it changes
    the renderer's clash strategy and the sprite data contract.
  - **Asset pipeline is a co-equal risk** and a spike deliverable: build a working
    converter (`tools/gfx_convert.py`) + a quality-assessment tool
    (`tools/gfx_assess.py`), and produce the spike sprite **through** them.
  - **Autonomous generation via Ollama** (`x/z-image-turbo` primary, `x/flux2-klein`
    fallback — general diffusion, concept only; never ship raster). No vision model
    installed → assessment uses objective metrics (silhouette IoU, SSIM, clash,
    render-back) unless a multimodal model is pulled later.
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

### SPIKE — Side-view feasibility spike · `IN-PROGRESS`
- **Owner:** `game-designer` (rendering approach) → `graphics-artist` (one real
  masked sprite + background) + `z80-staff-engineer` (renderer) → `z80-reviewer`
  (perf/feasibility verdict) · **Depends:** P3 (turn loop, input, test harness)
- **Goal:** prove — with running, measured evidence — that a **WazHack-style
  side-view** is buildable on the 128K: a recognizable **masked, moving character
  sprite** over a background at arbitrary pixel position, with **attribute clash
  managed to an acceptable look**, a **horizontally scrolling viewport**, driven
  by the existing turn/input loop, **within a sane per-frame budget**.
- **Deliberately throwaway-tolerant:** this is a risk-retirement prototype, not
  slice content. It may live in a separate source path and need not pass the P1
  playability checklist. Reuse P2/P3 plumbing (input, RNG, ZRCP harness).
- **Exit gate (decision-quality evidence):**
  0. **Asset pipeline proven:** `tools/gfx_convert.py` (image/text → clash-checked,
     masked Z80 DEFB + round-trip) and `tools/gfx_assess.py` (silhouette IoU, SSIM,
     clash, render-back PNG+ASCII; optional vision-model score) exist and produced
     the spike sprite via **autonomous Ollama** generation. Committed artifact =
     validated data + its text source, never raw AI raster.
  1. `game-designer` produces a **side-view rendering design** (sprite size +
     format incl. mask & pre-shift strategy, the **colour attribute-clash strategy
     for a MOVING sprite**, the **scroll model**, pixel-coordinate entity model)
     under `docs/design/`.
  2. A build renders the player sprite side-on **in colour** over a background; the
     player moves left/right via the existing input and the **viewport scrolls**;
     redraw leaves **no trails/stale pixels** (mask correct) and **every cell stays
     clash-legal (≤2 colours) as the sprite moves** (validated via screen-memory).
  3. **Measured cost:** the per-frame/redraw T-state (or frame) cost is recorded
     by `z80-reviewer` with a verdict on whether smooth side-view is feasible at
     the intended entity counts; ZRCP/golden assertions green for the spike scene.
  4. Manager + user **re-decide** Slice 1 direction from this evidence and update
     this plan.
- **RESULT / evidence (2026-06-29):** spike built clean, isolated in
  `src/spike_sideview.asm` (does not touch P2/P3); `tests/sideview.py` **14/14**
  green; P2/P3 still green. `z80-reviewer` recomputed all costs from the listing
  (independently confirmed, slightly more pessimistic):
  - **Coloured side-view IS feasible.** A masked 16×24 sprite composites in colour
    at arbitrary pixel-X over a scrolling coloured background, clash-managed every
    frame, **no pixel/colour trails, all cells ≤2 colours**. The defining hard case
    (colour under motion) is **retired**. **Attribute-follow is nearly free**
    (~1.2k T, <2% frame) — colour does not move the feasibility needle.
  - **Pipeline risk retired** (converter+assess deterministic, clash-legal sprite).
  - **Cost (uncontended):** per-sprite motion frame ~13.5k T (~19%); the **erase-
    under (~6.5k T) is the per-sprite bottleneck**, not the blit. **Naive ceiling
    ≈ 5 simultaneous sprites** (~4 contended), not 8–12.
  - **Scroll is the real monster:** a naive 8px scroll step ≈ **537k T ≈ 7.6
    frames** → continuous walking would be a slideshow. The spike **retired the
    sprite/clash/colour risk but only BOUNDED the scroll risk** (didn't retire it).
  - **M2 must-haves (ranked):** (1) byte-shift scroll + draw only the newly-exposed
    column [biggest win, still unproven at budget]; (2) save/restore-under instead
    of redraw-under [lifts sprite ceiling ~5→~8–10]; (3) shadow-screen double-buffer
    [kills the recorded single-buffer flicker]; (4) 16×16 sprite fallback; (5)
    per-entity cached screen col.
  - **Scope-honesty caveats:** "coloured side-view proven" = **for single-paper
    bands with band-matched features**; a feature-with-distinct-attribute vs sprite
    three-way clash cell is **untested**, and sprite-over-pillar colour-follow is
    asserted by construction, not by test — both are M2 questions.
  - **Verdict:** fix-then-ship (spike is decision-quality as-is; "fixes" are M2
    scope). Side-view risk #1 retired; **scroll risk remains the open gate.**

### SPIKE-2 — Byte-shift scroll proof · `IN-PROGRESS`
- **Owner:** `z80-staff-engineer` → `z80-reviewer` · **Depends:** SPIKE
- **Decision (2026-06-29, user):** side-view is committed *pending* this — prove
  the one remaining unretired risk (scroll) before folding side-view forward.
- **Goal:** replace the naive 768-cell scroll redraw (~537k T ≈ 7.6 frames) with
  a **byte-shift horizontal scroll** — shift the visible playfield bitmap +
  attributes by one char column and redraw **only the newly-exposed column** from
  the world buffer — and **measure** whether it fits an acceptable budget.
- **Exit gate:** byte-shift scroll implemented in the spike (reuse the existing
  scene for an apples-to-apples comparison), scroll legality/no-tear assertions
  green via ZRCP, and `z80-reviewer` records the **real per-scroll-step T cost**
  vs the naive 537k baseline with a verdict: does smooth-enough side-view scroll
  fit the frame budget (≤1 frame ideal; if N frames, is that acceptable for the
  movement model)? Then manager+user **commit**: fold side-view forward or adjust.

- **RESULT / evidence (2026-06-30):** byte-shift scroll built in the spike (east
  **and** west), `tests/scroll.py` **12/12** (reconstructs the expected `WORLD_BUF`
  window and byte-compares screen memory → proves no tear/dropped/doubled/stale
  column, no trail, bands intact); sideview 14/14, P2/P3 green; builds clean.
  Manager validated the cost from `build/spike.lst` (reviewer agent hit session
  limit; recompute done in-thread):
  - **Per 8px scroll step ≈ 146k T ≈ 2.06 frames** (uncontended); ~2.7–3.0 frames
    contended. Dominant term = 192 scanlines × 31 unrolled `LDI` (~95k T floor) +
    overhead ≈ 106–110k for the bitmap shift; +13.8k attr shift + 17.5k/4.8k for
    the one newly-exposed column. **3.67× cheaper than the naive 537k baseline.**
  - **PROVEN:** byte-shift scroll works, correct, no tear, ~2-frame burst per step.
  - **ASSUMED (M2, not proven here):** that it amortizes under one frame — the
    spike does it as a burst, not incrementally. Levers (each plausible, unbuilt):
    shift only the 12 content rows (sky is blank) → ~1.3 frames; spread the shift
    across the 4 inter-scroll frames; shadow-screen double-buffer.
  - **Read:** a periodic ~2-frame (~40–60 ms) hitch per scroll step is acceptable
    for stepped roguelike movement; true sub-frame smoothness is normal M2 work,
    not a feasibility unknown. **Scroll risk retired to an acceptable level.**

### P4 — Vertical slice content · `BLOCKED(awaiting side-view commit decision)`
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
| Side-view rendering cost/feasibility (clash, masked pre-shifted sprites, scroll, banking) | SPIKE | **#1 risk + the product's identity.** Reordered (2026-06-28) to retire it **early** via a feasibility SPIKE on the proven turn loop, instead of deferring to M2 after the whole top-down slice. Direction re-decided from measured evidence. |
| Asset-production pipeline (no GUI in agentic dev; AI raster→16×24 1-bit/clash; masks) | SPIKE | Co-equal risk (user-flagged 2026-06-28). Retired in the spike: build `tools/gfx_convert.py` + `tools/gfx_assess.py`, produce the spike sprite through them via **autonomous Ollama** gen + objective quality gate (silhouette IoU/SSIM/clash/render-back). |
| Colour under motion (attribute clash with a moving sprite) | SPIKE | User chose to **prove colour** in the spike rather than defer. Renderer must keep cells clash-legal as the sprite moves; this is the crux the game-designer's colour-revised design must solve. |
| ZRCP flag names differ in this build | P2 | Validate on first `debug` run; fix the skill |
| Attribute clash on real art | P5 | Pipeline enforces ≤2 colours/cell + round-trip |
| Z80/byte budget overrun | P3+ | Reviewer tracks cycle/byte cost; memory-map gates allocation |
| Scope creep beyond a slice | all | Hard in/out list in P1; manager guards it |
