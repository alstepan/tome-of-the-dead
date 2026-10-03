;==============================================================================
; main.asm — WazHack/ZX: first playable fighting prototype.
;             Spec: docs/design/prototype.md (rev B, authoritative).
;
; Target : ZX Spectrum 128K.   Build:
;   tools/build.sh   (zx0_sources.py, then sjasmplus src/main.asm --fullpath
;                     --lst/--sld/--sym=build/wazhack.* -i src; fails on warnings)
;   -> build/wazhack.tap (BASIC loader + CODE lowram_code..code_end + 2
;      headerless blocks: bank 1 sources, bank 3 source tail + cold code)
;   -> build/wazhack.sna (128K snapshot; entry = boot, all banks preloaded)
;
; Memory (docs/memory-map.md "PROTO"): HOT code+tables $8000..(< FRT, bank
; 2); frame runtime table FRT $A600..$AFFF; runtime entity/render tables
; $B000..$BAFF; stack $BB00..$BEFF; state block $BF00..$BFFF; room maps, tiles
; + generator buffers $6000..$6D3F and the COLD block lowram_code..$7FFF (bank
; 5: boot, generator, game start, frame descriptors);
; COLD paged code in bank 3 after the source tail (select, transition scrolls,
; via far3); unshifted sprite SOURCES in banks 1/3 (assembled at virtual
; $8000..$FFFF); mirrored + pre-shifted sprite POOL generated at boot into
; banks 0/4/6.
;
; Loop: 25 Hz tick (2 frames, ROM IM1 FRAMES counter). TURN_PHASE INPUT samples
; keys and resolves a whole turn instantly (player, then monsters in slot order,
; then pending materialise); TURN_PHASE ANIM replays it (tweens, attack /
; reaction / death sequences) until every queue is done (>= 2 ticks).
;==============================================================================

                DEVICE ZXSPECTRUM128

                INCLUDE "constants.asm"
                INCLUDE "defs.asm"

;==============================================================================
; SPRITE SOURCES — banks 1 and 3, assembled contiguously at virtual $8000..$FFFF
; (slot 2 = page 1, slot 3 = page 3). Read only by the boot generator (and
; init_tiles) via copy_virt (virtual < $C000 -> bank 1 at +$4000, else bank 3
; as-is). ZX0_SOURCES = 1 (default): the generator frames are ZX0 blocks
; (build/zx0/sprites_zx0.asm, written by tools/zx0_sources.py — tools/build.sh
; runs it); their per-frame block/offset are EQUs folded into the bank-5
; fdesc_tab (A6); items/tiles stay raw.
; ZX0_SOURCES = 0: the raw index.asm, as before A5 (A/B, tests/zx0_pool.py).
;==============================================================================
                MMU  2, BANK_SRC_LO
                MMU  3, BANK_SRC_HI
                ORG  SRC_VIRT_BASE
sprite_src:
    IF ZX0_SOURCES
                INCLUDE "../build/zx0/sprites_zx0.asm"
    ELSE
                INCLUDE "../assets/gfx/sprites/index.asm"
    ENDIF
sprite_src_end:
SRC_TOTAL       EQU sprite_src_end - sprite_src
    IF SRC_TOTAL > $4000
SRC_LEN_LO      EQU $4000
    ELSE
SRC_LEN_LO      EQU SRC_TOTAL
    ENDIF
SRC_LEN_HI      EQU SRC_TOTAL - SRC_LEN_LO
                ASSERT SRC_TOTAL <= $8000
                DISPLAY "GAME sprite sources: ", /D, SRC_TOTAL, " B (bank1 ", /D, SRC_LEN_LO, ", bank3 ", /D, SRC_LEN_HI, ")"
    IF ZX0_SOURCES
                DISPLAY "GAME ZX0 sources: ", /D, ZX0_FRAMES, " frames in ", /D, ZX0_BLOCKS, " blocks, ", /D, ZX0_PACKED_RAW, " -> ", /D, ZX0_PACKED_TOTAL, " B packed; total ", /D, SRC_TOTAL, " vs raw ", /D, ZX0_RAW_SRC_TOTAL, ": freed ", /D, ZX0_RAW_SRC_TOTAL - SRC_TOTAL, " B"
    ENDIF


;==============================================================================
; BANK-3 COLD CODE — hero select + transition scrolls (bank3.asm), assembled
; straight after the source tail in bank 3 (never below $C000), ending below
; the AY reserve. Loaded by the bank-3 tape block (BANK3_LEN from $C000).
;==============================================================================
    IF $ < BANK_WINDOW
                ORG  BANK_WINDOW               ; sources all in bank 1
    ENDIF
