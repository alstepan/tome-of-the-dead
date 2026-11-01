;==============================================================================
; fx6.asm — 3E-T8 / T12 item effects, R6 region (r6.asm rules; far6 only from
; other banks). game.md §7 (food), §8 (potions / scrolls), §5 (books), §8.11
; Q3 (verbs), Q6 (teleport), rulings 3 (quick use), "3E simplification".
; Was the T8 fx overlay (fx_ovl.asm): ZX0 packed that code only 3 % (180 ->
; 174 B), so running it from GEN_SCRATCH cost a map save / unpack / restore
; (EQUIP 52.3k T, a no-op 38.0k: tests/equip.py at T8) for ~6 B of R6.
; Resident, an effect costs its own work (EQUIP 10.9k T).
;
;   fx_main     far6 from page_post (bank 1): FX_OP / FX_ARG = the page verb
;   fx_quick    far6 from use_slot (bank 7): the POTION / FOOD / SCROLL icons
;   tele_pick   far6 from do_exit (bank 7): the Teleport target + arrival spot
;   pot_eff     a potion's effect (was bank 7 intent7.asm)
; Results come back in L (far6 loses A / F): FXR_TURN (1) = the turn is spent,
; FXR_REFUSED ($80) = refused with a line, 0 = nothing (no line, no turn).
; Nothing here renders: lines are queued (fx_line / it_line / msg_push), the
; panel polls HP / MP / E_POT / FOOD (PD_* where it does not).
;==============================================================================

;------------------------------------------------------------------------------
; fx_main — FX_OP = op (FX_*, VB_NONE = nothing), FX_ARG = slot. Out: L =
; FXR_*, also stored in FX_OP.  Clobbers: A, BC, DE, HL (IX kept).
;------------------------------------------------------------------------------
fx_main:
                ld   hl, (FX_OP)               ; L = op, H = arg
                ld   a, l
                or   a
                ret  z                         ; VB_NONE: L = 0
                cp   FX_EQUIP
                ld   a, h
                jr   c, .use                   ; DRINK / EAT / READ: by the item's class
                jr   nz, .rm
                call fx_equip
                jr   .o
.rm:            call fx_remove
                jr   .o
.use:           call fx_use
.o:             ld   a, l
                ld   (FX_OP), a
                ret
                ASSERT FX_DRINK < FX_EQUIP && FX_EAT < FX_EQUIP && FX_READ < FX_EQUIP && FX_REMOVE == FX_EQUIP + 1
                ASSERT FX_ARG == FX_OP + 1 && VB_NONE == 0

; fx_take — A = SFX: the sound, one item of fx_slot consumed, the turn spent.
fx_take:        call sfx_req                   ; (keeps A / BC)
                ld   a, (fx_slot)
                ld   b, 1
                call bag_take                  ; (+ pot_sync: E_POT for the panel)
fx_turn:        ld   l, FXR_TURN
                ret
fx_none:        ld   l, 0
                ret
