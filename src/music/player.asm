;==============================================================================
; src/music/player.asm — WZM v0.3 AY-3-8912 music player core (SND-0 S1a, legato
; S1b, two-shift staccato gate + optional voice-C envelope buzzer S1d, release
; tail "reverb", 9/16 add-gate and triangle buzzer S1e)
;
; Format: tools/abc2wzm.py docstring (WZM v0.3). Oracle: tools/wzm_ref.py — this
; player must produce its 14-register image frame for frame (tests/music_player.py
; checks the RAM mirror for 1,024+ frames and the AY chip registers per frame).
; Tone only, no noise. Without WZM_BUZZER: mixer $38, no envelope, R13 never
; written. With `DEFINE WZM_BUZZER` before the INCLUDE: player_start writes R13 =
; song header +9 once; a voice-C volume with bit 4 set (envelope mode) also sets
; R11/R12 to the note's envelope period and R7 = $3C (tone C off) that frame; on
; any other frame R7 = $38 (a buzzer note's release tail is its square tone).
; The mirror's R13 holds $FF in both builds.
;
; Interface (all cold except player_frame):
;   player_start  HL = song block   (from the ISR / under DI) — also writes R0..R12
;   player_stop   end every voice   (idem): volume 0 from the next frame
;   player_done   Z = every voice has ended (END or player_stop)
;   player_frame  once per 50 Hz frame (ISR): sequence 3 voices, write R0..R5, R8..R10
;   pl_out_all    write R0..R12 from the mirror (cold; after anything else touched the AY)
;   pl_regs       14-B register mirror of the last frame (test hook, R0..R13)
;
; No fixed addresses: code, period table and voice state live in this file;
; placement in the game (bank 3 AY slot) is a later task. Clobbers AF, BC, DE,
; HL, IX only (the AY slot contract allows IY too); no alternate set, no EI.
; Everything is in MODULE wzm (names wzm.player_start, wzm.AY_R_MIXER, ...): the
; game's src/defs.asm has its own AY_* names.
;
; Speed notes (hot path = a sounding note at t > 0): the period of both the
; note (VO_PER) and its arp0 first frame (VO_PER0) is looked up once in
; pl_fetch, so a frame only picks one of the two; DONE and FIRST are tested with
; BIT on the flags byte. The output stage writes the 9 registers R0..R5, R8..R10,
; unrolled, 40 T a register. R6 is constant (0; player_start / pl_out_all).
; Without WZM_BUZZER R7 is constant $38 and R11/R12 stay 0. With WZM_BUZZER the
; buzzer block writes R7 ($3C on a buzzer frame, else $38) and R11/R12, each only
; when it changes. R7 mirror contract: anyone else who writes R7 (or any AY
; register) must call pl_out_all afterwards, or the mirror and the chip differ.
;==============================================================================
                MODULE wzm

; --- stream bytes (abc2wzm.py) ---
WZM_REST        EQU $60         ; $00..$5F note (pitch idx = MIDI-12), $60 rest; + dur byte
WZM_LOOP        EQU $80         ; + DEFW target
WZM_END         EQU $81
WZM_STAC_ON     EQU $82
WZM_STAC_OFF    EQU $83         ; anything else >= $61 ends the voice ($84 set-inst: reserved)
WZM_LEGATO      EQU $85         ; next note does not re-attack (v0.1)
WZM_PITCH_MAX   EQU $5F         ; top of the period table (arp0 clamps here)

; --- song header ---
WZM_H_STREAMS   EQU 0           ; 3 x DEFW
WZM_H_INST      EQU 6           ; 3 x DEFB instrument index per voice
WZM_H_SHAPE     EQU 9           ; DEFB R13 for the buzzer ($0C saw, $0E triangle; 0 none)
WZM_H_IPTRS     EQU 10          ; DEFW inst_0 ..

; --- instrument header (8 B, then volume table terminated by $FF) ---
INS_HDR_LEN     EQU 8           ; arp0, loop_idx, trem_per, trem_dep, drop, s1+1, s2', rel_per
WZM_VOL_END     EQU $FF         ; also loop_idx "hold last"
WZM_GATE_ADD    EQU 7           ; s2' bit 7: gate = round(dur >> s1) + (dur >> s2), s2' = s2

; --- AY ---
AY_PORT_SEL     EQU $FFFD
AY_PORT_DATA    EQU $BFFD
AY_MIXER_TONE   EQU $38         ; tone A/B/C on, noise off (bits 6/7 = 0: I/O ports input)
AY_MIXER_BUZZ_C EQU $3C         ; tone C off: voice C = the pure envelope (buzzer frame)
AY_REGS_OUT     EQU 13          ; R0..R12; R13 never (writing it restarts the envelope)
AY_R_MIXER      EQU 7
AY_R_VOL_A      EQU 8
AY_R_ENV_LO     EQU 11
AY_R_ENV_HI     EQU 12
AY_R_ENV_SHAPE  EQU 13
AY_VOL_ENV_BIT  EQU 4           ; volume bit 4: the channel follows the envelope
AY_ENV_ALT      EQU $02         ; R13 bit 1 (alternate): triangle, 32 steps a cycle
WZM_ECHO_PER    EQU 9           ; echo: -1 step every 9 frames (the tsx IR, 17.4 dB/s)
WZM_ECHO_BUZZ   EQU 14          ; echo of a buzzer note starts from its tsx level 14

; --- voice state (stride VO_SIZE). VO_ARP..VO_G8 = copy of the instrument header ---
VO_PTR          EQU 0           ; 2  stream pointer (next event)
VO_REM          EQU 2           ; 1  frames of the current event left AFTER this one
VO_PITCH        EQU 3           ; 1  pitch index (kept across rests / end, like the oracle)
VO_FLAGS        EQU 4           ; 1  VF_* bits
VO_GATE         EQU 5           ; 1  sustain frames left (0 = release phase)
VO_VOL          EQU 6           ; 1  last output volume (release starts from it)
VO_TPH          EQU 7           ; 1  tremolo phase = t mod trem_per
VO_VPTR         EQU 8           ; 2  -> volume table entry for frame t
VO_ARP          EQU 10          ; 1  instrument copy (same order as the INS header)
VO_LOOP         EQU 11
VO_TPER         EQU 12
VO_TDEP         EQU 13
VO_DROP         EQU 14          ; first release step (the dry cut)
VO_GS1          EQU 15          ; s1 + 1 } staccato gate (abc2wzm.py docstring). Data
VO_GS2          EQU 16          ; s2'    } contract: GS1 >= 1, GS2 & $7F >= 1 (DJNZ counts)
VO_RPER         EQU 17          ; frames per release step after the drop (the tail);
                                ; data contract: >= 1 (0 = a 256-frame step)
