;==============================================================================
; anim.asm — per-entity animation state machine (prototype §7) and the
; per-tick dirty-sprite renderer (§4.2/§4.3/§5.5).
;
; Per tick: anim_tick advances every live entity of CUR_ROOM (REST idle loop /
; MOVE tween 4 px + motion cycle / SEQ one-shot with IMPACT / HOLD) and writes
; the desired frame into N_VIS/N_FID. render then diffs desired vs drawn:
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
                ld   hl, N_VIS
                add  a, l
                ld   l, a
                ld   (hl), 0                   ; default: hidden
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
                ld   hl, N_FID
                add  a, l
                ld   l, a
                ld   (hl), c
                ld   a, l
                sub  N_FID - N_VIS
                ld   l, a
                ld   (hl), b
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
; ascending). rl_next: A = ANIM_SLOT = next slot, CF = 1 when exhausted.
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
                ld   l, a
                ld   h, RLIST >> 8
                ld   a, (hl)
                ld   (ANIM_SLOT), a
                or   a                         ; CF = 0
                ret

;------------------------------------------------------------------------------
; anim_entity — IX = live entity. Out: A = fid, B = 1 visible / 0 hidden.
;------------------------------------------------------------------------------
anim_entity:
                ld   a, (ix+E_MODE)
                cp   M_MOVE
                jp   z, .move
                cp   M_SEQ
                jp   z, .seq
                cp   M_HOLD
                jr   nz, .rest
                ld   a, (ix+E_WPH)             ; HOLD: the final death frame
                ld   b, 1
                ret
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
                call kind_seq_ptr              ; resting mid-ladder: CLIMB1
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
                ld   a, (ix+E_MODE)
                cp   M_MOVE
                ret  z                         ; CF = 0 (cp equal)
                cp   M_SEQ
                ret  z
                ld   a, (ix+E_REACT)
                or   a
                ret  nz                        ; CF = 0 (or)
.n:             ld   de, P_ENT_STRIDE
                add  ix, de
                djnz .l
                scf
                ret

;==============================================================================
; RENDER
;==============================================================================
; slot_var — HL = array (page SLOTVARS) + ANIM_SLOT.   A = array low offset.
    MACRO SLOTVAR arr
                ld   a, (ANIM_SLOT)
                add  a, arr & $FF
                ld   l, a
                ld   h, arr >> 8
    ENDM

render:
                ; ---------------- 1. desired state + dirty class ----------------
                call rl_first
.d1:            call rl_next
                jp   c, .d1done
                call ent_ix
                SLOTVAR N_LOG
                ld   (hl), 0
                SLOTVAR N_VIS
                ld   a, (hl)
                or   a
                jr   nz, .vis
                ld   a, (ix+E_DVIS)
                and  1
                jr   z, .none
                ld   a, DIRTY_FULL             ; was drawn, now hidden: erase
                jr   .setd
.none:          xor  a
.setd:          push af
                SLOTVAR N_DIRTY
                pop  af
                ld   (hl), a
                jp   .n1
.vis:           ; facing
                ld   a, (ix+E_FLAGS)
                and  EF_LEFT
                ld   c, a
                SLOTVAR N_LEFT
                ld   (hl), c
                ; frame offsets
                SLOTVAR N_FID
                ld   a, (hl)
                ld   (BL_FID), a
                call ft_ptr                    ; HL = frame_tab + fid*4 (FT_COLS)
                inc  hl                        ; FT_H
                ld   b, (hl)
                inc  hl                        ; FT_OFFR
                ld   a, c
                or   a
                jr   z, .offr
                inc  hl                        ; FT_OFFL
