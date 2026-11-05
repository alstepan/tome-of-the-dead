#!/usr/bin/env python3
"""itch.io page media for Tome of the Dead (FINAL-3a).  Nearest-neighbour integer scaling only,
the real Spectrum palette (FLASH shown non-inverted).  Output: docs/release/itch/{img,video}/.

  python3 tools/itch_media.py cover                  # img/cover_a.png, cover_b.png (630x500)
  python3 tools/itch_media.py record W|M [--ticks N] # scripted run -> build/itch/rec_<W|M>.pkl (frames)
  python3 tools/itch_media.py shots                  # img/shot*.png (x3)  [needs recordings + extras]
  python3 tools/itch_media.py gif                    # img/walk_fight.gif
  python3 tools/itch_media.py video W|M              # video/warrior.mp4 | mage.mp4 (silent)

Recording needs the release build (tools/build.sh -DDEBUG_KIT=0), ZEsarUX and a free ZRCP port
(ZRCP_PORT, never 10000).  The run is tick-exact (the playthrough bot of tests/pt_bot.py drives the
real controls, SEED_FIXED), so the same seed gives the same frames.  Timing: a 25 Hz game tick = 2
display frames (40 ms), a menu/transition frame = 1 (20 ms): the video is constant 50 fps and never
sped up.  No audio: this ZEsarUX has no audio-to-file option, and the game's AY is not faked.
"""
import os
import pickle
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
OUT = ROOT / "docs/release/itch"
TMP = ROOT / "build/itch"
FFMPEG = "/opt/homebrew/bin/ffmpeg"


