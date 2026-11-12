;==============================================================================
; boot7.asm — MEM-SND: boot / new-game / level-start cold code moved out of
; bank 3 (its space went to the AY slot: AY_RESERVE lowered, SFX room).
; INCLUDEd by bank7.asm, so its rules hold here: entered only through far7
; (from low RAM, or nested from bank 3), no data, no SMC; every callee hands
; bank 7 back (copy_virt3 / far3 restore the caller's bank; stamp_rect,
; slot_act, KFIELD only read / write bank 2).
;   panel_init7  panel_init (bank 3, far7 per level): its bank-2-only half
;   (new_game: B0CODE -> bank 0, src/newgame0.asm)
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
                ld   hl, HUD4_EXT              ; HUD4_EXT, HUD4_PW, LOG_QN, PANEL_POT_SH (set below), P_NUMBUF
                ld   b, P_NUMBUF + 3 - HUD4_EXT ; (scratch) zeroed in one run: rows blank, nothing pending
                xor  a
.z:             ld   (hl), a
                inc  l
                djnz .z
                inc  l                         ; FIRE_LOCK ($BFDF) lives across levels
                ld   b, LOG_Q_LEN
.zq:            ld   (hl), a
                inc  l
                djnz .zq
                ld   (STAT_SH), a              ; D3-8 review: sig 0 = the blank cells this
                                               ; static panel has; a status carried over
                                               ; level_show then differs and redraws
                dec  a
                ld   h, a
                ld   l, a                      ; HL = $FFFF: the word stores below are -1 B each pair
                ld   (PANEL_HP_SH), hl         ; $FF: never drawn -> PD_HP / PD_ICONS (+ the next byte)
                ld   (PANEL_POT_SH), a
                ld   (PU_POS + 1), a           ; 3E-T11: FL_ROOM byte $FF = no cell: the
                                               ; first floor_pickup of a level has no span
                ld   (LVL_SH), hl              ; level digit: never drawn; ICON_SIG (no real
                                               ; signature is $FF)
                ASSERT ICON_SIG == LVL_SH + 1
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
                ; the attr rects of rows 18-22 (pi_rects, data7.asm: attr, col, row, cols; 1 row each)
                ld   hl, pi_rects
.r:             ld   a, (hl)
                inc  hl
                cp   $FF                       ; table end (the last panel_init7 step: ret z)
                ret  z
                ld   c, (hl)
                inc  hl
                ld   b, (hl)
                inc  hl
                ld   d, (hl)
                inc  hl
                ld   e, 1
                push hl                        ; stamp_rect keeps only C
                call stamp_rect
                pop  hl
                jr   .r
                ASSERT HUD4_EXT + 2 * TEXT_ROWS <= LOG_QN && LOG_QN + 1 == PANEL_POT_SH && PANEL_POT_SH + 1 == P_NUMBUF
                ASSERT P_NUMBUF + 3 == FIRE_LOCK && FIRE_LOCK + 1 == LOG_Q

; new_game: B0CODE (2026-11-12) -> bank-0 B0_CODE2 (src/newgame0.asm, FARB0 from start_game).
