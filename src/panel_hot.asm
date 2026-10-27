;==============================================================================
; PANEL HOT IMAGE (B3B-11, B3B-11b) — assembled for HOT_COPY (bank 2 runtime
; RAM, uncontended, always mapped) and copied there by panel_boot. Its load
; image sits in the boot-only cold data (main.asm `vdata`: bank 1 after the
; ZX0 sprite sources), read through copy_virt.
; Labels are the runtime addresses (DISP).
;==============================================================================
panel_hot_img:
                DISP HOT_COPY
panel_hot:

;------------------------------------------------------------------------------
; print6 — 6x8 text (planar FONT6, 6-px pitch) into the bank-5 bitmap, the
; "quad" printer: 4 chars = 24 px = 3 bytes per pixel line, composed in
; registers and STORED (no reads of the contended screen, no per-char phase
; code). HL = string (ASCII 32..127, 0-terminated), B = char row, E = pixel x,
; a multiple of 8 (every panel field starts on a cell, game.md §3.4), x + 6n
; <= 256.
; Exact output: the bytes the run covers, ceil(6n / 8) from x, are written
; whole (the last one's pixels past the run are 0); nothing else is touched.
; So a run overwrites its own old text, only cells past the new end keep old
; ink (callers clear). The font's bits 1..0 are masked off at boot (planes),
; so a glyph can never bleed into its neighbour (B3B-11b: the old self-
; clearing rule on the font is gone). Attrs untouched, nothing marked.
; Char source = 4 fetch sites .g0...g3 (3 B each). Default: inline
; `ld a, (bc) / inc bc / nop` on the string (BC). print6g (panel2.asm)
; patches them to `call getter` for a feeding decoder (B3B-13 dictionary
; tokens): getter out A = next char (0 = end), state in BC, keeps DE, may
; clobber HL; it is not called again after it returned 0. The getter must
; emit only chars 32..127 (FONT6 has planes for those only: any other code
; reads the free plane holes / HOT_COPY as glyph bits).
; Out: E = x after the last char (x + 6n, mod 256).
; Clobbers: A, BC, D, HL, E (out).
; SMC: .g0...g3 (fetch sites, print6g / p6_inline), .c0a...c3b (the quad's
; plane offsets), .s1e/.s1o/.s2e/.s2o (`ld (de),a` <-> nop in a partial
; last quad, restored before return), .xe+1 (E out).
; Cost: per quad 4 x 61 (fetch + patch) + 4 pairs x 361 + ~90 -> ~460 T/char
; incl. contention at display time (W15 measures it); ~150 T fixed per call.
;------------------------------------------------------------------------------
P6_LDBC         EQU $0A                        ; ld a, (bc)
P6_INCBC        EQU $03                        ; inc bc
P6_STORE        EQU $12                        ; ld (de), a
print6:
                ld   a, (print6_go.g0)
                cp   P6_LDBC
                call nz, p6_inline             ; (panel2.asm) undo print6g's patch
                ld   a, b
                ld   b, h
                ld   c, l                      ; BC = the string
print6_go:                                     ; A = row, E = x, BC = source state
                ld   l, a
                and  $18
                or   SCREEN_BITMAP >> 8
                ld   d, a                      ; D = bitmap high of the row's line 0
                ld   a, l
                rrca
                rrca
                rrca
                and  $E0
                ld   l, a
                ld   a, e
                rrca
                rrca
                rrca                           ; x / 8 (x & 7 = 0: no stray bits)
                or   l
                ld   e, a                      ; DE = first byte, line 0
.quad:
.g0:            ld   a, (bc)                   ; SMC: fetch site (3 B)
                inc  bc
                nop
                or   a
                jr   z, .end0
                ld   (.c0a+1), a
                add  a, FONT6_WB
                ld   (.c0b+1), a
.g1:            ld   a, (bc)
                inc  bc
                nop
                or   a
                jr   z, .k1
                ld   (.c1a+1), a
                add  a, FONT6_WB
                ld   (.c1b+1), a
.g2:            ld   a, (bc)
                inc  bc
                nop
                or   a
                jr   z, .k2
                ld   (.c2a+1), a
                add  a, FONT6_WB
                ld   (.c2b+1), a
.g3:            ld   a, (bc)
                inc  bc
                nop
                or   a
                jr   z, .k3
                ld   (.c3a+1), a
                add  a, FONT6_WB
                ld   (.c3b+1), a
                call .lines
                ld   a, d
                sub  8
                ld   d, a                      ; back to line 0
                inc  e
                inc  e
                inc  e                         ; next 3 bytes
                jp   .quad
                ; end of text inside a quad of k = 0..3 chars: E out, then a
                ; partial quad pads with ' ' and skips the bytes past the text
.end0:          ld   c, 0
                call .xset
                jr   .xe
.k1:            ld   c, 6
                call .xset
                ld   a, ' '
                ld   (.c1a+1), a
                ld   a, ' ' + FONT6_WB
                ld   (.c1b+1), a
                xor  a                         ; nop: byte 1 not written
                ld   (.s1e), a
                ld   (.s1o), a
                jr   .q2
.k2:            ld   c, 12
                call .xset
.q2:            ld   a, ' '
                ld   (.c2a+1), a
                ld   a, ' ' + FONT6_WB
                ld   (.c2b+1), a
                xor  a                         ; nop: byte 2 not written
                ld   (.s2e), a
                ld   (.s2o), a
                jr   .q3
.k3:            ld   c, 18
                call .xset
.q3:            ld   a, ' '
                ld   (.c3a+1), a
                ld   a, ' ' + FONT6_WB
                ld   (.c3b+1), a
                call .lines
                ld   a, P6_STORE
                ld   (.s1e), a
                ld   (.s1o), a
                ld   (.s2e), a
                ld   (.s2o), a
.xe:            ld   e, 0                      ; SMC: x after the last char
                ret
.xset:          ld   a, e                      ; x end = col * 8 + 6k (C = 6k)
                and  $1F
                add  a, a
                add  a, a
                add  a, a
                add  a, c
                ld   (.xe+1), a
                ret

; .lines — the quad's 8 pixel lines as 4 pairs: even line (window A, left to
; right), odd line (window B, right to left: no E rewind). Per line, with
; gN = glyph byte of char N (bits 1..0 = 0):
;   byte0 = g0 | g1 >> 6                 r1 = g1 rlc 2 (bits 1..0 = g1 >> 6,
;   byte1 = (g1 << 2) | g2 >> 4               bits 7..4 = g1 << 2)
;   byte2 = (g2 << 4) | g3 >> 2          r2 = g2 rrc 4
; merges by ((x ^ y) & m) ^ y = (x & m) | (y & ~m), 15 T, no spare register.
; In: DE = byte 0 line 0, the 8 code sites set.  Out: D += 8, E kept.
; Clobbers: A, H, L (BC saved).  166 + 195 T per pair, 1,444 + 48 T per quad.
.lines:         push bc
                ld   h, FONT6 >> 8
