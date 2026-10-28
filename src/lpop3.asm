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
; count incl. boss (3F-T3: real kind ids, defs.asm; golden bosses are a per-entity flag, T8).
;------------------------------------------------------------------------------
lp_dtab:        DB   K_RAT, K_BAT, K_SLIME, K_GOBLIN,          K_BOSS_D1, 11
                DB   K_GOBLIN, K_SPIDER, K_BAT, K_RAT,         K_BOSS_D2, 12
                DB   K_SKELETON, K_VAMPIRE, K_GHOST, K_BAT,    K_BOSS_D3, 12
                DB   K_ORC, K_RAT, K_SPIDER, K_ARCHER,         K_BOSS_D4, 13
                DB   K_MUMMY, K_SKELETON, K_ARCHER, K_SPIDER,  K_BOSS_D5, 13
                DB   K_VAMPIRE, K_GHOST, K_NECRO, K_ORC,       K_BOSS_D6, 14
                DB   K_ORC, K_ARCHER, K_GHOST, K_NECRO,        K_BOSS_D7, 14
                DB   K_NECRO, K_SKELETON, K_GHOST, K_VAMPIRE,  K_BOSS_D8, 11
LP_DROW         EQU 6
                ASSERT $ - lp_dtab == LEVELS * LP_DROW
; §9.4.1 "N >= |R|" always holds (min N = 11 - 2 = 9 >= 7 = the most rooms R
; can have), so lp_budget has no "N farthest rooms" branch (levelgen.py keeps it).
                ASSERT 11 - 2 >= GRID_CELLS - 2
; §9.3 weights by kind row (defs.asm WT_*), K_COUNT entries (3F-T3: 18 base + 12 tier rows)
; (the hero rows 0 / 1 and the id-2 hole stay 0: a record entry of kind 0 may exist in tests)
lp_wt:          DB   WT_K_KNIGHT, WT_K_WIZARD, 0, WT_K_SKELETON, WT_K_GOBLIN
                DB   WT_K_GHOST, WT_K_RAT, WT_K_BAT, WT_K_SLIME
                DB   WT_K_SPIDER, WT_K_VAMPIRE, WT_K_ORC, WT_K_ARCHER, WT_K_MUMMY
                DB   WT_K_NECRO, WT_K_OGRE, WT_K_DKNIGHT, WT_K_ARCHMAGE
                DB   WT_K_GIANT_RAT, WT_K_RABBIT_RAT, WT_K_SCREECH, WT_K_SLINGER
                DB   WT_K_BLACK_WIDOW, WT_K_SKEL_GUARD, WT_K_SKEL_KNIGHT, WT_K_POLTERGEIST
                DB   WT_K_ORC_BERSERK, WT_K_ORC_BOUNCER, WT_K_SNIPER, WT_K_BONE_CALLER
                ASSERT $ - lp_wt == K_COUNT
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
                dec  a
                ld   b, a
                add  a, a
                add  a, b
                add  a, a                      ; 6 (d - 1)
                ld   hl, lp_dtab
                call hla
                ld   de, LP_KINDS
                ld   bc, LP_DROW
                ldir                           ; LP_KINDS, LP_BOSS, LP_TOTAL
                ASSERT LP_BOSS == LP_KINDS + 4 && LP_TOTAL == LP_KINDS + 5
                ASSERT (LP_KINDS >> 8) == ((LP_KINDS + 4) >> 8)    ; lp_enter .mw: inc e
                ld   a, (LVL)
                ld   (LP_LVL), a
                ld   a, (LVL_DEPTH)
                cp   3
                ld   a, ROOM_MAX_LO
                jr   c, .rm
                ld   a, ROOM_MAX_HI
.rm:            ld   (LP_RMAX), a
                call bfs                       ; LG_DIST from LVL_START
                ; LG_CAND[r] = BFS distance if r in R else 0 (start = 0 anyway);
                ; every room of R: quota 1; C = |R|
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
                ld   a, b
                ld   hl, LG_DIST
                call hla
                ld   a, (hl)
                jr   .st