VO_TAB          EQU 18          ; 2  -> instrument volume table
VO_PER          EQU 20          ; 2  TP[pitch]
VO_PER0         EQU 22          ; 2  TP[min(pitch + arp0, $5F)]: frame t = 0 of an event
VO_RACC         EQU 24          ; 1  release countdown (a note sets 1: its first release
                                ;    frame steps; a rest keeps it: the tail runs on).
                                ;    player_start leaves it: harmless, VO_VOL = 0 until
                                ;    the first note, which sets it
        IFDEF WZM_ECHO
VO_EPER         EQU 25          ; 2  echo: the previous note's period
VO_ELVL         EQU 27          ; 1  echo level (0 = none)
VO_ECNT         EQU 28          ; 1  frames to the next echo decay step
VO_SIZE         EQU 29
        ELSE
VO_SIZE         EQU 25
        ENDIF

VF_DONE         EQU 0           ; voice ended (or stopped): period kept, volume 0
VF_TAIL         EQU 1           ; the release drop happened: further steps are -1
VF_STAC         EQU 2           ; staccato gate on (stream state, survives events)
VF_FIRST        EQU 3           ; this frame is t = 0 of an attacked note (period = VO_PER0).
                                ; Always clear when pl_fetch runs (frame 0 consumed it), so
                                ; the command scan reuses it as "legato pending" ($85)

;------------------------------------------------------------------------------
; PL_TP_HL — HL = pl_tp[A] (A = 0..$5F), inline (2 uses, saves CALL/RET 27 T).
; Clobbers AF.  54 T.
;------------------------------------------------------------------------------
PL_TP_HL        MACRO
                add  a, a
                add  a, low pl_tp
                ld   l, a
                adc  a, high pl_tp
                sub  l
                ld   h, a
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                ENDM

