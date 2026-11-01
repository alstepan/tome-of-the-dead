;==============================================================================
; kit0.asm — DBG-1: the designer's debug start kit (game.md §1.4 "Start kit",
; DEBUG_KIT=1 builds only; 0 B in a release build). Bank 0 cold code (b0_code,
; main.asm: INCLUDEd LAST in b0_code, after every release routine there), run
; once per new game by FARB0 from R6 kit_add (pickup6.asm). Was R6 debug_kit +
; the R6 kit list extras + the bank-7 far6 hook in hero_st_init (DBG-1: the kit
; build was over in bank 7 and R6).
;==============================================================================

;------------------------------------------------------------------------------
; kit_b0 — FARB0 from kit_add (R6), right after hero_st_init: the kit counters
; (Mage: 5 spells rank 1, MP 40/40 with the Robe's +2 from hero_recalc;
; Warrior: bow, 20 arrows, 8 daggers, Power Strike + Whirlwind rank 1, MP 20/20)
; and the hero's whole list (base + extras) copied to KIT_LIST (low RAM: R6
; cannot read bank 0), which kit_add then walks as it walks kit_w / kit_m.
; Out: HL = KIT_LIST.   Clobbers: A, BC, DE, F.   ~0.5k T (cold)
;------------------------------------------------------------------------------
kit_b0:         ld   a, (HERO_KIND)
                or   a
                ld   hl, kit_bm
                ld   de, %0101010101           ; Mage: k0..4 rank 1
                ld   bc, (40 - 2) * $0101      ; MP / MAXMP (+ the Robe's 2 = 40)
                jr   nz, .s
                ld   hl, 8 | (20 << 8)         ; DAGGERS 8, ARROWS 20 (adjacent)
                ld   (DAGGERS), hl
                ld   a, 1
                ld   (HAS_BOW), a
                ld   hl, kit_bw
                ld   de, %0101                 ; Warrior: k0, k1 rank 1
                ld   bc, 20 * $0101
.s:             ld   (ARANK), de
                ld   (MP), bc                  ; MP, MAXMP
                ld   de, KIT_LIST
                push de
                ld   bc, KIT_LEN               ; the longer list (the Mage's 14 B copies 1 B past its 0)
                ldir
                pop  hl
                ret
                ASSERT ARROWS == DAGGERS + 1 && MAXMP == MP + 1
kit_bw:         KIT_W_BASE
                DB   IT_P_CURE, IT_P_MANA, IT_S_TELEPORT, IT_S_FEAR, IT_S_SLEEP, IT_S_ENCHANT
                DB   IT_F_MEAT, IT_BOOK, IT_H_HELM, IT_BOW
                DB   0
kit_bm:         KIT_M_BASE
                DB   IT_P_CURE, IT_S_TELEPORT, IT_S_FEAR, IT_S_SLEEP, IT_S_ENCHANT
                DB   IT_F_MEAT, IT_BOOK, IT_H_HELM
                DB   0
kit_b0_end:
KIT_LEN         EQU kit_bm - kit_bw
                ASSERT kit_b0_end - kit_bm <= KIT_LEN && KIT_LIST + KIT_LEN <= PF_ROWF
