# Z80 coding conventions

> Authoritative rules for all hand-written Z80 in this repo. Reviewers enforce
> these. Update here first, then the code.

## Calling conventions

- Arguments in registers, documented per routine in a header comment.
- Document **clobbers** on every routine (`; Clobbers: A, BC, HL`).
- Preserve `IX`/`IY` across routines unless a routine documents otherwise.
- Return small results in `A` / carry flag; pointers in `HL`; pairs in `DE`/`BC`.
- `HL` is the workhorse pointer/accumulator pair — prefer it for hot paths.

## Performance rules

- Prefer `inc`/`dec`/`add hl,` arithmetic over `ld`+arith where possible.
- Unroll only with a measured reason; note the cycle saving in a comment.
- `ldir`/`lddr` for block copy; `out (c)`/`in` patterns for paging.
- Self-modifying code is allowed in hot paths but MUST be flagged
  `; SMC:` with what gets patched and where, and must not live in ROM-paged space.
- Annotate hot routines with their T-state cost in the header.

## Memory & data

- No magic addresses. Define them as constants in an include and reference by name.
- Tables that the renderer/engine index into get a comment with the entry stride.
- Keep `docs/memory-map.md` authoritative; never allocate a fixed address without
  recording it there in the same change.

## Banking (128K)

- Paging port is `$7FFD` (write-only — keep a shadow byte in RAM, never read-modify
  the port). Record the current bank shadow location in `docs/memory-map.md`.
- Document which bank any far data lives in, and the bank-switch cost around it.
- Hot (per-tick) code lives in bank 2. Cold code that pages `$C000` lives in
  bank 5 low RAM (`src/lowram.asm`); cold code that needs no other `$C000`
  bank lives in bank 3 (`src/bank3.asm`) and is entered only through `far3`
  (HL = target, A = arg; restores the caller's page from the shadow). Bank-3
  code never pages `$C000` itself — it calls bank-2 helpers that re-page it
  (`blit_keep`). See `docs/memory-map.md` "Cold code placement".

## World-state changes (render resync contract)

- The play loop renders FIRST in a tick, from the previous tick's `anim_tick`
  output (`N_VIS` / `N_FID` / `RLIST`). Every path that **rewrites the entity
  table** (new game; Stage 3B level change / stairs) must end with
  `vis_reset`, and every path that **changes `CUR_ROOM` with the slots kept**
  (room exit) with `vis_room_sync` (both `src/lowram.asm`, always mapped).
  Skipping it draws the previous world's slots for a tick (bugs B7 / B7b;
  `tests/game.py` #52 / #54). See `docs/memory-map.md` "Double buffer".

## Style

- Labels: `snake_case`; local labels `.likeThis` under a parent.
- Constants: `UPPER_SNAKE`.
- One logical routine per block, with a banner header comment.
- Comments explain *why* and cost, not the opcode mnemonic.

## Interrupts

- IM and ISR setup is documented in one place once it exists.
- Routines that must run with interrupts disabled document the `di`/`ei` window
  and keep it as short as possible.
- **`IY` = `$5C3A` invariant.** The engine runs under the ROM IM1 ISR (e.g. the
  chord-capture `halt` in the input layer relies on the ROM keyboard scan), which
  addresses system variables via `IY`. Both the `.tap` (USR-from-BASIC) and `.sna`
  entry paths leave `IY=$5C3A`, and the engine never reloads it — so it works
  today. If any routine ever repurposes `IY` or the `$5C00` system-var region
  while interrupts are enabled, the ROM ISR becomes memory-corrupting. Either keep
  `IY=$5C3A` whenever `ei` is in effect, or install a custom ISR first.

## Testing hook

- Anything worth asserting on (player HP, RNG state, dungeon seed, render flags)
  should live at a stable, named address so the `test` skill can read it via ZRCP.

## Test probe labels

- A label that exists only as a ZRCP breakpoint target for the tests (e.g.
  `tick_work`, `wait_tick`, `select_tick` in `src/main.asm`) is commented
  "test probe" at its definition and listed in `docs/memory-map.md`. Never place
  a probe on a `HALT`: ZEsarUX's `run` re-fires on the halted PC without progress.