;------------------------------------------------------------------------------
; player_frame — one 50 Hz tick: sequence voices A/B/C into pl_regs, then write
; R10..R8, R5..R0 to the AY.
; In: —   Out: pl_regs updated.   Clobbers: AF, BC, DE, HL, IX.
; Cost (tests/music_player.py stage D, incl. CALL/RET; docs/design/sound.md §2
; "Measured"): see there. Output stage 9 x 40 + 52 = 412 T.
;------------------------------------------------------------------------------
        IFDEF WZM_ECHO
PL_VOICE        EQU pl_voice_e          ; time-shared echo wrapper (tape-only experiment)
        ELSE
PL_VOICE        EQU pl_voice
        ENDIF
player_frame:
        IFDEF WZM_ECHO
                ld   hl, pl_ephase      ; frame k of the song: k + 1 (bit 0 set = dry)
                inc  (hl)
        ENDIF
                ld   ix, pl_voice_a
                call PL_VOICE
                ld   (pl_regs + 0), hl
                ld   (pl_regs + AY_R_VOL_A + 0), a
                ld   ix, pl_voice_b
                call PL_VOICE
                ld   (pl_regs + 2), hl
                ld   (pl_regs + AY_R_VOL_A + 1), a
                ld   ix, pl_voice_c
                call PL_VOICE
                ld   (pl_regs + 4), hl
                ld   (pl_regs + AY_R_VOL_A + 2), a
        IFDEF WZM_BUZZER
                ; buzzer: an envelope-mode volume on voice C -> R11/R12 = (TP + 8) >> 4,
                ; the envelope period whose 16-step sawtooth has the note's frequency
                ; (a triangle has 32 steps a cycle: halved again, rounding up), and
                ; R7 = $3C; any other frame R7 = $38 (the release tail of a buzzer
                ; note is its square tone). R7 and R11/R12 are OUT only when they
                ; change (a held note keeps its period: ~0.1k T saved on most
                ; buzzer frames).
                bit  AY_VOL_ENV_BIT, a
                ld   a, AY_MIXER_TONE
                jr   z, .mix
                ld   de, 8
                add  hl, de
                REPT 4
                srl  h
                rr   l
                ENDR
                ld   a, (pl_etri)       ; per song (player_start): triangle?
                or   a
                jr   z, .saw
                inc  hl                 ; triangle: (e + 1) >> 1
                srl  h
                rr   l
.saw:           ld   a, (pl_regs + AY_R_ENV_LO)
                cp   l
                jr   nz, .env
                ld   a, (pl_regs + AY_R_ENV_HI)
                cp   h
                jr   z, .envok          ; same period as the mirror: no OUT
.env:           ld   (pl_regs + AY_R_ENV_LO), hl
                ld   bc, AY_PORT_SEL    ; written here: the output stage skips R11/R12
                ld   a, AY_R_ENV_HI
                out  (c), a
                ld   b, high AY_PORT_DATA
                out  (c), h
                ld   b, high AY_PORT_SEL
                dec  a
                out  (c), a
                ld   b, high AY_PORT_DATA
                out  (c), l
.envok:         ld   a, AY_MIXER_BUZZ_C
.mix:           ld   hl, pl_regs + AY_R_MIXER
                cp   (hl)
                jr   z, .nobuzz
                ld   (hl), a
                ld   bc, AY_PORT_SEL
                ld   e, AY_R_MIXER
                out  (c), e
                ld   b, high AY_PORT_DATA
                out  (c), a
.nobuzz:
        ENDIF
                ; R10..R8 then R5..R0. OUTD pre-decrements B: E = data port high + 1
                ld   hl, pl_regs + AY_R_VOL_A + 2
                ld   de, (high AY_PORT_SEL << 8) | (high AY_PORT_DATA + 1)
                ld   c, low AY_PORT_SEL
                ld   a, AY_R_VOL_A + 2
                REPT 3
                ld   b, d
                out  (c), a
                ld   b, e
                outd
                dec  a
                ENDR
                ld   a, 5               ; skip R7/R6 (R6 constant; R7: buzzer block above)
                dec  hl
                dec  hl
                REPT 6
                ld   b, d
                out  (c), a
                ld   b, e
                outd
                dec  a
                ENDR
                ret

        IFDEF WZM_ECHO
