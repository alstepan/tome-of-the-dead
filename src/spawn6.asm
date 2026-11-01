;==============================================================================
; spawn6.asm — 3F-T9 mid-room spawns (R6; r6.asm rules: far6 / direct calls
; from R6 only, no SMC, no bank-3 code or data). docs/memory-map.md "3F-T9".
;
; The producers only DECIDE and fill the 1-entry spawn queue (SPQ_*, bank 5):
;   breed6     far6 from deal_hit (bank 3): a Rabbit Rat hit and alive, 1 in
;              BREED_N, once per Rabbit Rat (RCD_ONCE / LEK_BRED) -> one base Rat
;              (game.md §9.6);
;   sp_bcall   ai_ranged's caster pre-rule slot (ranged6.asm, RWF_PRE): the Bone
;              Caller -> one base Skeleton if Skeleton is in LP_KINDS, else a Ghost
;              (§9.4.6), cooldown BC_CD, <= BC_LIVE live summons (§9.6);
;   ph_summon  far6 from ai_guard (boss7.asm): the Golden Pharaoh raises ONE
;              Skeleton / Mummy at a time (plan.md PHARAOH ABILITY, user option 2), PH_LIVE 1;
;   the ALARM trap (trap7.asm tr_eff) -> a wave of 1 + (rnd & 1) LP_KINDS bodies at a
;              door of the room (§1.5 / §9.5 idle-wave placement).
; end_turn (bank 7) far6s sp_run, which places and creates them: the spawn work
; never lands in a cast / input tick (lcastf is the tightest gated tick).
; Bodies: F_RESPAWN (no drops, half XP); summons and offspring are summon-made
; (RCD_SUMMONED: lp_bank discards them, §9.4.2); the ALARM wave is banked like
; anyone. Every body passes the §9.3 cap (<= ROOM_CAP monsters, Σ weight <=
; LP_SIGMA_CAP) and needs a free slot; a body that does not fit ends the run.
; Summons / offspring appear at once (a legal cell beside the parent); the wave
; arrives PENDING at the door (horizontal: EF_WALKIN, as followers) and
; materialise walks it in. Each made body is followed by build_live (LIVE_LIST
; for the next body's box_free; PEND_N: the 3F-B4 rule).
;==============================================================================

;------------------------------------------------------------------------------
; sp_wt — A = kind byte (row | LEK_GOLD) -> A = its §9.3 weight (lp_wt + 1 if
; golden). Keeps B, DE, HL.  Clobbers: C.
;------------------------------------------------------------------------------
sp_wt:          ld   c, a
                and  LEK_KIND_MASK
                add  a, lp_wt & $FF           ; (lp_wt: one page, r6.asm)
                push hl
                ld   l, a
                ld   h, lp_wt >> 8
                ld   a, (hl)
                pop  hl
                bit  LEK_GOLD_BIT, c
                ret  z
                inc  a
                ret

;------------------------------------------------------------------------------
; sp_scan — the §9.3 count of CUR_ROOM over slots 1..15: SP_N = active, not
; DYING (PENDING included, as dest_counts), SP_SIG = their Σ weight, SP_NS =
; how many are summon-made. Out: HL = the first free slot (E_FLAGS 0; a freed
; corpse still drawn is fine: sp_init keeps the drawn record), 0 = none.
; Keeps IX.  Clobbers: A, BC, DE, HL.   ~1.3k T
;------------------------------------------------------------------------------
sp_scan:        push ix
                ld   ix, P_ENTITIES + P_ENT_STRIDE
                ld   bc, (P_MAX_ENT - 1) << 8  ; B = slots, C = SP_N
                ld   d, c                      ; D = SP_NS
                ld   e, c                      ; E = SP_SIG
                ld   h, c
                ld   l, c                      ; HL = the free slot
.l:             ld   a, (ix+E_FLAGS)
                or   a
                jr   nz, .o
                ld   a, h
                or   l
                jr   nz, .n
                push ix
                pop  hl
                jr   .n
.o:             and  EF_DYING
                jr   nz, .n
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .n
                inc  c
                bit  RCD_SUMMONED_BIT, (ix+E_RCD)
                jr   z, .w
                inc  d
.w:             ld   a, (ix+E_KIND)
                or   (ix+E_GOLD)
                push bc
                call sp_wt
                pop  bc
                add  a, e
                ld   e, a
.n:             push de
                ld   de, P_ENT_STRIDE
                add  ix, de
                pop  de
                djnz .l
                ld   a, c
                ld   (SP_N), a
                ld   (SP_SIG), de              ; E -> SP_SIG, D -> SP_NS
                pop  ix
                ret
                ASSERT SP_NS == SP_SIG + 1

;------------------------------------------------------------------------------
; sp_fit — after sp_scan: A = kind byte -> CF = the room cannot take it (§9.3:
; SP_N >= ROOM_CAP or SP_SIG + w > LP_SIGMA_CAP; IX = the caster / parent: a K_ARCHMAGE
; one skips the Sigma term).  Clobbers: A, C.
;------------------------------------------------------------------------------
sp_fit:         call sp_wt
                ld   c, a
                ld   a, (ix+E_KIND)            ; user 2026-11-01: the Archmage's own summon is exempt from
                xor  K_ARCHMAGE                ; the Sigma cap (escort 3-6 + 6 + 5 > 12 refused every one):
                jr   nz, .f                    ; IX = the caster / parent; A = 0 here -> SP_SIG := 0
                ld   (SP_SIG), a               ; (ROOM_CAP stays)
.f:             ld   a, (SP_N)
                cp   ROOM_CAP
                ccf
                ret  c
                ld   a, (SP_SIG)
                add  a, c
                cp   LP_SIGMA_CAP + 1
                ccf
                ret

;------------------------------------------------------------------------------
; sp_summon — a caster's summon decision (IX = caster, ACT_SLOT = its slot):
; D = the kind byte to queue (row | SQF_*), E = its live-summon cap, B =
; bodies, C = the cooldown to set (pre-shifted into RCD_SUMMON). S (E_RCD bits
; 2-5) > 0: S - 1, no summon. S = 0: the queue is free, the room holds < E
; summon-made bodies, a free slot and the cap take one more D -> queue {D,
; ACT_SLOT, B}, S := C, the cast pose (KS_ATTACK) with the line "THE <kind>
; SUMMONS!" at its IMPACT (E_MSG, no hit flash). Out: CF = summoned (the turn
; is used). Keeps IX.  Clobbers: A, BC, DE, HL.   S > 0 ~80 T; a try ~1.8k T
;------------------------------------------------------------------------------
sp_summon:      ld   a, (ix+E_RCD)
                and  RCD_SUMMON
                jr   z, .rdy
                ld   a, (ix+E_RCD)
                sub  RCD_S1                    ; (S >= 1: no borrow; CF = 0)
                ld   (ix+E_RCD), a
                ret
