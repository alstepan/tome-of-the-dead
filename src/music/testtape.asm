;==============================================================================
; src/music/testtape.asm — SND-0 STANDALONE music test tape (not the game), S1e
;
;   tools/build_music_test.sh  ->  build/music_test.tap (auto-runs from 128
;   BASIC: CLEAR / LOAD "" CODE / RANDOMIZE USR) and build/music_test.sna.
;
; Plays the WZM v0.3 songs emitted by tools/abc2wzm.py --batch build/music (from
; the tsx JSON sources assets/sfx/music/src) with src/music/player.asm (buzzer
; assembled in), driven from an IM 2 ISR at 50 Hz. Key map (docs/design/sound.md
; S1e): 1..7 = the 7 tunes as GOTHIC ORGAN + reverb tail, Q..U = the same as
; HARPSICHORD + reverb tail (tsx-max tempo), 8 / 9 = the S1d tsx-faithful Lament
; at 74 / 96 bpm (no reverb); 0 / I = the tsx's pure-legato Lament II as organ /
; harpsichord + reverb (96), O / P = Lament II tsx-faithful 74 / 96 (no reverb).
; G cycles the current song's staccato gate 30 -> 45 -> 56 -> 62 -> 100 % and H its
; reverb tail S1e -> 0 -> 50 -> 100 % (organ / harpsichord entries only); both patch
; the song's instrument bytes in RAM and restart it. J cycles the global echo
; EXPERIMENT (WZM_ECHO) off -> 25 -> 50 -> 100 %. L restarts, SPACE stops.
; Screen: menu, then title, mode, gate, frame counter and state of the current song.
;
; Test hooks (tests/music_player.py, ZRCP): tt_req (mailbox, 1..TT_SONGS = start
; song n, TT_REQ_STOP = stop), tt_state, tt_frames, tt_song; the ISR appends the
; 14-B register mirror pl_regs of every played frame to the ring TT_LOG (bank 0
; at $C000; frame k of the current song -> slot k mod TT_LOG_FRAMES).
;
; Layout (all private to this tape; docs/memory-map.md is the GAME's map):
;   $8000..        code + player + song data (bank 2, uncontended)
;   TT_VEC  $BE00  IM 2 vector table (257 x TT_VEC_BYTE), built at start
;   TT_ISR  $BFBF  JP tt_isr
;   stack below TT_VEC;  TT_LOG $C000 bank 0 (log, 14,336 B)
;==============================================================================
                DEVICE ZXSPECTRUM128

; Player configuration: the buzzer always (organ triangle / harpsichord saw on
; voice C); the time-shared echo experiment (key J) unless WZM_NO_ECHO is defined
; (tools/build_music_test.sh WZM_ECHO=0: the game configuration).
                DEFINE WZM_BUZZER
        IFNDEF WZM_NO_ECHO
                DEFINE WZM_ECHO
        ENDIF

TT_ORG          EQU $8000
TT_VEC          EQU $BE00
TT_VEC_BYTE     EQU $BF
TT_ISR          EQU (TT_VEC_BYTE << 8) | TT_VEC_BYTE   ; $BFBF
TT_STACK        EQU TT_VEC
TT_LOG          EQU $C000
TT_LOG_FRAMES   EQU 1024
TT_LOG_END      EQU TT_LOG + TT_LOG_FRAMES * 14
                ASSERT TT_LOG_END < $10000

PORT_7FFD       EQU $7FFD
TT_7FFD         EQU $10             ; bank 0 at $C000, screen 5, ROM 1 (48 BASIC: font)
ROM_FONT        EQU $3C00           ; char c at ROM_FONT + 8c (32..127)
SCREEN          EQU $4000
ATTRS           EQU $5800
ATTR_NORMAL     EQU $47             ; bright white on black
ATTR_CUR        EQU $46             ; bright yellow on black: current song row
ATTR_HEAD       EQU $45             ; bright cyan

TT_REQ_STOP     EQU $FF             ; scan_keys / mailbox: SPACE
TT_KEY_RESTART  EQU $FE             ; scan_keys: L (never a mailbox value)
TT_KEY_GATE     EQU $FD             ; scan_keys: G (never a mailbox value)
TT_KEY_REVERB   EQU $FC             ; scan_keys: H (never a mailbox value)
TT_KEY_ECHO     EQU $FB             ; scan_keys: J (never a mailbox value)
TT_ENTRY        EQU 8               ; song_tab: DW song, DW title, DW mode, DB menu row, DB 0
ST_IDLE         EQU 0
ST_PLAYING      EQU 1
ST_ENDED        EQU 2
ST_STOPPED      EQU 3

INS_GATE        EQU 5               ; instrument header +5/+6: the gate bytes (WZM v0.3)
GATE_N          EQU 5               ; gate_tab entries
INS_DROP        EQU 4               ; instrument header +4: release drop (WZM v0.3)
INS_RPER        EQU 7               ; instrument header +7: tail step period
INS_VOLS        EQU 8               ; instrument header +8: volume table ($10 = buzzer)
REV_N           EQU 4               ; rev_tab levels per kind
SHAPE_TRI       EQU $0E             ; song header +9: organ (triangle pedal)
SHAPE_SAW       EQU $0C             ; harpsichord (saw bass); 0 = dry entry

MENU_ROW        EQU 3               ; first tune row
STAT_ROW        EQU 20

; screen address of character cell (row, col)
SCR             MACRO row, col
                ld   de, SCREEN + ((row & $18) << 8) + ((row & 7) << 5) + col
                ENDM

                ORG  TT_ORG
start:
                di
                ld   sp, TT_STACK
                ld   a, TT_7FFD
                ld   bc, PORT_7FFD
                out  (c), a
                ; IM 2: 257-byte vector table + JP at TT_ISR
                ld   hl, TT_VEC
                ld   de, TT_VEC + 1
                ld   bc, 256
                ld   (hl), TT_VEC_BYTE
                ldir
                ld   a, $C3
                ld   (TT_ISR), a
                ld   hl, tt_isr
                ld   (TT_ISR + 1), hl
                ld   a, high TT_VEC
                ld   i, a
                im   2
                call player_stop
                call pl_out_all             ; AY: R0..R12 from the mirror (volumes 0)
                call draw_screen
                ei

;------------------------------------------------------------------------------
; main loop: one pass per frame (after the ISR). Keys -> mailbox, status redraw.
;------------------------------------------------------------------------------
main_loop:
                halt
ml_wake:        call scan_keys              ; test probe: first instruction after the ISR; A = request (0 none)
                or   a
                jr   z, .nokey
                cp   TT_KEY_GATE
                jr   nz, .nogate
                call gate_cycle             ; patch the current song's gates, restart it
                jr   .restart
.nogate:        cp   TT_KEY_REVERB
                jr   nz, .norev
                call rev_cycle              ; patch the current song's tails, restart it
                jr   .restart
.norev:
        IFDEF WZM_ECHO
                cp   TT_KEY_ECHO
                jr   nz, .noecho
                call echo_cycle             ; next echo level (global), restart
                jr   .restart
.noecho:
        ENDIF
                cp   TT_KEY_RESTART
                jr   nz, .req
.restart:       ld   a, (tt_song)
                or   a
                jr   z, .nokey
.req:           ld   (tt_req), a
.nokey:         ld   a, (tt_song)
                ld   hl, shown_song
                cp   (hl)
                call nz, show_song
                call show_status
                jr   main_loop

;------------------------------------------------------------------------------
; tt_isr — 50 Hz: mailbox, player_frame, log, frame count. Not the game ISR
; (that one is lowram.asm's; it calls the same player core).
;------------------------------------------------------------------------------
tt_isr:
                push af
                push bc
                push de
                push hl
                push ix
                ld   a, (tt_req)
                or   a
                jr   z, .play
                ld   hl, tt_req
                ld   (hl), 0
                inc  a
                jr   nz, .start
                call player_stop
                ld   a, ST_STOPPED
                ld   (tt_state), a
                jr   .play
.start:         dec  a
                ld   (tt_song), a
                call entry_ptr
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                call player_start
                ld   hl, 0
                ld   (tt_frames), hl
                ld   hl, TT_LOG
                ld   (tt_logp), hl
                ld   a, ST_PLAYING
                ld   (tt_state), a
.play:
tt_isr_pf:      call player_frame           ; probe pair for tests/music_player.py timing
tt_isr_pf_ret:  ld   a, (tt_state)
                cp   ST_PLAYING
                jr   nz, .out
                ld   hl, (tt_frames)
                inc  hl
                ld   (tt_frames), hl
                ld   de, (tt_logp)          ; ring: frame k -> slot k mod TT_LOG_FRAMES
                ld   hl, pl_regs
                ld   bc, 14
                ldir
                ld   hl, TT_LOG_END
                or   a
                sbc  hl, de
                jr   nz, .logp
                ld   de, TT_LOG
.logp:          ld   (tt_logp), de
                call player_done
                jr   nz, .out
                ld   a, ST_ENDED
                ld   (tt_state), a
.out:           pop  ix
                pop  hl
                pop  de
                pop  bc
                pop  af
                ei
                reti

;------------------------------------------------------------------------------
; entry_ptr: A = request 1..TT_SONGS -> HL = its song_tab entry. Clobbers AF, DE.
;------------------------------------------------------------------------------
entry_ptr:      dec  a
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ASSERT TT_ENTRY == 8
                ld   de, song_tab
                add  hl, de
                ret

; cur_song: HL = song block of tt_song; Z = no song yet. Clobbers AF, DE.
cur_song:       ld   a, (tt_song)
                or   a
                ret  z
                call entry_ptr
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                or   h                      ; NZ: song blocks live at $8000+
                ret

; song_inst: HL = song block, C = voice 0..2 -> HL = its instrument. Clobbers AF, DE.
song_inst:      push hl
                ld   de, WZM_H_INST
                add  hl, de
                ld   e, c
                add  hl, de
                ld   e, (hl)                ; DE = instrument index
                pop  hl
                add  hl, de
                add  hl, de
                ld   e, WZM_H_IPTRS
                add  hl, de
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                ret

; gate_index: HL = song block -> A = gate_tab index of voice A's gate (GATE_N =
; none of them). Clobbers AF, BC, DE, HL.
gate_index:     ld   c, 0
                call song_inst
                ld   de, INS_GATE
                add  hl, de
                ld   de, gate_tab
                ld   b, 0
.g:             ld   a, (de)
                cp   (hl)
                inc  hl
                inc  de
                jr   nz, .nx
                ld   a, (de)
                cp   (hl)
                jr   z, .found
.nx:            dec  hl
                inc  de
                inc  b
                ld   a, b
                cp   GATE_N
                jr   c, .g
.found:         ld   a, b
                ret

; gate_cycle: the current song's instruments (all 3 voices) get the next gate of
; gate_tab (45 -> 56 -> 62 -> 100 -> 45). Takes effect at the next player_start.
; Clobbers AF, BC, DE, HL.
gate_cycle:     call cur_song
                ret  z
                push hl
                call gate_index
                inc  a
                cp   GATE_N
                jr   c, .ok
                xor  a
.ok:            add  a, a
                ld   e, a
                ld   d, 0
                ld   hl, gate_tab
                add  hl, de
                ld   e, (hl)
                inc  hl
                ld   d, (hl)
                ld   (tt_gnew), de
                pop  hl
                ld   c, 0
.v:             push hl
                call song_inst
                ld   de, INS_GATE
                add  hl, de
                ld   de, (tt_gnew)
                ld   (hl), e
                inc  hl
                ld   (hl), d
                pop  hl
                inc  c
                ld   a, c
                cp   3
                jr   c, .v
                ret

; gate bytes (instrument +5 = s1 + 1, +6 = s2'), = tools/abc2wzm.py GATES 30..100
gate_tab:       DB   3, $84                 ; 30 %: round(dur >> 2) + (dur >> 4) = 5/16
                DB   2, 3                   ; 45 %: (dur >> 1) - (dur >> 4)
                DB   2, $84                 ; 56 %: round(dur >> 1) + (dur >> 4)
                DB   2, $83                 ; 62 %: round(dur >> 1) + (dur >> 3)
                DB   1, 8                   ; 100 %: dur - (dur >> 8) = dur
                ASSERT $ - gate_tab == 2 * GATE_N
gate_names:     DW   s_g30, s_g45, s_g56, s_g62, s_g100, s_gnone
s_g30:          DB   "31% ", 0
s_g45:          DB   "45% ", 0
s_g56:          DB   "56% ", 0
s_g62:          DB   "62% ", 0
s_g100:         DB   "100%", 0
s_gnone:        DB   "-   ", 0

;------------------------------------------------------------------------------
; Reverb level (key H). rev_tab = tools/abc2wzm.py inst_tail(): per kind (organ,
; harpsichord) and level (REVERB_STEPS s1e, 0, 50, 100) the voice-A/B (drop,
; rel_per); a buzzer instrument (volume table $10) drops 2 more, capped at 16.
;------------------------------------------------------------------------------
rev_tab:        DB   3, 6,  14, 255,  2, 9,  1, 9     ; organ:  s1e, 0, 50, 100 %
                DB   4, 4,  14, 255,  2, 9,  1, 9     ; harpsichord
                ASSERT $ - rev_tab == 2 * 2 * REV_N
rev_names:      DW   s_rs1e, s_r0, s_r50, s_r100, s_rnone, s_rdry
s_rs1e:         DB   "S1e ", 0
s_r0:           DB   "0%  ", 0
s_r50:          DB   "50% ", 0
s_r100:         DB   "100%", 0
s_rnone:        DB   "-   ", 0
s_rdry:         DB   "none", 0

; rev_kind: HL = song block -> A = 0 organ / 1 harpsichord, NC; CY = a dry entry.
; Clobbers AF, E.
rev_kind:       push hl
                ld   de, WZM_H_SHAPE
                add  hl, de
                ld   e, (hl)
                pop  hl
                ld   a, e
                sub  SHAPE_TRI              ; organ: A = 0, Z, NC
                ret  z
                ld   a, e
                sub  SHAPE_SAW
                ld   a, 1                   ; harpsichord: Z, NC
                ret  z
                scf
                ret

; rev_index: HL = song block -> A = rev_tab level index of voice A's (drop,
; rel_per) (REV_N = none), NC, tt_rkind = kind * 8; CY = dry. Clobbers AF, BC, DE, HL.
rev_index:      call rev_kind
                ret  c
                add  a, a
                add  a, a
                add  a, a
                ld   (tt_rkind), a
                ld   c, 0
                call song_inst              ; HL = voice A's instrument (B kept)
                ld   de, INS_DROP
                add  hl, de
                ld   c, (hl)                ; C = drop
                ld   e, INS_RPER - INS_DROP
                add  hl, de
                ld   b, (hl)                ; B = rel_per
                ld   hl, rev_tab
                ld   a, (tt_rkind)
                ld   e, a
                add  hl, de
                ld   e, 0                   ; E = level index
.r:             ld   a, (hl)
                cp   c
                inc  hl
                jr   nz, .nx
                ld   a, (hl)
                cp   b
                jr   z, .found
.nx:            inc  hl
                inc  e
                ld   a, e
                cp   REV_N
                jr   c, .r
.found:         ld   a, e
                or   a                      ; NC
                ret

; rev_cycle: the current song's instruments get the next reverb level (s1e -> 0
; -> 50 -> 100 -> s1e); dry entries are left alone. Clobbers AF, BC, DE, HL.
rev_cycle:      call cur_song
                ret  z
                push hl
                call rev_index
                pop  hl
                ret  c
                inc  a
                cp   REV_N
                jr   c, .ok
                xor  a
