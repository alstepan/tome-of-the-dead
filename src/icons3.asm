;==============================================================================
; icons3.asm — C3-3 icon bar state, bank 3 (moved out of bank 2 for headroom:
; entered by far3 only when PD_ICONS is drained, or called from bank-3 code:
; intent3.asm, panel.asm). icon_poll / icon_sig / panel_more / print6x stay
; in bank 2 (icons.asm).
;==============================================================================
                IF (($ & $FF) + 2 * ICON_SLOTS) > 256    ; LP: keep the table in one page
                DS   256 - ($ & $FF), 0
                ENDIF
slot_act_tab:
                ; Warrior: Sword, Power Strike, Whirlwind, Daggers, Bow, food, potion, scroll, Bag, -
                DB SA_MELEE, SA_ABIL + 0, SA_ABIL + 1, SA_DAGGERS, SA_BOW
                DB SA_FOOD, SA_POTION, SA_SCROLL, SA_BAG, SA_EMPTY
                ; Mage: Staff, Spark, Firebolt, Frost Shard, Drain Life, Lightning, food, potion, scroll, Bag
                DB SA_MELEE, SA_ABIL + 0, SA_ABIL + 1, SA_ABIL + 2, SA_ABIL + 3
                DB SA_ABIL + 4, SA_FOOD, SA_POTION, SA_SCROLL, SA_BAG
                ASSERT K_KNIGHT == 0 && K_WIZARD == 1
                ASSERT (slot_act_tab >> 8) == ((slot_act_tab + 2 * ICON_SLOTS - 1) >> 8)

;------------------------------------------------------------------------------
; slot_act — A = slot 0..9 -> A = its SA_* for HERO_KIND.  Clobbers: A, HL
;------------------------------------------------------------------------------
slot_act:
                ld   l, a
                ld   a, (HERO_KIND)
                or   a
                ld   a, l
                jr   z, .k
                add  a, ICON_SLOTS
.k:             add  a, slot_act_tab & $FF     ; one page (ASSERTed)
                ld   l, a
                ld   h, slot_act_tab >> 8
                ld   a, (hl)
                ret

; abil_rank — A = ability index k -> A = its rank 0..3 (ARANK bits 2k..2k+1),
; Z = unlearned.  Clobbers: A, C, HL
abil_rank:
                ld   hl, (ARANK)
                add  a, a
                jr   z, .r
                ld   c, a
.sh:            srl  h
                rr   l
                dec  c
                jr   nz, .sh
.r:             ld   a, l
                and  3
                ret

;------------------------------------------------------------------------------
; icon_state — A = slot -> A = IS_HIDDEN / IS_GREY / IS_NORMAL (concept-screen
; §5: melee and the Bag never grey; ammo / item at 0 greys; food and scrolls
; are greyed until 3E; an unlearned ability is an empty outline).
; Clobbers: A, C, HL (B, DE kept)      ~80 T
;------------------------------------------------------------------------------
icon_state:
                call slot_act
                or   a
                ret  z                         ; SA_EMPTY -> IS_HIDDEN
                cp   SA_ABIL
                jr   c, .t
                sub  SA_ABIL
                call abil_rank
                ret  z                         ; unlearned: IS_HIDDEN
                ld   a, IS_NORMAL              ; 3D: MP < cost greys
                ret
.t:             cp   SA_DAGGERS
                jr   z, .dag
                cp   SA_BOW
                jr   z, .bow
                cp   SA_POTION
                jr   z, .pot
                cp   SA_FOOD
                jr   z, .grey
                cp   SA_SCROLL
                jr   z, .grey
.norm:          ld   a, IS_NORMAL              ; melee, Bag
                ret
.dag:           ld   a, (DAGGERS)
.cnt:           or   a
                jr   nz, .norm
.grey:          ld   a, IS_GREY
                ret
.bow:           ld   a, (HAS_BOW)
                or   a
                jr   z, .grey
                ld   a, (ARROWS)
                jr   .cnt
.pot:           ld   a, (P_ENTITIES + E_POT)
                jr   .cnt
                ASSERT IS_HIDDEN == 0

; slot_want — B = slot -> A = icon_state | IS_SEL (| IS_MODE in ICON MODE)
; if B = SEL_SLOT.  Clobbers: A, C, HL (B, DE kept)
slot_want:
                ld   a, b
                call icon_state
                ld   c, a
                ld   a, (SEL_SLOT)
                cp   b
                ld   a, c
                ret  nz
                or   IS_SEL
                ld   c, a
                ld   a, (ICON_MODE)
                or   a
                ld   a, c
                ret  z
                or   IS_MODE
                ret


;------------------------------------------------------------------------------
; item_icons — far3 via item_icons_far (PD_ICONS). Potion count changed: the potion slot is
; redrawn (its count digit). Level changed: the digit at (31, 19). Then the
; slots: a selection-only change is painted here (attrs, ~0.3k T each, all of
; them); the first other change is ONE slot_redraw (panel.asm, ~2-4k T) and
; PD_ICONS stays set for the next item. Any change sets PD_INFO.
; Clobbers: all but IX, IY.
;------------------------------------------------------------------------------
item_icons:
                ld   hl, PANEL_DIRTY
                res  PD_ICONS_BIT, (hl)
                call icon_sig
                ld   (ICON_SIG), a             ; (a slot left for the next item
                                               ; re-sets PD_ICONS itself)
                ld   a, (P_ENTITIES + E_POT)
                ld   hl, PANEL_POT_SH
                cp   (hl)
                jr   z, .np
                ld   (hl), a
                ld   a, (pot_slot)             ; count changed: redraw that slot
                add  a, ICON_SH & $FF
                ld   l, a
                ld   h, ICON_SH >> 8
                ld   (hl), IS_NONE
