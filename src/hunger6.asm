;==============================================================================
; hunger6.asm — 3E-T9 hunger (game.md §7, §8.11 (2) "Food odds and hunger"),
; R6 region (r6.asm rules: entered only by far6, A / F lost on the way back,
; bank 6 at $C000 while it runs: bank-1 code only through far1).
; State: ITEM_RAM FOOD / FOOD_TMR / HSTAGE / HP_RG / HW_TMR / MP_HOLD
; (item_defs.asm) + ST_FLAGS slot 0 bit STS_HWEAK (combat_defs.asm).
;   hunger_turn  far6 from end_turn (bank 7), once per turn
;   hunger_add   far6, A = FOOD to add (the T12 EAT API)
;   item_food    far6 from panel_more (bank 2): the FOOD bar + stage word
; The penalties are read where they apply (no hero_recalc): to-hit
; (hit_roll: HUNGRY atk -1, WEAK atk -2 / eva -1), WEAK dmg -1 (deal_hit),
; WEAK no jump (h_jump), MP regen (xp_turn reads MP_HOLD), FED HP regen
; (here). Every WEAK test masks STS_WEAK | STS_HWEAK: never stacked.
;==============================================================================

;------------------------------------------------------------------------------
; hunger_turn — end_turn (bank 7), far6, every turn the hero is not DYING,
; after TURN_COUNTER++ / floor_pickup, right before xp_turn ("hunger ->
; regen", game.md §2.2):
;  1. a jump this turn (try_jump left JUMP_TURN = the counter + 1, and
;     end_turn has incremented it since: equal) -> FOOD - FOOD_JUMP;
;  2. FOOD_TMR + 1; at the period (FOOD_PERIOD, x2 while the Food or Scarab
;     amulet is worn: §8 "FOOD burn x1/2") -> 0, FOOD - 1. FOOD floors at 0:
;     hunger is never fatal;
;  3. hg_stage (HSTAGE, its line, STS_HWEAK);
;  4. FED: HP_RG + 1, at HP_REG_FED -> 0, HP + 1 (to MAXHP; the panel polls
;     HP). WEAK: HW_TMR + 1, at HW_REPEAT -> 0, "YOU ARE WEAK WITH HUNGER";
;  5. MP_HOLD for xp_turn: WEAK (status or hunger) -> != 0 (MP regen
;     halted); HUNGRY -> TURN_COUNTER bit 0 (MP_RG advances every 2nd turn:
;     the regen period doubles, §8.11); else 0.
; Clobbers: A, BC, DE, HL.   ~0.5k T (+ far6 ~0.25k; + ~3k on a line turn)
;------------------------------------------------------------------------------
hunger_turn:
                ld   hl, (TURN_COUNTER)
                ld   de, (JUMP_TURN)
                or   a
                sbc  hl, de
                ld   b, FOOD_JUMP
                call z, food_sub               ; 1. jumped this turn
                ld   a, (WORN + WS_CHARM * IR_STRIDE + IR_TYPE)
                sub  IT_C_PLENTY
                cp   IT_C_SCARAB - IT_C_PLENTY + 1
                ld   b, FOOD_PERIOD
                jr   nc, .per
                ld   b, 2 * FOOD_PERIOD        ; Food / Scarab amulet: burn x1/2
.per:           ld   hl, FOOD_TMR
                inc  (hl)
                ld   a, (hl)
                cp   b
                jr   c, .stg
                ld   (hl), 0
                ld   b, 1
                call food_sub                  ; 2. the burn
.stg:           call hg_stage                  ; 3.
                ld   a, (HSTAGE)
                or   a
                jr   nz, .nfed
                ld   hl, HP_RG                 ; 4. FED: HP + 1 per HP_REG_FED turns
                inc  (hl)
                ld   a, (hl)
                cp   HP_REG_FED
                jr   c, .hold
                ld   (hl), 0
                ld   hl, P_ENTITIES + E_HP
                ld   a, (hl)
                inc  hl
                cp   (hl)                      ; HP < MAXHP ?
                jr   nc, .hold
                dec  hl
                inc  (hl)
                jr   .hold
.nfed:          cp   HS_WEAK
                jr   nz, .hold
                ld   hl, HW_TMR                ; WEAK: the line again every HW_REPEAT turns
                inc  (hl)
                ld   a, (hl)
                cp   HW_REPEAT
                jr   c, .hold
                ld   (hl), 0
                call hg_weak_line
.hold:          ld   a, (ST_FLAGS)             ; 5. MP_HOLD (STS_HWEAK just synced)
                and  STS_WEAK | STS_HWEAK
                jr   nz, .mh
                ld   a, (HSTAGE)
                cp   HS_HUNGRY
                ld   a, 0
                jr   nz, .mh
                ld   a, (TURN_COUNTER)
                and  1
.mh:            ld   (MP_HOLD), a
                ret
                ASSERT HS_FED == 0 && IT_C_SCARAB == IT_C_PLENTY + 1 && E_MAXHP == E_HP + 1

;------------------------------------------------------------------------------
; food_sub — FOOD -= B, floored at 0; PD_FOOD when it moved.
; food_dirty — PD_FOOD only.  Clobbers: A, HL (food_dirty: HL).
;------------------------------------------------------------------------------
food_sub:
                ld   hl, FOOD
                ld   a, (hl)
                or   a
                ret  z                         ; already 0: never negative
                sub  b
                jr   nc, .s
                xor  a
.s:             ld   (hl), a
food_dirty:
                ld   hl, PANEL_DIRTY
                set  PD_FOOD_BIT, (hl)
                ret

;------------------------------------------------------------------------------
; hunger_add — the EAT API for T12 (far6; A passes in): FOOD += A, capped at
; FOOD_MAX (game.md §8.11 (2): eating clamps), PD_FOOD, then hg_stage (an
; upward crossing into FED prints "YOU FEEL WELL FED"). The refusal at FOOD
; 100 ("NO NEED") is the caller's. A <= FOOD_MAX.
; Clobbers: A, BC, DE, HL.   ~0.3k T (+ ~3k with the FED line)
;------------------------------------------------------------------------------
hunger_add:
                ld   hl, FOOD
                add  a, (hl)                   ; <= 200: no carry
                cp   FOOD_MAX + 1
                jr   c, .s
                ld   a, FOOD_MAX
.s:             ld   (hl), a
                call food_dirty
                ; fall through
;------------------------------------------------------------------------------
; hg_stage — HSTAGE := the stage of FOOD (FED >= 50, OK >= 25, HUNGRY >= 10,
; else WEAK); ST_FLAGS slot 0 STS_HWEAK := (stage == WEAK). On a change:
; PD_FOOD and at most ONE line (§8.11 (2)): downward into HUNGRY "YOU ARE
; HUNGRY", into WEAK "YOU ARE WEAK WITH HUNGER" (HW_TMR := -1), upward into
; FED "YOU FEEL WELL FED" (3E-T12: + HP_RG := 0, the regen count restarts);
; into OK and WEAK -> HUNGRY nothing.
; Clobbers: A, BC, DE, HL.   ~0.2k T (+ ~3k with a line)
;------------------------------------------------------------------------------
hg_stage:
                ld   a, (FOOD)
                ld   c, HS_WEAK
                cp   HS_WEAK_BELOW
                jr   c, .s
                dec  c
                cp   HS_HUNGRY_BELOW
                jr   c, .s
                dec  c
                cp   HS_OK_BELOW
                jr   c, .s
                dec  c
.s:             ld   hl, ST_FLAGS              ; hunger WEAK follows the stage
                res  STS_HWEAK_BIT, (hl)
                ld   a, c
                cp   HS_WEAK
                jr   nz, .w
                set  STS_HWEAK_BIT, (hl)
.w:             ld   hl, HSTAGE
                ld   b, (hl)                   ; B = the old stage
                cp   b
                ret  z
                ld   (hl), a
                call food_dirty                ; the word / attr change
                ld   a, c
                ld   e, S3_HG_FED
                or   a
                jr   nz, .nf                   ; into FED: always upward; 3E-T12: the FED
                ld   (HP_RG), a                ; regen count restarts (A = 0: +1 HP 12 turns on)
                jr   hg_line
.nf:
                cp   b
                ret  c                         ; upward into OK / HUNGRY: no line
                ld   e, S3_HG_HUNGRY
                cp   HS_HUNGRY
                jr   z, hg_line
                ret  c                         ; downward into OK: no line
                ld   a, $FF                    ; into WEAK (only ever from hunger_turn, whose
                ld   (HW_TMR), a               ; WEAK step follows: -1 + 1 = 0 this turn)
hg_weak_line:   ld   e, S3_HG_WEAK
hg_line:        xor  a                         ; IT_NONE: the stem alone
                ld   hl, it_line               ; bank 1 (itemname1.asm): MSG_BUF, log_push
                jp   far1
                ASSERT HS_FED == 0 && HS_OK == 1 && HS_HUNGRY == 2 && HS_WEAK == 3 && IT_NONE == 0

;------------------------------------------------------------------------------
; item_food — the panel FOOD item (far6 from panel_more, a tick's 1st frame
; only): the bar (fill FOOD / FOOD_MAX, cols 15..18), the stage word (bank-0
; hg_fed / hg_ok / hg_hungry / hg_weak, padded to HG_CHARS so a shorter word
; overwrites a longer one; cols 19..23) and the stage attr over both
; (hg_attr; game.md §7 table), marked for the present.
; Clobbers: A, BC, DE, HL.   ~8.5k T incl. far6 (tests/hunger.py T1; screen
; writes are contended)
;------------------------------------------------------------------------------
HG_CHARS        EQU 6
FOOD_BAR_ADDR   EQU ((SCREEN_BITMAP >> 8) | (STAT_ROW & $18)) << 8 | ((STAT_ROW & 7) << 5) | FOOD_BAR_COL
item_food:
                ld   hl, PANEL_DIRTY
                res  PD_FOOD_BIT, (hl)
                ld   a, (FOOD)
                ld   d, FOOD_MAX
                ld   hl, FOOD_BAR_ADDR
                call bars_draw
                ld   a, (HSTAGE)
                add  a, TX_HG_FED
                call tx_dec                    ; HL = TX_DEC (bank 5; hands bank 6 back)
                ld   b, HG_CHARS
.f:             ld   a, (hl)
                or   a
                jr   z, .pad
                inc  hl
                djnz .f
                jr   .pr                       ; a 6-char word: HL at its terminator
.pad:           ld   (hl), ' '
                inc  hl
                djnz .pad
                ld   (hl), 0
.pr:            ld   hl, TX_DEC
                ld   b, STAT_ROW
                ld   e, HUNGER_COL * 8
                call print6
                ld   a, (HSTAGE)
                ld   e, a
                ld   d, 0
                ld   hl, hg_attr
                add  hl, de
                ld   a, (hl)
                ld   bc, (STAT_ROW << 8) | FOOD_BAR_COL
                ld   de, ((GEAR_COL - FOOD_BAR_COL) << 8) | 1
                call stamp_rect                ; (A, B, D, E, HL)
                ld   bc, (STAT_ROW << 8) | FOOD_BAR_COL
                ld   de, ((GEAR_COL - FOOD_BAR_COL) << 8) | 1
                jp   pmark_rect
hg_attr:        DB   ATTR_P_FED, ATTR_P_OK, ATTR_P_HUNGRY, ATTR_P_WEAK   ; by HSTAGE
                ASSERT TX_HG_OK == TX_HG_FED + HS_OK && TX_HG_HUNGRY == TX_HG_FED + HS_HUNGRY && TX_HG_WEAK == TX_HG_FED + HS_WEAK
                ASSERT ((HUNGER_COL * 8) & 7) == 0 && HUNGER_COL * 8 + 6 * HG_CHARS <= GEAR_COL * 8   ; print6 x rule
                ASSERT FOOD_BAR_COL + BAR_CELLS == HUNGER_COL
