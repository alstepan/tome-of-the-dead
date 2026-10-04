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
; FRAME TABLE (bank 2, FT_STRIDE = 4 B/fid: FT_COLS, FT_H, FT_OFFR, FT_OFFL —
; what the per-tick renderer reads). The list itself is src/frames.asm; its
; generator half (source block / offset / flags) is fdesc_tab in lowram.asm.
;==============================================================================
frame_tab:
FRM_EMIT = FRM_HOT
                INCLUDE "frames.asm"
                ASSERT $ - frame_tab == FID_COUNT * FT_STRIDE

                ; Pool budget (prototype §5.2 / R-2): monsters + the largest
                ; hero + the 2 select-screen idles + worst per-bank straddle
                ; waste (<= 1 largest variant, 6 cols x 48 x 2 = 576) x 3 banks.
POOL_HERO_MAX = POOL_KNIGHT
    IF POOL_WIZARD > POOL_HERO_MAX
POOL_HERO_MAX = POOL_WIZARD
    ENDIF
POOL_NEED       EQU POOL_MONSTERS + POOL_HERO_MAX + 2 * 576 + 3 * 576
                ASSERT POOL_NEED <= 3 * 16384
                ASSERT FID_COUNT <= FRT_MAX
                DISPLAY "GAME frames: ", /D, FID_COUNT, "  pool need: ", /D, POOL_NEED, " of 49152 (monsters ", /D, POOL_MONSTERS, ", hero max ", /D, POOL_HERO_MAX, ")"

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

                ROLE WZ_REST,   FID_wizard_idle,   FID_wizard_idle
                ROLE WZ_IDLE2,  FID_wizard_idle2,  WZ_REST
                ROLE WZ_HURT,   FID_wizard_hurt,   WZ_REST
                ROLE WZ_DEAD,   FID_wizard_dead,   WZ_REST

                ROLE SK_REST,   FID_skeleton_walk1, FID_skeleton_walk1
                ROLE SK_HURT,   FID_skeleton_hurt, SK_REST

                ROLE GB_REST,   FID_goblin_walk1,  FID_goblin_walk1
                ROLE GB_HURT,   FID_goblin_hurt,   GB_REST
                ROLE GB_DEAD,   FID_goblin_dead,   GB_REST

                ROLE GH_REST,   FID_ghost_float1,  FID_ghost_float1
                ROLE GH_LUNGE,  FID_ghost_lunge,   FID_ghost_float2
                ROLE GH_HURT,   FID_ghost_hurt,    GH_REST
                ROLE GH_DEAD,   FID_ghost_dead,    GH_REST

                ROLE RT_REST,   FID_rat_run1,      FID_rat_run1
                ROLE RT_BITE,   FID_rat_bite,      FID_rat_run1
                ROLE RT_HURT,   FID_rat_hurt,      RT_REST
                ROLE RT_DEAD,   FID_rat_dead,      RT_REST

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
;   CYCLE_WALK4 a,b,c,d : 4-tick walk cycle, 1 tick per frame
;   CLIMBCYC kind-prefix: CLIMB1/CLIMB2 alternating per tick, or the WALK
;                         cycle when the climb art is missing.
;   DEATHSEQ hurt, dead, real?, rest : HURT 3 -> DEAD 12, or the blink stand-in
;------------------------------------------------------------------------------
    MACRO CLIMBCYC c1, c2, w1, w2, w3, w4
      IF ((c1) >= 0) && ((c2) >= 0)
        DB 2, c1, 1, c2, 1, SEQ_END
      ELSE
        DB 4, w1, 1, w2, 1, w3, 1, w4, 1, SEQ_END
      ENDIF
    ENDM
    MACRO CLIMBREST c1, w1
      IF (c1) >= 0
        DB c1, 0
      ELSE
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
; SEQUENCES (prototype §7). cycles: DB total_ticks, (fid,ticks)*, $FF.
;                           seqs  : (fid,ticks,flags)*, $FF.
;==============================================================================
; --- Knight ---
kn_idle:        DB 32, KN_REST, 16, KN_IDLE2, 16, SEQ_END
kn_move:        DB 4, FID_knight_walk1, 1, FID_knight_walk2, 1, FID_knight_walk3, 1, FID_knight_walk4, 1, SEQ_END
kn_climb:       CLIMBCYC FID_knight_climb1, FID_knight_climb2, FID_knight_walk1, FID_knight_walk2, FID_knight_walk3, FID_knight_walk4
kn_climbrest:   CLIMBREST FID_knight_climb1, FID_knight_walk1
kn_attack:      DB FID_knight_windup, 2, 0, FID_knight_slash, 2, SF_IMPACT, FID_knight_follow, 2, 0, SEQ_END
kn_hurt:        DB KN_HURT, 3, 0, SEQ_END
kn_block:       DB KN_BLOCK, 3, 0, SEQ_END
kn_death:       DEATHSEQ KN_HURT, KN_DEAD, FID_knight_dead, KN_REST
; --- Wizard ---
wz_idle:        DB 32, WZ_REST, 16, WZ_IDLE2, 16, SEQ_END
wz_move:        DB 4, FID_wizard_walk1, 1, FID_wizard_walk2, 1, FID_wizard_walk3, 1, FID_wizard_walk4, 1, SEQ_END
wz_climb:       CLIMBCYC FID_wizard_climb1, FID_wizard_climb2, FID_wizard_walk1, FID_wizard_walk2, FID_wizard_walk3, FID_wizard_walk4
wz_climbrest:   CLIMBREST FID_wizard_climb1, FID_wizard_walk1
wz_attack:      DB FID_wizard_cast1, 2, 0, FID_wizard_cast2, 3, SF_IMPACT, SEQ_END
wz_hurt:        DB WZ_HURT, 3, 0, SEQ_END
wz_death:       DEATHSEQ WZ_HURT, WZ_DEAD, FID_wizard_dead, WZ_REST
; --- Skeleton ---
sk_idle:        DB 1, SK_REST, 1, SEQ_END
sk_move:        DB 4, FID_skeleton_walk1, 1, FID_skeleton_walk2, 1, FID_skeleton_walk3, 1, FID_skeleton_walk4, 1, SEQ_END
sk_climb:       CLIMBCYC FID_skeleton_climb1, FID_skeleton_climb2, FID_skeleton_walk1, FID_skeleton_walk2, FID_skeleton_walk3, FID_skeleton_walk4
sk_climbrest:   CLIMBREST FID_skeleton_climb1, FID_skeleton_walk1
sk_attack:      DB FID_skeleton_raise, 3, 0, FID_skeleton_cut, 2, SF_IMPACT, SEQ_END
sk_hurt:        DB SK_HURT, 3, 0, SEQ_END
                ; Skeleton death uses its sheet COLLAPSED frame (always exists)
