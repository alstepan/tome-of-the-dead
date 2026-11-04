;==============================================================================
; vbat6.asm — 3F-T9 the Vampire's bat form (game.md §9.2 "Vampire"), R6
; (r6.asm rules: far6 only, no SMC, no bank-3 code or data). docs/memory-map.md
; "3F-T9 Vampire bat form".
;
; The bat form is a kind row of its own, K_VBAT (id 2, the retired Rogue's
; hole): the Bat's body / flags / 1d2 bite / every-turn cadence, so ai_flyer,
; try_step, render and the hit path need nothing new; the row carries the
; Vampire's hp row, resistances, KXP, weight, name and ink. A transform rewrites
; E_KIND (+ E_Y on a revert); hp, statuses, E_GOLD and E_RCD stay. The golden
; Vampire Lord keeps its boss identity by LP_BOSS following its kind (kind |
; E_GOLD == LP_BOSS everywhere: guard, drop, grate, PROVOKED, never follows).
;
; Decided and applied at end_turn only (bank-7 vb_turn, after sp_run, picks
; the bodies; R6 vb_one decides and makes the change): never in the
; cast / input tick. "Costs its whole turn": a humanoid turns into a bat only
; at the end of its rest turn (odd TURN_COUNTER: "acts every 2" rests then, so
; it did nothing this turn) and a bat reverts only at the end of an even turn
; (the humanoid then rests on the next, odd, turn).
;   humanoid, odd turn, the hero on its storey (rule 1 before rule 2):
;     1. flee: not RCD_ONCE and 3 hp <= max hp + 2 (hp <= 1/3 max, 5 of 14)
;        -> bat, RCD_ONCE | RCD_VFLEE, FEAR VB_FLEE_T turns (mon_status: a
;        step away from the hero each turn; cornered it bites);
;     2. close distance: 1 <= gap <= VB_GAP and (gap >= VB_FAR: open floor too, or a cut
;        between: vb_cut, a pit col in the floor row 9s+8 or a solid cell in the standing
;        row 9s+7) -> bat (ai_flyer flies over it at the hero). Its line prints only the
;        first time per body (RCD_VSEEN); the flee transform always prints.
;     The hero on the OTHER storey: neither (open: a flyer cannot leave its
;     storey band, ai_flyer / clamp_band; see memory-map "3F-T9 Vampire bat form").
;   bat, even turn: revert when (RCD_VFLEE: its FEAR is over) / (else: the
;     hero on another storey / on its storey, gap <= VB_NEAR (hysteresis vs VB_FAR), no cut between) and the humanoid box
;     at its x is legal (spawn6.asm sp_try: standing floor, no wall / shaft /
;     plank, no body; else it stays a bat and retries next even turn).
; Every transform: M_REST, px / py snapped, LP_BOSS (golden), build_live
; (LIVE_LIST caches the body box). Turning into a bat prints
; "THE VAMPIRE TURNS INTO A BAT!" (close distance: once per body); the revert is silent.
;==============================================================================

;------------------------------------------------------------------------------
; vb_one — far6 from bank-7 vb_turn (end_turn; bank7.asm), which picked the
; body and prepared: IX = a Vampire at the end of an odd turn / a bat form at
; the end of an even one (CUR_ROOM, active, not held), ACT_SLOT = its slot
; (box_free skips it), PL_* = cache_player, VB_S = its storey. The rules of
; the header.  Clobbers: A, BC, DE, HL (IX kept).   ~0.5-1.5k T, + a transform
;------------------------------------------------------------------------------
vb_one:         ld   a, (ix+E_KIND)
                cp   K_VBAT
                jr   z, .bat
                call vb_gap
                ret  c                         ; the hero on another storey
                ld   d, a                      ; D = gap, C = the first gap col
                call is_standing               ; VAMP-BOSS: a climbing Vampire keeps its form (the 3x2 bat box
                ret  nz                        ; would drop it off the ladder); on_ladder minus the flyer test
                                               ; (a humanoid here); bank 2, clobbers A, HL (keeps C, D)
                bit  RCD_ONCE_BIT, (ix+E_RCD)
                jr   nz, .close                ; fled once already
                ld   a, (ix+E_HP)
                dec  a
                ld   e, a
                add  a, a
                add  a, e                      ; 3 (hp - 1) (golden max <= 2 x 21 + 6: no overflow)
                cp   (ix+E_MAXHP)              ; flee iff 3 hp <= max + 2  <=>  3 (hp - 1) < max
                jr   nc, .close                ; hp > 1/3 max (rounded: 5 of 14 flees)
                ; 1. flee
                ld   a, (ix+E_RCD)
                or   RCD_ONCE | RCD_VFLEE
                ld   (ix+E_RCD), a
                call vb_st
                ld   a, (hl)                   ; MIND := FEAR (a CONFUSED is replaced)
                and  ~STS_MIND & $FF
                or   MIND_FEAR
                ld   (hl), a
                ld   a, l
                add  a, (ST_T1 - ST_FLAGS) & $FF
                ld   l, a
                ld   a, (hl)
                and  $F0                       ; the HOLD nibble stays (0: not held)
                or   VB_FLEE_T
                ld   (hl), a
                cp   a                         ; Z: the flee transform always logs its line
                jr   vb_bat
