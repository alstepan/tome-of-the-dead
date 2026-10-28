;==============================================================================
; icons6.asm — IC1 the 16x16 item icons (game.md §8.11 Q5), the R6 region
; (r6.asm rules: far6 only from other banks, results in BC / DE / HL, no SMC).
; The icon table icons16 (assets/gfx/icons/icons16.asm, 43 x 32 = 1,376 B raw: 45 logical icons, the 3 potions share one shape; generated
; by tools/icons16.py) follows this code in R6: one copy, read only here, so
; every draw site reaches it through these routines (the ISR never reads it).
;   icon_slot  far6 from the page overlay (bag grid, worn row, description)
;   worn_draw  far6 from panel_init (bank 3); worn_cell: fx_done (equip / remove)
;   qs_draw    far6 from slot_redraw (bank 3): a quick FOOD / POTION / SCROLL slot
; All draw into the bank-5 screen (always mapped): an icon is COPIED (not
; ORed) into 2 x 2 byte-aligned cells, its 4 attrs = the type's floor ink on
; black (item_ink, lowram.asm: it_tab) or ICONS16_INK_PH for a placeholder.
;==============================================================================

;------------------------------------------------------------------------------
; icon_slot — A = slot 0..23 (a BAG / WORN record, PAGE_SLOT numbering; >= 24
; = none), D = char row, E = col of the 2 x 2 cells. An item -> its icon; an
; empty worn slot -> its placeholder (ICONS16_PH + worn slot); an empty bag
; slot / none -> the 4 cells' bitmap cleared, attrs untouched.
; Out: L = 0 cleared, else drawn.  Clobbers: A, BC, DE, HL.  ~1.3k T
; ic_slot — the same with B = row, C = col (R6 callers).
;------------------------------------------------------------------------------
icon_slot:      ld   b, d
                ld   c, e                      ; (far6 passes DE in, not BC)
ic_slot:        ld   e, a                      ; E = slot
                cp   PG_SLOT_WORN + WORN_SLOTS
                jr   nc, ic_clr
                add  a, a
                add  a, e
                ld   l, a
                ld   h, HIGH BAG               ; HL = the record (WORN follows BAG)
                ld   a, (hl)
                sub  IT_BAG_LO
                jr   nc, ic_draw               ; A = icon index (bag types only in records)
                ld   a, e
                sub  PG_SLOT_WORN
                jr   c, ic_clr                 ; an empty bag slot
                add  a, ICONS16_PH             ; an empty worn slot: its placeholder
                ; fall through
;------------------------------------------------------------------------------
; ic_draw — A = icon index 0..ICONS16_COUNT-1, B = row, C = col: the icon
; copied into the 2 x 2 cells, their attrs = its ink on black. Out: L != 0.
; ic_clr  — B = row, C = col: the 2 x 2 cells' bitmap cleared. Out: L = 0.
; Clobbers: A, BC, DE, HL.   ~1.2k T (16 lines x 2 B x ~33 T + the 4 attrs)
;------------------------------------------------------------------------------
ic_draw:        ld   d, a                      ; D = index
                sub  ICONS16_PH
                ld   a, ICONS16_INK_PH
                jr   nc, .ph
                ld   a, d
                add  a, IT_BAG_LO
                call item_ink                  ; A = attr (keeps BC, DE)
.ph:            ld   e, $FF                    ; copy mask: the icon as is
                jr   ic_blit
ic_clr:         xor  a                         ; attr 0 = none written; mask 0 = clear
                ld   d, a
                ld   e, a
; ic_blit — A = attr (0: attrs untouched), D = index, E = byte mask, B / C cell
ic_blit:        push af                        ; [attr]
                call attr_addr                 ; HL = attr (B, C)   (BC, DE kept)
                push hl                        ; [attr address]
                ld   a, h
                and  3
                rlca
                rlca
                rlca
                or   SCREEN_BITMAP >> 8
                ld   b, a
                ld   c, l                      ; BC = bitmap line 0 of the cell
                ld   a, d
                call ic_addr                   ; HL = the icon's 32 B (keeps BC, DE)
                ld   a, e
                ld   d, b
                ld   e, c                      ; DE = the screen
                ld   c, a                      ; C = mask
                call .cell                     ; upper cells: rows 0..7
                ld   a, e
                add  a, 32                     ; the next char row ...
                ld   e, a
                jr   c, .th                    ; ... crossed a third: D is right already
                ld   a, d
                sub  8
                ld   d, a
