# FINAL-1 rename map: wazhack -> Tome of the Dead

Old names appear only in this file and `docs/rename-user-steps.md` (both exempt by path in
`tests/rename_gate.py`). Run on every build (`tools/build.sh`) and standalone:
`python3 tests/rename_gate.py`.

| Class | Old | New |
|---|---|---|
| Display name / prose / headers (917 grid + tool + doc headers `# WazHack/ZX ...`) | `WazHack/ZX` | `Tome of the Dead` |
| On-screen title (menu glyphs, loading screen, HOW TO PLAY) | already `TOME OF THE DEAD` (graphic glyphs, no source string) | unchanged |
| Design-doc menu mock / history | `WAZHACK` | `TOME OF THE DEAD` |
| Build artefacts | `build/wazhack.{tap,sna,sym,lst,sld}` | `build/tome-of-the-dead.{tap,sna,sym,lst,sld}` |
| Tape header names (BASIC + 2 CODE blocks; 10-char limit; loader uses `LOAD ""`, no name match) | `wazhack` | `tomedead` |
| Tracked files (git mv) | `assets/gfx/source/wazhack_sprites.dc.html`, `wazhack_mock_256x192.png` | `assets/gfx/source/tome-of-the-dead_sprites.dc.html`, `tome-of-the-dead_mock_256x192.png` |
| Design canvas / artifact title | `WazHack Spectrum Sprites` | `Tome of the Dead Spectrum Sprites` (the claude.ai canvas itself is renamed by the user/manager) |
| Consumers | tests/*.py, tools/*.py, tools/build.sh, src/main.asm (SAVETAP/SAVESNA), `.claude/skills/{build,run,debug,test}`, `.claude/agents`, `.claude/settings.json` | follow the artefact names |
| Env / identifiers | `WZ_BUILD_DIR`, `ZRCP_PORT` (not the project name) | unchanged |
| Repo / paths | `alstepan/wazhack`, `~/sources/zxspectrum/wazhack` | `alstepan/tome-of-the-dead`, `~/sources/zxspectrum/tome-of-the-dead` (user performs the move: `docs/rename-user-steps.md`) |
| Credit (the only allowed mention) | "inspired by WazHack", "WazHack-like/-style/feel" | the phrase `WazHack-inspired`; other historic prose reworded ("the original game's") |
| Dropped | README `[WazHack]: https://www.wazhack.com/` link | removed (gate forbids the name outside the credit phrase) |

Effects: the game image is byte-identical (names live only in the tape headers' padded 10-byte
field and comments); no ledger/floor change; goldens (screen hashes) unchanged.
