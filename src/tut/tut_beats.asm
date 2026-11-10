; =============================================================================
; tut_beats.asm - TUT0-T8: the D0 tutorial beat table (blob, bank 4).
; Spec: docs/design/tutorial_d0.md s3 (beats B0..B15), s6 (class pairs), s11
; (architect round); format: docs/design/tut0_split.md "Contracts shared by all
; tasks". Pure data, no code. Included only by the blob; the EQUs are TUT_-
; prefixed so they never clash with defs.asm. TL_* line ids come from T3's
; build/tut/tut_text.asm (forward references are fine in DEFB).
; =============================================================================

TUT_NONE        EQU $FF                 ; "no line / no rect / stay / no handler"
TUT_TB_STRIDE   EQU 16

; --- rooms (grid cells of the D0 block, spec s2) -----------------------------
TUT_RA          EQU 1
TUT_RB          EQU 4
TUT_RC          EQU 5

; --- trigger kinds (+1); params in +2 / +3 -----------------------------------
TUT_TK_STOREY       EQU 0               ; p2 = storey
TUT_TK_NEAR         EQU 1               ; p2 = cols (hero box within p2 cols of the mentor spot)
TUT_TK_XGE          EQU 2               ; p2 = storey, p3 = x (hero x >= p3)
TUT_TK_ARANK        EQU 3               ; ARANK <> 0 (book read)
TUT_TK_FOOD_UP      EQU 4               ; FOOD rose this turn
TUT_TK_ROOM         EQU 5               ; p2 = room
TUT_TK_POISON       EQU 6               ; hero POISONED
TUT_TK_POISON_CLR   EQU 7               ; poison cleared
TUT_TK_GOB_HURT     EQU 8               ; Goblin HP < max
TUT_TK_PASSIVE      EQU 9               ; never fires; ends when B13/B14 take over
TUT_TK_GOB_ASLEEP   EQU 10              ; p2 = cols: G0 shows when the awake Goblin is within p2; fires when it sleeps
TUT_TK_GOB_DEAD     EQU 11              ; Goblin dead
TUT_TK_EXIT         EQU 12              ; exit pending at end of turn

; --- fail / skip handlers (+14) ----------------------------------------------
TUT_FH_PITFALL        EQU 0             ; L69 + L10 (R2), beat stays
TUT_FH_BOOK_DISCARD   EQU 1             ; L15, advance
TUT_FH_TRAP_PASSED    EQU 2             ; L29 + L28 (B8); B9 then uses L32
TUT_FH_NOT_POISONED   EQU 3             ; L32 on pickup, advance (B9)
TUT_FH_IMPATIENT      EQU 4             ; L53 before G0 (B11)
TUT_FH_VICTORY_EXTRAS EQU 5             ; tut_extras: L48 after G3 (HP<max + Heal), L52 after G4 (unread scroll)
TUT_FH_NONE           EQU TUT_NONE

; --- mentor poses (+5 bits 0..5 = FRAME index of the 3/4 art, aldous34.asm;
;     T7: the blob picks the facing (toward the hero) and mirrors LEFT at runtime,
;     so POINT has one id; TUT_POSE_IDLE toggles IDLE1/IDLE2 every turn) --------
TUT_POSE_IDLE   EQU 0
TUT_POSE_TALK   EQU 2                   ; (a shown group sets TALK1/TALK2 anyway)
TUT_POSE_PT     EQU 4                   ; POINT (spec POINT_L / POINT_R: facing = toward the hero)
TUT_POSE_PT_DN  EQU 5
TUT_POSE_FADE   EQU 6
TUT_POSE_MASK   EQU $3F
TUT_PF_BLINK    EQU $80                 ; blink into the spot
TUT_PF_FADEIN   EQU $40                 ; fade in at the spot

