;==============================================================================
; key6.asm — LARGER-D T8 / KEY-PANEL: the panel key cells (R6, r6.asm rules: far6 only, no SMC). Reads
; LVL_FLAGS (bank 5), writes the bank-5 screen, pmark_rect (bank 2). The rest of the key runtime: lockl.asm.
;==============================================================================
;------------------------------------------------------------------------------
; key_pan — far6 tail of item_depth (HOT_COPY, PD_DEPTH): KEY-PANEL (user 2026-11-16; 16x8 keys, option 1)
; two 2-cell key icons on row STAT_ROW: cyan at KEY_PAN_COL..+1 (24-25), magenta at KEY_PAN_COLM..+1
; (27-28), col 26 a gap (cols 24..29 of row 21 are free: the FOOD word ends at col 23, the status icons
; are cols 30-31; level_defs.asm). Each icon gets the 16x8 key glyph (floor_key.grid rows 8..15) and its
; key's ink on paper 0 while that key is held, blank (glyph lines 0, attr ATTR_HUD = the panel clear's)
; otherwise. In: A = LVL_FLAGS. item_depth marks the cells for present (R6 has no room for it).
; Clobbers: A, F, BC, DE, HL.   ~1.0k T (2 x ~0.45k)
;------------------------------------------------------------------------------
KEY_PAN_ATTR    EQU SCREEN_ATTR + STAT_ROW * 32 + KEY_PAN_COL
KEY_PAN_BM      EQU SCREEN_BITMAP + ((STAT_ROW & $18) << 8) + ((STAT_ROW & 7) << 5) + KEY_PAN_COL
KP_L6           EQU KEY_PAN_BM + (KEY_GLY_N / 2) * $100     ; glyph line 6 (the last non-0), right cell
key_pan:                                       ; A = LVL_FLAGS (item_depth loads it: farb passes A in)
                add  a, a                      ; CF = LF_KEYM (bit 7), A bit 7 = LF_KEYC
                push af
                ld   hl, KP_L6 + KEY_PAN_COLM - KEY_PAN_COL + 1
                ld   c, ATTR_KEY_M ^ ATTR_HUD
                call .k
                pop  af
                add  a, a                      ; CF = LF_KEYC
                ld   hl, KP_L6 + 1
                ld   c, ATTR_KEY_C ^ ATTR_HUD  ; falls into .k for the cyan icon
; .k: one icon. CF = held, HL = its right cell at glyph line 6, C = its attr ^ ATTR_HUD. Lines 6..1 bottom-up
; (lines 0 / 7 of the glyph are 0, and so are those lines of the cells: level_show clears the panel, no
; other writer there, so they are never written). Mask B = $FF held / 0: an unheld icon is written blank.
.k:             sbc  a, a
                ld   b, a
                ld   de, key_gly + KEY_GLY_N - 1   ; interleaved (left, right) per line, upwards
.g:             ld   a, (de)
                and  b
                ld   (hl), a                   ; right cell
                dec  l
                dec  e
                ld   a, (de)
                and  b
                ld   (hl), a                   ; left cell
                inc  l
                dec  e
                dec  h
                ld   a, h
                cp   KEY_PAN_BM >> 8           ; line 0 reached: done (not written)
                jr   nz, .g
                ld   h, KEY_PAN_ATTR >> 8      ; same low byte (ASSERT): L = the right cell's attr
                ld   a, b                      ; held: the key ink; else ATTR_HUD, the panel's own attr
                and  c                         ; (a blank cell either way; the goldens keep it)
                xor  ATTR_HUD
                ld   (hl), a
                dec  l
                ld   (hl), a
                ret
; the panel key glyph = assets/gfx/icons/floor_key.grid rows 9..14 (its rows 8 / 15 are 0), (left, right)
; per line; the same art as the floor key, so no separate art source.
key_gly:        DB   $3C, $00
                DB   $66, $00
                DB   $43, $FE
                DB   $43, $FE
                DB   $66, $36
                DB   $3C, $36
KEY_GLY_N       EQU $ - key_gly
                ASSERT KEY_GLY_N == 12
                ASSERT KEY_PAN_ATTR - KEY_PAN_BM == $A00 && (KEY_PAN_ATTR & $FF) == (KEY_PAN_BM & $FF)
                ASSERT (KEY_PAN_BM & $0700) == 0 && (KEY_PAN_BM & $FF) + KEY_PAN_W <= $100
                ASSERT (key_gly >> 8) == ((key_gly + KEY_GLY_N - 1) >> 8)
                ASSERT LF_KEYC == $40 && LF_KEYM == $80
                ASSERT KEY_PAN_COLM == KEY_PAN_COL + 3 && KEY_PAN_W == 5
                ASSERT GEAR_COL <= KEY_PAN_COL && KEY_PAN_COL + KEY_PAN_W <= ST_ICON_COL
                ASSERT (ATTR_HUD & $38) == 0 && (ATTR_KEY_C & $38) == 0 && (ATTR_KEY_M & $38) == 0 && ATTR_KEY_C != 0 && ATTR_KEY_M != 0
