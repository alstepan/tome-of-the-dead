;==============================================================================
; drip7.asm — D3-8b decorative drip, bank-7 (cold) part: the room's sources,
; the spawn / let-go steps, the idle gap, hide. The per-tick fall, draw and
; erase are bank 2 (src/drip.asm, header there). Entered through far7 (or
; called from bank-7 code); no data here (the glyphs are bank 2).
;==============================================================================

;------------------------------------------------------------------------------
; drip_room — the tail of vis_room_sync (low RAM, far7): CUR_ROOM's map is in
; ROOM_MAP. Forgets any drawn drop (the screen was redrawn / scrolled) and
; re-derives the room's sources — the B3B-13b placement (git 3831572^
; dg_drips / dg_dat, minus its structural ring scan: a drop only ever falls
; through T_AIR): per depth D1..D8 1, 2, 2, 1, 2, 2, 1, 0 sources (none in the
; PROTO rooms, depth 0), each up to DRIP_TRIES tries of (col = rnd & 31,
; storey = rnd bit, storey row = rnd & 3 if < 3): the cell is T_AIR on map
; row >= 1, the cell above T_PLAT / T_BRICK / T_WALLF (ids 1..3), the cell
; below T_AIR, >= DRIP_DMIN cols from the first source. The LFSR is seeded
; from the room's RD_SEED, so a room keeps its sources on every visit.
; Then IDLE with a random gap (the first drop comes 24..87 ticks after entry).
; Clobbers: A, BC, DE, HL.  Cold: ~3-9k T per room entry.
;------------------------------------------------------------------------------
drip_room:
                xor  a
                ld   (DRIP_DRAWN), a
                ld   (DRIP_N), a
                dec  a
                ld   (DRIP_ROW), a             ; $FF: no drop cell yet (tests: the old
                                               ; room's last cell is not this room's)
                ld   a, (CUR_ROOM)
                add  a, a
                add  a, a
                add  a, a
                add  a, a
                add  a, (ROOM_DESC & $FF) + RD_SEED
                ld   l, a
                ld   h, ROOM_DESC >> 8
                ld   a, (hl)
                inc  l
                xor  (hl)
                jr   nz, .sd
                inc  a                         ; the LFSR must not be 0
.sd:            ld   (DRIP_RND), a
                ld   a, (LVL_DEPTH)
                dec  a
                cp   LEVELS - 1
                ret  nc                        ; PROTO (0) and D8: no drip
                ld   b, 1                      ; (d - 1) mod 3 == 0 (D1 / D4 / D7): 1
.m3:            sub  3
                jr   nc, .m3
                cp   -3
                jr   z, .one
                inc  b                         ; else 2
.one:
.src:           push bc
                ld   b, DRIP_TRIES
.try:           push bc
                call drip_try
                pop  bc
                jr   c, .next                  ; placed
                djnz .try
.next:          pop  bc
                djnz .src
                ; fall through: IDLE + the first gap
                ASSERT DRIP_SRC_MAX == 2 && LEVELS == 8 && ROOM_DESC + 9 * RD_STRIDE <= (ROOM_DESC | $FF) + 1

;------------------------------------------------------------------------------
; drip_idle — DRIP_ST = IDLE, DRIP_T = DRIP_GAP + (rnd & DRIP_GAP_RND).
; Clobbers: A, HL
;------------------------------------------------------------------------------
drip_idle:
                call drip_rnd
                and  DRIP_GAP_RND
                add  a, DRIP_GAP
                ld   (DRIP_T), a
                xor  a
                ld   (DRIP_ST), a
                ret
                ASSERT DRS_IDLE == 0 && DRIP_GAP >= 1 && DRIP_GAP + DRIP_GAP_RND <= 255

; drip_rnd — A = the next DRIP_RND (8-bit Galois LFSR, x^8+x^4+x^3+x^2+1:
; period 255 over 1..255).  Clobbers: A, F
drip_rnd:
                ld   a, (DRIP_RND)
                add  a, a
                jr   nc, .n
                xor  $1D
.n:             ld   (DRIP_RND), a
                ret

; drip_try — one placement try (always 3 rnd calls). CF = 1: the source was
; appended to DRIP_SRC.  Clobbers: A, BC, DE, HL
drip_try:
                call drip_rnd
                and  ROOM_COLS - 1
                ld   c, a                      ; C = col
                call drip_rnd
                and  3
                ld   b, a                      ; B = storey row 0..2 (3: no)
                call drip_rnd
                ld   e, a                      ; bit 0: the storey
                ld   a, b
                cp   3
                jr   z, .no
                rr   e
                jr   nc, .s0
                add  a, STOREY_ROWS            ; storey 1
