;==============================================================================
; io.asm — PROTO input layer + RNG.
;
; Input: COPIED (not shared) from main.asm's P3 layer, keeping the exact
; INPUT_SRC / KBD_MATRIX test-injection contract. Copy rather than factor
; because main.asm's primitives are inline in main.asm (factoring would move its
; bytes) and PROTO's semantics differ anyway (held keys repeat, no diagonals,
; extra 1/2/3/G/Enter/'.' keys) — prototype §3.1/§9.
;
; RNG: xorshift16 (7,9,8), foundations F3 — main.asm only seeds
; RNG_STATE, it has no generator yet, so this is the first implementation.
;==============================================================================

; discrete key bits (PLAYER_DISC)
DK_QUAFF        EQU %00000001
DK_WAIT         EQU %00000010
DK_ENTER        EQU %00000100
DK_1            EQU %00001000
DK_2            EQU %00010000
DK_3            EQU %00100000
DK_QUAFF_BIT    EQU 0
DK_WAIT_BIT     EQU 1
DK_ENTER_BIT    EQU 2
DK_1_BIT        EQU 3
DK_2_BIT        EQU 4
DK_3_BIT        EQU 5

KB_1_BIT        EQU 0               ; KBROW_12345
KB_2_BIT        EQU 1
KB_3_BIT        EQU 2
KB_SYM_BIT      EQU 1               ; KBROW_SPACE
KB_M_BIT        EQU 2

;==============================================================================
; scan_matrix — copy the 8 keyboard half-rows into KBD_MATRIX, unless
; INPUT_SRC != 0 (test injection: keep the poked mirror). Same as main.asm.
; Clobbers: A, BC, D, HL      ~ 8 x 45 T = 360 T
;==============================================================================
scan_matrix:
                ld   a, (INPUT_SRC)
                or   a
                ret  nz
                ld   hl, KBD_MATRIX
                ld   c, $FE
                ld   b, $FE
                ld   d, KBD_MATRIX_LEN
.row:
                in   a, (c)
                ld   (hl), a
                inc  hl
                rlc  b
                dec  d
                jr   nz, .row
                ret

;==============================================================================
; sample_input — fold held keys into PLAYER_DIR (DIR_* bits) and PLAYER_DISC
; (DK_* bits). Out: A = DIR | DISC (NZ iff anything held).  Clobbers: A, E, HL
;==============================================================================
sample_input:
                ld   e, 0
                ld   hl, KBD_MATRIX + KBROW_HJKL
                ld   a, (hl)
                bit  KB_L_BIT, a
                jr   nz, .nL
                set  DIR_E_BIT, e
.nL:            bit  KB_H_BIT, a
                jr   nz, .nH
                set  DIR_W_BIT, e
.nH:            bit  KB_K_BIT, a
                jr   nz, .nK
                set  DIR_N_BIT, e
.nK:            bit  KB_J_BIT, a
                jr   nz, .nJ
                set  DIR_S_BIT, e
.nJ:            ld   a, (KBD_MATRIX + KBROW_POIUY)
                bit  KB_P_BIT, a
                jr   nz, .nP
                set  DIR_E_BIT, e
.nP:            bit  KB_O_BIT, a
                jr   nz, .nO
                set  DIR_W_BIT, e
.nO:            ld   a, (KBD_MATRIX + KBROW_QWERT)
                bit  KB_Q_BIT, a
                jr   nz, .nQ
                set  DIR_N_BIT, e
.nQ:            ld   a, (KBD_MATRIX + KBROW_ASDFG)
                bit  KB_A_BIT, a
                jr   nz, .nA
                set  DIR_S_BIT, e
.nA:            ld   a, e
                ld   (PLAYER_DIR), a
                ; --- discrete keys ---
                ld   e, 0
                ld   a, (KBD_MATRIX + KBROW_ASDFG)
                bit  KB_G_BIT, a
                jr   nz, .nG
                set  DK_QUAFF_BIT, e
.nG:            ld   a, (KBD_MATRIX + KBROW_SPACE)
                bit  KB_SPACE_BIT, a
                jr   nz, .nSp
                set  DK_WAIT_BIT, e
.nSp:           and  (1 << KB_SYM_BIT) | (1 << KB_M_BIT)
                jr   nz, .nDot               ; '.' = SYMBOL SHIFT + M
                set  DK_WAIT_BIT, e
.nDot:          ld   a, (KBD_MATRIX + KBROW_HJKL)
                bit  KB_ENTER_BIT, a
                jr   nz, .nEn
                set  DK_ENTER_BIT, e
.nEn:           ld   a, (KBD_MATRIX + KBROW_12345)
                bit  KB_1_BIT, a
                jr   nz, .n1
                set  DK_1_BIT, e
.n1:            bit  KB_2_BIT, a
                jr   nz, .n2
                set  DK_2_BIT, e
.n2:            bit  KB_3_BIT, a
                jr   nz, .n3
                set  DK_3_BIT, e
.n3:            ld   a, e
                ld   (PLAYER_DISC), a
                ld   hl, PLAYER_DIR
                or   (hl)
                ret

;==============================================================================
; rng_next — xorshift16, triplet (7,9,8) (J. Metcalf's Z80 form).
; Out: HL = new state (also stored), A = L (the rng_byte).  Clobbers: A, HL
; ~ 90 T. Never yields 0 from a non-zero seed; period 65535.
;==============================================================================
rng_next:
                ld   hl, (RNG_STATE)
                ld   a, h
                rra
                ld   a, l
                rra
                xor  h
                ld   h, a
                ld   a, l
                rra
                ld   a, h
                rra
                xor  l
                ld   l, a
                xor  h
                ld   h, a
                ld   (RNG_STATE), hl
                ld   a, l
                ret

;==============================================================================
; rng_mod — uniform 0..C-1 by mask-and-reject (no divide, no modulo bias).
; In : C = n (1..128).  Out: A = 0..n-1.  Clobbers: A, B, HL
;==============================================================================
rng_mod:
                ld   a, c
                dec  a
                ld   b, a                    ; B = n-1 -> smear to a 2^k-1 mask
                srl  a
                or   b
                ld   b, a
                srl  a
                srl  a
                or   b
                ld   b, a
                srl  a
                srl  a
                srl  a
                srl  a
                or   b
                ld   b, a                    ; B = mask
.again:
                call rng_next
                and  b
                cp   c
                jr   nc, .again              ; reject >= n
                ret
