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
IMP_EMBER_ATTR  EQU $42                 ; NEW-MON3 §4.2 / §10 Q6: the Fire Imp's ember (Firebolt red)
WR_BOLT_ATTR    EQU $45                 ; §4.4: the Frost Wraith's bolt = the Frost Shard pair's cyan
WR_BOLT_R       EQU 8                   ; §4.4 (the T10a re-gate's r 6 / N 3 knobs undone by the Warrior's innate COLD R)
WR_BOLT_N       EQU 2                   ; §4.4; <= RCD_MASK
PIT_AXE_ATTR    EQU $07                 ; §8.3: the Orc's thrown hand axe (white); Goblin dagger / Skeleton bone THROW_ATTR $47
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
                ; BOSS-RANGED (rows >= RK_GOLD1, golden only: ai_rhook's gate): range 6, a shot every 3rd turn,
                ; keeps walking in between shots (RWF_WALK), the yellow dagger_spin (RWF_NOIMP: ROCK_ATTR); the Queen's spit the magenta spark_fly (NOIMP, own attr)
                ; WIDOW-SPIT (user 2026-11-05): the Black Widow (any body, no gate) = the Queen's spit with N 3
                ; (every 4th turn), + 6 POISON; 1d2 - DEF (not golden: no + 1)
                DB   6, BW_SPIT_N, RWF_WALK | RWF_NOIMP, 2, 0, DTY_PHYS | (EFX_POISON << DH_EFX_SHIFT), BW_PSN_T / 2, FID_spark_fly1  ; 13 Black Widow
                ; NEW-MON3 T8 (new_monsters.md §4.2): the Fire Imp's ember: range 6, a shot every 3rd turn (N 2), flies on between
                ; shots (RWF_WALK), auto-hit (RWF_SPELL: the Necromancer branch, roll x response, no DEF) that never meets the
                ; DARK reflect gate (RWF_NOREFL), 1d4+1 FIRE, impact = spark_fizz (class-shared; the ember's $42 ink is F-1 code)
                ; T10a F-1: a flyer's flight row is its bottom row (rg_line); the ember flies $42 with the class-shared
                ; spark_fizz impact (rd_x)
                DB   6,  2, RWF_WALK | RWF_SPELL | RWF_NOREFL, 4, 1, DTY_FIRE | DH_NODEF, 0, FID_spark_fly1  ; 14 Fire Imp
                ; NEW-MON3 T10a (new_monsters.md §4.4, user 2026-11-14): the Frost Wraith's FROST BOLT, the Imp's F-1 path as data:
                ; auto-hit COLD 1d4+1 x the hero's response (the Frost Charm's COLD R halves it), damage only (no rider: the
                ; touch stays the freezer), drifts on between shots (RWF_WALK); frost_fly -> frost_crack, $45 (rd_x: RXF_ONE).
                ; r 8, N 2 (every 3rd ACTING turn = every 6th game turn under KF_SLOW): the §4.4 values, kept since the T10a
                ; follow-up gave the Warrior an innate COLD R (gear6 hero_recalc; tools/balance_nm3.json WRAITH_R / WRAITH_COOL)
                DB   WR_BOLT_R, WR_BOLT_N, RWF_WALK | RWF_SPELL | RWF_NOREFL, 4, 1, DTY_COLD | DH_NODEF, 0, FID_frost_fly   ; 15 Frost Wraith
                DB   6,  2, RWF_WALK | RWF_NOIMP,        3, 0, DTY_PHYS,  0,          FID_dagger_spin1  ; 16 Goblin King
                DB   6,  2, RWF_WALK | RWF_NOIMP,        2, 0, DTY_PHYS | (EFX_POISON << DH_EFX_SHIFT), SQ_PSN_T / 2, FID_spark_fly1  ; 17 Spider Queen (spit = the Mage's spark, always + 12 POISON)
                ; NEW-MON3 T10a P-1 (§8.3): the pit throws (pit6 only; F1 d20, PHYS - DEF min 1, no impact frame). The Goblin's
                ; N 0 is never read twice (one dagger: RCD_SPENT). Inks in rd_x
                DB   4,  3, RWF_NOIMP,                   2, 0, DTY_PHYS | (EFX_POISON << DH_EFX_SHIFT), BW_PSN_T / 2, FID_spark_fly1  ; 18 pit Spider (+ 6 POISON)
                DB   6,  0, RWF_NOIMP,                   3, 0, DTY_PHYS,  0,          FID_dagger_spin1  ; 19 pit Goblin (one dagger)
                DB   5,  3, RWF_NOIMP,                   6, 0, DTY_PHYS,  0,          FID_dagger_spin1  ; 20 pit Orc (a hand axe)
                DB   5,  3, RWF_NOIMP,                   4, 0, DTY_PHYS,  0,          FID_dagger_spin1  ; 21 pit Skeleton (a bone)
                ASSERT $ - rd_tab == RK_ROWS * RW_STRIDE
                ASSERT FID_arrow_fly2 == FID_arrow_fly1 + 1 && FID_arrow_hit == FID_arrow_fly1 + 2
                ASSERT FID_dagger_spin2 == FID_dagger_spin1 + 1
                ASSERT FID_nbolt_fly2 == FID_nbolt_fly1 + 1 && FID_nbolt_hit == FID_nbolt_fly1 + 2
                ASSERT RK_ARCHER == 1 && RK_SNIPER == 2 && RK_SLINGER == 3 && RK_NECRO == 4 && RK_BONE_CALLER == 5 && RK_ARCHMAGE == 6
                ASSERT RK_ARCHMAGE + AM_VENOM == RK_WIDOW - 1 && RK_IMP == RK_WIDOW + 1 && RK_WRAITH == RK_IMP + 1 && RK_GKING == RK_WRAITH + 1 && RK_SQUEEN == RK_GKING + 1 && RK_WRAITH < RK_GOLD1
                ASSERT RK_PSPIDER == RK_SQUEEN + 1 && RK_PGOBLIN == RK_PSPIDER + 1 && RK_PORC == RK_PGOBLIN + 1 && RK_PSKEL == RK_PORC + 1 && RK_PSKEL == RK_ROWS
                ASSERT FID_frost_crack == FID_frost_fly + 1 && WR_BOLT_N <= RCD_MASK
                ASSERT SQ_PSN_T <= PSN_CAP && SQ_PSN_T % 2 == 0 && SQ_PSN_T / 2 <= STS_MAX_TURNS && DTY_PHYS == 0
                ASSERT BW_PSN_T <= PSN_CAP && BW_PSN_T % 2 == 0 && BW_PSN_T / 2 <= STS_MAX_TURNS && RK_WIDOW < RK_GOLD1
                ASSERT AM_SLEEP_T << 4 < 256 && AM_SLEEP_T <= STS_MAX_TURNS && AM_PSN_T <= PSN_CAP

;------------------------------------------------------------------------------
; rd_x — NEW-MON3 T10a: per rd_tab row (1-based, RG_RIX) 2 B: FXD_ATTR (0 = the frames' own fx_meta ink)
; | RXF_ONE (one flight frame: FIDB = FIDA), and the impact fid (read only without RWF_NOIMP). Was rg_q's
; "dagger_spin -> ROCK_ATTR, else 0" test and "impact = fid + 2": the Imp's ember ($42, spark_fizz), the
; Wraith's frost (frost_fly -> frost_crack) and the pit inks need their own. One page (rg_q: ld h).
;------------------------------------------------------------------------------
rd_x:           DB   0, FID_arrow_hit,           0, FID_arrow_hit            ; Archer, Sniper
                DB   ROCK_ATTR, 0,               0, FID_nbolt_hit            ; Slinger (rock), Necromancer
                DB   0, FID_nbolt_hit                                        ; Bone Caller
                DUP  AM_VENOM + 1                                            ; the Archmage's 7 (am_cast re-inks)
                DB   0, FID_nbolt_hit
                EDUP
                DB   0, 0,                       IMP_EMBER_ATTR, FID_spark_fizz1   ; Black Widow (NOIMP), Fire Imp
                DB   RXF_ONE | WR_BOLT_ATTR, FID_frost_crack                 ; Frost Wraith
                DB   ROCK_ATTR, 0,               0, 0                        ; Goblin King (rock ink), Spider Queen ($43 own)
                DB   0, 0,                       THROW_ATTR, 0               ; pit Spider ($43 own), pit Goblin (the hero's dagger ink)
                DB   PIT_AXE_ATTR, 0,            THROW_ATTR, 0               ; pit Orc (a hand axe), pit Skeleton (a bone)
                ASSERT $ - rd_x == 2 * RK_ROWS && (rd_x >> 8) == (($ - 1) >> 8)
                ASSERT FID_arrow_hit == FID_arrow_fly1 + 2 && FID_nbolt_hit == FID_nbolt_fly1 + 2

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
                ld   a, (RG_RIX)               ; T10a: HL = the row's rd_x pair {attr | RXF_ONE, impact}
                add  a, a
                add  a, (rd_x - 2) & $FF
                ld   l, a
                ld   h, rd_x >> 8
                ld   a, (RG_ROW + RW_FX)       ; FXD_FIDA / FIDB / IMPA / IMPB
                ld   (de), a
                inc  de
                bit  7, (hl)                   ; RXF_ONE: one flight frame (frost_fly)
                jr   nz, .one
                inc  a
.one:           ld   (de), a
                inc  de
                inc  l
                ld   a, (hl)                   ; the impact fid (rd_x)
                dec  l
                ld   b, PF_IMPT
                bit  RGF_IMP_BIT, c
                jr   nz, .im
                ld   a, FX_NONE                ; a miss / the rock: no impact frame
                ld   b, 0
.im:            ld   (de), a
                inc  de
                ld   (de), a
                inc  de
                ld   a, (hl)                   ; FXD_ATTR (rd_x): ROCK_ATTR for the Slinger / Goblin King
                and  ~RXF_ONE & $FF            ; rock, the Imp's $42 ember, the pit inks; 0 = the frames'
                ld   (de), a                   ; own (the spark $43, arrows $07, bolts $43)
                inc  de
                ASSERT RXF_ONE == $80
                ld   a, (RG_DIR)               ; FXD_COL = the cell next to the shooter:
                rla                            ; right x + w = RG_FIRST, left x - 1 =
                ld   a, (RG_FIRST)             ; RG_FIRST + gap - 1
                ld   hl, RG_GAP
                jr   nc, .an
                add  a, (hl)
                dec  a
.an:            ld   (de), a
                inc  de
                ld   a, (RG_FR)                ; FXD_ROW = rg_line's flight row (T10a: was a fid test here;
                ld   (de), a                   ; the flyer's bottom row needs rg_line's own value)
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
; rg_row — the same, copied to RG_ROW (RW_STRIDE B), RG_RIX = A.  Keeps DE.  Clobbers: A, BC, HL.
;------------------------------------------------------------------------------
rg_row:         ld   (RG_RIX), a               ; T10a: rg_q's rd_x row
                call rg_rp
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
; RG_FIRST / RG_GAP set; gap < RG_ROW's RW_R (the row must be loaded); the flight row (top + 2; a 2-high body: its top;
; T10a F-1: a flyer (E = 0 from ai_flyer) its bottom row y + h - 1) = RG_FR, at or below the hero's top row PL_Y; over the gap free of TF_SOLID cells
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
                ld   d, a                      ; D = gap cols
                KFIELD KT_BH                   ; (keeps BC, DE)
                ld   e, a                      ; E = h
                KFIELD KT_FLAGS
                rrca                           ; CF = KF_FLYER
                ld   a, e
                jr   c, .fly
                rrca                           ; BOSS-RANGED: flight row = top + ((h / 2) & 2):
                and  PF_ROW_DY                 ; top + 2, a 2-high body (the Spider Queen) its top
                jr   .fr                       ; row (top + 2 is its floor; §9.2: fr lies in the hero's rows)
.fly:           dec  a                         ; NEW-MON3 T10a F-1: a flyer's fr = y + h - 1 (its bottom row)
.fr:            add  a, (ix+E_Y)
                ld   b, a                      ; B = fr
                ld   (RG_FR), a                ; rg_q's FXD_ROW (was its own fid test)
                ld   hl, PL_Y                  ; F-1: in line only if fr >= the standing hero's top row 9s + 2
                cp   (hl)                      ; (fr <= 9s + 7 always: a walker's fr is inside his rows, a flyer's
                ret  c                         ; bottom row never leaves its band 9s .. 9s + 8 - h)
                ld   a, d
                or   a                         ; gap 0: in line (NC; 0 only guards the loops)
                ret  z
                ASSERT KF_FLYER == 1
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

;------------------------------------------------------------------------------
; perch6 — NEW-MON3 T10a G-1 (new_monsters.md §4.1, as amended 2026-11-14): far6 from bank-3 afl_perch, a
; perched Gargoyle's own turn (IX; RCD_AWAKE clear; the status step and the slow gate passed). The hero
; standing (not mid-ladder) on its storey (storey_ref vs PL_STOREY) at a box gap <= PERCH_GAP (an overlap
; counts as 0) -> RCD_AWAKE, it faces him, "THE GARGOYLE WAKES UP." (the existing MSG_M_WAKE line, 0 new
; text), the WAKING pose (its KS_CLIMB one-shot: a flyer never climbs; T10b's art) and the turn is spent;
; else it waits (the PERCHED rest pose: anim's KS_IDLE). Never otherwise. Damage (deal_hit) and a missed
; bump (do_attack) set RCD_AWAKE silently; room re-entry re-perches (zeroed / restored slot clears bit 2).
; Clobbers: all but IX.  A waiting turn ~0.5k T (far6 incl.); a wake + its line ~2.5k.
;------------------------------------------------------------------------------
perch6:         ld   a, (PL_LADDER)
                or   a
                ret  nz                        ; the hero mid-ladder: stays perched
                call storey_ref                ; (bank 2; A, HL)
                ld   hl, PL_STOREY
                cp   (hl)
                ret  nz                        ; the other storey: never
                KFIELD KT_BW
                add  a, (ix+E_X)
                ld   b, a                      ; x + w
                ld   a, (PL_X)
                ld   c, 1                      ; C = the facing (+1 right / $FF left)
                sub  b                         ; hero right: gap = px - (x + w)
                jr   nc, .g
                ld   a, (PL_X)
                ld   hl, PL_W
                add  a, (hl)
                ld   b, a
                ld   c, $FF
                ld   a, (ix+E_X)
                sub  b                         ; hero left: gap = x - (px + pw); CF = an overlap
                jr   c, .wk
.g:             cp   PERCH_GAP + 1
                ret  nc                        ; too far: stays perched
.wk:            set  RCD_AWAKE_BIT, (ix+E_RCD)
                ld   a, c
                call face_a                    ; (bank 2)
                ld   b, MSG_M_WAKE
                ld   c, (ix+E_KIND)
                call impact_line               ; (low RAM: pages the text, restores R6) "THE GARGOYLE WAKES UP."
                call kind_seq_ptr              ; (bank 2) the waking one-shot = KS_CLIMB
                ld   de, KS_CLIMB
                add  hl, de
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                jp   start_seq                 ; (bank 2)

;------------------------------------------------------------------------------
; pit6 — NEW-MON3 T10a P-1 (new_monsters.md §8.2 / §8.3, user 2026-11-13: across pits only): far6 from
; ai_monster's refused .fstep (bank 3) for a KF_PIT walker (IX, ACT_SLOT = its slot, TMP6 = the refused step's
; dx, toward the hero: .same's). First match:
;  1. a golden body (a lair boss) never; my storey != 0 (pits exist only there); the refused col
;     x + TMP6 outside the pit's fall range (pit_range = try_step's own walker test): another
;     refusal (a body, a wall) -> nothing;
;  2. the kind's pit row (pit_tab); the Goblin's one dagger spent (RCD_SPENT) -> nothing;
;  3. track limit: >= FX_TRACKS shots queued this phase (RS_Q, TP_SHOT) -> wait, the counter untouched
;     (pit throws never queue a 4th track);
;  4. the counter (rg_cnt) and rg_line (the hero standing on storey 0, gap < r, the flight row and the gap
;     box clear: the pit holes are in the floor row, never the flight row) -> no: wait;
;  5. counter 0 at entry -> rg_shoot (faces the hero, F1 + PHYS - DEF, counter := N; the Goblin's SPENT set).
; §8.6 fallback (step 1, no bytes and no routine to reuse: the hero's thrown daggers do not land as loot yet,
; game.md §6.3): the Goblin's dagger is consumed like every monster shot. Out-of-line / reloading: the
; refused step is the turn (a wait). No result (ai_monster's caller reads none).
; Clobbers: all but IX.  Not a pit refusal ~0.5k T (far6 incl.); a throw + rg_shoot ~3-5k.
;------------------------------------------------------------------------------
pit6:           ld   a, (ix+E_GOLD)
                or   a
                ret  nz                        ; a lair boss never throws
                call storey_ref                ; (bank 2; A, HL)
                ld   (TMP4), a                 ; rg_line's storey
                or   a
                ret  nz                        ; pits: storey 0 only
                ld   a, (TMP6)                 ; .fstep's refused dx (try_step.vert keeps TMP6)
                add  a, (ix+E_X)
                ld   c, a                      ; C = x + dx (the refused body-left col)
                call pit_range                 ; (low RAM; keeps BC, DE) CF = inside the fall range
                ret  nc                        ; another refusal
                ld   a, (ix+E_KIND)
                ld   hl, pit_tab
                ld   b, PIT_N
.k:             cp   (hl)
                inc  hl
                jr   z, .row
                inc  hl
                djnz .k
                ret                            ; (every KF_PIT kind has a row: pit_tab ASSERT)
.row:           cp   K_GOBLIN
                jr   nz, .ng
                bit  RCD_SPENT_BIT, (ix+E_RCD)
                ret  nz                        ; its one dagger is gone
.ng:            ld   a, (TURN_PEND)            ; 3. the shots already queued this monster phase
                bit  TP_SHOT_BIT, a
                jr   z, .tf
                ld   a, (RS_P)
                cp   (RS_Q + FX_TRACKS * RS_STRIDE) & $FF
                ret  nc                        ; all 3 tracks claimed: wait, the counter unchanged
.tf:            ld   a, (hl)                   ; the pit row
                call rg_row                    ; (keeps DE)
                call rg_cnt                    ; 4. the counter
                ld   e, 0                      ; standing (a walker's .fstep)
                call rg_line
                ret  c                         ; out of line / range / a body or a block in the way
                ld   a, (RG_OLD)
                or   a
                ret  nz                        ; reloading: wait
                ld   a, (ix+E_KIND)
                cp   K_GOBLIN
                jr   nz, .sh
                set  RCD_SPENT_BIT, (ix+E_RCD) ; the one dagger
.sh:            jp   rg_shoot                  ; 5. (faces the hero)
                ASSERT (RS_Q & $FF) + FX_TRACKS * RS_STRIDE < $100 && FX_TRACKS == 3
pit_tab:        DB   K_SPIDER, RK_PSPIDER,       K_GOBLIN, RK_PGOBLIN
                DB   K_ORC, RK_PORC,             K_ORC_BERSERK, RK_PORC,     K_ORC_BOUNCER, RK_PORC
                DB   K_SKELETON, RK_PSKEL,       K_SKEL_GUARD, RK_PSKEL,     K_SKEL_KNIGHT, RK_PSKEL
PIT_N           EQU ($ - pit_tab) / 2
                ; every KF_PIT kind has a row (and no other walker: pit6 is entered only for KF_PIT)
                ; rg_line's walker flight row top + ((h / 2) & 2) of a standing pit kind (top = 8 - h on storey 0) lies in
                ; the standing hero's rows 2 .. 7 (review T10a: the Orc / Skeleton h 6 -> top + 2, the Spider h 2 -> its top)
                DUP PIT_N, n
PTH = {b kind_tab + KT_BH + {b pit_tab + 2 * n}}
                ASSERT 8 - PTH + ((PTH >> 1) & 2) >= 2 && 8 - PTH + ((PTH >> 1) & 2) <= 7 && PTH <= STOREY_AIR
                EDUP
                DUP K_COUNT, n
                ASSERT !(({b kind_tab + KT_FLAGS + n} & (KF_PIT | KF_FLYER)) == KF_PIT) || n == K_SPIDER || n == K_GOBLIN || n == K_ORC || n == K_ORC_BERSERK || n == K_ORC_BOUNCER || n == K_SKELETON || n == K_SKEL_GUARD || n == K_SKEL_KNIGHT
                EDUP
