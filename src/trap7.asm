;==============================================================================
; trap7.asm — 3E-T16 the traps runtime, bank-7 cold code (MEM-RECLAIM w2b: from
; R6 trap6.asm; bank7.asm rules: R6 code only through far6). tele_arm /
; tele_flash / trap_at stay in R6 trap6.asm (R6 fx6 / pickup6 call them).
; game.md §1.5 (model, trigger, finding, effects), §2.3 (Wait searches),
; §2.2 (Mage sense), §8.11 (3) text rulings (the lines), §6.4 (POISON /
; ASLEEP), §6 V3 (flashes). The generator (items_ovl.asm, T6) fills
; TRAP_LIST; the known plate is drawn by build_room_map (bank 3: T_TRAP in the
; map, its type attr into TILE_ATTRS[T_TRAP]), mid-room by tr_plate / tr_show
; (the attr) + ap_put_a (bank 7, a plain call now).
;
; Two halves (review 2026-10-26: a trap event on the input tick overran the
; 126k cap, pmix + DART 141k T):
;  trap_turn  the DECISION, on the turn's input tick (bank-7 trap_chk): which
;             event (fire / find), the TRAP_LIST bits, the search roll — cheap;
;             it arms the trap sequence: TURN_PEND = TP_ACT | TP_MON, ACT_ABL =
;             ABL_TRAP, ACT_AT = 1, MON_AT = ACT_AT + 1: turn_input skips the
;             monster phase (MON_AT != 0), act_pend (bank 7) calls trap_step at
;             ACT_AT on a TP_FIRE tick (no panel item / decor step there) and
;             runs the monsters after the last step, as for a cast;
;  trap_step  the WORK, one step per armed tick (the effect, lines, the plate /
;             hero flashes), re-arming ACT_AT = TURN_TICK + TRAP_STEP_T.
; Immediate mode (no sequence: the effect is a find only): the room-entry
; sense (end_turn, after do_exit: the transition tick) and a turn whose
; TURN_PEND is already in use (an ability turn) — the plate is drawn in its
; ink at once, no blink.
;==============================================================================

HERO_W          EQU TRAP_HERO_W
TRAP_FX_DY      EQU 4               ; the DART impact row: hero top + 4 (the lower body)

;------------------------------------------------------------------------------
; trap_turn — jp from trap_chk (bank 7). In: A = TRP_WAIT (bit 0 a Wait, bit 1 the
; room-entry sense: immediate mode), DE = the room's unspent TRAP_LIST entry.
; Nothing for a DYING hero or a trap on the other storey. Then, with t = the
; trap col and x = the hero's body-left col:
;  1. trigger: t in x .. x+2 now and NOT before the action (TRP_PRE: same
;     storey and t in its x .. x+2) — standing, turning or waiting on it never
;     re-fires; walking off and on does; a jump that clears it (t in the
;     swept cols) never has it under the body. The bits now (DART known, a
;     one-shot spent), the work in the sequence (TEV_FIRE + type);
;  2. else a hidden trap is found (known now; TEV_FIND) by the Mage's sense
;     (t in x-2 .. x+4, 100 %) or, on a Wait, by the search (t in x-6 .. x+8,
;     1 in 2: rng_mod 2 = 0, gameplay RNG; the sense is tested first, so a
;     sensed trap draws no roll).
; Clobbers: all but IY (IX kept).
;   no event ~0.3k T; an event ~0.5k (arming); immediate find ~8k
;------------------------------------------------------------------------------
trap_turn:
                ex   de, hl                    ; HL = the entry (TR_B0)
                ld   e, a                      ; E = the TRP_WAIT bits
                ld   a, (P_ENTITIES + E_FLAGS)
                and  EF_DYING
                ret  nz
                ld   a, (P_ENTITIES + E_Y)
                call tr_sto
                xor  (hl)
                and  TRF_S1
                ret  nz                        ; the other storey: nothing to do
                call tr_col
                ld   c, a                      ; C = t
                ld   a, (P_ENTITIES + E_X)
                ld   b, a                      ; B = x
                ld   a, c
                sub  b                         ; t - x (mod 256)
                bit  TRW_ENTRY_BIT, e
                jr   nz, .nu                   ; the room-entry sense: no trigger
                cp   HERO_W
                jr   nc, .nu                   ; not under the body
                ld   a, (TRP_PRE + 1)          ; before the action: same storey ...
                call tr_sto
                xor  (hl)
                and  TRF_S1
                jr   nz, .fire
                ld   a, (TRP_PRE)
                ld   b, a
                ld   a, c
                sub  b
                cp   HERO_W                    ; ... and under that body: no re-fire
                ret  c
