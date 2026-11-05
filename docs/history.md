# Project history — Tome of the Dead

> Archived from `docs/plan.md` on 2026-10-01 when the PROTO became the baseline
> game. Decision log and evidence for P0–P3, SPIKE-1..4, and PROTO. Read-only;
> agents do not need this for current work.


- **PROTO — first playable fighting prototype (user 2026-09-24) · IN-PROGRESS.**
  Uses the user's claude.ai Design canvas "Tome of the Dead Spectrum Sprites"
  (https://claude.ai/artifact/U71G9dWUWzZBVxmJUrevD3, vendored at
  `assets/gfx/source/tome-of-the-dead_sprites.dc.html`) as the art source of truth.
  Decisions: cast = the sheet's (heroes **Knight/Wizard/Rogue** 24×48; monsters
  Skeleton, Goblin, Ghost, Rat, Bat, Slime) — **supersedes Wizard/Witch + cat**
  (R3); "move in all directions" = **rooms + ladders/stairs** (walk L/R, climb
  U/D, vertical Cauldron transitions). Converter: build our own
  (`tools/svg_sprites.py` → `gfx_convert.py`). Gate: heroes and enemies visibly
  move in all four directions and fight (attack anims, HP, death), ZRCP-tested.
  Spec review answers (user 2026-09-24): accepted 3 storeys + HUD, 25 Hz/4 px,
  turn-based w/ key repeat, flyers storey-bound, instant zap, visual-only block;
  CHANGED: **keep coloured floor bands** (ladder holes solved by cell-snapped
  climbing), **monsters follow between rooms** (persistent state), **potions**
  added; **all 32 missing frames + tiles** to be drawn and reviewed on the canvas
  as "Draft 3" before import.
  Progress 2026-09-24: spec rev B done; 32 missing frames + tiles drawn and
  published to the canvas as artboard "Draft 3" (awaiting user review; imported
  meanwhile from `assets/gfx/source/draft3_frames.html`); `src/proto*.asm` built
  (all 3 stages, worst tick 139.2k/141.8k T per engineer). **Manager gate NOT
  passed:** builds clean + legacy suites green, but full `tests/proto.py` = 108/118
  in 3h53m (the same items pass in isolation, 46/46) → suspected order-dependent/
  racy harness; z80-reviewer diagnosing + reviewing.
  **Update 2026-09-25 — manager gate PASSED:** root cause = racy snapshot reload in
  `tests/proto_lib.py` (silently continued from the previous scenario's state under
  host load; also a reviewer rebuild overwrote proto.sna mid-run). Harness now
  reloads inside cpu-step, verifies all 128K RAM vs the .sna, loads a private copy,
  30 s command timeout, headless 2× speed. 3-slice static review (fix-then-ship):
  2 🔴 fixed (mid-ladder yield let a monster leave the ladder and climb through
  floor; overlap repair skipped attr-dirty sprites), plus paging-lock check, alloc
  $10000 wrap, damage-list overflow, zap over sprites, ladder bodies block reach,
  yield fallback, potion edge cases, new-game reset. Manager run: builds 0 warn;
  proto 157/157 (~80 s); smoke/p3/sideview/scroll green.
  **Update 2026-09-25 (later):** user playtest found (a) the tape path fell into
  `check_paging` after loading → Fuse reset (fixed in progress + tape E2E test),
  (b) the hero-select screen shows the wrong sprites after a game ends. **User
  decision: renderer optimisation DISCARDED for now**; after these bugs are fixed,
  the manager + user review the plan and game concepts before any new work.
  **Fixed + manager-gated 2026-09-25:** tape path (`ASSERT start_loaded == boot`
  + fall-through guards, tape E2E test #50) and select-screen sprites
  (`sel_frt_copy` restores the select idles' FRT rows; #51 covers a second game
  with a different hero). Optimisation reverted. Manager run: builds 0 warn,
  proto 179/179, legacy green; tape sha256 `6fa4629d…`. **PROTO playable; next =
  plan/concept review with the user.**
  **Open:** (1) heavy fight (hero + 2 skeletons + goblin + ghost) measures
  154,852 T = 109% of the 2-frame tick on the turn-start tick → user decision;
  (2) Draft 3 art review on the canvas; (3) spec §6.4 text for the new ladder
  rules (designer); (4) Fuse / real-hardware load not yet tried; (5) single-buffer
  flicker unmitigated.
  Steps: (1) game-designer → `docs/design/prototype.md`; (1‖) graphics-artist →
  SVG importer + masked asm + ladder tiles + pipeline docs; (2) z80-staff-engineer
  → `src/proto.asm`; (3) z80-reviewer; (4) manager gate (build + test).
- **Scroll model re-scoped (user decision 2026-07-03) — Cauldron-style room
  transitions.** SPIKE-4's double-buffer continuous scroll is **DONE and works
  (tests 12/12)** but the continuous 8px-every-4-frames scroll read as a slow
  lurch. Decision: **drop continuous scrolling during play.** Normal gameplay is
  **static** (dirty-sprite redraw only, no per-frame shift); the screen scrolls
  **once, whole-screen, only on a room-boundary crossing** with gameplay frozen
  (Cauldron, 1985). The dungeon becomes **room-based** (discrete rooms joined at
  edges), not an open continuous floor. Side-view is **committed** as the Slice 1
  renderer. Full spec: `docs/design/spectrum-design.md` §R1/R2; the spike's
  continuous-scroll model (`sideview-renderer.md` §3) is marked superseded.
- **Hero selection added (user 2026-07-03):** player picks **Wizard or Witch** at
  start (cosmetic in Slice 1), each with a **cat companion** (following ally).
  Artist contract: `docs/design/heroes.md`.
- **Next:** sprite work (wizard/witch idle 16×24 + cat idle 16×16, per
  `heroes.md`) and the **room-transition scroll engine** (reuse the SPIKE-2/3/4
  byte-shift primitive for the frozen whole-screen pan; double-buffer no longer
  required since we never scroll during interactive frames). Then unblock P4
  content on the room-based world model.
- **Superseded active phase:** SPIKE-4 — shadow-screen double-buffer · DONE
  (12/12; the double-buffer machinery is retained in the spike but is **not**
  needed by the shipped Cauldron scroll — kept for reference only). Was IN-PROGRESS
  under user 2026-07-01 "build double-buffer first"; the 2026-07-03 re-scope makes
  continuous-scroll smoothness moot. SPIKE-3 (content-rows lever) DONE (`71d2b1c`).
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
  actual WazHack-inspired look, where graphics carry the gameplay). We are **pulling a
  side-view feasibility SPIKE forward, before P4 content**, to retire that #1 risk
  early. P2/P3 are renderer-agnostic (turn loop, input, RNG, test harness) and are
  kept. After the spike's evidence we re-decide: continue side-view as the Slice 1
  renderer (fold M2 forward) or revert to the staged top-down-first order. **P4 is
  paused** pending the spike outcome.
