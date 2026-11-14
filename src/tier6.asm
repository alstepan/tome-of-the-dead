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
;   i = rnd(8) (LP8); the rolled tier row (iff the kind has tiers, FRESH ordinary
;   room) is tried first, then LP_KINDS[i] at base, then the other kinds in list
;   order at base; a kind is accepted iff LP_SIG + w + LP_RES <= cap, then
;   LP_SIG += w. The lightest kind always passes (LP_DISCARD stays 0).
; Clobbers: all but IX, IY.   ~0.9k T for a 2-unit room (the far6 ~0.45k included); a full room: gen_fit may make up to 8 gen_tryi calls (LP8), about +4 x ~100 T per refused unit
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
                call lp_minw                   ; A = C = minW (keeps DE)
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
                add  a, lp_wt & $FF
                ld   l, a
                ld   h, lp_wt >> 8
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
                and  7
                ld   c, a                      ; C = i = rnd(8): the slot (NEW-MON3 T3; duplicates = weights)
                ld   a, (LPV_BOSS)
                or   a
                jr   nz, .nt
                ld   a, c
                add  a, LP_KINDS & $FF
                ld   l, a
                ld   h, LP_KINDS >> 8
                push bc
                ld   a, (LP_LVL)
                ld   c, a                      ; C = the level-entry LVL (§9.6)
                ld   a, (hl)                   ; the rolled base row
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
                cp   8                         ; (a duplicate of the rolled kind is refused again: same state)
                jr   c, .j
                ld   hl, LP_DISCARD
                inc  (hl)
                scf
                ret
; lp_minw — A = C = the lightest §9.3 weight in LP_KINDS (lp_gen, the T12 trickle).
; Keeps DE.  Clobbers: B, HL.
lp_minw:        ld   hl, LP_KINDS
                ld   bc, (8 << 8) | $FF
.mw:            ld   a, (hl)
                inc  l                         ; (LP_KINDS: one page, ASSERTed)
                add  a, lp_wt & $FF
                push hl
                ld   l, a
                ld   h, lp_wt >> 8
                ld   a, (hl)
                pop  hl
                cp   c
                jr   nc, .mn
                ld   c, a
.mn:            djnz .mw
                ld   a, c
                ret
; gen_tryi — A = LP_KINDS index; gen_tryk — A = kind row: accept iff LP_SIG + w + LP_RES <= cap.
; NC: A = the row, LP_SIG += w; CF: rejected. Clobbers: A, DE, HL.
gen_tryi:          add  a, LP_KINDS & $FF
                ld   l, a
                ld   h, LP_KINDS >> 8
                ld   a, (hl)
gen_tryk:          ld   e, a
                add  a, lp_wt & $FF
                ld   l, a
                ld   h, lp_wt >> 8
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

; gen_step — one xorshift 7,9,8 step of the spawn stream (GEN_RNG) -> HL: bank 2 (io.asm; MEM-RECLAIM w3, was a 21-B copy here).

;------------------------------------------------------------------------------
; tier_row — A = a base row, C = the hero LVL to use (lp_gen: LP_LVL, the level-entry
; LVL; the T12 trickle: the current LVL) -> A = its tier row to try first, 0 = none
; (the kind has no tiers: NO stream step; or the roll gave the base). The odds (out of 256):
;   T2 = clamp(T2_BASE[d] + 16 Δ, 0, 160)   T3 = d >= 4 ? clamp(T3_BASE[d] + 8 Δ, 0, 80) : 0
;   r = the low byte of one stream step: r < T3 -> tier 3 (tier 2 if the base
;   has none), r < T3 + T2 -> tier 2, else base. NEW-MON3 T9: the caps are reached
;   on D7 / D8 (bases 144 / 72-80) and applied (+10 B; levelgen.py tier_odds); the
;   floors only at D1 for LVL < 1 (kept: exact for every LP_LVL <= 120). Clobbers: A, BC, DE, HL.   ~0.5k T tiered, ~0.15k else
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
                ld   b, a
                ld   a, c                      ; LVL
                sub  b
                ld   c, b                      ; C = depth
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
.t2:            cp   T2_CAP + 1                ; NEW-MON3 T9: D7 / D8 base 144 + 32 reaches the cap
                jr   c, .c2
                ld   a, T2_CAP
.c2:            ld   d, a                      ; D = T2
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
.t3:            cp   T3_CAP + 1                ; NEW-MON3 T9: D7 / D8 base 72 / 80 + 16 reaches the cap
                jr   c, .c3
                ld   a, T3_CAP
.c3:            ld   e, a
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
    IF (($ & $FF) + 9) > $100
                ALIGN 256                      ; each 9-byte table inside one page (H loaded per table); MEM-RECLAIM w3: pad only when it would straddle (was ALIGN 16: 25 B)
    ENDIF