.fire:          call tr_type
                ld   b, a
                or   a
                jr   nz, .one
                set  TRF_KNOWN_BIT, (hl)       ; DART: known, re-arms
                jr   .arm
.one:           set  TRF_SPENT_BIT, (hl)       ; GAS / TELEPORT / ALARM: one-shot
.arm:           ld   a, b
                add  a, TEV_FIRE
                jr   tr_arm
.nu:            bit  TRF_KNOWN_BIT, (hl)
                ret  nz                        ; known: nothing to find
                ld   d, a                      ; D = t - x
                ld   a, (HERO_KIND)
                cp   K_WIZARD
                jr   nz, .ns
                ld   a, d                      ; sense: t - x in -2 .. 4
                add  a, TRAP_SENSE_R
                cp   2 * TRAP_SENSE_R + HERO_W
                jr   c, .find
.ns:            bit  TRW_WAIT_BIT, e
                ret  z                         ; not a Wait
                ld   a, d                      ; search: t - x in -6 .. 8
                add  a, TRAP_SEARCH_R
                cp   2 * TRAP_SEARCH_R + HERO_W
                ret  nc
                push hl
                ld   c, 2
                call rng_mod                   ; (A, B, HL)
                pop  hl
                or   a
                ret  nz                        ; 1 in 2
.find:          set  TRF_KNOWN_BIT, (hl)
                bit  TRW_ENTRY_BIT, e
                jr   nz, .imm
                ld   a, (TURN_PEND)
                or   a
                ld   a, TEV_FIND
                jr   z, tr_arm
.imm:           call tr_show                   ; immediate: drawn in its ink, the line
                jp   tr_fline
                ASSERT TRAP_SEARCH_R + HERO_W + TRAP_SEARCH_R < 128

; tr_arm — A = TEV_*, HL = the entry: the sequence from tick TRAP_ACT_TICK.
tr_arm:         ld   (TRP_EV), a
                ld   a, l
                ld   (TRP_ENT), a
                xor  a
                ld   (TRP_STEP), a
                ld   a, ABL_TRAP
                ld   (ACT_ABL), a
                ld   a, TP_ACT | TP_MON
                ld   (TURN_PEND), a
                ld   a, TRAP_ACT_TICK
tr_at:          ld   (ACT_AT), a               ; the next step, the monsters one tick after
                inc  a
                ld   (MON_AT), a
                ret
; tr_rearm — the next step B ticks on.
tr_rearm:       ld   hl, TURN_PEND
                set  TP_ACT_BIT, (hl)
                ld   a, (TURN_TICK)
                add  a, b
                jr   tr_at
                ASSERT ACT_ABL == TURN_PEND + 1 && ACT_AT == TURN_PEND + 2 && MON_AT == TURN_PEND + 3

