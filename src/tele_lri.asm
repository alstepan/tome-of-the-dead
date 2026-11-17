;------------------------------------------------------------------------------
; tele_lri.asm — BALANCE-PKG5 C1 (balance_v2 §7c, the safe Teleport landing) + tp_ok: the
; boot-installed low-RAM block (PKG5+FLY-CUT reclaim; were HOT_COPY tele_hot.asm and low-RAM dscl.asm).
; Assembled DISP'd at tape_tab (main.asm "LOW-RAM INSTALLED BLOCK", with the TUT0 stubs at
; check_paging after it) and copied there by the INSTR overlay (instr_ovl.asm in_tut) once tape_tab
; (start's block list, read by in_tut) is dead: 0 resident bytes. Bank 5: callable with any bank at
; $C000 (R6 tele_pick / tp_room call it with bank 6 paged). Not live before boot's INSTR overlay ran:
; no caller before a game starts. Contended (low RAM): + ~10-20 T a call (teleport only).
;
; tp_safe — R6 tele_pick's room filter (bank 6 paged), B = an otherwise eligible room:
; Z = keep it: pass 2 (tp_msk 0: today's rule, every eligible room), or pass 1 (tp_msk = TP_SAFE)
; and its LP record header == LR_VISITED exactly (entered before, 0 banked residents: no lazy spawn
; on arrival, no body near the landing). NZ = skip. Keeps BC, DE, HL.  Clobbers: A, F.   ~0.1k T
;------------------------------------------------------------------------------
tp_safe:        push hl
                ld   a, b
                add  a, a
                add  a, a
                add  a, a
                add  a, b                      ; 9 x room (LR_STRIDE), all of LP in one page
                add  a, LP_REC & $FF
                ld   l, a
                ld   h, LP_REC >> 8
                ld   a, (hl)                   ; LR_HDR: bit 7 VISITED, bits 0-2 the count
                xor  LR_VISITED
                ld   hl, tp_msk
                and  (hl)                      ; pass 2: 0 -> Z
                pop  hl
                ret
                ASSERT LR_STRIDE == 9 && LR_HDR == 0 && (LP_REC >> 8) == ((LP_REC + ROOM_SLOTS * LR_STRIDE - 1) >> 8)
tp_msk:         DB   0                         ; tele_pick C1: TP_SAFE (pass 1) / 0 (pass 2); runtime (low RAM)

;------------------------------------------------------------------------------
; tp_ok — tele_pick's / tp_room's spot test (R6 fx6.asm, called with bank 6
; paged; moved verbatim by BALANCE-PKG5 from R6 to low RAM dscl.asm, then here).
; D = storey, E = col: Z = LP_CMAP clear under cols E .. E+2.
; Keeps BC, DE.  Clobbers: A, HL.   ~90 T (+ contention: low RAM)
;------------------------------------------------------------------------------
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
