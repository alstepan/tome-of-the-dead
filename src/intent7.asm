;==============================================================================
; intent7.asm — C3-2 icon bar logic, bank 7 since D3-7 T0 (was intent3.asm,
; bank 3; moved for bank-3 relief). Cold: entered only on an event — a cursor
; step, a slot shortcut, an icon use; game.md §3.1 / §3.5. INCLUDEd by
; bank7.asm, so its rules hold here: no data, no SMC, far7 entries from bank 2
; / bank 3 (intent_tick: sel_key; new_game: hero_st_init), plain calls from
; bank-7 code (tpt_intent: use_icon; intent_icon7: cursor_step); bank-3
; targets via far3 (do_attack, abil_load). The per-tick FIRE
; machine is intent_tick (io.asm, bank 2); the movement rules tpt_intent.
;
; Slot actions (SA_*) by class, one byte per slot (game.md §3.5). The panel
; draws its own bars (panel.asm bar_knight / bar_wizard, C3-3); these say
; what FIRE does and whether the cursor may stop there.
;==============================================================================

; SA_* (hero_defs.asm), slot_act_tab / slot_act / abil_rank: bank 2 (icons.asm,
; D3-7 T0: moved from icons3.asm), shared with the bank-3 icon / panel code.

;------------------------------------------------------------------------------
; slot_ok — A = slot -> NZ if the cursor may stop there (not empty, not an
; unlearned ability: game.md §3.5; greyed icons are selectable), E = SA_*.
; Clobbers: A, BC (B kept), DE, HL
;------------------------------------------------------------------------------
slot_ok:
                call slot_act
                ld   e, a
                or   a
                ret  z                         ; SA_EMPTY
                sub  SA_ABIL
                jp   nc, abil_rank
                or   a                         ; NZ
                ret
;------------------------------------------------------------------------------
; cursor_step — intent_icon7 (plain call), A = +1 / -1: move SEL_SLOT to the next selectable slot
; that way, wrapping 10 -> 1 / 1 -> 10 (none other: unchanged). No turn.
; Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
cursor_step:
                ld   c, a
                ld   a, (SEL_SLOT)
                ld   b, ICON_SLOTS - 1
.l:             add  a, c
                cp   ICON_SLOTS
                jr   c, .in
                ld   a, ICON_SLOTS - 1         ; -1 -> 9
                bit  7, c
                jr   nz, .in
                xor  a                         ; 10 -> 0
.in:            push bc                        ; slot_ok clobbers C (abil_rank)
                push af
                call slot_ok
                pop  hl                        ; H = the slot (A of the push)
                ld   a, h
                pop  bc
                jr   nz, .set
                djnz .l
                ret
.set:           ld   hl, SEL_SLOT
                cp   (hl)
                ret  z                         ; SND-5b: wrapped onto itself (the only stop)
                ld   (hl), a
                ld   a, SFX_MENU               ; the main menu's navigation effect
                jp   sfx_req

;------------------------------------------------------------------------------
; sel_key — far7 from intent_tick (bank 2), A = shortcut 1..10 (key 1..9, 0): select that slot if the
; cursor may stop there; an unlearned ability prints NOT LEARNED. No turn.
; Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
sel_key:
                dec  a
                ld   b, a
                call slot_ok
                ld   a, b
                jr   z, .no
                ld   (SEL_SLOT), a
                ret
.no:            ld   a, e
                cp   SA_ABIL
                ret  c                         ; an empty slot: nothing
                ld   a, TX_NOT_LEARNED
                jp   msg_push

