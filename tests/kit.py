#!/usr/bin/env python3
"""DBG-1: the debug start kit + infinite lives (game.md §1.4 DEBUG_KIT), both builds.
Code: bank-0 src/kit0.asm kit_b0 (FARB0 from R6 pickup6.asm kit_add), bank-7 bank7.asm
end_turn.dead (kit: the revive; release: GS_DEAD).

Kit build (DEBUG_KIT=1; GAME_ALLOW_DEBUG_KIT=1 needed, as for every suite):
  B   kit_b0 / KIT_LIST in the .sym, kit_b0 inside the bank-0 b0_code room
  K   the kit: Warrior HAS_BOW 1, ARROWS 20, DAGGERS 8, ARANK %0101, MP 20/20, worn Short +
      Leather, bag = base + extras (Helm, Bow, ...); Mage ARANK %0101010101, MP 40/40, worn
      Oak + Robe, bag = base + extras
  D   deal_hit 50 on the hero at 1 HP (DEATH reaction, EF_DYING, HP 0), then end_turn:
      HP 1, EF_DYING off, MODE REST, REACT none, GS_PLAYING; a real WAIT turn follows
  P   POISON at HP 1 over 8 real turns: HP 1, playing
  A   the Tome aura's kill (HP 1 -> 0, tome_aura's jp end_turn.dead): HP 1, playing
  F   hero_fall (1d4, no DEF) at HP 1 on storey 0, then end_turn: HP 1, playing
  R   real play: a Goblin next to the hero at 1 HP, 24 WAIT turns: it hit (HP 0 seen at a
      tick) and the hero is still at 1 HP and playing
Release build (DEBUG_KIT=0):
  N   no kit symbol (kit_b0, KIT_LIST, kit_bw, kit_bm, it_byte_live); KIT_DEBUG 0
  X   deal_hit 50 at 1 HP, then end_turn: GS_DEAD (the release death)
Run: tools/build.sh [-DDEBUG_KIT=0]; [GAME_ALLOW_DEBUG_KIT=1] ZRCP_PORT=<port> python3 tests/kit.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, K_GOBLIN, stand_y, RUN_LIMIT  # noqa: E402
from proj3 import T, w16  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
STRIDE = S["P_ENT_STRIDE"]
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT, EF_DYING = 1, 2, 4, 8, 16
GS_PLAYING, GS_DEAD = 2, 4
HY, HY0 = stand_y(1, 6), stand_y(0, 6)
HX = 12
NOWHERE = 7
STUB = S["LOWRAM_END_3B"]
I = lambda n: S["IT_" + n]                     # noqa: E731,E741
KIT_NAMES = ("kit_b0", "KIT_LIST", "kit_bw", "kit_bm", "it_byte_live")


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:600]}", flush=True)

        run(h, p, check)
        print(f"kit ({'kit' if KIT else 'release'} build): {len(fails)} failed"
              + (f": {fails[:10]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def run(h, p, check):
    WT = S["wait_tick"]
    z = p.z
    slots = {}

    def run_to_probe():
        for _ in range(4000):
            z.cmd("run %d" % RUN_LIMIT)
            if p.pc() in p.probes:
                return
            raise RuntimeError(f"stopped at {p.pc():#06x}")

    def tick(n=1):
        for _ in range(n):
            z.cmd("cpu-step")
            run_to_probe()
    p.tick = tick

    def stub(body):
        assert p.pc() == WT, hex(p.pc())
        p.wmem(STUB, body + [0xC3] + w16(WT))
        z.cmd("set-register PC=%d" % STUB)
        run_to_probe()
        assert p.pc() == WT, "stub did not return"

    def far7(label):
        stub([0x21] + w16(S[label]) + [0xCD] + w16(S["far7"]))

    def lethal():
        """deal_hit(IX = a parked Goblin, hero, 50 PHYS)."""
        inner = ([0xDD, 0x21] + w16(S["P_ENTITIES"] + slots[K_GOBLIN] * STRIDE)
                 + [0x3E, 0, 0x06, 50, 0x0E, 0, 0x1E, 0, 0xCD] + w16(S["deal_hit"]))
        stub(p.bank3(inner))

    def place(slot, x, y, flags, hp):
        p.set_ent(slot, X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=p.rb("CUR_ROOM"), FLAGS=flags, REACT=0,
                  FLT=0, HIT=0, HP=hp, MAXHP=hp)

    def scene(hero=K_KNIGHT, hp=1, y=HY):
        p.boot(hero)
        if not slots:
            for sl in range(1, 16):
                slots.setdefault(p.ent(sl)["KIND"], sl)
        room = p.rb("CUR_ROOM")
        for sl in range(1, 16):
            e = p.ent(sl)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                p.set_ent(sl, ROOM=NOWHERE)
        place(0, HX, y, EF_ACTIVE | EF_PLAYER, 40)
        p.set_ent(0, HP=hp)
        p.wmem(S["ST_FLAGS"], [0] * 16)
        p.wmem(S["ST_X"], [0] * 16)
        p.wb("FOOD", 80)
        p.tick(3)

    def alive(tag, extra=""):
        e = p.ent(0)
        ok = (e["HP"] == 1 and not e["FLAGS"] & EF_DYING and e["FLAGS"] & EF_ACTIVE
              and p.rb("GAME_STATE") == GS_PLAYING)
        check(tag + " HP 1, not DYING, GS_PLAYING" + extra, ok,
              dict(hp=e["HP"], flags=e["FLAGS"], mode=e["MODE"], react=e["REACT"], gs=p.rb("GAME_STATE")))
        return ok

    if not KIT:
        bad = [n for n in KIT_NAMES if n in S]
        check("N release: no kit symbols, KIT_DEBUG 0", not bad and S.get("KIT_DEBUG", 0) == 0, bad)
        scene()
        lethal()
        check("X release: the lethal hit -> HP 0 + EF_DYING", p.ent(0)["HP"] == 0 and p.ent(0)["FLAGS"] & EF_DYING)
        far7("end_turn")
        check("X release: end_turn -> GS_DEAD", p.rb("GAME_STATE") == GS_DEAD, p.rb("GAME_STATE"))
        return

    # --- B: placement ---
    check("B kit_b0 / KIT_LIST present, kit_b0 inside b0_code (bank 0)",
          all(n in S for n in KIT_NAMES) and S["b0_code"] <= S["kit_b0"] < S["b0_code_end"] <= S["POOL_START"])

    # --- K: the kit itself ---
    def bag():
        b = z.read_memory(S["BAG"], S["BAG_SLOTS"] * S["IR_STRIDE"])
        return [b[i] for i in range(0, len(b), S["IR_STRIDE"]) if b[i]]
    worn = lambda: [p.rb(S["WORN"] + i * S["IR_STRIDE"]) for i in range(2)]  # noqa: E731
    p.boot(K_KNIGHT)
    want = [I(n) for n in ("P_HEAL", "F_APPLE", "P_CURE", "P_MANA", "S_TELEPORT", "S_FEAR", "S_SLEEP",
                           "S_ENCHANT", "F_MEAT", "BOOK", "H_HELM", "BOW")]
    got = dict(bow=p.rb("HAS_BOW"), arr=p.rb("ARROWS"), dag=p.rb("DAGGERS"), arank=p.rw("ARANK") & 0x3FF,
               mp=(p.rb("MP"), p.rb("MAXMP")), worn=worn(), bag=bag())
    check("K Warrior kit (bow, 20 arrows, 8 daggers, ranks k0/k1, MP 20/20, worn + bag)",
          got == dict(bow=1, arr=20, dag=8, arank=0b0101, mp=(20, 20), worn=[I("W_SHORT"), I("A_LEATHER")],
                      bag=want), got)
    p.boot(K_WIZARD)
    want = [I(n) for n in ("P_HEAL", "P_MANA", "F_APPLE", "P_CURE", "S_TELEPORT", "S_FEAR", "S_SLEEP",
                           "S_ENCHANT", "F_MEAT", "BOOK", "H_HELM")]
    got = dict(arank=p.rw("ARANK") & 0x3FF, mp=(p.rb("MP"), p.rb("MAXMP")), worn=worn(), bag=bag())
    check("K Mage kit (5 spells rank 1, MP 40/40, worn + bag)",
          got == dict(arank=0b0101010101, mp=(40, 40), worn=[I("W_OAK"), I("A_ROBE")], bag=want), got)

    # --- D: a lethal hit, then end_turn ---
    scene()
    lethal()
    e = p.ent(0)
    check("D the lethal hit lands (HP 0, EF_DYING, DEATH reaction)",
          e["HP"] == 0 and e["FLAGS"] & EF_DYING and e["REACT"] & 0x7F == S["RC_DEATH"], e)
    far7("end_turn")
    if alive("D after end_turn:"):
        e = p.ent(0)
        check("D revived: MODE REST, REACT none", e["MODE"] == 0 and e["REACT"] == 0, e)
        check("D a real WAIT turn runs after the revive", p.turn("WAIT") and alive("D after the next turn:"))

    # --- P: poison at HP 1 ---
    scene()
    p.wb(S["ST_FLAGS"], S["STS_POISON"])
    p.wb(S["ST_X"], 12)
    for _ in range(8):
        p.turn("WAIT")
    alive("P poison 8 turns:")

    # --- A: the Tome aura's kill path ---
    scene()
    stub([0x21] + w16(S["P_ENTITIES"] + 5) + [0x35, 0x21] + w16(S["end_turn.dead"]) + [0xCD] + w16(S["far7"]))
    alive("A the aura's last hp (end_turn.dead):")

    # --- F: a pit fall at HP 1 ---
    scene(y=HY0)
    stub([0xDD, 0x21] + w16(S["P_ENTITIES"]) + [0xCD] + w16(S["hero_fall"]))
    e = p.ent(0)
    check("F hero_fall at HP 1 kills (HP 0, EF_DYING)", e["HP"] == 0 and e["FLAGS"] & EF_DYING, e)
    p.tick(40)                                  # the M_FALL drop + the DEATH reaction play
    far7("end_turn")
    alive("F after end_turn:")

    # --- R: real play, a Goblin next to the hero ---
    scene()
    g = slots[K_GOBLIN]
    place(g, HX + 4, stand_y(1, 4), EF_ACTIVE | EF_HOSTILE | EF_LEFT, 60)
    p.tick(2)
    seen = []
    for _ in range(24):
        p.turn("WAIT", per_tick=lambda fr, he: seen.append(he["HP"]))
        if 0 in seen or p.rb("GAME_STATE") != GS_PLAYING:
            p.turn("WAIT")
            break
    check("R the Goblin's hit took the hero to 0 HP (seen at a tick)", 0 in seen, sorted(set(seen)))
    alive("R real play:")


if __name__ == "__main__":
    sys.exit(main())
