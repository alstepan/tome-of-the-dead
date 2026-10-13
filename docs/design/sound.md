# Sound — assessment and plan (sound-composer, rev 2, 2026-10-13)

> Status: **planning pass only** (user request 2026-10-13). Nothing here is approved.
> No player code or final data exists. **Primary material (rev 2):**
> `assets/sfx/concepts/6-melodies.abc` and
> `assets/sfx/concepts/tome_of_the_dead_f_minor_staccato_theme.abc` (= Catacomb Lament).
> The nine older single-tune ABCs are secondary (§1.4).
> Fixed points: the A8 slot (`AY_PLAY` = `AY_RESERVE` `$F000`, bank 3, 4 KB, silent stub,
> `src/ay.asm`) and the ISR contract (`docs/conventions.md` "Interrupts").
> **E** = estimate, **M** = measured. Every E must be measured before it is used as a budget.

## 0. Facts this plan rests on

| Item | Value | Source |
|---|---|---|
| AY clock (128K/+2/+2A) | 1.7734 MHz. Tone f = clk/(16·TP), TP 12 bit (lowest ≈ 27 Hz). Buzzer: saw f = clk/(256·EP), triangle clk/(512·EP) | hardware |
| Pentagon clock 1.75 MHz | ≈ 23 cents flat with our tables. Accepted, no second table | hardware |
| Writing R13 | **restarts** the envelope, so write it only when the shape changes | hardware |
| Envelope / noise generators | **one each, shared**. At most one buzzer voice at a time; one noise period (R6) | hardware |
| ISR | IM 2, runs at frame start in the top border. Overhead 334 T **M**, silent stub 286 T **M**. The tick probes (`get-tstates-partial`) already include both | conventions, lowram.asm |
| Tick caps | ordinary 126k, cast 128k, hard 141,816 (2 frames). Worst measured: ordinary 120.0k, cast 126.0k ("advcast") **M** | memory-map.md |
| AY share | (141.8k − 128k) ≈ 13.8k per tick ≈ **6.5k T a frame** | budget.md §5 |
| Contention | Bank 3 is contended on 128K/+2, but the ISR runs before the first contended line (~14.3k T), so a player under ~14k T runs **uncontended**. budget.md §5's "+10%" is pessimistic | hardware |
| Bank 3 outside the slot | **235 B free** **M**, so the slot cannot grow without moving cold code | memory-map.md |
| Bank 2 | ~48 B free. The `MUS_REQ` / `SFX_REQ` mailbox (3–4 B) must live here or in low RAM, because main code does not have bank 3 paged | memory-map.md |

## 1. Assessment of the primary material

Analysed with a throwaway ABC parser (bar sums, ranges, events, byte estimate). Everything
is in **F minor**, 4/4, `L:1/8`, and the **shortest note is an eighth** in every tune.
At 50 Hz an eighth lasts 1500/Q frames.

### 1.1 Voices: V1 and V2 are two separate monophonic voices

`%%score (V1 V2) V3` only brackets V1 and V2 onto one grand-staff group for display. Each
`V:` is its own line, and neither file contains a chord (`[...]`). So there are 3
monophonic voices → AY channels A/B/C one-to-one, with no chord splitting.

- **V1 ("Alto")** and **V2 ("Soprano")** are both high and cross each other.
- **V3 ("Basso")** sits in the tenor range (44–72). Transposing everything **down an octave** puts V3 in the buzzer-bass sweet spot (33–53), takes the leads off the shrill top of the AY (TP ≈ 53 at C7), and costs 0 B: it is a converter option.

### 1.2 `6-melodies.abc`: "Tome of the Dead" suite, X:1–6

**The file is damaged.** Several header/voice lines are spliced together with text missing.
It looks like a copy/paste loss, not a CR/LF problem: there is no `\r`, and the bytes really
are gone.

