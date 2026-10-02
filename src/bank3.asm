;==============================================================================
; bank3.asm — COLD code paged in at $C000 from bank 3 (docs/memory-map.md
; "Bank 3"). Assembled right after the sprite-source tail, below the AY
; reserve (AY_RESERVE, $E000). Entered ONLY through far3 (gfx.asm), which pages
; bank 3 in and puts the caller's $C000 bank back on return.
;
; Rule: nothing here may page $C000 directly (it would unmap the code that is
; running). The select screen blits through blit_keep (re-pages bank 3 after the
; pool blit); the transition scrolls never touch $C000 at all (screen, ROOM_MAP,
; NEXT_MAP and TILE_* are in bank 5, TMP4/TMP5 in bank 2).
; FORBIDDEN callees from here (they page $C000): page_bank, shadow_rect,
; shadow_room, erase_rect, hide_sprites, draw_room, blit_sprite (use blit_keep),
; and every bank-5 generator routine (gen_*, alloc*, copy_virt, mirror_src).
;
; Bank 3 is contended: code fetches here pay ULA contention (cold paths only:
; the select screen idles in HALT; the scrolls are dominated by contended
; screen LDI anyway).
;==============================================================================

;==============================================================================
; sel_run — GS_SELECT: the two heroes' IDLE frames, names, keys 1/2. Returns
; when a hero is chosen (enter_select then jumps to start_game).
; Out: C = hero kind (K_KNIGHT / K_WIZARD).  Clobbers: all but IY.
;==============================================================================
SEL_ROW         EQU 7                   ; body top row of the hero previews
sel_run:
                ld   a, GS_BOOT                ; GS_SELECT only once fully drawn
                ld   (GAME_STATE), a
                scf                            ; the last game's gen_kind re-pointed
                call sel_frt_copy              ; its hero's idle FRT row: restore
                xor  a
                call clear_screen
                ld   b, 2
                ld   c, 8
                ld   hl, str_title
                call print_str
                ld   hl, sel_tab
                ld   b, 2
.h:             push bc
                push hl
                ld   a, (hl)                   ; fid
                ld   (BL_FID), a
                inc  hl
                ld   a, (hl)                   ; col
                add  a, a
                add  a, a
                add  a, a
                ld   (BL_FPX), a
                ld   a, SEL_ROW * 8
                ld   (BL_FPY), a
                xor  a
                ld   (BL_LEFT), a
                call blit_keep                 ; pool blit, bank 3 re-paged after
                pop  hl
                push hl
                inc  hl
                ld   c, (hl)                   ; col
                inc  hl
                ld   a, (hl)                   ; attr
                ld   b, SEL_ROW
                ld   d, 3
                ld   e, 6
                call stamp_rect
                pop  hl
                push hl
                inc  hl
                ld   c, (hl)
                dec  c
                inc  hl
                inc  hl
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                ld   b, SEL_ROW + 7
                call print_str
                pop  hl
                ld   de, 5
                add  hl, de
                pop  bc
                djnz .h
                ld   b, SEL_ROW + 9
                ld   c, 7
                ld   hl, str_keys
                call print_str
                ld   b, SEL_ROW + 9
                ld   a, ATTR_HUD
                call row_attr_fill
                ld   b, 2
                call row_attr_fill
                ld   b, SEL_ROW + 7
                call row_attr_fill
                ld   a, (SYS_FRAMES)
                ld   (LAST_TICK_FRAME), a
                ld   a, GS_SELECT
                ld   (GAME_STATE), a
select_loop:
                halt
select_tick:                                   ; test probe (after the HALT)
                call scan_matrix
                call sample_input
                ld   a, (PLAYER_DISC)
                ld   c, K_KNIGHT
                bit  DK_1_BIT, a               ; '1'
                ret  nz
                inc  c
                bit  DK_2_BIT, a               ; '2'
                ret  nz
                jr   select_loop
row_attr_fill:  ld   c, 0
                push af
                call attr_addr
                pop  af
                ld   (hl), a
                ld   d, h
                ld   e, l
                inc  de
                ld   bc, 31
                ldir
                ret

str_title:      DB "CHOOSE YOUR HERO", 0
str_keys:       DB "1            2", 0

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
