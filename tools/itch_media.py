#!/usr/bin/env python3
"""itch.io page media for Tome of the Dead (FINAL-3a).  Nearest-neighbour integer scaling only,
the real Spectrum palette (FLASH shown non-inverted).  Output: docs/release/itch/{img,video}/.

  python3 tools/itch_media.py cover                  # img/cover_a.png, cover_b.png (630x500)
  python3 tools/itch_media.py record W|M [--ticks N] # scripted run -> build/itch/rec_<W|M>.pkl (frames)
  python3 tools/itch_media.py shots                  # img/shot*.png (x3)  [needs recordings + extras]
  python3 tools/itch_media.py clips                  # img/warrior.gif, mage.gif from the video recordings
  python3 tools/itch_media.py gif                    # img/walk_fight.gif
  python3 tools/itch_media.py script W|M [part..]    # dev: run the hand-written input script (fast, no sound)
  python3 tools/itch_media.py video W|M [--reuse]    # script at emulator speed 100 + --aofile -> video/warrior.mp4 | mage.mp4 (with sound)
  python3 tools/itch_media.py trailer rec music|W|M  # trailer captures (music once from the menu; hero SFX-only runs), speed 100
  python3 tools/itch_media.py trailer                # assemble video/trailer.mp4 from those captures (real time, trim only)

Recording needs the release build (tools/build.sh -DDEBUG_KIT=0), ZEsarUX and a free ZRCP port
(ZRCP_PORT, never 10000).  The run is tick-exact (the playthrough bot of tests/pt_bot.py drives the
real controls, SEED_FIXED), so the same seed gives the same frames.  Timing: a 25 Hz game tick = 2
display frames (40 ms), a menu/transition frame = 1 (20 ms): the video is constant 50 fps and never
sped up.  Sound: ZEsarUX --aofile = raw mono unsigned 8 bit 15600 Hz, 312 B per 50 Hz frame, written only while the
emulated machine runs; anchored at the end of the file (verified to ~2 frames on a pickup jingle).
"""
import contextlib
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
def require_no_zesarux():
    """A second ZEsarUX steals CPU, the speed-100 emulator falls behind real time and --aofile is stretched/garbled.
    Fuse may run (never touched)."""
    r = subprocess.run(["pgrep", "-il", "zesarux"], capture_output=True, text=True)
    if r.stdout.strip():
        sys.exit("ERROR: another ZEsarUX process is running (would corrupt the sound recording); refusing:\n" + r.stdout)


def record(hero_name, ticks, seed=0x1234, start_depth=1, out=None):
    """Bot-driven run from the menu; every probe (tick) is captured: [(frame6912, display_frames)]."""
    if os.environ.get("ZRCP_PORT", "10000") == "10000":
        sys.exit("never port 10000: set ZRCP_PORT")
    require_no_zesarux()
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
    if tag == "scr":                                   # the `video` script recording (bag, deeper depths)
        return pickle.load(open(TMP / f"scr_{hero_name}.pkl", "rb"))
    return pickle.load(open(TMP / f"rec_{hero_name}{tag}.pkl", "rb"))


# ------------------------------------------------------------------ video / gif
AUDIO_HZ = 15600                      # ZEsarUX --aofile: mono, unsigned 8 bit, 312 bytes per 50 Hz frame
BPF = AUDIO_HZ // 50
BLACK_KEEP = 0.35                     # s of black kept at each end of a cut (the rest is trimmed, picture AND sound)


def check_audio(frames, audio_path, span):
    """Fail loudly on stretched/garbled/silent sound.  span = (bytes at recording start, bytes at end) of the
    --aofile while the recording ran: must equal emulated frames x 312 within 2 %."""
    raw = np.fromfile(audio_path, np.uint8)
    need = sum(d for _, d in frames) * BPF
    (b0, f0), (b1, f1), rec_total = span
    emu = (f1 - f0) & 0xFFFFFF                          # emulated 50 Hz frames (SYS_FRAMES) over the same span
    got = b1 - b0
    print(f"emulated frames {emu}, recorded frames {rec_total}")
    need = rec_total * BPF                              # SYS_FRAMES undercounts DI stretches: Rec re-clocked on the sound
    print(f"hidden (DI) frames {rec_total - emu} ({(rec_total - emu) / 50:.1f} s) assigned from the sound file clock")
    ratio = got / need
    tail = raw[-need:].astype(np.float32)
    sd = float(tail.std())
    print(f"audio check: {got} B vs {need} B expected, ratio {ratio:.4f}, file {len(raw)} B, std {sd:.2f}")
    if abs(ratio - 1) > 0.02:
        sys.exit(f"AUDIO CHECK FAILED: ratio {ratio:.4f} (emulator not real time?)")
    if sd < 1.0 or len(np.unique(tail[::97])) < 4:
        sys.exit("AUDIO CHECK FAILED: audio is silent/constant")


