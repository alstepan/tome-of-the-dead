;==============================================================================
; pool6.asm — 3F-T1 the per-level sprite pool's kind list (R6; r6.asm rules:
; far6 only, results in memory, no SMC). docs/memory-map.md "Level pool".
;
; level_enter (lowram.asm) rewinds the pool to the LEVEL mark (above the
; select idles + the hero + its class FX, start_game's alloc_mark), sets every
; monster frame's FRT row to NONE, far6 pool_list, then gen_kind's each entry
; of PL_LIST. A generation kind is a kind_tab row whose [KT_FID0, +KT_FCNT)
; range is generated (only the generator reads those two columns).
;
; GENERATION-KIND MAP (pool_gmap; the contract T2 builds on): records
;   DB kind, g1, g2         g2 = PG_NONE: no second unit
; A kind with a record generates g1 (+ g2) INSTEAD of its own range; a kind
; without one generates its own range. Shared / tier rows map to their base
; frames' unit (Vampire / Archmage -> the Necro unit, a Giant Rat tier -> Rat),
; a row needing two units lists both (Archer -> the Skeleton-walk unit + its
; SHOOT unit; Necro -> its body + the bolt unit). Units must not overlap
; (dedup is per kind: an overlapping fid would be generated twice). Records
; are read in order, the first match wins. Today every 3F kind is a stand-in
; ALIAS of an original kind id (defs.asm K_SPIDER = K_RAT, ...), so the map
; is empty. The build-time need (main.asm "LEVEL POOL NEED") reads these
; bytes too, so the map and POOL_NEED cannot drift.
;==============================================================================
PG_NONE         EQU $FF
PL_LIST         EQU GEN_SRC            ; pblit's staging bytes (< 54, below the FI glyph cache):
PL_CAP          EQU 12                 ; free in level_enter between level_new and panel_init
LP_GEN_N        EQU 5                  ; LP_KINDS[0..3] + LP_BOSS (not the LP scratch: lp.py
                                       ; B0G reads LP_HX.. after a new game)
                ASSERT LP_BOSS == LP_KINDS + 4 && PL_LIST + PL_CAP <= GEN_SRC + 54 && FI_PAD >= GEN_SRC + 54
                ASSERT 2 * LP_GEN_N + 1 <= PL_CAP   ; <= 2 units per kind + the $FF end

;------------------------------------------------------------------------------
; pool_list — far6 from level_enter: PL_LIST := the generation kinds of
; LP_KINDS[0..3] + LP_BOSS (pool_map), each once, in first-seen order, $FF
; terminated (<= 10 + 1 B).   Clobbers: A, BC, DE, HL.   ~2k T
;------------------------------------------------------------------------------
pool_list:
                ld   hl, PL_LIST
                ld   (hl), PG_NONE             ; empty list
                ld   de, LP_KINDS
                ld   b, LP_GEN_N
.k:             ld   a, (de)
                push de
                push bc
                call pool_map                  ; B = g1, C = g2
                ld   a, b
                call pl_add
                ld   a, c
                call pl_add
                pop  bc
                pop  de
                inc  de
                djnz .k
                ret

; pool_map — A = kind -> B = g1, C = g2 (PG_NONE) per pool_gmap (no record:
; B = the kind itself).   Clobbers: F, HL.
pool_map:
                ld   b, a
                ld   c, PG_NONE
                ld   hl, pool_gmap
.s:             bit  7, (hl)                   ; PG_NONE: end of the map
                ret  nz
                cp   (hl)
                inc  hl
                jr   z, .hit
                inc  hl
                inc  hl
                jr   .s
.hit:           ld   b, (hl)
                inc  hl
                ld   c, (hl)
                ret

; pl_add — A = generation kind (PG_NONE: none): append it to PL_LIST unless
; already listed. Keeps BC, DE.   Clobbers: A, F, HL.
pl_add:
                inc  a
                ret  z
                dec  a
                ld   hl, PL_LIST
.c:             cp   (hl)
                ret  z                         ; listed already
                bit  7, (hl)                   ; the $FF end?
                inc  hl
                jr   z, .c
                dec  hl
                ld   (hl), a                   ; over the old end
                inc  hl
                ld   (hl), PG_NONE
                ret

; pool_gmap — the generation-kind map (see the header). Kinds < $80.
pool_gmap:
                DB   PG_NONE                   ; (empty: every 3F kind is an alias today)
pool_gmap_end:
PGMAP_N         EQU (pool_gmap_end - pool_gmap - 1) / 3
                ASSERT pool_gmap_end - pool_gmap == 3 * PGMAP_N + 1
