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
| Tick caps | ordinary 126k, cast 128k as **work** caps (tick time minus the ISR time inside it), hard 141,816 (2 frames) as the **real** gate (SND-2 T5). Worst measured **with the Lament playing** (SND-2 T6): ordinary work 121.4k (mage), cast work 119.1k (wcast4), real 130.8k. "advcast" is no longer the worst: 81.7k cast / 92.0k ordinary since D3-8e (now 81.4k / 92.7k work) **M** | budget.md §5.1, memory-map.md |
| AY share | (141.8k − 128k) ≈ 13.8k per tick ≈ **6.5k T a frame** (contract). Measured: worst ISR 5.2k, worst adjacent pair 8.6k **M** | budget.md §5 / §5.1 |
| Contention | Bank 3 is contended on 128K/+2, but the ISR runs before the first contended line (~14.3k T), so a player under ~14k T runs **uncontended**. budget.md §5's "+10%" is pessimistic | hardware |
| Bank 3 outside the slot | **359 B free** **M** (SND-2 build), so the slot cannot grow without moving cold code; the slot itself has 857 B free | memory-map.md |
| Bank 2 | The mailbox lives in the bank-2 state block: `SND_MODE` `$BFEB`, `MUS_REQ` `$BFEC`, `MUS_SHOT` `$BFED`, `MUS_STATE` `$BFEE` (SND-2; `SFX_REQ` not allocated yet) | memory-map.md |

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
| **Accidental bug** | The file writes an explicit `_` on every Ab/Bb/Db/Eb (228 times) although `K:Fm` already flattens them. So the generator ignored the key signature. That means its **bare `e`/`d` (29 notes: V1 12, V2 17, V3 1) are meant as E♮/D♮**, but strict ABC reads them as **E♭/D♭**. The context confirms naturals: V1 bar 30 `_B g _B2 e2 c'2` is C7, and V3 bar 31 `C G, C2 C E G2` is a C-major cadence into F. **Fix:** spell them `=e` / `=d` in the source. The converter will also render both readings to WAV so the user can confirm by ear (§5). **S1b: by ear the user hears the naturals as "missing flats", so strict ABC (Eb/Db) is the reading (§2 S1b)** |

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
- **Cost E:** ~1.5k typical, ≤ 2.5k worst → **+4.4k T a tick worst**. Ordinary 120.0k → ~124.4k (cap 126k). "advcast" 126.0k → ~130.4k: **over the 128k cast cap**, still under the 141.8k hard limit. Re-derive the caps from the measured player. *(Done in SND-2: caps kept as work caps + a real gate; measured worst real 130.8k, budget.md §5.1.)*
- **Driven from the ISR, not the main loop:** tempo stays steady when a tick runs to 3 frames.

### Reference = the tsx player, not the ABC (user ear check, 2026-10-13)

User: the web-audio player `assets/sfx/concepts/player-js/main.tsx` **sounds right in the browser**; the ABC renders
had legato shy / staccato loud. So the tsx is the **ground truth** for notes (its `Note[]` arrays: pitch, duration,
staccato flag) and for the intended balance; the `.abc` exports are the lossy copy. (An earlier note here blamed the
tsx gain model — withdrawn.) Playback model to match in `ay_render.py` / the real player: every voice at AY level 13
(bass 14), legato = sustain at that level with a ~6 ms frequency glide, staccato = level 0 after 45 % of the note
(l.1197–1210; `AY_VOL_TABLE` l.809). Open: the tsx shows both articulations at equal level, so the ABC renders'
imbalance is likely their synth's per-note attack/velocity — keep levels equal and do not add an extra attack to legato.
**Action for T1 (`abc2wzm.py`):** cross-check parsed ABC notes against the tsx arrays (pitch, duration, staccato) and
report any disagreement; where they differ, the tsx wins and the ABC is regenerated from it (or `--source tsx`).

### Timbres (instrument tables, ~25–40 B each)

> **Superseded for the harpsichord (S1d, below):** the reference is now the user's browser
> player `main.tsx`, which holds a constant level for the whole note. The decaying
> harpsichord row below is kept as the A/B "pluck" variant only; it is audibly wrong.

| Timbre | Volume table (per frame) | Arp / pitch | Other |
|---|---|---|---|
| **Harpsichord** | 15,13,12,11,10,9,9,8,8,7,7,6,6,5,5,4,4,3… (≈1 s to 3); staccato gate → release to 0 in 1 frame | frame 1 = +12 (pluck transient), then 0 | optional 1 frame of low noise ("quill"). No vibrato |
| **Church organ** | 9,11,13, then hold 13; release 13,9,5,0 | none (or a 50 Hz root/oct/5th "mixture", test by ear) | tremulant ±1 volume at an 8-frame cycle (~6 Hz). Pedal: triangle buzzer (shape `$0E`) on V3 only. Staccato under the organ = 75% gate, not 50% |
| **Staccato gate** | the note sounds for ⌈rows × gate⌉ frames, then the release index | — | per-note `.` → gate 50%, legato → 100% |

### Measured: S1a player core (2026-10-13, **M**)

`src/music/player.asm` (WZM v0 as defined in `tools/abc2wzm.py`), run on the standalone
test tape `src/music/testtape.asm` (`tools/build_music_test.sh` → `build/music_test.tap`
/ `.sna`; not part of the game). It is checked against `tools/wzm_ref.py` by
`tests/music_player.py`: the RAM register mirror for 1,024 frames of all 13 songs (the
f6 Lament runs to 1,700 frames to cover its `$80` loop), and the AY chip registers
(ZRCP `get-io-ports` answers open question 6) for every timed frame.

| Item | Value |
|---|---|
| Player bytes | **890 B**: code 616, period table 192 (96 × DW), state 82 (mirror 14, 3 voices × 22, song pointer 2) |
| T per frame, incl. CALL/RET, uncontended (bank 2 in the test) | median **1,817**, mean **1,990** over 11,203 frames (13 songs × up to 1,024 frames) |
| by timbre | harpsichord median 1,757–1,925; organ (tremolo path) median **2,198** |
| worst | **4,869** (organ Lament, frame 512: all three voices fetch a note on the same frame with a staccato command). Harpsichord worst 4,530; short tunes 4,163 |
| one fetch (new note) | ~0.8–1.0k T: two period lookups (note and arp0 frame), envelope reset, staccato gate `(dur·gate8+7)>>3` by repeated addition |
| output stage | 9 registers a frame (R0–R5, R8–R10), unrolled, 412 T. R6/R7/R11/R12 are constant and written only by `player_start` / `pl_out_all` |

