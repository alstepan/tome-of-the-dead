;==============================================================================
; hero_defs.asm — Stage 3C contracts (C3-0; plan "3C breakdown" D4 / D7).
; Addresses only (EQU: no image bytes). docs/memory-map.md "3C contracts" is
; the authoritative table; change both together.
;==============================================================================

;------------------------------------------------------------------------------
; HERO_ST — hero / input state block in the bank-2 runtime spare after the
; animated-decor lists, up to the ISR ($BC90..$BCBB, 44 B; runtime RAM, not on
; tape: the owner task initialises it). Test-observable.
;------------------------------------------------------------------------------
HERO_ST         EQU $BC90
SEL_SLOT        EQU HERO_ST + 0     ; selected icon slot 0..ICON_SLOTS-1
FIRE_ST         EQU HERO_ST + 1     ; fire-button state machine
FIRE_T          EQU HERO_ST + 2     ; fire hold timer (ticks)
STICK           EQU HERO_ST + 3     ; the 5 inputs this tick, JOY_* bits (Kempston order)
STICK_OLD       EQU HERO_ST + 4     ; STICK of the previous tick (edges)
JOY_MODE        EQU HERO_ST + 5     ; input source: keys (KEYTAB) / Kempston
KEYTAB          EQU HERO_ST + 6     ; 10 B: 5 x {KEYTAB_ROW + KBROW_*, bit mask}, entry i = JOY bit i
KEYTAB_N        EQU 5
KEYTAB_STRIDE   EQU 2
ICON_SH         EQU HERO_ST + 16    ; 10 B: panel icon state last drawn, one per slot
DAGGERS         EQU HERO_ST + 26    ; Warrior throwing daggers
ARROWS          EQU HERO_ST + 27
HAS_BOW         EQU HERO_ST + 28    ; 0 / 1
; 3E-T11 (HERO_ST + 29..31, the old QPIN bytes): floor_pickup's arrival state
PU_POS          EQU HERO_ST + 29    ; word: the hero's x, FL_ROOM byte at the last pickup
                                    ; check (byte 1 $FF = none: panel_init7, per level)
PU_ARR          EQU HERO_ST + 31    ; the previous x (PU_NONE $80: other room / storey):
                                    ; BAG FULL only for a col outside its body span
; reserved for 3D (allocated now so the block does not move):
LVL             EQU HERO_ST + 32    ; hero level
XP              EQU HERO_ST + 33    ; word
ARANK           EQU HERO_ST + 35    ; word: bits 0-9 ranks (2 bits x 5), bits 10-11 BOOK_DRY (RANK1)
BOOK_DRY_MASK   EQU $0C             ; in ARANK + 1: 0 / 4 / 8 = BOOK_DRY 0 / 1 / 2 (game.md §5 pity)
PITY_N          EQU 2               ; reads skipped while an unlock was eligible, before the forced learn
MP              EQU HERO_ST + 37
MAXMP           EQU HERO_ST + 38
; C3-2 turn-intent machine (intent_tick / try_player_turn, io.asm / logic.asm):
CUR_REP         EQU HERO_ST + 39    ; cursor auto-repeat countdown (ticks) while FIRE held
TURN_HOLD       EQU HERO_ST + 40    ; ticks a held direction still waits after a turn-around
INTENT          EQU HERO_ST + 41    ; pending icon use (IN_FIRE) for the next INPUT tick
SC_OLD          EQU HERO_ST + 42    ; PLAYER_SC of the previous tick (shortcut edges)
PAUSE_REQ       EQU HERO_ST + 43    ; pause requests (FIRE+UP / BREAK); C3-6 consumes
HERO_ST_USED    EQU HERO_ST + 44    ; full
HERO_ST_END     EQU $BCBC
                ASSERT HERO_ST >= ANIM_LIST + ANIM_MAX * AL_STRIDE
                ASSERT HERO_ST_END == ISR_ADDR && HERO_ST_USED <= HERO_ST_END
                ASSERT KEYTAB + KEYTAB_N * KEYTAB_STRIDE == ICON_SH
                ASSERT ICON_SH + ICON_SLOTS == DAGGERS
                ASSERT HAS_BOW + 4 == LVL && PU_ARR + 1 == LVL   ; the old QPIN bytes = PU_*
                ASSERT (HERO_ST >> 8) == ((HERO_ST_END - 1) >> 8)   ; one page: inc l walks it

;------------------------------------------------------------------------------
; The 5 inputs (STICK, KEYTAB entry order, JOY_MIRROR): the Kempston bit
; layout, active-high (1 = pressed), so the joystick byte needs no remap.
;------------------------------------------------------------------------------
KEMPSTON_PORT   EQU $1F             ; IN A,($1F): bits 0..4 = R L D U F
JOY_R_BIT       EQU 0
JOY_L_BIT       EQU 1
JOY_D_BIT       EQU 2
JOY_U_BIT       EQU 3
JOY_F_BIT       EQU 4
JOY_MASK        EQU %00011111
JOY_DIRS        EQU %00001111           ; the 4 directions (PLAYER_DIR = STICK & JOY_DIRS)
                ASSERT JOY_R_BIT == DIR_E_BIT && JOY_L_BIT == DIR_W_BIT
                ASSERT JOY_D_BIT == DIR_S_BIT && JOY_U_BIT == DIR_N_BIT