- **Spike scope decisions (2026-06-28, user):**
  - **Prove colour too** — the spike must manage **attribute clash under a moving
    sprite** (not just monochrome). The hardest, most WazHack-inspired part; it changes
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
  **side-view bitmap sprites (WazHack-inspired feel)**, but we **stage** it.
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
- **Exit gate:** a smoke-test `build/tome-of-the-dead.tap` boots on **both** Fuse (`run`)
  and ZEsarUX, **`debug` confirms ZRCP connectivity** (regs/memory readable),
  and the `test` skill captures its first golden. `docs/memory-map.md` seeded
  with the real program/origin layout.
- **Evidence (verified by manager 2026-06-26):**
  - Build clean (0 warnings). ZEsarUX 12.1 launches headless with ZRCP;
    `get-registers`/`read-memory`/`write-memory` all work (`write-memory` needs
    **decimal** addr+value — recorded in the harness). Top P2 risk ("ZRCP flag
    names differ") **retired**.
  - Smoke frame is deterministic and ROM-independent: own glyph blitter draws
    "TOME OF THE DEAD" (verified by decoding `$4000` from screen RAM), attributes flooded
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
- **Goal:** prove — with running, measured evidence — that a **WazHack-inspired
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

### SPIKE-2 — Byte-shift scroll proof · `DONE`
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

### SPIKE-3 — Scroll smoothness lever · `DONE`
- **Owner:** `z80-staff-engineer` → `z80-reviewer` · **Depends:** SPIKE-2
- **Decision (2026-07-01, user):** before folding side-view forward, prove **one**
  sub-frame smoothness lever so motion is *demonstrably smooth*, not merely
  hitch-tolerable.
- **Framing (manager, grounded in the spike code):** two of the three smoothness
  properties are **already present** in the spike and just need to be recognised
  as such — (1) the sprite already glides at **2px/frame** (`MOVE_STEP=2`), and
  (2) the viewport only scrolls at the dead-zone margin, so during sustained
  edge-walking the expensive scroll fires only **1 frame in 4** (sprite crosses a
  byte boundary every 4×2px). Inter-scroll motion is therefore already smooth.
  The **only** residual hitch is the cost of that 1-in-4 scroll *frame*: the
  full-height byte-shift (~146k T ≈ 2 frames). SPIKE-3 attacks exactly that.
- **Lever chosen = content-rows-only shift.** Rows 0–11 are blank sky; shift only
  the 12 content rows (rows 12–23 = 96 scanlines) in `shift_bitmap_left/right`
  (and, if it helps, skip the sky in `shift_attr_*`). Predicted ~55k bitmap →
  **~91k T total ≈ 1.28 frames** for the scroll frame (code comment, lines
  288–300). Guard it behind a compile-time flag (`SHIFT_CONTENT_ROWS_ONLY`,
  default 1) for A/B measurement against the SPIKE-2 full-height path.
- **Exit gate:**
  1. Content-rows-only shift implemented, **`tests/scroll.py` + `tests/sideview.py`
     still green** (no tear/clash/trail — correctness must not regress; the scene's
     content is confined to rows 12–23 so a content-rows shift must be byte-exact).
  2. Manager records the **measured worst-case frame under sustained edge-walking**
     from `build/spike.lst`: the scroll-frame T-cost (new vs the 146k baseline) and
     the 3 intervening glide-frame costs, i.e. the real per-frame envelope while
     the player walks into the viewport edge continuously.
  3. Verdict: is the scroll frame now ≤~1 frame (demonstrably smooth), or ~1.3
     frames (one minor 1-in-4 burst)? If the latter, note whether the
     **shadow-screen double-buffer** (split the shift across 2 frames, atomic flip
     — tear-free even if work >1 frame) is warranted now or is M2 polish. Then
     manager+user **commit**: fold side-view forward as the Slice 1 renderer.

- **RESULT / evidence (2026-07-01):** content-rows-only shift built behind flag
  `SHIFT_CONTENT_ROWS_ONLY` (default 1); full-height SPIKE-2 path preserved for A/B
  (flag=0). Manager verified independently (not on agent assertion): build clean
  (0 warn); `tests/sideview.py` **14/14** (golden hash `bfc7560e…5aae6` unchanged —
  the shift never runs at rest); `tests/scroll.py` **12/12** (full-window byte-compare
  vs `WORLD_BUF` → no tear/dropped/doubled/stale scanline from the shorter shift).
  Constants confirmed against `build/spike.lst`: `BMP_C_START=$4880` (char row 12
  top scanline, interleaved), `BMP_T2_HIGH=$50` (third-1→2 at row 16),
  `ATTR_C_START=$5A40` (ground row 18) → shift covers rows **12–23 = 96 scanlines**,
  not 192.
  - **Measured per-frame envelope (uncontended, 70,908 T/frame budget):**
    - **Glide frame** (3 of every 4 while edge-walking): ~13.5k T ≈ **0.19 frame** —
      erase + reblit sprite only. Comfortably sub-frame; motion is smooth.
    - **Scroll frame** (1 of 4): scroll step ~81.5k T (bitmap shift ~55.6k [was
      110.3k] + attr shift ~3.5k [was 13.8k] + newcol 17.5k + set-attr 4.8k) + sprite
      erase/blit ~13.5k ≈ **~95k T ≈ 1.34 frames** (west ~1.37). Was ~2.2 frames at
      full-height → **~1.65× cheaper scroll frame; 1.80× cheaper scroll step.**
      Contended: +~40% on the move-heavy shift phases.
  - **PROVEN:** inter-scroll motion is genuinely smooth (2px glide, 0.19-frame
    frames); the periodic scroll cost is cut to a single ~1.34-frame frame occurring
    1-in-4 during sustained edge-walking. No tear, correctness preserved.
  - **REMAINING (not taken here):** the scroll frame is still >1 frame, so during
    continuous edge-walking there is one dropped frame every 4th step. Erasing even
    that requires the **shadow-screen double-buffer** (split the ~95k across 2 frames,
    atomic `$7FFD` bit-3 flip → tear-free regardless of cost) OR skipping sky rows in
    `draw_newcol_bitmap`/`set_newcol_attr` too (a further ~cheap lever noted in-code).
    Both are straightforward M2 renderer work, not feasibility unknowns.
  - **Correctness caveat (inherent to the lever):** byte-exactness relies on this
    scene confining bitmap content to rows 12–23 and keeping sky attrs uniform
    `ATTR_AIR`. Content in rows 0–11 or non-uniform sky attrs would need flag=0.
  - **Read:** smoothness risk retired. Inter-scroll motion is smooth; the residual
    is a single 1-in-4 minor burst with a known, cheap, non-speculative fix path
    (double-buffer). **Recommend committing side-view forward as the Slice 1
    renderer.** Manager awaiting user's fold-forward + commit decision.

### SPIKE-4 — Shadow-screen double-buffer · `DONE (superseded by Cauldron re-scope 2026-07-03)`
- **Note (2026-07-03):** built and green (tests 12/12), but the 2026-07-03 scroll
  re-scope to **Cauldron-style room transitions** (see Current state /
  `spectrum-design.md` §R1) removes continuous scrolling from interactive play, so
  the double-buffer's job (hiding the 1-in-4 scroll burst) no longer applies. The
  byte-shift primitive is reused for the frozen whole-screen room-transition pan;
  the double-buffer is retained in the spike for reference, not shipped.
- **Owner:** `z80-staff-engineer` → `z80-reviewer` · **Depends:** SPIKE-3
- **Decision (2026-07-01, user):** "build double-buffer first" — before folding
  side-view forward, erase even the residual 1-in-4 ~1.34-frame scroll burst so
  motion is *fully* sub-frame and tear-free, not just improved.
- **Why a plain flip is not enough:** double-buffering by itself only hides
  *tearing*; it does not shrink the ~95k-T (1.34-frame) scroll frame. To make
  **every** frame ≤1 frame we must **spread the scroll work across the 4-frame
  inter-scroll window** (the sprite crosses a byte boundary only every 4×2px) into
  the hidden back buffer, then reveal it with an **atomic `$7FFD` bit-3 flip**.
- **Target scheme (guidance; engineer may refine):** two screen buffers — bank 5
  (`$4000`, displayed when bit3=0) and bank 7 (drawn via the `$C000` window with
  `$7FFD` bits0-2=7, displayed when bit3=1). Each edge-walk step:
  - frames 1–4 (glide): advance the sprite 2px on the **front** buffer as today
    (~0.19 fr), AND do ~¼ of the next scroll into the **back** buffer (incremental
    content-rows shift + newcol + sprite), keeping every frame sub-frame;
  - on the boundary frame, **flip** bit3 to reveal the fully-prepared back buffer;
    the old front becomes the new back. No frame exceeds budget; the flip is atomic.
- **Key constraints / risks to handle:**
  - Renderer writes are currently hardcoded to `$4000/$5800`; back-buffer drawing
    needs a **base-relative** target (bank 7 bitmap `$C000`, attrs `$D800` via the
    window). Keep it behind flag `USE_SHADOW_DOUBLEBUFFER` (default 1) with the
    SPIKE-3 single-buffer path as fallback (flag 0) for A/B.
  - **Never page out ROM** (`$7FFD` bit4 stays 0 — ROM IM1 ISR + `halt` sync rely
    on it); only touch bit3 (screen select) and bits0-2 (`$C000` bank). `$7FFD` is
    write-only → keep a `PORT_7FFD_SHADOW` byte (currently `TBD` in memory-map —
    **allocate it in this change** and record the value/RMW discipline).
  - Code/data/stack live in the fixed `$8000-$BFFF` region (bank 2) and
    `PRESHIFT_TABLE`/`WORLD_BUF` at `$A000/$A500` — unaffected by `$C000` paging;
    confirm no routine assumes `$C000` holds anything across the window swap.
  - The sprite must be present on **both** buffers at the correct position after a
    flip (it lives on whichever buffer is shown); handle the erase/reblit on the
    back buffer during the incremental prep.
  - Note the contention model (bank 5 `$4000-$7FFF` is contended whether or not
    displayed; bank 7 at `$C000` contention is model-dependent) — measure, don't
    assume.
- **Exit gate:**
  1. `USE_SHADOW_DOUBLEBUFFER` path implemented; **`tests/scroll.py` +
     `tests/sideview.py` green** (no tear/clash/trail/stale column). Add/extend a
     ZRCP assertion that the **displayed** buffer (per `$7FFD` shadow / which bank
     bit3 selects) shows the expected post-scroll window — i.e. the flip actually
     reveals a correct, complete frame (no half-shifted buffer ever displayed).
  2. Manager records the **measured worst-case single frame** under sustained
     edge-walking from `build/spike.lst`: prove **no frame exceeds ~70,908 T** (or
     report the real number and where the residual is). Include the flip cost and
     the per-frame share of the spread scroll work.
  3. Verdict: is motion now fully sub-frame + tear-free? Then manager+user
     **commit + fold side-view forward** as the Slice 1 renderer (unblock P4).

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
- **Goal:** replace the top-down renderer with the WazHack-inspired side-view —
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
