;==============================================================================
; proto.asm — WazHack/ZX PROTO: first playable fighting prototype.
;             Spec: docs/design/prototype.md (rev B, authoritative).
;
; Target : ZX Spectrum 128K.   Separate build from main.asm / spike_sideview.asm:
;   sjasmplus src/proto.asm --fullpath --lst=build/proto.lst --sld=build/proto.sld
;             --sym=build/proto.sym -i src
;   -> build/proto.tap (BASIC loader + main CODE + 2 headerless sprite banks)
;   -> build/proto.sna (128K snapshot; entry = boot, all banks preloaded)
;
; Memory (docs/memory-map.md "PROTO"): code+tables $8000..(< $B000, bank 2);
; runtime entity/frame/render tables $B000..$B9FF; stack $BA00..$BEFF; state
; block $BF00..$BFFF; room maps + generator buffers $6000..$6C1F (bank 5);
; unshifted sprite SOURCES in banks 1/3 (assembled at virtual $8000..$FFFF);
; mirrored + pre-shifted sprite POOL generated at boot into banks 0/4/6.
;
; Loop: 25 Hz tick (2 frames, ROM IM1 FRAMES counter). TURN_PHASE INPUT samples
; keys and resolves a whole turn instantly (player, then monsters in slot order,
; then pending materialise); TURN_PHASE ANIM replays it (tweens, attack /
; reaction / death sequences) until every queue is done (>= 2 ticks).
;==============================================================================

                DEVICE ZXSPECTRUM128

                INCLUDE "constants.asm"
                INCLUDE "proto_defs.asm"

;==============================================================================
; SPRITE SOURCES — banks 1 and 3, assembled contiguously at virtual $8000..$FFFF
; (slot 2 = page 1, slot 3 = page 3). Read only by the boot generator via
; copy_virt (virtual < $C000 -> bank 1 at +$4000, else bank 3 as-is).
;==============================================================================
                MMU  2, BANK_SRC_LO
                MMU  3, BANK_SRC_HI
                ORG  SRC_VIRT_BASE
sprite_src:
                INCLUDE "../assets/gfx/sprites/index.asm"
sprite_src_end:
SRC_TOTAL       EQU sprite_src_end - sprite_src
    IF SRC_TOTAL > $4000
SRC_LEN_LO      EQU $4000
    ELSE
SRC_LEN_LO      EQU SRC_TOTAL
    ENDIF
SRC_LEN_HI      EQU SRC_TOTAL - SRC_LEN_LO
                ASSERT SRC_TOTAL <= $8000
                DISPLAY "PROTO sprite sources: ", /D, SRC_TOTAL, " B (bank1 ", /D, SRC_LEN_LO, ", bank3 ", /D, SRC_LEN_HI, ")"

;==============================================================================
; MAIN IMAGE — bank 2 at $8000.
;==============================================================================
                MMU  2, 2
                MMU  3, 0
                ORG  $8000

;------------------------------------------------------------------------------
; start — .tap entry (RANDOMIZE USR 32768): pull the two headerless sprite-bank
; blocks off tape with the ROM loader, then boot. The .sna enters at boot.
;------------------------------------------------------------------------------
start:
                di
                ld   sp, WORKSTORE_TOP
                ld   iy, IY_SYSVAR
                call check_paging              ; stops here if $7FFD is locked
.lo:            ld   a, BANK_SRC_LO            ; test probe (paging OK)
                call page_bank
                ld   ix, BANK_WINDOW
                ld   de, SRC_LEN_LO
                ld   a, $FF                    ; data block flag
                scf                            ; LOAD (not VERIFY)
                call ROM_LD_BYTES
                jr   nc, .lo                   ; tape error: rewind + retry
    IF SRC_LEN_HI > 0
.hi:            ld   a, BANK_SRC_HI
                call page_bank
                ld   ix, BANK_WINDOW
                ld   de, SRC_LEN_HI
                ld   a, $FF
                scf
                call ROM_LD_BYTES
                jr   nc, .hi
    ENDIF
start_loaded:                                  ; falls straight into boot:
                ASSERT start_loaded == boot    ; nothing may be inserted here

