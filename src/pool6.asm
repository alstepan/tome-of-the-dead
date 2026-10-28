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
; units >= K_MAX = extra ranges with no kind (3F: e.g. a SHOOT frame, the
; Necro bolt, the Mage's arrows) — none yet. Monster / extra units must not
; overlap (dedup is per unit, by fid0: an overlap would be generated twice).
;
; GENERATION MAP (pool_gmap, 3F-T1 contract): records DB kind, u1, u2 (u2 =
; PG_NONE: none), first match wins; a mapped kind generates u1 (+ u2) INSTEAD
; of its own unit (tier rows -> their base unit, Vampire / Archmage -> Necro,
; Archer -> Skeleton walk + its SHOOT unit). 3F-T3: the nine new base kinds map to
; their STAND-IN units (T13 replaces the records).
; HERO EXTRAS (pool_xmap, 3F-T2): records DB kind, hero kind, unit: on a level
; listing the kind, a game of that hero also generates the unit (game.md 3F:
; the Mage's arrow frames on Archer levels, dagger_spin on D1 / D2). Empty
; today. An extra unit must lie outside that hero's class FX unit (it is
; NONE'd at the next level entry by fxr_none).
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
PL_CAP          EQU 2 * 12 + 1         ; level: <= 5 kinds x 2 units + 2 extras; hero: 2
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
; units of LP_KINDS[0..3] + LP_BOSS (pool_map) + their hero extras
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
                call pl_begin
                ld   a, (HERO_KIND)
                call pl_unit
                ld   a, (HERO_KIND)
                add  a, K_FX_BASE
                call pl_unit
                jp   sq_fill

pool_proto:
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
                call pl_begin
                ld   de, LP_KINDS
                ld   b, LP_GEN_N
                ; fall through
; pl_kinds — DE = kind list, B = count: each kind's units + hero extras ->
; PL_LIST, its seq block -> the cache; then KT_SEQ.
pl_kinds:
.k:             ld   a, (de)
                and  LEK_KIND_MASK             ; 3F-T5: LP_BOSS may carry LEK_GOLD
                push de
                push bc
                push af
                call pool_map                  ; B = u1, C = u2
                ld   a, b
                call pl_unit
                ld   a, c
                call pl_unit
                pop  af
                push af
                ld   e, a                      ; hero extras: DB kind, hero, unit
                ld   hl, pool_xmap
.x:             ld   a, (hl)
                cp   PG_NONE
                jr   z, .xe
                inc  hl
                cp   e
                ld   a, (hl)                   ; A = hero kind (flags: the kind test)
                inc  hl
                ld   b, (hl)                   ; B = unit
                inc  hl
                jr   nz, .x
                push hl
                ld   hl, HERO_KIND
                cp   (hl)
                ld   a, b
                call z, pl_unit                ; (keeps DE)
                pop  hl
                jr   .x
.xe:            pop  af
                call sq_load
                pop  bc
                pop  de
                inc  de
                djnz .k
                jp   sq_fill

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

; pool_map — A = kind -> B = u1, C = u2 (PG_NONE) per pool_gmap (no record:
; B = the kind's own unit).   Clobbers: F, HL.
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
                GU   KFID_SKELETON, KFCNT_SKELETON
                GU   KFID_GOBLIN, KFCNT_GOBLIN
                GU   KFID_GHOST, KFCNT_GHOST
                GU   KFID_RAT, KFCNT_RAT
                GU   KFID_BAT, KFCNT_BAT
                GU   KFID_SLIME, KFCNT_SLIME
                ; 3F-T3: ids 9..17 (the new base kinds) have no unit of their own yet: their STAND-IN
                ; frames come from pool_gmap (below); T13 puts the real units here. The 12 tier rows
                ; (18..29) name their BASE kind's unit (same frames, 0 new ids, 0 pool; Black Widow =
                ; the Spider's, i.e. the Rat stand-in for now), so a tier needs no map entry.
                DS   GU_STRIDE * (K_GIANT_RAT - K_SPIDER), 0   ; ids 9..17
                GU   KFID_RAT, KFCNT_RAT                       ; K_GIANT_RAT
                GU   KFID_RAT, KFCNT_RAT                       ; K_RABBIT_RAT
                GU   KFID_BAT, KFCNT_BAT                       ; K_SCREECH
                GU   KFID_GOBLIN, KFCNT_GOBLIN                 ; K_SLINGER
                GU   KFID_RAT, KFCNT_RAT                       ; K_BLACK_WIDOW (the Spider's stand-in)
                GU   KFID_SKELETON, KFCNT_SKELETON             ; K_SKEL_GUARD
                GU   KFID_SKELETON, KFCNT_SKELETON             ; K_SKEL_KNIGHT
                GU   KFID_GHOST, KFCNT_GHOST                   ; K_POLTERGEIST
                GU   KFID_SKELETON, KFCNT_SKELETON             ; K_ORC_BERSERK (the Orc's stand-in)
                GU   KFID_SKELETON, KFCNT_SKELETON             ; K_ORC_BOUNCER
                GU   KFID_SKELETON, KFCNT_SKELETON             ; K_SNIPER (the Archer's)
                GU   KFID_SKELETON, KFCNT_SKELETON             ; K_BONE_CALLER (the Necro's)
                ASSERT K_BONE_CALLER == K_FXW - 1
                GU   KFID_FXW, KFCNT_FXW
                GU   KFID_FXM, KFCNT_FXM
gu_tab_x:                                      ; units >= K_MAX (extras): none yet
gu_tab_end:
GU_N            EQU (gu_tab_end - gu_tab) / GU_STRIDE
                ASSERT gu_tab_x - gu_tab == GU_STRIDE * K_MAX && GU_N <= 64 && K_COUNT == 30
                ASSERT K_FXW == K_MAX - 2 && K_FXM == K_MAX - 1

; pool_gmap — the generation map (see the header). Kinds < $80.
pool_gmap:
                ; 3F-T3 STAND-INS (T13 replaces each record by the kind's own unit(s)): a new base
                ; kind generates the frames of the nearest existing body (unit dedup by fid0 at run
                ; time, by this map at build time: one Skeleton set serves the Vampire, Orc, Archer,
                ; Mummy, Necro, Ogre, Death Knight, Archmage)
                DB   K_SPIDER,   K_RAT,      PG_NONE
                DB   K_VAMPIRE,  K_SKELETON, PG_NONE
                DB   K_ORC,      K_SKELETON, PG_NONE
                DB   K_ARCHER,   K_SKELETON, PG_NONE
                DB   K_MUMMY,    K_SKELETON, PG_NONE
                DB   K_NECRO,    K_SKELETON, PG_NONE
                DB   K_OGRE,     K_SKELETON, PG_NONE
                DB   K_DKNIGHT,  K_SKELETON, PG_NONE
                DB   K_ARCHMAGE, K_SKELETON, PG_NONE
                DB   PG_NONE
pool_gmap_end:
PGMAP_N         EQU (pool_gmap_end - pool_gmap - 1) / 3
                ASSERT pool_gmap_end - pool_gmap == 3 * PGMAP_N + 1

; pool_xmap — the hero extras (see the header): DB kind, hero kind, unit.
pool_xmap:
                DB   PG_NONE                   ; (empty: no Archer / thrower kind yet)
pool_xmap_end:
PXMAP_N         EQU (pool_xmap_end - pool_xmap - 1) / 3
                ASSERT pool_xmap_end - pool_xmap == 3 * PXMAP_N + 1
                ASSERT 2 * (2 * LP_GEN_N + 2) + 1 <= PL_CAP && 2 * 2 * (K_PROTO_END - K_SKELETON) + 1 <= PL_CAP
