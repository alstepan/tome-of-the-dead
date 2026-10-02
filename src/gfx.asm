;==============================================================================
; gfx.asm — PROTO graphics layer.
;   paging, boot-time mirror+pre-shift generator (prototype §5.1/§5.2),
;   masked blit at any (px multiple of 4, py) (§5.1), exact-footprint attr
;   stamp (§4.2), tile-map erase/restore (§4.3), HUD text, room draw and the
;   frozen Cauldron transition scrolls (§3.6, foundations F5/F6).
; Conventions: IX preserved unless stated; IY never touched (= $5C3A, ROM ISR).
;==============================================================================

;==============================================================================
; page_bank — page RAM bank A (0..7) at $C000 (48K ROM, normal screen).
; In : A = bank.   Clobbers: A, BC.   48 T
;==============================================================================
page_bank:
                or   P7FFD_ROM48
                ld   (PORT_7FFD_SHADOW), a    ; port is write-only: keep the shadow
                ld   bc, PORT_7FFD
                out  (c), a
                ret

;==============================================================================
; scr_addr_py — bitmap address of pixel row A (0..191), byte column C (0..31).
; Out: HL.  Clobbers: A.  Preserves BC, DE.   ~90 T
;   H = $40 | (py & $C0) >> 3 | (py & 7);  L = (py & $38) << 2 | col
;==============================================================================
scr_addr_py:
                ld   l, a
                and  7
                ld   h, a
                ld   a, l
                rra
                rra
                rra                           ; py>>3 (carry junk masked off)
                and  $18
                or   h
                or   SCREEN_BITMAP >> 8
                ld   h, a
                ld   a, l
                rla
                rla                           ; py<<2
                and  $E0
                or   c
                ld   l, a
                ret

;==============================================================================
; attr_addr — attribute address of cell (row B, col C).
; Out: HL.  Clobbers: A.  Preserves BC, DE.   ~60 T
;==============================================================================
attr_addr:
                ld   a, b
                rrca
                rrca
                rrca
                ld   l, a
                and  3
                or   SCREEN_ATTR >> 8
                ld   h, a
                ld   a, l
                and  $E0
                or   c
                ld   l, a
                ret

;==============================================================================
; stamp_rect — fill an attribute rectangle.
; In : A = attr, C = col (0..31), B = row, D = cols, E = rows (D,E >= 1).
; C + D > 32 is clamped to the row end and counted in CLIP_TRAP (debug trap).
; Clobbers: A, B, D, E, HL.   ~ 30 T/cell + 40 T/row + 30 T
;==============================================================================
stamp_rect:
                push af
                ld   a, c
                add  a, d
                cp   ROOM_COLS + 1
                jr   c, .inx
                ld   a, ROOM_COLS
                sub  c
                ld   d, a
                ld   hl, CLIP_TRAP
                inc  (hl)
.inx:           call attr_addr
                pop  af
.row:
                push de
                push hl
.col:
                ld   (hl), a
                inc  hl
                dec  d
                jr   nz, .col
                pop  hl
                ld   de, 32
                add  hl, de
                pop  de
                dec  e
                jr   nz, .row
                ret

;==============================================================================
; tile_rect — draw the background tiles (glyph AND attr) of a cell rect from
; the tile map (prototype §4.3). Target = the screen, or the bank-7 clean-
; background shadow (set_tile_target). Used for room draws, transition columns
; and shadow upkeep; per-tick sprite erase uses the faster erase_rect below.
; In : C = col, B = row, D = cols, E = rows (inside 0..31 x 0..20).
; Clobbers: A, BC, DE, HL.   ~290 T/cell (listing: 8 glyph rows unrolled).
;------------------------------------------------------------------------------
; Screen bitmap, attrs and the page-aligned map share the low byte
; ((row&7)<<5 | col) — so per row we patch three high bytes (SMC) and walk C.
; SMC: .mh+1 (map high), .ah+1 (attr high), .sh+1 (bitmap high) patched per row.
;==============================================================================
tile_rect:
                ld   a, e
                ld   (.rows+1), a             ; SMC: rows remaining
                ld   a, d
                ld   (.cols+1), a             ; SMC: cols per row
.row:
                ld   a, b                     ; B = row
                rrca
                rrca
                rrca
                ld   e, a                     ; E = row rotated
                and  3
                ld   d, a                     ; D = row >> 3
.mhi:           add  a, ROOM_MAP >> 8         ; SMC: map page (ROOM_MAP / NEXT_MAP)
                ld   (.mh+1), a
                ld   a, d
.aor:           or   SCREEN_ATTR >> 8          ; SMC: $58 screen / $D8 shadow
                ld   (.ah+1), a
                ld   a, b
                and  $18
.bor:           or   SCREEN_BITMAP >> 8        ; SMC: $40 screen / $C0 shadow
                ld   (.sh+1), a
                ld   a, e
                and  $E0
                or   c
                push bc                        ; keep row/col for the next row
                ld   c, a                      ; C = low byte of this row's first cell
.cols:          ld   b, 0                      ; SMC: cols
.cell:
                ld   l, c
.mh:            ld   h, 0                      ; SMC: map high
                ld   a, (hl)                   ; tile id
                ld   d, a
                ld   l, a
                ld   h, TILE_ATTRS >> 8
                ld   a, (hl)                   ; tile attr
                ld   l, c
.ah:            ld   h, 0                      ; SMC: attr high
                ld   (hl), a
                ld   a, d
                add  a, a
                add  a, a
                add  a, a
                ld   e, a
                ld   d, TILE_GLYPHS >> 8       ; DE = glyph
.sh:            ld   h, 0                      ; SMC: bitmap high (L = C still)
                DUP  7
                ld   a, (de)
                ld   (hl), a
                inc  e
                inc  h
                EDUP
                ld   a, (de)
                ld   (hl), a
                inc  c
                djnz .cell
                pop  bc
                inc  b                         ; next row
.rows:          ld   a, 0                      ; SMC: rows remaining
                dec  a
                ld   (.rows+1), a
                jr   nz, .row
                ret

; select which map tile_rect reads (A = high byte of ROOM_MAP or NEXT_MAP)
set_tile_map:
                ld   (tile_rect.mhi+1), a
                ret

