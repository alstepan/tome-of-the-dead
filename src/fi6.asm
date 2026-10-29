;==============================================================================
; fi6.asm — FLOOR1 (game.md §8.11 Q1 rev 2026-10-26) the floor-item glyph
; cache, R6 (r6.asm rules: far6 only, results in memory, no SMC; bank 6 is
; uncontended: the per-pickup / per-drop update runs here).
; The cache (defs.asm FI_*, docs/memory-map.md "FLOOR1") holds, for ONE room
; (CUR_ROOM; EXIT_DEST during a scroll), up to FI_SLOTS distinct item types:
; per slot its 16x16 icon (copied from icons16, this region) and ink
; (item_ink), and per storey / col the slot of the item cell drawn there
; (FI_CELL). erase_rect (bank 2) draws from it on every restore of a marker
; cell; fi_cells (lowram) on the room draw and the scroll strips.
;   fi_add   far6 from bank-3 fi_full (fi3.asm: the cold from-scratch build,
;            one call per live entry) and from ap_stamp (bank 7); fi_gc: the
;            re-mark of the slots in use (dp_cap, uq_fit).
; Slot use: FI_USE[s] != 0 = slot s mapped this room visit (fi_full resets it);
; a type keeps its slot (and glyph), so only a NEW type copies 32 B.
;==============================================================================

;------------------------------------------------------------------------------
; fi_add — far6 from bank-3 fi_full (one call per live entry of the room, in
; list order: the last on a col wins) and from bank-7 ap_stamp (a col just
; changed: a pickup / a drop): A = col, D = the type to show there (the col's
; last live entry in list order; FI_NONE: none left — the map holds T_AIR,
; nothing to do), E = the FL_ROOM byte: the type's slot (fi_slot: a new type
; takes a free slot + its glyph) and the col's 4 cells.
; INVARIANT: a room holds <= FI_SLOTS distinct types (drop_put refuses a 9th,
; uq_fit displaces for a unique), so every live type has a slot and a pickup
; revealing the type under a pile always finds it; CF (no slot) can only follow
; a poked list. A slot stays in use until the next fi_full (room entry / pause
; / page) even if its type leaves the room: only dp_cap's fi_gc frees it.
; Clobbers: A, BC, DE, HL.   ~0.4k T (+0.8k a new type)
;------------------------------------------------------------------------------
fi_add:         ld   c, a
                ld   b, d
                ld   a, d
                cp   FI_NONE
                ret  z                         ; FI_NONE: no entry left at the col (NC)
                call fi_slot
                ret  c                         ; no slot left (CF)
                jr   fi_put

; fi_gc — A = room: FI_USE := in use only for the types some live entry of the
; room still has (a cheap re-mark, no glyph copies; the list is not otherwise
; touched). Keeps nothing.  ~3k T
fi_gc:          ld   c, a
                ld   hl, FI_USE
                ld   b, FI_SLOTS
                xor  a
.z:             ld   (hl), a
                inc  l
                djnz .z
                ld   hl, FLOOR_LIST
.l:             ld   a, (hl)
                and  FL_ROOM_MASK
                cp   c
                jr   nz, .n
                inc  l
                inc  l
                ld   a, (hl)                   ; FL_ITEM
                dec  l
                dec  l
                add  a, FI_TSLOT & $FF
                ld   e, a
                ld   d, FI_TSLOT >> 8
                ld   a, (de)
                cp   FI_SLOTS
                jr   nc, .n
                add  a, FI_USE & $FF
                ld   e, a
                ld   (de), a                   ; != 0: in use
.n:             ld   a, l
                add  a, FL_STRIDE
                ld   l, a
                jp   p, .l
                ret

;------------------------------------------------------------------------------
; fi_put — A = slot, C = col, E = the FL_ROOM byte: the col's 4 FI_CELL bytes
; (storey s's page FI_CELL + 256 s, by the map cells' low bytes: rows 9s+6 /
; 9s+7, cols c / c + 1) <- the FI_GLY low byte of each icon quarter: slot *
; 32 + 8 * (2 lower + half).  Keeps BC.  Clobbers A, DE, HL.
;------------------------------------------------------------------------------
fi_put:         rrca
                rrca
                rrca
                ld   d, a                      ; D = slot * 32 (the upper left quarter)
                ld   h, FI_CELL >> 8
                ld   a, e
                and  FL_S1
                jr   z, .s0
                inc  h                         ; storey 1's page
                ld   a, $20                    ; row 15: (15 & 7) << 5 = $E0 = $C0 + $20
