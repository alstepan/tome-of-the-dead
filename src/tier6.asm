;==============================================================================
; tier6.asm — 3F-T5: the FRESH-room unit generation (lp_gen) with the §9.6 tier
; roll, the golden flag and the depth-scaled spawn hp (R6; r6.asm rules: far6
; only, no SMC, no bank-3 code / data), plus the monster drop row scan +
; drop_tab moved here from bank 3 (drop3.asm). Byte-exact reference:
; tools/levelgen.py lp_enter (fit / tier_roll / k3_hp / k3_weight), tier_odds,
; tier_pick (game.md §9.4.3, §9.6, §9.7 R1). Moving the whole unit loop here
; (it was bank-3 lp_fit / .unit / .fresh, ~200 B) costs ONE far6 per room entry
; (~0.45k T) instead of one per tier roll / unit; bank 3 had 10 B free.
;
; Entries (far6; A and F are lost on the way back):
;   lp_gen     lp_enter (bank 3) for a FRESH record (LP_RECP, LPV_ROOM, the
;              spawn stream in GEN_RNG, LPV_BOSS = 0): writes the record's
;              entries {kind byte, hp} and returns B = their number.
;              Ordinary room: quota x fit with the tier roll; the lair: the
;              boss (LP_BOSS | LEK_GOLD on the golden depths, weight + 1) and
;              one base-tier escort (cap LP_SIGMA_CAP, never rolled).
;   drop_row   mon_drop (bank 3), IX = the dead monster: the drop_tab scan.
; kind_hp is also the contract for every other creation path (bank-3 lp_spawn
; computes the same for E_MAXHP; the T12 trickle must call it): row hp +
; (depth - 1) (§9.1), a golden boss 2 x that + 6 (§9.7 R1).
;==============================================================================
TIER_N          EQU 9                       ; tiered bases (Slime, Vampire, Mummy and the uniques have none)
TIER3_MIN_DEPTH EQU 4                       ; §9.6: D1-D3 never roll tier 3
TIER_SHIFT2     EQU 16                      ; T2 odds per Δ unit (of 256)
TIER_SHIFT3     EQU 8
TIER_DELTA_MAX  EQU 2                       ; Δ = clamp(LVL - depth, -2, +2)
T2_CAP          EQU 160
T3_CAP          EQU 80
LPG_MINW        EQU LP_BS                   ; lp_gen scratch: the lightest LP_KINDS weight (lp_place sets LP_BS later)

;------------------------------------------------------------------------------
; lp_gen — see above. fit (game.md §9.4.3 reservation fit, 3F-D2 fallback):
;   i = rnd(4); the rolled tier row (iff the kind has tiers, FRESH ordinary
;   room) is tried first, then LP_KINDS[i] at base, then the other kinds in list
;   order at base; a kind is accepted iff LP_SIG + w + LP_RES <= cap, then
;   LP_SIG += w. The lightest kind always passes (LP_DISCARD stays 0).
; Clobbers: all but IX, IY.   ~0.9k T for a 2-unit room (the far6 ~0.45k included)
;------------------------------------------------------------------------------
lp_gen:         ld   hl, (LP_RECP)
                ld   a, (hl)
                and  LR_CNT_MASK
                ld   b, a                      ; B = the quota
                inc  hl
                ex   de, hl                    ; DE = entry 0
                xor  a
                ld   (LP_SIG), a
                ld   (LP_RES), a
                ld   a, (LVL_LAIR)
                ld   hl, LPV_ROOM
                cp   (hl)
                jr   z, .lair
                ; ---- an ordinary room: minW, then the cap = max(LP_SIGMA_INIT, LP_RMAX x minW) ----
                push bc
                ld   b, 4
                ld   hl, LP_KINDS
                ld   c, $FF
.mw:            ld   a, (hl)
                inc  l                         ; (LP_KINDS: one page, ASSERTed)
                add  a, lp_wt6 & $FF
                push hl
                ld   l, a
                ld   h, lp_wt6 >> 8
                ld   a, (hl)
                pop  hl
                cp   c
                jr   nc, .mn
                ld   c, a
.mn:            djnz .mw
                ld   a, c
                ld   (LPG_MINW), a
                ld   a, (LP_RMAX)
                ld   b, a
                xor  a
.mu:            add  a, c
                djnz .mu
                cp   LP_SIGMA_INIT
                jr   nc, .sg
                ld   a, LP_SIGMA_INIT
