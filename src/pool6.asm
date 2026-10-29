;==============================================================================
; pool6.asm — the sprite pool's per-session generation lists + the sequence
; cache (R6; r6.asm rules: far6 only, results in memory, no SMC).
; docs/memory-map.md "Level pool (3F-T1)" / "Sequence cache (3F-T2)".
;
; Three far6 entries, each writing PL_LIST (pairs DB fid0, fcnt; $FF end) for
; lowram gen_list and loading the matching kind sequence blocks into the bank-2
; cache (seq_rows / seq_bytes, kind_tab KT_SEQ):
;   pool_hero   start_game, after gen_idles: the hero + its class FX kind; seq
;               slot 0 = the hero; every FX FRT row except the hero's class
;               FX := NONE (3F-T2: the other class's rows never go stale)
;   pool_proto  start_game, PROTO rooms: the original monster kinds
;               K_SKELETON .. K_PROTO_END - 1, seq slots 1..6
;   pool_list   level_enter, after alloc_restore: monster FRT rows := NONE,
;               the FX rows outside the hero's class FX := NONE (stale extras
;               of the previous level), LP_KINDS[0..3] + LP_BOSS through
;               pool_gmap + the hero-dependent extras (pool_xmap); seq slots 1..
;
; GENERATION UNITS (gu_tab, 3F-T2; was kind_tab KT_FID0 / KT_FCNT): DB fid0,
; fcnt per unit. Units 0..K_MAX-1 = the kinds' own ranges (0 frames: none);
; units >= K_MAX = extra ranges with no kind (3F-T13: the Skeleton halves, the
; shared DEADs, the Necro bolt, the Mage's arrows / daggers). Units that can
; meet on one level must not overlap (dedup is per unit, by fid0: an overlap
; would be generated twice); a frame set shared by kinds is ONE unit id.
;
; GENERATION MAP (pool_gmap; 3F-T13: EVERY matching record applies, was the
; first): records DB kind, u1, u2 (u2 = PG_NONE: none); a kind with records
; generates their units INSTEAD of its own unit (Skeleton = U_SKARCH +
; U_SKCLIMB + U_SKREST, Archer = U_SKARCH + U_SKCLIMB + U_DEADH, Vampire / Archmage = the Necro's,
; Necro = its own + U_DEADH + U_NBOLT: two records). Tier rows are never in
; LP_KINDS / LP_BOSS (spawns take the base's frames, game.md §9.6), so they
; need no record; their gu_tab row names the base's own unit (documentation).
; HERO EXTRAS (pool_xmap, 3F-T2): records DB kind, hero kind, unit: on a level
; listing the kind, a game of that hero also generates the unit (game.md 3F:
; the Mage's arrow_fly1/2 on Archer levels D4 / D5 / D7, dagger_spin1/2 on the
; Goblin's D1 / D2 for the Slinger's rock). An extra unit must lie outside that
; hero's class FX unit (it is NONE'd at the next level entry by fxr_none).
; The build-time need (main.asm "LEVEL POOL NEED") reads gu_tab / pool_gmap /
; pool_xmap too, so the tables and POOL_NEED cannot drift.
;
; SEQUENCE CACHE (3F-T2): the masters are src/seq_img.asm, a ZX0 stream
; (sqm_zx0, main.asm r6_blobs) unpacked to SQ_IMG per call (~60k T); ksm_tab
; there names each kind's block (tiers: their base's). sq_reset puts the
; hero's block in slot 0 (same bytes, same place every time: the hero's live
; E_SEQ stays valid), sq_load adds a kind's block (deduplicated by block),
; sq_fill writes KT_SEQ of every kind (no block cached: slot 0's row — no
; entity of such a kind exists in play). The scratch (PL_LIST, SQ_PTR,
; SQ_TOP, SQ_IMG) is the play-free GEN_SRC / GEN_MIR window: fi_full rebuilds
; the floor-item cache there at the following room build (as after any
; generator run), pblit stages its <= 54 B at GEN_SRC only after it.
;==============================================================================
PG_NONE         EQU $FF
PL_LIST         EQU GEN_SRC            ; pairs fid0, fcnt; $FF end
PL_CAP          EQU 2 * 17 + 1         ; level: <= 5 kinds x 3 units + 2 extras (3F-T13; build-ASSERTed
                                       ; per depth in main.asm LEVEL POOL NEED); hero: 2
