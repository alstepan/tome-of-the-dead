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

## Style

- Labels: `snake_case`; local labels `.likeThis` under a parent.
- Constants: `UPPER_SNAKE`.
- One logical routine per block, with a banner header comment.
- Comments explain *why* and cost, not the opcode mnemonic.

## Interrupts

- IM and ISR setup is documented in one place once it exists.
- Routines that must run with interrupts disabled document the `di`/`ei` window
  and keep it as short as possible.

## Testing hook

- Anything worth asserting on (player HP, RNG state, dungeon seed, render flags)
  should live at a stable, named address so the `test` skill can read it via ZRCP.