; --- spot indexes (T4 order: A1 A2 A3 B1 B2 B3 C1 + grate spot) --------------
TUT_SP_A1       EQU 0
TUT_SP_A2       EQU 1
TUT_SP_A3       EQU 2
TUT_SP_B1       EQU 3
TUT_SP_B2       EQU 4
TUT_SP_B3       EQU 5
TUT_SP_C1       EQU 6
TUT_SP_GRATE    EQU 7

; --- record flags (+15) ------------------------------------------------------
TUT_BF_FIRST    EQU 1                   ; first beat of its room (overtaken-beat jump target)
TUT_BF_TAIL     EQU 2                   ; more groups after G2: pairs in tut_tail from index p3
TUT_BF_G2PRE    EQU 4                   ; G2 follows G0 on the next turn (before the trigger); +13 rect belongs to G2
TUT_BF_GRATE    EQU 8                   ; GOB_DEAD: open the grate after tail pair p2 has been shown
; TUT0-F2 (user B2, 2026-11-09): only important groups HOLD (wait for a keypress): the first
; explanation of each control, the Tome lines L54-L59, the grate lines. Repeats, nags, short
; confirmations and fail notes scroll on. One bit per group; tail pairs: tut_tail_hold.
TUT_BF_H0       EQU $10                 ; G0 holds
TUT_BF_H1       EQU $20                 ; G1 holds
TUT_BF_H2       EQU $40                 ; G2 holds (G2PRE or not)

; --- class-pair ids: a line id with bit 7 set = tut_cpairs[id & $7F] (W, M) ---
TUT_CP          EQU $80
TUT_CP_L14      EQU TUT_CP + 0
TUT_CP_L35      EQU TUT_CP + 1
TUT_CP_L36      EQU TUT_CP + 2
TUT_CP_L38      EQU TUT_CP + 3
TUT_CP_I01      EQU TUT_CP + 4              ; R2 icon tour: slot 1 (sword / staff)
TUT_CP_I02      EQU TUT_CP + 5              ; slot 2 (Power Strike / Spark)

; --- pointer rect ids (+12 / +13) -> tut_rects index -------------------------
TUT_PR_BAG      EQU 0
TUT_PR_FOOD     EQU 1
TUT_PR_POTION   EQU 2
TUT_PR_SCROLL   EQU 3
TUT_PR_STATUS   EQU 4                   ; (TUT0-F2: the key-icon rect is gone, L24 reworded)
TUT_PR_BARS     EQU 5
TUT_PR_ROW20    EQU 6
TUT_R20_W       EQU 26                  ; ROW20 = cols 0..25 (TUT0-F3; <= HP_COL, ASSERT tut_turn)

; one record = 16 B (ASSERTed). Group = 2 line ids (second may be $FF).
        MACRO TBEAT room, trig, p2, p3, spot, pose, g0a, g0b, g1a, g1b, g2a, g2b, r0, r1, fh, fl
        DEFB room, trig, p2, p3, spot, pose
        DEFB g0a, g0b, g1a, g1b, g2a, g2b
        DEFB r0, r1, fh, fl
        ENDM

; =============================================================================
; Beat table: 16 x TUT_TB_STRIDE = 256 B, B0..B15 in order.
; Group timing: G0 = when the beat becomes current; G1 = on trigger; G2 = the
; turn after G1 (or after G0 with TUT_BF_G2PRE).
; =============================================================================
tut_beats:
; B0 Arrive (A): A1, TALK; L01/L02; stand on storey 0
        TBEAT TUT_RA, TUT_TK_STOREY, 0, 0, TUT_SP_A1, TUT_POSE_TALK, \
              TL_L01, TL_L02, TUT_NONE, TUT_NONE, TUT_NONE, TUT_NONE, \
              TUT_NONE, TUT_NONE, TUT_FH_NONE, TUT_BF_FIRST