SQ_PTR          EQU PL_LIST + PL_CAP   ; SQ_SLOTS words: each slot's master block (0 = free)
SQ_TOP          EQU SQ_PTR + 2 * SQ_SLOTS  ; word: the next free seq_bytes byte
PL_PROTO        EQU SQ_TOP + 2         ; pool_proto's kind list (6 B)
SQ_IMG          EQU GEN_SRC + 64       ; the unpacked masters (seq_img.asm is DISPed here)
LP_GEN_N        EQU 5                  ; LP_KINDS[0..3] + LP_BOSS (not the LP scratch: lp.py
                                       ; B0G reads LP_HX.. after a new game)
GU_STRIDE       EQU 2
FX_FID0         EQU KFID_FXM           ; the class FX fids [FX_FID0, FX_END): both FX units
FX_END          EQU KFID_FXW + KFCNT_FXW
                ASSERT LP_BOSS == LP_KINDS + 4 && PL_PROTO + K_PROTO_END - K_SKELETON <= SQ_IMG
                ASSERT FX_FID0 + KFCNT_FXM <= FX_END && KFID_FXW >= FX_FID0

;------------------------------------------------------------------------------
; pool_hero — far6 from start_game (HERO_KIND set, after gen_idles):
; PL_LIST := [hero unit, class FX unit]; seq slot 0 := the hero; KT_SEQ.
; pool_list — far6 from level_enter (after alloc_restore): PL_LIST := the
; units of LP_KINDS[0..3] + LP_BOSS (pool_gmap) + their hero extras
; (pool_xmap), each once, first-seen order; seq slots 1.. := their blocks.
; pool_proto — far6 from start_game (PROTO rooms, after pool_hero's session):
; the same for the original kinds K_SKELETON .. K_PROTO_END - 1.
; All three first (pl_begin): the masters unpacked, monster FRT rows := NONE
; (a kind not generated now blits nothing — BLIT_MISS — never stale pool
; bytes; 3F-T1's level_enter LDIR), the FX rows outside the hero's class FX
; := NONE (fxr_none), PL_LIST empty, seq slot 0 := the hero (sq_reset).
; Clobbers: A, BC, DE, HL.   ~0.1M T (unpack ~60k, FRT rows ~15k)
;------------------------------------------------------------------------------
pool_hero:
                ld   a, HIGH POOL6_END         ; 3F-T13: alloc's bank-6 limit = below SRC6 (the
                ld   (alloc.lim6 + 1), a       ; PROTO fixture may have moved it; SMC target, lowram.asm)
                call pl_begin
                ld   a, (HERO_KIND)
                call pl_unit
                ld   a, (HERO_KIND)
                add  a, K_FX_BASE
                call pl_unit
                jp   sq_fill

pool_proto:
                ; 3F-T13: the PROTO fixture (6 original kinds, POOL_NEED_PROTO) pools over the
                ; SRC6 sources: no 3F kind, no stairs in rooms A-D, so this session never reads
                ; them; the next game start (pool_hero) moves the limit back. A test must not
                ; descend from PROTO without a reload (SRC6 is then overwritten).
                ld   a, HIGH R6_ADDR
                ld   (alloc.lim6 + 1), a       ; SMC target (lowram.asm alloc)
                call pl_begin
                ld   hl, PL_PROTO              ; the kind list K_SKELETON ..
                ld   a, K_SKELETON
.w:             ld   (hl), a
                inc  hl
                inc  a
                cp   K_PROTO_END
                jr   c, .w
                ld   de, PL_PROTO
                ld   b, K_PROTO_END - K_SKELETON
                ld   a, (proto_start)          ; 3F-T3: bit PS_SLIME_BIT = also the Slime (the last
                bit  PS_SLIME_BIT, a           ; kind of the list); the default fixture pools the
                jr   nz, pl_kinds              ; other five (POOL_NEED_PROTO); tests poke 3
                dec  b
                jr   pl_kinds
                ASSERT K_PROTO_END - 1 == K_SLIME

pool_list:
                ; 3F-T13 guard: a level pool must never run with the PROTO limit (it would
                ; pool over SRC6 and the next descend read overwritten sources): trap + reset.
                ld   hl, alloc.lim6 + 1
                ld   a, HIGH POOL6_END
                cp   (hl)
                jr   z, .lim
                ld   (hl), a                   ; reset the SMC limit
                ld   hl, GEN_TRAP
                inc  (hl)
                jr   nz, .lim
                dec  (hl)                      ; saturate
.lim:           call pl_begin
                ld   de, LP_KINDS
                ld   b, LP_GEN_N
                ; fall through
; pl_kinds — DE = kind list, B = count: each kind's units (every pool_gmap
; record of the kind, else its own unit) + its hero extras -> PL_LIST, its seq
; block -> the cache; then KT_SEQ.
pl_kinds:
.k:             ld   a, (de)
                and  LEK_KIND_MASK             ; 3F-T5: LP_BOSS may carry LEK_GOLD
                push de
                push bc
                ld   e, a                      ; E = kind
                ld   d, a                      ; D = the fallback unit (own; PG_NONE once a record hit)
                ld   hl, pool_gmap
