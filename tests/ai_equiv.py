"""3F-B5 A/B equivalence: the same seeded walk / fight play on two builds must
leave the same entity state after every turn (ai_monster / attack_if_reach
refactors are behaviour-neutral).

Usage:
  python3 tests/ai_equiv.py BASE_BUILD_DIR [NEW_BUILD_DIR] [turns per run]
      runs the scenario on both builds (each in a child process with
      WZ_BUILD_DIR set; NEW defaults to ./build) and compares per turn.
  python3 tests/ai_equiv.py --record OUT [turns per run]
      (child) plays under the current WZ_BUILD_DIR, one JSON line per turn.

Per turn it records: every slot's KIND/ROOM/FLAGS/X/Y/HP/AIDIR (positions,
hp, facing = EF_LEFT in FLAGS, alive/pending/dying), RNG_STATE, CUR_ROOM,
TURN_COUNTER, GAME_STATE, ST_FLAGS (16 B), and a full 512-B P_ENTITIES hash
(reported separately: animation bytes may legitimately depend on frame
timing). The hero is healed to MAXHP before every turn (same poke on both
builds) so fights run long. Build both with -DDEBUG_KIT=0.
3F-T7: before every turn the shooter kinds (Archer, Sniper, Necromancer, Bone
Caller -> Orc; Slinger -> Goblin) are re-kinded on both builds, so the A/B
against a pre-T7 base proves the ranged hook neutral for every other kind (the
shooter path itself: tests/ranged.py A, the model A/B).
"""
import hashlib
import json
import os
import random
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = [  # (hero, proto, seed, depth): PROTO rooms A-D (ladders, B14 / B8 / squeeze
    # cases), generated D1, and D4 / D7 for the 3F walkers / climbers / flyers
    (0, 1, 11, 1), (1, 1, 12, 1), (0, 0, 13, 1), (1, 0, 14, 4), (0, 0, 15, 7), (1, 0, 16, 7)]
KEYS = ["L", "L", "L", "H", "H", "H", "K", "J", "K", "J", "WAIT", "SPACE", "SPACE"]
LOGIC = ("KIND", "ROOM", "FLAGS", "X", "Y", "HP", "AIDIR")


def record(out, nturns):
    sys.path.insert(0, str(HERE))
    import game_lib as GL
    from game_lib import Harness, S, EMU_ARGS, E, STRIDE
    from lp import T as Proto, w16
    GL.Proto.snd_mode = 2
    REKIND = {S[k]: S[v] for k, v in (("K_ARCHER", "K_ORC"), ("K_SNIPER", "K_ORC"), ("K_NECRO", "K_ORC"),
                                       ("K_BONE_CALLER", "K_ORC"), ("K_SLINGER", "K_GOBLIN"))}
    with Harness() as h, open(out, "w") as f:
        h.launch(EMU_ARGS)
        class P(Proto):                              # 3F-T7: a fixed master seed per run, so a
            seed = None                              # generated start does not depend on the build's
                                                     # boot timing (SYS_FRAMES at the hero choice)
            def load(self, attempts=3):
                super().load(attempts)
                if self.seed is not None:
                    self.wb("seed_fixed", 1)
                    self.wmem(S["seed_value"], w16(self.seed))
        p = P(h)
        for run, (hero, proto, seed, depth) in enumerate(RUNS):
            rnd = random.Random(seed)
            p.proto_start = proto
            p.seed = 0x2000 + seed
            p.boot(hero=hero, freeze=0)
            if depth > 1:
                p.wmem(S["MASTER_SEED"], w16(0x2000 + seed))
                pc0 = p.pc()
                ok, _ = p.code([0x3E, depth - 1, 0x32] + w16(S["LVL_DEPTH"])
                               + [0xCD] + w16(S["level_descend"]), game=True)
                p.z.cmd("set-register PC=%d" % pc0)
                p.release()
                p.settle(4)
            for t in range(nturns):
                if p.rb("GAME_STATE") != 2:
                    break
                p.wb(S["P_ENTITIES"] + E["HP"], p.rb(S["P_ENTITIES"] + E["MAXHP"]))
                for s_ in range(1, 16):              # 3F-T7: shooters re-kinded (the base build has no
                    ka = S["P_ENTITIES"] + s_ * STRIDE + E["KIND"]   # ranged hook): the A/B stays
                    k_ = p.rb(ka)                    # behaviour-neutral for every other kind
                    if k_ in REKIND:
                        p.wb(ka, REKIND[k_])
                k = rnd.choice(KEYS)
                p.turn(k, max_ticks=200)
                ents = bytes(p.z.read_memory(S["P_ENTITIES"], 16 * STRIDE))
                logic = [[ents[s * STRIDE + E[n]] for n in LOGIC] for s in range(16)]
                rec = dict(run=run, t=t, key=k, logic=logic,
                           rng=p.rw("RNG_STATE"), room=p.rb("CUR_ROOM"),
                           tc=p.rw("TURN_COUNTER"), gs=p.rb("GAME_STATE"),
                           st=list(p.z.read_memory(S["ST_FLAGS"], 16)),
                           full=hashlib.sha1(ents).hexdigest()[:12])
                if os.environ.get("AI_EQUIV_FULL"):  # 3F-T7 review: the full-hash diff offsets
                    rec["ents"] = ents.hex()
                f.write(json.dumps(rec) + "\n")
                f.flush()
            print(f"[rec] run {run} hero {hero} proto {proto} depth {depth}: {t + 1} turns", flush=True)


