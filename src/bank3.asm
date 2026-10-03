;==============================================================================
; bank3.asm — COLD code paged in at $C000 from bank 3 (docs/memory-map.md
; "Bank 3"). Assembled right after the sprite-source tail, below the AY
; reserve (AY_RESERVE, $E400, A8). Entered ONLY through far3 (gfx.asm), which pages
; bank 3 in and puts the caller's $C000 bank back on return.
;
; Rule: nothing here may page $C000 directly (it would unmap the code that is
; running). The select screen blits through blit_keep (re-pages bank 3 after the
; pool blit); the transition scrolls never touch $C000 at all (screen, ROOM_MAP,
; NEXT_MAP and TILE_* are in bank 5, TMP4/TMP5 in bank 2).
; FORBIDDEN callees from here (they page $C000): page_bank, shadow_rect,
; shadow_room, erase_rect, hide_sprites, draw_room, blit_sprite (use blit_keep),
; present / present_full (A7), and every bank-5 generator
; routine (gen_*, alloc*, copy_virt, mirror_src).
; A7: everything here draws on the $4000 (bank 5) screen, which is the one
; displayed while it runs (enter_select / do_exit call show_bank5 first).
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
.lg:            ld   b, FLOOR_ROW1
                ld   d, HSTEP
                ld   a, SCREEN_BITMAP >> 8
                call orn_cells                 ; (lowram; pages nothing)
                ld   hl, TMP5
                inc  (hl)
                ld   a, (hl)
                cp   ROOM_COLS / HSTEP
                jp   c, .step
                ret
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