bank3_code:
                INCLUDE "bank3.asm"
bank3_end:
BANK3_LEN       EQU bank3_end - BANK_WINDOW
BANK3_CODE_LEN  EQU bank3_end - bank3_code
                ASSERT bank3_end <= AY_RESERVE
                DISPLAY "GAME bank-3 cold code: ", /H, bank3_code, "..", /H, bank3_end - 1, " (", /D, BANK3_CODE_LEN, " B), free to AY reserve: ", /D, AY_RESERVE - bank3_end

;==============================================================================
; BANK-5 LOW-RAM COLD CODE — tape entry, boot, generator, init_tiles, game
; start (lowram.asm). ORGed so it ends exactly at $8000 (no ALIGN inside, so
; its size does not depend on its base): contiguous with the bank-2 image.
;==============================================================================
                MMU  1, 5
                ORG  $8000 - (lowram_code_end - lowram_code)
lowram_code:                                   ; = start (ASSERTed): the USR target
                INCLUDE "lowram.asm"
lowram_code_end:
LOWRAM_CODE_LEN EQU lowram_code_end - lowram_code
                ASSERT lowram_code_end == $8000
                ; the descriptors are the tail of the cold block: room for the
                ; remaining FRT_MAX - FDESC_COUNT ones is kept free below it
FDESC_GROW      EQU (FRT_MAX - FDESC_COUNT) * FDESC_STRIDE
LOWRAM_SPARE    EQU lowram_code - ZX0_RESERVE - FDESC_GROW - LOWRAM_FREE_END
                ASSERT lowram_code - ZX0_RESERVE - FDESC_GROW >= LOWRAM_FREE_END
                ASSERT fdesc_end == lowram_code_end
                ASSERT GEN_SCRATCH + GEN_SCRATCH_LEN <= TILE_GLYPHS  ; the lowest buffer above the alias
                ASSERT GEN_SCRATCH + GEN_SCRATCH_LEN <= BITREV_TAB
                ASSERT (TILE_GLYPHS & $1FF) == 0                    ; tile_rect glyph addressing
                ASSERT (TILE_ATTRS & $FF) + TILE_IDS <= 256          ; one page
                DISPLAY "GAME low-RAM cold block: ", /H, lowram_code, "..0x7FFF (", /D, LOWRAM_CODE_LEN, " B = code ", /D, fdesc_tab - lowram_code, " + ", /D, FDESC_COUNT, " frame descriptors ", /D, fdesc_end - fdesc_tab, " B); spare after the descriptor growth reserve (", /D, FDESC_GROW, " B): ", /D, LOWRAM_SPARE

;==============================================================================
; MAIN IMAGE — bank 2 at $8000. Hot code + tables only.
;==============================================================================
                MMU  2, 2
                MMU  3, 0
                ORG  $8000
image_start:


;==============================================================================
; play_loop — one 25 Hz tick per iteration (prototype §3.2).
; A7 double buffer (option A): bank 7 is displayed during play; render composes
; in bank 5 and pmark_dmg marks the cells it changed. The NEXT tick starts with
; present, right after the HALT: it copies everything marked during the
; previous tick (render + HUD / messages of the turn logic) top to bottom while
; the beam is still in the top border, so it stays ahead of the beam (no tear)
; and runs mostly uncontended. Cost: +1 tick display latency (user, A7).
; At probe_presented bank 7 == bank 5 (tests/flicker.py asserts it per tick).
;==============================================================================
play_loop:
                call wait_tick
tick_work:                                     ; budget probe: tick work starts here
                call present                   ; A7: last tick's changes -> bank 7
probe_presented:                               ; test probe (no code): bank 7 == bank 5
                ld   hl, (TICK_COUNTER)
                inc  hl
                ld   (TICK_COUNTER), hl
                ld   a, (GAME_STATE)
                cp   GS_PLAYING
                jp   nz, end_screen
    IF RENDER_FIRST
                ; E0 experiment: draw right after the HALT sync, so the erase->draw
                ; window of every sprite sits at a fixed early point of the frame
                ; (beam is still in the top border/first rows) instead of wherever
                ; input+anim happened to end. Costs one tick of display latency.
                call render
                call pmark_dmg                 ; A7: presented at the next tick start
