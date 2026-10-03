;==============================================================================
; anim.asm — per-entity animation state machine (prototype §7) and the
; per-tick dirty-sprite renderer (§4.2/§4.3/§5.5).
;
; Per tick: anim_tick advances every live entity of CUR_ROOM (REST idle loop /
; MOVE tween 4 px + motion cycle / SEQ one-shot with IMPACT / HOLD) and writes
; the desired frame into R_VIS/R_FID (SLOTREC). render then diffs desired vs drawn:
;   erase changed sprites (tile-map restore = bitmap + attr, §4.3), repair
;   overlapping sprites (FORCE re-blit, cascading), draw in slot order with the
;   player last, stamp exact-footprint attrs, overlay the zap, tick timers.
;==============================================================================

; KFIELD variant that preserves HL.
    MACRO KFIELD_KEEPHL off
                push hl
                KFIELD off
                pop  hl
    ENDM

;==============================================================================
; anim_tick — Clobbers: all but IY.
;==============================================================================
anim_tick:
                xor  a
                ld   (RLIST_N), a
.lp:            ld   (ANIM_SLOT), a
                rlca
                rlca
                rlca
                rlca
                ld   l, a
                ld   h, SLOTREC >> 8
                ld   (hl), 0                   ; R_VIS default: hidden
                ld   a, (ANIM_SLOT)
                call ent_ix
                ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_PENDING
                cp   EF_ACTIVE
                jr   nz, .next
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .next
                call anim_entity               ; A = fid, B = visible
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
                cp   P_MAX_ENT
                jr   c, .lp
                ld   a, (MSG_Q)
                or   a
                ret  z
                dec  a
                call ent_ix
                call show_impact_msg
                xor  a
                ld   (MSG_Q), a
                ret

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
                jr   z, .jump
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
                jr   .crest
.jump:          ; JUMP (game.md §2.4): arc tick t = E_TMR. t 0 and 13: JUMP1,
                ; aligned (stand-in: the CLIMB1 / WALK1 pose); t 1..12: JUMP2
                ; (stand-in: the walk cycle), px += 4, py = 8y + jump_dy[t-1]
                ld   a, (ix+E_TMR)
                inc  (ix+E_TMR)
                or   a
                jr   z, .crest
                cp   JUMP_TICKS - 1
                jr   nc, .land
                ld   hl, jump_dy - 1
                ld   e, a
                ld   a, d
                ld   d, 0
                add  hl, de
                add  a, (hl)                   ; signed rise (<= 0)
                ld   (ix+E_PY), a
.fpx:           ld   b, c                      ; px 4 px toward 8x, walk cycle
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
                ; start the pending reaction (HURT / BLOCK / DEATH)
                ld   a, (ix+E_REACT)
                ld   c, KS_HURT
                cp   RC_HURT
                jr   z, .rs
                ld   c, KS_BLOCK
                cp   RC_BLOCK
                jr   z, .rs
                ld   c, KS_DEATH
.rs:            or   $80                       ; running
                ld   (ix+E_REACT), a
                push bc
                call kind_seq_ptr
                pop  bc
                ld   b, 0
                add  hl, bc
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                call start_seq
                jp   .seq
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
                push bc
                call kind_seq_ptr
                pop  bc
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

; jump_dy — the §2.4 arc: py offset of jump ticks 1..12 (game.md §2.4)
jump_dy:        DB -4, -8, -12, -16, -16, -16, -16, -16, -12, -8, -4, 0
                ASSERT $ - jump_dy == JUMP_TICKS - 2
                ASSERT (JUMP_TICKS - 2) * TWEEN_STEP == JUMP_COLS * 8

; tween — A = cur, B = target: step 4 toward.  Clobbers: A
tween:
                cp   b
                ret  z
                jr   c, .up
                sub  TWEEN_STEP
                ret
.up:            add  a, TWEEN_STEP
                ret

