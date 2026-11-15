;==============================================================================
; rsp0.asm — LARGER-D T5 progress respawn (bank 0, B0_CODE2; INCLUDEd by nm3_b0.asm). Pairs with R6
; trickle6.asm rsp_pick. Bank-0 rules (no SMC, never pages $C000: far6 hands R6 back).
;==============================================================================
;------------------------------------------------------------------------------
; rsp_run — LARGER-D T5 (BANK 0, B0_CODE2: R6 has no room; FARB0 from bank-7 turn_input, rules of nm3_b0.asm) (larger_depths §3.2): the PROGRESS respawn, replacing the time trickle on
; D1-D8 (end_turn no longer counts it). R6 far6 from turn_input on the idle INPUT tick after any
; room entry (lp_transition sets TRK_DUE: the event never runs inside the transition).
;   1. trk_gate; the room just left (TRK_PREV) gets its "last seen" stamp RD_STAMP =
;      (TURN_COUNTER >> 2) & 255 (4-turn units, wraps after 1,024 turns: a stale hit only skips an event);
;   2. only when ROOM_VISITS[CUR_ROOM] == 1 (a FIRST entry; the start room is visited at generation);
;   3. a gameplay-stream byte < RSP_CHANCE (192 = 0.75), else nothing;
;   4. the target: a random UNVISITED room (quota 1..3, not the lair / Sanctum) -> quota + 1 (lp_gen
;      places it on first entry, one more unit of the room's own roll); else a VISITED room that is not
;      the current room nor joined to it by an exit (>= 2 rooms by path), unseen >= RSP_UNSEEN x 4 turns,
;      < LR_MAX entries, not the lair / Sanctum: the trk_draw kind roll + append (LEK_RESPAWN; the 0.4
;      backtrack rule is unchanged); neither -> skipped. LP_RESPAWNS + 1 (the cap, RESPAWN_MAX).
; RNG: RNG_STATE through GEN_RNG, as trk_run. The room pick is uniform (byte mod count) over TRK_W.
; Clobbers: all but IY (far6 / farb: A, F lost).   ~0.2k T gated / not a first entry; a first entry ~3k T (+ trk_draw ~2k)
;------------------------------------------------------------------------------
RD_STAMP        EQU RD_SPARE + 3    ; runtime: the turn clock when the hero last left this room (never read for FRESH / current)
RSP_CHANCE      EQU 192             ; of 256: 0.75 per first entry
RSP_UNSEEN      EQU 38              ; x 4 turns = 152 >= 150 (the stamp's unit is 4 turns)
RSP_NOW         EQU TMP0            ; the current stamp, rsp_w's input (nothing else runs in the tick)
RSP_MODE        EQU TMP1            ; rsp_w: $80 = unvisited rooms, 0 = visited rooms
rsp_run:        ld   a, (LVL_DEPTH)            ; the gate (== trk_run's): PROTO rooms; the boss dead (D1-D7 grate_open,
                or   a                         ; LF_UNIQUE set just before it; D8 .seal: SEAL_OPEN | UNIQUE);
                ret  z                         ; LP_RESPAWNS at RESPAWN_MAX (the D0 tutorial's preset keeps it silent)
                ld   a, (LVL_FLAGS)
                and  LF_GRATE_OPEN | LF_UNIQUE
                ret  nz
                ld   a, (LP_RESPAWNS)
                cp   RESPAWN_MAX
                ret  nc
                ld   hl, (TURN_COUNTER)
                ld   a, l
                rrca
                rrca
                and  $3F
                ld   b, a
                ld   a, h
                rrca
                rrca
                and  $C0
                or   b                         ; (TC >> 2) & 255
                ld   (RSP_NOW), a
                ld   c, a
                ld   a, (TRK_PREV)
                add  a, a
                add  a, a
                add  a, a
                add  a, a                      ; 16 r <= 176
                add  a, (ROOM_DESC & $FF) + RD_STAMP
                ld   l, a
                ld   h, ROOM_DESC >> 8
                ld   (hl), c                   ; the room left was last seen now
                ld   a, (CUR_ROOM)
                add  a, ROOM_VISITS & $FF
                ld   l, a
                ld   h, ROOM_VISITS >> 8
                ld   a, (hl)
                dec  a
                ret  nz                        ; not a first entry
                ld   hl, (RNG_STATE)
                ld   (GEN_RNG), hl
                call gen_step
                ld   a, l
                cp   RSP_CHANCE
                jr   nc, .out                  ; the 0.25: no event
                ld   a, $80
                ld   (RSP_MODE), a             ; unvisited rooms first
                call rsp_w
                ld   a, c
                or   a
                jr   nz, .pk
                xor  a
                ld   (RSP_MODE), a             ; else visited rooms
                call rsp_w
                ld   a, c
                or   a
                jr   z, .out                   ; neither: skipped
.pk:            ld   e, c                      ; far6 loses C: DE = Σ w
                ld   d, 0
                ld   hl, rsp_pick              ; R6 (trickle6.asm): the room + kind pick / the quota
                call far6
.out:           ld   hl, (GEN_RNG)
                ld   (RNG_STATE), hl
                ret
                ASSERT RD_STAMP == RD_STRIDE - 1 && (ROOM_DESC & $FF) + (ROOM_SLOTS - 1) * RD_STRIDE + RD_STAMP <= $FF
                ASSERT (ROOM_VISITS >> 8) == ((ROOM_VISITS + ROOM_SLOTS - 1) >> 8) && RSP_NOW == TMP0 && RSP_MODE == TMP1

;------------------------------------------------------------------------------
; rsp_w — RSP_MODE -> TRK_W[r] = 1 for an eligible room (else 0), C = Σ. Visited mode: the current
; room's exit neighbours are zeroed after the scan (path distance >= 2).
; Clobbers: A, B, C, D, E, HL, IX.   ~2k T
;------------------------------------------------------------------------------
rsp_w:          ld   hl, TRK_W
                ld   ix, LP_REC
                ld   b, 0
.r:             ld   a, (RSP_MODE)
                xor  (ix+LR_HDR)
                jp   p, .no                    ; the wrong kind of record (header bit 7 vs the mode)
                ld   a, (ix+LR_HDR)
                and  LR_CNT_MASK
                cp   LR_MAX
                jr   nc, .no                   ; full (an unvisited quota of 5 would overflow lp_gen's entries)
                or   a
                jr   nz, .q
                ld   a, (RSP_MODE)
                or   a
                jr   nz, .no                   ; an unvisited room with quota 0: not in R
.q:             ld   a, (LVL_LAIR)
                cp   b
                jr   z, .no
                ld   a, (LVL_SANCTUM)
                cp   b
                jr   z, .no
                ld   a, (CUR_ROOM)
                cp   b
                jr   z, .no
                ld   a, (RSP_MODE)
                or   a
                jr   nz, .ok                   ; unvisited: no clock
                ld   a, b
                add  a, a
                add  a, a
                add  a, a
                add  a, a
                add  a, (ROOM_DESC & $FF) + RD_STAMP
                ld   e, a
                ld   d, ROOM_DESC >> 8
                ld   a, (de)
                ld   c, a
                ld   a, (RSP_NOW)
                sub  c                         ; the turns unseen / 4, mod 256
                cp   RSP_UNSEEN
                jr   c, .no
.ok:            ld   a, 1
                jr   .st
.no:            xor  a
.st:            ld   (hl), a
                inc  l
                ld   de, LR_STRIDE
                add  ix, de
                inc  b
                ld   a, b
                cp   GRID_CELLS
                jr   c, .r
                ld   a, (RSP_MODE)
                or   a
                jr   nz, .sum
                ld   a, (CUR_ROOM)             ; visited mode: drop the rooms one exit away
                ld   c, a
                add  a, a
                add  a, a
                add  a, a
                add  a, a
                add  a, (ROOM_DESC & $FF) + RD_EXITS
                ld   l, a
                ld   h, ROOM_DESC >> 8
                ld   d, (hl)                   ; D = the exit bits of the current room
                ld   a, c
                add  a, TRK_W & $FF
                ld   l, a
                ld   h, TRK_W >> 8
                bit  RDX_L_BIT, d
                jr   z, .nl
                dec  l
                ld   (hl), 0
                inc  l
.nl:            bit  RDX_R_BIT, d
                jr   z, .nr
                inc  l
                ld   (hl), 0
                dec  l
.nr:            bit  RDX_U_BIT, d
                jr   z, .nu
                ld   a, l
                sub  GRID_W
                ld   l, a
                ld   (hl), 0
                add  a, GRID_W
                ld   l, a
.nu:            bit  RDX_D_BIT, d
                jr   z, .sum
                ld   a, l
                add  a, GRID_W
                ld   l, a
                ld   (hl), 0
.sum:           ld   hl, TRK_W
                ld   b, GRID_CELLS
                ld   c, 0
.s:             ld   a, c
                add  a, (hl)
                ld   c, a
                inc  l
                djnz .s
                ret
                ASSERT (ROOM_DESC >> 8) == ((ROOM_DESC + ROOM_SLOTS * RD_STRIDE - 1) >> 8) && RD_EXITS < RD_STAMP && LR_HDR == 0
                ASSERT (TRK_W >> 8) == ((TRK_W + ROOM_SLOTS - 1) >> 8) && (ROOM_DESC & $FF) + (ROOM_SLOTS - 1) * RD_STRIDE + RD_EXITS <= $FF

