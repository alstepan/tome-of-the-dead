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
  ZRCP_PORT=<free port> python3 tools/itch_media.py walkthrough M --seed N [--god] [--out DIR] [--smoke TICKS] [--search A B [--no-pace] [--max-ticks N] [--events DIR]]
                                                     # full-game YouTube walkthrough: menu -> 2 START -> D1..D8 -> Tome -> win,
                                                     # real speed + AY, paced for viewers (WT_* below, idle ticks only), 1920x1080
                                                     # (x5 centred), H.264 + AAC, + chapters.txt.  --search A B: fast seed scan
                                                     # (no sound, no frames, same pacing) -> prints win/dead per seed.
  python3 tools/itch_media.py walkthrough --fmf RUN.fmf [--out DIR]   # a user's RZX at real speed: Fuse --playback ->
                                                     # FMF -> mp4 + chapters (tools/fmf.py; Fuse command in its docstring)
  python3 tools/itch_media.py scene tut|garg|imp|key|xp  # dev: one trailer scene at max speed -> build/itch/scene_<n>.png (1 frame/s)
  python3 tools/itch_media.py trailer rec music|tut|garg|imp|key|xp  # one trailer capture, speed 100 + sound
  python3 tools/itch_media.py trailer                # assemble video/trailer.mp4 from the captures (real time, trim only)
  ZRCP_PORT=<free port> python3 tools/itch_media.py trailer all   # THE v1.2 TRAILER RE-RECORD, one command: release
                                                     # build first (tools/build.sh -DDEBUG_KIT=0), no other ZEsarUX running
                                                     # (~5 min); records music + the 5 scenes, then assembles video/trailer.mp4

