;==============================================================================
; jump6.asm — RECLAIM-SV R3: try_jump's pit test (was low RAM). R6 rules (r6.asm): far6
; only; pit_range is low RAM, TMP6 / TMP7 / JUMP_ARC bank-2 RAM.
;==============================================================================
;------------------------------------------------------------------------------
; jump_pit6 — RECLAIM-SV R3 (was low-RAM jump_pit): far6 from try_jump on the storey-0
; floor, IX = hero (C = x = E_X re-read: far6 passes no BC), TMP6 = dx, TMP7 = x',
; JUMP_ARC = n | D7. Pit p, width W (pit_w; game.md §2.4 "Landing in a pit",
; §2.5): x' in p .. p+W-3 -> fall at x'; else W >= 4 and a hole col in the
; cleared span -> fall at x_f = p+W-3 (right) / p (left), n = 2 |x_f - x|.
; Sets JA_FALL_BIT on a fall.  Keeps DE (try_jump keeps its BC).  Clobbers: A, C, HL
;------------------------------------------------------------------------------
jump_pit6:      ld   c, (ix+E_X)               ; x (try_jump's C: the hero has not moved yet)
                push bc
                ld   a, (TMP7)
                ld   c, a
                call pit_range                 ; H = p, L = W - 2 (p = 0: no pit)
                pop  bc
                jr   c, .fall                  ; p <= x' <= p+W-3: x_f = x'
                inc  h
                dec  h
                ret  z                         ; no pit
                ld   a, l
                cp   2
                ret  c                         ; narrow: never cut short
                ld   a, (TMP6)
                dec  a
                jr   nz, .left
                ld   a, (TMP7)                 ; right: hole in x+3 .. x'-1 iff
                dec  a                         ; p <= x'-1 and p+W-1 >= x+3
                cp   h
                ret  c
                ld   a, h
                add  a, l
                sub  2
                cp   c
                ret  c
                ld   a, h
                add  a, l
                dec  a                         ; x_f = p+W-3
                jr   .cut
.left:          ld   a, h                      ; left: hole in x'+3 .. x-1 iff
                cp   c                         ; p <= x-1 and p+W-1 >= x'+3
                ret  nc
                add  a, l
                dec  a
                ld   l, a
                ld   a, (TMP7)
                cp   l
                ret  nc
                ld   a, h                      ; x_f = p
.cut:           ld   (TMP7), a
                sub  c
                jr   nc, .ab
                neg                            ; |x_f - x|
.ab:            add  a, a
                ld   l, a                      ; n = 2 |x_f - x|
                ld   a, (JUMP_ARC)
                and  ~JA_N & $FF
                or   l
                ld   (JUMP_ARC), a
.fall:          ld   a, (JUMP_ARC)
                set  JA_FALL_BIT, a
                ld   (JUMP_ARC), a
                ret
