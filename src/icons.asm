;==============================================================================
; icons.asm — C3-3 icon bar state, bank 2 (architect D3; game.md §3.3–3.5,
; concept-screen §5 icon states). The slot table is shared with C3-2's
; intent3.asm (bank 3: cursor / shortcuts / FIRE dispatch).
;
; The panel polls icon_state for the 10 slots against ICON_SH (state | IS_SEL
; as last drawn, HERO_ST) — "polled like HP" — and redraws only what changed:
; a selection move is an attr-only paper change (sel_paint), any other change
; one cold far3 slot_redraw (bank 3, panel.asm) per item. The level digit at
; (31, 19) rides on the same item (LVL vs LVL_SH). Info line: PD_INFO,
; item_info (bank 3) via panel_more. The state / drawing code is bank 3
; (icons3.asm); item_icons_far is panel_step's entry to it.
;==============================================================================

; item_icons_far — panel_step (HOT_COPY): the icon item, bank 3.
item_icons_far: ld   hl, item_icons
                jp   far3


;------------------------------------------------------------------------------
; icon_poll — panel_step's poll (HOT_COPY): sets PD_ICONS in (HL) when the
; potion count, the level or the icon signature (icon_sig) differs from what
; is drawn. Only these inputs change a slot's state in 3C; 3D's learning /
; rank-up / MP greying must set PD_ICONS itself (or extend icon_sig).
; HL = PANEL_DIRTY, kept; BC kept.  Clobbers: A, DE      ~0.15k T
;------------------------------------------------------------------------------
icon_poll:
                ex   de, hl
                ld   a, (P_ENTITIES + E_POT)
                ld   hl, PANEL_POT_SH
                cp   (hl)
                jr   nz, .dirty
                ld   a, (LVL)
                ld   hl, LVL_SH
                cp   (hl)
                jr   nz, .dirty
                call icon_sig
                ld   hl, ICON_SIG
                cp   (hl)
                ex   de, hl
                ret  z
                set  PD_ICONS_BIT, (hl)
                ret
.dirty:         ex   de, hl
                set  PD_ICONS_BIT, (hl)
                ret

; icon_sig — A = SEL_SLOT | $10 if DAGGERS = 0 | $20 if the bow can shoot
; (HAS_BOW and ARROWS > 0) | $40 in ICON MODE.  Clobbers: A, L
icon_sig:
                ld   a, (DAGGERS)
                or   a
                ld   a, (SEL_SLOT)
                jr   nz, .d
                or   $10
.d:             ld   l, a
                ld   a, (HAS_BOW)
                or   a
                jr   z, .b
                ld   a, (ARROWS)
                or   a
                jr   z, .b
                set  5, l
.b:             ld   a, (ICON_MODE)
                or   a
                jr   z, .m
                set  6, l
.m:             ld   a, l
                ret
                ASSERT ICON_SLOTS <= 16

;------------------------------------------------------------------------------
; panel_more — panel_step's tail (HOT_COPY) after HP / LOG / ICONS / DEPTH:
; HL = PANEL_DIRTY, C = 0 in the tick's 1st frame. The info line (~25k T, a
; whole row of 6x8 text) draws only in a 1st frame, like a log line; MP /
; FOOD / AMMO have nothing to draw until 3D / 3E (cleared).
;------------------------------------------------------------------------------
panel_more:
                bit  PD_INFO_BIT, (hl)
                jr   z, .clr
                inc  c
                dec  c
                jr   nz, .clr                  ; 2nd frame: the info line waits
                res  PD_INFO_BIT, (hl)
                ld   hl, item_info             ; bank 1 (info1.asm)
                jp   far1
.clr:           ld   a, (hl)
                and  PD_LOG | PD_INFO          ; waiting log / info items stay
                ld   (hl), a
                ret

;------------------------------------------------------------------------------
; print6x — print6 of string A (TX_*, a token stream in the text block) at
; row B, pixel x E (multiple of 8; x + 6n <= 256: info lines are <= 42
; chars). Pages BANK_TEXT around tx_ptr + print6g and hands $C000 back as it
; found it (callers in bank 3). Out: E = x after the text.
; Clobbers: A, BC, D, HL.
;------------------------------------------------------------------------------
print6x:
                ld   c, a
                ld   a, (PORT_7FFD_SHADOW)
                push af                        ; caller's page
                push bc
                ld   a, BANK_TEXT
                call page_bank                 ; (A, BC)
                pop  bc                        ; B = row, C = id
                ld   a, c
                push bc
                call tx_ptr                    ; HL = the stream
                pop  af                        ; A = row
                ld   b, h
                ld   c, l
                ld   hl, pre_get
                call print6g
                pop  af
                jp   restore_page              ; (keeps BC, DE)

; pre_get — print6x's getter: tk_get, or with PRE_N = 1 (item_info in ICON
; MODE) a ">" first, and the string's char 15 dropped if it is a space, so
; the line keeps its 42 chars and the fields stay on chars 16 / 28 (every
; info name is <= 15 chars, padded). PRE_N counts the chars given + 1.
; Getter rules as tk_get (print6g): A out, state BC, keeps DE.
pre_get:
                ld   hl, PRE_N
                ld   a, (hl)
                or   a
                jp   z, tk_get                 ; no prefix
                inc  (hl)
                dec  a
                jr   nz, .c
                ld   a, '>'
                ret
.c:             cp   16                        ; 16 given: the string's char 15 next
                jp   nz, tk_get
                call tk_get
                or   a
                ret  z
                cp   ' '
                ret  nz
                jp   tk_get
