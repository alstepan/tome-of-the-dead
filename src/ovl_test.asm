;==============================================================================
; ovl_test.asm — 3E-T1 self-test overlay (tests/ovl.py), assembled at
; GEN_SCRATCH (main.asm "OVERLAYS"), stored ZX0-packed in bank 1
; (ovl_test_zx0), run through ovl_run. It records the $C000 bank it was
; entered with and the IX it got, then pages BANK_POOL1 (ovl_run must hand
; the caller's bank back anyway) and returns fixed BC / DE / HL (they must
; pass out). The results live in its own image (ovl_t_res, 3 B), which the
; test reads before anything reuses the window.
; In: IX = any.  Out: BC $9ABC, DE $5678, HL $1234.  Clobbers: A, F, BC, DE, HL.
;==============================================================================
                ld   a, (PORT_7FFD_SHADOW)
                ld   (ovl_t_res), a            ; the bank at entry (ovl_run: the caller's)
                ld   (ovl_t_res + 1), ix
                ld   a, BANK_POOL1
                call page_bank
                ld   bc, $9ABC
                ld   de, $5678
                ld   hl, $1234
                ret
ovl_t_res:      DB   0, 0, 0                   ; shadow at entry, IX (written at run time)
