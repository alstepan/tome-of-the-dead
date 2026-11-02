;==============================================================================
; anim.asm — per-entity animation state machine (prototype §7) and the
; per-tick dirty-sprite renderer (§4.2/§4.3/§5.5).
;
; Per tick: anim_tick advances every live entity of CUR_ROOM (REST idle loop /
; MOVE tween 4 px + motion cycle / SEQ one-shot with IMPACT / HOLD) and writes
; the desired frame into R_VIS/R_FID (SLOTREC). render then diffs desired vs drawn:
;   erase changed sprites (tile-map restore = bitmap + attr, §4.3), repair
;   overlapping sprites (FORCE re-blit, cascading), draw in slot order with the
;   player last, stamp exact-footprint attrs, tick timers.
;==============================================================================

; KFIELD variant that preserves HL.
    MACRO KFIELD_KEEPHL off
                push hl
                KFIELD off
                pop  hl
    ENDM

;==============================================================================
; anim_tick — Clobbers: all but IY.  (B6: ASSERT P_MAX_ENT = 16, L = slot*16 wraps.)
;==============================================================================
                ASSERT P_MAX_ENT == 16
                ASSERT P_ENT_STRIDE == 32
anim_tick:
                xor  a
                ld   (RLIST_N), a
                ld   ix, P_ENTITIES
                ld   de, P_ENT_STRIDE           ; B6: IX walks by 32, L (record) by 16
                ld   l, a
                ld   h, SLOTREC >> 8
.lp:            ld   (hl), 0                   ; R_VIS default: hidden
                ld   a, (ix+E_FLAGS)
                or   a
                jr   nz, .full
                bit  0, (ix+E_DVIS)
                jr   nz, .full                 ; empty but still drawn: erase via list
                add  ix, de                    ; empty slot: nothing more to do
                ld   a, l
                add  a, 16
                ld   l, a
                jr   nc, .lp                   ; carry = slot 16 reached
.done:          ld   a, (MSG_Q)
                or   a
                ret  z
                dec  a
                call ent_ix
                call show_impact_msg           ; B3B-13: lowram (IX = attacker)
                xor  a
                ld   (MSG_Q), a
                ret

.full:          ld   c, a                      ; C = E_FLAGS (A is the slot below)
                ld   a, l                      ; ANIM_SLOT only stored when a callee
                rrca                           ; may read it (non-empty / drawn)
                rrca
                rrca
                rrca
                ld   (ANIM_SLOT), a
                ld   a, c
                and  EF_ACTIVE | EF_PENDING
                cp   EF_ACTIVE
                jr   nz, .next
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .next
                push de                        ; (anim_entity clobbers DE; IX is kept)
                call anim_entity               ; A = fid, B = visible
                pop  de
                ld   c, a
                ld   a, (ANIM_SLOT)
                rlca
                rlca
                rlca
                rlca
                ld   l, a
                ld   h, SLOTREC >> 8
                ld   (hl), b                   ; R_VIS
                inc  l
                ld   (hl), c                   ; R_FID
                ld   a, b
                or   a
                jr   nz, .add                  ; visible -> render list
.next:          bit  0, (ix+E_DVIS)
                jr   z, .skip                  ; not drawn either -> nothing to do
.add:           ld   a, (RLIST_N)
                ld   l, a
                inc  a
                ld   (RLIST_N), a
                ld   h, RLIST >> 8
                ld   a, l
                add  a, RLIST & $FF
                ld   l, a
                ld   a, (ANIM_SLOT)
                ld   (hl), a
.skip:          ld   a, (ANIM_SLOT)
                inc  a
                and  P_MAX_ENT - 1             ; wraps to 0 after the last slot
                add  ix, de                    ; (keeps Z)
                jp   z, .done
                rlca
                rlca
                rlca
                rlca
                ld   l, a
                ld   h, SLOTREC >> 8
                jp   .lp

;------------------------------------------------------------------------------
; rl_first / rl_next — iterate RLIST (slots visible or still drawn this tick,
; ascending). rl_next: A = ANIM_SLOT = next slot (Z = slot 0), HL = its
; SLOTREC record (R_VIS), CF = 1 when exhausted.
; Clobbers: A, HL.  (The render loops touch ~5 slots instead of 16.)
;------------------------------------------------------------------------------
rl_first:       xor  a
                ld   (RL_IDX), a
                ret
rl_next:        ld   a, (RL_IDX)
                ld   hl, RLIST_N
                cp   (hl)
                ccf
                ret  c
                ld   l, a
                inc  a
                ld   (RL_IDX), a
                ld   a, l
                add  a, RLIST & $FF
                ld   l, a                      ; (RLIST, RLIST_N: one page)
                ld   a, (hl)
                ld   (ANIM_SLOT), a
                rlca
                rlca
                rlca
                rlca
                ld   l, a                      ; A7b: HL = the slot's record
                ld   h, SLOTREC >> 8
                ld   a, (ANIM_SLOT)
                or   a                         ; CF = 0; Z = slot 0
                ret
                ASSERT (RLIST >> 8) == (RLIST_N >> 8)

;------------------------------------------------------------------------------
; anim_entity — IX = live entity. Out: A = fid, B = 1 visible / 0 hidden.
;------------------------------------------------------------------------------
anim_entity:
                ld   a, (ix+E_MODE)
                cp   M_MOVE
                jp   z, .move
                cp   M_SEQ
                jp   z, .seq
                cp   M_FALL
                jr   nc, .fj                   ; B3B-5: M_FALL / M_JUMP
                cp   M_HOLD
                jr   nz, .rest
                ld   a, (ix+E_WPH)             ; HOLD: the final death frame
                ld   b, 1
                ret