; set_tile_target — A = 0: tile_rect draws to the screen; else to the shadow.
; Clobbers: A
set_tile_target:
                or   a
                ld   a, SCREEN_ATTR >> 8
                jr   z, .s
                ld   a, SHADOW_ATTR >> 8
.s:             ld   (tile_rect.aor+1), a
                sub  (SCREEN_ATTR - SCREEN_BITMAP) >> 8
                ld   (tile_rect.bor+1), a
                ret

; shadow_rect — redraw rect C,B,D,E of the clean-background shadow (bank 7)
; from ROOM_MAP (room entry, potion taken).  Clobbers: A, BC, DE, HL
shadow_rect:
                push bc
                ld   a, BANK_SHADOW
                call page_bank
                pop  bc
                ld   a, ROOM_MAP >> 8
                call set_tile_map
                ld   a, 1
                call set_tile_target
                call tile_rect
                xor  a
                jp   set_tile_target

;==============================================================================
; erase_rect — restore a cell rect (bitmap + attrs) from the clean-background
; shadow in bank 7 (prototype R-1 lever: "clean-background copy for erase").
; Shadow = the room's tiles in screen layout at $C000/$D800, so source and
; destination share the low byte and differ by +$80 in the high byte.
; In : C = col, B = row, D = cols, E = rows.  Clobbers: A, BC, DE, HL (IX kept)
; ~231 T/cell (vs ~290 T for the tile-map path: no map/glyph/attr lookups).
; SMC: .cols+1, .rows+1, .bh/.dh/.ah/.dah+1 patched per call / per row.
;==============================================================================
erase_rect:
                push bc
                ld   a, BANK_SHADOW
                call page_bank
                pop  bc
                ld   a, d
                ld   (.cols+1), a
                ld   a, e
                ld   (.rows+1), a
.row:           ld   a, b
                and  $18
                or   SCREEN_BITMAP >> 8
                ld   (.bh+1), a
                add  a, (SHADOW_BITMAP - SCREEN_BITMAP) >> 8
                ld   (.dh+1), a
                ld   a, b
                rrca
                rrca
                rrca
                ld   e, a
                and  3
                or   SCREEN_ATTR >> 8
                ld   (.ah+1), a
                add  a, (SHADOW_ATTR - SCREEN_ATTR) >> 8
                ld   (.dah+1), a
                ld   a, e
                and  $E0
                or   c
                ld   e, a                      ; E = low byte of the row's first cell
                push bc
.cols:          ld   b, 0
.cell:          ld   l, e
.bh:            ld   h, 0                      ; SMC: screen bitmap high
.dh:            ld   d, 0                      ; SMC: shadow bitmap high
                DUP  7
                ld   a, (de)
                ld   (hl), a
                inc  h
                inc  d
                EDUP
                ld   a, (de)
                ld   (hl), a
.ah:            ld   h, 0                      ; SMC: screen attr high
.dah:           ld   d, 0                      ; SMC: shadow attr high
                ld   a, (de)
                ld   (hl), a
                inc  e
                djnz .cell
                pop  bc
                inc  b
.rows:          ld   a, 0
                dec  a
                ld   (.rows+1), a
                jr   nz, .row
                ret

;==============================================================================
; draw_room — full redraw of rows 0..20 from ROOM_MAP.  ~195k T (boot/room only)
;==============================================================================
draw_room:
                ld   a, ROOM_MAP >> 8
                call set_tile_map
                ld   bc, 0                     ; row 0, col 0
                ld   de, (ROOM_COLS << 8) | ROOM_ROWS
                call tile_rect
                ; fall through: rebuild the clean-background shadow too
; shadow_room — whole-room shadow rebuild (~195k T; room entry only).
shadow_room:
                ld   bc, 0
                ld   de, (ROOM_COLS << 8) | ROOM_ROWS
                jp   shadow_rect

;==============================================================================
; clear_screen — bitmap 0, attrs = A.   Clobbers: BC, DE, HL
;==============================================================================
clear_screen:
                push af
                ld   hl, SCREEN_BITMAP
                ld   de, SCREEN_BITMAP + 1
                ld   bc, SCREEN_BITMAP_LEN - 1
                ld   (hl), 0
                ldir
                pop  af
                ld   hl, SCREEN_ATTR
                ld   de, SCREEN_ATTR + 1
                ld   bc, SCREEN_ATTR_LEN - 1
                ld   (hl), a
                ldir
                ret

;==============================================================================
; TEXT (ROM charset, 48K ROM paged).
; print_char — A = ASCII 32..127 at cell (row B, col C); C advances.
; Clobbers: A, DE, HL.
;==============================================================================
print_char:
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ld   de, ROM_CHARSET - 32 * 8
                add  hl, de
                ex   de, hl                    ; DE = glyph
                ld   a, b
                and  $18
                or   SCREEN_BITMAP >> 8
                ld   h, a
                ld   a, b
                rrca
                rrca
                rrca
                and  $E0
                or   c
                ld   l, a
                DUP  7
                ld   a, (de)
                ld   (hl), a
                inc  de
                inc  h
                EDUP
                ld   a, (de)
                ld   (hl), a
                inc  c
                ret

; print_str — HL = 0-terminated string at (row B, col C). C advances.
; Clobbers: A, C, DE, HL
print_str:
                ld   a, (hl)
                or   a
                ret  z
                push hl
                call print_char
                pop  hl
                inc  hl
                jr   print_str

; print_dec — A (0..255) in decimal, no leading zeros, at (B, C). C advances.
; Clobbers: A, DE, HL
print_dec:
                ld   l, 0                      ; L = "printed a digit" flag
                ld   h, 100
                call .digit
                ld   h, 10
                call .digit
                add  a, '0'
                jp   print_char
.digit:
                ld   e, '0' - 1
.sub:           inc  e
                sub  h
                jr   nc, .sub
                add  a, h                      ; A = remainder
                ld   d, a
                ld   a, e
                cp   '0'
                jr   nz, .out
                bit  0, l
                jr   z, .skip                  ; leading zero -> nothing
.out:           ld   l, 1
                push hl
                push de
                ld   a, e
                call print_char
                pop  de
                pop  hl