| Tune | Damage |
|---|---|
| X:1 | the `X:1` line is missing. V2: the `V:V2` header plus the first note and a half of bar 1 are lost (the bar sums to 1/2) |
| X:2 | V1: the `V:V1` header plus the first 6/8 of bar 1 are lost |
| X:4 | `C:` and `M:` merged, so `M:4/4` is lost (harmless: defaults to 4/4) |
| X:5 | V3: the `V:V3` header plus the first 6/8 of bar 1 are lost |
| X:6 | `T:` and `C:` merged. The surviving title fragment confirms **X:6 = "Game Over (Lament of the Fallen)"** |

**→ Re-export needed for X:1, X:2 and X:5** (the missing notes cannot be guessed reliably).
Figures below use the intact bars.

| X | Title | Q → whole-frame eighth | Bars · length | Ranges V1 / V2 / V3 | Events | Bytes **E** | Loop | Event |
|---|---|---|---|---|---|---|---|---|
| 1 | Dungeon Crawl (Walking) | 72: 20.8 → **21** (71.4 BPM) | 4 · 13.3 s | 72–85 / 79–89 / 49–60 | 20/16+/16 | **~85** | bar 4 → 1 (F → F, clean) | **Explore / walk** |
| 2 | Dangerous (Creeping Dread) | 68: 22.1 → **22** (68.2) | 2 · 7.1 s | 76–80 / 76–85 / 46–53 | 5+/8/12 | **~45** | bar 2 → 1 (ends on C = V, pulls back: good) | **Danger** |
| 3 | Boss Fight (Lich Lord) | 106: 14.2 → **14** (107.1) | 4 · 9.1 s | 72–85 / 79–94 / 44–65 | 30/30/30 | **~110** | bar 4 → 1 | **Boss** |
| 4 | Level Complete (Crypt Cleared) | 78: 19.2 → **19** (78.9) | 2 · 6.2 s | 76–85 / 84–94 / 53–65 | 11/11/7 | **~57** | one-shot | **Level complete / descent** stinger |
| 5 | Game Win (Triumph of the Relic) | 84: 17.9 → **18** (83.3) | 2 · 5.7 s | 72–85 / 76–89 / 53–61 | 10/10/5+ | **~50** | one-shot (or loop on the win screen) | **Win** |
| 6 | Game Over (Lament of the Fallen) | 66: 22.7 → **23** (65.2) | 2 · 7.3 s | 65–84 / 76–89 / 53–65 | 8/8/8 | **~41** | one-shot | **Game over** |

The six total **~0.39 KB E** (~0.45 KB with instrument and loop commands).

Musical notes:
- A coherent family: same key, same "Tome of the Dead" titling. Same-key cuts at bar boundaries will sound seamless.
- **They are motifs, not loops.** Crawl (13 s), Danger (7 s) and Boss (9 s) will grate in a long run. Stingers 4–6 are fine at their length.
- V2 sits above V1 almost throughout, as parallel 4ths and 5ths over V1 (organum-like). It sounds hollow on 3 square waves, but that suits the "dead" theme.

### 1.3 Catacomb Lament (`tome_of_the_dead_f_minor_staccato_theme.abc`)

Title: "Tome of the Dead - IIb. Catacomb Lament (Staccato Theme) (F minor)". 96 BPM, 32 bars
in 8 four-bar blocks. The file is intact. Every bar sums correctly in all three voices.

| Item | Value |
|---|---|
| Length | 32 bars = **80.0 s** at 96. At a 16-frame eighth: 4,096 frames = 81.9 s, a good long loop |
| Ranges | V1 68–89 · V2 73–96 (**C7, top of what is usable**) · V3 48–72 |
| Events | 180 / 184 / 192. Unique bars 27, 29, 27 of 32 (through-composed, little to dedupe) |
| Staccato | `.` on 185 notes. Staccato and legato alternate per 4-bar block and pass between the voices: a built-in texture change, ~2 B a switch → ~50 B |
| Bytes **E** | ~860 raw → **~0.85 KB** with the staccato switches and dedupe |
| Loop | bar 32 (`_a f c' f _a4` over F) → bar 1 (F minor): clean |
| **Accidental bug** | The file writes an explicit `_` on every Ab/Bb/Db/Eb (228 times) although `K:Fm` already flattens them. So the generator ignored the key signature. That means its **bare `e`/`d` (29 notes: V1 12, V2 17, V3 1) are meant as E♮/D♮**, but strict ABC reads them as **E♭/D♭**. The context confirms naturals: V1 bar 30 `_B g _B2 e2 c'2` is C7, and V3 bar 31 `C G, C2 C E G2` is a C-major cadence into F. **Fix:** spell them `=e` / `=d` in the source. The converter will also render both readings to WAV so the user can confirm by ear (§5) |

