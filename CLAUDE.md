# WazHack/ZX — ZX Spectrum 128K roguelike

A roguelike for the ZX Spectrum 128K, inspired by WazHack. Hand-written Z80
assembly, assembled with **sjasmplus**, developed fully agentically.

## Per-repo override of global preferences

The global "never write code I haven't asked for; guide me to write it myself"
rule is **suspended for this repo**. Development here is agentic: agents and the
main thread write Z80 directly; the user reviews. Everything else from the
global prefs still applies (deep reviews, challenging questions, perf/security
focus, concise communication).

## Roles — main thread is the manager

The main thread is the **manager/orchestrator**: it owns the execution plan
(`docs/plan.md`), delegates scoped tasks to subagents, controls the final state
of the work, and is accountable for quality. It does not normally write the
game's Z80 itself — implementation is delegated to the `z80-staff-engineer`
agent, which reconstructs context from the docs on every spawn.

Delegation map:
- design/rules/scope/rendering → `game-designer`
- Z80 implementation, hard (frame tick, render, paging, memory layout) →
  `z80-staff-engineer` (Opus)
- Z80/Python implementation, bounded (data, tests, tools, renames, doc sync) →
  `z80-junior` (Sonnet); escalates to staff via `ESCALATE:`
- feature split needing code knowledge → `z80-architect` (Opus, read-only)
- review (correctness/perf/regression) → `z80-reviewer`
- graphics data → `graphics-artist`; sound → `sound-composer` (deferred)

### Token budget rules (manager)

- Default: the manager splits tasks itself from the plan — no extra spawn.
  `z80-architect` only for medium/large features whose contracts need code
  reading; small or hard tasks go straight to staff.
- Model overrides per spawn: `z80-reviewer` → Sonnet for data/test/tool diffs;
  `graphics-artist` → Sonnet for import/convert-only runs (authoring stays Opus).
- Task prompts name the exact doc sections and files to read; agents do not
  cold-load whole design docs.
- Agents report test summaries (counts, failing ids), never full harness logs.
- Junior tasks run in parallel only with disjoint owned files; shared layout
  files (`memory-map.md`, `sprites/index.asm`, `*_defs.asm`) are staff-only.

The manager writes/maintains `docs/plan.md`, decides task sequencing, integrates
results, runs the final `build`/`test` gate, and keeps the docs authoritative.

## Engineering ground truth

Optimise for cycles and bytes; the 128K budget is generous but not infinite and
the Z80 is slow. Persistent engineering knowledge lives in docs, not in any
subagent:

- `docs/conventions.md` — register/calling conventions, coding rules, banking.
- `docs/memory-map.md`  — the authoritative memory & bank layout. Update it in
  the same change that moves anything. Treat it as ground truth.
- `docs/design/`        — game-designer output: the Spectrum reinterpretation,
  rules, controls, scope.

## Toolchain (all installed and verified)

- Assembler: `sjasmplus` 1.20.x  (`DEVICE ZXSPECTRUM128`, `SAVETAP`)
- Emulator (primary, runtime): **Fuse for macOS**
- Emulator (debug/test): **ZEsarUX** via the **ZRCP** remote protocol (TCP)
- Pixel editing: Pixelorama (GUI; agents cannot drive it — they produce/validate
  the packed asm byte data instead)
- Sprite art: the user's claude.ai **Design** canvas (Artifact type "Design") is
  the source of truth; the manager reads/writes it (subagents can't use the
  Artifact tool), the artist imports via `tools/svg_sprites.py`. No AI raster.

## Workflow

- `build`  skill → assemble to `build/wazhack.tap` (+ `.sld` for debug)
- `run`    skill → launch in Fuse
- `debug`  skill → launch ZEsarUX with ZRCP and drive it (registers/memory/bp)
- `test`   skill → automated emulator assertions + golden-screen regression
- `gfx-convert` skill → image → attribute-legal → asm DEFB, with clash validation

After any change that touches running behaviour, run `test`. Treat a golden-screen
diff or a failed ZRCP assertion as a regression, not noise.

## Hard Spectrum constraints (do not forget)

- Screen: 256×192, **1-bit** bitmap + 32×24 attribute grid; each 8×8 cell has
  only 2 colours (ink/paper) → "attribute clash". The rendering approach chosen
  by game-designer exists largely to manage this.
- Sound: AY-3-8912 (3 ch + noise) + beeper. Sound is deferred until the slice
  has a working engine.
- 128K paging: 16K banks at $C000 via port $7FFD. Screen bank shadowing exists.

## Conventions

- Comments explain *why*/cycle-cost, not what the opcode does.
- No magic addresses in code — use named constants from the include files.
- Keep `docs/memory-map.md` and code in sync in the same commit.

## Git

- Feature branches `feat/...`, squash-merge to main, PR descriptions even solo.
- Commit/push only when the user asks.