.fj:            ; B3B-5 FALL / JUMP. C = 8x (target px), D = 8y (target py)
                ld   b, a
                ld   a, (ix+E_X)
                add  a, a
                add  a, a
                add  a, a
                ld   c, a
                ld   a, (ix+E_Y)
                add  a, a
                add  a, a
                add  a, a
                ld   d, a
                ld   a, b
                cp   M_JUMP
                jp   z, .jump                  ; (out of line: keeps .fj's jr in range)
                ; FALL (game.md §2.5): the walk step first (4 px/tick, walk
                ; cycle), then FALL_STEP px/tick straight down (F9: px = 8x)
                ; in the CLIMB1 / WALK1 pose; landing = M_REST (hero_fall's
                ; HURT / DEATH reaction, E_REACTAT 0, starts on the next tick)
                ld   a, (ix+E_PX)
                cp   c
                jr   nz, .fpx
                ld   a, (ix+E_PY)
                add  a, FALL_STEP
                ld   (ix+E_PY), a
                cp   d
                jr   nz, .crest
.land:          ld   (ix+E_MODE), M_REST
                bit  EF_PLAYER_BIT, (ix+E_FLAGS)   ; SND-5: the hero lands (fall)
                jr   z, .crest
                ld   a, SFX_LAND
                call sfx_req
                jr   .crest
.fpx:           ld   b, c                      ; FALL: px 4 px toward 8x, walk cycle
                ld   a, (ix+E_PX)
                call tween
                ld   (ix+E_PX), a
                ld   c, KS_MOVE
                jp   .mv
.rest:
                ld   a, (ix+E_REACT)
                or   a
                jr   z, .idle
                ld   a, (TURN_PHASE)
                or   a
                jr   z, .idle
                ld   a, (TURN_TICK)
                cp   (ix+E_REACTAT)
                jr   c, .idle
                ; start the pending reaction (HURT / BLOCK / DEATH; T7 DODGE /
                ; 3F-T13bc PARRY (the Death Knight): no sequence, a flash)
                ld   a, (ix+E_REACT)
                cp   RC_DODGE
                jr   nc, .dodge                ; RC_DODGE / RC_PARRY (the largest codes)
                ld   c, KS_HURT
                cp   RC_HURT
                jr   z, .rs
                ld   c, KS_BLOCK
                cp   RC_BLOCK
                jr   z, .rs
                ld   c, KS_DEATH
                call vb_fall                   ; VBAT-ART (low RAM, lowram.asm): a bat form drops to its floor; A = RC_DEATH
.rs:            or   $80                       ; running
                ld   (ix+E_REACT), a
                call kind_seq_ptr              ; (keeps BC, 3F-T2)
                ld   b, 0
                add  hl, bc
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                call start_seq
                jp   .seq
.dodge:         ld   (ix+E_REACT), RC_NONE     ; (no flag change: Z = RC_DODGE still)
                ld   bc, ATTR_MISS << 8 | MISS_FLASH
                jr   z, .dfl
                ld   bc, ATTR_PARRY << 8 | PARRY_FLASH   ; 3F-T13bc: +6 B vs the dodge-only path
.dfl:           ld   (ix+E_FLT), c
                ld   (ix+E_FLA), b
.idle:
                call on_ladder
                jr   nz, .cyc
.crest:         call kind_seq_ptr              ; resting mid-ladder: CLIMB1
                ld   de, KS_CLIMBREST
                add  hl, de
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                ld   a, (hl)
                ld   b, 1
                ret
.cyc:           call kind_seq_ptr
                ld   a, (hl)                   ; KS_IDLE
                inc  hl
                ld   h, (hl)
                ld   l, a
                call idle_phase
                call cycle_frame
                ld   b, 1
                ret

.move:          ; vertical move of a non-flyer = climbing
                ld   a, (ix+E_Y)
                add  a, a
                add  a, a
                add  a, a
                cp   (ix+E_PY)
                ld   c, KS_MOVE
                jr   z, .horiz
                KFIELD KT_FLAGS
                and  KF_FLYER
                ld   c, KS_CLIMB
                jr   z, .horiz
                ld   c, KS_MOVE
.horiz:         ; tween px / py 4 px toward x*8 / y*8
                ld   a, (ix+E_X)
                add  a, a
                add  a, a
                add  a, a
                ld   b, a
                ld   a, (ix+E_PX)
                call tween
                ld   (ix+E_PX), a
                ld   a, (ix+E_Y)
                add  a, a
                add  a, a
                add  a, a
                ld   b, a
                ld   a, (ix+E_PY)
                call tween
                ld   (ix+E_PY), a
                ; arrived?
                ld   a, (ix+E_X)
                add  a, a
                add  a, a
                add  a, a
                cp   (ix+E_PX)
                jr   nz, .mv
                ld   a, (ix+E_Y)
                add  a, a
                add  a, a
                add  a, a
                cp   (ix+E_PY)
                jr   nz, .mv
                ld   (ix+E_MODE), M_REST
.mv:            ; frame: flyers use the idle loop phase; others the walk phase
                call kind_seq_ptr              ; (keeps BC, 3F-T2)
                ld   b, 0
                add  hl, bc
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                KFIELD_KEEPHL KT_FLAGS
                and  KF_FLYER
                jr   z, .walkph
                call idle_phase
                jr   .cf
.walkph:        ld   a, (ix+E_WPH)
                inc  (ix+E_WPH)
    IF PHASE_SHIFT
                ; Phase lock (KS_MOVE only; C = KS_MOVE 2 / KS_CLIMB 4): the
                ; drawn phase's bit 0 = NOT (px & 4), so WALK1/3 (even) sit at
                ; px & 4 = 4 and WALK2/4 at 0 BY CONSTRUCTION (one stored shift,
                ; FF_PH4 / STA). E_WPH and px both step once per tween tick, so
                ; it is a no-op while the parities agree; a disagreement bumps
                ; PHASE_TRAP (= a frame the unlocked engine would have drawn
                ; at the ungenerated shift). HL = the cycle (kept). 26 B;
                ; per walking body per tick 85-86 T while the parities agree,
                ; +37 T on a disagreement (the trap); a climb tick 15 T.
                ; Clobbers D, E.
                bit  1, c
                jr   z, .cf                    ; climb cycle: unlocked
                ld   d, a
                and  $FE
                bit  2, (ix+E_PX)
                jr   nz, .ph4                  ; px & 4 = 4: even phase
                inc  a
.ph4:           ld   e, a
                xor  d
                rrca                           ; CF = the parities disagreed
                ld   a, e
                jr   nc, .cf
                push hl
                ld   hl, PHASE_TRAP
                inc  (hl)
                pop  hl
      IF PHASE_SHIFT == 2
                ld   a, d                      ; diagnostic: the unlocked phase (a
      ENDIF                                    ; violation then shows as BLIT_MISS)
    ENDIF
.cf:            call cycle_frame
                ld   b, 1
                ret

.seq:           ld   l, (ix+E_SEQL)
                ld   h, (ix+E_SEQH)
                ld   a, (ix+E_TMR)
                or   a
                jr   nz, .run
                inc  hl
                ld   a, (hl)                   ; entry ticks
                ld   (ix+E_TMR), a
                inc  hl
                ld   a, (hl)
                dec  hl
                dec  hl
                and  SF_IMPACT
                jr   z, .run
                push hl
                call do_impact
                pop  hl
.run:           ld   c, (hl)                   ; fid
                inc  hl
                inc  hl
                ld   a, (hl)                   ; flags
                and  SF_HIDE
                ld   b, 1
                jr   z, .vis
                ld   b, 0
.vis:           inc  hl                        ; -> next entry
                dec  (ix+E_TMR)
                jr   nz, .out
                ld   (ix+E_SEQL), l
                ld   (ix+E_SEQH), h
                ld   a, (hl)
                cp   SEQ_END
                jr   nz, .out
                ; sequence finished
                ld   (ix+E_MODE), M_REST
                ld   a, (ix+E_REACT)
                bit  7, a
                jr   z, .out
                and  $7F
                ld   (ix+E_REACT), RC_NONE
                cp   RC_DEATH
                jr   nz, .out
                ; death finished: hero holds the pose; a monster's slot is freed
                ld   (ix+E_WPH), c
                bit  1, (ix+E_FLAGS)           ; EF_PLAYER
                jr   z, .free
                ld   (ix+E_MODE), M_HOLD
                jr   .out
.free:          ld   (ix+E_FLAGS), 0           ; slot freed; renderer erases it
.out:           ld   a, c
                ret
.jump:          ; JUMP (game.md §2.4; J1 2026-10-06). Arc tick t = E_TMR, n =
                ; JUMP_ARC airborne ticks, N = 12 (D 6) / 14 (D 7). t 0: JUMP1,
                ; aligned (the crouch at take-off); t 1..n: JUMP2 every airborne
                ; tick (ANIM-IMPORT2 J-a, user 2026-10-30: one leap pose, a MOT
                ; frame drawn at both px parities; the JUMP-ALT parity pick is
                ; gone), px += 4, py = 8y - 4 min(t, N-t, 4) (= the §2.4 dy lists for
                ; both D; a cut-short arc stops at n < N); t n+1: JUMP1, landed
                ; (M_REST) or, JA_FALL (the hero already sits on storey 1:
                ; base py - 72), py snapped to storey 0 and M_FALL drops it.
                ; Frame = hero_jump[E_KIND * 2 + (airborne)] (only the hero jumps).
                ; ~260 T on an airborne tick (the old py table: ~220).
                ld   a, (ix+E_TMR)
                inc  (ix+E_TMR)
                ld   e, 0                      ; JUMP1 (ld keeps the flags)
                or   a
                jr   z, .jfid
                ld   b, a                      ; t
                ld   a, (JUMP_ARC)
                ld   l, a
                and  JA_N
                cp   b
                jr   c, .jland                 ; t > n
                ld   a, 2 * JUMP_COLS
                bit  JA_D7_BIT, l
                jr   z, .jn
                ld   a, 2 * JUMP_COLS7
.jn:            sub  b                         ; N - t (t <= n <= N)
                cp   b
                jr   c, .jm
                ld   a, b                      ; min(t, N - t)
.jm:            cp   JUMP_APEX
                jr   c, .jr
                ld   a, JUMP_APEX           ; .. capped at 4 (16 px)
.jr:            add  a, a
                add  a, a
                neg
                add  a, d                      ; py = 8y - 4m
                bit  JA_FALL_BIT, l
                jr   z, .jp
                sub  STOREY_ROWS * 8           ; falling: the arc is a storey up
.jp:            ld   (ix+E_PY), a
                ld   b, c
                ld   a, (ix+E_PX)
                call tween
                ld   (ix+E_PX), a
                ld   e, 1                      ; JUMP2 (J-a: every airborne tick)
                jr   .jfid
.jland:         ld   (ix+E_MODE), M_REST       ; landed, E = 0 (JUMP1)
                bit  JA_FALL_BIT, l
                jr   nz, .jfall
                ld   a, SFX_LAND               ; SND-5 (only the hero jumps; F only)
                call sfx_req
                jr   .jfid
.jfall:
                ld   (ix+E_MODE), M_FALL       ; F9 snap: py = the storey-0 top
                ld   a, d                      ; (px = 8 x_f already: n tween
                sub  STOREY_ROWS * 8           ; steps of 4 px), then the drop
                ld   (ix+E_PY), a
.jfid:          ld   a, (ix+E_KIND)
                add  a, a
                add  a, e
                ld   e, a
                ld   d, 0
                ld   hl, hero_jump
                add  hl, de
                ld   a, (hl)
                ld   b, 1
                ret
                ASSERT JUMP_APEX * TWEEN_STEP == JUMP_RISE * 8   ; the apex = the swept-box rise

; tween — A = cur, B = target: step 4 toward.  Clobbers: A
tween:
                cp   b
                ret  z
                jr   c, .up
                sub  TWEEN_STEP
                ret
.up:            add  a, TWEEN_STEP
                ret

; idle_phase — A = (ANIM_FREEZE or the slot HOLD (FROZEN / ASLEEP / STUNNED)
; ? 0 : TICK_COUNTER + slot*5). D3-8d V1 (game.md §6.4.1): a held body's idle
; loop stops on its first frame (bats stop flapping, the hero stops breathing)
; and resumes when the HOLD clears; +32 T per call, and it saves the idle-frame
; redraws.  Clobbers: A, DE (both callers run cycle_frame next: D is free)
idle_phase:
                ld   a, (ANIM_FREEZE)
                or   a
                jr   nz, .z
                ld   a, (ANIM_SLOT)
                add  a, ST_FLAGS & $FF
                ld   e, a
                ld   d, ST_FLAGS >> 8
                ld   a, (de)
                and  STS_HOLD
                jr   nz, .z
                ld   a, e
                sub  ST_FLAGS & $FF            ; the slot again
                ld   e, a
                add  a, a
                add  a, a
                add  a, e
                ld   e, a
                ld   a, (TICK_COUNTER)
                add  a, e
                ret
.z:             xor  a
                ret

; cycle_frame — HL = cycle (DB total, (fid,ticks)*), A = phase -> A = fid.
; Clobbers: A, BC, D, HL
cycle_frame:
                ld   c, (hl)                   ; total ticks
                inc  hl
                ld   d, a                      ; phase mod total (8-bit restoring div)
                xor  a
                ld   b, 8
.dv:            sla  d
                rla
                cp   c
                jr   c, .dn
                sub  c
.dn:            djnz .dv
.walk:          inc  hl
                sub  (hl)                      ; - ticks of this entry
                dec  hl
                jr   c, .hit
                inc  hl
                inc  hl
                jr   .walk
.hit:           ld   a, (hl)
                ret

;------------------------------------------------------------------------------
; do_impact — IX = attacker reaching its IMPACT entry (§6.5): target hit flash,
; HUD message.  Clobbers: all but IX.
;------------------------------------------------------------------------------
do_impact:
                ld   a, (ix+E_HIT)             ; LOG-DMG: the HP lost (1..127: flash), 0 or a
                dec  a                         ; ranged shot's $80 | L (bit 7: shot_tick flashes
                cp   $7F                       ; with the bolt): no flash. +2 B
                jr   nc, .nohit
                push ix
                ld   a, (ix+E_TGT)
                call ent_ix
                ld   (ix+E_FLT), FLASH_TICKS
                ld   (ix+E_FLA), ATTR_HIT
                pop  ix