Against the estimates in the table above: typical is ~1.8k (E 1.5k) and the worst frame
is ~4.9k (E ≤ 2.5k). The worst case recurs on every beat where all three voices start
a note, so for a 2-frame tick count **~7.1k T worst** (4.9k + 2.2k), not +4.4k. That is
inside the 13k-per-tick contract (6.5k a frame), but the "advcast" re-check in §2 must
use 7.1k. In the game the player runs from bank 3 (contended), but inside the ISR in
the top border, so these figures still apply as long as the ISR finishes before the
first contended line (~14.3k T). If the cast cap gets tight, the levers are: spreading
the three fetches over the frame before the note (a look-ahead in the player), or a
cheaper staccato gate (a gate8 per instrument precomputed to a shift table).

### S1b: accuracy audit + legato, WZM v0.1 (2026-10-13, **M**)

**Accuracy audit** (`tools/abc_audit.py FILE.abc` prints a per-note table: bar.beat, token,
decoded and heard pitch, AY period, Hz, cents error, arp0 frame, frames, flags and the
alternative readings of every ambiguous token).
- Period table: worst error of any note used is **+5.8 cents** (Ab5, TP 133). The 128K
  clock (1,773,447.5 Hz) differs from the table clock (1,773,400) by 0.05 cents. No pitch
  problem comes from the table, the 12-bit range or the arp0 clamp.
- **Fixed bug:** short melodies without bar lines kept an in-bar accidental for the whole
  tune. Dangerous V1 bar 2 `g2` played Gb5; per ABC it is G5. The parser now closes a bar
  every `M:` when a voice has no bar lines.
- **User report "missing flats" (Lament, all keys):** the strict ABC reading plays all
  30 bare `e`/`d` (V1 12, V2 17, V3 1) as Eb/Db. The "naturals" reading (§1.3) plays them
  E/D natural. The S1a tape used naturals on 5 of the 7 Lament keys (8, 0, Q, W, E), so
  §1.3's naturals hypothesis is contradicted by ear. The tape is now strict everywhere
  except keys 8 and 0, which stay naturals for A/B.
- Short-melody octave digits (`_a4`, `_b42`, `_d5`, `G5`, `F32`): read as an octave in
  C3 = MIDI 60 numbering (all bar sums depend on it). `_d5`, `_a5`, `_b5`, `G5` contradict
  the letter case by one octave (the digit wins). Uppercase `_D2` is read as Db4, length 2.
  The audit flags all of these.
- Now handled: key signatures K: major/minor (any key; was Fm only); an accidental carried
  across a bar by a tie; tuplets and grace notes are errors (never silently dropped);
  boundary rounding of durations (no drift between voices when a note is not a whole
  number of frames).
- Not a bug, but it can be heard: the tape transposes everything −12 (§1.1), and the
  harpsichord's first frame is +12 (an octave-high 20 ms pluck at full volume).

**WZM v0.1** (format in the `tools/abc2wzm.py` docstring):
- **`$85` legato:** the next note does not re-attack. It has no arp0 frame, and the
  volume table and tremolo phase run on from the previous note. Only the period and the
  note's own gate change. The converter emits it inside ABC slurs (and on ties between
  different pitches), but never into the same pitch, where a repeat re-attacks. A slurred
  note has full gate: its staccato is dropped, and only the last note of a slur keeps its
  gate. `--no-legato` ignores slurs. `--legato-unmarked` also slurs every run of unmarked
  (non-staccato) notes; the Lament's "legato blocks" (§1.3) are an interpretation.
- **Gate:** instrument byte +5 is now `gate_sh`: the staccato gate is
  `dur − (dur >> gate_sh)`. This gives the same frames as v0's `⌈dur·gate8/8⌉` for
  gate8 4/6 (harpsichord 1, organ 2). Shifts replace the multiply loop.
- A rest no longer plays the arp0 period on its frame 0. That frame has volume 0, so it is
  inaudible, but the register stream changes and so the inline golden moved.
- On a legato instrument, the harpsichord sustains a slur on its decayed tail (it ends at
  volume 3). The organ is where legato pays off.

| Item | S1a (v0) | S1b (v0.1) |
|---|---|---|
| Player bytes | 890 (code 616) | **880 (code 606)**: legato +14 B, shift gate −17 B, rest path −1 B, command chain reordered |
| T/frame median / mean | 1,817 / 1,990 (11,203 frames) | 1,889 / 2,028 (17,347 frames, 19 versions incl. the organ Door). Per song unchanged medians; means −10 T (Lament harp 1,843 → 1,833, organ 2,273 → 2,261) |
| worst | 4,869 (organ Lament f.512) | **4,467** (same frame: 3 fetches + staccato switches), −402. Harp Lament 4,518 → 4,170; f8/f6 4,530 → 4,318. Loop frame of the short loops 4,163 → 4,334 (+171: `$80` is now the last test in the command chain). 2-frame tick worst ~6.7k (was 7.1k) |
| one fetch | ~0.8–1.0k | staccato gate ~50–70 T (was ~250–300); a command ~55–90 T (was ~150) |

Test tape: 15 songs; `L` toggles legato and restarts the current song. Songs marked "L"
have a `--no-legato` twin: 7 and 9 (Lament harpsichord/organ, strict, legato-unmarked)
and R/T (*The Last Locked Door*, K:F, real ABC slurs, organ/harpsichord). Tests:
`tests/abc_tools_test.py` (19, incl. slur events, slur oracle + golden, invalid `$85`,
accidental and key rules, rounding) and `tests/music_player.py` (Z80 == oracle for all
19 song versions, incl. both twins, plus the `L` key).

### S1d: tsx-faithful instrument, 45 % gate, exact tempo, WZM v0.2 (2026-10-13, **M**)

**Reference.** The user's browser player `assets/sfx/concepts/player-js/main.tsx` is the
ground truth for notes *and* sound (notes: `tools/tsx_extract.py` →
`assets/sfx/music/src/*.json`). Its gain model is the same in every mode (l.1178–1214):
a sounding note is held at `AY_VOL_TABLE[13]` (V1, V2) or `[14]` (V3) for the whole note,
with no decay, no tremolo and no re-attack between notes; a staccato note drops to level
0 once it is 45 % through; a rest is 0. HARPSICHORD mode (l.1049–1057) only switches all
three oscillators to sawtooth. `tools/tsx_model.py` samples this at 50 Hz (frame k = the
state at k + ½) and compares a WZM register stream with it.

**The S1 harpsichord is audibly wrong.** It decays 15 → 3 and only resets on an attack,
so a legato note sits on its quiet tail while every staccato note restarts at 15.
Per-note mean amplitude on the Lament (AY_VOL_TABLE): legato 0.156, staccato 0.141,
against the tsx's **0.795 / 0.349**. Legato is not louder than staccato, as it is in the
tsx, but about the same. This is the user's "legato shy, staccato loud". It is kept on
the tape only as the A/B "pluck" entry.

