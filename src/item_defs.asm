;==============================================================================
; item_defs.asm — Stage 3E item contracts (3E-T3). EQUs + MACROs + ASSERTs
; only: this file emits NO bytes. INCLUDEd by defs.asm right after
; level_defs.asm. Every fixed address is recorded in docs/memory-map.md
; "3E contracts (3E-T3)"; tests/items3e.py mirrors the ASSERTs from the .sym.
; Design refs: game.md §1.5 (traps), §7 (hunger), §8 (items, bag, worn slots,
; quick slots), §8.5 (placement), §8.7 (wear), §8.9 (record), §8.11 (3E simplification: no ID / BUC);
; plan.md "3E breakdown" + user rulings 2026-10-19/20 (no gold, scaled 8x8
; floor glyphs as icons, no other-class books, light ID kept).
;==============================================================================

;------------------------------------------------------------------------------
; Item TYPE ids, ORDERED BY CLASS: every class (and every gear slot) is one
; contiguous range, so a class test is IT_IN lo, hi (below). The 3B/3D ids
; 1..3 keep their values (FLOOR_LIST data, levelgen.py / levelgen.asm, the
; FLOOR1: on the floor every type is its 16x16 icon over the T_ITEM0 markers).
;
;   0          IT_NONE      empty bag / worn slot, no pin
;   1          IT_POTION    LEGACY 3B stand-in: a floor potion that pickup adds
;                           to E_POT (heals QUAFF_HEAL). Retired by T11 (floor
;                           potions become IT_P_*); then id 1 is reserved.
;   2..4       counters     never in the bag (game.md §8): DAGGERS / ARROWS
;                           (hero_defs.asm) and the level key (LF_KEY_TAKEN)
;   5..18      bag-only     food, potions, scrolls (light ID), book, bow
;   19..43     gear         W / A / H / C slot ranges, in WORN slot order
;------------------------------------------------------------------------------
IT_NONE         EQU 0
; FLOOR1 (game.md §8.11 Q1 rev 2026-10-26): a floor item covers cols c..c+1 of
; rows 9s+6..9s+7 (FL_COL = c); c in ITEM_COL_LO..ITEM_COL_LAST (c+1 <= 29:
; never the door cols 0-1 / 30-31). Generator (items_ovl.asm) and drop_put.
ITEM_COL_LO     EQU 2
ITEM_COL_LAST   EQU 28
ITEM_ROOM_CAP   EQU 6               ; FLOOR1: generated entries per room (both storeys), max (4: ~13 % of the levels lose an item)
IT_POTION       EQU 1               ; legacy (see above); E_POT migration: memory-map "3E contracts"
; counters (floor-only types: pickup adds to a counter, never a bag slot)
IT_DAGGER       EQU 2               ; D3-7: FL_QTY = count, cap DAGGERS_MAX (FLOOR1 icon 43)
IT_ARROW        EQU 3               ; D3-7: FL_QTY = count, cap ARROWS_MAX (FLOOR1 icon 44)
IT_KEY          EQU 4               ; level key: pickup sets LF_KEY_TAKEN (game.md §8)
; food, ascending FOOD value (game.md §7 table), so the quick slot's
; "smallest FOOD first" (§8) = the lowest food type present
IT_F_CARROT     EQU 5               ; +10
IT_F_APPLE      EQU 6               ; +15
IT_F_PEAR       EQU 7               ; +20
IT_F_CHEESE     EQU 8               ; +30
IT_F_MEAT       EQU 9               ; +40
; potions (§8; quick-slot priority Heal > Mana > Cure = id order)
IT_P_HEAL       EQU 10
IT_P_MANA       EQU 11
IT_P_CURE       EQU 12
; scrolls (§8; quick-slot tie order Teleport > Fear > Sleep > Enchant = id order)
IT_S_TELEPORT   EQU 13
IT_S_FEAR       EQU 14
IT_S_SLEEP      EQU 15
IT_S_ENCHANT    EQU 16
; books / tools
IT_BOOK         EQU 17              ; the hero's class book (SPELLBOOK / WAR MANUAL by HERO_KIND,
                                    ; game.md §5; other-class books dropped 2026-10-20). A tome is
                                    ; a READ outcome (§5 rule 3), not an item type