;==============================================================================
; boot — .sna entry. Cold init, pool generation (~1 s), then hero select.
;==============================================================================
boot:
                di
                ld   sp, WORKSTORE_TOP
                ld   iy, IY_SYSVAR             ; ROM ISR invariant (conventions)
                im   1
                ld   a, BANK_POOL0
                call page_bank
                xor  a
                out  (PORT_BORDER), a
                ld   (INPUT_SRC), a
                ld   (ANIM_FREEZE), a
                ld   (ANIM_TRACE_IDX), a
                ld   (BLIT_MISS), a
                ld   (DMG_OVERFLOW), a
                ld   (CLIP_TRAP), a
                ld   (TURN_PHASE), a
                ld   (ZAP_T), a
                ld   (PEND_DMG_COUNT), a
                ld   (CUR_ROOM), a
                ld   (YIELD_FLAG), a
                ld   hl, 0
                ld   (OVERRUN_COUNT), hl
                ld   (TICK_COUNTER), hl
                ld   (TURN_COUNTER), hl
                ld   hl, RNG_SEED
                ld   (RNG_STATE), hl
                ld   a, 1
                ld   (INPUT_REPEAT), a         ; play default: held keys repeat
                ld   a, GS_BOOT
                ld   (GAME_STATE), a
                ld   hl, ANIM_TRACE
                ld   de, ANIM_TRACE + 1
                ld   bc, ANIM_TRACE_LEN - 1
                ld   (hl), $FF
                ldir
                call init_kbd_mirror
                ld   a, ATTR_HUD
                call clear_screen
                ld   hl, P_ENTITIES            ; nothing drawn / alive yet
                ld   de, P_ENTITIES + 1
                ld   bc, P_MAX_ENT * P_ENT_STRIDE - 1
                ld   (hl), 0
                ldir
                ei
                call build_bitrev
                call init_tiles
                call alloc_reset
                ; monsters: every kind's frames, both facings (§5.2)
                ld   a, K_SKELETON
.gk:            push af
                call gen_kind
                pop  af
                inc  a
                cp   K_COUNT
                jr   c, .gk
                ; the three heroes' IDLE frames for the select screen
                ld   a, FID_knight_idle1
                call gen_frame
                ld   a, FID_wizard_idle
                call gen_frame
                ld   a, FID_rogue_idle
                call gen_frame
                or   a                         ; CF = 0: save
                call sel_frt_copy
                call alloc_mark                ; hero sets regenerate from here
boot_done:                                     ; falls through into enter_select
                ASSERT boot_done == enter_select

;==============================================================================
; enter_select — GS_SELECT: the three heroes' IDLE frames, names, keys 1/2/3.
;==============================================================================
SEL_ROW         EQU 7                   ; body top row of the hero previews
enter_select:
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
                ld   b, 3
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
                call blit_sprite
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
                jr   nz, start_game
                inc  c
                bit  DK_2_BIT, a               ; '2'
                jr   nz, start_game
                inc  c
                bit  DK_3_BIT, a               ; '3'
                jr   nz, start_game
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

;------------------------------------------------------------------------------
; check_paging — 48 BASIC / USR 0 set $7FFD bit 5 (paging lock): every later
; OUT is ignored, so the two sprite banks would load over each other and the
; pool would alias. Write different bytes to bank 1 and bank 0 at $C000 and
; read bank 1 back; on a mismatch print a message and stop (DI + HALT).
; Tape path only (the .sna preloads all banks and enters at boot). Bank 0 and
; bank 1 $C000 are free here (pool / sources are written after this).
; +2A/+3 are unsupported (different paging). Clobbers: A, BC, HL (+ print).
;------------------------------------------------------------------------------
check_paging:
                ld   a, BANK_SRC_LO
                call page_bank
                ld   hl, BANK_WINDOW
                ld   (hl), PAGING_PROBE
                ld   a, BANK_POOL0
                call page_bank
                ld   (hl), ~PAGING_PROBE & $FF
                ld   a, BANK_SRC_LO
                call page_bank
                ld   a, (hl)
                cp   PAGING_PROBE
                ret  z
                ld   a, ATTR_HUD
                call clear_screen
                ld   b, 11
                ld   c, 5
                ld   hl, str_lock
                call print_str
.locked:        di                             ; test probe (paging locked)
                halt


; select-screen entries: fid, body col, attr, name
sel_tab:        DB   FID_knight_idle1, 5,  $47
                DW   nm_knight
                DB   FID_wizard_idle,  14, $45
                DW   nm_wizard
                DB   FID_rogue_idle,   23, $44
                DW   nm_rogue