**New instruments** (`tools/abc2wzm.py` `INSTRUMENTS` / `INSTR_SETS`):
- `tsx` set = per-voice map `tsx13, tsx13, tsx14`: arp0 0, volume table `[13]` (or 14)
  held, no tremolo, rel_step 15 (0 the frame after the gate), staccato gate (1, 4). This
  is the default for `--source json` and for the whole tape. The player needed no change
  for the levels: equal consecutive pitches re-attack, but with a flat table and arp0 0
  that gives the same registers as no re-attack.
- **Gate, WZM v0.2:** the instrument header grew to 7 B: `+5 = s1+1`, `+6 = s2−s1`, and
  `gate = (dur >> s1) − (dur >> s2)`. (0,1) and (0,2) reproduce v0.1's 50 % / 75 %
  exactly, so the S1 goldens are unchanged. (1,4) = 7/16. For every staccato length the
  Lament produces at 66/74/96 bpm (15–46 frames) it equals round(0.45·dur). The
  converter rejects a gate of 0. Compared with the 50 Hz tsx model: at 96 bpm all 185
  staccato gates are exact; at 74 bpm 153 are exact and 32 are one frame short. Those 32
  are a frame-phase effect: round(0.45·dur) misses the same 32, so only per-note data
  could hit them. A per-note gate byte would cost +185 B on the Lament; the two shifts
  cost +10 B of player code. Cost: ~150 T on a staccato fetch (was ~50).
- Header `+9` is now the song's R7 mixer (`$38`; `$3C` for the buzzer). It was `n_inst`,
  which the player never read.

**Tempo.** Frames per eighth = `Fraction(1500, bpm)` exactly (74 → 750/37). Every note
boundary is rounded on the exact cumulative time (half up), so there is no drift and the
voices stay aligned. One pass: Lament 5,189 frames at 74 bpm, 4,000 at 96. `--bpm`
overrides the tune's tempo, and with `--batch` it overrides the Lament's (`WZM_BPM=… 
tools/build_music_test.sh`). `--frames-per-eighth` takes a fraction (`750/37`).

**Accidentals.** For the Lament ABC the default is now `naturals` (= the tsx: test
`test_iib_vs_old_abc`). Other ABCs stay `strict`. The tape no longer has strict variants;
it plays the JSON, where pitches are exact.

**Tape (`tools/build_music_test.sh`, from the tracked JSON; no concept ABCs needed):**

| Key | Song | Variant |
|---|---|---|
| 1 | Dungeon Crawl | tsx, 72 bpm, loop |
| 2 | Dangerous | tsx, 68 bpm, loop |
| 3 | Boss Fight | tsx, 106 bpm, loop |
| 4 | Level Complete | tsx, 78 bpm, once |
| 5 | Game Win | tsx, 84 bpm, once |
| 6 | Game Over | tsx, 66 bpm, once |
| 7 | Lament IIb | **tsx, 74 bpm** (default) |
| 8 | Lament IIb | tsx, 96 bpm (pick by ear) |
| 9 | Lament IIb | old pluck harpsichord, 74 bpm (A/B) |
| 0 | Lament IIb | experiment: envelope-saw buzzer bass on V3 |
| Q | Lament IIb | experiment: +12 on frame 0 only |

SPACE stops. L restarts the current song (the twin mechanism stays, but no entry has a
twin now).

**Bytes / cycles (M).**

| Item | Value |
|---|---|
| Player, game build (no buzzer) | **893 B** (code 616, table 192, state 85): +13 B vs S1b (gate +10, voice state +3) |
| Player with `DEFINE WZM_BUZZER` (tape) | 970 B (code 693): buzzer +77 B |
| 7 songs (tsx set) | **1,901 B**: Crawl 149, Dangerous 97, Boss 221, Level Complete 93, Win 91, Over 83, Lament 1,167 |
| Player + 7 songs (game build) | **2,794 B** |
| T/frame (tape, buzzer assembled, 256 frames × 11 entries) | median 1,945 (cues) / 1,777 (Lament tsx); worst **4,362** (tsx Lament frame 0), 4,548 with the buzzer (frame 0) |