**Max-tempo staccato.** The shortest note is an eighth.

| Frames per eighth | BPM | Staccato gate (on / off frames) | Verdict |
|---|---|---|---|
| 16 | 93.75 | 8 / 8 | nearest to the written 96 |
| 15 | 100 | 8 / 7 | alternative to 16 |
| 15.6 (8.8 accumulator) | 96 exact | 15/16 alternation | 1-frame (20 ms) jitter on staccato. Avoid |
| 12 | 125 | 6 / 6 | brisk |
| 10 | 150 | 5 / 5 | fast, harpsichord decay still readable |
| **8** | **187.5** | 4 / 4 | **double time**: the practical "max tempo" theme |
| 6 | 250 | 3 / 3 | ceiling. Decay squeezed to 15-11-8, chiptune tick |
| 4 | 375 | 2 / 2 | clicks, not notes. Too fast |

Preview candidates: **16, 12, 8, 6**.

### 1.4 Secondary material (the nine older ABCs, 2026-10-09)

Optional extras only. All are in D minor, so they do not crossfade with the F-minor suite
without a transposition (free in the converter).

- **`dungeon-fugue.abc` stays REJECTED.** Its header says it arranges *Il Vento d'Oro* (Yugo Kanno, 2018), a copyrighted work. It also has two wrong-length lead bars (13 and 25).
- Useful spares if loops need variety: the-forgotten-catacombs (explore, ~120 B), shadows-in-the-keep (danger, ~120 B), level-boss-dungeon-overlord (boss, ~160 B).

### 1.5 Provenance (as written in the files; no new questions)

- Both files: `C:ZX Spectrum 128K AY-3-8912 Chiptune` is a target description, not a composer credit. No copyright or licence line.
- The Lament is numbered "IIb", which implies a larger "Tome of the Dead" suite. Its flowmusic.app origin and terms are still open from rev 1.

## 2. Format and player

| | PT3 (Vortex Tracker II) | Arkos Tracker 2/3 (AKM) | **Custom "WZM"** (recommended) |
|---|---|---|---|
| Player bytes | 1.6–2.0 KB + ~200 vars | smaller than PT3: **verify** | **0.8–1.0 KB E** incl. SFX overlay and period table |
| T per frame | 3–6k, worst ~8k (over the 6.5k contract) | verify | **~1.5k typical, ≤ 2.5k worst E** |
| Song data | ~1.5–3 KB per in-game loop | compact | ~1.2–1.5 B per note (§1 tables) |
| Authoring | GUI. Agents cannot drive it | native macOS GUI with MIDI import. Agents cannot drive it | ABC text, fully agentic, diffable |
| Proto B in 4 KB? | no | probably | **yes** (§3) |

**Recommendation: custom WZM.** Fallback: Arkos AKM, if the user wants to compose in a GUI.

**WZM sketch** (to be agreed with z80-staff-engineer):
- **Song header:** tempo (8.8 frames per row; integer for these tunes), 3 stream pointers, loop pointers, a 4-B instrument map, a buzzer channel and a steal channel.
- **Streams:** `$00–$5F` = note. `$60` = rest. `$61–$7F` = commands (duration, instrument, staccato gate on/off, glide, buzzer, transpose, call/return pattern, loop, end). `$80+n` = sticky duration.
- **Instruments:** ~10–20 B each — volume table with sustain/release index, arpeggio table, vibrato, and a noise mask.
- **Output:** a 14-register shadow, ~700 T a frame. R13 is written only when it changes.
- **Cost E:** ~1.5k typical, ≤ 2.5k worst → **+4.4k T a tick worst**. Ordinary 120.0k → ~124.4k (cap 126k). "advcast" 126.0k → ~130.4k: **over the 128k cast cap**, still under the 141.8k hard limit. Re-derive the caps from the measured player.
- **Driven from the ISR, not the main loop:** tempo stays steady when a tick runs to 3 frames.