.pair:
.c1a:           ld   l, 0                      ; SMC: code 1
                ld   a, (hl)
                rlca
                rlca
                ld   b, a                      ; B = r1
                and  3
.c0a:           ld   l, 0                      ; SMC: code 0
                or   (hl)
                ld   (de), a                   ; byte 0
                inc  e
.c2a:           ld   l, 0                      ; SMC: code 2
                ld   a, (hl)
                rrca
                rrca
                rrca
                rrca
                ld   c, a                      ; C = r2
                xor  b
                and  $0F
                xor  b
.s1e:           ld   (de), a                   ; byte 1 (SMC: nop)
                inc  e
.c3a:           ld   l, 0                      ; SMC: code 3
                ld   a, (hl)
                rrca
                rrca                           ; g3 >> 2
                xor  c
                and  $3F
                xor  c
.s2e:           ld   (de), a                   ; byte 2 (SMC: nop)
                inc  d
.c2b:           ld   l, 0                      ; SMC: code 2 + FONT6_WB
                ld   a, (hl)
                rrca
                rrca
                rrca
                rrca
                ld   c, a
.c3b:           ld   l, 0                      ; SMC: code 3 + FONT6_WB
                ld   a, (hl)
                rrca
                rrca
                xor  c
                and  $3F
                xor  c
.s2o:           ld   (de), a                   ; byte 2 (SMC: nop)
                dec  e
.c1b:           ld   l, 0                      ; SMC: code 1 + FONT6_WB
                ld   a, (hl)
                rlca
                rlca
                ld   b, a
                xor  c
                and  $F0
                xor  c
.s1o:           ld   (de), a                   ; byte 1 (SMC: nop)
                dec  e
                ld   a, b
                and  3
