;==============================================================================
; icons.asm — C3-3 icon bar state, bank 2 (architect D3; game.md §3.3–3.5,
; concept-screen §5 icon states). The slot table is shared with C3-2's
; intent7.asm (bank 7 since D3-7: cursor / shortcuts / FIRE dispatch) and the
; bank-3 panel code.
;
; The panel polls icon_state for the 10 slots against ICON_SH (state | IS_SEL
; as last drawn, HERO_ST) — "polled like HP" — and redraws only what changed:
; a selection move is an attr-only paper change (sel_paint), any other change
; one cold far3 slot_redraw (bank 3, panel.asm) per item. The level digit at
; (31, 19) rides on the same item (LVL vs LVL_SH). Info line: PD_INFO,
; item_info (bank 3) via panel_more. The state / drawing code is bank 3
; (icons3.asm); item_icons_far is panel_step's entry to it.
;==============================================================================

slot_act_tab:
                ; Warrior: Sword, Power Strike, Whirlwind, Daggers, Bow, food, potion, scroll, Bag, -
                DB SA_MELEE, SA_ABIL + 0, SA_ABIL + 1, SA_DAGGERS, SA_BOW
                DB SA_FOOD, SA_POTION, SA_SCROLL, SA_BAG, SA_EMPTY
                ; Mage: Staff, Spark, Firebolt, Frost Shard, Drain Life, Lightning, food, potion, scroll, Bag
                DB SA_MELEE, SA_ABIL + 0, SA_ABIL + 1, SA_ABIL + 2, SA_ABIL + 3
                DB SA_ABIL + 4, SA_FOOD, SA_POTION, SA_SCROLL, SA_BAG
                ASSERT K_KNIGHT == 0 && K_WIZARD == 1
                ; IC1 (pot_sync's forced redraw): quick slot = QS_SLOT0 + HERO_KIND + QS_*
                ASSERT {b slot_act_tab + QS_SLOT0 + QS_FOOD} == SA_FOOD && {b slot_act_tab + QS_SLOT0 + QS_SCROLL} == SA_SCROLL
                ASSERT {b slot_act_tab + ICON_SLOTS + QS_SLOT0 + 1 + QS_FOOD} == SA_FOOD
                ASSERT {b slot_act_tab + ICON_SLOTS + QS_SLOT0 + 1 + QS_SCROLL} == SA_SCROLL

;------------------------------------------------------------------------------
; slot_act — A = slot 0..9 -> A = its SA_* for HERO_KIND (D3-7 T0: bank 2,
; called from bank 3 (icons3 / panel) and bank 7 (intent7); 16-bit index, so
; the table needs no page pad).  Clobbers: A, HL
;------------------------------------------------------------------------------
slot_act:
                ld   l, a
                ld   a, (HERO_KIND)
                or   a
                ld   a, l
                jr   z, .k
                add  a, ICON_SLOTS
.k:             ld   hl, slot_act_tab
                add  a, l
                ld   l, a
                adc  a, h
                sub  l
                ld   h, a
                ld   a, (hl)
                ret

; abil_rank — A = ability index k -> A = its rank 0..3 (ARANK bits 2k..2k+1),
; Z = unlearned.  Clobbers: A, C, HL
abil_rank:
                ld   hl, (ARANK)
                add  a, a
                jr   z, .r
                ld   c, a
.sh:            srl  h
                rr   l
                dec  c
                jr   nz, .sh
.r:             ld   a, l
                and  3
                ret

; item_icons_far — panel_step (HOT_COPY): the icon item, bank 3.
; IC1: A = C = 0 in the tick's 1st frame (panel_step / panel_flush), else != 0.
item_icons_far: ld   a, c
                ld   hl, item_icons
                jp   far3


;------------------------------------------------------------------------------
; icon_poll — panel_step's poll (HOT_COPY): sets PD_ICONS in (HL) when the
; potion count, the level or the icon signature (icon_sig) differs from what
; is drawn, or (IC1, C = 0: a tick's 1st frame) QS_RECHK bit 7 asks for a pass
; (a quick slot pending, or HP / MP moved: the potion pick; set by item_hp,
; item_mp, pot_sync, item_icons). Only these inputs change a slot's state in 3C; 3D's learning /
; rank-up / MP greying must set PD_ICONS itself (or extend icon_sig).
; D3-9b: also MP vs MP_SH (sets PD_MP: casts, regen, potions all redraw the
; MP item without their own dirty bit).
; HL = PANEL_DIRTY, kept; BC kept.  Clobbers: A, DE      ~0.2k T
;------------------------------------------------------------------------------
icon_poll:
                ld   a, (MP_SH)
                ld   e, a
                ld   a, (MP)
                cp   e
                jr   z, .mp
                set  PD_MP_BIT, (hl)
.mp:            ex   de, hl
                call st_sig                    ; D3-8: the 2 status icons (row 21)
                ld   hl, STAT_SH
                cp   (hl)
                jr   nz, .dirty
                ld   a, (P_ENTITIES + E_POT)
                ld   hl, PANEL_POT_SH
                cp   (hl)
                jr   nz, .dirty
                ld   a, (LVL)
                ld   hl, LVL_SH
                cp   (hl)
                jr   nz, .dirty
                ld   a, (QS_RECHK)             ; IC1: bit 7 = an item_icons pass wanted,
                add  a, a                      ; only in a tick's 1st frame (C = 0): a
                jr   nc, .qd                   ; quick slot (big item) / the potion pick
                inc  c
                dec  c
                jr   z, .dirty
.qd:            call icon_sig
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
; st_sig — D3-8: the hero's 2 panel status icons (game.md §6.4, priority HOLD >
; MIND > POISON > WEAK) packed as icon index + 1 (combat_defs.asm SI_*; 0 =
; blank): low nibble = col 30, high nibble = col 31. 0 = no status.
; Keeps BC, DE, HL.  Clobbers: A.   ~0.1k T (STATUS 0: ~40 T)
;------------------------------------------------------------------------------
st_sig:
                ld   a, (ST_FLAGS)
                and  ~(1 << STS_GUARD_BIT) & $FF
                ret  z
                push bc
                push de
                ld   c, a                      ; C = STATUS
                ld   b, 0                      ; B = the sig so far
                and  STS_HOLD                  ; HOLD kind 1..3 = FROZEN / ASLEEP / STUNNED
                call nz, .add                  ; (index + 1 = the kind)
                ld   a, c
                and  STS_MIND
                jr   z, .p
                cp   MIND_FEAR
                ld   a, SI_FEAR
                jr   z, .m
                ld   a, SI_CONFUSED
.m:             call .add
.p:             bit  STS_POISON_BIT, c
                ld   a, SI_POISON
                call nz, .add
                bit  STS_WEAK_BIT, c
                ld   a, SI_WEAK
                call nz, .add
                ld   a, b
                pop  de
                pop  bc
                ret
.add:           ld   e, a                      ; the first goes low, the second high,
                ld   a, b                      ; any further one is dropped
                or   a
                jr   nz, .hi
                ld   b, e
                ret
.hi:            and  $F0
                ret  nz
                ld   a, e
                rlca
                rlca
                rlca
                rlca
                or   b
                ld   b, a
                ret
                ASSERT HOLD_FROZEN == 1 && HOLD_ASLEEP == 2 && HOLD_STUNNED == 3

;------------------------------------------------------------------------------
; panel_more — panel_step's tail (HOT_COPY) after HP / LOG / ICONS / DEPTH:
; HL = PANEL_DIRTY, C = 0 in the tick's 1st frame. The info line (~25k T, a
; whole row of 6x8 text) draws only in a 1st frame, like a log line; MP
; (D3-9b) first; 3E-T9 FOOD (bar + stage word, ~7k T incl. far6: 1st frame
; only, like INFO); AMMO has nothing to draw yet (cleared).
;------------------------------------------------------------------------------
panel_more:
                bit  PD_MP_BIT, (hl)           ; D3-9b: a small item (HP's size), any frame
                jp   nz, item_mp               ; (xp2.asm, after kind_tab)
                inc  c
                dec  c
                jr   nz, .clr                  ; 2nd frame: FOOD / the info line wait
                bit  PD_FOOD_BIT, (hl)
                ld   hl, item_food             ; 3E-T9: R6 (hunger6.asm)
                jp   nz, far6
                ld   hl, PANEL_DIRTY
                bit  PD_INFO_BIT, (hl)
                jr   z, .clr
                res  PD_INFO_BIT, (hl)
                ld   hl, item_info             ; bank 1 (info1.asm)
                jp   far1
.clr:           ld   a, (hl)
                and  PD_LOG | PD_INFO | PD_FOOD ; waiting log / info / food items stay
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