**(6) Sawtooth approximation (experiment, not the default).** The tsx timbre is a
sawtooth, and the AY's tone is a square, so it is hollower (odd harmonics only).
- *Envelope buzzer on V3* (key 0, instrument set `tsx-buzz`): voice C's volume table
  holds `$10` (envelope mode), and the song's mixer is `$3C` (tone C off, so you hear the
  pure envelope). R13 = `$0C` (rising saw ////) is written once at `player_start`. On a
  buzzer frame the player sets R11/R12 = (TP + 8) >> 4, which gives a saw at the note's
  pitch (rounding error ≤ ~10 cents in the bass, worse higher up: bass only). Cost:
  +77 B (47 B frame, 30 B start), +20 T on every frame, +206 T on a buzzer frame.
  Worst frame 4,548. It is a real sawtooth, but only on one voice: the envelope generator
  is shared. Staccato and rests gate it to 0 like the others. Loudness is not
  comparable: a log-DAC ramp, nominally counted as level 15. Judge by ear.
- *+1 octave on frame 0* (key Q, `tsx-oct`): arp0 12 on the flat instrument. 0 player
  bytes, 0 cycles. It brightens only the 20 ms attack (a click/chiff), not the
  sustained timbre.
- Not tried: a sustained octave mixture (there is no free voice) and per-frame arpeggios
  (the player only has arp0).

**Tests.** `tests/abc_tools_test.py` 35 (new `TsxFaithful`):
- golden register streams for all 11 tape entries;
- against the tsx model: pitches exact on every sounding frame, levels exact except the
  32 pinned one-frame-short gates (74 bpm), every gate within 1 frame;
- loudness: legato > staccato, both means and their ratio within 10 % of the tsx (the
  Lament: 0.795 / 0.344 at 74, 0.795 / 0.347 at 96; each cue's legato mean equals the
  tsx's);
- the pluck harpsichord's inverted ratio is pinned as a known-wrong case;
- the gate formula, gate-0 rejection, exact tempo and the buzzer oracle.

`tests/music_player.py` covers all 11 tape entries: the Z80 equals the oracle, including
the buzzer's R7/R11/R12, and the 96 bpm Lament runs through its loop at 4,000 frames.

### S1e: organ / harpsichord with "crypt reverb" tails, 9/16 gate, tsx-max tempo, WZM v0.3 (2026-10-14, **M**)

**User brief.** S1d tape: "music is much better, but staccato sounds too short". Every
tune at the tsx's maximum tempo (slider max 96 bpm, l.2267; boss_fight's defaultBpm 106
is above it and stays 106), in the two tsx modes with the "cathedral crypt" reverb at
100 % (wet 1.0 / dry 0.5, l.1071-1085; IR = 2.8 s of noise × exp(−2t), l.946-962):
GOTHIC ORGAN (A saw, B square, C triangle, lowpass 8 k) and HARPSICHORD (3 saws,
lowpass 9.5 k).

**What each variant approximates** (`tools/abc2wzm.py` `REVERB`, `GATES`, sets
`organ-rev` / `harp-rev`):

| tsx feature | AY approximation | Fidelity |
|---|---|---|
| Convolution reverb, wet 1.0 / dry 0.5 | **Release tail per voice**: when the gate ends (staccato cut, or the end of a note followed by a rest), the level drops by `drop` steps (the dry part stops; what remains is the wet tail), then falls 1 step (≈3 dB) every `rel_per` frames, i.e. an exponential decay. Organ: 13 → 10, 1 step / 6 frames, **1.2 s** to silence; harpsichord: 13 → 9, 1 step / 4 frames, **0.72 s**. Bass (voice C) from 11 / 10. A rest continues the tail; the next note on the same voice cuts it (it never overlaps that note's attack). A one-shot gets a final rest (67 / 41 frames) so its last chord rings out | The tsx IR decays ~17 dB/s (~1 step / 9.5 frames, ~2 s); both tails are deliberately shorter, per the brief. No diffusion, no stereo, no pitch smear: the tail is the same note at a lower level |
| Reverb smear between consecutive notes (legato) | **Impossible.** One AY channel holds one pitch; a note's tail can only sound where its own voice is silent. The six cues have **no rests and no staccato**, so in them the reverb is audible **only at the end of the one-shots** (Level Complete / Win / Over); in the Lament it fills every staccato gap (~1,750 tail frames in one pass, all voices) |
| Second, quieter, delayed echo | **Impossible with 3 voices**: all three carry melody; an echo needs a free channel (the SFX steal channel would be the only candidate, and only while no SFX plays) |
| ORGAN A: sawtooth | plain square at 13 (a sustained octave/detune mixture is not ≈0: a per-frame arpeggio costs ~40 B + ~60 T/frame and a 25 Hz root/octave alternation sounds like a buzz, not a mixture; detune needs a second channel) | hollower (odd harmonics only) |
| ORGAN B: square | square at 13 | exact |
| ORGAN C: triangle | **envelope buzzer, shape $0E**, period ≈ TP/32. At the bass's own pitch that integer is too coarse (C3: 26.5 → ±33 cents); one octave down it is ≤16 cents on every cue and ≤1 cent on the Lament's common C3/F2/Db3. So the organ's voice C is **transposed −12 (a 16' pedal)**. The tail is a square at the same (pedal) pitch | timbre: the AY envelope is a 16-step log-DAC ramp, not a linear triangle; pitch: **an octave below the tsx** |
| HARPSICHORD A/B: sawtooth | squares at 13 | hollower |
| HARPSICHORD C: sawtooth | **envelope buzzer, shape $0C** (the S1d key-0 experiment, picked over the +12 "blip": it changes the sustained timbre to a real saw at the right pitch; the blip only colours 20 ms). Errors ≤19 cents except one Lament note (C4, 34 cents) | only one voice can be a saw (one envelope generator) |
| Lowpass 8 k / 9.5 k | none | AY output is not filtered (the TV/speaker does that) |
| Level model 13 / 13 / 14 flat | unchanged (buzzer = full envelope level) | flat parts within 10 % (tests) |

**Staccato gate.** WZM v0.3 adds an *add* form, gate = round-half-up(dur >> s1) +
(dur >> s2) (instrument +6 bit 7). `GATES`: **56 = 9/16** (S1e default: eighths at
96 bpm are 15/16 frames → 8/9 frames on), **62 = 5/8** (the "65 %" option: no two-shift
form gives 65 %), **100** = (0,8) subtract form, dur − (dur >> 8) = dur (S1e follow-up:
staccato notes sound their whole row; same player path, the tail then only sounds on
rests — at 100 % the IIb Lament is register-identical to the legato Lament II, test
`test_gate_100`), **30 → exactly 5/16 = 31.25 %** = round(dur >> 2) + (dur >> 4) (the
closest two-shift form; the neighbours are 1/4 and 3/8; a 96 bpm eighth of 15/16 frames
→ 4/5 frames on; within 1 frame of round(5/16 dur) for every length),
**45** = the S1d (1,4) subtract form. Against the 50 Hz model cut at
9/16: 148 of 185 Lament staccato gates exact, 37 one frame short (frame phase, as in
S1d). The gate is a build parameter (`tools/abc2wzm.py --gate`, `WZM_GATE=` for
`tools/build_music_test.sh`) and a tape key (G). With the tail a staccato note still
reads as separated: a 10 dB step (organ) / 13 dB (harpsichord) at the cut.

**WZM v0.3 format** (abc2wzm docstring): instrument header 8 B (+4 `drop`, +7
`rel_per`, +6 bit 7 = add gate); song header +9 = R13 shape (was the R7 mixer). A
rest no longer forces volume 0: it runs the release (with drop ≥ 15 it is silent, so
every S1d stream is unchanged — the S1d goldens still pass, except lament_buzz's R7 on
silent frames). R7 is per frame in the buzzer build: $3C on a buzzer frame, else $38.

**Tape (`tools/build_music_test.sh`; all songs at the tsx-max tempo):**

| Key | Song | Key | Song |
|---|---|---|---|
| 1 | Dungeon Crawl, ORGAN + reverb, 96, loop | Q | same, HARPSICHORD + reverb |
| 2 | Dangerous, organ, 96, loop | W | harpsichord |
| 3 | Boss Fight, organ, 106, loop | E | harpsichord |
| 4 | Level Complete, organ, 96, once | R | harpsichord |
| 5 | Game Win, organ, 96, once | T | harpsichord |
| 6 | Game Over, organ, 96, once | Y | harpsichord |
| 7 | Lament IIb, organ, 96, loop | U | harpsichord |
| 8 | Lament, S1d tsx-faithful 74, no reverb | 9 | Lament, S1d tsx 96, no reverb |
| 0 | **Lament II (legato)**, organ + reverb, 96, loop | I | Lament II, harpsichord + reverb, 96 |
| O | Lament II, tsx-faithful 74, no reverb | P | Lament II, tsx-faithful 96, no reverb |

Lament II = the tsx's "II. Catacomb Lament (Legato)" (`f_minor_lament`, main.tsx
l.728-737: `transposeNotes(BASE_V*_LEGATO, 3, true)`, no staccato), extracted by
`tools/tsx_extract.py` to `assets/sfx/music/src/f_minor_lament.json` (+ reference
`assets/sfx/music/ref/f_minor_lament.abc`): IIb's notes without a single staccato flag
(test `test_lament_ii_legato`). It has no rests either, so its reverb tail never sounds
(only the voices' timbres differ from the dry entries).

**G** cycles the current song's gate 30 → 45 → 56 → 62 → 100 % (from the default 56:
62, 100, 30, 45, 56; `WZM_GATE=30|45|56|62|100` at build time). **H** cycles the reverb
level of the organ / harpsichord entries S1e → 0 → 50 → 100 % (`WZM_REVERB=s1e|0|50|100`;
dry entries 8 / 9 / O / P ignore it). Both patch the current song's instrument bytes in
RAM and restart it: no player change, 0 B / 0 T in the game build. L restarts, SPACE
stops. **J** cycles the echo experiment off → 25 → 50 → 100 % (global; below). The screen
shows title + tempo, mode, "Gate: n%  REVERB n%", "J ECHO experiment: n%", frame, state.