.skip:          ld   a, d
                ret

; clear_row — blank the bitmap of char row B and set its 32 attrs to A.
; Unrolled fill: ~3.3k T (was ~7k with a byte loop).  Clobbers: A, DE, HL (B kept)
clear_row:
                push bc
                ld   c, 0
                push af
                call attr_addr
                pop  af
                DUP  32
                ld   (hl), a
                inc  l
                EDUP
                ld   a, b
                and  $18
                or   SCREEN_BITMAP >> 8
                ld   h, a
                ld   a, b
                rrca
                rrca
                rrca
                and  $E0
                ld   e, a                      ; E = row low byte
                ld   c, 8
                xor  a
.line:          ld   l, e
                DUP  32
                ld   (hl), a
                inc  l
                EDUP
                inc  h
                dec  c
                jr   nz, .line
                pop  bc
                ret

;==============================================================================
; MASKED BLIT (prototype §5.1): frame BL_FID, facing BL_LEFT, top-left
; (BL_FPX, BL_FPY). Variant = FRT[fid][left*2 + (fpx AND 4 ? 1 : 0)].
; screen = (screen AND mask) OR data, width = cols (+1 spill if shifted).
; Clobbers: A, BC, DE, HL.  (IX/IY untouched)
;------------------------------------------------------------------------------
; Cost: 52 T/byte (unrolled chain, entered at (6-width)*9 by an SMC jump) +
; ~65 T/scanline (reposition + third crossing) + ~420 T setup.
;   24x48 shifted  (4 cols)  : 192 B -> 10.0k + 3.1k + 0.4k = 13.5k T
;   40x48 slash    (6 cols)  : 288 B -> 15.0k + 3.1k + 0.4k = 18.5k T
; SMC: blit_jp+1 (chain entry), blit_sub+1 (width) — patched once per sprite.
;==============================================================================
BLIT_BLOCK      EQU 9                   ; bytes per unrolled chain block
BLIT_MAXW       EQU 6

blit_sprite:
                ld   a, (BL_FID)
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl                    ; fid*8
                ld   de, frame_tab + FT_COLS
                add  hl, de
                ld   c, (hl)                   ; C = data cols
                inc  hl
                ld   b, (hl)                   ; B = rows (H)
                ld   a, (BL_FPX)
                and  4                         ; shift 4?
                jr   z, .s0
                inc  c                         ; spill column
                ld   a, 1
.s0:            ld   e, a                      ; E = shift flag (0/1)
                ld   a, (BL_LEFT)
                or   a
                jr   z, .r
                ld   a, 2
.r:             add  a, e                      ; A = variant 0..3
                ld   e, a
                add  a, a
                add  a, e                      ; *3
                ld   e, a
                ld   a, (BL_FID)
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl                    ; fid*16
                ld   d, 0
                add  hl, de
                ld   de, FRT
                add  hl, de
                ld   a, (hl)                   ; bank
                cp   FRT_NONE
                jp   z, blit_miss
                inc  hl
                ld   e, (hl)
                inc  hl
                ld   d, (hl)                   ; DE = pre-shifted frame
                push bc
                call page_bank
                pop  bc
                ; SMC: width -> chain entry + reposition amount
                ld   a, c
                ld   (blit_sub+1), a
                ld   a, BLIT_MAXW
                sub  c
                ld   l, a
                add  a, a
                add  a, a
                add  a, a
                add  a, l                      ; (6-w)*9
                ld   l, a
                ld   h, 0
                push de
                ld   de, blit_chain
                add  hl, de
                ld   (blit_jp+1), hl
                pop  de
                ; screen address of the top-left
                ld   a, (BL_FPX)
                rrca
                rrca
                rrca
                and  $1F
                ld   c, a                      ; C = byte col; both paths below
                ld   a, (blit_sub+1)           ; debug trap: col + width > 32
                add  a, c                      ; would wrap into the next row
                cp   ROOM_COLS + 1             ; (unreachable today: wide ATTACK
                jp   nc, blit_clip             ; frames only face a target)
                ld   a, (BL_FPY)               ; compute HL themselves (review A1:
                and  7                         ; the shared call here was dead)
                jr   nz, .gen                  ; flyer between cells: general path
                ld   a, b
                and  7
                jr   nz, .gen                  ; (all frames are 8n rows; belt+braces)
                ; char-aligned: the row fix-up only runs every 8 lines
                ld   a, b
                rrca
                rrca
                rrca
                ld   (BLIT_CROWS), a           ; char rows
                push de
                ld   hl, (blit_jp+1)           ; same entry offset in the twin chain
                ld   de, blit_chain_al - blit_chain
                add  hl, de
                ld   (blit_al_jp+1), hl
                pop  de
                ld   a, (blit_sub+1)
                ld   (blit_al_sub+1), a
                ld   a, (BL_FPY)
                call scr_addr_py
                ld   b, 8
                jp   blit_al_jp
.gen:           ld   a, (BL_FPY)
                call scr_addr_py
blit_rowloop:
blit_jp:        jp   blit_chain                ; SMC: entry for this width
blit_chain:
                DUP  BLIT_MAXW
                ld   a, (de)                   ; mask
                inc  de
                and  (hl)
                ld   c, a
                ld   a, (de)                   ; data
                or   c
                ld   (hl), a
                inc  de
                inc  l
                EDUP
blit_sub_pre:   ld   a, l
blit_sub:       sub  0                         ; SMC: width
                ld   l, a
                inc  h                         ; next pixel line
                ld   a, h
                and  7
                jr   nz, .nx
                ld   a, l                      ; crossed a char row
                add  a, 32
                ld   l, a
                jr   c, .nx                    ; crossed a third: H already right
                ld   a, h
                sub  8
                ld   h, a
.nx:            djnz blit_rowloop
                ret
blit_clip:
                ld   hl, CLIP_TRAP             ; not drawn (stack balanced here)
                inc  (hl)
                ret
blit_miss:
                ld   hl, BLIT_MISS             ; stationary frame at a missing shift
                inc  (hl)                      ; (§5.1 debug trap) -> not drawn
                ret
                ASSERT (blit_sub_pre - blit_chain) == BLIT_BLOCK * BLIT_MAXW