probe_render_done:
                ld   a, (TURN_PHASE)
                or   a
                call z, read_turn_input        ; INPUT: maybe start a turn
                call anim_tick
    ELSE
                ld   a, (TURN_PHASE)
                or   a
                call z, read_turn_input        ; INPUT: maybe start a turn
                call anim_tick
                call render
                call pmark_dmg
probe_render_done:
    ENDIF
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
; arrival, arrival conflicts. A7: shows bank 5 for the scroll (bank-3 code
; scrolls $4000), then present_full copies it to bank 7 and shows bank 7.
; Clobbers: all but IY.
;------------------------------------------------------------------------------
do_exit:
                ld   hl, follow_select         ; bank 3 (cold)
                call far3
                call hide_sprites              ; every sprite hidden, hero too
                call show_bank5                ; A7: the scroll runs on the $4000 screen
                ld   a, GS_TRANSITION          ; (state flips once none is drawn)
                ld   (GAME_STATE), a
                ld   h, NEXT_MAP >> 8
                ld   a, (EXIT_DEST)
                call build_room_map
                ld   a, (EXIT_KIND)            ; scroll arg: the exit direction
                ld   hl, hscroll_room          ; both scrolls live in bank 3
                cp   EX_UP
                jr   c, .h
                ld   hl, vscroll_room
.h:             call far3
                call shadow_room               ; clean background of the new room
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
                ld   hl, arrival_conflicts     ; bank 3 (cold)
                call far3
                call hud_room
                call vis_room_sync             ; B7: no old-room sprite in the next render
                call present_full              ; A7: bank 5 -> 7 (6,912 B), show bank 7
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
                ; ENTER: fall through into enter_select

;==============================================================================
; enter_select — hero select (bank 3: sel_run via far3), then start_game (bank
; 5 low RAM) with C = the chosen kind. Reached by jp only (boot, end_screen),
; so the stack is at its base level here.
;==============================================================================
enter_select:
                call show_bank5                ; A7: select draws on (and shows) bank 5
                ld   hl, sel_run
                call far3                      ; C = hero kind
                jp   start_game


                INCLUDE "io.asm"
                INCLUDE "gfx.asm"
                INCLUDE "logic.asm"
                INCLUDE "anim.asm"
                INCLUDE "data.asm"

;==============================================================================
; kind_tab — page-aligned parallel byte arrays (KT_*), prototype §6.3. A6: two
; pages, K_MAX (32) B per array; no array crosses a page (KFIELD, feet_mod).
;==============================================================================
kind_tab_pad:                                  ; ALIGN padding starts here (headroom)
                ALIGN 256
kind_tab:
                ASSERT K_COUNT <= K_MAX            ; A6 review: every kind has a column
                ASSERT K_COUNT <= KROW_W           ; ... and KROW emits it (widen KROW first)
                ;     KN  WZ  RG  SK  GB  GH  RT  BT  SL
                KROW   3,  3,  3,  3,  3,  3,  4,  3,  3          ; KT_BW (cells)
                KROW BH_K_KNIGHT, BH_K_WIZARD, 0, BH_K_SKELETON, BH_K_GOBLIN, BH_K_GHOST, BH_K_RAT, BH_K_BAT, BH_K_SLIME ; KT_BH
                KROW  22, 14, 18, 10,  6,  7,  3,  3,  5          ; KT_HP
                KROW   2,  3,  5,  2,  1,  2,  0,  1,  0          ; KT_ATK
                KROW   2,  1,  3,  2,  1,  3,  1,  4,  0          ; KT_EVA
                KROW   6,  6,  4,  4,  3,  4,  2,  2,  3          ; KT_DIE
                KROW   0,  1,  1,  0,  0,  0,  0,  0,  0          ; KT_BONUS
                KROW   1,  3,  1,  1,  1,  1,  1,  1,  1          ; KT_REACH
                KROW   1,  1,  1,  1,  1,  1,  1,  1,  2          ; KT_PERIOD
                KROW KF_HERO|KF_CLIMBER, KF_HERO|KF_CLIMBER|KF_ZAP, KF_HERO|KF_CLIMBER, KF_CLIMBER|KF_TALL, KF_CLIMBER, KF_FLYER, 0, KF_FLYER|KF_BAT, 0  ; KT_FLAGS
                KROW $47,$45,$44,$47,$44,$45,$06,$43,$44          ; KT_ATTR
                KROW KFID_KNIGHT, KFID_WIZARD, 0, KFID_SKELETON, KFID_GOBLIN, KFID_GHOST, KFID_RAT, KFID_BAT, KFID_SLIME   ; KT_FID0
                KROW KFCNT_KNIGHT, KFCNT_WIZARD, 0, KFCNT_SKELETON, KFCNT_GOBLIN, KFCNT_GHOST, KFCNT_RAT, KFCNT_BAT, KFCNT_SLIME ; KT_FCNT
                ASSERT $ - kind_tab == KT_MOD7
                ASSERT (KT_MOD7 >> 8) == ((KT_DIV7 + 23) >> 8)    ; feet_mod: one H for both
                ASSERT (KT_FID0 >> 8) == (KT_FCNT >> 8)            ; gen_kind: one H for both
                DUP 24, n
                DB   n % 7                     ; KT_MOD7
                EDUP
                ASSERT $ - kind_tab == KT_DIV7
                DUP 24, n
                DB   n / 7                     ; KT_DIV7
                EDUP
                ASSERT $ - kind_tab == KT_END
                ASSERT KT_END <= KT_SIZE           ; $1D0..$1FF spare (resistances, 3F)

