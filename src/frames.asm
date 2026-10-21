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
                FRM skeleton_walk1,     K_SKELETON, 24, MOT
                FRM skeleton_walk2,     K_SKELETON, 24, WK0
                FRM skeleton_walk3,     K_SKELETON, 24, WK4
                FRM skeleton_walk4,     K_SKELETON, 24, WK0
                FRM skeleton_raise,     K_SKELETON, 24, STA
                FRM skeleton_cut,       K_SKELETON, 24, STA
                FRM skeleton_collapsed, K_SKELETON, 24, STA
                FRM skeleton_climb1,    K_SKELETON, 24, STA|SYM
                FRM skeleton_climb2,    K_SKELETON, 24, STA|SYM
                FRM skeleton_hurt,      K_SKELETON, 24, STA
KFCNT_SKELETON = FCTR - KFID_SKELETON

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
POOL_MONSTERS = POOLACC
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
