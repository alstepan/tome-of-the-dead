;==============================================================================
; xp2.asm — D3-9b, bank 2 (assembled after kind_tab's arrays + mark.asm, so it
; takes no kind_tab ALIGN pad): the XP_NEXT table and the MP panel item.
;==============================================================================

;------------------------------------------------------------------------------
; xpn_tab — XP_NEXT (game.md §4.1), THE single table (D3-9b; was duplicated in
; bank 3 and bank 1): total XP to reach level 2..9, 16-bit LE, row = (LVL - 2)
; * 2 = the threshold that ends level LVL - 1. Bank 2: read by bank-7 xp_turn
; and bank-1 item_info alike.
;------------------------------------------------------------------------------
XPN_COUNT       EQU 8
xpn_tab:        DW   40, 100, 200, 340, 500, 700, 920, 1150
                ASSERT $ - xpn_tab == XPN_COUNT * 2 && XPN_COUNT == LVL_MAX - 1

;------------------------------------------------------------------------------
; item_mp — D3-9b: MP bar (fill MP / MAXMP) + 2-digit MP (row 21, cols 8..13),
; like item_hp. MP_SH = MP as drawn (icon_poll compares it). HL = PANEL_DIRTY.
; Clobbers: all but IX, IY.   ~4.5k T
;------------------------------------------------------------------------------
item_mp:
                res  PD_MP_BIT, (hl)
                ld   a, (MAXMP)
                ld   d, a                      ; (MAXMP 0 draws an empty bar)
                ld   a, (MP)
                ld   (MP_SH), a
                ld   hl, MP_BAR_ADDR
                call bars_draw
                ld   a, (MP_SH)
                call num2
                ld   b, STAT_ROW
                ld   e, MP_NUM_COL * 8
                call print6
                ASSERT ((MP_NUM_COL * 8) & 7) == 0 && MP_NUM_COL * 8 + 6 * 2 <= FOOD_LBL_COL * 8   ; print6 x rule
                ld   bc, (STAT_ROW << 8) | MP_BAR_COL
                ld   de, ((MP_NUM_COL + 2 - MP_BAR_COL) << 8) | 1
                jp   pmark_rect
MP_BAR_ADDR     EQU ((SCREEN_BITMAP >> 8) | (STAT_ROW & $18)) << 8 | ((STAT_ROW & 7) << 5) | MP_BAR_COL