.ok:            add  a, a
                ld   e, a
                ld   a, (tt_rkind)
                add  a, e
                ld   e, a
                ld   d, 0
                push hl
                ld   hl, rev_tab
                add  hl, de
                ld   e, (hl)                ; E = drop (voices A/B)
                inc  hl
                ld   d, (hl)                ; D = rel_per
                ld   (tt_rnew), de
                pop  hl
                ld   c, 0
.v:             push hl
                call song_inst
                ld   de, INS_VOLS
                add  hl, de
                ld   a, (hl)
                and  $10                    ; buzzer instrument?
                ld   de, (tt_rnew)
                jr   z, .put
                inc  e
                inc  e                      ; drops 2 more (16 stands for 14)
                ld   a, e
                cp   17
                jr   c, .put
                ld   e, 16
.put:           dec  hl                     ; +7
                ld   (hl), d
                dec  hl
                dec  hl
                dec  hl                     ; +4
                ld   (hl), e
                pop  hl
                inc  c
                ld   a, c
                cp   3
                jr   c, .v
                ret
                ASSERT INS_VOLS - 1 == INS_RPER && INS_RPER - 3 == INS_DROP

;------------------------------------------------------------------------------
; scan_keys — newly pressed key -> A = 1..TT_SONGS, TT_REQ_STOP, TT_KEY_RESTART,
; TT_KEY_GATE, else 0. Edge-triggered: nothing fires again until every key is
; released.
;------------------------------------------------------------------------------
scan_keys:
                ld   hl, key_tab
                ld   e, 1                   ; request code
