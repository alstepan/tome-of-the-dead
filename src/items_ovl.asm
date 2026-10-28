;==============================================================================
; items_ovl.asm — 3E-T6 the level-start item / trap generator OVERLAY
; (docs/memory-map.md "Overlays" + "3E contracts"; spec: tools/items_model.py
; rev 6, byte-exact, tests/items_gen.py; design game.md §8.11 "3E generation
; rulings" + "3E simplification (2026-10-20)", §8.5 / §1.5). Assembled at
; ITEMS_ORG (= GEN_SCRATCH), stored ZX0-packed in bank BANK_OVL_ITEMS (main.asm
; `ovl_items_zx0`), run by bank-3 `level_new` through ovl_run after level_gen
; + level_populate, before level_show's build_room_map. The caller is bank 3,
; so ovl_run enters with bank 3 paged and the overlay calls the bank-3
; generator helpers directly (rnd, rdp, hla, hits: none touches the LG_*
; scratch this window overwrites; lp_budget has consumed it already).
; Pages nothing.
;
; ig_main   In : the level_gen block (LVL_STATE..), MASTER_SEED, HERO_KIND.
;           The level on ITEM_RNG = LVL_SEED(master, depth|$80): potion types
;           (+ FLOOR1 the potion re-check), food, scrolls, gear, books, Warrior ammo /
;           the D2 bow + bundle, traps (per item: type / qty, then placement);
;           writes FLOOR_N + all 32 FLOOR_LIST entries (unused = FL_EMPTY x 4)
;           and TRAP_LIST / TRAP_N. A floor item is TYPE / QTY only (no ISTATE;
;           its ink is f(type): fl_attr, lowram.asm). ITEM_RNG runs in the
;           GEN_RNG word (bank-3 rnd reused as is); GEN_RNG is restored on the
;           only exit: every GEN_RNG-derived output stays.
;           Out: -. Clobbers: A, BC, DE, HL (IX kept).
; Cost: measured by tests/items_gen.py (worst case reported there).
;==============================================================================
PLACE_TRIES     EQU 2 * FEAT_TRIES      ; col tries per item (model PLACE_TRIES; FLOOR1: 8 -> 16, the 2-col footprint)
TRAP_TRIES      EQU 8
ITEM_COL_SPAN   EQU 28
TRAP_COL_LO     EQU 6                   ; t = 6 + rnd(20)
TRAP_COL_SPAN   EQU 20
ARROW_BUNDLE    EQU 6
BOW_DEPTH       EQU 2
BOOK2_DEPTH     EQU 4                   ; 2nd-book roll D4..D7
GT_W            EQU $40                 ; ig_gtab: Warrior-only weapon
GT_M            EQU $80                 ;          Mage-only weapon
GT_DMASK        EQU $0F                 ;          first depth
IG_GRP_N        EQU 3                   ; ig_grp descriptors: food, scrolls, gear
IG_GRP_LEN      EQU 5

ig_main:
                push ix
                ld   hl, (GEN_RNG)
                push hl                        ; restored at the (only) exit
                xor  a
                ld   (TRAP_N), a
                ld   a, (LVL_DEPTH)
                ld   (ig_d), a
                or   $80
                call ig_seed                   ; ITEM_RNG
                ; room pools (length-prefixed, id order): NS = present non-start,
                ; NL = NS minus the lair, ST = [start]
                ld   ix, ROOM_DESC
                ld   hl, ig_ns + 1
                ld   de, ig_nl + 1
                ld   c, 0
.r:             bit  0, (ix+RD_FLAGS)
                jr   z, .rn
                ld   a, (LVL_START)
                cp   c
                jr   z, .rn
                ld   (hl), c
                inc  hl
                ld   a, (LVL_LAIR)
                cp   c
                jr   z, .rn
                ld   a, c
                ld   (de), a
                inc  de
.rn:            push de
                ld   de, RD_STRIDE
                add  ix, de
                pop  de
                inc  c
                ld   a, c
                cp   GRID_CELLS
                jr   nz, .r
                ld   a, l
                sub  (ig_ns + 1) & $FF
                ld   (ig_ns), a
                ld   a, e
                sub  (ig_nl + 1) & $FF
                ld   (ig_nl), a
                ld   a, (LVL_START)
                ld   (ig_st + 1), a
                ; gear pool (no rolls): the §8 'Found' table, depth + class gated
                ld   a, (HERO_KIND)
                or   a
                ld   c, GT_M                   ; the Warrior skips Mage weapons
                jr   z, .gc
                ld   c, GT_W
.gc:            ld   ix, ig_gtab
                ld   hl, ig_gp + 1
                ld   a, (ig_d)
                ld   e, a
                ld   b, IG_GEAR_N
.g:             ld   a, (ix+0)
                and  c
                jr   nz, .gx
                ld   a, (ix+0)
                and  GT_DMASK
                dec  a
                cp   e                         ; first depth <= depth
                jr   nc, .gx
                ld   a, (ix+1)
                ld   (hl), a
                inc  hl
.gx:            inc  ix
                inc  ix
                djnz .g
                ld   a, l
                sub  (ig_gp + 1) & $FF
                ld   (ig_gp), a
                ; unused entries -> FL_EMPTY
                ld   a, (FLOOR_N)
                ld   (ig_n), a
                ld   b, a                      ; (potion count, below)
                add  a, a
                add  a, a
                ld   l, a
                ld   h, FLOOR_LIST >> 8
.fe:            ld   (hl), FL_EMPTY
                inc  l
                bit  7, l                      ; end of the 128-B list
                jr   z, .fe
                ; 1. potion types: entry 0 Heal (no roll), the others rnd(3)
                ld   hl, FLOOR_LIST + FL_ITEM
                ld   (hl), IT_P_HEAL
.pt:            dec  b
                jr   z, .pd
                ld   a, l
                add  a, FL_STRIDE
                ld   l, a
                push hl
                ld   a, IT_POT_HI - IT_POT_LO + 1
                call rnd                       ; (keeps BC)
                pop  hl
                add  a, IT_POT_LO
                ld   (hl), a
                jr   .pt
.pd:            ; FLOOR1: every GEN_RNG potion re-checked against the item rules
                ; (ig_ok: footprint c..c+1, c <= 28, no item within c-1..c+1, the
                ; room cap); an illegal one is re-placed in NS (scan fallback; same slot)
                ld   a, (ig_n)
                ld   b, a
                ld   hl, FLOOR_LIST
.pv:            ld   d, (hl)
                inc  l
                ld   e, (hl)
                dec  l
                ld   (hl), FL_EMPTY            ; (not its own neighbour)
                push hl
                push bc
                call ig_ok                     ; (keeps DE)
                jr   nc, .pk
                ld   hl, ig_ns
                call ig_place_s
.pk:            pop  bc
                pop  hl
                ld   (hl), d
                inc  l
                ld   (hl), e
                dec  l
                ld   a, l
                add  a, FL_STRIDE
                ld   l, a
                djnz .pv
                ; 2.-4. food, scrolls, gear: n = lo + rnd(2) items of a type roll each
.grp:           ld   ix, ig_grps
                ld   b, IG_GRP_N
.gg:            push bc
                call ig_grp
                ld   de, IG_GRP_LEN
                add  ix, de
                pop  bc
                djnz .gg
                ; 5. class books D1-D7: 1 (+1 on D4-D7 if rnd(2) == 0); D1: start room
                ld   a, (ig_d)
                cp   LEVELS
                jr   z, .ammo                  ; D8: none, no roll
                ld   b, 1
                cp   BOOK2_DEPTH
                jr   c, .b1
                ld   a, 2
                call rnd                       ; (keeps BC)
                or   a
                jr   nz, .b1
                inc  b
.b1:            ld   a, (ig_d)
                dec  a
                jr   nz, .bl
                ld   a, IT_BOOK                ; D1 (n = 1): start room, scan fallback,
                call ig_t1                     ; never dropped (§8.11 CHANGE)
                ld   hl, ig_st
                call ig_place_s
                call ig_app
                jr   .ammo
.bl:            push bc
                ld   a, IT_BOOK
                ld   hl, ig_ns
                call ig_add1
                pop  bc
                djnz .bl
                ; 6. Warrior, D1-D7: daggers 2 + rnd(2), arrows 5 + rnd(4) (NL);
                ;    D2: the bow (place, else scan) + the 6-arrow bundle in its cell
.ammo:          ld   a, (HERO_KIND)
                or   a
                jr   nz, .traps                ; the Mage consumes no rolls
                ld   a, (ig_d)
                cp   LEVELS
                jr   z, .traps
                ld   bc, (IT_DAGGER << 8) | 2  ; B = type, C = qty base (span 2)
                ld   a, 2
                call ig_ammo
                ld   bc, (IT_ARROW << 8) | 5   ; (span 4)
                ld   a, 4
                call ig_ammo
                ld   a, (ig_d)
                cp   BOW_DEPTH
                jr   nz, .traps
                ld   a, IT_BOW
                call ig_t1
                ld   hl, ig_nl
                call ig_place_s
                call ig_app                    ; (keeps DE)
                ld   a, IT_ARROW
                ld   (ig_t), a
                ld   a, ARROW_BUNDLE
                ld   (ig_q), a
                call ig_app
                ; 7. traps (§1.5): type rnd(pool), then <= 8 tries (room of the
                ;    eligible NL rooms without a trap, storey, t = 6 + rnd(20))
.traps:         ld   a, (ig_d)
                ld   hl, ig_tcnt - 1
                call hla
                ld   b, (hl)
.tl:            push bc
                ld   a, (ig_d)
                ld   hl, ig_tplen - 1
                call hla
                ld   a, (hl)
                call rnd
                ld   hl, ig_tord               ; STUN1: the pool is a prefix of DART GAS TELEPORT STUN ALARM
                call hla
                ld   a, (hl)
                ld   (ig_t), a                 ; consumed even if the trap drops
                ld   b, TRAP_TRIES
.tt:            push bc
                call ig_elig                   ; A = n eligible, Z = none
                jr   z, .tdrop
                call rnd
                ld   hl, ig_el + 1
                call hla
                ld   d, (hl)
                ld   a, 2
                call rnd
                rrca
                or   d
                ld   d, a                      ; D = room | storey << 7
                ld   a, TRAP_COL_SPAN
                call rnd
                add  a, TRAP_COL_LO
                ld   e, a
                call ig_trap_ok
                jr   nc, .tput
                pop  bc
                djnz .tt
                jr   .tnx
.tput:          ld   a, (TRAP_N)
                ld   c, a
                inc  a
                ld   (TRAP_N), a
                ld   a, c
                add  a, a
                add  a, TRAP_LIST & $FF
                ld   l, a
                ld   h, TRAP_LIST >> 8
                ld   a, d
                and  FL_ROOM_MASK
                bit  FL_S1_BIT, d
                jr   z, .t0
                or   TRF_S1
.t0:            ld   (hl), a
                inc  l
                ld   a, (ig_t)
                rrca
                rrca
                rrca                           ; type << TR_TYPE_SHIFT
                or   e
                ld   (hl), a
.tdrop:         pop  bc
.tnx:           pop  bc
                djnz .tl
                ld   a, (ig_n)
                ld   (FLOOR_N), a
                pop  hl
                ld   (GEN_RNG), hl
                pop  ix
                ret
                ASSERT TR_TYPE_SHIFT == 5 && FL_S1 == $80 && FL_ITEM == 2 && FL_COL == 1
                ASSERT FLOOR_MAX * FL_STRIDE == $80 && (FLOOR_LIST & $FF) == 0
                ASSERT (TRAP_LIST >> 8) == (TRAP_N >> 8)

;------------------------------------------------------------------------------
; ig_seed — A = d' (1..255): GEN_RNG := (MASTER_SEED + d' * LVL_SEED_MUL) ^
; (d' * $0101), 0 -> 1 (level_new + level_gen's derivation). Clobbers A, BC, DE, HL.
ig_seed:        ld   b, a
                ld   c, a
                ld   hl, (MASTER_SEED)
                ld   de, LVL_SEED_MUL