; B1 Walk + the goal (A): A1, IDLE; G0 L03/L04; trigger hero within 3 cols:
; G1 L05/L06, G2 L54/L55, tail pair 0 = L07 (p3 = tail index 0)
        TBEAT TUT_RA, TUT_TK_NEAR, 3, 0, TUT_SP_A1, TUT_POSE_IDLE, \
              TL_L03, TL_L04, TL_L05, TL_L06, TL_L54, TL_L55, \
              TUT_NONE, TUT_NONE, TUT_FH_NONE, TUT_BF_TAIL | TUT_BF_H0 | TUT_BF_H1 | TUT_BF_H2
; B2 Pit + jump (A, R2 s13.6): blink -> A2, POINT (at the pit); G0 L65/L66 (what a pit is, hold),
; G2 (next turn, pre-trigger) L08/L09 (hold); storey 0 and x >= 22: G1 L67/L68 (scroll); a fall:
; FH_PITFALL L69 + L10, the beat stays
        TBEAT TUT_RA, TUT_TK_XGE, 0, 22, TUT_SP_A2, TUT_PF_BLINK | TUT_POSE_PT, \
              TL_L65, TL_L66, TL_L67, TL_L68, TL_L08, TL_L09, \
              TUT_NONE, TUT_NONE, TUT_FH_PITFALL, TUT_BF_G2PRE | TUT_BF_H0 | TUT_BF_H2
; B3 Book + bag (A): A2, POINT_DN; G0 L11/L60 (pointer BAG; R2: the BAG steps are the icon
; target, tut_tgt); ARANK<>0: G1 L13 + class L14 W/M, tail pair 6 L63/L64 (scroll; p3 = 6)
        TBEAT TUT_RA, TUT_TK_ARANK, 0, TUT_TI_B3, TUT_SP_A2, TUT_POSE_PT_DN, \
              TL_L11, TL_L60, TL_L13, TUT_CP_L14, TUT_NONE, TUT_NONE, \
              TUT_PR_BAG, TUT_NONE, TUT_FH_BOOK_DISCARD, TUT_BF_TAIL | TUT_BF_H0 | TUT_BF_H1
; B4 Ladder (A): blink -> A3, IDLE; L16; standing on storey 1
        TBEAT TUT_RA, TUT_TK_STOREY, 1, 0, TUT_SP_A3, TUT_PF_BLINK | TUT_POSE_IDLE, \
              TL_L16, TUT_NONE, TUT_NONE, TUT_NONE, TUT_NONE, TUT_NONE, \
              TUT_NONE, TUT_NONE, TUT_FH_NONE, 0
; B5 Panel + food (A): A3, POINT_DN; G0 L17/L18 (pointer bars); G2 (next turn,
; pre-trigger) L19/L20 (pointer FOOD, in the +13 slot); FOOD rose: G1 L21/L22, then (R2) the
; tail pair 8 L70/L71 (WEAK: no leap; scroll; p3 = 8; for a G2PRE beat the tail follows G1)
        TBEAT TUT_RA, TUT_TK_FOOD_UP, 0, TUT_TI_B5, TUT_SP_A3, TUT_POSE_PT_DN, \
              TL_L17, TL_L18, TL_L21, TL_L22, TL_L19, TL_L20, \
              TUT_PR_BARS, TUT_PR_FOOD, TUT_FH_NONE, TUT_BF_TAIL | TUT_BF_G2PRE | TUT_BF_H0 | TUT_BF_H1 | TUT_BF_H2
; B6 Shaft (A): A3, POINT left; L23; room = B
        TBEAT TUT_RA, TUT_TK_ROOM, TUT_RB, 0, TUT_SP_A3, TUT_POSE_PT, \
              TL_L23, TUT_NONE, TUT_NONE, TUT_NONE, TUT_NONE, TUT_NONE, \
              TUT_NONE, TUT_NONE, TUT_FH_NONE, 0
; B7 Key (B): fade-in B1, POINT_DN; L24/L25 (TUT0-F2: no pointer, L24 reworded); storey 0
        TBEAT TUT_RB, TUT_TK_STOREY, 0, 0, TUT_SP_B1, TUT_PF_FADEIN | TUT_POSE_PT_DN, \
              TL_L24, TL_L25, TUT_NONE, TUT_NONE, TUT_NONE, TUT_NONE, \
              TUT_NONE, TUT_NONE, TUT_FH_NONE, TUT_BF_FIRST