;==============================================================================
; start_game — C = hero kind. Generate its frames (§5.2: only the chosen
; hero), new game, first render, then the play loop.
;==============================================================================
start_game:
                ld   a, c
                ld   (HERO_KIND), a
                call alloc_restore
                ld   a, (HERO_KIND)
                call gen_kind
                call new_game
                ld   h, ROOM_MAP >> 8
                ld   a, (CUR_ROOM)
                call build_room_map
                ld   a, ATTR_HUD
                call clear_screen
                call draw_room
                call hud_status
                call hud_room
                call msg_begin
                ld   hl, str_welcome
                call print_str
                ld   a, 1
                ld   (NEED_RELEASE), a         ; the select key must be released
                ld   a, GS_PLAYING
                ld   (GAME_STATE), a
                ld   a, (SYS_FRAMES)
                ld   (LAST_TICK_FRAME), a
start_game_done:                               ; falls through into play_loop
                ASSERT start_game_done == play_loop

;==============================================================================
; play_loop — one 25 Hz tick per iteration (prototype §3.2).
;==============================================================================
play_loop:
                call wait_tick
tick_work:                                     ; budget probe: tick work starts here
                ld   hl, (TICK_COUNTER)
                inc  hl
                ld   (TICK_COUNTER), hl
                ld   a, (GAME_STATE)
                cp   GS_PLAYING
                jp   nz, end_screen
                ld   a, (TURN_PHASE)
                or   a
                call z, read_turn_input        ; INPUT: maybe start a turn
                call anim_tick
                call render
                ld   a, (TURN_PHASE)
                or   a
                jr   z, play_loop
                ld   hl, TURN_TICK
                inc  (hl)
                call turn_done
                call c, end_turn
                jr   play_loop

;------------------------------------------------------------------------------
; wait_tick — pace to 2 frames per tick. Arriving with >= 2 frames already gone
; means this tick blew its 141.8k T budget: OVERRUN_COUNT++ (presentation only).
; Clobbers: A, B, HL
;------------------------------------------------------------------------------
wait_tick:
                ld   a, (LAST_TICK_FRAME)
                ld   b, a
                ld   a, (SYS_FRAMES)
                sub  b
                cp   TICK_FRAMES
                jr   c, .wait
                ld   hl, (OVERRUN_COUNT)
                inc  hl
                ld   (OVERRUN_COUNT), hl
                jr   .go
.wait:          halt
                ld   a, (SYS_FRAMES)
                sub  b
                cp   TICK_FRAMES
                jr   c, .wait
.go:            ld   a, (SYS_FRAMES)
                ld   (LAST_TICK_FRAME), a
                ret

; resync_tick — forget elapsed time (after a transition / long cold path).
resync_tick:
                ld   a, (SYS_FRAMES)
                ld   (LAST_TICK_FRAME), a
                ret

;------------------------------------------------------------------------------
; read_turn_input — INPUT phase. Held keys repeat unless INPUT_REPEAT = 0 (then
; a release is required between turns, the P3 rule). A legal action resolves
; the whole turn now and enters the ANIM phase.  Clobbers: all but IY.
;------------------------------------------------------------------------------
read_turn_input:
                call scan_matrix
                call sample_input
                jr   nz, .held
                xor  a
                ld   (NEED_RELEASE), a
                ret
.held:          ld   a, (INPUT_REPEAT)
                or   a
                jr   nz, .go
                ld   a, (NEED_RELEASE)
                or   a
                ret  nz
.go:            call try_player_turn
                ret  nc                        ; illegal: no turn consumed
                ld   a, 1
                ld   (NEED_RELEASE), a
                ld   a, (EXIT_KIND)
                or   a
                call z, resolve_monsters       ; exit turn: monsters don't act
                ld   a, TP_ANIM
                ld   (TURN_PHASE), a
                xor  a
                ld   (TURN_TICK), a
                ret

;------------------------------------------------------------------------------
; end_turn — ANIM finished: transition (if exiting), TURN_COUNTER++, potion
; pickup, HUD, death / win checks, back to INPUT.  Clobbers: all but IY.
;------------------------------------------------------------------------------
end_turn:
                ld   a, (EXIT_KIND)
                or   a
                call nz, do_exit
                ld   hl, (TURN_COUNTER)
                inc  hl
                ld   (TURN_COUNTER), hl
                call potion_pickup
                call hud_status
                xor  a
                ld   (TURN_PHASE), a
                ld   a, (P_ENTITIES + E_FLAGS)
                and  EF_DYING
                jr   z, .alive
                ld   a, GS_DEAD
                ld   (GAME_STATE), a
                call msg_begin
                ld   hl, str_died
                jp   print_str
