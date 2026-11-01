;==============================================================================
; tome7.asm — P3 the Tome of Absolute Death Magic (game.md §1.3; user rulings
; 2026-10-31), bank 7 part (bank7.asm rules: no data, no SMC). The Tome is no
; entity: the lectern (2x2 tiles T_LECT_TL..BR, TF_SOLID | TF_ATTACK) that bank-3
; build_room_map stamps on storey 1 against the Sanctum's dead-end wall
; (level_defs.asm LECT_*), its hp TOME_HP (sanctum_leaf: TOME_MAX once per level).
;   A hit counts when an attack is RELEASED by a hero standing on storey 1 of the
;   Sanctum, FACING the lectern, its gap (empty cols between the body and the
;   lectern) < that attack's reach / range — geometry only (R6 tome_geo6), no
;   projectile / tile collision (the ruling): melee (bump: try_horizontal, FIRE:
;   intent7 ic_melee), Power Strike / Whirlwind (abil_melee accepts with no body
;   target; act_fire counts at the release), spells / daggers / arrows (act_fire).
;   Never missed, no resistance, 1 hp a hit, "THE TOME SHUDDERS"; the 5th (WIN2,
;   user 2026-11-01): tome_gone (low RAM: "THE TOME IS DESTROYED", the lair grate
;   opens through grate_open.op); the run goes on until the hero leaves through
;   it (level_descend -> game_win, GS_WIN). No $43 flash, no ash: the lectern
;   stays, inert (tome_geo6: TOME_HP 0 = no Tome).
;   The aura: low-RAM tome_aura (end_turn).
;==============================================================================

;------------------------------------------------------------------------------
; tome_in — IX = hero, C = the attack's reach / range in cells: CF = 1 iff the
; Tome is faced within it (gap < C; facing away / no Tome: L >= $80, never).
; Clobbers: A, HL (BC, DE, IX kept: abil_melee's empty mask DE stays 0).
;   ~0.4k T (far6 + tome_geo6)
; tome_rel — the same, then a hit if so (tome_strike): CF = 1 struck.
; tome_strike — the Tome loses 1 hp (never missed, no resistance): "THE TOME
; SHUDDERS"; at 0 tome_gone (low RAM; the gate opens). CF = 1. Only after
; tome_in (TOME_HP > 0 there): the bump enters at tome_rel too (bank7.asm .tome).
; Clobbers (rel / strike): AF, BC, DE, HL (IX kept).   ~1.5k T (the line)
;------------------------------------------------------------------------------
tome_in:        push bc                        ; (far6 does not pass BC)
                ld   hl, tome_geo6             ; R6 tome6.asm: L = gap (+ $80) / $FF
                call far6
                pop  bc
                ld   a, l
                cp   c
                ret
tome_rel:       call tome_in
                ret  nc
tome_strike:    ld   hl, TOME_HP
                dec  (hl)
                jp   z, tome_gone              ; low RAM (CF = 1)
                ld   a, TX_TOME_HIT
                call msg_push_t                ; LOG-DMG: "THE TOME SHUDDERS -1 HP H" (H = TOME_HP)
                scf
                ret