.offr:          ld   a, (hl)
                add  a, (ix+E_PX)
                ld   (BL_FPX), a               ; fpx = px + off
                ld   c, b                      ; fpy = py + bh*8 - H
                KFIELD KT_BH
                add  a, a
                add  a, a
                add  a, a
                add  a, (ix+E_PY)
                sub  c
                ld   (BL_FPY), a
                SLOTVAR N_FPX
                ld   a, (BL_FPX)
                ld   (hl), a
                SLOTVAR N_FPY
                ld   a, (BL_FPY)
                ld   (hl), a
                ; attr: flash overrides the kind colour
                ld   a, (ix+E_FLT)
                or   a
                ld   a, (ix+E_FLA)
                jr   nz, .fl
                KFIELD KT_ATTR
.fl:            ld   c, a
                SLOTVAR N_ATTR
                ld   (hl), c
                ; footprint
                ld   a, (BL_FPX)
                ld   e, a
                ld   a, (BL_FPY)
                ld   d, a
                ld   a, (BL_FID)
                call frame_footprint           ; C col, B row, D cols, E rows
                push de
                SLOTVAR N_COL
                ld   (hl), c
                SLOTVAR N_ROW
                ld   (hl), b
                pop  de
                SLOTVAR N_COLS
                ld   (hl), d
                SLOTVAR N_ROWS
                ld   (hl), e
                ; classify vs drawn
                ld   a, (ix+E_DVIS)
                and  1
                jr   z, .full_log
                ld   a, (BL_FID)
                cp   (ix+E_DFID)
                jr   nz, .full_log
                ld   a, (ix+E_DVIS)
                and  EF_LEFT
                ld   c, a
                SLOTVAR N_LEFT
                ld   a, (hl)
                cp   c
                jr   nz, .full
                ld   a, (BL_FPX)
                cp   (ix+E_DFPX)
                jr   nz, .full
                ld   a, (BL_FPY)
                cp   (ix+E_DFPY)
                jr   nz, .full
                SLOTVAR D_ATTR
                ld   c, (hl)
                SLOTVAR N_ATTR
                ld   a, (hl)
                cp   c
                ld   a, DIRTY_NONE
                jr   z, .cls
                ld   a, DIRTY_ATTR
                jr   .cls
.full_log:      SLOTVAR N_LOG
                ld   (hl), 1
.full:          ld   a, DIRTY_FULL
.cls:           ld   c, a
                SLOTVAR N_DIRTY
                ld   (hl), c
.n1:            jp   .d1
.d1done:

                ; ---------------- 2. erase + damage list ------------------------
                xor  a
                ld   (DMG_COUNT), a
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
                call rl_first
.e2:            call rl_next
                jr   c, .e2done
                call ent_ix
                SLOTVAR N_DIRTY
                ld   a, (hl)
                cp   DIRTY_FULL
                jr   nz, .n2
                ld   a, (ix+E_DVIS)
                and  1
                jr   z, .n2
                ld   c, (ix+E_DCOL)            ; erase the old footprint
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
                ; A7: a sprite redrawn in place (same footprint: frame change)
                ; would add the same rect twice (here and in .e3): add it once,
                ; in .e3 (fewer rects to mark for present and to test in repair)
                SLOTVAR N_VIS
                ld   a, (hl)
                or   a
                jr   z, .add2                  ; hidden now: .e3 adds nothing
                ld   a, l
                add  a, N_COL - N_VIS
                ld   l, a
                ld   a, (hl)
                cp   c
                jr   nz, .add2
                ld   a, l
                add  a, N_ROW - N_COL
                ld   l, a
                ld   a, (hl)
                cp   b
                jr   nz, .add2
                ld   a, l
                add  a, N_COLS - N_ROW
                ld   l, a
                ld   a, (hl)
                cp   d
                jr   nz, .add2
                ld   a, l
                add  a, N_ROWS - N_COLS
                ld   l, a
                ld   a, (hl)
                cp   e
                jr   z, .n2
.add2:          call dmg_add
.n2:            jr   .e2
                ASSERT N_COL > N_VIS && N_ROW > N_COL && N_COLS > N_ROW && N_ROWS > N_COLS
                ASSERT (N_VIS >> 8) == (N_ROWS >> 8)