.k:             ld   a, (hl)
                or   a
                jr   z, .none
                ld   b, a
                ld   c, $FE
                inc  hl
                in   a, (c)
                and  (hl)
                inc  hl
                jr   z, .hit
                inc  e
                jr   .k
.none:          xor  a
                ld   (key_held), a
                ret
.hit:           ld   a, (key_held)
                or   a
                ld   a, 0
                ret  nz
                inc  a
                ld   (key_held), a
                ld   a, e
                cp   TT_SONGS + 1
                ret  c
                sub  TT_SONGS + 1           ; 0..4 -> $FF / $FE / $FD / $FC / $FB
                cpl
                ret

; (port high byte, bit mask) per request 1..TT_SONGS, then SPACE, L, G, H, J
key_tab:        DB   $F7, $01,  $F7, $02,  $F7, $04,  $F7, $08,  $F7, $10   ; 1..5
                DB   $EF, $10,  $EF, $08                                    ; 6, 7
                DB   $FB, $01,  $FB, $02,  $FB, $04,  $FB, $08,  $FB, $10   ; Q..T
                DB   $DF, $10,  $DF, $08                                    ; Y, U
                DB   $EF, $04,  $EF, $02                                    ; 8, 9
                DB   $EF, $01,  $DF, $04,  $DF, $02,  $DF, $01              ; 0, I, O, P