.no:            xor  a
.st:            ld   e, a
                ld   a, b
                ld   hl, LG_CAND
                call hla
                ld   (hl), e
                inc  b
                ld   a, b
                cp   GRID_CELLS
                jr   c, .rs
                ld   a, (LP_TOTAL)
                sub  2
                sub  c                         ; units left after one per room (>= 2)
                ld   (LP_SIG), a               ; (scratch: the remainder)
                ld   hl, (GEN_RNG)
                push hl
.wl:            ld   a, (LP_SIG)
                or   a
                jr   z, .wd
                dec  a
                ld   (LP_SIG), a
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
; .elig: B = room -> A = its weight if in R and quota < LP_RMAX, else 0 (Z).
; Keeps BC.
.elig:          ld   a, b
                call lp_rec
                ld   a, (LP_RMAX)
                dec  a
                cp   (hl)                      ; rmax - 1 < quota -> full
                jr   c, .e0
                ld   a, b
                ld   hl, LG_CAND
                call hla
                ld   a, (hl)
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
; E = 0: every slot (E, not C: far3 passes DE, not BC — tests call it). §9.4.2: each active monster slot of the room is freed;
; the alive ones (not EF_DYING) are appended to the record with their exact
; hp and EF_RESPAWN (position, facing, AI state, statuses, PENDING dropped).
; Dead ones are never written. (Summons: no summon exists yet — 3F flags them
; and skips the append.) The record becomes VISITED.
; Clobbers: A, BC, DE, HL, IX.   ~2.4k T (15 slots) + ~0.2k T per banked one
;------------------------------------------------------------------------------
lp_bank:        ld   (LPV_ROOM), a
                ld   a, e
                ld   (LPV_BOSS), a
                ld   a, 1
.l:             ld   (LPV_K), a                ; slot
                call ent_ix
                bit  0, (ix+E_FLAGS)           ; EF_ACTIVE
                jr   z, .n
                ld   a, (LPV_ROOM)
                cp   (ix+E_ROOM)
                jr   nz, .n
                ld   a, (LPV_BOSS)
                or   a
                jr   z, .b
                ld   a, (LPV_K)
                ld   hl, CAND_LIST
                call hla
                ld   a, (hl)
                inc  a
                jr   nz, .n                    ; a candidate: kept aside
.b:             ld   a, (ix+E_FLAGS)
                bit  EF_DYING_BIT, a
                jr   nz, .free                 ; dead: never returns
                and  EF_RESPAWN
                or   (ix+E_KIND)
                ld   b, a
                ld   c, (ix+E_HP)
                ld   a, (LPV_ROOM)
                call lp_append
.free:          ld   (ix+E_FLAGS), 0
.n:             ld   a, (LPV_K)
                inc  a
                cp   P_MAX_ENT
                jr   c, .l
                ld   a, (LPV_ROOM)
                call lp_rec
                set  LR_VISITED_BIT, (hl)
                ret
                ASSERT EF_ACTIVE == 1

;------------------------------------------------------------------------------
; lp_transition — do_exit (far3), after follow_select / hide_sprites, before
; the NEXT_MAP build and the scroll (§9.4.3 order): bank the old room
; (candidates aside), spawn the destination's residents for the hero's
; arrival box (EXIT_*), admit the candidates against the real residents
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
                ; the hero's arrival box (do_exit places it there after the scroll)
                ld   ix, P_ENTITIES
                KFIELD KT_BW
                ld   (LP_HW), a
                ld   b, a
                ld   a, (EXIT_KIND)
                cp   EX_UP
                jr   nc, .v
                ld   c, a
                ld   a, (EXIT_STOREY)
                ld   (LP_HS), a
                ld   a, c
                cp   EX_RIGHT
                ld   a, 1                      ; entered from the left edge
                jr   z, .hx
                ld   a, ROOM_COLS - 1
                sub  b                         ; 31 - w
                jr   .hx
.v:             ld   c, 0                      ; EX_DOWN: storey 0
                jr   nz, .vs                   ; (Z from cp EX_UP: up -> storey 1)
                inc  c
.vs:            ld   a, c
                ld   (LP_HS), a
                ld   a, (EXIT_COL)
.hx:            ld   (LP_HX), a
                ld   a, (EXIT_DEST)
                call lp_enter
                call follow_admit
                ld   a, (CUR_ROOM)
                ld   e, 0
                call lp_bank
                ld   a, (EXIT_DEST)
                ld   hl, ROOM_VISITS
                call hla
                inc  (hl)
                ld   hl, SLOTREC + SLOTREC_STRIDE + R_VIS
                ld   b, P_MAX_ENT - 1
.hv:            ld   (hl), 0
                ld   a, l
                add  a, SLOTREC_STRIDE
                ld   l, a
                djnz .hv
                ret
                ASSERT EX_LEFT < EX_RIGHT && EX_RIGHT < EX_UP && EX_UP + 1 == EX_DOWN

;------------------------------------------------------------------------------
; lp_enter — A = room, LP_HX / LP_HS / LP_HW = the hero's arrival box:
; §9.4.3 spawn. Seeds the spawn stream (GEN_RNG algorithm, own state: GEN_RNG
; is saved and put back) from LVL_SEED, the room and ROOM_VISITS[room]; a
; FRESH record gets its units (lair: boss + escort, cap 12; else quota x
; lp_fit, cap SIGMA_INIT = max(8, ROOM_MAX x minW) with the reservation) written into its own entry area; then every unit is placed
; (lp_place) into a free slot (lp_spawn) or kept, in order, in the record,
; which becomes VISITED. ROOM_VISITS is NOT incremented (callers do it).
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
                ld   c, a
                call lp_rec
                ld   (LP_RECP), hl
                ld   a, (hl)
                inc  hl                        ; -> entry 0
                bit  LR_VISITED_BIT, a
                jp   nz, .vis
                and  LR_CNT_MASK
                ld   b, a                      ; FRESH: the quota
                ld   a, (LVL_LAIR)
                cp   c
                jr   nz, .fresh
                ld   a, 1
                ld   (LPV_BOSS), a
                ld   a, (LP_BOSS)
                push hl
                ld   hl, lp_wt
                call hla
                ld   a, (hl)
                ld   (LP_SIG), a
                pop  hl
                ld   a, (LP_BOSS)
                call .unit
                xor  a
                ld   (LP_RES), a
                ld   b, 1
                ld   a, LP_SIGMA_CAP
                call lp_fit                    ; escort (base tier, never rolled)
                jr   c, .place
                call .unit
                inc  b
                jr   .place
.fresh:         push hl                        ; minW = the lightest LP_KINDS weight,
                ld   de, LP_KINDS              ; E (then the cap) = SIGMA_INIT =
                ld   c, $FF                    ; max(LP_SIGMA_INIT, LP_RMAX x minW)
.mw:            ld   a, (de)
                ld   hl, lp_wt
                call hla
                ld   a, (hl)
                cp   c
                jr   nc, .mn
                ld   c, a
.mn:            inc  e
                ld   a, e
                cp   (LP_KINDS + 4) & $FF
                jr   nz, .mw
                ld   a, (LP_RMAX)
                ld   d, a
                xor  a
.mu:            add  a, c
                dec  d
                jr   nz, .mu
                cp   LP_SIGMA_INIT
                jr   nc, .sg
                ld   a, LP_SIGMA_INIT
.sg:            ld   (LPV_N), a                ; (scratch until .place)
                pop  hl
                ld   d, 0                      ; units written
                inc  b
                jr   .fn
.fl:            push bc                        ; LP_RES = (units left after this) x minW
                xor  a
                dec  b
                jr   z, .rz
.rm:            add  a, c
                djnz .rm
.rz:            ld   (LP_RES), a
                pop  bc
                ld   a, (LPV_N)
                call lp_fit                    ; (3F: + the §9.6 tier roll here)
                jr   c, .fn
                call .unit
                inc  d
.fn:            djnz .fl
                ld   b, d
                jr   .place
.vis:           and  LR_CNT_MASK
                ld   b, a
.place:         ld   a, b
                ld   (LPV_N), a
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
                call lp_place                  ; CF = no legal cell, else C = s, E = x
                call nc, lp_spawn              ; CF = no free slot
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
                xor  a
                ld   (LPV_BOSS), a             ; only unit 0 can be the boss
                ld   hl, LPV_N
                dec  (hl)
                jr   nz, .u
.done:          ld   hl, (LP_RECP)
                ld   de, (LPV_WRP)
                ld   a, e
                sub  l
                dec  a                         ; 2 * entries kept
                ld   c, a
                rrca
                or   LR_VISITED
                ld   (hl), a
                ld   a, LR_MAX * LE_STRIDE
                sub  c
                jr   z, .full
                ld   b, a
                ex   de, hl
                xor  a
.z:             ld   (hl), a                   ; unused entries = 0 (levelgen.py)
                inc  hl
                djnz .z
.full:          pop  hl
                ld   (GEN_RNG), hl
                ret
; .unit: A = kind -> entry (HL) = {kind, its full hp}, HL += 2. Keeps BC, DE.
.unit:          ld   (hl), a
                inc  hl
                push hl
                KTA  KT_HP
                pop  hl
                ld   (hl), a
                inc  hl
                ret

;------------------------------------------------------------------------------
; lp_fit — A = sum cap, LP_RES = reservation: roll i = rnd(4), the kind
; LP_KINDS[i] if LP_SIG + its weight + LP_RES <= cap (reservation fit, §9.4.3
; designer decision 2026-10-06), else the other LP_KINDS in list order (i
; skipped), else none (never with a FRESH room's reservation):
; CF, LP_DISCARD += 1. NC: A = kind, LP_SIG += its weight.
; Keeps BC, DE, HL.
;------------------------------------------------------------------------------
lp_fit:         push hl
                push de
                push bc
                ld   c, a                      ; cap
                ld   a, 4
                call rnd
                ld   e, a                      ; i
                ld   b, a
                call .try
                jr   nc, .ok
                ld   b, 0
.j:             ld   a, b
                cp   e
                jr   z, .jn
                call .try
                jr   nc, .ok
.jn:            inc  b
                ld   a, b
                cp   4
                jr   c, .j
                ld   hl, LP_DISCARD
                inc  (hl)
                scf
                jr   .x
.ok:            ld   b, a
                ld   a, (LP_SIG)
                add  a, d
                ld   (LP_SIG), a
                ld   a, b                      ; (add: no carry, sum <= 12)
                or   a
.x:             pop  bc
                pop  de
                pop  hl
                ret
; .try: B = index, C = cap -> D = weight, A = kind; CF = cap < LP_SIG + weight + LP_RES
.try:           ld   a, b
                ld   hl, LP_KINDS
                call hla
                ld   a, (hl)
                push af
                ld   hl, lp_wt
                call hla
                ld   d, (hl)
                ld   a, (LP_SIG)
                add  a, d
                ld   hl, LP_RES                ; + the reservation for the units
                add  a, (hl)                   ;   still to roll (§9.4.3)
                ld   l, a
                ld   a, c
                sub  l
                pop  hl
                ld   a, h                      ; (ld keeps the flags)
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
                xor  a
                ld   (LP_BEST), a
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
                ld   a, c                      ; only the gap: same x, other storey
                xor  1                         ; (no new RNG step; no gap rule there)
                ld   c, a
                call lp_legal
                jr   c, .n
.lg:
                ld   a, (LPV_BOSS)
                or   a
                jr   z, .first
                ld   a, (LP_HX)
                sub  e
                jr   nc, .ab
                neg
.ab:            ld   d, a
                ld   a, (LP_HS)
                cp   c
                ld   a, d
                jr   z, .ss
                add  a, 32
.ss:            inc  a                         ; distance + 1 (>= 1)
                ld   hl, LP_BEST
                cp   (hl)
                jr   z, .n
                jr   c, .n                     ; not strictly farther
                ld   (hl), a
                ld   a, c
                ld   (LP_BS), a
                ld   a, e
                ld   (LP_BX), a
.n:             pop  bc
                djnz .t
                ld   a, (LP_BEST)
                or   a
                scf
                ret  z
                ld   a, (LP_BS)
                ld   c, a
                ld   a, (LP_BX)
                ld   e, a
                or   a
                ret
.first:         pop  hl                        ; drop the saved BC: C = s stays
                ret                            ; (NC from the or)

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
                ld   a, c
                cp   2
                jr   c, .s
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
                sub  2
                ld   c, 0
                call lp_mark
                ld   a, d
                add  a, 2
                ld   b, a                      ; s1: the fall's landing cols p..p+W-1, +-1
                ld   a, (ix+RD_PITCOL)
                dec  a
                ld   c, 1
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
                and  1
                ld   c, a                      ; storey (RDB_S1 = bit 6)
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
                and  RDX_LS1
                jr   z, $+4
                ld   a, 1
                ld   c, a
                ld   a, 1
                ld   b, 4
                call lp_mark                   ; cols 1..4
.ar2:           bit  1, d                      ; RDX_R
                jr   z, .gp
                ld   a, d
                and  RDX_RS1
                jr   z, $+4
                ld   a, 1
                ld   c, a
                ld   a, 27
                ld   b, 4
                call lp_mark                   ; cols 27..30
.gp:            ret
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
                ASSERT RDB_WMASK == 3 && LP_CMW == 33

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
                ld   a, (LP_HS)                ; arrival storey: body gap >= LP_GAPV
                cp   c
                jr   nz, .ok
                ld   a, (LP_HX)
                ld   hl, LP_HW
                add  a, (hl)
                ld   hl, LP_GAPV
                add  a, (hl)
                ld   b, a                      ; hx + hw + g
                ld   a, e
                cp   b
                jr   nc, .ok                   ; right of the hero
                ld   a, (LP_W)
                add  a, e
                add  a, (hl)
                ld   b, a                      ; x + w + g
                ld   a, (LP_HX)
                cp   b
                jr   nc, .ok                   ; left of the hero
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
; LPV_ROOM, LP_W: the first free slot 1..15 (not EF_ACTIVE) is zeroed (+ its
; ST_* status bytes) and spawn_one'd (facing the hero: x > hx -> EF_LEFT;
; LEK_RESPAWN -> EF_RESPAWN), hp = the entry's; the body is marked LPC_BAD.
; CF = no free slot (nothing changed). Out: IX = the slot.
; Clobbers: A, BC, DE, HL, IX.   ~1.5k T
;------------------------------------------------------------------------------
lp_spawn:       ld   ix, P_ENTITIES + P_ENT_STRIDE
                ld   b, P_MAX_ENT - 1
                push de
                ld   de, P_ENT_STRIDE
