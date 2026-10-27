;==============================================================================
; icons6.asm — IC1 the 16x16 item icons (game.md §8.11 Q5), the R6 region
; (r6.asm rules: far6 only from other banks, results in BC / DE / HL, no SMC).
; The icon table icons16 (assets/gfx/icons/icons16.asm, 1,376 B raw, generated
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
                ld   l, d
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl                    ; index * ICONS16_BYTES
                ld   a, e
                ld   de, icons16
                add  hl, de                    ; HL = the icon's 32 B
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
; .cell — 8 lines of 2 bytes (HL) & C -> (DE); D advances 8.  Clobbers: A, B
.cell:          ld   b, 8
.ln:            ld   a, (hl)
                and  c
                ld   (de), a
                inc  hl
                inc  e
                ld   a, (hl)
                and  c
                ld   (de), a
                inc  hl
                dec  e
                inc  d
                djnz .ln
                ret
                ASSERT ICONS16_BYTES == 32 && ICONS16_COUNT * ICONS16_BYTES < $10000
                ASSERT ICONS16_PH == IT_COUNT - IT_BAG_LO && ICONS16_COUNT == ICONS16_PH + WORN_SLOTS
                ASSERT PG_SLOT_WORN == BAG_SLOTS && WORN == BAG + BAG_SLOTS * IR_STRIDE && (BAG & $FF) == 0
                ASSERT (BAG_SLOTS + WORN_SLOTS) * IR_STRIDE <= 256 && ATTR_STRIDE == 32

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
