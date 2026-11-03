;==============================================================================
; proto_fix.asm — the PROTO rooms A-D as a TEST FIXTURE (D3-11, user 2026-11-02:
; the PROTO code and data left the image to make room for the flying numbers).
; Nothing ships it: main.asm assembles it in the overlay raw area (OVL_PASS
; images, bank-0 scratch, never loaded) DISPed at PROTO_FIX_ORG and SAVEBINs
; build/ovl/proto.bin. tests/game_lib.py (Proto.arm_proto) breaks at
; start_game's proto_hook when proto_start != 0, pokes the image at
; PROTO_FIX_ORG (the bank-5 screen bitmap: level_show clears it) and lets the
; call run it. What it does is what main ran before D3-11 (new_game -> far3
; new_game_proto; start_game -> far6 pool_proto, gen_list, level_show depth 0),
; with the pages switched here instead of by far3 / far6:
;   1. bank 3: proto_level (rooms A-D, edges, potions) + the spawn_tab
;      monsters in slots 1.. (spawn_one), vis_reset;
;   2. R6: the original kinds' pool session (pl_begin / pl_kinds, bank-6
;      limit R6_ADDR: the old pool_proto), then gen_list;
;   3. level_show depth 0 (the D1 set); its return lands in start_game .go.
; new_game's MASTER_SEED store is dead here: proto_level rewrites the header.
; In: DE = the first log line (start_game). Clobbers: all but IY.
;==============================================================================
proto_fix:
                push de                        ; (spawn_one / gen_list clobber DE)
                ld   a, BANK_COLD3
                call page_bank                 ; (bank-3 routines below, as far3 did)
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
                call vis_reset                 ; B7b: no stale render slot (lowram)
                ld   a, BANK_R6
                call page_bank
                ; the old pool_proto (R6): the original kinds K_SKELETON .. K_PROTO_END - 1
                ; pool over the SRC6 sources (no 3F kind, no stairs in rooms A-D); the
                ; limit is put back right after (D3-11: pool_hero / pool_list no longer
                ; reset it). A test must not descend from PROTO without a reload (SRC6
                ; is then overwritten).
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
                jr   nz, .k6                   ; other five (POOL_NEED_PROTO); tests poke 3
                dec  b
.k6:            call pl_kinds
                ASSERT K_PROTO_END - 1 == K_SLIME
                call gen_list
                ld   a, HIGH POOL6_END
                ld   (alloc.lim6 + 1), a       ; the bank-6 limit back (below SRC6)
                pop  de
                xor  a                         ; depth 0: the PROTO rooms' theme
                jp   level_show                ; (the D1 set)

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
; descriptors (RD_SEED 0: build_room_map skips
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