**Reverb levels (key H).** The tsx reverb is a wet/dry *mix*: dry = max(0.3, 1 − wet/2),
wet = the slider, convolver normalised (equal power), IR exp(−2t) = 17.4 dB/s. At a
staccato cut the dry part stops and the wet part rings on, at
wet·w / √(dry² + (wet·w)²) of the note's mix (w = the IR's build-up during the note:
1 for a long note, ≈0.69 for a 96 bpm staccato eighth sounding ~0.16 s):

| Level | tsx (wet / dry) | Tail start vs note | AY mapping (voices A/B; C buzzer drops 2 more) | Tail length from the gate |
|---|---|---|---|---|
| 0 % | 0 / 1.0 | silence | drop 14 (instant cut), rel_per 255 | none |
| 50 % | 0.5 / 0.75 | −5 … −8 dB | **drop 2** (13 → 11), 1 step / **9** frames | ~2.0 s |
| 100 % | 1.0 / 0.5 | −1 … −2 dB | **drop 1** (13 → 12), 1 step / **9** frames | 1 + 9 × 12 = 109 frames ≈ **2.2 s** (tsx ≈ 2 s audible) |
| S1e (default, the sound so far) | — | −10 / −13 dB | organ drop 3, 1 / 6; harpsichord drop 4, 1 / 4 | 1.2 s / 0.72 s |

One AY step ≈ 3 dB; 17.4 dB/s ≈ 5.8 steps/s ≈ 1 step every 8.6 frames → 9. At 50 / 100 %
a staccato note is far less separated than at S1e (−3 / −6 dB step instead of −10 / −13):
that is what the tsx at those settings does. **Still a release-tail approximation, not a
wet/dry mix**: the tail is the voice's own note at a lower level, and only where that
voice is silent (after the gate, in rests); nothing is added under a sounding note, no
smear between notes. The cues have no rests and no staccato, so any level is audible
only at the end of the three one-shots (their final rest now fits the longest, 100 %,
tail: 118 frames).