The v1.2 trailer (TRAILER-V12, ~76 s) = loading screen, title, then clips of the real game (a staged start, then real
time) in this order: tut (W) Brother Morrow's opening + the climb down; garg (M) a Gargoyle perched high on the wall
(y = 9s + 1), an Orc walking through it, the hero walks up, THE GARGOYLE WAKES UP, the fight; imp (W) Fire Imp (D6)
and wraith (M) Ice Shade (D7), their shots; the old-favourites montage vamp (W) skel (M) ogre (W, OGRE LORD D4 lair)
ghost (M) dlord (W, DEATHLORD D7 lair); key (M) level key + locked door; xp (W) the XP bar to a level-up; the cover.
A capture is one session ("mW" / "mM" hold the montage cuts of one hero); TR_CLIPS = (capture, mark, seconds).
Staged monsters follow the generator's rules: flyers + the Gargoyle on the cruise row 9s + 1, nobody inside the
1-col margin of a ladder / shaft (legal_x), lair bosses spawned by the real lair entry.  Scenes: sc_* below.

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
    Fuse may run (never touched).  WT_ALLOW_PARALLEL=1 skips the check on a shared machine (check_audio then judges the sound)."""
    if os.environ.get("WT_ALLOW_PARALLEL"):
        print("note: WT_ALLOW_PARALLEL set, other ZEsarUX processes are not refused")
        return
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


def check_audio(frames, audio_path, span, quiet_ok=False):
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
    if abs(ratio - 1) > (0.03 if quiet_ok else 0.02):     # scenes: 3 % (each level generation under DI adds a little sound-clock skew;
        #                                                        the sound is end-anchored, so the skew is at most ~0.6 s at a capture's start)
        sys.exit(f"AUDIO CHECK FAILED: ratio {ratio:.4f} (emulator not real time?)")
    if sd < 1.0 or len(np.unique(tail[::97])) < 4:
        if not quiet_ok:                                # an SFX-only scene can be (nearly) silent: the music carries it
            sys.exit("AUDIO CHECK FAILED: audio is silent/constant")
        print("note: (nearly) silent SFX capture, fine for a scene")


def assemble(frames, audio_path, out, scale=6, canvas=None, marks=None, chapters=None):
    """frames [(6912 B, display frames)] + the raw sound file -> constant-50 fps H.264 + AAC MP4.
    The sound file covers the whole emulator run, the recording its last sum(d) frames: it is anchored at the END
    (the file is complete when the emulator exits).  Black runs longer than 2*BLACK_KEEP are trimmed in picture
    and sound alike (10 ms crossfade) so a cut costs ~0.7 s, never a de-sync."""
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
        a -= _movavg2000(a)                                                   # drop the DC offset / slow drift
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
    vf = f"scale={256 * scale}:{192 * scale}:flags=neighbor"
    lvl = "4.0"
    if canvas:                                              # integer-scaled image centred on a black canvas (1080p50 needs level 4.2)
        vf += f",pad={canvas[0]}:{canvas[1]}:{(canvas[0] - 256 * scale) // 2}:{(canvas[1] - 192 * scale) // 2}:black"
        lvl = "4.2"
    cmd += ["-vf", vf + ",format=yuv420p", "-c:v", "libx264", "-preset", "slow", "-profile:v", "high" if canvas else "main", "-level", lvl,
            "-crf", "16", "-r", "50"]
    if audio is not None:
        cmd += ["-af", "aresample=44100", "-c:a", "aac", "-b:a", "128k", "-shortest"]
    cmd += ["-movflags", "+faststart", str(out)]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    last_i, buf = -1, b""
    for t in np.nonzero(keep)[0]:
        if tl[t] != last_i:                                 # convert lazily, once per captured frame (a 1 h run is ~90k probes)
            last_i, buf = tl[t], scr_to_rgb(frames[tl[t]][0]).tobytes()
        pr.stdin.write(buf)
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
    if marks and chapters:                                  # (title, display-frame index) -> YouTube chapters on the TRIMMED timeline
        kept = np.concatenate([[0], np.cumsum(keep)])      # kept[i] = kept display frames before frame i
        rows, prev = [], None
        for title, at in marks:
            t = int(kept[min(int(at), n)] / 50)
            if prev is not None and t - prev < 10:          # YouTube: chapters >= 10 s apart
                continue
            stamp = f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"
            rows.append(f"{stamp} {title}")
            prev = t
        Path(chapters).write_text("\n".join(rows) + "\n")
        print(f"{chapters}: {len(rows)} chapters")


def _movavg2000(a):
    """== np.convolve(a, ones(2000) / 2000, 'same') (window [i-1000, i+999], zero padded) in O(n): the full
    convolution of a 1 h recording (56 M samples) would take hours."""
    k = 2000
    c = np.concatenate([[0.0], np.cumsum(np.concatenate([np.zeros(k), a.astype(np.float64), np.zeros(k)]))])
    i = np.arange(len(a)) + k                               # index of a[i] in the padded array
    return ((c[i + 1000] - c[i - 1000]) / k).astype(np.float32)


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
    global pt, Bot, Harness, PT, Mon, S, K_KNIGHT, K_WIZARD, EMU_ARGS, RunEnd, room_model, HERO_W, IT_NAME, IT
    import playthrough as pt                      # noqa: F811
    from pt_plan import Harness, PT, Mon, S, K_KNIGHT, K_WIZARD, EMU_ARGS, RunEnd   # noqa: F811
    from pt_bot import Bot, HERO_W, IT_NAME, IT       # noqa: F811
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
            f = bytes(6912) if self.black else bytes(self.p.frame())
            if self.frames and self.frames[-1][0] == f:
                f = self.frames[-1][0]                    # identical picture: share the object (a 1 h run stays small in RAM)
            self.frames.append((f, d))

    def total(self):
        return sum(d for _, d in self.frames)


XP_AT = {1: 0, 2: 44, 3: 110, 4: 220, 5: 374, 6: 550, 7: 770, 8: 1012, 9: 1265}   # LARGER-D package 3 XP_NEXT


def make_stage(p, hero):
    """Bot used only as a LIBRARY (room geometry, pathing, exits, hostile scan, fight helper): every
    decision is made by the hand-written scripts, never by Bot.play()."""
    _imports()
    _rev()

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
def session(hero_name, seed, audio=None, fast=True, tut=False):
    """Emulator at the main menu (cold boot passed, seed fixed).  fast: tick-exact at max speed (no usable
    audio); not fast: emulator speed 100 + --aofile (raw sound: 15600 Hz, mono, unsigned 8-bit, written
    only while the emulated machine runs, 312 bytes per 50 Hz frame)."""
    if os.environ.get("ZRCP_PORT", "10000") == "10000":
        sys.exit("never port 10000: set ZRCP_PORT")
    if not fast:                                  # a tick-exact max-speed run has no sound to corrupt (parallel seed searches)
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
        p.tut_default_off = not tut               # tut: the real menu path (START, then 1 = TUTORIAL) stays live
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
    p.z.cmd("write-memory %d 40 0" % S["XP"])         # 4 XP short of level 2 (XP_NEXT[2] 44): the first kill levels up
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


def deep(st, p, rec, depth, hp, mp, ranks, first_spell=None, first_steps=0, fight_s=14, pre=None):
    """cut to depth N (the real level_descend), cut to the room beside the lair, walk in, fight the boss."""
    cut(st, rec, lambda: (st.go_depth(depth), st.buff(hp=hp, mp=mp, ranks=ranks, lvl=depth)), sec=0.3)
    log(st, f"D{depth} start r{st.rb('LVL_START')} lair r{st.lair}")
    st.wait_s(1.2)
    boss = enter_lair(st, p, rec)
    rec.marks.append((f"lair{depth}", rec.total()))
    log(st, f"boss {boss:#x} hostiles {[(h['kind'], h['x'], h['hp']) for h in st.hostiles()]}")
    st.god = True
    if pre is not None:
        pre(st, p, rec)
    if first_spell is not None:
        st.force_spell = first_spell
        st.fight_room(first_steps)
        st.force_spell = None
    st.fight_room(260, max_s=fight_s)
    log(st, "fight over")
    st.wait_s(2.0)


def give(st, name, qty=1):
    """poke an item into the first free bag slot (type, qty, ident-state)."""
    for i, (t, q) in enumerate(st.bag()):
        if t == 0:
            st.p.z.cmd("write-memory %d %d %d %d" % (S["BAG"] + 3 * i, IT_NAME_REV[name], qty, 0))
            return i
    return None


def inv_clip(st, p, rec):
    """Inventory clip (trailer): hurt hero, a potion + a helm + a weapon poked in; I opens the bag, the cursor moves slowly
    across items (name line readable), DRINK the heal potion, close."""
    st.wait_s(1.0)
    for n, q in (("P_HEAL", 2), ("H_HELM", 1), ("W_LONG", 1)):
        give(st, n, q)
    st.p.set_ent(0, HP=max(6, st.heroe()["MAXHP"] // 3))
    st.wait_s(0.5)
    log(st, f"bag {st.bag()[:8]}")
    rec.marks.append(("inv", rec.total()))
    p.tap("I")
    p.until(lambda: p.rb("PAGE_OPEN") == 1 and p.pc() == S["select_tick"], 20)
    st.wait_s(1.0)
    rc = lambda: (p.rb("pg_rc"), p.rb(S["pg_rc"] + 1))      # noqa: E731
    pi = max(i for i, (t, q) in enumerate(st.bag()) if t == IT_NAME_REV["P_HEAL"])      # the stack of 2
    row, col = 1 + pi // 5, pi % 5
    for _ in range(8):                                        # to the first bag row, one slow step at a time
        if rc()[0] >= row:
            break
        p.tap("A")
        st.wait_s(0.9)
    for _ in range(6):                                        # across the items, 0.9 s per step (reads the name line)
        if rc()[1] >= col:
            break
        p.tap("P")
        st.wait_s(0.9)
    st.wait_s(0.6)
    p.tap("FIRE")                                             # the verb strip
    st.wait_s(1.0)
    p.tap("FIRE")                                             # DRINK
    st.wait_s(0.8)
    if p.rb("PAGE_OPEN"):
        p.tap("CAPS", "SPACE")
        p.until(lambda: p.rb("PAGE_OPEN") == 0, 20)
    p.tick(3)
    st.wait_s(1.5)
    rec.marks.append(("inv_end", rec.total()))


def icon_clip(st, p, rec):
    """Icon-mode clip (trailer): DOWN+FIRE enters ICON MODE, the cursor steps along the bar (0.7 s/step) to Frost
    (slot 3), FIRE casts it at the monster; then number key 5 (Lightning) + FIRE."""
    st.wait_s(0.8)
    rec.marks.append(("icon", rec.total()))
    p.hold("A", "SPACE")
    p.tick(5)
    p.release()
    p.tick(2)
    log(st, f"ICON_MODE {p.rb('ICON_MODE')} slot {p.rb('SEL_SLOT')}")
    st.wait_s(1.0)
    for _ in range(10):
        if p.rb("SEL_SLOT") == 3:
            break
        p.tap("P")
        st.wait_s(0.8)
    st.wait_s(0.8)
    p.tap("FIRE")
    st.wait_s(2.5)
    p.tap("6")                                                # direct select: Lightning
    st.wait_s(1.0)
    p.tap("FIRE")
    st.wait_s(1.5)
    rec.marks.append(("icon_end", rec.total()))


def warrior(st, p, rec):
    d1_intro(st, p, rec, "W")
    deep(st, p, rec, 4, 60, 20, [2, 2, 0, 0, 0])
    deep(st, p, rec, 7, 90, 30, [3, 3, 0, 0, 0])


def mage(st, p, rec):
    d1_intro(st, p, rec, "M")
    deep(st, p, rec, 5, 60, 40, [2, 2, 2, 1, 2])
    deep(st, p, rec, 8, 90, 60, [3, 3, 2, 2, 3])


IT_NAME_REV = {}


def _rev():
    _imports()
    IT_NAME_REV.update(IT)


PARTS = {"W": {"d1": lambda st, p, rec: d1_intro(st, p, rec, "W"),
               "inv": inv_clip,
               "d4": lambda st, p, rec: deep(st, p, rec, 4, 60, 20, [2, 2, 0, 0, 0]),
               "d7": lambda st, p, rec: deep(st, p, rec, 7, 90, 30, [3, 3, 0, 0, 0]),
               "all": warrior},
         "M": {"d1": lambda st, p, rec: d1_intro(st, p, rec, "M"),
               "d3": lambda st, p, rec: deep(st, p, rec, 3, 60, 40, [2, 2, 2, 1, 2], pre=icon_clip),
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


# ------------------------------------------------------------------ trailer (v1.2, TRAILER-V12)
# Five scenes, each its own session (boot, menu, SFX-only through key 5, a staged start): everything on screen is the
# real game running; the memory pokes only stage a start (a depth, the hero's kit, which monsters stand where) and are
# hidden by a black cut, never a speed-up or an edited frame.  The clip starts exactly at its (capture, mark)
# and lasts its TR_CLIPS seconds.  (scene, mark, seconds)
TR_CLIPS = [("tut", "tut", 8.0), ("garg", "garg", 12.8), ("imp", "imp", 7.0), ("wraith", "wraith", 7.0),
            ("mW", "vamp", 2.5), ("mM", "skel", 2.5), ("mW", "ogre", 4.0), ("mM", "ghost", 2.5), ("mW", "dlord", 3.0),
            ("key", "key", 8.5), ("xp", "xp", 9.0),
            ("arch", "arch", 9.6), ("tome", "door", 3.0), ("tome", "tome", 8.5)]
TR_AT_MARK = tuple(m for _, m, _ in TR_CLIPS)
TR_CAPS = {}                          # captions (from s, to s, text) by mark; none in v1.2
TR_MUSIC_S = 100                      # menu capture length (the trailer needs ~60 s of it)

EF_ACTIVE, EF_HOSTILE, EF_LEFT = 1, 4, 8


def clear_room_mons(p):
    """every monster slot 1..15 off (the staged room holds only what the scene puts in)."""
    n = S["P_ENT_STRIDE"]
    mem = bytearray(p.z.read_memory(S["P_ENTITIES"], 16 * n))
    for k in range(1, 16):
        mem[k * n + S["E_FLAGS"]] = 0
        mem[k * n + S["E_ROOM"]] = 0
    p.z.cmd("write-memory %d %s" % (S["P_ENTITIES"], " ".join(str(b) for b in mem)))
    for nm in ("ST_FLAGS", "ST_T1", "ST_T2", "ST_X"):
        p.z.cmd("write-memory %d %s" % (S[nm], " ".join(["0"] * 16)))
    for nm in ("TURN_PEND", "TURN_TICK", "COMBAT_NOT_BEFORE", "FX_DROP", "SPQ_K"):      # (never dh_rtick: it is a bank-0 byte, $E57F = bank-7 CODE while the game runs)
        p.wb(nm, 0)


def spawn(st, p, kind, x, s, hp=None, flags=EF_ACTIVE | EF_HOSTILE, left=False, rcd=1, fly=False):
    """put one monster into the first free slot of the current room (the nm3b.py World.put fixture)."""
    n = S["P_ENT_STRIDE"]
    raw = p.z.read_memory(S["P_ENTITIES"], 16 * n)
    slot = next(k for k in range(1, 16) if not raw[k * n + S["E_FLAGS"]] & EF_ACTIVE)
    h = st.kb(kind, "KT_BH")
    from game_lib import stand_y
    y = 9 * s + 1 if fly else stand_y(s, h)
    hp = hp or p.rb(S["kind_tab"] + S["KT_HP"] + kind)
    mem = [0] * n
    mem[S["E_KIND"]], mem[S["E_ROOM"]], mem[S["E_FLAGS"]] = kind, st.room(), flags | (EF_LEFT if left else 0)
    mem[S["E_X"]], mem[S["E_Y"]], mem[S["E_HP"]], mem[S["E_MAXHP"]] = x, y, hp, hp
    mem[S["E_POT"]], mem[S["E_PX"]], mem[S["E_PY"]] = rcd, x * 8, y * 8
    p.z.cmd("write-memory %d %s" % (S["P_ENTITIES"] + slot * n, " ".join(str(b) for b in mem)))
    return slot


def refresh(p):
    """the staged entity table becomes the live world: build_live + vis_reset + a full present (a stub, as teleport)."""
    from lp import w16
    pc0 = p.pc()
    p.code([0xCD] + w16(S["build_live"]) + [0xCD] + w16(S["vis_reset"]) + [0xCD] + w16(S["present_full"]), game=True)
    p.z.cmd("set-register PC=%d" % pc0)
    p.release()
    p.settle(3)


def stage_room(st, p, depth, hp, mp, ranks, lvl, room=None, hx=None, hs=1, left=False):
    """staging (call inside cut()): the real descent to `depth`, the kit, a room cleared of monsters with the hero on
    storey hs at col hx (default: the start room, col 4).  -> the walkable span (lo, hi) of that storey."""
    st.go_depth(depth)
    st.buff(hp=hp, mp=mp, ranks=ranks, lvl=lvl)
    r = st.rb("LVL_START") if room is None else room
    teleport(st, p, r, hs, 4 if hx is None else hx, left=left)
    clear_room_mons(p)
    st.refresh_room()
    return st.reach_span(hs)


def sc_tut(st, p, rec):
    """Tutorial opening (D0): Brother Morrow's balloon + log line while the hero stands at the top of the ladder, then
    the hero climbs down (DOWN = the A key) as the goal line says."""
    rec.marks.append(("tut", rec.total()))
    st.wait_s(4.0)
    for _ in range(14):                                          # one DOWN per turn (no key repeat): the ladder, 0.35 s apart
        if not p.turn("J"):
            st.wait_s(0.3)
        e = p.ent(0)
        if e["Y"] >= 9 and (e["Y"] + 4) % 9 == 8:
            break
        st.wait_s(0.1)
    st.wait_s(0.6)
    for _ in range(7):                                           # then right, toward the room
        p.turn("L")
        st.wait_s(0.15)
    st.wait_s(2.0)


def legal_x(st, x, w):
    """the game's lp_legal rule for a body w cols wide: a 1-col margin round every ladder / shaft footprint
    (x + w - 1 <= f - 3 or x >= f + 4 for each ladder left col f), 2 cols off the walls / doors."""
    lo, hi = st.reach_span(1)
    return lo + 2 <= x and x + w - 1 <= hi - 2 and all(x + w - 1 <= f - 3 or x >= f + 4 for f in st.room_ladders())


def find_x(st, want, w, direction=0):
    """the legal col nearest `want` (direction -1 / +1: only that side of it)."""
    for d in range(0, 30):
        for x in ((want - d, want + d) if direction == 0 else (want + direction * d,)):
            if legal_x(st, x, w):
                return x
    raise RuntimeError(f"no legal col near {want}")


def sc_garg(st, p, rec):
    """D6, the Mage.  The game perches a Gargoyle high on the wall (y = 9s + 1): the statue.  An Orc walks in from the
    right THROUGH it (a perched Gargoyle is intangible) toward the hero, who waits, kills it, then walks up to the
    statue: within 2 cols it wakes ("THE GARGOYLE WAKES UP."), flies and fights."""
    box = {}
    kg, ko = S["K_GARGOYLE"], S["K_ORC"]

    def put():
        stage_room(st, p, 6, 100, 90, [2, 2, 2, 1, 2], 6, hx=6)
        gw = st.kb(kg, "KT_BW")
        for r in [st.rb("LVL_START")] + [r for r in st.rooms if r != st.rb("LVL_START")]:    # a room that fits the layout
            teleport(st, p, r, 1, 4)
            st.refresh_room()
            lo, hi = st.reach_span(1)
            cand = [x for x in range(lo + st.kw + 6, hi - 9) if legal_x(st, x, gw)]
            if cand:
                break
        g = cand[0]
        ox = find_x(st, g + 8, st.kb(ko, "KT_BW"), -1)
        hx = g - st.kw - 6
        teleport(st, p, r, 1, hx)
        clear_room_mons(p)
        st.refresh_room()
        box.update(r=r, lo=lo, hi=hi, g=g, hx=hx, ox=ox)
        spawn(st, p, kg, g, 1, hp=60, flags=EF_ACTIVE | EF_HOSTILE | S["EF_GHOST"], fly=True)   # 60 HP: a fight to watch
        spawn(st, p, ko, ox, 1, left=True)
        refresh(p)
    cut(st, rec, put, sec=0.4)
    rec.marks.append(("garg", rec.total()))
    log(st, f"garg {box}")
    st.wait_s(1.5)                                               # the statue, high on the wall
    st.god = True
    for _ in range(40):                                          # the Orc walks through it; the hero holds
        orcs = [h for h in st.hostiles() if h["kind"] == ko]
        if not orcs or orcs[0]["x"] < box["g"] - 3:
            break
        st.act("WAIT")
    st.fight_room(120, until=lambda: not [h for h in st.hostiles() if h["kind"] == ko], max_s=8)
    st.wait_s(0.6)
    for _ in range(12):                                          # now up to the statue, one slow step at a time
        garg = [h for h in st.hostiles() if h["kind"] == kg]
        if not garg or not garg[0]["fl"] & S["EF_GHOST"]:
            break
        st.act("L")
        st.wait_s(0.35)
    st.fight_room(200, max_s=9)
    st.wait_s(1.5)


def flyer_clip(st, p, rec, depth, hero_kit, gap, mark, hold=3.5, fight_s=3.0, total=7.0):
    """a flyer (the row-31 alias: Fire Imp D6 / Ice Shade D7) on the cruise row 9s + 1, inside its shot range: the hero
    holds `hold` seconds (the shots are the real flyer AI's), then fights."""
    def put():
        stage_room(st, p, depth, *hero_kit, depth, hx=6)
        x = find_x(st, 6 + st.kw + gap, st.kb(S["K_ALIAS"], "KT_BW"), 1)
        spawn(st, p, S["K_ALIAS"], x, 1, hp=3 * p.rb(S["kind_tab"] + S["KT_HP"] + S["K_ALIAS"]), left=True, fly=True)
        refresh(p)
    cut(st, rec, put, sec=0.4)
    rec.marks.append((mark, rec.total()))
    t0 = rec.total()
    st.god = True
    while rec.total() - t0 < hold * 50:                          # stand still, the flyer shoots (seconds, not turns)
        st.act("WAIT")
    st.fight_room(200, max_s=fight_s)
    st.wait_s(max(0.3, total - (rec.total() - t0) / 50))


def sc_imp(st, p, rec):
    """Fire Imp (D6), the Warrior."""
    flyer_clip(st, p, rec, 6, (120, 20, [2, 2, 0, 0, 0]), 5, "imp", hold=3.5, fight_s=3.0)


def sc_wraith(st, p, rec):
    """Frost Wraith (shown in game as ICE SHADE, D7), the Mage."""
    flyer_clip(st, p, rec, 7, (100, 60, [2, 2, 2, 1, 2]), 7, "wraith", hold=3.5, fight_s=3.0)


def mont_floor(st, p, rec, depth, kind, hero_kit, mark, secs, gap=5, fly=False):
    """one montage cut: a regular of the level (staged on the floor / cruise row, 3x HP so the fight lasts) and the hero."""
    def put():
        stage_room(st, p, depth, *hero_kit, depth, hx=6)
        x = find_x(st, 6 + st.kw + gap, st.kb(kind, "KT_BW"), 1)
        spawn(st, p, kind, x, 1, hp=min(250, 3 * p.rb(S["kind_tab"] + S["KT_HP"] + kind)), left=True, fly=fly)
        refresh(p)
    cut(st, rec, put, sec=0.3)
    rec.marks.append((mark, rec.total()))
    st.god = True
    st.fight_room(200, max_s=secs)


def mont_lair(st, p, rec, depth, hero_kit, mark, secs):
    """one montage cut: the real lair boss of `depth` (the game spawns it on entering the lair), the fight."""
    def put():
        st.go_depth(depth)
        st.buff(hp=hero_kit[0], mp=hero_kit[1], ranks=hero_kit[2], lvl=depth)
        p.wb("LVL_FLAGS", p.rb("LVL_FLAGS") | S["LF_KEYC"] | S["LF_KEYM"])      # the level keys in hand: the lair door can be walked to
    cut(st, rec, put, sec=0.3)
    boss = enter_lair(st, p, rec)
    rec.marks.append((mark, rec.total()))
    log(st, f"boss {boss:#x}")
    st.god = True
    st.fight_room(260, max_s=secs)


KIT_W = (120, 30, [3, 3, 0, 0, 0])
KIT_M = (100, 60, [3, 3, 2, 2, 3])


def sc_montW(st, p, rec):
    """old favourites, the Warrior: Vampire (D3), OGRE LORD (D4 lair), DEATHLORD (D7 lair)."""
    mont_floor(st, p, rec, 3, S["K_VAMPIRE"], KIT_W, "vamp", 2.5)
    mont_lair(st, p, rec, 4, KIT_W, "ogre", 4.0)
    mont_lair(st, p, rec, 7, KIT_W, "dlord", 3.0)


def sc_montM(st, p, rec):
    """old favourites, the Mage: Skeleton, Ghost (D3)."""
    mont_floor(st, p, rec, 3, S["K_SKELETON"], KIT_M, "skel", 2.5)
    mont_floor(st, p, rec, 3, S["K_GHOST"], KIT_M, "ghost", 2.5, fly=True)


def sc_key(st, p, rec):
    """D1 (seeded): the level key lies in room 0; the hero picks it up ("YOU FIND A CYAN KEY", the panel key by the bag),
    then walks into the locked door (EG_LOCK between rooms 6 | 7): "YOU UNLOCK THE DOOR", through it."""
    lock = next(m for m in range(12) if m % 3 != 2 and st.edge_flags(m) & S["EG_LOCK"])
    near_right = bool(st.edge_flags(lock) & S["EG_NEARR"])
    prev, kind = (lock + 1, "L") if near_right else (lock, "R")        # the near side bars; the door's other side is the far room
    key = next(i for i in st.floor_items(st.keyroom) if i["type"] == S["IT_KEY"])
    log(st, f"key r{st.keyroom} {key}, lock edge {lock} near {'R' if near_right else 'L'}")
    cut(st, rec, lambda: teleport(st, p, st.keyroom, key["s"], key["x"] + 7), sec=0.4)
    rec.marks.append(("key", rec.total()))
    st.wait_s(1.0)
    st.walk_to(key["s"], key["x"])
    log(st, f"keys held {st.lflags() & (S['LF_KEYC'] | S['LF_KEYM'])}")
    st.wait_s(2.0)

    def put():
        ex = room_model.field(st.blk, prev, "RD_EXITS")
        s_ = 1 if ex & S["RDX_" + ("LS1" if kind == "L" else "RS1")] else 0
        lo, hi = st.reach_span(s_) if st.room() == prev else (None, None)
        teleport(st, p, prev, s_, 14, left=(kind == "L"))
        lo, hi = st.reach_span(s_)
        tx = (lo + 7) if kind == "L" else (hi - 7)
        teleport(st, p, prev, s_, max(lo, min(hi, tx)), left=(kind == "L"))
    cut(st, rec, put, sec=0.4)
    st.wait_s(0.8)
    st.leave(kind)
    st.wait_s(2.0)


def sc_xp(st, p, rec):
    """Warrior at D3, level 2 with the bar nearly full (XP poked just under XP_NEXT[3]): two monsters, the kills fill the
    XP bar on row 21 and the second level-up lands."""
    def put():
        lo, hi = stage_room(st, p, 3, 80, 30, [2, 2, 0, 0, 0], 2, hx=5)
        p.z.cmd("write-memory %d %d %d" % (S["XP"], 106, 0))       # XP_NEXT[3] = 110
        spawn(st, p, S["K_SKELETON"], 5 + st.kw + 6, 1, left=True)
        spawn(st, p, S["K_GOBLIN"], 5 + st.kw + 10, 1, left=True)
        refresh(p)
    cut(st, rec, put, sec=0.4)
    rec.marks.append(("xp", rec.total()))
    st.god = True
    st.wait_s(0.8)
    st.fight_room(200, max_s=9)
    st.wait_s(2.0)


def sc_arch(st, p, rec):
    """D8, the Warrior: the real lair of the Necromancer Archmage (the game spawns it on entering the lair), the fight to its
    death ("THE SEAL BREAKS").  The Archmage's HP is brought down to the last few points mid-fight so it fits the clip
    (as the playthrough bot's boss_poke does); the kill, the log and the seal are the game's."""
    def put():
        st.go_depth(8)
        st.buff(hp=KIT_W[0], mp=KIT_W[1], ranks=KIT_W[2], lvl=8)
        p.wb("LVL_FLAGS", p.rb("LVL_FLAGS") | S["LF_KEYC"] | S["LF_KEYM"])
    cut(st, rec, put, sec=0.3)
    boss = enter_lair(st, p, rec)
    rec.marks.append(("arch", rec.total()))
    log(st, f"boss {boss:#x}")
    st.god = True
    t0 = st.sysf()
    poked = False
    for _ in range(300):
        st.fight_room(1, max_s=None)
        if st.rb("GAME_STATE") != S["GS_PLAYING"] or st.lflags() & S["LF_SEAL_OPEN"]:
            break
        if not poked and ((st.sysf() - t0) & 0xFFFFFF) > 4.5 * 50:
            for h in st.hostiles():
                if h["kind"] == S["K_ARCHMAGE"] and h["hp"] > 6:
                    p.set_ent(h["slot"], HP=6)
                    poked = True
    st.wait_s(2.5)


def sc_tome(st, p, rec):
    """D8, the Mage: the Archmage (1 HP, so the cut is short) dies to the hero's real hit -> the seal breaks; the hero walks
    through the Sanctum door and strikes the Tome with the staff until it is ash: "THE TOME IS DESTROYED", "A GATE GLEAMS"."""
    def put():
        st.go_depth(8)
        st.buff(hp=KIT_M[0], mp=KIT_M[1], ranks=KIT_M[2], lvl=8)
        p.wb("LVL_FLAGS", p.rb("LVL_FLAGS") | S["LF_KEYC"] | S["LF_KEYM"])
    cut(st, rec, put, sec=0.3)
    boss = enter_lair(st, p, rec)
    st.god = True

    def kill():                      # the hero's own hit does the killing; only the boss's HP is brought to 1 (black cut)
        t0 = st.sysf()
        while not st.lflags() & S["LF_SEAL_OPEN"] and ((st.sysf() - t0) & 0xFFFFFF) < 40 * 50:
            for h in st.hostiles():
                if h["kind"] == S["K_ARCHMAGE"] and h["hp"] > 1:
                    p.set_ent(h["slot"], HP=1)
            st.fight_room(1)
        st.fight_room(150, max_s=25)             # the Archmage's summons die too: nothing follows the hero into the Sanctum

    def to_door():                   # the hero stands 6 cols short of the Sanctum door (legal span, facing it)
        ex = room_model.field(st.blk, st.room(), "RD_EXITS")
        k = next(k for m_, k in st.neighbours(st.room()) if m_ == st.sanctum)
        s_ = 1 if ex & S["RDX_" + ("LS1" if k == "L" else "RS1")] else 0
        teleport(st, p, st.room(), s_, 14, left=(k == "L"))
        lo, hi = st.reach_span(s_)
        teleport(st, p, st.room(), s_, max(lo, min(hi, (lo + 6) if k == "L" else (hi - 6))), left=(k == "L"))
    cut(st, rec, lambda: (kill(), to_door()), sec=0.2)
    log(st, f"seal open {bool(st.lflags() & S['LF_SEAL_OPEN'])}")
    sn = st.sanctum
    kind = next(k for m_, k in st.neighbours(st.room()) if m_ == sn)
    rec.marks.append(("door", rec.total()))
    st.wait_s(0.5)
    st.leave(kind)                               # the real bump opens the broken-seal door, then the hero walks in
    st.wait_s(0.3)
    rec.marks.append(("door_end", rec.total()))
    st.refresh_room()
    lect = [(c, rr) for rr in range(S["STOREY_ROWS"], 18) for c in range(32) if st.cell_tf(c, rr) & S["TF_ATTACK"]]
    left = min(c for c, _ in lect) < 16
    lo, hi = st.reach_span(1)
    # the Sanctum walk is long: a black cut puts the hero (legal storey-1 col, 4 cols short of the lectern, facing it)
    cut(st, rec, lambda: teleport(st, p, sn, 1, (lo + 4) if left else (hi - 4), left=left), sec=0.3)
    rec.marks.append(("tome", rec.total()))
    st.wait_s(0.8)
    for _ in range(14):
        e, s_, x_, _st = st.hero_pos()
        if st.rb("TOME_HP") == 0:
            break
        if not st.act("H" if left else "L"):
            st.wait_s(0.3)
        st.wait_s(0.3)
    log(st, f"TOME_HP {st.rb('TOME_HP')}")
    st.wait_s(3.5)


def sc_ogre(st, p, rec):
    """Warrior vs the OGRE LORD in its real D4 lair (itch shot / GIF)."""
    mont_lair(st, p, rec, 4, KIT_W, "ogre", 6.0)
    st.wait_s(0.5)


def sc_bag(st, p, rec):
    """Warrior D3: a potion, a helm and a long weapon in the bag; I opens the bag page, the cursor rests on the helm (its
    properties on the lines under the grid)."""
    def put():
        stage_room(st, p, 3, 120, 30, [3, 3, 0, 0, 0], 3, hx=6)
        for n, q in (("P_HEAL", 2), ("H_HELM", 1), ("W_LONG", 1)):
            give(st, n, q)
    cut(st, rec, put, sec=0.4)
    rec.marks.append(("bag", rec.total()))
    st.wait_s(0.5)
    i = st.bag_find("H_HELM")
    st.bag_show(goto=i, dwell=0.8, step_s=0.6, close_dwell=0.2)


# ---- itch page shots / GIFs (v1.2): each scene is recorded once at max speed (the same deterministic scenes), the frames
# are pickled, and `shots12 make` writes the files from picked offsets (display frames after the scene's mark)
SH_SCENES = {"sh_ogre": ("W", False, sc_ogre, "ogre"), "sh_ice": ("M", False, sc_wraith, "wraith"),
             "sh_imp": ("W", False, sc_imp, "imp"), "sh_garg": ("M", False, sc_garg, "garg"),
             "sh_tut": ("W", True, sc_tut, "tut"), "sh_key": ("M", False, sc_key, "key"),
             "sh_tome": ("M", False, sc_tome, "tome"), "sh_bag": ("W", False, sc_bag, "bag")}


SCENES = {"tut": ("W", True, sc_tut), "garg": ("M", False, sc_garg), "imp": ("W", False, sc_imp),
          "wraith": ("M", False, sc_wraith), "key": ("M", False, sc_key), "xp": ("W", False, sc_xp),
          "mW": ("W", False, sc_montW), "arch": ("W", False, sc_arch), **{k: v[:3] for k, v in SH_SCENES.items()}, "tome": ("M", False, sc_tome), "mM": ("M", False, sc_montM)}


def start_tut(p, st, rec):
    """real path: START, then 1 = TUTORIAL (the key is held until D0's start, never into its first tick)."""
    rec.start()
    st.wait_s(0.5)
    p.hold("1")
    p.tick(3)
    p.release()
    st.wait_s(1.0)
    p.hold("1")
    p.z.cmd("set-breakpoint 21 PC=%d" % S["tut_d0"])
    for _ in range(60):
        p.z.cmd("cpu-step")
        p.z.cmd("run 20000000")
        if p.pc() == S["tut_d0"]:
            break
    p.z.cmd("set-breakpoint 21")
    p.release()
    p.z.cmd("cpu-step")
    p.wait_state(pt.GS_PLAYING)
    p.settle(3)


def run_scene(what, fast, audio=None, sfx_only=True):
    _imports()
    hero_name, tut, fn = SCENES[what]
    hero = K_KNIGHT if hero_name == "W" else K_WIZARD
    with session(hero_name, 0x1234, audio=audio, fast=fast, tut=tut) as (h, p, rec, st):
        sz = lambda: audio.stat().st_size if audio and Path(audio).exists() else 0     # noqa: E731
        if sfx_only:
            p.tap("5")                                    # ALL ON -> EFFECTS ONLY through the real menu key
            st.wait_s(0.5)
            if p.rb("SND_MODE") != 2:
                sys.exit(f"SND_MODE {p.rb('SND_MODE')}: key 5 did not give EFFECTS ONLY")
        s0 = (sz(), rec.sys())
        if tut:
            for _ in range(2):
                if p.rb("menu_hero") == hero:
                    break
                p.tap("2")
                st.wait_s(1.5)
            start_tut(p, st, rec)
        else:
            menu_start(p, rec, st, hero, dwell=0.5)
        try:
            fn(st, p, rec)
        finally:
            rec.marks.append((what + "_end", rec.total()))
            if sfx_only and p.rb("SND_MODE") != 2:
                print("WARNING: SND_MODE changed during the run:", p.rb("SND_MODE"))
        return rec, (s0, (sz(), rec.sys()), rec.total())


def cmd_scene(what):
    """dev: run a scene at max speed (no sound) and write build/itch/scene_<what>.png, 1 frame per second."""
    rec, span = run_scene(what, True, sfx_only=False)
    TMP.mkdir(parents=True, exist_ok=True)
    tl = np.repeat(np.arange(len(rec.frames)), [d for _, d in rec.frames])
    ms = [t for m, t in rec.marks if not m.endswith("_end")]
    secs = 12 if len(ms) == 1 else 4                      # 1 frame/s from each mark (a scene) / 4 per montage cut
    pics = []
    for t0 in ms:
        pics += [scaled(scr_to_rgb(rec.frames[tl[min(t0 + k * 50 + 10, len(tl) - 1)]][0]), 1) for k in range(secs)]
    cols = 4
    w, hh = pics[0].size
    sh = Image.new("RGB", (cols * w, ((len(pics) + cols - 1) // cols) * hh))
    for i, im in enumerate(pics):
        sh.paste(im, ((i % cols) * w, (i // cols) * hh))
    sh.save(TMP / f"scene_{what}.png")
    print(f"scene {what}: {rec.total() / 50:.1f} s, marks {rec.marks}, sheet build/itch/scene_{what}.png")


def cmd_trailer_rec(what):
    """what = music: the title/menu theme once, uninterrupted, from the menu (sound ALL ON, nothing pressed).
    what = a scene (tut garg imp key xp): that scene's own session with in-game sound set to EFFECTS ONLY through the
    real menu key 5, so its --aofile holds SFX and no song.  Always emulator speed 100 (real time), never turbo."""
    audio = TMP / f"tr_audio_{what}.raw"
    TMP.mkdir(parents=True, exist_ok=True)
    if audio.exists():
        audio.unlink()
    if what == "music":
        with session("W", 0x1234, audio=audio, fast=False) as (h, p, rec, st):
            s0 = (audio.stat().st_size if audio.exists() else 0, rec.sys())
            rec.start()
            st.wait_s(TR_MUSIC_S)
            span = (s0, (audio.stat().st_size, rec.sys()), rec.total())
    else:
        rec, span = run_scene(what, False, audio=audio)
    pickle.dump({"frames": rec.frames, "span": span, "marks": rec.marks}, open(TMP / f"tr_{what}.pkl", "wb"))
    print(f"trailer capture {what}: {len(rec.frames)} probes, {rec.total() / 50:.1f} s, marks {rec.marks}")
    check_audio(rec.frames, audio, span, quiet_ok=what != "music")


def _tr_audio(what, d):
    """the capture's sound aligned to its frame timeline (anchored at the END, as assemble), DC-free, float -1..1."""
    raw = np.fromfile(TMP / f"tr_audio_{what}.raw", np.uint8)
    need = d["span"][2] * BPF
    a = raw[len(raw) - need:].astype(np.float32)
    a -= np.convolve(a, np.ones(2000) / 2000, mode="same")
    return a / 128.0


def _tr_timeline(d):
    """per 50 Hz display frame: probe index and black flag (the clips start at their marks, no window search)."""
    fr = d["frames"]
    tl_i = np.repeat(np.arange(len(fr)), [dd for _, dd in fr])
    black = np.array([not any(f) for f, _ in fr])[tl_i]
    return tl_i, None, black


_FONT = None


def caption_bar(text, w, h, k=3):
    """`text` in the game's own font6x8_bold (assets/gfx/fonts, 6 px advance, MSB-left rows), bright yellow on black,
    nearest-neighbour x3, centred in a w x h bar."""
    global _FONT
    if _FONT is None:
        _FONT = (ROOT / "assets/gfx/fonts/font6x8_bold.bin").read_bytes()
    bits = np.zeros((8, 6 * len(text)), bool)
    for n, ch in enumerate(text.upper()):
        g = np.frombuffer(_FONT[(ord(ch) - 32) * 8:(ord(ch) - 32) * 8 + 8], np.uint8)
        bits[:, n * 6:n * 6 + 6] = np.unpackbits(g[:, None], axis=1)[:, :6].astype(bool)
    big = np.repeat(np.repeat(bits, k, 0), k, 1)
    bar = np.zeros((h, w, 3), np.uint8)
    y0, x0 = (h - big.shape[0]) // 2, (w - big.shape[1]) // 2
    assert x0 >= 0, "caption too long"
    bar[y0:y0 + big.shape[0], x0:x0 + big.shape[1]][big] = (255, 255, 0)
    return bar


def cmd_trailer():
    """assemble video/trailer.mp4 from the music capture + one capture per scene (every clip starts at its mark)."""
    W, H, FPS, BAR = 768, 624, 50, 48                       # 3x game picture under a 48 px black caption bar
    nf = lambda s: int(round(s * FPS))                                        # noqa: E731
    FADE, TITLE, COVER = nf(0.4), nf(3.0), nf(3.0)
    mus = pickle.load(open(TMP / "tr_music.pkl", "rb"))
    segs = [("loading", TITLE), ("title", TITLE)] + [((c[0], c[1]), nf(c[2])) for c in TR_CLIPS] + [("cover", COVER)]
    total = sum(n for _, n in segs)
    # ---- the music: ONE contiguous slice of the single menu capture, frame-aligned with its title picture
    # (v1.2 fix: from the FIRST NOTE of the whole file, not the end-anchored tail of the capture, which began mid-tune)
    u8 = np.fromfile(TMP / "tr_audio_music.raw", np.uint8)
    i0 = int(np.argmax(u8 != 128))                                             # the first sample that is not digital silence
    raw = u8.astype(np.float32)
    raw -= np.convolve(raw, np.ones(2000) / 2000, mode="same")
    raw /= 128.0
    music_all = raw[max(0, i0 - AUDIO_HZ // 20):]                              # 50 ms of lead-in before the first sound
    if len(music_all) < total * BPF:
        sys.exit(f"music capture too short: {len(music_all)} < {total * BPF}")
    music = music_all[:total * BPF].copy()                                     # THE music: one slice, never spliced
    first = int(np.argmax(np.abs(music) > 0.02))
    print(f"music: first sound {first / AUDIO_HZ:.2f} s into the slice (file start {i0 / AUDIO_HZ:.2f} s); "
          f"{len(music_all) / AUDIO_HZ:.1f} s available for a {total / 50:.1f} s trailer")
    music_src = music.copy()
    scn = [c[0] for c in TR_CLIPS]
    heroes = {h: pickle.load(open(TMP / f"tr_{h}.pkl", "rb")) for h in scn}
    aud = {h: _tr_audio(h, heroes[h]) for h in scn}
    tlx = {h: _tr_timeline(heroes[h]) for h in scn}
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
            mt = dict(heroes[h]["marks"])[mark]
            t = mt
            if t + n > heroes[h]["span"][2] or tlx[h][2][t]:      # a black cut INSIDE a clip is a staging poke (imp: D6 -> D7)
                sys.exit(f"scene {h}: its {n / 50:.1f} s clip runs past the capture ({heroes[h]['span'][2] / 50:.1f} s) "
                         f"or starts on a black frame")
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
    title = np.zeros((H, W, 3), np.uint8)
    title[BAR:] = np.repeat(np.repeat(scr_to_rgb(mus["frames"][mi][0]), 3, 0), 3, 1)
    loading = np.zeros((H, W, 3), np.uint8)             # the loading screen (768x576) under the caption bar
    loading[BAR:] = np.asarray(Image.open(ROOT / "assets/gfx/loading/loading_l3d.png").convert("RGB"))
    cover = np.zeros((H, W, 3), np.uint8)
    cv = np.asarray(Image.open(OUT / "img/cover_b.png").convert("RGB"))
    y0, x0 = (H - cv.shape[0]) // 2, (W - cv.shape[1]) // 2
    cover[y0:y0 + cv.shape[0], x0:x0 + cv.shape[1]] = cv      # 630x500 unscaled, centred
    (OUT / "video").mkdir(parents=True, exist_ok=True)
    out = OUT / "video" / "trailer.mp4"
    # no setpts/atempo/frame dropping: 1 emulated frame = 1 video frame = 312 audio bytes
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", "50", "-i", "-",
           "-f", "s16le", "-ar", str(AUDIO_HZ), "-ac", "1", "-i", str(wav),
           "-c:v", "libx264", "-preset", "slow", "-profile:v", "main", "-level", "4.0", "-crf", "16", "-pix_fmt", "yuv420p", "-r", "50",
           "-af", "aresample=44100", "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
           "-movflags", "+faststart", str(out)]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    pos = 0
    for name, n in segs:
        for i in range(n):
            if name == "loading":
                im = loading
            elif name == "title":
                im = title
            elif name == "cover":
                im = cover
            else:
                h, t = plan[pos]
                im = np.zeros((H, W, 3), np.uint8)
                im[BAR:] = np.repeat(np.repeat(scr_to_rgb(heroes[h]["frames"][tlx[h][0][t + i]][0]), 3, 0), 3, 1)
                for c0, c1, txt in TR_CAPS.get(name[1], []):
                    if nf(c0) <= i < nf(c1):
                        im[:BAR] = caption_bar(txt, W, BAR)
            g = env_pic[pos + i]
            pr.stdin.write((im if g >= 1 else (im * g).astype(np.uint8)).tobytes())
        pos += n
    pr.stdin.close()
    if pr.wait():
        sys.exit("ffmpeg failed")
    print(f"{out}: {total} frames = {total / 50:.1f} s, {out.stat().st_size / 1e6:.1f} MB")


def _sh_frames(name):
    d = pickle.load(open(TMP / f"sh_{name}.pkl", "rb"))
    tl = np.repeat(np.arange(len(d["frames"])), [x for _, x in d["frames"]])
    t0 = dict(d["marks"])[SH_SCENES[name][3]]
    return d, tl, t0


def cmd_sh_rec(name):
    rec, _ = run_scene(name, True, sfx_only=False)
    TMP.mkdir(parents=True, exist_ok=True)
    pickle.dump({"frames": rec.frames, "marks": rec.marks}, open(TMP / f"sh_{name}.pkl", "wb"))
    print(f"shots12 rec {name}: {rec.total() / 50:.1f} s, marks {rec.marks}")


def cmd_sh_sheet(name, step=25, n=24):
    """contact sheet of one recorded scene: a frame every `step` display frames from its mark, offset in the corner."""
    d, tl, t0 = _sh_frames(name)
    from PIL import ImageDraw
    pics = []
    for k in range(n):
        i = min(t0 + k * step, len(tl) - 1)
        im = scaled(scr_to_rgb(d["frames"][tl[i]][0]), 1)
        ImageDraw.Draw(im).text((2, 2), str(k * step), fill=(255, 255, 255))
        pics.append(im)
    cols = 4
    w, hh = pics[0].size
    sh = Image.new("RGB", (cols * w, ((len(pics) + cols - 1) // cols) * hh))
    for i, im in enumerate(pics):
        sh.paste(im, ((i % cols) * w, (i // cols) * hh))
    sh.save(TMP / f"shsheet_{name}.png")
    print(f"build/itch/shsheet_{name}.png (marks {d['marks']})")


def _gif(frames, name, fps=25):
    """the cmd_clip GIF writer on an explicit list of 6912-B screens at 50 Hz: 2x, Spectrum palette, equal frames merged."""
    pal = []
    for br in (0xD7, 0xFF):
        for c in range(8):
            pal += [(c >> 1 & 1) * br, (c >> 2 & 1) * br, (c & 1) * br]
    pal += [0] * (768 - len(pal))
    ref = Image.new("P", (1, 1))
    ref.putpalette(pal)
    q = [scaled(scr_to_rgb(f), 2).quantize(palette=ref, dither=Image.Dither.NONE) for f in frames[::50 // fps]]
    mi, md = [q[0]], [1000 // fps]
    for b in q[1:]:
        if b.tobytes() == mi[-1].tobytes():
            md[-1] += 1000 // fps
        else:
            mi.append(b)
            md.append(1000 // fps)
    md[-1] += 600
    out = OUT / "img" / name
    mi[0].save(out, save_all=True, append_images=mi[1:], duration=md, loop=0, optimize=True, disposal=1)
    print(f"{out.name}: {sum(md) / 1000:.1f} s, {out.stat().st_size / 1e6:.2f} MB, {len(mi)} frames")


# (file, scene, display-frame offset after the scene's mark) ; (file, scene, from, to) for GIFs
SH_PNG = [("shot2_warrior_fight.png", "sh_ogre", 250), ("shot3_mage_bolt.png", "sh_ice", 250),
          ("shot4_bag.png", "sh_bag", 175), ("shot5_deeper_d5.png", "sh_imp", 150),
          ("shot6_tutorial.png", "sh_tut", 50), ("shot7_key_door.png", "sh_key", 300),
          ("shot8_gargoyle_statue.png", "sh_garg", 300), ("shot9_tome_destroyed.png", "sh_tome", 300)]
SH_GIF = [("walk_fight.gif", "sh_garg", 275, 550), ("warrior.gif", "sh_ogre", 150, 400), ("mage.gif", "sh_ice", 100, 375)]


def cmd_sh_menu():
    """shot1_menu: the real main menu (nothing pressed), x3."""
    _imports()
    with session("W", 0x1234, fast=True) as (h, p, rec, st):
        st.wait_s(1.0)
        scaled(scr_to_rgb(bytes(p.frame())), 3).save(OUT / "img" / "shot1_menu.png")
    print("wrote shot1_menu.png")


def cmd_sh_make():
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    for fn, name, off in SH_PNG:
        d, tl, t0 = _sh_frames(name)
        scaled(scr_to_rgb(d["frames"][tl[t0 + off]][0]), 3).save(OUT / "img" / fn)
        print("wrote", fn)
    for fn, name, a, b in SH_GIF:
        d, tl, t0 = _sh_frames(name)
        _gif([d["frames"][tl[i]][0] for i in range(t0 + a, min(t0 + b, len(tl)))], fn)


# ------------------------------------------------------------------ full-game walkthrough (YouTube)
# Pacing = idle ticks only (no key held): the bot's decisions and the game's turns are untouched, but the idle ticks
# are part of the run, so a seed must be searched WITH the same pacing (--search does).
WT_TURN_TICKS = 10        # 0.4 s: a bot action (turn) never takes less than this many 25 Hz ticks
WT_BAG_TICKS = 38         # 1.5 s on the bag page when it opens
WT_BAG_TAP = 8            # 0.32 s after every key press inside the bag page
WT_ROOM_TICKS = 25        # 1.0 s on each new room / new depth
WT_BOSS_TICKS = 50        # 2.0 s after a boss dies
WT_WIN_TICKS = 50         # 2.0 s on the win screen
WT_TAIL_TICKS = 25        # + 1 s of end card in the picture so the cut is not abrupt


def make_walker(p, hero, god, pace, marks_cb, max_ticks=10 ** 6):
    """The expert bot (tests/pt_plan.Player) + the viewer pacing.  marks_cb(title) records a chapter mark."""
    _imports()
    from pt_plan import Player
    from pt_bot import GS_PLAYING
    kname = {}
    for k, v in S.items():
        if k.startswith("K_") and isinstance(v, int):
            kname.setdefault(v, k[2:])

    class Walker(Player):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.in_bag, self.seen_rooms, self.seen_depth = False, set(), 0
            self.boss, self.tome_seen = None, False
            tap = self.p.tap

            def paced_tap(*keys, **kw2):
                tap(*keys, **kw2)
                if pace and self.in_bag:
                    self.idle(WT_BAG_TAP)
            self.p.tap = paced_tap

        def idle(self, n):
            # the bot's timers (blocked 250, ignore 800, ping-pong 500, stuck / level caps) count mon.ticks: idle ticks
            # are taken back out of that clock so the bot decides exactly as it does unpaced (the game itself still
            # sees them: hunger and the RNG move on)
            for _ in range(n):
                self.p.tick(1)
                self.mon.ticks -= 1

        def ev(self, text):
            super().ev(text)
            if text.startswith("Tome bump") and not self.tome_seen:
                self.tome_seen = True
                marks_cb("The Tome")

        def act(self, *keys):
            t0 = self.mon.ticks
            ok = super().act(*keys)
            if pace and self.rb("GAME_STATE") == GS_PLAYING:
                self.idle(max(0, WT_TURN_TICKS - (self.mon.ticks - t0)))
            return ok

        def bag_nav(self, slot):
            if pace:
                self.idle(WT_BAG_TICKS)
            return super().bag_nav(slot)

        def bag_use(self, slot):
            self.in_bag = True
            try:
                return super().bag_use(slot)
            finally:
                self.in_bag = False

        def boss_here(self):
            for h in self.hostiles():
                if h["gold"] or h["kind"] in (S["K_OGRE"], S["K_DKNIGHT"], S["K_ARCHMAGE"]):
                    return h
            return None

        def step(self):
            if self.rb("GAME_STATE") == GS_PLAYING:
                d, r = self.rb("LVL_DEPTH"), self.rb("CUR_ROOM")
                if d != self.seen_depth:
                    self.seen_depth, self.boss = d, None
                    self.seen_rooms = {(d, r)}
                    marks_cb(f"Depth {d}")
                    if pace:
                        self.idle(WT_ROOM_TICKS)
                elif (d, r) not in self.seen_rooms:
                    self.seen_rooms.add((d, r))
                    if pace:
                        self.idle(WT_ROOM_TICKS)
                if r == getattr(self, "lair", None):
                    b = self.boss_here()
                    if b and not self.boss:
                        self.boss = kname.get(b["kind"], "BOSS")
                        marks_cb(f"Depth {d} boss: {self.boss.replace('_', ' ').title()}")
                    elif self.boss and not b:
                        self.boss = None
                        marks_cb(f"__boss_dead D{d}")
                        if pace:
                            self.idle(WT_BOSS_TICKS)
            super().step()

    w = Walker(p, hero, mode="win", god=god, max_ticks=max_ticks, level_cap=60000)
    w.boss_poke = 60 if god else 0
    return w


def walk_run(seed, god=False, pace=True, audio=None, capture=True, hero_name="M", max_ticks=10 ** 6):
    """One bot run from the menu (2 START, no tutorial).  capture: speed 100 + --aofile + frames; else tick-exact max
    speed, nothing recorded (seed search).  Returns (end, rec, span, marks, bot)."""
    _imports()
    hero = K_KNIGHT if hero_name == "W" else K_WIZARD
    marks = []
    with session(hero_name, seed, audio=audio, fast=not capture) as (h, p, rec, st):
        sz = lambda: audio.stat().st_size if audio and Path(audio).exists() else 0     # noqa: E731
        s0 = (sz(), rec.sys())
        menu_start(p, rec, st, hero)
        if not capture:
            p.tick = rec.orig                                  # no frame grabbing
        rec.marks.append(("Menu", 0))
        bot = make_walker(p, hero, god, pace, lambda t: marks.append((t, rec.total())), max_ticks)
        end = bot.play()
        if end == "win" and pace:
            marks.append(("Victory", rec.total()))
            bot.idle(WT_WIN_TICKS + WT_TAIL_TICKS)
        span = (s0, (sz(), rec.sys()), rec.total())
        if end.startswith("no path") and os.environ.get("WT_DEBUG"):         # why did the planner give up?
            print("DEBUG flags", hex(bot.lflags()), "keyroom", bot.keyroom, "lair", bot.lair, "visited", sorted(bot.visited),
                  "skip", sorted(bot.skip_rooms), "bag", bot.bag()[:8], flush=True)
            for rm in bot.rooms:
                print("DEBUG floor r%d" % rm, bot.floor_items(rm), flush=True)
            print("DEBUG edges", [(m, hex(bot.edge_flags(m))) for m in bot.rooms], flush=True)
        bot.info = dict(ticks=bot.mon.ticks, lvl=bot.rb("LVL"), depth=bot.rb("LVL_DEPTH"), turns=bot.p.rw("TURN_COUNTER"))
        return end, rec, span, marks, bot


def cmd_walkthrough(hero_name, seed, god=False, out=None, smoke=0):
    out = Path(out or TMP / "walkthrough")
    out.mkdir(parents=True, exist_ok=True)
    audio = out / "audio.raw"
    if audio.exists():
        audio.unlink()
    end, rec, span, marks, bot = walk_run(seed, god, True, audio, True, hero_name, smoke or 10 ** 6)
    pickle.dump((rec.frames, span, marks), open(out / "walk.pkl", "wb"))
    print(f"end {end}: {rec.total() / 50:.1f} s, pokes {dict(bot.pokes)}, stats {dict(bot.stats)}")
    if end != "win" and not smoke:
        sys.exit(f"the run ended {end}, not win: pick another seed")
    walk_assemble(out, out / ("smoke.mp4" if smoke else "mage_walkthrough.mp4"))


def walk_assemble(out, mp4):
    frames, span, marks = pickle.load(open(Path(out) / "walk.pkl", "rb"))
    check_audio(frames, Path(out) / "audio.raw", span)
    chap = [("Start - Depth 1", 0)] + [m for m in marks if not m[0].startswith("__")]
    assemble(frames, Path(out) / "audio.raw", mp4, scale=5, canvas=(1920, 1080), marks=chap,
             chapters=Path(mp4).with_name("chapters.txt"))


def cmd_walk_search(hero_name, a, b, god=False, pace=True, max_ticks=10 ** 6, events=None):
    for seed in range(a, b + 1):
        end, rec, span, marks, bot = walk_run(seed, god, pace, None, False, hero_name, max_ticks)
        print(f"SEED {seed}: {end} ticks {bot.info['ticks']} lvl {bot.info['lvl']} depth {bot.info['depth']} "
              f"turns {bot.info['turns']} pokes {dict(bot.pokes)}", flush=True)
        if events:                                  # event texts without tick numbers: diff two runs (pacing neutrality)
            Path(events).mkdir(parents=True, exist_ok=True)
            Path(events, f"{seed}.ev").write_text("\n".join(t for _, t in bot.events) + "\n")


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
    elif a[0] == "scene":
        cmd_scene(a[1])
    elif a[0] == "shots12":
        {"rec": lambda: cmd_sh_rec(a[2]), "sheet": lambda: cmd_sh_sheet(a[2]), "make": cmd_sh_make, "menu": cmd_sh_menu}[a[1]]()
    elif a[0] == "trailer":
        if a[1:2] == ["rec"]:
            cmd_trailer_rec(a[2])
        elif a[1:2] == ["all"]:
            for w in ["music"] + [c[0] for c in TR_CLIPS]:
                cmd_trailer_rec(w)
            cmd_trailer()
        else:
            cmd_trailer()
    elif a[0] == "walkthrough" and "--fmf" in a:          # a user's Fuse RZX, replayed by Fuse into an FMF (tools/fmf.py)
        import fmf
        fmf.video(a[a.index("--fmf") + 1], a[a.index("--out") + 1] if "--out" in a else TMP / "walkthrough")
    elif a[0] == "walkthrough":
        hero = a[1] if a[1:2] and a[1] in ("W", "M") else "M"
        god = "--god" in a
        if "--search" in a:
            i = a.index("--search")
            cmd_walk_search(hero, int(a[i + 1], 0), int(a[i + 2], 0), god, "--no-pace" not in a,
                            int(a[a.index("--max-ticks") + 1]) if "--max-ticks" in a else 10 ** 6,
                            a[a.index("--events") + 1] if "--events" in a else None)
        elif "--assemble" in a:
            walk_assemble(a[a.index("--out") + 1], a[a.index("--assemble") + 1])
        else:
            cmd_walkthrough(hero, int(a[a.index("--seed") + 1], 0), god,
                            a[a.index("--out") + 1] if "--out" in a else None,
                            int(a[a.index("--smoke") + 1]) if "--smoke" in a else 0)
    elif a[0] == "video":
        cmd_video(a[1], reuse="--reuse" in a)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
