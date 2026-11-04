;==============================================================================
; dnum2b.asm — D3-11 flying damage numbers, the bank-2 entries (header in
; dnum0.asm). After every other bank-2 code (main.asm, after ldir2.asm), so
; no older bank-2 symbol moves.
;==============================================================================

;------------------------------------------------------------------------------
; dn_gate — play_loop's first call (before wait_tick): the numbers pass
; (bank-0, FARB0) as the LAST work of the tick just done (after the turn logic
; and end_turn: it never runs ahead of a heavy tick's tail), only while
; playing: a tick still in its first frame runs the whole pass (dn_tick: age,
; redraw, rescan, <= 1 spawn; <= ~40k T, then ends below ~111k); a 2nd-frame
; tick only spawns the next queued number (dn_q2: the last scan's ranking, no
; rescan, 11-17k T measured; tests/budget.py gates both). The live numbers neither age
; nor redraw in a 2nd-frame tick. PERF-GHOST: a 2nd-frame tick with DN_QN = 0 (the queue
; empty) and TOME_FL = 0 returns at once (dn_q2 would be a no-op).  Clobbers: all but IY.  Gated ~0.1k T.
;------------------------------------------------------------------------------
dn_gate:
                ld   hl, GAME_STATE
                ld   a, (hl)
                cp   GS_PLAYING
                ret  nz
                ld   a, (SYS_FRAMES)
                ld   l, LAST_TICK_FRAME & $FF
                cp   (hl)
                ld   hl, dn_tick
                jr   z, .f                     ; still in its first frame: the pass
    IF !ANIM_TRACE_ON                          ; (trace test builds: no room in the bank-2 tail)
                ld   de, (TOME_FL)             ; PERF-GHOST: E = TOME_FL, D = DN_QN: no Tome count
                ld   a, d                      ; (dn_tm) and the queue known empty -> dn_q2 would
                or   e                         ; do nothing: skip its FARB0 (~1.1k T a 2nd-frame
                ret  z                         ; tick, +7 B; DN_QN: level_defs.asm)
    ENDIF
                ld   l, dn_q2 & $FF            ; in its second: a queued spawn only (one page)
.f:             ld   c, BANK_TEXT
                jp   farb
                ASSERT (GAME_STATE >> 8) == (LAST_TICK_FRAME >> 8) && DN_QN == TOME_FL + 1

;------------------------------------------------------------------------------
; dn_sfx — impact_line's entry (in place of sfx_msg): a miss / parry line also
; marks a MISS number for its target (DS_FLG): the hero's blows (melee, Power
; Strike, every Whirlwind body: melee_strike sets his E_TGT too) -> his E_TGT;
; a monster's miss (MSG_M_MISS: "THE <kind> MISSES YOU") -> the hero.
; Then sfx_msg. Same In / Clobbers as sfx_msg (BC, IX kept).  +~0.1k T
;------------------------------------------------------------------------------
dn_sfx:
                ld   a, b
                sub  MSG_M_MISS
                jr   z, .m                     ; a monster's miss: on the hero (A = slot 0)
                add  a, MSG_M_MISS - MSG_P_MISS
                jr   z, .p
                sub  MSG_P_PARRY - MSG_P_MISS
                jp   nz, sfx_msg               ; (sfx_msg reloads A from B)
.p:             ld   a, (P_ENTITIES + E_TGT)
.m:             add  a, a
                add  a, a
                add  a, (DN_SLOT + DS_FLG) & $FF
                ld   l, a
                ld   h, DN_SLOT >> 8
                set  DSF_MISS, (hl)            ; DS_FLG bit 0: a miss line (bit 7 = the hero's level-up kept)
                jp   sfx_msg