.th:            call .cell                     ; lower cells: rows 8..15
                pop  hl                        ; attr address
                pop  af                        ; attr
                or   a
                jr   z, .none
                ld   (hl), a
                inc  l
                ld   (hl), a
                ld   de, ATTR_STRIDE - 1
                add  hl, de
                ld   (hl), a
                inc  l                         ; (L != 0: col + 1 of a row's attrs)
                ld   (hl), a
                ret
.none:          ld   l, a                      ; L = 0: cleared
                ret
; .cell — 2 quarters (16 B at HL, FLOOR1 layout: 8 lines each) & C -> the
; cells at DE / DE + 1; D advances 8, E kept.  Clobbers: A, B
.cell:          call .q
                ld   a, d
                sub  8
                ld   d, a
                inc  e
                call .q
                dec  e
                ret
.q:             ld   b, 4                      ; 2 lines a pass
.ln:            DUP  2
                ld   a, (hl)
                and  c
                ld   (de), a
                inc  hl
                inc  d
                EDUP
                djnz .ln
                ret
                ASSERT ICONS16_BYTES == 32 && ICONS16_COUNT * ICONS16_BYTES < $10000
                ASSERT ICONS16_PH == IT_COUNT - IT_BAG_LO && ICONS16_AMMO_DAGGER == ICONS16_PH + WORN_SLOTS
                ASSERT ICONS16_AMMO_ARROW == ICONS16_AMMO_DAGGER + 1 && ICONS16_COUNT == ICONS16_AMMO_ARROW + 1
                ASSERT PG_SLOT_WORN == BAG_SLOTS && WORN == BAG + BAG_SLOTS * IR_STRIDE && (BAG & $FF) == 0
                ASSERT (BAG_SLOTS + WORN_SLOTS) * IR_STRIDE <= 256 && ATTR_STRIDE == 32

;------------------------------------------------------------------------------
; 3E-T6 floor-item ink (game.md §8.11 Q1 + "3E simplification" 2: the ink is a
; pure function of the TYPE): it_tab, one byte per type (FLOOR1: moved here
; from low RAM; every caller is R6). FLOOR1: the floor
; item is its 16x16 icon (fi_cells) in this ink; the icon sites (icons6.asm)
; use it too.
;------------------------------------------------------------------------------
; it_byte — A = item type (< IT_COUNT): A = it_tab[type]. Keeps BC, DE. Clobbers HL.
it_byte:        ld   hl, it_tab
                add  a, l
                ld   l, a
                adc  a, h
                sub  l
                ld   h, a
                ld   a, (hl)
                ret

; DEBUG_KIT only (0 B in the release build): item_glyph / item_ink get a LIVE FL type, so
; a type >= IT_COUNT (a corrupt floor entry) bumps IT_BAD (expect 0) before the lookup.
    IF DEBUG_KIT
it_byte_live:   cp   IT_COUNT
                jr   c, it_byte
                ld   hl, IT_BAD
                inc  (hl)
                jr   it_byte
IT_BYTE_LIVE    EQU it_byte_live
    ELSE
IT_BYTE_LIVE    EQU it_byte
    ENDIF

; item_ink — A = item type: A = its floor attr (ink on black; 0 = no glyph).
; Keeps BC, DE. Clobbers HL.
item_ink:       call IT_BYTE_LIVE
                ld   h, a
                and  7
                bit  IT_BRIGHT_BIT, h
                ret  z
                or   $40                       ; BRIGHT
                ret

; it_tab: type -> class << 4 | BRIGHT << 3 | ink (paper 0). SINGLE SOURCE in
; tools/items_model.py ITEM_INK + glyph(); tests/items_gen.py G0 checks this
; table against it. (FLOOR1: the class nibble is documentation only — the old
; floor class glyph; nothing reads it.)
IT_BRIGHT_BIT   EQU 3
    MACRO ITB cls, attr
                DB   ((cls) << 4) | (((attr) >> 3) & 8) | ((attr) & 7)
    ENDM
IC_NONE         EQU 0
IC_FLASK        EQU 1
IC_AMMO         EQU 2
IC_FOOD         EQU 3
IC_PAGES        EQU 4
IC_WEAPON       EQU 5
IC_WORN         EQU 6
it_tab:         ITB  IC_NONE, 0                ; IT_NONE
                ITB  IC_FLASK, $42             ; IT_POTION (legacy / PROTO)
                ITB  IC_AMMO, $47              ; dagger
                ITB  IC_AMMO, $46              ; arrow
                ITB  IC_NONE, 0                ; key (no floor entry)
                ITB  IC_FOOD, $06              ; carrot
                ITB  IC_FOOD, $44              ; apple
                ITB  IC_FOOD, $04              ; pear
                ITB  IC_FOOD, $46              ; cheese
                ITB  IC_FOOD, $42              ; meat
                ITB  IC_FLASK, $42             ; Heal
                ITB  IC_FLASK, $45             ; Mana
                ITB  IC_FLASK, $44             ; Cure
                ITB  IC_PAGES, $45             ; Teleport
                ITB  IC_PAGES, $46             ; Fear
                ITB  IC_PAGES, $44             ; Sleep
                ITB  IC_PAGES, $47             ; Enchant
                ITB  IC_PAGES, $43             ; book
                ITB  IC_WEAPON, $06            ; bow
                DUP  IT_WPN_W_HI - IT_WPN_W_LO + 1
                ITB  IC_WEAPON, $07            ; Warrior blades
                EDUP
                DUP  IT_WPN_M_HI - IT_WPN_M_LO + 1
                ITB  IC_WEAPON, $06            ; Mage staves
                EDUP
                DUP  IT_HELM_HI - IT_ARM_LO + 1
                ITB  IC_WORN, $07              ; armour, helmets
                EDUP
                DUP  IT_CHARM_HI - IT_CHARM_LO + 1
                ITB  IC_WORN, $06              ; charms
                EDUP
                ASSERT $ - it_tab == IT_COUNT && IT_KEY == 4 && IT_F_CARROT == 5 && IT_P_HEAL == 10
                ASSERT IT_S_TELEPORT == 13 && IT_BOOK == 17 && IT_BOW == 18 && IT_WPN_W_LO == 19
                ASSERT IT_WPN_M_LO == IT_WPN_W_HI + 1 && IT_ARM_LO == IT_WPN_M_HI + 1
                ASSERT IT_HELM_LO == IT_ARM_HI + 1 && IT_CHARM_LO == IT_HELM_HI + 1

;------------------------------------------------------------------------------
; ic_addr — A = a LOGICAL icon index (type - IT_BAG_LO, ICONS16_PH + worn slot,
; the floor ammo): HL = its 32 B in icons16. FLOOR1 (user 2026-10-27): the 3
; potions share Heal's shape (their inks differ): logical 6 / 7 -> physical 5,
; >= 8 -> - 2.  Keeps BC, DE.  Clobbers A, F.   ~0.2k T
;------------------------------------------------------------------------------
ic_addr:        cp   ICONS16_SHARE_LO
                jr   c, .p
                sub  ICONS16_SHARE_N
                cp   ICONS16_SHARE_LO
                jr   nc, .p
                ld   a, ICONS16_SHARE_LO - 1   ; Mana / Cure -> Heal's shape
.p:             ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl                    ; * ICONS16_BYTES
                push de
                ld   de, icons16
                add  hl, de
                pop  de
                ret
                ASSERT ICONS16_SHARE_LO == IT_P_MANA - IT_BAG_LO && ICONS16_SHARE_LO - 1 == IT_P_HEAL - IT_BAG_LO
                ASSERT ICONS16_SHARE_N == 2 && IT_P_CURE == IT_P_MANA + 1

;------------------------------------------------------------------------------
; worn_draw — the panel's 4 worn cells (rows LOG_ROW..+1, cols GEAR_COL + 2k,
; WS_* order: weapon, armour, helmet, charm): the worn item's icon, else its
; slot placeholder (game.md §8.11 Q5 "Panel worn cells"); marked for present.
; far6 from panel_init (bank 3, per level). (EQUIP / REMOVE: worn_cell.)
; Clobbers: A, BC, DE, HL.   ~6k T
;------------------------------------------------------------------------------
worn_draw:      ld   bc, (LOG_ROW << 8) | GEAR_COL
                ld   a, PG_SLOT_WORN
