;==============================================================================
; trap3.asm — TRAP-OR (user playtest 2026-11-05): the known trap plate is OR-composited
; over the cell it lies on, bank 3 (bank3.asm rules: far3 only, no SMC, never pages
; $C000 itself). Before, the reveal / build wrote T_TRAP over the map cell, erasing the
; decor there (a floor object's bottom row, the glow) and, at a room build, stamping it
; before the deriver dropped the whole overlapping decor object on re-entry.
; Model: <= 1 trap a room (generator), so the plate's tile slot T_TRAP is per room:
;  TILE_GLYPHS[T_TRAP] = glyph(u) | the plate (lines 6 / 7, TRAP_GLY6 / 7), u = TRAP_UNDER
;  = the cell's id before T_TRAP went in; TILE_ATTRS[T_TRAP] = the wanted attr when u is
;  T_AIR or for the bright flash, else the decor's own attr (TILE_ATTRS[u]: a cell keeps
;  2 colours; the decor never changes colour, its plate pixels take the decor ink).
;  The blink's "off" (attr 0) puts u back: the decor alone, never a blank cell.
; Every map writer of T_TRAP goes through tr_cell3: build_room_map (ROOM_MAP and
; NEXT_MAP, so a scroll-in strip / re-entry draws the composite) and tr_put3 (the live
; reveal / flashes, far3 from bank-7 tr_plate). The renderers (erase_rect, tile_rect,
; the scroll strips, mark7) just draw the T_TRAP tile: nothing else knows about it.
; The plate's row 9s+7 never holds an animated decor cell (decor_tick never swaps it:
; only floor-class objects reach it and their row 1 is static, tests/trap_cells.py).
;==============================================================================

;------------------------------------------------------------------------------
; tr_cell3 — HL = a map cell, A = the attr wanted (the type ink, PLATE_FLASH_ATTR, or 0 =
; off): the plate composed there (see the header); an item marker there: nothing (it
; shows; never generated: game.md §1.5).  Keeps BC, HL.  Clobbers: A, DE.   ~0.3k T
;------------------------------------------------------------------------------
tr_cell3:       ld   e, a                      ; E = the attr wanted
                ld   a, (hl)
                cp   T_ITEM0
                ret  nc
                cp   T_TRAP
                jr   z, .k                     ; drawn already: u kept
                ld   (TRAP_UNDER), a
.k:             ld   a, (TRAP_UNDER)
                inc  e
                dec  e
                jr   z, .off                   ; off: u alone
                push bc
                push hl
                ld   d, a                      ; D = u
                add  a, a
                add  a, a
                add  a, a                      ; CF = u bit 5 (u < 64: 512-B glyph table)
                ld   l, a
                ld   a, TILE_GLYPHS >> 8
                adc  a, 0
                ld   h, a                      ; HL = glyph(u)
                push de
                ld   de, TILE_GLYPHS + T_TRAP * 8
                ld   bc, 6                     ; the plate's lines 0..5 are blank (boot6 ASSERT)
                ldir
                ld   a, TRAP_GLY6              ; line 6: $FF | anything = $FF (ASSERT)
                ld   (de), a
                inc  l                         ; (8-aligned glyphs: same page)
                inc  e
                ld   a, (hl)
                or   TRAP_GLY7
                ld   (de), a
                pop  de
                pop  hl
                pop  bc
                ld   a, d
                or   a
                ld   a, e
                jr   z, .a                     ; over T_AIR: the attr wanted
                cp   PLATE_FLASH_ATTR
                jr   z, .a                     ; the bright flash: the whole cell (transient)
                ld   e, d
                ld   d, TILE_ATTRS >> 8
                ld   a, (de)                   ; over decor: the decor's attr
.a:             ld   (TILE_ATTRS + T_TRAP), a
                ld   a, T_TRAP
.off:           ld   (hl), a
                ret
                ASSERT T_AIR == 0 && T_ITEM0 + 4 == TILE_IDS && TILE_IDS <= 64 && (TILE_GLYPHS & $1FF) == 0
                ASSERT (TILE_ATTRS & $FF) == 0 && ((TILE_GLYPHS + T_TRAP * 8) & 7) == 0 && TRAP_GLY6 == $FF

;------------------------------------------------------------------------------
; tr_loc3 — HL = a TRAP_LIST entry: B = its row 9s+7, C = its col, HL = its cell in the
; (TMP1) map, A = its type (TT_*).  Keeps DE.  Clobbers: F.
;------------------------------------------------------------------------------
tr_loc3:        ld   a, (hl)
                and  TRF_S1
                rrca
                rrca
                rrca
                rrca                           ; s
                call storey_row                ; (bank 2) A = 9s+7, keeps BC, DE
                ld   b, a
                inc  l
                ld   a, (hl)
                and  TR_COL_MASK
                ld   c, a
                xor  (hl)                      ; the type << 5
                rlca
                rlca
                rlca
                push af
                call map_cell                  ; (bank 2; A) keeps BC, DE
                pop  af
                ret
                ASSERT TRF_S1 == 1 << 4 && TR_TYPE_SHIFT == 5 && TR_B1 == 1

;------------------------------------------------------------------------------
; tr_put3 — far3 from bank-7 tr_plate: DE = an entry of CUR_ROOM, A = the attr wanted
; (tr_cell3): its plate composed in ROOM_MAP; out B = its row, C = its col (farb passes
; BC out: tr_plate queues the 1x1 redraw + the attr shadow from bank 7, as ap_put_a did).
; Clobbers: A, DE, HL.   ~0.5k T + the far call
;------------------------------------------------------------------------------
tr_put3:        ex   de, hl                    ; HL = the entry
                ld   d, a                      ; D = the attr
                ld   a, ROOM_MAP >> 8
                ld   (TMP1), a
                call tr_loc3                   ; B, C, HL = the cell (keeps DE)
                ld   a, d
                jr   tr_cell3                  ; (keeps BC)