.nohit:         ld   a, (MSG_Q)                ; LOG-FIX P2b: a second impact in the same tick
                or   a                         ; used to overwrite the first one's line (two
                jr   z, .q                     ; Goblins flanking the hero: one line): show the
                ld   a, (LOG_QN)               ; queued one now (~1.4k T), queue this one - only
                cp   1                         ; with the ring EMPTY (the panel drains one line a
                jr   nc, .q                    ; first-frame tick: a looser test overflowed a
                ld   a, (MSG_Q)                ; 4-monster faint turn); else last-wins as before
                push ix
                push de                        ; (anim_entity's DE / HL survive; the ring has room:
                dec  a                         ; ROOM_CAP lines)
                call ent_ix                    ; (A, E)
                call show_impact_msg           ; (A, BC, DE, HL; IX kept)
                pop  de
                pop  ix
.q:             call ix_slot                   ; queue the HUD line: printed once
                inc  a                         ; at the end of anim_tick (the last
                ld   (MSG_Q), a                ; impact of a tick is the one queued)
                ret

;------------------------------------------------------------------------------
; st_tint — render (D3-8): A = STATUS & STS_TINTED (!= 0), IX = the entity
; -> A = its tint (game.md §6.4: the HOLD kind's, else CONFUSED's); equal to
; the kind's KT_ATTR -> the BRIGHT twin (XOR $40). Keeps B, C, HL.
; Clobbers: A, DE.   ~0.15k T
;------------------------------------------------------------------------------
st_tint:
                and  STS_HOLD                  ; 0 = CONFUSED only
                add  a, st_tint_tab & $FF
                ld   e, a
                ld   d, st_tint_tab >> 8
                ld   a, (de)
                ld   d, a                      ; D = the tint
                push hl
                KFIELD KT_ATTR
                pop  hl
                cp   d
                ld   a, d
                ret  nz
                xor  $40
                ret