### Balance finding from the web-audio concept player (user ear check, 2026-10-13)

User: "legato is shy while staccato is loud". Cause in `assets/sfx/concepts/player-js/main.tsx` (l.1197–1214):
both articulations sit at the same AY level (13; bass 14) but legato notes **glide** (`setTargetAtTime` on frequency,
no re-trigger, no attack) while a staccato note is cut at 45 % of its length — so the plucked voice gets an audible
onset on every note and the legato voice has none. Loudness is perceived at the attack, not at the sustain level.
**Rules for the real player:** (1) balance by *peak vs sustain*, not by one shared level: pluck peak ≈ 12–13 decaying
fast, legato/organ sustain 13–14 with its own 2–3-frame attack ramp (9,11,13); (2) every legato note boundary still
re-triggers the volume table (a 1-frame dip to ~−2 steps, no envelope restart) so repeated pitches are heard;
(3) never gate legato below 100 % of its row; (4) staccato blocks pass between voices, so the mix must hold with the
pluck on V1 *and* on V3 — tune by ear in `ay_render.py --compare` with the staccato/legato level offset as a CLI knob
(`--stac-offset`, default −1). The AY log table (3 dB/step) means 1 step ≈ 1.4× amplitude: a 1-step shift is audible.

### Timbres (instrument tables, ~25–40 B each)

| Timbre | Volume table (per frame) | Arp / pitch | Other |
|---|---|---|---|
| **Harpsichord** | 15,13,12,11,10,9,9,8,8,7,7,6,6,5,5,4,4,3… (≈1 s to 3); staccato gate → release to 0 in 1 frame | frame 1 = +12 (pluck transient), then 0 | optional 1 frame of low noise ("quill"). No vibrato |
| **Church organ** | 9,11,13, then hold 13; release 13,9,5,0 | none (or a 50 Hz root/oct/5th "mixture", test by ear) | tremulant ±1 volume at an 8-frame cycle (~6 Hz). Pedal: triangle buzzer (shape `$0E`) on V3 only. Staccato under the organ = 75% gate, not 50% |
| **Staccato gate** | the note sounds for ⌈rows × gate⌉ frames, then the release index | — | per-note `.` → gate 50%, legato → 100% |

## 3. Prototypes (recomputed)

### A: Catacomb Lament, harpsichord and organ

- Same note data. A variant = 4-B instrument map + its tables (~40–80 B).
- Organ variant: triangle buzzer pedal on V3, transposed −12.
- Harpsichord variant: tone only, with a free choice of steal channel.
- Tempo variants (16 / 12 / 8 frames) are one header byte each.

| Item | Bytes **E** |
|---|---|
| player | 0.9 KB |
| Lament | 0.85 KB |
| 2 instrument sets | 0.1 KB |
| SFX bank | 0.8 KB |
| **Total** | **~2.65 KB of 4 KB (1.35 KB spare)** |

### B: the six tunes switched by game events

| State | Tune | Enter | Leave | Transition |
|---|---|---|---|---|
| EXPLORE | X:1 Dungeon Crawl. Or the **Lament** as the long explore loop, with X:1 for title/menu | level start | — | fade 12 frames, start at bar 1 |
| DANGER | X:2 Dangerous | awake hostile in the room | room clear 2 turns (hysteresis) | **next bar** (same key → seamless) |
| BOSS | X:3 Boss Fight | boss room entry | boss dead → X:4 | fade 8 frames + cut |
| STINGER | X:4 Level Complete | descent / boss dead | end → **resume** explore (~20 B snapshot) | immediate |
| WIN / GAME OVER | X:5 / X:6 | event | menu | immediate cut. Override everything |