IT_BOW          EQU 18              ; Warrior bag item (replaces HAS_BOW at T11)
; gear, slot W (weapon; class-locked: Warrior ids, then Mage ids; uniques last)
IT_W_SHORT      EQU 19              ; Short Sword 1d6 (Warrior start)
IT_W_LONG       EQU 20              ; Long Sword 1d8 atk+1 (D2+)
IT_W_AXE        EQU 21              ; War Axe 1d10 atk-1 (D4+)
IT_W_CLEAVER    EQU 22              ; Warlord's Cleaver (D4 boss unique)
IT_W_OAK        EQU 23              ; Oak Staff 1d4 (Mage start)
IT_W_IRON       EQU 24              ; Iron Staff 1d6 (D2+)
IT_W_RUNE       EQU 25              ; Rune Staff 1d4, spells +1 (D4+)
IT_W_BONE       EQU 26              ; Bone Staff (D4 boss unique)
; slot A (armour)
IT_A_ROBE       EQU 27              ; MP+2 (Mage start)
IT_A_LEATHER    EQU 28              ; DEF 1 (Warrior start)
IT_A_CHAIN      EQU 29              ; DEF 2 (D3+)
IT_A_PLATE      EQU 30              ; DEF 3 (D6+)
IT_A_SILK       EQU 31              ; Silk Cloak (D2 unique)
IT_A_GRAVE      EQU 32              ; Gravecloak (D3 unique)
; slot H (helmet)
IT_H_HOOD       EQU 33              ; MP+1
IT_H_HELM       EQU 34              ; DEF+1
IT_H_KING       EQU 35              ; Goblin King's Helm (D1 unique)
IT_H_MIRROR     EQU 36              ; Mirror Helm (D7 unique)
; slot C (charm: ring or amulet)
IT_C_MIGHT      EQU 37              ; Ring of Might
IT_C_WARD       EQU 38              ; Ring of Warding
IT_C_FIRE       EQU 39              ; Ring of Fire Ward
IT_C_MANA       EQU 40              ; Amulet of Mana
IT_C_PLENTY     EQU 41              ; Amulet of Plenty
IT_C_SCARAB     EQU 42              ; Scarab Amulet (D5 unique)
IT_C_GRAVE      EQU 43              ; Ring of the Grave (D6 unique)
IT_COUNT        EQU 44              ; type tables (T4) have IT_COUNT entries

; class ranges (inclusive)
IT_CNT_LO       EQU IT_DAGGER       ; counters
IT_CNT_HI       EQU IT_KEY
IT_AMMO_LO      EQU IT_DAGGER
IT_AMMO_HI      EQU IT_ARROW
IT_BAG_LO       EQU IT_F_CARROT     ; types that occupy a bag slot: IT_BAG_LO..IT_COUNT-1
IT_FOOD_LO      EQU IT_F_CARROT
IT_FOOD_HI      EQU IT_F_MEAT
IT_POT_LO       EQU IT_P_HEAL
IT_POT_HI       EQU IT_P_CURE
IT_SCR_LO       EQU IT_S_TELEPORT
IT_SCR_HI       EQU IT_S_ENCHANT
IT_GEAR_LO      EQU IT_W_SHORT
IT_GEAR_HI      EQU IT_C_GRAVE
IT_WPN_LO       EQU IT_W_SHORT
IT_WPN_HI       EQU IT_W_BONE
IT_WPN_W_LO     EQU IT_W_SHORT      ; Warrior weapons
IT_WPN_W_HI     EQU IT_W_CLEAVER
IT_WPN_M_LO     EQU IT_W_OAK        ; Mage weapons
IT_WPN_M_HI     EQU IT_W_BONE
IT_ARM_LO       EQU IT_A_ROBE
IT_ARM_HI       EQU IT_A_GRAVE
IT_HELM_LO      EQU IT_H_HOOD
IT_HELM_HI      EQU IT_H_MIRROR
IT_CHARM_LO     EQU IT_C_MIGHT
IT_CHARM_HI     EQU IT_C_GRAVE

                ASSERT IT_NONE == 0 && IT_POTION == 1 && IT_DAGGER == 2 && IT_ARROW == 3
                ASSERT IT_ARROW == IT_DAGGER + 1 && IT_KEY == IT_ARROW + 1
                ASSERT IT_FOOD_LO == IT_CNT_HI + 1 && IT_POT_LO == IT_FOOD_HI + 1
                ASSERT IT_SCR_LO == IT_POT_HI + 1 && IT_BOOK == IT_SCR_HI + 1 && IT_BOW == IT_BOOK + 1
                ASSERT IT_GEAR_LO == IT_BOW + 1 && IT_WPN_LO == IT_GEAR_LO
                ASSERT IT_WPN_M_LO == IT_WPN_W_HI + 1 && IT_WPN_HI == IT_WPN_M_HI
                ASSERT IT_ARM_LO == IT_WPN_HI + 1 && IT_HELM_LO == IT_ARM_HI + 1
                ASSERT IT_CHARM_LO == IT_HELM_HI + 1 && IT_GEAR_HI == IT_CHARM_HI
                ASSERT IT_COUNT == IT_GEAR_HI + 1 && IT_COUNT <= 64
                ASSERT IT_FOOD_HI - IT_FOOD_LO + 1 == 5 && IT_POT_HI - IT_POT_LO + 1 == 3
                ASSERT IT_SCR_HI - IT_SCR_LO + 1 == 4

