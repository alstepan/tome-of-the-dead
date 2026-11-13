;==============================================================================
; bag6.asm — 3E-T10 bag helpers (R6: was bank-3 bag3.asm), the R6 region
; (r6.asm, bank 6). Reached by far6 from any bank (results in BC / DE / HL
; only: far6 clobbers A, F — bag_find's C = 0 when absent) or called directly
; by R6 code. BAG ($5D00, bank 5) is always mapped, so nothing here pages.
; Callers since 3E-T11: pickup6.asm (pu_add, kit_add, pot_sync), fx6.asm (the effects). IX / IY are never touched; no EXX.
;
; BAG invariant (kept by these helpers): records are packed from slot 0 (a
; free slot, TYPE IT_NONE, is followed only by free slots), so the order is
; pickup order and bag_add's first free slot is the end of the list.
;==============================================================================

;------------------------------------------------------------------------------
; bag_add — add a stack of B items of type A with ISTATE C.
; In : A = type, B = qty (1..STACK_MAX), C = ISTATE (gear; 0 for stackables).
; Out: L = 0 added (UX1: E = 3 * the slot added to / topped up), L = 1 refused (bag
;      full, or A is not a bag type: < IT_BAG_LO (counters, the legacy potion id 1) or
;      >= IT_COUNT). BAG untouched on 1.
; Food / potions / scrolls (IT_FOOD_LO..IT_SCR_HI) top up the first stack of the
; type that stays <= STACK_MAX, else take the first free slot; gear, the book
; and the bow never merge (E = 0 never equals a used slot's non-zero type).
; 3E-T11: an add runs pot_sync (E_POT = the bag's potion count, +~1.2k T).
; Clobbers: A, DE, HL, F (B, C kept).   ~0.6k T worst (20 slots) + pot_sync
;------------------------------------------------------------------------------
bag_add:
                ld   d, a
                sub  IT_BAG_LO
                cp   IT_COUNT - IT_BAG_LO
                jr   nc, .full              ; counter / legacy / out of range
                ld   a, d
                IT_IN IT_FOOD_LO, IT_SCR_HI
                ld   e, 0                      ; match type: none ...
                jr   nc, .ns
                ld   e, d                      ; ... or the type itself if it stacks
.ns:            ld   hl, BAG
.l:             ld   a, (hl)
                or   a
                jr   z, .new                   ; packed list: first free slot = the end
                cp   e
                jr   nz, .nx
                inc  l
                ld   a, (hl)
                add  a, b
                cp   STACK_MAX + 1
                jr   c, .mg
                dec  l                         ; this stack would overflow: keep looking
.nx:            ld   a, l
                add  a, IR_STRIDE
                ld   l, a
                cp   BAG_SLOTS * IR_STRIDE
                jr   c, .l
.full:         ld   l, 1
                ret
.mg:            ld   (hl), a
                dec  l
                jr   .ok
.new:           ld   (hl), d
                inc  l
                ld   (hl), b
                inc  l
                ld   (hl), c
                dec  l
                dec  l
.ok:            ld   e, l                      ; UX1: E = 3 * the slot (pu_add -> ux_pick)
                call pot_sync                  ; 3E-T11: E_POT = the bag's potions (keeps DE)
                ld   l, 0
                ret

;------------------------------------------------------------------------------
; bag_find — first slot holding a type.
; In : A = type (IT_NONE finds the first free slot).
; Out: A = slot 0..BAG_SLOTS-1, or $FF if absent.
; Clobbers: A, C, HL, F (B, DE kept).   ~0.5k T worst
;------------------------------------------------------------------------------
bag_find:
                ld   hl, BAG
                ld   c, BAG_SLOTS
.l:             cp   (hl)
                jr   z, .f
                inc  l
                inc  l
                inc  l
                dec  c
                jr   nz, .l
                ld   a, $FF
                ret
.f:             ld   a, BAG_SLOTS
                sub  c
                ret

;------------------------------------------------------------------------------
; bag_take — remove B items from a slot; an emptied slot is compacted away
; (the later records shift down, the last record is cleared).
; In : A = slot (valid, occupied), B = qty to take (taking >= QTY empties it).
; Out: A = QTY left (0 = the slot is gone).
; 3E-T11: ends with pot_sync (E_POT, +~1.2k T).
; Clobbers: A, BC, DE, HL, F.   ~60 T; + ~21 T per record shifted when emptied
;------------------------------------------------------------------------------
bag_take:
                ld   l, a
                add  a, a
                add  a, l
                ld   l, a                      ; slot * IR_STRIDE (<= 57)
                ld   h, HIGH BAG
                inc  l
                ld   a, (hl)
                sub  b
                jr   z, .free
                jr   c, .free
                ld   (hl), a
                jr   .sy
.free:          dec  l
                push hl
                ld   a, l                      ; UX1 (ux_polish.md §4): NEW_MASK / LAST_PICK follow
                FARB0 ux_compact               ; the shift (ux0.asm, B0_CODE2)
                pop  hl
                ld   d, h
                ld   e, l                      ; DE = this record
                inc  l
                inc  l
                inc  l                         ; HL = the next record
                ld   a, BAG_SLOTS * IR_STRIDE - IR_STRIDE
                sub  e
                ld   c, a
                ld   b, 0
                jr   z, .z                     ; last slot: nothing to shift
                ldir
.z:             xor  a                         ; DE = the last record now
                ld   (de), a
                inc  e
                ld   (de), a
                inc  e
                ld   (de), a
.sy:            push af                        ; 3E-T11: E_POT = the bag's potions
                call pot_sync
                pop  af
                ret

;------------------------------------------------------------------------------
; bag_discard — 3E-T13 the page's DISCARD (game.md §8.11 Q3): the whole stack
; in bag slot A is destroyed (no floor entry, no line yet: the "YOU DISCARD "
; stem is the T8 fx overlay's); the bow also clears HAS_BOW. far6 from
; page_post (bank 1) after the page closed; 0 turns.
; In : A = slot 0..BAG_SLOTS-1 (occupied). Out: A = 0.
; Clobbers: A, BC, DE, HL, F.   ~2k T (bag_take + pot_sync)
;------------------------------------------------------------------------------
bag_discard:
                ld   c, a
                add  a, a
                add  a, c
                ld   l, a
                ld   h, HIGH BAG
                ld   a, (hl)
                cp   IT_BOW
                jr   nz, .nb
                xor  a
                ld   (HAS_BOW), a
.nb:            ld   a, c
                ld   b, STACK_MAX              ; >= any QTY: the slot empties
                jr   bag_take

;------------------------------------------------------------------------------
; bag_pick — the quick-slot pick (game.md §8 "Quick slots auto-fill"; no pin).
; In : B = first type of the class (IT_FOOD_LO / IT_POT_LO / IT_SCR_LO),
;      D = 2 * class size + mode (mode 0: the lowest type present = food,
;      potion; mode 1: the largest stack, ties to the lowest type = scroll).
; Out: A = the type, IT_NONE if the class is absent from the bag. (bag_find
;      gives its slot.) A type spread over two slots counts its first stack.
; Clobbers: A, BC, DE, HL, F.   <= 12 bag_find (~0.5k T) ~ 6k T worst
;------------------------------------------------------------------------------
bag_pick:
                ld   e, 0                      ; E = best QTY so far
                xor  a
                push af                        ; best type (high byte) = none
.t:             ld   a, b
                call bag_find
                inc  a
                jr   z, .nx                    ; absent
                dec  a
                ld   c, a
                add  a, a
                add  a, c
                inc  a                         ; slot * IR_STRIDE + IR_QTY
                ld   l, a
                ld   h, HIGH BAG
                ld   c, (hl)                   ; C = this stack's QTY
                ld   a, e
                cp   c
                jr   nc, .nx                   ; not strictly larger
                ld   e, c
                pop  af
                push bc                        ; best type = B
                bit  0, d
                jr   z, .done                  ; mode 0: the first present wins
.nx:            inc  b
                dec  d
                dec  d
                ld   a, d
                cp   2
                jr   nc, .t
.done:          pop  bc
                ld   a, b
                ret
                ASSERT (BAG & $FF) == 0 && BAG_SLOTS * IR_STRIDE <= 60
                ASSERT IT_FOOD_LO == IT_BAG_LO && IT_SCR_HI + 1 == IT_BOOK
bag6_end:
BAG6_LEN        EQU bag6_end - bag_add
