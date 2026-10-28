;==============================================================================
; scroll1.asm — the room transition scrolls, bank 1 (C3 review "bank-3
; relief": moved from bank3.asm; entered by far1 from do_exit, once per
; transition). Pages nothing at $C000: everything they touch is bank 5 (screen,
; ROOM_MAP / NEXT_MAP, TILE_GLYPHS, ORN_GLYPHS) or bank 2 (tile_rect,
; set_tile_map, orn_cells in low RAM).
;==============================================================================
;==============================================================================
; TRANSITION SCROLLS (prototype §3.6; foundations F5/F6). Gameplay frozen,
; sprites already erased, panel rows 18..23 never touched (B3B-3: playfield rows
; 0..17 only, row 17 = the bottom floor scrolls with the room). ROOM_MAP is shifted in
; lock-step so it always mirrors the screen; at the end ROOM_MAP == NEXT_MAP.
; Clobbers: A, BC, DE, HL, IX (documented; IY untouched).
;==============================================================================

; hscroll_room — A = EX_LEFT/EX_RIGHT (direction the player left in).
; 32/HSTEP steps of HSTEP byte-columns. HSTEP = 2 (16 px/step): each step moves
; the whole contended bitmap once (~150-170k T incl. ULA contention), so fewer,
; wider steps halve the transition (measured: 8 px/step = 1.55 s, see docs).
HSTEP           EQU 2
hscroll_room:
                call fi_mp_next                ; FLOOR1: the strips' items from NEXT_MAP
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
                ld   b, PLAY_ROWS
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
                ld   b, PLAY_ROWS
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
                push bc
                ld   a, ROOM_MAP >> 8
                call set_tile_map
                ld   b, 0
                ld   de, (HSTEP << 8) | PLAY_ROWS
                call tile_rect
                pop  bc                        ; C = the entering screen col
                ld   a, (TMP5)                 ; B3B-8: their row-17 ornament, by the
                add  a, a                      ; NEXT room's col (east: 2k, west:
                ld   e, a                      ; 32 - HSTEP - 2k)
                ld   a, (TMP4)
                cp   EX_RIGHT
                jr   z, .lg
                ld   a, ROOM_COLS - HSTEP
                sub  e
                ld   e, a
