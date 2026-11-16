;==============================================================================
; key6.asm — LARGER-D T8: the panel key cell (R6, r6.asm rules: far6 only, no SMC). Reads LVL_FLAGS
; (bank 5), writes the bank-5 screen, pmark_rect (bank 2). The rest of the key runtime: lockl.asm.
;==============================================================================
;------------------------------------------------------------------------------
; key_pan — far6 tail of item_depth (HOT_COPY, PD_DEPTH): the key cell (ICON_ROW + 1, DEPTH_COL): the key
; glyph in the held colour (cyan / magenta, both = ATTR_KEY_CM); no key: attr 0 (panel_init7's), the
; glyph stays drawn but invisible after a key was used up. Then marks the 2 x 2 depth / key cells.
; Clobbers: A, BC, DE, HL.   ~0.5k T
;------------------------------------------------------------------------------
KEY_CELL_ATTR   EQU SCREEN_ATTR + (ICON_ROW + 1) * 32 + DEPTH_COL
KEY_CELL_BM     EQU SCREEN_BITMAP + (((ICON_ROW + 1) & $18) << 8) + (((ICON_ROW + 1) & 7) << 5) + DEPTH_COL
key_pan:
                ld   a, (LVL_FLAGS)
                rlca
                rlca
                and  3                         ; bit 0 = cyan (LF_KEYC), bit 1 = magenta (LF_KEYM)
                add  a, key_attr & $FF
                ld   l, a
                ld   h, key_attr >> 8
                ld   a, (hl)
                ld   (KEY_CELL_ATTR), a
                or   a                         ; no key: attr 0 hides the glyph (drawn only once a key
                jr   z, .m                     ; is held; level_show clears the panel rows)
                ld   hl, key_gly
                ld   de, KEY_CELL_BM
                ld   b, 8
.g:             ld   a, (hl)
                ld   (de), a
                inc  hl
                inc  d
                djnz .g
.m:             ld   bc, (ICON_ROW << 8) | DEPTH_COL
                ld   de, (2 << 8) | 2
                jp   pmark_rect
key_attr:       DB   0, ATTR_KEY_C, ATTR_KEY_M, ATTR_KEY_CM
; the panel key glyph = assets/gfx/panel/panel_icons.asm label_key (bank-1 vdata, not readable here)
key_gly:        DB   $00, $60, $90, $9F, $65, $00, $00, $00
                ASSERT (key_attr >> 8) == ((key_attr + 3) >> 8)
                ASSERT LF_KEYC == $40 && LF_KEYM == $80 && (KEY_CELL_BM & $FF) == (KEY_CELL_ATTR & $FF)
