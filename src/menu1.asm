;==============================================================================
; menu1.asm — C3-6 main menu, redefine keys, pause overlay, end / DEPTH cards
; (bank 1, ui1.asm; game.md §3.1 / §3.2 / §4.1, concept screen_menu.png).
; Everything draws into the bank-5 screen (shown: show_bank5 / play's
; present). Pages nothing at $C000 (bank 1 stays paged: the menu art is read
; in place; D3-TX: the text (bank 0) only through tx_dec, which decodes into
; TX_DEC); helpers used: print6x / print6 / stamp_rect / blit_keep /
; input_tick / sample_input (bank 2), tx_dec (low RAM).
;
; Frame pacing: menu_wait busy-waits for the next frame (counting MENU_SPIN:
; the seed entropy, game.md §1 "Seed") and passes the test probe select_tick
; (also menu_tick), then input_tick — every menu / redefine loop goes through
; it, so the harness ticks it like the old select screen.
;==============================================================================

MENU_ITEM_ROW0  EQU 8               ; item i at rows 8 + 3i (2 rows, menu font); 4 at 18
MENU_CTL_ROW    EQU 16              ; KEYS / KEMPSTON / SINCLAIR 1 / 2 (6x8)
MENU_SND_ROW    EQU 22              ; item 5 (menu font, rows 22-23)
MENU_KEYS_ROW   EQU 20              ; UP Q  DOWN A ... (6x8)
MENU_PREV_ROW   EQU 9               ; hero previews (body top)
MENU_A_DIGIT    EQU $45
MENU_A_LABEL    EQU $47
MENU_A_SEL      EQU $46             ; the pause box choice / QUIT? ask
MENU_A_SUB      EQU $45             ; subtitle, ornament, keys row
MENU_A_CTL      EQU $47
MENU_A_CTL_SEL  EQU $4F             ; the chosen control: PAPER blue

;------------------------------------------------------------------------------
; menu_run — far1 from enter_select: the main menu until START.
; Out: C = hero kind.  Clobbers: all but IY.
;------------------------------------------------------------------------------
menu_run:
                ld   a, MUS_LAMENT             ; menu tune (level-triggered; ISR starts it)
                ld   (MUS_REQ), a
                ld   a, GS_BOOT                ; GS_SELECT once fully drawn
                ld   (GAME_STATE), a
                scf                            ; the last game re-pointed its hero's
                call sel_frt_copy              ; idle FRT row: restore (as sel_run did)
                xor  a
                call clear_screen
                call menu_static
                call menu_items
                call menu_ctl
                call menu_keys
                ld   a, (SYS_FRAMES)
                ld   (LAST_TICK_FRAME), a
                ld   a, GS_SELECT
                ld   (GAME_STATE), a
                call menu_read                 ; keys still down from the end screen
                ld   (menu_sc_old), a          ; (the digit that got here) give no edge