.f:             bit  0, (ix+E_FLAGS)
                jr   z, .got
                add  ix, de
                djnz .f
                pop  de
                scf
                ret
.got:           pop  de
                push bc                        ; C = storey
                push de                        ; E = col
                ld   a, P_MAX_ENT
                sub  b                         ; slot
                ld   hl, ST_FLAGS
                call .st0
                ld   hl, ST_T1
                call .st0
                ld   hl, ST_T2
                call .st0
                ld   hl, ST_X
                call .st0
                push ix
                pop  hl
                ld   d, h
                ld   e, l
                inc  de
                ld   (hl), 0
                ld   bc, P_ENT_STRIDE - 1
                ldir
                pop  de
                pop  bc
                push de
                ld   a, (LP_W)
                ld   b, a
                ld   a, e
                ld   e, LPC_BAD                ; the body: no later unit overlaps it
                call lp_mark
                pop  de
                ld   a, (LP_HX)
                cp   e
                ld   b, 0
                jr   nc, .fr
                ld   b, EF_LEFT                ; hx < x: face left, toward the hero
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
                inc  hl
                ld   a, (hl)
                ld   (ix+E_HP), a              ; exact hp (FRESH: = the kind's)
                or   a                         ; NC
                ret
; .st0: HL = status array, A = slot: (HL + A) = 0. Keeps A.
.st0:           push af
                call hla
                ld   (hl), 0
                pop  af
                ret
