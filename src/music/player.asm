;==============================================================================
; src/music/player.asm — WZM v0.2 AY-3-8912 music player core (SND-0 S1a, legato
; S1b, two-shift staccato gate + optional voice-C envelope buzzer S1d)
;
; Format: tools/abc2wzm.py docstring (WZM v0.2). Oracle: tools/wzm_ref.py — this
; player must produce its 14-register image frame for frame (tests/music_player.py
; checks the RAM mirror for 1,024+ frames and the AY chip registers per frame).
; Tone only, no noise. Without WZM_BUZZER: mixer $38, no envelope, R13 never
; written. With `DEFINE WZM_BUZZER` before the INCLUDE (experimental, S1d (6)):
; player_start takes R7 from the song header and writes R13 = WZM_ENV_SHAPE once;
; a voice-C volume with bit 4 set (envelope mode) also sets R11/R12 to the note's
; envelope period that frame. The mirror's R13 holds $FF in both builds.
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
;
; Speed notes (hot path = a sounding note at t > 0): the period of both the
; note (VO_PER) and its arp0 first frame (VO_PER0) is looked up once in
; pl_fetch, so a frame only picks one of the two; DONE / REST / FIRST share one
; flags byte tested once; the output stage writes the 9 registers that can
; change (R6/R7/R11/R12 are constant per song and written by player_start;
; only a buzzer frame changes R11/R12, and writes them itself), unrolled,
; 40 T a register.
;==============================================================================

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
WZM_H_MIXER     EQU 9           ; DEFB R7 ($38; $3C = tone C off for the buzzer)
WZM_H_IPTRS     EQU 10          ; DEFW inst_0 ..

; --- instrument header (7 B, then volume table terminated by $FF) ---
INS_HDR_LEN     EQU 7           ; arp0, loop_idx, trem_per, trem_dep, rel_step, s1+1, s2-s1
WZM_VOL_END     EQU $FF         ; also loop_idx "hold last"

; --- AY ---
AY_PORT_SEL     EQU $FFFD
AY_PORT_DATA    EQU $BFFD
AY_MIXER_TONE   EQU $38         ; tone A/B/C on, noise off (bits 6/7 = 0: I/O ports input)
AY_REGS_OUT     EQU 13          ; R0..R12; R13 never (writing it restarts the envelope)
AY_R_MIXER      EQU 7
AY_R_VOL_A      EQU 8
AY_R_ENV_LO     EQU 11
AY_R_ENV_HI     EQU 12
AY_R_ENV_SHAPE  EQU 13
AY_VOL_ENV_BIT  EQU 4           ; volume bit 4: the channel follows the envelope
WZM_ENV_SHAPE   EQU $0C         ; repeating rising sawtooth ////

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
VO_REL          EQU 14
VO_GS1          EQU 15          ; s1 + 1 } staccato gate = (dur >> s1) - (dur >> s2)
VO_GS2          EQU 16          ; s2 - s1 }
VO_TAB          EQU 17          ; 2  -> instrument volume table
VO_PER          EQU 19          ; 2  TP[pitch]
VO_PER0         EQU 21          ; 2  TP[min(pitch + arp0, $5F)]: frame t = 0 of an event
VO_SIZE         EQU 23

VF_DONE         EQU 0           ; voice ended (or stopped): period kept, volume 0
VF_REST         EQU 1           ; current event is a rest
VF_STAC         EQU 2           ; staccato gate on (stream state, survives events)
VF_FIRST        EQU 3           ; this frame is t = 0 of an attacked note (period = VO_PER0).
                                ; Always clear when pl_fetch runs (frame 0 consumed it), so
                                ; the command scan reuses it as "legato pending" ($85)