.m:             add  hl, de
                djnz .m
                ld   a, h
                xor  c
                ld   h, a
                ld   a, l
                xor  c
                ld   l, a
                or   h
                jr   nz, .s
                inc  l
.s:             ld   (GEN_RNG), hl
                ret

; ig_grp — IX = descriptor {n_lo, type_lo, k, DW pool-pointer variable}: n = n_lo + rnd(2) items, each type = type_lo + rnd(k)
; (k = 0: ig_gp[rnd(len)]), qty 1, place in the pool, append (or drop).
; Keeps IX. Clobbers A, BC, DE, HL.
ig_grp:         ld   a, 2
                call rnd
                add  a, (ix+0)
                ld   b, a
.l:             push bc
                ld   a, (ix+2)
                or   a
                jr   z, .gear
                call rnd
                add  a, (ix+1)
                jr   .t
.gear:          ld   a, (ig_gp)
                call rnd
                ld   hl, ig_gp + 1
                call hla
                ld   a, (hl)
.t:             ld   l, (ix+3)
                ld   h, (ix+4)
                ld   e, (hl)
                inc  hl
                ld   d, (hl)
                ex   de, hl                    ; HL = the pool
                push ix
                call ig_add1
                pop  ix
                pop  bc
                djnz .l
                ret

