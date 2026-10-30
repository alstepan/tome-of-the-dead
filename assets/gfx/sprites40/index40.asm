; ============================================================================
; sprites40/index40.asm — ANIM-IMPORT2 (2026-10-30): the frames the build takes
; from the 40-px set (plan.md "40 PX APPROVED" / "ART11 DECISIONS" / "ART12 PICKS").
; Not assembled: tools/zx0_pack.py sprite_asm() reads assets/gfx/sprites40/<name>.asm
; for every name INCLUDEd here and assets/gfx/sprites/<name>.asm otherwise (the 48-px
; originals stay there; git tag archive/48px-sprites = the last all-48-px main).
; Frames are 40 rows, bottom-anchored on the unchanged 48-row (6-cell) body: FRM's
; fpy = py + BH * 8 - H draws them 8 px lower (8 px blank at the body top).
; Sources: ART11 (feat/3f-art11-40px b2178b2, tools/gen_art11_40px.py) unless noted;
; ART12 picks and the Vampire set via tools/import_anim40.py.
; ============================================================================
; --- Warrior: 19 frames (knight_dead 40x16 unchanged); J-a jump (jump2 = the leap, MOT)
        INCLUDE "knight_idle1.asm"
        INCLUDE "knight_idle2.asm"
        INCLUDE "knight_walk1.asm"
        INCLUDE "knight_walk2.asm"
        INCLUDE "knight_walk3.asm"
        INCLUDE "knight_walk4.asm"
        INCLUDE "knight_windup.asm"
        INCLUDE "knight_slash.asm"
        INCLUDE "knight_follow.asm"
        INCLUDE "knight_block.asm"
        INCLUDE "knight_hurt.asm"
        INCLUDE "knight_climb1.asm"
        INCLUDE "knight_climb2.asm"
        INCLUDE "knight_jump1.asm"
        INCLUDE "knight_jump2.asm"
        INCLUDE "knight_throw.asm"
        INCLUDE "knight_bow.asm"
        INCLUDE "knight_whirl.asm"
        INCLUDE "knight_powerstrike.asm"
; --- Mage: 15 frames (wizard_dead unchanged); HURT = ART12 V3 stagger (import_anim40 mage)
        INCLUDE "wizard_idle.asm"
        INCLUDE "wizard_idle2.asm"
        INCLUDE "wizard_walk1.asm"
        INCLUDE "wizard_walk2.asm"
        INCLUDE "wizard_walk3.asm"
        INCLUDE "wizard_walk4.asm"
        INCLUDE "wizard_cast1.asm"
        INCLUDE "wizard_cast2.asm"
        INCLUDE "wizard_climb1.asm"
        INCLUDE "wizard_climb2.asm"
        INCLUDE "wizard_hurt.asm"
        INCLUDE "wizard_jump1.asm"
        INCLUDE "wizard_jump2.asm"
        INCLUDE "wizard_staffraise.asm"
        INCLUDE "wizard_staffswing.asm"
; --- Skeleton family: 9 frames (Skeleton Archer / Sniper share U_SKARCH + U_SKCLIMB)
        INCLUDE "skeleton_walk1.asm"
        INCLUDE "skeleton_walk2.asm"
        INCLUDE "skeleton_walk3.asm"
        INCLUDE "skeleton_walk4.asm"
        INCLUDE "skeleton_cut.asm"
        INCLUDE "skeleton_hurt.asm"
        INCLUDE "skeleton_climb1.asm"
        INCLUDE "skeleton_climb2.asm"
        INCLUDE "skeleton_raise.asm"
; --- the shared humanoid climb pair (Orc / Necro / Mummy families; STA|SYM, kind ink)
        INCLUDE "climb_h1.asm"
        INCLUDE "climb_h2.asm"
; --- Orc V4 Ironhide: 6 frames (ART11; orc_walk3 / orc_hurt are new ids)
        INCLUDE "orc_walk1.asm"
        INCLUDE "orc_walk2.asm"
        INCLUDE "orc_walk3.asm"
        INCLUDE "orc_raise.asm"
        INCLUDE "orc_attack.asm"
        INCLUDE "orc_hurt.asm"
; --- Mummy V2 tomb guard: walk1..4 + attack (ART12 pick; HURT = the rest pose; import_anim40 mummy)
        INCLUDE "mummy_walk1.asm"
        INCLUDE "mummy_walk2.asm"
        INCLUDE "mummy_walk3.asm"
        INCLUDE "mummy_walk4.asm"
        INCLUDE "mummy_attack.asm"
; --- Necromancer V2 bone caster: walk1..4 + cast (ART12 pick; Archmage / Bone Caller share it;
;     import_anim40 necro)
        INCLUDE "necro_walk1.asm"
        INCLUDE "necro_walk2.asm"
        INCLUDE "necro_walk3.asm"
        INCLUDE "necro_walk4.asm"
        INCLUDE "necro_cast.asm"