; char-aligned continuation (~42 T/line vs ~65): B = lines left in this char
; row; the char-row / third fix-up runs once per 8 lines.
; SMC: blit_al_jp+1 (chain entry), blit_al_sub+1 (width) copied per sprite.
blit_chain_al:                                 ; twin chain: falls into the
                DUP  BLIT_MAXW                 ; aligned continuation below
                ld   a, (de)
                inc  de
                and  (hl)
                ld   c, a
                ld   a, (de)
                or   c
                ld   (hl), a
                inc  de
                inc  l
                EDUP
                ld   a, l
blit_al_sub:    sub  0                         ; SMC: width
                ld   l, a
                inc  h
                djnz blit_al_jp
                ld   a, l                      ; next char row
                add  a, 32
                ld   l, a
                jr   c, .third
                ld   a, h
                sub  8
                ld   h, a
.third:         ld   b, 8
                ld   a, (BLIT_CROWS)
                dec  a
                ret  z
                ld   (BLIT_CROWS), a
blit_al_jp:     jp   blit_chain                ; SMC: entry for this width

;==============================================================================
; frame_footprint — exact cell footprint of frame A at (fpx E, fpy D).
; Out: C = col, B = row, D = cols, E = rows.  Clobbers: A, HL
;   cols = (fpx&7 + W + 7) >> 3 ; rows = (fpy&7 + H + 7) >> 3   (§4.2 exact)
;==============================================================================
frame_footprint:
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                push de
                ld   de, frame_tab + FT_COLS
                add  hl, de
                pop  de
                ld   a, e
                and  4
                ld   a, (hl)                   ; cols
                jr   z, .c0
                inc  a                         ; shifted -> +1 spill col
.c0:            ld   c, a                      ; C = cols (temp)
                inc  hl
                ld   a, d
                and  7
                add  a, (hl)                   ; + H
                add  a, 7
                rrca
                rrca
                rrca
                and  $1F
                ld   l, a                      ; L = rows
                ld   a, d
                rrca
                rrca
                rrca
                and  $1F
                ld   b, a                      ; B = row
                ld   d, c                      ; D = cols
                ld   a, e
                rrca
                rrca
                rrca
                and  $1F
                ld   c, a                      ; C = col
                ld   e, l                      ; E = rows
                ret

;==============================================================================
; BOOT-TIME GENERATOR (prototype §5.1/§5.2). Per frame: copy the unshifted
; right-facing source out of banks 1/3, then emit each needed variant
; (facing x shift) into the pool banks 0/4/6 with a bump allocator. No variant
; straddles a bank (allocator skips to the next bank). ~70-100 T/output byte.
;==============================================================================
pool_banks:     DB BANK_POOL0, BANK_POOL1, BANK_POOL2

; alloc_reset — pool empty.   Clobbers: A, HL
alloc_reset:
                xor  a
                ld   (ALLOC_IDX), a
                ld   (GEN_OVERFLOW), a
                ld   hl, BANK_WINDOW
                ld   (ALLOC_PTR), hl
                ret

; alloc_mark / alloc_restore — remember/rewind the pool top (hero regen).
alloc_mark:
                ld   a, (ALLOC_IDX)
                ld   (ALLOC_MARK_IDX), a
                ld   hl, (ALLOC_PTR)
                ld   (ALLOC_MARK_PTR), hl
                ret
alloc_restore:
                ld   a, (ALLOC_MARK_IDX)
                ld   (ALLOC_IDX), a
                ld   hl, (ALLOC_MARK_PTR)
                ld   (ALLOC_PTR), hl
                ret

; alloc — reserve BC bytes. Out: A = bank, HL = addr, CF = 1 if the pool is full.
; Clobbers: A, DE, HL
alloc:
                ld   a, (ALLOC_IDX)
                cp   3
                ccf
                ret  c                         ; out of banks
                ld   hl, (ALLOC_PTR)
                push hl
                add  hl, bc                    ; end = ptr + size
                jr   nc, .fits                 ; <= $FFFF
                ld   a, h
                or   l
                jr   z, .fits                  ; exactly $10000 also fits
                pop  hl
                ld   hl, ALLOC_IDX              ; next bank, retry
                inc  (hl)
                ld   hl, BANK_WINDOW
                ld   (ALLOC_PTR), hl
                jr   alloc
.fits:
                ld   (ALLOC_PTR), hl
                ld   a, (ALLOC_IDX)
                ld   e, a
                ld   d, 0
                ld   a, h
                or   l
                jr   nz, .same
                ld   hl, BANK_WINDOW           ; ended exactly at $10000: the
                ld   (ALLOC_PTR), hl           ; next alloc opens the next bank
                ld   a, e                      ; (ptr 0 would alias the ROM)
                inc  a
                ld   (ALLOC_IDX), a
.same:          ld   hl, pool_banks
                add  hl, de
                ld   a, (hl)                   ; A = bank of THIS allocation
                pop  hl                        ; HL = start
                or   a                         ; CF = 0
                ret

; build_bitrev — BITREV_TAB[i] = i with bit order reversed.  Boot, ~20k T
build_bitrev:
                ld   hl, BITREV_TAB
.next:          ld   a, l
                ld   b, 8
                ld   c, 0
.bit:           rra
                rl   c
                djnz .bit
                ld   (hl), c
                inc  l
                jr   nz, .next
                ret

; copy_virt — copy BC bytes from VIRTUAL sprite-source address HL (banks 1/3,
; assembled at $8000..$FFFF) to DE (bank 2/5 RAM). Handles the $C000 straddle.
; Clobbers: A, BC, DE, HL
copy_virt:
                ld   a, h
                cp   BANK_WINDOW >> 8
                jr   nc, .hi                   ; $C000.. -> bank 3 as-is
                ; $8000..$BFFF -> bank 1 at +$4000; may run past into bank 3
                push bc
                push de
                push hl
                ld   a, BANK_SRC_LO
                call page_bank
                pop  hl
                pop  de
                pop  bc
                push hl                        ; avail = $C000 - HL
                ld   a, BANK_WINDOW >> 8
                sub  h
                ld   h, a
                xor  a
                sub  l
                ld   l, a
                jr   nc, .nb
                dec  h                         ; borrow