st_tint_tab:    DB   TINT_CONFUSED, TINT_FROZEN, TINT_ASLEEP, TINT_STUNNED
                ASSERT (st_tint_tab >> 8) == ((st_tint_tab + 3) >> 8)
                ASSERT HOLD_FROZEN == 1 && HOLD_ASLEEP == 2 && HOLD_STUNNED == 3

;------------------------------------------------------------------------------
; turn_done — CF = 1 when every live entity of CUR_ROOM rests (or holds) with no
; reaction pending/running, no FX track is live or drawn (D3-5), no split
; ability turn pending (D3-7: TURN_PEND, the fire or the deferred monster
; phase), and >= 2 ticks have elapsed.  Clobbers: A, B, DE, IX
;------------------------------------------------------------------------------
turn_done:
                ld   a, (TURN_TICK)
                cp   2
                ccf
                ret  nc
                ld   a, (FX_BUSY)              ; D3-5: FX tracks live or still drawn
                or   a
                ret  nz                        ; CF = 0 (or)
                ld   a, (TURN_PEND)            ; D3-7
                or   a
                ret  nz                        ; CF = 0 (or)
                ld   ix, P_ENTITIES
                ld   b, P_MAX_ENT
.l:             ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_PENDING
                cp   EF_ACTIVE
                jr   nz, .n
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .n
                ld   a, (ix+E_MODE)            ; busy unless REST / HOLD (B3B-5:
                cp   M_HOLD                    ; MOVE, SEQ, FALL, JUMP)
                jr   z, .rs
                or   a
                ret  nz                        ; CF = 0 (or)