code_end:
IMAGE_LEN       EQU code_end - image_start
TAPE_CODE_LEN   EQU code_end - lowram_code     ; one CODE block: low-RAM cold + bank 2
                ASSERT start == lowram_code    ; USR target = first byte of the block
                ASSERT FDESC_COUNT == FID_COUNT    ; fdesc_tab and frame_tab: same frames
                ASSERT image_start == $8000
                ASSERT code_end <= FRT         ; the image ends below the frame runtime table
                ASSERT FRT + FRT_MAX * FRT_STRIDE <= P_ENTITIES
                ASSERT P_ENTITIES + P_MAX_ENT * P_ENT_STRIDE <= BANK2_FREE
                ASSERT DMG_LIST + DMG_MAX * 4 <= PEND_DMG
                ASSERT LOWRAM_END <= LOWRAM_FREE_END
                ASSERT lowram_code > TAPE_CLEAR    ; above the loader's RAMTOP
                DISPLAY "GAME image: $8000..", /H, code_end, " (", /D, IMAGE_LEN, " B), free to FRT: ", /D, FRT - code_end, " (+", /D, kind_tab - kind_tab_pad, " B kind_tab ALIGN pad); free runtime RAM ", /H, BANK2_FREE, "..", /H, BANK2_FREE_END - 1, ": ", /D, BANK2_FREE_END - BANK2_FREE

;------------------------------------------------------------------------------
; tap_loader — 10 CLEAR VAL "24575": LOAD "" CODE: RANDOMIZE USR VAL "<start>"
; CLEAR 24575 frees $6000..$7FFF for the room maps / generator buffers and the
; low-RAM cold code. The USR address is emitted as 5 ASCII digits of `start`.
; Tokenised in a scratch ORG (page 0 at $E000; not part of the runtime image —
; bank 0 is overwritten by the pre-shift pool at boot).
;------------------------------------------------------------------------------
TAPE_CLEAR      EQU 24575
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
tap_l30_body:   DB   $F9, $C0, $B0, '"'
                DB   '0' + (start / 10000) % 10, '0' + (start / 1000) % 10
                DB   '0' + (start / 100) % 10, '0' + (start / 10) % 10, '0' + start % 10
                DB   '"', $0D
tap_l30_end:
tap_loader_len  EQU  $ - tap_loader

;==============================================================================
; Artefacts. SAVETAP dumps device memory at this point in source order (see
; main.asm's note), so it comes after every byte is assembled. Slot 1 = page 5
; and slot 2 = page 2 here, so the CODE block spans low-RAM cold + bank 2. The
; banked blocks are saved by mapping each bank into slot 3 ($C000) in turn.
;==============================================================================
                EMPTYTAP "build/wazhack.tap"
                SAVETAP  "build/wazhack.tap", BASIC, "wazhack", tap_loader, tap_loader_len, 10
                SAVETAP  "build/wazhack.tap", CODE,  "wazhack", lowram_code, TAPE_CODE_LEN
                MMU  3, BANK_SRC_LO
                SAVETAP  "build/wazhack.tap", HEADLESS, BANK_WINDOW, SRC_LEN_LO
                MMU  3, BANK_COLD3             ; source tail + bank-3 cold code
                SAVETAP  "build/wazhack.tap", HEADLESS, BANK_WINDOW, BANK3_LEN
                MMU  3, 0
                SAVESNA  "build/wazhack.sna", boot