sk_death:       DEATHSEQ SK_HURT, FID_skeleton_collapsed, FID_skeleton_collapsed, SK_REST
; --- Goblin ---
gb_idle:        DB 1, GB_REST, 1, SEQ_END
gb_move:        DB 4, FID_goblin_walk1, 1, FID_goblin_walk2, 1, FID_goblin_walk3, 1, FID_goblin_walk4, 1, SEQ_END
gb_climb:       CLIMBCYC FID_goblin_climb1, FID_goblin_climb2, FID_goblin_walk1, FID_goblin_walk2, FID_goblin_walk3, FID_goblin_walk4
gb_climbrest:   CLIMBREST FID_goblin_climb1, FID_goblin_walk1
gb_attack:      DB FID_goblin_clubup, 3, 0, FID_goblin_smash, 2, SF_IMPACT, SEQ_END
gb_hurt:        DB GB_HURT, 3, 0, SEQ_END
gb_death:       DEATHSEQ GB_HURT, GB_DEAD, FID_goblin_dead, GB_REST
; --- Ghost (flyer: FLY uses the idle loop) ---
gh_idle:        DB 12, FID_ghost_float1, 6, FID_ghost_float2, 6, SEQ_END
gh_climbrest:   DB GH_REST, 0
gh_attack:      DB FID_ghost_float2, 2, 0, GH_LUNGE, 2, SF_IMPACT, SEQ_END
gh_hurt:        DB GH_HURT, 3, 0, SEQ_END
gh_death:       DEATHSEQ GH_HURT, GH_DEAD, FID_ghost_dead, GH_REST
; --- Rat ---
rt_idle:        DB 1, RT_REST, 1, SEQ_END
rt_move:        DB 2, FID_rat_run1, 1, FID_rat_run2, 1, SEQ_END
rt_climbrest:   DB RT_REST, 0
rt_attack:      DB FID_rat_run1, 1, 0, RT_BITE, 2, SF_IMPACT, SEQ_END
rt_hurt:        DB RT_HURT, 3, 0, SEQ_END
rt_death:       DEATHSEQ RT_HURT, RT_DEAD, FID_rat_dead, RT_REST
; --- Bat (flyer) ---
bt_idle:        DB 12, FID_bat_flapup, 3, FID_bat_glide, 3, FID_bat_flapdown, 3, FID_bat_glide, 3, SEQ_END
bt_climbrest:   DB BT_REST, 0
bt_attack:      DB FID_bat_flapup, 2, 0, BT_DIVE, 2, SF_IMPACT, SEQ_END
bt_hurt:        DB BT_HURT, 3, 0, SEQ_END
bt_death:       DEATHSEQ BT_HURT, BT_DEAD, FID_bat_dead, BT_REST
; --- Slime ---
sl_idle:        DB 24, FID_slime_wobble, 8, FID_slime_squash, 4, FID_slime_wobble, 8, FID_slime_stretch, 4, SEQ_END
sl_move:        DB 2, FID_slime_squash, 1, FID_slime_stretch, 1, SEQ_END
sl_climbrest:   DB SL_REST, 0
sl_attack:      DB FID_slime_squash, 2, 0, SL_LUNGE, 2, SF_IMPACT, SEQ_END
sl_hurt:        DB SL_HURT, 3, 0, SEQ_END
sl_death:       DEATHSEQ SL_HURT, SL_DEAD, FID_slime_dead, SL_REST

