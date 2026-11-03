;==============================================================================
; trap2.asm — TOME-FX reclaim (bank-7 low block -16 B): trap7.asm's two leaf helpers, which touch no
; bank-7 data (TRAP_LIST / TRP_ENT are bank-5 low RAM), moved to bank 2 (always mapped: bank-7 code
; calls them with a plain CALL). Only with TOME_FX (main.asm); a trace test build (TOME_FX 0, 4 B of bank 2
; left) has trap7.asm INCLUDE this file instead: the same code in bank 7.
;------------------------------------------------------------------------------
; tr_ent — HL = the sequence's entry (TRP_ENT).  Clobbers: A
tr_ent:         ld   a, (TRP_ENT)
                ld   l, a
                ld   h, TRAP_LIST >> 8
                ret
; tr_type — HL = an entry: A = its TT_*.  Keeps HL.  Clobbers: F   (tr_col, trap7.asm, is the same shape)
tr_type:        inc  l
                ld   a, (hl)
                dec  l
                rlca
                rlca
                rlca
                and  7                         ; bits 5-7 -> 0-4 (STUN1: 3 bits)
                ret
                ASSERT TR_TYPE_SHIFT == 5 && TR_TYPE_MASK == $E0 && TR_B1 == 1 && (TRAP_LIST >> 8) == ((TRAP_LIST + 11) >> 8)
