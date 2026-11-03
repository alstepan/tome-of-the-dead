;==============================================================================
; xp7.asm — D3-9b, bank 7: MP regen, XP level-up, learn / rank-up (game.md
; §4, §4.1, §5, §7). Events only (once per turn / per level / per book): no
; data here (bank-7 rule) — the gains are immediates, the thresholds are the
; bank-2 xpn_tab (the single XP_NEXT table, also read by bank-1 item_info).
;==============================================================================

MP_REG_W        EQU 8               ; game.md §4: Warrior +1 MP per 8 turns
MP_REG_M        EQU 6               ; Mage period 6 (B20, game.md 4.0)
LUP_W_HP        EQU 4               ; §4.1 level-up: Warrior max HP +4, max MP +1
LUP_W_MP        EQU 1
LUP_M_HP        EQU 3               ; Mage max HP +3, max MP +2
LUP_M_MP        EQU 2
LVL_ATK1        EQU 4               ; §4.1 steps: L4 atk +1, L6 eva +1, L8 atk +1
LVL_EVA1        EQU 6
LVL_ATK2        EQU 8
XPF_LVL         EQU 0               ; xp_turn's C flags: a level was gained
XPF_ATK         EQU 1               ; an atk step
XPF_EVA         EQU 2               ; an eva step

;------------------------------------------------------------------------------
; xp_turn — end_turn's regen + level-up step (game.md §2.2 end of turn:
; "... hunger -> regen -> ..."), a plain call (bank 7), skipped when the hero
; is DYING (end_turn tests it first).
; MP regen: MP_RG counts turns; at MP_PER (3E-T8 hero_recalc: the class period,
; x 1/2 Mana / Scarab amulet, x 2 Plate) MP += 1 + MAXMP div 16 (to MAXMP) and
; MP_RG = 0. While WEAK (ST_FLAGS slot 0) the counter is frozen (§7 "halted");
; 3E-T9: the test is MP_HOLD, written by hunger_turn (R6) right before: WEAK
; (status or hunger) -> frozen; HUNGRY -> frozen on odd TURN_COUNTER (period x2).
; Level-up (XP_UP set by deal_hit's award): while LVL < LVL_MAX and XP >=
; xpn_tab[LVL - 1]: LVL + 1, max/current HP and MP + the class gains; then
; hero_recalc (R6, 3E-T8) rewrites the hero's kind_tab KT_ATK / KT_EVA columns
; = base + the L4 / L8 atk and L6 eva steps (from LVL: never counted twice) +
; gear (0 T on every to-hit roll). Several levels at once loop;
; the log gets ONE "YOU REACH LEVEL n!" (the final n) + one line per step kind
; gained, then LT_HOLD (end_turn's drain: the next turn waits for the lines).
; PD_INFO when the Bag's line (LV / XP) is selected; PD_MP + PD_INFO on a level.
; Clobbers: A, BC, DE, HL.  Cost (tests/xp.py C): regen ~0.6k T incl. far7;
; stats ~0.3k T per level; the lines ~4.5k + ~1.1k per step line.
;------------------------------------------------------------------------------
xp_turn:
                ld   a, (MP_HOLD)              ; 3E-T9 (hunger_turn, just before): WEAK
                or   a                         ; (status or hunger) or a HUNGRY odd turn:
                jr   nz, .lv                   ; no regen, counter held (-1 B vs ST_FLAGS)
                ld   a, (MP_PER)               ; 3E-T8: hero_recalc's period (class 8 / 6,
                ld   b, a                      ; Mana / Scarab x 1/2, Plate x 2; -6 B)
                ld   hl, MP_RG
                inc  (hl)
                ld   a, (hl)
                cp   b
                jr   c, .lv
                ld   (hl), 0
                ld   hl, MAXMP
                ld   a, (hl)
                rrca
                rrca
                rrca
                rrca
                and  $0F
                inc  a                         ; B20: gain = 1 + MAXMP div 16
                ld   b, a
                ld   a, (MP)
                add  a, b                      ; MP <= MAXMP <= 99: no carry
                cp   (hl)
                jr   c, .rg
                ld   a, (hl)                   ; clamp to MAXMP (the panel polls MP: no PD_MP)
.rg:            ld   (MP), a
.lv:            ; fall through
;------------------------------------------------------------------------------
; xp_level — the level-up check + its lines (XP_UP != 0), only while the tick
; is in its 1st frame (<= ~71k T elapsed + <= ~17k T here incl. 3E-T8 hero_recalc: never past the
; cap); else XP_UP stays set and the next INPUT tick's turn_input (or the next
; end_turn) retries. Clobbers: A, BC, DE, HL.  ~0.1k T when it defers.
;------------------------------------------------------------------------------
xp_level:
                ld   hl, XP_UP
                ld   a, (hl)
                or   a
                ret  z
                ld   a, (SYS_FRAMES)
                ld   de, LAST_TICK_FRAME
                ex   de, hl
                cp   (hl)
                ret  nz                        ; 2nd frame: later
                ex   de, hl
                ld   (hl), 0
                ld   a, (SEL_SLOT)
                call slot_act                  ; bank 2 (A, HL)
                cp   SA_BAG
                jr   nz, .nb
                ld   hl, PANEL_DIRTY           ; the Bag's line shows XP: refresh it
                set  PD_INFO_BIT, (hl)