- **Priority:** WIN = GAMEOVER > BOSS > STINGER > DANGER > EXPLORE.
- **Interface:** main code writes 1 B to `MUS_REQ` (no `DI` needed); the ISR switches at the bar line. Fades are an output-stage attenuation (~30 T).

| Item | Bytes **E** |
|---|---|
| player + state machine + fades | 1.05 KB |
| X:1–6 as written | 0.45 KB |
| **Lament** as explore (optional) | 0.85 KB |
| SFX | 0.8 KB |
| **Total with the Lament** | **~3.15 KB** (0.85 KB spare) |
| **Total without the Lament** | **~2.3 KB** |

**B now fits in 4 KB.** The spare can extend Crawl, Danger and Boss from 2–4 bars to 8 bars
(~20–27 B a bar → ~+0.4 KB), which brings B with the Lament to ~3.55 KB. Going to 16 bars
each (~+1.0 KB) would not fit with the Lament: then use transposed pattern calls (3 B per
repeat) or drop the Lament from B. None of the rev-1 ways out (ZX0 songs, a bigger slot,
pool slack) are needed.

## 4. SFX

Rules:
- **No beeper in game**: it busy-waits the CPU.
- **Steal channel:** V1 (alto, the inner voice). Never V2 (the top line) and never the buzzer V3. The music keeps sequencing the stolen channel, and the current note is restored when the effect ends.
- **Priority 0–7:** a new effect replaces the current one if its priority is ≥.
- SFX never touch R11–R13 and own R6 while they play.
- Ducking −2 volume steps for priority ≥ 6.
- Mailbox `SFX_REQ` in bank 2. A call site is `ld a,n : call sfx_req` (5 B), and the routine keeps the higher-priority request. **Bank-3 call sites eat into its 235 B.**
- Format: AYFX-like, 1–3 B a frame.

| SFX | Frames | Bytes **E** | Prio | Hook |
|---|---|---|---|---|
| melee swing / hit / miss | 5 / 6 / 4 | 12 / 18 / 10 | 2 / 4 / 2 | 3D |
| kill / hero hurt (ducks) | 12 / 8 | 32 / 22 | 6 / 7 | 3D |
| Power Strike / Whirlwind | 10 / 20 | 28 / 45 | 5 | 3D |
| Spark / Firebolt (+ burst) / Frost Shard / Lightning / Drain Life | 8 / 14+8 / 14 / 12 / 16 | 20 / 60 / 32 / 28 / 34 | 4–5 | 3D |
| fizz (no MP) / projectile bounce / throw | 5 / 3 / 4 | 12 / 8 / 10 | 2–3 | 3D |
| status apply (one SFX, pitch per status) | 10 | 28 + 5 | 4 | 3D |
| step (default off) / ladder / jump / land / fall | 2 / 2 / 6 / 3 / 20 | 6 / 6 / 14 / 8 / 40 | 1–5 | 3C, J1 |
| door / gate raise | 12 / 24 | 30 / 55 | 4 / 5 | 3B |
| pickup / gold / potion / eat | 6 / 8 / 10 / 6 | 14 / 18 / 24 / 14 | 3 | 3E |
| trap | 8 | 20 | 6 | 3E |
| level-up (or X:4 as a stinger instead → 0 B) | 24 | 50 | 6 | 3D |
| boss roar / boss death | 30 / 40 | 60 / 70 | 6 / 7 | 3F |
| menu move / select / cancel | 1 / 4 / 4 | 3 / 10 / 10 | 1 | 3C |

About **30 SFX ≈ 0.8 KB E**.

## 5. Tools: first-pass plan (no code yet; owner z80-junior, spec from sound-composer)