; ig_ammo — B = type, C = qty base, A = qty span: qty = C + rnd(A), place in
; NL, append (or drop).  Clobbers A, BC, DE, HL, IX.
ig_ammo:        call rnd                       ; (keeps BC)
                add  a, c
                ld   (ig_q), a
                ld   a, b
                ld   (ig_t), a
                ld   hl, ig_nl
                jr   ig_addq

; ig_t1 — A = type: ig_t = A, ig_q = 1.  Clobbers A.
ig_t1:          ld   (ig_t), a
                ld   a, 1
                ld   (ig_q), a
                ret

; ig_add1 — A = type, HL = pool: qty 1, place, append (or drop: rolls consumed).
; Clobbers A, BC, DE, HL, IX.
ig_add1:        call ig_t1
ig_addq:        call ig_place
                ret  c
                ; fall through
; ig_app — append (D, E, ig_t, ig_q) as entry ig_n. Keeps DE. Clobbers A, HL.
ig_app:         ld   hl, ig_n
                ld   a, (hl)
                inc  (hl)
                add  a, a
                add  a, a
                ld   l, a
                ld   h, FLOOR_LIST >> 8
                ld   (hl), d
                inc  l
                ld   (hl), e
                inc  l
                ld   a, (ig_t)
                ld   (hl), a
                inc  l
                ld   a, (ig_q)
                ld   (hl), a
                ret