.nb:            ld   c, 0                      ; C = XPF_* gained
                ld   a, (LVL)
.chk:           cp   LVL_MAX
                jr   nc, .msg
                ld   b, a                      ; B = LVL (1..8)
                add  a, a
                add  a, (xpn_tab - 2) & $FF    ; row LVL - 1 = the total XP for LVL + 1
                ld   l, a
                adc  a, (xpn_tab - 2) >> 8
                sub  l
                ld   h, a
                ld   e, (hl)
                inc  hl
                ld   d, (hl)
                ld   hl, (XP)
                or   a
                sbc  hl, de
                jr   c, .msg                   ; below the next threshold
                inc  b
                ld   a, b
                ld   (LVL), a
                set  XPF_LVL, c
                ld   a, (HERO_KIND)
                or   a
                ld   de, (LUP_W_HP << 8) | LUP_W_MP
                jr   z, .g
                ld   de, (LUP_M_HP << 8) | LUP_M_MP
.g:             ld   hl, P_ENTITIES + E_HP     ; HP, MAXHP += D (E_MAXHP = E_HP + 1)
                ld   a, (hl)
                add  a, d
                ld   (hl), a
                inc  hl
                ld   a, (hl)
                add  a, d
                ld   (hl), a
                ld   hl, MP                    ; MP, MAXMP += E (MAXMP = MP + 1)
                ld   a, (hl)
                add  a, e
                ld   (hl), a
                inc  l
                ld   a, (hl)
                add  a, e
                ld   (hl), a
                ASSERT MAXMP == MP + 1 && (MP >> 8) == (MAXMP >> 8)
                ld   a, b                      ; the step lines (3E-T8: hero_recalc applies
                ld   l, 1 << XPF_ATK           ; the steps from LVL: no kind_tab write here)
                cp   LVL_ATK1
                jr   z, .st
                cp   LVL_ATK2
                jr   z, .st
                ld   l, 1 << XPF_EVA
                cp   LVL_EVA1
                jr   nz, .nx
.st:            ld   a, l
                or   c
                ld   c, a
.nx:            ld   a, b
                jr   .chk
.msg:           bit  XPF_LVL, c
                ret  z
                ld   a, c
                and  (1 << XPF_ATK) | (1 << XPF_EVA)
                jr   z, .nr                    ; no step: nothing recalc derives changed
                push bc
                ld   hl, hero_recalc           ; R6: atk / eva = base + steps(LVL) + gear
                call far6
                pop  bc
