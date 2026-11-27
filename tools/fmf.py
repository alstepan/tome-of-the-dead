#!/usr/bin/env python3
"""Fuse Movie File (FMF, Fuse 1.x `--movie-start`) decoder + the RZX walkthrough video pipeline.

  python3 tools/fmf.py info FILE.fmf [--text]        # frames, sound, A/V ratio (+ OCR'd text timeline)
  python3 tools/fmf.py video FILE.fmf OUTDIR [--no-border]
        # -> OUTDIR/mage_walkthrough.mp4 (1920x1080: default the 320x240 canvas with border x4, --no-border the paper x5; H.264 High 4.2 + AAC, 50 fps, real time,
        #    no trimming), chapters.txt, events.txt, start/mid/win .png, thumb_1280x720.png

Why FMF: ZEsarUX 12.1 replays a Fuse RZX by its own interrupt clock (it ignores the per-frame fetch counts), so the
R register and with it the game's master seed (newgame0.asm `ld a, r`) diverge and the run desyncs in D1.  Fuse plays
its own RZX exactly and writes picture + sound per emulated frame into the FMF:

  Fuse --machine 128 --playback RUN.rzx --movie-start RUN.fmf --movie-stop-after-rzx      (speed 100: sound on)

Format (Fuse movie.c): 16-B header "FMF_V1" <e|E> <U|Z> rate screen timing sndfmt freq16 <S|M> "\\n", then ONE zlib
stream (Z) of chunks: '$' x y16 w h16 + RLE planes (bitmap, attr[, hires attr]) of a 40-col x 240-line canvas
(8-px cells incl. border; R = 80 cols), 'S' fmt freq16 ch len-1(16) + samples (P = s16, A = A-law),
'N' rate screen timing = a new frame, 'X' = end.  RLE: a byte equal to the previous literal is followed by a count of
further copies (0-255); after a count the next byte is always a literal.  Each plane resets the RLE.
"""
import re
import subprocess
import sys
import zlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
FFMPEG = "/opt/homebrew/bin/ffmpeg"
PAPER = (24, 4)                       # paper origin in the 320x240 canvas: line 24, cell column 4


# ------------------------------------------------------------------ decoder
class _Stream:
    """Byte reader over the (possibly zlib-compressed, possibly truncated) chunk stream."""

    def __init__(self, f, compressed):
        self.f, self.z = f, zlib.decompressobj() if compressed else None
        self.buf, self.pos, self.eof = b"", 0, False

    def _fill(self, n):
        while len(self.buf) - self.pos < n and not self.eof:
            raw = self.f.read(1 << 16)
            if not raw:
                self.eof = True
                break
            self.buf = self.buf[self.pos:] + (self.z.decompress(raw) if self.z else raw)
            self.pos = 0
        return len(self.buf) - self.pos >= n

    def read(self, n):
        if not self._fill(n):
            raise EOFError
        b = self.buf[self.pos:self.pos + n]
        self.pos += n
        return b

    def rle(self, n):
        """n decoded bytes of one RLE plane."""
        out = bytearray()
        last = -1
        while len(out) < n:
            d = self.read(1)[0]
            out.append(d)
            if d == last:
                c = self.read(1)[0]
                out.extend(bytes([d]) * c)
                last = -1
            else:
                last = d
        if len(out) != n:
            raise ValueError(f"RLE overrun {len(out)} > {n}")
        return out


def alaw_decode(b):
    a = np.frombuffer(b, np.uint8) ^ 0x55
    sign = a & 0x80
    exp = (a >> 4) & 7
    man = (a & 15).astype(np.int32)
    v = np.where(exp == 0, (man << 4) + 8, ((man << 4) + 0x108) << np.maximum(exp - 1, 0))
    return np.where(sign, v, -v).astype(np.int16)