.rs:            ld   a, (ix+E_REACT)
                or   a
                ret  nz                        ; CF = 0 (or)
.n:             ld   de, P_ENT_STRIDE
                add  ix, de
                djnz .l
                scf
                ret

;==============================================================================
; RENDER
; A7b: per-slot state is one 16-B record (SLOTREC + slot*16, fields R_*), so a
; slot's fields are reached by inc l / RFIELD instead of one 31-T array lookup
; each; classify + erase + damage run in ONE pass over RLIST (was three), and
; a moving sprite's old and new footprints become one damage rect when their
; union is a rectangle (same row band or same col band, overlapping or
; touching): fewer rects to mark for present and to test in the repair pass.
;==============================================================================
; RFIELD f — L = this record's field f (H = SLOTREC page).  Clobbers: A  (22 T)
    MACRO RFIELD f
                ld   a, l
                and  $F0
                or   f
                ld   l, a
    ENDM
                ASSERT SLOTREC_STRIDE == 16 && (SLOTREC & $FF) == 0
                ASSERT P_MAX_ENT * SLOTREC_STRIDE == 256 && R_LOG < 16
                ASSERT E_DFPX == E_DFID + 1 && E_DFPY == E_DFID + 2 && E_DCOL == E_DFID + 3
                ASSERT E_DROW == E_DFID + 4 && E_DCOLS == E_DFID + 5 && E_DROWS == E_DFID + 6
                ASSERT R_FPX == R_FID + 1 && R_FPY == R_FID + 2 && R_COL == R_FID + 3
                ASSERT R_ROW == R_FID + 4 && R_COLS == R_FID + 5 && R_ROWS == R_FID + 6
                ASSERT R_LEFT == R_ROWS + 1 && R_ATTR == R_LEFT + 1 && R_DATTR == R_ATTR + 1
                ASSERT R_DIRTY == R_DATTR + 1 && R_LOG == R_DIRTY + 1
                ASSERT R_TINT == R_ATTR | 4 && (R_ATTR & 4) == 0 && RC_NONE == 0
                ASSERT DIRTY_ATTR == DIRTY_NONE + 1 && DIRTY_FULL == 2

render:
                xor  a
                ld   (DMG_COUNT), a
                ; ---------------- 1. queued restores (PEND_DMG) ------------------
                ld   a, (PEND_DMG_COUNT)
                or   a
                jr   z, .nopend
                ld   b, a
                ld   hl, PEND_DMG
.pd:            push bc
                ld   c, (hl)
                inc  hl
                ld   b, (hl)
                inc  hl
                ld   d, (hl)
                inc  hl
                ld   e, (hl)
                inc  hl
                push hl
                push bc
                push de
                call erase_rect
                pop  de
                pop  bc
                call dmg_add
                pop  hl
                pop  bc
                djnz .pd
                xor  a
                ld   (PEND_DMG_COUNT), a
.nopend:
                ; ---------------- 2. per slot: classify, erase, damage ----------
                call rl_first
.s:             call rl_next                   ; HL = record (R_VIS), A = slot
                jp   c, .sdone
                call ent_ix                    ; (keeps HL)
                ld   a, (hl)                   ; R_VIS
                or   a
                jp   z, .hidden
                ; desired frame geometry (§5.1): fpx = px + off, fpy = py + bh*8 - H
                inc  l                         ; R_FID
                ld   a, (hl)
                push hl
                FT_HL_A FT_COLS                ; MEM-FT: frame_tab in the FRT row (+6 T)
                ld   c, (hl)                   ; C = data cols
                inc  hl
                ld   b, (hl)                   ; B = H (FT_H)
                inc  hl                        ; FT_OFFR
                bit  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   z, .offr
                inc  hl                        ; FT_OFFL
.offr:          ld   a, (hl)
                add  a, (ix+E_PX)
                ld   e, a                      ; E = fpx (mod 256)
                ; T7 edge clamp: a frame wider than the body (the Knight's 40-px
                ; WHIRL / POWER_STRIKE / SLASH at col 0 or 29) would wrap below x 0
                ; or run past x 255 -> blit_clip, the sprite vanished (CLIP_TRAP).
                ; Clamp the frame into the screen instead, keeping its shift
                ; (fpx & 4): x 0 / 4, or 256 - W - shift (a shifted frame spans
                ; cols + 1). +30 T per drawn slot; the clamp itself ~70 T.
                ld   a, c
                add  a, a
                add  a, a
                add  a, a                      ; W = cols * 8 (<= 40)
                add  a, e
                jp   c, .edge                  ; fpx + W > 255 (or a wrap; jp: no spot
                                               ; for .edge within jr range of here)
.fpx:           KFIELD KT_BH
                add  a, a
                add  a, a
                add  a, a
                add  a, (ix+E_PY)
                sub  b
                ld   d, a                      ; D = fpy
                pop  hl                        ; R_FID
                inc  l
                ld   (hl), e                   ; R_FPX
                inc  l
                ld   (hl), d                   ; R_FPY
                ; exact footprint (§4.2): cols = W/8 (+1 if shifted),
                ; rows = (fpy&7 + H + 7) >> 3
                inc  l
                ld   a, e
                rrca
                rrca
                rrca
                and  $1F
                ld   (hl), a                   ; R_COL
                inc  l
                ld   a, d
                rrca
                rrca
                rrca
                and  $1F
                ld   (hl), a                   ; R_ROW
                inc  l
                ld   a, e
                and  4
                jr   z, .c0
                inc  c                         ; shifted: +1 spill col
