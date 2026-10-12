;==============================================================================
; pickup7.asm — D3-7, bank 7 (bank7.asm rules: no data, no SMC): picking up
; dropped daggers / arrows (IT_DAGGER / IT_ARROW floor items, game.md §6.3:
; QUIVER FULL. when ammo stays on the floor). T0: stub, T1 implements it.
;==============================================================================

;------------------------------------------------------------------------------
; ammo_pickup — end_turn, after potion_pickup (far3). T0 stub: nothing.
; Clobbers: (T1 documents; end_turn needs nothing kept)
;------------------------------------------------------------------------------
ammo_pickup:
                ret