key_tab_songs:  DB   $7F, $01                                               ; SPACE
                DB   $BF, $02                                               ; L
                DB   $FD, $10                                               ; G
                DB   $BF, $10                                               ; H
        IFDEF WZM_ECHO
                DB   $BF, $08                                               ; J
        ENDIF
                DB   0
                ASSERT key_tab_songs - key_tab == 2 * TT_SONGS
                ASSERT TT_REQ_STOP == $FF && TT_KEY_RESTART == $FE && TT_KEY_GATE == $FD
                ASSERT TT_KEY_REVERB == $FC && TT_KEY_ECHO == $FB

;------------------------------------------------------------------------------
; Echo experiment (key J, player WZM_ECHO): pl_edrop = AY steps below the old
; note: 0 = off, 25 % = 6 (-18 dB), 50 % = 4 (-12 dB), 100 % = 2 (-6 dB: the tsx's
; wet 1.0 vs dry 0.5). Global (every song); restarts the current song.
;------------------------------------------------------------------------------
        IFDEF WZM_ECHO
echo_tab:       DB   0, 6, 4, 2
ECHO_N          EQU $ - echo_tab
echo_names:     DW   s_eoff, s_e25, s_e50, s_e100
s_eoff:         DB   "off ", 0
s_e25:          DB   "25% ", 0
s_e50:          DB   "50% ", 0
s_e100:         DB   "100%", 0

