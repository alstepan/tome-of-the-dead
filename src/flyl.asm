;==============================================================================
; flyl.asm — FLY-CUT (game.md §9.2 "FLY-CUT"; docs/memory-map.md "FLY-CUT ledger"). Low-RAM cold
; block (bank 5: callable with any bank at $C000; bank 3 had 22 B, bank 7 8 B; the head is in HOT_COPY:
; the low-RAM spare is the tests' stub window).
;
; fly_cut / fly_cut2 — bank-3 ai_flyer (head fly_cut in HOT_COPY, panel_hot.asm; the rest here), after its attack / ranged hooks. A flyer is held to its storey band
;   (game.md §2.1), so an L2 mid-room block (solid storey-0 rows 0..7) cuts storey 0 for it while
;   the hero stands in the other half (AI-SEEK2 Q3: it hovered at the face for ever). The detour uses
;   the walkers' segments (ai_seek2.md §2.1, ROOM_CUT = FLY_CUT = b - 1 in a block room) and seek_col's
;   ladder pick: from a storey-0 half, the internal ladder in its own half, DOWN its shaft hole; from
;   storey 1, the ladder whose top is the hero's half, UP. Every flyer is FEAT_W (3 cols) wide: it fits
;   a {c,1} shaft (HOLE_* / LAD_* cells are not TF_SOLID; try_step's box_solid / box_free / cork_check
;   still bind it). Only when the hero's target segment PL_SEG is a storey-0 half other than the
;   flyer's: a hero on (or heading to) storey 1 leaves the storey-0 flyer on its old rules, and pits or
;   plain rooms (FLY_CUT = $FF) never detour. Stateless: (FLY_CUT, PL_SEG, the flyer's box) only, no RNG.
;   seek_col cannot answer STRANDED here: a block room owns a ladder in each half (larger_depths.md I4).
; In: IX = the flyer, TMP4 = its storey s (storey_ref).
; Out: CF = 1: no detour (A / D / E undefined). CF = 0: detour, E = the shaft dy (1 down from storey
;   0, $FF up from storey 1); Z = at the ladder col (straight through the hole), else D = dx toward it
;   (ai_flyer's .dy adds the cruise / band dy).  Clobbers: A, BC, DE, HL.
; ~60 T without a mid-block (the HOT_COPY head); with one ~0.9k (seek_col + far7, bank 7 contended)
;==============================================================================
fly_cut2:       ld   a, (PL_SEG)               ; D = M (fly_cut, HOT_COPY panel_hot.asm)
                cp   d
                scf
                ret  z                         ; same segment: the old rules
                rla
                ret  c                         ; H = storey 1: the old rules
                ld   hl, seek_col              ; bank 7 (seek7.asm): L = the ladder col, D = M in
                call far7                      ; (far7 loses F)
                ld   a, (TMP4)
                add  a, a
                neg
                inc  a
                ld   e, a                      ; E = 1 - 2s: the shaft dy, up ($FF) from storey 1, else down
                ld   a, l                      ; A = the col
                call dx_to_a                   ; bank 3 (turn3.asm): paged, fly_cut2 runs only under ai_flyer
                ld   a, d                      ; and far7 gave bank 3 back. D = dx
                or   a                         ; CF = 0: detour; Z = at the col
                ret