;==============================================================================
; A7 review: cold game-state code moved out of bank 2 (bank-2 headroom for
; Stage-3 hot code): new_game (+ init_ent_common, spawn_tab), the follower
; selection and arrival conflicts. None of it pages $C000 (only bank-2
; queries + vis_reset in bank-5 low RAM).
;==============================================================================
;==============================================================================
; NEW GAME (prototype §6.5: fixed seed reseeded; all rooms, monsters, potions
; re-initialised). HERO_KIND already set. A7 review: bank 3 (cold; entered
; via far3 from start_game). Ends with vis_reset (the render-state resync
; contract, lowram.asm).  Clobbers: all but IY.
;==============================================================================
new_game:
                ld   hl, RNG_SEED
                ld   (RNG_STATE), hl
                ld   hl, 0
                ld   (TURN_COUNTER), hl
                ld   (TICK_COUNTER), hl        ; per-game test observables
                ld   hl, ANIM_TRACE            ; (OVERRUN_COUNT, GEN_OVERFLOW
                ld   de, ANIM_TRACE + 1        ; stay "since boot")
                ld   bc, ANIM_TRACE_LEN - 1
                ld   (hl), $FF
                ldir
                xor  a
                ld   (ANIM_TRACE_IDX), a
                ld   (BLIT_MISS), a
                ld   (DMG_OVERFLOW), a
                ld   (CLIP_TRAP), a
                ld   (POTIONS_TAKEN), a
                ld   (CUR_ROOM), a
                ld   (EXIT_KIND), a
                ld   (ZAP_T), a
                ld   (MSG_Q), a
                ld   (PEND_DMG_COUNT), a
                ld   (TURN_PHASE), a
                ld   (NEED_RELEASE), a
                ld   (FLY_INBOX), a            ; 0 outside ai_flyer (try_step reads it)
                ld   (YIELD_FLAG), a
                ld   hl, P_ENTITIES
                ld   de, P_ENTITIES + 1
                ld   bc, P_MAX_ENT * P_ENT_STRIDE - 1
                ld   (hl), 0
                ldir
                call proto_level               ; B3B-8: rooms A-D = a 3B level state
                ld   hl, $FFFF                 ; no jump refused (game.md §2.4 "not
                ld   (JUMP_TURN), hl           ; two turns in a row")
                ; --- hero, slot 0 ---
                ld   ix, P_ENTITIES
                ld   a, (HERO_KIND)
                ld   (ix+E_KIND), a
                ld   (ix+E_ROOM), ROOM_A
                ld   (ix+E_FLAGS), EF_ACTIVE | EF_PLAYER
                ld   (ix+E_X), HERO_START_COL
                ld   (ix+E_POT), 1
                KFIELD KT_BH
                ld   b, a
                ld   a, HERO_START_S * STOREY_ROWS + STOREY_AIR
                sub  b                         ; 9s+8-h
                ld   (ix+E_Y), a
                call init_ent_common
                ; --- monsters from spawn_tab, slots 1.. ---
                ld   hl, spawn_tab
                ld   b, SPAWN_COUNT
                ld   ix, P_ENTITIES + P_ENT_STRIDE
.sp:            push bc
                ld   a, (hl)
                ld   (ix+E_KIND), a
                inc  hl
                ld   a, (hl)
                ld   (ix+E_ROOM), a
                inc  hl
                ld   a, (hl)
                ld   (ix+E_X), a
                inc  hl
                ld   c, (hl)                   ; storey
                inc  hl
                ld   a, (hl)
                or   EF_ACTIVE | EF_HOSTILE
                ld   (ix+E_FLAGS), a
                inc  hl
                push hl
                ld   a, c                      ; 9s = 8s + s (MUL_STOREY inlined:
                add  a, a                      ; C already holds s, so the
                add  a, a                      ; macro's ld c,a would be dead)
                add  a, a
                add  a, c
                ld   c, a                      ; 9s
                KFIELD KT_FLAGS
                and  KF_FLYER
                jr   z, .walker
                ld   a, c
                inc  a                         ; flyer cruises at 9s+1
                jr   .sety
.walker:        KFIELD KT_BH
                ld   b, a
                ld   a, c
                add  a, STOREY_AIR
                sub  b                         ; 9s+8-h
.sety:          ld   (ix+E_Y), a
                call init_ent_common
                pop  hl
                ld   de, P_ENT_STRIDE
                add  ix, de
                pop  bc
                djnz .sp
                jp   vis_reset                 ; B7b: no stale render slot (lowram)

; init_ent_common — hp/max from the kind, px/py from x/y, render state reset.
init_ent_common:
                KFIELD KT_HP
                ld   (ix+E_HP), a
                ld   (ix+E_MAXHP), a
                call snap_pxpy
                ld   (ix+E_MODE), M_REST
                ld   (ix+E_DFID), $FF
                ret

;==============================================================================
; FOLLOW SELECTION (prototype §3.7) — on the player's exit turn, before the
; transition. EXIT_KIND/DEST/STOREY/COL set. No RNG; deterministic order
; (gap ascending, ties lower slot). A7 review: bank 3 (cold), do_exit enters
; it and arrival_conflicts via far3.  Clobbers: all but IY.
;==============================================================================
follow_select:
                xor  a
                ld   (FOLLOW_N), a
                ; reference box: player (horizontal) or the shaft standing box
                ld   ix, P_ENTITIES
                call get_box
                ld   a, (EXIT_KIND)
                cp   EX_UP
                jr   c, .hbox
                ld   a, (EXIT_COL)
                ld   c, a
                ld   a, (EXIT_STOREY)
                MUL_STOREY b
                add  a, STOREY_AIR
                sub  e
                ld   b, a                      ; standing y on the exit storey (9s+8-h)
.hbox:          ld   a, c
                ld   (TMP0), a                 ; ref x
                ld   a, d
                ld   (TMP2), a                 ; ref w
                ; --- candidate gaps ---
                ld   a, 1
.cl:            ld   (TMP7), a
                ld   hl, CAND_LIST
                ld   e, a
                ld   d, 0
                add  hl, de
                ld   (hl), $FF
                call ent_ix
                ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_PENDING | EF_DYING
                cp   EF_ACTIVE
                jr   nz, .cn
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .cn
                call on_ladder
                jr   z, .cn                    ; must be standing / flying
                call storey_ref
                ld   hl, EXIT_STOREY
                cp   (hl)
                jr   nz, .cn
                ld   a, (EXIT_KIND)
                cp   EX_UP
                jr   c, .hz
                KFIELD KT_FLAGS                ; vertical: climbers only
                and  KF_CLIMBER
                jr   z, .cn
.hz:            ; gap = |boxes| distance
                ld   a, (TMP0)
                cp   (ix+E_X)
                jr   c, .mright
                KFIELD KT_BW
                add  a, (ix+E_X)
                ld   b, a
                ld   a, (TMP0)
                sub  b                         ; ref.x - (m.x+m.w)
                jr   .g
.mright:        ld   a, (TMP0)
                ld   hl, TMP2
                add  a, (hl)
                ld   b, a
                ld   a, (ix+E_X)
                sub  b                         ; m.x - (ref.x+ref.w)
.g:             jr   c, .cn
                cp   FOLLOW_GAP + 1
                jr   nc, .cn
                ld   b, a
                ld   a, (TMP7)
                ld   e, a
                ld   d, 0
                ld   hl, CAND_GAP
                add  hl, de
                ld   (hl), b
                ld   hl, CAND_LIST
                add  hl, de
                ld   (hl), a
.cn:            ld   a, (TMP7)
                inc  a
                cp   P_MAX_ENT
                jp   c, .cl
                ; --- destination population ---
                call dest_counts               ; TMP3 = alive, TMP4 = tall
                ; --- admit in (gap, slot) order ---
.pick:          ld   a, (FOLLOW_N)
                cp   FOLLOW_MAX
                ret  nc
                ld   b, $FF                    ; best gap
                ld   c, $FF                    ; best slot
                ld   hl, CAND_LIST + 1
                ld   de, CAND_GAP + 1
                ld   a, 1
.pl:            push af
                ld   a, (hl)
                cp   $FF
                jr   z, .pn
                ld   a, (de)
                cp   b
                jr   nc, .pn                   ; not strictly smaller (ties: lower slot)
                ld   b, a
                pop  af
                push af
                ld   c, a
.pn:            inc  hl
                inc  de
                pop  af
                inc  a
                cp   P_MAX_ENT
                jr   c, .pl
                ld   a, c
                cp   $FF
                ret  z                         ; no more candidates
                ; mark processed
                ld   hl, CAND_LIST
                ld   e, a
                ld   d, 0
                add  hl, de
                ld   (hl), $FF
                call ent_ix
                ; caps: alive + 1 <= ROOM_CAP ; tall + 1 <= TALL_CAP
                ld   a, (TMP3)
                cp   ROOM_CAP
                jr   nc, .pick                 ; rejected, stays
                KFIELD KT_FLAGS
                and  KF_TALL
                jr   z, .admit
                ld   a, (TMP4)
                cp   TALL_CAP
                jr   nc, .pick
                inc  a
                ld   (TMP4), a
.admit:         ld   hl, TMP3
                inc  (hl)
                ld   hl, FOLLOW_N
                inc  (hl)
                call place_follower
                jr   .pick

; dest_counts — TMP3 = active monsters (incl. pending) in EXIT_DEST, TMP4 = tall.
dest_counts:
                xor  a
                ld   (TMP3), a
                ld   (TMP4), a
                ld   a, 1
.l:             ld   (TMP5), a
                call ent_ix
                ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_DYING
                cp   EF_ACTIVE
                jr   nz, .n
                ld   a, (EXIT_DEST)
                cp   (ix+E_ROOM)
                jr   nz, .n
                ld   hl, TMP3
                inc  (hl)
                KFIELD KT_FLAGS
                and  KF_TALL
                jr   z, .n
                ld   hl, TMP4
                inc  (hl)
.n:             ld   a, (TMP5)
                inc  a
                cp   P_MAX_ENT
                jr   c, .l
                ret

; place_follower — IX = admitted follower: room <- dest, PENDING, entry spot.
place_follower:
                ld   a, (EXIT_DEST)
                ld   (ix+E_ROOM), a
                set  EF_PENDING_BIT, (ix+E_FLAGS)
                ld   a, (EXIT_KIND)
                cp   EX_UP
                jr   nc, .vert
                ; horizontal: x = 1 (arrive at left edge) or 31-w; face in
                cp   EX_RIGHT
                jr   nz, .fromleft
                ld   (ix+E_X), 1
                res  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   .hy
.fromleft:      KFIELD KT_BW
                ld   b, a
                ld   a, ROOM_COLS - 1
                sub  b
                ld   (ix+E_X), a
                set  EF_LEFT_BIT, (ix+E_FLAGS)
.hy:            set  EF_WALKIN_BIT, (ix+E_FLAGS)
                KFIELD KT_FLAGS
                and  KF_FLYER
                ret  nz                        ; flyers keep their band offset (same s)
                ld   a, (EXIT_STOREY)
                jr   .stand
.vert:          ld   a, (EXIT_COL)
                ld   (ix+E_X), a
                ld   a, (EXIT_KIND)
                cp   EX_UP
                ld   a, STOREY_COUNT - 1       ; going up: arrive on the bottom storey
                jr   z, .stand
                xor  a                         ; going down: storey 0
.stand:         MUL_STOREY b
                add  a, STOREY_AIR             ; 9s+8
                ld   b, a
                KFIELD KT_BH
                ld   c, a
                ld   a, b
                sub  c
                ld   (ix+E_Y), a
                ret

;==============================================================================
; arrival_conflicts — after a transition: any non-pending monster in CUR_ROOM
; whose box overlaps the hero's arrival box becomes PENDING in place (§3.6).
;==============================================================================
arrival_conflicts:
                ld   ix, P_ENTITIES
                call get_box                   ; hero arrival box
                ld   ix, P_ENTITIES + P_ENT_STRIDE
                ld   a, 1
.l:             push af
                push bc
                push de
                ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_PENDING | EF_DYING
                cp   EF_ACTIVE
                jr   nz, .n
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .n
                call box_vs_ix
                jr   nc, .n
                set  EF_PENDING_BIT, (ix+E_FLAGS)
.n:             ld   de, P_ENT_STRIDE
                add  ix, de
                pop  de
                pop  bc
                pop  af
                inc  a
                cp   P_MAX_ENT
                jr   c, .l
                ret

;------------------------------------------------------------------------------
; Spawns (used ONCE at new-game init; slots are the truth afterwards, §3.7).
;   DB kind, room, col, storey, flags(EF_LEFT or 0) ; slot = 1 + index
;------------------------------------------------------------------------------
; B3B-3 (2 storeys): the prototype §8.2 population, storeys mapped PROTO s2 ->
; s1 (bottom: the hero's start / exit storey), s1 -> s0, s0 -> s0. One col
; moved (skeleton C) so the reference route keeps the PROTO shape: the
; skeleton climbs the far shaft while the hero takes potion 2.
;==============================================================================
; proto_level — B3B-8: the PROTO rooms A-D (data.asm map) as a 3B level state
; at LVL_STATE: header (LVL_DEPTH 0 = PROTO: level_load_tiles takes D1's set +
; the chest; D1 colours), EDGE_TAB (A|B door open, D|C closed), the 4 room
; descriptors (RD_SEED 0: build_room_map lays proto_decor instead of calling
; decor_room), FLOOR_LIST = the 4 potions (entry i = PROTO potion id i =
; POTIONS_TAKEN bit i). Until B3B-12 generates real levels for a game.
; Clobbers: A, BC, DE, HL.
;==============================================================================
proto_level:
                ld   hl, LVL_STATE
                ld   de, LVL_STATE + 1
                ld   bc, FLOOR_LIST - LVL_STATE - 1
                ld   (hl), 0
                ldir                           ; header, edges, all 9 descriptors
                ld   hl, FLOOR_LIST
                ld   de, FLOOR_LIST + 1
                ld   bc, FLOOR_MAX * FL_STRIDE - 1
                ld   (hl), FL_EMPTY
                ldir
                ld   hl, proto_hdr             ; header + EDGE_TAB (contiguous)
                ld   de, LVL_STATE
                ld   bc, PROTO_HDR_LEN
                ldir
                ld   de, FLOOR_LIST            ; the potions
                ld   c, PROTO_FLOOR_LEN
                ldir                           ; (HL runs on into proto_rooms)
                ld   a, PROTO_ROOMS
.r:             push af
                ld   a, (hl)                   ; room id
                inc  hl
                push hl
                call room_desc                 ; (bank 2) HL = its descriptor
                ex   de, hl
                pop  hl
                ld   bc, PROTO_DESC_LEN
                ldir
                pop  af
                dec  a
                jr   nz, .r
                ret

proto_hdr:      DB   0                         ; LVL_DEPTH: 0 = PROTO
                DW   0, 0                      ; LVL_SEED, GEN_RNG
                DB   ATTR_FLOOR, ATTR_WALL     ; = D1's (game.md §1.2)
                DB   ROOM_A, ROOM_NONE, ROOM_NONE, ROOM_NONE   ; start, lair, key, sanctum
                DB   PROTO_ROOMS, 0, PROTO_POTIONS             ; NROOMS, FLAGS, FLOOR_N
                DW   0                         ; MASTER_SEED
                DB   EG_LINK | EG_DOOR | EG_OPEN, 0, EG_LINK | EG_DOOR, 0, 0, 0   ; EDGE_TAB
PROTO_HDR_LEN   EQU $ - proto_hdr
                ASSERT PROTO_HDR_LEN == EDGE_TAB + EDGES_H - LVL_STATE
                ASSERT EDGE_TAB == LVL_STATE + LVL_HDR_LEN && EDGE_AB == 0 && EDGE_DC == 2
                ASSERT LVL_ATTR_FLOOR - LVL_STATE == 5 && FLOOR_N - LVL_STATE == 13
proto_floor:    ; FL_ROOM, FL_COL, FL_ITEM, FL_QTY: potion ids 0..3 (all storey 0)
                DB   ROOM_A, 28, IT_POTION, 1
                DB   ROOM_B, 1,  IT_POTION, 1
                DB   ROOM_C, 29, IT_POTION, 1
                DB   ROOM_D, 17, IT_POTION, 1
PROTO_FLOOR_LEN EQU $ - proto_floor
PROTO_POTIONS   EQU PROTO_FLOOR_LEN / FL_STRIDE
proto_rooms:    ; room id, then RD_FLAGS .. RD_BLOCK (seed / spare stay 0)
                DB   ROOM_A, RDF_PRESENT | RDF_START | RDF_DEADEND, RDX_R | RDX_RS1
                DB   0, 0, 0, 0, 5, 23, 0, 0                  ; LAD1 {5,1}, LAD2 {23,1}
                DB   ROOM_B, RDF_PRESENT, RDX_L | RDX_LS1 | RDX_D
                DB   0, 24, 0, 0, 4, 11, PIT_B, 0             ; DN {24,2}; {4,1} {11,1}
                DB   ROOM_C, RDF_PRESENT, RDX_L | RDX_LS1 | RDX_U
                DB   24, 0, 0, 0, 24, 6, 0, 0                 ; UP {24,0}; {24,1} {6,1}
                DB   ROOM_D, RDF_PRESENT | RDF_DEADEND, RDX_R | RDX_RS1
                DB   0, 0, 0, 0, 22, 8, 0, RDB_RIGHT | 3      ; {22,1} {8,1}; block
PROTO_DESC_LEN  EQU RD_BLOCK + 1
PROTO_ROOMS     EQU ($ - proto_rooms) / (PROTO_DESC_LEN + 1)
                ASSERT PROTO_ROOMS == 4 && proto_rooms == proto_floor + PROTO_FLOOR_LEN
                ASSERT proto_floor == proto_hdr + PROTO_HDR_LEN
                ASSERT RD_FLAGS == 0 && RD_BLOCK == 9 && RD_LAD1 == 6 && RD_PITCOL == 8
; PROTO decor (seed-0 rooms only): room, tile, col, row; $FF ends
proto_decor:    DB   ROOM_A, T_TORCH_T, 0, 14,  ROOM_A, T_TORCH_B, 0, 15
                DB   ROOM_D, T_CHEST_TL, 2, 6,  ROOM_D, T_CHEST_TR, 3, 6
                DB   ROOM_D, T_CHEST_BL, 2, 7,  ROOM_D, T_CHEST_BR, 3, 7
                DB   $FF

HERO_START_COL  EQU 2
HERO_START_S    EQU 1
spawn_tab:
                DB K_RAT,      ROOM_A, 16, 1, EF_LEFT
                DB K_SLIME,    ROOM_A, 14, 0, EF_LEFT
                DB K_GOBLIN,   ROOM_B, 16, 1, EF_LEFT
                DB K_BAT,      ROOM_B, 18, 0, EF_LEFT
                DB K_SKELETON, ROOM_C, 12, 1, EF_LEFT  ; col 16 -> 12: its nearest
                                                       ; climb is {6,1}, away from the
                                                       ; hero's arrival shaft {24,0}/{24,1}
                DB K_GHOST,    ROOM_C, 12, 0, EF_LEFT
                DB K_SKELETON, ROOM_D, 12, 0, EF_LEFT
                DB K_BAT,      ROOM_D, 12, 1, EF_LEFT
SPAWN_COUNT     EQU ($ - spawn_tab) / 5

                INCLUDE "levelgen.asm"          ; B3B-7: level_gen, level_start_x

;==============================================================================
; build_room_map — B3B-8 v2 (plan D7; game.md §1.1 / §2.1 / §2.5 / §3.3 /
; §1.4, concept-screen §3.1): the tile map of room A (0..8) from ROOM_DESC +
; EDGE_TAB + FLOOR_LIST (+ LVL_FLAGS for the grate) into the map at page D
; (ROOM_MAP / NEXT_MAP >> 8). Entered via far3 (lowram `build_room` keeps the
; A / H signature for do_exit and room_show). Pages nothing.
; Overwrites GEN_SCRATCH (aliases both maps): the ZX0 cache GEN_ZBLK is dropped.
;   base     cols 0 / 31 wall (WALLF in the floor rows 8 / 17), the rest AIR /
;            PLAT (row 17 stays logical PLATFORM: orn_cells draws its ornament)
;   exits    L / R: that storey's air rows opened in col 0 / 31; a door edge
;            (EDGE_TAB, index from the room id) = lintel WALL row 9s, arch 9s+1,
;            planks 9s+2..9s+7 (closed / LOCK plank if locked or sealed / the
;            open-door jambs, B10)
;   pit      row 8: T_PIT_L p-1, AIR p..p+2, T_PIT_R p+3
;   block    RD_BLOCK: w cols WALL (WALLF floor row), RUBBLE at its foot
;   segments the 6 col bytes RD_UPCOL..RD_LAD2 as {c,s} (seg_storey): ladder
;            rows 9s-1..9s+7 clipped; row 8 = HOLE + T_END_R / T_END_L caps on
;            the platform either side; row 17 = HOLE, no caps (the ornament
;            runs to the hole). ARR: + RUBBLE over the shaft in row 0 (no exit
;            up, game.md §1.1). EXIT: the level exit, T_GRATE over it unless
;            LF_GRATE_OPEN (always set in 3B, §1.4: an open grate = the hole)
;   potions  FLOOR_LIST entries of this room (IT_POTION) -> T_POTION, row 9s+7
;   decor    RD_SEED != 0: decor_room (B3B-9); seed 0 (PROTO): proto_decor
; Clobbers: A, BC, DE, HL (IX, IY kept).   ~25k T (tests/world.py W12)
;==============================================================================
build_room_map:
                push ix
                ld   (TMP0), a                 ; room
                ld   a, d
                ld   (TMP1), a                 ; map page (map_cell)
                ld   hl, 0
                ld   (GEN_ZBLK), hl            ; GEN_SCRATCH is about to be overwritten
                ld   a, (TMP0)
                call room_desc                 ; (bank 2) A, HL
                push hl
                pop  ix                        ; IX = descriptor
                ; base fill, rows 0..17 (the map rows are contiguous, 32 B each)
                ld   h, d
                ld   l, 0
                ld   b, 0                      ; row
.r:             ld   de, (T_BRICK << 8) | T_AIR
                ld   a, b
                cp   FLOOR_ROW0
                jr   z, .fl
                cp   FLOOR_ROW1
                jr   nz, .air
.fl:            ld   de, (T_WALLF << 8) | T_PLAT
.air:           ld   (hl), d                   ; col 0
                inc  hl
                ld   c, ROOM_COLS - 2
.c:             ld   (hl), e
                inc  hl
                dec  c
                jr   nz, .c
                ld   (hl), d                   ; col 31
                inc  hl
                inc  b
                ld   a, b
                cp   PLAY_ROWS
                jr   nz, .r
                ; horizontal exits + doors
                ld   bc, 0                     ; C = col 0
                ld   e, RDX_L
                call .side
                ld   c, ROOM_COLS - 1
                ld   e, RDX_R
                call .side
                ; pit, block
                ld   a, (ix+RD_PITCOL)
                or   a
                call nz, .pit
                ld   a, (ix+RD_BLOCK)
                call .block
                ; shafts and ladders: RD_UPCOL .. RD_LAD2 as {c, s}
                push ix
                pop  hl
                inc  l                         ; -> RD_EXITS; the loop pre-increments
.sg:            inc  l
                ld   a, l
                and  RD_STRIDE - 1
                cp   RD_LAD2 + 1
                jr   nc, .sgd
                push hl
                call seg_storey                ; (bank 2) A = s
                ld   e, a
                ld   a, (hl)
                call .lad
                pop  hl
                jr   .sg
.sgd:           ld   a, (ix+RD_ARRCOL)         ; arrival shaft: rubble-capped (row 0)
                ld   d, T_RUBBLE
                ld   b, 0
                call .three
                ld   a, (LVL_FLAGS)            ; level exit: the grate unless open
                and  LF_GRATE_OPEN
                jr   nz, .pots
                ld   a, (ix+RD_EXITCOL)
                ld   d, T_GRATE
                ld   b, FLOOR_ROW1
                call .three
.pots:          ; potions (3B stand-in: floor tiles, game.md §1.4)
                ld   hl, FLOOR_LIST
                ld   b, FLOOR_MAX
.pt:            ld   a, (hl)                   ; FL_ROOM ($FF & $0F = 15: never a room)
                and  FL_ROOM_MASK
                ld   c, a
                ld   a, (TMP0)
                cp   c
                jr   nz, .pn
                inc  l
                inc  l
                ld   a, (hl)                   ; FL_ITEM
                dec  l
                ld   c, (hl)                   ; FL_COL
                dec  l
                cp   IT_POTION
                jr   nz, .pn
                push hl
                push bc
                ld   a, (hl)
                rlca                           ; FL_S1 -> bit 0
                and  1
                call storey_row                ; (bank 2) A = 9s+7, keeps BC
                ld   b, a
                call map_cell
                ld   (hl), T_POTION
                pop  bc
                pop  hl
.pn:            ld   a, l
                add  a, FL_STRIDE
                ld   l, a
                djnz .pt
                ; decor
                ld   a, (ix+RD_SEED)
                or   (ix+RD_SEED + 1)
                jr   z, .proto
                ld   a, (TMP0)
                call decor_room                ; B3B-9 (IX = descriptor)
                pop  ix
                ret
.proto:         ld   hl, proto_decor           ; seed 0: the PROTO rooms' list
.pd:            ld   a, (hl)
                cp   $FF
                jr   z, .x
                ld   d, a                      ; room
                inc  hl
                ld   e, (hl)                   ; tile
                inc  hl
                ld   c, (hl)                   ; col
                inc  hl
                ld   b, (hl)                   ; row
                inc  hl
                ld   a, (TMP0)
                cp   d
                jr   nz, .pd
                push hl
                call map_cell
                ld   (hl), e
                pop  hl
                jr   .pd
.x:             pop  ix
                ret
                ASSERT FL_ROOM == 0 && FL_COL == 1 && FL_ITEM == 2 && FL_S1 == $80
                ASSERT (FLOOR_LIST & $FF) == 0 && FLOOR_MAX * FL_STRIDE <= 256
                ASSERT (FL_EMPTY & FL_ROOM_MASK) >= GRID_CELLS

.three:         ; A = left col (0: none), B = row, D = tile: 3 cells
                or   a
                ret  z
                ld   c, a
                call map_cell
                ld   (hl), d
                inc  hl
                ld   (hl), d
                inc  hl
                ld   (hl), d
                ret

.side:          ; E = RDX_L / RDX_R, C = edge col 0 / 31
                ld   a, (ix+RD_EXITS)
                and  e
                ret  z
                ld   a, e
                add  a, a
                add  a, a
                add  a, a
                add  a, a                      ; -> RDX_LS1 / RDX_RS1
                and  (ix+RD_EXITS)
                jr   z, .s0
                ld   a, 1
.s0:            MUL_STOREY b                   ; A = 9s
                ld   b, a
                push bc
                ld   d, STOREY_AIR
.o:             call map_cell
                ld   (hl), T_AIR
                inc  b
                dec  d
                jr   nz, .o
                pop  bc                        ; B = 9s, C = edge col
                ld   a, (TMP0)                 ; edge index: right edge of m =
                bit  RDX_L_BIT, e              ; m - m div 3, m = r (R) / r-1 (L)
                jr   z, .em
                dec  a
.em:            ld   l, a
.eg:            sub  GRID_W
                jr   c, .ex
                dec  l
                jr   .eg
.ex:            ld   a, l
                add  a, EDGE_TAB & $FF
                ld   l, a
                ld   h, EDGE_TAB >> 8
                ld   a, (hl)                   ; edge state
                bit  EG_DOOR_BIT, a
                ret  z                         ; open passage: no door cells
                ld   e, a
                ld   a, c
                or   a
                jr   z, .dc
                dec  a                         ; right door: cols 30-31
.dc:            ld   c, a
                call map_cell                  ; lintel, row 9s
                ld   (hl), T_BRICK
                inc  hl
                ld   (hl), T_BRICK
                inc  b
                call map_cell                  ; arch, row 9s+1
                ld   (hl), T_DOOR_ARCH_L
                inc  hl
                ld   (hl), T_DOOR_ARCH_R
                ld   a, e
                ld   de, (T_DOOR_JAMB_L << 8) | T_DOOR_JAMB_R   ; open (B10)
                bit  EG_OPEN_BIT, a
                jr   nz, .dk
                ld   de, (T_DOOR_L << 8) | T_DOOR_R
                and  EG_LOCK | EG_SEAL
                jr   z, .dk
                ld   e, T_DOOR_LOCK
.dk:            ld   a, DOOR_PLANK_H
.dp:            inc  b                         ; planks, rows 9s+2 .. 9s+7
                push af
                call map_cell
                ld   (hl), d
                inc  hl
                ld   (hl), e
                pop  af
                dec  a
                jr   nz, .dp
                ret
                ASSERT DOOR_ARCH_DY == 1 && DOOR_PLANK_DY == 2 && DOOR_COLS == 2
                ASSERT RDX_LS1 == RDX_L << 4 && RDX_RS1 == RDX_R << 4

.pit:           ; A = p (game.md §2.5): row 8, cap T_PIT_L at p-1, holes p..p+2
                ; AIR, cap T_PIT_R at p+3
                dec  a
                ld   c, a
                ld   b, FLOOR_ROW0
                call map_cell
                ld   (hl), T_PIT_L
                inc  hl
                ld   (hl), T_AIR
                inc  hl
                ld   (hl), T_AIR
                inc  hl
                ld   (hl), T_AIR
                inc  hl
                ld   (hl), T_PIT_R
                ret
                ASSERT FEAT_W == 3

.block:         ; A = RD_BLOCK: w cols at the left / right edge of storey s,
                ; rows 9s..9s+7 WALL, floor row WALLF, RUBBLE at its foot (row
                ; 9s+7, col w / 31-w)
                ld   e, a
                and  RDB_WMASK
                ret  z
                ld   d, a                      ; D = w
                ld   c, 0
                bit  RDB_RIGHT_BIT, e
                jr   z, .bl
                ld   a, ROOM_COLS
                sub  d
                ld   c, a                      ; 32 - w
.bl:            xor  a
                bit  RDB_S1_BIT, e
                jr   z, .bs
                ld   a, STOREY_ROWS
.bs:            ld   b, a                      ; 9s
                ld   e, STOREY_ROWS            ; 8 air rows + the floor row
.br:            call map_cell
                ld   a, e
                dec  a
                ld   a, T_BRICK
                jr   nz, .bt
                ld   a, T_WALLF
.bt:            push bc
                ld   b, d
.bc:            ld   (hl), a
                inc  hl
                djnz .bc
                pop  bc
                inc  b
                dec  e
                jr   nz, .br
                dec  b
                dec  b                         ; row 9s+7
                ld   a, c
                or   a
                ld   a, d                      ; left: col w
                jr   z, .rc
                ld   a, c
                dec  a                         ; right: col 31-w
.rc:            ld   c, a
                call map_cell
                ld   (hl), T_RUBBLE
                ret

.lad:           ; A = col (0: none), E = s: {c,s} rows 9s-1 .. 9s+7 clipped
                or   a
                ret  z
                ld   c, a
                ld   a, e
                MUL_STOREY b                   ; 9s
                dec  a                         ; 9s-1 ($FF for s = 0)
                ld   b, a
                ld   e, STOREY_ROWS
.lr:            ld   a, b
                cp   PLAY_ROWS                 ; $FF / > 17: clipped
                jr   nc, .lskip
                call map_cell
                ld   a, b
                cp   FLOOR_ROW1
                ld   a, T_HOLE_L               ; row 17: hole, no caps
                jr   z, .la
                ld   a, b
                cp   FLOOR_ROW0
                ld   a, T_LAD_L
                jr   nz, .la
                dec  hl                        ; row 8: caps on the platform
                ld   a, (hl)                   ; cells either side of the hole
                cp   T_PLAT
                jr   nz, .nc1
                ld   (hl), T_END_R             ; platform ends at the hole's left
.nc1:           inc  hl
                inc  hl
                inc  hl
                inc  hl
                ld   a, (hl)
                cp   T_PLAT
                jr   nz, .nc2
                ld   (hl), T_END_L             ; platform resumes at its right
.nc2:           dec  hl
                dec  hl
                dec  hl
                ld   a, T_HOLE_L
.la:            ld   (hl), a
                inc  hl
                inc  a
                ld   (hl), a
                inc  hl
                inc  a
                ld   (hl), a
.lskip:         inc  b
                dec  e
                jr   nz, .lr
                ret
                ASSERT T_LAD_M == T_LAD_L + 1 && T_LAD_R == T_LAD_L + 2
                ASSERT T_HOLE_M == T_HOLE_L + 1 && T_HOLE_R == T_HOLE_L + 2

;==============================================================================
; decor_room — B3B-9 (src/decor_gen.asm). build_room_map calls it for a
; seeded room (RD_SEED != 0) once every structural cell is placed: A = room,
; IX = its descriptor, (TMP1) = the map page (map_cell). Contract: re-derive
; everything from RD_SEED (re-entry must rebuild the identical map, W12);
; game.md §1.2 "Solidity of decor" + concept-screen §3.3 (never in floor rows
; or on door / arch / lintel / ladder / pit / cap / rubble cells; wall-set ids
; only on solid wall cells, others only on non-solid ones); fill ANIM_LIST
; only for the room being built into ROOM_MAP. Keep IX.
;==============================================================================
decor_room:
                INCLUDE "decor_gen.asm"         ; B3B-9: the deriver (code from the label on)

;==============================================================================
; init_tiles — boot (far3): the common tile set, ids 0..31 (B3B-2
; tiles_common: glyphs + depth-1 attrs; level_load_tiles re-themes the floor /
; wall ids per level) into TILE_GLYPHS / TILE_ATTRS, the row-17 ornament into
; ORN_GLYPHS, then the PROTO zap glyphs over ids 17/18 (T_ZAP1/2, still drawn
; by draw_zap; the common set has T_DRIP1/2 there, B3B-13). The per-level ids
; 32..63 come from level_load_tiles (start_game). Clobbers: A, BC, DE, HL.
;==============================================================================
init_tiles:
                ld   hl, tiles_common_glyphs
                ld   de, TILE_GLYPHS
                ld   bc, TILE_COMMON * 8
                ldir
                ld   de, TILE_ATTRS            ; tiles_common_attrs follow
                ld   c, TILE_COMMON
                ldir
                ld   hl, orn_glyphs
                ld   de, ORN_GLYPHS
                ld   c, ORN_COUNT * 8
                ldir
                ld   hl, b3fx.tiles_fx_zap1
                ld   de, TILE_GLYPHS + T_ZAP1 * 8
                ld   c, 2 * 8
                ldir
                ret
                ASSERT tiles_common_attrs == tiles_common_glyphs + TILE_COMMON * 8
                ASSERT TILES_COMMON_LEN == TILE_COMMON * 9
                ASSERT orn_glyphs_end - orn_glyphs == ORN_COUNT * 8
                ASSERT T_ZAP2 == T_ZAP1 + 1 && b3fx.tiles_fx_zap2 == b3fx.tiles_fx_zap1 + 8
                ASSERT T_ZAP1 == T_DRIP1 && T_ZAP2 == T_DRIP2 && ATTR_ZAP == $45

; cold tile data (bank 3, read once at boot)
                INCLUDE "../assets/gfx/tiles/tiles_common.asm"
                INCLUDE "../assets/gfx/panel/panel_orn.asm"
                MODULE b3fx                     ; the sheet's zap tiles (labels
                INCLUDE "../assets/gfx/sprites/tiles_fx.asm"   ; also in sprite_src)
                ENDMODULE
