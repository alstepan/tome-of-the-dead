;==============================================================================
; theme7.asm - half-row flames: the attr-patch tail of level_tiles7 (tiles7.asm), moved to the low bank-7
; block (the high block TSET_BASE..$FFFF was 8 B over with the extra flame glyph; this block had 31 B free).
; Same bank, so level_tiles7 reaches it with plain CALL / JP; reached only through far7.
;------------------------------------------------------------------------------
; level_patch7w / level_patch7 - the common floor / wall ids' attrs := LVL_ATTR_FLOOR / LVL_ATTR_WALL:
; level_patch7: A = attr -> TILE_ATTRS[id] for the ids at HL up to a 0 (T_AIR), HL left after the 0;
; level_patch7w: the wall list (A loaded here). Clobbers: A, DE, HL.   ~0.3k T, once a level
;------------------------------------------------------------------------------
level_patch7w:
                ld   a, (LVL_ATTR_WALL)
level_patch7:
                ld   e, (hl)
                inc  hl
                inc  e
                dec  e
                ret  z
                ld   d, TILE_ATTRS >> 8
                ld   (de), a
                jr   level_patch7
