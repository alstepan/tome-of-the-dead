;==============================================================================
; pickup6.asm — 3E-T11 (R6: was bank-3 pickup3.asm), the R6 region (r6.asm,
; bank 6; INCLUDEd before bag6.asm): the bag side of the floor pickup, the
; potion quick slot, the start kit, and the monster drops (game.md §8.11 "3E
; pickup/drop rulings", Q10, Q11). Entered by far6 only: from bank 7 (pu_add,
; pot_take1, kit_add), bank 3 (mon_drop from deal_hit: R6 is paged OVER bank 3
; meanwhile — nothing here touches bank-3 code or data; hla is inlined) and
; bank 3 (pot_sync from level_populate). bag6.asm is called directly (same
; bank). BAG / FLOOR_LIST / ROOM_MAP are bank 5.
;
; E_POT (hero slot 0) is no longer a counter of its own: it is the number of
; potions in BAG (Heal + Mana + Cure), written ONLY by pot_sync, which every
; BAG writer runs (bag_add / bag_take tails, level_populate). The potion icon /
; count / info readers keep reading E_POT unchanged (0 B and 0 T for them).
;==============================================================================

;------------------------------------------------------------------------------
; pot_sync — E_POT := the sum of the potion stacks' QTY in BAG; 3E-T12 / IC1:
; QS_CACHE + QS_FOOD / QS_SCROLL := the food / scroll QTY in BAG (0 = the
; icon greys, icons3.asm icon_state; IC1: QTY, not stacks — every BAG write
; that touches the class changes it, so a change = the quick slot's pick or
; count may differ: that slot is forced to redraw, ICON_SH := IS_NONE +
; QS_RECHK bit 7 -> icon_poll's PD_ICONS in a tick's 1st frame); QS_CACHE + QS_POTION := the potion types present (bit k =
; IT_P_HEAL + k: pot_need / icon_state's pick; the potion slot redraws on
; E_POT, item_icons). The quick slots are icon-bar slots 6..8 (both
; heroes, UB5) = QS_SLOT0 + QS_*.
; Clobbers: A, HL, F (BC, DE kept).   ~1.7k T (20 slots)
;------------------------------------------------------------------------------
pot_sync:
                push bc
                push de
                xor  a
                ld   (QS_CACHE + QS_POTION), a
                ld   hl, BAG
                ld   bc, BAG_SLOTS << 8        ; B = slots, C = potions
                ld   de, 0                     ; D = food QTY, E = scroll QTY
.l:             ld   a, (hl)
                inc  l                         ; -> QTY
                sub  IT_FOOD_LO
                cp   IT_FOOD_HI - IT_FOOD_LO + 1
                jr   nc, .nf
                ld   a, (hl)
                add  a, d
                ld   d, a
                jr   .nx
.nf:            sub  IT_POT_LO - IT_FOOD_LO    ; (a food wraps past both tests)
                cp   IT_POT_HI - IT_POT_LO + 1
                jr   nc, .np
                push hl                        ; potion k = A: present bit 1 << k
                ld   hl, QS_CACHE + QS_POTION
                inc  a
                cp   3
                jr   c, .pb
                inc  a                         ; 1, 2, 4
.pb:            or   (hl)
                ld   (hl), a
                pop  hl
                ld   a, (hl)
                add  a, c
                ld   c, a
                jr   .nx
.np:            sub  IT_SCR_LO - IT_POT_LO
                cp   IT_SCR_HI - IT_SCR_LO + 1
                jr   nc, .nx
                ld   a, (hl)
                add  a, e
                ld   e, a
.nx:            inc  l
                inc  l
                djnz .l
                ld   a, c
                ld   (P_ENTITIES + E_POT), a
                ld   hl, QS_CACHE + QS_FOOD
                ld   a, d
                ld   c, QS_SLOT0 + QS_FOOD
                call .qs
                ld   l, (QS_CACHE + QS_SCROLL) & $FF
                ld   a, e
                ld   c, QS_SLOT0 + QS_SCROLL
                call .qs
                pop  de
                pop  bc
                ret
