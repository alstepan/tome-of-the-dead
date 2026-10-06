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
- Write order is always **shadow first, then `OUT`**, through `page_bank` /
  `set_screen` only: the IM 2 ISR pages bank 3 for the AY player and restores
  the port from the shadow (protocol under "Interrupts").
- Document which bank any far data lives in, and the bank-switch cost around it.
- Hot (per-tick) code lives in bank 2. Cold code that pages `$C000` lives in
  bank 5 low RAM (`src/lowram.asm`); cold code that needs no other `$C000`
  bank lives in bank 3 (`src/bank3.asm`) and is entered only through `far3`;
  the 3C UI (menus / pause / end screens) lives in bank 1 (`src/ui1.asm`,
  `ui1_code` after `vdata`) and is entered only through `far1`. Both are
  2-byte bank loads in front of **`farb`** (bank 2, `gfx.asm`): HL = target,
  A = arg (passed in), C = bank (`farb` only); DE / IX pass in, BC does not;
  the target's BC / DE / HL / IX pass out; clobbers A, F; restores the
  caller's bank (bits 0-2 of the saved shadow, screen bit kept). Far calls
  nest (a bank-1 target may `far3`, and vice versa). Paged-bank code (bank 1
  or 3) never pages `$C000` itself — it calls helpers that re-page it
  (`blit_keep`). See `docs/memory-map.md` "Cold code placement" / "3C
  contracts".
- **Helpers restore the caller's bank.** Every bank-2 / low-RAM helper that
  pages `$C000` and returns, and is reachable from paged-bank code (bank 3 or
  bank 1), saves `PORT_7FFD_SHADOW` before paging and ends with
  `restore_page` (bits 0-2 of the saved value) — never a hard-coded
  `page_bank BANK_x` (C3-0 audit: `copy_virt3` re-paged bank 3, now
  `copy_virt_keep`; the others — `msg_push(_end)`, `show_impact_msg`,
  `print6t`, `level_load_tiles`, `door_paint`, `blit_keep`, `far*` — already
  did). Helpers that leave another bank paged (`shadow_rect`, `erase_rect`,
  `blit_sprite`, `present`, `draw_room`, `present_full`, the generator) are
  forbidden from paged-bank code except as its tail jump (`potion_pickup` →
  `shadow_rect`: `farb` re-pages). `tests/world.py` W18 calls `msg_push`,
  `copy_virt3` (pages bank 3) and a nested `far1` from a bank-1 target
  entered by `far1` with bank 0 paged and asserts bank 1 / bank 0 afterwards
  (it crashes with the old `copy_virt3`).
- History (B3B-R2 review), the rule as first written for bank 3: since R2 the monster phase runs in
  bank 3, so anything `try_step` can reach (today `mon_door` → `door_open` →
  `door_paint` → `shadow_rect`, which pages bank 7) saves `PORT_7FFD_SHADOW`
  before paging and `restore_page`s it before returning; otherwise the return
  lands in another bank's bytes. The same holds for any helper a far3 target
  calls. `tests/world.py` W9R runs a goblin opening a door through the real
  `resolve_monsters` and asserts bank 3 is paged afterwards (it crashes with
  the restore removed).

## World-state changes (render resync contract)

- The play loop renders FIRST in a tick, from the previous tick's `anim_tick`
  output (`SLOTREC` `R_VIS` / `R_FID` / `RLIST`). Every path that **rewrites the entity
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

## Interrupts (A8: IM 2)

Single source of truth for the setup: `docs/memory-map.md` "Interrupts (A8)".