.g:             ld   a, (hl)
                cp   PG_NONE
                jr   z, .ge
                inc  hl
                cp   e
                jr   nz, .gn
                ld   d, PG_NONE
                call pl_unit_hl                ; u1
                call pl_unit_hl                ; u2
                jr   .g
.gn:            inc  hl
                inc  hl
                jr   .g
.ge:            ld   a, d
                call pl_unit                   ; no record: the kind's own unit (PG_NONE: none; keeps DE)
                ld   hl, pool_xmap             ; hero extras: DB kind, hero, unit
.x:             ld   a, (hl)
                cp   PG_NONE
                jr   z, .xe
                inc  hl
                cp   e
                ld   a, (hl)                   ; A = hero kind (flags: the kind test)
                inc  hl
                jr   nz, .xn
                push hl
                ld   hl, HERO_KIND
                cp   (hl)
                pop  hl
                jr   nz, .xn
                call pl_unit_hl
                jr   .x
.xn:            inc  hl
                jr   .x
.xe:            ld   a, e
                call sq_load
                pop  bc
                pop  de
                inc  de
                djnz .k
                jp   sq_fill

; pl_unit_hl — pl_unit of the unit byte at (HL); HL += 1. Keeps BC, DE.
pl_unit_hl:
                ld   a, (hl)
                inc  hl
                push hl
                call pl_unit
                pop  hl
                ret

pl_begin:
                ld   hl, sqm_zx0               ; the sequence masters -> SQ_IMG
                ld   de, SQ_IMG
                call dzx0_standard
                ld   a, KFID_MONSTERS
                ld   b, KFCNT_MONSTERS
                call frt_none
                call fxr_none
                ld   a, PG_NONE                ; PL_LIST := empty
                ld   (PL_LIST), a
                jp   sq_reset                  ; seq slot 0 := the hero (low RAM)

; pl_unit — A = unit (PG_NONE: none): append its pair to PL_LIST unless it has
; no frames or is listed already (same fid0). Keeps BC, DE.  Clobbers: A, F, HL
pl_unit:
                cp   PG_NONE
                ret  z
                push de
                add  a, a                      ; units < 128
                ld   l, a
                ld   h, 0
                ld   de, gu_tab
                add  hl, de
                ld   d, (hl)                   ; D = fid0
                inc  hl
                ld   a, (hl)                   ; frames
                or   a
                jr   z, .r                     ; 0-frame unit (the Rogue hole, 3F rows)
                ld   e, a
                ld   hl, PL_LIST
.c:             ld   a, (hl)
                cp   PG_NONE
                jr   z, .add
                cp   d
                jr   z, .r                     ; listed already
                inc  hl
                inc  hl
                jr   .c
