;==============================================================================
; nm3var0.asm — NEW-MON3 T8: the row-31 ALIAS table (new_monsters.md §3). DATA ONLY (bank-0 B0_CODE2, read with
; BANK_TEXT paged); the A-1 patch that applies it is T9.
;
; Kind id 31 (K_ALIAS) is the Fire Imp as ASSEMBLED (variant A: D4 / D6) and the Frost Wraith (variant B: D5 / D7 / D8),
; chosen per level; the two never share a depth, and descent discards every monster, so a level only ever holds one.
; An entry = DW address, DB value A (Fire Imp, = the byte assembled there), DB value B (Frost Wraith): the patch writes A or B
; at address, both ways (Imp -> Wraith -> Imp), so no copy of the original is kept. Each group ends with DW 0 and is
; applied from code that can write its bank (nothing here pages):
;   nm3_var_b2   bank 2, always mapped ($8000..$BFFF): kind_tab columns, rk_tab
;   nm3_var_b3   bank 3 kx_tab row 31 (8 B): its page must be at $C000 (bank-0 code cannot write it directly)
;   nm3_var_r6   bank 6 R6: gu_tab row 31 (fid0, fcnt), drop_tab row `drop_imp` (kind byte: K_ALIAS | 0 = no drop)
;   nm3_var_img  the sequence masters' ksm_tab word of row 31 (ksm_ia | ksm_wr): an address of the UNPACKED image (SQ_IMG,
;                rewritten by every pool_* unpack): patch it after pl_begin's unpack, not before
; Not here (code, T9): the name (TX_NM_KNIGHT + 31 = "FIRE IMP"; the Wraith's is TX_NM_FIRE_IMP + 1 = "ICE SHADE") and the
; weight (3 for both: lp_wt row 31 does not change). Row 31's KT_BW (3) / lp_wt / KT_SEQ are the same for both.
; tests/combat_tables.py checks every A byte against the assembled row and every B byte against the §4 spec.
;==============================================================================
    MACRO VB dst, val_a, val_b
                DW   dst
                DB   val_a, val_b
    ENDM

; the two kx rows (8 B each, the same macros as kx_tab row 31 / the spec): the table reads their bytes ({b})
nm3_kx_a:       KX_IMP_ROW
nm3_kx_b:       KX_WRAITH_ROW
                ASSERT $ - nm3_kx_a == 2 * KX_STRIDE

nm3_var_b2:
                VB kind_tab + KT_HP + K_ALIAS,    NM3_IMP_HP,    NM3_WR_HP
                VB kind_tab + KT_ATK + K_ALIAS,   NM3_IMP_ATK,   NM3_WR_ATK
                VB kind_tab + KT_EVA + K_ALIAS,   NM3_IMP_EVA,   NM3_WR_EVA
                VB kind_tab + KT_DIE + K_ALIAS,   NM3_IMP_DIE,   NM3_WR_DIE
                VB kind_tab + KT_BONUS + K_ALIAS, NM3_IMP_BONUS, NM3_WR_BONUS
                VB kind_tab + KT_BH + K_ALIAS,    NM3_IMP_BH,    NM3_WR_BH
                VB kind_tab + KT_FLAGS + K_ALIAS, NM3_IMP_FLAGS, NM3_WR_FLAGS
                VB kind_tab + KT_ATTR + K_ALIAS,  NM3_IMP_ATTR,  NM3_WR_ATTR
                VB rk_tab + K_ALIAS,              RK_IMP,        0
                DW   0
nm3_var_b3:
                VB kx_tab + K_ALIAS * KX_STRIDE + 0, {b nm3_kx_a + 0}, {b nm3_kx_b + 0}    ; RES B0 (phys / fire / cold / shock)
                VB kx_tab + K_ALIAS * KX_STRIDE + 1, {b nm3_kx_a + 1}, {b nm3_kx_b + 1}    ; RES B1 (drain / dark)
                VB kx_tab + K_ALIAS * KX_STRIDE + 2, {b nm3_kx_a + 2}, {b nm3_kx_b + 2}    ; RES B2 (the weak mask)
                VB kx_tab + K_ALIAS * KX_STRIDE + 3, {b nm3_kx_a + 3}, {b nm3_kx_b + 3}    ; KX_IMM
                VB kx_tab + K_ALIAS * KX_STRIDE + 4, {b nm3_kx_a + 4}, {b nm3_kx_b + 4}    ; KX_XP
                VB kx_tab + K_ALIAS * KX_STRIDE + 5, {b nm3_kx_a + 5}, {b nm3_kx_b + 5}    ; KX_DEF
                VB kx_tab + K_ALIAS * KX_STRIDE + 6, {b nm3_kx_a + 6}, {b nm3_kx_b + 6}    ; KX_MELEE dty | efx
                VB kx_tab + K_ALIAS * KX_STRIDE + 7, {b nm3_kx_a + 7}, {b nm3_kx_b + 7}    ; KX_MELEE chance | turns
                DW   0
nm3_var_r6:
                VB gu_tab + GU_STRIDE * K_ALIAS,     KFID_IMP,  KFID_WRAITH
                VB gu_tab + GU_STRIDE * K_ALIAS + 1, KFCNT_IMP, KFCNT_WRAITH
                VB drop_imp,                         K_ALIAS,   0
                DW   0
nm3_var_img:
                VB ksm_tab + 2 * K_ALIAS,     low ksm_ia,  low ksm_wr
                VB ksm_tab + 2 * K_ALIAS + 1, high ksm_ia, high ksm_wr
                DW   0
nm3_var_end:
                ASSERT KX_MELEE + 2 == KX_STRIDE && GU_STRIDE == 2