T2_BASE:        DB   0, 24, 48, 64, 72, 80, 88, 144, 144   ; NEW-MON3 T9 (tools/balance_nm3.json, user 2026-11-13): D7 / D8 96 -> 144
    IF (($ & $FF) + 9) > $100
                ALIGN 256
    ENDIF
T3_BASE:        DB   0, 0, 0, 0, 16, 24, 32, 72, 80        ; NEW-MON3 T9: D7 / D8 40 / 48 -> 72 / 80
                ASSERT (T2_BASE >> 8) == ((T2_BASE + 8) >> 8) && (T3_BASE >> 8) == ((T3_BASE + 8) >> 8)
                ASSERT LEVELS == 8
                ASSERT 144 + 2 * TIER_SHIFT2 * TIER_DELTA_MAX < 256 && 80 + 2 * TIER_SHIFT3 * TIER_DELTA_MAX < 256   ; no 8-bit wrap before the caps
                ASSERT (LP_KINDS >> 8) == ((LP_KINDS + 7) >> 8)

; §9.3 weights by kind row: lp_wt (bank 2, kind_tab + KT_REACH; main.asm), one copy for bank 3 and R6

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
                or   a
                jr   nz, .dp
                ld   c, 3                      ; 3F-T6 type 0: a random Carrot / Apple / Pear (§9.6)
                call rng_mod                   ; (keeps C, DE)
                add  a, IT_F_CARROT
.dp:            ld   d, e                      ; D = qty
                ld   e, DROP_NEAR
                jp   drop_put

; drop_tab (§8.11 rulings 2 + §9.6 rewards; 3F-T3: 12 rows x 4 B: kind, type, N, k = "k in
; N"): the base drops (k = 1) and the tier rows (the base numerator + 1 per tier above 1:
; Cheese 1/4 -> 2/4 -> 3/4, Arrows 1/2 -> 2/2). First match wins. NOT here: the tier rows
; of a base with no drop (Screech Bat, Black Widow, Skeleton Guard / Knight, Poltergeist),
; are the last 5 rows (3F-T6): type 0 = a random food (Carrot / Apple / Pear), 1 in 4.
; 3F-T6: 17 rows.
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
                DB   K_SCREECH,     0, 4, 1    ; 3F-T6: the tiers of a base with no drop: a random food (type 0) 1 in 4
                DB   K_BLACK_WIDOW, 0, 4, 1
                DB   K_SKEL_GUARD,  0, 4, 1
                DB   K_SKEL_KNIGHT, 0, 4, 1
                DB   K_POLTERGEIST, 0, 4, 1
drop_imp:       DB   K_ALIAS,       IT_P_MANA,   4, 1    ; NEW-MON3 T8: the Fire Imp (row 31 variant A): Mana 1 in 4. The Frost Wraith drops
                                                         ; nothing: nm3_var turns this row's kind byte to 0 (no monster has kind 0)
DROP_ROWS       EQU ($ - drop_tab) / DROP_STRIDE
                ASSERT DROP_ROWS == 18 && IT_F_APPLE == IT_F_CARROT + 1 && IT_F_PEAR == IT_F_CARROT + 2

