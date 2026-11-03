;==============================================================================
; boot7.asm — MEM-SND: boot / new-game / level-start cold code moved out of
; bank 3 (its space went to the AY slot: AY_RESERVE lowered, SFX room).
; INCLUDEd by bank7.asm, so its rules hold here: entered only through far7
; (from low RAM, or nested from bank 3), no data, no SMC; every callee hands
; bank 7 back (copy_virt3 / far3 restore the caller's bank; stamp_rect,
; slot_act, KFIELD only read / write bank 2).
;   panel_init7  panel_init (bank 3, far7 per level): its bank-2-only half
;   new_game     start_game (far7): the per-game state, hero slot, seed
; 3E-T1: init_tiles / panel_boot (boot only) moved on to the boot block
; (boot6.asm, bank-6 pool tail: boot6_tiles).
; Cost of the move: panel_init's
; nested far7 ~0.3k T per level start; new_game's two nested far3 (+ a third
; on the PROTO path) ~0.5-0.8k T once per game. Nothing per tick.
;==============================================================================

;------------------------------------------------------------------------------
; panel_init7 — far7 from panel_init (bank 3): the bank-2-only half of the
; static panel: panel state reset (the *_SH "as drawn" bytes: $FF = never
; drawn; STAT_SH 0 = both status cells blank), every attr rect of rows 20-22
; (info fields, depth / level cells, HP / MP / FOOD bars, log row 22).
; (IC1: the quick-potion slot scan is gone: QS_SLOT0 + QS_POTION.)
; Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
panel_init7:
                ld   hl, HUD4_EXT              ; HUD4_EXT, HUD4_PW: rows blank, nothing pending
                ld   b, 2 * TEXT_ROWS
                xor  a
.z:             ld   (hl), a
                inc  l
                djnz .z
                ld   (LOG_QN), a
                ld   hl, LOG_Q
                ld   b, LOG_Q_LEN
.zq:            ld   (hl), a
                inc  l
                djnz .zq
                ld   (STAT_SH), a              ; D3-8 review: sig 0 = the blank cells this
                                               ; static panel has; a status carried over
                                               ; level_show then differs and redraws
                dec  a
                ld   (PANEL_HP_SH), a          ; $FF: never drawn -> PD_HP / PD_ICONS
                ld   (PANEL_HP_SH + 1), a
                ld   (PANEL_POT_SH), a
                ld   (PU_POS + 1), a           ; 3E-T11: FL_ROOM byte $FF = no cell: the
                                               ; first floor_pickup of a level has no span
                ld   (LVL_SH), a               ; level digit: never drawn
                ld   (ICON_SIG), a             ; (no real signature is $FF)
                ld   a, PD_HP | PD_MP | PD_ICONS | PD_DEPTH | PD_INFO | PD_FOOD   ; 3E-T9: FOOD bar + word
                ld   (PANEL_DIRTY), a
                ; C3-3: the icon bar is drawn by item_icons (icon_state vs
                ; ICON_SH): every slot "never drawn" -> slot_redraw each
                ld   hl, ICON_SH
                ld   b, ICON_SLOTS
                ld   a, IS_NONE
.ish:           ld   (hl), a
                inc  l
                djnz .ish
                ; info line fields (game.md §3.4): name chars 0-15, numbers 16-27,
                ; notes 28-41 = cols 0-11 / 12-20 / 21-31
                ld   a, ATTR_INFO_NAME
                ld   bc, INFO_ROW << 8
                ld   de, (INFO_NUM_COL << 8) | 1
                call stamp_rect
                ld   a, ATTR_INFO_NUM
                ld   bc, (INFO_ROW << 8) | INFO_NUM_COL
                ld   de, ((INFO_NOTE_COL - INFO_NUM_COL) << 8) | 1
                call stamp_rect
                ld   a, ATTR_INFO_NOTE
                ld   bc, (INFO_ROW << 8) | INFO_NOTE_COL
                ld   de, ((ROOM_COLS - INFO_NOTE_COL) << 8) | 1
                call stamp_rect
                ; depth cell row 19 (key icon until 3F: none) -> black
                ld   bc, ((ICON_ROW + 1) << 8) | DEPTH_COL
                ld   de, (2 << 8) | 1
                xor  a
                call stamp_rect
                ld   a, ATTR_LVL               ; C3-3: the level digit at (31, 19)
                ld   bc, ((ICON_ROW + 1) << 8) | LVL_COL
                ld   de, (1 << 8) | 1
                call stamp_rect
                ; row 21: bar frames' attrs (the labels' cells HP_LBL_COL /
                ; MP_LBL_COL / FOOD_LBL_COL are outside these rects: glyph8)
                ASSERT HP_LBL_COL < HP_BAR_COL && HP_NUM_COL + 2 <= MP_LBL_COL && MP_LBL_COL < MP_BAR_COL
                ASSERT MP_NUM_COL + 2 <= FOOD_LBL_COL && FOOD_LBL_COL < FOOD_BAR_COL && LOG_COLS <= GEAR_COL
                ld   a, ATTR_P_HP
                ld   bc, (STAT_ROW << 8) | HP_BAR_COL
                ld   de, ((HP_NUM_COL + 2 - HP_BAR_COL) << 8) | 1
                call stamp_rect
                ld   a, ATTR_P_MP
                ld   bc, (STAT_ROW << 8) | MP_BAR_COL
                ld   de, ((MP_NUM_COL + 2 - MP_BAR_COL) << 8) | 1
                call stamp_rect
                ld   a, ATTR_P_FED
                ld   bc, (STAT_ROW << 8) | FOOD_BAR_COL
                ld   de, ((GEAR_COL - FOOD_BAR_COL) << 8) | 1
                call stamp_rect
                ; row 22: log attrs (cols 0..LOG_COLS-1; the gear cells: pblit)
                ld   a, ATTR_LOG_OLD
                ld   bc, LOG_ROW << 8
                ld   de, (LOG_COLS << 8) | 1
                jp   stamp_rect