def child(build, out, nturns):
    env = dict(os.environ, WZ_BUILD_DIR=str(Path(build).resolve()))
    r = subprocess.run([sys.executable, __file__, "--record", out, str(nturns)], env=env)
    return r.returncode == 0


def main():
    if sys.argv[1] == "--record":
        record(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 350)
        return 0
    base = sys.argv[1]
    new = sys.argv[2] if len(sys.argv) > 2 else str(HERE.parent / "build")
    nturns = int(sys.argv[3]) if len(sys.argv) > 3 else 350
    tmp = Path(os.environ.get("TMPDIR", "/tmp"))
    fa, fb = str(tmp / "ai_equiv_base.jsonl"), str(tmp / "ai_equiv_new.jsonl")
    if not (child(base, fa, nturns) and child(new, fb, nturns)):
        print("ai_equiv: FAILED (a recording run failed)")
        return 1
    A = [json.loads(x) for x in open(fa)]
    B = [json.loads(x) for x in open(fb)]
    first = None
    full_diff = 0
    for a, b in zip(A, B):
        ka = {k: v for k, v in a.items() if k not in ("full", "ents")}
        kb = {k: v for k, v in b.items() if k not in ("full", "ents")}
        if ka != kb and first is None:
            first = (a, b)
        full_diff += a["full"] != b["full"]
    offs = {}
    for a, b in zip(A, B):
        if a["full"] != b["full"] and "ents" in a and "ents" in b:
            ea, eb = bytes.fromhex(a["ents"]), bytes.fromhex(b["ents"])
            for i in range(len(ea)):
                if ea[i] != eb[i]:
                    offs[i % 32] = offs.get(i % 32, 0) + 1
    if offs:
        print("ai_equiv: full-hash diffs by entity field offset (count):", dict(sorted(offs.items())))
    moved = sum(1 for i in range(1, len(A)) if A[i]["logic"] != A[i - 1]["logic"])
    ok = first is None and len(A) == len(B)
    print(f"ai_equiv: {len(A)} / {len(B)} turns, {moved} turns with entity change; "
          f"logic+RNG+status mismatches: {'none' if first is None else 'run %d turn %d' % (first[0]['run'], first[0]['t'])}; "
          f"full 512-B entity hash differs on {full_diff} turns")
    if first:
        print("  base:", json.dumps(first[0])[:400])
        print("  new: ", json.dumps(first[1])[:400])
    print("ai_equiv:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