.rdy:           ld   a, (SPQ_K)
                or   a
                ret  nz                        ; CF = 0: busy (another producer this turn)
                push bc
                push de
                call sp_scan
                pop  de
                ld   a, (SP_NS)
                cp   e
                jr   nc, .no                   ; its summons are up
                ld   a, h
                or   l
                jr   z, .no                    ; no free slot
                ld   a, d
                call sp_fit
                jr   c, .no
                pop  bc
                ld   hl, SPQ_K
                ld   (hl), d
                inc  l
                ld   a, (ACT_SLOT)
                ld   (hl), a                   ; SPQ_P
                inc  l
                ld   (hl), b                   ; SPQ_N
                ASSERT SPQ_P == SPQ_K + 1 && SPQ_N == SPQ_P + 1 && (SPQ_K & $FF) < $FE
                ld   a, (ix+E_RCD)
                and  ~RCD_SUMMON & $FF
                or   c
                ld   (ix+E_RCD), a
                ld   b, MSG_M_SUMMON
                call rg_pose                   ; (ranged6.asm) the cast / attack pose + the line
                scf
                ret
.no:            pop  bc
                or   a
                ret

;------------------------------------------------------------------------------
; sp_bcall — ai_ranged's caster pre-rule slot for an RWF_PRE row (the Bone
; Caller): sp_summon with a base Skeleton if Skeleton is in LP_KINDS, else a
; base Ghost (game.md §9.4.6), BC_LIVE, 1 body, cooldown BC_CD.
; Out: CF = summoned.  Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
sp_bcall:       ld   hl, LP_KINDS
                ld   bc, 4
                ld   a, K_SKELETON
                cpir
                ld   d, K_SKELETON | SQF_SUMM | SQF_RESP
                jr   z, .k
                ld   d, K_GHOST | SQF_SUMM | SQF_RESP