; echo_index: A = echo_tab index of pl_edrop (only ever set from echo_tab: always
; found; CPIR leaves BC = ECHO_N - 1 - index). Clobbers AF, BC, HL.
echo_index:     ld   a, (pl_edrop)
                ld   hl, echo_tab
                ld   bc, ECHO_N
                cpir
                ld   a, ECHO_N - 1
                sub  c
                ret

; echo_cycle: pl_edrop = the next echo_tab level. Clobbers AF, BC, HL.
echo_cycle:     call echo_index
                inc  a
                cp   ECHO_N
                jr   c, .ok
                xor  a
.ok:            ld   c, a
                ld   b, 0
                ld   hl, echo_tab
                add  hl, bc
                ld   a, (hl)
                ld   (pl_edrop), a
                ret
        ENDIF

;------------------------------------------------------------------------------
; Text output with the ROM font (ROM 1 paged). print: HL = 0-terminated string,
; DE = screen cell. Advances DE along the row. Clobbers AF, BC, HL.
;------------------------------------------------------------------------------
print:          ld   a, (hl)
                or   a
                ret  z
                inc  hl
                push hl
                call putc
                pop  hl
                jr   print

; putc: A = char, DE = cell -> DE + 1. Clobbers AF, BC, HL.
putc:           ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ld   bc, ROM_FONT
                add  hl, bc
                ld   b, 8
                push de
.row:           ld   a, (hl)
                ld   (de), a
                inc  hl
                inc  d
                djnz .row
                pop  de
                inc  e
                ret

; clear_to: blank DE's row from DE up to column 31.
clear_to:       ld   a, e
                and  31
                ret  z                      ; wrapped past col 31
                ld   a, ' '
                call putc
                jr   clear_to

; row_cell: A = row -> DE = cell (row, 0). Clobbers AF.
row_cell:       ld   d, a
                and  7
                rrca
                rrca
                rrca
                ld   e, a
                ld   a, d
                and  $18
                or   high SCREEN
                ld   d, a
                ret

draw_screen:
                xor  a
                out  ($FE), a
                ld   hl, SCREEN
                ld   de, SCREEN + 1
                ld   bc, 6144
                ld   (hl), a
                ldir
                ld   hl, ATTRS
                ld   de, ATTRS + 1
                ld   bc, 767
                ld   (hl), ATTR_NORMAL
                ldir
                ld   hl, ATTRS
                ld   b, 32
