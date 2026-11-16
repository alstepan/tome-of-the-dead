;==============================================================================
; keyui1.asm — LARGER-D T8: the bag page's key lines (bank 1, INCLUDEd by ui1.asm). Called directly
; by the page overlay (page_ovl.asm runs with BANK_UI1 paged; bank 1 instead of the overlay: the
; packed overlay stream sits in bank-0 B0_CODE2, which had no room).
;==============================================================================
pg_s_kcy:       DB   "CYAN KEY", 0
pg_s_kmg:       DB   "MAGENTA KEY", 0
                ASSERT LF_KEYC == $40 && LF_KEYM == $80

;------------------------------------------------------------------------------
; pg_key — LARGER-D T8: HL = a key line, B = its row, C = its attr: printed at PG_KEY_COL, its cells
; stamped C. Out: B = the next key line's row.  Clobbers: A, C, DE, HL.
;------------------------------------------------------------------------------
pg_key:         push bc
                ld   e, PG_KEY_COL * 8
                call print6
                pop  bc
                push bc
                ld   a, c
                ld   c, PG_KEY_COL
                ld   de, (PG_KEY_W << 8) | 1
                call stamp_rect
                pop  bc
                inc  b
                inc  b                         ; row 2 is the ornament
                ret
