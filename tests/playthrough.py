#!/usr/bin/env python3
"""T14: end-to-end playthrough bot (release build, -DDEBUG_KIT=0), ZRCP-driven.  See docs notes in
docs/t14-playthrough.md for the design, the poke ledger and the results.

A deterministic bot plays a real run from the menu: new game (SEED_FIXED via the seed_fixed / seed_value
pokes, proto_start = 0), D1 -> D8 -> GS_WIN (or the GS_DEAD variant), for either hero.  Everything that is
gameplay runs on the game's own code paths (combat, abilities, XP, pickups, hunger, the bag page, room
changes, room-mem re-entry, bosses, the Archmage, the sealed door, the Tome, the D8 gate, the end card).
Pokes (counted and printed per run): "nav" (hero position inside the current room after a stuck streak),
"god_hp" / "god_food" (only when the bot would otherwise die / starve; --no-god forbids them),
"dead_hp" (the GS_DEAD variant squeezes HP to 2 at D3).

Per-tick monitor (tests/pt_mon.py): tick work vs 141,816 T, SYS_FRAMES vs AY_CALLS, GAME_STATE, GEN_OVERFLOW,
bank-7 code hash, entity slots, TOME state, border, log text, [ANOMALY] lines.

Run:  tools/build.sh -o DIR -DDEBUG_KIT=0 ; WZ_BUILD_DIR=DIR/build ZRCP_PORT=<port> python3 tests/playthrough.py
        [--hero W|M] [--seed 0x1234] [--mode win|dead] [--no-god] [--start-depth N] [--max-ticks N]
Never port 10000.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pt_plan import *  # noqa: F401,F403,E402
from pt_plan import Player, RunEnd, S, K_KNIGHT, K_WIZARD, GS_SELECT, GS_PLAYING, Mon, PT, Harness, EMU_ARGS  # noqa: E402
import pt_mon  # noqa: E402
from lp import w16  # noqa: E402


def new_game(p, hero, seed):
    p.proto_start = 0
    p.snd_mode = None                         # music on: the real descent stinger wait, the AY in use
    p.load()
    p.wait_state(GS_SELECT)
    p.wb("seed_fixed", 1)
    p.z.cmd("write-memory %d %d %d" % (S["seed_value"], seed & 255, seed >> 8))
    p.wb("INPUT_REPEAT", 0)
    p.wb("ANIM_FREEZE", 0)
    p.wb("INPUT_SRC", 1)
    p.menu_start(hero)


def run(hero_name, seed, mode, god, start_depth, max_ticks, level_cap, boss_hp1=False, boss_fb=60):
    hero = K_KNIGHT if hero_name == "W" else K_WIZARD
    t0 = time.time()
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = PT(h)
        p.mon = Mon(p)
        new_game(p, hero, seed)
        if start_depth > 1:                    # debugging aid / targeted D8 runs: level_descend from depth N-1 (a poke)
            pc0 = p.pc()
            ok, _ = p.code([0x3E, start_depth - 1, 0x32] + w16(S["LVL_DEPTH"]) + [0xCD] + w16(S["level_descend"]),
                           game=True)
            p.z.cmd("set-register PC=%d" % pc0)
            p.release()
            p.settle(4)
            print(f"[poke] depth skip: level_descend from D{start_depth - 1}: ok={ok} depth now {p.rb('LVL_DEPTH')}",
                  flush=True)
        bot = Player(p, hero, mode=mode, god=god, max_ticks=max_ticks, level_cap=level_cap)
        bot.boss_poke = True if boss_hp1 else boss_fb
        end = bot.play()
        bot.finish_level()
        return report(p, bot, end, time.time() - t0, hero_name, seed, mode)


def report(p, bot, end, wall, hero_name, seed, mode):
    m = p.mon
    gs = p.rb("GAME_STATE")
    p.tick(6)
    ends = {pt_mon.GS_WIN: "GS_WIN", pt_mon.GS_DEAD: "GS_DEAD"}
    raw = bytes(p.z.read_memory(S["LOG_TXT"], pt_mon.LOG_SLOTS * pt_mon.LOG_SLOT_LEN))
    ring = [pt_mon.textpack.expand(pt_mon.IMG, raw[i * pt_mon.LOG_SLOT_LEN:][:pt_mon.LOG_SLOT_LEN])
            for i in range(pt_mon.LOG_SLOTS)]
    png = os.environ.get("PT_PNG")
    if png:                                    # the end card as displayed (bank 7 screen 2 while playing, else bank 5)
        from game_lib import frame_png
        frame_png(bytes(p.frame()), os.path.join(png, f"end_{hero_name}_{seed:#x}_{mode}.png"))
    res = dict(hero=hero_name, seed=hex(seed), mode=mode, end=end, game_state=ends.get(gs, gs),
               depth=p.rb("LVL_DEPTH"), hero_level=p.rb("LVL"), turns=p.rw("TURN_COUNTER"),
               ticks=m.ticks, max_tick_T_work=m.max_work_t, max_tick_T_any=m.max_t,
               over_budget=len(m.over), transitions=len(m.trans),
               max_transition_T=max([t for t, _ in m.trans] or [0]),
               violations={k: len(v) for k, v in m.viol.items()}, anomalies=pt_mon.Proto.anomalies,
               pokes=dict(bot.pokes), kills=p.rw("ST1_KILLS"), end_shown=p.rb("END_SHOWN"),
               levels=bot.levels, stats=dict(bot.stats), wall_s=round(wall), b7_checks=m.b7_checks,
               max_slots=m.max_ents, max_parked=m.max_parked, dframes=dict(m.dsf),
               tome=sorted(m.tome_seen.items()), border=dict(m.border_seen), tome_log=bot.tome_log,
               log_ring_at_end=ring, recent_log=list(m.recent), heaviest_ticks=m.top, hp_trace=list(m.hp_trace), room_changes=sum(1 for _, w in m.trans if w == "room change"),
               lines=len(m.lines), garbage=m.garbage[:5], slow_n=len(m.slow),
               slow_sample=m.slow[:25], slow_by_why=dict(__import__("collections").Counter(w for *_, w, _r in m.slow)))
    print("=" * 100)
    print(json.dumps(res, indent=1, default=str))
    print("distinct log lines:", sorted(m.lines)[:400])
    for k, v in m.viol.items():
        print("VIOLATION", k, v[:5])
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hero", default="W", choices=("W", "M"))
    ap.add_argument("--seed", default="0x1234")
    ap.add_argument("--mode", default="win", choices=("win", "dead"))
    ap.add_argument("--no-god", action="store_true")
    ap.add_argument("--boss-hp1", action="store_true", help="debugging aid: Archmage HP poked to 1 when first fought")
    ap.add_argument("--boss-fallback", type=int, default=60,
                    help="Archmage fallback: poke its HP to 1 after N god heals (or 160 N ticks) of fighting it; 0 = never")
    ap.add_argument("--start-depth", type=int, default=1)
    ap.add_argument("--max-ticks", type=int, default=900000)
    ap.add_argument("--level-cap", type=int, default=60000)
    a = ap.parse_args()
    if os.environ.get("ZRCP_PORT", "10000") == "10000":
        sys.exit("never port 10000: set ZRCP_PORT")
    for attempt in range(1, 4):                # the run is deterministic: an emulator that dies mid-run (socket
        try:                                   # reset / broken pipe seen under host load) is simply replayed
            res = run(a.hero, int(a.seed, 0), a.mode, not a.no_god, a.start_depth, a.max_ticks, a.level_cap,
                      a.boss_hp1, a.boss_fallback)
            break
        except (ConnectionError, BrokenPipeError, TimeoutError, RuntimeError) as exc:
            print(f"[EMU-DIED] attempt {attempt}: {type(exc).__name__}: {exc}: replaying the run", flush=True)
    else:
        sys.exit("emulator died 3 times")
    ok = (res["game_state"] == ("GS_WIN" if a.mode == "win" else "GS_DEAD")) and not res["violations"]
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
