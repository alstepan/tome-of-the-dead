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
xpn_tab:        DW   44, 110, 220, 374, 550, 770, 1012, 1265     ; LARGER-D T5 package 3
                ASSERT $ - xpn_tab == XPN_COUNT * 2 && XPN_COUNT == LVL_MAX - 1
                ; XP-BAR (info1.asm xp_bar): every threshold delta (incl. 0 -> L2) must fit a byte (max 253 today)
                ASSERT {xpn_tab} <= 255
                ASSERT {xpn_tab + 2} - {xpn_tab} <= 255 && {xpn_tab + 4} - {xpn_tab + 2} <= 255
                ASSERT {xpn_tab + 6} - {xpn_tab + 4} <= 255 && {xpn_tab + 8} - {xpn_tab + 6} <= 255
                ASSERT {xpn_tab + 10} - {xpn_tab + 8} <= 255 && {xpn_tab + 12} - {xpn_tab + 10} <= 255
                ASSERT {xpn_tab + 14} - {xpn_tab + 12} <= 255

; item_mp (the MP panel item): NEW-MON3 T1 -> bank-0 src/nm3_b0.asm (FARB0 from panel_more).
