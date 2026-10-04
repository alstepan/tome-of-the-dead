;==============================================================================
; main.asm — WazHack/ZX: first playable fighting prototype.
;             Spec: docs/design/prototype.md (rev B, authoritative).
;
; Target : ZX Spectrum 128K.   Build:
;   tools/build.sh   (zx0_sources.py, then sjasmplus src/main.asm --fullpath
;                     --lst/--sld/--sym=build/wazhack.* -i src; fails on warnings)
;   -> build/wazhack.tap (BASIC loader + CODE lowram_code..code_end + 3
;      headerless blocks: bank 1 sources, bank 3 source tail + cold code,
;      bank 3 AY slot)
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
; Loop: 25 Hz tick (2 frames of SYS_FRAMES, bumped by the A8 IM 2 ISR). TURN_PHASE INPUT samples
; keys and resolves a whole turn instantly (player, then monsters in slot order,
; then pending materialise); TURN_PHASE ANIM replays it (tweens, attack /
; reaction / death sequences) until every queue is done (>= 2 ticks).
;==============================================================================

                DEVICE ZXSPECTRUM128

                INCLUDE "constants.asm"
                INCLUDE "defs.asm"

;==============================================================================
; SPRITE SOURCES — banks 1 and 3, assembled contiguously at virtual $8000..$FFFF
; (slot 2 = page 1, slot 3 = page 3). Read only by the boot generator via
; copy_virt (B3B-8: init_tiles no longer reads the raw items / tiles) (virtual < $C000 -> bank 1 at +$4000, else bank 3
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
; B3B-11b (bank-3 relief): boot / new-game cold DATA, read only through
; copy_virt / copy_virt3 (virtual address -> bank 1 or 3), right after the
; sources: bank 1 with ZX0 sources; the raw build's sources fill bank 1, so
; there it lands in the bank-3 tail (as before B3B-11b). Same tape blocks.
vdata:
                INCLUDE "../assets/gfx/fonts/font6x8.asm"     ; -> FONT6 planes (panel_boot)
                INCLUDE "../assets/gfx/panel/panel_icons.asm" ; panel_init (pblit via GEN_SRC)
                INCLUDE "panel_hot.asm"                       ; -> HOT_COPY (panel_boot)
                INCLUDE "../assets/gfx/tiles/tiles_common.asm" ; init_tiles (boot)
                INCLUDE "../assets/gfx/panel/panel_orn.asm"    ; init_tiles -> ORN_GLYPHS
                MODULE b3fx                                    ; init_tiles: the zap tiles
                INCLUDE "../assets/gfx/sprites/tiles_fx.asm"   ; (labels also in sprite_src)
                ENDMODULE
vdata_end:
VDATA_LEN       EQU vdata_end - vdata
VIRT_TOTAL      EQU vdata_end - sprite_src
    IF VIRT_TOTAL > $4000
SRC_LEN_LO      EQU $4000
    ELSE
SRC_LEN_LO      EQU VIRT_TOTAL
    ENDIF
SRC_LEN_HI      EQU VIRT_TOTAL - SRC_LEN_LO
                ASSERT VIRT_TOTAL <= $8000
                DISPLAY "GAME sprite sources: ", /D, SRC_TOTAL, " B + vdata ", /D, VDATA_LEN, " B (bank1 ", /D, SRC_LEN_LO, ", free ", /D, $4000 - SRC_LEN_LO, "; bank3 ", /D, SRC_LEN_HI, ")"
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
; AY PLAYER SLOT (A8) — bank 3 AY_RESERVE..$FFFF (7 KB): called by the IM 2
; ISR once per frame (ay.asm: silent stub for now). Own headerless tape block.
;==============================================================================
                ORG  AY_RESERVE
ay_code:
                INCLUDE "ay.asm"
ay_code_end:
AY_LEN          EQU ay_code_end - AY_RESERVE
                ASSERT ay_code_end <= AY_RESERVE_END
                DISPLAY "GAME AY slot (bank 3): ", /H, AY_RESERVE, "..", /H, ay_code_end - 1, " (", /D, AY_LEN, " B), free in the 7 KB reserve: ", /D, AY_RESERVE_END - ay_code_end, "; ISR ", /D, ISR_LEN, " B at ", /H, ISR_ADDR

;==============================================================================
; LEVEL TILESETS (B3B-8) — the 8 per-level tile sets (tools/tiles_convert.py,
; slot format TSET_* in level_defs.asm) in the bank-7 spare: slots 0-3 above
; screen 2 (TSET_LO), 4-7 above the shadow attrs (TSET_HI; TSET_SPLIT, a
; macro the generated file invokes between D4 and D5). Two headerless tape
; blocks (`start` .t7lo / .t7hi); level_load_tiles copies one slot per level.
;==============================================================================
                MMU  3, BANK_TSET
    MACRO TSET_SPLIT
tsets_lo_end:
                ORG  TSET_HI
    ENDM
                ORG  TSET_LO
                INCLUDE "../assets/gfx/tiles/tilesets.asm"
                ASSERT tileset_d1 == TSET_LO && tileset_d5 == TSET_HI
                ASSERT tileset_d2 - tileset_d1 == TSET_STRIDE && TILESET_SLOT_LEN == TSET_STRIDE
                ASSERT tsets_lo_end == TSET_LO + TSET_HALF_LEN && tilesets_end == TSET_HI + TSET_HALF_LEN
                ASSERT tsets_lo_end <= SHADOW_BITMAP && tilesets_end <= $10000

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
                ; B3B-10: animated decor. After this tick's render (the drawn
                ; footprints R_COL..R_ROWS it tests are render's; anim_tick only
                ; rewrites R_VIS / R_FID) and, with RENDER_FIRST, after the turn
                ; logic: a heavy input tick is then usually in its 2nd frame,
                ; where decor_tick holds (it never lengthens such a tick)
                call decor_tick
                ; B3B-11 (D5, user 2026-10-03): one panel item per tick, in ANIM
                ; ticks >= 1 and idle ticks, never in a turn's input tick (TURN_PHASE
                ; = ANIM with TURN_TICK still 0: read_turn_input just started it)
                ld   a, (TURN_PHASE)
                or   a
                jr   z, .panel
                ld   a, (TURN_TICK)
                or   a
                jr   z, panel_done
