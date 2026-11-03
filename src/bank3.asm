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
; L = kind * 8). Reserved here, zero = no resistance / immunity, 0 XP, DEF 0;
; D3-1: combat_data3.asm defines kx_tab here (+ the other combat tables).
;------------------------------------------------------------------------------
                INCLUDE "combat_data3.asm"    ; D3-1: kx_tab rows + XP / level-up / ability tables
                ASSERT (kx_tab & $FF) + KX_LEN <= 256

; sel_run (the PROTO hero select): replaced by the C3-6 menu (menu1.asm, bank 1).

; TRANSITION SCROLLS: bank 1 since the C3-3 review (scroll1.asm, far1).

;==============================================================================
; A7 review: cold game-state code moved out of bank 2 (bank-2 headroom for
; Stage-3 hot code): new_game (bank 7 since MEM-SND; init_ent_common,
; D3-11: the PROTO rooms are the test fixture proto_fix.asm), the follower
; admission (L-RELIEF: the candidate scan, place_follower and the arrival
; conflicts are bank 7 now). None of it pages $C000 (only bank-2 queries +
; vis_reset in bank-5 low RAM).
;==============================================================================

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
                ld   b, MP_PER - HERO3D        ; D3-7: + the TURN_PEND block; D3-8: + HST_DONE / HELD_T; D3-8e2: + COMBAT_NOT_BEFORE;
                                               ; 3E-T8: + PAGE_* + GEAR_MP (hero_recalc's delta base)
.z:             ld   (hl), a
                inc  l
                djnz .z
                ld   (WEAR_PEND), a            ; 3F-T6: a stale wear line would print at the first end_turn
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
                KFL    KT_FLAGS
                and  KF_FLYER
                jr   z, .walker
                ld   a, c
                inc  a                         ; flyer cruises at 9s+1
                jr   .sety
.walker:        KFL    KT_BH
                ld   b, a
                ld   a, c
                add  a, STOREY_AIR
                sub  b                         ; 9s+8-h
.sety:          ld   (ix+E_Y), a
                ; fall through
; init_ent_common — hp/max from the kind, px/py from x/y, render state reset.
init_ent_common:
                KFL    KT_HP
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
                or   (ix+E_GOLD)               ; 3F-T5: a golden follower weighs +1
                call kind_wt
                ld   hl, TMP4
                add  a, (hl)
                cp   LP_SIGMA_CAP + 1
                jr   nc, .pick
                ld   (TMP4), a
                jr   .admit
.tall:          KFL    KT_FLAGS
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
                call place_follower            ; (3F-T8 review: bank 3 again; .pick reloads A)
                jp   .pick                     ; (+3 B of far call: out of jr range)

; place_follower — IX = admitted follower: room <- dest, PENDING, entry spot.
; (3F-T8 review: back in bank 3 from bank 7 — bank-7 relief; a plain call from follow_admit.)
; Clobbers: A, BC.
place_follower:
                ld   a, (ix+E_RCD)             ; 3F-T7: cooldown counter 1 on arrival (stored XOR 1);
                and  RCD_KEEP                  ; 3F-T9: the summon counter / summon-made / once bits stay
                ld   (ix+E_RCD), a
                ld   a, (EXIT_DEST)
                ld   (ix+E_ROOM), a
                set  EF_PENDING_BIT, (ix+E_FLAGS)
                ld   a, (EXIT_KIND)
                cp   EX_UP
                jr   nc, .vert
                ; horizontal: x = 1 (arrive at left edge) or 31-w; face in
                cp   EX_RIGHT
                jr   nz, .fromleft
                ld   (ix+E_X), 1
                res  EF_LEFT_BIT, (ix+E_FLAGS)
                jr   .hy
.fromleft:      KFL    KT_BW
                ld   b, a
                ld   a, ROOM_COLS - 1
                sub  b
                ld   (ix+E_X), a
                set  EF_LEFT_BIT, (ix+E_FLAGS)
.hy:            set  EF_WALKIN_BIT, (ix+E_FLAGS)
                KFL    KT_FLAGS
                and  KF_FLYER
                ret  nz                        ; flyers keep their band offset (same s)
                ld   a, (EXIT_STOREY)
                jr   .stand
.vert:          ld   a, (EXIT_COL)
                ld   (ix+E_X), a
                ld   a, (EXIT_KIND)
                cp   EX_UP
                ld   a, STOREY_COUNT - 1       ; going up: arrive on the bottom storey
                jr   z, .stand
                xor  a                         ; going down: storey 0
.stand:         MUL_STOREY b
                add  a, STOREY_AIR             ; 9s+8
                ld   b, a
                KFL    KT_BH
                ld   c, a
                ld   a, b
                sub  c
                ld   (ix+E_Y), a
                ret


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
                KFL    KT_FLAGS
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
                ld   a, (hl)                   ; LE_KIND (| LEK_GOLD)
                inc  hl
                call .wt
                djnz .r
                ret
.w:             or   (ix+E_GOLD)               ; A = E_KIND here
                call .wt
                jr   .n
; .wt: A = kind byte (row | LEK_GOLD) -> TMP4 += its weight. Keeps BC, HL.
.wt:            push hl
                call kind_wt
                ld   hl, TMP4
                add  a, (hl)
                ld   (TMP4), a
                pop  hl
                ret
; kind_wt: A = kind byte (row | LEK_*) -> A = lp_wt[row] + 1 if LEK_GOLD (3F-T5, levelgen k3_weight). Clobbers HL.
kind_wt:        push af
                and  LEK_KIND_MASK
                ld   hl, lp_wt
                call hla
                ld   a, (hl)
                pop  hl                        ; H = the kind byte
                bit  LEK_GOLD_BIT, h
                ret  z
                inc  a
                ret

; D3-11: the PROTO rooms A-D (proto_level, the room / potion data and spawn_tab) left
; the image: they are the test fixture src/proto_fix.asm (tests/game_lib.py pokes it).
HERO_START_COL  EQU 2
HERO_START_S    EQU 1

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
; only before the first room is built (level_enter). No gen_kind here: the
; 3F-T1 level pool (LP_KINDS + LP_BOSS, low-RAM level_enter) is generated
; after this returns, before the build. 3E-T6: then the items overlay (items_ovl.asm,
; ovl_run: unpacks from BANK_OVL_ITEMS, back in this bank).
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
                call level_populate
                ; 3E-T6: items + traps (+ at D1 = a new game the light-ID shuffle):
                ; the overlay runs with this bank paged (it calls rnd / hits / rdp)
                ld   hl, ovl_items_zx0
                ld   de, ITEMS_ORG
                ld   c, BANK_OVL_ITEMS
                jp   ovl_run
;------------------------------------------------------------------------------
; level_populate — the hero into an emptied entity table, then the LP level
; budget (lp_budget: game.md §9.4.1, replaces the B3B-12 stand-in table) and
; the start room's entry (lp_enter: quota 0, so no monster; record VISITED,
; ROOM_VISITS = 1). Monsters spawn when the hero enters their room (do_exit
; -> lp_transition). Hero (slot 0): kind / HP / MAXHP / facing (E_POT: pot_sync)
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
                ld   hl, pot_sync              ; 3E-T11: E_POT = the bag's potions (was a carry);
                call far6                      ; R6 (keeps DE, IX; HL / BC clobbered, popped next)
                pop  bc
                ld   a, c
                or   EF_ACTIVE | EF_PLAYER
                ld   (ix+E_FLAGS), a
                KFL    KT_BH
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
                KFL    KT_BW
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
;            up, game.md §1.1). EXIT: the level exit (row 17 = HOLE here; its
;            gate is stamped after the deriver, below)
;   items    FLOOR1: every live FLOOR_LIST entry of this room -> T_ITEM0 + k on its
;            2x2 cells (c..c+1, rows 9s+6..9s+7); the icon is drawn after the
;            map draw (fi_cells, from the R6 fi_full glyph cache)
;   decor    RD_SEED != 0: decor_room (B3B-9); seed 0 (PROTO): none.
;            The animated cells go to ANIM_N/ANIM_LIST (ROOM_MAP) or
;            ANIM_N2/ANIM_LIST2 (NEXT_MAP: do_exit's room_shadow copies it
;            after the scroll); the list is emptied first (PROTO: stays 0)
;   gate     B12 / 3F-T8, after the deriver: shut (LF_GRATE_OPEN = 0, the boss
;            lives) T_GRATE_SHUT x 3; open: T_GRATE (raised, LADDER|HOLE) over the
;            3 exit cells + glow_ids[depth] on row 16 above the middle one if T_AIR
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
.pots:          ; FLOOR1 floor items: the T_ITEM0 + k markers over each live entry's 2x2 cells
                ld   hl, FLOOR_LIST
                ld   b, FLOOR_MAX
.pt:            ld   a, (hl)                   ; FL_ROOM ($FF & $0F = 15: never a room)
                and  FL_ROOM_MASK
                ld   c, a
                ld   a, (TMP0)
                cp   c
                jr   nz, .pn
                push hl
                push bc
                inc  l
                ld   c, (hl)                   ; FL_COL
                dec  l
                ld   a, (hl)
                rlca                           ; FL_S1 -> bit 0
                and  1
                ld   e, a                      ; E = s
                call storey_row                ; (bank 2) A = 9s+7, keeps BC, DE
                dec  a
                ld   b, a                      ; B = 9s+6, the item's top row
                call map_cell
                ld   a, e
                add  a, a
                add  a, T_ITEM0                ; band row 2s: the upper marker
                ld   (hl), a
                inc  l
                ld   (hl), a
                inc  a                         ; 2s + 1: the lower one
                ld   de, ROOM_COLS - 1
                add  hl, de
                ld   (hl), a
                inc  l
                ld   (hl), a
                pop  bc
                pop  hl
.pn:            ld   a, l
                add  a, FL_STRIDE
                ld   l, a
                djnz .pt
                ; 3E-T16 known unspent traps (game.md §1.5): T_TRAP in their
                ; standing-row cell, before the deriver (decor needs T_AIR: a
                ; known trap overrides decor), and its type attr into
                ; TILE_ATTRS[T_TRAP] (<= 1 trap a room; the draw that follows
                ; reads it). All TRAP_MAX entries: unused ones are 0 (never known).
                ld   hl, TRAP_LIST
