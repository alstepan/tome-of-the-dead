;==============================================================================
; frames.asm — THE frame list (fid order). INCLUDEd twice (see FRM, defs.asm):
; lowram.asm (FRM_EMIT = FRM_DESC -> fdesc_tab, bank 5) and data.asm
; (FRM_EMIT = FRM_HOT -> frame_tab, bank 2; FID_*, KFID_*/KFCNT_*, POOL_*).
; Kinds are contiguous so a kind's frames are [KT_FID0, KT_FID0 + KT_FCNT).
; Heroes are listed first; monsters after. tools/zx0_sources.py packs the
; frames named here, in this order (= gen_kind order).
;
; Shift flags: MOT = both shifts (0, 4); STA = the one shift its anchor implies
; at px & 4 = 0; SYM = left = right. WALK CYCLES (PHASE_SHIFT, default 1; rule
; in docs/conventions.md "Walk cycles"): a move cycle (data.asm MOVECYC2/4) has
; 1 tick per entry and an even length; anim .walkph draws its even slots only
; at px & 4 = 4 (WK4: one shift) and its odd slots only at px & 4 = 0 (WK0).
; A walk frame ALSO used at rest / attack / climb / death / jump must be MOT
; (Skeleton / Goblin WALK1 = their REST, rat_run1, slime_squash). The build
; ASSERTs the cycle slots; tests/frames_phase.py checks the other uses.
;==============================================================================
FCTR = 0
POOLACC = 0
KFID_KNIGHT = FCTR
POOLACC = 0
                FRM knight_idle1,   K_KNIGHT, 24, STA
                FRM knight_idle2,   K_KNIGHT, 24, STA
                FRM knight_walk1,   K_KNIGHT, 24, WK4
                FRM knight_walk2,   K_KNIGHT, 24, WK0
                FRM knight_walk3,   K_KNIGHT, 24, WK4
                FRM knight_walk4,   K_KNIGHT, 24, WK0
                FRM knight_windup,  K_KNIGHT, 24, STA
                FRM knight_slash,   K_KNIGHT, 24, STA
                FRM knight_follow,  K_KNIGHT, 24, STA
                FRM knight_block,   K_KNIGHT, 24, STA
                FRM knight_hurt,    K_KNIGHT, 24, STA
                FRM knight_climb1,  K_KNIGHT, 24, STA|SYM
                FRM knight_climb2,  K_KNIGHT, 24, STA|SYM
                FRM knight_dead,    K_KNIGHT, 24, STA
                ; C3-7: jump (game.md §2.4). JUMP2 is drawn mid-tween (x += 4 px/tick)
                FRM knight_jump1,   K_KNIGHT, 24, STA
                FRM knight_jump2,   K_KNIGHT, 24, MOT
                ; D3-4: Warrior abilities (game.md §6.2 / §6.3; art D3-3)
                FRM knight_throw,   K_KNIGHT, 24, STA
                FRM knight_bow,     K_KNIGHT, 24, STA
                FRM knight_whirl,   K_KNIGHT, 24, STA
                FRM knight_powerstrike, K_KNIGHT, 24, STA
KFCNT_KNIGHT = FCTR - KFID_KNIGHT
POOL_KNIGHT = POOLACC

KFID_WIZARD = FCTR
POOLACC = 0
                FRM wizard_idle,    K_WIZARD, 24, STA
                FRM wizard_idle2,   K_WIZARD, 24, STA
                FRM wizard_walk1,   K_WIZARD, 24, WK4
                FRM wizard_walk2,   K_WIZARD, 24, WK0
                FRM wizard_walk3,   K_WIZARD, 24, WK4
                FRM wizard_walk4,   K_WIZARD, 24, WK0
                FRM wizard_cast1,   K_WIZARD, 24, STA
                FRM wizard_cast2,   K_WIZARD, 24, STA
                FRM wizard_climb1,  K_WIZARD, 24, STA|SYM
                FRM wizard_climb2,  K_WIZARD, 24, STA|SYM
                FRM wizard_hurt,    K_WIZARD, 24, STA
                FRM wizard_dead,    K_WIZARD, 24, STA
                ; C3-7: jump + staff melee (game.md §2.4 / §6.2)
                FRM wizard_jump1,   K_WIZARD, 24, STA
                FRM wizard_jump2,   K_WIZARD, 24, MOT
                FRM wizard_staffraise, K_WIZARD, 24, STA
                FRM wizard_staffswing, K_WIZARD, 24, STA
KFCNT_WIZARD = FCTR - KFID_WIZARD
POOL_WIZARD = POOLACC

KFID_MONSTERS = FCTR
KFID_SKELETON = FCTR
POOLACC = 0
                ; 3F-T13: walk1..4 + cut first = the Skeleton Archer's unit U_SKARCH (a PREFIX
                ; of the Skeleton's frames: pool6.asm gu_tab; the Skeleton = U_SKARCH + U_SKREST)
                FRM skeleton_walk1,     K_SKELETON, 24, MOT
                FRM skeleton_walk2,     K_SKELETON, 24, WK0
                FRM skeleton_walk3,     K_SKELETON, 24, WK4
                FRM skeleton_walk4,     K_SKELETON, 24, WK0
                FRM skeleton_cut,       K_SKELETON, 24, STA
