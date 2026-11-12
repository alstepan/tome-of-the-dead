;==============================================================================
; PANEL ENGINE, bank-2 part (B3B-11): the log item, items, bars, numbers, the
; print6 source switch. The rest of the hot panel code is boot-copied to
; HOT_COPY (panel_hot.asm); both are uncontended bank-2 RAM, split only by
; what fits HOT_COPY.
;==============================================================================
;------------------------------------------------------------------------------
; item_log — the oldest pending message as ONE item (B3B-11b: no chunked
; steps): log_scroll (row 23 -> 22, row 23 cleared), then the whole line on
; row 23 (B3B-13: print6t, the ring holds token streams), next ring slot,
; LOG_QN -= 1, PD_LOG cleared at 0.
; HL = PANEL_DIRTY. Clobbers: all but IX, IY.  ~23k T for 32 chars (W15)
;------------------------------------------------------------------------------
item_log:
                ld   a, (LOG_QN)
                or   a
                jr   nz, .go
                res  PD_LOG_BIT, (hl)
                ret
.go:            FARB0 log_scroll               ; C-T6: bank 0 (logsc0.asm; +~0.25k T a log line)
                ld   a, (LOG_Q + LQ_RD)
                rrca
                rrca                           ; * LOG_SLOT_LEN
                ld   l, a
                ld   h, LOG_TXT >> 8
                ld   b, LOG_ROW + 1
                ld   e, 0                      ; (x 0: a multiple of 8; 32 chars = 192 px)
                call print6t
                ASSERT LOG_ROW + 1 < 24 && 6 * LOG_MAX <= 256
                ld   a, e
                add  a, 7
                rrca
                rrca
                rrca
                and  $1F                       ; cols holding ink now (row 23 was cleared)
                ld   hl, HUD4_EXT + 3          ; row 23
                ld   (hl), a
                ld   l, (HUD4_PW + 3) & $FF
                cp   (hl)
                jr   c, .w
                ld   (hl), a
.w:             ld   a, 1
                ld   (PRES_ANY), a
                ld   hl, LOG_TURN              ; T7: LT_SERVED (end_turn: the log was
                set  0, (hl)                   ; not starved this turn)
                ASSERT LT_SERVED == 1
                ld   hl, LOG_Q + LQ_RD
                ld   a, (hl)
                inc  a
                and  LOG_SLOTS - 1
                ld   (hl), a
                ld   hl, LOG_QN
                dec  (hl)
                ret  nz
                ld   hl, PANEL_DIRTY
                res  PD_LOG_BIT, (hl)
                ret
                ASSERT (HUD4_EXT >> 8) == ((HUD4_PW + 3) >> 8)

; item_icons: C3-3, icons.asm.

;------------------------------------------------------------------------------
; print6t — print6 of a dictionary-token stream (B3B-13; format: tools/
; textpack.py, docs/memory-map.md "Text (B3B-13)"): HL = stream (0-terminated,
; readable while BANK_TEXT is paged: LOG_TXT, MSG_BUF, the text block itself),
; B = char row, E = pixel x (multiple of 8), decoded length n: x + 6n <= 256.
; Pages BANK_TEXT (the dictionary) around print6g + tk_get and hands $C000
; back as it found it (callers in bank 3: panel_flush).
; Out: E = x after the last char.  Clobbers: A, BC, D, HL.
; Cost: print6 + 35 T per literal char (tk_get) + print6g's ~0.3k patch +
; ~0.2k paging (W17 measures it).
;------------------------------------------------------------------------------
print6t:
                ld   a, (PORT_7FFD_SHADOW)
                push af                        ; caller's page
                push bc                        ; B = row
                push hl
                ld   a, BANK_TEXT
                call page_bank                 ; (A, BC)
                pop  bc                        ; BC = the stream (tk_get state)
                pop  af                        ; A = row (was B)
                ld   hl, tk_get
