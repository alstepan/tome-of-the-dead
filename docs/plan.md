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
| B1 | Heavy fight (hero + 2 skeletons + goblin + ghost) = 154,852 T = **109%** of the 2-frame tick on the turn-start tick | staff | Needs user decision: optimise vs cap encounter size |
| B2 | Single-buffer flicker unmitigated | staff | Shadow-screen double-buffer proven in SPIKE-4 (see history) |
| B3 | Draft 3 art (32 frames + tiles) not yet reviewed on the canvas | user → artist | Imported provisionally from `assets/gfx/source/draft3_frames.html` |
| B4 | Spec §6.4 text for the new ladder rules | designer | |
| B5 | Fuse / real-hardware tape load not yet tried | user | |
| B6 | Bugs from the user's playtest of the baseline | user → manager | **To be listed** |

## Next

Plan & concept review with the user (game loop beyond the prototype: dungeon
generation, progression, items, descend, sound). Phases are defined here after
that review — nothing is scheduled until then.

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