.c0:            ld   (hl), c                   ; R_COLS
                inc  l
                ld   a, d
                and  7
                add  a, b
                add  a, 7
                rrca
                rrca
                rrca
                and  $1F
                ld   (hl), a                   ; R_ROWS
                inc  l
                ld   a, (ix+E_FLAGS)
                and  EF_LEFT
                ld   (hl), a                   ; R_LEFT
                ld   b, a                      ; B = desired facing
                inc  l
                ld   a, (ix+E_FLT)             ; attr: flash overrides the kind colour
                or   a
                ld   a, (ix+E_FLA)
                jr   nz, .fl
                ; D3-8e2 (game.md §6.5.1, visible output at impact): while a
                ; reaction is pending (E_REACT 1..$7F: struck, its impact tick
                ; not reached) the body keeps the attr it showed before the strike
                ; (R_TINT): a new FROZEN / CONFUSED tint appears at the impact, a
                ; killed body's tint (deal_hit clears its STATUS) stays until its
                ; DEATH starts. +13 B, ~45 T a drawn slot (~30 T while pending)
                ld   a, (ix+E_REACT)
                dec  a                         ; pending -> 0..$7E: P
                set  2, l                      ; R_TINT (SET / LD keep the flags)
                ld   a, (hl)
                jp   p, .ro
                ld   a, (ANIM_SLOT)            ; D3-8: HOLD / CONFUSED tint from the slot's
                add  a, ST_FLAGS & $FF         ; STATUS (game.md §6.4; +57 T a drawn slot
                ld   e, a                      ; without one). DE free here (fpx / fpy
                ld   d, ST_FLAGS >> 8          ; stored), B = the facing: kept
                ld   a, (de)
                and  STS_TINTED
                jr   z, .kat
                call st_tint                   ; (keeps B, HL)
                jr   .tsh
.kat:           ld   a, (ix+E_GOLD)            ; 3F-T8: a golden body glows (boss2.asm)
                or   a
                jp   nz, glow_kat
                KFIELD_KEEPHL KT_ATTR
.tsh:           ld   (hl), a                   ; R_TINT = shown now
.ro:            res  2, l                      ; back to R_ATTR
.fl:            ld   (hl), a                   ; R_ATTR
                inc  l
                ld   c, DIRTY_NONE
                cp   (hl)                      ; R_DATTR
                jr   z, .sa
                inc  c                         ; DIRTY_ATTR
.sa:            ; classify vs drawn: frame / facing / position change -> FULL
                bit  0, (ix+E_DVIS)
                jr   z, .full_log              ; not drawn
                RFIELD R_FID
                ld   a, (hl)
                cp   (ix+E_DFID)
                jr   nz, .full_log             ; frame change: ANIM_TRACE logs it
                ld   a, (ix+E_DVIS)
                and  EF_LEFT
                cp   b
                jr   nz, .full
                inc  l
                ld   a, (hl)
                cp   (ix+E_DFPX)
                jr   nz, .full
                inc  l
                ld   a, (hl)
                cp   (ix+E_DFPY)
                jr   nz, .full
                ld   a, l
                add  a, R_DIRTY - R_FPY
                ld   l, a
                ld   (hl), c                   ; R_DIRTY = NONE / ATTR
    IF ANIM_TRACE_ON
                inc  l
                ld   (hl), 0                   ; R_LOG
    ENDIF
                dec  c
                jp   nz, .s                    ; NONE: nothing to erase or add
                ld   a, (ix+E_GOLD)            ; 3F-T8: a golden body's attr-only repaint
                or   a                         ; (draw_slot -> stamp_slot: both screens),
                jp   nz, .s                    ; no damage rect
                RFIELD R_COL                   ; ATTR: re-stamped in place
                jp   .addn
.edge:          ld   d, a                      ; D = fpx + W - 256 (right edge: the overhang)
                ld   a, e
                and  4
                ld   l, a                      ; L = the shift (a STATIONARY frame with
                ld   a, (ix+E_PX)              ; ax 4 has only shift 4: keep it)
                rla                            ; CF = px >= 128: the right edge
                ld   a, l
                jr   nc, .ecl                  ; left: wrapped below x 0 -> x 0 / 4
                ld   a, e
                sub  d
                sub  l                         ; 256 - W - shift (D = 0, unshifted: exact fit)
.ecl:           ld   e, a
                jp   .fpx
    IF ANIM_TRACE_ON
.full_log:      RFIELD R_LOG
                ld   (hl), 1
                jr   .fullc
.full:          RFIELD R_LOG
                ld   (hl), 0
.fullc:         dec  l                         ; R_DIRTY
    ELSE                                       ; release: no R_LOG, one path (-13 B; -14 T,
                                               ; -26 T on a frame change)
.full_log:
.full:          RFIELD R_DIRTY
    ENDIF
                ld   (hl), DIRTY_FULL
                RFIELD R_COL
                bit  0, (ix+E_DVIS)
                jr   z, .addn                  ; not drawn: new footprint only
                push hl
                call .erase                    ; C,B,D,E = old footprint
                pop  hl
                ; old O (entity drawn block, still intact) + new N (record) ->
                ; one rect if O u N is a rectangle, else both
                ld   c, (hl)
                inc  l
                ld   b, (hl)
                inc  l
                ld   d, (hl)
                inc  l
                ld   e, (hl)                   ; C,B,D,E = N
                ld   a, b
                cp   (ix+E_DROW)
                jr   nz, .tryv
                ld   a, e
                cp   (ix+E_DROWS)
                jr   nz, .tryv
                ; same row band: merge if c1 <= c0 + w0 and c0 <= c1 + w1
                ld   a, (ix+E_DCOL)
                add  a, (ix+E_DCOLS)
                ld   l, a                      ; L = O end col (H unused now)
                cp   c
                jr   c, .two
                ld   a, c
                add  a, d                      ; A = N end col
                cp   (ix+E_DCOL)
                jr   c, .two
                cp   l
                jr   nc, .h1
                ld   a, l                      ; A = max end