**Echo experiment: "why not a real wet/dry mix?" (key J, `DEFINE WZM_ECHO`, tape only).**
A true send/return is impossible: all three channels carry melody and the AY has no
mixer after the channels. The nearest thing is **time-sharing**: after every note
change (attacked or legato; not into the same pitch) a voice remembers the previous
note's period at its last level − `pl_edrop`, decaying 1 step every 9 frames (the IR's
17.4 dB/s). On odd frames, and on every frame where the voice itself is silent (after
the gate, in rests), it plays that old note instead of the dry one. Levels (J: off →
25 → 50 → 100 %, global, the song restarts): `pl_edrop` 6 / 4 / 2 steps = the old note
−18 / −12 / −6 dB (100 % ≈ the tsx's wet 1.0 vs dry 0.5). Not done: borrowing another
voice's silent channel for an echo (it would need cross-voice routing in the player).

| Measured (oracle, one pass) | Organ Lament IIb | Legato Lament II (tsx 96) | Dangerous (organ) |
|---|---|---|---|
| Dry frames given to the echo | 46–48 % | 47.5 % | 33.5 % |
| **Dry note level** | **−2.8 dB** (at every wet level) | −2.8 dB | −1.7 dB |
| Wet vs dry power, 25 / 50 / 100 % | −25 / −19 / −12 dB | −24 / −18 / −11 dB | −27 / −21 / −14 dB |

| Cost | Value |
|---|---|
| Player bytes (tape build: buzzer + echo) | **1,200 B** (code 902): **+118 B** over the game configuration (wrapper ~45, fetch hook ~45, 4 B per voice + 2 B state). Song data: **0 B** (runtime). Game build: unaffected (no `WZM_ECHO`: 954 / 1,082 B) |
| T/frame, echo assembled but off | median 2,384 over all entries (2,141 in the game configuration): +~80 T per voice for the wrapper |
| T/frame, echo 100 % | organ Lament median 2,586, worst **5,871** (frame 94), adjacent-pair max **8,457**; Lament II tsx 96 median 2,437, worst 5,446. Still inside the 13k-per-tick contract |

**Verdict (prediction; the user judges by ear).** It will sound like a **25 Hz
flutter / buzz on every note after a change, not like reverb.** The dry note is cut
off on every other frame whatever the wet level, so it loses ~3 dB and is amplitude
modulated at 25 Hz (sidebands ±25 Hz around every partial: the "motor-boat" roughness
of chiptune arpeggios). The old note is only 11–25 dB below, so the "wet" is barely
audible while the chopping is fully audible. This is the same reason the earlier +octave
mixture was rejected. On the buzzer bass (organ/harpsichord voice C) the echo frames
switch the channel between the envelope triangle/saw and a square every frame, which
is rougher still. The tsx's reverb is *louder* than its dry signal (wet 1.0 vs dry 0.5);
here the wet must stay far below dry or it would take over the melody. Expect the
release tails (key H) to be the better reverb on this chip; key J stays a curiosity.
Off by default, so every earlier sound is unchanged (test `test_off_is_identity`).
Note that with `WZM_ECHO` assembled into the tape, the tape's per-frame figures include
the wrapper. The game-configuration figures below are measured on a build without it
(`WZM_ECHO=0 tools/build_music_test.sh -o build/game_cfg`).

**Bytes / cycles (M).**

| Item | Value |
|---|---|
| Player, no buzzer (`DEFINE` absent) | **954 B** (code 671): +61 B vs S1d (release tail ~24, add-gate ~14, state +6) |
| Player with `WZM_BUZZER` = **the game configuration** (both S1e variants need it) | **1,082 B** (code 798): +112 B vs S1d (triangle halving, per-frame R7, R11/R12 written only on change +13 B). In `MODULE wzm` (the game's `defs.asm` has its own `AY_R_MIXER` / `AY_R_VOL_A`): `constants.asm` + `defs.asm` + the player at `AY_RESERVE` assemble with 0 errors |
| Songs per variant (7 tunes) | organ **1,933 B** = harpsichord 1,933 B: Crawl 151, Dangerous 99, Boss 223, Level Complete 101, Win 99, Over 91, Lament 1,169 |
| Lament II (legato) | 1,155 B per entry (no staccato commands: −14 B vs IIb); the tape holds 4 (4,620 B). Tape total 14,208 B (G/H/J tape code and the echo player incl.) of the ~15.8 KB below the vector table |
| Player (buzzer) + one variant (S1f: harpsichord, 5/16 gate) | **1,082 + 1,933 = 3,015 B** of the 4 KB slot. Both variants: streams A/B are identical (only C is transposed for the organ): a shared-stream layout would cost ~+0.7 KB, not +1.9 KB |
| T/frame, game configuration (256 frames × 20 entries, incl. CALL/RET) | organ median **2,158**, harpsichord median **2,141** (was 2,214 / 2,197 before R11/R12 were skipped when unchanged and `VO_PITCH` was kept in B); the buzzer on voice C (~0.3k T, sounding on most frames) is most of the rise over S1d's ~1.9k. S1d tsx Lament 74: median 1,872. **Worst single frame 4,820** (organ Lament frame 0: three staccato fetches + add-gate + buzzer + R7 write; harpsichord 4,803; S1d worst 4,548). **Max over two adjacent frames 6,978** (organ Lament frames 0+1; harpsichord 6,944): the measured 2-frame tick cost, under the safe bound 2 × 4,820 ≈ 9.6k and inside the 13k contract. The echo tape build adds ~0.45k (worst 5,276, pair max 7,677 with echo off) |
| 100 % gate cost | no new code; a staccato fetch runs the subtract path with 8 shifts (~+0.1k T on that fetch only, worst frame ≤ +0.3k if all 3 voices fetch a staccato note together); tail/step logic untouched (frame costs as above) |
| Release cost | a tail frame without a step 54 T (v0.2 release 50 T); a step frame ~0.15k T; a note fetch +19 T (`VO_RACC`); the buzzer build +~36 T/frame for the R7 check |

**Tests.** `tests/abc_tools_test.py` 51 (new `S1eReverb`, `EchoExperiment`: off = identity, alternation + decay, no echo into the same pitch, the 3 levels): goldens of the 14 S1e entries
and the 4 Lament II entries; Lament II = IIb without staccato (128 beats, same pitches);
the 100 % gate (= the whole note; IIb at 100 % == Lament II); every reverb level
(`test_reverb_levels`: flat parts exact and within 10 %, tails below the note and never
rising, tail shape = drop / rel_per, the bytes = `inst_tail`, s1e = default, dry
entries untouched); the 30 % gate within 1 frame of 5/16;
S1d goldens unchanged; tsx-max tempi vs the JSON; against `tools/tsx_model.py` at the
9/16 cut with `tails=True` (pitches exact incl. the −12 pedal, levels exact except the
37 pinned short gates, every tail below the note level and never rising); flat-part
loudness within 10 %; gates 45/56/62/100 within 1 frame of the model; the oracle's gate
formula = the converter's; the tail shape (13…, 10 ×6, 9 ×6…); the one-shot ring-out;
a rest continuing the release. `tests/music_player.py`: Z80 == oracle for all 20
entries (every 96 bpm Lament through its loop), keys 6/SPACE/Q/L/9/0/I/O/P, the G key
(5 gates, ring == oracle on the patched bytes), the H key (stage F: 4 levels on the
organ and harpsichord Lament, bytes == `inst_tail`, ring == oracle; a dry entry
unchanged), the J key (stage G: 4 echo levels on the organ Lament IIb and the legato
Lament II, ring == oracle), chip registers + T per frame (stage D, + 2 entries with echo
100 %). 130 checks on the echo tape. The game configuration (`WZM_ECHO=0 ... -o
build/game_cfg`, `MUSIC_BUILD=build/game_cfg/build`) runs every stage except G: 113 checks.
Stage D prints the max over adjacent frame pairs. The R11/R12 skip changes no register
(stages A and D compare the chip with the oracle every frame).

### S1f. Cue assignment for the game (user ear check, 2026-10-14)

Chosen on the S1e tape: **harpsichord + reverb tail S1e, staccato gate 5/16 (the tape's "30 %" and "31 %" are the same
5/16), 96 bpm** (Boss 106) for every tune. Keys are the tape keys.

| Tape key | Tune (JSON source) | Plays | Mode | Phase |
|---|---|---|---|---|
| **U** | Lament IIb `f_minor_staccato_theme` | **main menu, story screen**, and for now the **in-game theme** (to be replaced later) | loop | SND-2 |
| ~~Q~~ | ~~Dungeon Crawl~~ | **removed from the game by the user 2026-10-19** (unused; −151 B): id 1 is reserved and rejected by the ISR, the other ids keep their numbers; the S1 test tape keeps it | — | — |
| **W** | Dangerous | **danger**: **implemented (SND-3)** — >= 4 awake hostiles in the hero's room or HP <= 25 % of max, hysteresis below | loop | SND-3 |
| **E** | Boss Fight | entering a **boss room** | loop | SND-4 |
| **R** | Level Complete | **once** when the player kills the boss | one-shot | SND-4 |
| **T** | Game Win | **once** when the game is finished successfully | one-shot | SND-4 |
| **Y** | Game Over | **once** when the player dies — **implemented (SND-3)**: `end_turn` death branch, `MUS_REQ` 0 + `MUS_SHOT` 6 | one-shot | SND-3 |

**DANGER trigger (W), as built in SND-3 (manager decision 2026-10-19, replaces the game.md §3.7 threat
score for now):** `mus_pick` (`src/mus7.asm`, bank 7, a plain call from `end_turn` on every surviving turn;
mailbox writes only). Condition = **>= 4 awake hostile monsters in CUR_ROOM** (walks the `LIVE_LIST`; ACTIVE |
HOSTILE, not PENDING / DYING, not ASLEEP; frozen / stunned count) **or hero HP <= MAXHP / 4** (integer, so
exactly 25 % enters). Enter on the condition (`MUS_REQ` = `MUS_DANGER`); leave only when the condition has been
false for **>= 8 consecutive turns AND >= 16 turns have passed since entering** (`DNG_DWELL`, `DNG_CALM`
`$BFF1/$BFF2`; a turn with the condition resets the calm run); then `MUS_REQ` = `MUS_ROOM` (= Lament today; the Q
rotation will replace it). The "or one full loop" shortcut is not used (no loop-end flag in the mailbox; calm >= 8
already implies dwell >= 9). `level_enter` (new game, descent) clears the state. Music off / hold: `MUS_REQ` is
still written (level-triggered), the dispatcher restarts the current request at bar 1 when music returns. After a
room change the list is the old room's for one turn (its entries fail the room test): a one-turn lag.
Cost ~105 T per monster entry + ~0.15k (typ. < 1k T; 761 T with 2 monsters). **Death (Y):** `end_turn`
(the only place `GS_DEAD` is set) writes `MUS_REQ` 0 then `MUS_SHOT` `MUS_OVER` once; the end screen redraw never
touches the mailbox. Tests: `tests/snd3.py`.

Not used for now: the organ variants, the legato Lament II, Echo (J), reverb 0/50/100, gates other than 5/16. The echo
experiment is not built into the game player. Other melodies will be added later.
Budget: player with buzzer ≈ 1.07 KB + 7 harpsichord tunes ≈ 1.93 KB = ≈ 3.0 KB of the 4 KB AY slot.

### SND-2 as built (2026-10-14, **M**; supersedes the interface sketches in §3 B and game.md §3.6 where they differ)

- **Slot:** `ay_play` (mailbox dispatcher, 208 B) + WZM v0.3 player (`WZM_BUZZER`, no echo, 1,082 B) +
  7 harpsichord songs (1,947 B, generated by `tools/abc2wzm.py --game`) = 3,239 B, 857 B free. Layout,
  ids and costs: memory-map.md "Interrupts (A8)" and the `$BFEB..$BFEE` rows; budget: budget.md §5.1.
- **Mailbox semantics (replace the "`$FF` = stop" idea of the S1 test tape):**
  `MUS_REQ` is **level-triggered**: the looping tune id, 0 = silence. It is never consumed; the ISR
  compares it with its private copy and (re)starts on a change, so writing the same id again is a
  no-op (menu → level keeps the Lament playing). `MUS_SHOT` is an **edge**: a one-shot id that the
  ISR clears when it takes it (or drops it while music is off / held / invalid). A shot plays **over**
  the loop; when it ends, the loop **restarts at bar 1** (stinger R). A final cue (Y death, T win) is
  `MUS_REQ` 0 then `MUS_SHOT` id. `MUS_STATE` reports idle / loop / shot and a sticky `MS_DONE`.
- **`SND_MODE` edges** (game.md §3.6) are in the dispatcher: music off → silence once, sequencer
  stops (~0.2k T a frame); music back on → the requested loop restarts at bar 1; `SND_HOLD` → volumes 0,
  sequencer frozen, resumes in place.
- **Not in the player (spec gaps, open for the designer/user; plan.md SND-2):** the **8-frame
  fade-in** on music-on / level start (game.md §3.6, §3 B "fade 12 / 8 frames"), and switching **at
  the next bar line** (§3 B DANGER, game.md §3.7 real-time floor): every change today is an
  immediate cut at the next frame. The **story screen** hook (S1f: U on the story screen) is deferred
  to S1 / 3G (no story screen yet). Death / win cards keep playing U until SND-3 / SND-4 wire Y / T.
- **Hooks today (T3):** `menu_run` and `level_enter` write `MUS_REQ` = `MUS_LAMENT`; `pause_run`
  sets / clears `SND_HOLD`. SND-3's `mus_pick` becomes the only in-play writer.
- **Tests:** `tests/sound.py` (46 checks: oracle-exact chip registers through the Lament loop, edges,
  real pause, shots, per-song ISR cost); `tests/budget.py` runs every scenario with the Lament playing
  and gates work + real.

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
| DANGER | X:2 Dangerous | game.md §3.7 enter test (supersedes "awake hostile in the room") | game.md §3.7: dwell 8 + 3 safe turns, cool-down 6 | **next bar** (same key → seamless) |
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
- Mailbox `SFX_REQ` in bank 2. A call site is `ld a,n : call sfx_req` (5 B), and the routine keeps the higher-priority request. **Bank-3 call sites eat into its 359 B free (SND-2 build).**
- Format: AYFX-like, 1–3 B a frame.

| SFX | Frames | Bytes **E** | Prio | Hook |
|---|---|---|---|---|
| melee swing / hit / miss | 5 / 6 / 4 | 12 / 18 / 10 | 2 / 4 / 2 | 3D |
| kill / hero hurt (ducks) | 12 / 8 | 32 / 22 | 6 / 7 (as built: kill **7**, so a level-up never cuts it; see "SFX as built") | 3D |
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

### SFX as built (SND-5, 2026-10-19, **M**)

- **Request:** `ld a, SFX_x : call sfx_req` (5 B, any bank; `src/sfx2.asm`, bank 2; keeps A / BC).
  Ids = `prio << 5 | index` (`build/sfx/sfx_ids.inc`), so no priority table. `sfx_req` keeps the pending
  `SFX_REQ` unless the new priority is >=; it drops the request while `SND_HOLD` is set or the SFX bit is
  off. The ISR (`sfx_step`, `src/ay.asm`) takes `SFX_REQ` every unheld frame: it replaces the effect
  playing if its priority is **>=** (ties replace); else dropped — except a request of prio >=
  `SFX_DEFER_PRIO` (6), which goes to the **one deferred slot `SFX_NEXT`** (`$BFF3`; overwritten only by
  an id of >= priority; cleared by a pause with nothing playing and on a new level) and starts the frame
  the playing effect ends. `sfx_req` does the same for the loser of two requests in one frame (the old
  pending one or the new one; not the same id twice). **User 2026-10-19: a KILL is never cut by the
  level-up** — KILL is prio **7** (was 6 in the §4 table), LEVELUP 6: a kill and a level-up in one turn
  (either order) play KILL fully, then LEVELUP (`tests/sfx.py` SFX12). HURT (7) still cuts anything
  (a tie with KILL: the later one wins). A new effect plays its frame 0 in that ISR.
- **V1 steal:** one effect at a time, channel A only. While it plays, `wzm.pl_regs` R0/R1/R8 hold the
  effect's values (the mirror stays the chip's image); `player_frame` (`DEFINE WZM_SFX`) sequences V1
  on but does not store it, so the music's note returns on the first frame after the effect, and its
  OUT stage writes the effect's R0/R1/R8 with the music's other registers (no intra-frame V1 glitch).
  The effect's tone/noise-A bits are merged into R7 (the music's tone B/C bits kept). R6 is written to
  the chip AND the mirror on each noise change (a song start's `pl_out_all` mid-effect keeps it) and
  back to the music's 0 at the end. R2-R5, R11-R13 are never written. Frames without `player_frame`
  (music off / idle / a start frame) get the channel-A OUTs from `sfx_out`.
- **Loudness (user 2026-10-19: effects clearly louder than the music):** the music's fixed voice levels
  are **13** (V1 / V2 every song, the tsx gain; V3's tail <= 10; measured with the oracle over all 6
  songs). While **any** effect plays, the music's V2 / V3 fixed volumes are **ducked by 3** (prio >= 6:
  **by 4**), floor 0, in the mirror before the OUTs (`sfx_dk`), so the duck ends with the effect (the
  player rewrites them each frame). Effect peaks are **14-15** (every effect, `tests/sfx.py` SFX6):
  headroom at the peak = 14-15 vs 10 (9 for prio >= 6) = 4-6 AY steps (~6-9 dB). Not ducked: V3 in
  envelope mode (the buzzer bass: a fixed volume there would mute it, tone C is off on a buzzer frame);
  its peak is the envelope's 15, in the bass register.