.k:             ld   e, BC_LIVE
                ld   bc, (1 << 8) | (BC_CD << 2)
                jr   sp_summon
                ASSERT BC_CD < 16 && PH_CD < 16 && (RCD_SUMMON >> 2) == 15

;------------------------------------------------------------------------------
; ph_summon — far6 from ai_guard (bank 7): IX = the lair boss, a Mummy = the
; Golden Pharaoh (D5). sp_summon (cooldown PH_CD, <= PH_LIVE = 1 live minion: user
; 2026-10-30, one at a time; Pharaoh 6 + minion 5 = 11 of 12 never fits a 2nd) with
; a base Skeleton; on a summon one RNG byte: bit 1 = a Mummy instead (both weigh 5:
; the cap test with the Skeleton holds for either).
; Out: L = 1 the turn is used.  Clobbers: all but IX.
;------------------------------------------------------------------------------
ph_summon:      ld   d, K_SKELETON | SQF_SUMM | SQF_RESP
                ld   e, PH_LIVE
                ld   bc, (1 << 8) | (PH_CD << 2)
                call sp_summon
                ld   l, 0
                ret  nc
                call rng_next                  ; (bank 2) A = the byte
                ld   l, 1
                bit  1, a
                ret  z
                ld   a, K_MUMMY | SQF_SUMM | SQF_RESP
                ld   (SPQ_K), a
                ret
                ASSERT WT_K_MUMMY == WT_K_SKELETON

;------------------------------------------------------------------------------
; breed6 — far6 from deal_hit (bank 3), IX = a Rabbit Rat that was hit and
; lives (§9.6): not bred yet (RCD_ONCE), the queue free, 1 in BREED_N (one
; rng_mod draw) -> queue one base Rat beside it (summon-made, F_RESPAWN); the
; once bit is set by sp_run when the Rat is made. Keeps IX.
; Clobbers: A, B, C, E, HL.   ~0.3k T (+ far6)
;------------------------------------------------------------------------------
breed6:         bit  RCD_ONCE_BIT, (ix+E_RCD)
                ret  nz
                ld   a, (SPQ_K)
                or   a
                ret  nz
                ld   c, BREED_N
                call rng_mod                   ; (bank 2)
                or   a
                ret  nz
                call ix_slot                   ; (bank 2; A, E)
                ld   hl, SPQ_P
                ld   (hl), a
                inc  l
                ld   (hl), 1                   ; SPQ_N
                ld   a, K_RAT | SQF_ONCE | SQF_SUMM | SQF_RESP
                ld   (SPQ_K), a
                ret