;------------------------------------------------------------------------------
; lp_bk6 — lp_bank's per-body part (ROOM-MEM2 review: moved from bank 3 with lp_append, its
; only caller; -83 B there): far6 from bank-3 lp_bank, IX = an active slot of LPV_ROOM that
; leaves play (not a kept-aside candidate). §9.4.2: dead (EF_DYING) or summon-made
; (RCD_SUMMONED) -> freed (E_FLAGS 0), never written; else the entry {kind | EF_RESPAWN |
; LEK_GOLD | LEK_BRED (RCD_ONCE), exact hp} is appended to the room's record (VISITED; a full
; record (LR_MAX, cannot happen under the §9.3 cap): LP_DISCARD + 1, freed, not parked), its
; LP_POS byte = its LAST cell (E_X | storey_ref << 5 | facing left << 6: the live slot, every
; step writes E_X) and the slot is PARKED (ROOM-MEM: EF_ACTIVE clear, E_ROOM | LPK_PARK).
; Nothing comes back (the caller's BC is lost to far6 anyway). Keeps IX.
; Clobbers: A, F, BC, DE, HL.   ~0.4k T + far6 (~0.45k) a body
;------------------------------------------------------------------------------
lp_bk6:         ld   a, (ix+E_FLAGS)
                bit  EF_DYING_BIT, a
                jr   nz, .free                 ; dead: never returns
                bit  RCD_SUMMONED_BIT, (ix+E_RCD)
                jr   nz, .free                 ; 3F-T9: summon-made: discarded (§9.4.2)
                and  EF_RESPAWN
                or   (ix+E_KIND)
                or   (ix+E_GOLD)               ; 3F-T5: LEK_GOLD or 0
                bit  RCD_ONCE_BIT, (ix+E_RCD)
                jr   z, .nb
                set  LEK_BRED_BIT, a           ; 3F-T9: the once bit (a Rabbit Rat bred)
.nb:            ld   b, a                      ; B = the kind byte
                ld   a, (LPV_ROOM)
                ld   e, a
                add  a, a
                add  a, a
                add  a, a
                add  a, e
                ld   e, a
                ld   d, 0
                ld   hl, LP_REC
                add  hl, de                    ; the record (LP_REC + 9 room; bank-3 lp_rec / hla: not here)
                ld   a, (hl)
                and  LR_CNT_MASK
                cp   LR_MAX
                jr   nc, .full
                ld   c, a                      ; C = the entry index
                inc  a
                or   LR_VISITED
                ld   (hl), a
                ld   a, c
                add  a, a
                inc  a                         ; LR_ENT + 2 i
                ld   e, a
                add  hl, de
                ld   (hl), b
                inc  hl
                ld   a, (ix+E_HP)
                ld   (hl), a                   ; exact hp
                call storey_ref                ; (bank 2) A = 0 / 1; clobbers HL only
                rrca
                rrca
                rrca                           ; -> bit 5 (LPP_S_BIT)
                or   (ix+E_X)                  ; bits 0-4 (a body-left col < 32)
                bit  3, (ix+E_FLAGS)
                jr   z, .r
                or   1 << LPP_LEFT_BIT
.r:             ld   b, a
                ld   a, (LPV_ROOM)
                add  a, a
                add  a, a
                add  a, c
                add  a, LP_POS & $FF           ; LP_POS: one page (level_defs.asm ASSERT)
                ld   l, a
                ld   h, LP_POS >> 8
                ld   (hl), b
                res  0, (ix+E_FLAGS)           ; ROOM-MEM: parked, not freed: EF_ACTIVE clear, the
                set  7, (ix+E_ROOM)            ; rest (HOSTILE: != 0) kept, E_ROOM | LPK_PARK
                ret
.full:          ld   hl, LP_DISCARD
                inc  (hl)
.free:          ld   (ix+E_FLAGS), 0
                ret
                ASSERT LPK_PARK == 1 << 7 && EF_ACTIVE == 1 && EF_HOSTILE != 0 && EF_LEFT == 1 << 3
                ASSERT LPP_S_BIT == 5 && LPP_LEFT_BIT == 6 && LPP_X == 31 && STOREY_COUNT == 2
                ASSERT LR_ENT == 1 && LE_KIND == 0 && LE_HP == 1 && LE_STRIDE == 2 && LR_STRIDE == 9

;------------------------------------------------------------------------------
; lp_t06 — ROOM-MEM2 try 0's decode (far6 from bank-3 lp_enter .t0, VISITED records only):
; LPV_RDP = the unit's entry -> B = its LP_POS byte (0 = none), E = x, C = storey, D = the
; byte rotated right 3 (facing left -> EF_LEFT bit 3; != 0 iff B != 0: lp_spawn's marker).
; Clobbers: A, F, HL.   ~0.2k T + far6
;------------------------------------------------------------------------------
lp_t06:         ld   a, (LPV_RDP)
                call lp_posr6
                ld   a, (hl)
                ld   b, a
                and  LPP_X
                ld   e, a
                ld   a, b
                rrca
                rrca
                rrca
                ld   d, a                      ; bit 6 -> bit 3 (EF_LEFT), bit 5 -> bit 2
                rrca
                rrca
                and  1
                ld   c, a                      ; storey
                ret

;------------------------------------------------------------------------------
; lp_cp6 — ROOM-MEM2 (far6 from bank-3 lp_enter, a VISITED unit not placed): its LP_POS
; byte follows its entry down (LPV_RDP -> LPV_WRP, the record's compaction).
; Clobbers: A, F, B, HL.   ~0.3k T + far6
;------------------------------------------------------------------------------
lp_cp6:         ld   a, (LPV_RDP)
                call lp_posr6
                ld   b, (hl)
                ld   a, (LPV_WRP)
                call lp_posr6
                ld   (hl), b
                ret

; lp_posr6 — A = the low byte of an entry pointer of the record being entered (LPV_RDP /
; LPV_WRP = LP_RECP + 1 + 2 i), LPV_ROOM -> HL = &LP_POS[4 room + i]. Clobbers: A, F.
lp_posr6:       ld   hl, LP_RECP
                sub  (hl)                      ; 1 + 2 i (8-bit: a record is 9 B)
                rrca                           ; i | $80
                and  LR_MAX - 1
                ld   l, a
                ld   a, (LPV_ROOM)
                add  a, a
                add  a, a
                add  a, l
                add  a, LP_POS & $FF
                ld   l, a
                ld   h, LP_POS >> 8
                ret
                ASSERT LR_MAX == 4

