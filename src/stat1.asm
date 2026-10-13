;==============================================================================
; stat1.asm — D3-8, bank-1 UI code (ui1.asm rules: far1 only, never page
; $C000; vdata read in place at virtual + TEXT_DISP).
;------------------------------------------------------------------------------
; st_icons_draw — far1 from item_icons (bank 3, PD_ICONS): A = the status sig
; (icons.asm st_sig). The hero's 2 status icons (game.md §6.4 "Indication":
; row 21 = STAT_ROW, cols 30 / 31, one attr per cell from status_icons_attr;
; a blank cell = 0 bitmap, attr 0) into the bank-5 screen, then marked.
; Clobbers: A, BC, DE, HL.   ~1k T
;------------------------------------------------------------------------------
st_icons_draw:
                ld   c, ST_ICON_COL
                push af
                call .cell                     ; low nibble -> col 30
                pop  af
                rrca
                rrca
                rrca
                rrca
                inc  c
                call .cell                     ; high nibble -> col 31
                ld   bc, (STAT_ROW << 8) | ST_ICON_COL
                ld   de, (2 << 8) | 1
                jp   pmark_rect
; .cell — A low nibble = icon index + 1 (0 blank), C = col.  Keeps C.
.cell:          and  $0F
                push bc
                ld   b, STAT_ROW
                ld   e, a
                call attr_addr                 ; HL = the attr cell (keeps DE)
                ld   a, e
                or   a
                jr   z, .blank
                dec  a
                ld   e, a
                ld   d, 0
                push hl
                ld   hl, status_icons_attr + TEXT_DISP
                add  hl, de
                ld   a, (hl)
                pop  hl
                ld   (hl), a                   ; its attr
                ex   de, hl                    ; DE = the attr cell, HL = index
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ld   bc, status_icons + TEXT_DISP
                add  hl, bc
                ex   de, hl                    ; DE = the glyph (8 B)
                call .bm
                ld   b, 8
.g:             ld   a, (de)
                ld   (hl), a
                inc  de
                inc  h
                djnz .g
                pop  bc
                ret
.blank:         ld   (hl), a                   ; A = 0: attr 0, bitmap 0
                call .bm
                ld   b, 8
.z:             ld   (hl), a
                inc  h
                djnz .z
                pop  bc
                ret
; .bm — HL = attr cell -> bitmap line 0 of that cell (panel.asm cell_bm's rule).
.bm:            ld   a, h
                and  3
                rlca
                rlca
                rlca
                or   SCREEN_BITMAP >> 8
                ld   h, a
                xor  a
                ret
                ASSERT ST_ICON_COL + 1 < ROOM_COLS
