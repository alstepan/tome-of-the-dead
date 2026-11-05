;==============================================================================
; trap3.asm — TRAP-OR (user playtest 2026-11-05): the known trap plate is OR-composited
; over the cell it lies on, bank 3 (bank3.asm rules: far3 only, no SMC, never pages
; $C000 itself). Before, the reveal / build wrote T_TRAP over the map cell, erasing the
; decor there (a floor object's bottom row), and the build stamped it before the deriver,
; which then dropped the whole overlapping decor object on every re-entry.
; Model: <= 1 trap a room (generator, items_ovl.asm ig_elig), so the plate's tile slot
; T_TRAP is per room: TILE_GLYPHS[T_TRAP] = glyph(u) | the plate (lines 6 / 7,
; TRAP_GLY6 / 7), u = TRAP_UNDER = the cell's id before T_TRAP went in;
; TILE_ATTRS[T_TRAP] = the attr wanted (user ruling 2026-11-05: the trap keeps its own
; type colour over decor too: the decor pixels of that cell take the trap ink, the paper /
; bright as on plain floor). The blink's "off" (attr 0) puts u back: the decor alone.
; Every map writer of T_TRAP goes through tr_cell3, via bank-7 tr_put7 (the location +
; the type ink): build_room_map's stamp (ROOM_MAP and NEXT_MAP, so a scroll-in strip /
; re-entry draws the composite: far7 tr_build7, which far3s back here) and the live
; reveal / flashes (tr_plate). The renderers (erase_rect, tile_rect, the scroll strips,
; mark7) just draw the T_TRAP tile: nothing else knows about it.
; CONTRACT (TRAP_UNDER and the slot are per room, not per map): no other room may be
; built (build_room_map with a known trap) between a room's build and a live tr_put7 on
; it. True today: the only second-map build is do_exit's NEXT_MAP build, and the room it
; leaves never gets another plate draw (the scroll, then room_shadow makes NEXT_MAP the room).
; The plate's row 9s+7 never holds an animated decor cell (only floor-class objects reach
; it and their row 1 is static), so decor_tick never swaps a plate cell.
;==============================================================================

;------------------------------------------------------------------------------
; tr_cell3 — far3 from bank-7 tr_put7 (which already wrote A to TILE_ATTRS[T_TRAP]): DE = a
; map cell, A = the attr wanted (the type ink, PLATE_FLASH_ATTR, or 0 = off): the plate composed there (see the header); an item
; marker there: nothing (it shows; never generated: game.md §1.5).
; Clobbers: A, BC, DE, HL.   ~0.3k T
;------------------------------------------------------------------------------
tr_cell3:       ex   de, hl                    ; HL = the cell
                ld   e, a                      ; E = the attr wanted
                ld   a, (hl)
                cp   T_ITEM0
                ret  nc
                cp   T_TRAP
                jr   z, .k                     ; drawn already: u kept
                ld   (TRAP_UNDER), a
.k:             ld   a, (TRAP_UNDER)
                inc  e
                dec  e
                jr   nz, .on
                ld   (hl), a                   ; off: u alone
                ret
.on:            ld   (hl), T_TRAP
                add  a, a
                add  a, a
                add  a, a                      ; CF = u bit 5 (u < 64: 512-B glyph table)
                ld   l, a
                ld   a, TILE_GLYPHS >> 8
                adc  a, 0
                ld   h, a                      ; HL = glyph(u)
                ld   de, TILE_GLYPHS + T_TRAP * 8
                ld   bc, 6                     ; the plate's lines 0..5 are blank (boot6 ASSERT)
                ldir
                ld   a, TRAP_GLY6              ; line 6: $FF | anything = $FF
                ld   (de), a
                inc  l                         ; (8-aligned glyphs: same page)
                inc  e
                ld   a, (hl)
                or   TRAP_GLY7
                ld   (de), a
                ret
                ASSERT T_AIR == 0 && T_ITEM0 + 4 == TILE_IDS && TILE_IDS <= 64 && (TILE_GLYPHS & $1FF) == 0
                ASSERT ((TILE_GLYPHS + T_TRAP * 8) & 7) == 0 && TRAP_GLY6 == $FF