.sg:            ld   (LPV_N), a                ; the cap (scratch until .place)
                pop  bc                        ; B = quota
                ld   c, 0                      ; C = units written
                inc  b
                jr   .fn
.fl:            push bc                        ; LP_RES = (units left after this) x minW
                ld   a, (LPG_MINW)
                ld   c, a
                xor  a
                dec  b
                jr   z, .rz
.rm:            add  a, c
                djnz .rm
.rz:            ld   (LP_RES), a
                pop  bc
                push bc
                push de
                call gen_fit
                pop  de
                pop  bc
                jr   c, .fn                    ; (never: the reservation)
                call gen_unit
                inc  c
.fn:            djnz .fl
                ld   b, c
                ret
                ; ---- the lair: the boss, then 1 base-tier escort (cap 12) ----
.lair:          ld   a, 1
                ld   (LPV_BOSS), a
                ld   a, (LP_BOSS)
                ld   c, a                      ; kind byte (| LEK_GOLD)
                and  LEK_KIND_MASK
                add  a, lp_wt6 & $FF
                ld   l, a
                ld   h, lp_wt6 >> 8
                ld   a, (hl)
                bit  LEK_GOLD_BIT, c           ; golden: weight + 1 (levelgen.py k3_weight)
                jr   z, .bw
                inc  a
.bw:            ld   (LP_SIG), a
                ld   a, c
                call gen_unit
                ld   a, LP_SIGMA_CAP
                ld   (LPV_N), a
                push de
                call gen_fit                       ; LP_RES = 0
                pop  de
                ld   b, 1
                ret  c
                call gen_unit
                inc  b
                ret

; unit — A = kind byte, DE = the entry -> {kind byte, kind_hp}, DE += 2. Keeps B, C.
gen_unit:      ld   (de), a
                inc  de
                push bc
                call kind_hp
                pop  bc
                ld   (de), a
                inc  de
                ret

; fit — LPV_N = cap, LP_SIG, LP_RES; LPV_BOSS set = no tier roll (the escort).
; -> NC: A = the kind row, LP_SIG += its weight; CF: none fits, LP_DISCARD += 1.
; Clobbers: A, BC, DE, HL.
gen_fit:       call gen_step
                ld   a, l
                and  3
                ld   c, a                      ; C = i = rnd(4)
                ld   a, (LPV_BOSS)
                or   a
                jr   nz, .nt
                ld   a, c
                add  a, LP_KINDS & $FF
                ld   l, a
                ld   h, LP_KINDS >> 8
                ld   a, (hl)                   ; the rolled base row
                push bc
                call tier_row
                pop  bc
                or   a
                jr   z, .nt                    ; no tier row (none exists / rolled the base)
                call gen_tryk
                ret  nc
.nt:            ld   a, c
                call gen_tryi
                ret  nc
                ld   b, 0
.j:             ld   a, b
                cp   c
                jr   z, .jn
                call gen_tryi
                ret  nc
.jn:            inc  b
                ld   a, b
                cp   4
                jr   c, .j
                ld   hl, LP_DISCARD
                inc  (hl)
                scf
                ret
; gen_tryi — A = LP_KINDS index; gen_tryk — A = kind row: accept iff LP_SIG + w + LP_RES <= cap.
; NC: A = the row, LP_SIG += w; CF: rejected. Clobbers: A, DE, HL.
gen_tryi:          add  a, LP_KINDS & $FF
                ld   l, a
                ld   h, LP_KINDS >> 8
                ld   a, (hl)
gen_tryk:          ld   e, a
                add  a, lp_wt6 & $FF
                ld   l, a
                ld   h, lp_wt6 >> 8
                ld   d, (hl)                   ; D = w
                ld   a, (LP_SIG)
                add  a, d
                ld   hl, LP_RES
                add  a, (hl)
                ld   l, a
                ld   a, (LPV_N)
                sub  l
                ret  c                         ; cap < total
                ld   a, (LP_SIG)
                add  a, d
                ld   (LP_SIG), a               ; (the sum is <= 12: no carry, the NC stays)
                ld   a, e
                ret

; step — one xorshift 7,9,8 step of the spawn stream (GEN_RNG) -> HL (= bank-3 lg_step, which R6 cannot call).
gen_step:      ld   hl, (GEN_RNG)
                ld   a, h
                rra
                ld   a, l
                rra
                xor  h
                ld   h, a
                ld   a, l
                rra
                ld   a, h
                rra
                xor  l
                ld   l, a
                xor  h
                ld   h, a
                ld   (GEN_RNG), hl
                ret