;------------------------------------------------------------------------------
; use_icon — tpt_intent (plain call, both bank 7; IX = hero, live list built):
; FIRE on the selected slot. Out: L = 1 turn used; L bit 0 = 0 refused (no
; turn): IC_REFUSED with a message (ic_refuse; NO TARGET included), 0 silent.
; use_slot's handlers may also return IC_NOTGT (NO TARGET, line not pushed):
; use_icon turns it into the line, or into a stumble on the reversed path. Bank 7 holds no data (gfx_integrity), so the SA_* dispatch is a
; cp chain, not a jump table (about the bytes of the 18-B DW table + its
; index code it replaces; cold: one use per FIRE).
; Clobbers: all but IX, IY.
;------------------------------------------------------------------------------
use_icon:
                ld   a, (SEL_SLOT)
                call slot_act                  ; bank 2
                ; D3-8: a CONFUSED hero's facing actions (melee, abilities but
                ; Whirlwind, throw, bow) are reversed 1 in 3 (never mid-ladder: conf_roll): turn
                ; around, then use it. Refused that way: a refusal with a line
                ; (L = IC_REFUSED: no MP / ammo, unlearned, AFRAID — not the
                ; direction's fault) faces back, no turn; one the direction
                ; caused (L = IC_NOTGT: melee / power attack NO TARGET; 0: the
                ; silent act_begin lead col 0 / 31) -> YOU STUMBLE instead of
                ; the line, the turn is spent (game.md §2.3 / §6.4)
                cp   SA_ABIL
                jr   nc, .fa
                cp   SA_MELEE
                jr   z, .fa
                cp   SA_DAGGERS
                jr   z, .fa
                cp   SA_BOW
                jr   nz, .go
.fa:            ld   b, a
                cp   SA_ABIL + ABL_WHIRL - ABL_POWER
                jr   nz, .rl
                ld   a, (HERO_KIND)            ; D3-8f (game.md §6.4.2 R4): the Warrior's
                or   a                         ; Whirlwind never rolls (it strikes both
                ld   a, b                      ; sides): no target = the plain refusal
                jr   z, .go
.rl:            call conf_roll                 ; status7.asm (keeps B)
                ld   a, b
                jr   nc, .go
                ld   a, (ix+E_FLAGS)
                xor  EF_LEFT
                ld   (ix+E_FLAGS), a
                ld   a, b
                call use_slot
                ld   a, l
                dec  a
                ret  z                         ; L = 1: used
                cp   IC_REFUSED - 1
                jr   z, .back                  ; IC_REFUSED: no turn, facing restored
                call h_stumble                 ; 0 / IC_NOTGT: the direction's fault
                ld   l, 1
                ret
.back:          ld   a, (ix+E_FLAGS)
                xor  EF_LEFT
                ld   (ix+E_FLAGS), a
                ret                            ; (L = IC_REFUSED)
.go:            call use_slot                  ; not reversed: IC_NOTGT -> the line
                ld   a, l
                cp   IC_NOTGT
                ret  nz
                ld   a, TX_NO_TARGET
                jr   ic_refuse
; use_slot — use_icon's dispatch, A = SA_*.
use_slot:
                cp   SA_ABIL
                jp   nc, ic_abil               ; A = SA_ABIL + k
                cp   SA_MELEE
                jr   z, ic_melee
                cp   SA_DAGGERS
                jr   z, ic_daggers
                cp   SA_BOW
                jr   z, ic_bow
                cp   SA_POTION
                jr   z, ic_potion
                ld   e, TX_NO_FOOD             ; 3E: food
                cp   SA_FOOD
                jr   z, .rf
                ld   e, TX_NO_SCROLL           ; 3E: scrolls
                cp   SA_SCROLL
                jr   z, .rf
                cp   SA_BAG
                jr   nz, ic_none               ; SA_EMPTY
                jp   page_run                  ; 3E-T2: the bag page (lowram.asm); 3E-T8:
                                               ; L = page_post's (1: a verb spent the turn)
.rf:            ld   a, e
                jr   ic_no
; ic_no_mana — SND-5: the NO MANA refusal (abil_spell / abil_melee); plays FIZZ (= NO).
ic_no_mana:     ld   a, TX_NO_MANA
; ic_no — SND-5b: a 'nothing to use' refusal (no potion / food / scroll / bag /
; daggers / bow / arrows / mana) = ic_refuse + the shared NO effect (SFX_NO ==
; SFX_FIZZ); A = the TX_ line.
ic_no:          push af
                ld   a, SFX_NO
                call sfx_req
                pop  af
ic_refuse:      call msg_push
                ld   l, IC_REFUSED
                ret
ic_none:        ld   l, 0
                ret
                ASSERT SA_EMPTY == 0 && SA_ABIL == SA_COUNT - 1 && SA_BAG < SA_ABIL
IC_REFUSED      EQU $80                        ; ic_refuse's L: refused with a line
                                               ; (bit 0 = 0: tpt_intent's rrca test)
IC_NOTGT        EQU $82                        ; NO TARGET, line not yet pushed: use_icon
                                               ; pushes it, or stumbles if reversed
                ASSERT (IC_NOTGT & 1) == 0 && IC_NOTGT != IC_REFUSED

; melee (sword / staff): the nearest hostile in reach on the faced side, else
; close the faced door (game.md §2.3, replaces the 3B key C), else NO TARGET.
; Not from mid-ladder.
ic_melee:
                call on_ladder
                jr   z, .nt
                ld   a, 1
                bit  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   z, .f
                ld   a, $FF
.f:             ld   (TMP6), a
                call find_target               ; bank 7: A = slot / $FF
                cp   $FF
                jr   z, .door
                ld   b, a
                call fear_chk                  ; D3-8: FEAR: no melee (illegal, no turn)
                ld   a, TX_ST_AFRAID
                jr   z, ic_refuse
                ld   a, b
                ld   hl, do_attack             ; turn3.asm, bank 3 (A = target slot)
                call far3
                call melee_bonk                ; D3-7 slot: the Mage staff bonk (abil_melee7.asm)
                ld   l, 1
                ret
.door:          call try_close                 ; lowram: CF = 1 closed
                ld   l, 1
                ret  c
.nt:            ld   l, IC_NOTGT               ; use_icon: the line, or a stumble
                ret

; potion (quick slot): E_POT (= the bag's potions, pot_sync) 0 -> NO POTION;
; else pot_quaff (bank 3): the lowest potion type's effect, 1 turn; Heal at
; full HP / Mana at full MP: refused, no turn, no message.
ic_potion:
                ld   a, (ix+E_POT)
                or   a
                ld   a, TX_NO_POTION
                jr   z, ic_no
                jp   ic_quaff

ic_daggers:
                ld   a, (DAGGERS)
                or   a
                ld   a, TX_NO_DAGGERS
                jr   z, ic_no
                ld   a, ABL_DAGGER
                jr   ic_disp

ic_bow:
                ld   a, (HAS_BOW)
                or   a
                ld   a, TX_NO_BOW
                jr   z, ic_no
                ld   a, (ARROWS)
                or   a
                ld   a, TX_NO_ARROWS
                jr   z, ic_no
                ld   a, ABL_BOW
                jr   ic_disp

; ic_abil — A = SA_ABIL + k (k = the class's ability index, ARANK bits
; 2k..2k+1): unlearned -> NOT LEARNED; else ABL_* = k (Mage: Spark ..
; Lightning) or ABL_POWER + k (Warrior: Power Strike, Whirlwind).
ic_abil:
                sub  SA_ABIL
                ld   b, a                      ; k
                call abil_rank                 ; bank 2 (A, C, HL)
                ld   a, TX_NOT_LEARNED
                jr   z, ic_refuse
                ld   a, (HERO_KIND)
                or   a
                ld   a, b
                jr   nz, ic_disp               ; Mage
                add  a, ABL_POWER              ; Warrior
                ASSERT K_KNIGHT == 0 && ABL_SPARK == 0 && ABL_WHIRL == ABL_POWER + 1
; ic_disp — A = ABL_*: abil_load (bank 3, rank3.asm) fills ABIL_DESC (the
; ab_def row + the rank / ammo row) and returns L = its ABF_* flags, B = the
; ABL_* (far3 passes BC / L out); dispatch by the flags: ABF_MELEE ->
; abil_melee, ABF_AMMO -> abil_ammo, else (ABF_SPELL) -> abil_spell. Each:
; IX = hero, B = ABL_*, ABIL_DESC loaded -> L = 1 turn used / IC_REFUSED (a line) /
; IC_NOTGT (abil_melee: no target, no line yet) / 0 (silent) refused.
ic_disp:
                ld   hl, abil_load
                call far3
                bit  ABF_MELEE_BIT, l
                jr   z, .nm
                call fear_chk                  ; D3-8: FEAR: no Power Strike / Whirlwind
                ld   a, TX_ST_AFRAID
                jp   z, ic_refuse
                jp   abil_melee
.nm:            bit  ABF_AMMO_BIT, l
                jp   nz, abil_ammo
                jp   abil_spell
ABF_MELEE_BIT   EQU 6
ABF_AMMO_BIT    EQU 7
                ASSERT ABF_MELEE == 1 << ABF_MELEE_BIT && ABF_AMMO == 1 << ABF_AMMO_BIT

;------------------------------------------------------------------------------
; hero_st_init — far7 from new_game (bank 3): the C3-2 intent state + the start kit counters the
; icon handlers read (game.md §4: Warrior 3 daggers, no bow, 0 arrows; no
; ability learned). STICK / KEYTAB / JOY_MODE persist (boot), ICON_SH is the
; panel's (C3-3), LVL / XP / MP 3D's.  Clobbers: A, B, HL
;------------------------------------------------------------------------------
hero_st_init:
                xor  a
                ld   hl, SEL_SLOT              ; SEL_SLOT, FIRE_ST, FIRE_T
                ld   (hl), a
                inc  l
                ld   (hl), a
                inc  l
                ld   (hl), a
                ld   hl, CUR_REP               ; CUR_REP .. PAUSE_REQ
                ld   b, HERO_ST_USED - CUR_REP
.z:             ld   (hl), a
                inc  l
                djnz .z
                ld   (ARROWS), a
                ld   (HAS_BOW), a
                ld   (ICON_MODE), a            ; C3-2b
                ld   (END_SHOWN), a            ; C3-6
                ld   (PAUSED), a
                ld   (EXIT_LOCK), a
                ld   (DN_T), a
                ld   (DN_COMMIT), a
                ld   (ARANK), a
                ld   (ARANK + 1), a
                ld   (XP), a                   ; C3-3 shows LV / XP (reserved for 3D)
                ld   (XP + 1), a
                ; 3E-T8: the hero's kind_tab atk / eva / die / bonus columns, HERO_DEF,
                ; HERO_RES / IMM and the gear MP are hero_recalc's (R6; kit_add runs it
                ; right after this, with LVL 1: the level steps off)
                inc  a
                ld   (LVL), a                  ; level 1
                dec  a
                ld   a, (HERO_KIND)
                or   a
                ld   a, 0
                ld   b, MAGE_MP
                jr   nz, .d                    ; Mage: no daggers, DEF 0 (HERO3D zeroed)
                ld   b, WARRIOR_MP
                ld   a, WARRIOR_DAGGERS
.d:             ld   (DAGGERS), a
                ld   a, b                      ; D3-7 T3: base MP (game.md §4; 3E-T8: the
                ld   (MP), a                   ; Robe's +2 is gear: hero_recalc adds it,
                ld   (MAXMP), a                ; kit_add fills MP)
    IF DEBUG_KIT
                jr   debug_kit
    ELSE
                ret
    ENDIF
WARRIOR_MP      EQU 6
MAGE_MP         EQU 10                         ; 3E-T8: base (game.md §4: 10 + Robe 2 = 12)
WARRIOR_DAGGERS EQU 3                          ; (EQUs: no bytes in bank 7)

    IF DEBUG_KIT
;------------------------------------------------------------------------------
; debug_kit — the tail of hero_st_init (game.md §1.4 start kit, debug builds
; only; 3E: delete this block, the jump in hero_st_init and DEBUG_KIT; D3-7
; T5: moved from bank-3 rank3.asm for bank-3 room).
; Mage: 5 spells rank 1, MP 40/40. Warrior: bow, 20 arrows, 8 daggers, Power
; Strike + Whirlwind rank 1, MP 20/20. Then rank_sync.
; Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
debug_kit:
                ld   a, (HERO_KIND)
                or   a
                ld   hl, %0101                 ; Warrior: k0, k1 rank 1
                ld   b, 20
                jr   nz, .m
                ld   a, 1
                ld   (HAS_BOW), a
                ld   a, 20
                ld   (ARROWS), a
                ld   a, 8
                ld   (DAGGERS), a
                jr   .s
.m:             ld   hl, %0101010101           ; Mage: k0..4 rank 1
                ld   b, 40 - 2                 ; 3E-T8: + the Robe's MP 2 (hero_recalc) = 40
.s:             ld   (ARANK), hl
                ld   a, b
                ld   (MP), a
                ld   (MAXMP), a
                ld   hl, rank_sync             ; bank 3
                jp   far3
    ENDIF

; ic_quaff — ic_potion's drink (out of line: keeps the jr chains in range).
; 3E-T11: the first potion type, Heal -> Mana -> Cure (game.md §8.11 rulings
; 3), that is in the BAG (far6 bag_find) AND whose effect is not refused
; (pot_eff). None -> "NO NEED" (bank-1 stem), no turn, nothing consumed.
; Used: pot_take1 (R6: the stack - 1, E_POT synced), the heal flash,
; SFX_QUAFF, "YOU DRINK A POTION" (the "DRINK THE <name>" stem is the fx
; overlay's, T12). L = 1 turn used / IC_REFUSED.  ~3-8k T
ic_quaff:
                ld   c, IT_POT_LO
.t:             ld   a, c
                push bc
                ld   hl, bag_find              ; R6: C out = 0 if absent
                call far6
                ld   a, c
                pop  bc
                or   a
                jr   z, .nx
                ld   a, c
                call pot_eff                   ; CF = refused (nothing done)
                jr   nc, .take
.nx:            inc  c
                ld   a, c
                cp   IT_POT_HI + 1
                jr   c, .t
                xor  a                         ; IT_NONE: the stem alone
                ld   e, S3_NO_NEED
                ld   hl, it_line               ; bank 1
                call far1
                ld   l, IC_REFUSED             ; a line, no turn
                ret
.take:          ld   a, c
                ld   hl, pot_take1             ; R6
                call far6
                ld   (ix+E_FLT), FLASH_TICKS
                ld   (ix+E_FLA), ATTR_HEAL
                ld   a, SFX_QUAFF              ; SND-5b
                call sfx_req
                ld   a, TX_QUAFF
                call msg_push                  ; queued (panel_tick)
                ld   l, 1
                ret

; pot_eff — A = potion type: its effect (game.md §8), CF = 1 refused, nothing
; done: Heal HP + QUAFF_HEAL / Mana MP + POT_MANA (capped; refused when full);
; Cure clears POISON / WEAK / MIND (timers 0, HOLD kept) + POT_CURE_HP
; (capped; refused with none of the three).  Clobbers: A, DE, HL
pot_eff:
                cp   IT_P_MANA
                ld   hl, MP                    ; (MAXMP = MP + 1)
                ld   e, POT_MANA
                jr   z, cap_add
                ld   hl, P_ENTITIES + E_HP     ; (E_MAXHP = E_HP + 1)
                ld   e, QUAFF_HEAL
                jr   c, cap_add                ; Heal
                ld   hl, ST_FLAGS              ; Cure: the hero = status slot 0
                ld   a, (hl)
                and  STS_MIND | STS_POISON | STS_WEAK
                scf
                ret  z                         ; nothing to cure
                xor  (hl)                      ; = flags & ~mask
                ld   (hl), a
                ld   l, ST_T1 & $FF
                ld   a, (hl)
                and  $F0                       ; MIND timer 0, HOLD kept
                ld   (hl), a
                ld   l, ST_T2 & $FF
                ld   (hl), 0                   ; POISON / WEAK timers
                ld   e, POT_CURE_HP
                ld   hl, P_ENTITIES + E_HP
                call cap_add                   ; (full HP: the cure alone)
                or   a
                ret
POT_MANA        EQU 8                          ; game.md §8: Mana +8 MP
POT_CURE_HP     EQU 4                          ; game.md §8: Cure +4 HP
                ASSERT MAXMP == MP + 1 && E_MAXHP == E_HP + 1 && IT_P_CURE == IT_P_MANA + 1 && IT_P_HEAL + 1 == IT_P_MANA
                ASSERT (ST_FLAGS >> 8) == (ST_T1 >> 8) && (ST_T1 >> 8) == (ST_T2 >> 8)

; cap_add — HL = a value, (HL + 1) its max, E = amount: value = min(value +
; E, max); CF = 1 (nothing done) if it was already >= max.  Clobbers: A, D
cap_add:
                inc  hl
                ld   d, (hl)
                dec  hl
                ld   a, (hl)
                cp   d
                ccf
                ret  c
                add  a, e
                cp   d
                jr   c, .s
                ld   a, d
.s:             ld   (hl), a
                or   a
                ret
