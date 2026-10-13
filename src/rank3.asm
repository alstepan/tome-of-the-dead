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
; D3-8e: when the accept already ran proj_prep for this ability (act_prep,
; pf_prep = A + 1), only the walk runs here (proj_go: ~10k T of set-up and
; pf_cands off the fire tick); otherwise (a poked test turn) the whole cast.
proj_rel:
                ex   de, hl
                ld   e, 0
                ld   c, a
                ld   a, (pf_prep)
                dec  a
                cp   c
                ld   a, c
                jp   z, proj_go
                jp   proj_fire

; proj_pre — far3 from the bank-7 accept (act_begin): A = ABL_*, DE = its
; rank row -> proj_part (HL = DE, E = FXD_DELAY = ACT_FIRE_TICK - TURN_TICK:
; the ticks to the release): the set-up, the candidates and the first
; PF_PRE_HITS strikes, valid until the release (nothing moves in between:
; the monster phase is deferred).  Clobbers: all but IX
proj_pre:
                ex   de, hl
                ld   c, a
                ld   a, (TURN_TICK)            ; (0 on the input tick)
                neg
                add  a, ACT_FIRE_TICK
                ld   e, a
                ld   a, c
                jp   proj_part

;------------------------------------------------------------------------------
; melee_hit — far3 from the bank-7 power attacks (abil_melee7.asm
; melee_strike): one Power Strike / Whirlwind blow (game.md §6.2) of IX =
; hero on slot A, ABIL_DESC loaded (abil_load). hit_roll with B = ABD_HIT
; (Power Strike +2; Whirlwind 0 + its RK_EFFECT: the rank-3 to-hit +2); a
; hit: dmg = 1d(KT_DIE) + KT_BONUS (the weapon, kind_tab: the 3E gear joins
; there) + RK_BONUS (Whirlwind +1 / +2), x 2 with ABF_DMGX2 (saturating),
; then deal_hit, C = ABD_DTY (PHYS); Power Strike also EFX_STUNNED, E =
; RK_EFFECT (always; turns 1 / 1 / 2: deal_hit applies it to a survivor
; only, halves it on R, refuses it under STUN_GUARD / IMMF_STUN).
; RNG (prototype §6.2 order): d20, 1dN, deal_hit's effect chance.
; Out: L = HP lost, H = 1 hit / 0 miss (far3 passes HL out); IX = hero.
; Clobbers: all but IX.   ~1.3k T + deal_hit (~0.7k + ~1.5k per message)
;------------------------------------------------------------------------------
melee_hit:
                push af                        ; the target slot
                ld   hl, ABIL_DESC + ABD_FLAGS
                ld   c, (hl)                   ; C = ABF_*
                inc  hl
                ld   b, (hl)                   ; B = ABD_HIT
                ld   a, (ABIL_RK + RK_EFFECT)
                ld   e, a                      ; E = RK_EFFECT
                bit  ABF_DMGX2_B3, c
                jr   nz, .h
                add  a, b                      ; Whirlwind: + the rank's to-hit
                ld   b, a
                ld   e, 0                      ; (no effect)
.h:             pop  af
                push af
                push de
                push bc
                call hit_roll                  ; Z = miss (A, BC, DE, HL)
                pop  bc
                pop  de
                ld   hl, 0
                jr   z, .x                     ; miss: L = 0, H = 0
                push de
                push bc
                KFIELD KT_DIE
                ld   c, a
                call rng_mod                   ; 0..N-1 (keeps C, DE)
                inc  a
                ld   d, a
                KFIELD KT_BONUS
                add  a, d
                ld   hl, ABIL_RK + RK_BONUS
                add  a, (hl)
                pop  bc                        ; C = ABF_*
                pop  de                        ; E = the effect parameter
                ld   b, a                      ; B = dmg
                ld   a, (ABIL_DESC + ABD_DTY)
                bit  ABF_DMGX2_B3, c
                ld   c, a
                jr   z, .d
                sla  b                         ; Power Strike: x 2
                jr   nc, .s
                ld   b, $FF
.s:             or   EFX_STUNNED << DH_EFX_SHIFT
                ld   c, a
.d:             pop  af                        ; A = slot
                call deal_hit                  ; L = HP lost (all but IX)
                ld   h, 1
                ret
.x:             pop  af
                ret
ABF_DMGX2_B3    EQU 4
                ASSERT ABF_DMGX2 == 1 << ABF_DMGX2_B3 && ABD_HIT == ABD_FLAGS + 1 && DTY_PHYS == 0
