#!/usr/bin/env python3
"""3E-T11: pickup into the BAG, the potion quick slot from the bag, the start
kit, monster drops and the boss unique (src/pickup7.asm floor_pickup /
pp_take, src/pickup6.asm (R6) pu_add / pot_pick / pot_take1 / kit_add / mon_drop /
drop_put, src/intent7.asm ic_quaff, src/itemname1.asm it_line). Played in
PROTO room A on a release build (DEBUG_KIT=0). Spec: game.md §8.11 "3E
pickup/drop rulings (2026-10-20)", Q10, Q11, §8 potions.

  K1  start kit: Warrior BAG Heal, Apple / WORN Short Sword, Leather / E_POT 1;
      Mage BAG Heal, Mana, Apple / WORN Oak Staff, Robe / E_POT 2
  P1  one item of each bag class stepped on (food, potion, scroll, book, weapon,
      armour, charm, bow): the bag record (type, qty 1, ISTATE 0), the line
      "YOU PICK UP <name>", the entry FL_EMPTY, the cell T_AIR + its attr
      shadow = TILE_ATTRS[T_AIR], E_POT follows the potions, the bow sets HAS_BOW
  P2  full bag: the item stays (entry, glyph), "BAG FULL" on the arrival only:
      a WAIT on it prints nothing, stepping off and back prints it again
  P3  stacking: Heal x8 + 1 -> 9; one more opens a new slot (stack cap 9)
  Q1  quick potion order Heal -> Mana -> Cure (bag order Cure, Mana, Heal):
      Heal +QUAFF_HEAL HP, Mana +8 MP (capped), Cure clears POISON / WEAK /
      MIND +4 HP; E_POT 3 -> 0 and the panel's drawn count
      (PANEL_POT_SH) follows; then G = NO POTION, no turn
  P2w walk across one item, full bag: one BAG FULL; off and back on: one more
  Q2  Heal at full HP, nothing else: NO NEED, no turn, the bag untouched
  Q3  a refused type is skipped (full HP: Mana next); all refused: NO NEED
  D1  a Rat killed by deal_hit, seed with rng_mod(4) == 0: FL entry {room|s,
      centre col, CHEESE, 1}, the cell shows T_FOOD, no log line; RNG == model
  D2  the same with a losing seed: no entry; RNG == model (one roll)
  D3  Skeleton Archer (K_ARCHER), Warrior: 3 arrows (1/2); Mage: no roll
  D4  body centre col taken by an entry: the drop goes to the nearest free col
  D5  FLOOR_LIST with 31 used: an ordinary drop is lost
  U1  the D1 lair boss (kind LP_BOSS in LVL_LAIR, LF_UNIQUE clear): KING HELM
      under it, "BOSS DROPS KING HELM", LF_UNIQUE set, no RNG used; the next
      Goblin kill there rolls the ordinary row
  U2  the unique with 31 entries used takes the 32nd
Run: ZRCP_PORT=<port> python3 tests/pickup3e.py
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from game_lib import Harness, S, EMU_ARGS, K_KNIGHT, K_WIZARD, K_RAT, K_GOBLIN, K_SKELETON, K_ARCHER, stand_y  # noqa: E402
from proj3 import T, w16, Rng  # noqa: E402
import textpack  # noqa: E402
import world  # noqa: E402

KIT = bool(S.get("KIT_DEBUG", 0))
EF_ACTIVE, EF_PLAYER, EF_HOSTILE, EF_LEFT, EF_DYING = 1, 2, 4, 8, 16
HX = 9
HY = stand_y(1, 6)
NOWHERE = 7
FL, FLS = S["FLOOR_LIST"], S["FL_STRIDE"]
S1 = S["FL_S1"]
IROW = 9 + 7
BAG, WORN = S["BAG"], S["WORN"]
STRINGS = textpack.read_strings()
TXT = dict(STRINGS)
PICK = TXT["cmb_pick"]
IMG = textpack.parse_emitted(os.path.join(HERE.parent, "build", "text", "strings.asm"))
RES = S["WORKSTORE_TOP"] - 8
IT = {k[3:]: v for k, v in S.items() if k.startswith("IT_") and isinstance(v, int)}
NAME = {"F_CHEESE": "CHEESE", "P_MANA": "MANA POTION", "S_FEAR": "FEAR SCROLL", "BOOK": "WAR TOME",
        "W_LONG": "LONG SWORD", "A_CHAIN": "CHAIN MAIL", "C_MIGHT": "MIGHT RING", "BOW": "BOW",
        "P_HEAL": "HEAL POTION"}


def stream_text(raw):
    t0 = 2 * len(STRINGS)
    out = []
    for a in raw:
        if a == 0:
            break
        if a < 0x80:
            out.append(chr(a))
            continue
        q = int.from_bytes(IMG[t0 + 2 * (a - 0x80):t0 + 2 * (a - 0x80) + 2], "little")
        while True:
            c = IMG[q]
            q += 1
            out.append(chr(c & 0x7F))
            if c & 0x80:
                break
    return "".join(out)


def main():
    fails = []
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = T(h)

        def check(tag, cond, detail=""):
            if not h.expect(tag, bool(cond), True):
                fails.append(tag)
                if detail != "":
                    print(f"[detail] {tag}: {str(detail)[:700]}", flush=True)

        if KIT:
            print("[skip] pickup3e needs a DEBUG_KIT=0 build", flush=True)
        else:
            run(p, check)
        print(f"pickup3e: {len(fails)} failed"
              + (f": {fails[:8]}" if fails else ""), flush=True)
        return 1 if fails or h.failures else 0


def run(p, check):
    kt = {}

    def bag():
        b = p.z.read_memory(BAG, 60)
        return [tuple(b[i:i + 3]) for i in range(0, 60, 3) if b[i]]

    def place(slot, x, y, flags, hp):
        p.set_ent(slot, X=x, Y=y, PX=x * 8, PY=y * 8, MODE=0, ROOM=p.rb("CUR_ROOM"), FLAGS=flags, REACT=0,
                  FLT=0, HIT=0, HP=hp, MAXHP=hp)

    def scene(cls=K_KNIGHT, bagrecs=None):
        p.boot(cls)
        if not kt:
            kt.update(p.kinds())
        room = p.rb("CUR_ROOM")
        for sl in range(1, 16):
            e = p.ent(sl)
            if e["FLAGS"] & EF_ACTIVE and e["ROOM"] == room:
                p.set_ent(sl, ROOM=NOWHERE)
        place(0, HX, HY, EF_ACTIVE | EF_PLAYER, 200)
        p.wmem(S["ST_FLAGS"], [0] * 16)
        p.wmem(S["ST_T1"], [0] * 16)
        p.wmem(S["ST_T2"], [0] * 16)
        p.wmem(S["ST_X"], [0] * 16)
        if bagrecs is not None:
            flat = [v for r in bagrecs for v in r]
            p.wmem(BAG, flat + [0] * (60 - len(flat)))
            p.set_ent(0, POT=sum(q for t, q, _ in bagrecs if IT["POT_LO"] <= t <= IT["POT_HI"]))
        p.tick(3)

    def free_entries(n):
        out = [i for i in range(S["FLOOR_MAX"]) if p.rb(FL + i * FLS) == S["FL_EMPTY"]]
        assert len(out) >= n, "floor list full"
        return out[:n]

    def glyph(t):                                # FLOOR1: every type shows the marker (row 16)
        return S["T_ITEM0"] + 3

    def put(i, col, item, qty=1):
        p.wmem(FL + i * FLS, [p.rb("CUR_ROOM") | S1, col, item, qty])
        p.wmem(S["ROOM_MAP"] + (IROW - 1) * 32 + col, [S["T_ITEM0"] + 2] * 2)
        p.wmem(S["ROOM_MAP"] + IROW * 32 + col, [S["T_ITEM0"] + 3] * 2)
        # the marker cells' FI_CELL quarters as fi_put writes them (slot 0: UL 0,
        # UR 8 / LL 16, LR 24; storey 1's page): dp_pile reads the left-quarter
        # bit there (3F-T2: no longer relying on what the low RAM held before)
        pg = S["FI_CELL"] + 256
        p.wmem(pg + ((((IROW - 1) & 7) << 5) | col), [0, 8])
        p.wmem(pg + (((IROW & 7) << 5) | col), [16, 24])

    def entry(i):
        return list(p.z.read_memory(FL + i * FLS, 4))

    def cell(col, row=IROW):
        return p.rb(S["ROOM_MAP"] + row * 32 + col)

    def shadow_attr(row, c):
        return world.bank7(p, S["SHADOW_ATTR"] + row * 32 + c, 1)[0]

    def ring():
        return p.rb(S["LOG_Q"] + S["LQ_RD"]), p.rb("LOG_QN")

    def lines_since(w0):
        wr0 = (w0[0] + w0[1]) % S["LOG_SLOTS"]
        wr1 = (p.rb(S["LOG_Q"] + S["LQ_RD"]) + p.rb("LOG_QN")) % S["LOG_SLOTS"]
        n = (wr1 - wr0) % S["LOG_SLOTS"]
        out = []
        for k in range(n):
            sl = (wr0 + k) % S["LOG_SLOTS"]
            out.append(stream_text(p.z.read_memory(S["LOG_TXT"] + sl * S["LOG_SLOT_LEN"], S["LOG_SLOT_LEN"])))
        return out

    def step(keys=("L",)):
        r0 = ring()
        t0 = p.rw("TURN_COUNTER")
        p.turn(*keys)
        return p.rw("TURN_COUNTER") == t0 + 1, lines_since(r0)

    col = HX + 3                                    # one step right: the body covers HX+1..HX+3

    # ---- K1 start kit ------------------------------------------------------------------
    for cls, want_bag, want_worn, pot in (
            (K_KNIGHT, [(IT["P_HEAL"], 1, 0), (IT["F_APPLE"], 1, 0)], [IT["W_SHORT"], 1, 0, IT["A_LEATHER"], 1, 0], 1),
            (K_WIZARD, [(IT["P_HEAL"], 1, 0), (IT["P_MANA"], 1, 0), (IT["F_APPLE"], 1, 0)],
             [IT["W_OAK"], 1, 0, IT["A_ROBE"], 1, 0], 2)):
        p.boot(cls)
        got = dict(bag=bag(), worn=list(p.z.read_memory(WORN, 6)), pot=p.ent(0)["POT"])
        check(f"K1 start kit kind {cls}: bag, worn, E_POT", got == dict(bag=want_bag, worn=want_worn, pot=pot), got)

    # ---- P1 every class --------------------------------------------------------------
    for nm in ("F_CHEESE", "P_MANA", "S_FEAR", "BOOK", "W_LONG", "A_CHAIN", "C_MIGHT", "BOW"):
        scene(bagrecs=[])
        p.wb("HAS_BOW", 0)
        i, = free_entries(1)
        put(i, col, IT[nm])
        ok, lines = step()
        got = dict(ok=ok, bag=bag(), lines=lines, e=entry(i)[0], c=cell(col),
                   sh=shadow_attr(IROW, col) == p.rb(S["TILE_ATTRS"] + S["T_AIR"]), pot=p.ent(0)["POT"],
                   bow=p.rb("HAS_BOW"))
        want = dict(ok=True, bag=[(IT[nm], 1, 0)], lines=[PICK + NAME[nm]], e=S["FL_EMPTY"], c=S["T_AIR"], sh=True,
                    pot=1 if nm == "P_MANA" else 0, bow=1 if nm == "BOW" else 0)
        check(f"P1 pick up {nm}: bag record, line, entry gone, cell + attr T_AIR, E_POT, HAS_BOW", got == want,
              (got, want))

    # ---- P2 BAG FULL once per arrival ------------------------------------------------
    full = [(IT["W_LONG"], 1, 0)] * 20
    scene(bagrecs=full)
    i, = free_entries(1)
    put(i, col, IT["F_CHEESE"])
    g = glyph(IT["F_CHEESE"])
    ok1, l1 = step()
    ok2, l2 = step(("WAIT",))
    ok3, l3 = step(("H",))
    ok4, l4 = step()
    got = dict(ok=(ok1, ok2, ok3, ok4), lines=(l1, l2, l3, l4), e=entry(i), c=cell(col), bag=bag() == full)
    want = dict(ok=(True,) * 4, lines=(["BAG FULL"], [], [], ["BAG FULL"]),
                e=[p.rb("CUR_ROOM") | S1, col, IT["F_CHEESE"], 1], c=g, bag=True)
    check("P2 full bag: the item stays, BAG FULL on arrival only (not on a WAIT), again after off + on",
          got == want, (got, want))

    # P2w walk across one item with a full bag: 3 steps over it -> one BAG FULL; one
    # step off, back on -> exactly one more (review 2026-10-20: was 3 per crossing)
    scene(bagrecs=full)
    i, = free_entries(1)
    put(i, col, IT["F_CHEESE"])
    walk = []
    for _ in range(5):                              # x HX+1 .. +4 (all cover col..col+1: FLOOR1
        walk += step()[1]                           # 2-col footprint), HX+5 (off)
    back = []
    for _ in range(4):                              # back left until the body covers col + 1 again
        back += step(("H",))[1]
        if p.ent(0)["X"] + kt[K_KNIGHT]["bw"] - 1 >= col + 1:
            break
    got = dict(walk=walk, back=back, x=p.ent(0)["X"], e=entry(i)[0])
    check("P2w walk across: one BAG FULL for 4 steps over the item (2-col footprint), one more on the way back",
          got == dict(walk=["BAG FULL"], back=["BAG FULL"], x=HX + 4, e=p.rb("CUR_ROOM") | S1), got)

    # ---- P3 stacking -------------------------------------------------------------------
    scene(bagrecs=[(IT["P_HEAL"], 8, 0)])
    i, = free_entries(1)
    put(i, col, IT["P_HEAL"])
    ok, lines = step()
    b1, pot1 = bag(), p.ent(0)["POT"]
    i, = free_entries(1)
    put(i, col + 1, IT["P_HEAL"])
    ok2, _ = step()
    got = dict(ok=(ok, ok2), b1=b1, pot1=pot1, b2=bag(), pot2=p.ent(0)["POT"], lines=lines)
    want = dict(ok=(True, True), b1=[(IT["P_HEAL"], 9, 0)], pot1=9, b2=[(IT["P_HEAL"], 9, 0), (IT["P_HEAL"], 1, 0)],
                pot2=10, lines=[PICK + NAME["P_HEAL"]])
    check("P3 stacking: Heal 8 + 1 = 9, the next opens a slot; E_POT 9 -> 10", got == want, (got, want))

    # ---- Q1 / Q2 quaff ------------------------------------------------------------------
    scene(bagrecs=[(IT["P_CURE"], 1, 0), (IT["P_MANA"], 1, 0), (IT["P_HEAL"], 1, 0)])
    p.set_ent(0, HP=100, MAXHP=200)
    st = S["ST_FLAGS"]
    qh = S["QUAFF_HEAL"]

    def quaff():
        t0, hp0 = p.rw("TURN_COUNTER"), p.ent(0)["HP"]
        p.turn("G")
        p.until(lambda: p.idle(), 60)
        p.tick(4)
        return dict(t=p.rw("TURN_COUNTER") - t0, dhp=p.ent(0)["HP"] - hp0, pot=p.ent(0)["POT"],
                    sh=p.rb("PANEL_POT_SH"), bag=bag())
    g1 = quaff()
    p.wb("MP", 1)
    p.wb("MAXMP", 6)
    g2 = quaff()
    g2["mp"] = p.rb("MP")
    p.wb(st, S["STS_POISON"] | S["STS_WEAK"] | S["MIND_FEAR"])
    p.wb(S["ST_T1"], 0x05)                         # FEAR 5
    p.wb(S["ST_T2"], 0x05)                         # WEAK 5
    p.wb(S["ST_X"], 6)                             # POISON 6 (POIS1: a full byte; the step before the quaff makes it 5: no tick, a tick is at a multiple of 4)
    g3 = quaff()
    g3["st"] = (p.rb(st), p.rb(S["ST_T1"]), p.rb(S["ST_T2"]))
    got = [g1, g2, g3]
    for g, lo in zip(got, (qh, 0, 4)):
        g["dhp"] = g["dhp"] - lo in (0, 1)         # (+1: a regen tick may land in the turn)
    want = [dict(t=1, dhp=True, pot=2, sh=2, bag=[(IT["P_CURE"], 1, 0), (IT["P_MANA"], 1, 0)]),
            dict(t=1, dhp=True, pot=1, sh=1, bag=[(IT["P_CURE"], 1, 0)], mp=6),
            dict(t=1, dhp=True, pot=0, sh=0, bag=[], st=(0, 0, 0))]
    check("Q1 G x3: Heal (+QUAFF_HEAL), then Mana (+8 capped at 6), then Cure (POISON / WEAK / FEAR "
          "cleared, +4 HP); E_POT and the drawn count 2, 1, 0", got == want, (got, want))
    check("Q1 G with no potion: no turn", p.no_turn("G"), True)
    scene(bagrecs=[(IT["P_HEAL"], 2, 0)])
    r0 = ring()
    nt = p.no_turn("G")
    check("Q2 Heal at full HP (nothing else): NO NEED, no turn, bag kept",
          nt and bag() == [(IT["P_HEAL"], 2, 0)] and lines_since(r0) == ["NO NEED"], (nt, bag(), lines_since(r0)))
    # Q3 skip a refused type (review ruling (c)): full HP + Heal, Mana -> Mana drunk;
    # full MP too, a Cure but nothing to cure -> NO NEED
    scene(bagrecs=[(IT["P_HEAL"], 1, 0), (IT["P_MANA"], 1, 0), (IT["P_CURE"], 1, 0)])
    p.wb("MP", 1)
    p.wb("MAXMP", 6)
    t0 = p.rw("TURN_COUNTER")
    p.turn("G")
    p.until(lambda: p.idle(), 60)
    got1 = dict(t=p.rw("TURN_COUNTER") - t0, mp=p.rb("MP"), bag=bag())
    r0 = ring()
    nt = p.no_turn("G")
    got2 = dict(nt=nt, bag=bag(), lines=lines_since(r0))
    check("Q3 full HP: Heal skipped, Mana drunk; then full MP and nothing to cure: NO NEED, nothing used",
          (got1, got2) == (dict(t=1, mp=6, bag=[(IT["P_HEAL"], 1, 0), (IT["P_CURE"], 1, 0)]),
                           dict(nt=True, bag=[(IT["P_HEAL"], 1, 0), (IT["P_CURE"], 1, 0)], lines=["NO NEED"])),
          (got1, got2))

    # ---- D: drops --------------------------------------------------------------------
    def stub(body):
        assert p.code(p.bank3(body)), "stub did not return"

    def kill(slot):
        stub([0xDD, 0x21] + w16(S["P_ENTITIES"]) + [0x3E, slot, 0x06, 250, 0x0E, 0x08, 0x1E, 0, 0xCD]
             + w16(S["deal_hit"]))

    def seed_for(n, win):
        for sd in range(1, 4000):
            if (Rng(sd).mod(n) == 0) == win:
                return sd

    def monster(kind, x, cls=K_KNIGHT, hp=5):
        # the PROTO monster of that kind, else (3F-T3: K_ARCHER is no PROTO kind) a Skeleton's slot
        # re-kinded: the Archer row's stand-in body is the Skeleton's
        sl = next((s for s in range(1, 16) if p.ent(s)["KIND"] == kind), None)
        if sl is None:
            sl = next(s for s in range(1, 16) if p.ent(s)["KIND"] == K_SKELETON)
            p.set_ent(sl, KIND=kind)
        y = HY + kt[cls]["bh"] - kt[kind]["bh"]
        place(sl, x, y, EF_ACTIVE | EF_HOSTILE | EF_LEFT, hp)
        return sl

    def drop_case(tag, kind, cls, n, win, want_item, qty, x=18, pre=None):
        scene(cls)
        sl = monster(kind, x, cls)
        if pre:
            pre()
        before = [entry(k) for k in range(S["FLOOR_MAX"])]
        sd = seed_for(n, win) if n else 0x1234
        p.wmem(S["RNG_STATE"], w16(sd))
        r = Rng(sd)
        if n:
            r.mod(n)
        r0 = ring()
        kill(sl)
        new = [(k, entry(k)) for k in range(S["FLOOR_MAX"]) if entry(k) != before[k]]
        cx = x + kt[kind]["bw"] // 2
        got = dict(rng=p.rw("RNG_STATE"), new=new, lines=lines_since(r0))
        return got, r.st, cx

    for cls, kind, n, item, qty, nm in ((K_KNIGHT, K_RAT, 4, IT["F_CHEESE"], 1, "Rat cheese"),
                                       (K_KNIGHT, K_GOBLIN, 4, IT["F_APPLE"], 1, "Goblin apple"),
                                       (K_KNIGHT, K_ARCHER, 2, IT["ARROW"], 3, "Skeleton Archer arrows")):
        got, st, cx = drop_case("D1", kind, cls, n, True, item, qty)
        room = p.rb("CUR_ROOM") | S1
        k = got["new"][0][0] if got["new"] else None
        want = dict(rng=st, new=[(k, [room, cx, item, qty])], lines=[])
        check(f"D1 {nm}: the winning seed drops at the centre col, no line, RNG == model", got == want, (got, want))
        if k is not None:
            check(f"D1 {nm}: the cell shows the glyph", cell(cx) == glyph(item), cell(cx))
        got, st, cx = drop_case("D2", kind, cls, n, False, item, qty)
        check(f"D2 {nm}: the losing seed drops nothing, one roll", got == dict(rng=st, new=[], lines=[]), (got, st))
    got, st, _ = drop_case("D3", K_ARCHER, K_WIZARD, 0, True, None, 0)
    check("D3 Mage run: a Skeleton Archer rolls nothing, drops nothing", got == dict(rng=st, new=[], lines=[]),
          (got, st))

    def block_centre():
        i, = free_entries(1)
        cx = 18 + kt[K_RAT]["bw"] // 2
        put(i, cx, IT["F_PEAR"])
    got, st, cx = drop_case("D4", K_RAT, K_KNIGHT, 4, True, IT["F_CHEESE"], 1, pre=block_centre)
    news = [e for _, e in got["new"] if e[2] == IT["F_CHEESE"]]
    check("D4 FLOOR1: an item at the centre col -> the cheese stacks on it (an item within +-1 snaps)",
          news == [[p.rb("CUR_ROOM") | S1, cx, IT["F_CHEESE"], 1]], got)

    def fill31():
        fr = [k for k in range(S["FLOOR_MAX"]) if p.rb(FL + k * FLS) == S["FL_EMPTY"]]
        for k in fr[:-1]:
            p.wmem(FL + k * FLS, [NOWHERE, 1, IT["F_PEAR"], 1])
    got, st, cx = drop_case("D5", K_RAT, K_KNIGHT, 4, True, IT["F_CHEESE"], 1, pre=fill31)
    check("D5 31 entries used: an ordinary drop is lost (the roll still made)",
          dict(rng=got["rng"], new=[e for _, e in got["new"] if e[0] != NOWHERE]) == dict(rng=st, new=[]), got)

    # ---- U: the boss unique --------------------------------------------------------------
    def lair():
        p.wb("LVL_LAIR", p.rb("CUR_ROOM"))
        p.wb("LP_BOSS", K_GOBLIN)
        p.wb("LVL_DEPTH", 1)
        p.wb("LVL_FLAGS", p.rb("LVL_FLAGS") & ~S["LF_UNIQUE"] & 0xFF)
    got, st, cx = drop_case("U1", K_GOBLIN, K_KNIGHT, 0, True, None, 0, pre=lair)
    room = p.rb("CUR_ROOM") | S1
    want = dict(rng=st, new=[(got["new"][0][0] if got["new"] else None, [room, cx, IT["H_KING"], 1])],
                lines=["BOSS DROPS KING HELM"])
    check("U1 D1 boss: KING HELM at the centre, BOSS DROPS line, no RNG", got == want, (got, want))
    check("U1 LF_UNIQUE set", p.rb("LVL_FLAGS") & S["LF_UNIQUE"], p.rb("LVL_FLAGS"))
    sl = monster(K_GOBLIN, 24)
    sd = seed_for(4, True)
    p.wmem(S["RNG_STATE"], w16(sd))
    r = Rng(sd)
    r.mod(4)
    before = [entry(k) for k in range(S["FLOOR_MAX"])]
    kill(sl)
    new = [entry(k) for k in range(S["FLOOR_MAX"]) if entry(k) != before[k]]
    check("U1 the next Goblin in the lair: the ordinary row (apple, one roll)",
          p.rw("RNG_STATE") == r.st and [e[2] for e in new] == [IT["F_APPLE"]], (new, p.rw("RNG_STATE"), r.st))

    # ---- T: cost (info + loose caps) ------------------------------------------------
    tm = {}
    for tag, win in (("kill + drop", True), ("kill, no drop", False)):
        scene()
        sl = monster(K_RAT, 18)
        p.wmem(S["RNG_STATE"], w16(seed_for(4, win)))
        kill(sl)
        tm[tag] = p.tstates
    scene()
    lair()
    sl = monster(K_GOBLIN, 18)
    kill(sl)
    tm["boss kill + unique"] = p.tstates
    scene(bagrecs=[])
    i, = free_entries(1)
    put(i, HX + 1, IT["W_LONG"])
    p.wb("PU_POS", 0xFF)
    assert p.code([0x21] + w16(S["floor_pickup"]) + [0xCD] + w16(S["far7"])), "floor_pickup stub"
    tm["pickup (floor_pickup, 1 bag item)"] = p.tstates
    picked = bag() == [(IT["W_LONG"], 1, 0)]
    scene(bagrecs=[])
    assert p.code([0x3E, IT["W_LONG"], 0x21] + w16(S["pu_add"]) + [0xCD] + w16(S["far6"])), "pu_add stub"
    tm["pu_add alone"] = p.tstates
    i, = free_entries(1)
    put(i, HX + 1, IT["W_LONG"])
    assert p.code([0x0E, HX + 1, 0x1E, p.rb("CUR_ROOM") | S1, 0x3E, HX + 1, 0x21] + w16(S["ap_stamp_a"])
                  + [0xCD] + w16(S["far7"])), "ap_stamp stub"
    tm["ap_stamp alone"] = p.tstates
    scene(bagrecs=[])
    assert p.code([0x21] + w16(S["floor_pickup"]) + [0xCD] + w16(S["far7"])), "floor_pickup stub"
    tm["floor_pickup, nothing"] = p.tstates
    print("[info] T incl. stub: " + ", ".join(f"{k} {v}" for k, v in tm.items()), flush=True)
    check("T costs: pickup <= 26k T, kill + drop <= 30k T, boss kill <= 40k T",
          tm["pickup (floor_pickup, 1 bag item)"] <= 26000 and tm["kill + drop"] <= 30000
          and tm["boss kill + unique"] <= 40000 and picked, tm)

    def lair31():
        lair()
        fill31()
    got, st, cx = drop_case("U2", K_GOBLIN, K_KNIGHT, 0, True, None, 0, pre=lair31)
    news = [(k, e) for k, e in got["new"] if e[0] != NOWHERE]
    check("U2 31 entries used: the unique takes the last free entry",
          len(news) == 1 and news[0][1][2] == IT["H_KING"], got)


if __name__ == "__main__":
    sys.exit(main())
