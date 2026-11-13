;==============================================================================
; xp2.asm — D3-9b, bank 2 (assembled after kind_tab's arrays + mark.asm, so it
; takes no kind_tab ALIGN pad): the XP_NEXT table (the MP panel item is bank 0 since NEW-MON3 T1).
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

; item_mp (the MP panel item): NEW-MON3 T1 -> bank-0 src/nm3_b0.asm (FARB0 from panel_more).
