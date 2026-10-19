;==============================================================================
; io.asm — input layer + RNG. C3-1: one STICK byte (read_stick: KEYTAB /
; Sinclair / Kempston, JOY_* bits) feeds PLAYER_DIR; shortcuts -> PLAYER_SC.
;
; Input keeps the P3 INPUT_SRC / KBD_MATRIX test-injection contract (+ C3-0's
; JOY_MIRROR for the Kempston port). Held keys repeat (read_turn_input).
;
; RNG: xorshift16 (7,9,8), foundations F3 — main.asm only seeds
; RNG_STATE, it has no generator yet, so this is the first implementation.
;==============================================================================

; discrete key bits (PLAYER_DISC)
DK_WAIT         EQU %00000010
DK_ENTER        EQU %00000100
DK_1            EQU %00001000
DK_2            EQU %00010000
DK_3            EQU %00100000
DK_WAIT_BIT     EQU 1
DK_ENTER_BIT    EQU 2
DK_1_BIT        EQU 3
DK_2_BIT        EQU 4
DK_3_BIT        EQU 5

; PLAYER_SC (C3-1): the shortcut keys of game.md §3.1 (C3-2 consumes them)
SC_SLOT_MASK    EQU %00001111       ; 1..10 = key 1..9, 0 held (lowest wins); 0 = none
SC_ENTER_BIT    EQU 5               ; ENTER (use the selected icon, C3-2)
SC_SOUND_BIT    EQU 4               ; S (SND-1: bit 4 was free: slots 1..10 are 4 bits)
SC_INV_BIT      EQU 6               ; I
SC_BREAK_BIT    EQU 7               ; CAPS SHIFT + SPACE
SC_ROWKEYS      EQU %00011111       ; the 5 keys of a half-row

KB_1_BIT        EQU 0               ; KBROW_12345
KB_2_BIT        EQU 1
KB_3_BIT        EQU 2
KB_SYM_BIT      EQU 1               ; KBROW_SPACE
KB_M_BIT        EQU 2
KB_C_BIT        EQU 3               ; KBROW_CAPSV (CAPS Z X C V)

;==============================================================================
; scan_matrix — copy the 8 keyboard half-rows into KBD_MATRIX, unless
; INPUT_SRC != 0 (test injection: keep the poked mirror).
; Clobbers: A, BC, D, HL      ~ 8 x 45 T = 360 T
;==============================================================================
scan_matrix:
                ld   a, (INPUT_SRC)
                or   a
                ret  nz
                ld   hl, KBD_MATRIX
                ld   c, $FE
                ld   b, $FE
                ld   d, KBD_MATRIX_LEN
.row:
                in   a, (c)
                ld   (hl), a
                inc  hl
                rlc  b
                dec  d
                jr   nz, .row
                ret

