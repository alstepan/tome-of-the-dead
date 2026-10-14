;==============================================================================
; ay.asm — A8 AY player slot: bank 3, AY_RESERVE..AY_RESERVE_END (4 KB since
; D3-0, user 2026-10-06; game.md §11.2). SND-2 T2: the WZM v0.3 player
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
;   4. MODULE mus: the songs + mus_tab (DW song, in MUS_* id order 1..7)
;
; Slot contract (docs/conventions.md "Interrupts"): the IM 2 ISR (lowram.asm
; `isr`, running from bank 2) pages BANK_AY in by OUT only and calls AY_PLAY
; once per frame with interrupts disabled, then re-OUTs PORT_7FFD_SHADOW.
; ay_play clobbers AF, BC, DE, HL, IX (the ISR saves them + IY); no IY, no
; alternate set, no EI, no $7FFD / shadow writes, no $C000 data of other banks.
; Mailbox semantics: defs.asm (SND_MODE .. SFX_REQ), docs/memory-map.md.
;==============================================================================

;------------------------------------------------------------------------------
; ay_play — once per frame from the ISR. AY_CALLS += 1, then by SND_MODE and
; the mailbox, in this order:
;  1. SND_HOLD: silence R8-R10 (chip + wzm.pl_regs), drop MUS_SHOT, freeze —
;     ay_mode is NOT updated, so a music bit changed in the pause is seen as an
;     edge at release; unchanged = resume from the frozen position.
;  2. music bit edge (vs ay_mode): falling -> idle, player_stop, silence once;
;     rising -> force a restart of MUS_REQ at bar 1 (ay_loop = AY_LOOP_FORCE).
;     Music off (steady or falling): MUS_SHOT dropped, MUS_STATE = MS_IDLE (+ the
;     DONE bit kept), MUS_CUR 0, return at ~stub cost.
;  3. MUS_SHOT != 0: take it (clear), MUS_STATE = MS_SHOT (DONE cleared),
;     MUS_CUR = id, player_start; return WITHOUT player_frame (start ~3.1k T).
;  4. in MS_SHOT and player_done: MUS_STATE = MS_DONE (idle), restart the loop
;     (step 5 at once: ay_loop forced).
;  5. not in a shot, MUS_REQ != ay_loop: ay_loop = MUS_REQ; 0 (or an invalid
;     id > MUS_COUNT) -> idle + player_stop + silence; else player_start,
;     MS_LOOP, MUS_CUR = id; return.
;  6. else MS_LOOP / MS_SHOT -> player_frame; MS_IDLE -> return.
; Clobbers: AF, BC, DE, HL, IX.   Stack: 4 B below its return address.
; Cost (measured, ZEsarUX, incl. CALL/RET; docs/memory-map.md "Interrupts
; (A8)"): idle 243 T, off 210 (falling edge 643), hold 291, start frame
; 3.3-3.5k (player_start ~3.1k), play frame = player_frame + ~0.25k (a shot
; + ~0.08k player_done); worst measured 5,194.
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
                jp   c, .hold                   ; JP: out of JR range (+3 T)
                ld   hl, ay_mode
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
                dec  a                          ; id - 1: 0 -> $FF, > MUS_COUNT -> >= it
                cp   MUS_COUNT
                jr   nc, .stop
                ld   b, a
                ld   a, (MUS_STATE)
                and  MS_DONE                    ; a loop start keeps the last shot's DONE
                or   MS_LOOP
                jr   .start

.shot:          ld   b, a
                xor  a
                ld   (MUS_SHOT), a              ; taken (the ISR is the only clearer)
                dec  b
                ld   a, b
                cp   MUS_COUNT
                ret  nc                         ; invalid id: dropped
                ld   a, MS_SHOT                 ; DONE cleared: a new shot is running
                ; B = id - 1, A = the new MUS_STATE
.start:         ld   (MUS_STATE), a
                ld   a, b
                inc  a
                ld   (MUS_CUR), a
                ld   l, b
                ld   h, 0
                add  hl, hl
                ld   de, mus.mus_tab
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

.hold:          xor  a
                ld   (MUS_SHOT), a              ; dropped while held
                ; fall through: silence (every held frame, ~0.15k T; frozen state)

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
; The player (MODULE wzm). Game configuration: the voice-C buzzer, no echo.
;------------------------------------------------------------------------------
                DEFINE WZM_BUZZER
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
ay_vars_end:
ay_vars         EQU wzm.pl_regs
                ASSERT ay_mode == wzm.player_end
                ASSERT wzm.pl_regs < wzm.player_end && ay_vars_end - ay_vars == wzm.player_end - wzm.pl_regs + 2

;------------------------------------------------------------------------------
; Songs (MODULE mus): generated by tools/build.sh into OUTDIR/build/music_game/
; (-i search path). mus_tab: DW song block, id order MUS_CRAWL .. MUS_LAMENT.
;------------------------------------------------------------------------------
                MODULE mus
mus_songs:
                INCLUDE "game_songs.asm"
mus_songs_end:
                ENDMODULE
                ASSERT mus.mus_tab_end - mus.mus_tab == 2 * MUS_COUNT
                DISPLAY "GAME AY slot parts: ay_play ", /D, ay_play_end - ay_play, " B, player ", /D, wzm.PLAYER_LEN, " B (code+table ", /D, wzm.pl_regs - wzm.player_frame, ", state ", /D, wzm.player_end - wzm.pl_regs, "), dispatcher state ", /D, ay_vars_end - wzm.player_end, " B, songs ", /D, mus.mus_songs_end - mus.mus_songs, " B; ay_vars ", /H, ay_vars, "..", /H, ay_vars_end - 1
