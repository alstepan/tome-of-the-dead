;==============================================================================
; frames.asm — THE frame list (fid order). INCLUDEd twice (see FRM, defs.asm):
; lowram.asm (FRM_EMIT = FRM_DESC -> fdesc_tab, bank 5) and data.asm
; (FRM_EMIT = FRM_HOT -> frame_tab, bank 2; FID_*, KFID_*/KFCNT_*, POOL_*).
; Kinds are contiguous so a kind's frames are [KT_FID0, KT_FID0 + KT_FCNT).
; Heroes are listed first; monsters after. tools/zx0_sources.py packs the
; frames named here, in this order (= gen_kind order).
;==============================================================================
FCTR = 0
POOLACC = 0
KFID_KNIGHT = FCTR
POOLACC = 0
                FRM knight_idle1,   K_KNIGHT, 24, STA
                FRM knight_idle2,   K_KNIGHT, 24, STA
                FRM knight_walk1,   K_KNIGHT, 24, MOT
                FRM knight_walk2,   K_KNIGHT, 24, MOT
                FRM knight_walk3,   K_KNIGHT, 24, MOT
                FRM knight_walk4,   K_KNIGHT, 24, MOT
                FRM knight_windup,  K_KNIGHT, 24, STA
                FRM knight_slash,   K_KNIGHT, 24, STA
                FRM knight_follow,  K_KNIGHT, 24, STA
                FRM knight_block,   K_KNIGHT, 24, STA
                FRM knight_hurt,    K_KNIGHT, 24, STA
                FRM knight_climb1,  K_KNIGHT, 24, STA|SYM
                FRM knight_climb2,  K_KNIGHT, 24, STA|SYM
                FRM knight_dead,    K_KNIGHT, 24, STA
KFCNT_KNIGHT = FCTR - KFID_KNIGHT
POOL_KNIGHT = POOLACC

KFID_WIZARD = FCTR
POOLACC = 0
                FRM wizard_idle,    K_WIZARD, 24, STA
                FRM wizard_idle2,   K_WIZARD, 24, STA
                FRM wizard_walk1,   K_WIZARD, 24, MOT
                FRM wizard_walk2,   K_WIZARD, 24, MOT
                FRM wizard_walk3,   K_WIZARD, 24, MOT
                FRM wizard_walk4,   K_WIZARD, 24, MOT
                FRM wizard_cast1,   K_WIZARD, 24, STA
                FRM wizard_cast2,   K_WIZARD, 24, STA
                FRM wizard_climb1,  K_WIZARD, 24, STA|SYM
                FRM wizard_climb2,  K_WIZARD, 24, STA|SYM
                FRM wizard_hurt,    K_WIZARD, 24, STA
                FRM wizard_dead,    K_WIZARD, 24, STA
KFCNT_WIZARD = FCTR - KFID_WIZARD
POOL_WIZARD = POOLACC

KFID_MONSTERS = FCTR
KFID_SKELETON = FCTR
POOLACC = 0
                FRM skeleton_walk1,     K_SKELETON, 24, MOT
                FRM skeleton_walk2,     K_SKELETON, 24, MOT
                FRM skeleton_walk3,     K_SKELETON, 24, MOT
                FRM skeleton_walk4,     K_SKELETON, 24, MOT
                FRM skeleton_raise,     K_SKELETON, 24, STA
                FRM skeleton_cut,       K_SKELETON, 24, STA
                FRM skeleton_collapsed, K_SKELETON, 24, STA
                FRM skeleton_climb1,    K_SKELETON, 24, STA|SYM
                FRM skeleton_climb2,    K_SKELETON, 24, STA|SYM
                FRM skeleton_hurt,      K_SKELETON, 24, STA
KFCNT_SKELETON = FCTR - KFID_SKELETON

KFID_GOBLIN = FCTR
                FRM goblin_walk1,   K_GOBLIN, 24, MOT
                FRM goblin_walk2,   K_GOBLIN, 24, MOT
                FRM goblin_walk3,   K_GOBLIN, 24, MOT
                FRM goblin_walk4,   K_GOBLIN, 24, MOT
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
                FRM rat_run2,       K_RAT, 32, MOT
                FRM rat_bite,       K_RAT, 32, STA
                FRM rat_hurt,       K_RAT, 32, STA
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
                FRM slime_stretch,  K_SLIME, 24, MOT
                FRM slime_lunge,    K_SLIME, 24, STA
                FRM slime_hurt,     K_SLIME, 24, STA
                FRM slime_dead,     K_SLIME, 24, STA
KFCNT_SLIME = FCTR - KFID_SLIME
POOL_MONSTERS = POOLACC
FID_COUNT = FCTR
KFCNT_MONSTERS = FCTR - KFID_MONSTERS