.alive:         ; win: standing on storey 0 of room D with x <= 3 (§8.2)
                ld   a, (CUR_ROOM)
                cp   WIN_ROOM
                ret  nz
                ld   ix, P_ENTITIES
                call is_standing
                ret  nz
                call storey_ref
                or   a
                ret  nz
                ld   a, (ix+E_X)
                cp   WIN_MAX_X + 1
                ret  nc
                ld   a, GS_WIN
                ld   (GAME_STATE), a
                call msg_begin
                ld   hl, str_win
                jp   print_str

;------------------------------------------------------------------------------
; do_exit — follower selection (§3.7), frozen Cauldron transition (§3.6),
; arrival, arrival conflicts.  Clobbers: all but IY.
;------------------------------------------------------------------------------
do_exit:
                call follow_select
                call hide_sprites              ; every sprite hidden, hero too
                ld   a, GS_TRANSITION          ; (state flips once none is drawn)
                ld   (GAME_STATE), a
                ld   h, NEXT_MAP >> 8
                ld   a, (EXIT_DEST)
                call build_room_map
                ld   a, (EXIT_KIND)
                cp   EX_UP
                jr   nc, .v
                call hscroll_room
                jr   .arr
.v:             call vscroll_room
.arr:           call shadow_room               ; clean background of the new room
                ld   a, (EXIT_DEST)
                ld   (CUR_ROOM), a
                ld   ix, P_ENTITIES
                ld   (ix+E_ROOM), a
                ld   a, (EXIT_KIND)
                cp   EX_RIGHT
                jr   nz, .nl
                ld   (ix+E_X), 1               ; entered from the left edge
                res  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   .pos
.nl:            cp   EX_LEFT
                jr   nz, .vert
                KFIELD KT_BW
                ld   b, a
                ld   a, ROOM_COLS - 1
                sub  b
                ld   (ix+E_X), a               ; 31 - w
                set  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   .pos
.vert:          ld   a, (EXIT_COL)
                ld   (ix+E_X), a
                KFIELD KT_BH
                ld   b, a
                ld   a, (EXIT_KIND)
                cp   EX_UP
                ld   a, (STOREYS - 1) * STOREY_H + 6   ; up: stand on storey 2
                jr   z, .vy
                ld   a, 6                      ; down: stand on storey 0
.vy:            sub  b
                ld   (ix+E_Y), a
.pos:           call snap_pxpy
                ld   (ix+E_MODE), M_REST
                call arrival_conflicts
                call hud_room
                xor  a
                ld   (EXIT_KIND), a
                ld   a, GS_PLAYING
                ld   (GAME_STATE), a
                jp   resync_tick

;------------------------------------------------------------------------------
; end_screen — GS_DEAD / GS_WIN: wait for ENTER -> hero select (new game uses
; the same fixed seed, §6.5).
;------------------------------------------------------------------------------
end_screen:
                call scan_matrix
                call sample_input
                ld   a, (PLAYER_DISC)
                bit  DK_ENTER_BIT, a
                jp   z, play_loop
                jp   enter_select

;==============================================================================
; init_kbd_mirror — all released.  Clobbers: A, B, HL
;==============================================================================
init_kbd_mirror:
                ld   hl, KBD_MATRIX
                ld   b, KBD_MATRIX_LEN
                ld   a, KBD_RELEASED
.r:             ld   (hl), a
                inc  hl
                djnz .r
                ret

                INCLUDE "proto_io.asm"
                INCLUDE "proto_gfx.asm"
                INCLUDE "proto_logic.asm"
                INCLUDE "proto_anim.asm"
                INCLUDE "proto_data.asm"
                INCLUDE "../assets/gfx/bg_tiles.asm"

;==============================================================================
; kind_tab — page-aligned parallel byte arrays (KT_*), prototype §6.3.
;==============================================================================
                ALIGN 256