.s0:            ld   b, a                      ; B = map row
                or   a
                jr   z, .no                    ; map row 0: nothing above it
                call cell_addr                 ; HL = ROOM_MAP (row B, col C)
                ld   a, (hl)
                or   a
                jr   nz, .no                   ; the cell is T_AIR
                ld   de, -ROOM_COLS
                add  hl, de
                ld   a, (hl)
                dec  a
                cp   T_WALLF
                jr   nc, .no                   ; above: T_PLAT / T_BRICK / T_WALLF (1..3)
                ld   de, 2 * ROOM_COLS
                add  hl, de
                ld   a, (hl)
                or   a
                jr   nz, .no                   ; below: T_AIR
                ld   hl, DRIP_N
                ld   a, (hl)
                or   a
                jr   z, .put
                ld   a, (DRIP_SRC)             ; the 2nd source: >= DRIP_DMIN cols away
                sub  c
                jr   nc, .p
                neg
.p:             cp   DRIP_DMIN
                jr   c, .no
                ld   a, (hl)
.put:           inc  (hl)
                add  a, a
                add  a, DRIP_SRC & $FF
                ld   l, a
                ld   h, DRIP_SRC >> 8
                ld   (hl), c
                inc  l
                ld   (hl), b
                scf
                ret
.no:            or   a
                ret
                ASSERT T_PLAT == 1 && T_BRICK == 2 && T_WALLF == 3 && T_AIR == 0
                ASSERT (DRIP_SRC >> 8) == ((DRIP_SRC + 2 * DRIP_SRC_MAX - 1) >> 8)

;------------------------------------------------------------------------------
; drip_step — far7 from drip_tick when DRIP_T ran out in IDLE or FORM.
; IDLE: a drop forms at a source (random of DRIP_N) if its cell is still T_AIR
; and no body / FX covers it, else another gap. FORM: it lets go (the DROP
; frame) in place. Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
drip_step:
                ld   a, (DRIP_ST)
                or   a
                jr   nz, .go
                ld   a, (DRIP_N)
                dec  a
                ld   b, a                      ; 0 (one source) or 1
                call drip_rnd
                and  b
                add  a, a
                add  a, DRIP_SRC & $FF
                ld   l, a
                ld   h, DRIP_SRC >> 8
                ld   c, (hl)
                inc  l
                ld   b, (hl)
                call cell_addr
                ld   a, (hl)
                or   a
                jp   nz, drip_idle             ; not air any more (a closed door)
                call cell_occ
                jp   c, drip_idle              ; a body / FX on the source: later
                ld   (DRIP_COL), bc
                ld   a, DRS_FORM
                ld   (DRIP_ST), a
                ld   a, DRIP_FORM_T
                ld   (DRIP_T), a
                ld   hl, drip_g_form
                jp   drip_draw
.go:            ld   bc, (DRIP_COL)            ; FORM -> DROP in place. drip_tick's cover
                call cell_addr                 ; test ran this tick; re-check T_AIR: a map
                ld   a, (hl)                   ; rewrite (a door closing) repainted the
                or   a                         ; cell over the hanging drop: forget it
                jr   z, .air
                xor  a
                ld   (DRIP_DRAWN), a
                jp   drip_idle
.air:           ld   a, DRS_DROP
                ld   (DRIP_ST), a
                ld   a, DRIP_DROP_T
                ld   (DRIP_T), a
                ld   hl, drip_g_drop
                jp   drip_draw
                ASSERT DRIP_SRC_MAX == 2

;------------------------------------------------------------------------------
; drip_cover — far7 from drip_tick: a body / FX now covers the drawn drop.
; Forget it without erasing (that would wipe the body); queue_damage makes
; the next render restore the cell from the map and repair what covers it,
; so no drop pixels stay inside a body's cell. Then IDLE.
; drip_land — far7 from drip_tick: the drop reached the floor (or a body /
; FX below): erased, then IDLE.  Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
drip_cover:
                ld   bc, (DRIP_COL)
                ld   de, $0101
                call queue_damage
                xor  a
                ld   (DRIP_DRAWN), a
                jp   drip_idle
drip_land:
                call drip_erase
                jp   drip_idle

;------------------------------------------------------------------------------
; drip_hide — hide_sprites (before a room transition): erase a drawn drop,
; no drip until drip_room re-derives (vis_room_sync after the arrival).
; Leaves bank 7 paged.  Clobbers: A, BC, DE, HL
;------------------------------------------------------------------------------
drip_hide:
                ld   a, (DRIP_DRAWN)
                or   a
                call nz, drip_erase
                xor  a
                ld   (DRIP_N), a
                ret