;------------------------------------------------------------------------------
; IT_IN lo, hi — class / range test. In: A = type. Out: CF = 1 iff
; lo <= type <= hi, and A = type - lo (the index inside the class: the gear
; variant, the food rank). Clobbers F.
; 4 B, 14 T (sub n + cp n; the unsigned wrap makes one compare do both ends).
;------------------------------------------------------------------------------
    MACRO IT_IN lo, hi
                sub  lo
                cp   (hi) - (lo) + 1
    ENDM

;------------------------------------------------------------------------------
; Item record (game.md §8.9): TYPE / QTY / ISTATE, 3 B. Bag and worn slots
; store it as is (IR_*); FLOOR_LIST keeps its 4-B entry (FL_ITEM = TYPE,
; FL_QTY = QTY); a floor item has no ISTATE: pickup writes (FL_QTY - 1) & 7 = q
; (GEAR2: generated numeric gear carries FL_QTY = 1 + (q & 7), everything else 1).
; Stacks merge only on equal TYPE and ISTATE; QTY 1..STACK_MAX (ammo / key
; counts live outside the bag). TYPE = IT_NONE marks a free slot (QTY and
; ISTATE then 0).
;------------------------------------------------------------------------------
IR_TYPE         EQU 0
IR_QTY          EQU 1
IR_IST          EQU 2
IR_STRIDE       EQU 3
STACK_MAX       EQU 9               ; game.md §8 "same-type stacks to 9"

; ISTATE bits (§8.9, 3E simplification: no BUC / HIDDEN; gear only, 0 elsewhere):
;   bits 0-2 q, the per-instance offset set at generation (GEAR2, gear_rules.md 2.2):
;            signed 3-bit two's complement, -1..+2 used, never changes; 0 elsewhere.
;            Extract (gear_dec ist_v): v = m + q, the total offset on the main stat
;   bits 3-4 weapon enchant +0..ENCH_MAX (Enchant scroll)
;   bits 5-7 m, signed 3-bit two's complement -4..+3 (used -3..+2): the
;            wear modifier on the main stat (§8.7). Extract:
;            5 x `sra a` (sign-extends, 40 T) or the IST_M_* compares below
IST_Q_MASK      EQU %00000111
IST_ENCH_MASK   EQU %00011000
IST_ENCH_SHIFT  EQU 3
IST_ENCH_ONE    EQU 1 << IST_ENCH_SHIFT
ENCH_MAX        EQU 3
IST_M_MASK      EQU %11100000
IST_M_SHIFT     EQU 5
IST_M_ONE       EQU 1 << IST_M_SHIFT ; add IST_M_ONE = m + 1 (caller clamps)
IST_M_P2        EQU (2 & 7) << IST_M_SHIFT   ; m = +2  $40
IST_M_P1        EQU (1 & 7) << IST_M_SHIFT   ; m = +1  $20
IST_M_M1        EQU (-1 & 7) << IST_M_SHIFT  ; m = -1  $E0
IST_M_M2        EQU (-2 & 7) << IST_M_SHIFT  ; m = -2  $C0
IST_M_M3        EQU (-3 & 7) << IST_M_SHIFT  ; m = -3  $A0 (3F wear floor)
                ASSERT (IST_Q_MASK & IST_ENCH_MASK) == 0 && ((IST_Q_MASK | IST_ENCH_MASK) & IST_M_MASK) == 0
                ASSERT (IST_Q_MASK | IST_ENCH_MASK | IST_M_MASK) == $FF
                ASSERT (ENCH_MAX << IST_ENCH_SHIFT) == IST_ENCH_MASK
                ASSERT IST_M_P1 == $20 && IST_M_P2 == $40 && IST_M_M1 == $E0 && IST_M_M2 == $C0