;------------------------------------------------------------------------------
; tier_row — A = a base row -> A = its tier row to try first, 0 = none (the kind has
; no tiers: NO stream step; or the roll gave the base). The odds (out of 256):
;   T2 = max(0, T2_BASE[d] + 16 Δ)   T3 = d >= 4 ? max(0, T3_BASE[d] + 8 Δ) : 0
;   r = the low byte of one stream step: r < T3 -> tier 3 (tier 2 if the base
;   has none), r < T3 + T2 -> tier 2, else base. The caps (160 / 80) cannot be
;   reached (ASSERTed below), the floors only at D1 for LVL < 1 (kept: exact for
;   every LP_LVL <= 120). Clobbers: A, BC, DE, HL.   ~0.5k T tiered, ~0.15k else
;------------------------------------------------------------------------------
tier_row:       ld   hl, tier_tab
                ld   b, TIER_N
.f:             cp   (hl)
                jr   z, .hit
                inc  hl
                inc  hl
                inc  hl
                djnz .f
                xor  a
                ret
.hit:           inc  hl
                ld   e, (hl)                   ; tier-2 row
                inc  hl
                ld   d, (hl)                   ; tier-3 row, 0 = none
                push de
                ld   a, (LVL_DEPTH)
                ld   c, a
                ld   a, (LP_LVL)
                sub  c
                add  a, TIER_DELTA_MAX         ; x = clamp(LVL - d, -2, 2) + 2
                jp   m, .x0
                cp   2 * TIER_DELTA_MAX + 1
                jr   c, .xk
                ld   a, 2 * TIER_DELTA_MAX
                jr   .xk
.x0:            xor  a
.xk:            add  a, a
                add  a, a
                add  a, a
                ld   b, a                      ; B = 8 x (the T3 step)
                ld   a, c
                add  a, T2_BASE & $FF
                ld   l, a
                ld   h, T2_BASE >> 8
                ld   a, b
                add  a, a                      ; 16 x
                add  a, (hl)
                sub  TIER_SHIFT2 * TIER_DELTA_MAX   ; T2_BASE + 16 (x - 2), floor 0
                jr   nc, .t2
                xor  a
.t2:            ld   d, a                      ; D = T2
                ld   e, 0                      ; E = T3
                ld   a, c
                cp   TIER3_MIN_DEPTH
                jr   c, .r
                add  a, T3_BASE & $FF
                ld   l, a
                ld   h, T3_BASE >> 8
                ld   a, b
                add  a, (hl)
                sub  TIER_SHIFT3 * TIER_DELTA_MAX
                jr   nc, .t3
                xor  a
.t3:            ld   e, a
.r:             call gen_step
                ld   a, l                      ; r
                cp   e
                pop  hl                        ; H = tier-3 row, L = tier-2 row (flags kept)
                jr   nc, .n3
                ld   a, h                      ; r < T3: tier 3, tier 2 if the base has none
                or   a
                ret  nz
                ld   a, l
                ret
.n3:            sub  e                         ; r - T3 < T2  <=>  r < T3 + T2
                cp   d
                ld   a, l
                ret  c
                xor  a
                ret

; tiered bases: base row, tier-2 row, tier-3 row (0 = none). Order irrelevant (a scan).
tier_tab:       DB   K_RAT,      K_GIANT_RAT,     K_RABBIT_RAT
                DB   K_BAT,      K_SCREECH,       0
                DB   K_GOBLIN,   K_SLINGER,       0
                DB   K_SPIDER,   K_BLACK_WIDOW,   0
                DB   K_SKELETON, K_SKEL_GUARD,    K_SKEL_KNIGHT
                DB   K_GHOST,    K_POLTERGEIST,   0
                DB   K_ORC,      K_ORC_BERSERK,   K_ORC_BOUNCER
                DB   K_ARCHER,   K_SNIPER,        0
                DB   K_NECRO,    K_BONE_CALLER,   0
                ASSERT ($ - tier_tab) == 3 * TIER_N
; §9.6 odds bases, indexed by depth (1..8; entry 0 unused)
                ALIGN 16                       ; each 9-byte table inside one page (H loaded per table)
T2_BASE:        DB   0, 24, 48, 64, 72, 80, 88, 96, 96
                ALIGN 16
T3_BASE:        DB   0, 0, 0, 0, 16, 24, 32, 40, 48
                ASSERT LEVELS == 8
                ASSERT 96 + TIER_SHIFT2 * TIER_DELTA_MAX <= T2_CAP && 48 + TIER_SHIFT3 * TIER_DELTA_MAX <= T3_CAP
                ASSERT (LP_KINDS >> 8) == ((LP_KINDS + 3) >> 8)