.add:           ld   (hl), d
                inc  hl
                ld   (hl), e
                inc  hl
                ld   (hl), PG_NONE
.r:             pop  de
                ret

;------------------------------------------------------------------------------
; frt_none — A = first fid, B = count (>= 1): those FRT rows := FRT_NONE (all
; 16 B, as the 3F-T1 level clear).   Clobbers: A, BC, DE, HL.   ~21 T / byte
;------------------------------------------------------------------------------
frt_none:
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ld   de, FRT
                add  hl, de                    ; HL = the first row
                ex   de, hl
                ld   l, b
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                dec  hl
                ld   b, h
                ld   c, l                      ; BC = count x 16 - 1 (>= 15)
                ex   de, hl
                ld   (hl), FRT_NONE
                ld   d, h
                ld   e, l
                inc  de
                ldir
                ret
                ASSERT FRT_STRIDE == 16

; fxr_none — the FX FRT rows outside the hero's class FX unit := NONE: the other
; class's exclusive rows and any hero extra of the previous level (3F-T2: the
; T1 note — a bolt / arrow drawn from another class's stale row). The class
; FX rows themselves are generated by start_game / kept for the game.
; Clobbers: A, BC, DE, HL.
fxr_none:
                ld   a, (HERO_KIND)
                add  a, K_FX_BASE
                add  a, a
                ld   l, a
                ld   h, 0
                ld   de, gu_tab
                add  hl, de
                ld   a, (hl)                   ; A = fid0 of the class FX
                inc  hl
                add  a, (hl)                   ; A = its end
                push af
                dec  hl
                ld   a, (hl)
                sub  FX_FID0                   ; rows [FX_FID0, fid0)
                ld   b, a
                ld   a, FX_FID0
                call nz, frt_none
                pop  af                        ; rows [end, FX_END)
                ld   b, a
                ld   a, FX_END
                sub  b
                ret  z
                ld   c, b                      ; A = count, C = first
                ld   b, a
                ld   a, c
                jp   frt_none

;------------------------------------------------------------------------------
; gu_tab — the generation units: DB fid0, fcnt (see the header). Units < K_MAX
; are the kinds (the old kind_tab KT_FID0 / KT_FCNT columns; D3-4: the class FX
; kinds K_FXW / K_FXM, ids 30 / 31, overlapping ranges).
;------------------------------------------------------------------------------
    MACRO GU f0, fn
                DB   f0, fn
    ENDM
