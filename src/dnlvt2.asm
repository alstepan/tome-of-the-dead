;==============================================================================
; dnlvt2.asm — LVL-FLOATER: dn_lvt (bank 2). Placed by main.asm: in the kind_tab
; ALIGN pad (after dnfix2.asm) normally; in the bank-2 tail (after dnum2b.asm)
; when ANIM_TRACE_ON (the trace leaves the pad 2 B: an overflow would push
; kind_tab a whole page).
;==============================================================================
;------------------------------------------------------------------------------
; dn_lvt — LVL-FLOATER, called by bank-0 dn_scan's .miss (a MISS-kind spawn for
; slot DN_CUR): DN_TXT := the 6-B text record (4 chars, 0, attr) and A := DNV_MISS
; for bank-3 dn_take (which reads the attr from DN_TXT + 5). "MISS" (dn_miss_s,
; kind_tab spare), or, when the slot is the hero's and his DS_FLG bit 7 is set
; (xp7: a level-up), "+LVL" in DNA_LVL and the bit consumed. A same-width text
; (4 chars = 3 cells), so the spawn path, merge ("replaced only") and placement
; are MISS's. Clobbers: A, BC, DE, HL.  ~0.25k T
;------------------------------------------------------------------------------
dn_lvt:
                ld   hl, DN_SLOT + DS_FLG      ; the hero's
                ld   a, (DN_CUR)
                or   a
                jr   nz, .m
                bit  DSF_LVL, (hl)
                jr   nz, .l
.m:             ld   hl, dn_miss_s
                jr   .c
.l:             res  DSF_LVL, (hl)
                ld   hl, dn_lvl_s
.c:             ld   de, DN_TXT
                ld   bc, 6
                ldir
                ld   a, DNV_MISS
                ret
dn_lvl_s:       DB   "+LVL", 0, DNA_LVL