.nb:            ; HL = avail;  n1 = min(BC, avail)
                push hl
                or   a
                sbc  hl, bc                    ; avail - BC
                pop  hl
                jr   c, .split                 ; BC > avail
                pop  hl
                ld   a, h
                add  a, (BANK_WINDOW - SRC_VIRT_BASE) >> 8
                ld   h, a
                ldir
                ret
.split:         ; copy avail bytes from bank 1, then the rest from bank 3 @ $C000
                push bc                        ; total
                ld   b, h
                ld   c, l                      ; BC = avail
                pop  hl                        ; HL = total
                or   a
                sbc  hl, bc                    ; HL = rest
                ex   (sp), hl                  ; stack = rest, HL = virt src
                ld   a, h
                add  a, (BANK_WINDOW - SRC_VIRT_BASE) >> 8
                ld   h, a
                ldir
                push de
                ld   a, BANK_SRC_HI
                call page_bank
                pop  de
                pop  bc                        ; rest
                ld   hl, BANK_WINDOW
                ldir
                ret
.hi:
                push bc
                push de
                push hl
                ld   a, BANK_SRC_HI
                call page_bank
                pop  hl
                pop  de
                pop  bc
                ldir
                ret

;------------------------------------------------------------------------------
; gen_kind — generate every frame of kind A.   Clobbers: all but IX
;------------------------------------------------------------------------------
gen_kind:
                ld   h, kind_tab >> 8
                add  a, KT_FID0
                ld   l, a
                ld   a, (hl)                   ; first fid
                ld   c, a
                ld   a, l
                add  a, KT_FCNT - KT_FID0
                ld   l, a
                ld   b, (hl)                   ; count
.f:             push bc
                ld   a, c
                call gen_frame
                pop  bc
                inc  c
                djnz .f
                ret

;------------------------------------------------------------------------------
; gen_frame — generate all variants of frame A into the pool; fill FRT[A].
; Clobbers: all but IX.
;------------------------------------------------------------------------------
gen_frame:
                ld   (GEN_FID), a
                ; FRT[fid] = all NONE
                call frt_ptr                   ; HL = FRT + fid*16
                ld   b, 4
.clr:           ld   (hl), FRT_NONE
                inc  hl
                inc  hl
                inc  hl
                djnz .clr
                ; read the static entry
                ld   a, (GEN_FID)
                call ft_ptr                    ; HL = frame_tab + fid*8
                ld   e, (hl)
                inc  hl
                ld   d, (hl)                   ; DE = virtual src
                inc  hl
                ld   a, (hl)
                ld   (GEN_COLS), a
                inc  hl
                ld   a, (hl)
                ld   (GEN_H), a
                inc  hl
                inc  hl                        ; skip OFFR for now
                inc  hl
                ld   a, (hl)
                ld   (GEN_FLAGS), a
                ; source bytes = cols * H * 2
                push de
                call gen_rowbytes              ; A = cols*2
                ld   c, a
                ld   a, (GEN_H)
                call mul8                      ; HL = A * C
                ld   b, h
                ld   c, l
                pop  hl                        ; HL = virt src
                ld   de, GEN_SRC
                call copy_virt
                ; --- right facing ---
                ld   hl, GEN_SRC
                ld   (GEN_BASE), hl
                ld   a, (GEN_FID)
                call ft_ptr
                ld   de, FT_OFFR
                add  hl, de
                ld   a, (hl)
                ld   (GEN_OFF), a
                xor  a
                call gen_facing
                ; --- left facing ---
                ld   a, (GEN_FLAGS)
                and  FF_SYM
                jr   z, .mirror
                call frt_ptr_cur               ; SYM: left = right (no copy)
                ld   d, h
                ld   e, l
                inc  de
                inc  de
                inc  de
                inc  de
                inc  de
                inc  de                        ; DE = variant 2
                ld   bc, 6
                ldir
                ret
.mirror:
                call mirror_src
                ld   hl, GEN_MIR
                ld   (GEN_BASE), hl
                ld   a, (GEN_FID)
                call ft_ptr
                ld   de, FT_OFFL
                add  hl, de
                ld   a, (hl)
                ld   (GEN_OFF), a
                ld   a, 2
                jp   gen_facing

; gen_facing — A = variant base (0 right / 2 left). Uses GEN_* state.
gen_facing:
                ld   (GEN_VAR), a
                ld   a, (GEN_FLAGS)
                and  FF_MOTION
                jr   z, .stat
                xor  a                         ; MOTION: shift 0 and shift 4
                call gen_variant
                ld   hl, GEN_VAR
                inc  (hl)
                ld   a, 4
                jp   gen_variant
.stat:
                ld   a, (GEN_OFF)
                and  7                         ; anchor implies the one shift
                jp   z, gen_variant            ; shift 0 -> variant base
                ld   hl, GEN_VAR
                inc  (hl)                      ; shift 4 -> base + 1
                ld   a, 4
                jp   gen_variant

; gen_variant — emit GEN_BASE shifted by A (0/4) into the pool as variant
; GEN_VAR of GEN_FID. Clobbers: all but IX.
gen_variant:
                ld   (GEN_SHIFT), a
                ; out bytes = (cols + (shift?1:0)) * 2 * H
                ld   a, (GEN_COLS)
                ld   c, a
                ld   a, (GEN_SHIFT)
                or   a
                jr   z, .n
                inc  c
.n:             sla  c                         ; C = out row bytes
                ld   a, (GEN_H)
                call mul8                      ; HL = size
                ld   b, h
                ld   c, l
                call alloc                     ; A = bank, HL = addr
                jr   nc, .ok
                ld   a, 1
                ld   (GEN_OVERFLOW), a
                ret
.ok:
                push hl
                push af
                ; FRT[fid][var] = bank, addr
                call frt_ptr_cur
                ld   a, (GEN_VAR)
                ld   e, a
                add  a, a
                add  a, e
                ld   e, a
                ld   d, 0
                add  hl, de
                pop  af
                ld   (hl), a
                inc  hl
                pop  de                        ; DE = dest addr
                ld   (hl), e
                inc  hl
                ld   (hl), d
                push de
                call page_bank                 ; A = bank
                pop  de
                ld   hl, (GEN_BASE)
                ld   a, (GEN_H)
                ld   b, a