;------------------------------------------------------------------------------
; pl_voice_e — S1e EXPERIMENT (tape only, `DEFINE WZM_ECHO`): a time-shared "wet"
; signal. After a note change the voice keeps the previous note's period at its
; last level - pl_edrop (VO_ELVL, -1 every WZM_ECHO_PER frames); on odd frames of the
; song (and on every frame where the dry voice is silent) it plays that echo
; instead of the dry note. pl_edrop 0 = off (output == pl_voice).
; In: IX = voice.  Out: HL = period, A = volume.  Clobbers: AF, BC, DE, HL.
; Cost over pl_voice: 17 + ~45 T without an echo, ~0.1k T with one.
;------------------------------------------------------------------------------
pl_voice_e:
                call pl_voice
                ld   c, a               ; C = dry volume
                ld   a, (ix + VO_ELVL)
                or   a
                ld   b, a               ; B = echo level of this frame
                jr   z, .dry
                dec  (ix + VO_ECNT)
                jr   nz, .w
                ld   (ix + VO_ECNT), WZM_ECHO_PER
                dec  (ix + VO_ELVL)
.w:             ld   a, c
                or   a
                jr   z, .wet            ; the dry voice is silent: the echo has it
                ld   a, (pl_ephase)
                rra
                jr   c, .dry            ; even frame k: the dry note
.wet:           ld   l, (ix + VO_EPER)
                ld   h, (ix + VO_EPER + 1)
                ld   a, b
                ret
.dry:           ld   a, c
                ret
        ENDIF

;------------------------------------------------------------------------------
; pl_voice — advance one voice by one frame.
; In: IX = voice.  Out: HL = tone period, A = volume (0..15).
; Clobbers: AF, BC, DE, HL.
;------------------------------------------------------------------------------
pl_voice:
                ld   a, (ix + VO_REM)
                or   a
                jp   z, .fetch          ; JP: out of JR range (+3 T vs JR not taken)
                dec  a
                ld   (ix + VO_REM), a
.go:            bit  VF_DONE, (ix + VO_FLAGS)
                jp   nz, .silent        ; JP: out of JR range (30 T; v0.2 ld/and/jr 33)
                ld   a, (ix + VO_GATE)
                or   a
                jr   z, .release
                dec  a
                ld   (ix + VO_GATE), a
                ; sustain: C = table(t), then step the table pointer for t+1
                ld   l, (ix + VO_VPTR)
                ld   h, (ix + VO_VPTR + 1)
                ld   c, (hl)
                inc  hl
                ld   a, (hl)
                inc  a                  ; $FF terminator?
                jr   nz, .vstep
                ld   a, (ix + VO_LOOP)
                inc  a
                jr   z, .hold           ; loop_idx $FF: hold the last entry
                dec  a
                ld   l, (ix + VO_TAB)   ; wrap: tab + loop_idx
                ld   h, (ix + VO_TAB + 1)
                add  a, l
                ld   l, a
                adc  a, h
                sub  l
                ld   h, a
                jr   .vstep
.hold:          dec  hl
.vstep:         ld   (ix + VO_VPTR), l
                ld   (ix + VO_VPTR + 1), h
                ; tremolo: phase >= per/2 loses trem_dep (floor 0)
                ld   a, (ix + VO_TPER)
                or   a
                jr   z, .sust
                ld   b, a
                srl  a
                ld   e, a               ; E = per/2
                ld   a, (ix + VO_TPH)
                cp   e
                jr   c, .tnext
                ld   e, a
                ld   a, c
                sub  (ix + VO_TDEP)
                jr   nc, .tdip
                xor  a
.tdip:          ld   c, a
                ld   a, e
.tnext:         inc  a
                cp   b
                jr   c, .tph
                xor  a