; ig_place — HL = pool (length-prefixed): room = pool[rnd(n)], storey =
; rnd(2), then up to PLACE_TRIES x col = 2 + rnd(28), first free legal cell.
; Out: NC + D = room | storey << 7, E = col; CF = none (dropped).
; ig_place_s — the same, then the deterministic scan over the pool (bow,
; D1 book, a re-placed potion: never dropped).  Clobbers A, BC, DE, HL, IX.
ig_place_s:     call ig_place
                ret  nc
                ld   hl, (ig_pool)
                jr   ig_scan
ig_place:       ld   (ig_pool), hl
                ld   a, (hl)
                call rnd
                ld   hl, (ig_pool)
                inc  hl
                call hla
                ld   a, (hl)
                ld   (ig_r), a
                ld   a, 2
                call rnd
                rrca
                ld   hl, ig_r
                or   (hl)
                ld   (hl), a
                ld   b, PLACE_TRIES
.t:             push bc
                ld   a, ITEM_COL_SPAN
                call rnd
                add  a, ITEM_COL_LO
                ld   e, a
                ld   a, (ig_r)
                ld   d, a
                call ig_ok
                pop  bc
                ret  nc
                djnz .t
                ret                            ; CF from ig_ok

; ig_scan — HL = pool: first free legal cell, pool order, storey 0 then 1,
; col 2..29 (ig_ok refuses 29). Out as ig_place (CF only if the pool has none: unreachable).
ig_scan:        ld   b, (hl)
.r:             inc  hl
                push bc
                push hl
                ld   d, (hl)
