;==============================================================================
; abil6.asm — 3F-T6 tier abilities that need R6 (r6.asm rules: far6 only, results
; in HL, bank 6 at $C000 while it runs). game.md §8.10 (gear wear), §9.1, §9.6.
;   parry6    far6 from deal_hit: the parry roll + the NOTCH decision
;   mummy6    far6 from do_attack: the Mummy's hit drains FOOD
;   acid6     far6 from do_attack: a Black Widow bite, ACID 1 in 4
;   wear_slot the wear step (m - 1, or destroyed at -3); the LINE and the
;             recalc are deferred: WEAR_PEND -> wear_apply (hunger_turn,
;             end_turn), never on the input tick
; The rage and the parry compare live in bank 3 (combat3.asm).
;==============================================================================
                ASSERT TX_CMB_ACID_ARM == TX_CMB_NOTCH + 1 && TX_CMB_ACID_HELM == TX_CMB_NOTCH + 2
                ASSERT TX_CMB_WPN_BREAKS == TX_CMB_NOTCH + 3 && TX_CMB_ARM_BREAKS == TX_CMB_NOTCH + 4
                ASSERT TX_CMB_HELM_BREAKS == TX_CMB_NOTCH + 5 && WS_WEAPON == 0 && WS_ARMOUR == 1 && WS_HELM == 2

;------------------------------------------------------------------------------
; parry6 — In: E = chance /256, D = 0 melee / else a shot. Out: L = 1 parried.
; A melee parry notches the worn weapon 1 in 2 (fists: nothing to wear).
; Clobbers: A, BC, DE, HL (IX kept).   ~0.4k T
;------------------------------------------------------------------------------
parry6:
                call rng_next
                cp   e
                ld   l, 0
                ret  nc
                ld   a, d
                or   a
                jr   nz, .y
                call rng_next
                and  1
                jr   nz, .y
                ld   a, WS_WEAPON
                call wear_slot
.y:             ld   l, 1
                ret

mummy6:         ld   b, FOOD_MUMMY
                jp   food_sub                  ; FOOD floors at 0 (hunger6.asm)

acid6:          call rng_next
                and  3
                ret  nz                        ; 1 in 4
                ld   a, WS_ARMOUR
                call wear_slot
                ret  nc
                ld   a, WS_HELM                ; no armour: the helmet, else nothing
                ; fall through
;------------------------------------------------------------------------------
; wear_slot — A = WS_WEAPON / WS_ARMOUR / WS_HELM: m - 1 on the worn item; at the
; floor (-3) the slot empties. ORs the slot's bit into WEAR_PEND (bit 2 s = wear,
; bit 2 s + 1 = break: two events of one turn both stay). Out: CF = 1 slot empty.
; Clobbers: A, BC, HL.   ~0.2k T
;------------------------------------------------------------------------------
wear_slot:
                ld   c, a
                add  a, a
                add  a, c
                add  a, WORN & $FF
                ld   l, a
                ld   h, HIGH WORN
                ASSERT (WORN & $FF) + 3 * WS_HELM + 2 < 256     ; one page: no carry into H
                ld   a, (hl)
                or   a
                scf
                ret  z
                inc  l
                inc  l                         ; ISTATE
                ld   a, (hl)
                and  IST_M_MASK
                cp   IST_M_M3
                jr   z, .brk
                ld   a, (hl)
                sub  IST_M_ONE                 ; m - 1 (bits 0-4 kept)
                ld   (hl), a
                ld   a, c
                jr   .pend
.brk:           xor  a
                ld   (hl), a                   ; ISTATE, QTY, TYPE: the slot is empty
                dec  l
                ld   (hl), a
                dec  l
                ld   (hl), a
                ld   a, c
                add  a, 3                      ; the break bits follow the three wear bits
.pend:          add  a, wear_bit & $FF
                ld   l, a
                ld   h, HIGH wear_bit
                ld   a, (hl)
                ld   hl, WEAR_PEND
                or   (hl)
                ld   (hl), a
                or   a                         ; NC
                ret
wear_bit:       DB   1, 4, 16, 2, 8, 32        ; wear w / a / h, then break w / a / h
                ASSERT (wear_bit & $FF) + 6 <= 256 && WS_WEAPON == 0

;------------------------------------------------------------------------------
; wear_apply — hunger_turn, WEAR_PEND != 0: hero_recalc once, then for every affected
; slot (weapon, armour, helm) its line (the BREAK line when it broke, else the
; notch / acid line) and its worn cell.  Clobbers: A, BC, DE, HL.
; ~6k T + ~4k per affected slot, once per wear turn
;------------------------------------------------------------------------------
wear_apply:
                ld   hl, WEAR_PEND
                ld   d, (hl)
                ld   (hl), 0
                push de
                call hero_recalc
                pop  de
                ld   c, 0                      ; C = slot
.l:             ld   a, d
                and  3
                jr   z, .n
                sub  1                         ; 0 = wear, 1 / 2 = break
                jr   z, .w
                ld   a, 3                      ; the break lines follow the wear lines
.w:             add  a, c
                add  a, TX_CMB_NOTCH
                push bc
                push de
                call msg_push
                pop  de
                pop  bc
                ld   hl, wear_ty
                ld   a, c
                add  a, l
                ld   l, a
                ld   a, (hl)
                push bc
                push de
                call worn_cell
                pop  de
                pop  bc
.n:             srl  d
                srl  d
                inc  c
                ld   a, c
                cp   3
                jr   c, .l
                ret
wear_ty:        DB   IT_WPN_LO, IT_ARM_LO, IT_HELM_LO
                ASSERT (wear_ty & $FF) + 3 <= 256      ; `add a, l` above has no carry