;------------------------------------------------------------------------------
; sp_run — far6 from end_turn (bank 7) when SPQ_K != 0: empties the queue; no
; spawn when the hero leaves the room this turn (EXIT_KIND) or is dying. Per
; body: the kind (a wave: LP_KINDS[rnd & 3], base row), sp_scan + sp_fit (the
; cap) and a free slot, the parent anchor, sp_init, the spot (sp_place beside
; the parent / sp_door), sp_fin, build_live; a body that fails ends the run.
; Clobbers: all but IY.   ~6-8k T a summon / offspring, ~4k T a wave body
;------------------------------------------------------------------------------
sp_run:         ld   hl, SPQ_K
                ld   a, (hl)
                ld   (hl), 0
                ld   c, a                      ; C = the queued byte
                ld   a, (EXIT_KIND)
                or   a
                ret  nz
                ld   a, (P_ENTITIES + E_FLAGS)
                and  EF_DYING
                ret  nz
                dec  a
                ld   (ACT_SLOT), a             ; $FF: box_free tests every live body (try_player_turn resets it)
                ld   ix, P_ENTITIES            ; (sp_fit's caster: a wave body has no parent = the hero)
.b:             push bc
                ld   a, c
                and  LEK_KIND_MASK
                ld   a, c
                jr   nz, .k
                call rng_next                  ; a wave body: one of the level's kinds
                and  3
                add  a, LP_KINDS & $FF
                ld   l, a
                ld   h, LP_KINDS >> 8
                ld   a, (hl)
                or   SPQ_WAVE
.k:             ld   (SP_KB), a
                call sp_scan
                ld   a, h
                or   l
                jr   z, .x                     ; no free slot
                push hl
                ld   a, (SPQ_P)
                cp   SPQ_NONE
                jr   z, .nd
                call ent_ix                    ; (bank 2; A, E) the parent
                ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_PENDING | EF_DYING
                cp   EF_ACTIVE
                jr   nz, .xp                   ; it died / is hidden
                ld   a, (CUR_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .xp
                call storey_ref                ; (bank 2; A, HL)
                ld   (SP_S), a
                ld   a, (ix+E_X)
                ld   (SP_AX), a
                KFIELD KT_BW
                add  a, (ix+E_X)
                ld   (SP_AR), a
.nd:            ld   a, (SP_KB)
                and  ~SQF_ONCE & $FF           ; (LEK_GOLD's bit: not a golden weight)
                call sp_fit                    ; (after the parent test: IX = the parent)
                jr   c, .xp                    ; the §9.3 cap
.np:            pop  ix                        ; IX = the free slot
                call sp_init
                ld   a, (SPQ_P)
                cp   SPQ_NONE
                jr   z, .dr
                ld   a, (SP_S)
                call sp_y
                call sp_place
                ld   d, 0
                jr   .pl
.dr:            call sp_door
.pl:            jr   c, .x
                call sp_fin
                call build_live                ; (bank 2; keeps IX)
                pop  bc
                ld   hl, SPQ_N
                dec  (hl)
                jp   nz, .b
                ret
.xp:            pop  hl
.x:             pop  bc
                ret
                ASSERT (LP_KINDS >> 8) == ((LP_KINDS + 3) >> 8)

;------------------------------------------------------------------------------
; sp_init — IX = the free slot: bytes 0 .. E_DVIS - 1 and its ST_* bytes
; zeroed (the drawn record E_DVIS.. stays: render erases a corpse still drawn
; there when the new body is classified FULL), E_KIND (SP_KB), E_ROOM.
; Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
sp_init:        push ix
                pop  hl
                ld   d, h
                ld   e, l
                inc  de
                ld   (hl), 0
                ld   bc, E_DVIS - 1
                ldir
                call ix_slot                   ; (bank 2; A, E) A = the slot
                ld   c, a
                ld   h, ST_FLAGS >> 8
                add  a, ST_FLAGS & $FF
                ld   l, a
                ld   (hl), b                   ; (B = 0 after the ldir)
                ld   a, c
                add  a, ST_T1 & $FF
                ld   l, a
                ld   (hl), b
                ld   a, c
                add  a, ST_T2 & $FF
                ld   l, a
                ld   (hl), b
                ld   h, ST_X >> 8
                ld   a, c
                add  a, ST_X & $FF
                ld   l, a
                ld   (hl), b
                ld   a, (SP_KB)
                and  LEK_KIND_MASK
                ld   (ix+E_KIND), a
                ld   a, (CUR_ROOM)
                ld   (ix+E_ROOM), a
                ret
                ASSERT (ST_FLAGS >> 8) == (ST_T1 >> 8) && (ST_T1 >> 8) == (ST_T2 >> 8) && E_DVIS == 24

;------------------------------------------------------------------------------
; sp_y — A = storey, IX = the body (E_KIND set): SP_S, E_Y = SP_Y = 9s + 8 - h
; (walker, standing) / 9s + 1 (flyer, its cruise row).  Clobbers: A, B, C, HL.
;------------------------------------------------------------------------------
sp_y:           ld   (SP_S), a
                ld   c, a
                add  a, a
                add  a, a
                add  a, a
                add  a, c
                ld   c, a                      ; 9s
                KFIELD KT_FLAGS
                and  KF_FLYER
                ld   a, c
                jr   z, .w
                inc  a                         ; flyer: 9s + 1
                jr   .o
.w:             KFIELD KT_BH
                ld   b, a
                ld   a, c
                add  a, STOREY_AIR
                sub  b                         ; walker: 9s + 8 - h
.o:             ld   (SP_Y), a
                ld   (ix+E_Y), a
                ret

;------------------------------------------------------------------------------
; sp_place — IX = the body (E_KIND, E_Y set), SP_AX / SP_AR = the parent's x /
; x + w: the first legal x of d = 0 .. SP_R - 1, the side toward the hero first
; (right: x = SP_AR + d; left: x = SP_AX - w - d). Out: CF = none, else E_X
; set (sp_try).  Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
sp_place:       ld   a, (P_ENTITIES + E_X)
                ld   hl, SP_AX
                cp   (hl)
                sbc  a, a                      ; $FF: the hero is left, left first; 0: right first
                ld   bc, SP_R << 8             ; B = tries, C = d
.d:             ld   d, a
                call .side
                ret  nc
                ld   a, d
                cpl
                call .side
                ret  nc
                ld   a, d
                inc  c
                djnz .d
                scf
                ret
; .side: A = 0 right / $FF left, C = d -> sp_try of that x. Keeps BC, DE.
.side:          push bc
                push de
                or   a
                jr   nz, .lft
                ld   a, (SP_AR)
                add  a, c
                jr   .t
.lft:           KFIELD KT_BW
                add  a, c
                ld   e, a
                ld   a, (SP_AX)
                sub  e                         ; x - w - d (negative: >= $80, sp_try refuses)
.t:             call sp_try
                pop  de
                pop  bc
                ret

;------------------------------------------------------------------------------
; sp_try — A = candidate x (negative: >= $80), IX = the body (E_KIND, E_Y):
; E_X := A; CF = illegal: body cols outside LP_XMIN..LP_XMAX, a live body in
; the box (box_free, ACT_SLOT $FF), a flyer's solid cell (box_solid), a
; walker's floor cell without TF_FLOOR or with a hole / ladder, or its
; standing-row cell solid / a ladder / a plank.
; Clobbers: A, BC, DE, HL.   ~0.3k T + ~0.13k T a live body + walker ~0.3k T a col
;------------------------------------------------------------------------------
sp_try:         ld   (ix+E_X), a
                cp   LP_XMIN
                ret  c
                cp   LP_XMAX + 1               ; x itself too: a negative x ($FF) + width wraps below the
                ccf                            ; end-col test (4 B); CF = x > LP_XMAX
                ret  c
                call get_box                   ; (bank 2) C x, B y, D w, E h
                ld   a, c
                add  a, d
                dec  a
                cp   LP_XMAX + 1
                ccf
                ret  c                         ; runs past the last col
                call box_free                  ; (bank 2; keeps BC, DE) a body there
                ret  c
                KFIELD KT_FLAGS
                and  KF_FLYER
                jp   nz, box_solid             ; (bank 2) CF = a solid cell
                ld   a, b
                add  a, e
                ld   b, a                      ; B = the floor row 9s + 8
.t:             call cell_blocked              ; (bank 2; keeps BC, DE) A = TILE_FLAGS
                and  TF_FLOOR | TF_HOLE | TF_LADDER
                cp   TF_FLOOR
                scf
                ret  nz                        ; no floor / a hole / a ladder end
                dec  b
                call cell_blocked              ; the standing row 9s + 7
                inc  b
                and  TF_SOLID | TF_LADDER | TF_DOOR
                scf
                ret  nz                        ; a wall / block / shaft / plank
                inc  c
                dec  d
                jr   nz, .t
                or   a
                ret

;------------------------------------------------------------------------------
; sp_door — the ALARM wave's arrival (game.md §1.5 / §9.5 idle wave: a door,
; else a ladder end): the room's left door (x = 1), else its right door (x =
; 31 - w), on the door's storey, EF_PENDING | EF_WALKIN (it walks in as a
; follower); no door: the up-exit col on storey 0, else the down-exit col on
; storey 1, EF_PENDING. Every body of the wave takes the same spot: materialise
; pops / walks each in once its box is free. Out: NC, E_X / E_Y set, D = the
; extra E_FLAGS.  Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
sp_door:        call cur_room_desc             ; (bank 2) HL, L low nibble = 0
                inc  l
                ld   a, (hl)                   ; RD_EXITS
                ld   c, a
                ld   e, 1
                rra
                jr   c, .h                     ; RDX_L
                rra
                jr   nc, .v
                srl  c                         ; RDX_R: its storey bit RDX_RS1 -> bit 4
                ld   e, 0