def frames(path):
    """Yield (bitmap 240xW uint8, attr 240xW uint8, sound int16 array (mono or interleaved), info) per frame.
    W = 40 cells (80 for HiRes 'R').  The arrays are live views: copy to keep them."""
    f = open(path, "rb")
    h = f.read(16)
    if h[:6] != b"FMF_V1" or h[6:7] != b"e":
        sys.exit(f"{path}: not a little-endian FMF V1 ({h[:8]!r})")
    s = _Stream(f, h[7:8] == b"Z")
    info = {"rate": h[8], "screen": chr(h[9]), "timing": chr(h[10]), "snd": chr(h[11]),
            "freq": h[12] | h[13] << 8, "ch": 2 if h[14:15] == b"S" else 1, "end": False}
    bm = np.zeros((240, 80), np.uint8)
    at = np.zeros((240, 80), np.uint8)
    snd, started = [], False
    while True:
      try:
        t = s.read(1)
        if t == b"$":
            x, y0, y1, w, h0, h1 = s.read(6)
            y, hh = y0 | y1 << 8, h0 | h1 << 8
            n = w * hh
            planes = [s.rle(n), s.rle(n)] + ([s.rle(n)] if info["screen"] == "R" else [])
            if info["screen"] == "R":      # HiRes: two bitmaps (even/odd 8-px columns) + one attr
                b1 = np.frombuffer(planes[0], np.uint8).reshape(hh, w)
                b2 = np.frombuffer(planes[1], np.uint8).reshape(hh, w)
                bm[y:y + hh, 2 * x:2 * (x + w):2], bm[y:y + hh, 2 * x + 1:2 * (x + w):2] = b1, b2
                at[y:y + hh, 2 * x:2 * (x + w):2] = at[y:y + hh, 2 * x + 1:2 * (x + w):2] = \
                    np.frombuffer(planes[2], np.uint8).reshape(hh, w)
            else:
                bm[y:y + hh, x:x + w] = np.frombuffer(planes[0], np.uint8).reshape(hh, w)
                at[y:y + hh, x:x + w] = np.frombuffer(planes[1], np.uint8).reshape(hh, w)
        elif t == b"S":
            fmt, f0, f1, ch, l0, l1 = s.read(6)
            n = ((l0 | l1 << 8) + 1) * (2 if ch == ord("S") else 1)
            info["freq"], info["ch"] = f0 | f1 << 8, 2 if ch == ord("S") else 1
            if fmt == ord("P"):
                snd.append(np.frombuffer(s.read(2 * n), "<i2"))
            elif fmt == ord("A"):
                snd.append(alaw_decode(s.read(n)))
            else:
                sys.exit(f"unsupported FMF sound format {chr(fmt)!r}")
        elif t == b"N":
            r, scr, tim = s.read(3)
            if started:
                yield bm[:, :80 if info["screen"] == "R" else 40], at[:, :80 if info["screen"] == "R" else 40], \
                    np.concatenate(snd) if snd else np.zeros(0, np.int16), info
                snd = []
            started = True
            info["rate"], info["screen"], info["timing"] = r, chr(scr), chr(tim)
        elif t == b"X":
            info["end"] = True
            break
        else:
            sys.exit(f"bad FMF chunk {t!r} at decoded offset {s.pos}")
      except EOFError:                    # truncated file (Fuse killed): keep the complete frames
        info["truncated"] = True
        break
    if started:
        yield bm[:, :80 if info["screen"] == "R" else 40], at[:, :80 if info["screen"] == "R" else 40], \
            np.concatenate(snd) if snd else np.zeros(0, np.int16), info


# ------------------------------------------------------------------ picture
def paper(bm, at):
    """192x32 bitmap + 192x32 attr (per pixel line) of the 256x192 paper."""
    y, x = PAPER
    return bm[y:y + 192, x:x + 32], at[y:y + 192, x:x + 32]


