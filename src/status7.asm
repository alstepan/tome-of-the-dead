;==============================================================================
; status7.asm — D3-8 status effects, bank 7 (bank7.asm rules: no data, no
; SMC; contended: once per entity per turn, never per tick). game.md §6.4,
; §2.2 "Status step" / "Held hero", §2.3 (illegal = no turn; the CONFUSED
; exception). The effects are APPLIED by deal_hit (combat3.asm, bank 3); the
; tint is derived by render (anim.asm st_tint) and the hero's 2 panel icons
; by icon_poll / st_sig (icons.asm), both from ST_FLAGS: nothing here keeps
; a second copy of the state.
;   st_step     the status step of one entity (hero: turn_input; monsters:
;               mon_status)
;   mon_status  far7 from resolve_monsters (bank 3) for a monster with
;               STATUS != 0: the step, then CONFUSED / FEAR behaviour
;   conf_roll / h_walk / h_jump / h_stumble / fear_chk   the hero's CONFUSED
;               reversal and FEAR refusal (bank7.asm tpt_intent, intent7.asm)
;==============================================================================

;------------------------------------------------------------------------------
; st_step — the status step (game.md §6.4), IX = entity, A = its slot:
;  1. POISON: timer - 1; a new value that is a multiple of 3 (0 included)
;     costs 1 HP, never below 1 (poison never kills), and wakes a sleeper
;     (any HP loss); at 0 POISON clears ("THE POISON WEARS OFF", hero).
;  2. WEAK, then MIND: timer - 1, at 0 clear (the hero's end line).
;  3. HOLD set: timer - 1, the action is skipped (L = 1); at 0 clear (ASLEEP:
;     "WAKES UP" / "YOU WAKE UP", FROZEN / STUNNED: "YOU CAN MOVE AGAIN", hero
;     only); a FROZEN / STUNNED that just cleared sets HOLD_GUARD (D3-8c).
;  4. Else L = 0 (the entity acts) and HOLD_GUARD clears ("after the action":
;     nothing between here and its action can freeze / stun it).
; Invariant kept: a group bit / kind is set <=> its timer nibble != 0.
; Out: L = 1 held (skip the action), 0 act. IX kept.
; Clobbers: A, BC, DE, HL.   ~0.25k T (+ ~1.5k per line)
;------------------------------------------------------------------------------
ST_D_T1         EQU (ST_T1 - ST_FLAGS) & $FF   ; L offsets inside page $B3
ST_D_T2         EQU (ST_T2 - ST_FLAGS) & $FF
st_step:
                add  a, ST_FLAGS & $FF
                ld   l, a
                ld   h, ST_FLAGS >> 8          ; HL = STATUS (T1 / T2: same page)
                ; --- 1. POISON ---
                bit  STS_POISON_BIT, (hl)
                jr   z, .weak
                ld   a, l
                add  a, ST_D_T2
                ld   e, a
                ld   d, h                      ; DE = STMR2 (POISON: high nibble)
                ld   a, (de)
                sub  $10
                ld   (de), a
                and  $F0
                jr   nz, .pm
                res  STS_POISON_BIT, (hl)
                ld   bc, TX_ST_POISON_OFF << 8 ; (no monster line)
                call .msg
                jr   .hp                       ; 0 is a multiple of 3
.pm:            sub  $30                       ; (n << 4) mod (3 << 4) == 0 ?
                jr   z, .hp
                jr   nc, .pm
                jr   .weak
.hp:            ld   a, (ix+E_HP)
                cp   2
                jr   c, .weak                  ; HP 1: never below (§6.4)
                dec  (ix+E_HP)
                ld   a, (hl)
                and  STS_HOLD
                cp   HOLD_ASLEEP
                jr   nz, .weak                 ; HP lost: a sleeper wakes
                call .hclr
                ld   bc, (TX_ST_WAKE << 8) | MSG_M_WAKE
                call .msg
                ; --- 2. WEAK (STMR2 low nibble), MIND (STMR1 low nibble) ---
.weak:          bit  STS_WEAK_BIT, (hl)
                jr   z, .mind
                ld   a, l
                add  a, ST_D_T2
                ld   e, a
                ld   d, h
                ld   a, (de)
                dec  a
                ld   (de), a
                and  $0F
                jr   nz, .mind
                res  STS_WEAK_BIT, (hl)
                ld   bc, TX_ST_STRONGER << 8
                call .msg
.mind:          ld   a, (hl)
                and  STS_MIND
                jr   z, .hold
                ld   c, a                      ; C = the MIND kind
                ld   a, l
                add  a, ST_D_T1
                ld   e, a
                ld   d, h
                ld   a, (de)
                dec  a
                ld   (de), a
                and  $0F
                jr   nz, .hold
                ld   a, (hl)
                and  ~STS_MIND & $FF
                ld   (hl), a
                ld   a, c
                cp   MIND_FEAR
                ld   bc, TX_ST_NERVE << 8
                jr   z, .mm
                ld   b, TX_ST_CLEAR
.mm:            call .msg
                ; --- 3. HOLD ---
.hold:          ld   a, (hl)
                and  STS_HOLD
                jr   z, .act
                ld   c, a                      ; C = the HOLD kind
                ld   a, l
                add  a, ST_D_T1
                ld   e, a
                ld   d, h
                ld   a, (de)
                sub  $10
                ld   (de), a
                and  $F0
                jr   nz, .held
                ld   a, (hl)
                and  ~STS_HOLD & $FF
                ld   (hl), a
                ld   a, c
                cp   HOLD_ASLEEP
                ld   bc, (TX_ST_WAKE << 8) | MSG_M_WAKE
                jr   z, .hm
                set  STS_GUARD_BIT, (hl)       ; HOLD_GUARD (D3-8c): one action before the
                                               ; next freeze / stun
                ld   bc, TX_ST_MOVE << 8       ; frozen / stunned: the tint drops
.hm:            call .msg
.held:          ld   l, 1
                ret
                ; --- 4. act ---
.act:           res  STS_GUARD_BIT, (hl)
                ld   l, 0
                ret
; .hclr — HOLD kind and timer of HL's slot to 0.  Clobbers: A, DE
.hclr:          ld   a, (hl)
                and  ~STS_HOLD & $FF
                ld   (hl), a
                ld   a, l
                add  a, ST_D_T1
                ld   e, a
                ld   d, h
                ld   a, (de)
                and  $0F
                ld   (de), a
                ret
; .msg — st_msg with HL kept.
.msg:           push hl
                call st_msg
                pop  hl
                ret
                ASSERT (ST_FLAGS >> 8) == (ST_T2 >> 8) && (ST_FLAGS & $FF) + ST_SLOTS <= 256

;------------------------------------------------------------------------------
; st_msg — IX = entity: the hero gets line B (TX_*), a monster "THE " + name +
; suffix C (MSG_M_*; 0 = no monster line). deal_hit's dh_msg, bank-7 copy.
; Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
st_msg:
                bit  EF_PLAYER_BIT, (ix+E_FLAGS)
                ld   a, b
                jp   nz, msg_push
                ld   a, c
                or   a
                ret  z
                ld   b, a
                ld   c, (ix+E_KIND)
                jp   impact_line

;------------------------------------------------------------------------------
; mon_status — far7 from resolve_monsters (bank 3; STATUS != 0): IX = monster,
; A = slot. The step (st_step); held -> L = 1. Then, on a turn it acts (an
; "acts every 2" monster rests on odd TURN_COUNTER; ai_monster's rule):
;  FEAR: a step away from the hero (walkers and flyers, x only); cornered (the
;    step illegal) it melees if the hero is in reach (attack_if_reach), else
;    waits. L = 1.
;  CONFUSED: 1 in 2 the action is a step in a random direction (walkers
;    dx +-1; flyers dx, dy in -1..1, dy kept in the storey band by
;    clamp_band); illegal -> wait (try_step: walkers never onto the pit col).
;    L = 1; else L = 0 (ai_monster acts). A confused monster never shoots
;    (no shooter before 3F: ai_monster's ranged rules must test it then).
; Either is skipped (L = 0: ai_monster, whose yield rule runs first) while
; the monster blocks the hero's climb (cork_check: the hero mid-ladder, or a
; climb blocked this turn) — a feared / confused body can't cork a ladder end.
; Out: L = 1 the action is spent, 0 = run ai_monster. IX kept.
; Clobbers: all but IX, IY.   ~0.4k T + the step / try_step
;------------------------------------------------------------------------------
mon_status:
                ld   (ACT_SLOT), a             ; try_step's box_free skips this body
                call st_step
                ld   a, l
                or   a
                ret  nz                        ; held: L = 1
                ld   a, (ACT_SLOT)
                add  a, ST_FLAGS & $FF
                ld   l, a
                ld   h, ST_FLAGS >> 8
                ld   a, (hl)
                and  STS_MIND
                ld   l, 0
                ret  z                         ; no MIND effect: ai_monster
                push af
                call get_box                   ; review: the §6.4 yield first — a feared /
                call cork_check                ; confused body on the hero's climb path
                pop  bc                        ; runs ai_monster's yield (bank 2; keeps BC,
                ld   l, 0                      ; DE; pop / ld keep CF)
                ret  c
                ld   c, b                      ; C = the MIND kind
                KFIELD KT_PERIOD               ; acts every 2: rests on odd turns
                cp   2
                jr   nz, .on
                ld   a, (TURN_COUNTER)
                rrca
                ld   l, 0
                ret  c                         ; (ai_monster rests too)
.on:            ld   a, c
                cp   MIND_FEAR
                jr   z, .fear
                ld   c, 2                      ; CONFUSED: 1 in 2 (a 0 roll)
                call rng_mod
                or   a
                ld   l, 0
                ret  nz                        ; not this time: ai_monster
                jr   .conf
.fear:          ld   d, 1                      ; away from the hero (x only)
                ld   a, (P_ENTITIES + E_X)
                cp   (ix+E_X)
                jr   c, .fs
                jr   nz, .fl
                bit  EF_LEFT_BIT, (ix+E_FLAGS) ; same x: away = its back
                jr   nz, .fs
.fl:            ld   d, $FF
.fs:            ld   e, 0
                call try_step_face
                jr   c, .spent
                ld   hl, attack_if_reach       ; cornered: melee if in reach (bank 3;
                call far3                      ; cache_player is the turn's)
.spent:         ld   l, 1
                ret
.conf:          ld   c, 2
                call rng_mod
                add  a, a
                dec  a                         ; dx -1 / +1
                ld   d, a
                ld   e, 0
                KFIELD KT_FLAGS
                and  KF_FLYER
                jr   z, .cstep
                ld   c, 3                      ; flyer: dx, dy in -1..1
                call rng_mod
                dec  a
                ld   d, a
                ld   c, 3
                push de
                call rng_mod
                pop  de
                dec  a
                ld   e, a
                push de
                call storey_ref
                ld   (TMP4), a                 ; clamp_band's storey
                pop  de
                ld   hl, clamp_band            ; bank 3: E kept in the band (0 = out);
                call far3                      ; far3 passes DE both ways
                ld   a, d
                or   e
                jr   z, .spent                 ; (0, 0): a wait
.cstep:         call try_step_face
                jr   .spent

;==============================================================================
; The hero (game.md §6.4 CONFUSED / FEAR rows, §2.3)
;==============================================================================

;------------------------------------------------------------------------------
; conf_roll — IX = hero. CF = 1: the CONFUSED hero's action is reversed this
; time (1 in 3, one rng_mod draw; no draw unless CONFUSED and off a ladder:
; mid-ladder never rolls — a side step / jump / facing action is refused
; there anyway, not a reversed action). Keeps BC, DE.  Clobbers: A, HL
;------------------------------------------------------------------------------
conf_roll:
                ld   a, (ST_FLAGS)
                and  STS_MIND
                cp   MIND_CONFUSED
                jr   nz, .no
                call on_ladder                 ; Z = mid-ladder (A, HL)
                jr   z, .no
                push bc
                ld   c, 3
                call rng_mod
                pop  bc
                or   a
                ret  nz                        ; CF = 0
                scf
                ret
.no:            or   a
                ret

; fear_chk — Z = the hero is FEARful (no melee-reach action).  Clobbers: A
fear_chk:
                ld   a, (ST_FLAGS)
                and  STS_MIND
                cp   MIND_FEAR
                ret

;------------------------------------------------------------------------------
; h_walk — tpt_intent's walk / bump along the facing (IX = hero, D = dx):
; CONFUSED and the roll -> turn around (face -dx), then try_horizontal the
; other way; illegal -> h_stumble (the turn is spent anyway, §2.3). Mid-ladder
; never rolls (conf_roll; the side step is illegal there, not an action).
; Out: CF = 1 turn used.  Clobbers: as try_horizontal.
;------------------------------------------------------------------------------
h_walk:
                call conf_roll
                jp   nc, try_horizontal
                ld   a, d
                neg
                ld   d, a
                call face_a                    ; (A, flags)
                call try_horizontal
                ret  c
                ; fall through
; h_stumble — "YOU STUMBLE": a reversed action that turned out illegal; CF = 1
; (the turn is spent).  Clobbers: A, BC, DE, HL
h_stumble:
                ld   a, TX_ST_STUMBLE
                call msg_push
                scf
                ret

;------------------------------------------------------------------------------
; h_jump — tpt_intent's jump, A = the E / W bits (try_jump's input), IX =
; hero. WEAK: no jump (game.md §7 / §6.4: illegal, no turn, no line —
; there is no string yet). CONFUSED and the roll: the other side (facing it
; first), illegal -> h_stumble.  Out: CF = 1 turn used.
;------------------------------------------------------------------------------
h_jump:
                ld   e, a
                ld   a, (ST_FLAGS)
                and  STS_WEAK
                ret  nz                        ; (and: CF = 0)
                call conf_roll
                ld   a, e
                jp   nc, try_jump
                xor  (1 << DIR_E_BIT) | (1 << DIR_W_BIT)
                ld   e, a
                and  1 << DIR_E_BIT
                ld   a, 1
                jr   nz, .f
                ld   a, $FF
.f:             call face_a
                ld   a, e
                call try_jump
                ret  c
                jr   h_stumble
