;==============================================================================
; dzx0_standard.asm — VENDORED, code unmodified: ZX0 "standard" decoder (68 B)
; by Einar Saukas & Urusergi, https://github.com/einar-saukas/ZX0 at commit
; ecde3a2ae05061fe06469ed46df81a33b7de7d86 (the version tools/setup_zx0.sh pins,
; so the packer and this decoder always agree on the v2 format).
; BSD 3-Clause License, Copyright (c) 2021, Einar Saukas. All rights reserved.
; Redistribution and use in source and binary forms, with or without
; modification, are permitted provided that the BSD 3-Clause conditions are met
; (full text: https://github.com/einar-saukas/ZX0/blob/main/LICENSE, also
; tools/bin/ZX0-src/LICENSE after tools/setup_zx0.sh).
;
; Tome of the Dead use (lowram.asm, zx0_frame): HL = packed stream, DE = output.
; Out: HL = past the stream, DE = past the output.  Clobbers: AF, BC, DE, HL
; (IX/IY untouched; 2 stack words). Its only exit is the end marker's
; `inc c / ret z`, so it returns with C = 0 (ovl_run relies on it, 3E-T1). Forward, non-overlapping: the stream is in
; bank 1/3 at $C000+, the output in GEN_SCRATCH (bank 5). Cost ~LDIR rate for
; literal runs / matches + ~40 T per Elias-gamma bit pair.
;==============================================================================
dzx0_standard:
        ld      bc, $ffff               ; preserve default offset 1
        push    bc
        inc     bc
        ld      a, $80
dzx0s_literals:
        call    dzx0s_elias             ; obtain length
        ldir                            ; copy literals
        add     a, a                    ; copy from last offset or new offset?
        jr      c, dzx0s_new_offset
        call    dzx0s_elias             ; obtain length
dzx0s_copy:
        ex      (sp), hl                ; preserve source, restore offset
        push    hl                      ; preserve offset
        add     hl, de                  ; calculate destination - offset
        ldir                            ; copy from offset
        pop     hl                      ; restore offset
        ex      (sp), hl                ; preserve offset, restore source
        add     a, a                    ; copy from literals or new offset?
        jr      nc, dzx0s_literals
dzx0s_new_offset:
        pop     bc                      ; discard last offset
        ld      c, $fe                  ; prepare negative offset
        call    dzx0s_elias_loop        ; obtain offset MSB
        inc     c
        ret     z                       ; check end marker
        ld      b, c
        ld      c, (hl)                 ; obtain offset LSB
        inc     hl
        rr      b                       ; last offset bit becomes first length bit
        rr      c
        push    bc                      ; preserve new offset
        ld      bc, 1                   ; obtain length
        call    nc, dzx0s_elias_backtrack
        inc     bc
        jr      dzx0s_copy
dzx0s_elias:
        inc     c                       ; interlaced Elias gamma coding
dzx0s_elias_loop:
        add     a, a
        jr      nz, dzx0s_elias_skip
        ld      a, (hl)                 ; load another group of 8 bits
        inc     hl
        rla
dzx0s_elias_skip:
        ret     c
dzx0s_elias_backtrack:
        add     a, a
        rl      c
        rl      b
        jr      dzx0s_elias_loop