.panel:         call panel_tick
panel_done:                                    ; test probe (no code): panel item done
                ld   a, (TURN_PHASE)
                or   a
                jr   z, play_loop
                ld   hl, TURN_TICK
                inc  (hl)
                call turn_done
                call c, end_turn
                jr   play_loop

;------------------------------------------------------------------------------
; wait_tick — pace to 2 frames per tick (SYS_FRAMES: the A8 IM 2 ISR bumps it at
; every frame start, like the ROM IM1 ISR did). Arriving with >= 2 frames already gone
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
                ld   (LOCK_SHOWN), a           ; B3B-5: next bump may print again
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
                ld   hl, resolve_monsters      ; B3B-R2: bank 3, one far3 a turn
                call z, far3                   ; exit turn: monsters don't act
                ld   a, TP_ANIM
                ld   (TURN_PHASE), a
                xor  a
                ld   (TURN_TICK), a
                ret

;------------------------------------------------------------------------------
; end_turn — ANIM finished: transition (if exiting), TURN_COUNTER++, potion
; pickup, death / win checks (B3B-11: messages via log_push), back to INPUT.  Clobbers: all but IY.
;------------------------------------------------------------------------------
end_turn:
                ld   a, (EXIT_KIND)
                or   a
                call nz, do_exit
                ld   hl, (TURN_COUNTER)
                inc  hl
                ld   (TURN_COUNTER), hl
                ld   hl, potion_pickup         ; B3B-R2: bank 3 (B3B-11: HP / potions
                call far3                      ; reach the panel by
                xor  a                         ; panel_tick's poll, not from here)
                ld   (TURN_PHASE), a
                ld   a, (P_ENTITIES + E_FLAGS)
                and  EF_DYING
                jr   z, .alive
                ld   a, GS_DEAD
                ld   (GAME_STATE), a
                ld   hl, str_died
                jp   log_push_end              ; never dropped (B3B-11b); end_screen drains it
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
                ld   hl, str_win
                jp   log_push_end

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
                call build_room                ; B3B-8: far3 -> bank-3 build_room_map v2
                ld   a, (EXIT_KIND)            ; scroll arg: the exit direction
                ld   hl, hscroll_room          ; both scrolls live in bank 3
                cp   EX_UP
                jr   c, .h
                ld   hl, vscroll_room
.h:             call far3
                call room_shadow               ; clean background of the new room + its
                                               ; row-17 ornament (the scroll drew the screen's)
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
                ld   a, FLOOR_ROW1             ; up: stand on the bottom storey (9s+8-h, s 1)
                jr   z, .vy
                ld   a, FLOOR_ROW0             ; down: stand on storey 0
.vy:            sub  b
                ld   (ix+E_Y), a
.pos:           call snap_pxpy
                ld   (ix+E_MODE), M_REST
                ld   hl, arrival_conflicts     ; bank 3 (cold)
                call far3
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
                call panel_tick                ; B3B-11: the death / win line, HP 0
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
                INCLUDE "panel2.asm"            ; B3B-11 panel engine, bank-2 part
                INCLUDE "decor.asm"             ; B3B-10 animated decor (decor_tick)
    IF !ZX0_SOURCES
                ; B3B-R2: the raw A/B build (ZX0_SOURCES=0, tests/zx0_pool.py)
                ; has only ~675 B left in bank 3 (the raw sprite tail + vdata
                ; take 2,942 B there), so its turn3.asm stays in bank 2 as before
                ; R2. far3 into a bank-2 target works unchanged (it only pages
                ; bank 3 around the call); the shipping build has it in bank 3.
                INCLUDE "turn3.asm"
    ENDIF

;==============================================================================
; kind_tab — page-aligned parallel byte arrays (KT_*), prototype §6.3. A6: two
; pages, K_MAX (32) B per array; no array crosses a page (KFIELD, feet_mod).
;==============================================================================
kind_tab_pad:                                  ; ALIGN padding starts here (headroom)
                DS   (-($ + TILE_IDS + DT_ATTR_LEN)) & $FF, 0    ; B3B-5: tile_flags ends on the page
;------------------------------------------------------------------------------
; dt_attr_tab — B3B-10 decor_tick attr cycles, 8 steps per kind (concept-screen
; §3.3): kind 1 flame (DT_HOT -> DT_RED -> DT_DIM: small / tall torch bodies),
; kind 2 candle (8-step flicker). Whole attr bytes: they override the cell's
; paper (black on every cycled cell, see decor.asm DT_HOT). In the pad below
; tile_flags: never crosses a page.
;------------------------------------------------------------------------------
dt_attr_tab:
                DB   DT_HOT, DT_RED, DT_DIM, DT_HOT, DT_RED, DT_DIM, DT_HOT, DT_RED   ; 1 flame
                DB   DT_HOT, DT_HOT, DT_DIM, DT_HOT, DT_RED, DT_HOT, DT_HOT, DT_DIM   ; 2 candle
DT_ATTR_LEN     EQU  DT_KINDS * 8
                ASSERT $ - dt_attr_tab == DT_ATTR_LEN && (dt_attr_tab >> 8) == (($ - 1) >> 8)
;------------------------------------------------------------------------------
; tile_flags — TILE_FLAGS[64] (D2, level_defs.asm TF_*), static, by tile id;
; the 64 B right below kind_tab (low byte $C0: cell_blocked adds the id with
; no carry, H constant). Placed in the ALIGN pad, so it costs no bank-2 bytes
; beyond its 64. Per-level ids 32..59 = 0 (decor), 60..63 = lectern / Book
; until the first level_load_tiles (B3B-8) overwrites 32..63 from the slot.
; Solidity belongs to the cell class (game.md §1.2 "Solidity of decor",
; designer 2026-10-03): the wall set (DARK = T_BRICK, DITHER, PATCH, FADE) is
; SOLID and only ever replaces wall cells; rubble / skulls / moss / cobweb /
; chain / torch / candles / drips are not. Per-level wall variants (pillar,
; plaster patches in 32..59) carry TF_SOLID in their tileset slot's flags.
;------------------------------------------------------------------------------
tile_flags:
                DB 0                                   ;  0 T_AIR
                DB TF_FLOOR                            ;  1 T_PLAT
                DB TF_SOLID                            ;  2 T_BRICK (wall, lintel, block)
                DB TF_SOLID | TF_FLOOR                 ;  3 T_WALLF
                DB TF_LADDER, TF_LADDER, TF_LADDER     ;  4-6 T_LAD_L/M/R
                DB TF_LADDER | TF_HOLE, TF_LADDER | TF_HOLE, TF_LADDER | TF_HOLE ; 7-9 T_HOLE_*
                DB 0                                   ; 10 T_POTION (floor item)
                DB 0, 0, 0, 0                          ; 11 / 14 door jambs (open door), 12-13 chain, skulls
                DB TF_ANIM, TF_ANIM                    ; 15-16 T_TORCH_T/B
                DB TF_ANIM, TF_ANIM                    ; 17-18 T_DRIP1/2 (PROTO zap: overlay only)
                DB TF_FLOOR, TF_FLOOR                  ; 19-20 T_END_L/R = pit caps
                DB TF_SOLID, TF_SOLID                  ; 21-22 T_DOOR_ARCH_L/R
                DB TF_SOLID | TF_DOOR, TF_SOLID | TF_DOOR   ; 23-24 T_DOOR_L/R (closed planks)
                DB TF_SOLID | TF_DOOR | TF_LOCK        ; 25 T_DOOR_LOCK
                DB TF_FLOOR                            ; 26 T_GRATE (closed)
                DB 0                                   ; 27 T_RUBBLE (decor at a block's foot)
                DB TF_SOLID, TF_SOLID, TF_SOLID        ; 28-30 wall set DITHER / PATCH / FADE
                DB TF_ANIM                             ; 31 T_CANDLES
                DS T_LVL_OBJ - TILE_COMMON, 0          ; 32-59 per-level decor
                DS T_LVL_OBJ_N, TF_SOLID | TF_ATTACK   ; 60-63 lectern / Book
                ASSERT $ - tile_flags == TILE_IDS
                ASSERT (tile_flags & $FF) + TILE_IDS == $100     ; one page, ends on it
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
                ; B3B-5: skeleton + goblin are openers (game.md §9.1); the heroes
                ; open by bump in try_horizontal, not through KF_OPENER
                KROW KF_HERO|KF_CLIMBER, KF_HERO|KF_CLIMBER|KF_ZAP, KF_HERO|KF_CLIMBER, KF_CLIMBER|KF_TALL|KF_OPENER, KF_CLIMBER|KF_OPENER, KF_FLYER, 0, KF_FLYER|KF_BAT, 0  ; KT_FLAGS
                KROW $47,$45,$44,$47,$44,$45,$06,$43,$44          ; KT_ATTR
                KROW KFID_KNIGHT, KFID_WIZARD, 0, KFID_SKELETON, KFID_GOBLIN, KFID_GHOST, KFID_RAT, KFID_BAT, KFID_SLIME   ; KT_FID0
                KROW KFCNT_KNIGHT, KFCNT_WIZARD, 0, KFCNT_SKELETON, KFCNT_GOBLIN, KFCNT_GHOST, KFCNT_RAT, KFCNT_BAT, KFCNT_SLIME ; KT_FCNT
                ASSERT $ - kind_tab == KT_MOD9
                ; walker height (B3B-5 lead_cell, logic.asm): a non-flyer body
                ; never reaches a door's arch / lintel rows. Reads the bytes
                ; just assembled ({b}), so it covers every kind automatically.
                DUP K_COUNT, n
                ASSERT ({b kind_tab + KT_FLAGS + n} & KF_FLYER) || ({b kind_tab + KT_BH + n} <= STOREY_AIR - DOOR_PLANK_DY)
                EDUP
                ASSERT (KT_MOD9 >> 8) == ((KT_DIV9 + 23) >> 8)    ; feet_mod: one H for both
                ASSERT (KT_FID0 >> 8) == (KT_FCNT >> 8)            ; gen_kind: one H for both
                DUP 24, n
                DB   n % STOREY_ROWS           ; KT_MOD9
                EDUP
                ASSERT $ - kind_tab == KT_DIV9
                DUP 24, n
                DB   n / STOREY_ROWS           ; KT_DIV9
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
                DISPLAY "GAME image: $8000..", /H, code_end, " (", /D, IMAGE_LEN, " B), free to FRT: ", /D, FRT - code_end, " (+", /D, dt_attr_tab - kind_tab_pad, " B kind_tab ALIGN pad); HOT_COPY ", /H, HOT_COPY, ".. ", /D, PANEL_HOT_LEN, " B of ", /D, HOT_COPY_END - HOT_COPY, ", spare ", /D, HOT_COPY_END - HOT_COPY - PANEL_HOT_LEN

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
                SAVETAP  "build/wazhack.tap", HEADLESS, AY_RESERVE, AY_LEN   ; A8 AY slot (BANK_AY = 3)
                MMU  3, BANK_TSET              ; B3B-8: level tilesets (2 x 1,280 B)
                SAVETAP  "build/wazhack.tap", HEADLESS, TSET_LO, TSET_HALF_LEN
                SAVETAP  "build/wazhack.tap", HEADLESS, TSET_HI, TSET_HALF_LEN
                MMU  3, 0
                SAVESNA  "build/wazhack.sna", boot