.tph:           ld   (ix + VO_TPH), a
.sust:          ld   a, c
                jr   .setvol
                ; release (after the gate; every rest frame): the countdown steps the
                ; volume - first by VO_DROP (the dry cut), then by 1 every VO_RPER
                ; frames (the reverb tail, ~3 dB a step = exponential). 54 T on a
                ; frame without a step (v0.2 release: 50 T); a step frame ~0.15k T.
.release:       dec  (ix + VO_RACC)
                ld   a, (ix + VO_VOL)
                jr   nz, .setvol
                ld   c, (ix + VO_RPER)
                ld   (ix + VO_RACC), c
                bit  VF_TAIL, (ix + VO_FLAGS)
                jr   nz, .tstep
                set  VF_TAIL, (ix + VO_FLAGS)
                sub  (ix + VO_DROP)
                jr   nc, .setvol
                xor  a
                jr   .setvol
.tstep:         sub  1                  ; -1, floor 0
                adc  a, 0
.setvol:        ld   (ix + VO_VOL), a
.per:           bit  VF_FIRST, (ix + VO_FLAGS)
                jr   nz, .first
                ld   l, (ix + VO_PER)
                ld   h, (ix + VO_PER + 1)
                ret
.first:         res  VF_FIRST, (ix + VO_FLAGS)
                ld   l, (ix + VO_PER0)
                ld   h, (ix + VO_PER0 + 1)
                ret
.silent:        xor  a                  ; ended: volume 0, period kept
                jr   .per
.fetch:         bit  VF_DONE, (ix + VO_FLAGS)
                jr   nz, .silent        ; FIRST is clear on an ended voice
                call pl_fetch
                jp   .go                ; out of JR range; once per event