.qs:            cp   (hl)
                ret  z
                ld   (hl), a
                push hl
                ld   a, c
                add  a, ICON_SH & $FF
                ld   l, a
                ld   h, ICON_SH >> 8
                ld   (hl), IS_NONE             ; that slot redraws (pick / count) in a
                ld   hl, QS_RECHK              ; tick's 1st frame (icon_poll: bit 7)
                set  7, (hl)
                pop  hl
                ret
                ASSERT (BAG & $FF) + BAG_SLOTS * IR_STRIDE <= 256 && IR_QTY == 1 && IR_STRIDE == 3
                ASSERT IT_POT_LO == IT_FOOD_HI + 1 && IT_SCR_LO == IT_POT_HI + 1 && IT_POT_HI == IT_POT_LO + 2
                ASSERT ((QS_CACHE + QS_FOOD) >> 8) == ((QS_CACHE + QS_SCROLL) >> 8)
                ASSERT (ICON_SH >> 8) == ((ICON_SH + ICON_SLOTS - 1) >> 8)
                ASSERT QS_SLOT0 + QS_SCROLL < ICON_SLOTS

;------------------------------------------------------------------------------
; pu_add — far6 from floor_pickup (bank 7) for a non-ammo entry under the
; hero. In: A = its FL_ITEM (the legacy IT_POTION of the PROTO rooms / the 3B
; levelgen step = a Heal potion). bag_add qty 1, ISTATE 0 (a floor item is
; always plain, rev 6): added -> IT_BOW sets HAS_BOW (the bow icon / ic_bow
; until HAS_BOW retires), "YOU PICK UP " + name, L = 1 (the caller empties the
; entry, sets its POTIONS_TAKEN bit, SFX, re-stamps the cell); refused (bag
; full) -> L = 0 (the caller prints BAG FULL on an arrival).
; Clobbers: A, BC, DE, HL.   added ~10k T (bag_add + pot_sync + name + log)
;------------------------------------------------------------------------------
pu_add:
                cp   IT_POTION
                jr   nz, .t
                ld   a, IT_P_HEAL
.t:             push af
                ld   bc, 1 << 8                ; B = qty 1, C = ISTATE 0
                call bag_add                   ; L = 0 added / 1 refused (A, DE, HL)
                pop  af
                dec  l
                ret  z                         ; refused: L = 0 (bank 7 prints BAG FULL)
                cp   IT_BOW
                jr   nz, .nb
                ld   hl, HAS_BOW
                ld   (hl), 1
.nb:            ld   e, IL_PICK                ; "YOU PICK UP " + name (bank 1)
                ld   hl, it_line
                call far1
                ld   l, 1
                ret

;------------------------------------------------------------------------------
; kit_add — far6 from new_game (bank 7), after ITEM_RAM is cleared and the hero
; slot is set: the start kit (game.md §8.11 Q10 / §4): WORN weapon + armour,
; the bag list by HERO_KIND (+ the DEBUG_KIT extras, rev 6 list, + the bow for
; the Warrior). Ends with E_POT synced (bag_add). 3E-T9: FOOD := FOOD_START.
; 3E-T8: then hero_recalc (atk / eva / die / DEF / RES / MAXMP / MP_PER) and
; MP := MAXMP.
; Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
kit_add:
                ld   a, FOOD_START             ; 3E-T9: new_game zeroed ITEM_RAM (FED, timers 0)
                ld   (FOOD), a
                ld   a, (HERO_KIND)
                ld   hl, kit_w
                or   a
                jr   z, .k
                ld   hl, kit_m
.k:             ld   de, WORN                  ; WS_WEAPON, then WS_ARMOUR: TYPE, QTY 1
                ld   b, 2
.w:             ld   a, (hl)
                inc  hl
                ld   (de), a
                inc  e
                ld   a, 1
                ld   (de), a
                inc  e
                inc  e
                djnz .w
.l:             ld   a, (hl)
                inc  hl
                or   a
                jr   z, .rc
                push hl
                ld   bc, 1 << 8
                call bag_add
                pop  hl
                jr   .l
