;==============================================================================
; lpop3.asm — LP: lazy monster population (game.md §9.4.1-9.4.7, user
; 2026-10-06). Bank 3 cold code, INCLUDEd from bank3.asm after levelgen.asm
; (uses its rnd / lg_step / bfs / hits / hla / rdp / ispres). Byte-exact
; reference: tools/levelgen.py lp_budget / lp_enter (algorithm documented
; there). State: LP_STATE (bank 5, level_defs.asm "LP").
;
; A level stores no monster list: a budget + one record per room. Monsters
; hold entity slots only while the hero is in their room.
;   level_populate  -> lp_budget (the per-room quotas) + lp_enter (start room)
;   do_exit         -> follow_select (candidates only) -> lp_transition:
;                      lp_bank (old room, candidates kept aside), lp_enter
;                      (destination), follow_admit, lp_bank (rejected
;                      candidates), ROOM_VISITS[dest] += 1
;   3F trickle      -> lp_append (record side only, §9.5)
; PROTO rooms (LVL_DEPTH 0): none of this runs; every monster keeps its slot.
; Pages nothing (spawn_one / ent_ix / KFIELD are bank-2 / bank-3 only).
;==============================================================================
LPV_ROOM        EQU TMP0                ; room being banked / entered
LPV_BOSS        EQU TMP1                ; lp_enter: 1 = the unit is the fresh lair's boss
                                        ; lp_bank: 1 = keep the follower candidates aside
LPV_N           EQU TMP2                ; units left to place
LPV_RDP         EQU TMP3                ; word (TMP3/4): record read pointer
LPV_WRP         EQU TMP5                ; word (TMP5/6): record write pointer
LPV_K           EQU TMP7                ; unit kind / bank slot

; A = kind -> A = kind_tab[off + kind] (KFIELD without IX). Clobbers HL.
    MACRO KTA off
                add  a, (off) & $FF
                ld   l, a
                ld   h, (kind_tab + (off)) >> 8
                ld   a, (hl)
    ENDM

;------------------------------------------------------------------------------
; Per-depth budget rows (game.md §9.4 table): 4 kinds in table order, boss,
; count incl. boss (3F-T3: real kind ids, defs.asm). 3F-T5: the golden depths (D1-D3, D5, D6, §9.7
; R1) carry LEK_GOLD in the boss byte (levelgen.py k3_boss); the entity bit is E_GOLD.
;------------------------------------------------------------------------------
lp_dtab:        DB   K_RAT, K_BAT, K_SLIME, K_GOBLIN,          K_BOSS_D1 | LEK_GOLD, 13
                DB   K_GOBLIN, K_SPIDER, K_BAT, K_RAT,         K_BOSS_D2 | LEK_GOLD, 14
                DB   K_SKELETON, K_VAMPIRE, K_GHOST, K_BAT,    K_BOSS_D3 | LEK_GOLD, 14
                DB   K_ORC, K_RAT, K_SPIDER, K_ARCHER,         K_BOSS_D4, 15
                DB   K_MUMMY, K_SKELETON, K_ARCHER, K_SPIDER,  K_BOSS_D5 | LEK_GOLD, 16
                DB   K_VAMPIRE, K_GHOST, K_NECRO, K_ORC,       K_BOSS_D6 | LEK_GOLD, 15
                DB   K_ORC, K_NECRO, K_GHOST, K_NECRO,         K_BOSS_D7, 15   ; 3F-T13bc ARCHER-DEPTHS H1: the 2nd Necro replaces the Archer (weight 6 = 6)
                DB   K_NECRO, K_SKELETON, K_GHOST, K_VAMPIRE,  K_BOSS_D8, 12
LP_DROW         EQU 6
                ASSERT $ - lp_dtab == LEVELS * LP_DROW
; §9.4.1 "N >= |R|" always holds (min N = LP_N_MIN - 2 = 10 >= 7 = the most rooms R
; can have), so lp_budget has no "N farthest rooms" branch (levelgen.py keeps it).
                ASSERT LP_N_MIN - 2 >= GRID_CELLS - 2
; §9.3 weights by kind row (defs.asm WT_*), K_COUNT entries (3F-T3: 18 base + 12 tier rows)
; (the hero rows 0 / 1 stay 0: a record entry of kind 0 may exist in tests; id 2 = K_VBAT, 3F-T9)
; (3F: MEM-RECLAIM w3: lp_wt is the kind_tab KT_REACH slot, bank 2 main.asm; the macro LP_WT_ROWS lives in defs.asm)
; lp_wt: one copy in bank 2 (kind_tab + KT_REACH), read by bank 3 and R6
                ASSERT LEK_RESPAWN == EF_RESPAWN && K_COUNT - 1 <= LEK_KIND_MASK
                ASSERT LVL_LAIR == LVL_START + 1 && LVL_SANCTUM == LVL_START + 3
; low-RAM neighbours (D3-TX merge): TX_DEC (GEN_MIR top) < LVL_STATE < ORN_GLYPHS
; < LP_STATE < LOWRAM_FREE_END; the cell map stays in NEXT_MAP's unused tail
                ASSERT TX_DEC + TX_DEC_LEN <= LVL_STATE && LP_STATE >= ORN_GLYPHS + ORN_COUNT * 8
                ASSERT LP_END <= LOWRAM_FREE_END && LP_CMAP >= NEXT_MAP + PLAY_CELLS
                ASSERT LP_CMAP + 2 * LP_CMW <= NEXT_MAP + MAP_BUF_LEN && LP_CMAP + 2 * LP_CMW <= GEN_MIR

