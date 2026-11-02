;==============================================================================
; ranged6.asm — 3F-T7: monster ranged attacks (game.md §9.2 RANGED-SPEC), R6.
; Two far6 entries:
;   ai_ranged   the DECISION (input tick, or the deferred monster phase): from
;               bank-2 ai_rhook (ranged2.asm), which ai_monster (bank 3) calls
;               right after its melee test (ret c) for a kind with an rk_tab row;
;   shot_tick   the deferred FX: act_pend (bank 7) while TP_SHOT, every tick of
;               the turn: the bolt's FX starts on the shooter's release tick R
;               (monster-phase tick + RG_REL + (slot & 1): the parity stagger
;               spreads the fx_start cost off the input tick), the hero's hit
;               flash on its impact tick I = R + gap + 1.
; The logic (hit roll, damage, status, death, the hero's HURT / DEATH reaction
; at I, the panel gate) is all resolved in ai_ranged (§6.5.1: logic first,
; visible output at impact); the FX descriptor is built there too and waits
; in RS_Q. Bank-3 combat (hit_roll / deal_hit) through the bank-3 entries
; rs_hit / rs_deal (turn3.asm, far3). Monster shots never bounce, reflect or
; drop anything; a blocked line or a reflecting hero is never fired at.
;==============================================================================