.l:             push af
                push bc
                call ic_slot
                pop  bc
                pop  af
                inc  c
                inc  c
                inc  a
                cp   PG_SLOT_WORN + WORN_SLOTS
                jr   c, .l
                ld   bc, (LOG_ROW << 8) | GEAR_COL
                ld   de, ((2 * WORN_SLOTS) << 8) | 2
                jp   pmark_rect
                ASSERT GEAR_COL + 2 * WORN_SLOTS == ROOM_COLS

;------------------------------------------------------------------------------
; worn_cell — A = a gear type: the panel cell of its worn slot redrawn (the
; slot's item now, else its placeholder), marked for present. fx_done (EQUIP /
; REMOVE: A = the item equipped / removed).  Clobbers: A, BC, DE, HL.  ~2.6k T
;------------------------------------------------------------------------------
worn_cell:      ld   bc, (LOG_ROW << 8) | GEAR_COL
                ld   e, PG_SLOT_WORN
                ld   d, IT_ARM_LO
                call .st
                ld   d, IT_HELM_LO
                call .st
                ld   d, IT_CHARM_LO
                call .st
                ld   a, e
                push bc
                call ic_slot
                pop  bc
                ld   de, (2 << 8) | 2
                jp   pmark_rect
.st:            cp   d                         ; the slot ranges ascend (WS_* order)
                ret  c
                inc  e
                inc  c
                inc  c
                ret
                ASSERT IT_ARM_LO > IT_WPN_LO && IT_HELM_LO > IT_ARM_LO && IT_CHARM_LO > IT_HELM_LO
                ASSERT WS_WEAPON == 0 && WS_ARMOUR == 1 && WS_HELM == 2 && WS_CHARM == 3