; fx_noneed — "NO NEED" (bank-1 resident stem), no turn. fx_refuse: E = the
; stem (fx_eat's "TOO SICK TO EAT" joins here).
fx_noneed:      ld   e, S3_NO_NEED
fx_refuse:      xor  a                         ; IT_NONE: the stem alone
                ld   hl, it_line
                call far1
                ld   l, FXR_REFUSED
                ret
                ASSERT E_FLA == E_FLT + 1 && ((P_ENTITIES + E_FLT) & $FF) != $FF
                ASSERT IT_POT_LO == IT_FOOD_HI + 1 && IT_SCR_LO == IT_POT_HI + 1 && IT_BOOK == IT_SCR_HI + 1

;------------------------------------------------------------------------------
; fx_equip — A = bag slot 0..19 holding gear: WORN[its slot] <- the item; the
; item worn before (if any) takes the freed bag slot (swap: the bag count is
; unchanged, so it never fails), else the slot is compacted away. Then
; "YOU EQUIP <name>", hero_recalc, 1 turn (game.md §8.11 "3E simplification":
; no refusal).  Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
fx_equip:
                cp   BAG_SLOTS
                jr   nc, fx_none
                ld   b, a                      ; B = slot
                add  a, a
                add  a, b
                ld   l, a
                ld   h, HIGH BAG               ; HL = the bag record
                ld   a, (hl)
                sub  IT_GEAR_LO
                cp   IT_GEAR_HI - IT_GEAR_LO + 1
                jr   nc, fx_none               ; not gear (the page offers EQUIP for gear only)
                add  a, IT_GEAR_LO
                ld   de, WORN + WS_CHARM * IR_STRIDE
                cp   IT_CHARM_LO
                jr   nc, .ws
                ld   e, (WORN + WS_HELM * IR_STRIDE) & $FF
                cp   IT_HELM_LO
                jr   nc, .ws
                ld   e, (WORN + WS_ARMOUR * IR_STRIDE) & $FF
                cp   IT_ARM_LO
                jr   nc, .ws
                ld   e, (WORN + WS_WEAPON * IR_STRIDE) & $FF
.ws:            push de                        ; the worn record
                push bc                        ; B = slot
                ld   b, IR_STRIDE
.sw:            ld   c, (hl)                   ; swap the two records
                ld   a, (de)
                ld   (hl), a
                ld   a, c
                ld   (de), a
                inc  l
                inc  e
                djnz .sw
                pop  bc
                dec  l
                dec  l
                dec  l
                ld   a, (hl)
                or   a
                jr   nz, .sx                   ; the old worn item took the slot
                ld   a, b
                ld   b, STACK_MAX
                call bag_take                  ; empty: compacted away (+ pot_sync)
.sx:            pop  hl
                ld   a, (hl)                   ; the item now worn
                ld   e, S_FX_EQUIP
                jr   fx_done
                ASSERT IT_WPN_LO == IT_GEAR_LO && IT_ARM_LO == IT_WPN_HI + 1 && IT_HELM_LO == IT_ARM_HI + 1
                ASSERT IT_CHARM_LO == IT_HELM_HI + 1 && (BAG & $FF) == 0 && HIGH WORN == HIGH BAG

;------------------------------------------------------------------------------
; fx_remove — A = PG_SLOT_WORN + WS_*: the worn item -> the bag (bag_add with
; its QTY / ISTATE); refused (bag full: the page refuses first) -> nothing, no
; turn. Then "YOU REMOVE <name>", hero_recalc, 1 turn.  Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
fx_remove:
                sub  PG_SLOT_WORN
                cp   WORN_SLOTS
                jr   nc, fx_none
                ld   c, a
                add  a, a
                add  a, c
                add  a, WORN & $FF
                ld   l, a
                ld   h, HIGH WORN              ; HL = the worn record
                ld   a, (hl)
                or   a
                jr   z, fx_none                ; empty slot
                push hl
                inc  l
                ld   b, (hl)                   ; QTY
                inc  l
                ld   c, (hl)                   ; ISTATE
                push af
                call bag_add                   ; L = 1 refused (A, DE, HL)
                pop  af
                pop  de
                dec  l
                jr   z, fx_none                ; bag full
                ex   de, hl
                ld   (hl), IT_NONE             ; the slot empties (fists for a weapon)
                inc  l
                ld   (hl), 0
                inc  l
                ld   (hl), 0
                ld   e, S_FX_REMOVE
                ; fall through
; fx_done — A = type, E = the S_FX_* stem: the line, hero_recalc, the panel's
; worn cell of that type's slot (IC1 worn_cell, ~3.5-5k T, marked for present), 1 turn.
fx_done:        push af
                call fx_line                   ; "<stem><name>", queued
                call hero_recalc
                pop  af
                call worn_cell
                jp   fx_turn



;------------------------------------------------------------------------------
; fx_quick — the icon-bar quick use (game.md §8.11 rulings 3), far6 from
; use_slot, A = the class's empty line: TX_NO_POTION / TX_NO_FOOD /
; TX_NO_SCROLL. FOOD = the lowest food type, SCROLL = the largest stack
; (bag_pick); POTION = Heal -> Mana -> Cure, the first present whose effect
; is not refused; all refused -> NO NEED. Empty class -> the NO line + SFX_NO.
; Out: L = FXR_TURN / FXR_REFUSED.  Clobbers: A, BC, DE, HL (IX kept).
;   ~7-12k T (bag_pick + the effect + a line)
;------------------------------------------------------------------------------
fx_quick:
                push af                        ; [the NO line]
                cp   TX_NO_POTION
                jr   z, .pot
                cp   TX_NO_FOOD
                ld   bc, (IT_FOOD_LO << 8) | 0
                ld   d, 2 * (IT_FOOD_HI - IT_FOOD_LO + 1) + 0   ; mode 0: the lowest type
                jr   z, .pk
                ld   b, IT_SCR_LO
                ld   d, 2 * (IT_SCR_HI - IT_SCR_LO + 1) + 1     ; mode 1: the largest stack
.pk:            call bag_pick                  ; A = type / IT_NONE
                or   a
                jr   z, .none
                call bag_find                  ; A = its slot
                pop  bc                        ; (drop the line)
                jr   fx_use
.pot:           ld   a, (P_ENTITIES + E_POT)   ; the bag's potions (pot_sync)
                or   a
                jr   z, .none
                pop  af
                ld   b, IT_POT_LO
.t:             ld   a, b
                call bag_find                  ; A = slot / $FF (B kept)
                inc  a
                jr   z, .nx
                dec  a
                ld   (fx_slot), a
                ld   a, b
                ld   (fx_type), a
                push bc
                call pot_eff                   ; CF = refused, nothing done
                pop  bc
                jr   nc, fx_drunk
.nx:            inc  b
                ld   a, b
                cp   IT_POT_HI + 1
                jr   c, .t
                jp   fx_noneed
.none:          ld   a, SFX_NO                 ; SND-5b: the shared NO effect
                call sfx_req
                pop  af
                call msg_push                  ; "NO FOOD" ... (restores bank 6)
                ld   l, FXR_REFUSED
                ret
                ASSERT IT_NONE == 0 && IT_POT_HI == IT_POT_LO + 2

;------------------------------------------------------------------------------
; fx_use — A = bag slot: DRINK a potion / EAT a food / READ a scroll or the
; book (the page verbs DRINK / EAT / READ, the quick slots). One turn; the item
; is consumed (one of the stack: bag_take compacts an emptied slot, pot_sync).
; Refused (nothing consumed, no turn, "NO NEED"): EAT at FOOD_MAX, a potion
; whose effect would do nothing (pot_eff). Anything else in the slot: L = 0.
;------------------------------------------------------------------------------
fx_use:
                cp   BAG_SLOTS
                jp   nc, fx_none
                ld   (fx_slot), a
                ld   c, a
                add  a, a
                add  a, c
                ld   l, a
                ld   h, HIGH BAG
                ld   a, (hl)
                ld   (fx_type), a
                ld   b, a                      ; B = type
                IT_IN IT_FOOD_LO, IT_BOOK      ; A = index in food .. book
                jp   nc, fx_none               ; gear / the bow / empty: no use verb
                cp   IT_POT_LO - IT_FOOD_LO
                jr   c, fx_eat
                cp   IT_SCR_LO - IT_FOOD_LO
                jr   nc, fx_read
                ; --- DRINK ---
                ld   a, b
                call pot_eff                   ; CF = refused
                jp   c, fx_noneed
fx_drunk:       ld   hl, P_ENTITIES + E_FLT    ; the heal flash (as the quick potion did)
                ld   (hl), FLASH_TICKS
                inc  l
                ld   (hl), ATTR_HEAL
                ld   a, (fx_type)
                ld   e, S_FX_DRINK             ; "YOU DRINK THE HEAL POTION"
                call fx_line
                ld   a, (fx_type)              ; + the effect line (game.md §8.11 (3))
                cp   IT_P_MANA
                ld   e, S_FX_MANA_SURGE        ; "MANA SURGES!"
                jr   z, .l2
                ld   e, S_FX_CURED             ; "YOU ARE CURED"
                jr   nc, .l2
                ld   a, TX_SPL_DRAIN_HEAL      ; Heal: "YOU FEEL HEALTHIER +G" (bank 0; LOG-DMG:
                call msg_push_h                ; G = LN_G, pot_eff's cap_add)
                jr   .l3
.l2:            xor  a
                call fx_line
.l3:            ld   a, SFX_QUAFF
                ; fall through
                jp   fx_take


;------------------------------------------------------------------------------
; fx_eat — B = a food type: poisoned -> TOO SICK TO EAT; FOOD 100 -> NO NEED; else "YOU EAT THE <name>",
; FOOD + its value (it_stat; hunger_add clamps at 100, a crossing into FED
; prints "YOU FEEL WELL FED" after it), SFX_EAT, one eaten.   ~6k T
;------------------------------------------------------------------------------
fx_eat:
                ld   a, (ST_FLAGS)             ; POIS1 (§7.2): poisoned, he cannot eat -
                bit  STS_POISON_BIT, a         ; before NO NEED; 0 turns, nothing consumed
                ld   e, S3_TOO_SICK
                jp   nz, fx_refuse
                ld   a, (FOOD)
                cp   FOOD_MAX
                jp   nc, fx_noneed
                ld   a, b
                ld   e, S_FX_EAT
                call fx_line
                ld   a, (fx_type)
                call it_amt                    ; A = its FOOD
                ld   hl, hunger_add            ; bank 7 hunger7.asm (MEM-RECLAIM w2b; A passes in)
                call far7
                ld   a, SFX_EAT
                jp   fx_take

;------------------------------------------------------------------------------
; fx_read — B = a scroll type or IT_BOOK: "YOU READ THE <name>", the item is
; consumed whatever it does (game.md §8), then:
;  Teleport  EXIT_KIND = EX_TELE: end_turn's do_exit moves the hero (the
;            monsters do not act on an exit turn; tele_pick prints the line)
;  Fear      the room's monsters FEAR SCR_FEAR_T turns (room_status, bank 3)
;  Sleep     ... ASLEEP SCR_SLEEP_T turns; "THEY FLEE IN TERROR!" / "THEY
;            FALL ASLEEP!", none affected -> "NOTHING HAPPENS"
;  Enchant   ench_any (gear6.asm): "ENCHANTED: <name>" / "NOTHING HAPPENS"
;  book      fx_book (game.md §5 reading rules)
;------------------------------------------------------------------------------
SCR_FEAR_T      EQU 6               ; game.md §8: Fear "flee 6 turns"
SCR_SLEEP_T     EQU 8               ; game.md §8: Sleep "ASLEEP 8 turns"
fx_read:
                ld   a, b
                ld   e, S_FX_READ
                call fx_line
                ld   a, (fx_slot)
                ld   b, 1
                call bag_take
                ld   a, (fx_type)
                cp   IT_BOOK
                jr   z, fx_book
                sub  IT_S_FEAR
                jr   c, .tp                    ; Teleport
                cp   IT_S_ENCHANT - IT_S_FEAR
                jr   z, .en
                ld   hl, room_status           ; bank 3: A = 0 Fear / 1 Sleep -> L = bodies
                call far3
                ld   a, (fx_type)
                ld   e, S_FX_FEAR_FLEE
                cp   IT_S_FEAR
                jr   z, .hit
                ld   e, S_FX_SLEEP_FALL
.hit:           inc  l
                dec  l
                jr   nz, .ln
.no:            ld   e, S_FX_NOTHING
.ln:            xor  a                         ; the stem alone
.fl:            call fx_line
                jp   fx_turn
.en:            call ench_any                  ; GEAR3: A = the enchanted item's type / 0 nothing
                or   a
                ld   e, S_FX_ENCHANTED         ; "ENCHANTED: <name>"
                jr   nz, .fl
                jr   .no
.tp:            call tele_arm                  ; 3E-T16: EX_TELE + the flash + the hold
                jp   fx_turn
                ASSERT IT_S_FEAR == IT_S_TELEPORT + 1 && IT_S_SLEEP == IT_S_FEAR + 1 && IT_S_ENCHANT == IT_S_SLEEP + 1

;------------------------------------------------------------------------------
; fx_book — the class book (game.md §5 "Reading" rev 6, first match wins):
;  1. starter: no ability known yet -> slot 0 (Spark / Power Strike), 0 RNG;
;  2. pity: BOOK_DRY == PITY_N and an eligible unlearned ability exists ->
;     the earliest-depth one (the first candidate), 0 RNG;
;  3. uniform pick over the candidates (<= 5, in slot = unlock-depth order):
;     every ability that is unlearned with unlock depth <= LVL_DEPTH (learn;
;     fx_cand byte = k | $80) or known below rank 3 (rank-up; byte = k). ONE
;     call: index = (rng_byte * n) >> 8 (rng_next, no rejection loop);
;  4. else the tome: Warrior Vigor HP +3 MP +1, Mage Power MP +3 HP +1 (max
;     and current raised, §4; not a heal: no flash) + its line, 0 RNG.
; BOOK_DRY (ARANK + 1 bits 2-3, ARANK bits 10-11): a learn resets it, a
; rank-up while an eligible unlearned ability existed adds 1, a tome leaves it
; (no eligible ability is left then: it is 0). Unlock depth: Warrior k0 D1, k1
; D3 (2k + 1); Mage k0..4 D1..D5 (k + 1, §4): "slots 0..L-1 are unlocked" with
; L = min(depth, 5) / min((depth + 1) div 2, 2).
; abil_learn is bank 7 (far7: ARANK += 1 << 2k, PD_ICONS | PD_INFO, the line).
;------------------------------------------------------------------------------
fx_book:
                ld   a, SFX_LEVELUP            ; UB2: every read learns / ranks up / tomes (keeps BC, HL)
                call sfx_req
                ld   hl, (ARANK)
                ld   a, h
                and  3                         ; (bits 10-15: BOOK_DRY, masked out)
                or   l
                jr   nz, .scan
                                               ; starter: Z = A = 0: slot 0, 0 RNG
.learn:         ld   hl, abil_learn            ; bank 7 (A = k)
                call far7
                ld   l, FXR_TURN
                ret
.scan:          ld   a, (HERO_KIND)
                or   a
                ld   a, (LVL_DEPTH)
                ld   c, 5
                jr   nz, .lim                  ; Mage: min(depth, 5)
                inc  a
                srl  a                         ; Warrior: (depth + 1) div 2, min 2
                ld   c, 2
.lim:           cp   c
                jr   c, .l0
                ld   a, c
.l0:            ld   c, a                      ; C = L: slot k is unlocked iff k < C
                ld   de, (ARANK)               ; shifted right 2 bits per k
                ld   b, 0                      ; k
                ld   hl, fx_cand
.s:             ld   a, e
                and  3
                jr   z, .un
                cp   RANK_MAX
                jr   z, .nx                    ; rank 3: no candidate
                ld   a, b                      ; known below rank 3: a rank-up
.ad:            ld   (hl), a
                inc  l
.nx:            srl  d
                rr   e
                srl  d
                rr   e
                inc  b
                ld   a, b
                cp   RANK_N
                jr   nz, .s
                ld   a, l                      ; n = candidates
                sub  fx_cand & $FF
                jr   z, .tome
                ld   c, a
                ld   b, a
                ld   d, $FF                    ; D = index of the first unlearned ($FF none)
.f:             dec  l                         ; walking down: the last write is the first
                bit  7, (hl)
                jr   z, .fn
                ld   a, b
                dec  a
                ld   d, a
.fn:            djnz .f
                ld   a, (ARANK + 1)
                and  BOOK_DRY_MASK
                cp   PITY_N << 2
                jr   nz, .rnd
                ld   a, d
                inc  a
                jr   z, .rnd                   ; (pity with nothing eligible: unreachable)
                ld   b, d
                jr   .got
.rnd:           call rng_next                  ; A = the byte (A, HL)
                ld   e, a
                ld   b, 0
                xor  a
.m:             add  a, e                      ; B = (byte * n) >> 8 (n <= 5: 8-bit adds)
                jr   nc, .mn
                inc  b
.mn:            dec  c
                jr   nz, .m
.got:           ld   hl, fx_cand
                ld   a, b
                add  a, l
                ld   l, a
                ld   c, (hl)                   ; C = k | $80 if unlearned
                ld   hl, ARANK + 1
                ld   a, (hl)
                ld   b, a
                and  ~BOOK_DRY_MASK & $FF
                ld   e, a                      ; E = BOOK_DRY 0
                bit  7, c
                jr   nz, .st                   ; a learn resets it
                inc  d
                jr   z, .st                    ; rank-up with nothing eligible: 0
                ld   a, b
                and  BOOK_DRY_MASK
                add  a, 1 << 2                 ; rank-up while one was eligible: +1
                or   e
                ld   e, a
.st:            ld   (hl), e
                ld   a, c
                and  $7F
                jp   .learn
.un:            ld   a, b                      ; unlearned: a candidate iff unlocked
                cp   c
                jr   nc, .nx
                or   $80
                jr   .ad
.tome:          ld   a, (HERO_KIND)
                or   a
                ld   de, (TOME_BIG << 8) | TOME_SMALL      ; Vigor: D = HP, E = MP
                ld   c, TX_BK_VIGOR
                jr   z, .tv
                ld   de, (TOME_SMALL << 8) | TOME_BIG      ; Power
                ld   c, TX_BK_POWER
.tv:            ld   hl, P_ENTITIES + E_HP     ; HP, MAXHP += D
                call .add2
                ld   d, e
                ld   hl, MP                    ; MP, MAXMP += E
                call .add2
                ld   hl, PANEL_DIRTY
                ld   a, (hl)
                or   PD_MP | PD_INFO
                ld   (hl), a
                ld   a, c
                call msg_push
.turn:          ld   l, FXR_TURN
                ret
.add2:          ld   a, (hl)
                add  a, d
                ld   (hl), a
                inc  l
                ld   a, (hl)
                add  a, d
                ld   (hl), a
                ret
TOME_BIG        EQU 3               ; game.md §4: Tome of Vigor +3 HP +1 MP, Power +3 MP +1 HP
TOME_SMALL      EQU 1
                ASSERT E_MAXHP == E_HP + 1 && MAXMP == MP + 1 && ((P_ENTITIES + E_HP) & $FF) != $FF && (MP & $FF) != $FF
                ASSERT (fx_cand >> 8) == ((fx_cand + RANK_N) >> 8) && ABL_SPARK == 0 && K_KNIGHT == 0 && RANK_N == 5
                ASSERT BOOK_DRY_MASK == $0C && PITY_N == 2

;------------------------------------------------------------------------------
; pot_eff — A = potion type: its effect (game.md §8), CF = 1 refused, nothing
; done: Heal HP + QUAFF_HEAL / Mana MP + POT_MANA (capped; refused when full);
; Cure clears POISON / WEAK / MIND (timers 0, HOLD kept) + POT_CURE_HP
; (capped; refused with none of the three). 3E-T12: moved from bank 7.
; Clobbers: A, DE, HL
;------------------------------------------------------------------------------
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
                xor  a
                ld   (hl), a                   ; WEAK timer
                ld   (ST_X), a                 ; POIS1: the POISON timer
                ld   e, POT_CURE_HP
                ld   hl, P_ENTITIES + E_HP
                call cap_add                   ; (full HP: the cure alone)
                or   a
                ret
POT_MANA        EQU 8                          ; game.md §8: Mana +8 MP
POT_CURE_HP     EQU 4                          ; game.md §8: Cure +4 HP
                ASSERT MAXMP == MP + 1 && E_MAXHP == E_HP + 1 && IT_P_CURE == IT_P_MANA + 1 && IT_P_HEAL + 1 == IT_P_MANA
                ASSERT (ST_FLAGS >> 8) == (ST_T1 >> 8) && (ST_T1 >> 8) == (ST_T2 >> 8)

; cap_add — HL = a value, (HL + 1) its max, E = amount (>= 1): value = min(value +
; E, max); CF = 1 (nothing done) if it was already >= max. LOG-DMG: LN_G = the gain
; G = min(E, max - value) (msg_push_h; MP too, harmless: only a heal line reads it);
; out A = G (was the new value: the callers read CF only).  Clobbers: A
cap_add:
                ld   a, (hl)
                inc  hl
                sub  (hl)                      ; value - max: NC = already full
                dec  hl
                ccf
                ret  c
                neg                            ; room = max - value (>= 1)
                cp   e
                jr   c, .g
                ld   a, e
.g:             ld   (LN_G), a
                add  a, (hl)                   ; <= max: CF = 0
                ld   (hl), a
                ret

;------------------------------------------------------------------------------
; it_amt — A = a food / potion type: A = its it_stat amount (FOOD / HP / MP).
; Clobbers: HL, F
;------------------------------------------------------------------------------
it_amt:         add  a, a
                add  a, (it_stat + 1) & $FF
                ld   l, a
                adc  a, (it_stat + 1) >> 8
                sub  l
                ld   h, a
                ld   a, (hl)
                ret

;------------------------------------------------------------------------------
; tele_pick — far6 from do_exit's EX_TELE branch, after hide_sprites, before
; lp_transition (game.md §8.11 Q6; the trap teleport of T16 reuses it):
;  - no followers: CAND_LIST all $FF, FOLLOW_N 0 (lp_transition banks every
;    monster of the old room exactly as on a normal exit);
;  - the room: uniform (gameplay RNG) among the present rooms != CUR_ROOM,
;    != LVL_SANCTUM, != LVL_LAIR while its boss lives (stand-in until 3F:
;    LF_UNIQUE = the boss's kill was seen); none (PROTO) -> CUR_ROOM;
;  - the spot: the room's LP_CMAP (far3 lp_cmap: ladders / shafts / exits +
;    their end boxes with the 1-col margin, the pit + caps + landing, the
;    blocks, the horizontal arrival boxes) + its unspent trap cols (tp_room):
;    TELE_TRIES x (storey rnd(2), col LP_XMIN + rnd(26) = 2..27) until the
;    hero's 3 body cols are clear, else the clear col nearest TELE_MID on
;    storey 1, then storey 0 (cols 2..27); a room with no legal spot (review:
;    41 of 27,468 generated rooms have storey 1 blocked, 2 both) is dropped
;    and another eligible room drawn; none left -> CUR_ROOM, then the hero's
;    own spot (never seen). Monster bodies: lp_enter places every resident against this
;    arrival box (the entry gap rule), arrival_conflicts makes an overlap
;    PENDING — the hero never lands on a body, pit or ladder box.
; Out: EXIT_DEST, EXIT_COL = the col, EXIT_KIND = EX_UP (storey 1) / EX_DOWN
; (storey 0): lp_transition's and do_exit's vertical arrival = the spot;
; "YOU ARE TELEPORTED!" queued.  Clobbers: all but IY (IX: lp_cmap).
;   ~11.5-13.5k T measured incl. lp_cmap (far3) and the ~6k line (tests/t12.py T3)
; Col range: x = 2..27 (LP_XMIN.., the body <= LP_XMAX = 29) instead of Q6's
; rnd(28) + 1: x = 1 is a door cell (cols 0-1) on an exit storey.
;------------------------------------------------------------------------------
TELE_TRIES      EQU 16              ; game.md §8.11 Q6
TELE_W          EQU 3               ; both heroes' KT_BW (kind_tab)
TELE_MID        EQU 14              ; Q6 fallback: the nearest legal col to 14 on storey 1
TELE_XN         EQU LP_XMAX - TELE_W + 1 - LP_XMIN + 1   ; 26 cols: 2..27
TELE_XHI        EQU LP_XMAX - TELE_W + 1                 ; 27
tele_pick:
                ld   hl, CAND_LIST
                ld   b, P_MAX_ENT
.cl:            ld   (hl), $FF
                inc  l
                djnz .cl
                xor  a
                ld   (FOLLOW_N), a
                ; --- the eligible rooms -> fx_cand (<= 8) ---
                ld   hl, ROOM_DESC + RD_FLAGS
                ld   de, fx_cand
                ld   bc, 0                     ; B = room, C = count
.r:             bit  RDF_PRESENT_BIT, (hl)
                jr   z, .rn
                ld   a, (CUR_ROOM)
                cp   b
                jr   z, .rn
                ld   a, (LVL_SANCTUM)
                cp   b
                jr   z, .rn
                ld   a, (LVL_LAIR)
                cp   b
                jr   nz, .ok
                ld   a, (LVL_FLAGS)
                and  LF_UNIQUE
                jr   z, .rn                    ; the lair while its boss lives
.ok:            ld   a, b
                ld   (de), a
                inc  e
                inc  c
.rn:            ld   a, l
                add  a, RD_STRIDE
                ld   l, a
                inc  b
                ld   a, b
                cp   GRID_CELLS
                jr   c, .r
                ld   hl, tp_n
                ld   (hl), c
.pick:          ld   a, (hl)                   ; HL = tp_n
                or   a
                jr   z, .cur                   ; no eligible room left
                ld   c, a
                call rng_mod                   ; A = 0..n-1 (A, B, HL)
                push af
                add  a, fx_cand & $FF
                ld   l, a
                ld   h, fx_cand >> 8
                ld   a, (hl)
                call tp_room                   ; Z = a spot (D, E)
                pop  bc                        ; B = its index
                jr   z, .got
                ld   hl, tp_n                  ; no spot in it: drop it (the last one
                dec  (hl)                      ; takes its place), pick again
                ld   a, (hl)
                add  a, fx_cand & $FF
                ld   e, a
                ld   d, fx_cand >> 8
                ld   a, b
                add  a, fx_cand & $FF
                ld   l, a
                ld   h, d
                ld   a, (de)
                ld   (hl), a
                ld   hl, tp_n
                jr   .pick
.cur:           ld   a, (CUR_ROOM)             ; none (PROTO, or every room full): here
                call tp_room
                jr   z, .got
                ld   hl, P_ENTITIES + E_X      ; not even here: where he stands
                ld   e, (hl)
                ld   d, 0
                ld   a, (P_ENTITIES + E_Y)
                cp   STOREY_ROWS
                jr   c, .got
                inc  d
.got:           ld   a, e
                ld   (EXIT_COL), a
                ld   a, d
                or   a
                ld   a, EX_DOWN                ; storey 0 (do_exit: FLOOR_ROW0)
                jr   z, .k
                ld   a, EX_UP                  ; storey 1 (FLOOR_ROW1)
.k:             ld   (EXIT_KIND), a
                call tele_flash                ; 3E-T16: the arrival flash
                xor  a
                ld   e, S_FX_TELEPORTED
                jp   fx_line
                ASSERT (CAND_LIST & $FF) + P_MAX_ENT <= 256 && (TRAP_LIST & $FF) + TRAP_MAX * TRAP_STRIDE <= 256
                ASSERT (ROOM_DESC >> 8) == ((ROOM_DESC + GRID_CELLS * RD_STRIDE - 1) >> 8) && RD_FLAGS == 0
                ASSERT LPC_BAD == 1 && TR_B0 == 0 && TR_B1 == 1 && TRAP_STRIDE == 2 && GRID_CELLS <= 9
                ASSERT TELE_XN == 26 && STOREY_ROWS == 9
                ASSERT (fx_cand >> 8) == ((fx_cand + GRID_CELLS - 2) >> 8)

;------------------------------------------------------------------------------
; tp_room — tele_pick's spot in room A: EXIT_DEST := A, far3 lp_cmap (test
; hook tp_room.cmap: the call), + its unspent trap cols, then TELE_TRIES x
; (storey rnd(2), col 2 + rnd(26)) with the 3 body cols clear, then a scan:
; storey 1, then storey 0, the clear col nearest TELE_MID over cols 2..27.
; Out: Z = found (D = storey, E = col); NZ = no legal spot in the room.
; Clobbers: all but IY (IX: lp_cmap).
;------------------------------------------------------------------------------
tp_room:
                ld   (EXIT_DEST), a
                ld   (LPV_ROOM), a
                ld   hl, lp_cmap               ; bank 3: the room's LP_CMAP (bank 5)