;==============================================================================
; input_tick — once per 25 Hz tick (play_loop every tick, the select / end
; loops each pass): scan_matrix, then STICK_OLD = STICK, STICK = read_stick
; (C3-8a: the PROTO H/J/K/L aliases are gone). So STICK / STICK_OLD
; are always two consecutive ticks, ANIM ticks included (C3-2's edges).
; BREAK (CAPS + SPACE) clears FIRE: with the default KEYTAB SPACE is FIRE,
; and SC_BREAK has priority (sample_input reports it). FIRE stays cleared
; (FIRE_LOCK) until FIRE itself is released, whichever key goes first.
; C3-6b: GAME_STATE != GS_PLAYING -> STICK = 0 (no read_stick at all).
; Clobbers: A, BC, DE, HL     ~0.5k + read_stick (live, keys: ~0.95k T)
;==============================================================================
input_tick:
                call scan_matrix
                ld   a, (GAME_STATE)          ; C3-6b: menu / redefine / end screens
                cp   GS_PLAYING               ; read the raw matrix only: no KEYTAB,
                ld   c, 0                     ; Sinclair or Kempston port ($1F floats
                jr   nz, .nrd                 ; on a bare machine). The pause overlay
                call read_stick               ; runs in GS_PLAYING: in-game controls.
                ld   c, a
.nrd:
                ld   a, (KBD_MATRIX + KBROW_CAPSV)
                ld   hl, KBD_MATRIX + KBROW_SPACE
                or   (hl)
                rra                           ; CF = 0 iff CAPS and SPACE (BREAK)
                ld   hl, FIRE_LOCK
                jr   c, .nBrk
                ld   (hl), 1                  ; BREAK: FIRE off until it is released
.nBrk:          ld   a, (hl)                  ; (review: lifting CAPS first must
                or   a                        ; not turn the held SPACE into a tap)
                jr   z, .st
                bit  JOY_F_BIT, c
                jr   z, .unl
                res  JOY_F_BIT, c
                jr   .st
.unl:           ld   (hl), 0                  ; FIRE released: unlocked
.st:            ld   hl, STICK
                ld   a, (hl)
                ld   (hl), c
                inc  l
                ld   (hl), a                  ; STICK_OLD = last tick's STICK
                ret

;==============================================================================
; read_stick — the 5 inputs (JOY_* bits, Kempston order, 1 = pressed), ORed
; from KEYTAB (always), the Sinclair preset of JOY_MODE (JM_SINC1/2) or the
; Kempston port (JM_KEMPSTON only: the port floats without an interface).
; Reads KBD_MATRIX (needs this tick's scan_matrix). Does not write STICK.
; Kempston: a byte with any of bits 5-7 set is ignored (absent interface /
; floating bus reads $FF); INPUT_SRC != 0 reads JOY_MIRROR instead of the port.
; Out: A = STICK bits.  Clobbers: A, BC, DE, HL
; T (incl. call; W19): keys ~0.42k, Kempston ~0.5k, Sinclair ~0.83k
;==============================================================================
read_stick:
                ld   hl, KEYTAB
                call stick_tab
                ld   c, a
                ld   a, (JOY_MODE)
                sub  JM_KEMPSTON
                jr   z, .kemp
                ld   a, c
                ret  c                        ; JM_KEYS
                push bc                       ; Sinclair 1 / 2
                ld   hl, sinc1_tab
                ld   a, (JOY_MODE)
                cp   JM_SINC1
                jr   z, .sinc
                ld   l, sinc2_tab & $FF       ; same page (ASSERTed)
.sinc:          call stick_tab
                pop  bc
                or   c
                ret
.kemp:          ld   a, (INPUT_SRC)           ; A = 0 on the live path: harmless
                or   a                        ; high address byte for IN (n)
                jr   nz, .mirror
.port:          in   a, (KEMPSTON_PORT)       ; test probe (no IN unless JM_KEMPSTON)
                jr   .kv
.mirror:        ld   a, (JOY_MIRROR)
.kv:            ld   b, a
                and  ~JOY_MASK & $FF
                ld   a, c
                ret  nz                       ; bits 5-7: no interface, ignore
                or   b
                ret

;------------------------------------------------------------------------------
; stick_tab — HL = a 5-entry KEYTAB-format table ({KBD_MATRIX low byte + row,
; mask}; one page; entry i = JOY bit i). Out: A = the JOY bits whose key is
; down, bits 5-7 = 0.  Clobbers: A, BC, DE, HL     5 x 57 + 43 = ~0.33k T
;------------------------------------------------------------------------------
stick_tab:
                ld   d, KBD_MATRIX >> 8
                ld   bc, KEYTAB_N << 8        ; B = entries, C = bits (shifted in)
.k:             ld   e, (hl)                  ; = the half-row's KBD_MATRIX address
                inc  l
                ld   a, (de)                  ; the half-row, active low
                and  (hl)
                inc  l
                sub  1                        ; CF iff the key's bit is 0 (down)
                rr   c
                djnz .k
                ld   a, c                     ; entries 0..4 in bits 3..7, 0 below
                rrca
                rrca
                rrca
                ret

; Sinclair presets (game.md §3.2), KEYTAB format. Sinclair 1 = 6 L, 7 R,
; 8 D, 9 U, 0 F (KBROW_09876: 0 bit 0 .. 6 bit 4); Sinclair 2 = 1 L, 2 R,
; 3 D, 4 U, 5 F (KBROW_12345: 1 bit 0 .. 5 bit 4).
S1_ROW          EQU KEYTAB_ROW + KBROW_09876
S2_ROW          EQU KEYTAB_ROW + KBROW_12345
sinc1_tab:      DB S1_ROW, 1 << 3, S1_ROW, 1 << 4, S1_ROW, 1 << 2, S1_ROW, 1 << 1, S1_ROW, 1 << 0
sinc2_tab:      DB S2_ROW, 1 << 1, S2_ROW, 1 << 0, S2_ROW, 1 << 2, S2_ROW, 1 << 3, S2_ROW, 1 << 4
sinc_end:
                ASSERT (sinc1_tab >> 8) == ((sinc_end - 1) >> 8)
                ASSERT sinc2_tab - sinc1_tab == KEYTAB_N * KEYTAB_STRIDE

;==============================================================================
; sample_input — derive this tick's PLAYER_DIR (= STICK & JOY_DIRS),
; PLAYER_DISC (DK_*: FIRE / '.' = wait, ENTER, 1/2/3, G, C) and PLAYER_SC
; (SC_*: slot shortcut 1..10, I, BREAK) from STICK + KBD_MATRIX. Call after
; this tick's input_tick (reads only; may run more than once a tick).
; Sinclair 1 / 2 turn off the shortcuts on its half of the number row
; (6-0 / 1-5, incl. DK_1..3).
; Out: A = DIR | DISC | SC (NZ iff anything held).  Clobbers: A, BC, DE, HL
; T: ~0.6k (no shortcut held)
;==============================================================================
sample_input:
                ld   a, (STICK)
                ld   c, a
                and  JOY_DIRS
                ld   (PLAYER_DIR), a
                ; --- discrete keys ---
                ld   e, 0
                ld   a, (KBD_MATRIX + KBROW_SPACE)
                and  (1 << KB_SYM_BIT) | (1 << KB_M_BIT)
                jr   nz, .nDot               ; '.' = SYMBOL SHIFT + M
                set  DK_WAIT_BIT, e
.nDot:          ld   a, (KBD_MATRIX + KBROW_HJKL)
                bit  KB_ENTER_BIT, a
                jr   nz, .nEn
                set  DK_ENTER_BIT, e
.nEn:           ; --- number row, minus the selected Sinclair half ---
                ld   hl, (KBD_MATRIX + KBROW_12345)   ; L = 12345, H = 09876
                ASSERT KBROW_09876 == KBROW_12345 + 1
                ld   a, (JOY_MODE)
                cp   JM_SINC1
                jr   nz, .nS1
                ld   h, KBD_RELEASED
.nS1:           cp   JM_SINC2
                jr   nz, .nS2
                ld   l, KBD_RELEASED
.nS2:           ld   a, l
                cpl
                and  SC_ROWKEYS               ; 1..5 held, active high
                ld   d, a
                and  %00000111                ; 1 / 2 / 3 -> DK_1..3 in one go
                add  a, a
                add  a, a
                add  a, a
                ASSERT DK_1_BIT == 3 && DK_2_BIT == 4 && DK_3_BIT == 5
                or   e
                ld   e, a
                ld   a, d
                ld   d, 0                     ; D = PLAYER_SC
                or   a
                jr   z, .no5
                inc  d                        ; lowest key held wins: 1 = bit 0
.s5:            rra
                jr   c, .sc
                inc  d
                jr   .s5
.no5:           ld   a, h
                cpl
                and  SC_ROWKEYS
                jr   z, .sc
                ld   d, 6                     ; 6 = bit 4 .. 0 (slot 10) = bit 0
                rlca
                rlca
                rlca
.s0:            rla
                jr   c, .sc
                inc  d
                jr   .s0
.sc:            ld   a, (KBD_MATRIX + KBROW_POIUY)
                bit  KB_I_BIT, a
                jr   nz, .nI
                set  SC_INV_BIT, d
.nI:            call snd_scan                 ; SND-1: S -> SC_SOUND (sfx2.asm, after kind_tab: pad)
                ld   a, (KBD_MATRIX + KBROW_CAPSV)
                ld   hl, KBD_MATRIX + KBROW_SPACE
                or   (hl)                     ; bit 0 clear iff CAPS and SPACE
                rra
                jr   c, .nBrk
                set  SC_BREAK_BIT, d
.nBrk:          bit  DK_ENTER_BIT, e
                jr   z, .nEnt
                set  SC_ENTER_BIT, d
.nEnt:          ld   a, d
                ld   (PLAYER_SC), a
                ld   a, e
                ld   (PLAYER_DISC), a
                or   d
                ld   hl, PLAYER_DIR
                or   (hl)
                ret

;==============================================================================
; keys_down — C3-6b end screens: Z iff none of 1..0 / ENTER is down in
; KBD_MATRIX (raw: JOY_MODE's Sinclair half-masking does not apply).
; Out: A = 0 if none.  Clobbers: A, HL     ~0.15k T
;==============================================================================
keys_down:
                ld   a, (KBD_MATRIX + KBROW_HJKL)
                or   ~(1 << KB_ENTER_BIT) & $FF   ; only ENTER's bit can be low
                ld   hl, KBD_MATRIX + KBROW_12345
                and  (hl)
                inc  l
                ASSERT KBROW_09876 == KBROW_12345 + 1 && (KBD_MATRIX >> 8) == ((KBD_MATRIX + KBROW_09876) >> 8)
                and  (hl)
                and  SC_ROWKEYS               ; bits 5-7 (EAR) are not keys
                xor  SC_ROWKEYS               ; a low bit (down) -> 1
                ret

;==============================================================================
; intent_tick — C3-2b turn-intent machine (game.md §3.1 "ICON MODE", user
; 2026-10-05), every GS_PLAYING tick after input_tick (ANIM ticks too, so no
; press is lost). Runs sample_input
; (read_turn_input reuses its outputs). Never costs a turn itself.
; Shortcut edges (both modes): 1..0 -> sel_key (select only), I -> NO BAG YET, S -> snd_cycle (SND-1),
;   ENTER -> INTENT (use), BREAK -> leaves ICON MODE, else pause_hook; a held
;   FIRE is cancelled (BREAK has priority).
; ICON MODE (ICON_MODE != 0; play frozen in INPUT ticks, play_loop): FIRE
;   press -> INTENT (use: a turn-costing use leaves the mode, an illegal one
;   stays, tpt_intent); UP / DOWN press -> leave; LEFT / RIGHT -> cursor_step
;   at once, after CUR_DELAY1 ticks, then every CUR_DELAY2.
; Play: FIRE released after < FIRE_TAP_MAX ticks with no direction -> INTENT.
;   FIRE + DOWN, either first, the other within DN_DEFER ticks -> ICON MODE.
;   FIRE + UP press -> pause_hook. DOWN alone counts DN_T (tpt_intent waits /
;   climbs down at DN_DEFER ticks held); released earlier -> DN_COMMIT.
; Clobbers: A, BC, DE, HL      idle ~0.65k T (sample_input ~0.5k)
;==============================================================================
DN_DEFER        EQU 3               ; ticks DOWN alone is held back (ICON MODE window)
intent_tick:
                call sample_input
                ; --- shortcut edges ---
                ld   hl, SC_OLD
                ld   a, (PLAYER_SC)
                ld   c, (hl)                  ; C = last tick
                ld   (hl), a
                ld   b, a                     ; B = now
                ld   a, c
                cpl
                and  b
                and  ~SC_SLOT_MASK & $FF
                ld   e, a                     ; E = new INV / ENTER / BREAK
                ld   a, b
                and  SC_SLOT_MASK
                jr   z, .nSlot
                ld   d, a
                ld   a, c
                and  SC_SLOT_MASK
                cp   d
                jr   z, .nSlot                ; same slot key still held
                ld   a, d
                push de
                ld   hl, sel_key              ; bank 7 (intent7.asm, D3-7 T0)
                call far7
                pop  de
.nSlot:         bit  SC_BREAK_BIT, e
                jr   z, .nBrk
                call fire_used
                push de
                ld   a, (ICON_MODE)
                or   a
                jr   z, .brkP
                call mode_exit                ; BREAK in ICON MODE: exit, no pause
                jr   .brkE
.brkP:          call pause_hook
.brkE:          pop  de
.nBrk:          bit  SC_INV_BIT, e
                jr   z, .nInv
                push de
                call bag_msg
                pop  de
.nInv:          bit  SC_SOUND_BIT, e          ; SND-1: S edge: cycle the sound setting, no turn
                call nz, snd_hot              ; (sfx2.asm; keeps DE; touches no input state)
                bit  SC_ENTER_BIT, e
                jr   z, .stick
                ld   a, IN_FIRE
                ld   (INTENT), a
                ; --- the stick ---
.stick:         ld   hl, STICK
                ld   d, (hl)                  ; D = STICK
                inc  l
                ld   a, (hl)                  ; STICK_OLD
                cpl
                and  d
                ld   e, a                     ; E = pressed this tick
                ld   a, (ICON_MODE)
                or   a
                jr   z, .play
                ld   hl, intent_icon7          ; D3-S2: ICON MODE (frozen play) in
                jp   far7                      ; bank 7; D, E pass in
                ; --- play ---
.play:          ld   hl, FIRE_ST
                bit  JOY_F_BIT, d
                jr   nz, .down
                ld   a, (hl)                  ; FIRE up
                ld   (hl), FS_UP
                cp   FS_TAP
                jr   nz, .dn
                ld   a, IN_FIRE               ; a tap: use the icon (next INPUT tick)
                ld   (INTENT), a
                jr   .dn
.down:          ld   a, (hl)
                or   a
                jr   nz, .held
                ld   (hl), FS_TAP             ; pressed
                xor  a
                ld   (FIRE_T), a
                jr   .fd
.held:          ld   a, (FIRE_T)
                inc  a
                jr   z, .fd                   ; saturates
                ld   (FIRE_T), a
                cp   FIRE_TAP_MAX
                jr   c, .fd
                ld   (hl), FS_USED            ; held too long: not a tap
.fd:            bit  JOY_D_BIT, d             ; FIRE + DOWN, the 2nd within DN_DEFER?
                jr   z, .nfd
                bit  JOY_F_BIT, e
                jr   z, .dfirst
                ld   a, (DN_T)                ; FIRE now: DOWN held < DN_DEFER?
                cp   DN_DEFER
                jr   c, .enter
                jr   .used
.dfirst:        bit  JOY_D_BIT, e             ; DOWN now: FIRE held < DN_DEFER?
                jr   z, .used
                ld   a, (FIRE_T)
                cp   DN_DEFER
                jr   nc, .used
.enter:         xor  a
                ld   (DN_T), a
                ld   (DN_COMMIT), a
                call fire_used
                jp   mode_enter
.nfd:           bit  JOY_U_BIT, e
                jr   z, .nfu
                call fire_used
                jp   pause_hook               ; FIRE + UP
.nfu:           ld   a, d
                and  JOY_DIRS
                ret  z
.used:          jp   fire_used                ; FIRE with a direction: not a tap
                ; --- DOWN alone (FIRE up): the ICON MODE window ---
.dn:            ld   a, (EXIT_LOCK)          ; the stick that left ICON MODE is
                or   a                        ; still held: no DOWN window
                ret  nz
                ld   a, d
                and  JOY_DIRS
                cp   1 << JOY_D_BIT
                ld   hl, DN_T
                jr   nz, .dnu
                inc  (hl)
                ret  nz
                dec  (hl)                     ; saturates at 255
                ret
.dnu:           ld   a, (hl)                  ; released (or joined) before it
                ld   (hl), 0                  ; committed: commit it once now
                or   a
                ret  z
                cp   DN_DEFER
                ret  nc
                ld   a, d
                and  JOY_DIRS
                ret  nz                       ; another direction took over
                inc  a
                ld   (DN_COMMIT), a
                ret

;------------------------------------------------------------------------------
; menu_frame — the menu / redefine / pause frame (C3-6; bank 2 so the test
; probe select_tick is always-mapped RAM, never a bank-1 / bank-3 alias):
; busy-wait for SYS_FRAMES to move, the probe, input_tick, then the seed
; mixing: on any input change (STICK or a key row) MENU_SPIN = MENU_SPIN * 2
; + R + SYS_FRAMES, so the seed depends on the timing of every keypress in the
; menu, not only the START frame (game.md §1 "Seed").  Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
menu_frame:
                ld   a, (SYS_FRAMES)
                ld   b, a
.w:             ld   a, (SYS_FRAMES)
                cp   b
                jr   z, .w
select_tick:                                   ; test probe (one per menu frame; menu_tick)
menu_tick:
                call input_tick
                ld   hl, KBD_MATRIX            ; input changed since last frame?
                ld   b, KBD_MATRIX_LEN
                ld   c, 0
.x:             ld   a, (hl)
                xor  c
                ld   c, a                      ; C = a cheap fold of the rows
                rlc  c
                inc  l
                djnz .x
                ld   a, (STICK)
                xor  c
                ld   hl, MENU_IN_SIG
                cp   (hl)
                ret  z
                ld   (hl), a
                ld   hl, (MENU_SPIN)
                add  hl, hl
                ld   a, r
                add  a, l
                ld   l, a
                ld   a, (SYS_FRAMES)
                adc  a, h
                ld   h, a
                ld   (MENU_SPIN), hl
                ret

; mode_enter / mode_exit — ICON MODE on / off: the selected slot's highlight
; (icon_sig) and the info line's ">" prefix follow (PD_INFO).  Clobbers: A, HL
mode_enter:     ld   a, 1
                jr   mode_set
mode_exit:      ld   a, (STICK)               ; a direction held at the exit waits
                and  JOY_DIRS                 ; for its release (EXIT_LOCK != 0);
                ld   (EXIT_LOCK), a           ; none held (FIRE use): no lock
                xor  a
                ld   (DN_T), a
mode_set:       ld   (ICON_MODE), a
                ld   hl, PANEL_DIRTY
                set  PD_INFO_BIT, (hl)
                ld   hl, CUR_REP
                ld   (hl), 0
                ret

; fire_used — a held FIRE did something: its release is not a tap.  Clobbers: A
fire_used:      ld   a, (FIRE_ST)
                or   a
                ret  z
                ld   a, FS_USED
                ld   (FIRE_ST), a
                ret

; bag_msg — I / FIRE on BAG before 3E's bag page (game.md §3.1).
bag_msg:        ld   a, TX_NO_BAG
                jp   msg_push

; pause_hook — FIRE+UP / BREAK (outside ICON MODE): D3-S2: the body is
; bank-7 pause_run7 (far7). Clobbers: all but IX, IY.
pause_hook:     ld   hl, pause_run7
                jp   far7

;==============================================================================
; rng_next — xorshift16, triplet (7,9,8) (J. Metcalf's Z80 form).
; Out: HL = new state (also stored), A = L (the rng_byte).  Clobbers: A, HL
; ~ 90 T. Never yields 0 from a non-zero seed; period 65535.
;==============================================================================
rng_next:
                ld   hl, (RNG_STATE)
                ld   a, h
                rra
                ld   a, l
                rra
                xor  h
                ld   h, a
                ld   a, l
                rra
                ld   a, h
                rra
                xor  l
                ld   l, a
                xor  h
                ld   h, a
                ld   (RNG_STATE), hl
                ld   a, l
                ret

;==============================================================================
; rng_mod — uniform 0..C-1 by mask-and-reject (no divide, no modulo bias).
; In : C = n (1..128).  Out: A = 0..n-1.  Clobbers: A, B, HL
;==============================================================================
rng_mod:
                ld   a, c
                dec  a
                ld   b, a                    ; B = n-1 -> smear to a 2^k-1 mask
                srl  a
                or   b
                ld   b, a
                srl  a
                srl  a
                or   b
                ld   b, a
                srl  a
                srl  a
                srl  a
                srl  a
                or   b
                ld   b, a                    ; B = mask
.again:
                call rng_next
                and  b
                cp   c
                jr   nc, .again              ; reject >= n
                ret
