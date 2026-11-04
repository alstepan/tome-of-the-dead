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
;   it (level_descend -> game_win, GS_WIN). TOME-FX (user 2026-11-03, replaces
;   "no flash, no ash"): a hit flashes the 2x2 ATTR_TOME_FLASH + SFX_HIT, the last leaves ATTR_TOME_ASH + SFX_KILL (the
;   glyphs stay); the lectern is inert (tome_geo6: TOME_HP 0 = no Tome).
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
tome_strike:
    IF TOME_FX
                ld   de, ATTR_TOME_FLASH * $0101
                call lect_paint                ; TOME-FX: the hit tick flashes the 2x2 (TOME_FX2: lect_back, called by the
                                               ; bank-0 dn_tm hook on the TOME_FL_N-th tick end, ends it; else the first
                                               ; INPUT tick after the turn: ash after the last hit, else its own)
    IF TOME_FX2
                ld   hl, TOME_FL               ; every hit restarts the count
                ld   (hl), TOME_FL_N
                dec  l                         ; = TOME_HP (ASSERTed adjacent)
    ELSE
                ld   hl, TOME_HP
    ENDIF
                ld   a, SFX_HIT                ; every hit sounds; the last one SFX_KILL (a spell's cast
                dec  (hl)                      ; sound, equal / higher prio, may replace it)
                jr   nz, .s
                ld   a, SFX_KILL
.s:             call sfx_req                   ; keeps AF: the dec's Z
    ELSE
                ld   hl, TOME_HP
                dec  (hl)
    ENDIF
                jp   z, tome_gone              ; low RAM (CF = 1)
                ld   a, TX_TOME_HIT
                call msg_push_t                ; LOG-DMG: "THE TOME SHUDDERS -1 HP H" (H = TOME_HP)
                scf
                ret

    IF TOME_FX
;------------------------------------------------------------------------------
; TOME-FX (user 2026-11-03). The lectern's 4 attrs live in TILE_ATTRS[T_LECT_TL..BR] (common ids, loaded at
; boot, reset by lect_norm at every level start), so a room (re-)entry, the room memory and the end card all
; draw whatever they hold: the ash after the last hit persists with no further state.
; lect_back — TOME-FX2: the bank-0 dn_tm hook (dnum0.asm; far7, TOME_FL_N tick ends after a hit = the flash has
;   been on screen 2 ticks; before TOME-FX2 turn_input called it on the first INPUT tick, so a spell's 10-tick
;   turn kept the flash up for the whole turn) and end_turn's .dead (a lethal turn must not reach the end
;   card flashed): a hit's flash (BL = ATTR_TOME_FLASH) ends: the ash if TOME_HP is 0, else the book / stand
;   attrs. Else nothing (~45 T).
; lect_paint — DE = (top TL TR, foot BL BR): set the 4 attrs, then the 2x2 repainted (rect_repaint: the attr
;   shadow + a queued restore; ROOM_MAP is unchanged, only attrs). Only in the Sanctum (a hit's turn never
;   leaves the room). lect_norm / lect_attrs (theme7.asm): DE := its own attrs / store DE's two bytes in the 4 cells.
; lect_cb — C, B = the lectern's TL col, row (LVL_SANCTUM 6: cols 1-2, 8: 29-30).
; Clobbers: all but IX (back / paint, ~9k T when it repaints); norm / attrs: HL (and DE); cb: A, BC
;------------------------------------------------------------------------------
lect_back:      ld   a, (TILE_ATTRS + T_LECT_BL)
                cp   ATTR_TOME_FLASH
                ret  nz
                ld   de, ATTR_LECT_TOP << 8 | ATTR_LECT_FOOT
                ld   a, (TOME_HP)
                or   a
                jr   nz, lect_paint
                ld   de, ATTR_TOME_ASH * $0101
lect_paint:     call lect_attrs
                call lect_cb
                ld   de, $0202
                jp   rect_repaint              ; (low RAM; hands bank 7 back)
; (lect_norm / lect_attrs: theme7.asm, level_patch7w falls into them)
lect_cb:        ld   bc, (LECT_ROW << 8) | LECT_COL_L
                ld   a, (LVL_SANCTUM)
                bit  1, a
                ret  nz                        ; S = 6: the left wall
                ld   c, LECT_COL_R
                ret
                ASSERT T_LECT_TR == T_LECT_TL + 1 && T_LECT_BL == T_LECT_TL + 2 && T_LECT_BR == T_LECT_TL + 3
                ASSERT ((TILE_ATTRS + T_LECT_TL) >> 8) == ((TILE_ATTRS + T_LECT_BR) >> 8)
                ASSERT (6 & 2) != 0 && (8 & 2) == 0
    ENDIF