;------------------------------------------------------------------------------
; kind_seqs: KS_STRIDE (18) B per kind — see KS_* in defs.asm.
;------------------------------------------------------------------------------
kind_seqs:
                DW kn_idle, kn_move, kn_climb, kn_climbrest, kn_attack, kn_hurt, kn_block, kn_death
                DB 2
                DW wz_idle, wz_move, wz_climb, wz_climbrest, wz_attack, wz_hurt, wz_hurt, wz_death
                DB 2
                DS KS_STRIDE, 0                ; K_ROGUE retired (hole keeps K_* ids stable)
                DW sk_idle, sk_move, sk_climb, sk_climbrest, sk_attack, sk_hurt, sk_hurt, sk_death
                DB 3
                DW gb_idle, gb_move, gb_climb, gb_climbrest, gb_attack, gb_hurt, gb_hurt, gb_death
                DB 3
                DW gh_idle, gh_idle, gh_idle, gh_climbrest, gh_attack, gh_hurt, gh_hurt, gh_death
                DB 2
                DW rt_idle, rt_move, rt_move, rt_climbrest, rt_attack, rt_hurt, rt_hurt, rt_death
                DB 1
                DW bt_idle, bt_idle, bt_idle, bt_climbrest, bt_attack, bt_hurt, bt_hurt, bt_death
                DB 2
                DW sl_idle, sl_move, sl_move, sl_climbrest, sl_attack, sl_hurt, sl_hurt, sl_death
                DB 2
                ASSERT $ - kind_seqs == K_COUNT * KS_STRIDE

; resting frame per kind (select screen, HOLD fallback)
kind_rest:      DB KN_REST, WZ_REST, 0, SK_REST, GB_REST, GH_REST, RT_REST, BT_REST, SL_REST

kind_names:     DW nm_knight, nm_wizard, 0, nm_skeleton, nm_goblin, nm_ghost, nm_rat, nm_bat, nm_slime
nm_knight:      DB "KNIGHT", 0
nm_wizard:      DB "WIZARD", 0
nm_skeleton:    DB "SKELETON", 0
nm_goblin:      DB "GOBLIN", 0
nm_ghost:       DB "GHOST", 0
nm_rat:         DB "RAT", 0
nm_bat:         DB "BAT", 0
nm_slime:       DB "SLIME", 0

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
; (POTIONS_TAKEN bit = entry index). Decor (A torch, D chest) = proto_decor.
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

WIN_ROOM        EQU ROOM_D
WIN_MAX_X       EQU 3               ; standing on storey 0 with x <= 3 (chest cols)


;------------------------------------------------------------------------------
; Strings (0-terminated, upper case, <= LOG_MAX chars; log lines via log_push, B3B-11).
;------------------------------------------------------------------------------
; (B3B-R2: the combat message words moved to bank-3 turn3.asm; these two stay:
; tests/world.py W15 pushes them from a stub with any bank paged)
str_found:      DB "YOU FOUND A POTION", 0
str_quaff:      DB "YOU DRINK A POTION", 0
str_died:       DB "YOU DIED - PRESS ENTER", 0
str_win:        DB "TREASURE! PRESS ENTER", 0
str_welcome:    DB "FIND THE TREASURE", 0

; per-kind stats (prototype §6.3) — emitted into the page-aligned kind_tab,
; one K_MAX (32) B array per KROW (ids 9..31 = 0 until Stage 3F kinds land)
;                  KN  WZ  RG  SK  GB  GH  RT  BT  SL
KROW_W          EQU 9                   ; kinds per KROW (its parameter count)
    MACRO KROW v0, v1, v2, v3, v4, v5, v6, v7, v8
                DB v0, v1, v2, v3, v4, v5, v6, v7, v8
                DS K_MAX - KROW_W, 0
    ENDM