.row:
                push bc
                ld   a, (GEN_COLS)
                ld   b, a
                ld   a, (GEN_SHIFT)
                or   a
                jr   nz, .sh
.cp:            ld   a, (hl)                   ; shift 0: straight copy
                ld   (de), a
                inc  hl
                inc  de
                ld   a, (hl)
                ld   (de), a
                inc  hl
                inc  de
                djnz .cp
                jr   .rowdone
.sh:            ld   c, $FF                    ; prev mask  (transparent feed)
                ld   a, 0
                ld   (TMP0), a                 ; prev data  (empty feed)
.shc:           ld   a, c
                rrca
                rrca
                rrca
                rrca
                and  $F0                       ; prev_m << 4
                ld   c, a
                ld   a, (hl)
                rrca
                rrca
                rrca
                rrca
                and  $0F                       ; m >> 4
                or   c
                ld   (de), a
                inc  de
                ld   c, (hl)                   ; prev_m = m
                inc  hl
                ld   a, (TMP0)
                rrca
                rrca
                rrca
                rrca
                and  $F0
                ld   (TMP1), a
                ld   a, (hl)
                ld   (TMP0), a                 ; prev_d = d
                rrca
                rrca
                rrca
                rrca
                and  $0F
                push hl
                ld   hl, TMP1
                or   (hl)
                pop  hl
                ld   (de), a
                inc  de
                inc  hl
                djnz .shc
                ld   a, c                      ; spill column
                rrca
                rrca
                rrca
                rrca
                and  $F0
                or   $0F
                ld   (de), a
                inc  de
                ld   a, (TMP0)
                rrca
                rrca
                rrca
                rrca
                and  $F0
                ld   (de), a
                inc  de
.rowdone:
                pop  bc
                djnz .row
                ret

; mirror_src — GEN_SRC -> GEN_MIR, each row's columns reversed + bit-reversed.
; Clobbers: A, BC, DE, HL
mirror_src:
                ld   hl, GEN_SRC
                ld   de, GEN_MIR
                ld   a, (GEN_H)
                ld   b, a
.row:           push bc
                push de
                call gen_rowbytes              ; A = cols*2
                ld   c, a
                ld   b, 0
                ex   de, hl
                add  hl, bc                    ; HL = dest row end
                ex   de, hl
                ld   a, (GEN_COLS)
                ld   b, a
.col:           dec  de
                dec  de                        ; DE = dest pair (from the right)
                push de
                ld   a, (hl)                   ; mask
                inc  hl
                push hl
                ld   l, a
                ld   h, BITREV_TAB >> 8
                ld   a, (hl)
                ld   (de), a
                pop  hl
                ld   a, (hl)                   ; data
                inc  hl
                push hl
                ld   l, a
                ld   h, BITREV_TAB >> 8
                ld   a, (hl)
                inc  de
                ld   (de), a
                pop  hl
                pop  de
                djnz .col
                pop  de
                call gen_rowbytes
                add  a, e
                ld   e, a
                jr   nc, .nc
                inc  d
.nc:            pop  bc
                djnz .row
                ret

gen_rowbytes:   ld   a, (GEN_COLS)
                add  a, a
                ret

; mul8 — HL = A * C (unsigned 8x8).  Clobbers: A, B, DE, HL
mul8:
                ld   hl, 0
                ld   d, 0
                ld   e, c
                ld   b, 8
.m:             add  hl, hl
                rla
                jr   nc, .n
                add  hl, de
.n:             djnz .m
                ret

; ft_ptr — HL = frame_tab + A*8.  Clobbers: A, DE, HL
ft_ptr:
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ld   de, frame_tab
                add  hl, de
                ret

; frt_ptr — HL = FRT + A*16 ; frt_ptr_cur uses GEN_FID.  Clobbers: A, DE, HL
;------------------------------------------------------------------------------
; sel_frt_copy — CF = 0: save the two select idles' FRT rows (boot pool,
; below the alloc mark) to SEL_FRT_SAVE; CF = 1: restore them. start_game's
; gen_kind regenerates the chosen hero's frames ABOVE the mark and re-points
; their FRT rows (incl. its select idle) there; the next hero's gen_kind then
; overwrites that pool region, so without the restore the select screen drew
; whatever the last game left there.  ~1.2k T.  Clobbers: A, BC, DE, HL, TMP0
;------------------------------------------------------------------------------
sel_frt_copy:
                sbc  a, a                      ; A = $FF restore / 0 save
                ld   (TMP0), a
                ld   hl, sel_tab
                ld   de, SEL_FRT_SAVE
                ld   b, 2
.l:             push bc
                push hl
                push de
                ld   a, (hl)                   ; fid
                call frt_ptr                   ; HL = FRT row (DE clobbered)
                pop  de                        ; DE = save cursor
                ld   a, (TMP0)
                or   a
                jr   z, .cp
                ex   de, hl                    ; restore: save -> FRT
.cp:            ld   bc, FRT_STRIDE
                ldir                           ; keeps Z
                jr   z, .nx
                ex   de, hl                    ; DE = save cursor again
.nx:            pop  hl
                ld   bc, 5                     ; sel_tab stride
                add  hl, bc
                pop  bc
                djnz .l
                ret

frt_ptr_cur:
                ld   a, (GEN_FID)
frt_ptr:
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ld   de, FRT
                add  hl, de
                ret

;==============================================================================
; init_tiles — TILE_GLYPHS / TILE_ATTRS in RAM. Stand-ins from data.asm +
; bg_tiles_floor; potion/chest/torch glyphs extracted from the sheet's item
; frames (masked source: data byte = offset 1 of each [mask,data] pair).
; Clobbers: all but IX.  Boot only.
;==============================================================================
init_tiles:
                ld   hl, TILE_GLYPHS
                ld   de, TILE_GLYPHS + 1
                ld   bc, 255
                ld   (hl), 0
                ldir
                ld   hl, tile_attr_src
                ld   de, TILE_ATTRS
                ld   bc, T_COUNT
                ldir
                ld   hl, tile_src_tab
                ld   b, TILE_SRC_N
