;==============================================================================
; sfx2.asm — SND-5, bank 2 (always mapped): the main-code side of the sound
; effects. The ISR side (sfx_step / sfx_out, the V1 steal) is in src/ay.asm;
; mailbox semantics: docs/memory-map.md `SFX_REQ`, docs/design/sound.md
; "SFX as built".
;==============================================================================

;------------------------------------------------------------------------------
; sfx_req — request sound effect A (SFX_* = prio << 5 | index, sfx_ids.inc)
; for the next ISR. Call site: `ld a, SFX_x : call sfx_req` (5 B), any bank.
; The pending SFX_REQ is replaced by a request of >= priority (the ISR then
; applies the same >= rule against the effect playing). The loser of the two
; (the old pending one, or the new one) is kept in SFX_NEXT if its priority
; is >= SFX_DEFER_PRIO (6: LEVELUP behind a KILL in the same turn), it is not
; the same id and its priority is >= the one already in SFX_NEXT: the ISR
; plays it after the effect. Dropped while SND_HOLD
; (pause) or with the SFX bit off. Single-byte stores: the ISR may take the old
; value between the read and the write; the new one is then taken a frame later.
; In: A = id.  Out: A kept.  Clobbers: none (F kept too).   ~0.2k T.
;------------------------------------------------------------------------------
sfx_req:
                push af
                push bc
                ld   b, a
                ld   a, (SND_MODE)
                and  SND_HOLD | SND_SFX
                cp   SND_SFX
                jr   nz, .x                     ; held or SFX off: dropped
                ld   a, (SFX_REQ)
                ld   c, a                       ; C = the pending id (0 = none)
                xor  b
                and  SFX_PRIO_MASK
                jr   z, .rep                    ; equal priority: the new one replaces
                ld   a, b
                cp   c                          ; prios differ: the id order is the prio order
                jr   c, .lose                   ; lower than the pending one
.rep:           ld   a, b
                ld   (SFX_REQ), a
                cp   c
                jr   z, .x                      ; the same effect again: nothing to keep
                ld   b, c                       ; the loser = the old pending one
.lose:          ld   a, b
                cp   SFX_DEFER_PRIO
                jr   c, .x                      ; (0 = none: < too)
                ld   a, (SFX_NEXT)              ; the slot keeps a higher-priority id
                xor  b
                and  SFX_PRIO_MASK
                jr   z, .st                     ; equal priority: the newer one
                ld   a, (SFX_NEXT)
                cp   b                          ; prios differ: id order = prio order
                jr   nc, .x
.st:            ld   a, b
                ld   (SFX_NEXT), a              ; played after the effect (one slot)
.x:             pop  bc
                pop  af
                ret

;------------------------------------------------------------------------------
; sfx_msg — impact_line's hook (lowram.asm): B = the impact message code; the
; melee lines MSG_P_HIT .. MSG_M_MISS request hit / miss / kill / hero hurt /
; monster miss, the monster status lines MSG_M_FROZEN .. MSG_M_CONFUSED (dh_msg
; / st_msg: a status applied) the status effect, pitched per status; squeeze,
; unaffected, wake, thaw: nothing. Clobbers: AF, DE, HL (BC, IX kept).
;------------------------------------------------------------------------------
sfx_msg:
                ld   a, b
                dec  a
                cp   MSG_M_CONFUSED
                ret  nc
                ld   e, a
                ld   d, 0
                ld   hl, sfx_msg_tab
                add  hl, de
                ld   a, (hl)
                or   a
                ret  z
                jr   sfx_req
sfx_msg_tab:    DB   SFX_HIT, SFX_MISS, SFX_KILL, SFX_HURT, SFX_MISS   ; by MSG code 1..5
                DB   0, 0                                              ; 6 squeeze, 7 unaffected
                DB   SFX_ST_FROZEN, SFX_ST_ASLEEP, SFX_ST_STUNNED      ; 8..10
                DB   SFX_ST_FEAR, SFX_ST_CONFUSED                      ; 11 flees, 12
                ASSERT MSG_P_HIT == 1 && MSG_P_MISS == 2 && MSG_P_KILL == 3 && MSG_M_HIT == 4 && MSG_M_MISS == 5
                ASSERT MSG_SQUEEZE == 6 && MSG_M_UNAFF == 7 && MSG_M_FROZEN == 8 && MSG_M_ASLEEP == 9
                ASSERT MSG_M_STUNNED == 10 && MSG_M_FLEES == 11 && MSG_M_CONFUSED == 12 && $ - sfx_msg_tab == 12

;------------------------------------------------------------------------------
; sfx_abl — act_fire's hook (bank 7, the release tick): A = ABL_* -> the
; ability's sound (spells, Power Strike / Whirlwind, the dagger / arrow throw).
; In: A = ABL_* (< ABL_COUNT).  Out: A kept.  Clobbers: F, HL.
;------------------------------------------------------------------------------
sfx_abl:
                push af
                add  a, low sfx_abl_tab
                ld   l, a
                adc  a, high sfx_abl_tab
                sub  l
                ld   h, a
                ld   a, (hl)
                call sfx_req
                pop  af
                ret
sfx_abl_tab:    DB   SFX_SPARK, SFX_FIREBOLT, SFX_FROST, SFX_DRAIN, SFX_LIGHTNING
                DB   SFX_POWER, SFX_WHIRL, SFX_THROW, SFX_THROW
                ASSERT ABL_SPARK == 0 && ABL_FIREBOLT == 1 && ABL_FROST == 2 && ABL_DRAIN == 3 && ABL_LIGHTNING == 4
                ASSERT ABL_POWER == 5 && ABL_WHIRL == 6 && ABL_DAGGER == 7 && ABL_BOW == 8 && $ - sfx_abl_tab == ABL_COUNT

;------------------------------------------------------------------------------
; fx_imp_sfx — SND-5: a track's impact starts: the Firebolt's burst requests
; SFX_BURST (the other spells sound at the release, act_fire). Clobbers: A, F.
; Here (after kind_tab), not in fx.asm: bytes before kind_tab eat its ALIGN pad.
;------------------------------------------------------------------------------
fx_imp_sfx:
                ld   a, (ix+FXD_IMPA)
                cp   FID_firebolt_burst1
                ret  nz
                ld   a, SFX_BURST
                jp   sfx_req

;------------------------------------------------------------------------------
; SND-1 (game.md §3.6) — the in-game sound hotkey `S`. Both pieces live here,
; after kind_tab, because the ALIGN pad before it is nearly full.
; snd_scan — sample_input: D |= SC_SOUND if S is down.  Clobbers: A  (~50 T)
; snd_hot  — intent_tick: the S edge -> snd_cycle (bank 1, far1). Keeps DE;
;            touches no INTENT / FIRE_ST / TURN_HOLD / DN_T / NEED_RELEASE.
;            Clobbers: A, BC, HL
;------------------------------------------------------------------------------
snd_scan:
                ld   a, (KBD_MATRIX + KBROW_ASDFG)
                bit  KB_S_BIT, a
                ret  nz
                set  SC_SOUND_BIT, d
                ret
snd_hot:
                push de
                ld   hl, snd_cycle
                call far1
                pop  de
                ret
