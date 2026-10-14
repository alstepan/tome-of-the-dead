;==============================================================================
; src/music/testtape.asm — SND-0 S1a STANDALONE music test tape (not the game)
;
;   tools/build_music_test.sh  ->  build/music_test.tap (auto-runs from 128
;   BASIC: CLEAR / LOAD "" CODE / RANDOMIZE USR) and build/music_test.sna.
;
; Plays the WZM v0.2 songs emitted by tools/abc2wzm.py --batch build/music (from
; the tsx JSON sources assets/sfx/music/src) with src/music/player.asm (buzzer
; assembled in), driven from an IM 2 ISR at 50 Hz. Menu keys 1..0, Q pick a
; song (docs/design/sound.md S1d key map), SPACE stops, L restarts the current
; song (in its twin version if a song_tab entry has one; none do now). Screen:
; menu, title + variant of the current song, twin state, frame counter and state.
;
; Test hooks (tests/music_player.py, ZRCP): tt_req (mailbox, 1..TT_SONGS = start
; song n, TT_REQ_STOP = stop; tt_legato picks the version when the ISR takes the
; request), tt_state, tt_frames, tt_song, tt_legato; the ISR appends the
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

TT_REQ_STOP     EQU $FF
TT_KEY_LEG      EQU $FE             ; scan_keys: L pressed (never a mailbox value)
TT_ENTRY        EQU 8               ; song_tab: DW legato, DW no-legato (0 = same), DW title, DW variant
ST_IDLE         EQU 0
ST_PLAYING      EQU 1
ST_ENDED        EQU 2
ST_STOPPED      EQU 3

MENU_ROW        EQU 2               ; first menu row
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
                cp   TT_KEY_LEG
                jr   nz, .req
                ld   hl, tt_legato          ; L: toggle, restart the current song in that version
                ld   a, (hl)
                xor  1
                ld   (hl), a
                ld   a, (tt_song)
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
                dec  a
                ld   l, a                   ; HL = song_tab + TT_ENTRY * (n - 1)
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ASSERT TT_ENTRY == 8
                ld   de, song_tab
                add  hl, de
                ld   e, (hl)                ; DE = legato version
                inc  hl
                ld   d, (hl)
                inc  hl
                ld   a, (tt_legato)
                or   a
                jr   nz, .ver
                ld   a, (hl)                ; no-legato twin, if any
                inc  hl
                ld   h, (hl)
                ld   l, a
                or   h
                jr   z, .ver
                ex   de, hl
.ver:           ex   de, hl
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
; scan_keys — newly pressed menu key -> A = 1..TT_SONGS / TT_REQ_STOP, else 0.
; Edge-triggered: nothing fires again until every key is released.
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
                ld   a, TT_REQ_STOP
                ret  z
                ld   a, TT_KEY_LEG
                ret

; (port high byte, bit mask) per request 1..TT_SONGS, then SPACE = stop
key_tab:        DB   $F7, $01,  $F7, $02,  $F7, $04,  $F7, $08,  $F7, $10   ; 1..5
                DB   $EF, $10,  $EF, $08,  $EF, $04,  $EF, $02,  $EF, $01   ; 6..0
                DB   $FB, $01                                               ; Q
                DB   $7F, $01                                               ; SPACE
                DB   $BF, $02                                               ; L
                DB   0
key_chars:      DB   "1234567890Q"
                ASSERT $ - key_chars == TT_SONGS

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
                SCR  0, 0
                ld   hl, s_head
                call print
                ; menu: "<key> <title> <variant>" one row each
                ld   ix, song_tab
                ld   iy, key_chars          ; (IY: no ROM ISR runs under our IM 2)
                ld   c, 0
.m:             ld   a, c
                add  a, MENU_ROW
                call row_cell
                push bc
                ld   a, (iy + 0)
                call putc
                inc  e
                ld   l, (ix + 4)
                ld   h, (ix + 5)
                call print
                ld   a, ' '
                call putc
                ld   l, (ix + 6)
                ld   h, (ix + 7)
                call print
                ld   a, (ix + 2)
                or   (ix + 3)
                jr   z, .nol
                ld   a, ' '
                call putc
                ld   a, 'L'
                call putc
.nol:           pop  bc
                ld   de, TT_ENTRY
                add  ix, de
                inc  iy
                inc  c
                ld   a, c
                cp   TT_SONGS
                jr   c, .m
                SCR  MENU_ROW + TT_SONGS + 1, 0
                ld   hl, s_keys
                call print
                SCR  STAT_ROW, 0
                ld   hl, s_now
                call print
                SCR  STAT_ROW + 1, 0
                ld   hl, s_var
                call print
                SCR  STAT_ROW + 2, 0
                ld   hl, s_leg
                call print
                SCR  STAT_ROW + 3, 0
                ld   hl, s_frame
                jp   print

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

