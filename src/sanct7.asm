;==============================================================================
; sanct7.asm — 3F-T10: the D8 Sanctum leaf (only with -DF3_GEN=1, else 0 B).
; sanctum_leaf == tools/levelgen.py sanctum_pass, byte-exact (tests/levelgen_z80.py --f3).
; M0 (lever L1): bank 7, the high block after the tilesets (main.asm b7h_code; was
; R6 sanct6.asm), so the 3F switch costs R6 nothing. Bank 3's cold code is full; the
; bank-3 caller is level_gen's tail (`ld hl, sanctum_leaf / jp far7`, every depth).
; Reads / writes only bank-5 low RAM (LVL_STATE), no bank-7 data, no SMC.
;
; The reserved bottom-row end cell S (6 or 8: the one the DFS never entered) becomes a
; leaf behind the lair's (7) SEALED edge EG_LINK|EG_DOOR|EG_SEAL; room flags
; PRESENT|DEADEND|SANCTUM, one ladder col, a room seed. Own stream, kept in HL (no
; memory, GEN_RNG untouched): x0 = LVL_SEED ^ SANCT_SALT ^ depth*$0101 (= ^ $521F, 0 -> 1),
; calls in the Python order: rnd(2) edge storey, rnd(24) ladder col (its pick_feature
; accepts the 1st try: the empty room has no footprints), rnd16 room seed.
;
; Entered as level_gen's tail (jp far7): also writes LVL_FLAGS = 0 (all depths), B = 0.
; In : the level generated (LVL_SEED = the seed used). Out: LVL_SANCTUM = S,
;      LVL_NROOMS + 1, the edge / exits / room written, TOME_HP = TOME_MAX (P3).
;      Clobbers all but IY.
; Cost: ~2.1k T. No SMC.
;==============================================================================
SANCT_XOR       EQU $521F
                ASSERT (EDGE_TAB >> 8) == ((EDGE_TAB + 5) >> 8) && RD_EXITS == 1 && RD_STRIDE == 16 && RD_SEED + 1 < RD_STRIDE
                ASSERT (ROOM_DESC >> 8) == ((ROOM_DESC + 8 * RD_STRIDE + RD_STRIDE - 1) >> 8)
                ASSERT (TOME_HP >> 8) == (EDGE_TAB >> 8)

sn_step:                                ; HL = xorshift(7,9,8)(HL) (lg_step without the memory); A clobbered
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
                ret

sanctum_leaf:   xor  a
                ld   (LVL_FLAGS), a     ; 3F, every depth: the grate opens on the boss's death
                ld   b, a               ; B = 0 for level_gen's caller (restore_page keeps BC)
                ld   a, (LVL_DEPTH)
                cp   8
                ret  nz
                ld   hl, (LVL_SEED)
                ld   a, h
                xor  SANCT_XOR >> 8
                ld   h, a
                ld   a, l
                xor  SANCT_XOR & $FF
                ld   l, a
                or   h
                jr   nz, .nz
                inc  l                  ; x = 0 would lock the xorshift
.nz:            call sn_step            ; rnd(2): the edge's storey s
                ld   a, l
                and  1
                rrca
                rrca
                rrca
                rrca                    ; s ? RDX_LS1 : 0
                ld   b, a
                add  a, a               ; RDX_RS1 = 2 * RDX_LS1
                or   RDX_R
                ld   c, a               ; C = the left room's exit bits (R | RS1)
                ld   a, b
                or   RDX_L
                ld   b, a               ; B = the right room's (L | LS1)
                call sn_step            ; rnd(24): ladder col
                ld   a, l
.m:             sub  LAD_COL_MAX - LAD_COL_MIN + 1
                jr   nc, .m
                add  a, LAD_COL_MAX - LAD_COL_MIN + 1 + LAD_COL_MIN
                ld   d, a
                call sn_step            ; rnd16: room seed
                push hl
                ld   hl, ROOM_DESC + 6 * RD_STRIDE   ; left room of the pair
                ld   e, 6               ; E = S
                bit  0, (hl)
                jr   z, .a              ; room 6 absent: S = 6, pair (6, 7)
                ld   e, 8
                ld   l, (ROOM_DESC & $FF) + 7 * RD_STRIDE   ; pair (7, 8)
.a:             inc  l                  ; -> RD_EXITS
                ld   a, (hl)
                or   c
                ld   (hl), a
                ld   a, l
                add  a, RD_STRIDE
                ld   l, a
                ld   a, (hl)
                or   b
                ld   (hl), a
                ld   a, e
                ld   (LVL_SANCTUM), a
                srl  a                  ; S / 2 = 3 / 4; the edge index is hedge(left room) = 4 / 5
                add  a, (EDGE_TAB & $FF) + 1
                ld   l, a
                ld   h, EDGE_TAB >> 8
                ld   (hl), EG_LINK | EG_DOOR | EG_SEAL
                ld   l, TOME_HP & $FF   ; P3 (game.md §1.3): the Tome's hp, once per level (it never
                ld   (hl), TOME_MAX     ; regenerates: leaving the Sanctum keeps the damage)
                ld   a, e
                add  a, a
                add  a, a
                add  a, a
                add  a, a               ; 16 * S
                add  a, ROOM_DESC & $FF
                ld   l, a
                ld   h, ROOM_DESC >> 8
                ld   (hl), RDF_PRESENT | RDF_DEADEND | RDF_SANCTUM
                add  a, RD_LAD1
                ld   l, a
                ld   (hl), d
                add  a, RD_SEED - RD_LAD1
                ld   l, a
                pop  de
                ld   (hl), e
                inc  l
                ld   (hl), d
                ld   hl, LVL_NROOMS
                inc  (hl)
                ld   b, 0
                ret