- **Pause / mode:** `SND_HOLD` freezes the effect with the music (R8-R10 0, `SFX_REQ` dropped every held
  frame), the effect resumes at its next frame. SFX bit off (`SND_MODE` 0 or 1) stops a playing effect at
  once; mode 2 (SFX only) plays effects over silence.
- **Format** (AYFX-like, 1-3 B a frame; `tools/sfx2asm.py` docstring): B0 = volume (bits 0-3), tone off
  (bit 4), pitch byte follows (bit 5), noise byte follows (bit 6), noise off (bit 7); pitch = index into
  the music's period table `wzm.pl_tp` (MIDI - 12); noise = R6 0..31; `$FF` = end.
- **Tool:** effects are text in `assets/sfx/effects.json` (per frame `v<vol> t<note|idx> n<noise> x<repeat>`;
  no `t` = tone off, no `n` = noise off; `"like": X, "transpose": k` = a transposed copy of X).
  `tools/build.sh` runs `tools/sfx2asm.py` into `build/sfx/` (`sfx_ids.inc` included by `main.asm`,
  `sfx_data.asm` by `ay.asm`). Add an effect = append it to the JSON (ids are file order, max 31) and
  call `sfx_req` with `SFX_<NAME>`.

| Effect | Prio | Frames | Bytes | Hook (bank) |
|---|---|---|---|---|
| MENU | 1 | 4 | 7 | `menu_run` key 1-4 (1) |
| MISS | 2 | 5 | 11 | `impact_line` → `sfx_msg` MSG_P_MISS / MSG_M_MISS (low RAM → 2) |
| HIT | 4 | 6 | 17 | idem MSG_P_HIT |
| KILL | **7** | 10 | 28 | idem MSG_P_KILL (melee, Power Strike, dagger / arrow) |
| HURT | 7 | 8 | 21 | idem MSG_M_HIT (a monster's blow on the hero) |
| FIZZ | 3 | 5 | 12 | NO MANA refusal `ic_no_mana`; a fizzled release in `act_fire` (7) |
| LEVELUP | 6 | 16 | 21 | `xp_level` (7); behind a KILL / HURT: deferred (`SFX_NEXT`), never lost |
| SPARK / FIREBOLT / FROST / DRAIN / LIGHTNING | 4 / 4 / 4 / 4 / 5 | 7 / 8 / 10 / 11 / 11 | 19 / 25 / 21 / 23 / 25 | `act_fire` → `sfx_abl` (the release tick; 7 → 2) |
| POWER / WHIRL | 5 | 9 / 11 | 23 / 23 | idem |
| THROW | 3 | 4 | 9 | idem (dagger, bow) |
| BURST | 5 | 10 | 22 | `fx_trk_tick` impact of `firebolt_burst` (`fx_imp_sfx` in `sfx2.asm`, 2) |
| BOUNCE | 3 | 3 | 6 | `fx_step` segment change: bounce / reflection (2) |
| ST_STUNNED / FROZEN (+7) / ASLEEP (−7) / FEAR (−3) / CONFUSED (+4) | 4 | 6 each | 13 each | `sfx_msg` MSG_M_FROZEN .. MSG_M_CONFUSED (a monster's status line: `dh_msg` / `st_msg`) |
| LADDER | 1 | 2 | 4 | `try_climb` step (7) |
| JUMP / FALL | 3 / 4 | 6 / 14 | 11 / 29 | the jump / `hero_fall` (low RAM; a jump into the pit: FALL replaces JUMP) |
| LAND | 2 | 3 | 9 | `anim_entity` jump end / fall end, the hero (2) |
| DOOR | 4 | 10 | 25 | `door_open` (low RAM; hero or monster) |
| **Total** | | | **510** (table 54 + data 456) | |

- **Not built (no event today / held):** menu move / cancel (the main menu has no cursor; the pause box
  runs under `SND_HOLD`, where requests are dropped by the user's rule), gate raise (3B: the grate is
  always raised; 3F's boss death), the hero's own status lines (hero statuses go through `msg_push`, no
  hook), step (default off), melee swing (not in this round). 3E (pickup / gold / potion / eat / trap)
  and 3F (boss) come with those features.
- **Space:** engine 381 B in the AY slot + data 510 B; slot **109 B free** (songs 1,794 B after the
  Crawl removal). Elsewhere: bank 2 +122 B (free to FRT 178; `kind_tab` ALIGN pad 41 → **13 B**), low
  RAM +25, bank 7 +36, bank 1 +7, bank 3 cold 0.
- **Cost:** ~40 T a frame idle (music off ISR 465 T), ~0.1k T of hooks per music frame (music-only worst
  5,381 T); effect frames ~0.4-0.9k T; worst ISR measured **6,243 T** (a prio-7 effect taken every frame
  over the Lament; contract 6.5k); details memory-map.md "Interrupts (A8)". Tests: `tests/sfx.py`.

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
| **S4** proto B state machine (X:1–6) | 3F (boss, win and death exist) | staff + composer | S1; DANGER trigger = game.md §3.7 (done) | fades ~30 T |
| **S5** loop extensions, mix pass | 3G | composer, user in Fuse | all | none |

This moves part of plan.md's "3G Sound" earlier. That is a manager/user decision.

## 7. Open questions

1. **Re-export `6-melodies.abc`**: X:1 V2 bar 1, X:2 V1 bar 1 and X:5 V3 bar 1 are truncated; the X:1, X:4 and X:6 headers are damaged.
2. **Lament accidentals**: are the 29 bare `e`/`d` E♮/D♮ (my reading) or E♭/D♭? To be confirmed by ear with the T3 A/B render, then fixed in the source.
3. Transpose the suite down an octave (recommended) or keep it as written?
4. B's EXPLORE: X:1 Dungeon Crawl, or the Lament (X:1 then becomes the title/menu tune)?
5. How long should the Crawl/Danger/Boss loops be (8 bars fits; 16 bars only without the Lament or with pattern reuse), and who writes the extensions (user tool vs composer)?
6. Still open from rev 1: flowmusic.app terms; the player's real bytes and T; level-up as stinger or SFX; the ZRCP AY-register command and ZEsarUX audio-to-file; a GM soundfont for T5.
