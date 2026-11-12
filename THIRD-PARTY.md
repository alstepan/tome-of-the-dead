# Third-party components

Only the ZX0 decompressor is part of the game itself; its BSD 3-Clause notice
below must travel with every copy of the tape or snapshot. The other entries
are credited for transparency; their licences put no conditions on the game.

## Included in the game (tape and snapshot)

**ZX0 decompressor** (`src/dzx0_standard.asm`, unmodified), by Einar Saukas and
Urusergi, https://github.com/einar-saukas/ZX0 (licence:
https://github.com/einar-saukas/ZX0/blob/main/LICENSE). BSD 3-Clause License,
reproduced as its condition 2 requires:

    Copyright (c) 2021, Einar Saukas
    All rights reserved.

    Redistribution and use in source and binary forms, with or without
    modification, are permitted provided that the following conditions are met:

    1. Redistributions of source code must retain the above copyright notice,
       this list of conditions and the following disclaimer.
    2. Redistributions in binary form must reproduce the above copyright notice,
       this list of conditions and the following disclaimer in the documentation
       and/or other materials provided with the distribution.
    3. Neither the name of the copyright holder nor the names of its
       contributors may be used to endorse or promote products derived from
       this software without specific prior written permission.

    THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
    AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
    IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
    ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
    LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
    CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
    SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
    INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
    CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
    ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
    POSSIBILITY OF SUCH DAMAGE.

## Included in the browser (itch.io HTML5) bundle only

- **JSSpeccy 3** (v3.2, unmodified), by Matthew Westcott, GPL-3.0
  (`JSSPECCY-LICENSE-GPL3.txt` in the bundle). Corresponding source ships in the bundle
  (`jsspeccy3-v3.2-source.tar.gz`) and is kept in this repo at `third_party/`; upstream:
  https://github.com/gasman/jsspeccy3/tree/v3.2. It embeds JSZip (MIT or GPL-3)
  and pako (MIT), and ships the 48K/128K ZX Spectrum ROMs (c) Amstrad plc /
  Sky; Amstrad permits free redistribution of these ROMs with emulators. The
  game tape itself is not affected: it is loaded as data by the emulator, and
  the bundle is built by `tools/web_bundle.sh`.

## AI tools used to make the game

- **Anthropic Claude** (https://www.anthropic.com/claude; terms:
  https://www.anthropic.com/legal/consumer-terms): the code, tools, tests, text
  and pixel art (drawn on a claude.ai Design canvas) were produced agentically
  with Claude, under the author's direction and review.
- **Google Flow Music** (https://www.flowmusic.app; terms:
  https://policies.google.com/terms): the music was generated with Flow
  Music and then arranged by hand for the AY-3-8912 (`assets/sfx/`). Flow Music
  is covered by the Google Terms of Service, linked above.

## Build, test and media tools (not included in the game)

- **sjasmplus** (Z80 assembler), https://github.com/z00m128/sjasmplus, BSD 3-Clause
  (https://github.com/z00m128/sjasmplus/blob/master/LICENSE.md).
- **ZX0 compressor** (`zx0`), same repository and licence as the decompressor
  above; fetched and built by `tools/setup_zx0.sh`, not committed.
- **NumPy** (https://numpy.org, BSD 3-Clause) and **Pillow**
  (https://python-pillow.org, MIT-CMU), Python packages used by tools and tests.
- **ZEsarUX** (https://github.com/chernandezba/zesarux, GPL-3.0) and **Fuse**
  (https://fuse-emulator.sourceforge.net, GPL-2.0) emulators, used for testing and
  for recording the screenshots and videos.
- **FFmpeg** (https://ffmpeg.org, LGPL/GPL), used to make the promotional videos and GIF.

## Inspiration and trademarks

- **WazHack** (https://www.wazhack.com/) inspired the game's design. No WazHack code, art, music or text
  is used.
- The game runs on the machine's own ROM and reads its character set at run
  time; no ROM content is copied into the game.
- ZX Spectrum and Sinclair are trademarks of their respective owners, as is
  Kempston. They are named only to describe compatible hardware; this project
  is not affiliated with or endorsed by them, nor by Anthropic or Google.