; §9.3 weights by kind row: the same list as bank-3 lp_wt (LP_WT_ROWS, lpop3.asm); R6 cannot read bank 3
lp_wt6:         LP_WT_ROWS
                ASSERT $ - lp_wt6 == K_COUNT && ((lp_wt6 + K_COUNT) >> 8) == (lp_wt6 >> 8)

;------------------------------------------------------------------------------
; kind_hp — A = kind byte (row | LEK_*) -> A = row hp + (depth - 1); golden:
; 2 x that + 6. Clobbers: C, HL.
;------------------------------------------------------------------------------
kind_hp:        ld   c, a
                and  LEK_KIND_MASK
                add  a, KT_HP & $FF            ; kind_tab is page aligned, KT_HP + 31 < 256
                ld   l, a
                ld   h, kind_tab >> 8
                ld   a, (hl)
                ld   hl, LVL_DEPTH
                add  a, (hl)
                dec  a
                bit  LEK_GOLD_BIT, c
                ret  z
                add  a, a
                add  a, 6
                ret

;------------------------------------------------------------------------------
; drop_row — far6 from mon_drop (bank 3), IX = the dead monster: the first
; drop_tab row of its kind ("k in N" on the gameplay RNG, rolled only for a kind
; with a row; arrows only in a Warrior run), then drop_put (this region).
; Moved from drop3.asm unchanged (3F-T5: bank 3 had 10 B free); same results.
; Clobbers: all but IX.   no row ~0.2k T
;------------------------------------------------------------------------------
drop_row:       ld   hl, drop_tab
                ld   b, DROP_ROWS
.r:             ld   a, (ix+E_KIND)
                cp   (hl)
                jr   z, .hit
                inc  hl
                inc  hl
                inc  hl
                inc  hl
                djnz .r
                ret
.hit:           inc  hl
                ld   d, (hl)                   ; D = type
                inc  hl
                ld   e, 1                      ; E = qty
                ld   a, d
                cp   IT_ARROW
                jr   nz, .q
                ld   a, (HERO_KIND)
                or   a
                ret  nz                        ; arrows: Warrior runs only
                ld   e, DROP_ARROWS
.q:             ld   c, (hl)                   ; C = N
                inc  hl                        ; HL -> the numerator (a tier's "k in N", §9.6)
                push hl
                push de
                call rng_mod                   ; A = 0..N-1
                pop  de
                pop  hl
                cp   (hl)                      ; roll < numerator <=> drop (1 in N rows: numerator 1,
                ret  nc                        ; the same RNG draw / outcome as before)
                ld   a, d
                ld   d, e                      ; D = qty
                ld   e, DROP_NEAR
                jp   drop_put

; drop_tab (§8.11 rulings 2 + §9.6 rewards; 3F-T3: 12 rows x 4 B: kind, type, N, k = "k in
; N"): the base drops (k = 1) and the tier rows (the base numerator + 1 per tier above 1:
; Cheese 1/4 -> 2/4 -> 3/4, Arrows 1/2 -> 2/2). First match wins. NOT here: the tier rows
; of a base with no drop (Screech Bat, Black Widow, Skeleton Guard / Knight, Poltergeist),
; which drop a random food (Carrot / Apple / Pear) 1 in 4 (open, not in the T5 contract).
DROP_STRIDE     EQU 4
drop_tab:       DB   K_RAT,         IT_F_CHEESE, 4, 1
                DB   K_GOBLIN,      IT_F_APPLE,  4, 1
                DB   K_ORC,         IT_F_MEAT,   3, 1
                DB   K_ARCHER,      IT_ARROW,    2, 1
                DB   K_NECRO,       IT_P_MANA,   3, 1
                DB   K_GIANT_RAT,   IT_F_CHEESE, 4, 2
                DB   K_RABBIT_RAT,  IT_F_CHEESE, 4, 3
                DB   K_SLINGER,     IT_F_APPLE,  4, 2
                DB   K_ORC_BERSERK, IT_F_MEAT,   3, 2
                DB   K_ORC_BOUNCER, IT_F_MEAT,   3, 3
                DB   K_SNIPER,      IT_ARROW,    2, 2
                DB   K_BONE_CALLER, IT_P_MANA,   3, 2
DROP_ROWS       EQU ($ - drop_tab) / DROP_STRIDE
                ASSERT DROP_ROWS == 12
