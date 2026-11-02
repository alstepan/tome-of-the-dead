;==============================================================================
; fi3.asm — FLOOR1: fi_full, the cold from-scratch build of the floor-item
; glyph cache (far3 only; the per-entry work is R6 fi_add, fi6.asm). Bank 3
; (bank 2 from LAND-PENDING to BLAIR-FIX, which moved resolve_monsters the
; other way); touches only low RAM + far6 (nests from bank 3).
;==============================================================================
;------------------------------------------------------------------------------
; fi_full — A = room (0..8): the cache emptied, then every live FLOOR_LIST
; entry of the room (both storeys), in list order, -> its type's slot (a new
; type: the first free slot, glyph + ink copied) and its 4 cells (a later entry
; of the col overdraws: the pile's top shows). The room holds <= FI_SLOTS (8)
; distinct types (drop_put / uq_fit keep that), so every entry, piled or not,
; gets a slot: a pickup revealing the type under a pile needs no rebuild.
; far3 from room_show (level entry, start_game, teleport), do_exit (EXIT_DEST
; before the scroll), pause close (menu1), page_post (menu1): the bytes may be
; garbage (pause save / page map save / generator). Cold (bank 3).
; Clobbers: A, BC, DE, HL.   ~4k T + ~1.5k T per live entry of the room + ~0.9k T per type
;------------------------------------------------------------------------------
fi_full:        push af
                ld   hl, FI_PAD
                ld   b, 1 + 64 + FI_SLOTS      ; FI_PAD + FI_TSLOT + FI_TYPE: all FI_NONE
.i:             ld   (hl), FI_NONE
                inc  l
                djnz .i
                xor  a
                ld   b, FI_SLOTS               ; FI_USE: 0 (FI_CELL: valid only under a marker)
.u:             ld   (hl), a
                inc  l
                djnz .u
                pop  af
                ld   d, a                      ; D = room
                ld   hl, FLOOR_LIST
.e:             ld   a, (hl)
                ld   e, a                      ; E = the FL_ROOM byte (fi_put reads FL_S1 only)
                and  FL_ROOM_MASK              ; (FL_EMPTY -> 15: never a room; bits 4-7 ignored)
                cp   d
                jr   nz, .n
                push hl
                push de
                inc  l
                ld   a, (hl)                   ; A = col
                inc  l
                ld   d, (hl)                   ; D = type
                ld   hl, fi_add                ; R6: slot + cells (a later entry of the col wins)
                call far6
                pop  de
                pop  hl
.n:             ld   a, l
                add  a, FL_STRIDE
                ld   l, a
                jp   p, .e                     ; 32 entries: L $00..$7C
                ret
                ASSERT FI_TYPE == FI_TSLOT + 64 && FI_USE == FI_TYPE + FI_SLOTS
                ASSERT (FLOOR_LIST & $FF) == 0 && FLOOR_MAX * FL_STRIDE == $80 && FL_COL == 1 && FL_ITEM == 2