.ts:            push bc
                ld   a, (hl)                   ; tile id
                inc  hl
                add  a, a
                add  a, a
                add  a, a
                ld   e, a
                ld   d, TILE_GLYPHS >> 8       ; DE = glyph slot
                ld   a, (hl)                   ; banked?
                inc  hl
                ld   c, (hl)
                inc  hl
                ld   b, (hl)
                inc  hl
                push hl
                ld   h, b
                ld   l, c
                ld   bc, 8
                or   a
                jr   z, .img
                call copy_virt                 ; artist tile in bank 1/3
                jr   .tn
.img:           ldir                           ; engine stand-in in the image
.tn:            pop  hl
                pop  bc
                djnz .ts
                ; items from the sheet (banked source -> GEN_SRC, then pick data)
                ld   hl, item_potion
                ld   bc, item_potion_len
                ld   de, GEN_SRC
                call copy_virt
                ld   hl, GEN_SRC + 1
                ld   a, T_POTION
                ld   c, 2                      ; 1 col: stride 2
                call .pick
                ld   hl, item_torch
                ld   bc, item_torch_len
                ld   de, GEN_SRC
                call copy_virt
                ld   hl, GEN_SRC + 1
                ld   a, T_TORCH_T
                ld   c, 2
                call .pick
                ld   hl, GEN_SRC + 1 + 16
                ld   a, T_TORCH_B
                ld   c, 2
                call .pick
                ld   hl, item_chest
                ld   bc, item_chest_len
                ld   de, GEN_SRC
                call copy_virt
                ld   hl, GEN_SRC + 1
                ld   a, T_CHEST_TL
                ld   c, 4
                call .pick
                ld   hl, GEN_SRC + 3
                ld   a, T_CHEST_TR
                ld   c, 4
                call .pick
                ld   hl, GEN_SRC + 1 + 32
                ld   a, T_CHEST_BL
                ld   c, 4
                call .pick
                ld   hl, GEN_SRC + 3 + 32
                ld   a, T_CHEST_BR
                ld   c, 4
                jp   .pick
.pick:          ; 8 bytes from HL with stride C into tile A
                add  a, a
                add  a, a
                add  a, a
                ld   e, a
                ld   d, TILE_GLYPHS >> 8
                ld   b, 8
                push bc
                ld   b, 0
.pk:            ld   a, (hl)
                ld   (de), a
                inc  e
                add  hl, bc
                ex   (sp), hl
                dec  h
                ex   (sp), hl
                jr   nz, .pk
                pop  bc
                ret

;==============================================================================
; TRANSITION SCROLLS (prototype §3.6; foundations F5/F6). Gameplay frozen,
; sprites already erased, HUD rows 21..23 never touched. ROOM_MAP is shifted in
; lock-step so it always mirrors the screen; at the end ROOM_MAP == NEXT_MAP.
; Clobbers: A, BC, DE, HL, IX (documented; IY untouched).
;==============================================================================

; hscroll_room — A = EX_LEFT/EX_RIGHT (direction the player left in).
; 32/HSTEP steps of HSTEP byte-columns. HSTEP = 2 (16 px/step): each step moves
; the whole contended bitmap once (~150-170k T incl. ULA contention), so fewer,
; wider steps halve the transition (measured: 8 px/step = 1.55 s, see docs).
HSTEP           EQU 2
hscroll_room:
                ld   (TMP4), a
                xor  a
                ld   (TMP5), a                 ; k = 0 .. 32/HSTEP-1
.step:
                ld   a, (TMP4)
                cp   EX_RIGHT
                jr   nz, .west
                call shift_bmp_left
                call shift_attr_left
                ; ROOM_MAP rows <- HSTEP cols; cols 32-HSTEP.. = NEXT_MAP k*HSTEP..
                ld   hl, ROOM_MAP
                ld   b, ROOM_ROWS
.ml:            push bc
                ld   d, h
                ld   e, l
                push hl
                ld   bc, HSTEP
                add  hl, bc
                ld   bc, 32 - HSTEP
                ldir                           ; DE = row + 32-HSTEP
                pop  hl                        ; HL = row start
                push hl
                ld   bc, NEXT_MAP - ROOM_MAP
                add  hl, bc
                ld   a, (TMP5)
                add  a, a                      ; k * HSTEP
                ld   c, a
                ld   b, 0
                add  hl, bc                    ; NEXT_MAP row + k*HSTEP
                ld   bc, HSTEP
                ldir
                pop  hl
                ld   bc, 32
                add  hl, bc
                pop  bc
                djnz .ml
                ld   c, 32 - HSTEP
                jr   .col
.west:
                call shift_bmp_right
                call shift_attr_right
                ld   hl, ROOM_MAP
                ld   b, ROOM_ROWS
.mr:            push bc
                push hl                        ; row base
                ld   de, 31 - HSTEP
                add  hl, de                    ; HL = row + 31-HSTEP
                ld   d, h
                ld   e, l
                inc  de
                inc  de                        ; DE = row + 31   (HSTEP = 2)
                ld   bc, 32 - HSTEP
                lddr
                pop  hl
                push hl
                ld   bc, NEXT_MAP - ROOM_MAP + 32 - HSTEP
                add  hl, bc                    ; NEXT_MAP row + 32-HSTEP
                ld   a, (TMP5)
                add  a, a
                ld   e, a
                ld   d, 0
                or   a
                sbc  hl, de                    ; - k*HSTEP
                pop  de
                push de                        ; DE = ROOM_MAP row + 0
                ld   bc, HSTEP
                ldir
                pop  hl
                ld   bc, 32
                add  hl, bc
                pop  bc
                djnz .mr
                ld   c, 0
.col:
                ld   a, ROOM_MAP >> 8
                call set_tile_map
                ld   b, 0
                ld   de, (HSTEP << 8) | ROOM_ROWS
                call tile_rect
                ld   hl, TMP5
                inc  (hl)
                ld   a, (hl)
                cp   ROOM_COLS / HSTEP
                jp   c, .step
                ret
                ASSERT HSTEP == 2

