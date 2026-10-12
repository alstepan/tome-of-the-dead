;==============================================================================
; act7.asm — D3-7 T1, bank 7 (bank7.asm rules: no data, no SMC): the split
; ability turn (game.md §2.2 "Casts and missiles", designer 2026-10-12;
; docs/memory-map.md "Projectiles"). Timeline of an ability turn:
;   input tick (TURN_TICK 0): the ability's accept (abil_spell / abil_melee /
;     abil_ammo) pays the cost, starts the hero's sequence and calls
;     act_begin -> TURN_PEND = TP_ACT | TP_MON, ACT_AT = f, MON_AT = f + 1;
;     turn_input then skips resolve_monsters (MON_AT != 0);
;   every later tick: anim_gate (bank 2) -> pend_far -> act_pend, BEFORE
;     anim_tick / fx_tick (what starts here animates from this tick on, as
;     on the input tick):
;   fire tick f (TURN_TICK == ACT_AT): TP_ACT -> TP_FIRE (panel item and
;     decor_tick skip this tick), probe_act_fire, act_fire (A = ACT_ABL);
;   the first tick with TURN_TICK >= MON_AT and FX_BUSY == 0 (the hero's FX
;     idle: its last impact shown and erased): TURN_PEND = MON_AT = 0, then
;     resolve_monsters (far3) unless the hero is DYING.
; turn_done waits while TURN_PEND != 0. Contended bank: once per event.
;==============================================================================

;------------------------------------------------------------------------------
; act_lead — IX = hero -> A = its leading body col in the facing (x facing
; left, x + w - 1 facing right: where proj_fire starts).  Clobbers: A, B, HL
;------------------------------------------------------------------------------
act_lead:
                ld   a, (ix+E_X)
                bit  EF_LEFT_BIT, (ix+E_FLAGS)
                ret  nz
                ld   b, a
                KFIELD KT_BW
                add  a, b
                dec  a
                ret

; act_lead_ok — IX = hero: CF = 1 if the lead col is 1..30 (a projectile's
; first cell is inside the room: PF_ROWF is indexed by col).  Clobbers: A, B, HL
act_lead_ok:
                call act_lead
                dec  a                         ; 1..30 -> 0..29; 0 -> $FF, 31 -> 30
                cp   ROOM_COLS - 2
                ret

;------------------------------------------------------------------------------
; act_begin — the accept of an ability turn (input tick; abil_* code, after
; it validated the cost, before it pays): IX = hero, B = ABL_*.
; Out: L = 1 accepted: TURN_PEND = TP_ACT | TP_MON, ACT_ABL = B, ACT_AT =
;      ACT_FIRE_TICK, MON_AT = ACT_FIRE_TICK + 1 (the caller pays the cost and
;      starts the sequence); L = 0 refused, nothing changed (lead col 0 / 31:
;      no turn, the caller prints nothing or its own message).
; Clobbers: A, HL (B, C, DE, IX kept)
;------------------------------------------------------------------------------
act_begin:
                push bc
                call act_lead_ok
                pop  bc
                ld   l, 0
                ret  nc
                ld   hl, TURN_PEND
                ld   (hl), TP_ACT | TP_MON
                inc  l
                ld   (hl), b                   ; ACT_ABL
                inc  l
                ld   (hl), ACT_FIRE_TICK       ; ACT_AT
                inc  l
                ld   (hl), ACT_FIRE_TICK + 1   ; MON_AT
                ld   l, 1
                ret
                ASSERT ACT_ABL == TURN_PEND + 1 && ACT_AT == TURN_PEND + 2 && MON_AT == TURN_PEND + 3
                ASSERT (TURN_PEND >> 8) == (MON_AT >> 8) && ACT_FIRE_TICK > 0

;------------------------------------------------------------------------------
; act_pend — far7 from bank-2 pend_far (anim_gate, TURN_PEND != 0).
; Clobbers: all but IY.  ~0.3k T a waiting tick (far7 included)
;------------------------------------------------------------------------------
act_pend:
                ld   hl, TURN_PEND
                res  TP_FIRE_BIT, (hl)         ; the fire tick is over
                bit  TP_ACT_BIT, (hl)
                jr   z, .mon
                ld   a, (ACT_AT)
                ld   b, a
                ld   a, (TURN_TICK)
                cp   b
                ret  c                         ; before the release
                ld   a, (hl)
                xor  TP_ACT | TP_FIRE          ; TP_ACT was set, TP_FIRE clear
                ld   (hl), a
                call probe_act_fire            ; bank-2 test probe (budget "cast")
                ld   a, (ACT_ABL)
                jr   act_fire
.mon:           bit  TP_MON_BIT, (hl)
                ret  z
                ld   a, (FX_BUSY)              ; the hero's FX first (designer
                or   a                         ; 2026-10-12: not at a fixed f + 1)
                ret  nz
                ld   a, (MON_AT)
                ld   b, a
                ld   a, (TURN_TICK)
                cp   b
                ret  c
                xor  a
                ld   (hl), a                   ; TURN_PEND = 0: turn_done may end it
                ld   (MON_AT), a               ; turn_input calls resolve_monsters again
                ld   a, (P_ENTITIES + E_FLAGS)
                and  EF_DYING
                ret  nz                        ; the hero died of his own cast
                ld   hl, resolve_monsters      ; bank 3 (cache_player: the hero's
                jp   far3                      ; position / HP as the cast left them)

;------------------------------------------------------------------------------
; act_fire — the release (act_pend, fire tick): A = ABL_*. Guard: the hero's
; lead col must be 1..30 (act_begin refused it at the accept; a fizzle here,
; L = 0, only if something moved him since). Dispatch: ABL_DAGGER / ABL_BOW
; -> ammo_fire, ABL_POWER / ABL_WHIRL -> power_fire, else (spells) ->
; spell_fire; each: IX = hero, B = ABL_*, ABIL_DESC as abil_load left it,
; L = 1 fired. (proj_fire's fx_start drop counts in FX_DROP.)
; Clobbers: all but IY.
;------------------------------------------------------------------------------
act_fire:
                ld   ix, P_ENTITIES
                ld   c, a
                call act_lead_ok
                ld   l, 0
                ret  nc                        ; fizzle (the turn stands)
                ld   a, c
                ld   b, a
                cp   ABL_DAGGER
                jp   nc, ammo_fire
                cp   ABL_POWER
                jp   nc, power_fire
                jp   spell_fire
                ASSERT ABL_DAGGER > ABL_WHIRL && ABL_WHIRL > ABL_POWER && ABL_POWER > ABL_LIGHTNING
                ASSERT ABL_BOW == ABL_COUNT - 1 && ABL_DAGGER == ABL_BOW - 1