;------------------------------------------------------------------------------
; pl_fetch — read the next note/rest of a voice (commands are consumed in the
; same frame). Sets VF_DONE on END (or any byte >= $61 that is not a known
; command). A note computes gate and VO_PER and restarts the release (VO_RACC 1,
; VF_TAIL clear); an attacked note also resets the volume envelope and sets
; VO_PER0 (arp0 frame); a legato note ($85 before it) keeps the envelope running
; and has no arp0 frame. A rest keeps pitch, VO_PER and the release state with
; gate 0: the previous note's tail runs on through it.
; VO_REM = dur - 1 (the current frame is the event's first).
; In: IX = voice.  Clobbers: AF, BC, DE, HL.
;------------------------------------------------------------------------------
pl_fetch:
                ld   l, (ix + VO_PTR)
                ld   h, (ix + VO_PTR + 1)
.next:          ld   a, (hl)
                inc  hl
                cp   WZM_REST + 1
                jr   c, .event
                ; commands, most frequent first (staccato switches, legato)
                cp   WZM_LEGATO
                jr   z, .leg
                cp   WZM_STAC_OFF
                jr   z, .soff
                cp   WZM_STAC_ON
                jr   z, .son
                cp   WZM_LOOP
                jr   nz, .end           ; $81 END, $84 and anything invalid
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                jr   .next
.leg:           set  VF_FIRST, (ix + VO_FLAGS)  ; legato pending (see .event)
                jr   .next
.soff:          res  VF_STAC, (ix + VO_FLAGS)
                jr   .next
.son:           set  VF_STAC, (ix + VO_FLAGS)
                jr   .next
.end:           set  VF_DONE, (ix + VO_FLAGS)
                ret
.event:         ld   c, (hl)            ; C = dur frames
                inc  hl
                ld   (ix + VO_PTR), l
                ld   (ix + VO_PTR + 1), h
                ld   b, c
                dec  b
                ld   (ix + VO_REM), b
                cp   WZM_REST
                jr   nz, .note
                ld   a, (ix + VO_FLAGS) ; rest: no attack frame; period, STAC and the
                and  (1 << VF_STAC) | (1 << VF_TAIL)   ; release state kept
                ld   (ix + VO_FLAGS), a
                ld   (ix + VO_GATE), 0
                ret
.note:          ld   (ix + VO_PITCH), a
                ld   b, a               ; B = pitch (cheaper than re-reading VO_PITCH)
                ld   a, (ix + VO_FLAGS)
                and  (1 << VF_STAC) | (1 << VF_FIRST)
                xor  1 << VF_FIRST      ; FIRST = attack = NOT legato pending
                ld   e, a               ; E = new flags (STAC kept, TAIL clear)
                ld   (ix + VO_FLAGS), a
                ld   a, b
                PL_TP_HL
        IFDEF WZM_ECHO
                ; echo: remember the previous note (period, last level - pl_edrop);
                ; none if off, or if the pitch repeats. ~0.15k T a note fetch.
                ld   a, (pl_edrop)
                or   a
                jr   z, .eoff
                ld   d, a
                ld   a, (ix + VO_PER)
                cp   l
                jr   nz, .eon
                ld   a, (ix + VO_PER + 1)
                cp   h
                jr   z, .eoff
.eon:           ld   a, (ix + VO_PER)
                ld   (ix + VO_EPER), a
                ld   a, (ix + VO_PER + 1)
                ld   (ix + VO_EPER + 1), a
                ld   a, (ix + VO_VOL)
                cp   1 << AY_VOL_ENV_BIT
                jr   c, .elv
                ld   a, WZM_ECHO_BUZZ   ; a buzzer note counts as its tsx level
.elv:           sub  d
                jr   nc, .eset
.eoff:          xor  a
.eset:          ld   (ix + VO_ELVL), a
                ld   (ix + VO_ECNT), WZM_ECHO_PER
        ENDIF
                ld   (ix + VO_PER), l
                ld   (ix + VO_PER + 1), h
                ld   (ix + VO_RACC), 1  ; the first release frame steps (by VO_DROP)
                bit  VF_FIRST, e
                jr   z, .stgate         ; legato: volume table and tremolo run on
                ld   l, (ix + VO_TAB)
                ld   h, (ix + VO_TAB + 1)
                ld   (ix + VO_VPTR), l
                ld   (ix + VO_VPTR + 1), h
                ld   (ix + VO_TPH), 0
.stgate:        ld   a, c
                bit  VF_STAC, e
                jr   z, .gate
                ; staccato gate (the converter guarantees >= 1), only on a staccato
                ; note's fetch. s2' bit 7 clear: (dur >> s1) - (dur >> s2), s2' = s2 - s1
                ; ((0,1) = 50 % rounded up, (1,4) = 7/16, the tsx's 45 %; (0,8) = dur,
                ; the 100 % gate: the same path, 8 shifts, ~250 T), ~165 T.
                ; Bit 7 set (s1 >= 1): round-half-up(dur >> s1) + (dur >> s2), s2' = s2
                ; ((1,4) = 9/16 ~ 56 %, (1,3) = 5/8), ~200 T.
                ld   b, (ix + VO_GS1)   ; s1 + 1
                jr   .g1e
.g1:            srl  a
.g1e:           djnz .g1
                ld   d, a               ; D = dur >> s1, CY = the last bit shifted out
                ld   b, (ix + VO_GS2)
                bit  WZM_GATE_ADD, b    ; (BIT keeps CY)
                jr   nz, .gadd
.g2:            srl  a
                djnz .g2
                neg
                add  a, d
                jr   .gate
.gadd:          adc  a, 0               ; round half up
                ld   d, a
                res  WZM_GATE_ADD, b    ; B = s2
                ld   a, c
.g3:            srl  a
                djnz .g3
                add  a, d
.gate:          ld   (ix + VO_GATE), a
                ld   a, (ix + VO_PITCH)
                ; fall through (a legato note computes an unused VO_PER0: cheaper in
                ; bytes than a test, and no dearer than the envelope reset it skips)
; pl_per0 — VO_PER0 = TP[min(A + arp0, $5F)].  Clobbers AF, HL.
pl_per0:
                add  a, (ix + VO_ARP)
                jr   c, .clamp
                cp   WZM_PITCH_MAX + 1
                jr   c, .ok
.clamp:         ld   a, WZM_PITCH_MAX
.ok:            PL_TP_HL
                ld   (ix + VO_PER0), l
                ld   (ix + VO_PER0 + 1), h
                ret


;------------------------------------------------------------------------------
; player_start — start a song from frame 0 (next player_frame plays frame 0) and
; write R0..R12 (the per-song constant R6/R7/R11/R12 are written here; with
; WZM_BUZZER also R7 = $38, R11/R12 = 0 and R13 = the header's shape).
; In: HL = song block.  Clobbers: AF, BC, DE, HL, IX.  Cold (~1.9k T).
; Must not race player_frame: call from the ISR (mailbox) or under DI.
;------------------------------------------------------------------------------
player_start:
                ld   (pl_song), hl
                ld   ix, pl_voice_a
                ld   bc, 0              ; C = voice v, B = 0 for the ADD HL,BC
.voice:         ld   hl, (pl_song)
                add  hl, bc
                add  hl, bc             ; header + 2v: stream pointer
                ld   a, (hl)
                ld   (ix + VO_PTR), a
                inc  hl
                ld   a, (hl)
                ld   (ix + VO_PTR + 1), a
                ld   hl, (pl_song)
                add  hl, bc
                ld   de, WZM_H_INST
                add  hl, de
                ld   e, (hl)            ; DE = instrument index (D = 0)
                ld   hl, (pl_song)
                add  hl, de
                add  hl, de
                ld   e, WZM_H_IPTRS
                add  hl, de             ; header + 10 + 2*idx
                ld   e, (hl)
                inc  hl
                ld   d, (hl)            ; DE = instrument
                push bc
                push ix
                pop  hl
                ld   bc, VO_ARP
                add  hl, bc
                ex   de, hl             ; HL = instrument, DE = voice + VO_ARP
                ld   bc, INS_HDR_LEN
                ldir                    ; HL = volume table, DE = voice + VO_TAB
                ex   de, hl
                ld   (hl), e
                inc  hl
                ld   (hl), d
                pop  bc
                xor  a
                ld   (ix + VO_REM), a
                ld   (ix + VO_PITCH), a
                ld   (ix + VO_FLAGS), a
                ld   (ix + VO_VOL), a   ; a leading rest releases from 0
        IFDEF WZM_ECHO
                ld   (ix + VO_ELVL), a  ; no echo across songs
                ld   (pl_ephase), a     ; frame k sees k + 1: k even = dry, odd = echo
        ENDIF
                ld   hl, (pl_tp)        ; pitch 0: a leading rest / END keeps TP[0]
                ld   (ix + VO_PER), l
                ld   (ix + VO_PER + 1), h
                ld   de, VO_SIZE
                add  ix, de
                inc  c
                ld   a, c
                cp   3
                jr   c, .voice
        IFDEF WZM_BUZZER
                ld   hl, (pl_song)      ; R7 = $38, R11/R12 = 0 until a buzzer frame;
                ld   de, WZM_H_SHAPE    ; R13 = the header's shape once (writing R13
                add  hl, de             ; restarts the envelope: never per frame)
                ld   a, (hl)
                ld   d, a               ; D = R13
                and  AY_ENV_ALT
                ld   (pl_etri), a       ; per-song triangle flag for player_frame
                ld   hl, AY_MIXER_TONE
                ld   (pl_regs + AY_R_MIXER), hl     ; R7 = $38, R8 = 0 (rewritten per frame)
                ld   l, h
                ld   (pl_regs + AY_R_ENV_LO), hl
                ld   bc, AY_PORT_SEL
                ld   e, AY_R_ENV_SHAPE
                out  (c), e
                ld   b, high AY_PORT_DATA
                out  (c), d
        ENDIF
                ; fall through: constant registers + the current mirror
                ASSERT VO_TAB == VO_ARP + INS_HDR_LEN

;------------------------------------------------------------------------------
; pl_out_all — write R12..R0 from pl_regs.  Clobbers: AF, BC, HL.  ~0.75k T.
;------------------------------------------------------------------------------
pl_out_all:
                ld   hl, pl_regs + AY_REGS_OUT - 1
                ld   a, AY_REGS_OUT - 1
                ld   c, low AY_PORT_SEL
.reg:           ld   b, high AY_PORT_SEL
                out  (c), a
                ld   b, high AY_PORT_DATA + 1
                outd
                dec  a
                jp   p, .reg
                ret

;------------------------------------------------------------------------------
; player_done — have all three voices ended (END / player_stop)?
; Out: Z = all ended (silent), NZ = still playing.  Clobbers: AF, HL.  ~60 T.
;------------------------------------------------------------------------------
player_done:
                ld   hl, pl_voice_a + VO_FLAGS
                ld   a, (hl)
                ld   hl, pl_voice_b + VO_FLAGS
                and  (hl)
                ld   hl, pl_voice_c + VO_FLAGS
                and  (hl)
                cpl
                and  1 << VF_DONE
                ret

;------------------------------------------------------------------------------
; player_stop — end every voice now (period kept, volume 0 from the next frame).
; Clobbers: AF, B, HL.
;------------------------------------------------------------------------------
player_stop:
                ld   hl, pl_voice_a + VO_FLAGS
                ld   b, 3
.v:             set  VF_DONE, (hl)
                ld   a, l
                add  a, VO_SIZE
                ld   l, a
                adc  a, h
                sub  l
                ld   h, a
                djnz .v
                ret

;------------------------------------------------------------------------------
; pl_tp — AY tone period per pitch index (MIDI-12), equal temperament A4 = 440,
; AY clock 1,773,400 Hz, clamped 1..4095. Same values as wzm_ref.TP (checked
; frame by frame by tests/music_player.py). Stride 2.
;------------------------------------------------------------------------------
pl_tp:
                DEFW 4095, 4095, 4095, 4095, 4095, 4095, 4095, 4095   ; idx $00..
                DEFW 4095, 4030, 3804, 3591, 3389, 3199, 3019, 2850   ; idx $08..
                DEFW 2690, 2539, 2397, 2262, 2135, 2015, 1902, 1795   ; idx $10..
                DEFW 1695, 1599, 1510, 1425, 1345, 1270, 1198, 1131   ; idx $18..
                DEFW 1068, 1008,  951,  898,  847,  800,  755,  712   ; idx $20..
                DEFW  673,  635,  599,  566,  534,  504,  476,  449   ; idx $28..
                DEFW  424,  400,  377,  356,  336,  317,  300,  283   ; idx $30..
                DEFW  267,  252,  238,  224,  212,  200,  189,  178   ; idx $38..
                DEFW  168,  159,  150,  141,  133,  126,  119,  112   ; idx $40..
                DEFW  106,  100,   94,   89,   84,   79,   75,   71   ; idx $48..
                DEFW   67,   63,   59,   56,   53,   50,   47,   45   ; idx $50..
                DEFW   42,   40,   37,   35,   33,   31,   30,   28   ; idx $58..
                ASSERT $ - pl_tp == 2 * (WZM_PITCH_MAX + 1)

;------------------------------------------------------------------------------
; Player state. pl_regs = the AY register image of the last frame (test hook):
; R0..R5 tone A/B/C, R6 noise 0, R7 mixer $38 ($3C on a buzzer frame), R8..R10
; volume, R11/R12 envelope period (0 until a buzzer frame), R13 $FF (the mirror
; never tracks R13; player_start writes the song's shape to the chip once).
;------------------------------------------------------------------------------
pl_regs:        DEFB 0, 0, 0, 0, 0, 0, 0, AY_MIXER_TONE, 0, 0, 0, 0, 0, $FF
pl_voice_a:     DEFB 0, 0, 0, 0, 1 << VF_DONE
                DS   VO_SIZE - 5, 0
pl_voice_b:     DEFB 0, 0, 0, 0, 1 << VF_DONE
                DS   VO_SIZE - 5, 0
pl_voice_c:     DEFB 0, 0, 0, 0, 1 << VF_DONE
                DS   VO_SIZE - 5, 0
                ASSERT pl_voice_b - pl_voice_a == VO_SIZE
pl_song:        DEFW 0                  ; song block (player_start scratch)
        IFDEF WZM_BUZZER
pl_etri:        DEFB 0                  ; current song: R13 & AY_ENV_ALT (non-zero = triangle)
        ENDIF
        IFDEF WZM_ECHO
pl_edrop:       DEFB 0                  ; echo level below the old note (0 = off; runtime)
pl_ephase:      DEFB 0                  ; frame counter (bit 0: parity)
        ENDIF
player_end:
PLAYER_CODE_LEN EQU pl_tp - player_frame
PLAYER_LEN      EQU player_end - player_frame
                ENDMODULE