.bat:           bit  RCD_VFLEE_BIT, (ix+E_RCD)
                jr   z, .near
                call vb_st
                ld   a, (hl)
                and  STS_MIND
                cp   MIND_FEAR
                ret  z                         ; still fleeing
                jr   .rv
.near:          call vb_gap
                jr   c, .rv                    ; the hero on another storey: a flyer cannot follow, back to the humanoid
                cp   VB_NEAR + 1
                ret  nc
                ld   d, a
                call vb_cut                    ; (gap 0: no col between, NC)
                ret  c                         ; still a cut between: it stays a bat
.rv:            ld   (ix+E_KIND), K_VAMPIRE    ; the humanoid box at its x, standing
                ld   a, (ix+E_Y)
                push af
                ld   a, (VB_S)
                call sp_y                      ; (spawn6.asm) E_Y = 9s + 8 - h
                ld   a, (ix+E_X)
                call sp_try                    ; (spawn6.asm) CF = illegal (box_free skips ACT_SLOT)
                pop  hl                        ; H = the bat's y (flags kept)
                jr   nc, .ok
                ld   (ix+E_Y), h
                ld   (ix+E_KIND), K_VBAT
                ret
.ok:            res  RCD_VFLEE_BIT, (ix+E_RCD)
                jr   vb_fin

;------------------------------------------------------------------------------
; vb_bat — IX = a humanoid Vampire: the bat form, same x and top row (the 3x2
; box lies inside the 3x6 one: no legality test), the line. vb_fin — both
; directions: M_REST, px / py snapped, the golden Lord's LP_BOSS := its kind |
; LEK_GOLD, build_live, the slot hidden for the next render (R_VIS 0, below).
; Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
.close:         ; 2. close distance: gap 1 .. VB_GAP and (gap >= VB_FAR: the open floor, or a cut
                ; between: a pit / a block it cannot cross). The line only on the first one.
                ld   a, d
                cp   VB_GAP + 1
                ret  nc
                cp   VB_FAR
                jr   nc, .go
                call vb_cut                    ; (gap 0: touching, NC: it bites)
                ret  nc                        ; gap < VB_FAR and no cut: it walks
.go:            bit  RCD_VSEEN_BIT, (ix+E_RCD) ; Z = not logged yet; set / ld keep the flags
                set  RCD_VSEEN_BIT, (ix+E_RCD)
vb_bat:         ld   (ix+E_KIND), K_VBAT      ; (ld keeps Z)
                ld   a, TX_VB_TURNS
                call z, msg_push               ; (low RAM; any bank)
                ; fix/vamp-corruption: RENDER_FIRST renders the next tick BEFORE anim_tick,
                ; i.e. with this tick's R_FID = a frame of the OLD kind placed by the NEW
                ; kind's KT_BH (fpy = py + 8 bh - H): a 48-px Vampire frame on the 2-row
                ; bat box at y 2 gave fpy = -16 -> R_ROW 30 -> blit / erase_rect into the
                ; attributes and the bank-5 RAM above them ($5Bxx..$5Fxx). R_VIS 0: that
                ; render only erases the drawn sprite; anim_tick then sets the new frame
                ; (one tick blank).  12 B, ~60 T a transform