; idle_phase — A = (ANIM_FREEZE ? 0 : TICK_COUNTER + slot*5).  Clobbers: A, E
idle_phase:
                ld   a, (ANIM_FREEZE)
                or   a
                ld   a, 0
                ret  nz
                ld   a, (ANIM_SLOT)
                ld   e, a
                add  a, a
                add  a, a
                add  a, e
                ld   e, a
                ld   a, (TICK_COUNTER)
                add  a, e
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
; wizard zap overlay, HUD message.  Clobbers: all but IX.
;------------------------------------------------------------------------------
do_impact:
                ld   a, (ix+E_HIT)
                or   a
                jr   z, .nohit
                push ix
                ld   a, (ix+E_TGT)
                call ent_ix
                ld   (ix+E_FLT), FLASH_TICKS
                ld   (ix+E_FLA), ATTR_HIT
                pop  ix
.nohit:         ld   a, (ix+E_ZAP)
                or   a
                jr   z, .nozap
                ld   a, ZAP_TICKS
                ld   (ZAP_T), a
.nozap:         call ix_slot                   ; queue the HUD line: printed once
                inc  a                         ; at the end of anim_tick (the last
                ld   (MSG_Q), a                ; impact of a tick wins)
                ret

;------------------------------------------------------------------------------
; turn_done — CF = 1 when every live entity of CUR_ROOM rests (or holds) with no
; reaction pending/running, and >= 2 ticks have elapsed.  Clobbers: A, DE, IX
;------------------------------------------------------------------------------
turn_done:
                ld   a, (TURN_TICK)
                cp   2
                ccf
                ret  nc
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
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl                    ; fid * FT_STRIDE
                ld   de, frame_tab + FT_COLS
                add  hl, de
                ld   c, (hl)                   ; C = data cols
                inc  hl
                ld   b, (hl)                   ; B = H (FT_H)
                inc  hl                        ; FT_OFFR
                bit  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   z, .offr
                inc  hl                        ; FT_OFFL
.offr:          ld   a, (hl)
                add  a, (ix+E_PX)
                ld   e, a                      ; E = fpx
                KFIELD KT_BH
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
                KFIELD_KEEPHL KT_ATTR
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
                inc  l
                ld   (hl), 0                   ; R_LOG
                dec  c
                jp   nz, .s                    ; NONE: nothing to erase or add
                RFIELD R_COL                   ; ATTR: re-stamped in place
                jp   .addn
.full_log:      RFIELD R_LOG
                ld   (hl), 1
                jr   .fullc
.full:          RFIELD R_LOG
                ld   (hl), 0
.fullc:         dec  l                         ; R_DIRTY
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
.hidden:        RFIELD R_LOG
                ld   (hl), 0
                dec  l                         ; R_DIRTY
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

                ; ---------------- 5. zap overlay, 6. timers ---------------------
                call draw_zap
                ld   hl, P_ENTITIES + E_FLT    ; A7b: HL walk, 47 T/slot (was 63)
                ld   de, P_ENT_STRIDE
                ld   b, P_MAX_ENT
.t:             ld   a, (hl)
                or   a
                jr   z, .tn
                dec  (hl)
.tn:            add  hl, de
                djnz .t
                ld   a, (ZAP_T)
                or   a
                ret  z
                dec  a
                ld   (ZAP_T), a
                ret  nz
                ld   a, (ZAP_COL)              ; zap over: restore its cells next tick
                ld   c, a
                ld   a, (ZAP_ROW)
                ld   b, a
                ld   a, (ZAP_LEN)
                ld   d, a
                ld   e, 1
                jp   queue_damage

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
                ld   a, l
                add  a, R_LOG - R_LEFT
                ld   l, a
                ld   a, (hl)
                or   a
                jr   z, .attr
                push hl
                call trace_log                 ; ANIM_TRACE on a drawn-frame change (§11.2)
                pop  hl
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
                jp   stamp_rect

; trace_log — append (ANIM_SLOT, BL_FID) to the 32-B ANIM_TRACE ring.
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

;------------------------------------------------------------------------------
; draw_zap — wizard zap overlay: ZAP1/ZAP2 alternating per tick in the gap
; cells of the staff row, skipping cells under any drawn sprite (zap_covered);
; marks the run for present (A7).
; Clobbers: A, BC, DE, HL, IX
;------------------------------------------------------------------------------
draw_zap:
                ld   a, (ZAP_T)
                or   a
                ret  z
                ld   a, (ZAP_LEN)
                ld   b, a
                ld   a, (ZAP_COL)
                ld   c, a
                push bc                        ; A7: the overlay is not in DMG_LIST:
                ld   d, b                      ; mark its whole row run for present
                ld   e, 1
                ld   a, (ZAP_ROW)
                ld   b, a
                call pmark_rect
                pop  bc
