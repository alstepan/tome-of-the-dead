;==============================================================================
; key6.asm — LARGER-D T8 / KEY-PANEL: the panel key cells (R6, r6.asm rules: far6 only, no SMC). Reads
; LVL_FLAGS (bank 5), writes the bank-5 screen, pmark_rect (bank 2). The rest of the key runtime: lockl.asm.
;==============================================================================
;------------------------------------------------------------------------------
; key_pan — far6 tail of item_depth (HOT_COPY, PD_DEPTH): KEY-PANEL (user 2026-11-16) two key cells on
; row STAT_ROW, cyan at KEY_PAN_COL, magenta at KEY_PAN_COL + 1 (cols 24..29 of row 21 are free: the FOOD
; word ends at col 23, the status icons are cols 30-31; level_defs.asm KEY_PAN_COL). Each cell gets the
; 8x8 key glyph and its key's ink on paper 0 while that key is held, blank (glyph lines 0, attr ATTR_HUD
; = the panel clear's) otherwise; no "both" state. In: A = LVL_FLAGS. Then marks the 2 key cells for present (item_depth marks its "Dn" cells itself).
; Clobbers: A, BC, DE, HL.   ~0.8k T
;------------------------------------------------------------------------------
KEY_PAN_ATTR    EQU SCREEN_ATTR + STAT_ROW * 32 + KEY_PAN_COL
KEY_PAN_BM      EQU SCREEN_BITMAP + ((STAT_ROW & $18) << 8) + ((STAT_ROW & 7) << 5) + KEY_PAN_COL
key_pan:                                       ; A = LVL_FLAGS (item_depth loads it: farb passes A in)
                add  a, a                      ; CF = LF_KEYM (bit 7), A bit 7 = LF_KEYC
                ld   c, a
                sbc  a, a
                ld   b, a                      ; B = magenta mask ($FF held / 0)
                ld   a, c
                add  a, a
                sbc  a, a
                ld   c, a                      ; C = cyan mask
                ld   hl, KEY_PAN_BM + KEY_GLY_N * $100 - $100   ; the glyph's last line, upwards
                ld   de, key_gly + KEY_GLY_N - 1
.g:             ld   a, (de)                   ; each cell: the glyph line AND its mask (an unheld
                and  c                         ; key's cell is written blank)
                ld   (hl), a
                inc  l
                ld   a, (de)
                and  b
                ld   (hl), a
                dec  l
                dec  e
                dec  h
                bit  3, h                      ; line 0 done: H = (KEY_PAN_BM >> 8) - 1 ($4F)
                jr   z, .g
                ld   h, KEY_PAN_ATTR >> 8
                ld   a, c                      ; held: the key ink; else ATTR_HUD, the panel's own attr
                and  ATTR_KEY_C ^ ATTR_HUD     ; (a blank cell either way; the goldens keep it)
                xor  ATTR_HUD
                ld   (hl), a
                inc  l
                ld   a, b
                and  ATTR_KEY_M ^ ATTR_HUD
                xor  ATTR_HUD
                ld   (hl), a
                ld   bc, (STAT_ROW << 8) | KEY_PAN_COL   ; (item_depth marked its "Dn" cells)
                ld   de, (2 << 8) | 1
                jp   pmark_rect
; the panel key glyph = assets/gfx/panel/panel_icons.asm label_key lines 0..4 (bank-1 vdata, not readable
; here); its lines 5..7 are 0, and so are those lines of the two cells (level_show clears the panel; no
; other writer there), so they are never written.
key_gly:        DB   $00, $60, $90, $9F, $65
KEY_GLY_N       EQU $ - key_gly
                ASSERT KEY_PAN_ATTR - KEY_PAN_BM == $A00 && (KEY_PAN_COL & 1) == 0 && (KEY_PAN_ATTR & $FF) == (KEY_PAN_BM & $FF)
                ASSERT (KEY_PAN_BM & $0700) == 0 && ((KEY_PAN_BM >> 8) & 8) == 0 && (((KEY_PAN_BM >> 8) - 1) & 8) != 0
                ASSERT (key_gly >> 8) == ((key_gly + KEY_GLY_N - 1) >> 8)
                ASSERT LF_KEYC == $40 && LF_KEYM == $80
                ASSERT GEAR_COL <= KEY_PAN_COL && KEY_PAN_COL + 2 <= ST_ICON_COL
                ASSERT (ATTR_HUD & $38) == 0 && (ATTR_KEY_C & $38) == 0 && (ATTR_KEY_M & $38) == 0 && ATTR_KEY_C != 0 && ATTR_KEY_M != 0