.cmap:          call far3                      ; (test hook: tests/t12.py F NOPs it)
                ; --- + its unspent trap cols (the body may not cover one) ---
                ld   a, (TRAP_N)
                or   a
                jr   z, .nt
                ld   b, a
                ld   a, (EXIT_DEST)
                ld   d, a
                ld   hl, TRAP_LIST
.tr:            ld   e, (hl)                   ; TR_B0
                inc  l
                ld   a, e
                xor  d
                and  TRF_ROOM_MASK | TRF_SPENT
                jr   nz, .tn                   ; another room, or spent
                ld   a, (hl)                   ; TR_B1
                and  TR_COL_MASK
                push hl
                ld   hl, LP_CMAP
                bit  TRF_S1_BIT, e
                jr   z, .t0
                ld   l, (LP_CMAP + LP_CMW) & $FF
.t0:            add  a, l
                ld   l, a
                set  0, (hl)                   ; LPC_BAD
                pop  hl
.tn:            inc  l
                djnz .tr
.nt:            ld   b, TELE_TRIES
.try:           push bc
                ld   c, 2
                call rng_mod
                ld   d, a                      ; D = storey
                ld   c, TELE_XN
                call rng_mod
                add  a, LP_XMIN
                ld   e, a                      ; E = col
                call tp_ok
                pop  bc
                ret  z
                djnz .try
                ld   d, 1                      ; the scan: storey 1, then 0