def to_rgb(pb, pa):
    """Paper -> 192x256x3, the itch_media palette (normal 0xD7, bright 0xFF).  Fuse stores the bitmap with FLASH
    already applied, so flashing cells blink as on the real machine."""
    bits = np.unpackbits(pb, axis=1).astype(bool)
    a = np.repeat(pa, 8, 1)
    lv = np.where(a & 0x40, 0xFF, 0xD7).astype(np.uint8)
    idx = np.where(bits, a & 7, (a >> 3) & 7)
    return (np.stack([idx >> 1 & 1, idx >> 2 & 1, idx & 1], -1) * lv[..., None]).astype(np.uint8)


# ------------------------------------------------------------------ 6x8-font OCR (chapter events)
def _font():
    g = {}
    code = 32
    for ln in open(ROOT / "assets/gfx/fonts/font6x8.asm"):
        m = re.match(r"\s*DEFB\s+(.*?);", ln)
        if m:
            rows = [int(v.strip().lstrip("$"), 16) >> 2 for v in m.group(1).split(",")]
            key = bytes(rows)
            if any(rows):
                g.setdefault(key, chr(code))
            code += 1
    return g


FONT = None


def ocr(pb):
    """24 text rows of the paper, read at the 6-px pitch (42 chars, the log / info line / page layout), best of the
    6 pixel phases per row.  Unknown cells -> '~', empty -> ' '."""
    global FONT
    FONT = FONT or _font()
    bits = np.unpackbits(pb, axis=1)                         # 192x256 (ink = 1)
    out = []
    for r in range(24):
        blk = bits[r * 8:r * 8 + 8]
        best = ""
        for ph in range(6):
            n = (256 - ph) // 6
            cells = blk[:, ph:ph + n * 6].reshape(8, n, 6)
            vals = (cells * (1 << np.arange(5, -1, -1))).sum(2).astype(np.uint8).T     # n x 8 rows
            s = "".join(" " if not v.any() else FONT.get(v.tobytes(), "~") for v in vals)
            if sum(c.isalnum() for c in s) > sum(c.isalnum() for c in best):
                best = s
        out.append(best.rstrip())
    return out


# ------------------------------------------------------------------ passes
def scan(path, text_every=5, verbose=False):
    """Pass 1: frame count, all sound, text events.  -> (n_frames, sound int16, info, events[(frame, row, text)])."""
    n, snd, ev, last_txt, info = 0, [], [], [None] * 24, {}
    prev_pb = None
    for bm, at, s, info in frames(path):
        snd.append(s.copy())
        if n % text_every == 0:
            pb, _ = paper(bm, at)
            if prev_pb is None or not np.array_equal(pb, prev_pb):
                for r, t in enumerate(ocr(pb)):
                    if t != last_txt[r]:
                        last_txt[r] = t
                        if sum(c.isalnum() for c in t) >= 2:
                            ev.append((n, r, t))
                            if verbose:
                                print(f"{n / 50:8.2f} r{r:02d} {t}")
                prev_pb = pb.copy()
        n += 1
    info = dict(info)
    return n, np.concatenate(snd) if snd else np.zeros(0, np.int16), info, ev


def av_report(n, snd, info):
    ch = info.get("ch", 1)
    samples = len(snd) // ch
    exp = n * info["freq"] / 50
    ratio = samples / exp if exp else 0
    print(f"frames {n} ({n / 50:.2f} s at 50 fps), rate 1:{info.get('rate')}, screen {info.get('screen')!r}, "
          f"timing {info.get('timing')!r}, end marker {info.get('end')}")
    print(f"sound {info.get('snd')!r} {info['freq']} Hz x{ch}: {samples} samples = {samples / info['freq']:.2f} s, "
          f"ratio vs frames {ratio:.5f} (50.02 Hz machine: expect ~0.9996)")
    return ratio


def _title(name):
    return " ".join(w.capitalize() for w in name.split())


