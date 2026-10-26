;==============================================================================
; fx_ovl.asm — 3E-T8 the silent in-play effects overlay (docs/memory-map.md
; "Overlays"; game.md §8.11 Q3 verbs). Assembled at FX_ORG (= GEN_SCRATCH),
; stored ZX0-packed in R6 (`ovl_fx_zx0`), run by ovl_fx / ovl_fx_saved
; (lowram.asm) with the room map saved to FX_MAP_SAVE and put back after it.
; Rules: it never renders, presents or reads ROOM_MAP / NEXT_MAP / LP_CMAP;
; log lines are only queued (fx_line -> log_push: the LOG_TXT ring, drawn
; later by panel_tick); it keeps IX; no state of its own survives it.
; It pages R6 (bank 6) at its entry and calls the R6 resident code directly
; (bag6 / gear6: their far1 / far3 calls hand bank 6 back); ovl_run re-pages
; the caller's bank afterwards.
; In : FX_OP = op (FX_*, item_defs.asm), FX_ARG = its argument.
; Out: FX_OP = FXR_* flags (FXR_TURN: the hero's turn is spent).
; Ops: FX_EQUIP, FX_REMOVE (T8); FX_DRINK / FX_EAT / FX_READ / FX_TELEPORT
; are reserved for T12 (no-ops: 0, no turn); FX_DISCARD is page_post's own.
;==============================================================================
fx_main:
                ld   a, BANK_R6
                call page_bank                 ; (A, BC) R6 resident code + data
                ld   a, (FX_OP)
                dec  a
                cp   FX_COUNT - 1
                ld   l, 0
                jr   nc, .out                  ; not an op: nothing, no turn
                add  a, a
                add  a, fx_tab & $FF
                ld   l, a
                adc  a, fx_tab >> 8
                sub  l
                ld   h, a
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                ld   a, (FX_ARG)
                call jp_hl                     ; the op: A = arg -> L = FXR_*
.out:           ld   a, l
                ld   (FX_OP), a
                ret
fx_tab:         DW   fx_none                   ; FX_DRINK (T12)
                DW   fx_none                   ; FX_EAT (T12)
                DW   fx_none                   ; FX_READ (T12)
                DW   fx_equip
                DW   fx_remove
                DW   fx_none                   ; FX_DISCARD (page_post)
                DW   fx_none                   ; FX_TELEPORT (T12)
                ASSERT ($ - fx_tab) / 2 == FX_COUNT - 1 && FX_EQUIP == 4 && FX_REMOVE == 5
fx_none:        ld   l, 0
                ret

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
; fx_done — A = type, E = the S_FX_* stem: the line, hero_recalc, 1 turn.
fx_done:        call fx_line                   ; "<stem><name>", queued
                call hero_recalc
                ld   l, FXR_TURN
                ret
fx_end:
