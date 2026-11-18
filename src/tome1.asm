;==============================================================================
; tome1.asm — RECLAIM-SV R3: the P3 seal_open (was R6 tome6.asm), bank 1 (ui1.asm rules:
; far1 only; msg_push hands $C000 back). Entered by far1 from bank-7 grate_open (boss7.asm .seal).
;==============================================================================
;------------------------------------------------------------------------------
; seal_open — far1 (RECLAIM-SV R3; was far6) from bank-7 grate_open on D8 (F3_GEN; the Archmage's death
; does not open the D8 grate, the Tome's destruction does: tome_gone): the Archmage died — by any hand, its own Mirror Helm return
; included (deal_hit's kill -> mon_drop -> grate_open). Resident: nothing is
; unpacked on the death tick. LF_SEAL_OPEN; EG_SEAL off the lair<->Sanctum edge
; (EDGE_TAB + 6 = 9-10 or + 7 = 10-11 (LARGER-D T4): both bits cleared, cheaper than finding S's;
; the other edge never carries a seal), so the door is an ordinary closed door:
; it keeps its T_DOOR_LOCK plank on screen until a bump opens it (door_open reads
; the edge only; the planks then go as for any door). "THE SEAL BREAKS".
; Clobbers: A, BC, DE, HL.   ~1.5k T (the line)
;------------------------------------------------------------------------------
seal_open:
                ld   hl, LVL_FLAGS
                set  LF_SEAL_OPEN_BIT, (hl)
                ld   l, (EDGE_TAB + 6) & $FF
                res  EG_SEAL_BIT, (hl)
                inc  l
                res  EG_SEAL_BIT, (hl)
                ld   a, TX_SEAL_BREAKS
                jp   msg_push
                ASSERT (LVL_FLAGS >> 8) == ((EDGE_TAB + 7) >> 8) && LF_SEAL_OPEN == 1 << LF_SEAL_OPEN_BIT && GRID_BOT == 9
                ASSERT EG_SEAL == 1 << EG_SEAL_BIT