KFID_SKREST = FCTR
                FRM skeleton_raise,     K_SKELETON, 24, STA
                FRM skeleton_collapsed, K_SKELETON, 24, STA
                FRM skeleton_climb1,    K_SKELETON, 24, STA|SYM
                FRM skeleton_climb2,    K_SKELETON, 24, STA|SYM
                FRM skeleton_hurt,      K_SKELETON, 24, STA
KFCNT_SKELETON = FCTR - KFID_SKELETON
KFCNT_SKARCH = KFID_SKREST - KFID_SKELETON
KFCNT_SKREST = FCTR - KFID_SKREST

KFID_GOBLIN = FCTR
                FRM goblin_walk1,   K_GOBLIN, 24, MOT
                FRM goblin_walk2,   K_GOBLIN, 24, WK0
                FRM goblin_walk3,   K_GOBLIN, 24, WK4
                FRM goblin_walk4,   K_GOBLIN, 24, WK0
                FRM goblin_clubup,  K_GOBLIN, 24, STA
                FRM goblin_smash,   K_GOBLIN, 24, STA
                FRM goblin_climb1,  K_GOBLIN, 24, STA|SYM
                FRM goblin_climb2,  K_GOBLIN, 24, STA|SYM
                FRM goblin_hurt,    K_GOBLIN, 24, STA
                FRM goblin_dead,    K_GOBLIN, 24, STA
KFCNT_GOBLIN = FCTR - KFID_GOBLIN

KFID_GHOST = FCTR
                FRM ghost_float1,   K_GHOST, 24, MOT
                FRM ghost_float2,   K_GHOST, 24, MOT
                FRM ghost_lunge,    K_GHOST, 24, STA
                FRM ghost_hurt,     K_GHOST, 24, STA
                FRM ghost_dead,     K_GHOST, 24, STA
KFCNT_GHOST = FCTR - KFID_GHOST

KFID_RAT = FCTR
                FRM rat_run1,       K_RAT, 32, MOT
                FRM rat_run2,       K_RAT, 32, WK0
                FRM rat_bite,       K_RAT, 32, STA
                FRM rat_hurt,       K_RAT, 32, STA
KFID_RATDEAD = FCTR                     ; 3F-T13: unit U_DEADR (the Rat's and the Spider's DEAD)
                FRM rat_dead,       K_RAT, 32, STA
KFCNT_RAT = FCTR - KFID_RAT

KFID_BAT = FCTR
                FRM bat_flapup,     K_BAT, 24, MOT
                FRM bat_glide,      K_BAT, 24, MOT
                FRM bat_flapdown,   K_BAT, 24, MOT
                FRM bat_dive,       K_BAT, 24, STA
                FRM bat_hurt,       K_BAT, 24, STA
                FRM bat_dead,       K_BAT, 24, STA
KFCNT_BAT = FCTR - KFID_BAT

KFID_SLIME = FCTR
                FRM slime_wobble,   K_SLIME, 24, STA
                FRM slime_squash,   K_SLIME, 24, MOT
                FRM slime_stretch,  K_SLIME, 24, WK0
                FRM slime_lunge,    K_SLIME, 24, STA
                FRM slime_hurt,     K_SLIME, 24, STA
                FRM slime_dead,     K_SLIME, 24, STA
