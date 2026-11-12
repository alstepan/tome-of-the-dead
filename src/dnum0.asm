;==============================================================================
; dnum0.asm — D3-11 flying damage numbers (game.md §6.5, §6.5.1 Q2, §6.4.1),
; the per-pass part. Bank 0 cold-code block (b0_code; FARB0 from bank-2
; dn_gate at the END of a tick: dn_tick still in its first frame, dn_q2 in its
; second). Rules = bank3.asm's: pages nothing itself (far7 / far3 hand $C000
; back), no SMC, no variables (all state is DN_* RAM + DN_ZCOL,
; combat_defs.asm). Bank 0 is uncontended. The spawn (value, merge, text,
; placement, compose) is bank-3 dnum3.asm (far3, <= 1 a pass).
;
; Detection is a DIFF per slot (DN_SLOT records), not a hook per damage
; site: DS_SNAP = the HP last accounted for, DS_SRC = E_REACT at the last pass,
; DS_SEEN = the pass it was last scanned (a slot the previous pass did not see
; only resyncs: no number for what happened while it was away).
;  - a reaction pending (E_REACT 1..$7F: struck, its impact tick later) holds
;    the HP change back; once it starts (anim .rest: HURT / BLOCK / DEATH run
;    as $80 | rc, DODGE / PARRY clear at once) the change spawns -n / +n: the
;    impact tick (§6.5.1 Q2); nothing lost on a HURT = "0" (immune), on a
;    BLOCK / DODGE / PARRY = MISS;
;  - LVL-FLOATER: a hero level-up (xp7 sets DS_FLG bit 7) spawns "+LVL" as a MISS-kind
;    candidate (dn_lvt picks the text; bank 2);
;  - a miss / parry line (impact_line -> dn_sfx: DS_FLG) spawns a MISS: melee,
;    Power Strike and every Whirlwind body, monsters' misses on the hero;
;  - an HP change with no reaction (potion, Drain Life's caster, a poison
;    tick, the Vampire's bite heal, a trap) spawns, but not while an FX track
;    is busy (a bolt in flight keeps the caster's +n behind the target's -n);
;  - silent: FED regen (hunger7 bumps the hero's DS_SNAP with the HP), the
;    hero's MAXHP rise (level-up / tomes: taken off his HP change), any
;    change from a snapshot of 0 (a dead body's slot reused; the kit revive).
; One spawn a tick: every candidate is ranked by E_X (left to right: the
; Whirlwind ripple), changes with no reaction after the rest (key bit 7); a
; 1st-frame pass spawns the best, each 2nd-frame tick the next of the same
; ranking (dn_q2, no rescan); the others keep their state and come up at the
; next scan. The change is the full 9-bit HP difference, shown capped at 99.
;
; Drawing: cell-aligned, centred on the drawn footprint (SLOTREC), clamped to
; the row; start row = the drawn top row - 1, kept inside the storey (at least
; 9s + 1: it overdraws a body that tops the storey); rises 1 px a pass for 8
; passes, then holds 4 (12). Window = rows start - 1 and start.
; DNUM-SPRITE-FIX (user 2026-11-03): drawn on the DISPLAYED screen only (bank-2
; dnum2.asm dn_show, far7: screen 2 paged), OR'd over the bank-5 composed cell
; (sprite pixels kept; the number's attr on a bare cell only); bank 5 never
; holds a number. Redrawn every pass. A row it leaves (the start row at rise 8,
; both at the end, a merged / replaced / evicted number) is marked for present
; (pmark_rect: the next present copies bank 5 back, exact; nothing to repair).
; A cell the tick marked is drawn by the next present's dn_fix (dnfix2.asm)
; right before its copy, so a body walking under a number keeps the digit.
; A room exit needs nothing: the scroll runs on the bank-5 screen (show_bank5)
; and present_full copies it to screen 2; vis_room_sync's dn_reset frees them.
;==============================================================================

;------------------------------------------------------------------------------
; dn_tick — FARB0 from dn_gate (bank 2): one pass. Clobbers: all but IY.
; Cost: ~0.3k + ~0.2-0.6k per slot (16); a spawn + its far3 ~4k; per live number
; ~0.6k (far7) + ~0.25k per cell + ~0.55k per drawn cell row (<= 3 cells x 2 rows).
;------------------------------------------------------------------------------
dn_tick:
    IF TOME_FX2
                call dn_tm                     ; TOME-FX2: the Tome hit effect's per-tick count
    ENDIF
                ld   hl, dn_step               ; erases first, then every draw: an
                call dn_each                   ; erase never wipes a number drawn
                ld   hl, dn_shw7               ; earlier in the same pass
                call dn_each
                ld   hl, DN_LIVE + DL_SLOT     ; every record free: present's dn_fix call off
                ld   a, (hl)                   ; (dn_mb turns it on with the next spawn)
                ld   l, (DN_LIVE + DN_LIVE_STRIDE + DL_SLOT) & $FF
                and  (hl)
                ld   l, (DN_LIVE + 2 * DN_LIVE_STRIDE + DL_SLOT) & $FF
                and  (hl)
                inc  a
                jr   nz, dn_scan
                ld   a, OP_LD_BC_NN
                ld   (present.dnf), a          ; (bank-2 code byte: present's SMC site)
                ; fall through: then <= 1 spawn (drawn by dn_mb)
;------------------------------------------------------------------------------
; dn_scan — the 1st-frame pass's spawn: every slot ranked (dn_cls: its key in
; DN_KEY, $FF none), then the best spawned (dn_take, bank 3: it draws the new
; number at once). The keys left are the queue the next 2nd-frame ticks spawn
; from (dn_q2), one a tick, until the next scan rewrites them. All 16 slots,
; not RLIST: a kill's slot freed between two passes (its DEATH ended, off the
; render list) still owes its -n (dn_cls).  Clobbers: all but IY
;------------------------------------------------------------------------------
dn_scan:
                ld   (DN_QN), a                ; PERF-GHOST: the queue may hold keys now (A != 0 on
                                               ; both entries: dn_tick's INC A / JR NZ, OP_LD_BC_NN)
                ld   hl, DN_PASS
                inc  (hl)
                ld   hl, DN_KEY
                ld   b, P_MAX_ENT
.k:             ld   (hl), $FF                 ; no candidate
                inc  l
                djnz .k
                ld   bc, P_MAX_ENT << 8        ; B = 16, C = slot 0
.l:             push bc
                ld   a, c
                call dn_cls
                pop  bc
                inc  c
                djnz .l
.pop:           call dn_pop                    ; the lowest key -> DN_CUR / DN_BT
                ret  c                         ; none left
                ld   a, (DN_CUR)               ; its state consumed
                ld   c, a
                call dn_sl                     ; IX = entity, HL = DS_SEEN
                ld   a, (DN_PASS)
                cp   (hl)
                jr   nz, .pop                  ; not ranked by the last scan (a room change since)
                ld   a, (ix+E_REACT)
                dec  a
                cp   $7F
                jr   c, .pop                   ; struck again since the scan (2nd frame): its next pass
                inc  l
                inc  a                         ; B = rc (DNT_REACT): the running reaction's,
                jr   nz, .rk                   ; else (DODGE / PARRY / done: E_REACT 0) the
                ld   a, (hl)                   ; pending one remembered in DS_SRC (a reaction
.rk:            and  7                         ; set and started between two passes has no
                ld   b, a                      ; pending snapshot: its own rc)
                ld   a, (ix+E_REACT)
                ld   (hl), a                   ; DS_SRC := now
                inc  l
                res  DSF_MISS, (hl)            ; DS_FLG: the miss line goes with it (a level-up's bit 7
                                               ; stays until dn_lvt spawns "+LVL": a reaction spawn first keeps it)
                ld   a, (DN_BT)
                rra
                jr   c, .miss                  ; DNT_MISS (a MISS keeps the HP snapshot)
                push bc
                ld   a, c
                call dn_delta                  ; A = the change (-99..99), the snapshots := now
                pop  bc
                jr   nz, .go
                ld   a, (DN_BT)
                rla
                ret  c                         ; DNT_HP: no net change (the hero's MAXHP rise taken off)
                ld   a, b
                cp   RC_DEATH
                ret  z
                sub  RC_HURT
                jr   z, .go                    ; struck, nothing lost: "0" (immune)
.miss:          call dn_lvt                    ; BLOCK / DODGE / PARRY, a miss line: A = DNV_MISS, DN_TXT = "MISS"
                                               ; (the hero's pending level-up: "+LVL" instead; bank 2)
.go:            ld   hl, dn_take               ; (bank 3: A = the value passes in; IX = the
                call far3                      ; new record comes back)
                ; fall through (DNUM-SPRITE-FIX: the new number drawn now)
;------------------------------------------------------------------------------
; dn_mb — IX = a new record (DL_ROW / DL_COL placed): DL_MB = the PRES_MASK
; low byte of its row above's first col (dn_fix's coarse test), then drawn.
; Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
dn_mb:
                ld   a, (ix+DL_ROW)
                add  a, a
                add  a, a
                ld   b, a                      ; row * 4
                ld   a, (ix+DL_COL)
                rrca
                rrca
                rrca
                and  3
                add  a, b
                add  a, (PRES_MASK - 4) & $FF  ; (row - 1) * 4 + col / 8
                ld   (ix+DL_MB), a
                ld   a, OP_CALL_NN
                ld   (present.dnf), a          ; present calls dn_fix again (bank-2 SMC site)
                ; fall through
; dn_shw7 — IX = record: bank-2 dn_show with screen 2 paged (far7: farb pages
; bank 7, then bank 0 back).  Clobbers: A, BC, DE, HL
dn_shw7:
                ld   hl, dn_show
                jp   far7
                ASSERT DL_MB == 7 && DL_GLY == 8 && (PRES_MASK & $FF) >= 4 && DN_LIVE_N == 3
                ASSERT DNT_MISS == 1 && DNT_HP == $80 && DNT_REACT == 0 && P_MAX_ENT == 16

; dn_q2 — FARB0 from dn_gate in a tick already in its 2nd frame: no aging, no
; redraw, no rescan: <= 1 spawn from the last scan's queue (dn_pop), not
; while an FX track is busy (a bolt's targets and its caster wait for the next
; light tick).  Clobbers: all but IY
dn_q2:
    IF TOME_FX2
                call dn_tm                     ; TOME-FX2 (every tick passes dn_tick or dn_q2 once)
    ENDIF
                ld   a, (FX_BUSY)
                or   a
                ret  nz
                ; DN-GATE (C2, 2026-11-10): the spawn (up to ~12.8k T) never lands on a heavy
                ; 2nd-frame tick: none after turn logic (heavy_mark: LOGIC_TICK == this tick)
                ; nor after a render with >= DN2_DMG_MAX damage rects (~ that many bodies
                ; redrawn: its present follows in the next tick too). The number waits for the
                ; next light 2nd-frame tick or the next 1st-frame pass (dn_tick).  ~60 T
                ld   a, (DMG_COUNT)
                cp   DN2_DMG_MAX
                ret  nc
                ld   a, (TICK_COUNTER)
                ld   hl, LOGIC_TICK
                cp   (hl)
                ret  z
                jp   dn_scan.pop
                ASSERT (dn_q2 >> 8) == (dn_tick >> 8)      ; dn_gate: ld l, dn_q2 & $FF

    IF TOME_FX2
;------------------------------------------------------------------------------
; dn_tm — TOME-FX2 (user 2026-11-03): the Tome hit effect, counted at the end of every playing tick (dn_gate
; is play_loop's first call: the last work of the tick just done, after the turn logic). TOME_FL (tome_strike:
; TOME_FL_N) 0 = nothing (~45 T with the call). Else it counts down and, per value AFTER the decrement:
;   TOME_BORDER 0 (N 3): 0 -> lect_back (bank 7, far7: the flash restored, ash after the last hit).
;   TOME_BORDER 1 (N 4): 2 -> the border BORDER_TOME (BORDER_TOME_END once TOME_HP is 0), 1 -> lect_back,
;                        0 -> the border black. The border bits 3 / 4 (MIC / EAR) are 0: the game has no beeper
;                        (AY only; the ALARM border and end_card write the port the same way).
; A paint is queued after the tick's render and shown at the start of the tick after next; the restore queued
; here is rendered / shown 2 ticks later too, so lectern white = exactly 2 ticks, whatever the attack (a
; spell's projectile phase no longer holds it: the old restore waited for the end of the turn). The border
; is written at the tick's end, just before the HALT that starts the tick which presents the change.
; A modal screen (pause, bag) calls show_bank5, which blacks the border (lowram.asm).
; Clobbers: A, HL (lect_back via far7: all but IX).
;------------------------------------------------------------------------------
dn_tm:
                ld   hl, TOME_FL
                ld   a, (hl)
                or   a
                ret  z
                dec  a
                ld   (hl), a
    IF TOME_BORDER
                jr   z, .off
                cp   2
                jr   z, .on
                ret  nc                        ; 3: the paint is not on screen yet
    ELSE
                ret  nz
    ENDIF
                ld   hl, lect_back             ; (bank 7: back with bank 0 paged again, farb)
                jp   far7
    IF TOME_BORDER
.on:            ld   a, (TOME_HP)
                or   a
                ld   a, BORDER_TOME
                jr   nz, .o
                ld   a, BORDER_TOME_END        ; the last hit: the destroyed beat
                jr   .o
.off:           xor  a
.o:             out  (PORT_BORDER), a
                ret
    ENDIF
    ENDIF

; dn_each — HL = routine, called with IX = the record for every live entry
; (it keeps IX).  Clobbers: as the routine
dn_each:
                ld   ix, DN_LIVE
.e:             ld   a, (ix+DL_SLOT)
                inc  a                         ; $FF: free
                push hl
                call nz, jp_hl
                pop  hl
                ld   de, DN_LIVE_STRIDE
                add  ix, de
                ld   a, ixl
                cp   (DN_LIVE + DN_LIVE_N * DN_LIVE_STRIDE) & $FF
                jr   nz, .e
                ret
                ASSERT (DN_LIVE >> 8) == ((DN_LIVE + DN_LIVE_N * DN_LIVE_STRIDE - 1) >> 8)
; dn_step — IX = record: expire (both rows erased, free) or age; at rise 8
; (k 7 -> 8) the start row is erased (marked: the next present copies bank 5
; back).  Clobbers: A, BC, DE, HL
dn_step:
                ld   a, (ix+DL_AGE)
                cp   DN_LIFE
                jr   nc, .end
                inc  (ix+DL_AGE)
                cp   DN_RISE
                ret  nz
                call dn_win                    ; k = 8: the start row back
                inc  b
                dec  e
                jp   pmark_rect
.end:           ld   (ix+DL_SLOT), $FF         ; expired: its rows marked (present restores them)
                ; fall through
; dn_erase — record IX's window (rows start - 1, start) marked for present
; (also far from bank-3 dn_take): the next present copies the composed cells
; back, unless another live number covers one (dn_fix draws it there).
; Clobbers: A, BC, DE, HL
dn_erase:
                call dn_win
                jp   pmark_rect

;------------------------------------------------------------------------------
; dn_pop — the spawn queue's head (dn_scan / dn_q2): the lowest DN_KEY (the
; last scan's ranking) taken ($FF) -> DN_CUR = its slot, DN_BT = its key (bit 0
; DNT_MISS, bit 7 DNT_HP). CF: none left (PERF-GHOST: then DN_QN := 0).  Clobbers: A, BC, E, HL.  ~0.5k T
; (DNUM-SPRITE-FIX: from bank 2, room for the screen-2 draw there)
;------------------------------------------------------------------------------
dn_pop:
                ld   hl, DN_KEY
                ld   bc, P_MAX_ENT << 8 | $FF  ; C = the lowest key so far
.f:             ld   a, (hl)
                cp   c
                jr   nc, .n
                ld   c, a
                ld   e, l
.n:             inc  l
                djnz .f
                ld   a, c
                add  a, 1
                jr   c, .none                  ; all $FF
                ld   l, e
                ld   (hl), $FF                 ; taken
                ld   a, c
                ld   (DN_BT), a
                ld   a, e
                sub  DN_KEY & $FF              ; (NC)
                ld   (DN_CUR), a
                ret
.none:          ld   (DN_QN), a                ; PERF-GHOST: A = 0 (CF kept): the queue empty
                ret                            ; (dn_gate skips dn_q2 until the next scan)
                ASSERT OP_LD_BC_NN != 0

;------------------------------------------------------------------------------
; dn_cls — A = slot: resync / hold / rank (header above): a candidate's key
; (2 E_X | its DNT_* kind) into DN_KEY. A freed slot (E_FLAGS 0) is ranked as
; a live one: a kill whose DEATH ended between two passes shows its -n (no
; reaction left: an unreacted change, DNT_HP); an empty slot only resyncs.
; Clobbers: A, BC, DE, HL, IX
;------------------------------------------------------------------------------
dn_cls:
                ld   c, a                      ; C = slot
                call dn_sl                     ; IX = entity, HL = its DS_SEEN
                ld   a, (ix+E_FLAGS)
                or   a
                jr   z, .in                    ; freed: still ranked (a kill's -n owed)
                and  EF_ACTIVE | EF_PENDING
                dec  a                         ; 0: active, not pending
                jr   nz, .off
.in:            ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .off
                ld   a, (DN_PASS)
                ld   b, (hl)
                ld   (hl), a
                dec  a
                cp   b
                inc  hl                        ; DS_SRC (inc hl: the flags kept)
                jr   nz, .sync                 ; not seen last pass: snapshots only
                ld   b, (hl)                   ; B = E_REACT last pass
                ld   a, (ix+E_REACT)
                ld   d, a                      ; D = now
                dec  a
                cp   $7F
                jr   c, .hold                  ; pending: the change waits for its impact
                ld   e, DNT_REACT
                ld   a, b
                dec  a
                cp   $7F
                jr   c, .cand                  ; was pending: started (or cleared) since
                ld   a, d
                cp   b
                jr   z, .none                  ; none, or the same reaction still running
                or   a
                jr   nz, .cand                 ; set and started between two passes
.none:          ld   (hl), d
                inc  l                         ; DS_FLG
                ld   e, DNT_MISS
                ld   a, (hl)
                or   a
                jr   nz, .cand                 ; a miss line
                ld   a, (FX_BUSY)
                or   a
                ret  nz                        ; a track busy: an unreacted change waits
                inc  l                         ; DS_SNAP
                ld   a, (ix+E_HP)
                cp   (hl)
                ret  z
                ld   e, DNT_HP                 ; after every reaction / miss (bit 7)
.cand:          ld   a, (ix+E_X)
                add  a, a
                or   e
                ld   b, a                      ; B = the key
                ld   a, c
                add  a, DN_KEY & $FF
                ld   l, a
                ld   h, DN_KEY >> 8
                ld   (hl), b
                ret
                ASSERT ((DN_KEY + P_MAX_ENT - 1) >> 8) == (DN_KEY >> 8)
.hold:          ld   (hl), d
                ret
.off:           ld   a, (DN_PASS)              ; out of play: resync when it is back
                add  a, $80
                ld   (hl), a
                ret
.sync:          ld   a, (ix+E_REACT)
                ld   (hl), a                   ; DS_SRC
                inc  l
                ld   (hl), 0                   ; DS_FLG
                ld   a, c
                ; fall through (the snapshot := now)
;------------------------------------------------------------------------------
; dn_delta — A = slot: IX = its entity, the snapshots := now; NZ: A = HP -
; DS_SNAP (the hero: - his MAXHP rise since, level-up / tomes: game.md §6.5;
; the full 9-bit difference, shown capped: -99..99, never 0). Z = silent: no
; net change, or the old snapshot 0 (a dead body's slot reused, the kit revive).
; C = slot kept.  Clobbers: A, B, D, E, HL, IX (HL: H = the sign mask)
;------------------------------------------------------------------------------
dn_delta:
                ld   c, a
                call dn_sl
                inc  l
                inc  l
                inc  l                         ; DS_SNAP
                ld   b, (hl)                   ; B = the HP accounted for
                ld   a, (ix+E_HP)
                ld   (hl), a
                ld   e, a                      ; E = HP
                ld   a, c
                or   a
                jr   nz, .m
                ld   hl, DN_SMAX               ; the hero: his MAXHP rise since (level-up / tome:
                ld   a, (ix+E_MAXHP)           ; HP and MAXHP += D) is taken off the change, not
                ld   d, (hl)                   ; the change dropped (a blow in the same window
                ld   (hl), a                   ; still shows; MAXHP never falls: HP <= MAXHP
                sub  d                         ; keeps the sum <= 255)
                add  a, b
                ld   b, a                      ; B = the HP accounted for + the rise
.m:             ld   a, b
                or   a
                ret  z                         ; from 0: silent
                ld   a, e
                sub  b
                ret  z
                ld   l, a
                sbc  a, a
                ld   h, a                      ; H = the sign mask ($FF: lost)
                xor  l
                sub  h                         ; |change| 1..255
                cp   100
                jr   c, .c
                ld   a, 99
.c:             xor  h
                sub  h                         ; signed again (NZ)
                ret
                ASSERT DS_SNAP == 3

    IF !DEBUG_KIT
                INCLUDE "dnwin.asm"            ; dn_win / dn_sl here in a release build (kit: bank 2, dnum2.asm)
    ENDIF
