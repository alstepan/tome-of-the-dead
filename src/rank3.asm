;==============================================================================
; rank3.asm — D3-7, bank 3: the ability descriptor for the bank-7 ability code
; (abil_*7.asm), which cannot read the bank-3 tables (combat_data3.asm).
;==============================================================================

;------------------------------------------------------------------------------
; abil_load — far3 from intent7 ic_disp, A = ABL_* (a ranked ability must be
; learned: ARANK rank 1..3; a rank of 0 reads the rank-1 row). ABIL_DESC =
; its ab_def row (ABD_STRIDE B), ABIL_RK = its rank row (RK_STRIDE B: ab_rank
; at the hero's rank, ab_ammo for the dagger / bow). The class's ability index
; k for ARANK: Mage k = ABL_*, Warrior k = ABL_* - ABL_POWER.
; Out: L = ABD_FLAGS (ABF_*), B = ABL_* (far3 passes BC / HL out).
; Clobbers: A, C, DE, HL      ~0.6k T (2 LDIRs)
;------------------------------------------------------------------------------
abil_load:
                ld   b, a                      ; B = ABL
                add  a, a
                add  a, a
                add  a, b
                add  a, a                      ; 10 * ABL (<= 80)
                ld   e, a
                ld   d, 0
                ld   hl, ab_def
                add  hl, de
                ld   de, ABIL_DESC
                ld   c, ABD_STRIDE             ; B is the ABL: LDIR on C alone
                call .cp
                ld   a, b
                sub  ABL_RANKED
                jr   nc, .ammo                 ; A = ammo row 0 / 1
                ld   a, b
                cp   ABL_POWER
                jr   c, .k
                sub  ABL_POWER                 ; Warrior: k = 0 / 1
.k:             push de
                call abil_rank                 ; bank 2: A = rank, Z = 0 (A, C, HL)
                pop  de
                jr   nz, .r
                inc  a                         ; unlearned: the rank-1 row
.r:             dec  a
                ld   c, a
                ld   a, b
                add  a, a
                add  a, b                      ; 3 * ABL
                add  a, c                      ; row = 3 * ABL + rank - 1
                jr   .row
.ammo:          add  a, ABL_RANKED * RANK_MAX  ; ab_ammo follows ab_rank (ASSERTed)
.row:           ld   l, a
                add  a, a
                add  a, l
                add  a, a                      ; 6 * row (<= 138)
                ld   l, a
                ld   h, 0
                push de
                ld   de, ab_rank
                add  hl, de
                pop  de
                ld   c, RK_STRIDE
                call .cp
                ld   a, (ABIL_DESC + ABD_FLAGS)
                ld   l, a
                ret
.cp:            ld   a, (hl)                   ; C bytes HL -> DE (B kept)
                ld   (de), a
                inc  hl
                inc  de
                dec  c
                jr   nz, .cp
                ret
                ASSERT ab_ammo == ab_rank + ABL_RANKED * RANK_MAX * RK_STRIDE
                ASSERT ABL_RANKED == ABL_DAGGER && ABL_BOW == ABL_DAGGER + 1 && ABL_WHIRL == ABL_POWER + 1
                ASSERT RANK_MAX == 3 && RK_STRIDE == 6 && ABD_STRIDE == 10

;------------------------------------------------------------------------------
; rank_sync — far3 (D3-9b reuses it after a learn / rank-up): RANK_ROWS row k <-
; the ab_rank row of the hero's current rank, for every k whose ARANK rank is
; != 0 (rank 0 rows are left alone). Class base: Mage ability k, Warrior
; ABL_POWER + k (k = 0..4 is safe for both: a Warrior's bits 4..9 are 0).
; HL walks the ab_rank class rows (RANK_MAX * RK_STRIDE = 18 B per k), BC the
; RANK_ROWS destination (LDIR leaves it advanced); the end test is the low
; byte of the last row + RR_STRIDE, as RANK_ROWS never crosses a page.
; Clobbers: A, BC, DE, HL      ~1.2k T
;------------------------------------------------------------------------------
rank_sync:
                ld   hl, ab_rank
                ld   a, (HERO_KIND)
                or   a                         ; K_KNIGHT == 0: Warrior
                jr   nz, .m
                ld   de, ABL_POWER * RANK_MAX * RK_STRIDE
                add  hl, de
.m:             ld   de, (ARANK)               ; DE shifts right 2 bits per k
                ld   bc, RANK_ROWS
.l:             ld   a, e
                and  3
                jr   z, .skip
                push hl
                push de
                dec  a
                ld   e, a
                add  a, a
                add  a, e
                add  a, a                      ; 6 * (rank - 1)
                ld   e, a
                ld   d, 0
                add  hl, de
                ld   d, b
                ld   e, c
                ld   bc, RK_STRIDE
                ldir
                ld   b, d                      ; BC = the next row
                ld   c, e
                pop  de
                pop  hl
                jr   .adv
.skip:          ld   a, c
                add  a, RK_STRIDE              ; RANK_ROWS $E0..$FE: no carry
                ld   c, a
.adv:           srl  d
                rr   e
                srl  d
                rr   e
                push de
                ld   de, RANK_MAX * RK_STRIDE
                add  hl, de
                pop  de
                ld   a, c
                cp   (RANK_ROWS + RANK_N * RK_STRIDE) & $FF
                jr   nz, .l
                ret
                ASSERT (RANK_ROWS >> 8) == ((RANK_ROWS + RANK_N * RK_STRIDE - 1) >> 8)
                ASSERT RR_STRIDE == RK_STRIDE && RANK_N == 5

;------------------------------------------------------------------------------
; proj_rel — far3 from the bank-7 releases (spell_fire; ammo_fire may share
; it): A = ABL_*, DE = its 6-B rank row -> proj_fire with HL = DE, E =
; FXD_DELAY 0 (the release tick: the projectile appears now). far3 takes HL
; as its target, so the row comes in DE.  Out / Clobbers: proj_fire's.
;------------------------------------------------------------------------------
proj_rel:
                ex   de, hl
                ld   e, 0
                jp   proj_fire

    IF DEBUG_KIT
;------------------------------------------------------------------------------
; debug_kit — far3 at the end of hero_st_init (game.md §1.4 start kit, debug
; builds only; 3E: delete this block, the call in hero_st_init and DEBUG_KIT).
; Mage: 5 spells rank 1, MP 40/40. Warrior: bow, 20 arrows, 8 daggers, Power
; Strike + Whirlwind rank 1, MP 20/20. Then rank_sync.
; Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
debug_kit:
                ld   a, (HERO_KIND)
                or   a
                ld   hl, %0101                 ; Warrior: k0, k1 rank 1
                ld   b, 20
                jr   nz, .m
                ld   a, 1
                ld   (HAS_BOW), a
                ld   a, 20
                ld   (ARROWS), a
                ld   a, 8
                ld   (DAGGERS), a
                jr   .s
.m:             ld   hl, %0101010101           ; Mage: k0..4 rank 1
                ld   b, 40
.s:             ld   (ARANK), hl
                ld   a, b
                ld   (MP), a
                ld   (MAXMP), a
                jr   rank_sync
    ENDIF