; show_song: redraw title/variant of tt_song, move the menu highlight.
show_song:
                ld   (shown_song), a
                ; attribute rows: all menu rows normal, the current one highlighted
                ld   hl, ATTRS + MENU_ROW * 32
                ld   de, ATTRS + MENU_ROW * 32 + 1
                ld   bc, TT_SONGS * 32 - 1
                ld   (hl), ATTR_NORMAL
                ldir
                ld   a, (shown_song)
                or   a
                ret  z
                add  a, MENU_ROW - 1
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
                ld   a, (shown_song)
                dec  a
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ld   de, song_tab + 4
                add  hl, de
                push hl
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                SCR  STAT_ROW, 5
                call print
                call clear_to
                pop  hl
                inc  hl
                inc  hl
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                SCR  STAT_ROW + 1, 5
                call print
                jp   clear_to

; show_status: legato state, frame counter (5 digits) + state word.
show_status:
                SCR  STAT_ROW + 2, 8
                ld   hl, s_on
                ld   a, (tt_legato)
                or   a
                jr   nz, .leg
                ld   hl, s_off
.leg:           call print
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
s_on:           DB   "ON ", 0
s_off:          DB   "OFF", 0
s_head:         DB   "WZM v0.2 AY player test SND-0 S1", 0
s_keys:         DB   "SPACE stop  L restart", 0
s_leg:          DB   "Twin:   ON", 0
s_now:          DB   "Now: -", 0
s_var:          DB   "Var:", 0
s_frame:        DB   "Frame: 00000 IDLE", 0

;------------------------------------------------------------------------------
; Song table: DW song block, DW title, DW variant (6 B per entry, request n =
; entry n - 1). Order = key_chars.
;------------------------------------------------------------------------------
song_tab:
                DW   tune_dungeon_crawl, 0, t_crawl, v_crawl
                DW   tune_dangerous, 0, t_danger, v_danger
                DW   tune_boss_fight, 0, t_boss, v_boss
                DW   tune_level_complete, 0, t_level, v_level
                DW   tune_game_win, 0, t_win, v_win
                DW   tune_game_over, 0, t_over, v_over
                DW   lament_tsx, 0, t_lament, v_tsx
                DW   lament_tsx_96, 0, t_lament, v_tsx96
                DW   lament_pluck, 0, t_lament, v_pluck
                DW   lament_buzz, 0, t_lament, v_buzz
                DW   lament_oct, 0, t_lament, v_oct
TT_SONGS        EQU ($ - song_tab) / TT_ENTRY

t_crawl:        DB   "Dungeon Crawl", 0
t_danger:       DB   "Dangerous", 0
t_boss:         DB   "Boss Fight", 0
t_level:        DB   "Level Complete", 0
t_win:          DB   "Game Win", 0
t_over:         DB   "Game Over", 0
t_lament:       DB   "Lament", 0
v_crawl:        DB   "tsx 72bpm loop", 0
v_danger:       DB   "tsx 68bpm loop", 0
v_boss:         DB   "tsx 106bpm loop", 0
v_level:        DB   "tsx 78bpm once", 0
v_win:          DB   "tsx 84bpm once", 0
v_over:         DB   "tsx 66bpm once", 0
v_tsx:          DB   "tsx 74bpm", 0
v_tsx96:        DB   "tsx 96bpm", 0
v_pluck:        DB   "old pluck harp 74", 0
v_buzz:         DB   "exp saw-buzz bass 74", 0
v_oct:          DB   "exp oct blip 74", 0

; --- test-hook state ---
tt_req:         DB   0              ; mailbox: 1..TT_SONGS start, TT_REQ_STOP stop
tt_state:       DB   ST_IDLE
tt_song:        DB   0              ; current song 1..TT_SONGS (0 = none yet)
tt_legato:      DB   1              ; 1 = legato version, 0 = the --no-legato twin
tt_frames:      DW   0              ; frames played since the start (stops at ENDED)
tt_logp:        DW   TT_LOG         ; next log slot
shown_song:     DB   0
key_held:       DB   0

;------------------------------------------------------------------------------
                DEFINE WZM_BUZZER       ; S1d (6) experiment: key 0
                INCLUDE "player.asm"
player_bytes    EQU player_end - player_frame

songs:
                INCLUDE "tune_dungeon_crawl.asm"
                INCLUDE "tune_dangerous.asm"
                INCLUDE "tune_boss_fight.asm"
                INCLUDE "tune_level_complete.asm"
                INCLUDE "tune_game_win.asm"
                INCLUDE "tune_game_over.asm"
                INCLUDE "lament_tsx.asm"
songs7_end:
                INCLUDE "lament_tsx_96.asm"
                INCLUDE "lament_pluck.asm"
                INCLUDE "lament_buzz.asm"
                INCLUDE "lament_oct.asm"
code_end:
                ASSERT code_end <= TT_STACK - 64   ; leave room for the stack
                ASSERT TT_ISR + 3 <= $C000
TT_CODE_LEN     EQU code_end - TT_ORG
                DISPLAY "music_test: code $8000..", /H, code_end, " (", /D, TT_CODE_LEN, " B); player ", /D, player_bytes, " B (code ", /D, PLAYER_CODE_LEN, ", table+state ", /D, player_bytes - PLAYER_CODE_LEN, "); songs ", /D, code_end - songs, " B (the 7 tsx tunes ", /D, songs7_end - songs, " B)"

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