.nr:
                ld   a, SFX_LEVELUP            ; SND-5 (F only)
                call sfx_req
                ld   hl, DN_SLOT + DS_FLG      ; LVL-FLOATER: the hero's "+LVL" number is owed
                set  DSF_LVL, (hl)             ; (render-only: dn_cls ranks it, dn_lvt picks the text)
                ld   hl, PANEL_DIRTY
                set  PD_INFO_BIT, (hl)         ; (a new XP_NEXT; also PD_MP: max changed)
                set  PD_MP_BIT, (hl)
                push bc
                ld   de, MSG_BUF
                ld   a, TX_XP_REACH
                call msg_cat                   ; "YOU REACH LEVEL "
                ld   a, (LVL)
                add  a, '0'
                ld   (de), a
                inc  de
                ld   a, '!'
                ld   (de), a
                inc  de
                call msg_end
                pop  bc
                bit  XPF_ATK, c
                jr   z, .ne
                push bc
                ld   a, TX_XP_ATK
                call msg_push                  ; "YOU STRIKE TRUER" (AF, BC, DE, HL)
                pop  bc
.ne:            bit  XPF_EVA, c
                ld   a, TX_XP_EVA
                call nz, msg_push              ; "YOU FEEL NIMBLE"
                ld   hl, LOG_TURN              ; end_turn's drain: hold the next turn
                set  LT_HOLD_BIT, (hl)         ; until these lines are drawn
                ret
                ASSERT TXL_XP_REACH + 2 <= LOG_MAX

;------------------------------------------------------------------------------
; abil_learn — the read-time book entry's apply step (game.md §5; the READ verb
; and the choice of k are fx_book's, R6). A = class ability index k (Mage 0..4 =
; ABL_*, Warrior 0..1 = ABL_* - ABL_POWER). Rank 0 -> 1: "YOU LEARN <NAME>!";
; rank 1..2 -> +1: "<NAME> RISES TO RANK n"; rank 3: nothing (L = 0).
; ARANK += 1 << 2k (BOOK_DRY bits 10-11 untouched), PD_ICONS | PD_INFO (the
; slot's outline / info line).
; far7-callable (no IX use). Out: L = the new rank (0 = already at rank 3).
; Clobbers: A, BC, DE, HL.   ~1k T (one log line)
;------------------------------------------------------------------------------
abil_learn:
                ld   b, a                      ; B = k
                call abil_rank                 ; bank 2: A = rank (A, C, HL)
                ld   c, b                      ; C = k
                ld   b, a                      ; B = old rank
                cp   RANK_MAX
                ld   l, 0
                ret  nc
                ld   hl, 1                     ; 1 << 2k
                ld   a, c
                or   a
                jr   z, .a
.sh:            add  hl, hl
                add  hl, hl
                dec  a
                jr   nz, .sh
.a:             ld   de, (ARANK)
                add  hl, de
                ld   (ARANK), hl
                ld   hl, PANEL_DIRTY
                ld   a, (hl)
                or   PD_ICONS | PD_INFO
                ld   (hl), a
                ld   a, (HERO_KIND)            ; name = TX_AB_SPARK + ABL_*
                or   a
                ld   a, c
                jr   nz, .m
                add  a, ABL_POWER
.m:             add  a, TX_AB_SPARK
                ld   c, a                      ; C = the name's TX
                push bc                        ; (B = the old rank)
                ld   de, MSG_BUF
                ld   a, b
                or   a
                jr   nz, .up
                ld   a, TX_BK_LEARN
                call msg_cat                   ; "YOU LEARN "
                pop  bc
                push bc
                ld   a, c
                call msg_cat                   ; + name
                ld   a, '!'
                jr   .end
.up:            ld   a, c
                call msg_cat                   ; name
                ld   a, TX_BK_RISES
                call msg_cat                   ; + " RISES TO RANK "
                pop  bc
                push bc
                ld   a, b
                add  a, '1'                    ; the new rank digit
.end:           ld   (de), a
                inc  de
                call msg_end
                pop  bc
                ld   l, b
                inc  l
                ret
                ASSERT TX_AB_FIREBOLT == TX_AB_SPARK + ABL_FIREBOLT && TX_AB_WHIRL == TX_AB_SPARK + ABL_WHIRL
                ASSERT TXL_AB_POWER + TXL_BK_RISES + 1 <= LOG_MAX && TXL_BK_LEARN + TXL_AB_POWER + 1 <= LOG_MAX