.sc:            ld   c, 0                      ; C = distance from TELE_MID
.fb:            ld   a, TELE_MID
                sub  c
                cp   LP_XMIN
                jr   c, .rt                    ; (left of col 2: the right side only)
                ld   e, a
                call tp_ok
                ret  z
.rt:            ld   a, TELE_MID
                add  a, c
                ld   e, a
                call tp_ok
                ret  z
                inc  c
                ld   a, c
                cp   TELE_XHI - TELE_MID + 1   ; 14 + 13 = 27
                jr   c, .fb
                ld   a, d
                sub  1
                ld   d, a
                jr   nc, .sc                   ; storey 0 next
                ret                            ; NZ ($FF): no legal spot
                ASSERT TELE_XHI == LP_XMIN + TELE_XN - 1 && TELE_MID - (TELE_XHI - TELE_MID) < LP_XMIN


; tp_ok — D = storey, E = col: Z = LP_CMAP clear under cols E .. E+2.
; Keeps BC, DE.  Clobbers: A, HL.   ~90 T
tp_ok:          ld   hl, LP_CMAP
                inc  d
                dec  d
                jr   z, .s
                ld   l, (LP_CMAP + LP_CMW) & $FF
.s:             ld   a, l
                add  a, e
                ld   l, a
                ld   a, (hl)
                inc  l
                or   (hl)
                inc  l
                or   (hl)
                ret
                ASSERT TELE_W == 3 && (LP_CMAP >> 8) == ((LP_CMAP + 2 * LP_CMW - 1) >> 8)

; variables (written in play; r6.asm rules)
fx_slot:        DB   0                         ; the bag slot being used
fx_type:        DB   0                         ; its type
tp_n:           DB   0                         ; tele_pick: eligible rooms left
fx_cand:        DS   GRID_CELLS - 1            ; fx_book: rank-up candidates (<= 5);
                                               ; tele_pick: the eligible rooms (<= 8)