.l:             push bc
                call zap_covered               ; a drawn sprite's cell (hero,
                jr   c, .skip                  ; or a wide / HURT target): keep it
                ld   a, (ZAP_ROW)
                ld   b, a
                ld   a, (TICK_COUNTER)
                and  1
                add  a, T_ZAP1
                add  a, a
                add  a, a
                add  a, a
                ld   l, a
                ld   h, TILE_GLYPHS >> 8       ; T_ZAP1/2 < TILE_COMMON (32): first page
                ld   a, ATTR_ZAP
                call draw_glyph
.skip:          pop  bc
                inc  c
                djnz .l
                ret

; zap_covered — CF = 1 if cell (col C, ZAP_ROW) lies in any drawn sprite's
; footprint. The bolt only fills empty gap cells (§6.5): it never overwrites a
; sprite's pixels or attrs (review C A5). ~90 T per RLIST entry, zap ticks only.
; Preserves BC.  Clobbers: A, DE, HL, IX
zap_covered:
                ld   a, (RLIST_N)
                or   a
                ret  z                         ; CF = 0
                ld   d, a
                ld   hl, RLIST
.l:             ld   a, (hl)
                push de
                call ent_ix
                pop  de
                bit  0, (ix+E_DVIS)
                jr   z, .n
                ld   a, (ZAP_ROW)
                sub  (ix+E_DROW)
                jr   c, .n
                cp   (ix+E_DROWS)
                jr   nc, .n
                ld   a, c
                sub  (ix+E_DCOL)
                jr   c, .n
                cp   (ix+E_DCOLS)
                jr   nc, .n
                scf
                ret
.n:             inc  hl
                dec  d
                jr   nz, .l
                or   a                         ; CF = 0
                ret

; draw_glyph — 8 B glyph HL into cell (row B, col C) with attr A.
; Clobbers: A, DE, HL
draw_glyph:
                push hl
                push af
                call attr_addr
                pop  af
                ld   (hl), a
                ld   a, b
                and  $18
                or   SCREEN_BITMAP >> 8
                ld   d, a
                ld   a, b
                rrca
                rrca
                rrca
                and  $E0
                or   c
                ld   e, a
                pop  hl
                ld   a, 8
.g:             push af
                ld   a, (hl)
                ld   (de), a
                inc  hl
                inc  d
                pop  af
                dec  a
                jr   nz, .g
                ret

;------------------------------------------------------------------------------
; hide_sprites — erase every drawn sprite + the zap + queued damage (before a
; transition: "all sprites are hidden", §3.6). Clobbers: all but IY.
;------------------------------------------------------------------------------
hide_sprites:
                xor  a
.l:             ld   (ANIM_SLOT), a
                call ent_ix
                ld   a, (ix+E_DVIS)
                and  1
                jr   z, .n
                ld   c, (ix+E_DCOL)
                ld   b, (ix+E_DROW)
                ld   d, (ix+E_DCOLS)
                ld   e, (ix+E_DROWS)
                call erase_rect
                ld   (ix+E_DVIS), 0
.n:             ld   a, (ANIM_SLOT)
                inc  a
                cp   P_MAX_ENT
                jr   c, .l
                ld   a, (ZAP_T)
                or   a
                jr   z, .nz
                xor  a
                ld   (ZAP_T), a
                ld   a, (ZAP_COL)
                ld   c, a
                ld   a, (ZAP_ROW)
                ld   b, a
                ld   a, (ZAP_LEN)
                ld   d, a
                ld   e, 1
                call erase_rect
.nz:            ld   a, (PEND_DMG_COUNT)
                or   a
                ret  z
                ld   b, a
                ld   hl, PEND_DMG
.p:             push bc
                ld   c, (hl)
                inc  hl
                ld   b, (hl)
                inc  hl
                ld   d, (hl)
                inc  hl
                ld   e, (hl)
                inc  hl
                push hl
                call erase_rect
                pop  hl
                pop  bc
                djnz .p
                xor  a
                ld   (PEND_DMG_COUNT), a
                ret
