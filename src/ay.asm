;==============================================================================
; ay.asm — A8 AY player slot: bank 3, AY_RESERVE..AY_RESERVE_END (4 KB since
; D3-0, user 2026-10-06; game.md §11.2; 4704 B from $EDA0 since MEM-SND). SND-2 T2: the WZM v0.3 player
; (src/music/player.asm, WZM_BUZZER, no echo) + the mailbox dispatcher ay_play
; + the 7 in-game songs (tools/abc2wzm.py --game -> build/music_game/). Loaded
; by its own headerless tape block (AY_LEN from AY_RESERVE, `start`).
;
; Slot order (main.asm ASSERTs / tests rely on it):
;   1. ay_play (= AY_PLAY, $F000)
;   2. MODULE wzm: the player (code, period table, then its state pl_regs ..
;      player_end)
;   3. the dispatcher's private state (ay_mode, ay_loop), right after
;      wzm.player_end: ay_vars = wzm.pl_regs .. ay_vars_end is ONE block of
;      every runtime-written byte of the slot (tests/game.py #50 masks it)
;   4. MODULE mus: the songs + mus_tab_first (DW song, MUS_* id order 2..7; id 1 removed)
;
; Slot contract (docs/conventions.md "Interrupts"): the IM 2 ISR (lowram.asm
; `isr`, running from bank 2) pages BANK_AY in by OUT only and calls AY_PLAY
; once per frame with interrupts disabled, then re-OUTs PORT_7FFD_SHADOW.
; ay_play clobbers AF, BC, DE, HL, IX (the ISR saves them + IY); no IY, no
; alternate set, no EI, no $7FFD / shadow writes, no $C000 data of other banks.
; Mailbox semantics: defs.asm (SND_MODE .. SFX_REQ), docs/memory-map.md.
;==============================================================================

;------------------------------------------------------------------------------
; ay_play — once per frame from the ISR. AY_CALLS += 1, then:
;  0. SND_HOLD: drop MUS_SHOT and SFX_REQ, silence R8-R10 (chip + wzm.pl_regs),
;     freeze the music AND the sound effect (sfx_* untouched: the V1 steal
;     resumes in place) — ay_mode is NOT updated, so a music bit changed in the
;     pause is seen as an edge at release; unchanged = resume in place.
;  Unheld, no SFX_REQ and no effect playing (~40 T): ay_music (steps 1-5).
;  Else (SND-5): sfx_step (take SFX_REQ, advance the effect one frame into the
;  mirror), ay_music, sfx_out (the channel-A OUTs when player_frame did not).
; Clobbers: AF, BC, DE, HL, IX.   Stack: 8 B incl. its CALL (ay_music / sfx_step
; call + player_frame -> pl_voice -> pl_fetch, or -> sfx_dk -> .duck).
; Cost (measured, ZEsarUX, incl. CALL/RET; docs/memory-map.md "Interrupts
; (A8)"): SND-2 figures + ~40 T idle; an effect frame + ~0.4-0.6k T.
;------------------------------------------------------------------------------
AY_LOOP_FORCE   EQU $FF             ; ay_loop value no MUS_REQ equals: restart

ay_play:
                ASSERT ay_play == AY_PLAY
                ld   hl, (AY_CALLS)
                inc  hl
                ld   (AY_CALLS), hl
                ld   a, (SND_MODE)
                ld   c, a                       ; C = the mode this frame (one read)
                rla                             ; CY = SND_HOLD (bit 7)
                ASSERT SND_HOLD_BIT == 7 && SND_MUSIC_BIT == 0
                jr   c, .hold
                ld   a, (SFX_REQ)
                ld   hl, sfx_ptr + 1
                or   (hl)
                jr   z, ay_music_c              ; no request, no effect: the music alone
                call sfx_step                   ; the effect's frame into the mirror first:
                call ay_music                   ; player_frame OUTs it with the music
                jp   sfx_out
.hold:          xor  a
                ld   (MUS_SHOT), a              ; dropped while held
                ld   (SFX_REQ), a               ; SND-5: requests too (sfx_req drops them anyway)
                ld   hl, sfx_ptr + 1
                or   (hl)
                jr   nz, .hk                    ; an effect is frozen: its deferred one waits
                ld   (SFX_NEXT), a              ; none plays: a deferred id would replay later
.hk:            jp   ay_silence                 ; every held frame, ~0.15k T; frozen state

;------------------------------------------------------------------------------
; ay_music — the SND-2 music dispatcher (unheld frames), by SND_MODE and the
; mailbox, in this order:
;  1. music bit edge (vs ay_mode): falling -> idle, player_stop, silence once;
;     rising -> force a restart of MUS_REQ at bar 1 (ay_loop = AY_LOOP_FORCE).
;     Music off (steady or falling): MUS_SHOT dropped, MUS_STATE = MS_IDLE (+ the
;     DONE bit kept), MUS_CUR 0, return at ~stub cost.
;  2. MUS_SHOT != 0: take it (clear), MUS_STATE = MS_SHOT (DONE cleared),
;     MUS_CUR = id, player_start; return WITHOUT player_frame (start ~3.1k T).
;  3. in MS_SHOT and player_done: MUS_STATE = MS_DONE (idle), restart the loop
;     (step 4 at once: ay_loop forced).
;  4. not in a shot, MUS_REQ != ay_loop: ay_loop = MUS_REQ; 0 (or an invalid
;     id > MUS_COUNT) -> idle + player_stop + silence; else player_start,
;     MS_LOOP, MUS_CUR = id; return.
;  5. else MS_LOOP / MS_SHOT -> player_frame; MS_IDLE -> return.
; ay_music_c: the same with C = SND_MODE already loaded (ay_play's fast path).
; Clobbers: AF, BC, DE, HL, IX.   Stack: 4 B below its return address.
; Cost (SND-2, incl. CALL/RET): idle 243 T, off 210 (falling edge 643), hold
; 291, start frame 3.3-3.5k (player_start ~3.1k), play frame = player_frame +
; ~0.25k (a shot + ~0.08k player_done); worst measured 5,194.
;------------------------------------------------------------------------------
ay_music:
                ld   a, (SND_MODE)              ; (the ISR is atomic: same value as ay_play read)
                ld   c, a                       ; C = the mode this frame
ay_music_c:     ld   hl, ay_mode
                ld   a, c
                xor  (hl)
                rra                             ; CY = the music bit changed
                jr   c, .edge
                ld   a, c
                rra                             ; CY = music on
                jr   nc, .off
.on:            ld   a, (MUS_SHOT)
                or   a
                jr   nz, .shot
                ld   a, (MUS_STATE)
                and  MS_MASK
                cp   MS_SHOT
                jr   z, .inshot
.req:           ld   a, (MUS_REQ)
                ld   hl, ay_loop
                cp   (hl)
                jr   nz, .change
                or   a                          ; same tune: 0 = idle (nothing sounds)
                ret  z
                jp   wzm.player_frame

.inshot:        call wzm.player_done
                jp   nz, wzm.player_frame       ; the shot plays on
                ld   a, MS_DONE                 ; finished: idle + DONE, and the loop
                ld   (MUS_STATE), a             ; (MUS_REQ) restarts at bar 1 now
                ld   a, AY_LOOP_FORCE
                ld   (ay_loop), a
                jr   .req

.change:        ld   (hl), a                    ; ay_loop follows MUS_REQ
                sub  MUS_FIRST                  ; id - 2: 0 / 1 -> $FE / $FF, > MUS_COUNT -> >= it
                cp   MUS_COUNT - MUS_FIRST + 1
                jr   nc, .stop
                ld   b, a
                ld   a, (MUS_STATE)
                and  MS_DONE                    ; a loop start keeps the last shot's DONE
                or   MS_LOOP
                jr   .start

.shot:          ld   b, a
                xor  a
                ld   (MUS_SHOT), a              ; taken (the ISR is the only clearer)
                ld   a, b
                sub  MUS_FIRST
                ld   b, a
                cp   MUS_COUNT - MUS_FIRST + 1
                ret  nc                         ; invalid id (1 = the removed Crawl): dropped
                ld   a, MS_SHOT                 ; DONE cleared: a new shot is running
                ; B = id - MUS_FIRST, A = the new MUS_STATE
.start:         ld   (MUS_STATE), a
                ld   a, b
                add  a, MUS_FIRST
                ld   (MUS_CUR), a
                ld   l, b
                ld   h, 0
                add  hl, hl
                ld   de, mus.mus_tab_first
                add  hl, de
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                jp   wzm.player_start           ; writes R0..R13; frame 0 next call

.edge:          ld   (hl), c                    ; ay_mode = this (unheld) mode
                ld   a, c
                rra
                jr   nc, .fall
                ld   a, AY_LOOP_FORCE           ; rising: MUS_REQ restarts at bar 1
                ld   (ay_loop), a               ; (not the old position: game.md §3.6)
                jr   .on

.fall:          xor  a                          ; falling edge: drop the shot, idle,
                ld   (MUS_SHOT), a              ; then silence once
.stop:          call .idle
                call wzm.player_stop            ; voices DONE: no stale note can resume
                jr   ay_silence

.off:           xor  a
                ld   (MUS_SHOT), a              ; one-shots are dropped while music is off
.idle:          ld   hl, MUS_STATE
                ld   a, (hl)
                and  MS_DONE
                ld   (hl), a                    ; MS_IDLE (+ DONE kept)
                inc  l
                ASSERT MUS_CUR == MUS_STATE + 1 && (MUS_CUR & $FF) != 0
                ld   (hl), 0                    ; MUS_CUR: nothing sounds
                ret


;------------------------------------------------------------------------------
; ay_silence — R8..R10 = 0 in the chip AND the wzm.pl_regs mirror (the player's
; R7 / mirror contract: no other register is touched, so no pl_out_all needed;
; player_frame rewrites R8..R10 on the next played frame).
; Clobbers: AF, BC, DE, HL.   ~0.15k T.
;------------------------------------------------------------------------------
ay_silence:
                ld   hl, 0
                ld   (wzm.pl_regs + AY_R_VOL_A), hl
                ld   a, l
                ld   (wzm.pl_regs + AY_R_VOL_A + 2), a
                ld   bc, AY_REG_PORT
                ld   de, (high AY_REG_PORT) << 8 | high AY_DATA_PORT
                ld   a, AY_R_VOL_A
                REPT 3                          ; unrolled: 36 T a register (loop ~58)
                out  (c), a
                ld   b, e
                out  (c), h                     ; H = 0
                ld   b, d
                inc  a
                ENDR
                ret
ay_play_end:

;------------------------------------------------------------------------------
; SND-5 sound effects, ISR side (docs/design/sound.md "SFX as built"). One
; effect at a time, on channel A = V1 (alto) only. While an effect plays,
; wzm.pl_regs R0/R1/R8 hold the EFFECT's values (the mirror stays the chip's
; image): sfx_step writes them before the music, player_frame (`WZM_SFX`)
; still sequences V1 every frame but does not store it, so the music's note
; comes back by itself on the first frame after the effect. player_frame then
; OUTs R0/R1/R8 with its own registers (no V1 glitch inside a frame), merges
; sfx_mix into R7 and ducks R9/R10 (prio >= SFX_DUCK_PRIO) in the mirror;
; frames without player_frame (music off / idle / start frame) get the OUTs
; from sfx_out. R6 (noise period) is OUT by sfx_step on each change and back
; to the mirror's 0 at the end. Never R2-R5 or R11-R13.
;------------------------------------------------------------------------------
SFX_CODE        EQU sfx_step
SFX_END         EQU $FF             ; frame byte: end of effect (sfx2asm.py)
SFXF_PIT_BIT    EQU 5               ; frame byte bits (>> 4: bit 1 / bit 2)
SFXF_NSE_BIT    EQU 6
SFX_MIX_A       EQU $09             ; R7 bit 0 tone A off, bit 3 noise A off
SFX_MIX_IDLE    EQU SFX_MIX_A & wzm.AY_MIXER_TONE   ; $08: the music's A bits
                ASSERT (wzm.AY_MIXER_TONE & SFX_MIX_A) == (wzm.AY_MIXER_BUZZ_C & SFX_MIX_A)
SFX_R_NOISE     EQU 6

;------------------------------------------------------------------------------
; sfx_step — take SFX_REQ (always cleared: taken or dropped), then advance the
; effect by one frame: sfx_vol / sfx_per into wzm.pl_regs R8 / R0-R1, sfx_mix,
; R6 OUT on a noise byte. SFX bit off (SND_MODE 0 / 1): any effect stops. A
; request replaces the effect playing if its priority is >= (or nothing
; plays); an invalid index is dropped. A new effect plays its frame 0 in the
; same ISR. At SFX_END (or stop): idle, vol 0, mix / R6 back to the music's.
; Clobbers: AF, BC, DE, HL.   ~0.35k T a frame (+ ~60 with a noise byte).
;------------------------------------------------------------------------------
sfx_step:
                ld   hl, 0
                ld   (sfx_ran), hl              ; player_frame sets it (non-zero) if it runs
                ld   hl, SFX_REQ
                ld   b, (hl)
                ld   (hl), 0                    ; the ISR is the only clearer
                ld   a, (SND_MODE)
                and  SND_SFX
                jp   z, .off                    ; (JP: out of JR range)
                ld   a, b
                or   a
                jr   z, .run
                and  SFX_PRIO_MASK
                ld   c, a                       ; C = the request's priority
                ld   a, (sfx_ptr + 1)
                or   a
                jr   z, .take                   ; nothing plays
                ld   a, c
                ld   hl, sfx_prio
                cp   (hl)
                jr   c, .defer                  ; lower than the effect playing
.take:          ld   a, b
                and  SFX_IDX_MASK
                dec  a
                cp   SFX_COUNT
                jr   nc, .run                   ; invalid: dropped
                ld   l, a
                ld   a, c
                ld   (sfx_prio), a
                cp   SFX_DUCK_PRIO
                ld   a, SFX_DUCK_HI
                jr   nc, .dk
                ld   a, SFX_DUCK_LO
.dk:            ld   (sfx_duck), a              ; the music's V2 / V3 duck while it plays
                ld   h, 0
                add  hl, hl
                ld   de, sfx_tab
                add  hl, de
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                jr   .frame
.run:           ld   hl, (sfx_ptr)
                ld   a, h
                or   a
                ret  z                          ; idle (effects live at $F000+: H != 0)
                jr   .frame
.defer:         ld   a, b                       ; prio >= SFX_DEFER_PRIO: after the effect
                cp   SFX_DEFER_PRIO             ; (one slot, SFX_NEXT); else dropped
                jr   c, .run
                ld   hl, SFX_NEXT               ; the slot keeps a higher-priority id
                xor  (hl)
                and  SFX_PRIO_MASK
                jr   z, .dst                    ; equal priority: the newer one
                ld   a, (hl)
                cp   b                          ; prios differ: id order = prio order
                jr   nc, .run
.dst:           ld   (hl), b
                jr   .run
.frame:         ld   a, (hl)
                inc  hl
                cp   SFX_END
                jr   z, .end
                ld   b, a
                and  $0F
                ld   (sfx_vol), a
                ld   (wzm.pl_regs + AY_R_VOL_A), a
                ld   a, b
                rrca
                rrca
                rrca
                rrca
                ld   c, a                       ; C bit 1 = pitch byte, bit 2 = noise byte
                and  SFX_MIX_A
                ld   (sfx_mix), a
                bit  SFXF_PIT_BIT - 4, c
                jr   z, .np
                ld   a, (hl)
                inc  hl
                ex   de, hl
                add  a, a                       ; HL = wzm.pl_tp[A] (the music's period table)
                add  a, low wzm.pl_tp
                ld   l, a
                adc  a, high wzm.pl_tp
                sub  l
                ld   h, a
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                ld   (sfx_per), hl
                ld   (wzm.pl_regs + 0), hl
                ex   de, hl
.np:            bit  SFXF_NSE_BIT - 4, c
                jr   z, .nn
                ld   a, (hl)
                inc  hl
.r6:            ld   (wzm.pl_regs + SFX_R_NOISE), a ; mirror == chip: a start frame's
                ld   bc, AY_REG_PORT            ; pl_out_all keeps it (R6 is not in
                ld   e, SFX_R_NOISE             ; player_frame's OUT set)
                out  (c), e
                ld   b, high AY_DATA_PORT
                out  (c), a
.nn:            ld   (sfx_ptr), hl
                ret
.off:           xor  a
                ld   (SFX_NEXT), a              ; SFX off: the deferred one goes too
                ld   a, (sfx_ptr + 1)
                or   a
                ret  z
                jr   .stop
.end:           ld   a, (SFX_NEXT)              ; a deferred effect: starts at once
                or   a
                jr   z, .stop
                ld   b, a
                xor  a
                ld   (SFX_NEXT), a
                ld   a, b
                and  SFX_PRIO_MASK
                ld   c, a
                jp   .take
.stop:          ld   hl, 0
                xor  a
                ld   (sfx_vol), a               ; sfx_out (no player_frame): V1 silent
                ld   (sfx_duck), a
                ld   a, SFX_MIX_IDLE
                ld   (sfx_mix), a               ; channel A back to the music's mixer bits
                xor  a                          ; R6 = the music's constant 0 (player_start /
                jr   .r6                        ; pl_out_all); sfx_ptr = 0: idle

;------------------------------------------------------------------------------
; sfx_out — after the music, on sfx_step's frames: if player_frame ran it has
; OUT R0/R1/R8 (and R7) already; else (music off / idle / held-over start
; frame) R0/R1 = sfx_per, R8 = sfx_vol into the mirror and OUT, R7 = mirror
; with sfx_mix. After an effect's end that is vol 0 (V1 silent with no music).
; Clobbers: AF, BC, DE, HL.   ~60 T after a player frame, ~0.25k T writing.
;------------------------------------------------------------------------------
sfx_out:
                ld   hl, (sfx_ran)
                ld   a, h
                or   l
                ret  nz
                ld   hl, (sfx_per)
                ld   (wzm.pl_regs + 0), hl
                ld   a, (sfx_vol)
                ld   (wzm.pl_regs + AY_R_VOL_A), a
                ld   e, a
                ld   bc, AY_REG_PORT
                xor  a
                out  (c), a                     ; R0
                ld   b, high AY_DATA_PORT
                out  (c), l
                ld   b, high AY_REG_PORT
                inc  a
                out  (c), a                     ; R1
                ld   b, high AY_DATA_PORT
                out  (c), h
                ld   b, high AY_REG_PORT
                ld   a, AY_R_VOL_A
                out  (c), a
                ld   b, high AY_DATA_PORT
                out  (c), e
                ld   hl, wzm.pl_regs + wzm.AY_R_MIXER
                ld   a, (hl)
                and  ~SFX_MIX_A & $FF
                ld   e, a
                ld   a, (sfx_mix)
                or   e
                ld   (hl), a                    ; mirror == chip
                ld   b, high AY_REG_PORT
                ld   e, wzm.AY_R_MIXER
                out  (c), e
                ld   b, high AY_DATA_PORT
                out  (c), a
                ret

;------------------------------------------------------------------------------
; sfx_dk — player_frame's ducking hook while any effect plays: A = sfx_duck
; (SFX_DUCK_LO 3, SFX_DUCK_HI 4 for prio >= 6): mirror R9 / R10 -= A, floor 0;
; an envelope-mode volume (bit 4, the V3 buzzer) is left (a fixed volume
; there would mute it: tone C is off on a buzzer frame). The music rewrites
; them every frame, so the duck ends with the effect.
; In: A = steps.  Clobbers: AF, E, HL.  ~0.13k T.
;------------------------------------------------------------------------------
sfx_dk:
                ld   e, a
                ld   hl, wzm.pl_regs + AY_R_VOL_A + 1
                call .duck
                inc  hl
.duck:          ld   a, (hl)
                cp   1 << wzm.AY_VOL_ENV_BIT
                ret  nc                         ; envelope mode: no fixed volume to duck
                sub  e
                jr   nc, .d
                xor  a
.d:             ld   (hl), a
                ret
sfx_code_end:

;------------------------------------------------------------------------------
; The player (MODULE wzm). Game configuration: the voice-C buzzer, no echo.
;------------------------------------------------------------------------------
                DEFINE WZM_BUZZER
                DEFINE WZM_SFX                  ; SND-5: the V1 / sfx_ran / sfx_dk / sfx_mix hooks
                INCLUDE "music/player.asm"

;------------------------------------------------------------------------------
; Dispatcher state — right after the player's state (wzm.pl_regs ..
; wzm.player_end), so ay_vars .. ay_vars_end is contiguous. Assembled values
; are the boot state: ay_mode 0 makes the first ay_play see a music-on edge
; (SND_MODE = SND_ALL), take MUS_REQ 0 and write silence (also clearing what
; 128 BASIC left in the AY).
;------------------------------------------------------------------------------
ay_mode:        DEFB 0                  ; SND_MODE of the last unheld frame (bit 0 used)
ay_loop:        DEFB 0                  ; the loop id ay_play started (MUS_REQ copy; AY_LOOP_FORCE)
; SND-5 effect state (runtime-written, inside ay_vars .. ay_vars_end)
sfx_ptr:        DEFW 0                  ; next frame of the effect playing; H = 0: none
sfx_prio:       DEFB 0                  ; its priority (id & SFX_PRIO_MASK)
sfx_duck:       DEFB 0                  ; duck steps for the music's V2 / V3 (0 = none)
sfx_per:        DEFW 0                  ; R0/R1 (carried between frames)
sfx_vol:        DEFB 0                  ; R8 (0 after the end)
sfx_mix:        DEFB SFX_MIX_IDLE       ; R7 bits 0 / 3 (idle = the music's)
sfx_ran:        DEFW 0                  ; non-zero: player_frame ran this ISR (sfx_step clears)
ay_vars_end:
ay_vars         EQU wzm.pl_regs
                ASSERT ay_mode == wzm.player_end
                ASSERT wzm.pl_regs < wzm.player_end && ay_vars_end - ay_vars == wzm.player_end - wzm.pl_regs + 2 + 10

;------------------------------------------------------------------------------
; Songs (MODULE mus): generated by tools/build.sh into OUTDIR/build/music_game/
; (-i search path). mus_tab_first: DW song block, id order MUS_FIRST .. MUS_LAMENT;
; mus_tab (EQU) = mus_tab_first - 2: mus_tab + 2 * (id - 1) for every id (no id 1).
;------------------------------------------------------------------------------
                MODULE mus
mus_songs:
                INCLUDE "game_songs.asm"
mus_songs_end:
                ENDMODULE

;------------------------------------------------------------------------------
; SND-5 effects: tools/sfx2asm.py (assets/sfx/effects.json) -> OUTDIR/build/sfx/
; (-i search path). sfx_tab: DW effect, stride 2, index order 1..SFX_COUNT.
;------------------------------------------------------------------------------
                INCLUDE "sfx_data.asm"
                ASSERT mus.mus_tab_end - mus.mus_tab_first == 2 * (MUS_COUNT - MUS_FIRST + 1) && mus.mus_tab == mus.mus_tab_first - 2 * (MUS_FIRST - 1)
                DISPLAY "GAME AY slot parts: ay_play ", /D, ay_play_end - ay_play, " B, player ", /D, wzm.PLAYER_LEN, " B (code+table ", /D, wzm.pl_regs - wzm.player_frame, ", state ", /D, wzm.player_end - wzm.pl_regs, "), dispatcher state ", /D, ay_vars_end - wzm.player_end, " B, songs ", /D, mus.mus_songs_end - mus.mus_songs, " B, sfx code ", /D, sfx_code_end - SFX_CODE, " B, sfx data ", /D, SFX_DATA_LEN, " B (", /D, SFX_COUNT, " effects); ay_vars ", /H, ay_vars, "..", /H, ay_vars_end - 1
