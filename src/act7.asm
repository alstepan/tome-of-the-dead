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
;      no turn, the caller prints nothing or its own message). D3-8e: an
;      accepted projectile also runs far3 proj_pre (proj_fire's set-up + its
;      first PF_PRE_HITS strikes: ~10k T + ~3.5k a strike, up to ~60k T with
;      8 message-bearing strikes, on this otherwise light tick; the release
;      walks the rest: proj_rel). D3-8e2 (game.md §6.5.1): those strikes'
;      lines / HP must not show before the bolt -> COMBAT_NOT_BEFORE = the
;      first impact tick (pf_ftick; at most ACT_FIRE_TICK + CNB_MAX), 0 when
;      nothing was struck (a miss sets no gate).
; LOG-FIX: a spell (B < ABL_DAGGER) also logs "YOU CAST <SPELL>" first (msg_push, TX_SPL_C_SPARK + B;
;      dropped when LOG_QN >= CAST_LINE_MAX so the hit / kill line keeps its slot).
; act_begin_ok: the same without the lead-col guard (always L = 1): the power
;      attacks, which fire no projectile (act_fire skips the guard for them).
; Clobbers: A, HL (B, C, DE, IX kept)
;------------------------------------------------------------------------------
act_begin:
                push bc
                call act_lead_ok
                pop  bc
                ld   l, 0
                ret  nc
                push bc                        ; D3-8e: proj_fire's set-up + candidates
                push de                        ; now (far3 proj_pre: ~10k T on this
                ld   de, ABIL_RK               ; light input tick), the release walks
                ld   a, b                      ; only (proj_rel): the fire tick of a
                cp   ABL_DAGGER                ; Lightning through 4 bodies is the
                jr   nc, .rk                   ; heaviest of the game. Ammo: the ab_ammo
                ld   a, (LOG_QN)               ; row (ammo_fire's); spells: CAST_ROW
                cp   CAST_LINE_MAX             ; (spell_fire's). LOG-FIX: a spell first logs
                jr   nc, .cr                   ; "YOU CAST <SPELL>" ahead of proj_pre's status
                push bc                        ; lines; with >= CAST_LINE_MAX pending it is
                ld   a, b                      ; dropped instead: the ring keeps its room
                add  a, TX_SPL_C_SPARK         ; for the hit / kill line (msg_push: ~1k T)
                call msg_push                  ; (AF, BC, DE, HL)
                pop  bc
.cr:            ld   de, CAST_ROW
.rk:            call probe_act_prep            ; bank-2 test probe (abil / abil_ammo)
                ld   a, b
                ld   hl, proj_pre
                call far3                      ; (all but IX)
                ld   a, (pf_tgt)               ; D3-8e2: the panel gate (main.asm)
                inc  a
                jr   z, .cnb                   ; nothing struck: A = 0, no gate
                ld   a, (pf_ftick)
                cp   ACT_FIRE_TICK + CNB_MAX + 1
                jr   c, .cnb
                ld   a, ACT_FIRE_TICK + CNB_MAX    ; bound: a long flight
.cnb:           ld   (COMBAT_NOT_BEFORE), a
                pop  de
                pop  bc
act_begin_ok:   ld   hl, TURN_PEND
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

; act_seq — IX = hero, B = ABL_*: start its abl_seq sequence (row B: {DW seq,
; DB fire tick}; the accept, after act_begin).  Clobbers: A, DE, HL (B, C kept)
act_seq:
                ld   a, b
                add  a, a
                add  a, b
                ld   e, a
                ld   d, 0
                ld   hl, abl_seq
                add  hl, de
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                jp   start_seq                 ; bank 2 (A)
                ASSERT ABS_STRIDE == 3

;------------------------------------------------------------------------------
; act_pend — far7 from bank-2 pend_far (anim_gate, TURN_PEND != 0).
; T7: the monster phase also waits while LOG_QN > LOG_MON_MAX (at most
; LOG_WAIT_MAX ticks past max(MON_AT, COMBAT_NOT_BEFORE)), so panel_tick can drain the cast's lines on the rest
; ticks before the replies arrive (a Whirlwind on 4 bodies: 4 + 4 lines).
; Clobbers: all but IY.  ~0.3k T a waiting tick (far7 included), + <= ~23k
; T a log line
;------------------------------------------------------------------------------
; Lines left pending when the monsters act: 0, so the ring has LOG_SLOTS free
; for their replies. ROOM_CAP monsters give at most ROOM_CAP melee lines (one
; per impact via MSG_Q, spread over the anim ticks: panel / end_turn's hold
; drain them); the residual overflow is deal_hit's on-hit status lines, pushed
; at once in resolve_monsters (3D: only the Ghost's 1-in-4 CONFUSED; a 5th
; line needs >= 1 such proc with 4 monsters all hitting) — dropped and counted
; in LQ_DROP, never a corrupt ring.
LOG_MON_MAX     EQU 0
CAST_LINE_MAX   EQU LOG_SLOTS - 1              ; LOG-FIX: pending lines at which the cast line is dropped
LOG_WAIT_MAX    EQU 8                          ; ticks (320 ms): progress if the log cannot drain
                ASSERT ROOM_CAP + LOG_MON_MAX <= LOG_SLOTS
act_pend:
                ld   hl, TURN_PEND
                bit  TP_SHOT_BIT, (hl)         ; 3F-T7: monster shots in flight (R6 shot_tick:
                jr   z, .ns                    ; the FX start at the release, the hit flash at
                ld   hl, shot_tick             ; the impact; clears TP_SHOT when done). Never
                call far6                      ; with TP_ACT / TP_MON (set later, in .go)
                ld   hl, TURN_PEND
.ns:            res  TP_FIRE_BIT, (hl)         ; the fire tick is over
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
                ld   a, (ACT_ABL)              ; 3E-T16: ABL_TRAP (bit 7): a trap
                rla                            ; sequence step (R6 trap6.asm), no
                jr   c, .trp                   ; probe: an ordinary tick for budget.py
                call probe_act_fire            ; bank-2 test probe (budget "cast")
                ld   a, (ACT_ABL)
                jr   act_fire
.trp:           ld   hl, trap_step
                jp   far6
                ASSERT ABL_TRAP == $80 && ABL_COUNT < $80
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
                ld   a, (LOG_QN)               ; T7 log drain: the cast's lines first —
                cp   LOG_MON_MAX + 1           ; while more than LOG_MON_MAX are pending
                jr   c, .go                    ; the monsters wait (<= LOG_WAIT_MAX ticks
                ld   a, (MON_AT)               ; past MON_AT), so their lines find ring
                ld   b, a                      ; D3-8e2: or past COMBAT_NOT_BEFORE when
                ld   a, (COMBAT_NOT_BEFORE)    ; later (the gated lines can only start
                cp   b                         ; to drain at gate + 1: the cap is 1 tick short)
                jr   nc, .w
                ld   a, b
.w:             add  a, LOG_WAIT_MAX           ; slots. No line is drawn here: panel_tick's
                ld   b, a                      ; 1st-frame rule drains them on the light
                ld   a, (TURN_TICK)            ; rest ticks (review: a line drawn here on top
                cp   b                         ; of a heavy repaint passed the cast cap in
                ret  c                         ; "wcast4": cost-safe by construction now)
.go:            xor  a
                ld   (hl), a                   ; TURN_PEND = 0: turn_done may end it
                ld   (MON_AT), a               ; turn_input calls resolve_monsters again
                ld   hl, ST_FLAGS              ; D3-8f: the hero's action is resolved (his
                res  STS_GUARD_BIT, (hl)       ; own bounced Frost was refused under it):
                                               ; HOLD_GUARD clears before the monster phase
                ld   a, (P_ENTITIES + E_FLAGS)
                and  EF_DYING
                ret  nz                        ; the hero died of his own cast
                ld   a, (EXIT_KIND)            ; 3E-T16: a teleport turn (scroll / trap,
                or   a                         ; tele_arm's hold): no monster phase
                ret  nz
                ld   hl, resolve_monsters      ; bank 3 (cache_player: the hero's
                jp   far3                      ; position / HP as the cast left them)

;------------------------------------------------------------------------------
; act_fire — the release (act_pend, fire tick): A = ABL_*. Dispatch:
; ABL_POWER / ABL_WHIRL -> power_fire (no projectile: no guard); else the
; guard: the hero's lead col must be 1..30 (act_begin refused it at the
; accept; a fizzle here, L = 0, only if something moved him since), then
; ABL_DAGGER / ABL_BOW -> ammo_fire, else (spells) -> spell_fire; each: IX =
; hero, B = ABL_*, ABIL_DESC as abil_load left it, L = 1 fired. (proj_fire's
; fx_start drop counts in FX_DROP.)
; Clobbers: all but IY.
;------------------------------------------------------------------------------
act_fire:
                ld   ix, P_ENTITIES
                ld   b, a
                sub  ABL_POWER
                cp   ABL_WHIRL - ABL_POWER + 1
                jr   nc, .guard
                ld   a, b
                call sfx_abl                   ; SND-5: the release sound by ABL_* (A, BC kept)
                jp   power_fire
.guard:         push bc
                call act_lead_ok
                pop  bc
                ld   l, 0
                ld   a, SFX_FIZZ               ; SND-5: a fizzled release sounds FIZZ
                jp   nc, sfx_req               ; fizzle (the turn stands; sfx_req keeps L, F)
                ld   a, b
                call sfx_abl                   ; SND-5: the release sound (A, BC kept)
                cp   ABL_DAGGER
                jp   nc, ammo_fire
                jp   spell_fire
                ASSERT ABL_DAGGER > ABL_WHIRL && ABL_WHIRL > ABL_POWER && ABL_POWER > ABL_LIGHTNING
                ASSERT ABL_BOW == ABL_COUNT - 1 && ABL_DAGGER == ABL_BOW - 1
