;------------------------------------------------------------------------------
; es_stats — STATS1 S1 (user 2026-11-01): far7 from end_card (menu1.asm, bank 1; the bank-7 HIGH
; block): rows ES_ROW "KILLS n" and ES_ROW + 1 "TURNS n" of the end card (the BEST KILL row is
; combat3.asm es_best). The values are the hero's kill count (ST1_KILLS, kill_note) and
; TURN_COUNTER. Clobbers: all but IX, IY.   ~3k T (once, at the end card)
;------------------------------------------------------------------------------
es_stats:
                ld   hl, (ST1_KILLS)
                ld   a, TX_END_KILLS
                ld   b, ES_ROW
                call es_item
                ld   hl, (TURN_COUNTER)
                ld   a, TX_END_TURNS
                ld   b, ES_ROW + 1
                jp   es_item
