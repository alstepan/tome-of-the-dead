;==============================================================================
; combat_data3.asm — Stage 3D D3-1: combat data tables (bank 3, data only).
; INCLUDEd once from bank3.asm at the kx_tab slot (first in bank 3, page
; $C000: `ld h` + kind * KX_STRIDE in L). Source: game.md §4.1 (XP, level-up),
; §5 (rank table), §6.0-6.3 (abilities, types), §9.1 (resistances, immunity,
; KXP), §11.4 (monster DEF = 0 in 3D). All field meanings are defined HERE
; (named offsets/EQUs); tests/combat_tables.py re-derives every byte from the
; doc text independently. No code reads these yet (D3-2+).
;==============================================================================

;------------------------------------------------------------------------------
; kx_tab rows (combat_defs.asm KX_*). Responses per damage type; RSP_W marks a
; weak (x2) type: field bits stay N (0), the W mask bit is set (RES_B2).
;------------------------------------------------------------------------------
RSP_W           EQU 4               ; local to the KXROW macro (not a stored value)

    ; dty / efx / chance / turns: the kind's melee hit (KX_MELEE; 3F-T2: was
    ; combat3.asm kx_melee, game.md §9.1 dmg column + on-hit effects)
    MACRO KXROW phys, fire, cold, shock, drain, dark, imm, xp, dty, efx, chance, turns, def
                DB   ((phys) & 3) | (((fire) & 3) << 2) | (((cold) & 3) << 4) | (((shock) & 3) << 6)
                DB   ((drain) & 3) | (((dark) & 3) << 2)
                DB   (((phys) >> 2) & 1) | ((((fire) >> 2) & 1) << 1) | ((((cold) >> 2) & 1) << 2) | ((((shock) >> 2) & 1) << 3) | ((((drain) >> 2) & 1) << 4) | ((((dark) >> 2) & 1) << 5)
                DB   imm, xp
                DB   def            ; KX_DEF (3F-T3: §9.1 DEF for the new rows; the 3D rows stay 0, game.md §11.4)
                DB   (dty) | ((efx) << DH_EFX_SHIFT), ((chance) << 4) | (turns)   ; KX_MELEE
    ENDM
    MACRO KXNONE                    ; unused kind id: N everywhere, no immunity, 0 XP, PHYS melee
                DS   KX_STRIDE, 0
    ENDM

IMM_UNDEAD      EQU IMMF_SLEEP | IMMF_POISON

