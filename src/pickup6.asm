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
; pot_sync — E_POT := the sum of the potion stacks' QTY in BAG; 3E-T12: also
; QS_CACHE + QS_FOOD / QS_SCROLL := the number of food / scroll stacks (the
; icon bar's FOOD / SCROLL grey test, icons3.asm icon_state), PD_ICONS when
; one of those changed (the potion count reaches the panel by icon_poll).
; Clobbers: A, HL, F (BC, DE kept).   ~1.6k T (20 slots)
;------------------------------------------------------------------------------
pot_sync:
                push bc
                push de
                ld   hl, BAG
                ld   bc, BAG_SLOTS << 8        ; B = slots, C = potions
                ld   de, 0                     ; D = food stacks, E = scroll stacks
.l:             ld   a, (hl)
                inc  l                         ; -> QTY
                sub  IT_FOOD_LO
                cp   IT_FOOD_HI - IT_FOOD_LO + 1
                jr   nc, .nf
                inc  d
.nf:            sub  IT_POT_LO - IT_FOOD_LO    ; (a food wraps past both tests)
                cp   IT_POT_HI - IT_POT_LO + 1
                jr   nc, .np
                ld   a, (hl)
                add  a, c
                ld   c, a
                jr   .nx
.np:            sub  IT_SCR_LO - IT_POT_LO
                cp   IT_SCR_HI - IT_SCR_LO + 1
                jr   nc, .nx
                inc  e
.nx:            inc  l
                inc  l
                djnz .l
                ld   a, c
                ld   (P_ENTITIES + E_POT), a
                ld   hl, QS_CACHE + QS_FOOD
                ld   a, d
                call .qs
                ld   l, (QS_CACHE + QS_SCROLL) & $FF
                ld   a, e
                call .qs
                pop  de
                pop  bc
                ret
.qs:            cp   (hl)
                ret  z
                ld   (hl), a
                ld   a, (PANEL_DIRTY)
                or   PD_ICONS
                ld   (PANEL_DIRTY), a
                ret
                ASSERT (BAG & $FF) + BAG_SLOTS * IR_STRIDE <= 256 && IR_QTY == 1 && IR_STRIDE == 3
                ASSERT IT_POT_LO == IT_FOOD_HI + 1 && IT_SCR_LO == IT_POT_HI + 1
                ASSERT ((QS_CACHE + QS_FOOD) >> 8) == ((QS_CACHE + QS_SCROLL) >> 8)

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
; mon_drop — far6 from deal_hit's kill path (bank 3), IX = the dead monster (EF_DYING
; set, still in place). game.md §8.11 Q11 + pickup/drop rulings 2:
;  - EF_RESPAWN: nothing.
;  - the lair boss: the first kill of kind LP_BOSS in LVL_LAIR on this level
;    (LF_UNIQUE; STAND-IN until 3F gives bosses their own kind / IMMF_BOSS:
;    an escort of the boss's kind killed first takes the drop) -> the depth's
;    unique (uniq_tab; D4 Mage: Bone Staff; D8 none), placed anywhere on the
;    storey, "BOSS DROPS " + name.
;  - else the first drop_tab row of its kind: 1 in N on the gameplay RNG
;    (rng_mod; rolled only for a kind with a row); arrows (qty 3) only in a
;    Warrior run (no roll for the Mage). No line (the glyph appears).
; Clobbers: all but IX.   no row ~0.2k T; a drop ~12k T (placement + ap_stamp)
;------------------------------------------------------------------------------
mon_drop:
                bit  EF_RESPAWN_BIT, (ix+E_FLAGS)
                ret  nz
                ld   a, (LVL_LAIR)
                cp   (ix+E_ROOM)
                jr   nz, .row
                ld   a, (LP_BOSS)
                cp   (ix+E_KIND)
                jr   nz, .row
                ld   hl, LVL_FLAGS
                bit  LF_UNIQUE_BIT, (hl)
                jr   nz, .row                  ; (the boss's kind as an ordinary monster)
                set  LF_UNIQUE_BIT, (hl)
                ld   a, (LVL_DEPTH)
                dec  a
                cp   UNIQ_DEPTHS
                ret  nc                        ; D8: none
                cp   3
                jr   nz, .u
                ld   a, (HERO_KIND)
                add  a, a
                add  a, a                      ; Mage: 4 -> +3 below = 7
                add  a, 3
.u:             ld   hl, uniq_tab              ; uniq_tab[A]: hla is bank 3 (not paged)
                add  a, l
                ld   l, a
                adc  a, h
                sub  l
                ld   h, a
                ld   a, (hl)
                push af                        ; [type]
                ld   bc, (1 << 8) | DROP_WHOLE
                call drop_put                  ; CF = lost (never: entry 32 is kept free)
                pop  bc                        ; B = type
                ret  c
                ld   a, b
                ld   e, S3_BOSS_DROPS          ; "BOSS DROPS " + name (bank 1)
                ld   hl, it_line
                jp   far1
.row:           ld   hl, drop_tab
                ld   b, DROP_ROWS
.r:             ld   a, (ix+E_KIND)
                cp   (hl)
                jr   z, .hit
                inc  hl
                inc  hl
                inc  hl
                djnz .r
                ret
.hit:           inc  hl
                ld   d, (hl)                   ; D = type
                inc  hl
                ld   c, (hl)                   ; C = 1 in N
                ld   e, 1                      ; E = qty
                ld   a, d
                cp   IT_ARROW
                jr   nz, .q
                ld   a, (HERO_KIND)
                or   a
                ret  nz                        ; arrows: Warrior runs only
                ld   e, DROP_ARROWS
.q:             push de
                call rng_mod                   ; A = 0..N-1 (A, B, HL)
                pop  de
                or   a
                ret  nz
                ld   a, d
                ld   b, e
                ld   c, DROP_NEAR
                ; fall through
;------------------------------------------------------------------------------
; drop_put — a new FLOOR_LIST entry under the dead body IX.
; In : A = type, B = qty, C = search half-width (DROP_NEAR 3; DROP_WHOLE: the
;      whole storey, a unique). Placement (§8.11 rulings 2): the body's centre
;      col (x + w/2) on its storey's standing row 9s+7, else the nearest col
;      within +-C (left first) — a cell is free when ROOM_MAP shows T_AIR
;      there (no item glyph = no live entry, the FLOOR_LIST invariant; also
;      no wall / decor) and no unspent trap has that col (3E-T16:
;      trap_at). List: the first FL_EMPTY entry, among 0..30 for an
;      ordinary drop, 0..31 for a unique (entries fill from 0 and the
;      generator uses <= 17, so entry 31 is the last to fill: it stays the
;      unique's; a pickup freeing a lower entry after all 32 were used is
;      the one case this differs from "<= 31 used"). NOT here (3F, with the
;      D8 lectern swap it guards): §8.11 Q1's "a 60..63-glyph drop in the D8
;      lair / Sanctum is lost".
;      Arrows never merge into a stack (one entry per drop; pickup merges).
; Out: CF = 1 lost (silently); else the entry written and the cell stamped
;      (far7 ap_stamp_a: map + attr shadow + floor inks).
; Clobbers: all but IX.
;------------------------------------------------------------------------------
drop_put:
                ld   l, a
                ld   h, b
                ld   (dp_tq), hl               ; type, qty
                ld   a, c
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
.sp:            ; --- the cell ---
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
                ld   e, 0                      ; E = distance
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
                ret                            ; no free cell: lost
.try:           cp   ROOM_COLS
                ret  nc                        ; off the room (also a negative col)
                ld   c, a
                call cell_addr                 ; HL = ROOM_MAP (B, C) (A)
                ld   a, (hl)
                or   a
                ret  nz                        ; not T_AIR
                push de                        ; 3E-T16: nor a trap col (hidden or
                ld   a, (dp_rb)                ; known, unspent: R6 trap_at)
                ld   e, a
                call trap_at
                pop  de
                ret  z
                pop  af                        ; found: leave .s
                ld   a, (dp_slot)
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
                ASSERT T_AIR == 0 && (FLOOR_LIST & $FF) == 0 && FL_EMPTY == $FF
                ASSERT FL_ROOM == 0 && FL_COL == 1 && FL_ITEM == 2 && FL_QTY == 3 && FL_S1 == $80
DROP_NEAR       EQU 3
DROP_WHOLE      EQU ROOM_COLS - 1
DROP_ARROWS     EQU 3
dp_tq:          DW   0                         ; type, qty
dp_w:           DB   0
dp_slot:        DB   0
dp_rb:          DB   0

; drop_tab (§8.11 rulings 2, 5 rows x 3 B: kind, type, 1 in N). The kinds are
; the defs.asm stand-in aliases until 3F (K_ORC / K_NECRO = K_GOBLIN: their
; rows are shadowed by the Goblin's; K_ARCHER = K_SKELETON: Skeletons drop
; the archer's arrows meanwhile). First match wins.
drop_tab:       DB   K_RAT,    IT_F_CHEESE, 4
                DB   K_GOBLIN, IT_F_APPLE,  4
                DB   K_ORC,    IT_F_MEAT,   3
                DB   K_ARCHER, IT_ARROW,    2
                DB   K_NECRO,  IT_P_MANA,   3
DROP_ROWS       EQU ($ - drop_tab) / 3
; uniq_tab (§8.6 / §8.11: 8 B): D1..D7 by depth - 1, then the D4 Mage variant
uniq_tab:       DB   IT_H_KING, IT_A_SILK, IT_A_GRAVE, IT_W_CLEAVER
                DB   IT_C_SCARAB, IT_C_GRAVE, IT_H_MIRROR, IT_W_BONE
UNIQ_DEPTHS     EQU 7
                ASSERT DROP_ROWS == 5 && $ - uniq_tab == 8 && K_KNIGHT == 0 && K_WIZARD == 1