.hd:            ld   (hl), ATTR_HEAD
                inc  hl
                djnz .hd
                ; menu_text: (row, string) pairs, row $FF ends
                ld   hl, menu_text
.m:             ld   a, (hl)
                inc  a
                ret  z
                dec  a
                inc  hl
                call row_cell
                call print
                inc  hl                     ; past the 0
                jr   .m

; show_song: redraw title / mode of tt_song, move the menu highlight.
show_song:
                ld   (shown_song), a
                ld   hl, ATTRS + MENU_ROW * 32
                ld   de, ATTRS + MENU_ROW * 32 + 1
                ld   bc, (MENU_ROWS * 32) - 1
                ld   (hl), ATTR_NORMAL
                ldir
                ld   a, (shown_song)
                or   a
                ret  z
                call entry_ptr
                ld   de, 6
                add  hl, de
                ld   a, (hl)                ; menu row
                push hl
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ld   de, ATTRS
                add  hl, de
                ld   b, 32
.hl:            ld   (hl), ATTR_CUR
                inc  hl
                djnz .hl
                pop  hl
                dec  hl
                dec  hl
                dec  hl
                dec  hl                     ; -> DW title
                push hl
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                SCR  STAT_ROW, 6
                call print
                call clear_to
                pop  hl
                inc  hl
                inc  hl                     ; -> DW mode
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                SCR  STAT_ROW + 1, 6
                call print
                jp   clear_to

; show_status: gate of the current song, frame counter (5 digits) + state word.
show_status:
                call cur_song
                ld   a, GATE_N
                call nz, gate_index
                add  a, a
                ld   l, a
                ld   h, 0
                ld   de, gate_names
                add  hl, de
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                SCR  STAT_ROW + 2, 6
                call print
                call cur_song               ; REVERB: level of the current song
                ld   a, REV_N
                jr   z, .rv
                call rev_index
                jr   nc, .rv
                ld   a, REV_N + 1           ; dry entry
.rv:            add  a, a
                ld   l, a
                ld   h, 0
                ld   de, rev_names
                add  hl, de
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                SCR  STAT_ROW + 2, 19
                call print
        IFDEF WZM_ECHO
                call echo_index             ; ECHO (experiment): the global level
                add  a, a
                ld   l, a
                ld   h, 0
                ld   de, echo_names
                add  hl, de
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                SCR  14, 23
                call print
        ENDIF
                SCR  STAT_ROW + 3, 7
                ld   hl, (tt_frames)
                ld   bc, -10000
                call .dig
                ld   bc, -1000
                call .dig
                ld   bc, -100
                call .dig
                ld   bc, -10
                call .dig
                ld   bc, -1
                call .dig
                inc  e
                ld   a, (tt_state)
                add  a, a
                ld   l, a
                ld   h, 0
                ld   bc, state_names
                add  hl, bc
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                jp   print
.dig:           ld   a, '0' - 1
.sub:           inc  a
                add  hl, bc
                jr   c, .sub
                sbc  hl, bc                 ; undo the overshoot (carry is clear here)
                push hl
                call putc
                pop  hl
                ret

state_names:    DW   s_idle, s_playing, s_ended, s_stopped
s_idle:         DB   "IDLE    ", 0
s_playing:      DB   "PLAYING ", 0
s_ended:        DB   "ENDED   ", 0
s_stopped:      DB   "STOPPED ", 0

menu_text:      DB   0,  "WZM v0.3 S1e  tsx-max tempo", 0
                DB   2,  "Org Hps Tune           bpm", 0
                DB   3,  " 1   Q  Dungeon Crawl   96 loop", 0
                DB   4,  " 2   W  Dangerous       96 loop", 0
                DB   5,  " 3   E  Boss Fight     106 loop", 0
                DB   6,  " 4   R  Level Complete  96 once", 0
                DB   7,  " 5   T  Game Win        96 once", 0
                DB   8,  " 6   Y  Game Over       96 once", 0
                DB   9,  " 7   U  Lament IIb      96 loop", 0
                DB   10, " 8      Lament S1d tsx  74 loop", 0
                DB   11, " 9      Lament S1d tsx  96 loop", 0
                DB   12, " 0   I  Lament II legato 96 loop", 0
                DB   13, " O/P    Lament II tsx 74/96 dry", 0
                DB   15, "1-7,0 ORGAN  Q-U,I HARPSICHORD", 0
                DB   16, "(crypt reverb; 8 9 O P: none)", 0
                DB   17, "G gate 31/45/56/62/100%", 0
                DB   18, "H reverb S1e/0/50/100%", 0
        IFDEF WZM_ECHO
                DB   14, "J ECHO experiment:", 0
        ENDIF
                DB   19, "L restart  SPACE stop", 0
                DB   STAT_ROW,     "Now:", 0
                DB   STAT_ROW + 1, "Mode:", 0
                DB   STAT_ROW + 2, "Gate:       REVERB", 0
                DB   STAT_ROW + 3, "Frame: 00000 IDLE", 0
                DB   $FF