- **IM 2**, installed by `boot` (`isr_install`, under boot's `DI`): 257-byte
  vector table `ISR_VEC_TABLE` (`I` = `$BB`, bank 2) of `ISR_VEC_BYTE`, ISR
  copied to `ISR_ADDR` `$BCBC`. The tape entry `start` runs before that under
  the ROM IM1 ISR (LD-BYTES ends with `EI`), with `IY = $5C3A`.
- **The ISR** (`isr`, `src/lowram.asm`, runs from bank 2): `SYS_FRAMES += 1`
  exactly as the ROM did (3 bytes; `wait_tick` paces on the low byte), then
  pages `BANK_AY` and calls `AY_PLAY` once per frame, then re-OUTs the shadow.
  It saves AF, BC, DE, HL, IX, IY (+ AF'..HL' with `ISR_SAVE_ALT=1`). No ROM
  chain by default: input is read straight from the ports (`scan_matrix`),
  nothing reads the ROM keyboard variables, so the ROM handler would only cost
  ~0.9k T/frame. `ISR_ROM_CHAIN=1` (assemble-only, untested at runtime: test #61's probe sets IY, invalid under ROM chain) ends the ISR with `jp $0038` instead (then
  `IY` must be `$5C3A` whenever interrupts are on — keep it there anyway: the
  engine never touches `IY`).
- **Paging protocol (race-free without `DI`).** Every `$7FFD` write in main
  code goes **shadow first, then `OUT`** (`page_bank`, `set_screen`; never a
  bare `OUT`, never "OUT then shadow"). The ISR **never writes the shadow**:
  it OUTs `(PORT_7FFD_SHADOW & ~7) | BANK_AY` (keeps screen bit 3 and ROM bit
  4), calls the player, then OUTs `PORT_7FFD_SHADOW` **as it is now**. An
  interrupt between a shadow write and its `OUT` therefore puts the new value
  on the port a few T early and the main code's `OUT` repeats it; an
  interrupt anywhere else restores exactly what was paged. The screen bit is
  never touched by the ISR (`tests/game.py` #61 checks port == shadow at every
  ISR exit across a 7 → 5 → 7 screen flip).
- **AY player slot contract** (`AY_PLAY` = `AY_RESERVE` `$E400`, bank 3, 7 KB
  to `$FFFF`; `src/ay.asm`, silent stub today): called with interrupts off,
  bank 3 paged at `$C000`, any stack depth. May clobber AF, BC, DE, HL, IX, IY.
  Must not: write the shadow or `$7FFD`, `EI`, touch `$C000` data of other
  banks, use the alternate set unless `ISR_SAVE_ALT=1` (assemble-only, untested at runtime) (or main code never
  uses `EXX` / `EX AF,AF'` — true today), take more than ~6.5k T (budget.md
  §5: the tick keeps 13k T per 2 frames for it).
  Main code never touches the AY ports ($FFFD select / $BFFD data): the
  select+write pair is not atomic against the ISR — sound effects are queued
  to the player (or, if ever unavoidable, DI around the pair).
- **No `DI` windows in runtime code** (they would stall the music). The only
  sites: `start` (tape entry; the ROM loader), `boot` (`DI` … `EI` around the
  SP reset, `isr_install` and the first shadow write — the ISR must not run
  before the shadow is valid), `check_paging.locked` (`DI` + `HALT`: the
  deliberate stop when paging is locked). The ISR itself runs with
  interrupts off (~0.6k T, in the top border). New routines that need `DI`
  document the window and keep it as short as possible; SP tricks (stack
  blits) are out unless they run under `DI` with that cost accepted.
- **`IY` = `$5C3A`**: still set by `start` / `boot` and never changed — needed
  by the tape path (ROM IM1 ISR) and by `ISR_ROM_CHAIN=1`; the default IM 2
  ISR does not use it.

## Testing hook

- Anything worth asserting on (player HP, RNG state, dungeon seed, render flags)
  should live at a stable, named address so the `test` skill can read it via ZRCP.

## Test probe labels

- A label that exists only as a ZRCP breakpoint target for the tests (e.g.
  `tick_work`, `wait_tick`, `select_tick` in `src/main.asm`) is commented
  "test probe" at its definition and listed in `docs/memory-map.md`. Never place
  a probe on a `HALT`: ZEsarUX's `run` re-fires on the halted PC without progress.


## Message API (B3B-13)

- `msg_push` / `msg_push_end` (low RAM) clobber **AF, BC, DE, HL** (C is no longer preserved, unlike the old `log_push`); callers in any paged bank (bank 3, bank-1 UI code) get their bank back (restore_page; W18 checks it from bank 1).
- `tk_get` uses an SMC mode switch (`tk_get.sw`): never call the text printer from the ISR.