;------------------------------------------------------------------------------
; qs_draw — far6 from slot_redraw (bank 3; the caller has cleared the slot's
; 3 x 2 cells, bitmap + attrs 0): A = the quick class (QS_*), D = the slot's
; col, E = its icon_state (the potion pick in bits 2-3). Draws at (ICON_ROW,
; D) the icon of the item quick-use would use (game.md §8.11 rulings 3,
; fx_quick): FOOD bag_pick mode 0, SCROLL mode 1, POTION IT_P_HEAL + the pick
; (icon_state: Heal -> Mana -> Cure skipping refused effects, pot_need); an
; empty class -> its representative APPLE / HEAL / TELEPORT (the caller greys
; it, IS_GREY). Then at (ICON_ROW + 1, D + 2) the count OF THAT TYPE (all its
; stacks, capped 9) in ATTR_HUD.
; Clobbers: A, BC, DE, HL.   ~4-9k T (bag_pick ~0.5-6k, icon ~1.2k, digit ~1k)
;------------------------------------------------------------------------------
qs_draw:        push de                        ; [D = col]
                ld   b, IT_FOOD_LO
                ld   d, 2 * (IT_FOOD_HI - IT_FOOD_LO + 1) + 0   ; mode 0: the lowest type
                ld   l, IT_F_APPLE
                cp   QS_FOOD
                jr   z, .pk
                cp   QS_SCROLL
                jr   nz, .pot
                ld   b, IT_SCR_LO
                ld   d, 2 * (IT_SCR_HI - IT_SCR_LO + 1) + 1     ; mode 1: the largest stack
                ld   l, IT_S_TELEPORT
.pk:            push hl                        ; [the representative]
                call bag_pick                  ; A = type / IT_NONE
                pop  hl
                or   a
                jr   nz, .ty
                ld   a, l
                jr   .ty
.pot:           ld   a, e
                rrca
                rrca
                and  3
                add  a, IT_P_HEAL
.ty:            pop  bc                        ; B = col
                push bc
                push af                        ; [type]
                ld   c, b
                ld   b, ICON_ROW
                sub  IT_BAG_LO
                call ic_draw
                pop  af                        ; A = type: its QTY over the bag
                ld   hl, BAG
                ld   bc, BAG_SLOTS << 8        ; C = sum
.c:             cp   (hl)
                jr   nz, .n
                inc  l
                ld   e, a
                ld   a, c
                add  a, (hl)                   ; (<= 20 x 9: no overflow)
                ld   c, a
                ld   a, e
                dec  l
.n:             inc  l
                inc  l
                inc  l
                djnz .c
                ld   a, c
                cp   10
                jr   c, .d
                ld   a, 9
.d:             add  a, '0'
                ld   hl, P_NUMBUF
                ld   (hl), a
                inc  l
                ld   (hl), 0
                dec  l
                pop  bc                        ; B = col
                ld   a, b
                add  a, 2                      ; the count column
                ld   c, a
                add  a, a
                add  a, a
                add  a, a
                ld   e, a                      ; pixel x: a cell (print6 x rule)
                ld   b, ICON_ROW + 1
                push bc
                call print6
                pop  bc
                call attr_addr
                ld   (hl), ATTR_HUD
                ret
                ASSERT (BAG & $FF) == 0 && BAG_SLOTS * IR_STRIDE <= 256 && IR_QTY == 1 && IR_STRIDE == 3
                ASSERT IT_P_CURE == IT_P_HEAL + 2 && IT_F_APPLE >= IT_FOOD_LO && IT_F_APPLE <= IT_FOOD_HI
                ASSERT IT_S_TELEPORT == IT_SCR_LO && QS_FOOD == 0 && QS_POTION == 1 && QS_SCROLL == 2