.c0b:           ld   l, 0                      ; SMC: code 0 + FONT6_WB
                or   (hl)
                ld   (de), a                   ; byte 0
                inc  d
                inc  h
                ld   a, d
                and  7
                jp   nz, .pair                 ; the row's line 0 has D & 7 = 0
                pop  bc
                ret
P6_SITES        EQU 4                          ; fetch sites .g0...g3, 3 B each, P6_SITE_STEP apart
P6_SITE0        EQU print6_go.g0
P6_SITE_STEP    EQU print6_go.g1 - print6_go.g0
                ASSERT print6_go.g2 - print6_go.g1 == P6_SITE_STEP && print6_go.g3 - print6_go.g2 == P6_SITE_STEP

;------------------------------------------------------------------------------
; log_push — queue message HL (0-terminated, upper case, <= LOG_MAX chars;
; longer ones are cut) for the log: copied into the LOG_TXT ring, LOG_QN += 1,
; PANEL_DIRTY |= PD_LOG. Ring full (LOG_SLOTS pending): dropped, LQ_DROP += 1.
; log_push_end — the same for a message that must never be lost (GS_DEAD /
; GS_WIN): ring full -> it REPLACES the newest pending message (counted in
; LQ_DROP). Safe: a message is drawn whole inside one panel_step, so no
; pending slot is ever half printed.
; Any tick, any bank paged. Clobbers: A, B, DE, HL.   ~0.5k T (20 chars)
;------------------------------------------------------------------------------
log_push_end:
                ld   a, (LOG_QN)
                cp   LOG_SLOTS
                jr   c, log_push.ok
                dec  a
                ld   (LOG_QN), a
                call log_drop
                ; fall through: pushes into the newest slot
log_push:
                ld   a, (LOG_QN)
                cp   LOG_SLOTS
                jr   nc, log_drop
.ok:            ld   b, a
                inc  a
                ld   (LOG_QN), a
                ld   a, (LOG_Q + LQ_RD)
                add  a, b
                and  LOG_SLOTS - 1
                rrca
                rrca                           ; * LOG_SLOT_LEN
                ld   e, a
                ld   d, LOG_TXT >> 8
                ld   b, LOG_MAX
.c:             ld   a, (hl)
                or   a
                jr   z, .t
                ld   (de), a
                inc  hl
                inc  e
                djnz .c
                xor  a
.t:             ld   (de), a
                ld   a, (PANEL_DIRTY)
                or   PD_LOG
                ld   (PANEL_DIRTY), a
                ret
log_drop:       push hl
                ld   hl, LOG_Q + LQ_DROP
                inc  (hl)
                jr   nz, .n
                dec  (hl)                      ; saturate at 255
.n:             pop  hl
                ret

;------------------------------------------------------------------------------
; panel_tick — play_loop / end_screen, once per tick except a turn's input
; tick (D5). Budget rule (B3B-11b): while the tick is still in its FIRST
; frame (SYS_FRAMES == LAST_TICK_FRAME: < 70.9k T used so far) it draws an
; item — any, incl. a whole log message (scroll + line, <= ~21k T) — and
; re-checks: items keep coming until the queue is empty or the 2nd frame has
; begun, so it ends below ~92k T. A tick already in its 2nd frame draws ONE
; small item (HP / ICONS / DEPTH, <= ~4.5k T): the render-bound heavy ticks
; reach ~116k T before the panel (budget.py), a log item there could pass the
; 126k T cap; the log waits for a 1st-frame tick (in a fight: the turn's last,
; light ANIM ticks — budget.py reports the latency).
; D5 footnote: a locked-door bump spends no turn (TURN_PHASE stays INPUT), so
; that tick is not a turn's input tick and its message prints in the SAME
; tick (1st frame permitting).
; panel_step — C = 0: any item, else small items only. Polls the hero's HP /
; MAXHP / potions against what is drawn (sets PD_HP / PD_ICONS), then draws
; the first dirty item in the order HP, LOG (C = 0 only), ICONS, DEPTH, then
; panel_more: MP (D3-9b), INFO (1st frame); FOOD / AMMO cleared until 3E.
; Clobbers: all but IX, IY.
; Cost: ~200 T idle; HP ~4.5k; potion slot ~2.5k; depth ~2.5k; log: scroll up
; to ~7.7k (24 cols) + print6 ~460 T/char (W15) -> 32 chars + scroll ~21k.
;------------------------------------------------------------------------------
panel_tick:
                ld   a, (SYS_FRAMES)
                ld   hl, LAST_TICK_FRAME
                sub  (hl)
                ld   c, a                      ; 0: still in the tick's 1st frame
                jr   nz, panel_step            ; 2nd frame: one small item at most
                call panel_step
                ld   a, (PANEL_DIRTY)
                or   a
                jr   nz, panel_tick            ; more queued: again while in the 1st frame
                ret
