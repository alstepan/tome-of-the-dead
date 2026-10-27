;==============================================================================
; icons3.asm — C3-3 icon bar state, bank 3 (moved out of bank 2 for headroom:
; entered by far3 only when PD_ICONS is drained, or called from bank-3 code:
; panel.asm). icon_poll / icon_sig / panel_more / print6x stay
; in bank 2 (icons.asm).
;==============================================================================
; slot_act_tab / slot_act / abil_rank: bank 2 since D3-7 T0 (icons.asm), so
; the bank-7 icon logic (intent7.asm) calls them directly too.

;------------------------------------------------------------------------------
; icon_state — A = slot -> A = IS_HIDDEN / IS_GREY / IS_NORMAL (concept-screen
; §5: melee and the Bag never grey; ammo / item at 0 greys; 3E-T12: food /
; scrolls grey with none in the bag (QS_CACHE); an unlearned ability is an empty outline).
; IC1: the quick POTION slot's IS_NORMAL carries the pick (0..2 = Heal / Mana /
; Cure) in bits IS_PICK_SH..+1, so a pick change redraws it (slot_redraw ->
; qs_draw); FOOD / SCROLL pick / count changes are forced by pot_sync.
; Clobbers: A, C, HL (B, DE kept)      ~80 T (potion ~0.3k)
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
                ld   hl, QS_CACHE + QS_FOOD    ; 3E-T12: food / scroll stacks in the bag
                cp   SA_FOOD                   ; (R6 pot_sync keeps them): 0 greys
                jr   z, .qs
                ld   l, (QS_CACHE + QS_SCROLL) & $FF
                cp   SA_SCROLL
                jr   nz, .norm
.qs:            ld   a, (hl)
                jr   .cnt
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
                or   a
                jr   z, .grey                  ; none: the HEAL representative, greyed
                call pot_need                  ; IC1: the pick = the first potion whose
                jr   nz, .pk                   ; effect applies (fx_quick's order), else
                ld   a, (QS_CACHE + QS_POTION) ; the first present (quick-use: NO NEED)
                or   a
                jr   nz, .pk
                inc  a                         ; (E_POT without pot_sync: Heal)
.pk:            ld   l, a
                ld   a, IS_NORMAL - (1 << IS_PICK_SH)
.pb:            add  a, 1 << IS_PICK_SH
                srl  l
                jr   nc, .pb                   ; IS_NORMAL | potion index << IS_PICK_SH
                ret
                ASSERT IS_HIDDEN == 0 && IS_PICK_SH == 2 && ((IS_SEL | IS_MODE) & (3 << IS_PICK_SH)) == 0

;------------------------------------------------------------------------------
; pot_need — IC1: A = the potion types present (QS_CACHE + QS_POTION, pot_sync)
; whose effect quick-use would NOT refuse now, bit k = IT_P_HEAL + k (fx6
; pot_eff's tests: Heal HP < MAXHP, Mana MP < MAXMP, Cure a MIND / POISON /
; WEAK status); Z = none. icon_state's potion pick.
; Clobbers: A, C, HL, F (B, DE kept).   ~0.14k T
;------------------------------------------------------------------------------
pot_need:       ld   a, (ST_FLAGS)             ; the hero = status slot 0
                and  STS_MIND | STS_POISON | STS_WEAK
                add  a, $FF                    ; CF = something to cure
                rl   c
                ld   hl, (MP)                  ; L = MP, H = MAXMP
                ld   a, l
                cp   h                         ; CF = MP < MAXMP
                rl   c
                ld   hl, (P_ENTITIES + E_HP)   ; L = HP, H = MAXHP
                ld   a, l
                cp   h                         ; CF = HP < MAXHP
                rl   c                         ; C bits 0..2 = Heal / Mana / Cure
                ld   a, (QS_CACHE + QS_POTION)
                and  c
                ret
                ASSERT MAXMP == MP + 1 && E_MAXHP == E_HP + 1 && IT_P_MANA == IT_P_HEAL + 1 && IT_P_CURE == IT_P_HEAL + 2

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
; them); the first other change is ONE slot_redraw (panel.asm, ~2-4k T; IC1: a
; quick slot ~15k, only in a tick's 1st frame, else skipped and kept pending)
; and PD_ICONS stays set for the next item. A selection change or
; a redraw of the selected slot sets PD_INFO (IC1: not another slot's redraw).
; Clobbers: all but IX, IY.
;------------------------------------------------------------------------------
item_icons:
                ld   (ii_frame), a             ; IC1: 0 = the tick's 1st frame (item_icons_far)
                ld   hl, PANEL_DIRTY
                res  PD_ICONS_BIT, (hl)
                xor  a                         ; IC1: this pass answers QS_RECHK (a quick
                ld   (QS_RECHK), a             ; slot left undrawn below sets it again)
                call st_sig                    ; D3-8: the hero's status icons changed:
                ld   hl, STAT_SH               ; redraw both cells (bank 1, ~1k T)
                cp   (hl)
                jr   z, .ns
                ld   (hl), a
                ld   hl, st_icons_draw
                call far1                      ; A = the sig
.ns:
                call icon_sig
                ld   (ICON_SIG), a             ; (a slot left for the next item
                                               ; re-sets PD_ICONS itself)
                ld   a, (P_ENTITIES + E_POT)
                ld   hl, PANEL_POT_SH
                cp   (hl)
                jr   z, .np
                ld   (hl), a
                ld   a, (HERO_KIND)            ; count changed: redraw the potion slot
                add  a, (ICON_SH & $FF) + QS_SLOT0 + QS_POTION     ; (IC1: was pot_slot)
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
.slow:          ld   a, (HERO_KIND)            ; IC1: a quick slot (qs_draw, ~15k T with
                ld   c, a                      ; the far6 and the clear) is a big item:
                ld   a, b                      ; like INFO / FOOD only in a tick's 1st
                sub  QS_SLOT0                  ; frame (panel_tick's D5 rule: a 2nd-frame
                sub  c                         ; tick draws small items only); else it
                cp   QS_COUNT                  ; stays undrawn (ICON_SH back) and pending
                jr   nc, .now
                ld   a, (ii_frame)
                or   a
                jr   z, .now                   ; the tick's 1st frame
                ld   (hl), d                   ; not drawn: pending (QS_RECHK bit 7 ->
                ld   hl, QS_RECHK              ; icon_poll sets PD_ICONS in a 1st frame;
                set  7, (hl)                   ; no item_icons pass per 2nd-frame tick)
                jr   .next
.now:           ld   a, (SEL_SLOT)             ; IC1: the info line is the SELECTED
                cp   b                         ; slot's: another slot's redraw (a quick
                push af                        ; slot's pick / count) leaves it (pmix:
                ld   a, b                      ; no 25k T line + its row present per pickup)
                call slot_redraw               ; A = slot, E = state
                ld   hl, PANEL_DIRTY
                set  PD_ICONS_BIT, (hl)        ; maybe more: the next item
                pop  af
                ret  nz
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

ii_frame:       DB   0                         ; IC1: item_icons' A in (0 = a 1st frame)