.s:             ld   e, ITEM_COL_LO
.c:             call ig_ok
                jr   nc, .f
                inc  e
                ld   a, e
                cp   ITEM_COL_LO + ITEM_COL_SPAN
                jr   nz, .c
                bit  FL_S1_BIT, d
                set  FL_S1_BIT, d
                jr   z, .s
                pop  hl
                pop  bc
                djnz .r
                scf
                ret
.f:             pop  hl
                pop  bc
                ret                            ; NC

; ig_ok — D = room | storey << 7, E = col c: CF = illegal (FLOOR1 rules, model
; cell_legal + item_free): c > ITEM_COL_LAST; another entry of the storey
; within c-1..c+1 (ig_occ); the room (both storeys) already holds
; ITEM_ROOM_CAP entries (ig_cap); the footprint c..c+1 on levelgen.lp_hits
; (bank-3 `hits` = storey footprints f..f+2, storey-0 pit p-1..p+3, the
; storey's edge block) or, storey 0, on an L2 span (wide pit p-1..p+W,
; mid-block b-1..b+w). Keeps DE. Clobbers A, BC, HL, IX.
ig_ok:          ld   a, e
                cp   ITEM_COL_LAST + 1
                ccf
                ret  c
                ld   c, 3
                call ig_occ
                ret  c
                call ig_cap
                ret  c
                call ig_desc                   ; IX = the room's descriptor
                ld   a, d
                rlca
                and  1
                ld   c, a                      ; storey
                push de
                ld   d, e                      ; lo = c, hi = c + 1
                inc  e
                call hits                      ; (keeps BC)
                pop  de
                ret  c
                ld   a, c
                or   a
                ret  nz                        ; storey 1: done (NC)
                inc  e                         ; c..c+1 meets s-1..s+w <=> c+1 in s-1..s+w+1
                call .l2
                dec  e                         ; (keeps CF)
                ret
.l2:            ld   b, (ix+L2_PITW)
                inc  b
                dec  b
                jr   z, .mid                   ; narrow pit (or none): hits covered it
                ld   a, (ix+RD_PITCOL)
                or   a
                jr   z, .mid
                inc  b
                call ig_span
                ret  c
.mid:           ld   b, (ix+L2_MIDW)
                ld   a, (ix+L2_MIDB)
                or   a
                ret  z
                inc  b
                jr   ig_span
; ig_mid — storey 0: CF = E in the mid-block span b-1 .. b+w (IX = descriptor).
; Clobbers A, B.
ig_mid:         ld   b, (ix+L2_MIDW)
                ld   a, (ix+L2_MIDB)
                or   a
                ret  z
                ; fall through
; ig_span — A = c (!= 0), B = w, E = col: CF = c-1 <= col <= c+w
; (col - c + 1 < w + 2, unsigned). Clobbers A, B.
ig_span:        neg
                add  a, e
                inc  a                         ; col - c + 1
                inc  b
                inc  b
                cp   b
                ret

; ig_desc — D = room byte: IX = HL = &ROOM_DESC[room]. Clobbers A.
ig_desc:        ld   a, d
                and  FL_ROOM_MASK
                call rdp
                push hl
                pop  ix
                ret

; ig_occ — D = room | storey << 7, E = col, C = window (3: an item col in
; E-1..E+1, a new item; 2: in E-1..E, a trap col t inside a footprint): CF =
; a live entry 0..ig_n-1 of that storey there. Keeps DE, C. Clobbers A, B, HL.
ig_occ:         ld   a, (ig_n)
                or   a
                ret  z
                ld   b, a
                ld   hl, FLOOR_LIST
