;==============================================================================
; trickle6.asm — 3F-T12 the respawn trickle (game.md §9.5; R6, r6.asm rules:
; far6 only, no SMC, no bank-3 code / data). Byte-exact reference:
; tools/respawn_model.py trickle_check (the 3F-D2 draw order).
;
; Lazy population: the trickle APPENDS one {kind byte | LEK_RESPAWN, depth-scaled
; hp} entry to a VISITED room record and never touches a slot (the target is
; never CUR_ROOM: lp_enter places it on the hero's next entry, §9.4.3). It runs
; at end_turn only (bank 7, after the exit / sp_run / TURN_COUNTER++), every
; RESPAWN_PERIOD turns of the level (TRK_PHASE, zeroed with LVL_STATE by
; level_gen) — never in a cast / input tick.
;
; RNG: every draw is on RNG_STATE (gameplay stream, §9.5). The shared §9.6 roll
; tier_row steps GEN_RNG (gen_step), so trk_run copies RNG_STATE into GEN_RNG,
; draws through gen_step and copies it back. GEN_RNG is NOT restored: between
; level generations nothing consumes it (lp_enter saves, reseeds and restores it
; around its own spawn stream; level_gen / lp_budget / the items overlay reseed
; it), so it simply keeps the gameplay stream's last value (-8 B). Steps 1-4
; draw nothing: an empty set leaves RNG_STATE alone.
;==============================================================================

;------------------------------------------------------------------------------
; trk_run — far6 from end_turn on a RESPAWN_PERIOD turn: §9.5 steps 2-10.
;   2. a level (LVL_DEPTH), boss alive (LF_GRATE_OPEN, LF_UNIQUE clear), LP_RESPAWNS < MAX;
;   3. w_r = min(RESPAWN_ITEM_CAP, 1 + 2 x live FLOOR_LIST entries of r) for r
;      VISITED, entries < 4, not CUR_ROOM / TRK_PREV / LVL_LAIR / LVL_SANCTUM,
;      Σ(entry weights) + minW <= 12; else 0 -> TRK_W[r] (ascending id);
;   4. Σ w = 0 -> stop;  5-10: trk_draw.
; Clobbers: all but IY.   ~0.1k T stopped at step 2; a full check ~6-9k T
;   (32 floor entries, 9 records x <= 4 sp_wt, the draws incl. 2 tier rolls)
;------------------------------------------------------------------------------
trk_run:        ld   a, (LVL_DEPTH)
                or   a
                ret  z                         ; PROTO rooms: no LP
                ld   a, (LVL_FLAGS)
                and  LF_GRATE_OPEN | LF_UNIQUE ; the boss is dead: D1-D7 grate_open (LF_UNIQUE set just before
                ret  nz                        ; it), D8 .seal (LF_SEAL_OPEN | LF_UNIQUE, the grate stays shut)
                ld   a, (LP_RESPAWNS)
                cp   RESPAWN_MAX
                ret  nc
                ; TRK_W[r] = the live floor entries of r: one pass over every entry
                ; (drops reuse any FL_EMPTY slot, so FLOOR_N is not a bound)
                ld   hl, TRK_W
                ld   b, GRID_CELLS
                xor  a
.z:             ld   (hl), a
                inc  l
                djnz .z
                ld   hl, FLOOR_LIST
                ld   bc, FLOOR_MAX << 8        ; B = entries, C = 0 = Σ w (below)
                ld   d, TRK_W >> 8
.f:             ld   a, (hl)                   ; FL_ROOM
                cp   FL_EMPTY
                jr   z, .fn
                and  FL_ROOM_MASK
                add  a, TRK_W & $FF
                ld   e, a
                ld   a, (de)
                inc  a
                ld   (de), a
.fn:            ld   a, l
                add  a, FL_STRIDE
                ld   l, a                      ; (FLOOR_LIST: one page)
                djnz .f
                call lp_minw                   ; (tier6.asm; B, HL; keeps DE) A = minW
                cpl
                add  a, LP_SIGMA_CAP + 2
                ld   d, a                      ; D = 13 - minW: Σ < D passes
                ld   c, b                      ; (B = 0 after lp_minw's djnz) C = Σ w
                ; ascending id: B = r, C = Σ w, HL = TRK_W + r, IX = the record
                ld   l, TRK_W & $FF            ; (H: lp_minw left LP_KINDS' page = TRK_W's)
                ld   ix, LP_REC
.r:             ld   a, (ix+LR_HDR)
                sub  LR_VISITED
                cp   LR_MAX
                jr   nc, .no                   ; FRESH, or 4 entries
                ld   a, (CUR_ROOM)
                cp   b
                jr   z, .no
                ld   a, (TRK_PREV)
                cp   b
                jr   z, .no
                ld   a, (LVL_LAIR)
                cp   b
                jr   z, .no
                ld   a, (LVL_SANCTUM)
                cp   b
                jr   z, .no
                push hl
                call trk_sig                   ; A = Σ (keeps BC, D, IX)
                pop  hl
                cp   d
                jr   nc, .no                   ; Σ + minW > 12
                ld   a, (hl)                   ; items
                add  a, a
                inc  a                         ; 1 + RESPAWN_ITEM_W x items (<= 65)
                cp   RESPAWN_ITEM_CAP + 1
                jr   c, .st
                ld   a, RESPAWN_ITEM_CAP
                jr   .st
.no:            xor  a
.st:            ld   (hl), a
                add  a, c
                ld   c, a
                inc  l
                push de
                ld   de, LR_STRIDE
                add  ix, de
                pop  de
                inc  b
                ld   a, b
                cp   GRID_CELLS
                jr   c, .r
                ld   a, c
                or   a
                ret  z                         ; step 4: no eligible room, no draw
                ld   hl, (RNG_STATE)           ; steps 5-10 on the gameplay stream
                ld   (GEN_RNG), hl
                call trk_draw
                ld   hl, (GEN_RNG)
                ld   (RNG_STATE), hl
                ret
                ASSERT LF_GRATE_OPEN == 1 && RESPAWN_ITEM_W == 2 && LP_SIGMA_CAP + 2 == 14
                ASSERT (TRK_W >> 8) == ((TRK_W + GRID_CELLS - 1) >> 8) && (FLOOR_LIST & $FF) + FLOOR_MAX * FL_STRIDE <= $100
                ASSERT LR_HDR == 0 && LR_VISITED == $80 && LR_MAX == 4 && (LP_KINDS >> 8) == (TRK_W >> 8)

;------------------------------------------------------------------------------
; trk_sig — IX = a record -> A = Σ of its entries' §9.3 weights (sp_wt: tier row
; + golden), HL = the record + 2 x count (the last entry's LE_HP; the header if
; empty). Keeps BC, D, IX.  Clobbers: A, E, HL.   ~0.1k T + ~0.1k T an entry
;------------------------------------------------------------------------------
trk_sig:        push bc
                push ix
                pop  hl
                ld   a, (hl)
                and  LR_CNT_MASK
                ld   b, a
                ld   e, 0
                jr   z, .d
.l:             inc  hl
                ld   a, (hl)                   ; LE_KIND
                inc  hl                        ; LE_HP
                call sp_wt                     ; (spawn6.asm; keeps B, DE, HL)
                add  a, e
                ld   e, a
                djnz .l
.d:             ld   a, e
                pop  bc
                ret

;------------------------------------------------------------------------------
; trk_draw — §9.5 steps 5-10, C = Σ w (>= 1), TRK_W = the weights; the draws
; through gen_step (GEN_RNG = the gameplay stream here, see trk_run):
;   5. byte >= RESPAWN_CHANCE -> stop;  6. room = byte mod Σ w walked over TRK_W;
;   7. k = byte & 3, tier_row(LP_KINDS[k], the current LVL) (draws only if tiered);
;   8. Σ + w <= 12 -> 10;  9. once: k + 1 & 3, its tier roll, the cap; fail = stop;
;  10. append {row | LEK_RESPAWN, kind_hp} (the record stays VISITED), LP_RESPAWNS + 1.
; Clobbers: all but IY.   ~1.5-2.5k T
;------------------------------------------------------------------------------
trk_draw:       call gen_step                  ; (bank 2) L = the byte
                ld   a, l
                cp   RESPAWN_CHANCE
                ret  nc
                call gen_step
                ld   a, l
.m:             sub  c
                jr   nc, .m
                add  a, c                      ; v = byte mod Σ w (levelgen.py Rng.rnd)
                ld   hl, TRK_W
                ld   ix, LP_REC
                ld   de, LR_STRIDE
.p:             sub  (hl)
                jr   c, .hit                   ; v < w_r (w 0 never hits); IX = its record
                inc  l
                add  ix, de
                jr   .p
.hit:           call gen_step
                ld   a, l
                and  3
                ld   e, a                      ; E = k
                ld   d, 2                      ; D = tries
.k:             push de
                ld   a, e
                add  a, LP_KINDS & $FF
                ld   l, a
                ld   h, LP_KINDS >> 8
                ld   a, (LVL)
                ld   c, a                      ; the current LVL (§9.5 step 7)
                ld   a, (hl)
                push af
                call tier_row                  ; (tier6.asm) A = the tier row, 0 = the base
                pop  bc                        ; B = the base row
                or   a
                jr   nz, .t
                ld   a, b
.t:             or   LEK_RESPAWN
                ld   b, a                      ; B = the kind byte
                call sp_wt                     ; A = w (keeps B, DE, HL)
                ld   c, a
                call trk_sig                   ; A = Σ, HL = the last entry's LE_HP (keeps BC)
                pop  de
                add  a, c
                cp   LP_SIGMA_CAP + 1
                jr   c, .ok
                inc  e
                res  2, e                      ; k + 1 & 3
                dec  d
                jr   nz, .k
                ret                            ; both tries refused: the draws are spent
.ok:            push hl
                ld   a, b
                call kind_hp                   ; (tier6.asm; C, HL) depth-scaled, never golden
                pop  hl
                inc  hl
                ld   (hl), b                   ; LE_KIND of entry n (record + 1 + 2n)
                inc  hl
                ld   (hl), a                   ; LE_HP
                inc  (ix+LR_HDR)               ; count + 1 (VISITED kept)
                ld   hl, LP_RESPAWNS
                inc  (hl)
                ret
                ASSERT LR_ENT == 1 && LE_STRIDE == 2 && LE_KIND == 0 && LE_HP == 1 && LR_STRIDE == 9
                ASSERT (LP_KINDS >> 8) == ((LP_KINDS + 3) >> 8) && (TRK_W & $FF) + GRID_CELLS <= $100