def chapters(ev, n, out):
    """YouTube chapters from the OCR'd text (Tome of the Dead's own lines, src/strings.txt):
    depth = the HUD field at the end of row 21 ("D<n>", new maximum that holds >= 5 s; D0 = the tutorial);
    boss fight = the first log line naming the boss whose "YOU KILL <name>" precedes "A GATE GLEAMS, THE WAY DOWN";
    D8: first ARCHMAGE log line, "THE TOME SHUDDERS", "THE TOME IS DESTROYED" (= the win)."""
    depth_at = []                                        # (frame, depth) readings of the HUD field
    for fr, r, t in ev:
        m = re.search(r"(?<![A-Z0-9])D([0-8])$", t) if r == 21 else None
        if m:
            depth_at.append((fr, int(m.group(1))))
    marks, cur, best = [(0, "Title and main menu")], {}, -1
    for i, (fr, d) in enumerate(depth_at):
        nxt = next((f for f, d2 in depth_at[i + 1:] if d2 != d), n)
        if d > best and nxt - fr >= 250:
            best = d
            cur[d] = fr
            marks.append((max(fr, 500), "Tutorial with Brother Morrow") if d == 0 else (fr, f"Depth {d}"))

    def depth_of(fr):
        return max([d for d, f in cur.items() if f <= fr], default=0)
    log = [(fr, t.split("  ")[0].strip()) for fr, r, t in ev if r in (22, 23)]
    done = set()
    for i, (fr, t) in enumerate(log):                     # the boss dies: "BOSS DROPS <item>" (+ "YOU KILL <boss>")
        d = depth_of(fr)
        if t.startswith("BOSS DROPS ") and 1 <= d <= 7 and d not in done:
            kill = [(abs(f - fr), x[9:].split(" -")[0].strip()) for f, x in log
                    if x.startswith("YOU KILL ") and -50 * 30 < f - fr < 50 * 5]
            if kill:
                done.add(d)
                name, start = min(kill)[1], fr
                for f, x in reversed(log[:i]):             # back through the fight: the boss named, gaps <= 20 s
                    if f < cur[d] or start - f > 50 * 20:
                        break
                    if name in x:
                        start = f
                marks.append((start, f"Depth {d} boss fight"))
    for key, title in (("ARCHMAGE", "The Archmage"), ("THE TOME SHUDDERS", "The Tome")):
        f = next((f for f, x in log if key in x and depth_of(f) == 8), None)
        if f is not None:
            marks.append((f, title))
    win = [f for f, r, t in ev if r not in (22, 23) and ("TOME IS DESTROYED" in t or "YOU WIN" in t) and depth_of(f) == 8]
    win = win or [f for f, x in log if "THE TOME IS DESTROYED" in x and depth_of(f) == 8]
    if win:
        marks.append((win[0], "Victory: the win screen"))
    rows, prev = [], None
    for fr, title in sorted(marks):
        t = fr // 50
        if prev is not None and t - prev < 10:              # YouTube: >= 10 s apart (the earlier mark wins)
            continue
        stamp = f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if n >= 3600 * 50 else f"{t // 60}:{t % 60:02d}"
        rows.append(f"{stamp} {title}")
        prev = t
    Path(out).write_text("\n".join(rows) + "\n")
    return rows