def assemble(frames, audio_path, out, scale=6):
    """frames [(6912 B, display frames)] + the raw sound file -> constant-50 fps H.264 + AAC MP4.
    The sound file covers the whole emulator run, the recording its last sum(d) frames: it is anchored at the END
    (the file is complete when the emulator exits).  Black runs longer than 2*BLACK_KEEP are trimmed in picture
    and sound alike (10 ms crossfade) so a cut costs ~0.7 s, never a de-sync."""
    imgs = [scr_to_rgb(f) for f, _ in frames]
    tl = [i for i, (_, d) in enumerate(frames) for _ in range(d)]            # image per 50 Hz display frame
    n = len(tl)
    black = [not any(f) for f, _ in frames]
    keep = np.ones(n, bool)
    i = 0
    while i < n:
        if black[tl[i]]:
            j = i
            while j < n and black[tl[j]]:
                j += 1
            k = int(BLACK_KEEP * 50)
            if j - i > 2 * k + 5:
                keep[i + k:j - k] = False
            i = j
        else:
            i += 1
    audio = None
    if audio_path and Path(audio_path).exists():
        raw = np.fromfile(audio_path, np.uint8)
        need = n * BPF
        if len(raw) < need:
            sys.exit(f"audio file shorter than the video ({len(raw)} < {need})")
        a = raw[len(raw) - need:].astype(np.float32)
        a -= np.convolve(a, np.ones(2000) / 2000, mode="same")                # drop the DC offset / slow drift
        a *= 0.89 / max(1.0, float(np.abs(a).max()))                          # level: peak at -1 dBFS, no clipping
        a = np.clip(a, -1, 1)
        seg = a.reshape(n, BPF)
        out_a, prev = [], None
        for run_start, run_end in _runs(keep):
            chunk = seg[run_start:run_end].reshape(-1).copy()
            if prev is not None:                                              # crossfade the join
                m = 156
                fade = np.linspace(0, 1, m, dtype=np.float32)
                chunk[:m] *= fade
                out_a[-1][-m:] *= fade[::-1]
            out_a.append(chunk)
            prev = chunk
        audio = np.concatenate(out_a)
    TMP.mkdir(parents=True, exist_ok=True)
    (OUT / "video").mkdir(parents=True, exist_ok=True)
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "256x192", "-r", "50",
           "-i", "-"]
    if audio is not None:
        wav = TMP / "audio.s16"
        (audio * 32000).astype("<i2").tofile(wav)
        cmd += ["-f", "s16le", "-ar", str(AUDIO_HZ), "-ac", "1", "-i", str(wav)]
    cmd += ["-vf", f"scale={256 * scale}:{192 * scale}:flags=neighbor,format=yuv420p", "-c:v", "libx264", "-preset", "slow",
            "-crf", "16", "-r", "50"]
    if audio is not None:
        cmd += ["-af", "aresample=44100", "-c:a", "aac", "-b:a", "128k", "-shortest"]
    cmd += ["-movflags", "+faststart", str(out)]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for t in np.nonzero(keep)[0]:
        pr.stdin.write(imgs[tl[t]].tobytes())
    pr.stdin.close()
    if pr.wait():
        sys.exit("ffmpeg failed")
    try:
        dur = float(subprocess.run([FFMPEG.replace("ffmpeg", "ffprobe"), "-v", "error", "-show_entries", "format=duration",
                                    "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout)
    except ValueError:
        dur = -1
    print(f"ffprobe duration {dur:.1f} s vs expected {int(keep.sum()) / 50:.1f} s")
    print(f"{out}: {int(keep.sum()) / 50:.1f} s, {Path(out).stat().st_size / 1e6:.1f} MB, audio {'yes' if audio is not None else 'NO'}")


def _runs(keep):
    out, i, n = [], 0, len(keep)
    while i < n:
        if keep[i]:
            j = i
            while j < n and keep[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def cmd_video(hero_name, reuse=False):
    """record (emulator speed 100 + --aofile, ~2.5 min) and assemble; reuse: re-assemble the last recording."""
    name = {"W": "warrior", "M": "mage"}[hero_name]
    audio = TMP / f"audio_{hero_name}.raw"
    if not reuse:
        if audio.exists():
            audio.unlink()
        cmd_script(hero_name, fast=False, audio=audio)
    frames = pickle.load(open(TMP / f"scr_{hero_name}.pkl", "rb"))
    check_audio(frames, audio, pickle.load(open(TMP / f"span_{hero_name}.pkl", "rb")))
    assemble(frames, audio, OUT / "video" / f"{name}.mp4")


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


def cmd_clip(hero_name, start, end, name, fps=25):
    """GIF at 2x cut from the `video` recording (build/itch/scr_<W|M>.pkl, probes start..end), fps 25: the 50 Hz
    display-frame timeline is sampled every 50/fps frames; equal consecutive frames are merged."""
    frames = pickle.load(open(TMP / f"scr_{hero_name}.pkl", "rb"))[start:end]
    tl = [f for f, d in frames for _ in range(d)][::50 // fps]
    pal = []
    for br in (0xD7, 0xFF):
        for c in range(8):
            pal += [(c >> 1 & 1) * br, (c >> 2 & 1) * br, (c & 1) * br]
    pal += [0] * (768 - len(pal))
    ref = Image.new("P", (1, 1))
    ref.putpalette(pal)
    q = [scaled(scr_to_rgb(f), 2).quantize(palette=ref, dither=Image.Dither.NONE) for f in tl]
    mi, md = [q[0]], [1000 // fps]
    for b in q[1:]:
        if b.tobytes() == mi[-1].tobytes():
            md[-1] += 1000 // fps
        else:
            mi.append(b)
            md.append(1000 // fps)
    md[-1] += 600                                  # hold the last frame before the loop restarts
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    out = OUT / "img" / name
    mi[0].save(out, save_all=True, append_images=mi[1:], duration=md, loop=0, optimize=True, disposal=1)
    print(f"{out}: {sum(md) / 1000:.1f} s, {out.stat().st_size / 1e6:.2f} MB, {len(mi)} frames")


# ------------------------------------------------------------------ scripted stages (hand-written input scripts)
def _imports():
    global pt, Bot, Harness, PT, Mon, S, K_KNIGHT, K_WIZARD, EMU_ARGS, RunEnd, room_model, HERO_W, IT_NAME
    import playthrough as pt                      # noqa: F811
    from pt_plan import Harness, PT, Mon, S, K_KNIGHT, K_WIZARD, EMU_ARGS, RunEnd   # noqa: F811
    from pt_bot import Bot, HERO_W, IT_NAME       # noqa: F811
    import room_model                             # noqa: F811


class Rec:
    """Frame recorder on the p.tick hook.  Every captured frame carries the number of 50 Hz display
    frames (SYS_FRAMES delta) it stayed on screen, so video length == emulated time == audio length,
    whatever the probe spacing (game tick 2, menu frame 1, a code stub / transition more)."""

    def __init__(self, p):
        self.p, self.frames, self.black, self.last = p, [], False, None
        self.audio, self.a0, self.tot = None, 0, 0
        self.marks = []                                   # (name, display-frame index) set by the scripts (trailer)
        self.orig = p.tick
        p.tick = self.tick

    def sys(self):
        b = self.p.z.read_memory(S["SYS_FRAMES"], 3)
        return b[0] | b[1] << 8 | b[2] << 16

    def start(self):
        self.last = self.sys()
        if self.audio:
            self.a0 = Path(self.audio).stat().st_size

    def tick(self, n=1):
        for _ in range(n):
            self.orig(1)
            if self.last is None:
                continue
            c = self.sys()
            d = max(1, (c - self.last) & 0xFFFFFF)
            self.last = c
            if self.audio:
                # SYS_FRAMES stands still while the game runs DI (level generation, ~1-2 s) but --aofile keeps
                # being written: take the sound file (4096 B chunks = 13 frames of lag) as the clock there,
                # else the picture would run short and the sound drift earlier by seconds.
                a = (Path(self.audio).stat().st_size - self.a0) / BPF
                extra = a - (self.tot + d) - 6.5
                if extra > 20:
                    d += int(extra)
            self.tot += d
            self.frames.append((bytes(6912) if self.black else bytes(self.p.frame()), d))

    def total(self):
        return sum(d for _, d in self.frames)


XP_AT = {1: 0, 2: 40, 3: 100, 4: 200, 5: 340, 6: 500, 7: 700, 8: 920, 9: 1150}


def make_stage(p, hero):
    """Bot used only as a LIBRARY (room geometry, pathing, exits, hostile scan, fight helper): every
    decision is made by the hand-written scripts, never by Bot.play()."""
    _imports()

    class Stage(Bot):
        allow_jump = False
        force_spell = None
        god = False

        def jump_ok(self, x, dx):                 # no jumping unless a pit forces it (see walk_to)
            return self.allow_jump and super().jump_ok(x, dx)

        def pick_spell(self, h, gap, mp, rk):
            f = self.force_spell
            if f is not None and rk[f] and f not in self.banned(h["kind"]) and mp >= self.SPELL_MP[f] \
                    and 0 <= gap <= self.SPELL_RANGE[f] - 1 and not (f == 1 and gap <= 2):
                return f
            return super().pick_spell(h, gap, mp, rk)

        # ---- time (display frames, from the game's own frame counter) ----
        def sysf(self):
            b = self.p.z.read_memory(S["SYS_FRAMES"], 3)
            return b[0] | b[1] << 8 | b[2] << 16

        def wait_s(self, sec):
            t0 = self.sysf()
            while ((self.sysf() - t0) & 0xFFFFFF) < sec * 50:
                self.p.tick(1)

        # ---- movement ----
        def room(self):
            return self.rb("CUR_ROOM")

        def walk_to(self, s, x, tries=90):
            bad = 0
            for _ in range(tries):
                self.refresh_room()
                e, s0, x0, standing = self.hero_pos()
                if not standing:
                    self.continue_climb()
                    continue
                if (s0, x0) == (s, x):
                    return True
                path = self.path_to([(s, x)])
                if path is None and not self.allow_jump:
                    self.allow_jump = True        # a pit in the way: a jump is the only crossing
                    path = self.path_to([(s, x)])
                self.allow_jump = False
                if path is None or len(path) < 2:
                    bad += 1
                    if bad > 4:
                        return False
                    self.act("WAIT")
                    continue
                self.follow(path)
            return False

        def leave(self, kind, tries=120):
            r0 = self.room()
            for _ in range(tries):
                self.refresh_room()
                e, s0, x0, standing = self.hero_pos()
                if not standing:
                    self.continue_climb()
                elif self.room() != r0:
                    break
                else:
                    self.do_exit(kind)
            self.p.tick(2)
            self.refresh_room()
            return self.room() != r0

        def fight_room(self, max_steps=150, until=None, max_s=None):
            t0 = self.sysf()
            for _ in range(max_steps):
                if max_s and ((self.sysf() - t0) & 0xFFFFFF) > max_s * 50:
                    return
                self.refresh_room()
                if self.rb("GAME_STATE") != S["GS_PLAYING"]:
                    return
                if self.god:
                    e = self.heroe()
                    if e["HP"] * 3 < e["MAXHP"]:
                        self.p.set_ent(0, HP=e["MAXHP"])
                if until and until():
                    return
                e, s, x, standing = self.hero_pos()
                if not standing:
                    self.continue_climb()
                    continue
                if not [h for h in self.hostiles() if not h["pend"]]:
                    return
                if not self.fight():
                    self.act("WAIT")

        # ---- the bag page: open, dwell, move the cursor slowly, close ----
        def bag_show(self, goto=None, use=False, dwell=2.0, step_s=0.7, close_dwell=0.8):
            p = self.p
            p.tap("I")
            p.until(lambda: p.rb("PAGE_OPEN") == 1 and p.pc() == S["select_tick"], 20)
            self.wait_s(dwell)
            rc = lambda: (p.rb("pg_rc"), p.rb(S["pg_rc"] + 1))      # noqa: E731
            if goto is not None:
                row, col = 1 + goto // 5, goto % 5
                for _ in range(8):
                    if rc()[0] == row:
                        break
                    p.tap("A")
                    self.wait_s(step_s)
                for _ in range(6):
                    if rc()[1] == col:
                        break
                    p.tap("P")
                    self.wait_s(step_s)
                self.wait_s(step_s)
                if use:
                    p.tap("FIRE")
                    self.wait_s(step_s)
                    p.tap("FIRE")
                    self.wait_s(close_dwell)
            if p.rb("PAGE_OPEN"):
                p.tap("CAPS", "SPACE")
                p.until(lambda: p.rb("PAGE_OPEN") == 0, 20)
            p.tick(3)
            p.until(lambda: p.idle() and self.rb("LOG_QN") == 0, 80)

        def bag_find(self, name):
            for i, (t, q) in enumerate(self.bag()):
                if IT_NAME.get(t) == name:
                    return i
            return None

        # ---- level control ----
        def go_depth(self, n, black=None):
            """the real level_descend from depth n-1 (a poke, as playthrough.py --start-depth), then re-read the level."""
            p = self.p
            from lp import w16
            p.until(lambda: p.rb("GAME_STATE") == S["GS_PLAYING"] and p.pc() == S["wait_tick"], 1200)
            pc0 = p.pc()
            snd = p.rb("SND_MODE")
            p.wb("SND_MODE", 2)                   # SFX only while the poke runs: with music on, level_descend holds the
            #                                       Level Complete stinger (361 frames) and the next poke derails
            p.code([0x3E, n - 1, 0x32] + w16(S["LVL_DEPTH"]) + [0xCD] + w16(S["level_descend"]), game=True)
            p.z.cmd("set-register PC=%d" % pc0)
            p.release()
            p.tick(2)
            p.until(lambda: p.rb("GAME_STATE") == S["GS_PLAYING"] and p.pc() == S["wait_tick"], 1200)
            p.settle(3)
            p.wb("SND_MODE", snd)
            self.load_level()

        def buff(self, hp=None, mp=None, ranks=None, lvl=None):
            """poke the hero's kit for the deeper segments (a promo video of D4-D8 for a hero who played D1 only)."""
            p = self.p
            if hp:
                p.set_ent(0, HP=hp, MAXHP=hp)
            if mp:
                p.wb("MP", mp)
                p.wb("MAXMP", mp)
            if ranks is not None:
                a = p.rw("ARANK") & 0xFC00             # keep BOOK_DRY (bits 10-11)
                for i, r in enumerate(ranks):
                    a |= (r & 3) << (2 * i)
                p.z.cmd("write-memory %d %d %d" % (S["ARANK"], a & 255, a >> 8))
            if lvl:
                p.wb("LVL", lvl)
                p.z.cmd("write-memory %d %d %d" % (S["XP"], XP_AT[lvl] & 255, XP_AT[lvl] >> 8))

    st = Stage(p, hero, mode="win", god=False, max_ticks=10 ** 9, log=lambda *a: None)
    return st


@contextlib.contextmanager
def session(hero_name, seed, audio=None, fast=True):
    """Emulator at the main menu (cold boot passed, seed fixed).  fast: tick-exact at max speed (no usable
    audio); not fast: emulator speed 100 + --aofile (raw sound: 15600 Hz, mono, unsigned 8-bit, written
    only while the emulated machine runs, 312 bytes per 50 Hz frame)."""
    if os.environ.get("ZRCP_PORT", "10000") == "10000":
        sys.exit("never port 10000: set ZRCP_PORT")
    require_no_zesarux()
    TMP.mkdir(parents=True, exist_ok=True)
    _imports()
    hero = K_KNIGHT if hero_name == "W" else K_WIZARD
    args = EMU_ARGS if fast else ("--vo", "null", "--ao", "null") + (("--aofile", str(audio)) if audio else ())
    with Harness() as h:
        h.launch(args)
        p = PT(h)
        p.mon = Mon(p)
        p.proto_start = 0
        p.snd_mode = None                         # music + SFX on (the boot default)
        p.load()
        p.wait_state(pt.GS_SELECT)
        p.wb("seed_fixed", 1)
        p.z.cmd("write-memory %d %d %d" % (S["seed_value"], seed & 255, seed >> 8))
        p.wb("INPUT_REPEAT", 0)
        p.wb("ANIM_FREEZE", 0)
        p.wb("INPUT_SRC", 1)
        p.release()
        rec = Rec(p)
        rec.audio = audio if not fast else None
        st = make_stage(p, hero)
        yield h, p, rec, st


def menu_start(p, rec, st, hero, dwell=2.0):
    """Main menu on screen `dwell` s, the hero toggled with key 2 when needed, START."""
    rec.start()
    st.wait_s(dwell)
    for _ in range(2):
        if p.rb("menu_hero") == hero:
            break
        p.tap("2")
        st.wait_s(1.5)
    st.wait_s(0.6)
    p.hold("1")
    p.wait_state(pt.GS_PLAYING)
    p.release()
    p.settle(3)
    st.load_level()


# ------------------------------------------------------------------ the scripts
def log(st, msg):
    print(f"[script D{st.rb('LVL_DEPTH')} r{st.room()} f{st.sysf() & 0xFFFF}] {msg}", flush=True)


def pick_up(st, it, tries=(0, 1, -1, 2)):
    """walk onto a floor item {s, x, ...}; True when the bag count changed."""
    n0 = st.bag_total()
    for dx in tries:
        st.walk_to(it["s"], it["x"] + dx)
        if st.bag_total() != n0:
            return True
    return st.bag_total() != n0


def cut(st, rec, fn, sec=0.6):
    """black ~sec at both ends of fn() (a poke / teleport): the sound runs on, the picture is black."""
    rec.black = True
    st.wait_s(sec)
    fn()
    st.wait_s(sec)
    rec.black = False


def teleport(st, p, r, s, x, left=False):
    """put the hero at (room r, storey s, col x): the same room_show / vis_reset / present_full stub tests/lp.py
    uses (no monsters are spawned: the room's population comes with the real transition).  Hidden by a cut."""
    from lp import w16
    from game_lib import stand_y
    kh = st.kh
    y = stand_y(s, kh)
    p.wb("CUR_ROOM", r)
    p.set_ent(0, ROOM=r, X=x, Y=y, PX=x * 8, PY=y * 8, FLAGS=1 | 2 | (8 if left else 0), MODE=0, DVIS=0)
    pc0 = p.pc()
    p.code([0x3E, r, 0xCD] + w16(S["room_show"]) + [0xCD] + w16(S["vis_reset"]) + [0xCD] + w16(S["present_full"]),
           game=True)
    p.z.cmd("set-register PC=%d" % pc0)
    p.release()
    p.settle(3)
    st.refresh_room()


def enter_lair(st, p, rec, walk_cols=7):
    """cut to the room next to the lair, walk through the real door/ladder into the lair (boss spawns by the
    game's own room transition).  -> the boss's kind id."""
    path = st.room_path(st.rb("LVL_START"), st.lair)
    prev = path[-2]
    kind = next(k for m_, k in st.neighbours(prev) if m_ == st.lair)
    ex = room_model.field(st.blk, prev, "RD_EXITS")

    def put():
        if kind in "LR":
            s = 1 if ex & S["RDX_" + ("LS1" if kind == "L" else "RS1")] else 0
            teleport(st, p, prev, s, 14, left=(kind == "L"))
            lo, hi = st.reach_span(s)
            tx = (lo + walk_cols) if kind == "L" else (hi - walk_cols)
            teleport(st, p, prev, s, max(lo, min(hi, tx)), left=(kind == "L"))
        elif kind == "D":
            col = room_model.field(st.blk, prev, "RD_DNCOL")
            teleport(st, p, prev, 1, col)
        else:
            col = room_model.field(st.blk, prev, "RD_UPCOL")
            teleport(st, p, prev, 0, col)
    cut(st, rec, put)
    log(st, f"in r{prev}, lair r{st.lair} via {kind}")
    st.leave(kind)
    return st.rb("LP_BOSS")


def d1_intro(st, p, rec, hero_name):
    """D1 (seeded): pick up the tome, read it from the BAG page (slow cursor), ladder down, leave through the
    vertical exit once (room 2 -> 5), fight what is there (a level-up is staged), pick up an item."""
    log(st, "D1 start")
    st.wait_s(1.5)
    for it in st.floor_items(st.room()):
        pick_up(st, it)
        log(st, f"picked {IT_NAME.get(it['type'])}")
    i = st.bag_find("BOOK")
    if i is not None:
        st.bag_show(goto=i, use=True)                 # open, 2 s dwell, cursor to the tome 0.7 s/step, read, close
        log(st, f"ranks {st.ranks()}")
    rec.marks.append(("d1fight", rec.total()))
    st.walk_to(1, st.room_ladders()[0])               # the room's ladder down to the lower storey
    st.walk_to(1, room_model.field(st.blk, st.room(), "RD_DNCOL"))
    st.leave("D")                                     # the vertical exit: the next room scrolls in
    st.wait_s(0.8)
    log(st, f"hostiles {[(h['kind'], h['x'], h['s']) for h in st.hostiles()]}")
    p.z.cmd("write-memory %d 36 0" % S["XP"])         # 4 XP short of level 2: the first kill levels up
    st.god = True
    if hero_name == "M":                              # a status effect on screen: Frost (rank poked in beside Spark)
        st.buff(ranks=[1, 0, 1, 0, 0])
        st.force_spell = 2
        st.fight_room(6)
        st.force_spell = None
    st.fight_room(160)
    st.wait_s(1.0)
    for it in st.floor_items(st.room()):
        if pick_up(st, it):
            log(st, f"picked {IT_NAME.get(it['type'])}")
            break
    st.wait_s(1.0)


def deep(st, p, rec, depth, hp, mp, ranks, first_spell=None, first_steps=0, fight_s=14):
    """cut to depth N (the real level_descend), cut to the room beside the lair, walk in, fight the boss."""
    cut(st, rec, lambda: (st.go_depth(depth), st.buff(hp=hp, mp=mp, ranks=ranks, lvl=depth)), sec=0.3)
    log(st, f"D{depth} start r{st.rb('LVL_START')} lair r{st.lair}")
    st.wait_s(1.2)
    boss = enter_lair(st, p, rec)
    rec.marks.append((f"lair{depth}", rec.total()))
    log(st, f"boss {boss:#x} hostiles {[(h['kind'], h['x'], h['hp']) for h in st.hostiles()]}")
    st.god = True
    if first_spell is not None:
        st.force_spell = first_spell
        st.fight_room(first_steps)
        st.force_spell = None
    st.fight_room(260, max_s=fight_s)
    log(st, "fight over")
    st.wait_s(2.0)


def warrior(st, p, rec):
    d1_intro(st, p, rec, "W")
    deep(st, p, rec, 4, 60, 20, [2, 2, 0, 0, 0])
    deep(st, p, rec, 7, 90, 30, [3, 3, 0, 0, 0])


def mage(st, p, rec):
    d1_intro(st, p, rec, "M")
    deep(st, p, rec, 5, 60, 40, [2, 2, 2, 1, 2])
    deep(st, p, rec, 8, 90, 60, [3, 3, 2, 2, 3])


PARTS = {"W": {"d1": lambda st, p, rec: d1_intro(st, p, rec, "W"),
               "d4": lambda st, p, rec: deep(st, p, rec, 4, 60, 20, [2, 2, 0, 0, 0]),
               "d7": lambda st, p, rec: deep(st, p, rec, 7, 90, 30, [3, 3, 0, 0, 0]),
               "all": warrior},
         "M": {"d1": lambda st, p, rec: d1_intro(st, p, rec, "M"),
               "d5": lambda st, p, rec: deep(st, p, rec, 5, 60, 40, [2, 2, 2, 1, 2]),
               "d8": lambda st, p, rec: deep(st, p, rec, 8, 90, 60, [3, 3, 2, 2, 3]),
               "all": mage}}


def cmd_script(hero_name, seed=0x1234, fast=True, audio=None, parts=None):
    with session(hero_name, seed, audio=audio, fast=fast) as (h, p, rec, st):
        hero = K_KNIGHT if hero_name == "W" else K_WIZARD
        sz = lambda: audio.stat().st_size if audio and Path(audio).exists() else 0
        s0 = (sz(), rec.sys())
        menu_start(p, rec, st, hero)
        try:
            for nm in parts or ["all"]:
                PARTS[hero_name][nm](st, p, rec)
        finally:
            TMP.mkdir(parents=True, exist_ok=True)
            pickle.dump(rec.frames, open(TMP / f"scr_{hero_name}.pkl", "wb"))
            pickle.dump((s0, (sz(), rec.sys()), rec.total()), open(TMP / f"span_{hero_name}.pkl", "wb"))
            print(f"captured {len(rec.frames)} probes, {rec.total() / 50:.1f} s")


# probe indices into the (deterministic) recordings picked by eye from contact sheets
SHOTS = [("shot1_menu", "W", "", 30), ("shot2_warrior_fight", "W", "scr", 1250), ("shot3_mage_bolt", "M", "scr", 1438),
         ("shot4_bag", "W", "scr", 400), ("shot5_deeper_d5", "W", "_d5", 279)]
GIF = ("W", 440, 560)


def cmd_shots():
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    for name, h, tag, i in SHOTS:
        scaled(scr_to_rgb(load_rec(h, tag)[i][0]), 3).save(OUT / "img" / f"{name}.png")


# ------------------------------------------------------------------ trailer
# hero alternates, every clip from a different depth
# (W D7 is left out: the scripted boss fight there stalls (hero idle 14 s), nothing readable to show)
TR_CLIPS = [("W", "d1fight"), ("M", "lair5"), ("W", "lair4"), ("M", "lair8")]
# window starts (s into the capture) picked by eye where the automatic most-motion pick is wrong
TR_STARTS = {"d1fight": 22.0, "lair5": 18.5}
TR_PARTS = {"W": ["d1", "d4", "d7"], "M": ["d5", "d8"]}
TR_MUSIC_S = 64                       # menu capture length (the trailer needs ~51 s of it)


def cmd_trailer_rec(what):
    """what = music: the title/menu theme once, uninterrupted, from the menu (sound ALL ON, nothing pressed).
    what = W|M: a scripted run with in-game sound set to EFFECTS ONLY through the real menu key 5 (ALL ON -> SFX ONLY),
    so its --aofile holds SFX and no song.  Always emulator speed 100 (real time), never turbo."""
    audio = TMP / f"tr_audio_{what}.raw"
    TMP.mkdir(parents=True, exist_ok=True)
    if audio.exists():
        audio.unlink()
    with session("W" if what == "music" else what, 0x1234, audio=audio, fast=False) as (h, p, rec, st):
        sz = lambda: audio.stat().st_size if audio.exists() else 0
        if what == "music":
            s0 = (sz(), rec.sys())
            rec.start()
            st.wait_s(TR_MUSIC_S)
        else:
            p.tap("5")
            st.wait_s(0.5)
            if p.rb("SND_MODE") != 2:
                sys.exit(f"SND_MODE {p.rb('SND_MODE')}: key 5 did not give EFFECTS ONLY")
            s0 = (sz(), rec.sys())
            hero = K_KNIGHT if what == "W" else K_WIZARD
            try:
                menu_start(p, rec, st, hero, dwell=0.5)
                for nm in TR_PARTS[what]:
                    PARTS[what][nm](st, p, rec)
            finally:
                if p.rb("SND_MODE") != 2:
                    print("WARNING: SND_MODE changed during the run:", p.rb("SND_MODE"))
        span = (s0, (sz(), rec.sys()), rec.total())
        pickle.dump({"frames": rec.frames, "span": span, "marks": rec.marks}, open(TMP / f"tr_{what}.pkl", "wb"))
        print(f"trailer capture {what}: {len(rec.frames)} probes, {rec.total() / 50:.1f} s, marks {rec.marks}")
    check_audio(rec.frames, audio, span)


def _tr_audio(what, d):
    """the capture's sound aligned to its frame timeline (anchored at the END, as assemble), DC-free, float -1..1."""
    raw = np.fromfile(TMP / f"tr_audio_{what}.raw", np.uint8)
    need = d["span"][2] * BPF
    a = raw[len(raw) - need:].astype(np.float32)
    a -= np.convolve(a, np.ones(2000) / 2000, mode="same")
    return a / 128.0


def _tr_timeline(d):
    """per 50 Hz display frame: probe index, picture change (bytes differing from the previous probe), black flag."""
    fr = d["frames"]
    tl_i = np.repeat(np.arange(len(fr)), [dd for _, dd in fr])
    first = np.concatenate([[0], np.cumsum([dd for _, dd in fr])])[:-1]
    act = np.zeros(len(tl_i), np.float32)
    for i in range(1, len(fr)):
        act[first[i]] = np.count_nonzero(np.frombuffer(fr[i][0][:6912], np.uint8) != np.frombuffer(fr[i - 1][0][:6912], np.uint8))
    black = np.array([not any(f) for f, _ in fr])[tl_i]
    return tl_i, act, black


def _tr_window(d, tlx, mark, length):
    """best `length`-frame window after `mark` (display frames of the capture): most picture change, no black frame."""
    tl_i, act, black = tlx
    mk = sorted(d["marks"], key=lambda x: x[1])
    t0 = dict(mk)[mark] + 25
    nxt = [t for _, t in mk if t > t0]
    cut_end = nxt[0] if nxt else len(act)                       # stay inside this scene
    cs, cb = np.concatenate([[0], np.cumsum(act)]), np.concatenate([[0], np.cumsum(black)])
    best, bt = -1.0, None
    for t in range(t0, cut_end - length):
        if cb[t + length] - cb[t]:
            continue
        v = cs[t + length] - cs[t]
        if v > best:
            best, bt = v, t
    return bt


def cmd_trailer(starts=None):
    """starts: {mark: seconds into the capture} overriding the automatic window pick (default TR_STARTS)."""
    starts = starts or TR_STARTS
    W, H, FPS = 768, 576, 50
    nf = lambda s: int(round(s * FPS))                                        # noqa: E731
    FADE, CLIP, TITLE, COVER = nf(0.4), nf(9.5), nf(3.0), nf(3.0)
    mus = pickle.load(open(TMP / "tr_music.pkl", "rb"))
    segs = [("title", TITLE)] + [(c, CLIP) for c in TR_CLIPS] + [("cover", COVER)]
    total = sum(n for _, n in segs)
    # ---- the music: ONE contiguous slice of the single menu capture, frame-aligned with its title picture
    music_all = _tr_audio("music", mus)
    if len(music_all) < total * BPF:
        sys.exit(f"music capture too short: {len(music_all)} < {total * BPF}")
    music = music_all[:total * BPF].copy()                                     # THE music: one slice, never spliced
    first = int(np.argmax(np.abs(music) > 0.02))
    print(f"music: first sound {first / AUDIO_HZ:.2f} s into the slice; capture {len(music_all) / AUDIO_HZ:.1f} s for "
          f"{mus['span'][2]} frames = {mus['span'][2] / 50:.1f} s (15600 Hz x 312 B/frame -> 50 fps real time)")
    music_src = music.copy()
    heroes = {h: pickle.load(open(TMP / f"tr_{h}.pkl", "rb")) for h in "WM"}
    aud = {h: _tr_audio(h, heroes[h]) for h in "WM"}
    tlx = {h: _tr_timeline(heroes[h]) for h in "WM"}
    env_pic = np.ones(total, np.float32)
    sfx = np.zeros(total * BPF, np.float32)
    env_sfx = np.zeros(total, np.float32)
    plan, pos = {}, 0
    for name, n in segs:
        e = np.ones(n, np.float32)
        a = min(FADE, n)
        e[:a] = np.linspace(0, 1, a, endpoint=False)
        b = nf(1.0) if name == "cover" else FADE
        e[n - b:] = np.minimum(e[n - b:], np.linspace(1, 0, b))
        env_pic[pos:pos + n] = e
        if isinstance(name, tuple):
            h, mark = name
            t = nf(starts[mark]) if starts and mark in starts else _tr_window(heroes[h], tlx[h], mark, n)
            plan[pos] = (h, t)
            sfx[pos * BPF:(pos + n) * BPF] = aud[h][t * BPF:(t + n) * BPF] * np.repeat(e, BPF)
            env_sfx[pos:pos + n] = 1
            print(f"clip {h} {mark}: capture {t / 50:.1f}-{(t + n) / 50:.1f} s -> trailer {pos / 50:.1f} s")
        pos += n
    # ---- levels: SFX ~ -10 dB under the music (RMS over the 20 ms blocks where an effect actually sounds)
    blk = sfx.reshape(total, BPF)
    act = (blk.std(1) > 0.01) & (env_sfx > 0)
    rms = lambda x: float(np.sqrt(np.mean(np.square(x)))) if len(x) else 1e-9     # noqa: E731
    m_rms, s_rms = rms(music), rms(blk[act].reshape(-1))
    g_sfx = m_rms * 10 ** (-10 / 20) / s_rms
    print(f"music rms {m_rms:.4f}, sfx active rms {s_rms:.4f} ({int(act.sum())} active frames), sfx gain {g_sfx:.3f}")
    me = np.ones(total * BPF, np.float32)
    fi, fo = AUDIO_HZ, 2 * AUDIO_HZ
    me[:fi] = np.linspace(0, 1, fi, endpoint=False)
    me[-fo:] = np.linspace(1, 0, fo)
    mix_m = music * me
    mix = mix_m + sfx * g_sfx
    gn = 0.89 / float(np.abs(mix).max())
    mix *= gn
    # contiguity guarantee: the music stem is exactly source-slice x (1 s in / 2 s out) envelope; no clip cut touches it
    assert np.array_equal(music, music_src) and np.allclose(mix_m, music_src * me)
    print(f"normalisation gain {gn:.3f} (peak 0.89)")
    TMP.mkdir(parents=True, exist_ok=True)
    wav = TMP / "trailer_audio.s16"
    (np.clip(mix, -1, 1) * 32000).astype("<i2").tofile(wav)
    (np.clip(mix_m * gn, -1, 1) * 32000).astype("<i2").tofile(TMP / "trailer_music_only.s16")
    # ---- picture
    mi = int(np.searchsorted(np.cumsum([dd for _, dd in mus["frames"]]), nf(1.0), side="right"))
    title = np.repeat(np.repeat(scr_to_rgb(mus["frames"][mi][0]), 3, 0), 3, 1)
    cover = np.zeros((H, W, 3), np.uint8)
    cv = np.asarray(Image.open(OUT / "img/cover_b.png").convert("RGB"))
    y0, x0 = (H - cv.shape[0]) // 2, (W - cv.shape[1]) // 2
    cover[y0:y0 + cv.shape[0], x0:x0 + cv.shape[1]] = cv
    (OUT / "video").mkdir(parents=True, exist_ok=True)
    out = OUT / "video" / "trailer.mp4"
    # no setpts/atempo/frame dropping: 1 emulated frame = 1 video frame = 312 audio bytes
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", "50", "-i", "-",
           "-f", "s16le", "-ar", str(AUDIO_HZ), "-ac", "1", "-i", str(wav),
           "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-r", "50",
           "-af", "aresample=44100", "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
           "-movflags", "+faststart", str(out)]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    pos = 0
    for name, n in segs:
        for i in range(n):
            if name == "title":
                im = title
            elif name == "cover":
                im = cover
            else:
                h, t = plan[pos]
                im = np.repeat(np.repeat(scr_to_rgb(heroes[h]["frames"][tlx[h][0][t + i]][0]), 3, 0), 3, 1)
            g = env_pic[pos + i]
            pr.stdin.write((im if g >= 1 else (im * g).astype(np.uint8)).tobytes())
        pos += n
    pr.stdin.close()
    if pr.wait():
        sys.exit("ffmpeg failed")
    print(f"{out}: {total} frames = {total / 50:.1f} s, {out.stat().st_size / 1e6:.1f} MB")


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
    elif a[0] == "script":
        cmd_script(a[1], parts=a[2:] or None)
    elif a[0] == "shots":
        cmd_shots()
    elif a[0] == "gif":
        cmd_gif(*GIF)
    elif a[0] == "clips":
        cmd_clip("W", 1110, 1400, "warrior.gif")
        cmd_clip("M", 1140, 1500, "mage.gif")
    elif a[0] == "trailer":
        if a[1:2] == ["rec"]:
            cmd_trailer_rec(a[2])
        else:
            cmd_trailer()
    elif a[0] == "video":
        cmd_video(a[1], reuse="--reuse" in a)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
