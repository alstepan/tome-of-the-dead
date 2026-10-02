;==============================================================================
; gfx.asm — PROTO graphics layer (bank 2, hot).
;   paging + the bank-3 far-call trampoline, masked blit at any (px multiple
;   of 4, py) (§5.1), exact-footprint attr stamp (§4.2), tile-map
;   erase/restore (§4.3), HUD text, room draw. The boot-time generator and
;   init_tiles live in lowram.asm (bank 5); the transition scrolls in
;   bank3.asm.
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
; far3 — call the bank-3 cold routine at HL with bank 3 paged in at $C000, then
; put the caller's $C000 bank back (saved PORT_7FFD_SHADOW value).
; In : HL = target (bank3.asm), A = passed to the target in A.
; Out: the target's BC, DE, HL, IX (passed through).  Clobbers: A, F.
; ~200 T + target. Not re-entrant into another bank (bank-3 code must not page
; $C000 itself — see bank3.asm; it blits through blit_keep).
;==============================================================================
far3:
                ld   b, a
                ld   a, (PORT_7FFD_SHADOW)
                push af                        ; caller's page (bit 4 set, bit 5 clear)
                ld   a, b
                push af                        ; target's A
                ld   a, BANK_COLD3
                call page_bank
                pop  af
                call jp_hl
                pop  af
                ; fall through
;------------------------------------------------------------------------------
; restore_page — re-page $C000 from A = a saved PORT_7FFD_SHADOW value. Shadow
; first, then the port (page_bank rule: an ISR re-OUTing the shadow is then
; never stale). Clobbers: nothing but the shadow (BC kept for far3's callers).
;------------------------------------------------------------------------------
restore_page:
                ld   (PORT_7FFD_SHADOW), a
                push bc
                ld   bc, PORT_7FFD
                out  (c), a
                pop  bc
                ret
jp_hl:          jp   (hl)

;------------------------------------------------------------------------------
; blit_keep — blit_sprite for code running from a paged bank (bank3.asm): the
; blit pages the pool in at $C000, so the caller's bank is re-paged before the
; return. Same In as blit_sprite.  Clobbers: A, F, BC, DE, HL.  blit + ~80 T
;------------------------------------------------------------------------------
blit_keep:
                ld   a, (PORT_7FFD_SHADOW)
                push af
                call blit_sprite
                pop  af
                jr   restore_page

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
                add  a, a                      ; CF = id bit 5 (ids < TILE_IDS = 64)
                ld   e, a
                ld   d, TILE_GLYPHS >> 9
                rl   d                         ; DE = TILE_GLYPHS + id*8 (512-aligned base; +8 T vs 32 ids)
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
                add  hl, hl                    ; fid*FT_STRIDE (4; ASSERTed at ft_ptr)
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
                add  hl, hl                    ; fid*FT_STRIDE
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

; ft_ptr — HL = frame_tab + A*FT_STRIDE (4).  Clobbers: A, DE, HL
                ASSERT FT_STRIDE == 4          ; blit_sprite / frame_footprint / ft_ptr: 2 x add hl,hl
                ASSERT FT_H == FT_COLS + 1     ; blit_sprite / frame_footprint: inc hl
ft_ptr:
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                ld   de, frame_tab
                add  hl, de
                ret