| # | Tool | Input → output | Must do | Notes |
|---|---|---|---|---|
| T1 | `tools/abc2wzm.py` | ABC (multi-tune `X:` files, `%%score`, `V:`) → `assets/sfx/music/<name>.asm` (sjasmplus `DEFB`, labels, `ASSERT` size) + a size report | parse the subset actually used: headers, `K:` major/minor key signatures, `_ ^ =`, octaves `, '`, lengths `n` `/n`, rests, `.` staccato, slurs as legato, `\|` `\|]` | **Checks:** each bar sums to `M:`; ≤ 3 monophonic voices; AY range after transposing; integer frames per row (or an explicit 8.8); ≤ 1 buzzer voice. **`--accidentals strict\|explicit`** (the Lament bug, §1.3), `--transpose`, `--frames-per-eighth`. Directives as `%%wzm instr=… loop=… steal=…` comments, so the ABC stays valid |
| T2 | `tools/wzm_ref.py` | WZM bytes → per-frame 14-register stream (+ `.psg` export) | **logic identical** to the Z80 player: same tables, same rounding | the oracle for T4 |
| T3 | `tools/ay_render.py` | register stream → 44.1 kHz WAV (numpy) → `afplay` | 3 tone counters, 17-bit LFSR noise, 16 envelope shapes with R13 restart, AY log volume table, simple mix and DC block | `--compare` renders both accidental readings or both timbres back to back for A/B listening |
| T4 | `tests/` assertion "golden register stream" | run the real player in ZEsarUX for N frames over ZRCP; read the player's 14-B register shadow each frame; diff against T2 | wire into the `test` skill like the golden screens | **Unknown:** a ZRCP AY-register command. Fallback: the shadow in memory |
| T5 | intent preview (optional) | ABC → `abc2midi` (installed) → `fluidsynth` (installed) → WAV of a "real" harpsichord (GM 7) and organ (GM 20) | — | needs a GM soundfont (none installed) |
| T6 | MIDI input (optional) | SMF → the same internal note list as T1 | quantise to eighths | a minimal SMF reader, or `mido` in a venv (not installed) |

Order: T1 + T2 + T3 first (to listen before any Z80 exists), then T4 together with the
player (S1).

## 6. Schedule

| Step | When | Who | Dependencies | Tick risk |
|---|---|---|---|---|
| **S0** T1–T3; Lament harpsichord vs organ and tempo 16/12/8/6 rendered to WAV for the user | **now, parallel to 3E** (owns only `tools/`, `assets/sfx/`) | junior + composer | WZM spec agreed with staff; fixed `6-melodies.abc` | none |
| **S1** player core (music only) = proto A, measure T, re-derive caps, T4 | **start of 3E**, so 3E/3F are budgeted against the real cost | z80-staff-engineer | S0; `src/ay.asm`, `MUS_REQ` in bank 2 | +~4k T a tick worst **E**; "advcast" cap re-check |
| **S2** SFX overlay + 3B/3C/3D hooks | during 3E | staff (overlay), junior (hooks outside bank 3) | S1 | +~0.3k T a frame |
| **S3** 3E hooks (pickup, potion, trap) | with 3E items | junior | S2 | none |
| **S4** proto B state machine (X:1–6) | 3F (boss, win and death exist) | staff + composer | S1; designer DANGER trigger | fades ~30 T |
| **S5** loop extensions, mix pass | 3G | composer, user in Fuse | all | none |

This moves part of plan.md's "3G Sound" earlier. That is a manager/user decision.

## 7. Open questions

1. **Re-export `6-melodies.abc`**: X:1 V2 bar 1, X:2 V1 bar 1 and X:5 V3 bar 1 are truncated; the X:1, X:4 and X:6 headers are damaged.
2. **Lament accidentals**: are the 29 bare `e`/`d` E♮/D♮ (my reading) or E♭/D♭? To be confirmed by ear with the T3 A/B render, then fixed in the source.
3. Transpose the suite down an octave (recommended) or keep it as written?
4. B's EXPLORE: X:1 Dungeon Crawl, or the Lament (X:1 then becomes the title/menu tune)?
5. How long should the Crawl/Danger/Boss loops be (8 bars fits; 16 bars only without the Lament or with pattern reuse), and who writes the extensions (user tool vs composer)?
6. Still open from rev 1: flowmusic.app terms; the player's real bytes and T; the DANGER trigger (game-designer); level-up as stinger or SFX; the ZRCP AY-register command and ZEsarUX audio-to-file; a GM soundfont for T5.
