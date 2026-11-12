# Browser play on itch.io (WEB1)

Bundle = JSSpeccy 3 v3.2 (GPL-3, unmodified) + the **released** tape of a tag.
Nothing is committed; `build/` is gitignored.

## Build

    tools/web_bundle.sh [tag]        # default v1.1; needs gh + network once, then cached in build/web-dl/

Pinned inputs: JSSpeccy `jsspeccy-3.2.zip` (sha256 in the script) and our release
files (verified against the release `SHA256SUMS`). Output
`build/web/tome-of-the-dead-web-<tag>.zip` (deterministic, ~220 KB) and the
unzipped `build/web/site/`. `index.html` is at the zip root; 128K machine, the
`.tap` autoloads through the 128 ROM loader (so `check_paging` runs). Set
`GAME_EXT=sna` only as a fallback. No external requests at runtime (`sandbox:true`
removes Open / Find-games, the latter calls archive.org). The zip carries
`LICENSE`, `LICENSE-ASSETS.md`, `THIRD-PARTY.md` (repo copies, with the JSSpeccy
entry), `JSSPECCY-LICENSE-GPL3.txt` and `SOURCE.txt` (source link).

## Local test

    cd build/web/site && python3 -m http.server 8765 --bind 127.0.0.1    # open http://127.0.0.1:8765/ in Chrome

Click the screen (focuses the emulator), press play; audio starts only after that click.

## Upload to itch

1. Project page -> Kind of project: **HTML**.
2. Upload `tome-of-the-dead-web-v1.1.zip`, tick **This file will be played in the browser**.
3. Embed options: viewport **660 x 600** px (emulator is zoom 2 = 640 x 480 incl. toolbar-free
   border, toolbar above it, hint text below); enable the **Fullscreen button**;
   leave mobile-friendly off (keyboard-only, see below). Optionally tick "Click to launch in fullscreen".
4. Keep the .tap/.sna as separate downloadable files if wanted.

## Spike findings (from JSSpeccy 3.2 docs and source; not yet verified in Chrome)

- **128K / $7FFD / loader:** `machine:128`, full 128K paging emulated; `autoLoadTapes` loads
  the .tap with the 128 ROM Tape Loader snapshot (`tapeloaders/tape_128.szx`) and ROM trap
  (instant load). `tapeAutoLoadMode:'usr0'` is the alternative if the menu path misbehaves.
  Still to confirm in Chrome: it boots past `check_paging`.
- **AY:** supported (AY + beeper), as is the 128 mix; needs a click before audio starts.
- **Timing:** Wasm core is cycle-accurate per scanline (128K frame 70908 T, contention
  modelled). The 0 T ISR margin on SFX10c/SND6 depends on it matching ZEsarUX; play-test
  the SFX/music paths. Throttling uses requestAnimationFrame (50 Hz via audio sync); a 60 Hz
  display may judder but the emulated T count is unaffected.
- **Screen bank 5/7 shadow:** standard 128K bit 3 of $7FFD; the video builder reads the
  selected bank per scanline. Expected fine; confirm visually (no tearing/flicker on swap).
- **Kempston:** not found in 3.2 (keyboard only; cursor keys map to CAPS+5..8). The game's
  default keys Q/A/O/P/SPACE work. No joystick selection needed.
- **Mobile:** no touch controls in JSSpeccy 3 (no touch handlers found); needs a physical
  keyboard. Page says so. A zxplay-style touch UI would be a separate task.
- **Iframe focus:** key events go to JSSpeccy's own focusable container; the page focuses it on
  click. It calls preventDefault on keys, so arrows/space do not scroll the itch page.
