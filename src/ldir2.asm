;==============================================================================
; ldir2.asm — RECLAIM-C (d): bank-2 helpers for paged-bank code that must read
; another $C000 bank. LAST code in the bank-2 image (before ftz_zx0): adding
; here moves no other bank-2 symbol (the overlay / R6 streams that call bank-2
; code repack identically).
;==============================================================================
;------------------------------------------------------------------------------
; ldir7 — RECLAIM-C (d): copy BC bytes from bank-7 HL ($C000+, e.g. the tilesets)
; to DE in bank 2 / 5 RAM, then hand $C000 back as it was (restore_page): for
; paged-bank code (bank-1 menu_static: the torch's static cells, a tset_pool run).
; Cold. Clobbers: A, F, BC, DE, HL (DE / HL past the copy).   ~0.2k T + 21 T/byte
;------------------------------------------------------------------------------
ldir7:
                ld   a, (PORT_7FFD_SHADOW)
                push af                        ; caller's page (restore_page)
                push bc                        ; page_bank uses BC
                ld   a, BANK_TSET
                call page_bank
                pop  bc
                ldir
                pop  af
                jp   restore_page