.loop:          call menu_wait
                call menu_read                 ; A = 1..4 / ENTER down, raw
                ld   hl, menu_sc_old
                ld   c, (hl)
                ld   (hl), a
                ld   b, a
                ld   a, c
                cpl
                and  b                         ; A = pressed this frame (lowest wins)
                jr   z, .loop
                ld   c, a                      ; SND-5: a menu key -> the select blip
                ld   a, SFX_MENU               ; (sfx_req keeps BC)
                call sfx_req
                ld   a, c
                rra
                jr   c, .start                 ; 1 / ENTER
                rra
                jr   c, .hero                  ; 2
                rra
                jr   c, .ctl                   ; 3
                rra
                jr   nc, .snd                  ; 5 (SND-1: key 4's bit is now in CF)
                call redefine                  ; 4
                call menu_keys
                jr   .loop
.snd:           call snd_cycle                 ; 5 SOUND: next state (applies at once:
                call menu_snd                  ; the ISR restarts / silences the title tune)
                jr   .loop
.start:         ld   a, (menu_hero)
                ld   c, a
                ret
.hero:          ld   a, (menu_hero)            ; 2 HERO: toggle
                xor  1
                ld   (menu_hero), a
                call menu_items
                call menu_previews
                jr   .loop
.ctl:           ld   a, (JOY_MODE)             ; 3 CONTROLS: next mode (live only
                inc  a                         ; from START: input_tick reads no
                and  3                         ; stick outside GS_PLAYING)
                ld   (JOY_MODE), a
                call menu_ctl
                jr   .loop
                ASSERT JM_KEYS == 0 && JM_SINC2 == 3 && K_KNIGHT == 0 && K_WIZARD == 1

;------------------------------------------------------------------------------
; menu_read — the menu's only input (C3-6b, game.md §3.2): the raw matrix, so
; neither the stick nor JOY_MODE's Sinclair half-masking matters.
; Out: A = bit n = key n+1 down (1..5); ENTER is ORed onto bit 0 (= START).
; Clobbers: A, C, HL
;------------------------------------------------------------------------------
menu_read:
                ld   a, (KBD_MATRIX + KBROW_12345)
                cpl
                and  %00011111                 ; keys 1..5 (bit 0..4), active high
                ld   c, a
                ld   a, (KBD_MATRIX + KBROW_HJKL)
                cpl
                and  1 << KB_ENTER_BIT
                or   c
                ret
                ASSERT KB_ENTER_BIT == 0 && KB_1_BIT == 0


;------------------------------------------------------------------------------
; menu_wait — one menu frame: menu_frame (bank 2: wait, the probe, input,
; seed mixing), then the torch step. The pause loop calls menu_frame only:
; the torches live in playfield row 0 (C3-6 review).  Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
menu_wait:
                call menu_frame
                jp   menu_torch

;------------------------------------------------------------------------------
; menu_static — torches, title, subtitle, ornament, footer, previews.
;------------------------------------------------------------------------------
menu_static:
                ; torches: the static lower cells (frame 0 on top: menu_torch).
                ; RECLAIM-C (d): they are the bank-7 tileset run tset_pool[MENU_TORCH_POOL_IX..]
                ; (byte-checked in main.asm): fetched into MENU_TORCH_BUF (-36 B bank 1, +17 bank 2)
                ld   hl, tset_pool + 8 * MENU_TORCH_POOL_IX
                ld   de, MENU_TORCH_BUF
                ld   bc, MENU_TORCH_STATIC_LEN
                call ldir7
                ld   c, MENU_TORCH_COL_L
                call .torch
                ld   c, MENU_TORCH_COL_R
                call .torch
                ld   a, 1
                ld   (torch_t), a              ; draw now ...
                ld   (torch_k), a              ; ... frame 0 (menu_torch flips k first): the
                                               ; same picture frozen or not (goldens)
                call menu_torch
                ; title: lines of 16x16 glyphs, 2 x 2 cells
                ld   hl, menu_title_lines
.tl:            ld   a, (hl)
                cp   $FF
                jr   z, .tdone
                ld   b, a                      ; row
                inc  hl
                ld   c, (hl)                   ; col
                inc  hl
.tg:            ld   a, (hl)
                inc  hl
                cp   $FE
                jr   z, .tl
                cp   $FF
                jr   z, .gap
                push hl
                push bc
                call title_glyph
                pop  bc
                pop  hl
                inc  c
.gap:           inc  c
                jr   .tg
.tdone:         ; subtitle (6x8), ornament, footer
                ld   a, TX_FT_SUBTITLE
                ld   b, 5
                ld   e, 9 * 8                  ; 19 chars x 6 = 114 px: centred at x=71 ~ 72 (E: multiple of 8)
                call print6x
                ld   a, MENU_A_SUB
                ld   bc, 5 << 8
                ld   de, (32 << 8) | 2         ; rows 5-6
                call stamp_rect
                call menu_orn
                ld   a, MENU_A_LABEL
                ld   bc, 22 << 8
                ld   de, (32 << 8) | 2
                call stamp_rect
                jp   menu_previews
; .torch — C = col: the 6 static cells (rows 1-3) and the 8 attrs.
.torch:         push bc
                ld   hl, MENU_TORCH_BUF
                ld   b, 1
.tr:            push bc
                call mcell                     ; DE = bitmap line 0 of (B, C)
                call copy8
                inc  c
                call mcell
                call copy8
                pop  bc
                inc  b
                ld   a, b
                cp   4
                jr   c, .tr
                pop  bc
                ld   hl, menu_torch_attr
                ld   b, 0
.ta:            push bc
                call mattr                     ; DE = attr (B, C)
                ldi
                ldi
                pop  bc
                inc  b
                ld   a, b
                cp   4
                jr   c, .ta
                ret

; title_glyph — A = glyph index, B / C = top-left cell: 16x16 (2 x 2 cells),
; attrs top MENU_TITLE_ATTR_TOP, bottom MENU_TITLE_ATTR_BOT.
title_glyph:
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl                    ; * 32
                ld   de, menu_title
                add  hl, de
                ld   a, 2
.half:          push af
                push bc
                call mcell
                push bc
                ld   b, 8
.ln:            ld   a, (hl)
                ld   (de), a
                inc  hl
                inc  e
                ld   a, (hl)
                ld   (de), a
                inc  hl
                dec  e
                inc  d
                djnz .ln
                pop  bc
                pop  bc
                pop  af
                push af
                cp   2
                ld   a, MENU_TITLE_ATTR_TOP
                jr   z, .at
                ld   a, MENU_TITLE_ATTR_BOT
.at:            push hl
                ld   l, a
                call mattr                     ; DE = attr (B, C) (clobbers A)
                ld   a, l
                ld   (de), a
                inc  e
                ld   (de), a
                pop  hl
                pop  af
                inc  b
                dec  a
                jr   nz, .half
                ret

; menu_orn — row 6: the panel ornament pattern (orn_cells' rule), MENU_A_SUB.
menu_orn:
                ld   b, 6
menu_orn_b:                                    ; B = row (3E-T2: the bag page's borders)
                ld   c, 0
.c:             ld   a, c
                or   a
                jr   z, .g                     ; ORN_CAP_L
                cp   31
                ld   a, ORN_CAP_R
                jr   z, .g
                ld   a, c
                sub  ORN_MID_COL
                cp   ORN_MID_N
                jr   nc, .ch
                add  a, ORN_WING_L
                jr   .g
.ch:            ld   a, c
                and  1
                ld   e, a
                ld   a, ORN_BAR
                sub  e
.g:             add  a, a
                add  a, a
                add  a, a
                add  a, ORN_GLYPHS & $FF
                ld   l, a
                ld   h, ORN_GLYPHS >> 8
                call mcell
                call copy8
                inc  c
                ld   a, c
                cp   32
                jr   c, .c
                ret

;------------------------------------------------------------------------------
; menu_torch — every MENU_TORCH_STEP frames (8 = 160 ms, the decor flames' rate,
; LOOK-1): the other flame frame on both torches (the right one a frame ahead).
; LOOK-1: fixed attrs (written by menu_static), no flame-tip cycle. RECLAIM-C (d):
; the frame's 2 cells come from the bank-7 tileset (tset_pool, the D1 tall torch)
; through ldir7 into MENU_TORCH_FBUF.  Clobbers: A, BC, DE, HL.  ~1.5k T a swap
;------------------------------------------------------------------------------
menu_torch:
                ld   hl, torch_t
                dec  (hl)
                ret  nz
                ld   (hl), MENU_TORCH_STEP
                ld   hl, torch_k
                ld   a, (hl)
                xor  1                         ; 2 frames
                ld   (hl), a
                ld   a, (ANIM_FREEZE)          ; goldens: hold frame 0 (as the sprites'
                or   a                         ; IDLE frames do)
                jr   z, .nf
                ld   (hl), 0
.nf:            ld   a, (hl)
                push af
                ld   c, MENU_TORCH_COL_L
                call .one
                pop  af
                xor  1
                ld   c, MENU_TORCH_COL_R
.one:           push bc                        ; A = frame 0 / 1, C = col
                rrca
                rrca                           ; A = frame * 8 * MENU_TORCH_FSTEP_IX
                ld   l, a
                ld   h, 0
                ld   de, tset_pool + 8 * MENU_TORCH_F0_IX
                add  hl, de
                ld   de, MENU_TORCH_FBUF
                ld   bc, MENU_TORCH_SWAP_BYTES
                call ldir7
                pop  bc
                ld   hl, MENU_TORCH_FBUF
                ld   b, 0
                call mcell
                call copy8
                inc  c
                call mcell
                jp   copy8
                ASSERT MENU_TORCH_FRAMES == 2 && MENU_TORCH_FSTEP_IX == 8 && MENU_TORCH_SWAP_ROWS == 1

;------------------------------------------------------------------------------
; menu_items — the 4 items (menu font); no cursor (digits-only, C3-6b).
;------------------------------------------------------------------------------
menu_items:
                ld   b, MENU_ITEM_ROW0
                ld   c, 0
                ld   a, MENU_A_LABEL
                ld   (mf_lattr), a
.i:             push bc
                ld   a, c
                add  a, TX_M_START             ; the items' ids are consecutive
                ld   c, 4
                ld   e, MENU_A_DIGIT
                call mf_tx                     ; "n " digit attr, rest mf_lattr
                pop  bc
                push bc
                ld   a, c
                cp   1
                jr   nz, .nh
                ld   a, (menu_hero)            ; "2 HERO: " + the class
                add  a, TX_CLS_WARRIOR
                ld   hl, mf_lattr
                ld   e, (hl)
                ld   c, 12
                call mf_tx_attr
                ld   a, (menu_hero)            ; MAGE after WARRIOR: clear the tail
                or   a                         ; (3 cells; WARRIOR ends at col 18,
                jr   z, .nh                    ; the previews start at col 21)
                ld   a, ' '
                call mf_char_e
                ld   a, ' '
                call mf_char_e
                ld   a, ' '
                call mf_char_e
.nh:            pop  bc
                ld   a, b
                add  a, 3
                cp   MENU_ITEM_ROW0 + 9
                jr   c, .r
                inc  a
                
.r:             ld   b, a
                inc  c
                ld   a, c
                cp   4
                jr   c, .i
                ; fall through: item 5 (the value changes, so it is also redrawn alone)
                ASSERT TX_M_HERO == TX_M_START + 1 && TX_M_CONTROLS == TX_M_START + 2
                ASSERT TX_M_REDEFINE == TX_M_START + 3 && TX_CLS_MAGE == TX_CLS_WARRIOR + 1

; menu_snd — item 5 "5 SOUND: <state>" on rows 21-22 (menu font; the old
; TX_FT_PRESS footer is gone, the credit line is gone too): the rows are cleared
; first (the values differ in length), the digit takes MENU_A_DIGIT like the
; others. Clobbers: A, BC, DE, HL
menu_snd:
                ld   b, MENU_SND_ROW
                call row_clear
                ld   b, MENU_SND_ROW + 1
                call row_clear
                ld   a, '5'
                ld   bc, (MENU_SND_ROW << 8) | 4
                ld   e, MENU_A_DIGIT
                call mf_char
                call snd_id
                ld   bc, (MENU_SND_ROW << 8) | 6
                ld   e, MENU_A_LABEL
                jp   mf_tx_attr

; snd_id — A = the TX id of the current sound state ("SOUND: OFF / SFX ONLY /
; ALL ON"); SND_MODE bits 1..0 = 0 / 2 / 3 -> +0 / +1 / +2 ((m + 1) >> 1).
; Clobbers: A
snd_id:
                ld   a, (SND_MODE)
                and  SND_MUSIC | SND_SFX
                inc  a
                srl  a
                add  a, TX_SND_OFF
                ret
                ASSERT TX_SND_SFX == TX_SND_OFF + 1 && TX_SND_ALL == TX_SND_OFF + 2
                ASSERT SND_ALL == 3 && SND_SFX == 2

;------------------------------------------------------------------------------
; snd_cycle — the one place the sound setting changes (menu 5, pause SOUND,
; in-game S; far1 from sfx2.asm snd_hot): ALL ON (3) -> SFX ONLY (2) -> OFF (0)
; -> ALL ON. Only bits 0-1 change (SND_HOLD stays: in the pause box the new mode
; applies at resume, the ISR acts on its edges). Then the MENU blip (dropped by
; sfx_req when SFX are off or held) and, in play (GS_PLAYING, not SND_HOLD: no
; line in the pause box or the menu), the log line, replacing a pending SOUND line.
; Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
snd_cycle:
                ld   hl, SND_MODE
                ld   a, (hl)
                and  SND_MUSIC | SND_SFX
                jr   z, .all                   ; OFF -> ALL ON
                add  a, a                      ; 3 -> 6, 2 -> 4: & 3 = 2 / 0
                and  SND_MUSIC | SND_SFX
                jr   .set
.all:           ld   a, SND_ALL
.set:           ld   c, a
                ld   a, (hl)
                and  ~(SND_MUSIC | SND_SFX) & $FF
                or   c
                ld   (hl), a
                ld   a, SFX_MENU
                call sfx_req
                ld   a, (GAME_STATE)
                cp   GS_PLAYING
                ret  nz
                ld   a, (SND_MODE)
                add  a, a
                ret  c                         ; SND_HOLD (the pause box): no log line
                call snd_id
                call tx_dec                    ; HL = TX_DEC: plain ASCII is a valid log stream
                ld   a, (LOG_QN)
                or   a
                jr   z, .push
                dec  a                         ; the newest pending line already "SO..."?
                ld   b, a                      ; (no other message starts so): replace it,
                ld   a, (LOG_Q + LQ_RD)        ; so quick S taps use one slot
                add  a, b
                and  LOG_SLOTS - 1
                rrca
                rrca                           ; * LOG_SLOT_LEN (log_push's slot address)
                ld   e, a
                ld   d, LOG_TXT >> 8
                ld   a, (de)
                cp   'S'
                jr   nz, .push
                inc  e
                ld   a, (de)
                cp   'O'
                jr   nz, .push
                ld   a, (LOG_QN)
                dec  a
                ld   (LOG_QN), a
.push:          jp   log_push

; menu_previews — both heroes' idle frames; the chosen one BRIGHT.
menu_previews:
                xor  a
.h:             ld   (pv_i), a
                ld   l, a
                add  a, a
                add  a, l                      ; * 3
                ld   l, a
                ld   h, 0
                ld   de, prev_tab
                add  hl, de
                ld   a, (hl)
                ld   (BL_FID), a
                inc  hl
                ld   a, (hl)                   ; col
                ld   (pv_c), a
                add  a, a
                add  a, a
                add  a, a
                ld   (BL_FPX), a
                inc  hl
                ld   a, (hl)
                ld   (pv_a), a
                ld   a, MENU_PREV_ROW * 8
                ld   (BL_FPY), a
                xor  a
                ld   (BL_LEFT), a
                call blit_keep
                ld   a, (menu_hero)
                ld   hl, pv_i
                cp   (hl)
                ld   a, (pv_a)
                jr   z, .br
                and  ~ATTR_BRIGHT & $FF        ; not chosen: dim
.br:            ld   b, MENU_PREV_ROW
                ld   hl, pv_c
                ld   c, (hl)
                ld   de, (3 << 8) | 6
                call stamp_rect
                ld   a, (pv_i)
                inc  a
                cp   2
                jr   c, .h
                ret
prev_tab:       DB   FID_knight_idle1, 21, $47 ; by hero kind
                DB   FID_wizard_idle, 25, $45

;------------------------------------------------------------------------------
; menu_ctl — row 16: KEYS / KEMPSTON / SINCLAIR 1 / SINCLAIR 2, the chosen
; JOY_MODE on PAPER blue (options on 4-char = 3-cell boundaries).
;------------------------------------------------------------------------------
menu_ctl:
                ld   a, TX_CTL_KEYS
                ld   e, 0 * 6
                call .o
                ld   a, TX_CTL_KEMPSTON
                ld   e, 8 * 6
                call .o
                ld   a, TX_CTL_SINCLAIR1
                ld   e, 20 * 6
                call .o
                ld   a, TX_CTL_SINCLAIR2
                ld   e, 32 * 6
                call .o
                ld   a, MENU_A_CTL
                ld   bc, MENU_CTL_ROW << 8
                ld   de, (32 << 8) | 1
                call stamp_rect
                ld   a, (JOY_MODE)
                add  a, a
                ld   l, a
                ld   h, 0
                ld   de, ctl_cells
                add  hl, de
                ld   c, (hl)
                inc  hl
                ld   d, (hl)
                ld   e, 1
                ld   b, MENU_CTL_ROW
                ld   a, MENU_A_CTL_SEL
                jp   stamp_rect
.o:             ld   b, MENU_CTL_ROW
                jp   print6x
ctl_cells:      DB   0, 3, 6, 6, 15, 8, 24, 8  ; per JOY_MODE: first col, cols
                ASSERT TX_CTL_KEMPSTON == TX_CTL_KEYS + 1

;------------------------------------------------------------------------------
; menu_keys — row 20: "UP x  DOWN x  LEFT x  RIGHT x  FIRE x" from KEYTAB.
;------------------------------------------------------------------------------
menu_keys:
                ld   de, mk_buf
                ld   hl, mk_order
                ld   b, 5
.k:             push bc
                ld   a, (hl)                   ; TX id
                inc  hl
                ld   c, (hl)                   ; KEYTAB entry
                inc  hl
                push hl
                push bc
                call tx_copy                   ; DE -> after the label
                ld   a, ' '
                ld   (de), a
                inc  de
                pop  bc
                ld   a, c
                call key_name                  ; HL = 2-char name of KEYTAB entry A
                ldi
                ld   a, (hl)
                cp   ' '
                jr   z, .one
                ld   (de), a
                inc  de
.one:           ld   a, ' '
                ld   (de), a
                inc  de
                ld   (de), a
                inc  de
                pop  hl
                pop  bc
                djnz .k
                xor  a
                dec  de
                dec  de
                ld   (de), a
                ld   hl, mk_buf                ; blank the row first (shorter names)
                ld   b, MENU_KEYS_ROW
                call row_clear
                ld   hl, mk_buf
                ld   b, MENU_KEYS_ROW
                ld   e, 0
                call print6
                ld   a, MENU_A_SUB
                ld   bc, MENU_KEYS_ROW << 8
                ld   de, (32 << 8) | 1
                jp   stamp_rect
mk_order:       DB   TX_KEY_UP, JOY_U_BIT, TX_KEY_DOWN, JOY_D_BIT, TX_KEY_LEFT, JOY_L_BIT
                DB   TX_KEY_RIGHT, JOY_R_BIT, TX_KEY_FIRE, JOY_F_BIT

; key_name — A = KEYTAB entry index: HL = its 2-char name.  Clobbers: A, BC, HL
key_name:
                add  a, a
                ld   l, a
                ld   h, 0
                ld   bc, KEYTAB
                add  hl, bc
                ld   a, (hl)                   ; row byte
                sub  KEYTAB_ROW
                ld   c, a                      ; row 0..7
                inc  hl
                ld   a, (hl)                   ; mask
                ld   b, 0
.b:             rrca
                jr   c, .f
                inc  b
                jr   .b
.f:             ld   a, c                      ; name index = row * 5 + bit
                add  a, a
                add  a, a
                add  a, c
                add  a, b
                add  a, a                      ; * 2
                ld   l, a
                ld   h, 0
                ld   bc, key_names
                add  hl, bc
                ret
key_names:      DB   "CSZ X C V "              ; row 0: CAPS Z X C V
                DB   "A S D F G "
                DB   "Q W E R T "
                DB   "1 2 3 4 5 "
                DB   "0 9 8 7 6 "
                DB   "P O I U Y "
                DB   "ENL K J H "              ; row 6: ENTER L K J H
                DB   "SPSSM N B "              ; row 7: SPACE SYM M N B

;------------------------------------------------------------------------------
; redefine — "PRESS KEY FOR <UP / DOWN / LEFT / RIGHT / FIRE>" on row 20, one
; key each (game.md §3.2): every key released first, then one key down; a
; key already given this round -> "KEY IN USE" (asked again). Every entry is
; a real row byte + a one-bit mask by construction (any_key). KEYTAB is
; written only when all 5 are in.  Clobbers: all but IY.
;------------------------------------------------------------------------------
redefine:
                xor  a
                ld   (rd_i), a
.ask:           ld   de, mk_buf                ; "PRESS KEY FOR " + the name
                ld   a, TX_KEY_PRESS
                call tx_copy
                call rd_ent                    ; HL = mk_order entry
                ld   a, (hl)
                call tx_copy
                ld   a, TX_KEY_BRK             ; hint: how to cancel
                call tx_copy
                xor  a
                ld   (de), a
                call rd_show
.rel:           call menu_wait                 ; everything released
                call any_key
                jr   nz, .rel
.prs:           call menu_wait
                ld   a, (KBD_MATRIX + KBROW_CAPSV)  ; BREAK (CAPS + SPACE): cancel,
                ld   hl, KBD_MATRIX + KBROW_SPACE   ; the old KEYTAB stays
                or   (hl)
                rra
                jr   nc, .cancel
                call any_key
                jr   z, .prs                   ; B = row byte, C = mask
                call key_reserved              ; ENTER, 1-0, I, CAPS, SYM: the
                jr   z, .resv                  ; shortcuts / BREAK / '.' keep them
                ld   hl, rd_new                ; a duplicate of this round's?
                ld   a, (rd_i)
                or   a
                jr   z, .ok
                ld   e, a
.dup:           ld   a, (hl)
                inc  hl
                cp   b
                ld   a, (hl)
                inc  hl
                jr   nz, .nx
                cp   c
                jr   z, .used
.nx:            dec  e
                jr   nz, .dup
.ok:            ld   a, (rd_i)                 ; rd_new[i] = B, C
                add  a, a
                ld   e, a
                ld   d, 0
                ld   hl, rd_new
                add  hl, de
                ld   (hl), b
                inc  hl
                ld   (hl), c
                ld   hl, rd_i
                inc  (hl)
                ld   a, (hl)
                cp   5
                jr   c, .ask
.last:          call menu_wait                 ; release the last key
                call any_key
                jr   nz, .last
                ld   hl, mk_order + 1          ; rd_new (U D L R F) -> KEYTAB[JOY bit]
                ld   de, rd_new
                ld   b, 5
.cp:            push bc
                ld   a, (hl)
                inc  hl
                inc  hl
                push hl
                add  a, a
                ld   l, a
                ld   h, 0
                ld   bc, KEYTAB
                add  hl, bc
                ex   de, hl                    ; HL = rd_new cursor, DE = KEYTAB slot
                ldi
                ldi
                ex   de, hl
                pop  hl
                pop  bc
                djnz .cp
                ret
.cancel:        call menu_wait                 ; let BREAK go, keep KEYTAB
                call any_key
                jr   nz, .cancel
                ret
.resv:          ld   a, TX_KEY_RESERVED
                jr   .msg
.used:          ld   a, TX_KEY_USED            ; "KEY IN USE", then ask again
.msg:           ld   de, mk_buf
                call tx_copy
                xor  a
                ld   (de), a
                call rd_show
                ld   b, 25                     ; a beat to read it
.bt:            push bc
                call menu_wait
                pop  bc
                djnz .bt
                jp   .ask
; rd_ent — HL = mk_order entry rd_i.  Clobbers: A, BC, HL.  DE (the mk_buf
; cursor after "PRESS KEY FOR ") must survive: UB8 — it used DE, so the name was
; written through DE = 2*i (ROM) and the old menu_keys text showed through.
rd_ent:         ld   a, (rd_i)
                add  a, a
                ld   c, a
                ld   b, 0
                ld   hl, mk_order
                add  hl, bc
                ret

; rd_show — mk_buf (plain) on the keys row, after a clear.
rd_show:        ld   b, MENU_KEYS_ROW
                call row_clear
                ld   hl, mk_buf
                ld   b, MENU_KEYS_ROW
                ld   e, 0
                jp   print6

; key_reserved — B = row byte, C = mask: Z if the key is reserved (C3-6 review,
; manager ruling): the number row (slot shortcuts), ENTER, I, S (SND-1), CAPS SHIFT
; (BREAK), SYMBOL SHIFT ('.').  Clobbers: A
key_reserved:   ld   a, b
                sub  KEYTAB_ROW
                cp   KBROW_12345
                ret  z
                cp   KBROW_09876
                ret  z
                cp   KBROW_HJKL
                jr   z, .ent
                cp   KBROW_POIUY
                jr   z, .i
                cp   KBROW_ASDFG
                jr   z, .s
                cp   KBROW_CAPSV
                jr   z, .cs
                cp   KBROW_SPACE
                ret  nz
                ld   a, c                      ; SYM = bit 1
                cp   1 << KB_SYM_BIT
                ret
.ent:           ld   a, c
                cp   1 << KB_ENTER_BIT
                ret
.i:             ld   a, c
                cp   1 << KB_I_BIT
                ret
.s:             ld   a, c                      ; SND-1: S (the sound hotkey)
                cp   1 << KB_S_BIT
                ret
.cs:            ld   a, c
                cp   1 << KB_CAPS_BIT
                ret

; any_key — Z if no key is down in KBD_MATRIX; else NZ, B = the KEYTAB row
; byte and C = the one-bit mask of the first key found (row 0..7, bit 0..4).
; Clobbers: A, BC, DE, HL
any_key:
                ld   hl, KBD_MATRIX
                ld   e, 0
.r:             ld   a, (hl)
                cpl
                and  $1F
                jr   nz, .k
                inc  l
                inc  e
                ld   a, e
                cp   KBD_MATRIX_LEN
                jr   c, .r
                xor  a                         ; Z
                ret
.k:             ld   c, 1
.b:             rrca
                jr   c, .m
                sla  c
                jr   .b
.m:             ld   a, e
                add  a, KEYTAB_ROW
                ld   b, a
                or   1                         ; NZ
                ret
                ASSERT (KBD_MATRIX >> 8) == ((KBD_MATRIX + KBD_MATRIX_LEN - 1) >> 8)

;------------------------------------------------------------------------------
; Pause (game.md §3.1): pause_run — far1 from pause_hook (bank 2), the screen
; shown is bank 5 (the caller). Rows PAUSE_ROW..+2 of the bank-5 screen are
; saved to GEN_SRC (bitmap 768 B + attrs 96 B), overwritten by the box
; "RESUME   QUIT" (menu font, the choice in yellow); LEFT / RIGHT choose,
; FIRE / ENTER confirm, BREAK resumes; QUIT asks "QUIT? Y/N" (FIRE or Y =
; yes, anything else = no). Resume: the rows restored byte for byte.
; Out: L = 0 resume / 1 quit (far1 clobbers A).  Clobbers: all but IY.
;------------------------------------------------------------------------------
PAUSE_ROW       EQU 7
PAUSE_ITEMS     EQU 3               ; RESUME / SOUND / QUIT
PAUSE_SAVE      EQU GEN_SRC
PAUSE_LEN       EQU 3 * 256 + 3 * 32
                ASSERT PAUSE_SAVE + PAUSE_LEN <= GEN_MIR + 512
                ASSERT PAUSE_SAVE + PAUSE_LEN <= TX_DEC      ; D3-TX: menu text decodes while paused
pause_run:
                ld   hl, SND_MODE              ; HOLD: ISR zeroes volumes, freezes the sequencer
                set  SND_HOLD_BIT, (hl)
                ld   a, 1
                ld   (PAUSED), a
                xor  a                         ; save: screen -> GEN_SRC
                call pause_copy
                ld   a, (PLAYER_SC)
                ld   (menu_sc_old), a
                xor  a
                ld   (pause_sel), a
.redraw:        call pause_box
.loop:          call menu_frame
                call sample_input
                ld   hl, menu_sc_old
                ld   a, (hl)
                cpl
                ld   c, a                      ; C = ~old
                ld   a, (PLAYER_SC)
                ld   (hl), a
                and  c                         ; new SC bits
                ld   d, a
                bit  SC_BREAK_BIT, d
                jp   nz, .resume
                bit  SC_SOUND_BIT, d           ; SND-1: S cycles here too
                jr   nz, .snd
                ld   hl, STICK
                ld   a, (hl)
                inc  l
                ld   e, a
                ld   a, (hl)
                cpl
                and  e                         ; stick presses
                ld   e, a
                bit  JOY_F_BIT, e
                jr   nz, .ok
                bit  SC_ENTER_BIT, d
                jr   nz, .ok
                and  (1 << JOY_L_BIT) | (1 << JOY_R_BIT)
                jr   z, .loop
                ld   hl, pause_sel             ; RESUME / SOUND / QUIT, wrapping
                bit  JOY_R_BIT, a
                jr   z, .left
                inc  (hl)
                ld   a, (hl)
                cp   PAUSE_ITEMS
                jr   c, .redraw
                ld   (hl), 0
                jr   .redraw
.left:          dec  (hl)
                jp   p, .redraw
                ld   (hl), PAUSE_ITEMS - 1
                jr   .redraw
.ok:            ld   a, (pause_sel)
                or   a
                jr   z, .resume
                dec  a
                jr   nz, .ask
.snd:           call snd_cycle                 ; SOUND: cycle in place, stay paused
                jp   .redraw                   ; (SND_HOLD stays set: the ISR applies it at resume)
.ask:
                ; QUIT? Y/N
                call pause_clear
                ld   a, TX_QUIT_ASK
                ld   bc, ((PAUSE_ROW + 1) << 8) | 11
                ld   e, MENU_A_SEL
                call mf_tx
.rel:           call menu_frame                 ; FIRE / ENTER up first
                call sample_input
                ld   a, (STICK)
                and  1 << JOY_F_BIT
                ld   hl, PLAYER_SC
                bit  SC_ENTER_BIT, (hl)
                jr   nz, .rel
                or   a
                jr   nz, .rel
.yn:            call menu_frame
                call sample_input
                ld   a, (STICK)
                bit  JOY_F_BIT, a
                jr   nz, .quit
                ld   a, (KBD_MATRIX + KBROW_POIUY)
                bit  4, a                      ; Y (P O I U Y: bit 4)
                jr   z, .quit
                call any_key                   ; any other key / direction: no
                jr   nz, .no
                ld   a, (STICK)
                and  JOY_MASK
                jr   z, .yn
.no:            call menu_frame                 ; let it go, back to the box
                call any_key
                jr   nz, .no
                ld   a, (STICK)
                and  JOY_MASK
                jr   nz, .no
                jp   .redraw
.quit:          ld   hl, SND_MODE
                res  SND_HOLD_BIT, (hl)
                xor  a
                ld   (PAUSED), a
                ld   l, 1                      ; (far1 clobbers A: the result is L)
                ret
.resume:        ld   a, 1                      ; restore: GEN_SRC -> screen
                call pause_copy
                ld   a, (CUR_ROOM)             ; FLOOR1: the save overwrote the floor-item
                ld   hl, fi_full               ; glyph cache (GEN_SRC tail): rebuilt
                call far3
                ld   bc, PAUSE_ROW << 8
                ld   de, (32 << 8) | 3
                call pmark_rect
                ld   hl, SND_MODE
                res  SND_HOLD_BIT, (hl)
                xor  a
                ld   (PAUSED), a
                ld   l, a
                ret

; pause_box — clear the 3 rows, "RESUME  SOUND: <state>  QUIT" (menu font,
; rows 8-9; cols 1 / 9 / 27 = 30 wide with the longest state), the choice yellow.
pause_box:      call pause_clear
                ld   a, TX_RESUME
                ld   c, 1
                ld   d, 0
                call .it
                call snd_id
                ld   c, 9
                ld   d, 1
                call .it
                ld   a, TX_QUIT
                ld   c, 27
                ld   d, 2
.it:            ld   b, a                      ; A = id, C = col, D = item number
                ld   a, (pause_sel)
                cp   d
                ld   e, MENU_A_SEL
                jr   z, .a
                ld   e, MENU_A_LABEL
.a:             ld   a, b
                ld   b, PAUSE_ROW + 1
                jp   mf_tx_attr

; pause_clear — rows PAUSE_ROW..+2: bitmap 0, attrs $40 (black, bright), row 7 attr $41.
pause_clear:    ld   b, PAUSE_ROW
                call row_clear
                ld   b, PAUSE_ROW + 1
                call row_clear
                ld   b, PAUSE_ROW + 2
                call row_clear
                ld   a, $40
                ld   bc, PAUSE_ROW << 8
                ld   de, (32 << 8) | 3
                jp   stamp_rect

; pause_copy — A = 0: rows PAUSE_ROW..+2 -> PAUSE_SAVE, else back (bitmap
; 3 x 8 lines x 32 B, then the 96 attrs).  Clobbers: A, BC, DE, HL
pause_copy:     ld   (pc_dir), a
                ld   hl, PAUSE_SAVE
                ld   (pc_cur), hl
                ld   b, PAUSE_ROW
.r:             push bc
                ld   c, 0
                call mcell                     ; DE = line 0 of (B, 0)
                ld   b, 8
.l:             push bc
                push de
                call .xfer
                pop  de
                inc  d
                pop  bc
                djnz .l
                pop  bc
                inc  b
                ld   a, b
                cp   PAUSE_ROW + 3
                jr   c, .r
                ld   bc, PAUSE_ROW << 8
                call mattr                     ; DE = attr (row, 0): 96 contiguous
                ld   a, 96
                jr   .x2
.xfer:          ld   a, 32                     ; DE = screen, A = bytes
.x2:            ld   c, a
                ld   b, 0
                ld   hl, (pc_cur)
                ld   a, (pc_dir)
                or   a
                jr   nz, .rs
                ex   de, hl                    ; save: screen -> buffer
                ldir
                ld   (pc_cur), de
                ret
.rs:            ldir                           ; restore: buffer -> screen
                ld   (pc_cur), hl
                ret

;------------------------------------------------------------------------------
; page_ovl — 3E-T2: far1 from page_run (low RAM; screen 2 = the backup, shown):
; the page state (PAGE_N, PAGE_OPEN), ROOM_MAP -> PAGE_MAP_SAVE, then unpack
; the bag page overlay (R6 stream ovl_page_zx0) into GEN_SCRATCH
; (PAGE_ORG) and run it there with bank 1 paged (ovl_run hands the caller's
; bank, 1, on). The page is NOT a pause: music and effects play on (no
; SND_HOLD; user 2026-10-20).
; page_post — far1 from page_run after the copy-back: ROOM_MAP back,
; PAGE_OPEN off; nothing pressed on the page reaches play: no FIRE tap, no shortcut or
; stick edge, a held direction waits for its release (EXIT_LOCK, as an ICON
; MODE exit), no DOWN window, no pending use; ICON MODE is kept.
; 3E-T8: page_post CONSUMES the verb (PAGE_VERB := VB_NONE first) and puts
; the room map back; DISCARD prints "YOU DISCARD <name>" and runs bag_discard
; (0 turns); 3E-T12: every other verb is its fx op (far6 fx_main, R6 fx6.asm:
; EQUIP / REMOVE / DRINK / EAT / READ, 1 turn unless refused: NO NEED).
; Out (page_post): L = 1 the verb spent the turn, else 0.
; Clobbers: A, BC, DE, HL (IX kept).
;------------------------------------------------------------------------------
page_ovl:       ld   hl, PAGE_N
                inc  (hl)
                ld   a, 1
                ld   (PAGE_OPEN), a
                ld   hl, ROOM_MAP              ; the live room map: the window aliases it
                ld   de, PAGE_MAP_SAVE
                ld   bc, PLAY_CELLS
                ldir
                ld   hl, ovl_page_zx0          ; R6 stream (BANK_OVL_PAGE = BANK_R6)
                ld   c, BANK_OVL_PAGE
                ld   de, PAGE_ORG
                jp   ovl_run
page_post:      ld   hl, (PAGE_VERB)           ; L = verb, H = slot (PAGE_SLOT follows)
                xor  a
                ld   (PAGE_VERB), a            ; 3E-T8: consumed here, once (both entries:
                                               ; tpt_intent IN_BAG, use_slot SA_BAG): a stale
                                               ; verb never replays
                ld   a, l
                ld   (PAGE_VLAST), a           ; (test-observable)
                push hl
                ld   hl, PAGE_MAP_SAVE         ; the room map back first: every verb's
                ld   de, ROOM_MAP              ; effect runs with the live map (3E-T12:
                ld   bc, PLAY_CELLS            ; R6 code, no overlay window)
                ldir
                ld   a, (CUR_ROOM)             ; FLOOR1: the map save overwrote the
                ld   hl, fi_full               ; floor-item glyph cache: rebuilt
                call far3
                pop  hl
                ld   a, l
                cp   VB_DISCARD
                jr   z, .dsc
                ld   (FX_OP), hl               ; 3E-T12: DRINK / EAT / READ / EQUIP / REMOVE
                ld   hl, fx_main               ; = their fx ops (R6 fx6.asm; VB_NONE: L 0);
                call far6                      ; L = FXR_* (Teleport: EXIT_KIND, end_turn)
                ld   a, l
                jr   .lat
.dsc:           ld   a, h                      ; 3E-T13: DISCARD applies here (0 turns)
                push af
                add  a, a
                add  a, h
                ld   l, a
                ld   h, HIGH BAG               ; the record (BAG page-aligned)
                ld   a, (hl)                   ; 3E-T8: "YOU DISCARD <name>"
                ld   e, S_FX_DISCARD
                ld   hl, fx_line               ; R6
                call far6
                pop  af
                ld   hl, bag_discard           ; R6: the whole stack, HAS_BOW for the bow
                call far6
                xor  a                         ; no turn
.lat:           ld   hl, page_lat3             ; RECLAIM-C (e): the epilogue is bank 3 (far3 passes
                jp   far3                      ; A in, HL out: L = 1 the verb spent the turn)
                ASSERT PAGE_SLOT == PAGE_VERB + 1

;------------------------------------------------------------------------------
; end_card — ENDCARD-G1 (user 2026-11-02, plan "ENDCARD-L1F-G1"): far1 from end_screen (the
; first key after the end flow's quiet wait, GAME_STATE = GS_DEAD / GS_WIN). A clean full screen (black border, attr
; EC_ATTR): the title in the menu font (row EC_TROW) — "KILLED BY" + the killer's kind name
; (ST1_KILLER), "YOU DIED" (no monster killer), "YOU WIN!" + "THE TOME IS DESTROYED"; on the
; left the killer's first KS_MOVE frame (1x, facing right) or, on a win, the D8 lectern (4
; common tiles, written into the dead room map and drawn by tile_rect); on the right the hero's
; KS_IDLE frame (facing left); the table (ec_tab, bank 3) and "PRESS 1-4 OR ENTER" (row EC_PRESS_ROW);
; then the whole screen is presented (present_full; it leaves bank 7 paged, farb re-pages).
; Feet row of both portraits = the table's first row + 7. Clobbers: all but IY.
; Cost ~0.35M T (clear 0.1M + present_full 0.15M + text + 2 blits), once.
;------------------------------------------------------------------------------
end_card:       xor  a
                out  (PORT_BORDER), a          ; (the ALARM's red border may be up)
                ld   a, EC_ATTR
                call clear_screen              ; (keeps A)
                ld   a, EC_A_HERO              ; the CLASS / LEVEL / DEPTH rows (cols 9-24)
                ld   bc, (EC_TAB_ROW << 8) | 9
                ld   de, (16 << 8) | 3
                call stamp_rect
                ld   a, (GAME_STATE)           ; (END-WAIT: read here, not passed: -3 B in bank 2)
                ld   bc, (EC_TROW << 8) | 12   ; YOU DIED / YOU WIN!: 8 chars, cols 12-19 = centred
                cp   GS_WIN
                jr   z, .win
                ld   a, (ST1_KILLER)
                add  a, a
                jr   c, .kil                   ; $80 | kind
                ld   a, TX_END_DEAD
                ld   e, EC_A_DEAD
                call mf_tx_attr
                jr   .tab
.kil:           rrca                           ; A = the kind
                push af
                add  a, TX_NM_KNIGHT
                push af                        ; the name's TX id
                call tx_dec                    ; DE = TX_DEC + len + 1 (low byte: TX_DEC does not wrap)
                ld   a, 23 + (TX_DEC & $FF)    ; the title is 10 + len cols: col = (32 - 10 - len) / 2
                sub  e                         ; = (22 - len) / 2 (a half col rounds left)
                srl  a
                ld   c, a
                ld   b, EC_TROW
                ld   a, TX_END_KILLED
                ld   e, EC_A_KBY
                call mf_tx_attr
                ld   bc, (mf_row)              ; the col after "KILLED BY" (+ the space)
                inc  c
                ld   e, EC_A_NAME
                pop  af
                call mf_tx_attr
                pop  af
                ; BLAIR-FIX review: ec_kind reads the killer's row of the CURRENT level's
                ; sequence cache (kind_tab KT_SEQ -> seq_rows, R6 pool6 / lowram per level).
                ; Valid: ST1_KILLER is stored at the fatal hit (combat3 deal_hit .kill) by a
                ; body on this level, nothing changes level between it and this card (GS_DEAD
                ; stops the loop; a kit revive clears it, bank7). A kind the cache lacks
                ; (test pokes only) reads a stale row: its FRT_NONE frame is not drawn (blit_miss).
                ld   bc, (EC_FEET << 8) | EC_PCOL_L
                ld   de, KS_MOVE               ; D = 0: facing right
                call ec_kind
                jr   .tab
.win:           ld   a, TX_END_WIN
                ld   e, EC_A_WIN
                call mf_tx_attr
                ld   a, TX_WIN                 ; "THE TOME IS DESTROYED": 21 x 6 px at x 64 = centred
                ld   b, EC_TROW + 2
                ld   e, 64
                call print6x
                ld   hl, ROOM_MAP + (EC_FEET - 2) * ROOM_COLS + EC_PCOL_L + 3   ; the run is over: the map is dead
                ld   a, T_LECT_TL
                ld   (hl), a
                inc  l
                inc  a
                ld   (hl), a                   ; T_LECT_TR
                ld   l, ((EC_FEET - 1) * ROOM_COLS + EC_PCOL_L + 3) & $FF
                inc  a
                ld   (hl), a                   ; T_LECT_BL
                inc  l
                inc  a
                ld   (hl), a                   ; T_LECT_BR
                ld   bc, ((EC_FEET - 2) << 8) | EC_PCOL_L + 3
                ld   de, (2 << 8) | 2
                call tile_rect                 ; (low RAM; glyph + TILE_ATTRS)
.tab:           ld   de, (EC_TAB_ROW << 8) | EC_TAB_X
                ld   hl, ec_tab                ; bank 3 (combat3.asm); DE passes in
                call far3
                ld   b, EC_FEET
                ld   a, (HERO_KIND)
                ld   c, EC_PCOL_R
                ld   de, (6 << 8) | KS_IDLE    ; D = 6: facing left
                call ec_kind
                ld   a, TX_END_PRESS           ; 18 x 6 px at x 72 = centred
                ld   b, EC_PRESS_ROW
                ld   e, 72
                call print6x
                jp   present_full
                ASSERT T_LECT_TR == T_LECT_TL + 1 && T_LECT_BL == T_LECT_TL + 2 && T_LECT_BR == T_LECT_TL + 3
                ASSERT (ROOM_MAP & $FF) == 0 && ((ROOM_MAP + (EC_FEET - 2) * ROOM_COLS) >> 8) == ((ROOM_MAP + (EC_FEET - 1) * ROOM_COLS + EC_PCOL_L + 4) >> 8)
                ASSERT KS_IDLE == 0 && KS_MOVE < 256
                ; ec_kind: the KT_ATTR -> KT_SEQ step changes L only; the cache row + the slot
                ; stays in the seq_rows page (the per-level cache, see .kil)
                ASSERT ((kind_tab + KT_ATTR) >> 8) == ((kind_tab + KT_SEQ + K_MAX - 1) >> 8)
                ASSERT (seq_rows >> 8) == ((seq_rows + SQ_ROWS_LEN - 1) >> 8) && KS_MOVE < KS_STRIDE

;------------------------------------------------------------------------------
; ec_kind — A = kind, E = a sequence slot (KS_IDLE / KS_MOVE: a cycle), B = the feet row,
; C = the col, D = facing (0 right / 6 left): the cycle's first frame (the per-level sequence
; cache: the kind is on this level) in the kind's KT_ATTR, through ec_port.
; ec_port — A = fid, E = attr, B / C / D as above: blit_keep at (C * 8 [+ 4 when only the
; shift-4 variant exists: a WK4 walk frame], feet * 8 - FT_H), facing D; then the attr box
; rows feet - 8 .. feet - 1, cols C .. C + FT_COLS. Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
ec_kind:        add  a, KT_ATTR & $FF
                ld   l, a
                ld   h, (kind_tab + KT_ATTR) >> 8
                ld   a, (hl)                   ; attr
                push af
                ld   a, l
                add  a, KT_SEQ - KT_ATTR
                ld   l, a
                ld   a, (hl)                   ; the kind's SEQ_ROWS row
                add  a, e
                ld   l, a
                ld   h, seq_rows >> 8
                ld   a, (hl)
                inc  l
                ld   h, (hl)
                ld   l, a                      ; HL = the cycle: total ticks, (fid, ticks)...
                inc  hl
                ld   a, (hl)                   ; its first fid
                pop  hl
                ld   e, h
ec_port:        ld   (BL_FID), a
                push de
                call frt_ptr                   ; HL = the FRT row (bank 2; A, DE)
                pop  de
                ld   a, d
                ld   (BL_LEFT), a
                add  a, l
                ld   l, a                      ; the facing's shift-0 variant
                ld   a, (hl)
                inc  a                         ; Z: FRT_NONE
                ld   a, c
                rlca
                rlca
                rlca
                jr   nz, .s
                or   4
.s:             ld   (BL_FPX), a
                ld   a, l
                or   $0F
                sub  3 - FT_H                  ; L = row + FT_IN_ROW + FT_H
                ld   l, a
                ld   a, b
                rlca
                rlca
                rlca
                sub  (hl)
                ld   (BL_FPY), a               ; feet * 8 - H
                dec  l
                ld   d, (hl)                   ; FT_COLS
                inc  d                         ; + the spill col
                push bc
                push de
                call blit_keep
                pop  de
                pop  bc
                ld   a, b
                sub  8
                ld   b, a
                ld   a, e
                ld   e, 8
                jp   stamp_rect
                ASSERT FRT_NONE == $FF && FT_IN_ROW + 3 == 15 && FT_COLS == FT_H - 1 && FRT_STRIDE == 16
                ASSERT (KT_ATTR >> 8) == (KT_SEQ >> 8) && (kind_tab & $FF) == 0

;------------------------------------------------------------------------------
; level_card — far1 from level_show (low RAM): A = depth 1..8: "DEPTH n" in
; the menu font, centred on rows 11-12 of the (cleared) bank-5 screen.
;------------------------------------------------------------------------------
level_card:     push af
                ld   a, TX_CARD_DEPTH
                ld   bc, (11 << 8) | 12
                ld   e, $47
                call mf_tx
                pop  af
                add  a, '0'
                ld   e, $46
                jp   mf_char_e

;------------------------------------------------------------------------------
; stinger_wait — SND-4a: far1 from level_enter, between the level generation
; and level_show (the "DEPTH n" card is still up). Holds the next level's start
; while the Level Complete stinger (MUS_CUR = MUS_LEVEL, MS_SHOT) is sounding:
; one menu_frame per loop (frame wait + input_tick; the ISR plays on). Returns
; at once when no stinger runs (new game, music off / SFX ONLY: the ISR drops the
; shot, MUS_STATE stays idle). A FRESH press (STICK or any key, after everything
; was released: the move key that took the exit is still down) skips it: the
; music bit is dropped for one ISR frame (falling edge = player_stop) and set
; again (rising edge = the room loop restarts at bar 1). Outside the play tick.
; Clobbers: all but IY.   Worst wait = the stinger's length less the generation.
;------------------------------------------------------------------------------
stinger_wait:
                ld   de, 0                     ; D bit 0 = released once; D bits 1-2 + E = a
.w:             ld   a, (MUS_STATE)            ; 512-frame cap (R is 385 frames: never a hang)
                and  MS_MASK
                cp   MS_SHOT
                ret  nz
                ld   a, (MUS_CUR)
                cp   MUS_LEVEL
                ret  nz
                dec  e
                jr   nz, .c
                inc  d
                inc  d
.c:             bit  2, d
                ret  nz
                push de
                call menu_frame
                call read_stick                ; GS_TRANSITION: input_tick left STICK at 0, so
                push af                        ; read the keys + the Kempston port here (the
                call any_key                   ; matrix is fresh from menu_frame)
                pop  bc
                or   b
                pop  de
                jr   nz, .down
                set  0, d                      ; released: a press now counts
                jr   .w
.down:          bit  0, d
                jr   z, .w
                ld   hl, SND_MODE              ; skip: stop, then restart the loop
                res  SND_MUSIC_BIT, (hl)
                push hl
                call menu_frame                ; >= 1 ISR frame sees music off
                pop  hl
                set  SND_MUSIC_BIT, (hl)
                ret

;------------------------------------------------------------------------------
; Menu-font printing (8x16, 2 cells tall, one attr for both cells).
; mf_tx      — A = TX id at row B / col C, attr E (mf_tx_attr: the same);
;              mf_tx sets mf_lattr = E, then the first 2 chars ("n ") take E
;              and the rest mf_lattr (menu_items' digit / label split).
; mf_char    — A = char at (B, C), attr E.  mf_char_e: at (mf_row, mf_col),
;              attr mf_attr, then mf_col += 1.
; Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
mf_tx:          ld   d, a
                ld   a, e
                ld   (mf_attr), a
                ld   a, (mf_lattr)
                ld   (mf_lt), a
                ld   a, 2
                ld   (mf_split), a
                ld   a, d
                jr   mf_go
mf_tx_attr:     ld   d, a
                ld   a, e
                ld   (mf_attr), a
                ld   (mf_lt), a
                xor  a
                ld   (mf_split), a
                ld   a, d
mf_go:          ld   (mf_row), bc              ; C = col, B = row
                call tx_dec                    ; HL = TX_DEC (D3-TX: the text is in bank 0)
.n:             ld   a, (hl)
                inc  hl
                or   a
                ret  z
                ld   (mf_bc), hl
                ld   hl, mf_split
                ld   e, a
                ld   a, (hl)
                or   a
                jr   z, .t
                dec  (hl)
                jr   nz, .t
                ld   a, (mf_lt)                ; past the digit: the label attr
                ld   (mf_attr), a
.t:             ld   a, e
                call mf_char_e
                ld   hl, (mf_bc)
                jr   .n
mf_char:        ld   (mf_row), bc
                push af
                ld   a, e
                ld   (mf_attr), a
                pop  af
; RECLAIM-B T3: ASCII -> glyph by range arithmetic (was a 64-B map; same glyph for all
; 41 charset chars, absent -> 0 = space; tools/menu_art.py `font_glyph` is the model
; and asserts it against the charset). Cold path (menu text only). A = char in,
; glyph out; DE is dead here (reloaded below).
mf_char_e:      cp   'A'
                jr   c, .lo
                cp   'Z' + 1
                jr   nc, .sp
                sub  50                        ; 'A'..'Z' -> 15..40
                jr   .g
.lo:            cp   '0'
                jr   c, .pu
                cp   ':' + 1
                jr   c, .dg
                cp   '>'
                ld   a, 14
                jr   z, .g
.sp:            xor  a                         ; absent: glyph 0 (space)
                jr   .g
.dg:            sub  45                        ; '0'..'9' -> 3..12, ':' -> 13
                jr   .g
.pu:            sub  32                        ; ' ' 0, '!' 1, '-' (13) -> 2
                jr   z, .g
                cp   1
                jr   z, .g
                cp   13
                ld   a, 2
                jr   z, .g
                xor  a
.g:             ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl                    ; * 16
                ld   de, menu_font
                add  hl, de
                ld   bc, (mf_row)
                push bc
                call mcell
                call copy8
                pop  bc
                push bc
                inc  b
                call mcell
                call copy8
                pop  bc
                push bc
                call mattr
                ld   a, (mf_attr)
                ld   (de), a
                ex   de, hl
                ld   de, 32
                add  hl, de
                ld   (hl), a
                pop  bc
                inc  c
                ld   (mf_row), bc
                ret
                ASSERT MENU_FONT_STRIDE == 16

;------------------------------------------------------------------------------
; small helpers (bank 1)
;------------------------------------------------------------------------------
; mcell — DE = bitmap line 0 of cell (B, C).  Clobbers: A
mcell:          ld   a, b
                and  $18
                or   SCREEN_BITMAP >> 8
                ld   d, a
                ld   a, b
                rrca
                rrca
                rrca
                and  $E0
                or   c
                ld   e, a
                ret
; mattr — DE = attr of cell (B, C).  Clobbers: A
mattr:          ld   a, b
                rrca
                rrca
                rrca
                ld   e, a
                and  3
                or   SCREEN_ATTR >> 8
                ld   d, a
                ld   a, e
                and  $E0
                or   c
                ld   e, a
                ret
; copy8 — 8 B from HL (advanced) to the 8 lines of the cell at DE.  Clobbers: A, D
copy8:          push bc
                ld   b, 8
.l:             ld   a, (hl)
                ld   (de), a
                inc  hl
                inc  d
                djnz .l
                pop  bc
                ret
; row_clear — char row B: bitmap 0 (attrs kept).  Clobbers: A, C, DE, HL
row_clear:      push bc
                ld   c, 0
                call mcell
                ex   de, hl
                ld   c, 8
.l:             push hl
                ld   b, 32
.b:             ld   (hl), 0
                inc  l
                djnz .b
                pop  hl
                inc  h
                dec  c
                jr   nz, .l
                pop  bc
                ret
; tx_copy — A = TX id: its decoded text at (DE) .. DE out (no terminator).
; D3-TX: decoded by tx_dec (low RAM) into TX_DEC, then copied here: DE may
; point into bank 1 (mk_buf), which tx_dec pages out.
; Clobbers: A, BC, HL
tx_copy:        push de
                call tx_dec                    ; HL = TX_DEC
                pop  de
.n:             ld   a, (hl)
                or   a
                ret  z
                ld   (de), a
                inc  hl
                inc  de
                jr   .n

                INCLUDE "../assets/gfx/menu/menu_font.asm"
                INCLUDE "../assets/gfx/menu/menu_title.asm"
                INCLUDE "../assets/gfx/menu/menu_torch.asm"