.h1:            ld   l, a
                ld   a, (ix+E_DCOL)
                cp   c
                jr   nc, .h2
                ld   c, a                      ; C = min col
.h2:            ld   a, l
                sub  c
                ld   d, a                      ; D = bbox cols
                jr   .add1
.tryv:          ld   a, c                      ; same col band: merge if
                cp   (ix+E_DCOL)               ; r1 <= r0 + h0 and r0 <= r1 + h1
                jr   nz, .two
                ld   a, d
                cp   (ix+E_DCOLS)
                jr   nz, .two
                ld   a, (ix+E_DROW)
                add  a, (ix+E_DROWS)
                ld   l, a                      ; L = O end row
                cp   b
                jr   c, .two
                ld   a, b
                add  a, e                      ; A = N end row
                cp   (ix+E_DROW)
                jr   c, .two
                cp   l
                jr   nc, .v1
                ld   a, l
.v1:            ld   l, a
                ld   a, (ix+E_DROW)
                cp   b
                jr   nc, .v2
                ld   b, a                      ; B = min row
.v2:            ld   a, l
                sub  b
                ld   e, a                      ; E = bbox rows
                jr   .add1
.two:           push bc
                push de
                ld   c, (ix+E_DCOL)
                ld   b, (ix+E_DROW)
                ld   d, (ix+E_DCOLS)
                ld   e, (ix+E_DROWS)
                call dmg_add                   ; O
                pop  de
                pop  bc
                jr   .add1                     ; N
.addn:          ld   c, (hl)                   ; HL = R_COL: C,B,D,E = N
                inc  l
                ld   b, (hl)
                inc  l
                ld   d, (hl)
                inc  l
                ld   e, (hl)
.add1:          call dmg_add
                jp   .s
    IF ANIM_TRACE_ON
.hidden:        RFIELD R_LOG
                ld   (hl), 0
                dec  l                         ; R_DIRTY
    ELSE
.hidden:        RFIELD R_DIRTY
    ENDIF
                ld   (hl), DIRTY_NONE
                bit  0, (ix+E_DVIS)
                jp   z, .s                     ; neither visible nor drawn
                ld   (hl), DIRTY_FULL          ; was drawn, now hidden: erase
                call .erase
                jr   .add1                     ; O
                ; erase the drawn footprint (IX) -> C,B,D,E = it; not drawn now
.erase:         ld   c, (ix+E_DCOL)
                ld   b, (ix+E_DROW)
                ld   d, (ix+E_DCOLS)
                ld   e, (ix+E_DROWS)
                push bc
                push de
                call erase_rect
.probe_e2_ret:                                  ; flicker probe (no code)
                pop  de
                pop  bc
                ld   (ix+E_DVIS), 0
                ret
.sdone:
                ld   a, (FX_BUSY)              ; D3-5: changed FX erased here, so their
                or   a                         ; rects are presented and the bodies
                call nz, fx_erase              ; under them repaired (phase 3)
                ld   a, (DMG_COUNT)            ; A7: present needs only these rects:
                ld   (DMG_PRES_N), a           ; a forced re-blit (below) only rewrites
                                               ; cells outside them with identical
                                               ; bytes (same sprites, same slot order)

                ; ---------------- 3. overlap repair (cascade) -------------------
.force:         xor  a
                ld   (RENDER_PASS), a
                call rl_first
.f3:            call rl_next
                jr   c, .f3done
                ld   a, (hl)                   ; R_VIS
                or   a
                jr   z, .f3
                ld   a, l
                or   R_DIRTY
                ld   l, a
                ld   a, (hl)
                cp   DIRTY_FULL                ; NONE *and* ATTR get repaired: an
                jr   nc, .f3                   ; ATTR draw only stamps, so its
                                               ; pixels under a damage rect are lost
                push hl
                ld   a, l
                sub  R_DIRTY - R_COL
                ld   l, a
                ld   c, (hl)                   ; same as drawn (not dirty)
                inc  l
                ld   b, (hl)
                inc  l
                ld   d, (hl)
                inc  l
                ld   e, (hl)
                push bc
                push de
                call dmg_hit
                pop  de
                pop  bc
                pop  hl                        ; R_DIRTY
                jr   nc, .f3
                ld   (hl), DIRTY_FORCE
                call dmg_add
                ld   a, 1
                ld   (RENDER_PASS), a
                jr   .f3
.f3done:        ld   a, (RENDER_PASS)
                or   a
                jr   nz, .force

                ; ---------------- 4. draw: slots 1..15, then the player ---------
                call rl_first
.dr:            call rl_next
                jr   c, .drdone
                or   a
                call nz, draw_slot             ; slot 0 (the player) goes last
                jr   .dr
.drdone:        ld   a, (RLIST_N)
                or   a
                jr   z, .nopl
                ld   a, (RLIST)
                or   a
                jr   nz, .nopl
                ld   (ANIM_SLOT), a
                ld   hl, SLOTREC               ; slot 0's record
                call draw_slot
.nopl:
                ld   a, (FX_BUSY)              ; D3-5: FX drawn last, over every body
                or   a
                call nz, fx_draw

                ; ---------------- 5. timers (D3-0: the zap overlay is gone) ----
                call frozen                    ; C3-2b: ICON MODE holds the
                ret  z                         ; timers
                ld   hl, P_ENTITIES + E_FLT    ; A7b: HL walk, 47 T/slot (was 63)
                ld   de, P_ENT_STRIDE
                ld   b, P_MAX_ENT
.t:             ld   a, (hl)
                or   a
                jr   z, .tn
                dec  (hl)
.tn:            add  hl, de
                djnz .t
                ret

