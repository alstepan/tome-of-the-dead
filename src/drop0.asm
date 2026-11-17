;==============================================================================
; drop0.asm — BALANCE-PKG5 (balance_v2 §8 DROP_ALL_P): the any-kill food drop.
; B0_CODE2 (bank 0; bank3.asm rules: no data, no SMC, never pages $C000:
; far6 hands it back); bank 3 and R6 had no room. INCLUDEd by main.asm.
;==============================================================================

;------------------------------------------------------------------------------
; drop_any — farb (C = BANK_TEXT) from mon_drop (bank 3, drop3.asm) right after
; R6 drop_row, IX = the dead monster: never EF_RESPAWN (mon_drop's gate, which
; also covers every summon-made body: SQF_SUMM comes with SQF_RESP), never the
; lair boss (its path returns first). 8 in 100 (rng_mod 25 < 2: exact) -> one
; random food of the 5 (rnd(5): the sim's FOODS[rr * 5]), placed like a kind
; drop (R6 drop_put, DROP_NEAR). Independent of drop_row's roll: a Rat can drop
; its Cheese AND this (the sim's model). Moves food from the floor (3-4 now,
; items_ovl.asm) to kills.  Clobbers: all but IX.   no drop ~0.35k T (farb)
;------------------------------------------------------------------------------
DROP_ANY_N      EQU 25                  ; P = DROP_ANY_K / DROP_ANY_N = 0.08
DROP_ANY_K      EQU 2
drop_any:       ld   c, DROP_ANY_N
                call rng_mod                   ; A = 0..24 (gameplay RNG; keeps C, DE)
                cp   DROP_ANY_K
                ret  nc
                ld   c, IT_FOOD_HI - IT_FOOD_LO + 1
                call rng_mod
                add  a, IT_FOOD_LO             ; A = type: far6 passes A, DE, IX in
                ld   de, (1 << 8) | DROP_NEAR  ; D = qty 1, E = the search half-width
                ld   hl, drop_put              ; R6 pickup6.asm (L = 0: a 9th type, refused)
                jp   far6