p6_tail:        call print6g                   ; (RECLAIM-D: print6x's tail too)
                pop  af
                jp   restore_page              ; (keeps BC, DE)

;------------------------------------------------------------------------------
; tk_get — the dictionary-token decoder, print6g's getter (B3B-13). State BC
; = stream pointer. Out: A = next char 32..127, 0 = end (never called again
; after it: a stream always ends in the main mode). Keeps DE; clobbers H(L).
; Stream bytes: 0 end, 32..127 literal, t >= 128 token -> dictionary entry
; t - 128 (tx_dict byte = its offset in the tx_entries page; 2+ literal
; chars, the last with bit 7 set, no
; nesting). Two modes switched by the opcode at .sw: main (TK_MAIN `ld h, n`,
; falls through to the stream) and entry (TK_ENTRY `jr .ent`; BC walks the
; entry, the stream pointer parked in .back+1).
; SMC: .sw (opcode), .back+1 (parked stream pointer). NEVER call from the ISR (the SMC
; mode switch is not re-entrant: an interrupt mid-entry would corrupt the walk).
; Cost per char (+17 T call, vs 17 T for the inline fetch): literal 35 T,
; entry char 40 T, an entry's last char 81 T, token 125 T + its first char.
;------------------------------------------------------------------------------
TK_MAIN         EQU $26                        ; ld h, n: operand = the jr offset, harmless
TK_ENTRY        EQU $18                        ; jr e
tk_get:
.sw:            DB   TK_MAIN, .ent - (.sw + 2) ; SMC: TK_MAIN / TK_ENTRY (= jr .ent)
                ld   a, (bc)
                inc  bc
                or   a
                ret  p                         ; 0 = end, 32..127 = literal
                ld   (.back + 1), bc           ; park the stream
                add  a, (tx_dict - $80) & $FF  ; w2d: tx_dict is a byte per token
                ld   l, a
                adc  a, (tx_dict - $80) >> 8
                sub  l
                ld   h, a                      ; HL = tx_dict + t - 128
                ld   c, (hl)                   ; the entry's offset in its page
                ld   b, tx_entries >> 8        ; BC = the entry (all in one page)
                ld   a, TK_ENTRY
                ld   (.sw), a
.ent:           ld   a, (bc)
                inc  bc
                or   a
                ret  p                         ; not the entry's last char
                and  $7F
.back:          ld   bc, 0                     ; SMC: the parked stream pointer
                ld   h, a
                ld   a, TK_MAIN
                ld   (.sw), a
                ld   a, h
                ret

;------------------------------------------------------------------------------
; print6g — print6 fed by a getter (B3B-13: print6t + tk_get use it): HL =
; getter (out A = next char 32..127 only, 0 = end; its state in BC; keeps DE;
; may clobber HL), BC = its initial
; state, A = char row, E = pixel x (x & 7 = 0). Patches print6's 4 fetch
; sites to `call getter` (print6 puts the inline fetch back by itself).
; Out / clobbers: as print6.  +23 T per char vs the inline fetch.
; p6_inline — restore the inline `ld a, (bc) / inc bc / nop` fetch sites.
; Keeps B, C, E, HL.  Clobbers: A, D.
;------------------------------------------------------------------------------
print6g:
                push af
                push bc
                push de
                ex   de, hl                    ; DE = getter
                ld   hl, P6_SITE0
                ld   c, P6_SITES
.s:             ld   (hl), $CD                 ; call getter
                inc  hl
                ld   (hl), e
                inc  hl
                ld   (hl), d
                ld   a, l
                add  a, P6_SITE_STEP - 2
                ld   l, a
                jr   nc, .n
                inc  h
.n:             dec  c
                jr   nz, .s
                pop  de
                pop  bc
                pop  af
                jp   print6_go
p6_inline:
                push hl
                push bc
                ld   hl, P6_SITE0
                ld   d, P6_SITES
.s:             ld   (hl), P6_LDBC
                inc  hl
                ld   (hl), P6_INCBC
                inc  hl
                ld   (hl), 0                   ; nop
                ld   bc, P6_SITE_STEP - 2
                add  hl, bc
                dec  d
                jr   nz, .s
                pop  bc
                pop  hl
                ret

; log_scroll: C-T6, bank 0 (logsc0.asm, FARB0 from item_log; it made room for the mirror blit).

; bars_draw / num2: after kind_tab since MEM-SND (bars2.asm: kind_tab ALIGN-pad headroom).