;------------------------------------------------------------------------------
; draw_slot — blit/stamp ANIM_SLOT per its dirty class; update drawn state.
; In : HL = its record (SLOTREC + slot*16).  Clobbers: all but IY.
;------------------------------------------------------------------------------
draw_slot:
                ld   a, l
                or   R_DIRTY
                ld   l, a
                ld   a, (hl)
                or   a
                ret  z                         ; NONE
                ld   c, a
                RFIELD R_VIS
                ld   a, (hl)
                or   a
                ret  z                         ; hidden: erase already done
                ld   a, (ANIM_SLOT)
                call ent_ix                    ; (keeps HL, C)
                ld   a, c
                cp   DIRTY_ATTR
                jr   z, .attr
                ; full / force: blit
                inc  l
                ld   a, (hl)                   ; R_FID
                ld   (BL_FID), a
                inc  l
                ld   a, (hl)                   ; R_FPX
                ld   (BL_FPX), a
                inc  l
                ld   a, (hl)                   ; R_FPY
                ld   (BL_FPY), a
                ld   a, l
                add  a, R_LEFT - R_FPY
                ld   l, a
                ld   a, (hl)                   ; R_LEFT
                ld   (BL_LEFT), a
                call blit_sprite
.probe_blit_ret:                                ; flicker probe (no code)
                ; drawn state: E_DVIS, then E_DFID..E_DROWS = R_FID..R_ROWS
                ld   a, (BL_LEFT)
                or   1
                ld   (ix+E_DVIS), a
                ld   a, (ANIM_SLOT)
                rlca
                rlca
                rlca
                rlca
                inc  a                         ; R_FID
                ld   l, a
                ld   h, SLOTREC >> 8
                push ix
                pop  de
                ld   a, e
                ASSERT (P_ENTITIES & $FF) == 0 ; no carry: records 32-B aligned
                add  a, E_DFID                 ; (32-B records: no carry)
                ld   e, a
                ld   bc, R_ROWS - R_FID + 1
                ldir                           ; HL -> R_LEFT
    IF ANIM_TRACE_ON
                ld   a, l
                add  a, R_LOG - R_LEFT
                ld   l, a
                ld   a, (hl)
                or   a
                jr   z, .attr
                push hl
                call trace_log                 ; ANIM_TRACE on a drawn-frame change (§11.2)
                pop  hl
    ENDIF
.attr:          RFIELD R_COL
                ld   c, (hl)
                inc  l
                ld   b, (hl)
                inc  l
                ld   d, (hl)
                inc  l
                ld   e, (hl)
                inc  l
                inc  l                         ; R_ATTR
                ld   a, (hl)
                inc  l
                ld   (hl), a                   ; R_DATTR = the attr stamped now
                jp   stamp_slot                ; 3F-T8 (boss2.asm): stamp_rect, or both screens

    IF ANIM_TRACE_ON
; trace_log — append (ANIM_SLOT, BL_FID) to the 32-B ANIM_TRACE ring.
; ANIM_TRACE_ON builds only (kit / test builds; 0 B in the release tape).
; Clobbers: A, DE, HL.
trace_log:
                ld   a, (ANIM_TRACE_IDX)
                ld   l, a
                add  a, 2
                and  ANIM_TRACE_LEN - 1
                ld   (ANIM_TRACE_IDX), a
                ld   h, 0
                ld   de, ANIM_TRACE
                add  hl, de
                ld   a, (ANIM_SLOT)
                ld   (hl), a
                inc  hl
                ld   a, (BL_FID)
                ld   (hl), a
                ret
    ENDIF

;------------------------------------------------------------------------------
; damage list: rects stored as (c0, c1, r0, r1) with exclusive ends.
;------------------------------------------------------------------------------
; dmg_add — add rect C,B,D(cols),E(rows). Full list: the last entry becomes
; the whole playfield (every visible sprite is then repaired: slow but never
; wrong) and DMG_OVERFLOW counts it.  Clobbers: A, HL
dmg_add:
                ld   a, (DMG_COUNT)
                cp   DMG_MAX
                jr   nc, .full
                inc  a
                ld   (DMG_COUNT), a
                dec  a
                add  a, a
                add  a, a
                ld   l, a
                ld   h, 0
                push de
                ld   de, DMG_LIST
                add  hl, de
                pop  de
                ld   (hl), c
                inc  hl
                ld   a, c
                add  a, d
                ld   (hl), a
                inc  hl
                ld   (hl), b
                inc  hl
                ld   a, b
                add  a, e
                ld   (hl), a
                ret
.full:          ld   hl, DMG_OVERFLOW
                inc  (hl)
                ld   hl, DMG_LIST + (DMG_MAX - 1) * 4
                ld   (hl), 0                   ; c0
                inc  hl
                ld   (hl), ROOM_COLS           ; c1
                inc  hl
                ld   (hl), 0                   ; r0
                inc  hl
                ld   (hl), PLAY_ROWS           ; r1
                ret

; dmg_hit — CF = 1 if rect C,B,D(cols),E(rows) intersects any damage rect.
; Clobbers: A, D, E, HL (BC kept)
dmg_hit:
                ld   a, c
                add  a, d
                ld   d, a                      ; D = c1
                ld   a, b
                add  a, e
                ld   e, a                      ; E = r1
                ld   a, (DMG_COUNT)
                or   a
                ret  z
                ld   (TMP7), a
                ld   hl, DMG_LIST
.l:             ld   a, (hl)                   ; rc0 < c1 ?
                cp   d
                jr   nc, .s3
                inc  hl
                ld   a, c                      ; c0 < rc1 ?
                cp   (hl)
                jr   nc, .s2
                inc  hl
                ld   a, (hl)                   ; rr0 < r1 ?
                cp   e
                jr   nc, .s1
                inc  hl
                ld   a, b                      ; r0 < rr1 ?
                cp   (hl)
                jr   nc, .s0
                scf
                ret
.s3:            inc  hl
.s2:            inc  hl
.s1:            inc  hl
.s0:            inc  hl
                ld   a, (TMP7)
                dec  a
                ld   (TMP7), a
                jr   nz, .l
                ret                            ; CF = 0 from the failing jr nc