; scanline walker for rows 0..20: IX = base, returns NC while valid.
; shift_bmp_left — every scanline of char rows 0..20: bytes 1..31 -> 0..30.
shift_bmp_left:
                ld   ix, SCREEN_BITMAP
.scan:          push ix
                pop  de
                ld   h, d
                ld   l, e
                inc  hl
                inc  hl                        ; HSTEP = 2
                DUP  32 - HSTEP
                ldi
                EDUP
                call next_scan20
                jr   nc, .scan
                ret

shift_bmp_right:
                ld   ix, SCREEN_BITMAP
.scan:          push ix
                pop  hl
                ld   a, l
                add  a, 31 - HSTEP
                ld   l, a
                ld   d, h
                add  a, HSTEP
                ld   e, a
                DUP  32 - HSTEP
                ldd
                EDUP
                call next_scan20
                jr   nc, .scan
                ret

; next_scan20 — IX -> next scanline base inside char rows 0..20; CF = 1 when done.
next_scan20:
                ld   a, ixl
                add  a, 32
                ld   ixl, a
                jr   c, .page                  ; low wrapped -> next pixel line
                ld   a, ixh
                cp   $50                       ; third 2?
                ccf
                ret  nc                        ; thirds 0/1: all 8 char rows valid
                ld   a, ixl
                cp   (ROOM_ROWS - 16) * 32     ; third 2: rows 16..20 only
                ccf
                ret  nc
.page:          ld   ixl, 0
                inc  ixh
                ld   a, ixh
                cp   SCREEN_ATTR >> 8
                ccf                            ; CF = 1 when past the bitmap
                ret

shift_attr_left:
                ld   hl, SCREEN_ATTR
                ld   b, ROOM_ROWS
.r:             push bc
                ld   d, h
                ld   e, l
                inc  hl
                inc  hl
                DUP  32 - HSTEP
                ldi
                EDUP
                pop  bc                        ; HL = next row start already
                djnz .r
                ret

shift_attr_right:
                ld   hl, SCREEN_ATTR + 31 - HSTEP
                ld   b, ROOM_ROWS
.r:             push bc
                push hl
                ld   d, h
                ld   e, l
                inc  de
                inc  de
                DUP  32 - HSTEP
                ldd
                EDUP
                pop  hl
                ld   bc, 32
                add  hl, bc
                pop  bc
                djnz .r
                ret

;------------------------------------------------------------------------------
; vscroll_room — A = EX_DOWN (content moves up, new rows enter at the bottom)
; or EX_UP (content moves down, new rows enter at the top). 21 char-row steps.
;------------------------------------------------------------------------------
vscroll_room:
                ld   (TMP4), a
                xor  a
                ld   (TMP5), a
.step:
                ld   a, (TMP4)
                cp   EX_DOWN
                jr   nz, .up
                ; --- content up: rows 1..20 -> 0..19 ---
                ld   b, 0                      ; dest row
.bu:            push bc
                call move_char_row_up          ; row B+1 -> row B
                pop  bc
                inc  b
                ld   a, b
                cp   ROOM_ROWS - 1
                jr   nz, .bu
                ld   hl, SCREEN_ATTR + 32
                ld   de, SCREEN_ATTR
                ld   bc, (ROOM_ROWS - 1) * 32
                ldir
                ld   hl, ROOM_MAP + 32
                ld   de, ROOM_MAP
                ld   bc, (ROOM_ROWS - 1) * 32
                ldir
                ; ROOM_MAP row 20 = NEXT_MAP row k
                ld   a, (TMP5)
                call next_map_row              ; HL = NEXT_MAP + k*32
                ld   de, ROOM_MAP + (ROOM_ROWS - 1) * 32
                ld   bc, 32
                ldir
                ld   b, ROOM_ROWS - 1
                jr   .draw
.up:
                ld   b, ROOM_ROWS - 1          ; dest row 20..1
.bd:            push bc
                call move_char_row_down        ; row B-1 -> row B
                pop  bc
                dec  b
                jr   nz, .bd
                ld   hl, SCREEN_ATTR + (ROOM_ROWS - 1) * 32 - 1
                ld   de, SCREEN_ATTR + ROOM_ROWS * 32 - 1
                ld   bc, (ROOM_ROWS - 1) * 32
                lddr
                ld   hl, ROOM_MAP + (ROOM_ROWS - 1) * 32 - 1
                ld   de, ROOM_MAP + ROOM_ROWS * 32 - 1
                ld   bc, (ROOM_ROWS - 1) * 32
                lddr
                ld   a, (TMP5)
                ld   c, a
                ld   a, ROOM_ROWS - 1
                sub  c
                call next_map_row              ; NEXT_MAP row 20-k
                ld   de, ROOM_MAP
                ld   bc, 32
                ldir
                ld   b, 0
.draw:
                ld   a, ROOM_MAP >> 8
                call set_tile_map
                ld   c, 0
                ld   de, (ROOM_COLS << 8) | 1
                call tile_rect
                ld   hl, TMP5
                inc  (hl)
                ld   a, (hl)
                cp   ROOM_ROWS
                jp   c, .step
                ret

next_map_row:   ; HL = NEXT_MAP + A*32
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ld   de, NEXT_MAP
                add  hl, de
                ret

; char_row_line — HL = bitmap address of char row B, pixel line 0. Clobbers A
char_row_base:
                ld   a, b
                and  $18
                or   SCREEN_BITMAP >> 8
                ld   h, a
                ld   a, b
                rrca
                rrca
                rrca
                and  $E0
                ld   l, a
                ret

; move_char_row_up — copy char row B+1 (8 lines x 32 B) onto char row B.
move_char_row_up:
                call char_row_base
                ex   de, hl                    ; DE = dest
                inc  b
                call char_row_base             ; HL = src
                jr   move_char_row
; move_char_row_down — copy char row B-1 onto char row B.
move_char_row_down:
                call char_row_base
                ex   de, hl
                dec  b
                call char_row_base
move_char_row:
                ld   a, 8
.l:             push hl
                push de
                DUP  32
                ldi
                EDUP
                pop  de
                pop  hl
                inc  h
                inc  d
                dec  a
                jr   nz, .l
                ret