.rc:            call hero_recalc               ; 3E-T8: the worn kit's stats (gear6.asm)
                ld   a, (MAXMP)                ; start full (the Robe's +2 included)
                ld   (MP), a
                ret
kit_w:          DB   IT_W_SHORT, IT_A_LEATHER, IT_P_HEAL, IT_F_APPLE
    IF DEBUG_KIT
                DB   IT_P_CURE, IT_P_MANA, IT_S_TELEPORT, IT_S_FEAR, IT_S_SLEEP, IT_S_ENCHANT
                DB   IT_F_MEAT, IT_BOOK, IT_H_HELM, IT_BOW
    ENDIF
                DB   0
kit_m:          DB   IT_W_OAK, IT_A_ROBE, IT_P_HEAL, IT_P_MANA, IT_F_APPLE
    IF DEBUG_KIT
                DB   IT_P_CURE, IT_S_TELEPORT, IT_S_FEAR, IT_S_SLEEP, IT_S_ENCHANT
                DB   IT_F_MEAT, IT_BOOK, IT_H_HELM
    ENDIF
                DB   0
                ASSERT WS_WEAPON == 0 && WS_ARMOUR == 1 && ((WORN + 2 * IR_STRIDE) >> 8) == (WORN >> 8)

;------------------------------------------------------------------------------
; drop_put — far6 from bank-3 mon_drop (FLOOR1: was in this file): a new
; FLOOR_LIST entry under the dead body IX.
; In : A = type, D = qty, E = search half-width (DROP_NEAR 3; DROP_WHOLE: the
;      whole storey, a unique). INVARIANT (FLOOR1 manager decision 2026-10-28):
;      a room never holds more than FI_SLOTS (8) distinct item types, tops and
;      piles alike. A type that would be a 9th is REFUSED here (L = 0, silently:
;      monster loot is not dropped; a future thrown-ammo / hero drop of a type
;      the room already has is never a 9th, so it follows the rules below). A
;      boss unique is made to fit by its caller (drop3.asm uq_fit displaces an
;      ordinary item first). Placement (§8.11 rulings 2), on the body's storey,
;      centre col d = x + w/2:
;      1. an existing item whose col is within d-1 .. d+1 (an exact-col stack);
;      2. else the nearest free footprint c..c+1 with c in d-C .. d+C (left
;         first), c in 2..28: its 4 cells T_AIR (no wall / decor / ladder,
;         no other item within c-1..c+1: their marker cells), a floor under
;         both cols (TF_FLOOR: no hole / pit) and no unspent trap on c or
;         c+1 (3E-T16 trap_at, hidden or known).
;      List: the first FL_EMPTY entry, among 0..30 for an ordinary drop,
;      0..31 for a unique (entries fill from 0 and the generator uses <= 17,
;      so entry 31 is the last to fill: it stays the unique's; a pickup
;      freeing a lower entry after all 32 were used is the one case this
;      differs from "<= 31 used"). Arrows never merge into a stack (one entry
;      per drop; pickup merges).
; Out: L = 0 lost (silently); else L = 1, the entry written and the cell
;      stamped (far7 ap_stamp_a: map + attr shadow + the glyph cache).
; Clobbers: all but IX.
;------------------------------------------------------------------------------
drop_put:       call .go
                sbc  a, a
                inc  a
                ld   l, a                      ; (far6 loses F: the result in L)
                ret
.go:            ld   l, a
                ld   h, d
                ld   (dp_tq), hl               ; type, qty
                ld   a, e
                ld   (dp_w), a
                ; --- the first free entry: 0..30, or 0..31 for a unique ---
                ld   hl, FLOOR_LIST
                ld   b, FLOOR_MAX - 1
                cp   DROP_WHOLE                ; (A = C)
                jr   nz, .f
                inc  b
.f:             ld   a, (hl)
                inc  a                         ; FL_EMPTY = $FF
                jr   z, .fe
                ld   a, l
                add  a, FL_STRIDE
                ld   l, a
                djnz .f
                scf
                ret                            ; list full: lost
.fe:            ld   a, l
                ld   (dp_slot), a
                ; --- the cell ---
                call get_box                   ; C = x, D = w (A, B, E, HL)
                srl  d
                ld   a, c
                add  a, d
                ld   d, a                      ; D = centre col
                call storey_ref                ; A = s (A, HL)
                ld   e, a
                rrca
                or   (ix+E_ROOM)
                ld   (dp_rb), a                ; the FL_ROOM byte
                ld   a, e
                call storey_row                ; A = 9s + 7
                ld   b, a
                ld   a, (dp_tq)
                call dp_cap                    ; CF = a 9th type: the room's invariant (<= 8 distinct
                ret  c                         ; types) refuses it, lost (else its slot is taken now)
                ld   e, 1                      ; 1. a pile within +-1
                call dp_pile
                jr   nc, .put
                ld   e, 0                      ; 2. E = distance
.s:             ld   a, d
                sub  e
                call .try
                ld   a, d
                add  a, e
                call .try
                inc  e
                ld   a, (dp_w)
                cp   e
                jr   nc, .s
                scf
                ret                            ; no free footprint: lost
.try:           cp   ITEM_COL_LO
                ret  c                         ; (also a negative col)
                cp   ITEM_COL_LAST + 1
                ret  nc
                ld   c, a
                call dp_free
                ret  c
                pop  af                        ; found: leave .s
