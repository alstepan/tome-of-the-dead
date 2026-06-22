# Memory map (128K) — authoritative

> Ground truth for every fixed address and bank assignment. Update in the same
> change that allocates or moves anything. Code references named constants only;
> this table is where the numbers are decided.

## Address space (paged view)

| Range        | Contents                                   | Notes                         |
|--------------|--------------------------------------------|-------------------------------|
| `$0000-$3FFF`| ROM (48 or 128 editor/BASIC)               | paged via $7FFD bit 4         |
| `$4000-$57FF`| Screen bitmap (bank 5)                      | 6144 bytes                    |
| `$5800-$5AFF`| Screen attributes (bank 5)                  | 768 bytes, the clash grid     |
| `$5B00-$5BFF`| Printer buffer / reusable                   |                               |
| `$5C00-$5CBF`| System variables                            |                               |
| `$5CCB-$7FFF`| Free RAM (after BASIC reclaim)              | program + working storage     |
| `$8000-$BFFF`| Program origin region                       | `ORG $8000` for now           |
| `$C000-$FFFF`| Paged bank window                           | bank selected by $7FFD bits0-2|

## 128K banks ($C000 window)

| Bank | Planned use                       | Status   |
|------|-----------------------------------|----------|
| 0    | —                                 | TBD      |
| 1    | —                                 | TBD      |
| 2    | (also $8000 fixed)                | system   |
| 3    | —                                 | TBD      |
| 4    | —                                 | TBD      |
| 5    | normal screen (also $4000 fixed)  | system   |
| 6    | —                                 | TBD      |
| 7    | shadow screen                     | system   |

## Paging shadow

| Symbol            | Address | Purpose                                  |
|-------------------|---------|------------------------------------------|
| `PORT_7FFD_SHADOW`| TBD     | last value written to $7FFD (port is WO) |

## Engine working storage

_To be filled as the engine is built. Each entry: symbol, address, size, owner._

| Symbol | Address | Size | Owner | Notes |
|--------|---------|------|-------|-------|
| —      | —       | —    | —     | —     |

## Stable test-observable addresses

_Addresses the `test` skill reads via ZRCP. Keep these stable._

| Symbol | Address | Meaning |
|--------|---------|---------|
| —      | —       | —       |