.o:             ld   a, (hl)
                cp   d
                jr   nz, .on
                inc  l
                ld   a, (hl)
                dec  l
                inc  a
                sub  e                         ; col - E + 1
                cp   c
                ret  c
.on:            ld   a, l
                add  a, FL_STRIDE
                ld   l, a
                djnz .o
                or   a
                ret

; ig_cap — D = room | storey << 7: CF = entries 0..ig_n-1 of the room (both
; storeys) number ITEM_ROOM_CAP already. Keeps DE. Clobbers A, BC, HL.
ig_cap:         ld   a, (ig_n)
                or   a
                ret  z
                ld   b, a
                ld   c, ITEM_ROOM_CAP
                ld   hl, FLOOR_LIST
.l:             ld   a, (hl)
                xor  d
                and  FL_ROOM_MASK              ; (FL_EMPTY: 15 ^ room != 0)
                jr   nz, .n
                dec  c
                scf
                ret  z
.n:             ld   a, l
                add  a, FL_STRIDE
                ld   l, a
                djnz .l
                or   a
                ret

; ig_elig — ig_el := the NL rooms without a trap (id order). Out A = n,
; Z = none. Clobbers A, BC, DE, HL.
ig_elig:        ld   hl, ig_nl
                ld   b, (hl)
                ld   de, ig_el + 1
.e:             inc  hl
                ld   c, (hl)
                push hl
                push bc
                ld   a, (TRAP_N)
                or   a
                jr   z, .ok
                ld   b, a
                ld   hl, TRAP_LIST
.u:             ld   a, (hl)
                and  TRF_ROOM_MASK
                cp   c
                jr   z, .no
                inc  l
                inc  l
                djnz .u
.ok:            ld   a, c
                ld   (de), a
                inc  de
.no:            pop  bc
                pop  hl
                djnz .e
                ld   a, e
                sub  (ig_el + 1) & $FF
                ld   (ig_el), a
                ret

; ig_trap_ok — D = room | storey << 7, E = t: CF = illegal (§1.5, model
; trap_col_ok): a storey footprint c (s0: up, arrival, ladders, pit; s1:
; down, exit, ladders) with c-1 <= t <= c+3; the pit zone p-1..p+(W or 3)
; on both storeys; s0 the mid-block b-1..b+w; the storey's edge block (right:
; t >= 30-w, left: t <= w+1); a floor item's footprint (c or c+1) on it.
; Clobbers A, BC, HL, IX.
ig_trap_ok:     call ig_desc
                inc  hl
                inc  hl                        ; RD_UPCOL
                ld   c, $75                    ; s0: UP, ARR, LAD1, LAD2, PIT
                bit  FL_S1_BIT, d
                jr   z, .l
                ld   c, $3A                    ; s1: DN, EXIT, LAD1, LAD2
.l:             srl  c
                jr   nc, .n
                ld   a, (hl)
                or   a
                jr   z, .n
                ld   b, PIT_W_NARROW           ; c-1 .. c+3
                call ig_span
                ret  c
.n:             inc  hl
                inc  c
                dec  c
                jr   nz, .l
                ld   a, (ix+RD_PITCOL)
                or   a
                jr   z, .mb
                ld   b, (ix+L2_PITW)
                inc  b
                dec  b
                jr   nz, .w
                ld   b, PIT_W_NARROW
.w:             call ig_span
                ret  c
.mb:            bit  FL_S1_BIT, d
                call z, ig_mid
                ret  c
                ld   a, (ix+RD_BLOCK)
                or   a
                jr   z, .fl
                ld   c, a
                rlca                           ; RDB storey bit 6 -> 7
                xor  d
                and  FL_S1
                jr   nz, .fl                   ; other storey
                ld   a, c
                and  RDB_WMASK
                ld   b, a
                bit  RDB_RIGHT_BIT, c
                jr   z, .lf
                ld   a, e
                add  a, b
                cp   30
                ccf
                ret  c                         ; t + w >= 30
                jr   .fl