# ------------------------------------------------------------------ screen rendering
def scr_to_rgb(data: bytes) -> np.ndarray:
    """6912-B SCREEN$ (bitmap + attrs) -> 192x256x3 uint8 (bright respected, flash = non-inverted)."""
    d = np.frombuffer(bytes(data[:6912]), np.uint8)
    y = np.arange(192)
    base = ((y & 0xC0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2)
    rows = d[base[:, None] + np.arange(32)[None, :]]                      # 192x32 bytes
    bits = np.unpackbits(rows, axis=1).astype(bool)                       # 192x256
    attr = d[6144:6912].reshape(24, 32)
    attr = np.repeat(np.repeat(attr, 8, 0), 8, 1)                         # 192x256
    lv = np.where(attr & 0x40, 0xFF, 0xD7).astype(np.uint8)

    def col(idx):
        return np.stack([(idx >> 1 & 1), (idx >> 2 & 1), (idx & 1)], -1) * lv[..., None]
    return np.where(bits[..., None], col(attr & 7), col(attr >> 3 & 7)).astype(np.uint8)


def scaled(rgb, k):
    return Image.fromarray(rgb).resize((rgb.shape[1] * k, rgb.shape[0] * k), Image.NEAREST)


# ------------------------------------------------------------------ cover
def cmd_cover():
    OUT.joinpath("img").mkdir(parents=True, exist_ok=True)
    rgb = scr_to_rgb((ROOT / "assets/gfx/loading/loading_l3d.scr").read_bytes())
    # a: whole screen x2 (rows 22-23 are blank black paper, so they read as a black margin)
    for name, crop in (("cover_a", 192), ("cover_b", 176)):
        im = scaled(rgb[:crop], 2)
        cv = Image.new("RGB", (630, 500), (0, 0, 0))
        cv.paste(im, ((630 - im.width) // 2, (500 - im.height) // 2))
        cv.save(OUT / "img" / f"{name}.png")


# ------------------------------------------------------------------ recording
def record(hero_name, ticks, seed=0x1234, start_depth=1, out=None):
    """Bot-driven run from the menu; every probe (tick) is captured: [(frame6912, display_frames)]."""
    if os.environ.get("ZRCP_PORT", "10000") == "10000":
        sys.exit("never port 10000: set ZRCP_PORT")
    import playthrough as pt
    from pt_plan import Player, RunEnd, S, K_KNIGHT, K_WIZARD, PT, Harness, EMU_ARGS, Mon
    hero = K_KNIGHT if hero_name == "W" else K_WIZARD
    frames, total = [], [0]
    with Harness() as h:
        h.launch(EMU_ARGS)
        p = PT(h)
        p.mon = Mon(p)
        orig = p.tick

        def tick(n=1):
            for _ in range(n):
                orig(1)
                d = 1 if p.pc() == S["select_tick"] else 2
                frames.append((bytes(p.frame()), d))
                total[0] += d
                if total[0] >= ticks * 2:
                    raise RunEnd("recorded")
        # = playthrough.new_game, but the hook is on from the menu: ~2 s of main menu, then START
        p.proto_start = 0
        p.snd_mode = None
        p.load()
        p.wait_state(pt.GS_SELECT)
        p.wb("seed_fixed", 1)
        p.z.cmd("write-memory %d %d %d" % (S["seed_value"], seed & 255, seed >> 8))
        p.wb("INPUT_REPEAT", 0)
        p.wb("ANIM_FREEZE", 0)
        p.wb("INPUT_SRC", 1)
        p.release()
        p.tick = tick
        p.tick(2)
        for _ in range(2):
            if p.rb("menu_hero") == hero:
                break
            p.tap("2")
            p.tick(40)                          # the toggled hero shown on the menu
        p.tick(40)
        p.hold("1")
        p.wait_state(pt.GS_PLAYING)
        p.release()
        p.settle(3)
        if start_depth > 1:                     # same poke as playthrough.py --start-depth: the real level_descend
            from lp import w16
            pc0 = p.pc()
            p.code([0x3E, start_depth - 1, 0x32] + w16(S["LVL_DEPTH"]) + [0xCD] + w16(S["level_descend"]), game=True)
            p.z.cmd("set-register PC=%d" % pc0)
            p.release()
            p.settle(4)
        bot = Player(p, hero, mode="win", god=True, max_ticks=10 ** 6, level_cap=60000)
        bot.boss_poke = 60
        bot.play()
    out = out or TMP / f"rec_{hero_name}{'_d%d' % start_depth if start_depth > 1 else ''}.pkl"
    TMP.mkdir(parents=True, exist_ok=True)
    pickle.dump(frames, open(out, "wb"))
    print(f"recorded {len(frames)} probes, {total[0] / 50:.1f} s -> {out}")


def load_rec(hero_name, tag=""):
    return pickle.load(open(TMP / f"rec_{hero_name}{tag}.pkl", "rb"))


# ------------------------------------------------------------------ video / gif
def cmd_video(hero_name, scale=6, start=0, end=None, name=None):
    frames = load_rec(hero_name)[start:end]
    name = name or {"W": "warrior", "M": "mage"}[hero_name]
    d = TMP / f"png_{hero_name}"
    d.mkdir(parents=True, exist_ok=True)
    lst = []
    for i, (f, dur) in enumerate(frames):
        pth = d / f"{i:05d}.png"
        Image.fromarray(scr_to_rgb(f)).save(pth)
        lst.append(f"file '{pth}'\nduration {dur * 0.02:.2f}")
    lst.append(f"file '{pth}'")
    (TMP / f"{name}.txt").write_text("\n".join(lst) + "\n")
    (OUT / "video").mkdir(parents=True, exist_ok=True)
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(TMP / f"{name}.txt"),
                    "-vf", f"scale={256 * scale}:{192 * scale}:flags=neighbor,fps=50,format=yuv420p",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-r", "50", "-movflags", "+faststart",
                    str(OUT / "video" / f"{name}.mp4")], check=True)


def cmd_gif(hero_name, start, end, name="walk_fight.gif"):
    frames = load_rec(hero_name)[start:end]
    ims, dur = [], []
    for f, d in frames:
        ims.append(scaled(scr_to_rgb(f), 2))
        dur.append(d * 20)
    # one shared palette from the real Spectrum colours, no dithering
    pal = []
    for br in (0xD7, 0xFF):
        for c in range(8):
            pal += [(c >> 1 & 1) * br, (c >> 2 & 1) * br, (c & 1) * br]
    pal += [0] * (768 - len(pal))
    ref = Image.new("P", (1, 1))
    ref.putpalette(pal)
    q = [i.quantize(palette=ref, dither=Image.Dither.NONE) for i in ims]
    # merge equal consecutive frames (shorter file, same timing)
    mi, md = [q[0]], [dur[0]]
    for a, b, dd in zip(q, q[1:], dur[1:]):
        if a.tobytes() == b.tobytes():
            md[-1] += dd
        else:
            mi.append(b)
            md.append(dd)
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    mi[0].save(OUT / "img" / name, save_all=True, append_images=mi[1:], duration=md, loop=0,
               optimize=True, disposal=1)


# probe indices into the (deterministic) recordings picked by eye from contact sheets
SHOTS = [("shot1_menu", "W", "", 30), ("shot2_warrior_fight", "W", "", 492), ("shot3_mage_bolt", "M", "", 501),
         ("shot4_bag", "W", "", 532), ("shot5_deeper_d5", "W", "_d5", 279)]
GIF = ("W", 440, 560)


def cmd_shots():
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    for name, h, tag, i in SHOTS:
        scaled(scr_to_rgb(load_rec(h, tag)[i][0]), 3).save(OUT / "img" / f"{name}.png")


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "cover":
        cmd_cover()
    elif a[0] == "record":
        n = int(a[a.index("--ticks") + 1]) if "--ticks" in a else 1500
        d = int(a[a.index("--depth") + 1]) if "--depth" in a else 1
        record(a[1], n, start_depth=d)
    elif a[0] == "shots":
        cmd_shots()
    elif a[0] == "gif":
        cmd_gif(*GIF)
    elif a[0] == "video":
        cmd_video(a[1])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