;------------------------------------------------------------------------------
; Worn slots (game.md §8 "Worn slots: 4"), WORN + slot * IR_STRIDE, in the
; gear type order (slot k <-> the k-th gear range). Empty = TYPE IT_NONE
; (weapon: fists 1d2, §8.7 shattering).
;------------------------------------------------------------------------------
WS_WEAPON       EQU 0
WS_ARMOUR       EQU 1
WS_HELM         EQU 2
WS_CHARM        EQU 3
WORN_SLOTS      EQU 4
BAG_SLOTS       EQU 20              ; game.md §8: 5 x 4 page grid

;------------------------------------------------------------------------------
; Page verbs (3E-T13, game.md §8.11 Q3): the bag page RECORDS a verb in
; PAGE_VERB and its slot in PAGE_SLOT (0..BAG_SLOTS-1 bag, BAG_SLOTS + WS_* worn:
; the record is BAG + IR_STRIDE * slot), closes, and the effect runs after the
; copy-back. page_post applies VB_DISCARD itself (bag_discard, 0 turns); the
; others are the T8 / T12 effect overlay's (tpt_intent, 1 turn). VB_DRINK..
; VB_READ are also the page's USE-word index (page_ovl.asm pg_uw).
;------------------------------------------------------------------------------
VB_NONE         EQU 0               ; closed without a verb ([CLOSE], CLOSE, BREAK, I)
VB_DRINK        EQU 1               ; potion
VB_EAT          EQU 2               ; food
VB_READ         EQU 3               ; scroll, book
VB_EQUIP        EQU 4               ; gear in the bag
VB_REMOVE       EQU 5               ; worn gear (refused on the page with a full bag)
VB_DISCARD      EQU 6               ; any bag item: the whole stack (never worn)
PG_SLOT_WORN    EQU BAG_SLOTS       ; PAGE_SLOT of worn slot 0 (+ WS_*)
;------------------------------------------------------------------------------
;------------------------------------------------------------------------------
; Effect ops (3E-T8 / T12: fx_main, R6 src/fx6.asm, far6): FX_OP = op, FX_ARG
; = its argument. The page verbs ARE their ops (page_post stores PAGE_VERB /
; PAGE_SLOT as FX_OP / FX_ARG). Out: L = FXR_* (also written back to FX_OP).
; DRINK / EAT / READ all run fx_use, which acts by the item's class.
;------------------------------------------------------------------------------
FX_DRINK        EQU VB_DRINK        ; arg = bag slot 0..19 (fx_use)
FX_EAT          EQU VB_EAT          ; arg = bag slot (fx_use)
FX_READ         EQU VB_READ         ; arg = bag slot (fx_use; Teleport: EXIT_KIND = EX_TELE)
FX_EQUIP        EQU VB_EQUIP        ; arg = bag slot 0..19: worn <- it, the old worn item -> that slot
FX_REMOVE       EQU VB_REMOVE       ; arg = PG_SLOT_WORN + WS_*: -> the bag (refused when full)
FXR_TURN_BIT    EQU 0               ; the op spent the hero's turn
FXR_TURN        EQU 1 << FXR_TURN_BIT
FXR_REFUSED     EQU $80             ; refused with a line (NO NEED / NO FOOD ...): no turn
                                    ; (= IC_REFUSED, intent7.asm; bit 0 clear)
; quick slots (§8 "Quick slots auto-fill"): QPIN / QS_CACHE index
QS_FOOD         EQU 0
QS_POTION       EQU 1
QS_SCROLL       EQU 2
QS_COUNT        EQU 3
QS_SLOT0        EQU 6               ; IC1 / UB5: icon-bar slot of FOOD, the SAME for both heroes (the Warrior's
                                    ; slot 5 is the blank gap); + QS_* for POTION / SCROLL: slot_act_tab, ASSERTed in icons.asm