.lg:            push bc                        ; FLOOR1: the next room's floor items
                push de                        ; in the strip (fi_cells: its room cols,
                ld   a, c                      ; on screen at + screen col - room col;
                sub  e                         ; the glyph cache is EXIT_DEST's: do_exit)
                ld   (fi_cell.dc+1), a         ; SMC (lowram)
                ld   c, e                      ; (fi_cells reads NEXT_MAP: room coords)
                ld   b, 0
                ld   de, (HSTEP << 8) | PLAY_ROWS
                call fi_cells                  ; (lowram; pages nothing)
                xor  a
                ld   (fi_cell.dc+1), a
                pop  de
                pop  bc
                ld   b, FLOOR_ROW1
                ld   d, HSTEP
                ld   a, SCREEN_BITMAP >> 8
                call orn_cells                 ; (lowram; pages nothing)
                ld   hl, TMP5
                inc  (hl)
                ld   a, (hl)
                cp   ROOM_COLS / HSTEP
                jp   c, .step
                jp   fi_mp_room
                ASSERT HSTEP == 2

; scanline walker for rows 0..PLAY_ROWS-1: IX = base, returns NC while valid.
; shift_bmp_left — every scanline of char rows 0..17: bytes 2..31 -> 0..29.
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
                call next_scan_play
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
                call next_scan_play
                jr   nc, .scan
                ret

; next_scan_play — IX -> next scanline base inside char rows 0..PLAY_ROWS-1; CF = 1 when done.
next_scan_play:
                ld   a, ixl
                add  a, 32
                ld   ixl, a
                jr   c, .page                  ; low wrapped -> next pixel line
                ld   a, ixh
                cp   $50                       ; third 2?
                ccf
                ret  nc                        ; thirds 0/1: all 8 char rows valid
                ld   a, ixl
                cp   (PLAY_ROWS - 16) * 32     ; third 2: rows 16..17 only
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
                ld   b, PLAY_ROWS
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
                ld   b, PLAY_ROWS
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
; or EX_UP (content moves down, new rows enter at the top). PLAY_ROWS (18) char-row steps.
;------------------------------------------------------------------------------
vscroll_room:
                call fi_mp_next
                ld   (TMP4), a
                xor  a
                ld   (TMP5), a
.step:
                ld   a, (TMP4)
                cp   EX_DOWN
                jr   nz, .up
                ; --- content up: rows 1..17 -> 0..16 ---
                ld   b, 0                      ; dest row
.bu:            push bc
                call move_char_row_up          ; row B+1 -> row B
                pop  bc
                inc  b
                ld   a, b
                cp   PLAY_ROWS - 1
                jr   nz, .bu
                ld   hl, SCREEN_ATTR + 32
                ld   de, SCREEN_ATTR
                ld   bc, (PLAY_ROWS - 1) * 32
                ldir
                ld   hl, ROOM_MAP + 32
                ld   de, ROOM_MAP
                ld   bc, (PLAY_ROWS - 1) * 32
                ldir
                ; ROOM_MAP row 17 = NEXT_MAP row k
                ld   a, (TMP5)
                call next_map_row              ; HL = NEXT_MAP + k*32
                ld   de, ROOM_MAP + (PLAY_ROWS - 1) * 32
                ld   bc, 32
                ldir
                ld   b, PLAY_ROWS - 1
                jr   .draw
.up:
                ld   b, PLAY_ROWS - 1          ; dest row 17..1
.bd:            push bc
                call move_char_row_down        ; row B-1 -> row B
                pop  bc
                dec  b
                jr   nz, .bd
                ld   hl, SCREEN_ATTR + (PLAY_ROWS - 1) * 32 - 1
                ld   de, SCREEN_ATTR + PLAY_ROWS * 32 - 1
                ld   bc, (PLAY_ROWS - 1) * 32
                lddr
                ld   hl, ROOM_MAP + (PLAY_ROWS - 1) * 32 - 1
                ld   de, ROOM_MAP + PLAY_ROWS * 32 - 1
                ld   bc, (PLAY_ROWS - 1) * 32
                lddr
                ld   a, (TMP5)
                ld   c, a
                ld   a, PLAY_ROWS - 1
                sub  c
                call next_map_row              ; NEXT_MAP row 17-k
                ld   de, ROOM_MAP
                ld   bc, 32
                ldir
                ld   b, 0
.draw:
                push bc
                ld   a, ROOM_MAP >> 8
                call set_tile_map
                ld   c, 0
                ld   de, (ROOM_COLS << 8) | 1
                call tile_rect
                pop  bc                        ; B = the entering screen row
                push bc                        ; FLOOR1: the next room's floor items
                ld   a, (TMP4)                 ; in the row (its room row: k down,
                cp   EX_DOWN                   ; 17 - k up; on screen at row B)
                ld   a, (TMP5)
                jr   z, .vd
                cpl
                add  a, PLAY_ROWS              ; 17 - k
.vd:            ld   c, a
                ld   a, b
                sub  c
                ld   (fi_cell.dr+1), a           ; SMC (lowram): screen row - room row
                ld   b, c
                ld   c, 0
                ld   de, (ROOM_COLS << 8) | 1
                call fi_cells                  ; (lowram; pages nothing)
                xor  a
                ld   (fi_cell.dr+1), a
                pop  bc
                ld   a, (TMP4)                 ; B3B-8: is it the next room's row 17
                cp   EX_DOWN                   ; (down: k = 17 at the bottom; up:
                ld   a, (TMP5)                 ; k = 0 at the top)? -> its ornament
                jr   nz, .up0
                cp   PLAY_ROWS - 1
                jr   .orn
.up0:           or   a
.orn:           jr   nz, .nx
                ld   c, 0
                ld   de, ROOM_COLS << 8        ; 32 cells, logical col 0
                ld   a, SCREEN_BITMAP >> 8
                call orn_cells
.nx:            ld   hl, TMP5
                inc  (hl)
                ld   a, (hl)
                cp   PLAY_ROWS
                jp   c, .step
                ; fall through
; fi_mp_room / fi_mp_next — FLOOR1: fi_cells' map page (SMC) back to ROOM_MAP /
; to NEXT_MAP (the entering room in its own coords, read by the strips).
; Keep all but F (fi_mp_next keeps A: the scroll arg).
fi_mp_room:     ld   a, ROOM_MAP >> 8
                ld   (fi_cells.mp+1), a
                ret
fi_mp_next:     push af
                ld   a, NEXT_MAP >> 8
                ld   (fi_cells.mp+1), a
                pop  af
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

; char_row_base — HL = bitmap address of char row B, pixel line 0. Clobbers A
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