.h:             xor  a
                bit  4, c                      ; RDX_LS1
                jr   z, $+3
                inc  a
                ld   d, EF_PENDING | EF_WALKIN
                jr   .s
.v:             inc  l
                ld   a, (hl)                   ; RD_UPCOL (storey 0)
                ld   e, a
                or   a
                ld   a, 0
                jr   nz, .vs
                inc  l
                ld   e, (hl)                   ; RD_DNCOL (storey 1)
                inc  a
.vs:            ld   d, EF_PENDING
.s:             push de
                call sp_y
                pop  de
                ld   a, e
                or   a
                jr   nz, .x
                KFIELD KT_BW                   ; the right door: 31 - w
                cpl
                add  a, ROOM_COLS
.x:             ld   (ix+E_X), a
                or   a
                ret
                ASSERT RD_EXITS == 1 && RD_UPCOL == 2 && RD_DNCOL == 3 && RDX_L == 1 && RDX_R == 2
                ASSERT RDX_LS1 == $10 && RDX_RS1 == $20 && ROOM_COLS == 32

;------------------------------------------------------------------------------
; sp_fin — IX = the placed body, D = extra E_FLAGS (EF_PENDING / EF_WALKIN):
; E_FLAGS = ACTIVE | HOSTILE | F_RESPAWN (SQF_RESP) | D, facing the hero;
; RCD_SUMMONED from SQF_SUMM; hp = max hp = kind_hp (depth-scaled base row,
; §9.4.3); px / py snapped (E_MODE M_REST from sp_init). SQF_ONCE: the parent
; (SPQ_P) gets RCD_ONCE (the Rabbit Rat bred).  Clobbers: A, BC, HL.
;------------------------------------------------------------------------------
sp_fin:         ld   a, (SP_KB)
                ld   c, a
                and  SQF_SUMM
                ld   (ix+E_RCD), a             ; RCD_SUMMONED (the counters 0)
                ld   a, c
                and  SQF_RESP
                or   d
                or   EF_ACTIVE | EF_HOSTILE
                ld   b, a
                ld   a, (P_ENTITIES + E_X)
                cp   (ix+E_X)
                jr   nc, .f
                set  EF_LEFT_BIT, b            ; the hero is left of it: face left
.f:             ld   (ix+E_FLAGS), b
                ld   a, (ix+E_KIND)
                call kind_hp                   ; (tier6.asm; C, HL)
                ld   (ix+E_HP), a
                ld   (ix+E_MAXHP), a
                call snap_pxpy                 ; (bank 2)
                ld   a, (SP_KB)
                and  SQF_ONCE
                ret  z
                push ix
                ld   a, (SPQ_P)
                call ent_ix
                set  RCD_ONCE_BIT, (ix+E_RCD)
                pop  ix
                ret
                ASSERT SQF_SUMM == RCD_SUMMONED && SQF_RESP == EF_RESPAWN && SQF_ONCE == LEK_GOLD && M_REST == 0
