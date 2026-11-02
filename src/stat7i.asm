;------------------------------------------------------------------------------
; es_item — STATS1 S1 (bank 7 low block): A = the label's TX id, B = the char row, HL = the value
; (0..65535): the label at ES_LX (print6x), its decimal (es_num, no leading zeros) at ES_VX
; (print6t, composed in MSG_BUF). Both printers hand bank 7 back. Clobbers: A, BC, DE, HL.
;------------------------------------------------------------------------------
es_item:
                push bc                        ; the row
                push hl                        ; the value
                ld   e, ES_LX
                call print6x
                pop  hl
                ld   de, MSG_BUF
                call es_num                    ; (low RAM, lowram.asm; writes the 0 too)
                ld   hl, MSG_BUF
                pop  bc
                ld   e, ES_VX
                jp   print6t