panel_step:
                ld   hl, (P_ENTITIES + E_HP)   ; L = HP, H = MAXHP
                ld   de, (PANEL_HP_SH)
                or   a
                sbc  hl, de
                ld   hl, PANEL_DIRTY
                jr   z, .p1
                set  PD_HP_BIT, (hl)
.p1:            call icon_poll                 ; C3-3 (icons.asm): potions, level, slots
                ld   a, (hl)
                or   a
                ret  z
                rrca
                jr   c, item_hp
                bit  PD_LOG_BIT, (hl)
                jr   z, .nl
                inc  c
                dec  c
                jp   z, item_log               ; 1st frame only
.nl:            bit  PD_ICONS_BIT, (hl)
                jp   nz, item_icons_far        ; C3-3: bank 3 (icons3.asm)
                bit  PD_DEPTH_BIT, (hl)
                jp   nz, item_depth
                jp   panel_more                ; C3-3 (icons.asm): INFO; MP / FOOD / AMMO 3D / 3E

;------------------------------------------------------------------------------
; item_hp — HP bar + 2-digit number (row 21, cols 1..6). HL = PANEL_DIRTY.
;------------------------------------------------------------------------------
item_hp:
                res  PD_HP_BIT, (hl)
                ld   a, $80                    ; IC1: HP / MAXHP moved -> the quick potion
                ld   (QS_RECHK), a             ; pick may (icon_poll: a 1st-frame pass)
                ld   hl, (P_ENTITIES + E_HP)
                ld   (PANEL_HP_SH), hl         ; HP and MAXHP as drawn
                ld   d, h
                ld   a, l
                ld   hl, HP_BAR_ADDR
                call bars_draw
                ld   a, (PANEL_HP_SH)
                call num2
                ld   b, STAT_ROW
                ld   e, HP_NUM_COL * 8
                call print6
                ASSERT ((HP_NUM_COL * 8) & 7) == 0 && HP_NUM_COL * 8 + 6 * 2 <= 256   ; print6 x rule
                ld   bc, (STAT_ROW << 8) | HP_BAR_COL
                ld   de, ((HP_NUM_COL + 2 - HP_BAR_COL) << 8) | 1
                jp   pmark_rect

;------------------------------------------------------------------------------
; item_depth — "Dn" at (30, 18) (LVL_DEPTH; the PROTO level 0 shows D1; the
; key icon at (30, 19) arrives with the key in 3F). HL = PANEL_DIRTY.  ~1k T
;------------------------------------------------------------------------------
item_depth:
                res  PD_DEPTH_BIT, (hl)
                ld   a, (LVL_DEPTH)
                or   a
                jr   nz, .d
                inc  a
.d:             add  a, '0'
                ld   hl, P_NUMBUF
                ld   (hl), 'D'
                inc  l
                ld   (hl), a
                inc  l
                ld   (hl), 0
                ld   l, P_NUMBUF & $FF
                ld   b, ICON_ROW
                ld   e, DEPTH_COL * 8
                call print6
                ASSERT ((DEPTH_COL * 8) & 7) == 0 && DEPTH_COL * 8 + 6 * 2 <= 256     ; print6 x rule
                ld   bc, (ICON_ROW << 8) | DEPTH_COL
                ld   de, (2 << 8) | 1
                jp   pmark_rect

panel_hot_end:
                ENT
PANEL_HOT_LEN   EQU panel_hot_end - panel_hot
                ASSERT HOT_COPY + PANEL_HOT_LEN <= HOT_COPY_END
HP_BAR_ADDR     EQU ((SCREEN_BITMAP >> 8) | (STAT_ROW & $18)) << 8 | ((STAT_ROW & 7) << 5) | HP_BAR_COL
                ASSERT PANEL_HP_SH >= LOG_Q + LOG_Q_LEN && PANEL_HP_SH + 2 <= STATE_3B_END