KFCNT_SLIME = FCTR - KFID_SLIME
POOL_MONSTERS = POOLACC                 ; the original six kinds (the PROTO fixture's monsters)

; 3F-T13: the 3F-A1 lean frames (game.md §9.1 / §9.7 R3-R5). Packed sources in the
; bank-6 SRC6 region (tools/zx0_sources.py SRC6_KINDS). HURT = the $42 flash (no
; frame); the Vampire / Archmage / Bone Caller draw the Necro frames, the Archer /
; Sniper the Skeleton's U_SKARCH (pool6.asm pool_gmap). WALK CYCLE of the 2-frame
; walkers (docs/conventions.md "Walk cycles"): MOVECYC2 walk2, walk1 — WALK1 (the
; rest pose) sits in the ODD slot, drawn cell-aligned like every rest / attack /
; death use, so it is WK0 (one shift; MOT under PHASE_SHIFT 0) and WALK2 is the
; WK4 stride: one shift each instead of MOT + WK0 (-576 B pool per 24x48 kind).
KFID_F3 = FCTR
POOLACC = 0
KFID_SPIDER = FCTR
                FRM spider_walk1,   K_SPIDER, 32, WK0
                FRM spider_walk2,   K_SPIDER, 32, WK4
                FRM spider_bite,    K_SPIDER, 32, STA
KFCNT_SPIDER = FCTR - KFID_SPIDER
KFID_ORC = FCTR
                FRM orc_walk1,      K_ORC, 24, WK0
                FRM orc_walk2,      K_ORC, 24, WK4
                FRM orc_attack,     K_ORC, 24, STA
KFCNT_ORC = FCTR - KFID_ORC
KFID_NECRO = FCTR
                FRM necro_walk1,    K_NECRO, 24, WK0
                FRM necro_walk2,    K_NECRO, 24, WK4
                FRM necro_cast,     K_NECRO, 24, STA
KFCNT_NECRO = FCTR - KFID_NECRO
KFID_MUMMY = FCTR
                FRM mummy_walk1,    K_MUMMY, 24, WK0
                FRM mummy_walk2,    K_MUMMY, 24, WK4
                FRM mummy_attack,   K_MUMMY, 24, STA
KFCNT_MUMMY = FCTR - KFID_MUMMY
KFID_OGRE = FCTR
                FRM ogre_walk1,     K_OGRE, 32, WK0
                FRM ogre_walk2,     K_OGRE, 32, WK4
                FRM ogre_slam,      K_OGRE, 32, STA
KFCNT_OGRE = FCTR - KFID_OGRE
KFID_DKNIGHT = FCTR
                FRM dk_walk1,       K_DKNIGHT, 24, WK0
                FRM dk_walk2,       K_DKNIGHT, 24, WK4
                FRM dk_cleave,      K_DKNIGHT, 24, STA
                FRM dk_block,       K_DKNIGHT, 24, STA
KFCNT_DKNIGHT = FCTR - KFID_DKNIGHT
                ; shared units with no kind of their own (G_* = zx0 block groups; defs.asm BH_G_*)
KFID_DEADH = FCTR                       ; the shared humanoid DEAD (body 24; the Ogre draws it too)
                FRM dead_humanoid,  G_DEADH, 24, STA
KFID_NBOLT = FCTR                       ; the Necro / Archmage bolt (FX-style: cell-aligned, body 8)
                FRM nbolt_fly1,     G_NBOLT, 8, STA
                FRM nbolt_fly2,     G_NBOLT, 8, STA
                FRM nbolt_hit,      G_NBOLT, 8, STA
KFCNT_NBOLT = FCTR - KFID_NBOLT
POOL_F3 = POOLACC
KFCNT_MONSTERS = FCTR - KFID_MONSTERS

; D3-4: the class FX kinds (defs.asm K_FXM / K_FXW; game.md §6.1-6.3).
; Render-only projectile / impact frames: ax 0, body width 8 (one cell), all
; STATIONARY (cell-aligned: one shift; 2 x source in the pool), SYM where the
; art is mirror-symmetric (drain_hit, power_burst: left = right). The two
; kinds' ranges overlap on spark_fizz1/2 (Spark impact = Whirlwind impact):
;   K_FXM = [KFID_FXM, KFID_FXM + KFCNT_FXM) = mage-only + shared
;   K_FXW = [KFID_FXW, KFID_FXW + KFCNT_FXW) = shared + warrior-only
; The FRM kind argument (BH_ ASSERT, zx0_sources block grouping) is the
; owning kind; the shared pair is grouped with K_FXW.
KFID_FXM = FCTR
POOLACC = 0
                FRM spark_fly1,       K_FXM, 8, STA
                FRM spark_fly2,       K_FXM, 8, STA
                FRM firebolt_fly1,    K_FXM, 8, STA
                FRM firebolt_fly2,    K_FXM, 8, STA
                FRM firebolt_burst1,  K_FXM, 8, STA
                FRM firebolt_burst2,  K_FXM, 8, STA
                FRM frost_fly,        K_FXM, 8, STA
                FRM frost_crack,      K_FXM, 8, STA
                FRM drain_fly1,       K_FXM, 8, STA
                FRM drain_fly2,       K_FXM, 8, STA
                FRM drain_hit,        K_FXM, 8, STA|SYM
                FRM lightning_fly1,   K_FXM, 8, STA
                FRM lightning_fly2,   K_FXM, 8, STA
                FRM lightning_flash,  K_FXM, 8, STA
                FRM staff_bonk,       K_FXM, 8, STA
POOL_FXM_ONLY = POOLACC
KFID_FXW = FCTR
POOLACC = 0
                FRM spark_fizz1,      K_FXW, 8, STA
                FRM spark_fizz2,      K_FXW, 8, STA
POOL_FX_SHARED = POOLACC
KFCNT_FXM = FCTR - KFID_FXM
POOLACC = 0
                FRM power_burst,      K_FXW, 8, STA|SYM
                FRM dagger_spin1,     K_FXW, 8, STA
                FRM dagger_spin2,     K_FXW, 8, STA
                FRM arrow_fly1,       K_FXW, 8, STA
                FRM arrow_fly2,       K_FXW, 8, STA
                FRM arrow_hit,        K_FXW, 8, STA
KFCNT_FXW = FCTR - KFID_FXW
POOL_FXM = POOL_FXM_ONLY + POOL_FX_SHARED
POOL_FXW = POOL_FX_SHARED + POOLACC
FID_COUNT = FCTR
