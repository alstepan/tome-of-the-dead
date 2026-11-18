;------------------------------------------------------------------------------
; perch1 — GARG-PASS (new_monsters.md §4.1, user 2026-11-18; was R6 perch6, NEW-MON3 T10a G-1): far1 from
; bank-3 afl_perch, the own turn of a Gargoyle whose RCD_AWAKE is clear (IX; ACT_SLOT = its slot, the
; status step and the slow gate passed). Bank-1 rules (ui1.asm): bank-2 / low-RAM helpers only.
;  1. solid (no EF_GHOST): a door arrival (ALARM wave / trickle: materialise cleared PENDING | WALKIN) ->
;     RCD_AWAKE, the turn spent (rule 4: no statue at the door; anim already shows the fly pose);
;  2. a ghost whose box any body (the hero or a monster: box_free, ACT_SLOT = me, ghosts / corpses
;     skipped) overlaps -> waits (rule 2: the wake is delayed until the box is clear);
;  3. the hero standing (not mid-ladder) on its storey (storey_ref vs PL_STOREY) at a box gap <= PERCH_GAP
;     -> wakes: EF_GHOST off + RCD_AWAKE (it collides from now on, this phase too), faces
;     him, "THE GARGOYLE WAKES UP." (MSG_M_WAKE, 0 new text), the WAKING pose (its KS_CLIMB one-shot)
;     and the turn is spent: the hero always gets >= 1 turn after it becomes solid;
;  4. else waits (the statue pose: anim's KS_CLIMBREST fid while EF_GHOST).
; No damage reaches a ghost (box_free / find_target / pf_cands / jump_bodies / act_here skip it).
; Clobbers: all but IX.  A waiting turn ~0.9k T (far1 incl.); a wake + its line ~2.5k.
;------------------------------------------------------------------------------
                ; GARG-PASS review: the gap math below assumes "horizontal overlap => box overlap" on one
                ; storey (step 2 refused an overlap, so the hero-left gap never goes negative = ~254, "never
                ; wakes"): the standing hero (rows 9s+8-h .. 9s+7) always meets the statue's rows 9s+1 ..
                ; 9s+GP. Pinned here: both heroes 6 rows, the Gargoyle 4 at the flyer cruise row 9s + 1.
                ASSERT BH_K_KNIGHT == BH_K_WIZARD && 1 + BH_K_GARGOYLE > STOREY_AIR - BH_K_KNIGHT && 1 < STOREY_AIR
perch1:         bit  EF_GHOST_BIT, (ix+E_FLAGS)
                jr   nz, .gh
                set  RCD_AWAKE_BIT, (ix+E_RCD)  ; 1. a solid arrival: awake from its first turn
                ret
.gh:            call get_box                   ; (bank 2) C x, B y, D w, E h
                call box_free                  ; (bank 2) 2. CF = a body overlaps the statue
                ret  c
                ld   a, (PEND_N)               ; ... or a PENDING one (a squeezed body / a door arrival): only when the room has any
                or   a                         ; (pend_hit's own fast path; the .go entry skips it: ~1.1k T a statue a pass saved)
                call nz, gh_pend              ; (R4 sv_r4.asm: pend_hit.go with a "current box" no body meets; keeps BC, DE, IX; CF out)
                ret  c                         ; (+1 B vs the direct call)
                jp   stir_gate                 ; GARG-CHAIN (low RAM, garg_l.asm): the armed chain wakes me (jp .wk); else the hero
                                               ; mid-ladder leaves it perched (ret nz), or it comes back to .st (-2 B here)
.st:            call storey_ref                ; (bank 2; A, HL)
                ld   hl, PL_STOREY
                cp   (hl)
                ret  nz                        ; the other storey: never
                ld   hl, PL_X                  ; (get_box's C x / D w survive box_free / storey_ref)
                ld   a, c
                add  a, d
                ld   b, a                      ; x + w
                ld   a, (hl)
                ld   e, 1                      ; E = the facing (+1 right / $FF left)
                sub  b                         ; hero right: gap = px - (x + w)
                jr   nc, .g
                ld   a, (hl)
                ld   l, PL_W & $FF
                add  a, (hl)
                ld   b, a
                ld   e, $FF
                ld   a, c
                sub  b                         ; hero left: gap = x - (px + pw) (never < 0: step 2 refused
                                               ; an overlap; perch6's jr c, .wk is gone)
.g:             cp   PERCH_GAP + 1
                ret  nc                        ; too far: stays perched
.wk:            res  EF_GHOST_BIT, (ix+E_FLAGS) ; 3. solid from now on (it stays in LIVE_LIST: box_free reads
                set  RCD_AWAKE_BIT, (ix+E_RCD)  ; the flag live, so it collides at once: no build_live)
                call stir_arm                  ; GARG-CHAIN: arm the room's chain (+ "THE STATUES STIR!" with a joiner); keeps E, IX
                ld   a, e
                call face_a                    ; (bank 2)
                ld   b, MSG_M_WAKE
                ld   c, (ix+E_KIND)
                call impact_line               ; (low RAM: pages the text, restore_page = bank 1) "THE GARGOYLE WAKES UP."
                call kind_seq_ptr              ; (bank 2) the waking one-shot = KS_CLIMB (the row: one page)
                ld   a, l
                add  a, KS_CLIMB
                ld   l, a
                ld   a, (hl)
                inc  hl
                ld   h, (hl)
                ld   l, a
                jp   start_seq                 ; (bank 2)
                ASSERT (PL_X >> 8) == (PL_W >> 8) && (seq_rows >> 8) == ((seq_rows + SQ_ROWS_LEN - 1) >> 8)