; lp_rec — A = room -> HL = its record (LP_REC + 9 A). Clobbers A, F.
lp_rec:         ld   l, a
                add  a, a
                add  a, a
                add  a, a
                add  a, l
                ld   hl, LP_REC
                jp   hla

;------------------------------------------------------------------------------
; lp_budget — §9.4.1, right after level_gen (LG_* scratch still valid: bfs
; reuses LG_DIST / LG_CAND). Zeroes LP_STATE, copies the depth row, LP_LVL =
; the hero's LVL, LP_RMAX, then the quota split: every room of R (present, not
; start / lair / Sanctum) gets 1, each remaining unit a weighted pick
; (rnd(sum of BFS distances) over the rooms of R below LP_RMAX) on GEN_RNG,
; which is put back afterwards (the header keeps the generator's final state:
; Python == Z80 for every earlier output). Lair quota = 2 (boss + escort).
; Clobbers: all but IY.   ~5k T (bfs ~2k, <= 5 weighted picks ~0.5k each)
;------------------------------------------------------------------------------
lp_budget:
                ld   hl, LP_STATE
                ld   de, LP_STATE + 1
                ld   bc, LP_LEN - 1
                ld   (hl), 0
                ldir
                ld   a, (LVL_DEPTH)
                ld   b, a
                add  a, a
                add  a, b
                add  a, a                      ; 6 d (row d - 1 from lp_dtab - 6)
                ld   hl, lp_dtab - LP_DROW
                call hla
                ld   de, LP_KINDS
                ld   bc, LP_DROW
                ldir                           ; LP_KINDS, LP_BOSS, LP_TOTAL
                ASSERT LP_BOSS == LP_KINDS + 4 && LP_TOTAL == LP_KINDS + 5
                ASSERT (LP_KINDS >> 8) == ((LP_KINDS + 4) >> 8)    ; lp_enter .mw: inc e
                ld   a, (LVL)
                ld   (LP_LVL), a
                ld   a, ROOM_MAX               ; MORE-MON: one cap for all depths (was 2 on D1-D2)
                ld   (LP_RMAX), a
                call bfs                       ; LG_DIST from LVL_START
                ; every room of R: quota 1; C = |R| (ROOM-MEM reclaim: no LG_CAND copy any
                ; more: .elig reads "in R" from the quota >= 1, the weight from LG_DIST)
                ld   bc, 0                     ; B = r, C = |R|
.rs:            ld   a, b
                call ispres                    ; Z = absent
                jr   z, .no
                ld   a, b
                ld   hl, LVL_START
                cp   (hl)
                jr   z, .no
                inc  hl                        ; LVL_LAIR
                cp   (hl)
                jr   z, .no
                inc  hl
                inc  hl                        ; LVL_SANCTUM
                cp   (hl)
                jr   z, .no
                call lp_rec
                ld   (hl), 1
                inc  c
.no:            inc  b
                ld   a, b
                cp   GRID_CELLS
                jr   c, .rs
                ld   a, (LP_TOTAL)
                sub  2
                sub  c                         ; units left after one per room (>= 2)
                ld   (LP_SIG), a               ; (scratch: the remainder)
                ld   hl, (GEN_RNG)
                push hl
.wl:            ld   hl, LP_SIG
                ld   a, (hl)
                or   a
                jr   z, .wd
                dec  (hl)
                ld   bc, 0                     ; B = r, C = sum of weights
.ws:            call .elig
                add  a, c
                ld   c, a
                inc  b
                ld   a, b
                cp   GRID_CELLS
                jr   c, .ws
                ld   a, c
                or   a
                jr   z, .none                  ; every room of R full
                call rnd                       ; v = rnd(sum) (sum <= 56)
                ld   c, a
                ld   b, 0
.wp:            call .elig
                jr   z, .wn
                ld   e, a
                ld   a, c
                sub  e
                jr   c, .hit                   ; v < weight
                ld   c, a
.wn:            inc  b
                jr   .wp
.hit:           ld   a, b
                call lp_rec
                inc  (hl)
                jr   .wl
.none:          ld   a, (LP_SIG)
                inc  a                         ; this unit + the rest
                ld   (LP_DISCARD), a
.wd:            pop  hl
                ld   (GEN_RNG), hl
                xor  a
                ld   (LP_SIG), a
                ld   a, (LVL_LAIR)
                call lp_rec
                ld   (hl), 2                   ; boss + escort (§9.4.4)
                ret
; .elig: B = room -> A = its weight (LG_DIST, >= 1) if in R (quota >= 1: only R got
; one; the lair's 2 comes after) and quota < LP_RMAX, else 0 (Z). Keeps BC.
.elig:          ld   a, b
                call lp_rec
                ld   a, (hl)
                or   a
                ret  z                         ; not in R
                ld   hl, LP_RMAX
                cp   (hl)
                jr   nc, .e0                   ; quota >= rmax: full
                ld   a, b
                ld   hl, LG_DIST
                call idx
                or   a
                ret
.e0:            xor  a
                ret

;------------------------------------------------------------------------------
; lp_append — A = room, B = kind byte (kind | LEK_*), C = hp: append an entry
; to the room's record and mark it VISITED (§9.4.2 bank on leave; the §9.5
; trickle's record side, 3F). CF = the record is full (LR_MAX): dropped,
; LP_DISCARD += 1 (cannot happen with the §9.3 cap). Clobbers: A, E, HL.
;------------------------------------------------------------------------------
lp_append:      call lp_rec
                ld   a, (hl)
                and  LR_CNT_MASK
                cp   LR_MAX
                jr   nc, .full
                ld   e, a
                inc  a
                or   LR_VISITED
                ld   (hl), a
                ld   a, e
                add  a, a
                inc  a                         ; LR_ENT + 2 * count
                call hla
                ld   (hl), b
                inc  hl
                ld   (hl), c
                or   a
                ret
.full:          ld   hl, LP_DISCARD
                inc  (hl)
                scf
                ret
                ASSERT LR_ENT == 1 && LE_KIND == 0 && LE_HP == 1 && LE_STRIDE == 2

;------------------------------------------------------------------------------
; lp_bank — A = room, E = 1: keep the follower candidates (CAND_LIST) aside;
; E = 0: every slot (E, not C: far3 passes DE, not BC — tests call it). §9.4.2: each active
; monster slot of the room leaves play; the alive ones (not EF_DYING) are appended to the
; record with their exact hp and EF_RESPAWN, and (ROOM-MEM, user 2026-11-03) their slot is
; PARKED, not freed (level_defs.asm LPK_PARK: E_FLAGS bit 0 clear, E_ROOM | LPK_PARK; x,
; y, facing, statuses, cooldown, AI bytes kept for lp_enter). Dead ones are freed and never
; written; summon-made ones (3F-T9 RCD_SUMMONED) are freed (§9.4.2); RCD_ONCE is written
; as LEK_BRED. The record becomes VISITED. Eviction: every inactive slot whose room
; (E_ROOM & LPK_ROOM) is not this one, EXIT_DEST or TRK_PREV is freed (the two last rooms
; left stay parked: A -> B -> C -> A; a free slot is "freed" again, harmless).
; Clobbers: A, BC, DE, HL, IX.   ~2.6k T (15 slots) + ~0.2k T per banked one
;------------------------------------------------------------------------------
lp_bank:        ld   (LPV_ROOM), a
                call lp_rec                    ; VISITED first (lp_append keeps it; a room left
                set  LR_VISITED_BIT, (hl)      ; with nothing to bank still becomes VISITED)
                ld   a, e
                ld   (LPV_BOSS), a
                ld   a, 1
.l:             ld   (LPV_K), a                ; slot
                call ent_ix
                bit  0, (ix+E_FLAGS)           ; EF_ACTIVE
                jr   z, .ev
                ld   a, (LPV_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .n
                ld   a, (LPV_BOSS)
                or   a
                jr   z, .b
                ld   a, (LPV_K)
                ld   hl, CAND_LIST
                call idx
                inc  a
                jr   nz, .n                    ; a candidate: kept aside
.b:             ld   a, (ix+E_FLAGS)
                bit  EF_DYING_BIT, a
                jr   nz, .free                 ; dead: never returns
                bit  RCD_SUMMONED_BIT, (ix+E_RCD)
                jr   nz, .free                 ; 3F-T9: summon-made: discarded (§9.4.2)
                and  EF_RESPAWN
                or   (ix+E_KIND)
                or   (ix+E_GOLD)               ; 3F-T5: LEK_GOLD or 0
                bit  RCD_ONCE_BIT, (ix+E_RCD)
                jr   z, .nb
                set  LEK_BRED_BIT, a           ; 3F-T9: the once bit (a Rabbit Rat bred)
.nb:            ld   b, a
                ld   c, (ix+E_HP)
                ld   a, (LPV_ROOM)
                call lp_append
                jr   c, .free                  ; the record is full (cannot happen, §9.3 cap): not parked
                res  0, (ix+E_FLAGS)           ; ROOM-MEM: parked, not freed: EF_ACTIVE clear, the
                set  7, (ix+E_ROOM)            ; rest (HOSTILE: != 0) kept, E_ROOM | LPK_PARK
                jr   .n
                ASSERT LPK_PARK == 1 << 7 && EF_ACTIVE == 1 && EF_HOSTILE != 0
.ev:            ld   a, (ix+E_ROOM)            ; ROOM-MEM eviction (header)
                and  LPK_ROOM
                ld   hl, LPV_ROOM
                cp   (hl)
                jr   z, .n
                ld   hl, EXIT_DEST
                cp   (hl)
                jr   z, .n
                ld   hl, TRK_PREV
                cp   (hl)
                jr   z, .n
                ld   (ix+E_ROOM), 0
.free:          ld   (ix+E_FLAGS), 0
.n:             ld   a, (LPV_K)
                inc  a
                cp   P_MAX_ENT
                jr   c, .l
                ret
                ASSERT EF_ACTIVE == 1

;------------------------------------------------------------------------------
; lp_transition — do_exit (far3, .lpt), after follow_select / hide_sprites and the
; hero's placement at his arrival, before the NEXT_MAP build and the scroll (§9.4.3
; order): bank the old room (candidates aside; ROOM-MEM: parked, older rooms evicted),
; spawn the destination's residents for the hero's arrival box (his slot), admit the candidates against the real residents
; (follow_admit), bank the rejected ones, ROOM_VISITS[dest] += 1, and hide
; every monster slot's render record (slots 1..15 were rewritten: do_exit's
; vis_room_sync then rebuilds RLIST; the hero keeps its frame). No-op on the
; PROTO rooms (LVL_DEPTH 0). Clobbers: all but IY.
;   ~5-25k T (tests/lp.py reports the measured worst; gameplay is frozen)
;------------------------------------------------------------------------------
lp_transition:
                ld   a, (LVL_DEPTH)
                or   a
                ret  z
                ld   a, (CUR_ROOM)
                ld   e, 1
                call lp_bank
                ; the hero's arrival box: ROOM-MEM: do_exit (.lpt) has already placed him
                ; there (x 1 / 31 - w / EXIT_COL, standing on the arrival storey; H1: a vertical
                ; exit's arrival is mid-ladder at the shaft end, y 0 / 18 - h: storey_ref 0 / 1)
                ld   ix, P_ENTITIES
                KFL    KT_BW
                ld   (LP_HW), a
                ld   a, (ix+E_X)
                ld   (LP_HX), a
                call storey_ref                ; (bank 2; A, HL)
                ld   (LP_HS), a
                ld   a, (EXIT_DEST)
                call lp_enter
                ld   hl, boss_chk              ; 3F-T8: the lair boss still exists (debug trap; bank 7, w2b)
                call far7
                call follow_admit
                ld   a, (CUR_ROOM)
                ld   e, 0
                call lp_bank
                ld   a, (EXIT_DEST)
                ld   hl, ROOM_VISITS
                call hla
                inc  (hl)
                ld   hl, SLOTREC + SLOTREC_STRIDE + R_VIS
                ld   de, SLOTREC_STRIDE
                ld   b, P_MAX_ENT - 1
.hv:            ld   (hl), d
                add  hl, de
                djnz .hv
                ret

;------------------------------------------------------------------------------
; lp_enter — A = room, LP_HX / LP_HS / LP_HW = the hero's arrival box:
; §9.4.3 spawn. Seeds the spawn stream (GEN_RNG algorithm, own state: GEN_RNG
; is saved and put back) from LVL_SEED, the room and ROOM_VISITS[room]; a
; FRESH record gets its units (3F-T5: R6 lp_gen, tier6.asm, ONE far6: lair = boss +
; escort, cap 12; else quota x fit with the §9.6 tier roll, cap SIGMA_INIT = max(8, ROOM_MAX x minW)
; with the reservation; entries {kind byte | LEK_GOLD, depth-scaled hp}) written into its own entry area; then every unit is placed
; (lp_place) into a free slot (lp_spawn) or kept, in order, in the record,
; which becomes VISITED. ROOM_VISITS is NOT incremented (callers do it).
; ROOM-MEM: a unit with a parked slot (lp_find) tries its saved cell first (try 0, no stream
; step, §9.4.3 rules with the 5-col arrival gap; not for a lair unit with a post) and is
; restored in place (lp_spawn); else tries 1-8 as before.
; Clobbers: all but IY.   <= ~15k T worst (4 units x 8 tries)
;------------------------------------------------------------------------------
lp_enter:
                ld   (LPV_ROOM), a
                ld   c, a
                ld   hl, ROOM_VISITS
                call hla
                ld   e, (hl)
                ld   a, c
                add  a, a
                add  a, a
                add  a, a
                add  a, a
                add  a, $0F                    ; r * 16 + 15: never a depth (GEN_RNG's seed mix)
                ld   hl, (LVL_SEED)
                xor  h
                ld   h, a
                ld   a, l
                xor  e
                ld   l, a
                or   h
                jr   nz, .sd
                inc  l                         ; x = 0 would lock the xorshift
.sd:            ld   (LP_RNG), hl
                ld   de, (GEN_RNG)
                push de
                ld   (GEN_RNG), hl
                call lp_cmap                   ; the room's static cell map
                xor  a
                ld   (LP_SIG), a
                ld   (LPV_BOSS), a
                ld   a, (LPV_ROOM)
                call lp_rec
                ld   (LP_RECP), hl
                ld   a, (hl)
                bit  LR_VISITED_BIT, a
                jr   nz, .vis
                ld   hl, lp_gen                ; 3F-T5: FRESH -> R6 lp_gen (tier6.asm): the lair's boss (+ golden flag)
                call far6                      ; + escort, else quota x fit with the §9.6 tier roll; entries
                ld   a, b                      ; {kind byte, depth-scaled hp}; B = their number
                jr   .place
.vis:           and  LR_CNT_MASK
.place:         ld   (LPV_N), a
                ld   hl, (LP_RECP)
                inc  hl
                ld   (LPV_RDP), hl
                ld   (LPV_WRP), hl
                or   a
                jr   z, .done
.u:             ld   hl, (LPV_RDP)
                ld   a, (hl)
                and  LEK_KIND_MASK
                ld   (LPV_K), a
                KTA  KT_BW
                ld   (LP_W), a
                call lp_find                   ; ROOM-MEM: IX = the unit's parked slot / PK_NONE
                ld   a, (LVL_LAIR)             ; 3F-T8 (game.md §9.2 G1 / G1a / G1b): a unit
                ld   hl, LPV_ROOM              ; of the lair takes its post (R6 boss6.asm, no
                cp   (hl)                      ; stream step; keeps IX); an escort with no legal
                jr   nz, .t0                   ; post falls back to its saved cell / lp_place
                ld   hl, lp_post
                call far6                      ; L = 1: C = 1, E = x
                ld   a, l
                cp   1                         ; Z, NC: posted
                jr   z, .sp
.t0:            ld   a, ixh                    ; ROOM-MEM try 0 (no stream step): the saved cell,
                cp   PK_NONE >> 8              ; the §9.4.3 rules with the 5-col arrival gap
                jr   z, .pl
                call storey_ref                ; (bank 2) A = its storey (feet: a flyer -> its band)
                ld   c, a
                ld   e, (ix+E_X)
                ld   a, LP_GAP2
                ld   (LP_GAPV), a
                call lp_legal                  ; NC: legal (C = s, E = x kept)
                jr   nc, .sp
.pl:            call lp_place                  ; CF = no legal cell, else C = s, E = x
.sp:            call nc, lp_spawn              ; CF = no free slot
                jr   nc, .nu
                ld   hl, (LPV_RDP)             ; not placed: stays in the record
                ld   de, (LPV_WRP)
                ldi
                ldi
                ld   (LPV_WRP), de
.nu:            ld   hl, (LPV_RDP)
                inc  hl
                inc  hl
                ld   (LPV_RDP), hl
                ld   hl, LPV_N
                dec  (hl)
                jr   nz, .u
.done:          ld   hl, (LP_RECP)
                ld   de, (LPV_WRP)
                ld   a, e
                sub  l
                dec  a                         ; 2 * entries kept
                rrca
                or   LR_VISITED
                ld   (hl), a                   ; (ROOM-MEM reclaim: the unused entries keep
                pop  hl                        ; their stale bytes; levelgen.py models it)
                ld   (GEN_RNG), hl
                ret
;------------------------------------------------------------------------------
; lp_place — LP_W / LP_M = the unit, LPV_BOSS: LP_TRIES candidates from the
; spawn stream, one step each: s = bit 0 of its high byte, x = LP_XMIN + (low
; byte mod (LP_XMAX - w)); the first legal one
; (lp_legal), or for the boss the legal one farthest from the hero (|x - hx|,
; + 32 on another storey; the first of equals). Out: CF = none; else C = s,
; E = x.  Clobbers: A, BC, DE, HL.   ~8 x 0.6k T worst
;------------------------------------------------------------------------------
lp_place:       ld   b, LP_TRIES
.t:             push bc
                call lg_step                   ; ONE step per candidate (~0.35k T saved):
                ld   a, h                      ; s = bit 0 of the high byte,
                and  1                         ; x = LP_XMIN + low byte mod (LP_XMAX - w)
                ld   c, a
                ld   a, (LP_W)
                cpl
                add  a, LP_XMAX + 1            ; LP_XMAX - w
                ld   b, a
                ld   a, l
.md:            sub  b
                jr   nc, .md
                add  a, b
                add  a, LP_XMIN
                ld   e, a
                pop  af                        ; A = tries left (8..1)
                push af
                cp   LP_TRIES / 2 + 1
                ld   a, LP_GAP                 ; tries 1-4: gap 8
                jr   nc, .gv
                ld   a, LP_GAP2                ; tries 5-8: gap 5
.gv:            ld   (LP_GAPV), a
                call lp_legal
                jr   nc, .lg
                dec  a
                jr   nz, .n                    ; another rule failed
                inc  c                         ; only the gap: same x, other storey
                res  1, c                      ; (C 0 <-> 1; no new RNG step; no gap rule there)
                call lp_legal
                jr   c, .n
.lg:            pop  hl                        ; drop the saved BC: C = s stays
                ret                            ; (NC from lp_legal)
.n:             pop  bc
                djnz .t
                scf
                ret

;------------------------------------------------------------------------------
; lp_cmap — LPV_ROOM, LP_HX / LP_HS / LP_HW: build LP_CMAP (level_defs.asm),
; the §9.4.3 placement rules as per-col marks, once per entry:
;   LPC_BAD   every col a body may not cover, the 1-col margin baked in:
;             storey-s footprints f-1..f+3 (the `hits` sets: s0 = up-exit,
;             arrival shaft, both ladders; s1 = down-exit, level exit, both
;             ladders: the ladder cells and their end boxes), the storey-0 pit
;             p-2..p+4, the storey-1 landing cols p-1..p+3, the block + rubble
;             + 1; the arrival boxes (cols 1-4 / 27-30 of a horizontal exit's
;             storey, no margin). The hero's arrival gap is tested per try
;             (lp_legal); lp_spawn marks each body it places.
; Clobbers: A, BC, DE, HL, IX.   ~2.5k T
;------------------------------------------------------------------------------
lp_cmap:        ld   hl, LP_CMAP               ; clear: 3 stores / loop, ~15 T/B
                ld   b, 2 * LP_CMW / 3         ; (ldir: 21 T/B; ~0.4k T saved)
                xor  a
.c:             ld   (hl), a
                inc  l
                ld   (hl), a
                inc  l
                ld   (hl), a
                inc  l
                djnz .c
                ASSERT (2 * LP_CMW) % 3 == 0
                ld   a, (LPV_ROOM)
                call rdp
                push hl
                pop  ix                        ; IX = descriptor
                ld   e, LPC_BAD
                ld   c, 0                      ; storey
.s:             ld   b, $35                    ; s0: UPCOL, ARRCOL, LAD1, LAD2 (= hits)
                ld   a, c
                or   a
                jr   z, .m0
                ld   b, $3A                    ; s1: DNCOL, EXITCOL, LAD1, LAD2
.m0:            push ix
                pop  hl
                inc  hl
                inc  hl                        ; RD_UPCOL
.f:             srl  b
                jr   nc, .fn
                ld   a, (hl)
                or   a
                jr   z, .fn
                push hl
                push bc
                dec  a                         ; f-1 .. f+3: the footprint + the
                ld   b, 5                      ; 1-col margin (body cols only are tested)
                call lp_mark
                pop  bc
                pop  hl
.fn:            inc  hl
                ld   a, b
                or   a
                jr   nz, .f
                inc  c
                bit  1, c                      ; storeys 0, 1
                jr   z, .s
                ld   a, (ix+RD_PITCOL)
                or   a
                jr   z, .mb
                ld   a, (ix+L2_PITW)           ; L2: wide pit W holes (0 = the ordinary 3)
                or   a
                jr   nz, .pw
                ld   a, 3
.pw:            ld   d, a
                add  a, 4
                ld   b, a                      ; s0: holes + caps p-1..p+W, +-1 = W+4 cols from p-2
                ld   a, (ix+RD_PITCOL)
                sub  2                         ; (C = 2 after the storey loop: bit 0 = storey 0;
                call lp_mark                   ; lp_mark reads bit 0 only)
                ld   a, d
                add  a, 2
                ld   b, a                      ; s1: the fall's landing cols p..p+W-1, +-1
                ld   a, (ix+RD_PITCOL)
                dec  a
                inc  c                         ; C = 3: storey 1
                call lp_mark
.mb:            ld   a, (ix+L2_MIDB)           ; L2 mid-block (storey 0): b..b+w-1 + rubble b-1 / b+w,
                or   a                         ; +-1 = w+4 cols from b-2
                jr   z, .bl
                ld   a, (ix+L2_MIDW)
                add  a, 4
                ld   b, a
                ld   a, (ix+L2_MIDB)
                sub  2
                ld   c, 0
                call lp_mark
.bl:            ld   a, (ix+RD_BLOCK)
                or   a
                jr   z, .ar
                ld   d, a
                rlca
                rlca
                ld   c, a                      ; storey = bit 0 (RDB_S1 = bit 6; lp_mark reads bit 0 only)
                ld   a, d
                and  RDB_WMASK
                add  a, 2
                ld   b, a                      ; w + 2 cols: left 0..w+1 (block,
                xor  a                         ; rubble at w, + the margin)
                bit  7, d
                jr   z, .bm
                ld   a, 32                     ; right: 30-w .. 31
                sub  b
.bm:            call lp_mark
.ar:            ld   d, (ix+RD_EXITS)
                bit  0, d                      ; RDX_L
                jr   z, .ar2
                ld   a, d
                rrca
                rrca
                rrca
                rrca
                ld   c, a                      ; bit 0 = RDX_LS1 (lp_mark reads bit 0 only)
                ld   a, 1
                ld   b, 4
                call lp_mark                   ; cols 1..4
.ar2:           bit  1, d                      ; RDX_R
                ret  z
                ld   a, d
                rlca
                rlca
                rlca
                ld   c, a                      ; bit 0 = RDX_RS1
                ld   a, 27
                ld   b, 4
                jp   lp_mark                   ; cols 27..30
;------------------------------------------------------------------------------
; lp_mark — A = first col (signed: -128..127), B = cols (>= 1), C = storey,
; E = bit: OR E into LP_CMAP[C][A .. A+B-1], CLIPPED to cols 0..LP_CMW-1
; (fix/3d-artefacts: an unclipped range once ran past LP_CMAP into
; TILE_GLYPHS). In-range fast path: the 2 range tests (~40 T) are paid for
; by the one-page address (no `call hla`, `inc l`): ~+10 T per call.
; Keeps C, DE.  Clobbers: A, B, HL.  (tests/lp.py A6: out-of-range calls.)
;   ~95 T + 30 T per col
;------------------------------------------------------------------------------
lp_mark:        cp   LP_CMW                    ; unsigned: a negative start is >= $80
                jr   nc, .clip
                ld   h, a
                add  a, b
                cp   LP_CMW + 1
                jr   nc, .clipr                ; runs past the right edge
                ld   a, h
.go:            ld   hl, LP_CMAP
                bit  0, c
                jr   z, .r
                ld   l, (LP_CMAP + LP_CMW) & $FF
.r:             add  a, l                      ; LP_CMAP: one page (ASSERTed at lp_legal)
                ld   l, a
.l:             ld   a, (hl)
                or   e
                ld   (hl), a
                inc  l
                djnz .l
                ret
.clipr:         ld   a, LP_CMW
                sub  h
                ld   b, a                      ; cols h .. LP_CMW-1
                ld   a, h
                jr   .go
.clip:          bit  7, a
                ret  z                         ; starts right of the map
                add  a, b                      ; end = A + B
                ret  z                         ; ... <= 0: nothing on the map
                bit  7, a
                ret  nz
                cp   LP_CMW + 1
                jr   c, .ce
                ld   a, LP_CMW
.ce:            ld   b, a                      ; cols 0 .. end-1
                xor  a
                jr   .go
                ASSERT RDB_WMASK == 3 && LP_CMW == 33 && RDX_LS1 == 1 << 4 && RDX_RS1 == 1 << 5 && RDB_S1 == 1 << 6

;------------------------------------------------------------------------------
; lp_legal — C = storey, E = body-left col, LP_W, LP_GAPV: §9.4.3 placement
; rules: no LPC_BAD mark in the body's cols x .. x+w-1 (LP_CMAP), and
; on the hero's arrival storey a body gap >= LP_GAPV to its arrival box
; (levelgen.py lp_legal states the same rules directly). NC = legal; CF =
; illegal, A = 1 if ONLY the gap failed (lp_place re-tests the other storey),
; else A = 0. Keeps BC, DE.  Clobbers: A, HL.
;   ~0.25k T + 24 T per col checked (<= 14 cols)
;------------------------------------------------------------------------------
lp_legal:       push bc
                push de
                ld   hl, LP_CMAP
                bit  0, c
                jr   z, .r
                ld   l, (LP_CMAP + LP_CMW) & $FF
.r:             ld   a, e                      ; the body's cols only: the marks are
                add  a, l                      ; pre-widened by the margin (lp_cmap)
                ld   l, a
                ld   a, (LP_W)
                ld   b, a
                xor  a
.g:             or   (hl)                      ; 24 T / col: OR the marks, test once
                inc  l                         ; (LP_CMAP: one page, ASSERTed)
                djnz .g
                or   a
                jr   nz, .bad
                ld   hl, LP_HS                 ; arrival storey: body gap >= LP_GAPV
                ld   a, (hl)
                cp   c
                jr   nz, .ok
                dec  hl
                ld   a, (hl)                   ; LP_HX
                inc  hl
                inc  hl
                add  a, (hl)                   ; + LP_HW
                ld   l, LP_GAPV & $FF
                add  a, (hl)
                ld   b, a                      ; hx + hw + g
                ld   a, e
                cp   b
                jr   nc, .ok                   ; right of the hero
                dec  hl
                ld   a, (hl)                   ; LP_W
                add  a, e
                inc  hl
                add  a, (hl)
                ld   b, a                      ; x + w + g
                ld   l, LP_HX & $FF
                ld   a, (hl)
                cp   b
                jr   nc, .ok                   ; left of the hero
                ASSERT LP_HS == LP_HX + 1 && LP_HW == LP_HX + 2 && LP_GAPV == LP_W + 1 && (LP_HX >> 8) == (LP_GAPV >> 8)
                ld   a, 1                      ; fails ONLY the gap: A = 1
                jr   .bad1
.ok:            pop  de
                pop  bc
                or   a
                ret
.bad:           xor  a                         ; A = 0: another rule
.bad1:          pop  de
                pop  bc
                scf
                ret
                ASSERT LP_XMIN >= 1
                ASSERT (LP_CMAP >> 8) == ((LP_CMAP + 2 * LP_CMW - 1) >> 8)

;------------------------------------------------------------------------------
; lp_spawn — C = storey, E = col, LPV_RDP -> the entry {kind byte, hp},
; LPV_ROOM, LP_W, IX = the unit's parked slot (lp_find) or PK_NONE.
; ROOM-MEM: a parked slot is restored IN PLACE (its ST_* statuses, E_RCD cooldown and
; AI bytes kept; the summon counter reset; its own facing); else the first free slot
; 1..15 (E_FLAGS = 0: a parked slot is never taken) is zeroed (+ its ST_* bytes) and
; faces the hero (x > hx -> EF_LEFT). Both: spawn_one'd (LEK_RESPAWN -> EF_RESPAWN),
; max hp depth-scaled, hp = the entry's; the body is marked LPC_BODY.
; CF = no free slot (nothing changed). Out: IX = the slot.
; Clobbers: A, BC, DE, HL, IX.   ~1.5k T
;------------------------------------------------------------------------------
lp_spawn:       push de                        ; E = col
                push bc                        ; C = storey
                ld   a, ixh
                cp   PK_NONE >> 8
                jr   nz, .pk                   ; ROOM-MEM: the unit's parked slot, in place
                ld   ix, P_ENTITIES + P_ENT_STRIDE
                ld   b, P_MAX_ENT - 1
                ld   de, P_ENT_STRIDE          ; (D = 0: the zero stores below)
.f:             ld   a, (ix+E_FLAGS)
                or   a                         ; free = 0 (a parked slot is not: never taken)
                jr   z, .got
                add  ix, de
                djnz .f
                pop  bc
                pop  de
                scf
                ret
.got:           ld   a, P_MAX_ENT + (ST_FLAGS & $FF)
                sub  b                         ; ST_FLAGS + slot (1..15): its ST_* bytes = 0
                ld   l, a
                ld   h, ST_FLAGS >> 8
                ld   (hl), d
                add  a, (ST_T1 - ST_FLAGS) & $FF
                ld   l, a
                ld   (hl), d
                set  4, l                      ; ST_T2 = ST_T1 + 16
                ld   (hl), d
                and  $0F
                ld   l, a
                inc  h                         ; ST_X = the next page + slot
                ld   (hl), d
                ASSERT (ST_T1 & $FF) == $E0 && ST_T2 == ST_T1 + 16 && ST_X == (ST_FLAGS & $FF00) + $100 && (ST_FLAGS & $FF) == $10
                push ix
                pop  hl
                ld   b, P_ENT_STRIDE / 2       ; the slot = 0 (32-aligned: one page), 2 B a pass:
.z:             ld   (hl), d                   ; 0.56k T (the LDIR it replaces: 0.67k), 2 B less
                inc  l
                ld   (hl), d
                inc  l
                djnz .z
                jr   .mk
                ASSERT (P_ENTITIES & (P_ENT_STRIDE - 1)) == 0
.pk:            ld   a, (ix+E_RCD)             ; its statuses / cooldown / AI bytes stay; the summon
                ld   b, a                      ; counter resets (a discarded summon's ping-pong reset
                rrca                           ; stays, plan ROOM-MEM); the cooldown c (bits 0-1,
                or   ~1 & $FF                  ; stored c XOR 1) := max(c, 1): the fresh entry's
                and  b                         ; grace (no shot on the first monster phase after the
                and  ~RCD_SUMMON & $FF         ; entry, user 2026-11-03), a longer one kept: stored
                ld   (ix+E_RCD), a             ; bit 0 &= bit 1 (01 -> 00; 00 / 10 / 11 stay)
.mk:            pop  bc
                pop  de
                push de
                ld   a, (LP_W)
                ld   b, a
                ld   a, e
                ld   e, LPC_BODY               ; the body: no later unit overlaps it (lp_post: never exempt)
                call lp_mark
                pop  de
                ld   a, (LP_HX)
                cp   e
                sbc  a, a                      ; hx < x: $FF
                and  EF_LEFT
                ld   b, a                      ; face the hero ...
                ld   a, (ix+E_FLAGS)
                or   a
                jr   z, .fr
                and  EF_LEFT                   ; ... ROOM-MEM: a parked one keeps its own facing
                ld   b, a
.fr:            ld   hl, (LPV_RDP)
                ld   a, (hl)
                and  LEK_RESPAWN
                or   b
                ld   b, a
                ld   a, (LPV_ROOM)
                ld   d, a
                ld   a, (hl)
                and  LEK_KIND_MASK
                push hl
                call spawn_one                 ; A kind, D room, E col, C storey, B flags
                pop  hl
                push hl
                ld   c, (hl)                   ; C = the record's kind byte (| LEK_GOLD)
                ld   a, (ix+E_MAXHP)           ; = KT_HP (init_ent_common)
                ld   hl, LVL_DEPTH
                add  a, (hl)
                dec  a                         ; 3F-T5: max hp = row hp + (depth - 1) (§9.1; was the unscaled
                bit  LEK_GOLD_BIT, c           ; KT_HP spawn_one set: the stand-in bug), golden 2 x + 6 (§9.7 R1)
                jr   z, .mh                    ; (= R6 kind_hp, the record side)
                add  a, a
                add  a, 6
.mh:            ld   (ix+E_MAXHP), a
                bit  LEK_BRED_BIT, c           ; 3F-T9: the once bit back (lp_bank wrote it)
                jr   z, .nb
                set  RCD_ONCE_BIT, (ix+E_RCD)
.nb:            ld   a, c
                and  LEK_GOLD
                ld   (ix+E_GOLD), a            ; the golden bit travels with the entity (lp_bank writes it back)
                pop  hl
                inc  hl
                ld   a, (hl)
                ld   (ix+E_HP), a              ; exact hp (FRESH: = the max)
                or   a                         ; NC
                ret

;------------------------------------------------------------------------------
; lp_find — ROOM-MEM: LPV_ROOM, LPV_K = the unit's kind: IX = the first slot (slot
; order) parked for this room (E_ROOM = room | LPK_PARK, lp_bank) holding that kind,
; Z; else IX = PK_NONE (past the 16 slots), NZ. lp_bank appends in slot order and
; lp_enter reads the record in order, so the k-th entry of a kind gets the k-th
; parked body of that kind (exact unless a leftover entry of the same kind, one no
; cell was found for on the last entry, comes first: then two such bodies swap).
; A FRESH record returns at once (nothing of a room never left is parked).
; Clobbers: A, BC, DE, HL.   FRESH ~0.1k T; else ~45 T a slot that is not the room's: ~0.7k T
;------------------------------------------------------------------------------
lp_find:        ld   hl, (LP_RECP)
                bit  LR_VISITED_BIT, (hl)
                ld   hl, PK_NONE + E_ROOM
                jr   z, .f                     ; FRESH (never left, nothing parked): ~0.1k T, not ~0.6k
                ld   a, (LPV_ROOM)
                or   LPK_PARK
                ld   hl, P_ENTITIES + P_ENT_STRIDE + E_ROOM
                ld   de, P_ENT_STRIDE
                ld   b, P_MAX_ENT - 1
.l:             cp   (hl)
                jr   nz, .n
                dec  hl                        ; E_KIND
                ld   c, a
                ld   a, (LPV_K)
                cp   (hl)
                ld   a, c
                inc  hl
                jr   z, .f
.n:             add  hl, de
                djnz .l
.f:             dec  hl                        ; the slot; none: P_ENTITIES + 16 slots
                push hl
                pop  ix
                ret
PK_NONE         EQU P_ENTITIES + P_MAX_ENT * P_ENT_STRIDE
                ASSERT (PK_NONE & $FF) == 0 && ((P_ENTITIES + (P_MAX_ENT - 1) * P_ENT_STRIDE) >> 8) != (PK_NONE >> 8)
                ASSERT E_KIND == 0 && E_ROOM == 1 && LPK_PARK == $80
