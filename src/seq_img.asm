;==============================================================================
; seq_img.asm — 3F-T2 the kind SEQUENCE MASTERS (prototype §7 sequences, were
; data.asm's bank-2 kind_seqs + per-kind sequences). Assembled by main.asm
; "OVERLAYS" as a raw image DISPed at SQ_IMG (low RAM, the play-free GEN_SRC
; window) -> build/ovl/seq.bin; tools/build.sh packs it; pass 2 INCBINs the
; stream into R6 (sqm_zx0). R6 pool6.asm unpacks it to SQ_IMG and copies a
; kind's block into the bank-2 cache (SEQ_ROWS / SEQ_BYTES), relocating the
; 8 row pointers (docs/memory-map.md "Sequence cache (3F-T2)").
;
; Layout: ksm_tab (K_MAX words: the kind's master block, 0 = none; a tier row
; names its BASE kind's block, so tiers cost one word and share the cache
; slot), then the blocks. Block (defs.asm KSM_*): DB n, impact, 8 offsets
; (KS_IDLE..KS_DEATH order) from the first sequence byte, then the n bytes.
; Sequences hold no pointers, so a block is position-independent. Formats:
;   cycles: DB total_ticks, (fid, ticks)*, $FF     seqs: (fid, ticks, flags)*, $FF
; Macros (MOVECYC4 / MOVECYC2 / CLIMBCYC / CLIMBREST / DEATHSEQ) and the role
; EQUs (KN_REST, ...) are data.asm's.
;==============================================================================
ksm_tab:
                DW   ksm_kn, ksm_wz, 0, ksm_sk, ksm_gb, ksm_gh, ksm_rt, ksm_bt, ksm_sl
                DS   2 * (K_MAX - K_COUNT), 0  ; ids 9..31: 3F rows (tiers -> their base block)
                ASSERT $ - ksm_tab == 2 * K_MAX && K_COUNT == 9

    ; KSMH nm: the block header; offsets are from nm_s (the first byte)
    MACRO KSMH len, imp, q0, q1, q2, q3, q4, q5, q6, q7, base
                DB   len, imp
                DB   q0 - base, q1 - base, q2 - base, q3 - base, q4 - base, q5 - base, q6 - base, q7 - base
                ASSERT (len) > 0 && (len) < 256
    ENDM

; --- Knight ---
ksm_kn:         KSMH ksm_kn_e - ksm_kn_s, 2, kn_idle, kn_move, kn_climb, kn_climbrest, kn_attack, kn_hurt, kn_block, kn_death, ksm_kn_s
ksm_kn_s:
kn_idle:        DB 32, KN_REST, 16, KN_IDLE2, 16, SEQ_END
kn_move:        MOVECYC4 knight_walk1, knight_walk2, knight_walk3, knight_walk4
kn_climb:       CLIMBCYC FID_knight_climb1, FID_knight_climb2, FID_knight_walk1, FID_knight_walk2, FID_knight_walk3, FID_knight_walk4
kn_climbrest:   CLIMBREST FID_knight_climb1, FID_knight_walk1
kn_attack:      DB FID_knight_windup, 2, 0, FID_knight_slash, 2, SF_IMPACT, FID_knight_follow, 2, 0, SEQ_END
kn_hurt:        DB KN_HURT, 3, 0, SEQ_END
kn_block:       DB KN_BLOCK, 3, 0, SEQ_END
kn_death:       DEATHSEQ KN_HURT, KN_DEAD, FID_knight_dead, KN_REST
ksm_kn_e:
; --- Wizard ---
                ; C3-7: KS_ATTACK = the staff melee (gap 0, game.md §6.2: STAFF_RAISE
                ; wind-up -> STAFF_SWING strike, IMPACT on the swing). D3-0: the
                ; PROTO ranged zap (CAST1 -> CAST2 at gap > 0) is gone: a Mage
                ; with no spell has no ranged attack (game.md §5 / §11.4).
                ; WZ_WIND (data.asm) = the wind-up ticks = the wizard's KS_IMPACT.
ksm_wz:         KSMH ksm_wz_e - ksm_wz_s, WZ_WIND, wz_idle, wz_move, wz_climb, wz_climbrest, wz_attack, wz_hurt, wz_hurt, wz_death, ksm_wz_s
ksm_wz_s:
wz_idle:        DB 32, WZ_REST, 16, WZ_IDLE2, 16, SEQ_END
wz_move:        MOVECYC4 wizard_walk1, wizard_walk2, wizard_walk3, wizard_walk4
wz_climb:       CLIMBCYC FID_wizard_climb1, FID_wizard_climb2, FID_wizard_walk1, FID_wizard_walk2, FID_wizard_walk3, FID_wizard_walk4
wz_climbrest:   CLIMBREST FID_wizard_climb1, FID_wizard_walk1
wz_attack:      DB WZ_SRAISE, WZ_WIND, 0, WZ_SSWING, 3, SF_IMPACT, SEQ_END
wz_hurt:        DB WZ_HURT, 3, 0, SEQ_END
wz_death:       DEATHSEQ WZ_HURT, WZ_DEAD, FID_wizard_dead, WZ_REST
ksm_wz_e:
; --- Skeleton ---
ksm_sk:         KSMH ksm_sk_e - ksm_sk_s, 3, sk_idle, sk_move, sk_climb, sk_climbrest, sk_attack, sk_hurt, sk_hurt, sk_death, ksm_sk_s
ksm_sk_s:
sk_idle:        DB 1, SK_REST, 1, SEQ_END
sk_move:        MOVECYC4 skeleton_walk1, skeleton_walk2, skeleton_walk3, skeleton_walk4
sk_climb:       CLIMBCYC FID_skeleton_climb1, FID_skeleton_climb2, FID_skeleton_walk1, FID_skeleton_walk2, FID_skeleton_walk3, FID_skeleton_walk4
sk_climbrest:   CLIMBREST FID_skeleton_climb1, FID_skeleton_walk1
sk_attack:      DB FID_skeleton_raise, 3, 0, FID_skeleton_cut, 2, SF_IMPACT, SEQ_END
sk_hurt:        DB SK_HURT, 3, 0, SEQ_END
                ; Skeleton death uses its sheet COLLAPSED frame (always exists)
sk_death:       DEATHSEQ SK_HURT, FID_skeleton_collapsed, FID_skeleton_collapsed, SK_REST
ksm_sk_e:
; --- Goblin ---
ksm_gb:         KSMH ksm_gb_e - ksm_gb_s, 3, gb_idle, gb_move, gb_climb, gb_climbrest, gb_attack, gb_hurt, gb_hurt, gb_death, ksm_gb_s
ksm_gb_s:
gb_idle:        DB 1, GB_REST, 1, SEQ_END
gb_move:        MOVECYC4 goblin_walk1, goblin_walk2, goblin_walk3, goblin_walk4
gb_climb:       CLIMBCYC FID_goblin_climb1, FID_goblin_climb2, FID_goblin_walk1, FID_goblin_walk2, FID_goblin_walk3, FID_goblin_walk4
gb_climbrest:   CLIMBREST FID_goblin_climb1, FID_goblin_walk1
gb_attack:      DB FID_goblin_clubup, 3, 0, FID_goblin_smash, 2, SF_IMPACT, SEQ_END
gb_hurt:        DB GB_HURT, 3, 0, SEQ_END
gb_death:       DEATHSEQ GB_HURT, GB_DEAD, FID_goblin_dead, GB_REST
ksm_gb_e:
; --- Ghost (flyer: FLY uses the idle loop) ---
ksm_gh:         KSMH ksm_gh_e - ksm_gh_s, 2, gh_idle, gh_idle, gh_idle, gh_climbrest, gh_attack, gh_hurt, gh_hurt, gh_death, ksm_gh_s
ksm_gh_s:
gh_idle:        DB 12, FID_ghost_float1, 6, FID_ghost_float2, 6, SEQ_END
gh_climbrest:   DB GH_REST, 0
gh_attack:      DB FID_ghost_float2, 2, 0, GH_LUNGE, 2, SF_IMPACT, SEQ_END
gh_hurt:        DB GH_HURT, 3, 0, SEQ_END
gh_death:       DEATHSEQ GH_HURT, GH_DEAD, FID_ghost_dead, GH_REST
ksm_gh_e:
; --- Rat ---
                ; rat / slime: KS_CLIMB = the move cycle (never used: not KF_CLIMBER,
                ; but a vertical M_MOVE would draw it at px & 4 = 0 with any phase):
                ; its even-slot frames must keep both shifts (ASSERT after the slime)
ksm_rt:         KSMH ksm_rt_e - ksm_rt_s, 1, rt_idle, rt_move, rt_move, rt_climbrest, rt_attack, rt_hurt, rt_hurt, rt_death, ksm_rt_s
ksm_rt_s:
rt_idle:        DB 1, RT_REST, 1, SEQ_END
rt_move:        MOVECYC2 rat_run1, rat_run2
rt_climbrest:   DB RT_REST, 0
rt_attack:      DB FID_rat_run1, 1, 0, RT_BITE, 2, SF_IMPACT, SEQ_END
rt_hurt:        DB RT_HURT, 3, 0, SEQ_END
rt_death:       DEATHSEQ RT_HURT, RT_DEAD, FID_rat_dead, RT_REST
ksm_rt_e:
; --- Bat (flyer) ---
ksm_bt:         KSMH ksm_bt_e - ksm_bt_s, 2, bt_idle, bt_idle, bt_idle, bt_climbrest, bt_attack, bt_hurt, bt_hurt, bt_death, ksm_bt_s
ksm_bt_s:
bt_idle:        DB 12, FID_bat_flapup, 3, FID_bat_glide, 3, FID_bat_flapdown, 3, FID_bat_glide, 3, SEQ_END
bt_climbrest:   DB BT_REST, 0
bt_attack:      DB FID_bat_flapup, 2, 0, BT_DIVE, 2, SF_IMPACT, SEQ_END
bt_hurt:        DB BT_HURT, 3, 0, SEQ_END
bt_death:       DEATHSEQ BT_HURT, BT_DEAD, FID_bat_dead, BT_REST
ksm_bt_e:
; --- Slime ---
ksm_sl:         KSMH ksm_sl_e - ksm_sl_s, 2, sl_idle, sl_move, sl_move, sl_climbrest, sl_attack, sl_hurt, sl_hurt, sl_death, ksm_sl_s
ksm_sl_s:
sl_idle:        DB 24, FID_slime_wobble, 8, FID_slime_squash, 4, FID_slime_wobble, 8, FID_slime_stretch, 4, SEQ_END
sl_move:        MOVECYC2 slime_squash, slime_stretch
sl_climbrest:   DB SL_REST, 0
sl_attack:      DB FID_slime_squash, 2, 0, SL_LUNGE, 2, SF_IMPACT, SEQ_END
sl_hurt:        DB SL_HURT, 3, 0, SEQ_END
sl_death:       DEATHSEQ SL_HURT, SL_DEAD, FID_slime_dead, SL_REST
ksm_sl_e:
                ASSERT (FFL_rat_run1 & FF_MOTION) && (FFL_slime_squash & FF_MOTION)
