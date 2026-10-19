;==============================================================================
; bank3.asm — COLD code paged in at $C000 from bank 3 (docs/memory-map.md
; "Bank 3"). Assembled right after the sprite-source tail, below the AY
; reserve (AY_RESERVE, $EDA0 since MEM-SND, $F000 since D3-0; A8). Entered ONLY through far3 (gfx.asm), which pages
; bank 3 in and puts the caller's $C000 bank back on return.
;
; Rule: nothing here may page $C000 directly (it would unmap the code that is
; running). The select screen blits through blit_keep (re-pages bank 3 after the
; pool blit); the transition scrolls never touch $C000 at all (screen, ROOM_MAP,
; NEXT_MAP and TILE_* are in bank 5, TMP4/TMP5 in bank 2).
; FORBIDDEN callees from here (they page $C000): page_bank, shadow_rect,
; shadow_room, erase_rect, hide_sprites, draw_room, blit_sprite (use blit_keep),
; present / present_full (A7), and every bank-5 generator
; routine (gen_*, alloc*, copy_virt, mirror_src). (B3B-R2: shadow_rect only as a
; tail jump — floor_pickup (ap_stamp); door_paint re-pages the caller's bank itself.)
; D3-S2: bank-7 code (bank7.asm: find_target, the player turn, ...) only via
; far7 (nests: bank 3 comes back), e.g. panel_init -> panel_init7 (boot7.asm).
; A7: everything here draws on the $4000 (bank 5) screen, which is the one
; displayed while it runs (enter_select / do_exit call show_bank5 first).
;
; Bank 3 is contended: code fetches here pay ULA contention (cold paths only:
; the select screen idles in HALT; the scrolls are dominated by contended
; screen LDI anyway).
;==============================================================================

;------------------------------------------------------------------------------
; kx_tab — D3-0 (R2): the per-kind extension table (combat_defs.asm "KX"),
; K_MAX rows x KX_STRIDE B, first in bank 3 so it sits in one page (`ld h`,
; L = kind * 6). Reserved here, zero = no resistance / immunity, 0 XP, DEF 0;
; D3-1: combat_data3.asm defines kx_tab here (+ the other combat tables).
;------------------------------------------------------------------------------
                INCLUDE "combat_data3.asm"    ; D3-1: kx_tab rows + XP / level-up / ability tables
                ASSERT (kx_tab & $FF) + KX_LEN <= 256

; sel_run (the PROTO hero select): replaced by the C3-6 menu (menu1.asm, bank 1).

; TRANSITION SCROLLS: bank 1 since the C3-3 review (scroll1.asm, far1).

;==============================================================================
; A7 review: cold game-state code moved out of bank 2 (bank-2 headroom for
; Stage-3 hot code): new_game (bank 7 since MEM-SND; init_ent_common,
; spawn_tab and its PROTO tail new_game_proto stay here), the follower
; admission (L-RELIEF: the candidate scan, place_follower and the arrival
; conflicts are bank 7 now). None of it pages $C000 (only bank-2 queries +
; vis_reset in bank-5 low RAM).
;==============================================================================
;==============================================================================
; new_game_proto — MEM-SND: the bank-3 tail of new_game (bank 7 since MEM-SND,
; boot7.asm), far3 from it when proto_start = 1 (test path, docs/memory-map.md
; "Level entry"): the PROTO rooms A-D (proto_level) + the spawn_tab monsters
; in slots 1.. (both bank-3 data), then vis_reset. Clobbers: all but IY.
;==============================================================================
new_game_proto:
                call proto_level               ; B3B-8: rooms A-D = a 3B level state
                ; --- monsters from spawn_tab, slots 1.. ---
                ld   hl, spawn_tab
                ld   b, SPAWN_COUNT
                ld   ix, P_ENTITIES + P_ENT_STRIDE
.sp:            push bc
                ld   a, (hl)                   ; kind
                inc  hl
                ld   d, (hl)                   ; room
                inc  hl
                ld   e, (hl)                   ; col
                inc  hl
                ld   c, (hl)                   ; storey
                inc  hl
                ld   b, (hl)                   ; flags
                inc  hl
                push hl
                call spawn_one
                pop  hl
                ld   de, P_ENT_STRIDE
                add  ix, de
                pop  bc
                djnz .sp
                jp   vis_reset                 ; B7b: no stale render slot (lowram)

;------------------------------------------------------------------------------
; level_reset — per-level / per-game transient state + an empty entity table
; (new_game; level_populate keeps the hero's carried fields itself).
; Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
level_reset:
                xor  a
                ld   (POTIONS_TAKEN), a        ; bits index this level's FLOOR_LIST
                ld   (EXIT_KIND), a
                ld   (MSG_Q), a
                ld   (PEND_DMG_COUNT), a
                ld   (YIELD_FLAG), a
                ld   (CLIMB_BLK_N), a          ; B14: no run of blocked climbs
                ld   (pf_prep), a              ; D3-8e2: no cast set up across a level
                ld   hl, $FFFF                 ; no jump refused (game.md §2.4 "not
                ld   (JUMP_TURN), hl           ; two turns in a row")
                ld   hl, P_ENTITIES
                ld   de, P_ENTITIES + 1
                ld   bc, P_MAX_ENT * P_ENT_STRIDE - 1
                ld   (hl), a
                ldir
                ; D3-0: status arrays, slots 1..15 (slot 0 = the hero's,
                ; carried over a descend: HERO_CARRY rule; new_game clears it
                ; through level_reset_new). A = 0. ~1.4k T, once per level.
                ld   hl, ST_FLAGS + 1
                call .st
                ld   l, (ST_T1 + 1) & $FF      ; same page (combat_defs ASSERT)
                call .st
                ld   l, (ST_T2 + 1) & $FF
                call .st
                ld   hl, ST_X + 1
.st:            ld   b, ST_SLOTS - 1
.stl:           ld   (hl), a
                inc  l                         ; one page per array (FONT6_HOLE)
                djnz .stl
                ret

;------------------------------------------------------------------------------
; level_reset_new — new_game: level_reset + the hero's own 3D state (slot 0's
; status bytes, HERO3D: MP regen, resistances, immunity, panel shadows).
; Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
level_reset_new:
                xor  a
                ld   (ST_FLAGS), a
                ld   (ST_T1), a
                ld   (ST_T2), a
                ld   (ST_X), a
                ld   hl, HERO3D
                ld   b, ST_HERO_END - HERO3D   ; D3-7: + the TURN_PEND block; D3-8: + HST_DONE / HELD_T; D3-8e2: + COMBAT_NOT_BEFORE
.z:             ld   (hl), a
                inc  l
                djnz .z
                jr   level_reset

;------------------------------------------------------------------------------
; spawn_one — IX = free slot: A = kind, D = room, E = body-left col, C =
; storey 0/1, B = extra flags (EF_LEFT or 0). Walkers stand on the storey's
; floor (9s+8-h), flyers cruise at 9s+1; HP from the kind, render state reset.
; Clobbers: A, BC, HL.
;------------------------------------------------------------------------------
spawn_one:
                ld   (ix+E_KIND), a
                ld   (ix+E_ROOM), d
                ld   (ix+E_X), e
                ld   a, b
                or   EF_ACTIVE | EF_HOSTILE
                ld   (ix+E_FLAGS), a
                ld   a, c                      ; 9s = 8s + s (MUL_STOREY inlined:
                add  a, a                      ; C already holds s, so the
                add  a, a                      ; macro's ld c,a would be dead)
                add  a, a
                add  a, c
                ld   c, a                      ; 9s
                KFIELD KT_FLAGS
                and  KF_FLYER
                jr   z, .walker
                ld   a, c
                inc  a                         ; flyer cruises at 9s+1
                jr   .sety
.walker:        KFIELD KT_BH
                ld   b, a
                ld   a, c
                add  a, STOREY_AIR
                sub  b                         ; 9s+8-h
.sety:          ld   (ix+E_Y), a
                ; fall through
; init_ent_common — hp/max from the kind, px/py from x/y, render state reset.
init_ent_common:
                KFIELD KT_HP
                ld   (ix+E_HP), a
                ld   (ix+E_MAXHP), a
                call snap_pxpy
                ld   (ix+E_MODE), M_REST
                ld   (ix+E_DFID), $FF
                ret

;==============================================================================
; FOLLOW SELECTION (prototype §3.7). L-RELIEF: the candidate scan
; follow_select, place_follower and arrival_conflicts are bank-7 code now
; (bank7.asm, room exit = cold); the admission half stays here (lp_wt / lp_rec
; are bank-3 data): follow_select far3s follow_admit (PROTO), lp_transition
; calls it directly; it far7s place_follower.
;==============================================================================
;------------------------------------------------------------------------------
; follow_admit — the admission half of follow_select (CAND_LIST / CAND_GAP
; filled): candidates in (gap, slot) order against the destination's
; population (dest_counts) until FOLLOW_MAX: PROTO rooms <= ROOM_CAP alive and
; <= TALL_CAP tall; LP <= ROOM_CAP and sum weight <= LP_SIGMA_CAP (§9.3).
; Admitted -> place_follower. Clobbers: all but IY.
;------------------------------------------------------------------------------
follow_admit:
                call dest_counts               ; TMP3 = alive, TMP4 = tall (LP: sum weight)
                ; --- admit in (gap, slot) order ---
.pick:          ld   a, (FOLLOW_N)
                cp   FOLLOW_MAX
                ret  nc
                ld   b, $FF                    ; best gap
                ld   c, $FF                    ; best slot
                ld   hl, CAND_LIST + 1
                ld   de, CAND_GAP + 1
                ld   a, 1
.pl:            push af
                ld   a, (hl)
                cp   $FF
                jr   z, .pn
                ld   a, (de)
                cp   b
                jr   nc, .pn                   ; not strictly smaller (ties: lower slot)
                ld   b, a
                pop  af
                push af
                ld   c, a
.pn:            inc  hl
                inc  de
                pop  af
                inc  a
                cp   P_MAX_ENT
                jr   c, .pl
                ld   a, c
                cp   $FF
                ret  z                         ; no more candidates
                ; mark processed
                ld   hl, CAND_LIST
                ld   e, a
                ld   d, 0
                add  hl, de
                ld   (hl), $FF
                call ent_ix
                ; caps: alive + 1 <= ROOM_CAP ; tall + 1 <= TALL_CAP (PROTO)
                ; or sum weight + w <= LP_SIGMA_CAP (LP, §9.3)
                ld   a, (TMP3)
                cp   ROOM_CAP
                jr   nc, .pick                 ; rejected, stays
                ld   a, (LVL_DEPTH)
                or   a
                jr   z, .tall
                ld   a, (ix+E_KIND)
                ld   hl, lp_wt
                call hla
                ld   a, (TMP4)
                add  a, (hl)
                cp   LP_SIGMA_CAP + 1
                jr   nc, .pick
                ld   (TMP4), a
                jr   .admit
.tall:          KFIELD KT_FLAGS
                and  KF_TALL
                jr   z, .admit
                ld   a, (TMP4)
                cp   TALL_CAP
                jr   nc, .pick
                inc  a
                ld   (TMP4), a
.admit:         ld   hl, TMP3
                inc  (hl)
                ld   hl, FOLLOW_N
                inc  (hl)
                ld   hl, place_follower        ; L-RELIEF: bank 7 (IX passes in; A, F lost:
                call far7                      ; .pick reloads them)
                jp   .pick                     ; (+3 B of far call: out of jr range)

; dest_counts — TMP3 = active monsters (incl. pending) in EXIT_DEST, TMP4 =
; tall (PROTO) / sum weight (LP: + the residents still in the destination's
; record, the ones lp_enter found no cell for, so a room never exceeds the
; §9.3 cap when they spawn next time).
dest_counts:
                xor  a
                ld   (TMP3), a
                ld   (TMP4), a
                ld   a, 1
.l:             ld   (TMP5), a
                call ent_ix
                ld   a, (ix+E_FLAGS)
                and  EF_ACTIVE | EF_DYING
                cp   EF_ACTIVE
                jr   nz, .n
                ld   a, (EXIT_DEST)
                cp   (ix+E_ROOM)
                jr   nz, .n
                ld   hl, TMP3
                inc  (hl)
                ld   a, (LVL_DEPTH)
                or   a
                ld   a, (ix+E_KIND)
                jr   nz, .w
                KFIELD KT_FLAGS
                and  KF_TALL
                jr   z, .n
                ld   hl, TMP4
                inc  (hl)
.n:             ld   a, (TMP5)
                inc  a
                cp   P_MAX_ENT
                jr   c, .l
                ld   a, (LVL_DEPTH)
                or   a
                ret  z
                ld   a, (EXIT_DEST)            ; LP: + the record's entries
                call lp_rec
                ld   a, (hl)
                and  LR_CNT_MASK
                ret  z
                ld   b, a
                ld   a, (TMP3)
                add  a, b
                ld   (TMP3), a
.r:             inc  hl
                ld   a, (hl)                   ; LE_KIND
                inc  hl
                and  LEK_KIND_MASK
                call .wt
                djnz .r
                ret
.w:             call .wt
                jr   .n
; .wt: A = kind -> TMP4 += lp_wt[kind]. Keeps BC, HL.
.wt:            push hl
                ld   hl, lp_wt
                call hla
                ld   a, (TMP4)
                add  a, (hl)
                ld   (TMP4), a
                pop  hl
                ret

;------------------------------------------------------------------------------
; Spawns (used ONCE at new-game init; slots are the truth afterwards, §3.7).
;   DB kind, room, col, storey, flags(EF_LEFT or 0) ; slot = 1 + index
;------------------------------------------------------------------------------
; B3B-3 (2 storeys): the prototype §8.2 population, storeys mapped PROTO s2 ->
; s1 (bottom: the hero's start / exit storey), s1 -> s0, s0 -> s0. One col
; moved (skeleton C) so the reference route keeps the PROTO shape: the
; skeleton climbs the far shaft while the hero takes potion 2.
;==============================================================================
; proto_level — B3B-8: the PROTO rooms A-D (data.asm map) as a 3B level state
; at LVL_STATE: header (LVL_DEPTH 0 = PROTO: level_load_tiles takes D1's set +
; the chest; D1 colours), EDGE_TAB (A|B door open, D|C closed), the 4 room
; descriptors (RD_SEED 0: build_room_map lays proto_decor instead of calling
; decor_room), FLOOR_LIST = the 4 potions (entry i = PROTO potion id i =
; POTIONS_TAKEN bit i). Until B3B-12 generates real levels for a game.
; Clobbers: A, BC, DE, HL.
;==============================================================================
proto_level:
                ld   hl, LVL_STATE
                ld   de, LVL_STATE + 1
                ld   bc, FLOOR_LIST - LVL_STATE - 1
                ld   (hl), 0
                ldir                           ; header, edges, all 9 descriptors
                ld   hl, FLOOR_LIST
                ld   de, FLOOR_LIST + 1
                ld   bc, FLOOR_MAX * FL_STRIDE - 1
                ld   (hl), FL_EMPTY
                ldir
                ld   hl, proto_hdr             ; header + EDGE_TAB (contiguous)
                ld   de, LVL_STATE
                ld   bc, PROTO_HDR_LEN
                ldir
                ld   de, FLOOR_LIST            ; the potions
                ld   c, PROTO_FLOOR_LEN
                ldir                           ; (HL runs on into proto_rooms)
                ld   a, PROTO_ROOMS
.r:             push af
                ld   a, (hl)                   ; room id
                inc  hl
                push hl
                call room_desc                 ; (bank 2) HL = its descriptor
                ex   de, hl
                pop  hl
                ld   bc, PROTO_DESC_LEN
                ldir
                pop  af
                dec  a
                jr   nz, .r
                ret

proto_hdr:      DB   0                         ; LVL_DEPTH: 0 = PROTO
                DW   0, 0                      ; LVL_SEED, GEN_RNG
                DB   ATTR_FLOOR, ATTR_WALL     ; = D1's (game.md §1.2)
                DB   ROOM_A, ROOM_NONE, ROOM_NONE, ROOM_NONE   ; start, lair, key, sanctum
                DB   PROTO_ROOMS, 0, PROTO_POTIONS             ; NROOMS, FLAGS, FLOOR_N
                DW   0                         ; MASTER_SEED
                DB   EG_LINK | EG_DOOR | EG_OPEN, 0, EG_LINK | EG_DOOR, 0, 0, 0   ; EDGE_TAB
PROTO_HDR_LEN   EQU $ - proto_hdr
                ASSERT PROTO_HDR_LEN == EDGE_TAB + EDGES_H - LVL_STATE
                ASSERT EDGE_TAB == LVL_STATE + LVL_HDR_LEN && EDGE_AB == 0 && EDGE_DC == 2
                ASSERT LVL_ATTR_FLOOR - LVL_STATE == 5 && FLOOR_N - LVL_STATE == 13
proto_floor:    ; FL_ROOM, FL_COL, FL_ITEM, FL_QTY: potion ids 0..3 (all storey 0)
                DB   ROOM_A, 28, IT_POTION, 1
                DB   ROOM_B, 1,  IT_POTION, 1
                DB   ROOM_C, 29, IT_POTION, 1
                DB   ROOM_D, 17, IT_POTION, 1
PROTO_FLOOR_LEN EQU $ - proto_floor
PROTO_POTIONS   EQU PROTO_FLOOR_LEN / FL_STRIDE
proto_rooms:    ; room id, then RD_FLAGS .. RD_BLOCK (seed / spare stay 0)
                DB   ROOM_A, RDF_PRESENT | RDF_START | RDF_DEADEND, RDX_R | RDX_RS1
                DB   0, 0, 0, 0, 5, 23, 0, 0                  ; LAD1 {5,1}, LAD2 {23,1}
                DB   ROOM_B, RDF_PRESENT, RDX_L | RDX_LS1 | RDX_D
                DB   0, 24, 0, 0, 4, 11, PIT_B, 0             ; DN {24,2}; {4,1} {11,1}
                DB   ROOM_C, RDF_PRESENT, RDX_L | RDX_LS1 | RDX_U
                DB   24, 0, 0, 0, 24, 6, 0, 0                 ; UP {24,0}; {24,1} {6,1}
                DB   ROOM_D, RDF_PRESENT | RDF_DEADEND, RDX_R | RDX_RS1
                DB   0, 0, 0, 0, 22, 8, 0, RDB_RIGHT | 3      ; {22,1} {8,1}; block
PROTO_DESC_LEN  EQU RD_BLOCK + 1
PROTO_ROOMS     EQU ($ - proto_rooms) / (PROTO_DESC_LEN + 1)
                ASSERT PROTO_ROOMS == 4 && proto_rooms == proto_floor + PROTO_FLOOR_LEN
                ASSERT proto_floor == proto_hdr + PROTO_HDR_LEN
                ASSERT RD_FLAGS == 0 && RD_BLOCK == 9 && RD_LAD1 == 6 && RD_PITCOL == 8
; PROTO decor (seed-0 rooms only): room, tile, col, row; $FF ends
proto_decor:    DB   $FF                       ; (empty: B3B-13 dropped the room-D chest, DEC1 the room-A torch)

HERO_START_COL  EQU 2
HERO_START_S    EQU 1
spawn_tab:
                DB K_RAT,      ROOM_A, 16, 1, EF_LEFT
                DB K_SLIME,    ROOM_A, 14, 0, EF_LEFT
                DB K_GOBLIN,   ROOM_B, 16, 1, EF_LEFT
                DB K_BAT,      ROOM_B, 18, 0, EF_LEFT
                DB K_SKELETON, ROOM_C, 12, 1, EF_LEFT  ; col 16 -> 12: its nearest
                                                       ; climb is {6,1}, away from the
                                                       ; hero's arrival shaft {24,0}/{24,1}
                DB K_GHOST,    ROOM_C, 12, 0, EF_LEFT
                DB K_SKELETON, ROOM_D, 12, 0, EF_LEFT
                DB K_BAT,      ROOM_D, 12, 1, EF_LEFT
SPAWN_COUNT     EQU ($ - spawn_tab) / 5

;==============================================================================
; LEVEL ENTRY, bank-3 part (B3B-12; the low-RAM driver is level_enter in
; lowram.asm, which pages tiles / screens around these far3 calls).
;==============================================================================
; level_card: bank 1 since C3-6 (menu1.asm, menu font).

;------------------------------------------------------------------------------
; level_new — A = depth 1..8: LVL_SEED = MASTER_SEED + depth * LVL_SEED_MUL
; (level_defs.asm: why additive), level_gen until it succeeds (B = 1 + CF:
; 16 reseeds exhausted, LVL_SEED already advanced by 16 -> just call again;
; D8 seeds 55352..55354 exhaust once; at most 2 calls: the longest run of
; failing seeds is 18 < 32, tools/levelgen_runs.py), then level_populate
; (hero + the LP budget, game.md §9.4.1). LG_* scratch = GEN_SCRATCH: called
; only before the first room is built (level_enter). No gen_kind here: every
; kind of lp_dtab (stand-in aliases included) is in the boot pool (3F's
; per-level pool from LP_KINDS + LP_BOSS goes between level_gen and the
; build, after alloc_restore). Pages nothing.
; Clobbers: all but IY.   level_gen ~0.1-0.6M T per call (W16 reports)
;------------------------------------------------------------------------------
level_new:
                ld   (LVL_DEPTH), a
                ld   b, a
                ld   hl, (MASTER_SEED)
                ld   de, LVL_SEED_MUL
.m:             add  hl, de                    ; + depth * MUL (16-bit wrap)
                djnz .m
                ld   (LVL_SEED), hl
.g:             ld   a, (LVL_DEPTH)
                call level_gen                 ; B = 0 ok / 1 exhausted
                dec  b
                jr   z, .g                     ; 1 -> retry from LVL_SEED + 16
                ; fall through
;------------------------------------------------------------------------------
; level_populate — the hero into an emptied entity table, then the LP level
; budget (lp_budget: game.md §9.4.1, replaces the B3B-12 stand-in table) and
; the start room's entry (lp_enter: quota 0, so no monster; record VISITED,
; ROOM_VISITS = 1). Monsters spawn when the hero enters their room (do_exit
; -> lp_transition). Hero (slot 0): kind / HP / MAXHP / potions / facing
; carried over, room = LVL_START, x = level_start_x, standing on storey 0
; (game.md §1.1 gaps (4)), CUR_ROOM = LVL_START. Clobbers: all but IY.
;------------------------------------------------------------------------------
; Hero E_FLAGS bits carried over a descend (everything else is rebuilt:
; ACTIVE | PLAYER set, DYING / WALKIN / PENDING dropped). D3-0: the hero's
; status (ST_FLAGS / ST_T1 / ST_T2 / ST_X slot 0, combat_defs.asm) and
; HERO3D carry by not being touched: level_reset clears slots 1..15 only.
HERO_CARRY      EQU EF_LEFT
level_populate:
                ld   ix, P_ENTITIES
                ld   l, (ix+E_HP)
                ld   h, (ix+E_MAXHP)
                push hl
                ld   b, (ix+E_POT)
                ld   a, (ix+E_FLAGS)
                and  HERO_CARRY                ; flags that survive a descend
                ld   c, a
                push bc
                call level_reset
                call level_start_x             ; A = col (clobbers IX)
                ld   ix, P_ENTITIES
                ld   (ix+E_X), a
                ld   a, (LVL_START)
                ld   (CUR_ROOM), a
                ld   (ix+E_ROOM), a
                ld   a, (HERO_KIND)
                ld   (ix+E_KIND), a
                pop  bc
                ld   (ix+E_POT), b
                ld   a, c
                or   EF_ACTIVE | EF_PLAYER
                ld   (ix+E_FLAGS), a
                KFIELD KT_BH
                ld   b, a
                ld   a, FLOOR_ROW0             ; storey 0: 8 - h
                sub  b
                ld   (ix+E_Y), a
                call init_ent_common
                pop  hl
                ld   (ix+E_HP), l
                ld   (ix+E_MAXHP), h
                ; --- monsters: LP (game.md §9.4.1 / §9.4.3) ---
                call lp_budget                 ; the per-room quotas (LG_* still valid)
                ld   ix, P_ENTITIES            ; lp_budget clobbers IX (bfs walks LG_Q
                                               ; with it): without this reload LP_HX /
                                               ; LP_HW were garbage and lp_cmap's gap
                                               ; zone ORed LPC_BODY into TILE_GLYPHS
                                               ; (fix/3d-artefacts, lp.py LP-HX)
                ld   a, (ix+E_X)               ; the start room = an entry: hero on
                ld   (LP_HX), a                ; storey 0 at its start col (quota 0:
                xor  a                         ; nothing spawns; the record becomes
                ld   (LP_HS), a                ; VISITED, ROOM_VISITS = 1)
                KFIELD KT_BW
                ld   (LP_HW), a
                ld   a, (LVL_START)
                call lp_enter
                ld   a, (LVL_START)
                ld   hl, ROOM_VISITS
                call hla
                inc  (hl)
                ret

                INCLUDE "levelgen.asm"          ; B3B-7: level_gen, level_start_x
                INCLUDE "lpop3.asm"             ; LP: lazy monster population (game.md §9.4)

; glow_ids — B12: the per-level GLOW tile id (tileset_ids.inc), by depth - 1;
; build_room_map stamps it above the middle cell of the open level exit.
glow_ids:       DB   TS1_GLOW_F1_R0C0, TS2_GLOW_F1_R0C0, TS3_GLOW_F1_R0C0, TS4_GLOW_F1_R0C0
                DB   TS5_GLOW_F1_R0C0, TS6_GLOW_F1_R0C0, TS7_GLOW_F1_R0C0, TS8_GLOW_F1_R0C0
                ASSERT $ - glow_ids == LEVELS

;==============================================================================
; build_room_map — B3B-8 v2 (plan D7; game.md §1.1 / §2.1 / §2.5 / §3.3 /
; §1.4, concept-screen §3.1): the tile map of room A (0..8) from ROOM_DESC +
; EDGE_TAB + FLOOR_LIST (+ LVL_FLAGS for the grate) into the map at page D
; (ROOM_MAP / NEXT_MAP >> 8). Entered via far3 (lowram `build_room` keeps the
; A / H signature for do_exit and room_show). Pages nothing.
; Overwrites GEN_SCRATCH (aliases both maps): the ZX0 cache GEN_ZBLK is dropped.
;   base     cols 0 / 31 wall (WALLF in the floor rows 8 / 17), the rest AIR /
;            PLAT (row 17 stays logical PLATFORM: orn_cells draws its ornament)
;   exits    L / R: that storey's air rows opened in col 0 / 31; a door edge
;            (EDGE_TAB, index from the room id) = lintel WALL row 9s, arch 9s+1,
;            planks 9s+2..9s+7 (closed / LOCK plank if locked or sealed / the
;            open-door jambs, B10)
;   pit      row 8: T_PIT_L p-1, AIR p..p+W-1, T_PIT_R p+W (W = L2_PITW: the
;            L2 wide pit, 4..6; 0 = the narrow 3). Storey 1 below is plain floor
;   block    RD_BLOCK: w cols WALL (WALLF floor row), RUBBLE at its foot
;   mid      L2_MIDB (L2 mid-room block, storey 0): cols b..b+w-1 as a block,
;            RUBBLE at both feet (row 7, cols b-1 and b+w)
;   segments the 6 col bytes RD_UPCOL..RD_LAD2 as {c,s} (seg_storey): ladder
;            rows 9s-1..9s+7 clipped; row 8 = HOLE + T_END_R / T_END_L caps on
;            the platform either side; row 17 = HOLE, no caps (the ornament
;            runs to the hole). ARR: + RUBBLE over the shaft in row 0 (no exit
;            up, game.md §1.1). EXIT: the level exit; closed (LF_GRATE_OPEN = 0,
;            3F) T_GRATE_SHUT over it before the deriver
;   potions  FLOOR_LIST entries of this room (IT_POTION) -> T_POTION, row 9s+7;
;            D3-7 T6: IT_DAGGER / IT_ARROW -> T_DAGGERS / T_ARROWS the same way
;   decor    RD_SEED != 0: decor_room (B3B-9); seed 0 (PROTO): proto_decor.
;            The animated cells go to ANIM_N/ANIM_LIST (ROOM_MAP) or
;            ANIM_N2/ANIM_LIST2 (NEXT_MAP: do_exit's room_shadow copies it
;            after the scroll); the list is emptied first (PROTO: stays 0)
;   gate     B12, after the deriver, open grate only (always in 3B): T_GRATE
;            (raised, LADDER|HOLE) over the 3 exit cells + glow_ids[depth] on
;            row 16 above the middle one if T_AIR
; Clobbers: A, BC, DE, HL (IX, IY kept).   45.4k T worst (measured, DI, contended: W11 / W12M)
;==============================================================================
build_room_map:
                push ix
                ld   (TMP0), a                 ; room
                ld   a, d
                ld   (TMP1), a                 ; map page (map_cell)
                cp   ROOM_MAP >> 8             ; B3B-9 review: the decor list of this map
                ld   a, ANIM_N & $FF           ; (ROOM_MAP -> ANIM_N, NEXT_MAP -> ANIM_N2),
                jr   z, .an                    ; emptied for every build (PROTO seed 0
                ld   a, ANIM_N2 & $FF          ; rooms keep it empty)
.an:            ld   (dg_dst), a
                ld   l, a
                ld   h, ANIM_N >> 8
                ld   (hl), 0
                ld   hl, 0
                ld   (GEN_ZBLK), hl            ; GEN_SCRATCH is about to be overwritten
                ld   a, (TMP0)
                call room_desc                 ; (bank 2) A, HL
                push hl
                pop  ix                        ; IX = descriptor
                ; base fill, rows 0..17 (the map rows are contiguous, 32 B each)
                ld   h, d
                ld   l, 0
                ld   b, 0                      ; row
.r:             ld   de, (T_BRICK << 8) | T_AIR
                ld   a, b
                cp   FLOOR_ROW0
                jr   z, .fl
                cp   FLOOR_ROW1
                jr   nz, .air
.fl:            ld   de, (T_WALLF << 8) | T_PLAT
.air:           ld   (hl), d                   ; col 0
                inc  hl
                ld   c, ROOM_COLS - 2
.c:             ld   (hl), e
                inc  hl
                dec  c
                jr   nz, .c
                ld   (hl), d                   ; col 31
                inc  hl
                inc  b
                ld   a, b
                cp   PLAY_ROWS
                jr   nz, .r
                ; horizontal exits + doors
                ld   bc, 0                     ; C = col 0
                ld   e, RDX_L
                call .side
                ld   c, ROOM_COLS - 1
                ld   e, RDX_R
                call .side
                ; pit, block
                ld   a, (ix+RD_PITCOL)
                or   a
                call nz, .pit
                ld   a, (ix+RD_BLOCK)
                call .block
                ld   a, (ix+L2_MIDB)
                or   a
                call nz, .mid
                ; shafts and ladders: RD_UPCOL .. RD_LAD2 as {c, s}
                push ix
                pop  hl
                inc  l                         ; -> RD_EXITS; the loop pre-increments
.sg:            inc  l
                ld   a, l
                and  RD_STRIDE - 1
                cp   RD_LAD2 + 1
                jr   nc, .sgd
                push hl
                call seg_storey                ; (bank 2) A = s
                ld   e, a
                ld   a, (hl)
                call .lad
                pop  hl
                jr   .sg
.sgd:           ld   a, (ix+RD_ARRCOL)         ; arrival shaft: rubble-capped (row 0)
                ld   d, T_RUBBLE
                ld   b, 0
                call .three
                ld   a, (LVL_FLAGS)            ; level exit, CLOSED grate (3F; 3B never):
                and  LF_GRATE_OPEN             ; drawn before the deriver as before. The
                jr   nz, .pots                 ; open gate is stamped after it (.gate)
                ld   a, (ix+RD_EXITCOL)
                ld   d, T_GRATE_SHUT           ; TODO 3F: own closed id (level_defs.asm)
                ld   b, FLOOR_ROW1
                call .three
.pots:          ; potions (3B stand-in: floor tiles, game.md §1.4)
                ld   hl, FLOOR_LIST
                ld   b, FLOOR_MAX
.pt:            ld   a, (hl)                   ; FL_ROOM ($FF & $0F = 15: never a room)
                and  FL_ROOM_MASK
                ld   c, a
                ld   a, (TMP0)
                cp   c
                jr   nz, .pn
                inc  l
                inc  l
                ld   a, (hl)                   ; FL_ITEM
                dec  l
                ld   c, (hl)                   ; FL_COL
                dec  l
                ld   e, T_POTION
                cp   IT_POTION
                jr   z, .pi
                sub  IT_DAGGER                 ; D3-7 T6: ammo stacks -> T_DAGGERS / T_ARROWS
                cp   IT_ARROW - IT_DAGGER + 1
                jr   nc, .pn
                add  a, T_DAGGERS
                ld   e, a
.pi:            push hl
                push bc
                ld   a, (hl)
                rlca                           ; FL_S1 -> bit 0
                and  1
                call storey_row                ; (bank 2) A = 9s+7, keeps BC, DE
                ld   b, a
                call map_cell
                ld   (hl), e                   ; (list order: the last live entry of a cell shows)
                pop  bc
                pop  hl
.pn:            ld   a, l
                add  a, FL_STRIDE
                ld   l, a
                djnz .pt
                ; decor
                ld   a, (ix+RD_SEED)
                or   (ix+RD_SEED + 1)
                jr   z, .proto
                ld   a, (TMP0)
                call decor_room                ; B3B-9 (IX = descriptor)
                ; B12 (concept-screen B3B-8 #4): the OPEN level exit = the raised gate
                ; T_GRATE over its 3 hole cells + the depth's GLOW on the standing row
                ; above the middle cell if that is still T_AIR. After the deriver, so its
                ; ring rule still saw HOLE_* there: the decor stays byte-identical to
                ; before (and nothing is ever placed beside / above the exit).
.gate:          ld   a, (LVL_FLAGS)            ; (PROTO rooms come here too: no exit)
                and  LF_GRATE_OPEN
                jr   z, .x
                ld   a, (ix+RD_EXITCOL)        ; 0 = not the lair (.three: none)
                ld   d, T_GRATE
                ld   b, FLOOR_ROW1
                call .three                    ; HL = the right cell (col c+2)
                jr   z, .x                     ; (Z from .three's or a: no exit)
                ld   de, -(ROOM_COLS + 1)      ; -> row 16, col c+1
                add  hl, de
                ld   a, (hl)
                or   a                         ; T_AIR only (decor / potion: no glow)
                jr   nz, .x
                ex   de, hl
                ld   a, (LVL_DEPTH)            ; 1..8 (a lair exists only on D1..D8)
                ld   hl, glow_ids - 1
                call hla
                ld   a, (hl)
                ld   (de), a
                pop  ix
                ret
                ASSERT T_AIR == 0
.proto:         ld   hl, proto_decor           ; seed 0: the PROTO rooms' list
.pd:            ld   a, (hl)
                cp   $FF
                jr   z, .gate
                ld   d, a                      ; room
                inc  hl
                ld   e, (hl)                   ; tile
                inc  hl
                ld   c, (hl)                   ; col
                inc  hl
                ld   b, (hl)                   ; row
                inc  hl
                ld   a, (TMP0)
                cp   d
                jr   nz, .pd
                push hl
                call map_cell
                ld   (hl), e
                pop  hl
                jr   .pd
.x:             pop  ix
                ret
                ASSERT FL_ROOM == 0 && FL_COL == 1 && FL_ITEM == 2 && FL_S1 == $80
                ASSERT (FLOOR_LIST & $FF) == 0 && FLOOR_MAX * FL_STRIDE <= 256
                ASSERT (FL_EMPTY & FL_ROOM_MASK) >= GRID_CELLS

.three:         ; A = left col (0: none -> Z), B = row, D = tile: 3 cells; drawn ->
                ; NZ (map_cell's `or c`, C >= 1) and HL = the 3rd cell (B12 .gate)
                or   a
                ret  z
                ld   c, a
                call map_cell
                ld   (hl), d
                inc  hl
                ld   (hl), d
                inc  hl
                ld   (hl), d
                ret

.side:          ; E = RDX_L / RDX_R, C = edge col 0 / 31
                ld   a, (ix+RD_EXITS)
                and  e
                ret  z
                ld   a, e
                add  a, a
                add  a, a
                add  a, a
                add  a, a                      ; -> RDX_LS1 / RDX_RS1
                and  (ix+RD_EXITS)
                jr   z, .s0
                ld   a, 1
.s0:            MUL_STOREY b                   ; A = 9s
                ld   b, a
                push bc
                ld   d, STOREY_AIR
.o:             call map_cell
                ld   (hl), T_AIR
                inc  b
                dec  d
                jr   nz, .o
                pop  bc                        ; B = 9s, C = edge col
                ld   a, (TMP0)                 ; edge index: right edge of m =
                bit  RDX_L_BIT, e              ; m - m div 3, m = r (R) / r-1 (L)
                jr   z, .em
                dec  a
.em:            ld   l, a
.eg:            sub  GRID_W
                jr   c, .ex
                dec  l
                jr   .eg
.ex:            ld   a, l
                add  a, EDGE_TAB & $FF
                ld   l, a
                ld   h, EDGE_TAB >> 8
                ld   a, (hl)                   ; edge state
                bit  EG_DOOR_BIT, a
                ret  z                         ; open passage: no door cells
                ld   e, a
                ld   a, c
                or   a
                jr   z, .dc
                dec  a                         ; right door: cols 30-31
.dc:            ld   c, a
                call map_cell                  ; lintel, row 9s
                ld   (hl), T_BRICK
                inc  hl
                ld   (hl), T_BRICK
                inc  b
                call map_cell                  ; arch, row 9s+1
                ld   (hl), T_DOOR_ARCH_L
                inc  hl
                ld   (hl), T_DOOR_ARCH_R
                ld   a, e
                ld   de, (T_DOOR_JAMB_L << 8) | T_DOOR_JAMB_R   ; open (B10)
                bit  EG_OPEN_BIT, a
                jr   nz, .dk
                ld   de, (T_DOOR_L << 8) | T_DOOR_R
                and  EG_LOCK | EG_SEAL
                jr   z, .dk
                ld   e, T_DOOR_LOCK
.dk:            ld   a, DOOR_PLANK_H
.dp:            inc  b                         ; planks, rows 9s+2 .. 9s+7
                push af
                call map_cell
                ld   (hl), d
                inc  hl
                ld   (hl), e
                pop  af
                dec  a
                jr   nz, .dp
                ret
                ASSERT DOOR_ARCH_DY == 1 && DOOR_PLANK_DY == 2 && DOOR_COLS == 2
                ASSERT RDX_LS1 == RDX_L << 4 && RDX_RS1 == RDX_R << 4

.pit:           ; A = p (game.md §2.5, §1.1 "Wide pit"): row 8, cap T_PIT_L at
                ; p-1, holes p..p+W-1 AIR, cap T_PIT_R at p+W
                dec  a
                ld   c, a
                ld   b, FLOOR_ROW0
                call map_cell
                ld   (hl), T_PIT_L
                ld   a, (ix+L2_PITW)
                or   a
                jr   nz, .pw
                ld   a, PIT_W_NARROW
.pw:            ld   b, a
.ph:            inc  hl
                ld   (hl), T_AIR
                djnz .ph
                inc  hl
                ld   (hl), T_PIT_R
                ret
                ASSERT PIT_W_NARROW == FEAT_W

.mid:           ; A = b (game.md §1.1 "Mid-room block"): storey 0, cols b..b+w-1
                ; rows 0..7 WALL, row 8 WALLF (.wall), RUBBLE at row 7 cols b-1
                ; and b+w
                ld   c, a
                ld   d, (ix+L2_MIDW)
                ld   b, 0
                call .wall                     ; B = row 7
                dec  c
                call map_cell
                ld   (hl), T_RUBBLE
                ld   a, d
                inc  a
                call hla                       ; -> col b+w
                ld   (hl), T_RUBBLE
                ret

.block:         ; A = RD_BLOCK: w cols at the left / right edge of storey s,
                ; rows 9s..9s+7 WALL, floor row WALLF, RUBBLE at its foot (row
                ; 9s+7, col w / 31-w)
                ld   e, a
                and  RDB_WMASK
                ret  z
                ld   d, a                      ; D = w
                ld   c, 0
                bit  RDB_RIGHT_BIT, e
                jr   z, .bl
                ld   a, ROOM_COLS
                sub  d
                ld   c, a                      ; 32 - w
.bl:            xor  a
                bit  RDB_S1_BIT, e
                jr   z, .bs
                ld   a, STOREY_ROWS
.bs:            ld   b, a                      ; 9s
                call .wall                     ; B = row 9s+7
                ld   a, c
                or   a
                ld   a, d                      ; left: col w
                jr   z, .rc
                ld   a, c
                dec  a                         ; right: col 31-w
.rc:            ld   c, a
                call map_cell
                ld   (hl), T_RUBBLE
                ret

.wall:          ; B = 9s, C = left col, D = w: rows 9s..9s+7 WALL, the floor row
                ; 9s+8 WALLF (edge and mid blocks). Out: B = 9s+7; C, D kept
                ld   e, STOREY_ROWS            ; 8 air rows + the floor row
.br:            call map_cell
                ld   a, e
                dec  a
                ld   a, T_BRICK
                jr   nz, .bt
                ld   a, T_WALLF
.bt:            push bc
                ld   b, d
.bc:            ld   (hl), a
                inc  hl
                djnz .bc
                pop  bc
                inc  b
                dec  e
                jr   nz, .br
                dec  b
                dec  b                         ; row 9s+7
                ret

.lad:           ; A = col (0: none), E = s: {c,s} rows 9s-1 .. 9s+7 clipped
                or   a
                ret  z
                ld   c, a
                ld   a, e
                MUL_STOREY b                   ; 9s
                dec  a                         ; 9s-1 ($FF for s = 0)
                ld   b, a
                ld   e, STOREY_ROWS
.lr:            ld   a, b
                cp   PLAY_ROWS                 ; $FF / > 17: clipped
                jr   nc, .lskip
                call map_cell
                ld   a, b
                cp   FLOOR_ROW1
                ld   a, T_HOLE_L               ; row 17: hole, no caps
                jr   z, .la
                ld   a, b
                cp   FLOOR_ROW0
                ld   a, T_LAD_L
                jr   nz, .la
                dec  hl                        ; row 8: caps on the platform
                ld   a, (hl)                   ; cells either side of the hole
                cp   T_PLAT
                jr   nz, .nc1
                ld   (hl), T_END_R             ; platform ends at the hole's left
.nc1:           inc  hl
                inc  hl
                inc  hl
                inc  hl
                ld   a, (hl)
                cp   T_PLAT
                jr   nz, .nc2
                ld   (hl), T_END_L             ; platform resumes at its right
.nc2:           dec  hl
                dec  hl
                dec  hl
                ld   a, T_HOLE_L
.la:            ld   (hl), a
                inc  hl
                inc  a
                ld   (hl), a
                inc  hl
                inc  a
                ld   (hl), a
.lskip:         inc  b
                dec  e
                jr   nz, .lr
                ret
                ASSERT T_LAD_M == T_LAD_L + 1 && T_LAD_R == T_LAD_L + 2
                ASSERT T_HOLE_M == T_HOLE_L + 1 && T_HOLE_R == T_HOLE_L + 2

;==============================================================================
; decor_room — B3B-9 (src/decor_gen.asm). build_room_map calls it for a
; seeded room (RD_SEED != 0) once every structural cell is placed: A = room,
; IX = its descriptor, (TMP1) = the map page (map_cell). Contract: re-derive
; everything from RD_SEED (re-entry must rebuild the identical map, W12);
; game.md §1.2 "Solidity of decor" + concept-screen §3.3 (never in floor rows
; or on door / arch / lintel / ladder / pit / cap / rubble cells; wall-set ids
; only on solid wall cells, others only on non-solid ones); fill ANIM_LIST
; into the list chosen by the map page (dg_dst, set + zeroed by
; build_room_map: ROOM_MAP -> ANIM_N, NEXT_MAP -> ANIM_N2). Keep IX.
;==============================================================================
decor_room:
                INCLUDE "decor_gen.asm"         ; B3B-9: the deriver (code from the label on)

; init_tiles: bank 7 since MEM-SND, the boot block since 3E-T1 (boot6.asm boot6_tiles).
; (cold tile data: B3B-11b moved it to main.asm vdata, read via copy_virt3)
                INCLUDE "panel.asm"            ; B3B-11 panel engine (cold part + the HOT_COPY image)
                INCLUDE "turn3.asm"            ; B3B-R2 turn logic: monster phase, attacks, potions
                INCLUDE "combat3.asm"          ; D3-6a: hit_roll, deal_hit (shared damage core)
                INCLUDE "proj3.asm"            ; D3-6b: proj_fire (projectile logic at cast time)
                INCLUDE "rank3.asm"            ; D3-7: abil_load (ABIL_DESC for the bank-7 ability code)
                INCLUDE "icons3.asm"           ; C3-3 icon bar state + drawing