VFM_SILENT      EQU (1 << VF_DONE) | (1 << VF_REST)

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
player_frame:
                ld   ix, pl_voice_a
                call pl_voice
                ld   (pl_regs + 0), hl
                ld   (pl_regs + AY_R_VOL_A + 0), a
                ld   ix, pl_voice_b
                call pl_voice
                ld   (pl_regs + 2), hl
                ld   (pl_regs + AY_R_VOL_A + 1), a
                ld   ix, pl_voice_c
                call pl_voice
                ld   (pl_regs + 4), hl
                ld   (pl_regs + AY_R_VOL_A + 2), a
        IFDEF WZM_BUZZER
                ; buzzer: an envelope-mode volume on voice C -> R11/R12 = (TP + 8) >> 4,
                ; the envelope period whose 16-step sawtooth has the note's frequency.
                ; 20 T on every other frame, 206 T on a buzzer frame; 47 B.
                bit  AY_VOL_ENV_BIT, a
                jr   z, .nobuzz
                ld   de, 8
                add  hl, de
                REPT 4
                srl  h
                rr   l
                ENDR
                ld   (pl_regs + AY_R_ENV_LO), hl
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
                ld   a, 5               ; skip R7/R6 (constant)
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
.go:            ld   a, (ix + VO_FLAGS)
                and  VFM_SILENT
                jr   nz, .silent
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
.release:       ld   a, (ix + VO_VOL)   ; vol(gate-1) - rel*(t-gate+1), floor 0
                sub  (ix + VO_REL)
                jr   nc, .setvol
                xor  a
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
.silent:        xor  a                  ; rest / ended: volume 0, period kept
                jr   .per
.fetch:         bit  VF_DONE, (ix + VO_FLAGS)
                jr   nz, .silent        ; FIRST is clear on an ended voice
                call pl_fetch
                jp   .go                ; out of JR range; once per event

;------------------------------------------------------------------------------
; pl_fetch — read the next note/rest of a voice (commands are consumed in the
; same frame). Sets VF_DONE on END (or any byte >= $61 that is not a known
; command). A note computes gate and VO_PER; an attacked note also resets the
; volume envelope and sets VO_PER0 (arp0 frame); a legato note ($85 before it)
; keeps the envelope running and has no arp0 frame. A rest keeps pitch and VO_PER.
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
                ld   b, a               ; B = pitch / WZM_REST
                ld   a, (ix + VO_FLAGS)
                and  (1 << VF_STAC) | (1 << VF_FIRST)
                xor  1 << VF_FIRST      ; FIRST = attack = NOT legato pending
                ld   e, a               ; E = new flags (STAC kept)
                ld   a, b
                cp   WZM_REST
                jr   nz, .note
                ld   a, e               ; rest: no attack frame, period kept
                and  1 << VF_STAC
                or   1 << VF_REST
                ld   (ix + VO_FLAGS), a
                ret
.note:          ld   (ix + VO_PITCH), a
                ld   (ix + VO_FLAGS), e
                PL_TP_HL
                ld   (ix + VO_PER), l
                ld   (ix + VO_PER + 1), h
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
                ; staccato gate = (dur >> s1) - (dur >> s2), s1 >= 0, s2 > s1 (the
                ; converter guarantees >= 1). (0,1) = 50 % rounded up, (1,4) = 7/16 (the
                ; tsx's 45 %): ~150 T, only on a staccato note's fetch.
                ld   b, (ix + VO_GS1)   ; s1 + 1
                jr   .g1e
.g1:            srl  a
.g1e:           djnz .g1
                ld   d, a               ; D = dur >> s1
                ld   b, (ix + VO_GS2)   ; s2 - s1
.g2:            srl  a
                djnz .g2
                neg
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
; WZM_BUZZER also R7 from the header, R11/R12 = 0 and R13 = WZM_ENV_SHAPE).
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
                ld   hl, (pl_song)      ; R7 from the header; R11/R12 = 0 until a buzzer
                ld   de, WZM_H_MIXER    ; frame; R13 = sawtooth once (writing R13
                add  hl, de             ; restarts the envelope: never per frame)
                ld   a, (hl)
                ld   (pl_regs + AY_R_MIXER), a
                ld   hl, 0
                ld   (pl_regs + AY_R_ENV_LO), hl
                ld   bc, AY_PORT_SEL
                ld   a, AY_R_ENV_SHAPE
                out  (c), a
                ld   b, high AY_PORT_DATA
                ld   a, WZM_ENV_SHAPE
                out  (c), a
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
; R0..R5 tone A/B/C, R6 noise 0, R7 mixer $38, R8..R10 volume, R11/R12 0,
; R13 $FF (never written to the AY).
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
player_end:
PLAYER_CODE_LEN EQU pl_tp - player_frame
PLAYER_LEN      EQU player_end - player_frame
