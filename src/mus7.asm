;==============================================================================
; mus7.asm — SND-3, bank 7: the Dangerous (W) cue. Mailbox writes only (MUS_REQ,
; level-triggered): no work in the ISR, SND_MODE / SND_HOLD are the dispatcher's
; business (music off: the request is remembered and restarts at bar 1 when it
; goes on; turns do not run while paused). Death (Y) is in end_turn.
; Rule (manager decision, sound.md S1f): DANGER = >= DNG_N awake hostiles in
; CUR_ROOM (ACTIVE | HOSTILE, not PENDING / DYING / ASLEEP) or hero HP <=
; MAXHP / 4. Enter on the condition; leave only after DNG_CALM_MIN consecutive
; calm turns AND >= DNG_DWELL_MIN turns since entering; then MUS_ROOM again.
; (The "or one full loop" shortcut is not used: no loop-end flag in the mailbox;
; calm >= 8 already implies dwell >= 9.)
;==============================================================================
DNG_N           EQU 4
DNG_CALM_MIN    EQU 8
DNG_DWELL_MIN   EQU 16
DNG_SCAN_MASK   EQU EF_ACTIVE | EF_HOSTILE | EF_PENDING | EF_DYING
                ASSERT (P_ENTITIES & 31) == 0 && P_ENT_STRIDE == 32 && E_ROOM == E_FLAGS - 1
                ASSERT (ST_FLAGS & $F0) == $10 && (ST_FLAGS & $0F) == 0   ; 'or slot' builds the address

;------------------------------------------------------------------------------
; mus_pick — once per surviving turn, from end_turn (plain call, bank 7).
; Walks the LIVE_LIST (build_live: the active, non-pending bodies of CUR_ROOM,
; built at the turn start; hero = entry 0). Each entry's flags and room are
; re-checked (a body that died this turn is DYING; after a do_exit the list is
; the old room's: its entries fail the room test, the new room counts from the
; next turn's list: a one-turn lag). Status byte = ST_FLAGS + the entry's slot.
; Clobbers: A, BC, DE, HL.  Cost: ~105 T per skipped entry, ~250 T per counted
; hostile (early out at the 4th), + ~0.15k T HP test and state update; worst
; ~2.1k T a turn (12 skipped + 3 counted), typ. < 1k.
;------------------------------------------------------------------------------
mus_pick:
                ld   a, (LIVE_N)
                or   a
                jr   z, .hp                    ; (empty list: never walk 255 entries)
                dec  a                         ; the monsters (entry 0 = the hero)
                jr   z, .hp
                ld   b, a
                ld   c, 0                      ; C = awake hostiles counted
                ld   de, LIVE_LIST + LL_STRIDE + 1 ; DE = entry 1, +1 (ptr lo)
.l:             ld   a, (de)                   ; ptr lo: entities are 32-B aligned, so
                add  a, E_FLAGS                ; + E_FLAGS never carries
                ld   l, a
                inc  de
                ld   a, (de)
                ld   h, a                      ; HL = the entity's E_FLAGS
                ld   a, (hl)
                and  DNG_SCAN_MASK
                cp   EF_ACTIVE | EF_HOSTILE
                jr   nz, .n
                dec  l                         ; E_ROOM = E_FLAGS - 1
                ld   a, (CUR_ROOM)
                cp   (hl)
                jr   nz, .n
                dec  de
                dec  de
                ld   a, (de)                   ; the entry's slot
                inc  de
                inc  de
                or   ST_FLAGS & $FF            ; ST_FLAGS low byte $10: no carry for 0..15
                ld   l, a
                ld   h, ST_FLAGS >> 8
                ld   a, (hl)
                and  STS_HOLD
                cp   HOLD_ASLEEP
                jr   z, .n
                inc  c
                ld   a, c
                cp   DNG_N
                jr   nc, .cond
.n:             inc  de                        ; to the next entry's ptr lo (entry = 5 B,
                inc  de                        ; DE is at +2 now)
                inc  de
                inc  de
                djnz .l
.hp:
                ld   a, (P_ENTITIES + E_MAXHP) ; HP <= MAXHP / 4  (integer: 4 * HP <= MAXHP)
                rrca
                rrca
                and  $3F
                ld   hl, P_ENTITIES + E_HP
                cp   (hl)                      ; CF = quarter < HP
                jr   nc, .cond
                ; calm turn
                ld   hl, DNG_DWELL
                ld   a, (hl)
                or   a
                ret  z                         ; W off
                inc  a
                jr   z, .nd                    ; saturate at 255
                ld   (hl), a
.nd:            inc  l
                inc  (hl)                      ; DNG_CALM (<= ~16: it leaves by then)
                ld   a, (hl)
                cp   DNG_CALM_MIN
                ret  c
                dec  l
                ld   a, (hl)
                cp   DNG_DWELL_MIN
                ret  c
                xor  a
                ld   (hl), a                   ; W off
                inc  l
                ld   (hl), a
                ld   a, MUS_ROOM
                ld   (MUS_REQ), a
                ret
.cond:          ld   hl, DNG_DWELL
                ld   a, (hl)
                or   a
                jr   nz, .on
                ld   (hl), 1                   ; enter
                inc  l
                ld   (hl), 0
                ld   a, MUS_DANGER
                ld   (MUS_REQ), a
                ret
.on:            inc  a
                jr   z, .nc
                ld   (hl), a
.nc:            inc  l
                ld   (hl), 0                   ; calm run broken
                ret