; JOY_MODE values (C3-1; the menu order KEYS | KEMPSTON | SINCLAIR 1 | 2).
; KEYTAB is read in every mode (game.md §3.1: keys stay live, ORed).
; FIRE_ST values (C3-2)
FS_UP           EQU 0               ; FIRE released
FS_TAP          EQU 1               ; held, nothing done yet: release < FIRE_TAP_MAX = use icon
FS_USED         EQU 2               ; held and used (cursor / bag / pause) or held too long
FIRE_TAP_MAX    EQU 10              ; ticks: a longer hold is not a tap
CUR_DELAY1      EQU 10              ; cursor: first auto-repeat after 10 ticks ...
CUR_DELAY2      EQU 4               ; ... then every 4 (game.md §3.1)
TURN_DELAY      EQU 10              ; held ←/→ walks this many ticks after a turn-around
IN_FIRE         EQU 1               ; INTENT: use the selected icon
IN_BAG          EQU 2               ; INTENT: 3E-T2 the bag page (I; tpt_intent -> page_run, no turn)

; Slot actions (C3-2/C3-3; icons.asm slot_act_tab, one byte per class x slot)
SA_EMPTY        EQU 0               ; no icon (the Warrior's slot 6, the gap): never selected
SA_MELEE        EQU 1               ; sword / staff
SA_DAGGERS      EQU 2
SA_BOW          EQU 3
SA_FOOD         EQU 4               ; quick food (3E)
SA_POTION       EQU 5               ; quick potion
SA_SCROLL       EQU 6               ; quick scroll (3E)
SA_BAG          EQU 7
SA_ABIL         EQU 8               ; + ability index k (ARANK bits 2k..2k+1)
SA_COUNT        EQU SA_ABIL + 1     ; SA_* count (intent7.asm use_icon dispatch)
; Icon states (C3-3; icon_state, ICON_SH = state | IS_SEL as last drawn)
IS_HIDDEN       EQU 0               ; empty outline (empty slot, unlearned ability)
IS_GREY         EQU 1               ; greyed: no ammo / no item / not found
IS_NORMAL       EQU 2
IS_SEL          EQU $80             ; the selected slot (PAPER blue)
IS_MODE         EQU $40             ; + ICON MODE: the selected slot inverse (ink <-> paper)
IS_NONE         EQU $FF             ; ICON_SH: never drawn -> full redraw
IS_PICK_SH      EQU 2               ; IC1: quick POTION pick (0..2) in bits 2-3 of IS_NORMAL

JM_KEYS         EQU 0               ; KEYTAB only (boot zeroes JOY_MODE)
JM_KEMPSTON     EQU 1               ; + IN ($1F) (JOY_MIRROR while INPUT_SRC != 0).
                                    ; Accepted caveat (user-selected only): on a
                                    ; 128K / +2 without an interface the port
                                    ; floats; a byte with bits 5-7 = 0 (e.g. a
                                    ; plain attr) passes the guard as input
JM_SINC1        EQU 2               ; + keys 6-0 (shortcuts 6-0 off)
JM_SINC2        EQU 3               ; + keys 1-5 (shortcuts 1-5 off)


; KEYTAB entry (C3-1 review): {row byte, mask}. Row byte = KEYTAB_ROW +
; KBROW_* = the low byte of the half-row's KBD_MATRIX address (stick_tab:
; ld d, KBD_MATRIX >> 8 / ld e, row / ld a,(de)); mask = one key bit 0..4.
; C3-6 (redefine) must only store a row byte in KEYTAB_ROW..+7 and a
; non-zero mask (a mask-0 entry would read as always pressed; any other row
; byte reads unrelated state).
KEYTAB_ROW      EQU KBD_MATRIX & $FF
                ASSERT (KBD_MATRIX >> 8) == ((KBD_MATRIX + KBD_MATRIX_LEN - 1) >> 8)

; Default KEYTAB (Q/A/O/P/SPACE). A macro, so the 10 B land wherever the
; owner task instantiates it (boot copies lowram.asm's keytab_defaults).
    MACRO KEYTAB_DEFAULTS
                DB KEYTAB_ROW + KBROW_POIUY, 1 << KB_P_BIT  ; R = P
                DB KEYTAB_ROW + KBROW_POIUY, 1 << KB_O_BIT  ; L = O
                DB KEYTAB_ROW + KBROW_ASDFG, 1 << KB_A_BIT  ; D = A
                DB KEYTAB_ROW + KBROW_QWERT, 1 << KB_Q_BIT  ; U = Q
                DB KEYTAB_ROW + KBROW_SPACE, 1 << KB_SPACE_BIT ; F = SPACE
    ENDM

;------------------------------------------------------------------------------
; JOY_MIRROR — test injection for the joystick, in the 3B state sub-range:
; while INPUT_SRC != 0 the Kempston read takes this byte (JOY_* bits) instead
; of IN ($1F), like KBD_MATRIX stands in for the keyboard.
;------------------------------------------------------------------------------
JOY_MIRROR      EQU $BFEA
                ASSERT JOY_MIRROR >= PANEL_HP_SH + 2 && JOY_MIRROR < STATE_3B_END