.np:            ld   a, (LVL)
                ld   hl, LVL_SH
                cp   (hl)
                call nz, lvl_draw
                ld   b, 0
.l:             call slot_want
                ld   e, a                      ; E = wanted
                ld   a, b
                add  a, ICON_SH & $FF
                ld   l, a
                ld   h, ICON_SH >> 8
                ld   d, (hl)                   ; D = drawn
                ld   a, e
                xor  d
                jr   z, .next
                ld   (hl), e
                and  ~(IS_SEL | IS_MODE) & $FF
                jr   nz, .slow                 ; more than the selection changed
                ld   a, d
                cp   IS_NONE
                jr   z, .slow
                push bc
                call sel_paint
                pop  bc
                call .info
.next:          inc  b
                ld   a, b
                cp   ICON_SLOTS
                jr   c, .l
                ret
.slow:          ld   a, b                      ; A = slot, E = state
                call slot_redraw
                ld   hl, PANEL_DIRTY
                set  PD_ICONS_BIT, (hl)        ; maybe more: the next item
.info:          ld   hl, PANEL_DIRTY
                set  PD_INFO_BIT, (hl)
                ret
                ASSERT (ICON_SH >> 8) == ((ICON_SH + ICON_SLOTS - 1) >> 8)

; sel_paint — B = slot, D = the slot's drawn state, E = the new one: the
; selection look over its 3 x 2 cells. Every icon has black paper, so the base
; attr is the cell with paper 0 (drawn IS_MODE: ink = its paper). New IS_MODE:
; inverse (ink -> paper, ink black); IS_SEL: PAPER blue (greyed $07 -> $0F);
; else the base. Marks it.  Clobbers: A, BC, DE, HL      ~0.5k T
; SMC: .om+1 / .nm+1 = the drawn / new state, patched per call.
sel_paint:
                ld   a, b
                add  a, a
                add  a, b                      ; col = 3 * slot
                ld   c, a
                ld   b, ICON_ROW
                push bc                        ; for pmark_rect
                call attr_addr                 ; HL = attr (B, C)
                ld   a, d
                ld   (.om+1), a                ; SMC: the drawn state
                ld   a, e
                ld   (.nm+1), a                ; SMC: the new state
                ld   e, 2
.r:             push hl
                ld   d, ICON_W
.cell:
.om:            ld   a, 0                      ; SMC: drawn state
                and  IS_MODE
                ld   a, (hl)
                jr   z, .base
                rrca                           ; inverse drawn: ink = its paper bits
                rrca
                rrca
                and  7
                ld   c, a
                ld   a, (hl)
                and  $C0
                or   c
                jr   .new
.base:          and  ~$38 & $FF                ; paper off
.new:           ld   c, a                      ; C = base attr
.nm:            ld   a, 0                      ; SMC: new state
                bit  6, a
                jr   nz, .inv
                rlca                           ; IS_SEL (bit 7) -> CF
                ld   a, c
                jr   nc, .put
                or   ATTR_P_SEL
                jr   .put
.inv:           ld   a, c
                and  7
                jr   nz, .ik
                ld   a, 7                      ; a blank (ink 0) cell: white paper
.ik:            rlca
                rlca
                rlca                           ; ink -> paper, ink 0
                ld   b, a
                ld   a, c
                and  $C0
                or   b
.put:           ld   (hl), a
                inc  l
                dec  d
                jr   nz, .cell
                pop  hl
                ld   a, l
                add  a, ATTR_STRIDE
                ld   l, a
                jr   nc, .c
                inc  h
.c:             dec  e
                jr   nz, .r
                pop  bc
                ld   de, (ICON_W << 8) | 2
                jp   pmark_rect                ; (B, C)
                ASSERT IS_MODE == 1 << 6 && IS_SEL == 1 << 7

; lvl_draw — A = LVL: LVL_SH = A, its digit at (31, 19) (attr $46 by
; panel_init; 3C shows the reserved state, 3D moves it). Clobbers: A, BC, DE, HL
lvl_draw:
                ld   (LVL_SH), a
                cp   10
                jr   c, .d
                ld   a, 9
.d:             add  a, '0'
                ld   hl, P_NUMBUF
                ld   (hl), a
                inc  l
                ld   (hl), 0
                dec  l
                ld   b, ICON_ROW + 1
                ld   e, LVL_COL * 8
                call print6
                ASSERT ((LVL_COL * 8) & 7) == 0 && LVL_COL * 8 + 6 <= 256    ; print6 x rule
                ld   bc, ((ICON_ROW + 1) << 8) | LVL_COL
                ld   de, (1 << 8) | 1
                jp   pmark_rect
LVL_COL         EQU 31

pot_slot:       DB   0                         ; the quick-potion slot (panel_init)