;==============================================================================
; NEW GAME (prototype §6.5: fixed gameplay RNG seed; all rooms, monsters,
; potions re-initialised). HERO_KIND already set. MEM-SND: bank 7 (far7 from
; start_game; was bank 3 since A7). Hero slot 0: kind, flags, HP; the start
; kit (kit_add, 3E-T11: WORN + BAG; E_POT follows the bag).
; B3B-12 / D3-11: proto_start = 1 (test path) no longer branches here: the
; PROTO fixture (src/proto_fix.asm, run by start_game's proto_hook) rewrites the
; level state and the slots after it. MASTER_SEED = SYS_FRAMES
; at the hero choice (game.md §1 "Seed"; seed_fixed = 1 forces seed_value)
; and nothing else — start_game's level_enter generates D1, populates it and
; ends with vis_reset. Clobbers: all but IY.
;==============================================================================
new_game:
                ld   hl, RNG_SEED
                ld   (RNG_STATE), hl
                ld   hl, 0
                ld   (TURN_COUNTER), hl
                ld   (TICK_COUNTER), hl        ; per-game test observables
    IF ANIM_TRACE_ON                          ; (OVERRUN_COUNT, GEN_OVERFLOW
                ld   hl, ANIM_TRACE            ; stay "since boot")
                ld   b, ANIM_TRACE_LEN         ; RECLAIM-D: a 10-B loop (was the 13-B LDIR)
.trc:           ld   (hl), $FF
                inc  l                         ; (one page: trace_log ASSERTs it)
                djnz .trc
    ENDIF
                xor  a
    IF ANIM_TRACE_ON
                ld   (ANIM_TRACE_IDX), a
    ENDIF
                ld   (BLIT_MISS), a
                ld   (DMG_OVERFLOW), a
                ld   (CLIP_TRAP), a
                ld   (CUR_ROOM), a
                ld   (TURN_PHASE), a
                ld   (NEED_RELEASE), a
                ld   hl, ITEM_RAM              ; 3E-T3: bag, worn,
                ld   b, ITEM_RAM_LEN           ; hunger, quick slots, M0 ST1_CNT := 0 (86 B, one page:
.ir:            ld   (hl), a                   ; 9 B, ~2.1k T; level changes keep it)
                inc  l
                djnz .ir
                ld   hl, level_reset_new      ; bank 3 (pf_prep is bank-3 data):
                call far3                      ; per-level state + the entity table (+ hero 3D state)
                ; --- hero, slot 0 ---
                ld   ix, P_ENTITIES
                ld   a, (HERO_KIND)
                ld   (ix+E_KIND), a
                ld   (ix+E_ROOM), ROOM_A
                ld   (ix+E_FLAGS), EF_ACTIVE | EF_PLAYER
                ld   (ix+E_X), HERO_START_COL
                KFL    KT_BH
                ld   b, a
                ld   a, HERO_START_S * STOREY_ROWS + STOREY_AIR
                sub  b                         ; 9s+8-h
                ld   (ix+E_Y), a
                ld   hl, init_ent_common       ; bank 3 (shared with spawn_one /
                call far3                      ; level_populate; IX passes in)
                call hero_st_init              ; C3-2 (intent7.asm, this bank)
                ld   hl, kit_add               ; 3E-T11: worn + bag start kit (R6;
                call far6                      ; E_POT = its potions via pot_sync)
                xor  a                         ; 3F-T9: the spawn queue is garbage at boot
                ld   (SPQ_K), a                ; (end_turn empties it after that)
                ld   hl, (seed_value)          ; (D3-11: a PROTO fixture game rewrites it)          ; generated: the master seed
                ld   a, (seed_fixed)
                or   a
                jr   nz, .ms
                ld   hl, (SYS_FRAMES)          ; frames since boot at the choice
                ld   de, (MENU_SPIN)           ; C3-6: + the menu's busy-wait count
                add  hl, de
                ld   a, r                      ; + R (B3B-12 review): little extra entropy
                xor  h                         ; (the select loop is HALT-synchronised),
                ld   h, a                      ; the 20 ms keypress frame is the real source
.ms:            ld   (MASTER_SEED), hl
                ret
