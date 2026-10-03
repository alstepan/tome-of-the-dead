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
                ld   a, ROOM_MAP >> 8
                call set_tile_map
                ld   b, 0
                ld   de, (HSTEP << 8) | PLAY_ROWS
                call tile_rect
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
                ld   a, ROOM_MAP >> 8
                call set_tile_map
                ld   c, 0
                ld   de, (ROOM_COLS << 8) | 1
                call tile_rect
                ld   hl, TMP5
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