.s0:            add  a, (STOREY_AIR - 2) << 5  ; row 6: $C0
                add  a, c
                ld   l, a
                ld   (hl), d                   ; UL
                inc  l
                ld   a, d
                add  a, 8
                ld   (hl), a                   ; UR
                ld   a, l
                add  a, ROOM_COLS - 1
                ld   l, a                      ; the row below, col c (16: wraps to $00 + c)
                ld   a, d
                add  a, 16
                ld   (hl), a                   ; LL
                inc  l
                add  a, 8
                ld   (hl), a                   ; LR
                ret
                ASSERT FL_S1 == $80 && (FI_CELL & $FF) == 0 && FI_END - FI_CELL == 512 && ICONS16_BYTES == 32 && STOREY_AIR == 8

;------------------------------------------------------------------------------
; fi_slot — B = type: NC + A = its slot (marked in use; a type not cached:
; the first free slot, the slot's old type unmapped, its ink + icon copied),
; CF = every slot in use (a 9th type).  Keeps BC, DE.  Clobbers A, HL.
;------------------------------------------------------------------------------
fi_slot:        ld   a, b
                add  a, FI_TSLOT & $FF
                ld   l, a
                ld   h, FI_TSLOT >> 8
                ld   a, (hl)
                cp   FI_SLOTS
                jr   nc, .new
                push af
                add  a, FI_USE & $FF
                ld   l, a
                ld   (hl), h                   ; != 0: in use
                pop  af
                or   a                         ; NC
                ret
.new:           push de
                push bc
                ex   de, hl                    ; DE = &FI_TSLOT[type]
                ld   hl, FI_USE
.f:             ld   a, (hl)
                or   a
                jr   z, .g
                inc  l
                ld   a, l
                cp   (FI_USE + FI_SLOTS) & $FF
                jr   nz, .f
                scf                            ; no slot left
                jr   .x
.g:             ld   (hl), h                   ; in use
                ld   a, l
                sub  FI_USE & $FF
                ld   c, a                      ; C = slot
                ld   (de), a                   ; FI_TSLOT[type] = slot
                add  a, FI_TYPE & $FF
                ld   l, a                      ; HL = &FI_TYPE[slot]
                ld   a, (hl)
                ld   (hl), b                   ; FI_TYPE[slot] = type
                add  a, FI_TSLOT & $FF         ; the old type (FI_NONE: FI_PAD)
                ld   e, a
                ld   d, h
                ld   a, FI_NONE
                ld   (de), a                   ; unmapped
                ld   a, b
                call item_ink                  ; (icons6.asm, R6; keeps BC, DE)
                ld   e, a                      ; FI_INK[slot * 32 ..+ 31] := the ink
                ld   a, c
                rrca
                rrca
                rrca
                ld   l, a
                ld   h, FI_INK >> 8
                ld   a, e
                push bc
                ld   b, ICONS16_BYTES
.ik:            ld   (hl), a
                inc  l
                djnz .ik
                pop  bc
                ld   a, b                      ; the icon: type - IT_BAG_LO; below it
                sub  IT_BAG_LO                 ; daggers / arrows -> the 2 floor-ammo
                jr   nc, .ix                   ; icons, the legacy IT_POTION -> Heal
                add  a, IT_BAG_LO - IT_DAGGER + ICONS16_AMMO_DAGGER
                cp   ICONS16_AMMO_DAGGER
                jr   nc, .ix
                ld   a, IT_P_HEAL - IT_BAG_LO
.ix:            call ic_addr                   ; HL = its 32 B (icons6.asm)
                ld   a, c
                rrca
                rrca
                rrca                           ; slot * 32
                ld   e, a
                ld   d, FI_GLY >> 8
                push bc                        ; (icons16 is laid out as 4 quarters of 8
                ld   bc, ICONS16_BYTES         ; contiguous lines: erase_rect steps E by 1)
                ldir
                pop  bc
                ld   a, c                      ; A = slot, NC (rrca left CF = slot bit 2: clear it)
                or   a
.x:             pop  bc
                pop  de
                ret
                ASSERT IT_POTION == 1 && IT_DAGGER == 2 && IT_ARROW == 3 && IT_DAGGER - 1 == IT_POTION
                ASSERT ICONS16_AMMO_ARROW == ICONS16_AMMO_DAGGER + 1
                ASSERT (FI_USE >> 8) == (FI_TSLOT >> 8) && (FI_INK & $FF) == 0
                ASSERT FI_PAD == FI_TSLOT - 1 && (FI_PAD >> 8) == (FI_TSLOT >> 8) && FI_NONE == $FF
                ASSERT (FI_GLY & $FF) == 0 && FI_SLOTS * ICONS16_BYTES == 256

;------------------------------------------------------------------------------
; uq_fit — (R6 since the 3F-T8 review: far6 from mon_drop; was bank 3) FLOOR1 invariant (a room holds <= FI_SLOTS = 8 distinct item types):
; before a boss unique is placed, if CUR_ROOM already holds 8 types the lowest-
; value ordinary item is DESTROYED so the unique always fits: the first live
; entry of the room (both storeys, list order) whose type is a potion / ammo /
; food (types IT_POTION..IT_P_CURE, not IT_KEY), then every entry of that type
; (the type must leave the room), each col re-stamped (ap_stamp: the pile's next
; item, else air). Always found: the generator places <= 7 entries (<= 7 types),
; so an 8th type is a monster drop, and monster drops are food / ammo / mana.
; (uq_tab types are unique ids: never already on the floor.) None found
; (poked list): nothing happens and drop_put refuses the unique (L = 0).
; Clobbers: all but IX.   fits ~0.2k T (all 8 slots marked: + ~3k T gc); a displacement ~+9k T per destroyed entry (ap_stamp)
;------------------------------------------------------------------------------
uq_fit:         call uq_chk
                ret  z                         ; a slot is unmarked: <= 7 types, it fits (~0.2k T)
                ld   a, (CUR_ROOM)
                call fi_gc                     ; FI_USE := the types the room holds (~3k T)
                call uq_chk
                ret  z                         ; (only stale slots were in use)
                ld   a, (CUR_ROOM)
                ld   c, a
                ld   hl, FLOOR_LIST
.v:             ld   a, (hl)
                and  FL_ROOM_MASK
                cp   c
                jr   nz, .nv
                inc  l
                inc  l
                ld   a, (hl)                   ; FL_ITEM
                dec  l
                dec  l
                ld   b, a
                cp   IT_KEY
                jr   z, .nv
                dec  a
                cp   IT_P_CURE
                jr   c, .d                     ; type 1 .. 12: the victim's type = B
.nv:            ld   a, l
                add  a, FL_STRIDE
                ld   l, a
                jp   p, .v
                ret
.d:             ld   hl, FLOOR_LIST            ; destroy every entry of the room with type B
.dl:            ld   a, (hl)
                and  FL_ROOM_MASK
                cp   c
                jr   nz, .dn
                inc  l
                inc  l
                ld   a, (hl)
                dec  l
                dec  l
                cp   b
                jr   nz, .dn
                ld   a, (hl)
                and  FL_ROOM_MASK | FL_S1
                ld   e, a                      ; E = room | storey
                inc  l
                ld   a, (hl)                   ; A = col
                dec  l
                ld   (hl), FL_EMPTY
                push bc
                push hl
                ld   hl, ap_stamp_a            ; bank 7: map + shadow + fi_add of the col's next
                call far7
                pop  hl
                pop  bc
.dn:            ld   a, l
                add  a, FL_STRIDE
                ld   l, a
                jp   p, .dl
                ld   a, FI_TSLOT & $FF         ; the victim type's slot is free again: drop_put's dp_cap
                add  a, b                      ; finds it at once (no second fi_gc, ~3k T)
                ld   l, a
                ld   h, FI_TSLOT >> 8
                ld   a, (hl)
                add  a, FI_USE & $FF
                ld   l, a
                ld   (hl), 0
                ret
; uq_chk — Z = some FI_USE slot is 0 (free: the room holds < 8 types, as every live type is marked).
uq_chk:         ld   hl, FI_USE
                ld   b, FI_SLOTS
.c:             ld   a, (hl)
                inc  l
                or   a
                ret  z
                djnz .c
                ret                            ; NZ: all 8 marked
                ASSERT (FI_USE >> 8) == (FI_TSLOT >> 8) && FI_SLOTS < 256 - (FI_USE & $FF)
                ASSERT IT_KEY == 4 && IT_P_CURE == 12 && IT_POTION == 1 && IT_F_CARROT == IT_KEY + 1 && IT_P_HEAL == IT_F_MEAT + 1
                ASSERT (FLOOR_LIST & $FF) == 0 && FLOOR_MAX * FL_STRIDE == $80 && FL_COL == 1 && FL_ITEM == 2