MENU_ROWS       EQU 11                      ; rows MENU_ROW..MENU_ROW+10 highlightable

;------------------------------------------------------------------------------
; Song table (TT_ENTRY B per entry, request n = entry n - 1, order = key_tab):
; DW song block, DW title, DW mode, DB menu row, DB 0.
;------------------------------------------------------------------------------
SONG            MACRO song, title, mode, row
                DW   song, title, mode
                DB   row, 0
                ENDM
song_tab:
                SONG org_dungeon_crawl, t_crawl, m_org, MENU_ROW + 0
                SONG org_dangerous, t_danger, m_org, MENU_ROW + 1
                SONG org_boss_fight, t_boss, m_org, MENU_ROW + 2
                SONG org_level_complete, t_level, m_org, MENU_ROW + 3
                SONG org_game_win, t_win, m_org, MENU_ROW + 4
                SONG org_game_over, t_over, m_org, MENU_ROW + 5
                SONG org_lament, t_lament, m_org, MENU_ROW + 6
                SONG hps_dungeon_crawl, t_crawl, m_hps, MENU_ROW + 0
                SONG hps_dangerous, t_danger, m_hps, MENU_ROW + 1
                SONG hps_boss_fight, t_boss, m_hps, MENU_ROW + 2
                SONG hps_level_complete, t_level, m_hps, MENU_ROW + 3
                SONG hps_game_win, t_win, m_hps, MENU_ROW + 4
                SONG hps_game_over, t_over, m_hps, MENU_ROW + 5
                SONG hps_lament, t_lament, m_hps, MENU_ROW + 6
                SONG lament_tsx, t_lament, m_tsx74, MENU_ROW + 7
                SONG lament_tsx_96, t_lament, m_tsx96, MENU_ROW + 8
                SONG org_lament2, t_lament2, m_org, MENU_ROW + 9
                SONG hps_lament2, t_lament2, m_hps, MENU_ROW + 9
                SONG lament2_tsx, t_lament2, m_tsx74, MENU_ROW + 10
                SONG lament2_tsx_96, t_lament2, m_tsx96, MENU_ROW + 10
TT_SONGS        EQU ($ - song_tab) / TT_ENTRY

t_crawl:        DB   "Dungeon Crawl 96", 0
t_danger:       DB   "Dangerous 96", 0
t_boss:         DB   "Boss Fight 106", 0
t_level:        DB   "Level Complete 96", 0
t_win:          DB   "Game Win 96", 0
t_over:         DB   "Game Over 96", 0
t_lament:       DB   "Lament IIb", 0
t_lament2:      DB   "Lament II legato", 0
m_org:          DB   "ORGAN + reverb", 0
m_hps:          DB   "HARPSICHORD + reverb", 0
m_tsx74:        DB   "tsx 74bpm, no reverb", 0
m_tsx96:        DB   "tsx 96bpm, no reverb", 0

; --- test-hook state ---
tt_req:         DB   0              ; mailbox: 1..TT_SONGS start, TT_REQ_STOP stop
tt_state:       DB   ST_IDLE
tt_song:        DB   0              ; current song 1..TT_SONGS (0 = none yet)
tt_frames:      DW   0              ; frames played since the start (stops at ENDED)
tt_logp:        DW   TT_LOG         ; next log slot
tt_gnew:        DW   0              ; gate_cycle scratch
tt_rnew:        DW   0              ; rev_cycle scratch: E drop, D rel_per
tt_rkind:       DB   0              ; rev_index: kind * 8 (rev_tab offset)
shown_song:     DB   0
key_held:       DB   0

;------------------------------------------------------------------------------
                INCLUDE "player.asm"
