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
                ; 3F-T13: the real 3F-A1 blocks; kinds drawing another's frames share its block
                ; (Vampire / Archmage = the Necro's), a tier row names its BASE kind's block (0 B
                ; here, and the cache dedups by block: one slot)
                ;    SP      VP      OR      AR      MU      NE      OG      DK      AM
                DW   ksm_sp, ksm_vp, ksm_or, ksm_ar, ksm_mu, ksm_ne, ksm_og, ksm_dk, ksm_ne
                ;    GR      RR      SB      SL      BW      SG      SK      PG      OB      OU      SN      BC
                DW   ksm_rt, ksm_rt, ksm_bt, ksm_gb, ksm_sp, ksm_sk, ksm_sk, ksm_gh, ksm_or, ksm_or, ksm_ar, ksm_ne
                DS   2 * (K_MAX - K_COUNT), 0  ; ids 30 / 31: the class FX kinds (no sequences)
                ASSERT $ - ksm_tab == 2 * K_MAX && K_COUNT == 30

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
sk_move:        MOVECYC4 skeleton_walk2, skeleton_walk3, skeleton_walk4, skeleton_walk1
sk_climb:       CLIMBCYC FID_skeleton_climb1, FID_skeleton_climb2, FID_skeleton_walk2, FID_skeleton_walk3, FID_skeleton_walk4, FID_skeleton_walk1
sk_climbrest:   CLIMBREST FID_skeleton_climb1, FID_skeleton_walk1
sk_attack:      DB FID_skeleton_raise, 3, 0, FID_skeleton_cut, 2, SF_IMPACT, SEQ_END
sk_hurt:        DB SK_HURT, 3, 0, SEQ_END
                ; CORPSE-ASHES: DEAD = the shared small_corpse (U_DEADR; was skeleton_collapsed)
sk_death:       DEATHSEQ SK_HURT, FID_small_corpse, FID_small_corpse, SK_REST
ksm_sk_e:
; --- Goblin ---
ksm_gb:         KSMH ksm_gb_e - ksm_gb_s, 3, gb_idle, gb_move, gb_climb, gb_climbrest, gb_attack, gb_hurt, gb_hurt, gb_death, ksm_gb_s
ksm_gb_s:
gb_idle:        DB 1, GB_REST, 1, SEQ_END
gb_move:        MOVECYC4 goblin_walk2, goblin_walk3, goblin_walk4, goblin_walk1
gb_climb:       CLIMBCYC FID_goblin_climb1, FID_goblin_climb2, FID_goblin_walk2, FID_goblin_walk3, FID_goblin_walk4, FID_goblin_walk1
gb_climbrest:   CLIMBREST FID_goblin_climb1, FID_goblin_walk1
gb_attack:      DB FID_goblin_clubup, 3, 0, FID_goblin_smash, 2, SF_IMPACT, SEQ_END
gb_hurt:        DB GB_HURT, 3, 0, SEQ_END
gb_death:       DEATHSEQ GB_HURT, FID_small_corpse, FID_small_corpse, GB_REST   ; CORPSE-ASHES
ksm_gb_e:
; --- Ghost (flyer) ---
                ; 3F-D7LEV: FLY = gh_fly (anim .mv reads a flyer's KS_MOVE cycle at the
                ; idle_phase, i.e. at any px parity): FLOAT2 held (MOT), so FLOAT1 (the rest
                ; pose: idle at rest, cell-aligned) keeps ONE shift (STA, -512 B pool per
                ; Ghost level). KS_CLIMBREST = gh_idle + 1: anim .crest reads one byte, and
                ; gh_idle's first fid IS GH_REST (never used: not a climber; -2 B)
ksm_gh:         KSMH ksm_gh_e - ksm_gh_s, 2, gh_idle, gh_fly, gh_idle, gh_idle + 1, gh_attack, gh_hurt, gh_hurt, gh_death, ksm_gh_s
ksm_gh_s:
gh_idle:        DB 12, FID_ghost_float1, 6, FID_ghost_float2, 6, SEQ_END
                ASSERT GH_REST == FID_ghost_float1 && !(FFL_ghost_float1 & FF_MOTION) == !!PHASE_SHIFT
gh_fly:         DB 1, FID_ghost_float2, 1, SEQ_END
                ASSERT FFL_ghost_float2 & FF_MOTION
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
rt_death:       DEATHSEQ RT_HURT, RT_DEAD, FID_small_corpse, RT_REST
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
; --- 3F-T13: the 3F-A1 kinds (game.md §9.1 / §9.7 R3-R4) ---
; Non-climbers (Vampire, Ogre, DK, Spider): KS_CLIMB = the idle cycle
; (cell-aligned at any phase; never the move cycle, whose even slot is a WK4
; frame). 3F-T13bc climbers (Orc, Necro, Mummy families; the Mummy since 2026-10-29; the Archer / Sniper use the Skeleton's own
; skeleton_climb1/2 in their ink, U_SKCLIMB; user 2026-10-29):
; KS_CLIMB = the SHARED humanoid climb pair climb_h1 / climb_h2 (ART3 A1, unit
; U_CLIMBH, STA|SYM, drawn in the kind's KT_ATTR ink), KS_CLIMBREST = that
; cycle + 1 (anim .crest reads one byte: the cycle's first fid = climb_h1; -2 B
; a block, ASSERTed). 2-frame walk: MOVECYC2 walk2, walk1 — WALK1 (the rest
; pose) in the odd, cell-aligned slot (frames.asm). HURT = the rest frame held
; + the $42 hit flash (R4) — ANIM-IMPORT: real poses for the Spider (bite), Archer
; (skeleton_hurt); the Orc / Vampire real hurt poses are pending (feat/anim-import wip). DEAD = the shared
; small_corpse (CORPSE-ASHES: every monster but Bat / Slime / Ghost). Attack
; timing = the Skeleton's (wind-up 3, strike 2 + IMPACT; 3F-T13bc: the Orc /
; Ogre wind-up is their RAISE frame, the Vampire strikes with vamp_bite) / the
; Rat's for the Spider (1, 2). A non-climber's KS_CLIMBREST points at its HURT
; seq (first byte = the rest fid; never used); the Spider's is sp_idle + 1 = spider_walk1.
; --- Spider (32x16; Black Widow) ---
ksm_sp:         KSMH ksm_sp_e - ksm_sp_s, 1, sp_idle, sp_move, sp_idle, sp_idle + 1, sp_attack, sp_hurt, sp_hurt, sp_death, ksm_sp_s
ksm_sp_s:
sp_idle:        DB 1, FID_spider_walk1, 1, SEQ_END
sp_move:        MOVECYC2 spider_walk2, spider_walk1
sp_attack:      DB FID_spider_walk1, 1, 0, FID_spider_bite, 2, SF_IMPACT, SEQ_END
sp_hurt:        DB FID_spider_bite, 3, 0, SEQ_END        ; ANIM-IMPORT item 1: HURT = the bite pose (0 B)
sp_death:       DEATHSEQ FID_spider_bite, FID_small_corpse, FID_small_corpse, FID_spider_walk1
ksm_sp_e:
; --- Orc (Berserker, Bouncer): climber; RAISE -> ATTACK ---
ksm_or:         KSMH ksm_or_e - ksm_or_s, 3, or_idle, or_move, or_climb, or_climb + 1, or_attack, or_hurt, or_hurt, or_death, ksm_or_s
ksm_or_s:
or_idle:        DB 1, FID_orc_walk1, 1, SEQ_END
or_move:        MOVECYC2 orc_walk2, orc_walk1
or_climb:       CLIMBCYC FID_climb_h1, FID_climb_h2, FID_orc_walk1, FID_orc_walk1, FID_orc_walk1, FID_orc_walk1
or_attack:      DB FID_orc_raise, 3, 0, FID_orc_attack, 2, SF_IMPACT, SEQ_END
or_hurt:        DB FID_orc_walk1, 3, 0, SEQ_END
or_death:       DEATHSEQ FID_orc_walk1, FID_small_corpse, FID_small_corpse, FID_orc_walk1
ksm_or_e:
; --- Necromancer (Archmage, Bone Caller): climber (not the Archmage: it never walks, no
; KF_CLIMBER); walk B4 = walk2, walk4, walk3, walk1 (ART3; ANIM-IMPORT, was B3); CAST ---
ksm_ne:         KSMH ksm_ne_e - ksm_ne_s, 3, ne_idle, ne_move, ne_climb, ne_climb + 1, ne_attack, ne_hurt, ne_hurt, ne_death, ksm_ne_s
ksm_ne_s:
ne_idle:        DB 1, FID_necro_walk1, 1, SEQ_END
ne_move:        MOVECYC4 necro_walk2, necro_walk4, necro_walk3, necro_walk1   ; ANIM-IMPORT item 3: B4 (ART3)
ne_climb:       CLIMBCYC FID_climb_h1, FID_climb_h2, FID_necro_walk1, FID_necro_walk1, FID_necro_walk1, FID_necro_walk1
ne_attack:      DB FID_necro_walk1, 3, 0, FID_necro_cast, 2, SF_IMPACT, SEQ_END
ne_hurt:        DB FID_necro_walk1, 3, 0, SEQ_END
ne_death:       DEATHSEQ FID_necro_walk1, FID_small_corpse, FID_small_corpse, FID_necro_walk1
ksm_ne_e:
; --- Vampire: the Necro walk (B3, hood + staff in its own ink $05) + BITE (ART2 V1); not a climber ---
ksm_vp:         KSMH ksm_vp_e - ksm_vp_s, 3, vp_idle, vp_move, vp_idle, vp_hurt, vp_attack, vp_hurt, vp_hurt, vp_death, ksm_vp_s
ksm_vp_s:
vp_idle:        DB 1, FID_necro_walk1, 1, SEQ_END
vp_move:        MOVECYC4 necro_walk2, necro_walk4, necro_walk3, necro_walk1   ; shares the Necro B4 until its own set
vp_attack:      DB FID_necro_walk1, 3, 0, FID_vamp_bite, 2, SF_IMPACT, SEQ_END
vp_hurt:        DB FID_necro_walk1, 3, 0, SEQ_END
vp_death:       DEATHSEQ FID_necro_walk1, FID_small_corpse, FID_small_corpse, FID_necro_walk1
ksm_vp_e:
; --- Mummy: walk B4 = walk2, walk4, walk3, walk1 (ART3) ---
ksm_mu:         KSMH ksm_mu_e - ksm_mu_s, 3, mu_idle, mu_move, mu_climb, mu_climb + 1, mu_attack, mu_hurt, mu_hurt, mu_death, ksm_mu_s
ksm_mu_s:
mu_idle:        DB 1, FID_mummy_walk1, 1, SEQ_END
mu_move:        MOVECYC4 mummy_walk2, mummy_walk4, mummy_walk3, mummy_walk1
mu_climb:       CLIMBCYC FID_climb_h1, FID_climb_h2, FID_mummy_walk1, FID_mummy_walk1, FID_mummy_walk1, FID_mummy_walk1
mu_attack:      DB FID_mummy_walk1, 3, 0, FID_mummy_attack, 2, SF_IMPACT, SEQ_END
mu_hurt:        DB FID_mummy_walk1, 3, 0, SEQ_END
mu_death:       DEATHSEQ FID_mummy_walk1, FID_small_corpse, FID_small_corpse, FID_mummy_walk1
ksm_mu_e:
; --- Ogre: RAISE -> SLAM (ART2 O2 / O1) ---
ksm_og:         KSMH ksm_og_e - ksm_og_s, 3, og_idle, og_move, og_idle, og_hurt, og_attack, og_hurt, og_hurt, og_death, ksm_og_s
ksm_og_s:
og_idle:        DB 1, FID_ogre_walk1, 1, SEQ_END
og_move:        MOVECYC2 ogre_walk2, ogre_walk1
og_attack:      DB FID_ogre_raise, 3, 0, FID_ogre_slam, 2, SF_IMPACT, SEQ_END
og_hurt:        DB FID_ogre_walk1, 3, 0, SEQ_END
og_death:       DEATHSEQ FID_ogre_walk1, FID_small_corpse, FID_small_corpse, FID_ogre_walk1
ksm_og_e:
; --- Death Knight: 3F-T13bc the BLOCK frame is gone: a parry is RC_PARRY (anim: the rest
; pose + a 1-tick ATTR_PARRY flash, no sequence); KS_BLOCK = the HURT seq (never started) ---
ksm_dk:         KSMH ksm_dk_e - ksm_dk_s, 3, dk_idle, dk_move, dk_idle, dk_hurt, dk_attack, dk_hurt, dk_hurt, dk_death, ksm_dk_s
ksm_dk_s:
dk_idle:        DB 1, FID_dk_walk1, 1, SEQ_END
dk_move:        MOVECYC4 dk_walk2, dk_walk1, dk_walk3, dk_walk1   ; 3F-T13bc B3 walk (ART4)
dk_attack:      DB FID_dk_walk1, 3, 0, FID_dk_cleave, 2, SF_IMPACT, SEQ_END
dk_hurt:        DB FID_dk_walk1, 3, 0, SEQ_END
dk_death:       DEATHSEQ FID_dk_walk1, FID_small_corpse, FID_small_corpse, FID_dk_walk1
ksm_dk_e:
; --- Skeleton Archer (Sniper): the Skeleton's walk + cut = U_SKARCH; SHOOT / melee = the cut
; (game.md §9.7 DECIDED: no SHOOT art); 3F-T13bc climber (the Skeleton's own climb pair, as sk_climb; user 2026-10-29);
; DEAD = small_corpse (CORPSE-ASHES) ---
ksm_ar:         KSMH ksm_ar_e - ksm_ar_s, 3, ar_idle, ar_move, ar_climb, ar_climb + 1, ar_attack, ar_hurt, ar_hurt, ar_death, ksm_ar_s
ksm_ar_s:
ar_idle:        DB 1, SK_REST, 1, SEQ_END
ar_move:        MOVECYC4 skeleton_walk2, skeleton_walk3, skeleton_walk4, skeleton_walk1
ar_climb:       CLIMBCYC FID_skeleton_climb1, FID_skeleton_climb2, SK_REST, SK_REST, SK_REST, SK_REST
ar_attack:      DB SK_REST, 3, 0, FID_skeleton_cut, 2, SF_IMPACT, SEQ_END
ar_hurt:        DB SK_HURT, 3, 0, SEQ_END                ; ANIM-IMPORT item 2: skeleton_hurt (in U_SKARCH)
ar_death:       DEATHSEQ SK_HURT, FID_small_corpse, FID_small_corpse, SK_REST
ksm_ar_e:
                ; the 2-frame walkers' rest frame (odd slot, drawn cell-aligned) must not be WK4
                ASSERT !(FFL_spider_walk1 & FF_PH4) && !(FFL_orc_walk1 & FF_PH4) && !(FFL_necro_walk1 & FF_PH4)
                ASSERT !(FFL_mummy_walk1 & FF_PH4) && !(FFL_ogre_walk1 & FF_PH4) && !(FFL_dk_walk1 & FF_PH4)
                ; KS_CLIMBREST = the climb cycle + 1 (one byte read): that byte is climb_h1, which
                ; must be the cell-aligned STA climb art (CLIMBCYC emitted the real pair)
                ASSERT FID_climb_h1 >= 0 && FID_climb_h2 >= 0 && !(FFL_climb_h1 & (FF_PH4 | FF_MOTION))
                ; the Archer / Sniper climb with the Skeleton's own pair (sk_climb's): cell-aligned STA|SYM
                ASSERT !(FFL_skeleton_climb1 & (FF_PH4 | FF_MOTION)) && !(FFL_skeleton_climb2 & FF_MOTION)