; B8 Trap + status (B): B1, IDLE; G0 silent; POISONED: G1 L26/L27 (pointer
; status icon), G2 L28; not poisoned and x >= 17: FH_TRAP_PASSED (L29 + L28)
        TBEAT TUT_RB, TUT_TK_POISON, 0, 0, TUT_SP_B1, TUT_POSE_IDLE, \
              TUT_NONE, TUT_NONE, TL_L26, TL_L27, TL_L28, TUT_NONE, \
              TUT_NONE, TUT_PR_STATUS, TUT_FH_TRAP_PASSED, TUT_BF_H1 | TUT_BF_H2
; B9 Cure (B): blink -> B2, POINT_DN; G0 L30b (pointer BAG: T7, spec s6 - both kits hold a
; Heal, so the quick POTION slot would pick Heal first); poison cleared:
; G1 L31; not poisoned: FH_NOT_POISONED (L32)
        TBEAT TUT_RB, TUT_TK_POISON_CLR, 0, 0, TUT_SP_B2, TUT_PF_BLINK | TUT_POSE_PT_DN, \
              TL_L30b, TUT_NONE, TL_L31, TUT_NONE, TUT_NONE, TUT_NONE, \
              TUT_PR_BAG, TUT_NONE, TUT_FH_NOT_POISONED, 0
; B10 Door (B): blink -> B3, POINT right; L33; room = C
        TBEAT TUT_RB, TUT_TK_ROOM, TUT_RC, 0, TUT_SP_B3, TUT_PF_BLINK | TUT_POSE_PT, \
              TL_L33, TUT_NONE, TUT_NONE, TUT_NONE, TUT_NONE, TUT_NONE, \
              TUT_NONE, TUT_NONE, TUT_FH_NONE, TUT_BF_H0
; B11 Sleeping Goblin (C): fade-in C1, POINT right; G0 L34, G2 (next turn,
; pre-trigger) class L35/L36; Goblin HP < max; arriving out of order: FH_IMPATIENT
        TBEAT TUT_RC, TUT_TK_GOB_HURT, 0, 0, TUT_SP_C1, TUT_PF_FADEIN | TUT_POSE_PT, \
              TL_L34, TUT_NONE, TUT_NONE, TUT_NONE, TUT_CP_L35, TUT_CP_L36, \
              TUT_NONE, TUT_NONE, TUT_FH_IMPATIENT, TUT_BF_FIRST | TUT_BF_G2PRE | TUT_BF_H0 | TUT_BF_H2
; B12 Fight (C): C1, TALK; G0 L37 + class L38 (pointer row 20); passive
        TBEAT TUT_RC, TUT_TK_PASSIVE, 0, 0, TUT_SP_C1, TUT_POSE_TALK, \
              TL_L37, TUT_CP_L38, TUT_NONE, TUT_NONE, TUT_NONE, TUT_NONE, \
              TUT_PR_ROW20, TUT_NONE, TUT_FH_NONE, TUT_BF_H0
; B13 Scroll (C): C1, POINT_DN; G0 L39/L40 (pointer SCROLL) when the awake
; Goblin is within 6 cols; Goblin ASLEEP: G1 L41
        TBEAT TUT_RC, TUT_TK_GOB_ASLEEP, 6, 0, TUT_SP_C1, TUT_POSE_PT_DN, \
              TL_L39, TL_L40, TL_L41, TUT_NONE, TUT_NONE, TUT_NONE, \
              TUT_PR_SCROLL, TUT_NONE, TUT_FH_NONE, TUT_BF_H0