; kinds not listed stay zero: heroes (0 XP; their resistances come from gear),
; the retired id 2, and every kind id >= K_COUNT (no 3D kind yet; 3F adds rows).
kx_tab:
                KXROW 0,0,0,0,0,0, 0, 0, DTY_PHYS, EFX_NONE, 0, 0, 0                                  ; K_KNIGHT (hero)
                KXROW 0,0,0,0,0,0, 0, 0, DTY_PHYS, EFX_NONE, 0, 0, 0                                  ; K_WIZARD (hero)
                KXNONE                                                    ; id 2 retired
                KXROW 0,0,RSP_I,0,RSP_I,RSP_I, IMM_UNDEAD, 6, DTY_PHYS, EFX_NONE, 0, 0, 1              ; K_SKELETON (DEF 1, §9.1 / D3-1)
                KXROW 0,0,0,0,0,0, 0, 3, DTY_PHYS, EFX_NONE, 0, 0, 0                                  ; K_GOBLIN
                KXROW RSP_R,0,RSP_I,RSP_X,RSP_I,RSP_I, IMM_UNDEAD, 6, DTY_DRAIN, EFX_CONFUSED, 4, 4, 0  ; K_GHOST: the 1d4 DRAIN touch, 1 in 4 -> CONFUSED 4 (no heal: §9.1)
                KXROW 0,0,0,0,0,0, 0, 2, DTY_PHYS, EFX_NONE, 0, 0, 0                                  ; K_RAT
                KXROW 0,0,0,RSP_W,0,0, 0, 2, DTY_PHYS, EFX_NONE, 0, 0, 0                              ; K_BAT
                KXROW RSP_R,RSP_W,0,0,0,0, IMMF_SLEEP | IMMF_CONFUSE | IMMF_FEAR, 3, DTY_PHYS, EFX_NONE, 0, 0, 1 ; K_SLIME (DEF 1, D3-1)
                ; --- 3F-T3: the new base rows (game.md §9.1: resistances, immunity set, KXP, DEF, the
                ; melee hit's type / on-hit status). The on-hit status lives in KX_MELEE (deal_hit
                ; reads it today); POISON's turns nibble is HALF the turns (PSN_*). Behaviour that
                ; is NOT a plain on-hit status (Mummy FOOD drain, Ogre SLAM, parry, ACID, breed,
                ; summon, ranged, rage) is T6-T9 code keyed on the kind id.
                KXROW 0,RSP_W,0,0,0,0, 0, 4, DTY_PHYS, EFX_POISON, 0, PSN_SPIDER / 2, 0               ; K_SPIDER: bite POISON 12
                KXROW 0,RSP_W,RSP_I,0,RSP_I,RSP_I, IMM_UNDEAD, 9, DTY_DRAIN | DH_HEAL, EFX_NONE, 0, 0, 0 ; K_VAMPIRE: drain bite heals it
                KXROW 0,RSP_R,0,0,0,0, 0, 9, DTY_PHYS, EFX_NONE, 0, 0, 1                               ; K_ORC
                KXROW 0,0,RSP_I,0,RSP_I,RSP_I, IMM_UNDEAD, 7, DTY_PHYS, EFX_NONE, 0, 0, 0              ; K_ARCHER (arrow: T7)
                KXROW RSP_R,RSP_W,RSP_I,0,RSP_I,RSP_I, IMM_UNDEAD, 12, DTY_PHYS, EFX_WEAK, 3, 12, 2    ; K_MUMMY: curse 1 in 3 -> WEAK 12 (FOOD drain: T6)
                KXROW 0,0,RSP_R,0,RSP_I,RSP_I, 0, 10, DTY_PHYS, EFX_NONE, 0, 0, 0                      ; K_NECRO (Dark Bolt: T7)
                KXROW RSP_R,0,RSP_R,RSP_W,0,0, 1 << IMMF_BOSS_BIT, 60, DTY_PHYS, EFX_NONE, 0, 0, 2     ; K_OGRE: SLAM = T8
                KXROW 0,RSP_X,RSP_I,RSP_W,RSP_I,RSP_I, 1 << IMMF_BOSS_BIT, 90, DTY_PHYS, EFX_NONE, 0, 0, 3 ; K_DKNIGHT: parry 1 in 3, notch 1 in 2 = T6
                KXROW 0,0,RSP_X,RSP_X,RSP_I,RSP_R, 1 << IMMF_BOSS_BIT, 0, DTY_PHYS, EFX_NONE, 0, 0, 1  ; K_ARCHMAGE: awards 0 XP (§4.1)
                ; --- the 12 tier rows (§9.6): the base kind's resistances / immunity (+ the noted extras),
                ; own KXP (§4.1 table), DEF and on-hit status
                KXROW 0,0,0,0,0,0, 0, 3, DTY_PHYS, EFX_POISON, 4, PSN_RAT / 2, 0                       ; K_GIANT_RAT: bite 1 in 4 -> POISON 12
                KXROW 0,0,0,0,0,0, 0, 4, DTY_PHYS, EFX_NONE, 0, 0, 0                                   ; K_RABBIT_RAT (breeds: T6)
                KXROW 0,0,0,RSP_W,0,0, 0, 3, DTY_PHYS, EFX_CONFUSED, 4, 2, 0                           ; K_SCREECH: bite 1 in 4 -> CONFUSED 2
                KXROW 0,0,0,0,0,0, 0, 4, DTY_PHYS, EFX_NONE, 0, 0, 0                                   ; K_SLINGER (rock: T7)
                KXROW 0,RSP_W,0,0,0,0, 0, 6, DTY_PHYS, EFX_POISON, 0, PSN_WIDOW / 2, 0                 ; K_BLACK_WIDOW: POISON 24 (ACID: T6)
                KXROW 0,0,RSP_I,0,RSP_I,RSP_I, IMM_UNDEAD, 9, DTY_PHYS, EFX_NONE, 0, 0, 2              ; K_SKEL_GUARD: parry 1 in 4 = T6
                KXROW 0,0,RSP_I,0,RSP_I,RSP_I, IMM_UNDEAD, 12, DTY_PHYS, EFX_STUNNED, 4, 1, 3          ; K_SKEL_KNIGHT: 1 in 4 -> STUNNED 1; parry 1 in 3 = T6
                KXROW RSP_R,0,RSP_I,RSP_X,RSP_I,RSP_I, IMM_UNDEAD, 9, DTY_DRAIN, EFX_FEAR, 3, 3, 0     ; K_POLTERGEIST: touch 1 in 3 -> FEAR 3
                KXROW 0,RSP_R,0,0,0,0, IMMF_FEAR, 13, DTY_PHYS, EFX_NONE, 0, 0, 1                      ; K_ORC_BERSERK: FEAR-immune; rage = T6
                KXROW 0,RSP_R,0,0,0,0, 0, 18, DTY_PHYS, EFX_STUNNED, 3, 1, 2                           ; K_ORC_BOUNCER: 1 in 3 -> STUNNED 1
                KXROW 0,0,RSP_I,0,RSP_I,RSP_I, IMM_UNDEAD, 10, DTY_PHYS, EFX_NONE, 0, 0, 0             ; K_SNIPER (stand-and-shoot: T7)
                KXROW 0,0,RSP_R,0,RSP_I,RSP_I, 0, 15, DTY_PHYS, EFX_NONE, 0, 0, 0                      ; K_BONE_CALLER (summon: T6)
                ASSERT ($ - kx_tab) == K_COUNT * KX_STRIDE && K_COUNT == 30
                DS   KX_LEN - K_COUNT * KX_STRIDE, 0                      ; ids 30 / 31: the class FX kinds
                ASSERT kx_tab == BANK_WINDOW && $ - kx_tab == KX_LEN