.put:           ld   a, (dp_slot)              ; C = the col
                ld   l, a
                ld   h, FLOOR_LIST >> 8
                ld   a, (dp_rb)
                ld   e, a
                ld   (hl), a                   ; FL_ROOM
                inc  l
                ld   (hl), c                   ; FL_COL
                inc  l
                push de
                ld   de, (dp_tq)
                ld   (hl), e                   ; FL_ITEM
                inc  l
                ld   (hl), d                   ; FL_QTY
                pop  de
                ld   a, c                      ; A = col, E = the FL_ROOM byte
                ld   hl, ap_stamp_a
                call far7
                or   a                         ; CF = 0: placed
                ret
                ASSERT T_AIR == 0 && (FLOOR_LIST & $FF) == 0 && FL_EMPTY == $FF && TF_FLOOR == $80
                ASSERT FL_ROOM == 0 && FL_COL == 1 && FL_ITEM == 2 && FL_QTY == 3 && FL_S1 == $80

; dp_cap — A = type: CF = it gets no glyph slot even after a re-mark = a 9th
; distinct type of the room (the invariant's test). The first fi_slot may fail
; on stale slots (types gone from the room keep theirs during a visit): then
; fi_gc frees them and fi_slot runs again (~3k T, only with 8 slots used).
; Otherwise the type's slot is taken now (ap_stamp's fi_add finds it).
; Keeps BC, DE.  Clobbers A, HL.
dp_cap:         push bc
                push de
                ld   b, a
                push bc
                call fi_slot
                pop  bc
                jr   nc, .x
                push bc
                ld   a, (CUR_ROOM)
                call fi_gc
                pop  bc
                call fi_slot
.x:             pop  de
                pop  bc
                ret

; dp_pile — B = 9s + 7, D = centre col, E = max distance: NC + C = the col of
; the nearest item of the storey within it (FLOOR1: a marker cell in ROOM_MAP
; whose FI_CELL byte is a LEFT quarter, so every item col has one), d - k
; before d + k; CF = none.
; Keeps B, D, E.  Clobbers: A, C, HL.
dp_pile:        ld   c, 0                      ; C = k
.k:             ld   a, d
                sub  c
                call .t
                ret  nc
                ld   a, d
                add  a, c
                call .t
                ret  nc
                inc  c
                ld   a, e
                cp   c
                jr   nc, .k
                ret                            ; CF: none within E
.t:             cp   ROOM_COLS                 ; A = col (a negative one wraps)
                ccf
                ret  c
                push bc
                ld   c, a
                call cell_addr                 ; HL = ROOM_MAP (B, C) (keeps BC, DE)
                ld   a, (hl)
                cp   T_ITEM0
                jr   c, .no
                ld   a, (dp_rb)
                rlca
                and  1
                add  a, FI_CELL >> 8
                ld   h, a                      ; the storey's FI_CELL page, the map's L
                bit  3, (hl)                   ; quarter 1 / 3: a right one
                jr   nz, .no
                ld   a, c
                pop  bc
                ld   c, a                      ; C = its col
                or   a                         ; NC
                ret
.no:            pop  bc
                scf
                ret
                ASSERT (FI_CELL & $FF) == 0 && FL_S1 == $80 && ROOM_COLS == 32

; dp_free — B = 9s + 7, C = col c: CF = c..c+1 is not a free item footprint
; (dp_cell on both cols). Keeps BC, DE.  Clobbers: A, HL.
dp_free:        call dp_cell
                ret  c
                inc  c
                call dp_cell
                dec  c
                ret
; dp_cell — B = 9s + 7, C = col: CF unless (9s+6, C) and (9s+7, C) are T_AIR,
; (9s+8, C) is a floor (TF_FLOOR) and no unspent trap has col C.
dp_cell:        dec  b
                call cell_addr                 ; (keeps BC, DE)
                inc  b
                ld   a, (hl)
                or   a
                scf
                ret  nz
                call cell_addr
                ld   a, (hl)
                or   a
                scf
                ret  nz                        ; (a marker: another item's footprint)
                inc  b
                call cell_blocked              ; A = the floor cell's TILE_FLAGS
                dec  b
                rlca                           ; CF = TF_FLOOR
                ccf
                ret  c
                push de
                ld   a, (dp_rb)
                ld   e, a
                call trap_at                   ; Z = an unspent trap (keeps BC, DE)
                pop  de
                scf
                ret  z
                or   a
                ret
dp_tq:          DW   0                         ; type, qty
dp_w:           DB   0
dp_slot:        DB   0
dp_rb:          DB   0