kind_tab:
                ;     KN  WZ  RG  SK  GB  GH  RT  BT  SL
                KROW   3,  3,  3,  3,  3,  3,  4,  3,  3          ; KT_BW (cells)
                KROW BH_K_KNIGHT, BH_K_WIZARD, BH_K_ROGUE, BH_K_SKELETON, BH_K_GOBLIN, BH_K_GHOST, BH_K_RAT, BH_K_BAT, BH_K_SLIME ; KT_BH
                KROW  22, 14, 18, 10,  6,  7,  3,  3,  5          ; KT_HP
                KROW   2,  3,  5,  2,  1,  2,  0,  1,  0          ; KT_ATK
                KROW   2,  1,  3,  2,  1,  3,  1,  4,  0          ; KT_EVA
                KROW   6,  6,  4,  4,  3,  4,  2,  2,  3          ; KT_DIE
                KROW   0,  1,  1,  0,  0,  0,  0,  0,  0          ; KT_BONUS
                KROW   1,  3,  1,  1,  1,  1,  1,  1,  1          ; KT_REACH
                KROW   1,  1,  1,  1,  1,  1,  1,  1,  2          ; KT_PERIOD
                KROW KF_HERO|KF_CLIMBER, KF_HERO|KF_CLIMBER|KF_ZAP, KF_HERO|KF_CLIMBER, KF_CLIMBER|KF_TALL, KF_CLIMBER, KF_FLYER, 0, KF_FLYER|KF_BAT, 0  ; KT_FLAGS
                KROW $47,$45,$44,$47,$44,$45,$06,$43,$44          ; KT_ATTR
                KROW KFID_KNIGHT, KFID_WIZARD, KFID_ROGUE, KFID_SKELETON, KFID_GOBLIN, KFID_GHOST, KFID_RAT, KFID_BAT, KFID_SLIME   ; KT_FID0
                KROW KFCNT_KNIGHT, KFCNT_WIZARD, KFCNT_ROGUE, KFCNT_SKELETON, KFCNT_GOBLIN, KFCNT_GHOST, KFCNT_RAT, KFCNT_BAT, KFCNT_SLIME ; KT_FCNT
                ASSERT $ - kind_tab == KT_MOD7
                DUP 24, n
                DB   n % 7                     ; KT_MOD7
                EDUP
                ASSERT $ - kind_tab == KT_DIV7
                DUP 24, n
                DB   n / 7                     ; KT_DIV7
                EDUP
                ASSERT $ - kind_tab == 256

code_end:
CODE_LEN        EQU code_end - start
                ASSERT code_end <= P_ENTITIES
                ASSERT FRT + FRT_MAX * FRT_STRIDE <= SLOTVARS
                ASSERT DMG_LIST + DMG_MAX * 4 <= PEND_DMG
                ASSERT LOWRAM_END <= $8000
                DISPLAY "PROTO image: $8000..", /H, code_end, " (", /D, CODE_LEN, " B), free to ENTITIES: ", /D, P_ENTITIES - code_end

;------------------------------------------------------------------------------
; tap_loader — 10 CLEAR VAL "24575": LOAD "" CODE: RANDOMIZE USR VAL "32768"
; CLEAR 24575 frees $6000..$7FFF for the room maps / generator buffers.
; Tokenised in a scratch ORG (page 0 at $E000; not part of the runtime image —
; bank 0 is overwritten by the pre-shift pool at boot).
;------------------------------------------------------------------------------
                ORG  $E000
tap_loader:
                DB   0, 10
                DW   tap_l10_end - tap_l10_body
tap_l10_body:   DB   $FD, $B0, '"', "24575", '"', $0D
tap_l10_end:
                DB   0, 20
                DW   tap_l20_end - tap_l20_body
tap_l20_body:   DB   $EF, $22, $22, $AF, $0D
tap_l20_end:
                DB   0, 30
                DW   tap_l30_end - tap_l30_body
tap_l30_body:   DB   $F9, $C0, $B0, '"', "32768", '"', $0D
tap_l30_end:
tap_loader_len  EQU  $ - tap_loader

;==============================================================================
; Artefacts. SAVETAP dumps device memory at this point in source order (see
; main.asm's note), so it comes after every byte is assembled. The sprite-source
; banks are saved by mapping each into slot 3 ($C000) in turn.
;==============================================================================
                EMPTYTAP "build/proto.tap"
                SAVETAP  "build/proto.tap", BASIC, "wazproto", tap_loader, tap_loader_len, 10
                SAVETAP  "build/proto.tap", CODE,  "wazproto", start, CODE_LEN
                MMU  3, BANK_SRC_LO
                SAVETAP  "build/proto.tap", HEADLESS, BANK_WINDOW, SRC_LEN_LO
    IF SRC_LEN_HI > 0
                MMU  3, BANK_SRC_HI
                SAVETAP  "build/proto.tap", HEADLESS, BANK_WINDOW, SRC_LEN_HI
    ENDIF
                MMU  3, 0
                SAVESNA  "build/proto.sna", boot