;------------------------------------------------------------------------------
; Hunger (game.md §7). FOOD 0..FOOD_MAX, start FOOD_START; -1 per
; FOOD_PERIOD turns (FOOD_TMR counts them), a jump -FOOD_JUMP extra; never
; fatal. HSTAGE = the stage derived from FOOD (HS_FED = 0, so a zeroed block
; reads FED). Written by T9 (src/hunger6.asm, R6); new_game zeroes all three,
; kit_add then sets FOOD_START.
;------------------------------------------------------------------------------
FOOD_MAX        EQU 100
FOOD_START      EQU 80
FOOD_PERIOD     EQU 6
FOOD_JUMP       EQU 2
HS_FED          EQU 0               ; FOOD >= HS_OK_BELOW
HS_OK           EQU 1
HS_HUNGRY       EQU 2
HS_WEAK         EQU 3
HS_OK_BELOW     EQU 50              ; FOOD < 50 -> OK
HS_HUNGRY_BELOW EQU 25              ; FOOD < 25 -> HUNGRY
HS_WEAK_BELOW   EQU 10              ; FOOD < 10 -> WEAK
HP_REG_FED      EQU 12              ; FED: HP +1 per 12 turns (§7)
HW_REPEAT       EQU 50              ; WEAK: the faint check every 50 turns (§7.1; was the repeat line)
FAINT_T         EQU 5               ; FAINT1 (§7.1): the hunger faint = ASLEEP 5 (BAL1 knob 4..6)
FAINT_GAP       EQU 30              ; faints come 30 turns apart (HW_TMR := HW_REPEAT - FAINT_GAP; BAL1 25..40)
; Hunger-WEAK = ST_FLAGS slot 0 bit STS_HWEAK_BIT (combat_defs.asm), kept equal to
; HSTAGE == HS_WEAK by hunger_turn: every WEAK test masks STS_WEAK | STS_HWEAK
; (same effects, never stacked; no timer, no icon, Cure leaves it).

;------------------------------------------------------------------------------
; ITEM_RAM — the 3E runtime item block. Bank 5 $5D00.., the BASIC area freed
; once boot has moved SP to $BF00 (garbage at power-on; not on tape; never
; touched before new_game). One page: every field is reached with `inc l`.
; new_game (bank 7, boot7.asm) zeroes ALL of it; level changes keep it.
; 3E simplification (game.md §8.11, 2026-10-20): no FL_IST (a floor item is
; TYPE / QTY only, m 0), no ID_MAP / KNOWN (names fixed), no FL_ATTR (the
; floor ink is f(type): it_tab, lowram.asm) -> 81 B (was 121 / 153).
;------------------------------------------------------------------------------
ITEM_RAM        EQU $5D00
BAG             EQU ITEM_RAM                    ; BAG_SLOTS x IR_STRIDE   (kept)
WORN            EQU BAG + BAG_SLOTS * IR_STRIDE ; WORN_SLOTS x IR_STRIDE  (kept)
FOOD            EQU WORN + WORN_SLOTS * IR_STRIDE   ; 0..FOOD_MAX                          (kept)
FOOD_TMR        EQU FOOD + 1                    ; turns since the last burn                (kept)
HSTAGE          EQU FOOD_TMR + 1                ; HS_*                                     (kept)
; 3E-T9: the 3 QPIN bytes (QUICK pin cut, game.md §8.11 Q3; never used) = hunger state
HP_RG           EQU HSTAGE + 1                  ; FED HP regen turn counter 0..HP_REG_FED-1     (kept)
HW_TMR          EQU HP_RG + 1                   ; turns since the last WEAK line 0..HW_REPEAT-1  (kept)
MP_HOLD         EQU HW_TMR + 1                  ; != 0: xp_turn skips MP regen this turn (hunger_turn
                                                ;   writes it every turn, just before xp_turn)
QS_CACHE        EQU MP_HOLD + 1                 ; QS_COUNT (pot_sync, IC1): food / scroll QTY in BAG (0 = the icon
                                                ;   greys), QS_POTION = the potion types present (bit k = IT_P_HEAL + k) (kept)
