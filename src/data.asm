;==============================================================================
; data.asm — PROTO static tables: kinds, frame table (with the §10
; stand-in rule), per-kind state->frame role tables, animation sequences, the
; 4 hand-authored rooms (§8), spawns and in-game strings. (Stand-in tile
; glyphs / tile tables: lowram.asm; select strings: bank3.asm.)
;
; STAND-IN RULE (prototype §10, task brief): every frame is declared with FRM
; (src/frames.asm). FRM includes a frame only if its label EXISTS in the sources
; AND its anchor is legal (§5.3: ax mod 4 == 0, 0 <= ax <= 8, 0 <= ax_L <= 16).
; Otherwise FID_<name> = -1 and the per-kind ROLE table below falls back to the
; listed stand-in frame. When the artist appends a frame (or re-pads an anchor)
; it drops in with NO code change; the role tables are the only thing to edit
; if a name differs.
;==============================================================================

; ROLE dst, candidate_fid, fallback_fid  — the state->frame table entry.
    MACRO ROLE dst, cand, fb
      IF (cand) >= 0
dst EQU cand
      ELSE
dst EQU fb
      ENDIF
    ENDM


;==============================================================================
; FRAME TABLE — MEM-FT: the list (src/frames.asm) is assembled HERE in source
; order (it defines FID_* / KFID_* / POOL_* for everything after), but ORGed at
; FRT: the FRT row image of every fid (12 x FRT_NONE + the 4-B frame_tab entry
; FT_COLS, FT_H, FT_OFFR, FT_OFFL), runtime RAM above the image — not on tape,
; only in the .sna. The build packs its frame_tab bytes (main.asm ovl_raw_ft ->
; bank-2 ftz_zx0); boot6_ft rebuilds exactly these rows at boot. main.asm's LEVEL
; POOL NEED reads the entries here ({b frame_tab + fid * FT_STRIDE}). Its
; generator half (source block / offset / flags) is fdesc_tab in lowram.asm.
;==============================================================================
FT_RESUME = $
                ORG  FRT
frt_image:
FRM_EMIT = FRM_HOT
                INCLUDE "frames.asm"
                ASSERT $ - frt_image == FID_COUNT * FRT_STRIDE
                ORG  FT_RESUME

                ; Pool budget (prototype §5.2 / R-2): monsters + the largest
                ; hero + the 2 select-screen idles + worst per-bank straddle
                ; waste (<= 1 largest variant, 6 cols x 48 x 2 = 576) x 3 banks.
                ; D3-4: a hero is generated with its class FX kind (start_game),
                ; so the hero term is max(Knight + K_FXW, Wizard + K_FXM).
                ASSERT KFCNT_FXM == 17 && KFCNT_FXW == 8 && KFID_FXW + 2 == KFID_FXM + KFCNT_FXM
                ASSERT FID_knight_powerstrike >= 0 && FID_spark_fizz2 >= 0 && FID_arrow_hit >= 0
POOL_HERO_MAX = POOL_KNIGHT + POOL_FXW
    IF POOL_WIZARD + POOL_FXM > POOL_HERO_MAX
POOL_HERO_MAX = POOL_WIZARD + POOL_FXM
    ENDIF
                ; 3F-T1 (per-level pool): the pool holds the 2 idles, the hero
                ; + its FX and ONE level's monster kinds (level_enter), so the
                ; need is the worst depth: POOL_LVL_MAX = max over D1..D8 of
                ; the level's generation kinds, computed at the end of main.asm
                ; ("LEVEL POOL NEED") from the assembled lp_dtab / pool_gmap /
                ; kind_tab / frame_tab / fdesc_tab bytes — exact per frame,
                ; the same dedup as pool_list. POOL_NEED (MEM-PS2: the simulated
                ; pool top + POOL_SIM_MARGIN, worst hero x depth), its checks and the DISPLAY are
                ; defined there (DEFL, final pass only: use nothing above it).
                ; ANIM-IMPORT2: the select idles are 40 rows (24 x 40 STA, both facings = 480 B
                ; each, was 576); the straddle allowance stays 6 cols x 48 x 2 (Ogre / DK are 48)
                ASSERT knight_idle1_cols == 3 && knight_idle1_ax == 0 && wizard_idle_cols == 3 && wizard_idle_ax == 0
POOL_FIXED      EQU (knight_idle1_h + wizard_idle_h) * 2 * 3 * 2 + 3 * 576   ; select idles + straddle waste
                ; MEM-PS2: the LEVEL need no longer uses POOL_FIXED's 3 x 576 straddle guess:
                ; main.asm "LEVEL POOL NEED" replays alloc variant by variant (the real
                ; session order: idles, hero, class FX, mark, the level's units first-seen)
                ; -> the exact pool top per hero x depth (skipped bank tails counted), plus
                ; this documented safety margin; tests/zx0_pool.py checks simulated == the
                ; real ALLOC_IDX / ALLOC_PTR at every depth, both heroes and PROTO. POOL_FIXED
                ; stays the PROTO fixture's static (conservative) bound below.
POOL_SIM_MARGIN EQU 64
                ; the PROTO rooms (test fixture, proto_start = 1): every original
                ; monster kind (start_game .gk, K_SKELETON .. K_PROTO_END - 1)
K_PROTO_END     EQU K_SLIME + 1
                ASSERT KFID_SKELETON == KFID_MONSTERS && KFID_SLIME + KFCNT_SLIME == KFID_F3
                ASSERT KFID_CLIMBH + 2 == KFID_MONSTERS + KFCNT_MONSTERS   ; 3F-T13(bc): the 3F frames end the range
POOL_NEED_PROTO EQU POOL_FIXED + POOL_HERO_MAX + POOL_MONSTERS
                ; level_enter clears the FRT rows [KFID_MONSTERS, + KFCNT_MONSTERS):
                ; every monster frame must lie there (heroes before, FX kinds after)
                ASSERT KFID_MONSTERS + KFCNT_MONSTERS == KFID_FXM
POOL_CAP        EQU 3 * 16384 - (POOL_START - BANK_WINDOW) - R6_LEN - SRC6_LEN   ; D3-TX: the text block under bank 0's pool; R6 + SRC6: bank 6 ends at POOL6_END
                ASSERT POOL6_END - BANK_WINDOW == $4000 - R6_LEN - SRC6_LEN          ; POOL_CAP's bank-6 term = alloc's limit
                ASSERT FID_COUNT <= FRT_MAX
                DISPLAY "GAME class FX pool: warrior ", /D, POOL_FXW, " (", /D, KFCNT_FXW, " frames), mage ", /D, POOL_FXM, " (", /D, KFCNT_FXM, " frames); knight ", /D, POOL_KNIGHT, ", wizard ", /D, POOL_WIZARD

;==============================================================================
; ROLE TABLES (per-kind state -> frame). Stand-ins per prototype §7/§10:
;   CLIMB -> the WALK cycle; IDLE2 -> static IDLE; HURT -> resting frame;
;   DEAD -> resting frame blinking (death sequence, below); LUNGE/BITE/DIVE ->
;   the wind-up frame held; Knight BLOCK/HURT until re-padded (ax 2/3) -> rest.
;==============================================================================
                ROLE KN_REST,   FID_knight_idle1,  FID_knight_idle1
                ROLE KN_IDLE2,  FID_knight_idle2,  KN_REST
                ROLE KN_HURT,   FID_knight_hurt,   KN_REST
                ROLE KN_BLOCK,  FID_knight_block,  KN_REST
                ROLE KN_DEAD,   FID_knight_dead,   KN_REST
                ROLE KN_JUMP1,  FID_knight_jump1,  KN_REST      ; C3-7 (3B stand-in: CLIMB1 / walk)
                ROLE KN_JUMP2,  FID_knight_jump2,  FID_knight_walk1

                ROLE WZ_REST,   FID_wizard_idle,   FID_wizard_idle
                ROLE WZ_IDLE2,  FID_wizard_idle2,  WZ_REST
                ROLE WZ_HURT,   FID_wizard_hurt,   WZ_REST
                ROLE WZ_DEAD,   FID_wizard_dead,   WZ_REST
                ROLE WZ_JUMP1,  FID_wizard_jump1,  WZ_REST
                ROLE WZ_JUMP2,  FID_wizard_jump2,  FID_wizard_walk1
                ; PHASE_SHIFT: JUMP2 is drawn mid-tween at both px parities (ANIM-IMPORT2
                ; J-a: every airborne tick), so it must be a real MOT frame, never the
                ; (one-shift WK4) WALK1 stand-in
                ASSERT !PHASE_SHIFT || ((FID_knight_jump2 >= 0) && (FFL_knight_jump2 & FF_MOTION))
                ASSERT !PHASE_SHIFT || ((FID_wizard_jump2 >= 0) && (FFL_wizard_jump2 & FF_MOTION))
                ROLE WZ_SRAISE, FID_wizard_staffraise, FID_wizard_cast1
                ROLE WZ_SSWING, FID_wizard_staffswing, FID_wizard_cast2

                ROLE SK_REST,   FID_skeleton_walk1, FID_skeleton_walk1
                ROLE SK_HURT,   FID_skeleton_hurt, SK_REST

                ROLE GB_REST,   FID_goblin_walk1,  FID_goblin_walk1
                ROLE GB_HURT,   FID_goblin_hurt,   GB_REST

                ROLE GH_REST,   FID_ghost_float1,  FID_ghost_float1
                ROLE GH_LUNGE,  FID_ghost_lunge,   FID_ghost_float2
                ROLE GH_HURT,   FID_ghost_hurt,    GH_REST
                ROLE GH_DEAD,   FID_ghost_dead,    GH_REST

                ROLE RT_REST,   FID_rat_run1,      FID_rat_run1
                ROLE RT_BITE,   FID_rat_bite,      FID_rat_run1
                ROLE RT_HURT,   FID_rat_hurt,      RT_REST
                ROLE RT_DEAD,   FID_small_corpse,  RT_REST   ; 3F-T13bc: the neutral corpse (ART2 C2);
                ; CORPSE-ASHES: every monster DEAD but Bat / Slime / Ghost (seq_img DEATHSEQ)

                ROLE BT_REST,   FID_bat_flapup,    FID_bat_flapup
                ROLE BT_DIVE,   FID_bat_dive,      FID_bat_flapup
                ROLE BT_HURT,   FID_bat_hurt,      BT_REST
                ROLE BT_DEAD,   FID_bat_dead,      BT_REST

                ROLE SL_REST,   FID_slime_wobble,  FID_slime_wobble
                ROLE SL_LUNGE,  FID_slime_lunge,   FID_slime_squash
                ROLE SL_HURT,   FID_slime_hurt,    SL_REST
                ROLE SL_DEAD,   FID_slime_dead,    SL_REST

;------------------------------------------------------------------------------
; Cycle / sequence emitters.
;   MOVECYC4 / MOVECYC2 names : the KS_MOVE walk cycle (frame NAMES, not fids),
;                         1 tick per frame, even length. PHASE_SHIFT (anim
;                         .walkph): an even slot is drawn only at px & 4 = 4,
;                         an odd one only at 0 -> even slots MOT or WK4, odd
;                         slots MOT or STA/WK0 (ASSERTed; docs/conventions.md
;                         "Walk cycles"). Write every move cycle with these.
;   CLIMBCYC kind-prefix: CLIMB1/CLIMB2 alternating per tick, or the WALK
;                         cycle when the climb art is missing.
;   DEATHSEQ hurt, dead, real?, rest : HURT 3 -> DEAD 12, or the blink stand-in
;------------------------------------------------------------------------------
    MACRO MOVECYC4 cy0, cy1, cy2, cy3
        DB 4, FID_cy0, 1, FID_cy1, 1, FID_cy2, 1, FID_cy3, 1, SEQ_END
        ASSERT (FID_cy0 >= 0) && (FID_cy1 >= 0) && (FID_cy2 >= 0) && (FID_cy3 >= 0)
        ASSERT (FFL_cy0 & (FF_MOTION | FF_PH4)) && (FFL_cy2 & (FF_MOTION | FF_PH4))
        ASSERT ((FFL_cy1 & FF_MOTION) || !(FFL_cy1 & FF_PH4)) && ((FFL_cy3 & FF_MOTION) || !(FFL_cy3 & FF_PH4))
    ENDM
    MACRO MOVECYC2 cy0, cy1
        DB 2, FID_cy0, 1, FID_cy1, 1, SEQ_END
        ASSERT (FID_cy0 >= 0) && (FID_cy1 >= 0)
        ASSERT FFL_cy0 & (FF_MOTION | FF_PH4)
        ASSERT (FFL_cy1 & FF_MOTION) || !(FFL_cy1 & FF_PH4)
    ENDM
    ; The walk-cycle stand-in draws WALK1/3 at px & 4 = 0: illegal for WK4
    ; frames, so PHASE_SHIFT needs the climb art (CLIMBREST: the same).
    MACRO CLIMBCYC c1, c2, w1, w2, w3, w4
      IF ((c1) >= 0) && ((c2) >= 0)
        DB 2, c1, 1, c2, 1, SEQ_END
      ELSE
        ASSERT !PHASE_SHIFT
        DB 4, w1, 1, w2, 1, w3, 1, w4, 1, SEQ_END
      ENDIF
    ENDM
    MACRO CLIMBREST c1, w1
      IF (c1) >= 0
        DB c1, 0
      ELSE
        ASSERT !PHASE_SHIFT
        DB w1, 0
      ENDIF
    ENDM
    ; NB: sjasmplus re-substitutes macro params inside '_'-separated parts of
    ; the substituted text, so param names must not occur in any argument.
    MACRO DEATHSEQ q_h, q_d, q_x, q_r
        DB q_h, 3, 0
      IF (q_x) >= 0
        DB q_d, 12, 0
      ELSE
        DB q_r, 2, 0, q_r, 2, SF_HIDE, q_r, 2, 0, q_r, 2, SF_HIDE, q_r, 2, 0, q_r, 2, SF_HIDE
      ENDIF
        DB SEQ_END
    ENDM

;==============================================================================
; SEQUENCES (prototype §7): 3F-T2 — the per-kind sequences and the kind_seqs
; rows are MASTERS in R6 now (src/seq_img.asm, a ZX0 stream unpacked by
; pool6.asm / lowram.asm); bank 2 holds the per-level cache SEQ_ROWS / SEQ_BYTES (main.asm),
; read through kind_tab KT_SEQ (kind_seq_ptr). The macros above are used there.
; WZ_WIND: the wizard's staff wind-up ticks = its KS_IMPACT (seq_img.asm).
;==============================================================================
WZ_WIND         EQU 2

; hero_jump — the §2.4 arc frames per hero kind (anim_entity .jump; only the
; hero jumps, try_jump): 2 B/kind {JUMP1 (ticks 0 / 13, aligned), JUMP2
; (ticks 1..12, airborne)}, indexed E_KIND * 2.
hero_jump:      DB KN_JUMP1, KN_JUMP2, WZ_JUMP1, WZ_JUMP2
                ASSERT K_KNIGHT == 0 && K_WIZARD == 1

;------------------------------------------------------------------------------
; D3-7 ability animation sequences (game.md §6.1-6.3). Same (fid,ticks,flags)*
; format as the attack seqs. The projectile / strike is released on the entry
; named in abl_seq's fire tick (= sum of the ticks before it); the cast and the
; ranged seqs carry no SF_IMPACT (the projectile's own hit is the impact).
; Designer rulings (game.md §6): every ability releases at tick 2 (FXD_DELAY 2).
;------------------------------------------------------------------------------
wz_cast:        DB FID_wizard_cast1, 2, 0, FID_wizard_cast2, 3, 0, SEQ_END
kn_power:       DB FID_knight_windup, 2, 0, FID_knight_powerstrike, 3, SF_IMPACT, SEQ_END
kn_whirl:       DB FID_knight_windup, 2, 0, FID_knight_whirl, 3, SF_IMPACT, SEQ_END
kn_throw:       DB FID_knight_windup, 2, 0, FID_knight_throw, 3, 0, SEQ_END
kn_bow:         DB FID_knight_bow, 2, 0, FID_knight_bow, 2, 0, SEQ_END   ; 4 ticks, arrow released on tick 2
wz_bonk:        DB FID_wizard_cast1, 2, 0, WZ_SSWING, 3, SF_IMPACT, SEQ_END   ; staff bonk (no abl_seq row)

; abl_seq: ABL_COUNT x 3 B {DW seq, DB fire tick}, indexed ability * 3.
ABS_STRIDE      EQU 3
abl_seq:
                DW wz_cast
                DB 2                            ; Spark
                DW wz_cast
                DB 2                            ; Firebolt
                DW wz_cast
                DB 2                            ; Frost
                DW wz_cast
                DB 2                            ; Drain
                DW wz_cast
                DB 2                            ; Lightning
                DW kn_power
                DB 2                            ; Power Strike
                DW kn_whirl
                DB 2                            ; Whirlwind
                DW kn_throw
                DB 2                            ; Dagger
                DW kn_bow
                DB 2                            ; Bow
                ASSERT $ - abl_seq == ABL_COUNT * ABS_STRIDE
                ASSERT ABL_SPARK == 0 && ABL_LIGHTNING == 4 && ABL_POWER == 5 && ABL_WHIRL == 6 && ABL_DAGGER == 7 && ABL_BOW == 8

; (3F-T2: kind_rest — the per-kind resting frame — is gone: nothing read it.)

; (B3B-13: the kind names are strings TX_NM_* in src/strings.txt, bank-1 text block)

;==============================================================================
; ROOMS — prototype §8.2 on 2 storeys (B3B-3). B3B-8: rooms A-D are a PROTO
; *level* in the 3B level state (ROOM_DESC / EDGE_TAB / FLOOR_LIST, written by
; new_game from bank-3 proto_level, bank3.asm) and built by build_room_map v2
; like any generated room. Room id = 3x3 grid cell r = gy*3 + gx:
;
;   A (0,0) r0 <-> B (1,0) r1       <-> = horizontal exit on storey 1 (bottom)
;                    v                v = B's down-exit {24,2} -> C's up-exit {24,0}
;   D (0,1) r3 <-> C (1,1) r4
;
; (the only placement with A|B, B over C, D|C: A = a, B = a+1, C = a+4,
; D = a+3; a = 0). Edges A|B = e0, D|C = e2 (level_defs.asm formula).
; B3B-5 features: A|B door starts OPEN, D|C door CLOSED (the walkthrough bumps
; it), B pit p = 20 (storey 0, off the route), D dead-end block (right edge,
; storey 0, cols 29..31, rubble (28, 7)). Potions = FLOOR_LIST entries 0..3
; (POTIONS_TAKEN bit = entry index). Decor = none (proto_decor was empty since DEC1; RECLAIM-A removed it; B3B-13:
; the room-D chest and the PROTO win are gone).
;==============================================================================
ROOM_A          EQU 0
ROOM_B          EQU 1
ROOM_D          EQU 3
ROOM_C          EQU 4
EDGE_AB         EQU 0               ; A (0,0) | B (1,0): e = gy*2 + gx = 0
EDGE_DC         EQU 2               ; D (0,1) | C (1,1): e = 2
PIT_B           EQU 20              ; room B storey-0 pit, left hole col
                ASSERT ROOM_B == ROOM_A + 1 && ROOM_C == ROOM_B + GRID_W && ROOM_D == ROOM_C - 1
                ASSERT EDGE_AB < EDGES_H && EDGE_DC < EDGES_H


; (B3B-13: every game message is a token stream from src/strings.txt — TX_*
; ids, bank-1 text block; msg_push / show_impact_msg, lowram.asm.)

; per-kind stats (prototype §6.3) — emitted into the page-aligned kind_tab,
; one K_MAX (32) B array per KROW (3F-T3: ids 0..29 = the 18 base + 12 tier rows;
; 30 / 31 = the class FX kinds, which have no kind_tab column)
KROW_W          EQU 30                  ; kinds per KROW (its parameter count)
    MACRO KROW v0, v1, v2, v3, v4, v5, v6, v7, v8, v9, v10, v11, v12, v13, v14, v15, v16, v17, v18, v19, v20, v21, v22, v23, v24, v25, v26, v27, v28, v29
                DB v0, v1, v2, v3, v4, v5, v6, v7, v8, v9, v10, v11, v12, v13, v14
                DB v15, v16, v17, v18, v19, v20, v21, v22, v23, v24, v25, v26, v27, v28, v29
                DS K_MAX - KROW_W, 0
    ENDM
; (3F-T2: KROWFX — the FX kinds' KT_FID0 / KT_FCNT columns — is gone with them:
; the generation units are R6 gu_tab, pool6.asm.)