def _movavg(a, k=2000):
    c = np.concatenate([[0.0], np.cumsum(np.concatenate([np.zeros(k), a.astype(np.float64), np.zeros(k)]))])
    i = np.arange(len(a)) + k
    return ((c[i + k // 2] - c[i - k // 2]) / k).astype(np.float32)


def video(path, outdir, border=True, scale=None, canvas=(1920, 1080)):
    """border: the whole 320x240 Fuse canvas (border colours per line/cell as recorded) x4 = 1280x960;
    else the 256x192 paper x5 = 1280x960.  Both centred on a black 1920x1080."""
    from PIL import Image
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    W, H = (320, 240) if border else (256, 192)
    scale = scale or (4 if border else 5)
    n, snd, info, ev = scan(path)
    ratio = av_report(n, snd, info)
    if abs(ratio - 1) > 0.02:
        sys.exit(f"A/V CHECK FAILED: sound/frames ratio {ratio:.4f}")
    (outdir / "events.txt").write_text("".join(f"{fr / 50:8.2f} r{r:02d} {t}\n" for fr, r, t in ev))
    rows = chapters(ev, n, outdir / "chapters.txt")
    print(f"{len(rows)} chapters -> {outdir / 'chapters.txt'}")
    ch = info.get("ch", 1)
    a = snd.astype(np.float32).reshape(-1, ch).mean(1)
    a -= _movavg(a)
    a *= 0.89 / max(1.0, float(np.abs(a).max()))
    wav = outdir / "audio.s16"
    (np.clip(a, -1, 1) * 32000).astype("<i2").tofile(wav)
    # the machine runs at 50.02 Hz: declare the sound's real rate against a 50.000 fps picture so both end together
    sr = max(1, round(len(a) / (n / 50)))
    out = outdir / "mage_walkthrough.mp4"
    vf = (f"scale={W * scale}:{H * scale}:flags=neighbor,"
          f"pad={canvas[0]}:{canvas[1]}:{(canvas[0] - W * scale) // 2}:{(canvas[1] - H * scale) // 2}:black,format=yuv420p")
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", "50", "-i", "-",
           "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", str(wav),
           "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-profile:v", "high", "-level", "4.2", "-crf", "16", "-r", "50",
           "-af", "aresample=48000", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    shots = {"start": min(n - 1, 50 * 30), "mid": n // 2, "win": max(0, n - 50 * 8)}   # this run: win screen 2019.5-2023 s, then the menu
    k, last, buf, fx, last_bc = 0, None, b"", [], 0
    for bm, at, _s, _i in frames(path):
        pb, pa = (bm, at) if border else paper(bm, at)
        bc = int(at[0, 0] >> 3 & 7) if border else 0      # border colour (bitmap 0, paper = colour) at the top-left cell
        if bc and bc != last_bc:
            fx.append(f"{k / 50:9.2f} {k} border {bc}")
        last_bc = bc
        key = pb.tobytes() + pa.tobytes()
        if key != last:
            last, rgb = key, to_rgb(pb, pa)
            buf = rgb.tobytes()
        pr.stdin.write(buf)
        for nm, at_f in shots.items():
            if k == at_f:
                img = Image.fromarray(np.frombuffer(buf, np.uint8).reshape(H, W, 3))
                img.resize((W * scale, H * scale), Image.NEAREST).save(outdir / f"{nm}.png")
                if nm == "mid":
                    th = Image.new("RGB", (1280, 720))
                    tw, thh = (W * 3, H * 3) if border else (768, 576)          # x3: 960x720 / 768x576
                    th.paste(img.resize((tw, thh), Image.NEAREST), ((1280 - tw) // 2, (720 - thh) // 2))
                    th.save(outdir / "thumb_1280x720.png")
        k += 1
    pr.stdin.close()
    (outdir / "border_fx.txt").write_text("\n".join(fx) + "\n")
    if pr.wait():
        sys.exit("ffmpeg failed")
    probe = subprocess.run([FFMPEG.replace("ffmpeg", "ffprobe"), "-v", "error", "-show_entries",
                            "stream=codec_type,duration,nb_frames,r_frame_rate,profile,level,width,height",
                            "-of", "compact", str(out)], capture_output=True, text=True).stdout
    print(probe.strip())
    print(f"{out}: expected {n / 50:.2f} s, {out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "info":
        n, snd, info, ev = scan(a[1], verbose="--text" in a)
        av_report(n, snd, info)
        print("\n".join(chapters(ev, n, "/dev/null") if "--chapters" in a else []))
    elif len(a) >= 4 and a[0] == "chapters":             # re-derive chapters.txt from a video run's events.txt
        evs = [(round(float(ln[:8]) * 50), int(ln[10:12]), ln[13:].rstrip("\n")) for ln in open(a[1])]
        print("\n".join(chapters(evs, int(a[2]), a[3])))
    elif len(a) >= 3 and a[0] == "video":
        video(a[1], a[2], border="--no-border" not in a)
    else:
        sys.exit(__doc__)