.lf:            inc  b
                inc  b
                ld   a, e
                cp   b
                ret  c                         ; t < w + 2
.fl:            ld   c, 2                      ; FLOOR1: t != c, c + 1 of any item
                jp   ig_occ
                ASSERT RD_UPCOL == 2 && RD_DNCOL == 3 && RD_ARRCOL == 4 && RD_EXITCOL == 5
                ASSERT RD_LAD1 == 6 && RD_LAD2 == 7 && RD_PITCOL == 8 && RDB_S1 == $40
                ASSERT PIT_W_NARROW == 3

; --- data ---------------------------------------------------------------------
; ig_grp descriptors (game.md §8.5): n_lo (+ rnd(2)), type_lo, k (0 = the gear
; pool), DW the pool-pointer variable
ig_grps:        DB   3, IT_FOOD_LO, IT_FOOD_HI - IT_FOOD_LO + 1
                DW   ig_nsp                    ; food 3-4 (FLOOR1: the D8 lair allowed)
                DB   1, IT_SCR_LO, IT_SCR_HI - IT_SCR_LO + 1
                DW   ig_nsp                    ; scrolls 1-2 (lair allowed)
                DB   1, 0, 0
                DW   ig_nsp                    ; gear 1-2
                ASSERT $ - ig_grps == IG_GRP_N * IG_GRP_LEN
ig_nsp:         DW   ig_ns
ig_st:          DB   1, 0                      ; [start] (+1 written per level)
; §8 'Found' gear table (model GEAR_TABLE order): first depth | class flag, type
ig_gtab:        DB   2 | GT_W, IT_W_LONG
                DB   4 | GT_W, IT_W_AXE
                DB   2 | GT_M, IT_W_IRON
                DB   4 | GT_M, IT_W_RUNE
                DB   3, IT_A_CHAIN
                DB   6, IT_A_PLATE
                DB   1, IT_H_HOOD
                DB   1, IT_H_HELM
                DB   2, IT_C_MIGHT
                DB   2, IT_C_WARD
                DB   2, IT_C_FIRE
                DB   3, IT_C_MANA
                DB   3, IT_C_PLENTY
IG_GEAR_N       EQU ($ - ig_gtab) / 2
; §1.5 traps: count by depth; pool length (DART D1+, GAS D2+, TELEPORT D3+, STUN D4+, ALARM D5+)
; = a prefix of ig_tord (type = ig_tord[rnd(len)]; one draw, as before STUN1)
ig_tcnt:        DB   1, 2, 2, 3, 3, 3, 4, 4
ig_tplen:       DB   1, 2, 3, 4, 5, 5, 5, 5
ig_tord:        DB   TT_DART, TT_GAS, TT_TELEPORT, TT_STUN, TT_ALARM
                ASSERT TT_DART == 0 && TT_GAS == 1 && TT_TELEPORT == 2 && TT_ALARM == 3 && TT_STUN == 4
ig_image_end:
; --- scratch (past the stored image; inside the window) ------------------------
ig_d            EQU ig_image_end        ; depth
ig_n            EQU ig_d + 1            ; FLOOR_LIST entries used
ig_t            EQU ig_n + 1            ; type / trap type of the item being placed
ig_q            EQU ig_t + 1            ; qty
ig_r            EQU ig_q + 1            ; placement room | storey << 7
ig_pool         EQU ig_r + 1            ; word: the pool of the last ig_place
ig_ns           EQU ig_pool + 2         ; 1 + 9: present non-start rooms
ig_nl           EQU ig_ns + 10          ; 1 + 9: ... minus the lair
ig_el           EQU ig_nl + 10          ; 1 + 9: trap-eligible rooms
ig_gp           EQU ig_el + 10          ; 1 + IG_GEAR_N: gear pool
ig_end          EQU ig_gp + 1 + IG_GEAR_N