gu_tab:
                GU   KFID_KNIGHT, KFCNT_KNIGHT
                GU   KFID_WIZARD, KFCNT_WIZARD
                GU   0, 0                      ; id 2 retired
                GU   KFID_SKELETON, KFCNT_SKELETON             ; (generated as U_SKARCH + U_SKCLIMB + U_SKREST)
                GU   KFID_GOBLIN, KFCNT_GOBLIN
                GU   KFID_GHOST, KFCNT_GHOST
                GU   KFID_RAT, KFID_RATDEAD - KFID_RAT         ; the Rat's body (+ U_DEADR: pool_gmap)
                GU   KFID_BAT, KFCNT_BAT
                GU   KFID_SLIME, KFCNT_SLIME
                ; 3F-T13: the real 3F-A1 units of the new base kinds (ids 9..17); a kind drawing
                ; another's frames names that unit (informational: its pool_gmap records decide)
                GU   KFID_SPIDER, KFCNT_SPIDER                 ; K_SPIDER (+ U_DEADR)
                GU   KFID_NECRO, KFCNT_NECRO                   ; K_VAMPIRE (the Necro walk; + U_VBITE)
                GU   KFID_ORC, KFCNT_ORC                       ; K_ORC
                GU   KFID_SKELETON, KFCNT_SKARCH               ; K_ARCHER (= U_SKARCH: walk1..4 + cut)
                GU   KFID_MUMMY, KFCNT_MUMMY                   ; K_MUMMY
                GU   KFID_NECRO, KFCNT_NECRO                   ; K_NECRO = walk1..3 (+ U_NCAST, U_DEADH, U_NBOLT, U_CLIMBH)
                GU   KFID_OGRE, KFCNT_OGRE                     ; K_OGRE
                GU   KFID_DKNIGHT, KFCNT_DKNIGHT               ; K_DKNIGHT
                GU   KFID_NECRO, KFCNT_NECRO                   ; K_ARCHMAGE (the Necro's frames)
                ; the 12 tier rows (18..29) name their BASE kind's unit (same frames, 0 pool; never
                ; in LP_KINDS / LP_BOSS, so never generated as a unit of their own)
                GU   KFID_RAT, KFID_RATDEAD - KFID_RAT         ; K_GIANT_RAT
                GU   KFID_RAT, KFID_RATDEAD - KFID_RAT         ; K_RABBIT_RAT
                GU   KFID_BAT, KFCNT_BAT                       ; K_SCREECH
                GU   KFID_GOBLIN, KFCNT_GOBLIN                 ; K_SLINGER
                GU   KFID_SPIDER, KFCNT_SPIDER                 ; K_BLACK_WIDOW
                GU   KFID_SKELETON, KFCNT_SKELETON             ; K_SKEL_GUARD
                GU   KFID_SKELETON, KFCNT_SKELETON             ; K_SKEL_KNIGHT
                GU   KFID_GHOST, KFCNT_GHOST                   ; K_POLTERGEIST
                GU   KFID_ORC, KFCNT_ORC                       ; K_ORC_BERSERK
                GU   KFID_ORC, KFCNT_ORC                       ; K_ORC_BOUNCER
                GU   KFID_SKELETON, KFCNT_SKARCH               ; K_SNIPER
                GU   KFID_NECRO, KFCNT_NECRO                   ; K_BONE_CALLER
                ASSERT K_BONE_CALLER == K_FXW - 1
                GU   KFID_FXW, KFCNT_FXW
                GU   KFID_FXM, KFCNT_FXM
gu_tab_x:                                      ; units >= K_MAX (extras, 3F-T13)
U_SKARCH        EQU K_MAX + 0
                GU   KFID_SKELETON, KFCNT_SKARCH               ; Skeleton walk1..4 + cut (= the Archer)
U_SKREST        EQU K_MAX + 1
                GU   KFID_SKREST, KFCNT_SKREST                 ; Skeleton raise, collapsed, hurt
U_DEADR         EQU K_MAX + 2
                GU   KFID_RATDEAD, 1                           ; small_corpse (Rat, Spider; 3F-T13bc: was rat_dead)
U_DEADH         EQU K_MAX + 3
                GU   KFID_DEADH, 1                             ; dead_humanoid (every 3F humanoid + Ogre)
U_NBOLT         EQU K_MAX + 4
                GU   KFID_NBOLT, KFCNT_NBOLT                   ; nbolt_fly1/2 + hit (Necro, Archmage)
U_ARROWM        EQU K_MAX + 5
                GU   FID_arrow_fly1, 2                         ; Mage extra on Archer levels (D4 / D5 / D7)
U_DAGM          EQU K_MAX + 6
                GU   FID_dagger_spin1, 2                       ; Mage extra on Goblin levels (Slinger rock)
U_CLIMBH        EQU K_MAX + 7
                GU   KFID_CLIMBH, 2                            ; 3F-T13bc: the shared humanoid climb pair
U_NCAST         EQU K_MAX + 8
                GU   KFID_NCAST, 1                             ; 3F-T13bc: necro_cast (Necro, Archmage)
U_VBITE         EQU K_MAX + 9
                GU   KFID_VBITE, 1                             ; 3F-T13bc: vamp_bite (Vampire)
U_SKCLIMB       EQU K_MAX + 10
                GU   KFID_SKCLIMB, KFCNT_SKCLIMB               ; Skeleton climb1/2 (Skeleton, Archer, Sniper)
gu_tab_end:
GU_N            EQU (gu_tab_end - gu_tab) / GU_STRIDE
                ASSERT gu_tab_x - gu_tab == GU_STRIDE * K_MAX && GU_N <= 64 && K_COUNT == 30
                ASSERT K_FXW == K_MAX - 2 && K_FXM == K_MAX - 1
                ASSERT KFID_SKCLIMB == KFID_SKELETON + KFCNT_SKARCH && KFID_SKREST == KFID_SKCLIMB + KFCNT_SKCLIMB && FID_skeleton_climb2 == KFID_SKREST - 1 && KFCNT_SKCLIMB == 2 && FID_skeleton_cut == KFID_SKCLIMB - 1
                ASSERT KFID_RATDEAD == KFID_RAT + KFCNT_RAT - 1 && FID_small_corpse == KFID_RATDEAD
                ASSERT KFID_NCAST == KFID_NECRO + KFCNT_NECRO && KFID_VBITE == KFID_NCAST + 1
                ASSERT FID_climb_h2 == KFID_CLIMBH + 1
                ASSERT FID_arrow_fly2 == FID_arrow_fly1 + 1 && FID_dagger_spin2 == FID_dagger_spin1 + 1
                ; the Mage's extras lie outside his class FX unit (fxr_none NONEs them per level)
                ASSERT FID_arrow_fly1 >= KFID_FXM + KFCNT_FXM && FID_dagger_spin1 >= KFID_FXM + KFCNT_FXM

; pool_gmap — the generation map (see the header): every record of a kind applies. Kinds < $80.
pool_gmap:
                DB   K_SKELETON, U_SKARCH,   U_SKREST
                DB   K_SKELETON, U_SKCLIMB,  PG_NONE
                DB   K_RAT,      K_RAT,      U_DEADR
                DB   K_SPIDER,   K_SPIDER,   U_DEADR
                ; 3F-T13bc: the Necro walk is shared (K_NECRO unit = walk1..3), the Vampire adds its
                ; bite, the Necro / Archmage the cast; climbers (Orc, Necro, Mummy) add the
                ; shared climb pair U_CLIMBH (the Archer family uses the Skeleton's U_SKCLIMB) (once a level: dedup per unit)
                DB   K_VAMPIRE,  K_NECRO,    U_VBITE
                DB   K_VAMPIRE,  U_DEADH,    PG_NONE
                DB   K_ORC,      K_ORC,      U_DEADH
                DB   K_ORC,      U_CLIMBH,   PG_NONE
                DB   K_ARCHER,   U_SKARCH,   U_DEADH  ; SHOOT = the Skeleton cut (game.md §9.7 DECIDED)
                DB   K_ARCHER,   U_SKCLIMB,  PG_NONE  ; the Skeleton's own climb pair (not U_CLIMBH)
                DB   K_MUMMY,    K_MUMMY,    U_DEADH
                DB   K_MUMMY,    U_CLIMBH,   PG_NONE
                DB   K_NECRO,    K_NECRO,    U_DEADH
                DB   K_NECRO,    U_NBOLT,    U_NCAST
                DB   K_NECRO,    U_CLIMBH,   PG_NONE
                DB   K_OGRE,     K_OGRE,     U_DEADH
                DB   K_DKNIGHT,  K_DKNIGHT,  U_DEADH
                DB   K_ARCHMAGE, K_NECRO,    U_DEADH
                DB   K_ARCHMAGE, U_NBOLT,    U_NCAST
                DB   PG_NONE
pool_gmap_end:
PGMAP_N         EQU (pool_gmap_end - pool_gmap - 1) / 3
                ASSERT pool_gmap_end - pool_gmap == 3 * PGMAP_N + 1

; pool_xmap — the hero extras (see the header): DB kind, hero kind, unit.
pool_xmap:
                DB   K_ARCHER, K_WIZARD, U_ARROWM
                DB   K_GOBLIN, K_WIZARD, U_DAGM
                DB   PG_NONE
pool_xmap_end:
PXMAP_N         EQU (pool_xmap_end - pool_xmap - 1) / 3
                ASSERT pool_xmap_end - pool_xmap == 3 * PXMAP_N + 1
                ASSERT 2 * (3 * LP_GEN_N + 2) + 1 <= PL_CAP && 2 * 2 * (K_PROTO_END - K_SKELETON) + 1 <= PL_CAP
