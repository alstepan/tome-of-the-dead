;==============================================================================
; sq0.asm — the 3F-T2 SEQUENCE CACHE loader (docs/memory-map.md "Sequence cache (3F-T2)",
; "NEW-MON3 T10b ledger"). Bank-0 B0_CODE2 (low RAM until NEW-MON3 T10b): entered by
; FARB0 from R6 pool6.asm (pool_hero / pool_proto / pool_list) after the masters are
; unpacked to SQ_IMG; reads only low RAM (the image, the SQ_* scratch) and writes
; bank 2 (seq_rows, the hero block, seq_bytes, kind_tab KT_SEQ) and low-RAM region 2
; (seq2_bytes). Generator-session code. B0_CODE2 rules: no SMC, never pages $C000.
;
; TWO BYTE REGIONS (T10b: the FRT page went $A600 -> $A500 for the 10 new frames; seq_rows +
; the hero's block moved into FRT_GAP above the FRT, and the bank-2 bytes below the FRT
; shrank): a master block at or after ksm_r2 in the image (seq_img.asm: the blocks after
; that label) goes to REGION 2 (seq2_bytes, low RAM, SEQ2_LEN); every other block to
; region 1 (seq_bytes, bank 2, SEQB_LEN). The split is static per block, so the per-depth
; need is order-independent: main.asm "SEQ CACHE NEED" ASSERTs both sums.
;==============================================================================
; sq_reset — no slot cached, both regions empty, then the hero's block -> slot 0
; (SEQH_BYTES: FRT_GAP, after seq_rows). Clobbers: A, BC, DE, HL.
sq_reset:
                ld   hl, seq2_bytes
                ld   (SQ_TOP2), hl
                ld   hl, SEQH_BYTES
                ld   (SQ_TOP), hl
                ld   hl, SQ_PTR
                ld   b, 2 * SQ_SLOTS
.z:             ld   (hl), 0
                inc  hl
                djnz .z
                ld   a, (HERO_KIND)
                call sq_load                   ; (the hero blocks lie before ksm_r2: region 1, ASSERTed in seq_img.asm)
                ld   hl, seq_bytes
                ld   (SQ_TOP), hl
                ret
;------------------------------------------------------------------------------
; sq_kind — A = a level kind: sq_load, the Vampire's bat form first (3F-T9: K_VBAT's
; KT_SEQ). R6 pl_kinds: one FARB0 a kind.  Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
sq_kind:
                cp   K_VAMPIRE
                jr   nz, sq_load
                ld   a, K_VBAT
                call sq_load
                ld   a, K_VAMPIRE
                ; fall through
;------------------------------------------------------------------------------
; sq_load — A = kind: its master block (ksm_tab; none = no-op) -> the first
; free cache slot, unless a slot holds it already: row = 8 pointers (SQ_TOP +
; offset) + KS_IMPACT, the sequence bytes copied to SQ_TOP. No free slot:
; SEQ_TRAP++ (the build ASSERTs <= SQ_SLOTS - 1 monster blocks per level and the
; byte need, main.asm "SEQ CACHE NEED").   Clobbers: A, BC, DE, HL.   ~2k T
; T10b: a region-2 block (address >= ksm_r2) swaps SQ_TOP / SQ_TOP2 around sq_ld1 (+~0.2k T;
; a 0 = no-block kind takes region 1, then sq_ld1's trap).
;------------------------------------------------------------------------------
sq_load:
                ld   b, a
                call ksm_ptr                   ; DE = the block
                ld   hl, -ksm_r2 & $FFFF
                add  hl, de                    ; CF = DE >= ksm_r2: region 2
                ld   a, b
                jr   nc, sq_ld1
                call sq_swap
                call sq_ld1
sq_swap:        ld   hl, (SQ_TOP)              ; SQ_TOP <-> SQ_TOP2
                ld   de, (SQ_TOP2)
                ld   (SQ_TOP), de
                ld   (SQ_TOP2), hl
                ret
sq_ld1:
                call ksm_ptr                   ; DE = the block (0: none)
                ld   a, d
                or   e
                jr   z, .trap                  ; (build-ASSERTed never: every level kind has one)
                ld   hl, SQ_PTR
                ld   b, SQ_SLOTS
.s:             ld   a, (hl)
                inc  hl
                or   (hl)
                jr   z, .free                  ; 0: free (the used slots come first)
                dec  hl
                ld   a, (hl)
                inc  hl
                cp   e
                jr   nz, .nx
                ld   a, (hl)
                cp   d
                ret  z                         ; cached already
.nx:            inc  hl
                djnz .s
.trap:          ld   hl, SEQ_TRAP              ; full (build-checked: never) / no block: the kind
                inc  (hl)                      ; would blit the hero's row (debug trap, saturating)
                ret  nz
                dec  (hl)
                ret
.free:          ld   (hl), d                   ; slot := the block
                dec  hl
                ld   (hl), e
                ld   a, SQ_SLOTS               ; slot index = SQ_SLOTS - B
                sub  b
                ld   c, a                      ; row = seq_rows + 17 * slot
                add  a, a
                add  a, a
                add  a, a
                add  a, a
                add  a, c
                add  a, seq_rows & $FF         ; (one page, ASSERTed at seq_rows)
                ld   l, a
                ld   h, seq_rows >> 8
                push de                        ; row: 8 x (SQ_TOP + offset)
                ex   de, hl                    ; DE = row, HL = block
                inc  hl                        ; KSM_IMP
                ld   c, (hl)                   ; C = impact
                inc  hl                        ; KSM_OFF
                ld   b, 8                      ; (C = impact kept)
.r:             ld   a, (hl)
                inc  hl
                push hl
                ld   hl, (SQ_TOP)
                add  a, l
                ld   l, a
                jr   nc, .nc
                inc  h
.nc:            ex   de, hl
                ld   (hl), e
                inc  hl
                ld   (hl), d
                inc  hl
                ex   de, hl
                pop  hl
                djnz .r
                ld   a, c
                ld   (de), a                   ; KS_IMPACT
                pop  hl                        ; the block
                ld   c, (hl)                   ; KSM_LEN
                ld   b, 0
                ld   de, KSM_SEQ
                add  hl, de
                ld   de, (SQ_TOP)
                ldir
                ld   (SQ_TOP), de
                ret
                ASSERT KSM_LEN == 0 && KSM_IMP == 1 && KSM_OFF == 2 && KSM_SEQ == 10 && KS_IMPACT == 16 && KS_STRIDE == 17

; ksm_ptr — A = kind -> DE = its master block in SQ_IMG (ksm_tab; 0 = none).
; Clobbers: A, HL.
ksm_ptr:
                add  a, a
                ld   l, a
                ld   h, 0
                ld   de, ksm_tab
                add  hl, de
                ld   e, (hl)
                inc  hl
                ld   d, (hl)
                ret

;------------------------------------------------------------------------------
; sq_fill — kind_tab KT_SEQ := the low byte of each kind's cached row (no row
; for the kind's block: slot 0's, the hero — no entity of such a kind exists).
; Clobbers: A, BC, DE, HL.   ~10k T
;------------------------------------------------------------------------------
sq_fill:
                xor  a
.k:             push af
                call ksm_ptr                   ; DE = block
                ld   hl, SQ_PTR
                ld   bc, (SQ_SLOTS << 8) | (seq_rows & $FF)   ; B = slots, C = row low
                ld   a, d
                or   e
                jr   z, .set                   ; no block: slot 0's row
.s:             ld   a, (hl)
                inc  hl
                cp   e
                jr   nz, .n
                ld   a, (hl)
                cp   d
                jr   z, .set
.n:             inc  hl
                ld   a, c
                add  a, KS_STRIDE
                ld   c, a
                djnz .s
                ld   c, seq_rows & $FF         ; (not cached: slot 0)
.set:           pop  af
                ld   l, a
                add  a, KT_SEQ & $FF
                ld   e, a
                ld   d, (kind_tab + KT_SEQ) >> 8
                ld   a, c
                ld   (de), a
                ld   a, l
                inc  a
                cp   K_MAX
                jr   c, .k
                ret
