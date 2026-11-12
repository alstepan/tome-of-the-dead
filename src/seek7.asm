; seek7.asm — AI-SEEK2 (design/ai_seek2.md §2.3 R4-R6; bank-7 cold code, bank7.asm rules: far7 only, no
; SMC, no data). The ladder a standing climber walks to when its segment M is not the hero's
; (PL_SEG = H). Placement: bank 2 has 5 B and R6 2 B free (R6_GROW cannot grow: the boot block + SRC6
; below it have no slack), so the design's Q5 fallback "R6 behind far6" is bank 7 behind far7: same
; far cost (+19 T), 85 B of the 70 B + the try_horizontal edge dedupe (bank7.asm).
;
; seek_col — far7 from bank-3 ai_monster. In: IX = the climber, D = M ($80 = storey 1, else seg0(x) =
;   0 / 1; ai_monster computes it), M != H, PL_SEG = H, ROOM_CUT = K.
;   Out: L = the ladder col (LAD1 / LAD2, {c,1}); L = $FF = STRANDED (no route: ai_monster's R6
;   step; the hook for the pit-stuck ranged fallback, §5).  Clobbers: A, BC, DE, HL (far7 loses A / F).
;   A ladder {c,1}'s top end is seg0(c) = c > K. ~0.3k T (two ladders, one or two passes) + far7.
;   M = storey 1: the ladder whose top is H's half (R4); none -> the nearest of any (R5).
;   M = a half: the ladder in my own half, down (R4); H on storey 0 as well (the 1-hop
;   route, F3) needs a ladder into H's half too, else STRANDED (R6).
;==============================================================================
seek_col:
                ld   a, (PL_SEG)
                ld   b, a                      ; B = H: the first pick is the ladder into H's half (M on
                ld   c, 1                      ; storey 1: R4; M a half and H a half: the 1-hop gate, F3)
                bit  7, d
                jr   nz, .up
                bit  7, b
                jr   nz, .own                  ; H = storey 1: no gate
                push de
                call .pick
                pop  de
                cp   $FF
                jr   z, .ret                   ; no ladder into H's half: STRANDED (R6)
.own:           ld   b, d                      ; the nearest ladder in my own half (C = 1)
.go:            call .pick
.ret:           ld   l, a
                ret
.up:            call .pick                     ; M = storey 1: B = H
                cp   $FF
                jr   nz, .ret
                ld   c, 0                      ; R5: no ladder into H's half: the nearest of any
                jr   .go

; .pick — the nearest ladder col whose top half is B (C = 1; C = 0: any), tie = LAD1.
; Out: A = col / $FF.  Clobbers: A, DE, HL
.pick:          call cur_room_desc
                ld   a, l
                add  a, RD_LAD1                ; (the 16-B page: no carry)
                ld   l, a
                ld   de, $FFFF                 ; D = best col, E = best dist
                call .one
                inc  l
                call .one
                ld   a, d
                ret
.one:           ld   a, (hl)
                or   a
                ret  z                         ; no such ladder
                ld   a, (ROOM_CUT)
                cp   (hl)                      ; CF iff K < c: the top is the right half
                ld   a, b
                adc  a, 0                      ; B + top: odd = the wrong half (B = 0 / 1)
                and  c
                ret  nz
                ld   a, (hl)
                sub  (ix+E_X)
                jr   nc, .p
                neg
.p:             cp   e
                ret  nc                        ; not strictly nearer
                ld   e, a
                ld   d, (hl)
                ret
                ASSERT RD_LAD2 == RD_LAD1 + 1