;------------------------------------------------------------------------------
; rd_tab — one row per shooter (RW_* fields, combat_defs.asm), row k = rk_tab
; value k (1-based). game.md §9.2 table: atk = kind_tab KT_ATK (hit_roll);
; PHYS = max(1, roll x res - DEF) (deal_hit); DARK = roll x res, no DEF.
; The reflect gate tests DARK only: every RWF_SPELL row it applies to (no RWF_NOREFL:
; Necro / Bone Caller) is DARK; the Archmage's typed rows (3F-T11b) never pass it.
;------------------------------------------------------------------------------
ROCK_ATTR       EQU $06                 ; the Slinger's rock (game.md §9.6: $06)
FEAR3_1IN3      EQU (3 << 4) | 3        ; DARK on-hit: FEAR 3 turns, 1 in 3 (~85/256, §9.2)
DARK_DHC        EQU DTY_DARK | DH_NODEF | (EFX_FEAR << DH_EFX_SHIFT)
rd_tab:         ;    r   N  flags                      die bon dhc        dhe         fx
                DB  10,  1, RWF_AWAY,                    6, 0, DTY_PHYS,  0,          FID_arrow_fly1    ; Archer
                DB  14,  1, 0,                           8, 0, DTY_PHYS,  0,          FID_arrow_fly1    ; Sniper
                DB   6,  2, RWF_AWAY | RWF_NOIMP,        3, 0, DTY_PHYS,  0,          FID_dagger_spin1  ; Slinger (rock)
                DB   8,  2, RWF_AWAY | RWF_SPELL,        6, 1, DARK_DHC,  FEAR3_1IN3, FID_nbolt_fly1    ; Necromancer
                DB   8,  2, RWF_AWAY | RWF_SPELL | RWF_PRE, 6, 1, DARK_DHC, FEAR3_1IN3, FID_nbolt_fly1   ; Bone Caller
                ; 3F-T11b the Archmage's 7 spells (game.md §9.9 A2; arch6.asm, no rk_tab entry): no
                ; bounces, N 1 (C cadence: a bolt every 2nd turn), hexes N 0 (an off-turn hex keeps
                ; C = 0). Riders through deal_hit's on-hit apply (85/256 = 1 in 3, 128/256 = 1 in 2).
                ; Hex rows: RW_DIE = the immunity bit, RW_BON = the hero's line, RW_DHE = the turns
                ; (Sleep: << 4, the ST_T1 HOLD nibble), RW_DHC = the EFX (am_hex tells them apart).
                DB  28,  1, RWF_SPELL | RWF_NOREFL, 8, 3, DARK_DHC, FEAR3_1IN3, FID_nbolt_fly1                    ; 0 Death Bolt
                DB  12,  1, RWF_SPELL | RWF_HOLD, 6, 1, DTY_COLD | DH_NODEF | (EFX_FROZEN << DH_EFX_SHIFT), $22, FID_nbolt_fly1  ; 1 Frost
                DB  12,  1, RWF_SPELL, 8, 1, DTY_SHOCK | DH_NODEF | (EFX_CONFUSED << DH_EFX_SHIFT), $24, FID_nbolt_fly1      ; 2 Lightning
                DB   5,  1, RWF_SPELL, 6, 1, DTY_DRAIN | DH_NODEF | DH_HEAL | (EFX_WEAK << DH_EFX_SHIFT), $28, FID_nbolt_fly1 ; 3 Drain
                DB  12,  1, RWF_SPELL | RWF_HOLD, 8, 2, DTY_FIRE | DH_NODEF | (EFX_STUNNED << DH_EFX_SHIFT), $31, FID_nbolt_fly1 ; 4 Firebolt
                DB  AM_HEX_R, 0, RWF_SPELL | RWF_HEX | RWF_HOLD, IMMF_SLEEP, TX_ST_ASLEEP, EFX_ASLEEP << DH_EFX_SHIFT, AM_SLEEP_T << 4, FID_nbolt_fly1 ; 5 Sleep
                DB  AM_HEX_R, 0, RWF_SPELL | RWF_HEX, IMMF_POISON, TX_ST_POISONED, EFX_POISON << DH_EFX_SHIFT, AM_PSN_T, FID_nbolt_fly1     ; 6 Venom
                ; BOSS-RANGED (golden only: ai_rhook's RK_GOLD1 gate): range 6, a shot every 3rd turn,
                ; keeps walking in between shots (RWF_WALK), the yellow dagger_spin (RWF_NOIMP: ROCK_ATTR)
                DB   6,  2, RWF_WALK | RWF_NOIMP,        3, 0, DTY_PHYS,  0,          FID_dagger_spin1  ; 13 Goblin King
                DB   6,  2, RWF_WALK | RWF_NOIMP,        2, 0, DTY_PHYS | (EFX_POISON << DH_EFX_SHIFT), SQ_PSN_T / 2, FID_dagger_spin1  ; 14 Spider Queen (spit, always + 12 POISON)
                ASSERT $ - rd_tab == RK_ROWS * RW_STRIDE
                ASSERT FID_arrow_fly2 == FID_arrow_fly1 + 1 && FID_arrow_hit == FID_arrow_fly1 + 2
                ASSERT FID_dagger_spin2 == FID_dagger_spin1 + 1
                ASSERT FID_nbolt_fly2 == FID_nbolt_fly1 + 1 && FID_nbolt_hit == FID_nbolt_fly1 + 2
                ASSERT RK_ARCHER == 1 && RK_SNIPER == 2 && RK_SLINGER == 3 && RK_NECRO == 4 && RK_BONE_CALLER == 5 && RK_ARCHMAGE == 6
                ASSERT RK_ARCHMAGE + AM_VENOM == RK_GKING - 1 && RK_SQUEEN == RK_GKING + 1 && RK_SQUEEN == RK_ROWS
                ASSERT SQ_PSN_T <= PSN_CAP && SQ_PSN_T % 2 == 0 && SQ_PSN_T / 2 <= STS_MAX_TURNS && DTY_PHYS == 0
                ASSERT AM_SLEEP_T << 4 < 256 && AM_SLEEP_T <= STS_MAX_TURNS && AM_PSN_T <= PSN_CAP

;------------------------------------------------------------------------------
; ai_ranged — the hook (game.md §9.2 "Per-turn order" step 4), first match:
;  1. counter: old = c, c = max(0, c - 1) (every acting turn that did not
;     melee). Not standing, or the hero not in line (mid-ladder / other storey)
;     -> L = 0 (walker rules: climbers .seek the ladder, others patrol);
;  2. gap >= r -> L = 0 (it closes in);
;  3. line not clear (a TF_SOLID cell on the flight row over the gap, any body
;     in gap cols x my rows: box_free with ACT_SLOT = me) or the hero reflects
;     DARK (a spell row without RWF_NOREFL) -> L = 0;
;     [caster pre-rule slot: T9 / T11 (RWF_PRE) hook in at .pre]
;  4. old == 0 -> SHOOT (rg_shoot), counter := N;
;  4b. RWF_WALK (BOSS-RANGED: the Goblin King / Spider Queen) -> L = 0 (it walks in);
;  5. gap 2 and RWF_AWAY -> one step away (try_step_face); blocked -> wait;
;  6. HOLD: wait facing the hero. 4-6: L = 1 (the turn is used).
; Counter rule: a shot needs the counter at 0 when the hook is entered (the
; decrement comes after the test): spawn 1 = no shot on the first phase, N = 1
; fires every 2nd turn, N = 2 every 3rd (the §9.2 cadence + delay statements).
; In : IX = the shooter (CUR_ROOM, active, acting), A = its rk_tab row (1..),
;      E = 0 iff standing (ai_monster's H), TMP4 = its storey (ai_monster),
;      ACT_SLOT = its slot, cache_player's PL_* current. TMP4 is kept.
; Out: L = 1 the turn is used, 0 not.  Clobbers: all but IX.
; Cost (far6 incl.): out of line ~0.6k T, out of range ~0.8k (rg_line tests the
; range before the scans), a full line test
; ~1.3k + 60 T a gap col, a shot ~2.5k + hit_roll / deal_hit (+ lines) ~1-3k.
;------------------------------------------------------------------------------
rg_no:          ld   l, 0                      ; the walker rules run
                ret
ai_ranged:
                call rg_row                    ; RG_ROW = row A (keeps DE)
                call rg_cnt                    ; 1. the counter (keeps E)
                call rg_line                   ; 2. in line and gap < r (CF = no: it closes in)
                jr   c, rg_no
.refl:          ld   a, (RG_ROW + RW_F)        ; reflect gate: a DARK (spell) row, not exempt,
                xor  RWF_SPELL                 ; vs the hero's DARK response X (Mirror Helm)
                and  RWF_SPELL | RWF_NOREFL
                jr   nz, .pre
                ld   a, (HERO_RES + RES_B1)    ; DARK = type 5: RES_B1 bits 2-3 (rsp_hl)
                and  3 << 2
                cp   RSP_X << 2
                jp   z, rg_no                  ; X: never fired at (as if blocked)
                ASSERT DTY_DARK == 5 && RES_B1 == 1
.pre:           ; T9 caster pre-rule slot (RWF_PRE: the Bone Caller's summon, spawn6.asm;
                ; T11's Archmage takes its own branch), before the shot: CF = summoned
                ld   a, (RG_ROW + RW_F)
                and  RWF_PRE
                call nz, sp_bcall
                jr   c, rg_used
                ; 4. SHOOT if the counter was 0
                ld   a, (RG_OLD)
                or   a
                jr   z, rg_shoot
                ; 4b. BOSS-RANGED: a walking shooter (RWF_WALK, bit 7) between shots -> the walker rules
                ; 5. gap 2 and a step-away kind: one step away (one RW_F load for both: +3 B)
                ld   a, (RG_ROW + RW_F)
                rla                            ; CF = RWF_WALK; RWF_AWAY -> bit 2
                jr   c, rg_no
                and  RWF_AWAY << 1
                jr   z, .hold
                ld   a, (RG_GAP)
                cp   3
                jr   nc, .hold
                ASSERT RWF_WALK == $80 && RWF_AWAY < $80
                ld   a, (RG_DIR)
                neg
                ld   d, a
                ld   e, 0
                call try_step_face             ; (faces the step)
                jr   c, rg_used
                ; 6. HOLD (and a blocked step-away): wait facing the hero
.hold:          ld   a, (RG_DIR)
                call face_a
rg_used:        ld   l, 1
                ret

;------------------------------------------------------------------------------
; rg_pose — IX = the monster, B = E_MSG: the line at its attack's IMPACT (do_impact),
; E_TGT 0, E_HIT = C (LOG-DMG: rg_shoot's $80 | L, 0 on a miss / the summon: no flash
; at the IMPACT either way), the attack sequence (the cut / cast pose). Shared by
; rg_shoot and the 3F-T9 summon (spawn6.asm sp_summon).  Clobbers: A, DE, HL (C kept).
;------------------------------------------------------------------------------
rg_pose:        ld   (ix+E_MSG), b
                xor  a
                ld   (ix+E_TGT), a
                ld   (ix+E_HIT), c
                call kind_seq_ptr              ; (bank 2)
                ld   de, KS_ATTACK
                add  hl, de
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                jp   start_seq

;------------------------------------------------------------------------------
; rg_shoot — step 4: face the hero, counter := N, resolve now (RNG order §9.2:
; PHYS d20 then damage; spells damage then deal_hit's on-hit roll), the hero's
; reaction at I = R + gap + 1 (the FX starts at R with 0 delay and flies gap
; cells at 8 px a tick: fx_start's timeline), the panel gate (a hit: §6.5.1),
; E_MSG (the melee hit / miss line at the attack's IMPACT, behind the gate),
; the attack sequence (the cut / cast pose), the RS_Q entry. L = 1, DE = the
; byte after the RS_Q entry written (3F-T11b am_cast re-inks it, the sink too).
; 3F-T11b: an RWF_HEX row deals nothing (am_hex), AM_DMG = the damage roll.
;------------------------------------------------------------------------------
rg_shoot:
                ld   a, (RG_DIR)
                call face_a
                ld   a, (RG_ROW + RW_N)        ; counter := N
                xor  1
                ld   b, a
                ld   a, (ix+E_RCD)
                and  ~RCD_MASK & $FF
                or   b
                ld   (ix+E_RCD), a
                xor  a
                ld   (RG_F), a
                ld   a, (RG_ROW + RW_F)
                rra                            ; CF = RWF_SPELL: auto-hit
                ASSERT RWF_SPELL == 1
                jr   c, .hit
                xor  a                         ; target = the hero
                ld   hl, rs_hit
                call far3                      ; L = 1 hit / 0 miss
                ld   a, l
                or   a
                ld   b, MSG_M_MISS
                ld   c, a                      ; LOG-DMG: C = the E_HIT (0 on a miss)
                jr   z, .msg
.hit:           ld   a, (RG_ROW + RW_F)
                and  RWF_NOIMP
                jr   nz, .ni
                ld   hl, RG_F
                set  RGF_IMP_BIT, (hl)
.ni:            ld   a, (RG_ROW + RW_F)        ; 3F-T11b: a hex (the Archmage's Sleep / Venom):
                and  RWF_HEX                   ; no damage roll, the rider by the immunity mask
                jr   z, .dm                    ; (am_hex, arch6.asm); L = 0: no flash, no
                call am_hex                    ; reaction (the caller clears E_MSG: no hit line)
                ld   l, 0
                jr   .dl
.dm:            ld   a, (RG_ROW + RW_DIE)      ; 1dN + bonus
                ld   c, a
                call rng_mod
                inc  a
                ld   hl, RG_ROW + RW_BON
                add  a, (hl)
                bit  LEK_GOLD_BIT, (ix+E_GOLD) ; 3F-T8: a golden shooter's dmg + 1 (§9.7 R1)
                jr   z, .ng
                inc  a
.ng:            ld   d, a
                ld   (AM_DMG), a               ; 3F-T11b: the Mirror Helm return's roll (am_cast)
                ld   a, (RG_ROW + RW_DHE)
                ld   e, a
                ld   a, (RG_ROW + RW_DHC)
                ld   hl, rs_deal
                call far3                      ; L = HP lost (I: 0 + the UNAFFECTED line)
.dl:            ld   c, l                      ; LOG-DMG: C = L (rg_ri / rg_pose keep C)
                call rg_ri                     ; A = R, B = I
                inc  l
                dec  l
                jr   z, .gate
                ld   hl, RG_F
                set  RGF_FLASH_BIT, (hl)
                ld   hl, P_ENTITIES + E_REACTAT ; HURT / DEATH under the impact (deal_hit
                ld   (hl), b                   ; set one at the attack's IMPACT: pending)
.gate:          add  a, CNB_MAX                ; §6.5.1: COMBAT_NOT_BEFORE = max(it, min(I,
                cp   b                         ; R + CNB_MAX)); a miss sets none
                jr   c, .g1
                ld   a, b
.g1:            ld   hl, COMBAT_NOT_BEFORE
                cp   (hl)
                jr   c, .g2
                ld   (hl), a
.g2:            ld   b, MSG_M_HIT
                set  7, c                      ; LOG-DMG: E_HIT = $80 | L: the line's -D, bit 7 = no flash at
.msg:           call rg_pose                   ; the IMPACT (do_impact): it waits for the bolt (shot_tick);
                                               ; rg_pose stores C (a miss: C = 0)
                ; --- the RS_Q entry (TP_SHOT: act_pend runs shot_tick every tick) ---
rg_q:           ld   hl, TURN_PEND             ; (3F-T11b am_cast: the Mirror Helm return track)
                bit  TP_SHOT_BIT, (hl)
                set  TP_SHOT_BIT, (hl)
                ld   hl, RS_P
                jr   nz, .q
                ld   (hl), RS_Q & $FF          ; a fresh queue
.q:             ld   a, (hl)
                ld   e, a
                ld   d, RS_Q >> 8
                cp   RS_SINK & $FF
                jr   nc, .full                 ; a 5th shooter: the sink, no FX (tests assert 0)
                add  a, RS_STRIDE
                ld   (hl), a
                jr   .w
.full:          ld   hl, FX_DROP
                inc  (hl)
.w:             call rg_ri
                ld   (de), a                   ; RS_R
                inc  de
                ld   hl, RG_F
                bit  RGF_FLASH_BIT, (hl)
                jr   nz, .fl
                ld   b, 0                      ; no flash
.fl:            ld   a, b
                ld   (de), a                   ; RS_FL = I or 0
                inc  de
                ld   c, (hl)                   ; C = RG_F
                ld   a, (RG_ROW + RW_FX)       ; FXD_FIDA / FIDB / IMPA / IMPB
                ld   (de), a
                inc  de
                inc  a
                ld   (de), a
                inc  de
                inc  a
                ld   b, PF_IMPT
                bit  RGF_IMP_BIT, c
                jr   nz, .im
                ld   a, FX_NONE                ; a miss / the rock: no impact frame
                ld   b, 0
.im:            ld   (de), a
                inc  de
                ld   (de), a
                inc  de
                ld   a, (RG_ROW + RW_F)        ; FXD_ATTR: the frames' own (fx_meta, 0), the
                and  RWF_NOIMP                 ; rock ROCK_ATTR (dagger_spin's own is $47)
                jr   z, .at
                ld   a, ROCK_ATTR
.at:            ld   (de), a
                inc  de
                ld   a, (RG_DIR)               ; FXD_COL = the cell next to the shooter:
                rla                            ; right x + w = RG_FIRST, left x - 1 =
                ld   a, (RG_FIRST)             ; RG_FIRST + gap - 1
                ld   hl, RG_GAP
                jr   nc, .an
                add  a, (hl)
                dec  a
.an:            ld   (de), a
                inc  de
                ld   a, (ix+E_KIND)            ; FXD_ROW = the flight row (rg_line's: top + 2, the
                cp   K_SPIDER                  ; 2-high Spider Queen's top; HL / BC are live here:
                ld   a, (ix+E_Y)               ; the kind test, not KT_BH)
                jr   z, .fr
                add  a, PF_ROW_DY
.fr:            ld   (de), a
                ; the only 2-high shooter is the Spider (rg_line's (h / 2) & 2 == rg_q's kind test)
                ASSERT PF_ROW_DY == 2 && BH_K_SPIDER == 2 && BH_K_GOBLIN >= 4 && BH_K_ARCHER >= 4 && BH_K_NECRO >= 4 && BH_K_ARCHMAGE >= 4
                ASSERT BH_K_GOBLIN <= 7 && BH_K_ARCHER <= 7 && BH_K_NECRO <= 7 && BH_K_ARCHMAGE <= 7
                inc  de
                ld   a, (RG_DIR)               ; FXD_FLAGS: FXDF_LEFT, 8 px a tick
                rlca
                and  FXDF_LEFT
                ld   (de), a
                inc  de
                xor  a
                ld   (de), a                   ; FXD_DELAY 0 (started at R)
                inc  de
                ld   a, b
                ld   (de), a                   ; FXD_IMPT
                inc  de
                ld   a, 1
                ld   (de), a                   ; FXD_NSEG
                inc  de
                ld   a, (hl)                   ; SEGS[0] = gap (the moves after the anchor)
                ld   b, FXD_SEGMAX
.sg:            ld   (de), a
                inc  de
                xor  a
                djnz .sg                       ; SEGS[1..4] = 0
                jp   rg_used
                ASSERT FXD_FIDA == 0 && FXD_FIDB == 1 && FXD_IMPA == 2 && FXD_IMPB == 3 && FXD_ATTR == 4
                ASSERT FXD_COL == 5 && FXD_ROW == 6 && FXD_FLAGS == 7 && FXD_DELAY == 8 && FXD_IMPT == 9
                ASSERT FXD_NSEG == 10 && FXD_SEGS == 11 && FXD_SEGS + FXD_SEGMAX == FXD_LEN && FXDF_LEFT == 1
                ASSERT RS_R == 0 && RS_FL == 1 && RS_D == 2

; rg_ri — A = R = TURN_TICK + RG_REL + (ACT_SLOT & 1), B = I = R + RG_GAP + 1.
; Clobbers: A, B (HL kept)
rg_ri:          push hl
                ld   a, (ACT_SLOT)
                and  1
                add  a, RG_REL
                ld   hl, TURN_TICK
                add  a, (hl)
                ld   b, a
                ld   hl, RG_GAP
                add  a, (hl)
                inc  a
                ld   h, b
                ld   b, a
                ld   a, h
                pop  hl
                ret


;------------------------------------------------------------------------------
; rg_rp — A = rd_tab row 1.. -> HL = the row.  Clobbers: A, BC.
; rg_row — the same, copied to RG_ROW (RW_STRIDE B).  Keeps DE.  Clobbers: A, BC, HL.
;------------------------------------------------------------------------------
rg_row:         call rg_rp
                push de
                ld   de, RG_ROW
                ld   bc, RW_STRIDE
                ldir
                pop  de
                ret
rg_rp:          ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ld   bc, rd_tab - RW_STRIDE
                add  hl, bc
                ret
                ASSERT RW_STRIDE == 8

;------------------------------------------------------------------------------
; rg_cnt — step 1's counter (E_RCD bits 0-1, stored XOR 1): RG_OLD = A = c, c =
; max(0, c - 1); Z = c was 0.  Keeps C, DE, HL.  Clobbers: A, B.
;------------------------------------------------------------------------------
rg_cnt:         ld   a, (ix+E_RCD)
                xor  1
                ld   b, a
                and  RCD_MASK
                ld   (RG_OLD), a
                jr   z, .c0
                dec  b                         ; > 0: only the low bits change
.c0:            ld   a, b
                xor  1
                ld   (ix+E_RCD), a
                ld   a, (RG_OLD)
                or   a
                ret

;------------------------------------------------------------------------------
; rg_line — RANGED-SPEC "in line" (§9.2 Geometry): IX standing (E = 0) on the
; hero's storey TMP4, the hero standing (not mid-ladder), no overlap; RG_DIR /
; RG_FIRST / RG_GAP set; gap < RG_ROW's RW_R (the row must be loaded); the flight row (top + 2; a 2-high body: its top) over the gap free of TF_SOLID cells
; (rg_scan) and no live body in gap cols x my rows (box_free, ACT_SLOT = me).
; Out: CF = not in line; NC: A = gap.  Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
rg_line:        ld   a, e
                ld   hl, PL_LADDER             ; the hero mid-ladder: not in line
                or   (hl)
                jr   nz, .no
                ld   a, (PL_STOREY)
                ld   hl, TMP4
                cp   (hl)
                jr   nz, .no                   ; another storey
                ; gap, side, first gap col (standing bodies of a storey always
                ; overlap vertically: no row test, §9.2 "Geometry")
                KFIELD KT_BW
                add  a, (ix+E_X)
                ld   c, a                      ; C = x + w
                ld   a, (PL_X)
                sub  c
                ld   b, 1
                jr   nc, .gd                   ; hero right: gap = px - (x + w), first = x + w
                ld   a, (PL_X)
                ld   hl, PL_W
                add  a, (hl)
                ld   c, a                      ; hero left: first = px + pw
                ld   a, (ix+E_X)
                sub  c                         ; gap = x - (px + pw)
                ret  c                         ; (overlap: never for two standing bodies)
                ld   b, $FF
.gd:            ld   hl, RG_DIR
                ld   (hl), b
                inc  l
                ld   (hl), c                   ; RG_FIRST
                inc  l
                ld   (hl), a                   ; RG_GAP
                ASSERT RG_FIRST == RG_DIR + 1 && RG_GAP == RG_FIRST + 1 && (RG_DIR >> 8) == (RG_GAP >> 8)
                ld   hl, RG_ROW + RW_R         ; gap >= r: out of range, before the scans (cheap reject)
                cp   (hl)
                jr   nc, .no
                or   a                         ; gap 0: in line (NC; 0 only guards the loops)
                ret  z
                ld   d, a                      ; D = gap cols
                KFIELD KT_BH                   ; (keeps BC, DE)
                ld   e, a
                rrca                           ; BOSS-RANGED: flight row = top + ((h / 2) & 2):
                and  PF_ROW_DY                 ; top + 2, a 2-high body (the Spider Queen) its top
                add  a, (ix+E_Y)               ; row (top + 2 is its floor; §9.2: fr lies in the
                ld   b, a                      ; hero's rows). rg_q matches it (K_SPIDER)
                call rg_scan
                ret  c                         ; a solid cell (a mid-room block)
                ld   b, (ix+E_Y)               ; gap cols x my rows
                call box_free                  ; (ACT_SLOT = me)
                ret  c                         ; a body in the way: no friendly fire
                ld   a, (RG_GAP)
                ret
.no:            scf
                ret

;------------------------------------------------------------------------------
; rg_scan — CF = 1 if ROOM_MAP row B, cols C .. C+D-1 (D >= 1, inside the row)
; holds a TF_SOLID cell (tile_flags; air decor / torches / back-wall patches are
; non-solid, game.md §1.2: in practice a mid-room block). R6 ai_ranged's wall
; scan; T9's Vampire cut test uses the same scan on other rows.
; Keeps BC, DE.  Clobbers: A, HL.  ~0.15k T + 50 T a col
;------------------------------------------------------------------------------
rg_scan:
                push bc
                push de
                call cell_addr                 ; HL = (B, C) (keeps BC, DE)
                ld   b, d
                ld   d, tile_flags >> 8        ; (tile_flags never crosses a page)
.l:             ld   a, (hl)
                add  a, tile_flags & $FF
                ld   e, a
                ld   a, (de)
                rrca                           ; CF = TF_SOLID
                jr   c, .x
                inc  l                         ; (cols stay inside the row)
                djnz .l
.x:             pop  de
                pop  bc
                ret
                ASSERT TF_SOLID == 1

;------------------------------------------------------------------------------
; shot_tick — act_pend (bank 7, far6: +~0.3k T on a TP_SHOT tick) on every tick
; while TP_SHOT (R6 rg_shoot queued RS_Q .. RS_P): per entry, at TURN_TICK >= R
; its FX descriptor goes to fx_start (a free track, else FXQ: a 4th waits, the
; logic is unaffected; else FX_DROP); then at TURN_TICK >= I (RS_FL != 0: HP
; was lost) the hero's ATTR_HIT flash. No entry live: TP_SHOT clears
; (turn_done waits for the FX to go idle as well).
; Clobbers: all but IY.  ~0.1k T + ~60 T an entry a tick, a start + ~0.9k
;------------------------------------------------------------------------------
shot_tick:
                ld   hl, RS_Q
                ld   c, 0                      ; C = entries still live
.l:             ld   a, (RS_P)
                cp   l
                jr   z, .end
                push bc
                push hl
                ld   a, (TURN_TICK)
                ld   b, (hl)                   ; RS_R
                inc  b
                jr   z, .fly                   ; RS_STARTED
                dec  b
                cp   b
                jr   c, .live                  ; before the release
                ld   (hl), RS_STARTED
                inc  hl
                inc  hl
                ld   a, (hl)                   ; the release sound (FXD_FIDA): a DARK bolt SPARK,
                cp   FID_nbolt_fly1            ; an arrow / rock THROW (sfx_req keeps every register)
                ld   a, SFX_THROW
                jr   nz, .snd
                ld   a, SFX_SPARK
.snd:           call sfx_req
                call fx_start                  ; HL = the descriptor (copied; all but IY)
                jr   .live
.fly:           inc  hl
                ld   b, (hl)                   ; RS_FL: the flash's impact tick, 0 = none
                inc  b
                dec  b
                jr   z, .done
                cp   b
                jr   c, .live
                ld   (hl), 0
                ld   hl, P_ENTITIES + E_FLT    ; the bolt's hit: the $42 flash under it
                ld   (hl), FLASH_TICKS
                inc  l
                ld   (hl), ATTR_HIT
.done:          pop  hl
                pop  bc
                jr   .nx
.live:          pop  hl
                pop  bc
                inc  c
.nx:            ld   de, RS_STRIDE
                add  hl, de
                jr   .l
.end:           ld   a, c
                or   a
                ret  nz
                ld   hl, TURN_PEND
                res  TP_SHOT_BIT, (hl)
                ret
                ASSERT E_FLA == E_FLT + 1 && ((P_ENTITIES + E_FLT) & $FF) != $FF
                ASSERT RS_R == 0 && RS_FL == 1 && RS_D == 2 && (RS_Q >> 8) == (RS_SINK >> 8)