.e2done:
                ; new footprints of changed visible sprites join the damage list
                call rl_first
.e3:            call rl_next
                jr   c, .e3done
                SLOTVAR N_DIRTY
                ld   a, (hl)
                or   a
                jr   z, .n3
                SLOTVAR N_VIS
                ld   a, (hl)
                or   a
                jr   z, .n3
                call slot_new_rect
                call dmg_add
.n3:            jr   .e3
.e3done:
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
                SLOTVAR N_DIRTY
                ld   a, (hl)
                cp   DIRTY_FULL                ; NONE *and* ATTR get repaired: an
                jr   nc, .nf                   ; ATTR draw only stamps, so its
                                               ; pixels under a damage rect are lost
                SLOTVAR N_VIS
                ld   a, (hl)
                or   a
                jr   z, .nf
                call slot_new_rect             ; same as drawn (not dirty)
                push bc
                push de
                call dmg_hit
                pop  de
                pop  bc
                jr   nc, .nf
                call dmg_add
                SLOTVAR N_DIRTY
                ld   (hl), DIRTY_FORCE
                ld   a, 1
                ld   (RENDER_PASS), a
.nf:            jr   .f3
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
                call draw_slot
.nopl:

                ; ---------------- 5. zap overlay, 6. timers ---------------------
                call draw_zap
                ld   ix, P_ENTITIES
                ld   b, P_MAX_ENT
                ld   de, P_ENT_STRIDE
.t:             ld   a, (ix+E_FLT)
                or   a
                jr   z, .tn
                dec  (ix+E_FLT)
.tn:            add  ix, de
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

; slot_new_rect — C,B,D,E = the desired footprint of ANIM_SLOT.  Clobbers A, HL
slot_new_rect:
                SLOTVAR N_COL
                ld   c, (hl)
                SLOTVAR N_ROW
                ld   b, (hl)
                SLOTVAR N_COLS
                ld   d, (hl)
                SLOTVAR N_ROWS
                ld   e, (hl)
                ret

; draw_slot — blit/stamp ANIM_SLOT per its dirty class; update drawn state.
draw_slot:
                ld   a, (ANIM_SLOT)
                call ent_ix
                SLOTVAR N_DIRTY
                ld   a, (hl)
                or   a
                ret  z
                ld   c, a
                SLOTVAR N_VIS
                ld   a, (hl)
                or   a
                ret  z                         ; hidden: erase already done
                ld   a, c
                cp   DIRTY_ATTR
                jr   z, .attr
                ; full / force: blit
                SLOTVAR N_FID
                ld   a, (hl)
                ld   (BL_FID), a
                SLOTVAR N_LEFT
                ld   a, (hl)
                ld   (BL_LEFT), a
                SLOTVAR N_FPX
                ld   a, (hl)
                ld   (BL_FPX), a
                SLOTVAR N_FPY
                ld   a, (hl)
                ld   (BL_FPY), a
                call blit_sprite
.probe_blit_ret:                                ; flicker probe (no code)
                ; ANIM_TRACE on a drawn-frame change (§11.2)
                SLOTVAR N_LOG
                ld   a, (hl)
                or   a
                call nz, trace_log
                ; drawn state
                ld   a, (BL_FID)
                ld   (ix+E_DFID), a
                ld   a, (BL_FPX)
                ld   (ix+E_DFPX), a
                ld   a, (BL_FPY)
                ld   (ix+E_DFPY), a
                ld   a, (BL_LEFT)
                or   1
                ld   (ix+E_DVIS), a
                call slot_new_rect
                ld   (ix+E_DCOL), c
                ld   (ix+E_DROW), b
                ld   (ix+E_DCOLS), d
                ld   (ix+E_DROWS), e
.attr:          call slot_new_rect
                SLOTVAR N_ATTR
                ld   a, (hl)
                push af
                SLOTVAR D_ATTR
                pop  af
                ld   (hl), a
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
                ld   (hl), ROOM_ROWS           ; r1
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
