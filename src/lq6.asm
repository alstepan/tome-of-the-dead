;==============================================================================
; lq6.asm — AI-L1 ladder queue (game.md §9.2 'Ladder queue', user 2026-10-29:
; STRONGEST FIRST), R6. One far6 entry, lq_block, from turn3.asm ai_monster
; .seek when a climber's standing step toward its shaft col failed.
;
; J2 (two seekers reaching for col from opposite sides blocked each other one
; cell short for ever): the seeker finds the body in its way (box_free over
; the failed step's box; the first LIVE_LIST hit). The blocker WINS when its
; power (static kind_tab KT_HP of its kind: not current hp, which would
; reorder the queue mid-fight) is higher, or equal and its slot is lower.
; - winner blocks me and my box overlaps the near-end box (|x - col| < 3):
;   I step 1 cell AWAY from col, still facing the shaft (try_step, no
;   face: it reads as backing off; blocked -> wait);
; - a body on my side in the near-end box but not at col (it may have to
;   back off into me): step 1 cell away whatever its power or my distance
;   (review: a 3-climber chain, the middle one boxed in by two winners,
;   else waits for ever);
; - otherwise (I win, or I am not on the near-end box): wait facing the
;   shaft (no pacing: pacing re-collides). A winner blocked
;   by a loser just waits; the loser clears on its own turn.
; Not a body (terrain / door / pit / cork / a PENDING body): plain wait, as
; before AI-L1 (no facing change: A/B-identical without contention).
; The shaft itself stays the queue (.at: one climber per segment).
;
; In: IX = the seeker (standing walker, ACT_SLOT = its slot: B5 contract),
;     D = dx toward col (+1 / -1), E = col.   No result.
; Clobbers: all but IX (far6 loses A, F anyway).
; Cost: ~0.35k T + a step-away try_step (~0.4k T), only on a blocked seek step.
;==============================================================================
LQ_HOLD         EQU $80
lq_block:
                push de
                call get_box                   ; C = x, B = y, D = w, E = h
                pop  hl                        ; H = dx, L = col
                push hl
                ld   a, c
                add  a, h
                ld   c, a                      ; the failed step's box
                call box_free                  ; CF: a body, HL = its LIVE_LIST entry + 4
                pop  de                        ; D = dx, E = col (flags kept)
                ret  nc                        ; no body in the way: wait, as before
                call face_dx                   ; waiting faces the shaft (A only)
                ASSERT LL_STRIDE == 5 && E_KIND == 0
                dec  hl
                dec  hl
                ld   b, (hl)
                dec  hl
                ld   c, (hl)                   ; BC = its entity (the hero too: KT_HP 24 / 16,
                                               ; and it never blocks a seek step off its path)
                ld   hl, E_X                   ; review: a body on my side, in the near-end
                add  hl, bc                    ; box but not yet at col, may have to back off
                ld   a, (hl)                   ; into me: I back off first whatever the power
                sub  e                         ; or my distance, so a 3-climber chain unwinds
                bit  7, d                      ; (col c: Orc c-2, Necro c+1, Orc c+4 stuck for
                jr   z, .sgn                   ; ever: the Necro, between two winners, had
                neg                            ; nowhere to go). dx * (its x - col) in -2..-1
.sgn:           push af                        ; W = the wider of the two bodies (3; 4 with a Spider:
                call .w                        ; it needs col .. col + 3 free). On my side,
                dec  a                         ; 0 < |its x - col| < W <=> rel + W - 1 < W - 1
                ld   l, a                      ; (unsigned). Farther out it never backs off (no
                pop  af                        ; pacing behind a mere waiter); at col: power rule
                add  a, l
                cp   l
                jr   c, .back
.pow:           KFIELD KT_HP                   ; A = my power, H = the KT_HP page
                push af
                ld   a, (bc)                   ; its kind
                add  a, KT_HP & $FF
                ld   l, a                      ; (hl) = its power
                pop  af
                cp   (hl)
                jr   c, .away                  ; it is stronger
                ret  nz                        ; I am: wait, it backs off on its turn
                push ix                        ; tie: the lower slot wins; slot order =
                pop  hl                        ; address order (P_ENTITIES + 32 x slot)
                sbc  hl, bc                    ; (CF = 0 from cp: equal) CF iff I am lower
                ret  c                         ; I win
.away:          call .w                        ; |x - col| < W: my box overlaps the near-end box
                ld   l, a                      ; (W as above)
                ld   a, (ix+E_X)
                sub  e
                jr   nc, .abs
                neg
.abs:           cp   l
                ret  nc                        ; clear of it: wait
.back:          ld   (ix+E_AIDIR), LQ_HOLD     ; scratch/lq-hold: hold the next seek turn (turn3 .sk)
                ld   a, d
                neg
                ld   d, a
                ld   e, 0
                jp   try_step                  ; 1 cell away (facing kept); blocked -> wait
; .w — A = max(my KT_BW, the blocker's KT_BW) (fix/spider-climb: FEAT_W except around the 4-wide
; Spider / Black Widow). In: IX = me, BC = the blocker's entity (E_KIND = +0). Clobbers: HL, A.
.w:             KFIELD KT_BW
                push af
                ld   a, (bc)
                add  a, KT_BW & $FF
                ld   l, a
                pop  af
                cp   (hl)
                ret  nc
                ld   a, (hl)
                ret