; L-RELIEF: decor_gen.asm's dg_bad (64 B, 64-aligned lookup) sits here, at
; $C000 + KX_LEN = $C100: aligned by construction, so no ALIGN pad whatever the
; bank-3 code size (it was an ALIGN 64 inside decor_gen.asm: 0..63 B of pad that
; moved with every byte of code before it). Bank 3 data, read by bank-3 code only.
                INCLUDE "dg_bad3.asm"           ; GENERATED: tools/decorgen.py --asm-bad
                ASSERT dg_bad == kx_tab + KX_LEN && (dg_bad & 63) == 0 && $ - dg_bad == TILE_IDS

; (D3-9b: XP_NEXT = bank-2 xpn_tab (xp2.asm), the single table; the level-up
; gains / steps are xp_turn's immediates, bank-7 xp7.asm.)

;------------------------------------------------------------------------------
; Abilities. Index (ABL_*): the 7 rank-able ones first (ARANK order: Mage 0..4,
; Warrior 5..6), then the two ammo attacks (not rank-able, ab_ammo rows).
;------------------------------------------------------------------------------
ABL_SPARK       EQU 0
ABL_FIREBOLT    EQU 1
ABL_FROST       EQU 2
ABL_DRAIN       EQU 3
ABL_LIGHTNING   EQU 4
ABL_POWER       EQU 5
ABL_WHIRL       EQU 6
ABL_RANKED      EQU 7               ; count of rank-able abilities
ABL_DAGGER      EQU 7               ; ab_def only; ab_ammo row 0
ABL_BOW         EQU 8               ; ab_def only; ab_ammo row 1
ABL_COUNT       EQU 9
RANK_MAX        EQU 3

; --- rank table: ab_rank + (ability * RANK_MAX + rank - 1) * RK_STRIDE -------
; Ranks are cumulative (§5): each row is the full effective value at that rank.
RK_MP           EQU 0               ; MP cost
RK_RANGE        EQU 1               ; range in cells (melee abilities: 0 = reach)
RK_DIE          EQU 2               ; damage die sides (0 = the weapon die; Power Strike: multiplier code, see its rows)
RK_BONUS        EQU 3               ; flat damage bonus (Whirlwind: added to weapon die)
RK_BOUNCES      EQU 4               ; wall reversals allowed (Power Strike: extra to-hit)
RK_EFFECT       EQU 5               ; per-ability, see below
RK_STRIDE       EQU 6
; RK_EFFECT meaning (ability's ABF_* flags say which):
;   status (Spark, Frost, Power):  low nibble = turns, high nibble = chance "1 in N" (0 = always)
;   Firebolt (ABF_BURST):          low nibble = burst die sides, RKE_SPARE = burst spares the caster
;   Whirlwind:                     to-hit bonus added on top of ab_def ABD_HIT
;   Drain, Lightning:              0
RKE_SPARE       EQU $80

    MACRO RANK mp, range, die, bonus, bounces, effect
                DB   mp, range, die, bonus, bounces, effect
    ENDM
    MACRO STAT chance, turns
                DB   ((chance) << 4) | (turns)
    ENDM

ab_rank:
; RANK1 (game.md §5 rev 6): rank 2 / 3 cost 1.6-3x rank 1 for more damage per cast.
; Spark: 2 MP r6 1d4+1, 1 in 4 CONFUSED 4 (D3-8c) | 4 MP r8 1d8+2 | 6 MP r8 1d8+4, CONFUSED 1 in 2
                RANK 2, 6, 4, 1, 0, (4 << 4) | 4
                RANK 4, 8, 8, 2, 0, (4 << 4) | 4
                RANK 6, 8, 8, 4, 0, (2 << 4) | 4
; Firebolt: 3 MP r12 1d8+2, burst 1d4 | 5 MP 1d8+5, burst 1d6 | 8 MP 1d10+7, burst spares caster
                RANK 3, 12, 8, 2, 0, 4
                RANK 5, 12, 8, 5, 0, 6
                RANK 8, 12, 10, 7, 0, 6 | RKE_SPARE
; Frost Shard: 3 MP r12 1d6, 1 bounce, freeze 2 | 5 MP 1d6+1, 2 bounces, freeze 3 | 8 MP 1d6+3, freeze 4
                RANK 3, 12, 6, 0, 1, 2
                RANK 5, 12, 6, 1, 2, 3
                RANK 8, 12, 6, 3, 2, 4
; Drain Life: 3 MP r5 1d6+1 | 5 MP r8 1d6+3 | 8 MP r8 1d8+5
                RANK 3, 5, 6, 1, 0, 0
                RANK 5, 8, 6, 3, 0, 0
                RANK 8, 8, 8, 5, 0, 0
; Lightning: 5 MP r28 1d8+3, 2 bounces | 8 MP 1d8+6 | 12 MP 1d8+8, 3 bounces
                RANK 5, 28, 8, 3, 2, 0
                RANK 8, 28, 8, 6, 2, 0
                RANK 12, 28, 8, 8, 3, 0
; Power Strike (RK_DIE = the multiplier code 0 / 1 / 2 = x2 / x2.5 / x3, RK_BOUNCES = the to-hit
; added to ab_def's +2; RK_EFFECT = stun turns): 3 MP x2 +2 stun 1 | 5 MP x2.5 +3 stun 1 | 7 MP x3 +4 stun 2
                RANK 3, 0, 0, 0, 0, 1
                RANK 5, 0, 1, 0, 1, 1
                RANK 7, 0, 2, 0, 2, 2
; Whirlwind: 4 MP, dmg +1 | 7 MP, dmg +3 | 10 MP, dmg +4, to-hit +2
                RANK 4, 0, 0, 1, 0, 0
                RANK 7, 0, 0, 3, 0, 0
                RANK 10, 0, 0, 4, 0, 2
RK_LEN          EQU $ - ab_rank
                ASSERT RK_LEN == ABL_RANKED * RANK_MAX * RK_STRIDE      ; 126 B

; Dagger / bow (§6.3): same row format, no ranks; to-hit in ab_def.
; Dagger r6 1d4+2 | Bow r14 1d6+1; both PHYS.
ab_ammo:        RANK 0, 6, 4, 2, 0, 0
                RANK 0, 14, 6, 1, 0, 0
                ASSERT $ - ab_ammo == (ABL_COUNT - ABL_RANKED) * RK_STRIDE

;------------------------------------------------------------------------------
; ab_def: per-ability constants (rank-independent), row = ab_def + ability * ABD_STRIDE.
; Frame ids (D3-4): the FXF_* EQUs name the class FX kinds' frames (frames.asm
; K_FXM / K_FXW; FID_COUNT <= FRT_MAX so a fid fits a byte); FXF_NONE = no
; sprite (melee: no projectile; dagger: no impact). A one-frame sprite repeats
; its fid. Every non-NONE fid is in its class's FX kind range (ASSERTed below),
; i.e. generated with that hero.
;------------------------------------------------------------------------------
ABD_DTY         EQU 0               ; damage type DTY_*
ABD_PF1         EQU 1               ; projectile frames (alternate per tick)
ABD_PF2         EQU 2
ABD_IF1         EQU 3               ; impact frames
ABD_IF2         EQU 4
ABD_AT1         EQU 5               ; projectile attr per frame ($43 etc.; black paper)
ABD_AT2         EQU 6
ABD_SPEED       EQU 7               ; px per tick (cell aligned; 8, Lightning 16)
ABD_FLAGS       EQU 8               ; ABF_*
ABD_HIT         EQU 9               ; to-hit modifier (signed); spells never roll
ABD_STRIDE      EQU 10

ABF_SPELL       EQU %00000001       ; always hits unless I/X (§6)
ABF_PIERCE      EQU %00000010       ; Lightning: each body once per pass
ABF_BURST       EQU %00000100       ; Firebolt: burst, RK_EFFECT = die / spare flag
ABF_HEAL        EQU %00001000       ; Drain Life: caster heals the damage dealt
ABF_DMGX2       EQU %00010000       ; Power Strike: weapon damage x2
ABF_AOE         EQU %00100000       ; Whirlwind: every hostile in reach, both sides
ABF_MELEE       EQU %01000000       ; no projectile; target in reach
ABF_AMMO        EQU %10000000       ; consumes DAGGERS / ARROWS

FXF_NONE        EQU $FF
FXF_SPARK_FLY1  EQU FID_spark_fly1  ; D3-4
FXF_SPARK_FLY2  EQU FID_spark_fly2  ; D3-4
FXF_SPARK_FIZ1  EQU FID_spark_fizz1 ; D3-4
FXF_SPARK_FIZ2  EQU FID_spark_fizz2 ; D3-4
FXF_FIRE_FLY1   EQU FID_firebolt_fly1 ; D3-4
FXF_FIRE_FLY2   EQU FID_firebolt_fly2 ; D3-4
FXF_FIRE_BRST1  EQU FID_firebolt_burst1 ; D3-4
FXF_FIRE_BRST2  EQU FID_firebolt_burst2 ; D3-4
FXF_FROST_FLY   EQU FID_frost_fly   ; D3-4
FXF_FROST_CRACK EQU FID_frost_crack ; D3-4
FXF_DRAIN_FLY1  EQU FID_drain_fly1  ; D3-4
FXF_DRAIN_FLY2  EQU FID_drain_fly2  ; D3-4
FXF_DRAIN_HIT   EQU FID_drain_hit   ; D3-4
FXF_LIGHT_FLY1  EQU FID_lightning_fly1 ; D3-4
FXF_LIGHT_FLY2  EQU FID_lightning_fly2 ; D3-4
FXF_LIGHT_FLASH EQU FID_lightning_flash ; D3-4
FXF_POWER_BURST EQU FID_power_burst ; D3-4
FXF_DAGGER1     EQU FID_dagger_spin1 ; D3-4
FXF_DAGGER2     EQU FID_dagger_spin2 ; D3-4
FXF_ARROW1      EQU FID_arrow_fly1  ; D3-4
FXF_ARROW2      EQU FID_arrow_fly2  ; D3-4
FXF_ARROW_HIT   EQU FID_arrow_hit   ; D3-4
; FXM_IN / FXW_IN f — f is generated with the Mage / Warrior (its FX kind range)
    MACRO FXM_IN f
                ASSERT (f) >= KFID_FXM && (f) < KFID_FXM + KFCNT_FXM
    ENDM
    MACRO FXW_IN f
                ASSERT (f) >= KFID_FXW && (f) < KFID_FXW + KFCNT_FXW
    ENDM
                FXM_IN FXF_SPARK_FLY1
                FXM_IN FXF_SPARK_FLY2
                FXM_IN FXF_SPARK_FIZ1
                FXM_IN FXF_SPARK_FIZ2
                FXM_IN FXF_FIRE_FLY1
                FXM_IN FXF_FIRE_FLY2
                FXM_IN FXF_FIRE_BRST1
                FXM_IN FXF_FIRE_BRST2
                FXM_IN FXF_FROST_FLY
                FXM_IN FXF_FROST_CRACK
                FXM_IN FXF_DRAIN_FLY1
                FXM_IN FXF_DRAIN_FLY2
                FXM_IN FXF_DRAIN_HIT
                FXM_IN FXF_LIGHT_FLY1
                FXM_IN FXF_LIGHT_FLY2
                FXM_IN FXF_LIGHT_FLASH
                FXW_IN FXF_SPARK_FIZ1               ; Whirlwind's impact: shared range
                FXW_IN FXF_SPARK_FIZ2
                FXW_IN FXF_POWER_BURST
                FXW_IN FXF_DAGGER1
                FXW_IN FXF_DAGGER2
                FXW_IN FXF_ARROW1
                FXW_IN FXF_ARROW2
                FXW_IN FXF_ARROW_HIT

ab_def:
; Spark: SHOCK, spark_fly1/2 `$43` -> spark_fizz1/2
                DB   DTY_SHOCK, FXF_SPARK_FLY1, FXF_SPARK_FLY2, FXF_SPARK_FIZ1, FXF_SPARK_FIZ2, $43, $43, 8, ABF_SPELL, 0
; Firebolt: FIRE, yellow `$46` / red `$42` alternate (user 2026-10-06) -> firebolt_burst1/2
                DB   DTY_FIRE, FXF_FIRE_FLY1, FXF_FIRE_FLY2, FXF_FIRE_BRST1, FXF_FIRE_BRST2, $46, $42, 8, ABF_SPELL | ABF_BURST, 0
; Frost Shard: COLD, frost_fly `$45` -> frost_crack (8x8)
                DB   DTY_COLD, FXF_FROST_FLY, FXF_FROST_FLY, FXF_FROST_CRACK, FXF_FROST_CRACK, $45, $45, 8, ABF_SPELL, 0
; Drain Life: DRAIN, drain_fly1/2 `$43` -> drain_hit
                DB   DTY_DRAIN, FXF_DRAIN_FLY1, FXF_DRAIN_FLY2, FXF_DRAIN_HIT, FXF_DRAIN_HIT, $43, $43, 8, ABF_SPELL | ABF_HEAL, 0
; Lightning: SHOCK, lightning_fly1/2 `$47`, 16 px/tick -> lightning_flash
                DB   DTY_SHOCK, FXF_LIGHT_FLY1, FXF_LIGHT_FLY2, FXF_LIGHT_FLASH, FXF_LIGHT_FLASH, $47, $47, 16, ABF_SPELL | ABF_PIERCE, 0
; Power Strike: PHYS, melee, to-hit +2, x2 -> power_burst
                DB   DTY_PHYS, FXF_NONE, FXF_NONE, FXF_POWER_BURST, FXF_POWER_BURST, 0, 0, 0, ABF_MELEE | ABF_DMGX2, 2
; Whirlwind: PHYS, melee AoE, impact spark_fizz1/2 on each side
                DB   DTY_PHYS, FXF_NONE, FXF_NONE, FXF_SPARK_FIZ1, FXF_SPARK_FIZ2, 0, 0, 0, ABF_MELEE | ABF_AOE, 0
; Throw dagger: PHYS, dagger_spin1/2 `$47`, no impact sprite, to-hit atk+1 (the +1 here)
                DB   DTY_PHYS, FXF_DAGGER1, FXF_DAGGER2, FXF_NONE, FXF_NONE, $47, $47, 8, ABF_AMMO, 1
; Bow: PHYS, arrow1/2 `$07` -> arrow_hit, to-hit atk
                DB   DTY_PHYS, FXF_ARROW1, FXF_ARROW2, FXF_ARROW_HIT, FXF_ARROW_HIT, $07, $07, 8, ABF_AMMO, 0
                ASSERT $ - ab_def == ABL_COUNT * ABD_STRIDE