; the player lives in MODULE wzm: the names this tape (and tests/music_player.py,
; via the .sym) use
player_start    EQU wzm.player_start
player_frame    EQU wzm.player_frame
player_stop     EQU wzm.player_stop
player_done     EQU wzm.player_done
pl_out_all      EQU wzm.pl_out_all
pl_regs         EQU wzm.pl_regs
pl_voice_a      EQU wzm.pl_voice_a
        IFDEF WZM_ECHO
pl_edrop        EQU wzm.pl_edrop
        ENDIF
WZM_H_INST      EQU wzm.WZM_H_INST
WZM_H_IPTRS     EQU wzm.WZM_H_IPTRS
WZM_H_SHAPE     EQU wzm.WZM_H_SHAPE
PLAYER_CODE_LEN EQU wzm.PLAYER_CODE_LEN
player_bytes    EQU wzm.player_end - wzm.player_frame

songs:
                INCLUDE "org_dungeon_crawl.asm"
                INCLUDE "org_dangerous.asm"
                INCLUDE "org_boss_fight.asm"
                INCLUDE "org_level_complete.asm"
                INCLUDE "org_game_win.asm"
                INCLUDE "org_game_over.asm"
                INCLUDE "org_lament.asm"
songs_org_end:
                INCLUDE "hps_dungeon_crawl.asm"
                INCLUDE "hps_dangerous.asm"
                INCLUDE "hps_boss_fight.asm"
                INCLUDE "hps_level_complete.asm"
                INCLUDE "hps_game_win.asm"
                INCLUDE "hps_game_over.asm"
                INCLUDE "hps_lament.asm"
songs_hps_end:
                INCLUDE "lament_tsx.asm"
                INCLUDE "lament_tsx_96.asm"
songs_s1d_end:
                INCLUDE "org_lament2.asm"
                INCLUDE "hps_lament2.asm"
                INCLUDE "lament2_tsx.asm"
                INCLUDE "lament2_tsx_96.asm"
code_end:
                ASSERT code_end <= TT_STACK - 64   ; leave room for the stack
                ASSERT TT_ISR + 3 <= $C000
TT_CODE_LEN     EQU code_end - TT_ORG
                DISPLAY "music_test: code $8000..", /H, code_end, " (", /D, TT_CODE_LEN, " B); player ", /D, player_bytes, " B (code ", /D, PLAYER_CODE_LEN, ", table+state ", /D, player_bytes - PLAYER_CODE_LEN, ")"
                DISPLAY "music_test: songs organ ", /D, songs_org_end - songs, " B, harpsichord ", /D, songs_hps_end - songs_org_end, " B, S1d 2 x Lament ", /D, songs_s1d_end - songs_hps_end, " B, Lament II x 4 ", /D, code_end - songs_s1d_end, " B"

;------------------------------------------------------------------------------
; BASIC loader: 10 CLEAR VAL "32767": 20 LOAD "" CODE: 30 RANDOMIZE USR VAL "<start>"
; (tokenised in page 1, which this tape never uses at run time).
;------------------------------------------------------------------------------
TAPE_CLEAR      EQU TT_ORG - 1
                MMU  3, 1
                ORG  $C000
tap_loader:
                DB   0, 10
                DW   tap_l10_end - tap_l10_body
tap_l10_body:   DB   $FD, $B0, '"'
                DB   '0' + (TAPE_CLEAR / 10000) % 10, '0' + (TAPE_CLEAR / 1000) % 10
                DB   '0' + (TAPE_CLEAR / 100) % 10, '0' + (TAPE_CLEAR / 10) % 10, '0' + TAPE_CLEAR % 10
                DB   '"', $0D
tap_l10_end:
                DB   0, 20
                DW   tap_l20_end - tap_l20_body
tap_l20_body:   DB   $EF, $22, $22, $AF, $0D
tap_l20_end:
                DB   0, 30
                DW   tap_l30_end - tap_l30_body
tap_l30_body:   DB   $F9, $C0, $B0, '"'
                DB   '0' + (start / 10000) % 10, '0' + (start / 1000) % 10
                DB   '0' + (start / 100) % 10, '0' + (start / 10) % 10, '0' + start % 10
                DB   '"', $0D
tap_l30_end:
tap_loader_len  EQU  $ - tap_loader

                EMPTYTAP "build/music_test.tap"
                SAVETAP  "build/music_test.tap", BASIC, "musictest", tap_loader, tap_loader_len, 10
                MMU  3, 0
                SAVETAP  "build/music_test.tap", CODE,  "musictest", TT_ORG, TT_CODE_LEN
                SAVESNA  "build/music_test.sna", start