vb_fin:         ld   a, (ACT_SLOT)
                rrca
                rrca
                rrca
                rrca                           ; slot * 16 (slot < 16)
                ld   l, a
                ld   h, SLOTREC >> 8
                ld   (hl), 0                   ; R_VIS := hidden
                ld   (ix+E_MODE), M_REST       ; no sequence of the other kind runs on (start_seq
                call snap_pxpy                 ; zeroes E_TMR; .walkph re-locks E_WPH to px)
                ld   a, (ix+E_GOLD)
                or   a
                jr   z, .b
                or   (ix+E_KIND)
                ld   (LP_BOSS), a
.b:             jp   build_live                ; (bank 2; keeps IX)
                ASSERT M_REST == 0 && BH_K_BAT <= BH_K_VAMPIRE && BH_K_VAMPIRE == 6
                ASSERT R_VIS == 0 && (SLOTREC & $FF) == 0 && SLOTREC_STRIDE == 16 && P_MAX_ENT == 16
                ASSERT VB_FLEE_T <= STS_MAX_TURNS && (ST_FLAGS >> 8) == (ST_T1 >> 8)

; vb_st — HL = ST_FLAGS of ACT_SLOT.  Clobbers: A
vb_st:          ld   a, (ACT_SLOT)
                add  a, ST_FLAGS & $FF
                ld   l, a
                ld   h, ST_FLAGS >> 8
                ret

;------------------------------------------------------------------------------
; vb_gap — IX = the body, VB_S = its storey, PL_* cached: CF = the hero on
; another storey; else NC, A = the box gap in cols (0: touching or overlapping,
; a bat above the hero), C = the first gap col. Both bodies are 3 cols wide
; (ASSERTed: the heroes, the Vampire, its bat form): gap = |dx| - 3, first =
; min(x, px) + 3 (18 B less than ranged6's general box gap).  Clobbers: A, C, HL.
;------------------------------------------------------------------------------
vb_gap:         ld   a, (VB_S)
                ld   hl, PL_STOREY
                cp   (hl)
                scf
                ret  nz
                ld   a, (PL_X)
                ld   c, a
                ld   a, (ix+E_X)
                sub  c                         ; x - px
                jr   nc, .g                    ; the hero left (C = px)
                ld   c, (ix+E_X)               ; the hero right (C = x)
                neg
.g:             inc  c
                inc  c
                inc  c                         ; C = min + 3
                sub  3
                ret  nc
                xor  a                         ; overlapping: 0 (NC)
                ret
                ASSERT {b kind_tab + KT_BW + K_KNIGHT} == 3 && {b kind_tab + KT_BW + K_WIZARD} == 3
                ASSERT {b kind_tab + KT_BW + K_VAMPIRE} == 3 && {b kind_tab + KT_BW + K_VBAT} == 3

;------------------------------------------------------------------------------
; vb_cut — C = the first gap col, D = gap cols (>= 1), VB_S = the storey s:
; CF = a cut between (game.md §9.2 RANGED-SPEC "close distance"): a col of
; the floor row 9s+8 with neither TF_FLOOR nor TF_LADDER (a narrow / wide
; pit; a ladder top is walkable), or a TF_SOLID cell in the standing row
; 9s+7 (a mid-room block: ranged6.asm rg_scan).
; D = 0: NC.  Clobbers: A, B, C, E, HL (D kept).   ~0.3k T + ~0.2k T a col
;------------------------------------------------------------------------------
vb_cut:         ld   a, d
                or   a
                ret  z                         ; gap 0: nothing between (NC)
                ld   a, (VB_S)
                MUL_STOREY b
                add  a, STOREY_AIR
                ld   b, a                      ; B = 9s + 8
                ld   e, d                      ; E = the col counter (cell_blocked keeps DE)
.p:             call cell_blocked              ; (bank 2; keeps BC, DE) A = TILE_FLAGS
                and  TF_FLOOR | TF_LADDER
                jr   z, .c                     ; a pit col (CF = 0 from the and)
                inc  c
                dec  e
                jr   nz, .p
                ld   a, c
                sub  d
                ld   c, a                      ; C back to the first gap col (D kept)
                dec  b                         ; the standing row 9s + 7
                jp   rg_scan                   ; (ranged6.asm) CF = a solid cell
.c:             scf
                ret
                ASSERT STOREY_AIR == 8