; M0 (post-3F, reserved for STATS1 S1; architect 2026-10-31): 5 per-game counters, zeroed by
; new_game with the rest of the block (0 B of code: ITEM_RAM_LEN is the clear's count). Unused
; until STATS1 S1 defines them (names / meaning: that task; memory-map "M0 / post-3F ledger").
ST1_CNT         EQU QS_CACHE + QS_COUNT         ; 5 B: STATS1 S1 counters                  (kept)
ST1_LEN         EQU 5
ST1_KILLS       EQU ST1_CNT                     ; word: the hero's kills (kill_note, combat3.asm; the end card)
ST1_BL          EQU ST1_CNT + 2                 ; best kind: its kx_tab entry's low byte (8 * kind + KX_XP)
ST1_BXP         EQU ST1_CNT + 3                 ; best kind's KXP (the compare)
ST1_KILLER      EQU ST1_CNT + 4                 ; ENDCARD-G1: $80 | the kind that killed the hero, 0 = no monster
                                                ; (deal_hit .kill; traps / poison / falls / the aura / his own hit: 0)
; ENDCARD-G1 end card layout (menu1.asm end_card, combat3.asm ec_tab): a clean full screen
EC_POS          EQU TMP6                        ; 2 B: ec_tab's label x (px), then its next row (TMP7)
EC_VX           EQU 64                          ; value x = label x + EC_VX (px)
EC_TAB_X        EQU 72                          ; the table's label x: 72 + 118 (EC_VX + 9 chars) = 190, centre 131
EC_TAB_ROW      EQU 7                           ; its first row (CLASS); the last row (BEST KILL) = 15 (user 2026-11-05: the whole card up 3 rows
                                                ; (was 10) so the ink, title top .. PRESS bottom, is centred: 25 px above / 33 below)
EC_FEET         EQU EC_TAB_ROW + 9              ; the portraits' / lectern's shared feet row (= the table's bottom;
                                                ; the first row below BEST KILL)
EC_PCOL_L       EQU 2                           ; killer col (the Ogre's ink ends ~10 px short of the table at x 72); lectern = +3
EC_PCOL_R       EQU 25                          ; the hero's col (his ink starts ~11 px after the table's widest row, x 190)
EC_PRESS_ROW    EQU EC_TAB_ROW + 12             ; "PRESS 1-5 OR ENTER" (was 22)
EC_TROW         EQU EC_TAB_ROW - 4                          ; the title row (menu font, 2 rows)
EC_ATTR         EQU $47                         ; the card (bright white on black)
EC_A_HERO       EQU $46                         ; CLASS / LEVEL / DEPTH rows (yellow)
EC_A_DEAD       EQU $42                         ; YOU DIED (red)
EC_A_WIN        EQU $46                         ; YOU WIN! (yellow)
EC_A_KBY        EQU $45                         ; KILLED BY (cyan)
EC_A_NAME       EQU $43                         ; the killer's name (magenta)
; STATS2 (game.md STATS1 / STATS2): 3 saturating per-game counters right after ST1_CNT (the free
; BASIC-area bytes $5D56..; zeroed by new_game with the block: ITEM_RAM_LEN is the clear's count)
ST2_CNT         EQU ST1_CNT + ST1_LEN           ; 3 B                                       (kept)
ST2_LEN         EQU 3
ST2_BKR         EQU ST2_CNT                     ; books read (fx_book, fx6.asm: every completed book READ)
ST2_BKF         EQU ST2_CNT + 1                 ; books found (pu_add, pickup6.asm: an IT_BOOK taken)
ST2_ITM         EQU ST2_CNT + 2                 ; items found (pu_add non-book + ap_take, pickup7.asm: n > 0)
ITEM_RAM_END    EQU ST2_CNT + ST2_LEN
ITEM_RAM_LEN    EQU ITEM_RAM_END - ITEM_RAM     ; 89 (M0: 81 + ST1_LEN; STATS2: + ST2_LEN)
                ASSERT ITEM_RAM_LEN == 89
                ASSERT (ITEM_RAM & $FF) == 0 && ITEM_RAM_LEN <= 256      ; one page (inc l, djnz clear)
                ASSERT ITEM_RAM >= $5CCB        ; above the system variables + channel area
                ASSERT ITEM_RAM_END <= PF_RAM   ; below D3-6b PF_RAM ($5E00) / MK_RAM ($5F00)
; The start kit's base lists (game.md §8.11 Q10 / §4; weapon, armour, then the bag): R6
; kit_add's kit_w / kit_m (release) and, DBG-1, bank-0 kit_bw / kit_bm (kit0.asm, + extras).
    MACRO KIT_W_BASE
                DB   IT_W_SHORT, IT_A_LEATHER, IT_P_HEAL, IT_F_APPLE
    ENDM
    MACRO KIT_M_BASE
                DB   IT_W_OAK, IT_A_ROBE, IT_P_HEAL, IT_P_MANA, IT_F_APPLE
    ENDM
                ASSERT WORN == BAG + BAG_SLOTS * IR_STRIDE      ; bag + worn = one 24-record scan

;------------------------------------------------------------------------------
; Trap list (game.md §1.5): per level, in the LVL_STATE ROOM_DESC spare
; ($6DF0..$6DFF), so level_gen's `attempt` (EDGE_TAB..LVL_STATE_END := 0) and
; proto_level clear it on every level for free; written by T6 after
; level_gen. TRAP_N entries used (0..TRAP_MAX); spent entries are skipped,
; never compacted mid-level.
;   byte TR_B0: bits 0-3 room id, bit 4 TRF_S1 (storey 1), bit 5 TRF_KNOWN,
;               bit 6 TRF_RUNG (ALARM-1, runtime only), bit 7 spare (0); TRAP2: no trap is ever spent
;   byte TR_B1: bits 0-4 col, bits 5-7 type TT_* (STUN1: 3 bits)
; NOTE: tools/levelgen.py's 320-B block model (tests/levelgen_z80.py,
; room_model.py) must keep these bytes 0 until T6 / T7 model the traps.
;------------------------------------------------------------------------------
TRAP_LIST       EQU ROOM_DESC + GRID_CELLS * RD_STRIDE   ; $6DF0
TRAP_MAX        EQU 6
TRAP_STRIDE     EQU 2
TRAP_N          EQU TRAP_LIST + TRAP_MAX * TRAP_STRIDE   ; $6DFC ($6DFD..$6DFF spare)
TR_B0           EQU 0
TR_B1           EQU 1
TRF_ROOM_MASK   EQU %00001111
TRF_S1          EQU %00010000
TRF_KNOWN       EQU %00100000
TRF_SPENT       EQU 0               ; TRAP2: retired (mask terms in trap6 / fx6 / bank3 / bank7 are no-ops)
TRF_S1_BIT      EQU 4
TRF_KNOWN_BIT   EQU 5
TRF_RUNG        EQU %01000000       ; ALARM-1: this ALARM plate has rung its one wave (readers mask it)
TRF_RUNG_BIT    EQU 6
TR_COL_MASK     EQU %00011111
TR_TYPE_MASK    EQU %11100000
TR_TYPE_SHIFT   EQU 5
TT_DART         EQU 0               ; D1+, re-arms
TT_GAS          EQU 1               ; D2+, one-shot
TT_TELEPORT     EQU 2               ; D3+, one-shot
TT_ALARM        EQU 3               ; D5+, one-shot
TT_STUN         EQU 4               ; D4+, one-shot (STUN1: the falling stone; pool order DART GAS TELEPORT STUN ALARM)
                ASSERT TRAP_N < FLOOR_LIST      ; inside the ROOM_DESC spare, below FLOOR_LIST
                ASSERT TRAP_LIST == $6DF0 && TRAP_N == $6DFC
; 3E-T16 traps runtime state (state block spare $BFF5..$BFF7, test-observable,
; never zeroed: both are written before they are read on every accepted turn)
TRP_PRE         EQU $BFF5           ; 2 B: the hero's E_X, E_Y before this turn's action
                                    ;   (turn_input .act, bank 7): the trigger's "first under"
TRP_WAIT        EQU $BFF7           ; TRW_* bits: a Wait (tpt_intent .srch) / the room-entry
                                    ;   sense (end_turn .ex); trap_chk passes and clears it
TRP_EV          EQU $BFF8           ; the armed trap sequence (trap6.asm): TEV_FIRE + TT_* / TEV_FIND
TRP_STEP        EQU $BFF9           ;   its step counter (trap_step)
TRP_ENT         EQU $BFFA           ;   its TRAP_LIST entry (low byte)
                ASSERT TRP_ENT < STATE_3B_END && TRP_PRE > SFX_XP
TRAP_UNDER      EQU $BFFF           ; TRAP-OR: the tile id the drawn plate composes over (the cell's
                                    ;   id before T_TRAP; bank-3 tr_cell3 writes it before any read)
                ASSERT TRAP_UNDER == STATE_3B_END - 1
TRW_WAIT_BIT    EQU 0
TRW_ENTRY_BIT   EQU 1
TRW_ENTRY       EQU 1 << TRW_ENTRY_BIT
TEV_FIRE        EQU 1               ; + TT_*: 1..5
TEV_FIND        EQU 6
ABL_TRAP        EQU $80             ; ACT_ABL of a trap sequence (act_pend -> far6 trap_step)
TRAP_ACT_TICK   EQU 1               ; the first step: the tick after the input tick
TRAP_STEP_T     EQU 2               ; ticks between steps (each flash phase)
BORDER_ALARM    EQU 2               ; 3F-T9: the ALARM wave's red border (game.md §1.5: 2 ticks = TRAP_STEP_T)
FIND_BLINKS     EQU 2               ; the found plate blinks bright / off twice, then its ink
PLATE_FLASH_ATTR EQU $47            ; the plate's bright flash (trigger) / blink (find)
TRAP_FLASH_T    EQU FLASH_TICKS     ; the hero's type-ink flash on a trigger (GAS: one step)
TELE_FLASH_ATTR EQU $43             ; teleport (scroll / trap): bright magenta, the TELEPORT ink;
                                    ;   not a hero kind attr ($47 / $45), the hit $42, gold $46
TELE_FLASH_T    EQU 5               ; ticks, before the room change and again on arrival (the
                                    ;   displayed screen trails E_FLT by ~2 ticks: 3 shown)
TELE_HOLD_T     EQU 5               ; the scroll's turn is held >= this (MON_AT)
TELE_STEP_T     EQU 4               ; the trap's: step 1 at tick 1 + 4, the monster step after
; trap rules (game.md §1.5)
TRAP_HERO_W     EQU 3               ; both heroes' KT_BW: the body cols x .. x+2
TRAP_SEARCH_R   EQU 6               ; Wait searches hidden traps within 6 cols of the body, 1 in 2
TRAP_SENSE_R    EQU 2               ; the Mage senses them within 2 cols (100 %)
TRAP_GAS_T      EQU 4               ; GAS: ASLEEP 4
TRAP_DART_PSN   EQU 12              ; DART: 1d4+1 PHYS + POISON 12 (POIS1: was 6; deal_hit's E param is /2, PSN_CAP)
TRAP_DART_DIE   EQU 4
TRAP_STONE_DIE  EQU 3               ; STUN1: the falling stone 1d3 PHYS (DEF applies) ...
TRAP_STUN_T     EQU 2               ; ... + STUNNED 2 + rnd(2) (gameplay RNG: the damage die, then the duration)
; the known plate's attr by type (§1.5: ink on black). <= 1 trap per room
; (generator), so the room's known trap sets TILE_ATTRS[T_TRAP] itself:
; build_room_map's stamp and trap7's reveal, both through bank-7 tr_ink (data7 tr_ink7; TRAP-OR),
; built from these. (A scroll between two rooms with known traps
; shows the old plate in the new room's ink AND with the new room's decor
; bits until it leaves: the NEXT_MAP build rewrites both TILE_ATTRS[T_TRAP] and
; TILE_GLYPHS[T_TRAP] via tr_cell3. tr_cell3's item-marker early return also
; leaves TILE_ATTRS changed with no T_TRAP placed; cosmetic, the next build or
; reveal rewrites it.)
TRAP_INK_DART   EQU $42
TRAP_INK_GAS    EQU $44             ; (also the GAS hero flash, §1.5: $44 one step)
TRAP_INK_TELE   EQU $43
TRAP_INK_ALARM  EQU $46
TRAP_INK_STUN   EQU $07             ; grey stone = the STUNNED tint (also the hero flash)
    MACRO TRAP_INKS
                DB   TRAP_INK_DART, TRAP_INK_GAS, TRAP_INK_TELE, TRAP_INK_ALARM, TRAP_INK_STUN
                ASSERT TT_DART == 0 && TT_GAS == 1 && TT_TELEPORT == 2 && TT_ALARM == 3 && TT_STUN == 4
    ENDM
