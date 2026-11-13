;==============================================================================
; hunger0.asm — 3E-T9 the panel FOOD item. NEW-MON3 T1 (2026-11-13): moved from R6
; (hunger6.asm) to bank-0 B0_CODE2 (src/nm3_b0.asm) with bars_draw: entered only by FARB0
; from panel_more (A / F lost on the way back; same cost as the far6 it replaced). MEM-RECLAIM w2b: the hunger
; logic (hunger_turn / hunger_add / hg_stage ...) is bank-7 hunger7.asm;
; item_food stays here (panel render code never runs from contended bank 7).
;   item_food    FARB0 from panel_more (bank 2): the FOOD bar + stage word
;==============================================================================

;------------------------------------------------------------------------------
; item_food — the panel FOOD item (FARB0 from panel_more, a tick's 1st frame
; only): the bar (fill FOOD / FOOD_MAX, cols 15..18), the stage word (bank-0
; hg_fed / hg_ok / hg_hungry / hg_weak, padded to HG_CHARS so a shorter word
; overwrites a longer one; cols 19..23) and the stage attr over both
; (hg_attr; game.md §7 table), marked for the present.
; Clobbers: A, BC, DE, HL.   ~8.5k T incl. FARB0 (tests/hunger.py T1; screen
; writes are contended)
;------------------------------------------------------------------------------
HG_CHARS        EQU 6
FOOD_WORD_BMP   EQU ((SCREEN_BITMAP >> 8) | (STAT_ROW & $18)) << 8 | ((STAT_ROW & 7) << 5) | HUNGER_COL
FOOD_BAR_ADDR   EQU ((SCREEN_BITMAP >> 8) | (STAT_ROW & $18)) << 8 | ((STAT_ROW & 7) << 5) | FOOD_BAR_COL
item_food:
                ld   hl, PANEL_DIRTY
                res  PD_FOOD_BIT, (hl)
                ld   a, (FOOD)
                ld   d, FOOD_MAX
                ld   hl, FOOD_BAR_ADDR
                call bars_draw
                ld   a, (HSTAGE)
                add  a, TX_HG_FED
                call tx_dec                    ; HL = TX_DEC (bank 5; hands bank 0 back)
                ld   b, HG_CHARS
.f:             ld   a, (hl)
                or   a
                jr   z, .pad
                inc  hl
                djnz .f
                jr   .pr                       ; a 6-char word: HL at its terminator
.pad:           ld   (hl), ' '
                inc  hl
                djnz .pad
                ld   (hl), 0
.pr:            ld   hl, TX_DEC
                ld   b, STAT_ROW
                ld   e, HUNGER_COL * 8
                call print6
                ld   a, (HSTAGE)
                ld   e, a
                ld   d, 0
                ld   hl, hg_attr
                add  hl, de
                ld   a, (hl)
                ld   bc, (STAT_ROW << 8) | FOOD_BAR_COL
                ld   de, ((GEAR_COL - FOOD_BAR_COL) << 8) | 1
                call stamp_rect                ; (A, B, D, E, HL)
                ld   a, (HSTAGE)               ; UX1 F1 (ux_polish.md §2): at WEAK the word's ink
                cp   HS_WEAK                   ; cells FLASH (bit 7; the bar never; a blank cell would
                jr   nz, .pm                   ; flash as a block: R4). Inline (not ux0.asm's ux_foodg:
                ld   hl, SCREEN_ATTR + STAT_ROW * 32 + HUNGER_COL   ; hunger.py T1's 9k cap)  ~1.1k T at WEAK
                ld   de, FOOD_WORD_BMP
                ld   c, GEAR_COL - HUNGER_COL
.fw:            push de
                xor  a
                ld   b, 8
.fp:            ex   de, hl
                or   (hl)
                ex   de, hl
                inc  d
                djnz .fp
                pop  de
                or   a
                jr   z, .fb
                set  7, (hl)
.fb:            inc  l
                inc  e
                dec  c
                jr   nz, .fw
.pm:            ld   bc, (STAT_ROW << 8) | FOOD_BAR_COL
                ld   de, ((GEAR_COL - FOOD_BAR_COL) << 8) | 1
                jp   pmark_rect
hg_attr:        DB   ATTR_P_FED, ATTR_P_OK, ATTR_P_HUNGRY, ATTR_P_WEAK   ; by HSTAGE
                ASSERT TX_HG_OK == TX_HG_FED + HS_OK && TX_HG_HUNGRY == TX_HG_FED + HS_HUNGRY && TX_HG_WEAK == TX_HG_FED + HS_WEAK
                ASSERT ((HUNGER_COL * 8) & 7) == 0 && HUNGER_COL * 8 + 6 * HG_CHARS <= GEAR_COL * 8   ; print6 x rule
                ASSERT FOOD_BAR_COL + BAR_CELLS == HUNGER_COL