; B14 Victory (C): blink -> beside the grate, TALK; Goblin dead: G1 L42/L56,
; G2 L57/L58, tail pairs 0.. (p3 = TUT_TI_B14 -> index 2 after B1's 2-pair run) =
; G3 L59/L43, G4 L44/L45, G5 L46/L47; grate opens after tail pair p2 = 0 (G3);
; FH_VICTORY_EXTRAS adds L48 (after G3) / L52 (after G4)
        TBEAT TUT_RC, TUT_TK_GOB_DEAD, 0, TUT_TI_B14, TUT_SP_GRATE, TUT_PF_BLINK | TUT_POSE_TALK, \
              TUT_NONE, TUT_NONE, TL_L42, TL_L56, TL_L57, TL_L58, \
              TUT_NONE, TUT_NONE, TUT_FH_VICTORY_EXTRAS, TUT_BF_TAIL | TUT_BF_GRATE | TUT_BF_H1 | TUT_BF_H2
; B15 Exit (C): FADE out in place; the grate step (exit pending) -> sandbox reset
        TBEAT TUT_RC, TUT_TK_EXIT, 0, 0, TUT_NONE, TUT_POSE_FADE, \
              TUT_NONE, TUT_NONE, TUT_NONE, TUT_NONE, TUT_NONE, TUT_NONE, \
              TUT_NONE, TUT_NONE, TUT_FH_NONE, 0
tut_beats_end:
        ASSERT tut_beats_end - tut_beats = 16 * TUT_TB_STRIDE

; =============================================================================
; Tail groups (TUT_BF_TAIL): pairs of line ids shown one group per turn after
; G2, starting at pair index p3, ending at a
; ($FF,$FF) pair. 10 pairs = 20 B. R2: B3 / B5 pairs APPENDED (B14 keeps 2..5).
; =============================================================================
TUT_TI_B14      EQU 2
TUT_TI_B3       EQU 6
TUT_TI_B5       EQU 8
tut_tail:
        DEFB TL_L07, TUT_NONE           ; 0  B1 G3: WAIT BY ME TO HEAR IT AGAIN
        DEFB TUT_NONE, TUT_NONE         ; 1  end (B1)
        DEFB TL_L59, TL_L43             ; 2  B14 G3 (the grate opens after this one)
        DEFB TL_L44, TL_L45             ; 3  B14 G4
        DEFB TL_L46, TL_L47             ; 4  B14 G5
        DEFB TUT_NONE, TUT_NONE         ; 5  end (B14)
        DEFB TL_L63, TL_L64             ; 6  B3 tail (R2): scrolls from bar or bag, empty icons
        DEFB TUT_NONE, TUT_NONE         ; 7  end (B3)
        DEFB TL_L70, TL_L71             ; 8  B5 tail (R2): WEAK, no leap
        DEFB TUT_NONE, TUT_NONE         ; 9  end (B5)
tut_tail_end:
; TUT0-F2: bit i = tail pair i holds (B14 G3..G5: the Tome / sandbox / grate lines; B1's L07 not).
; tt_step tests bit (i mod 8): R2's pairs 6 and 8 land on bits 6 / 0, both clear (they scroll).
tut_tail_hold:
        DEFB %00011100

; FH_VICTORY_EXTRAS lines: [0] after G3 if HP < max and a Heal is held,
; [1] after G4 if the scroll is unread. 2 B.
tut_extras:
        DEFB TL_L48, TL_L52

; =============================================================================
; Class pairs (W, M), indexed by TUT_CP_* & $7F: L14, L35, L36, L38, I01, I02. 12 B.
; =============================================================================
tut_cpairs:
        DEFB TL_L14W, TL_L14M
        DEFB TL_L35W, TL_L35M
        DEFB TL_L36W, TL_L36M
        DEFB TL_L38W, TL_L38M
        DEFB TL_I01W, TL_I01M
        DEFB TL_I02W, TL_I02M

; =============================================================================
; R2 icon tour (tutorial_d0.md s13.3): tut_tour = the generic line of each icon slot
; (SEL_SLOT 0..9 = slots 1..10; $FF silent: Whirlwind / the gap are never selectable in D0;
; slots 4 / 5 are the Warrior's daggers / bow, unlearned = unreachable for the Mage). 10 B.
; =============================================================================
tut_tour:
        DEFB TUT_CP_I01, TUT_CP_I02, TUT_NONE, TL_I04W, TL_I05W
        DEFB TUT_NONE, TL_I07, TL_I08, TL_I09, TL_I10
tut_tour_end:
        ASSERT tut_tour_end - tut_tour == ICON_SLOTS

; tut_tgt - icon targets, checked first on a rest (stride TUT_TG_STRIDE 6): beat, SEL_SLOT,
; line pair (2nd $FF = one line), flags (bits 0-2 = the lowest TV_STAGE: ST_G2P = G0 shown,
; ST_WAIT = G2 shown; the stage must also be <= ST_WAIT; TUT_TGF_POIS = only while poisoned),
; hold-first mask (a bit of TV_ISAID + 1: the first rest in that beat holds; 0 = never).
; A target group is said on EVERY rest on its slot and never sets the slot's said bit. 36 B.
TUT_TG_STRIDE   EQU 6
TUT_TGF_POIS    EQU $40
TUT_TGF_POIS_BIT EQU 6
TUT_TGH_B3      EQU $08                 ; TV_ISAID bit 11
TUT_TGH_B9      EQU $10                 ; TV_ISAID bit 12
TUT_SL_POWER    EQU 1                   ; SEL_SLOT of the class power (slot 2)
TUT_SL_FOOD     EQU QS_SLOT0 + QS_FOOD  ; 6 (both heroes, UB5)
TUT_SL_SCROLL   EQU QS_SLOT0 + QS_SCROLL ; 8
TUT_SL_BAG      EQU ICON_SLOTS - 1      ; 9
tut_tgt:
        DEFB 3,  TUT_SL_BAG, TL_L12, TL_L61, ST_G2P, TUT_TGH_B3                 ; B3 BAG: the steps (hold first)
        DEFB 5,  TUT_SL_FOOD, TL_L73, TUT_NONE, ST_WAIT, 0                        ; B5 FOOD (after G2)
        DEFB 9,  TUT_SL_BAG, TL_L72, TUT_NONE, ST_G2P | TUT_TGF_POIS, TUT_TGH_B9  ; B9 BAG (poisoned; hold first)
        DEFB 11, TUT_SL_POWER, TL_L73, TUT_NONE, ST_G2P, 0                        ; B11 class power
        DEFB 12, TUT_SL_POWER, TL_L73, TUT_NONE, ST_G2P, 0                        ; B12 class power
        DEFB 13, TUT_SL_SCROLL, TL_L73, TUT_NONE, ST_G2P, 0                        ; B13 SCROLL (after G0)
tut_tgt_end:
TUT_TGT_N       EQU (tut_tgt_end - tut_tgt) / TUT_TG_STRIDE

; =============================================================================
; Pointer rects (row, col, w, h) in character cells; the FLASH bit goes on every
; cell of the rect. Stride 4, indexed by TUT_PR_*. 28 B. Panel (D5) / game.md
; s3.3, s3.5: icon i (1-based) = cols 3(i-1)..+2, rows 18-19; food 7, potion 8,
; scroll 9, bag 10 on both bars.
; =============================================================================
tut_rects:
        DEFB 18, 27, 3, 2               ; BAG    (slot 10)
        DEFB 18, 18, 3, 2               ; FOOD   (slot 7)
        DEFB 18, 21, 3, 2               ; POTION (slot 8)
        DEFB 18, 24, 3, 2               ; SCROLL (slot 9)
        DEFB 21, 30, 2, 1               ; hero status icons, row 21 cols 30-31
        DEFB 21,  0, 30, 1              ; HP / MP / FOOD bars + numbers + hunger word
        DEFB 20,  0, TUT_R20_W, 1       ; row 20, the info line cols 0-25 (TUT0-F3: the hold
                                        ; prompt owns 26-31, tutorial_d0.md s14.6; ASSERT tut_turn)
tut_rects_end:
