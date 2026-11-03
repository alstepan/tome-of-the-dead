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
;   (pool_proto: D3-11, the PROTO test fixture src/proto_fix.asm)
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
; 3F-T9 exception: units with the SAME fid0 merge (pl_unit keeps the longer
; count): K_VBAT (the Bat's first 2 frames) inside K_BAT on D3.
;
; GENERATION MAP (pool_gmap; 3F-T13: EVERY matching record applies, was the
; first): records DB kind, u1, u2 (u2 = PG_NONE: none); a kind with records
; generates their units INSTEAD of its own unit (Skeleton = U_SKARCH +
; U_SKCLIMB + U_SKREST + U_DEADR, Archer = U_SKARCH + U_SKCLIMB + U_DEADR, Archmage = its own + U_DEADR + U_NBOLT (3F-T11),
; Necro = its own + U_DEADR + U_NBOLT: two records; CORPSE-ASHES: U_DEADR = THE
; monster corpse of every kind but the Bat / Slime / Ghost). Tier rows are never in
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
; (D3-11: the PROTO fixture, src/proto_fix.asm, runs the same session for the
; original kinds K_SKELETON .. K_PROTO_END - 1 with pl_begin / pl_kinds.)
; All three first (pl_begin): the masters unpacked, monster FRT rows := NONE
; (a kind not generated now blits nothing — BLIT_MISS — never stale pool
; bytes; 3F-T1's level_enter LDIR), the FX rows outside the hero's class FX
; := NONE (fxr_none), PL_LIST empty, seq slot 0 := the hero (sq_reset).
; Clobbers: A, BC, DE, HL.   ~0.1M T (unpack ~60k, FRT rows ~15k)
;------------------------------------------------------------------------------
pool_hero:
                call pl_begin                  ; (D3-11: the bank-6 limit is never left moved)
                ld   a, (HERO_KIND)
                call pl_unit
                ld   a, (HERO_KIND)
                add  a, K_FX_BASE
                call pl_unit
                jp   sq_fill

; pool_proto: D3-11, the PROTO test fixture (src/proto_fix.asm) runs it.

pool_list:
                ; (3F-T13's PROTO-limit guard is gone, D3-11: the PROTO fixture puts the
                ; bank-6 limit back itself after its pool session, proto_fix.asm)
                call pl_begin
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
                cp   K_VAMPIRE                 ; 3F-T9: + its bat form's block (K_VBAT's KT_SEQ)
                jr   nz, .xs
                ld   a, K_VBAT
                call sq_load
                ld   a, K_VAMPIRE
.xs:            call sq_load
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
                jr   z, .r                     ; 0-frame unit
                ld   e, a
                ld   hl, PL_LIST
.c:             ld   a, (hl)
                cp   PG_NONE
                jr   z, .add
                cp   d
                jr   z, .same                  ; listed already
                inc  hl
                inc  hl
                jr   .c
.same:          inc  hl                        ; 3F-T9: same fid0 = one range: keep the longer
                ld   a, (hl)                   ; (K_VBAT's 2 Bat frames + the Bat's 6 on D3)
                cp   e
                jr   nc, .r
                ld   (hl), e
                jr   .r
.add:           ld   (hl), d
                inc  hl
                ld   (hl), e
                inc  hl
                ld   (hl), PG_NONE
.r:             pop  de
                ret

;------------------------------------------------------------------------------
; frt_none — A = first fid, B = count (>= 1): those FRT rows' variants (bytes
; 0..FT_IN_ROW-1) := FRT_NONE. MEM-FT: the row tail is the fid's static
; frame_tab entry, so a row is no longer filled whole (was one 16-B LDIR run).
; Clobbers: A, BC, HL.   ~390 T / row (was ~340: 16 B at 21 T)
;------------------------------------------------------------------------------
frt_none:
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ld   a, b                      ; A = rows
                ld   bc, FRT
                add  hl, bc                    ; HL = the first row
.r:             ld   b, FT_IN_ROW
.f:             ld   (hl), FRT_NONE
                inc  hl
                djnz .f
                inc  hl                        ; skip the frame_tab tail
                inc  hl
                inc  hl
                inc  hl
                dec  a
                jr   nz, .r
                ret
                ASSERT FRT_STRIDE == 16 && FT_IN_ROW + 4 == FRT_STRIDE

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
                GU   KFID_BAT, VB_FCNT         ; K_VBAT (3F-T9): the Bat's flapup / glide (via pool_gmap K_VAMPIRE)
                GU   KFID_SKELETON, KFCNT_SKELETON             ; (generated as U_SKARCH + U_SKCLIMB + U_SKREST)
                GU   KFID_GOBLIN, KFCNT_GOBLIN
                GU   KFID_GHOST, KFCNT_GHOST
                GU   KFID_RAT, KFID_RATDEAD - KFID_RAT         ; the Rat's body (+ U_DEADR: pool_gmap)
                GU   KFID_BAT, KFCNT_BAT
                GU   KFID_SLIME, KFCNT_SLIME
                ; 3F-T13: the real 3F-A1 units of the new base kinds (ids 9..17); a kind drawing
                ; another's frames names that unit (informational: its pool_gmap records decide)
                GU   KFID_SPIDER, KFCNT_SPIDER                 ; K_SPIDER (+ U_DEADR)
                GU   KFID_VAMPIRE, KFCNT_VAMPIRE               ; K_VAMPIRE (ANIM-IMPORT2: its own set)
                GU   KFID_ORC, KFCNT_ORC                       ; K_ORC
                GU   KFID_SKELETON, KFCNT_SKARCH               ; K_ARCHER (= U_SKARCH: walk1..4 + cut + hurt)
                GU   KFID_MUMMY, KFCNT_MUMMY                   ; K_MUMMY
                GU   KFID_NECRO, KFCNT_NECRO                   ; K_NECRO = walk1..4 (+ U_NCAST, U_DEADR, U_NBOLT, U_CLIMBH)
                GU   KFID_OGRE, KFCNT_OGRE                     ; K_OGRE
                GU   KFID_DKNIGHT, KFCNT_DKNIGHT               ; K_DKNIGHT
                GU   KFID_ARCH, KFCNT_ARCH                     ; K_ARCHMAGE (3F-T11: the nun's own walk1/2 + cast + hurt)
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
                GU   KFID_SKELETON, KFCNT_SKARCH               ; Skeleton walk1..4 + cut + hurt (= the Archer; ANIM-IMPORT: + hurt)
U_SKREST        EQU K_MAX + 1
                GU   KFID_SKREST, KFCNT_SKREST                 ; Skeleton raise (CORPSE-ASHES: collapsed out; ANIM-IMPORT: hurt -> U_SKARCH)
U_DEADR         EQU K_MAX + 2
                GU   KFID_RATDEAD, 1                           ; small_corpse: CORPSE-ASHES, every monster but Bat / Slime / Ghost
                ; CORPSE-ASHES: U_DEADH (dead_humanoid) retired; the later units renumbered
U_NBOLT         EQU K_MAX + 3
                GU   KFID_NBOLT, KFCNT_NBOLT                   ; nbolt_fly1/2 + hit (Necro, Bone Caller, Archmage)
U_ARROWM        EQU K_MAX + 4
                GU   FID_arrow_fly1, 2                         ; Mage extra on Archer levels (D4 / D5 / D7)
U_DAGM          EQU K_MAX + 5
                GU   FID_dagger_spin1, 2                       ; Mage extra on Goblin levels (Slinger rock)
U_CLIMBH        EQU K_MAX + 6
                GU   KFID_CLIMBH, 2                            ; 3F-T13bc: the shared humanoid climb pair
U_NCAST         EQU K_MAX + 7
                GU   KFID_NCAST, 1                             ; 3F-T13bc: necro_cast (Necro, Bone Caller)
                ; ANIM-IMPORT2: U_VBITE retired (vamp_bite is in the Vampire's own unit)
U_SKCLIMB       EQU K_MAX + 8
                GU   KFID_SKCLIMB, KFCNT_SKCLIMB               ; Skeleton climb1/2 (Skeleton, Archer, Sniper)
U_SPARKW        EQU K_MAX + 9
                GU   FID_spark_fly1, 2                         ; Warrior extra on Spider levels (the Queen's spit)
gu_tab_end:
GU_N            EQU (gu_tab_end - gu_tab) / GU_STRIDE
                ASSERT gu_tab_x - gu_tab == GU_STRIDE * K_MAX && GU_N <= 64 && K_COUNT == 30
                ASSERT K_FXW == K_MAX - 2 && K_FXM == K_MAX - 1
                ASSERT KFID_SKCLIMB == KFID_SKELETON + KFCNT_SKARCH && KFID_SKREST == KFID_SKCLIMB + KFCNT_SKCLIMB && FID_skeleton_climb2 == KFID_SKREST - 1 && KFCNT_SKCLIMB == 2 && FID_skeleton_hurt == KFID_SKCLIMB - 1 && FID_skeleton_cut == KFID_SKCLIMB - 2 && KFCNT_SKREST == 1
                ASSERT KFID_RATDEAD == KFID_RAT + KFCNT_RAT - 1 && FID_small_corpse == KFID_RATDEAD
                ASSERT KFID_NCAST == KFID_NECRO + KFCNT_NECRO
                ASSERT FID_climb_h2 == KFID_CLIMBH + 1
                ASSERT FID_arrow_fly2 == FID_arrow_fly1 + 1 && FID_dagger_spin2 == FID_dagger_spin1 + 1
                ASSERT FID_spark_fly2 == FID_spark_fly1 + 1 && FID_spark_fly1 == KFID_FXM   ; the Warrior's extra: outside K_FXW,
                                                       ; inside the Mage's (xmap row is Warrior-only; fxr_none runs first)
                ; the Mage's extras lie outside his class FX unit (fxr_none NONEs them per level)
                ASSERT FID_arrow_fly1 >= KFID_FXM + KFCNT_FXM && FID_dagger_spin1 >= KFID_FXM + KFCNT_FXM

VB_FCNT         EQU 2                          ; 3F-T9: K_VBAT's frames = the Bat's first two
; pool_gmap — the generation map (see the header): every record of a kind applies. Kinds < $80.
pool_gmap:
                DB   K_SKELETON, U_SKARCH,   U_SKREST
                DB   K_SKELETON, U_SKCLIMB,  U_DEADR
                DB   K_GOBLIN,   K_GOBLIN,   U_DEADR   ; CORPSE-ASHES: the Goblin's DEAD is the shared corpse
                DB   K_RAT,      K_RAT,      U_DEADR
                DB   K_SPIDER,   K_SPIDER,   U_DEADR
                ; 3F-T13bc: the Necro walk is shared (K_NECRO unit = walk1..4: Necro / Bone Caller),
                ; the Necro adds the cast (3F-T11: the Archmage has its own unit); climbers (Orc, Necro, Mummy) add the
                ; shared climb pair U_CLIMBH (the Archer family uses the Skeleton's U_SKCLIMB) (once a level: dedup per unit)
                DB   K_VAMPIRE,  K_VAMPIRE,  U_DEADR   ; ANIM-IMPORT2: own set (was Necro walk + U_VBITE)
                DB   K_VAMPIRE,  U_CLIMBH,   PG_NONE   ; VAMP-BOSS: the shared climb pair (the Vampire climbs)
                DB   K_VAMPIRE,  K_VBAT,     PG_NONE   ; 3F-T9: its bat form (the Bat's first 2 frames; on a
                                                       ; Bat level pl_unit merges them into the Bat's unit)
                DB   K_ORC,      K_ORC,      U_DEADR
                DB   K_ORC,      U_CLIMBH,   PG_NONE
                DB   K_ARCHER,   U_SKARCH,   U_DEADR  ; SHOOT = the Skeleton cut (game.md §9.7 DECIDED)
                DB   K_ARCHER,   U_SKCLIMB,  PG_NONE  ; the Skeleton's own climb pair (not U_CLIMBH)
                DB   K_MUMMY,    K_MUMMY,    U_DEADR
                DB   K_MUMMY,    U_CLIMBH,   PG_NONE
                DB   K_NECRO,    K_NECRO,    U_DEADR
                DB   K_NECRO,    U_NBOLT,    U_NCAST
                DB   K_NECRO,    U_CLIMBH,   PG_NONE
                DB   K_OGRE,     K_OGRE,     U_DEADR
                DB   K_DKNIGHT,  K_DKNIGHT,  U_DEADR
                DB   K_ARCHMAGE, K_ARCHMAGE, U_DEADR   ; 3F-T11: the nun (walk1/2, cast, hurt)
                DB   K_ARCHMAGE, U_NBOLT,    PG_NONE   ; its Death Bolt (rd_tab row RW_FX)
                DB   PG_NONE
pool_gmap_end:
PGMAP_N         EQU (pool_gmap_end - pool_gmap - 1) / 3
                ASSERT pool_gmap_end - pool_gmap == 3 * PGMAP_N + 1

; pool_xmap — the hero extras (see the header): DB kind, hero kind, unit.
pool_xmap:
                DB   K_ARCHER, K_WIZARD, U_ARROWM
                DB   K_GOBLIN, K_WIZARD, U_DAGM
                DB   K_SPIDER, K_KNIGHT, U_SPARKW              ; BOSS-RANGED: the Queen's spit = spark_fly1/2 (golden D2;
                                                       ; the Mage's class FX unit already holds them)
                DB   PG_NONE
pool_xmap_end:
PXMAP_N         EQU (pool_xmap_end - pool_xmap - 1) / 3
                ASSERT pool_xmap_end - pool_xmap == 3 * PXMAP_N + 1
                ASSERT 2 * (3 * LP_GEN_N + 2) + 1 <= PL_CAP && 2 * 2 * (K_PROTO_END - K_SKELETON) + 1 <= PL_CAP