;------------------------------------------------------------------------------
; trap_step — jp from act_pend (bank 7) at ACT_AT when ACT_ABL = ABL_TRAP
; (TP_ACT already cleared, TP_FIRE set: this tick skips the panel item and the
; decor step). TRP_STEP counts the steps. Every flash is an E_FLT hero flash
; or the plate's attr (TILE_ATTRS[T_TRAP] + ap_put_a): no new graphics.
;  TEV_FIRE + type (game.md §1.5 table, §6 V3):
;   step 0  SFX_TRAP; the hero flashes the type ink (DART $42, GAS $44 one step,
;           TELEPORT $43, ALARM $46, STUN $07; TRAP_FLASH_T ticks); the plate shows bright
;           (PLATE_FLASH_ATTR); the effect —
;           DART: "A DART HITS YOU!", far3 trap_hit (1d4+1 PHYS, DEF, POISON 12,
;             its lines); the hurt plays on arrival (E_REACTAT = walk 2, jump
;             JA_N + 1) with the arrow_hit impact on the trap col (Warrior only:
;             arrow_hit is not in the Mage's class FX pool, game.md §1.5);
;           STUN (STUN1): "A STONE FALLS ON YOU!", far3 trap_stone (1d3 PHYS, DEF,
;             STUNNED 2 + rnd(2) through deal_hit: HOLD_GUARD refuses the stun,
;             "YOU ARE STUNNED!"); the DART's hurt timing, no impact sprite;
;           GAS: hero_hold ASLEEP TRAP_GAS_T (HOLD overwritten: a moving hero
;             holds nothing), "SLEEPING GAS!" + "YOU FALL ASLEEP";
;           TELEPORT: tele_arm (EX_TELE, the $43 flash, SFX_DRAIN); act_pend's
;             monster step sees EXIT_KIND and skips the monsters; end_turn's
;             do_exit -> tele_pick ("YOU ARE TELEPORTED!", the arrival flash);
;           ALARM: 3E stub "A BELL RINGS. NOTHING COMES" (3F: the wave while
;             the boss lives + the red border, "AN ALARM BELL RINGS!");
;   step 1  (TRAP_STEP_T ticks on; TELEPORT: TELE_STEP_T) the plate: DART in its ink, a one-shot
;           erased (ap_put_a: T_AIR; decor returns on the next entry).
;  TEV_FIND: step 0 "TRAP FOUND: <type>"; the plate blinks bright / off
;           (TILE_ATTRS 0 = ink on black paper: unseen) FIND_BLINKS times,
;           TRAP_STEP_T ticks each, then shows in its ink.
; Clobbers: all but IY (IX kept).   DART step 0 ~16k T, STUN ~13k, GAS ~9k, ALARM ~7k,
;   TELEPORT ~4.5k, a plate step ~4k, the find's line step ~8k
;------------------------------------------------------------------------------
trap_step:
                ld   hl, TRP_STEP
                ld   c, (hl)                   ; C = this step
                inc  (hl)
                call tr_ent                    ; HL = the entry
                ld   a, (TRP_EV)
                sub  TEV_FIND
                jr   z, .fd
                ; --- fire ---
                dec  c
                jr   z, tr_final               ; step 1
                call tr_eff                    ; step 0
                call tr_ent
                ld   a, PLATE_FLASH_ATTR
                call tr_plate
                ld   a, (TRP_EV)
                cp   TEV_FIRE + TT_TELEPORT
                ld   b, TRAP_STEP_T
                jr   nz, tr_rearm
                ld   b, TELE_STEP_T            ; a teleport: hold for the hero's flash
                jr   tr_rearm
.pl:            call tr_plate
                ld   b, TRAP_STEP_T
                jr   tr_rearm
                ; --- find ---
.fd:            ld   a, c
                or   a
                jr   nz, .b
                push bc
                call tr_fline                  ; step 0: the line
                pop  bc
                call tr_ent
.b:             ld   a, c
                cp   2 * FIND_BLINKS
                jr   z, tr_final               ; done: its ink
                rrca
                ld   a, PLATE_FLASH_ATTR       ; even steps bright,
                jr   nc, .pl
                xor  a                         ; odd steps off
                jr   .pl

; tr_final — HL = the entry: DART / a found trap in its ink; a one-shot erased.
tr_final:       bit  TRF_SPENT_BIT, (hl)
                jr   z, tr_show
                ; fall through
; tr_erase / tr_show / tr_plate — HL = an entry in CUR_ROOM: its plate
; erased (T_AIR — no floor item footprint covers a trap col, drop_put / the
; generator) / drawn in its type attr / drawn with TILE_ATTRS[T_TRAP] := A;
; redrawn next render + the attr shadow (ap_put_a, bank 7: the one cell).
; Keep HL.  Clobbers: A, BC, DE.   ~4k T
tr_erase:       ld   b, T_AIR
                jr   tr_draw
tr_show:        call tr_ink                    ; A = its type attr
tr_plate:       ld   (TILE_ATTRS + T_TRAP), a  ; (<= 1 trap a room: item_defs.asm)
                ld   b, T_TRAP
tr_draw:        push hl
                ld   a, (hl)
                ld   e, a
                and  TRF_ROOM_MASK
                bit  TRF_S1_BIT, e
                jr   z, .s
                or   FL_S1
.s:             ld   e, a                      ; E = the FL_ROOM-style byte
                call tr_col                    ; A = col
                ld   d, b                      ; D = the tile
                call ap_put_a                  ; (A, DE in; keeps IX)
                pop  hl
                ret
                ASSERT TRF_ROOM_MASK == FL_ROOM_MASK

; tr_eff — the trigger's step 0 (HL = the entry; see trap_step).
tr_eff:
                ld   a, SFX_TRAP
                call sfx_req                   ; (keeps all)
                call tr_ink
                ld   de, P_ENTITIES + E_FLT    ; the hero flashes the type ink
                ex   de, hl
                ld   (hl), TRAP_FLASH_T
                inc  l
                ld   (hl), a
                ex   de, hl
                call tr_type
                dec  a
                jr   z, .gas
                dec  a
                jr   nz, .nt
                ld   hl, tele_arm              ; R6 trap6.asm (shared with fx6's Teleport scroll)
                jp   far6
.nt:            dec  a
                jr   nz, .dart                 ; DART (A = -3) / STUN (A = 1)
                ld   e, S_FX_TRAP_BELL         ; ALARM: TODO 3F the wave (§1.5, §9.5)
                ld   hl, fx_line               ; R6 gear6.asm (A = 0: the stem alone; E kept by farb)
                jp   far6
.gas:           ld   a, HOLD_ASLEEP
                ld   b, TRAP_GAS_T
                call hero_hold
                ld   e, S3_TRAP_GAS
                xor  a                         ; the stem alone
                ld   hl, it_line
                call far1
                ld   a, TX_ST_ASLEEP           ; "YOU FALL ASLEEP" (bank 0)
                jp   msg_push
.dart:          dec  a                         ; Z = STUN
                ld   hl, trap_hit              ; bank 3 (combat3.asm)
                ld   e, S3_TRAP_DART
                jr   nz, .st
                ld   hl, trap_stone            ; STUN1: 1d3 + STUNNED 2-3 through deal_hit
                ld   e, S3_TRAP_STONE
.st:            push hl
                xor  a                         ; the stem alone
                ld   hl, it_line
                call far1
                pop  hl
                call far3
                ld   a, (P_ENTITIES + E_MODE)
                cp   M_JUMP
                ld   a, TRAP_ACT_TICK + 1      ; a walk: arrives on tick 2
                jr   nz, .d
                ld   a, (JUMP_ARC)
                and  JA_N                      ; a jump: on landing (arc tick n + 1)
                inc  a
.d:             ld   (P_ENTITIES + E_REACTAT), a
                sub  TRAP_ACT_TICK + 1         ; fx_start from act_pend at tick k: the
                ld   c, a                      ; impact on k + delay + 1 -> delay =
                ld   a, (TRP_EV)               ; arrival - TRAP_ACT_TICK - 1
                cp   TEV_FIRE + TT_STUN
                ret  z                         ; STUN: no impact sprite (arrow_hit is DART-only)
                ld   a, (HERO_KIND)
                or   a
                ret  nz                        ; the Mage: no arrow_hit frame
                call tr_ent
                call tr_col
                ld   b, a                      ; B = the trap col
                ld   hl, tr_fx                 ; the descriptor -> MSG_BUF (free again:
                ld   de, MSG_BUF               ; the lines are queued; tr_fx: bank-7 data7.asm)
                push bc
                ld   bc, FXD_LEN
                ldir
                pop  bc
                ld   a, c
                ld   (MSG_BUF + FXD_DELAY), a
                ld   a, b
                ld   (MSG_BUF + FXD_COL), a
                ld   a, (P_ENTITIES + E_Y)
                add  a, TRAP_FX_DY
                ld   (MSG_BUF + FXD_ROW), a
                push ix
                ld   hl, MSG_BUF               ; (copied by fx_start)
                call fx_start                  ; bank 2 (all but IY)
                pop  ix
                ret
                ASSERT TT_DART == 0 && TT_GAS == 1 && TT_TELEPORT == 2 && TT_ALARM == 3 && TT_STUN == 4
                ASSERT E_FLA == E_FLT + 1 && ((P_ENTITIES + E_FLT) & $FF) != $FF

;------------------------------------------------------------------------------
; hero_hold — the hero falls under a HOLD with a timer, the GAS one-step flash:
; HOLD kind := A (HOLD_*), HOLD timer := B turns (<= STS_MAX_TURNS, the MIND
; timer kept), E_FLT := TRAP_FLASH_T ticks of TRAP_INK_GAS. Shared by the GAS
; trap (tr_eff) and the hunger faint (hunger7.asm hg_faint); a STUN goes
; through deal_hit (HOLD_GUARD, the line). Callers pick the lines / SFX.
; In: A = HOLD_*, B = turns.  Clobbers: A, B, C, HL.   ~0.25k T
;------------------------------------------------------------------------------
hero_hold:
                ld   hl, ST_FLAGS              ; the hero = status slot 0
                ld   c, a
                ld   a, (hl)
                and  ~STS_HOLD & $FF
                or   c
                ld   (hl), a
                ld   l, ST_T1 & $FF
                ld   a, b
                rlca
                rlca
                rlca
                rlca                           ; HOLD timer: the high nibble
                ld   b, a
                ld   a, (hl)
                and  $0F                       ; (the MIND timer kept)
                or   b
                ld   (hl), a
                ld   hl, P_ENTITIES + E_FLT
                ld   (hl), TRAP_FLASH_T
                inc  l
                ld   (hl), TRAP_INK_GAS
                ret
                ASSERT (ST_FLAGS >> 8) == (ST_T1 >> 8) && TRAP_GAS_T <= STS_MAX_TURNS && FAINT_T <= STS_MAX_TURNS
                ASSERT E_FLA == E_FLT + 1 && ((P_ENTITIES + E_FLT) & $FF) != $FF


; tr_fline — HL = the entry: "TRAP FOUND: <type>" (bank 1).  Clobbers: all but IX
tr_fline:       call tr_type
                ld   hl, tf_line
                jp   far1
; tr_ent — HL = the sequence's entry (TRP_ENT).  Clobbers: A
tr_ent:         ld   a, (TRP_ENT)
                ld   l, a
                ld   h, TRAP_LIST >> 8
                ret
; tr_ink — HL = an entry: A = its type attr (tr_ink7, data7.asm).  Keeps HL. Clobbers: F
tr_ink:         call tr_type
                push hl
                add  a, tr_ink7 & $FF
                ld   l, a
                adc  a, tr_ink7 >> 8
                sub  l
                ld   h, a
                ld   a, (hl)
                pop  hl
                ret
; tr_sto — A = a body-top row: A = TRF_S1 on storey 1, else 0.  Clobbers: F
tr_sto:         cp   STOREY_ROWS
                ld   a, 0
                ret  c
                ld   a, TRF_S1
                ret
; tr_col — HL = an entry: A = its col.  tr_type — A = its TT_*.  Keep HL.
tr_col:         inc  l
                ld   a, (hl)
                dec  l
                and  TR_COL_MASK
                ret
tr_type:        inc  l
                ld   a, (hl)
                dec  l
                rlca
                rlca
                rlca
                and  7                         ; bits 5-7 -> 0-4 (STUN1: 3 bits)
                ret
                ASSERT TR_TYPE_SHIFT == 5 && TR_TYPE_MASK == $E0 && TR_B1 == 1 && (TRAP_LIST >> 8) == ((TRAP_LIST + 11) >> 8)