.tr:            ld   a, (TMP0)
                xor  (hl)
                and  TRF_ROOM_MASK | TRF_KNOWN | TRF_SPENT
                cp   TRF_KNOWN                 ; this room, known, not spent
                jr   nz, .tn
                push hl
                ld   a, (hl)
                and  TRF_S1
                rrca
                rrca
                rrca
                rrca                           ; s
                call storey_row                ; (bank 2) A = 9s+7
                ld   b, a
                inc  l
                ld   a, (hl)
                and  TR_COL_MASK
                ld   c, a
                xor  (hl)                      ; the type << 5
                rlca
                rlca
                rlca
                add  a, tr_ink3 & $FF
                ld   e, a
                adc  a, tr_ink3 >> 8
                sub  e
                ld   d, a
                call map_cell
                ld   a, (hl)
                or   a
                jr   nz, .tk                   ; an item there: it shows (never generated)
                ld   (hl), T_TRAP
                ld   a, (de)
                ld   (TILE_ATTRS + T_TRAP), a
.tk:            pop  hl
.tn:            inc  l
                inc  l
                ld   a, l
                cp   (TRAP_LIST + TRAP_MAX * TRAP_STRIDE) & $FF
                jr   nz, .tr
                ASSERT TRF_S1 == 1 << 4 && (TRAP_LIST >> 8) == ((TRAP_LIST + TRAP_MAX * TRAP_STRIDE) >> 8)
                ; P3 (game.md §1.3): the Sanctum's lectern, rows LECT_ROW..+1 of storey 1 against the
                ; dead-end wall (the door on the right: cols 1-2, else 29-30), ids TL TR / BL BR. Every
                ; build (the Tome's state is TOME_HP); BEFORE the decor, whose T_AIR footprint rule then
                ; keeps every object off it (tests/room_model.py stamps it there too)
                bit  RDF_SANCTUM_BIT, (ix+RD_FLAGS)
                jr   z, .nolec
                ld   bc, (LECT_ROW << 8) | LECT_COL_L
                bit  RDX_R_BIT, (ix+RD_EXITS)
                jr   nz, .lcl
                ld   c, LECT_COL_R
.lcl:            ld   e, T_LECT_TL
.lec:            call map_cell                  ; (bank 2; A)
                ld   (hl), e
                inc  e
                inc  l                         ; (col <= 30: same row)
                ld   (hl), e
                inc  e
                inc  b
                bit  0, b
                jr   z, .lec                    ; rows 15, 16
.nolec:
                ASSERT T_LECT_TR == T_LECT_TL + 1 && T_LECT_BL == T_LECT_TL + 2 && T_LECT_BR == T_LECT_TL + 3
                ASSERT (LECT_ROW & 1) && RDF_SANCTUM == 1 << RDF_SANCTUM_BIT && RDX_R == 1 << RDX_R_BIT
                ; decor
                ld   a, (ix+RD_SEED)
                or   (ix+RD_SEED + 1)
                jr   z, .gate                  ; seed 0 (PROTO rooms): no decor (their old list was empty)
                ld   a, (TMP0)
                call decor_room                ; B3B-9 (IX = descriptor)
                ; B12 (concept-screen B3B-8 #4): the OPEN level exit = the raised gate
                ; T_GRATE over its 3 hole cells + the depth's GLOW on the standing row
                ; above the middle cell if that is still T_AIR. After the deriver, so its
                ; ring rule still saw HOLE_* there: the decor stays byte-identical to
                ; before (and nothing is ever placed beside / above the exit).
.gate:          ld   a, (ix+RD_EXITCOL)        ; 0 = not the lair (.three: none; PROTO
                ld   b, FLOOR_ROW1             ; rooms come here too: no exit)
                ld   d, T_GRATE_SHUT           ; 3F-T8 (BOSS-GUARD): the SHUT gate while the
                ld   hl, LVL_FLAGS             ; boss lives, also after the deriver, so the
                bit  LF_GRATE_OPEN_BIT, (hl)   ; decor never depends on the grate state
                jr   nz, .open                 ; (grate_open re-stamps the same 3 cells + glow)
                call .three
                jr   .x
.open:          ld   d, T_GRATE
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
                INCLUDE "lq3.asm"              ; AI-L1: lq_block (the ladder queue: strongest first; R6 until MEM-RECLAIM w3)
                INCLUDE "combat3.asm"          ; D3-6a: hit_roll, deal_hit (shared damage core)
                INCLUDE "proj3.asm"            ; D3-6b: proj_fire (projectile logic at cast time)
                INCLUDE "rank3.asm"            ; D3-7: abil_load (ABIL_DESC for the bank-7 ability code)
                INCLUDE "icons3.asm"           ; C3-3 icon bar state + drawing
                INCLUDE "fi3.asm"              ; FLOOR1 fi_full (cold, far3 only): bank 2 LAND-PENDING .. BLAIR-FIX
                                               ; (resolve_monsters moved to bank 2 paid its 52 B back)
                INCLUDE "drop3.asm"            ; FLOOR1: mon_drop + drop_tab / uniq_tab (from R6)
                INCLUDE "dnum3.asm"            ; D3-11: dn_take (far3 from bank-0 dn_scan, the spawn)

;------------------------------------------------------------------------------
; page_lat3 — RECLAIM-C (e): page_post's epilogue (was bank-1 menu1.asm `.lat`, -41 B
; bank 1), far3 from page_post. A = FXR_* (bit 0 = the verb spent the turn).
; PAGE_OPEN off; nothing pressed on the page reaches play: no INTENT / DOWN window,
; no stick edge, a held direction waits for its release (EXIT_LOCK), a held FIRE is
; not a tap, no shortcut edge; the page time is not a tick overrun.
; Out: L = 1 the verb spent the turn, else 0.  Clobbers: A, F, L.  Cold (once a page).
;------------------------------------------------------------------------------
page_lat3:      and  FXR_TURN
                ld   l, a                      ; L out (resync_tick keeps it; far3 passes HL)
                xor  a
                ld   (PAGE_OPEN), a
                ld   (INTENT), a
                ld   (DN_T), a
                ld   (DN_COMMIT), a
                ld   a, (STICK)                ; no stick edge from the page's frames
                ld   (STICK_OLD), a
                and  JOY_DIRS
                ld   (EXIT_LOCK), a            ; a held direction waits for its release
                ld   a, FS_USED                ; a held FIRE is not a tap
                ld   (FIRE_ST), a
                ld   a, (PLAYER_SC)            ; no shortcut edge either
                ld   (SC_OLD), a
                jp   resync_tick               ; A only
                ASSERT FXR_TURN == 1
                ; R6 (2026-10-21): pickup3.asm / bag3.asm moved to the R6 region (r6.asm:
                ; pickup6.asm, bag6.asm), reached through far6
