;==============================================================================
; tiles7.asm — MEM-RECLAIM w2a: the level theme loader in bank 7 (was the body
; of the low-RAM level_load_tiles, B3B-8). Bank 7 is paged (far7), so the
; deduplicated tilesets (TSET_BASE, level_defs.asm) are read directly.
;==============================================================================

;------------------------------------------------------------------------------
; level_tiles7 — far7 from level_load_tiles: A = depth 1..8, or 0 = the PROTO
; rooms (D1's set). Gathers the depth's record: 32 glyphs tset_pool[GIDX[i]]
; -> TILE_LEVEL_GLYPHS, 32 attrs -> TILE_LEVEL_ATTRS, flag set FSET ->
; tile_flags + 32; then the common floor / wall ids' attrs := LVL_ATTR_FLOOR /
; LVL_ATTR_WALL (theme_ids, low RAM). Once per level, cold: LDIRs over LDI
; unrolls (bytes over T).
; Clobbers: A, BC, DE, HL.   ~17k T contended (32 x ~400 T gather + 2 x 32-B LDIR + patch), once a level
;------------------------------------------------------------------------------
level_tiles7:
                or   a
                jr   z, .s                     ; PROTO: record 0 (D1)
                dec  a                         ; record = depth - 1
.s:             ld   l, a
                ld   h, 0
                ld   e, l
                ld   d, h
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl                    ; slot * 64
                add  hl, de                    ; slot * 65 (TSET_STRIDE)
                ld   de, tset_slots
                add  hl, de                    ; HL = the record's GIDX bytes
                ld   de, TILE_LEVEL_GLYPHS
                ld   b, TILE_IDS - TILE_COMMON
.g:             push bc
                ld   a, (hl)                   ; pool index
                inc  hl
                push hl
                ld   l, a
                ld   h, 0
                add  hl, hl
                add  hl, hl
                add  hl, hl
                ld   bc, tset_pool
                add  hl, bc
                ld   bc, 8
                ldir                           ; DE steps on through the 256-B glyph page
                pop  hl
                pop  bc
                djnz .g
                ld   de, TILE_LEVEL_ATTRS      ; HL = +TSET_ATTRS
                ld   bc, TILE_IDS - TILE_COMMON
                ldir
                ld   l, (hl)                   ; HL = +TSET_FSET
                ld   h, b                      ; B = 0 after the LDIR
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl
                add  hl, hl                    ; set * 32
                ld   de, tset_fsets
                add  hl, de
                ld   de, tile_flags + TILE_COMMON
                ld   c, TILE_IDS - TILE_COMMON
                ldir
                ld   hl, theme_ids             ; common ids that follow the depth
                ld   a, (LVL_ATTR_FLOOR)
                call level_patch7              ; LOWER-FLAME exp.: the patch loop lives in the LOW bank-7 block
                jp   level_patch7w             ; (theme7.asm, same bank: the high block was 8 B over, the low had 31 free)
                ASSERT (TILE_ATTRS & $FF) == 0 && T_AIR == 0
                ASSERT ((tile_flags + TILE_IDS - 1) >> 8) == (tile_flags >> 8)
                ASSERT TSET_GIDX == 0 && TSET_ATTRS == TILE_IDS - TILE_COMMON && TSET_FSET == TSET_ATTRS + TILE_IDS - TILE_COMMON
                ASSERT TILE_LEVEL_ATTRS == TILE_ATTRS + TILE_COMMON
